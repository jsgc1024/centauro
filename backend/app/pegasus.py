# -*- coding: utf-8 -*-
"""Pegasus, el GPS de las unidades: la conexion (seccion 60).

Pegasus Gateway es la plataforma de Digital Communications Technologies
que opera Centauro Satelital. Esto es lo unico del sistema que habla con
ella, y **solo lee**. Lo que no hace, y esta amarrado en el codigo:

  * No escribe nada en Pegasus. Despues de entrar solo hace GET a las
    rutas de LECTURAS; cualquier otra truena antes de salir a la red.
  * No guarda la clave: vive en el `.env` del servidor y aqui solo se
    usa para pedir la sesion.
  * Pocas llamadas y espaciadas. Los eventos (/rawdata) tienen una cuota
    por usuario --30 por minuto, 500 por hora-- y otra de TODO el sitio
    de Centauro Satelital --60 por minuto, 800 por hora--, que comparte
    con sus operadores y sus clientes. Se piden de 25 unidades en 25.
  * Si Pegasus contesta 429 (demasiadas), no se le pide nada hasta la
    hora que diga. Seguir pidiendo despues de un 429 hace que bloquee la
    IP: lo dice su documentacion.

Las horas que manda Pegasus son UTC y las velocidades, millas por hora.
Aqui no se convierte nada: eso es de las reglas (`gps_reglas.py`).
"""
import logging
import time

import httpx

registro = logging.getLogger("centauro.pegasus")

# Lo unico que se le pide despues de entrar.
LECTURAS = {"/groups", "/vehicles", "/rawdata", "/trips", "/counters"}
POR_LLAMADA = 25          # unidades por consulta de eventos
PAUSA = 0.4               # segundos entre llamadas: tope de 3 por segundo

# La sesion se guarda mientras viva el proceso: pedir una nueva cada dos
# minutos serian treinta entradas por hora con la misma clave.
_sesiones: dict[tuple, str] = {}

# La pausa despues de un 429. Vive en Redis para que la respeten todos los
# procesos --el worker de Celery tiene varios--; si Redis no contesta, al
# menos la respeta este.
LLAVE_PAUSA = "pegasus:pausa_hasta"
ESPERA_SIN_AVISO = 15 * 60      # segundos, si el 429 no dice hasta cuando
ESPERA_MAXIMA = 60 * 60
_pausa_local = 0.0
_redis_cliente = None


class NoResponde(Exception):
    """Pegasus no contesto, o contesto que no. El mensaje es corto y no
    trae nada de la sesion ni de la clave."""


def _redis():
    global _redis_cliente
    if _redis_cliente is None:
        try:
            import redis

            from app.config import settings
            _redis_cliente = redis.Redis.from_url(
                settings.redis_url, socket_connect_timeout=0.5,
                socket_timeout=0.5, decode_responses=True)
            _redis_cliente.ping()
        except Exception:                                  # noqa: BLE001
            _redis_cliente = False
    return _redis_cliente or None


def pausa_hasta() -> float:
    """Hasta cuando (epoch) no se le pide nada a Pegasus; 0 si se puede."""
    guardada = 0.0
    r = _redis()
    if r is not None:
        try:
            guardada = float(r.get(LLAVE_PAUSA) or 0)
        except Exception:                                  # noqa: BLE001
            guardada = 0.0
    return max(guardada, _pausa_local)


def _pausar(respuesta) -> float:
    """Pegasus dijo 429: hasta cuando no se le pide nada."""
    global _pausa_local
    ahora = time.time()
    try:
        hasta = float(respuesta.headers.get("X-RateLimit-Reset") or 0)
    except ValueError:
        hasta = 0.0
    if hasta <= ahora:
        hasta = ahora + ESPERA_SIN_AVISO
    hasta = min(hasta, ahora + ESPERA_MAXIMA) + 5
    _pausa_local = hasta
    r = _redis()
    if r is not None:
        try:
            r.set(LLAVE_PAUSA, hasta, ex=int(hasta - ahora) + 1)
        except Exception:                                  # noqa: BLE001
            pass
    return hasta


def quitar_pausa() -> None:
    """Para las pruebas: olvida la pausa."""
    global _pausa_local
    _pausa_local = 0.0
    r = _redis()
    if r is not None:
        try:
            r.delete(LLAVE_PAUSA)
        except Exception:                                  # noqa: BLE001
            pass


def _mensaje_de_pausa(hasta: float) -> str:
    minutos = max(1, int((hasta - time.time()) // 60) + 1)
    return (f"Pegasus pidio bajar el ritmo: no se le vuelve a pedir nada "
            f"en {minutos} min.")


def lista_de(respuesta) -> list:
    """Pegasus pagina en {data: [...]} y a veces contesta la lista sola."""
    if isinstance(respuesta, list):
        return respuesta
    if isinstance(respuesta, dict):
        for llave in ("data", "events", "trips", "counters", "results",
                      "groups", "vehicles"):
            if isinstance(respuesta.get(llave), list):
                return respuesta[llave]
    return []


def en_tandas(ids: list, n: int = POR_LLAMADA):
    for i in range(0, len(ids), n):
        yield ids[i:i + n]


class Pegasus:
    def __init__(self, sitio: str, usuario: str, clave: str,
                 timeout: float = 30):
        sitio = (sitio or "").strip().rstrip("/")
        if sitio and not sitio.startswith("http"):
            sitio = "https://" + sitio
        self.sitio = sitio
        self.base = sitio + "/api"
        self._usuario = (usuario or "").strip()
        self._clave = clave or ""
        self.http = httpx.Client(timeout=timeout, headers={
            "Accept": "application/json",
            "User-Agent": "centauro/1.0"})
        self.llamadas = 0
        self._ultima = 0.0

    # ----------------------------------------------------------- la sesion

    def _entrar(self) -> None:
        """La unica escritura permitida: pedir la sesion."""
        credenciales = {"username": self._usuario, "password": self._clave}
        try:
            self._esperar()
            r = self.http.post(f"{self.base}/login", json=credenciales)
            if r.status_code in (400, 415, 422):
                # Hay sitios que la piden como formulario.
                self._esperar()
                r = self.http.post(f"{self.base}/login", data=credenciales)
        except httpx.ConnectError:
            # Un sitio mal escrito o que no existe cae aqui, antes de que
            # haya sesion. Sin esto la lectura tronaba cada dos minutos en
            # vez de decir en pantalla que no hay conexion.
            raise NoResponde("No se encontro el sitio de Pegasus o no "
                             "contesta: revisa PEGASUS_SITIO.")
        except httpx.HTTPError as e:
            raise NoResponde(f"Pegasus no contesto ({type(e).__name__}).")
        if r.status_code == 429:
            raise NoResponde(_mensaje_de_pausa(_pausar(r)))
        if r.status_code != 200:
            raise NoResponde(f"Pegasus no dejo entrar ({r.status_code}): "
                             "revisa el usuario y la clave de la conexion.")
        try:
            token = (r.json() or {}).get("auth")
        except ValueError:
            token = None
        if not token:
            raise NoResponde("Pegasus contesto sin sesion.")
        _sesiones[(self.sitio, self._usuario)] = token
        self.http.headers["Authenticate"] = token

    def _esperar(self) -> None:
        hasta = pausa_hasta()
        if hasta > time.time():
            raise NoResponde(_mensaje_de_pausa(hasta))
        falta = PAUSA - (time.monotonic() - self._ultima)
        if falta > 0:
            time.sleep(falta)
        self._ultima = time.monotonic()
        self.llamadas += 1

    def leer(self, ruta: str, **params):
        if ruta not in LECTURAS:
            raise RuntimeError(f"{ruta} no esta entre las lecturas permitidas")
        token = _sesiones.get((self.sitio, self._usuario))
        if token:
            self.http.headers["Authenticate"] = token
        else:
            self._entrar()
        for intento in (1, 2):
            self._esperar()
            try:
                r = self.http.get(f"{self.base}{ruta}", params=params)
            except httpx.HTTPError as e:
                raise NoResponde(f"Pegasus no contesto ({type(e).__name__}).")
            if r.status_code == 429:
                raise NoResponde(_mensaje_de_pausa(_pausar(r)))
            if r.status_code == 401 and intento == 1:
                # La sesion vencio: una vez mas con una nueva.
                _sesiones.pop((self.sitio, self._usuario), None)
                self._entrar()
                continue
            if r.status_code != 200:
                raise NoResponde(f"Pegasus contesto {r.status_code} en {ruta}.")
            try:
                return r.json()
            except ValueError:
                raise NoResponde(f"Pegasus no contesto JSON en {ruta}.")
        raise NoResponde("Pegasus no acepto la sesion.")

    # ----------------------------------------------------------- lecturas

    def grupos(self) -> list[dict]:
        return [g for g in lista_de(self.leer("/groups", set=1000))
                if isinstance(g, dict)]

    def unidades(self, grupo_id: int) -> list[dict]:
        """Las unidades del grupo con lo ultimo que reporto cada equipo."""
        return [u for u in lista_de(self.leer(
            "/vehicles", groups=grupo_id, set=1000,
            select="id,name,info,device:latest"))
            if isinstance(u, dict)]

    def eventos(self, vehiculos: list, duracion: str,
                etiquetas: str | None = None, campos: str | None = None,
                tope: int | None = None) -> list[dict]:
        """Los eventos crudos de esas unidades, de 25 en 25.

        `duracion` es ISO 8601 hacia atras desde ahora ("PT10M", "P1D").
        Quien llama filtra por hora: Pegasus no siempre respeta los
        limites exactos y aqui no se adivina."""
        salida = []
        for tanda in en_tandas([str(v) for v in vehiculos]):
            params = {"vehicles": ",".join(tanda), "duration": duracion}
            if etiquetas:
                params["labels"] = etiquetas
            if campos:
                params["fields"] = campos
            if tope:
                params["tail"] = tope
            salida.extend(e for e in lista_de(self.leer("/rawdata", **params))
                          if isinstance(e, dict))
        return salida

    def tramos(self, vehiculos: list, duracion: str) -> list[dict]:
        """Los tramos del dia: los de movimiento son trayectos y los
        demas, paradas."""
        salida = []
        for tanda in en_tandas([str(v) for v in vehiculos]):
            salida.extend(t for t in lista_de(self.leer(
                "/trips", vehicles=",".join(tanda), duration=duracion))
                if isinstance(t, dict))
        return salida


def desde_la_configuracion():
    """El cliente con lo que diga el `.env`, o nada si falta algo."""
    from app.config import settings

    if not (settings.pegasus_sitio and settings.pegasus_usuario
            and settings.pegasus_clave):
        return None
    return Pegasus(settings.pegasus_sitio, settings.pegasus_usuario,
                   settings.pegasus_clave)

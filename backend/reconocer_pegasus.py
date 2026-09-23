# -*- coding: utf-8 -*-
"""Reconocimiento de Pegasus (el GPS de las unidades), de SOLO LECTURA.

Antes de construir nada con el GPS de las unidades hay que ver que da de
verdad la plataforma de DCT: que campos trae cada unidad, si la placa
viene y como viene escrita, cada cuanto reporta, que eventos manda
--encendido, apagado, exceso de velocidad, panico--, en que unidades
vienen la velocidad y la distancia, y si las horas vienen en UTC o en
hora local.

Lo que NO hace, y esta amarrado en el codigo:
  * No escribe nada en Pegasus. Despues de entrar solo hace GET a las
    rutas de LECTURAS; cualquier otra truena antes de salir a la red.
  * No imprime ni guarda la clave, coordenadas, direcciones, placas
    completas, nombres, telefonos, VIN ni IMEI. De la placa solo sale su
    forma ("AAA-999-A"); de la posicion, cuanto hace que la reporto.
  * Seis llamadas en total: los limites de Pegasus son de cientos por
    hora y aqui no se gasta ni una de mas.

Se corre desde la raiz del proyecto:

    docker compose run --rm api python reconocer_pegasus.py

Pide el sitio, el usuario y la clave (la clave no se ve al escribirla);
tambien los lee de PEGASUS_SITIO, PEGASUS_USUARIO y PEGASUS_CLAVE si
estan en el entorno. La clave no se guarda en ningun lado. El detalle
queda en backend/reconocimiento_pegasus.txt, que no va a git; en la
terminal sale solo el resumen.
"""
import collections
import getpass
import os
import re
import statistics
import sys
from datetime import datetime, timezone

import httpx

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "reconocimiento_pegasus.txt")

# Lo unico que este script le pide a Pegasus despues de entrar.
LECTURAS = {"/user", "/vehicles", "/rawdata", "/counters", "/trips"}

# Nunca se imprime su valor: solo que existe y de que tipo es.
DELICADOS = re.compile(
    r"(^|_)(lat|lon|lng|loc|location|coords?|coordinates|geo|address|"
    r"direccion|street|city|state|zip|plate|placa|license|vin|imei|esn|"
    r"serial|phone|tel|mobile|email|mail|name|nombre|driver|asset|"
    r"password|pass|token|auth|key|secret|user(name)?)($|_)",
    re.IGNORECASE)

# Campos cuyo valor si ayuda a entender y no dice nada de nadie.
CLAROS = re.compile(
    r"^(id|vid|code|label|type|mph|kph|speed|head|heading|alt|hdop|pdop|"
    r"sats?|valid|online|io_\w+|ecu_\w+|event_time|system_time|\w*_time|"
    r"\w*time\w*|temp\d*|dev_\w+|vehicle_\w+|vo|ce|cl|odometer|distance|"
    r"dist\w*|duration|fuel\w*|battery\w*|make|model|year|set|page|pages|"
    r"total|state|status|trip\w*|moving|ign\w*)$",
    re.IGNORECASE)


class Pegasus:
    def __init__(self, sitio: str):
        sitio = sitio.strip().rstrip("/")
        if not sitio.startswith("http"):
            sitio = "https://" + sitio
        self.sitio = sitio
        self.base = sitio + "/api"
        self.http = httpx.Client(timeout=60, headers={
            "Accept": "application/json",
            "User-Agent": "centauro-reconocimiento/1.0"})
        self.llamadas = 0
        self.fallas = []

    def entrar(self, usuario: str, clave: str) -> None:
        """La unica escritura permitida: pedir la sesion."""
        credenciales = {"username": usuario, "password": clave}
        self.llamadas += 1
        r = self.http.post(f"{self.base}/login", json=credenciales)
        if r.status_code in (400, 415, 422):
            # Hay sitios que la piden como formulario.
            self.llamadas += 1
            r = self.http.post(f"{self.base}/login", data=credenciales)
        if r.status_code in (404, 405):
            # Y otros entran por el servidor central de DCT.
            self.llamadas += 1
            r = self.http.post("https://auth.pegasusgateway.com/", json={
                **credenciales,
                "gateway": self.sitio.split("://", 1)[-1]})
        if r.status_code != 200:
            raise SystemExit(f"No se pudo entrar ({r.status_code}): "
                             f"{_corto(r.text)}")
        token = (r.json() or {}).get("auth")
        if not token:
            raise SystemExit("Pegasus contesto sin sesion ('auth').")
        self.http.headers["Authenticate"] = token

    def leer(self, ruta: str, **params):
        if ruta not in LECTURAS:
            raise RuntimeError(f"{ruta} no esta entre las lecturas permitidas")
        self.llamadas += 1
        try:
            r = self.http.get(f"{self.base}{ruta}", params=params)
        except httpx.HTTPError as e:
            self.fallas.append(f"{ruta}: {type(e).__name__}")
            return None
        if r.status_code != 200:
            self.fallas.append(f"{ruta}: {r.status_code} {_corto(r.text)}")
            return None
        try:
            return r.json()
        except ValueError:
            self.fallas.append(f"{ruta}: no contesto JSON")
            return None


# ------------------------------------------------------------ ayudas

def _corto(texto: str, n: int = 160) -> str:
    return re.sub(r"\s+", " ", texto or "")[:n]


def forma(texto) -> str:
    """'ABC-123-D' -> 'AAA-999-A': como viene escrita, sin decir cual es."""
    if texto is None:
        return "(vacia)"
    s = str(texto).strip()
    if not s:
        return "(vacia)"
    return re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", s))


def lista_de(respuesta) -> list:
    """Pegasus pagina en {data: [...]} y a veces contesta la lista sola."""
    if isinstance(respuesta, list):
        return respuesta
    if isinstance(respuesta, dict):
        for llave in ("data", "events", "trips", "counters", "results"):
            if isinstance(respuesta.get(llave), list):
                return respuesta[llave]
    return []


def recorrer(obj, prefijo=""):
    """Cada hoja del objeto como ('a.b.c', valor)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from recorrer(v, f"{prefijo}.{k}" if prefijo else str(k))
    elif isinstance(obj, list):
        if obj and all(isinstance(x, (dict, list)) for x in obj):
            for x in obj[:3]:
                yield from recorrer(x, prefijo + "[]")
        else:
            yield prefijo, obj
    else:
        yield prefijo, obj


def tipo(valor) -> str:
    if valor is None:
        return "nulo"
    if isinstance(valor, bool):
        return "si/no"
    if isinstance(valor, (int, float)):
        return "numero"
    if isinstance(valor, list):
        return "lista"
    if isinstance(valor, str) and re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}",
                                           valor):
        return "fecha"
    return "texto"


def mostrar(ruta: str, valor):
    """El valor si es claro; si no, solo su tipo."""
    hoja = ruta.split(".")[-1].replace("[]", "")
    if DELICADOS.search(hoja):
        return f"<{tipo(valor)}>"
    if CLAROS.match(hoja) and not isinstance(valor, (dict, list)):
        return valor
    return f"<{tipo(valor)}>"


def momento(valor) -> datetime | None:
    """Fecha ISO o epoch (segundos o milisegundos), sin zona: UTC."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        if valor > 1e12:
            valor = valor / 1000
        if 1e9 < valor < 4e9:
            return datetime.fromtimestamp(valor, tz=timezone.utc)
        return None
    if isinstance(valor, str):
        try:
            d = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


def mas_reciente(obj) -> datetime | None:
    """La hora mas nueva que traiga el objeto en un campo *time*."""
    fechas = [momento(v) for r, v in recorrer(obj)
              if "time" in r.split(".")[-1].lower()]
    fechas = [f for f in fechas if f]
    return max(fechas) if fechas else None


def estructura(objetos: list) -> list[str]:
    """Que campos trae, en cuantos objetos, y un ejemplo tapado."""
    presencia = collections.Counter()
    ejemplo = {}
    for o in objetos:
        vistos = set()
        for r, v in recorrer(o):
            if r in vistos:
                continue
            vistos.add(r)
            presencia[r] += 1
            if r not in ejemplo or ejemplo[r] in (None, "", []):
                ejemplo[r] = v
    n = max(len(objetos), 1)
    return [f"  {r:<44} {presencia[r]:>5}/{n:<5} {mostrar(r, ejemplo[r])!s:.60}"
            for r in sorted(presencia)]


# ------------------------------------------------------------ el reconocimiento

def main():
    sitio = os.environ.get("PEGASUS_SITIO") or input(
        "Sitio de Pegasus (como entras en el navegador): ")
    usuario = os.environ.get("PEGASUS_USUARIO") or input("Usuario: ")
    clave = os.environ.get("PEGASUS_CLAVE") or getpass.getpass(
        "Clave (no se ve al escribirla): ")
    p = Pegasus(sitio)
    p.entrar(usuario.strip(), clave)
    del clave

    detalle, resumen = [], []

    def ambos(linea=""):
        resumen.append(linea)
        detalle.append(linea)

    ahora = datetime.now(timezone.utc)
    ambos(f"Reconocimiento de Pegasus -- {ahora:%Y-%m-%d %H:%M} UTC")
    ambos()

    # --- quien entro: solo que permisos trae, nunca quien es
    yo = p.leer("/user")
    if isinstance(yo, dict):
        detalle.append("USUARIO (campos, sin valores personales)")
        detalle.extend(estructura([yo]))
        detalle.append("")

    # --- las unidades
    datos = p.leer("/vehicles", set=1000)
    unidades = lista_de(datos)
    tiene_equipo = any(isinstance(u, dict) and isinstance(u.get("device"), dict)
                       for u in unidades)
    if unidades and not tiene_equipo:
        # Sin el equipo no hay ultima posicion: se pide con el.
        otra = lista_de(p.leer("/vehicles", set=1000,
                               select="id,name,info,device"))
        if otra:
            unidades = otra
    total = (datos.get("total") if isinstance(datos, dict) else None) or len(unidades)
    ambos(f"UNIDADES: {total}")

    placas = collections.Counter()
    nombres = collections.Counter()
    marcas = collections.Counter()
    edades = collections.Counter()
    en_linea = collections.Counter()
    adelantadas = 0
    recientes = []
    for u in unidades:
        if not isinstance(u, dict):
            continue
        info = u.get("info") if isinstance(u.get("info"), dict) else {}
        placas[forma(info.get("license_plate") or info.get("plate"))] += 1
        nombres[forma(u.get("name"))] += 1
        if info.get("make"):
            marcas[str(info.get("make")).strip().title()] += 1
        equipo = u.get("device") if isinstance(u.get("device"), dict) else {}
        conexion = equipo.get("connection") if isinstance(
            equipo.get("connection"), dict) else {}
        if "online" in conexion:
            en_linea["en linea" if conexion.get("online") else "sin linea"] += 1
        ultima = mas_reciente(equipo) or mas_reciente(u)
        if ultima is None:
            edades["sin hora"] += 1
            continue
        minutos = (ahora - ultima).total_seconds() / 60
        if minutos < -5:
            adelantadas += 1
        recientes.append((ultima, u.get("id")))
        edades["menos de 10 min" if minutos < 10 else
               "menos de 1 hora" if minutos < 60 else
               "menos de 24 horas" if minutos < 1440 else
               "mas de 24 horas"] += 1

    con_placa = sum(n for f, n in placas.items() if f != "(vacia)")
    ambos(f"  con placa: {con_placa} de {len(unidades)}")
    ambos("  como viene escrita la placa: " + ", ".join(
        f"{f} x{n}" for f, n in placas.most_common(6)))
    ambos("  como viene el nombre:        " + ", ".join(
        f"{f} x{n}" for f, n in nombres.most_common(6)))
    if marcas:
        ambos("  marcas: " + ", ".join(f"{m} x{n}" for m, n in marcas.most_common(8)))
    if recientes:
        mas_nueva = max(r[0] for r in recientes)
        ambos(f"  la que reporto mas reciente: hace "
              f"{(ahora - mas_nueva).total_seconds() / 60:.0f} min "
              "(si da ~360 con unidades andando, las horas vienen en hora "
              "de Mexico y no en UTC)")
    ambos("  ultimo reporte: " + ", ".join(
        f"{k} {edades[k]}" for k in ("menos de 10 min", "menos de 1 hora",
                                     "menos de 24 horas", "mas de 24 horas",
                                     "sin hora") if edades[k]))
    if en_linea:
        ambos("  conexion: " + ", ".join(f"{k} {n}" for k, n in en_linea.items()))
    if adelantadas:
        ambos(f"  OJO: {adelantadas} unidades reportan horas en el futuro; "
              "las horas podrian venir en hora local, no en UTC")
    ambos()
    detalle.append("CAMPOS DE UNA UNIDAD (presencia / ejemplo tapado)")
    detalle.extend(estructura([u for u in unidades if isinstance(u, dict)]))
    detalle.append("")

    # --- las cinco que reportaron mas reciente: su ultimo dia
    recientes.sort(key=lambda x: x[0], reverse=True)
    elegidas = [str(i) for _, i in recientes[:5] if i is not None]
    if not elegidas:
        elegidas = [str(u.get("id")) for u in unidades[:5]
                    if isinstance(u, dict) and u.get("id") is not None]
    if not elegidas:
        ambos("Sin unidades con identificador: no se piden eventos.")
        cerrar(p, resumen, detalle)
        return
    ids = ",".join(elegidas)
    ambos(f"EL ULTIMO DIA DE {len(elegidas)} UNIDADES (las que reportaron mas reciente)")

    crudo = p.leer("/rawdata", vehicles=ids, duration="P1D")
    eventos = [e for e in lista_de(crudo) if isinstance(e, dict)]
    ambos(f"  eventos: {len(eventos)}")
    if eventos:
        etiquetas = collections.Counter(
            f"{e.get('label')} (codigo {e.get('code')}, tipo {e.get('type')})"
            for e in eventos)
        ambos("  eventos por etiqueta:")
        for etiqueta, n in etiquetas.most_common(25):
            ambos(f"    {etiqueta}: {n}")
        velocidades = [e[c] for e in eventos for c in ("mph", "kph", "speed")
                       if isinstance(e.get(c), (int, float))]
        campos_vel = sorted({c for e in eventos for c in ("mph", "kph", "speed")
                             if c in e})
        if velocidades:
            ambos(f"  velocidad en {', '.join(campos_vel)}: maxima "
                  f"{max(velocidades)}, mediana {statistics.median(velocidades)}")
        distancias = sorted({r for e in eventos[:50] for r, _ in recorrer(e)
                             if re.search(r"dist|odom|(^|\.)vo$", r)})
        if distancias:
            ambos("  campos de distancia: " + ", ".join(distancias))
        # Cada cuanto reporta, unidad por unidad.
        por_unidad = collections.defaultdict(list)
        for e in eventos:
            m = momento(e.get("event_time"))
            if m:
                por_unidad[e.get("vid")].append(
                    (m, (e.get("mph") or e.get("kph") or e.get("speed") or 0) > 0))
        andando, parado = [], []
        for marcas_ in por_unidad.values():
            marcas_.sort()
            for (a, mov), (b, _) in zip(marcas_, marcas_[1:]):
                (andando if mov else parado).append((b - a).total_seconds())
        if andando:
            ambos(f"  cada cuanto reporta andando: {statistics.median(andando):.0f} s "
                  "(mediana)")
        if parado:
            ambos(f"  cada cuanto reporta parado:  {statistics.median(parado):.0f} s "
                  "(mediana)")
        horas = [momento(e.get("event_time")) for e in eventos]
        futuras = sum(1 for h in horas if h and (h - ahora).total_seconds() > 300)
        if futuras:
            ambos(f"  OJO: {futuras} eventos con hora en el futuro: "
                  "event_time vendria en hora local")
        detalle.append("CAMPOS DE UN EVENTO (presencia / ejemplo tapado)")
        detalle.extend(estructura(eventos))
        detalle.append("")
    ambos()

    # --- la distancia y las horas de motor de ese dia
    cuentas = p.leer("/counters", vehicles=ids, duration="P1D")
    if cuentas is not None:
        filas = lista_de(cuentas)
        if not filas and isinstance(cuentas, dict):
            # {id_unidad: {contadores}} o un solo objeto.
            if cuentas and all(isinstance(v, dict) for v in cuentas.values()):
                filas = [{"vid": k, **v} for k, v in cuentas.items()]
            else:
                filas = [cuentas]
        ambos("CONTADORES DEL ULTIMO DIA (por unidad, id interno)")
        for f in filas[:5]:
            if not isinstance(f, dict):
                continue
            numeros = {r: v for r, v in recorrer(f)
                       if isinstance(v, (int, float)) and not isinstance(v, bool)
                       and re.search(r"dist|ign|idle|fuel|(^|\.)(vo|ce|cl)$", r)}
            ident = f.get("vid") or f.get("id") or f.get("vehicle") or "?"
            ambos(f"  unidad {ident}: " + ", ".join(
                f"{r}={v}" for r, v in sorted(numeros.items())[:10]))
        detalle.append("CAMPOS DE LOS CONTADORES")
        detalle.extend(estructura([f for f in filas if isinstance(f, dict)]))
        detalle.append("")
        ambos()

    # --- los viajes: arranque, llegada, duracion, distancia
    viajes = [v for v in lista_de(p.leer("/trips", vehicles=ids,
                                         duration="P1D")) if isinstance(v, dict)]
    ambos(f"VIAJES DEL ULTIMO DIA: {len(viajes)}")
    if viajes:
        detalle.append("CAMPOS DE UN VIAJE (presencia / ejemplo tapado)")
        detalle.extend(estructura(viajes))
        detalle.append("")
    cerrar(p, resumen, detalle)


def cerrar(p: Pegasus, resumen: list, detalle: list):
    pie = [f"Llamadas a Pegasus: {p.llamadas}"]
    if p.fallas:
        pie.append("Lo que no contesto:")
        pie.extend(f"  {f}" for f in p.fallas)
    resumen.extend(pie)
    detalle.extend(pie)
    with open(SALIDA, "w", encoding="utf-8") as f:
        f.write("\n".join(detalle) + "\n")
    print("\n".join(resumen))
    print(f"\nEl detalle quedo en backend/{os.path.basename(SALIDA)} "
          "(no va a git).")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nCancelado.")

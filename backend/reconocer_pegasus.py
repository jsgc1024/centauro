# -*- coding: utf-8 -*-
"""Reconocimiento de Pegasus (el GPS de las unidades), de SOLO LECTURA.

Antes de construir nada con el GPS de las unidades hay que ver que da de
verdad la plataforma: si la placa viene y como viene escrita, cada cuanto
reporta cada unidad, que eventos manda --encendido, apagado, exceso de
velocidad, panico--, en que unidades vienen la velocidad y la distancia,
y si las horas vienen en UTC o en hora local.

Solo mira un grupo de Proteccion Ejecutiva: "2025 P.E." (Mexico) por
omision, o "CENTAURO BRASIL" con PEGASUS_GRUPO (decisiones de Salvador,
23 sep). El gateway es el de Centauro Satelital y trae las unidades de
otras areas y de clientes, que aqui no tienen nada que hacer. De los
demas grupos no se imprime ni el nombre.

Tambien cuenta los panicos del ultimo mes: el evento "panic" (codigo
10, segun Salvador), para confirmar como llega y cada cuanto pasa.

Lo que NO hace, y esta amarrado en el codigo:
  * No escribe nada en Pegasus. Despues de entrar solo hace GET a las
    rutas de LECTURAS; cualquier otra truena antes de salir a la red.
  * No pide coordenadas, y si llegan no las imprime ni las guarda; nada
    de direcciones, placas completas, nombres, telefonos, VIN ni IMEI.
    De la placa solo sale su forma ("AAA-999-A"); de la posicion, cuanto
    hace que la reporto.
  * Pocas llamadas y espaciadas: los limites de Pegasus son de tres por
    segundo y unos cientos por hora.

Se corre desde la raiz del proyecto:

    docker compose run --rm api python reconocer_pegasus.py

Pide el sitio, el usuario y la clave (la clave no se ve al escribirla);
tambien los lee de PEGASUS_SITIO, PEGASUS_USUARIO, PEGASUS_CLAVE y
PEGASUS_GRUPO si estan en el entorno. La clave no se guarda en ningun
lado. El detalle queda en backend/reconocimiento_pegasus.txt, que no va
a git; en la terminal sale solo el resumen.
"""
import collections
import getpass
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone

import httpx

AQUI = os.path.dirname(os.path.abspath(__file__))
GRUPO = "2025 P.E."
PANICO = "panic"
POR_LLAMADA = 25          # unidades por consulta de eventos (limite de Pegasus)
PAUSA = 0.5               # segundos entre llamadas: tope de 3 por segundo
KM_POR_MILLA = 1.609344

# Lo unico que este script le pide a Pegasus despues de entrar.
LECTURAS = {"/user", "/groups", "/vehicles", "/rawdata", "/counters",
            "/trips"}

# Los campos de evento que se piden. Sin coordenadas: para esta prueba
# no hacen falta y asi ni siquiera viajan.
CAMPOS_EVENTO = "vid,event_time,system_time,label,code,type,mph,head,io_ign"

# Nunca se imprime su valor: solo que existe y de que tipo es.
DELICADOS = re.compile(
    r"(^|_)(lat|lon|lng|loc|location|coords?|coordinates|geo|address|"
    r"direccion|street|city|state|zip|plate|placa|license|vin|imei|esn|"
    r"serial|phone|tel|mobile|email|mail|name|nombre|alias|description|"
    r"driver|asset|password|pass|token|auth|key|secret|user(name)?)($|_)",
    re.IGNORECASE)

# Campos cuyo valor si ayuda a entender y no dice nada de nadie.
CLAROS = re.compile(
    r"^(id|vid|code|label|type|mph|kph|speed|head|heading|alt|hdop|pdop|"
    r"sats?|valid|online|io_\w+|ecu_\w+|event_time|system_time|\w*_time|"
    r"\w*time\w*|temp\d*|dev_\w+|vehicle_\w+|vo|ce|cl|odometer|distance|"
    r"dist\w*|duration|fuel\w*|battery\w*|make|model|year|set|page|pages|"
    r"total|status|trip\w*|moving|ign\w*|epoch\w*|age)$",
    re.IGNORECASE)


class Pegasus:
    def __init__(self, sitio: str):
        sitio = sitio.strip().rstrip("/")
        if not sitio.startswith("http"):
            sitio = "https://" + sitio
        self.sitio = sitio
        self.base = sitio + "/api"
        self.http = httpx.Client(timeout=90, headers={
            "Accept": "application/json",
            "User-Agent": "centauro-reconocimiento/2.0"})
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

    def leer(self, ruta: str, callar=False, **params):
        if ruta not in LECTURAS:
            raise RuntimeError(f"{ruta} no esta entre las lecturas permitidas")
        if self.llamadas:
            time.sleep(PAUSA)
        self.llamadas += 1
        try:
            r = self.http.get(f"{self.base}{ruta}", params=params)
        except httpx.HTTPError as e:
            self.fallas.append(f"{ruta}: {type(e).__name__}")
            return None
        if r.status_code != 200:
            if not callar:
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
        for llave in ("data", "events", "trips", "counters", "results",
                      "groups"):
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
    partes = [p.replace("[]", "") for p in ruta.split(".")]
    if any(DELICADOS.search(p) for p in partes):
        return f"<{tipo(valor)}>"
    if CLAROS.match(partes[-1]) and not isinstance(valor, (dict, list)):
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
    """La hora mas nueva que traiga el objeto en un campo de hora."""
    fechas = [momento(v) for r, v in recorrer(obj)
              if re.search(r"time|epoch|date", r.split(".")[-1], re.I)]
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
    return [f"  {r:<48} {presencia[r]:>5}/{n:<5} {mostrar(r, ejemplo[r])!s:.60}"
            for r in sorted(presencia)]


def en_tandas(ids: list, n: int = POR_LLAMADA):
    for i in range(0, len(ids), n):
        yield ids[i:i + n]


def normal(nombre: str) -> str:
    return re.sub(r"[\s.\-_]", "", str(nombre or "")).lower()


def mediana(valores):
    return statistics.median(valores) if valores else None


# ------------------------------------------------------------ el reconocimiento

def main():
    sitio = os.environ.get("PEGASUS_SITIO") or input(
        "Sitio de Pegasus (como entras en el navegador): ")
    usuario = os.environ.get("PEGASUS_USUARIO") or input("Usuario: ")
    clave = os.environ.get("PEGASUS_CLAVE") or getpass.getpass(
        "Clave (no se ve al escribirla): ")
    grupo_buscado = os.environ.get("PEGASUS_GRUPO") or GRUPO
    global SALIDA
    SALIDA = os.path.join(AQUI, f"reconocimiento_pegasus_{normal(grupo_buscado)}.txt")
    p = Pegasus(sitio)
    p.entrar(usuario.strip(), clave)
    del clave

    detalle, resumen = [], []

    def ambos(linea=""):
        resumen.append(linea)
        detalle.append(linea)

    ahora = datetime.now(timezone.utc)
    ambos(f"Reconocimiento de Pegasus, grupo «{grupo_buscado}» -- "
          f"{ahora:%Y-%m-%d %H:%M} UTC")
    ambos()

    # --- el grupo: solo el de Proteccion Ejecutiva
    grupos = [g for g in lista_de(p.leer("/groups", set=1000))
              if isinstance(g, dict)]
    grupo = next((g for g in grupos
                  if normal(g.get("name")) == normal(grupo_buscado)), None)
    if grupo is None:
        # De los demas grupos no se dice el nombre: solo los que se
        # parecen, por si el nombre trae otro espacio u otro punto.
        parecidos = [g.get("name") for g in grupos
                     if re.search(r"p\.?\s*e\.?\b|protec", str(g.get("name")),
                                  re.I)]
        ambos(f"No encontre el grupo «{grupo_buscado}» entre {len(grupos)} "
              "grupos.")
        if parecidos:
            ambos("  Se parecen: " + " | ".join(map(str, parecidos[:10])))
        cerrar(p, resumen, detalle)
        return
    gid = grupo.get("id")
    ambos(f"GRUPO: id {gid}")

    # --- sus unidades, con lo ultimo que reporto cada equipo
    unidades = []
    for select in ("id,name,info,device:latest", "id,name,info,device:latest.loc",
                   None):
        params = {"groups": gid, "set": 1000}
        if select:
            params["select"] = select
        unidades = [u for u in lista_de(p.leer("/vehicles", callar=bool(select),
                                               **params))
                    if isinstance(u, dict)]
        if unidades:
            break
    ambos(f"UNIDADES DEL GRUPO: {len(unidades)}")
    if not unidades:
        cerrar(p, resumen, detalle)
        return

    placas = collections.Counter()
    marcas = collections.Counter()
    sin_placa = []
    edades = collections.Counter()
    ultimas = []
    for u in unidades:
        info = u.get("info") if isinstance(u.get("info"), dict) else {}
        placa = info.get("license_plate")
        placas[forma(placa)] += 1
        if not str(placa or "").strip():
            sin_placa.append(u.get("id"))
        if info.get("make"):
            marcas[f"{str(info['make']).strip().title()} "
                   f"{str(info.get('model') or '').strip().title()}".strip()] += 1
        equipo = u.get("device") if isinstance(u.get("device"), dict) else {}
        ultima = mas_reciente(equipo)
        if ultima is None:
            edades["sin hora"] += 1
            continue
        ultimas.append(ultima)
        minutos = (ahora - ultima).total_seconds() / 60
        edades["menos de 10 min" if minutos < 10 else
               "menos de 1 hora" if minutos < 60 else
               "menos de 24 horas" if minutos < 1440 else
               "de 1 a 7 dias" if minutos < 10080 else
               "mas de 7 dias"] += 1

    con_placa = len(unidades) - len(sin_placa)
    ambos(f"  con placa: {con_placa} de {len(unidades)}")
    ambos("  como viene escrita la placa: " + ", ".join(
        f"{f} x{n}" for f, n in placas.most_common(8)))
    if sin_placa:
        ambos("  sin placa (id interno de Pegasus, para capturarla alla): "
              + ", ".join(str(i) for i in sin_placa[:40]))
    if marcas:
        ambos("  unidades: " + ", ".join(
            f"{m} x{n}" for m, n in marcas.most_common(10)))
    ambos("  ultimo reporte: " + ", ".join(
        f"{k} {edades[k]}" for k in ("menos de 10 min", "menos de 1 hora",
                                     "menos de 24 horas", "de 1 a 7 dias",
                                     "mas de 7 dias", "sin hora")
        if edades[k]))
    if ultimas:
        mas_nueva = (ahora - max(ultimas)).total_seconds() / 60
        ambos(f"  la que reporto mas reciente: hace {mas_nueva:.0f} min"
              + ("  <- parece hora de Mexico, no UTC"
                 if 330 <= mas_nueva <= 390 else ""))
    ambos()
    detalle.append("CAMPOS DE UNA UNIDAD CON SU ULTIMO REPORTE "
                   "(presencia / ejemplo tapado)")
    detalle.extend(estructura(unidades))
    detalle.append("")

    ids = [str(u.get("id")) for u in unidades if u.get("id") is not None]

    # --- el ultimo dia de eventos, en tandas de 25 unidades
    eventos = []
    for tanda in en_tandas(ids):
        crudo = p.leer("/rawdata", vehicles=",".join(tanda), duration="P1D",
                       fields=CAMPOS_EVENTO)
        eventos.extend(e for e in lista_de(crudo) if isinstance(e, dict))
    activas = {e.get("vid") for e in eventos}
    ambos(f"EVENTOS DEL ULTIMO DIA: {len(eventos)}, de {len(activas)} unidades")
    if eventos:
        etiquetas = collections.Counter(
            f"{e.get('label')} (codigo {e.get('code')}, tipo {e.get('type')})"
            for e in eventos)
        ambos("  por etiqueta:")
        for etiqueta, n in etiquetas.most_common(30):
            ambos(f"    {etiqueta}: {n}")
        mph = [e["mph"] for e in eventos
               if isinstance(e.get("mph"), (int, float))]
        if mph:
            ambos(f"  velocidad (mph): maxima {max(mph)} "
                  f"= {max(mph) * KM_POR_MILLA:.0f} km/h; en movimiento, "
                  f"mediana {mediana([v for v in mph if v > 0]) or 0} mph")
        encendido = collections.Counter(str(e.get("io_ign")) for e in eventos)
        if encendido:
            ambos("  encendido (io_ign): " + ", ".join(
                f"{k} {n}" for k, n in encendido.most_common()))
        # Cada cuanto reporta, unidad por unidad.
        por_unidad = collections.defaultdict(list)
        for e in eventos:
            m = momento(e.get("event_time"))
            if m:
                por_unidad[e.get("vid")].append((m, (e.get("mph") or 0) > 0))
        andando, parado, retraso = [], [], []
        for marcas_ in por_unidad.values():
            marcas_.sort()
            for (a, mov), (b, _) in zip(marcas_, marcas_[1:]):
                (andando if mov else parado).append((b - a).total_seconds())
        for e in eventos:
            a, b = momento(e.get("event_time")), momento(e.get("system_time"))
            if a and b:
                retraso.append((b - a).total_seconds())
        if andando:
            ambos(f"  cada cuanto reporta andando: {mediana(andando):.0f} s "
                  "(mediana)")
        if parado:
            ambos(f"  cada cuanto reporta parado:  {mediana(parado):.0f} s "
                  "(mediana)")
        if retraso:
            ambos(f"  cuanto tarda en llegar a Pegasus: {mediana(retraso):.0f} s "
                  f"(mediana), {max(retraso):.0f} s el peor")
        horas = [momento(e.get("event_time")) for e in eventos]
        horas = [h for h in horas if h]
        if horas:
            ultimo = (ahora - max(horas)).total_seconds() / 60
            ambos(f"  el evento mas reciente: hace {ultimo:.0f} min"
                  + ("  <- parece hora de Mexico, no UTC"
                     if 330 <= ultimo <= 390 else ""))
        detalle.append("CAMPOS DE UN EVENTO (presencia / ejemplo tapado)")
        detalle.extend(estructura(eventos))
        detalle.append("")
    ambos()

    # --- la distancia y las horas de motor de ese dia
    filas = []
    for tanda in en_tandas(ids):
        cuentas = p.leer("/counters", vehicles=",".join(tanda), duration="P1D")
        filas_ = lista_de(cuentas)
        if not filas_ and isinstance(cuentas, dict):
            if cuentas and all(isinstance(v, dict) for v in cuentas.values()):
                filas_ = [{"vid": k, **v} for k, v in cuentas.items()]
            else:
                filas_ = [cuentas]
        filas.extend(f for f in filas_ if isinstance(f, dict))
    anduvieron = [f for f in filas
                  if isinstance(f.get("dev_dist"), (int, float)) and f["dev_dist"] > 0]
    ambos(f"KILOMETROS DEL ULTIMO DIA: {len(anduvieron)} de {len(filas)} unidades "
          "se movieron")
    for f in sorted(anduvieron, key=lambda f: -f["dev_dist"])[:15]:
        motor = f.get("dev_ign") or f.get("ignition") or 0
        ambos(f"  unidad {f.get('vid')}: {f['dev_dist'] / 1000:.1f} km, "
              f"{motor / 3600:.1f} h de motor")
    if anduvieron:
        ambos(f"  en total: {sum(f['dev_dist'] for f in anduvieron) / 1000:.0f} km")
    detalle.append("CAMPOS DE LOS CONTADORES")
    detalle.extend(estructura(filas))
    detalle.append("")
    ambos()

    # --- los viajes: arranque, llegada, duracion, distancia
    viajes = []
    for tanda in en_tandas(ids):
        viajes.extend(v for v in lista_de(p.leer(
            "/trips", vehicles=",".join(tanda), duration="P1D"))
            if isinstance(v, dict))
    # Pegasus parte el dia en tramos: los de movimiento son trayectos y
    # los demas, paradas.
    trayectos = [v for v in viajes if v.get("moving")]
    ambos(f"TRAMOS DEL ULTIMO DIA: {len(viajes)} ({len(trayectos)} trayectos, "
          f"{len(viajes) - len(trayectos)} paradas)")
    if viajes:
        dur = [v["duration"] / 60 for v in trayectos
               if isinstance(v.get("duration"), (int, float))]
        dist = [v["distance"] / 1000 for v in trayectos
                if isinstance(v.get("distance"), (int, float))]
        if dur:
            ambos(f"  trayectos: duracion mediana {mediana(dur):.0f} min")
        if dist:
            ambos(f"  trayectos: distancia mediana {mediana(dist):.1f} km, "
                  f"el mas largo {max(dist):.1f} km")
        fines = [momento(v.get("end_time")) for v in viajes]
        fines = [f for f in fines if f]
        if fines:
            ultimo = (ahora - max(fines)).total_seconds() / 60
            ambos(f"  el tramo que termino mas reciente: hace {ultimo:.0f} min"
                  + ("  <- parece hora de Mexico, no UTC"
                     if 330 <= ultimo <= 390 else ""))
        detalle.append("CAMPOS DE UN VIAJE (presencia / ejemplo tapado)")
        detalle.extend(estructura(viajes))
        detalle.append("")
    ambos()

    # --- el panico: un mes, solo ese evento. Con tope por si el filtro
    # no se respeta: asi nunca se baja el mes entero.
    panicos, otros = [], 0
    for tanda in en_tandas(ids):
        crudo = p.leer("/rawdata", vehicles=",".join(tanda), duration="P30D",
                       labels=PANICO, tail=500,
                       fields="vid,event_time,label,code,type")
        for e in lista_de(crudo):
            if not isinstance(e, dict):
                continue
            if str(e.get("label", "")).lower() == PANICO:
                panicos.append(e)
            else:
                otros += 1
    ambos(f"PANICO EN LOS ULTIMOS 30 DIAS: {len(panicos)}, en "
          f"{len({e.get('vid') for e in panicos})} unidades")
    if panicos:
        codigos = collections.Counter(f"codigo {e.get('code')}, tipo {e.get('type')}"
                                      for e in panicos)
        ambos("  como llega: " + ", ".join(f"{c} x{n}" for c, n in codigos.items()))
        fechas = sorted((momento(e.get("event_time")) for e in panicos
                         if momento(e.get("event_time"))), reverse=True)
        ambos("  los mas recientes (UTC): " + ", ".join(
            f"{f:%d/%m %H:%M}" for f in fechas[:5]))
        por_dia = collections.Counter(f.date() for f in fechas)
        ambos(f"  dias con panico: {len(por_dia)}; el dia con mas: "
              f"{max(por_dia.values())}")
    if otros:
        ambos(f"  OJO: llegaron {otros} eventos que no son panico: el filtro "
              "por etiqueta no se respeto y la cuenta puede estar corta")
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


SALIDA = os.path.join(AQUI, "reconocimiento_pegasus.txt")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nCancelado.")

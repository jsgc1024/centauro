#!/usr/bin/env python3
"""Arma un servicio de ejemplo, publica su task sheet y guarda la hoja
como task_sheet.html para abrirla en el navegador."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "http://localhost:8000"


def pedir(metodo, ruta, cuerpo=None, token=None, crudo=False):
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    datos = json.dumps(cuerpo, default=str).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo, headers=cab)
    try:
        with urllib.request.urlopen(req) as r:
            bruto = r.read()
            return r.status, (bruto.decode() if crudo else json.loads(bruto or "null"))
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or "null")
        except json.JSONDecodeError:
            return e.code, bruto.decode(errors="replace")[:300]


def entrar(correo, contrasena="centauro2026"):
    d = urllib.parse.urlencode({"username": correo, "password": contrasena}).encode()
    req = urllib.request.Request(BASE + "/auth/token", data=d, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]


pedir("POST", "/sistema/sembrar-catalogos")
h = entrar("ana.solis@centauro.lat")

_, paises = pedir("GET", "/catalogos/paises", token=h)
mx = next(p for p in paises if p["codigo"] == "MX")
_, plazas = pedir("GET", "/catalogos/plazas", token=h)
cdmx = next(p for p in plazas if p["nombre"] == "Ciudad de Mexico")
_, mods = pedir("GET", "/catalogos/modalidades", token=h)
M = {x["codigo"]: x for x in mods if x["pais_id"] == mx["id"]}
_, clientes = pedir("GET", "/catalogos/clientes", token=h)
_, personal = pedir("GET", "/catalogos/personal", token=h)
_, flota = pedir("GET", "/catalogos/vehiculos", token=h)
_, hoteles = pedir("GET", "/catalogos/hoteles", token=h)
juan = next(p for p in personal if p["nombre"] == "Juan Ramirez")
miguel = next(p for p in personal if p["nombre"] == "Miguel Torres")
ana = next(p for p in personal if p["nombre"] == "Ana Solis")

# Cada corrida toma fechas libres, para no chocar con lo que dejo la anterior.
_, servicios = pedir("GET", "/servicios", token=h)
base = date.today() + timedelta(days=200 + len(servicios) * 5)
fechas = [base, base + timedelta(days=1), base + timedelta(days=2)]

_, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual", "consultor_id": ana["id"],
    "solicitante_nombre": "Patricia Lopez", "solicitante_correo": "patricia@cliente.com",
    "solicitante_telefono": "55 5555 1010",
    "ejecutivo_nombre": "Mr. John Carter", "ejecutivo_correo": "jcarter@cliente.com",
    "ejecutivo_telefono": "+1 555 010 2030",
    "equipos": [{"clave": "EQ-1", "jornadas": [
        {"fecha": fechas[0], "modalidad_id": M["transfer"]["id"],
         "hora_presentacion": "14:30:00"},
        {"fecha": fechas[1], "modalidad_id": M["full_day"]["id"],
         "hora_presentacion": "07:30:00"},
        {"fecha": fechas[2], "modalidad_id": M["full_day"]["id"],
         "hora_presentacion": "08:00:00"},
    ]}]}, token=h)

agendas = [
    ("Recepcion en aeropuerto y traslado al hotel",
     "14:30 Presentacion en Terminal 1, sala de llegadas internacionales\n"
     "15:15 Recepcion del ejecutivo\n"
     "16:00 Traslado al hotel"),
    ("Jornada corporativa en Reforma y Santa Fe",
     "07:30 Salida del hotel\n09:00 Oficinas corporativas Reforma\n"
     "13:30 Comida de negocios en Polanco\n"
     "16:00 Visita a planta en Santa Fe\n19:30 Regreso al hotel"),
    None,   # el tercer dia va sin agenda, a proposito
]

for j, (agenda) in zip(srv["equipos"][0]["jornadas"], agendas):
    for ruta, cuerpo, que in (
        ("asignar-personal", {"persona_id": juan["id"], "forzar": True}, "el conductor"),
        ("asignar-vehiculo", {"vehiculo_id": flota[0]["id"], "forzar": True}, "la unidad"),
    ):
        codigo, r = pedir("POST", f"/servicios/jornadas/{j['id']}/{ruta}",
                          cuerpo, token=h)
        if codigo != 200:
            print(f"No se pudo asignar {que} el {j['fecha']}: HTTP {codigo}")
            print(json.dumps(r.get("detail", r), indent=2, ensure_ascii=False)[:400])
            raise SystemExit(1)
    pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen", {
        "origen_lat": "19.4247", "origen_lon": "-99.1700", "geocerca_metros": 250,
        "origen_direccion": "Four Seasons, Paseo de la Reforma 500, CDMX"}, token=h)
    if agenda:
        pedir("PUT", f"/operacion/jornadas/{j['id']}/agenda",
              {"resumen": agenda[0], "puntos": agenda[1]}, token=h)

# El segundo dia se suma un agente de seguridad
pedir("POST", f"/servicios/jornadas/{srv['equipos'][0]['jornadas'][1]['id']}/asignar-personal",
      {"persona_id": miguel["id"], "forzar": True}, token=h)

pedir("POST", "/hospedajes", {
    "servicio_id": srv["id"], "hotel_id": hoteles[0]["id"], "habitacion": "1204",
    "desde": fechas[0], "hasta": fechas[2],
    "notas": "Llegada tarde, confirmar late check-in"}, token=h)

pedir("PUT", f"/servicios/{srv['id']}/senal", {
    "texto": "MR. CARTER"}, token=h)

codigo, pub = pedir("POST", f"/task-sheets/servicio/{srv['id']}/publicar",
                    {}, token=h)
if codigo != 200:
    print("No se pudo publicar:", json.dumps(pub, indent=2, ensure_ascii=False))
    raise SystemExit(1)

for idioma, archivo in (("en", "task_sheet.html"),
                        ("es", "task_sheet_es.html")):
    codigo, hoja = pedir("GET",
                         f"/task-sheets/servicio/{srv['id']}/hoja?idioma={idioma}",
                         token=h, crudo=True)
    with open(archivo, "w") as f:
        f.write(hoja)

print(f"{srv['folio']} equipo {pub.get('equipo')} publicado "
      f"(version {pub['version']})")
print("Hoja en ingles:  task_sheet.html")
print("Hoja en espanol: task_sheet_es.html")
print("Abrelas con:  open task_sheet.html task_sheet_es.html")

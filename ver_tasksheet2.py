#!/usr/bin/env python3
"""Segundo ejemplo: estancia de 5 dias con el mismo equipo todos los dias.
Es el caso normal, para ver la hoja limpia."""
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
luis = next(p for p in personal if p["nombre"] == "Luis Mendoza")
ana = next(p for p in personal if p["nombre"] == "Ana Solis")
suburban = next(v for v in flota if v["placa"] == "ABC-5678")

_, servicios = pedir("GET", "/servicios", token=h)
base = date.today() + timedelta(days=400 + len(servicios) * 7)
fechas = [base + timedelta(days=i) for i in range(5)]
# Llegada y salida son transfers de aeropuerto; en medio, tres full days.
MODALIDADES = ["transfer", "full_day", "full_day", "full_day", "transfer"]

_, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual", "consultor_id": ana["id"],
    "solicitante_nombre": "Karen Whitfield",
    "solicitante_correo": "kwhitfield@cliente.com",
    "solicitante_telefono": "+1 312 555 0144",
    "ejecutivo_nombre": "Mr. Daniel Brooks",
    "ejecutivo_correo": "dbrooks@cliente.com",
    "ejecutivo_telefono": "+1 312 555 0190",
    "equipos": [{"jornadas": [
        {"fecha": f, "modalidad_id": M[mo]["id"],
         "hora_presentacion": "07:30:00", "km_estimados": 150}
        for f, mo in zip(fechas, MODALIDADES)]}]}, token=h)

equipo = srv["equipos"][0]
agendas = [
    ("Arrival and transfer to hotel",
     "07:30 Pickup at Benito Juarez International Airport, Terminal 1\n"
     "09:00 Transfer to hotel\n11:00 Standby at hotel"),
    ("Corporate meetings in Reforma",
     "07:30 Departure from hotel\n09:00 Corporate offices, Paseo de la Reforma\n"
     "13:30 Business lunch, Polanco\n17:00 Return to hotel"),
    ("Plant visit, Santa Fe",
     "07:30 Departure from hotel\n09:30 Plant visit, Santa Fe\n"
     "14:00 Lunch on site\n18:00 Return to hotel"),
    ("Meetings and dinner",
     "07:30 Departure from hotel\n10:00 Meetings, Polanco\n"
     "20:00 Dinner, Roma Norte\n23:00 Return to hotel"),
    ("Departure",
     "07:30 Departure from hotel\n09:00 Benito Juarez International Airport\n"
     "10:00 Service ends"),
]

for j, agenda in zip(equipo["jornadas"], agendas):
    for ruta, cuerpo, que in (
        ("asignar-personal", {"persona_id": luis["id"], "forzar": True}, "conductor"),
        ("asignar-vehiculo", {"vehiculo_id": suburban["id"], "forzar": True}, "unidad"),
    ):
        codigo, r = pedir("POST", f"/servicios/jornadas/{j['id']}/{ruta}", cuerpo, token=h)
        if codigo != 200:
            print(f"No se pudo asignar {que} el {j['fecha']}: HTTP {codigo}")
            print(json.dumps(r.get("detail", r), indent=2, ensure_ascii=False)[:300])
            raise SystemExit(1)
    if j is equipo["jornadas"][0]:
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen", {
            "origen_lat": "19.4361", "origen_lon": "-99.0719",
            "geocerca_metros": 300,
            "origen_direccion": ("Benito Juarez International Airport, Terminal 1 "
                                 "- International arrivals, at the exit of "
                                 "customs filter")}, token=h)
    else:
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen", {
            "origen_lat": "19.4250", "origen_lon": "-99.1742",
            "geocerca_metros": 250,
            "origen_direccion": ("The St. Regis, Paseo de la Reforma 439, CDMX "
                                 "- hotel lobby")}, token=h)
    # Vuelo del ejecutivo: llegada el primer dia, salida el ultimo.
    if j is equipo["jornadas"][0]:
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/vuelo",
              {"vuelo_aerolinea": "American Airlines", "vuelo_numero": "AA 1298",
             "vuelo_origen": "Chicago O'Hare",
             "vuelo_hora": f"{fechas[0]}T07:55:00"}, token=h)
    elif j is equipo["jornadas"][-1]:
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/vuelo",
              {"vuelo_aerolinea": "American Airlines", "vuelo_numero": "AA 1299",
             "vuelo_hora": f"{fechas[-1]}T10:40:00"}, token=h)
    pedir("PUT", f"/operacion/jornadas/{j['id']}/agenda",
          {"resumen": agenda[0], "puntos": agenda[1]}, token=h)

pedir("POST", "/hospedajes", {
    "servicio_id": srv["id"], "hotel_id": hoteles[1]["id"],
    "desde": fechas[0], "hasta": fechas[-1],
    "notas": "Check-in previo confirmado por el cliente"}, token=h)

pedir("PUT", f"/servicios/{srv['id']}/senal", {
    "texto": "D. BROOKS"}, token=h)

codigo, pub = pedir("POST", f"/task-sheets/servicio/{srv['id']}/publicar", {}, token=h)
if codigo != 200:
    print(json.dumps(pub, indent=2, ensure_ascii=False))
    raise SystemExit(1)

for idioma, archivo in (("en", "task_sheet2.html"), ("es", "task_sheet2_es.html")):
    codigo, hoja = pedir("GET",
                         f"/task-sheets/servicio/{srv['id']}/hoja?idioma={idioma}",
                         token=h, crudo=True)
    with open(archivo, "w") as f:
        f.write(hoja)

print(f"{srv['folio']} equipo {pub.get('equipo')} · 5 dias, mismo equipo")
print(f"   {fechas[0]} al {fechas[-1]}")
print("Ingles:  task_sheet2.html")
print("Espanol: task_sheet2_es.html")

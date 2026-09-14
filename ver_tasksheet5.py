#!/usr/bin/env python3
"""Quinto ejemplo: un transfer de llegada y tres full days.

El caso mas comun de un ejecutivo de visita: llega en vuelo, lo recogen
en el aeropuerto, y despues tres dias completos con el mismo conductor y
la misma unidad. Prueba el desglose por modalidad en el encabezado
("3 full days · 1 transfer") y que el primer dia no repita su punto de
origen, porque ya va arriba en el meet and greet.
"""
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


def buscar(lista, clave, valor, que):
    encontrado = next((x for x in lista if x.get(clave) == valor), None)
    if not encontrado:
        print(f"Falta {que} ({valor}) en el catalogo.")
        print("Corre:  ./reiniciar.sh    para volver a sembrar.")
        raise SystemExit(1)
    return encontrado


conductor = buscar(personal, "nombre", "Luis Mendoza", "el conductor")
ana = buscar(personal, "nombre", "Ana Solis", "la consultora")
sienna = buscar(flota, "placa", "JKL-3333", "la Sienna blindada")

_, servicios = pedir("GET", "/servicios", token=h)
base_fecha = date.today() + timedelta(days=1100 + len(servicios) * 7)
fechas = [base_fecha + timedelta(days=i) for i in range(4)]

# El primer dia es el transfer de llegada; los tres siguientes, full days.
JORNADAS = [
    ("transfer", "14:20:00", 40),
    ("full_day", "08:00:00", 180),
    ("full_day", "08:00:00", 110),
    ("full_day", "08:00:00", 95),
]

_, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual", "consultor_id": ana["id"],
    "solicitante_nombre": "Karen Whitfield",
    "solicitante_correo": "kwhitfield@cliente.com",
    "solicitante_telefono": "+1 713 555 0102",
    "ejecutivo_nombre": "Mr. James Caldwell",
    "ejecutivo_correo": "jcaldwell@cliente.com",
    "ejecutivo_telefono": "+1 713 555 0148",
    "equipos": [{"jornadas": [
        {"fecha": f, "modalidad_id": M[mo]["id"],
         "hora_presentacion": hora, "km_estimados": km}
        for f, (mo, hora, km) in zip(fechas, JORNADAS)]}]}, token=h)

if not srv.get("equipos"):
    print(json.dumps(srv, indent=2, ensure_ascii=False))
    raise SystemExit(1)

equipo = srv["equipos"][0]

AGENDAS = [
    ("Arrival and transfer to hotel",
     "14:20 Meet and greet at Terminal 1, international arrivals\n"
     "15:10 Transfer to hotel, Polanco\n"
     "16:00 Check in, service ends"),
    ("Plant visit, Toluca corridor",
     "08:00 Departure from hotel\n10:00 Manufacturing plant, Lerma\n"
     "13:30 Working lunch with plant management\n"
     "16:00 Return to Mexico City\n19:30 Hotel"),
    ("Corporate agenda, Polanco and Santa Fe",
     "08:00 Departure from hotel\n09:00 Corporate offices, Polanco\n"
     "13:00 Lunch, Campos Eliseos\n15:30 Regional office, Santa Fe\n"
     "19:00 Dinner, Polanco\n20:00 Hotel"),
    ("Closing meeting and departure",
     "08:00 Departure from hotel\n09:30 Closing meeting, Paseo de la Reforma\n"
     "13:00 Lunch, Reforma\n"
     "16:10 Benito Juarez International Airport, Terminal 1\n"
     "17:00 Service ends at check-in counters"),
]

# Dias de corrido: el mismo conductor y la misma unidad los cuatro dias.
for j, agenda in zip(equipo["jornadas"], AGENDAS):
    for ruta, cuerpo_peticion, que in (
        ("asignar-personal", {"persona_id": conductor["id"], "forzar": True},
         "el conductor"),
        ("asignar-vehiculo", {"vehiculo_id": sienna["id"], "forzar": True},
         "la unidad"),
    ):
        codigo, r = pedir("POST", f"/servicios/jornadas/{j['id']}/{ruta}",
                          cuerpo_peticion, token=h)
        if codigo != 200:
            print(f"No se pudo asignar {que} el {j['fecha']}: HTTP {codigo}")
            print(json.dumps(r.get("detail", r), indent=2, ensure_ascii=False)[:400])
            raise SystemExit(1)

    if j is equipo["jornadas"][0]:
        # El meet and greet: aqui arranca el servicio.
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen", {
            "origen_lat": "19.4361", "origen_lon": "-99.0719",
            "geocerca_metros": 300,
            "origen_direccion": ("Benito Juarez International Airport, "
                                 "Terminal 1 - international arrivals, "
                                 "at the exit of the customs filter")}, token=h)
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/vuelo", {
            "vuelo_aerolinea": "United", "vuelo_numero": "UA 1518",
            "vuelo_origen": "Houston",
            "vuelo_hora": f"{fechas[0]}T13:50:00"}, token=h)
    else:
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen", {
            "origen_lat": "19.4326", "origen_lon": "-99.1962",
            "geocerca_metros": 250,
            "origen_direccion": ("Las Alcobas, Presidente Masaryk 390, "
                                 "Polanco - hotel lobby")}, token=h)

    if j is equipo["jornadas"][-1]:
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/vuelo", {
            "vuelo_aerolinea": "United", "vuelo_numero": "UA 1519",
            "vuelo_hora": f"{fechas[-1]}T19:05:00"}, token=h)

    pedir("PUT", f"/operacion/jornadas/{j['id']}/agenda",
          {"resumen": agenda[0], "puntos": agenda[1]}, token=h)

pedir("POST", "/hospedajes", {
    "servicio_id": srv["id"], "hotel_id": hoteles[0]["id"],
    "desde": fechas[0], "hasta": fechas[-1]}, token=h)

pedir("PUT", f"/servicios/{srv['id']}/senal", {"texto": "J. CALDWELL"}, token=h)

codigo, pub = pedir("POST", f"/task-sheets/servicio/{srv['id']}/publicar", {}, token=h)
if codigo != 200:
    print(json.dumps(pub, indent=2, ensure_ascii=False))
    raise SystemExit(1)

for idioma, archivo in (("en", "task_sheet5.html"), ("es", "task_sheet5_es.html")):
    codigo, hoja = pedir("GET",
                         f"/task-sheets/servicio/{srv['id']}/hoja?idioma={idioma}",
                         token=h, crudo=True)
    with open(archivo, "w") as f:
        f.write(hoja)

print(f"{srv['folio']} equipo {pub.get('equipo')} · conductor y Sienna blindada")
print(f"   {fechas[0]} al {fechas[-1]} · 1 transfer de llegada y 3 full days")
print("Ingles:  task_sheet5.html")
print("Espanol: task_sheet5_es.html")

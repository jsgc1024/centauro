#!/usr/bin/env python3
"""Tercer ejemplo: equipo de dos personas (conductor de seguridad y agente
de seguridad) con una Toyota Sienna blindada, tres dias."""
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


conductor = buscar(personal, "nombre", "Juan Ramirez", "el conductor")
agente = buscar(personal, "nombre", "Miguel Torres", "el agente")
ana = buscar(personal, "nombre", "Ana Solis", "la consultora")
sienna = buscar(flota, "placa", "JKL-3333", "la Sienna blindada")

_, servicios = pedir("GET", "/servicios", token=h)
base_fecha = date.today() + timedelta(days=700 + len(servicios) * 7)
fechas = [base_fecha + timedelta(days=i) for i in range(3)]
MODALIDADES = ["transfer", "full_day", "full_day"]

_, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual", "consultor_id": ana["id"],
    "solicitante_nombre": "Patricia Lundgren",
    "solicitante_correo": "plundgren@cliente.com",
    "solicitante_telefono": "+46 8 555 0177",
    "ejecutivo_nombre": "Ms. Ingrid Halvorsen",
    "ejecutivo_correo": "ihalvorsen@cliente.com",
    "ejecutivo_telefono": "+46 70 555 0188",
    "equipos": [{"jornadas": [
        {"fecha": f, "modalidad_id": M[mo]["id"],
         "hora_presentacion": "08:00:00", "km_estimados": 120}
        for f, mo in zip(fechas, MODALIDADES)]}]}, token=h)

if not srv.get("equipos"):
    print(json.dumps(srv, indent=2, ensure_ascii=False))
    raise SystemExit(1)

equipo = srv["equipos"][0]
agendas = [
    ("Arrival and transfer to hotel",
     "08:00 Meet and greet at Terminal 2, international arrivals\n"
     "09:30 Transfer to hotel\n10:30 Service ends"),
    ("Corporate agenda, Polanco and Santa Fe",
     "08:00 Departure from hotel\n09:30 Corporate offices, Polanco\n"
     "13:00 Working lunch, Santa Fe\n16:00 Site visit\n19:00 Return to hotel"),
    ("Meetings and departure",
     "08:00 Departure from hotel\n10:00 Closing meeting, Reforma\n"
     "14:00 Benito Juarez International Airport, Terminal 2\n"
     "15:00 Service ends"),
]

# Un conductor de seguridad y un agente de seguridad, los dos los tres dias,
# con una sola unidad blindada.
for j, agenda in zip(equipo["jornadas"], agendas):
    for ruta, cuerpo_peticion, que in (
        ("asignar-personal", {"persona_id": conductor["id"], "forzar": True},
         "el conductor"),
        ("asignar-personal", {"persona_id": agente["id"], "forzar": True},
         "el agente"),
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
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen", {
            "origen_lat": "19.4361", "origen_lon": "-99.0719",
            "geocerca_metros": 300,
            "origen_direccion": ("Benito Juarez International Airport, "
                                 "Terminal 2 - international arrivals, "
                                 "at the exit of the customs filter")}, token=h)
    else:
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen", {
            "origen_lat": "19.4326", "origen_lon": "-99.1962",
            "geocerca_metros": 250,
            "origen_direccion": ("Las Alcobas, Presidente Masaryk 390, "
                                 "Polanco - hotel lobby")}, token=h)
    # Vuelo del ejecutivo: llegada el primer dia, salida el ultimo.
    if j is equipo["jornadas"][0]:
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/vuelo",
              {"vuelo_aerolinea": "Lufthansa", "vuelo_numero": "LH 498",
             "vuelo_origen": "Frankfurt",
             "vuelo_hora": f"{fechas[0]}T08:35:00"}, token=h)
    elif j is equipo["jornadas"][-1]:
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/vuelo",
              {"vuelo_aerolinea": "Lufthansa", "vuelo_numero": "LH 497",
             "vuelo_hora": f"{fechas[-1]}T16:20:00"}, token=h)
    pedir("PUT", f"/operacion/jornadas/{j['id']}/agenda",
          {"resumen": agenda[0], "puntos": agenda[1]}, token=h)

pedir("POST", "/hospedajes", {
    "servicio_id": srv["id"], "hotel_id": hoteles[0]["id"],
    "desde": fechas[0], "hasta": fechas[-1]}, token=h)

pedir("PUT", f"/servicios/{srv['id']}/senal", {"texto": "I. HALVORSEN"}, token=h)

codigo, pub = pedir("POST", f"/task-sheets/servicio/{srv['id']}/publicar", {}, token=h)
if codigo != 200:
    print(json.dumps(pub, indent=2, ensure_ascii=False))
    raise SystemExit(1)

for idioma, archivo in (("en", "task_sheet3.html"), ("es", "task_sheet3_es.html")):
    codigo, hoja = pedir("GET",
                         f"/task-sheets/servicio/{srv['id']}/hoja?idioma={idioma}",
                         token=h, crudo=True)
    with open(archivo, "w") as f:
        f.write(hoja)

print(f"{srv['folio']} equipo {pub.get('equipo')} · conductor + agente, Sienna blindada")
print(f"   {fechas[0]} al {fechas[-1]} · 1 transfer y 2 full days")
print("Ingles:  task_sheet3.html")
print("Espanol: task_sheet3_es.html")

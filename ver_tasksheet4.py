#!/usr/bin/env python3
"""Cuarto ejemplo: un solo transfer de salida, del hotel al aeropuerto.

Es el caso mas corto que existe y el que prueba que el meet and greet
sirve igual cuando el vuelo es de salida y no de llegada."""
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


def buscar(lista, clave, valor, que):
    encontrado = next((x for x in lista if x.get(clave) == valor), None)
    if not encontrado:
        print(f"Falta {que} ({valor}) en el catalogo.")
        print("Corre:  ./reiniciar.sh    para volver a sembrar.")
        raise SystemExit(1)
    return encontrado


conductor = buscar(personal, "nombre", "Luis Mendoza", "el conductor")
ana = buscar(personal, "nombre", "Ana Solis", "la consultora")
suburban = buscar(flota, "placa", "ABC-1234", "la unidad")

_, servicios = pedir("GET", "/servicios", token=h)
dia = date.today() + timedelta(days=900 + len(servicios) * 3)

_, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual", "consultor_id": ana["id"],
    "solicitante_nombre": "Karen Whitfield",
    "solicitante_correo": "kwhitfield@cliente.com",
    "solicitante_telefono": "55 1234 5690",
    "ejecutivo_nombre": "Mr. Thomas Reed",
    "ejecutivo_correo": "treed@cliente.com",
    "ejecutivo_telefono": "+1 646 555 0123",
    "equipos": [{"jornadas": [
        {"fecha": dia, "modalidad_id": M["transfer"]["id"],
         "hora_presentacion": "05:45:00", "km_estimados": 35}]}]}, token=h)

if not srv.get("equipos"):
    print(json.dumps(srv, indent=2, ensure_ascii=False))
    raise SystemExit(1)

j = srv["equipos"][0]["jornadas"][0]

for ruta, cuerpo_peticion, que in (
    ("asignar-personal", {"persona_id": conductor["id"], "forzar": True},
     "el conductor"),
    ("asignar-vehiculo", {"vehiculo_id": suburban["id"], "forzar": True},
     "la unidad"),
):
    codigo, r = pedir("POST", f"/servicios/jornadas/{j['id']}/{ruta}",
                      cuerpo_peticion, token=h)
    if codigo != 200:
        print(f"No se pudo asignar {que}: HTTP {codigo}")
        print(json.dumps(r.get("detail", r), indent=2, ensure_ascii=False)[:400])
        raise SystemExit(1)

# El meet and greet es el lobby del hotel: aqui arranca el servicio.
pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen", {
    "origen_lat": "19.4250", "origen_lon": "-99.1742", "geocerca_metros": 250,
    "origen_direccion": ("The St. Regis, Paseo de la Reforma 439, CDMX "
                         "- hotel lobby")}, token=h)

# El vuelo es de SALIDA: hay que decirlo, en un servicio de un solo dia
# el sistema no lo puede deducir.
pedir("PATCH", f"/operacion/jornadas/{j['id']}/vuelo", {
    "vuelo_aerolinea": "Delta", "vuelo_numero": "DL 594",
    "vuelo_tipo": "salida",
    "vuelo_hora": f"{dia}T08:40:00"}, token=h)

pedir("PUT", f"/operacion/jornadas/{j['id']}/agenda", {
    "resumen": "Transfer to the airport",
    "puntos": ("05:45 Pickup at hotel lobby\n"
               "06:30 Benito Juarez International Airport, Terminal 2\n"
               "06:45 Service ends at check-in counters")}, token=h)

pedir("PUT", f"/servicios/{srv['id']}/senal", {"texto": "T. REED"}, token=h)

codigo, pub = pedir("POST", f"/task-sheets/servicio/{srv['id']}/publicar", {}, token=h)
if codigo != 200:
    print(json.dumps(pub, indent=2, ensure_ascii=False))
    raise SystemExit(1)

for idioma, archivo in (("en", "task_sheet4.html"), ("es", "task_sheet4_es.html")):
    codigo, hoja = pedir("GET",
                         f"/task-sheets/servicio/{srv['id']}/hoja?idioma={idioma}",
                         token=h, crudo=True)
    with open(archivo, "w") as f:
        f.write(hoja)

print(f"{srv['folio']} equipo {pub.get('equipo')} · transfer de salida")
print(f"   {dia} · hotel al aeropuerto, vuelo DL 594 a las 08:40")
print("Ingles:  task_sheet4.html")
print("Espanol: task_sheet4_es.html")

#!/usr/bin/env python3
"""Carga servicios de prueba con los casos que ya soporta el sistema.

    python3 servicios_prueba.py

Deja tres:
  · Un transfer sencillo desde el aeropuerto, un solo equipo.
  · Un proyecto de dos ciudades: Alfa en Ciudad de Mexico y Beta en
    Monterrey, con el mismo ejecutivo principal.
  · Un full day de tres dias con agenda cargada, para probar paradas.

Se puede correr las veces que haga falta: cada corrida crea servicios
nuevos, no toca los que ya estan.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "http://localhost:8000"
HOY = date.today()


def pedir(metodo, ruta, cuerpo=None, token=None):
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    datos = json.dumps(cuerpo, default=str).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo, headers=cab)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or "null")
        except json.JSONDecodeError:
            return e.code, bruto.decode(errors="replace")[:300]


def entrar(correo, contrasena="centauro2026"):
    d = urllib.parse.urlencode({"username": correo, "password": contrasena}).encode()
    req = urllib.request.Request(
        BASE + "/auth/token", data=d, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]


h = entrar("ana.solis@centauro.lat")

_, clientes = pedir("GET", "/catalogos/clientes", token=h)
_, paises = pedir("GET", "/catalogos/paises", token=h)
_, plazas = pedir("GET", "/catalogos/plazas?todas=true", token=h)
_, modalidades = pedir("GET", "/catalogos/modalidades", token=h)

mx = next(p for p in paises if p["codigo"] in ("MX", "MEX"))
por_ciudad = {p["nombre"]: p for p in plazas if p["pais_id"] == mx["id"]}
mods = {m["codigo"]: m for m in modalidades if m["pais_id"] == mx["id"]}
cliente_id = clientes[0]["id"]


def dia(cuando, modalidad, **extra):
    j = {"fecha": str(cuando), "modalidad_id": mods[modalidad]["id"]}
    j.update(extra)
    return j


AEROPUERTO = {
    "origen_direccion": "Aeropuerto Internacional Benito Juarez, Terminal 2 - "
                        "salida de aduana",
    "origen_lat": "19.4353", "origen_lon": "-99.0719",
    "geocerca_metros": 1000,
}
HOTEL = {
    "origen_direccion": "Las Alcobas, Presidente Masaryk 390 - lobby",
    "origen_lat": "19.4325", "origen_lon": "-99.1975",
    "geocerca_metros": 1000,
}

SERVICIOS = [
    ("Transfer desde el aeropuerto", {
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "solicitante_correo": "kwhitfield@cliente.com",
        "solicitante_telefono": "+1 713 555 0102",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "plaza": "Ciudad de Mexico",
        "equipos": [{"jornadas": [
            dia(HOY + timedelta(days=3), "transfer", hora_presentacion="13:05:00",
                vuelo_aerolinea="United", vuelo_numero="UA 1518",
                vuelo_origen="Houston", vuelo_tipo="llegada",
                vuelo_hora=f"{HOY + timedelta(days=3)}T13:50:00", **AEROPUERTO),
        ]}],
    }),
    ("Proyecto de dos ciudades", {
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "solicitante_correo": "kwhitfield@cliente.com",
        "ejecutivo_nombre": "Helen", "ejecutivo_apellidos": "Voss",
        "plaza": "Ciudad de Mexico",
        "equipos": [
            {"ejecutivo_nombre": "Helen", "ejecutivo_apellidos": "Voss",
             "jornadas": [
                 dia(HOY + timedelta(days=7), "transfer",
                     hora_presentacion="09:15:00", **AEROPUERTO),
                 dia(HOY + timedelta(days=8), "full_day", **HOTEL),
             ]},
            {"ciudad": "Monterrey",
             "ejecutivo_nombre": "Helen", "ejecutivo_apellidos": "Voss",
             "jornadas": [
                 dia(HOY + timedelta(days=9), "full_day",
                     hora_presentacion="08:00:00",
                     origen_direccion="Hotel Habita MTY, San Pedro Garza Garcia",
                     origen_lat="25.6540", origen_lon="-100.3620",
                     geocerca_metros=1000),
                 dia(HOY + timedelta(days=10), "transfer"),
             ]},
        ],
    }),
    ("Tres dias con agenda", {
        "solicitante_nombre": "Patricia", "solicitante_apellidos": "Lundgren",
        "solicitante_correo": "plundgren@cliente.com",
        "ejecutivo_nombre": "Ingrid", "ejecutivo_apellidos": "Halvorsen",
        "plaza": "Ciudad de Mexico",
        "equipos": [{"jornadas": [
            dia(HOY + timedelta(days=14), "transfer",
                hora_presentacion="07:30:00", **AEROPUERTO),
            dia(HOY + timedelta(days=15), "full_day", **HOTEL),
            dia(HOY + timedelta(days=16), "full_day", **HOTEL),
        ]}],
    }),
]

# Agenda del segundo dia del tercer servicio, para probar las paradas.
PARADAS = [
    {"hora": "09:00:00", "lugar": "Oficinas corporativas",
     "direccion": "Paseo de la Reforma 250, piso 12"},
    {"hora": "13:30:00", "lugar": "Comida en San Angel Inn",
     "direccion": "Diego Rivera 50, San Angel"},
    {"hora": "17:00:00", "lugar": "Regreso al hotel"},
    {"lugar": "Posible visita a planta", "notas": "Sin confirmar con el cliente"},
]

creados = []
for titulo, datos in SERVICIOS:
    ciudad = por_ciudad.get(datos.pop("plaza"))
    equipos = []
    for eq in datos.pop("equipos"):
        nombre_ciudad = eq.pop("ciudad", None)
        if nombre_ciudad:
            otra = por_ciudad.get(nombre_ciudad)
            if otra:
                eq["plaza_id"] = otra["id"]
            else:
                print(f"   (no hay {nombre_ciudad} en el catalogo; "
                      f"el equipo se queda en la ciudad del servicio)")
        equipos.append(eq)

    codigo, r = pedir("POST", "/servicios", {
        "cliente_id": cliente_id, "pais_id": mx["id"],
        "plaza_id": ciudad["id"], "tipo": "eventual",
        "equipos": equipos, **datos}, token=h)
    if codigo != 201:
        print(f"   no se pudo crear '{titulo}': {r}")
        continue
    print(f"   {r['folio']}  {titulo:<28} {r['estatus']}")
    creados.append(r)

# Al ultimo se le carga la agenda del segundo dia.
if creados:
    ultimo = creados[-1]
    jornadas = sorted(ultimo["equipos"][0]["jornadas"], key=lambda j: j["fecha"])
    if len(jornadas) > 1:
        segundo = jornadas[1]["id"]
        pedir("PUT", f"/operacion/jornadas/{segundo}/agenda",
              {"resumen": "Reuniones corporativas en Reforma"}, token=h)
        for parada in PARADAS:
            pedir("POST", f"/operacion/jornadas/{segundo}/agenda/paradas",
                  parada, token=h)
        print(f"\n   Agenda cargada en el dia {jornadas[1]['fecha']} "
              f"de {ultimo['folio']}")

print(f"\nListos {len(creados)} servicios. Recarga la consola.")

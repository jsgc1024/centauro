#!/usr/bin/env python3
"""Da de alta tres personas de seguridad de prueba.

Sirve para tener con que probar la asignacion de recursos: dos conductores
y un agente, en dos ciudades distintas, para ver el bloqueo duro cuando se
empalman y la alerta de "no hay recurso local" cuando no los hay.

Se puede correr las veces que haga falta: a quien ya existe no lo duplica,
solo le completa lo que le falte.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"

# Nombre, correo, perfil, ciudad, telefono sin clave de pais.
GENTE = [
    ("Ernesto Vidal", "ernesto.vidal@centauro.lat",
     "conductor_seguridad", "Ciudad de Mexico", "55 3311 7742"),
    ("Marco Zepeda", "marco.zepeda@centauro.lat",
     "conductor_seguridad", "Monterrey", "81 2244 9130"),
    ("Daniela Ibarra", "daniela.ibarra@centauro.lat",
     "agente_seguridad", "Ciudad de Mexico", "55 4088 2651"),
]


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


h = entrar("admin@centauro.lat")

_, perfiles = pedir("GET", "/catalogos/perfiles", token=h)
_, plazas = pedir("GET", "/catalogos/plazas", token=h)
_, personal = pedir("GET", "/catalogos/personal", token=h)

por_codigo = {p["codigo"]: p for p in perfiles}
por_ciudad = {p["nombre"]: p for p in plazas}
ya_estan = {p["correo"] for p in personal}

nuevos = []
for nombre, correo, perfil, ciudad, telefono in GENTE:
    if correo in ya_estan:
        print(f"   ya estaba: {nombre}")
        nuevos.append((correo, telefono))
        continue

    lugar = por_ciudad.get(ciudad) or por_ciudad.get("Ciudad de Mexico")
    if not lugar or perfil not in por_codigo:
        print(f"   falta el catalogo para {nombre} ({perfil}, {ciudad})")
        continue

    codigo, r = pedir("POST", "/catalogos/personal", {
        "nombre": nombre, "correo": correo,
        "perfil_id": por_codigo[perfil]["id"], "plaza_id": lugar["id"],
    }, token=h)
    if codigo != 201:
        print(f"   no se pudo dar de alta a {nombre}: {r}")
        continue
    print(f"   alta: {nombre} · {por_codigo[perfil]['nombre']} · {lugar['nombre']}")
    nuevos.append((correo, telefono))

# El telefono viene de Odoo, no se captura en el alta del catalogo. Se
# manda por la misma puerta por la que entrara el dia que se conecte, y
# de paso queda con su clave de pais, como todos.
if nuevos:
    codigo, r = pedir("POST", "/odoo/personal",
                      [{"correo": correo, "telefono": telefono}
                       for correo, telefono in nuevos], token=h)
    print(f"\nTelefonos desde Odoo: {r if codigo == 200 else codigo}")

_, personal = pedir("GET", "/catalogos/personal", token=h)
print(f"\nPersonal en el catalogo: {len(personal)}")
for p in personal:
    perfil = next((x["nombre"] for x in perfiles if x["id"] == p["perfil_id"]), "—")
    ciudad = next((x["nombre"] for x in plazas if x["id"] == p["plaza_id"]), "—")
    print(f"   {p['nombre']:<20} {perfil:<24} {ciudad:<18} {p.get('telefono') or ''}")

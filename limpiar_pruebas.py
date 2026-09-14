#!/usr/bin/env python3
"""Barre lo que las pruebas dejaron en la base de desarrollo.

Durante un tiempo la bateria corrio contra la base de desarrollo en vez
de la suya, y sembro catalogos de mentira: clientes "Otro cliente",
ciudades con nombre generado. Eso ya esta corregido en tests/conftest.py
—ahora se detiene sola si no apunta a centauro_test— pero lo que quedo
hay que recogerlo.

No borra: desactiva. Un cliente con servicios encima no se puede borrar
sin llevarselos, y esos servicios son historia.

    python3 limpiar_pruebas.py
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"

# Lo que dejaron las pruebas, reconocible por su nombre.
CLIENTES = re.compile(r"^Otro cliente$")
CIUDADES = re.compile(r"^(Ciudad [0-9a-f]{8}|Merida [0-9a-f]{6}|Plaza Duplicada"
                      r"|Torreon|Tampico|Culiacan)( [0-9a-f]{6})?$")


def pedir(metodo, ruta, cuerpo=None, token=None):
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    datos = json.dumps(cuerpo, default=str).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo, headers=cab)
    try:
        with urllib.request.urlopen(req) as r:
            crudo = r.read()
            return r.status, (json.loads(crudo) if crudo else None)
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or "null")
        except json.JSONDecodeError:
            return e.code, bruto.decode(errors="replace")[:200]


def entrar(correo, contrasena="centauro2026"):
    d = urllib.parse.urlencode({"username": correo, "password": contrasena}).encode()
    req = urllib.request.Request(
        BASE + "/auth/token", data=d, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]


h = entrar("admin@centauro.lat")

for ruta, patron, que in (("/catalogos/clientes", CLIENTES, "clientes"),
                          ("/catalogos/plazas", CIUDADES, "ciudades")):
    codigo, lista = pedir("GET", ruta + "?todas=true", token=h)
    if codigo != 200:
        codigo, lista = pedir("GET", ruta, token=h)
    if codigo != 200:
        print(f"   no pude leer {que}: {lista}")
        continue

    basura = [x for x in lista if patron.match(x.get("nombre", ""))]
    hechos = 0
    for x in basura:
        codigo, r = pedir("DELETE", f"{ruta}/{x['id']}", token=h)
        if codigo == 204:
            hechos += 1
        else:
            print(f"   {x['nombre']}: {codigo} {r}")
    print(f"   {que}: {hechos} de {len(basura)} desactivados")

print("\nListo. Recarga la consola.")

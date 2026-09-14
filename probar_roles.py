#!/usr/bin/env python3
"""Permisos por rol: quien puede hacer que."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE = "http://localhost:8000"


def pedir(metodo, ruta, cuerpo=None, token=None):
    cabeceras = {"Content-Type": "application/json"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    datos = json.dumps(cuerpo, default=str).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo, headers=cabeceras)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


def entrar(correo, contrasena="centauro2026"):
    datos = urllib.parse.urlencode({"username": correo, "password": contrasena}).encode()
    req = urllib.request.Request(BASE + "/auth/token", data=datos, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())["access_token"]
    except urllib.error.HTTPError as e:
        print("Error al entrar:", e.read())
        raise


def titulo(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


def resultado(esperado, codigo, etiqueta):
    marca = "OK " if codigo == esperado else "MAL"
    print(f"   [{marca}] {etiqueta:<52} HTTP {codigo} (esperado {esperado})")


pedir("POST", "/sistema/sembrar-catalogos")

titulo("1. Inicio de sesion por rol")
tokens = {}
for etiqueta, correo in [("admin", "admin@centauro.lat"),
                         ("consultor", "ana.solis@centauro.lat"),
                         ("central", "central@centauro.lat"),
                         ("finanzas", "finanzas@centauro.lat"),
                         ("dirgeneral", "direccion@centauro.lat"),
                         ("diroperaciones", "operaciones@centauro.lat"),
                         ("juan", "juan.ramirez@centauro.lat"),
                         ("luis", "luis.mendoza@centauro.lat")]:
    tokens[etiqueta] = entrar(correo)
    c, yo = pedir("GET", "/auth/yo", token=tokens[etiqueta])
    print(f"   {yo['nombre']:<18} rol: {yo['rol']}")

titulo("2. Sin sesion no se entra")
c, r = pedir("GET", "/servicios")
resultado(401, c, "listar servicios sin token")
c, r = pedir("POST", "/auth/token", {"username": "juan.ramirez@centauro.lat",
                                     "password": "equivocada"})
print(f"   [--] contrasena incorrecta                            HTTP {c}")

titulo("3. Montaje del escenario (lo hace el consultor)")
_, paises = pedir("GET", "/catalogos/paises", token=tokens["consultor"])
mx = next(p for p in paises if p["codigo"] == "MX")
_, plazas = pedir("GET", "/catalogos/plazas", token=tokens["consultor"])
cdmx = next(p for p in plazas if p["nombre"] == "Ciudad de Mexico")
_, mods = pedir("GET", "/catalogos/modalidades", token=tokens["consultor"])
M = {x["codigo"]: x for x in mods if x["pais_id"] == mx["id"]}
_, clientes = pedir("GET", "/catalogos/clientes", token=tokens["consultor"])
_, personal = pedir("GET", "/catalogos/personal", token=tokens["consultor"])
juan = next(p for p in personal if p["nombre"] == "Juan Ramirez")

presentacion = (datetime.now() + timedelta(minutes=30)).replace(second=0, microsecond=0)
c, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual", "solicitante_correo": "patricia@cliente.com",
    "ejecutivo_correo": "jcarter@cliente.com",
    "equipos": [{"clave": "EQ-1", "jornadas": [
        {"fecha": presentacion.date(), "modalidad_id": M["full_day"]["id"],
         "hora_presentacion": presentacion.strftime("%H:%M:%S")}]}]},
    token=tokens["consultor"])
j = srv["equipos"][0]["jornadas"][0]
pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-personal",
      {"persona_id": juan["id"], "forzar": True}, token=tokens["consultor"])
pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen",
      {"origen_lat": "19.4270", "origen_lon": "-99.1677", "geocerca_metros": 250},
      token=tokens["consultor"])
print(f"   {srv['folio']} creado, Juan asignado a la jornada #{j['id']}")

titulo("4. Cada quien en su carril")
c, r = pedir("POST", "/servicios", {"cliente_id": clientes[0]["id"], "pais_id": mx["id"],
                                    "plaza_id": cdmx["id"], "tipo": "eventual",
                                    "equipos": []}, token=tokens["juan"])
resultado(403, c, "conductor intenta crear un servicio")

c, r = pedir("POST", "/viaticos/transferencias/barrido", token=tokens["consultor"])
resultado(403, c, "consultor intenta correr el barrido de finanzas")

c, r = pedir("POST", "/viaticos/transferencias/barrido", token=tokens["finanzas"])
resultado(200, c, "finanzas corre el barrido")

c, r = pedir("POST", "/catalogos/plazas", {"pais_id": mx["id"], "nombre": "Cancun"},
             token=tokens["consultor"])
resultado(403, c, "consultor intenta dar de alta una plaza")

c, r = pedir("POST", "/catalogos/plazas", {"pais_id": mx["id"], "nombre": "Cancun"},
             token=tokens["admin"])
resultado(201, c, "admin da de alta la plaza")

titulo("5. El conductor solo actua sobre sus jornadas")
c, r = pedir("POST", f"/operacion/jornadas/{j['id']}/confirmar-recurso",
             token=tokens["juan"])
resultado(200, c, "Juan confirma su disponibilidad")

c, r = pedir("POST", f"/operacion/jornadas/{j['id']}/hitos",
             {"tipo": "llegada_origen", "lat": "19.4272", "lon": "-99.1679",
              "marcado_en": presentacion - timedelta(minutes=5)}, token=tokens["luis"])
resultado(403, c, "Luis intenta marcar en la jornada de Juan")

c, r = pedir("POST", f"/operacion/jornadas/{j['id']}/hitos",
             {"tipo": "llegada_origen", "lat": "19.4272", "lon": "-99.1679",
              "marcado_en": presentacion - timedelta(minutes=5)}, token=tokens["juan"])
resultado(200, c, "Juan marca su llegada")
hito = r.get("hito_id")

titulo("6. EL PUNTO DEL EJERCICIO: nadie corrige su propia marca")
ajuste = {"nuevo_momento": presentacion.isoformat(),
          "justificacion": "Ajuste solicitado por el propio conductor via telefono."}
c, r = pedir("POST", f"/operacion/hitos/{hito}/ajustar", ajuste, token=tokens["juan"])
resultado(403, c, "Juan intenta ajustar su propia marca")
print("      ", json.dumps(r.get("detail", r), ensure_ascii=False))

c, r = pedir("POST", f"/operacion/hitos/{hito}/ajustar", ajuste, token=tokens["consultor"])
resultado(403, c, "el consultor intenta ajustar la marca")

c, r = pedir("POST", f"/operacion/hitos/{hito}/ajustar", ajuste, token=tokens["central"])
resultado(200, c, "la central ajusta la marca")

titulo("7. Alcance de la direccion general")
c, r = pedir("GET", "/servicios", token=tokens["dirgeneral"])
resultado(200, c, "direccion general consulta servicios")
c, r = pedir("POST", "/viaticos/transferencias/barrido", token=tokens["dirgeneral"])
resultado(200, c, "direccion general alcanza lo de finanzas")
c, r = pedir("POST", "/catalogos/plazas", {"pais_id": mx["id"], "nombre": "Merida"},
             token=tokens["dirgeneral"])
resultado(403, c, "direccion general intenta tocar catalogos")
c, r = pedir("POST", f"/operacion/jornadas/{j['id']}/hitos",
             {"tipo": "standby", "lat": "19.4272", "lon": "-99.1679"},
             token=tokens["dirgeneral"])
resultado(403, c, "direccion general intenta marcar un hito de campo")

titulo("8. El ajuste queda firmado con quien lo hizo")
c, bit = pedir("GET", f"/operacion/jornadas/{j['id']}/bitacora", token=tokens["central"])
for h in bit["hitos"]:
    print(f"   {h['tipo']}  marcado por {h['marcado_por']}")
    if h["ajuste"]:
        print(f"      ajustado por: {h['ajuste']['ajustado_por']}")
        print(f"      hora original: {h['ajuste']['original']}")
        print(f"      justificacion: {h['ajuste']['justificacion']}")
print()

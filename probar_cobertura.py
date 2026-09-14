#!/usr/bin/env python3
"""Un consultor cubre la cartera de otro: se permite, pero queda registrado
y se avisa al titular."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE = "http://localhost:8000"


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
        return e.code, json.loads(e.read() or "null")


def entrar(correo, contrasena="centauro2026"):
    datos = urllib.parse.urlencode({"username": correo, "password": contrasena}).encode()
    req = urllib.request.Request(BASE + "/auth/token", data=datos, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]


def titulo(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


pedir("POST", "/sistema/sembrar-catalogos")

ana = entrar("ana.solis@centauro.lat")        # consultora titular
beatriz = entrar("beatriz.roman@centauro.lat")  # cubre por ausencia

_, paises = pedir("GET", "/catalogos/paises", token=ana)
mx = next(p for p in paises if p["codigo"] == "MX")
_, plazas = pedir("GET", "/catalogos/plazas", token=ana)
cdmx = next(p for p in plazas if p["nombre"] == "Ciudad de Mexico")
_, mods = pedir("GET", "/catalogos/modalidades", token=ana)
M = {x["codigo"]: x for x in mods if x["pais_id"] == mx["id"]}
_, clientes = pedir("GET", "/catalogos/clientes", token=ana)
_, personal = pedir("GET", "/catalogos/personal", token=ana)
juan = next(p for p in personal if p["nombre"] == "Juan Ramirez")
ana_p = next(p for p in personal if p["nombre"] == "Ana Solis")
_, flota = pedir("GET", "/catalogos/vehiculos", token=ana)

fecha = (datetime.now() + timedelta(days=3)).date()

titulo("1. Ana da de alta un servicio de su cartera")
c, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual", "consultor_id": ana_p["id"],
    "equipos": [{"clave": "EQ-1", "jornadas": [
        {"fecha": fecha, "modalidad_id": M["full_day"]["id"],
         "hora_presentacion": "08:00:00", "km_estimados": 90}]}]}, token=ana)
j = srv["equipos"][0]["jornadas"][0]
print(f"   {srv['folio']}  consultora titular: Ana Solis")

titulo("2. Ana se enferma. Beatriz entra a cubrir")
c, r = pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-personal",
             {"persona_id": juan["id"], "forzar": True}, token=beatriz)
print(f"   Beatriz asigna personal        -> HTTP {c}")
c, r = pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-vehiculo",
             {"vehiculo_id": flota[0]["id"], "forzar": True}, token=beatriz)
print(f"   Beatriz asigna vehiculo        -> HTTP {c}")

c, prop = pedir("GET", f"/viaticos/calcular?jornada_id={j['id']}&persona_id={juan['id']}",
                token=beatriz)
conceptos = [{"concepto": x["concepto"], "monto": str(x["monto"]),
              "descripcion": x["descripcion"], "origen": x["origen"]}
             for x in prop["conceptos"]]
c, v = pedir("POST", "/viaticos/asignar",
             {"jornada_id": j["id"], "persona_id": juan["id"], "conceptos": conceptos},
             token=beatriz)
print(f"   Beatriz asigna viaticos        -> HTTP {c}  total {v.get('monto_total')}")

titulo("3. Bitacora del servicio")
c, aud = pedir("GET", f"/servicios/{srv['id']}/auditoria", token=ana)
print(f"   Titular: {aud['consultor_titular']}")
print(f"   Movimientos en cobertura: {aud['movimientos_en_cobertura']}")
for mv in aud["movimientos"]:
    marca = "COBERTURA" if mv["en_cobertura"] else "titular  "
    print(f"   [{marca}] {mv['quien']:<16} {mv['accion']:<24} {mv['detalle']}")

titulo("4. Avisos que le llegaron a Ana")
c, bit = pedir("GET", f"/operacion/jornadas/{j['id']}/bitacora", token=ana)
for n in bit["notificaciones"]:
    if n["para"] == "consultor":
        print(f"   Para {n['correo']}: {n['asunto']}")
print()

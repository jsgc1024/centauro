#!/usr/bin/env python3
"""Full day nocturno: mismo dia de presentacion = bloqueo;
cruce de medianoche = solo alerta forzable."""
import json
import urllib.error
import urllib.request

BASE = "http://localhost:8000"


def pedir(metodo, ruta, cuerpo=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


_, paises = pedir("GET", "/catalogos/paises")
mx = next(p for p in paises if p["codigo"] == "MX")
_, plazas = pedir("GET", "/catalogos/plazas")
cdmx = next(p for p in plazas if p["nombre"] == "Ciudad de Mexico")
_, mods = pedir("GET", "/catalogos/modalidades")
M = {m["codigo"]: m for m in mods if m["pais_id"] == mx["id"]}
_, clientes = pedir("GET", "/catalogos/clientes")
_, personal = pedir("GET", "/catalogos/personal")
luis = next(p for p in personal if p["nombre"] == "Luis Mendoza")


def crear(fecha, modalidad, hora):
    _, srv = pedir("POST", "/servicios", {
        "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
        "tipo": "eventual",
        "equipos": [{"clave": "EQ-1", "jornadas": [
            {"fecha": fecha, "modalidad_id": M[modalidad]["id"],
             "hora_presentacion": hora}]}]})
    return srv["equipos"][0]["jornadas"][0]


def asignar(jornada, forzar=False):
    return pedir("POST", f"/servicios/jornadas/{jornada['id']}/asignar-personal",
                 {"persona_id": luis["id"], "forzar": forzar})


def motivos(r):
    d = r.get("detail", r)
    if isinstance(d, dict) and "alertas" in d:
        return [a["motivo"] for a in d["alertas"]]
    return d


print("=" * 68)
print("A. Full day nocturno 10-nov 18:00 -> 11-nov 06:00")
j1 = crear("2026-11-10", "full_day", "18:00:00")
print(f"   {j1['inicio_programado']} -> {j1['fin_programado']}")
c, r = asignar(j1)
print(f"   Asignar a Luis -> HTTP {c}  (esperado 200)")

print("\n" + "=" * 68)
print("B. Transfer el 11-nov 10:00  (dia siguiente, se cobra aparte)")
j2 = crear("2026-11-11", "transfer", "10:00:00")
c, r = asignar(j2)
print(f"   HTTP {c}  (esperado 409 de RIESGO, no bloqueo)")
for m_ in motivos(r):
    print(f"   -> {m_}")
c, r = asignar(j2, forzar=True)
print(f"   Con forzar=true -> HTTP {c}  (esperado 200)")

print("\n" + "=" * 68)
print("C. Transfer el 10-nov 08:00  (mismo dia de presentacion del full day)")
j3 = crear("2026-11-10", "transfer", "08:00:00")
c, r = asignar(j3)
print(f"   HTTP {c}  (esperado 409 BLOQUEO)")
for m_ in motivos(r):
    print(f"   -> {m_}")
c, r = asignar(j3, forzar=True)
print(f"   Con forzar=true -> HTTP {c}  (esperado 409: no se puede forzar)")
print()

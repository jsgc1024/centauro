#!/usr/bin/env python3
"""Verifica que un full day bloquee el dia completo del recurso."""
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
mods_mx = {m["codigo"]: m for m in mods if m["pais_id"] == mx["id"]}
_, clientes = pedir("GET", "/catalogos/clientes")
_, personal = pedir("GET", "/catalogos/personal")
juan = next(p for p in personal if p["nombre"] == "Juan Ramirez")

print("Juan Ramirez ya trae transfers asignados el 2026-10-05.\n")

# Full day el mismo dia 5, a una hora que NO empalma con 09-12 ni 13-16
cuerpo = {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual",
    "equipos": [{"clave": "EQ-1", "jornadas": [
        {"fecha": "2026-10-05", "modalidad_id": mods_mx["full_day"]["id"],
         "hora_presentacion": "18:00:00"}]}],
}
_, srv = pedir("POST", "/servicios", cuerpo)
jornada = srv["equipos"][0]["jornadas"][0]
print(f"Nuevo full day {srv['folio']}: "
      f"{jornada['inicio_programado'][11:16]} - {jornada['fin_programado'][11:16]}")

codigo, r = pedir("POST", f"/servicios/jornadas/{jornada['id']}/asignar-personal",
                  {"persona_id": juan["id"]})
print(f"\nAsignar a Juan -> HTTP {codigo}   (esperado 409 BLOQUEO)")
print(json.dumps(r, indent=2, ensure_ascii=False))

codigo, r = pedir("POST", f"/servicios/jornadas/{jornada['id']}/asignar-personal",
                  {"persona_id": juan["id"], "forzar": True})
print(f"\nIntento con forzar=true -> HTTP {codigo}   "
      f"(esperado 409: un bloqueo duro NO se puede forzar)")

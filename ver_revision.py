#!/usr/bin/env python3
"""Muestra la revision del ultimo servicio, para ver que lo esta frenando."""
import json
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"

d = urllib.parse.urlencode({"username": "ana.solis@centauro.lat",
                            "password": "centauro2026"}).encode()
req = urllib.request.Request(BASE + "/auth/token", data=d, method="POST",
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
token = json.loads(urllib.request.urlopen(req).read())["access_token"]


def get(ruta):
    r = urllib.request.Request(BASE + ruta,
                               headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(r).read())


servicios = get("/servicios")
ultimo = servicios[0]
print(f"Servicio {ultimo['folio']} (id {ultimo['id']})\n")

rev = get(f"/cierre/servicio/{ultimo['id']}/revision")
print(f"Listo para finanzas: {rev['listo_para_finanzas']}")
print(f"{rev['resumen']}\n")
for o in rev["observaciones"]:
    print(f"[{o['nivel']}] {o['asunto']}")
    print(f"   {o['mensaje']}")
    print(f"   -> {o['accion']}\n")

comp = rev["comparativo"]
print(f"Cotizado {comp['cotizacion']['total']}  "
      f"Ejecutado {comp['ejecutado']['total']}  "
      f"Horas extra {comp['ejecutado']['horas_extra']}")

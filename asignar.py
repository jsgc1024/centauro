#!/usr/bin/env python3
"""Asigna conductor y unidad a un servicio, para seguir probando.

    python3 asignar.py            al servicio EP-0002
    python3 asignar.py EP-0005    a otro

Toma el mismo conductor y la misma unidad para todos los dias, que es la
regla cuando los dias son de corrido. Si el motor de disponibilidad marca
bloqueo duro lo dice y se detiene; si solo marca riesgo, lo acepta, que es
lo que hace el consultor cuando decide.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"
FOLIO = sys.argv[1] if len(sys.argv) > 1 else "EP-0002"


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

_, servicios = pedir("GET", "/servicios", token=h)
servicio = next((s for s in servicios if s["folio"] == FOLIO), None)
if not servicio:
    print(f"No existe el servicio {FOLIO}. Los que hay:")
    for s in servicios[:12]:
        print(f"   {s['folio']}  {s['estatus']}")
    raise SystemExit(1)

_, perfiles = pedir("GET", "/catalogos/perfiles", token=h)
_, plazas = pedir("GET", "/catalogos/plazas", token=h)
_, personal = pedir("GET", "/catalogos/personal", token=h)
_, flota = pedir("GET", "/catalogos/vehiculos", token=h)

ciudad = next((p["nombre"] for p in plazas if p["id"] == servicio["plaza_id"]), "—")
conductor_id = next((p["id"] for p in perfiles
                     if p["codigo"] == "conductor_seguridad"), None)

# Primero de la ciudad del servicio; si no hay, cualquiera disponible, que
# es justo el caso de "no hay recurso local" y se resuelve trasladando.
def de_la_ciudad(lista, **filtros):
    def cumple(x, locales):
        if locales and x["plaza_id"] != servicio["plaza_id"]:
            return False
        return all(x.get(k) == v for k, v in filtros.items()) and x.get("activo", True)

    return (next((x for x in lista if cumple(x, True)), None)
            or next((x for x in lista if cumple(x, False)), None))


conductor = de_la_ciudad(personal, perfil_id=conductor_id, es_freelance=False)
unidad = de_la_ciudad(flota)

if not conductor or not unidad:
    print("Falta personal o flota en el catalogo.")
    raise SystemExit(1)

print(f"{FOLIO} · {ciudad} · {servicio['estatus']}")
print(f"   conductor: {conductor['nombre']}")
print(f"   unidad:    {unidad['placa']}\n")

for equipo in servicio["equipos"]:
    for jornada in equipo["jornadas"]:
        for ruta, cuerpo, que in (
            ("asignar-personal", {"persona_id": conductor["id"], "forzar": True},
             conductor["nombre"]),
            ("asignar-vehiculo", {"vehiculo_id": unidad["id"], "forzar": True},
             unidad["placa"]),
        ):
            codigo, r = pedir("POST",
                              f"/servicios/jornadas/{jornada['id']}/{ruta}",
                              cuerpo, token=h)
            if codigo == 409:
                detalle = r.get("detail", r)
                print(f"   {jornada['fecha']}  bloqueo: "
                      f"{detalle.get('mensaje') if isinstance(detalle, dict) else detalle}")
                raise SystemExit(1)
            if codigo != 200:
                print(f"   {jornada['fecha']}  error {codigo}: {r}")
                raise SystemExit(1)

            alertas = r.get("alertas_aceptadas") or []
            aviso = f"  (riesgo aceptado: {len(alertas)})" if alertas else ""
            print(f"   {jornada['fecha']}  {que}{aviso}")

        faltan = r.get("faltantes_de_recursos")
        if faltan is not None and not faltan:
            pass

_, servicio = pedir("GET", f"/servicios/{servicio['id']}", token=h)
_, estado = pedir("GET", f"/servicios/{servicio['id']}/programacion", token=h)
print(f"\n{servicio['folio']} quedo en: {servicio['estatus']}")
if estado.get("faltantes_de_recursos"):
    print("   falta todavia:")
    for f in estado["faltantes_de_recursos"]:
        print("     ", f)

#!/usr/bin/env python3
"""Cotizacion, ejecucion con desviacion, comparativo, revision y rentabilidad."""
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
    def leer(datos):
        try:
            return json.loads(datos or "null")
        except json.JSONDecodeError:
            return {"respuesta_no_json": (datos or b"").decode(errors="replace")[:400]}

    try:
        with urllib.request.urlopen(req) as r:
            return r.status, leer(r.read())
    except urllib.error.HTTPError as e:
        return e.code, leer(e.read())


def entrar(correo, contrasena="centauro2026"):
    d = urllib.parse.urlencode({"username": correo, "password": contrasena}).encode()
    req = urllib.request.Request(BASE + "/auth/token", data=d, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]


def titulo(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


pedir("POST", "/sistema/sembrar-catalogos")
ana = entrar("ana.solis@centauro.lat")
central = entrar("central@centauro.lat")
finanzas = entrar("finanzas@centauro.lat")
juan_t = entrar("juan.ramirez@centauro.lat")

_, paises = pedir("GET", "/catalogos/paises", token=ana)
mx = next(p for p in paises if p["codigo"] == "MX")
_, plazas = pedir("GET", "/catalogos/plazas", token=ana)
cdmx = next(p for p in plazas if p["nombre"] == "Ciudad de Mexico")
_, mods = pedir("GET", "/catalogos/modalidades", token=ana)
M = {x["codigo"]: x for x in mods if x["pais_id"] == mx["id"]}
_, clientes = pedir("GET", "/catalogos/clientes", token=ana)
_, personal = pedir("GET", "/catalogos/personal", token=ana)
_, perfiles = pedir("GET", "/catalogos/perfiles", token=ana)
_, cats = pedir("GET", "/catalogos/categorias-vehiculo", token=ana)
_, flota = pedir("GET", "/catalogos/vehiculos", token=ana)
juan = next(p for p in personal if p["nombre"] == "Juan Ramirez")
miguel = next(p for p in personal if p["nombre"] == "Miguel Torres")
ana_p = next(p for p in personal if p["nombre"] == "Ana Solis")
conductor = next(p for p in perfiles if p["codigo"] == "conductor_seguridad")
agente = next(p for p in perfiles if p["codigo"] == "agente_seguridad")
suburban = next(c for c in cats if c["codigo"] == "suv_blindada")
unidad = next(v for v in flota if v["categoria_id"] == suburban["id"])

d1 = (datetime.now() - timedelta(days=3)).date()
d2 = (datetime.now() - timedelta(days=2)).date()

titulo("1. Servicio de 2 full days y su cotizacion")
_, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual", "consultor_id": ana_p["id"],
    "solicitante_correo": "patricia@cliente.com", "ejecutivo_correo": "jc@cliente.com",
    "equipos": [{"clave": "EQ-1", "jornadas": [
        {"fecha": d1, "modalidad_id": M["full_day"]["id"],
         "hora_presentacion": "07:00:00", "km_estimados": 100},
        {"fecha": d2, "modalidad_id": M["full_day"]["id"],
         "hora_presentacion": "07:00:00", "km_estimados": 100}]}]}, token=ana)
j1, j2 = srv["equipos"][0]["jornadas"]
print(f"   {srv['folio']}  jornadas {j1['id']} y {j2['id']}")

lineas = []
for f in (d1, d2):
    lineas.append({"fecha": str(f), "tipo": "recurso", "perfil_id": conductor["id"]})
    lineas.append({"fecha": str(f), "tipo": "vehiculo", "categoria_id": suburban["id"]})
c, cotiz = pedir("POST", "/cotizaciones",
                 {"servicio_id": srv["id"], "lineas": lineas}, token=ana)
print(f"   Cotizacion v{cotiz['version']}: {cotiz['total']} {cotiz['moneda']} "
      f"({cotiz['lineas']} lineas)")
pedir("POST", f"/cotizaciones/{cotiz['cotizacion_id']}/autorizar",
      {"autorizada_por": "Patricia Lopez"}, token=ana)
print("   Autorizada por el cliente")

titulo("2. Se ejecuta, pero con dos cosas fuera de lo cotizado")
for j in (j1, j2):
    pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-personal",
          {"persona_id": juan["id"], "forzar": True}, token=ana)
    pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-vehiculo",
          {"vehiculo_id": unidad["id"], "forzar": True}, token=ana)

# Desviacion 1: se sumo un agente el segundo dia sin recotizar
pedir("POST", f"/servicios/jornadas/{j2['id']}/asignar-personal",
      {"persona_id": miguel["id"], "forzar": True}, token=ana)
print("   Se agrego un agente de seguridad el dia 2 sin recotizar")

# Desviacion 2: el dia 2 se pasaron 3 horas
for j, extra in ((j1, 0), (j2, 3)):
    inicio = datetime.fromisoformat(j["inicio_programado"])
    fin = datetime.fromisoformat(j["fin_programado"]) + timedelta(hours=extra)
    for tipo, cuando in (("llegada_origen", inicio - timedelta(minutes=10)),
                         ("contacto_ejecutivo", inicio),
                         ("fin_servicio", fin)):
        pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen",
              {"origen_lat": "19.4270", "origen_lon": "-99.1677"}, token=ana)
        pedir("POST", f"/operacion/jornadas/{j['id']}/hitos",
              {"tipo": tipo, "lat": "19.4272", "lon": "-99.1679",
               "marcado_en": cuando}, token=juan_t)
print("   El dia 2 el servicio se paso 3 horas")

titulo("3. Comparativo: cotizado contra ejecutado")
c, comp = pedir("GET", f"/cierre/servicio/{srv['id']}/comparativo", token=ana)
print(f"   Cotizado:  {comp['cotizacion']['total']}")
print(f"   Ejecutado: {comp['ejecutado']['total']}  "
      f"(horas extra: {comp['ejecutado']['horas_extra']})")
print(f"   Diferencia: {comp['diferencia']}")
print("   Desviaciones detectadas:")
for d in comp["desviaciones"]:
    print(f"      [{d['tipo']}] {d['descripcion']}  ({d['monto']})")

titulo("4. El revisor acompana al consultor")
c, cierre = pedir("POST", f"/cierre/servicio/{srv['id']}/abrir", token=ana)
print(f"   Cierre #{cierre['cierre_id']}, limite: {cierre['limite_consultor'][:16]}")
c, rev = pedir("GET", f"/cierre/servicio/{srv['id']}/revision", token=ana)
print(f"   Listo para finanzas: {rev['listo_para_finanzas']}")
print(f"   {rev['resumen']}")
for o in rev["observaciones"]:
    print(f"      [{o['nivel']}] {o['asunto']}: {o['mensaje']}")
    print(f"         -> {o['accion']}")

titulo("5. El consultor intenta enviar a finanzas con las desviaciones abiertas")
c, r = pedir("POST", f"/cierre/{cierre['cierre_id']}/enviar-finanzas", token=ana)
print(f"   HTTP {c}  (esperado 409)")

titulo("6. Rentabilidad del servicio")
c, rent = pedir("GET", f"/cierre/servicio/{srv['id']}/rentabilidad", token=ana)
print(json.dumps(rent, indent=2, ensure_ascii=False))

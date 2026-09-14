#!/usr/bin/env python3
"""Ciclo diario: candados de la app, tablero de la central,
notificaciones al cliente y aviso de horas extra."""
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta

BASE = "http://localhost:8000"


def pedir(metodo, ruta, cuerpo=None):
    datos = json.dumps(cuerpo, default=str).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


def titulo(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


def msg(r):
    d = r.get("detail", r) if isinstance(r, dict) else r
    return d


pedir("POST", "/sistema/sembrar-catalogos")

_, paises = pedir("GET", "/catalogos/paises")
mx = next(p for p in paises if p["codigo"] == "MX")
_, plazas = pedir("GET", "/catalogos/plazas")
cdmx = next(p for p in plazas if p["nombre"] == "Ciudad de Mexico")
_, mods = pedir("GET", "/catalogos/modalidades")
M = {m["codigo"]: m for m in mods if m["pais_id"] == mx["id"]}
_, clientes = pedir("GET", "/catalogos/clientes")
_, personal = pedir("GET", "/catalogos/personal")
_, flota = pedir("GET", "/catalogos/vehiculos")
juan = next(p for p in personal if p["nombre"] == "Juan Ramirez")
unidad = flota[0]

# Presentacion dentro de 90 minutos, para que caiga en la ventana de 2 horas.
presentacion = (datetime.now() + timedelta(minutes=90)).replace(second=0, microsecond=0)

titulo(f"1. Servicio full day, presentacion a las {presentacion:%H:%M}")
_, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual",
    "solicitante_nombre": "Patricia Lopez", "solicitante_correo": "patricia@cliente.com",
    "ejecutivo_nombre": "Mr. John Carter", "ejecutivo_correo": "jcarter@cliente.com",
    "equipos": [{"clave": "EQ-1", "jornadas": [
        {"fecha": presentacion.date(), "modalidad_id": M["full_day"]["id"],
         "hora_presentacion": presentacion.strftime("%H:%M:%S"),
         "km_estimados": 120}]}]})
j = srv["equipos"][0]["jornadas"][0]
print(f"{srv['folio']}  jornada #{j['id']}  "
      f"{j['inicio_programado'][11:16]} - {j['fin_programado'][11:16]}")

pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-personal",
      {"persona_id": juan["id"], "forzar": True})

# Punto de origen: Angel de la Independencia
ORIGEN = {"origen_lat": "19.4270", "origen_lon": "-99.1677",
          "geocerca_metros": 250, "origen_direccion": "Paseo de la Reforma 500, CDMX"}
pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen", ORIGEN)
print(f"Origen configurado con geocerca de {ORIGEN['geocerca_metros']} m")

titulo("2. Tablero de la central: servicios a 2 horas de iniciar")
c, tab = pedir("GET", "/operacion/tablero-proximos")
for fila in tab:
    print(f"   {fila['servicio']} inicia en {fila['inicia_en_minutos']} min  "
          f"listo={fila['listo']}")
    for p in fila["pendientes"]:
        print(f"      - {p}")

titulo("3. Se resuelven los pendientes")
pedir("POST", f"/operacion/jornadas/{j['id']}/confirmar-recurso", {"persona_id": juan["id"]})
pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-vehiculo",
      {"vehiculo_id": unidad["id"], "forzar": True})
c, prop = pedir("GET", f"/viaticos/calcular?jornada_id={j['id']}&persona_id={juan['id']}")
conceptos = [{"concepto": x["concepto"], "monto": str(x["monto"]),
              "descripcion": x["descripcion"], "origen": x["origen"]}
             for x in prop["conceptos"]]
c, v = pedir("POST", "/viaticos/asignar",
             {"jornada_id": j["id"], "persona_id": juan["id"], "conceptos": conceptos})
c, sol = pedir("POST", f"/viaticos/{v['id']}/solicitar-transferencia")
pedir("POST", "/viaticos/transferencias/barrido")
pedir("POST", f"/viaticos/transferencias/{sol['id']}/confirmar?referencia_odoo=ODOO-1")

c, tab = pedir("GET", "/operacion/tablero-proximos")
for fila in tab:
    print(f"   {fila['servicio']}  listo={fila['listo']}  "
          f"pendientes={fila['pendientes']}")

titulo("4. CANDADO 1: intenta marcar llegada a 3 km del origen")
c, r = pedir("POST", f"/operacion/jornadas/{j['id']}/hitos", {
    "persona_id": juan["id"], "tipo": "llegada_origen",
    "lat": "19.4540", "lon": "-99.1677",
    "marcado_en": presentacion - timedelta(minutes=10)})
print(f"   HTTP {c}  (esperado 409)")
print("  ", json.dumps(msg(r), ensure_ascii=False))

titulo("5. CANDADO 2: llega dentro de la geocerca pero 3 horas antes")
c, r = pedir("POST", f"/operacion/jornadas/{j['id']}/hitos", {
    "persona_id": juan["id"], "tipo": "llegada_origen",
    "lat": "19.4272", "lon": "-99.1679",
    "marcado_en": presentacion - timedelta(hours=3)})
print(f"   HTTP {c}   distancia: {r.get('distancia_origen_m')} m   "
      f"requiere_revision: {r.get('requiere_revision')}")
for a in r.get("avisos", []):
    print(f"   -> {a}")
hito_llegada = r.get("hito_id")

titulo("6. Contacto con el ejecutivo: arranca formalmente el servicio")
c, r = pedir("POST", f"/operacion/jornadas/{j['id']}/hitos", {
    "persona_id": juan["id"], "tipo": "contacto_ejecutivo",
    "lat": "19.4272", "lon": "-99.1679",
    "marcado_en": presentacion})
print(f"   HTTP {c}   hito #{r.get('hito_id')}")

titulo("7. La central ajusta la hora de llegada")
c, r = pedir("POST", f"/operacion/hitos/{hito_llegada}/ajustar", {
    "nuevo_momento": presentacion - timedelta(minutes=20),
    "ajustado_por_id": juan["id"], "justificacion": "corto"})
print(f"   Justificacion corta -> HTTP {c}: {msg(r)}")

c, r = pedir("POST", f"/operacion/hitos/{hito_llegada}/ajustar", {
    "nuevo_momento": presentacion - timedelta(minutes=20),
    "ajustado_por_id": juan["id"],
    "justificacion": "El conductor marco antes por error de la app; "
                     "se valida con GPS y llamada a la central."})
print(f"   Justificacion valida -> HTTP {c}")
print("  ", json.dumps(msg(r), ensure_ascii=False, indent=2)[:300])

titulo("8. Aviso preventivo de horas extra (30 min antes del cierre)")
fin = datetime.fromisoformat(j["fin_programado"])
simulado = fin - timedelta(minutes=25)
c, r = pedir("POST", f"/operacion/avisar-horas-extra?ahora={simulado.isoformat()}")
print(f"   Simulando las {simulado:%H:%M} ->", r)

titulo("9. Alerta por falta de reporte")
simulado2 = presentacion + timedelta(hours=4)
c, r = pedir("POST", f"/operacion/revisar-standby?ahora={simulado2.isoformat()}")
print(f"   Simulando las {simulado2:%H:%M} ->", r)

titulo("10. Bitacora de la jornada")
c, bit = pedir("GET", f"/operacion/jornadas/{j['id']}/bitacora")
print(json.dumps(bit, indent=2, ensure_ascii=False))

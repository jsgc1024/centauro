#!/usr/bin/env python3
"""Ciclo completo de viaticos: calculo, asignacion, transferencia,
comprobacion y cierre."""
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


def titulo(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)


titulo("0. Sembrando parametros (precio del combustible)")
c, r = pedir("POST", "/sistema/sembrar-catalogos")
print(r.get("parametros"))

# --- referencias
_, paises = pedir("GET", "/catalogos/paises")
mx = next(p for p in paises if p["codigo"] == "MX")
_, plazas = pedir("GET", "/catalogos/plazas")
cdmx = next(p for p in plazas if p["nombre"] == "Ciudad de Mexico")
_, mods = pedir("GET", "/catalogos/modalidades")
M = {m["codigo"]: m for m in mods if m["pais_id"] == mx["id"]}
_, clientes = pedir("GET", "/catalogos/clientes")
_, personal = pedir("GET", "/catalogos/personal")
_, cats = pedir("GET", "/catalogos/categorias-vehiculo")
suburban = next(c for c in cats if c["codigo"] == "suv_blindada")
_, flota = pedir("GET", "/catalogos/vehiculos")
unidad = next(v for v in flota if v["categoria_id"] == suburban["id"])
carlos = next(p for p in personal if p["nombre"] == "Carlos Vega")

titulo("1. Servicio full day FORANEO con 420 km estimados")
_, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual",
    "equipos": [{"clave": "EQ-1", "jornadas": [
        {"fecha": "2026-12-01", "modalidad_id": M["full_day"]["id"],
         "hora_presentacion": "06:00:00", "es_foraneo": True,
         "km_estimados": 420}]}]})
j = srv["equipos"][0]["jornadas"][0]
print(f"{srv['folio']}  jornada #{j['id']}  {j['fecha']}  foraneo, 420 km")

pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-personal",
      {"persona_id": carlos["id"], "forzar": True})
pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-vehiculo",
      {"vehiculo_id": unidad["id"], "forzar": True})
print(f"Asignados: {carlos['nombre']} + unidad {unidad['placa']} "
      f"(rendimiento {suburban['rendimiento_km_litro']} km/l)")

titulo("2. Propuesta de viaticos del sistema")
c, prop = pedir("GET", f"/viaticos/calcular?jornada_id={j['id']}&persona_id={carlos['id']}")
print(f"Escenario: {prop['escenario']}   Moneda: {prop['moneda']}")
for con in prop["conceptos"]:
    linea = f"   {con['concepto']:<18} {str(con['monto']):>10}   [{con['origen']}]"
    if con["descripcion"]:
        linea += f"\n      {con['descripcion']}"
    print(linea)
print(f"   {'TOTAL PROPUESTO':<18} {str(prop['total_propuesto']):>10}")

titulo("3. El consultor ajusta: captura casetas y un concepto abierto")
conceptos = []
for con in prop["conceptos"]:
    monto = con["monto"]
    desc = con["descripcion"]
    if con["concepto"] == "casetas":
        monto, desc = "780", "Caseta Mexico-Queretaro ida y vuelta"
    if con["concepto"] == "otros":
        monto, desc = "150", "Parquimetros y amenidades"
    conceptos.append({"concepto": con["concepto"], "monto": str(monto),
                      "descripcion": desc, "origen": con["origen"]})

c, v = pedir("POST", "/viaticos/asignar", {
    "jornada_id": j["id"], "persona_id": carlos["id"], "conceptos": conceptos})
print(f"HTTP {c}   viatico #{v['id']}   total asignado: {v['monto_total']} {v['moneda']}")

titulo("4. Ventana de transferencia")
c, w = pedir("GET", f"/viaticos/transferencias/ventana?jornada_id={j['id']}")
print(json.dumps(w, indent=2, ensure_ascii=False))

c, sol = pedir("POST", f"/viaticos/{v['id']}/solicitar-transferencia")
print(f"Solicitud #{sol['id']} por {sol['monto']} -> {sol['estatus']}")

c, lote = pedir("POST", "/viaticos/transferencias/barrido")
print(f"Barrido {lote['lote']}: {lote['enviadas']} enviadas, "
      f"{lote['pospuestas']} pospuestas (aun no toca su ventana)")

titulo("5. Finanzas confirma y el personal comprueba")
c, r = pedir("POST", f"/viaticos/transferencias/{sol['id']}/confirmar?referencia_odoo=ODOO-8891")
print(r["nota"])

for concepto, tipo, monto in [("alimentos", "nota", "450"),
                              ("hospedaje", "factura", "1200"),
                              ("casetas", "factura", "780")]:
    c, v2 = pedir("POST", f"/viaticos/{v['id']}/comprobantes",
                  {"concepto": concepto, "tipo": tipo, "monto": monto,
                   "archivo_url": f"s3://comprobantes/{concepto}.pdf"})
print(f"Comprobado hasta ahora: {v2['monto_comprobado']} de {v2['monto_total']}")

titulo("6. Cierre con diferencia pendiente")
for comp in v2["comprobantes"]:
    pedir("POST", f"/viaticos/{v['id']}/validar-comprobante/{comp['id']}")
c, r = pedir("POST", f"/viaticos/{v['id']}/cerrar")
print(json.dumps(r, indent=2, ensure_ascii=False))

titulo("7. Se devuelve lo que sobro y se cierra")
sobrante = float(v2["monto_total"]) - float(v2["monto_comprobado"])
c, r = pedir("POST", f"/viaticos/{v['id']}/devolver?monto={sobrante:.2f}"
                     f"&archivo_url=s3://devoluciones/spei.pdf")
print(r)
c, r = pedir("POST", f"/viaticos/{v['id']}/cerrar")
print(json.dumps(r, indent=2, ensure_ascii=False))
print()

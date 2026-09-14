#!/usr/bin/env python3
"""Prueba de punta a punta del alta de servicio y el motor de disponibilidad.
Corre con: python3 probar.py   (no necesita instalar nada)
"""
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
    print("\n" + "=" * 68)
    print(t)
    print("=" * 68)


titulo("1. Sembrando catalogos y recursos")
codigo, r = pedir("POST", "/sistema/sembrar-catalogos")
print(json.dumps(r, indent=2, ensure_ascii=False))

# --- referencias que necesitamos
_, paises = pedir("GET", "/catalogos/paises")
mx = next(p for p in paises if p["codigo"] == "MX")

_, plazas = pedir("GET", "/catalogos/plazas")
cdmx = next(p for p in plazas if p["nombre"] == "Ciudad de Mexico")

_, mods = pedir("GET", "/catalogos/modalidades")
mods_mx = {m["codigo"]: m for m in mods if m["pais_id"] == mx["id"]}

_, perfiles = pedir("GET", "/catalogos/perfiles")
conductor = next(p for p in perfiles if p["codigo"] == "conductor_seguridad")

_, cats = pedir("GET", "/catalogos/categorias-vehiculo")
suburban = next(c for c in cats if c["codigo"] == "suv_blindada")

_, clientes = pedir("GET", "/catalogos/clientes")
cliente = clientes[0]

titulo("2. Alta de servicio eventual de 4 dias con modalidades mezcladas")
servicio = {
    "cliente_id": cliente["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual",
    "solicitante_nombre": "Patricia Lopez", "solicitante_correo": "patricia@clientedemo.com",
    "ejecutivo_nombre": "Mr. John Carter", "ejecutivo_correo": "jcarter@clientedemo.com",
    "equipos": [{
        "clave": "EQ-1", "descripcion": "Un vehiculo blindado con conductor",
        "jornadas": [
            {"fecha": "2026-10-05", "modalidad_id": mods_mx["transfer"]["id"],
             "hora_presentacion": "09:00:00", "km_estimados": 60},
            {"fecha": "2026-10-06", "modalidad_id": mods_mx["full_day"]["id"],
             "hora_presentacion": "07:00:00", "km_estimados": 180},
            {"fecha": "2026-10-07", "modalidad_id": mods_mx["full_day"]["id"],
             "hora_presentacion": "07:00:00", "km_estimados": 180},
            {"fecha": "2026-10-08", "modalidad_id": mods_mx["medio_dia"]["id"],
             "hora_presentacion": "08:00:00", "km_estimados": 80},
        ],
    }],
}
codigo, srv = pedir("POST", "/servicios", servicio)
print(f"HTTP {codigo}  folio: {srv.get('folio')}")
for j in srv["equipos"][0]["jornadas"]:
    print(f"   {j['fecha']}  {j['inicio_programado'][11:16]} - {j['fin_programado'][11:16]}"
          f"   jornada #{j['id']}")

jornadas = srv["equipos"][0]["jornadas"]
j_transfer = jornadas[0]
j_fullday = jornadas[1]

titulo("3. Recomendacion de recursos para el transfer del dia 1")
codigo, rec = pedir("GET", f"/servicios/jornadas/{j_transfer['id']}/recomendaciones"
                           f"?perfil_id={conductor['id']}&categoria_id={suburban['id']}")
print("Conductores disponibles:",
      [p["nombre"] for p in rec["personal"]["disponibles"]])
print("Unidades disponibles:",
      [v["placa"] for v in rec["vehiculos"]["disponibles"]])

if not rec["personal"]["disponibles"]:
    print("Sin conductores libres, no se puede continuar la prueba.")
    raise SystemExit

persona = rec["personal"]["disponibles"][0]
vehiculo = rec["vehiculos"]["disponibles"][0]

titulo("4. Asignando recursos al transfer")
codigo, r = pedir("POST", f"/servicios/jornadas/{j_transfer['id']}/asignar-personal",
                  {"persona_id": persona["persona_id"]})
print(f"HTTP {codigo} ->", r)
codigo, r = pedir("POST", f"/servicios/jornadas/{j_transfer['id']}/asignar-vehiculo",
                  {"vehiculo_id": vehiculo["vehiculo_id"]})
print(f"HTTP {codigo} ->", r)

titulo("5. PRUEBA DE BLOQUEO: otro transfer empalmado el mismo dia")
servicio2 = dict(servicio)
servicio2["equipos"] = [{
    "clave": "EQ-1",
    "jornadas": [{"fecha": "2026-10-05", "modalidad_id": mods_mx["transfer"]["id"],
                  "hora_presentacion": "10:00:00"}],   # empalma con 09:00-12:00
}]
_, srv2 = pedir("POST", "/servicios", servicio2)
j2 = srv2["equipos"][0]["jornadas"][0]
codigo, r = pedir("POST", f"/servicios/jornadas/{j2['id']}/asignar-personal",
                  {"persona_id": persona["persona_id"]})
print(f"HTTP {codigo}  (esperado 409)")
print(json.dumps(r, indent=2, ensure_ascii=False))

titulo("6. PRUEBA DE RIESGO: transfer a las 13:00, solo 1 h despues del anterior")
servicio3 = dict(servicio)
servicio3["equipos"] = [{
    "clave": "EQ-1",
    "jornadas": [{"fecha": "2026-10-05", "modalidad_id": mods_mx["transfer"]["id"],
                  "hora_presentacion": "13:00:00"}],
}]
_, srv3 = pedir("POST", "/servicios", servicio3)
j3 = srv3["equipos"][0]["jornadas"][0]
codigo, r = pedir("POST", f"/servicios/jornadas/{j3['id']}/asignar-personal",
                  {"persona_id": persona["persona_id"]})
print(f"HTTP {codigo}  (esperado 409 de riesgo, no bloqueo)")
print(json.dumps(r, indent=2, ensure_ascii=False))

print("\n--> El consultor decide: reintentando con forzar=true")
codigo, r = pedir("POST", f"/servicios/jornadas/{j3['id']}/asignar-personal",
                  {"persona_id": persona["persona_id"], "forzar": True})
print(f"HTTP {codigo} ->", json.dumps(r, indent=2, ensure_ascii=False))

titulo("7. PRUEBA DE FULL DAY: bloquea el dia completo")
codigo, rec2 = pedir("GET", f"/servicios/jornadas/{j_fullday['id']}/recomendaciones"
                            f"?perfil_id={conductor['id']}&categoria_id={suburban['id']}")
print("Full day del 06-oct, conductores disponibles:",
      [p["nombre"] for p in rec2["personal"]["disponibles"]])
codigo, r = pedir("POST", f"/servicios/jornadas/{j_fullday['id']}/asignar-personal",
                  {"persona_id": persona["persona_id"]})
print(f"Asignando al mismo conductor -> HTTP {codigo} (debe permitir: es otro dia)")

print("\nPrueba terminada.\n")

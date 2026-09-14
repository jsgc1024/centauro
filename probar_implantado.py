#!/usr/bin/env python3
"""Servicio implantado: contrato mensual, calendario, dia adicional,
reemplazo por descanso y resumen para facturar."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

BASE = "http://localhost:8000"


def pedir(metodo, ruta, cuerpo=None, token=None):
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    datos = json.dumps(cuerpo, default=str).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo, headers=cab)

    def leer(d):
        try:
            return json.loads(d or "null")
        except json.JSONDecodeError:
            return {"no_json": (d or b"").decode(errors="replace")[:300]}

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


ana = entrar("ana.solis@centauro.lat")

_, paises = pedir("GET", "/catalogos/paises", token=ana)
mx = next(p for p in paises if p["codigo"] == "MX")
_, plazas = pedir("GET", "/catalogos/plazas", token=ana)
cdmx = next(p for p in plazas if p["nombre"] == "Ciudad de Mexico")
_, mods = pedir("GET", "/catalogos/modalidades", token=ana)
M = {x["codigo"]: x for x in mods if x["pais_id"] == mx["id"]}
_, clientes = pedir("GET", "/catalogos/clientes", token=ana)
_, personal = pedir("GET", "/catalogos/personal", token=ana)
_, flota = pedir("GET", "/catalogos/vehiculos", token=ana)
juan = next(p for p in personal if p["nombre"] == "Juan Ramirez")
luis = next(p for p in personal if p["nombre"] == "Luis Mendoza")
ana_p = next(p for p in personal if p["nombre"] == "Ana Solis")

ANIO, MES = 2026, 11

titulo(f"1. Calendario de {MES:02d}/{ANIO}")
c, cal = pedir("GET", f"/implantados/calendario/{ANIO}/{MES}", token=ana)
print(f"   {cal['dias_habiles']} dias habiles, {cal['fines_de_semana']} de fin de "
      f"semana, {cal['dias_totales']} totales")

titulo("2. Alta del servicio implantado y su contrato mensual")
c, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "implantado", "consultor_id": ana_p["id"],
    "solicitante_correo": "patricia@cliente.com",
    "ejecutivo_correo": "director@cliente.com",
    "equipos": []}, token=ana)
print(f"   {srv['folio']} tipo implantado")

c, con = pedir("POST", "/implantados/contratos", {
    "servicio_id": srv["id"], "anio": ANIO, "mes": MES,
    "modalidad_id": M["full_day"]["id"], "esquema": "por_dia",
    "incluye_fines_de_semana": False,
    "hora_presentacion": "08:00:00",
    "titular_id": juan["id"], "vehiculo_id": flota[0]["id"],
    "precio_mes_vehiculo": "66000", "precio_dia_personal": "2900",
    "precio_dia_adicional": "3500"}, token=ana)
print(f"   Contrato #{con['contrato_id']}  esquema: {con['esquema']}  "
      f"base del mes: {con['dias_base_del_mes']} dias")

titulo("3. Generar el mes")
c, gen = pedir("POST", f"/implantados/contratos/{con['contrato_id']}/generar-mes",
               token=ana)
print(f"   {gen['jornadas_creadas']} jornadas creadas de lunes a viernes")
print(f"   Base del mes: {gen['dias_base_del_mes']} dias")
print(f"   {gen['nota']}")

titulo("4. El cliente pide un sabado extra")
sabado = None
for d in range(1, 29):
    f = date(ANIO, MES, d)
    if f.weekday() == 5:
        sabado = f
        break
c, extra = pedir("POST", f"/implantados/contratos/{con['contrato_id']}/dias-adicionales",
                 {"fecha": str(sabado)}, token=ana)
print(f"   {extra['fecha']} agregado, costo extra {extra['costo_extra']}")

titulo("5. Juan se enferma: Luis lo cubre un dia")
c, res = pedir("GET", f"/implantados/contratos/{con['contrato_id']}/resumen", token=ana)
_, srv_full = pedir("GET", f"/servicios/{srv['id']}", token=ana)
jornadas = srv_full["equipos"][0]["jornadas"]
jornada_media = jornadas[len(jornadas) // 2]
c, rem = pedir("POST", f"/implantados/jornadas/{jornada_media['id']}/reemplazo",
               {"entra_id": luis["id"], "motivo": "enfermedad",
                "nota": "Incapacidad de un dia"}, token=ana)
print(f"   {rem['fecha']}: sale {rem['sale']}, entra {rem['entra']} "
      f"({rem['motivo']})")

titulo("6. Resumen del mes para facturar")
c, res = pedir("GET", f"/implantados/contratos/{con['contrato_id']}/resumen", token=ana)
print(json.dumps(res, indent=2, ensure_ascii=False))

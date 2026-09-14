#!/usr/bin/env python3
"""Estrellas del personal, sancion por incidencia y comision del consultor."""
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


pedir("POST", "/sistema/sembrar-catalogos")
ana = entrar("ana.solis@centauro.lat")
central = entrar("central@centauro.lat")
finanzas = entrar("finanzas@centauro.lat")
diroper = entrar("operaciones@centauro.lat")
dirgen = entrar("direccion@centauro.lat")
luis_t = entrar("luis.mendoza@centauro.lat")

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
luis = next(p for p in personal if p["nombre"] == "Luis Mendoza")
ana_p = next(p for p in personal if p["nombre"] == "Ana Solis")
conductor = next(p for p in perfiles if p["codigo"] == "conductor_seguridad")
suburban = next(c for c in cats if c["codigo"] == "suv_blindada")
unidad = next(v for v in flota if v["categoria_id"] == suburban["id"])

hoy = datetime.now()
ANIO, MES = hoy.year, hoy.month
d1 = hoy.replace(day=min(hoy.day, 20)) - timedelta(days=5)
d2 = d1 + timedelta(days=1)

titulo("1. Dos jornadas de Luis: una puntual y una con retraso")
_, srv = pedir("POST", "/servicios", {
    "cliente_id": clientes[0]["id"], "pais_id": mx["id"], "plaza_id": cdmx["id"],
    "tipo": "eventual", "consultor_id": ana_p["id"],
    "solicitante_correo": "p@cliente.com", "ejecutivo_correo": "e@cliente.com",
    "equipos": [{"clave": "EQ-1", "jornadas": [
        {"fecha": d1.date(), "modalidad_id": M["full_day"]["id"],
         "hora_presentacion": "07:00:00"},
        {"fecha": d2.date(), "modalidad_id": M["full_day"]["id"],
         "hora_presentacion": "07:00:00"}]}]}, token=ana)
jornadas = srv["equipos"][0]["jornadas"]

lineas = []
for j in jornadas:
    lineas.append({"fecha": j["fecha"], "tipo": "recurso", "perfil_id": conductor["id"]})
    lineas.append({"fecha": j["fecha"], "tipo": "vehiculo", "categoria_id": suburban["id"]})
_, cotiz = pedir("POST", "/cotizaciones",
                 {"servicio_id": srv["id"], "lineas": lineas}, token=ana)
pedir("POST", f"/cotizaciones/{cotiz['cotizacion_id']}/autorizar",
      {"autorizada_por": "Cliente"}, token=ana)

for idx, j in enumerate(jornadas):
    c, r = pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-personal",
                 {"persona_id": luis["id"], "forzar": True}, token=ana)
    if c != 200:
        print(f"\n   NO SE PUDO ASIGNAR A LUIS EL {j['fecha']}: HTTP {c}")
        print(f"   {json.dumps(r.get('detail', r), ensure_ascii=False)[:200]}")
        print("\n   Probablemente quedaron jornadas de una corrida anterior en "
              "esas fechas.\n   Corre ./reiniciar.sh y vuelve a intentar.\n")
        raise SystemExit(1)
    c, r = pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-vehiculo",
                 {"vehiculo_id": unidad["id"], "forzar": True}, token=ana)
    if c != 200:
        print(f"\n   NO SE PUDO ASIGNAR LA UNIDAD EL {j['fecha']}: HTTP {c}")
        print("   Corre ./reiniciar.sh y vuelve a intentar.\n")
        raise SystemExit(1)
    pedir("PATCH", f"/operacion/jornadas/{j['id']}/origen",
          {"origen_lat": "19.4270", "origen_lon": "-99.1677"}, token=ana)

    inicio = datetime.fromisoformat(j["inicio_programado"])
    fin = datetime.fromisoformat(j["fin_programado"])
    retraso = timedelta(minutes=25) if idx == 1 else timedelta(0)
    for tipo, cuando in (("llegada_origen", inicio - timedelta(minutes=10) + retraso),
                         ("contacto_ejecutivo", inicio + retraso),
                         ("fin_servicio", fin)):
        c, r = pedir("POST", f"/operacion/jornadas/{j['id']}/hitos",
                     {"tipo": tipo, "lat": "19.4272", "lon": "-99.1679",
                      "marcado_en": cuando}, token=luis_t)
        if c != 200:
            print(f"   Fallo el hito {tipo} del {j['fecha']}: HTTP {c} "
                  f"{json.dumps(r.get('detail', r), ensure_ascii=False)[:120]}")
print(f"   {srv['folio']}: dia 1 puntual, dia 2 con 25 minutos de retraso")

titulo("2. Estrellas del mes (sin capacitacion registrada)")
c, ev = pedir("POST", "/evaluaciones",
              {"persona_id": luis["id"], "anio": ANIO, "mes": MES,
               "capacitacion_cumplida": False}, token=ana)
print(f"   {ev['persona']}  {ev['periodo']}  jornadas: {ev['jornadas_evaluadas']}")
for cr in ev["criterios"]:
    marca = ("--" if not cr["aplica"] else "SI" if cr["cumplido"] else "NO")
    print(f"   [{marca}] {cr['criterio']:<24} medido {cr['medido']:>6}% "
          f"(umbral {cr['umbral']}%)  bono {cr['monto']}")
    print(f"        {cr['detalle']}")
print(f"   ESTRELLAS: {ev['estrellas']} de {ev['estrellas_posibles']} aplicables"
      f"   BONO: {ev['bono']} {ev['moneda']}")

titulo("3. Incidencia leve clasificada por el consultor")
c, inc = pedir("POST", "/incidencias", {
    "persona_id": luis["id"], "fecha": str(d2.date()), "gravedad": "leve",
    "servicio_id": srv["id"],
    "descripcion": "Queja menor del ejecutivo por presentacion del vehiculo"},
    token=ana)
print(f"   Incidencia #{inc['incidencia_id']} ({inc['gravedad']})")
print(f"   {inc['efecto_si_se_autoriza']}")
print(f"   {inc['siguiente_paso']}")

c, ev2 = pedir("POST", "/evaluaciones",
               {"persona_id": luis["id"], "anio": ANIO, "mes": MES,
                "capacitacion_cumplida": False}, token=ana)
print(f"   Bono antes del visto bueno: {ev2['bono']} "
      f"(anulado: {ev2['anulado_por_incidencia']})")

titulo("4. El director de operaciones da el visto bueno")
c, vb = pedir("POST", f"/incidencias/{inc['incidencia_id']}/visto-bueno",
              {"autorizar": True,
               "resolucion": "Se confirma la queja con el cliente"}, token=diroper)
print(f"   {vb['resultado']}: {vb['nota']}")
c, ev3 = pedir("POST", "/evaluaciones",
               {"persona_id": luis["id"], "anio": ANIO, "mes": MES,
                "capacitacion_cumplida": False}, token=ana)
print(f"   Estrellas de referencia: {ev3['estrellas']}   "
      f"BONO: {ev3['bono']}   anulado: {ev3['anulado_por_incidencia']}")

titulo("5. Cierre del servicio y comision del consultor")
c, cierre = pedir("POST", f"/cierre/servicio/{srv['id']}/abrir", token=ana)
c, rev = pedir("GET", f"/cierre/servicio/{srv['id']}/revision", token=ana)
print(f"   Revision: listo={rev['listo_para_finanzas']}")
c, env = pedir("POST", f"/cierre/{cierre['cierre_id']}/enviar-finanzas", token=ana)
print(f"   Enviar a finanzas -> HTTP {c}")
if c == 200:
    print(f"   Dentro de plazo: {env['dentro_de_plazo']}")
    c, apr = pedir("POST", f"/cierre/{cierre['cierre_id']}/aprobar", token=finanzas)
    print(f"   Aprobado por finanzas -> HTTP {c}")
    if apr.get("comision_consultor"):
        k = apr["comision_consultor"]
        print(f"   Comision: facturacion base {k['base']} x {k['porcentaje']}% "
              f"= {k['monto']}  ({k['estatus']})")

titulo("6. Corte mensual del consultor")
c, corte = pedir("GET", f"/comisiones/corte/{ana_p['id']}/{ANIO}/{MES}", token=ana)
print(json.dumps(corte, indent=2, ensure_ascii=False))

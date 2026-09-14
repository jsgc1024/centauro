#!/usr/bin/env python3
"""Implantados al azar, para ver que se rompe.

    python3 implantados_al_azar.py            diez, distintos cada vez
    python3 implantados_al_azar.py 10 4177    diez, repitiendo esa corrida

Arma implantados que no se parecen entre si —ciudades, esquemas de dias,
fechas de arranque a mitad de mes, plantillas de una a tres personas con
una, dos o ninguna unidad— y despues los recorre enteros: el calendario,
cubrir un fin de semana, abrir y cerrar un dia suelto, el cierre del mes
y la hoja en los tres idiomas.

Cada tropiezo se anota y se sigue. Al final la tabla y la lista de lo
que no cuadro, que es para lo que sirve esto.

No borra nada: cada corrida agrega servicios nuevos.
"""
import calendar
import json
import random
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "http://localhost:8000"
HOY = date.today()

CUANTOS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
SEMILLA = int(sys.argv[2]) if len(sys.argv) > 2 else random.randrange(10_000)
rng = random.Random(SEMILLA)

problemas = []


def pedir(metodo, ruta, cuerpo=None, token=None, crudo=False):
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    datos = json.dumps(cuerpo, default=str).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo,
                                 headers=cab)
    try:
        with urllib.request.urlopen(req) as r:
            bruto = r.read()
            if crudo:
                return r.status, bruto.decode(errors="replace")
            return r.status, json.loads(bruto or "null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or "null")
        except json.JSONDecodeError:
            return e.code, bruto.decode(errors="replace")[:300]
    except urllib.error.URLError as e:
        print(f"\nNo hay API en {BASE}: {e.reason}")
        print("Levanta el sistema con  docker compose up -d  y vuelve a correr.")
        sys.exit(1)


def entrar(correo, contrasena="centauro2026"):
    d = urllib.parse.urlencode({"username": correo,
                                "password": contrasena}).encode()
    req = urllib.request.Request(
        BASE + "/auth/token", data=d, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())["access_token"]
    except urllib.error.URLError as e:
        print(f"\nNo se pudo entrar a {BASE}: {e}")
        sys.exit(1)


h = entrar("ana.solis@centauro.lat")

_, clientes = pedir("GET", "/catalogos/clientes", token=h)
_, paises = pedir("GET", "/catalogos/paises", token=h)
_, plazas = pedir("GET", "/catalogos/plazas?todas=true", token=h)
_, modalidades = pedir("GET", "/catalogos/modalidades", token=h)
_, perfiles = pedir("GET", "/catalogos/perfiles", token=h)
_, gente = pedir("GET", "/catalogos/personal?limite=500", token=h)
_, flota = pedir("GET", "/catalogos/vehiculos?limite=500", token=h)

mx = next(p for p in paises if p["codigo"] in ("MX", "MEX"))
ciudades = [p for p in plazas if p["pais_id"] == mx["id"]]
nombre_ciudad = {p["id"]: p["nombre"] for p in plazas}
full_day = next((m for m in modalidades
                 if m["pais_id"] == mx["id"] and m["codigo"] == "full_day"), None)

if not clientes or not ciudades or not full_day:
    print("Faltan catalogos. Corre primero  python3 sembrar_flota.py")
    sys.exit(1)

DE_SEGURIDAD = ("conductor_seguridad", "agente_seguridad")
PERFIL = {p["id"]: p["codigo"] for p in perfiles}
CONDUCTOR = next((p["id"] for p in perfiles
                  if p["codigo"] == "conductor_seguridad"), None)
AGENTE = next((p["id"] for p in perfiles
               if p["codigo"] == "agente_seguridad"), None)

# Solo las ciudades donde hay con que armar un servicio.
CON_RECURSO = [c for c in ciudades
               if any(x["plaza_id"] == c["id"]
                      and PERFIL.get(x["perfil_id"]) in DE_SEGURIDAD
                      for x in gente)
               and any(v["plaza_id"] == c["id"] for v in flota)]
if not CON_RECURSO:
    print("No hay ninguna ciudad con personal de seguridad y flota.")
    sys.exit(1)

PUNTOS = {
    "Ciudad de Mexico": ("Torre Mayor, Paseo de la Reforma 505 - lobby",
                         "19.4264", "-99.1737"),
    "Monterrey": ("Torre Avalanz, Batallon de San Patricio 111, San Pedro",
                  "25.6560", "-100.3620"),
    "Guadalajara": ("Torre Zafiro, Av. Americas 1600, Guadalajara",
                    "20.6960", "-103.3800"),
}

NOMBRES = ["Karen Whitfield", "James Caldwell", "Helen Voss",
           "Patricia Lundgren", "Ingrid Halvorsen", "Robert Sandoval",
           "Marta Oliveira", "Andrew Keene", "Sofia Marchetti",
           "Daniel Okonkwo", "Claire Bennet", "Thomas Nakamura"]

# Nombre, cuantos conductores, cuantos agentes, cuantas unidades.
FORMAS = [
    ("conductor solo", 1, 0, 1),
    ("conductor y agente", 1, 1, 1),
    ("agente a pie", 0, 1, 0),
    ("dos unidades", 2, 0, 2),
    ("equipo de tres", 1, 2, 2),
]

ESQUEMAS = ["lunes_viernes", "lunes_sabado", "todos"]

# El dia en que arranca: el 1, a media quincena y ya entrado el mes.
ARRANQUES = [1, 8, 16, 24]


def persona_al_azar():
    return rng.choice(NOMBRES).split(" ", 1)


def gente_de(plaza_id, perfil_id):
    return [x for x in gente
            if x["plaza_id"] == plaza_id and x["perfil_id"] == perfil_id]


def flota_de(plaza_id):
    return [v for v in flota if v["plaza_id"] == plaza_id]


def armar_plantilla(plaza_id, conductores, agentes, unidades, libres):
    """La plantilla, hecha con quien de verdad esta libre todo el mes.

    Se prefiere a los que no traen choques: un implantado es la misma
    persona todos los dias, y armar el mes con alguien ocupado el dia 12
    es armar un problema para el dia 12.
    """
    disponibles = {p["persona_id"]: p for p in (libres or {}).get("personal", [])}
    unidades_libres = {v["vehiculo_id"]: v
                       for v in (libres or {}).get("vehiculos", [])}

    def escoge(perfil_id, cuantos):
        candidatos = gente_de(plaza_id, perfil_id)
        candidatos.sort(key=lambda x: -(disponibles.get(x["id"], {})
                                        .get("libres", 0)))
        return candidatos[:cuantos]

    personas = escoge(CONDUCTOR, conductores) + escoge(AGENTE, agentes)
    if len(personas) < conductores + agentes:
        return None, None, "no hay suficiente personal en la ciudad"

    coches = flota_de(plaza_id)
    coches.sort(key=lambda v: -(unidades_libres.get(v["id"], {})
                                .get("libres", 0)))
    coches = coches[:unidades]
    if len(coches) < unidades:
        return None, None, "no hay suficientes unidades en la ciudad"

    # Cada unidad la lleva alguien de seguridad: es la regla que valida
    # el servidor, y aqui se cumple repartiendo de uno en uno.
    plantilla = []
    for i, persona in enumerate(personas):
        coche = coches[i] if i < len(coches) else None
        plantilla.append({"persona_id": persona["id"],
                          "vehiculo_id": coche["id"] if coche else None})

    return plantilla, [c["id"] for c in coches], None


def primer_dia(anio, mes, dia):
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(dia, ultimo))


def mes_siguiente(n=1):
    anio, mes = HOY.year, HOY.month + n
    while mes > 12:
        anio, mes = anio + 1, mes - 12
    return anio, mes


# ------------------------------------------------------------ dar de alta

print(f"Semilla {SEMILLA} — repite con "
      f"python3 implantados_al_azar.py {CUANTOS} {SEMILLA}\n")
print("Lo que hay en casa")
for ciudad in CON_RECURSO:
    suyos = [x for x in gente if x["plaza_id"] == ciudad["id"]
             and PERFIL.get(x["perfil_id"]) in DE_SEGURIDAD]
    print(f"   {ciudad['nombre']:<20} {len(suyos)} de seguridad · "
          f"{len(flota_de(ciudad['id']))} unidades")

print("\nDando de alta")
creados = []

for i in range(CUANTOS):
    ciudad = CON_RECURSO[i % len(CON_RECURSO)]
    forma, conductores, agentes, unidades = FORMAS[i % len(FORMAS)]
    esquema = ESQUEMAS[i % len(ESQUEMAS)]
    anio, mes = mes_siguiente(1 + (i // len(ESQUEMAS)) % 2)
    arranque = primer_dia(anio, mes, ARRANQUES[i % len(ARRANQUES)])
    dos_pasos = i % 2 == 0

    sol_nombre, sol_apellidos = persona_al_azar()
    eje_nombre, eje_apellidos = persona_al_azar()
    direccion, lat, lon = PUNTOS.get(ciudad["nombre"],
                                     PUNTOS["Ciudad de Mexico"])

    acuerdo = {
        "cubre": "Traslados casa-oficina, escolta a reuniones y avanzadas "
                 "en la zona acordada.",
        "no_cubre": "Mandados personales y traslados de familiares sin "
                    "autorizacion de la coordinacion.",
        "zona_operacion": "Miguel Hidalgo, Cuauhtemoc, Alvaro Obregon",
        "dias_semana": {"lunes_viernes": "Lunes a viernes",
                        "lunes_sabado": "Lunes a sabado",
                        "todos": "Todos los dias"}[esquema],
        "fecha_inicio": str(arranque),
        "dias_servicio": esquema,
        "origen_direccion": direccion,
        "origen_lat": lat, "origen_lon": lon, "geocerca_metros": 500,
        "reporta_a_nombre": "Marta", "reporta_a_apellidos": "Ruiz de la Vega",
        "reporta_a_telefono": "+52 55 1122 3344",
        "reporta_a_correo": "coordinacion@cliente.com",
        "protocolo_contacto": "Reporta llegada por WhatsApp al grupo antes "
                              "de las 07:40.\nCambios de ruta solo los "
                              "autoriza la coordinacion.\nSi el ejecutivo "
                              "no baja, espera 20 minutos y marca.",
    }

    datos_cliente = {
        "cliente_id": rng.choice(clientes)["id"],
        "pais_id": mx["id"], "plaza_id": ciudad["id"],
        "solicitante_nombre": sol_nombre, "solicitante_apellidos": sol_apellidos,
        "solicitante_correo": f"{sol_nombre.lower()}.{sol_apellidos.lower()}"
                              f"@cliente.com",
        "solicitante_telefono": f"+52 55 {rng.randrange(1000, 9999)} "
                                f"{rng.randrange(1000, 9999)}",
        "ejecutivo_nombre": eje_nombre, "ejecutivo_apellidos": eje_apellidos,
        "ejecutivo_correo": f"{eje_nombre.lower()}@ejecutivo.com",
        "ejecutivo_telefono": f"+1 713 555 {rng.randrange(1000, 9999)}",
        "acuerdo": acuerdo,
    }

    # Quien esta libre ese mes, para armar la plantilla con cabeza.
    parametros = urllib.parse.urlencode({
        "plaza_id": ciudad["id"], "desde": str(arranque),
        "dias_servicio": esquema})
    codigo, libres = pedir("GET", f"/implantados/disponibilidad?{parametros}",
                           token=h)
    if codigo != 200:
        problemas.append(f"disponibilidad de {ciudad['nombre']}: {codigo} {libres}")
        libres = None

    plantilla, coches, falla = armar_plantilla(
        ciudad["id"], conductores, agentes, unidades, libres)
    if falla:
        problemas.append(f"{forma} en {ciudad['nombre']}: {falla}")
        print(f"   ✗ {forma:<20} {ciudad['nombre']:<18} {falla}")
        continue

    mes_datos = {
        "modalidad_id": full_day["id"],
        "hora_presentacion": rng.choice(["07:00:00", "08:00:00", "09:00:00"]),
        "esquema": "por_dia",
        "personal": plantilla, "unidades": coches,
        "precio_mes_vehiculo": "66000", "precio_dia_personal": "2900",
        "precio_dia_adicional": "3500",
    }

    if dos_pasos:
        codigo, r = pedir("POST", "/implantados/servicio", datos_cliente, token=h)
        if codigo != 201:
            problemas.append(f"alta en dos pasos ({forma}): {codigo} {r}")
            print(f"   ✗ {forma:<20} {codigo} {r}")
            continue
        servicio_id, folio, estatus = r["servicio_id"], r["folio"], r["estatus"]
        if estatus != "solicitado":
            problemas.append(f"{folio}: al guardar el acuerdo quedo "
                             f"'{estatus}' y deberia ser 'solicitado'")
        codigo, r = pedir("POST", f"/implantados/{servicio_id}/mes",
                          mes_datos, token=h)
        if codigo != 201:
            problemas.append(f"{folio}: abrir el mes {codigo} {r}")
            print(f"   ✗ {folio:<11} {forma:<20} {codigo} {r}")
            continue
        creadas = r.get("jornadas_creadas", 0)
    else:
        codigo, r = pedir("POST", "/implantados", {
            **datos_cliente, **mes_datos,
            "fecha_inicio": str(arranque), "dias_servicio": esquema}, token=h)
        if codigo != 201:
            problemas.append(f"alta de un tiron ({forma}): {codigo} {r}")
            print(f"   ✗ {forma:<20} {codigo} {r}")
            continue
        servicio_id, folio = r["servicio_id"], r["folio"]
        creadas = r.get("jornadas_creadas", 0)

    print(f"   {folio:<11} {forma:<20} {ciudad['nombre']:<18} "
          f"{esquema:<14} desde {arranque} · {creadas} dias"
          + ("  (dos pasos)" if dos_pasos else ""))

    creados.append({
        "servicio_id": servicio_id, "folio": folio, "forma": forma,
        "ciudad": ciudad["nombre"], "esquema": esquema,
        "arranque": arranque, "anio": anio, "mes": mes,
        "jornadas": creadas, "plantilla": plantilla,
    })

if not creados:
    print("\nNo se creo ninguno. Revisa la consola del api.")
    sys.exit(1)

# ------------------------------------------------------------- recorrerlos

print("\nRecorriendo cada uno")

filas = []
for s_ in creados:
    sid, folio = s_["servicio_id"], s_["folio"]
    linea = []

    # ---- el calendario
    codigo, cal = pedir("GET",
                        f"/implantados/{sid}/calendario/{s_['anio']}/{s_['mes']}",
                        token=h)
    if codigo != 200:
        problemas.append(f"{folio}: calendario {codigo} {cal}")
        continue

    verdes = [d for d in cal["dias"] if d["estado"] == "cubierto"]
    ambar = [d for d in cal["dias"] if d["estado"] == "por_cubrir"]
    grises = [d for d in cal["dias"] if d["estado"] == "sin_servicio"
              and d["fecha"] >= str(s_["arranque"])]

    if s_["esquema"] == "lunes_viernes" and ambar:
        problemas.append(f"{folio}: de lunes a viernes y salieron "
                         f"{len(ambar)} dias en ambar")
    if s_["esquema"] != "lunes_viernes" and not ambar:
        problemas.append(f"{folio}: esquema {s_['esquema']} y ningun dia "
                         f"en ambar")
    linea.append(f"{len(verdes)}v/{len(ambar)}a")

    # ---- cubrir un fin de semana contratado
    if ambar:
        fecha = ambar[0]["fecha"]
        codigo, dia = pedir("GET", f"/implantados/{sid}/dia/{fecha}", token=h)
        if codigo != 200:
            problemas.append(f"{folio}: ficha del dia {fecha} {codigo} {dia}")
        else:
            if not dia["candidatos"]:
                problemas.append(f"{folio}: el {fecha} no propone a nadie")
            # Lo cubre alguien que no es de la plantilla, si se puede:
            # es el caso del relevo, que es el que interesa.
            de_planta = {p["persona_id"] for p in s_["plantilla"]}
            relevo = next((c for c in dia["candidatos"]
                           if not c["ocupado"] and not c["del_equipo"]), None)
            quien = relevo or next((c for c in dia["candidatos"]
                                    if not c["ocupado"]), None)
            if not quien:
                problemas.append(f"{folio}: nadie libre para el {fecha}")
            else:
                codigo, r = pedir(
                    "POST", f"/implantados/{sid}/dia/{fecha}/cubrir",
                    {"personal": [{"persona_id": quien["persona_id"],
                                   "vehiculo_id": p["vehiculo_id"]}
                                  for p in s_["plantilla"][:1]],
                     "ambos_dias": True}, token=h)
                if codigo != 200:
                    problemas.append(f"{folio}: cubrir {fecha} {codigo} {r}")
                else:
                    linea.append(f"cubre {len(r['dias'])}d")
                    if s_["esquema"] == "todos" and len(r["dias"]) != 2:
                        problemas.append(
                            f"{folio}: con los dos dias contratados, cubrir "
                            f"el {fecha} debio llevarse los dos y se llevo "
                            f"{len(r['dias'])}")

    # ---- abrir un dia gris y volverlo a cerrar
    if grises:
        fecha = grises[0]["fecha"]
        codigo, r = pedir("POST", f"/implantados/{sid}/dia/{fecha}/cubrir",
                          {"personal": s_["plantilla"][:1],
                           "ambos_dias": False}, token=h)
        if codigo != 200:
            problemas.append(f"{folio}: abrir el gris {fecha} {codigo} {r}")
        else:
            codigo, r = pedir("DELETE", f"/implantados/{sid}/dia/{fecha}",
                              token=h)
            if codigo != 200:
                problemas.append(f"{folio}: cerrar el gris {fecha} {codigo} {r}")
            else:
                linea.append("gris ok")

    # ---- el cierre del mes
    codigo, contratos = pedir("GET", "/implantados/contratos", token=h)
    contrato = next((c for c in contratos if c["servicio"] == folio), None)
    cierre = None
    if not contrato:
        problemas.append(f"{folio}: no aparece en la lista de contratos")
    else:
        codigo, cierre = pedir(
            "GET", f"/implantados/contratos/{contrato['id']}/cierre", token=h)
        if codigo != 200:
            problemas.append(f"{folio}: cierre {codigo} {cierre}")
            cierre = None
        else:
            dias_cliente = cierre["cliente"]["dias_de_actividad"]
            suma = sum(p["dias"] for p in cierre["personal"])
            if not dias_cliente:
                problemas.append(f"{folio}: el cierre no trae dias de actividad")
            if cierre["personal"] and not suma:
                problemas.append(f"{folio}: el cierre trae gente con cero dias")
            linea.append(f"cierre {dias_cliente}d")

    # ---- la hoja
    codigo, r = pedir("POST", f"/task-sheets/implantado/{sid}/liberar",
                      token=h)
    hoja = "no"
    if codigo != 200:
        problemas.append(f"{folio}: liberar la hoja {codigo} {r}")
    else:
        if r["estatus"] != "asignado":
            problemas.append(f"{folio}: al liberar quedo '{r['estatus']}' "
                             f"y deberia ser 'asignado'")
        hoja = f"v{r['version']}"

        for lengua in ("es", "en", "pt"):
            codigo, html = pedir(
                "GET", f"/task-sheets/implantado/{sid}/hoja?idioma={lengua}",
                token=h, crudo=True)
            if codigo != 200:
                problemas.append(f"{folio}: hoja en {lengua} {codigo} {html}")
            elif "<html" not in html.lower():
                problemas.append(f"{folio}: la hoja en {lengua} no es HTML")
            elif folio not in html:
                problemas.append(f"{folio}: la hoja en {lengua} no trae el folio")

    # ---- la hoja de cobertura del dia que se cubrio
    if ambar:
        codigo, html = pedir(
            "GET", f"/task-sheets/implantado/{sid}/cobertura/{ambar[0]['fecha']}",
            token=h, crudo=True)
        if codigo != 200:
            problemas.append(f"{folio}: hoja de cobertura {codigo} {html}")
        else:
            linea.append("cobertura ok")

    print(f"   {folio:<11} " + " · ".join(linea))

    filas.append({
        "folio": folio, "forma": s_["forma"], "ciudad": s_["ciudad"],
        "esquema": s_["esquema"], "arranque": str(s_["arranque"]),
        "verdes": len(verdes), "ambar": len(ambar),
        "dias_cierre": (cierre["cliente"]["dias_de_actividad"]
                        if cierre else 0),
        "gente_cierre": len(cierre["personal"]) if cierre else 0,
        "hoja": hoja,
    })

# --------------------------------------------------------------- la tabla

print("\n" + "=" * 116)
print(f"{'FOLIO':<11} {'FORMA':<20} {'CIUDAD':<18} {'ESQUEMA':<14} "
      f"{'ARRANCA':<11} {'VERDES':<7} {'AMBAR':<6} {'CIERRE':<7} {'HOJA':<5}")
print("-" * 116)
for f in filas:
    print(f"{f['folio']:<11} {f['forma']:<20} {f['ciudad']:<18} "
          f"{f['esquema']:<14} {f['arranque']:<11} {f['verdes']:<7} "
          f"{f['ambar']:<6} {f['dias_cierre']:<7} {f['hoja']:<5}")
print("=" * 116)

print(f"\n{len(filas)} implantados · "
      f"{sum(1 for f in filas if f['hoja'] != 'no')} con hoja liberada")

if problemas:
    print(f"\n{len(problemas)} cosas que no cuadraron:")
    for p in problemas:
        print(f"   · {p}")
else:
    print("\nTodo en orden.")

print("\nRecarga la consola para verlos.")

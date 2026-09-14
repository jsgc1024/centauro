#!/usr/bin/env python3
"""Cinco eventuales grandes, de tres a siete equipos cada uno.

    python3 servicios_multiequipo.py            distinto cada vez
    python3 servicios_multiequipo.py 5 4177     cinco, repitiendo esa corrida

La prueba final del eventual: proyectos de varios equipos, cada uno con
su ciudad, sus dias y su propia configuracion de gente y unidades.

  · conductor solo            un conductor, una unidad
  · escolta                   dos personas, una unidad
  · caravana                  dos personas, dos unidades, una cada quien
  · agente a pie              una persona, sin unidad
  · equipo de tres            tres personas, dos unidades

Despues los recorre: asigna, reparte el abordo —quien va en que
unidad—, revisa viaticos, confirma y publica el task sheet. Al final la
tabla y todo lo que no cuadro.

No borra nada: cada corrida agrega servicios nuevos.
"""
import json
import random
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "http://localhost:8000"
HOY = date.today()

CUANTOS = int(sys.argv[1]) if len(sys.argv) > 1 else 5
SEMILLA = int(sys.argv[2]) if len(sys.argv) > 2 else random.randrange(10_000)
rng = random.Random(SEMILLA)

problemas = []


def pedir(metodo, ruta, cuerpo=None, token=None):
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    datos = json.dumps(cuerpo, default=str).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo,
                                 headers=cab)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or "null")
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
_, categorias = pedir("GET", "/catalogos/categorias-vehiculo", token=h)
_, gente = pedir("GET", "/catalogos/personal?limite=500", token=h)
_, flota = pedir("GET", "/catalogos/vehiculos?limite=500", token=h)

mx = next(p for p in paises if p["codigo"] in ("MX", "MEX"))
ciudades = [p for p in plazas if p["pais_id"] == mx["id"]]
por_ciudad = {p["nombre"]: p for p in ciudades}
mods = {m["codigo"]: m for m in modalidades if m["pais_id"] == mx["id"]}
nombre_ciudad = {p["id"]: p["nombre"] for p in plazas}
nombre_categoria = {c["id"]: c["nombre"] for c in categorias}

if not clientes or not ciudades or not mods:
    print("Faltan catalogos. Corre primero  python3 sembrar_flota.py")
    sys.exit(1)

DE_SEGURIDAD = ("conductor_seguridad", "agente_seguridad")
PERFILES_SEGURIDAD = [p["id"] for p in perfiles
                      if p["codigo"] in DE_SEGURIDAD] or [p["id"] for p in perfiles]

CDMX = por_ciudad.get("Ciudad de Mexico") or ciudades[0]
# Las ciudades donde de verdad hay con que trabajar.
CON_RECURSO = [c for c in ciudades
               if any(x["plaza_id"] == c["id"] and x["perfil_id"] in PERFILES_SEGURIDAD
                      for x in gente)
               and any(v["plaza_id"] == c["id"] for v in flota)] or [CDMX]


def cuenta_por(coleccion, plaza_id, llave):
    cuenta = {}
    for x in coleccion:
        if x.get("plaza_id") == plaza_id:
            cuenta[x[llave]] = cuenta.get(x[llave], 0) + 1
    return cuenta


def categorias_de(plaza_id):
    cuenta = cuenta_por(flota, plaza_id, "categoria_id")
    orden = [c for c, _ in sorted(cuenta.items(), key=lambda kv: -kv[1])]
    return orden + [c["id"] for c in categorias if c["id"] not in cuenta]


def perfiles_de(plaza_id):
    cuenta = cuenta_por([p for p in gente if p["perfil_id"] in PERFILES_SEGURIDAD],
                        plaza_id, "perfil_id")
    orden = [p for p, _ in sorted(cuenta.items(), key=lambda kv: -kv[1])]
    return orden + [p for p in PERFILES_SEGURIDAD if p not in cuenta]


def inventario():
    print("Lo que hay en casa")
    donde = sorted({x["plaza_id"] for x in gente} | {v["plaza_id"] for v in flota})
    for plaza_id in donde:
        suyos = [x for x in gente if x["plaza_id"] == plaza_id
                 and x["perfil_id"] in PERFILES_SEGURIDAD]
        unidades = [v for v in flota if v["plaza_id"] == plaza_id]
        detalle = ", ".join(
            f"{n} {nombre_categoria.get(c, '?')}"
            for c, n in sorted(cuenta_por(unidades, plaza_id, "categoria_id").items(),
                               key=lambda kv: -kv[1])) or "ninguna"
        print(f"   {nombre_ciudad.get(plaza_id, '?'):<20} "
              f"{len(suyos)} de seguridad · {len(unidades)} unidades ({detalle})")
    print()


# ------------------------------------------------------------- los puntos

PUNTOS = {
    "Ciudad de Mexico": [
        {"nombre": "aeropuerto", "aeropuerto": True,
         "origen_direccion": "Aeropuerto Internacional Benito Juarez, Terminal 2",
         "origen_lat": "19.4353", "origen_lon": "-99.0719",
         "geocerca_metros": 2000},
        {"nombre": "hotel Polanco",
         "origen_direccion": "Las Alcobas, Presidente Masaryk 390 - lobby",
         "origen_lat": "19.4325", "origen_lon": "-99.1975",
         "geocerca_metros": 500},
        {"nombre": "oficina Reforma",
         "origen_direccion": "Torre Mayor, Paseo de la Reforma 505 - lobby",
         "origen_lat": "19.4264", "origen_lon": "-99.1737",
         "geocerca_metros": 500},
        {"nombre": "Santa Fe",
         "origen_direccion": "Park Plaza, Javier Barros Sierra 540, Santa Fe",
         "origen_lat": "19.3641", "origen_lon": "-99.2718",
         "geocerca_metros": 500},
    ],
    "Monterrey": [
        {"nombre": "aeropuerto MTY", "aeropuerto": True,
         "origen_direccion": "Aeropuerto Internacional Mariano Escobedo",
         "origen_lat": "25.7785", "origen_lon": "-100.1069",
         "geocerca_metros": 2000},
        {"nombre": "San Pedro",
         "origen_direccion": "Hotel Habita MTY, Vasconcelos 209, San Pedro",
         "origen_lat": "25.6540", "origen_lon": "-100.3620",
         "geocerca_metros": 500},
    ],
    "Guadalajara": [
        {"nombre": "aeropuerto GDL", "aeropuerto": True,
         "origen_direccion": "Aeropuerto Internacional Miguel Hidalgo y Costilla",
         "origen_lat": "20.5218", "origen_lon": "-103.3112",
         "geocerca_metros": 2000},
        {"nombre": "Puerta de Hierro",
         "origen_direccion": "Hotel Demetria, Av. Union 1541, Guadalajara",
         "origen_lat": "20.6800", "origen_lon": "-103.3830",
         "geocerca_metros": 500},
    ],
}

NOMBRES = ["Karen Whitfield", "James Caldwell", "Helen Voss",
           "Patricia Lundgren", "Ingrid Halvorsen", "Robert Sandoval",
           "Marta Oliveira", "Andrew Keene", "Sofia Marchetti",
           "Daniel Okonkwo", "Claire Bennet", "Thomas Nakamura",
           "Gregory Ashford", "Yuki Tanaka", "Elena Vasquez"]

# Cuanta gente y cuantas unidades lleva cada equipo.
CONFIGURACIONES = [
    ("conductor solo", 1, 1),
    ("escolta", 2, 1),
    ("caravana", 2, 2),
    ("agente a pie", 1, 0),
    ("equipo de tres", 3, 2),
]

PROYECTOS = ["Gira de directorio", "Visita de casa matriz",
             "Auditoria regional", "Cierre de planta", "Consejo trimestral"]


def persona_al_azar():
    return rng.choice(NOMBRES).split(" ", 1)


def dia(cuando, modalidad, punto, hora=None, vuelo=False):
    j = {"fecha": str(cuando), "modalidad_id": mods[modalidad]["id"]}
    if hora:
        j["hora_presentacion"] = hora
    for llave, valor in punto.items():
        if llave in ("nombre", "aeropuerto"):
            continue
        j[llave] = valor
    if punto.get("aeropuerto"):
        j["origen_aeropuerto"] = True
    if vuelo:
        j.update({"vuelo_aerolinea": rng.choice(["United", "Aeromexico", "Delta"]),
                  "vuelo_numero": f"{rng.choice(['UA', 'AM', 'DL'])} "
                                  f"{rng.randrange(100, 1999)}",
                  "vuelo_origen": rng.choice(["Houston", "Bogota", "Madrid"]),
                  "vuelo_tipo": "llegada",
                  "vuelo_hora": f"{cuando}T{rng.randrange(7, 21):02d}:"
                                f"{rng.choice(['05', '20', '40'])}:00"})
    return j


def armar(indice):
    """Un proyecto grande: de tres a siete equipos, cada uno lo suyo."""
    titulo = PROYECTOS[indice % len(PROYECTOS)]
    vuelta = indice // len(PROYECTOS)
    if vuelta:
        titulo += f" ({vuelta + 1})"

    arranque = HOY + timedelta(days=rng.randrange(3, 55))
    sol_nombre, sol_apellidos = persona_al_azar()
    eje_nombre, eje_apellidos = persona_al_azar()

    equipos, plan = [], []
    for n in range(rng.randrange(3, 8)):
        ciudad = rng.choice(CON_RECURSO)
        puntos = PUNTOS.get(ciudad["nombre"]) or PUNTOS["Ciudad de Mexico"]
        modalidad = rng.choice(["full_day", "full_day", "medio_dia", "transfer"])
        cuantos_dias = 1 if modalidad == "transfer" else rng.randrange(1, 4)
        desde = arranque + timedelta(days=rng.randrange(0, 4))

        jornadas = []
        for d in range(cuantos_dias):
            punto = rng.choice(puntos)
            jornadas.append(dia(
                desde + timedelta(days=d), modalidad, punto,
                hora=rng.choice(["06:00:00", "07:30:00", "08:00:00", "13:00:00"]),
                vuelo=(d == 0 and punto.get("aeropuerto"))))

        # Cada equipo cuida a alguien: el mismo ejecutivo en dos ciudades,
        # o su familia en la misma. Los dos casos pasan de verdad.
        if rng.random() < 0.5:
            nombre, apellidos = eje_nombre, eje_apellidos
        else:
            nombre, apellidos = persona_al_azar()

        equipos.append({"plaza_id": ciudad["id"],
                        "ejecutivo_nombre": nombre,
                        "ejecutivo_apellidos": apellidos,
                        "ejecutivo_correo": f"{nombre.lower()}@ejecutivo.com",
                        "jornadas": jornadas})
        plan.append(rng.choice(CONFIGURACIONES))

    return titulo, plan, {
        "solicitante_nombre": sol_nombre, "solicitante_apellidos": sol_apellidos,
        "solicitante_correo": f"{sol_nombre.lower()}.{sol_apellidos.lower()}"
                              f"@cliente.com",
        "solicitante_telefono": f"+52 55 {rng.randrange(1000, 9999)} "
                                f"{rng.randrange(1000, 9999)}",
        "ejecutivo_nombre": eje_nombre, "ejecutivo_apellidos": eje_apellidos,
        "ejecutivo_correo": f"{eje_nombre.lower()}@ejecutivo.com",
        "ejecutivo_telefono": f"+1 713 555 {rng.randrange(1000, 9999)}",
        "plaza_id": CDMX["id"],
        "equipos": equipos,
    }


# ------------------------------------------------------------ dar de alta

print(f"Semilla {SEMILLA} — repite con "
      f"python3 servicios_multiequipo.py {CUANTOS} {SEMILLA}\n")
inventario()
print("Dando de alta")

creados = []
for i in range(CUANTOS):
    titulo, plan, datos = armar(i)
    codigo, r = pedir("POST", "/servicios", {
        "cliente_id": rng.choice(clientes)["id"], "pais_id": mx["id"],
        "tipo": "eventual", **datos}, token=h)
    if codigo != 201:
        problemas.append(f"alta de '{titulo}': {codigo} {r}")
        print(f"   ✗ {titulo:<26} {codigo} {r}")
        continue
    dias = sum(len(e["jornadas"]) for e in r["equipos"])
    print(f"   {r['folio']:<10} {titulo:<26} "
          f"{len(r['equipos'])} equipos, {dias} dias")
    creados.append({"titulo": titulo, "plan": plan, **r})

if not creados:
    print("\nNo se creo ninguno. Revisa la consola del api.")
    sys.exit(1)

# --------------------------------------------------------- asignar equipos

print("\nAsignando, equipo por equipo")


def libres(bloque, cuantos):
    """Los que se pueden tomar: libres, con alerta, o de otra ciudad."""
    monton = list(bloque.get("disponibles") or [])
    monton += list(bloque.get("con_alerta") or [])
    monton += [f for f in (bloque.get("de_otras_ciudades") or [])
               if not f["bloqueado"]]
    return monton[:cuantos]


def buscar(eid, ciudad_id, cuanta_gente, cuantas_unidades):
    """Recorre perfiles y categorias hasta juntar lo que pide la
    configuracion. Preguntar por una sola categoria contesta que no hay
    flota cuando la flota esta ahi, en otra categoria."""
    personas, unidades = [], []
    for perfil_id in perfiles_de(ciudad_id):
        for categoria_id in categorias_de(ciudad_id):
            codigo, rec = pedir(
                "GET", f"/servicios/equipos/{eid}/recomendaciones"
                       f"?perfil_id={perfil_id}&categoria_id={categoria_id}",
                token=h)
            if codigo != 200:
                return personas, unidades, f"recomendaciones {codigo} {rec}"
            for ficha in libres(rec["personal"], cuanta_gente):
                if len(personas) < cuanta_gente and ficha not in personas:
                    if ficha["persona_id"] not in [p["persona_id"] for p in personas]:
                        personas.append(ficha)
            for ficha in libres(rec["vehiculos"], cuantas_unidades):
                if len(unidades) < cuantas_unidades:
                    if ficha["vehiculo_id"] not in [v["vehiculo_id"] for v in unidades]:
                        unidades.append(ficha)
            if (len(personas) >= cuanta_gente
                    and len(unidades) >= cuantas_unidades):
                return personas, unidades, None
    return personas, unidades, None


for s_ in creados:
    lineas = []
    for equipo, (forma, cuanta_gente, cuantas_unidades) in zip(s_["equipos"],
                                                               s_["plan"]):
        eid = equipo["id"]
        ciudad_id = equipo.get("ciudad_id") or CDMX["id"]
        ciudad = nombre_ciudad.get(ciudad_id, "?")
        personas, unidades, error = buscar(eid, ciudad_id, cuanta_gente,
                                           cuantas_unidades)
        if error:
            problemas.append(f"{s_['folio']} {equipo['alias']}: {error}")
            continue

        puestas = []
        for persona in personas:
            codigo, r = pedir(
                "POST", f"/servicios/equipos/{eid}/asignar-personal",
                {"persona_id": persona["persona_id"], "forzar": True}, token=h)
            if codigo >= 400:
                problemas.append(f"{s_['folio']} {equipo['alias']}: "
                                 f"asignar {persona.get('nombre')} {codigo} {r}")
            else:
                puestas.append(persona)

        subidas = []
        for unidad in unidades:
            codigo, r = pedir(
                "POST", f"/servicios/equipos/{eid}/asignar-vehiculo",
                {"vehiculo_id": unidad["vehiculo_id"], "forzar": True}, token=h)
            if codigo >= 400:
                problemas.append(f"{s_['folio']} {equipo['alias']}: "
                                 f"unidad {unidad.get('placa')} {codigo} {r}")
            else:
                subidas.append(unidad)

        # El abordo: quien va en que unidad. Con dos unidades se reparten
        # uno y uno; con una, todos en la misma.
        for i, persona in enumerate(puestas):
            if not subidas:
                break
            unidad = subidas[i % len(subidas)]
            codigo, r = pedir(
                "PATCH", f"/servicios/equipos/{eid}/personal/"
                         f"{persona['persona_id']}/unidad",
                {"vehiculo_id": unidad["vehiculo_id"]}, token=h)
            if codigo >= 400:
                problemas.append(f"{s_['folio']} {equipo['alias']}: "
                                 f"abordo {codigo} {r}")

        faltan = []
        if len(puestas) < cuanta_gente:
            faltan.append(f"{cuanta_gente - len(puestas)} de seguridad")
        if len(subidas) < cuantas_unidades:
            faltan.append(f"{cuantas_unidades - len(subidas)} unidades")
        if faltan:
            problemas.append(f"{s_['folio']} {equipo['alias']} ({forma}, "
                             f"{ciudad}): faltaron " + " y ".join(faltan))

        lineas.append(f"{equipo['alias']} {forma} {len(puestas)}p/"
                      f"{len(subidas)}u {ciudad}")

    print(f"   {s_['folio']:<10} " + " · ".join(lineas))

# ----------------------------------------------------------- que quedo

print("\nRevisando")

filas = []
for s_ in creados:
    codigo, prog = pedir("GET", f"/servicios/{s_['id']}/programacion", token=h)
    if codigo != 200:
        problemas.append(f"{s_['folio']}: programacion {codigo} {prog}")
        continue

    propuesto, moneda = 0, ""
    for equipo in s_["equipos"]:
        codigo, panel = pedir("GET", f"/viaticos/equipos/{equipo['id']}", token=h)
        if codigo != 200:
            problemas.append(f"{s_['folio']} {equipo['alias']}: "
                             f"viaticos {codigo} {panel}")
            continue
        propuesto += float(panel["total_propuesto"] or 0)
        moneda = panel["moneda"] or ""

    publicado = "—"
    if prog["recursos_completos"]:
        pedir("POST", f"/servicios/{s_['id']}/confirmar-asignacion", token=h)
        codigo, r = pedir("POST", f"/task-sheets/servicio/{s_['id']}/publicar",
                          {"motivo": "prueba final", "forzar": False}, token=h)
        if codigo == 200:
            hojas = r if isinstance(r, list) else [r]
            publicado = f"{len(hojas)} hoja(s)"
        else:
            detalle = r.get("detail", r) if isinstance(r, dict) else r
            publicado = "no"
            problemas.append(f"{s_['folio']}: publicar {codigo} {detalle}")

    filas.append({
        "folio": s_["folio"], "titulo": s_["titulo"],
        "estatus": prog["estatus"],
        "equipos": len(s_["equipos"]),
        "dias": sum(len(e["jornadas"]) for e in s_["equipos"]),
        "ciudades": len({e.get("ciudad_id") for e in s_["equipos"]}),
        "falta": "; ".join(prog["faltantes"]) or "—",
        "falta_recurso": "; ".join(prog["faltantes_de_recursos"]) or "—",
        "recursos": "completos" if prog["recursos_completos"] else "faltan",
        "viaticos": f"{propuesto:,.0f} {moneda}",
        "task_sheet": publicado,
    })

# ------------------------------------------------------------- la tabla

print("\n" + "=" * 112)
print(f"{'FOLIO':<10} {'PROYECTO':<26} {'ESTATUS':<11} {'EQ':<3} {'DIAS':<5} "
      f"{'CIU':<4} {'RECURSOS':<10} {'VIATICOS':<14} {'TASK SHEET':<12}")
print("-" * 112)
for f in filas:
    print(f"{f['folio']:<10} {f['titulo']:<26} {f['estatus']:<11} "
          f"{f['equipos']:<3} {f['dias']:<5} {f['ciudades']:<4} "
          f"{f['recursos']:<10} {f['viaticos']:<14} {f['task_sheet']:<12}")
print("=" * 112)

for etiqueta, llave in (("Lo que les falta para quedar planeados", "falta"),
                        ("Lo que les falta de recursos", "falta_recurso")):
    pendientes = [f for f in filas if f[llave] != "—"]
    if pendientes:
        print(f"\n{etiqueta}:")
        for f in pendientes:
            print(f"   {f['folio']}: {f[llave]}")

print(f"\n{len(filas)} servicios · "
      f"{sum(f['equipos'] for f in filas)} equipos · "
      f"{sum(f['dias'] for f in filas)} dias · "
      f"{sum(1 for f in filas if f['task_sheet'] not in ('—', 'no'))} publicados")

if problemas:
    print(f"\n{len(problemas)} cosas que no cuadraron:")
    for p in problemas:
        print(f"   · {p}")
else:
    print("\nTodo en orden.")

print("\nRecarga la consola para verlos.")

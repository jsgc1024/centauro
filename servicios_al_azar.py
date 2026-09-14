#!/usr/bin/env python3
"""Eventuales al azar, para ver si todo sigue en orden.

    python3 servicios_al_azar.py          diez, distintos cada vez
    python3 servicios_al_azar.py 20       veinte
    python3 servicios_al_azar.py 20 4177  veinte, repitiendo esa corrida

Arma servicios que no se parecen entre si —transfer de aeropuerto,
full day de varios dias, medio dia, proyecto de dos ciudades, dias
todavia sin direccion— y despues los recorre de principio a fin: que le
falta a cada uno, a quien recomienda el sistema, se lo asigna, revisa
los viaticos que propone, arma el task sheet y lo publica.

Al final imprime la tabla y lo que no cuadro. No borra nada: cada
corrida agrega servicios nuevos a los que ya estan.
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

CUANTOS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
SEMILLA = int(sys.argv[2]) if len(sys.argv) > 2 else random.randrange(10_000)
rng = random.Random(SEMILLA)

# Lo que no cuadro. Se junta todo y se dice al final, en vez de cortar la
# corrida en el primer tropiezo: queremos ver los diez.
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

mx = next(p for p in paises if p["codigo"] in ("MX", "MEX"))
ciudades = [p for p in plazas if p["pais_id"] == mx["id"]]
por_ciudad = {p["nombre"]: p for p in ciudades}
mods = {m["codigo"]: m for m in modalidades if m["pais_id"] == mx["id"]}

if not clientes or not ciudades or not mods:
    print("Faltan catalogos. Corre primero  python3 alta_personal.py  "
          "o siembra los catalogos.")
    sys.exit(1)

CDMX = por_ciudad.get("Ciudad de Mexico") or ciudades[0]


_, gente = pedir("GET", "/catalogos/personal", token=h)
_, flota = pedir("GET", "/catalogos/vehiculos", token=h)

nombre_ciudad = {p["id"]: p["nombre"] for p in plazas}
nombre_perfil = {p["id"]: p["nombre"] for p in perfiles}
nombre_categoria = {c["id"]: c["nombre"] for c in categorias}

# Quien cubre un servicio. Un coordinador no cubre.
DE_SEGURIDAD = ("conductor_seguridad", "agente_seguridad")
PERFILES_SEGURIDAD = [p["id"] for p in perfiles
                      if p["codigo"] in DE_SEGURIDAD] or [p["id"] for p in perfiles]


def cuenta_por(coleccion, plaza_id, llave):
    cuenta = {}
    for x in coleccion:
        if x.get("plaza_id") == plaza_id:
            cuenta[x[llave]] = cuenta.get(x[llave], 0) + 1
    return cuenta


def categorias_de(plaza_id):
    """Las categorias que de verdad hay en esa ciudad, de la mas surtida a
    la menos. Pedir recomendaciones de una categoria que ahi no existe
    contesta 'no hay nada' y no es que no haya: es que se pregunto mal."""
    cuenta = cuenta_por(flota, plaza_id, "categoria_id")
    orden = [c for c, _ in sorted(cuenta.items(), key=lambda kv: -kv[1])]
    return orden + [c["id"] for c in categorias if c["id"] not in cuenta]


def perfiles_de(plaza_id):
    cuenta = cuenta_por([p for p in gente if p["perfil_id"] in PERFILES_SEGURIDAD],
                        plaza_id, "perfil_id")
    orden = [p for p, _ in sorted(cuenta.items(), key=lambda kv: -kv[1])]
    return orden + [p for p in PERFILES_SEGURIDAD if p not in cuenta]


def inventario():
    """Lo que hay antes de empezar. Si la casa esta vacia, los diez
    servicios van a salir sin recursos y no es culpa del sistema."""
    print("Lo que hay en casa")
    donde = sorted({x["plaza_id"] for x in gente} | {v["plaza_id"] for v in flota})
    for plaza_id in donde:
        suyos = [x for x in gente if x["plaza_id"] == plaza_id]
        unidades = [v for v in flota if v["plaza_id"] == plaza_id]
        seguridad = [x for x in suyos if x["perfil_id"] in PERFILES_SEGURIDAD]
        detalle = ", ".join(
            f"{n} {nombre_categoria.get(c, '?')}"
            for c, n in sorted(cuenta_por(unidades, plaza_id,
                                          "categoria_id").items(),
                               key=lambda kv: -kv[1])) or "ninguna"
        print(f"   {nombre_ciudad.get(plaza_id, '?'):<20} "
              f"{len(seguridad)} de seguridad de {len(suyos)} personas · "
              f"{len(unidades)} unidades ({detalle})")
    print()

# ------------------------------------------------------------- los puntos

# Puntos reales de la ciudad, con su pin. El aeropuerto se marca aparte
# porque dispara la geocerca de dos kilometros y los cien de
# estacionamiento por cada vuelta.
PUNTOS = [
    {"nombre": "aeropuerto", "aeropuerto": True,
     "origen_direccion": "Aeropuerto Internacional Benito Juarez, Terminal 2 "
                         "- salida de aduana",
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
    # Escrito a mano, sin pin: pasa, y el task sheet tiene que decirlo.
    {"nombre": "sin pin",
     "origen_direccion": "Domicilio particular en Lomas de Chapultepec, "
                         "lo confirma el ejecutivo"},
    # Ni direccion: el conductor le pregunta al ejecutivo un dia antes.
    {"nombre": "por confirmar"},
]

MONTERREY = {
    "origen_direccion": "Hotel Habita MTY, Vasconcelos 209, San Pedro",
    "origen_lat": "25.6540", "origen_lon": "-100.3620",
    "geocerca_metros": 500,
}

NOMBRES = ["Karen Whitfield", "James Caldwell", "Helen Voss",
           "Patricia Lundgren", "Ingrid Halvorsen", "Robert Sandoval",
           "Marta Oliveira", "Andrew Keene", "Sofia Marchetti",
           "Daniel Okonkwo", "Claire Bennet", "Thomas Nakamura"]

TITULOS = [
    "Transfer de llegada", "Transfer de salida", "Full day de un dia",
    "Full day de tres dias", "Medio dia", "Semana completa",
    "Dos ciudades", "Dos equipos misma ciudad", "Agenda por confirmar",
    "Madrugada con traslado",
]


def persona_al_azar():
    nombre, apellidos = rng.choice(NOMBRES).split(" ", 1)
    return nombre, apellidos


def dia(cuando, modalidad, punto, hora=None, vuelo=False):
    """Un dia del servicio. El punto puede venir completo, a medias o vacio."""
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
        j.update({"vuelo_aerolinea": rng.choice(["United", "Aeromexico",
                                                 "Delta", "LATAM"]),
                  "vuelo_numero": f"{rng.choice(['UA', 'AM', 'DL'])} "
                                  f"{rng.randrange(100, 1999)}",
                  "vuelo_origen": rng.choice(["Houston", "Bogota", "Madrid",
                                              "Sao Paulo"]),
                  "vuelo_tipo": "llegada",
                  "vuelo_hora": f"{cuando}T{rng.randrange(7, 21):02d}:"
                                f"{rng.choice(['05', '20', '40', '55'])}:00"})
    return j


def punto_al_azar(con_pin=True):
    opciones = [p for p in PUNTOS if not con_pin or p.get("origen_lat")]
    return rng.choice(opciones)


def armar(indice):
    """Diez formas distintas de pedir un servicio.

    Si se piden mas de diez se vuelve a dar la vuelta a la lista, pero
    ninguno sale igual: cambian las fechas, la gente, el punto y el
    vuelo. Al repetido se le pone el numero de vuelta para poder
    distinguirlos en la tabla.
    """
    vuelta, posicion = divmod(indice, len(TITULOS))
    titulo = TITULOS[posicion] + ("" if vuelta == 0 else f" ({vuelta + 1})")
    inicio = HOY + timedelta(days=rng.randrange(2, 25))
    nombre, apellidos = persona_al_azar()
    sol_nombre, sol_apellidos = persona_al_azar()

    base = {
        "titulo": titulo,
        "solicitante_nombre": sol_nombre,
        "solicitante_apellidos": sol_apellidos,
        "solicitante_correo": f"{sol_nombre.lower()}.{sol_apellidos.lower()}"
                              f"@cliente.com",
        "solicitante_telefono": f"+52 55 {rng.randrange(1000, 9999)} "
                                f"{rng.randrange(1000, 9999)}",
        "ejecutivo_nombre": nombre, "ejecutivo_apellidos": apellidos,
        "ejecutivo_correo": f"{nombre.lower()}@ejecutivo.com",
        "ejecutivo_telefono": f"+1 713 555 {rng.randrange(1000, 9999)}",
        "plaza_id": CDMX["id"],
    }
    aeropuerto = PUNTOS[0]

    titulo_base = TITULOS[posicion]
    if titulo_base == "Transfer de llegada":
        base["equipos"] = [{"jornadas": [
            dia(inicio, "transfer", aeropuerto, "13:05:00", vuelo=True)]}]

    elif titulo_base == "Transfer de salida":
        base["equipos"] = [{"jornadas": [
            dia(inicio, "transfer", punto_al_azar(), "16:30:00")]}]

    elif titulo_base == "Full day de un dia":
        base["equipos"] = [{"jornadas": [
            dia(inicio, "full_day", punto_al_azar(), "08:00:00")]}]

    elif titulo_base == "Full day de tres dias":
        punto = punto_al_azar()
        base["equipos"] = [{"jornadas": [
            dia(inicio + timedelta(days=n), "full_day", punto, "08:00:00")
            for n in range(3)]}]

    elif titulo_base == "Medio dia":
        base["equipos"] = [{"jornadas": [
            dia(inicio, "medio_dia", punto_al_azar(), "09:00:00")]}]

    elif titulo_base == "Semana completa":
        punto = punto_al_azar()
        base["equipos"] = [{"jornadas": [
            dia(inicio + timedelta(days=n), "full_day", punto, "07:45:00")
            for n in range(5)]}]

    elif titulo_base == "Dos ciudades":
        mty = por_ciudad.get("Monterrey")
        alfa = {"jornadas": [
            dia(inicio, "transfer", aeropuerto, "09:15:00", vuelo=True),
            dia(inicio + timedelta(days=1), "full_day", PUNTOS[1], "08:00:00")]}
        beta = {"jornadas": [
            dia(inicio + timedelta(days=2), "full_day", MONTERREY, "08:00:00"),
            dia(inicio + timedelta(days=3), "transfer", MONTERREY, "17:00:00")]}
        if mty:
            beta["plaza_id"] = mty["id"]
        base["equipos"] = [alfa, beta]

    elif titulo_base == "Dos equipos misma ciudad":
        otro_nombre, otro_apellidos = persona_al_azar()
        base["equipos"] = [
            {"jornadas": [dia(inicio, "full_day", PUNTOS[1], "08:00:00")]},
            {"ejecutivo_nombre": otro_nombre,
             "ejecutivo_apellidos": otro_apellidos,
             "jornadas": [dia(inicio, "full_day", PUNTOS[2], "08:00:00")]}]

    elif titulo_base == "Agenda por confirmar":
        # El cliente no dio la agenda: el dia 1 con punto y los demas en
        # blanco, que es como llega de verdad.
        base["equipos"] = [{"jornadas": [
            dia(inicio, "full_day", PUNTOS[1], "08:00:00"),
            dia(inicio + timedelta(days=1), "full_day", PUNTOS[5]),
            dia(inicio + timedelta(days=2), "full_day", PUNTOS[5])]}]

    else:  # Madrugada con traslado
        # Antes de las 6:30 el tabulador paga el traslado del personal.
        base["equipos"] = [{"jornadas": [
            dia(inicio, "full_day", aeropuerto, "05:30:00", vuelo=True),
            dia(inicio + timedelta(days=1), "full_day", PUNTOS[1], "06:00:00")]}]

    return base


# ------------------------------------------------------------ dar de alta

print(f"Semilla {SEMILLA} — repite esta misma corrida con "
      f"python3 servicios_al_azar.py {CUANTOS} {SEMILLA}\n")
inventario()
print("Dando de alta")

creados = []
for i in range(CUANTOS):
    datos = armar(i)
    titulo = datos.pop("titulo")
    codigo, r = pedir("POST", "/servicios", {
        "cliente_id": rng.choice(clientes)["id"], "pais_id": mx["id"],
        "tipo": "eventual", **datos}, token=h)
    if codigo != 201:
        problemas.append(f"alta de '{titulo}': {codigo} {r}")
        print(f"   ✗ {titulo:<26} {codigo} {r}")
        continue
    dias = sum(len(e["jornadas"]) for e in r["equipos"])
    print(f"   {r['folio']:<10} {titulo:<26} "
          f"{len(r['equipos'])} equipo(s), {dias} dia(s)")
    creados.append({"titulo": titulo, **r})

if not creados:
    print("\nNo se creo ninguno. Revisa la consola del api.")
    sys.exit(1)

# --------------------------------------------------------- asignar equipo

print("\nAsignando personal y unidad")


def elegir(bloque):
    """El primero que se pueda: libre, con alerta, o de otra ciudad.

    El de otra ciudad no es un error —se traslada y genera viaticos
    foraneos—, pero se dice, porque encarece el servicio.
    """
    for grupo in ("disponibles", "con_alerta"):
        if bloque.get(grupo):
            return bloque[grupo][0], grupo
    for ficha in bloque.get("de_otras_ciudades") or []:
        if not ficha["bloqueado"]:
            return ficha, "de_otras_ciudades"
    return None, None


def buscar(eid, ciudad_id):
    """Se pregunta por perfil y categoria, y hay varias de cada uno.

    Se recorren de la mas surtida a la menos hasta encontrar quien y con
    que: preguntar una sola vez por la categoria equivocada contesta que
    no hay flota cuando la flota esta ahi.
    """
    persona = unidad = None
    origen_p = origen_v = None
    for perfil_id in perfiles_de(ciudad_id):
        for categoria_id in categorias_de(ciudad_id):
            codigo, rec = pedir(
                "GET", f"/servicios/equipos/{eid}/recomendaciones"
                       f"?perfil_id={perfil_id}&categoria_id={categoria_id}",
                token=h)
            if codigo != 200:
                return None, None, None, None, f"recomendaciones {codigo} {rec}"
            if not persona:
                persona, origen_p = elegir(rec["personal"])
            if not unidad:
                unidad, origen_v = elegir(rec["vehiculos"])
            if persona and unidad:
                return persona, unidad, origen_p, origen_v, None
    return persona, unidad, origen_p, origen_v, None


for s_ in creados:
    notas = []
    for equipo in s_["equipos"]:
        eid = equipo["id"]
        ciudad_id = equipo.get("ciudad_id") or CDMX["id"]
        ciudad = nombre_ciudad.get(ciudad_id, "?")
        persona, unidad, origen_p, origen_v, error = buscar(eid, ciudad_id)

        if error:
            problemas.append(f"{s_['folio']} {equipo['alias']}: {error}")
            continue

        if persona:
            codigo, r = pedir(
                "POST", f"/servicios/equipos/{eid}/asignar-personal",
                {"persona_id": persona["persona_id"], "forzar": True}, token=h)
            if codigo >= 400:
                problemas.append(f"{s_['folio']} {equipo['alias']}: "
                                 f"asignar personal {codigo} {r}")
            elif origen_p != "disponibles":
                notas.append(f"{equipo['alias']}: {persona.get('nombre', '')} "
                             f"entra {origen_p.replace('_', ' ')}")
        else:
            cuantos = len([x for x in gente
                           if x["plaza_id"] == ciudad_id
                           and x["perfil_id"] in PERFILES_SEGURIDAD])
            problemas.append(
                f"{s_['folio']} {equipo['alias']}: nadie de seguridad libre "
                f"para esos dias en {ciudad} ({cuantos} en el catalogo)")

        if unidad:
            codigo, r = pedir(
                "POST", f"/servicios/equipos/{eid}/asignar-vehiculo",
                {"vehiculo_id": unidad["vehiculo_id"], "forzar": True},
                token=h)
            if codigo >= 400:
                problemas.append(f"{s_['folio']} {equipo['alias']}: "
                                 f"asignar unidad {codigo} {r}")
            elif origen_v != "disponibles":
                notas.append(f"{equipo['alias']}: {unidad.get('placa', '')} "
                             f"entra {origen_v.replace('_', ' ')}")
        else:
            cuantas = len([v for v in flota if v["plaza_id"] == ciudad_id])
            problemas.append(
                f"{s_['folio']} {equipo['alias']}: ninguna unidad libre "
                f"para esos dias en {ciudad} ({cuantas} en la flota)")

    print(f"   {s_['folio']:<10} {s_['titulo']:<26} "
          + ("; ".join(notas) if notas else ""))

# ----------------------------------------------------------- que quedo

print("\nRevisando")

filas = []
for s_ in creados:
    codigo, prog = pedir("GET", f"/servicios/{s_['id']}/programacion", token=h)
    if codigo != 200:
        problemas.append(f"{s_['folio']}: programacion {codigo} {prog}")
        continue

    # Viaticos: lo que el tabulador propone para el equipo.
    propuesto, moneda = 0, ""
    for equipo in s_["equipos"]:
        codigo, panel = pedir("GET", f"/viaticos/equipos/{equipo['id']}",
                              token=h)
        if codigo != 200:
            problemas.append(f"{s_['folio']} {equipo['alias']}: "
                             f"viaticos {codigo} {panel}")
            continue
        propuesto += float(panel["total_propuesto"] or 0)
        moneda = panel["moneda"] or ""

    # Task sheet: se confirma la asignacion y se publica.
    publicado = "—"
    if prog["recursos_completos"]:
        pedir("POST", f"/servicios/{s_['id']}/confirmar-asignacion", token=h)
        codigo, r = pedir("POST", f"/task-sheets/servicio/{s_['id']}/publicar",
                          {"motivo": "prueba automatica", "forzar": False},
                          token=h)
        if codigo == 200:
            hojas = r if isinstance(r, list) else [r]
            publicado = f"v{hojas[0].get('version', 1)}"
        else:
            detalle = r.get("detail", r) if isinstance(r, dict) else r
            publicado = "no"
            problemas.append(f"{s_['folio']}: publicar {codigo} {detalle}")

    filas.append({
        "folio": s_["folio"], "titulo": s_["titulo"],
        "estatus": prog["estatus"],
        "equipos": len(s_["equipos"]),
        "dias": sum(len(e["jornadas"]) for e in s_["equipos"]),
        "falta": "; ".join(prog["faltantes"]) or "—",
        "recursos": "completos" if prog["recursos_completos"] else "faltan",
        "falta_recurso": "; ".join(prog["faltantes_de_recursos"]) or "—",
        "viaticos": f"{propuesto:,.0f} {moneda}",
        "task_sheet": publicado,
    })

# ------------------------------------------------------------- la tabla

print("\n" + "=" * 108)
print(f"{'FOLIO':<10} {'QUE ES':<26} {'ESTATUS':<11} {'EQ':<3} {'DIAS':<5} "
      f"{'RECURSOS':<10} {'VIATICOS':<14} {'TS':<5}")
print("-" * 108)
for f in filas:
    print(f"{f['folio']:<10} {f['titulo']:<26} {f['estatus']:<11} "
          f"{f['equipos']:<3} {f['dias']:<5} {f['recursos']:<10} "
          f"{f['viaticos']:<14} {f['task_sheet']:<5}")
print("=" * 108)

pendientes = [f for f in filas if f["falta"] != "—"]
if pendientes:
    print("\nLo que les falta para quedar planeados:")
    for f in pendientes:
        print(f"   {f['folio']}: {f['falta']}")

sin_recursos = [f for f in filas if f["falta_recurso"] != "—"]
if sin_recursos:
    print("\nLo que les falta de recursos:")
    for f in sin_recursos:
        print(f"   {f['folio']}: {f['falta_recurso']}")

print(f"\n{len(filas)} servicios · "
      f"{sum(1 for f in filas if f['task_sheet'].startswith('v'))} con task "
      f"sheet publicado")

if problemas:
    print(f"\n{len(problemas)} cosas que no cuadraron:")
    for p in problemas:
        print(f"   · {p}")
else:
    print(f"\nTodo en orden: ni un error en {len(filas)}.")

print("\nRecarga la consola para verlos.")

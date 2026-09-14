#!/usr/bin/env python3
"""Llena la casa: personal de seguridad y unidades, para tener con que probar.

    python3 sembrar_flota.py

Deja veinticuatro personas de seguridad y diecinueve unidades repartidas
en Ciudad de Mexico, Monterrey y Guadalajara. Es gente y flota de
prueba, no la real: sirve para que la asignacion de recursos tenga de
donde escoger y se puedan ver los empalmes, las alertas y los traslados
entre ciudades.

Se puede correr las veces que haga falta: a quien ya existe no lo
duplica, y la unidad que ya tiene esa placa se queda como esta.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"

# ------------------------------------------------------------- la gente

# Nombre, perfil y ciudad. El correo y el telefono se arman solos.
# Mas conductores que agentes: asi es la operacion, y el conductor es el
# que amarra la unidad.
GENTE = [
    # Ciudad de Mexico: el grueso
    ("Ernesto Vidal", "conductor_seguridad", "Ciudad de Mexico"),
    ("Ruben Alcantara", "conductor_seguridad", "Ciudad de Mexico"),
    ("Hector Barajas", "conductor_seguridad", "Ciudad de Mexico"),
    ("Javier Pineda", "conductor_seguridad", "Ciudad de Mexico"),
    ("Omar Trevino", "conductor_seguridad", "Ciudad de Mexico"),
    ("Ivan Rosales", "conductor_seguridad", "Ciudad de Mexico"),
    ("Gerardo Munoz", "conductor_seguridad", "Ciudad de Mexico"),
    ("Sergio Renteria", "conductor_seguridad", "Ciudad de Mexico"),
    ("Fernando Aguilar", "conductor_seguridad", "Ciudad de Mexico"),
    ("Arturo Cisneros", "conductor_seguridad", "Ciudad de Mexico"),
    ("Daniela Ibarra", "agente_seguridad", "Ciudad de Mexico"),
    ("Paulina Esquivel", "agente_seguridad", "Ciudad de Mexico"),
    ("Rodrigo Salas", "agente_seguridad", "Ciudad de Mexico"),
    ("Karla Montiel", "agente_seguridad", "Ciudad de Mexico"),
    ("Adrian Ferrer", "agente_seguridad", "Ciudad de Mexico"),
    # Monterrey
    ("Marco Zepeda", "conductor_seguridad", "Monterrey"),
    ("Luis Cantu", "conductor_seguridad", "Monterrey"),
    ("Roberto Elizondo", "conductor_seguridad", "Monterrey"),
    ("Cesar Villarreal", "conductor_seguridad", "Monterrey"),
    ("Monica Garza", "agente_seguridad", "Monterrey"),
    # Guadalajara
    ("Emilio Zamora", "conductor_seguridad", "Guadalajara"),
    ("Alfonso Beltran", "conductor_seguridad", "Guadalajara"),
    ("Victor Padilla", "conductor_seguridad", "Guadalajara"),
    ("Lorena Ceballos", "agente_seguridad", "Guadalajara"),
]

LADA = {"Ciudad de Mexico": "55", "Monterrey": "81", "Guadalajara": "33"}

# ------------------------------------------------------------- la flota

# Placa, marca y modelo, color, anio, categoria y ciudad. La categoria es
# la de Centauro —SUV, CUV, minivan, van— y no la marca: el mismo
# servicio se cubre con la SUV que haya. Cada ciudad lleva de varias para
# que el consultor pueda escoger y no se quede trabado con una sola.
UNIDADES = [
    ("CTR-101-A", "Chevrolet Suburban", "Negro", 2024, "suv", "Ciudad de Mexico"),
    ("CTR-102-A", "Chevrolet Suburban", "Negro", 2023, "suv", "Ciudad de Mexico"),
    ("CTR-103-A", "Chevrolet Tahoe", "Gris Oxford", 2024, "suv", "Ciudad de Mexico"),
    ("CTR-104-A", "Chevrolet Tahoe", "Negro", 2025, "suv", "Ciudad de Mexico"),
    ("CTR-105-A", "Chevrolet Suburban", "Negro", 2024, "suv_blindada",
     "Ciudad de Mexico"),
    ("CTR-106-A", "Toyota Highlander", "Negro", 2024, "cuv", "Ciudad de Mexico"),
    ("CTR-107-A", "Honda CR-V", "Plata", 2023, "cuv", "Ciudad de Mexico"),
    ("CTR-108-A", "Toyota Sienna", "Gris", 2024, "minivan", "Ciudad de Mexico"),
    ("CTR-109-A", "Chrysler Pacifica", "Negro", 2023, "minivan_blindada",
     "Ciudad de Mexico"),
    ("CTR-110-A", "Mercedes Sprinter", "Blanco", 2023, "van_10",
     "Ciudad de Mexico"),
    ("CTR-201-B", "Chevrolet Suburban", "Negro", 2024, "suv", "Monterrey"),
    ("CTR-202-B", "Chevrolet Tahoe", "Blanco", 2023, "suv", "Monterrey"),
    ("CTR-203-B", "Chevrolet Suburban", "Negro", 2023, "suv_blindada",
     "Monterrey"),
    ("CTR-204-B", "Toyota Highlander", "Gris", 2023, "cuv", "Monterrey"),
    ("CTR-205-B", "Toyota Sienna", "Negro", 2024, "minivan", "Monterrey"),
    ("CTR-301-C", "Chevrolet Suburban", "Negro", 2023, "suv", "Guadalajara"),
    ("CTR-302-C", "Chevrolet Tahoe", "Gris", 2024, "suv", "Guadalajara"),
    ("CTR-303-C", "Toyota Highlander", "Negro", 2022, "cuv", "Guadalajara"),
    ("CTR-304-C", "Toyota Sienna", "Plata", 2024, "minivan", "Guadalajara"),
]

COSTO = {"suv": "2600", "suv_blindada": "4200", "cuv": "1900",
         "minivan": "1700", "minivan_blindada": "3600", "van_10": "2200"}


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


def correo_de(nombre):
    partes = nombre.lower().replace("í", "i").replace("é", "e").split()
    return f"{partes[0]}.{partes[-1]}@centauro.lat"


h = entrar("admin@centauro.lat")

_, perfiles = pedir("GET", "/catalogos/perfiles", token=h)
_, paises = pedir("GET", "/catalogos/paises", token=h)
_, plazas = pedir("GET", "/catalogos/plazas?todas=true", token=h)
_, categorias = pedir("GET", "/catalogos/categorias-vehiculo", token=h)
_, personal = pedir("GET", "/catalogos/personal?limite=500", token=h)
_, flota = pedir("GET", "/catalogos/vehiculos?limite=500", token=h)

if not perfiles or not categorias:
    print("Faltan los catalogos base. Siembra primero los catalogos.")
    sys.exit(1)

mx = next(p for p in paises if p["codigo"] in ("MX", "MEX"))
por_codigo = {p["codigo"]: p for p in perfiles}
por_ciudad = {p["nombre"]: p for p in plazas if p["pais_id"] == mx["id"]}

# --------------------------------------------------------- las ciudades

# Una ciudad donde no se ha trabajado todavia no esta en el catalogo. Se
# da de alta aqui para poder poner gente en ella.
print("Ciudades")
for ciudad in ("Ciudad de Mexico", "Monterrey", "Guadalajara"):
    if ciudad in por_ciudad:
        print(f"   ya estaba: {ciudad}")
        continue
    codigo, r = pedir("POST", "/catalogos/plazas",
                      {"nombre": ciudad, "pais_id": mx["id"]}, token=h)
    if codigo == 201:
        por_ciudad[ciudad] = r
        print(f"   alta: {ciudad}")
    else:
        print(f"   no se pudo dar de alta {ciudad}: {r}")

# ------------------------------------------------------------- personal

print("\nPersonal de seguridad")
ya_estan = {p["correo"] for p in personal}
nuevos, repetidos = [], 0

for nombre, perfil, ciudad in GENTE:
    correo = correo_de(nombre)
    if correo in ya_estan:
        repetidos += 1
        continue
    lugar = por_ciudad.get(ciudad)
    if not lugar or perfil not in por_codigo:
        print(f"   falta el catalogo para {nombre} ({perfil}, {ciudad})")
        continue

    codigo, r = pedir("POST", "/catalogos/personal", {
        "nombre": nombre, "correo": correo,
        "perfil_id": por_codigo[perfil]["id"], "plaza_id": lugar["id"],
    }, token=h)
    if codigo != 201:
        print(f"   no se pudo dar de alta a {nombre}: {r}")
        continue
    print(f"   alta: {nombre:<22} {por_codigo[perfil]['nombre']:<24} {ciudad}")
    nuevos.append((correo, ciudad))

if repetidos:
    print(f"   ({repetidos} ya estaban)")

# El telefono viene de Odoo, no del alta del catalogo. Entra por la misma
# puerta por la que entrara el dia que se conecte de verdad.
if nuevos:
    lote = []
    for i, (correo, ciudad) in enumerate(nuevos):
        lada = LADA.get(ciudad, "55")
        lote.append({"correo": correo,
                     "telefono": f"{lada} {4000 + i * 7} {1100 + i * 13}"})
    codigo, r = pedir("POST", "/odoo/personal", lote, token=h)
    print(f"   telefonos desde Odoo: {r if codigo == 200 else codigo}")

# ---------------------------------------------------------------- flota

print("\nFlota")
placas = {v["placa"].upper() for v in flota}
altas, ya = 0, 0

por_categoria = {c["codigo"]: c for c in categorias}

for placa, modelo, color, anio, cat, ciudad in UNIDADES:
    if placa in placas:
        ya += 1
        continue
    lugar = por_ciudad.get(ciudad)
    categoria = por_categoria.get(cat) or categorias[0]
    if not lugar:
        print(f"   no hay ciudad para {placa} ({ciudad})")
        continue

    codigo, r = pedir("POST", "/catalogos/vehiculos", {
        "placa": placa, "categoria_id": categoria["id"],
        "plaza_id": lugar["id"], "marca_modelo": modelo, "color": color,
        "modelo_anio": anio, "costo_diario": COSTO.get(cat, "1500"),
    }, token=h)
    if codigo != 201:
        print(f"   no se pudo dar de alta {placa}: {r}")
        continue
    print(f"   alta: {placa:<12} {modelo:<22} "
          f"{categoria['nombre']:<16} {ciudad}")
    altas += 1

if ya:
    print(f"   ({ya} ya estaban)")

# -------------------------------------------------------------- resumen

_, personal = pedir("GET", "/catalogos/personal?limite=500", token=h)
_, flota = pedir("GET", "/catalogos/vehiculos?limite=500", token=h)

nombre_ciudad = {p["id"]: p["nombre"] for p in plazas}
nombre_perfil = {p["id"]: p["nombre"] for p in perfiles}
nombre_categoria = {c["id"]: c["nombre"] for c in categorias}
seguridad = {por_codigo[c]["id"] for c in ("conductor_seguridad",
                                           "agente_seguridad")
             if c in por_codigo}

print("\n" + "=" * 76)
print(f"{'CIUDAD':<20} {'SEGURIDAD':<12} {'UNIDADES':<10} DETALLE")
print("-" * 76)
for plaza_id in sorted({p["plaza_id"] for p in personal}
                       | {v["plaza_id"] for v in flota}):
    suyos = [p for p in personal if p["plaza_id"] == plaza_id
             and p["perfil_id"] in seguridad]
    unidades = [v for v in flota if v["plaza_id"] == plaza_id]
    cuenta = {}
    for v in unidades:
        llave = nombre_categoria.get(v["categoria_id"], "?")
        cuenta[llave] = cuenta.get(llave, 0) + 1
    detalle = ", ".join(f"{n} {c}" for c, n in
                        sorted(cuenta.items(), key=lambda kv: -kv[1])) or "—"
    print(f"{nombre_ciudad.get(plaza_id, '?'):<20} {len(suyos):<12} "
          f"{len(unidades):<10} {detalle}")
print("=" * 76)

print(f"\n{len(personal)} personas y {len(flota)} unidades en el catalogo.")
print("Ahora corre  python3 servicios_al_azar.py 20")

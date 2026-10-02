# -*- coding: utf-8 -*-
"""Las reglas de la flota y del taller que vienen de Odoo, sin base de datos.

Aqui se decide que hacer con cada unidad y con cada entrada al taller a
partir de fotos fijas de Odoo y de Centauro. No lee ni escribe nada: por
eso se prueba sola, y el ensayo y la lectura de verdad deciden lo mismo.

Las decisiones de Salvador (23 de septiembre) que viven aqui:

  * Entran las unidades de Proteccion Ejecutiva: las que traen la
    etiqueta «PROTECCION EJECUTIVA» o «pe». Logistica, Direccion y las
    utilitarias no.
  * Y por pais (1 de octubre, seccion 118): Mexico es la compania
    CENTAURO ASS con esa etiqueta; Brasil, la compania Centauro Brasil con
    «PROTECCION EJECUTIVA BRASIL». Nunca se mezclan: la etiqueta de un
    pais con la compania de otro no entra en ninguna flota.
  * La etiqueta se reconoce por su numero en Odoo (seccion 121): la de
    Mexico es la 3 y la de Brasil la 5, se llamen como se llamen. Asi la
    de Mexico se puede renombrar «PROTECCION EJECUTIVA MEXICO» sin que la
    flota salga de Connect. Su nombre sigue valiendo de respaldo.
  * La llave es el numero interno de Odoo; la primera vez se vincula por
    placa con la que ya estaba en Centauro.
  * Las categorias de Odoo son las de Centauro --con la CUV Blindada de
    Brasil desde la seccion 118--. VAN es la «Van 10 pax».
  * La plaza sale de la Ubicacion de la unidad, entre las ciudades de su
    pais. El Estado de Mexico va como Ciudad de Mexico. En Brasil la
    unidad entra aunque no la tenga: se captura despues.
  * El taller: Preventivo, Correctivo y Desgaste natural sacan la unidad
    de circulacion, de la fecha de entrada a la de salida; sin salida se
    da por adentro. «Resguardo de Unidad» y los de contrato no cuentan.
  * Lo dudoso no se adivina: se reporta como pendiente y no se toca.
"""
import collections
import re

from app.odoo_api import COMPANIAS
from app.odoo_personal_reglas import (buscar_plaza, corto, fecha, nombre_de,
                                      normal, texto)

# Que unidades de Odoo son la flota de cada pais (decision de Salvador,
# 1 de octubre; seccion 118). En Odoo cada pais es una compania y su flota
# lleva su etiqueta. La unidad es de la flota cuya compania Y cuya etiqueta
# trae: con una sola de las dos no es de ninguna, y se reporta en vez de
# adivinar. Asi una unidad de Brasil nunca cae en la flota de Mexico, ni al
# reves.
#
# `ciudad_obligatoria`: en Mexico la unidad sin Ubicacion no entra (23 de
# septiembre). La flota de Brasil llega a Odoo sin VIN, color ni Ubicacion,
# que se capturan despues: entra igual, y lo que le falta se dice aparte,
# como por capturar, sin detener nada. Connect no lee el VIN.
#
# `etiqueta`: el numero de su etiqueta en fleet.vehicle.tag (seccion 121).
# Manda el numero; los nombres de `etiquetas` son el respaldo, con el de
# Mexico de antes y el de despues del cambio.
FLOTAS = (
    {"pais": "MX", "nombre": "México", "compania": COMPANIAS["MX"],
     "etiqueta": 3,
     "etiquetas": frozenset({"proteccion ejecutiva",
                             "proteccion ejecutiva mexico", "pe"}),
     "ciudad_obligatoria": True},
    {"pais": "BR", "nombre": "Brasil", "compania": COMPANIAS["BR"],
     "etiqueta": 5,
     "etiquetas": frozenset({"proteccion ejecutiva brasil"}),
     "ciudad_obligatoria": False},
)
ETIQUETAS = frozenset().union(*(f["etiquetas"] for f in FLOTAS))
# El nombre de la categoria en Odoo, como codigo de Centauro. Lo que no
# esta aqui se toma tal cual: «MINIVAN BLINDADA» -> minivan_blindada.
ALIAS_CATEGORIA = {"van": "van_10"}
TALLER = {
    "preventivo": "mantenimiento_preventivo",
    "correctivo": "mantenimiento_correctivo",
    "desgaste natural": "mantenimiento_correctivo",
}


def id_de(valor):
    """El id de un many2one, venga como [id, nombre], dict o id."""
    if not valor:
        return None
    if isinstance(valor, (list, tuple)):
        return valor[0]
    if isinstance(valor, dict):
        return valor.get("id")
    return valor


def placa_de(valor) -> str:
    """La placa sin espacios ni guiones y en mayusculas: «ABC-1234» y
    «abc 1234» son la misma."""
    return re.sub(r"[^0-9A-Z]", "", texto(valor).upper())


def codigo_de_categoria(nombre: str) -> str:
    clave = normal(nombre).replace(" ", "_")
    return ALIAS_CATEGORIA.get(clave, clave)


def marca_modelo_de(valor) -> str:
    """«Toyota/SIENNA XSE» como se lee: «Toyota SIENNA XSE»."""
    return " ".join(nombre_de(valor).replace("/", " ").split())


def anio_de(valor) -> int | None:
    t = texto(valor)
    return int(t) if t.isdigit() and 1950 < int(t) < 2100 else None


# El color como se guarda la foto de la categoria: la primera palabra, sin
# acentos. «Blanco perla» y «BLANCO» son la misma foto blanca.
ALIAS_COLOR = {"plateado": "plata", "silver": "plata", "white": "blanco",
               "black": "negro", "gray": "gris", "grey": "gris",
               "blue": "azul", "red": "rojo"}


def color_de(valor) -> str:
    palabras = normal(valor).split()
    return ALIAS_COLOR.get(palabras[0], palabras[0]) if palabras else ""


def plaza_de(lugar, plazas: dict) -> tuple:
    """(plaza o None, lo que dice Odoo). `plazas` va por nombre normalizado.
    «Sao Paulo - Barueri» es Sao Paulo, como en el personal (seccion 121)."""
    lugar = texto(lugar)
    return buscar_plaza(lugar, plazas), lugar


def marcadas(unidad: dict, etiquetas: dict) -> list:
    """Las flotas cuya etiqueta trae la unidad: por su numero o, de
    respaldo, por su nombre. `etiquetas`: id -> nombre, de
    fleet.vehicle.tag."""
    ids = {id_de(t) for t in (unidad.get("tag_ids") or [])}
    nombres = {normal(etiquetas.get(t, "")) for t in ids}
    return [f for f in FLOTAS
            if f["etiqueta"] in ids or f["etiquetas"] & nombres]


def es_de_proteccion(unidad: dict, etiquetas: dict) -> bool:
    """Si trae la etiqueta de alguna de las flotas."""
    return bool(marcadas(unidad, etiquetas))


def etiquetas_de_las_flotas(etiquetas: dict) -> list:
    """Con que nombre esta hoy en Odoo la etiqueta de cada flota, por su
    numero (seccion 121). La que no existe se dice: esa flota solo se
    reconoce por el nombre, y renombrarla la sacaria de Connect."""
    return [{"pais": f["nombre"], "id": f["etiqueta"],
             "nombre": texto(etiquetas.get(f["etiqueta"])) or None}
            for f in FLOTAS]


def flota_de(unidad: dict, etiquetas: dict) -> tuple:
    """(flota, problema). La flota cuya compania y cuya etiqueta trae la
    unidad. Con la etiqueta de una flota y otra compania --o ninguna-- no
    es de ninguna: (None, por que). Sin etiqueta de Proteccion Ejecutiva
    no es asunto de Connect: (None, None)."""
    suyas = marcadas(unidad, etiquetas)
    if not suyas:
        return None, None
    compania = id_de(unidad.get("company_id"))
    for flota in suyas:
        if flota["compania"] == compania:
            return flota, None
    flota = suyas[0]
    if compania is None:
        return None, (f"la etiqueta es de «{flota['nombre']}» y en Odoo no "
                      "tiene compania")
    nombre = nombre_de(unidad.get("company_id")) or str(compania)
    return None, (f"la etiqueta es de «{flota['nombre']}» y su compania en "
                  f"Odoo es «{nombre}»")


def por_capturar(flota: dict, plaza, lugar: str, color, vehiculo) -> list:
    """Lo que a la unidad le falta en Odoo y no detiene nada (seccion 118):
    solo en la flota que entra sin ciudad. Lo que Centauro ya tiene no se
    pide: un campo vacio en Odoo no borra el de Centauro."""
    if flota["ciudad_obligatoria"]:
        return []
    vehiculo = vehiculo or {}
    falta = []
    if plaza is None:
        if lugar:
            falta.append(f"la ubicacion «{lugar}» no es una ciudad de "
                         f"«{flota['nombre']}» en Centauro")
        elif not vehiculo.get("plaza_id"):
            falta.append("sin ubicacion")
    if not color and not vehiculo.get("color"):
        falta.append("sin color")
    return falta


# ------------------------------------------------------------ las unidades

def planear(unidades: list, etiquetas: dict, vehiculos: list,
            categorias: dict, plazas: dict, paises: dict) -> dict:
    """Que hacer con cada unidad de Odoo, sin hacerlo.

    `unidades`: las activas de Odoo. `vehiculos`: foto fija de la flota
    propia de Centauro (sin las rentadas), con id, odoo_id, placa,
    categoria_id, plaza_id, pais_id (el de su ciudad, o el de su flota si
    no tiene), marca_modelo, color, modelo_anio, activo y sincronizado_en.
    `categorias`: por codigo, con id y nombre. `plazas`: por pais (su id) y
    nombre normalizado, con id y nombre. `paises`: por codigo, con id.
    """
    elegidas, mezcladas = [], []
    for u in unidades:
        flota, problema = flota_de(u, etiquetas)
        if flota is not None:
            elegidas.append((u, flota))
        elif problema:
            mezcladas.append((u, problema))
    por_odoo = {v["odoo_id"]: v for v in vehiculos if v.get("odoo_id")}
    por_placa = {placa_de(v["placa"]): v for v in vehiculos if v.get("placa")}
    cuenta = collections.Counter(placa_de(u.get("license_plate"))
                                 for u, _ in elegidas)
    repetidas = {p for p, n in cuenta.items() if p and n > 1}

    plan = {"leidas": len(elegidas),
            "por_pais": {f["pais"]: 0 for f in FLOTAS},
            "altas": [], "vinculos": [], "cambios": [], "pendientes": [],
            "por_capturar": [], "sin_cambio": 0, "procesadas": [],
            "revisar_salida": []}
    tomadas = set()

    def pendiente(u, vehiculo_id, faltas, flota=None):
        plan["pendientes"].append({"odoo_id": u["id"], "vehiculo_id": vehiculo_id,
                                   "placa": texto(u.get("license_plate")),
                                   "pais": flota["nombre"] if flota else None,
                                   "falta": faltas})

    def capturar(u, vehiculo_id, flota, faltas):
        if faltas:
            plan["por_capturar"].append({
                "odoo_id": u["id"], "vehiculo_id": vehiculo_id,
                "placa": texto(u.get("license_plate")),
                "pais": flota["nombre"], "falta": faltas})

    # La etiqueta de un pais con la compania de otro: no entra en ninguna
    # flota ni se toca la que ya estaba. Cuenta como vista, para que no se
    # tome por una salida de Proteccion Ejecutiva.
    for u, problema in mezcladas:
        ya = por_odoo.get(u["id"])
        pendiente(u, ya["id"] if ya else None, [problema])

    for u, flota in elegidas:
        plan["por_pais"][flota["pais"]] += 1
        pais = paises.get(flota["pais"])
        if pais is None:
            ya = por_odoo.get(u["id"])
            pendiente(u, ya["id"] if ya else None,
                      [f"el pais «{flota['pais']}» no existe en Centauro"], flota)
            continue
        placa = placa_de(u.get("license_plate"))
        nombre_cat = nombre_de(u.get("category_id"))
        categoria = (categorias.get(codigo_de_categoria(nombre_cat))
                     if nombre_cat else None)
        # La ciudad, entre las de su pais: «Guadalajara» en una unidad de
        # Brasil no la manda a Mexico.
        plaza, lugar = plaza_de(u.get("location"), plazas.get(pais["id"], {}))
        datos = {"marca_modelo": marca_modelo_de(u.get("model_id"))[:80].rstrip() or None,
                 "color": corto(u.get("color"), 40) or None,
                 "modelo_anio": anio_de(u.get("model_year"))}

        vehiculo, vinculo = por_odoo.get(u["id"]), False
        if vehiculo is None and placa and placa not in repetidas:
            candidato = por_placa.get(placa)
            if candidato is not None:
                if candidato.get("odoo_id") and candidato["odoo_id"] != u["id"]:
                    pendiente(u, candidato["id"],
                              ["su placa ya es de otra unidad en Centauro"], flota)
                    continue
                if candidato.get("pais_id") != pais["id"]:
                    pendiente(u, candidato["id"],
                              ["su placa ya es de una unidad de otro pais "
                               "en Centauro"], flota)
                    continue
                vehiculo, vinculo = candidato, True

        # ------------------------------------------------ la que llega nueva
        if vehiculo is None:
            faltas = []
            if not placa:
                faltas.append("sin placa")
            elif placa in repetidas:
                faltas.append("placa repetida en Odoo")
            if not nombre_cat:
                faltas.append("sin categoria")
            elif categoria is None:
                faltas.append(f"la categoria «{nombre_cat}» no existe en Centauro")
            if plaza is None and flota["ciudad_obligatoria"]:
                faltas.append(f"la plaza «{lugar}» no existe en Centauro"
                              if lugar else "sin plaza")
            if faltas:
                pendiente(u, None, faltas, flota)
                continue
            tomadas.add(placa)
            plan["altas"].append({"odoo_id": u["id"],
                                  "placa": corto(u.get("license_plate"), 20).upper(),
                                  "categoria_id": categoria["id"],
                                  "categoria": categoria["nombre"],
                                  "pais_id": pais["id"], "pais": flota["nombre"],
                                  "plaza_id": plaza["id"] if plaza else None,
                                  "plaza": plaza["nombre"] if plaza else None,
                                  **datos})
            capturar(u, None, flota,
                     por_capturar(flota, plaza, lugar, datos["color"], None))
            continue

        # ------------------------------------------------ la que ya esta
        # La de otro pais no se cambia de flota sola: lo dice y no se toca.
        if vehiculo.get("pais_id") != pais["id"]:
            pendiente(u, vehiculo["id"],
                      [f"en Odoo es de la flota de «{flota['nombre']}» y en "
                       "Centauro es de otro pais"], flota)
            continue
        if not vehiculo.get("activo"):
            pendiente(u, vehiculo["id"], ["activa en Odoo pero dada de baja en "
                                          "Centauro: reactivar a mano"], flota)
            continue

        valores, que, avisos = {}, [], []
        if placa and placa != placa_de(vehiculo.get("placa")):
            otra = por_placa.get(placa)
            if placa in repetidas:
                avisos.append("placa repetida en Odoo")
            elif (otra is not None and otra["id"] != vehiculo["id"]) \
                    or placa in tomadas:
                avisos.append("su placa nueva ya es de otra unidad en Centauro")
            else:
                valores["placa"] = texto(u.get("license_plate")).upper()
                que.append("placa")
                tomadas.add(placa)
        if categoria is not None and categoria["id"] != vehiculo.get("categoria_id"):
            valores["categoria_id"] = categoria["id"]
            que.append("categoria")
        elif nombre_cat and categoria is None:
            avisos.append(f"la categoria «{nombre_cat}» no existe en Centauro")
        if plaza is not None and plaza["id"] != vehiculo.get("plaza_id"):
            valores["plaza_id"] = plaza["id"]
            que.append("plaza")
        elif plaza is None and lugar and flota["ciudad_obligatoria"]:
            avisos.append(f"la plaza «{lugar}» no existe en Centauro")
        for campo, etiqueta in (("marca_modelo", "marca y modelo"),
                                ("color", "color"), ("modelo_anio", "año")):
            if datos[campo] and datos[campo] != vehiculo.get(campo):
                valores[campo] = datos[campo]
                que.append(etiqueta)

        if vinculo:
            plan["vinculos"].append({"vehiculo_id": vehiculo["id"],
                                     "odoo_id": u["id"],
                                     "placa": vehiculo.get("placa")})
        if valores:
            plan["cambios"].append({"vehiculo_id": vehiculo["id"],
                                    "odoo_id": u["id"],
                                    "placa": vehiculo.get("placa"),
                                    "valores": valores, "que": que})
        elif not vinculo:
            plan["sin_cambio"] += 1
        if avisos:
            pendiente(u, vehiculo["id"], avisos, flota)
        capturar(u, vehiculo["id"], flota,
                 por_capturar(flota, plaza, lugar, datos["color"], vehiculo))
        plan["procesadas"].append(vehiculo["id"])

    ids = {u["id"] for u, _ in elegidas} | {u["id"] for u, _ in mezcladas}
    plan["revisar_salida"] = [
        v for v in vehiculos
        if v.get("odoo_id") and v.get("activo") and v.get("sincronizado_en")
        and v["odoo_id"] not in ids]
    return plan


def clasificar_salidas(revisar: list, estados: dict, etiquetas: dict) -> tuple:
    """(bajas, pendientes). `estados`: lo que dice Odoo de cada una, leido
    con las archivadas incluidas."""
    bajas, pendientes = [], []
    for v in revisar:
        u = estados.get(v["odoo_id"])
        if u is not None and u.get("active", True) is not False:
            pendientes.append({"odoo_id": v["odoo_id"], "vehiculo_id": v["id"],
                               "placa": v.get("placa"),
                               "falta": ["ya no es de Proteccion Ejecutiva "
                                         "en Odoo" if not es_de_proteccion(u, etiquetas)
                                         else "revisar en Odoo"]})
        else:
            bajas.append({"odoo_id": v["odoo_id"], "vehiculo_id": v["id"],
                          "placa": v.get("placa"),
                          "motivo": ("archivada en Odoo" if u is not None
                                     else "ya no esta en Odoo")})
    return bajas, pendientes


# ------------------------------------------------------------ el taller

def planear_taller(registros: list, vehiculo_por_odoo: dict,
                   existentes: dict) -> dict:
    """Que hacer con cada entrada al taller de Odoo, sin hacerlo.

    `registros`: fleet.vehicle.log.services, con las fechas de entrada y
    salida ya leidas como `entrada` y `salida`. `vehiculo_por_odoo`: id de
    la unidad en Odoo -> id en Centauro. `existentes`: lo que Centauro ya
    guardo de Odoo, por odoo_id, con vehiculo_id, desde, hasta, tipo,
    taller y nota.
    """
    plan = {"crear": [], "cambiar": [], "borrar": [], "pendientes": [],
            "sin_cambio": 0, "de_otras_unidades": 0}
    vistos = set()
    for r in registros:
        tipo = TALLER.get(normal(nombre_de(r.get("service_type_id"))))
        if tipo is None or r.get("state") == "cancelled":
            continue                    # no es taller: si estaba, se borra
        vehiculo_id = vehiculo_por_odoo.get(id_de(r.get("vehicle_id")))
        if vehiculo_id is None:
            plan["de_otras_unidades"] += 1
            continue
        vistos.add(r["id"])
        desde, hasta = fecha(r.get("entrada")), fecha(r.get("salida"))
        faltas = []
        if desde is None:
            faltas.append("sin fecha de entrada")
        elif hasta is not None and hasta < desde:
            faltas.append("la salida es antes que la entrada")
        elif hasta is None and r.get("state") == "done":
            # Terminado y sin salida: ya no esta en el taller, pero no se
            # sabe desde cuando. Se toma el dia de entrada y se avisa.
            hasta = desde
            faltas.append("terminado sin fecha de salida: se tomo el dia "
                          "de entrada")
        if faltas:
            plan["pendientes"].append({"odoo_id": r["id"],
                                       "vehiculo_id": vehiculo_id,
                                       "falta": faltas})
            if desde is None or (hasta is not None and hasta < desde):
                continue
        valores = {"vehiculo_id": vehiculo_id, "desde": desde, "hasta": hasta,
                   "tipo": tipo,
                   "taller": nombre_de(r.get("vendor_id"))[:160] or None,
                   "nota": texto(r.get("description"))[:300] or None}
        antes = existentes.get(r["id"])
        if antes is None:
            plan["crear"].append({"odoo_id": r["id"], **valores})
        elif any(antes.get(k) != v for k, v in valores.items()):
            plan["cambiar"].append({"odoo_id": r["id"], "id": antes["id"],
                                    **valores})
        else:
            plan["sin_cambio"] += 1
    plan["borrar"] = [e["id"] for odoo_id, e in existentes.items()
                      if odoo_id not in vistos]
    return plan

# -*- coding: utf-8 -*-
"""Las reglas de los clientes que vienen de Odoo, sin base de datos.

Seccion 75, tercer paso de la propuesta Puestos y Odoo que aprobo
Salvador el 26 de septiembre. Como las otras lecturas, aqui se decide
que hacer con cada cliente a partir de fotos fijas de Odoo y de Centauro,
sin leer ni escribir nada.

Las decisiones que viven aqui:

  * Es cliente toda empresa de Odoo con la etiqueta «Protección
    ejecutiva» (seccion 77; antes, toda empresa con ventas).
  * Los clientes se dan de alta en Odoo; Centauro los lee con su nombre,
    su RFC y su pais. El tarifario es de Centauro: el cliente llega sin
    el y se le pone aqui.
  * La llave es el numero interno de Odoo. La primera vez, al cliente que
    ya estaba en Centauro se le reconoce por su RFC o, si no, por su
    nombre sin la razon social --«Grupo Gamma» es «Grupo Gamma SA de
    CV»--, y solo si el parecido es con uno y nada mas.
  * Sin RFC se da de alta igual --se le pueden dar servicios-- pero se
    cuenta aparte: sin RFC no se le puede facturar.
  * Lo dudoso no se adivina: pendiente. El pais sin decir en Odoo se
    toma de un RFC mexicano, que tiene su forma; si tampoco, pendiente.
  * Un cliente de Centauro que no esta en Odoo --los de Brasil, mientras
    no lleguen alla-- no se toca.
"""
import collections
import re

from app.odoo_personal_reglas import nombre_de, normal, texto

# La razon social no es parte del nombre: con ella o sin ella es la
# misma empresa. Se quita del final, una o varias.
RAZON_SOCIAL = re.compile(
    r"(,?\s+(s\.?\s*a\.?\s*p\.?\s*i\.?|s\.?\s*a\.?|s\.?\s*de\s*r\.?\s*l\.?|"
    r"s\.?\s*c\.?|a\.?\s*c\.?|de\s+c\.?\s*v\.?|ltda\.?|s/a|inc\.?|llc|"
    r"corp\.?|me|epp|eireli))+\s*$")

# El RFC mexicano: tres o cuatro letras, la fecha y tres de homoclave.
RFC_MEXICANO = re.compile(r"^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$")

# Los nombres con que Odoo dice los paises que Centauro tiene, ademas del
# nombre de Centauro mismo.
ALIAS_PAIS = {"mexico": "MX", "brazil": "BR", "brasil": "BR",
              "colombia": "CO", "peru": "PE", "venezuela": "VE",
              "united states": "US", "estados unidos": "US"}


def nombre_llave(nombre) -> str:
    """El nombre para reconocer a la empresa: sin acentos, sin puntos ni
    comas y sin razon social."""
    limpio = normal(nombre)
    limpio = RAZON_SOCIAL.sub("", limpio)
    limpio = re.sub(r"[^\w&]+", " ", limpio)
    return " ".join(limpio.split())


def rfc_de(partner: dict) -> str:
    """El RFC como lo escriben en Odoo, en mayusculas y sin espacios. El
    prefijo del pais que a veces le ponen --«MX»-- no es parte del RFC."""
    rfc = re.sub(r"[\s\-]", "", texto(partner.get("vat"))).upper()
    if rfc.startswith("MX") and RFC_MEXICANO.match(rfc[2:]):
        rfc = rfc[2:]
    return rfc


def pais_de(partner: dict, paises: dict) -> tuple:
    """(pais o None, lo que dice Odoo, si se tomo del RFC). `paises`: por
    codigo de dos letras y por nombre normalizado."""
    escrito = nombre_de(partner.get("country_id"))
    if escrito:
        clave = normal(escrito)
        return paises.get(ALIAS_PAIS.get(clave, clave)), escrito, False
    if RFC_MEXICANO.match(rfc_de(partner)):
        return paises.get("MX"), "", True
    return None, "", False


def planear(partners: list, clientes: list, paises: dict) -> dict:
    """Que hacer con cada cliente de Odoo, sin hacerlo.

    `partners`: las empresas cliente que leyo Odoo (las activas).
    `clientes`: foto fija de Centauro, con id, odoo_id, nombre, rfc,
    pais_id, activo y sincronizado_en.
    """
    por_odoo = {c["odoo_id"]: c for c in clientes if c.get("odoo_id")}
    libres = [c for c in clientes if not c.get("odoo_id")]
    por_rfc = collections.defaultdict(list)
    por_nombre = collections.defaultdict(list)
    for c in libres:
        if texto(c.get("rfc")):
            por_rfc[texto(c["rfc"]).upper()].append(c)
        por_nombre[nombre_llave(c.get("nombre"))].append(c)
    nombres_en_odoo = collections.Counter(nombre_llave(p.get("name"))
                                          for p in partners)

    plan = {"leidos": len(partners), "altas": [], "vinculos": [],
            "cambios": [], "pendientes": [], "sin_rfc": [], "por_rfc": [],
            "sin_cambio": 0, "procesados": [], "revisar_salida": []}
    tomados = set()        # clientes de Centauro que este plan ya ligo

    def pendiente(p, cliente_id, faltas):
        plan["pendientes"].append({"odoo_id": p["id"], "cliente_id": cliente_id,
                                   "nombre": texto(p.get("name")),
                                   "falta": faltas})

    for p in partners:
        nombre = texto(p.get("name"))
        rfc = rfc_de(p)
        pais, escrito, del_rfc = pais_de(p, paises)

        cliente = por_odoo.get(p["id"])
        # El que se ligo a mano en el ensayo trae su No. Odoo pero nunca
        # se ha leido: para el informe, se liga ahora por primera vez.
        vinculo = cliente is not None and not cliente.get("sincronizado_en")
        if cliente is None:
            candidatos = [c for c in por_rfc.get(rfc, []) if rfc] or (
                por_nombre.get(nombre_llave(nombre), [])
                if nombres_en_odoo[nombre_llave(nombre)] == 1 else [])
            candidatos = [c for c in candidatos if c["id"] not in tomados]
            if len(candidatos) > 1:
                pendiente(p, None, ["se parece a mas de un cliente de "
                                    "Centauro"])
                continue
            if candidatos:
                cliente, vinculo = candidatos[0], True
                tomados.add(cliente["id"])

        if not rfc:
            plan["sin_rfc"].append({"odoo_id": p["id"], "nombre": nombre})
        if del_rfc and pais is not None:
            plan["por_rfc"].append({"odoo_id": p["id"], "nombre": nombre})

        # ------------------------------------------------ quien llega nuevo
        if cliente is None:
            if pais is None:
                pendiente(p, None, [f"el pais «{escrito}» no existe en "
                                    "Centauro" if escrito else "sin pais"])
                continue
            plan["altas"].append({"odoo_id": p["id"], "nombre": nombre,
                                  "rfc": rfc or None, "pais_id": pais["id"],
                                  "pais": pais["nombre"]})
            continue

        # ------------------------------------------------ quien ya esta
        if not cliente.get("activo"):
            pendiente(p, cliente["id"], ["activo en Odoo pero dado de baja en "
                                         "Centauro: reactivar a mano"])
            continue
        valores, que = {}, []
        if nombre and nombre != cliente.get("nombre"):
            valores["nombre"] = nombre
            que.append("nombre")
        if rfc and rfc != texto(cliente.get("rfc")).upper():
            valores["rfc"] = rfc
            que.append("rfc")
        if pais is not None and pais["id"] != cliente.get("pais_id"):
            valores["pais_id"] = pais["id"]
            que.append("pais")
        if vinculo:
            plan["vinculos"].append({"cliente_id": cliente["id"],
                                     "odoo_id": p["id"],
                                     "nombre": nombre or cliente.get("nombre")})
        if valores:
            plan["cambios"].append({"cliente_id": cliente["id"],
                                    "odoo_id": p["id"],
                                    "nombre": nombre or cliente.get("nombre"),
                                    "valores": valores, "que": que})
        elif not vinculo:
            plan["sin_cambio"] += 1
        plan["procesados"].append(cliente["id"])

    # Los de Centauro que no se encontraron en Odoo. No se tocan, pero se
    # dicen: si alguno es uno de los que llegan con otro nombre, se liga a
    # mano antes de aplicar y no se duplica.
    plan["sin_ligar"] = [
        {"cliente_id": c["id"], "nombre": c.get("nombre"),
         "pais_id": c.get("pais_id")}
        for c in libres if c.get("activo") and c["id"] not in tomados]

    # Los que Centauro ya lleva desde Odoo y hoy no salieron: o los
    # archivaron, o dejaron de ser cliente. Se pregunta a Odoo por cada
    # uno antes de decidir. Los que no vienen de Odoo no se tocan.
    ids = {p["id"] for p in partners}
    plan["revisar_salida"] = [
        c for c in clientes
        if c.get("odoo_id") and c.get("activo") and c.get("sincronizado_en")
        and c["odoo_id"] not in ids]
    return plan


def clasificar_salidas(revisar: list, estados: dict) -> tuple:
    """(bajas, pendientes). `estados`: lo que dice Odoo de cada uno, leido
    con los archivados incluidos."""
    bajas, pendientes = [], []
    for c in revisar:
        f = estados.get(c["odoo_id"])
        if f is not None and f.get("active", True) is not False:
            pendientes.append({"odoo_id": c["odoo_id"], "cliente_id": c["id"],
                               "nombre": c.get("nombre"),
                               "falta": ["ya no trae la etiqueta de "
                                         "Proteccion Ejecutiva en Odoo"]})
        else:
            bajas.append({"odoo_id": c["odoo_id"], "cliente_id": c["id"],
                          "nombre": c.get("nombre"),
                          "motivo": ("archivado en Odoo" if f is not None
                                     else "ya no esta en Odoo")})
    return bajas, pendientes

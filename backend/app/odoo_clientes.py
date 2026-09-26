# -*- coding: utf-8 -*-
"""Los clientes, leidos de Odoo (seccion 75).

Tercer paso de la propuesta Puestos y Odoo (Salvador, 26 sep): los
clientes se dan de alta en Odoo y Centauro los lee de ahi, con su nombre,
su RFC y su pais. El cliente llega sin tarifario: desde la seccion 77 lo
toma de la lista de precios de su ficha de Odoo, en la lectura de los
tarifarios; mientras esa no este en marcha, se le pone en Centauro.

Funciona igual que las otras lecturas: ensayo que no guarda nada, la
primera a mano y de ahi cada hora sola. Nunca escribe en Odoo.

Las reglas viven en odoo_clientes_reglas.py, sin base de datos.
"""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import accesos, odoo_tarifarios
from app import models as m
from app import odoo_clientes_reglas as reglas
from app.config import settings
from app.odoo_personal_reglas import normal

registro = logging.getLogger("centauro.odoo")

TIPO = "clientes"
MODELO = "res.partner"
# Las empresas con la etiqueta «Protección ejecutiva» (seccion 77,
# decision 5): asi llegan los clientes que todavia no tienen ventas en
# Odoo --Volvo-- y no llegan los de GPS ni los de carga. Antes eran todas
# las empresas con ventas. Los contactos de cada empresa --las personas
# que piden los servicios-- no: esos son los solicitantes, y se capturan
# en Centauro.
CAMPOS = ["name", "vat", "country_id", "write_date"]


def etiqueta(odoo) -> int | None:
    """El id de la etiqueta de los clientes de Proteccion Ejecutiva."""
    buscada = normal(settings.odoo_etiqueta_clientes)
    for fila in odoo.leer("res.partner.category", [], ["name"]):
        if normal(fila.get("name")) == buscada:
            return fila["id"]
    return None


def dominio(etiqueta_id: int) -> list:
    return [["is_company", "=", True], ["category_id", "in", [etiqueta_id]]]


def _utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fotos_fijas(db: Session) -> tuple:
    paises = {}
    for p in db.query(m.Pais).all():
        ficha = {"id": p.id, "nombre": p.nombre}
        paises[p.codigo.upper()] = ficha
        paises[normal(p.nombre)] = ficha
    clientes = [{
        "id": c.id, "odoo_id": c.odoo_id, "nombre": c.nombre, "rfc": c.rfc,
        "pais_id": c.pais_id, "activo": c.activo,
        "tarifario_id": c.tarifario_id,
        "sincronizado_en": c.odoo_sincronizado_en,
    } for c in db.query(m.Cliente).all()]
    return paises, clientes


def sincronizar(db: Session, odoo, ensayo: bool = True,
                quien: m.Usuario | None = None,
                automatica: bool = False) -> dict:
    """Lee los clientes de Odoo y, si no es ensayo, los guarda."""
    ahora = _utc()
    etiqueta_id = etiqueta(odoo)
    if etiqueta_id is None:
        # Sin la etiqueta no se sabe quien es cliente: no se toca nada.
        # Leer a todos seria traer a los de GPS y a los de carga.
        return {"ensayo": ensayo, "sin_etiqueta": settings.odoo_etiqueta_clientes,
                "leidos": 0, "altas": [], "vinculadas": [], "cambios": [],
                "bajas": [], "pendientes": [], "sin_rfc": [],
                "pais_por_rfc": [], "sin_ligar": [], "sin_tarifario": 0,
                "sin_cambio": 0,
                "tarifarios_de_odoo": odoo_tarifarios.en_marcha(db)}
    partners = odoo.leer(MODELO, dominio(etiqueta_id), CAMPOS)
    paises, clientes = _fotos_fijas(db)
    plan = reglas.planear(partners, clientes, paises)

    estados = {}
    if plan["revisar_salida"]:
        estados = {f["id"]: f for f in odoo.leer(
            MODELO,
            [["id", "in", [c["odoo_id"] for c in plan["revisar_salida"]]]],
            ["active"], archivados=True)}
    bajas, pendientes_de_salida = reglas.clasificar_salidas(
        plan["revisar_salida"], estados)
    plan["pendientes"].extend(pendientes_de_salida)

    # Llegan sin tarifario: se cuenta cuantos de los que ya son clientes
    # siguen sin el, que es lo que falta para poder cotizarles.
    procesados = set(plan["procesados"])
    sin_tarifario = len(plan["altas"]) + sum(
        1 for c in clientes
        if c["id"] in procesados and not c.get("tarifario_id"))

    informe = {
        "ensayo": ensayo,
        "leidos": plan["leidos"],
        "altas": [{k: a[k] for k in ("odoo_id", "nombre", "rfc", "pais")}
                  for a in plan["altas"]],
        "vinculadas": plan["vinculos"],
        "cambios": [{k: c[k] for k in ("cliente_id", "odoo_id", "nombre", "que")}
                    for c in plan["cambios"]],
        "bajas": bajas,
        "pendientes": plan["pendientes"],
        "sin_rfc": plan["sin_rfc"],
        "pais_por_rfc": plan["por_rfc"],
        "sin_ligar": plan["sin_ligar"],
        "sin_tarifario": sin_tarifario,
        "sin_cambio": plan["sin_cambio"],
        # Si su tarifario ya lo pone su lista de Odoo (seccion 77) o
        # todavia se les pone a mano: la pantalla dice una cosa u otra.
        "tarifarios_de_odoo": odoo_tarifarios.en_marcha(db),
    }
    if ensayo:
        return informe

    # ------------------------------------------------------------ aplicar
    for alta in plan["altas"]:
        db.add(m.Cliente(nombre=alta["nombre"], pais_id=alta["pais_id"],
                         odoo_id=alta["odoo_id"], rfc=alta["rfc"],
                         activo=True, odoo_sincronizado_en=ahora))
    for vinculo in plan["vinculos"]:
        db.get(m.Cliente, vinculo["cliente_id"]).odoo_id = vinculo["odoo_id"]
    for cambio in plan["cambios"]:
        cliente = db.get(m.Cliente, cambio["cliente_id"])
        for campo, valor in cambio["valores"].items():
            setattr(cliente, campo, valor)
    for cliente_id in plan["procesados"]:
        db.get(m.Cliente, cliente_id).odoo_sincronizado_en = ahora
    for baja in bajas:
        # No se borra: sus servicios y sus facturas lo siguen nombrando.
        # Solo deja de ofrecerse para un servicio nuevo.
        db.get(m.Cliente, baja["cliente_id"]).activo = False

    hubo_algo = (plan["altas"] or plan["vinculos"] or plan["cambios"] or bajas)
    fila = m.SincronizacionOdoo(
        tipo=TIPO, automatica=automatica,
        hecha_por_id=quien.persona_id if quien else None,
        leidos=plan["leidos"], altas=len(plan["altas"]),
        cambios=len({c["cliente_id"] for c in plan["cambios"]}
                    | {v["cliente_id"] for v in plan["vinculos"]}),
        bajas=len(bajas), pendientes=len(plan["pendientes"]),
        detalle=(json.dumps(informe, ensure_ascii=False, default=str)
                 if hubo_algo or not automatica else None))
    db.add(fila)
    db.flush()
    if quien is not None:
        accesos.anotar(
            db, quien, "clientes leidos de odoo", "sincronizacion_odoo",
            fila.id, despues=(f"{len(plan['altas'])} altas, "
                              f"{len(plan['cambios'])} cambios, "
                              f"{len(bajas)} bajas, "
                              f"{len(plan['sin_rfc'])} sin RFC"))
    db.commit()
    return informe


def resumen(informe: dict) -> dict:
    return {"leidos": informe["leidos"], "altas": len(informe["altas"]),
            "vinculadas": len(informe["vinculadas"]),
            "cambios": len(informe["cambios"]), "bajas": len(informe["bajas"]),
            "sin_rfc": len(informe["sin_rfc"]),
            "pendientes": len(informe["pendientes"])}


def sincronizar_si_toca(db: Session, odoo=None) -> dict:
    """La tarea de cada hora. No arranca sola: espera a que alguien haya
    hecho la primera lectura a mano, despues de ver el ensayo."""
    from app import odoo_api

    primera = (db.query(m.SincronizacionOdoo)
               .filter_by(tipo=TIPO, automatica=False).first())
    if primera is None:
        return {"omitido": "falta la primera lectura a mano"}
    if odoo is None:
        if not odoo_api.hay_conexion():
            return {"omitido": "Odoo no esta conectado"}
        odoo = odoo_api.cliente()
    try:
        return resumen(sincronizar(db, odoo, ensayo=False, automatica=True))
    except odoo_api.NoResponde as error:
        db.rollback()
        registro.warning("odoo no respondio al leer los clientes: %s", error)
        return {"error": str(error)}

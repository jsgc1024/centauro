# -*- coding: utf-8 -*-
"""Logistica (seccion 151): quien puede salir a un viaje.

Una sola funcion para la unidad y otra para el operador, que usan la
pantalla de Flota LG, la de Jornada LG y, en el bloque 4, la asignacion:
no hay dos versiones de la misma regla. Cada una contesta

    {"estado": "libre" | "alerta" | "bloqueo", "motivos": [...]}

con cada motivo como {nivel, clave, ...datos}; la pantalla lo dice en el
idioma de quien lee (`lgd_<clave>` en idioma.js).

Bloqueo: ocupada en otro viaje esas fechas o marcada en viaje, en taller,
fuera de servicio, un documento o la licencia vencidos, un servicio
preventivo vencido, el operador sin su marca de jornada (o por validar).
Alerta: un documento o la licencia sin capturar (decision de Salvador, 3
oct), uno que vence durante el viaje o la licencia a menos de 30 dias, un
servicio que cae dentro de los km del viaje.

Las reglas puras (`evaluar_*`) no tocan la base: asi las prueban los
ejemplos sin armar nada.
"""
from datetime import date

from sqlalchemy.orm import Session

from app import lg_flota
from app import models as m

LIBRE, ALERTA, BLOQUEO = "libre", "alerta", "bloqueo"


def _motivo(nivel: str, clave: str, **datos) -> dict:
    return {"nivel": nivel, "clave": clave,
            **{k: (v.isoformat() if isinstance(v, date) else v) for k, v in datos.items()}}


def _resultado(motivos: list[dict]) -> dict:
    niveles = {x["nivel"] for x in motivos}
    estado = BLOQUEO if BLOQUEO in niveles else ALERTA if ALERTA in niveles else LIBRE
    # Primero lo que bloquea.
    motivos.sort(key=lambda x: 0 if x["nivel"] == BLOQUEO else 1)
    return {"estado": estado, "motivos": motivos}


def _se_cruza(desde: date, hasta: date, otro_desde: date | None,
              otro_hasta: date | None) -> bool:
    if otro_desde is None and otro_hasta is None:
        return False
    otro_desde = otro_desde or date.min
    otro_hasta = otro_hasta or date.max
    return desde <= otro_hasta and otro_desde <= hasta


# ================================================================ la unidad

def datos_unidad(u: m.LgUnidad, documentos: dict, proximos: list[dict],
                 viajes: list | None = None) -> dict:
    """Lo que la regla necesita de una unidad, sin la base."""
    return {"activo": u.activo and not u.baja_odoo_en, "clase": u.clase,
            "tipo_id": u.tipo_id, "estado": u.estado,
            "estado_hasta": u.estado_hasta, "estado_motivo": u.estado_motivo,
            "documentos": {t: (d.vence_en if d is not None else None, d is not None)
                           for t, d in ((t, documentos.get(t)) for t in lg_flota.DOCUMENTOS)},
            "proximos": proximos, "viajes": viajes or []}


def evaluar_unidad(u: dict, desde: date, hasta: date | None, km, hoy: date) -> dict:
    hasta = hasta or desde
    motivos: list[dict] = []
    if not u["activo"]:
        motivos.append(_motivo(BLOQUEO, "baja"))
    if u["clase"] == "remolque":
        motivos.append(_motivo(BLOQUEO, "remolque"))
    elif not u["tipo_id"]:
        motivos.append(_motivo(BLOQUEO, "sin_tipo"))
    estado = u["estado"]
    if estado == "fuera_de_servicio":
        motivos.append(_motivo(BLOQUEO, "fuera_de_servicio", motivo=u.get("estado_motivo")))
    elif estado in ("en_taller", "en_viaje"):
        regresa = u.get("estado_hasta")
        if regresa is not None and hoy <= regresa < desde:
            # Se espera de vuelta antes de que salga: se avisa, no se
            # frena. Si ya paso su fecha y sigue asi, sigue frenada.
            motivos.append(_motivo(ALERTA, f"{estado}_regresa", hasta=regresa,
                                   motivo=u.get("estado_motivo")))
        else:
            motivos.append(_motivo(BLOQUEO, estado, hasta=regresa,
                                   motivo=u.get("estado_motivo")))
    for viaje in u.get("viajes") or []:
        if _se_cruza(desde, hasta, viaje.get("desde"), viaje.get("hasta")):
            motivos.append(_motivo(BLOQUEO, "ocupada", viaje=viaje.get("folio")))
    for tipo, (vence, capturado) in u["documentos"].items():
        if not capturado:
            motivos.append(_motivo(ALERTA, "documento_falta", documento=tipo))
        elif vence is None:
            continue
        elif vence < desde:
            motivos.append(_motivo(BLOQUEO, "documento_vencido", documento=tipo, vence=vence))
        elif vence <= hasta:
            motivos.append(_motivo(ALERTA, "documento_vence_en_viaje", documento=tipo,
                                   vence=vence))
    for p in u["proximos"]:
        faltan = p.get("faltan_km")
        if faltan is None:
            continue
        if faltan <= 0:
            motivos.append(_motivo(BLOQUEO, "servicio_vencido", servicio=p["nombre"],
                                   km=-faltan))
        elif km is not None and faltan <= int(km):
            motivos.append(_motivo(ALERTA, "servicio_en_viaje", servicio=p["nombre"],
                                   km=faltan))
    return _resultado(motivos)


def _viajes_de_unidad(db: Session, unidad_id: int, desde: date, hasta: date) -> list:
    """Los viajes de la unidad que se cruzan con esas fechas. Los viajes
    llegan con el bloque 4; mientras, ninguno."""
    return []


def unidad(db: Session, unidad_id: int, desde: date | None = None,
           hasta: date | None = None, km=None, hoy: date | None = None) -> dict:
    """Si la unidad puede salir a un viaje de esas fechas y esos km."""
    hoy = hoy or lg_flota.hoy()
    desde = desde or hoy
    hasta = hasta or desde
    u = lg_flota.unidad_o_404(db, unidad_id)
    docs = lg_flota.vigentes(db, unidad_ids=[u.id]).get(("u", u.id), {})
    prox = lg_flota.proximos(lg_flota.plan_de(db, u),
                             lg_flota.ultimos_servicios(db, [u.id]), u)
    datos = datos_unidad(u, docs, prox, _viajes_de_unidad(db, u.id, desde, hasta))
    return evaluar_unidad(datos, desde, hasta, km, hoy)


# ================================================================ el operador

def datos_operador(o: m.LgOperador, licencia: m.LgDocumento | None,
                   jornadas: dict, viajes: list | None = None,
                   a_mano: list | None = None) -> dict:
    """`jornadas`: {fecha: estado de su marca}. `a_mano`: [(desde, hasta)]
    de sus viajes marcados a mano mientras siga Tango."""
    return {"activo": o.activo and not o.baja_odoo_en,
            "licencia": (licencia.vence_en if licencia else None, licencia is not None),
            "en_viaje": list(a_mano or []),
            "jornadas": jornadas, "viajes": viajes or []}


def evaluar_operador(o: dict, desde: date, hasta: date | None, hoy: date) -> dict:
    hasta = hasta or desde
    motivos: list[dict] = []
    if not o["activo"]:
        motivos.append(_motivo(BLOQUEO, "baja"))
    for viaje_desde, viaje_hasta in o["en_viaje"]:
        if viaje_hasta >= hoy and _se_cruza(desde, hasta, viaje_desde, viaje_hasta):
            motivos.append(_motivo(BLOQUEO, "en_viaje", hasta=viaje_hasta))
            break
    for viaje in o.get("viajes") or []:
        if _se_cruza(desde, hasta, viaje.get("desde"), viaje.get("hasta")):
            motivos.append(_motivo(BLOQUEO, "ocupado", viaje=viaje.get("folio")))
    vence, capturada = o["licencia"]
    if not capturada:
        motivos.append(_motivo(ALERTA, "licencia_falta"))
    elif vence is not None:
        if vence < desde:
            motivos.append(_motivo(BLOQUEO, "licencia_vencida", vence=vence))
        elif vence <= hasta:
            motivos.append(_motivo(ALERTA, "licencia_vence_en_viaje", vence=vence))
        elif (vence - hoy).days < lg_flota.DIAS_AVISO:
            motivos.append(_motivo(ALERTA, "licencia_por_vencer", vence=vence,
                                   dias=(vence - hoy).days))
    # La marca de jornada solo se puede pedir el mismo dia: la de manana
    # todavia no existe.
    if desde == hoy:
        marca = o["jornadas"].get(hoy)
        if marca is None:
            motivos.append(_motivo(BLOQUEO, "sin_jornada"))
        elif marca == "por_validar":
            motivos.append(_motivo(BLOQUEO, "jornada_por_validar"))
        elif marca == "rechazada":
            motivos.append(_motivo(BLOQUEO, "jornada_rechazada"))
    return _resultado(motivos)


def _viajes_de_operador(db: Session, operador_id: int, desde: date, hasta: date) -> list:
    """Como los de la unidad: llegan con el bloque 4."""
    return []


def operador(db: Session, operador_id: int, desde: date | None = None,
             hasta: date | None = None, hoy: date | None = None) -> dict:
    """Si el operador puede salir a un viaje de esas fechas."""
    hoy = hoy or lg_flota.hoy()
    desde = desde or hoy
    hasta = hasta or desde
    o = db.get(m.LgOperador, operador_id)
    if not o:
        from fastapi import HTTPException
        raise HTTPException(404, "No existe ese operador")
    licencia = lg_flota.vigentes(db, operador_ids=[o.id]).get(("o", o.id), {}).get(
        lg_flota.LICENCIA)
    jornadas = {j.fecha: j.estado for j in db.query(m.LgJornada).filter(
        m.LgJornada.operador_id == o.id, m.LgJornada.fecha == hoy).all()}
    a_mano = [(v.desde, v.hasta) for v in db.query(m.LgViajeManual).filter(
        m.LgViajeManual.operador_id == o.id, m.LgViajeManual.quitado_en.is_(None),
        m.LgViajeManual.hasta >= hoy).all()]
    datos = datos_operador(o, licencia, jornadas,
                           _viajes_de_operador(db, o.id, desde, hasta), a_mano)
    return evaluar_operador(datos, desde, hasta, hoy)

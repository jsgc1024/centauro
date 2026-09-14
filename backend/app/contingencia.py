"""Cambio de recurso por contingencia.

Reparto de responsabilidades, tal como opera Centauro:
la central estabiliza el servicio (puede mandar su equipo de respuesta a
emergencias) y el consultor formaliza el cambio aqui.

Lo delicado no es cambiar el nombre de quien va: son los viaticos. La
persona que sale se queda con dinero que ya recibio y tiene que
comprobarlo; la que entra necesita dinero nuevo para dar continuidad.
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import viaticos as motor_viaticos

# Estos viaticos ya tienen dinero encima: no se cancelan, se comprueban.
CON_DINERO = (m.EstatusViatico.TRANSFERIDO, m.EstatusViatico.EN_COMPROBACION)
# Estos todavia no: se cancelan sin mas.
SIN_DINERO = (m.EstatusViatico.ASIGNADO, m.EstatusViatico.SOLICITADO)


def jornadas_afectadas(db: Session, desde: m.Jornada) -> list[m.Jornada]:
    """De la jornada de la contingencia en adelante, dentro del mismo equipo.

    Los dias ya terminados no se tocan: esos ya los trabajo quien iba.
    """
    return (db.query(m.Jornada)
            .filter(m.Jornada.equipo_id == desde.equipo_id,
                    m.Jornada.fecha >= desde.fecha,
                    m.Jornada.estatus.notin_([m.EstatusJornada.CANCELADA,
                                              m.EstatusJornada.TERMINADA]))
            .order_by(m.Jornada.fecha)
            .all())


def reemplazar_personal(db: Session, desde_jornada_id: int, sale_persona_id: int,
                        entra_persona_id: int, motivo: str,
                        hecho_por_id: int | None = None,
                        alerta_id: int | None = None) -> dict:
    desde = db.get(m.Jornada, desde_jornada_id)
    if not desde:
        raise HTTPException(404, f"No existe la jornada {desde_jornada_id}")
    if sale_persona_id == entra_persona_id:
        raise HTTPException(409, "La persona que entra es la misma que sale")

    entra = db.get(m.Persona, entra_persona_id)
    if not entra or not entra.activo:
        raise HTTPException(404, "La persona que entra no existe o esta inactiva")

    jornadas = jornadas_afectadas(db, desde)
    cambiadas, choques = [], []

    for j in jornadas:
        asignacion = (db.query(m.AsignacionPersonal)
                      .filter_by(jornada_id=j.id, persona_id=sale_persona_id)
                      .first())
        if not asignacion:
            continue
        # Si el que entra ya estaba en ese dia, el equipo se quedaria corto.
        ya_estaba = (db.query(m.AsignacionPersonal)
                     .filter_by(jornada_id=j.id, persona_id=entra_persona_id)
                     .first())
        if ya_estaba:
            choques.append(j.fecha.isoformat())
            continue

        asignacion.persona_id = entra_persona_id
        asignacion.reemplaza_a_id = sale_persona_id
        asignacion.confirmado = False       # el que entra tiene que confirmar
        cambiadas.append(j)

    if not cambiadas:
        raise HTTPException(409, {
            "mensaje": ("Esa persona no esta asignada a ninguna jornada "
                        "pendiente desde ese dia"),
            "choques": choques,
        })

    viaticos = _mover_viaticos(db, cambiadas, sale_persona_id, entra_persona_id)

    reemplazo = m.ReemplazoRecurso(
        alerta_id=alerta_id, servicio_id=desde.equipo.servicio_id,
        desde_jornada_id=desde.id, tipo=m.TipoRecurso.PERSONAL,
        sale_persona_id=sale_persona_id, entra_persona_id=entra_persona_id,
        motivo=motivo, jornadas_afectadas=len(cambiadas),
        hecho_por_id=hecho_por_id)
    db.add(reemplazo)
    db.flush()

    return {
        "reemplazo_id": reemplazo.id,
        "jornadas_afectadas": [j.fecha.isoformat() for j in cambiadas],
        "jornadas_con_choque": choques,
        "viaticos": viaticos,
    }


def reemplazar_vehiculo(db: Session, desde_jornada_id: int, sale_vehiculo_id: int,
                        entra_vehiculo_id: int, motivo: str,
                        hecho_por_id: int | None = None,
                        alerta_id: int | None = None) -> dict:
    desde = db.get(m.Jornada, desde_jornada_id)
    if not desde:
        raise HTTPException(404, f"No existe la jornada {desde_jornada_id}")
    if sale_vehiculo_id == entra_vehiculo_id:
        raise HTTPException(409, "La unidad que entra es la misma que sale")

    entra = db.get(m.Vehiculo, entra_vehiculo_id)
    if not entra or not entra.activo:
        raise HTTPException(404, "La unidad que entra no existe o esta inactiva")

    cambiadas, choques = [], []
    for j in jornadas_afectadas(db, desde):
        asignacion = (db.query(m.AsignacionVehiculo)
                      .filter_by(jornada_id=j.id, vehiculo_id=sale_vehiculo_id)
                      .first())
        if not asignacion:
            continue
        ya_estaba = (db.query(m.AsignacionVehiculo)
                     .filter_by(jornada_id=j.id, vehiculo_id=entra_vehiculo_id)
                     .first())
        if ya_estaba:
            choques.append(j.fecha.isoformat())
            continue
        asignacion.vehiculo_id = entra_vehiculo_id
        cambiadas.append(j)

    if not cambiadas:
        raise HTTPException(409, {
            "mensaje": ("Esa unidad no esta asignada a ninguna jornada "
                        "pendiente desde ese dia"),
            "choques": choques,
        })

    reemplazo = m.ReemplazoRecurso(
        alerta_id=alerta_id, servicio_id=desde.equipo.servicio_id,
        desde_jornada_id=desde.id, tipo=m.TipoRecurso.VEHICULO,
        sale_vehiculo_id=sale_vehiculo_id, entra_vehiculo_id=entra_vehiculo_id,
        motivo=motivo, jornadas_afectadas=len(cambiadas),
        hecho_por_id=hecho_por_id)
    db.add(reemplazo)
    db.flush()

    return {
        "reemplazo_id": reemplazo.id,
        "jornadas_afectadas": [j.fecha.isoformat() for j in cambiadas],
        "jornadas_con_choque": choques,
        # El vehiculo no mueve viaticos: el combustible y las casetas siguen
        # siendo del conductor, que es el mismo.
        "viaticos": None,
    }


def _mover_viaticos(db: Session, jornadas: list[m.Jornada],
                    sale_persona_id: int, entra_persona_id: int) -> dict:
    """La que sale comprueba lo que ya recibio; la que entra recibe nuevo.

    Un viatico que nunca llego a transferirse no se comprueba: se cancela,
    porque esa persona no va a trabajar ese dia.
    """
    a_comprobar, cancelados, nuevos = [], [], []
    ahora = datetime.now()

    for j in jornadas:
        viejo = (db.query(m.AsignacionViatico)
                 .filter_by(jornada_id=j.id, persona_id=sale_persona_id)
                 .first())
        if viejo:
            if viejo.estatus in CON_DINERO:
                # Ya tiene el dinero: entra a comprobacion con su plazo.
                viejo.estatus = m.EstatusViatico.EN_COMPROBACION
                viejo.limite_comprobacion = motor_viaticos.limite_de_comprobacion(ahora)
                a_comprobar.append({
                    "viatico_id": viejo.id, "fecha": j.fecha.isoformat(),
                    "monto": float(viejo.monto_total),
                    "limite": viejo.limite_comprobacion.isoformat()})
            elif viejo.estatus in SIN_DINERO:
                viejo.estatus = m.EstatusViatico.CANCELADO
                cancelados.append({"viatico_id": viejo.id,
                                   "fecha": j.fecha.isoformat()})

        ya_tiene = (db.query(m.AsignacionViatico)
                    .filter_by(jornada_id=j.id, persona_id=entra_persona_id)
                    .first())
        if ya_tiene:
            continue

        # Viaticos nuevos para quien entra, con el mismo tabulador.
        calculo = motor_viaticos.calcular(db, j.id, entra_persona_id)
        pais_id = j.equipo.servicio.pais_id
        pais = db.get(m.Pais, pais_id)
        nuevo = m.AsignacionViatico(
            jornada_id=j.id, persona_id=entra_persona_id,
            escenario=motor_viaticos.escenario_de(j),
            moneda=pais.moneda_local)
        db.add(nuevo)
        db.flush()
        for c in calculo.get("conceptos", []):
            db.add(m.ConceptoAsignado(
                asignacion_id=nuevo.id,
                concepto=m.ConceptoViatico(c["concepto"]),
                monto=c["monto"],
                descripcion=c.get("descripcion"),
                origen=m.OrigenMonto(c.get("origen", "tabulador"))))
        db.flush()
        db.refresh(nuevo)
        nuevo.monto_total = sum(c.monto for c in nuevo.conceptos)
        nuevos.append({"viatico_id": nuevo.id, "fecha": j.fecha.isoformat(),
                       "monto": float(nuevo.monto_total)})

    return {"a_comprobar": a_comprobar, "cancelados": cancelados,
            "nuevos": nuevos}

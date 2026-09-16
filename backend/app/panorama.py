"""Concentrado de la operacion viva.

Una sola consulta que contesta lo que la direccion quiere saber al abrir
la pantalla: que esta pasando ahora mismo, que esta por arrancar y no
esta listo, y que se esta atorando en el camino al cobro.

Todo lo que sale aqui ya existe en otros modulos. La gracia es que este
en una sola pantalla y que lo urgente se vea primero.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app import models as m
from app import reloj
from app.nomina import lunes_de

CERO = Decimal("0")
VENTANA_PROXIMOS_HORAS = 2


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def panorama(db: Session, ahora: datetime | None = None) -> dict:
    ahora = ahora or datetime.now()
    return {
        "momento": ahora.isoformat(),
        "en_curso": _en_curso(db, ahora),
        "por_iniciar": _por_iniciar(db, ahora),
        "alertas": _alertas(db),
        "dinero": _dinero(db, ahora),
        "cierres": _cierres(db, ahora),
        "pendientes_de_atencion": _pendientes(db),
    }


def _en_curso(db: Session, ahora: datetime) -> dict:
    # El silencio y las horas extra son de cada servicio, y se miden con
    # la hora de su pais. Con la del contenedor, un servicio brasileño
    # aparecia con tres horas de silencio desde que arrancaba.
    relojes = reloj.Relojes(db, ahora)
    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.estatus == m.EstatusJornada.EN_CURSO).all())
    detalle = []
    for j in jornadas:
        suyo = relojes.de_la_jornada(j)
        ultimo = (db.query(m.Hito)
                  .filter_by(jornada_id=j.id)
                  .order_by(m.Hito.marcado_en.desc()).first())
        sin_reporte_min = None
        if ultimo and ultimo.marcado_en:
            sin_reporte_min = int((suyo - ultimo.marcado_en).total_seconds() / 60)

        # Las 12 horas son exactas: el aviso preventivo va 30 min antes.
        minutos_para_extra = None
        if j.fin_programado:
            minutos_para_extra = int((j.fin_programado - suyo).total_seconds() / 60)

        detalle.append({
            "jornada_id": j.id,
            "servicio": j.equipo.servicio.folio,
            "equipo": j.equipo.alias,
            "cliente": j.equipo.servicio.cliente.nombre,
            "personal": [a.persona.nombre for a in j.personal],
            "placas": [a.vehiculo.placa for a in j.vehiculos],
            "inicio": j.inicio_programado.isoformat(),
            "fin_programado": j.fin_programado.isoformat(),
            "ultimo_reporte": ultimo.tipo.value if ultimo else None,
            "minutos_sin_reportar": sin_reporte_min,
            "minutos_para_horas_extra": minutos_para_extra,
        })
    detalle.sort(key=lambda x: x["minutos_sin_reportar"] or 0, reverse=True)
    return {"cuantos": len(detalle), "servicios": detalle}


def _por_iniciar(db: Session, ahora: datetime) -> dict:
    relojes = reloj.Relojes(db, ahora)
    margen = reloj.margen_de_paises(db)
    limite = ahora + timedelta(hours=VENTANA_PROXIMOS_HORAS)
    jornadas = (db.query(m.Jornada)
                .filter(m.Jornada.inicio_programado >= ahora - margen,
                        m.Jornada.inicio_programado <= limite + margen,
                        m.Jornada.estatus.notin_([m.EstatusJornada.CANCELADA,
                                                  m.EstatusJornada.TERMINADA]))
                .order_by(m.Jornada.inicio_programado).all())
    sin_listo = []
    for j in jornadas:
        # Lo que entro por el margen y alla todavia no esta en ventana.
        suyo = relojes.de_la_jornada(j)
        if not (suyo <= j.inicio_programado
                <= suyo + timedelta(hours=VENTANA_PROXIMOS_HORAS)):
            continue
        faltas = []
        if not j.personal:
            faltas.append("sin personal")
        elif any(not a.confirmado for a in j.personal):
            faltas.append("sin confirmar")
        if not j.vehiculos:
            faltas.append("sin unidad")
        if not j.origen_direccion:
            faltas.append("sin meet and greet")
        if faltas:
            sin_listo.append({
                "jornada_id": j.id,
                "servicio": j.equipo.servicio.folio,
                "inicia": j.inicio_programado.isoformat(),
                "en_minutos": int((j.inicio_programado - ahora).total_seconds() / 60),
                "faltas": faltas,
            })
    return {"cuantos": len(jornadas), "no_listos": sin_listo}


def _alertas(db: Session) -> dict:
    filas = (db.query(m.AlertaIncidencia)
             .filter(m.AlertaIncidencia.estatus != m.EstatusAlerta.CERRADA)
             .order_by(m.AlertaIncidencia.reportada_en.desc()).all())
    return {
        "abiertas": len([a for a in filas
                         if a.estatus == m.EstatusAlerta.ABIERTA]),
        "en_atencion": len([a for a in filas
                            if a.estatus == m.EstatusAlerta.EN_ATENCION]),
        "detalle": [{"id": a.id, "canal": a.canal.value,
                     "estatus": a.estatus.value,
                     "servicio_id": a.servicio_id,
                     "reportada_en": a.reportada_en.isoformat()
                     if a.reportada_en else None}
                    for a in filas[:8]],
    }


def _dinero(db: Session, ahora: datetime) -> dict:
    viaticos = db.query(m.AsignacionViatico).all()

    por_transferir = [v for v in viaticos
                      if v.estatus in (m.EstatusViatico.ASIGNADO,
                                       m.EstatusViatico.SOLICITADO)]
    en_comprobacion = [v for v in viaticos
                       if v.estatus == m.EstatusViatico.EN_COMPROBACION]
    # El plazo de comprobacion se vence a la hora de alla.
    relojes = reloj.Relojes(db, ahora)
    vencidos = [
        v for v in en_comprobacion
        if v.limite_comprobacion and v.limite_comprobacion < relojes.ahora(
            reloj.pais_de_la_jornada(v.jornada))]

    corte = lunes_de(ahora.date())
    nomina = (db.query(m.NominaSemanal)
              .filter_by(fecha_corte=corte).first())
    ajustes = (db.query(m.AjusteNomina)
               .filter_by(aplicado_en_nomina_id=None).all())

    return {
        "viaticos_por_transferir": {
            "cuantos": len(por_transferir),
            "monto": sum((_d(v.monto_total) for v in por_transferir), CERO)},
        "viaticos_en_comprobacion": len(en_comprobacion),
        "viaticos_con_plazo_vencido": [
            {"viatico_id": v.id, "persona": v.persona.nombre,
             "monto": _d(v.monto_total),
             "vencio": v.limite_comprobacion.isoformat()}
            for v in vencidos],
        "nomina_de_la_semana": {
            "fecha_corte": corte.isoformat(),
            "estatus": nomina.estatus.value if nomina else "sin calcular",
            "total": _d(nomina.total) if nomina else CERO,
            "personas": len(nomina.renglones) if nomina else 0,
        },
        "ajustes_pendientes": {
            "cuantos": len(ajustes),
            "neto": sum((_d(a.monto) for a in ajustes), CERO)},
    }


def _cierres(db: Session, ahora: datetime) -> dict:
    relojes = reloj.Relojes(db, ahora)
    filas = db.query(m.Cierre).all()
    abiertos = [c for c in filas if c.estatus == m.EstatusCierre.ABIERTO]
    # El plazo del consultor corre en su pais, y de si lo cumple depende
    # que cobre su comision.
    vencidos = [c for c in abiertos
                if c.limite_consultor < relojes.ahora(
                    c.servicio.pais_id if c.servicio else None)]
    en_finanzas = [c for c in filas
                   if c.estatus == m.EstatusCierre.ENVIADO_FINANZAS]
    devueltos = [c for c in filas
                 if c.estatus == m.EstatusCierre.DEVUELTO_A_OPERACION]
    return {
        "abiertos": len(abiertos),
        "con_plazo_vencido": [
            {"servicio": c.servicio.folio,
             "vencio": c.limite_consultor.isoformat(),
             "nota": "El consultor pierde la comision, pero se puede facturar"}
            for c in vencidos],
        "esperando_finanzas": len(en_finanzas),
        "devueltos_a_operacion": [
            {"servicio": c.servicio.folio, "motivo": c.devuelto_motivo}
            for c in devueltos],
    }


def _pendientes(db: Session) -> dict:
    encuestas = (db.query(m.Encuesta)
                 .filter_by(requiere_clasificacion=True)
                 .filter(m.Encuesta.clasificada_en.is_(None)).all())
    incidencias = (db.query(m.Incidencia)
                   .filter_by(autorizada=False)
                   .filter(m.Incidencia.visto_bueno_por_id.is_(None)).all())
    return {
        "encuestas_por_clasificar": [
            {"id": e.id, "servicio_id": e.servicio_id,
             "calificacion": e.calificacion} for e in encuestas],
        "incidencias_sin_visto_bueno": [
            {"id": i.id, "persona": i.persona.nombre,
             "gravedad": i.gravedad.value} for i in incidencias],
    }

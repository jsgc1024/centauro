"""Estrellas mensuales del personal de seguridad.

Una estrella por criterio cumplido. La evaluacion es mensual y por persona,
no por servicio: se agregan todas sus jornadas del mes, sean de servicios
eventuales o implantados.

Sancion escalonada por incidencia:
  - error menor: solo retroalimentacion documentada, no toca las estrellas
  - leve:        quita todas las estrellas del mes
  - grave:       la gestiona Recursos Humanos, quita todas las estrellas
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m

CERO = Decimal("0")


def _rango(anio: int, mes: int) -> tuple[date, date]:
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, 1), date(anio, mes, ultimo)


def jornadas_del_mes(db: Session, persona_id: int, anio: int, mes: int) -> list[m.Jornada]:
    desde, hasta = _rango(anio, mes)
    return (db.query(m.Jornada)
            .join(m.AsignacionPersonal, m.AsignacionPersonal.jornada_id == m.Jornada.id)
            .filter(m.AsignacionPersonal.persona_id == persona_id,
                    m.Jornada.fecha >= desde, m.Jornada.fecha <= hasta,
                    m.Jornada.estatus != m.EstatusJornada.CANCELADA)
            .all())


# ---------------------------------------------------------------- criterios

def medir_puntualidad(db: Session, jornadas: list[m.Jornada]) -> dict:
    """Se mide contra la hora de presentacion de cada dia.
    En implantados cada dia del mes; en eventuales todos los servicios.
    Se exige el 100 por ciento."""
    evaluables = [j for j in jornadas if j.inicio_real]
    if not evaluables:
        return {"valor": CERO, "aplica": False,
                "detalle": "Sin jornadas con inicio registrado este mes"}

    a_tiempo = [j for j in evaluables if j.inicio_real <= j.inicio_programado]
    tarde = [j for j in evaluables if j.inicio_real > j.inicio_programado]
    valor = Decimal(len(a_tiempo)) / Decimal(len(evaluables)) * 100

    detalle = f"{len(a_tiempo)} de {len(evaluables)} jornadas a tiempo"
    if tarde:
        dias = ", ".join(j.fecha.strftime("%d/%m") for j in tarde[:5])
        detalle += f". Tarde: {dias}"
    return {"valor": valor.quantize(Decimal("0.01")), "detalle": detalle}


def medir_seguimiento(db: Session, jornadas: list[m.Jornada], persona_id: int) -> dict:
    """Asertividad en el uso de la app: que cada jornada tenga su secuencia
    completa de hitos y sin alertas por falta de reporte."""
    if not jornadas:
        return {"valor": CERO, "aplica": False,
                "detalle": "Sin jornadas este mes"}

    completas = 0
    faltantes = []
    for j in jornadas:
        tipos = {h.tipo for h in db.query(m.Hito).filter_by(
            jornada_id=j.id, persona_id=persona_id).all()}
        requeridos = {m.TipoHito.LLEGADA_ORIGEN, m.TipoHito.CONTACTO_EJECUTIVO,
                      m.TipoHito.FIN_SERVICIO}
        sin_reporte = (db.query(m.Alerta)
                       .filter_by(jornada_id=j.id, tipo=m.TipoAlerta.SIN_REPORTE)
                       .count())
        if requeridos.issubset(tipos) and not sin_reporte:
            completas += 1
        else:
            faltantes.append(j.fecha.strftime("%d/%m"))

    valor = Decimal(completas) / Decimal(len(jornadas)) * 100
    detalle = f"{completas} de {len(jornadas)} jornadas con seguimiento completo"
    if faltantes:
        detalle += f". Fallas: {', '.join(faltantes[:5])}"
    return {"valor": valor.quantize(Decimal("0.01")), "detalle": detalle}


def medir_cierre_viaticos(db: Session, jornadas: list[m.Jornada],
                          persona_id: int) -> dict:
    """Dentro de 24 horas y sin desviaciones detectadas."""
    ids = [j.id for j in jornadas]
    if not ids:
        return {"valor": CERO, "aplica": False, "detalle": "Sin jornadas este mes"}

    viaticos = (db.query(m.AsignacionViatico)
                .filter(m.AsignacionViatico.jornada_id.in_(ids),
                        m.AsignacionViatico.persona_id == persona_id).all())
    if not viaticos:
        return {"valor": CERO, "aplica": False,
                "detalle": "No se le asignaron viaticos este mes: el criterio no aplica"}

    bien = 0
    problemas = []
    for v in viaticos:
        cerrado = v.estatus == m.EstatusViatico.CERRADO
        cuadra = (Decimal(str(v.monto_total)) - Decimal(str(v.monto_comprobado))
                  - Decimal(str(v.monto_devuelto))) == CERO
        a_tiempo = True
        if v.limite_comprobacion and v.jornada.fin_real:
            a_tiempo = v.limite_comprobacion >= v.jornada.fin_real + timedelta(hours=24)
        if cerrado and cuadra and a_tiempo:
            bien += 1
        else:
            motivo = ("no cerrado" if not cerrado else
                      "cerrado con descuento" if v.cerrado_con_descuento else
                      "no cuadra" if not cuadra else "fuera de plazo")
            problemas.append(f"{v.jornada.fecha:%d/%m} ({motivo})")

    valor = Decimal(bien) / Decimal(len(viaticos)) * 100
    detalle = f"{bien} de {len(viaticos)} cierres correctos"
    if problemas:
        detalle += f". {', '.join(problemas[:5])}"
    return {"valor": valor.quantize(Decimal("0.01")), "detalle": detalle}


# ---------------------------------------------------------------- evaluacion

def incidencia_del_mes(db: Session, persona_id: int, anio: int, mes: int):
    """Solo cuentan las incidencias ya autorizadas por el director de operaciones,
    y el error menor nunca toca las estrellas."""
    desde, hasta = _rango(anio, mes)
    return (db.query(m.Incidencia)
            .filter(m.Incidencia.persona_id == persona_id,
                    m.Incidencia.fecha >= desde, m.Incidencia.fecha <= hasta,
                    m.Incidencia.autorizada.is_(True),
                    m.Incidencia.gravedad != m.GravedadIncidencia.ERROR_MENOR)
            .order_by(m.Incidencia.gravedad.desc())
            .first())


def evaluar(db: Session, persona_id: int, anio: int, mes: int,
            capacitacion_cumplida: bool = False) -> m.EvaluacionMensual:
    persona = db.get(m.Persona, persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {persona_id}")

    pais_id = persona.plaza.pais_id
    criterios = (db.query(m.CriterioEstrella)
                 .filter_by(pais_id=pais_id, activo=True).all())
    if not criterios:
        raise HTTPException(400, "No hay criterios de estrella configurados para ese pais")

    jornadas = jornadas_del_mes(db, persona_id, anio, mes)

    evaluacion = (db.query(m.EvaluacionMensual)
                  .filter_by(persona_id=persona_id, anio=anio, mes=mes).first())
    if evaluacion:
        if evaluacion.estatus == m.EstatusEvaluacion.PAGADA:
            raise HTTPException(409, "Esa evaluacion ya se pago")
        for r in list(evaluacion.detalle):
            db.delete(r)
        db.flush()
    else:
        evaluacion = m.EvaluacionMensual(
            persona_id=persona_id, anio=anio, mes=mes,
            moneda=db.get(m.Pais, pais_id).moneda_local)
        db.add(evaluacion)
        db.flush()

    evaluacion.jornadas_evaluadas = len(jornadas)
    evaluacion.capacitacion_cumplida = capacitacion_cumplida

    medidas = {
        m.CodigoCriterio.PUNTUALIDAD: medir_puntualidad(db, jornadas),
        m.CodigoCriterio.SEGUIMIENTO_APP: medir_seguimiento(db, jornadas, persona_id),
        m.CodigoCriterio.CIERRE_VIATICOS: medir_cierre_viaticos(db, jornadas, persona_id),
        m.CodigoCriterio.CAPACITACION: {
            "valor": Decimal("100") if capacitacion_cumplida else CERO,
            "detalle": ("Capacitacion del mes cumplida" if capacitacion_cumplida
                        else "Sin registro de capacitacion (dato de Odoo)")},
    }

    # El bono posible del mes es la suma del catalogo. Si algun criterio no
    # aplica, ese monto se reparte entre los que si aplican, para que nadie
    # cobre de menos por algo que no dependio de el.
    bono_posible = sum((Decimal(str(c.monto_mensual)) for c in criterios), CERO)
    aplicables = [c for c in criterios
                  if medidas.get(c.codigo, {}).get("aplica", True)]
    valor_estrella = (bono_posible / len(aplicables)) if aplicables else CERO

    estrellas = 0
    total = CERO
    for criterio in criterios:
        medida = medidas.get(criterio.codigo,
                             {"valor": CERO, "detalle": "Sin medir", "aplica": True})
        aplica = medida.get("aplica", True)
        cumplido = aplica and medida["valor"] >= Decimal(str(criterio.umbral_pct))
        monto = valor_estrella.quantize(Decimal("0.01")) if cumplido else CERO
        if cumplido:
            estrellas += 1
            total += monto
        db.add(m.ResultadoCriterio(
            evaluacion_id=evaluacion.id, criterio_id=criterio.id,
            valor_medido=medida["valor"], umbral=criterio.umbral_pct,
            cumplido=cumplido, aplica=aplica, monto=monto,
            detalle=medida["detalle"]))

    incidencia = incidencia_del_mes(db, persona_id, anio, mes)
    if incidencia:
        evaluacion.anulado_por_incidencia = True
        evaluacion.incidencia_id = incidencia.id
        evaluacion.estrellas = estrellas      # se conservan como referencia
        evaluacion.monto_bono = CERO
    else:
        evaluacion.anulado_por_incidencia = False
        evaluacion.incidencia_id = None
        evaluacion.estrellas = estrellas
        evaluacion.monto_bono = total

    evaluacion.estatus = m.EstatusEvaluacion.CALCULADA
    db.commit()
    db.refresh(evaluacion)
    return evaluacion


def ficha(db: Session, evaluacion: m.EvaluacionMensual) -> dict:
    incidencia = (db.get(m.Incidencia, evaluacion.incidencia_id)
                  if evaluacion.incidencia_id else None)
    return {
        "persona": evaluacion.persona.nombre,
        "periodo": f"{evaluacion.mes:02d}/{evaluacion.anio}",
        "jornadas_evaluadas": evaluacion.jornadas_evaluadas,
        "estrellas": evaluacion.estrellas,
        "bono": evaluacion.monto_bono,
        "moneda": evaluacion.moneda.value,
        "estatus": evaluacion.estatus.value,
        "anulado_por_incidencia": evaluacion.anulado_por_incidencia,
        "incidencia": ({"gravedad": incidencia.gravedad.value,
                        "fecha": incidencia.fecha.isoformat(),
                        "descripcion": incidencia.descripcion}
                       if incidencia else None),
        "estrellas_posibles": sum(1 for r in evaluacion.detalle if r.aplica),
        "criterios": [{
            "criterio": r.criterio.nombre,
            "aplica": r.aplica,
            "medido": float(r.valor_medido),
            "umbral": float(r.umbral),
            "cumplido": r.cumplido,
            "monto": r.monto,
            "detalle": r.detalle,
        } for r in evaluacion.detalle],
    }

"""Comision del consultor.

Sobre facturacion del cliente, descontando los viaticos:
  1 por ciento en implantados, 3 por ciento en eventuales.

Se detona con el cierre VALIDADO por finanzas dentro de las 24 horas,
no con el cierre simplemente capturado. Se paga por servicio facturado,
con corte mensual de todo lo acumulado, sin esperar a la cobranza.
"""
import calendar
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import cierre as motor_cierre
from app import models as m

CERO = Decimal("0")


def _porcentaje(db: Session, pais_id: int, tipo: m.TipoServicio) -> Decimal:
    fila = (db.query(m.PorcentajeComision)
            .filter_by(pais_id=pais_id, tipo_servicio=tipo, activo=True).first())
    if not fila:
        raise HTTPException(400, f"No hay porcentaje de comision configurado para "
                                 f"{tipo.value} en ese pais")
    return Decimal(str(fila.porcentaje))


def incidencia_grave_del_servicio(db: Session, servicio_id: int):
    return (db.query(m.Incidencia)
            .filter_by(servicio_id=servicio_id,
                       gravedad=m.GravedadIncidencia.GRAVE,
                       autorizada=True)
            .first())


def generar(db: Session, servicio_id: int) -> m.ComisionConsultor:
    """Se llama cuando finanzas aprueba el cierre."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    if not servicio.consultor_id:
        raise HTTPException(400, "El servicio no tiene consultor asignado")

    registro = (db.query(m.Cierre)
                .filter_by(servicio_id=servicio_id, contrato_id=None).first())
    if not registro or registro.estatus not in (m.EstatusCierre.APROBADO,
                                                m.EstatusCierre.FACTURADO):
        raise HTTPException(409, "La comision se detona con el cierre validado "
                                 "por finanzas")

    existente = (db.query(m.ComisionConsultor)
                 .filter_by(servicio_id=servicio_id, contrato_id=None,
                            consultor_id=servicio.consultor_id).first())
    if existente:
        return existente

    rent = motor_cierre.rentabilidad(db, servicio_id)
    facturacion = Decimal(str(rent["facturacion"]))
    viaticos = Decimal(str(rent["costos"]["viaticos_comprobados"]))
    base = facturacion - viaticos
    pct = _porcentaje(db, servicio.pais_id, servicio.tipo)
    monto = (base * pct / Decimal("100")).quantize(Decimal("0.01"))

    referencia = registro.aprobado_en or registro.enviado_en
    periodo = referencia.date() if referencia else date.today()

    comision = m.ComisionConsultor(
        servicio_id=servicio_id, consultor_id=servicio.consultor_id,
        anio=periodo.year, mes=periodo.month,
        facturacion=facturacion, viaticos=viaticos, base=base,
        porcentaje=pct, monto=monto,
        moneda=m.Moneda(rent["moneda"]))

    if not registro.dentro_de_plazo:
        comision.estatus = m.EstatusComision.PERDIDA
        comision.monto = CERO
        comision.motivo = ("El consultor no cerro dentro de sus 24 horas: "
                           "se pierde la comision del servicio")
    elif incidencia_grave_del_servicio(db, servicio_id):
        comision.estatus = m.EstatusComision.RETENIDA
        comision.motivo = ("Hay una incidencia grave en el servicio. "
                           "La consecuencia la decide el director general.")

    db.add(comision)
    db.commit()
    db.refresh(comision)
    return comision


def generar_del_mes(db: Session, cierre: m.Cierre) -> m.ComisionConsultor:
    """La comision del consultor por un mes de implantado (seccion 56).

    La misma regla que la del servicio --sobre lo facturado,
    descontando los viaticos; se pierde si el visto bueno salio fuera
    de plazo; se retiene si hubo incidencia grave-- pero por mes,
    porque el implantado se factura mes con mes. La incidencia que
    cuenta es la de ese mes.
    """
    from app import cierre_mes

    servicio = cierre.servicio
    if not servicio.consultor_id:
        raise HTTPException(400, "El servicio no tiene consultor asignado")
    if cierre.estatus not in (m.EstatusCierre.APROBADO,
                              m.EstatusCierre.FACTURADO):
        raise HTTPException(409, "La comision se detona con el cierre validado "
                                 "por finanzas")

    existente = (db.query(m.ComisionConsultor)
                 .filter_by(contrato_id=cierre.contrato_id,
                            consultor_id=servicio.consultor_id).first())
    if existente:
        return existente

    contrato = cierre.contrato
    facturacion = Decimal(str(cierre.total_ejecutado or 0))
    # El costo real de los viaticos del mes es lo comprobado.
    viaticos = sum((Decimal(str(v.monto_comprobado or 0))
                    for v in cierre_mes.viaticos_del_mes(db, contrato)),
                   CERO)
    base = facturacion - viaticos
    pct = _porcentaje(db, servicio.pais_id, servicio.tipo)
    monto = (base * pct / Decimal("100")).quantize(Decimal("0.01"))

    referencia = cierre.aprobado_en or cierre.enviado_en
    periodo = referencia.date() if referencia else date.today()
    pais = db.get(m.Pais, servicio.pais_id)

    comision = m.ComisionConsultor(
        servicio_id=servicio.id, contrato_id=contrato.id,
        consultor_id=servicio.consultor_id,
        anio=periodo.year, mes=periodo.month,
        facturacion=facturacion, viaticos=viaticos, base=base,
        porcentaje=pct, monto=monto, moneda=pais.moneda_local)

    ultimo = calendar.monthrange(contrato.anio, contrato.mes)[1]
    grave = (db.query(m.Incidencia)
             .filter(m.Incidencia.servicio_id == servicio.id,
                     m.Incidencia.gravedad == m.GravedadIncidencia.GRAVE,
                     m.Incidencia.autorizada.is_(True),
                     m.Incidencia.fecha >= date(contrato.anio,
                                                contrato.mes, 1),
                     m.Incidencia.fecha <= date(contrato.anio,
                                                contrato.mes, ultimo))
             .first())
    if not cierre.dentro_de_plazo:
        comision.estatus = m.EstatusComision.PERDIDA
        comision.monto = CERO
        comision.motivo = ("El consultor no dio el visto bueno del mes "
                           "dentro de sus 24 horas: se pierde la comision "
                           "de ese mes")
    elif grave:
        comision.estatus = m.EstatusComision.RETENIDA
        comision.motivo = ("Hay una incidencia grave en el mes. "
                           "La consecuencia la decide el director general.")

    db.add(comision)
    db.commit()
    db.refresh(comision)
    return comision


def del_cierre(db: Session, cierre: m.Cierre) -> dict | None:
    """La comision del consultor por ese cierre, para su tarjeta.

    Si finanzas ya lo cerro, la que se genero. Si todavia esta en
    facturacion, lo que va a ser --o que se pierde, si el visto bueno
    salio fuera de plazo--: el consultor quiere saber cuanto le toca
    antes de que finanzas lo cierre. Antes del visto bueno no hay cifra.
    """
    servicio = cierre.servicio
    if not servicio or not servicio.consultor_id:
        return None
    consulta = db.query(m.ComisionConsultor).filter_by(
        consultor_id=servicio.consultor_id)
    if cierre.contrato_id:
        generada = consulta.filter_by(contrato_id=cierre.contrato_id).first()
    else:
        generada = consulta.filter_by(servicio_id=servicio.id,
                                      contrato_id=None).first()
    if generada:
        return {"generada": True, "estatus": generada.estatus.value,
                "monto": generada.monto, "base": generada.base,
                "porcentaje": float(generada.porcentaje),
                "moneda": generada.moneda.value, "motivo": generada.motivo}
    if not cierre.enviado_en or cierre.estatus not in (
            m.EstatusCierre.ENVIADO_FINANZAS, m.EstatusCierre.APROBADO,
            m.EstatusCierre.FACTURADO):
        return None
    if cierre.dentro_de_plazo is False:
        return {"generada": False, "estatus": "se_pierde", "monto": CERO,
                "base": None, "porcentaje": None, "moneda": None,
                "motivo": "El visto bueno salio fuera de plazo"}
    try:
        pct = _porcentaje(db, servicio.pais_id, servicio.tipo)
    except HTTPException:
        return None
    if cierre.contrato_id:
        from app import cierre_mes
        viaticos = cierre_mes.viaticos_del_mes(db, cierre.contrato)
        pais = db.get(m.Pais, servicio.pais_id)
        moneda = pais.moneda_local.value if pais else None
    else:
        viaticos = motor_cierre.viaticos_del_servicio(db, servicio.id)
        from app import cotizacion as cot
        vigente = cot.vigente(db, servicio.id)
        moneda = vigente.moneda.value if vigente else None
    comprobado = sum((Decimal(str(v.monto_comprobado or 0))
                      for v in viaticos), CERO)
    base = Decimal(str(cierre.total_ejecutado or 0)) - comprobado
    return {"generada": False, "estatus": "por_generar",
            "monto": (base * pct / Decimal("100")).quantize(Decimal("0.01")),
            "base": base, "porcentaje": float(pct), "moneda": moneda,
            "motivo": None}


def solo_la_suya(datos, usuario: m.Usuario):
    """Un consultor ve su comision, no la de otro.

    La misma regla que su corte ("Solo puedes ver tu propio corte"): la
    tarjeta del cierre y la bandeja de facturacion traen la comision, y
    un consultor puede abrir el servicio de un companero. Se apaga en
    todo renglon cuya comision sea de otro; los demas roles la ven como
    antes. Devuelve los mismos datos, ya limpios.
    """
    if usuario is None or usuario.rol != m.Rol.CONSULTOR:
        return datos

    def limpiar(x):
        if isinstance(x, dict):
            if x.get("comision") is not None:
                duenio = x.get("consultor_id")
                if duenio is None and isinstance(x.get("consultor"), dict):
                    duenio = x["consultor"].get("id")
                if duenio != usuario.persona_id:
                    x["comision"] = None
            for valor in x.values():
                limpiar(valor)
        elif isinstance(x, list):
            for valor in x:
                limpiar(valor)

    limpiar(datos)
    return datos


def resolver_retenida(db: Session, comision_id: int, se_paga: bool,
                      resolucion: str) -> m.ComisionConsultor:
    """En incidencia grave no hay regla automatica: decide el director general."""
    comision = db.get(m.ComisionConsultor, comision_id)
    if not comision:
        raise HTTPException(404, f"No existe la comision {comision_id}")
    if comision.estatus != m.EstatusComision.RETENIDA:
        raise HTTPException(409, f"La comision esta en {comision.estatus.value}")
    if len(resolucion.strip()) < 15:
        raise HTTPException(400, "Explica la decision con mas detalle")

    if se_paga:
        comision.estatus = m.EstatusComision.GENERADA
    else:
        comision.estatus = m.EstatusComision.PERDIDA
        comision.monto = CERO
    comision.motivo = resolucion
    db.commit()
    db.refresh(comision)
    return comision


def cancelar_por_no_cobro(db: Session, comision_id: int, anio: int, mes: int,
                          motivo: str) -> dict:
    """Nota de credito o cancelacion: resta en el corte siguiente."""
    comision = db.get(m.ComisionConsultor, comision_id)
    if not comision:
        raise HTTPException(404, f"No existe la comision {comision_id}")
    if comision.estatus == m.EstatusComision.AJUSTADA:
        raise HTTPException(409, "Esa comision ya tiene ajuste registrado")

    ajuste = m.AjusteComision(
        comision_id=comision.id, consultor_id=comision.consultor_id,
        anio=anio, mes=mes, monto=-Decimal(str(comision.monto)), motivo=motivo)
    db.add(ajuste)
    comision.estatus = m.EstatusComision.AJUSTADA
    db.commit()

    return {"resultado": "ajuste registrado",
            "se_resta_en": f"{mes:02d}/{anio}",
            "monto": float(ajuste.monto), "motivo": motivo}


def corte_mensual(db: Session, consultor_id: int, anio: int, mes: int) -> dict:
    """Todo lo acumulado del mes, mas los ajustes que caen en este corte."""
    consultor = db.get(m.Persona, consultor_id)
    if not consultor:
        raise HTTPException(404, f"No existe la persona {consultor_id}")

    comisiones = (db.query(m.ComisionConsultor)
                  .filter_by(consultor_id=consultor_id, anio=anio, mes=mes).all())
    ajustes = (db.query(m.AjusteComision)
               .filter_by(consultor_id=consultor_id, anio=anio, mes=mes).all())

    pagables = [c for c in comisiones
                if c.estatus in (m.EstatusComision.GENERADA, m.EstatusComision.PAGADA)]
    subtotal = sum((Decimal(str(c.monto)) for c in pagables), CERO)
    total_ajustes = sum((Decimal(str(a.monto)) for a in ajustes), CERO)

    return {
        "consultor": consultor.nombre,
        "periodo": f"{mes:02d}/{anio}",
        "servicios": [{
            "servicio": c.servicio.folio,
            "tipo": c.servicio.tipo.value,
            "facturacion": c.facturacion,
            "viaticos_descontados": c.viaticos,
            "base": c.base,
            "porcentaje": float(c.porcentaje),
            "monto": c.monto,
            "estatus": c.estatus.value,
            "motivo": c.motivo,
        } for c in comisiones],
        "ajustes": [{"motivo": a.motivo, "monto": a.monto} for a in ajustes],
        "subtotal": subtotal,
        "ajustes_total": total_ajustes,
        "total_a_pagar": subtotal + total_ajustes,
        "moneda": comisiones[0].moneda.value if comisiones else None,
    }

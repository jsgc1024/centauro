"""Cierre del servicio: comparativo contra la cotizacion y rentabilidad.

El comparativo busca desviaciones: dias de mas o de menos, recursos no
cotizados, horas extra, y viaticos mal dispersados o sin comprobar.
Solo las desviaciones sin respaldo detonan el escalamiento.
"""
import math
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import cotizacion as cot
from app import models as m

HORAS_CONSULTOR = 24
HORAS_MAXIMO_TOTAL = 48
CERO = Decimal("0")


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


# ---------------------------------------------------------------- ejecutado

def factor_festivo(db: Session, pais_id: int, fecha) -> Decimal:
    """En dia festivo la comision del personal se paga al doble.
    El festivo se trabaja como dia normal; lo que cambia es lo que se le paga."""
    festivo = (db.query(m.DiaFestivo)
               .filter_by(pais_id=pais_id, fecha=fecha, activo=True).first())
    return _d(festivo.factor_comision) if festivo else Decimal("1")


def _horas_extra(jornada: m.Jornada) -> int:
    """Horas extra completas despues del fin programado.
    Las 12 horas son exactas, sin tolerancia."""
    if not jornada.modalidad.aplica_horas_extra or not jornada.fin_real:
        return 0
    exceso = (jornada.fin_real - jornada.fin_programado).total_seconds() / 3600
    return max(0, math.ceil(exceso)) if exceso > 0 else 0


def ejecutado(db: Session, servicio: m.Servicio, tarifario_id: int) -> dict:
    """Lo que realmente se presto, valuado al tarifario del cliente."""
    detalle = []
    total = CERO
    horas_extra_total = 0

    for equipo in servicio.equipos:
        for j in equipo.jornadas:
            if j.estatus == m.EstatusJornada.CANCELADA:
                continue
            ejecutada = j.fin_real is not None or j.estatus == m.EstatusJornada.TERMINADA
            if not ejecutada:
                continue

            extras = _horas_extra(j)
            horas_extra_total += extras

            for a in j.personal:
                # Se cobra el rol con el que fue ese dia, no lo que la
                # persona es: eso es lo que se le vendio al cliente.
                tarifa = cot.precio_recurso(db, tarifario_id, a.rol_id,
                                            j.modalidad_id)
                importe = _d(tarifa.precio)
                linea = {"fecha": j.fecha.isoformat(), "equipo": equipo.alias,
                         "tipo": "recurso", "referencia_id": a.rol_id,
                         "descripcion": a.rol.nombre if a.rol else None,
                         "cantidad": 1, "importe": importe}
                if extras and tarifa.precio_hora_extra:
                    extra_importe = _d(tarifa.precio_hora_extra) * extras
                    importe += extra_importe
                    linea["horas_extra"] = extras
                    linea["importe_horas_extra"] = extra_importe
                    linea["importe"] = importe
                detalle.append(linea)
                total += importe

            for a in j.vehiculos:
                tarifa = cot.precio_vehiculo(db, tarifario_id, a.vehiculo.categoria_id,
                                             j.modalidad_id)
                importe = _d(tarifa.precio)
                detalle.append({"fecha": j.fecha.isoformat(), "equipo": equipo.alias,
                                "tipo": "vehiculo", "referencia_id": a.vehiculo.categoria_id,
                                "descripcion": a.vehiculo.categoria.nombre,
                                "cantidad": 1, "importe": importe})
                total += importe

    return {"detalle": detalle, "total": total, "horas_extra": horas_extra_total}


# ---------------------------------------------------------------- comparativo

def _clave(linea) -> tuple:
    return (linea["fecha"], linea["equipo"], linea["tipo"], linea["referencia_id"])


def _viatico_facturable(cotizacion, comprobado: Decimal) -> Decimal:
    """Cuanto de viaticos se le suma a la factura del cliente.

    Si la cotizacion los llevaba incluidos, el cliente ya los pago dentro
    del precio: no se le suma nada, pase lo que pase con la comprobacion.
    Si se cobran por comprobar, se le factura lo comprobado valido, que ya
    excluye lo rechazado.
    """
    if cotizacion.viaticos_incluidos:
        return CERO
    return comprobado


def _viaticos_del_comparativo(cotizacion, asignado, comprobado, devuelto,
                              rechazado, descontado, absorbido) -> dict:
    incluidos = cotizacion.viaticos_incluidos
    return {
        "asignado": asignado,
        "comprobado": comprobado,
        "devuelto": devuelto,
        "pendiente": asignado - comprobado - devuelto,
        # Lo rechazado no es costo de la empresa: se recupera del personal.
        "rechazado_no_facturable": rechazado,
        "descontado_al_personal": descontado,
        "absorbido_por_la_empresa": absorbido,
        "modo_cobro": "incluidos_en_cotizacion" if incluidos else "por_comprobar",
        "facturable_al_cliente": _viatico_facturable(cotizacion, comprobado),
        "nota_facturacion": (
            "Los viaticos van dentro del precio cotizado: la factura no "
            "cambia por lo que haya pasado con la comprobacion."
            if incluidos else
            "Se factura lo comprobado valido. Lo rechazado no se le cobra "
            "al cliente."),
    }


def comparar(db: Session, servicio_id: int) -> dict:
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    cotizacion = cot.vigente(db, servicio_id)
    if not cotizacion:
        raise HTTPException(409, "El servicio no tiene cotizacion autorizada")

    cotizado = [{
        "fecha": l.fecha.isoformat(), "equipo": l.equipo_clave,
        "tipo": l.tipo.value,
        "referencia_id": l.perfil_id if l.tipo == m.TipoLinea.RECURSO else l.categoria_id,
        "descripcion": l.descripcion, "cantidad": l.cantidad,
        "importe": _d(l.subtotal),
    } for l in cotizacion.lineas if l.tipo != m.TipoLinea.VIATICOS]

    real = ejecutado(db, servicio, cotizacion.tarifario_id)

    # agrupar por clave
    mapa_cot, mapa_eje = {}, {}
    for l in cotizado:
        k = _clave(l)
        mapa_cot.setdefault(k, {"cantidad": 0, "importe": CERO, "descripcion": l["descripcion"]})
        mapa_cot[k]["cantidad"] += l["cantidad"]
        mapa_cot[k]["importe"] += l["importe"]
    for l in real["detalle"]:
        k = _clave(l)
        mapa_eje.setdefault(k, {"cantidad": 0, "importe": CERO, "descripcion": l["descripcion"]})
        mapa_eje[k]["cantidad"] += l["cantidad"]
        mapa_eje[k]["importe"] += l["importe"]

    desviaciones = []

    for k, v in mapa_cot.items():
        fecha, equipo, tipo, _ = k
        if k not in mapa_eje:
            desviaciones.append({
                "tipo": m.TipoDesviacion.DIAS_DE_MENOS.value,
                "descripcion": f"{fecha} {equipo}: se cotizo {v['descripcion']} "
                               f"y no se ejecuto",
                "monto": -v["importe"]})

    for k, v in mapa_eje.items():
        fecha, equipo, tipo, _ = k
        if k not in mapa_cot:
            desviaciones.append({
                "tipo": m.TipoDesviacion.RECURSO_NO_COTIZADO.value,
                "descripcion": f"{fecha} {equipo}: se ejecuto {v['descripcion']} "
                               f"sin estar cotizado",
                "monto": v["importe"]})
        else:
            diferencia = v["importe"] - mapa_cot[k]["importe"]
            if diferencia > 0:
                desviaciones.append({
                    "tipo": m.TipoDesviacion.HORAS_EXTRA.value if real["horas_extra"]
                            else m.TipoDesviacion.DIAS_DE_MAS.value,
                    "descripcion": f"{fecha} {equipo}: {v['descripcion']} cobra "
                                   f"{diferencia} mas de lo cotizado",
                    "monto": diferencia})
            elif diferencia < 0:
                desviaciones.append({
                    "tipo": m.TipoDesviacion.COBRO_MENOR.value,
                    "descripcion": f"{fecha} {equipo}: {v['descripcion']} cobra "
                                   f"{abs(diferencia)} menos de lo cotizado",
                    "monto": diferencia})

    # ---- viaticos
    viaticos = (db.query(m.AsignacionViatico)
                .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
                .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                .filter(m.Equipo.servicio_id == servicio_id).all())

    asignado = sum((_d(v.monto_total) for v in viaticos), CERO)
    comprobado = sum((_d(v.monto_comprobado) for v in viaticos), CERO)
    devuelto = sum((_d(v.monto_devuelto) for v in viaticos), CERO)

    descontado = sum((_d(v.monto_descontado) for v in viaticos), CERO)
    absorbido = sum((_d(v.monto_absorbido) for v in viaticos), CERO)
    rechazado = sum((_d(c.monto) for v in viaticos for c in v.comprobantes
                     if c.rechazado), CERO)

    for v in viaticos:
        pendiente = _d(v.monto_total) - _d(v.monto_comprobado) - _d(v.monto_devuelto)
        if v.cerrado_con_descuento:
            # Ya esta resuelto: no es un pendiente, es una decision tomada.
            # Se informa para que finanzas lo vea, pero no frena el envio.
            desviaciones.append({
                "tipo": m.TipoDesviacion.VIATICO_SIN_COMPROBAR.value,
                "descripcion": (f"{v.persona.nombre}: cierre con descuento de "
                                f"{_d(v.monto_descontado)}"
                                + (f", {_d(v.monto_absorbido)} absorbido por la "
                                   f"empresa" if _d(v.monto_absorbido) else "")
                                + f". {v.motivo_cierre or ''}"),
                "monto": _d(v.monto_descontado),
                "respaldada": True})
            continue
        if pendiente != CERO:
            desviaciones.append({
                "tipo": m.TipoDesviacion.VIATICO_SIN_COMPROBAR.value,
                "descripcion": f"{v.persona.nombre}: {abs(pendiente)} "
                               f"{'sin comprobar ni devolver' if pendiente > 0 else 'comprobado de mas'}",
                "monto": pendiente})
        if v.estatus != m.EstatusViatico.CERRADO:
            desviaciones.append({
                "tipo": m.TipoDesviacion.VIATICO_NO_CERRADO.value,
                "descripcion": f"{v.persona.nombre}: viaticos en estatus "
                               f"{v.estatus.value}",
                "monto": CERO})

    return {
        "servicio": servicio.folio,
        "cotizacion": {"version": cotizacion.version, "total": _d(cotizacion.total),
                       "moneda": cotizacion.moneda.value,
                       "viaticos_incluidos": cotizacion.viaticos_incluidos},
        "ejecutado": {"total": real["total"], "horas_extra": real["horas_extra"]},
        "diferencia": real["total"] - _d(cotizacion.total),
        "viaticos": _viaticos_del_comparativo(
            cotizacion, asignado, comprobado, devuelto, rechazado,
            descontado, absorbido),
        "desviaciones": desviaciones,
        "sin_desviaciones": not desviaciones,
    }


# ---------------------------------------------------------------- rentabilidad

def rentabilidad(db: Session, servicio_id: int) -> dict:
    """Tres bloques: facturacion, costo directo de personal y viaticos,
    y costo del vehiculo."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    cotizacion = cot.vigente(db, servicio_id)
    if not cotizacion:
        raise HTTPException(409, "El servicio no tiene cotizacion autorizada")

    real = ejecutado(db, servicio, cotizacion.tarifario_id)
    facturacion = real["total"]

    costo_personal = CERO
    costo_vehiculo = CERO
    dias_vehiculo = 0
    dias_festivos = 0

    for equipo in servicio.equipos:
        for j in equipo.jornadas:
            if j.estatus == m.EstatusJornada.CANCELADA:
                continue
            if not (j.fin_real or j.estatus == m.EstatusJornada.TERMINADA):
                continue

            extras = _horas_extra(j)
            factor = factor_festivo(db, servicio.pais_id, j.fecha)
            if factor > 1:
                dias_festivos += 1
            for a in j.personal:
                comision = None
                if a.rol_id:
                    comision = (db.query(m.ComisionPersonal)
                                .filter_by(pais_id=servicio.pais_id,
                                           perfil_id=a.rol_id,
                                           tipo_servicio=servicio.tipo,
                                           modalidad_id=j.modalidad_id).first())
                if comision:
                    costo_personal += _d(comision.monto) * factor
                    if extras and comision.monto_hora_extra:
                        costo_personal += _d(comision.monto_hora_extra) * extras * factor

            for a in j.vehiculos:
                if a.vehiculo.costo_diario:
                    costo_vehiculo += _d(a.vehiculo.costo_diario)
                dias_vehiculo += 1

    viaticos = (db.query(m.AsignacionViatico)
                .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
                .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                .filter(m.Equipo.servicio_id == servicio_id).all())
    # El costo real es lo comprobado, no lo dispersado.
    costo_viaticos = sum((_d(v.monto_comprobado) for v in viaticos), CERO)

    costo_total = costo_personal + costo_viaticos + costo_vehiculo
    utilidad = facturacion - costo_total
    margen = (utilidad / facturacion * 100) if facturacion else CERO

    return {
        "servicio": servicio.folio,
        "moneda": cotizacion.moneda.value,
        "facturacion": facturacion,
        "costos": {
            "personal": costo_personal,
            "dias_festivos_pagados_al_doble": dias_festivos,
            "viaticos_comprobados": costo_viaticos,
            "vehiculo": costo_vehiculo,
            "dias_vehiculo": dias_vehiculo,
            "total": costo_total,
        },
        "utilidad": utilidad,
        "margen_pct": round(float(margen), 2),
    }


# ---------------------------------------------------------------- flujo

def abrir(db: Session, servicio_id: int, abierto_en: datetime | None = None) -> m.Cierre:
    """Arranca el reloj de las 24 horas del consultor."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    existente = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()
    if existente:
        return existente

    momento = abierto_en or datetime.now()
    cierre = m.Cierre(servicio_id=servicio_id, abierto_en=momento,
                      limite_consultor=momento + timedelta(hours=HORAS_CONSULTOR))
    db.add(cierre)
    db.commit()
    db.refresh(cierre)
    return cierre

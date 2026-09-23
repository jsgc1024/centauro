"""Cierre del servicio: comparativo contra la cotizacion y rentabilidad.

El comparativo busca desviaciones: dias de mas o de menos, recursos no
cotizados, horas extra, y viaticos mal dispersados o sin comprobar.
Solo las desviaciones sin respaldo detonan el escalamiento.
"""
import logging
import math
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import cotizacion as cot
from app import models as m
from app import reloj

# Los dos relojes (decision de Salvador, 22 sep). T0 es el termino
# general del servicio: de T0 a T0 + 24 el personal comprueba sus
# viaticos. T1 llega al vencer ese plazo --o antes, si todo el dinero
# ya cerro--: de T1 a T1 + 24 el consultor da el visto bueno. Si nadie
# se adelanta, los dos suman 48 horas desde el termino.
HORAS_PERSONAL = 24
HORAS_CONSULTOR = 24
HORAS_MAXIMO_TOTAL = HORAS_PERSONAL + HORAS_CONSULTOR
CERO = Decimal("0")
registro = logging.getLogger(__name__)


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
                # La asignacion relevada no se le cobra al cliente. Ese
                # dia hubo dos personas porque una salio a media jornada
                # y entro otra: el cliente tuvo un conductor, no dos. A
                # la empresa si le costaron los dos (ver `utilidad`), y
                # esa diferencia es el costo de la contingencia.
                if a.relevado_en:
                    continue
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
                # Lo mismo con la unidad relevada: el cliente tuvo una
                # camioneta ese dia, aunque en la base haya dos filas.
                if a.relevado_en:
                    continue
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


def viaticos_por_cobrar(db: Session, servicio_id: int,
                        cotizacion) -> Decimal:
    """Los viaticos que se le cobran al cliente aparte (seccion 57).

    Lo dice la cotizacion, y son dos opciones distintas: incluidos, el
    cliente ya los paga dentro del precio y la factura no suma nada;
    por comprobar, se le factura lo comprobado valido --sin lo
    rechazado ni lo enviado a descuento, que no es gasto del servicio--.
    """
    comprobado = sum((_d(v.monto_comprobado) for v in (
        db.query(m.AsignacionViatico)
        .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
        .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
        .filter(m.Equipo.servicio_id == servicio_id).all())), CERO)
    return _viatico_facturable(cotizacion, comprobado)


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
        mapa_eje.setdefault(k, {"cantidad": 0, "importe": CERO,
                                "extra": CERO, "descripcion": l["descripcion"]})
        mapa_eje[k]["cantidad"] += l["cantidad"]
        mapa_eje[k]["importe"] += l["importe"]
        # Cuanto de esa linea son horas extra. Se guarda por linea y no
        # por servicio: es lo unico que puede decir si el sobrecosto de
        # ESTE renglon se explica solo.
        mapa_eje[k]["extra"] += l.get("importe_horas_extra") or CERO

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
                # Horas extra solo si las de ESTE renglon lo explican
                # completo. Antes bastaba con que hubiera una sola hora
                # extra en cualquier dia del servicio para etiquetar asi
                # todos los sobrecostos, y "horas extra" es informativo:
                # el cobro de mas se iba a facturacion sin que nadie lo
                # recotizara. Lo que no explica la hora extra es un dia
                # de mas, y eso si hay que corregirlo antes de enviar.
                explicado = v["extra"] > 0 and diferencia <= v["extra"]
                desviaciones.append({
                    "tipo": (m.TipoDesviacion.HORAS_EXTRA.value if explicado
                             else m.TipoDesviacion.DIAS_DE_MAS.value),
                    "descripcion": f"{fecha} {equipo}: {v['descripcion']} cobra "
                                   f"{diferencia} mas de lo cotizado"
                                   + (f" ({v['extra']} son horas extra)"
                                      if v["extra"] and not explicado else ""),
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
    # Lo que se le factura: lo ejecutado y, si la cotizacion cobra los
    # viaticos aparte, lo comprobado (seccion 57). Sin esto la utilidad
    # y la comision restaban unos viaticos que no se facturaban.
    viaticos_cobrados = viaticos_por_cobrar(db, servicio_id, cotizacion)
    facturacion = real["total"] + viaticos_cobrados

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
            # Aqui si entran las relevadas: a la empresa le costaron las
            # dos. Lo que el cliente no paga de ese dia es el costo de la
            # contingencia, y sale solo en esta resta.
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
        "viaticos_cobrados": viaticos_cobrados,
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

def estado(db: Session, servicio_id: int,
           ahora: datetime | None = None) -> dict:
    """El reloj del consultor, solo.

    Vive aparte de la revision a proposito: **el plazo corre igual**
    --arranca cuando el servicio termina, tenga cotizacion o no-- y hay
    pantallas que solo necesitan el reloj, sin cargar el comparativo
    entero para pintarlo.

    Se manda el limite Y el momento, los dos en hora del pais del
    servicio: la cuenta regresiva sale de la resta entre ellos y no del
    reloj de la maquina donde este abierta la consola. De este plazo
    depende que el consultor cobre su comision; no puede depender de la
    hora de una laptop.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    ahora = reloj.ahora_del_servicio(db, servicio, ahora)
    # El del servicio. El implantado lleva uno por mes y se lee con
    # `cierre_mes.estado`.
    fila = (db.query(m.Cierre)
            .filter_by(servicio_id=servicio_id, contrato_id=None).first())
    if not fila:
        return {"momento": ahora.isoformat(), "existe": False,
                "cierre_id": None, "estatus": None, "fase": None,
                "abierto_en": None, "comprobacion_hasta": None,
                "visto_bueno_desde": None, "limite": None,
                "minutos_restantes": None, "viaticos_abiertos": None,
                "motivo": None, "factura": None, "factura_error": None}

    def iso(momento):
        return momento.isoformat() if momento else None

    return {
        "momento": ahora.isoformat(),
        "existe": True,
        "cierre_id": fila.id,
        "estatus": fila.estatus.value,
        # La fase, para las pantallas: en que reloj va.
        "fase": FASES.get(fila.estatus),
        "abierto_en": iso(fila.abierto_en),
        "comprobacion_hasta": iso(fila.comprobacion_hasta),
        "visto_bueno_desde": iso(fila.visto_bueno_desde),
        "limite": iso(fila.limite_consultor),
        "minutos_restantes": int(
            (fila.limite_consultor - ahora).total_seconds() / 60),
        "viaticos_abiertos": viaticos_abiertos(db, servicio_id),
        "motivo": fila.motivo_apertura,
        "factura": fila.factura_odoo,
        "factura_error": fila.factura_error,
    }


def abrir(db: Session, servicio_id: int, abierto_en: datetime | None = None,
          motivo: str = "termino") -> m.Cierre:
    """Arranca el primer reloj: las 24 horas del personal.

    `abierto_en` es T0 --el termino general, o la cancelacion--. De ahi
    salen `comprobacion_hasta` (T0 + 24 h) y, provisional, el limite
    del consultor en T0 + 48 h: el de verdad lo pone `avanzar` cuando
    llega T1.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    # El implantado no termina: cierra por mes, solo, al cerrar el ultimo
    # dia trabajado de cada mes (`cierre_mes`, seccion 56). Un cierre del
    # servicio entero lo sacaria de esa cadena.
    if servicio.tipo == m.TipoServicio.IMPLANTADO:
        raise HTTPException(409, {
            "mensaje": "El implantado cierra por mes, no por servicio",
            "que_hacer": "El cierre de cada mes arranca solo al cerrar su "
                         "ultimo dia trabajado."})

    existente = (db.query(m.Cierre)
                 .filter_by(servicio_id=servicio_id, contrato_id=None).first())
    if existente:
        return existente

    # En hora del pais del servicio. El plazo de 24 horas del consultor
    # decide si cobra su comision: si nace con el reloj del contenedor y
    # se juzga con otro, queda torcido desde el principio.
    momento = reloj.ahora_del_servicio(db, servicio, abierto_en)
    hasta = momento + timedelta(hours=HORAS_PERSONAL)
    cierre = m.Cierre(servicio_id=servicio_id, abierto_en=momento,
                      comprobacion_hasta=hasta,
                      limite_consultor=hasta + timedelta(hours=HORAS_CONSULTOR),
                      motivo_apertura=motivo)
    db.add(cierre)
    # `flush` y no `commit`: esto se llama tambien desde adentro del
    # cierre del ultimo dia, y ahi commitear a media transaccion partiria
    # en dos una operacion que tiene que ser una sola --la marca de fin y
    # el arranque del reloj--. Quien llama decide cuando guardar.
    db.flush()
    return cierre


# ---------------------------------------------------------------- el segundo reloj

# La fase, para las pantallas: lo que cada estatus del cierre quiere
# decir en la cadena de dos relojes.
FASES = {
    m.EstatusCierre.ABIERTO: "comprobacion",
    m.EstatusCierre.SIN_VISTO_BUENO: "sin_visto_bueno",
    m.EstatusCierre.EN_REVISION_IA: "sin_visto_bueno",
    m.EstatusCierre.DEVUELTO_A_OPERACION: "devuelto",
    m.EstatusCierre.ENVIADO_FINANZAS: "en_facturacion",
    m.EstatusCierre.APROBADO: "aprobado",
    m.EstatusCierre.FACTURADO: "facturado",
}

# Lo que ya no cuenta como dinero afuera.
VIATICO_RESUELTO = (m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO,
                    m.EstatusViatico.CANCELADO)


def viaticos_abiertos(db: Session, servicio_id: int) -> int:
    """Cuantos viaticos del servicio siguen sin cerrar."""
    return (db.query(m.AsignacionViatico)
            .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == servicio_id,
                    m.AsignacionViatico.estatus.notin_(VIATICO_RESUELTO))
            .count())


def _dinero_afuera(db: Session, cierre: m.Cierre) -> int:
    """Los viaticos sin cerrar de lo que cierra: el servicio entero en
    el eventual; en el implantado, solo los del mes (seccion 56)."""
    if cierre.contrato_id:
        from app import cierre_mes
        return cierre_mes.viaticos_abiertos(db, cierre.contrato)
    return viaticos_abiertos(db, cierre.servicio_id)


def avanzar(db: Session, cierre: m.Cierre,
            ahora: datetime | None = None) -> bool:
    """De la comprobacion al visto bueno: pone T1 y el limite del consultor.

    Lo mueve el reloj del sistema, no una persona. T1 llega cuando
    vencen las 24 h del personal (T0 + 24) o antes, si todos los
    viaticos del servicio ya cerraron, se devolvieron o se cancelaron:
    no hay nada que esperar (decision 2 de la propuesta).

    Solo escribe; quien llama decide cuando guardar. Devuelve si movio.
    """
    if cierre.estatus != m.EstatusCierre.ABIERTO:
        return False
    servicio = cierre.servicio
    ahora = reloj.ahora_del_servicio(db, servicio, ahora)

    viejo = cierre.comprobacion_hasta is None
    if viejo:
        # Nacio antes de los dos relojes: su plazo era el de siempre, 24 h
        # desde que se abrio. Se respeta tal cual (regla 10 de la
        # propuesta): lo ya terminado no se toca.
        t1, limite = cierre.abierto_en, cierre.limite_consultor
    elif ahora >= cierre.comprobacion_hasta:
        t1 = cierre.comprobacion_hasta
        limite = t1 + timedelta(hours=HORAS_CONSULTOR)
    elif _dinero_afuera(db, cierre) == 0:
        t1 = ahora
        limite = t1 + timedelta(hours=HORAS_CONSULTOR)
    else:
        return False

    cierre.visto_bueno_desde = t1
    cierre.limite_consultor = limite
    cierre.estatus = m.EstatusCierre.SIN_VISTO_BUENO
    # El cancelado se queda cancelado: su rastro es el cierre.
    if servicio.estatus == m.EstatusServicio.TERMINADO:
        servicio.estatus = m.EstatusServicio.SIN_VISTO_BUENO

    if servicio.consultor_id and not viejo:
        from app import push
        # En el implantado el visto bueno es del mes y se da en su
        # panel (seccion 56).
        de_que = (f"{servicio.folio} {cierre.contrato.mes:02d}/"
                  f"{cierre.contrato.anio}" if cierre.contrato_id
                  else servicio.folio)
        pantalla = (f"/consola/#/implantado/{servicio.id}"
                    if cierre.contrato_id
                    else f"/consola/#/servicio/{servicio.id}")
        try:
            push.avisar(
                db, servicio.consultor_id,
                titulo=f"{de_que}: tienes 24 h para el visto bueno",
                cuerpo=("La comprobacion del personal termino. Tu plazo "
                        f"vence el {limite:%d/%m a las %H:%M}."),
                # El consultor trabaja en la consola, no en la app de campo.
                url=pantalla,
                etiqueta=f"visto-bueno-{cierre.id}")
        except Exception:                 # noqa: BLE001
            # Un aviso que no sale no puede frenar el reloj.
            registro.exception("no se pudo avisar el visto bueno de %s",
                               servicio.folio)
    return True


def avanzar_cierres(db: Session, ahora: datetime | None = None) -> list[str]:
    """El barrido de cada cinco minutos: lo que llego a T1 pasa a sin
    visto bueno. Devuelve los folios que movio."""
    movidos = []
    for cierre in (db.query(m.Cierre)
                   .filter(m.Cierre.estatus == m.EstatusCierre.ABIERTO)
                   .all()):
        if avanzar(db, cierre, ahora):
            # El mes del implantado se dice con su mes: el folio es el
            # mismo todo el contrato.
            movidos.append(
                cierre.servicio.folio if not cierre.contrato_id else
                f"{cierre.servicio.folio} {cierre.contrato.mes:02d}/"
                f"{cierre.contrato.anio}")
    db.commit()
    return movidos

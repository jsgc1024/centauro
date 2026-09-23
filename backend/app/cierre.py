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


# ---------------------------------------------------------------- gastos

# Como se le cobran los gastos al cliente (decision de Salvador, 23 sep;
# seccion 59). Son sus dos tratos:
#
# * A precio alzado: el cliente pidio un monto fijo desde la propuesta y
#   la cotizacion lo lleva en sus renglones de gastos. Se factura ese
#   monto, se gaste mas o menos: lo que sobra es margen y lo que se pasa
#   lo absorbe Centauro. Sin renglones de gastos, los gastos van dentro
#   del precio y no se suma nada.
# * Gastos netos: se factura lo comprobado valido y el cliente recibe el
#   desglose al final.
#
# En los dos el personal comprueba todo igual: es el control de la casa.
# La columna se sigue llamando `viaticos_incluidos` (seccion 57, cuando
# se decia "incluidos o aparte"): verdadero es precio alzado.
PRECIO_ALZADO = "precio_alzado"
NETOS = "netos"


def modo_de_gastos(incluidos: bool) -> str:
    return PRECIO_ALZADO if incluidos else NETOS


def gastos_cotizados(cotizacion) -> Decimal:
    """El monto fijo de gastos de la propuesta: sus renglones de gastos."""
    return sum((_d(l.subtotal) for l in cotizacion.lineas
                if l.tipo == m.TipoLinea.VIATICOS), CERO)


def _viatico_facturable(cotizacion, comprobado: Decimal) -> Decimal:
    """Cuanto de gastos lleva la factura del cliente.

    A precio alzado, el monto fijo de la cotizacion, pase lo que pase
    con la comprobacion --hasta la seccion 59 ese monto no llegaba a la
    factura: el servicio se cobraba sin los gastos--. Netos, lo
    comprobado valido, que ya excluye lo rechazado.
    """
    if cotizacion.viaticos_incluidos:
        return gastos_cotizados(cotizacion)
    return comprobado


def _viaticos_del_comparativo(cotizacion, asignado, comprobado, devuelto,
                              rechazado, descontado, absorbido) -> dict:
    alzado = cotizacion.viaticos_incluidos
    return {
        "asignado": asignado,
        "comprobado": comprobado,
        "devuelto": devuelto,
        "pendiente": asignado - comprobado - devuelto,
        # Lo rechazado no es costo de la empresa: se recupera del personal.
        "rechazado_no_facturable": rechazado,
        "descontado_al_personal": descontado,
        "absorbido_por_la_empresa": absorbido,
        "modo_cobro": modo_de_gastos(alzado),
        "gastos_cotizados": gastos_cotizados(cotizacion),
        "facturable_al_cliente": _viatico_facturable(cotizacion, comprobado),
        "nota_facturacion": (
            "A precio alzado se factura el monto fijo de la propuesta, se "
            "gaste mas o menos. Si no lleva monto, los gastos van dentro "
            "del precio."
            if alzado else
            "Gastos netos: se factura lo comprobado valido. Lo rechazado y "
            "lo que se desconto al personal no se le cobra al cliente."),
    }


def viaticos_por_cobrar(db: Session, servicio_id: int,
                        cotizacion) -> Decimal:
    """Los gastos que lleva la factura del cliente (seccion 59).

    A precio alzado, el monto fijo de la cotizacion; netos, lo
    comprobado valido --sin lo rechazado ni lo enviado a descuento, que
    no es gasto del servicio--.
    """
    if cotizacion.viaticos_incluidos:
        return gastos_cotizados(cotizacion)
    comprobado = sum((_d(v.monto_comprobado) for v in (
        db.query(m.AsignacionViatico)
        .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
        .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
        .filter(m.Equipo.servicio_id == servicio_id).all())), CERO)
    return comprobado


def viaticos_del_servicio(db: Session, servicio_id: int) -> list:
    """Todo el dinero del servicio, dia por dia y persona por persona."""
    return (db.query(m.AsignacionViatico)
            .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == servicio_id).all())


def desviaciones_del_dinero(viaticos: list) -> list[dict]:
    """Lo que el dinero del servicio le dice a finanzas, persona por persona.

    El dinero de cada persona es un solo bolson (`bolson`): lo que falta
    se cuenta por persona y no por dia. Contado por dia, un ticket
    cargado el lunes dejaba al martes "sin comprobar" y al lunes
    "comprobado de mas": dos desviaciones por un dinero que cuadraba.
    """
    from app import bolson

    desviaciones = []
    for suyos in bolson.agrupar(viaticos):
        persona = suyos[0].persona
        nombre = persona.nombre if persona else str(suyos[0].persona_id)
        c = bolson.cuenta(suyos)
        if c["estatus"] == "con_descuento":
            # Ya esta resuelto: no es un pendiente, es una decision
            # tomada. Se informa para que finanzas lo vea, pero no frena.
            desviaciones.append({
                "tipo": m.TipoDesviacion.VIATICO_SIN_COMPROBAR.value,
                "descripcion": (f"{nombre}: cierre con descuento de "
                                f"{c['descontado']}"
                                + (f", {c['absorbido']} absorbido por la "
                                   f"empresa" if c["absorbido"] else "")
                                + f". {c['motivo_cierre'] or ''}").strip(),
                "monto": c["descontado"],
                "respaldada": True})
            continue
        if c["por_depositar"] > 0:
            desviaciones.append({
                "tipo": m.TipoDesviacion.VIATICO_NO_CERRADO.value,
                "descripcion": (f"{nombre}: {c['por_depositar']} autorizados "
                                "que no se depositaron"),
                "monto": c["por_depositar"]})
        if c["falta"] != CERO:
            desviaciones.append({
                "tipo": m.TipoDesviacion.VIATICO_SIN_COMPROBAR.value,
                "descripcion": (f"{nombre}: {abs(c['falta'])} "
                                + ("sin comprobar ni devolver"
                                   if c["falta"] > 0 else "comprobado de mas")),
                "monto": c["falta"]})
        if c["estatus"] == "abierto":
            desviaciones.append({
                "tipo": m.TipoDesviacion.VIATICO_NO_CERRADO.value,
                "descripcion": f"{nombre}: sus viaticos siguen sin cerrar",
                "monto": CERO})
    return desviaciones


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
    viaticos = viaticos_del_servicio(db, servicio_id)

    asignado = sum((_d(v.monto_total) for v in viaticos), CERO)
    comprobado = sum((_d(v.monto_comprobado) for v in viaticos), CERO)
    devuelto = sum((_d(v.monto_devuelto) for v in viaticos), CERO)

    descontado = sum((_d(v.monto_descontado) for v in viaticos), CERO)
    absorbido = sum((_d(v.monto_absorbido) for v in viaticos), CERO)
    rechazado = sum((_d(c.monto) for v in viaticos for c in v.comprobantes
                     if c.rechazado), CERO)

    desviaciones.extend(desviaciones_del_dinero(viaticos))

    # La cotizacion lleva el servicio y, a precio alzado, el monto fijo de
    # gastos. El comparativo los separa: la diferencia del servicio se
    # mide contra el servicio, y los gastos contra su propio trato.
    fijo = gastos_cotizados(cotizacion)
    total_cotizado = _d(cotizacion.total)
    servicio_cotizado = total_cotizado - fijo
    gastos_a_facturar = _viatico_facturable(cotizacion, comprobado)
    return {
        "servicio": servicio.folio,
        "cotizacion": {"version": cotizacion.version, "total": total_cotizado,
                       "servicio": servicio_cotizado, "gastos": fijo,
                       "moneda": cotizacion.moneda.value,
                       "viaticos_incluidos": cotizacion.viaticos_incluidos},
        "ejecutado": {"total": real["total"], "horas_extra": real["horas_extra"],
                      "dias": len({l["fecha"] for l in real["detalle"]}),
                      "equipos": len({l["equipo"] for l in real["detalle"]})},
        "diferencia": real["total"] - servicio_cotizado,
        "gastos": {"modo": modo_de_gastos(cotizacion.viaticos_incluidos),
                   "cotizado": fijo, "comprobado": comprobado,
                   "a_facturar": gastos_a_facturar},
        "a_facturar": {"servicio": real["total"], "gastos": gastos_a_facturar,
                       "total": real["total"] + gastos_a_facturar},
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
    """El reloj del cierre del eventual, sin el comparativo.

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
        return {"momento": ahora.isoformat(), **VACIO}
    return {"momento": ahora.isoformat(), **ficha_del_cierre(db, fila, ahora)}


# Lo que dice el reloj cuando todavia no hay cierre: el servicio no ha
# terminado, o el mes sigue trabajandose.
VACIO = {"existe": False, "cierre_id": None, "estatus": None, "fase": None,
         "abierto_en": None, "comprobacion_hasta": None,
         "visto_bueno_desde": None, "limite": None,
         "minutos_restantes": None, "viaticos_abiertos": None,
         "motivo": None, "factura": None, "factura_error": None,
         "factura_anulada": None, "dentro_de_plazo": None, "total": None,
         "visto_bueno_en": None, "enviado_en": None, "devuelto_en": None,
         "devuelto_motivo": None, "aprobado_en": None, "reloj": None,
         "consultor": None, "comision": None}

# Cuantas horas tiene el consultor desde que finanzas le regresa el
# servicio (decision 1 de Salvador, 23 sep).
HORAS_REGRESO = 24


def limite_vigente(cierre: m.Cierre) -> tuple[str, datetime] | None:
    """El reloj que corre ahora, y de quien es.

    En comprobacion corre el del personal; sin visto bueno, el del
    consultor; regresado por finanzas, 24 horas desde el regreso. Con el
    visto bueno dado ya no corre ninguno.
    """
    e = cierre.estatus
    if e == m.EstatusCierre.ABIERTO:
        hasta = cierre.comprobacion_hasta or cierre.limite_consultor
        return ("personal", hasta) if hasta else None
    if e == m.EstatusCierre.DEVUELTO_A_OPERACION and cierre.devuelto_en:
        return ("regreso",
                cierre.devuelto_en + timedelta(hours=HORAS_REGRESO))
    if e in (m.EstatusCierre.SIN_VISTO_BUENO, m.EstatusCierre.EN_REVISION_IA,
             m.EstatusCierre.DEVUELTO_A_OPERACION):
        return ("consultor", cierre.limite_consultor)
    return None


def reloj_de(cierre: m.Cierre, ahora: datetime) -> dict | None:
    vigente = limite_vigente(cierre)
    if not vigente:
        return None
    quien, hasta = vigente
    return {"quien": quien, "hasta": hasta.isoformat(),
            "minutos": int((hasta - ahora).total_seconds() // 60)}


def ficha_del_cierre(db: Session, fila: m.Cierre, ahora: datetime) -> dict:
    """El cierre como lo pinta la tarjeta de visto bueno y facturacion.

    Las mismas llaves para el eventual y para el mes del implantado: la
    tarjeta es una sola. Todo en hora del pais del servicio.
    """
    from app import comisiones

    def iso(momento):
        return momento.isoformat() if momento else None

    consultor = (db.get(m.Persona, fila.servicio.consultor_id)
                 if fila.servicio and fila.servicio.consultor_id else None)
    return {
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
        "viaticos_abiertos": _dinero_afuera(db, fila),
        "motivo": fila.motivo_apertura,
        "factura": fila.factura_odoo,
        "factura_error": fila.factura_error,
        "factura_anulada": fila.factura_anulada,
        "dentro_de_plazo": fila.dentro_de_plazo,
        # Lo que se mando a facturar; antes del visto bueno no hay cifra.
        "total": str(fila.total_ejecutado) if fila.enviado_en else None,
        "visto_bueno_en": iso(fila.visto_bueno_en or fila.enviado_en),
        "enviado_en": iso(fila.enviado_en),
        "devuelto_en": iso(fila.devuelto_en),
        "devuelto_motivo": fila.devuelto_motivo,
        "aprobado_en": iso(fila.aprobado_en),
        # El reloj que corre ahora, sea de quien sea.
        "reloj": reloj_de(fila, ahora),
        "consultor": ({"id": consultor.id, "nombre": consultor.nombre}
                      if consultor else None),
        "comision": comisiones.del_cierre(db, fila),
    }


# Como se dice cada estatus del cierre en un mensaje. El valor de la
# base ("enviado_finanzas") no es una frase: salia tal cual en la
# pantalla.
NOMBRE_ESTATUS = {
    m.EstatusCierre.ABIERTO: "comprobacion",
    m.EstatusCierre.SIN_VISTO_BUENO: "sin visto bueno",
    m.EstatusCierre.EN_REVISION_IA: "sin visto bueno",
    m.EstatusCierre.ENVIADO_FINANZAS: "facturacion: ya tiene visto bueno",
    m.EstatusCierre.DEVUELTO_A_OPERACION: "regresado a operacion",
    m.EstatusCierre.APROBADO: "cerrado por finanzas",
    m.EstatusCierre.FACTURADO: "cerrado y facturado",
}


def nombre_estatus(estatus: m.EstatusCierre) -> str:
    return NOMBRE_ESTATUS.get(estatus, estatus.value.replace("_", " "))


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


# ---------------------------------------------------------------- visto bueno y regreso

def dar_visto_bueno(cierre: m.Cierre, momento: datetime) -> None:
    """El visto bueno del consultor: pasa a facturacion.

    El primero es el que juzga el plazo, y se queda (decision 1 de
    Salvador, 23 sep): si finanzas lo regresa y el consultor lo vuelve a
    mandar, aquel "en plazo" no se pierde por la vuelta, ni un "fuera de
    plazo" se limpia con ella. Solo escribe; guarda quien llama.
    """
    cierre.enviado_en = momento
    if cierre.visto_bueno_en is None:
        cierre.visto_bueno_en = momento
        cierre.dentro_de_plazo = momento <= cierre.limite_consultor
    cierre.estatus = m.EstatusCierre.ENVIADO_FINANZAS


def regresar(db: Session, cierre: m.Cierre, motivo: str, usuario: m.Usuario,
             ahora: datetime | None = None) -> dict:
    """Finanzas regresa el servicio --o el mes-- a operacion.

    Solo lo que esta en facturacion: lo cerrado ya genero la comision y
    su factura, y lo que no tiene visto bueno todavia no es de finanzas.
    El motivo se exige porque es lo que el consultor lee en su tarjeta.

    Decisiones de Salvador (23 sep): el consultor tiene 24 horas desde el
    regreso, y lo "en plazo" de su primer visto bueno se queda. Si la
    factura ya salio, se anula: con el nuevo visto bueno sale otra, que
    lleva el folio de la anulada para que en Odoo se sepa cual sustituye.
    """
    from app import auditoria

    if cierre.estatus != m.EstatusCierre.ENVIADO_FINANZAS:
        raise HTTPException(409, {
            "mensaje": (f"Solo se regresa lo que esta en facturacion; este "
                        f"esta en {nombre_estatus(cierre.estatus)}"),
            "que_hacer": ("Lo que ya se cerro se corrige con una nota de "
                          "credito, no regresandolo.")})
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise HTTPException(400, {
            "mensaje": "Escribe por que se regresa",
            "que_hacer": "Es lo que el consultor lee para corregirlo."})

    momento = reloj.ahora_del_servicio(db, cierre.servicio, ahora)
    cierre.estatus = m.EstatusCierre.DEVUELTO_A_OPERACION
    cierre.devuelto_motivo = motivo[:500]
    cierre.devuelto_en = momento
    anulada = None
    if cierre.factura_odoo:
        anulada = cierre.factura_odoo
        cierre.factura_anulada = cierre.factura_odoo
        cierre.factura_odoo = None
        cierre.facturado_en = None
    cierre.factura_error = None
    # Vuelve al consultor: el eventual regresa a sin visto bueno. El
    # implantado no cambia de estatus: la fase la lleva el mes.
    if (not cierre.contrato_id
            and cierre.servicio.estatus == m.EstatusServicio.EN_FACTURACION):
        cierre.servicio.estatus = m.EstatusServicio.SIN_VISTO_BUENO
    de_que = (f"{cierre.servicio.folio} {cierre.contrato.mes:02d}/"
              f"{cierre.contrato.anio}" if cierre.contrato_id
              else cierre.servicio.folio)
    auditoria.registrar(db, usuario, cierre.servicio, "devolver a operacion",
                        (f"{de_que}: {motivo}"
                         + (f" (factura {anulada} anulada)" if anulada
                            else ""))[:400])
    db.commit()

    hasta = momento + timedelta(hours=HORAS_REGRESO)
    if cierre.servicio.consultor_id:
        from app import push
        pantalla = (f"/consola/#/implantado/{cierre.servicio_id}"
                    if cierre.contrato_id
                    else f"/consola/#/servicio/{cierre.servicio_id}")
        try:
            push.avisar(
                db, cierre.servicio.consultor_id,
                titulo=f"{de_que}: finanzas lo regreso",
                cuerpo=(f"{motivo[:140]} Tienes hasta el "
                        f"{hasta:%d/%m a las %H:%M} para volver a mandarlo."),
                url=pantalla, etiqueta=f"regreso-{cierre.id}")
            db.commit()
        except Exception:                 # noqa: BLE001
            # Un aviso que no sale no deshace el regreso.
            db.rollback()
            registro.exception("no se pudo avisar el regreso de %s", de_que)
    return {"resultado": "devuelto a operacion", "motivo": motivo,
            "hasta": hasta.isoformat(), "factura_anulada": anulada}


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

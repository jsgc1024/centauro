"""Comision del consultor.

Sobre facturacion del cliente, descontando los viaticos:
  1 por ciento en implantados, 3 por ciento en eventuales.

Se detona con el cierre VALIDADO por finanzas dentro de las 24 horas,
no con el cierre simplemente capturado. Se paga por servicio facturado,
con corte mensual de todo lo acumulado, sin esperar a la cobranza.

El corte del mes (seccion 66, decisiones de Salvador del 25 de
septiembre): por pais; entra lo que finanzas valido en el mes; cuando
el mes termina, direccion de operaciones le da el visto bueno y eso
deja fijo lo de cada consultor; finanzas registra cada pago con su
referencia. Lo que cambie despues --un servicio que se vuelve a
facturar, una factura que no se cobra, lo que capture finanzas-- es
una diferencia en el mes que siga abierto. Y nadie cobra en negativo:
si las diferencias dejan a un consultor debajo de cero, ese mes cobra
cero y lo que falta pasa al mes siguiente.
"""
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import cierre as motor_cierre
from app import models as m
from app import reloj

CERO = Decimal("0")

# De que es una diferencia en la comision.
AJUSTE_NO_COBRADA = "no_cobrada"        # la factura no se cobro
AJUSTE_REFACTURADA = "refacturacion"    # se volvio a facturar ya pagada
AJUSTE_MANUAL = "manual"                # la captura finanzas
AJUSTE_SALDO = "saldo_en_contra"        # el corte anterior quedo debajo de cero
MINIMO_MOTIVO = 10


def _mes_siguiente(anio: int, mes: int) -> tuple[int, int]:
    return (anio, mes + 1) if mes < 12 else (anio + 1, 1)


def corte_de(db: Session, pais_id: int, anio: int, mes: int
             ) -> m.CorteComision | None:
    return (db.query(m.CorteComision)
            .filter_by(pais_id=pais_id, anio=anio, mes=mes).first())


def mes_abierto(db: Session, pais_id: int, anio: int, mes: int
                ) -> tuple[int, int]:
    """El primer mes, desde ese, cuyo corte no tiene visto bueno.

    Una comision que finanzas valida el ultimo dia, despues del visto
    bueno de ese mes, ya no puede entrar a el: pasa al siguiente.
    """
    while corte_de(db, pais_id, anio, mes):
        anio, mes = _mes_siguiente(anio, mes)
    return anio, mes


def _hoy(db: Session, pais_id: int, ahora: datetime | None = None) -> date:
    return reloj.ahora_en(db.get(m.Pais, pais_id), ahora).date()


def _ya_ajustado(db: Session, comision: m.ComisionConsultor) -> Decimal:
    """Lo que ya se le corrigio a una comision por refacturacion."""
    return sum((Decimal(str(a.monto)) for a in db.query(m.AjusteComision)
                .filter_by(comision_id=comision.id,
                           tipo=AJUSTE_REFACTURADA).all()), CERO)


def _volver_a_calcular(db: Session, existente: m.ComisionConsultor,
                       facturacion: Decimal, viaticos: Decimal,
                       base: Decimal, monto: Decimal, hoy: date):
    """Finanzas vuelve a validar un servicio que ya tenia comision.

    Mientras su mes no tenga visto bueno, la comision se corrige en su
    lugar. Si ya lo tuvo, su monto se quedo fijo --quiza ya se pago--, y
    lo que cambie es una diferencia en el mes que siga abierto. La que
    se perdio o se retuvo se queda como esta: esa la decide otra regla.
    """
    if existente.estatus in (m.EstatusComision.PERDIDA,
                             m.EstatusComision.RETENIDA):
        return
    if existente.corte_id is None:
        existente.facturacion = facturacion
        existente.viaticos = viaticos
        existente.base = base
        existente.monto = monto
        return
    antes = Decimal(str(existente.monto)) + _ya_ajustado(db, existente)
    diferencia = monto - antes
    if diferencia == CERO:
        return
    servicio = existente.servicio
    anio, mes = mes_abierto(db, servicio.pais_id, hoy.year, hoy.month)
    db.add(m.AjusteComision(
        comision_id=existente.id, consultor_id=existente.consultor_id,
        pais_id=servicio.pais_id, servicio_id=servicio.id,
        anio=anio, mes=mes, monto=diferencia, tipo=AJUSTE_REFACTURADA,
        motivo=(f"Se volvio a facturar despues de pagar su comision: la "
                f"comision pasa de {antes:,.2f} a {monto:,.2f}")))


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

    rent = motor_cierre.rentabilidad(db, servicio_id)
    facturacion = Decimal(str(rent["facturacion"]))
    viaticos = Decimal(str(rent["costos"]["viaticos_comprobados"]))
    base = facturacion - viaticos
    pct = _porcentaje(db, servicio.pais_id, servicio.tipo)
    monto = (base * pct / Decimal("100")).quantize(Decimal("0.01"))

    referencia = registro.aprobado_en or registro.enviado_en
    periodo = referencia.date() if referencia else date.today()

    if existente:
        _volver_a_calcular(db, existente, facturacion, viaticos, base,
                           monto, periodo)
        db.commit()
        db.refresh(existente)
        return existente

    # El mes de la validacion, o el que siga si ese ya tiene visto bueno.
    anio, mes = mes_abierto(db, servicio.pais_id, periodo.year, periodo.month)
    comision = m.ComisionConsultor(
        servicio_id=servicio_id, consultor_id=servicio.consultor_id,
        anio=anio, mes=mes,
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

    if existente:
        _volver_a_calcular(db, existente, facturacion, viaticos, base,
                           monto, periodo)
        db.commit()
        db.refresh(existente)
        return existente

    anio, mes = mes_abierto(db, servicio.pais_id, periodo.year, periodo.month)
    comision = m.ComisionConsultor(
        servicio_id=servicio.id, contrato_id=contrato.id,
        consultor_id=servicio.consultor_id,
        anio=anio, mes=mes,
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
        # Si su mes ya tuvo visto bueno, no entro a el --estaba retenida--
        # y se paga en el mes que siga abierto.
        pais_id = comision.servicio.pais_id
        if corte_de(db, pais_id, comision.anio, comision.mes):
            hoy = _hoy(db, pais_id)
            comision.anio, comision.mes = mes_abierto(db, pais_id, hoy.year,
                                                      hoy.month)
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

    pais_id = comision.servicio.pais_id
    anio, mes = mes_abierto(db, pais_id, anio, mes)
    ajuste = m.AjusteComision(
        comision_id=comision.id, consultor_id=comision.consultor_id,
        pais_id=pais_id, servicio_id=comision.servicio_id,
        anio=anio, mes=mes, monto=-Decimal(str(comision.monto)), motivo=motivo,
        tipo=AJUSTE_NO_COBRADA)
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


# ---------------------------------------------------------------- el corte del mes

SE_PAGA = (m.EstatusComision.GENERADA, m.EstatusComision.AJUSTADA,
           m.EstatusComision.PAGADA)
NO_SE_PAGA = (m.EstatusComision.PERDIDA, m.EstatusComision.RETENIDA)


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _iso(valor) -> str | None:
    return valor.isoformat() if valor else None


def _cierre_de(db: Session, c: m.ComisionConsultor) -> m.Cierre | None:
    if c.contrato_id:
        return db.query(m.Cierre).filter_by(contrato_id=c.contrato_id).first()
    return (db.query(m.Cierre)
            .filter_by(servicio_id=c.servicio_id, contrato_id=None).first())


def _periodo(db: Session, c: m.ComisionConsultor) -> str | None:
    if not c.contrato_id:
        return None
    contrato = db.get(m.ContratoImplantado, c.contrato_id)
    return f"{contrato.anio}-{contrato.mes:02d}" if contrato else None


def _renglon_comision(db: Session, c: m.ComisionConsultor) -> dict:
    cierre = _cierre_de(db, c)
    pct = _d(c.porcentaje)
    # La perdida guarda su monto en cero; lo que se perdio sale de su base.
    monto = (_d(c.monto) if c.estatus != m.EstatusComision.PERDIDA
             else (_d(c.base) * pct / Decimal("100")).quantize(Decimal("0.01")))
    return {
        "comision_id": c.id, "servicio_id": c.servicio_id,
        "folio": c.servicio.folio, "tipo": c.servicio.tipo.value,
        "periodo": _periodo(db, c), "estatus": c.estatus.value,
        "validado": _iso(cierre.aprobado_en if cierre else None),
        "visto_bueno": _iso(cierre.visto_bueno_en if cierre else None),
        "limite": _iso(cierre.limite_consultor if cierre else None),
        "facturacion": _d(c.facturacion), "viaticos": _d(c.viaticos),
        "base": _d(c.base), "porcentaje": float(pct), "monto": monto,
        "moneda": c.moneda.value, "motivo": c.motivo}


def _renglon_ajuste(db: Session, a: m.AjusteComision, moneda: str) -> dict:
    quien = db.get(m.Persona, a.creado_por_id) if a.creado_por_id else None
    return {"ajuste_id": a.id, "tipo": a.tipo, "monto": _d(a.monto),
            "motivo": a.motivo, "folio": a.servicio.folio if a.servicio else None,
            "servicio_id": a.servicio_id, "creado_en": _iso(a.creado_en),
            "quien": quien.nombre if quien else None, "moneda": moneda}


def _en_camino(db: Session, pais_id: int) -> list[dict]:
    """Lo que ya tiene el visto bueno del consultor y espera a finanzas:
    entra al corte del mes en que finanzas lo valide."""
    salida = []
    cierres = (db.query(m.Cierre)
               .join(m.Servicio, m.Cierre.servicio_id == m.Servicio.id)
               .filter(m.Servicio.pais_id == pais_id,
                       m.Servicio.consultor_id.isnot(None),
                       m.Cierre.estatus == m.EstatusCierre.ENVIADO_FINANZAS)
               .all())
    for cierre in cierres:
        estimada = del_cierre(db, cierre)
        if not estimada:
            continue
        contrato = cierre.contrato if cierre.contrato_id else None
        salida.append({
            "consultor_id": cierre.servicio.consultor_id,
            "folio": cierre.servicio.folio,
            "servicio_id": cierre.servicio_id,
            "periodo": (f"{contrato.anio}-{contrato.mes:02d}"
                        if contrato else None),
            "visto_bueno": _iso(cierre.enviado_en),
            "monto": _d(estimada["monto"]),
            "moneda": estimada["moneda"],
            "se_pierde": estimada["estatus"] == "se_pierde"})
    return salida


def corte_del_mes(db: Session, pais_id: int, anio: int, mes: int,
                  usuario: m.Usuario | None = None,
                  ahora: datetime | None = None) -> dict:
    """El corte de comisiones de un mes y un pais, como se ve en Nominas.

    Antes del visto bueno se arma al vuelo con lo que finanzas valido en
    el mes. Con el visto bueno, cada consultor tiene su pago fijo y lo
    que sale es eso. Un consultor ve solo el suyo.
    """
    pais = db.get(m.Pais, pais_id)
    if not pais:
        raise HTTPException(404, f"No existe el pais {pais_id}")
    if not 1 <= mes <= 12:
        raise HTTPException(400, "El mes va del 1 al 12")
    hoy = _hoy(db, pais_id, ahora)
    ultimo = date(anio, mes, calendar.monthrange(anio, mes)[1])
    corte = corte_de(db, pais_id, anio, mes)
    local = pais.moneda_local.value

    comisiones = (db.query(m.ComisionConsultor)
                  .join(m.Servicio,
                        m.ComisionConsultor.servicio_id == m.Servicio.id)
                  .filter(m.Servicio.pais_id == pais_id,
                          m.ComisionConsultor.anio == anio,
                          m.ComisionConsultor.mes == mes)
                  .order_by(m.ComisionConsultor.id).all())
    ajustes = (db.query(m.AjusteComision)
               .filter_by(pais_id=pais_id, anio=anio, mes=mes)
               .order_by(m.AjusteComision.id).all())

    solo = None
    if usuario is not None and usuario.rol == m.Rol.CONSULTOR:
        solo = usuario.persona_id

    consultores: dict = {}

    def de(consultor_id: int, moneda: str) -> dict:
        clave = (consultor_id, moneda)
        if clave not in consultores:
            persona = db.get(m.Persona, consultor_id)
            consultores[clave] = {
                "consultor_id": consultor_id,
                "consultor": persona.nombre if persona else None,
                "moneda": moneda, "se_paga": [], "no_se_paga": [],
                "diferencias": [], "en_camino": [], "pago": None}
        return consultores[clave]

    for c in comisiones:
        if solo is not None and c.consultor_id != solo:
            continue
        # Con visto bueno, lo que se paga es lo que quedo en el corte.
        if corte and c.estatus in SE_PAGA and c.corte_id != corte.id:
            continue
        renglon = _renglon_comision(db, c)
        fila = de(c.consultor_id, renglon["moneda"])
        (fila["no_se_paga"] if c.estatus in NO_SE_PAGA
         else fila["se_paga"]).append(renglon)

    for a in ajustes:
        if solo is not None and a.consultor_id != solo:
            continue
        if corte and a.corte_id != corte.id:
            continue
        moneda = (a.comision.moneda.value if a.comision else local)
        de(a.consultor_id, moneda)["diferencias"].append(
            _renglon_ajuste(db, a, moneda))

    # Lo que espera a finanzas solo tiene sentido en el mes que corre.
    abierto = corte is None and (anio, mes) >= (hoy.year, hoy.month)
    if abierto:
        for e in _en_camino(db, pais_id):
            if solo is not None and e["consultor_id"] != solo:
                continue
            de(e["consultor_id"], e["moneda"] or local)["en_camino"].append(e)

    if corte:
        for p in corte.pagos:
            if solo is not None and p.consultor_id != solo:
                continue
            quien = db.get(m.Persona, p.pagado_por_id) if p.pagado_por_id else None
            de(p.consultor_id, p.moneda)["pago"] = {
                "pago_id": p.id, "se_paga": _d(p.se_paga),
                "diferencias": _d(p.diferencias), "total": _d(p.total),
                "saldo_en_contra": _d(p.saldo_en_contra),
                "referencia": p.referencia, "pagado_en": _iso(p.pagado_en),
                "pagado_por": quien.nombre if quien else None}

    filas = []
    total = {"se_paga": CERO, "no_se_paga": CERO, "diferencias": CERO,
             "a_pagar": CERO, "en_contra": CERO}
    for fila in consultores.values():
        se_paga = sum((r["monto"] for r in fila["se_paga"]), CERO)
        no_se_paga = sum((r["monto"] for r in fila["no_se_paga"]), CERO)
        diferencias = sum((r["monto"] for r in fila["diferencias"]), CERO)
        suma = se_paga + diferencias
        fila["totales"] = {"se_paga": se_paga, "no_se_paga": no_se_paga,
                           "diferencias": diferencias,
                           "a_pagar": max(suma, CERO),
                           "en_contra": min(suma, CERO),
                           "en_camino": sum((e["monto"] for e in fila["en_camino"]
                                             if not e["se_pierde"]), CERO)}
        pago = fila["pago"]
        if pago:
            fila["estado"] = ("pagado" if pago["pagado_en"] and pago["total"] > 0
                              else "sin_pago" if pago["pagado_en"]
                              else "por_pagar")
        elif corte is None and hoy > ultimo:
            fila["estado"] = "por_autorizar"
        else:
            fila["estado"] = "abierto"
        if fila["moneda"] == local:
            for k in ("se_paga", "no_se_paga", "diferencias", "a_pagar",
                      "en_contra"):
                total[k] += fila["totales"][k]
        filas.append(fila)
    filas.sort(key=lambda f: ((f["consultor"] or "").lower(), f["moneda"]))

    if corte:
        estado = corte.estatus
    elif hoy > ultimo:
        estado = "por_autorizar"
    else:
        estado = "abierto"
    autorizo = (db.get(m.Persona, corte.autorizado_por_id)
                if corte and corte.autorizado_por_id else None)
    # La regla que se lee arriba del corte sale de lo configurado en el
    # pais, no de un texto fijo: si manana cambia, la pantalla no miente.
    porcentajes = {}
    for tipo in (m.TipoServicio.EVENTUAL, m.TipoServicio.IMPLANTADO):
        fila = (db.query(m.PorcentajeComision)
                .filter_by(pais_id=pais_id, tipo_servicio=tipo, activo=True)
                .first())
        porcentajes[tipo.value] = float(fila.porcentaje) if fila else None
    return {
        "pais_id": pais_id, "anio": anio, "mes": mes, "moneda": local,
        "porcentajes": porcentajes,
        "estado": estado, "hasta": ultimo.isoformat(),
        "se_puede_autorizar": corte is None and hoy > ultimo,
        "corte_id": corte.id if corte else None,
        "autorizado_en": _iso(corte.autorizado_en if corte else None),
        "autorizado_por": autorizo.nombre if autorizo else None,
        "pagado_en": _iso(corte.pagado_en if corte else None),
        "consultores": filas, "totales": total,
        "solo_el_suyo": solo is not None,
    }


def visto_bueno(db: Session, pais_id: int, anio: int, mes: int,
                usuario: m.Usuario, ahora: datetime | None = None) -> dict:
    """Direccion de operaciones da el visto bueno del mes: lo de cada
    consultor queda fijo y finanzas ya puede pagarlo.

    Se da con el mes terminado. Si a alguien las diferencias lo dejan
    debajo de cero, su pago de este mes es cero y lo que falta pasa al
    mes siguiente, hasta saldarse.
    """
    if corte_de(db, pais_id, anio, mes):
        raise HTTPException(409, "Ese mes ya tiene su visto bueno")
    hoy = _hoy(db, pais_id, ahora)
    ultimo = date(anio, mes, calendar.monthrange(anio, mes)[1])
    if hoy <= ultimo:
        raise HTTPException(409, {
            "mensaje": "Ese mes todavia no termina",
            "que_hacer": (f"El visto bueno se da a partir del "
                          f"{ultimo + timedelta(days=1):%d/%m}: hasta "
                          "entonces pueden entrar mas comisiones.")})

    vista = corte_del_mes(db, pais_id, anio, mes, ahora=ahora)
    corte = m.CorteComision(pais_id=pais_id, anio=anio, mes=mes,
                            estatus="autorizado",
                            autorizado_por_id=usuario.persona_id)
    db.add(corte)
    db.flush()

    siguiente = mes_abierto(db, pais_id, *_mes_siguiente(anio, mes))
    pagos = 0
    for fila in vista["consultores"]:
        for r in fila["se_paga"]:
            db.get(m.ComisionConsultor, r["comision_id"]).corte_id = corte.id
        for r in fila["diferencias"]:
            db.get(m.AjusteComision, r["ajuste_id"]).corte_id = corte.id
        t = fila["totales"]
        if not fila["se_paga"] and not fila["diferencias"]:
            continue            # solo lo que no se paga o lo que viene
        pago = m.PagoComision(corte_id=corte.id,
                              consultor_id=fila["consultor_id"],
                              moneda=fila["moneda"], se_paga=t["se_paga"],
                              diferencias=t["diferencias"],
                              total=t["a_pagar"],
                              saldo_en_contra=t["en_contra"])
        if t["a_pagar"] <= CERO:
            # No hay nada que transferir: queda saldado desde ahora.
            pago.pagado_en = datetime.now(timezone.utc)
        db.add(pago)
        pagos += 1
        if t["en_contra"] < CERO:
            db.add(m.AjusteComision(
                consultor_id=fila["consultor_id"], pais_id=pais_id,
                anio=siguiente[0], mes=siguiente[1], monto=t["en_contra"],
                tipo=AJUSTE_SALDO, creado_por_id=usuario.persona_id,
                motivo=f"Saldo en contra del corte de {mes:02d}/{anio}"))
    db.flush()
    _cerrar_si_ya_salio_todo(corte)
    db.flush()
    return {"corte_id": corte.id, "consultores": pagos,
            "total": vista["totales"]["a_pagar"], "estatus": corte.estatus}


def _cerrar_si_ya_salio_todo(corte: m.CorteComision):
    if all(p.pagado_en for p in corte.pagos):
        corte.estatus = "pagado"
        corte.pagado_en = corte.pagado_en or datetime.now(timezone.utc)


def pagar(db: Session, pago_id: int, referencia: str,
          usuario: m.Usuario) -> dict:
    """Finanzas registra la transferencia de un consultor."""
    pago = db.get(m.PagoComision, pago_id)
    if not pago:
        raise HTTPException(404, f"No existe el pago {pago_id}")
    if pago.pagado_en:
        raise HTTPException(409, "Ese pago ya se registro")
    referencia = (referencia or "").strip()
    if len(referencia) < 3:
        raise HTTPException(400, {
            "mensaje": "Falta la referencia de la transferencia",
            "que_hacer": "Es lo que se busca cuando el consultor pregunta "
                         "por su pago."})
    pago.referencia = referencia[:120]
    pago.pagado_en = datetime.now(timezone.utc)
    pago.pagado_por_id = usuario.persona_id
    for c in (db.query(m.ComisionConsultor)
              .filter_by(corte_id=pago.corte_id,
                         consultor_id=pago.consultor_id).all()):
        if c.moneda.value == pago.moneda and c.estatus in (
                m.EstatusComision.GENERADA, m.EstatusComision.AJUSTADA):
            c.estatus = m.EstatusComision.PAGADA
    db.flush()
    _cerrar_si_ya_salio_todo(pago.corte)
    db.flush()
    return {"pago_id": pago.id, "total": _d(pago.total),
            "referencia": pago.referencia,
            "corte": pago.corte.estatus}


def diferencia_a_mano(db: Session, pais_id: int, consultor_id: int,
                      monto: Decimal, motivo: str, usuario: m.Usuario,
                      servicio_id: int | None = None,
                      ahora: datetime | None = None) -> m.AjusteComision:
    """Lo que finanzas corrige a mano: entra en el mes que siga abierto."""
    motivo = (motivo or "").strip()
    if len(motivo) < MINIMO_MOTIVO:
        raise HTTPException(400, {
            "mensaje": "Falta decir por que",
            "que_hacer": (f"Escribe al menos {MINIMO_MOTIVO} letras: es lo "
                          "que lee el consultor en su corte.")})
    if monto == CERO:
        raise HTTPException(400, "Una diferencia de cero no cambia nada")
    persona = db.get(m.Persona, consultor_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {consultor_id}")
    if servicio_id is not None and not db.get(m.Servicio, servicio_id):
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    hoy = _hoy(db, pais_id, ahora)
    anio, mes = mes_abierto(db, pais_id, hoy.year, hoy.month)
    ajuste = m.AjusteComision(
        consultor_id=consultor_id, pais_id=pais_id, servicio_id=servicio_id,
        anio=anio, mes=mes, monto=monto, motivo=motivo, tipo=AJUSTE_MANUAL,
        creado_por_id=usuario.persona_id)
    db.add(ajuste)
    db.flush()
    return ajuste

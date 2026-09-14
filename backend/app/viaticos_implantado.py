"""Viaticos del implantado, mes por mes.

Vive aparte de los viaticos del eventual a proposito. Los dos reparten
dinero entre personas y los dos usan el mismo tabulador —el motor de
`app.viaticos`, que calcula lo que toca por dia—, pero el corte es
distinto y de ahi sale todo lo demas:

  - El eventual es un servicio de tres dias: se deposita una vez, por
    todo el paso de la persona por el equipo, y se cierra cuando el
    servicio termina.
  - El implantado corre sin fin. Se deposita, se comprueba y se cierra
    mes con mes, igual que se factura. Un deposito repartido entre
    septiembre y octubre no habria forma de comprobarlo ni de cobrarlo.

Por eso aqui todo lleva anio y mes, y por eso no se comparte el camino
con el eventual: un parametro suelto en el otro lado terminaria
moviendole el corte a quien no lo pidio.
"""
from datetime import date
from decimal import Decimal, ROUND_FLOOR

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import viaticos as motor

# El semaforo que ve el consultor. Un solo color por persona: lo que
# importa de un vistazo es si el dinero ya salio o todavia no.
POR_ASIGNAR = "por_asignar"      # gris: nadie ha dicho cuanto
ASIGNADO = "asignado"            # azul: hay monto, falta pedirlo
SOLICITADO = "solicitado"        # ambar: finanzas lo tiene
DEPOSITADO = "depositado"        # verde: el dinero ya esta con la persona

VIVAS = (m.EstatusTransferencia.PENDIENTE, m.EstatusTransferencia.ENVIADA,
         m.EstatusTransferencia.CONFIRMADA)
EN_CAMINO = (m.EstatusTransferencia.PENDIENTE, m.EstatusTransferencia.ENVIADA)


def dias_del_mes(servicio: m.Servicio, anio: int, mes: int) -> list[m.Jornada]:
    """Los dias del servicio en ese mes que siguen en pie."""
    equipo = servicio.equipos[0] if servicio.equipos else None
    return sorted([j for j in (equipo.jornadas if equipo else [])
                   if j.estatus != m.EstatusJornada.CANCELADA
                   and j.fecha.year == anio and j.fecha.month == mes],
                  key=lambda j: j.fecha)


def _suyos(persona_id: int, dias: list[m.Jornada]) -> list[m.Jornada]:
    return [j for j in dias
            if any(a.persona_id == persona_id for a in j.personal)]


def _asignaciones(db: Session, persona_id: int,
                  dias: list[m.Jornada]) -> list[m.AsignacionViatico]:
    if not dias:
        return []
    return (db.query(m.AsignacionViatico)
            .filter(m.AsignacionViatico.persona_id == persona_id,
                    m.AsignacionViatico.jornada_id.in_([j.id for j in dias]))
            .all())


def _dinero(db: Session, viaticos: list[m.AsignacionViatico]) -> dict:
    """Como va el dinero de una persona en ese mes, en tres numeros.

    Un deposito no es un evento unico: se manda uno, se cae y se manda
    otro. Por eso las cuentas salen de las solicitudes y no del estatus
    del viatico, que solo puede contar una ronda a la vez.
    """
    asignado = sum((Decimal(str(v.monto_total)) for v in viaticos),
                   Decimal("0"))
    solicitudes = []
    if viaticos:
        solicitudes = (db.query(m.SolicitudTransferencia)
                       .filter(m.SolicitudTransferencia.asignacion_id.in_(
                           [v.id for v in viaticos]),
                           m.SolicitudTransferencia.estatus.in_(VIVAS))
                       .all())
    depositado = sum((Decimal(str(s.monto)) for s in solicitudes
                      if s.estatus == m.EstatusTransferencia.CONFIRMADA),
                     Decimal("0"))
    en_camino = sum((Decimal(str(s.monto)) for s in solicitudes
                     if s.estatus in EN_CAMINO), Decimal("0"))
    return {"asignado": asignado, "depositado": depositado,
            "en_camino": en_camino,
            "por_solicitar": asignado - depositado - en_camino}


def _semaforo(dinero: dict) -> str:
    """Manda el estado mas atrasado: si algo falta por pedir, el renglon
    no esta cerrado por mas que ya haya salido un deposito antes."""
    if dinero["asignado"] <= 0:
        return POR_ASIGNAR
    if dinero["por_solicitar"] > 0:
        return ASIGNADO
    if dinero["en_camino"] > 0:
        return SOLICITADO
    return DEPOSITADO


def _propuesta(db: Session, jornada: m.Jornada, persona_id: int) -> Decimal:
    """Lo que dice el tabulador del acuerdo para ese dia."""
    return calcular_dia(db, jornada, persona_id)["total_propuesto"]


def _recalcular(v: m.AsignacionViatico) -> None:
    v.monto_total = sum((Decimal(str(c.monto)) for c in v.conceptos),
                        Decimal("0"))


def _repartir(monto: Decimal, pesos: list[Decimal]) -> list[Decimal]:
    """Parte el monto entre los dias segun lo que pesa cada uno.

    Todo en unidades enteras: un viatico se entrega en efectivo o por
    transferencia y nadie anda partiendo pesos. Lo que sobra se reparte
    de a uno entre los dias que quedaron mas cerca de subir, para que la
    suma de los dias de exactamente el numero que el consultor escribio.
    En finanzas, un peso de diferencia es una llamada.
    """
    if not pesos:
        return []
    monto = motor.redondear(monto)
    total = sum(pesos, Decimal("0"))
    if total <= 0:                       # sin propuesta, partes iguales
        pesos = [Decimal("1")] * len(pesos)
        total = Decimal(len(pesos))

    exactas = [monto * p / total for p in pesos]
    partes = [e.to_integral_value(rounding=ROUND_FLOOR) for e in exactas]
    sobran = int(monto - sum(partes, Decimal("0")))
    orden = sorted(range(len(pesos)), key=lambda i: exactas[i] - partes[i],
                   reverse=True)
    for i in orden[:sobran]:
        partes[i] += Decimal("1")
    return partes


# ------------------------------------------------------------- el panel

def panel(db: Session, servicio: m.Servicio, anio: int, mes: int) -> dict:
    """Una linea por persona: lo que propone el sistema, lo que decidio
    el consultor y en que va el deposito. Solo de ese mes."""
    dias = dias_del_mes(servicio, anio, mes)
    pais = db.get(m.Pais, servicio.pais_id)

    personas: dict[int, m.Persona] = {}
    for jornada in dias:
        for a in jornada.personal:
            personas.setdefault(a.persona_id, a.persona)

    filas = []
    for persona_id, persona in personas.items():
        suyos = _suyos(persona_id, dias)
        viaticos = _asignaciones(db, persona_id, suyos)
        dinero = _dinero(db, viaticos)
        filas.append({
            "persona_id": persona_id,
            "nombre": persona.nombre,
            "puesto": next((a.rol.nombre for j in suyos for a in j.personal
                            if a.persona_id == persona_id and a.rol), None),
            "dias": len(suyos),
            "propuesto": sum((_propuesta(db, j, persona_id) for j in suyos),
                             Decimal("0")),
            **dinero,
            "estatus": _semaforo(dinero),
            "comprobado": sum((Decimal(str(v.monto_comprobado))
                               for v in viaticos), Decimal("0")),
        })
    filas.sort(key=lambda f: f["nombre"])

    return {
        "servicio_id": servicio.id, "folio": servicio.folio,
        "periodo": f"{mes:02d}/{anio}", "anio": anio, "mes": mes,
        "dias": len(dias),
        "moneda": pais.moneda_local.value if pais else None,
        "personal": filas,
        "total_propuesto": sum((f["propuesto"] for f in filas), Decimal("0")),
        "total_asignado": sum((f["asignado"] for f in filas), Decimal("0")),
        "total_depositado": sum((f["depositado"] for f in filas), Decimal("0")),
        "total_en_camino": sum((f["en_camino"] for f in filas), Decimal("0")),
        "total_por_solicitar": sum((f["por_solicitar"] for f in filas),
                                   Decimal("0")),
    }


def _dias_de_la_persona(db: Session, servicio, anio, mes, persona_id):
    dias = _suyos(persona_id, dias_del_mes(servicio, anio, mes))
    if not dias:
        raise HTTPException(409, "Esa persona no tiene dias en ese mes")
    return dias


def fijar(db: Session, servicio: m.Servicio, anio: int, mes: int,
          persona_id: int, monto: Decimal, usuario_persona_id) -> dict:
    """Un solo numero por persona, por sus dias de ese mes.

    Por dentro se reparte entre sus dias segun lo que propone el
    tabulador, y la diferencia queda escrita como un ajuste con nombre y
    apellido: la comprobacion sigue teniendo contra que comparar.
    """
    dias = _dias_de_la_persona(db, servicio, anio, mes, persona_id)
    ya = _asignaciones(db, persona_id, dias)

    # Reescribe el desglose desde cero, asi que solo sirve mientras nadie
    # haya pedido nada: si ya hay dinero con finanzas o con la persona,
    # lo que sigue es agregar otro deposito.
    fuera = _dinero(db, ya)
    if fuera["depositado"] > 0 or fuera["en_camino"] > 0:
        raise HTTPException(409, {
            "mensaje": "Esa persona ya tiene un deposito en marcha. "
                       "Agregue otro deposito en vez de mover el monto.",
            **{k: str(v) for k, v in fuera.items()}})

    pais = db.get(m.Pais, servicio.pais_id)
    propuestas = [_propuesta(db, j, persona_id) for j in dias]
    partes = _repartir(Decimal(str(monto)), propuestas)
    por_jornada = {v.jornada_id: v for v in ya}

    for jornada, propuesto, toca in zip(dias, propuestas, partes):
        viatico = por_jornada.get(jornada.id)
        if not viatico:
            viatico = m.AsignacionViatico(
                jornada_id=jornada.id, persona_id=persona_id,
                escenario=motor.escenario_de(jornada),
                moneda=pais.moneda_local,
                asignado_por_id=usuario_persona_id)
            db.add(viatico)
            db.flush()

        for concepto in list(viatico.conceptos):
            db.delete(concepto)
        db.flush()

        detalle = calcular_dia(db, jornada, persona_id)
        for c in detalle["conceptos"]:
            db.add(m.ConceptoAsignado(
                asignacion_id=viatico.id,
                concepto=m.ConceptoViatico(c["concepto"]),
                monto=c["monto"], descripcion=c["descripcion"],
                origen=m.OrigenMonto(c["origen"])))

        ajuste = toca - propuesto
        if ajuste != 0:
            db.add(m.ConceptoAsignado(
                asignacion_id=viatico.id, concepto=m.ConceptoViatico.OTROS,
                monto=ajuste, origen=m.OrigenMonto.MANUAL,
                descripcion="Ajuste del consultor"))
        db.flush()
        db.refresh(viatico)
        _recalcular(viatico)
    db.flush()
    return {"dias": len(dias)}


def agregar(db: Session, servicio: m.Servicio, anio: int, mes: int,
            persona_id: int, monto: Decimal, usuario_persona_id) -> dict:
    """Otro deposito encima del que ya salio, sin tocar lo anterior."""
    if Decimal(str(monto)) <= 0:
        raise HTTPException(400, "Un deposito adicional de cero no existe")
    dias = _dias_de_la_persona(db, servicio, anio, mes, persona_id)
    ya = {v.jornada_id: v for v in _asignaciones(db, persona_id, dias)}
    if not ya:
        raise HTTPException(409, "Esa persona todavia no tiene viaticos. "
                                 "Capture primero cuanto se le deposita.")

    pais = db.get(m.Pais, servicio.pais_id)
    propuestas = [_propuesta(db, j, persona_id) for j in dias]
    partes = _repartir(Decimal(str(monto)), propuestas)

    for jornada, toca in zip(dias, partes):
        if toca == 0:
            continue
        viatico = ya.get(jornada.id)
        if not viatico:
            viatico = m.AsignacionViatico(
                jornada_id=jornada.id, persona_id=persona_id,
                escenario=motor.escenario_de(jornada),
                moneda=pais.moneda_local,
                asignado_por_id=usuario_persona_id)
            db.add(viatico)
            db.flush()
        db.add(m.ConceptoAsignado(
            asignacion_id=viatico.id, concepto=m.ConceptoViatico.OTROS,
            monto=toca, origen=m.OrigenMonto.MANUAL, es_adicional=True,
            descripcion="Deposito adicional"))
        db.flush()
        db.refresh(viatico)
        _recalcular(viatico)
        if viatico.estatus in (m.EstatusViatico.CANCELADO,
                               m.EstatusViatico.DEVUELTO):
            viatico.estatus = m.EstatusViatico.ASIGNADO
    db.flush()
    return {"dias": len(dias)}


def _del_mes(db: Session, servicio, anio, mes, persona_id=None):
    dias = dias_del_mes(servicio, anio, mes)
    if not dias:
        return []
    consulta = (db.query(m.AsignacionViatico)
                .filter(m.AsignacionViatico.jornada_id.in_([j.id for j in dias])))
    if persona_id:
        consulta = consulta.filter(
            m.AsignacionViatico.persona_id == persona_id)
    return consulta.all()


def solicitar(db: Session, servicio: m.Servicio, anio: int, mes: int,
              persona_id: int | None = None) -> dict:
    """Le pide a finanzas el saldo del mes, no el total: lo que ya se
    deposito o ya esta pedido no se vuelve a pedir."""
    pedidos, monto = 0, Decimal("0")
    for viatico in _del_mes(db, servicio, anio, mes, persona_id):
        saldo = _dinero(db, [viatico])["por_solicitar"]
        if saldo <= 0:
            continue
        db.add(m.SolicitudTransferencia(
            asignacion_id=viatico.id, monto=saldo, moneda=viatico.moneda))
        if viatico.estatus == m.EstatusViatico.ASIGNADO:
            viatico.estatus = m.EstatusViatico.SOLICITADO
        pedidos += 1
        monto += saldo

    if not pedidos:
        raise HTTPException(409, "No hay montos por solicitar en ese mes. "
                                 "Capture primero cuanto se deposita.")
    db.flush()
    return {"depositos": pedidos, "monto": str(monto)}


def cancelar(db: Session, servicio: m.Servicio, anio: int, mes: int,
             persona_id: int | None = None) -> dict:
    """Mientras el dinero no salga, el consultor puede echarse para atras.
    Lo ya depositado no entra aqui: eso se devuelve, no se cancela."""
    cancelados, monto = 0, Decimal("0")
    for viatico in _del_mes(db, servicio, anio, mes, persona_id):
        vueltas = (db.query(m.SolicitudTransferencia)
                   .filter(m.SolicitudTransferencia.asignacion_id == viatico.id,
                           m.SolicitudTransferencia.estatus.in_(EN_CAMINO))
                   .all())
        if not vueltas:
            continue
        for solicitud in vueltas:
            solicitud.estatus = m.EstatusTransferencia.CANCELADA
            monto += Decimal(str(solicitud.monto))
        if viatico.estatus == m.EstatusViatico.SOLICITADO:
            viatico.estatus = m.EstatusViatico.ASIGNADO
        cancelados += 1

    if not cancelados:
        raise HTTPException(409, "No hay depositos por cancelar. Si el "
                                 "dinero ya salio, se devuelve.")
    db.flush()
    return {"depositos": cancelados, "monto": str(monto)}


# --------------------------------------------------------------------
# El tabulador del acuerdo
#
# El tabulador de la empresa vale para el eventual: un dia suelto con las
# mismas reglas para todos. El implantado se negocia cliente por cliente
# —que se le da de comer al equipo, si se le paga el traslado, que pasa
# con la gasolina— y eso es parte del acuerdo. Por eso cada servicio
# trae el suyo y el calculo lee ese, no el del pais.
# --------------------------------------------------------------------

# Los conceptos que de verdad se usan en un implantado, en el orden en
# que se capturan. La lista completa existe en el enum; esta es la que se
# le ofrece al consultor para que no tenga que descartar cinco renglones
# que nunca va a llenar.
CONCEPTOS = [
    m.ConceptoViatico.ALIMENTOS,
    m.ConceptoViatico.TRASLADO_PERSONAL,
    m.ConceptoViatico.COMBUSTIBLE,
    m.ConceptoViatico.CASETAS,
    m.ConceptoViatico.HOSPEDAJE,
    m.ConceptoViatico.OTROS,
]


def tabulador(db: Session, servicio_id: int) -> list[m.TabuladorImplantado]:
    return (db.query(m.TabuladorImplantado)
            .filter_by(servicio_id=servicio_id, activo=True).all())


def calcular_dia(db: Session, jornada: m.Jornada, persona_id: int) -> dict:
    """Lo que le toca a una persona ese dia, segun el acuerdo.

    No guarda nada: es la propuesta que ve el consultor y que puede
    subir o bajar. Si el acuerdo todavia no tiene tabulador, la
    propuesta es cero y se dice —un cero sin explicacion se lee como
    "aqui no hay viaticos", que es distinto de "falta capturarlo".
    """
    servicio = jornada.equipo.servicio
    filas = tabulador(db, servicio.id)
    if not filas:
        return {"conceptos": [], "total_propuesto": Decimal("0"),
                "sin_tabulador": True}

    # La presentacion del dia manda sobre el traslado: a esa hora no hay
    # transporte publico con el que llegar y el que se presenta antes se
    # paga un taxi de su bolsa. El tabulador dice cuanto, no cuando.
    madruga = jornada.inicio_programado.time() < motor.HORA_TRASLADO

    orden = {c: i for i, c in enumerate(CONCEPTOS)}
    conceptos = []
    for fila in sorted(filas, key=lambda f: orden.get(f.concepto, 99)):
        if fila.concepto == m.ConceptoViatico.TRASLADO_PERSONAL and not madruga:
            # El renglon se queda a la vista, en cero y con el motivo:
            # que desapareciera dejaba al consultor preguntandose si el
            # tabulador estaba mal capturado o si la regla lo saco.
            conceptos.append({
                "concepto": fila.concepto.value, "monto": Decimal("0"),
                "descripcion": "Solo cuando la presentacion es antes de "
                               "las 6:30",
                "origen": m.OrigenMonto.TABULADOR.value, "editable": True})
            continue
        if fila.monto_abierto:
            conceptos.append({
                "concepto": fila.concepto.value, "monto": Decimal("0"),
                "descripcion": fila.nota or "El consultor captura el monto",
                "origen": m.OrigenMonto.MANUAL.value, "editable": True})
            continue
        conceptos.append({
            "concepto": fila.concepto.value,
            "monto": motor.redondear(fila.monto),
            "descripcion": fila.nota,
            "origen": m.OrigenMonto.TABULADOR.value, "editable": True})

    return {"conceptos": conceptos,
            "total_propuesto": sum((c["monto"] for c in conceptos),
                                   Decimal("0")),
            "sin_tabulador": False}


def ver_tabulador(db: Session, servicio: m.Servicio) -> dict:
    """El tabulador del acuerdo, y lo que la empresa sugiere si no hay.

    La sugerencia sale de la tabla de implantado del pais y es solo eso:
    un punto de partida para no capturar seis renglones desde cero. Lo
    que manda es lo que quede escrito aqui.
    """
    filas = {f.concepto: f for f in
             db.query(m.TabuladorImplantado)
             .filter_by(servicio_id=servicio.id).all()}

    sugerido = {}
    for fila in (db.query(m.TabuladorViatico)
                 .filter(m.TabuladorViatico.pais_id == servicio.pais_id,
                         m.TabuladorViatico.tipo_servicio
                         == m.TipoServicio.IMPLANTADO,
                         m.TabuladorViatico.activo.is_(True)).all()):
        # El implantado es siempre dia completo local: ese es el
        # escenario del que se toma la sugerencia.
        if fila.escenario == m.EscenarioViatico.FULL_DAY_LOCAL:
            sugerido[fila.concepto] = fila

    pais = db.get(m.Pais, servicio.pais_id)
    renglones = []
    for concepto in CONCEPTOS:
        suyo = filas.get(concepto)
        propuesto = sugerido.get(concepto)
        renglones.append({
            "concepto": concepto.value,
            "monto": str(suyo.monto) if suyo else None,
            "monto_abierto": bool(suyo.monto_abierto) if suyo else False,
            "nota": suyo.nota if suyo else None,
            "activo": bool(suyo.activo) if suyo else False,
            "sugerido": str(propuesto.monto) if propuesto else None,
        })

    vivos = [r for r in renglones if r["activo"]]
    return {
        "servicio_id": servicio.id,
        "moneda": pais.moneda_local.value if pais else None,
        "capturado": bool(vivos),
        "renglones": renglones,
        "total_dia": str(sum((Decimal(r["monto"] or 0) for r in vivos),
                             Decimal("0"))),
    }


def guardar_tabulador(db: Session, servicio: m.Servicio,
                      renglones: list) -> dict:
    """Reescribe el tabulador del acuerdo con lo que mando el consultor.

    Un renglon apagado no se borra: se deja inactivo. Asi el mes que ya
    se pago con el conserva de donde salio su numero, que es lo que se
    revisa cuando alguien pregunta por que en marzo fueron 260 y en
    abril 300.
    """
    previos = {f.concepto: f for f in
               db.query(m.TabuladorImplantado)
               .filter_by(servicio_id=servicio.id).all()}

    for renglon in renglones:
        concepto = m.ConceptoViatico(renglon.concepto)
        fila = previos.get(concepto)
        if not fila:
            fila = m.TabuladorImplantado(servicio_id=servicio.id,
                                         concepto=concepto)
            db.add(fila)
        fila.monto = renglon.monto or 0
        fila.monto_abierto = bool(renglon.monto_abierto)
        fila.nota = (renglon.nota or None)
        fila.activo = bool(renglon.activo)

    # Lo que el consultor no mando se apaga: quito el renglon de la
    # pantalla y eso quiere decir que ese concepto ya no va.
    mandados = {m.ConceptoViatico(r.concepto) for r in renglones}
    for concepto, fila in previos.items():
        if concepto not in mandados:
            fila.activo = False

    db.flush()
    return ver_tabulador(db, servicio)

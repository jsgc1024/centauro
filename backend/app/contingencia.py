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
from app import reloj
from app import viaticos as motor_viaticos

# Estos viaticos ya tienen dinero encima: no se cancelan, se comprueban.
CON_DINERO = (m.EstatusViatico.TRANSFERIDO, m.EstatusViatico.EN_COMPROBACION)
# Estos todavia no: se cancelan sin mas.
SIN_DINERO = (m.EstatusViatico.ASIGNADO, m.EstatusViatico.SOLICITADO)


def _solo_eventual(desde: m.Jornada) -> None:
    """Este motor es de eventual. El implantado tiene el suyo.

    No es una separacion de gusto: el implantado reutiliza el mismo
    equipo mes tras mes, asi que un cambio "de aqui en adelante" barreria
    todas las jornadas abiertas —el mes en curso y el siguiente, si ya se
    genero— y abriria decenas de viaticos de un solo clic. Su reemplazo
    va dia por dia, en `implantado.cambiar_personal`, y ahi es donde hay
    que hacerlo.
    """
    servicio = desde.equipo.servicio if desde.equipo else None
    if servicio and servicio.tipo == m.TipoServicio.IMPLANTADO:
        raise HTTPException(409, {
            "mensaje": ("El cambio de recurso de un implantado se hace desde "
                        "su propio calendario, dia por dia."),
            "servicio_id": servicio.id,
        })


def jornadas_afectadas(db: Session, desde: m.Jornada,
                       hasta: m.Jornada | None = None) -> list[m.Jornada]:
    """De la jornada de la contingencia en adelante, dentro del mismo equipo.

    Los dias ya terminados no se tocan: esos ya los trabajo quien iba.

    `hasta` es para el cambio que si tiene fin. Una contingencia no lo
    tiene —nadie sabe cuando vuelve el que salio— pero unas vacaciones se
    acaban, y decirlo evita que el titular regrese y nadie se acuerde de
    devolverle sus dias.
    """
    consulta = (db.query(m.Jornada)
                .filter(m.Jornada.equipo_id == desde.equipo_id,
                        m.Jornada.fecha >= desde.fecha,
                        m.Jornada.estatus.notin_([m.EstatusJornada.CANCELADA,
                                                  m.EstatusJornada.TERMINADA])))
    if hasta is not None:
        consulta = consulta.filter(m.Jornada.fecha <= hasta.fecha)
    return consulta.order_by(m.Jornada.fecha).all()


def se_presento(db: Session, jornada: m.Jornada, persona_id: int) -> bool:
    """Si alcanzo a marcar su llegada.

    Es la regla de pago y tambien la que decide si el dia se parte: cobra
    el dia quien se presento. Quien no llego a marcar no trabajo, asi que
    relevarlo es cambiar un nombre en una lista y no hay nada que
    partir. El sistema lo verifica solo; nadie captura nada.
    """
    return (db.query(m.Hito.id)
            .filter_by(jornada_id=jornada.id, persona_id=persona_id,
                       tipo=m.TipoHito.LLEGADA_ORIGEN)
            .first()) is not None


def reemplazar_personal(db: Session, desde_jornada_id: int, sale_persona_id: int,
                        entra_persona_id: int, motivo: str,
                        hecho_por_id: int | None = None,
                        alerta_id: int | None = None,
                        motivo_tipo: m.MotivoCambio | None = None,
                        hasta_jornada_id: int | None = None,
                        relevado_en: datetime | None = None) -> dict:
    """El que entra toma el lugar del que sale, de un dia en adelante.

    El dia del cambio no se muta: se parte. La asignacion de quien se
    presento esa manana se queda, marcada con la hora en que lo
    relevaron, y la de quien entra se crea aparte. Las dos entran a
    nomina —cada quien su dia completo— y al cliente se le cobra una
    sola, porque el cierre ignora la relevada.

    Antes esto era `asignacion.persona_id = entra_persona_id`: la fila
    cambiaba de dueno y el que trabajo cuatro horas cobraba cero.

    Los dias siguientes si cambian de dueno, porque nadie los trabajo
    todavia. Y el dia del cambio tampoco se parte si el que sale nunca
    marco su llegada: sin presentarse no hay nada que pagar ni que
    partir.
    """
    desde = db.get(m.Jornada, desde_jornada_id)
    if not desde:
        raise HTTPException(404, f"No existe la jornada {desde_jornada_id}")
    _solo_eventual(desde)
    if sale_persona_id == entra_persona_id:
        raise HTTPException(409, "La persona que entra es la misma que sale")

    entra = db.get(m.Persona, entra_persona_id)
    if not entra or not entra.activo:
        raise HTTPException(404, "La persona que entra no existe o esta inactiva")

    hasta = db.get(m.Jornada, hasta_jornada_id) if hasta_jornada_id else None
    if hasta_jornada_id and not hasta:
        raise HTTPException(404, f"No existe la jornada {hasta_jornada_id}")
    if hasta and hasta.fecha < desde.fecha:
        raise HTTPException(409, "El ultimo dia del cambio es anterior al primero")

    momento = reloj.ahora_de_la_jornada(db, desde, relevado_en)
    jornadas = jornadas_afectadas(db, desde, hasta)
    cambiadas, partidas, choques = [], [], []

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

        if se_presento(db, j, sale_persona_id):
            # Trabajo parte del dia: su asignacion se queda y cobra.
            asignacion.relevado_en = momento
            asignacion.relevado_por_id = entra_persona_id
            # El que entra hereda el rol y la unidad. El rol no se cambia
            # aqui: de el salen el precio al cliente y la comision, y
            # moverlo descuadraria la cotizacion sin avisar.
            db.add(m.AsignacionPersonal(
                jornada_id=j.id, persona_id=entra_persona_id,
                rol_id=asignacion.rol_id, vehiculo_id=asignacion.vehiculo_id,
                reemplaza_a_id=sale_persona_id, confirmado=False))
            partidas.append(j.fecha.isoformat())
        else:
            # No se presento: no hay nada que pagarle y nada que partir.
            asignacion.persona_id = entra_persona_id
            asignacion.reemplaza_a_id = sale_persona_id
            asignacion.confirmado = False   # el que entra tiene que confirmar
        cambiadas.append(j)

    if not cambiadas:
        raise HTTPException(409, {
            "mensaje": ("Esa persona no esta asignada a ninguna jornada "
                        "pendiente desde ese dia"),
            "choques": choques,
        })

    # Para que `calcular` encuentre las asignaciones recien creadas.
    db.flush()
    viaticos = _mover_viaticos(db, cambiadas, sale_persona_id,
                               entra_persona_id, momento)

    reemplazo = m.ReemplazoRecurso(
        alerta_id=alerta_id, servicio_id=desde.equipo.servicio_id,
        desde_jornada_id=desde.id, hasta_jornada_id=hasta.id if hasta else None,
        tipo=m.TipoRecurso.PERSONAL, motivo_tipo=motivo_tipo,
        sale_persona_id=sale_persona_id, entra_persona_id=entra_persona_id,
        motivo=motivo, jornadas_afectadas=len(cambiadas),
        hecho_por_id=hecho_por_id)
    db.add(reemplazo)
    db.flush()

    return {
        "reemplazo_id": reemplazo.id,
        "jornadas_afectadas": [j.fecha.isoformat() for j in cambiadas],
        # Los dias en que el que sale trabajo y cobra: son los que
        # explican por que el mismo dia aparece dos veces en la nomina.
        "jornadas_partidas": partidas,
        "jornadas_con_choque": choques,
        "relevado_en": momento.isoformat(),
        "viaticos": viaticos,
    }


def reemplazar_vehiculo(db: Session, desde_jornada_id: int, sale_vehiculo_id: int,
                        entra_vehiculo_id: int, motivo: str,
                        hecho_por_id: int | None = None,
                        alerta_id: int | None = None,
                        motivo_tipo: m.MotivoCambio | None = None,
                        hasta_jornada_id: int | None = None,
                        relevado_en: datetime | None = None) -> dict:
    """La unidad que entra toma el lugar de la que sale.

    Igual que con el personal, el dia que ya arranco no se muta: se
    parte. Si se mutara, la camioneta que salio desapareceria del
    servicio —la lista de unidades se arma de las asignaciones vivas— y
    ya no se le podria hacer la revision de devolucion. Un golpe en esa
    unidad se quedaria sin dueno, que es exactamente lo que la revision
    con fotos vino a resolver.
    """
    desde = db.get(m.Jornada, desde_jornada_id)
    if not desde:
        raise HTTPException(404, f"No existe la jornada {desde_jornada_id}")
    _solo_eventual(desde)
    if sale_vehiculo_id == entra_vehiculo_id:
        raise HTTPException(409, "La unidad que entra es la misma que sale")

    entra = db.get(m.Vehiculo, entra_vehiculo_id)
    if not entra or not entra.activo:
        raise HTTPException(404, "La unidad que entra no existe o esta inactiva")

    hasta = db.get(m.Jornada, hasta_jornada_id) if hasta_jornada_id else None
    if hasta_jornada_id and not hasta:
        raise HTTPException(404, f"No existe la jornada {hasta_jornada_id}")
    if hasta and hasta.fecha < desde.fecha:
        raise HTTPException(409, "El ultimo dia del cambio es anterior al primero")

    momento = reloj.ahora_de_la_jornada(db, desde, relevado_en)
    cambiadas, partidas, choques = [], [], []

    for j in jornadas_afectadas(db, desde, hasta):
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

        if _rodo(db, j, sale_vehiculo_id):
            asignacion.relevado_en = momento
            asignacion.relevado_por_vehiculo_id = entra_vehiculo_id
            db.add(m.AsignacionVehiculo(jornada_id=j.id,
                                        vehiculo_id=entra_vehiculo_id))
            partidas.append(j.fecha.isoformat())
        else:
            asignacion.vehiculo_id = entra_vehiculo_id

        # Quien iba a bordo de esa unidad ahora va en la nueva. Sin esto
        # la central sigue viendo a la gente repartida en una camioneta
        # que ya no esta en el servicio.
        for persona in db.query(m.AsignacionPersonal).filter_by(
                jornada_id=j.id, vehiculo_id=sale_vehiculo_id).all():
            persona.vehiculo_id = entra_vehiculo_id

        cambiadas.append(j)

    if not cambiadas:
        raise HTTPException(409, {
            "mensaje": ("Esa unidad no esta asignada a ninguna jornada "
                        "pendiente desde ese dia"),
            "choques": choques,
        })

    reemplazo = m.ReemplazoRecurso(
        alerta_id=alerta_id, servicio_id=desde.equipo.servicio_id,
        desde_jornada_id=desde.id, hasta_jornada_id=hasta.id if hasta else None,
        tipo=m.TipoRecurso.VEHICULO, motivo_tipo=motivo_tipo,
        sale_vehiculo_id=sale_vehiculo_id, entra_vehiculo_id=entra_vehiculo_id,
        motivo=motivo, jornadas_afectadas=len(cambiadas),
        hecho_por_id=hecho_por_id)
    db.add(reemplazo)
    db.flush()

    return {
        "reemplazo_id": reemplazo.id,
        "jornadas_afectadas": [j.fecha.isoformat() for j in cambiadas],
        "jornadas_partidas": partidas,
        "jornadas_con_choque": choques,
        "relevado_en": momento.isoformat(),
        # La unidad que sale se queda pendiente de que alguien la
        # entregue: es el momento en que cambia de manos, que es el unico
        # en que todavia se puede saber en que estado iba.
        "revision_pendiente": _revision_pendiente(db, desde, sale_vehiculo_id,
                                                  entra_vehiculo_id),
        # El vehiculo no mueve viaticos: el combustible y las casetas
        # siguen siendo del conductor, que es el mismo.
        "viaticos": None,
    }


def _rodo(db: Session, jornada: m.Jornada, vehiculo_id: int) -> bool:
    """Si la unidad alcanzo a salir ese dia.

    Se sabe por la revision de recepcion: si alguien la recibio, la
    camioneta ya cambio de manos una vez y tiene que cambiar otra al
    salir. Si nadie la recibio, no rodo y cambiarla es corregir un
    nombre en una lista.
    """
    return (db.query(m.RevisionUnidad.id)
            .filter_by(servicio_id=jornada.equipo.servicio_id,
                       vehiculo_id=vehiculo_id,
                       tipo=m.TipoRevision.RECIBE)
            .first()) is not None


def _revision_pendiente(db: Session, jornada: m.Jornada, sale_vehiculo_id: int,
                        entra_vehiculo_id: int) -> dict:
    """Que revisiones faltan despues del cambio, para poder decirlo."""
    servicio_id = jornada.equipo.servicio_id
    hechas = {(r.vehiculo_id, r.tipo) for r in
              db.query(m.RevisionUnidad).filter_by(servicio_id=servicio_id).all()}
    return {
        "entrega_de_la_que_sale": (sale_vehiculo_id, m.TipoRevision.RECIBE) in hechas
        and (sale_vehiculo_id, m.TipoRevision.ENTREGA) not in hechas,
        "recepcion_de_la_que_entra": (entra_vehiculo_id,
                                      m.TipoRevision.RECIBE) not in hechas,
    }


def _mover_viaticos(db: Session, jornadas: list[m.Jornada],
                    sale_persona_id: int, entra_persona_id: int,
                    ahora: datetime) -> dict:
    """La que sale comprueba lo que ya recibio; a la que entra se le propone.

    Dos reglas, y las dos son de la casa:

    El dinero que ya se deposito no se mueve con la persona. Quien lo
    recibio se hace responsable de comprobarlo, y esa comprobacion hace
    falta para cerrar el servicio. Un viatico que nunca llego a
    transferirse no se comprueba: se cancela, porque esa persona no va a
    trabajar ese dia.

    Y al que entra no se le abre nada solo. El sistema propone el monto
    del tabulador —para que el consultor no tenga que ir a buscarlo— pero
    la solicitud la hace el consultor, como con cualquier otra. Antes se
    creaban solos: eso era el sistema decidiendo gastar sin que nadie lo
    pidiera, y ademas dejaba el cierre trabado con viaticos que nadie
    habia pedido.
    """
    a_comprobar, cancelados, propuestos = [], [], []

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

        # Solo la cuenta: lo que le tocaria por tabulador ese dia. No se
        # guarda nada. El consultor la asigna desde la misma pantalla,
        # con el boton de siempre.
        calculo = motor_viaticos.calcular(db, j.id, entra_persona_id)
        monto = sum(float(c["monto"]) for c in calculo.get("conceptos", []))
        if monto:
            propuestos.append({"jornada_id": j.id, "fecha": j.fecha.isoformat(),
                               "monto": monto})

    return {"a_comprobar": a_comprobar, "cancelados": cancelados,
            "propuestos": propuestos}


# ==================================================================
# Antes de guardar: decir en voz alta lo que va a pasar
# ==================================================================

def vista_previa(db: Session, **cambio) -> dict:
    """Lo que haria el cambio, sin dejar rastro.

    Se ejecuta el cambio de verdad y se deshace. No hay una segunda
    implementacion que calcule "lo que pasaria": esa siempre acaba
    separandose de la primera, y entonces el recuadro que el consultor
    lee deja de ser lo que el sistema hace.

    Lo delicado de un reemplazo no es el nombre de quien va: son los
    viaticos. La persona que sale se queda con dinero que ya recibio y
    tiene que comprobarlo; la que entra necesita dinero nuevo. Todo eso
    ya pasaba, solo que en silencio.
    """
    try:
        return reemplazar_personal(db, **cambio)
    finally:
        db.rollback()


# ==================================================================
# Deshacer: la ventana de arrepentimiento
# ==================================================================

# Lo unico que se puede deshacer limpio. En cuanto alguien pidio el
# dinero o lo transfirio, el cambio dejo de vivir solo aqui: hay una
# solicitud, una transferencia y un plazo corriendo.
SIN_TOCAR = (m.EstatusViatico.ASIGNADO, m.EstatusViatico.CANCELADO)


def deshacer(db: Session, reemplazo_id: int) -> dict:
    """Borra un reemplazo recien hecho, si nadie toco el dinero.

    Es para el consultor que se equivoco de persona hace un minuto. No
    es un "revertir" general: en cuanto el dinero se movio, deshacer a
    mano seria peor que el error, y lo que corresponde es un cambio en
    sentido contrario, con su rastro.
    """
    reemplazo = db.get(m.ReemplazoRecurso, reemplazo_id)
    if not reemplazo:
        raise HTTPException(404, f"No existe el reemplazo {reemplazo_id}")
    if reemplazo.tipo != m.TipoRecurso.PERSONAL:
        raise HTTPException(409, "Solo se deshacen los cambios de personal")

    desde = db.get(m.Jornada, reemplazo.desde_jornada_id)
    hasta = (db.get(m.Jornada, reemplazo.hasta_jornada_id)
             if reemplazo.hasta_jornada_id else None)
    sale_id, entra_id = reemplazo.sale_persona_id, reemplazo.entra_persona_id
    jornadas = jornadas_afectadas(db, desde, hasta)
    ids = [j.id for j in jornadas]

    # El candado: si algo del dinero ya se movio, no se deshace.
    tocados = (db.query(m.AsignacionViatico)
               .filter(m.AsignacionViatico.jornada_id.in_(ids),
                       m.AsignacionViatico.persona_id.in_([sale_id, entra_id]))
               .all())
    trabados = [v for v in tocados
                if v.estatus not in SIN_TOCAR or v.comprobantes
                or float(v.monto_comprobado or 0) > 0]
    if trabados:
        raise HTTPException(409, {
            "mensaje": ("Este cambio ya no se puede deshacer: el dinero se "
                        "movio. Si hay que regresarlo, se hace un cambio en "
                        "sentido contrario."),
            "viaticos": [v.id for v in trabados],
        })

    devueltas = []
    for j in jornadas:
        suya = (db.query(m.AsignacionPersonal)
                .filter_by(jornada_id=j.id, persona_id=sale_id).first())
        entrante = (db.query(m.AsignacionPersonal)
                    .filter_by(jornada_id=j.id, persona_id=entra_id).first())

        if suya and suya.relevado_por_id == entra_id:
            # El dia se habia partido: se junta otra vez.
            suya.relevado_en = None
            suya.relevado_por_id = None
            if entrante and entrante.reemplaza_a_id == sale_id:
                db.delete(entrante)
            devueltas.append(j.fecha.isoformat())
        elif entrante and entrante.reemplaza_a_id == sale_id:
            # El dia se habia mutado: vuelve a su dueno.
            entrante.persona_id = sale_id
            entrante.reemplaza_a_id = None
            entrante.confirmado = False
            devueltas.append(j.fecha.isoformat())

    for v in tocados:
        if v.persona_id == entra_id:
            db.delete(v)            # los que se le abrieron al que entraba
        elif v.estatus == m.EstatusViatico.CANCELADO:
            v.estatus = m.EstatusViatico.ASIGNADO
            v.limite_comprobacion = None

    db.delete(reemplazo)
    db.flush()
    return {"deshecho": reemplazo_id, "jornadas": devueltas}

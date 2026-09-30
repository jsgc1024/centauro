"""Cambio de recurso por contingencia.

Reparto de responsabilidades, tal como opera Centauro:
la central estabiliza el servicio (puede mandar su equipo de respuesta a
emergencias) y el consultor formaliza el cambio aqui.

Lo delicado no es cambiar el nombre de quien va: son los viaticos. La
persona que sale se queda con dinero que ya recibio y tiene que
comprobarlo; la que entra necesita dinero nuevo para dar continuidad.
"""
import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import reloj
from app import viaticos as motor_viaticos

# Estos viaticos ya tienen dinero encima: no se cancelan, se comprueban.
CON_DINERO = (m.EstatusViatico.TRANSFERIDO, m.EstatusViatico.EN_COMPROBACION)
# Estos todavia no: se cancelan sin mas.
SIN_DINERO = (m.EstatusViatico.ASIGNADO, m.EstatusViatico.SOLICITADO)

# Una hora del relevo un par de minutos adelante del reloj del pais es
# el reloj del navegador contra el del servidor; mas que eso es una hora
# que todavia no llega (seccion 101). El mismo margen que la marca de la
# app (`operacion.MINUTOS_FUTURO_TOLERADO`).
MINUTOS_FUTURO_TOLERADO = 2


def ultimo_dia_del_mes(fecha: date) -> date:
    """El tope de un cambio de implantado sin fecha de fin.

    Vive aqui, al lado del candado que lo exige, y no en el implantado:
    escrito en dos lugares es como el umbral de silencio, que acabo
    diciendo 60 en una pantalla y 120 en la otra.
    """
    return fecha.replace(day=calendar.monthrange(fecha.year, fecha.month)[1])


def _tramo_con_fin(desde: m.Jornada, hasta: m.Jornada | None) -> None:
    """El implantado no admite un cambio sin fecha de fin.

    Antes este candado decia "implantado prohibido" y mandaba a cada tipo
    de servicio a su propio motor. Dos motores para la misma regla se
    separan con el tiempo, y se separaron: el del implantado mutaba la
    asignacion y el que trabajo media jornada cobraba cero.

    Lo que el candado protegia era otra cosa, y esa sigue en pie: el
    implantado reutiliza el mismo equipo mes tras mes, asi que un cambio
    "de aqui en adelante" barreria todas las jornadas abiertas —el mes en
    curso y el siguiente, si ya se genero— y abriria decenas de viaticos
    de un solo clic. Con fecha de fin eso no puede pasar, y la fecha la
    pone `implantado.cambiar_recurso`: el ultimo dia del mes en curso.

    El eventual sigue entrando sin fin, porque una contingencia no lo
    tiene: nadie sabe cuando vuelve el que salio.
    """
    servicio = desde.equipo.servicio if desde.equipo else None
    if servicio and servicio.tipo == m.TipoServicio.IMPLANTADO and hasta is None:
        raise HTTPException(409, {
            "mensaje": ("El cambio de un implantado tiene que decir hasta que "
                        "dia llega. Sin fin se llevaria tambien los meses que "
                        "ya esten abiertos."),
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


def hora_del_relevo(db: Session, jornada: m.Jornada,
                    persona_id: int) -> datetime | None:
    """La ultima marca de quien sale, que es la hora que se propone para
    partir el dia.

    Sale del telefono y no de la memoria de nadie: es la ultima vez que
    el sistema supo de esa persona ese dia. Tiene un limite conocido --un
    dia estatico, con el ejecutivo en su oficina, puede no tener marcas
    desde el contacto de la manana-- y por eso se propone en vez de
    imponerse: el consultor la confirma o la corrige.
    """
    ultimo = (db.query(m.Hito)
              .filter_by(jornada_id=jornada.id, persona_id=persona_id)
              .order_by(m.Hito.marcado_en.desc()).first())
    return ultimo.marcado_en if ultimo else None


def llegada_de(db: Session, jornada: m.Jornada,
               persona_id: int) -> datetime | None:
    """A que hora marco su llegada quien sale, si la marco."""
    llegada = (db.query(m.Hito)
               .filter_by(jornada_id=jornada.id, persona_id=persona_id,
                          tipo=m.TipoHito.LLEGADA_ORIGEN)
               .order_by(m.Hito.marcado_en).first())
    return llegada.marcado_en if llegada else None


def revisar_hora_del_relevo(db: Session, jornada: m.Jornada,
                            momento: datetime,
                            ahora: datetime | None = None,
                            llegada: datetime | None = None) -> None:
    """La hora que capturo el consultor tiene que poder ser cierta.

    Se guardaba tal cual (seccion 101), y de ella salen el plazo de
    comprobacion, la disponibilidad de quien salio y la nomina de los
    dos: una hora de otro dia, una que todavia no llega o una anterior a
    la llegada de quien sale contaba una historia que no ocurrio. La
    pantalla manda siempre el dia de la jornada; la API no lo exigia.

    `ahora` es el reloj del servidor para las pruebas (pasa por
    `reloj.de_prueba` en la ruta); en produccion es la hora del pais.
    """
    # Del dia del cambio. Un servicio que cruza la medianoche termina al
    # dia siguiente, y un relevo a la 01:00 es de ese mismo dia.
    ultimo = (jornada.fin_programado or jornada.inicio_programado).date()
    if not (jornada.fecha <= momento.date() <= max(jornada.fecha, ultimo)):
        raise HTTPException(409, {
            "mensaje": "La hora del relevo no es del día del cambio",
            "que_hacer": (f"El cambio arranca el {jornada.fecha:%d/%m/%Y}: "
                          "la hora que se captura es la de ese día."),
            "dia": jornada.fecha.isoformat()})

    # Una hora que todavia no llega es una hora inventada.
    limite = (reloj.ahora_de_la_jornada(db, jornada, ahora)
              + timedelta(minutes=MINUTOS_FUTURO_TOLERADO))
    if momento > limite:
        raise HTTPException(409, {
            "mensaje": "Esa hora todavía no llega",
            "que_hacer": ("El relevo se registra después de que pasó, no "
                          "antes. Si va a ocurrir más tarde, captúralo "
                          "cuando ocurra."),
            "relevado_en": momento.isoformat()})

    # Y nadie sale de un servicio antes de haber llegado a el.
    if llegada is not None and momento < llegada:
        raise HTTPException(409, {
            "mensaje": ("La hora del relevo es anterior a la llegada de "
                        f"quien sale ({llegada:%H:%M})"),
            "que_hacer": ("Quien sale marcó su llegada a esa hora y trabajó "
                          "desde entonces: el relevo va después. Si no se "
                          "presentó, deja la hora vacía."),
            "llegada": llegada.isoformat()})


def reemplazar_personal(db: Session, desde_jornada_id: int, sale_persona_id: int,
                        entra_persona_id: int, motivo: str,
                        hecho_por_id: int | None = None,
                        alerta_id: int | None = None,
                        motivo_tipo: m.MotivoCambio | None = None,
                        hasta_jornada_id: int | None = None,
                        relevado_en: datetime | None = None,
                        ahora: datetime | None = None) -> dict:
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

    `ahora` es el reloj del servidor, solo para las pruebas (pasa por
    `reloj.de_prueba` en la ruta): decide contra que hora se revisa la
    del relevo.
    """
    desde = db.get(m.Jornada, desde_jornada_id)
    if not desde:
        raise HTTPException(404, f"No existe la jornada {desde_jornada_id}")
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
    _tramo_con_fin(desde, hasta)

    # La hora que parte el dia. Si el consultor no dijo cual, se propone
    # la ultima marca de quien sale; si tampoco hay marcas, la de ahora.
    # Antes era siempre la de ahora, asi que un relevo de las 11:00
    # capturado a las 18:00 le pagaba siete horas de mas a quien ya se
    # habia ido, y se las quitaba a quien las trabajo.
    propuesta = hora_del_relevo(db, desde, sale_persona_id)
    momento = reloj.ahora_de_la_jornada(db, desde,
                                        relevado_en or propuesta or ahora)
    # La que capturo el consultor se revisa (seccion 101); la que propone
    # el sistema sale de una marca real y no hace falta.
    if relevado_en is not None:
        revisar_hora_del_relevo(db, desde, momento, ahora,
                                llegada_de(db, desde, sale_persona_id))
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
            # La hora es la del dia que se esta partiendo. Para el dia en
            # que arranca el cambio es la que el consultor confirmo; si
            # llegara a partirse otro --raro, pero posible si quedo una
            # jornada vieja sin cerrar-- ese dia usa su propia ultima
            # marca, porque una hora del jueves no parte el viernes.
            asignacion.relevado_en = (
                momento if j.id == desde.id
                else (hora_del_relevo(db, j, sale_persona_id) or momento))
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
        hora_propuesta=propuesta if partidas else None,
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
        # Lo que el sistema habria puesto solo. La vista previa lo trae
        # para que el consultor vea de donde sale la hora antes de
        # confirmarla, y para que se note cuando la corrigio.
        "hora_propuesta": propuesta.isoformat() if propuesta else None,
        "viaticos": viaticos,
    }


def reemplazar_vehiculo(db: Session, desde_jornada_id: int, sale_vehiculo_id: int,
                        entra_vehiculo_id: int, motivo: str,
                        hecho_por_id: int | None = None,
                        alerta_id: int | None = None,
                        motivo_tipo: m.MotivoCambio | None = None,
                        hasta_jornada_id: int | None = None,
                        relevado_en: datetime | None = None,
                        ahora: datetime | None = None) -> dict:
    """La unidad que entra toma el lugar de la que sale.

    Igual que con el personal, el dia que ya arranco no se muta: se
    parte. Si se mutara, la camioneta que salio desapareceria del
    servicio —la lista de unidades se arma de las asignaciones vivas— y
    ya no se le podria hacer la revision de devolucion. Un golpe en esa
    unidad se quedaria sin dueno, que es exactamente lo que la revision
    con fotos vino a resolver.

    `ahora` es el reloj del servidor, solo para las pruebas.
    """
    desde = db.get(m.Jornada, desde_jornada_id)
    if not desde:
        raise HTTPException(404, f"No existe la jornada {desde_jornada_id}")
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
    _tramo_con_fin(desde, hasta)

    momento = reloj.ahora_de_la_jornada(db, desde, relevado_en or ahora)
    # La hora en que la unidad cambio de manos se revisa igual que la de
    # una persona (seccion 101): del dia del cambio y ya ocurrida.
    if relevado_en is not None:
        revisar_hora_del_relevo(db, desde, momento, ahora)
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

        # Se parte el dia en que la unidad ya rodo y, si el equipo la
        # trae en las manos --recibida y sin entregar--, el dia del
        # cambio: es donde hay que devolverla con su revision.
        if _rodo(db, j, sale_vehiculo_id) or (
                j.id == desde.id and _en_manos(db, j, sale_vehiculo_id)):
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
    """Si la unidad alcanzo a salir ESE dia.

    Se parte solo el dia en que ya rodo: el que ya arranco, o el que
    todavia no arranca pero en el que alguien ya recibio la unidad (la
    recogio esa manana y se descompuso antes de la llegada). Los dias
    que siguen se mutan: la unidad que sale ya no va en ellos.

    Antes preguntaba por servicio --"¿alguien la recibio alguna vez?"--
    y partia tambien los dias futuros (seccion 98): el dia 3 exigia
    entregar una camioneta que se fue el dia 2 y ya no se podia
    fotografiar, el fin se atoraba, y la unidad seguia "ocupada" el dia
    3 para otros servicios.
    """
    if jornada.estatus in (*m.ARRANCADAS, m.EstatusJornada.TERMINADA):
        return True
    inicio = datetime.combine(jornada.fecha, datetime.min.time())
    fin = inicio + timedelta(days=1)
    return (db.query(m.RevisionUnidad.id)
            .filter(m.RevisionUnidad.servicio_id == jornada.equipo.servicio_id,
                    m.RevisionUnidad.vehiculo_id == vehiculo_id,
                    m.RevisionUnidad.tipo == m.TipoRevision.RECIBE,
                    m.RevisionUnidad.momento >= inicio,
                    m.RevisionUnidad.momento < fin)
            .first()) is not None


def _en_manos(db: Session, jornada: m.Jornada, vehiculo_id: int) -> bool:
    """Si el equipo trae la unidad: la recibio en este servicio y no la
    ha entregado. Es la que hay que devolver el dia del cambio aunque
    ese dia todavia no arranque."""
    ultima = (db.query(m.RevisionUnidad)
              .filter_by(servicio_id=jornada.equipo.servicio_id,
                         vehiculo_id=vehiculo_id)
              .order_by(m.RevisionUnidad.momento.desc(),
                        m.RevisionUnidad.id.desc())
              .first())
    return ultima is not None and ultima.tipo == m.TipoRevision.RECIBE


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

    # El dinero se cuenta en Decimal y sale como cadena, como el resto
    # (seccion 101): tres conceptos sumados en float le ensenaban al
    # consultor 0.30000000000000004.
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
                    "monto": str(Decimal(str(viejo.monto_total or 0))),
                    "limite": viejo.limite_comprobacion.isoformat()})
            elif viejo.estatus in SIN_DINERO:
                # Con su solicitud (seccion 98): la pendiente se cancela y
                # la enviada queda pedida a finanzas. Antes la solicitud
                # sobrevivia al relevo y finanzas le depositaba a quien
                # salio los dias que ya no trabaja.
                resultado = motor_viaticos.cancelar(db, viejo, ahora)
                cancelados.append({"viatico_id": viejo.id,
                                   "fecha": j.fecha.isoformat(),
                                   "pedida_a_finanzas": resultado["pedidas"] > 0})

        ya_tiene = (db.query(m.AsignacionViatico)
                    .filter_by(jornada_id=j.id, persona_id=entra_persona_id)
                    .first())
        if ya_tiene:
            continue

        # Solo la cuenta: lo que le tocaria por tabulador ese dia. No se
        # guarda nada. El consultor la asigna desde la misma pantalla,
        # con el boton de siempre.
        calculo = motor_viaticos.calcular(db, j.id, entra_persona_id)
        monto = sum((Decimal(str(c["monto"] or 0))
                     for c in calculo.get("conceptos", [])), Decimal("0"))
        if monto:
            propuestos.append({"jornada_id": j.id, "fecha": j.fecha.isoformat(),
                               "monto": str(monto)})

    return {"a_comprobar": a_comprobar, "cancelados": cancelados,
            "propuestos": propuestos}


# ==================================================================
# El regreso: el titular vuelve
# ==================================================================

def regresar(db: Session, reemplazo_id: int, desde: date,
             hecho_por_id: int | None = None,
             relevado_en: datetime | None = None,
             ahora: datetime | None = None) -> dict:
    """El titular vuelve. Cierra el movimiento, no abre otro.

    Marta se enferma el 10 y Luis la cubre. Marta se recupera, avisa al
    consultor y regresa el 25; Luis trabaja hasta el 24 por orden del
    consultor. Eso es un solo hecho —"Luis cubrio a Marta del 10 al
    24"— y asi tiene que leerse en el historial y en el corte del mes.
    Si el regreso abriera su propio movimiento, el mismo mes mostraria
    dos cambios cruzados y nadie sabria cual cierra a cual.

    El regreso no pide motivo: el motivo es el del movimiento que cierra.
    Lo que si queda es quien lo ordeno y cuando.

    Por dentro es el mismo relevo de siempre, con los nombres al reves,
    asi que si Luis alcanzo a trabajar la manana del 25 ese dia se parte
    y los dos cobran su parte. El movimiento que ese relevo abre se borra
    aqui mismo: el hecho es el cierre del primero.
    """
    r = db.get(m.ReemplazoRecurso, reemplazo_id)
    if not r:
        raise HTTPException(404, f"No existe el cambio {reemplazo_id}")
    arranco = db.get(m.Jornada, r.desde_jornada_id)
    if not arranco:
        raise HTTPException(404, "El cambio apunta a un dia que ya no existe")
    if desde <= arranco.fecha:
        raise HTTPException(409, {
            "mensaje": ("El regreso tiene que caer despues del dia en que "
                        "arranco el cambio. Si fue un error, se deshace."),
            "arranco": arranco.fecha.isoformat()})

    vuelve = _primer_dia_abierto(db, arranco.equipo_id, desde)
    if not vuelve:
        raise HTTPException(409, "No hay dias abiertos de ese dia en adelante")

    if r.regreso_en:
        return _mover_el_regreso(db, r, arranco, vuelve, hecho_por_id,
                                 relevado_en, ahora)

    fin = db.get(m.Jornada, r.hasta_jornada_id) if r.hasta_jornada_id else None
    if fin and vuelve.fecha > fin.fecha:
        raise HTTPException(409, {
            "mensaje": ("Ese cambio ya termino por su cuenta: no hay nada "
                        "que cerrar."),
            "termino": fin.fecha.isoformat()})

    titular, cubre = _quienes(r)
    hecho = _relevar_al_reves(db, r, vuelve, fin, cubre, titular,
                              hecho_por_id, relevado_en, ahora)
    return _firmar_el_cierre(db, r, arranco, vuelve, hecho, hecho_por_id)


def _primer_dia_abierto(db: Session, equipo_id: int,
                        desde: date) -> m.Jornada | None:
    """El primer dia que todavia se puede mover, de esa fecha en adelante.

    El consultor dice "vuelve el sabado" y el sabado no hay jornada: su
    primer dia es el lunes. Traducirlo aqui evita que el calendario de la
    pantalla tenga que saber que dias opera cada servicio.
    """
    return (db.query(m.Jornada)
            .filter(m.Jornada.equipo_id == equipo_id,
                    m.Jornada.fecha >= desde,
                    m.Jornada.estatus.notin_([m.EstatusJornada.CANCELADA,
                                              m.EstatusJornada.TERMINADA]))
            .order_by(m.Jornada.fecha).first())


def _quienes(r: m.ReemplazoRecurso) -> tuple[int | None, int | None]:
    """El que sale y el que entra, sea persona o unidad."""
    if r.tipo == m.TipoRecurso.PERSONAL:
        return r.sale_persona_id, r.entra_persona_id
    return r.sale_vehiculo_id, r.entra_vehiculo_id


def _asignacion_de(r: m.ReemplazoRecurso):
    """La tabla de asignaciones que le toca y su columna de recurso."""
    if r.tipo == m.TipoRecurso.PERSONAL:
        return m.AsignacionPersonal, m.AsignacionPersonal.persona_id
    return m.AsignacionVehiculo, m.AsignacionVehiculo.vehiculo_id


def _como_se_llama(db: Session, r: m.ReemplazoRecurso,
                   recurso_id: int | None) -> str | None:
    if not recurso_id:
        return None
    if r.tipo == m.TipoRecurso.PERSONAL:
        persona = db.get(m.Persona, recurso_id)
        return persona.nombre if persona else None
    unidad = db.get(m.Vehiculo, recurso_id)
    return unidad.placa if unidad else None


def quien_entra_por_quien(db: Session, r: m.ReemplazoRecurso) -> str:
    """«Luis entra por Juan», o las placas si el cambio es de unidad.

    Es lo que la central lee en la ficha de la alerta para no tener que
    llamar a preguntar si el consultor ya formalizo el cambio (seccion
    101).
    """
    sale, entra = _quienes(r)
    return (f"{_como_se_llama(db, r, entra) or '?'} entra por "
            f"{_como_se_llama(db, r, sale) or '?'}")


def momento_del_cambio(db: Session, r: m.ReemplazoRecurso) -> datetime | None:
    """El instante en que el movimiento cambio por ultima vez quien va:
    cuando se hizo, o cuando el titular regreso.

    `creado_en` ya es un instante con zona; `regreso_en` es hora de
    pared del pais del servicio y se le pone su zona, para comparar
    instantes con instantes.
    """
    momentos = [r.creado_en] if r.creado_en else []
    if r.regreso_en:
        servicio = db.get(m.Servicio, r.servicio_id)
        pais = (db.get(m.Pais, servicio.pais_id)
                if servicio and servicio.pais_id else None)
        momentos.append(r.regreso_en.replace(
            tzinfo=reloj.zona(getattr(pais, "zona_horaria", None))))
    return max(momentos) if momentos else None


def hoja_anterior_al_cambio(db: Session, r: m.ReemplazoRecurso) -> bool:
    """Si la hoja publicada del equipo es de antes de este cambio.

    El lunes el consultor cambia al conductor del jueves. No sale correo
    --el cambio "viaja en el task sheet"-- pero la hoja publicada es una
    foto de antes, con el nombre viejo, y nada lo decia (seccion 101):
    el cliente llegaba el jueves con el nombre y el telefono de quien ya
    no va. Lo leen la revision de la vispera de la central y la tarjeta
    del cambio en el servicio.

    Solo el eventual: la hoja del implantado es la del acuerdo y se
    vuelve a liberar cuando el acuerdo cambia, no cuando cambia un dia.
    """
    desde = db.get(m.Jornada, r.desde_jornada_id)
    if not desde or not desde.equipo:
        return False
    if desde.equipo.servicio.tipo == m.TipoServicio.IMPLANTADO:
        return False
    hoja = (db.query(m.TaskSheet)
            .filter_by(equipo_id=desde.equipo_id,
                       estatus=m.EstatusTaskSheet.PUBLICADO)
            .order_by(m.TaskSheet.version.desc()).first())
    momento = momento_del_cambio(db, r)
    return bool(hoja and hoja.creado_en and momento
                and hoja.creado_en < momento)


def _se_partio(db: Session, r: m.ReemplazoRecurso, jornada: m.Jornada) -> bool:
    """Si el dia del regreso quedo repartido entre los dos."""
    sale, entra = _quienes(r)
    if r.tipo == m.TipoRecurso.PERSONAL:
        return (db.query(m.AsignacionPersonal.id)
                .filter(m.AsignacionPersonal.jornada_id == jornada.id,
                        m.AsignacionPersonal.persona_id == entra,
                        m.AsignacionPersonal.relevado_por_id == sale,
                        m.AsignacionPersonal.relevado_en.isnot(None))
                .first()) is not None
    return (db.query(m.AsignacionVehiculo.id)
            .filter(m.AsignacionVehiculo.jornada_id == jornada.id,
                    m.AsignacionVehiculo.vehiculo_id == entra,
                    m.AsignacionVehiculo.relevado_por_vehiculo_id == sale,
                    m.AsignacionVehiculo.relevado_en.isnot(None))
            .first()) is not None


def _relevar_al_reves(db: Session, r: m.ReemplazoRecurso, desde: m.Jornada,
                      hasta: m.Jornada | None, sale: int, entra: int,
                      hecho_por_id: int | None,
                      relevado_en: datetime | None,
                      ahora: datetime | None = None) -> dict:
    """El mismo relevo de siempre, con los nombres al reves."""
    motor = (reemplazar_personal if r.tipo == m.TipoRecurso.PERSONAL
             else reemplazar_vehiculo)
    llaves = ({"sale_persona_id": sale, "entra_persona_id": entra}
              if r.tipo == m.TipoRecurso.PERSONAL
              else {"sale_vehiculo_id": sale, "entra_vehiculo_id": entra})
    return motor(db, desde_jornada_id=desde.id, motivo=r.motivo,
                 hecho_por_id=hecho_por_id, motivo_tipo=r.motivo_tipo,
                 hasta_jornada_id=hasta.id if hasta else None,
                 relevado_en=relevado_en, ahora=ahora, **llaves)


def _dinero_trabado(db: Session, r: m.ReemplazoRecurso, equipo_id: int,
                    desde: date, hasta: date) -> list[m.AsignacionViatico]:
    """Los viaticos de ese tramo que ya no se pueden desandar.

    El mismo candado que usa `deshacer`: en cuanto alguien pidio el
    dinero o lo transfirio, el movimiento dejo de vivir solo en una
    tabla. Hay una solicitud, una transferencia y un plazo corriendo.

    La unidad no mueve viaticos: el combustible y las casetas siguen
    siendo del conductor, que es el mismo.
    """
    if r.tipo != m.TipoRecurso.PERSONAL:
        return []
    personas = [r.sale_persona_id, r.entra_persona_id]
    tocados = (db.query(m.AsignacionViatico)
               .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
               .filter(m.Jornada.equipo_id == equipo_id,
                       m.Jornada.fecha >= desde, m.Jornada.fecha <= hasta,
                       m.AsignacionViatico.persona_id.in_(personas))
               .all())
    return [v for v in tocados
            if v.estatus not in SIN_TOCAR or v.comprobantes
            or float(v.monto_comprobado or 0) > 0]


def _mover_el_regreso(db: Session, r: m.ReemplazoRecurso, arranco: m.Jornada,
                      vuelve: m.Jornada, hecho_por_id: int | None,
                      relevado_en: datetime | None,
                      ahora: datetime | None = None) -> dict:
    """El titular dijo otra fecha despues de que ya se capturo el regreso.

    Juan dijo el 25, el consultor lo capturo, y el 24 avisa que mejor el
    28. El movimiento no se duplica: se recorre otra vez y se vuelve a
    firmar, para que el mes siga leyendo un solo hecho.

    Por dentro es el mismo relevo, en el sentido que toque: si se atrasa,
    el que cubria recupera los dias que ya habian vuelto al titular; si
    se adelanta, el titular se lleva unos dias mas.

    Dos cosas lo bloquean, y las dos son la misma: que el dinero ya se
    haya movido. Un viatico pedido, transferido o comprobado no se
    desanda a mano --eso seria peor que el error-- y lo que corresponde
    es un cambio nuevo, con su rastro.
    """
    fin = db.get(m.Jornada, r.hasta_jornada_id) if r.hasta_jornada_id else None
    if not fin:
        raise HTTPException(409, "Ese cambio no tiene ultimo dia que mover")

    # Si el dia del regreso se partio, ese dia ya esta repartido entre los
    # dos y tiene su hora. Moverlo seria rehacer una nomina.
    if _se_partio(db, r, fin):
        raise HTTPException(409, {
            "mensaje": ("El dia del regreso se partio: ese dia ya esta "
                        "repartido entre los dos, con su hora. Para "
                        "cambiarlo hay que hacer un cambio nuevo."),
            "dia": fin.fecha.isoformat(),
        })

    vuelve_hoy = _primer_dia_abierto(db, arranco.equipo_id,
                                     fin.fecha + timedelta(days=1))
    if not vuelve_hoy:
        raise HTTPException(409, "Ya no quedan dias abiertos despues de ese cambio")
    if vuelve.fecha == vuelve_hoy.fecha:
        raise HTTPException(409, {
            "mensaje": "El titular ya regresa ese dia.",
            "regresa": vuelve_hoy.fecha.isoformat()})

    titular, cubre = _quienes(r)
    if vuelve.fecha > vuelve_hoy.fecha:
        # Se atrasa: el que cubria recupera los dias que ya eran del titular.
        hasta = (db.query(m.Jornada)
                 .filter(m.Jornada.equipo_id == arranco.equipo_id,
                         m.Jornada.fecha >= vuelve_hoy.fecha,
                         m.Jornada.fecha < vuelve.fecha,
                         m.Jornada.estatus.notin_([m.EstatusJornada.CANCELADA,
                                                   m.EstatusJornada.TERMINADA]))
                 .order_by(m.Jornada.fecha.desc()).first())
        if not hasta:
            raise HTTPException(409, "No hay dias abiertos que recuperar")
        _no_pasarse_del_tope(arranco, hasta)
        _no_con_dinero(_dinero_trabado(db, r, arranco.equipo_id,
                                       vuelve_hoy.fecha, hasta.fecha))
        hecho = _relevar_al_reves(db, r, vuelve_hoy, hasta, titular, cubre,
                                  hecho_por_id, relevado_en, ahora)
        cerrado = _firmar_el_cierre(db, r, arranco, vuelve, hecho, hecho_por_id)
        # Esos dias no volvieron al titular: se los llevo el que cubre.
        cerrado["jornadas_recuperadas"] = cerrado.pop("jornadas_devueltas")
        cerrado["jornadas_devueltas"] = []
        return cerrado

    # Se adelanta: el titular se lleva unos dias mas.
    _no_con_dinero(_dinero_trabado(db, r, arranco.equipo_id, vuelve.fecha,
                                   fin.fecha))
    hecho = _relevar_al_reves(db, r, vuelve, fin, cubre, titular,
                              hecho_por_id, relevado_en, ahora)
    cerrado = _firmar_el_cierre(db, r, arranco, vuelve, hecho, hecho_por_id)
    cerrado["jornadas_recuperadas"] = []
    return cerrado


def _no_con_dinero(trabados: list[m.AsignacionViatico]) -> None:
    if trabados:
        raise HTTPException(409, {
            "mensaje": ("El dinero de esos dias ya se movio, asi que el "
                        "regreso no se puede correr. Si hay que cambiarlo, "
                        "se hace un cambio nuevo, con su rastro."),
            "viaticos": [v.id for v in trabados],
        })


def _no_pasarse_del_tope(arranco: m.Jornada, hasta: m.Jornada) -> None:
    """Atrasar un regreso no puede saltarse el tope del mes.

    Es el mismo candado de siempre visto por el otro lado: si el regreso
    se corre al 2 de octubre, el que cubre se quedaria con dias de
    octubre que nadie pidio.
    """
    servicio = arranco.equipo.servicio if arranco.equipo else None
    if servicio and servicio.tipo == m.TipoServicio.IMPLANTADO:
        tope = ultimo_dia_del_mes(arranco.fecha)
        if hasta.fecha > tope:
            raise HTTPException(409, {
                "mensaje": ("Ese regreso se pasa del mes. El cambio termina "
                            "el ultimo dia del mes; para seguir despues hay "
                            "que pedirlo otra vez."),
                "tope": tope.isoformat(),
            })


def _firmar_el_cierre(db: Session, r: m.ReemplazoRecurso, arranco: m.Jornada,
                      vuelve: m.Jornada, hecho: dict,
                      hecho_por_id: int | None) -> dict:
    """Recorre el `hasta` del movimiento y lo firma.

    El relevo que acaba de correr abrio su propio movimiento; ese se
    borra aqui, porque el hecho es el cierre del primero y no otro
    cambio.
    """
    partidas = hecho["jornadas_partidas"]
    nuevo = db.get(m.ReemplazoRecurso, hecho["reemplazo_id"])
    # La propuesta se rescata antes de borrar el movimiento temporal: es
    # el unico lugar donde quedo escrita, y sin ella no se puede saber
    # despues si el consultor corrigio la hora del regreso.
    propuesta = nuevo.hora_propuesta if nuevo else None
    if nuevo:
        db.delete(nuevo)

    # Hasta que dia se queda el que cubrio. Si el dia del regreso se
    # partio, ese dia todavia lo trabajo el: cuenta como suyo.
    if vuelve.fecha.isoformat() in partidas:
        ultimo = vuelve
    else:
        ultimo = (db.query(m.Jornada)
                  .filter(m.Jornada.equipo_id == arranco.equipo_id,
                          m.Jornada.fecha >= arranco.fecha,
                          m.Jornada.fecha < vuelve.fecha,
                          m.Jornada.estatus != m.EstatusJornada.CANCELADA)
                  .order_by(m.Jornada.fecha.desc()).first()) or arranco

    # Los dias se recuentan mirando las asignaciones, no restando: un
    # dia partido sigue siendo suyo y una jornada cancelada en medio no
    # lo era.
    tabla, columna = _asignacion_de(r)
    _, cubre = _quienes(r)
    cubiertos = (db.query(tabla.id)
                 .join(m.Jornada, tabla.jornada_id == m.Jornada.id)
                 .filter(m.Jornada.equipo_id == arranco.equipo_id,
                         m.Jornada.fecha >= arranco.fecha,
                         m.Jornada.fecha <= ultimo.fecha,
                         columna == cubre)
                 .count())

    r.hasta_jornada_id = ultimo.id
    r.jornadas_afectadas = cubiertos
    r.regreso_en = reloj.ahora_de_la_jornada(db, vuelve)
    r.regreso_por_id = hecho_por_id
    # Se vuelve a escribir cada vez: si el regreso se corrio y ya no
    # parte ningun dia, tampoco hay propuesta que guardar.
    r.hora_propuesta_regreso = propuesta
    db.flush()

    sale_id, _ = _quienes(r)
    return {
        "cerrado": r.id,
        "servicio_id": r.servicio_id,
        "tipo": r.tipo.value,
        "regresa": _como_se_llama(db, r, sale_id),
        "sale": _como_se_llama(db, r, cubre),
        "desde": arranco.fecha.isoformat(),
        "hasta": ultimo.fecha.isoformat(),
        # El primer dia que vuelve a ser del titular. Es lo que se le
        # dice a los dos en el aviso al telefono (seccion 101).
        "regresa_el": vuelve.fecha.isoformat(),
        "dias_cubiertos": cubiertos,
        "jornadas_devueltas": hecho["jornadas_afectadas"],
        # Los que el que cubria recupera cuando el regreso se atrasa. La
        # primera vez siempre va vacia; la forma es una sola.
        "jornadas_recuperadas": [],
        # Si el que cubria alcanzo a trabajar la manana del dia del
        # regreso, ese dia lo cobran los dos.
        "jornadas_partidas": partidas,
        "jornadas_con_choque": hecho["jornadas_con_choque"],
        # La hora que el sistema propone para partir ese dia: la ultima
        # marca del que cubria. El consultor la confirma o la corrige.
        "hora_propuesta": hecho.get("hora_propuesta"),
        "viaticos": hecho["viaticos"],
        # La unidad que vuelve cambia de manos otra vez: si nadie la
        # recibe, un golpe en ella se queda sin dueno.
        "revision_pendiente": hecho.get("revision_pendiente"),
    }


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


def vista_previa_vehiculo(db: Session, **cambio) -> dict:
    """Lo que haria el cambio de unidad, sin guardarlo (seccion 105,
    decision 3): los dias que se mueven, el que se parte con su hora, la
    revision que queda pendiente. El mismo cambio de verdad, deshecho."""
    try:
        return reemplazar_vehiculo(db, **cambio)
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

    desde = db.get(m.Jornada, reemplazo.desde_jornada_id)
    hasta = (db.get(m.Jornada, reemplazo.hasta_jornada_id)
             if reemplazo.hasta_jornada_id else None)

    # Con el titular ya de vuelta, el movimiento ya no es "hace un
    # minuto" (seccion 101): devolverle sus dias chocaba con la
    # asignacion que el regreso ya le creo y salia "Ese registro ya
    # existe", sin explicacion.
    if reemplazo.regreso_en:
        raise HTTPException(409, {
            "mensaje": ("Este cambio ya se cerró con el regreso del titular: "
                        "no se deshace."),
            "que_hacer": ("Si el regreso quedó en otra fecha, corrígelo "
                          "desde la tarjeta del cambio. Si hay que devolver "
                          "días, se hace un cambio en sentido contrario, "
                          "con su rastro."),
            "regreso_en": reemplazo.regreso_en.isoformat()})

    # La unidad se deshace por su propio camino (seccion 105): no mueve
    # dinero, pero si ya cambio de manos en la calle tampoco se desanda.
    if reemplazo.tipo == m.TipoRecurso.VEHICULO:
        return _deshacer_unidad(db, reemplazo, desde, hasta)

    sale_id, entra_id = reemplazo.sale_persona_id, reemplazo.entra_persona_id

    # Y un dia que ya termino con el cambio hecho se queda como se
    # trabajo: antes se borraba el movimiento y ese dia se quedaba
    # partido, la nomina pagaba a dos y ya no habia nada que lo explicara.
    terminadas = _dias_terminados_con_el_cambio(db, desde, hasta, sale_id,
                                                entra_id)
    if terminadas:
        raise HTTPException(409, {
            "mensaje": ("Este cambio ya no se puede deshacer: el día "
                        f"{', '.join(f.isoformat() for f in terminadas)} ya "
                        "terminó con el cambio hecho."),
            "que_hacer": ("Ese día se trabajó y se paga como quedó. Si hay "
                          "que regresar los días que faltan, se hace un "
                          "cambio en sentido contrario o el regreso del "
                          "titular."),
            "dias": [f.isoformat() for f in terminadas]})

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


def _deshacer_unidad(db: Session, reemplazo: m.ReemplazoRecurso,
                     desde: m.Jornada, hasta: m.Jornada | None) -> dict:
    """Borra un cambio de unidad recien hecho (seccion 105, decision 3).

    Es el gemelo del de personal, para el consultor que eligio la placa
    equivocada hace un minuto. La unidad no mueve viaticos, asi que el
    candado del dinero no aplica; lo que si lo frena es que el cambio ya
    haya ocurrido en la calle: un dia que ya termino con la unidad nueva,
    o la unidad que entro ya recibida con su revision de fotos. Desde
    ahi lo que corresponde es el regreso de la unidad, con su rastro.
    """
    sale_id, entra_id = reemplazo.sale_vehiculo_id, reemplazo.entra_vehiculo_id

    terminadas = _dias_terminados_con_la_unidad(db, desde, hasta, sale_id,
                                                entra_id)
    if terminadas:
        raise HTTPException(409, {
            "mensaje": ("Este cambio ya no se puede deshacer: el día "
                        f"{', '.join(f.isoformat() for f in terminadas)} ya "
                        "terminó con la unidad nueva."),
            "que_hacer": ("Ese día se trabajó con esa unidad y así se queda. "
                          "Si la unidad que salió vuelve, usa «Regresa la "
                          "unidad» en la tarjeta del cambio."),
            "dias": [f.isoformat() for f in terminadas]})

    # La que entro ya esta en manos del equipo: la recibieron con sus
    # fotos y no la han entregado. Deshacer el cambio dejaria una
    # revision de una unidad que "nunca estuvo" en el servicio, y un
    # golpe en ella sin dueno.
    if _en_manos(db, desde, entra_id):
        raise HTTPException(409, {
            "mensaje": ("Este cambio ya no se puede deshacer: la unidad que "
                        "entró ya se recibió con su revisión."),
            "que_hacer": ("El cambio ya ocurrió en la calle. Si la unidad que "
                          "salió vuelve al servicio, usa «Regresa la unidad» "
                          "en la tarjeta del cambio.")})

    devueltas = []
    for j in jornadas_afectadas(db, desde, hasta):
        suya = (db.query(m.AsignacionVehiculo)
                .filter_by(jornada_id=j.id, vehiculo_id=sale_id).first())
        entrante = (db.query(m.AsignacionVehiculo)
                    .filter_by(jornada_id=j.id, vehiculo_id=entra_id).first())
        if suya and suya.relevado_por_vehiculo_id == entra_id:
            # El dia se habia partido: se junta otra vez.
            suya.relevado_en = None
            suya.relevado_por_vehiculo_id = None
            if entrante:
                db.delete(entrante)
            devueltas.append(j.fecha.isoformat())
        elif entrante and not suya:
            # El dia se habia mutado: vuelve a su unidad.
            entrante.vehiculo_id = sale_id
            devueltas.append(j.fecha.isoformat())
        else:
            continue
        # Y quien iba a bordo de la nueva regresa a la de siempre.
        for persona in (db.query(m.AsignacionPersonal)
                        .filter_by(jornada_id=j.id, vehiculo_id=entra_id)
                        .all()):
            persona.vehiculo_id = sale_id

    db.delete(reemplazo)
    db.flush()
    return {"deshecho": reemplazo.id, "jornadas": devueltas}


def _dias_terminados_con_la_unidad(db: Session, desde: m.Jornada,
                                   hasta: m.Jornada | None, sale_id: int,
                                   entra_id: int) -> list[date]:
    """Los dias del tramo que ya terminaron con la unidad que entro: la
    que salio relevada por ella, o ella sola en el dia."""
    consulta = (db.query(m.Jornada)
                .filter(m.Jornada.equipo_id == desde.equipo_id,
                        m.Jornada.fecha >= desde.fecha,
                        m.Jornada.estatus == m.EstatusJornada.TERMINADA))
    if hasta is not None:
        consulta = consulta.filter(m.Jornada.fecha <= hasta.fecha)
    fechas = []
    for j in consulta.order_by(m.Jornada.fecha).all():
        huella = (db.query(m.AsignacionVehiculo.id)
                  .filter(m.AsignacionVehiculo.jornada_id == j.id,
                          ((m.AsignacionVehiculo.vehiculo_id == sale_id)
                           & (m.AsignacionVehiculo.relevado_por_vehiculo_id
                              == entra_id))
                          | (m.AsignacionVehiculo.vehiculo_id == entra_id))
                  .first())
        if huella:
            fechas.append(j.fecha)
    return fechas


def _dias_terminados_con_el_cambio(db: Session, desde: m.Jornada,
                                   hasta: m.Jornada | None, sale_id: int,
                                   entra_id: int) -> list[date]:
    """Los dias del tramo que ya terminaron y en los que el cambio dejo
    huella: el que sale relevado por el que entra, o el que entra en su
    lugar. `jornadas_afectadas` no los trae a proposito --no se tocan--
    y por eso deshacer los dejaba partidos sin movimiento que lo explique.
    """
    consulta = (db.query(m.Jornada)
                .filter(m.Jornada.equipo_id == desde.equipo_id,
                        m.Jornada.fecha >= desde.fecha,
                        m.Jornada.estatus == m.EstatusJornada.TERMINADA))
    if hasta is not None:
        consulta = consulta.filter(m.Jornada.fecha <= hasta.fecha)
    fechas = []
    for j in consulta.order_by(m.Jornada.fecha).all():
        huella = (db.query(m.AsignacionPersonal.id)
                  .filter(m.AsignacionPersonal.jornada_id == j.id,
                          ((m.AsignacionPersonal.persona_id == sale_id)
                           & (m.AsignacionPersonal.relevado_por_id == entra_id))
                          | ((m.AsignacionPersonal.persona_id == entra_id)
                             & (m.AsignacionPersonal.reemplaza_a_id == sale_id)))
                  .first())
        if huella:
            fechas.append(j.fecha)
    return fechas

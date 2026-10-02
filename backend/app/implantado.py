"""Servicios implantados: contratacion mensual con recursos fijos.

El procedimiento diario es identico al eventual. Lo que cambia:
  - Se contrata el mes completo, con una base de dias habiles (22 tipico).
  - Los fines de semana son dias adicionales, con costo extra.
  - El vehiculo se cotiza por mes completo.
  - Los reemplazos por descanso o enfermedad se resuelven sobre la marcha.
  - El cierre de viaticos y la facturacion son mensuales.
"""
import calendar
import logging
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy.orm import Session, object_session

from app import contingencia
from app import disponibilidad
from app import models as m
from app import reloj
from app import viaticos as motor_viaticos

registro = logging.getLogger("centauro.implantado")


# Hasta que dia de la semana llega cada esquema. weekday(): lunes es 0.
HASTA = {
    m.DiasServicio.LUNES_VIERNES: 5,
    m.DiasServicio.LUNES_SABADO: 6,
    m.DiasServicio.TODOS: 7,
}


# Estatus que todavia no llegan a planeado: generar un mes los empuja.
ANTES_DE_PLANEAR = {
    m.EstatusServicio.BORRADOR,
    m.EstatusServicio.SOLICITADO,
    m.EstatusServicio.COTIZADO,
    m.EstatusServicio.AUTORIZADO,
}


# Los dias que cubre el precio fijo del mes en las modalidades de la
# propuesta (seccion 115, decision 3 de Salvador): «22 dias (lunes a
# viernes) mas dias adicionales, 26 dias (lunes a sabado) mas dias
# adicionales o mes completo 30 dias al mes con un costo fijo». El
# mensual de cada puesto es su precio por dia por estos dias y no cambia
# si el mes trae 21 o 23 habiles. El 12x36 cubre los siete dias: va como
# el mes completo.
DIAS_DEL_MENSUAL = {
    m.DiasServicio.LUNES_VIERNES: 22,
    m.DiasServicio.LUNES_SABADO: 26,
    m.DiasServicio.TODOS: 30,
}


def hasta_donde(dias_servicio) -> int:
    """Acepta el esquema o el viejo si/no de fines de semana.

    El contrato mensual se dio de alta mucho antes que el esquema y sigue
    mandando un booleano; traducirlo aqui evita tocar esa puerta.
    """
    if isinstance(dias_servicio, bool):
        return 7 if dias_servicio else 5
    return HASTA.get(dias_servicio, 5)


# Los dos tipos de implantado. El primero es el que Centauro opera en
# Mexico --una persona, doce horas corridas, los dias del acuerdo-- y el
# segundo la escala de Brasil: dos personas de la misma categoria que se
# alternan dia con dia y cubren los siete dias de la semana.
TURNO_NATURAL = "natural"
TURNO_12X36 = "12x36"


def turno_del_servicio(db: Session, servicio_id: int) -> str:
    """Como se cubre el puesto. Sale del acuerdo, que es el trato."""
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio_id).first())
    return (acuerdo.turno if acuerdo and acuerdo.turno else TURNO_NATURAL)


# --------------------------------------------------------------------
# Las horas de la jornada (seccion 105, decision 6)
#
# En Mexico y en Brasil el implantado es de doce horas corridas, y el
# ano que entra va a llevar horas de descanso dentro de esas doce --en
# bloques de una hora, cuatro al dia; el 12x36 no--. Viven en la
# modalidad `implantado` de cada pais (Catalogos > Horas de cada
# modalidad) y el acuerdo las puede corregir por contrato. Hasta aqui el
# implantado tomaba el full day del pais, que en Brasil es de diez horas:
# cada dia que cerraba a las doce generaba dos horas extra.
#
# Las horas extra corren despues de la jornada completa: el descanso va
# adentro y no la alarga ni las recorta. El cliente no ve el descanso;
# lo ve el equipo en su app y lo ve Centauro.
# --------------------------------------------------------------------

HORAS_MAXIMAS_DE_JORNADA = Decimal("24")


def _decimal(valor, si_vacio: str) -> Decimal:
    return Decimal(str(valor if valor is not None else si_vacio))


def modalidad_del_pais(db: Session, pais_id: int | None):
    """La modalidad `implantado` del pais; sin ella --una base de antes
    de la seccion 105 que no corrio la migracion--, el dia completo, que
    es lo que el implantado tomaba hasta entonces."""
    if not pais_id:
        return None
    suya = (db.query(m.Modalidad)
            .filter_by(pais_id=pais_id, codigo=m.CodigoModalidad.IMPLANTADO)
            .first())
    return suya or (db.query(m.Modalidad)
                    .filter_by(pais_id=pais_id,
                               codigo=m.CodigoModalidad.FULL_DAY).first())


def horas_de(contrato: m.ContratoImplantado,
             db: Session | None = None) -> tuple[Decimal, Decimal, Decimal]:
    """(jornada, descanso, intervalo) de ese acuerdo.

    Lo que el contrato trae escrito manda; lo que no, sale de la
    modalidad `implantado` de su pais, leida en vivo: el dia que
    Catalogos ponga las horas de descanso, las tienen todos los
    implantados que no pactaron otras. En 12x36 el descanso es siempre
    cero --dos personas, sin descansos pactados con el cliente--, aunque
    alguien mande otro. Es la unica puerta a estas horas: la jornada, las
    horas extra, el aviso preventivo, el comparativo del mes y la nomina
    salen de aqui.
    """
    db = db or object_session(contrato)
    modalidad = contrato.modalidad
    if db is not None and (modalidad is None
                           or modalidad.codigo != m.CodigoModalidad.IMPLANTADO):
        # Un contrato que todavia apunta al full day (los de antes de la
        # seccion 105): las horas son las del implantado del pais.
        modalidad = modalidad_del_pais(db, contrato.servicio.pais_id) or modalidad
    jornada = (_decimal(contrato.horas_jornada, "12")
               if contrato.horas_jornada is not None
               else _decimal(modalidad.horas if modalidad else None, "12"))
    descanso = (_decimal(contrato.horas_descanso, "0")
                if contrato.horas_descanso is not None
                else _decimal(modalidad.horas_descanso if modalidad else None, "0"))
    intervalo = _decimal(getattr(modalidad, "intervalo_descanso", None), "1")
    if intervalo <= 0:
        intervalo = Decimal("1")
    if db is not None and turno_del_servicio(db, contrato.servicio_id) == TURNO_12X36:
        descanso = Decimal("0")
    return jornada, descanso, intervalo


def validar_horas(jornada, descanso) -> tuple[Decimal | None, Decimal | None]:
    """Las horas que el consultor corrige por contrato: tope de 24 y el
    descanso dentro de la jornada. Vacias, se quedan vacias (las del
    pais)."""
    jornada = Decimal(str(jornada)) if jornada is not None else None
    descanso = Decimal(str(descanso)) if descanso is not None else None
    if jornada is not None and not (0 < jornada <= HORAS_MAXIMAS_DE_JORNADA):
        raise HTTPException(422, {
            "mensaje": f"La jornada de {jornada} horas no cabe en un día",
            "que_hacer": "Escribe cuántas horas dura el turno: 12 en "
                         "México y en Brasil.",
        })
    if descanso is not None and descanso < 0:
        raise HTTPException(422, {
            "mensaje": "Las horas de descanso no pueden ser negativas",
            "que_hacer": "Vacías, van las del país.",
        })
    tope = jornada if jornada is not None else HORAS_MAXIMAS_DE_JORNADA
    if descanso is not None and descanso >= tope:
        raise HTTPException(422, {
            "mensaje": (f"{descanso} horas de descanso no caben en una "
                        f"jornada de {tope}"),
            "que_hacer": "El descanso va dentro de la jornada: tiene que "
                         "ser menor que ella.",
        })
    return jornada, descanso


def horas_de_la_jornada(db: Session, jornada: m.Jornada) -> Decimal | None:
    """Las horas contratadas de un dia de implantado --las de su acuerdo--
    o None si el dia es de un eventual. Es lo que el aviso preventivo y
    el panel del dia dicen como «contratado»."""
    equipo = jornada.equipo
    servicio = equipo.servicio if equipo else None
    if not servicio or servicio.tipo != m.TipoServicio.IMPLANTADO:
        return None
    contrato = (db.query(m.ContratoImplantado)
                .filter_by(servicio_id=servicio.id, anio=jornada.fecha.year,
                           mes=jornada.fecha.month).first())
    if contrato is None:
        return None
    return horas_de(contrato, db)[0]


def descanso_de_la_jornada(db: Session, jornada: m.Jornada) -> dict | None:
    """Lo que la app le dice al equipo de sus descansos: {jornada, horas,
    intervalo} solo cuando el acuerdo los tiene; con cero no se dice nada."""
    equipo = jornada.equipo
    servicio = equipo.servicio if equipo else None
    if not servicio or servicio.tipo != m.TipoServicio.IMPLANTADO:
        return None
    contrato = (db.query(m.ContratoImplantado)
                .filter_by(servicio_id=servicio.id, anio=jornada.fecha.year,
                           mes=jornada.fecha.month).first())
    if contrato is None:
        return None
    jornada_horas, descanso, intervalo = horas_de(contrato, db)
    if descanso <= 0:
        return None
    return {"jornada": float(jornada_horas), "horas": float(descanso),
            "intervalo": float(intervalo)}


def empieza_a_medio_mes(anio: int, mes: int, dias_servicio,
                        desde_dia: int | None,
                        turno: str = TURNO_NATURAL) -> bool:
    """Si el primer mes empezo con el mes ya corrido: despues de algun
    dia de su modalidad (seccion 115). Con el 1 en domingo, el de lunes a
    viernes que empieza el lunes 2 cubre todos los dias del mes y se cobra
    su mensual; por dia, habria salido mas barato que el mes que empieza
    el 1 con los mismos dias de servicio."""
    if not desde_dia or desde_dia <= 1:
        return False
    tope = 7 if turno == TURNO_12X36 else hasta_donde(dias_servicio)
    return any(date(anio, mes, d).weekday() < tope
               for d in range(1, desde_dia))


def termina_a_medio_mes(anio: int, mes: int, dias_servicio,
                        hasta: date | None,
                        turno: str = TURNO_NATURAL) -> bool:
    """Si el implantado se cancelo con el mes a medias: despues de su
    ultimo dia de servicio todavia quedaban dias de su modalidad en el mes
    (seccion 117, decision 4 de Salvador). Ese mes, como el primero que
    empieza a la mitad, se cobra por dia de servicio. Cancelado el ultimo
    dia de su modalidad --el lunes 30, con lunes a viernes--, el mes ya se
    trabajo entero y se cobra su mensual."""
    if hasta is None or (hasta.year, hasta.month) != (anio, mes):
        return False
    tope = 7 if turno == TURNO_12X36 else hasta_donde(dias_servicio)
    ultimo = calendar.monthrange(anio, mes)[1]
    return any(date(anio, mes, d).weekday() < tope
               for d in range(hasta.day + 1, ultimo + 1))


def dias_del_mes(anio: int, mes: int, dias_servicio,
                desde_dia: int | None = None,
                turno: str = TURNO_NATURAL) -> list[date]:
    """Los dias que cubre el contrato dentro del mes.

    Con desde_dia arranca a media marcha: un servicio que empieza el 15 se
    cobra del 15 al ultimo dia y el corte cae ahi. El mes siguiente entra
    limpio el dia 1, sin arrastrar el pedazo anterior.

    En 12x36 el mes va entero: la escala cubre los siete dias y no hay
    dias de la semana que elegir.
    """
    tope = 7 if turno == TURNO_12X36 else hasta_donde(dias_servicio)
    ultimo = calendar.monthrange(anio, mes)[1]
    primero = max(1, min(desde_dia or 1, ultimo))
    dias = [date(anio, mes, d) for d in range(primero, ultimo + 1)]
    return [d for d in dias if d.weekday() < tope]


def calendario_del_mes(anio: int, mes: int, dias_servicio,
                       desde_dia: int | None = None,
                       cubiertos: dict | None = None,
                       turno: str = TURNO_NATURAL,
                       cancelados: set | None = None,
                       vacios: set | None = None) -> list[dict]:
    """El mes dia por dia, con el color que le toca a cada uno.

    verde  el dia esta cubierto por los recursos del servicio
    ambar  esta contratado pero falta decir quien lo cubre; casi siempre
           un fin de semana, porque el que trabajo toda la semana
           descansa y hay que confirmarlo o cambiarlo; y el dia de entre
           semana que existe sin nadie --`vacios`-- porque se abrio sin
           la posicion que ya no podia ir (seccion 101)
    gris   no hay servicio contratado ese dia

    En 12x36 el ambar de fin de semana no existe: cada dia nace con su
    persona puesta --las dos se alternan y entre las dos cubren los siete
    dias-- asi que el mes sale entero en verde, salvo el dia vacio.
    """
    es_12x36 = turno == TURNO_12X36
    tope = 7 if es_12x36 else hasta_donde(dias_servicio)
    ultimo = calendar.monthrange(anio, mes)[1]
    primero = max(1, min(desde_dia or 1, ultimo))
    cubiertos = cubiertos or {}
    cancelados = cancelados or set()
    vacios = vacios or set()

    salida = []
    for numero in range(1, ultimo + 1):
        dia = date(anio, mes, numero)
        quien = cubiertos.get(dia.isoformat())
        # Un dia cancelado manda sobre todo lo demas: se saco del
        # servicio. Entre semana el color no sale de que exista la
        # jornada sino de que el dia este contratado, asi que sin esto
        # un dia cancelado a media semana seguia pintado de verde.
        if dia.isoformat() in cancelados:
            estado = "sin_servicio"
            quien = None
        elif quien and numero >= primero:
            # Un dia fuera del esquema que el cliente pidio aparte. Ya
            # tiene quien lo cubra, asi que cuenta como cubierto aunque
            # no entre en los dias contratados.
            estado = "cubierto"
        elif numero < primero or dia.weekday() >= tope:
            estado = "sin_servicio"
        elif quien:
            estado = "cubierto"
        elif not es_12x36 and dia.weekday() >= 5:
            estado = "por_cubrir"
        elif dia.isoformat() in vacios:
            estado = "por_cubrir"
        else:
            # Entre semana lo cubre la plantilla fija; si no hay nadie es
            # que el mes todavia no se genera.
            estado = "cubierto"
        salida.append({
            "fecha": dia.isoformat(),
            "dia": numero,
            "semana": dia.weekday(),
            "fin_de_semana": dia.weekday() >= 5,
            "antes_de_empezar": numero < primero,
            "estado": estado,
            "cubre": quien,
        })
    return salida


def resumen_calendario(anio: int, mes: int) -> dict:
    habiles = dias_del_mes(anio, mes, False)
    todos = dias_del_mes(anio, mes, True)
    return {"dias_habiles": len(habiles), "dias_totales": len(todos),
            "fines_de_semana": len(todos) - len(habiles)}


def generar_mes(db: Session, contrato_id: int,
                rellenando: bool = False) -> dict:
    """Crea las jornadas del mes y asigna los recursos fijos.

    Un implantado son full days encadenados: cada dia se opera igual que
    un eventual, con su ventana de dos horas previas y su ciclo de hitos.

    `rellenando` es para el mes que YA se genero y quedo con huecos:
    correr el arranque hacia adelante borra los dias sin dinero y
    corregirlo despues deja el calendario pintado y sin jornada detras.
    El candado de abajo existe para que nadie genere dos veces un mes
    completo por error; rellenar es otra cosa, y el ciclo de abajo se
    salta uno por uno los dias que ya estan.
    """
    contrato = db.get(m.ContratoImplantado, contrato_id)
    if not contrato:
        raise HTTPException(404, f"No existe el contrato {contrato_id}")
    if contrato.generado and not rellenando:
        raise HTTPException(409, "El calendario de este mes ya se genero")

    servicio = contrato.servicio
    equipo = servicio.equipos[0] if servicio.equipos else None
    if not equipo:
        equipo = m.Equipo(servicio_id=servicio.id, alias="Alfa", clave="Alfa",
                          descripcion="Implantado mensual")
        db.add(equipo)
        db.flush()

    hora = time.fromisoformat(contrato.hora_presentacion)
    # Las horas del acuerdo, no las del full day del pais (seccion 105).
    horas = float(horas_de(contrato, db)[0])

    # El punto de inicio es el mismo todos los dias del implantado: se
    # capturo una vez en el acuerdo y cada jornada lo hereda. Sin esto,
    # el consultor tendria que escribir la misma direccion veintidos
    # veces al mes, y la hoja no se publicaria hasta que lo hiciera.
    #
    # Y del acuerdo sale tambien como se cubre el puesto, que es lo que
    # decide que dias tiene el mes y quien va en cada uno.
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())
    turno = (acuerdo.turno if acuerdo and acuerdo.turno else TURNO_NATURAL)
    es_12x36 = turno == TURNO_12X36

    dias = dias_del_mes(contrato.anio, contrato.mes,
                        contrato.dias_servicio, contrato.desde_dia, turno)

    # La alternancia se resuelve una vez para todo el mes: de que dia
    # arranca y con quien.
    pareja = pareja_del_turno(contrato) if es_12x36 else []
    arranque = (arranque_del_mes(db, contrato, pareja, dias[0])
                if es_12x36 and dias else 0)

    # Lo que de la plantilla ya no puede ir (seccion 101) se resuelve una
    # vez para todo el mes y no se pone en los dias; cada dia que queda
    # sin esa posicion lleva su alerta.
    fuera = plantilla_fuera(db, contrato, dias)
    faltas_del_mes, sin_completar = set(), []

    creadas = 0
    for dia in dias:
        existente = (db.query(m.Jornada)
                     .filter_by(equipo_id=equipo.id, fecha=dia).first())
        if existente:
            continue
        inicio = datetime.combine(dia, hora)
        jornada = m.Jornada(
            equipo_id=equipo.id, fecha=dia, modalidad_id=contrato.modalidad_id,
            inicio_programado=inicio, fin_programado=inicio + timedelta(hours=horas),
            # La hora de un implantado NO es una suposicion: sale del
            # acuerdo con el cliente y es la misma todos los dias. La app
            # escondia la hora de los dias "sin confirmar" --regla hecha
            # para el eventual, donde el dia 2 hereda la del dia 1-- y
            # aqui dejaba al agente sin saber a que hora se presenta.
            hora_confirmada=True,
            # En 12x36 no hay dias adicionales: el mes completo es el
            # trato. Lo que el cliente pida de mas sale como un eventual
            # aparte, no como un dia colgado de este contrato.
            es_dia_adicional=False if es_12x36 else dia.weekday() >= 5)
        _heredar_punto(jornada, acuerdo)
        db.add(jornada)
        db.flush()

        faltas = []
        if es_12x36:
            faltas = _asignar_turno(db, jornada, contrato,
                                    de_quien_es(pareja, arranque, dias[0], dia),
                                    fuera)
        elif dia.weekday() < 5:
            faltas = _asignar_del_contrato(db, jornada, contrato, fuera)
        else:
            # El fin de semana contratado se abre, pero vacio: quien
            # trabajo de lunes a viernes descansa, y darle el sabado por
            # hecho es como se llega al domingo sin conductor. La unidad
            # si va: el vehiculo del implantado siempre es el mismo.
            if contrato.vehiculo_id:
                motivo = _unidad_fuera(fuera, contrato.vehiculo_id, dia)
                if motivo:
                    faltas.append((m.TipoAlerta.VEHICULO_SIN_ASIGNAR, None,
                                   contrato.vehiculo_id, motivo))
                else:
                    db.add(m.AsignacionVehiculo(
                        jornada_id=jornada.id,
                        vehiculo_id=contrato.vehiculo_id))
        if faltas:
            _avisar_lo_que_falta(db, jornada, faltas)
            faltas_del_mes.update(f[3] for f in faltas)
            sin_completar.append(dia.isoformat())
        creadas += 1

    # La base del mes es la que marca el calendario, no un numero fijo.
    contrato.dias_base = len(dias)
    contrato.generado = True
    # La unidad que "dejo el servicio" con el ultimo dia del mes anterior
    # --porque este mes no existia todavia-- vuelve a tener dias: su
    # entrega abierta se va (seccion 128).
    if creadas:
        from app import entregas
        entregas.al_seguir_la_unidad(db, servicio.id)
    # Abrir el mes de noviembre no regresa a planeado un servicio que ya
    # trae hoja liberada y gente en la calle. Solo empuja hacia adelante
    # al que todavia no llegaba ahi.
    if servicio.estatus in ANTES_DE_PLANEAR:
        servicio.estatus = m.EstatusServicio.PLANEADO
    db.commit()

    calendario = resumen_calendario(contrato.anio, contrato.mes)
    return {
        "contrato_id": contrato.id,
        "periodo": f"{contrato.mes:02d}/{contrato.anio}",
        "jornadas_creadas": creadas,
        "dias_base_del_mes": contrato.dias_base,
        "calendario": calendario,
        "turno": turno,
        # Lo que de la plantilla ya no pudo ir y los dias que quedaron
        # sin esa posicion (seccion 101): la pantalla y el proceso de la
        # manana lo dicen en voz alta.
        "plantilla_fuera": sorted(faltas_del_mes),
        "dias_sin_completar": sin_completar,
        "nota": (f"El mes va entero: {contrato.dias_base} dias cubiertos por "
                 f"dos personas que se alternan. No hay dias adicionales; lo "
                 f"que el cliente pida de mas sale como un eventual."
                 if es_12x36 else
                 f"Se factura por los {contrato.dias_base} dias que tiene el mes "
                 f"calendario. Los fines de semana se cobran aparte como dias "
                 f"adicionales."),
    }


def rol_del_contrato(contrato: m.ContratoImplantado,
                     persona_id: int | None = None) -> int | None:
    """Con que rol va esa persona en este servicio.

    Si esta en la plantilla del mes, el suyo. Si es un relevo que viene a
    cubrir sin decir que posicion, la del titular del mes --quien
    maneja, que es la que se cubre casi siempre-- y sin titular, la
    primera de la plantilla: lo que se le vendio al cliente ese dia es
    esa posicion, no la persona. Sin plantilla no hay rol que heredar y
    el consultor lo dice.

    Antes era siempre la primera fila, y con la plantilla capturada
    "coordinador, conductor" el relevo del conductor cobraba y se
    facturaba como coordinador (seccion 101).
    """
    if persona_id:
        suyo = next((f for f in contrato.plantilla
                     if f.persona_id == persona_id), None)
        if suyo and suyo.rol_id:
            return suyo.rol_id
    del_titular = next((f for f in contrato.plantilla
                        if f.persona_id == contrato.titular_id), None)
    if del_titular and del_titular.rol_id:
        return del_titular.rol_id
    return contrato.plantilla[0].rol_id if contrato.plantilla else None


def roles_por_posicion(contrato: m.ContratoImplantado, personal: list,
                       posiciones: list) -> list:
    """El rol de cada renglon con que se cubre un dia (seccion 101).

    El suyo si viene escrito; si la persona es de la plantilla, el de su
    fila; y si es un relevo, el de la posicion que cubre: la que queda
    libre, en el mismo orden en que la ficha lista las posiciones. Asi
    el sabado en que Carlos cubre al conductor, Carlos va de conductor
    aunque la primera fila de la plantilla sea el coordinador: de ese rol
    salen su comision y el precio del dia.
    """
    del_mes = {f.persona_id: f for f in posiciones}
    quienes = {p["persona_id"] for p in personal}
    libres = [f for f in posiciones if f.persona_id not in quienes]
    roles = []
    for fila in personal:
        rol_id = fila.get("rol_id")
        if not rol_id and fila["persona_id"] in del_mes:
            rol_id = del_mes[fila["persona_id"]].rol_id
        if not rol_id and libres:
            rol_id = libres.pop(0).rol_id
        if not rol_id:
            rol_id = rol_del_contrato(contrato, fila["persona_id"])
        roles.append(rol_id)
    return roles


def posiciones_del_dia(db: Session, contrato: m.ContratoImplantado,
                       fecha: date) -> list:
    """Las posiciones que se cubren ese dia: las filas de la plantilla.

    En natural, la plantilla entera: cada dia va todo el equipo. En
    12x36 una sola, la de quien le toca ese dia por la alternancia: el
    dia es de una persona, y ofrecer las dos preseleccionadas dejaba el
    dia con las dos con un clic --las dos cobraban y las dos entraban al
    corte (seccion 101)--.
    """
    filas = sorted(contrato.plantilla, key=lambda f: f.id)
    if turno_del_servicio(db, contrato.servicio_id) != TURNO_12X36:
        return filas
    pareja = pareja_del_turno(contrato)
    dias = dias_del_mes(contrato.anio, contrato.mes, contrato.dias_servicio,
                        contrato.desde_dia, TURNO_12X36)
    if not dias or not pareja:
        return filas[:1]
    arranque = arranque_del_mes(db, contrato, pareja, dias[0])
    de_quien = de_quien_es(pareja, arranque, dias[0], fecha)
    return [de_quien] if de_quien else filas[:1]


def _heredar_punto(jornada: m.Jornada, acuerdo) -> None:
    """El dia toma el punto de inicio del acuerdo, si el acuerdo lo tiene."""
    if not acuerdo or not acuerdo.origen_direccion:
        return
    jornada.origen_direccion = acuerdo.origen_direccion
    jornada.origen_lat = acuerdo.origen_lat
    jornada.origen_lon = acuerdo.origen_lon
    jornada.geocerca_metros = acuerdo.geocerca_metros or 500


def agregar_dia(db: Session, contrato_id: int, fecha: date,
                persona_id: int | None = None) -> dict:
    """El usuario pide un dia adicional, casi siempre un fin de semana.

    Puede ir el titular o alguien mas: el titular descansa el fin de
    semana y el cliente pide sabado, asi que quien cubre se dice aqui y
    no se hereda a ciegas del contrato.
    """
    contrato = db.get(m.ContratoImplantado, contrato_id)
    if not contrato:
        raise HTTPException(404, f"No existe el contrato {contrato_id}")
    if fecha.month != contrato.mes or fecha.year != contrato.anio:
        raise HTTPException(400, "La fecha no cae en el periodo del contrato")
    _que_se_pueda_armar(contrato.servicio)

    # En 12x36 el mes ya esta cubierto entero y no hay dias adicionales:
    # decision de Salvador (20 sep). Lo que el cliente pida de mas es
    # otro servicio, y se cotiza como tal. Colgarlo de este contrato lo
    # dejaria facturado a un precio que nadie pacto para eso.
    if turno_del_servicio(db, contrato.servicio_id) == TURNO_12X36:
        raise HTTPException(409, {
            "mensaje": "Un 12 x 36 no lleva dias adicionales: el mes ya va "
                       "entero.",
            "que_hacer": "Lo que el cliente pida de mas --otra persona, otro "
                         "turno, un traslado-- sale como un servicio eventual "
                         "aparte, con su propia cotizacion.",
        })

    # Un dia que entra despues de T0 (seccion 56): con el mes en
    # comprobacion o sin visto bueno el termino se deshace y el mes
    # vuelve a cerrar con su nuevo ultimo dia; con el visto bueno dado
    # ya no entra: la factura del mes salio con los dias que tenia.
    from app import cierre_mes
    cierre_mes.deshacer_termino(db, contrato, "ya no entra un dia nuevo")

    equipo = contrato.servicio.equipos[0]
    ya_esta = (db.query(m.Jornada)
               .filter_by(equipo_id=equipo.id, fecha=fecha).first())
    if ya_esta:
        # El dia ya existe. Si nadie lo cubre —el fin de semana que nace
        # en ambar— esto es justamente ponerle quien va, no un error.
        # Cancelado, primero se reactiva (seccion 101): "ya esta
        # cubierto" no decia nada de por que no se podia.
        _sin_cancelar(ya_esta)
        if ya_esta.personal:
            raise HTTPException(409, "Ese dia ya esta cubierto")
        return _cubrir(db, contrato, ya_esta, persona_id)

    inicio, fin = _ventana(contrato, fecha)
    # Adicional solo el fin de semana, con la misma regla que cubrir un
    # dia y que generar el mes (seccion 101). Nacia siempre adicional, y
    # un martes borrado por error y vuelto a abrir se facturaba al precio
    # del dia adicional.
    adicional = fecha.weekday() >= 5
    jornada = m.Jornada(
        equipo_id=equipo.id, fecha=fecha, modalidad_id=contrato.modalidad_id,
        inicio_programado=inicio, fin_programado=fin,
        hora_confirmada=True, es_dia_adicional=adicional)
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=contrato.servicio_id).first())
    _heredar_punto(jornada, acuerdo)
    db.add(jornada)
    db.flush()

    cubre_id = persona_id or contrato.titular_id
    if cubre_id:
        _que_pueda_cubrir(db, cubre_id)
        db.add(m.AsignacionPersonal(
            jornada_id=jornada.id, persona_id=cubre_id,
            rol_id=rol_del_contrato(contrato, cubre_id)))
    if contrato.vehiculo_id:
        db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                    vehiculo_id=contrato.vehiculo_id))
        db.flush()
        # El sabado que entra despues del viernes cerrado: la unidad
        # sigue y su entrega abierta se va (seccion 128).
        from app import entregas
        entregas.al_seguir_la_unidad(db, contrato.servicio_id)
    db.commit()

    cubre = db.get(m.Persona, cubre_id) if cubre_id else None
    return {"jornada_id": jornada.id, "fecha": fecha.isoformat(),
            "es_dia_adicional": adicional,
            "cubre": cubre.nombre if cubre else None,
            "costo_extra": (float(contrato.precio_dia_adicional or 0)
                            if adicional else 0.0)}


def _cubrir(db: Session, contrato: m.ContratoImplantado, jornada: m.Jornada,
            persona_id: int | None) -> dict:
    """Le pone gente a un dia que ya existe pero esta vacio.

    La regla del fin de semana: si cubre alguien distinto del titular, ese
    alguien se queda con los dos dias del fin, no con uno. Partir un fin
    de semana entre dos personas es como se pierde el sabado en la
    tarde: nadie sabe quien entrega a quien.
    """
    cubre_id = persona_id or contrato.titular_id
    if not cubre_id:
        raise HTTPException(409, "No hay a quien asignarle ese dia")
    _que_pueda_cubrir(db, cubre_id)

    dias = [jornada]
    if jornada.fecha.weekday() >= 5:
        # El otro dia de ese mismo fin de semana, si tambien esta abierto
        # y tambien esta vacio. Cancelado no se arrastra: ese se
        # reactiva a proposito (seccion 101).
        paso = 1 if jornada.fecha.weekday() == 5 else -1
        vecino = (db.query(m.Jornada)
                  .filter_by(equipo_id=jornada.equipo_id,
                             fecha=jornada.fecha + timedelta(days=paso))
                  .first())
        if (vecino and vecino.fecha.weekday() >= 5 and not vecino.personal
                and vecino.estatus != m.EstatusJornada.CANCELADA):
            dias.append(vecino)

    for dia in dias:
        db.add(m.AsignacionPersonal(
            jornada_id=dia.id, persona_id=cubre_id,
            rol_id=rol_del_contrato(contrato, cubre_id)))
        if contrato.vehiculo_id and not dia.vehiculos:
            db.add(m.AsignacionVehiculo(jornada_id=dia.id,
                                        vehiculo_id=contrato.vehiculo_id))
    if contrato.vehiculo_id:
        db.flush()
        from app import entregas
        entregas.al_seguir_la_unidad(db, contrato.servicio_id)
    db.commit()

    # Lo que de verdad es adicional --el fin de semana-- se cobra aparte;
    # un dia habil vuelto a cubrir es un dia base (seccion 101).
    adicionales = [d for d in dias if d.es_dia_adicional]
    cubre = db.get(m.Persona, cubre_id)
    return {"jornada_id": jornada.id, "fecha": jornada.fecha.isoformat(),
            "es_dia_adicional": jornada.es_dia_adicional, "cubre": cubre.nombre,
            "dias_cubiertos": [d.fecha.isoformat() for d in dias],
            "costo_extra": float(contrato.precio_dia_adicional or 0)
                           * len(adicionales)}


def taller_de(db: Session, vehiculo_ids: list[int]) -> dict:
    """Los bloqueos de taller de esas unidades, agrupados por unidad.

    Se traen de un golpe y se preguntan en memoria: medir un mes son
    veintidos dias por unidad, y una consulta por dia son cientos.
    """
    if not vehiculo_ids:
        return {}
    filas = (db.query(m.TallerVehiculo)
             .filter(m.TallerVehiculo.vehiculo_id.in_(vehiculo_ids)).all())
    por_unidad: dict = {}
    for fila in filas:
        por_unidad.setdefault(fila.vehiculo_id, []).append(fila)
    return por_unidad


def en_taller(bloqueos, dia: date) -> bool:
    """Si ese dia la unidad esta fuera de circulacion."""
    return any(b.cubre(dia) for b in (bloqueos or []))


def _ya_empezo(jornada: m.Jornada) -> bool:
    """Un dia que ya arranco no se toca: eso es un servicio que se dio."""
    return bool(jornada.inicio_real) or jornada.estatus in (
        *m.ARRANCADAS, m.EstatusJornada.TERMINADA)


# El implantado que ya no se arma (seccion 101): al cancelado --o cerrado
# o terminado-- no se le cubren dias ni se le devuelven los cancelados.
# Sus meses se consultan y se cierran; lo que haya que corregir se
# resuelve en el cierre de cada mes. Es la misma regla que el eventual
# gano en la seccion 98.
YA_NO_SE_ARMA = (m.EstatusServicio.CANCELADO, m.EstatusServicio.CERRADO,
                 m.EstatusServicio.TERMINADO)


def _que_se_pueda_armar(servicio: m.Servicio) -> None:
    if servicio.estatus in YA_NO_SE_ARMA:
        raise HTTPException(409, {
            "mensaje": f"El implantado ya está {servicio.estatus.value}: no "
                       "se le cubren ni se le devuelven días",
            "que_hacer": "Sus meses se consultan y se cierran desde su "
                         "pantalla. Si el cliente lo vuelve a pedir, se da "
                         "de alta otro implantado.",
        })


def _sin_cancelar(jornada: m.Jornada) -> None:
    """Un dia cancelado no se cubre: primero se devuelve al servicio.

    Cubrirlo contestaba 200, le ponia gente y lo dejaba cancelado: la
    ficha decia "cubierto", el calendario "cancelado", el agente no lo
    veia en su app y no se cobraba ni se pagaba (seccion 101). No se
    revive solo porque un dia puede estar cancelado porque el cliente no
    lo pidio: se reactiva a proposito, con su rastro, y despues se cubre.
    """
    if jornada.estatus == m.EstatusJornada.CANCELADA:
        raise HTTPException(409, {
            "mensaje": f"El día {jornada.fecha.isoformat()} está cancelado: "
                       "no se cubre",
            "que_hacer": "Primero reactívalo desde la ficha del día "
                         "(«Reactivar el día») y después dile quién lo "
                         "cubre.",
        })


def bajar_acuerdo_a_los_dias(db: Session, servicio: m.Servicio,
                             acuerdo) -> list[str]:
    """Reaplica el punto del acuerdo a los dias que no han arrancado.

    El acuerdo es la hoja maestra del servicio; los dias son copias de
    trabajo. Cuando las dos dicen cosas distintas, manda el acuerdo.
    """
    equipo = servicio.equipos[0] if servicio.equipos else None
    if not equipo or not acuerdo or not acuerdo.origen_direccion:
        return []
    tocados = []
    for j in equipo.jornadas:
        if j.estatus == m.EstatusJornada.CANCELADA or _ya_empezo(j):
            continue
        if (j.origen_direccion == acuerdo.origen_direccion
                and j.origen_lat == acuerdo.origen_lat
                and j.origen_lon == acuerdo.origen_lon):
            continue
        _heredar_punto(j, acuerdo)
        tocados.append(j.fecha.isoformat())
    db.flush()
    return sorted(tocados)


def dias_cancelados_dentro(db: Session, servicio: m.Servicio,
                           desde: date | None) -> list[dict]:
    """Los dias cancelados que vuelven a caer dentro del arranque.

    Se dicen, no se reviven: un dia puede estar cancelado porque el
    cliente no lo pidio, y devolverlo al servicio en silencio pondria a
    alguien a trabajar un dia que nadie contrato.
    """
    equipo = servicio.equipos[0] if servicio.equipos else None
    if not equipo or not desde:
        return []
    dentro = sorted(
        (j for j in equipo.jornadas
         if j.fecha >= desde and j.estatus == m.EstatusJornada.CANCELADA),
        key=lambda j: j.fecha)
    return [{
        "jornada_id": j.id,
        "fecha": j.fecha.isoformat(),
        "personal": [a.persona.nombre for a in j.personal if a.persona],
    } for j in dentro]


def dias_que_faltan(db: Session, servicio: m.Servicio,
                    desde: date | None) -> list[str]:
    """Los dias que el contrato dice que existen y no estan en la base.

    Se borran al correr el arranque hacia adelante --un dia sin dinero se
    borra, no se cancela-- y corregir la fecha despues no los devuelve.
    El calendario los pinta verdes igual, porque entre semana el color
    sale del rango contratado, asi que el hueco no se ve hasta que
    alguien busca quien trabaja ese dia.
    """
    equipo = servicio.equipos[0] if servicio.equipos else None
    if not equipo or not desde:
        return []
    contrato = (db.query(m.ContratoImplantado)
                .filter_by(servicio_id=servicio.id, anio=desde.year,
                           mes=desde.month).first())
    if not contrato:
        return []
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())
    turno = acuerdo.turno if acuerdo and acuerdo.turno else TURNO_NATURAL
    deberian = dias_del_mes(contrato.anio, contrato.mes,
                            contrato.dias_servicio, contrato.desde_dia, turno)
    hay = {j.fecha for j in equipo.jornadas}
    return [d.isoformat() for d in deberian if d not in hay]


def reactivar_dia(db: Session, servicio: m.Servicio, fecha: date) -> dict:
    """Devuelve al servicio un dia que se habia cancelado."""
    _que_se_pueda_armar(servicio)
    equipo = servicio.equipos[0] if servicio.equipos else None
    jornada = (db.query(m.Jornada)
               .filter_by(equipo_id=equipo.id, fecha=fecha).first()
               if equipo else None)
    if not jornada:
        raise HTTPException(404, "Ese dia no existe en el servicio")
    if jornada.estatus != m.EstatusJornada.CANCELADA:
        raise HTTPException(409, "Ese dia no esta cancelado")
    # Un dia que vuelve despues de T0 deshace el termino del mes; con el
    # visto bueno dado ya no vuelve (seccion 56).
    from app import cierre_mes
    cierre_mes.deshacer_termino(db, cierre_mes.contrato_de(db, jornada),
                                "ya no vuelve un dia cancelado")
    jornada.estatus = m.EstatusJornada.PLANEADA
    db.commit()
    return {"reactivado": fecha.isoformat()}


def cambiar_hora_presentacion(db: Session, servicio: m.Servicio,
                              contrato: m.ContratoImplantado,
                              hora: str) -> dict:
    """Mueve el meet and greet de un mes ya abierto.

    La hora vive en el contrato del mes y de ahi salen la ventana de
    cada dia, la geocerca y el aviso al personal. Cambiarla sin mover
    los dias dejaria el acuerdo diciendo una cosa y la app del agente
    otra.
    """
    time.fromisoformat(hora)              # que reviente aqui si viene mal
    contrato.hora_presentacion = hora

    equipo = servicio.equipos[0] if servicio.equipos else None
    movidos, trabados = [], []
    if equipo:
        ultimo = calendar.monthrange(contrato.anio, contrato.mes)[1]
        desde = date(contrato.anio, contrato.mes, 1)
        hasta = date(contrato.anio, contrato.mes, ultimo)
        for j in equipo.jornadas:
            if not (desde <= j.fecha <= hasta):
                continue
            if j.estatus == m.EstatusJornada.CANCELADA:
                continue
            if _ya_empezo(j):
                trabados.append(j.fecha.isoformat())
                continue
            j.inicio_programado, j.fin_programado = _ventana(contrato, j.fecha)
            j.hora_confirmada = True
            movidos.append(j.fecha.isoformat())
    db.flush()
    return {"hora": hora, "anio": contrato.anio, "mes": contrato.mes,
            "dias_movidos": sorted(movidos), "dias_trabados": sorted(trabados)}


def dias_fuera_del_inicio(db: Session, servicio: m.Servicio,
                          desde: date | None) -> list[dict]:
    """Los dias ya generados que quedaron antes del nuevo arranque.

    Se dice quien iba, porque el consultor no decide sobre una fecha: lo
    decide sobre "el lunes 21 iba Juan". Y se dice cual se puede cerrar
    y cual no: un dia que ya arranco es un servicio que se dio.
    """
    equipo = servicio.equipos[0] if servicio.equipos else None
    if not equipo or not desde:
        return []
    fuera = sorted(
        (j for j in equipo.jornadas
         if j.fecha < desde and j.estatus != m.EstatusJornada.CANCELADA),
        key=lambda j: j.fecha)
    return [{
        "jornada_id": j.id,
        "fecha": j.fecha.isoformat(),
        "personal": [a.persona.nombre for a in j.personal if a.persona],
        "se_puede_cerrar": not _ya_empezo(j),
    } for j in fuera]


def _ventana(contrato: m.ContratoImplantado, fecha: date):
    """De que hora a que hora corre ese dia, segun el contrato: su hora
    de presentacion y las horas de su acuerdo (seccion 105)."""
    hora = time.fromisoformat(contrato.hora_presentacion)
    inicio = datetime.combine(fecha, hora)
    return inicio, inicio + timedelta(hours=float(horas_de(contrato)[0]))


def _vecino_del_fin(db: Session, equipo_id: int, fecha: date,
                    dias_servicio) -> date | None:
    """El otro dia de ese mismo fin de semana, si tambien esta contratado.

    Un fin de semana se resuelve completo: cambiar el sabado arrastra el
    domingo. Partirlo entre dos personas es como se pierde el sabado en
    la tarde.
    """
    if fecha.weekday() < 5:
        return None
    paso = 1 if fecha.weekday() == 5 else -1
    otro = fecha + timedelta(days=paso)
    if otro.month != fecha.month:
        return None
    if otro.weekday() >= hasta_donde(dias_servicio):
        return None            # ese dia no esta contratado
    return otro


def dia_del_servicio(db: Session, servicio: m.Servicio, fecha: date) -> dict:
    """Como esta ese dia y quien lo puede cubrir.

    La lista sale de quien esta libre ese dia, no de quien esta en la
    plantilla: el conductor que cubre de lunes a viernes puede traer otro
    servicio ese sabado, y eso hay que verlo antes de asignarlo.

    Va en dos bloques —el equipo del mes primero, el resto de la ciudad
    despues— porque lo normal es que lo cubra el mismo equipo, y lo que
    es normal tiene que estar a la mano.
    """
    contrato = (db.query(m.ContratoImplantado)
                .filter_by(servicio_id=servicio.id, anio=fecha.year,
                           mes=fecha.month).first())
    if not contrato:
        raise HTTPException(409, f"El mes {fecha.month:02d}/{fecha.year} "
                                 f"no esta abierto")

    equipo = servicio.equipos[0] if servicio.equipos else None
    jornada = (db.query(m.Jornada)
               .filter_by(equipo_id=equipo.id, fecha=fecha).first()
               if equipo else None)

    contratado = fecha.weekday() < hasta_donde(contrato.dias_servicio)
    empezado = not contrato.desde_dia or fecha.day >= contrato.desde_dia
    cancelado = bool(jornada and jornada.estatus == m.EstatusJornada.CANCELADA)
    if cancelado:
        # Se dice antes que "cubierto": el dia cancelado conserva a su
        # gente por el rastro del dinero, y la ficha lo daba por
        # cubierto mientras el calendario lo pintaba cancelado
        # (seccion 101). Lo que se ofrece aqui es reactivarlo.
        estado = "cancelado"
    elif jornada and jornada.personal:
        estado = "cubierto"
    elif jornada or (contratado and empezado):
        estado = "por_cubrir"
    else:
        estado = "sin_servicio"

    inicio, fin = _ventana(contrato, fecha)
    del_mes = {p.persona_id for p in contrato.plantilla}

    libres = []
    for persona in (db.query(m.Persona)
                    .filter(m.Persona.plaza_id == servicio.plaza_id,
                            m.Persona.activo.is_(True),
                            # La oficina no cubre dias (seccion 74), y el
                            # freelance tampoco: solo va en eventuales
                            # (seccion 111).
                            m.Persona.oficina.is_(False),
                            m.Persona.es_freelance.is_(False)).all()):
        # Sin filtrar por puesto: el personal de seguridad es general y
        # el rol lo decide el consultor al cubrir el dia.
        hallazgos = disponibilidad.revisar_persona(
            db, persona.id, inicio, fin, contrato.modalidad.bloquea_dia_completo,
            excluir_jornada_id=jornada.id if jornada else None)
        libres.append({
            "persona_id": persona.id, "nombre": persona.nombre,
            "del_equipo": persona.id in del_mes,
            "ocupado": any(x.nivel == "bloqueo" for x in hallazgos),
            # La llave es `motivo`: `como_dict()` nunca tuvo `mensaje`,
            # asi que esto reventaba con KeyError en cuanto habia un
            # hallazgo --o sea, justo cuando esa persona SI tenia un
            # choque, que es cuando la pantalla mas falta hace--. Los
            # dias que ya tenian jornada no fallaban solo porque al
            # excluir la suya no quedaba ninguno.
            "avisos": [x.como_dict().get("motivo") or x.nivel
                       for x in hallazgos],
        })
    libres.sort(key=lambda x: (not x["del_equipo"], x["ocupado"], x["nombre"]))

    # Las posiciones del mes: a quien hay que reemplazar y con que unidad.
    # En 12x36, una sola: la de quien le toca ese dia (seccion 101).
    posiciones = [{
        "persona_id": p.persona_id,
        "nombre": p.persona.nombre if p.persona else None,
        "rol_id": p.rol_id,
        "rol": p.rol.nombre if p.rol else None,
        "vehiculo_id": p.vehiculo_id,
        "placa": p.vehiculo.placa if p.vehiculo else None,
    } for p in posiciones_del_dia(db, contrato, fecha)]

    vecino = _vecino_del_fin(db, equipo.id if equipo else 0, fecha,
                             contrato.dias_servicio)
    return {
        "fecha": fecha.isoformat(), "estado": estado,
        # El numero de la jornada, para poder abrir su bitacora desde
        # aqui. La ficha decia quien iba ese dia y no decia que paso,
        # que son las dos mitades de la misma pregunta.
        "jornada_id": jornada.id if jornada else None,
        "fin_de_semana": fecha.weekday() >= 5,
        "otro_dia_del_fin": vecino.isoformat() if vecino else None,
        "contrato_id": contrato.id,
        "posiciones": posiciones,
        "cubren": ([{"persona_id": a.persona_id,
                     "nombre": a.persona.nombre if a.persona else None}
                    for a in jornada.personal] if jornada else []),
        "se_puede_cerrar": bool(jornada and not cancelado
                                and not _ya_empezo(jornada)),
        # El cancelado se devuelve al servicio desde aqui, con su rastro;
        # cubrirlo directo se rechaza (seccion 101).
        "se_puede_reactivar": cancelado
                              and servicio.estatus not in YA_NO_SE_ARMA,
        "candidatos": libres,
    }


def cubrir_dia(db: Session, servicio: m.Servicio, fecha: date,
               personal: list, ambos_dias: bool = True) -> dict:
    """Abre o cubre un dia con las posiciones del mes.

    La plantilla del implantado no crece: el dia se cubre con las mismas
    posiciones, con su gente o con un relevo en su lugar. Si el cliente
    quiere personal adicional eso es otro servicio —un eventual, con su
    folio y su hoja—, no un implantado mas grande.
    """
    contrato = (db.query(m.ContratoImplantado)
                .filter_by(servicio_id=servicio.id, anio=fecha.year,
                           mes=fecha.month).first())
    if not contrato:
        raise HTTPException(409, f"El mes {fecha.month:02d}/{fecha.year} "
                                 f"no esta abierto")
    _que_se_pueda_armar(servicio)
    if not personal:
        raise HTTPException(409, "Hay que decir quien cubre el dia")
    # En 12x36 el dia es de una sola persona: con las dos, las dos
    # cobraban el dia y las dos entraban al corte (seccion 101). El
    # relevo de quien no puede ir se hace con "Cambiar".
    if (len(personal) > 1
            and turno_del_servicio(db, servicio.id) == TURNO_12X36):
        raise HTTPException(409, {
            "mensaje": "Un día de 12 x 36 lo cubre una sola persona, y "
                       f"vienen {len(personal)}",
            "que_hacer": "Ese día es de quien le toca por la escala. Si no "
                         "puede ir, el relevo se hace con «Cambiar», y si "
                         "el cliente pide a alguien más, es un eventual "
                         "aparte.",
        })
    # Lo mismo que el dia adicional: despues de T0 un dia nuevo deshace
    # el termino del mes, y con el visto bueno dado ya no entra.
    from app import cierre_mes
    cierre_mes.deshacer_termino(db, contrato, "ya no entra un dia nuevo")

    equipo = servicio.equipos[0]
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())

    dias = [fecha]
    if ambos_dias:
        vecino = _vecino_del_fin(db, equipo.id, fecha, contrato.dias_servicio)
        if vecino:
            dias.append(vecino)

    # Con que rol va cada quien: por la posicion que cubre (seccion 101).
    roles = roles_por_posicion(contrato, personal,
                               posiciones_del_dia(db, contrato, fecha))

    tocados = []
    for dia in sorted(dias):
        jornada = (db.query(m.Jornada)
                   .filter_by(equipo_id=equipo.id, fecha=dia).first())
        if jornada and _ya_empezo(jornada):
            raise HTTPException(409, f"El dia {dia.isoformat()} ya empezo")
        if jornada and jornada.estatus == m.EstatusJornada.CANCELADA:
            # El dia pedido se rechaza con su porque; el otro dia del fin
            # que este cancelado no se arrastra: se reactiva a proposito.
            if dia == fecha:
                _sin_cancelar(jornada)
            continue

        if not jornada:
            inicio, fin = _ventana(contrato, dia)
            jornada = m.Jornada(
                equipo_id=equipo.id, fecha=dia,
                modalidad_id=contrato.modalidad_id,
                inicio_programado=inicio, fin_programado=fin,
                hora_confirmada=True,
                es_dia_adicional=dia.weekday() >= 5)
            _heredar_punto(jornada, acuerdo)
            db.add(jornada)
            db.flush()

        # Se rehace: cubrir un dia dos veces no lo llena de gente.
        for asignacion in list(jornada.personal):
            db.delete(asignacion)
        for asignacion in list(jornada.vehiculos):
            db.delete(asignacion)
        db.flush()

        for fila, rol_id in zip(personal, roles):
            persona_id = fila["persona_id"]
            _que_pueda_cubrir(db, persona_id)
            db.add(m.AsignacionPersonal(
                jornada_id=jornada.id, persona_id=persona_id,
                rol_id=rol_id, vehiculo_id=fila.get("vehiculo_id")))
        for vehiculo_id in {f.get("vehiculo_id") for f in personal if f.get("vehiculo_id")}:
            db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                        vehiculo_id=vehiculo_id))
        tocados.append(dia)

    db.commit()
    return {"dias": [d.isoformat() for d in tocados],
            "personal": len(personal)}


def cerrar_dia(db: Session, servicio: m.Servicio, fecha: date) -> dict:
    """Cierra un dia que se abrio por error.

    Solo mientras nadie haya marcado nada: despues es un servicio que se
    dio, y borrarlo seria borrar lo que paso.
    """
    equipo = servicio.equipos[0] if servicio.equipos else None
    jornada = (db.query(m.Jornada)
               .filter_by(equipo_id=equipo.id, fecha=fecha).first()
               if equipo else None)
    if not jornada:
        raise HTTPException(404, "Ese dia no esta abierto")
    if _ya_empezo(jornada):
        raise HTTPException(409, "Ese dia ya empezo: no se puede cerrar")
    # Si con este dia el mes se queda sin nada por trabajar, arranca su
    # cierre (seccion 56): ya no hay otro dia cuyo termino lo dispare.
    from app import cierre_mes
    contrato = cierre_mes.contrato_de(db, jornada)

    # El dinero de ese dia. Lo que ya salio del banco no se borra con un
    # dia: primero hay que resolver el deposito.
    viaticos = (db.query(m.AsignacionViatico)
                .filter_by(jornada_id=jornada.id).all())
    con_dinero = []
    for v in viaticos:
        fuera = (db.query(m.SolicitudTransferencia)
                 .filter(m.SolicitudTransferencia.asignacion_id == v.id,
                         m.SolicitudTransferencia.estatus
                         != m.EstatusTransferencia.CANCELADA)
                 .first())
        if fuera or v.estatus != m.EstatusViatico.ASIGNADO:
            con_dinero.append(v)
    # Lo que apunta al dia --un cambio de vacaciones que empieza o
    # termina ahi, una alerta, una marca-- tambien lo cancela en vez de
    # borrarlo (seccion 98): borrarlo reventaba con "el registro hace
    # referencia a algo que no existe".
    from app.routers.servicios import _limpiar_jornadas, _movimientos
    con_rastro = bool(_movimientos(db, [jornada.id])) or bool(
        db.query(m.ReemplazoRecurso).filter(
            (m.ReemplazoRecurso.desde_jornada_id == jornada.id)
            | (m.ReemplazoRecurso.hasta_jornada_id == jornada.id)).count()
        or db.query(m.Alerta).filter_by(jornada_id=jornada.id).count()
        or db.query(m.Reemplazo).filter_by(jornada_id=jornada.id).count())
    if con_dinero or con_rastro:
        # El dia se cancela, no se borra. Decision de Salvador, 21 sep.
        #
        # Borrarlo se llevaria por delante el viatico y con el la prueba
        # de que ese dinero salio del banco y llego a una cuenta. Y
        # bloquear el cierre dejaba al consultor atorado: para devolver
        # el dinero del dia hace falta que el dia exista, y para cerrar
        # el dia hacia falta que el dinero ya hubiera vuelto.
        #
        # Cancelado sale de la app del personal y del calendario, y su
        # viatico sigue vivo para resolverse por devolucion.
        # Lo que no ha salido se cancela con su solicitud (seccion 98):
        # la pendiente se cancela y la enviada queda pedida a finanzas.
        ahora = reloj.ahora_del_servicio(db, servicio)
        pedidas = 0
        for v in viaticos:
            pedidas += motor_viaticos.cancelar(db, v, ahora)["pedidas"]
        salio = [v for v in con_dinero
                 if v.estatus in motor_viaticos.CON_DINERO_AFUERA]
        total = sum((Decimal(str(v.monto_total or 0)) for v in salio),
                    Decimal("0"))
        quienes = ", ".join(sorted(
            v.persona.nombre for v in salio if v.persona))
        jornada.estatus = m.EstatusJornada.CANCELADA
        cierre_mes.terminar_si_cerro_el_mes(
            db, contrato, registrado=reloj.ahora_del_servicio(db, servicio))
        db.commit()
        if salio:
            nota = (f"El dia queda cancelado: trae {total} de {quienes} "
                    f"que ya salio del banco. Ese dinero se resuelve "
                    f"con la devolucion, no borrando el dia.")
        else:
            nota = "El dia queda cancelado, no borrado: ya tenia rastro."
        if pedidas:
            nota += (f" Finanzas tiene {pedidas} deposito(s) de ese dia en "
                     f"camino: se le pidio cancelarlos.")
        return {"cancelado": fecha.isoformat(), "borrado": False,
                "viaticos_vivos": len(salio), "monto": str(total),
                "pedidas_a_finanzas": pedidas, "nota": nota}

    # Lo que solo estaba asignado se va con el dia: ese dinero no existe
    # todavia fuera del sistema. Y lo que cuelga del dia --su trayecto,
    # sus asignaciones-- con el, con la misma limpieza del eventual.
    _limpiar_jornadas(db, [jornada.id])
    db.flush()

    db.delete(jornada)
    cierre_mes.terminar_si_cerro_el_mes(
        db, contrato, registrado=reloj.ahora_del_servicio(db, servicio))
    db.commit()
    return {"cerrado": fecha.isoformat(),
            "viaticos_borrados": len(viaticos)}


def _cambios_de_personal(db: Session, jornadas: list) -> list[dict]:
    """Quien cubrio a quien en el mes, de las dos tablas.

    La vieja guarda un dia suelto y la nueva un tramo, asi que las dos se
    dicen igual: desde, hasta y cuantos dias. Un cambio de un dia tiene
    desde igual a hasta.

    Los dias partidos van aparte porque son los que explican por que el
    mismo dia aparece dos veces en la nomina: ese dia lo trabajaron dos
    personas y las dos cobran su parte.
    """
    if not jornadas:
        return []
    ids = [j.id for j in jornadas]
    fecha_de = {j.id: j.fecha for j in jornadas}
    salida = []

    for r in (db.query(m.Reemplazo)
              .filter(m.Reemplazo.jornada_id.in_(ids)).all()):
        dia = fecha_de[r.jornada_id].isoformat()
        salida.append({"desde": dia, "hasta": dia, "fecha": dia, "dias": 1,
                       "sale": r.sale.nombre, "entra": r.entra.nombre,
                       "motivo": r.motivo.value, "nota": r.nota,
                       "jornadas_partidas": []})

    for r in (db.query(m.ReemplazoRecurso)
              .filter(m.ReemplazoRecurso.desde_jornada_id.in_(ids),
                      m.ReemplazoRecurso.tipo == m.TipoRecurso.PERSONAL).all()):
        sale = db.get(m.Persona, r.sale_persona_id) if r.sale_persona_id else None
        entra = db.get(m.Persona, r.entra_persona_id) if r.entra_persona_id else None
        desde = fecha_de.get(r.desde_jornada_id)
        hasta = fecha_de.get(r.hasta_jornada_id) if r.hasta_jornada_id else None
        # Los dias que se partieron: la asignacion del que salio sigue
        # ahi, con la hora en que lo relevaron.
        partidos = [fecha_de[a.jornada_id].isoformat() for a in
                    db.query(m.AsignacionPersonal)
                    .filter(m.AsignacionPersonal.jornada_id.in_(ids),
                            m.AsignacionPersonal.persona_id == r.sale_persona_id,
                            m.AsignacionPersonal.relevado_por_id == r.entra_persona_id,
                            m.AsignacionPersonal.relevado_en.isnot(None)).all()]
        salida.append({
            "desde": desde.isoformat() if desde else None,
            "hasta": (hasta or desde).isoformat() if desde else None,
            "fecha": desde.isoformat() if desde else None,
            "dias": r.jornadas_afectadas,
            "sale": sale.nombre if sale else None,
            "entra": entra.nombre if entra else None,
            "motivo": r.motivo_tipo.value if r.motivo_tipo else None,
            "nota": r.motivo,
            "jornadas_partidas": sorted(partidos)})

    return sorted(salida, key=lambda c: c["desde"] or "")


def jornadas_del_mes(contrato: m.ContratoImplantado) -> list:
    """Las jornadas vivas del mes de este contrato, en orden.

    El implantado usa el mismo equipo mes tras mes, asi que las
    jornadas del equipo son las de todos sus meses. El resumen para
    facturar las contaba todas y, en cuanto se abria el mes que sigue,
    el de cada mes sumaba los dos: se habria cobrado doble. El corte y
    el resumen salen ahora de esta lista, que es la unica forma de que
    cuadren.
    """
    equipo = contrato.servicio.equipos[0] if contrato.servicio.equipos else None
    return sorted(
        [j for j in (equipo.jornadas if equipo else [])
         if j.fecha.year == contrato.anio and j.fecha.month == contrato.mes
         and j.estatus != m.EstatusJornada.CANCELADA],
        key=lambda j: j.fecha)


def base_del_mensual(db: Session, contrato: m.ContratoImplantado) -> int | None:
    """Cuantos dias cubre el precio fijo de este mes, si va con las
    modalidades de la propuesta (seccion 115): los de sus dias de
    servicio de hoy --22, 26 o 30; el 12x36, 30--. None: el mes se cobra
    por dia, o es el precio fijo de antes, con todo incluido."""
    if (contrato.esquema != m.EsquemaCotizacionImplantado.MES_COMPLETO
            or not contrato.dias_del_mensual):
        return None
    if turno_del_servicio(db, contrato.servicio_id) == TURNO_12X36:
        return DIAS_DEL_MENSUAL[m.DiasServicio.TODOS]
    return DIAS_DEL_MENSUAL.get(contrato.dias_servicio,
                                DIAS_DEL_MENSUAL[m.DiasServicio.LUNES_VIERNES])


def cobro_del_mensual(db: Session, contrato: m.ContratoImplantado,
                      trabajados: list[date],
                      hasta: date | None = None) -> dict | None:
    """Como se cobra el mes en las modalidades de la propuesta (seccion
    115), con los dias que se trabajaron:

    * el precio fijo del mes, se trabajen 21 o 23 dias de la modalidad;
    * el primer mes que empieza a medio mes --despues de algun dia de
      su modalidad (`empieza_a_medio_mes`)--, por dia de servicio: el
      mensual entre los dias de la modalidad, por los dias trabajados
      dentro de ella;
    * igual el mes en que el implantado se cancela a la mitad (seccion
      117, decision 4): `hasta` es el dia de la cancelacion
      (`termina_a_medio_mes`);
    * el dia trabajado fuera de la modalidad --el sabado o el domingo de
      lunes a viernes, el domingo de lunes a sabado--, aparte, al precio
      del dia adicional. El 12x36 y el mes completo no tienen.

    None si el mes no va asi (`base_del_mensual`). El precio por dia y
    lo que da por los dias van redondeados al centavo como los lee la
    factura: precio por cantidad.
    """
    base = base_del_mensual(db, contrato)
    if base is None:
        return None
    es_12x36 = turno_del_servicio(db, contrato.servicio_id) == TURNO_12X36
    tope = 7 if es_12x36 else hasta_donde(contrato.dias_servicio)
    dentro = sorted(d for d in trabajados if d.weekday() < tope)
    fuera = sorted(d for d in trabajados if d.weekday() >= tope)
    centavo = Decimal("0.01")
    mensual = Decimal(str(contrato.precio_mes_completo or 0))
    precio_dia = (mensual / base).quantize(centavo, rounding=ROUND_HALF_UP)
    turno = TURNO_12X36 if es_12x36 else TURNO_NATURAL
    empieza = empieza_a_medio_mes(contrato.anio, contrato.mes,
                                  contrato.dias_servicio, contrato.desde_dia,
                                  turno)
    termina = termina_a_medio_mes(contrato.anio, contrato.mes,
                                  contrato.dias_servicio, hasta, turno)
    # El mes a medias que trabajo tantos dias como cubre el mensual se
    # cobra el mensual (seccion 127, hallazgo r2-04): el que empieza el
    # dia 2 de un mes de 23 habiles trabaja 22, y 22 por el precio por
    # dia redondeado daba $118,600.02 --o $99,999.90-- en vez del mensual.
    parcial = (empieza or termina) and len(dentro) < base
    contratados = None
    if parcial:
        contratados = len([d for d in dias_del_mes(
            contrato.anio, contrato.mes, contrato.dias_servicio,
            contrato.desde_dia, turno) if not termina or d <= hasta])
        importe_mes = precio_dia * len(dentro)
        contratado = precio_dia * contratados
    else:
        importe_mes = contratado = mensual
    adicional = Decimal(str(contrato.precio_dia_adicional or 0))
    return {
        "base": base, "parcial": parcial, "desde_dia": contrato.desde_dia,
        # Si el primer mes empezo a la mitad, y el dia en que se cancelo
        # si termino a la mitad.
        "empieza": empieza,
        "hasta_dia": hasta.day if termina else None,
        "dentro": len(dentro), "contratados": contratados,
        "fuera": [d.isoformat() for d in fuera],
        "precio_dia": precio_dia, "importe_mes": importe_mes,
        "contratado": contratado,
        "precio_dia_adicional": adicional,
        "importe_adicionales": adicional * len(fuera),
    }


def cierre_del_mes(db: Session, contrato_id: int) -> dict:
    """Que dias se trabajaron y quien los trabajo.

    Es el papel del corte: de un lado lo que se le cobra al cliente
    —dias de actividad, con su fecha— y del otro lo que se le paga a
    cada quien —cuantos dias cubrio, base y adicionales—. Las dos listas
    salen de las mismas jornadas, que es la unica forma de que cuadren.

    Un dia cuenta como trabajado si tuvo gente asignada y no se cancelo.
    El dia que quedo abierto y nadie cubrio no se cobra ni se paga: no
    hubo servicio.
    """
    contrato = db.get(m.ContratoImplantado, contrato_id)
    if not contrato:
        raise HTTPException(404, f"No existe el contrato {contrato_id}")

    jornadas = jornadas_del_mes(contrato)

    # Con que rol fue cada quien. Se lee de las jornadas y no de la
    # plantilla porque el relevo que cubrio el sabado pudo ir con otro.
    rol_de = {}
    for jornada in jornadas:
        for a in jornada.personal:
            if a.rol and a.persona_id not in rol_de:
                rol_de[a.persona_id] = a.rol.nombre

    dias, por_persona, sin_cubrir = [], {}, []
    for jornada in jornadas:
        quienes = [a.persona for a in jornada.personal if a.persona]
        if not quienes:
            sin_cubrir.append(jornada.fecha.isoformat())
            continue

        dias.append({
            "fecha": jornada.fecha.isoformat(),
            "adicional": jornada.es_dia_adicional,
            "estatus": jornada.estatus.value,
            "personal": [p.nombre for p in quienes],
            "unidades": [a.vehiculo.placa for a in jornada.vehiculos
                         if a.vehiculo],
        })

        for persona in quienes:
            ficha = por_persona.setdefault(persona.id, {
                "persona_id": persona.id, "nombre": persona.nombre,
                "rol": rol_de.get(persona.id),
                "del_equipo": any(p.persona_id == persona.id
                                  for p in contrato.plantilla),
                "dias_base": 0, "dias_adicionales": 0, "fechas": [],
            })
            if jornada.es_dia_adicional:
                ficha["dias_adicionales"] += 1
            else:
                ficha["dias_base"] += 1
            ficha["fechas"].append(jornada.fecha.isoformat())

    gente = sorted(por_persona.values(),
                   key=lambda x: (not x["del_equipo"], x["nombre"]))
    for ficha in gente:
        ficha["dias"] = ficha["dias_base"] + ficha["dias_adicionales"]

    base = [d for d in dias if not d["adicional"]]
    adicionales = [d for d in dias if d["adicional"]]

    # Los viaticos del mes, persona por persona. El cierre de viaticos
    # del implantado es mensual como el de la operacion: se cierra lo de
    # septiembre con septiembre, y lo que entra en octubre es otro corte.
    dinero = viaticos_del_mes(db, [j.id for j in jornadas])
    for ficha in gente:
        ficha["viaticos"] = dinero["por_persona"].get(
            ficha["persona_id"], VIATICOS_EN_CERO.copy())

    return {
        "servicio": contrato.servicio.folio,
        "periodo": f"{contrato.mes:02d}/{contrato.anio}",
        "cliente": {
            "dias_de_actividad": len(dias),
            "base": len(base),
            "adicionales": len(adicionales),
            "fechas_adicionales": [d["fecha"] for d in adicionales],
        },
        "viaticos": dinero["total"],
        "personal": gente,
        # Lo que quedo abierto y nadie cubrio: ni se cobra ni se paga,
        # pero tiene que verse, porque es un dia que el cliente pidio.
        "dias_sin_cubrir": sin_cubrir,
        "dias": dias,
    }


def resumen_mensual(db: Session, contrato_id: int) -> dict:
    """Lo que se factura del mes y los movimientos de personal."""
    contrato = db.get(m.ContratoImplantado, contrato_id)
    if not contrato:
        raise HTTPException(404, f"No existe el contrato {contrato_id}")

    # Solo las del mes, las mismas del corte (ver `jornadas_del_mes`).
    vivas = jornadas_del_mes(contrato)
    base = [j for j in vivas if not j.es_dia_adicional]
    adicionales = [j for j in vivas if j.es_dia_adicional]

    # Las modalidades de la propuesta (seccion 115): el precio fijo, o
    # por dia el primer mes a medias --y el que se cancelo a medias,
    # seccion 117--, y aparte los dias fuera de ella.
    from app.cierre_mes import dia_de_la_cancelacion
    cobro = cobro_del_mensual(db, contrato,
                              [j.fecha for j in vivas if j.personal],
                              hasta=dia_de_la_cancelacion(db, contrato))
    if cobro is not None:
        desglose = {"mes_completo": cobro["importe_mes"]}
        if cobro["fuera"]:
            desglose["dias_adicionales"] = cobro["importe_adicionales"]
        total = sum(desglose.values(), Decimal("0"))
        fuera = set(cobro["fuera"])
        adicionales = [j for j in vivas if j.fecha.isoformat() in fuera]
        base = [j for j in vivas if j.fecha.isoformat() not in fuera]
    elif contrato.esquema == m.EsquemaCotizacionImplantado.MES_COMPLETO:
        total = Decimal(str(contrato.precio_mes_completo or 0))
        desglose = {"mes_completo": total}
    else:
        personal = Decimal(str(contrato.precio_dia_personal or 0)) * len(base)
        extra = Decimal(str(contrato.precio_dia_adicional or 0)) * len(adicionales)
        vehiculo = Decimal(str(contrato.precio_mes_vehiculo or 0))
        total = personal + extra + vehiculo
        desglose = {"personal_dias_base": personal,
                    "dias_adicionales": extra,
                    "vehiculo_mes": vehiculo}
    # Las horas extra del mes, aparte y en los dos esquemas (seccion 65):
    # las mismas cuentas que el visto bueno del mes (`cierre_mes.comparar`).
    from app import horas_extra
    horas_mes = sum(horas_extra.horas(j) for j in vivas if j.personal)
    if horas_mes:
        importe = Decimal(str(contrato.precio_hora_extra or 0)) * horas_mes
        desglose["horas_extra"] = importe
        total += importe

    reemplazos = _cambios_de_personal(db, vivas)

    return {
        "servicio": contrato.servicio.folio,
        "periodo": f"{contrato.mes:02d}/{contrato.anio}",
        "esquema": contrato.esquema.value,
        "titular": contrato.titular.nombre if contrato.titular else None,
        "vehiculo": contrato.vehiculo.placa if contrato.vehiculo else None,
        "dias": {"base": len(base), "adicionales": len(adicionales),
                 "habiles_del_mes": len(dias_del_mes(contrato.anio, contrato.mes, False)),
                 "total": len(vivas)},
        # Cuantos dias cubre el precio fijo (seccion 115); vacio, el mes
        # va por dia o con el precio fijo de antes.
        "dias_del_mensual": cobro["base"] if cobro else None,
        "horas_extra": horas_mes,
        "facturacion": {"desglose": desglose, "total": total},
        "reemplazos": reemplazos,
        "total_reemplazos": len(reemplazos),
    }


# ------------------------------------------------------- cambios con fin

# Lo planeado tiene fin y lo imprevisto no. Unas vacaciones se acaban y
# la unidad sale del taller; una baja no se sabe. Por eso el rango lleva
# un "hasta" opcional: sin el, el cambio corre de ese dia en adelante.

def cambiar_recurso(db: Session, servicio_id: int, tipo: m.TipoRecurso,
                    desde: date, hasta: date | None, entra_id: int,
                    motivo_tipo: m.MotivoCambio, hecho_por_id: int | None,
                    sale_id: int | None = None,
                    nota: str | None = None,
                    relevado_en: datetime | None = None) -> dict:
    """Cambia a una persona o una unidad en un tramo de dias.

    Un dia suelto es un rango de un dia: el consultor no tiene que
    aprender dos formas de hacer lo mismo segun si el que falta aviso con
    un mes o con una hora.

    Esta funcion ya no cambia nada por su cuenta. Traduce el tramo de
    fechas a jornadas y se lo entrega al motor de relevo, que es el mismo
    que usa el eventual. Antes tenia su propia copia de la regla y la
    copia estaba mal: mutaba la asignacion, asi que quien trabajo media
    jornada y fue relevado cobraba cero. Dos implementaciones de la misma
    regla se separan con el tiempo, y esta ya se habia separado.

    Lo que si es del implantado es el tope: un cambio sin fecha de fin
    llega al ultimo dia del mes en curso y ahi se detiene. El implantado
    reutiliza el mismo equipo mes tras mes, asi que "de aqui en adelante"
    se llevaria tambien octubre si octubre ya esta abierto, sin que nadie
    lo pida y sin que aparezca en ninguna pantalla. Si hay que extenderlo,
    se vuelve a pedir cuando octubre exista, y queda como otro movimiento
    en el historial.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    if hasta and hasta < desde:
        raise HTTPException(400, "El tramo termina antes de empezar")
    if not sale_id:
        raise HTTPException(409, {
            "mensaje": "Hay que decir quien sale.",
            "que_hacer": ("Antes se tomaba al primero de la lista del dia. "
                          "En una plantilla de tres —un coordinador y dos "
                          "agentes— eso cambiaba al que no era, y el fin de "
                          "semana, cuando la plantilla rota, cambiaba a "
                          "cualquiera."),
        })

    tope = hasta or contingencia.ultimo_dia_del_mes(desde)
    equipo = servicio.equipos[0] if servicio.equipos else None
    # Los dias ya terminados no se tocan: esos ya los trabajo quien fue.
    dias = sorted([j for j in (equipo.jornadas if equipo else [])
                   if j.estatus not in (m.EstatusJornada.CANCELADA,
                                        m.EstatusJornada.TERMINADA)
                   and j.fecha >= desde and j.fecha <= tope],
                  key=lambda j: j.fecha)
    if not dias:
        raise HTTPException(409, "No hay dias en ese tramo")

    if tipo == m.TipoRecurso.PERSONAL:
        sale = db.get(m.Persona, sale_id)
        entra = db.get(m.Persona, entra_id)
        if not sale:
            raise HTTPException(404, f"No existe la persona {sale_id}")
        if not entra:
            raise HTTPException(404, f"No existe la persona {entra_id}")
        hecho = contingencia.reemplazar_personal(
            db, desde_jornada_id=dias[0].id,
            sale_persona_id=sale_id, entra_persona_id=entra_id,
            motivo=(nota or motivo_tipo.value)[:600],
            hecho_por_id=hecho_por_id, motivo_tipo=motivo_tipo,
            hasta_jornada_id=dias[-1].id, relevado_en=relevado_en)
        sale_nombre, entra_nombre = sale.nombre, entra.nombre
    else:
        sale = db.get(m.Vehiculo, sale_id)
        entra = db.get(m.Vehiculo, entra_id)
        if not sale:
            raise HTTPException(404, f"No existe la unidad {sale_id}")
        if not entra:
            raise HTTPException(404, f"No existe la unidad {entra_id}")
        hecho = contingencia.reemplazar_vehiculo(
            db, desde_jornada_id=dias[0].id,
            sale_vehiculo_id=sale_id, entra_vehiculo_id=entra_id,
            motivo=(nota or motivo_tipo.value)[:600],
            hecho_por_id=hecho_por_id, motivo_tipo=motivo_tipo,
            hasta_jornada_id=dias[-1].id, relevado_en=relevado_en)
        sale_nombre, entra_nombre = sale.placa, entra.placa

    # No se cierra aqui: el router es quien guarda, igual que en
    # contingencia. Asi la vista previa puede correr el cambio de verdad
    # y deshacerlo, en vez de tener una segunda cuenta que calcule "lo
    # que pasaria" y acabe separandose de la primera.
    db.flush()

    fechas = hecho["jornadas_afectadas"]
    return {
        "resultado": "cambiado", "tipo": tipo.value,
        "reemplazo_id": hecho["reemplazo_id"],
        "dias_cambiados": len(fechas),
        "desde": fechas[0] if fechas else dias[0].fecha.isoformat(),
        "hasta": fechas[-1] if fechas else dias[-1].fecha.isoformat(),
        # Si el consultor no puso fin, el tope lo puso el sistema. La
        # pantalla lo dice en voz alta: "hasta el 30; para octubre hay
        # que volver a pedirlo".
        "tope_automatico": hasta is None,
        "sale": sale_nombre, "entra": entra_nombre,
        "motivo": motivo_tipo.value,
        # Con los nombres del motor y no con unos propios: la pantalla
        # que pinta esto es la misma para eventual y para implantado.
        "jornadas_afectadas": fechas,
        # Los dias que se partieron: la prueba de que quien trabajo media
        # jornada va a cobrar media jornada.
        "jornadas_partidas": hecho["jornadas_partidas"],
        "jornadas_con_choque": hecho["jornadas_con_choque"],
        "relevado_en": hecho["relevado_en"],
        "hora_propuesta": hecho.get("hora_propuesta"),
        "viaticos": hecho["viaticos"],
        "revision_pendiente": hecho.get("revision_pendiente"),
        "aviso": _aviso_del_dinero(hecho["viaticos"], sale_nombre,
                                   entra_nombre),
    }


def _aviso_del_dinero(viaticos: dict | None, sale: str, entra: str) -> str | None:
    """Lo que el consultor tiene que saber del dinero, en una frase.

    Antes esto era un letrero que le pedia hacer a mano lo que ahora el
    sistema ya hizo: el viatico depositado paso a comprobacion con su
    plazo y el que no se habia transferido se cancelo. Lo que sigue
    siendo suyo es pedir el del que entra, porque el sistema no gasta
    solo.
    """
    if not viaticos:
        return None
    partes = []
    if viaticos.get("a_comprobar"):
        dias = ", ".join(v["fecha"] for v in viaticos["a_comprobar"])
        partes.append(f"{sale} ya tenia dinero depositado ({dias}): quedo en "
                      f"comprobacion con su plazo.")
    if viaticos.get("cancelados"):
        partes.append(f"Se cancelaron {len(viaticos['cancelados'])} viatico(s) "
                      f"de {sale} que todavia no se transferian.")
    if viaticos.get("propuestos"):
        # El motor manda el monto como cadena, en Decimal (seccion 101).
        total = sum((Decimal(str(v["monto"])) for v in viaticos["propuestos"]),
                    Decimal("0"))
        partes.append(f"A {entra} le tocarian ${total:,.2f} por tabulador: "
                      f"hay que solicitarlos.")
    return " ".join(partes) or None


# ------------------------------------------------------------- plantilla

# La combinacion la pide el cliente —un conductor, un agente, dos de cada
# uno— y se repite igual todos los dias del mes. Dos reglas que no se
# pueden romper, porque romperlas manda a la calle un servicio que no
# existe.

# El rol con el que suele ir quien maneja. Se usa solo para elegir a
# quien se apunta como titular del mes: el que se lee de un vistazo en la
# cartera. No limita nada.
ROL_CONDUCTOR = "conductor_seguridad"


def _ciudad(db: Session, plaza_id: int | None) -> str:
    plaza = db.get(m.Plaza, plaza_id) if plaza_id else None
    return plaza.nombre if plaza else "otra ciudad"


def _que_pueda_cubrir(db: Session, persona_id: int) -> m.Persona:
    """La persona que cubre un dia del implantado: que exista y que no
    sea freelance --sus costos son solo de eventuales (seccion 111,
    decision 10 de Salvador)--."""
    persona = db.get(m.Persona, persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {persona_id}")
    if persona.es_freelance:
        from app import freelance
        raise HTTPException(409, freelance.NO_EN_IMPLANTADO)
    return persona


def por_que_no_va(db: Session, persona: m.Persona,
                  plaza_id: int | None) -> str | None:
    """Por que esa persona ya no puede ir a la plantilla, o None.

    Lo mismo que filtra la consola al armar el mes (seccion 74 y la
    ciudad del servicio), dicho tambien del lado del servidor y cada vez
    que un mes se abre: alguien dado de baja en Odoo, de oficina o de
    otra ciudad no se pone en veintidos dias sin que nadie lo vea
    (seccion 101).
    """
    if not persona.activo:
        return f"{persona.nombre} ya no está activo"
    if persona.oficina:
        return f"{persona.nombre} es personal de oficina: no va a la calle"
    # El freelance no se ofrece en implantados (seccion 111, decision 10).
    if persona.es_freelance:
        return (f"{persona.nombre} es freelance: el freelance va solo en "
                "servicios eventuales")
    if plaza_id and persona.plaza_id != plaza_id:
        return (f"{persona.nombre} es de {_ciudad(db, persona.plaza_id)}, no "
                f"de {_ciudad(db, plaza_id)}")
    return None


def por_que_no_sale(db: Session, unidad: m.Vehiculo, plaza_id: int | None,
                    bloqueos, dia: date | None) -> str | None:
    """Por que esa unidad no puede salir ese dia, o None: de baja, de
    renta, de otra ciudad o en el taller (seccion 101)."""
    if not unidad.activo:
        return f"La unidad {unidad.placa} está dada de baja"
    if unidad.rentado:
        return f"La unidad {unidad.placa} es de renta: no es de la flota fija"
    # La de Brasil llega de Odoo sin Ubicacion (seccion 118): mientras no
    # la tenga no es de ninguna ciudad, y el implantado es de una.
    if plaza_id and unidad.plaza_id is None:
        return (f"La unidad {unidad.placa} todavía no tiene ciudad: se le "
                "pone en Odoo, en su Ubicación")
    if plaza_id and unidad.plaza_id != plaza_id:
        return (f"La unidad {unidad.placa} es de {_ciudad(db, unidad.plaza_id)}, "
                f"no de {_ciudad(db, plaza_id)}")
    if dia and en_taller(bloqueos, dia):
        fila = next(b for b in bloqueos if b.cubre(dia))
        hasta = (f"hasta el {fila.hasta.isoformat()}" if fila.hasta
                 else "sin fecha de salida")
        return (f"La unidad {unidad.placa} está en el taller desde el "
                f"{fila.desde.isoformat()}, {hasta}")
    return None


def validar_plantilla(db: Session, personal: list, unidades: list,
                      turno: str = TURNO_NATURAL,
                      plaza_id: int | None = None,
                      primer_dia: date | None = None) -> None:
    """Cada quien con su rol, y toda unidad con alguien a bordo.

    Ya no se pregunta que es cada persona: el personal de seguridad es
    general y el rol lo decide el consultor. Lo que si se exige es que
    lo diga, porque de ese rol salen el precio al cliente y la comision
    que se le paga, y sin el la jornada no se puede cobrar ni pagar.

    Y que puedan ir (seccion 101): gente activa, de seguridad y de la
    ciudad del servicio; unidades de la flota fija de esa ciudad que no
    esten en el taller el primer dia del mes. La consola ya lo filtraba;
    el servidor aceptaba por la API a un monitorista de oficina o una
    unidad de Guadalajara en un implantado de la capital.

    `personal` son cuaternas (persona_id, vehiculo_id, rol_id, empieza) y
    `unidades` los ids de las unidades del mes.
    """
    if not personal:
        raise HTTPException(409, "El implantado necesita por lo menos una "
                                 "persona en la plantilla")

    if turno == TURNO_12X36:
        _validar_12x36(personal, unidades)

    gente = {}
    for persona_id, vehiculo_id, rol_id, _empieza in personal:
        persona = db.get(m.Persona, persona_id)
        if not persona:
            raise HTTPException(404, f"No existe la persona {persona_id}")
        motivo = por_que_no_va(db, persona, plaza_id)
        if motivo:
            raise HTTPException(409, {
                "mensaje": motivo,
                "que_hacer": "La plantilla del mes se arma con personal de "
                             "seguridad activo de la ciudad del servicio.",
            })
        if not rol_id:
            raise HTTPException(409, {
                "mensaje": f"Falta decir con que rol va {persona.nombre}",
                "que_hacer": "Del rol salen el precio al cliente y la "
                             "comision que se le paga. Sin el, esa jornada "
                             "no se puede cobrar ni pagar.",
            })
        if not db.get(m.PerfilPersonal, rol_id):
            raise HTTPException(404, f"No existe el rol {rol_id}")
        gente[persona_id] = (persona, vehiculo_id, rol_id)

    bloqueos = taller_de(db, list(unidades))
    for vehiculo_id in unidades:
        unidad = db.get(m.Vehiculo, vehiculo_id)
        if not unidad:
            raise HTTPException(404, f"No existe la unidad {vehiculo_id}")
        motivo = por_que_no_sale(db, unidad, plaza_id,
                                 bloqueos.get(vehiculo_id), primer_dia)
        if motivo:
            raise HTTPException(409, {
                "mensaje": motivo,
                "que_hacer": "La unidad del mes es una de la flota fija de "
                             "la ciudad del servicio, disponible desde el "
                             "primer día.",
            })
        if not [p for p, v, _ in gente.values() if v == vehiculo_id]:
            raise HTTPException(409, {
                "mensaje": f"La unidad {unidad.placa} no tiene a nadie "
                           "asignado",
                "que_hacer": "Asigne quien la lleva. Una unidad sin gente "
                             "no es una unidad, es un coche estacionado.",
            })

    sobran = {v for _, v, _ in gente.values() if v} - set(unidades)
    if sobran:
        raise HTTPException(409, "Hay gente asignada a una unidad que no "
                                 "esta en la plantilla del mes")


def _validar_12x36(personal: list, unidades: list) -> None:
    """Las reglas de la escala, que no son preferencias de armado.

    Dos personas, de la misma categoria, una sola unidad, y dicho cual
    empieza. Con una sola persona no hay escala: hay alguien trabajando
    treinta dias seguidos. Con tres no se sabe quien va. Con categorias
    distintas, el precio al cliente y la comision cambiarian segun el
    dia que caiga.
    """
    if len(personal) != 2:
        raise HTTPException(409, {
            "mensaje": f"El 12 x 36 se cubre con dos personas, y hay "
                       f"{len(personal)}.",
            "que_hacer": "Son dos que se alternan dia con dia. Con una sola "
                         "no hay escala: hay alguien trabajando el mes "
                         "seguido.",
        })
    roles = {rol_id for _p, _v, rol_id, _e in personal}
    if len(roles) > 1:
        raise HTTPException(409, {
            "mensaje": "Las dos personas del 12 x 36 tienen que ser de la "
                       "misma categoria.",
            "que_hacer": "De la categoria salen el precio al cliente y la "
                         "comision. Con dos distintas, lo que se cobra y lo "
                         "que se paga cambiarian segun el dia que caiga.",
        })
    if len(unidades) > 1:
        raise HTTPException(409, {
            "mensaje": f"El 12 x 36 lleva una sola unidad, y hay "
                       f"{len(unidades)}.",
            "que_hacer": "La unidad corre el mes entero y la maneja quien "
                         "trabaja ese dia. Lo que rota es la gente.",
        })
    cuantas = sum(1 for _p, _v, _r, empieza in personal if empieza)
    if cuantas != 1:
        raise HTTPException(409, {
            "mensaje": "Falta decir cual de las dos empieza.",
            "que_hacer": "De ahi sale quien trabaja el primer dia, y despues "
                         "se alternan solas. El orden en que se capturaron no "
                         "cuenta: eso es un accidente.",
        })


def guardar_plantilla(db: Session, contrato: m.ContratoImplantado,
                      personal: list, unidades: list) -> None:
    """Reescribe la plantilla del mes, ya validada.

    `personal` son cuaternas (persona_id, vehiculo_id, rol_id, empieza).
    """
    turno = turno_del_servicio(db, contrato.servicio_id)
    dias = dias_del_mes(contrato.anio, contrato.mes, contrato.dias_servicio,
                        contrato.desde_dia, turno)
    validar_plantilla(db, personal, unidades, turno,
                      plaza_id=contrato.servicio.plaza_id,
                      primer_dia=dias[0] if dias else None)

    for fila in list(contrato.plantilla):
        db.delete(fila)
    for fila in list(contrato.unidades):
        db.delete(fila)
    db.flush()

    for persona_id, vehiculo_id, rol_id, empieza in personal:
        db.add(m.PersonaImplantado(contrato_id=contrato.id,
                                   persona_id=persona_id,
                                   rol_id=rol_id,
                                   vehiculo_id=vehiculo_id,
                                   empieza=bool(empieza)))
    for vehiculo_id in unidades:
        db.add(m.UnidadImplantado(contrato_id=contrato.id,
                                  vehiculo_id=vehiculo_id))

    # Se dejan apuntados el primer conductor y la primera unidad: son lo
    # que se lee de un vistazo en la cartera y en el resumen del mes. Si
    # nadie va de conductor —un agente solo que maneja—, el primero.
    roles = {r.id: r.codigo for r in db.query(m.PerfilPersonal).all()}
    conduce = next((pid for pid, _, rid, _e in personal
                    if roles.get(rid) == ROL_CONDUCTOR), None)
    contrato.titular_id = conduce or (personal[0][0] if personal else None)
    contrato.vehiculo_id = unidades[0] if unidades else None
    db.flush()
    # La plantilla se guardo fila por fila: la que el contrato tenga en
    # memoria sigue siendo la de antes, y rehacer los dias con ella les
    # ponia la plantilla vieja --la unidad que se acababa de quitar
    # (seccion 101)--.
    db.expire(contrato, ["plantilla", "unidades"])


def pareja_del_turno(contrato: m.ContratoImplantado) -> list:
    """Las dos personas del 12x36, en orden: primero la que empieza."""
    return sorted(contrato.plantilla, key=lambda f: (not f.empieza, f.id))


def arranque_del_mes(db: Session, contrato: m.ContratoImplantado,
                     pareja: list, inicio: date) -> int:
    """Con cual de las dos abre el mes.

    Si el dia anterior existe y esta pegado --el 31 de marzo contra el 1
    de abril-- abre la que NO trabajo ese dia. Si no, esa persona haria
    dos dias seguidos, que es justo lo que la escala prohibe y la regla
    que manda sobre todo lo demas.

    Sin dia anterior pegado --un servicio nuevo, o un mes que arranca
    despues de una pausa-- abre la que el consultor marco.
    """
    equipo = contrato.servicio.equipos[0] if contrato.servicio.equipos else None
    if not equipo or len(pareja) != 2:
        return 0
    ayer = (db.query(m.Jornada)
            .filter(m.Jornada.equipo_id == equipo.id,
                    m.Jornada.fecha == inicio - timedelta(days=1))
            .first())
    if not ayer:
        return 0
    trabajaron = {a.persona_id for a in ayer.personal}
    return 1 if pareja[0].persona_id in trabajaron else 0


def de_quien_es(pareja: list, arranque: int, inicio: date, dia: date):
    """De quien es ese dia.

    Se calcula, no se guarda: dos personas alternandose son una paridad,
    y una paridad no necesita una tabla que mantener en pie. El dia que
    alguien mire el calendario y el dia que se rehagan los dias tienen
    que dar la misma respuesta, y asi la dan por construccion.
    """
    if not pareja:
        return None
    if len(pareja) == 1:
        return pareja[0]
    return pareja[(arranque + (dia - inicio).days) % 2]


def plantilla_fuera(db: Session, contrato: m.ContratoImplantado,
                    dias: list) -> dict:
    """Lo que de la plantilla del mes ya no puede ir a sus dias.

    {"personas": {persona_id: motivo}, "unidades": {vehiculo_id: {"motivo",
    "dias"}}}; `dias` es None cuando la unidad no sale ningun dia (de
    baja, de renta, de otra ciudad) y el conjunto de fechas cuando esta
    en el taller solo parte del mes.

    Es la revalidacion al abrir cada mes (seccion 101): la plantilla que
    fue buena en septiembre puede traer en octubre al conductor que Odoo
    dio de baja el 12 o la unidad que entro al taller sin fecha. El mes
    se abre igual --el reloj no se detiene por eso-- pero esa posicion
    no se pone en los dias: el dia queda por cubrir, con su alerta, y
    el consultor la resuelve.
    """
    plaza_id = contrato.servicio.plaza_id
    personas = {}
    # Los contratos de antes de la plantilla operan con su titular.
    gente = ([f.persona for f in contrato.plantilla] if contrato.plantilla
             else [contrato.titular])
    for persona in gente:
        if persona is None:
            continue
        motivo = por_que_no_va(db, persona, plaza_id)
        if motivo:
            personas[persona.id] = motivo
    ids = ({f.vehiculo_id for f in contrato.unidades}
           | {f.vehiculo_id for f in contrato.plantilla if f.vehiculo_id})
    if contrato.vehiculo_id:
        ids.add(contrato.vehiculo_id)
    bloqueos = taller_de(db, list(ids))
    unidades = {}
    for vehiculo_id in ids:
        unidad = db.get(m.Vehiculo, vehiculo_id)
        if unidad is None:
            continue
        motivo = por_que_no_sale(db, unidad, plaza_id, None, None)
        if motivo:
            unidades[vehiculo_id] = {"motivo": motivo, "dias": None}
            continue
        en = {d for d in dias if en_taller(bloqueos.get(vehiculo_id), d)}
        if en:
            unidades[vehiculo_id] = {
                "motivo": por_que_no_sale(db, unidad, plaza_id,
                                          bloqueos.get(vehiculo_id), min(en)),
                "dias": en}
    return {"personas": personas, "unidades": unidades}


def _unidad_fuera(fuera: dict | None, vehiculo_id: int | None,
                  dia: date) -> str | None:
    """Por que esa unidad no sale ese dia, segun `plantilla_fuera`."""
    if not fuera or not vehiculo_id:
        return None
    suya = fuera["unidades"].get(vehiculo_id)
    if not suya:
        return None
    if suya["dias"] is None or dia in suya["dias"]:
        return suya["motivo"]
    return None


def _avisar_lo_que_falta(db: Session, jornada: m.Jornada,
                         faltas: list) -> None:
    """Una alerta por cada posicion que no se pudo poner en el dia, como
    la que deja la baja de Odoo (secciones 51 y 52): la central la ve y
    la revision del mes la cuenta. La misma no se repite."""
    for tipo, persona_id, vehiculo_id, motivo in faltas:
        mensaje = (f"{motivo}: el día quedó sin esa posición, hay que "
                   "cubrirla.")[:400]
        repetida = (db.query(m.Alerta)
                    .filter_by(jornada_id=jornada.id, tipo=tipo,
                               mensaje=mensaje, atendida=False).first())
        if repetida:
            continue
        db.add(m.Alerta(jornada_id=jornada.id, tipo=tipo,
                        persona_id=persona_id, vehiculo_id=vehiculo_id,
                        mensaje=mensaje))


def _asignar_turno(db: Session, jornada: m.Jornada,
                   contrato: m.ContratoImplantado, fila,
                   fuera: dict | None = None) -> list:
    """El dia de una sola persona, con la unidad del mes.

    La unidad no rota: es una sola por turno --es regla-- y corre el mes
    entero. Lo que rota es quien la maneja. Devuelve lo que no se pudo
    poner (seccion 101).
    """
    faltas = []
    unidad = (contrato.unidades[0].vehiculo_id if contrato.unidades
              else contrato.vehiculo_id)
    motivo_unidad = _unidad_fuera(fuera, unidad, jornada.fecha)
    if motivo_unidad:
        faltas.append((m.TipoAlerta.VEHICULO_SIN_ASIGNAR, None, unidad,
                       motivo_unidad))
        unidad = None
    if fila:
        motivo = (fuera or {}).get("personas", {}).get(fila.persona_id)
        if motivo:
            faltas.append((m.TipoAlerta.PERSONAL_DE_BAJA, fila.persona_id,
                           None, motivo))
        else:
            db.add(m.AsignacionPersonal(
                jornada_id=jornada.id, persona_id=fila.persona_id,
                rol_id=fila.rol_id,
                vehiculo_id=(None if motivo_unidad
                             else fila.vehiculo_id or unidad)))
    if unidad:
        db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                    vehiculo_id=unidad))
    return faltas


def _asignar_del_contrato(db: Session, jornada: m.Jornada,
                          contrato: m.ContratoImplantado,
                          fuera: dict | None = None) -> list:
    """Le pone al dia la plantilla completa del mes.

    Con el abordo puesto: quien maneja que unidad ya se decidio una vez
    al armar el mes, y repetirlo dia por dia era la parte del trabajo que
    de verdad sobraba. Lo que ya no puede ir --`fuera`-- no se pone, y se
    devuelve para avisarlo (seccion 101).
    """
    faltas = []
    personas_fuera = (fuera or {}).get("personas", {})
    if contrato.plantilla:
        for fila in contrato.plantilla:
            motivo = personas_fuera.get(fila.persona_id)
            if motivo:
                faltas.append((m.TipoAlerta.PERSONAL_DE_BAJA,
                               fila.persona_id, None, motivo))
                continue
            db.add(m.AsignacionPersonal(
                jornada_id=jornada.id, persona_id=fila.persona_id,
                rol_id=fila.rol_id,
                vehiculo_id=(None if _unidad_fuera(fuera, fila.vehiculo_id,
                                                   jornada.fecha)
                             else fila.vehiculo_id)))
        for fila in contrato.unidades:
            motivo = _unidad_fuera(fuera, fila.vehiculo_id, jornada.fecha)
            if motivo:
                faltas.append((m.TipoAlerta.VEHICULO_SIN_ASIGNAR, None,
                               fila.vehiculo_id, motivo))
                continue
            db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                        vehiculo_id=fila.vehiculo_id))
        return faltas

    # Contratos de antes de la plantilla: siguen operando con su titular.
    if contrato.titular_id:
        motivo = personas_fuera.get(contrato.titular_id)
        if motivo:
            faltas.append((m.TipoAlerta.PERSONAL_DE_BAJA, contrato.titular_id,
                           None, motivo))
        else:
            db.add(m.AsignacionPersonal(jornada_id=jornada.id,
                                        persona_id=contrato.titular_id))
    if contrato.vehiculo_id:
        motivo = _unidad_fuera(fuera, contrato.vehiculo_id, jornada.fecha)
        if motivo:
            faltas.append((m.TipoAlerta.VEHICULO_SIN_ASIGNAR, None,
                           contrato.vehiculo_id, motivo))
        else:
            db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                        vehiculo_id=contrato.vehiculo_id))
    return faltas


def rehacer_dias(db: Session, contrato: m.ContratoImplantado,
                 plantilla_anterior: set | None = None) -> int:
    """Vuelve a poner la plantilla en los dias que todavia no pasaron.

    Lo ya operado no se toca: si alguien cubrio el martes, ese martes se
    queda como quedo. Reescribirlo seria borrar lo que de verdad paso, y
    de ahi salen la nomina y la comprobacion de viaticos.

    Solo los dias que `generar_mes` habria llenado con la plantilla: en
    natural, los de entre semana. El fin de semana nace vacio --quien
    trabajo de lunes a viernes descansa-- o lo cubrio alguien a mano
    desde la ficha, y rehacerlo le ponia la plantilla fija a todos los
    sabados y borraba al relevo (seccion 101). Tampoco se pisa un dia
    entre semana donde ya va alguien que no era de la plantilla
    anterior: eso lo decidio el consultor. `plantilla_anterior` son las
    personas de la plantilla que se acaba de reemplazar.
    """
    equipo = (contrato.servicio.equipos[0]
              if contrato.servicio.equipos else None)
    if not equipo:
        return 0

    # El hoy del pais del servicio: de esto depende que dias se dan por
    # pasados, y un dia de error reescribe un dia que ya se opero.
    hoy = reloj.ahora_del_servicio(db, contrato.servicio).date()
    ultimo = calendar.monthrange(contrato.anio, contrato.mes)[1]
    primero = date(contrato.anio, contrato.mes, 1)
    fin = date(contrato.anio, contrato.mes, ultimo)

    # En 12x36 no se le pone la plantilla entera a cada dia: cada dia es
    # de una sola de las dos, y de cual sale de la misma cuenta que uso
    # el calendario al generarse. Se resuelve una vez, no por dia.
    turno = turno_del_servicio(db, contrato.servicio_id)
    es_12x36 = turno == TURNO_12X36
    pareja = pareja_del_turno(contrato) if es_12x36 else []
    dias = dias_del_mes(contrato.anio, contrato.mes, contrato.dias_servicio,
                        contrato.desde_dia, turno)
    inicio = dias[0] if dias else primero
    arranque = (arranque_del_mes(db, contrato, pareja, inicio)
                if es_12x36 else 0)
    fuera = plantilla_fuera(db, contrato, dias)
    anterior = (set(plantilla_anterior) if plantilla_anterior is not None
                else None)

    rehechos = 0
    for jornada in equipo.jornadas:
        if not (primero <= jornada.fecha <= fin):
            continue
        if jornada.fecha <= hoy:
            continue           # lo que ya paso se queda como quedo
        # Un dia que su gente ya confirmo cuenta igual que uno planeado:
        # todavia no arranca y lo que se rehace es su plantilla. Vuelve a
        # planeada porque la gente que entra no ha confirmado nada.
        if jornada.estatus not in (m.EstatusJornada.PLANEADA,
                                   m.EstatusJornada.CONFIRMADA):
            continue
        # Un dia con cambio ya fue decidido a mano: no se pisa.
        if any(a.reemplaza_a_id for a in jornada.personal):
            continue
        if not es_12x36:
            # El fin de semana no es de la plantilla fija (seccion 101).
            if jornada.fecha.weekday() >= 5:
                continue
            # Ni el dia donde ya va alguien que no era de la plantilla
            # que se reemplaza: un relevo puesto a mano.
            if anterior is not None and any(a.persona_id not in anterior
                                            for a in jornada.personal):
                continue

        for a in list(jornada.personal):
            db.delete(a)
        for a in list(jornada.vehiculos):
            db.delete(a)
        db.flush()
        jornada.estatus = m.EstatusJornada.PLANEADA
        if es_12x36:
            faltas = _asignar_turno(
                db, jornada, contrato,
                de_quien_es(pareja, arranque, inicio, jornada.fecha), fuera)
        else:
            faltas = _asignar_del_contrato(db, jornada, contrato, fuera)
        _avisar_lo_que_falta(db, jornada, faltas)
        rehechos += 1

    db.flush()
    return rehechos


def meses_generados_despues(db: Session, servicio_id: int,
                            anio: int, mes: int) -> list:
    """Los contratos ya generados del servicio posteriores a ese mes, en
    orden. Es a donde llega lo que se cambia hoy (seccion 105)."""
    return [c for c in (db.query(m.ContratoImplantado)
                        .filter_by(servicio_id=servicio_id, generado=True)
                        .order_by(m.ContratoImplantado.anio,
                                  m.ContratoImplantado.mes).all())
            if (c.anio, c.mes) > (anio, mes)]


def copiar_plantilla_a_meses_siguientes(db: Session,
                                        contrato: m.ContratoImplantado,
                                        personal: list,
                                        unidades: list) -> list[dict]:
    """La plantilla que se acaba de guardar en un mes, en cada mes
    posterior ya abierto (seccion 105, pantalla «Cambiar la plantilla del
    mes»): la baja del titular el 12 dejaba octubre --ya abierto-- con el
    titular dado de baja, y habia que repetir el cambio cada mes. Cada
    mes se rehace con las mismas reglas que el primero: no se tocan los
    dias operados, con cambio ni cubiertos a mano. Un mes con visto
    bueno ya no se arma. Devuelve por mes cuantos dias se rehicieron."""
    from app import cierre_mes
    hechos = []
    for siguiente in meses_generados_despues(db, contrato.servicio_id,
                                             contrato.anio, contrato.mes):
        if cierre_mes.con_visto_bueno(db, siguiente):
            continue
        anterior = {f.persona_id for f in siguiente.plantilla}
        guardar_plantilla(db, siguiente, personal, unidades)
        rehechos = rehacer_dias(db, siguiente, plantilla_anterior=anterior)
        hechos.append({"contrato_id": siguiente.id,
                       "periodo": f"{siguiente.mes:02d}/{siguiente.anio}",
                       "anio": siguiente.anio, "mes": siguiente.mes,
                       "dias_rehechos": rehechos})
    return hechos


# --------------------------------------------------------------------
# Los cambios del acuerdo aplican desde el mes siguiente
#
# Decision 14 de Salvador (29 sep): los dias de servicio, la hora del
# encuentro, los precios y las horas que se corrigen a medio mes llegan a
# los meses futuros ya abiertos, que se rehacen solos con el acuerdo
# nuevo sin tocar los dias con gente puesta a mano ni con marcas. El mes
# en curso NO se toca: se corrige a mano con las herramientas del mes. Y
# si el servicio todavia no arranca, el cambio aplica desde su primer
# mes, porque no hay nada operado.
#
# Hasta aqui (hallazgo 65) cambiar los dias de servicio no llegaba a
# ningun mes, y mover la hora con el mes siguiente ya abierto lo dejaba
# con la hora vieja: la app, la geocerca y la puntualidad del bono.
# --------------------------------------------------------------------

# Lo que viaja de mes en mes: los terminos del acuerdo que un contrato
# puede recibir de otro.
CAMPOS_DEL_ACUERDO = (
    "dias_servicio", "hora_presentacion", "esquema",
    "precio_dia_personal", "precio_dia_adicional", "precio_mes_vehiculo",
    "precio_mes_completo", "viaticos_incluidos", "gastos_mes",
    "precio_hora_extra", "horas_jornada", "horas_descanso",
)


def _periodo(anio: int, mes: int) -> str:
    return f"{mes:02d}/{anio}"


def primer_mes_a_tocar(db: Session, servicio: m.Servicio) -> tuple[int, int]:
    """(anio, mes) del primer mes al que llega un cambio del acuerdo: el
    que sigue al mes de hoy en el pais del servicio, o el primer mes del
    servicio si todavia no arranca (su hoy es anterior al primer dia de
    su primer mes: no hay nada operado)."""
    hoy = hoy_del_servicio(db, servicio)
    primero = (db.query(m.ContratoImplantado)
               .filter_by(servicio_id=servicio.id)
               .order_by(m.ContratoImplantado.anio, m.ContratoImplantado.mes)
               .first())
    if primero is not None:
        arranque = date(primero.anio, primero.mes, primero.desde_dia or 1)
        if hoy < arranque:
            return primero.anio, primero.mes
    return _siguiente_periodo(hoy.year, hoy.month)


def mes_en_curso_que_no_se_toca(db: Session, servicio: m.Servicio,
                                desde: tuple[int, int]) -> str | None:
    """La frase para la pantalla cuando el mes de hoy queda fuera del
    cambio: existe, esta generado y es anterior al primer mes tocado."""
    hoy = hoy_del_servicio(db, servicio)
    if (hoy.year, hoy.month) >= desde:
        return None
    contrato = (db.query(m.ContratoImplantado)
                .filter_by(servicio_id=servicio.id, anio=hoy.year,
                           mes=hoy.month, generado=True).first())
    if contrato is None:
        return None
    return (f"{_periodo(hoy.year, hoy.month)}: no se toca; corrígelo con "
            "las herramientas del mes")


def _tiene_rastro(db: Session, jornada: m.Jornada) -> bool:
    """Marcas, dinero que ya salio o esta en camino, o un cambio."""
    from app.routers.servicios import _movimientos
    if bool(jornada.inicio_real) or jornada.estatus not in (
            m.EstatusJornada.PLANEADA, m.EstatusJornada.CONFIRMADA):
        return True
    if _movimientos(db, [jornada.id]):
        return True
    if any(a.reemplaza_a_id or a.relevado_en for a in jornada.personal):
        return True
    return bool(db.query(m.ReemplazoRecurso).filter(
        (m.ReemplazoRecurso.desde_jornada_id == jornada.id)
        | (m.ReemplazoRecurso.hasta_jornada_id == jornada.id)).count())


def _puesto_a_mano(jornada: m.Jornada, contrato: m.ContratoImplantado,
                   turno: str) -> bool:
    """Gente que el consultor puso desde la ficha del dia: alguien que no
    es de la plantilla del mes o, en natural, un fin de semana con gente
    --nace vacio y lo cubre alguien a proposito--. Ese dia lo decidio el."""
    if not jornada.personal:
        return False
    if turno != TURNO_12X36 and jornada.fecha.weekday() >= 5:
        return True
    plantilla = {f.persona_id for f in contrato.plantilla}
    if not plantilla and contrato.titular_id:
        plantilla = {contrato.titular_id}
    return any(a.persona_id not in plantilla for a in jornada.personal)


def _igual(a, b) -> bool:
    """Si dos valores de un termino dicen lo mismo: 2900 y 2900.00 son el
    mismo precio; lunes_viernes y lunes_viernes, los mismos dias."""
    if a is None or b is None:
        return a is None and b is None
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return str(getattr(a, "value", a)) == str(getattr(b, "value", b))


def _texto(valor) -> str | None:
    if valor is None:
        return None
    return str(getattr(valor, "value", valor))


def _rehacer_con_el_acuerdo(db: Session, contrato: m.ContratoImplantado,
                            antes: dict) -> dict:
    """Los dias de un mes futuro, con el acuerdo ya puesto en el contrato.

    Un dia que ya no es de servicio y no tiene nada se quita; los dias
    nuevos de servicio se crean como los crea el mes (entre semana con la
    plantilla, el fin de semana abierto por cubrir); la hora nueva se
    pone en los dias que siguen con la de antes. Un dia con marcas, con
    cambio, con gente puesta a mano o movido a mano se deja como esta y
    se cuenta como «no se toco».
    """
    from app.routers.servicios import _limpiar_jornadas
    equipo = contrato.servicio.equipos[0] if contrato.servicio.equipos else None
    turno = turno_del_servicio(db, contrato.servicio_id)
    hoy = hoy_del_servicio(db, contrato.servicio)
    movidos, creados, quitados, no_tocados = [], [], [], []
    if equipo is None:
        return {"movidos": movidos, "creados": creados, "quitados": quitados,
                "no_tocados": no_tocados}

    contratados = set(dias_del_mes(contrato.anio, contrato.mes,
                                   contrato.dias_servicio, contrato.desde_dia,
                                   turno))
    hora_vieja = time.fromisoformat(antes["hora_presentacion"])
    duracion_vieja = timedelta(hours=float(antes["horas"]))
    del_mes = [j for j in list(equipo.jornadas)
               if j.fecha.year == contrato.anio and j.fecha.month == contrato.mes]

    for j in sorted(del_mes, key=lambda x: x.fecha):
        if j.estatus == m.EstatusJornada.CANCELADA or j.fecha <= hoy:
            continue
        intocable = _tiene_rastro(db, j) or _puesto_a_mano(j, contrato, turno)
        if j.fecha not in contratados:
            # Ya no es dia de servicio. Con gente puesta --el sabado que
            # el cliente pidio aparte-- se queda: eso no es del esquema.
            if intocable or j.personal:
                no_tocados.append(j.fecha.isoformat())
                continue
            _limpiar_jornadas(db, [j.id])
            db.flush()
            db.delete(j)
            quitados.append(j.fecha.isoformat())
            continue
        inicio, fin = _ventana(contrato, j.fecha)
        if (j.inicio_programado, j.fin_programado) == (inicio, fin):
            continue
        if intocable:
            no_tocados.append(j.fecha.isoformat())
            continue
        # Solo los dias que siguen con la hora y las horas de antes: un
        # dia movido a mano a otra hora lo decidio el consultor.
        if (j.inicio_programado.time() != hora_vieja
                or j.fin_programado - j.inicio_programado != duracion_vieja):
            no_tocados.append(j.fecha.isoformat())
            continue
        j.inicio_programado, j.fin_programado = inicio, fin
        j.hora_confirmada = True
        movidos.append(j.fecha.isoformat())
    db.flush()

    # Los dias nuevos de servicio, como los abre el mes: `generar_mes`
    # rellenando salta los que ya estan y vuelve a poner la base del mes.
    db.expire(equipo, ["jornadas"])
    hay = {j.fecha for j in equipo.jornadas}
    faltan = [d for d in contratados if d not in hay and d > hoy]
    if faltan or not _igual(antes["dias_servicio"], contrato.dias_servicio):
        generar_mes(db, contrato.id, rellenando=True)
        hay_ahora = {j.fecha for j in equipo.jornadas}
        creados = [d.isoformat() for d in sorted(faltan) if d in hay_ahora]
    return {"movidos": movidos, "creados": creados, "quitados": quitados,
            "no_tocados": sorted(no_tocados)}


def aplicar_acuerdo_a_meses_futuros(db: Session, servicio: m.Servicio,
                                    desde_mes: tuple[int, int],
                                    cambios: dict,
                                    excepto_id: int | None = None) -> dict:
    """Copia los terminos nuevos a cada mes generado desde `desde_mes` y
    rehace sus dias (seccion 105, decision 14).

    `cambios` son los campos del contrato que cambiaron, de
    `CAMPOS_DEL_ACUERDO`; `excepto_id`, el contrato donde se hizo el
    cambio, que ya los tiene. Un mes con visto bueno no se toca: su
    factura salio. Devuelve por mes que campos cambiaron (antes y
    despues) y que dias se movieron, crearon, quitaron o no se tocaron,
    y la frase del mes en curso cuando quedo fuera.
    """
    from app import cierre_mes
    cambios = {k: v for k, v in cambios.items() if k in CAMPOS_DEL_ACUERDO}
    meses = []
    for contrato in (db.query(m.ContratoImplantado)
                     .filter_by(servicio_id=servicio.id, generado=True)
                     .order_by(m.ContratoImplantado.anio,
                               m.ContratoImplantado.mes).all()):
        if (contrato.anio, contrato.mes) < desde_mes or contrato.id == excepto_id:
            continue
        if cierre_mes.con_visto_bueno(db, contrato):
            continue
        antes = {"hora_presentacion": contrato.hora_presentacion,
                 "horas": horas_de(contrato, db)[0],
                 "dias_servicio": contrato.dias_servicio}
        campos = {}
        for campo, valor in cambios.items():
            previo = getattr(contrato, campo)
            if _igual(previo, valor):
                continue
            setattr(contrato, campo, valor)
            campos[campo] = (_texto(previo), _texto(valor))
        if "dias_servicio" in campos:
            contrato.incluye_fines_de_semana = (
                contrato.dias_servicio != m.DiasServicio.LUNES_VIERNES)
        db.flush()
        dias = _rehacer_con_el_acuerdo(db, contrato, antes)
        from app import implantado_precios
        if "dias_servicio" in campos and contrato.precios_de_la_lista:
            # Con la lista de implantados del cliente (seccion 80), los
            # dias de servicio cambian el precio del mes de la unidad.
            implantado_precios.aplicar(
                contrato, implantado_precios.de_la_lista(db, contrato))
            implantado_precios.fijar_moneda_del_mes(db, contrato)
        elif any(k in implantado_precios.CAMPOS or k == "esquema"
                 for k in campos):
            # Precios copiados: si son los de la lista, el mes sigue con
            # ella; si no, es un acuerdo especial, como en el mes de origen.
            contrato.precios_de_la_lista = implantado_precios.sigue_la_lista(
                contrato, implantado_precios.de_la_lista(db, contrato))
        db.flush()
        meses.append({"contrato_id": contrato.id,
                      "periodo": _periodo(contrato.anio, contrato.mes),
                      "anio": contrato.anio, "mes": contrato.mes,
                      "campos": campos, **dias})
    return {"desde": _periodo(*desde_mes), "meses": meses,
            "mes_en_curso": mes_en_curso_que_no_se_toca(db, servicio, desde_mes)}


def resumen_del_acuerdo_aplicado(hecho: dict) -> str:
    """Una frase por mes para la bitacora: que cambio y que dias."""
    partes = []
    for mes in hecho["meses"]:
        campos = "; ".join(f"{k}: {a} -> {d}" for k, (a, d) in mes["campos"].items())
        dias = (f"{len(mes['movidos'])} movidos, {len(mes['creados'])} creados, "
                f"{len(mes['quitados'])} quitados, "
                f"{len(mes['no_tocados'])} sin tocar")
        partes.append(f"{mes['periodo']}: {campos or 'sin cambios'} · {dias}")
    if hecho.get("mes_en_curso"):
        partes.append(hecho["mes_en_curso"])
    return " | ".join(partes)


# --------------------------------------------------------------------
# El mes que sigue
#
# El implantado no se vuelve a vender cada treinta dias: se vende una vez
# y se opera hasta que alguien lo cancela. Por eso el mes siguiente no se
# captura, se abre —con los mismos terminos y la misma plantilla— y se
# genera. Lo hace el consultor con un boton, o el proceso de todas las
# mananas cuando el mes en curso se esta acabando.
#
# El tope es uno: se puede tener abierto el mes en curso y el que sigue,
# no mas. Abrir diciembre en septiembre seria congelar tres meses de
# plantilla contra una realidad que todavia no existe.
# --------------------------------------------------------------------

# Cuando el proceso automatico empieza a abrir el mes que sigue: faltando
# estos dias o menos para que termine el mes en curso.
DIAS_ANTES = 7


def _siguiente_periodo(anio: int, mes: int) -> tuple[int, int]:
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def siguiente_periodo(anio: int, mes: int) -> tuple[int, int]:
    """(anio, mes) del mes que sigue a ese. Para quien lo pide desde
    fuera del motor (seccion 105): los terminos de un mes llegan a los
    meses que le siguen."""
    return _siguiente_periodo(anio, mes)


def ultimo_mes(db: Session, servicio_id: int):
    """El contrato mas adelantado del servicio."""
    return (db.query(m.ContratoImplantado)
            .filter_by(servicio_id=servicio_id)
            .order_by(m.ContratoImplantado.anio.desc(),
                      m.ContratoImplantado.mes.desc()).first())


def estado_del_siguiente(db: Session, servicio: m.Servicio,
                         hoy: date | None = None) -> dict:
    """Que mes sigue, si se puede abrir, y por que no cuando no se puede.

    Lo contesta el panel para poder pintar el boton apagado *con su
    razon*: un boton que no hace nada y no dice por que fue el problema
    que ya vimos con el primer mes.
    """
    return estado_desde(ultimo_mes(db, servicio.id), servicio,
                        hoy or hoy_del_servicio(db, servicio))


def hoy_del_servicio(db: Session, servicio: m.Servicio) -> date:
    """Que dia es en el pais del servicio, nunca el del servidor: cerca
    de la medianoche, con tres horas de diferencia con Brasil, el boton
    del mes siguiente hablaba del dia equivocado (seccion 101)."""
    return reloj.hoy_en(db.get(m.Pais, servicio.pais_id)
                        if servicio.pais_id else None)


def estado_desde(ultimo, servicio: m.Servicio, hoy: date) -> dict:
    """Lo mismo, con el contrato ya en la mano y el hoy de su pais.

    La cartera ya trajo los meses de cada servicio; volver a preguntarlos
    uno por uno seria una consulta por renglon de la pantalla.
    """
    if not ultimo:
        return {"se_puede": False, "periodo": None, "anio": None, "mes": None,
                "razon": "Este implantado todavia no tiene ningun mes abierto."}

    anio, mes = _siguiente_periodo(ultimo.anio, ultimo.mes)
    tope_a, tope_m = _siguiente_periodo(hoy.year, hoy.month)
    etiqueta = f"{mes:02d}/{anio}"

    if (anio, mes) > (tope_a, tope_m):
        return {"se_puede": False, "periodo": etiqueta, "anio": anio,
                "mes": mes, "abierto_hasta": f"{ultimo.mes:02d}/{ultimo.anio}",
                "razon": (f"El mes {ultimo.mes:02d}/{ultimo.anio} ya esta "
                          f"abierto. El sistema deja abierto un solo mes "
                          f"por delante del que se opera.")}

    if servicio.estatus in (m.EstatusServicio.CANCELADO,
                            m.EstatusServicio.CERRADO,
                            m.EstatusServicio.TERMINADO):
        return {"se_puede": False, "periodo": etiqueta, "anio": anio,
                "mes": mes,
                "razon": f"El servicio esta {servicio.estatus.value}."}

    return {"se_puede": True, "periodo": etiqueta, "anio": anio, "mes": mes,
            "abierto_hasta": f"{ultimo.mes:02d}/{ultimo.anio}",
            "razon": None}


def abrir_siguiente(db: Session, servicio: m.Servicio,
                    hoy: date | None = None) -> dict:
    """Abre el mes que sigue con los terminos y la plantilla vigentes.

    La plantilla se copia entera --son las posiciones del contrato-- y
    al generar los dias se revisa quien de ella puede ir todavia
    (seccion 101): lo que no, queda por cubrir y se dice en la respuesta.
    """
    estado = estado_del_siguiente(db, servicio, hoy)
    if not estado["se_puede"]:
        raise HTTPException(409, {"mensaje": "No se puede abrir el mes que sigue",
                                  "que_hacer": estado["razon"],
                                  "periodo": estado["periodo"]})

    anterior = ultimo_mes(db, servicio.id)
    anio, mes = estado["anio"], estado["mes"]

    # El mes nuevo nace con el acuerdo (seccion 105, decision 14): los
    # dias de servicio y la hora del encuentro son los del trato, que es
    # donde se corrigen a medio mes --el mes en curso no se toca--, y lo
    # que el trato no dice se copia del mes que termina, como siempre.
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())
    dias_servicio = ((acuerdo.dias_servicio if acuerdo else None)
                     or anterior.dias_servicio)
    hora = ((acuerdo.hora_presentacion if acuerdo else None)
            or anterior.hora_presentacion)
    contrato = m.ContratoImplantado(
        servicio_id=servicio.id, anio=anio, mes=mes,
        desde_dia=None,             # el mes nuevo siempre arranca el dia 1
        modalidad_id=anterior.modalidad_id,
        hora_presentacion=hora,
        esquema=anterior.esquema,
        dias_servicio=dias_servicio,
        incluye_fines_de_semana=dias_servicio != m.DiasServicio.LUNES_VIERNES,
        titular_id=anterior.titular_id,
        titular_rotacion_id=anterior.titular_rotacion_id,
        vehiculo_id=anterior.vehiculo_id,
        precio_mes_vehiculo=anterior.precio_mes_vehiculo,
        precio_dia_personal=anterior.precio_dia_personal,
        precio_dia_adicional=anterior.precio_dia_adicional,
        precio_mes_completo=anterior.precio_mes_completo,
        viaticos_incluidos=anterior.viaticos_incluidos,
        gastos_mes=anterior.gastos_mes,
        precio_hora_extra=anterior.precio_hora_extra,
        # Las horas que ese acuerdo tiene de distinto al pais (seccion
        # 104) pasan con el; vacias, siguen siendo las del pais.
        horas_jornada=anterior.horas_jornada,
        horas_descanso=anterior.horas_descanso,
        # El precio fijo de las modalidades de la propuesta (seccion
        # 115) sigue en el mes nuevo, con los dias de servicio del trato.
        dias_del_mensual=(DIAS_DEL_MENSUAL.get(dias_servicio)
                          if anterior.dias_del_mensual else None),
        # Los precios copiados van en su moneda (seccion 82); el tipo de
        # cambio no se copia: el mes nuevo toma el que este puesto cuando
        # se abre.
        moneda=anterior.moneda,
        dias_base=len(dias_del_mes(anio, mes, dias_servicio,
                                   None,
                                   turno_del_servicio(db, servicio.id))))
    db.add(contrato)
    db.flush()

    # La plantilla completa, no solo el titular: quien maneja que unidad
    # ya se decidio y el mes nuevo opera igual que el que termina.
    #
    # Con su rol. Se copiaba sin el, y el rol no es un adorno: de el
    # salen el precio al cliente y la comision que se paga, y una
    # jornada sin rol no se puede cobrar ni pagar. El mes que se abria
    # solo nacia con la plantilla desarmada y nadie lo veia hasta el
    # corte.
    for fila in anterior.plantilla:
        db.add(m.PersonaImplantado(contrato_id=contrato.id,
                                   persona_id=fila.persona_id,
                                   rol_id=fila.rol_id,
                                   vehiculo_id=fila.vehiculo_id,
                                   empieza=fila.empieza))
    for fila in anterior.unidades:
        db.add(m.UnidadImplantado(contrato_id=contrato.id,
                                  vehiculo_id=fila.vehiculo_id))
    # Si el mes que termina iba con la lista de implantados del cliente
    # (seccion 80), el nuevo la vuelve a tomar: con sus dias de servicio y
    # con lo que la lista diga hoy. Si iba a mano --un acuerdo especial--,
    # se queda lo copiado, como siempre.
    from app import implantado_precios
    if (anterior.precios_de_la_lista
            and anterior.esquema == m.EsquemaCotizacionImplantado.POR_DIA):
        implantado_precios.al_abrir(db, contrato)
    else:
        implantado_precios.fijar_moneda_del_mes(db, contrato)
    db.commit()
    db.refresh(contrato)

    generado = generar_mes(db, contrato.id)
    return {"contrato_id": contrato.id,
            "copiado_de": f"{anterior.mes:02d}/{anterior.anio}",
            "personas": len(anterior.plantilla),
            "unidades": len(anterior.unidades), **generado}


def atrasado(db: Session, servicio: m.Servicio, cuando: date) -> bool:
    """Si al servicio le falta el mes en que ya esta: su ultimo contrato
    es de un mes anterior al de hoy."""
    ultimo = ultimo_mes(db, servicio.id)
    return bool(ultimo) and (ultimo.anio, ultimo.mes) < (cuando.year,
                                                          cuando.month)


def por_abrir(db: Session, hoy: date | None = None) -> list:
    """Los implantados vivos a los que se les acaba el mes.

    Se miran faltando DIAS_ANTES o menos para que termine el mes en curso:
    antes de eso no hay prisa, y despues el consultor llega un dia 1 sin
    calendario.

    Y los que se quedaron atras (seccion 101): si el reloj no corrio la
    ultima semana --el worker caido del 24 al 30--, el dia 1 el mes en
    curso no existe, y con la regla de la ventana nadie lo abria hasta
    el 24 del mes siguiente. Un implantado vivo sin el mes de hoy le
    toca en la primera vuelta que corra.
    """
    # El proceso corre a una hora fija de Mexico, pero el mes se acaba
    # en cada pais a su hora. Se mira el calendario de cada servicio.
    relojes = reloj.Relojes(db)

    def le_toca(servicio) -> bool:
        cuando = hoy or relojes.hoy(servicio.pais_id)
        ultimo_dia = calendar.monthrange(cuando.year, cuando.month)[1]
        return (ultimo_dia - cuando.day <= DIAS_ANTES
                or atrasado(db, servicio, cuando))

    vivos = (db.query(m.Servicio)
             .filter(m.Servicio.tipo == m.TipoServicio.IMPLANTADO,
                     m.Servicio.estatus.notin_(list(YA_NO_SE_ARMA)))
             .all())
    return [s for s in vivos
            if le_toca(s)
            and estado_del_siguiente(
                db, s, hoy or relojes.hoy(s.pais_id))["se_puede"]]


def abrir_los_que_toquen(db: Session, hoy: date | None = None) -> dict:
    """El proceso de todas las mananas. No revienta por uno malo.

    Al que se quedo atras le abre, en la misma vuelta, lo que le falte
    hasta el mes en curso (seccion 101): un mes por vuelta lo dejaba
    dias sin calendario.
    """
    hechos, fallados = [], []
    relojes = reloj.Relojes(db)
    for servicio in por_abrir(db, hoy):
        cuando = hoy or relojes.hoy(servicio.pais_id)
        try:
            for _vuelta in range(12):
                abierto = abrir_siguiente(db, servicio, cuando)
                hechos.append({"servicio_id": servicio.id,
                               "folio": servicio.folio,
                               "periodo": abierto["periodo"],
                               "plantilla_fuera":
                                   abierto.get("plantilla_fuera") or []})
                _avisar_plantilla_fuera(db, servicio, abierto)
                if not atrasado(db, servicio, cuando):
                    break
        except HTTPException as error:
            db.rollback()
            fallados.append({"servicio_id": servicio.id,
                             "folio": servicio.folio,
                             "detalle": str(error.detail)})
        except Exception as error:                        # noqa: BLE001
            # Tampoco por uno que reviente con algo que no es un 409 --el
            # consultor abrio ese mes a mano a las 6:30, una hora mal
            # guardada--: antes salia de la tarea sin deshacer y a los
            # demas no se les abria el mes ese dia (seccion 100).
            db.rollback()
            registro.exception("no se pudo abrir el mes de %s", servicio.folio)
            fallados.append({"servicio_id": servicio.id,
                             "folio": servicio.folio,
                             "detalle": str(error)[:200]})
    return {"abiertos": hechos, "fallados": fallados}


def _avisar_plantilla_fuera(db: Session, servicio: m.Servicio,
                            abierto: dict) -> None:
    """El mes que el reloj abrio con alguien de la plantilla que ya no
    puede ir se le dice a su consultor al telefono (seccion 101), como
    la baja de Odoo: los dias quedaron por cubrir y nadie los esta
    mirando a las seis de la manana. Un aviso que no sale no deshace el
    mes: las alertas de la central ya quedaron."""
    fuera = abierto.get("plantilla_fuera") or []
    if not fuera or not servicio.consultor_id:
        return
    from app import push
    try:
        push.avisar(
            db, servicio.consultor_id,
            titulo=f"{servicio.folio}: el mes {abierto['periodo']} se abrió "
                   "con posiciones por cubrir",
            cuerpo="; ".join(fuera)[:300],
            url=f"/consola/#/implantado/{servicio.id}",
            etiqueta=f"plantilla-fuera-{servicio.id}-{abierto['periodo']}")
    except Exception:                                 # noqa: BLE001
        registro.exception("no se pudo avisar la plantilla fuera de %s",
                           servicio.folio)


def dias_abiertos_sin_nadie(equipo: m.Equipo | None) -> set:
    """Los dias que existen, no estan cancelados y no tienen a nadie: el
    fin de semana que nadie cubrio y, desde la seccion 101, el dia de
    entre semana que se abrio sin la posicion que ya no podia ir. Se
    pintan en ambar aunque el contrato diga que ahi va la plantilla."""
    if not equipo:
        return set()
    return {j.fecha.isoformat() for j in equipo.jornadas
            if j.estatus != m.EstatusJornada.CANCELADA and not j.personal}


def dias_en_ambar(db: Session, servicio: m.Servicio,
                  desde: date | None = None) -> list[str]:
    """Los dias contratados que todavia no tienen quien los cubra.

    Casi siempre son fines de semana: entre semana va la plantilla fija,
    salvo el dia que se abrio sin alguien que ya no podia ir (seccion
    101). Se miran de hoy en adelante —lo que ya paso no se puede
    cubrir— y en todos los meses abiertos, porque la hoja que se libera
    habla del servicio, no de un mes. `desde` es el hoy del pais del
    servicio, salvo que quien llama traiga otro (el reloj de prueba).
    """
    desde = desde or hoy_del_servicio(db, servicio)
    equipo = servicio.equipos[0] if servicio.equipos else None
    cubiertos = {}
    if equipo:
        for jornada in equipo.jornadas:
            if jornada.personal:
                cubiertos[jornada.fecha.isoformat()] = True
    vacios = dias_abiertos_sin_nadie(equipo)

    ambar = []
    for contrato in (db.query(m.ContratoImplantado)
                     .filter_by(servicio_id=servicio.id)
                     .order_by(m.ContratoImplantado.anio,
                               m.ContratoImplantado.mes).all()):
        if not contrato.generado:
            continue
        for dia in calendario_del_mes(contrato.anio, contrato.mes,
                                      contrato.dias_servicio,
                                      contrato.desde_dia, cubiertos,
                                      vacios=vacios):
            if dia["estado"] == "por_cubrir" and dia["fecha"] >= desde.isoformat():
                ambar.append(dia["fecha"])
    return ambar


# --------------------------------------------------------------------
# Viaticos del mes
#
# El implantado corre sin fin, pero el dinero no: se deposita, se
# comprueba y se cierra mes con mes, igual que se factura. Estas cuentas
# salen de las mismas jornadas del corte para que el papel cuadre solo.
# --------------------------------------------------------------------

VIATICOS_EN_CERO = {"asignado": "0", "depositado": "0", "en_camino": "0",
                    "comprobado": "0", "por_comprobar": "0"}


def viaticos_del_mes(db: Session, jornada_ids: list[int]) -> dict:
    """Lo asignado, lo depositado y lo comprobado, por persona y total."""
    vacio = {"por_persona": {}, "total": VIATICOS_EN_CERO.copy()}
    if not jornada_ids:
        return vacio

    asignaciones = (db.query(m.AsignacionViatico)
                    .filter(m.AsignacionViatico.jornada_id.in_(jornada_ids))
                    .all())
    if not asignaciones:
        return vacio

    # El deposito no es un evento unico —se pide, se cae, se vuelve a
    # pedir—, asi que lo que de verdad salio se lee de las solicitudes.
    solicitudes = (db.query(m.SolicitudTransferencia)
                   .filter(m.SolicitudTransferencia.asignacion_id.in_(
                       [a.id for a in asignaciones]))
                   .all())
    confirmadas, en_camino = {}, {}
    for s_ in solicitudes:
        if s_.estatus == m.EstatusTransferencia.CONFIRMADA:
            confirmadas[s_.asignacion_id] = (
                confirmadas.get(s_.asignacion_id, Decimal("0"))
                + Decimal(str(s_.monto)))
        elif s_.estatus in (m.EstatusTransferencia.PENDIENTE,
                            m.EstatusTransferencia.ENVIADA):
            en_camino[s_.asignacion_id] = (
                en_camino.get(s_.asignacion_id, Decimal("0"))
                + Decimal(str(s_.monto)))

    por_persona: dict[int, dict] = {}
    for a in asignaciones:
        ficha = por_persona.setdefault(a.persona_id, {
            "asignado": Decimal("0"), "depositado": Decimal("0"),
            "en_camino": Decimal("0"), "comprobado": Decimal("0")})
        ficha["asignado"] += Decimal(str(a.monto_total or 0))
        ficha["comprobado"] += Decimal(str(a.monto_comprobado or 0))
        ficha["depositado"] += confirmadas.get(a.id, Decimal("0"))
        ficha["en_camino"] += en_camino.get(a.id, Decimal("0"))

    total = {k: Decimal("0") for k in
             ("asignado", "depositado", "en_camino", "comprobado")}
    salida = {}
    for persona_id, ficha in por_persona.items():
        # Lo que la persona todavia le debe de papeles a la empresa.
        ficha["por_comprobar"] = max(ficha["depositado"] - ficha["comprobado"],
                                     Decimal("0"))
        for llave in total:
            total[llave] += ficha[llave]
        salida[persona_id] = {k: str(v) for k, v in ficha.items()}

    total["por_comprobar"] = max(total["depositado"] - total["comprobado"],
                                 Decimal("0"))
    return {"por_persona": salida,
            "total": {k: str(v) for k, v in total.items()}}

"""Servicios implantados: contratacion mensual con recursos fijos.

El procedimiento diario es identico al eventual. Lo que cambia:
  - Se contrata el mes completo, con una base de dias habiles (22 tipico).
  - Los fines de semana son dias adicionales, con costo extra.
  - El vehiculo se cotiza por mes completo.
  - Los reemplazos por descanso o enfermedad se resuelven sobre la marcha.
  - El cierre de viaticos y la facturacion son mensuales.
"""
import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import contingencia
from app import disponibilidad
from app import models as m
from app import reloj


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
                       cancelados: set | None = None) -> list[dict]:
    """El mes dia por dia, con el color que le toca a cada uno.

    verde  el dia esta cubierto por los recursos del servicio
    ambar  esta contratado pero falta decir quien lo cubre; siempre es
           un fin de semana, porque el que trabajo toda la semana
           descansa y hay que confirmarlo o cambiarlo
    gris   no hay servicio contratado ese dia

    En 12x36 el ambar no existe: cada dia nace con su persona puesta
    --las dos se alternan y entre las dos cubren los siete dias-- asi
    que el mes sale entero en verde.
    """
    es_12x36 = turno == TURNO_12X36
    tope = 7 if es_12x36 else hasta_donde(dias_servicio)
    ultimo = calendar.monthrange(anio, mes)[1]
    primero = max(1, min(desde_dia or 1, ultimo))
    cubiertos = cubiertos or {}
    cancelados = cancelados or set()

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
    horas = float(contrato.modalidad.horas)

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

        if es_12x36:
            _asignar_turno(db, jornada, contrato,
                           de_quien_es(pareja, arranque, dias[0], dia))
        elif dia.weekday() < 5:
            _asignar_del_contrato(db, jornada, contrato)
        else:
            # El fin de semana contratado se abre, pero vacio: quien
            # trabajo de lunes a viernes descansa, y darle el sabado por
            # hecho es como se llega al domingo sin conductor. La unidad
            # si va: el vehiculo del implantado siempre es el mismo.
            if contrato.vehiculo_id:
                db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                            vehiculo_id=contrato.vehiculo_id))
        creadas += 1

    # La base del mes es la que marca el calendario, no un numero fijo.
    contrato.dias_base = len(dias)
    contrato.generado = True
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
    cubrir, el de la posicion que cubre —la primera de la plantilla—,
    porque lo que se le vendio al cliente ese dia es esa posicion, no la
    persona. Sin plantilla no hay rol que heredar y el consultor lo dice.
    """
    if persona_id:
        suyo = next((f for f in contrato.plantilla
                     if f.persona_id == persona_id), None)
        if suyo and suyo.rol_id:
            return suyo.rol_id
    return contrato.plantilla[0].rol_id if contrato.plantilla else None


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

    equipo = contrato.servicio.equipos[0]
    ya_esta = (db.query(m.Jornada)
               .filter_by(equipo_id=equipo.id, fecha=fecha).first())
    if ya_esta:
        # El dia ya existe. Si nadie lo cubre —el fin de semana que nace
        # en ambar— esto es justamente ponerle quien va, no un error.
        if ya_esta.personal:
            raise HTTPException(409, "Ese dia ya esta cubierto")
        return _cubrir(db, contrato, ya_esta, persona_id)

    hora = time.fromisoformat(contrato.hora_presentacion)
    inicio = datetime.combine(fecha, hora)
    jornada = m.Jornada(
        equipo_id=equipo.id, fecha=fecha, modalidad_id=contrato.modalidad_id,
        inicio_programado=inicio,
        fin_programado=inicio + timedelta(hours=float(contrato.modalidad.horas)),
        hora_confirmada=True, es_dia_adicional=True)
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=contrato.servicio_id).first())
    _heredar_punto(jornada, acuerdo)
    db.add(jornada)
    db.flush()

    cubre_id = persona_id or contrato.titular_id
    if cubre_id:
        if not db.get(m.Persona, cubre_id):
            raise HTTPException(404, f"No existe la persona {cubre_id}")
        db.add(m.AsignacionPersonal(
            jornada_id=jornada.id, persona_id=cubre_id,
            rol_id=rol_del_contrato(contrato, cubre_id)))
    if contrato.vehiculo_id:
        db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                    vehiculo_id=contrato.vehiculo_id))
    db.commit()

    cubre = db.get(m.Persona, cubre_id) if cubre_id else None
    return {"jornada_id": jornada.id, "fecha": fecha.isoformat(),
            "es_dia_adicional": True,
            "cubre": cubre.nombre if cubre else None,
            "costo_extra": float(contrato.precio_dia_adicional or 0)}


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
    if not db.get(m.Persona, cubre_id):
        raise HTTPException(404, f"No existe la persona {cubre_id}")

    dias = [jornada]
    if jornada.fecha.weekday() >= 5:
        # El otro dia de ese mismo fin de semana, si tambien esta abierto
        # y tambien esta vacio.
        paso = 1 if jornada.fecha.weekday() == 5 else -1
        vecino = (db.query(m.Jornada)
                  .filter_by(equipo_id=jornada.equipo_id,
                             fecha=jornada.fecha + timedelta(days=paso))
                  .first())
        if vecino and vecino.fecha.weekday() >= 5 and not vecino.personal:
            dias.append(vecino)

    for dia in dias:
        db.add(m.AsignacionPersonal(
            jornada_id=dia.id, persona_id=cubre_id,
            rol_id=rol_del_contrato(contrato, cubre_id)))
        if contrato.vehiculo_id and not dia.vehiculos:
            db.add(m.AsignacionVehiculo(jornada_id=dia.id,
                                        vehiculo_id=contrato.vehiculo_id))
    db.commit()

    cubre = db.get(m.Persona, cubre_id)
    return {"jornada_id": jornada.id, "fecha": jornada.fecha.isoformat(),
            "es_dia_adicional": True, "cubre": cubre.nombre,
            "dias_cubiertos": [d.fecha.isoformat() for d in dias],
            "costo_extra": float(contrato.precio_dia_adicional or 0)
                           * len(dias)}


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
    equipo = servicio.equipos[0] if servicio.equipos else None
    jornada = (db.query(m.Jornada)
               .filter_by(equipo_id=equipo.id, fecha=fecha).first()
               if equipo else None)
    if not jornada:
        raise HTTPException(404, "Ese dia no existe en el servicio")
    if jornada.estatus != m.EstatusJornada.CANCELADA:
        raise HTTPException(409, "Ese dia no esta cancelado")
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
    """De que hora a que hora corre ese dia, segun el contrato."""
    hora = time.fromisoformat(contrato.hora_presentacion)
    inicio = datetime.combine(fecha, hora)
    return inicio, inicio + timedelta(hours=float(contrato.modalidad.horas))


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
    if jornada and jornada.personal:
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
                            m.Persona.activo.is_(True)).all()):
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
    posiciones = [{
        "persona_id": p.persona_id,
        "nombre": p.persona.nombre if p.persona else None,
        "rol_id": p.rol_id,
        "rol": p.rol.nombre if p.rol else None,
        "vehiculo_id": p.vehiculo_id,
        "placa": p.vehiculo.placa if p.vehiculo else None,
    } for p in contrato.plantilla]

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
        "se_puede_cerrar": bool(jornada and not _ya_empezo(jornada)),
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
    if not personal:
        raise HTTPException(409, "Hay que decir quien cubre el dia")

    equipo = servicio.equipos[0]
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())

    dias = [fecha]
    if ambos_dias:
        vecino = _vecino_del_fin(db, equipo.id, fecha, contrato.dias_servicio)
        if vecino:
            dias.append(vecino)

    tocados = []
    for dia in sorted(dias):
        jornada = (db.query(m.Jornada)
                   .filter_by(equipo_id=equipo.id, fecha=dia).first())
        if jornada and _ya_empezo(jornada):
            raise HTTPException(409, f"El dia {dia.isoformat()} ya empezo")

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

        for fila in personal:
            persona_id = fila["persona_id"]
            if not db.get(m.Persona, persona_id):
                raise HTTPException(404, f"No existe la persona {persona_id}")
            db.add(m.AsignacionPersonal(
                jornada_id=jornada.id, persona_id=persona_id,
                rol_id=(fila.get("rol_id")
                        or rol_del_contrato(contrato, persona_id)),
                vehiculo_id=fila.get("vehiculo_id")))
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
    if con_dinero:
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
        total = sum((Decimal(str(v.monto_total or 0)) for v in con_dinero),
                    Decimal("0"))
        quienes = ", ".join(sorted(
            v.persona.nombre for v in con_dinero if v.persona))
        jornada.estatus = m.EstatusJornada.CANCELADA
        db.commit()
        return {"cancelado": fecha.isoformat(), "borrado": False,
                "viaticos_vivos": len(con_dinero), "monto": str(total),
                "nota": (f"El dia queda cancelado: trae {total} de {quienes} "
                         f"que ya salio del banco. Ese dinero se resuelve "
                         f"con la devolucion, no borrando el dia.")}

    # Lo que solo estaba asignado se va con el dia: ese dinero no existe
    # todavia fuera del sistema.
    for v in viaticos:
        db.delete(v)
    db.flush()

    db.delete(jornada)
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

    equipo = contrato.servicio.equipos[0] if contrato.servicio.equipos else None
    jornadas = sorted(
        [j for j in (equipo.jornadas if equipo else [])
         if j.fecha.year == contrato.anio and j.fecha.month == contrato.mes
         and j.estatus != m.EstatusJornada.CANCELADA],
        key=lambda j: j.fecha)

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

    equipo = contrato.servicio.equipos[0] if contrato.servicio.equipos else None
    jornadas = equipo.jornadas if equipo else []
    vivas = [j for j in jornadas if j.estatus != m.EstatusJornada.CANCELADA]
    base = [j for j in vivas if not j.es_dia_adicional]
    adicionales = [j for j in vivas if j.es_dia_adicional]

    if contrato.esquema == m.EsquemaCotizacionImplantado.MES_COMPLETO:
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
        total = sum(v["monto"] for v in viaticos["propuestos"])
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


def validar_plantilla(db: Session, personal: list, unidades: list,
                      turno: str = TURNO_NATURAL) -> None:
    """Cada quien con su rol, y toda unidad con alguien a bordo.

    Ya no se pregunta que es cada persona: el personal de seguridad es
    general y el rol lo decide el consultor. Lo que si se exige es que
    lo diga, porque de ese rol salen el precio al cliente y la comision
    que se le paga, y sin el la jornada no se puede cobrar ni pagar.

    `personal` son ternas (persona_id, vehiculo_id, rol_id) y `unidades`
    los ids de las unidades del mes.
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

    for vehiculo_id in unidades:
        unidad = db.get(m.Vehiculo, vehiculo_id)
        if not unidad:
            raise HTTPException(404, f"No existe la unidad {vehiculo_id}")
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
    validar_plantilla(db, personal, unidades,
                      turno_del_servicio(db, contrato.servicio_id))

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


def _asignar_turno(db: Session, jornada: m.Jornada,
                   contrato: m.ContratoImplantado, fila) -> None:
    """El dia de una sola persona, con la unidad del mes.

    La unidad no rota: es una sola por turno --es regla-- y corre el mes
    entero. Lo que rota es quien la maneja.
    """
    unidad = (contrato.unidades[0].vehiculo_id if contrato.unidades
              else contrato.vehiculo_id)
    if fila:
        db.add(m.AsignacionPersonal(jornada_id=jornada.id,
                                    persona_id=fila.persona_id,
                                    rol_id=fila.rol_id,
                                    vehiculo_id=fila.vehiculo_id or unidad))
    if unidad:
        db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                    vehiculo_id=unidad))


def _asignar_del_contrato(db: Session, jornada: m.Jornada,
                          contrato: m.ContratoImplantado) -> None:
    """Le pone al dia la plantilla completa del mes.

    Con el abordo puesto: quien maneja que unidad ya se decidio una vez
    al armar el mes, y repetirlo dia por dia era la parte del trabajo que
    de verdad sobraba.
    """
    if contrato.plantilla:
        for fila in contrato.plantilla:
            db.add(m.AsignacionPersonal(jornada_id=jornada.id,
                                        persona_id=fila.persona_id,
                                        rol_id=fila.rol_id,
                                        vehiculo_id=fila.vehiculo_id))
        for fila in contrato.unidades:
            db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                        vehiculo_id=fila.vehiculo_id))
        return

    # Contratos de antes de la plantilla: siguen operando con su titular.
    if contrato.titular_id:
        db.add(m.AsignacionPersonal(jornada_id=jornada.id,
                                    persona_id=contrato.titular_id))
    if contrato.vehiculo_id:
        db.add(m.AsignacionVehiculo(jornada_id=jornada.id,
                                    vehiculo_id=contrato.vehiculo_id))


def rehacer_dias(db: Session, contrato: m.ContratoImplantado) -> int:
    """Vuelve a poner la plantilla en los dias que todavia no pasaron.

    Lo ya operado no se toca: si alguien cubrio el martes, ese martes se
    queda como quedo. Reescribirlo seria borrar lo que de verdad paso, y
    de ahi salen la nomina y la comprobacion de viaticos.
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

        for a in list(jornada.personal):
            db.delete(a)
        for a in list(jornada.vehiculos):
            db.delete(a)
        db.flush()
        jornada.estatus = m.EstatusJornada.PLANEADA
        if es_12x36:
            _asignar_turno(db, jornada, contrato,
                           de_quien_es(pareja, arranque, inicio, jornada.fecha))
        else:
            _asignar_del_contrato(db, jornada, contrato)
        rehechos += 1

    db.flush()
    return rehechos


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
    return estado_desde(ultimo_mes(db, servicio.id), servicio, hoy)


def estado_desde(ultimo, servicio: m.Servicio, hoy: date | None = None) -> dict:
    """Lo mismo, con el contrato ya en la mano.

    La cartera ya trajo los meses de cada servicio; volver a preguntarlos
    uno por uno seria una consulta por renglon de la pantalla.
    """
    hoy = hoy or date.today()
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
    """Abre el mes que sigue con los terminos y la plantilla vigentes."""
    estado = estado_del_siguiente(db, servicio, hoy)
    if not estado["se_puede"]:
        raise HTTPException(409, {"mensaje": "No se puede abrir el mes que sigue",
                                  "que_hacer": estado["razon"],
                                  "periodo": estado["periodo"]})

    anterior = ultimo_mes(db, servicio.id)
    anio, mes = estado["anio"], estado["mes"]

    contrato = m.ContratoImplantado(
        servicio_id=servicio.id, anio=anio, mes=mes,
        desde_dia=None,             # el mes nuevo siempre arranca el dia 1
        modalidad_id=anterior.modalidad_id,
        hora_presentacion=anterior.hora_presentacion,
        esquema=anterior.esquema,
        dias_servicio=anterior.dias_servicio,
        incluye_fines_de_semana=anterior.incluye_fines_de_semana,
        titular_id=anterior.titular_id,
        titular_rotacion_id=anterior.titular_rotacion_id,
        vehiculo_id=anterior.vehiculo_id,
        precio_mes_vehiculo=anterior.precio_mes_vehiculo,
        precio_dia_personal=anterior.precio_dia_personal,
        precio_dia_adicional=anterior.precio_dia_adicional,
        precio_mes_completo=anterior.precio_mes_completo,
        dias_base=len(dias_del_mes(anio, mes, anterior.dias_servicio,
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
    db.commit()
    db.refresh(contrato)

    generado = generar_mes(db, contrato.id)
    return {"contrato_id": contrato.id,
            "copiado_de": f"{anterior.mes:02d}/{anterior.anio}",
            "personas": len(anterior.plantilla),
            "unidades": len(anterior.unidades), **generado}


def por_abrir(db: Session, hoy: date | None = None) -> list:
    """Los implantados vivos a los que se les acaba el mes.

    Se miran faltando DIAS_ANTES o menos para que termine el mes en curso:
    antes de eso no hay prisa, y despues el consultor llega un dia 1 sin
    calendario.
    """
    # El proceso corre a una hora fija de Mexico, pero el mes se acaba
    # en cada pais a su hora. Se mira el calendario de cada servicio.
    relojes = reloj.Relojes(db)

    def le_toca(servicio) -> bool:
        cuando = hoy or relojes.hoy(servicio.pais_id)
        ultimo_dia = calendar.monthrange(cuando.year, cuando.month)[1]
        return ultimo_dia - cuando.day <= DIAS_ANTES

    vivos = (db.query(m.Servicio)
             .filter(m.Servicio.tipo == m.TipoServicio.IMPLANTADO,
                     m.Servicio.estatus.notin_([m.EstatusServicio.CANCELADO,
                                                m.EstatusServicio.CERRADO,
                                                m.EstatusServicio.TERMINADO]))
             .all())
    return [s for s in vivos
            if le_toca(s)
            and estado_del_siguiente(
                db, s, hoy or relojes.hoy(s.pais_id))["se_puede"]]


def abrir_los_que_toquen(db: Session, hoy: date | None = None) -> dict:
    """El proceso de todas las mananas. No revienta por uno malo."""
    hechos, fallados = [], []
    for servicio in por_abrir(db, hoy):
        try:
            abierto = abrir_siguiente(db, servicio, hoy)
            hechos.append({"servicio_id": servicio.id, "folio": servicio.folio,
                           "periodo": abierto["periodo"]})
        except HTTPException as error:
            db.rollback()
            fallados.append({"servicio_id": servicio.id,
                             "folio": servicio.folio,
                             "detalle": str(error.detail)})
    return {"abiertos": hechos, "fallados": fallados}


def dias_en_ambar(db: Session, servicio: m.Servicio,
                  desde: date | None = None) -> list[str]:
    """Los dias contratados que todavia no tienen quien los cubra.

    Siempre son fines de semana: entre semana va la plantilla fija. Se
    miran de hoy en adelante —lo que ya paso no se puede cubrir— y en
    todos los meses abiertos, porque la hoja que se libera habla del
    servicio, no de un mes.
    """
    desde = desde or date.today()
    equipo = servicio.equipos[0] if servicio.equipos else None
    cubiertos = {}
    if equipo:
        for jornada in equipo.jornadas:
            if jornada.personal:
                cubiertos[jornada.fecha.isoformat()] = True

    ambar = []
    for contrato in (db.query(m.ContratoImplantado)
                     .filter_by(servicio_id=servicio.id)
                     .order_by(m.ContratoImplantado.anio,
                               m.ContratoImplantado.mes).all()):
        if not contrato.generado:
            continue
        for dia in calendario_del_mes(contrato.anio, contrato.mes,
                                      contrato.dias_servicio,
                                      contrato.desde_dia, cubiertos):
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

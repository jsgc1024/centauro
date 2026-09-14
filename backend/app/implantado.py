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

from app import disponibilidad
from app import models as m


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


def dias_del_mes(anio: int, mes: int, dias_servicio,
                desde_dia: int | None = None) -> list[date]:
    """Los dias que cubre el contrato dentro del mes.

    Con desde_dia arranca a media marcha: un servicio que empieza el 15 se
    cobra del 15 al ultimo dia y el corte cae ahi. El mes siguiente entra
    limpio el dia 1, sin arrastrar el pedazo anterior.
    """
    tope = hasta_donde(dias_servicio)
    ultimo = calendar.monthrange(anio, mes)[1]
    primero = max(1, min(desde_dia or 1, ultimo))
    dias = [date(anio, mes, d) for d in range(primero, ultimo + 1)]
    return [d for d in dias if d.weekday() < tope]


def calendario_del_mes(anio: int, mes: int, dias_servicio,
                       desde_dia: int | None = None,
                       cubiertos: dict | None = None) -> list[dict]:
    """El mes dia por dia, con el color que le toca a cada uno.

    verde  el dia esta cubierto por los recursos del servicio
    ambar  esta contratado pero falta decir quien lo cubre; siempre es
           un fin de semana, porque el que trabajo toda la semana
           descansa y hay que confirmarlo o cambiarlo
    gris   no hay servicio contratado ese dia
    """
    tope = hasta_donde(dias_servicio)
    ultimo = calendar.monthrange(anio, mes)[1]
    primero = max(1, min(desde_dia or 1, ultimo))
    cubiertos = cubiertos or {}

    salida = []
    for numero in range(1, ultimo + 1):
        dia = date(anio, mes, numero)
        quien = cubiertos.get(dia.isoformat())
        if quien and numero >= primero:
            # Un dia fuera del esquema que el cliente pidio aparte. Ya
            # tiene quien lo cubra, asi que cuenta como cubierto aunque
            # no entre en los dias contratados.
            estado = "cubierto"
        elif numero < primero or dia.weekday() >= tope:
            estado = "sin_servicio"
        elif quien:
            estado = "cubierto"
        elif dia.weekday() >= 5:
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


def generar_mes(db: Session, contrato_id: int) -> dict:
    """Crea las jornadas del mes y asigna los recursos fijos.

    Un implantado son full days encadenados: cada dia se opera igual que
    un eventual, con su ventana de dos horas previas y su ciclo de hitos.
    """
    contrato = db.get(m.ContratoImplantado, contrato_id)
    if not contrato:
        raise HTTPException(404, f"No existe el contrato {contrato_id}")
    if contrato.generado:
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

    dias = dias_del_mes(contrato.anio, contrato.mes,
                        contrato.dias_servicio, contrato.desde_dia)

    # El punto de inicio es el mismo todos los dias del implantado: se
    # capturo una vez en el acuerdo y cada jornada lo hereda. Sin esto,
    # el consultor tendria que escribir la misma direccion veintidos
    # veces al mes, y la hoja no se publicaria hasta que lo hiciera.
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())

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
            es_dia_adicional=dia.weekday() >= 5)
        _heredar_punto(jornada, acuerdo)
        db.add(jornada)
        db.flush()

        if dia.weekday() < 5:
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
        "nota": (f"Se factura por los {contrato.dias_base} dias que tiene el mes "
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
        es_dia_adicional=True)
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
        m.EstatusJornada.EN_CURSO, m.EstatusJornada.TERMINADA)


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
            "avisos": [x.como_dict()["mensaje"] for x in hallazgos],
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

    db.delete(jornada)
    db.commit()
    return {"cerrado": fecha.isoformat()}


def reemplazar(db: Session, jornada_id: int, entra_id: int,
               motivo: m.MotivoReemplazo, registrado_por_id: int,
               nota: str | None = None) -> dict:
    """Cambio de personal por descanso, enfermedad o contingencia.
    Se resuelve sobre la marcha, no se planea desde el alta."""
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    if not jornada.personal:
        raise HTTPException(409, "Esa jornada no tiene personal asignado")

    entra = db.get(m.Persona, entra_id)
    if not entra:
        raise HTTPException(404, f"No existe la persona {entra_id}")

    asignacion = jornada.personal[0]
    sale_id = asignacion.persona_id
    if sale_id == entra_id:
        raise HTTPException(409, "Esa persona ya esta asignada a la jornada")

    sale_nombre = asignacion.persona.nombre
    asignacion.persona_id = entra_id
    asignacion.reemplaza_a_id = sale_id
    asignacion.confirmado = False

    db.add(m.Reemplazo(jornada_id=jornada.id, sale_id=sale_id, entra_id=entra_id,
                       motivo=motivo, nota=nota,
                       registrado_por_id=registrado_por_id))

    # Si ya habia viaticos dispersados al saliente, quedan para su cierre
    # y al que entra se le abren nuevos.
    viatico = (db.query(m.AsignacionViatico)
               .filter_by(jornada_id=jornada.id, persona_id=sale_id).first())
    aviso = None
    if viatico and viatico.estatus in (m.EstatusViatico.TRANSFERIDO,
                                       m.EstatusViatico.EN_COMPROBACION):
        aviso = (f"{sale_nombre} ya tenia viaticos transferidos: debe cerrarlos y "
                 f"comprobarlos. Hay que asignar viaticos nuevos a {entra.nombre}.")

    db.commit()
    return {"resultado": "reemplazado", "jornada_id": jornada.id,
            "fecha": jornada.fecha.isoformat(),
            "sale": sale_nombre, "entra": entra.nombre,
            "motivo": motivo.value, "aviso": aviso}


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

    reemplazos = (db.query(m.Reemplazo)
                  .join(m.Jornada, m.Reemplazo.jornada_id == m.Jornada.id)
                  .filter(m.Jornada.equipo_id == equipo.id).all() if equipo else [])

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
        "reemplazos": [{
            "fecha": r.jornada.fecha.isoformat(), "sale": r.sale.nombre,
            "entra": r.entra.nombre, "motivo": r.motivo.value, "nota": r.nota,
        } for r in reemplazos],
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
                    nota: str | None = None) -> dict:
    """Cambia a una persona o una unidad en un tramo de dias.

    Un dia suelto es un rango de un dia: el consultor no tiene que
    aprender dos formas de hacer lo mismo segun si el que falta avisó con
    un mes o con una hora.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    if hasta and hasta < desde:
        raise HTTPException(400, "El tramo termina antes de empezar")

    equipo = servicio.equipos[0] if servicio.equipos else None
    dias = sorted([j for j in (equipo.jornadas if equipo else [])
                   if j.estatus != m.EstatusJornada.CANCELADA
                   and j.fecha >= desde
                   and (hasta is None or j.fecha <= hasta)],
                  key=lambda j: j.fecha)
    if not dias:
        raise HTTPException(409, "No hay dias en ese tramo")

    if tipo == m.TipoRecurso.PERSONAL:
        entra = db.get(m.Persona, entra_id)
        if not entra:
            raise HTTPException(404, f"No existe la persona {entra_id}")
    else:
        entra = db.get(m.Vehiculo, entra_id)
        if not entra:
            raise HTTPException(404, f"No existe la unidad {entra_id}")

    cambiados, sale_nombre, con_dinero = 0, None, []
    for jornada in dias:
        if tipo == m.TipoRecurso.PERSONAL:
            asignaciones = [a for a in jornada.personal
                            if sale_id is None or a.persona_id == sale_id]
            if not asignaciones:
                continue
            a = asignaciones[0]
            if a.persona_id == entra_id:
                continue
            sale_nombre = sale_nombre or a.persona.nombre
            if sale_id is None:
                sale_id = a.persona_id
            # El dinero que ya salio no se mueve con la persona: el que
            # sale tiene que comprobar lo suyo y al que entra se le abre
            # lo suyo. Se enlista en vez de resolverlo a la callada.
            viatico = (db.query(m.AsignacionViatico)
                       .filter_by(jornada_id=jornada.id,
                                  persona_id=a.persona_id).first())
            if viatico and viatico.estatus in (
                    m.EstatusViatico.TRANSFERIDO,
                    m.EstatusViatico.EN_COMPROBACION):
                con_dinero.append(jornada.fecha.isoformat())
            a.reemplaza_a_id = a.persona_id
            a.persona_id = entra_id
            a.confirmado = False
        else:
            asignaciones = [a for a in jornada.vehiculos
                            if sale_id is None or a.vehiculo_id == sale_id]
            if not asignaciones:
                continue
            a = asignaciones[0]
            if a.vehiculo_id == entra_id:
                continue
            sale_nombre = sale_nombre or a.vehiculo.placa
            if sale_id is None:
                sale_id = a.vehiculo_id
            a.vehiculo_id = entra_id
            # Quien iba a bordo de la unidad que sale no se queda
            # colgado de una que ya no va.
            for p in jornada.personal:
                if p.vehiculo_id == sale_id:
                    p.vehiculo_id = entra_id
        cambiados += 1

    if not cambiados:
        raise HTTPException(409, "No habia nada que cambiar en ese tramo")

    db.add(m.ReemplazoRecurso(
        servicio_id=servicio.id,
        desde_jornada_id=dias[0].id,
        hasta_jornada_id=dias[-1].id if hasta else None,
        tipo=tipo, motivo_tipo=motivo_tipo,
        sale_persona_id=sale_id if tipo == m.TipoRecurso.PERSONAL else None,
        entra_persona_id=entra_id if tipo == m.TipoRecurso.PERSONAL else None,
        sale_vehiculo_id=sale_id if tipo == m.TipoRecurso.VEHICULO else None,
        entra_vehiculo_id=entra_id if tipo == m.TipoRecurso.VEHICULO else None,
        motivo=(nota or motivo_tipo.value)[:600],
        jornadas_afectadas=cambiados,
        hecho_por_id=hecho_por_id))
    db.commit()

    entra_nombre = (entra.nombre if tipo == m.TipoRecurso.PERSONAL
                    else entra.placa)
    return {
        "resultado": "cambiado", "tipo": tipo.value,
        "dias_cambiados": cambiados,
        "desde": dias[0].fecha.isoformat(),
        "hasta": dias[-1].fecha.isoformat() if hasta else None,
        "sale": sale_nombre, "entra": entra_nombre,
        "motivo": motivo_tipo.value,
        "aviso": (f"Hay dias con viaticos ya depositados a {sale_nombre}: "
                  f"{', '.join(con_dinero)}. Tiene que comprobarlos, y a "
                  f"{entra_nombre} hay que abrirle los suyos."
                  if con_dinero else None),
    }


# ------------------------------------------------------------- plantilla

# La combinacion la pide el cliente —un conductor, un agente, dos de cada
# uno— y se repite igual todos los dias del mes. Dos reglas que no se
# pueden romper, porque romperlas manda a la calle un servicio que no
# existe.

# El rol con el que suele ir quien maneja. Se usa solo para elegir a
# quien se apunta como titular del mes: el que se lee de un vistazo en la
# cartera. No limita nada.
ROL_CONDUCTOR = "conductor_seguridad"


def validar_plantilla(db: Session, personal: list, unidades: list) -> None:
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

    gente = {}
    for persona_id, vehiculo_id, rol_id in personal:
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


def guardar_plantilla(db: Session, contrato: m.ContratoImplantado,
                      personal: list, unidades: list) -> None:
    """Reescribe la plantilla del mes, ya validada."""
    validar_plantilla(db, personal, unidades)

    for fila in list(contrato.plantilla):
        db.delete(fila)
    for fila in list(contrato.unidades):
        db.delete(fila)
    db.flush()

    for persona_id, vehiculo_id, rol_id in personal:
        db.add(m.PersonaImplantado(contrato_id=contrato.id,
                                   persona_id=persona_id,
                                   rol_id=rol_id,
                                   vehiculo_id=vehiculo_id))
    for vehiculo_id in unidades:
        db.add(m.UnidadImplantado(contrato_id=contrato.id,
                                  vehiculo_id=vehiculo_id))

    # Se dejan apuntados el primer conductor y la primera unidad: son lo
    # que se lee de un vistazo en la cartera y en el resumen del mes. Si
    # nadie va de conductor —un agente solo que maneja—, el primero.
    roles = {r.id: r.codigo for r in db.query(m.PerfilPersonal).all()}
    conduce = next((pid for pid, _, rid in personal
                    if roles.get(rid) == ROL_CONDUCTOR), None)
    contrato.titular_id = conduce or (personal[0][0] if personal else None)
    contrato.vehiculo_id = unidades[0] if unidades else None
    db.flush()


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

    hoy = date.today()
    ultimo = calendar.monthrange(contrato.anio, contrato.mes)[1]
    primero = date(contrato.anio, contrato.mes, 1)
    fin = date(contrato.anio, contrato.mes, ultimo)

    rehechos = 0
    for jornada in equipo.jornadas:
        if not (primero <= jornada.fecha <= fin):
            continue
        if jornada.fecha <= hoy:
            continue           # lo que ya paso se queda como quedo
        if jornada.estatus != m.EstatusJornada.PLANEADA:
            continue
        # Un dia con cambio ya fue decidido a mano: no se pisa.
        if any(a.reemplaza_a_id for a in jornada.personal):
            continue

        for a in list(jornada.personal):
            db.delete(a)
        for a in list(jornada.vehiculos):
            db.delete(a)
        db.flush()
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
        dias_base=len(dias_del_mes(anio, mes, anterior.dias_servicio)))
    db.add(contrato)
    db.flush()

    # La plantilla completa, no solo el titular: quien maneja que unidad
    # ya se decidio y el mes nuevo opera igual que el que termina.
    for fila in anterior.plantilla:
        db.add(m.PersonaImplantado(contrato_id=contrato.id,
                                   persona_id=fila.persona_id,
                                   vehiculo_id=fila.vehiculo_id))
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
    hoy = hoy or date.today()
    ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
    if ultimo_dia - hoy.day > DIAS_ANTES:
        return []

    vivos = (db.query(m.Servicio)
             .filter(m.Servicio.tipo == m.TipoServicio.IMPLANTADO,
                     m.Servicio.estatus.notin_([m.EstatusServicio.CANCELADO,
                                                m.EstatusServicio.CERRADO,
                                                m.EstatusServicio.TERMINADO]))
             .all())
    return [s for s in vivos
            if estado_del_siguiente(db, s, hoy)["se_puede"]]


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

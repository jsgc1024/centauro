"""Estrellas mensuales del personal de seguridad.

Una estrella por criterio cumplido. La evaluacion es mensual y por persona,
no por servicio: se agregan todas sus jornadas del mes, sean de servicios
eventuales o implantados.

Sancion escalonada por incidencia:
  - error menor: solo retroalimentacion documentada, no toca las estrellas
  - leve:        quita todas las estrellas del mes
  - grave:       la gestiona Recursos Humanos, quita todas las estrellas
"""
import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m

CERO = Decimal("0")


def _rango(anio: int, mes: int) -> tuple[date, date]:
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, 1), date(anio, mes, ultimo)


def jornadas_del_mes(db: Session, persona_id: int, anio: int, mes: int) -> list[m.Jornada]:
    """Las jornadas que se le miden a esta persona este mes.

    El dia en que alguien entra a media jornada, relevando a otro, no es
    suyo: no tuvo hora de presentacion contra la cual medirse y no marco
    la secuencia del dia porque empezo a la mitad. Hasta hoy ese dia le
    regalaba una puntualidad que no trabajo --la jornada arranco a tiempo,
    pero la arranco el otro-- y de paso le cobraba un seguimiento
    incompleto por las marcas de la manana, que tampoco eran suyas.

    El dia del relevo es de quien lo empezo. A el si se le mide, con su
    asignacion marcada con la hora en que lo relevaron.

    Ojo con la prueba: lo que distingue al que entro a media jornada no
    es `reemplaza_a_id` --eso lo traen tambien los dias que cambiaron de
    dueno limpio, y esos si son suyos--, sino que en esa misma jornada
    haya una asignacion ajena marcada como relevada POR el.
    """
    desde, hasta = _rango(anio, mes)

    entro_a_media = (db.query(m.AsignacionPersonal.jornada_id)
                     .filter(m.AsignacionPersonal.relevado_por_id == persona_id,
                             m.AsignacionPersonal.relevado_en.isnot(None)))

    return (db.query(m.Jornada)
            .join(m.AsignacionPersonal, m.AsignacionPersonal.jornada_id == m.Jornada.id)
            .filter(m.AsignacionPersonal.persona_id == persona_id,
                    m.Jornada.fecha >= desde, m.Jornada.fecha <= hasta,
                    m.Jornada.estatus != m.EstatusJornada.CANCELADA,
                    m.Jornada.id.notin_(entro_a_media))
            .all())


# ---------------------------------------------------------------- criterios

def medir_puntualidad(db: Session, jornadas: list[m.Jornada], persona_id: int,
                      margen_minutos: int = 0,
                      margen_ocasiones: int = 0) -> dict:
    """Llegar al punto. Son dos cosas, no una.

    La hora sola no basta: "marque a tiempo" desde la casa no es haber
    llegado. Por eso la marca de llegada tiene que estar dentro de la
    geocerca del origen. Si la marca no trae coordenadas no se le
    cuenta en contra --no se puede probar lo contrario--; lo que cuenta
    en contra es la marca que SI trae coordenadas y cayo fuera.

    El margen: tantos minutos, tantas veces al mes. Sin el, un retraso
    de dos minutos una vez pesa igual que cuarenta minutos tres veces, y
    lo que no distingue no motiva. Cuando los retrasos perdonables pasan
    de las ocasiones permitidas, se perdonan los mas chicos y los demas
    cuentan tarde: el margen es para el descuido, no para el habito.
    """
    # Contra que se mide. `inicio_real` NO sirve: lo escribe el hito de
    # contacto con el ejecutivo, o sea el meet and greet. Medir la
    # llegada con esa hora es medir otra cosa --y castiga al que llego
    # temprano y espero veinte minutos a que el ejecutivo bajara--.
    # Se mide contra la marca de LLEGADA de esta persona, que es la que
    # dice "estoy en el punto". Y solo contra la suya (seccion 105,
    # decision 4): cada quien marca su llegada, y quien no la marco en
    # un dia que si opero no cuenta como puntual ese dia. Antes
    # `inicio_real` --el contacto del equipo-- servia de respaldo, y al
    # segundo de la unidad, que nunca marcaba, le regalaba la
    # puntualidad del companero.
    llegadas = {h.jornada_id: h for h in db.query(m.Hito).filter(
        m.Hito.jornada_id.in_([j.id for j in jornadas]),
        m.Hito.persona_id == persona_id,
        m.Hito.tipo == m.TipoHito.LLEGADA_ORIGEN,
        m.Hito.anulado_en.is_(None)).all()}

    # Lo que decide si el criterio aplica son las JORNADAS, no las
    # marcas. Es la diferencia entre "no le toco" y "no marco", y
    # confundirlas abria un agujero: el dia que alguien no marcara su
    # llegada, el criterio se declaraba no aplicable, sus 780 se
    # repartian entre los demas criterios, y no marcar salia pagando
    # MAS que llegar a tiempo. Un mes sin jornadas si es "no le toco".
    if not jornadas:
        return {"valor": CERO, "aplica": False,
                "detalle": "Sin jornadas este mes"}

    # El dia cuya llegada asento la central a mano NO se mide: decision
    # de Salvador, 20 sep. La central no puede probar la hora --no hay
    # ubicacion, nadie estaba ahi con el telefono-- asi que ni la premia
    # ni la castiga.
    #
    # Ese dia sale del DENOMINADOR y no cuenta como cumplido: contarlo a
    # favor convertiria el registro a mano en una forma de regalar bono,
    # que es justo lo que el candado de "nadie firma su propio dia"
    # existe para evitar.
    a_mano = {j.id for j in jornadas
              if (llegadas.get(j.id) is not None
                  and llegadas[j.id].registrado_a_mano_en is not None)}
    medibles = [j for j in jornadas if j.id not in a_mano]

    # Un mes entero asentado a mano no deja nada que medir. Entonces el
    # criterio no aplica Y SU MONTO NO SE REPARTE: si se repartiera,
    # volveriamos al agujero que ya cerramos --no marcar pagando mas que
    # llegar a tiempo--, solo que ahora por la puerta de la central.
    if not medibles:
        return {"valor": CERO, "aplica": False, "reparte": False,
                "detalle": (f"Las {len(a_mano)} jornadas del mes las asento "
                            "la central a mano: no hay llegada que medir")}

    # El intento de marcar fuera del punto no deja hito --el servidor lo
    # rechaza-- pero si deja alerta. Sin esto, ese dia aparece como "sin
    # marca" a secas y la ficha no explica nada.
    intentos = {a.jornada_id for a in db.query(m.Alerta).filter(
        m.Alerta.jornada_id.in_([j.id for j in jornadas]),
        m.Alerta.persona_id == persona_id,
        m.Alerta.tipo == m.TipoAlerta.FUERA_DE_GEOCERCA).all()}

    buenas, fuera, tarde, perdonables, sin_marca = [], [], [], [], []
    for j in medibles:
        marca = llegadas.get(j.id)
        if marca is None:
            sin_marca.append(j)
            continue
        momento = marca.marcado_en
        if marca.dentro_geocerca is False:
            fuera.append(j)
            continue
        retraso = (momento - j.inicio_programado).total_seconds() / 60
        if retraso <= 0:
            buenas.append(j)
        elif retraso <= margen_minutos:
            perdonables.append((j, int(round(retraso))))
        else:
            tarde.append((j, int(round(retraso))))

    # Los que sobran del margen se van a tarde: se perdonan los mas chicos.
    perdonables.sort(key=lambda x: x[1])
    tarde.extend(perdonables[margen_ocasiones:])
    perdonadas = perdonables[:margen_ocasiones]
    buenas.extend(j for j, _ in perdonadas)

    valor = Decimal(len(buenas)) / Decimal(len(medibles)) * 100
    detalle = f"{len(buenas)} de {len(medibles)} jornadas a tiempo y en el punto"
    if a_mano:
        detalle += (f". Fuera del calculo: {len(a_mano)} que asento la "
                    "central a mano")
    if tarde:
        tarde.sort(key=lambda x: -x[1])
        dias = ", ".join(f"{j.fecha:%d/%m} ({mm} min)" for j, mm in tarde[:4])
        detalle += f". Tarde: {dias}"
    if fuera:
        dias = ", ".join(f"{j.fecha:%d/%m}" for j in fuera[:4])
        detalle += f". Marco fuera del punto: {dias}"
    if sin_marca:
        con_intento = [j for j in sin_marca if j.id in intentos]
        resto = [j for j in sin_marca if j.id not in intentos]
        if con_intento:
            dias = ", ".join(f"{j.fecha:%d/%m}" for j in con_intento[:4])
            detalle += f". Intento marcar fuera del punto: {dias}"
        if resto:
            dias = ", ".join(f"{j.fecha:%d/%m}" for j in resto[:4])
            detalle += f". Sin marca de llegada: {dias}"
    if perdonadas:
        dias = ", ".join(f"{j.fecha:%d/%m}" for j, _ in perdonadas)
        detalle += f". Dentro del margen: {dias}"
    return {"valor": valor.quantize(Decimal("0.01")), "detalle": detalle}


def medir_entrega_unidad(db: Session, jornadas: list[m.Jornada],
                         persona_id: int) -> dict:
    """Entregar la unidad documentada.

    Ojo con lo que este criterio NO mide: el dano. El dano al entregar
    lo declara quien entrega, y el dano que aparece despues lo declara
    quien recibe --asi que medirlo aqui seria dejar que la palabra de
    uno le cueste el bono a otro sin que nadie lo revise--. El dano ya
    tiene su camino: avisa al consultor, y si amerita se vuelve
    incidencia con visto bueno de direccion, y la incidencia apaga el
    mes completo. Aqui se mide lo que es 100 por ciento suyo y no
    necesita el juicio de nadie: que la revision de entrega exista y
    este completa --odometro, firma y las fotos--.

    Y declarar un dano nunca castiga: quien lo declara se esta
    protegiendo, y frenarlo seria castigar justo lo que queremos.
    """
    # Se miden LAS ENTREGAS QUE EL REGISTRO, no las unidades que hubo en
    # sus jornadas.
    #
    # La unidad del dia no vive en su asignacion: con una sola unidad en
    # el equipo, `asignacion_personal.vehiculo_id` se queda vacio a
    # proposito --sobra decirlo-- y el vehiculo cuelga de la jornada. Y
    # de todos modos amarrarlo a la asignacion seria cobrarle la entrega
    # a quien nunca toco la camioneta, o al que lo relevaron a media
    # jornada.
    #
    # Como ya no hay fin de servicio sin revision de entrega, la revision
    # existe: lo que este criterio mide es que este COMPLETA --odometro,
    # firma y fotos--, que es lo unico que sirve tres semanas despues.
    servicios = {j.equipo.servicio_id for j in jornadas}
    if not servicios:
        return {"valor": CERO, "aplica": False, "detalle": "Sin jornadas este mes"}

    entregas = (db.query(m.RevisionUnidad)
                .filter(m.RevisionUnidad.persona_id == persona_id,
                        m.RevisionUnidad.tipo == m.TipoRevision.ENTREGA,
                        m.RevisionUnidad.servicio_id.in_(servicios)).all())
    if not entregas:
        return {"valor": CERO, "aplica": False,
                "detalle": "No entrego ninguna unidad este mes: el criterio "
                           "no aplica"}

    bien, problemas = 0, []
    for r in entregas:
        falta = []
        if r.kilometraje is None:
            falta.append("odometro")
        if not r.firma:
            falta.append("firma")
        if not r.fotos:
            falta.append("fotos")
        if falta:
            placa = r.vehiculo.placa if r.vehiculo else "?"
            problemas.append(f"{r.momento:%d/%m} {placa} (sin {', '.join(falta)})")
        else:
            bien += 1

    valor = Decimal(bien) / Decimal(len(entregas)) * 100
    detalle = f"{bien} de {len(entregas)} entregas documentadas"
    if problemas:
        detalle += f". {', '.join(problemas[:4])}"
    return {"valor": valor.quantize(Decimal("0.01")), "detalle": detalle}


def medir_recompra(db: Session, jornadas: list[m.Jornada],
                   persona_id: int) -> dict:
    """Que el cliente lo vuelva a pedir.

    La unica senal de calidad que el sistema puede contar solo. No se
    deduce de que haya coincidido con el mismo cliente --eso puede ser
    nada mas quien estaba libre--: la marca el consultor al armar el
    equipo, porque alguien tiene que afirmarlo.

    Se mide en veces, no en porcentaje: el valor es el numero de
    servicios distintos en que lo pidieron, y el umbral se configura en
    ese mismo lenguaje.
    """
    if not jornadas:
        return {"valor": CERO, "aplica": False, "detalle": "Sin jornadas este mes"}

    servicios = set()
    for j in jornadas:
        for a in j.personal:
            if a.persona_id == persona_id and a.pedido_por_cliente:
                servicios.add(j.equipo.servicio_id)

    if not servicios:
        # No aplica en vez de reprobado: este criterio suma, no resta.
        # El personal de plazas chicas o de cuentas nuevas no tiene como
        # acumularlas, y cobrarles por eso seria cobrarles la geografia.
        return {"valor": CERO, "aplica": False,
                "detalle": "Ningun cliente lo pidio por nombre este mes"}

    nombres = []
    for servicio_id in list(servicios)[:3]:
        servicio = db.get(m.Servicio, servicio_id)
        if servicio and servicio.folio:
            nombres.append(servicio.folio)
    detalle = f"Lo pidieron por nombre en {len(servicios)} servicio(s)"
    if nombres:
        detalle += f": {', '.join(nombres)}"
    return {"valor": Decimal(len(servicios)), "detalle": detalle}


def medir_seguimiento(db: Session, jornadas: list[m.Jornada], persona_id: int) -> dict:
    """Asertividad en el uso de la app: que cada jornada tenga su secuencia
    completa de hitos y sin alertas por falta de reporte.

    Al relevado a media jornada se le exige solo lo que paso antes del
    relevo (seccion 101): el dia es suyo --lo empezo y marco su
    llegada--, pero el fin lo marca quien se quedo, y el contacto con
    el ejecutivo tambien si el relevo llego antes. Se le cobraba ese
    fin ajeno como falla, y con pocas jornadas en el mes perdia la
    estrella.
    """
    if not jornadas:
        return {"valor": CERO, "aplica": False,
                "detalle": "Sin jornadas este mes"}

    relevado_en = {a.jornada_id: a.relevado_en for a in
                   db.query(m.AsignacionPersonal)
                   .filter(m.AsignacionPersonal.jornada_id.in_(
                               [j.id for j in jornadas]),
                           m.AsignacionPersonal.persona_id == persona_id,
                           m.AsignacionPersonal.relevado_en.isnot(None))
                   .all()}
    completas = 0
    faltantes = []
    for j in jornadas:
        hitos = db.query(m.Hito).filter_by(jornada_id=j.id).all()
        tipos = {h.tipo for h in hitos if h.persona_id == persona_id}
        requeridos = {m.TipoHito.LLEGADA_ORIGEN, m.TipoHito.CONTACTO_EJECUTIVO,
                      m.TipoHito.FIN_SERVICIO}
        relevo = relevado_en.get(j.id)
        if relevo is not None:
            # La llegada siempre: con ella se quedo con el dia. El
            # contacto solo si el ejecutivo subio antes de que lo
            # relevaran; el fin nunca es suyo.
            antes = {h.tipo for h in hitos if h.marcado_en <= relevo}
            requeridos = {m.TipoHito.LLEGADA_ORIGEN} | (
                {m.TipoHito.CONTACTO_EJECUTIVO} & antes)
        sin_reporte = (db.query(m.Alerta)
                       .filter_by(jornada_id=j.id, tipo=m.TipoAlerta.SIN_REPORTE)
                       .count())
        if requeridos.issubset(tipos) and not sin_reporte:
            completas += 1
        else:
            faltantes.append(j.fecha.strftime("%d/%m"))

    valor = Decimal(completas) / Decimal(len(jornadas)) * 100
    detalle = f"{completas} de {len(jornadas)} jornadas con seguimiento completo"
    if faltantes:
        detalle += f". Fallas: {', '.join(faltantes[:5])}"
    return {"valor": valor.quantize(Decimal("0.01")), "detalle": detalle}


DIAS_CORTOS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]


def _cuando(momento: datetime) -> str:
    """"jue 17 a las 23:40"."""
    return (f"{DIAS_CORTOS[momento.weekday()]} {momento.day} a las "
            f"{momento:%H:%M}")


def medir_cierre_viaticos(db: Session, persona_id: int, anio: int,
                          mes: int) -> dict:
    """Comprobar el dinero a tiempo (decision de Salvador, 23 sep).

    A tiempo es haber terminado de comprobar antes de su plazo: lo
    comprobado valido y lo devuelto alcanzaron lo depositado antes de
    T0 + 24 h. Se mide cuando termino de comprobar, no el dia de cada
    jornada: hasta aqui se comparaba el plazo contra el fin del dia mas
    24 horas, que desde los dos relojes es siempre igual o mayor, y el
    criterio no media nada.

    Cada dinero cuenta en el mes en que cae su plazo: el del servicio
    del 30 de septiembre que vence el 1 de octubre cuenta en octubre. El
    cierre con descuento no es a tiempo: es lo que pasa cuando no se
    comprobo. Se mide por servicio --por mes en el implantado--, porque
    el dinero de una persona en un servicio es uno solo (`app.bolson`).
    """
    from app import bolson
    from app import reloj

    desde, hasta = _rango(anio, mes)
    inicio = datetime.combine(desde, time.min)
    fin = datetime.combine(hasta + timedelta(days=1), time.min)
    # Con margen hacia atras: el plazo que manda es el ultimo del dinero,
    # y un dia puede traer el suyo del mes anterior.
    candidatos = (db.query(m.AsignacionViatico)
                  .filter(m.AsignacionViatico.persona_id == persona_id,
                          m.AsignacionViatico.estatus
                          != m.EstatusViatico.CANCELADO,
                          m.AsignacionViatico.limite_comprobacion
                          >= inicio - timedelta(days=45),
                          m.AsignacionViatico.limite_comprobacion < fin)
                  .all())
    bolsones: dict[tuple, list] = {}
    for v in candidatos:
        servicio = v.jornada.equipo.servicio
        clave = (servicio.id,
                 (v.jornada.fecha.year, v.jornada.fecha.month)
                 if servicio.tipo == m.TipoServicio.IMPLANTADO else None)
        bolsones.setdefault(clave, []).append(v)

    medidos, bien, problemas = 0, 0, []
    for suyos in bolsones.values():
        # El bolson completo, no solo lo que traia plazo en la ventana.
        suyos = bolson.de_la_persona(db, suyos[0])
        limites = [v.limite_comprobacion for v in suyos
                   if v.limite_comprobacion]
        plazo = max(limites) if limites else None
        if not plazo or not (inicio <= plazo < fin):
            continue
        cuenta = bolson.cuenta(suyos)
        if cuenta["depositado"] <= 0:
            continue
        servicio = suyos[0].jornada.equipo.servicio
        pais = db.get(m.Pais, servicio.pais_id)
        if cuenta["estatus"] == "con_descuento":
            medidos += 1
            problemas.append(f"{servicio.folio}: se cerro con descuento")
            continue
        termino = bolson.termino_de_comprobar(suyos, pais)
        if termino is None and reloj.ahora_en(pais) < plazo:
            # Sigue en plazo: todavia puede comprobar. Una evaluacion a
            # medio mes no lo cuenta como tarde; la del dia 3 ya lo ve
            # vencido o terminado.
            continue
        medidos += 1
        if termino and termino <= plazo:
            bien += 1
        elif termino:
            horas = int((termino - plazo).total_seconds() // 3600)
            tarde = (f"{horas} hora(s) despues" if horas >= 1
                     else "minutos despues")
            problemas.append(
                f"{servicio.folio}: termino de comprobar el "
                f"{_cuando(termino)}, {tarde} de su plazo "
                f"({plazo:%H:%M})")
        else:
            problemas.append(
                f"{servicio.folio}: no termino de comprobar; su plazo "
                f"vencio el {_cuando(plazo)}")

    if not medidos:
        return {"valor": CERO, "aplica": False,
                "detalle": ("No tuvo dinero que comprobar con plazo en este "
                            "mes: el criterio no aplica")}
    valor = Decimal(bien) / Decimal(medidos) * 100
    detalle = f"{bien} de {medidos} a tiempo"
    if problemas:
        detalle += ". " + ". ".join(problemas[:3])
    return {"valor": valor.quantize(Decimal("0.01")),
            "detalle": detalle[:400]}


def medir_capacitacion(db: Session, persona_id: int, anio: int,
                       mes: int) -> dict:
    """Si traia todos sus certificados vigentes al cierre del mes.

    Esto era una casilla que alguien marcaba a mano, y el criterio del
    bono decia "dato de Odoo" cuando Odoo no lo mandaba. Ahora sale del
    padron: esta al corriente quien no trae ningun certificado vencido.
    El sistema lo sabe solo, y el dia que Odoo mande los cursos solo
    cambia de donde llegan las filas --no como se mide--.

    Se mide al CIERRE del mes, no a hoy: un certificado que vencio el 2
    de octubre estaba vigente todo septiembre, y septiembre es el mes
    que se esta calculando.

    Padron vacio NO es reprobado. Sin certificados registrados el
    criterio no aplica y su monto se reparte entre los demas: nadie
    pierde dinero porque a un padron le falte una captura --o porque
    Odoo todavia no conecte--.
    """
    cierre = _rango(anio, mes)[1]
    cursos = (db.query(m.Capacitacion)
              .filter_by(persona_id=persona_id, activo=True).all())
    if not cursos:
        return {"valor": CERO, "aplica": False,
                "detalle": "Sin certificados registrados: el criterio no aplica"}

    vencidos = [c for c in cursos
                if c.vigencia_hasta and c.vigencia_hasta < cierre]
    if vencidos:
        cuales = ", ".join(f"{c.nombre} ({c.vigencia_hasta:%d/%m/%Y})"
                           for c in vencidos[:3])
        return {"valor": CERO,
                "detalle": f"Vencido al {cierre:%d/%m}: {cuales}"}

    # El que esta por vencer todavia cuenta, y se dice: el mes que entra
    # ya no cuenta, y avisarlo aqui es mas barato que descontarlo
    # despues.
    pronto = sorted((c for c in cursos if c.vigencia_hasta),
                    key=lambda c: c.vigencia_hasta)
    detalle = f"{len(cursos)} certificado(s) vigentes al {cierre:%d/%m}"
    if pronto:
        detalle += f". El proximo vence el {pronto[0].vigencia_hasta:%d/%m/%Y}"
    return {"valor": Decimal("100"), "detalle": detalle}


# ---------------------------------------------------------------- evaluacion

def incidencia_del_mes(db: Session, persona_id: int, anio: int, mes: int):
    """Solo cuentan las incidencias ya autorizadas por el director de operaciones,
    y el error menor nunca toca las estrellas."""
    desde, hasta = _rango(anio, mes)
    return (db.query(m.Incidencia)
            .filter(m.Incidencia.persona_id == persona_id,
                    m.Incidencia.fecha >= desde, m.Incidencia.fecha <= hasta,
                    m.Incidencia.autorizada.is_(True),
                    m.Incidencia.gravedad != m.GravedadIncidencia.ERROR_MENOR)
            .order_by(m.Incidencia.gravedad.desc())
            .first())


def evaluar(db: Session, persona_id: int, anio: int, mes: int,
            capacitacion_cumplida: bool | None = None) -> m.EvaluacionMensual:
    persona = db.get(m.Persona, persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {persona_id}")

    pais_id = persona.plaza.pais_id
    criterios = (db.query(m.CriterioEstrella)
                 .filter_by(pais_id=pais_id, activo=True).all())
    if not criterios:
        raise HTTPException(400, "No hay criterios de estrella configurados para ese pais")

    jornadas = jornadas_del_mes(db, persona_id, anio, mes)

    evaluacion = (db.query(m.EvaluacionMensual)
                  .filter_by(persona_id=persona_id, anio=anio, mes=mes).first())
    if evaluacion:
        if evaluacion.estatus == m.EstatusEvaluacion.PAGADA:
            raise HTTPException(409, "Esa evaluacion ya se pago")
        # Autorizar congela el monto (seccion 101): recalcular una
        # autorizada la regresaba a calculada, se perdia quien la firmo
        # y la persona desaparecia de la bandeja del dia 5 sin que RRHH
        # se enterara. La tarea del dia 3 ya la respetaba; esta no.
        if evaluacion.estatus == m.EstatusEvaluacion.AUTORIZADA:
            raise HTTPException(409, {
                "mensaje": "Esa evaluación ya está autorizada: el bono es "
                           "dinero y no se recalcula",
                "que_hacer": "Lo que haya que corregir va como ajuste a "
                             "mano en Nóminas, con su motivo; la "
                             "evaluación se queda como la firmó Recursos "
                             "Humanos."})
        for r in list(evaluacion.detalle):
            db.delete(r)
        db.flush()
    else:
        evaluacion = m.EvaluacionMensual(
            persona_id=persona_id, anio=anio, mes=mes,
            moneda=db.get(m.Pais, pais_id).moneda_local)
        db.add(evaluacion)
        db.flush()

    evaluacion.jornadas_evaluadas = len(jornadas)

    puntual = next((c for c in criterios
                    if c.codigo == m.CodigoCriterio.PUNTUALIDAD), None)
    medidas = {
        m.CodigoCriterio.PUNTUALIDAD: medir_puntualidad(
            db, jornadas, persona_id,
            margen_minutos=int(puntual.tolerancia_minutos) if puntual else 0,
            margen_ocasiones=int(puntual.tolerancia_ocasiones) if puntual else 0),
        m.CodigoCriterio.SEGUIMIENTO_APP: medir_seguimiento(db, jornadas, persona_id),
        m.CodigoCriterio.CIERRE_VIATICOS: medir_cierre_viaticos(
            db, persona_id, anio, mes),
        m.CodigoCriterio.ENTREGA_UNIDAD: medir_entrega_unidad(db, jornadas, persona_id),
        m.CodigoCriterio.RECOMPRA: medir_recompra(db, jornadas, persona_id),
        # Vacio no es reprobado. Mientras Odoo no mande la capacitacion
        # del mes, el criterio NO APLICA y su monto se reparte entre los
        # demas: nadie debe perder dinero porque a un sistema le falta
        # una conexion. Un False explicito si reprueba --eso ya es un
        # dato--; lo que no hay es None.
        # Sin decir nada, sale del padron de certificados. Un bool
        # explicito sigue mandando, para el caso raro en que alguien
        # tenga que corregir un mes a mano.
        m.CodigoCriterio.CAPACITACION: (
            medir_capacitacion(db, persona_id, anio, mes)
            if capacitacion_cumplida is None else
            {"valor": Decimal("100") if capacitacion_cumplida else CERO,
             "detalle": ("Capacitacion del mes cumplida a mano"
                         if capacitacion_cumplida
                         else "Marcado a mano como no cumplido")}),
    }

    # El bono posible del mes es la suma del catalogo. Si algun criterio no
    # aplica, ese monto se reparte entre los que si aplican, para que nadie
    # cobre de menos por algo que no dependio de el.
    #
    # El reparto es A PRORRATA DEL PESO, no en partes iguales. Repartir
    # en partes iguales aplanaba SIEMPRE el catalogo --con los cuatro
    # criterios aplicando, puntualidad dejaba de valer 800 y
    # capacitacion dejaba de valer 500: los dos pagaban 650--, o sea
    # que la pantalla dejaba configurar pesos y el motor los ignoraba.
    bono_posible = sum((Decimal(str(c.monto_mensual)) for c in criterios), CERO)
    aplicables = [c for c in criterios
                  if medidas.get(c.codigo, {}).get("aplica", True)]

    # El criterio que suma y no resta se sale del reparto: si no aplica,
    # su monto no se reparte entre los demas, simplemente no esta. Sin
    # esto, al que no le pidieron cobraba igual que a quien si.
    # `reparte` puede venir del catalogo --el criterio que suma y no
    # resta-- o de la medida del mes, cuando lo que dejo al criterio sin
    # medir fue algo que hizo la casa y no la persona. Las dos razones
    # llevan al mismo sitio: ese monto no se reparte, simplemente no
    # esta.
    def _reparte(c):
        return c.reparte and medidas.get(c.codigo, {}).get("reparte", True)

    fuera = sum((Decimal(str(c.monto_mensual)) for c in criterios
                 if not _reparte(c) and c not in aplicables), CERO)
    a_repartir = bono_posible - fuera
    suma_aplicables = sum((Decimal(str(c.monto_mensual)) for c in aplicables),
                          CERO)
    factor = (a_repartir / suma_aplicables) if suma_aplicables else CERO

    estrellas = 0
    total = CERO
    for criterio in criterios:
        medida = medidas.get(criterio.codigo,
                             {"valor": CERO, "detalle": "Sin medir", "aplica": True})
        aplica = medida.get("aplica", True)
        cumplido = aplica and medida["valor"] >= Decimal(str(criterio.umbral_pct))
        monto = ((Decimal(str(criterio.monto_mensual)) * factor)
                 .quantize(Decimal("0.01")) if cumplido else CERO)
        if cumplido:
            estrellas += 1
            total += monto
        db.add(m.ResultadoCriterio(
            evaluacion_id=evaluacion.id, criterio_id=criterio.id,
            valor_medido=medida["valor"], umbral=criterio.umbral_pct,
            cumplido=cumplido, aplica=aplica, monto=monto,
            detalle=medida["detalle"]))

    # Lo que se guarda es lo que se MIDIO. De este campo lee despues la
    # dimension de capacitacion de la calificacion --"3 de 3 meses al
    # corriente"--, asi que guardar el parametro en vez del resultado
    # dejaba a las dos midiendo cosas distintas.
    medida_cap = medidas[m.CodigoCriterio.CAPACITACION]
    evaluacion.capacitacion_cumplida = bool(
        medida_cap.get("aplica", True) and medida_cap["valor"] > CERO)

    incidencia = incidencia_del_mes(db, persona_id, anio, mes)
    if incidencia:
        evaluacion.anulado_por_incidencia = True
        evaluacion.incidencia_id = incidencia.id
        evaluacion.estrellas = estrellas      # se conservan como referencia
        evaluacion.monto_bono = CERO
    else:
        evaluacion.anulado_por_incidencia = False
        evaluacion.incidencia_id = None
        evaluacion.estrellas = estrellas
        evaluacion.monto_bono = total

    evaluacion.estatus = m.EstatusEvaluacion.CALCULADA
    db.commit()
    db.refresh(evaluacion)
    return evaluacion


def calcular_el_mes(db: Session, anio: int, mes: int) -> dict:
    """Las estrellas de todo el personal activo, de un golpe.

    Corre el dia 3 y no el 1 a proposito: el viatico del ultimo dia del
    mes tiene 24 horas para comprobarse, asi que calcular el 1 castiga a
    quien todavia esta en plazo. El dia 2 queda para que finanzas suba
    los comprobantes que entraron al filo.

    Lo que ya se autorizo o se pago no se toca: es dinero. Lo demas se
    vuelve a calcular cada vez que corre, asi que volver a correrla el
    dia 4 levanta lo que se cerro tarde.

    La incidencia que se autoriza despues de esto si alcanza el mes
    mientras RRHH no lo haya autorizado (seccion 105): el visto bueno
    vuelve a calcular la evaluacion en ese momento (`aplicar_visto_bueno`).
    La que llega con el bono ya autorizado o pagado no lo toca, y el
    visto bueno tiene fecha para poder demostrar que llego tarde.
    """
    calculadas, saltadas, fallidas = 0, 0, []
    personas = (db.query(m.Persona)
                .join(m.Usuario, m.Usuario.persona_id == m.Persona.id)
                .filter(m.Persona.activo.is_(True),
                        m.Usuario.rol == m.Rol.PERSONAL_SEGURIDAD)
                .all())
    for persona in personas:
        firme = (db.query(m.EvaluacionMensual)
                 .filter(m.EvaluacionMensual.persona_id == persona.id,
                         m.EvaluacionMensual.anio == anio,
                         m.EvaluacionMensual.mes == mes,
                         m.EvaluacionMensual.estatus.in_(
                             [m.EstatusEvaluacion.AUTORIZADA,
                              m.EstatusEvaluacion.PAGADA]))
                 .first())
        if firme:
            saltadas += 1
            continue
        try:
            evaluar(db, persona.id, anio, mes)
            calculadas += 1
        except Exception as error:
            # Una persona sin plaza, o un pais sin criterios, no puede
            # tumbar la corrida de los otros treinta y siete.
            db.rollback()
            fallidas.append({"persona_id": persona.id,
                             "nombre": persona.nombre,
                             "motivo": str(error)[:200]})
    return {"periodo": f"{mes:02d}/{anio}", "calculadas": calculadas,
            "ya_firmes": saltadas, "fallidas": fallidas}


def mes_anterior(hoy: date) -> tuple[int, int]:
    """El mes que se cierra hoy. En enero, diciembre del ano pasado."""
    return (hoy.year - 1, 12) if hoy.month == 1 else (hoy.year, hoy.month - 1)


# ------------------------------------------------- una incidencia, leida

def renglon_incidencia(db: Session, i: m.Incidencia) -> dict:
    """Una incidencia como la leen la bandeja de direccion, el expediente
    de la persona y la lista (seccion 105): con quien la registro, quien
    la firmo y su resolucion, no solo si esta autorizada."""
    servicio = db.get(m.Servicio, i.servicio_id) if i.servicio_id else None
    registro = db.get(m.Persona, i.clasificada_por_id)
    firmo = db.get(m.Persona, i.visto_bueno_por_id) if i.visto_bueno_por_id else None
    return {
        "id": i.id, "incidencia_id": i.id,
        "persona_id": i.persona_id, "persona": i.persona.nombre,
        "servicio_id": i.servicio_id,
        "folio": servicio.folio if servicio else None,
        "tipo": servicio.tipo.value if servicio else None,
        "jornada_id": i.jornada_id,
        "fecha": i.fecha.isoformat(),
        "gravedad": i.gravedad.value, "descripcion": i.descripcion,
        "registrada_por": registro.nombre if registro else None,
        "creada_en": i.creada_en.isoformat() if i.creada_en else None,
        "autorizada": i.autorizada,
        "pendiente_visto_bueno": i.visto_bueno_por_id is None,
        "estado": ("pendiente" if i.visto_bueno_por_id is None
                   else "autorizada" if i.autorizada else "descartada"),
        "visto_bueno_por": firmo.nombre if firmo else None,
        "visto_bueno_en": i.visto_bueno_en.isoformat() if i.visto_bueno_en else None,
        "resolucion": i.resolucion_direccion,
    }


# ------------------------------------------------- el visto bueno de una

def aplicar_visto_bueno(db: Session, incidencia: m.Incidencia) -> dict:
    """Lo que mueve el visto bueno del director de operaciones, ademas
    de la incidencia misma (decision 2 de Salvador, seccion 105).

    Hasta aqui el visto bueno contestaba "hay que recalcular la
    evaluacion" y nadie la recalculaba: la tarea del dia 3 corre una
    vez, la consola no tenia boton, y RRHH autorizaba el bono completo
    de alguien con una incidencia leve firmada el dia 4. Ahora:

      - autorizada y leve o grave: si el mes ya tiene su evaluacion y
        sigue CALCULADA, se vuelve a calcular aqui mismo y sale en cero;
        si RRHH ya la autorizo --o ya se pago-- no se toca (el bono es
        dinero) y se dice; si todavia no hay evaluacion, la tarea del
        dia 3 la leera cuando corra.
      - autorizada y grave: la comision del consultor que ya se genero y
        no ha entrado a un corte se retiene, y RRHH recibe el aviso.
      - descartada, o error menor: no toca bono ni comision.

    Devuelve lo que paso, para que el router lo diga en la respuesta.
    Quien llama guarda; lo unico que confirma por su cuenta es el
    recalculo, porque `evaluar` guarda al terminar.
    """
    from app import comisiones

    salida = {"bono": "no_aplica", "evaluacion": None,
              "comisiones_retenidas": [], "aviso_rrhh": 0}
    if not incidencia.autorizada:
        salida["bono"] = "descartada"
        return salida
    if incidencia.gravedad == m.GravedadIncidencia.ERROR_MENOR:
        return salida

    # `evaluar` lee las incidencias con visto bueno de la base: la
    # sesion no vacia sola (autoflush apagado) y sin esto leeria la
    # incidencia todavia sin firma.
    db.flush()
    anio, mes = incidencia.fecha.year, incidencia.fecha.month
    evaluacion = (db.query(m.EvaluacionMensual)
                  .filter_by(persona_id=incidencia.persona_id, anio=anio,
                             mes=mes).first())
    if evaluacion is None:
        salida["bono"] = "sin_evaluacion"
    elif evaluacion.estatus != m.EstatusEvaluacion.CALCULADA:
        salida["bono"] = "ya_autorizado"
        salida["evaluacion"] = _resumen(evaluacion)
    else:
        try:
            evaluacion = evaluar(db, incidencia.persona_id, anio, mes)
            salida["bono"] = "recalculado"
        except HTTPException as error:
            # Un pais que se quedo sin criterios no puede detener la
            # firma: la incidencia queda autorizada y se dice que el
            # bono no se pudo recalcular.
            salida["bono"] = "no_recalculado"
            salida["motivo"] = (error.detail if isinstance(error.detail, str)
                                else str(error.detail))
        salida["evaluacion"] = _resumen(evaluacion)

    if incidencia.gravedad == m.GravedadIncidencia.GRAVE:
        salida["comisiones_retenidas"] = comisiones.retener_por_incidencia(
            db, incidencia)
        salida["aviso_rrhh"] = avisar_grave_a_rrhh(
            db, incidencia, salida["comisiones_retenidas"])
    return salida


def _resumen(evaluacion: m.EvaluacionMensual) -> dict:
    return {"evaluacion_id": evaluacion.id,
            "periodo": f"{evaluacion.mes:02d}/{evaluacion.anio}",
            "anio": evaluacion.anio, "mes": evaluacion.mes,
            "estatus": evaluacion.estatus.value,
            "bono": evaluacion.monto_bono,
            "anulado_por_incidencia": evaluacion.anulado_por_incidencia}


def avisar_grave_a_rrhh(db: Session, incidencia: m.Incidencia,
                        retenidas: list | None = None) -> int:
    """La grave autorizada le llega a Recursos Humanos, por correo y al
    telefono (seccion 105): es quien la gestiona --puede derivar en
    baja-- y hasta aqui se enteraba, si acaso, por el bono en cero.

    A todos los de RRHH con acceso, en el idioma de su pais, como los
    demas avisos a la gente de la casa. Un aviso que no sale no deshace
    la firma. Devuelve a cuantos se les escribio.
    """
    from app import acceso_por_correo, correo_html, push
    from app import textos_aviso as ta

    persona = db.get(m.Persona, incidencia.persona_id)
    servicio = (db.get(m.Servicio, incidencia.servicio_id)
                if incidencia.servicio_id else None)
    registro = db.get(m.Persona, incidencia.clasificada_por_id)
    firmo = (db.get(m.Persona, incidencia.visto_bueno_por_id)
             if incidencia.visto_bueno_por_id else None)
    quien = persona.nombre if persona else f"#{incidencia.persona_id}"
    folio = servicio.folio if servicio else "-"
    avisados = 0
    for usuario in (db.query(m.Usuario)
                    .filter(m.Usuario.rol == m.Rol.RECURSOS_HUMANOS,
                            m.Usuario.activo.is_(True))
                    .order_by(m.Usuario.id).all()):
        if not usuario.correo:
            continue
        lengua = acceso_por_correo.idioma_de(usuario)
        asunto = ta.t(lengua, "inc_grave_asunto", quien=quien, folio=folio)
        cuerpo = ta.t(lengua, "inc_grave_cuerpo", quien=quien, folio=folio,
                      fecha=f"{incidencia.fecha:%d/%m/%Y}")
        pares = [
            (ta.t(lengua, "quien"), quien),
            (ta.t(lengua, "enc_servicio"), folio),
            (ta.t(lengua, "fecha"), f"{incidencia.fecha:%d/%m/%Y}"),
            (ta.t(lengua, "inc_descripcion"), incidencia.descripcion),
            (ta.t(lengua, "inc_registro"), registro.nombre if registro else "-"),
            (ta.t(lengua, "inc_resolucion"),
             f"{incidencia.resolucion_direccion or '-'}"
             + (f" ({firmo.nombre})" if firmo else "")),
            (ta.t(lengua, "inc_comision"),
             ta.t(lengua, "inc_comision_retenida")
             if retenidas else ta.t(lengua, "inc_comision_al_cerrar")),
        ]
        enlace = f"/consola/#/equipo/{incidencia.persona_id}"
        db.add(m.Notificacion(
            servicio_id=incidencia.servicio_id,
            destinatario=m.Destinatario.COLABORADOR, canal=m.Canal.CORREO,
            correo=usuario.correo, idioma=lengua, asunto=asunto[:200],
            cuerpo=cuerpo[:2000], datos=correo_html.guardar_datos(pares),
            enlace_seguimiento=enlace))
        if usuario.persona_id:
            try:
                push.avisar(db, usuario.persona_id, asunto, cuerpo,
                            url=enlace, etiqueta=f"incidencia-{incidencia.id}",
                            urgente=True)
            except Exception:                     # noqa: BLE001
                pass
        avisados += 1
    return avisados


def ficha(db: Session, evaluacion: m.EvaluacionMensual) -> dict:
    incidencia = (db.get(m.Incidencia, evaluacion.incidencia_id)
                  if evaluacion.incidencia_id else None)
    return {
        "persona": evaluacion.persona.nombre,
        "periodo": f"{evaluacion.mes:02d}/{evaluacion.anio}",
        "jornadas_evaluadas": evaluacion.jornadas_evaluadas,
        "estrellas": evaluacion.estrellas,
        "bono": evaluacion.monto_bono,
        "moneda": evaluacion.moneda.value,
        "estatus": evaluacion.estatus.value,
        "anulado_por_incidencia": evaluacion.anulado_por_incidencia,
        "incidencia": ({"gravedad": incidencia.gravedad.value,
                        "fecha": incidencia.fecha.isoformat(),
                        "descripcion": incidencia.descripcion}
                       if incidencia else None),
        "estrellas_posibles": sum(1 for r in evaluacion.detalle if r.aplica),
        "criterios": [{
            "criterio": r.criterio.nombre,
            "aplica": r.aplica,
            "medido": float(r.valor_medido),
            "umbral": float(r.umbral),
            "cumplido": r.cumplido,
            "monto": r.monto,
            # Lo que vale el criterio en el catalogo, al lado de lo que
            # pago. Sin los dos numeros juntos no se puede ver el
            # reparto: un criterio que cobra mas de lo que vale esta
            # recibiendo lo de otro que no aplico, y eso hay que poder
            # mirarlo --en la pantalla y en las pruebas.
            "monto_mensual": r.criterio.monto_mensual,
            "detalle": r.detalle,
        } for r in evaluacion.detalle],
    }

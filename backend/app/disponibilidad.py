"""Motor de disponibilidad de recursos.

Reglas de negocio:
  - Un full day bloquea el dia completo del recurso.
  - Medio dia y transfer trabajan por ventana; se pueden encadenar
    (dos o tres transfers al dia si los horarios lo permiten).
  - Entre el fin de un servicio y el inicio del siguiente debe haber
    de dos a tres horas de holgura.
  - Empalme real de horarios  -> BLOQUEO DURO.
  - Separacion insuficiente   -> ALERTA DE RIESGO; decide el consultor.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app import models as m
from app import profesionalismo

HOLGURA_MINIMA_HORAS = 2.0


@dataclass
class Hallazgo:
    nivel: str                 # "bloqueo" | "riesgo"
    motivo: str
    jornada_id: int
    servicio_folio: str
    inicio: datetime
    fin: datetime
    holgura_horas: float | None = None

    def como_dict(self) -> dict:
        return {
            "nivel": self.nivel,
            "motivo": self.motivo,
            "jornada_id": self.jornada_id,
            "servicio": self.servicio_folio,
            "inicio": self.inicio.isoformat(),
            "fin": self.fin.isoformat(),
            "holgura_horas": self.holgura_horas,
        }


def _jornadas_de_persona(db: Session, persona_id: int, desde: datetime, hasta: datetime):
    """Jornadas vivas de la persona en la ventana ampliada (un dia de margen).

    El dia del que la RELEVARON deja de ocuparle la tarde: se releva a
    alguien a las seis y a las siete ya esta libre, pero su asignacion
    sigue ahi --y tiene que seguir, porque ese dia lo trabajo y se le
    paga--. Mirando solo la asignacion, quien salio de un servicio por
    contingencia quedaba ocupado hasta la medianoche y no se le podia
    poner en otro lado. Por eso la jornada viaja con la hora en que
    termino DE VERDAD para esa persona.
    """
    filas = (
        db.query(m.Jornada, m.AsignacionPersonal.relevado_en)
        .join(m.AsignacionPersonal, m.AsignacionPersonal.jornada_id == m.Jornada.id)
        .filter(
            m.AsignacionPersonal.persona_id == persona_id,
            m.Jornada.estatus != m.EstatusJornada.CANCELADA,
            m.Jornada.fecha >= (desde - timedelta(days=1)).date(),
            m.Jornada.fecha <= (hasta + timedelta(days=1)).date(),
        )
        .all()
    )
    return [(j, relevado) for j, relevado in filas]


# Lo que `_evaluar` lee de cada jornada, cargado de una vez (seccion
# 101): el folio del servicio y si la modalidad bloquea el dia. Sin
# esto, cada jornada de cada persona iba a la base por su equipo, su
# servicio y su modalidad al calcular las recomendaciones.
_CON_LO_QUE_LEE = (joinedload(m.Jornada.equipo).joinedload(m.Equipo.servicio),
                   joinedload(m.Jornada.modalidad))


def _jornadas_de_personas(db: Session, persona_ids: list[int],
                          desde: datetime, hasta: datetime) -> dict[int, list]:
    """Las jornadas vivas de VARIAS personas en la ventana ampliada, en
    una sola consulta: persona -> [(jornada, relevado_en)]. Es lo que
    `_jornadas_de_persona` hace para una; las recomendaciones del equipo
    lo pedian persona por persona y dia por dia (seccion 101)."""
    if not persona_ids:
        return {}
    filas = (
        db.query(m.AsignacionPersonal.persona_id, m.Jornada,
                 m.AsignacionPersonal.relevado_en)
        .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
        .filter(
            m.AsignacionPersonal.persona_id.in_(persona_ids),
            m.Jornada.estatus != m.EstatusJornada.CANCELADA,
            m.Jornada.fecha >= (desde - timedelta(days=1)).date(),
            m.Jornada.fecha <= (hasta + timedelta(days=1)).date(),
        )
        .options(*_CON_LO_QUE_LEE)
        .all()
    )
    salida: dict[int, list] = {}
    for persona_id, j, relevado in filas:
        salida.setdefault(persona_id, []).append((j, relevado))
    return salida


def _jornadas_de_vehiculos(db: Session, vehiculo_ids: list[int],
                           desde: datetime, hasta: datetime) -> dict[int, list]:
    """Igual, para varias unidades: unidad -> [(jornada, relevado_en)]."""
    if not vehiculo_ids:
        return {}
    filas = (
        db.query(m.AsignacionVehiculo.vehiculo_id, m.Jornada,
                 m.AsignacionVehiculo.relevado_en)
        .join(m.Jornada, m.AsignacionVehiculo.jornada_id == m.Jornada.id)
        .filter(
            m.AsignacionVehiculo.vehiculo_id.in_(vehiculo_ids),
            m.Jornada.estatus != m.EstatusJornada.CANCELADA,
            m.Jornada.fecha >= (desde - timedelta(days=1)).date(),
            m.Jornada.fecha <= (hasta + timedelta(days=1)).date(),
        )
        .options(*_CON_LO_QUE_LEE)
        .all()
    )
    salida: dict[int, list] = {}
    for vehiculo_id, j, relevado in filas:
        salida.setdefault(vehiculo_id, []).append((j, relevado))
    return salida


def _en_la_ventana(ocupadas: list, desde: datetime, hasta: datetime) -> list:
    """De lo traido para varios dias, lo que cae en la ventana ampliada
    de UN dia: el mismo recorte que hace la consulta de una persona."""
    piso = (desde - timedelta(days=1)).date()
    techo = (hasta + timedelta(days=1)).date()
    return [(j, relevado) for j, relevado in ocupadas
            if piso <= j.fecha <= techo]


def _jornadas_de_vehiculo(db: Session, vehiculo_id: int, desde: datetime, hasta: datetime):
    """Igual que las de la persona: la unidad que salio a media jornada
    por contingencia queda libre desde la hora en que salio (seccion
    98). Antes se contaba ocupada el dia entero."""
    filas = (
        db.query(m.Jornada, m.AsignacionVehiculo.relevado_en)
        .join(m.AsignacionVehiculo, m.AsignacionVehiculo.jornada_id == m.Jornada.id)
        .filter(
            m.AsignacionVehiculo.vehiculo_id == vehiculo_id,
            m.Jornada.estatus != m.EstatusJornada.CANCELADA,
            m.Jornada.fecha >= (desde - timedelta(days=1)).date(),
            m.Jornada.fecha <= (hasta + timedelta(days=1)).date(),
        )
        .all()
    )
    return [(j, relevado) for j, relevado in filas]


def _evaluar(
    ocupadas: list[m.Jornada],
    inicio: datetime,
    fin: datetime,
    bloquea_dia: bool,
    excluir_jornada_id: int | None,
    holgura_minima: float,
) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []

    for j, relevado_en in ocupadas:
        if excluir_jornada_id and j.id == excluir_jornada_id:
            continue

        folio = j.equipo.servicio.folio

        # A que hora termino ese dia PARA ESTA PERSONA.
        #
        # Dos cosas lo acortan. El relevo: lo que ocupa es hasta que la
        # relevaron, no hasta el fin programado del servicio, que siguio
        # sin ella. Y el cierre: un dia que ya termino --con su hora
        # real de fin marcada-- deja de ocupar a partir de ahi. Sin
        # esto, quien hizo un transfer de 14:00 a 17:00 quedaba ocupado
        # hasta la medianoche y no se le podia poner en nada mas esa
        # tarde, aunque el servicio ya estuviera cerrado.
        cerrada = j.estatus == m.EstatusJornada.TERMINADA
        suyo_termina = relevado_en or (j.fin_real if cerrada else None) \
            or j.fin_programado
        # La relevaron antes de que empezara: ese dia no le ocupa nada.
        if relevado_en and relevado_en <= j.inicio_programado:
            continue

        # 1. Empalme real de horarios: nadie puede estar en dos lugares.
        if inicio < suyo_termina and j.inicio_programado < fin:
            hallazgos.append(Hallazgo(
                nivel="bloqueo",
                motivo="Empalme de horarios con otro servicio",
                jornada_id=j.id, servicio_folio=folio,
                inicio=j.inicio_programado, fin=j.fin_programado,
            ))
            continue

        # Holgura entre ventanas contiguas.
        if suyo_termina <= inicio:
            holgura = (inicio - suyo_termina).total_seconds() / 3600
        else:
            holgura = (j.inicio_programado - fin).total_seconds() / 3600

        hay_full_day = bloquea_dia or j.modalidad.bloquea_dia_completo

        # 2. Full day y mismo dia de presentacion: es el mismo dia
        #    contratado.
        #
        #    Deja de ser bloqueo cuando ese dia ya se cerro o la
        #    relevaron: entonces no es imposible, es un dato que el
        #    consultor tiene que ver --le esta vendiendo un dia completo
        #    a alguien que esa mañana ya dio horas a otro cliente-- y el
        #    decide si lo fuerza. Decision de Salvador, 20 sep.
        if hay_full_day and j.fecha == inicio.date():
            cual = "la nueva jornada" if bloquea_dia else "la jornada ya asignada"
            libre = cerrada or bool(relevado_en)
            hallazgos.append(Hallazgo(
                nivel="riesgo" if libre else "bloqueo",
                motivo=(f"Full day: ya trabajo ese dia en {folio} "
                        f"(hasta las {suyo_termina:%H:%M}). Se le vende el "
                        f"dia completo a otro cliente."
                        if libre else
                        f"Full day: {cual} ocupa el dia completo del recurso"),
                jornada_id=j.id, servicio_folio=folio,
                inicio=j.inicio_programado, fin=j.fin_programado,
            ))
            continue

        # 3. Full day nocturno que cruza la medianoche: son dias distintos y se
        #    cobran por separado, asi que solo se alerta y decide el consultor.
        if (hay_full_day and not relevado_en and not cerrada
                and ({inicio.date(), fin.date()}
                     & {j.fecha, j.fin_programado.date()})):
            hallazgos.append(Hallazgo(
                nivel="riesgo",
                motivo=(f"Jornada nocturna que cruza la medianoche: el recurso encadena "
                        f"dos dias con {holgura:.1f} h de descanso entre ellos. "
                        f"Se cobran como dias distintos."),
                jornada_id=j.id, servicio_folio=folio,
                inicio=j.inicio_programado, fin=j.fin_programado,
                holgura_horas=round(holgura, 2),
            ))
            continue

        # 4. Separacion insuficiente entre ventanas.
        if holgura < holgura_minima:
            hallazgos.append(Hallazgo(
                nivel="riesgo",
                motivo=(f"Solo {holgura:.1f} h entre servicios "
                        f"(minimo recomendado {holgura_minima:.0f} h). "
                        f"Verificar distancia entre puntos."),
                jornada_id=j.id, servicio_folio=folio,
                inicio=j.inicio_programado, fin=j.fin_programado,
                holgura_horas=round(holgura, 2),
            ))

    return hallazgos


def revisar_persona(
    db: Session, persona_id: int, inicio: datetime, fin: datetime,
    bloquea_dia: bool, excluir_jornada_id: int | None = None,
    holgura_minima: float = HOLGURA_MINIMA_HORAS,
) -> list[Hallazgo]:
    ocupadas = _jornadas_de_persona(db, persona_id, inicio, fin)
    return _evaluar(ocupadas, inicio, fin, bloquea_dia, excluir_jornada_id, holgura_minima)


def revisar_vehiculo(
    db: Session, vehiculo_id: int, inicio: datetime, fin: datetime,
    bloquea_dia: bool, excluir_jornada_id: int | None = None,
    holgura_minima: float = HOLGURA_MINIMA_HORAS,
) -> list[Hallazgo]:
    ocupadas = _jornadas_de_vehiculo(db, vehiculo_id, inicio, fin)
    return (_en_el_taller(db, vehiculo_id, inicio, fin)
            + _evaluar(ocupadas, inicio, fin, bloquea_dia,
                       excluir_jornada_id, holgura_minima))


def de_la_jornada(db: Session, jornada: m.Jornada, inicio: datetime,
                  fin: datetime, bloquea_dia: bool) -> tuple[list, list]:
    """Los choques de la gente y las unidades YA asignadas a esa jornada
    si su ventana pasara a ser (inicio, fin): (bloqueos, riesgos), cada
    uno con quien choca y la fecha del dia.

    Mover un dia --la fecha, la modalidad, la hora o el vuelo que fija
    la presentacion-- no volvia a revisar los empalmes (seccion 101):
    Juan quedaba en dos servicios el mismo dia sin bloqueo ni alerta.
    Se revisa igual que al asignar, sin contar el propio dia.
    """
    bloqueos, riesgos = [], []

    def _anotar(hallazgos, quien):
        for h in hallazgos:
            destino = bloqueos if h.nivel == "bloqueo" else riesgos
            destino.append({**h.como_dict(), "quien": quien,
                            "fecha": inicio.date().isoformat()})

    for a in jornada.personal:
        if a.relevado_en:
            continue
        _anotar(revisar_persona(db, a.persona_id, inicio, fin, bloquea_dia,
                                excluir_jornada_id=jornada.id),
                a.persona.nombre if a.persona else str(a.persona_id))
    for a in jornada.vehiculos:
        if a.relevado_en:
            continue
        _anotar(revisar_vehiculo(db, a.vehiculo_id, inicio, fin, bloquea_dia,
                                 excluir_jornada_id=jornada.id),
                a.vehiculo.placa if a.vehiculo else str(a.vehiculo_id))
    return bloqueos, riesgos


def frenar_si_choca(bloqueos: list, riesgos: list, forzar: bool,
                    que: str) -> None:
    """La misma regla que al asignar: el bloqueo no se mueve; el riesgo
    lo decide el consultor con forzar=true. `que` es lo que se estaba
    haciendo, para el mensaje."""
    from fastapi import HTTPException

    if bloqueos:
        quienes = ", ".join(sorted({b["quien"] for b in bloqueos}))
        raise HTTPException(409, {
            "mensaje": f"No se puede {que}: {quienes} no está libre a "
                       "esa hora",
            "que_hacer": "Cambia a quien choca por contingencia, o mueve "
                         "el día a otra fecha u hora.",
            "alertas": bloqueos,
        })
    if riesgos and not forzar:
        raise HTTPException(409, {
            "mensaje": f"Alerta de riesgo al {que}. Confirme con "
                       "forzar=true para moverlo.",
            "alertas": riesgos,
        })


def _en_el_taller(db: Session, vehiculo_id: int, inicio: datetime,
                  fin: datetime) -> list[Hallazgo]:
    """La unidad en el taller no se ofrece (seccion 52).

    El implantado ya lo respetaba y el eventual no: al asignar un
    eventual, un coche desarmado salia libre, y asi se le promete al
    cliente una unidad que no existe. Sin fecha de salida se da por
    adentro.
    """
    return _taller_en(_taller_de(db, [vehiculo_id], fin).get(vehiculo_id, []),
                      inicio, fin)


def _taller_de(db: Session, vehiculo_ids: list[int],
               hasta: datetime) -> dict[int, list[m.TallerVehiculo]]:
    """Las entradas al taller de varias unidades que empiezan antes de
    `hasta`, en orden: unidad -> [filas]. Cada dia recorta las suyas
    como lo hace `_en_el_taller`."""
    if not vehiculo_ids:
        return {}
    salida: dict[int, list] = {}
    for fila in (db.query(m.TallerVehiculo)
                 .filter(m.TallerVehiculo.vehiculo_id.in_(vehiculo_ids),
                         m.TallerVehiculo.desde <= hasta.date())
                 .order_by(m.TallerVehiculo.desde).all()):
        salida.setdefault(fila.vehiculo_id, []).append(fila)
    return salida


def _taller_en(filas: list, inicio: datetime, fin: datetime) -> list[Hallazgo]:
    salida = []
    for fila in filas:
        if fila.desde > fin.date():
            continue
        if fila.hasta is not None and fila.hasta < inicio.date():
            continue
        hasta = (f"hasta el {fila.hasta:%d/%m}" if fila.hasta
                 else "sin fecha de salida")
        salida.append(Hallazgo(
            nivel="bloqueo",
            motivo=f"En el taller desde el {fila.desde:%d/%m}, {hasta}",
            jornada_id=None, servicio_folio=None, inicio=inicio, fin=fin))
    return salida


def recomendar_personal(
    db: Session, plaza_id: int, perfil_id: int | None,
    inicio: datetime, fin: datetime, bloquea_dia: bool,
) -> dict:
    """Recomienda por plaza y disponibilidad para un dia.

    Ya no se filtra por puesto: el personal de seguridad es general y el
    rol lo decide el consultor al asignar. Quien esta libre es candidato
    para cualquiera de los cuatro roles, y el sistema dejo de decidir
    quien puede ser que.

    Si no hay recurso local libre, avisa para trasladar personal o dar de
    alta freelance."""
    return recomendar_personal_por_dia(
        db, plaza_id, perfil_id, [(inicio, fin, bloquea_dia)])[0]


def recomendar_personal_por_dia(
    db: Session, plaza_id: int, perfil_id: int | None,
    dias: list[tuple[datetime, datetime, bool]],
) -> list[dict]:
    """Lo mismo, para varios dias de un golpe: una respuesta por dia, en
    el mismo orden.

    Lo caro se hace una vez para todos los dias y todas las personas
    (seccion 101): la ficha de profesionalismo por lote y una sola
    consulta con las jornadas de todos en la ventana que cubre los
    dias. Antes cada dia pedia la ficha de cada persona otra vez.
    """
    todos = (
        db.query(m.Persona)
        # La gente de oficina que llega de Odoo (seccion 74) no va a la
        # calle: no se le ofrece a ningun equipo.
        .filter(m.Persona.activo.is_(True), m.Persona.oficina.is_(False))
        .options(joinedload(m.Persona.plaza))
        .all()
    )
    candidatos = [p for p in todos if p.plaza_id == plaza_id]
    otras_ciudades = [p for p in todos if p.plaza_id != plaza_id]
    ids = [p.id for p in todos]
    ocupadas = _jornadas_de_personas(
        db, ids, min(d[0] for d in dias), max(d[1] for d in dias))
    # La calificacion de profesionalismo entra aqui: entre dos personas
    # igual de libres, el consultor debe poder ver a quien conviene
    # mandar sin salirse de la pantalla.
    tableros = profesionalismo.fichas(db, ids)

    salida = []
    for inicio, fin, bloquea_dia in dias:
        def _ficha(p) -> dict:
            hallazgos = _evaluar(
                _en_la_ventana(ocupadas.get(p.id, []), inicio, fin),
                inicio, fin, bloquea_dia, None, HOLGURA_MINIMA_HORAS)
            tablero = tableros.get(p.id, {})
            return {"persona_id": p.id, "nombre": p.nombre,
                    "es_freelance": p.es_freelance,
                    "ciudad": p.plaza.nombre if p.plaza else None,
                    "local": p.plaza_id == plaza_id,
                    "telefono": p.telefono,
                    "calificacion": tablero.get("calificacion"),
                    "confianza_calificacion": tablero.get("confianza"),
                    "horas_en_centauro": tablero.get("horas_en_centauro"),
                    "bloqueado": any(h.nivel == "bloqueo" for h in hallazgos),
                    "alertas": [h.como_dict() for h in hallazgos]}

        libres, con_riesgo, ocupados = [], [], []
        for p in candidatos:
            ficha = _ficha(p)
            if ficha["bloqueado"]:
                ocupados.append(ficha)
            elif ficha["alertas"]:
                con_riesgo.append(ficha)
            else:
                libres.append(ficha)

        aviso = None
        if not libres and not con_riesgo:
            aviso = ("Sin recurso local disponible en la plaza. "
                     "Se requiere traslado de personal (genera viaticos extra) "
                     "o alta de un freelance.")

        # Mejor calificado primero, dentro de cada grupo.
        for grupo in (libres, con_riesgo):
            grupo.sort(key=lambda f: f.get("calificacion") or 0, reverse=True)

        # Quien esta en otra ciudad tambien se puede mandar: es el traslado
        # que genera viaticos foraneos. Se muestra aparte para que el
        # consultor vea que esta pagando por traerlo, no revuelto con los
        # locales.
        foraneos = [_ficha(p) for p in otras_ciudades]
        foraneos.sort(key=lambda f: (f["bloqueado"], -(f.get("calificacion") or 0)))

        salida.append({"disponibles": libres, "con_alerta": con_riesgo,
                       "no_disponibles": ocupados,
                       "de_otras_ciudades": foraneos, "aviso": aviso})
    return salida


def recomendar_vehiculos(
    db: Session, plaza_id: int, categoria_id: int,
    inicio: datetime, fin: datetime, bloquea_dia: bool,
    servicio_id: int | None = None,
) -> dict:
    return recomendar_vehiculos_por_dia(
        db, plaza_id, categoria_id, [(inicio, fin, bloquea_dia)],
        servicio_id=servicio_id)[0]


def recomendar_vehiculos_por_dia(
    db: Session, plaza_id: int, categoria_id: int,
    dias: list[tuple[datetime, datetime, bool]],
    servicio_id: int | None = None,
) -> list[dict]:
    """Una respuesta por dia, con las jornadas y el taller de todas las
    unidades traidos de una vez (seccion 101)."""
    # La flota propia siempre, y de los autos rentados solo los de este
    # servicio: se pidieron para el y se devuelven al terminarlo, asi que
    # ofrecerlos en otro seria prometer un auto que ya no esta.
    todas = (
        db.query(m.Vehiculo)
        .filter(m.Vehiculo.categoria_id == categoria_id,
                m.Vehiculo.activo.is_(True),
                or_(m.Vehiculo.rentado.is_(False),
                    m.Vehiculo.servicio_id == servicio_id))
        .options(joinedload(m.Vehiculo.categoria), joinedload(m.Vehiculo.plaza))
        .all()
    )
    candidatos = [v for v in todas if v.plaza_id == plaza_id]
    # Las de otra ciudad, solo de este pais (seccion 118): una camioneta
    # de Sao Paulo no se manda a la Ciudad de Mexico. Aqui entran tambien
    # las que todavia no tienen ciudad --la flota de Brasil llega de Odoo
    # sin Ubicacion-- dichas asi.
    plaza = db.get(m.Plaza, plaza_id)
    pais_id = plaza.pais_id if plaza else None
    otras_ciudades = [v for v in todas if v.plaza_id != plaza_id
                      and (pais_id is None or v.pais_de_la_unidad == pais_id)]
    todas = candidatos + otras_ciudades
    ids = [v.id for v in todas]
    techo = max(d[1] for d in dias)
    ocupadas = _jornadas_de_vehiculos(db, ids, min(d[0] for d in dias), techo)
    taller = _taller_de(db, ids, techo)

    salida = []
    for inicio, fin, bloquea_dia in dias:
        def _ficha(v) -> dict:
            hallazgos = (_taller_en(taller.get(v.id, []), inicio, fin)
                         + _evaluar(_en_la_ventana(ocupadas.get(v.id, []),
                                                   inicio, fin),
                                    inicio, fin, bloquea_dia, None,
                                    HOLGURA_MINIMA_HORAS))
            return {"vehiculo_id": v.id, "placa": v.placa,
                    "unidad": v.categoria.nombre if v.categoria else None,
                    "blindada": v.categoria.blindado if v.categoria else None,
                    "color": v.color, "anio": v.modelo_anio,
                    "marca_modelo": v.marca_modelo,
                    "rentado": v.rentado, "arrendadora": v.arrendadora,
                    "ciudad": v.plaza.nombre if v.plaza else None,
                    "local": v.plaza_id == plaza_id,
                    "sin_ciudad": v.plaza_id is None,
                    "bloqueado": any(h.nivel == "bloqueo" for h in hallazgos),
                    "alertas": [h.como_dict() for h in hallazgos]}

        libres, con_riesgo, ocupados = [], [], []
        for v in candidatos:
            ficha = _ficha(v)
            if ficha["bloqueado"]:
                ocupados.append(ficha)
            elif ficha["alertas"]:
                con_riesgo.append(ficha)
            else:
                libres.append(ficha)

        aviso = None if (libres or con_riesgo) else \
            "Sin unidad disponible de esa categoria en la plaza."

        # Mejor calificado primero, dentro de cada grupo.
        for grupo in (libres, con_riesgo):
            grupo.sort(key=lambda f: f.get("calificacion") or 0, reverse=True)

        foraneas = [_ficha(v) for v in otras_ciudades]
        foraneas.sort(key=lambda f: f["bloqueado"])

        salida.append({"disponibles": libres, "con_alerta": con_riesgo,
                       "no_disponibles": ocupados,
                       "de_otras_ciudades": foraneas, "aviso": aviso})
    return salida

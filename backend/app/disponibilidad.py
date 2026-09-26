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
from sqlalchemy.orm import Session

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


def _jornadas_de_vehiculo(db: Session, vehiculo_id: int, desde: datetime, hasta: datetime):
    """Igual que las de la persona, pero la unidad no se releva a media
    jornada: si cambia, cambia el dia entero."""
    return [(j, None) for j in (
        db.query(m.Jornada)
        .join(m.AsignacionVehiculo, m.AsignacionVehiculo.jornada_id == m.Jornada.id)
        .filter(
            m.AsignacionVehiculo.vehiculo_id == vehiculo_id,
            m.Jornada.estatus != m.EstatusJornada.CANCELADA,
            m.Jornada.fecha >= (desde - timedelta(days=1)).date(),
            m.Jornada.fecha <= (hasta + timedelta(days=1)).date(),
        )
        .all())]


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


def _en_el_taller(db: Session, vehiculo_id: int, inicio: datetime,
                  fin: datetime) -> list[Hallazgo]:
    """La unidad en el taller no se ofrece (seccion 52).

    El implantado ya lo respetaba y el eventual no: al asignar un
    eventual, un coche desarmado salia libre, y asi se le promete al
    cliente una unidad que no existe. Sin fecha de salida se da por
    adentro.
    """
    salida = []
    for fila in (db.query(m.TallerVehiculo)
                 .filter(m.TallerVehiculo.vehiculo_id == vehiculo_id,
                         m.TallerVehiculo.desde <= fin.date())
                 .order_by(m.TallerVehiculo.desde).all()):
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
    """Recomienda por plaza y disponibilidad.

    Ya no se filtra por puesto: el personal de seguridad es general y el
    rol lo decide el consultor al asignar. Quien esta libre es candidato
    para cualquiera de los cuatro roles, y el sistema dejo de decidir
    quien puede ser que.

    Si no hay recurso local libre, avisa para trasladar personal o dar de
    alta freelance."""
    todos = (
        db.query(m.Persona)
        # La gente de oficina que llega de Odoo (seccion 74) no va a la
        # calle: no se le ofrece a ningun equipo.
        .filter(m.Persona.activo.is_(True), m.Persona.oficina.is_(False))
        .all()
    )
    candidatos = [p for p in todos if p.plaza_id == plaza_id]
    otras_ciudades = [p for p in todos if p.plaza_id != plaza_id]

    def _ficha(p) -> dict:
        hallazgos = revisar_persona(db, p.id, inicio, fin, bloquea_dia)
        # La calificacion de profesionalismo entra aqui: entre dos personas
        # igual de libres, el consultor debe poder ver a quien conviene
        # mandar sin salirse de la pantalla.
        tablero = profesionalismo.ficha(db, p.id)
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
    # que genera viaticos foraneos. Se muestra aparte para que el consultor
    # vea que esta pagando por traerlo, no revuelto con los locales.
    foraneos = [_ficha(p) for p in otras_ciudades]
    foraneos.sort(key=lambda f: (f["bloqueado"], -(f.get("calificacion") or 0)))

    return {"disponibles": libres, "con_alerta": con_riesgo,
            "no_disponibles": ocupados, "de_otras_ciudades": foraneos,
            "aviso": aviso}


def recomendar_vehiculos(
    db: Session, plaza_id: int, categoria_id: int,
    inicio: datetime, fin: datetime, bloquea_dia: bool,
    servicio_id: int | None = None,
) -> dict:
    # La flota propia siempre, y de los autos rentados solo los de este
    # servicio: se pidieron para el y se devuelven al terminarlo, asi que
    # ofrecerlos en otro seria prometer un auto que ya no esta.
    todas = (
        db.query(m.Vehiculo)
        .filter(m.Vehiculo.categoria_id == categoria_id,
                m.Vehiculo.activo.is_(True),
                or_(m.Vehiculo.rentado.is_(False),
                    m.Vehiculo.servicio_id == servicio_id))
        .all()
    )
    candidatos = [v for v in todas if v.plaza_id == plaza_id]
    otras_ciudades = [v for v in todas if v.plaza_id != plaza_id]

    def _ficha(v) -> dict:
        hallazgos = revisar_vehiculo(db, v.id, inicio, fin, bloquea_dia)
        return {"vehiculo_id": v.id, "placa": v.placa,
                "unidad": v.categoria.nombre if v.categoria else None,
                "blindada": v.categoria.blindado if v.categoria else None,
                "color": v.color, "anio": v.modelo_anio,
                "marca_modelo": v.marca_modelo,
                "rentado": v.rentado, "arrendadora": v.arrendadora,
                "ciudad": v.plaza.nombre if v.plaza else None,
                "local": v.plaza_id == plaza_id,
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

    return {"disponibles": libres, "con_alerta": con_riesgo,
            "no_disponibles": ocupados, "de_otras_ciudades": foraneas,
            "aviso": aviso}

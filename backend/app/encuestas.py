"""Encuestas de satisfaccion al cierre del servicio.

Dos encuestas distintas y cortas a proposito: nadie contesta un
cuestionario largo. Al ejecutivo se le pregunta una sola cosa y solo se
profundiza si algo salio mal; al solicitante se le pregunta por el
consultor que lo atendio.

Regla de negocio que atraviesa todo el modulo: una mala calificacion NO
baja el bono por si sola. Abre una revision que clasifica el consultor,
igual que una incidencia.
"""
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import textos_aviso as ta

DIAS_PARA_RESPONDER = 15
# A los cinco dias, un recordatorio. Uno solo, y despues se deja en paz.
DIAS_PARA_RECORDAR = 5
# Con 3 o menos se considera que algo salio mal y se pregunta que fue.
UMBRAL_MALA = 3

PREGUNTAS = {
    "en": {
        "ejecutivo": {
            "general": "How would you rate the security service you received?",
            "escala": "1 = very poor · 5 = excellent",
            "bien": {"mas_valoro": "What did you value the most?"},
            "mal": {
                "puntualidad": "Was the team on time?",
                "trato": "How was the driver's manner and presentation?",
                "vehiculo": "What condition was the vehicle in?",
                "molestia": "What bothered you the most? Please tell us.",
            },
        },
        "solicitante": {
            "general": "How would you rate the service from your consultant?",
            "escala": "1 = very poor · 5 = excellent",
            "siempre": {
                "respuesta_cotizacion": "How quickly did you get your quote?",
                "claridad": "Was the information clear?",
                "seguimiento": "How was the follow-up during the service?",
            },
            "abierta": {"comentario": "Anything else you want us to know?"},
        },
        "gracias": "Thank you. Your answer goes straight to the operations team.",
    },
    "es": {
        "ejecutivo": {
            "general": "¿Cómo califica el servicio de seguridad que recibió?",
            "escala": "1 = muy malo · 5 = excelente",
            "bien": {"mas_valoro": "¿Qué fue lo que más valoró?"},
            "mal": {
                "puntualidad": "¿El equipo llegó a tiempo?",
                "trato": "¿Cómo fue el trato y la presentación del conductor?",
                "vehiculo": "¿En qué condiciones estaba el vehículo?",
                "molestia": "¿Qué fue lo que más le molestó? Cuéntenos.",
            },
        },
        "solicitante": {
            "general": "¿Cómo califica la atención de su consultor?",
            "escala": "1 = muy malo · 5 = excelente",
            "siempre": {
                "respuesta_cotizacion": "¿Qué tan rápido recibió su cotización?",
                "claridad": "¿La información fue clara?",
                "seguimiento": "¿Cómo fue el seguimiento durante el servicio?",
            },
            "abierta": {"comentario": "¿Algo más que quiera decirnos?"},
        },
        "gracias": "Gracias. Su respuesta llega directo al equipo de operaciones.",
    },
    "pt": {
        "ejecutivo": {
            "general": "Como avalia o serviço de segurança que recebeu?",
            "escala": "1 = muito ruim · 5 = excelente",
            "bien": {"mas_valoro": "O que mais valorizou?"},
            "mal": {
                "puntualidad": "A equipe chegou no horário?",
                "trato": "Como foi o trato e a apresentação do motorista?",
                "vehiculo": "Em que condições estava o veículo?",
                "molestia": "O que mais o incomodou? Conte para nós.",
            },
        },
        "solicitante": {
            "general": "Como avalia o atendimento do seu consultor?",
            "escala": "1 = muito ruim · 5 = excelente",
            "siempre": {
                "respuesta_cotizacion": "Com que rapidez recebeu seu orçamento?",
                "claridad": "A informação foi clara?",
                "seguimiento": "Como foi o acompanhamento durante o serviço?",
            },
            "abierta": {"comentario": "Algo mais que queira nos dizer?"},
        },
        "gracias": "Obrigado. Sua resposta vai direto para a equipe de operações.",
    },
}


def _textos(idioma: str | None) -> dict:
    return PREGUNTAS.get((idioma or "en").lower(), PREGUNTAS["en"])


# ---------------------------------------------------------------- envio

def generar(db: Session, servicio_id: int,
            idioma: str | None = None) -> list[m.Encuesta]:
    """Crea las dos encuestas del servicio. Se corre al cerrarlo.

    Sin `idioma`, cada una sale en el de quien la va a contestar: el
    principal en el suyo --ingles por omision-- y el solicitante en el
    del pais donde se ejecuto el servicio. Antes entraba "en" fijo y se
    equivocaba sola cada vez que el ejecutivo era mexicano.

    `idioma` sigue existiendo para el caso raro en que alguien quiera
    mandarlas a proposito en otro.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    creadas = []
    destinos = [
        (m.TipoEncuesta.EJECUTIVO, servicio.ejecutivo_completo,
         servicio.ejecutivo_correo),
        (m.TipoEncuesta.SOLICITANTE, servicio.solicitante_completo,
         servicio.solicitante_correo),
    ]
    for tipo, nombre, correo in destinos:
        if not correo:
            continue        # sin correo no hay a donde mandarla
        destinatario = (m.Destinatario.EJECUTIVO
                        if tipo == m.TipoEncuesta.EJECUTIVO
                        else m.Destinatario.SOLICITANTE)
        lengua = idioma or ta.idioma_de(db, servicio, destinatario)
        ya = (db.query(m.Encuesta)
              .filter_by(servicio_id=servicio_id, tipo=tipo).first())
        if ya:
            continue        # no se manda dos veces la misma
        encuesta = m.Encuesta(
            servicio_id=servicio_id, tipo=tipo,
            consultor_id=(servicio.consultor_id
                          if tipo == m.TipoEncuesta.SOLICITANTE else None),
            destinatario_nombre=nombre, destinatario_correo=correo,
            idioma=lengua,
            token=secrets.token_urlsafe(24),
            expira_en=datetime.now() + timedelta(days=DIAS_PARA_RESPONDER))
        db.add(encuesta)
        db.flush()
        creadas.append(encuesta)

        db.add(m.Notificacion(
            servicio_id=servicio_id,
            destinatario=destinatario,
            canal=m.Canal.CORREO, correo=correo,
            idioma=lengua,
            asunto=f"{servicio.folio}: {_textos(lengua)[tipo.value]['general']}",
            cuerpo=_textos(lengua)["gracias"],
            enlace_seguimiento=f"/encuestas/pagina/{encuesta.token}",
            # La encuesta tiene su propio correo escrito desde hace
            # meses (encuestas_html.correo): las estrellas se pican
            # desde el mensaje. La plantilla es lo que le dice al
            # despachador que use ese y no el armazon general.
            plantilla="encuesta",
            expira_en=encuesta.expira_en))
    return creadas


# ---------------------------------------------------------------- respuesta

def por_token(db: Session, token: str) -> m.Encuesta:
    encuesta = db.query(m.Encuesta).filter_by(token=token).first()
    if not encuesta:
        raise HTTPException(404, "Esa encuesta no existe")
    if encuesta.estatus == m.EstatusEncuesta.RESPONDIDA:
        raise HTTPException(409, "Esa encuesta ya fue contestada. Gracias.")
    if datetime.now() > encuesta.expira_en:
        if encuesta.estatus != m.EstatusEncuesta.EXPIRADA:
            encuesta.estatus = m.EstatusEncuesta.EXPIRADA
            db.commit()
        raise HTTPException(410, "El enlace de esa encuesta ya vencio")
    return encuesta


def formulario(encuesta: m.Encuesta) -> dict:
    """Lo que ve quien abre el enlace.

    Las ramas van declaradas desde el inicio para que quien la pinte pueda
    abrirlas sin volver a preguntarle al servidor.
    """
    t = _textos(encuesta.idioma)[encuesta.tipo.value]
    base = {
        "servicio": encuesta.servicio.folio,
        "tipo": encuesta.tipo.value,
        "idioma": encuesta.idioma,
        "general": {"pregunta": t["general"], "escala": t["escala"],
                    "min": 1, "max": 5},
    }
    if encuesta.tipo == m.TipoEncuesta.EJECUTIVO:
        base["si_califica_4_o_5"] = t["bien"]
        base["si_califica_3_o_menos"] = t["mal"]
    else:
        base["siempre"] = t["siempre"]
        base["abierta"] = t["abierta"]
    return base


def _preguntas_esperadas(encuesta: m.Encuesta, calificacion: int) -> tuple[set, set]:
    """(obligatorias, permitidas) segun la rama que toca."""
    t = _textos(encuesta.idioma)[encuesta.tipo.value]
    if encuesta.tipo == m.TipoEncuesta.EJECUTIVO:
        if calificacion > UMBRAL_MALA:
            return set(), set(t["bien"])
        # Cuando algo salio mal si se pide el detalle: es la unica
        # oportunidad de saber que arreglar.
        escala = {"puntualidad", "trato", "vehiculo"}
        return escala, escala | {"molestia"}
    permitidas = set(t["siempre"]) | set(t["abierta"])
    return set(t["siempre"]), permitidas


def responder(db: Session, token: str, calificacion: int,
              respuestas: dict) -> dict:
    encuesta = por_token(db, token)
    if not 1 <= calificacion <= 5:
        raise HTTPException(400, "La calificacion va del 1 al 5")

    obligatorias, permitidas = _preguntas_esperadas(encuesta, calificacion)
    sobran = set(respuestas) - permitidas
    if sobran:
        raise HTTPException(400, {
            "mensaje": "Esas preguntas no van en esta encuesta",
            "preguntas": sorted(sobran)})
    faltan = obligatorias - set(respuestas)
    if faltan:
        raise HTTPException(400, {
            "mensaje": "Faltan preguntas por contestar",
            "preguntas": sorted(faltan)})

    encuesta.calificacion = calificacion
    encuesta.estatus = m.EstatusEncuesta.RESPONDIDA
    encuesta.respondida_en = datetime.now()
    # Una mala calificacion abre revision, no castigo automatico.
    encuesta.requiere_clasificacion = calificacion <= UMBRAL_MALA

    for pregunta, valor in respuestas.items():
        if isinstance(valor, int):
            db.add(m.RespuestaEncuesta(encuesta_id=encuesta.id,
                                       pregunta=pregunta, valor=valor))
        else:
            db.add(m.RespuestaEncuesta(encuesta_id=encuesta.id,
                                       pregunta=pregunta,
                                       texto=str(valor)[:1000]))
    db.flush()
    if encuesta.requiere_clasificacion:
        avisar_mala_calificacion(db, encuesta, respuestas)
    return {
        "resultado": "recibida",
        "mensaje": _textos(encuesta.idioma)["gracias"],
        "abre_revision": encuesta.requiere_clasificacion,
    }


def quien_la_revisa(db: Session, encuesta: m.Encuesta) -> m.Persona | None:
    """A quien le toca clasificar esta mala calificacion.

    La del ejecutivo califica el servicio y al equipo: es del consultor
    que lo llevo. La del solicitante califica AL CONSULTOR, y ahi el
    consultor no puede ser quien decide si eso amerita incidencia --seria
    juez y parte--: esa sube a direccion de operaciones.
    """
    if encuesta.tipo == m.TipoEncuesta.SOLICITANTE:
        usuario = (db.query(m.Usuario)
                   .filter(m.Usuario.rol == m.Rol.DIRECTOR_OPERACIONES,
                           m.Usuario.activo.is_(True))
                   .order_by(m.Usuario.id).first())
        return usuario.persona if usuario else None
    # `Servicio` guarda el id del consultor, no la relacion.
    return (db.get(m.Persona, encuesta.servicio.consultor_id)
            if encuesta.servicio.consultor_id else None)


def avisar_mala_calificacion(db: Session, encuesta: m.Encuesta,
                             respuestas: dict) -> dict:
    """Una calificacion baja tiene que llegarle a alguien HOY.

    Un ejecutivo molesto el viernes es una cuenta en riesgo el lunes, y
    hasta ahora la queja se quedaba en una bandeja que nadie abria. Va
    por correo y por telefono: el correo lleva lo que dijo el cliente,
    el aviso del telefono lleva lo suficiente para saber que hay que
    abrirlo.

    Lo que el aviso NO dice: que alguien la rego. Una calificacion baja
    abre una revision, no un castigo, y decirlo al reves desde el
    primer renglon predispone a quien va a clasificarla.
    """
    from app import correo_html, push

    quien = quien_la_revisa(db, encuesta)
    if quien is None:
        return {"avisado": False, "motivo": "nadie a quien avisarle"}

    servicio = encuesta.servicio
    lengua = ta.idioma_de(db, servicio, m.Destinatario.CONSULTOR)
    cliente = encuesta.destinatario_nombre or "El cliente"
    nota = encuesta.calificacion

    # Lo que dijo, tal cual. Las preguntas cerradas y el texto libre van
    # con su pregunta al lado: "3" sin la pregunta no se puede leer.
    #
    # Las dos encuestas no se abren igual --la del ejecutivo en
    # bien/mal, la del solicitante en siempre/abierta-- asi que el
    # diccionario se arma junto en vez de ir a buscar una rama que en
    # la otra no existe.
    bloque = _textos(encuesta.idioma)[encuesta.tipo.value]
    preguntas = {}
    for rama in ("bien", "mal", "siempre", "abierta"):
        preguntas.update(bloque.get(rama, {}))
    dijo = [(preguntas.get(clave, clave), str(valor))
            for clave, valor in respuestas.items()]

    db.add(m.Notificacion(
        servicio_id=servicio.id,
        destinatario=m.Destinatario.CONSULTOR, canal=m.Canal.CORREO,
        correo=quien.correo, idioma=lengua,
        asunto=ta.t(lengua, "enc_mala_asunto", folio=servicio.folio,
                    cliente=cliente, nota=nota),
        cuerpo=ta.t(lengua, "enc_mala_cuerpo", quien=cliente, nota=nota),
        datos=correo_html.guardar_datos(
            [(ta.t(lengua, "enc_servicio"), servicio.folio),
             (ta.t(lengua, "enc_cliente"), cliente),
             (ta.t(lengua, "enc_nota"), f"{nota} / 5")]
            + [(pregunta, respuesta) for pregunta, respuesta in dijo]),
    ))

    push.avisar(
        db, quien.id,
        titulo=f"{servicio.folio}: {nota} de 5",
        cuerpo=f"{cliente} calificó el servicio con {nota}. "
               f"Abre revisión: hay que clasificarla.",
        # Quien revisa esto trabaja en la consola, no en la app de
        # campo: mandarlo al telefono a una pantalla que no es la suya
        # es mandarlo a ningun lado.
        url=f"/consola/#/servicio/{servicio.id}",
        etiqueta="encuesta", urgente=True)
    return {"avisado": True, "persona_id": quien.id}


# ---------------------------------------------------------------- el reloj

def pasar_lista(db: Session, ahora: datetime | None = None) -> dict:
    """Le recuerda a quien no ha contestado, y vence lo que ya paso.

    Sin esto la encuesta se mandaba una vez, al cierre, y ahi se acababa:
    la que nadie contesto se quedaba en "enviada" para siempre --porque
    EXPIRADA solo se escribia si alguien abria el enlace caducado-- y no
    habia forma de saber la tasa de respuesta ni de cerrar un mes.

    Dos cosas, en este orden: primero se vence lo vencido, para no
    mandarle un recordatorio a alguien cuyo enlace ya no sirve.
    """
    ahora = ahora or datetime.now()
    vencidas, recordadas = 0, 0

    abiertas = (db.query(m.Encuesta)
                .filter(m.Encuesta.estatus == m.EstatusEncuesta.ENVIADA).all())
    for encuesta in abiertas:
        if encuesta.expira_en <= ahora:
            encuesta.estatus = m.EstatusEncuesta.EXPIRADA
            vencidas += 1
            continue
        if encuesta.recordada_en is not None:
            continue
        # El plazo se cuenta hacia atras desde la fecha de cierre, no
        # hacia adelante desde el envio. Da el mismo dia --cierre menos
        # diez es envio mas cinco-- y evita un choque real: `expira_en`
        # esta sin zona horaria, igual que el reloj con el que se
        # compara, mientras que `enviada_en` la escribe Postgres CON
        # zona. Sumarle dias a esa y compararla con `ahora` truena.
        aviso_desde = encuesta.expira_en - timedelta(
            days=DIAS_PARA_RESPONDER - DIAS_PARA_RECORDAR)
        if aviso_desde > ahora:
            continue
        if not encuesta.destinatario_correo:
            continue
        recordar(db, encuesta)
        encuesta.recordada_en = ahora
        recordadas += 1

    db.commit()
    return {"vencidas": vencidas, "recordadas": recordadas,
            "abiertas": len(abiertas) - vencidas}


def recordar(db: Session, encuesta: m.Encuesta) -> None:
    """El segundo y ultimo correo. Mismo enlace, misma plantilla.

    No se genera un token nuevo: es la misma encuesta, y dos enlaces
    vivos para lo mismo es la forma mas facil de que alguien conteste
    dos veces.
    """
    servicio = encuesta.servicio
    lengua = encuesta.idioma
    db.add(m.Notificacion(
        servicio_id=servicio.id,
        destinatario=(m.Destinatario.EJECUTIVO
                      if encuesta.tipo == m.TipoEncuesta.EJECUTIVO
                      else m.Destinatario.SOLICITANTE),
        canal=m.Canal.CORREO, correo=encuesta.destinatario_correo,
        idioma=lengua,
        asunto=ta.t(lengua, "enc_rec_asunto", folio=servicio.folio),
        cuerpo=ta.t(lengua, "enc_rec_cuerpo",
                    fecha=f"{encuesta.expira_en:%d/%m}"),
        enlace_seguimiento=f"/encuestas/pagina/{encuesta.token}",
        plantilla="encuesta_recordatorio",
        expira_en=encuesta.expira_en))


# ---------------------------------------------------------------- resumen

def _promedio(valores: list[int]) -> float | None:
    return round(sum(valores) / len(valores), 2) if valores else None


def resumen_de_persona(db: Session, persona_id: int) -> dict:
    """Promedio del ejecutivo en los servicios donde esa persona trabajo.

    Alimenta el tablero de profesionalismo. Es del servicio, no de la
    persona: el ejecutivo califica al equipo, no a cada quien.
    """
    servicios = {
        j.equipo.servicio_id
        for a in db.query(m.AsignacionPersonal).filter_by(persona_id=persona_id)
        for j in [a.jornada]
    }
    if not servicios:
        return {"calificaciones": 0, "promedio": None}

    filas = (db.query(m.Encuesta)
             .filter(m.Encuesta.servicio_id.in_(servicios),
                     m.Encuesta.tipo == m.TipoEncuesta.EJECUTIVO,
                     m.Encuesta.calificacion.isnot(None)).all())
    notas = [f.calificacion for f in filas]
    return {"calificaciones": len(notas), "promedio": _promedio(notas),
            "malas": len([n for n in notas if n <= UMBRAL_MALA])}


def resumen_de_consultor(db: Session, consultor_id: int) -> dict:
    """Como lo califican sus solicitantes, con el desglose por pregunta."""
    filas = (db.query(m.Encuesta)
             .filter_by(tipo=m.TipoEncuesta.SOLICITANTE,
                        consultor_id=consultor_id)
             .filter(m.Encuesta.calificacion.isnot(None)).all())
    notas = [f.calificacion for f in filas]
    detalle = {}
    for encuesta in filas:
        for r in encuesta.respuestas:
            if r.valor is not None:
                detalle.setdefault(r.pregunta, []).append(r.valor)

    return {
        "calificaciones": len(notas),
        "promedio": _promedio(notas),
        "por_pregunta": {k: _promedio(v) for k, v in detalle.items()},
    }

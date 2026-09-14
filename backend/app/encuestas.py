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

DIAS_PARA_RESPONDER = 15
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
            "general": "Como califica el servicio de seguridad que recibio?",
            "escala": "1 = muy malo · 5 = excelente",
            "bien": {"mas_valoro": "Que fue lo que mas valoro?"},
            "mal": {
                "puntualidad": "El equipo llego a tiempo?",
                "trato": "Como fue el trato y la presentacion del conductor?",
                "vehiculo": "En que condiciones estaba el vehiculo?",
                "molestia": "Que fue lo que mas le molesto? Cuentenos.",
            },
        },
        "solicitante": {
            "general": "Como califica la atencion de su consultor?",
            "escala": "1 = muy malo · 5 = excelente",
            "siempre": {
                "respuesta_cotizacion": "Que tan rapido recibio su cotizacion?",
                "claridad": "La informacion fue clara?",
                "seguimiento": "Como fue el seguimiento durante el servicio?",
            },
            "abierta": {"comentario": "Algo mas que quiera decirnos?"},
        },
        "gracias": "Gracias. Su respuesta llega directo al equipo de operaciones.",
    },
    "pt": {
        "ejecutivo": {
            "general": "Como avalia o servico de seguranca que recebeu?",
            "escala": "1 = muito ruim · 5 = excelente",
            "bien": {"mas_valoro": "O que mais valorizou?"},
            "mal": {
                "puntualidad": "A equipe chegou no horario?",
                "trato": "Como foi o trato e a apresentacao do motorista?",
                "vehiculo": "Em que condicoes estava o veiculo?",
                "molestia": "O que mais o incomodou? Conte para nos.",
            },
        },
        "solicitante": {
            "general": "Como avalia o atendimento do seu consultor?",
            "escala": "1 = muito ruim · 5 = excelente",
            "siempre": {
                "respuesta_cotizacion": "Com que rapidez recebeu seu orcamento?",
                "claridad": "A informacao foi clara?",
                "seguimiento": "Como foi o acompanhamento durante o servico?",
            },
            "abierta": {"comentario": "Algo mais que queira nos dizer?"},
        },
        "gracias": "Obrigado. Sua resposta vai direto para a equipe de operacoes.",
    },
}


def _textos(idioma: str | None) -> dict:
    return PREGUNTAS.get((idioma or "en").lower(), PREGUNTAS["en"])


# ---------------------------------------------------------------- envio

def generar(db: Session, servicio_id: int, idioma: str = "en") -> list[m.Encuesta]:
    """Crea las dos encuestas del servicio. Se corre al cerrarlo."""
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
        ya = (db.query(m.Encuesta)
              .filter_by(servicio_id=servicio_id, tipo=tipo).first())
        if ya:
            continue        # no se manda dos veces la misma
        encuesta = m.Encuesta(
            servicio_id=servicio_id, tipo=tipo,
            consultor_id=(servicio.consultor_id
                          if tipo == m.TipoEncuesta.SOLICITANTE else None),
            destinatario_nombre=nombre, destinatario_correo=correo,
            idioma=idioma,
            token=secrets.token_urlsafe(24),
            expira_en=datetime.now() + timedelta(days=DIAS_PARA_RESPONDER))
        db.add(encuesta)
        db.flush()
        creadas.append(encuesta)

        db.add(m.Notificacion(
            servicio_id=servicio_id,
            destinatario=(m.Destinatario.EJECUTIVO
                          if tipo == m.TipoEncuesta.EJECUTIVO
                          else m.Destinatario.SOLICITANTE),
            canal=m.Canal.CORREO, correo=correo,
            asunto=f"{servicio.folio}: {_textos(idioma)[tipo.value]['general']}",
            cuerpo=_textos(idioma)["gracias"],
            enlace_seguimiento=f"/encuestas/pagina/{encuesta.token}",
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
    return {
        "resultado": "recibida",
        "mensaje": _textos(encuesta.idioma)["gracias"],
        "abre_revision": encuesta.requiere_clasificacion,
    }


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

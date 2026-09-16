"""Avisos al telefono del equipo de campo.

Los entrega el propio navegador: sin terceros, sin costo por mensaje y
sin tramite. A cambio tiene dos limites que hay que conocer y no
esconder:

  - en iPhone solo funciona desde iOS 16.4 y solo si el agente agrego la
    app a su pantalla de inicio
  - si el telefono esta apagado, el aviso espera; si pasa mucho, se
    pierde

Por eso esto sirve para recordar —confirma manana, se te vence un
curso— y no para lo que no puede fallar. Lo que no puede fallar se
habla por telefono, y por eso la app trae el numero de la central a un
toque.

El envio nunca detiene lo que lo llamo: si un aviso no sale, el corte de
nomina o la asignacion siguen su camino igual.
"""
import json
import logging

from sqlalchemy.orm import Session

from app import models as m
from app.config import settings

registro = logging.getLogger("centauro.push")


def hay_llaves() -> bool:
    return bool(settings.vapid_private and settings.vapid_public)


def suscripciones(db: Session, persona_id: int) -> list[m.SuscripcionPush]:
    return (db.query(m.SuscripcionPush)
            .filter_by(persona_id=persona_id, activa=True).all())


def avisar(db: Session, persona_id: int, titulo: str, cuerpo: str,
           url: str = "/app/", etiqueta: str | None = None) -> dict:
    """Manda un aviso a todos los telefonos de esa persona.

    `etiqueta` hace que un aviso reemplace al anterior del mismo tipo en
    vez de apilarse: tres recordatorios iguales en la pantalla de
    bloqueo se leen como una falla de la app, no como insistencia.
    """
    if not hay_llaves():
        return {"enviados": 0, "motivo": "sin llaves configuradas"}

    filas = suscripciones(db, persona_id)
    if not filas:
        return {"enviados": 0, "motivo": "sin telefonos suscritos"}

    from pywebpush import WebPushException, webpush

    carga = json.dumps({"titulo": titulo, "cuerpo": cuerpo, "url": url,
                        "etiqueta": etiqueta or "centauro"})
    enviados, apagadas = 0, 0

    for fila in filas:
        try:
            webpush(
                subscription_info={
                    "endpoint": fila.endpoint,
                    "keys": {"p256dh": fila.p256dh, "auth": fila.auth},
                },
                data=carga,
                vapid_private_key=settings.vapid_private,
                vapid_claims={"sub": settings.vapid_contacto},
                ttl=3600,
            )
            enviados += 1
        except WebPushException as error:
            # 404 y 410 quieren decir que ese telefono ya no existe: se
            # apaga la fila en vez de reintentarla todas las semanas.
            codigo = getattr(error.response, "status_code", None)
            if codigo in (404, 410):
                fila.activa = False
                apagadas += 1
            else:
                registro.warning("aviso no entregado a %s: %s",
                                 fila.persona_id, error)
        except Exception as error:                        # noqa: BLE001
            # Un aviso que no sale no puede tumbar lo que lo llamo.
            registro.warning("fallo el aviso a %s: %s", fila.persona_id, error)

    if apagadas:
        db.flush()
    return {"enviados": enviados, "telefonos": len(filas),
            "apagadas": apagadas}


# ==================================================================
# El recordatorio de la vispera
# ==================================================================

def sin_confirmar(db: Session, dia) -> list[tuple]:
    """Quien tiene servicio ese dia y todavia no ha dicho que va."""
    filas = (db.query(m.AsignacionPersonal)
             .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
             .filter(m.Jornada.fecha == dia,
                     m.Jornada.estatus != m.EstatusJornada.CANCELADA,
                     m.AsignacionPersonal.confirmado.is_(False))
             .all())
    return [(a.persona_id, a.jornada) for a in filas if a.persona_id]


def recordar_la_vispera(db: Session, dia=None) -> dict:
    """Le recuerda a cada quien que manana trabaja.

    Es el aviso que de verdad justifica todo esto: la confirmacion de la
    vispera dependia de que alguien se acordara de abrir la app, y una
    confirmacion que nadie hace es un renglon rojo eterno en la central.

    Un aviso por persona aunque tenga dos servicios: tres notificaciones
    seguidas se leen como una falla, no como insistencia.
    """
    from datetime import date, timedelta

    from app import reloj

    # "Manana" es el manana de cada pais. El beat corre a una hora fija
    # de Mexico, asi que sin esto el recordatorio le llega a Brasil a
    # las 19:00 y hablandole del dia equivocado cuando cae en el borde.
    if dia is None:
        dias = {reloj.hoy_en(p) + timedelta(days=1)
                for p in db.query(m.Pais).filter(m.Pais.activo.is_(True)).all()}
        dias = dias or {date.today() + timedelta(days=1)}
    else:
        dias = {dia}

    por_persona: dict[int, list] = {}
    for cada in sorted(dias):
        for persona_id, jornada in sin_confirmar(db, cada):
            por_persona.setdefault(persona_id, []).append(jornada)

    avisados = []
    for persona_id, jornadas in por_persona.items():
        jornadas.sort(key=lambda j: j.inicio_programado)
        primera = jornadas[0]
        cuantos = len(jornadas)
        cuerpo = (f"Mañana a las {primera.inicio_programado:%H:%M}"
                  + (f" y {cuantos - 1} servicio(s) más" if cuantos > 1 else "")
                  + ". Abre la app y confirma que vas.")
        r = avisar(db, persona_id, "Confirma que vas mañana", cuerpo,
                   etiqueta="vispera")
        if r["enviados"]:
            avisados.append({"persona_id": persona_id,
                             "servicios": cuantos})
    db.commit()
    return {"dia": dia.isoformat(), "avisados": avisados,
            "sin_telefono": len(por_persona) - len(avisados)}


# ==================================================================
# El relevo: el aviso que no puede esperar al de la vispera
# ==================================================================

def avisar_relevo(db: Session, entra: m.Persona, sale: m.Persona,
                  cambio: dict) -> dict:
    """Le avisa al que entra, en el momento del cambio.

    El recordatorio de la vispera solo mira manana. Un reemplazo hecho
    hoy para hoy nunca lo dispararia, y ese es justamente el urgente: la
    persona que entra se enteraba porque le hablaban por telefono, o no
    se enteraba.

    Como todos los avisos, este no detiene nada: si no sale, el cambio
    ya quedo hecho igual.
    """
    dias = cambio.get("jornadas_afectadas") or []
    if not dias:
        return {"enviados": 0, "motivo": "sin dias"}

    cuantos = len(dias)
    cuando = dias[0] if cuantos == 1 else f"{dias[0]} al {dias[-1]}"
    return avisar(
        db, entra.id,
        titulo="Entras a un servicio",
        cuerpo=(f"Cubres a {sale.nombre}: {cuando}"
                + (f" · {cuantos} dias" if cuantos > 1 else "")
                + ". Abre la app y confirma."),
        etiqueta="relevo")

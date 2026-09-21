"""Bitacora de acciones sobre los servicios.

Cualquier consultor puede trabajar la cartera de otro, para cubrir
enfermedades o ausencias. La apertura no quita trazabilidad: toda accion
sobre un servicio ajeno queda marcada como cobertura y se avisa al titular.
"""
from sqlalchemy.orm import Session

from app import correo_html
from app import models as m
from app import textos_aviso as ta


LARGO_DETALLE = 400          # lo que aguanta la columna


def registrar(db: Session, usuario: m.Usuario, servicio: m.Servicio,
              accion: str, detalle: str | None = None,
              jornada_id: int | None = None) -> m.RegistroAccion:
    titular_id = servicio.consultor_id
    cobertura = (
        usuario.rol == m.Rol.CONSULTOR
        and titular_id is not None
        and titular_id != usuario.persona_id
    )

    # El detalle es una nota para quien audita, no un dato: si se pasa de
    # largo se recorta. Nunca debe tumbar la operacion que esta narrando.
    if detalle and len(detalle) > LARGO_DETALLE:
        detalle = detalle[:LARGO_DETALLE - 1].rstrip() + "…"

    registro = m.RegistroAccion(
        servicio_id=servicio.id, jornada_id=jornada_id,
        usuario_id=usuario.id, persona_id=usuario.persona_id,
        rol=usuario.rol, accion=accion, detalle=detalle,
        en_cobertura=cobertura, titular_id=titular_id,
    )
    db.add(registro)

    if cobertura:
        titular = db.get(m.Persona, titular_id)
        quien = usuario.persona.nombre
        # El asunto dice quien y que, no "movimiento en tu servicio":
        # el titular lee la lista de correos en el telefono y necesita
        # decidir ahi si abre o no. Un asunto que no dice nada se abre
        # tarde, y este avisa de algo que ya paso en su cartera.
        # Este no va a un cliente: va a alguien de la casa, y la gente
        # de la casa lee en el idioma de su pais --la misma regla de la
        # app de campo--.
        lengua = ta.idioma_de(db, servicio, m.Destinatario.CONSULTOR)
        db.add(m.Notificacion(
            servicio_id=servicio.id, jornada_id=jornada_id,
            destinatario=m.Destinatario.CONSULTOR, canal=m.Canal.CORREO,
            correo=titular.correo if titular else None,
            idioma=lengua,
            asunto=ta.t(lengua, "cob_asunto", folio=servicio.folio,
                        quien=quien),
            cuerpo=ta.t(lengua, "cob_cuerpo", quien=quien),
            datos=correo_html.guardar_datos([
                (ta.t(lengua, "quien"), quien, usuario.persona.telefono),
                (ta.t(lengua, "que_hizo"), accion),
                (ta.t(lengua, "detalle"), detalle),
            ]),
        ))

    return registro


def servicio_de_jornada(db: Session, jornada_id: int) -> m.Servicio | None:
    jornada = db.get(m.Jornada, jornada_id)
    return jornada.equipo.servicio if jornada else None

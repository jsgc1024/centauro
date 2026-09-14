"""Bitacora de acciones sobre los servicios.

Cualquier consultor puede trabajar la cartera de otro, para cubrir
enfermedades o ausencias. La apertura no quita trazabilidad: toda accion
sobre un servicio ajeno queda marcada como cobertura y se avisa al titular.
"""
from sqlalchemy.orm import Session

from app import models as m


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
        db.add(m.Notificacion(
            servicio_id=servicio.id, jornada_id=jornada_id,
            destinatario=m.Destinatario.CONSULTOR, canal=m.Canal.CORREO,
            correo=titular.correo if titular else None,
            asunto=f"{servicio.folio}: movimiento en tu servicio",
            cuerpo=(f"{usuario.persona.nombre} trabajo tu servicio en cobertura. "
                    f"Accion: {accion}. {detalle or ''}").strip(),
        ))

    return registro


def servicio_de_jornada(db: Session, jornada_id: int) -> m.Servicio | None:
    jornada = db.get(m.Jornada, jornada_id)
    return jornada.equipo.servicio if jornada else None

"""Experiencia acumulada del personal de seguridad en Centauro.

Suma las horas de todos los servicios que ha ejecutado. Se muestra en el
task sheet junto a su nombre y alimenta el tablero de profesionalismo.
"""
from sqlalchemy.orm import Session

from app import models as m


def horas_acumuladas(db: Session, persona_id: int) -> int:
    """Horas reales cuando se registraron los hitos; si no, las de la
    modalidad contratada de esa jornada."""
    jornadas = (db.query(m.Jornada)
                .join(m.AsignacionPersonal,
                      m.AsignacionPersonal.jornada_id == m.Jornada.id)
                .filter(m.AsignacionPersonal.persona_id == persona_id,
                        m.Jornada.estatus.in_([m.EstatusJornada.TERMINADA,
                                               *m.ARRANCADAS]))
                .all())

    horas = 0.0
    for j in jornadas:
        if j.inicio_real and j.fin_real:
            horas += (j.fin_real - j.inicio_real).total_seconds() / 3600
        elif j.estatus == m.EstatusJornada.TERMINADA:
            horas += float(j.modalidad.horas)
    return int(round(horas))


def resumen(db: Session, persona_id: int) -> dict:
    persona = db.get(m.Persona, persona_id)
    horas = horas_acumuladas(db, persona_id)
    servicios = (db.query(m.Equipo.servicio_id)
                 .join(m.Jornada, m.Jornada.equipo_id == m.Equipo.id)
                 .join(m.AsignacionPersonal,
                       m.AsignacionPersonal.jornada_id == m.Jornada.id)
                 .filter(m.AsignacionPersonal.persona_id == persona_id)
                 .distinct().count())
    return {
        "persona": persona.nombre if persona else None,
        "horas_en_centauro": horas,
        "servicios_atendidos": servicios,
    }

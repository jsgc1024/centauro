"""Experiencia acumulada del personal de seguridad en Centauro.

Suma las horas de todos los servicios que ha ejecutado. Se muestra en el
task sheet junto a su nombre y alimenta el tablero de profesionalismo.
"""
from sqlalchemy.orm import Session

from app import models as m


def horas_acumuladas(db: Session, persona_id: int) -> int:
    """Horas reales cuando se registraron los hitos; si no, las de la
    modalidad contratada de esa jornada."""
    return horas_por_persona(db, [persona_id]).get(persona_id, 0)


def horas_por_persona(db: Session, persona_ids: list[int]) -> dict[int, int]:
    """Lo mismo, para varias personas de un golpe: persona -> horas.

    La ficha de profesionalismo de todo el personal la pedia persona por
    persona, cargando cada jornada con su modalidad (seccion 101). Aqui
    una sola consulta trae las horas de todos, sin cargar objetos.
    """
    if not persona_ids:
        return {}
    filas = (db.query(m.AsignacionPersonal.persona_id,
                      m.Jornada.inicio_real, m.Jornada.fin_real,
                      m.Jornada.estatus, m.Modalidad.horas)
             .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
             .join(m.Modalidad, m.Jornada.modalidad_id == m.Modalidad.id)
             .filter(m.AsignacionPersonal.persona_id.in_(list(persona_ids)),
                     m.Jornada.estatus.in_([m.EstatusJornada.TERMINADA,
                                            *m.ARRANCADAS]))
             .all())

    horas: dict[int, float] = {}
    for persona_id, inicio_real, fin_real, estatus, contratadas in filas:
        suma = horas.get(persona_id, 0.0)
        if inicio_real and fin_real:
            suma += (fin_real - inicio_real).total_seconds() / 3600
        elif estatus == m.EstatusJornada.TERMINADA:
            suma += float(contratadas)
        horas[persona_id] = suma
    return {persona_id: int(round(suma)) for persona_id, suma in horas.items()}


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

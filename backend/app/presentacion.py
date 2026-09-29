"""A que hora tiene que estar el equipo en el punto de encuentro.

El equipo NUNCA llega a la hora: llega antes. Si el encuentro es en el
aeropuerto, se mide contra la hora del vuelo, porque el ejecutivo puede
salir del filtro antes de lo previsto. En cualquier otro lugar se mide
contra la hora de presentacion acordada con el cliente.

Los minutos viven en el pais, no en el codigo: cada operacion los ajusta.
"""
from datetime import datetime, timedelta


def llegada_del_equipo(inicio_programado: datetime,
                       vuelo_hora: datetime | None,
                       vuelo_tipo: str | None,
                       minutos_aeropuerto: int = 45,
                       minutos_normal: int = 30) -> tuple[datetime, int, bool]:
    """Devuelve (hora a la que debe estar el equipo, minutos, contra_vuelo).

    Solo el vuelo de LLEGADA manda la hora: en un vuelo de salida el
    ejecutivo sale de su hotel y la referencia es su presentacion.
    """
    if vuelo_hora and vuelo_tipo == "llegada":
        return (vuelo_hora - timedelta(minutes=minutos_aeropuerto),
                minutos_aeropuerto, True)
    return (inicio_programado - timedelta(minutes=minutos_normal),
            minutos_normal, False)


def llegada_de_la_jornada(db, jornada) -> tuple[datetime, int, bool]:
    """Lo mismo, con los minutos del pais del servicio.

    La app, la central y el camino usaban los 45/30 de siempre mientras
    el task sheet ya leia los del pais (seccion 99): si un pais los
    cambiaba en Catalogos, la hoja decia una hora y la app otra.
    """
    from app import models as m

    equipo = getattr(jornada, "equipo", None)
    servicio = getattr(equipo, "servicio", None)
    pais = (db.get(m.Pais, servicio.pais_id)
            if db is not None and servicio is not None and servicio.pais_id
            else None)
    return llegada_del_equipo(
        jornada.inicio_programado, jornada.vuelo_hora, jornada.vuelo_tipo,
        getattr(pais, "anticipacion_aeropuerto_min", 45) or 45,
        getattr(pais, "anticipacion_min", 30) or 30)

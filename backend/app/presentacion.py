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

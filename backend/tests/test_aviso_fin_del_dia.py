"""El correo que cierra el dia.

Dos cosas que el cliente pregunta por telefono en cuanto se le va el
equipo: cuanto se paso del horario --porque eso se le va a facturar-- y
a que hora y donde esta el equipo manana. Peticion de Salvador (20 sep).

Si el correo las trae, no hay llamada. Si no las trae, la central
contesta la misma pregunta todas las noches.
"""
from ayudas import (asignar, configurar_origen, crear_servicio,
                    ejecutar_jornada, jornada, manana)


def _avisos_de_cierre(servicio_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return [a for a in db.query(m.Notificacion)
                .filter_by(servicio_id=servicio_id).all()
                if "terminado" in a.asunto]


def _servicio_de_dos_dias(cliente, sesion, datos, offset=420):
    h = sesion("consultor")
    modalidad = datos["modalidades"]["full_day"]["id"]
    servicio = crear_servicio(cliente, h, datos, [
        jornada(manana(offset), modalidad),
        jornada(manana(offset + 1), modalidad, hora="06:30:00"),
    ])
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        configurar_origen(cliente, h, j["id"])
    return servicio


def test_el_cierre_del_dia_dice_las_horas_extra_y_lo_de_manana(
        cliente, sesion, datos):
    servicio = _servicio_de_dos_dias(cliente, sesion, datos)
    primero = servicio["equipos"][0]["jornadas"][0]
    ejecutar_jornada(cliente, sesion("juan"), primero, horas_extra=2)

    avisos = _avisos_de_cierre(servicio["id"])
    assert len(avisos) == 1, avisos
    aviso = avisos[0]

    assert "2 horas extra" in aviso.cuerpo, aviso.cuerpo
    assert "Horas extra" in (aviso.datos or "")
    # La hora de manana y donde: el ejecutivo no tiene que abrir nada
    # mas para saber a que hora bajar.
    assert "06:30" in (aviso.datos or ""), aviso.datos
    assert "06:30" in aviso.cuerpo


def test_sin_horas_extra_tambien_se_dice(cliente, sesion, datos):
    """El silencio se lee como "no las contaron" y provoca la misma
    llamada que se queria evitar."""
    servicio = _servicio_de_dos_dias(cliente, sesion, datos, offset=440)
    primero = servicio["equipos"][0]["jornadas"][0]
    ejecutar_jornada(cliente, sesion("juan"), primero)

    aviso = _avisos_de_cierre(servicio["id"])[0]
    assert "dentro del horario contratado" in aviso.cuerpo
    assert "ninguna" in (aviso.datos or "")


def test_el_ultimo_dia_no_promete_un_manana_que_no_existe(
        cliente, sesion, datos):
    """Prometer una presentacion que no existe manda al ejecutivo a
    esperar abajo a nadie."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(460), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("juan"), j)

    aviso = _avisos_de_cierre(servicio["id"])[0]
    assert "último día programado" in aviso.cuerpo
    assert "Mañana" not in (aviso.datos or "")

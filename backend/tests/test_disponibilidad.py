"""Reglas de disponibilidad de recursos."""
from ayudas import asignar, crear_servicio, jornada, manana


def test_full_day_bloquea_el_dia_completo(cliente, sesion, datos):
    h = sesion("consultor")
    dia = manana(10)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    servicio = crear_servicio(cliente, h, datos,
                              [jornada(dia, datos["modalidades"]["full_day"]["id"])])
    j1 = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j1["id"], persona_id=juan)

    otro = crear_servicio(cliente, h, datos,
                          [jornada(dia, datos["modalidades"]["transfer"]["id"],
                                   hora="20:00:00")])
    j2 = otro["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j2["id"], persona_id=juan)[0]

    assert r.status_code == 409
    assert "Full day" in str(r.json()["detail"]["alertas"])


def test_bloqueo_duro_no_se_puede_forzar(cliente, sesion, datos):
    h = sesion("consultor")
    dia = manana(11)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    s1 = crear_servicio(cliente, h, datos,
                        [jornada(dia, datos["modalidades"]["transfer"]["id"],
                                 hora="09:00:00")])
    asignar(cliente, h, s1["equipos"][0]["jornadas"][0]["id"], persona_id=juan)

    # Empalme real: 10:00 cae dentro de la ventana 09:00-12:00
    s2 = crear_servicio(cliente, h, datos,
                        [jornada(dia, datos["modalidades"]["transfer"]["id"],
                                 hora="10:00:00")])
    r = asignar(cliente, h, s2["equipos"][0]["jornadas"][0]["id"],
                persona_id=juan, forzar=True)[0]

    assert r.status_code == 409, "un empalme real no debe poder forzarse"


def test_holgura_insuficiente_solo_alerta_y_el_consultor_decide(cliente, sesion, datos):
    h = sesion("consultor")
    dia = manana(12)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    s1 = crear_servicio(cliente, h, datos,
                        [jornada(dia, datos["modalidades"]["transfer"]["id"],
                                 hora="09:00:00")])
    asignar(cliente, h, s1["equipos"][0]["jornadas"][0]["id"], persona_id=juan)

    # Termina 12:00, el siguiente empieza 13:00: una sola hora de holgura
    s2 = crear_servicio(cliente, h, datos,
                        [jornada(dia, datos["modalidades"]["transfer"]["id"],
                                 hora="13:00:00")])
    j2 = s2["equipos"][0]["jornadas"][0]["id"]

    sin_forzar = asignar(cliente, h, j2, persona_id=juan, forzar=False)[0]
    assert sin_forzar.status_code == 409
    alertas = sin_forzar.json()["detail"]["alertas"]
    assert alertas[0]["nivel"] == "riesgo"
    assert alertas[0]["holgura_horas"] == 1.0

    forzando = asignar(cliente, h, j2, persona_id=juan, forzar=True)[0]
    assert forzando.status_code == 200


def test_transfers_encadenados_con_holgura_suficiente(cliente, sesion, datos):
    h = sesion("consultor")
    dia = manana(13)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    s1 = crear_servicio(cliente, h, datos,
                        [jornada(dia, datos["modalidades"]["transfer"]["id"],
                                 hora="08:00:00")])
    asignar(cliente, h, s1["equipos"][0]["jornadas"][0]["id"], persona_id=juan)

    # Termina 11:00, el siguiente empieza 14:00: tres horas de holgura
    s2 = crear_servicio(cliente, h, datos,
                        [jornada(dia, datos["modalidades"]["transfer"]["id"],
                                 hora="14:00:00")])
    r = asignar(cliente, h, s2["equipos"][0]["jornadas"][0]["id"],
                persona_id=juan, forzar=False)[0]
    assert r.status_code == 200, "dos transfers al dia deben poder encadenarse"


def test_nocturno_que_cruza_medianoche_solo_alerta(cliente, sesion, datos):
    """Se cobran como dias distintos, asi que no es bloqueo."""
    h = sesion("consultor")
    dia = manana(14)
    luis = datos["personal"]["Luis Mendoza"]["id"]

    s1 = crear_servicio(cliente, h, datos,
                        [jornada(dia, datos["modalidades"]["full_day"]["id"],
                                 hora="18:00:00")])
    asignar(cliente, h, s1["equipos"][0]["jornadas"][0]["id"], persona_id=luis)

    s2 = crear_servicio(cliente, h, datos,
                        [jornada(manana(15), datos["modalidades"]["transfer"]["id"],
                                 hora="10:00:00")])
    j2 = s2["equipos"][0]["jornadas"][0]["id"]

    sin_forzar = asignar(cliente, h, j2, persona_id=luis, forzar=False)[0]
    assert sin_forzar.status_code == 409
    assert sin_forzar.json()["detail"]["alertas"][0]["nivel"] == "riesgo"

    assert asignar(cliente, h, j2, persona_id=luis, forzar=True)[0].status_code == 200


def test_recomendacion_avisa_cuando_no_hay_recurso_local(cliente, sesion, datos):
    h = sesion("consultor")
    dia = manana(16)
    servicio = crear_servicio(cliente, h, datos,
                              [jornada(dia, datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]

    # La van de diez plazas no existe en CDMX: el aviso es de la flota.
    # Del personal ya no se pide por puesto —el personal de seguridad es
    # general— asi que lo que se mira aqui es la unidad.
    r = cliente.get(f"/servicios/jornadas/{j['id']}/recomendaciones"
                    f"?categoria_id={datos['categorias']['van_10']['id']}",
                    headers=h)
    assert r.status_code == 200
    assert r.json()["vehiculos"]["aviso"] is not None

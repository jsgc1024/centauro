"""La central cierra a mano un dia que nadie marco.

Un dia que se trabajo y que nadie marco se queda abierto, y mientras lo
este no entra a nomina: alguien que trabajo no cobra por una marca que
falto. Alguien tiene que poder cerrarlo.

Pero cerrar a mano es dar fe de algo sin evidencia desde la calle, y eso
es exactamente la forma que tendria un dia inventado. Lo que se prueba
aqui son los limites: quien puede, cuando puede, y que queda escrito
para que dentro de tres meses se pueda distinguir un dia marcado de uno
firmado por la central.
"""
from datetime import datetime, timedelta

from ayudas import asignar, configurar_origen, crear_servicio, jornada, manana


def _dia_pasado(cliente, sesion, datos, dias_atras=2, quien="Juan Ramirez"):
    """Un dia que ya paso y que nadie cerro."""
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(-dias_atras), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"],
                persona_id=datos["personal"][quien]["id"],
                vehiculo_id=datos["suburban"]["id"])[0]
    assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    return servicio, j


MOTIVO = "El equipo se quedo sin bateria; confirmado por telefono con el coordinador"


def test_el_dia_cerrado_a_mano_entra_a_nomina(cliente, sesion, datos):
    """Es todo el punto: sin esto, quien trabajo no cobra."""
    _, j = _dia_pasado(cliente, sesion, datos)

    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     json={"justificacion": MOTIVO}, headers=sesion("central"))
    assert r.status_code == 200, r.text
    assert r.json()["personas"] == 1
    assert r.json()["horas"] > 0

    r = cliente.get(f"/operacion/jornadas/{j['id']}/bitacora",
                    headers=sesion("central"))
    assert r.status_code == 200, r.text


def test_sin_justificacion_no_se_cierra(cliente, sesion, datos):
    """Dentro de tres meses esa nota va a ser lo unico que explique por
    que este dia no tiene marcas."""
    _, j = _dia_pasado(cliente, sesion, datos)
    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     json={"justificacion": "ok"}, headers=sesion("central"))
    assert r.status_code == 400, r.text


def test_no_se_cierra_un_dia_que_todavia_no_termina(cliente, sesion, datos):
    """Cerrar por adelantado es pagar trabajo que aun no ocurre, y es
    justo el agujero que este permiso podria abrir."""
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(3), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"])

    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     json={"justificacion": MOTIVO}, headers=sesion("central"))
    assert r.status_code == 409, r.text
    assert "todavia no termina" in r.json()["detail"]["mensaje"]


def test_el_consultor_no_puede_cerrar_dias(cliente, sesion, datos):
    """Es quien vende el servicio: a nadie le conviene mas que un dia
    aparezca trabajado."""
    _, j = _dia_pasado(cliente, sesion, datos)
    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     json={"justificacion": MOTIVO},
                     headers=sesion("consultor"))
    assert r.status_code == 403, r.text


def test_nadie_firma_su_propio_dia(cliente, sesion, datos):
    """Firmarse las propias horas es la version mas simple del fraude,
    y la mas facil de impedir."""
    _, j = _dia_pasado(cliente, sesion, datos)
    # Se mete a la persona de la central como personal de ese dia.
    quien = cliente.get("/auth/yo", headers=sesion("central")).json()
    asignar(cliente, sesion("consultor"), j["id"],
            persona_id=quien["persona_id"], rol="agente_seguridad")

    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     json={"justificacion": MOTIVO}, headers=sesion("central"))
    assert r.status_code == 403, r.text
    assert "que trabajaste" in r.json()["detail"]["mensaje"]


def test_un_dia_ya_cerrado_no_se_vuelve_a_cerrar(cliente, sesion, datos):
    _, j = _dia_pasado(cliente, sesion, datos)
    h = sesion("central")
    cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                 json={"justificacion": MOTIVO}, headers=h)
    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     json={"justificacion": MOTIVO}, headers=h)
    assert r.status_code == 409, r.text
    assert "ya esta cerrado" in r.json()["detail"]["mensaje"]


def test_el_termino_no_puede_ser_antes_del_inicio(cliente, sesion, datos):
    _, j = _dia_pasado(cliente, sesion, datos)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     json={"justificacion": MOTIVO,
                           "inicio_real": inicio.isoformat(),
                           "fin_real": (inicio - timedelta(hours=1)).isoformat()},
                     headers=sesion("central"))
    assert r.status_code == 409, r.text


def test_la_lista_de_dias_sin_cerrar_los_encuentra(cliente, sesion, datos):
    """Es la pantalla de trabajo de la central: cada renglon es alguien
    que trabajo y todavia no puede cobrar."""
    _, j = _dia_pasado(cliente, sesion, datos)
    r = cliente.get("/operacion/dias-sin-cerrar", headers=sesion("central"))
    assert r.status_code == 200, r.text

    mio = [d for d in r.json()["dias"] if d["jornada_id"] == j["id"]]
    assert len(mio) == 1
    # Un dia sin ninguna marca no es lo mismo que uno que arranco y no
    # cerro: el primero hay que preguntarlo antes de firmarlo.
    assert mio[0]["arranco"] is False
    assert mio[0]["marcas"] == []
    assert mio[0]["personal"][0]["nombre"] == "Juan Ramirez"

    cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                 json={"justificacion": MOTIVO}, headers=sesion("central"))
    r = cliente.get("/operacion/dias-sin-cerrar", headers=sesion("central"))
    assert not [d for d in r.json()["dias"] if d["jornada_id"] == j["id"]]


def test_un_dia_de_manana_no_aparece_como_sin_cerrar(cliente, sesion, datos):
    """La lista se lee todos los dias; si se llena de ruido deja de
    leerse."""
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(1), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    r = cliente.get("/operacion/dias-sin-cerrar", headers=sesion("central"))
    assert not [d for d in r.json()["dias"] if d["jornada_id"] == j["id"]]


def test_reabrir_deshace_solo_lo_que_la_central_cerro(cliente, sesion, datos):
    """Un dia que el equipo marco desde la calle no se reabre por aqui:
    esa hora se corrige ajustando el hito, que es donde queda el rastro."""
    _, j = _dia_pasado(cliente, sesion, datos)
    h = sesion("central")

    r = cliente.post(f"/operacion/jornadas/{j['id']}/reabrir",
                     json={"justificacion": "Me equivoque de jornada al cerrar"},
                     headers=h)
    assert r.status_code == 409, r.text
    assert "no lo cerro la central" in r.json()["detail"]["mensaje"]

    cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                 json={"justificacion": MOTIVO}, headers=h)
    r = cliente.post(f"/operacion/jornadas/{j['id']}/reabrir",
                     json={"justificacion": "Me equivoque de jornada al cerrar"},
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["ya_estaba_pagado"] is False

    # Y vuelve a aparecer en la lista de pendientes.
    r = cliente.get("/operacion/dias-sin-cerrar", headers=h)
    assert [d for d in r.json()["dias"] if d["jornada_id"] == j["id"]]

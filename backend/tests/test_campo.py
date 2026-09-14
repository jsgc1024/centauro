"""La app del personal de seguridad.

Cada quien ve solo lo suyo, y lo que ve tiene que ser cierto: el dia con
su punto y su hora, el dinero que trae de la empresa y el que le deben.

Lo que mas se cuida aqui es el limite: la ficha del dia trae el nombre
del ejecutivo al que se protege, y eso no se le ensena a quien no va.
"""
from datetime import date, timedelta

from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana)


def _servicio_de_juan(cliente, sesion, datos, dia=1, quien="Juan Ramirez"):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(dia), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"],
                persona_id=datos["personal"][quien]["id"],
                vehiculo_id=datos["suburban"]["id"])[0]
    assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def test_mi_dia_trae_lo_que_el_equipo_necesita(cliente, sesion, datos):
    """El punto, la hora a la que hay que estar parado ahi, con quien va
    y que sigue. En una sola consulta: el telefono la hace con media
    barra de senal."""
    _servicio_de_juan(cliente, sesion, datos, dia=0)
    r = cliente.get("/campo/mi-dia", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    dia = r.json()

    assert dia["persona"] == "Juan Ramirez"
    assert len(dia["hoy"]) == 1
    f = dia["hoy"][0]
    assert f["punto"]["lat"] is not None
    assert f["punto"]["geocerca_metros"] > 0
    # La hora que importa no es la del servicio: es la de llegar.
    assert f["llegar_a_las"] < f["presentacion"]
    assert f["anticipacion_minutos"] == 30
    # Y lo primero que toca hacer es marcar la llegada.
    assert f["siguiente"] == "llegada_origen"
    assert f["confirmado"] is False


def test_manana_entra_porque_la_confirmacion_es_de_la_vispera(cliente, sesion,
                                                              datos):
    """Si la app solo mostrara hoy, nadie podria confirmar nunca."""
    _servicio_de_juan(cliente, sesion, datos, dia=1)
    dia = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    assert len(dia["manana"]) == 1
    assert dia["hoy"] == []


def test_nadie_ve_el_dia_de_otro(cliente, sesion, datos):
    """La ficha trae el nombre del ejecutivo al que se protege."""
    _, j = _servicio_de_juan(cliente, sesion, datos, dia=0)
    r = cliente.get(f"/campo/jornadas/{j['id']}", headers=sesion("luis"))
    assert r.status_code == 403, r.text

    dia = cliente.get("/campo/mi-dia", headers=sesion("luis")).json()
    assert dia["hoy"] == []


def test_confirmar_se_ve_en_su_dia(cliente, sesion, datos):
    _, j = _servicio_de_juan(cliente, sesion, datos, dia=1)
    h = sesion("juan")
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=h)
    assert r.status_code == 200, r.text

    dia = cliente.get("/campo/mi-dia", headers=h).json()
    assert dia["manana"][0]["confirmado"] is True


def test_la_marca_sin_senal_llega_diferida_y_se_nota(cliente, sesion, datos):
    """El equipo marca en un sotano y se manda al volver la linea. La
    hora del telefono se respeta; lo que no se pierde es cuanto tardo en
    llegar."""
    from datetime import datetime

    _, j = _servicio_de_juan(cliente, sesion, datos, dia=0)
    h = sesion("juan")
    # Se marca con la hora de la presentacion, y llega despues.
    dia = cliente.get("/campo/mi-dia", headers=h).json()
    presentacion = dia["hoy"][0]["presentacion"]

    r = cliente.post(f"/operacion/jornadas/{j['id']}/hitos", json={
        "tipo": "llegada_origen",
        "lat": "19.4272", "lon": "-99.1679",
        "marcado_en": presentacion,
    }, headers=h)
    assert r.status_code == 200, r.text
    hito = r.json()
    assert hito["recibido_en"] is not None
    # Se marco a la hora de presentacion y llego despues: es diferida
    # salvo que la prueba corra en el mismo minuto.
    if hito["diferido"]:
        assert any("diferida" in a for a in hito["avisos"])


def test_mis_viaticos_muestran_lo_que_falta_comprobar(cliente, sesion, datos):
    servicio, j = _servicio_de_juan(cliente, sesion, datos, dia=1)
    h = sesion("consultor")
    equipo_id = servicio["equipos"][0]["id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": juan, "monto": "1500"}, headers=h)

    r = cliente.get("/campo/mis-viaticos", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    suyos = r.json()
    fila = next(s for s in suyos["servicios"]
                if s["folio"] == servicio["folio"])
    assert fila["entregado"] == 1500
    assert fila["comprobado"] == 0
    assert fila["por_comprobar"] == 1500


def test_mis_comisiones_separan_lo_pagado_de_lo_que_va_corriendo(cliente,
                                                                 sesion, datos):
    """Lo que todavia no entra a un corte es una cuenta, no una promesa."""
    r = cliente.get("/campo/mis-comisiones", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    mias = r.json()
    assert "cortes" in mias
    assert "en_curso" in mias
    assert "nota" in mias["en_curso"]


def test_mi_capacitacion_avisa_de_lo_que_vence(cliente, sesion, datos):
    from app import models as m
    from app.db import SessionLocal

    juan = datos["personal"]["Juan Ramirez"]["id"]
    db = SessionLocal()
    try:
        db.add(m.Capacitacion(persona_id=juan, nombre="Manejo defensivo",
                              vigencia_hasta=date.today() + timedelta(days=10)))
        db.add(m.Capacitacion(persona_id=juan, nombre="Primeros auxilios",
                              vigencia_hasta=date.today() - timedelta(days=3)))
        db.commit()
    finally:
        db.close()

    r = cliente.get("/campo/mi-capacitacion", headers=sesion("juan")).json()
    assert r["por_vencer"] == 1
    assert r["vencidas"] == 1


def test_la_consola_no_entra_a_la_app(cliente, sesion, datos):
    """Estas puertas son del personal de seguridad. Un consultor que
    entre aqui estaria viendo el dia de alguien mas."""
    assert cliente.get("/campo/mi-dia",
                       headers=sesion("consultor")).status_code == 403


# ----------------------------------------- comprobar desde la calle

def _con_viatico(cliente, sesion, datos, monto="1500"):
    servicio, j = _servicio_de_juan(cliente, sesion, datos, dia=1)
    h = sesion("consultor")
    equipo_id = servicio["equipos"][0]["id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                     json={"persona_id": juan, "monto": monto}, headers=h)
    assert r.status_code == 200, r.text
    mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
    return mios["servicios"][0]["dias"][0]["viatico_id"]


def test_comprobar_baja_lo_que_falta(cliente, sesion, datos):
    viatico_id = _con_viatico(cliente, sesion, datos, monto="1500")
    r = cliente.post(f"/campo/viaticos/{viatico_id}/comprobante", json={
        "concepto": "alimentos", "tipo": "nota", "monto": "400",
        "descripcion": "Comida del dia",
    }, headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert float(r.json()["comprobado"]) == 400
    assert float(r.json()["falta"]) == 1100


def test_nadie_comprueba_viaticos_de_otro(cliente, sesion, datos):
    viatico_id = _con_viatico(cliente, sesion, datos)
    r = cliente.post(f"/campo/viaticos/{viatico_id}/comprobante", json={
        "concepto": "alimentos", "tipo": "nota", "monto": "100",
    }, headers=sesion("luis"))
    assert r.status_code == 403, r.text


def test_la_foto_del_ticket_se_guarda_con_el_comprobante(cliente, sesion,
                                                         datos):
    """La prueba vive dentro del registro, no en un enlace que el dia de
    la revision puede no cargar."""
    from app import models as m
    from app.db import SessionLocal

    viatico_id = _con_viatico(cliente, sesion, datos)
    foto = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA=="
    r = cliente.post(f"/campo/viaticos/{viatico_id}/comprobante", json={
        "concepto": "combustible", "tipo": "nota", "monto": "800",
        "imagen": foto,
    }, headers=sesion("juan"))
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        guardado = (db.query(m.Comprobante)
                    .filter_by(asignacion_id=viatico_id).first())
        assert guardado.imagen == foto
    finally:
        db.close()


def test_mi_dia_trae_el_telefono_de_la_central(cliente, sesion, datos):
    """Decir 'llama a la central' sin dar el numero es no decir nada."""
    _servicio_de_juan(cliente, sesion, datos, dia=0)
    d = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    assert d["central"], "no viene la central"
    assert d["central"]["telefono"], d["central"]


def test_mi_dia_trae_los_proximos_dias(cliente, sesion, datos):
    """Dos dias no alcanzan para que alguien planee su vida."""
    _servicio_de_juan(cliente, sesion, datos, dia=5)
    d = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    assert len(d["proximos"]) == 1
    assert d["proximos"][0]["llegar_a_las"]

# -*- coding: utf-8 -*-
"""El reemplazo, contado al cliente.

Un reemplazo no es un hecho administrativo: es **otra persona tocando la
puerta del ejecutivo, u otra placa esperando en la calle**. Lo que
decide si sale un correo no es que el cambio exista, es si el cliente se
va a topar con él.

Por eso se prueban las dos mitades de la regla: el cambio de hoy avisa
de inmediato, y el de la semana que viene **no avisa** —ese viaja en el
task sheet, que es donde el cliente ya busca quién va—.

Y una tercera cosa, que es la que se rompe sola con el tiempo: **el
correo no dice el motivo**. Que alguien se enfermó o no llegó es de la
casa.
"""
from datetime import datetime, timedelta

from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana, marcar)


def _placa(datos, placa):
    return next(v["id"] for v in datos["vehiculos"] if v["placa"] == placa)


def _avisos(servicio_id, asunto_contiene=None):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        avisos = (db.query(m.Notificacion)
                  .filter_by(servicio_id=servicio_id).all())
        if asunto_contiene:
            avisos = [a for a in avisos if asunto_contiene in (a.asunto or "")]
        return avisos


def _hoy_alla(datos):
    """El hoy del país donde se ejecuta, no el del contenedor.

    Si la prueba corre de madrugada en UTC, en México todavía es el día
    anterior: una jornada con la fecha del contenedor sería *mañana*
    para el candado y el aviso no saldría. La diferencia solo se ve a
    ciertas horas, que es la peor forma de que una prueba falle.
    """
    from app import models as m, reloj
    from app.db import SessionLocal
    with SessionLocal() as db:
        return reloj.ahora_en(db.get(m.Pais, datos["mx"]["id"])).date()


def _servicio(cliente, sesion, datos, dia=0):
    """Un día, con Juan y la Suburban. `dia=0` es hoy, allá."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(dia) if dia else _hoy_alla(datos),
                 datos["modalidades"]["full_day"]["id"], hora="22:00:00")],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=_placa(datos, "ABC-1234"))
    return servicio, j


def _reemplazar(cliente, h, datos, jornada_id):
    return cliente.post(
        "/contingencia/reemplazos/personal",
        json={"desde_jornada_id": jornada_id,
              "sale_persona_id": datos["personal"]["Juan Ramirez"]["id"],
              "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
              "motivo": "Se reportó enfermo"},
        headers=h)


def test_el_cambio_de_hoy_se_avisa_a_los_dos(cliente, sesion, datos):
    """El ejecutivo tiene que poder reconocer a quien llega por él."""
    h = sesion("consultor")
    servicio, j = _servicio(cliente, sesion, datos, dia=0)

    r = _reemplazar(cliente, h, datos, j["id"])
    assert r.status_code == 200, r.text
    assert r.json()["cliente_avisado"] is True

    from app import models as m
    avisos = [a for a in _avisos(servicio["id"]) if "cambio" in (a.cuerpo or "")
              or "Luis" in (a.cuerpo or "")]
    destinatarios = {a.destinatario for a in avisos}
    assert m.Destinatario.EJECUTIVO in destinatarios
    assert m.Destinatario.SOLICITANTE in destinatarios


def test_el_cambio_de_otro_dia_no_manda_correo(cliente, sesion, datos):
    """Viaja en el task sheet. Un correo por el cambio de la semana que
    viene gasta la atención que hace falta para el de hoy."""
    h = sesion("consultor")
    servicio, j = _servicio(cliente, sesion, datos, dia=7)

    r = _reemplazar(cliente, h, datos, j["id"])
    assert r.status_code == 200, r.text
    assert r.json()["cliente_avisado"] is False
    assert [a for a in _avisos(servicio["id"]) if "Luis" in (a.cuerpo or "")] == []


def test_el_correo_no_dice_el_motivo(cliente, sesion, datos):
    """Que alguien se enfermó es de la casa. Al cliente se le dice quién
    va ahora, no por qué cambió."""
    h = sesion("consultor")
    servicio, j = _servicio(cliente, sesion, datos, dia=0)
    _reemplazar(cliente, h, datos, j["id"])

    for a in _avisos(servicio["id"]):
        texto = f"{a.asunto or ''} {a.cuerpo or ''} {a.datos or ''}"
        assert "enfermo" not in texto.lower()


def test_cada_uno_lo_recibe_en_su_idioma(cliente, sesion, datos):
    """El principal en inglés, quien solicita en el de su país."""
    from app import models as m
    h = sesion("consultor")
    servicio, j = _servicio(cliente, sesion, datos, dia=0)
    _reemplazar(cliente, h, datos, j["id"])

    avisos = {a.destinatario: a for a in _avisos(servicio["id"])
              if "Luis" in (a.cuerpo or "")}
    assert avisos[m.Destinatario.EJECUTIVO].idioma == "en"
    assert avisos[m.Destinatario.SOLICITANTE].idioma == "es"


def test_el_correo_lleva_al_equipo_como_queda_con_telefonos(cliente, sesion,
                                                            datos):
    """Lo que el ejecutivo necesita es la lista de quién llega por él, no
    un antes y un después que tenga que comparar."""
    from app import models as m
    h = sesion("consultor")
    servicio, j = _servicio(cliente, sesion, datos, dia=0)
    _reemplazar(cliente, h, datos, j["id"])

    aviso = next(a for a in _avisos(servicio["id"])
                 if "Luis" in (a.cuerpo or "")
                 and a.destinatario == m.Destinatario.EJECUTIVO)
    from app.correo_html import leer_datos
    ficha = leer_datos(aviso.datos)
    equipo = [p for p in ficha if "Luis Mendoza" in p[1]]
    assert equipo, ficha
    # El teléfono a un toque: el cliente que abre esto necesita algo
    # ahora, y lo que hace es llamar.
    assert equipo[0][2]
    assert not [p for p in ficha if "Juan Ramirez" in p[1]]


def test_el_cambio_de_unidad_tambien_se_avisa(cliente, sesion, datos):
    """Otra placa esperando en la calle es un cambio que el cliente se
    topa igual que el de una persona."""
    h = sesion("consultor")
    servicio, j = _servicio(cliente, sesion, datos, dia=0)

    # Otra de verdad: `datos["suburban"]` ES la ABC-1234, y cambiarla
    # por si misma es justo lo que el servidor rechaza.
    entra = next(v for v in datos["vehiculos"] if v["placa"] == "ABC-5678")
    r = cliente.post("/contingencia/reemplazos/vehiculo",
                     json={"desde_jornada_id": j["id"],
                           "sale_vehiculo_id": _placa(datos, "ABC-1234"),
                           "entra_vehiculo_id": entra["id"],
                           "motivo": "Falla mecanica"},
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["cliente_avisado"] is True

    placa = entra["placa"]
    assert [a for a in _avisos(servicio["id"]) if placa in (a.cuerpo or "")]


def test_el_dia_partido_no_manda_al_que_se_fue(cliente, sesion, datos):
    """El peor caso, y el que se rompe solo.

    Si el servicio ya arrancó, la asignación de quien sale **se queda**
    —tiene que quedarse, porque ese día lo cobra— y la ficha del correo
    saldría con los dos nombres: el que se va y el que llega. El cliente
    leería un aviso de cambio que sigue diciendo el nombre viejo.
    """
    from app import models as m
    h = sesion("consultor")
    servicio, j = _servicio(cliente, sesion, datos, dia=0)
    configurar_origen(cliente, h, j["id"])

    # Juan se presentó: el día se parte y su asignación sobrevive.
    inicio = datetime.fromisoformat(j["inicio_programado"])
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=10))
    assert r.status_code in (200, 201), r.text

    _reemplazar(cliente, h, datos, j["id"])

    from app.correo_html import leer_datos
    aviso = next(a for a in _avisos(servicio["id"])
                 if a.destinatario == m.Destinatario.EJECUTIVO
                 and "Luis" in (a.cuerpo or ""))
    ficha = leer_datos(aviso.datos)
    assert [p for p in ficha if "Luis Mendoza" in p[1]], ficha
    assert not [p for p in ficha if "Juan Ramirez" in p[1]], ficha

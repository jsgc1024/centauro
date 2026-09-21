# -*- coding: utf-8 -*-
"""La hora de la marca y el orden del día.

Dos candados que faltaban, encontrados en la revisión del 20 de
septiembre.

**La hora la ponía el teléfono y nadie la revisaba.** La app puede
marcar sin señal y mandar después —por eso existe `marcado_en`—, pero
sin cota eso abría tres puertas: la ventana de horario se evalúa contra
esa hora, una hora futura hacía que la marca no se detectara como
diferida, y en el fin de servicio esa hora fija `fin_real`, de donde
salen las horas extra que se le facturan al cliente y se le pagan a la
gente.

**Y el día se podía cerrar sin haber llegado.** Solo el contacto con el
ejecutivo pedía un hito previo; el fin de servicio no pedía nada.
"""
from datetime import datetime, timedelta

from ayudas import (DENTRO, asignar, configurar_origen, crear_servicio,
                    jornada, manana, marcar)


def _dia(cliente, sesion, datos, offset):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def test_una_marca_del_futuro_no_se_toma_como_buena(cliente, sesion, datos):
    """Con la hora del teléfono, alguien podía marcar puntual a cualquier
    hora y saltarse la ventana. Ahora se guarda la del servidor.

    No se rechaza la marca: un teléfono con el reloj mal dejaría a
    alguien parado en la calle sin poder marcar.

    El servicio es de HOY a propósito: el candado se revisa el día del
    servicio, que es cuando las marcas ocurren de verdad y cuando el
    engaño serviría de algo.
    """
    servicio, j = _dia(cliente, sesion, datos, 0)
    # Doce horas adelante del reloj de quien corre esto: futuro en
    # cualquier huso, sin depender de a qué hora sea la jornada.
    del_futuro = datetime.now() + timedelta(hours=12)

    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen", del_futuro)
    assert r.status_code == 200, r.text
    cuerpo = r.json()

    assert cuerpo["requiere_revision"] is True
    assert any("adelantado" in a for a in cuerpo["avisos"]), cuerpo["avisos"]
    # La hora guardada es la del servidor, no la que mandó el teléfono.
    guardada = datetime.fromisoformat(cuerpo["marcado_en"])
    assert guardada < del_futuro


def test_el_dia_no_se_cierra_sin_haber_llegado(cliente, sesion, datos):
    """Una llamada directa dejaba la jornada terminada, fijaba la hora de
    cierre y le mandaba al cliente el correo de "servicio terminado"."""
    servicio, j = _dia(cliente, sesion, datos, 640)
    fin = datetime.fromisoformat(j["fin_programado"])

    r = cliente.post(f"/operacion/jornadas/{j['id']}/hitos",
                     headers=sesion("juan"),
                     json={"tipo": "fin_servicio", "marcado_en": fin.isoformat(),
                           **DENTRO})
    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    assert "llegada" in detalle["mensaje"]
    # Y dice qué hacer, que es lo que le falta a un error en la calle.
    assert "consultor" in detalle["que_hacer"]

    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        jornada_guardada = db.get(m.Jornada, j["id"])
        assert jornada_guardada.fin_real is None
        assert jornada_guardada.estatus != m.EstatusJornada.TERMINADA


def test_el_dia_normal_sigue_pasando(cliente, sesion, datos):
    """El candado nuevo no le estorba a quien trabaja."""
    servicio, j = _dia(cliente, sesion, datos, 660)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    h = sesion("juan")

    assert marcar(cliente, h, j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    r = marcar(cliente, h, j["id"], "contacto_ejecutivo", inicio)
    assert r.status_code == 200, r.text
    assert r.json()["requiere_revision"] is False


def test_una_marca_diferida_de_verdad_sigue_valiendo(cliente, sesion, datos):
    """Marcar sin señal y mandar después es el caso para el que existe
    `marcado_en`: eso no se toca."""
    servicio, j = _dia(cliente, sesion, datos, 680)
    inicio = datetime.fromisoformat(j["inicio_programado"])

    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=5))
    assert r.status_code == 200, r.text
    guardada = datetime.fromisoformat(r.json()["marcado_en"])
    # Se respeta la hora que dijo el teléfono: es del pasado.
    assert guardada == inicio - timedelta(minutes=5)

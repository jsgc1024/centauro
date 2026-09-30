# -*- coding: utf-8 -*-
"""Seccion 106: los casos reportados desde Connect (Manual -> Casos).

Los seis casos abiertos al 30 de septiembre: la foto de la unidad (1),
reconfirmar cuando cambia la hora (2), los campos obligatorios con
asterisco (3), el telefono del principal y el hotel en la app (7), la
entrega de la unidad antes del fin (8) y el plazo de los viaticos (9).
"""
import os
import re

import pytest

from app import models as m
from ayudas import ORIGEN, asignar, crear_servicio, jornada, manana

WEB = os.path.join(os.path.dirname(__file__), "..", "app", "web")


def _js(nombre: str) -> str:
    return open(os.path.join(WEB, nombre), encoding="utf-8").read()


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def salieron(monkeypatch):
    """Los avisos al telefono que se habrian mandado, sin salir a internet."""
    import pywebpush
    from app import push
    mandados = []

    def falso(**kwargs):
        mandados.append(kwargs)
        return True
    monkeypatch.setattr(pywebpush, "webpush", falso)
    monkeypatch.setattr(push.settings, "vapid_private", "llave-de-prueba")
    monkeypatch.setattr(push.settings, "vapid_public", "publica-de-prueba")
    return mandados


def _telefono(db, persona_id, endpoint="https://push.example/106"):
    db.add(m.SuscripcionPush(persona_id=persona_id, endpoint=endpoint,
                             p256dh="clave-publica", auth="secreto"))
    db.commit()


def _dia(datos, cuando, hora="07:00:00"):
    return jornada(manana(cuando), datos["modalidades"]["full_day"]["id"],
                   hora=hora, **ORIGEN)


def _ficha(cliente, cabeceras, j):
    """La ficha de ese dia en la app, con el reloj puesto en su manana."""
    dia = cliente.get(f"/campo/mi-dia?ahora={j['fecha']}T06:00:00",
                      headers=cabeceras).json()
    return next(f for f in dia["hoy"] + dia["manana"]
                if f["jornada_id"] == j["id"])


# ============================== caso 2 · cambio la hora: reconfirmar

def test_cambiar_la_hora_pide_reconfirmar_a_quien_ya_habia_confirmado(
        cliente, sesion, datos, db, salieron):
    """Juan confirmo de enterado para las 07:00 y el consultor mueve el
    dia a las 08:30. Juan vuelve a quedar por confirmar, con la razon
    anotada; su app se lo pide otra vez y el aviso al telefono lo dice."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(cliente, h, datos, [_dia(datos, 19)])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)
    _telefono(db, juan)
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=sesion("juan"))
    assert r.status_code == 200, r.text
    ficha = _ficha(cliente, sesion("juan"), j)
    assert ficha["confirmado"] is True and ficha["reconfirmar"] is False

    r = cliente.patch(f"/servicios/jornadas/{j['id']}",
                      json={"hora_presentacion": "08:30:00"}, headers=h)
    assert r.status_code == 200, r.text

    fila = (db.query(m.AsignacionPersonal)
            .filter_by(jornada_id=j["id"], persona_id=juan).one())
    db.refresh(fila)
    assert fila.confirmado is False
    assert fila.confirmado_en is None
    assert fila.nota_confirmacion.startswith("por reconfirmar")
    assert "07:00" in fila.nota_confirmacion
    ficha = _ficha(cliente, sesion("juan"), j)
    assert ficha["confirmado"] is False and ficha["reconfirmar"] is True
    assert len(salieron) == 1, salieron
    assert "confirmar de enterado" in str(salieron[0]["data"])

    # La central ve el pendiente con su razon en la vispera.
    manana_ = cliente.get(f"/central/manana?ahora={j['fecha']}T18:00:00",
                          headers=sesion("central")).json()
    filas = [x for s in manana_ for x in s.get("personal", [])] \
        if isinstance(manana_, list) else []
    mio = [x for x in filas if x.get("persona_id") == juan]
    if mio:
        assert mio[0]["confirmado"] is False
        assert (mio[0]["nota_confirmacion"] or "").startswith("por reconfirmar")
    # ...y la pantalla pinta esa razon junto al "?", que antes se callaba.
    assert "p.nota_confirmacion" in _js("central.js")

    # Vuelve a confirmar y la nota se queda como quedo: ya no es "por".
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=sesion("juan"))
    assert r.status_code == 200, r.text
    ficha = _ficha(cliente, sesion("juan"), j)
    assert ficha["confirmado"] is True and ficha["reconfirmar"] is False


def test_sin_cambio_de_hora_no_se_toca_la_confirmacion(
        cliente, sesion, datos, db, salieron):
    """Corregir el dia sin mover la hora (los km) no le pide nada a
    nadie: la confirmacion sigue en pie y no sale aviso."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(cliente, h, datos, [_dia(datos, 20)])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)
    _telefono(db, juan)
    cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                 headers=sesion("juan"))
    r = cliente.patch(f"/servicios/jornadas/{j['id']}",
                      json={"km_estimados": 120}, headers=h)
    assert r.status_code == 200, r.text
    fila = (db.query(m.AsignacionPersonal)
            .filter_by(jornada_id=j["id"], persona_id=juan).one())
    db.refresh(fila)
    assert fila.confirmado is True
    assert not salieron


# ================== caso 7 · el telefono del principal y el hotel

def test_la_app_trae_el_telefono_del_principal_y_su_hotel(
        cliente, sesion, datos):
    """El equipo buscaba en la app a quien llamar y donde duerme el
    ejecutivo, y solo estaban en la hoja. Ahora viajan en mi-dia."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(cliente, h, datos, [_dia(datos, 21)],
                              ejecutivo_telefono="+52 55 4444 1212")
    equipo = servicio["equipos"][0]
    j = equipo["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)
    r = cliente.post("/hospedajes", json={
        "equipo_id": equipo["id"], "nombre_libre": "hyatt regency polanco",
        "direccion_libre": "Campos Eliseos 204, Polanco",
        "telefono_libre": "+52 55 5083 1234"}, headers=h)
    assert r.status_code == 201, r.text

    ficha = _ficha(cliente, sesion("juan"), j)
    assert ficha["ejecutivo_telefono"] == "+52 55 4444 1212"
    assert len(ficha["hospedaje"]) == 1
    hotel = ficha["hospedaje"][0]
    assert hotel["hotel"] == "Hyatt Regency Polanco"
    assert hotel["direccion"] == "Campos Eliseos 204, Polanco"
    assert hotel["telefono"] == "+52 55 5083 1234"


def test_sin_hotel_ni_telefono_la_ficha_no_inventa(cliente, sesion, datos):
    """Un servicio sin hotel capturado y sin telefono del principal: la
    lista va vacia y el telefono nulo, y la app no pinta el renglon."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(cliente, h, datos, [_dia(datos, 22)])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)
    ficha = _ficha(cliente, sesion("juan"), j)
    assert ficha["hospedaje"] == []
    assert ficha.get("ejecutivo_telefono") in (None, "")
    app = _js("campo/app.js")
    assert "function hospedaje(f)" in app
    assert ".filter(x => x.hotel)" in app
    assert 'href: `tel:${f.ejecutivo_telefono}`' in app


# ======================== casos 1, 3, 8 y 9 · lo que dice la pantalla

def test_la_app_pone_la_entrega_de_la_unidad_antes_del_fin():
    """Con la unidad por entregar hoy, el boton de terminar no se ofrece
    todavia: primero la entrega, y el letrero dice que el fin aparece
    despues. El servidor sigue rechazando el fin sin entrega (seccion
    98); esto evita que el equipo se tope con ese rechazo."""
    app = _js("campo/app.js")
    assert 'const finDespues = paso === "fin_servicio" && porEntregar.length > 0;' in app
    assert "} else if (paso && !finDespues) {" in app
    assert 't("cmp_fin_despues_de_entregar")' in app
    idioma = _js("idioma.js")
    assert idioma.count("cmp_fin_despues_de_entregar:") == 3
    assert idioma.count("cmp_reconfirmar:") == 3
    assert idioma.count("cmp_hotel:") == 3


def test_los_campos_obligatorios_llevan_asterisco():
    """El asterisco sale de campo(..., {obligatorio: true}) y de
    `requerido` en Catalogos; las altas del eventual y del implantado,
    la incidencia, el titular, cancelar, la cotizacion y accesos lo
    traen, con la leyenda al pie."""
    util = _js("util.js")
    assert "export function campo(etiqueta, control, opciones = {})" in util
    assert 'clase: "obligatorio"' in util
    assert "export function pieObligatorios()" in util
    assert "obligatorio: !!c.requerido" in _js("catalogos_pantalla.js")
    for archivo, cuantos in (("consultor.js", 7), ("implantado.js", 6),
                             ("incidencias.js", 4), ("titular.js", 2),
                             ("servicio.js", 1), ("accesos.js", 2)):
        assert _js(archivo).count("{ obligatorio: true }") >= cuantos, archivo
    assert _js("cotizacion.js").count('clase: "obligatorio"') == 2
    assert "pieObligatorios()" in _js("consultor.js")
    assert "pieObligatorios()" in _js("implantado.js")
    idioma = _js("idioma.js")
    assert idioma.count("obligatorio_pie:") == 3
    assert ".campo label .obligatorio" in _js("estilo.css")


def test_el_cuadro_sin_foto_dice_de_donde_sale_la_foto():
    """La foto de la unidad es la de su categoria (Catalogos) y la de la
    persona viene de Odoo: sin foto, el cuadro lo dice en vez de quedar
    en gris."""
    servicio = _js("servicio.js")
    assert '"sin-foto-de"' in servicio
    assert 'tipo === "retrato" ? "srv_sin_foto_persona"' in servicio
    idioma = _js("idioma.js")
    assert idioma.count("srv_sin_foto_unidad:") == 3
    assert re.search(r'srv_sin_foto_unidad: ".*Cat[aá]logos', idioma)
    assert ".foto.sin-foto-de" in _js("estilo.css")


def test_el_plazo_de_los_viaticos_ya_se_ve_en_pagos():
    """Caso 9: el reloj de las 24 horas para comprobar ya estaba en
    Pagos (cuando el servicio termina); lo que se ve antes de terminar
    es que el plazo corre al terminar. Queda como esta, y esta prueba lo
    deja escrito."""
    app = _js("campo/app.js")
    assert "function cuandoVence(s)" in app
    assert 't("cmp_vence")' in app and 't("cmp_plazo_al_terminar")' in app
    assert "te quedan {queda}" in _js("idioma.js")

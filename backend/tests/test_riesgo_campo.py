"""El riesgo cerca del servicio, en la app de campo (seccion 137).

Lo que se cuida: en la tarjeta de Hoy solo lo vigente de nivel 2 o mas a
25 km o menos del punto de encuentro; al telefono solo el 3 y el 4, una
vez por evento, persona y nivel; el detalle solo a quien le toca.
"""
from datetime import datetime, timedelta, timezone
from unittest import mock

from ayudas import asignar, configurar_origen, crear_servicio, jornada, manana

from app import models as m
from app import riesgo_campo
from app.db import SessionLocal
from tests.test_riesgo_clientes import cat  # noqa: F401

AHORA = datetime.now(timezone.utc).replace(microsecond=0)
# El punto de las pruebas es Av. Reforma 222, CDMX (ayudas.ORIGEN).
CERCA = {"lat": 19.4500, "lon": -99.1500}       # unos 3 km
LEJOS = {"lat": 25.6700, "lon": -100.3100}      # Monterrey


def _dia_de_juan(cliente, sesion, datos, dia=0):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(dia), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"])[0]
    assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def _publicar(cliente, sesion, cat, nivel, donde, region="Ciudad de México",  # noqa: F811
              titulo="Bloqueo en Reforma", radio_m=500):
    e = cliente.post("/riesgo/eventos", json={
        "pais_id": cat["pais_id"], "region_id": cat["regiones"][region],
        "tipo_id": cat["tipos"]["Bloqueo carretero"], "nivel": nivel,
        "titulo": titulo, "texto_cliente": "Eviten la zona por ahora.",
        "lat": donde["lat"], "lon": donde["lon"], "radio_m": radio_m,
        "ocurrio_en": (AHORA - timedelta(minutes=5)).isoformat(),
        "vigente_hasta": (AHORA + timedelta(hours=6)).isoformat(),
    }, headers=sesion("central"))
    assert e.status_code == 200, e.text
    e = e.json()
    r = cliente.post(f"/riesgo/eventos/{e['id']}/publicar",
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    if nivel == 4:
        r = cliente.post(f"/riesgo/eventos/{e['id']}/confirmar",
                         headers=sesion("diroperaciones"))
        assert r.status_code == 200, r.text
    return r.json()


def test_la_distancia():
    # De Reforma 222 al Zocalo, unos 4 km en linea recta.
    km = riesgo_campo.distancia_km(19.4270, -99.1677, 19.4326, -99.1332)
    assert 3.4 < km < 4.0


def test_la_tarjeta_trae_lo_cercano(cliente, sesion, datos, cat):  # noqa: F811
    _dia_de_juan(cliente, sesion, datos)
    cerca = _publicar(cliente, sesion, cat, 2, CERCA)
    _publicar(cliente, sesion, cat, 3, LEJOS, region="Nuevo León",
              titulo="Bloqueo lejano en Monterrey")
    _publicar(cliente, sesion, cat, 1, CERCA, titulo="Aviso informativo en Reforma")
    dia = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    assert [e["id"] for e in dia["riesgo_cerca"]] == [cerca["id"]]
    e = dia["riesgo_cerca"][0]
    assert 2 < e["km"] < 4 and e["servicio"]
    assert "fuentes" not in e
    # Quien no trabaja hoy no ve nada.
    otro = cliente.get("/campo/mi-dia", headers=sesion("luis")).json()
    assert otro["riesgo_cerca"] == []


def test_el_aviso_al_telefono_es_del_3_y_4(cliente, sesion, datos, cat):  # noqa: F811
    _dia_de_juan(cliente, sesion, datos)
    db = SessionLocal()
    try:
        db.add(m.SuscripcionPush(
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            endpoint="https://fcm.googleapis.com/fcm/send/juan",
            p256dh="x", auth="y"))
        db.commit()
    finally:
        db.close()
    with mock.patch("app.push.hay_llaves", return_value=True), \
            mock.patch("pywebpush.webpush") as webpush:
        _publicar(cliente, sesion, cat, 2, CERCA, titulo="Bloqueo nivel dos en Reforma")
        assert webpush.call_count == 0
        tres = _publicar(cliente, sesion, cat, 3, CERCA, titulo="Bloqueo nivel tres en Reforma")
        assert webpush.call_count == 1
        carga = webpush.call_args.kwargs["data"]
        assert f"/app/#/riesgo/{tres['id']}" in carga
        assert "Riesgo nivel 3 cerca de tu servicio" in carga
        _publicar(cliente, sesion, cat, 3, LEJOS, region="Nuevo León",
                  titulo="Bloqueo lejano en Monterrey")
        assert webpush.call_count == 1
    db = SessionLocal()
    try:
        aviso = db.query(m.AvisoRiesgoCampo).one()
        assert aviso.evento_id == tres["id"] and aviso.telefonos == 1
    finally:
        db.close()
    bitacora = cliente.get(f"/riesgo/eventos/{tres['id']}",
                           headers=sesion("central")).json()["bitacora"]
    assert any(b["accion"] == "aviso_campo" for b in bitacora)


def test_sin_punto_no_se_mide(cliente, sesion, datos, cat):  # noqa: F811
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(0), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"])
    _publicar(cliente, sesion, cat, 3, CERCA)
    dia = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    assert dia["riesgo_cerca"] == []


def test_el_detalle_solo_a_quien_le_toca(cliente, sesion, datos, cat):  # noqa: F811
    _dia_de_juan(cliente, sesion, datos)
    cerca = _publicar(cliente, sesion, cat, 3, CERCA)
    lejos = _publicar(cliente, sesion, cat, 3, LEJOS, region="Nuevo León",
                      titulo="Bloqueo lejano en Monterrey")
    r = cliente.get(f"/campo/riesgo/{cerca['id']}", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert r.json()["texto"] == "Eviten la zona por ahora."
    assert cliente.get(f"/campo/riesgo/{lejos['id']}",
                       headers=sesion("juan")).status_code == 404
    assert cliente.get(f"/campo/riesgo/{cerca['id']}",
                       headers=sesion("luis")).status_code == 404

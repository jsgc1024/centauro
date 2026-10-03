"""Respuesta a emergencias (seccion 145).

Lo que se cuida:
- el panico del cliente de la Central llega al panel con su ubicacion, una
  sola alerta aunque apriete dos veces, y su recorrido mientras siga
  abierta;
- el area la toma, manda al equipo, anota a las autoridades y la cierra
  con su resolucion; el cliente ve quien lo atiende y que se cerro;
- lo de EP no se rompe: el panico de la app de campo llega tambien al
  panel, tomarlo en la central se ve en el panel, y el del cliente no se
  mete a la central ni al panorama;
- solo entra quien debe: ni la central, ni el cliente, ni la app de campo
  con un panico ajeno.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app import emergencias, puestos_base
from app import models as m
from app.db import SessionLocal
from tests.test_cliente_ci import _entrar
from tests.test_riesgo_clientes import cat, cliente_ci, publicar  # noqa: F401

GUARDIA = "finanzas@centauro.lat"        # se le pone el rol en la prueba
DONDE = {"lat": 25.68, "lon": -100.31, "precision": 12}


@pytest.fixture
def guardia(cliente, base_de_pruebas):
    """Alguien de Respuesta a emergencias, entrando con su rol."""
    with base_de_pruebas.begin() as con:
        antes = con.execute(text(
            "SELECT id, rol, categoria_id FROM usuario WHERE correo = :c"),
            {"c": GUARDIA}).one()
        con.execute(text("UPDATE usuario SET rol = 'RESPUESTA_EMERGENCIAS', "
                         "categoria_id = NULL WHERE correo = :c"),
                    {"c": GUARDIA})
    r = cliente.post("/auth/token",
                     data={"username": GUARDIA, "password": "centauro2026"})
    assert r.status_code == 200, r.text
    yield {"Authorization": f"Bearer {r.json()['access_token']}"}
    with base_de_pruebas.begin() as con:
        con.execute(text("UPDATE usuario SET rol = :r, categoria_id = :c "
                         "WHERE id = :id"),
                    {"r": antes.rol, "c": antes.categoria_id, "id": antes.id})


@pytest.fixture
def gente(cliente, cliente_ci):  # noqa: F811
    """La sesion del gerente del cliente de la Central."""
    return _entrar(cliente, cliente_ci)


def _atrasar_ubicacion(alerta_id, segundos=30):
    """La app manda cada 15 s; la prueba no espera: corre el reloj de la
    ultima ubicacion hacia atras."""
    db = SessionLocal()
    try:
        a = db.get(m.AlertaIncidencia, alerta_id)
        a.ubicacion_en = a.ubicacion_en - timedelta(seconds=segundos)
        db.commit()
    finally:
        db.close()


def test_el_panico_del_cliente_llega_al_panel(cliente, gente, guardia):
    r = cliente.post("/ci-api/emergencia", json=DONDE, headers=gente)
    assert r.status_code == 200, r.text
    mia = r.json()
    assert mia["abierta"] is True and mia["atiende"] is None
    assert mia["telefono"] and mia["cada_segundos"] == 15
    # Apretar otra vez (o que la app reintente) no levanta otra.
    otra = cliente.post("/ci-api/emergencia", json=DONDE, headers=gente).json()
    assert otra["id"] == mia["id"]

    panel = cliente.get("/emergencias", headers=guardia).json()
    assert panel["sin_tomar"] == 1
    [a] = panel["activas"]
    assert a["canal"] == "boton_ci" and a["quien"] == "Andrés Saucedo"
    assert a["lat"] == pytest.approx(25.68)
    ficha = cliente.get(f"/emergencias/{a['id']}", headers=guardia).json()
    assert ficha["telefono_de_quien"] == "+52 55 1234 5678"
    assert [b["accion"] for b in ficha["bitacora"]] == ["levanto", "otra_vez"]
    assert len(ficha["puntos"]) == 1


def test_su_recorrido_mientras_siga_abierta(cliente, gente, guardia):
    mia = cliente.post("/ci-api/emergencia", json=DONDE, headers=gente).json()
    # Dos lecturas mas juntas que 5 s son una.
    cliente.post("/ci-api/emergencia/ubicacion",
                 json={"lat": 25.69, "lon": -100.32}, headers=gente)
    _atrasar_ubicacion(mia["id"])
    r = cliente.post("/ci-api/emergencia/ubicacion",
                     json={"lat": 25.70, "lon": -100.33, "precision": 8},
                     headers=gente)
    assert r.json()["abierta"] is True
    # Una coordenada imposible no entra.
    _atrasar_ubicacion(mia["id"])
    cliente.post("/ci-api/emergencia/ubicacion",
                 json={"lat": 125, "lon": -100.33}, headers=gente)
    ficha = cliente.get(f"/emergencias/{mia['id']}", headers=guardia).json()
    assert [p["lat"] for p in ficha["puntos"]] == [25.68, 25.70]
    assert ficha["precision_m"] == 8


def test_el_area_la_atiende_y_el_cliente_lo_ve(cliente, gente, guardia):
    mia = cliente.post("/ci-api/emergencia", json=DONDE, headers=gente).json()
    aid = mia["id"]
    # Antes de tomarla no se anota nada ni se cierra.
    assert cliente.post(f"/emergencias/{aid}/equipo", json={},
                        headers=guardia).status_code == 409
    r = cliente.post(f"/emergencias/{aid}/tomar", headers=guardia)
    assert r.status_code == 200, r.text
    assert r.json()["estatus"] == "en_atencion"
    # Dos de la guardia no la toman los dos.
    assert cliente.post(f"/emergencias/{aid}/tomar",
                        headers=guardia).status_code == 409
    atiende = cliente.get("/ci-api/emergencia", headers=gente).json()["atiende"]
    assert atiende                      # el cliente ve quien lo atiende

    assert cliente.post(f"/emergencias/{aid}/equipo",
                        json={"nota": "Unidad 9 en camino"},
                        headers=guardia).json()["equipo_enviado"] is True
    assert cliente.post(f"/emergencias/{aid}/autoridades", json={"nota": "911"},
                        headers=guardia).json()["autoridades"] is True
    assert cliente.post(f"/emergencias/{aid}/cerrar",
                        json={"resolucion": "corto"},
                        headers=guardia).status_code == 400
    r = cliente.post(f"/emergencias/{aid}/cerrar",
                     json={"resolucion": "El equipo llegó; estaba a salvo."},
                     headers=guardia)
    assert r.status_code == 200, r.text
    acciones = [b["accion"] for b in r.json()["bitacora"]]
    assert acciones == ["levanto", "tomo", "equipo", "autoridades", "cerro"]

    # Cerrada: el cliente lo ve, su telefono deja de mandar, y el panel la
    # quita de lo activo.
    assert cliente.get("/ci-api/emergencia",
                       headers=gente).json()["abierta"] is False
    assert cliente.post("/ci-api/emergencia/ubicacion", json=DONDE,
                        headers=gente).json()["abierta"] is False
    panel = cliente.get("/emergencias", headers=guardia).json()
    assert panel["activas"] == [] and panel["dia"]["cerradas"] == 1
    assert panel["dia"]["para_tomar_s"] is not None
    # Y un nuevo panico es otra alerta.
    nueva = cliente.post("/ci-api/emergencia", json=DONDE, headers=gente).json()
    assert nueva["id"] != aid


def test_dijo_que_fue_un_error_y_sigue_abierta(cliente, gente, guardia):
    assert cliente.post("/ci-api/emergencia/error",
                        headers=gente).status_code == 404
    mia = cliente.post("/ci-api/emergencia", json={}, headers=gente).json()
    r = cliente.post("/ci-api/emergencia/error", headers=gente)
    assert r.json()["dijo_error"] is True and r.json()["abierta"] is True
    [a] = cliente.get("/emergencias", headers=guardia).json()["activas"]
    assert a["id"] == mia["id"] and a["dijo_error"] is True
    assert a["lat"] is None            # sin ubicacion la alerta sale igual


def test_la_ficha_dice_que_hay_cerca_y_a_quien_llamar(
        cliente, sesion, gente, guardia, cliente_ci, publicar):  # noqa: F811
    publicar(nivel=3, lat=25.70, lon=-100.30)
    publicar(nivel=2, lat=19.43, lon=-99.13)        # lejos: no sale
    cc = cliente.get("/riesgo/clientes",
                     headers=sesion("diroperaciones")).json()[0]
    r = cliente.put(f"/riesgo/clientes/{cc['id']}/emergencia",
                    json={"contacto": "María Torres, seguridad",
                          "telefono": "+52 81 5566 7788"},
                    headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    assert r.json()["telefono_emergencia"] == "+52 81 5566 7788"
    assert cliente.put(f"/riesgo/clientes/{cc['id']}/emergencia",
                       json={"telefono": "llamar a María"},
                       headers=sesion("diroperaciones")).status_code == 400

    mia = cliente.post("/ci-api/emergencia", json=DONDE, headers=gente).json()
    ficha = cliente.get(f"/emergencias/{mia['id']}", headers=guardia).json()
    assert [e["nivel"] for e in ficha["riesgo_cerca"]] == [3]
    assert ficha["contactos"] == [{"nombre": "María Torres, seguridad",
                                   "telefono": "+52 81 5566 7788",
                                   "que": "cliente"}]


def test_el_panico_de_campo_tambien_llega_y_se_ve_quien_lo_toma(
        cliente, sesion, datos, guardia):
    r = cliente.post("/contingencia/alertas", headers=sesion("juan"),
                     json={"canal": "boton_app",
                           "lat": "19.4270", "lon": "-99.1677"})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    [a] = cliente.get("/emergencias", headers=guardia).json()["activas"]
    assert a["canal"] == "boton_app" and a["quien"] == "Juan Ramirez"

    # La app de campo manda donde va; solo quien la levanto.
    _atrasar_ubicacion(aid)
    r = cliente.post(f"/contingencia/alertas/{aid}/ubicacion",
                     json={"lat": 19.43, "lon": -99.17, "precision": 20},
                     headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert cliente.post(f"/contingencia/alertas/{aid}/ubicacion",
                        json={"lat": 19.43, "lon": -99.17},
                        headers=sesion("luis")).status_code == 404

    # La central la toma: el panel dice quien.
    r = cliente.post(f"/contingencia/alertas/{aid}/tomar",
                     json={"equipo_respuesta_enviado": False},
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    ficha = cliente.get(f"/emergencias/{aid}", headers=guardia).json()
    assert ficha["estatus"] == "en_atencion" and ficha["atiende"]
    assert [b["accion"] for b in ficha["bitacora"]] == ["levanto", "tomo"]
    # Y la cierra el area: la central la ve cerrada.
    r = cliente.post(f"/emergencias/{aid}/cerrar",
                     json={"resolucion": "Falsa alarma confirmada por teléfono"},
                     headers=guardia)
    assert r.status_code == 200, r.text
    abiertas = cliente.get("/contingencia/alertas",
                           headers=sesion("central")).json()
    assert aid not in [x["id"] for x in abiertas]
    # Cerrada, la app de campo deja de mandar.
    _atrasar_ubicacion(aid)
    assert cliente.post(f"/contingencia/alertas/{aid}/ubicacion",
                        json={"lat": 19.43, "lon": -99.17},
                        headers=sesion("juan")).status_code == 409


def test_el_del_cliente_no_se_mete_a_la_operacion_de_ep(
        cliente, sesion, gente, datos):
    from app import central, panorama
    cliente.post("/ci-api/emergencia", json=DONDE, headers=gente)
    assert cliente.get("/contingencia/alertas",
                       headers=sesion("central")).json() == []
    db = SessionLocal()
    try:
        assert central.tablero(db, datetime.now())["roto"]["panico"] == []
        assert panorama._alertas(db) == []
    finally:
        db.close()
    # Y nadie lo levanta por la puerta de EP.
    r = cliente.post("/contingencia/alertas", headers=sesion("juan"),
                     json={"canal": "boton_ci"})
    assert r.status_code == 400


def test_solo_entra_quien_debe(cliente, sesion, gente, guardia):
    mia = cliente.post("/ci-api/emergencia", json=DONDE, headers=gente).json()
    # La central sigue con lo suyo; el panel es del area.
    assert cliente.get("/emergencias",
                       headers=sesion("central")).status_code == 403
    assert cliente.post(f"/emergencias/{mia['id']}/tomar",
                        headers=sesion("consultor")).status_code == 403
    # La sesion del cliente no abre la consola.
    assert cliente.get("/emergencias", headers=gente).status_code == 401
    # Direccion de operaciones, el respaldo, si.
    assert cliente.get("/emergencias",
                       headers=sesion("diroperaciones")).status_code == 200
    # Y el area no ve el resto de la casa.
    assert cliente.get("/central/tablero",
                       headers=guardia).status_code == 403


def test_el_puesto_y_la_migracion_dicen_lo_mismo():
    import importlib
    migracion = importlib.import_module(
        "migrations.versions.a5c7e9b1d3f6_respuesta_a_emergencias")
    puesto = next(p for p in puestos_base.PUESTOS
                  if p["nombre"] == migracion.NOMBRE)
    assert puesto["rol"] == m.Rol.RESPUESTA_EMERGENCIAS
    assert puesto["area"] == migracion.AREA
    assert puesto["descripcion"] == migracion.DESCRIPCION
    assert puesto["pantallas"] == migracion.PANTALLAS.split(",")
    assert puesto["actividades"] == set(migracion.ACTIVIDADES)
    assert puesto["puestos_odoo"] == migracion.PUESTOS_ODOO
    operaciones = next(p for p in puestos_base.PUESTOS
                       if p["rol"] == m.Rol.DIRECTOR_OPERACIONES)
    assert "emergencias" in operaciones["pantallas"]


def test_el_folio_y_el_telefono():
    a = m.AlertaIncidencia(id=31)
    assert emergencias.folio(a) == "E-0031"
    assert emergencias.telefono()


def test_la_central_no_pisa_lo_que_el_area_ya_tomo(cliente, sesion, datos,
                                                   guardia):
    aid = cliente.post("/contingencia/alertas", headers=sesion("juan"),
                       json={"canal": "boton_app", "lat": "19.42",
                             "lon": "-99.16"}).json()["id"]
    assert cliente.post(f"/emergencias/{aid}/tomar",
                        headers=guardia).status_code == 200
    assert cliente.post(f"/emergencias/{aid}/equipo", json={},
                        headers=guardia).status_code == 200
    # La tarjeta de la central seguia ofreciendo «Tomar»: no la pisa.
    r = cliente.post(f"/contingencia/alertas/{aid}/tomar",
                     json={"equipo_respuesta_enviado": False},
                     headers=sesion("central"))
    assert r.status_code == 409
    ficha = cliente.get(f"/emergencias/{aid}", headers=guardia).json()
    assert ficha["equipo_enviado"] is True
    assert ficha["atiende"] == ficha["bitacora"][1]["quien"]


def test_la_central_no_toma_ni_cierra_el_del_cliente(cliente, sesion, gente):
    aid = cliente.post("/ci-api/emergencia", json=DONDE,
                       headers=gente).json()["id"]
    assert cliente.post(f"/contingencia/alertas/{aid}/tomar",
                        json={"equipo_respuesta_enviado": False},
                        headers=sesion("central")).status_code == 404
    assert cliente.post(f"/contingencia/alertas/{aid}/cerrar",
                        json={"resolucion": "No es de la central"},
                        headers=sesion("central")).status_code == 404


def test_el_recorrido_guarda_lo_ultimo(cliente, gente, monkeypatch):
    monkeypatch.setattr(emergencias, "MAXIMO_DE_PUNTOS", 2)
    aid = cliente.post("/ci-api/emergencia", json=DONDE,
                       headers=gente).json()["id"]
    for lat, precision in ((25.70, "5"), (25.71, "Infinity")):
        _atrasar_ubicacion(aid)
        # Un telefono que manda una precision infinita no tumba nada.
        cliente.post("/ci-api/emergencia/ubicacion",
                     content=f'{{"lat": {lat}, "lon": -100.3, '
                             f'"precision": {precision}}}',
                     headers={**gente, "Content-Type": "application/json"})
    db = SessionLocal()
    try:
        puntos = [float(p.lat) for p in db.query(m.PuntoAlerta)
                  .filter_by(alerta_id=aid).order_by(m.PuntoAlerta.id)]
        assert puntos == [25.70, 25.71]
        assert db.get(m.AlertaIncidencia, aid).precision_m is None
    finally:
        db.close()


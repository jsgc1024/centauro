# -*- coding: utf-8 -*-
"""La cotizacion autorizada, en el servicio (seccion 94).

Pieza 1 de «Para poder operar», decisiones de Salvador del 28 de
septiembre: mientras Odoo no manda la cotizacion, el consultor --o quien
lo cubre-- la registra en el servicio con los precios del tarifario del
cliente, y se autoriza con quien, el dia y el folio de Odoo si existe.

Lo que aqui se cuida:

  * La vista previa pone los precios sin guardar nada.
  * Se guarda ya autorizada, con quien, el dia y el folio.
  * Recotizar pide su motivo; la nueva nace autorizada y la de antes
    queda sustituida. Si algo falla no queda nada y la de antes sigue.
  * Los tres modos de gastos.
  * Lo asignado se ofrece para no volver a escribirlo.
  * Despues del visto bueno ya no: finanzas lo regresa.
  * Quien cubre queda anotado; finanzas no cotiza.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app import cotizacion as cotmotor
from app import models as m
from ayudas import (asignar, crear_servicio, jornada, manana,
                    servicio_para_cierre)

D = Decimal


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


def _servicio(cliente, sesion, datos, offset, dias=2):
    return crear_servicio(
        cliente, sesion("consultor"), datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"])
         for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])


def _lleva(servicio, datos, rol="conductor_seguridad", unidad="suv_blindada"):
    lineas = []
    for j in servicio["equipos"][0]["jornadas"]:
        lineas.append({"fecha": j["fecha"], "tipo": "recurso", "equipo_clave": "Alfa",
                       "perfil_id": datos["perfiles"][rol]["id"], "cantidad": 1})
        if unidad:
            lineas.append({"fecha": j["fecha"], "tipo": "vehiculo",
                           "equipo_clave": "Alfa", "cantidad": 1,
                           "categoria_id": datos["categorias"][unidad]["id"]})
    return lineas


def _autorizada(cliente, sesion, servicio, lineas, quien="consultor", **extra):
    cuerpo = {"servicio_id": servicio["id"], "lineas": lineas,
              "gastos": "comprobar", "autorizada_por": "Patricia Lundgren",
              "autorizada_el": str(date.today()), **extra}
    return cliente.post("/cotizaciones/autorizada", json=cuerpo,
                        headers=sesion(quien))


def _bloque(cliente, sesion, servicio, quien="consultor"):
    r = cliente.get(f"/cotizaciones/servicio/{servicio['id']}/bloque",
                    headers=sesion(quien))
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- armarla

def test_la_vista_previa_pone_precios_sin_guardar_nada(cliente, sesion, datos, db):
    servicio = _servicio(cliente, sesion, datos, 1400)
    r = cliente.post("/cotizaciones/vista-previa", headers=sesion("consultor"), json={
        "servicio_id": servicio["id"], "lineas": _lleva(servicio, datos),
        "gastos": "comprobar"})
    assert r.status_code == 200, r.text
    previa = r.json()
    assert previa["dias"] == 2 and previa["equipos"] == 1
    assert D(str(previa["total"])) > 0
    assert all(D(str(l["precio"])) > 0 for l in previa["lineas"])
    assert D(str(previa["total"])) == sum(D(str(l["importe"])) for l in previa["lineas"])

    db.expire_all()
    assert db.query(m.Cotizacion).filter_by(servicio_id=servicio["id"]).count() == 0
    assert db.get(m.Servicio, servicio["id"]).estatus != m.EstatusServicio.AUTORIZADO


def test_se_guarda_ya_autorizada_con_quien_el_dia_y_el_folio(cliente, sesion, datos, db):
    servicio = _servicio(cliente, sesion, datos, 1403)
    ayer = date.today() - timedelta(days=1)
    r = _autorizada(cliente, sesion, servicio, _lleva(servicio, datos),
                    autorizada_el=str(ayer), folio_odoo="  S00841 ")
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["version"] == 1 and c["estatus"] == "autorizada"
    assert c["autorizada_por"] == "Patricia Lundgren"
    assert c["autorizada_el"] == str(ayer)
    assert c["folio_odoo"] == "S00841"
    assert c["registrada_por"] == "Ana Solis"
    assert c["gastos"] == "comprobar"

    db.expire_all()
    guardada = db.query(m.Cotizacion).filter_by(servicio_id=servicio["id"]).one()
    assert guardada.estatus == m.EstatusCotizacion.AUTORIZADA
    assert guardada.viaticos_incluidos is False
    assert db.get(m.Servicio, servicio["id"]).estatus == m.EstatusServicio.AUTORIZADO
    assert db.query(m.RegistroAccion).filter_by(
        servicio_id=servicio["id"], accion="cotizar y autorizar").count() == 1

    b = _bloque(cliente, sesion, servicio)
    assert b["vigente"]["version"] == 1
    assert b["siguiente_version"] == 2


def test_sin_quien_o_con_el_dia_de_manana_no_se_guarda(cliente, sesion, datos):
    servicio = _servicio(cliente, sesion, datos, 1406)
    lineas = _lleva(servicio, datos)
    assert _autorizada(cliente, sesion, servicio, lineas,
                       autorizada_por="   ").status_code == 400
    manana_ = str(date.today() + timedelta(days=2))
    assert _autorizada(cliente, sesion, servicio, lineas,
                       autorizada_el=manana_).status_code == 400
    # Un dia que el servicio no tiene no se cotiza.
    otro = [{**lineas[0], "fecha": str(manana(5000))}]
    assert _autorizada(cliente, sesion, servicio, otro).status_code == 400
    # Y sin nada que cotizar tampoco.
    assert _autorizada(cliente, sesion, servicio, []).status_code == 400


# ---------------------------------------------------------------- recotizar

def test_recotizar_pide_motivo_y_la_de_antes_queda_sustituida(cliente, sesion,
                                                               datos, db):
    servicio = _servicio(cliente, sesion, datos, 1409)
    assert _autorizada(cliente, sesion, servicio,
                       _lleva(servicio, datos)).status_code == 201

    sin_unidad = _lleva(servicio, datos, unidad=None)
    r = _autorizada(cliente, sesion, servicio, sin_unidad)
    assert r.status_code == 400
    assert "recotiza" in r.json()["detail"]

    r = _autorizada(cliente, sesion, servicio, sin_unidad,
                    motivo="El cliente ya no quiere la unidad")
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 2
    assert r.json()["motivo"] == "El cliente ya no quiere la unidad"

    db.expire_all()
    versiones = {c.version: c.estatus for c in
                 db.query(m.Cotizacion).filter_by(servicio_id=servicio["id"])}
    assert versiones == {1: m.EstatusCotizacion.SUSTITUIDA,
                         2: m.EstatusCotizacion.AUTORIZADA}
    assert cotmotor.vigente(db, servicio["id"]).version == 2
    assert db.query(m.RegistroAccion).filter_by(
        servicio_id=servicio["id"], accion="recotizar").count() == 1


def test_si_algo_falla_no_queda_nada_y_la_de_antes_sigue(cliente, sesion, datos,
                                                          db, monkeypatch):
    servicio = _servicio(cliente, sesion, datos, 1412)
    assert _autorizada(cliente, sesion, servicio,
                       _lleva(servicio, datos)).status_code == 201

    def sin_tipo_de_cambio(*_a, **_k):
        raise HTTPException(409, {"motivo": "sin_tipo_de_cambio",
                                  "mensaje": "No hay tipo de cambio"})

    monkeypatch.setattr(cotmotor, "_autorizar", sin_tipo_de_cambio)
    r = _autorizada(cliente, sesion, servicio, _lleva(servicio, datos, unidad=None),
                    motivo="Cambio del cliente")
    assert r.status_code == 409

    db.expire_all()
    todas = db.query(m.Cotizacion).filter_by(servicio_id=servicio["id"]).all()
    assert len(todas) == 1
    assert todas[0].estatus == m.EstatusCotizacion.AUTORIZADA


# ---------------------------------------------------------------- los gastos

def test_los_tres_modos_de_gastos(cliente, sesion, datos, db):
    servicio = _servicio(cliente, sesion, datos, 1415, dias=1)
    lineas = _lleva(servicio, datos)

    def previa(gastos, monto=None):
        return cliente.post("/cotizaciones/vista-previa", headers=sesion("consultor"),
                            json={"servicio_id": servicio["id"], "lineas": lineas,
                                  "gastos": gastos, "monto_gastos": monto})

    dentro = previa("dentro").json()
    comprobar = previa("comprobar").json()
    fijo = previa("fijo", "1500").json()
    assert dentro["gastos"] == "dentro" and comprobar["gastos"] == "comprobar"
    assert fijo["gastos"] == "fijo" and D(str(fijo["gastos_fijos"])) == D("1500")
    assert D(str(fijo["total"])) == D(str(dentro["total"])) + D("1500")
    assert D(str(dentro["total"])) == D(str(comprobar["total"]))
    assert previa("fijo").status_code == 400
    assert previa("fijo", "-5").status_code == 400
    assert previa("otro").status_code == 400

    r = _autorizada(cliente, sesion, servicio, lineas, gastos="fijo",
                    monto_gastos="1500")
    assert r.status_code == 201, r.text
    db.expire_all()
    c = cotmotor.vigente(db, servicio["id"])
    assert c.viaticos_incluidos is True
    assert sum(D(str(l.subtotal)) for l in c.lineas
               if l.tipo == m.TipoLinea.VIATICOS) == D("1500")


# ---------------------------------------------------------------- lo que ofrece

def test_el_bloque_ofrece_lo_asignado_y_quien_pudo_autorizar(cliente, sesion, datos):
    servicio = _servicio(cliente, sesion, datos, 1418, dias=1)
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, sesion("consultor"), j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])

    b = _bloque(cliente, sesion, servicio)
    assert b["se_cotiza"] and b["se_puede"] and b["puede_cotizar"]
    assert b["vigente"] is None and b["siguiente_version"] == 1
    assert b["tarifario"]["moneda"] == "MXN"
    assert [d["fecha"] for d in b["dias"]] == [j["fecha"]]
    dia = b["asignado"]["Alfa"][j["fecha"]]
    assert dia["roles"] == {str(datos["perfiles"]["conductor_seguridad"]["id"]): 1}
    assert dia["unidades"] == {str(datos["categorias"]["suv_blindada"]["id"]): 1}
    assert b["quienes"][0] == {"nombre": "Patricia Lundgren", "solicita": True}
    ids_roles = {r["id"] for r in b["roles"]}
    assert datos["perfiles"]["conductor_seguridad"]["id"] in ids_roles


# ---------------------------------------------------------------- quien y cuando

def test_despues_del_visto_bueno_ya_no_se_recotiza(cliente, sesion, datos):
    servicio, _ = servicio_para_cierre(cliente, sesion, datos, offset=1421)
    b = _bloque(cliente, sesion, servicio)
    assert b["se_puede"] is False and b["con_visto_bueno"] is True
    r = _autorizada(cliente, sesion, servicio, _lleva(servicio, datos),
                    motivo="El cliente cambio algo")
    assert r.status_code == 409
    assert "finanzas" in r.json()["detail"]


def test_quien_cubre_queda_anotado_y_finanzas_no_cotiza(cliente, sesion, datos, db):
    servicio = _servicio(cliente, sesion, datos, 1424, dias=1)
    assert _autorizada(cliente, sesion, servicio, _lleva(servicio, datos),
                       quien="finanzas").status_code == 403
    r = _autorizada(cliente, sesion, servicio, _lleva(servicio, datos),
                    quien="consultor2")
    assert r.status_code == 201, r.text
    db.expire_all()
    accion = db.query(m.RegistroAccion).filter_by(
        servicio_id=servicio["id"], accion="cotizar y autorizar").one()
    assert accion.en_cobertura is True
    # Finanzas la ve, pero no la arma.
    b = _bloque(cliente, sesion, servicio, quien="finanzas")
    assert b["vigente"]["version"] == 1 and b["puede_cotizar"] is False


def test_la_revision_sin_cotizacion_apunta_al_bloque(cliente, sesion, datos):
    servicio = _servicio(cliente, sesion, datos, 1427, dias=1)
    r = cliente.get(f"/cierre/servicio/{servicio['id']}/revision",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    obs = r.json()["observaciones"]
    assert obs[0]["clave"] == "sin_cotizacion"
    assert "La cotizacion autorizada" in obs[0]["accion"]

# -*- coding: utf-8 -*-
"""Corregir los contactos del servicio (seccion 95).

Pieza 2 de «Para poder operar», decision 3 de Salvador del 28 de
septiembre: los corrigen el consultor del servicio y quien lo cubre, y
queda en la bitacora con lo de antes.

Lo que aqui se cuida:

  * Se corrige quien solicita y el principal; el telefono sale con su
    clave de pais.
  * Los avisos que no han salido y la encuesta sin contestar se van a los
    datos nuevos; lo que ya salio no se toca.
  * Quien solicita se cambia por otro de la lista, y se puede corregir en
    la lista del cliente sin duplicar a nadie.
  * Lo mal escrito no se guarda; cerrado o cancelado, ya no se corrige.
  * Si otro servicio abierto del cliente lleva el correo de antes, se dice.
  * Quien cubre queda anotado; finanzas y central no corrigen.
"""
import secrets
from datetime import datetime, timedelta

import pytest

from app import models as m
from ayudas import crear_servicio, jornada, manana

SOLICITA = {"nombre": "Patricia", "apellidos": "Lundgren",
            "correo": "patricia.lundgren@clientedemo.com",
            "telefono": "55 5550 1234", "idioma": "es"}
PRINCIPAL = {"nombre": "Ingrid", "apellidos": "Halvorsen",
             "correo": "ingrid.halvorsen@clientedemo.com",
             "telefono": "+47 912 34 567", "idioma": "en"}


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


def _servicio(cliente, sesion, datos, offset):
    return crear_servicio(
        cliente, sesion("consultor"), datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])


def _corregir(cliente, sesion, servicio, cuerpo, quien="consultor"):
    return cliente.patch(f"/servicios/{servicio['id']}/contactos", json=cuerpo,
                         headers=sesion(quien))


def _aviso(db, servicio_id, destinatario, correo, estado="pendiente"):
    aviso = m.Notificacion(servicio_id=servicio_id, destinatario=destinatario,
                           canal=m.Canal.CORREO, correo=correo, asunto="Prueba",
                           cuerpo="Prueba", estado=estado)
    db.add(aviso)
    db.commit()
    return aviso.id


# ---------------------------------------------------------------- corregir

def test_corrige_a_quien_solicita_y_al_principal(cliente, sesion, datos, db):
    servicio = _servicio(cliente, sesion, datos, 1500)
    r = cliente.get(f"/servicios/{servicio['id']}/contactos",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    antes = r.json()
    assert antes["solicitante"]["correo"] == "solicitante@cliente.com"
    assert antes["ejecutivo"]["idioma"] == "en" and antes["se_puede"] is True

    r = _corregir(cliente, sesion, servicio,
                  {"solicitante": SOLICITA, "ejecutivo": PRINCIPAL})
    assert r.status_code == 200, r.text
    cambios = {(c["quien"], c["campo"]) for c in r.json()["cambios"]}
    assert ("solicitante", "correo") in cambios
    assert ("ejecutivo", "correo") in cambios and ("ejecutivo", "telefono") in cambios

    db.expire_all()
    s = db.get(m.Servicio, servicio["id"])
    assert s.solicitante_correo == "patricia.lundgren@clientedemo.com"
    assert s.solicitante_telefono.startswith("+52")
    assert s.ejecutivo_telefono.startswith("+47")
    registro = db.query(m.RegistroAccion).filter_by(
        servicio_id=servicio["id"], accion="corregir contactos").one()
    assert "solicitante@cliente.com" in registro.detalle     # lo de antes
    assert "patricia.lundgren@clientedemo.com" in registro.detalle


def test_lo_que_no_ha_salido_se_va_a_los_datos_nuevos(cliente, sesion, datos, db):
    servicio = _servicio(cliente, sesion, datos, 1503)
    pendiente = _aviso(db, servicio["id"], m.Destinatario.SOLICITANTE,
                       "solicitante@cliente.com")
    salio = _aviso(db, servicio["id"], m.Destinatario.SOLICITANTE,
                   "solicitante@cliente.com", estado="enviada")
    encuesta = m.Encuesta(servicio_id=servicio["id"],
                          tipo=m.TipoEncuesta.SOLICITANTE,
                          destinatario_nombre="Patricia Lundgren",
                          destinatario_correo="solicitante@cliente.com",
                          token=secrets.token_urlsafe(24),
                          expira_en=datetime.now() + timedelta(days=10))
    db.add(encuesta)
    db.commit()

    r = _corregir(cliente, sesion, servicio, {"solicitante": SOLICITA})
    assert r.status_code == 200, r.text
    assert r.json()["avisos"] == 1 and r.json()["encuestas"] == 1

    db.expire_all()
    assert db.get(m.Notificacion, pendiente).correo == SOLICITA["correo"]
    assert db.get(m.Notificacion, salio).correo == "solicitante@cliente.com"
    assert db.get(m.Encuesta, encuesta.id).destinatario_correo == SOLICITA["correo"]


def test_otro_de_la_lista_y_corregirlo_en_la_lista(cliente, sesion, datos, db):
    servicio = _servicio(cliente, sesion, datos, 1506)
    r = cliente.post("/solicitantes", headers=sesion("consultor"), json={
        "cliente_id": datos["cliente_id"], "nombre": "Mariana",
        "apellidos": "Quiroz", "correo": "mariana.q@clientedemo.com"})
    assert r.status_code == 201, r.text
    otra = r.json()

    r = _corregir(cliente, sesion, servicio, {"solicitante": {
        "solicitante_id": otra["id"], "nombre": "Mariana", "apellidos": "Quiroz",
        "correo": "mariana.quiroz@clientedemo.com", "telefono": "55 1111 2222",
        "idioma": "es", "corregir_en_lista": True}})
    assert r.status_code == 200, r.text
    assert r.json()["lista_corregida"] is True

    db.expire_all()
    s = db.get(m.Servicio, servicio["id"])
    assert s.solicitante_id == otra["id"]
    assert db.get(m.Solicitante, otra["id"]).correo == "mariana.quiroz@clientedemo.com"

    # El correo de otro contacto de la lista no se duplica.
    r = cliente.post("/solicitantes", headers=sesion("consultor"), json={
        "cliente_id": datos["cliente_id"], "nombre": "Otro",
        "correo": "otro.contacto@clientedemo.com"})
    assert r.status_code == 201
    r = _corregir(cliente, sesion, servicio, {"solicitante": {
        "solicitante_id": otra["id"], "nombre": "Mariana", "apellidos": "Quiroz",
        "correo": "otro.contacto@clientedemo.com", "idioma": "es",
        "corregir_en_lista": True}})
    assert r.status_code == 409


def test_lo_mal_escrito_no_se_guarda(cliente, sesion, datos, db):
    servicio = _servicio(cliente, sesion, datos, 1509)
    for malo in ({**SOLICITA, "correo": "patricia@"},
                 {**SOLICITA, "correo": "patricia@gamil.com"},
                 {**SOLICITA, "nombre": "  "},
                 {**SOLICITA, "idioma": "fr"}):
        r = _corregir(cliente, sesion, servicio, {"solicitante": malo})
        assert r.status_code == 400, (malo, r.text)
    db.expire_all()
    assert db.get(m.Servicio, servicio["id"]).solicitante_correo == "solicitante@cliente.com"


def test_dice_donde_sigue_el_correo_de_antes(cliente, sesion, datos):
    """El correo equivocado suele estar en mas de un servicio: se dice en
    cuales sigue, sin tocarlos. El cancelado ya no cuenta."""
    compartido = f"patricia.{secrets.token_hex(3)}@clientedemo.com"
    uno = _servicio(cliente, sesion, datos, 1521)
    otro = _servicio(cliente, sesion, datos, 1524)
    cancelado = _servicio(cliente, sesion, datos, 1527)
    for s in (uno, otro, cancelado):
        r = _corregir(cliente, sesion, s,
                      {"solicitante": {**SOLICITA, "correo": compartido}})
        assert r.status_code == 200, r.text
    r = cliente.post(f"/servicios/{cancelado['id']}/cancelar",
                     headers=sesion("consultor"),
                     json={"motivo": "El cliente cancelo el viaje"})
    assert r.status_code == 200, r.text

    r = _corregir(cliente, sesion, uno, {"solicitante": {
        **SOLICITA, "correo": "patricia.bien@clientedemo.com"}})
    assert r.status_code == 200, r.text
    assert r.json()["otros_servicios"] == [otro["folio"]]


# ---------------------------------------------------------------- quien y cuando

def test_cancelado_ya_no_se_corrige(cliente, sesion, datos):
    servicio = _servicio(cliente, sesion, datos, 1512)
    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     headers=sesion("consultor"),
                     json={"motivo": "El cliente cancelo el viaje"})
    assert r.status_code == 200, r.text
    r = _corregir(cliente, sesion, servicio, {"solicitante": SOLICITA})
    assert r.status_code == 409


def test_quien_cubre_queda_anotado_y_los_demas_no_corrigen(cliente, sesion, datos, db):
    servicio = _servicio(cliente, sesion, datos, 1515)
    for quien in ("finanzas", "central"):
        assert _corregir(cliente, sesion, servicio, {"ejecutivo": PRINCIPAL},
                         quien=quien).status_code == 403
    r = _corregir(cliente, sesion, servicio, {"ejecutivo": PRINCIPAL},
                  quien="consultor2")
    assert r.status_code == 200, r.text
    db.expire_all()
    registro = db.query(m.RegistroAccion).filter_by(
        servicio_id=servicio["id"], accion="corregir contactos").one()
    assert registro.en_cobertura is True


def test_el_principal_del_equipo_que_tiene_el_suyo(cliente, sesion, datos, db):
    h = sesion("consultor")
    dia = [jornada(manana(1518), datos["modalidades"]["full_day"]["id"])]
    r = cliente.post("/servicios", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "solicitante_nombre": "Patricia", "solicitante_apellidos": "Lundgren",
        "solicitante_correo": "solicitante@cliente.com",
        "ejecutivo_nombre": "Ingrid", "ejecutivo_correo": "ejecutivo@cliente.com",
        "equipos": [{"clave": "EQ-1", "jornadas": dia},
                    {"clave": "EQ-2", "jornadas": dia, "ejecutivo_nombre": "Lars",
                     "ejecutivo_correo": "lars@cliente.com"}]})
    assert r.status_code == 201, r.text
    servicio = r.json()
    alfa, beta = servicio["equipos"]
    contactos = cliente.get(f"/servicios/{servicio['id']}/contactos", headers=h).json()
    assert [e["alias"] for e in contactos["equipos"]] == [beta["alias"]]

    r = _corregir(cliente, sesion, servicio, {"equipos": [{
        "equipo_id": beta["id"], "nombre": "Lars", "apellidos": "Berg",
        "correo": "lars.berg@cliente.com", "telefono": "+47 900 00 000"}]})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(m.Equipo, beta["id"]).ejecutivo_correo == "lars.berg@cliente.com"
    # El que hereda el del servicio se corrige con el del servicio.
    r = _corregir(cliente, sesion, servicio, {"equipos": [{
        "equipo_id": alfa["id"], "nombre": "Otro"}]})
    assert r.status_code == 400

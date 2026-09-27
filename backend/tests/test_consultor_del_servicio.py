"""Quien lleva el servicio (seccion 87).

Salvador, 27 sep: en «Consultor asignado» salia cualquiera --el mismo,
de direccion general--, porque sin consultores con acceso la lista caia
en la plantilla completa. Solo lo lleva un consultor, en el eventual y en
el implantado: la pantalla solo los ofrece y el servidor no acepta a
nadie mas. Y el implantado que da de alta quien no es consultor queda
sin asignar, no a su nombre.
"""
from ayudas import jornada, manana


def _persona(cliente, h):
    return cliente.get("/auth/yo", headers=h).json()["persona_id"]


def _eventual(cliente, h, datos, consultor_id):
    return cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Patricia", "solicitante_apellidos": "Lundgren",
        "ejecutivo_nombre": "Ingrid", "ejecutivo_apellidos": "Halvorsen",
        "consultor_id": consultor_id,
        "equipos": [{"clave": "EQ-1", "jornadas": [
            jornada(manana(3), datos["modalidades"]["full_day"]["id"])]}],
    }, headers=h)


def _implantado(cliente, h, datos, consultor_id=None):
    cuerpo = {
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
    }
    if consultor_id is not None:
        cuerpo["consultor_id"] = consultor_id
    return cliente.post("/implantados/servicio", json=cuerpo, headers=h)


def _consultor_de(cliente, h, servicio_id):
    return cliente.get(f"/servicios/{servicio_id}", headers=h).json()["consultor_id"]


def test_la_lista_es_solo_de_consultores(cliente, sesion, datos):
    lista = cliente.get("/catalogos/consultores", headers=sesion("dirgeneral")).json()
    nombres = {c["nombre"] for c in lista}
    assert {"Ana Solis", "Beatriz Roman"} <= nombres
    direccion = cliente.get("/auth/yo", headers=sesion("dirgeneral")).json()["nombre"]
    assert direccion not in nombres


def test_el_eventual_lo_lleva_un_consultor(cliente, sesion, datos):
    h = sesion("diroperaciones")
    r = _eventual(cliente, h, datos, _persona(cliente, h))
    assert r.status_code == 400, r.text
    assert "consultor" in r.json()["detail"]["mensaje"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    assert _eventual(cliente, h, datos, juan).status_code == 400
    r = _eventual(cliente, h, datos, datos["personal"]["Beatriz Roman"]["id"])
    assert r.status_code == 201, r.text


def test_el_implantado_tambien(cliente, sesion, datos):
    do = sesion("diroperaciones")
    # Direccion de operaciones lo da de alta sin escoger: queda sin
    # asignar, no a su nombre.
    r = _implantado(cliente, do, datos)
    assert r.status_code == 201, r.text
    assert _consultor_de(cliente, do, r.json()["servicio_id"]) is None
    # A alguien que no es consultor, no.
    r = _implantado(cliente, do, datos, _persona(cliente, do))
    assert r.status_code == 400, r.text
    # El consultor que lo da de alta se lo queda.
    ana = sesion("consultor")
    r = _implantado(cliente, ana, datos)
    assert r.status_code == 201, r.text
    assert (_consultor_de(cliente, ana, r.json()["servicio_id"])
            == datos["personal"]["Ana Solis"]["id"])

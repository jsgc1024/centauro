# -*- coding: utf-8 -*-
"""Seccion 109: la tabla de viaticos del implantado, sin medio dia ni
transfer, y su historial con nombre.

Caso de Salvador (30 sep, desde la consola): en Catalogos > Tabulador de
viaticos, con «Implantado», la tabla pedia montos de medio dia y
transfer, que al implantado no le aplican --es siempre dia completo--.
Y el historial decia «Agregó «»» y «monto: 1500» como si el monto fuera
el nombre del renglon.
"""
import os

from app import models as m

WEB = os.path.join(os.path.dirname(__file__), "..", "app", "web")


def _js(nombre: str) -> str:
    return open(os.path.join(WEB, nombre), encoding="utf-8").read()


def test_la_pantalla_del_implantado_solo_ofrece_dia_completo():
    pantalla = _js("catalogos_pantalla.js")
    assert "const ESCENARIOS_DE = (tipo) =>" in pantalla
    assert 'ESCENARIOS.filter(([e]) => e.startsWith("full_day"))' in pantalla
    assert "const escenarios = ESCENARIOS_DE(tipo);" in pantalla
    assert 't("ctl_tab_implantado_pie")' in pantalla
    assert _js("idioma.js").count("    ctl_tab_implantado_pie:") == 3


def test_la_api_no_acepta_medio_dia_ni_transfer_en_el_implantado(
        cliente, sesion, datos):
    h = sesion("diroperaciones")
    mx = datos["mx"]["id"]
    for escenario in ("medio_dia", "transfer"):
        r = cliente.post("/catalogos/tabulador-viaticos", json={
            "pais_id": mx, "tipo_servicio": "implantado",
            "concepto": "casetas", "escenario": escenario, "monto": "50"},
            headers=h)
        assert r.status_code == 400, r.text
        assert "día completo" in r.json()["detail"]["mensaje"]
    # El dia completo si entra, y no se le puede mover a transfer.
    r = cliente.post("/catalogos/tabulador-viaticos", json={
        "pais_id": mx, "tipo_servicio": "implantado", "concepto": "hospedaje",
        "escenario": "full_day_local", "monto": "900"}, headers=h)
    assert r.status_code == 201, r.text
    fila = r.json()
    r = cliente.patch(f"/catalogos/tabulador-viaticos/{fila['id']}", json={
        **{k: fila[k] for k in ("pais_id", "tipo_servicio", "concepto",
                                "monto", "monto_abierto")},
        "escenario": "transfer"}, headers=h)
    assert r.status_code == 400, r.text
    # El eventual sigue igual: medio dia y transfer son suyos.
    r = cliente.post("/catalogos/tabulador-viaticos", json={
        "pais_id": mx, "tipo_servicio": "eventual", "concepto": "hospedaje",
        "escenario": "transfer", "monto": "0"}, headers=h)
    assert r.status_code == 201, r.text

    # El historial dice que renglon es, en vez de «Agregó «»».
    r = cliente.patch(f"/catalogos/tabulador-viaticos/{fila['id']}", json={
        **{k: fila[k] for k in ("pais_id", "tipo_servicio", "concepto",
                                "escenario", "monto_abierto")},
        "monto": "950"}, headers=h)
    assert r.status_code == 200, r.text
    hist = cliente.get("/bitacora-admin/catalogo/tabulador-viaticos?idioma=es",
                       headers=h).json()["filas"]
    textos = [x["que"] for x in hist]
    assert any(x.startswith("Agregó «Hospedaje · día completo local · "
                            "implantado · Mexico»") for x in textos), textos
    assert any(x.startswith("«Hospedaje · día completo local · implantado · "
                            "Mexico»: monto") for x in textos), textos
    assert not any(x == "Agregó «»" for x in textos), textos
    en = cliente.get("/bitacora-admin/catalogo/tabulador-viaticos?idioma=en",
                     headers=h).json()["filas"]
    assert any("Lodging · local full day · embedded" in x["que"] for x in en)


def test_el_arranque_ya_no_siembra_medio_dia_ni_transfer_del_implantado():
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        sobran = (db.query(m.TabuladorViatico)
                  .filter(m.TabuladorViatico.tipo_servicio
                          == m.TipoServicio.IMPLANTADO,
                          m.TabuladorViatico.escenario.in_(
                              [m.EscenarioViatico.MEDIO_DIA,
                               m.EscenarioViatico.TRANSFER])).count())
        assert sobran == 0
    finally:
        db.close()

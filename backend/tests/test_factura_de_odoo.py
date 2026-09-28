# -*- coding: utf-8 -*-
"""La factura que se hizo en Odoo, anotada a mano (seccion 96).

Pieza 4 de «Para poder operar», decision 5 de Salvador del 28 de
septiembre: mientras la factura no se conecta con Odoo, finanzas la hace
alla y aqui anota su folio y su fecha.

Lo que aqui se cuida:

  * Anotada, sale de por facturar y queda como si Odoo la hubiera
    devuelto: el aprobado pasa a facturado, y el que falta aprobar pasa
    a facturado al aprobarlo, sin volver a mandarse.
  * Lo mal escrito no se guarda: sin folio, sin fecha o con una fecha
    de mañana. Un folio es de una sola factura, y la anulada no se usa.
  * La anotada a mano se corrige aqui, con lo de antes en la bitacora;
    la que llego de Odoo, no.
  * Regresar el servicio la anula como a la de Odoo.
  * Solo finanzas la anota, y solo lo que ya tiene visto bueno.
"""
from datetime import date, timedelta

from app import models as m
from app.db import SessionLocal
from ayudas import servicio_para_cierre


def _anotar(cliente, sesion, cierre_id, folio="INV/2026/01842", fecha=None,
            quien="finanzas"):
    return cliente.put(f"/cierre/{cierre_id}/factura-de-odoo",
                       headers=sesion(quien),
                       json={"folio": folio,
                             "fecha": str(fecha or date.today())})


def _por_facturar(cliente, sesion):
    r = cliente.get("/cierre/por-facturar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    return {x["cierre_id"] for x in r.json()["por_facturar"]}


def _cierre(cierre_id):
    with SessionLocal() as db:
        c = db.get(m.Cierre, cierre_id)
        db.expunge(c)
        return c


def _bitacora(servicio_id, accion):
    with SessionLocal() as db:
        return [r.detalle for r in db.query(m.RegistroAccion)
                .filter_by(servicio_id=servicio_id, accion=accion)
                .order_by(m.RegistroAccion.id)]


# ---------------------------------------------------------------- anotar

def test_anotada_sale_de_por_facturar_y_al_aprobar_queda_facturada(
        cliente, sesion, datos):
    servicio, cierre_id = servicio_para_cierre(cliente, sesion, datos,
                                               offset=1901)
    assert cierre_id in _por_facturar(cliente, sesion)

    ayer = date.today() - timedelta(days=1)
    r = _anotar(cliente, sesion, cierre_id, "  INV/2026/01842 ", ayer)
    assert r.status_code == 200, r.text
    assert r.json()["factura"] == "INV/2026/01842"
    assert r.json()["factura_a_mano"] is True
    assert r.json()["corregida"] is False
    assert cierre_id not in _por_facturar(cliente, sesion)

    c = _cierre(cierre_id)
    assert c.facturado_en.date() == ayer
    assert c.estatus == m.EstatusCierre.ENVIADO_FINANZAS   # falta aprobar
    assert any("INV/2026/01842" in d
               for d in _bitacora(servicio["id"], "anotar factura"))

    # Al aprobarlo queda facturado, y no se vuelve a mandar.
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["factura"]["resultado"] == "ya estaba facturado"
    c = _cierre(cierre_id)
    assert c.estatus == m.EstatusCierre.FACTURADO
    assert c.factura_odoo == "INV/2026/01842"


def test_el_aprobado_pasa_a_facturado(cliente, sesion, datos):
    _, cierre_id = servicio_para_cierre(cliente, sesion, datos, offset=1904)
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert _cierre(cierre_id).estatus == m.EstatusCierre.APROBADO

    r = _anotar(cliente, sesion, cierre_id)
    assert r.status_code == 200, r.text
    assert _cierre(cierre_id).estatus == m.EstatusCierre.FACTURADO

    # Y en la bandeja de finanzas, con quien la anoto.
    b = cliente.get("/cierre/facturacion", headers=sesion("finanzas")).json()
    suyo = next(x for x in b["cerrados"] if x["cierre_id"] == cierre_id)
    assert suyo["factura"] == "INV/2026/01842" and suyo["factura_anotada_por"]


# ---------------------------------------------------------------- lo que no

def test_lo_mal_escrito_no_se_guarda(cliente, sesion, datos):
    _, cierre_id = servicio_para_cierre(cliente, sesion, datos, offset=1907)
    for folio, fecha in (("   ", None),
                         ("X" * 61, None),
                         ("INV/2026/01843", date.today() + timedelta(days=2))):
        r = _anotar(cliente, sesion, cierre_id, folio, fecha)
        assert r.status_code == 400, (folio, r.text)
    r = cliente.put(f"/cierre/{cierre_id}/factura-de-odoo",
                    headers=sesion("finanzas"), json={"folio": "INV/1"})
    assert r.status_code == 422
    assert cierre_id in _por_facturar(cliente, sesion)


def test_un_folio_es_de_una_sola_factura(cliente, sesion, datos):
    _, uno = servicio_para_cierre(cliente, sesion, datos, offset=1910)
    _, otro = servicio_para_cierre(cliente, sesion, datos, offset=1913)
    assert _anotar(cliente, sesion, uno, "INV/2026/00100").status_code == 200
    r = _anotar(cliente, sesion, otro, "inv/2026/00100")
    assert r.status_code == 409, r.text
    assert otro in _por_facturar(cliente, sesion)


# ---------------------------------------------------------------- corregir

def test_la_anotada_a_mano_se_corrige_con_lo_de_antes(cliente, sesion, datos):
    servicio, cierre_id = servicio_para_cierre(cliente, sesion, datos,
                                               offset=1916)
    assert _anotar(cliente, sesion, cierre_id, "INV/2026/01824").status_code == 200
    r = _anotar(cliente, sesion, cierre_id, "INV/2026/01842")
    assert r.status_code == 200, r.text
    assert r.json()["corregida"] is True
    assert _cierre(cierre_id).factura_odoo == "INV/2026/01842"
    detalle = _bitacora(servicio["id"], "corregir factura")[-1]
    assert "INV/2026/01824" in detalle and "INV/2026/01842" in detalle


def test_la_que_llego_de_odoo_no_se_corrige_aqui(cliente, sesion, datos):
    _, cierre_id = servicio_para_cierre(cliente, sesion, datos, offset=1919)
    with SessionLocal() as db:
        c = db.get(m.Cierre, cierre_id)
        c.factura_odoo = "FAC-0007"
        c.facturado_en = c.enviado_en
        db.commit()
    r = _anotar(cliente, sesion, cierre_id, "INV/2026/01842")
    assert r.status_code == 409, r.text
    assert _cierre(cierre_id).factura_odoo == "FAC-0007"


# ---------------------------------------------------------------- regresar

def test_regresarlo_la_anula_y_su_folio_ya_no_se_usa(cliente, sesion, datos):
    _, cierre_id = servicio_para_cierre(cliente, sesion, datos, offset=1922)
    assert _anotar(cliente, sesion, cierre_id, "INV/2026/00500").status_code == 200
    r = cliente.post(f"/cierre/{cierre_id}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "Falta el dia 2 en el comparativo"})
    assert r.status_code == 200, r.text
    c = _cierre(cierre_id)
    assert c.factura_anulada == "INV/2026/00500"
    assert c.factura_odoo is None and c.facturado_en is None
    assert c.factura_anotada_por_id is None

    # Lo regresado no se factura hasta que vuelva con su visto bueno.
    assert _anotar(cliente, sesion, cierre_id, "INV/2026/00501").status_code == 409


# ---------------------------------------------------------------- quien

def test_solo_finanzas_la_anota(cliente, sesion, datos):
    _, cierre_id = servicio_para_cierre(cliente, sesion, datos, offset=1925)
    for quien in ("consultor", "central"):
        assert _anotar(cliente, sesion, cierre_id,
                       quien=quien).status_code == 403
    assert cierre_id in _por_facturar(cliente, sesion)

# -*- coding: utf-8 -*-
"""La factura que sale hacia Odoo.

Odoo era una entrada y nada mas: nos mandaba personal, flota,
capacitaciones y taller, y no salia nada. El estatus `facturado` existia
en el catalogo desde el primer dia sin que lo escribiera nadie, asi que
un servicio aprobado por finanzas se quedaba sin quien dijera "ya se
cobro".

Una factura por servicio, al aprobarlo (decision de Salvador, 20 sep).
Lo que se prueba aqui es lo que no se puede perder: que el envio nunca
tumbe la aprobacion, y que lo que falla se vea en una bandeja en vez de
desaparecer.
"""
import pytest


class Bandeja(list):
    """Lo que le llego a Odoo, con un interruptor para tirarlo.

    Se apaga con `odoo.caido = True` en vez de volver a parchar httpx:
    `monkeypatch.undo()` deshace TODO lo parchado --incluida la
    configuracion de Odoo-- y dejaba la prueba reintentando contra un
    sistema sin conexion, que es otra cosa.
    """
    caido = False


@pytest.fixture
def odoo(monkeypatch):
    """Un Odoo de mentiras: guarda lo que le llega y contesta su folio."""
    from app import facturacion

    recibidas = Bandeja()

    class Respuesta:
        status_code = 200
        content = b"{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {"factura": f"FAC-{len(recibidas):04d}"}

    def falso(url, json=None, headers=None, timeout=None):
        if recibidas.caido:
            raise RuntimeError("Odoo dormido")
        recibidas.append({"url": url, "cuerpo": json, "cabeceras": headers})
        return Respuesta()

    monkeypatch.setattr(facturacion.settings, "odoo_url",
                        "https://odoo.example/facturas")
    monkeypatch.setattr(facturacion.settings, "odoo_token", "un-token")
    monkeypatch.setattr(facturacion.httpx, "post", falso)
    return recibidas


def _cierre_aprobado(cliente, sesion, datos):
    """Un servicio trabajado, cerrado y enviado a finanzas."""
    from ayudas import servicio_para_cierre

    return servicio_para_cierre(cliente, sesion, datos)


def test_al_aprobar_se_manda_la_factura_con_lo_ejecutado(cliente, sesion,
                                                         datos, odoo):
    """Lo que se factura es lo EJECUTADO, no lo cotizado: la cotizacion
    es lo que se ofrecio y el ejecutado lo que de verdad se presto."""
    servicio, cierre_id = _cierre_aprobado(cliente, sesion, datos)

    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["factura"]["resultado"] == "facturado"

    assert len(odoo) == 1, odoo
    cuerpo = odoo[0]["cuerpo"]
    assert cuerpo["referencia"] == servicio["folio"]
    assert cuerpo["conceptos"], cuerpo
    assert odoo[0]["cabeceras"]["Authorization"] == "Bearer un-token"

    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = db.get(m.Cierre, cierre_id)
        assert c.estatus == m.EstatusCierre.FACTURADO
        assert c.factura_odoo
        assert c.facturado_en


def test_si_odoo_no_contesta_el_cierre_sigue_aprobado(cliente, sesion, datos,
                                                      monkeypatch):
    """El cierre ya quedo aprobado y la comision ya se genero cuando esto
    corre. Un Odoo caido no puede deshacer eso."""
    from app import facturacion

    monkeypatch.setattr(facturacion.settings, "odoo_url",
                        "https://odoo.example/facturas")

    def revienta(*a, **k):
        raise RuntimeError("Connection refused")

    monkeypatch.setattr(facturacion.httpx, "post", revienta)

    servicio, cierre_id = _cierre_aprobado(cliente, sesion, datos)
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["factura"]["resultado"] == "fallo"

    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = db.get(m.Cierre, cierre_id)
        assert c.estatus == m.EstatusCierre.APROBADO
        assert "Connection refused" in c.factura_error

    # Y se ve en la bandeja, que es lo que faltaba: sin ella nadie se
    # entera hasta que el cliente no paga.
    r = cliente.get("/cierre/por-facturar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    suyo = next(x for x in r.json()["por_facturar"]
                if x["cierre_id"] == cierre_id)
    assert "Connection refused" in suyo["error"]


def test_se_puede_reintentar_desde_la_bandeja(cliente, sesion, datos, odoo):
    """El dia que Odoo estaba caido, y el primer envio cuando la conexion
    se configura despues."""
    odoo.caido = True
    servicio, cierre_id = _cierre_aprobado(cliente, sesion, datos)
    cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))

    odoo.caido = False          # Odoo revive
    r = cliente.post(f"/cierre/{cierre_id}/facturar",
                     headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["resultado"] == "facturado"

    r = cliente.get("/cierre/por-facturar", headers=sesion("finanzas"))
    assert not any(x["cierre_id"] == cierre_id
                   for x in r.json()["por_facturar"])


def test_sin_odoo_configurado_no_se_pierde_nada(cliente, sesion, datos,
                                                monkeypatch):
    """Mientras no haya conexion, el aprobado se queda por facturar. Un
    sistema que se cree conectado y no lo esta es peor que uno apagado."""
    from app import facturacion

    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    servicio, cierre_id = _cierre_aprobado(cliente, sesion, datos)
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["factura"]["resultado"] == "sin conexion"

    r = cliente.get("/cierre/por-facturar", headers=sesion("finanzas"))
    assert r.json()["odoo_configurado"] is False
    assert any(x["cierre_id"] == cierre_id for x in r.json()["por_facturar"])


def test_la_pantalla_recibe_el_reloj_para_pintarlo_corriendo(cliente, sesion,
                                                             datos):
    """El limite y el momento, los dos en hora del país del servicio.

    La cuenta regresiva sale de la resta entre ellos y no del reloj de
    la máquina donde está abierta la consola: de ese plazo depende que
    el consultor cobre su comisión, y no puede depender de la hora de
    una laptop.
    """
    from ayudas import servicio_para_cierre

    servicio, cierre_id = servicio_para_cierre(cliente, sesion, datos,
                                               offset=910)
    r = cliente.get(f"/cierre/servicio/{servicio['id']}/revision",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    c = r.json()["cierre"]
    assert c["existe"] is True
    assert c["cierre_id"] == cierre_id
    assert c["limite"] and r.json()["revisado_en"]
    # Veinticuatro horas desde que se abrio, ni una mas.
    from datetime import datetime
    abierto = datetime.fromisoformat(c["abierto_en"])
    limite = datetime.fromisoformat(c["limite"])
    assert round((limite - abierto).total_seconds() / 3600) == 24

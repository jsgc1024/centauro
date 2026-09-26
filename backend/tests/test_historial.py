# -*- coding: utf-8 -*-
"""El historial de lo facturado y la foto que se trae del archivo
(seccion 69).

Lo cerrado nunca se borraba y no habia donde verlo: la pestana de
cerrados ensena solo el mes en curso. El historial trae todo, con
filtros y en Excel, y dice de cada servicio como van sus fotos. La foto
que ya se fue al archivo la traen de vuelta direccion general y finanzas,
y cada vez queda en la bitacora del servicio.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest

import ayudas_archivo as aa

FACTURA = datetime(2026, 12, 10, 12, 0)
EL_DIA = date(2027, 3, 10)


@pytest.fixture
def google(monkeypatch):
    g, apagar = aa.levantar_google(monkeypatch)
    yield g
    apagar()


@pytest.fixture(autouse=True)
def con_odoo(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "odoo_url", "https://odoo.example/facturas")


def _historial(cliente, sesion, quien="finanzas", **filtros):
    r = cliente.get("/cierre/historial", params=filtros,
                    headers=sesion(quien))
    assert r.status_code == 200, r.text
    return r.json()


# ================================================================ la lista

def test_trae_lo_cerrado_con_sus_fotos_y_lo_que_suma(cliente, sesion, datos):
    diciembre = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA,
                            offset=600)
    octubre = aa.eventual(cliente, sesion, datos,
                          facturado_en=datetime(2026, 10, 14, 9, 0),
                          offset=610, total="57900.00", factura="F-01011",
                          consultor="Beatriz Roman")
    # Lo que sigue en finanzas no es historial todavia.
    aa.eventual(cliente, sesion, datos, estatus="enviado_finanzas",
                facturado_en=FACTURA, aprobado_en=None, offset=620)

    h = _historial(cliente, sesion)
    assert h["total"] == 2
    primero, segundo = h["filas"]
    # Lo mas reciente arriba.
    assert primero["folio"] == diciembre["folio"]
    assert segundo["folio"] == octubre["folio"]
    assert primero["factura"] == "F-01245"
    assert primero["tipo"] == "eventual"
    assert primero["consultor"] == "Ana Solis"
    assert primero["moneda"] == "MXN"
    assert Decimal(primero["total"]) == Decimal("48600.00")
    # Lo comprobado de Juan y de Luis.
    assert Decimal(primero["viaticos"]) == Decimal("4215.00")
    # Seis fotos en Centauro y la fecha en que se van.
    assert primero["fotos"] == {"en_centauro": 6, "archivadas": 0,
                                "archivadas_en": None}
    assert primero["reloj"] == {"desde": "factura", "inicio": "2026-12-10",
                                "archivo": "2027-03-10"}
    assert primero["desde"] == primero["hasta"]           # un solo dia

    r = h["resumen"]
    assert r["servicios"] == 2
    assert Decimal(r["facturado"]["MXN"]) == Decimal("106500.00")
    assert r["fotos_en_centauro"] == 12 and r["fotos_archivadas"] == 0
    assert {c["nombre"] for c in h["opciones"]["consultores"]} == {
        "Ana Solis", "Beatriz Roman"}
    assert h["opciones"]["primer_mes"] == "2026-10"
    assert h["opciones"]["ultimo_mes"] == "2026-12"
    # Apagado: el historial funciona igual y dice cuando se irian.
    assert h["archivo"]["activo"] is False
    assert h["archivo"]["anios"] == 6


def test_los_filtros(cliente, sesion, datos):
    dic = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA, offset=600)
    oct_ = aa.eventual(cliente, sesion, datos,
                       facturado_en=datetime(2026, 10, 14, 9, 0), offset=610,
                       consultor="Beatriz Roman")

    def folios(**f):
        return [x["folio"] for x in _historial(cliente, sesion, **f)["filas"]]

    assert folios(desde="2026-11") == [dic["folio"]]
    assert folios(hasta="2026-11") == [oct_["folio"]]
    assert folios(desde="2026-10", hasta="2026-12") == [dic["folio"],
                                                        oct_["folio"]]
    beatriz = datos["personal"]["Beatriz Roman"]["id"]
    assert folios(consultor_id=beatriz) == [oct_["folio"]]
    assert folios(folio=dic["folio"][-3:]) == [dic["folio"]]
    assert folios(tipo="implantado") == []
    assert folios(cliente_id=datos["cliente_id"]) == [dic["folio"],
                                                      oct_["folio"]]
    # La pagina corta la lista, no lo que suma.
    h = _historial(cliente, sesion, por_pagina=1, pagina=2)
    assert [x["folio"] for x in h["filas"]] == [oct_["folio"]]
    assert h["total"] == 2 and h["resumen"]["servicios"] == 2

    r = cliente.get("/cierre/historial", params={"desde": "octubre"},
                    headers=sesion("finanzas"))
    assert r.status_code == 400


def test_sin_odoo_dice_que_cuenta_desde_la_aprobacion(cliente, sesion, datos,
                                                     monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "odoo_url", "")
    aa.eventual(cliente, sesion, datos, estatus="aprobado", facturado_en=None,
                aprobado_en=datetime(2026, 12, 2, 17, 30))
    fila = _historial(cliente, sesion)["filas"][0]
    assert fila["factura"] is None
    assert fila["reloj"] == {"desde": "aprobacion", "inicio": "2026-12-02",
                             "archivo": "2027-03-02"}


def test_quien_lo_ve(cliente, sesion, datos):
    aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    for quien in ("finanzas", "diroperaciones", "dirgeneral", "admin"):
        assert cliente.get("/cierre/historial",
                           headers=sesion(quien)).status_code == 200, quien
    for quien in ("consultor", "central", "juan"):
        assert cliente.get("/cierre/historial",
                           headers=sesion(quien)).status_code == 403, quien


# ================================================================ el detalle

def test_el_detalle_dice_como_va_cada_foto(cliente, sesion, datos, google):
    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    r = cliente.get(f"/cierre/historial/{s['cierre_id']}",
                    headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert [p["nombre"] for p in d["personas"]] == ["Juan Ramirez",
                                                    "Luis Mendoza"]
    juan, luis = d["personas"]
    assert [c["concepto"] for c in juan["comprobantes"]] == [
        "combustible", "casetas", "alimentos"]
    assert all(c["tiene_imagen"] and not c["archivada_en"]
               for c in juan["comprobantes"])
    assert luis["devoluciones"][0]["estatus"] == "confirmada"
    assert Decimal(d["comprobado"]) == Decimal("4215.00")
    assert Decimal(d["devuelto"]) == Decimal("285.00")
    assert Decimal(d["entregado"]) == Decimal("4500.00")
    assert d["plaza"] == "Ciudad de Mexico"
    assert d["puede_ver_archivo"] is True

    aa.archivar(EL_DIA)
    d = cliente.get(f"/cierre/historial/{s['cierre_id']}",
                    headers=sesion("finanzas")).json()
    juan, luis = d["personas"]
    assert all(not c["tiene_imagen"] and c["archivada_en"]
               for c in juan["comprobantes"])
    assert luis["devoluciones"][0]["archivada_en"]
    assert d["fotos"]["archivadas"] == 6 and d["fotos"]["en_centauro"] == 0

    # Direccion de operaciones ve el historial, no el archivo.
    d = cliente.get(f"/cierre/historial/{s['cierre_id']}",
                    headers=sesion("diroperaciones")).json()
    assert d["puede_ver_archivo"] is False


def test_lo_que_no_ha_cerrado_no_tiene_detalle(cliente, sesion, datos):
    s = aa.eventual(cliente, sesion, datos, estatus="enviado_finanzas",
                    facturado_en=None, aprobado_en=None)
    r = cliente.get(f"/cierre/historial/{s['cierre_id']}",
                    headers=sesion("finanzas"))
    assert r.status_code == 409
    assert "Por aprobar" in r.text


# ================================================================ el archivo

def _el_primer_ticket(s):
    return next(i for (t, i) in s["fotos"] if t == "comprobante")


def test_ver_del_archivo_trae_la_foto_y_queda_en_la_bitacora(
        cliente, sesion, datos, google):
    import base64
    from app import models as m
    from app.db import SessionLocal

    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    aa.archivar(EL_DIA)
    ticket = _el_primer_ticket(s)

    r = cliente.get(f"/archivo/comprobantes/{ticket}",
                    headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["coincide"] is True
    assert base64.b64decode(d["imagen"].split(",", 1)[1]) == \
        s["fotos"][("comprobante", ticket)]
    assert d["imagen"].startswith("data:image/jpeg;base64,")
    assert d["folio"] == s["folio"] and d["persona"] == "Juan Ramirez"
    assert d["concepto"] == "combustible"
    assert d["archivada_en"]

    with SessionLocal() as db:
        anotado = (db.query(m.RegistroAccion)
                   .filter_by(servicio_id=s["servicio_id"],
                              accion="foto traida del archivo").all())
        assert len(anotado) == 1
        assert "Juan Ramirez" in anotado[0].detalle
        assert "1,018.40" in anotado[0].detalle
        assert anotado[0].jornada_id == s["jornada_id"]

    # Direccion general tambien; direccion de operaciones y el
    # consultor, no.
    assert cliente.get(f"/archivo/comprobantes/{ticket}",
                       headers=sesion("dirgeneral")).status_code == 200
    for quien in ("diroperaciones", "consultor", "juan"):
        assert cliente.get(f"/archivo/comprobantes/{ticket}",
                           headers=sesion(quien)).status_code == 403, quien

    devolucion = next(i for (t, i) in s["fotos"] if t == "devolucion")
    r = cliente.get(f"/archivo/devoluciones/{devolucion}",
                    headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["concepto"] == "devolucion"


def test_si_la_huella_no_coincide_se_dice(cliente, sesion, datos, google):
    from app import models as m
    from app.db import SessionLocal

    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    aa.archivar(EL_DIA)
    ticket = _el_primer_ticket(s)
    nombre = aa.estado("comprobante", ticket)["objeto"].removeprefix(
        f"gs://{aa.DEPOSITO}/")
    google.objetos[nombre]["datos"] = b"\xff\xd8otra foto"

    d = cliente.get(f"/archivo/comprobantes/{ticket}",
                    headers=sesion("finanzas")).json()
    assert d["coincide"] is False
    with SessionLocal() as db:
        anotado = (db.query(m.RegistroAccion)
                   .filter_by(accion="foto traida del archivo").one())
        assert "NO COINCIDE" in anotado.detalle


def test_la_que_sigue_en_centauro_no_se_pide_al_archivo(cliente, sesion, datos,
                                                        google):
    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    r = cliente.get(f"/archivo/comprobantes/{_el_primer_ticket(s)}",
                    headers=sesion("finanzas"))
    assert r.status_code == 404
    assert "Sigue en Centauro" in r.text


def test_si_google_no_la_entrega_se_dice_y_no_se_anota(cliente, sesion, datos,
                                                      google):
    from app import models as m
    from app.db import SessionLocal

    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    aa.archivar(EL_DIA)
    google.objetos.clear()
    r = cliente.get(f"/archivo/comprobantes/{_el_primer_ticket(s)}",
                    headers=sesion("finanzas"))
    assert r.status_code == 502
    with SessionLocal() as db:
        assert not db.query(m.RegistroAccion).filter_by(
            accion="foto traida del archivo").count()


def test_la_foto_archivada_dice_donde_esta(cliente, sesion, datos, google):
    """El camino de siempre ya no la tiene: contesta que se archivo y
    como se trae, en vez de un "no trae foto" que seria mentira."""
    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA)
    ticket = _el_primer_ticket(s)
    juan = s["viaticos"]["juan"]
    devolucion = next(i for (t, i) in s["fotos"] if t == "devolucion")
    ruta = f"/viaticos/{juan}/comprobantes/{ticket}/imagen"
    assert cliente.get(ruta, headers=sesion("finanzas")).status_code == 200
    # La foto de la devolucion ahora tiene por donde verse.
    r = cliente.get(f"/viaticos/devoluciones/{devolucion}/comprobante",
                    headers=sesion("finanzas"))
    assert r.status_code == 200
    assert r.content == s["fotos"][("devolucion", devolucion)]
    # Solo la suya: a Juan la de Luis no.
    assert cliente.get(f"/viaticos/devoluciones/{devolucion}/comprobante",
                       headers=sesion("juan")).status_code == 403
    assert cliente.get(f"/viaticos/devoluciones/{devolucion}/comprobante",
                       headers=sesion("luis")).status_code == 200

    aa.archivar(EL_DIA)
    r = cliente.get(ruta, headers=sesion("finanzas"))
    assert r.status_code == 410
    # El dia en que de verdad se mudo, no el del reloj.
    assert f"se archivo el {date.today():%d/%m/%Y}" in r.text
    assert "Ver del archivo" in r.text
    assert cliente.get(f"/viaticos/devoluciones/{devolucion}/comprobante",
                       headers=sesion("finanzas")).status_code == 410

    # Y la tarjeta del cierre lo sabe.
    r = cliente.get(f"/cierre/servicio/{s['servicio_id']}/viaticos",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    tickets = [c for p in r.json()["personas"] for c in p["comprobantes"]]
    assert tickets and all(c["archivada_en"] and not c["tiene_imagen"]
                           for c in tickets)


# ================================================================ el Excel

def test_el_excel_trae_lo_mismo_que_la_pantalla(cliente, sesion, datos, google):
    from app import excel

    s = aa.eventual(cliente, sesion, datos, facturado_en=FACTURA, offset=600)
    aa.eventual(cliente, sesion, datos,
                facturado_en=datetime(2026, 10, 14, 9, 0), offset=610,
                total="57900.00", factura="F-01011")
    aa.archivar(date(2027, 1, 14))          # solo el de octubre se va

    r = cliente.get("/cierre/historial.xlsx", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml")
    assert "Historial_de_facturacion_" in r.headers["content-disposition"]
    hojas = excel.leer(r.content)
    assert list(hojas) == ["Servicios", "Comprobantes"]

    servicios = hojas["Servicios"]
    assert servicios[0]["A"] == "Folio" and servicios[0]["M"] == "Viáticos comprobados"
    assert len(servicios) == 3 and servicios[1]["A"] == s["folio"]
    assert sum(Decimal(f["K"]) for f in servicios[1:]) == Decimal("106500.00")
    # Las fechas van como fechas de Excel, no como texto.
    assert float(servicios[1]["I"]) == 46366.0        # 10/12/2026
    assert servicios[1]["N"] == "6" and servicios[1]["O"] == "0"
    assert servicios[2]["N"] == "0" and servicios[2]["O"] == "6"

    tickets = hojas["Comprobantes"]
    assert len(tickets) == 1 + 12
    fotos = {f["L"] for f in tickets[1:]}
    assert fotos == {"En Centauro", "En el archivo"}
    assert any(f["E"] == "Devolución" and f["I"] == "Confirmada"
               for f in tickets[1:])

    # En el idioma de quien lo baja.
    r = cliente.get("/cierre/historial.xlsx", params={"idioma": "pt"},
                    headers=sesion("finanzas"))
    assert list(excel.leer(r.content)) == ["Serviços", "Comprovantes"]
    # Con los mismos filtros que la pantalla.
    r = cliente.get("/cierre/historial.xlsx", params={"desde": "2026-11"},
                    headers=sesion("finanzas"))
    assert len(excel.leer(r.content)["Servicios"]) == 2
    assert cliente.get("/cierre/historial.xlsx",
                       headers=sesion("consultor")).status_code == 403

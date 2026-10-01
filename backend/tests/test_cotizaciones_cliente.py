# -*- coding: utf-8 -*-
"""Cotizaciones (seccion 114): la cotizacion del eventual que se arma en
Connect, su PDF y el servicio que nace cuando el cliente la autoriza.

Lo que aqui se cuida:

  * El folio de la serie EP/COT y sus versiones.
  * Los precios salen de la lista: del cliente o, de la empresa que
    todavia no esta en Odoo, la general de su pais.
  * Mandarla guarda su PDF y lo enviado ya no cambia; la version
    siguiente sustituye a la anterior al mandarse.
  * Al autorizarla nace el servicio, con el mismo alta que Nuevo servicio
    y la misma cotizacion adentro; la empresa nueva ya tiene que estar en
    Odoo.
  * Rechazada con su motivo; vencida por el reloj.
  * El servicio que se borra suelta su cotizacion; la recotizacion en el
    servicio sigue con el folio.
  * La firma de cada quien, los textos de Catalogos y quien puede que.
"""
import base64
import importlib.util
import pathlib
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app import cotizacion_cliente as motor
from app import cotizacion_pdf
from app import models as m
from ayudas import PIXEL, manana

D = Decimal
RAIZ = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture
def cliente_de_odoo(db, datos):
    """El cliente de la semilla, como si llegara de Odoo."""
    cliente = db.get(m.Cliente, datos["cliente_id"])
    antes = cliente.odoo_id
    cliente.odoo_id = 990114
    db.commit()
    yield cliente
    cliente = db.get(m.Cliente, datos["cliente_id"])
    cliente.odoo_id = antes
    db.commit()


@pytest.fixture
def lista_general(db, datos):
    """La lista de la semilla, marcada como la unica general de Mexico:
    otra prueba pudo dejar una general leida de Odoo."""
    cliente = db.get(m.Cliente, datos["cliente_id"])
    antes = {t.id: t.general for t in db.query(m.Tarifario).filter_by(
        pais_id=datos["mx"]["id"]).all()}
    for t in db.query(m.Tarifario).filter_by(pais_id=datos["mx"]["id"]).all():
        t.general = t.id == cliente.tarifario_id
    db.commit()
    yield db.get(m.Tarifario, cliente.tarifario_id)
    for t in db.query(m.Tarifario).filter(m.Tarifario.id.in_(antes)).all():
        t.general = antes[t.id]
    db.commit()


def _dia(datos, offset, modalidad="full_day", **extra):
    return {"fecha": str(manana(offset)),
            "modalidad_id": datos["modalidades"][modalidad]["id"], **extra}


def _lleva(datos, rol="conductor_seguridad", unidad="suv_blindada"):
    salida = [{"tipo": "recurso", "id": datos["perfiles"][rol]["id"],
               "cantidad": 1}]
    if unidad:
        salida.append({"tipo": "vehiculo",
                       "id": datos["categorias"][unidad]["id"], "cantidad": 1})
    return salida


def _cuerpo(datos, offset=2000, **extra):
    """Dos equipos: Alfa dos dias de dia completo, Beta un transfer."""
    return {
        "cliente_id": datos["cliente_id"],
        "solicitante_nombre": "Valeria", "solicitante_apellidos": "Rodas",
        "solicitante_correo": "valeria.rodas@ejemplo.com",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "tipo_servicio": "Transportación ejecutiva",
        "valida_hasta": str(date.today() + timedelta(days=60)),
        "idioma": "es", "con_iva": True, "gastos": "dentro",
        "equipos": [
            {"plaza_id": datos["cdmx"]["id"], "lleva": _lleva(datos),
             "dias": [_dia(datos, offset), _dia(datos, offset + 1)]},
            {"plaza_id": datos["cdmx"]["id"], "lleva": _lleva(datos),
             "dias": [_dia(datos, offset, "transfer", hora="18:00")]},
        ],
        **extra,
    }


def _crear(cliente, sesion, datos, quien="consultor", **extra):
    r = cliente.post("/cotizaciones/eventual", json=_cuerpo(datos, **extra),
                     headers=sesion(quien))
    assert r.status_code == 201, r.text
    return r.json()


def _enviar(cliente, sesion, cot, quien="consultor"):
    r = cliente.post(f"/cotizaciones/eventual/{cot['id']}/enviar",
                     headers=sesion(quien))
    assert r.status_code == 200, r.text
    return r.json()


def _autorizar(cliente, sesion, cot, quien="consultor", **campos):
    datos = {"autorizada_por": "Valeria Rodas",
             "autorizada_el": str(date.today()), **campos}
    return cliente.post(f"/cotizaciones/eventual/{cot['id']}/autorizar",
                        data=datos, headers=sesion(quien))


# ---------------------------------------------------------------- armarla

def test_el_borrador_trae_su_folio_y_los_precios_de_la_lista(cliente, sesion, datos):
    c = _crear(cliente, sesion, datos)
    assert c["folio"] == "EP/COT-0001" and c["version"] == 1
    assert c["estatus"] == "borrador" and c["se_edita"] is True
    assert c["aviso_precios"] is None
    # 2 dias completos y un transfer, cada uno con conductor y Suburban
    # blindada: 3200 + 8500 dos veces y 1200 + 3400 una.
    assert D(str(c["subtotal"])) == D("28000")
    assert c["tasa_iva"] == pytest.approx(0.16)
    assert D(str(c["iva"])) == D("4480.00")
    assert D(str(c["total"])) == D("32480.00")
    assert c["dias_n"] == 3 and c["equipos_n"] == 2
    assert [e["clave"] for e in c["equipos"]] == ["Alfa", "Beta"]
    assert c["equipos"][1]["dias"][0]["hora"] == "18:00"

    otra = _crear(cliente, sesion, datos)
    assert otra["folio"] == "EP/COT-0002"


def test_los_precios_se_ven_sin_guardar_nada(cliente, sesion, datos, db):
    r = cliente.post("/cotizaciones/eventual/precios",
                     json=_cuerpo(datos), headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    previa = r.json()
    assert D(str(previa["subtotal"])) == D("28000")
    assert previa["dias"] == 3 and previa["equipos"] == 2
    assert {x["rol"] for x in previa["hora_extra"]} == {"Conductor de seguridad"}
    assert db.query(m.Cotizacion).filter(m.Cotizacion.folio.isnot(None)).count() == 0


def test_la_vista_previa_dice_la_introduccion_la_firma_y_lo_que_falta(cliente, sesion, datos, lista_general):
    """Lo que la pantalla ensena mientras se arma: la introduccion que
    Connect escribiria --en texto, sin negritas--, si quien firma ya subio
    su firma y lo que al PDF le falta de Catalogos en su idioma."""
    previa = cliente.post("/cotizaciones/eventual/precios", json=_cuerpo(datos),
                          headers=sesion("consultor")).json()
    intro = previa["introduccion_auto"]
    assert intro.startswith("A solicitud de Valeria Rodas, de ")
    assert "transportación ejecutiva" in intro and "<b>" not in intro
    assert previa["firma"] is False
    # Mexico nace sin RFC ni condiciones de pago: los escribe direccion de
    # operaciones en Catalogos.
    assert {"rfc", "pago"} <= set(previa["faltan_textos"])
    assert "razon_social" not in previa["faltan_textos"]

    # La empresa nueva sin nombre todavia: los precios salen igual, de la
    # general de su pais, y la introduccion espera al nombre.
    cuerpo = _cuerpo(datos)
    cuerpo.pop("cliente_id")
    cuerpo.update(pais_id=datos["mx"]["id"], prospecto="  ")
    r = cliente.post("/cotizaciones/eventual/precios", json=cuerpo,
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert D(str(r.json()["subtotal"])) == D("28000")
    assert r.json()["introduccion_auto"] is None


def test_la_introduccion_escrita_manda_sobre_la_de_connect(cliente, sesion, datos, db):
    c = _crear(cliente, sesion, datos, introduccion="Como lo platicamos por teléfono.")
    html = cotizacion_pdf.html_de(db, db.get(m.Cotizacion, c["id"]))
    assert "Como lo platicamos por teléfono." in html
    assert "A solicitud de" not in html


def test_lo_que_la_lista_no_cobra_se_dice_y_el_borrador_se_guarda(cliente, sesion, datos, db):
    cliente_db = db.get(m.Cliente, datos["cliente_id"])
    perfil = datos["perfiles"]["conductor_seguridad"]["id"]
    tarifa = (db.query(m.TarifaRecurso)
              .filter_by(tarifario_id=cliente_db.tarifario_id, perfil_id=perfil,
                         modalidad_id=datos["modalidades"]["transfer"]["id"]).one())
    precio = tarifa.precio
    db.delete(tarifa)
    db.commit()
    try:
        c = _crear(cliente, sesion, datos)
        assert c["aviso_precios"]["clave"] == "sin_precio"
        assert c["lineas"] == []
        r = cliente.post(f"/cotizaciones/eventual/{c['id']}/enviar",
                         headers=sesion("consultor"))
        assert r.status_code == 400
    finally:
        db.add(m.TarifaRecurso(tarifario_id=cliente_db.tarifario_id,
                               perfil_id=perfil, precio=precio,
                               modalidad_id=datos["modalidades"]["transfer"]["id"]))
        db.commit()


def test_la_empresa_que_no_esta_en_odoo_cotiza_con_la_general(cliente, sesion, datos, lista_general):
    cuerpo = _cuerpo(datos)
    cuerpo.pop("cliente_id")
    cuerpo.update(prospecto="  Henkel   Capital ", pais_id=datos["mx"]["id"])
    r = cliente.post("/cotizaciones/eventual", json=cuerpo,
                     headers=sesion("consultor"))
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["cliente_id"] is None and c["prospecto"] == "Henkel Capital"
    assert c["es_prospecto"] is True and c["cliente"] == "Henkel Capital"
    assert c["tarifario"]["id"] == lista_general.id


def test_sin_cliente_ni_empresa_no_se_arma(cliente, sesion, datos):
    cuerpo = _cuerpo(datos)
    cuerpo.pop("cliente_id")
    cuerpo["pais_id"] = datos["mx"]["id"]
    r = cliente.post("/cotizaciones/eventual", json=cuerpo,
                     headers=sesion("consultor"))
    assert r.status_code == 400


def test_el_dia_que_va_distinto_y_el_monto_fijo(cliente, sesion, datos):
    cuerpo = _cuerpo(datos, gastos="fijo", monto_gastos="1900")
    cuerpo["equipos"][0]["dias"][1]["lleva"] = _lleva(datos, unidad="cuv")
    c = _crear(cliente, sesion, datos, **{k: v for k, v in cuerpo.items()
                                         if k in ("gastos", "monto_gastos")})
    # Se arma otra vez con el dia distinto, ahora guardando.
    r = cliente.put(f"/cotizaciones/eventual/{c['id']}", json=cuerpo,
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["gastos"] == "fijo" and c["monto_gastos"] == 1900
    # 3200 + 8500, 3200 + 2500, 1200 + 3400 y el fijo de 1900.
    assert D(str(c["subtotal"])) == D("23900")
    unidades = {l["categoria_id"] for l in c["lineas"] if l["tipo"] == "vehiculo"}
    assert datos["categorias"]["cuv"]["id"] in unidades


# ---------------------------------------------------------------- mandarla

def test_mandarla_guarda_su_pdf_y_ya_no_cambia(cliente, sesion, datos):
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    assert c["estatus"] == "enviada" and c["enviada_por"] == "Ana Solis"
    assert c["pdf"]["nombre"].endswith(".pdf")
    assert "_EP-COT-0001_V1_" in c["pdf"]["nombre"]

    r = cliente.get(f"/cotizaciones/eventual/{c['id']}/pdf?bajar=true",
                    headers=sesion("consultor"))
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    assert "attachment" in r.headers["content-disposition"]

    r = cliente.put(f"/cotizaciones/eventual/{c['id']}", json=_cuerpo(datos),
                    headers=sesion("consultor"))
    assert r.status_code == 409


def test_lo_que_le_falta_para_mandarla(cliente, sesion, datos):
    c = _crear(cliente, sesion, datos, consultor_id=None,
               valida_hasta=str(date.today() - timedelta(days=1)))
    assert "Quien la firma" in c["faltan"]
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/enviar",
                     headers=sesion("consultor"))
    assert r.status_code == 400
    assert "Quien la firma" in r.json()["detail"]["faltan"]


def test_la_version_siguiente_sustituye_a_la_anterior_al_mandarse(cliente, sesion, datos):
    v1 = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    r = cliente.post(f"/cotizaciones/eventual/{v1['id']}/version",
                     headers=sesion("consultor"))
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["folio"] == v1["folio"] and v2["version"] == 2
    assert v2["estatus"] == "borrador"
    # La de antes sigue mandada mientras la nueva no sale.
    assert cliente.get(f"/cotizaciones/eventual/{v1['id']}",
                       headers=sesion("consultor")).json()["estatus"] == "enviada"
    # Sin decir que cambio no sale.
    r = cliente.post(f"/cotizaciones/eventual/{v2['id']}/enviar",
                     headers=sesion("consultor"))
    assert r.status_code == 400
    r = cliente.put(f"/cotizaciones/eventual/{v2['id']}",
                    json=_cuerpo(datos, motivo="Beta en Minivan"),
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    v2 = _enviar(cliente, sesion, v2)
    assert [v["estatus"] for v in v2["versiones"]] == ["enviada", "sustituida"]
    # De la anterior ya no sale otra.
    r = cliente.post(f"/cotizaciones/eventual/{v1['id']}/version",
                     headers=sesion("consultor"))
    assert r.status_code == 409


def test_rechazada_con_su_motivo(cliente, sesion, datos):
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/rechazar",
                     json={"motivo": " "}, headers=sesion("consultor"))
    assert r.status_code == 400
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/rechazar",
                     json={"motivo": "Lo cubrió su equipo interno"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["estatus"] == "rechazada"
    assert r.json()["sale_otra"] is True


def test_el_reloj_vence_las_mandadas(cliente, sesion, datos, db):
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    fila = db.get(m.Cotizacion, c["id"])
    fila.valida_hasta = date.today() - timedelta(days=2)
    db.commit()
    assert motor.vencer(db)["vencidas"] == 1
    assert motor.vencer(db)["vencidas"] == 0
    r = cliente.get("/cotizaciones/eventual?vista=cerradas",
                    headers=sesion("consultor"))
    assert [x["estatus"] for x in r.json()["filas"]] == ["vencida"]
    # El cliente todavia la puede autorizar.
    assert cliente.get(f"/cotizaciones/eventual/{c['id']}",
                       headers=sesion("consultor")).json()["se_autoriza"] is True


# ---------------------------------------------------------------- autorizarla

def test_autorizada_nace_el_servicio_con_la_misma_cotizacion(cliente, sesion, datos, db, cliente_de_odoo):
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    r = _autorizar(cliente, sesion, c)
    assert r.status_code == 200, r.text
    nacido = r.json()
    assert nacido["estatus"] == "autorizado"

    db.expire_all()
    servicio = db.get(m.Servicio, nacido["servicio_id"])
    assert servicio.folio == nacido["folio"]
    assert servicio.consultor_id == datos["personal"]["Ana Solis"]["id"]
    assert servicio.solicitante_completo == "Valeria Rodas"
    assert servicio.solicitante_id is not None
    assert [e.alias for e in servicio.equipos] == ["Alfa", "Beta"]
    assert [len(e.jornadas) for e in servicio.equipos] == [2, 1]
    beta = servicio.equipos[1].jornadas[0]
    assert beta.inicio_programado.hour == 18

    cot = db.get(m.Cotizacion, c["id"])
    assert cot.servicio_id == servicio.id
    assert cot.estatus == m.EstatusCotizacion.AUTORIZADA
    assert cot.autorizada_por == "Valeria Rodas"
    assert cot.servicio_folio == servicio.folio
    assert db.query(m.RegistroAccion).filter_by(
        servicio_id=servicio.id, accion="alta desde la cotizacion").count() == 1

    # En el servicio es su cotizacion vigente, con su folio y su PDF.
    b = cliente.get(f"/cotizaciones/servicio/{servicio.id}/bloque",
                    headers=sesion("consultor")).json()
    assert b["vigente"]["id"] == c["id"]
    assert b["vigente"]["folio"] == "EP/COT-0001"
    assert b["vigente"]["tiene_pdf"] is True

    # Ya no se autoriza otra vez ni sale otra version de aqui.
    assert _autorizar(cliente, sesion, c).status_code == 409
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/version",
                     headers=sesion("consultor"))
    assert r.status_code == 409


def test_el_borrador_no_se_autoriza(cliente, sesion, datos, cliente_de_odoo):
    c = _crear(cliente, sesion, datos)
    assert _autorizar(cliente, sesion, c).status_code == 409


def test_la_empresa_nueva_se_autoriza_con_su_cliente_de_odoo(cliente, sesion, datos, lista_general, cliente_de_odoo):
    cuerpo = _cuerpo(datos)
    cuerpo.pop("cliente_id")
    cuerpo.update(prospecto="Henkel Capital", pais_id=datos["mx"]["id"])
    r = cliente.post("/cotizaciones/eventual", json=cuerpo,
                     headers=sesion("consultor"))
    c = _enviar(cliente, sesion, r.json())
    r = _autorizar(cliente, sesion, c)
    assert r.status_code == 400
    assert r.json()["detail"]["clave"] == "sin_cliente"
    r = _autorizar(cliente, sesion, c, cliente_id=str(datos["cliente_id"]))
    assert r.status_code == 200, r.text


def test_el_cliente_que_no_viene_de_odoo_no_se_autoriza(cliente, sesion, datos):
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    r = _autorizar(cliente, sesion, c)
    assert r.status_code == 400


def test_el_comprobante_se_guarda(cliente, sesion, datos, cliente_de_odoo):
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/autorizar",
                     data={"autorizada_por": "Valeria Rodas",
                           "autorizada_el": str(date.today())},
                     files={"comprobante": ("correo.png", PIXEL, "image/png")},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    r = cliente.get(f"/cotizaciones/eventual/{c['id']}/comprobante",
                    headers=sesion("consultor"))
    assert r.status_code == 200 and r.content == PIXEL


def test_el_servicio_que_se_borra_suelta_su_cotizacion(cliente, sesion, datos, db, cliente_de_odoo):
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    nacido = _autorizar(cliente, sesion, c).json()
    r = cliente.request("DELETE", f"/servicios/{nacido['servicio_id']}",
                        json={"motivo": "Se capturó dos veces"},
                        headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    db.expire_all()
    cot = db.get(m.Cotizacion, c["id"])
    assert cot is not None and cot.servicio_id is None
    assert cot.servicio_folio == nacido["folio"]
    fila = cliente.get(f"/cotizaciones/eventual/{c['id']}",
                       headers=sesion("consultor")).json()
    assert fila["servicio"] is None and fila["servicio_folio"] == nacido["folio"]


def test_recotizar_en_el_servicio_sigue_con_el_folio(cliente, sesion, datos, db, cliente_de_odoo):
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    nacido = _autorizar(cliente, sesion, c).json()
    servicio = db.get(m.Servicio, nacido["servicio_id"])
    lineas = []
    for e in servicio.equipos:
        for j in e.jornadas:
            lineas.append({"fecha": str(j.fecha), "tipo": "recurso",
                           "equipo_clave": e.alias, "cantidad": 1,
                           "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"]})
    r = cliente.post("/cotizaciones/autorizada", json={
        "servicio_id": servicio.id, "lineas": lineas, "gastos": "comprobar",
        "autorizada_por": "Valeria Rodas", "autorizada_el": str(date.today()),
        "motivo": "Sin unidad"}, headers=sesion("consultor"))
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 2
    db.expire_all()
    nueva = (db.query(m.Cotizacion).filter_by(servicio_id=servicio.id, version=2)
             .one())
    assert nueva.folio == db.get(m.Cotizacion, c["id"]).folio


# ---------------------------------------------------------------- la lista

def test_la_lista_trae_una_por_folio_con_sus_cuentas(cliente, sesion, datos):
    v1 = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    cliente.post(f"/cotizaciones/eventual/{v1['id']}/version",
                 headers=sesion("consultor"))
    _crear(cliente, sesion, datos)
    r = cliente.get("/cotizaciones/eventual", headers=sesion("consultor"))
    assert r.status_code == 200
    d = r.json()
    assert [(x["folio"], x["version"]) for x in d["filas"]] == [
        ("EP/COT-0002", 1), ("EP/COT-0001", 2)]
    assert d["cuentas"]["todas"] == 2 and d["cuentas"]["abiertas"] == 2
    assert d["puede_armar"] is True
    r = cliente.get("/cotizaciones/eventual?q=cot-0002",
                    headers=sesion("consultor"))
    assert [x["folio"] for x in r.json()["filas"]] == ["EP/COT-0002"]


def test_quien_puede_que(cliente, sesion, datos):
    assert cliente.get("/cotizaciones/eventual",
                       headers=sesion("central")).status_code == 403
    assert cliente.post("/cotizaciones/eventual", json=_cuerpo(datos),
                        headers=sesion("finanzas")).status_code == 403
    assert cliente.get("/cotizaciones/eventual",
                       headers=sesion("diroperaciones")).status_code == 200
    _crear(cliente, sesion, datos, quien="diroperaciones")


# ---------------------------------------------------------------- el PDF

@pytest.mark.parametrize("idioma,titulo,completo", [
    ("es", "COTIZACIÓN", "Día completo"), ("en", "QUOTATION", "Full day"),
    ("pt", "COTAÇÃO", "Dia inteiro")])
def test_el_pdf_en_su_idioma(cliente, sesion, datos, db, idioma, titulo, completo):
    c = _crear(cliente, sesion, datos, idioma=idioma)
    cot = db.get(m.Cotizacion, c["id"])
    texto = cotizacion_pdf.html_de(db, cot)
    assert titulo in texto and completo in texto
    assert "EP/COT-0001" in texto and "Centauro ASS, S.A. de C.V." in texto
    assert "16%" in texto
    # Solo la modalidad: el horario no sale (decision de Salvador).
    assert "18:00" not in texto
    # El borrador lo dice.
    assert "BORRADOR" in texto or "DRAFT" in texto or "RASCUNHO" in texto
    assert cotizacion_pdf.pdf(db, cot).startswith(b"%PDF")


def test_el_pdf_lleva_el_dia_del_pais(cliente, sesion, datos, db):
    """Mandada a las 9 de la noche en Mexico ya es otro dia en UTC: la
    fecha del PDF y su nombre van con el dia de alla."""
    from datetime import datetime, timezone

    c = _crear(cliente, sesion, datos)
    cot = db.get(m.Cotizacion, c["id"])
    cot.enviada_en = datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc)
    try:
        assert cotizacion_pdf.dia_de_la_cotizacion(db, cot) == date(2026, 9, 30)
        assert cotizacion_pdf.nombre_del_archivo(db, cot).startswith("20260930_EP-COT-")
        assert "30 de septiembre de 2026" in cotizacion_pdf.html_de(db, cot)
    finally:
        db.rollback()


def test_el_pdf_dice_lo_que_no_lleva_iva(cliente, sesion, datos, db):
    c = _crear(cliente, sesion, datos, con_iva=False)
    texto = cotizacion_pdf.html_de(db, db.get(m.Cotizacion, c["id"]))
    assert "Precios sin IVA." in texto and "Total con IVA" not in texto


def test_las_fechas_se_dicen_bien():
    d = date
    assert cotizacion_pdf.rango(d(2026, 9, 27), d(2026, 9, 29), "es") == \
        "del 27 al 29 de septiembre de 2026"
    assert cotizacion_pdf.rango(d(2026, 9, 27), d(2026, 9, 29), "en") == \
        "from September 27 to 29, 2026"
    assert cotizacion_pdf.rango(d(2026, 9, 30), d(2026, 10, 2), "pt") == \
        "de 30 de setembro a 2 de outubro de 2026"
    assert cotizacion_pdf.rango(d(2026, 9, 27), d(2026, 9, 27), "es") == \
        "el 27 de septiembre de 2026"
    assert cotizacion_pdf.dinero(D("45069"), "MXN") == "$45,069.00"
    assert cotizacion_pdf.dinero(D("4182.5"), "USD") == "US$4,182.50"
    assert cotizacion_pdf.dinero(D("3083"), "BRL") == "R$ 3.083,00"
    assert cotizacion_pdf.producto_limpio(
        "Conductor de Seguridad Bilingüe + CUV (Todo incluido, Transfer)") == \
        "Conductor de Seguridad Bilingüe + CUV"


# ---------------------------------------------------------------- la firma

def test_la_firma_es_de_quien_la_sube(cliente, sesion, datos, db):
    r = cliente.get("/cotizaciones/firma", headers=sesion("consultor"))
    assert r.json() == {"tiene": False, "imagen": None}
    r = cliente.put("/cotizaciones/firma", headers=sesion("consultor"),
                    files={"archivo": ("firma.png", PIXEL, "image/png")})
    assert r.status_code == 200, r.text
    assert cliente.get("/cotizaciones/firma",
                       headers=sesion("consultor")).json()["tiene"] is True
    # La de otro consultor no se ve desde aqui: cada quien la suya.
    assert cliente.get("/cotizaciones/firma",
                       headers=sesion("consultor2")).json()["tiene"] is False
    c = _crear(cliente, sesion, datos)
    assert c["firma"] is True
    assert base64.b64encode(PIXEL).decode() in cotizacion_pdf.html_de(
        db, db.get(m.Cotizacion, c["id"]))
    r = cliente.put("/cotizaciones/firma", headers=sesion("consultor"),
                    files={"archivo": ("firma.svg", b"<svg/>", "image/svg+xml")})
    assert r.status_code == 400


# ---------------------------------------------------------------- Catalogos

def test_los_textos_los_cambia_direccion_de_operaciones(cliente, sesion, datos, db):
    mx = datos["mx"]["id"]
    antes = cliente.get(f"/cotizaciones/textos?pais_id={mx}",
                        headers=sesion("consultor")).json()
    assert antes["razon_social"] == "Centauro ASS, S.A. de C.V."
    assert antes["textos"]["cancelacion"]["es"].startswith("Si se cancela")
    assert antes["textos"]["pago"]["es"] == ""

    cuerpo = {"razon_social": antes["razon_social"], "rfc": "cas123456ab1",
              "tasa_iva": "0.16",
              "textos": {"pago": {"es": "Crédito a 30 días."}}}
    assert cliente.put(f"/cotizaciones/textos/{mx}", json=cuerpo,
                       headers=sesion("consultor")).status_code == 403
    try:
        r = cliente.put(f"/cotizaciones/textos/{mx}", json=cuerpo,
                        headers=sesion("diroperaciones"))
        assert r.status_code == 200, r.text
        assert r.json()["rfc"] == "CAS123456AB1"
        assert r.json()["textos"]["pago"]["es"] == "Crédito a 30 días."
        acciones = {x.accion for x in db.query(m.RegistroAdmin)
                    .filter_by(objeto="cotizacion").all()}
        assert acciones == {"catalogo cambiado", "textos de la cotizacion"}
        r = cliente.get("/bitacora-admin/catalogo/cotizacion?idioma=es",
                        headers=sesion("admin"))
        frases = " | ".join(x["que"] for x in r.json()["filas"])
        assert "condiciones de pago (es)" in frases and "RFC" in frases
    finally:
        cliente.put(f"/cotizaciones/textos/{mx}", headers=sesion("admin"),
                    json={"razon_social": antes["razon_social"], "rfc": None,
                          "tasa_iva": "0.16", "textos": {"pago": {"es": ""}}})


def test_la_semilla_y_la_migracion_dicen_lo_mismo():
    ruta = RAIZ / "migrations" / "versions" / "e3a5c7b9d1f4_cotizaciones_en_connect.py"
    spec = importlib.util.spec_from_file_location("migracion_114", ruta)
    migracion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracion)
    assert migracion.DATOS_MEXICO == motor.DATOS_MEXICO
    assert migracion.TEXTOS_MEXICO == motor.TEXTOS_MEXICO
    assert set(motor.TEXTOS_MEXICO) <= set(motor.CLAVES_DE_TEXTO)

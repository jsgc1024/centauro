# -*- coding: utf-8 -*-
"""Escoger la moneda al cotizar (seccion 120).

Decision de Salvador, 2 de octubre: con una lista general en pesos y otra
en dolares para el mismo pais, quien arma la cotizacion escoge la moneda.

  * Se escoge solo si el pais tiene general en mas de una moneda. Con una,
    la moneda es la de esa general.
  * La empresa que todavia no esta en Odoo y el cliente que esta en la
    general se cotizan con la general de la moneda que se escoge. Sin
    escoger, la de la moneda del pais; el cliente, la de su ficha.
  * El cliente con lista pactada, en la moneda de su lista: no se escoge.
  * Los precios no se convierten: salen de la general de esa moneda.
  * Mandarla y la version siguiente siguen en la moneda escogida, y en el
    servicio la recotizacion sigue en la moneda que se autorizo.
  * Antes de autorizar se ve el tipo de cambio que queda fijo.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app import cotizacion as motor_servicio
from app import cotizacion_cliente as motor
from app import models as m
from ayudas import manana

D = Decimal
ENTRE = D("20")      # los dolares de la prueba: los pesos entre 20


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture
def cliente_de_odoo(db, datos):
    cliente = db.get(m.Cliente, datos["cliente_id"])
    antes = cliente.odoo_id
    cliente.odoo_id = 990120
    db.commit()
    yield cliente
    cliente = db.get(m.Cliente, datos["cliente_id"])
    cliente.odoo_id = antes
    db.commit()


@pytest.fixture
def lista_general(db, datos):
    """La lista de la semilla, la unica general de Mexico, en pesos."""
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


def _copia(db, base, nombre, moneda, general, entre=D("1"), odoo_id=None):
    """Otra lista con los renglones de `base`, entre `entre`."""
    nueva = m.Tarifario(
        nombre=nombre, pais_id=base.pais_id, moneda=moneda,
        vigencia_desde=date.today(), activo=True, general=general,
        odoo_id=odoo_id, paquetes_con_viaticos=base.paquetes_con_viaticos,
        precio_hora_extra=(D(str(base.precio_hora_extra)) / entre
                           if base.precio_hora_extra is not None else None))
    db.add(nueva)
    db.flush()
    for r in db.query(m.TarifaRecurso).filter_by(tarifario_id=base.id).all():
        db.add(m.TarifaRecurso(
            tarifario_id=nueva.id, perfil_id=r.perfil_id,
            modalidad_id=r.modalidad_id, precio=D(str(r.precio)) / entre,
            precio_hora_extra=(D(str(r.precio_hora_extra)) / entre
                               if r.precio_hora_extra is not None else None)))
    for v in db.query(m.TarifaVehiculo).filter_by(tarifario_id=base.id).all():
        db.add(m.TarifaVehiculo(
            tarifario_id=nueva.id, categoria_id=v.categoria_id,
            modalidad_id=v.modalidad_id, precio=D(str(v.precio)) / entre))
    for p in db.query(m.TarifaPaquete).filter_by(tarifario_id=base.id).all():
        db.add(m.TarifaPaquete(
            tarifario_id=nueva.id, perfil_id=p.perfil_id,
            categoria_id=p.categoria_id, modalidad_id=p.modalidad_id,
            precio=D(str(p.precio)) / entre))
    db.commit()
    return nueva


def _borrar(db, *listas):
    """Las listas de la prueba se van, con lo que las nombra: las
    cotizaciones se vacian igual antes de la prueba siguiente."""
    db.rollback()
    ids = [t.id for t in listas]
    with db.bind.begin() as con:
        con.execute(text("TRUNCATE cotizacion CASCADE"))
        for tabla in ("tarifa_recurso", "tarifa_vehiculo", "tarifa_paquete"):
            con.execute(text(f"DELETE FROM {tabla} WHERE tarifario_id = ANY(:ids)"),
                        {"ids": ids})
        con.execute(text("UPDATE cliente SET tarifario_id = NULL "
                         "WHERE tarifario_id = ANY(:ids)"), {"ids": ids})
        con.execute(text("DELETE FROM tarifario WHERE id = ANY(:ids)"),
                    {"ids": ids})


@pytest.fixture
def general_en_dolares(db, lista_general):
    """Junto a la general en pesos, la general en dolares: los mismos
    renglones entre 20."""
    usd = _copia(db, lista_general, "PE · General México USD", m.Moneda.USD,
                 True, ENTRE, odoo_id=990121)
    yield usd
    _borrar(db, usd)


@pytest.fixture
def otro_cliente(db, datos):
    """Un segundo cliente de Mexico, solo para la prueba."""
    otro = m.Cliente(nombre="Cliente de prueba de la moneda",
                     pais_id=datos["mx"]["id"], activo=True)
    db.add(otro)
    db.commit()
    otro_id = otro.id
    yield otro
    db.rollback()
    with db.bind.begin() as con:
        con.execute(text("TRUNCATE cotizacion CASCADE"))
        con.execute(text("DELETE FROM solicitante WHERE cliente_id = :c"),
                    {"c": otro_id})
        con.execute(text("DELETE FROM cliente WHERE id = :c"), {"c": otro_id})


def _dia(datos, offset, modalidad="full_day", **extra):
    return {"fecha": str(manana(offset)),
            "modalidad_id": datos["modalidades"][modalidad]["id"], **extra}


def _cuerpo(datos, offset=3000, **extra):
    """Alfa dos dias completos y Beta un transfer, con conductor y
    Suburban blindada: 28,000 pesos en la lista de la semilla."""
    lleva = [{"tipo": "recurso", "id": datos["perfiles"]["conductor_seguridad"]["id"],
              "cantidad": 1},
             {"tipo": "vehiculo", "id": datos["categorias"]["suv_blindada"]["id"],
              "cantidad": 1}]
    return {
        "cliente_id": datos["cliente_id"],
        "solicitante_nombre": "Valeria", "solicitante_apellidos": "Rodas",
        "solicitante_correo": "valeria.rodas@ejemplo.com",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "tipo_servicio": "Transportación ejecutiva",
        "valida_hasta": str(date.today() + timedelta(days=60)),
        "idioma": "es", "con_iva": True, "gastos": "dentro",
        "equipos": [
            {"plaza_id": datos["cdmx"]["id"], "lleva": lleva,
             "dias": [_dia(datos, offset), _dia(datos, offset + 1)]},
            {"plaza_id": datos["cdmx"]["id"], "lleva": lleva,
             "dias": [_dia(datos, offset, "transfer", hora="18:00")]},
        ],
        **extra,
    }


def _prospecto(datos, **extra):
    cuerpo = _cuerpo(datos, **extra)
    cuerpo.update(cliente_id=None, prospecto="Grupo Industrial del Bajío",
                  pais_id=datos["mx"]["id"])
    return cuerpo


def _info(cliente, sesion, **qs):
    ruta = "/cotizaciones/eventual/lista-de-precios?" + "&".join(
        f"{k}={v}" for k, v in qs.items())
    return cliente.get(ruta, headers=sesion("consultor"))


def _crear(cliente, sesion, cuerpo):
    r = cliente.post("/cotizaciones/eventual", json=cuerpo,
                     headers=sesion("consultor"))
    assert r.status_code == 201, r.text
    return r.json()


def _poner_tc(cliente, sesion, tasa="17.50"):
    r = cliente.put("/tarifarios/tipo-de-cambio", json={"tasa": tasa},
                    headers=sesion("finanzas"))
    assert r.status_code == 200, r.text


# ================================================================ la lista

def test_con_una_sola_general_no_se_escoge(cliente, sesion, datos, lista_general):
    r = _info(cliente, sesion, pais_id=datos["mx"]["id"])
    assert r.status_code == 200, r.text
    i = r.json()
    assert i["tarifario"]["id"] == lista_general.id
    assert i["tarifario"]["moneda"] == "MXN"
    assert i["monedas"] == [] and i["escogida"] is False and i["pactada"] is False
    i = _info(cliente, sesion, cliente_id=datos["cliente_id"]).json()
    assert i["monedas"] == [] and i["tarifario"]["id"] == lista_general.id
    # Pedir una moneda que no tiene general lo dice, en vez de cotizar en
    # otra.
    r = _info(cliente, sesion, pais_id=datos["mx"]["id"], moneda="USD")
    assert r.status_code == 400
    assert r.json()["detail"]["clave"] == "sin_lista"
    assert "en USD" in r.json()["detail"]["mensaje"]


def test_la_empresa_nueva_escoge_entre_las_generales(cliente, sesion, datos, lista_general,
                                                     general_en_dolares):
    i = _info(cliente, sesion, pais_id=datos["mx"]["id"]).json()
    # Sin escoger, la del pais: pesos.
    assert i["tarifario"]["id"] == lista_general.id
    assert i["monedas"] == ["MXN", "USD"]
    i = _info(cliente, sesion, pais_id=datos["mx"]["id"], moneda="USD").json()
    assert i["tarifario"]["id"] == general_en_dolares.id
    assert i["tarifario"]["moneda"] == "USD" and i["escogida"] is False
    i = _info(cliente, sesion, pais_id=datos["mx"]["id"], moneda="MXN").json()
    assert i["tarifario"]["id"] == lista_general.id
    assert _info(cliente, sesion, pais_id=datos["mx"]["id"],
                 moneda="XYZ").status_code == 400


def test_el_cliente_en_la_general_escoge_y_se_dice(cliente, sesion, datos, lista_general,
                                                   general_en_dolares):
    i = _info(cliente, sesion, cliente_id=datos["cliente_id"]).json()
    assert i["tarifario"]["id"] == lista_general.id
    assert i["monedas"] == ["MXN", "USD"] and i["escogida"] is False
    i = _info(cliente, sesion, cliente_id=datos["cliente_id"], moneda="USD").json()
    assert i["tarifario"]["id"] == general_en_dolares.id
    # No es «la lista del cliente en Odoo»: la escogio quien cotiza.
    assert i["escogida"] is True and i["pactada"] is False


def test_el_cliente_con_la_general_en_dolares_en_su_ficha_arranca_en_dolares(
        cliente, sesion, datos, db, lista_general, general_en_dolares, otro_cliente):
    otro_cliente.tarifario_id = general_en_dolares.id
    db.commit()
    i = _info(cliente, sesion, cliente_id=otro_cliente.id).json()
    assert i["tarifario"]["id"] == general_en_dolares.id and i["escogida"] is False
    assert i["monedas"] == ["MXN", "USD"]
    i = _info(cliente, sesion, cliente_id=otro_cliente.id, moneda="MXN").json()
    assert i["tarifario"]["id"] == lista_general.id and i["escogida"] is True


def test_la_lista_pactada_se_queda_en_su_moneda(cliente, sesion, datos, db, lista_general,
                                                general_en_dolares, otro_cliente):
    pactada = _copia(db, lista_general, "Pactada de prueba", m.Moneda.MXN, False)
    try:
        otro_cliente.tarifario_id = pactada.id
        db.commit()
        for qs in ({}, {"moneda": "USD"}):
            i = _info(cliente, sesion, cliente_id=otro_cliente.id, **qs).json()
            assert i["tarifario"]["id"] == pactada.id
            assert i["monedas"] == [] and i["pactada"] is True
            assert i["escogida"] is False
    finally:
        otro = db.get(m.Cliente, otro_cliente.id)
        otro.tarifario_id = None
        db.commit()
        _borrar(db, pactada)


def test_sin_escoger_va_la_de_la_moneda_del_pais_aunque_la_otra_sea_mas_vieja(
        db, datos, lista_general):
    """Antes, con dos generales, ganaba la que Connect conocia primero."""
    usd = _copia(db, lista_general, "PE · General México USD", m.Moneda.USD,
                 True, ENTRE, odoo_id=990122)
    pesos = _copia(db, lista_general, "PE · General México 2027", m.Moneda.MXN,
                   True, odoo_id=990123)
    semilla = db.get(m.Tarifario, lista_general.id)
    semilla.general = False
    db.commit()
    try:
        assert usd.id < pesos.id
        assert motor.general_del_pais(db, datos["mx"]["id"]).id == pesos.id
        assert motor.general_del_pais(db, datos["mx"]["id"], "USD").id == usd.id
        assert motor_servicio.monedas_generales(db, datos["mx"]["id"]) == ["MXN", "USD"]
    finally:
        semilla = db.get(m.Tarifario, lista_general.id)
        semilla.general = True
        db.commit()
        _borrar(db, usd, pesos)


# ================================================================ la cotizacion

def test_se_guarda_se_manda_y_se_recotiza_en_la_moneda_escogida(
        cliente, sesion, datos, db, lista_general, general_en_dolares):
    c = _crear(cliente, sesion, _prospecto(datos, moneda="USD"))
    assert c["moneda"] == "USD"
    assert c["tarifario"]["id"] == general_en_dolares.id
    # 28,000 pesos entre 20.
    assert D(str(c["subtotal"])) == D("1400")

    # Mandarla vuelve a cotizar con la lista de hoy, en la misma moneda.
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/enviar",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["moneda"] == "USD"
    assert D(str(r.json()["subtotal"])) == D("1400")

    # La version siguiente sale en dolares, y en su borrador se cambia.
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/version",
                     headers=sesion("consultor"))
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["moneda"] == "USD"
    r = cliente.put(f"/cotizaciones/eventual/{v2['id']}",
                    json=_prospecto(datos, moneda="MXN",
                                    motivo="El cliente paga en pesos"),
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["moneda"] == "MXN"
    assert D(str(r.json()["subtotal"])) == D("28000")


def test_el_cliente_con_lista_pactada_no_cambia_de_moneda_al_guardar(
        cliente, sesion, datos, db, lista_general, general_en_dolares, otro_cliente):
    pactada = _copia(db, lista_general, "Pactada de prueba", m.Moneda.MXN, False)
    try:
        otro_cliente.tarifario_id = pactada.id
        db.commit()
        c = _crear(cliente, sesion, _cuerpo(datos, cliente_id=otro_cliente.id,
                                            moneda="USD"))
        assert c["moneda"] == "MXN" and c["tarifario"]["id"] == pactada.id
    finally:
        otro = db.get(m.Cliente, otro_cliente.id)
        otro.tarifario_id = None
        db.commit()
        _borrar(db, pactada)


def test_antes_de_autorizar_se_ve_el_tipo_de_cambio(cliente, sesion, datos, lista_general,
                                                    general_en_dolares):
    c = _crear(cliente, sesion, _cuerpo(datos, moneda="USD"))
    d = cliente.get(f"/cotizaciones/eventual/{c['id']}",
                    headers=sesion("consultor")).json()
    assert d["moneda"] == "USD" and d["moneda_local"] == "MXN"
    assert d["tipo_cambio_hoy"] is None          # todavia no lo pone nadie
    _poner_tc(cliente, sesion, "17.5")
    d = cliente.get(f"/cotizaciones/eventual/{c['id']}",
                    headers=sesion("consultor")).json()
    assert d["tipo_cambio_hoy"]["corta"] == "17.50"
    assert d["tipo_cambio_hoy"]["por"]
    # En pesos no hay nada que fijar.
    c = _crear(cliente, sesion, _cuerpo(datos, offset=3100))
    d = cliente.get(f"/cotizaciones/eventual/{c['id']}",
                    headers=sesion("consultor")).json()
    assert d["moneda"] == "MXN" and d["tipo_cambio_hoy"] is None


def test_en_el_servicio_se_recotiza_en_la_moneda_autorizada(
        cliente, sesion, datos, db, lista_general, general_en_dolares, cliente_de_odoo):
    c = _crear(cliente, sesion, _cuerpo(datos, moneda="USD"))
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/enviar",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    _poner_tc(cliente, sesion)
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/autorizar", data={
        "autorizada_por": "Valeria Rodas", "autorizada_el": str(date.today())},
        headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    servicio_id = r.json()["servicio_id"]

    # El cliente esta en la general en pesos; su cotizacion autorizada, en
    # dolares: el bloque del servicio recotiza con la general en dolares.
    b = cliente.get(f"/cotizaciones/servicio/{servicio_id}/bloque",
                    headers=sesion("consultor")).json()
    assert b["tarifario"]["id"] == general_en_dolares.id
    assert b["tarifario"]["moneda"] == "USD" and b["tarifario"]["escogida"] is True
    assert b["vigente"]["tipo_cambio"]["corta"] == "17.50"

    servicio = db.get(m.Servicio, servicio_id)
    lineas = [{"fecha": str(j.fecha), "tipo": "recurso", "equipo_clave": e.alias,
               "cantidad": 1,
               "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"]}
              for e in servicio.equipos for j in e.jornadas]
    r = cliente.post("/cotizaciones/autorizada", json={
        "servicio_id": servicio_id, "lineas": lineas, "gastos": "comprobar",
        "autorizada_por": "Valeria Rodas", "autorizada_el": str(date.today()),
        "motivo": "Sin unidad"}, headers=sesion("consultor"))
    assert r.status_code == 201, r.text
    db.expire_all()
    v2 = db.query(m.Cotizacion).filter_by(servicio_id=servicio_id, version=2).one()
    assert v2.moneda == m.Moneda.USD and v2.tarifario_id == general_en_dolares.id

    # Con lista pactada, la recotizacion sale con su lista, como siempre.
    pactada = _copia(db, lista_general, "Pactada de prueba", m.Moneda.MXN, False)
    try:
        cliente_db = db.get(m.Cliente, datos["cliente_id"])
        cliente_db.tarifario_id = pactada.id
        db.commit()
        b = cliente.get(f"/cotizaciones/servicio/{servicio_id}/bloque",
                        headers=sesion("consultor")).json()
        assert b["tarifario"]["id"] == pactada.id
        assert b["tarifario"]["escogida"] is False
    finally:
        cliente_db = db.get(m.Cliente, datos["cliente_id"])
        cliente_db.tarifario_id = lista_general.id
        db.commit()
        _borrar(db, pactada)

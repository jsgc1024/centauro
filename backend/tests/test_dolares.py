# -*- coding: utf-8 -*-
"""Dolares en la cotizacion (seccion 82).

Amazon paga en dolares y los costos --comisiones, viaticos, unidad--
siempre son en pesos. Decisiones de Salvador, 26 de septiembre:

  * El tipo de cambio lo pone finanzas a mano, en Tarifarios, y el que se
    pone aplica para todo hasta que alguien lo cambie.
  * La utilidad y la comision del consultor, al que estaba puesto cuando
    se autorizo la cotizacion: fijo, no se mueve con el dolar.
  * Los gastos netos se comprueban en pesos y se facturan en dolares, en
    la misma factura, al que esta puesto en el visto bueno.
  * Tambien el implantado: el mes toma la moneda de su lista.

Sin tipo de cambio no se inventa uno: la cotizacion no se autoriza y el
visto bueno no pasa. El viatico se da por comprobado directo en la base:
aqui importa la cuenta, no el camino de la comprobacion.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app import cierre as motor_cierre
from app import facturacion
from app import models as m
from app import tipo_cambio
from ayudas import (asignar, configurar_origen, crear_servicio,
                    ejecutar_jornada, jornada, manana)

D = Decimal
MOTIVO = "El equipo cerro por telefono; confirmado con el cliente"
DIAS = [date(2029, 9, d) for d in (24, 25, 26, 27, 28)]
CONDUCTOR_USD = D("100.00")        # por dia, en la lista de implantados
SUV_USD = D("300.00")              # por dia; la unidad va por mes


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture(autouse=True)
def sin_odoo(monkeypatch):
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")


@pytest.fixture
def en_dolares(db, datos):
    """El tarifario del cliente de las pruebas, en dolares: los mismos
    numeros, rotulados en USD. Se regresa a su moneda al terminar."""
    tarifario = db.get(m.Cliente, datos["cliente_id"]).tarifario
    antes = tarifario.moneda.name
    with db.bind.begin() as con:
        con.execute(text("UPDATE tarifario SET moneda = 'USD' WHERE id = :t"),
                    {"t": tarifario.id})
    yield tarifario.id
    with db.bind.begin() as con:
        con.execute(text("UPDATE tarifario SET moneda = CAST(:m AS moneda) "
                         "WHERE id = :t"), {"t": tarifario.id, "m": antes})


def _poner(cliente, sesion, tasa, quien="finanzas"):
    r = cliente.put("/tarifarios/tipo-de-cambio", json={"tasa": tasa},
                    headers=sesion(quien))
    assert r.status_code == 200, r.text
    return r.json()


def _viatico(cliente, sesion, datos, jornada_id, monto="900"):
    r = cliente.post("/viaticos/asignar", headers=sesion("consultor"), json={
        "jornada_id": jornada_id,
        "persona_id": datos["personal"]["Juan Ramirez"]["id"],
        "conceptos": [{"concepto": "alimentos", "monto": monto,
                       "origen": "tabulador"}]})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _comprobado(viatico_id, monto):
    """Comprobado completo con un ticket valido, y cerrado."""
    from app.db import SessionLocal
    with SessionLocal() as sesion:
        v = sesion.get(m.AsignacionViatico, viatico_id)
        sesion.add(m.Comprobante(asignacion_id=v.id,
                                 concepto=m.ConceptoViatico.ALIMENTOS,
                                 tipo=m.TipoComprobante.NOTA, monto=D(monto),
                                 validado=True))
        v.monto_comprobado = D(monto)
        v.estatus = m.EstatusViatico.CERRADO
        sesion.commit()


def _cierre_de(servicio_id):
    from app.db import SessionLocal
    with SessionLocal() as sesion:
        return (sesion.query(m.Cierre)
                .filter_by(servicio_id=servicio_id, contrato_id=None).first().id)


# ================================================================ el tipo de cambio

def test_lo_pone_finanzas_y_se_queda_hasta_que_se_cambia(cliente, sesion, db):
    r = cliente.get("/tarifarios/tipo-de-cambio", headers=sesion("consultor"))
    assert r.status_code == 200
    assert r.json()["vigente"] is None and r.json()["puede_editar"] is False

    # El consultor lo ve; ponerlo es de finanzas.
    r = cliente.put("/tarifarios/tipo-de-cambio", json={"tasa": "17.5"},
                    headers=sesion("consultor"))
    assert r.status_code == 403

    estado = _poner(cliente, sesion, "17.5")
    assert estado["vigente"]["tasa"] == "17.5000"
    assert estado["vigente"]["por"] and estado["puede_editar"] is True
    # El mismo otra vez no escribe nada; otro se vuelve el que vale, y el
    # anterior queda en la historia.
    _poner(cliente, sesion, "17.50")
    estado = _poner(cliente, sesion, "18.1234")
    assert estado["vigente"]["tasa"] == "18.1234"
    assert [x["tasa"] for x in estado["anteriores"]] == ["17.5000"]
    assert tipo_cambio.vigente(db, "USD", "MXN")["tasa"] == D("18.1234")
    registro = (db.query(m.RegistroAdmin)
                .filter_by(accion="tipo de cambio").order_by(m.RegistroAdmin.id)
                .all())
    assert [(x.antes, x.despues) for x in registro] == [
        (None, "17.5000"), ("17.5000", "18.1234")]

    # Un numero que no es un tipo de cambio no entra.
    for malo in ("0", "-3", "10000", "diecisiete"):
        r = cliente.put("/tarifarios/tipo-de-cambio", json={"tasa": malo},
                        headers=sesion("finanzas"))
        assert r.status_code in (400, 422), malo


def test_solo_convierte_dolares_a_pesos(db):
    assert tipo_cambio.se_puede("USD", "MXN")
    assert tipo_cambio.se_puede("MXN", "MXN")
    assert not tipo_cambio.se_puede("USD", "BRL")
    assert tipo_cambio.vigente(db, "MXN", "MXN")["tasa"] == 1
    assert tipo_cambio.a_local("1122", "17.40") == D("19522.80")
    assert tipo_cambio.de_local("2204", "17.50") == D("125.94")
    assert tipo_cambio.corto("17.5") == "17.50"
    assert tipo_cambio.corto("17.4523") == "17.4523"
    assert tipo_cambio.corto("18") == "18.00"


# ================================================================ el eventual

def _eventual(cliente, sesion, datos, incluidos=False, offset=1500):
    """Un dia cotizado en dolares --conductor y SUV blindada--, todavia sin
    autorizar."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    r = cliente.post("/cotizaciones", headers=h, json={
        "servicio_id": servicio["id"], "viaticos_incluidos": incluidos,
        "lineas": [
            {"fecha": j["fecha"], "tipo": "recurso",
             "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"]},
            {"fecha": j["fecha"], "tipo": "vehiculo",
             "categoria_id": datos["categorias"]["suv_blindada"]["id"]}]})
    assert r.status_code == 201, r.text
    assert r.json()["moneda"] == "USD"
    return servicio, j, r.json()["cotizacion_id"]


def _autorizar(cliente, sesion, cotizacion_id):
    return cliente.post(f"/cotizaciones/{cotizacion_id}/autorizar",
                        json={"autorizada_por": "Cliente de prueba"},
                        headers=sesion("consultor"))


def _trabajar(cliente, sesion, datos, j, gasto="900"):
    h = sesion("consultor")
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    vid = _viatico(cliente, sesion, datos, j["id"])
    assert ejecutar_jornada(cliente, sesion("juan"), j).status_code == 200
    _comprobado(vid, gasto)


def _comparativo(cliente, sesion, servicio_id):
    r = cliente.get(f"/cierre/servicio/{servicio_id}/comparativo",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


def test_sin_tipo_de_cambio_no_se_autoriza(cliente, sesion, datos, en_dolares, db):
    servicio, _, cotizacion_id = _eventual(cliente, sesion, datos)
    r = _autorizar(cliente, sesion, cotizacion_id)
    assert r.status_code == 409
    assert r.json()["detail"]["motivo"] == "sin_tipo_de_cambio"
    assert "Tarifarios" in r.json()["detail"]["que_hacer"]

    _poner(cliente, sesion, "17.40")
    assert _autorizar(cliente, sesion, cotizacion_id).status_code == 200
    # Se queda con el que estaba puesto, aunque despues se cambie.
    _poner(cliente, sesion, "19")
    db.expire_all()
    cotizacion = db.get(m.Cotizacion, cotizacion_id)
    assert D(str(cotizacion.tipo_cambio)) == D("17.40")
    assert cotizacion.tipo_cambio_fecha is not None


def test_el_eventual_en_dolares_de_la_cotizacion_a_la_comision(
        cliente, sesion, datos, en_dolares, db):
    """Servicio en dolares, gastos netos en pesos: la factura en dolares
    con los gastos al tipo de cambio del visto bueno; la utilidad y la
    comision, en pesos, al de la autorizacion."""
    servicio, j, cotizacion_id = _eventual(cliente, sesion, datos)
    _poner(cliente, sesion, "17.40")
    assert _autorizar(cliente, sesion, cotizacion_id).status_code == 200
    _trabajar(cliente, sesion, datos, j)

    # Antes del visto bueno los gastos se ven al que esta puesto hoy.
    _poner(cliente, sesion, "17.50")
    cmp = _comparativo(cliente, sesion, servicio["id"])
    servicio_usd = D(str(cmp["ejecutado"]["total"]))
    assert cmp["moneda"] == "USD" and cmp["moneda_local"] == "MXN"
    assert cmp["cotizacion"]["tipo_cambio"]["tasa"] == "17.4000"
    gastos = cmp["gastos"]
    assert D(str(gastos["comprobado"])) == D(900)
    assert D(str(gastos["a_facturar"])) == D("51.43")          # 900 / 17.50
    assert gastos["tipo_cambio"]["tasa"] == "17.5000"
    assert gastos["tipo_cambio"]["fijo"] is False
    assert gastos["sin_tipo_de_cambio"] is None
    assert D(str(cmp["a_facturar"]["total"])) == servicio_usd + D("51.43")
    assert D(str(cmp["viaticos"]["facturable_al_cliente"])) == D("51.43")

    # El visto bueno lo deja fijo; lo que se cambie despues ya no lo mueve.
    cierre_id = _cierre_de(servicio["id"])
    r = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    _poner(cliente, sesion, "18")
    cmp = _comparativo(cliente, sesion, servicio["id"])
    assert cmp["gastos"]["tipo_cambio"] == {**cmp["gastos"]["tipo_cambio"],
                                            "tasa": "17.5000", "fijo": True}
    db.expire_all()
    registro = db.get(m.Cierre, cierre_id)
    assert D(str(registro.total_ejecutado)) == servicio_usd + D("51.43")

    # La factura: en dolares, y el renglon de gastos dice de donde sale.
    cuerpo = facturacion.armar(db, registro)
    assert cuerpo["moneda"] == "USD"
    renglon = next(c for c in cuerpo["conceptos"] if c["tipo"] == "viaticos")
    assert renglon["importe"] == "51.43"
    assert renglon["origen"] == {"moneda": "MXN", "importe": "900.00",
                                 "tipo_cambio": "17.5000"}
    assert "MXN 900.00 al tipo de cambio 17.50)" in renglon["descripcion"]
    assert D(cuerpo["total"]) == servicio_usd + D("51.43")

    # El desglose: los pesos como se pagaron, y los dolares de la factura.
    r = cliente.get(f"/cierre/servicio/{servicio['id']}/desglose-gastos",
                    params={"idioma": "es"}, headers=sesion("consultor"))
    assert r.status_code == 200
    assert "$900.00 MXN" in r.text and "$51.43 USD" in r.text
    assert "17.50 MXN por USD" in r.text

    # La tarjeta del cierre y la bandeja dicen la moneda de la factura.
    estado = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                         headers=sesion("consultor")).json()
    assert estado["moneda"] == "USD"
    assert estado["tipo_cambio_gastos"]["tasa"] == "17.5000"
    bandeja = cliente.get("/cierre/facturacion", headers=sesion("finanzas")).json()
    assert {"moneda": "USD", "monto": str(servicio_usd + D("51.43"))} in [
        {"moneda": x["moneda"], "monto": str(D(str(x["monto"])))}
        for x in bandeja["resumen"]["por_aprobar"]["montos"]]
    suyo = next(x for x in bandeja["por_aprobar"] if x["cierre_id"] == cierre_id)
    assert suyo["moneda"] == "USD"
    assert D(str(suyo["gastos"]["monto"])) == D("51.43")

    # Finanzas aprueba: la comision en pesos, al tipo de la cotizacion.
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    servicio_mxn = tipo_cambio.a_local(servicio_usd, "17.40")
    comision = r.json()["comision_consultor"]
    assert D(str(comision["base"])) == servicio_mxn
    fila = db.query(m.ComisionConsultor).filter_by(
        servicio_id=servicio["id"]).one()
    assert fila.moneda == m.Moneda.MXN
    assert D(str(fila.facturacion)) == servicio_mxn + 900
    assert D(str(fila.viaticos)) == 900
    assert D(str(fila.monto)) == (servicio_mxn * D(str(fila.porcentaje))
                                  / 100).quantize(D("0.01"))
    assert fila.moneda_facturada == m.Moneda.USD
    assert D(str(fila.facturado_en_moneda)) == servicio_usd + D("51.43")
    assert D(str(fila.servicio_en_moneda)) == servicio_usd
    assert D(str(fila.tipo_cambio)) == D("17.40")

    rent = r.json()["rentabilidad"]
    assert rent["moneda"] == "MXN"
    assert D(str(rent["facturacion"])) == servicio_mxn + 900
    assert rent["en_otra_moneda"]["moneda"] == "USD"
    assert D(str(rent["en_otra_moneda"]["total"])) == servicio_usd + D("51.43")
    assert rent["en_otra_moneda"]["tipo_cambio"]["tasa"] == "17.4000"


def test_regresado_por_finanzas_toma_el_del_nuevo_visto_bueno(
        cliente, sesion, datos, en_dolares, db):
    servicio, j, cotizacion_id = _eventual(cliente, sesion, datos, offset=1503)
    _poner(cliente, sesion, "17.40")
    _autorizar(cliente, sesion, cotizacion_id)
    _trabajar(cliente, sesion, datos, j)
    cierre_id = _cierre_de(servicio["id"])
    assert cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                        headers=sesion("consultor")).status_code == 200
    r = cliente.post(f"/cierre/{cierre_id}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "Falta el comprobante de la caseta"})
    assert r.status_code == 200, r.text
    # Regresado, ya no hay uno fijo: se ve el que esta puesto.
    _poner(cliente, sesion, "18")
    cmp = _comparativo(cliente, sesion, servicio["id"])
    assert cmp["gastos"]["tipo_cambio"]["tasa"] == "18.0000"
    assert cmp["gastos"]["tipo_cambio"]["fijo"] is False
    assert cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                        headers=sesion("consultor")).status_code == 200
    db.expire_all()
    assert D(str(db.get(m.Cierre, cierre_id).tipo_cambio_gastos)) == D(18)


def test_a_precio_alzado_los_gastos_ya_son_dolares(cliente, sesion, datos,
                                                   en_dolares, db):
    """El monto fijo de gastos va en la moneda de la cotizacion: no se
    convierte ni se fija nada en el visto bueno. Contra lo gastado se mide
    en pesos, al tipo de cambio de la cotizacion."""
    servicio, j, cotizacion_id = _eventual(cliente, sesion, datos,
                                           incluidos=True, offset=1506)
    _poner(cliente, sesion, "17.40")
    assert _autorizar(cliente, sesion, cotizacion_id).status_code == 200
    _trabajar(cliente, sesion, datos, j)
    cmp = _comparativo(cliente, sesion, servicio["id"])
    assert cmp["gastos"]["tipo_cambio"] is None
    assert cmp["gastos"]["cotizado_local"] is None      # sin monto fijo
    cierre_id = _cierre_de(servicio["id"])
    assert cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                        headers=sesion("consultor")).status_code == 200
    db.expire_all()
    assert db.get(m.Cierre, cierre_id).tipo_cambio_gastos is None
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    servicio_mxn = tipo_cambio.a_local(D(str(cmp["ejecutado"]["total"])), "17.40")
    # Van dentro del precio: la comision descuenta su costo, como siempre.
    assert D(str(r.json()["comision_consultor"]["base"])) == servicio_mxn - 900


def test_la_bandeja_no_suma_dolares_con_pesos(db, datos):
    """Dos cierres, uno en cada moneda: dos montos."""
    class Cierre:
        def __init__(self, total, moneda):
            self.total_ejecutado, self.moneda = total, moneda

    viejo = motor_cierre.moneda_del_cierre
    try:
        motor_cierre.moneda_del_cierre = lambda db, c: c.moneda
        montos = facturacion.montos(db, [Cierre("100", m.Moneda.USD),
                                         Cierre("1000", m.Moneda.MXN),
                                         Cierre("50", m.Moneda.USD)])
    finally:
        motor_cierre.moneda_del_cierre = viejo
    assert montos == [{"moneda": "MXN", "monto": D(1000)},
                      {"moneda": "USD", "monto": D(150)}]


# ================================================================ el implantado

@pytest.fixture
def lista_usd(db, datos):
    """La lista de implantados del cliente de las pruebas, en dolares:
    conductor y SUV blindada por dia. Se quita al terminar."""
    cliente = db.get(m.Cliente, datos["cliente_id"])
    base = db.get(m.Tarifario, cliente.tarifario_id)
    full = datos["modalidades"]["full_day"]["id"]
    t = m.Tarifario(nombre="Amazon implantados USD", pais_id=base.pais_id,
                    moneda=m.Moneda.USD, vigencia_desde=date(2026, 1, 1))
    db.add(t)
    db.flush()
    db.add(m.TarifaRecurso(tarifario_id=t.id, modalidad_id=full,
                           perfil_id=datos["perfiles"]["conductor_seguridad"]["id"],
                           precio=CONDUCTOR_USD, origen="propio"))
    db.add(m.TarifaVehiculo(tarifario_id=t.id, modalidad_id=full,
                            categoria_id=datos["categorias"]["suv_blindada"]["id"],
                            precio=SUV_USD, origen="propio"))
    cliente.tarifario_implantado_id = t.id
    db.commit()
    yield t.id
    with db.bind.begin() as con:
        con.execute(text("UPDATE cliente SET tarifario_implantado_id = NULL "
                         "WHERE id = :c"), {"c": datos["cliente_id"]})
        for tabla in ("tarifa_recurso", "tarifa_vehiculo", "tarifa_paquete"):
            con.execute(text(f"DELETE FROM {tabla} WHERE tarifario_id = :t"),
                        {"t": t.id})
        con.execute(text("DELETE FROM tarifario WHERE id = :t"), {"t": t.id})


def _alta(cliente, sesion, datos, **extra):
    """Del 24 al 28 de septiembre de 2029, Juan con la Suburban; sin
    precios: salen de la lista."""
    r = cliente.post("/implantados", headers=sesion("consultor"), json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "fecha_inicio": str(DIAS[0]), "dias_servicio": "lunes_viernes",
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": datos["suburban"]["id"]}],
        "unidades": [datos["suburban"]["id"]], **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _terminos(cliente, sesion, contrato_id):
    r = cliente.get(f"/implantados/contratos/{contrato_id}/terminos",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


def _trabajar_el_mes(cliente, sesion, datos, alta, gasto="900"):
    panel = cliente.get(f"/implantados/{alta['servicio_id']}/mes/2029/9",
                        headers=sesion("consultor")).json()
    jornadas = {date.fromisoformat(d["fecha"]): d["jornada_id"]
                for d in panel["dias"]}
    vid = _viatico(cliente, sesion, datos, jornadas[DIAS[1]])
    for dia in DIAS:
        r = cliente.post(
            f"/operacion/jornadas/{jornadas[dia]}/cerrar-a-mano",
            headers=sesion("central"), json={"justificacion": MOTIVO},
            params={"ahora": datetime.combine(dia, datetime.min.time())
                    .replace(hour=21).isoformat()})
        assert r.status_code == 200, r.text
    _comprobado(vid, gasto)
    from app.db import SessionLocal
    with SessionLocal() as sesion_db:
        return (sesion_db.query(m.Cierre)
                .filter_by(contrato_id=alta["contrato_id"]).first().id)


def _visto_bueno_del_mes(cliente, sesion, cierre_id):
    return cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                        headers=sesion("consultor"),
                        params={"ahora": datetime(2029, 9, 28, 22).isoformat()})


def test_el_mes_en_dolares_de_la_lista_a_la_comision(cliente, sesion, datos,
                                                     lista_usd, db):
    _poner(cliente, sesion, "17")
    alta = _alta(cliente, sesion, datos, viaticos_incluidos=False)
    terminos = _terminos(cliente, sesion, alta["contrato_id"])
    assert terminos["moneda"] == "USD" and terminos["moneda_local"] == "MXN"
    assert terminos["tipo_cambio"]["tasa"] == "17.0000"
    assert terminos["tipo_cambio"]["fijo"] is True
    assert D(str(terminos["precio_dia_personal"])) == CONDUCTOR_USD
    assert terminos["precios_de_la_lista"] is True
    assert terminos["diferencias"] == []

    cierre_id = _trabajar_el_mes(cliente, sesion, datos, alta)
    # Los gastos se facturan al del visto bueno; el mes se queda con el
    # suyo, el de cuando se abrio.
    _poner(cliente, sesion, "17.50")
    r = _visto_bueno_del_mes(cliente, sesion, cierre_id)
    assert r.status_code == 200, r.text
    db.expire_all()
    contrato = db.get(m.ContratoImplantado, alta["contrato_id"])
    assert D(str(contrato.tipo_cambio)) == D(17)
    registro = db.get(m.Cierre, cierre_id)
    assert D(str(registro.tipo_cambio_gastos)) == D("17.50")

    servicio_usd = CONDUCTOR_USD * 5 + SUV_USD * contrato.dias_base
    cuerpo = facturacion.armar(db, registro)
    assert cuerpo["moneda"] == "USD"
    gastos = next(c for c in cuerpo["conceptos"] if c["tipo"] == "viaticos")
    assert gastos["importe"] == "51.43"
    assert gastos["origen"]["tipo_cambio"] == "17.5000"
    assert D(cuerpo["total"]) == servicio_usd + D("51.43")

    r = cliente.get(f"/implantados/contratos/{alta['contrato_id']}/desglose-gastos",
                    params={"idioma": "es"}, headers=sesion("consultor"))
    assert "$51.43 USD" in r.text and "17.50 MXN por USD" in r.text

    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    servicio_mxn = tipo_cambio.a_local(servicio_usd, 17)
    assert D(str(r.json()["comision_consultor"]["base"])) == servicio_mxn
    fila = db.query(m.ComisionConsultor).filter_by(
        contrato_id=alta["contrato_id"]).one()
    assert fila.moneda == m.Moneda.MXN
    assert fila.moneda_facturada == m.Moneda.USD
    assert D(str(fila.servicio_en_moneda)) == servicio_usd
    assert D(str(fila.facturado_en_moneda)) == servicio_usd + D("51.43")
    assert D(str(fila.tipo_cambio)) == D(17)

    # El mes que sigue se abre en dolares, con el que este puesto entonces.
    from app import implantado as motor
    abierto = motor.abrir_siguiente(
        db, db.get(m.Servicio, alta["servicio_id"]), hoy=date(2029, 9, 27))
    octubre = db.get(m.ContratoImplantado, abierto["contrato_id"])
    assert octubre.moneda == m.Moneda.USD
    assert D(str(octubre.tipo_cambio)) == D("17.50")


def test_el_mes_sin_tipo_de_cambio_no_pasa_el_visto_bueno(cliente, sesion,
                                                         datos, lista_usd, db):
    """Se abrio sin ninguno puesto: el visto bueno lo pide, y cuando ya
    hay uno, el mes toma ese."""
    alta = _alta(cliente, sesion, datos, viaticos_incluidos=False)
    terminos = _terminos(cliente, sesion, alta["contrato_id"])
    assert terminos["moneda"] == "USD" and terminos["tipo_cambio"] is None
    cierre_id = _trabajar_el_mes(cliente, sesion, datos, alta)

    r = _visto_bueno_del_mes(cliente, sesion, cierre_id)
    assert r.status_code == 409
    graves = r.json()["detail"]["observaciones"]
    suya = next(o for o in graves if o.get("clave") == "sin_tipo_de_cambio")
    assert suya["datos"]["motivo"] == "sin_tipo_de_cambio"

    _poner(cliente, sesion, "17.25")
    r = _visto_bueno_del_mes(cliente, sesion, cierre_id)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert D(str(db.get(m.ContratoImplantado,
                        alta["contrato_id"]).tipo_cambio)) == D("17.25")


def test_cambiar_el_mes_a_la_lista_en_dolares_borra_lo_que_era_en_pesos(
        cliente, sesion, datos, db):
    """Un mes a mano en pesos que pasa a la lista en dolares: lo que la
    lista no trae --el monto fijo de gastos-- ya no se queda, porque se
    leeria como dolares."""
    from app import implantado_precios
    _poner(cliente, sesion, "17")
    alta = _alta(cliente, sesion, datos, precio_dia_personal="2900",
                 precio_mes_vehiculo="66000", gastos_mes="5000")
    contrato = db.get(m.ContratoImplantado, alta["contrato_id"])
    assert contrato.moneda is None and D(str(contrato.gastos_mes)) == 5000

    cliente_ = db.get(m.Cliente, datos["cliente_id"])
    base = db.get(m.Tarifario, cliente_.tarifario_id)
    full = datos["modalidades"]["full_day"]["id"]
    t = m.Tarifario(nombre="Lista USD", pais_id=base.pais_id,
                    moneda=m.Moneda.USD, vigencia_desde=date(2026, 1, 1))
    db.add(t)
    db.flush()
    db.add(m.TarifaRecurso(tarifario_id=t.id, modalidad_id=full,
                           perfil_id=datos["perfiles"]["conductor_seguridad"]["id"],
                           precio=CONDUCTOR_USD, origen="propio"))
    cliente_.tarifario_implantado_id = t.id
    db.commit()
    try:
        terminos = _terminos(cliente, sesion, alta["contrato_id"])
        assert {"campo": "moneda", "mes": "MXN", "lista": "USD"} in \
            terminos["diferencias"]
        r = cliente.post(
            f"/implantados/contratos/{alta['contrato_id']}/terminos/de-la-lista",
            headers=sesion("consultor"))
        assert r.status_code == 200, r.text
        x = r.json()
        assert x["moneda"] == "USD" and x["tipo_cambio"]["tasa"] == "17.0000"
        assert D(str(x["precio_dia_personal"])) == CONDUCTOR_USD
        # La unidad no esta en la lista y el gasto fijo era en pesos: fuera.
        assert x["precio_mes_vehiculo"] is None and x["gastos_mes"] is None
        assert "moneda" not in {d["campo"] for d in x["diferencias"]}
        db.expire_all()
        contrato = db.get(m.ContratoImplantado, alta["contrato_id"])
        assert not implantado_precios.sigue_la_lista(
            contrato, implantado_precios.de_la_lista(db, contrato))
    finally:
        with db.bind.begin() as con:
            con.execute(text("UPDATE cliente SET tarifario_implantado_id = NULL "
                             "WHERE id = :c"), {"c": datos["cliente_id"]})
            con.execute(text("DELETE FROM tarifa_recurso WHERE tarifario_id = :t"),
                        {"t": t.id})
            con.execute(text("DELETE FROM tarifario WHERE id = :t"), {"t": t.id})

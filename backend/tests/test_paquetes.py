# -*- coding: utf-8 -*-
"""Los paquetes conductor + unidad (seccion 79).

El dia que el equipo lleva ese rol con esa unidad, y la lista del cliente
pacta el paquete, se cobra el paquete: un solo renglon, en la cotizacion,
en el cierre y en la factura. Lo que no hace pareja se cobra suelto.

Y la regla de Salvador del 1 de octubre (seccion 115): si los paquetes de
la lista traen los gastos --«Todo incluido», como PE · General Mexico o
HASBRO--, el paquete solo va con los gastos dentro del precio. Con monto
fijo o por comprobar, el conductor y la unidad van a su precio unitario y
los gastos aparte, segun su modo.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app import cierre as motor_cierre
from app import cotizacion as cot
from app import facturacion
from app import models as m
from ayudas import (asignar, configurar_origen, crear_servicio,
                    ejecutar_jornada, jornada, manana)

PAQUETE = Decimal("11200")        # conductor + SUV blindada, dia completo


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


def _poner_paquete(db, datos, origen="propio"):
    """El paquete conductor + SUV blindada en dia completo, en el tarifario
    del cliente de las pruebas. `origen` es de donde lo saco la lectura de
    Odoo: "propio" si la lista lo pacta."""
    tarifario_id = db.get(m.Cliente, datos["cliente_id"]).tarifario_id
    db.add(m.TarifaPaquete(
        tarifario_id=tarifario_id,
        perfil_id=datos["perfiles"]["conductor_seguridad"]["id"],
        categoria_id=datos["categorias"]["suv_blindada"]["id"],
        modalidad_id=datos["modalidades"]["full_day"]["id"],
        precio=PAQUETE, origen=origen))
    db.commit()
    return tarifario_id


def _quitar_paquetes(db, tarifario_id):
    with db.bind.begin() as con:
        con.execute(text("DELETE FROM tarifa_paquete WHERE tarifario_id = :t"),
                    {"t": tarifario_id})
        con.execute(text("UPDATE tarifario SET paquetes_con_viaticos = false "
                         "WHERE id = :t"), {"t": tarifario_id})


@pytest.fixture
def paquete(db, datos):
    """El tarifario del cliente de las pruebas, con el paquete pactado. Se
    quita al terminar."""
    tarifario_id = _poner_paquete(db, datos)
    yield tarifario_id
    _quitar_paquetes(db, tarifario_id)


def _trabajado(cliente, sesion, datos, offset, dias=2, horas_extra=0,
               agente=False, incluidos=False):
    """Servicio cotizado --conductor y SUV blindada cada dia, y un agente
    si se pide-- y trabajado con Juan y la Suburban. Con gastos netos, o
    dentro del precio con `incluidos`."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"])
         for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    lineas = []
    for j in servicio["equipos"][0]["jornadas"]:
        lineas.append({"fecha": j["fecha"], "tipo": "recurso",
                       "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"]})
        lineas.append({"fecha": j["fecha"], "tipo": "vehiculo",
                       "categoria_id": datos["categorias"]["suv_blindada"]["id"]})
        if agente:
            lineas.append({"fecha": j["fecha"], "tipo": "recurso",
                           "perfil_id": datos["perfiles"]["agente_seguridad"]["id"]})
    r = cliente.post("/cotizaciones", headers=h,
                     json={"servicio_id": servicio["id"], "lineas": lineas,
                           "viaticos_incluidos": incluidos})
    assert r.status_code == 201, r.text
    cliente.post(f"/cotizaciones/{r.json()['cotizacion_id']}/autorizar",
                 json={"autorizada_por": "Cliente de prueba"}, headers=h)
    for idx, j in enumerate(servicio["equipos"][0]["jornadas"]):
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        if agente:
            asignar(cliente, h, j["id"],
                    persona_id=datos["personal"]["Miguel Torres"]["id"],
                    rol="agente_seguridad")
        configurar_origen(cliente, h, j["id"])
        ejecutar_jornada(cliente, sesion("juan"), j,
                         horas_extra=horas_extra if idx == dias - 1 else 0)
    return servicio


def comparativo(cliente, sesion, servicio):
    r = cliente.get(f"/cierre/servicio/{servicio['id']}/comparativo",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


# ================================================================ la regla

class _Paquete:
    def __init__(self, perfil_id, categoria_id):
        self.perfil_id, self.categoria_id = perfil_id, categoria_id


def test_se_empareja_lo_que_va_junto():
    roles, unidades = {1: 2, 2: 1}, {10: 1, 20: 1}
    pares = cot.emparejar(roles, unidades, [_Paquete(1, 10), _Paquete(1, 20),
                                            _Paquete(2, 30)])
    assert [(p.perfil_id, p.categoria_id, n) for p, n in pares] == [
        (1, 10, 1), (1, 20, 1)]
    # Lo que no hizo pareja se cobra suelto.
    assert roles == {1: 0, 2: 1} and unidades == {10: 0, 20: 0}


# ================================================================ cotizar y cerrar

def test_el_paquete_se_cotiza_se_cierra_y_se_factura(cliente, sesion, datos,
                                                     paquete, db):
    servicio = _trabajado(cliente, sesion, datos, offset=420, horas_extra=3)

    cotizaciones = cliente.get(f"/cotizaciones/servicio/{servicio['id']}",
                               headers=sesion("consultor")).json()
    lineas = cotizaciones[-1]["lineas"]
    assert [l["tipo"] for l in lineas] == ["paquete", "paquete"]
    assert lineas[0]["descripcion"] == "Conductor de seguridad + SUV Blindada"
    assert float(cotizaciones[-1]["total"]) == 2 * float(PAQUETE)

    cmp = comparativo(cliente, sesion, servicio)
    # Lo cotizado y lo ejecutado se comparan igual: solo las horas extra.
    assert {d["tipo"] for d in cmp["desviaciones"]
            if d["tipo"] not in ("viatico_sin_comprobar", "viatico_no_cerrado")} == {
        "horas_extra"}
    renglones = cmp["ejecutado"]["renglones"]
    assert [(r["tipo"], r["cantidad"], float(r["precio"]), float(r["importe"]))
            for r in renglones] == [("paquete", 2, 11200.0, 22400.0),
                                    ("horas_extra", 3, 320.0, 960.0)]
    assert renglones[0]["modalidad"] == "full_day"
    assert renglones[1]["descripcion"] == "Conductor de seguridad"
    assert float(cmp["ejecutado"]["total"]) == 22400 + 960

    # La factura lleva el paquete, un renglon por dia.
    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                          headers=sesion("consultor")).json()
    cuerpo = facturacion.armar(db, db.get(m.Cierre, cierre["cierre_id"]))
    tipos = [c["tipo"] for c in cuerpo["conceptos"]]
    assert tipos == ["paquete", "paquete"]
    assert Decimal(cuerpo["total"]) == Decimal("23360")


def test_lo_que_no_hace_pareja_se_cobra_suelto(cliente, sesion, datos, paquete):
    servicio = _trabajado(cliente, sesion, datos, offset=430, dias=1, agente=True)
    cotizaciones = cliente.get(f"/cotizaciones/servicio/{servicio['id']}",
                               headers=sesion("consultor")).json()
    assert [l["tipo"] for l in cotizaciones[-1]["lineas"]] == ["paquete", "recurso"]

    cmp = comparativo(cliente, sesion, servicio)
    renglones = {r["tipo"]: r for r in cmp["ejecutado"]["renglones"]}
    assert renglones["paquete"]["cantidad"] == 1
    assert renglones["recurso"]["descripcion"] == "Agente de seguridad"
    assert "vehiculo" not in renglones
    assert not [d for d in cmp["desviaciones"] if d["tipo"] in (
        "recurso_no_cotizado", "dias_de_menos", "dias_de_mas")]


def test_sin_paquete_en_la_lista_se_cobra_como_siempre(cliente, sesion, datos):
    servicio = _trabajado(cliente, sesion, datos, offset=440, dias=1)
    cmp = comparativo(cliente, sesion, servicio)
    assert sorted(r["tipo"] for r in cmp["ejecutado"]["renglones"]) == [
        "recurso", "vehiculo"]


def test_el_paquete_que_la_lista_no_pacta_no_cuenta(cliente, sesion, datos, db):
    """La lectura de Odoo le pone a toda lista todos los paquetes: si la
    lista no lo pacta, con el precio de la general o el «Precio de venta»
    del producto. Ese no se cobra --Control Risks compra conductor y
    unidad por separado-- ni se ve en el tarifario del cliente."""
    tarifario_id = _poner_paquete(db, datos, origen="precio_venta")
    try:
        servicio = _trabajado(cliente, sesion, datos, offset=470, dias=1)
        cotizaciones = cliente.get(f"/cotizaciones/servicio/{servicio['id']}",
                                   headers=sesion("consultor")).json()
        assert sorted(l["tipo"] for l in cotizaciones[-1]["lineas"]) == [
            "recurso", "vehiculo"]
        cmp = comparativo(cliente, sesion, servicio)
        assert sorted(r["tipo"] for r in cmp["ejecutado"]["renglones"]) == [
            "recurso", "vehiculo"]
        visto = cliente.get(f"/tarifarios/cliente/{datos['cliente_id']}",
                            headers=sesion("finanzas")).json()
        assert visto["tarifario"]["paquetes"] == []
        # Y cotizarlo directo tampoco: la lista no lo pacta.
        h = sesion("consultor")
        otro = crear_servicio(
            cliente, h, datos,
            [jornada(manana(471), datos["modalidades"]["full_day"]["id"])],
            consultor_id=datos["personal"]["Ana Solis"]["id"])
        r = cliente.post("/cotizaciones", headers=h, json={
            "servicio_id": otro["id"],
            "lineas": [{"fecha": otro["equipos"][0]["jornadas"][0]["fecha"],
                        "tipo": "paquete",
                        "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"],
                        "categoria_id": datos["categorias"]["suv_blindada"]["id"]}]})
        assert r.status_code == 400
        assert "no pacta" in r.text
    finally:
        _quitar_paquetes(db, tarifario_id)


def test_un_paquete_que_la_lista_no_tiene_se_dice(cliente, sesion, datos, paquete):
    """Un paquete sin su precio en la lista se dice, como un rol sin precio."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos, [jornada(manana(450), datos["modalidades"]["medio_dia"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    r = cliente.post("/cotizaciones", headers=h, json={
        "servicio_id": servicio["id"],
        "lineas": [{"fecha": servicio["equipos"][0]["jornadas"][0]["fecha"],
                    "tipo": "paquete",
                    "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"],
                    "categoria_id": datos["categorias"]["suv_blindada"]["id"]}]})
    assert r.status_code == 400
    assert "paquete" in r.text


# ================================================================ los viaticos

def _viaticos(db, servicio, monto):
    """Juan comprobo `monto` cada dia (sin pasar por el deposito: aqui solo
    importa cuanto se le factura al cliente)."""
    for j in servicio["equipos"][0]["jornadas"]:
        db.add(m.AsignacionViatico(
            jornada_id=j["id"], persona_id=db.query(m.Persona).filter_by(
                nombre="Juan Ramirez").one().id,
            escenario=m.EscenarioViatico.FULL_DAY_LOCAL, moneda=m.Moneda.MXN,
            monto_total=monto, monto_comprobado=monto))
    db.commit()


def _con_viaticos(cliente, sesion, tarifario_id):
    """Finanzas marca que los paquetes de la lista traen los gastos."""
    r = cliente.patch(f"/tarifarios/{tarifario_id}/viaticos",
                      json={"incluidos": True}, headers=sesion("finanzas"))
    assert r.status_code == 200, r.text


def test_con_gastos_netos_el_paquete_todo_incluido_no_va(
        cliente, sesion, datos, paquete, db):
    """Antes (seccion 79) se cobraba el paquete y los viaticos de quien iba
    en el no se facturaban. Desde la seccion 115 ese paquete solo va con
    los gastos dentro: con gastos netos, conductor y unidad a su precio
    unitario, y todos los viaticos comprobados a la factura."""
    _con_viaticos(cliente, sesion, paquete)
    servicio = _trabajado(cliente, sesion, datos, offset=460)
    _viaticos(db, servicio, Decimal("500"))

    cotizaciones = cliente.get(f"/cotizaciones/servicio/{servicio['id']}",
                               headers=sesion("consultor")).json()
    assert sorted(l["tipo"] for l in cotizaciones[-1]["lineas"]) == [
        "recurso", "recurso", "vehiculo", "vehiculo"]
    # El cierre cobra igual que como se cotizo: lo cotizado y lo cobrado
    # se comparan igual.
    cmp = comparativo(cliente, sesion, servicio)
    assert sorted(r["tipo"] for r in cmp["ejecutado"]["renglones"]) == [
        "recurso", "vehiculo"]
    assert not [d for d in cmp["desviaciones"] if d["tipo"] in (
        "recurso_no_cotizado", "dias_de_menos", "dias_de_mas")]
    assert float(cmp["gastos"]["comprobado"]) == 1000
    assert float(cmp["gastos"]["en_paquete"]) == 0
    assert float(cmp["gastos"]["a_facturar"]) == 1000
    db.expire_all()
    cotizacion = cot.vigente(db, servicio["id"])
    assert motor_cierre.viaticos_por_cobrar(db, servicio["id"], cotizacion) == 1000
    # Y van todos en el desglose que se le manda al cliente.
    facturables = motor_cierre.viaticos_facturables(
        db, db.get(m.Servicio, servicio["id"]), cotizacion.tarifario_id)
    assert len(facturables) == 2


def test_con_los_gastos_dentro_va_el_paquete_todo_incluido(
        cliente, sesion, datos, paquete, db):
    _con_viaticos(cliente, sesion, paquete)
    servicio = _trabajado(cliente, sesion, datos, offset=465, incluidos=True)
    cotizaciones = cliente.get(f"/cotizaciones/servicio/{servicio['id']}",
                               headers=sesion("consultor")).json()
    assert [l["tipo"] for l in cotizaciones[-1]["lineas"]] == [
        "paquete", "paquete"]
    cmp = comparativo(cliente, sesion, servicio)
    assert [r["tipo"] for r in cmp["ejecutado"]["renglones"]] == ["paquete"]
    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                          headers=sesion("consultor")).json()
    cuerpo = facturacion.armar(db, db.get(m.Cierre, cierre["cierre_id"]))
    assert [c["tipo"] for c in cuerpo["conceptos"]] == ["paquete", "paquete"]


def test_la_vista_previa_con_monto_fijo_no_usa_el_paquete(
        cliente, sesion, datos, paquete):
    _con_viaticos(cliente, sesion, paquete)
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(468), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    fecha = servicio["equipos"][0]["jornadas"][0]["fecha"]
    lleva = [{"fecha": fecha, "tipo": "recurso",
              "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"]},
             {"fecha": fecha, "tipo": "vehiculo",
              "categoria_id": datos["categorias"]["suv_blindada"]["id"]}]
    vistas = {}
    for gastos, monto in (("dentro", None), ("fijo", "1500"),
                          ("comprobar", None)):
        r = cliente.post("/cotizaciones/vista-previa", headers=h, json={
            "servicio_id": servicio["id"], "lineas": lleva,
            "gastos": gastos, "monto_gastos": monto})
        assert r.status_code == 200, r.text
        vistas[gastos] = [l["tipo"] for l in r.json()["lineas"]]
    assert vistas == {"dentro": ["paquete"],
                      "fijo": ["recurso", "vehiculo", "viaticos"],
                      "comprobar": ["recurso", "vehiculo"]}


def test_la_lista_cuyos_paquetes_no_traen_gastos_los_junta_siempre(
        cliente, sesion, datos, paquete):
    """Sin la marca de finanzas el paquete no trae gastos: va en cualquier
    modo, como siempre (los de arriba en netos lo prueban tambien)."""
    servicio = _trabajado(cliente, sesion, datos, offset=475, dias=1)
    cotizaciones = cliente.get(f"/cotizaciones/servicio/{servicio['id']}",
                               headers=sesion("consultor")).json()
    assert [l["tipo"] for l in cotizaciones[-1]["lineas"]] == ["paquete"]


@pytest.fixture
def todo_incluido(db, datos):
    """Una lista como PE · General Mexico, con las cifras de Salvador: el
    conductor a $3,255, la CUV a $3,675 y el paquete conductor + CUV
    «Todo incluido» a $8,430, dia completo, con los gastos dentro."""
    completo = datos["modalidades"]["full_day"]["id"]
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    cuv = datos["categorias"]["cuv"]["id"]
    tarifario = m.Tarifario(nombre="PE · General México (prueba)",
                            pais_id=datos["mx"]["id"], moneda=m.Moneda.MXN,
                            vigencia_desde=date(2026, 1, 1),
                            paquetes_con_viaticos=True)
    db.add(tarifario)
    db.flush()
    db.add(m.TarifaRecurso(tarifario_id=tarifario.id, perfil_id=conductor,
                           modalidad_id=completo, precio=Decimal("3255"),
                           precio_hora_extra=Decimal("270")))
    db.add(m.TarifaVehiculo(tarifario_id=tarifario.id, categoria_id=cuv,
                            modalidad_id=completo, precio=Decimal("3675")))
    db.add(m.TarifaPaquete(tarifario_id=tarifario.id, perfil_id=conductor,
                           categoria_id=cuv, modalidad_id=completo,
                           precio=Decimal("8430"), origen="propio"))
    cliente = db.get(m.Cliente, datos["cliente_id"])
    antes = cliente.tarifario_id
    cliente.tarifario_id = tarifario.id
    db.commit()
    yield tarifario
    cliente = db.get(m.Cliente, datos["cliente_id"])
    cliente.tarifario_id = antes
    db.query(m.Cotizacion).filter_by(tarifario_id=tarifario.id).update(
        {"tarifario_id": None})
    db.commit()
    db.delete(db.get(m.Tarifario, tarifario.id))
    db.commit()


@pytest.mark.parametrize("gastos,monto,esperado,servicio", [
    ("dentro", None, [("paquete", 8430.0)], 8430),
    ("fijo", "1500", [("recurso", 3255.0), ("vehiculo", 3675.0),
                      ("viaticos", 1500.0)], 6930),
    ("comprobar", None, [("recurso", 3255.0), ("vehiculo", 3675.0)], 6930),
])
def test_pe_general_mexico_conductor_y_cuv(cliente, sesion, datos, todo_incluido,
                                           gastos, monto, esperado, servicio):
    """La prueba de Salvador, en Cotizaciones: gastos incluidos, el paquete
    de $8,430; monto fijo o por comprobar, $3,255 + $3,675 = $6,930 y los
    gastos aparte."""
    r = cliente.post("/cotizaciones/eventual/precios", headers=sesion("consultor"),
                     json={"cliente_id": datos["cliente_id"], "gastos": gastos,
                           "monto_gastos": monto, "equipos": [{
                               "plaza_id": datos["cdmx"]["id"],
                               "lleva": [{"tipo": "recurso", "cantidad": 1,
                                          "id": datos["perfiles"]["conductor_seguridad"]["id"]},
                                         {"tipo": "vehiculo", "cantidad": 1,
                                          "id": datos["categorias"]["cuv"]["id"]}],
                               "dias": [{"fecha": str(manana(480)),
                                         "modalidad_id": datos["modalidades"]["full_day"]["id"]}]}]})
    assert r.status_code == 200, r.text
    lineas = r.json()["lineas"]
    assert [(l["tipo"], l["precio"]) for l in lineas] == esperado
    assert sum(l["importe"] for l in lineas if l["tipo"] != "viaticos") == servicio


def test_solo_finanzas_marca_los_viaticos_del_paquete(cliente, sesion, datos, paquete):
    assert cliente.patch(f"/tarifarios/{paquete}/viaticos", json={"incluidos": True},
                         headers=sesion("consultor")).status_code == 403
    visto = cliente.get(f"/tarifarios/cliente/{datos['cliente_id']}",
                        headers=sesion("consultor")).json()
    assert visto["puede_editar"] is False
    assert visto["tarifario"]["paquetes_con_viaticos"] is False
    assert visto["tarifario"]["paquetes"][0]["precio"] == float(PAQUETE)
    assert cliente.get(f"/tarifarios/cliente/{datos['cliente_id']}",
                       headers=sesion("finanzas")).json()["puede_editar"] is True

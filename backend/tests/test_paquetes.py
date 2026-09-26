# -*- coding: utf-8 -*-
"""Los paquetes conductor + unidad (seccion 79).

El dia que el equipo lleva ese rol con esa unidad, y la lista del cliente
pacta el paquete, se cobra el paquete: un solo renglon, en la cotizacion,
en el cierre y en la factura. Lo que no hace pareja se cobra suelto. Y si
la lista dice que sus paquetes traen los viaticos --HASBRO--, los de quien
fue en el paquete no se facturan aparte.
"""
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
               agente=False):
    """Servicio cotizado --conductor y SUV blindada cada dia, y un agente
    si se pide-- y trabajado con Juan y la Suburban."""
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
                           "viaticos_incluidos": False})
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


def test_los_viaticos_van_dentro_del_paquete_si_la_lista_lo_dice(
        cliente, sesion, datos, paquete, db):
    servicio = _trabajado(cliente, sesion, datos, offset=460)
    _viaticos(db, servicio, Decimal("500"))

    # Sin marcar: gastos netos, se facturan los mil.
    cmp = comparativo(cliente, sesion, servicio)
    assert float(cmp["gastos"]["a_facturar"]) == 1000
    assert float(cmp["gastos"]["en_paquete"]) == 0

    # HASBRO: sus paquetes traen los viaticos del dia.
    r = cliente.patch(f"/tarifarios/{paquete}/viaticos", json={"incluidos": True},
                      headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    cmp = comparativo(cliente, sesion, servicio)
    assert float(cmp["gastos"]["comprobado"]) == 1000
    assert float(cmp["gastos"]["en_paquete"]) == 1000
    assert float(cmp["gastos"]["a_facturar"]) == 0
    db.expire_all()
    cotizacion = cot.vigente(db, servicio["id"])
    assert motor_cierre.viaticos_por_cobrar(db, servicio["id"], cotizacion) == 0
    # Y tampoco van en el desglose que se le manda al cliente.
    facturables = motor_cierre.viaticos_facturables(
        db, db.get(m.Servicio, servicio["id"]), cotizacion.tarifario_id)
    assert facturables == []


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

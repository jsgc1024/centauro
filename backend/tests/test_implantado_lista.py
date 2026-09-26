# -*- coding: utf-8 -*-
"""Los precios del implantado, de su lista de implantados (seccion 80).

Al abrir el mes, los terminos salen de la lista de implantados del
cliente con la plantilla: cada quien por su rol, el conductor con su
unidad en paquete si la lista lo pacta, cada unidad por los dias de
servicio del mes y la hora extra del equipo. Sin lista de implantados,
de la de siempre. Lo que se pone a mano se queda y se dice; el mes que
sigue a uno que va con la lista la vuelve a tomar.

Todo pasa en 2031, que ninguna otra prueba usa: cada prueba en su mes.
"""
import calendar
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app import implantado as motor
from app import models as m

CONDUCTOR = Decimal("2131.50")
AGENTE = Decimal("2667.00")
SUV = Decimal("10920.00")
MINIVAN = Decimal("2047.50")
PAQUETE = Decimal("3928.00")
EXTRA = Decimal("270.00")


def _habiles(anio, mes):
    ultimo = calendar.monthrange(anio, mes)[1]
    return sum(1 for d in range(1, ultimo + 1)
               if date(anio, mes, d).weekday() < 5)


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture
def lista(db, datos):
    """Arma la lista de implantados del cliente de las pruebas y la quita
    al terminar. Trae conductor, agente, la SUV blindada y la Minivan por
    dia, con su hora extra; y un paquete conductor + SUV blindada que la
    lista NO pacta --con el «Precio de venta», como los pone la lectura de
    Odoo a toda lista--."""
    hechas = []

    def armar(agente=True, paquete_minivan=False):
        cliente = db.get(m.Cliente, datos["cliente_id"])
        base = db.get(m.Tarifario, cliente.tarifario_id)
        full = datos["modalidades"]["full_day"]["id"]
        perfiles, categorias = datos["perfiles"], datos["categorias"]
        t = m.Tarifario(nombre="Implantados de prueba", pais_id=base.pais_id,
                        moneda=base.moneda, vigencia_desde=date(2026, 1, 1))
        db.add(t)
        db.flush()
        db.add(m.TarifaRecurso(tarifario_id=t.id, modalidad_id=full,
                               perfil_id=perfiles["conductor_seguridad"]["id"],
                               precio=CONDUCTOR, precio_hora_extra=EXTRA,
                               origen="propio"))
        if agente:
            db.add(m.TarifaRecurso(tarifario_id=t.id, modalidad_id=full,
                                   perfil_id=perfiles["agente_seguridad"]["id"],
                                   precio=AGENTE, precio_hora_extra=EXTRA,
                                   origen="propio"))
        for codigo, precio in (("suv_blindada", SUV), ("minivan", MINIVAN)):
            db.add(m.TarifaVehiculo(tarifario_id=t.id, modalidad_id=full,
                                    categoria_id=categorias[codigo]["id"],
                                    precio=precio, origen="propio"))
        db.add(m.TarifaPaquete(tarifario_id=t.id, modalidad_id=full,
                               perfil_id=perfiles["conductor_seguridad"]["id"],
                               categoria_id=categorias["suv_blindada"]["id"],
                               precio=Decimal("9999"), origen="precio_venta"))
        if paquete_minivan:
            db.add(m.TarifaPaquete(tarifario_id=t.id, modalidad_id=full,
                                   perfil_id=perfiles["conductor_seguridad"]["id"],
                                   categoria_id=categorias["minivan"]["id"],
                                   precio=PAQUETE, origen="propio"))
        cliente.tarifario_implantado_id = t.id
        db.commit()
        hechas.append(t.id)
        return t.id

    yield armar
    with db.bind.begin() as con:
        con.execute(text("UPDATE cliente SET tarifario_implantado_id = NULL "
                         "WHERE id = :c"), {"c": datos["cliente_id"]})
        for t in hechas:
            for tabla in ("tarifa_recurso", "tarifa_vehiculo", "tarifa_paquete"):
                con.execute(text(f"DELETE FROM {tabla} WHERE tarifario_id = :t"),
                            {"t": t})
            con.execute(text("DELETE FROM tarifario WHERE id = :t"), {"t": t})


def _unidad(datos, codigo):
    categoria = datos["categorias"][codigo]["id"]
    return next(v for v in datos["vehiculos"] if v["categoria_id"] == categoria
                and v["plaza_id"] == datos["cdmx"]["id"])


def _alta(cliente, sesion, datos, inicio, personal, unidades, turno="natural",
          **precios):
    """Un implantado de lunes a viernes desde `inicio`, sin precios salvo
    los que se digan: como lo da de alta la consola."""
    r = cliente.post("/implantados", headers=sesion("consultor"), json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "fecha_inicio": str(inicio), "dias_servicio": "lunes_viernes",
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "personal": personal, "unidades": unidades,
        "acuerdo": {"turno": turno}, **precios})
    assert r.status_code == 201, r.text
    return r.json()


def _equipo(datos, suv):
    """Juan maneja la SUV blindada y Miguel va con el de agente."""
    return [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],
             "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
             "vehiculo_id": suv["id"]},
            {"persona_id": datos["personal"]["Miguel Torres"]["id"],
             "rol_id": datos["perfiles"]["agente_seguridad"]["id"],
             "vehiculo_id": suv["id"]}]


def _terminos(cliente, sesion, contrato_id):
    r = cliente.get(f"/implantados/contratos/{contrato_id}/terminos",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


def _revision(cliente, sesion, contrato_id):
    r = cliente.get(f"/implantados/contratos/{contrato_id}/cierre/revision",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return {o.get("clave"): o for o in r.json()["observaciones"]}


# ================================================================ al abrir

def test_el_primer_mes_sale_de_la_lista_de_implantados(cliente, sesion, datos,
                                                        lista):
    lista()
    suv = _unidad(datos, "suv_blindada")
    alta = _alta(cliente, sesion, datos, date(2031, 4, 1), _equipo(datos, suv),
                 [suv["id"]])
    x = _terminos(cliente, sesion, alta["contrato_id"])
    dias = _habiles(2031, 4)
    assert x["esquema"] == "por_dia" and x["precios_de_la_lista"] is True
    assert float(x["precio_dia_personal"]) == float(CONDUCTOR + AGENTE)
    assert float(x["precio_dia_adicional"]) == float(CONDUCTOR + AGENTE)
    assert float(x["precio_mes_vehiculo"]) == float(SUV * dias)
    assert float(x["precio_hora_extra"]) == float(EXTRA * 2)
    d = x["de_la_lista"]
    assert d["lista"]["nombre"] == "Implantados de prueba"
    assert d["lista"]["de_implantados"] is True
    assert d["dias_base"] == dias and d["faltan"] == []
    # El paquete conductor + SUV que la lista no pacta no cuenta.
    assert [r["tipo"] for r in d["renglones"]] == ["recurso", "recurso", "unidad"]
    assert x["diferencias"] == []
    assert "precios_lista" not in _revision(cliente, sesion, alta["contrato_id"])


def test_el_conductor_con_su_unidad_va_en_paquete_si_la_lista_lo_pacta(
        cliente, sesion, datos, lista):
    lista(paquete_minivan=True)
    minivan = _unidad(datos, "minivan")
    alta = _alta(cliente, sesion, datos, date(2031, 5, 1), [{
        "persona_id": datos["personal"]["Luis Mendoza"]["id"],
        "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
        "vehiculo_id": minivan["id"]}], [minivan["id"]])
    x = _terminos(cliente, sesion, alta["contrato_id"])
    # Un solo precio por dia, y la Minivan no se cobra aparte.
    assert float(x["precio_dia_personal"]) == float(PAQUETE)
    assert float(x["precio_mes_vehiculo"]) == 0
    assert float(x["precio_hora_extra"]) == float(EXTRA)
    assert [r["tipo"] for r in x["de_la_lista"]["renglones"]] == [
        "paquete", "unidad_en_paquete"]
    assert x["precios_de_la_lista"] is True


def test_sin_lista_de_implantados_sale_de_la_de_siempre(cliente, sesion, datos,
                                                         db):
    suv = _unidad(datos, "suv_blindada")
    alta = _alta(cliente, sesion, datos, date(2031, 7, 1), _equipo(datos, suv),
                 [suv["id"]])
    tarifario_id = db.get(m.Cliente, datos["cliente_id"]).tarifario_id
    full = datos["modalidades"]["full_day"]["id"]

    def precio(perfil):
        return (db.query(m.TarifaRecurso)
                .filter_by(tarifario_id=tarifario_id, modalidad_id=full,
                           perfil_id=datos["perfiles"][perfil]["id"]).one().precio)

    unidad = (db.query(m.TarifaVehiculo)
              .filter_by(tarifario_id=tarifario_id, modalidad_id=full,
                         categoria_id=suv["categoria_id"]).one().precio)
    x = _terminos(cliente, sesion, alta["contrato_id"])
    assert x["de_la_lista"]["lista"]["de_implantados"] is False
    assert x["de_la_lista"]["lista"]["id"] == tarifario_id
    assert float(x["precio_dia_personal"]) == float(
        precio("conductor_seguridad") + precio("agente_seguridad"))
    assert float(x["precio_mes_vehiculo"]) == float(unidad * _habiles(2031, 7))


def test_los_precios_escritos_en_el_alta_mandan(cliente, sesion, datos, lista):
    lista()
    suv = _unidad(datos, "suv_blindada")
    alta = _alta(cliente, sesion, datos, date(2031, 1, 1), _equipo(datos, suv),
                 [suv["id"]], precio_dia_personal="5000",
                 precio_dia_adicional="5000", precio_mes_vehiculo="200000")
    x = _terminos(cliente, sesion, alta["contrato_id"])
    assert float(x["precio_dia_personal"]) == 5000
    assert x["precios_de_la_lista"] is False
    assert {d["campo"] for d in x["diferencias"]} == {
        "precio_dia_personal", "precio_dia_adicional", "precio_mes_vehiculo",
        "precio_hora_extra"}


# ================================================================ a mano

def test_un_precio_a_mano_se_queda_y_se_dice(cliente, sesion, datos, lista):
    lista()
    suv = _unidad(datos, "suv_blindada")
    alta = _alta(cliente, sesion, datos, date(2031, 12, 1), _equipo(datos, suv),
                 [suv["id"]])
    contrato_id = alta["contrato_id"]
    antes = _terminos(cliente, sesion, contrato_id)
    r = cliente.put(f"/implantados/contratos/{contrato_id}/terminos",
                    headers=sesion("consultor"), json={
                        "esquema": "por_dia", "precio_dia_personal": 5000,
                        "precio_dia_adicional": 5000,
                        "precio_mes_vehiculo": antes["precio_mes_vehiculo"],
                        "precio_hora_extra": antes["precio_hora_extra"],
                        "viaticos_incluidos": True})
    assert r.status_code == 200, r.text
    x = r.json()
    assert x["precios_de_la_lista"] is False
    assert [(d["campo"], d["mes"], d["lista"]) for d in x["diferencias"]] == [
        ("precio_dia_personal", 5000.0, float(CONDUCTOR + AGENTE)),
        ("precio_dia_adicional", 5000.0, float(CONDUCTOR + AGENTE))]
    # El visto bueno del mes se lo dice a finanzas, sin frenarlo.
    aviso = _revision(cliente, sesion, contrato_id)["precios_lista"]
    assert aviso["nivel"] == "revisar"
    assert aviso["datos"]["lista"] == "Implantados de prueba"

    # «Usar los de la lista»: el mes vuelve a la lista.
    r = cliente.post(f"/implantados/contratos/{contrato_id}/terminos/de-la-lista",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    x = r.json()
    assert float(x["precio_dia_personal"]) == float(CONDUCTOR + AGENTE)
    assert x["precios_de_la_lista"] is True and x["diferencias"] == []
    assert "precios_lista" not in _revision(cliente, sesion, contrato_id)


def test_el_mes_que_sigue_vuelve_a_tomar_la_lista(cliente, sesion, datos, db,
                                                  lista):
    """El que iba con la lista la vuelve a tomar, con los dias de servicio
    del mes nuevo y con lo que la lista diga hoy; el puesto a mano se
    copia."""
    t = lista()
    suv = _unidad(datos, "suv_blindada")
    alta = _alta(cliente, sesion, datos, date(2031, 8, 1), _equipo(datos, suv),
                 [suv["id"]])
    # En Odoo sube el conductor.
    (db.query(m.TarifaRecurso)
     .filter_by(tarifario_id=t, perfil_id=datos["perfiles"]["conductor_seguridad"]["id"])
     .update({"precio": Decimal("2500")}))
    db.commit()
    servicio = db.get(m.Servicio, alta["servicio_id"])
    nuevo = motor.abrir_siguiente(db, servicio, hoy=date(2031, 8, 20))
    x = _terminos(cliente, sesion, nuevo["contrato_id"])
    assert x["periodo"] == "09/2031" and x["precios_de_la_lista"] is True
    assert float(x["precio_dia_personal"]) == float(Decimal("2500") + AGENTE)
    assert float(x["precio_mes_vehiculo"]) == float(SUV * _habiles(2031, 9))

    # Septiembre a mano: octubre lo copia, como siempre.
    r = cliente.put(f"/implantados/contratos/{nuevo['contrato_id']}/terminos",
                    headers=sesion("consultor"), json={
                        "esquema": "por_dia", "precio_dia_personal": 4000,
                        "precio_dia_adicional": 4000,
                        "precio_mes_vehiculo": 150000,
                        "precio_hora_extra": 300, "viaticos_incluidos": True})
    assert r.status_code == 200, r.text
    db.expire_all()
    otro = motor.abrir_siguiente(db, servicio, hoy=date(2031, 9, 20))
    x = _terminos(cliente, sesion, otro["contrato_id"])
    assert x["periodo"] == "10/2031" and x["precios_de_la_lista"] is False
    assert float(x["precio_dia_personal"]) == 4000
    assert float(x["precio_mes_vehiculo"]) == 150000


def test_mover_el_arranque_cambia_la_unidad_del_mes(cliente, sesion, datos,
                                                   lista):
    """La unidad va por los dias de servicio del mes: si el arranque se
    mueve, el mes que va con la lista la vuelve a contar."""
    lista()
    suv = _unidad(datos, "suv_blindada")
    alta = _alta(cliente, sesion, datos, date(2031, 2, 3), _equipo(datos, suv),
                 [suv["id"]])
    r = cliente.put(f"/implantados/{alta['servicio_id']}/acuerdo",
                    headers=sesion("consultor"),
                    json={"fecha_inicio": "2031-02-17", "dias_servicio": "lunes_viernes"})
    assert r.status_code == 200, r.text
    dias = r.json()["contrato_ajustado"]["dias_base"]
    x = _terminos(cliente, sesion, alta["contrato_id"])
    assert dias == 10
    assert float(x["precio_mes_vehiculo"]) == float(SUV * dias)
    assert x["precios_de_la_lista"] is True


# ================================================================ lo raro

def test_si_la_lista_no_tiene_un_precio_no_se_adivina(cliente, sesion, datos,
                                                      lista):
    lista(agente=False)
    suv = _unidad(datos, "suv_blindada")
    alta = _alta(cliente, sesion, datos, date(2031, 11, 3), _equipo(datos, suv),
                 [suv["id"]])
    x = _terminos(cliente, sesion, alta["contrato_id"])
    # Sin el agente, el precio por dia no sale a medias: se queda vacio y
    # el visto bueno lo pide.
    assert x["precio_dia_personal"] is None
    assert float(x["precio_mes_vehiculo"]) == float(SUV * x["de_la_lista"]["dias_base"])
    assert x["precios_de_la_lista"] is False
    assert [f["descripcion"] for f in x["de_la_lista"]["faltan"]] == [
        "Agente de seguridad"]
    aviso = _revision(cliente, sesion, alta["contrato_id"])["lista_incompleta"]
    assert aviso["datos"]["que"] == "Agente de seguridad"


def test_en_12x36_se_cobra_una_persona_por_dia(cliente, sesion, datos, lista):
    lista()
    suv = _unidad(datos, "suv_blindada")
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    alta = _alta(cliente, sesion, datos, date(2031, 6, 1), [
        {"persona_id": datos["personal"]["Juan Ramirez"]["id"], "rol_id": conductor,
         "vehiculo_id": suv["id"], "empieza": True},
        {"persona_id": datos["personal"]["Luis Mendoza"]["id"], "rol_id": conductor,
         "vehiculo_id": suv["id"]}], [suv["id"]], turno="12x36")
    x = _terminos(cliente, sesion, alta["contrato_id"])
    assert float(x["precio_dia_personal"]) == float(CONDUCTOR)
    assert x["de_la_lista"]["dias_base"] == 30
    assert float(x["precio_mes_vehiculo"]) == float(SUV * 30)

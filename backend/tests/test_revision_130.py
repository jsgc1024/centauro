# -*- coding: utf-8 -*-
"""Seccion 130: la ola 4a de la revision del 2 de octubre, Brasil antes
de encenderlo (decisiones 3, 4, 5, 12 y 15 de Salvador).

  * Lo que Odoo no devuelve ni entre los archivados queda pendiente, y
    solo el archivado explicito da de baja; y el freno por pais: si un
    pais leyo cero con registros activos de Connect, la vuelta entera se
    detiene y lo dice (decision 3).
  * La persona, la unidad o el cliente que Odoo pasa a otro pais quedan
    pendientes con el boton para pasarlos, solo sin dias asignados por
    delante (decision 4).
  * Al asignar, solo la gente del pais de la plaza (decision 5).
  * El alta directa del implantado lee la lista que cobra por mes como la
    propuesta: mes completo con el mensual, dia adicional, hora extra del
    paquete y la prefactura con el producto del mes (decision 12).
  * No se manda una cotizacion sin la tasa (si va con IVA) ni las
    condiciones de pago del pais; ni una propuesta sin su texto de
    aceptacion (decision 15).
"""
import os
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app import disponibilidad, odoo_facturacion_mes
from app import models as m
from app import odoo_clientes_reglas, odoo_flota_reglas, odoo_oficina_reglas
from app import odoo_pais, odoo_personal
from app import odoo_personal_reglas
from test_cotizaciones_cliente import _crear
from test_odoo_personal import DOMINIO, ODOO0, empleado, leer, persona
from test_odoo_personal import sin_rastro  # noqa: F401  (fixture)
from test_odoo_brasil_personal import BRASIL, OdooConCampos, motorista
from test_odoo_tarifarios_brasil import (EXTRA_BR, PAQUETE_BR, _leido,
                                         _producto_de, _real, mundo_brasil)
from test_odoo_tarifarios_brasil import (brasil, clientes, de_brasil,  # noqa: F401
                                         filtros, mexico)
from test_odoo_tarifarios import OdooFalso as OdooTarifarios
from test_odoo_tarifarios import sin_filtros  # noqa: F401  (fixture)
from test_odoo_tarifarios import sin_rastro as sin_rastro_tarifarios  # noqa: F401
from test_odoo_tarifarios import tarifario
from test_implantado_lista import lista  # noqa: F401  (fixture)

WEB = os.path.join(os.path.dirname(__file__), "..", "app", "web")
NO_ENCONTRADO = "no se encontro en Odoo: revisar la conexion"


def _js(nombre: str) -> str:
    return open(os.path.join(WEB, nombre), encoding="utf-8").read()


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


# ====================================== decision 3 · lo que Odoo no devuelve

def test_lo_no_encontrado_queda_pendiente_y_solo_el_archivado_da_de_baja():
    """En las cuatro lecturas: sin fila (ni entre los archivados) es
    pendiente; `active` en falso es baja."""
    sin_fila = {}
    archivado = {ODOO0 + 1: {"id": ODOO0 + 1, "active": False}}
    vivo = {ODOO0 + 1: {"id": ODOO0 + 1, "active": True}}

    p = [{"id": 5, "odoo_id": ODOO0 + 1, "nombre": "X"}]
    bajas, pendientes = odoo_personal_reglas.clasificar_salidas(p, sin_fila)
    assert bajas == [] and pendientes[0]["falta"] == [NO_ENCONTRADO]
    bajas, pendientes = odoo_personal_reglas.clasificar_salidas(p, archivado)
    assert pendientes == [] and bajas[0]["motivo"] == "archivado en Odoo"
    bajas, pendientes = odoo_personal_reglas.clasificar_salidas(p, vivo)
    assert bajas == [] and pendientes[0]["falta"] == [
        "ya no tiene puesto de seguridad en Odoo"]

    v = [{"id": 5, "odoo_id": ODOO0 + 1, "placa": "ABC"}]
    bajas, pendientes = odoo_flota_reglas.clasificar_salidas(v, sin_fila, {})
    assert bajas == [] and pendientes[0]["falta"] == [NO_ENCONTRADO]
    bajas, pendientes = odoo_flota_reglas.clasificar_salidas(v, archivado, {})
    assert pendientes == [] and bajas[0]["motivo"] == "archivada en Odoo"

    bajas, pendientes = odoo_oficina_reglas.clasificar_salidas(p, sin_fila)
    assert bajas == [] and pendientes[0]["falta"] == [NO_ENCONTRADO]
    bajas, pendientes = odoo_oficina_reglas.clasificar_salidas(p, archivado)
    assert pendientes == [] and bajas[0]["motivo"] == "archivado en Odoo"

    c = [{"id": 5, "odoo_id": ODOO0 + 1, "nombre": "X"}]
    bajas, pendientes = odoo_clientes_reglas.clasificar_salidas(c, sin_fila)
    assert bajas == [] and pendientes[0]["falta"] == [NO_ENCONTRADO]
    bajas, pendientes = odoo_clientes_reglas.clasificar_salidas(c, archivado)
    assert pendientes == [] and bajas[0]["motivo"] == "archivado en Odoo"


def test_el_pais_que_lee_cero_con_gente_activa_detiene_la_vuelta(db):
    """Dos de Mexico y uno de Brasil entran. Luego la conexion deja de
    ver la compania de Mexico: el personal lee Mexico 0 y Brasil 1. Antes
    daba de baja a los dos de Mexico con sus accesos; ahora la vuelta se
    detiene, no toca nada, lo dice y deja su renglon."""
    odoo = OdooConCampos(empleado(1), empleado(2), motorista(3))
    leer(db, odoo)
    assert persona(db, 1).activo and persona(db, 2).activo

    # La conexion sin Centauro Mexico: solo se ven los de Brasil.
    del odoo.empleados[ODOO0 + 1]
    del odoo.empleados[ODOO0 + 2]
    ensayo = leer(db, odoo, ensayo=True)
    assert ensayo["detenida"] is True
    assert ensayo["freno"] == [{"codigo": "MX", "pais": "Mexico", "leidos": 0,
                                "activos": 2}]
    assert ensayo["bajas"] == [] and ensayo["altas"] == []
    assert [(p["codigo"], p["leidos"]) for p in ensayo["por_pais"]] == [
        ("MX", 0), ("BR", 1)]

    antes = db.query(m.SincronizacionOdoo).filter_by(tipo="personal").count()
    informe = leer(db, odoo)
    assert informe["detenida"] is True
    assert persona(db, 1).activo and persona(db, 2).activo
    assert db.query(m.Usuario).filter_by(persona_id=persona(db, 1).id).one().activo
    fila = (db.query(m.SincronizacionOdoo).filter_by(tipo="personal")
            .order_by(m.SincronizacionOdoo.id.desc()).first())
    assert db.query(m.SincronizacionOdoo).filter_by(tipo="personal").count() == antes + 1
    assert fila.bajas == 0 and fila.detalle.startswith('{"detenida": true')
    assert odoo_personal.resumen(informe) == {
        "detenida": True, "freno": informe["freno"], "leidos": 1}

    # Vuelve la compania: la vuelta sigue como siempre, sin bajas.
    odoo.empleados[ODOO0 + 1] = empleado(1)
    odoo.empleados[ODOO0 + 2] = empleado(2)
    informe = leer(db, odoo)
    assert not informe.get("detenida") and informe["bajas"] == []


def test_el_freno_mira_a_toda_la_compania_y_no_solo_al_puesto(db):
    """El unico de seguridad de Mexico cambia de puesto: Mexico sigue
    leyendo a su compania, asi que no es la conexion rota. Queda
    pendiente, como antes, y la vuelta sigue."""
    odoo = OdooConCampos(empleado(1))
    leer(db, odoo)
    odoo.cambiar(1, job_id=[91, "Monitorista Bilingüe"],
                 job_title="Monitorista Bilingüe")
    informe = leer(db, odoo)
    assert not informe.get("detenida")
    assert informe["pendientes"][0]["falta"] == [
        "ya no tiene puesto de seguridad en Odoo"]
    assert persona(db, 1).activo


def test_los_frenos_por_tipo_cuentan_lo_activo_de_odoo(db, brasil):  # noqa: F811
    """`frenos` solo se dispara con cero leidos y activos de Odoo de ese
    pais; lo capturado a mano en Connect no cuenta."""
    assert odoo_pais.frenos(db, odoo_pais.PERSONAL, {"MX": 0, "BR": 0}) == []
    sp = db.query(m.Plaza).filter_by(pais_id=brasil.id).first()
    p = m.Persona(nombre="De Odoo BR", correo=f"deodoo.br@{DOMINIO}",
                  plaza_id=sp.id, odoo_id=ODOO0 + 900, activo=True,
                  es_freelance=False)
    db.add(p)
    db.commit()
    try:
        assert odoo_pais.frenos(db, odoo_pais.PERSONAL, {"MX": 3, "BR": 0}) == [
            {"codigo": "BR", "pais": brasil.nombre, "leidos": 0, "activos": 1}]
        assert odoo_pais.frenos(db, odoo_pais.PERSONAL, {"MX": 0, "BR": 1}) == []
        assert odoo_pais.frenos(db, odoo_pais.OFICINA, {"BR": 0}) == []
    finally:
        db.delete(p)
        db.commit()


# ====================================== decision 4 · el cambio de pais

def test_el_pendiente_del_cambio_de_pais_trae_a_donde_lo_pone_odoo(db, datos):
    odoo = OdooConCampos(empleado(1), empleado(9))
    leer(db, odoo)
    odoo.cambiar(1, company_id=BRASIL, job_id=[40, "Motorista Executivo Bilíngue"],
                 job_title="Motorista Executivo Bilíngue",
                 work_location_id=[9, "São Paulo - Barueri"])
    informe = leer(db, odoo)
    [p] = [p for p in informe["pendientes"] if p["odoo_id"] == ODOO0 + 1]
    assert p["falta"] == ["en Odoo es de «Brasil» y en Centauro es de otro pais"]
    sp = (db.query(m.Plaza).join(m.Pais, m.Plaza.pais_id == m.Pais.id)
          .filter(m.Pais.codigo == "BR", m.Plaza.nombre == "Sao Paulo").one())
    assert p["cambio_de_pais"] == {"a_pais_id": sp.pais_id, "a_pais": "Brasil",
                                   "plaza_id": sp.id, "plaza": "Sao Paulo"}
    assert persona(db, 1).plaza_id == datos["cdmx"]["id"]


def test_el_cliente_que_cambia_de_pais_en_odoo_queda_pendiente(db, brasil):  # noqa: F811
    mx = db.query(m.Pais).filter_by(codigo="MX").one()
    paises = {}
    for p in (mx, brasil):
        ficha = {"id": p.id, "nombre": p.nombre}
        paises[p.codigo.upper()] = ficha
        paises[odoo_clientes_reglas.normal(p.nombre)] = ficha
    partners = [{"id": 1, "name": "Cliente X", "vat": "XAX010101AB1",
                 "country_id": [31, "Brasil"], "write_date": "2026-09-01 10:00:00"}]
    clientes_ = [{"id": 7, "odoo_id": 1, "nombre": "Cliente X", "rfc": "XAX010101AB1",
                  "pais_id": mx.id, "activo": True, "tarifario_id": None,
                  "sincronizado_en": datetime(2026, 9, 1)}]
    plan = odoo_clientes_reglas.planear(partners, clientes_, paises)
    assert plan["cambios"] == []
    assert plan["pendientes"] == [{
        "odoo_id": 1, "cliente_id": 7, "nombre": "Cliente X",
        "falta": ["en Odoo es de «Brasil» y en Centauro es de otro pais"],
        "cambio_de_pais": {"a_pais_id": brasil.id, "a_pais": brasil.nombre}}]
    assert plan["por_pais_id"] == {brasil.id: 1}
    assert plan["procesados"] == [7]


def test_pasar_de_pais_a_una_persona_solo_sin_dias_por_delante(
        db, cliente, sesion, datos, brasil):  # noqa: F811
    from ayudas import asignar, crear_servicio, jornada, manana

    odoo = OdooConCampos(empleado(1), empleado(9))
    leer(db, odoo)
    p = persona(db, 1)
    admin = db.query(m.Usuario).filter_by(correo="admin@centauro.lat").one()

    # Con un dia asignado por delante no se pasa.
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(3), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    assert asignar(cliente, h, j["id"], persona_id=p.id)[0].status_code == 200
    r = cliente.post("/odoo/pasar-de-pais", headers=sesion("admin"),
                     json={"tipo": "persona", "id": p.id, "pais_id": brasil.id,
                           "plaza": "Sao Paulo"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["clave"] == "dias_por_delante"
    assert r.json()["detail"]["dias"] == 1

    # Sin el dia, se pasa: a Sao Paulo, con su renglon en la bitacora.
    cliente.delete(f"/servicios/{servicio['id']}", headers=h)
    r = cliente.post("/odoo/pasar-de-pais", headers=sesion("consultor"),
                     json={"tipo": "persona", "id": p.id, "pais_id": brasil.id})
    assert r.status_code == 403
    r = cliente.post("/odoo/pasar-de-pais", headers=sesion("admin"),
                     json={"tipo": "persona", "id": p.id, "pais_id": brasil.id,
                           "plaza": "Sao Paulo"})
    assert r.status_code == 200, r.text
    assert r.json() == {"resultado": "pasado de pais", "tipo": "persona",
                        "id": p.id, "pais": brasil.nombre, "plaza": "Sao Paulo"}
    db.expire_all()
    assert persona(db, 1).plaza.pais_id == brasil.id
    renglon = (db.query(m.RegistroAdmin)
               .filter_by(accion="pasado de pais desde odoo", objeto="persona",
                          objeto_id=p.id).one())
    assert renglon.usuario_id == admin.id and "Sao Paulo" in renglon.despues
    # Lo que no viene de Odoo no se pasa por aqui.
    juan = datos["personal"]["Juan Ramirez"]["id"]
    r = cliente.post("/odoo/pasar-de-pais", headers=sesion("admin"),
                     json={"tipo": "persona", "id": juan, "pais_id": brasil.id})
    assert r.status_code == 404


def test_pasar_de_pais_a_una_unidad_y_a_un_cliente(db, cliente, sesion, datos,
                                                   brasil, de_brasil):  # noqa: F811
    sp = db.query(m.Plaza).filter_by(pais_id=brasil.id).first()
    mx = db.query(m.Pais).filter_by(codigo="MX").one()
    u = m.Vehiculo(placa="PAIS-130", categoria_id=datos["categorias"]["suv"]["id"],
                   plaza_id=datos["cdmx"]["id"], pais_id=mx.id, odoo_id=ODOO0 + 130,
                   activo=True, rentado=False)
    db.add(u)
    db.commit()
    r = cliente.post("/odoo/pasar-de-pais", headers=sesion("admin"),
                     json={"tipo": "unidad", "id": u.id, "pais_id": brasil.id})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert u.pais_id == brasil.id and u.plaza_id == sp.id
    db.delete(u)
    db.commit()

    # El cliente de Brasil que Odoo pasa a Mexico: pierde la lista de su
    # pais de antes, y la siguiente lectura de tarifarios le pone la suya.
    c = db.get(m.Cliente, de_brasil.cliente)
    lista = m.Tarifario(nombre="Brasil · de prueba", pais_id=brasil.id,
                        moneda=m.Moneda.BRL, activo=True,
                        vigencia_desde=date(2026, 1, 1))
    db.add(lista)
    db.flush()
    c.tarifario_id = lista.id
    db.commit()
    r = cliente.post("/odoo/pasar-de-pais", headers=sesion("admin"),
                     json={"tipo": "cliente", "id": c.id, "pais_id": mx.id})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert c.pais_id == mx.id and c.tarifario_id is None
    # No existe el pais: nada.
    r = cliente.post("/odoo/pasar-de-pais", headers=sesion("admin"),
                     json={"tipo": "cliente", "id": c.id, "pais_id": 9999})
    assert r.status_code == 404


# ====================================== decision 5 · solo la gente del pais

def test_al_asignar_solo_se_ofrece_la_gente_del_pais_de_la_plaza(db, datos, brasil):  # noqa: F811
    sp = db.query(m.Plaza).filter_by(pais_id=brasil.id).first()
    p = m.Persona(nombre="Paulo De Prueba", correo=f"paulo.130@{DOMINIO}",
                  plaza_id=sp.id, activo=True, es_freelance=False)
    db.add(p)
    db.commit()
    try:
        inicio = datetime(2029, 10, 15, 8)
        [dia] = disponibilidad.recomendar_personal_por_dia(
            db, datos["cdmx"]["id"], datos["perfiles"]["conductor_seguridad"]["id"],
            [(inicio, inicio + timedelta(hours=12), True)])
        nombres = {f["nombre"] for f in dia["de_otras_ciudades"]}
        assert "Paulo De Prueba" not in nombres
        # De Guadalajara si: es del mismo pais.
        gdl = [f["nombre"] for f in dia["de_otras_ciudades"]
               if f["ciudad"] == "Guadalajara"]
        assert gdl, dia["de_otras_ciudades"]
        # Y en Sao Paulo, Paulo es local; la gente de Mexico no se ofrece.
        [dia] = disponibilidad.recomendar_personal_por_dia(
            db, sp.id, datos["perfiles"]["conductor_seguridad"]["id"],
            [(inicio, inicio + timedelta(hours=12), True)])
        assert "Paulo De Prueba" in {f["nombre"] for f in dia["disponibles"]}
        assert dia["de_otras_ciudades"] == []
    finally:
        db.delete(p)
        db.commit()


# ====================================== decision 15 · lo del pais que frena

def test_la_cotizacion_no_se_manda_sin_tasa_ni_condiciones_de_pago(
        cliente, sesion, datos, db):
    mx = datos["mx"]["id"]
    h = sesion("consultor")
    antes = cliente.get(f"/cotizaciones/textos?pais_id={mx}", headers=h).json()
    pago = antes["textos"]["pago"]["es"]
    assert pago
    c = _crear(cliente, sesion, datos)
    assert not any("Catálogos" in f for f in c["faltan"])
    try:
        # Sin las condiciones de pago en espanol: no se manda, y lo dice.
        r = cliente.put(f"/cotizaciones/textos/{mx}", headers=sesion("diroperaciones"),
                        json={"razon_social": antes["razon_social"], "rfc": antes["rfc"],
                              "tasa_iva": "0.16", "textos": {"pago": {"es": ""}}})
        assert r.status_code == 200, r.text
        r = cliente.get(f"/cotizaciones/eventual/{c['id']}", headers=h)
        assert ("Las condiciones de pago y facturación del país en español, en "
                "Catálogos → Cotización al cliente") in r.json()["faltan"]
        r = cliente.post(f"/cotizaciones/eventual/{c['id']}/enviar", headers=h)
        assert r.status_code == 400, r.text
        assert "condiciones de pago" in r.json()["detail"]["mensaje"]
        # Sin la tasa, con IVA: tampoco. Sin IVA, la tasa no hace falta.
        r = cliente.put(f"/cotizaciones/textos/{mx}", headers=sesion("diroperaciones"),
                        json={"razon_social": antes["razon_social"], "rfc": antes["rfc"],
                              "tasa_iva": None, "textos": {"pago": {"es": pago}}})
        assert r.status_code == 200, r.text
        faltan = cliente.get(f"/cotizaciones/eventual/{c['id']}", headers=h).json()["faltan"]
        assert "La tasa de IVA del país, en Catálogos → Cotización al cliente" in faltan
        assert not any("condiciones de pago" in f for f in faltan)
        sin_iva = _crear(cliente, sesion, datos, con_iva=False)
        assert not any("Catálogos" in f for f in sin_iva["faltan"])
    finally:
        r = cliente.put(f"/cotizaciones/textos/{mx}", headers=sesion("admin"),
                        json={"razon_social": antes["razon_social"], "rfc": antes["rfc"],
                              "tasa_iva": "0.16", "textos": {"pago": {"es": pago}}})
        assert r.status_code == 200, r.text


# ====================================== decision 12 · la lista que cobra por mes

def _gente_de_sao_paulo(db, datos, brasil):
    sp = db.query(m.Plaza).filter_by(nombre="Sao Paulo", pais_id=brasil.id).one()
    p = m.Persona(nombre="Motorista De Prueba", correo=f"motorista.130@{DOMINIO}",
                  plaza_id=sp.id, activo=True, es_freelance=False)
    u = m.Vehiculo(placa="BRA-130", categoria_id=datos["categorias"]["minivan_blindada"]["id"],
                   plaza_id=sp.id, pais_id=brasil.id, activo=True, rentado=False)
    db.add_all([p, u])
    db.commit()
    return SimpleNamespace(plaza=sp, persona=p, unidad=u)


def _alta_amazon(cliente, sesion, datos, amazon, sp, **extra):
    r = cliente.post("/implantados", headers=sesion("consultor"), json={
        "cliente_id": amazon, "pais_id": sp.plaza.pais_id, "plaza_id": sp.plaza.id,
        "solicitante_nombre": "Beatriz", "solicitante_apellidos": "Souza",
        "ejecutivo_nombre": "Carlos", "ejecutivo_apellidos": "Lima",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "fecha_inicio": "2029-10-01", "dias_servicio": "lunes_viernes",
        "personal": [{"persona_id": sp.persona.id,
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": sp.unidad.id}],
        "unidades": [sp.unidad.id], **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_el_alta_directa_lee_la_lista_que_cobra_por_mes(
        db, filtros, de_brasil, cliente, sesion, datos, brasil):  # noqa: F811
    """Amazon Brasil sin propuesta: el mes nace con el esquema de mes
    completo, USD 16,855 al mes, el dia adicional de 766.14, la hora extra
    de 112 del paquete, en dolares, y la prefactura con el producto del
    mes. Antes nacia sin precios y «Usar los de la lista» borraba la hora
    extra."""
    _leido(db, OdooTarifarios(mundo_brasil()))
    lista = tarifario(db, 35)
    r = cliente.patch(f"/tarifarios/{lista.id}/viaticos", json={"incluidos": True},
                      headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    _real(db)
    sp = _gente_de_sao_paulo(db, datos, brasil)
    alta = _alta_amazon(cliente, sesion, datos, de_brasil.amazon, sp)
    contrato = db.get(m.ContratoImplantado, alta["contrato_id"])
    assert contrato.esquema == m.EsquemaCotizacionImplantado.MES_COMPLETO
    assert D(str(contrato.precio_mes_completo)) == D(16855)
    assert contrato.dias_del_mensual == 22
    assert D(str(contrato.precio_dia_adicional)) == D("766.14")
    assert D(str(contrato.precio_hora_extra)) == D(112)
    assert contrato.moneda == m.Moneda.USD and contrato.precios_de_la_lista is True

    # Lo que la pantalla de terminos dice de la lista.
    r = cliente.get(f"/implantados/contratos/{contrato.id}/terminos",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["esquema"] == "mes_completo" and t["precios_de_la_lista"] is True
    de = t["de_la_lista"]
    assert de["por_mes"] is True and de["completa"] is True
    assert de["precio_mes_completo"] == 16855.0 and de["dias_del_mensual"] == 22
    [paquete, unidad] = de["renglones"]
    assert (paquete["tipo"], paquete["por_mes"], paquete["precio_mes"],
            paquete["precio_dia"], paquete["precio_hora_extra"]) == (
        "paquete", True, 16855.0, 766.14, 112.0)
    assert unidad["tipo"] == "unidad_en_paquete"
    assert t["diferencias"] == []

    # «Usar los de la lista» no lo vuelve «por dia» ni borra la hora extra.
    r = cliente.post(f"/implantados/contratos/{contrato.id}/terminos/de-la-lista",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["esquema"] == "mes_completo"
    assert r.json()["precio_hora_extra"] == 112.0

    # La prefactura toma el paquete del mes con su producto.
    db.expire_all()
    [puesto] = odoo_facturacion_mes.puestos_del_mes(db, contrato, None)
    assert (puesto.tipo, puesto.mes, puesto.dia, puesto.he, puesto.cantidad) == (
        "paquete", D(16855), D("766.14"), D(112), 1)
    faltan = []
    productos = odoo_facturacion_mes.Productos(db, contrato,
                                               lambda *a, **k: faltan.append(a))
    assert productos.del_puesto(puesto) == _producto_de(db, PAQUETE_BR).id
    assert productos.de_hora_extra(puesto.perfil_id) == _producto_de(db, EXTRA_BR).id
    assert faltan == []

    # Un mes escrito distinto se dice como diferencia, con el esquema.
    r = cliente.put(f"/implantados/contratos/{contrato.id}/terminos",
                    headers=sesion("consultor"),
                    json={"esquema": "por_dia", "precio_dia_personal": "700",
                          "precio_dia_adicional": "700", "precio_mes_vehiculo": None,
                          "precio_mes_completo": None, "viaticos_incluidos": True,
                          "gastos_mes": None, "precio_hora_extra": "112",
                          "horas_jornada": None, "horas_descanso": None})
    assert r.status_code == 200, r.text
    campos = [d["campo"] for d in r.json()["diferencias"]]
    assert campos[0] == "esquema" and "precio_mes_completo" in campos
    assert r.json()["precios_de_la_lista"] is False


def test_el_mes_siguiente_sigue_con_la_lista_por_mes(
        db, filtros, de_brasil, cliente, sesion, datos, brasil):  # noqa: F811
    _leido(db, OdooTarifarios(mundo_brasil()))
    lista = tarifario(db, 35)
    cliente.patch(f"/tarifarios/{lista.id}/viaticos", json={"incluidos": True},
                  headers=sesion("finanzas"))
    _real(db)
    sp = _gente_de_sao_paulo(db, datos, brasil)
    alta = _alta_amazon(cliente, sesion, datos, de_brasil.amazon, sp)
    from app import implantado as motor
    hecho = motor.abrir_los_que_toquen(db, hoy=date(2029, 10, 29))
    assert hecho["fallados"] == [], hecho
    db.expire_all()
    siguiente = (db.query(m.ContratoImplantado)
                 .filter_by(servicio_id=alta["servicio_id"], anio=2029, mes=11).one())
    assert siguiente.esquema == m.EsquemaCotizacionImplantado.MES_COMPLETO
    assert D(str(siguiente.precio_mes_completo)) == D(16855)
    assert siguiente.precios_de_la_lista is True


def test_la_lista_por_dia_sigue_como_siempre(db, cliente, sesion, datos, lista):  # noqa: F811
    """Lo de Mexico con su lista por dia no cambia: el mes va por dia,
    `por_mes` es falso y los renglones traen su precio por dia."""
    from test_implantado_lista import _alta, _equipo, _terminos, _unidad
    lista()
    alta = _alta(cliente, sesion, datos, date(2029, 10, 1),
                 _equipo(datos, _unidad(datos, "suv_blindada")),
                 [_unidad(datos, "suv_blindada")["id"]])
    t = _terminos(cliente, sesion, alta["contrato_id"])
    assert t["esquema"] == "por_dia" and t["precios_de_la_lista"] is True
    assert t["de_la_lista"]["por_mes"] is False
    assert t["de_la_lista"]["precio_mes_completo"] is None
    assert all(r["por_mes"] is False for r in t["de_la_lista"]["renglones"]
               if r["tipo"] != "unidad_en_paquete")


# ====================================== las pantallas

def test_las_pantallas_traen_lo_nuevo():
    odoo = _js("odoo.js")
    assert "function botonDePais" in odoo and "/odoo/pasar-de-pais" in odoo
    assert "d.detenida" in odoo and "odo_detenida" in odoo
    assert '"no se encontro en Odoo: revisar la conexion": "odo_f_no_encontrado"' in odoo
    implantado = _js("implantado.js")
    assert "r.por_mes" in implantado and "imp_lista_mensual_de_la_lista" in implantado
    cierre = _js("cierre.js")
    assert "precio_mes_completo: \"cie_mes_completo\"" in cierre
    idioma = _js("idioma.js")
    for clave in ("odo_detenida", "odo_pasar_a", "odo_pasarla_a", "odo_pasar_pie",
                  "odo_pasado", "odo_f_no_encontrado", "odo_freno_pais",
                  "imp_lista_unidad_por_mes", "imp_lista_mensual_de_la_lista",
                  "imp_lista_esquema"):
        assert idioma.count(f"    {clave}:") == 3, clave

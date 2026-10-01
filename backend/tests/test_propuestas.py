# -*- coding: utf-8 -*-
"""La propuesta del implantado (seccion 115).

Lo que aqui se cuida, con las cinco decisiones de Salvador del 1 de
octubre:

  * Su serie, EP/PRO-0001, aparte de la EP/COT, con sus versiones.
  * Los precios salen de la lista de implantados del cliente: su precio
    por dia por los dias de la modalidad --22, 26 o 30--. El dia
    adicional es el precio por dia de las personas; la hora extra, la
    suma de la de cada rol.
  * El precio escrito es especial: sin el visto bueno de direccion de
    operaciones no se manda, y si cambia se vuelve a pedir.
  * Mandarla guarda su PDF; la version siguiente sustituye a la de antes.
  * Al autorizarla nace el implantado con la propuesta adentro, y su
    primer mes se abre con los terminos pactados: precio fijo, el dia
    adicional aparte y el primer mes a medias por dia.
  * La lista de la pantalla trae cotizaciones y propuestas.
"""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import cierre_mes
from app import implantado as motor_implantado
from app import models as m
from app import propuesta as motor
from app import propuesta_pdf

D = Decimal
INICIO = date(2029, 9, 24)          # lunes; septiembre de 2029 acaba en domingo


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture
def lista(db, datos):
    """La lista de implantados del cliente de la semilla: conductor a
    $3,000 el dia con hora extra de $300, y la CUV a $2,000."""
    completo = datos["modalidades"]["full_day"]["id"]
    tarifario = m.Tarifario(nombre="Implantados prueba 115",
                            pais_id=datos["mx"]["id"], moneda=m.Moneda.MXN,
                            vigencia_desde=date(2026, 1, 1))
    db.add(tarifario)
    db.flush()
    db.add(m.TarifaRecurso(tarifario_id=tarifario.id,
                           perfil_id=datos["perfiles"]["conductor_seguridad"]["id"],
                           modalidad_id=completo, precio=D("3000"),
                           precio_hora_extra=D("300")))
    db.add(m.TarifaVehiculo(tarifario_id=tarifario.id,
                            categoria_id=datos["categorias"]["cuv"]["id"],
                            modalidad_id=completo, precio=D("2000")))
    cliente = db.get(m.Cliente, datos["cliente_id"])
    antes = cliente.tarifario_implantado_id
    cliente.tarifario_implantado_id = tarifario.id
    db.commit()
    yield tarifario
    cliente = db.get(m.Cliente, datos["cliente_id"])
    cliente.tarifario_implantado_id = antes
    # Las propuestas de la prueba la nombran; se vacian antes de la que
    # sigue, pero la lista se va ahora.
    db.query(m.Cotizacion).filter_by(tarifario_id=tarifario.id).update(
        {"tarifario_id": None})
    db.commit()
    db.delete(db.get(m.Tarifario, tarifario.id))
    db.commit()


@pytest.fixture
def cliente_de_odoo(db, datos):
    cliente = db.get(m.Cliente, datos["cliente_id"])
    antes = cliente.odoo_id
    cliente.odoo_id = 990115
    db.commit()
    yield cliente
    cliente = db.get(m.Cliente, datos["cliente_id"])
    cliente.odoo_id = antes
    db.commit()


def _conductor(datos, **extra):
    return {"tipo": "recurso", "cantidad": 1,
            "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"], **extra}


def _cuv(datos, **extra):
    return {"tipo": "vehiculo", "cantidad": 1,
            "categoria_id": datos["categorias"]["cuv"]["id"], **extra}


def _cuerpo(datos, **extra):
    """La del cliente de la semilla: un conductor y una CUV, de lunes a
    viernes en la Ciudad de Mexico, con mas viaticos."""
    return {
        "cliente_id": datos["cliente_id"],
        "solicitante_nombre": "Andrea", "solicitante_apellidos": "Ruiz",
        "solicitante_correo": "andrea.ruiz@ejemplo.com",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "tipo_servicio": "Transporte terrestre seguro",
        "valida_hasta": str(date.today() + timedelta(days=60)),
        "idioma": "es", "con_iva": True, "inicio": str(INICIO),
        "dias_servicio": "lunes_viernes", "viaticos": "aparte",
        "hora_presentacion": "07:00",
        "posiciones": [_conductor(datos), _cuv(datos)],
        **extra,
    }


def _siemens(datos, **extra):
    """La de Salvador: Siemens Energy, que todavia no esta en Odoo; todo
    su precio se escribe."""
    cuerpo = _cuerpo(datos, cliente_id=None, prospecto="Siemens Energy",
                     pais_id=datos["mx"]["id"], horas_jornada=14,
                     precio_hora_extra="400",
                     posiciones=[
                         _conductor(datos, precio_mes="68600",
                                    descripcion="Conductor de seguridad bilingüe"),
                         _cuv(datos, precio_mes="50000",
                              descripcion="Unidad CUV · Toyota RAV, hasta 3 "
                                          "pasajeros")])
    cuerpo.update(extra)
    return cuerpo


def _crear(cliente, sesion, cuerpo, quien="consultor"):
    r = cliente.post("/cotizaciones/propuesta", json=cuerpo,
                     headers=sesion(quien))
    assert r.status_code == 201, r.text
    return r.json()


def _enviar(cliente, sesion, p, quien="consultor", codigo=200):
    r = cliente.post(f"/cotizaciones/propuesta/{p['id']}/enviar",
                     headers=sesion(quien))
    assert r.status_code == codigo, r.text
    return r.json()


def _visto_bueno(cliente, sesion, p, autoriza=True, nota=None, huella=None,
                 quien="diroperaciones"):
    return cliente.post(f"/cotizaciones/propuesta/{p['id']}/especial/decidir",
                        json={"autoriza": autoriza, "nota": nota,
                              "huella": huella or p["huella"]},
                        headers=sesion(quien))


# ---------------------------------------------------------------- los precios

def test_con_la_lista_de_implantados_el_mensual_sale_solo(cliente, sesion,
                                                          datos, lista):
    p = _crear(cliente, sesion, _cuerpo(datos))
    assert p["folio"] == "EP/PRO-0001" and p["version"] == 1
    assert p["clase"] == "propuesta" and p["estatus"] == "borrador"
    assert p["lista"]["nombre"] == "Implantados prueba 115"
    # 22 dias de lunes a viernes: 3,000 y 2,000 el dia.
    assert [(x["nombre"], x["precio_mes"], x["especial"])
            for x in p["posiciones"]] == [
        ("Conductor de seguridad", 66000.0, False), ("CUV", 44000.0, False)]
    assert p["subtotal"] == 110000 and p["iva"] == 17600
    assert p["total"] == 127600 and p["al_mes"] is True
    # El dia adicional, el de las personas; la hora extra, la de la lista.
    assert p["dia_adicional"] == 3000 and p["hora_extra"] == 300
    assert p["especial"]["necesita"] is False and p["aviso_precios"] is None
    assert p["faltan"] == [] and p["se_edita"] is True


@pytest.mark.parametrize("dias,base,mensual,adicional", [
    ("lunes_viernes", 22, 66000, 3000),
    ("lunes_sabado", 26, 78000, 3000),
    ("todos", 30, 90000, None),
])
def test_las_tres_modalidades(cliente, sesion, datos, lista, dias, base,
                              mensual, adicional):
    r = cliente.post("/cotizaciones/propuesta/precios",
                     json=_cuerpo(datos, dias_servicio=dias,
                                  posiciones=[_conductor(datos)]),
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["base"] == base
    assert p["posiciones"][0]["precio_mes"] == mensual
    # El mes completo no tiene dia fuera de la modalidad.
    assert p["dia_adicional"] == adicional


def test_el_precio_escrito_es_especial_y_su_dia_es_el_mensual_entre_22(
        cliente, sesion, datos):
    p = _crear(cliente, sesion, _siemens(datos))
    assert p["cliente"] == "Siemens Energy" and p["es_prospecto"] is True
    assert p["lista"] is None
    conductor, unidad = p["posiciones"]
    assert conductor["especial"] and unidad["especial"]
    assert conductor["precio_mes"] == 68600
    # 68,600 entre 22: el dia adicional que el ejemplo decia $3,118.
    assert conductor["precio_dia"] == 3118.18
    assert p["dia_adicional"] == 3118.18
    assert p["hora_extra"] == 400 and p["hora_extra_especial"] is True
    assert p["subtotal"] == 118600 and p["total"] == 137576
    assert p["especial"]["necesita"] is True
    assert "El visto bueno de dirección de operaciones al precio especial" \
        in p["faltan"] or "Por qué el precio es especial" in p["faltan"]


def test_lo_que_no_tiene_precio_se_guarda_y_no_se_manda(cliente, sesion,
                                                        datos, lista):
    p = _crear(cliente, sesion, _cuerpo(
        datos, posiciones=[_conductor(datos), {
            "tipo": "vehiculo", "cantidad": 1,
            "categoria_id": datos["categorias"]["suv_blindada"]["id"]}]))
    assert p["aviso_precios"] == "SUV Blindada"
    assert any("precio de SUV Blindada" in f for f in p["faltan"])
    r = cliente.post(f"/cotizaciones/propuesta/{p['id']}/enviar",
                     headers=sesion("consultor"))
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------- el precio especial

def test_el_precio_especial_lo_autoriza_direccion_antes_de_mandarla(
        cliente, sesion, datos, db):
    p = _crear(cliente, sesion, _siemens(datos))
    # Sin el visto bueno no se manda.
    r = cliente.post(f"/cotizaciones/propuesta/{p['id']}/enviar",
                     headers=sesion("consultor"))
    assert r.status_code == 400, r.text
    # Pedirlo sin motivo, no.
    r = cliente.post(f"/cotizaciones/propuesta/{p['id']}/especial",
                     headers=sesion("consultor"))
    assert r.status_code == 400 and "por qué" in r.text.lower()
    r = cliente.put(f"/cotizaciones/propuesta/{p['id']}", headers=sesion("consultor"),
                    json=_siemens(datos, especial_motivo="Tarifa pactada con "
                                                         "Siemens para 2026"))
    assert r.status_code == 200, r.text
    r = cliente.post(f"/cotizaciones/propuesta/{p['id']}/especial",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["especial"]["estatus"] == "pedido"
    assert p["se_pide_especial"] is False and p["se_decide_especial"] is False
    # Le llega a direccion de operaciones, por correo, y a su bandeja.
    avisos = db.query(m.Notificacion).filter(
        m.Notificacion.correo == "operaciones@centauro.lat").all()
    assert any("precio especial por autorizar" in a.asunto for a in avisos)
    bandeja = cliente.get("/direccion/bandeja", headers=sesion("diroperaciones"))
    assert bandeja.status_code == 200, bandeja.text
    pendientes = bandeja.json()["precios_especiales"]
    assert [x["nombre"] for x in pendientes] == ["EP/PRO-0001 V1"]
    assert pendientes[0]["motivo"] == "Tarifa pactada con Siemens para 2026"
    assert pendientes[0]["especiales"][0]["precio_mes"] == 68600
    # El consultor no se lo autoriza solo.
    assert _visto_bueno(cliente, sesion, p, quien="consultor").status_code == 403
    # Con la huella de otros precios, no.
    r = _visto_bueno(cliente, sesion, p, huella="0" * 64)
    assert r.status_code == 409, r.text
    r = _visto_bueno(cliente, sesion, p, nota="Va, es cliente estratégico")
    assert r.status_code == 200, r.text
    assert r.json()["especial"]["estatus"] == "autorizado"
    assert r.json()["especial"]["vigente"] is True
    # Al consultor le llega la respuesta.
    assert any("precio especial autorizado" in a.asunto for a in db.query(
        m.Notificacion).filter(m.Notificacion.correo == "ana.solis@centauro.lat"))
    enviada = _enviar(cliente, sesion, p)
    assert enviada["estatus"] == "enviada"
    assert enviada["pdf"]["nombre"].endswith(
        "_SIEMENSENERGY_EP-PRO-0001_V1_CIUDADDEMEXICO.pdf")


def test_si_cambia_el_precio_se_vuelve_a_pedir(cliente, sesion, datos):
    cuerpo = _siemens(datos, especial_motivo="Tarifa pactada")
    p = _crear(cliente, sesion, cuerpo)
    p = cliente.post(f"/cotizaciones/propuesta/{p['id']}/especial",
                     headers=sesion("consultor")).json()
    p = _visto_bueno(cliente, sesion, p).json()
    assert p["especial"]["vigente"] is True
    # Cambiar el motivo no toca el precio: el visto bueno sigue.
    r = cliente.put(f"/cotizaciones/propuesta/{p['id']}", headers=sesion("consultor"),
                    json={**cuerpo, "especial_motivo": "Tarifa pactada 2026"})
    assert r.json()["especial"]["vigente"] is True
    # Cambiar el precio, si.
    cuerpo["posiciones"][0]["precio_mes"] = "70000"
    r = cliente.put(f"/cotizaciones/propuesta/{p['id']}", headers=sesion("consultor"),
                    json=cuerpo)
    assert r.status_code == 200, r.text
    assert r.json()["especial"]["vigente"] is False
    assert r.json()["se_pide_especial"] is True
    _enviar(cliente, sesion, r.json(), codigo=400)


def test_direccion_que_la_arma_la_autoriza_de_una_vez(cliente, sesion, datos):
    p = _crear(cliente, sesion, _siemens(datos, especial_motivo="Tarifa 2026"),
               quien="diroperaciones")
    r = cliente.post(f"/cotizaciones/propuesta/{p['id']}/especial",
                     headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    assert r.json()["especial"]["estatus"] == "autorizado"
    _enviar(cliente, sesion, r.json(), quien="diroperaciones")


def test_el_no_lleva_su_nota_y_le_llega_al_consultor(cliente, sesion, datos,
                                                       db):
    p = _crear(cliente, sesion, _siemens(datos, especial_motivo="Tarifa 2026"))
    p = cliente.post(f"/cotizaciones/propuesta/{p['id']}/especial",
                     headers=sesion("consultor")).json()
    assert _visto_bueno(cliente, sesion, p, autoriza=False).status_code == 400
    r = _visto_bueno(cliente, sesion, p, autoriza=False,
                     nota="El conductor bilingüe va a 72,000")
    assert r.status_code == 200, r.text
    assert r.json()["especial"]["estatus"] == "rechazado"
    assert r.json()["especial"]["nota"] == "El conductor bilingüe va a 72,000"
    assert any("no autorizado" in a.asunto for a in db.query(
        m.Notificacion).filter(m.Notificacion.correo == "ana.solis@centauro.lat"))
    # Lo corrige y lo vuelve a pedir.
    assert r.json()["se_pide_especial"] is True


# ---------------------------------------------------------------- folio y versiones

def _cotizacion_eventual(cliente, sesion, datos):
    """Una cotizacion del eventual (seccion 114), la mas sencilla."""
    r = cliente.post("/cotizaciones/eventual", headers=sesion("consultor"), json={
        "cliente_id": datos["cliente_id"], "solicitante_nombre": "Valeria",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "valida_hasta": str(date.today() + timedelta(days=60)),
        "gastos": "dentro",
        "equipos": [{"plaza_id": datos["cdmx"]["id"],
                     "lleva": [{"tipo": "recurso", "cantidad": 1,
                                "id": datos["perfiles"]["conductor_seguridad"]["id"]}],
                     "dias": [{"fecha": str(INICIO),
                               "modalidad_id": datos["modalidades"]["full_day"]["id"]}]}]})
    assert r.status_code == 201, r.text
    return r.json()


def test_su_serie_es_aparte_de_la_cotizacion(cliente, sesion, datos, lista):
    cot = _cotizacion_eventual(cliente, sesion, datos)
    assert cot["folio"] == "EP/COT-0001"
    uno = _crear(cliente, sesion, _cuerpo(datos))
    dos = _crear(cliente, sesion, _cuerpo(datos))
    assert (uno["folio"], dos["folio"]) == ("EP/PRO-0001", "EP/PRO-0002")
    # La de una serie no se abre por la puerta de la otra.
    assert cliente.get(f"/cotizaciones/eventual/{uno['id']}",
                       headers=sesion("consultor")).status_code == 404
    assert cliente.get(f"/cotizaciones/propuesta/{cot['id']}",
                       headers=sesion("consultor")).status_code == 404
    # La lista de la pantalla trae las dos; la de antes, solo cotizaciones.
    todas = cliente.get("/cotizaciones/lista", headers=sesion("consultor")).json()
    assert [f["folio"] for f in todas["filas"]] == [
        "EP/PRO-0002", "EP/PRO-0001", "EP/COT-0001"]
    assert todas["cuentas"]["todas"] == 3
    solo = cliente.get("/cotizaciones/lista?que=propuestas",
                       headers=sesion("consultor")).json()
    assert {f["clase"] for f in solo["filas"]} == {"propuesta"}
    eventual = cliente.get("/cotizaciones/eventual", headers=sesion("consultor")).json()
    assert [f["folio"] for f in eventual["filas"]] == ["EP/COT-0001"]
    busca = cliente.get("/cotizaciones/lista?q=pro-0002",
                        headers=sesion("consultor")).json()
    assert [f["folio"] for f in busca["filas"]] == ["EP/PRO-0002"]


def test_la_version_siguiente_y_el_visto_bueno_que_trae(cliente, sesion, datos):
    p = _crear(cliente, sesion, _siemens(datos, especial_motivo="Tarifa 2026"))
    p = cliente.post(f"/cotizaciones/propuesta/{p['id']}/especial",
                     headers=sesion("consultor")).json()
    p = _visto_bueno(cliente, sesion, p).json()
    v1 = _enviar(cliente, sesion, p)
    r = cliente.post(f"/cotizaciones/propuesta/{v1['id']}/version",
                     headers=sesion("consultor"))
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["folio"] == "EP/PRO-0001" and v2["version"] == 2
    assert v2["estatus"] == "borrador"
    # Trae el visto bueno: sus precios son los mismos.
    assert v2["especial"]["vigente"] is True
    assert "Qué cambió en esta versión" in v2["faltan"]
    r = cliente.put(f"/cotizaciones/propuesta/{v2['id']}", headers=sesion("consultor"),
                    json=_siemens(datos, especial_motivo="Tarifa 2026",
                                  inicio=str(INICIO + timedelta(days=7)),
                                  motivo="El cliente movió el inicio"))
    assert r.status_code == 200, r.text
    _enviar(cliente, sesion, r.json())
    v1 = cliente.get(f"/cotizaciones/propuesta/{v1['id']}",
                     headers=sesion("consultor")).json()
    assert v1["estatus"] == "sustituida"


def test_rechazada_y_vencida(cliente, sesion, datos, lista, db):
    p = _enviar(cliente, sesion, _crear(cliente, sesion, _cuerpo(datos)))
    r = cliente.post(f"/cotizaciones/propuesta/{p['id']}/rechazar",
                     json={"motivo": "Se fue con otro proveedor"},
                     headers=sesion("consultor"))
    assert r.status_code == 200 and r.json()["estatus"] == "rechazada"
    otra = _enviar(cliente, sesion, _crear(cliente, sesion, _cuerpo(datos)))
    fila = db.get(m.Cotizacion, otra["id"])
    fila.valida_hasta = date.today() - timedelta(days=2)
    db.commit()
    from app import cotizacion_cliente
    assert cotizacion_cliente.vencer(db)["vencidas"] == 1
    db.expire_all()
    assert db.get(m.Cotizacion, otra["id"]).estatus == m.EstatusCotizacion.VENCIDA


# ---------------------------------------------------------------- el implantado

def _autorizar(cliente, sesion, p, quien="consultor", **campos):
    datos = {"autorizada_por": "Andrea Ruiz",
             "autorizada_el": str(date.today()), **campos}
    return cliente.post(f"/cotizaciones/propuesta/{p['id']}/autorizar",
                        data=datos, headers=sesion(quien))


def test_autorizada_nace_el_implantado_con_la_propuesta_adentro(
        cliente, sesion, datos, lista, cliente_de_odoo, db):
    p = _enviar(cliente, sesion, _crear(cliente, sesion, _cuerpo(datos)))
    r = _autorizar(cliente, sesion, p)
    assert r.status_code == 200, r.text
    nacido = r.json()
    assert nacido["folio"].startswith("EP/IM-")
    assert nacido["estatus"] == "autorizado"
    servicio = db.get(m.Servicio, nacido["servicio_id"])
    assert servicio.tipo == m.TipoServicio.IMPLANTADO
    assert servicio.plaza_id == datos["cdmx"]["id"]
    assert servicio.consultor_id == datos["personal"]["Ana Solis"]["id"]
    acuerdo = db.query(m.AcuerdoImplantado).filter_by(
        servicio_id=servicio.id).one()
    assert acuerdo.fecha_inicio == INICIO
    assert acuerdo.dias_servicio == m.DiasServicio.LUNES_VIERNES
    assert acuerdo.hora_presentacion == "07:00:00"
    assert "EP/PRO-0001 V1" in acuerdo.cubre
    ahora = cliente.get(f"/cotizaciones/propuesta/{p['id']}",
                        headers=sesion("consultor")).json()
    assert ahora["estatus"] == "autorizada"
    assert ahora["servicio"]["folio"] == nacido["folio"]
    # El bloque de la pantalla del implantado.
    trato = cliente.get(f"/implantados/{servicio.id}/acuerdo",
                        headers=sesion("consultor")).json()
    assert trato["propuesta"]["nombre"] == "EP/PRO-0001 V1"
    assert trato["propuesta"]["subtotal"] == 110000
    # La propuesta no es la cotizacion de nadie: el eventual no la ve.
    from app import cotizacion as cot
    assert cot.vigente(db, servicio.id) is None


def test_la_empresa_nueva_se_autoriza_con_su_cliente_de_odoo(
        cliente, sesion, datos, cliente_de_odoo):
    p = _crear(cliente, sesion, _siemens(datos, especial_motivo="Tarifa 2026"))
    p = cliente.post(f"/cotizaciones/propuesta/{p['id']}/especial",
                     headers=sesion("consultor")).json()
    p = _enviar(cliente, sesion, _visto_bueno(cliente, sesion, p).json())
    r = _autorizar(cliente, sesion, p)
    assert r.status_code == 400 and r.json()["detail"]["clave"] == "sin_cliente"
    r = _autorizar(cliente, sesion, p, cliente_id=datos["cliente_id"])
    assert r.status_code == 200, r.text


def _primer_mes(cliente, sesion, datos, servicio_id):
    """El primer mes como lo abre la consola: la plantilla, sin hora ni
    precios."""
    r = cliente.post(f"/implantados/{servicio_id}/mes", headers=sesion("consultor"),
                     json={"personal": [{
                         "persona_id": datos["personal"]["Juan Ramirez"]["id"],
                         "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                         "vehiculo_id": datos["suburban"]["id"]}],
                         "unidades": [datos["suburban"]["id"]],
                         "modalidad_id": datos["modalidades"]["full_day"]["id"],
                         "esquema": "por_dia"})
    assert r.status_code == 201, r.text
    return r.json()


def test_el_primer_mes_abre_con_los_terminos_de_la_propuesta(
        cliente, sesion, datos, lista, cliente_de_odoo, db):
    p = _enviar(cliente, sesion, _crear(cliente, sesion, _cuerpo(
        datos, viaticos="incluidos", horas_jornada=14)))
    servicio_id = _autorizar(cliente, sesion, p).json()["servicio_id"]
    mes = _primer_mes(cliente, sesion, datos, servicio_id)
    contrato = db.get(m.ContratoImplantado, mes["contrato_id"])
    assert contrato.esquema == m.EsquemaCotizacionImplantado.MES_COMPLETO
    assert contrato.dias_del_mensual == 22
    assert D(str(contrato.precio_mes_completo)) == D("110000")
    assert D(str(contrato.precio_dia_adicional)) == D("3000")
    assert D(str(contrato.precio_hora_extra)) == D("300")
    assert D(str(contrato.horas_jornada)) == D("14")
    assert contrato.viaticos_incluidos is True and contrato.gastos_mes is None
    assert contrato.precios_de_la_lista is False
    # La hora del trato no se pierde con las 08:00 de omision.
    assert contrato.hora_presentacion == "07:00:00"
    terminos = cliente.get(f"/implantados/contratos/{contrato.id}/terminos",
                           headers=sesion("consultor")).json()
    assert terminos["dias_del_mensual"] == 22
    # La pantalla dice de que propuesta salen, en lugar de compararlos
    # con la lista.
    assert terminos["propuesta"]["nombre"].startswith("EP/PRO-")
    # El visto bueno del mes dice que son los de la propuesta.
    revision = cierre_mes.revisar(db, contrato)
    assert any(o.get("clave") == "precios_propuesta"
               for o in revision["observaciones"])


def test_la_hora_del_trato_tampoco_se_pierde_sin_propuesta(cliente, sesion,
                                                           datos, db):
    alta = cliente.post("/implantados/servicio", headers=sesion("consultor"), json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "solicitante_nombre": "Rocio",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "acuerdo": {"fecha_inicio": str(INICIO), "dias_servicio": "lunes_viernes"}})
    assert alta.status_code == 201, alta.text
    sid = alta.json()["servicio_id"]
    # La que el trato ya traia --la de una propuesta, o la que escriba
    # quien lo arme--: abrir el mes sin hora no la pisa con las 08:00.
    acuerdo = db.query(m.AcuerdoImplantado).filter_by(servicio_id=sid).one()
    acuerdo.hora_presentacion = "06:30:00"
    db.commit()
    mes = _primer_mes(cliente, sesion, datos, sid)
    db.expire_all()
    assert db.get(m.ContratoImplantado,
                  mes["contrato_id"]).hora_presentacion == "06:30:00"


# ---------------------------------------------------------------- el cobro del mes

def _contrato(**campos):
    base = {"esquema": m.EsquemaCotizacionImplantado.MES_COMPLETO,
            "dias_del_mensual": 22, "dias_servicio": m.DiasServicio.LUNES_VIERNES,
            "precio_mes_completo": D("110000"),
            "precio_dia_adicional": D("3000"), "desde_dia": None,
            "anio": 2029, "mes": 9, "servicio_id": 0}
    base.update(campos)
    return SimpleNamespace(**base)


def _habiles(desde=1, hasta=30, tope=5):
    return [date(2029, 9, d) for d in range(desde, hasta + 1)
            if date(2029, 9, d).weekday() < tope]


def test_el_mensual_no_cambia_con_los_dias_del_mes(db):
    # Septiembre de 2029 trae 20 habiles: el mensual es el mismo.
    cobro = motor_implantado.cobro_del_mensual(db, _contrato(), _habiles())
    assert len(_habiles()) == 20
    assert cobro["importe_mes"] == D("110000") and cobro["fuera"] == []


def test_el_dia_fuera_de_la_modalidad_va_aparte(db):
    trabajados = _habiles() + [date(2029, 9, 29)]            # un sabado
    cobro = motor_implantado.cobro_del_mensual(db, _contrato(), trabajados)
    assert cobro["fuera"] == ["2029-09-29"]
    assert cobro["importe_adicionales"] == D("3000")
    # De lunes a sabado el sabado va dentro; el domingo, aparte.
    cobro = motor_implantado.cobro_del_mensual(
        db, _contrato(dias_servicio=m.DiasServicio.LUNES_SABADO,
                      precio_mes_completo=D("130000")),
        _habiles(tope=6) + [date(2029, 9, 30)])
    assert cobro["base"] == 26 and cobro["fuera"] == ["2029-09-30"]
    # El mes completo no tiene dias fuera.
    cobro = motor_implantado.cobro_del_mensual(
        db, _contrato(dias_servicio=m.DiasServicio.TODOS),
        _habiles(tope=7))
    assert cobro["base"] == 30 and cobro["fuera"] == []


def test_el_12x36_no_tiene_dias_adicionales(db, monkeypatch):
    monkeypatch.setattr(motor_implantado, "turno_del_servicio",
                        lambda db, sid: motor_implantado.TURNO_12X36)
    cobro = motor_implantado.cobro_del_mensual(db, _contrato(), _habiles(tope=7))
    assert cobro["base"] == 30 and cobro["fuera"] == []


def test_el_primer_mes_a_medias_va_por_dia(db):
    # Empieza el lunes 24: cinco dias de servicio, a 110,000 entre 22.
    cobro = motor_implantado.cobro_del_mensual(
        db, _contrato(desde_dia=24), _habiles(desde=24))
    assert cobro["parcial"] is True and cobro["dentro"] == 5
    assert cobro["precio_dia"] == D("5000.00")
    assert cobro["importe_mes"] == D("25000.00")
    assert cobro["contratado"] == D("25000.00")
    # Un dia que nadie cubrio no se cobra.
    cobro = motor_implantado.cobro_del_mensual(
        db, _contrato(desde_dia=24), _habiles(desde=24)[:-1])
    assert cobro["importe_mes"] == D("20000.00")


def test_el_que_empieza_el_primer_dia_de_servicio_cobra_el_mes(db):
    """El 1 y el 2 de septiembre de 2029 son sabado y domingo: el de lunes
    a viernes que empieza el lunes 3 cubre todos sus dias del mes y se
    cobra su mensual, no por dia. El de lunes a sabado que empieza el 3
    ya se perdio el sabado 1: ese si va por dia."""
    cobro = motor_implantado.cobro_del_mensual(
        db, _contrato(desde_dia=3), _habiles(desde=3))
    assert cobro["parcial"] is False
    assert cobro["importe_mes"] == D("110000")
    cobro = motor_implantado.cobro_del_mensual(
        db, _contrato(desde_dia=4), _habiles(desde=4))
    assert cobro["parcial"] is True and cobro["dentro"] == 19
    cobro = motor_implantado.cobro_del_mensual(
        db, _contrato(desde_dia=3, dias_servicio=m.DiasServicio.LUNES_SABADO,
                      precio_mes_completo=D("130000")),
        _habiles(desde=3, tope=6))
    assert cobro["parcial"] is True


def test_el_mes_completo_de_antes_sigue_igual(db):
    """Sin `dias_del_mensual` --los contratos de antes de la seccion 115--
    el precio fijo es todo incluido, como siempre."""
    assert motor_implantado.cobro_del_mensual(
        db, _contrato(dias_del_mensual=None), _habiles()) is None


def test_el_cierre_del_mes_y_su_factura(cliente, sesion, datos, lista,
                                        cliente_de_odoo, db):
    """Del 24 al 28 de septiembre de 2029, y el sabado 29 pedido aparte:
    cinco dias a 110,000 entre 22 y un dia adicional."""
    p = _enviar(cliente, sesion, _crear(cliente, sesion, _cuerpo(datos)))
    servicio_id = _autorizar(cliente, sesion, p).json()["servicio_id"]
    mes = _primer_mes(cliente, sesion, datos, servicio_id)
    r = cliente.post(f"/implantados/contratos/{mes['contrato_id']}/dias-adicionales",
                     json={"fecha": "2029-09-29"}, headers=sesion("consultor"))
    assert r.status_code in (200, 201), r.text
    contrato = db.get(m.ContratoImplantado, mes["contrato_id"])
    comparativo = cierre_mes.comparar(db, contrato)
    assert comparativo["mensual"]["parcial"] is True
    assert comparativo["mensual"]["dias_de_servicio"] == 5
    assert comparativo["trabajado"]["dias_adicionales"] == 1
    assert comparativo["trabajado"]["desglose"]["mes_completo"] == D("25000.00")
    assert comparativo["trabajado"]["desglose"]["dias_adicionales"] == D("3000")
    assert comparativo["trabajado"]["importe"] == D("28000.00")
    assert comparativo["contratado"]["importe"] == D("25000.00")
    from datetime import datetime
    cierre = m.Cierre(servicio_id=servicio_id, contrato_id=contrato.id,
                      abierto_en=datetime(2029, 10, 1, 9),
                      limite_consultor=datetime(2029, 10, 2, 9),
                      estatus=m.EstatusCierre.SIN_VISTO_BUENO)
    db.add(cierre)
    db.commit()
    factura = cierre_mes.armar_factura(db, cierre)
    conceptos = [(c["tipo"], c["cantidad"], c["precio"], c["importe"])
                 for c in factura["conceptos"]]
    assert conceptos[:2] == [("mes_parcial", 5, "5000.00", "25000.00"),
                             ("dias_adicionales", 1, "3000.00", "3000.00")]
    resumen = motor_implantado.resumen_mensual(db, contrato.id)
    assert resumen["facturacion"]["total"] == D("28000.00")
    assert resumen["dias_del_mensual"] == 22


# ---------------------------------------------------------------- el pdf y Catalogos

@pytest.mark.parametrize("idioma,titulo,frase", [
    ("es", "PROPUESTA", "Cuando apliquen, se cobran aparte cada mes"),
    ("en", "PROPOSAL", "When applicable, charged separately each month"),
    ("pt", "PROPOSTA", "Quando se aplicarem, cobrados à parte a cada mês"),
])
def test_el_pdf_en_su_idioma(cliente, sesion, datos, db, idioma, titulo, frase):
    p = _crear(cliente, sesion, _siemens(datos, idioma=idioma))
    html = propuesta_pdf.html_de(db, db.get(m.Cotizacion, p["id"]))
    assert titulo in html and frase in html
    assert "EP/PRO-0001" in html
    assert "$3,118.18" in html and "$137,576.00" in html
    r = cliente.get(f"/cotizaciones/propuesta/{p['id']}/pdf",
                    headers=sesion("consultor"))
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_el_pdf_con_viaticos_incluidos_no_dice_comprobados(cliente, sesion,
                                                           datos, db, lista):
    p = _crear(cliente, sesion, _cuerpo(datos, viaticos="incluidos"))
    html = propuesta_pdf.html_de(db, db.get(m.Cotizacion, p["id"]))
    assert "según lo comprobado" not in html
    assert "Van incluidos en el mensual" in html
    assert "Los gastos de operación del servicio" in html


def test_los_textos_de_la_propuesta_en_catalogos(cliente, sesion, datos):
    mx = datos["mx"]["id"]
    leidos = cliente.get(f"/cotizaciones/propuesta/textos?pais_id={mx}",
                         headers=sesion("consultor")).json()
    assert leidos["textos"]["pro_incluye"]["es"].startswith("Personal de seguridad")
    alcance = next(a for a in leidos["alcances"]
                   if a["codigo"] == "conductor_seguridad")
    assert alcance["textos"]["es"].startswith("El servicio de conductor")
    cuerpo = {"textos": {"pro_cliente": {"es": "Dar el itinerario a tiempo."}},
              "alcances": {"agente_seguridad": {"es": "El agente cuida."}}}
    assert cliente.put(f"/cotizaciones/propuesta/textos/{mx}", json=cuerpo,
                       headers=sesion("consultor")).status_code == 403
    r = cliente.put(f"/cotizaciones/propuesta/textos/{mx}", json=cuerpo,
                    headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    assert r.json()["textos"]["pro_cliente"]["es"] == "Dar el itinerario a tiempo."
    agente = next(a for a in r.json()["alcances"]
                  if a["codigo"] == "agente_seguridad")
    assert agente["textos"]["es"] == "El agente cuida."
    assert cliente.put(f"/cotizaciones/propuesta/textos/{mx}",
                       json={"textos": {"otra": {"es": "x"}}},
                       headers=sesion("diroperaciones")).status_code == 400


def test_la_semilla_y_la_migracion_dicen_lo_mismo():
    import importlib.util
    import pathlib

    ruta = (pathlib.Path(__file__).resolve().parents[1] / "migrations"
            / "versions" / "b8e1d4f6a9c3_propuesta_implantado.py")
    spec = importlib.util.spec_from_file_location("migracion_115", ruta)
    migracion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracion)
    assert migracion.TEXTOS_MEXICO == motor.TEXTOS_MEXICO


def test_quien_puede_que(cliente, sesion, datos, lista):
    p = _crear(cliente, sesion, _cuerpo(datos))
    # Sistema y calidad la ve y no la arma.
    from app.db import SessionLocal
    with SessionLocal() as db:
        assert db.query(m.Cotizacion).count() == 1
    assert cliente.get(f"/cotizaciones/propuesta/{p['id']}",
                       headers=sesion("central")).status_code == 403
    assert cliente.post("/cotizaciones/propuesta", json=_cuerpo(datos),
                        headers=sesion("finanzas")).status_code == 403

# -*- coding: utf-8 -*-
"""Seccion 129: la ola 3 de la revision del 2 de octubre, los detalles.

Los textos y botones chicos de cada proceso: el monto fijo sin monto, la
moneda por version, el servicio que nace sin consultor, la coma decimal
de Brasil, el aviso del IVA, el idioma de los renglones, la lada doble,
la recontratacion, los detalles de tarifarios, el filtro «De baja», los
motivos en mayusculas, «Apto», el plazo vencido sin faltar nada, el
manual de nomina, la urgencia huerfana, el historial del expediente, las
fotos «comprobante.jpg», el tope de 20 MB, Gastos para el gerente, la
vuelta de cinco minutos aislada y las variables del servidor.
"""
import os
from datetime import date

import pytest

from app import models as m
from test_cotizaciones_cliente import _autorizar, _crear, _cuerpo, _enviar
from test_cotizaciones_cliente import cliente_de_odoo  # noqa: F401  (fixture)
from test_odoo_personal import DOMINIO, ODOO0, OdooFalso, empleado, leer
from test_odoo_personal import sin_rastro  # noqa: F401  (fixture)
from test_zona_horaria import brasil  # noqa: F401  (fixture)
from test_revision_111_freelance import (_alta as _alta_freelance, _cargar,
                                         _completar, _costos,
                                         _servicio as _eventual)
from test_revision_111_freelance import nuevos  # noqa: F401  (fixture)

WEB = os.path.join(os.path.dirname(__file__), "..", "app", "web")


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


# ============================== r1-05 · «monto fijo» sin monto en la cotizacion

def test_el_monto_fijo_sin_monto_se_queda_fijo_y_reclama_el_monto(
        cliente, sesion, datos):
    """El consultor marca «Monto fijo» y guarda antes de escribir el
    monto: el borrador se queda en monto fijo --antes volvia a «dentro
    del precio»-- y lo que falta es el monto, que mandarla reclama."""
    h = sesion("consultor")
    c = _crear(cliente, sesion, datos, gastos="fijo", monto_gastos=None)
    assert c["gastos"] == "fijo" and c["monto_gastos"] is None
    assert "El monto fijo de gastos" in c["faltan"]
    assert all(l["tipo"] != "paquete" for l in c["lineas"])
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/enviar", headers=h)
    assert r.status_code == 400, r.text
    assert "El monto fijo de gastos" in r.json()["detail"]["faltan"]

    r = cliente.put(f"/cotizaciones/eventual/{c['id']}",
                    json=_cuerpo(datos, gastos="fijo", monto_gastos="1900"),
                    headers=h)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["gastos"] == "fijo" and c["monto_gastos"] == 1900
    assert "El monto fijo de gastos" not in c["faltan"]
    r = cliente.get(f"/cotizaciones/eventual/{c['id']}", headers=h)
    assert r.json()["gastos"] == "fijo" and r.json()["monto_gastos"] == 1900
    # La pantalla manda «fijo» tal cual, sin cambiarlo a «dentro».
    pantalla = _js("cotizaciones.js")
    assert 'gastos: e.gastos || "comprobar"' in pantalla
    assert '? "dentro" : (e.gastos' not in pantalla


# ====================================== r1-07 · la moneda de cada version

def test_cada_version_dice_su_moneda(cliente, sesion, datos, db):
    """La V1 se mando en una moneda; la V2 cambia de lista. La tabla de
    versiones pinta cada total con la moneda de su version, no con la
    de la que se esta viendo."""
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    h = sesion("consultor")
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/version", headers=h)
    assert r.status_code in (200, 201), r.text
    v2 = r.json()
    db.expire_all()
    # La V1 se queda en dolares, como si la lista de entonces lo fuera.
    db.get(m.Cotizacion, c["id"]).moneda = m.Moneda.USD
    db.commit()
    d = cliente.get(f"/cotizaciones/eventual/{v2['id']}", headers=h).json()
    monedas = {v["version"]: v["moneda"] for v in d["versiones"]}
    assert monedas == {1: "USD", 2: d["moneda"]}
    assert "dinero(v.total, v.moneda || d.moneda)" in _js("cotizaciones.js")


# ================================ r1-duda5 · el servicio que nace sin consultor

def test_si_quien_firmo_perdio_su_acceso_el_servicio_nace_sin_consultor_y_se_dice(
        cliente, sesion, datos, cliente_de_odoo):
    """Beatriz firma la cotizacion; antes de que el cliente la autorice
    se le cierra el acceso. El servicio nace sin titular y la respuesta
    lo dice, para que alguien lo asigne; antes nadie lo veia hasta que
    faltara en la cartera."""
    from test_accesos import _id_de
    beatriz = datos["personal"]["Beatriz Roman"]["id"]
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos,
                                        consultor_id=beatriz))
    uid = _id_de(cliente, sesion, "beatriz.roman@centauro.lat")
    admin = sesion("admin")
    try:
        assert cliente.post(f"/auth/usuarios/{uid}/desactivar",
                            json={"motivo": "Dejo la empresa"},
                            headers=admin).status_code == 200
        r = _autorizar(cliente, sesion, c)
        assert r.status_code == 200, r.text
        assert r.json()["sin_consultor"] is True
        assert "sin consultor titular" in r.json()["aviso"]
    finally:
        cliente.post(f"/auth/usuarios/{uid}/reactivar", json={}, headers=admin)
    pantalla = _js("cotizaciones.js")
    assert pantalla.count('if (r.sin_consultor) mensaje(t("ctz_nacio_sin_consultor"), "alerta");') == 2
    assert _js("idioma.js").count("    ctz_nacio_sin_consultor:") == 3


# ============================= r2-05 · la coma decimal de Brasil en la propuesta

def test_el_precio_escrito_se_lee_en_el_formato_de_la_moneda():
    """«17.500,00» en reales es 17500; «17,500.00» en pesos tambien. Con
    los dos separadores manda el ultimo. Antes la coma de Brasil dejaba el
    precio vacio sin decir nada."""
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("sin node")
    fuente = _js("propuesta.js")
    inicio = fuente.index("export function montoEscrito")
    fin = fuente.index("/* El precio sugerido")
    codigo = fuente[inicio:fin].replace("export function", "function")
    casos = [("17.500,00", "BRL", 17500), ("16855,50", "BRL", 16855.5),
             ("17.500", "BRL", 17500), ("1,5", "BRL", 1.5),
             ("17,500.00", "MXN", 17500), ("17500", "MXN", 17500),
             ("17,500", "USD", 17500), ("1234.5", "MXN", 1234.5),
             ("", "BRL", None), ("abc", "MXN", None),
             ("R$ 1.234,56", "BRL", 1234.56)]
    programa = codigo + "\nconst casos = " + __import__("json").dumps(
        [[t, mo] for t, mo, _ in casos]) + ";\n" + \
        "console.log(JSON.stringify(casos.map(([t, mo]) => montoEscrito(t, mo))));"
    salida = subprocess.run(["node", "-e", programa], capture_output=True,
                            text=True, check=True).stdout
    assert __import__("json").loads(salida) == [esperado for _, _, esperado in casos]
    assert "precio_mes: montoEscrito(p.precio_mes, moneda)" in fuente
    assert "precio_hora_extra: montoEscrito(e.precio_hora_extra, moneda)" in fuente
    assert "sinMiles(x.lista_precio_mes, moneda)" in fuente


# ============================= r2-07 · el aviso del IVA en la propuesta sin IVA

def test_sin_iva_no_se_pide_la_tasa_de_iva(db, datos):
    """La propuesta que va sin IVA no avisa que falta la tasa: su PDF no
    la usa. Con IVA, si falta, se dice."""
    from types import SimpleNamespace
    from app import cotizacion_cliente as cc
    from app import propuesta
    pais = db.get(m.Pais, datos["mx"]["id"])
    d = cc.datos_del_pais(db, pais.id)
    antes = d.tasa_iva
    d.tasa_iva = None
    db.commit()
    try:
        sin = propuesta.faltan_textos(db, pais.id, "es", SimpleNamespace(con_iva=False))
        con = propuesta.faltan_textos(db, pais.id, "es", SimpleNamespace(con_iva=True))
        assert "tasa_iva" not in sin and "tasa_iva" in con
        assert "tasa_iva" not in cc.faltan_textos(db, pais.id, "es", con_iva=False)
        assert "tasa_iva" in cc.faltan_textos(db, pais.id, "es")
    finally:
        d = cc.datos_del_pais(db, pais.id)
        d.tasa_iva = antes
        db.commit()


# ============================= r3-09 · el idioma de los renglones de la factura

def test_sin_idioma_en_la_cotizacion_los_renglones_van_en_el_del_pais(
        cliente, sesion, datos, db, brasil):
    """Un servicio de Brasil cotizado desde el servicio, o un mes abierto
    sin propuesta: sus renglones salen en portugues, no en espanol."""
    from ayudas import crear_servicio, jornada, manana
    from app import odoo_facturacion as of
    h = sesion("consultor")
    br = crear_servicio(cliente, h, datos,
                        [jornada(manana(300), datos["modalidades"]["full_day"]["id"])],
                        pais_id=brasil["pais"]["id"], plaza_id=brasil["plaza"]["id"])
    mx = crear_servicio(cliente, h, datos,
                        [jornada(manana(301), datos["modalidades"]["full_day"]["id"])])
    sbr, smx = db.get(m.Servicio, br["id"]), db.get(m.Servicio, mx["id"])
    assert of.idioma_de_la_factura(db, sbr, None) == "pt"
    assert of.idioma_de_la_factura(db, smx, None) == "es"
    assert of.idioma_de_la_factura(db, sbr, "en") == "en"
    assert of.idioma_de_la_factura(db, sbr, "xx") == "pt"


# ==================================================== r4-06 · la lada doble

def test_el_celular_que_ya_trae_la_lada_sin_mas_solo_recibe_el_mas():
    """«55 11 98765 4321» en Brasil es +55 11 98765 4321, no «+55 55 11…»;
    «52 55 1234 5678» en Mexico, +52 55 1234 5678. Un numero de diez
    digitos que empiece con la lada sigue siendo nacional."""
    from app.telefonos import con_lada
    assert con_lada("55 11 98765 4321", "+55") == "+55 11 98765 4321"
    assert con_lada("52 55 1234 5678", "+52") == "+52 55 1234 5678"
    assert con_lada("55 1234 5678", "+52") == "+52 55 1234 5678"
    assert con_lada("11 98765 4321", "+55") == "+55 11 98765 4321"
    # El DDD 55 de Brasil, con sus once digitos, es nacional.
    assert con_lada("55 99999 8888", "+55") == "+55 55 99999 8888"
    assert con_lada("+52 55 1234 5678", "+52") == "+52 55 1234 5678"
    assert con_lada("911", "+52") == "911"


# ====================================== r4-07 · la recontratacion por Odoo

def test_el_recontratado_queda_pendiente_y_dice_que_se_desarchiva_en_odoo(
        cliente, sesion, datos, db):
    """Quien se fue vuelve con un empleado nuevo en Odoo y el mismo
    correo: su persona de Centauro sigue ligada al empleado anterior,
    dado de baja. El pendiente dice la salida --desarchivar al anterior
    en Odoo-- en vez de quedarse para siempre sin decir por que."""
    from app.odoo_personal_reglas import RECONTRATADO
    h = sesion("admin")
    r = cliente.post("/catalogos/personal", headers=h, json={
        "nombre": "Volvio A La Empresa", "correo": f"agente1@{DOMINIO}",
        "plaza_id": datos["cdmx"]["id"]})
    assert r.status_code == 201, r.text
    persona = db.get(m.Persona, r.json()["id"])
    persona.odoo_id = ODOO0 + 900
    persona.activo = False
    db.commit()
    informe = leer(db, OdooFalso(empleado(1)))
    assert informe["altas"] == [] and informe["vinculadas"] == []
    assert [(p["persona_id"], p["falta"]) for p in informe["pendientes"]] == [
        (persona.id, [RECONTRATADO])]
    assert "desarchiva al empleado anterior" in RECONTRATADO
    assert RECONTRATADO in _js("odoo.js")
    assert _js("idioma.js").count("    odo_f_recontratado:") == 3
    # Activo y ligado a otro empleado: es otra persona, como antes.
    db.expire_all()
    db.get(m.Persona, persona.id).activo = True
    db.commit()
    informe = leer(db, OdooFalso(empleado(1)))
    assert [p["falta"] for p in informe["pendientes"]] == [
        ["su correo ya es de otra persona en Centauro"]]


# ======================================= r5-06 a r5-09 · detalles de tarifarios

def test_el_producto_de_hora_extra_que_solo_nombra_un_paquete_cuenta(db, datos):
    """La «Hora Extra Motorista + Minivan» de Amazon Brasil solo la nombra
    su paquete: archivada en Odoo, se quedaba fuera de la tabla con el
    tarifario todavia usandola."""
    from app import odoo_tarifarios
    producto = m.ProductoOdoo(odoo_id=777001, nombre="Hora Extra Motorista + Minivan")
    db.add(producto)
    db.flush()
    cliente = db.get(m.Cliente, datos["cliente_id"])
    paquete = m.TarifaPaquete(
        tarifario_id=cliente.tarifario_id,
        perfil_id=datos["perfiles"]["conductor_seguridad"]["id"],
        categoria_id=datos["categorias"]["suv_blindada"]["id"],
        modalidad_id=datos["modalidades"]["full_day"]["id"], precio=100,
        origen="odoo", producto_hora_extra_id=producto.id)
    db.add(paquete)
    db.flush()
    try:
        assert odoo_tarifarios._nombrados(db, producto.id) is True
        db.delete(paquete)
        db.flush()
        assert odoo_tarifarios._nombrados(db, producto.id) is False
    finally:
        db.rollback()


def test_el_pais_sin_par_no_ensena_el_dolar_a_peso(db, monkeypatch):
    """Junto a la lista en dolares de un pais sin tipo de cambio propio no
    sale el dolar a peso como si fuera suyo."""
    from app import tipo_cambio
    from app.routers.tarifarios import _cambio_del_pais
    assert _cambio_del_pais(db, 1)["moneda_local"] == "MXN"
    monkeypatch.setattr(tipo_cambio, "local_del_pais", lambda db_, pais_id: m.Moneda.VES)
    assert _cambio_del_pais(db, 1) is None
    monkeypatch.setattr(tipo_cambio, "local_del_pais", lambda db_, pais_id: m.Moneda.BRL)
    assert _cambio_del_pais(db, 2)["moneda_local"] == "BRL"
    assert "if (!tc || tar.moneda !== tc.moneda) return null;" in _js("tarifarios.js")


def test_los_paquetes_de_una_lista_se_guardan_en_un_orden_fijo(db, datos):
    """Venga como venga de Odoo, los paquetes se guardan en el mismo orden:
    el cierre toma «el primero» cuando un rol cabe en dos el mismo dia."""
    from app import odoo_tarifarios
    from app import odoo_tarifarios_reglas as reglas
    modalidades = odoo_tarifarios._modalidades(db)
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    suv, cuv = datos["categorias"]["suv_blindada"]["id"], datos["categorias"]["cuv"]["id"]

    def precios(orden):
        salida = {}
        for categoria, producto in orden:
            salida[(reglas.PAQUETE, conductor, categoria, "full_day")] = {
                "precio": 100, "origen": "odoo", "producto_id": producto}
        return salida
    _, _, a, _, _ = odoo_tarifarios._filas_de(precios([(cuv, 9002), (suv, 9001)]), 1, modalidades)
    _, _, b, _, _ = odoo_tarifarios._filas_de(precios([(suv, 9001), (cuv, 9002)]), 1, modalidades)
    assert [p["producto_odoo_id"] for p in a] == [9001, 9002]
    assert a == b


def test_sin_la_categoria_la_vuelta_queda_anotada(db, monkeypatch):
    """Si «Proteccion Ejecutiva» desaparece de Odoo, la lectura de cada
    hora no calla: deja su renglon en el historial, con el pendiente."""
    from test_odoo_tarifarios import OdooFalso, con_filtros, leer, mundo_pe
    con_filtros(monkeypatch, categoria="Seguridad privada")
    antes = db.query(m.SincronizacionOdoo).filter_by(tipo="tarifarios").count()
    informe = leer(db, OdooFalso(mundo_pe()), automatica=True)
    assert informe["sin_categoria"] == "Seguridad privada"
    assert informe["pendientes"][0]["tipo"] == "sin_categoria_pais"
    db.expire_all()
    filas = (db.query(m.SincronizacionOdoo).filter_by(tipo="tarifarios")
             .order_by(m.SincronizacionOdoo.id.desc()).all())
    assert len(filas) == antes + 1
    assert filas[0].pendientes == 1 and filas[0].automatica is True
    assert "Seguridad privada" in (filas[0].detalle or "")


# ==================================================== r6-07 · el filtro «De baja»

def test_la_lista_trae_a_los_dados_de_baja_con_su_filtro(
        cliente, sesion, datos, nuevos):
    """Dan de baja a Mario por error: con el filtro «Dados de baja» se le
    encuentra para reactivarlo; sin el filtro no sale."""
    h = sesion("consultor")
    persona_id = _alta_freelance(cliente, h, datos, nuevos)
    assert cliente.post(f"/freelance/{persona_id}/baja",
                        json={"motivo": "Fue un error de captura"},
                        headers=h).status_code == 200
    sin = cliente.get(f"/freelance?pais_id={datos['mx']['id']}", headers=h).json()
    assert all(f["persona_id"] != persona_id for f in sin)
    con = cliente.get(f"/freelance?pais_id={datos['mx']['id']}&incluir_bajas=true",
                      headers=h).json()
    suyo = next(f for f in con if f["persona_id"] == persona_id)
    assert suyo["activo"] is False
    pantalla = _js("freelance.js")
    assert '"de_baja"' in pantalla and "incluir_bajas=true" in pantalla
    assert 'if (filtroEstado === "de_baja") return !f.activo' in pantalla
    assert _js("idioma.js").count("    fre_filtro_de_baja:") == 3


# ================================== r6-08 y r6-09 · los textos del freelance

def test_los_motivos_van_crudos_el_folio_en_mayusculas_y_apto_se_dice():
    pantalla = _js("freelance.js")
    for campo in ("motivo_baja", "motivo_rechazo", "motivo_urgencia"):
        inicio = pantalla.index(f'name: "{campo}"')
        assert '"data-crudo": ""' in pantalla[inicio:inicio + 160], campo
    inicio = pantalla.index('name: "notas"')
    assert '"data-crudo": ""' in pantalla[inicio:inicio + 60]
    inicio = pantalla.index('name: "servicio", placeholder: "EP/E-031"')
    assert '"data-mayusculas": ""' in pantalla[inicio:inicio + 120]
    assert 'const RESULTADO = { apto: "fre_apto", no_apto: "fre_no_apto"' in pantalla
    assert "t(RESULTADO[x.resultado] || `fre_res_${x.resultado}`)" in pantalla


# ======================= r6-10 · pasa a programado venga de donde venga el cambio

def test_el_de_emergencia_pasa_a_programado_cuando_el_catalogo_deja_de_pedir(
        cliente, sesion, datos, nuevos, db):
    """A Mario (emergencia) solo le falta lo de programado; sistema y
    calidad quita esos requisitos del catalogo. Ya no le falta nada: pasa
    a programado sin que nadie valide un documento. Antes se quedaba en
    «plazo vencido» sin faltarle nada."""
    h = sesion("consultor")
    persona_id = _alta_freelance(cliente, h, datos, nuevos, tipo="emergencia")
    _costos(cliente, sesion, persona_id)
    exp = _completar(cliente, sesion, persona_id)
    assert exp["resumen"]["estado"] == "listo"
    assert exp["resumen"]["para_programado"]["faltan"]
    solo_programado = (db.query(m.RequisitoFreelance)
                       .filter_by(pais_id=datos["mx"]["id"], activo=True,
                                  programado=True, emergencia=False).all())
    assert solo_programado
    ids = [r.id for r in solo_programado]
    try:
        for r in solo_programado:
            r.activo = False
        db.commit()
        ficha = cliente.get(f"/freelance/{persona_id}", headers=h).json()
        assert ficha["tipo"] == "programado"
        assert ficha["expediente"]["estado"] == "listo"
        db.expire_all()
        suya = db.query(m.Freelance).filter_by(persona_id=persona_id).one()
        assert suya.tipo == "programado" and suya.plazo_programado is None
    finally:
        db.expire_all()
        for r in db.query(m.RequisitoFreelance).filter(m.RequisitoFreelance.id.in_(ids)):
            r.activo = True
        db.commit()


# ================================ r6-11 · el manual y el mensaje de nomina

def test_la_tarifa_del_freelance_se_busca_en_su_ficha():
    from app import nomina
    import inspect
    assert "del freelance, en su ficha" in inspect.getsource(nomina)
    idioma = _js("idioma.js")
    for clave in ("nom_no_salio", "nom_borrador_no_cerro", "nom_borrador_sin_tarifa"):
        assert idioma.count(f"    {clave}:") == 3
        inicio = idioma.index(f"    {clave}:")
        assert "freelance" in idioma[inicio:inicio + 400], clave
    manual = open(os.path.join(os.path.dirname(__file__), "..", "manual", "es",
                               "530_nomina.md"), encoding="utf-8").read()
    assert "Tarifas de freelance" not in manual
    assert "Personal de seguridad → Freelance" in manual


# ===================== r6-12 · la urgencia huerfana y la respuesta al que pidio

def test_la_urgencia_del_servicio_cancelado_sale_de_la_bandeja_y_la_respuesta_llega(
        cliente, sesion, datos, nuevos, db):
    h = sesion("consultor")
    persona_id = _alta_freelance(cliente, h, datos, nuevos)
    _costos(cliente, sesion, persona_id)
    servicio = _eventual(cliente, sesion, datos, desde=140)
    otro = _eventual(cliente, sesion, datos, desde=141)
    for sv in (servicio, otro):
        r = cliente.post(f"/freelance/{persona_id}/urgencias", json={
            "servicio_id": sv["id"],
            "motivo": "El conductor de planta se enfermo y no hay otro"}, headers=h)
        assert r.status_code == 201, r.text
    # El cliente cancela el primero esa tarde.
    assert cliente.post(f"/servicios/{servicio['id']}/cancelar", headers=h,
                        json={"motivo": "El cliente cancelo el viaje"}).status_code == 200
    bandeja = cliente.get("/direccion/bandeja", headers=sesion("diroperaciones")).json()
    folios = [x["folio"] for x in bandeja["freelance_por_autorizar"]
              if x["persona_id"] == persona_id]
    assert folios == [otro["folio"]]

    # Direccion contesta la que sigue viva: al que la pidio le llega.
    pendiente = next(x for x in bandeja["freelance_por_autorizar"]
                     if x["persona_id"] == persona_id)
    r = cliente.post(f"/freelance/urgencias/{pendiente['id']}/autorizar",
                     json={"respuesta": "Solo este servicio"},
                     headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    aviso = (db.query(m.Notificacion)
             .filter(m.Notificacion.correo == "ana.solis@centauro.lat")
             .order_by(m.Notificacion.id.desc()).first())
    assert aviso is not None
    assert "autorizado para" in aviso.asunto and otro["folio"] in aviso.asunto
    assert "Solo este servicio" in aviso.cuerpo
    assert aviso.enlace_seguimiento == f"/consola/#/servicio/{otro['id']}"


# ============================ r6-13 · el historial del expediente, por quien lo ve

def test_el_historial_del_expediente_solo_lo_ve_quien_ve_el_expediente(
        cliente, sesion, datos, nuevos):
    h = sesion("consultor")
    persona_id = _alta_freelance(cliente, h, datos, nuevos)
    rh = sesion("rrhh")
    exp = cliente.get(f"/freelance/{persona_id}/expediente", headers=rh).json()
    req = next(r for r in exp["requisitos"] if r["captura"] == "archivo")
    assert _cargar(cliente, rh, persona_id, req, date.today()).status_code == 201
    de_rh = cliente.get(f"/freelance/{persona_id}", headers=rh).json()["historial"]
    assert "documento cargado" in {x["accion"] for x in de_rh}
    de_la_central = cliente.get(f"/freelance/{persona_id}",
                                headers=sesion("central")).json()["historial"]
    acciones = {x["accion"] for x in de_la_central}
    assert "alta" in acciones
    assert not acciones & {"documento cargado", "documento validado",
                           "documento rechazado"}


# ==================== r6-14, r6-duda12 y r7-06 · fotos, avisos sin nadie, 20 MB

def test_la_foto_reducida_conserva_su_nombre():
    util = _js("util.js")
    assert 'const nombre = ((archivo && archivo.name) || "comprobante")' in util
    assert 'new File([b], nombre, { type: "image/jpeg" })' in util


def test_sin_nadie_a_quien_avisar_no_se_marca_nada_como_avisado(db, monkeypatch):
    from app import freelance
    monkeypatch.setattr(freelance, "_de_rrhh", lambda db_: [])
    r = freelance.revisar_vencimientos(db)
    assert r["avisados"] == 0 and "omitido" in r


def test_los_archivos_que_pasan_de_20_mb_se_dicen_antes_de_mandarlos():
    pantalla = _js("freelance.js")
    assert "const TOPE_PETICION = 20 * 1024 * 1024 - 64 * 1024;" in pantalla
    assert "if (peso > TOPE_PETICION)" in pantalla
    assert 'if (codigo === 413 && !(d && d.mensaje)) return ErrorApi.texto("api_413");' in _js("api.js")
    idioma = _js("idioma.js")
    assert idioma.count("    api_413:") == 3 and idioma.count("    fre_pasan_de_20mb:") == 3


# ================================= r7-04 · el telefono robado y el contador

def test_la_huella_rechazada_dice_la_salida_y_la_pantalla_dice_lo_del_robo(
        cliente, sesion):
    from test_llaves import Telefono, _activar, _entrar
    from test_llaves import sin_llaves  # noqa: F401
    tel = Telefono()
    _activar(cliente, sesion, "consultor", tel)
    tel.contador = 5
    r, _ = _entrar(cliente, tel)
    assert r.status_code == 200
    # El telefono restauro un respaldo: su contador regreso.
    tel.contador = 1
    r, _ = _entrar(cliente, tel)
    assert r.status_code == 401, r.text
    assert r.json()["detail"]["codigo"] == "huella_rechazada"
    assert "quita la huella" in r.json()["detail"]["que_hacer"]
    idioma = _js("idioma.js")
    inicio = idioma.index("    hue_pie:")
    assert "contraseña nueva" in idioma[inicio:inicio + 500]
    manual = open(os.path.join(os.path.dirname(__file__), "..", "manual", "es",
                               "06_accesos.md"), encoding="utf-8").read()
    assert "Si le roban o pierde un equipo" in manual


# ============================== r8-06 · Gastos para quien no deposita

def test_gastos_en_modo_consulta_para_quien_no_transfiere():
    pantalla = _js("finanzas.js")
    assert 'if (!tiene(sesion.usuario, "viaticos.transferir")) {' in pantalla
    assert 'main.classList.add("solo-consulta");' in pantalla
    assert '+ " pestana"' in pantalla
    assert pantalla.count("consulta-si") >= 2
    assert _js("idioma.js").count("    fin_consulta:") == 3


# ====================== r8-07 y r9-05 · la vuelta de cinco minutos, aislada

def test_un_paso_que_revienta_no_detiene_a_los_demas(monkeypatch):
    from app import celery_app, cierre, entregas

    def revienta(db):
        raise RuntimeError("un cierre con datos raros")
    corrio = []
    monkeypatch.setattr(cierre, "avanzar_cierres", revienta)
    monkeypatch.setattr(entregas, "avisar_vencidas",
                        lambda db: corrio.append("entregas") or [])
    salida = celery_app.avanzar_cierres()
    assert corrio == ["entregas"]
    assert "movidos" not in salida and salida["entregas_vencidas"] == []
    assert "un cierre con datos raros" in salida["fallas"]["movidos"]


# ============================= r9-06 · las variables nuevas del servidor

def test_el_env_nuevo_trae_las_variables_de_odoo_por_pais():
    import importlib.util
    ruta = os.path.join(os.path.dirname(__file__), "..", "..", "despliegue", "crear_env.py")
    spec = importlib.util.spec_from_file_location("crear_env", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    texto = modulo.plantilla("pg", "rd", "sk")
    for variable in ("ODOO_FACTURACION_API_KEY=", "ODOO_CATEGORIA_PRODUCTOS=",
                     "ODOO_PREFIJO_LISTAS_BR=", "ODOO_IDIOMA_BR=", "ODOO_CAMPO_CNH=",
                     "ODOO_PRODUCTO_GASTOS=", "PEGASUS_GRUPOS=", "ARCHIVO_DESTINO=",
                     "EXPEDIENTES_DESTINO="):
        assert variable in texto, variable
    leeme = open(os.path.join(os.path.dirname(__file__), "..", "..", "despliegue",
                              "LEEME.md"), encoding="utf-8").read()
    assert "ODOO_CATEGORIA_PRODUCTOS_BR=" in leeme and "PEGASUS_GRUPOS=" in leeme

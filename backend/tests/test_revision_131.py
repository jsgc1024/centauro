# -*- coding: utf-8 -*-
"""Seccion 131: la ola 4b de la revision del 2 de octubre (decisiones 1,
2, 9, 10, 11, 13, 16 y 19 de Salvador, el «Eliminar» del implantado y lo
que pidio el 3 de octubre para Accesos).

  * «Descartar este borrador»: la V2 se borra y la anterior vuelve a ser
    la ultima; la V1 que nunca se mando se elimina con registro y su
    folio no se vuelve a usar (decision 1).
  * La propuesta cuyo implantado se elimino: «Volver a crear el
    implantado» y «Eliminar la propuesta» (decision 2).
  * «N dias ya pasaron» antes de autorizar o recrear (decision 11).
  * «Regresar» sobre lo aprobado mientras no tenga factura ni prefactura
    timbrada; la comision se cancela y renace; la que ya quedo en un
    corte se queda (decision 9).
  * El mes a precio fijo sin dias trabajados se cobra en cero y el
    visto bueno lo dice; justificado como costo fijo, se cobra el
    mensual (decision 10).
  * El cierre respeta el precio cotizado en lo que la lista toma en
    gris; lo no cotizado va con el precio de hoy (decision 13).
  * La cotizacion que otro manda con la firma del titular: el titular
    recibe el aviso con el PDF (decision 16).
  * El panel de direccion de operaciones con las comisiones por firmar,
    las malas calificaciones y los cierres por firmar (decision 19).
  * Accesos: quienes ya entraron y quienes no, y por pais.
"""
import os
from datetime import date, datetime, timedelta
from decimal import Decimal as D

from app import cierre as motor_cierre
from app import cierre_mes, cotizacion_cliente, reloj, revisor
from app import models as m
from app.db import SessionLocal
from test_cotizaciones_cliente import (_crear, _enviar,  # noqa: F401
                                       cliente_de_odoo, db)
from test_odoo_facturacion import _eventual, con_productos  # noqa: F401
from test_prefactura_odoo import (_bandeja, _cierre, _cierre_del_mes,  # noqa: F401
                                  _implantado, _visto_bueno, lista_de_odoo,
                                  odoo)

WEB = os.path.join(os.path.dirname(__file__), "..", "app", "web")


def _js(nombre: str) -> str:
    return open(os.path.join(WEB, nombre), encoding="utf-8").read()


def _idioma_tiene(*claves) -> None:
    """Cada clave, en los tres idiomas."""
    js = _js("idioma.js")
    for clave in claves:
        assert js.count(f"\n    {clave}: ") == 3, clave


# ======================================= decision 1 · descartar un borrador

def test_descartar_la_v2_devuelve_la_v1_y_la_v1_nunca_mandada_se_elimina(
        cliente, sesion, datos, db):
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    v2 = cliente.post(f"/cotizaciones/eventual/{c['id']}/version",
                      headers=sesion("consultor")).json()
    assert v2["version"] == 2 and v2["estatus"] == "borrador"
    # La V1 mandada ya no es la ultima: no se descarta.
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/descartar",
                     headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    r = cliente.post(f"/cotizaciones/eventual/{v2['id']}/descartar",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["resultado"] == "borrador descartado"
    assert r.json()["vuelve"] == {"id": c["id"], "version": 1,
                                  "estatus": "enviada"}
    assert r.json()["eliminada"] is False
    db.expire_all()
    assert db.get(m.Cotizacion, v2["id"]) is None
    assert db.get(m.Cotizacion, c["id"]).estatus == m.EstatusCotizacion.ENVIADA
    assert (cotizacion_cliente.ultima(db, db.get(m.Cotizacion, c["id"]).folio,
                                      "cotizacion").id == c["id"])

    # La V1 que nunca se mando: se elimina con registro y su folio se
    # quema.
    sola = _crear(cliente, sesion, datos)
    r = cliente.post(f"/cotizaciones/eventual/{sola['id']}/descartar",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["vuelve"] is None and r.json()["eliminada"] is True
    db.expire_all()
    assert db.get(m.Cotizacion, sola["id"]) is None
    quemada = (db.query(m.CotizacionEliminada)
               .filter_by(clase="cotizacion",
                          folio=int(sola["folio"].split("-")[-1]))
               .first())
    assert quemada is not None and "borrador que nunca se mandó" in quemada.resumen
    otra = _crear(cliente, sesion, datos)
    assert otra["folio"] != sola["folio"]
    # Lo mandado no es borrador: no se descarta.
    r = cliente.post(f"/cotizaciones/eventual/{c['id']}/descartar",
                     headers=sesion("consultor"))
    assert r.status_code == 409 and "ya no es borrador" in r.text
    # La pantalla ofrece el boton y pide confirmacion.
    js = _js("cotizaciones.js")
    assert "/descartar" in js and "ctz_seguro_descartar_v" in js
    _idioma_tiene("ctz_descartar", "ctz_seguro_descartar_v",
                  "ctz_seguro_descartar_1", "ctz_descartada_vuelve",
                  "ctz_descartada_eliminada", "pro_seguro_descartar_v",
                  "pro_descartada_eliminada")


# ========================== decision 2 · la propuesta sin implantado

def _eliminar_servicio(cliente, sesion, servicio_id):
    r = cliente.request("DELETE", f"/servicios/{servicio_id}",
                        json={"motivo": "Captura de prueba"},
                        headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


def test_la_propuesta_sin_implantado_se_recrea_o_se_elimina(
        cliente, sesion, datos, db, lista_de_odoo):
    servicio_id, _ = _implantado(cliente, sesion, datos)
    db.expire_all()
    propuesta = (db.query(m.Cotizacion)
                 .filter_by(servicio_id=servicio_id, clase="propuesta").one())
    folio_viejo = db.get(m.Servicio, servicio_id).folio
    _eliminar_servicio(cliente, sesion, servicio_id)
    db.expire_all()
    propuesta = db.get(m.Cotizacion, propuesta.id)
    assert propuesta.servicio_id is None and propuesta.servicio_folio == folio_viejo
    detalle = cliente.get(f"/cotizaciones/propuesta/{propuesta.id}",
                          headers=sesion("consultor")).json()
    assert detalle["se_recrea"] is True
    assert detalle["dias_pasados"] == 0            # arranca en 2029

    # Vuelve a crear: nace otro implantado, con folio nuevo y su primer mes
    # con los terminos de la propuesta.
    r = cliente.post(f"/cotizaciones/propuesta/{propuesta.id}/servicio",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    nuevo = r.json()
    assert nuevo["servicio_id"] != servicio_id and nuevo["folio"] != folio_viejo
    db.expire_all()
    propuesta = db.get(m.Cotizacion, propuesta.id)
    assert propuesta.servicio_id == nuevo["servicio_id"]
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=nuevo["servicio_id"]).first())
    assert acuerdo is not None and str(acuerdo.hora_presentacion)[:5] == "07:00"
    rastro = (db.query(m.RegistroAccion)
              .filter_by(servicio_id=nuevo["servicio_id"],
                         accion="alta desde la propuesta").first())
    assert rastro is not None and "otra vez" in rastro.detalle
    # Su primer mes nace con los terminos de la propuesta, como al
    # autorizar: mes completo con el mensual de los dos puestos.
    r = cliente.post(f"/implantados/{nuevo['servicio_id']}/mes",
                     headers=sesion("consultor"), json={
        "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": datos["suburban"]["id"]}],
        "unidades": [datos["suburban"]["id"]],
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia"})
    assert r.status_code == 201, r.text
    contrato = db.get(m.ContratoImplantado, r.json()["contrato_id"])
    assert contrato.esquema == m.EsquemaCotizacionImplantado.MES_COMPLETO
    assert D(str(contrato.precio_mes_completo)) == D("110000.00")

    # Y la otra salida: eliminar la propuesta, con motivo y folio quemado.
    propuesta_id, folio_propuesta = propuesta.id, propuesta.folio
    _eliminar_servicio(cliente, sesion, nuevo["servicio_id"])
    r = cliente.post(f"/cotizaciones/propuesta/{propuesta_id}/eliminar",
                     json={"motivo": "El cliente ya no quiso"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(m.Cotizacion, propuesta_id) is None
    quemada = (db.query(m.CotizacionEliminada)
               .filter_by(clase="propuesta", folio=folio_propuesta).first())
    assert quemada is not None and quemada.motivo == "El cliente ya no quiso"
    assert "implantado" in quemada.resumen
    js = _js("propuesta.js")
    assert "pro_recrear_implantado" in js and "pro_eliminar_propuesta" in js
    _idioma_tiene("pro_borrado_que_hacer", "pro_recrear_implantado",
                  "pro_seguro_recrear", "pro_eliminar_propuesta",
                  "pro_seguro_eliminar", "pro_eliminada")


# ================================ decision 11 · «N dias ya pasaron»

def test_los_dias_pasados_se_cuentan_antes_de_autorizar(cliente, sesion, datos,
                                                        db):
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    cot = db.get(m.Cotizacion, c["id"])
    assert cotizacion_cliente.dias_pasados(db, cot)["n"] == 0
    hoy = reloj.Relojes(db).hoy(datos["mx"]["id"])
    for i, d in enumerate(sorted(cot.dias, key=lambda x: (x.equipo_clave, x.fecha))[:2]):
        d.fecha = hoy - timedelta(days=3 - i)
    db.commit()
    db.expire_all()
    pasados = cotizacion_cliente.dias_pasados(db, db.get(m.Cotizacion, c["id"]))
    assert pasados["n"] == 2 and pasados["desde"] == str(hoy - timedelta(days=3))
    detalle = cliente.get(f"/cotizaciones/eventual/{c['id']}",
                          headers=sesion("consultor")).json()
    assert detalle["dias_pasados"]["n"] == 2
    js = _js("cotizaciones.js")
    assert "avisoDiasPasados" in js and "ctz_dias_pasados" in js
    assert "avisoInicioPasado" in _js("propuesta.js")
    _idioma_tiene("ctz_dia_pasado", "ctz_dias_pasados", "pro_dia_pasado",
                  "pro_dias_pasados")


# ======================================= decision 9 · regresar lo aprobado

def _aprobar(cliente, sesion, cierre_id):
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    return r.json()


def _comision_de(servicio_id):
    with SessionLocal() as db:
        return (db.query(m.ComisionConsultor)
                .filter_by(servicio_id=servicio_id, contrato_id=None).first())


def test_lo_aprobado_se_regresa_y_la_comision_renace(cliente, sesion, datos,
                                                     con_productos, odoo):
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2400)
    _visto_bueno(cliente, sesion, cierre_id)
    aprobado = _aprobar(cliente, sesion, cierre_id)
    assert aprobado["comision_consultor"]["estatus"] == "generada"
    assert _cierre(cierre_id).estatus == m.EstatusCierre.APROBADO
    with SessionLocal() as db:
        assert (db.get(m.Servicio, servicio["id"]).estatus
                == m.EstatusServicio.CERRADO)
    bandeja = _bandeja(cliente, sesion)
    fila = next(f for f in bandeja["en_odoo"] if f["cierre_id"] == cierre_id)
    assert fila["se_regresa"] is True and fila["aprobado_por"]
    assert fila["comision"]["estatus"] == "generada"
    assert fila["comision"]["en_corte"] is False

    r = cliente.post(f"/cierre/{cierre_id}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "El cliente cancelo el segundo dia"})
    assert r.status_code == 200, r.text
    salida = r.json()
    assert salida["estaba_aprobado"]["por"]
    assert salida["comision_cancelada"]["consultor"] == "Ana Solis"
    assert salida["comision_en_corte"] is None
    assert salida["prefactura_anulada"] == 4821
    c = _cierre(cierre_id)
    assert c.estatus == m.EstatusCierre.DEVUELTO_A_OPERACION
    assert c.aprobado_en is None and c.aprobado_por_id is None
    assert _comision_de(servicio["id"]) is None
    with SessionLocal() as db:
        assert (db.get(m.Servicio, servicio["id"]).estatus
                == m.EstatusServicio.SIN_VISTO_BUENO)
        regreso = (db.query(m.RegistroAccion)
                   .filter_by(servicio_id=servicio["id"],
                              accion="devolver a operacion").one())
        assert "estaba aprobado por" in regreso.detalle
        assert "se cancela y vuelve a nacer" in regreso.detalle
    # El consultor vuelve a dar el visto bueno (la prefactura de antes
    # sigue viva en Odoo: se cancela alla) y finanzas vuelve a aprobar:
    # la comision nace otra vez.
    odoo.facturas[4821]["state"] = "cancel"
    _visto_bueno(cliente, sesion, cierre_id)
    _aprobar(cliente, sesion, cierre_id)
    assert _comision_de(servicio["id"]) is not None
    assert _cierre(cierre_id).estatus == m.EstatusCierre.APROBADO


def test_la_comision_que_ya_entro_a_un_corte_se_queda_al_regresar(
        cliente, sesion, datos, con_productos, odoo):
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2403)
    _visto_bueno(cliente, sesion, cierre_id)
    _aprobar(cliente, sesion, cierre_id)
    with SessionLocal() as db:
        comision = (db.query(m.ComisionConsultor)
                    .filter_by(servicio_id=servicio["id"]).one())
        corte = m.CorteComision(pais_id=datos["mx"]["id"], anio=comision.anio,
                                mes=comision.mes, estatus="autorizado")
        db.add(corte)
        db.flush()
        comision.corte_id = corte.id
        db.commit()
        corte_id, comision_id = corte.id, comision.id
    try:
        r = cliente.post(f"/cierre/{cierre_id}/devolver",
                         headers=sesion("finanzas"),
                         json={"motivo": "Faltaron los gastos de la casetas"})
        assert r.status_code == 200, r.text
        assert r.json()["comision_cancelada"] is None
        assert r.json()["comision_en_corte"]["comision_id"] == comision_id
        with SessionLocal() as db:
            assert db.get(m.ComisionConsultor, comision_id) is not None
            regreso = (db.query(m.RegistroAccion)
                       .filter_by(servicio_id=servicio["id"],
                                  accion="devolver a operacion").one())
            assert "ya quedo en el corte" in regreso.detalle
    finally:
        with SessionLocal() as db:
            db.get(m.ComisionConsultor, comision_id).corte_id = None
            db.delete(db.get(m.CorteComision, corte_id))
            db.commit()


def test_lo_facturado_no_se_regresa_y_la_pantalla_ofrece_regresar(
        cliente, sesion, datos, con_productos, odoo):
    _, cierre_id = _eventual(cliente, sesion, datos, offset=2406)
    _visto_bueno(cliente, sesion, cierre_id)
    _aprobar(cliente, sesion, cierre_id)
    r = cliente.put(f"/cierre/{cierre_id}/factura-de-odoo",
                    json={"folio": "INV/2026/0777", "fecha": str(date.today())},
                    headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert _cierre(cierre_id).estatus == m.EstatusCierre.FACTURADO
    r = cliente.post(f"/cierre/{cierre_id}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "Se cobro de mas el segundo dia"})
    assert r.status_code == 409, r.text
    assert "nota de credito" in r.json()["detail"]["que_hacer"]
    js = _js("facturacion.js")
    assert "botonRegresar" in js and "lineaAprobado" in js
    assert "pieDelRegresoAprobado" in js
    _idioma_tiene("fac_aprobado_por", "fac_marca_com_generada",
                  "fac_marca_com_en_corte", "fac_regresar_corto",
                  "fac_regresar_aprobado_pie", "fac_regresado_comision",
                  "fac_regresado_corte", "fac_sin_cobro")


# ============================ decision 10 · el mes sin dias trabajados

def _cancelar_los_dias(contrato_id):
    with SessionLocal() as db:
        contrato = db.get(m.ContratoImplantado, contrato_id)
        servicio = db.get(m.Servicio, contrato.servicio_id)
        for e in servicio.equipos:
            for j in e.jornadas:
                if (j.fecha.year, j.fecha.month) == (contrato.anio, contrato.mes):
                    j.estatus = m.EstatusJornada.CANCELADA
        db.commit()


def test_el_mes_sin_dias_trabajados_se_cobra_en_cero_y_lo_dice(
        cliente, sesion, datos, lista_de_odoo, odoo, cliente_de_odoo):
    servicio_id, contrato_id = _implantado(cliente, sesion, datos)
    _cancelar_los_dias(contrato_id)
    cierre_id = _cierre_del_mes(contrato_id)
    with SessionLocal() as db:
        contrato = db.get(m.ContratoImplantado, contrato_id)
        comparativo = cierre_mes.comparar(db, contrato)
        assert comparativo["sin_dias"] == {"cobro": "cero", "justificacion": None}
        assert comparativo["trabajado"]["importe"] == D("0")
        assert comparativo["contratado"]["importe"] == D("110000.00")
        assert any("se cobra en cero" in n for n in comparativo["notas"])
        revision = cierre_mes.revisar(db, contrato)
        aviso = next(o for o in revision["observaciones"]
                     if o.get("clave") == "mes_sin_dias")
        assert aviso["nivel"] == revisor.AVISO and aviso["justificable"] is True
        assert revision["listo_para_finanzas"] is True
        factura = cierre_mes.armar_factura(db, db.get(m.Cierre, cierre_id))
        assert [c["tipo"] for c in factura["conceptos"]] == []
    # El visto bueno sale en cero, lo dice, y no manda nada a Odoo.
    salida = _visto_bueno(cliente, sesion, cierre_id)
    assert salida["sin_dias"]["cobro"] == "cero"
    assert salida["factura"]["resultado"] == "nada que facturar"
    c = _cierre(cierre_id)
    assert D(str(c.total_ejecutado)) == D("0") and c.prefactura_odoo_id is None
    with SessionLocal() as db:
        vb = (db.query(m.RegistroAccion)
              .filter_by(servicio_id=servicio_id, accion="enviar a finanzas")
              .one())
        assert "sin dias trabajados: se cobra en cero" in vb.detalle
    bandeja = _bandeja(cliente, sesion)
    fila = next(f for f in bandeja["por_aprobar"] if f["cierre_id"] == cierre_id)
    assert fila["sin_cobro"] is True
    assert all(f["cierre_id"] != cierre_id for f in bandeja["no_se_pudo"])
    # Finanzas lo aprueba: queda facturado sin folio, sin esperar factura.
    _aprobar(cliente, sesion, cierre_id)
    c = _cierre(cierre_id)
    assert c.estatus == m.EstatusCierre.FACTURADO and c.factura_odoo is None
    assert c.facturado_en is not None
    assert all(f["cierre_id"] != cierre_id
               for f in _bandeja(cliente, sesion)["no_se_pudo"])
    assert "cie_msd_mensaje" in _js("cierre.js")
    _idioma_tiene("cie_asu_mes_sin_dias", "cie_msd_mensaje", "cie_msd_accion",
                  "fac_sin_cobro_pie")


def test_el_costo_fijo_pactado_se_justifica_y_cobra_el_mensual(
        cliente, sesion, datos, lista_de_odoo, odoo, cliente_de_odoo):
    servicio_id, contrato_id = _implantado(cliente, sesion, datos)
    _cancelar_los_dias(contrato_id)
    cierre_id = _cierre_del_mes(contrato_id)
    with SessionLocal() as db:
        descripcion = cierre_mes.texto_sin_dias(db.get(m.ContratoImplantado,
                                                       contrato_id))
    r = cliente.post(f"/cierre/{cierre_id}/desviaciones/respaldar",
                     params={"descripcion": descripcion},
                     json={"justificacion": "Costo fijo pactado con compras: "
                                            "el puesto se paga aunque no se use"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        contrato = db.get(m.ContratoImplantado, contrato_id)
        comparativo = cierre_mes.comparar(db, contrato)
        assert comparativo["sin_dias"]["cobro"] == "costo_fijo"
        assert comparativo["trabajado"]["importe"] == D("110000.00")
        revision = cierre_mes.revisar(db, contrato)
        assert any(o["asunto"] == "Desviacion respaldada"
                   for o in revision["observaciones"])
        assert not any(o.get("clave") == "mes_sin_dias"
                       for o in revision["observaciones"])
        factura = cierre_mes.armar_factura(db, db.get(m.Cierre, cierre_id))
        assert [c["tipo"] for c in factura["conceptos"]] == ["mes_completo"]
        assert factura["conceptos"][0]["importe"] == "110000.00"
    salida = _visto_bueno(cliente, sesion, cierre_id)
    assert salida["sin_dias"]["cobro"] == "costo_fijo"
    assert salida["factura"]["resultado"] == "en odoo"
    assert D(str(_cierre(cierre_id).total_ejecutado)) == D("110000.00")
    with SessionLocal() as db:
        vb = (db.query(m.RegistroAccion)
              .filter_by(servicio_id=servicio_id, accion="enviar a finanzas")
              .one())
        assert "costo fijo pactado" in vb.detalle


# ============================ decision 13 · el precio cotizado en gris

def test_el_cierre_respeta_el_precio_cotizado_de_lo_que_esta_en_gris(
        cliente, sesion, datos, con_productos, odoo):
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2409)
    with SessionLocal() as db:
        s = db.get(m.Servicio, servicio["id"])
        from app import cotizacion as cot
        vigente = cot.vigente(db, s.id)
        conductor = datos["perfiles"]["conductor_seguridad"]["id"]
        suv = datos["categorias"]["suv_blindada"]["id"]
        full = datos["modalidades"]["full_day"]["id"]
        de_antes = motor_cierre.ejecutado(db, s, vigente.tarifario_id)
        precio_cotizado = next(D(str(l.precio_unitario)) for l in vigente.lineas
                               if l.tipo == m.TipoLinea.RECURSO)
        tarifa = (db.query(m.TarifaRecurso)
                  .filter_by(tarifario_id=vigente.tarifario_id,
                             perfil_id=conductor, modalidad_id=full).one())
        unidad = (db.query(m.TarifaVehiculo)
                  .filter_by(tarifario_id=vigente.tarifario_id,
                             categoria_id=suv, modalidad_id=full).one())
        precio_unidad = D(str(unidad.precio))
        # La lista toma el conductor en gris y hoy cambio el tipo de
        # cambio: el cierre cobra lo cotizado. La unidad, pactada en
        # negro, va como esta en la lista.
        tarifa.origen = "precio_venta"
        tarifa.precio = precio_cotizado + D("50")
        unidad.origen = "propio"
        unidad.precio = precio_unidad + D("10")
        db.flush()
        de_hoy = motor_cierre.ejecutado(db, s, vigente.tarifario_id)
        conductores = [l for l in de_hoy["detalle"] if l["tipo"] == "recurso"]
        assert all(l["precio"] == precio_cotizado and l["precio_cotizado"]
                   for l in conductores)
        unidades = [l for l in de_hoy["detalle"] if l["tipo"] == "vehiculo"]
        assert all(l["precio"] == precio_unidad + D("10")
                   and not l["precio_cotizado"] for l in unidades)
        assert de_hoy["total"] == de_antes["total"] + D("20")
        renglones = motor_cierre.renglones(de_hoy["detalle"])
        assert any(r["precio_cotizado"] for r in renglones
                   if r["tipo"] == "recurso")
        # Lo que no se cotizo --otro rol en gris-- va con el precio de hoy.
        agente = datos["perfiles"]["agente_seguridad"]["id"]
        (db.query(m.TarifaRecurso)
         .filter_by(tarifario_id=vigente.tarifario_id, perfil_id=agente,
                    modalidad_id=full)
         .update({"origen": "precio_venta"}, synchronize_session=False))
        for e in s.equipos:
            for j in e.jornadas:
                for a in j.personal:
                    a.rol_id = agente
        db.flush()
        otro = motor_cierre.ejecutado(db, s, vigente.tarifario_id)
        assert all(not l["precio_cotizado"] for l in otro["detalle"])
        db.rollback()
    assert "cie_r_precio_cotizado" in _js("cierre.js")
    _idioma_tiene("cie_r_precio_cotizado")


# ================================ decision 16 · el aviso al titular

def test_la_cotizacion_que_manda_otro_le_avisa_al_titular_con_el_pdf(
        cliente, sesion, datos, db):
    # Ana es la titular; Beatriz la manda.
    c = _crear(cliente, sesion, datos)
    antes = db.query(m.Notificacion).count()
    _enviar(cliente, sesion, c, quien="consultor2")
    db.expire_all()
    ana = datos["personal"]["Ana Solis"]
    aviso = (db.query(m.Notificacion)
             .filter(m.Notificacion.correo == ana["correo"],
                     m.Notificacion.asunto.like("%con tu firma%"))
             .order_by(m.Notificacion.id.desc()).first())
    assert aviso is not None
    assert db.query(m.Notificacion).count() == antes + 1
    assert aviso.canal == m.Canal.CORREO and aviso.idioma == "es"
    assert "Beatriz Roman" in aviso.asunto and c["folio"] in aviso.asunto
    assert aviso.enlace_seguimiento == f"/consola/#/cotizacion/{c['id']}"
    pdf = db.get(m.ArchivoCotizacion, aviso.adjunto_id)
    assert pdf is not None and pdf.cotizacion_id == c["id"]
    assert pdf.tipo == "application/pdf"
    # El despachador adjunta el PDF al correo.
    from app import correo
    adjuntos = correo.adjuntos_de(db, aviso)
    assert [(a[0], a[1]) for a in adjuntos] == [(pdf.nombre, "application/pdf")]
    assert adjuntos[0][2][:4] == b"%PDF"
    rastro = (db.query(m.RegistroAdmin)
              .filter_by(accion="mandada con la firma de otro")
              .order_by(m.RegistroAdmin.id.desc()).first())
    assert rastro is not None and "Ana Solis" in rastro.antes
    # La que manda la propia titular no avisa a nadie.
    otra = _crear(cliente, sesion, datos)
    cuantos = db.query(m.Notificacion).count()
    _enviar(cliente, sesion, otra)
    db.expire_all()
    assert db.query(m.Notificacion).count() == cuantos


def test_el_correo_lleva_el_adjunto(monkeypatch):
    """`correo.entregar` arma el mensaje con el PDF como adjunto, por SMTP
    o por Microsoft: el mismo MIME."""
    from app import correo
    from app.config import settings

    armado = {}

    class SMTPFalso:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            pass

        def login(self, *a):
            pass

        def send_message(self, mensaje):
            armado["mensaje"] = mensaje

    monkeypatch.setattr(correo.smtplib, "SMTP", SMTPFalso)
    monkeypatch.setattr(settings, "correo_usuario", "")
    monkeypatch.setattr(settings, "correo_host", "smtp.prueba")
    monkeypatch.setattr(settings, "correo_puerto", 587)
    monkeypatch.setattr(correo, "por_microsoft", lambda: False)
    correo.entregar("ana@ejemplo.com", "Asunto", "Cuerpo", "<p>Cuerpo</p>",
                    adjuntos=[("EP-COT-0001.pdf", "application/pdf", b"%PDF-1.4")])
    mensaje = armado["mensaje"]
    partes = [p for p in mensaje.walk()
              if p.get_content_disposition() == "attachment"]
    assert len(partes) == 1
    assert partes[0].get_filename() == "EP-COT-0001.pdf"
    assert partes[0].get_content_type() == "application/pdf"
    assert partes[0].get_payload(decode=True) == b"%PDF-1.4"
    # Y sin adjuntos, como siempre: texto y HTML.
    correo.entregar("ana@ejemplo.com", "Asunto", "Cuerpo", "<p>Cuerpo</p>")
    assert not [p for p in armado["mensaje"].walk()
                if p.get_content_disposition() == "attachment"]


# ============================== decision 19 · el panel de direccion

def test_el_panel_trae_las_comisiones_las_calificaciones_y_los_cierres(
        cliente, sesion, datos, con_productos, odoo):
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2412)
    with SessionLocal() as db:
        c = db.get(m.Cierre, cierre_id)
        ahora = reloj.ahora_del_servicio(db, c.servicio)
        c.estatus = m.EstatusCierre.SIN_VISTO_BUENO
        c.limite_consultor = ahora + timedelta(hours=5)
        # Una comision del mes pasado sin corte, y una mala calificacion
        # sin clasificar.
        hoy = reloj.Relojes(db).hoy(datos["mx"]["id"])
        pasado = (hoy.replace(day=1) - timedelta(days=1))
        comision = m.ComisionConsultor(
            servicio_id=servicio["id"], consultor_id=c.servicio.consultor_id,
            anio=pasado.year, mes=pasado.month, facturacion=D("10000"),
            viaticos=D("0"), base=D("10000"), porcentaje=D("3"),
            monto=D("300"), moneda=m.Moneda.MXN)
        db.add(comision)
        # La del solicitante nacio con el termino del servicio: se
        # contesta aqui con dos estrellas.
        encuesta = (db.query(m.Encuesta)
                    .filter_by(servicio_id=servicio["id"],
                               tipo=m.TipoEncuesta.SOLICITANTE).first())
        if encuesta is None:
            encuesta = m.Encuesta(
                servicio_id=servicio["id"], tipo=m.TipoEncuesta.SOLICITANTE,
                consultor_id=c.servicio.consultor_id,
                destinatario_nombre="Valeria Rodas",
                destinatario_correo="valeria@ejemplo.com", idioma="es",
                token="prueba-131-encuesta",
                expira_en=datetime.now() + timedelta(days=5))
            db.add(encuesta)
        encuesta.estatus = m.EstatusEncuesta.RESPONDIDA
        encuesta.calificacion = 2
        encuesta.respondida_en = datetime.now()
        encuesta.requiere_clasificacion = True
        encuesta.clasificada_en = None
        encuesta.incidencia_id = None
        db.flush()
        db.add(m.RespuestaEncuesta(encuesta_id=encuesta.id, pregunta="comentario",
                                   texto="Llegó tarde y no avisó"))
        db.commit()
        comision_id, encuesta_id = comision.id, encuesta.id
    try:
        r = cliente.get("/direccion/bandeja", headers=sesion("diroperaciones"))
        assert r.status_code == 200, r.text
        d = r.json()
        corte = next(x for x in d["comisiones_por_firmar"]
                     if (x["anio"], x["mes"]) == (pasado.year, pasado.month)
                     and x["pais_id"] == datos["mx"]["id"])
        assert corte["consultores"] >= 1 and corte["se_puede_autorizar"] is True
        assert corte["ruta"] == (f"#/nomina/comisiones/{datos['mx']['id']}/"
                                 f"{pasado.year}-{pasado.month:02d}")
        mala = next(x for x in d["malas_calificaciones"]
                    if x["encuesta_id"] == encuesta_id)
        assert mala["le_toca"] == "direccion" and mala["calificacion"] == 2
        assert mala["comentario"] == "Llegó tarde y no avisó"
        assert mala["ruta"] == "#/encuestas"
        suyo = next(x for x in d["cierres_por_firmar"]
                    if x["cierre_id"] == cierre_id)
        assert suyo["consultor"] == "Ana Solis" and suyo["reloj"] == "consultor"
        assert 0 < suyo["minutos_restantes"] <= 300
        assert suyo["monto"] is not None and suyo["moneda"] == "MXN"
        assert suyo["ruta"] == f"#/servicio/{servicio['id']}"
        assert all(x["cierre_id"] != cierre_id for x in d["plazos_vencidos"])
        # Con el corte firmado, el mes ya no espera.
        with SessionLocal() as db:
            db.add(m.CorteComision(pais_id=datos["mx"]["id"], anio=pasado.year,
                                   mes=pasado.month, estatus="autorizado"))
            db.commit()
        d = cliente.get("/direccion/bandeja", headers=sesion("diroperaciones")).json()
        assert not any((x["anio"], x["mes"]) == (pasado.year, pasado.month)
                       for x in d["comisiones_por_firmar"])
    finally:
        with SessionLocal() as db:
            db.query(m.CorteComision).filter_by(
                pais_id=datos["mx"]["id"], anio=pasado.year,
                mes=pasado.month).delete()
            db.query(m.RespuestaEncuesta).filter_by(encuesta_id=encuesta_id).delete()
            e = db.get(m.Encuesta, encuesta_id)
            e.requiere_clasificacion = False
            e.clasificada_en = datetime.now()
            db.query(m.ComisionConsultor).filter_by(id=comision_id).delete()
            db.commit()
    js = _js("direccion.js")
    assert "tarjetaComisiones" in js and "tarjetaCalificaciones" in js
    assert "tarjetaCierres" in js
    assert "nomina\\/?(comisiones" in _js("app.js")
    assert "comisiones\\/(\\d+)\\/(\\d{4})-(\\d{1,2})" in _js("nomina.js")
    _idioma_tiene("dir_com_titulo", "dir_cal_titulo", "dir_cie_titulo",
                  "dir_quedan_horas", "dir_cal_te_toca")


# ================================= el «Eliminar» del implantado y Accesos

def test_el_implantado_que_no_arranco_se_elimina_desde_su_pantalla():
    js = _js("implantado.js")
    assert "borrarImplantado" in js and "imp_eliminar" in js
    assert "ANTES_DE_ARRANCAR.includes(ficha.estatus)" in js
    _idioma_tiene("imp_eliminar", "imp_eliminar_srv", "imp_eliminado")


def test_accesos_dice_el_pais_de_cada_quien(cliente, sesion, datos):
    r = cliente.get("/auth/usuarios", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    ana = next(u for u in r.json() if u["correo"] == "ana.solis@centauro.lat")
    assert ana["pais_id"] == datos["mx"]["id"] and ana["pais"] == "Mexico"
    js = _js("accesos.js")
    assert 'lista("entraron"' in js and 'lista("pais"' in js
    assert "ponerPaises" in js and "porEntrada" in js
    _idioma_tiene("acc_f_titulo", "acc_f_entraron", "acc_f_nunca",
                  "acc_f_dormidos", "acc_f_pais", "acc_f_pais_todos",
                  "acc_f_sin_pais", "acc_nadie_asi")


# ============================================ la migracion del adjunto

def test_la_migracion_del_adjunto_es_la_cabeza():
    import pathlib

    versiones = (pathlib.Path(__file__).resolve().parents[1] / "migrations"
                 / "versions")
    nueva = (versiones / "c3d7e9f2a1b4_adjunto_del_aviso.py").read_text()
    assert 'down_revision = "b7d3e9a1c5f2"' in nueva
    # Fue la cabeza hasta la seccion 132, que cuelga de ella.
    assert [p.name for p in versiones.glob("*.py")
            if 'down_revision = "c3d7e9f2a1b4"' in p.read_text()] == [
        "d4e8f0a3b2c5_freelance_a_planta.py"]
    with SessionLocal() as db:
        assert db.query(m.Notificacion.adjunto_id).limit(1).all() is not None

# -*- coding: utf-8 -*-
"""Seccion 127: la ola 1 de la revision 360 de lo nuevo (2 de octubre):
el dinero y lo que se quedaba atorado.

Lo que aqui se cuida, un hallazgo por prueba (`REVISION_2026_10_02.md`):

  * r1-01  La recotizacion en el servicio hereda la cabecera y arma sus
           dias: la lista la pinta completa y «Volver a crear» funciona.
  * r1-03  Al mandarla, la lista y la moneda son las de hoy.
  * r1-04  Quitar un equipo del servicio ajusta tambien los dias.
  * r1-06  La ruta vieja de autorizar contesta 409, no 500.
  * r2-01  Direccion ve y autoriza los precios de hoy.
  * r2-03  La modalidad distinta a la de la propuesta se avisa.
  * r2-04  El mes a medias que trabaja toda la base cobra el mensual.
  * r3-01  La vuelta de cada hora rueda entre todos los pendientes.
  * r3-02  El mes cancelado se juzga por el ultimo dia trabajado.
  * r3-03  Lo timbrado en Odoo no se regresa.
  * r3-04  «Volver a revisar en Odoo» suelta el borrador cancelado.
  * r3-05  Lo anotado como facturado no se manda despues del candado.
  * r3-06  El limite de tiempo para la vuelta sin matarla.
  * r3-07  La prefactura de la vuelta queda en la bitacora.
  * r3-08  Un error inesperado al mandar es un intento fallido mas.
  * r5-01  Brasil sin categoria: sus listas y productos se quedan.
  * r5-02  Un precio fijo en cero no es un precio.
  * r5-04  La hora extra del PDF con el producto de su pais y su paquete.
  * r5-05  La lista archivada que un cliente conserva se dice.
"""
import json
from datetime import date, datetime
from decimal import Decimal

from celery.exceptions import SoftTimeLimitExceeded

from app import cierre_mes, facturacion, odoo_facturacion
from app import implantado as motor_implantado
from app import models as m
from app.db import SessionLocal
from test_cotizaciones_cliente import (_autorizar, _borrar_su_servicio,  # noqa: F401
                                       _crear, _cuerpo, _enviar,
                                       cliente_de_odoo, db, lista_general)
from test_moneda_al_cotizar import _borrar, _copia, otro_cliente  # noqa: F401
from test_odoo_facturacion import _eventual, con_productos  # noqa: F401
from test_odoo_tarifarios import (LISTA0, PRODUCTO0, clientes,  # noqa: F401
                                  precios, sin_filtros, sin_rastro, tarifario)
from test_odoo_tarifarios import OdooFalso as OdooTarifas
from test_odoo_tarifarios_brasil import (EXTRA_BR, GENERAL_BR, LISTA_BR,  # noqa: F401
                                         PAQUETE_BR, brasil, de_brasil,
                                         filtros, mexico, mundo_brasil, _leido,
                                         _producto_de, _real)
from test_prefactura_odoo import (OdooFalso, _bandeja, _cierre,  # noqa: F401
                                  _cierre_del_mes, _implantado, _reintentar,
                                  _visto_bueno, lista_de_odoo, odoo)
from test_propuestas import INICIO, _contrato, _primer_mes, lista  # noqa: F401
from test_propuestas import _autorizar as _autorizar_propuesta
from test_propuestas import _crear as _crear_propuesta
from test_propuestas import _cuerpo as _propuesta
from test_propuestas import _enviar as _enviar_propuesta
from test_propuestas import _visto_bueno as _decidir_especial

D = Decimal


# ================================================================ la cotizacion

def _recotizar_en_el_servicio(cliente, sesion, datos, servicio):
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
    return r.json()


def test_la_recotizacion_en_el_servicio_hereda_la_cabecera_y_sus_dias(
        cliente, sesion, datos, db, cliente_de_odoo):
    """r1-01: la V2 que nace al recotizar en el servicio copia quien la
    pidio, el consultor, el idioma, la vigencia y el IVA, y arma sus dias
    con los del servicio. La lista la pinta completa, el detalle dice sus
    fechas, y si el servicio se elimina «Volver a crear» funciona."""
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    nacido = _autorizar(cliente, sesion, c).json()
    servicio = db.get(m.Servicio, nacido["servicio_id"])
    _recotizar_en_el_servicio(cliente, sesion, datos, servicio)
    db.expire_all()
    v1 = db.get(m.Cotizacion, c["id"])
    v2 = db.query(m.Cotizacion).filter_by(servicio_id=servicio.id, version=2).one()
    assert v2.folio == v1.folio and v2.estatus == m.EstatusCotizacion.AUTORIZADA
    assert v2.solicitante_nombre == "Valeria" and v2.consultor_id == v1.consultor_id
    assert (v2.idioma, v2.valida_hasta, v2.con_iva) == ("es", v1.valida_hasta, True)
    assert D(str(v2.tasa_iva)) == D(str(v1.tasa_iva))
    assert v2.servicio_folio == servicio.folio
    # Sus dias: los del servicio, con la ciudad del equipo, la modalidad y
    # lo que lleva ese dia (solo el conductor: se recotizo sin unidad).
    dias = sorted(v2.dias, key=lambda d: (d.equipo_clave, d.fecha))
    assert [(d.equipo_clave, d.fecha) for d in dias] == [
        (e.alias, j.fecha) for e in servicio.equipos
        for j in sorted(e.jornadas, key=lambda x: x.fecha)]
    assert all(d.plaza_id == datos["cdmx"]["id"] for d in dias)
    assert dias[-1].modalidad.codigo == m.CodigoModalidad.TRANSFER
    assert all(len(json.loads(d.lleva)) == 1 for d in dias)

    # La lista de Cotizaciones trae la fila completa y con IVA.
    filas = cliente.get("/cotizaciones/eventual",
                        headers=sesion("consultor")).json()["filas"]
    fila = next(f for f in filas if f["id"] == v2.id)
    assert fila["solicitante"] == "Valeria Rodas" and fila["consultor"]
    assert fila["desde"] == str(min(j.fecha for e in servicio.equipos
                                    for j in e.jornadas))
    detalle = cliente.get(f"/cotizaciones/eventual/{v2.id}",
                          headers=sesion("consultor")).json()
    assert detalle["dias_n"] == 3 and detalle["equipos_n"] == 2
    assert D(str(detalle["iva"])) > 0
    # El total de la lista es con IVA: el subtotal de la V2 mas el 16 %.
    assert D(str(fila["total"])) == (D(str(detalle["subtotal"]))
                                     * D("1.16")).quantize(D("0.01"))

    # El servicio se elimina: la V2 --la ultima-- se vuelve a crear.
    _borrar_su_servicio(cliente, sesion, nacido)
    assert cliente.get(f"/cotizaciones/eventual/{v2.id}",
                       headers=sesion("consultor")).json()["se_recrea"] is True
    r = cliente.post(f"/cotizaciones/eventual/{v2.id}/servicio",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    db.expire_all()
    otro = db.get(m.Servicio, r.json()["servicio_id"])
    assert [e.alias for e in otro.equipos] == ["Alfa", "Beta"]
    assert [len(e.jornadas) for e in otro.equipos] == [2, 1]
    assert otro.consultor_id == datos["personal"]["Ana Solis"]["id"]


def test_al_mandarla_toma_la_lista_y_la_moneda_de_hoy(cliente, sesion, datos, db,
                                                     lista_general, otro_cliente):
    """r1-03: el borrador se guardo con la general en pesos; antes de
    mandarla al cliente le llego su lista pactada en dolares. Al mandar,
    los precios, la lista y la moneda son los de hoy."""
    # El cliente esta en la general en pesos.
    otro_cliente.tarifario_id = lista_general.id
    db.commit()
    c = _crear(cliente, sesion, datos, cliente_id=otro_cliente.id)
    assert c["moneda"] == "MXN" and c["tarifario"]["id"] == lista_general.id
    pactada = _copia(db, lista_general, "Pactada en dolares", m.Moneda.USD,
                     False, D("20"))
    try:
        otro = db.get(m.Cliente, otro_cliente.id)
        otro.tarifario_id = pactada.id
        db.commit()
        enviada = _enviar(cliente, sesion, c)
        assert enviada["moneda"] == "USD"
        assert enviada["tarifario"]["id"] == pactada.id
        assert D(str(enviada["subtotal"])) == D("1400")
        db.expire_all()
        cot = db.get(m.Cotizacion, c["id"])
        assert cot.tarifario_id == pactada.id and cot.moneda == m.Moneda.USD
    finally:
        otro = db.get(m.Cliente, otro_cliente.id)
        otro.tarifario_id = None
        db.commit()
        _borrar(db, pactada)


def test_quitar_un_equipo_ajusta_tambien_los_dias_de_la_cotizacion(
        cliente, sesion, datos, db, cliente_de_odoo):
    """r1-04: con Alfa y Beta autorizados nace el servicio; se quita Beta.
    Los renglones y los dias de la cotizacion dicen lo mismo."""
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    nacido = _autorizar(cliente, sesion, c).json()
    servicio = db.get(m.Servicio, nacido["servicio_id"])
    beta = next(e for e in servicio.equipos if e.alias == "Beta")
    r = cliente.delete(f"/servicios/equipos/{beta.id}", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    db.expire_all()
    cot = db.get(m.Cotizacion, c["id"])
    assert {l.equipo_clave for l in cot.lineas} == {"Alfa"}
    assert {d.equipo_clave for d in cot.dias} == {"Alfa"} and len(cot.dias) == 2
    detalle = cliente.get(f"/cotizaciones/eventual/{c['id']}",
                          headers=sesion("consultor")).json()
    assert [e["clave"] for e in detalle["equipos"]] == ["Alfa"]
    assert detalle["dias_n"] == 2


def test_la_ruta_vieja_no_revienta_con_una_de_cotizaciones(cliente, sesion, datos):
    """r1-06: por la ruta de la seccion 94, una EP/COT sin servicio
    contesta que se autoriza en Cotizaciones."""
    c = _enviar(cliente, sesion, _crear(cliente, sesion, datos))
    r = cliente.post(f"/cotizaciones/{c['id']}/autorizar",
                     json={"autorizada_por": "Valeria"}, headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert "Cotizaciones" in r.text


# ================================================================ la propuesta

def test_direccion_ve_y_autoriza_los_precios_de_hoy(cliente, sesion, datos, db,
                                                   lista):
    """r2-01: el conductor de la lista y la CUV con precio escrito; se
    pide el visto bueno; la lectura de la noche cambia el precio del
    conductor. La bandeja y la propuesta ensenan lo de hoy, y con esa
    huella direccion autoriza (antes: 409 a cada intento)."""
    cuerpo = _propuesta(datos, especial_motivo="Tarifa pactada con compras")
    cuerpo["posiciones"][1]["precio_mes"] = "45000"      # la CUV, especial
    p = _crear_propuesta(cliente, sesion, cuerpo)
    p = cliente.post(f"/cotizaciones/propuesta/{p['id']}/especial",
                     headers=sesion("consultor")).json()
    assert p["especial"]["estatus"] == "pedido"
    huella_de_antes = p["huella"]
    # Cambia la lista: el conductor sube de 3,000 a 3,100 el dia.
    fila = (db.query(m.TarifaRecurso).filter_by(tarifario_id=lista.id)
            .filter_by(perfil_id=datos["perfiles"]["conductor_seguridad"]["id"]).one())
    fila.precio = D("3100")
    db.commit()

    bandeja = cliente.get("/direccion/bandeja", headers=sesion("diroperaciones")).json()
    suya = next(x for x in bandeja["precios_especiales"] if x["id"] == p["id"])
    assert suya["huella"] != huella_de_antes
    # 3,100 x 22 + 45,000.
    assert D(str(suya["subtotal"])) == D("113200")
    detalle = cliente.get(f"/cotizaciones/propuesta/{p['id']}",
                          headers=sesion("consultor")).json()
    assert detalle["huella"] == suya["huella"]
    r = _decidir_especial(cliente, sesion, p, huella=suya["huella"],
                          nota="Va, con el precio de hoy")
    assert r.status_code == 200, r.text
    assert r.json()["especial"]["estatus"] == "autorizado"
    assert r.json()["especial"]["vigente"] is True
    # Y se manda con ese visto bueno.
    _enviar_propuesta(cliente, sesion, p)


def test_la_modalidad_distinta_a_la_de_la_propuesta_se_avisa(
        cliente, sesion, datos, db, lista, cliente_de_odoo):
    """r2-03: Siemens autorizo de lunes a viernes; el consultor corrige el
    trato a lunes a sabado antes de abrir el mes. El mismo mensual
    reparte en 26 dias, y el visto bueno del mes lo dice."""
    p = _enviar_propuesta(cliente, sesion, _crear_propuesta(
        cliente, sesion, _propuesta(datos)))
    servicio_id = _autorizar_propuesta(cliente, sesion, p).json()["servicio_id"]
    acuerdo = db.query(m.AcuerdoImplantado).filter_by(servicio_id=servicio_id).one()
    acuerdo.dias_servicio = m.DiasServicio.LUNES_SABADO
    db.commit()
    mes = _primer_mes(cliente, sesion, datos, servicio_id)
    db.expire_all()
    contrato = db.get(m.ContratoImplantado, mes["contrato_id"])
    assert contrato.dias_servicio == m.DiasServicio.LUNES_SABADO
    assert motor_implantado.base_del_mensual(db, contrato) == 26
    revision = cierre_mes.revisar(db, contrato)
    aviso = next(o for o in revision["observaciones"]
                 if o.get("clave") == "modalidad_no_propuesta")
    assert aviso["datos"]["base_del_mes"] == 26
    assert aviso["datos"]["base_de_ella"] == 22
    assert "22 días" in aviso["mensaje"] and "26" in aviso["mensaje"]
    assert not any(o.get("clave") == "precios_propuesta"
                   for o in revision["observaciones"])


def test_el_mes_a_medias_que_trabaja_toda_la_base_cobra_el_mensual(db):
    """r2-04: diciembre de 2026 trae 23 habiles y el 1 es martes. El de
    lunes a viernes que empieza el 2 trabaja 22 dias: el mensual, no
    22 x 5,390.91 = 118,600.02."""
    habiles = [date(2026, 12, d) for d in range(2, 32)
               if date(2026, 12, d).weekday() < 5]
    assert len(habiles) == 22
    cobro = motor_implantado.cobro_del_mensual(
        db, _contrato(anio=2026, mes=12, desde_dia=2,
                      precio_mes_completo=D("118600")), habiles)
    assert cobro["parcial"] is False
    assert cobro["importe_mes"] == D("118600") == cobro["contratado"]
    # Con un dia menos sigue a medias, por dia.
    cobro = motor_implantado.cobro_del_mensual(
        db, _contrato(anio=2026, mes=12, desde_dia=2,
                      precio_mes_completo=D("118600")), habiles[:-1])
    assert cobro["parcial"] is True and cobro["dentro"] == 21
    assert cobro["importe_mes"] == D("5390.91") * 21


# ================================================================ la prefactura

def test_la_vuelta_de_cada_hora_rueda_entre_todos(cliente, sesion, datos,
                                                  con_productos, odoo, monkeypatch):
    """r3-01: con un solo lugar por vuelta, el cierre que falla para
    siempre (no cuadra) ya no deja fuera al nuevo que fallo porque Odoo
    no contesto: a la segunda vuelta sale."""
    _, viejo = _eventual(cliente, sesion, datos, offset=2301)
    _, nuevo = _eventual(cliente, sesion, datos, offset=2304)
    odoo.caido = True
    _visto_bueno(cliente, sesion, viejo)
    _visto_bueno(cliente, sesion, nuevo)
    odoo.caido = False
    with SessionLocal() as db:
        c = db.get(m.Cierre, viejo)
        c.total_ejecutado = D(str(c.total_ejecutado)) + 1       # no cuadra, nunca
        db.commit()
    monkeypatch.setattr(odoo_facturacion, "POR_VUELTA", 1)
    primera = _reintentar()
    assert primera["intentadas"] == 1 and primera["en_odoo"] == []
    segunda = _reintentar()
    assert segunda["intentadas"] == 1 and len(segunda["en_odoo"]) == 1
    assert _cierre(nuevo).prefactura_odoo_id is not None
    assert facturacion.que_paso(_cierre(viejo).factura_error) == "no_cuadra"


def test_el_mes_cancelado_se_juzga_por_el_ultimo_dia_trabajado(
        cliente, sesion, datos, lista_de_odoo, odoo):
    """r3-02: el cliente termino el miercoles 17 de octubre (13 dias) y la
    cancelacion se registro el 31 --el ultimo dia de la modalidad--: el
    mes va por dia, no completo."""
    _, contrato_id = _implantado(cliente, sesion, datos)
    with SessionLocal() as db:
        contrato = db.get(m.ContratoImplantado, contrato_id)
        for j in motor_implantado.jornadas_del_mes(contrato):
            j.estatus = (m.EstatusJornada.CANCELADA if j.fecha > date(2029, 10, 17)
                         else m.EstatusJornada.TERMINADA)
        db.commit()
    _cierre_del_mes(contrato_id, motivo="cancelacion",
                    abierto=datetime(2029, 10, 31, 9))
    with SessionLocal() as db:
        contrato = db.get(m.ContratoImplantado, contrato_id)
        assert cierre_mes.dia_de_la_cancelacion(db, contrato) == date(2029, 10, 17)
        comparativo = cierre_mes.comparar(db, contrato)
    assert comparativo["mensual"]["parcial"] is True
    assert comparativo["mensual"]["hasta_dia"] == 17
    assert comparativo["mensual"]["dias_de_servicio"] == 13
    assert comparativo["trabajado"]["importe"] == D("65000.00")


def test_lo_timbrado_en_odoo_no_se_regresa(cliente, sesion, datos, con_productos,
                                           odoo):
    """r3-03: el facturista ya timbro la prefactura; finanzas intenta
    regresarla y el sistema no la deja. Si Odoo no contesta, se regresa
    igual y lo dice."""
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2307)
    _visto_bueno(cliente, sesion, cierre_id)
    assert _cierre(cierre_id).prefactura_odoo_id == 4821
    odoo.facturas[4821]["state"] = "posted"
    odoo.facturas[4821]["name"] = "INV/2026/0042"
    r = cliente.post(f"/cierre/{cierre_id}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "La hora extra del primer dia no va"})
    assert r.status_code == 409, r.text
    assert "timbrada" in r.json()["detail"]["mensaje"]
    assert r.json()["detail"]["timbrada"] == "INV/2026/0042"
    assert _cierre(cierre_id).estatus == m.EstatusCierre.ENVIADO_FINANZAS
    # Odoo caido: se regresa, y la bitacora dice que no se pudo mirar.
    odoo.caido = True
    r = cliente.post(f"/cierre/{cierre_id}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "La hora extra del primer dia no va"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        regreso = (db.query(m.RegistroAccion)
                   .filter_by(servicio_id=servicio["id"],
                              accion="devolver a operacion").one())
        assert "Odoo no contesto" in regreso.detalle


def test_volver_a_revisar_en_odoo_suelta_el_borrador_cancelado(
        cliente, sesion, datos, con_productos, odoo):
    """r3-04: el facturista cancelo (o borro) el borrador. «Volver a
    revisar en Odoo» lo suelta y la vuelta de cada hora manda otro. En
    borrador no cambia nada; timbrado, lo dice."""
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2310)
    _visto_bueno(cliente, sesion, cierre_id)
    url = f"/cierre/{cierre_id}/revisar-en-odoo"
    assert cliente.post(url, headers=sesion("consultor")).status_code == 403
    r = cliente.post(url, headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json() == {"resultado": "sigue", "prefactura": 4821,
                        "estado": "borrador", "nombre": "INV/4821"}
    odoo.facturas[4821]["state"] = "posted"
    assert cliente.post(url, headers=sesion("finanzas")).json()["estado"] == "timbrada"
    assert _cierre(cierre_id).prefactura_odoo_id == 4821

    odoo.facturas[4821]["state"] = "cancel"
    r = cliente.post(url, headers=sesion("finanzas"))
    assert r.json()["resultado"] == "cancelada"
    c = _cierre(cierre_id)
    assert c.prefactura_odoo_id is None and c.prefactura_anulada_id == 4821
    assert facturacion.que_paso(c.factura_error) == "cancelada_en_odoo"
    suyo = next(f for f in _bandeja(cliente, sesion)["no_se_pudo"]
                if f["cierre_id"] == cierre_id)
    assert suyo["que_paso"] == "cancelada_en_odoo"
    with SessionLocal() as db:
        assert (db.query(m.RegistroAccion)
                .filter_by(servicio_id=servicio["id"],
                           accion="prefactura revisada en odoo").count() == 1)
    _reintentar()
    assert _cierre(cierre_id).prefactura_odoo_id == 4822

    # Borrada en Odoo: igual, sin nada que recordar.
    del odoo.facturas[4822]
    r = cliente.post(url, headers=sesion("finanzas"))
    assert r.json()["resultado"] == "borrada"
    c = _cierre(cierre_id)
    assert c.prefactura_odoo_id is None and c.prefactura_anulada_id is None
    # La consola ofrece el boton donde dice «En Odoo».
    import pathlib
    js = (pathlib.Path(__file__).resolve().parents[1] / "app" / "web"
          / "facturacion.js").read_text(encoding="utf-8")
    assert "/revisar-en-odoo" in js and "fac_revisar_en_odoo" in js


def test_lo_que_no_cuadra_ya_aprobado_lo_dice(cliente, sesion, datos,
                                              con_productos, odoo):
    """r3-04: si finanzas ya aprobo y despues la prefactura no cuadra, el
    texto ya no manda a un «Regresar» que no existe."""
    _, cierre_id = _eventual(cliente, sesion, datos, offset=2313)
    odoo.caido = True
    _visto_bueno(cliente, sesion, cierre_id)
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    odoo.caido = False
    with SessionLocal() as db:
        c = db.get(m.Cierre, cierre_id)
        c.total_ejecutado = D(str(c.total_ejecutado)) + 1
        db.commit()
    _reintentar()
    error = _cierre(cierre_id).factura_error
    assert facturacion.que_paso(error) == "no_cuadra"
    assert "ya está aprobado" in error and "regresa" not in error


def test_lo_anotado_como_facturado_no_se_manda(cliente, sesion, datos,
                                               con_productos, odoo):
    """r3-05: finanzas anota la factura hecha a mano mientras la vuelta
    tenia al cierre en su lista; al llegar a el, no crea un borrador."""
    _, cierre_id = _eventual(cliente, sesion, datos, offset=2316)
    odoo.caido = True
    _visto_bueno(cliente, sesion, cierre_id)
    odoo.caido = False
    with SessionLocal() as vuelta:
        viejo = vuelta.get(m.Cierre, cierre_id)           # la lista de la vuelta
        assert viejo.facturado_en is None
        r = cliente.put(f"/cierre/{cierre_id}/factura-de-odoo",
                        json={"folio": "INV/2026/0099", "fecha": str(date.today())},
                        headers=sesion("finanzas"))
        assert r.status_code == 200, r.text
        resultado = odoo_facturacion.mandar(vuelta, viejo)
        vuelta.commit()
    assert resultado["resultado"] == "ya estaba facturado"
    assert odoo.creadas() == []


def test_el_limite_de_tiempo_para_la_vuelta_sin_matarla(cliente, sesion, datos,
                                                        con_productos, odoo,
                                                        monkeypatch):
    """r3-06: el aviso del reloj para la vuelta ordenadamente y dice
    cuantos quedaron; no se atrapa como un error del cierre."""
    _, uno = _eventual(cliente, sesion, datos, offset=2319)
    _, dos = _eventual(cliente, sesion, datos, offset=2322)
    odoo.caido = True
    _visto_bueno(cliente, sesion, uno)
    _visto_bueno(cliente, sesion, dos)
    odoo.caido = False
    llamadas = []

    def mandar(db, cierre, ahora=None, primera_vez=True):
        llamadas.append(cierre.id)
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(odoo_facturacion, "mandar", mandar)
    r = _reintentar()
    assert r["paro_por_tiempo"] is True
    assert r["intentadas"] == 0 and r["siguen"] == 2 and len(llamadas) == 1
    assert odoo.creadas() == []


def test_la_prefactura_de_la_vuelta_queda_en_la_bitacora(cliente, sesion, datos,
                                                         con_productos, odoo):
    """r3-07: la que manda la vuelta de cada hora se anota en la bitacora
    del servicio, a nombre de quien dio el visto bueno y diciendo que
    salio sola."""
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2325)
    odoo.caido = True
    _visto_bueno(cliente, sesion, cierre_id)
    odoo.caido = False
    _reintentar()
    with SessionLocal() as db:
        registro = (db.query(m.RegistroAccion)
                    .filter_by(servicio_id=servicio["id"], accion="prefactura en odoo")
                    .one())
        assert "salio sola" in registro.detalle and "#4821" in registro.detalle
        assert registro.persona_id == datos["personal"]["Ana Solis"]["id"]


def test_un_error_inesperado_al_mandar_es_un_intento_fallido(cliente, sesion, datos,
                                                             con_productos, odoo):
    """r3-08: Odoo contesta sin id al crear --algo que `mandar` no sabe
    leer--: el visto bueno queda, el cierre cuenta el intento con su error
    y entra al reintento; no se queda como «de antes de la conexion»."""
    original = odoo.post

    def post(url, json):
        if url.endswith("account.move/create"):
            return type(original(url, json))([])     # contesta vacio
        return original(url, json)

    odoo.post = post
    _, cierre_id = _eventual(cliente, sesion, datos, offset=2328)
    envio = _visto_bueno(cliente, sesion, cierre_id)
    assert envio["resultado"] == "enviado a finanzas"
    assert envio["factura"]["resultado"] == "fallo"
    c = _cierre(cierre_id)
    assert c.estatus == m.EstatusCierre.ENVIADO_FINANZAS
    assert c.prefactura_desde is not None and c.factura_intentos == 1
    assert facturacion.que_paso(c.factura_error) == "sin_respuesta"
    suyo = next(f for f in _bandeja(cliente, sesion)["no_se_pudo"]
                if f["cierre_id"] == cierre_id)
    assert suyo["de_antes"] is False
    # Odoo vuelve a contestar bien: la vuelta de cada hora la manda.
    odoo.post = original
    _reintentar()
    assert _cierre(cierre_id).prefactura_odoo_id is not None


# ================================================================ los tarifarios

def test_sin_la_categoria_de_brasil_sus_listas_y_productos_se_quedan(
        db, filtros, de_brasil, brasil, mexico):
    """r5-01: con la de Brasil leida una vez, alguien la renombra en Odoo.
    Las listas de Brasil no se llenan con productos de Mexico ni se
    apagan, y sus productos no se borran ni se ponen en gris."""
    _real(db)
    _leido(db, OdooTarifas(mundo_brasil()))
    de_antes = precios(tarifario(db, 37))
    assert de_antes
    paquete_id = _producto_de(db, PAQUETE_BR).id

    tablas = mundo_brasil()
    tablas["product.category"] = [c for c in tablas["product.category"] if c["id"] != 5]
    informe = _leido(db, OdooTarifas(tablas))
    assert any(p["tipo"] == "sin_categoria_pais" for p in informe["pendientes"])
    general = tarifario(db, 37)
    assert general.activo is True
    assert precios(general) == de_antes
    assert all(r.modalidad.pais_id == brasil.id for r in general.tarifas_recurso)
    amazon = tarifario(db, 35)
    assert amazon.activo is True and len(amazon.tarifas_paquete) == 1
    paquete = db.get(m.ProductoOdoo, paquete_id)
    assert paquete is not None and paquete.confirmado and paquete.vendible
    assert _producto_de(db, PRODUCTO0 + 201).vendible is True
    # Las de Mexico siguen leyendose con lo suyo.
    assert {r.modalidad.pais_id for r in tarifario(db, 1).tarifas_recurso} == {mexico.id}


def test_un_precio_fijo_en_cero_no_es_un_precio(db, filtros, de_brasil, brasil):
    """r5-02: la regla recien creada en Odoo deja 0.00; el concepto queda
    sin precio y se dice, en vez de cobrarse gratis."""
    _real(db)
    tablas = mundo_brasil()
    # El motorista de la general de Brasil, en cero.
    regla = next(r for r in tablas["product.pricelist.item"]
                 if r["pricelist_id"][0] == GENERAL_BR
                 and r["product_tmpl_id"][0] == PRODUCTO0 + 201)
    regla["fixed_price"] = 0
    informe = _leido(db, OdooTarifas(tablas))
    assert ("conductor_seguridad", "full_day") not in precios(tarifario(db, 37))
    assert {"tipo": "regla", "lista": "Brasil · General",
            "producto": "Motorista Executivo Bilíngue",
            "problema": "precio fijo en cero: un cero no es un precio"
            } in informe["pendientes"]


def test_la_hora_extra_del_pdf_es_la_de_su_pais_y_la_de_su_paquete(
        db, filtros, de_brasil, brasil, mexico, datos):
    """r5-04 / r9-04: con los productos de los dos paises confirmados, la
    cotizacion de Brasil dice el producto de Brasil; y el rol que solo va
    en paquete toma la hora extra del paquete, como el cierre."""
    from app import cotizacion_cliente as cc

    from test_odoo_tarifarios import fija

    _real(db)
    tablas = mundo_brasil()
    # Mexico tambien tiene la hora extra del conductor, con su regla en la
    # general; su id es mas bajo que el de Brasil, que era el que ganaba.
    tablas["product.template"].insert(
        0, {"id": PRODUCTO0 + 11, "name": "Hora Extra Conductor de Seguridad Bilingüe",
         "list_price": 350, "type": "service", "sale_ok": True, "active": True,
         "categ_id": [2, "Protección Ejecutiva"], "uom_id": [32, "Horas"]})
    tablas["product.pricelist.item"].append({
        **fija(61, 1, 1, 400),
        "product_tmpl_id": [PRODUCTO0 + 11, "Hora Extra Conductor de Seguridad Bilingüe"]})
    _leido(db, OdooTarifas(tablas))
    conductor = db.query(m.PerfilPersonal).filter_by(codigo="conductor_seguridad").one()
    # Los dos de hora extra del conductor, confirmados: el de Mexico y el
    # de Brasil (y el del paquete de Amazon).
    de_mexico = (db.query(m.ProductoOdoo)
                 .filter_by(clase="hora_extra", perfil_id=conductor.id,
                            pais_id=mexico.id).first())
    assert de_mexico is not None and de_mexico.id < _producto_de(db, PRODUCTO0 + 206).id
    general = tarifario(db, 37)
    extra = cc.hora_extra(db, general, [conductor.id], brasil.id)
    assert len(extra) == 1
    assert extra[0]["producto"] == "Hora Extra Motorista Executivo Bilíngue"
    assert extra[0]["precio"] == D("450")
    # Y en Mexico, el de Mexico.
    extra_mx = cc.hora_extra(db, tarifario(db, 1), [conductor.id], mexico.id)
    assert extra_mx[0]["producto"] == "Hora Extra Conductor de Seguridad Bilingüe"
    assert extra_mx[0]["precio"] == D("400")
    # La lista de Amazon: el conductor solo va en paquete, con su hora extra.
    amazon = tarifario(db, 35)
    completo = db.query(m.Modalidad).filter_by(
        pais_id=brasil.id, codigo=m.CodigoModalidad.FULL_DAY).one()
    from app.cierre import hora_extra_del_rol
    assert hora_extra_del_rol(db, amazon.id, conductor.id, completo)[0] is None
    assert cc.hora_extra(db, amazon, [conductor.id], brasil.id) == []


def test_la_lista_archivada_que_un_cliente_conserva_se_dice(
        db, filtros, de_brasil, brasil):
    """r5-05: finanzas archiva en Odoo la lista de Amazon Brasil; la ficha
    la sigue nombrando. El cliente se queda con ella, y la lectura y el
    tarifario del cliente lo dicen."""
    _real(db)
    _leido(db, OdooTarifas(mundo_brasil()))
    amazon = db.get(m.Cliente, de_brasil.amazon)
    assert amazon.tarifario.odoo_id == LISTA_BR
    tablas = mundo_brasil()
    tablas["product.pricelist"] = [l for l in tablas["product.pricelist"]
                                   if l["id"] != LISTA_BR]
    informe = _leido(db, OdooTarifas(tablas))
    assert {"tipo": "lista_archivada", "cliente": amazon.nombre,
            "lista": "Brasil · Amazon Implantados (USD)"} in informe["pendientes"]
    db.expire_all()
    amazon = db.get(m.Cliente, de_brasil.amazon)
    assert amazon.tarifario.odoo_id == LISTA_BR and amazon.tarifario.activo is False
    # La vuelta siguiente lo sigue diciendo, sin cambiarle nada.
    informe = _leido(db, OdooTarifas(tablas))
    assert any(p["tipo"] == "lista_archivada" for p in informe["pendientes"])

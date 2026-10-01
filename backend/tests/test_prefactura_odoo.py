# -*- coding: utf-8 -*-
"""La prefactura en Odoo, del eventual y del mes del implantado (seccion
117, entrega 2).

Decisiones de Salvador (1 oct): con el visto bueno --del servicio o del
mes-- Connect manda a Odoo una factura de cliente en borrador y el
facturista la confirma y la timbra alla. Una por implantado y por mes, con
un renglon por puesto y por unidad. El mes que se cancela a la mitad se
cobra por dia de servicio. Finanzas sigue aprobando mientras tanto.

Lo que se cuida:

  * Sale con el visto bueno, al momento, y lo que se mando se guarda y se
    ve en la tarjeta del cierre y en Facturacion → «En Odoo».
  * Si Odoo no contesta o falta un dato, el visto bueno queda y el cierre
    se queda en «No se pudo mandar» con su porque; la tarea de cada hora
    la vuelve a intentar sin duplicar.
  * Regresarlo no borra la prefactura de Odoo --no se puede--: la nueva no
    sale mientras la anterior siga viva.
  * Lo que tuvo su visto bueno antes de la llave no sale solo.
  * Lo que se manda es lo que el consultor aprobo.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app import cierre_mes, facturacion
from app import implantado as motor_implantado
from app import models as m
from app import odoo_facturacion
from app import odoo_facturacion_mes as mes_odoo
from app.db import SessionLocal
from test_odoo_facturacion import (NOMBRE, PARTNER, VARIANTE, _eventual,
                                   con_productos)

D = Decimal
_ = con_productos            # la fixture, para que pytest la encuentre


# ================================================================ el Odoo de mentiras

class Respuesta:
    def __init__(self, datos):
        self.status_code, self._datos = 200, datos

    def json(self):
        return self._datos


class OdooFalso:
    """Las monedas, las facturas de cliente que ya hay --por su origen-- y
    las que se crean. `caido`: no contesta. `pierde`: crea la siguiente
    pero su respuesta no llega."""

    def __init__(self):
        self.facturas, self.pedidos = {}, []
        self.siguiente, self.caido, self.pierde = 4821, False, False

    def post(self, url, json):
        modelo, metodo = url.split("/json/2/")[1].split("/")
        self.pedidos.append((modelo, metodo, json))
        if self.caido:
            raise httpx.ConnectTimeout("timed out")
        if modelo == "res.currency":
            nombre = json["domain"][0][2]
            return Respuesta([{"id": 33, "name": "MXN", "active": True}]
                             if nombre == "MXN" else [])
        if (modelo, metodo) == ("account.move", "search_read"):
            origen = next(d[2] for d in json["domain"] if d[0] == "invoice_origin")
            return Respuesta([f for f in self.facturas.values()
                              if f["invoice_origin"] == origen])
        if (modelo, metodo) == ("account.move", "create"):
            vals = json["vals_list"][0]
            n, self.siguiente = self.siguiente, self.siguiente + 1
            self.facturas[n] = {"id": n, "state": "draft",
                                "invoice_origin": vals["invoice_origin"],
                                "ref": vals["ref"], "vals": vals}
            if self.pierde:
                self.pierde = False
                raise httpx.ReadTimeout("timed out")
            return Respuesta([n])
        raise AssertionError(url)

    def creadas(self):
        return [p for p in self.pedidos if p[1] == "create"]


@pytest.fixture
def odoo(monkeypatch):
    """La llave de la factura puesta y un Odoo de mentiras detras."""
    from app.config import settings

    falso = OdooFalso()
    monkeypatch.setattr(settings, "odoo_base", "https://odoo.prueba")
    monkeypatch.setattr(settings, "odoo_facturacion_api_key", "secreta-117")
    original = odoo_facturacion.conexion

    def conexion(clase=odoo_facturacion.Conexion):
        c = original(clase)
        c.http = falso
        return c

    monkeypatch.setattr(odoo_facturacion, "conexion", conexion)
    yield falso
    # Lo que se quedo sin salir no se le reintenta a la prueba que sigue,
    # con su propio Odoo de mentiras.
    with SessionLocal() as db:
        (db.query(m.Cierre)
         .filter(m.Cierre.prefactura_odoo_id.is_(None),
                 m.Cierre.prefactura_desde.isnot(None))
         .update({"prefactura_desde": None}, synchronize_session=False))
        db.commit()


def _cierre(cierre_id) -> m.Cierre:
    db = SessionLocal()
    c = db.get(m.Cierre, cierre_id)
    db.expunge(c)
    db.close()
    return c


def _visto_bueno(cliente, sesion, cierre_id, codigo=200):
    r = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                     headers=sesion("consultor"))
    assert r.status_code == codigo, r.text
    return r.json()


def _bandeja(cliente, sesion):
    r = cliente.get("/cierre/facturacion", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    return r.json()


def _reintentar():
    with SessionLocal() as db:
        return odoo_facturacion.reintentar(db)


# ================================================================ el eventual

def test_con_el_visto_bueno_sale_la_prefactura(cliente, sesion, datos,
                                               con_productos, odoo):
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2201)
    envio = _visto_bueno(cliente, sesion, cierre_id)
    assert envio["factura"]["resultado"] == "en odoo"
    assert envio["factura"]["prefactura"] == 4821
    assert envio["factura"]["nueva"] is True

    # Lo que llego a Odoo: la factura de cliente en borrador, con su
    # referencia y su origen, y solo con lo que Connect sabe ponerle.
    (_, _, cuerpo), = odoo.creadas()
    vals = cuerpo["vals_list"][0]
    assert odoo_facturacion.es_prefactura({"vals_list": [vals]})
    assert (vals["partner_id"], vals["ref"], vals["invoice_origin"]) == (
        PARTNER, servicio["folio"], f"Connect · {servicio['folio']}")
    assert vals["currency_id"] == 33
    assert [r[2]["product_id"] for r in vals["invoice_line_ids"]] == [
        VARIANTE["rol"], VARIANTE["unidad"], VARIANTE["hora_extra"],
        VARIANTE["rol"], VARIANTE["unidad"], VARIANTE["gastos"]]

    c = _cierre(cierre_id)
    assert c.prefactura_odoo_id == 4821 and c.factura_error is None
    assert D(str(c.prefactura_total)) == D(str(c.total_ejecutado)) == D("25790.00")
    assert c.prefactura_desde is not None and c.factura_intentos == 1
    assert c.estatus == m.EstatusCierre.ENVIADO_FINANZAS
    assert c.facturado_en is None, "timbrarla es del facturista"

    # La tarjeta del cierre: el paso, lo que se mando y donde se abre.
    tarjeta = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                          headers=sesion("consultor")).json()
    assert tarjeta["llave_factura"] is True
    pre = tarjeta["prefactura"]
    assert pre["id"] == 4821 and pre["total"] == "25790.00"
    assert pre["referencia"] == servicio["folio"] and pre["moneda"] == "MXN"
    assert pre["url"] == ("https://odoo.prueba/web#id=4821&model=account.move"
                          "&view_type=form")
    assert [r["producto"] for r in pre["renglones"]][:3] == [
        NOMBRE["rol"], "SUBURBAN Blindada", NOMBRE["hora_extra"]]
    assert sum(D(r["importe"]) for r in pre["renglones"]) == D("25790.00")

    # En la bitacora del servicio, con quien la hizo salir.
    with SessionLocal() as db:
        accion = (db.query(m.RegistroAccion)
                  .filter_by(servicio_id=servicio["id"],
                             accion="prefactura en odoo").one())
        assert "borrador #4821" in accion.detalle
        assert "25,790.00 MXN antes de IVA" in accion.detalle

    # Facturacion: en «En Odoo», y finanzas la sigue aprobando.
    b = _bandeja(cliente, sesion)
    assert b["llave"] is True
    suyo = next(f for f in b["en_odoo"] if f["cierre_id"] == cierre_id)
    assert suyo["prefactura"]["id"] == 4821 and suyo["de_antes"] is False
    assert not [f for f in b["no_se_pudo"] if f["cierre_id"] == cierre_id]
    assert any(f["cierre_id"] == cierre_id for f in b["por_aprobar"])

    # «Mandar otra vez» no hace otra.
    r = cliente.post(f"/cierre/{cierre_id}/facturar", headers=sesion("finanzas"))
    assert r.json()["resultado"] == "ya estaba en odoo"
    assert len(odoo.creadas()) == 1

    # Finanzas aprueba: sigue en Odoo, por timbrar.
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["factura"]["resultado"] == "ya estaba en odoo"
    c = _cierre(cierre_id)
    assert c.estatus == m.EstatusCierre.APROBADO and c.facturado_en is None
    assert any(f["cierre_id"] == cierre_id for f in _bandeja(cliente, sesion)["en_odoo"])

    # Ya timbrada, finanzas anota su folio y sale de «En Odoo».
    r = cliente.put(f"/cierre/{cierre_id}/factura-de-odoo",
                    headers=sesion("finanzas"),
                    json={"folio": "INV/2026/04821", "fecha": str(date.today())})
    assert r.status_code == 200, r.text
    assert _cierre(cierre_id).estatus == m.EstatusCierre.FACTURADO
    assert not [f for f in _bandeja(cliente, sesion)["en_odoo"]
                if f["cierre_id"] == cierre_id]


def test_si_odoo_no_contesta_se_reintenta_sin_duplicar(cliente, sesion, datos,
                                                       con_productos, odoo):
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2204)
    odoo.caido = True
    envio = _visto_bueno(cliente, sesion, cierre_id)
    assert envio["resultado"] == "enviado a finanzas", "el visto bueno queda"
    assert envio["factura"]["resultado"] == "fallo"
    c = _cierre(cierre_id)
    assert c.estatus == m.EstatusCierre.ENVIADO_FINANZAS
    assert c.prefactura_odoo_id is None and c.factura_intentos == 1
    assert c.factura_error.startswith("Odoo no contesto")
    suyo = next(f for f in _bandeja(cliente, sesion)["no_se_pudo"]
                if f["cierre_id"] == cierre_id)
    assert suyo["que_paso"] == "sin_respuesta" and suyo["intentos"] == 1
    tarjeta = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                          headers=sesion("consultor")).json()
    assert tarjeta["prefactura"] is None and tarjeta["que_paso"] == "sin_respuesta"

    # Vuelve Odoo, pero la respuesta de la que crea se pierde: la crea y
    # el cierre no se entera...
    odoo.caido, odoo.pierde = False, True
    _reintentar()
    assert len(odoo.creadas()) == 1
    c = _cierre(cierre_id)
    assert c.prefactura_odoo_id is None and c.factura_intentos == 2
    # ...y la vuelta siguiente la encuentra por su origen: no hace otra.
    r = _reintentar()
    assert servicio["folio"] in r["en_odoo"]
    assert len(odoo.creadas()) == 1
    c = _cierre(cierre_id)
    assert c.prefactura_odoo_id == 4821 and c.factura_error is None
    # Ya en Odoo, la tarea no la vuelve a tocar.
    _reintentar()
    assert _cierre(cierre_id).factura_intentos == 3


def test_lo_que_falta_no_sale_y_se_dice(cliente, sesion, datos, odoo):
    """La lista del cliente de las pruebas se capturo a mano: sus precios
    no tienen producto de Odoo. El cliente sin ficha en Odoo no deja dar
    el visto bueno; con ficha, el visto bueno sale y la prefactura no."""
    _, cierre_id = _eventual(cliente, sesion, datos, offset=2207, gastos=None)
    r = _visto_bueno(cliente, sesion, cierre_id, codigo=409)
    claves = [o.get("clave") for o in r["detail"]["observaciones"]]
    assert "cliente_sin_odoo" in claves

    with SessionLocal() as db:
        cliente_db = db.get(m.Cliente, datos["cliente_id"])
        antes, cliente_db.odoo_id = cliente_db.odoo_id, PARTNER
        db.commit()
    try:
        envio = _visto_bueno(cliente, sesion, cierre_id)
    finally:
        with SessionLocal() as db:
            db.get(m.Cliente, datos["cliente_id"]).odoo_id = antes
            db.commit()
    assert envio["factura"]["resultado"] == "fallo"
    assert odoo.pedidos == [], "lo que no se puede mandar no sale a la red"
    c = _cierre(cierre_id)
    assert c.factura_error.startswith(odoo_facturacion.FALTA_DATO)
    assert "se capturó a mano" in c.factura_error
    assert facturacion.que_paso(c.factura_error) == "falta_dato"


def test_regresarlo_deja_la_prefactura_y_no_hace_dos(cliente, sesion, datos,
                                                    con_productos, odoo):
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2210)
    _visto_bueno(cliente, sesion, cierre_id)
    assert _cierre(cierre_id).prefactura_odoo_id == 4821

    r = cliente.post(f"/cierre/{cierre_id}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "La hora extra del primer dia no va"})
    assert r.status_code == 200, r.text
    assert r.json()["prefactura_anulada"] == 4821
    c = _cierre(cierre_id)
    assert c.prefactura_odoo_id is None and c.prefactura_anulada_id == 4821
    assert c.prefactura_detalle is None
    with SessionLocal() as db:
        regreso = (db.query(m.RegistroAccion)
                   .filter_by(servicio_id=servicio["id"],
                              accion="devolver a operacion").one())
        assert "prefactura #4821 quedo en Odoo" in regreso.detalle
    tarjeta = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                          headers=sesion("consultor")).json()
    assert tarjeta["fase"] == "devuelto" and tarjeta["prefactura_anulada"] == 4821

    # El nuevo visto bueno no manda otra mientras la anterior siga viva.
    envio = _visto_bueno(cliente, sesion, cierre_id)
    assert envio["factura"]["resultado"] == "fallo"
    assert len(odoo.creadas()) == 1
    c = _cierre(cierre_id)
    assert facturacion.que_paso(c.factura_error) == "anterior_viva"
    assert "#4821" in c.factura_error
    suyo = next(f for f in _bandeja(cliente, sesion)["no_se_pudo"]
                if f["cierre_id"] == cierre_id)
    assert suyo["prefactura_anulada"] == 4821
    assert suyo["prefactura_url_anulada"].endswith("id=4821&model=account.move"
                                                   "&view_type=form")

    # El facturista la cancela en Odoo: la vuelta de cada hora manda la
    # nueva, con la misma referencia.
    odoo.facturas[4821]["state"] = "cancel"
    _reintentar()
    c = _cierre(cierre_id)
    assert c.prefactura_odoo_id == 4822 and c.prefactura_anulada_id is None
    assert odoo.facturas[4822]["ref"] == servicio["folio"]


def test_lo_de_antes_de_la_llave_no_sale_solo(cliente, sesion, datos,
                                             con_productos, odoo, monkeypatch):
    """Tuvo su visto bueno antes de la llave: pudo haberse facturado a mano
    en Odoo sin anotarse aqui. Ni la tarea de cada hora ni la aprobacion
    lo mandan; finanzas decide."""
    from app.config import settings

    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2213)
    monkeypatch.setattr(settings, "odoo_facturacion_api_key", "")
    envio = _visto_bueno(cliente, sesion, cierre_id)
    assert envio["factura"]["resultado"] == "sin conexion"
    monkeypatch.setattr(settings, "odoo_facturacion_api_key", "secreta-117")

    _reintentar()
    assert odoo.pedidos == []
    suyo = next(f for f in _bandeja(cliente, sesion)["no_se_pudo"]
                if f["cierre_id"] == cierre_id)
    assert suyo["de_antes"] is True and suyo["que_paso"] == "de_antes"
    assert suyo["error"] is None
    assert _bandeja(cliente, sesion)["resumen"]["no_se_pudo"]["de_antes"] >= 1
    tarjeta = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                          headers=sesion("consultor")).json()
    assert tarjeta["prefactura_de_antes"] is True

    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["factura"]["resultado"] == "sin mandar"
    assert odoo.pedidos == []

    # «Mandar a Odoo»: la manda finanzas, y sus intentos cuentan desde ahi.
    r = cliente.post(f"/cierre/{cierre_id}/facturar", headers=sesion("finanzas"))
    assert r.json()["resultado"] == "en odoo"
    c = _cierre(cierre_id)
    assert c.prefactura_odoo_id == 4821 and c.factura_intentos == 1
    assert c.prefactura_desde is not None


def test_lo_que_se_manda_es_lo_que_se_aprobo(cliente, sesion, datos,
                                            con_productos, odoo):
    """Si un precio de la lista cambia despues del visto bueno, la
    prefactura ya no dice lo que el consultor aprobo: no sale."""
    _, cierre_id = _eventual(cliente, sesion, datos, offset=2216)
    odoo.caido = True
    _visto_bueno(cliente, sesion, cierre_id)
    odoo.caido = False
    with SessionLocal() as db:
        lista = db.get(m.Tarifario, con_productos["lista_id"])
        fila = next(x for x in lista.tarifas_recurso
                    if x.producto_odoo_id == con_productos["rol"]
                    and D(str(x.precio)) == D("3200"))
        fila.precio, fila_id = D("3300"), fila.id
        db.commit()
    try:
        _reintentar()
    finally:
        with SessionLocal() as db:
            db.get(m.TarifaRecurso, fila_id).precio = D("3200")
            db.commit()
    c = _cierre(cierre_id)
    assert c.prefactura_odoo_id is None
    assert facturacion.que_paso(c.factura_error) == "no_cuadra"
    assert "25,990.00" in c.factura_error and "25,790.00" in c.factura_error
    assert odoo.creadas() == []


def test_dos_a_la_vez_no_hacen_dos(cliente, sesion, datos, con_productos, odoo):
    """Quien llega segundo --la tarea de cada hora y «Mandar otra vez» en
    el mismo minuto-- espera la fila y la encuentra ya en Odoo."""
    _, cierre_id = _eventual(cliente, sesion, datos, offset=2219)
    odoo.caido = True
    _visto_bueno(cliente, sesion, cierre_id)
    odoo.caido = False
    with SessionLocal() as segundo:
        viejo = segundo.get(m.Cierre, cierre_id)        # lo leyo antes
        assert viejo.prefactura_odoo_id is None
        with SessionLocal() as primero:
            odoo_facturacion.mandar(primero, primero.get(m.Cierre, cierre_id))
            primero.commit()
        r = odoo_facturacion.mandar(segundo, viejo)
        segundo.commit()
    assert r["resultado"] == "ya estaba en odoo"
    assert len(odoo.creadas()) == 1


def test_que_paso_en_una_palabra():
    of = odoo_facturacion
    casos = {
        of.SIN_LLAVE: "sin_llave",
        f"{of.FALTA_DATO} «Van 10 pax»: la lista se capturó a mano en Connect.":
            "falta_dato",
        of.ANTERIOR_VIVA.format(id=4821): "anterior_viva",
        of.NO_CUADRA_VB.format(suma="1.00", total="2.00"): "no_cuadra",
        "Odoo no contesto: timed out": "sin_respuesta",
        "Odoo contesto 502: Bad Gateway": "sin_respuesta",
        f"{of.NO_SE_ENTIENDE} 'id'": "sin_respuesta",
        "Odoo rechazo la llave; puede que haya vencido.": "rechazada",
        "Odoo contesto 403: Access Denied": "rechazada",
        "Odoo contesto 422: Falta la cuenta de ingresos": "rechazada",
        # Los de la factura de siempre, como estaban.
        facturacion.SIN_CONEXION: "sin_conexion",
        "Client error '400 Bad Request'": "rechazada",
        "Server error '500'": "sin_respuesta",
        "El servicio no tiene cotizacion autorizada": "falta_dato",
    }
    for error, palabra in casos.items():
        assert facturacion.que_paso(error) == palabra, error


# ================================================================ el mes del implantado

INICIO = date(2029, 10, 1)        # lunes; octubre de 2029 acaba en miercoles


@pytest.fixture
def lista_de_odoo(datos):
    """La lista de implantados del cliente, como si viniera de Odoo: el
    conductor a $3,000 el dia --hora extra de $300-- y la CUV a $2,000,
    cada uno con su producto; el cliente con su ficha y el producto de los
    gastos."""
    completo = datos["modalidades"]["full_day"]["id"]
    with SessionLocal() as db:
        productos = {}
        for clave, nombre, clase, variante in (
                ("rol", "Conductor de Seguridad Bilingüe", "rol", 7101),
                ("cuv", "CUV", "unidad", 7102),
                ("hora_extra", "Hora Extra Conductor de Seguridad Bilingüe",
                 "hora_extra", 7103),
                ("gastos", "Gastos de Operación (Viáticos)", "viaticos", 7104)):
            p = m.ProductoOdoo(odoo_id=9_700_000 + variante, nombre=nombre,
                               clase=clase, confirmado=True, vendible=True,
                               variante_odoo_id=variante, variantes=1)
            db.add(p)
            db.flush()
            productos[clave] = p.id
        lista = m.Tarifario(nombre="Implantados prueba 117",
                            pais_id=datos["mx"]["id"], moneda=m.Moneda.MXN,
                            vigencia_desde=date(2026, 1, 1), odoo_id=9_700_900)
        db.add(lista)
        db.flush()
        db.add(m.TarifaRecurso(tarifario_id=lista.id,
                               perfil_id=datos["perfiles"]["conductor_seguridad"]["id"],
                               modalidad_id=completo, precio=D("3000"),
                               precio_hora_extra=D("300"),
                               producto_odoo_id=productos["rol"],
                               producto_hora_extra_id=productos["hora_extra"]))
        db.add(m.TarifaVehiculo(tarifario_id=lista.id,
                                categoria_id=datos["categorias"]["cuv"]["id"],
                                modalidad_id=completo, precio=D("2000"),
                                producto_odoo_id=productos["cuv"]))
        cliente = db.get(m.Cliente, datos["cliente_id"])
        antes = (cliente.tarifario_implantado_id, cliente.odoo_id)
        cliente.tarifario_implantado_id, cliente.odoo_id = lista.id, PARTNER
        lista_id = lista.id
        db.commit()
    yield productos
    with SessionLocal() as db:
        cliente = db.get(m.Cliente, datos["cliente_id"])
        cliente.tarifario_implantado_id, cliente.odoo_id = antes
        db.query(m.Cotizacion).filter_by(tarifario_id=lista_id).update(
            {"tarifario_id": None})
        db.flush()
        db.delete(db.get(m.Tarifario, lista_id))
        db.flush()
        db.query(m.ProductoOdoo).filter(
            m.ProductoOdoo.id.in_(list(productos.values()))).delete(
                synchronize_session=False)
        db.commit()


def _implantado(cliente, sesion, datos, inicio=INICIO, **precios):
    """Una propuesta con un conductor y una CUV, de lunes a viernes,
    autorizada, y su primer mes abierto con Juan y la Suburban. `precios`:
    el mensual de cada uno, escrito (precio especial)."""
    posiciones = [
        {"tipo": "recurso", "cantidad": 1,
         "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"],
         **({"precio_mes": precios["conductor"]} if "conductor" in precios else {})},
        {"tipo": "vehiculo", "cantidad": 1,
         "categoria_id": datos["categorias"]["cuv"]["id"],
         "descripcion": "Toyota RAV4",
         **({"precio_mes": precios["cuv"]} if "cuv" in precios else {})}]
    cuerpo = {
        "cliente_id": datos["cliente_id"],
        "solicitante_nombre": "Andrea", "solicitante_apellidos": "Ruiz",
        "solicitante_correo": "andrea.ruiz@ejemplo.com",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "tipo_servicio": "Transporte terrestre seguro",
        "valida_hasta": str(date.today() + timedelta(days=60)),
        "idioma": "es", "con_iva": True, "inicio": str(inicio),
        "dias_servicio": "lunes_viernes", "viaticos": "aparte",
        "hora_presentacion": "07:00", "posiciones": posiciones}
    if precios:
        cuerpo["especial_motivo"] = "Tarifa pactada con compras"
    h = sesion("consultor")
    p = cliente.post("/cotizaciones/propuesta", json=cuerpo, headers=h)
    assert p.status_code == 201, p.text
    p = p.json()
    if precios:
        p = cliente.post(f"/cotizaciones/propuesta/{p['id']}/especial",
                         headers=h).json()
        r = cliente.post(f"/cotizaciones/propuesta/{p['id']}/especial/decidir",
                         json={"autoriza": True, "nota": None, "huella": p["huella"]},
                         headers=sesion("diroperaciones"))
        assert r.status_code == 200, r.text
    r = cliente.post(f"/cotizaciones/propuesta/{p['id']}/enviar", headers=h)
    assert r.status_code == 200, r.text
    r = cliente.post(f"/cotizaciones/propuesta/{p['id']}/autorizar", headers=h,
                     data={"autorizada_por": "Andrea Ruiz",
                           "autorizada_el": str(date.today())})
    assert r.status_code == 200, r.text
    servicio_id = r.json()["servicio_id"]
    r = cliente.post(f"/implantados/{servicio_id}/mes", headers=h, json={
        "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": datos["suburban"]["id"]}],
        "unidades": [datos["suburban"]["id"]],
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia"})
    assert r.status_code == 201, r.text
    return servicio_id, r.json()["contrato_id"]


def _cierre_del_mes(contrato_id, motivo="termino", abierto=None):
    """El cierre del mes, ya en su visto bueno, sin recorrer sus relojes:
    aqui se mira la prefactura, no los plazos."""
    with SessionLocal() as db:
        contrato = db.get(m.ContratoImplantado, contrato_id)
        abierto = abierto or datetime(contrato.anio, contrato.mes, 28, 21)
        c = m.Cierre(servicio_id=contrato.servicio_id, contrato_id=contrato.id,
                     abierto_en=abierto, motivo_apertura=motivo,
                     limite_consultor=abierto + timedelta(hours=48),
                     estatus=m.EstatusCierre.SIN_VISTO_BUENO)
        db.add(c)
        db.commit()
        return c.id


def _prefactura_del_mes(cierre_id):
    with SessionLocal() as db:
        return odoo_facturacion.prefactura(db, db.get(m.Cierre, cierre_id))


def _renglones(pre):
    return [(r["tipo"], r["producto"], r["cantidad"], r["precio"])
            for r in pre["renglones"]]


def test_el_mes_de_la_propuesta_va_por_puesto_y_unidad(cliente, sesion, datos,
                                                       lista_de_odoo, odoo):
    """Octubre de 2029 entero: el mensual del conductor y el de la CUV, cada
    uno en su renglon con su producto, y la referencia del folio y el mes."""
    servicio_id, contrato_id = _implantado(cliente, sesion, datos)
    pre = _prefactura_del_mes(_cierre_del_mes(contrato_id))
    assert pre["faltan"] == [], pre["faltan"]
    folio = pre["referencia"].split(" · ")[0]
    assert folio.startswith("EP/IM-")
    assert pre["referencia"] == f"{folio} · 10/2029"
    assert pre["origen"] == f"Connect · {folio} · 10/2029"
    assert _renglones(pre) == [
        ("mes", "Conductor de Seguridad Bilingüe", 1, D("66000.00")),
        ("mes", "CUV", 1, D("44000.00"))]
    # Como lo lee el cliente: el puesto, el mes y la modalidad; la unidad,
    # como se la ofrecieron.
    assert pre["renglones"][0]["etiqueta"] == (
        "Conductor de Seguridad Bilingüe · octubre 2029 · lunes a viernes · "
        "el mensual")
    assert pre["renglones"][1]["etiqueta"] == (
        "Toyota RAV4 · octubre 2029 · el mensual")
    assert pre["total"] == D("110000.00")
    assert [r["variante_odoo_id"] for r in pre["renglones"]] == [7101, 7102]
    vals = odoo_facturacion.valores(pre, 33)
    assert odoo_facturacion.es_prefactura({"vals_list": [vals]})
    assert vals["ref"] == f"{folio} · 10/2029"


def test_el_dia_adicional_y_la_hora_extra_del_mes(cliente, sesion, datos,
                                                  lista_de_odoo, odoo,
                                                  monkeypatch):
    from app import horas_extra

    servicio_id, contrato_id = _implantado(cliente, sesion, datos)
    r = cliente.post(f"/implantados/contratos/{contrato_id}/dias-adicionales",
                     json={"fecha": "2029-10-06"}, headers=sesion("consultor"))
    assert r.status_code in (200, 201), r.text
    monkeypatch.setattr(horas_extra, "horas",
                        lambda j: 3 if j.fecha == date(2029, 10, 9) else 0)
    pre = _prefactura_del_mes(_cierre_del_mes(contrato_id))
    assert pre["faltan"] == [], pre["faltan"]
    assert _renglones(pre) == [
        ("mes", "Conductor de Seguridad Bilingüe", 1, D("66000.00")),
        ("mes", "CUV", 1, D("44000.00")),
        ("dia_adicional", "Conductor de Seguridad Bilingüe", 1, D("3000.00")),
        ("horas_extra", "Hora Extra Conductor de Seguridad Bilingüe", 3, D("300.00"))]
    assert pre["renglones"][2]["etiqueta"].endswith("día adicional · 06/10")
    assert pre["total"] == D("113900.00")


def test_el_primer_mes_a_medias_por_dia_con_su_centavo(cliente, sesion, datos,
                                                       lista_de_odoo, odoo):
    """Empieza el lunes 24 de septiembre: cinco dias de servicio. Con un
    mensual que no se reparte parejo, el centavo que sobra va en el ultimo
    puesto y los renglones suman lo del mes."""
    servicio_id, contrato_id = _implantado(
        cliente, sesion, datos, inicio=date(2029, 9, 24),
        conductor="66010", cuv="44010")
    pre = _prefactura_del_mes(_cierre_del_mes(contrato_id))
    assert pre["faltan"] == [], pre["faltan"]
    # 110,020 / 22 = 5,000.91 el dia; 3,000.45 + 2,000.46.
    assert _renglones(pre) == [
        ("mes", "Conductor de Seguridad Bilingüe", 5, D("3000.45")),
        ("mes", "CUV", 5, D("2000.46"))]
    assert pre["renglones"][0]["etiqueta"].endswith("5 días de servicio")
    assert pre["total"] == D("25004.55") == D("5000.91") * 5


def test_el_mes_que_se_cancela_a_la_mitad_va_por_dia(cliente, sesion, datos,
                                                     lista_de_odoo, odoo):
    """Decision 4: cancelado el miercoles 17 de octubre tras trece dias de
    servicio, el mes se cobra por dia, como el primero que empieza a la
    mitad. Cancelado el miercoles 31 --su ultimo dia-- va el mensual."""
    servicio_id, contrato_id = _implantado(cliente, sesion, datos)
    with SessionLocal() as db:
        contrato = db.get(m.ContratoImplantado, contrato_id)
        for j in motor_implantado.jornadas_del_mes(contrato):
            if j.fecha > date(2029, 10, 17):
                j.estatus = m.EstatusJornada.CANCELADA
        db.commit()
    cierre_id = _cierre_del_mes(contrato_id, motivo="cancelacion",
                                abierto=datetime(2029, 10, 17, 12))
    with SessionLocal() as db:
        comparativo = cierre_mes.comparar(db, db.get(m.ContratoImplantado,
                                                     contrato_id))
    assert comparativo["mensual"]["parcial"] is True
    assert comparativo["mensual"]["hasta_dia"] == 17
    assert comparativo["mensual"]["dias_de_servicio"] == 13
    assert comparativo["trabajado"]["importe"] == D("65000.00")
    assert any("se cancelo el dia 17" in n for n in comparativo["notas"])
    pre = _prefactura_del_mes(cierre_id)
    assert _renglones(pre) == [
        ("mes", "Conductor de Seguridad Bilingüe", 13, D("3000.00")),
        ("mes", "CUV", 13, D("2000.00"))]

    # Su ultimo dia de servicio: el mes ya se trabajo entero.
    assert motor_implantado.termina_a_medio_mes(
        2029, 10, m.DiasServicio.LUNES_VIERNES, date(2029, 10, 31)) is False
    assert motor_implantado.termina_a_medio_mes(
        2029, 10, m.DiasServicio.LUNES_VIERNES, date(2029, 10, 17)) is True
    assert motor_implantado.termina_a_medio_mes(
        2029, 10, m.DiasServicio.LUNES_VIERNES, date(2029, 11, 2)) is False


def test_el_mes_sin_desglose_va_en_un_renglon(cliente, sesion, datos,
                                              con_productos, odoo):
    """Precios del mes escritos a mano --por dia y la unidad por mes-- sin
    propuesta ni lista: los dias en un renglon con el producto del puesto
    principal, y la unidad en el suyo. Y de punta a punta: el visto bueno
    del mes manda su prefactura."""
    from test_cierre_mes import _a_las_21, _alta, _avanzar, _cerrar_mes, DIAS

    alta = _alta(cliente, sesion, datos)
    _cerrar_mes(cliente, sesion, alta["servicio_id"])
    with SessionLocal() as db:
        cierre_id = (db.query(m.Cierre)
                     .filter_by(contrato_id=alta["contrato_id"]).one().id)
    t0 = _a_las_21(DIAS[4])
    _avanzar(cierre_id, t0 + timedelta(hours=1))
    envio = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                         headers=sesion("consultor"),
                         params={"ahora": (t0 + timedelta(hours=2)).isoformat()})
    assert envio.status_code == 200, envio.text
    assert envio.json()["factura"]["resultado"] == "en odoo"
    (_, _, cuerpo), = odoo.creadas()
    vals = cuerpo["vals_list"][0]
    assert vals["ref"].endswith(" · 09/2029")
    assert [(r[2]["product_id"], r[2]["quantity"], r[2]["price_unit"])
            for r in vals["invoice_line_ids"]] == [
        (VARIANTE["rol"], 5.0, 2900.0), (VARIANTE["unidad"], 1.0, 66000.0)]
    c = _cierre(cierre_id)
    assert D(str(c.prefactura_total)) == D("80500.00") == D(str(c.total_ejecutado))
    # En Facturacion, junto con los eventuales, con su mes.
    suyo = next(f for f in _bandeja(cliente, sesion)["en_odoo"]
                if f["cierre_id"] == cierre_id)
    assert suyo["periodo"] == "09/2029" and suyo["contrato_id"] == alta["contrato_id"]


def test_el_cliente_sin_ficha_no_deja_dar_el_visto_bueno_del_mes(
        cliente, sesion, datos, odoo):
    from test_cierre_mes import _a_las_21, _alta, _avanzar, _cerrar_mes, DIAS

    alta = _alta(cliente, sesion, datos)
    _cerrar_mes(cliente, sesion, alta["servicio_id"])
    with SessionLocal() as db:
        cierre_id = (db.query(m.Cierre)
                     .filter_by(contrato_id=alta["contrato_id"]).one().id)
    t0 = _a_las_21(DIAS[4])
    _avanzar(cierre_id, t0 + timedelta(hours=1))
    r = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                     headers=sesion("consultor"),
                     params={"ahora": (t0 + timedelta(hours=2)).isoformat()})
    assert r.status_code == 409, r.text
    assert "cliente_sin_odoo" in [o.get("clave")
                                  for o in r.json()["detail"]["observaciones"]]


def test_reparto_por_dia():
    p = mes_odoo.Puesto
    uno = p("persona", 1, None, 1, "Conductor", mes=D("66010"))
    otro = p("unidad", None, 2, 1, "CUV", mes=D("44010"))
    assert mes_odoo.reparto_por_dia([uno, otro], 22, D("5000.91")) == [
        (uno, D("3000.45")), (otro, D("2000.46"))]
    # Dos conductores iguales y nadie solo: no se puede repartir el centavo.
    dos = p("persona", 1, None, 2, "Conductor", mes=D("33010"))
    assert mes_odoo.reparto_por_dia([dos], 22, D("3000.91")) is None
    # Sin el mensual de alguno, tampoco.
    assert mes_odoo.reparto_por_dia([p("persona", 1, None, 1, "x")], 22,
                                    D("100")) is None


def test_el_programa_que_revisa_odoo_ve_lo_mandado(cliente, sesion, datos,
                                                   con_productos, odoo, capsys):
    """El programa de solo lectura dice cuantas prefacturas mando Connect,
    como estan en Odoo y lo que no salio; y ensaya la del mes. No crea
    nada."""
    import reconocer_facturacion

    class Leido(OdooFalso):
        def post(self, url, json):
            modelo, metodo = url.split("/json/2/")[1].split("/")
            if metodo == "fields_get":
                self.pedidos.append((modelo, metodo, json))
                return Respuesta({})
            if metodo in ("has_access", "check_access_rights"):
                self.pedidos.append((modelo, metodo, json))
                return Respuesta(True)
            if (modelo, metodo) == ("account.move", "search_read"):
                dominio = json["domain"]
                if dominio and dominio[0][0] == "id":
                    self.pedidos.append((modelo, metodo, json))
                    return Respuesta([{**f, "name": "/", "amount_untaxed": 25790.0}
                                      for f in self.facturas.values()
                                      if f["id"] in dominio[0][2]])
                if not any(d[0] == "invoice_origin" and d[1] == "=" for d in dominio):
                    self.pedidos.append((modelo, metodo, json))
                    return Respuesta([])
            if metodo == "search_read" and modelo not in ("res.currency",
                                                          "account.move"):
                self.pedidos.append((modelo, metodo, json))
                return Respuesta([])
            return super().post(url, json)

    odoo.__class__ = Leido
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2222)
    _visto_bueno(cliente, sesion, cierre_id)
    assert len(odoo.creadas()) == 1
    assert reconocer_facturacion.main() == 0
    salida = capsys.readouterr().out
    assert len(odoo.creadas()) == 1, "el programa no crea nada"
    assert "8. La del mes" in salida and "9. Las prefacturas que Connect" in salida
    assert "draft" in salida and f"#4821 · {servicio['folio']}" in salida
    assert "secreta-117" not in salida
    assert "Listo. No se escribio nada" in salida

# -*- coding: utf-8 -*-
"""La factura del eventual en Odoo: la prefactura en borrador (seccion
116, entrega 1).

Decision de Salvador (1 oct): al dar el visto bueno, Connect manda a Odoo
una factura de cliente en borrador; el facturista la confirma y la timbra
alla. «Nunca action_post ni timbrar: eso lo hace el facturista.» En esta
entrega nada se manda todavia: aqui se cuida lo que se mandaria.

Lo que se cuida:

  * La conexion de la factura solo lee, pregunta si puede y crea UNA
    factura de cliente en borrador con lo que Connect sabe ponerle.
    Confirmarla, cambiarla, borrarla o crear cualquier otra cosa truena
    antes de salir a la red. La del programa que revisa Odoo, ni eso.
  * La prefactura suma lo mismo que la factura de siempre, renglon por
    renglon --dia, equipo y lo que se cobra-- con el producto de Odoo de
    cada uno; la hora extra con el de su rol y los gastos con el suyo.
  * Lo que falta para mandarla se dice una vez, para quien lo corrige.
  * Mandarla no duplica: si ya hay una viva del mismo servicio, no crea
    otra; la cancelada no cuenta.
"""
from decimal import Decimal

import pytest

from app import cierre as motor
from app import facturacion
from app import models as m
from app import odoo_api, odoo_facturacion
from app.db import SessionLocal
from ayudas import (asignar, configurar_origen, crear_servicio,
                    ejecutar_jornada, jornada, manana)

PARTNER = 9_600_100
VARIANTE = {"rol": 7001, "unidad": 7002, "hora_extra": 7003, "gastos": 7004}
NOMBRE = {"rol": "Conductor de Seguridad Bilingüe", "unidad": "SUBURBAN Blindada",
          "hora_extra": "Hora Extra Conductor de Seguridad",
          "gastos": "Gastos de Operación (Viáticos)"}
CLASE = {"rol": "rol", "unidad": "unidad", "hora_extra": "hora_extra",
         "gastos": "viaticos"}


# ================================================================ el decorado

@pytest.fixture
def con_productos(datos):
    """La lista del cliente de las pruebas como si viniera de Odoo: cada
    precio con su producto y su variante, la hora extra con el suyo, el
    cliente con su ficha y el producto de los gastos. Al terminar, todo
    vuelve a como estaba: la lista y el cliente son de toda la bateria."""
    with SessionLocal() as db:
        cliente = db.get(m.Cliente, datos["cliente_id"])
        lista = cliente.tarifario
        antes = {"cliente": cliente.odoo_id,
                 "lista": (lista.odoo_id, lista.producto_hora_extra_id),
                 "recurso": {x.id: (x.producto_odoo_id, x.producto_hora_extra_id)
                             for x in lista.tarifas_recurso},
                 "vehiculo": {x.id: x.producto_odoo_id
                              for x in lista.tarifas_vehiculo}}
        hechos = {}
        for clave, variante in VARIANTE.items():
            p = m.ProductoOdoo(odoo_id=9_600_000 + variante, nombre=NOMBRE[clave],
                               clase=CLASE[clave], confirmado=True, vendible=True,
                               variante_odoo_id=variante, variantes=1)
            db.add(p)
            db.flush()
            hechos[clave] = p.id
        for x in lista.tarifas_recurso:
            x.producto_odoo_id = hechos["rol"]
            x.producto_hora_extra_id = (hechos["hora_extra"]
                                        if x.precio_hora_extra else None)
        for x in lista.tarifas_vehiculo:
            x.producto_odoo_id = hechos["unidad"]
        cliente.odoo_id = PARTNER
        lista_id = lista.id
        db.commit()
    yield {**hechos, "lista_id": lista_id}
    with SessionLocal() as db:
        cliente = db.get(m.Cliente, datos["cliente_id"])
        cliente.odoo_id = antes["cliente"]
        lista = db.get(m.Tarifario, lista_id)
        lista.odoo_id, lista.producto_hora_extra_id = antes["lista"]
        for x in lista.tarifas_recurso:
            x.producto_odoo_id, x.producto_hora_extra_id = antes["recurso"][x.id]
        for x in lista.tarifas_vehiculo:
            x.producto_odoo_id = antes["vehiculo"][x.id]
        db.flush()
        db.query(m.ProductoOdoo).filter(
            m.ProductoOdoo.id.in_(list(hechos.values()))).delete(
                synchronize_session=False)
        db.commit()


def _eventual(cliente, sesion, datos, offset, gastos="1750", alzado=True,
              horas_extra=2):
    """Dos dias con Juan y la Suburban, cotizados con un monto fijo de
    gastos, trabajados --el primero con horas extra-- y con su cierre."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"])
         for i in range(2)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    dias = servicio["equipos"][0]["jornadas"]
    lineas = []
    for j in dias:
        lineas.append({"fecha": j["fecha"], "tipo": "recurso",
                       "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"]})
        lineas.append({"fecha": j["fecha"], "tipo": "vehiculo",
                       "categoria_id": datos["categorias"]["suv_blindada"]["id"]})
    if gastos:
        lineas.append({"fecha": dias[0]["fecha"], "tipo": "viaticos",
                       "precio_unitario": gastos, "descripcion": "Gastos"})
    r = cliente.post("/cotizaciones", headers=h, json={
        "servicio_id": servicio["id"], "lineas": lineas,
        "viaticos_incluidos": alzado})
    assert r.status_code == 201, r.text
    r = cliente.post(f"/cotizaciones/{r.json()['cotizacion_id']}/autorizar",
                     json={"autorizada_por": "Compras del cliente"}, headers=h)
    assert r.status_code == 200, r.text
    for i, j in enumerate(dias):
        asignar(cliente, h, j["id"], persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        configurar_origen(cliente, h, j["id"])
        ejecutar_jornada(cliente, sesion("juan"), j,
                         horas_extra=horas_extra if i == 0 else 0)
    r = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir", headers=h)
    assert r.status_code == 200, r.text
    return servicio, r.json()["cierre_id"]


def _prefactura(cierre_id, antes=None, **cambios):
    """La prefactura de ese cierre y lo que diria la factura de siempre.
    `antes(db)` cambia algo antes de armarla; nada se guarda."""
    with SessionLocal() as db:
        c = db.get(m.Cierre, cierre_id)
        for campo, valor in cambios.items():
            setattr(c, campo, valor)
        if antes:
            antes(db)
            db.flush()
        pre = odoo_facturacion.prefactura(db, c)
        try:
            armada = facturacion.armar(db, c)
        except Exception:                               # noqa: BLE001
            armada = None
        db.rollback()
        return pre, armada


def _claves(pre) -> list:
    return [f["clave"] for f in pre["faltan"]]


# ================================================================ la conexion

def _valida(**cambios) -> dict:
    v = {"move_type": "out_invoice", "partner_id": PARTNER, "ref": "EP/E-031",
         "currency_id": 33, "invoice_origin": "Connect · EP/E-031",
         "invoice_line_ids": [
             [0, 0, {"display_type": "line_note", "name": "Servicio cancelado"}],
             [0, 0, {"product_id": 7001, "name": "Conductor · 28/10/2026",
                     "quantity": 1.0, "price_unit": 3200.0}]]}
    v.update(cambios)
    return v


def test_la_conexion_de_la_factura_solo_crea_el_borrador():
    odoo = odoo_facturacion.Conexion("https://odoo.invalid", "llave")
    assert odoo.permitido("account.move", "create", {"vals_list": [_valida()]})
    for metodo in ("search_read", "fields_get", "has_access",
                   "check_access_rights"):
        assert odoo.permitido("account.move", metodo, {})

    malos = {
        "confirmarla": ("account.move", "action_post", {"ids": [1]}),
        "cambiarla": ("account.move", "write", {"ids": [1], "vals": {}}),
        "borrarla": ("account.move", "unlink", {"ids": [1]}),
        "cancelarla": ("account.move", "button_cancel", {"ids": [1]}),
        "escribir en su historial": ("account.move", "message_post", {"ids": [1]}),
        "otro modelo": ("res.partner", "create", {"vals_list": [_valida()]}),
        "con contexto": ("account.move", "create",
                         {"vals_list": [_valida()],
                          "context": {"default_state": "posted"}}),
        "dos facturas": ("account.move", "create",
                         {"vals_list": [_valida(), _valida()]}),
        "ya confirmada": ("account.move", "create",
                          {"vals_list": [_valida(state="posted")]}),
        "con su folio": ("account.move", "create",
                         {"vals_list": [_valida(name="INV/2026/00412")]}),
        "con su diario": ("account.move", "create",
                          {"vals_list": [_valida(journal_id=1)]}),
        "nota de credito": ("account.move", "create",
                            {"vals_list": [_valida(move_type="out_refund")]}),
        "de proveedor": ("account.move", "create",
                         {"vals_list": [_valida(move_type="in_invoice")]}),
        "sin cliente": ("account.move", "create",
                        {"vals_list": [_valida(partner_id=False)]}),
        "de otro origen": ("account.move", "create",
                           {"vals_list": [_valida(invoice_origin="SO0042")]}),
        "sin renglones": ("account.move", "create",
                          {"vals_list": [_valida(invoice_line_ids=[])]}),
        "ligar un renglon": ("account.move", "create", {"vals_list": [_valida(
            invoice_line_ids=[[4, 99, 0]])]}),
        "cambiar un renglon": ("account.move", "create", {"vals_list": [_valida(
            invoice_line_ids=[[1, 99, {"price_unit": 1.0}]])]}),
        "reemplazar renglones": ("account.move", "create", {"vals_list": [_valida(
            invoice_line_ids=[[6, 0, [99]]])]}),
        "renglon con su cuenta": ("account.move", "create", {"vals_list": [_valida(
            invoice_line_ids=[[0, 0, {"product_id": 7001, "account_id": 5}]])]}),
        "renglon con impuestos": ("account.move", "create", {"vals_list": [_valida(
            invoice_line_ids=[[0, 0, {"product_id": 7001, "tax_ids": [[6, 0, []]]}]])]}),
        "renglon sin producto": ("account.move", "create", {"vals_list": [_valida(
            invoice_line_ids=[[0, 0, {"name": "algo", "price_unit": 5.0}]])]}),
        "nota con precio": ("account.move", "create", {"vals_list": [_valida(
            invoice_line_ids=[[0, 0, {"display_type": "line_note", "name": "x",
                                      "price_unit": 5.0}]])]}),
        "seccion": ("account.move", "create", {"vals_list": [_valida(
            invoice_line_ids=[[0, 0, {"display_type": "line_section",
                                      "name": "x"}]])]}),
    }
    for que, (modelo, metodo, args) in malos.items():
        assert not odoo.permitido(modelo, metodo, args), que
        # Y truena antes de salir a la red: odoo.invalid no existe.
        with pytest.raises(RuntimeError, match="solo lee y crea la prefactura"):
            odoo.llamar(modelo, metodo, **args)

    # La del programa que revisa Odoo: ni la prefactura.
    revision = odoo_facturacion.Revision("https://odoo.invalid", "llave")
    with pytest.raises(RuntimeError, match="solo lee"):
        revision.llamar("account.move", "create", vals_list=[_valida()])
    assert revision.permitido("account.move", "has_access", {})
    # Y la de siempre sigue sin escribir nada.
    base = odoo_api.Odoo("https://odoo.invalid", "llave")
    with pytest.raises(RuntimeError, match="no escribe en Odoo"):
        base.llamar("account.move", "create", vals_list=[_valida()])


def test_sin_la_llave_no_hay_conexion(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "odoo_base", "https://odoo.prueba")
    monkeypatch.setattr(settings, "odoo_api_key", "la-de-leer")
    monkeypatch.setattr(settings, "odoo_facturacion_api_key", "")
    assert odoo_facturacion.hay_llave() is False
    with pytest.raises(odoo_api.SinConexion, match="ODOO_FACTURACION_API_KEY"):
        odoo_facturacion.conexion()
    monkeypatch.setattr(settings, "odoo_facturacion_api_key", "la-de-facturar")
    odoo = odoo_facturacion.conexion()
    assert isinstance(odoo, odoo_facturacion.Conexion)
    assert odoo.http.headers["Authorization"] == "bearer la-de-facturar"


# ================================================================ mandarla sin duplicar

class Respuesta:
    def __init__(self, datos):
        self.status_code, self._datos = 200, datos

    def json(self):
        return self._datos


class HttpFalso:
    """Lo que la conexion le pide a Odoo, y lo que Odoo contesta."""

    def __init__(self, existentes=()):
        self.existentes, self.pedidos = list(existentes), []

    def post(self, url, json):
        metodo = url.rsplit("/", 1)[1]
        self.pedidos.append((url.split("/json/2/")[1], json))
        if metodo == "search_read":
            return Respuesta(self.existentes)
        if metodo == "create":
            return Respuesta([4821])
        raise AssertionError(url)


PRE = {"faltan": [], "nota": None, "cliente": {"odoo_id": PARTNER},
       "referencia": "EP/E-031", "origen": "Connect · EP/E-031",
       "renglones": [{"variante_odoo_id": 7001, "etiqueta": "Conductor",
                      "cantidad": 2, "precio": Decimal("3200.00")}]}


def test_mandarla_no_duplica():
    odoo = odoo_facturacion.Conexion("https://odoo.prueba", "llave")
    odoo.http = HttpFalso()
    r = odoo_facturacion.crear(odoo, PRE, 33)
    assert r == {"id": 4821, "nueva": True, "estado": "draft"}
    (busca, primero), (crea, cuerpo) = odoo.http.pedidos
    assert busca == "account.move/search_read"
    assert ["invoice_origin", "=", "Connect · EP/E-031"] in primero["domain"]
    assert crea == "account.move/create"
    assert cuerpo["vals_list"] == [{
        "move_type": "out_invoice", "partner_id": PARTNER, "ref": "EP/E-031",
        "currency_id": 33, "invoice_origin": "Connect · EP/E-031",
        "invoice_line_ids": [[0, 0, {"product_id": 7001, "name": "Conductor",
                                     "quantity": 2.0, "price_unit": 3200.0}]]}]
    # El contexto es solo el idioma: nada que la cree confirmada.
    assert set(cuerpo["context"]) == {"lang"}

    # Si ya hay una viva del mismo servicio, no se crea otra.
    for estado in ("draft", "posted"):
        odoo.http = HttpFalso([{"id": 4800, "state": estado}])
        assert odoo_facturacion.crear(odoo, PRE, 33) == {
            "id": 4800, "nueva": False, "estado": estado}
        assert [p for p, _ in odoo.http.pedidos] == ["account.move/search_read"]
    # La cancelada no cuenta: al corregir sale una nueva.
    odoo.http = HttpFalso([{"id": 4800, "state": "cancel"}])
    assert odoo_facturacion.crear(odoo, PRE, 33)["id"] == 4821

    # A la que le falta algo no se manda, ni se busca.
    odoo.http = HttpFalso()
    with pytest.raises(ValueError):
        odoo_facturacion.crear(odoo, {**PRE, "faltan": [{"clave": "x"}]}, 33)
    assert odoo.http.pedidos == []


def test_la_moneda_por_su_nombre():
    class Monedas(HttpFalso):
        def post(self, url, json):
            dominio = json["domain"]
            filas = [{"id": 33, "name": "MXN", "active": True},
                     {"id": 2, "name": "USD", "active": False}]
            return Respuesta([f for f in filas if f["name"] == dominio[0][2]])

    odoo = odoo_facturacion.Revision("https://odoo.prueba", "llave")
    odoo.http = Monedas()
    assert odoo_facturacion.moneda_de(odoo, "MXN") == 33
    # Apagada en Odoo: una factura en esa moneda no la acepta.
    assert odoo_facturacion.moneda_de(odoo, "USD") is None
    assert odoo_facturacion.moneda_de(odoo, "BRL") is None


# ================================================================ la prefactura

def test_la_prefactura_dice_lo_mismo_que_la_factura(cliente, sesion, datos,
                                                    con_productos):
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2101)
    pre, armada = _prefactura(cierre_id)
    assert pre["faltan"] == []
    assert pre["referencia"] == servicio["folio"]
    assert pre["origen"] == f"Connect · {servicio['folio']}"
    assert pre["moneda"] == "MXN" and pre["nota"] is None
    # Lo mismo que la factura de siempre.
    assert pre["total"] == Decimal(armada["total"]) == Decimal("25790.00")

    tipos = [(r["tipo"], r["cantidad"], r["precio"], r["variante_odoo_id"])
             for r in pre["renglones"]]
    assert tipos == [
        ("recurso", 1, Decimal("3200.00"), VARIANTE["rol"]),
        ("vehiculo", 1, Decimal("8500.00"), VARIANTE["unidad"]),
        ("horas_extra", 2, Decimal("320.00"), VARIANTE["hora_extra"]),
        ("recurso", 1, Decimal("3200.00"), VARIANTE["rol"]),
        ("vehiculo", 1, Decimal("8500.00"), VARIANTE["unidad"]),
        ("gastos", 1, Decimal("1750.00"), VARIANTE["gastos"])]
    primero, _, extra = pre["renglones"][:3]
    dia = manana(2101)
    assert primero["etiqueta"].startswith(f"{NOMBRE['rol']} · {dia:%d/%m/%Y} · Equipo ")
    assert primero["etiqueta"].endswith(" · Día completo")
    assert extra["etiqueta"].startswith(NOMBRE["hora_extra"])
    assert extra["etiqueta"].endswith(" · 2 h") and extra["importe"] == Decimal("640.00")
    gastos = pre["renglones"][-1]
    assert gastos["etiqueta"] == (f"{NOMBRE['gastos']} · {servicio['folio']} · "
                                  "monto fijo")

    vals = odoo_facturacion.valores(pre, 33)
    assert odoo_facturacion.es_prefactura({"vals_list": [vals]})
    assert (vals["partner_id"], vals["ref"], vals["currency_id"]) == (
        PARTNER, servicio["folio"], 33)
    assert len(vals["invoice_line_ids"]) == 6


def test_la_cancelacion_que_se_cobra_completa(cliente, sesion, datos,
                                              con_productos):
    """Con la cotizacion autorizada tal cual, renglon por renglon, y su
    nota (seccion 105). La hora extra no: no se cobro lo trabajado."""
    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2104)
    pre, armada = _prefactura(cierre_id, cobro=motor.COBRO_COMPLETO)
    assert pre["faltan"] == []
    assert pre["nota"].startswith("Servicio cancelado")
    assert [r["tipo"] for r in pre["renglones"]] == [
        "recurso", "vehiculo", "recurso", "vehiculo", "gastos"]
    assert pre["total"] == Decimal(armada["total"]) == Decimal("25150.00")
    vals = odoo_facturacion.valores(pre, 33)
    assert vals["invoice_line_ids"][0] == [0, 0, {"display_type": "line_note",
                                                  "name": pre["nota"]}]
    assert odoo_facturacion.es_prefactura({"vals_list": [vals]})


def test_en_el_idioma_de_la_cotizacion(cliente, sesion, datos, con_productos):
    _, cierre_id = _eventual(cliente, sesion, datos, offset=2107)

    def en_ingles(db):
        c = db.get(m.Cierre, cierre_id)
        for cot in db.query(m.Cotizacion).filter_by(servicio_id=c.servicio_id):
            cot.idioma = "en"

    pre, _ = _prefactura(cierre_id, antes=en_ingles)
    assert " · Team " in pre["renglones"][0]["etiqueta"]
    assert pre["renglones"][0]["etiqueta"].endswith(" · Full day")
    assert pre["renglones"][-1]["etiqueta"].endswith(" · fixed amount")


def test_sin_la_lista_de_odoo_dice_lo_que_falta(cliente, sesion, datos):
    """La lista del cliente de las pruebas se capturo a mano y el cliente
    no tiene ficha en Odoo: no se manda, y se dice por que, una vez cada
    cosa aunque el servicio sea de dos dias."""
    _, cierre_id = _eventual(cliente, sesion, datos, offset=2110, gastos=None)
    pre, armada = _prefactura(cierre_id)
    assert _claves(pre) == ["cliente_sin_odoo", "sin_producto", "sin_producto",
                            "sin_producto"]
    assert pre["total"] == Decimal(armada["total"])      # la cifra, igual
    assert "se capturó a mano" in pre["faltan"][1]["texto"]
    with pytest.raises(ValueError):
        odoo_facturacion.valores(pre, 33)


def test_lo_que_falta_se_dice_para_quien_lo_corrige(cliente, sesion, datos,
                                                    con_productos):
    _, cierre_id = _eventual(cliente, sesion, datos, offset=2113)

    def descompuesto(db):
        rol = db.get(m.ProductoOdoo, con_productos["rol"])
        rol.variante_odoo_id, rol.variantes = None, 3
        unidad = db.get(m.ProductoOdoo, con_productos["unidad"])
        unidad.variante_odoo_id, unidad.variantes = None, None
        # La lista ya es de Odoo, y la hora extra todavia no sabe su
        # producto: lo trae la lectura de cada hora.
        lista = db.get(m.Tarifario, con_productos["lista_id"])
        lista.odoo_id = 9_600_900
        for x in lista.tarifas_recurso:
            x.producto_hora_extra_id = None
        gastos = db.get(m.ProductoOdoo, con_productos["gastos"])
        gastos.nombre = "Viáticos"

    pre, _ = _prefactura(cierre_id, antes=descompuesto)
    faltan = {f["clave"]: f for f in pre["faltan"]}
    assert list(faltan) == ["varias_variantes", "sin_variante",
                            "producto_por_leer", "sin_producto_gastos"]
    assert faltan["varias_variantes"]["texto"] == (
        f"«{NOMBRE['rol']}»: en Odoo tiene 3 variantes y no se sabe con cuál "
        "se cobra.")
    assert "lectura de los tarifarios" in faltan["producto_por_leer"]["texto"]
    assert "Gastos de Operación (Viáticos)" in faltan["sin_producto_gastos"]["texto"]

    # Dos productos que se llaman igual: no se adivina.
    def dos_de_gastos(db):
        db.add(m.ProductoOdoo(odoo_id=9_600_999, nombre="GASTOS DE OPERACION (VIATICOS)",
                              clase="viaticos", confirmado=True, vendible=True,
                              variante_odoo_id=7999, variantes=1))

    pre, _ = _prefactura(cierre_id, antes=dos_de_gastos)
    assert _claves(pre) == ["varios_de_gastos"]


def test_el_mes_del_implantado_va_por_su_camino(monkeypatch):
    """Desde la seccion 117 el mes del implantado tambien sale a Odoo
    (decision 5 de Salvador), con su propia prefactura: un renglon por
    puesto y por unidad. Sus pruebas viven en test_prefactura_odoo.py."""
    from app import odoo_facturacion_mes
    monkeypatch.setattr(odoo_facturacion_mes, "prefactura_del_mes",
                        lambda db, cierre: {"del_mes": cierre.contrato_id})
    assert odoo_facturacion.prefactura(None, m.Cierre(contrato_id=5)) == {
        "del_mes": 5}


# ================================================================ lo que se ve

def test_la_pantalla_de_odoo_dice_si_esta_la_llave(cliente, sesion, monkeypatch):
    from app.config import settings
    r = cliente.get("/odoo/estado", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["factura"] == {"llave": False}
    monkeypatch.setattr(settings, "odoo_base", "https://odoo.prueba")
    monkeypatch.setattr(settings, "odoo_facturacion_api_key", "secreta-116")
    r = cliente.get("/odoo/estado", headers=sesion("admin"))
    assert r.json()["factura"] == {"llave": True}
    assert "secreta-116" not in r.text                  # nunca la llave


def test_el_programa_que_revisa_odoo_no_escribe(cliente, sesion, datos,
                                                con_productos, monkeypatch,
                                                capsys):
    """Corre de punta a punta contra un Odoo de mentiras: solo lee y
    pregunta, con la conexion que no puede crear, y arma la prefactura del
    eventual con visto bueno sin mandarla."""
    import reconocer_facturacion
    from app.config import settings

    servicio, cierre_id = _eventual(cliente, sesion, datos, offset=2116)
    r = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text

    class OdooLeido(HttpFalso):
        def post(self, url, json):
            modelo, metodo = url.split("/json/2/")[1].split("/")
            self.pedidos.append((modelo, metodo))
            if metodo == "fields_get":
                return Respuesta({"state": {"type": "selection",
                                            "selection": [["draft", "Borrador"]]},
                                  "l10n_mx_edi_cfdi_uuid": {
                                      "type": "char", "string": "Fiscal Folio"}})
            if metodo in ("has_access", "check_access_rights"):
                return Respuesta(True)
            if modelo == "res.currency":
                return Respuesta([{"id": 33, "name": "MXN", "active": True}])
            return Respuesta([])

    usadas, http = [], OdooLeido()
    original = odoo_facturacion.conexion

    def conexion(clase=odoo_facturacion.Conexion):
        usadas.append(clase)
        odoo = original(clase)
        odoo.http = http
        return odoo

    monkeypatch.setattr(odoo_facturacion, "conexion", conexion)
    monkeypatch.setattr(settings, "odoo_base", "https://odoo.prueba")
    monkeypatch.setattr(settings, "odoo_facturacion_api_key", "secreta-116")
    assert reconocer_facturacion.main() == 0
    salida = capsys.readouterr().out
    assert usadas == [odoo_facturacion.Revision]
    assert not [p for p in http.pedidos if p[1] not in (
        "search_read", "fields_get", "has_access", "check_access_rights")]
    assert "secreta-116" not in salida
    assert "l10n_mx_edi_cfdi_uuid" in salida
    assert f"{servicio['folio']} ·" in salida and "Asi llegaria" in salida
    assert "Listo. No se escribio nada" in salida

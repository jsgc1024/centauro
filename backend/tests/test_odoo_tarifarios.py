# -*- coding: utf-8 -*-
"""Los tarifarios, leidos de Odoo (seccion 77).

Contra un Odoo de mentiras, en memoria: ninguna prueba sale a la red.

Lo que se cuida: el precio sale como lo calcula Odoo --la regla mas
especifica, la mas nueva, y lo que el cliente no negocio, de la general de
su pais--; solo pone precio lo que finanzas confirmo en la tabla de
productos; a un cliente no se le cambia a una lista sin precios; lo de
Odoo no se edita en Centauro; y la de cada hora espera a la primera a
mano.
"""
import copy
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app import models as m
from app import odoo_api, odoo_tarifarios
from app import odoo_tarifarios_reglas as reglas

LISTA0, PRODUCTO0, SOCIO0, REGLA0 = 9_300_000, 9_310_000, 9_320_000, 9_330_000
GRUPO_MX, GRUPO_BR = 9_340_001, 9_340_002
PAIS_MX, PAIS_BR = 156, 31
MONEDA_ID = {"MXN": 33, "USD": 2, "BRL": 7}
PREFIJO = "Tarifas Odoo"
CAMPO = "x_studio_lista_de_implantados"
CAMPO_IMPLANTADOS = {CAMPO: {"type": "many2one", "relation": "product.pricelist",
                             "string": "Lista de implantados"}}


# ================================================================ el Odoo falso

def _ids(valor) -> list:
    """Los ids de un many2one ([id, nombre]) o de un many2many ([ids])."""
    if valor in (False, None):
        return []
    if isinstance(valor, (list, tuple)):
        if len(valor) == 2 and isinstance(valor[1], str):
            return [valor[0]]
        return list(valor)
    return [valor]


def _termino(fila, campo, operador, valor) -> bool:
    actual = fila.get(campo, False)
    if operador == "=":
        return (valor in _ids(actual) if isinstance(actual, (list, tuple))
                else actual == valor)
    if operador == "in":
        return bool(set(_ids(actual)) & set(valor))
    if operador == ">":
        return (actual or 0) > valor
    raise AssertionError((campo, operador))


def cumple(fila, dominio) -> bool:
    """Un dominio de Odoo en notacion polaca: «|» toma los dos que siguen."""
    def uno(i):
        x = dominio[i]
        if x == "|":
            a, i = uno(i + 1)
            b, i = uno(i)
            return a or b, i
        return _termino(fila, *x), i + 1
    i, todo = 0, True
    while i < len(dominio):
        r, i = uno(i)
        todo = todo and r
    return todo


class OdooFalso:
    """Un Odoo en memoria: {modelo: [filas]}."""

    def __init__(self, tablas, campos_socio=None):
        self.tablas = tablas
        self.campos_socio = (CAMPO_IMPLANTADOS if campos_socio is None
                             else campos_socio)

    def leer(self, modelo, dominio, campos, archivados=False):
        filas = [f for f in self.tablas.get(modelo, [])
                 if archivados or f.get("active", True)]
        return [{"id": f["id"], **{c: f.get(c, False) for c in campos}}
                for f in filas if cumple(f, dominio)]

    def campos(self, modelo, atributos=None):
        assert modelo == "res.partner"
        return {"name": {"type": "char", "string": "Nombre"},
                "property_product_pricelist": {
                    "type": "many2one", "relation": "product.pricelist",
                    "string": "Lista de precios"},
                **self.campos_socio}

    # --------------------------------------------------- para cambiar cosas
    def fila(self, modelo, odoo_id):
        return next(f for f in self.tablas[modelo] if f["id"] == odoo_id)

    def regla(self, n):
        return self.fila("product.pricelist.item", REGLA0 + n)

    def lista(self, n):
        return self.fila("product.pricelist", LISTA0 + n)

    def socio(self, n):
        return self.fila("res.partner", SOCIO0 + n)

    def producto(self, n):
        return self.fila("product.template", PRODUCTO0 + n)


# ================================================================ el mundo

PRODUCTOS = {
    1: ("Conductor de Seguridad Bilingüe", 3500, "service"),
    2: ("Agente de Seguridad", 4000, "service"),
    3: ("SUBURBAN Blindada", 9000, "service"),
    4: ("Conductor + CUV (Transfer)", 2800, "service"),
    5: ("Hora Extra", 350, "service"),
    6: ("Viáticos", 0, "service"),
    7: ("Central de Inteligencia", 15000, "service"),
    8: ("Conductor de Seguridad Federal", 5000, "service"),
    9: ("MINIVAN (Medio día)", 1900, "service"),
    10: ("Rastreador GPS", 1200, "consu"),
}
LISTAS = {
    1: ("General México", "MXN", [GRUPO_MX]),
    2: ("HASBRO", "MXN", []),
    3: ("Amazon USD", "USD", []),
    4: ("HASBRO Implantados", "MXN", []),
    5: ("Lista vieja", "MXN", []),
    6: ("General Brasil", "BRL", [GRUPO_BR]),
}
# (cliente, nombre, su lista, la de sus implantados)
SOCIOS = [(1, "HASBRO", 2, 4), (2, "Cliente General", 1, None),
          (3, "Amazon", 3, None)]


def m2o(n, nombres, base):
    return [base + n, nombres[n][0]] if n else False


def fija(n, en, producto, precio, **extra):
    """Una regla de precio fijo para un producto."""
    return {"id": REGLA0 + n, "pricelist_id": m2o(en, LISTAS, LISTA0),
            "applied_on": "1_product",
            "product_tmpl_id": m2o(producto, PRODUCTOS, PRODUCTO0),
            "product_id": False, "categ_id": False, "min_quantity": 0,
            "compute_price": "fixed", "fixed_price": precio,
            "base": "list_price", "date_start": False, "date_end": False,
            **extra}


def resto(n, en, de):
    """«Todo lo demas, de otra lista»: asi se hace en Odoo que lo que el
    cliente no negocio salga de la general."""
    return {"id": REGLA0 + n, "pricelist_id": m2o(en, LISTAS, LISTA0),
            "applied_on": "3_global", "product_tmpl_id": False,
            "product_id": False, "categ_id": False, "min_quantity": 0,
            "compute_price": "formula", "base": "pricelist",
            "base_pricelist_id": m2o(de, LISTAS, LISTA0),
            "price_discount": 0, "price_surcharge": 0, "price_round": 0,
            "price_min_margin": 0, "price_max_margin": 0,
            "date_start": False, "date_end": False}


def mundo() -> dict:
    """Las tablas de Odoo de las pruebas. Cada prueba recibe las suyas."""
    return copy.deepcopy({
        "product.template": [
            {"id": PRODUCTO0 + n, "name": nombre, "list_price": precio,
             "type": tipo, "sale_ok": True, "active": True,
             "categ_id": [1, "All"], "uom_id": [1, "Unidades"]}
            for n, (nombre, precio, tipo) in PRODUCTOS.items()],
        "product.product": [],
        "product.category": [{"id": 1, "parent_path": "1/"}],
        "product.pricelist": [
            {"id": LISTA0 + n, "name": nombre,
             "currency_id": [MONEDA_ID[moneda], moneda],
             "country_group_ids": grupos, "active": True}
            for n, (nombre, moneda, grupos) in LISTAS.items()],
        "product.pricelist.item": [
            fija(1, 1, 1, 3300), fija(2, 1, 3, 8800), fija(3, 1, 5, 330),
            fija(10, 2, 1, 3000), fija(11, 2, 4, 2500), resto(12, 2, 1),
            fija(20, 3, 1, 180), resto(21, 3, 1),
            fija(30, 4, 2, 3600), resto(31, 4, 2),
            fija(40, 5, 1, 2000), fija(41, 5, 8, 5500),
            fija(50, 6, 1, 900)],
        "res.currency": [
            {"id": MONEDA_ID["MXN"], "name": "MXN", "rate": 1.0, "active": True},
            {"id": MONEDA_ID["USD"], "name": "USD", "rate": 0.05, "active": True},
            {"id": MONEDA_ID["BRL"], "name": "BRL", "rate": 0.3, "active": True}],
        "res.country.group": [{"id": GRUPO_MX, "country_ids": [PAIS_MX]},
                              {"id": GRUPO_BR, "country_ids": [PAIS_BR]}],
        "res.country": [{"id": PAIS_MX, "code": "MX"},
                        {"id": PAIS_BR, "code": "BR"}],
        "res.partner": [
            {"id": SOCIO0 + n, "name": nombre, "is_company": True,
             "property_product_pricelist": m2o(lista, LISTAS, LISTA0),
             CAMPO: m2o(implantados, LISTAS, LISTA0)}
            for n, nombre, lista, implantados in SOCIOS],
    })


# ================================================================ fixtures

@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture(autouse=True)
def sin_rastro(base_de_pruebas):
    yield
    de_odoo = "SELECT id FROM tarifario WHERE odoo_id IS NOT NULL"
    with base_de_pruebas.begin() as con:
        con.execute(text("DELETE FROM cliente WHERE odoo_id >= :o OR nombre LIKE :p"),
                    {"o": SOCIO0, "p": f"{PREFIJO}%"})
        for tabla in ("tarifa_recurso", "tarifa_vehiculo", "tarifa_paquete"):
            con.execute(text(f"DELETE FROM {tabla} WHERE tarifario_id IN ({de_odoo})"))
        con.execute(text(f"UPDATE cliente SET tarifario_implantado_id = NULL "
                         f"WHERE tarifario_implantado_id IN ({de_odoo})"))
        con.execute(text(f"DELETE FROM tarifario WHERE odoo_id IS NOT NULL"))
        con.execute(text("DELETE FROM producto_odoo"))


@pytest.fixture
def clientes(db):
    """Los tres clientes de Odoo, ya leidos, con el tarifario de antes."""
    mx = db.query(m.Pais).filter_by(codigo="MX").one()
    antes = db.query(m.Tarifario).filter_by(nombre="General Mexico",
                                            odoo_id=None).one()
    ids = {}
    for n, nombre, _, _ in SOCIOS:
        c = m.Cliente(nombre=f"{PREFIJO} {nombre}", pais_id=mx.id,
                      odoo_id=SOCIO0 + n, tarifario_id=antes.id, activo=True,
                      odoo_sincronizado_en=datetime(2026, 9, 1, 10))
        db.add(c)
        db.flush()
        ids[n] = c.id
    db.commit()
    return ids


def confirmar_todo(db, odoo):
    """Finanzas trae los productos y confirma lo que Centauro sugirio."""
    odoo_tarifarios.leer_productos(db, odoo)
    for p in db.query(m.ProductoOdoo).filter(m.ProductoOdoo.clase.isnot(None)):
        p.confirmado = True
    db.commit()


def leer(db, odoo, ensayo=False, **kwargs):
    db.expire_all()
    return odoo_tarifarios.sincronizar(db, odoo, ensayo=ensayo, **kwargs)


def tarifario(db, n) -> m.Tarifario:
    db.expire_all()
    return db.query(m.Tarifario).filter_by(odoo_id=LISTA0 + n).one()


def precios(t: m.Tarifario) -> dict:
    """{(que, modalidad): (precio, origen)} de un tarifario."""
    salida = {}
    for x in t.tarifas_recurso:
        salida[(x.perfil.codigo, x.modalidad.codigo.value)] = (x.precio, x.origen)
    for x in t.tarifas_vehiculo:
        salida[(x.categoria.codigo, x.modalidad.codigo.value)] = (x.precio, x.origen)
    for x in t.tarifas_paquete:
        salida[(f"{x.perfil.codigo}+{x.categoria.codigo}",
                x.modalidad.codigo.value)] = (x.precio, x.origen)
    return salida


def D(valor) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"))


def conectar(monkeypatch, odoo):
    from app.config import settings

    monkeypatch.setattr(odoo_api, "cliente", lambda: odoo)
    monkeypatch.setattr(settings, "odoo_base", "https://odoo.prueba")
    monkeypatch.setattr(settings, "odoo_api_key", "llave")


# ================================================================ las reglas

def test_sugiere_que_es_cada_producto():
    perfiles = reglas.perfiles_por_tipo([
        {"id": 1, "codigo": "conductor_seguridad", "nombre": "Conductor de seguridad"},
        {"id": 2, "codigo": "agente_seguridad", "nombre": "Agente de seguridad"}])
    categorias = reglas.categorias_por_tipo([
        {"id": 10, "codigo": "suv", "nombre": "SUV", "blindado": False},
        {"id": 11, "codigo": "suv_blindada", "nombre": "SUV Blindada", "blindado": True},
        {"id": 12, "codigo": "minivan", "nombre": "Minivan", "blindado": False},
        {"id": 13, "codigo": "van_10", "nombre": "Van 10 pax", "blindado": False}])

    def que(nombre, tipo="service"):
        s = reglas.sugerir({"name": nombre, "type": tipo}, perfiles, categorias)
        return s["clase"], s["perfil_id"], s["categoria_id"], s["modalidad"]

    assert que("Conductor de Seguridad Bilingüe") == ("rol", 1, None, "full_day")
    assert que("Security Driver") == ("rol", 1, None, "full_day")
    assert que("Agente de Seguridad (Medio día)") == ("rol", 2, None, "medio_dia")
    assert que("SUBURBAN Blindada") == ("unidad", None, 11, "full_day")
    assert que("Suburban") == ("unidad", None, 10, "full_day")
    # «minivan» no es «van».
    assert que("MINIVAN (Transfer)") == ("unidad", None, 12, "transfer")
    assert que("Hiace 10 pax") == ("unidad", None, 13, "full_day")
    assert que("Conductor + Suburban Blindada (Transfer)") == (
        "paquete", 1, 11, "transfer")
    assert que("Hora Extra Conductor")[0] == "hora_extra"
    assert que("Travel expenses")[0] == "viaticos"
    assert que("Booking fee")[0] == "viaticos"
    assert que("Central de Inteligencia")[0] == "no_ep"
    assert que("Rastreador", tipo="consu")[0] == "no_ep"
    # Lo que no se sabe no se adivina: lo decide finanzas.
    assert que("Conductor de Seguridad Federal")[0] is None
    assert que("Conductor + Helicoptero")[0] is None
    assert que("Consultoria")[0] is None


def regla(n, lista, **k):
    r = {"id": n, "pricelist_id": [lista, ""], "applied_on": "3_global",
         "min_quantity": 0, "compute_price": "fixed", "fixed_price": 0,
         "base": "list_price"}
    r.update(k)
    return r


def de_producto(n, lista, producto, precio, **k):
    return regla(n, lista, applied_on="1_product",
                 product_tmpl_id=[producto, ""], fixed_price=precio, **k)


def motor(reglas_odoo, tasas=None, variantes=None):
    listas = {1: {"nombre": "General", "moneda": "MXN"},
              2: {"nombre": "Cliente", "moneda": "MXN"},
              3: {"nombre": "Dolares", "moneda": "USD"}}
    productos = {10: {"precio": 1000, "categoria": 5},
                 11: {"precio": 500, "categoria": 6},
                 12: {"precio": 800, "categoria": 7}}
    categorias = {5: "1/5/", 6: "1/6/", 7: "1/5/7/"}
    return reglas.Listas(listas, reglas_odoo, productos, categorias,
                         tasas or {"MXN": 1, "USD": 0.05}, date(2026, 9, 26),
                         variantes=variantes)


def test_gana_la_regla_mas_especifica_y_la_mas_nueva():
    listas = motor([regla(1, 2, fixed_price=100),
                    regla(2, 2, applied_on="2_product_category",
                          categ_id=[5, ""], fixed_price=200),
                    de_producto(3, 2, 10, 300),
                    de_producto(4, 2, 10, 350)])
    assert listas.precio(2, 10)["precio"] == D(350)      # la mas nueva
    assert listas.precio(2, 10)["origen"] == reglas.PROPIO
    # La categoria alcanza a sus hijas; la que no es de ella, a todo.
    assert listas.precio(2, 12)["precio"] == D(200)
    assert listas.precio(2, 11)["precio"] == D(100)
    # Sin ninguna regla, el «Precio de venta».
    sin_reglas = listas.precio(1, 10)
    assert (sin_reglas["precio"], sin_reglas["origen"]) == (D(1000), reglas.PRECIO_VENTA)


def test_la_variante_cuenta_como_su_producto():
    listas = motor([regla(1, 2, applied_on="0_product_variant",
                          product_tmpl_id=False, product_id=[77, ""],
                          fixed_price=700)], variantes={77: 10})
    assert listas.precio(2, 10)["precio"] == D(700)


def test_descuento_formula_y_redondeo():
    listas = motor([regla(1, 2, compute_price="percentage", percent_price=10),
                    regla(2, 1, compute_price="formula", price_discount=10,
                          price_round=100, price_surcharge=25)])
    assert listas.precio(2, 10)["precio"] == D(900)
    # 500 menos 10% es 450; al cien mas cercano, 500; mas 25.
    assert listas.precio(1, 11)["precio"] == D(525)
    assert listas.precio(1, 10)["precio"] == D(925)


def test_vigencia_y_cantidad_minima():
    vencida = de_producto(1, 2, 10, 300, date_end="2026-08-31")
    futura = de_producto(2, 2, 10, 400, date_start="2026-10-01")
    de_mayoreo = de_producto(3, 2, 10, 500, min_quantity=5)
    assert motor([vencida, futura, de_mayoreo]).precio(2, 10)["precio"] == D(1000)
    vigente = de_producto(4, 2, 10, 600, min_quantity=1,
                          date_start="2026-09-01", date_end="2026-09-30")
    assert motor([vencida, futura, de_mayoreo, vigente]).precio(2, 10)["precio"] == D(600)


def test_lo_que_no_se_sabe_leer_se_dice():
    costo = motor([regla(1, 2, compute_price="formula", base="standard_price")])
    assert costo.precio(2, 10)["precio"] is None
    assert "standard_price" in costo.precio(2, 10)["problema"]
    margen = motor([regla(1, 2, compute_price="formula", price_min_margin=50)])
    assert "margen" in margen.precio(2, 10)["problema"]
    circulo = motor([regla(1, 1, compute_price="formula", base="pricelist",
                           base_pricelist_id=[2, ""]),
                     regla(2, 2, compute_price="formula", base="pricelist",
                           base_pricelist_id=[1, ""])])
    assert "sin fin" in circulo.precio(1, 10)["problema"]
    sin_tasa = motor([], tasas={"MXN": 1})
    assert sin_tasa.precio(3, 10)["problema"] == "sin tipo de cambio"


def test_lo_de_otra_lista_en_su_moneda():
    listas = motor([de_producto(1, 1, 10, 3300),
                    regla(2, 3, compute_price="formula", base="pricelist",
                          base_pricelist_id=[1, ""])])
    r = listas.precio(3, 10)
    assert (r["precio"], r["origen"], r["de_lista"]) == (D(165), reglas.OTRA, 1)
    # Lo que la general no pacto sigue siendo «Precio de venta».
    r = listas.precio(3, 11)
    assert (r["precio"], r["origen"]) == (D(25), reglas.PRECIO_VENTA)
    assert listas.resto_de(3) == ("General", 1)
    assert listas.resto_de(1) == ("", None)


def test_dos_productos_para_lo_mismo():
    """«Conductor» y su gemelo en ingles: gana el que la lista pacto; si
    empatan con precios distintos no se escoge."""
    productos = [
        {"id": 1, "odoo_id": 10, "nombre": "Conductor", "clase": "rol",
         "perfil_id": 1, "modalidad": "full_day", "vendible": True},
        {"id": 2, "odoo_id": 11, "nombre": "Driver", "clase": "rol",
         "perfil_id": 1, "modalidad": "full_day", "vendible": True},
        {"id": 3, "odoo_id": 12, "nombre": "Agente viejo", "clase": "rol",
         "perfil_id": 2, "modalidad": "full_day", "vendible": False},
    ]
    clave, viejo = ("rol", 1, None, "full_day"), ("rol", 2, None, "full_day")

    pactado, conflictos, _ = reglas.precios_de_la_lista(
        motor([de_producto(1, 2, 11, 3000)]), 2, productos, {1})
    assert pactado[clave]["precio"] == D(3000) and pactado[clave]["producto"] == "Driver"
    assert not conflictos
    # Lo que ya no se vende no pone precio... salvo que la lista lo pacte.
    assert viejo not in pactado

    empate, conflictos, _ = reglas.precios_de_la_lista(motor([]), 2, productos, {1})
    assert clave not in empate
    assert conflictos[0]["productos"] == [("Conductor", D(1000)), ("Driver", D(500))]
    # Con uno preferido por finanzas, manda ese.
    con_preferido = [productos[0], {**productos[1], "preferido": True}, productos[2]]
    manda, conflictos, _ = reglas.precios_de_la_lista(motor([]), 2, con_preferido, {1})
    assert not conflictos and manda[clave]["producto"] == "Driver"
    # ...pero no le gana a lo que la lista pacto.
    pactado, _, _ = reglas.precios_de_la_lista(
        motor([de_producto(1, 2, 10, 2900)]), 2, con_preferido, {1})
    assert pactado[clave]["producto"] == "Conductor"

    con_viejo, _, _ = reglas.precios_de_la_lista(
        motor([de_producto(1, 2, 12, 4100)]), 2, productos, {1})
    assert con_viejo[viejo]["precio"] == D(4100)

    de_la_general, _, _ = reglas.precios_de_la_lista(
        motor([de_producto(1, 1, 10, 3300), de_producto(2, 1, 11, 3300),
               regla(3, 2, compute_price="formula", base="pricelist",
                     base_pricelist_id=[1, ""])]), 2, productos, {1})
    assert de_la_general[clave]["origen"] == reglas.GENERAL
    assert de_la_general[clave]["producto_id"] == 1      # empate sin diferencia


def test_el_pais_de_cada_lista():
    paises = {"MX": 1, "BR": 2}
    grupos = {100: {"MX"}, 200: {"BR"}, 300: {"MX", "BR"}}
    pais = reglas.pais_de_la_lista
    assert pais({"grupos": [100], "moneda": "MXN"}, set(), paises, grupos) == (1, [1])
    assert pais({"grupos": [300], "moneda": "MXN"}, set(), paises, grupos) == (None, [1, 2])
    # La de un cliente: el pais de sus clientes; sin clientes, su moneda.
    assert pais({"grupos": [], "moneda": "USD"}, {2}, paises, grupos) == (2, [])
    assert pais({"grupos": [], "moneda": "BRL"}, set(), paises, grupos) == (2, [])
    assert pais({"grupos": [], "moneda": "USD"}, set(), paises, grupos) == (1, [])


# ================================================================ la lectura

def test_sin_productos_confirmados_nadie_cambia_de_tarifario(db, clientes):
    """El primer ensayo, antes de que finanzas confirme la tabla: no hay
    precio que leer, y se dice que falta."""
    informe = leer(db, OdooFalso(mundo()), ensayo=True)
    assert informe["leidas"] == 6 and informe["precios"] == 0
    assert not informe["cambian"]
    tipos = {p["tipo"] for p in informe["pendientes"]}
    assert {"producto_sin_confirmar", "lista_sin_precios"} <= tipos
    sin_confirmar = {p["producto"] for p in informe["pendientes"]
                     if p["tipo"] == "producto_sin_confirmar"}
    assert "Conductor de Seguridad Bilingüe" in sin_confirmar


def test_el_ensayo_no_guarda_nada(db, clientes):
    odoo = OdooFalso(mundo())
    confirmar_todo(db, odoo)
    informe = leer(db, odoo, ensayo=True)
    assert len(informe["cambian"]) == 2
    db.expire_all()
    assert db.query(m.Tarifario).filter(m.Tarifario.odoo_id.isnot(None)).count() == 0
    assert db.get(m.Cliente, clientes[1]).tarifario.odoo_id is None
    assert not odoo_tarifarios.en_marcha(db)


def test_los_precios_como_los_calcula_odoo(db, clientes):
    odoo = OdooFalso(mundo())
    confirmar_todo(db, odoo)
    informe = leer(db, odoo)
    fd, md, tr = "full_day", "medio_dia", "transfer"
    conductor, agente = "conductor_seguridad", "agente_seguridad"
    P, G, V, O = reglas.PROPIO, reglas.GENERAL, reglas.PRECIO_VENTA, reglas.OTRA

    general = tarifario(db, 1)
    assert general.general and db.get(m.Pais, general.pais_id).codigo == "MX"
    assert general.moneda == m.Moneda.MXN
    assert precios(general) == {
        (conductor, fd): (D(3300), P), (agente, fd): (D(4000), V),
        ("suv_blindada", fd): (D(8800), P), ("minivan", md): (D(1900), V),
        (f"{conductor}+cuv", tr): (D(2800), V)}
    # La hora extra es un producto para todos: va en el dia completo.
    assert general.precio_hora_extra == D(330)
    assert {x.precio_hora_extra for x in general.tarifas_recurso} == {D(330)}

    # HASBRO pacto al conductor y el paquete; lo demas sale de la general.
    hasbro = tarifario(db, 2)
    assert not hasbro.general and hasbro.resto_de == "General México"
    assert precios(hasbro) == {
        (conductor, fd): (D(3000), P), (agente, fd): (D(4000), V),
        ("suv_blindada", fd): (D(8800), G), ("minivan", md): (D(1900), V),
        (f"{conductor}+cuv", tr): (D(2500), P)}
    assert hasbro.precio_hora_extra == D(330)

    # La de dolares no se lee: los costos van en pesos y la utilidad y la
    # comision restarian dolares menos pesos (BITACORA, «La moneda»).
    db.expire_all()
    assert db.query(m.Tarifario).filter_by(odoo_id=LISTA0 + 3).first() is None

    # La de los implantados de HASBRO toma lo demas de la de HASBRO.
    implantados = tarifario(db, 4)
    assert precios(implantados)[(agente, fd)] == (D(3600), P)
    assert precios(implantados)[(conductor, fd)] == (D(3000), O)

    # La general de Brasil, en reales y con las modalidades de Brasil.
    brasil = tarifario(db, 6)
    assert brasil.general and db.get(m.Pais, brasil.pais_id).codigo == "BR"
    assert precios(brasil)[(conductor, fd)] == (D(900), P)
    assert {x.modalidad.pais_id for x in brasil.tarifas_recurso} == {brasil.pais_id}

    # A cada cliente, la lista de su ficha; a HASBRO, tambien la de sus
    # implantados.
    db.expire_all()
    hasbro_c, general_c, amazon_c = (db.get(m.Cliente, clientes[n]) for n in (1, 2, 3))
    assert hasbro_c.tarifario_id == hasbro.id
    assert hasbro_c.tarifario_implantado_id == implantados.id
    assert general_c.tarifario_id == general.id
    assert general_c.tarifario_implantado_id is None
    # Amazon se queda con el que tenia, y se dice por que.
    assert amazon_c.tarifario.nombre == "General Mexico"
    assert amazon_c.tarifario.odoo_id is None
    assert {"tipo": "otra_moneda", "lista": "Amazon USD", "moneda": "USD",
            "pais": "Mexico"} in informe["pendientes"]
    assert {"tipo": "lista_otra_moneda", "cliente": f"{PREFIJO} Amazon",
            "lista": "Amazon USD", "moneda": "USD"} in informe["pendientes"]

    assert {c["antes"] for c in informe["cambian"]} == {"General Mexico"}
    assert informe["implantados"] == 1
    assert informe["campo_implantados"] == CAMPO
    assert [g["nombre"] for g in informe["generales"]] == ["General México",
                                                         "General Brasil"]
    assert [l["nombre"] for l in informe["sin_cliente"]] == ["Lista vieja"]
    por_cliente = {l["nombre"]: l for l in informe["por_cliente"]}
    assert por_cliente["HASBRO Implantados"]["implantados"] == [f"{PREFIJO} HASBRO"]
    assert {p["tipo"] for p in informe["pendientes"]} == {
        "lista_sin_cliente", "producto_sin_confirmar", "otra_moneda",
        "lista_otra_moneda"}
    assert informe["leidas"] == 6 and len(informe["cambian"]) == 2
    assert odoo_tarifarios.en_marcha(db)


def test_la_de_cada_hora_espera_a_la_primera_y_trae_lo_nuevo(db, clientes):
    odoo = OdooFalso(mundo())
    assert "omitido" in odoo_tarifarios.sincronizar_si_toca(db, odoo)
    confirmar_todo(db, odoo)
    leer(db, odoo)

    # En Odoo: HASBRO sube al conductor, se archiva la lista vieja y
    # Amazon pasa a la general.
    odoo.regla(10)["fixed_price"] = 3100
    odoo.lista(5)["active"] = False
    odoo.socio(3)["property_product_pricelist"] = [LISTA0 + 1, "General México"]
    resumen = odoo_tarifarios.sincronizar_si_toca(db, odoo)
    assert resumen["leidas"] == 5 and resumen["cambian"] == 1

    assert precios(tarifario(db, 2))[("conductor_seguridad", "full_day")][0] == D(3100)
    assert tarifario(db, 5).activo is False
    assert db.get(m.Cliente, clientes[3]).tarifario.odoo_id == LISTA0 + 1
    ultima = (db.query(m.SincronizacionOdoo).filter_by(tipo="tarifarios")
              .order_by(m.SincronizacionOdoo.id.desc()).first())
    assert ultima.automatica is True


def test_dos_reglas_para_lo_mismo_se_dicen(db, clientes):
    """Gana la mas nueva, como en Odoo, pero casi siempre es un descuido."""
    tablas = mundo()
    tablas["product.pricelist.item"].append(fija(13, 2, 1, 3150))
    odoo = OdooFalso(tablas)
    confirmar_todo(db, odoo)
    informe = leer(db, odoo)
    repetidas = [p for p in informe["pendientes"] if p["tipo"] == "reglas_repetidas"]
    assert repetidas[0]["lista"] == "HASBRO"
    assert sorted(repetidas[0]["precios"]) == ["3000", "3150"]
    assert precios(tarifario(db, 2))[("conductor_seguridad", "full_day")][0] == D(3150)


def test_dos_productos_para_lo_mismo_manda_el_preferido(db, cliente, sesion,
                                                        monkeypatch, clientes):
    """El gemelo en ingles: si la lista no pacta ninguno de los dos,
    chocan en cada lista que los hereda. Se dice una vez, con esas listas,
    y finanzas escoge cual manda."""
    tablas = mundo()
    tablas["product.template"].append({
        "id": PRODUCTO0 + 11, "name": "Bilingual Security Agent",
        "list_price": 200, "type": "service", "sale_ok": True, "active": True,
        "categ_id": [1, "All"], "uom_id": [1, "Unidades"]})
    odoo = OdooFalso(tablas)
    confirmar_todo(db, odoo)
    informe = leer(db, odoo, ensayo=True)
    choques = [p for p in informe["pendientes"] if p["tipo"] == "conflicto"]
    assert len(choques) == 1
    assert sorted(n for n, _ in choques[0]["productos"]) == [
        "Agente de Seguridad", "Bilingual Security Agent"]
    assert choques[0]["listas"] == ["General México", "HASBRO", "Lista vieja",
                                    "General Brasil"]

    conectar(monkeypatch, odoo)
    f = sesion("finanzas")
    agente = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 2).one()
    r = cliente.post(f"/tarifarios/productos/{agente.id}/preferido", headers=f)
    assert r.status_code == 200 and r.json()["preferido"] is True
    informe = leer(db, odoo)
    assert "conflicto" not in {p["tipo"] for p in informe["pendientes"]}
    assert precios(tarifario(db, 2))[("agente_seguridad", "full_day")] == (
        D(4000), reglas.PRECIO_VENTA)

    # Manda uno solo: escoger al otro le quita la marca al primero.
    gemelo = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 11).one()
    assert cliente.post(f"/tarifarios/productos/{gemelo.id}/preferido",
                        headers=f).status_code == 200
    db.expire_all()
    assert db.get(m.ProductoOdoo, agente.id).preferido is False
    # Decir que es otra cosa le quita la marca.
    coordinador = db.query(m.PerfilPersonal).filter_by(codigo="coordinador_seguridad").one()
    r = cliente.patch(f"/tarifarios/productos/{gemelo.id}", headers=f,
                      json={"clase": "rol", "perfil_id": coordinador.id,
                            "modalidad": "full_day"})
    assert r.json()["preferido"] is False
    # Lo que no pone precio no manda nada; y solo lo escoge finanzas.
    viaticos = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 6).one()
    assert cliente.post(f"/tarifarios/productos/{viaticos.id}/preferido",
                        headers=f).status_code == 409
    assert cliente.post(f"/tarifarios/productos/{agente.id}/preferido",
                        headers=sesion("consultor")).status_code == 403


def test_la_general_de_dos_paises_no_se_lee(db, clientes):
    tablas = mundo()
    tablas["product.pricelist"][0]["country_group_ids"] = [GRUPO_MX, GRUPO_BR]
    odoo = OdooFalso(tablas)
    confirmar_todo(db, odoo)
    informe = leer(db, odoo, ensayo=True)
    tipos = [p["tipo"] for p in informe["pendientes"]]
    assert "general_varios_paises" in tipos and "sin_pais" not in tipos
    # Su cliente se queda como estaba, y se dice.
    retenido = [p for p in informe["pendientes"] if p["tipo"] == "lista_sin_precios"]
    assert retenido == [{"tipo": "lista_sin_precios",
                         "cliente": f"{PREFIJO} Cliente General",
                         "lista": "General México"}]


def test_sin_general_se_dice(db, clientes):
    tablas = mundo()
    for lista in tablas["product.pricelist"]:
        lista["country_group_ids"] = []
    odoo = OdooFalso(tablas)
    confirmar_todo(db, odoo)
    informe = leer(db, odoo, ensayo=True)
    assert "sin_general" in {p["tipo"] for p in informe["pendientes"]}
    assert not informe["generales"]


def test_sin_el_campo_de_implantados(db, clientes):
    """Mientras finanzas no lo agregue con Studio, los implantados cobran
    con la lista de siempre."""
    odoo = OdooFalso(mundo(), campos_socio={})
    confirmar_todo(db, odoo)
    informe = leer(db, odoo)
    assert informe["campo_implantados"] is None and informe["implantados"] == 0
    db.expire_all()
    assert db.get(m.Cliente, clientes[1]).tarifario_implantado_id is None


def test_el_campo_se_busca_por_su_nombre():
    por_nombre = OdooFalso({}, campos_socio={"x_studio_otro": {
        "type": "many2one", "relation": "product.pricelist",
        "string": "Lista de Implantados"}})
    assert odoo_tarifarios.campo_de_implantados(por_nombre) == "x_studio_otro"
    otra_cosa = OdooFalso({}, campos_socio={"x_studio_otro": {
        "type": "many2one", "relation": "res.partner",
        "string": "Lista de implantados"}})
    assert odoo_tarifarios.campo_de_implantados(otra_cosa) is None


# ================================================================ la tabla

def test_lo_confirmado_no_se_vuelve_a_sugerir(db):
    odoo = OdooFalso(mundo())
    cuenta = odoo_tarifarios.leer_productos(db, odoo)
    db.commit()
    assert (cuenta["leidos"], cuenta["nuevos"], cuenta["sugeridos"]) == (10, 10, 9)

    coordinador = db.query(m.PerfilPersonal).filter_by(
        codigo="coordinador_seguridad").one()
    agente = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 2).one()
    agente.clase, agente.perfil_id, agente.confirmado = "rol", coordinador.id, True
    db.commit()

    odoo.producto(2)["name"] = "Agente de Seguridad Armado"
    odoo.producto(7)["sale_ok"] = False
    cuenta = odoo_tarifarios.leer_productos(db, odoo)
    db.commit()
    assert cuenta["nuevos"] == 0
    db.expire_all()
    agente = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 2).one()
    assert agente.nombre == "Agente de Seguridad Armado"
    assert agente.perfil_id == coordinador.id
    central = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 7).one()
    assert central.vendible is False


# ================================================================ las puertas

def test_las_puertas(cliente, sesion, monkeypatch, clientes):
    conectar(monkeypatch, OdooFalso(mundo()))
    h = sesion
    assert cliente.get("/tarifarios/productos", headers=h("consultor")).status_code == 200
    assert cliente.get("/tarifarios/productos", headers=h("juan")).status_code == 403
    for ruta in ("/tarifarios/productos/leer", "/tarifarios/productos/confirmar"):
        assert cliente.post(ruta, headers=h("consultor")).status_code == 403
    r = cliente.post("/tarifarios/productos/leer", headers=h("finanzas"))
    assert r.status_code == 200 and r.json()["nuevos"] == 10

    assert cliente.get("/odoo/tarifarios/ensayo", headers=h("finanzas")).status_code == 403
    assert cliente.get("/odoo/tarifarios/ensayo", headers=h("admin")).status_code == 200
    assert cliente.post("/odoo/tarifarios/sincronizar",
                        headers=h("consultor")).status_code == 403
    estado = cliente.get("/odoo/estado", headers=h("admin")).json()
    assert estado["tarifarios"]["primera_hecha"] is False

    assert cliente.get(f"/tarifarios/cliente/{clientes[1]}",
                       headers=h("consultor")).status_code == 200
    assert cliente.get("/tarifarios", headers=h("central")).status_code == 200


def test_finanzas_dice_que_es_cada_producto(cliente, sesion, monkeypatch):
    conectar(monkeypatch, OdooFalso(mundo()))
    f = sesion("finanzas")
    cliente.post("/tarifarios/productos/leer", headers=f)
    tabla = cliente.get("/tarifarios/productos", headers=f).json()
    assert tabla["puede_editar"] is True and tabla["conectado"] is True
    assert cliente.get("/tarifarios/productos",
                       headers=sesion("consultor")).json()["puede_editar"] is False
    por_nombre = {p["nombre"]: p for p in tabla["productos"]}
    federal = por_nombre["Conductor de Seguridad Federal"]
    assert federal["clase"] is None and federal["confirmado"] is False
    assert por_nombre["Conductor + CUV (Transfer)"]["clase"] == "paquete"

    r = cliente.post("/tarifarios/productos/confirmar", headers=f)
    assert r.json() == {"confirmados": 9}

    # A medias no se guarda.
    r = cliente.patch(f"/tarifarios/productos/{federal['id']}",
                      json={"clase": "rol"}, headers=f)
    assert r.status_code == 422 and r.json()["detail"]["campo"] == "perfil_id"
    r = cliente.patch(f"/tarifarios/productos/{federal['id']}",
                      json={"clase": "nave"}, headers=f)
    assert r.status_code == 422
    r = cliente.patch(f"/tarifarios/productos/{federal['id']}",
                      json={"clase": "no_ep"}, headers=f)
    assert r.status_code == 200, r.text
    assert r.json()["confirmado"] is True and r.json()["clase"] == "no_ep"
    # Y quien cotiza no lo cambia.
    r = cliente.patch(f"/tarifarios/productos/{federal['id']}",
                      json={"clase": "no_ep"}, headers=sesion("consultor"))
    assert r.status_code == 403


def aplicar_por_la_consola(cliente, sesion):
    f = sesion("finanzas")
    assert cliente.post("/tarifarios/productos/leer", headers=f).status_code == 200
    assert cliente.post("/tarifarios/productos/confirmar", headers=f).status_code == 200
    r = cliente.post("/odoo/tarifarios/sincronizar", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    return r.json()


def test_lo_de_odoo_no_se_edita_en_centauro(db, cliente, sesion, monkeypatch, clientes):
    conectar(monkeypatch, OdooFalso(mundo()))
    aplicar_por_la_consola(cliente, sesion)
    a = sesion("admin")
    antes = db.query(m.Tarifario).filter_by(nombre="General Mexico", odoo_id=None).one()
    hasbro = cliente.get(f"/catalogos/clientes/{clientes[1]}", headers=a).json()

    # El tarifario de un cliente de Odoo lo pone su ficha de Odoo.
    r = cliente.patch(f"/catalogos/clientes/{hasbro['id']}",
                      json={"nombre": hasbro["nombre"], "pais_id": hasbro["pais_id"],
                            "tarifario_id": antes.id}, headers=a)
    assert r.status_code == 409 and "tarifario_id" in r.json()["detail"]["campos"]

    # El de un cliente que no esta en Odoo, si.
    r = cliente.post("/catalogos/clientes", headers=a,
                     json={"nombre": f"{PREFIJO} Brasil", "pais_id": hasbro["pais_id"]})
    propio = r.json()
    r = cliente.patch(f"/catalogos/clientes/{propio['id']}", headers=a,
                      json={"nombre": propio["nombre"], "pais_id": propio["pais_id"],
                            "tarifario_id": antes.id})
    assert r.status_code == 200, r.text

    # La lista y sus precios se corrigen en Odoo.
    t = tarifario(db, 2)
    ficha = {"nombre": "Otro", "pais_id": t.pais_id, "moneda": "MXN",
             "vigencia_desde": "2026-01-01"}
    assert cliente.patch(f"/catalogos/tarifarios/{t.id}", json=ficha,
                         headers=a).status_code == 409
    assert cliente.delete(f"/catalogos/tarifarios/{t.id}", headers=a).status_code == 409
    fila = t.tarifas_recurso[0]
    precio = {"tarifario_id": t.id, "perfil_id": fila.perfil_id,
              "modalidad_id": fila.modalidad_id, "precio": "1"}
    assert cliente.patch(f"/catalogos/tarifas-recurso/{fila.id}", json=precio,
                         headers=a).status_code == 409
    assert cliente.post("/catalogos/tarifas-recurso", json=precio,
                        headers=a).status_code == 409
    assert cliente.delete(f"/catalogos/tarifas-recurso/{fila.id}",
                          headers=a).status_code == 409

    # Los de antes, capturados a mano, se siguen editando.
    for desde in ("2026-01-02", antes.vigencia_desde.isoformat()):
        r = cliente.patch(f"/catalogos/tarifarios/{antes.id}", headers=a,
                          json={"nombre": antes.nombre, "pais_id": antes.pais_id,
                                "moneda": "MXN", "vigencia_desde": desde})
        assert r.status_code == 200, r.text


def test_el_tarifario_del_cliente_se_ve(cliente, sesion, monkeypatch, clientes):
    conectar(monkeypatch, OdooFalso(mundo()))
    aplicar_por_la_consola(cliente, sesion)
    r = cliente.get(f"/tarifarios/cliente/{clientes[1]}", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["desde_odoo"] is True and t["cliente"]["de_odoo"] is True
    assert t["tarifario"]["nombre"] == "HASBRO"
    assert t["tarifario"]["resto_de"] == "General México"
    personal = {(p["perfil"], p["modalidad"]): (p["precio"], p["origen"])
                for p in t["tarifario"]["personal"]}
    assert personal[("Conductor de seguridad", "full_day")] == (3000.0, "propio")
    paquete = t["tarifario"]["paquetes"][0]
    assert (paquete["perfil"], paquete["categoria"], paquete["modalidad"],
            paquete["precio"]) == ("Conductor de seguridad", "CUV", "transfer", 2500.0)
    assert t["implantados"]["nombre"] == "HASBRO Implantados"
    listado = cliente.get("/tarifarios", headers=sesion("consultor")).json()
    assert {"nombre": "HASBRO", "clientes": 1}.items() <= next(
        x for x in listado if x["nombre"] == "HASBRO").items()

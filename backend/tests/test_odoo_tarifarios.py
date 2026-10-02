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
from app import tipo_cambio
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
        self.llamadas = []
        self.campos_socio = (CAMPO_IMPLANTADOS if campos_socio is None
                             else campos_socio)

    def leer(self, modelo, dominio, campos, archivados=False, idioma=None,
             compania=None):
        """`idioma` y `compania` (seccion 123): cada llamada se anota, y si
        la tabla trae lo de otro idioma o lo de otra compania, sale eso."""
        self.llamadas.append((modelo, idioma, compania))
        filas = [f for f in self.tablas.get(modelo, [])
                 if archivados or f.get("active", True)]
        salida = []
        for f in filas:
            if not cumple(f, dominio):
                continue
            fila = {"id": f["id"], **{c: f.get(c, False) for c in campos}}
            for c in campos:
                if idioma and c in (f.get("_idioma") or {}).get(idioma, {}):
                    fila[c] = f["_idioma"][idioma][c]
                if compania and c in (f.get("_compania") or {}).get(compania, {}):
                    fila[c] = f["_compania"][compania][c]
            salida.append(fila)
        return salida

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


@pytest.fixture(autouse=True)
def sin_filtros(monkeypatch):
    """Las pruebas de siempre leen todo, como antes de la seccion 112: su
    Odoo no tiene la categoria de PE ni listas «PE ·». Las de los filtros
    los ponen ellas, con `con_filtros`."""
    from app.config import settings
    monkeypatch.setattr(settings, "odoo_categoria_productos", "")
    monkeypatch.setattr(settings, "odoo_prefijo_listas", "")


def con_filtros(monkeypatch, categoria="Protección Ejecutiva", prefijo="PE ·"):
    from app.config import settings
    monkeypatch.setattr(settings, "odoo_categoria_productos", categoria)
    monkeypatch.setattr(settings, "odoo_prefijo_listas", prefijo)


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
    # La de un rol dice cual (seccion 113); sin rol, es la de todos.
    assert que("Hora Extra Agente de Seguridad Bilingüe") == ("hora_extra", 2, None, None)
    assert que("Hora Extra") == ("hora_extra", None, None, None)
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
    # En dolares y sin clientes no dice pais: queda pendiente (seccion 100).
    # Antes se tomaba como de Mexico sin decirlo.
    assert pais({"grupos": [], "moneda": "USD"}, set(), paises, grupos) == (None, [])
    # Y con clientes en dos paises, tampoco.
    assert pais({"grupos": [], "moneda": "MXN"}, {1, 2}, paises, grupos) == (None, [])


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
    assert len(informe["cambian"]) == 3
    db.expire_all()
    assert db.query(m.Tarifario).filter(m.Tarifario.odoo_id.isnot(None)).count() == 0
    assert db.get(m.Cliente, clientes[1]).tarifario.odoo_id is None
    assert not odoo_tarifarios.en_marcha(db)


def test_los_precios_como_los_calcula_odoo(db, clientes):
    # El tipo de cambio que puso finanzas (seccion 82): Odoo dice 20 pesos
    # por dolar (0.05), y manda el de Centauro. Y el dolar a real (seccion
    # 123): la general de Brasil pasa a reales lo que toma en pesos, con
    # los dos de Centauro --nunca con el de Odoo--.
    tipo_cambio.poner(db, "17.50", None)
    tipo_cambio.poner(db, "5.25", None, m.Moneda.USD, m.Moneda.BRL)
    db.commit()
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

    # La de dolares se lee en dolares (seccion 82): lo que pacta Amazon, tal
    # cual; lo demas sale de la general, en pesos, pasado a dolares con el
    # tipo de cambio de Centauro --17.50, no el de Odoo--: 4000 / 17.50.
    amazon = tarifario(db, 3)
    assert amazon.moneda == m.Moneda.USD and amazon.resto_de == "General México"
    assert precios(amazon) == {
        (conductor, fd): (D(180), P), (agente, fd): (D("228.57"), V),
        ("suv_blindada", fd): (D("502.86"), G), ("minivan", md): (D("108.57"), V),
        (f"{conductor}+cuv", tr): (D(160), V)}

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
    # Y a Amazon, la suya en dolares.
    assert amazon_c.tarifario_id == amazon.id

    assert {c["antes"] for c in informe["cambian"]} == {"General Mexico"}
    assert informe["implantados"] == 1
    assert informe["campo_implantados"] == CAMPO
    assert [g["nombre"] for g in informe["generales"]] == ["General México",
                                                         "General Brasil"]
    assert [l["nombre"] for l in informe["sin_cliente"]] == ["Lista vieja"]
    por_cliente = {l["nombre"]: l for l in informe["por_cliente"]}
    assert por_cliente["HASBRO Implantados"]["implantados"] == [f"{PREFIJO} HASBRO"]
    assert {p["tipo"] for p in informe["pendientes"]} == {
        "lista_sin_cliente", "producto_sin_confirmar"}
    assert informe["leidas"] == 6 and len(informe["cambian"]) == 3
    assert odoo_tarifarios.en_marcha(db)


def test_sin_tipo_de_cambio_lo_que_viene_en_pesos_no_tiene_precio(db, clientes):
    """Mientras finanzas no pone el tipo de cambio, lo que la lista de
    Amazon toma de la general --en pesos-- no se pasa a dolares con el de
    Odoo: sale sin precio y se dice. Lo que Amazon pacta en dolares si."""
    odoo = OdooFalso(mundo())
    confirmar_todo(db, odoo)
    informe = leer(db, odoo)
    amazon = tarifario(db, 3)
    assert precios(amazon) == {
        ("conductor_seguridad", "full_day"): (D(180), reglas.PROPIO)}
    assert any(p.get("lista") == "Amazon USD" and "tipo de cambio" in str(p)
               for p in informe["pendientes"]), informe["pendientes"]
    # Las de pesos no se enteran.
    assert precios(tarifario(db, 1))[("agente_seguridad", "full_day")][0] == D(4000)


def test_la_lista_en_una_moneda_que_no_se_sabe_convertir_no_se_lee(db, clientes):
    """Reales en Mexico: Centauro convierte dolares a pesos mexicanos y,
    desde la seccion 123, dolares a reales; de reales a pesos no. La
    utilidad y la comision restarian una moneda de otra: la lista se dice
    y el cliente se queda con la suya. (Los dolares de Brasil ya se leen:
    test_odoo_tarifarios_brasil.)"""
    odoo = OdooFalso(mundo())
    odoo.lista(2)["currency_id"] = [MONEDA_ID["BRL"], "BRL"]
    confirmar_todo(db, odoo)
    informe = leer(db, odoo)
    mexico = db.query(m.Pais).filter_by(codigo="MX").one()
    assert {"tipo": "otra_moneda", "lista": "HASBRO", "moneda": "BRL",
            "pais": mexico.nombre} in informe["pendientes"]
    assert {"tipo": "lista_otra_moneda", "cliente": f"{PREFIJO} HASBRO",
            "lista": "HASBRO", "moneda": "BRL"} in informe["pendientes"]
    db.expire_all()
    assert db.query(m.Tarifario).filter_by(odoo_id=LISTA0 + 2).first() is None
    assert db.get(m.Cliente, clientes[1]).tarifario.nombre == "General Mexico"


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
    # Con tipo de cambio, para que la de dolares --y la de reales, con el
    # dolar a real (seccion 123)-- tambien tengan al agente.
    tipo_cambio.poner(db, "17.50", None)
    tipo_cambio.poner(db, "5.25", None, m.Moneda.USD, m.Moneda.BRL)
    db.commit()
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
    assert choques[0]["listas"] == ["General México", "HASBRO", "Amazon USD",
                                    "Lista vieja", "General Brasil"]

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


# ================================================================ solo PE (seccion 112)

def mundo_pe() -> dict:
    """El Odoo de hoy (seccion 112): la categoria «Protección Ejecutiva»
    con una subcategoria, el GPS en la suya, las listas de PE con su
    prefijo y una que no es de PE."""
    tablas = mundo()
    tablas["product.category"] = [
        {"id": 1, "name": "All", "complete_name": "All", "parent_path": "1/"},
        {"id": 2, "name": "Protección Ejecutiva",
         "complete_name": "All / Protección Ejecutiva", "parent_path": "1/2/"},
        {"id": 3, "name": "Unidades",
         "complete_name": "All / Protección Ejecutiva / Unidades",
         "parent_path": "1/2/3/"},
        {"id": 4, "name": "GPS", "complete_name": "All / GPS", "parent_path": "1/4/"}]
    # La Suburban, en la subcategoria; la Central y el rastreador, en el GPS.
    categoria = {3: 3, 7: 4, 10: 4}
    for f in tablas["product.template"]:
        f["categ_id"] = [categoria.get(f["id"] - PRODUCTO0, 2), "categoria"]
    for f in tablas["product.pricelist"]:
        if f["id"] != LISTA0 + 5:
            f["name"] = f"PE · {f['name']}"
    # La General de PE nombra el rastreador, que es del GPS.
    tablas["product.pricelist.item"].append(fija(60, 1, 10, 999))
    # Y Amazon trae en Odoo una lista que no es de PE.
    socio = next(s for s in tablas["res.partner"] if s["id"] == SOCIO0 + 3)
    socio["property_product_pricelist"] = [LISTA0 + 5, "Lista vieja"]
    return tablas


def test_solo_lo_de_proteccion_ejecutiva(db, clientes, monkeypatch):
    """Pedido de Salvador: la lectura traia el GPS, la Central de
    Inteligencia y ATLAS. Solo los productos de la categoria de PE --con
    sus subcategorias-- y las listas «PE ·»."""
    odoo = OdooFalso(mundo_pe())
    con_filtros(monkeypatch)
    confirmar_todo(db, odoo)
    fuera = db.query(m.ProductoOdoo).filter(
        m.ProductoOdoo.odoo_id.in_([PRODUCTO0 + 7, PRODUCTO0 + 10])).count()
    assert fuera == 0

    informe = leer(db, odoo)
    assert (informe["leidas"], informe["fuera"], informe["prefijo"]) == (5, 1, "PE ·")
    assert db.query(m.Tarifario).filter_by(odoo_id=LISTA0 + 5).count() == 0
    general = tarifario(db, 1)
    assert general.nombre == "PE · General México"
    # La Suburban viene de la subcategoria, y tiene su precio.
    assert precios(general)[("suv_blindada", "full_day")][0] == D(8800)
    # Lo que una lista de PE nombra y no es de la categoria, se dice.
    assert {"tipo": "producto_fuera", "producto": "Rastreador GPS",
            "listas": ["PE · General México"],
            "categoria": "Protección Ejecutiva"} in informe["pendientes"]
    assert not any(p["tipo"] == "producto_sin_confirmar"
                   and p["producto"] == "Rastreador GPS" for p in informe["pendientes"])
    # El cliente cuya lista no es de PE se queda con su tarifario, y se dice.
    assert {"tipo": "lista_no_pe", "cliente": f"{PREFIJO} Amazon",
            "lista": "Lista vieja", "prefijo": "PE ·"} in informe["pendientes"]
    db.expire_all()
    assert db.get(m.Cliente, clientes[3]).tarifario.odoo_id is None

    # La de cada hora, igual: nada del GPS vuelve a la tabla.
    leer(db, odoo, automatica=True)
    db.expire_all()
    assert db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 7).count() == 0


def test_lo_que_no_es_de_pe_sale_de_la_tabla(db, monkeypatch):
    """Lo que ya estaba en la tabla y no es de PE sale; lo de PE que ya no
    se vende se queda en gris, y lo que un tarifario todavia nombra
    tambien."""
    odoo = OdooFalso(mundo_pe())
    odoo_tarifarios.leer_productos(db, odoo)        # sin filtro: los diez
    db.commit()
    assert db.query(m.ProductoOdoo).count() == 10

    # Un tarifario de antes nombra el rastreador: lo confirmaron mal.
    mx = db.query(m.Pais).filter_by(codigo="MX").one()
    viejo = m.Tarifario(nombre="Una lista vieja", pais_id=mx.id,
                        moneda=m.Moneda.MXN, vigencia_desde=date(2026, 9, 1),
                        odoo_id=LISTA0 + 99)
    db.add(viejo)
    db.flush()
    gps = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 10).one()
    conductor = db.query(m.PerfilPersonal).filter_by(codigo="conductor_seguridad").one()
    dia = db.query(m.Modalidad).filter_by(pais_id=mx.id,
                                          codigo=m.CodigoModalidad.FULL_DAY).one()
    db.add(m.TarifaRecurso(tarifario_id=viejo.id, perfil_id=conductor.id,
                           modalidad_id=dia.id, precio=100, producto_odoo_id=gps.id))
    db.commit()
    odoo.producto(9)["sale_ok"] = False              # de PE, ya no se vende

    con_filtros(monkeypatch)
    cuenta = odoo_tarifarios.leer_productos(db, odoo)
    db.commit()
    assert (cuenta["leidos"], cuenta["quitados"]) == (7, 1)
    db.expire_all()
    quedan = {p.odoo_id: p for p in db.query(m.ProductoOdoo)}
    assert PRODUCTO0 + 7 not in quedan                # la Central de Inteligencia
    assert quedan[PRODUCTO0 + 10].vendible is False   # lo nombra un tarifario
    assert quedan[PRODUCTO0 + 9].vendible is False    # de PE, en gris


def test_sin_la_categoria_no_se_toca_nada(db, clientes, cliente, sesion, monkeypatch):
    """Sin la categoria en Odoo no se sabe que es de PE: leer todo seria
    volver a traer el GPS. No se lee nada y se dice."""
    odoo = OdooFalso(mundo_pe())
    con_filtros(monkeypatch, categoria="Seguridad privada")
    informe = leer(db, odoo)
    assert informe["sin_categoria"] == "Seguridad privada"
    assert informe["pendientes"] == [] and informe["leidas"] == 0
    assert db.query(m.Tarifario).filter(m.Tarifario.odoo_id.isnot(None)).count() == 0
    assert db.query(m.ProductoOdoo).count() == 0
    with pytest.raises(odoo_tarifarios.SinCategoria):
        odoo_tarifarios.leer_productos(db, odoo)
    db.rollback()

    conectar(monkeypatch, odoo)
    r = cliente.post("/tarifarios/productos/leer", headers=sesion("finanzas"))
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "sin_categoria"
    # La tabla dice de donde salen los productos.
    d = cliente.get("/tarifarios/productos", headers=sesion("finanzas")).json()
    assert d["categoria"] == "Seguridad privada"


def test_las_listas_de_pe_por_su_nombre(monkeypatch):
    con_filtros(monkeypatch)
    assert odoo_tarifarios.es_lista_de_pe("PE · General México")
    assert odoo_tarifarios.es_lista_de_pe("  pe ·  Control Risks")
    assert odoo_tarifarios.es_lista_de_pe("PE•Amazon")
    assert odoo_tarifarios.es_lista_de_pe("PE ∙ Amazon")
    assert not odoo_tarifarios.es_lista_de_pe("Pemex · Tarifas")
    assert not odoo_tarifarios.es_lista_de_pe("General · México")
    assert not odoo_tarifarios.es_lista_de_pe("GPS · Tarifas")
    con_filtros(monkeypatch, prefijo="")
    assert odoo_tarifarios.es_lista_de_pe("GPS · Tarifas")


def test_los_nombres_se_leen_en_espanol_de_mexico(monkeypatch):
    """En Odoo cada producto guarda su nombre por idioma: se leen en es_MX
    (`odoo_idioma`)."""
    from app.config import settings

    pedidos = []

    class Respuesta:
        status_code = 200

        def json(self):
            return []

    odoo = odoo_api.Odoo("https://odoo.prueba", "llave")
    monkeypatch.setattr(odoo.http, "post",
                        lambda url, json: pedidos.append(json) or Respuesta())
    odoo.leer("product.template", [], ["name"], archivados=True)
    assert pedidos[0]["context"] == {"lang": "es_MX", "active_test": False}
    monkeypatch.setattr(settings, "odoo_idioma", "es_419")
    odoo.leer("product.template", [], ["name"])
    assert pedidos[1]["context"] == {"lang": "es_419"}


# ================================================================ la hora extra (seccion 113)

def test_la_hora_extra_de_cada_rol(db):
    """En Odoo cada rol trae su hora extra: «Hora Extra Agente de
    Seguridad Bilingüe». Antes la tabla no dejaba decir de que rol era:
    todas decian lo mismo y cobraba la del conductor para todos. Ahora se
    sugiere por el nombre y cada rol cobra la suya; la de todos queda
    para el rol que no trae la propia."""
    tablas = mundo()
    tablas["product.template"].append(
        {"id": PRODUCTO0 + 11, "name": "Hora Extra Agente de Seguridad",
         "list_price": 578, "type": "service", "sale_ok": True, "active": True,
         "categ_id": [1, "All"], "uom_id": [1, "Horas"]})
    regla = fija(4, 1, 1, 578)
    regla["product_tmpl_id"] = [PRODUCTO0 + 11, "Hora Extra Agente de Seguridad"]
    tablas["product.pricelist.item"].append(regla)
    odoo = OdooFalso(tablas)
    confirmar_todo(db, odoo)
    agente = db.query(m.PerfilPersonal).filter_by(codigo="agente_seguridad").one()
    suya = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 11).one()
    assert (suya.clase, suya.perfil_id) == ("hora_extra", agente.id)
    general = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 5).one()
    assert (general.clase, general.perfil_id) == ("hora_extra", None)

    informe = leer(db, odoo)
    assert not [p for p in informe["pendientes"] if p["tipo"] == "conflicto"]
    extras = {x.perfil.codigo: x.precio_hora_extra
              for x in tarifario(db, 1).tarifas_recurso
              if x.modalidad.codigo.value == "full_day"}
    assert extras["agente_seguridad"] == D(578)
    assert extras["conductor_seguridad"] == D(330)      # la de todos


def test_la_tabla_ofrece_la_hora_extra_de_cada_rol():
    """El selector de la tabla de productos trae la hora extra de cada
    rol, y la de todos."""
    import pathlib
    js = (pathlib.Path(__file__).parent.parent / "app" / "web" / "tarifarios.js").read_text(
        encoding="utf-8")
    assert "value: `hora_extra:${p.id}:`" in js
    assert 't("tar_hora_extra_todos")' in js


# ================================================================ la factura (seccion 116)

def test_la_variante_con_que_se_factura(db):
    """En una factura de Odoo el renglon lleva el producto exacto --la
    variante, product.product-- y la tabla guardaba su plantilla. La
    lectura trae la variante del que tiene una sola; del que tiene varias
    no escoge ninguna y lo dice en sus pendientes."""
    tablas = mundo()
    for f in tablas["product.template"]:
        f["product_variant_id"] = [f["id"] + 50_000, f["name"]]
        f["product_variant_count"] = 1
    suburban = next(f for f in tablas["product.template"]
                    if f["id"] == PRODUCTO0 + 3)
    suburban["product_variant_count"] = 3
    odoo = OdooFalso(tablas)
    confirmar_todo(db, odoo)
    db.expire_all()
    conductor = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 1).one()
    assert (conductor.variante_odoo_id, conductor.variantes) == (PRODUCTO0 + 50_001, 1)
    tres = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 3).one()
    assert (tres.variante_odoo_id, tres.variantes) == (None, 3)

    informe = leer(db, odoo)
    assert {"tipo": "producto_variantes", "producto": "SUBURBAN Blindada",
            "variantes": 3} in informe["pendientes"]
    # Un Odoo que no dice cuantas tiene: no se adivina.
    for f in tablas["product.template"]:
        f.pop("product_variant_count")
    odoo_tarifarios.leer_productos(db, OdooFalso(tablas))
    db.commit()
    db.expire_all()
    conductor = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 1).one()
    assert (conductor.variante_odoo_id, conductor.variantes) == (None, None)


def test_la_hora_extra_sabe_con_que_producto_se_cobra(db):
    """La hora extra sale en la factura con el producto de la de su rol, o
    con la de todos: cada renglon del tarifario guarda de cual salio su
    precio, y la lista el de la de todos."""
    tablas = mundo()
    tablas["product.template"].append(
        {"id": PRODUCTO0 + 11, "name": "Hora Extra Agente de Seguridad",
         "list_price": 578, "type": "service", "sale_ok": True, "active": True,
         "categ_id": [1, "All"], "uom_id": [1, "Horas"]})
    regla = fija(4, 1, 1, 578)
    regla["product_tmpl_id"] = [PRODUCTO0 + 11, "Hora Extra Agente de Seguridad"]
    tablas["product.pricelist.item"].append(regla)
    odoo = OdooFalso(tablas)
    confirmar_todo(db, odoo)
    leer(db, odoo)
    suya = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 11).one()
    de_todos = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 5).one()
    general = tarifario(db, 1)
    productos = {(x.perfil.codigo, x.modalidad.codigo.value): x.producto_hora_extra_id
                 for x in general.tarifas_recurso}
    assert productos[("agente_seguridad", "full_day")] == suya.id
    assert productos[("conductor_seguridad", "full_day")] == de_todos.id
    assert general.producto_hora_extra_id == de_todos.id

    # La de cada hora vuelve a poner todo igual.
    leer(db, odoo, automatica=True)
    assert tarifario(db, 1).producto_hora_extra_id == de_todos.id


def test_el_producto_de_los_gastos_entra_aunque_no_sea_de_pe(db, monkeypatch):
    """«Gastos de Operación (Viáticos)» es con el que se facturan los
    gastos del eventual. Se lee a la tabla aunque no sea de la categoria
    de PE: moverlo de categoria en Odoo le cambiaria su cuenta contable."""
    tablas = mundo_pe()
    tablas["product.template"].append(
        {"id": PRODUCTO0 + 12, "name": "Gastos de Operacion (viaticos)",
         "list_price": 0, "type": "service", "sale_ok": True, "active": True,
         "categ_id": [4, "GPS"], "uom_id": [1, "Unidades"],
         "product_variant_id": [PRODUCTO0 + 50_012, "Gastos"],
         "product_variant_count": 1})
    odoo = OdooFalso(tablas)
    con_filtros(monkeypatch)
    odoo_tarifarios.leer_productos(db, odoo)
    db.commit()
    db.expire_all()
    gastos = db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 12).one()
    assert gastos.variante_odoo_id == PRODUCTO0 + 50_012
    assert gastos.clase == "viaticos"                  # sugerido por su nombre
    fila = next(p for p in odoo_tarifarios.tabla_de_productos(db)
                if p["odoo_id"] == PRODUCTO0 + 12)
    assert fila["de_gastos"] is True
    assert not any(p["de_gastos"] for p in odoo_tarifarios.tabla_de_productos(db)
                   if p["odoo_id"] != PRODUCTO0 + 12)

    # La siguiente lectura no lo saca de la tabla.
    odoo_tarifarios.leer_productos(db, odoo)
    db.commit()
    assert db.query(m.ProductoOdoo).filter_by(odoo_id=PRODUCTO0 + 12).count() == 1
    # Y si en el .env se llama de otro modo, ese ya no es.
    from app.config import settings
    monkeypatch.setattr(settings, "odoo_producto_gastos", "Viáticos")
    assert odoo_tarifarios.es_el_de_gastos("Viaticos")
    assert not odoo_tarifarios.es_el_de_gastos("Gastos de Operación (Viáticos)")
    monkeypatch.setattr(settings, "odoo_producto_gastos", "")
    assert not odoo_tarifarios.es_el_de_gastos("")

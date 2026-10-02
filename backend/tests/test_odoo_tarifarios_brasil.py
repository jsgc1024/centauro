# -*- coding: utf-8 -*-
"""El tarifario de Brasil desde Odoo (seccion 123).

Contra un Odoo de mentiras como el que dejo cargado Ari el 2 de octubre:

  * La categoria «Proteção Executiva Brasil», con los productos en
    portugues de la compania de Brasil: el Motorista Executivo Bilíngue
    (el conductor), el Consultor y el Coordenador de Segurança, las
    unidades «Nível III», los paquetes «(Tudo incluído...)» y la hora
    extra de cada puesto --en Brasil, el 30% del dia, capturada en la
    lista--. Las modalidades se dicen «(Meio Período)» y «(Transfer)».
  * «Brasil · General», en reales, y «Brasil · General USD», en dolares,
    con el grupo de paises de Brasil.
  * «Brasil · Amazon Implantados (USD)»: el paquete de Amazon Brasil,
    USD 16,855 al mes, y su hora extra, USD 112.
  * «Predeterminado», que no se usa; y el real sin tipo de cambio en la
    compania de Mexico (vale 1).

Lo que se cuida, como lo aprobo Salvador:

  * Cada pais lee lo suyo --su categoria, sus listas, sus nombres en su
    idioma--, y los productos de un pais nunca ponen precio en la lista
    de otro.
  * El paquete que en Odoo se cobra por «Mes» se queda del mes, con su
    hora extra, aunque la lista no traiga al conductor suelto.
  * Las listas en dolares de Brasil se leen, con el dolar a real de
    Centauro --nunca el de Odoo--; la del cliente se lee desde la
    compania de su pais, y una lista de otro pais nunca se le pone.
  * Brasil sin lista general se dice, y no usa la de Mexico.
  * La propuesta de Amazon Brasil sale en USD 16,855.00 tal cual, con su
    dia adicional y su hora extra; sin el dolar a real no se autoriza; y
    el mes nace igual, con los productos de la prefactura.
  * La flota que la general de su pais no cobra --las Corolla Cross,
    «CUV Blindada»-- se dice, sin bloquear nada.
  * «Que mande este» es entre los productos de un mismo pais.
  * «Confirmar los sugeridos» es de la pestana que se ve, y una general
    sin cliente se abre por si misma (seccion 124).
"""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app import models as m
from app import odoo_facturacion_mes, odoo_tarifarios, tipo_cambio
from app import odoo_tarifarios_reglas as reglas
from app import propuesta as motor_propuesta
from test_odoo_tarifarios import (CAMPO, LISTA0, PREFIJO, PRODUCTO0, REGLA0,  # noqa: F401
                                  SOCIO0, D, OdooFalso, clientes, conectar,
                                  confirmar_todo, con_filtros, db, leer,
                                  mundo_pe, precios, sin_rastro, tarifario)

PAIS_BR, GRUPO_BRASIL = 31, 13
AMAZON_BR, CLIENTE_BR = SOCIO0 + 50, SOCIO0 + 51
LISTA_BR, PREDETERMINADO = LISTA0 + 35, LISTA0 + 26
GENERAL_BR, GENERAL_USD = LISTA0 + 37, LISTA0 + 38
PAQUETE_BR, EXTRA_BR, DESPESAS = PRODUCTO0 + 109, PRODUCTO0 + 110, PRODUCTO0 + 111
CENTAURO_ASS = "CENTAURO ASS"
CENTAURO_BR = "CENTAURO SOLUCOES AVANCADAS DE SEGURANCA LTDA."
PAQUETE_PT = ("Motorista Executivo Bilíngue + Minivan Blindada Nível III "
              "(Plano 12h, Tudo incluído)")
EXTRA_PT = "Hora Extra Motorista Executivo Bilíngue + Minivan Blindada Nível III"
NOMBRE_BR = f"{PREFIJO} AMAZON SERVICOS DE VAREJO DO BRASIL LTDA."
NOMBRE_CLIENTE_BR = f"{PREFIJO} Cliente de Sao Paulo"

# Los de la general de Brasil: (n, nombre en portugues, unidad, reales en
# «Brasil · General»). El 30% del dia en la hora extra, capturado.
DIAS, HORAS = [31, "Días"], [32, "Horas"]
DE_BRASIL = [
    (201, "Motorista Executivo Bilíngue", DIAS, 1500),
    (202, "Motorista Executivo Bilíngue (Meio Período)", DIAS, 900),
    (203, "Motorista Executivo Bilíngue (Transfer)", DIAS, 600),
    (204, "Consultor de Segurança Bilíngue", DIAS, 2500),
    (205, "Coordenador de Segurança Bilíngue", DIAS, 2000),
    (206, "Hora Extra Motorista Executivo Bilíngue", HORAS, 450),
    (207, "Hora Extra Consultor de Segurança Bilíngue", HORAS, 750),
    (208, "SUV Blindada Nível III", DIAS, 3000),
    (209, "Minivan Blindada Nível III (Meio Período)", DIAS, 1800),
    # Sin regla: sale de su «Precio de venta», en reales.
    (210, "Minivan", DIAS, None),
    (211, "Motorista Executivo Bilíngue + SUV Blindada Nível III (Tudo incluído)",
     DIAS, 4800),
    (212, "Motorista Executivo Bilíngue + Minivan Blindada Nível III "
          "(Tudo incluído, Meio Período)", DIAS, 2900),
    (213, "Motorista Executivo Bilíngue + Minivan (Tudo incluído, Transfer)",
     DIAS, 1500),
]
PRECIO_DE_VENTA_MINIVAN = 900


def _producto(n, es, pt, unidad, **extra):
    return {"id": n, "name": es, "_idioma": {"pt_BR": {"name": pt}},
            "list_price": 0, "type": "service", "sale_ok": True, "active": True,
            "categ_id": [5, "Proteção Executiva Brasil"], "uom_id": unidad,
            "currency_id": [7, "BRL"],
            "product_variant_id": [n + 1000, es], "product_variant_count": 1,
            **extra}


def _fija(n, producto, nombre, precio, lista=LISTA_BR):
    return {"id": REGLA0 + n, "pricelist_id": [lista, "lista"],
            "applied_on": "1_product", "product_tmpl_id": [producto, nombre],
            "product_id": False, "categ_id": False, "min_quantity": 0,
            "compute_price": "fixed", "fixed_price": precio,
            "base": "list_price", "date_start": False, "date_end": False}


def _lo_demas_de(n, lista, de):
    """«Todo lo demas, de otra lista», con la conversion de Odoo."""
    return {"id": REGLA0 + n, "pricelist_id": [lista, "lista"],
            "applied_on": "3_global", "product_tmpl_id": False,
            "product_id": False, "categ_id": False, "min_quantity": 0,
            "compute_price": "formula", "base": "pricelist",
            "base_pricelist_id": [de, "otra"], "price_discount": 0,
            "price_surcharge": 0, "price_round": 0, "price_min_margin": 0,
            "price_max_margin": 0, "date_start": False, "date_end": False}


def mundo_brasil() -> dict:
    """El Odoo de mentiras del 2 de octubre: el de Mexico de la seccion 112
    --sin la «General Brasil» de las pruebas de antes-- y lo de Brasil que
    cargo Ari."""
    tablas = mundo_pe()
    tablas["product.pricelist"] = [l for l in tablas["product.pricelist"]
                                   if l["id"] != LISTA0 + 6]
    tablas["product.pricelist.item"] = [
        r for r in tablas["product.pricelist.item"]
        if r["pricelist_id"][0] != LISTA0 + 6]
    for lista in tablas["product.pricelist"]:
        lista["company_id"] = [1, CENTAURO_ASS]
    tablas["product.category"].append(
        {"id": 5, "name": "Proteção Executiva Brasil",
         "complete_name": "Proteção Executiva Brasil", "parent_path": "5/"})
    tablas["product.template"] += [
        _producto(PAQUETE_BR, "Conductor Ejecutivo Bilingüe + Minivan Blindada "
                  "Nivel III (Plan 12h, Todo incluido)", PAQUETE_PT, [21, "Mes"]),
        _producto(EXTRA_BR, "Hora Extra Conductor Ejecutivo Bilingüe + Minivan "
                  "Blindada Nivel III", EXTRA_PT, HORAS),
        # Archivado en Odoo: se queda fuera mientras lo este.
        _producto(DESPESAS, "Gastos Operativos (casetas, estacionamiento, "
                  "combustible, hospedaje)",
                  "Despesas Operacionais (pedágios, estacionamento, combustível, "
                  "hospedagem)", [1, "Unidades"], active=False)]
    tablas["product.template"] += [
        _producto(PRODUCTO0 + n, f"(es) {pt}", pt, unidad,
                  list_price=PRECIO_DE_VENTA_MINIVAN if n == 210 else 0)
        for n, pt, unidad, _ in DE_BRASIL]
    tablas["product.pricelist"] += [
        {"id": LISTA_BR, "name": "Brasil · Amazon Implantados (USD)",
         "currency_id": [2, "USD"], "country_group_ids": [], "active": True,
         "company_id": [5, CENTAURO_BR]},
        {"id": PREDETERMINADO, "name": "Predeterminado",
         "currency_id": [7, "BRL"], "country_group_ids": [], "active": True,
         "company_id": [5, CENTAURO_BR]},
        {"id": GENERAL_BR, "name": "Brasil · General", "currency_id": [7, "BRL"],
         "country_group_ids": [GRUPO_BRASIL], "active": True,
         "company_id": [5, CENTAURO_BR]},
        {"id": GENERAL_USD, "name": "Brasil · General USD",
         "currency_id": [2, "USD"], "country_group_ids": [GRUPO_BRASIL],
         "active": True, "company_id": [5, CENTAURO_BR]}]
    tablas["product.pricelist.item"] += [
        _fija(101, PAQUETE_BR, PAQUETE_PT, 16855),
        _fija(102, EXTRA_BR, EXTRA_PT, 112)]
    tablas["product.pricelist.item"] += [
        _fija(300 + n, PRODUCTO0 + n, pt, precio, lista=GENERAL_BR)
        for n, pt, _, precio in DE_BRASIL if precio is not None]
    # La de dolares: el motorista y su hora extra pactados en dolares; lo
    # demas, de la de reales.
    tablas["product.pricelist.item"] += [
        _fija(401, PRODUCTO0 + 201, "Motorista Executivo Bilíngue", 250,
              lista=GENERAL_USD),
        _fija(406, PRODUCTO0 + 206, "Hora Extra Motorista Executivo Bilíngue", 75,
              lista=GENERAL_USD),
        _lo_demas_de(499, GENERAL_USD, GENERAL_BR)]
    tablas["res.country.group"].append({"id": GRUPO_BRASIL, "country_ids": [PAIS_BR]})
    tablas["res.company"] = [{"id": 1, "name": CENTAURO_ASS},
                             {"id": 5, "name": CENTAURO_BR}]
    # El real vale 1 en la compania de Mexico: nadie le puso el suyo. En la
    # de Brasil esta en 6.00, pero Connect usa el suyo.
    for moneda in tablas["res.currency"]:
        if moneda["name"] == "BRL":
            moneda["rate"] = 1.0
    # Amazon Brasil: desde la compania de Mexico, Odoo le pone la General
    # de Mexico; desde la suya, la de Amazon, como la de sus implantados.
    tablas["res.partner"] += [
        {"id": AMAZON_BR, "name": "AMAZON SERVICOS DE VAREJO DO BRASIL LTDA.",
         "is_company": True,
         "property_product_pricelist": [LISTA0 + 1, "PE · General México"],
         "_compania": {5: {"property_product_pricelist":
                           [LISTA_BR, "Brasil · Amazon Implantados (USD)"]}},
         CAMPO: [LISTA_BR, "Brasil · Amazon Implantados (USD)"]},
        # Un cliente de Brasil sin lista suya: cae en la general de reales.
        {"id": CLIENTE_BR, "name": "Cliente de Sao Paulo", "is_company": True,
         "property_product_pricelist": [LISTA0 + 1, "PE · General México"],
         "_compania": {5: {"property_product_pricelist":
                           [GENERAL_BR, "Brasil · General"]}},
         CAMPO: False}]
    return tablas


@pytest.fixture
def brasil(db):
    return db.query(m.Pais).filter_by(codigo="BR").one()


@pytest.fixture
def mexico(db):
    return db.query(m.Pais).filter_by(codigo="MX").one()


@pytest.fixture
def de_brasil(db, brasil, clientes, base_de_pruebas):
    """Amazon Brasil y un cliente de Sao Paulo en Connect, de Odoo, sin
    tarifario. Al terminar, lo que la prueba armo con ellos --propuestas,
    el implantado, la flota-- se va antes que los clientes."""
    ids = {}
    for odoo_id, nombre in ((AMAZON_BR, NOMBRE_BR), (CLIENTE_BR, NOMBRE_CLIENTE_BR)):
        c = m.Cliente(nombre=nombre, pais_id=brasil.id, odoo_id=odoo_id, activo=True)
        db.add(c)
        db.flush()
        ids[odoo_id] = c.id
    db.commit()
    yield SimpleNamespace(amazon=ids[AMAZON_BR], cliente=ids[CLIENTE_BR])
    db.rollback()
    from conftest import TABLAS_DE_OPERACION
    from app.seed import sembrar_recursos

    with base_de_pruebas.begin() as con:
        con.execute(text(f"TRUNCATE {', '.join(TABLAS_DE_OPERACION)} "
                         "RESTART IDENTITY CASCADE"))
    sembrar_recursos()


@pytest.fixture
def filtros(monkeypatch):
    """La configuracion de hoy: «Protección Ejecutiva» y «PE ·» para
    Mexico; la de Brasil, la de omision."""
    con_filtros(monkeypatch)


def _real(db, tasa="6.00"):
    """Finanzas pone el dolar a real en Connect."""
    tipo_cambio.poner(db, tasa, None, m.Moneda.USD, m.Moneda.BRL)
    db.commit()


def _leido(db, odoo, ensayo=False):
    confirmar_todo(db, odoo)
    return leer(db, odoo, ensayo=ensayo)


def _producto_de(db, odoo_id) -> m.ProductoOdoo:
    db.expire_all()
    return db.query(m.ProductoOdoo).filter_by(odoo_id=odoo_id).one()


# ================================================================ los nombres

def test_los_nombres_de_brasil_se_reconocen(db):
    """Los de Brasil dicen la modalidad distinto: sin parentesis, el dia
    completo; «(Meio Período)», el medio dia; «(Transfer)»; y el paquete,
    «(Tudo incluído...)». El Motorista Executivo es el conductor."""
    perfiles, categorias = odoo_tarifarios._catalogos(db)
    perfil = {p.codigo: p.id for p in db.query(m.PerfilPersonal)}
    categoria = {c.codigo: c.id for c in db.query(m.CategoriaVehiculo)}

    def que(nombre, unidad=DIAS):
        s = reglas.sugerir({"name": nombre, "type": "service", "uom_id": unidad},
                           perfiles, categorias)
        return s["clase"], s["perfil_id"], s["categoria_id"], s["modalidad"]

    conductor, consultor = perfil["conductor_seguridad"], perfil["consultor_seguridad"]
    coordinador = perfil["coordinador_seguridad"]
    suv, minivan_b = categoria["suv_blindada"], categoria["minivan_blindada"]
    minivan = categoria["minivan"]
    assert que("Motorista Executivo Bilíngue") == ("rol", conductor, None, "full_day")
    assert que("Motorista Executivo Bilíngue (Meio Período)") == (
        "rol", conductor, None, "medio_dia")
    assert que("Motorista Executivo Bilíngue (Transfer)") == (
        "rol", conductor, None, "transfer")
    assert que("Consultor de Segurança Bilíngue") == ("rol", consultor, None, "full_day")
    assert que("Coordenador de Segurança Bilíngue (Meio Período)") == (
        "rol", coordinador, None, "medio_dia")
    assert que("Hora Extra Motorista Executivo Bilíngue", HORAS) == (
        "hora_extra", conductor, None, None)
    assert que("Hora Extra Coordenador de Segurança Bilíngue", HORAS) == (
        "hora_extra", coordinador, None, None)
    assert que("SUV Blindada Nível III") == ("unidad", None, suv, "full_day")
    assert que("Minivan Blindada Nível III (Transfer)") == (
        "unidad", None, minivan_b, "transfer")
    assert que("Minivan (Meio Período)") == ("unidad", None, minivan, "medio_dia")
    assert que("Motorista Executivo Bilíngue + SUV Blindada Nível III (Tudo incluído)") == (
        "paquete", conductor, suv, "full_day")
    assert que("Motorista Executivo Bilíngue + Minivan Blindada Nível III "
               "(Tudo incluído, Meio Período)") == (
        "paquete", conductor, minivan_b, "medio_dia")
    assert que("Motorista Executivo Bilíngue + Minivan (Tudo incluído, Transfer)") == (
        "paquete", conductor, minivan, "transfer")
    # El de Amazon Brasil se cobra por «Mes».
    assert que(PAQUETE_PT, [21, "Mes"]) == ("paquete", conductor, minivan_b, "mes")
    # Los de Mexico, como siempre.
    assert que("Conductor de Seguridad Bilingüe (Medio Día)")[3] == "medio_dia"
    assert que("Conductor + CUV (Todo incluido, Transfer)")[3] == "transfer"


# ================================================================ la lectura

def test_cada_pais_lee_lo_suyo(db, filtros, de_brasil, brasil, mexico):
    _real(db)
    odoo = OdooFalso(mundo_brasil())
    informe = _leido(db, odoo)

    # Los productos de Brasil, de su categoria y con su nombre en portugues.
    paquete = _producto_de(db, PAQUETE_BR)
    conductor = db.query(m.PerfilPersonal).filter_by(codigo="conductor_seguridad").one()
    minivan = db.query(m.CategoriaVehiculo).filter_by(codigo="minivan_blindada").one()
    assert paquete.nombre == PAQUETE_PT and paquete.pais_id == brasil.id
    assert (paquete.clase, paquete.modalidad) == ("paquete", "mes")
    assert (paquete.perfil_id, paquete.categoria_id) == (conductor.id, minivan.id)
    extra = _producto_de(db, EXTRA_BR)
    assert (extra.nombre, extra.clase, extra.perfil_id) == (EXTRA_PT, "hora_extra",
                                                            conductor.id)
    assert _producto_de(db, DESPESAS).vendible is False
    motorista = _producto_de(db, PRODUCTO0 + 201)
    assert (motorista.nombre, motorista.clase, motorista.modalidad) == (
        "Motorista Executivo Bilíngue", "rol", "full_day")
    assert _producto_de(db, PRODUCTO0 + 1).pais_id == mexico.id
    assert ("product.template", "pt_BR", None) in odoo.llamadas

    # Lo que se leyo de cada pais.
    assert informe["por_pais"] == [
        {"codigo": "MX", "pais": mexico.nombre, "leidas": 4},
        {"codigo": "BR", "pais": brasil.nombre, "leidas": 3}]
    assert informe["lecturas"][1] == {
        "codigo": "BR", "pais": brasil.nombre,
        "categoria": "Proteção Executiva Brasil", "prefijo": "Brasil ·",
        "idioma": "pt_BR", "compania": CENTAURO_BR, "en_odoo": True}
    assert informe["lecturas"][0]["compania"] == CENTAURO_ASS
    assert informe["fuera"] == 2            # «Lista vieja» y «Predeterminado»
    assert [(g["nombre"], g["moneda"], g["pais"]) for g in informe["generales"]] == [
        ("PE · General México", "MXN", mexico.nombre),
        ("Brasil · General", "BRL", brasil.nombre),
        ("Brasil · General USD", "USD", brasil.nombre)]
    assert not [p for p in informe["pendientes"] if p["tipo"] in (
        "sin_general", "lista_no_cuadra", "lista_de_otro_pais", "otra_moneda",
        "producto_de_otro_pais", "sin_categoria_pais")], informe["pendientes"]

    # La lista de Amazon Brasil: el paquete del mes con su hora extra, y
    # nada de Mexico.
    lista = tarifario(db, 35)
    assert (lista.pais_id, lista.moneda) == (brasil.id, m.Moneda.USD)
    assert lista.precio_hora_extra is None
    [fila] = [p for p in lista.tarifas_paquete
              if p.modalidad.codigo == m.CodigoModalidad.IMPLANTADO]
    assert fila.modalidad.pais_id == brasil.id
    assert D(fila.precio) == D(16855) and D(fila.precio_hora_extra) == D(112)
    assert fila.producto_odoo_id == paquete.id
    assert fila.producto_hora_extra_id == extra.id
    assert not any(r.perfil.codigo == "agente_seguridad" for r in lista.tarifas_recurso)
    leida = next(l for l in informe["por_cliente"] if l["odoo_id"] == LISTA_BR)
    assert (leida["propios"], leida["pais"]) == (2, brasil.nombre)
    # Sus precios cuentan cada hora extra: el mensual, su hora extra y la
    # Minivan, de su «Precio de venta» (ensayo: «3 precios, 2 propios»).
    assert leida["precios"] == 3
    assert leida["clientes"] == leida["implantados"] == [NOMBRE_BR]

    # La general de reales: lo pactado, tal cual, con las modalidades de
    # Brasil; la hora extra de cada puesto, la de la lista (no se calcula).
    general = tarifario(db, 37)
    assert general.general and (general.pais_id, general.moneda) == (brasil.id, m.Moneda.BRL)
    p = precios(general)
    fd, md, tr = "full_day", "medio_dia", "transfer"
    assert p[("conductor_seguridad", fd)] == (D(1500), reglas.PROPIO)
    assert p[("conductor_seguridad", md)] == (D(900), reglas.PROPIO)
    assert p[("conductor_seguridad", tr)] == (D(600), reglas.PROPIO)
    assert p[("consultor_seguridad", fd)] == (D(2500), reglas.PROPIO)
    assert p[("suv_blindada", fd)] == (D(3000), reglas.PROPIO)
    assert p[("conductor_seguridad+suv_blindada", fd)] == (D(4800), reglas.PROPIO)
    assert p[("conductor_seguridad+minivan_blindada", md)] == (D(2900), reglas.PROPIO)
    # Sin regla, su «Precio de venta», que ya esta en reales.
    assert p[("minivan", fd)] == (D(900), reglas.PRECIO_VENTA)
    # En Brasil no hay agente: no lo cobra.
    assert not any(k[0] == "agente_seguridad" for k in p)
    extras = {r.perfil.codigo: r.precio_hora_extra for r in general.tarifas_recurso
              if r.modalidad.codigo == m.CodigoModalidad.FULL_DAY}
    assert D(extras["conductor_seguridad"]) == D(450)
    assert D(extras["consultor_seguridad"]) == D(750)
    # El coordenador no trae la suya en la lista: no se inventa.
    assert extras["coordinador_seguridad"] is None
    assert {r.modalidad.pais_id for r in general.tarifas_recurso} == {brasil.id}

    # La de dolares: lo pactado en dolares y lo demas de la de reales, con
    # el dolar a real de Centauro --6.00, no el 1 de Odoo--.
    usd = tarifario(db, 38)
    assert usd.general and usd.moneda == m.Moneda.USD
    p = precios(usd)
    assert p[("conductor_seguridad", fd)] == (D(250), reglas.PROPIO)
    assert p[("consultor_seguridad", fd)] == (D("416.67"), reglas.GENERAL)
    assert p[("minivan", fd)] == (D(150), reglas.PRECIO_VENTA)
    assert D(next(r.precio_hora_extra for r in usd.tarifas_recurso
                  if r.perfil.codigo == "conductor_seguridad"
                  and r.modalidad.codigo == m.CodigoModalidad.FULL_DAY)) == D(75)

    # Cada cliente de Brasil, con la lista que dice su ficha en la compania
    # de Brasil: Amazon, la suya; el de Sao Paulo, la general de reales.
    db.expire_all()
    amazon = db.get(m.Cliente, de_brasil.amazon)
    assert amazon.tarifario.odoo_id == amazon.tarifario_implantado.odoo_id == LISTA_BR
    assert db.get(m.Cliente, de_brasil.cliente).tarifario.odoo_id == GENERAL_BR
    assert ("res.partner", None, 5) in odoo.llamadas
    assert ("res.partner", None, 1) in odoo.llamadas


def test_sin_el_dolar_a_real_no_se_inventa_uno(db, filtros, de_brasil):
    """En la compania de Mexico el real vale 1: con el de Odoo, 2,500
    reales serian 125 dolares. Sin el de Centauro no hay precio, y se
    dice."""
    informe = _leido(db, OdooFalso(mundo_brasil()))
    p = precios(tarifario(db, 38))
    assert p[("conductor_seguridad", "full_day")] == (D(250), reglas.PROPIO)
    assert ("consultor_seguridad", "full_day") not in p
    assert {"tipo": "regla", "lista": "Brasil · General USD",
            "producto": "Consultor de Segurança Bilíngue",
            "problema": "sin tipo de cambio"} in informe["pendientes"]


def test_una_ficha_con_predeterminado_se_dice_con_el_prefijo_de_brasil(
        db, filtros, de_brasil):
    """«Predeterminado» no es de PE: se dice con el prefijo de Brasil y el
    cliente se queda como estaba."""
    tablas = mundo_brasil()
    socio = next(s for s in tablas["res.partner"] if s["id"] == CLIENTE_BR)
    socio["_compania"][5]["property_product_pricelist"] = [PREDETERMINADO,
                                                           "Predeterminado"]
    informe = _leido(db, OdooFalso(tablas))
    assert {"tipo": "lista_no_pe", "cliente": NOMBRE_CLIENTE_BR,
            "lista": "Predeterminado", "prefijo": "Brasil ·"} in informe["pendientes"]
    db.expire_all()
    assert db.get(m.Cliente, de_brasil.cliente).tarifario_id is None


def test_una_lista_de_otro_pais_nunca_se_le_pone(db, filtros, de_brasil, brasil,
                                                 mexico):
    tablas = mundo_brasil()
    socio = next(s for s in tablas["res.partner"] if s["id"] == CLIENTE_BR)
    socio["_compania"][5]["property_product_pricelist"] = [LISTA0 + 1,
                                                           "PE · General México"]
    informe = _leido(db, OdooFalso(tablas))
    assert {"tipo": "lista_de_otro_pais", "cliente": NOMBRE_CLIENTE_BR,
            "lista": "PE · General México", "pais_lista": mexico.nombre,
            "pais": brasil.nombre} in informe["pendientes"]
    assert not any(c["cliente"] == NOMBRE_CLIENTE_BR for c in informe["cambian"])
    db.expire_all()
    assert db.get(m.Cliente, de_brasil.cliente).tarifario_id is None

    # La de sus implantados, igual.
    socio["_compania"][5]["property_product_pricelist"] = [GENERAL_BR,
                                                           "Brasil · General"]
    socio[CAMPO] = [LISTA0 + 4, "PE · HASBRO Implantados"]
    informe = leer(db, OdooFalso(tablas))
    assert {"tipo": "lista_de_otro_pais", "cliente": NOMBRE_CLIENTE_BR,
            "lista": "PE · HASBRO Implantados", "pais_lista": mexico.nombre,
            "pais": brasil.nombre, "implantados": True} in informe["pendientes"]
    db.expire_all()
    cliente = db.get(m.Cliente, de_brasil.cliente)
    assert cliente.tarifario.odoo_id == GENERAL_BR
    assert cliente.tarifario_implantado_id is None


def test_brasil_sin_lista_general_se_dice(db, filtros, de_brasil, brasil, mexico):
    """Asi estaba antes de que Ari cargara las generales: se dice, y su
    cliente sin lista no toma la de Mexico."""
    tablas = mundo_brasil()
    tablas["product.pricelist"] = [l for l in tablas["product.pricelist"]
                                   if l["id"] not in (GENERAL_BR, GENERAL_USD)]
    socio = next(s for s in tablas["res.partner"] if s["id"] == CLIENTE_BR)
    socio["_compania"][5]["property_product_pricelist"] = [PREDETERMINADO,
                                                           "Predeterminado"]
    informe = _leido(db, OdooFalso(tablas), ensayo=True)
    sin = [p for p in informe["pendientes"] if p["tipo"] == "sin_general"]
    assert sin == [{"tipo": "sin_general", "pais": brasil.nombre}]
    assert [g["pais"] for g in informe["generales"]] == [mexico.nombre]


def test_los_productos_de_un_pais_no_ponen_precio_en_la_lista_de_otro(
        db, filtros, de_brasil, brasil, mexico):
    _real(db)
    tablas = mundo_brasil()
    # La lista de Brasil nombra al conductor de Mexico.
    tablas["product.pricelist.item"].append(
        _fija(103, PRODUCTO0 + 1, "Conductor de Seguridad Bilingüe", 99))
    informe = _leido(db, OdooFalso(tablas))
    assert {"tipo": "producto_de_otro_pais",
            "lista": "Brasil · Amazon Implantados (USD)",
            "producto": "Conductor de Seguridad Bilingüe", "pais": mexico.nombre,
            "pais_lista": brasil.nombre} in informe["pendientes"]
    assert D(99) not in {D(r.precio) for r in tarifario(db, 35).tarifas_recurso}
    # Y las de Mexico no se llevan lo de Brasil.
    for n in (1, 2):
        assert {r.modalidad.pais_id for t in (tarifario(db, n),)
                for r in t.tarifas_recurso + t.tarifas_vehiculo + t.tarifas_paquete
                } == {mexico.id}


def test_la_lista_que_no_cuadra_con_su_compania_no_se_lee(db, filtros, de_brasil,
                                                          mexico):
    tablas = mundo_brasil()
    lista = next(l for l in tablas["product.pricelist"] if l["id"] == LISTA_BR)
    lista["name"] = "PE · Amazon Brasil (USD)"
    informe = _leido(db, OdooFalso(tablas))
    assert {"tipo": "lista_no_cuadra", "lista": "PE · Amazon Brasil (USD)",
            "pais": mexico.nombre, "compania": CENTAURO_BR} in informe["pendientes"]
    assert db.query(m.Tarifario).filter_by(odoo_id=LISTA_BR).first() is None


def test_la_categoria_de_brasil_dentro_de_la_de_mexico(monkeypatch):
    """Si en Odoo la de Brasil cuelga de la de Mexico, lo de abajo es de
    Brasil: manda la raiz mas cercana."""
    con_filtros(monkeypatch)
    filas = [{"id": 2, "name": "Protección Ejecutiva", "parent_path": "1/2/"},
             {"id": 5, "name": "Proteção Executiva Brasil", "parent_path": "1/2/5/"},
             {"id": 6, "name": "Unidades", "parent_path": "1/2/5/6/"},
             {"id": 7, "name": "Unidades", "parent_path": "1/2/7/"}]
    assert odoo_tarifarios.categorias_por_pais(filas) == {"MX": {2, 7},
                                                          "BR": {5, 6}}


def test_sin_la_categoria_de_brasil_su_lista_se_dice(db, filtros, de_brasil, brasil):
    tablas = mundo_brasil()
    tablas["product.category"] = [c for c in tablas["product.category"] if c["id"] != 5]
    informe = _leido(db, OdooFalso(tablas), ensayo=True)
    assert {"tipo": "sin_categoria_pais", "pais": brasil.nombre,
            "categoria": "Proteção Executiva Brasil"} in informe["pendientes"]
    assert informe["lecturas"][1]["en_odoo"] is False


def test_la_flota_sin_precio_en_su_general_se_dice_sin_bloquear(
        db, filtros, de_brasil, brasil):
    """Las seis Corolla Cross de Brasil son «CUV Blindada», que las
    generales de Brasil todavia no cobran."""
    cuv = db.query(m.CategoriaVehiculo).filter_by(codigo="cuv_blindada").one()
    suv = db.query(m.CategoriaVehiculo).filter_by(codigo="suv_blindada").one()
    for i in range(6):
        db.add(m.Vehiculo(placa=f"BR-CC{i}", categoria_id=cuv.id, pais_id=brasil.id,
                          odoo_id=9_990_000 + i, activo=True))
    db.add(m.Vehiculo(placa="BR-SUV1", categoria_id=suv.id, pais_id=brasil.id,
                      odoo_id=9_990_010, activo=True))
    db.commit()
    informe = _leido(db, OdooFalso(mundo_brasil()))
    assert [p for p in informe["pendientes"] if p["tipo"] == "flota_sin_precio"] == [
        {"tipo": "flota_sin_precio", "pais": brasil.nombre, "categoria": cuv.nombre,
         "unidades": 6}]
    # La lectura se aplico igual: no detiene nada.
    assert tarifario(db, 37).activo


# ================================================================ en la consola

def test_el_tarifario_de_brasil_se_ve_por_mes(db, filtros, de_brasil, cliente,
                                              sesion, monkeypatch):
    odoo = OdooFalso(mundo_brasil())
    _leido(db, odoo)
    conectar(monkeypatch, odoo)
    h = sesion("finanzas")
    d = cliente.get(f"/tarifarios/cliente/{de_brasil.amazon}", headers=h).json()
    [paquete] = [x for x in d["implantados"]["paquetes"] if x["modalidad"] == "mes"]
    assert D(paquete["precio"]) == D(16855)
    assert D(paquete["precio_hora_extra"]) == D(112)
    # El tipo de cambio de su pais: el dolar a real.
    assert (d["tipo_cambio"]["moneda"], d["tipo_cambio"]["moneda_local"]) == ("USD", "BRL")

    productos = cliente.get("/tarifarios/productos", headers=h).json()
    assert [(p["codigo"], p["categoria"], p["idioma"]) for p in productos["paises"]] == [
        ("MX", "Protección Ejecutiva", "es_MX"),
        ("BR", "Proteção Executiva Brasil", "pt_BR")]
    # Cuando se leyo, con su zona: la consola lo dice en la hora de quien
    # mira, no en la de Londres.
    assert productos["leidos_en"].endswith("+00:00")
    assert d["implantados"]["leido_en"].endswith("+00:00")
    suyo = next(p for p in productos["productos"] if p["odoo_id"] == PAQUETE_BR)
    assert (suyo["pais"], suyo["nombre"], suyo["modalidad"]) == ("BR", PAQUETE_PT, "mes")
    # Finanzas puede decir que un producto es «por mes».
    r = cliente.patch(f"/tarifarios/productos/{suyo['id']}", headers=h, json={
        "clase": "paquete", "perfil_id": suyo["perfil_id"],
        "categoria_id": suyo["categoria_id"], "modalidad": "mes"})
    assert r.status_code == 200, r.text
    assert r.json()["modalidad"] == "mes" and r.json()["confirmado"] is True


def test_el_que_manda_es_de_su_pais(db, brasil, mexico, cliente, sesion):
    """«Que mande este» en un producto de Brasil le quita la marca al de
    Brasil que dice lo mismo, nunca al de Mexico: cada lista se lee con los
    productos de su pais."""
    conductor = db.query(m.PerfilPersonal).filter_by(codigo="conductor_seguridad").one()

    def producto(odoo_id, nombre, pais, preferido=False):
        p = m.ProductoOdoo(odoo_id=odoo_id, nombre=nombre, clase="hora_extra",
                           perfil_id=conductor.id, pais_id=pais.id,
                           confirmado=True, preferido=preferido)
        db.add(p)
        db.flush()
        return p.id

    mx = producto(PRODUCTO0 + 900, "Hora Extra Conductor de Seguridad Bilingüe",
                  mexico, preferido=True)
    br_puesto = producto(PRODUCTO0 + 901, "Hora Extra Motorista Executivo Bilíngue",
                         brasil, preferido=True)
    br_paquete = producto(PRODUCTO0 + 902, EXTRA_PT, brasil)
    db.commit()
    r = cliente.post(f"/tarifarios/productos/{br_paquete}/preferido",
                     headers=sesion("finanzas"), json={"preferido": True})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(m.ProductoOdoo, br_paquete).preferido
    assert not db.get(m.ProductoOdoo, br_puesto).preferido
    assert db.get(m.ProductoOdoo, mx).preferido


def test_confirmar_los_sugeridos_de_una_pestana(db, brasil, mexico, cliente, sesion):
    """«Confirmar los sugeridos» en la pestana de Brasil confirma los de
    Brasil y deja los de Mexico para su pestana (seccion 124)."""
    conductor = db.query(m.PerfilPersonal).filter_by(codigo="conductor_seguridad").one()

    def sugerido(odoo_id, nombre, pais):
        p = m.ProductoOdoo(odoo_id=odoo_id, nombre=nombre, clase="rol",
                           perfil_id=conductor.id, modalidad="full_day",
                           pais_id=pais.id, confirmado=False)
        db.add(p)
        db.flush()
        return p.id

    mx = sugerido(PRODUCTO0 + 910, "Conductor de Seguridad Bilingüe", mexico)
    br = sugerido(PRODUCTO0 + 911, "Motorista Executivo Bilíngue", brasil)
    db.commit()
    h = sesion("finanzas")
    r = cliente.post("/tarifarios/productos/confirmar", headers=h, json={"ids": [br]})
    assert r.status_code == 200, r.text
    assert r.json()["confirmados"] == 1
    db.expire_all()
    assert db.get(m.ProductoOdoo, br).confirmado
    assert not db.get(m.ProductoOdoo, mx).confirmado
    # Sin decir cuales, todos, como antes.
    assert cliente.post("/tarifarios/productos/confirmar", headers=h,
                        json={}).json()["confirmados"] == 1
    # La consola manda los de la pestana que se ve.
    import pathlib
    js = (pathlib.Path(__file__).parent.parent / "app" / "web" / "tarifarios.js").read_text(
        encoding="utf-8")
    assert 'ids: pestanas.visibles.filter(p => estadoDe(p) === "sugerido")' in js


def test_una_general_se_abre_sin_cliente(db, filtros, de_brasil, brasil, cliente, sesion,
                                         monkeypatch):
    """«Brasil · General USD» no tiene cliente: se abre por si misma, con
    el dolar a real, y ahi se marca si sus paquetes traen los viaticos
    (seccion 124)."""
    odoo = OdooFalso(mundo_brasil())
    _leido(db, odoo)
    conectar(monkeypatch, odoo)
    h = sesion("finanzas")
    usd = tarifario(db, 38)
    d = cliente.get(f"/tarifarios/lista/{usd.id}", headers=h).json()
    assert (d["tarifario"]["nombre"], d["tarifario"]["general"]) == ("Brasil · General USD", True)
    assert d["puede_editar"] is True and d["implantados"] is None
    assert (d["tipo_cambio"]["moneda"], d["tipo_cambio"]["moneda_local"]) == ("USD", "BRL")
    assert d["tarifario"]["leido_en"].endswith("+00:00")
    r = cliente.patch(f"/tarifarios/{usd.id}/viaticos", headers=h, json={"incluidos": True})
    assert r.status_code == 200 and r.json()["paquetes_con_viaticos"] is True
    # Quien cotiza la ve, pero no la marca.
    d = cliente.get(f"/tarifarios/lista/{usd.id}", headers=sesion("consultor")).json()
    assert d["puede_editar"] is False and d["tarifario"]["paquetes_con_viaticos"] is True
    assert cliente.get("/tarifarios/lista/999999", headers=h).status_code == 404
    # En la consola, las generales van arriba de los clientes.
    generales = [x for x in cliente.get("/tarifarios", headers=h).json() if x["general"]]
    assert {x["nombre"] for x in generales} >= {"Brasil · General", "Brasil · General USD"}
    # Cada una dice su pais: la consola la pone en su pestana (seccion 125).
    assert {x["pais_id"] for x in generales if x["nombre"].startswith("Brasil ·")} == {brasil.id}


def test_el_dolar_a_real_lo_pone_finanzas(cliente, sesion, db):
    h = sesion("finanzas")
    d = cliente.get("/tarifarios/tipo-de-cambio", headers=h).json()
    assert [(p["moneda"], p["moneda_local"]) for p in d["pares"]] == [
        ("USD", "MXN"), ("USD", "BRL")]
    assert all(p["vigente"] is None for p in d["pares"])
    r = cliente.put("/tarifarios/tipo-de-cambio", headers=h,
                    json={"tasa": "6.00", "moneda_local": "BRL"})
    assert r.status_code == 200, r.text
    pares = {p["moneda_local"]: p for p in r.json()["pares"]}
    assert pares["BRL"]["vigente"]["tasa"] == "6.0000"
    assert pares["MXN"]["vigente"] is None          # el del peso, aparte
    assert r.json()["vigente"] is None              # arriba, el del peso
    registro = (db.query(m.RegistroAdmin)
                .filter(m.RegistroAdmin.accion == "tipo de cambio").all())
    assert [(x.despues, x.detalle) for x in registro] == [("6.0000", "reales por dolar")]
    # Solo dolares: de reales a pesos no se convierte.
    r = cliente.put("/tarifarios/tipo-de-cambio", headers=h,
                    json={"tasa": "3.2", "moneda_local": "USD"})
    assert r.status_code == 400
    assert cliente.put("/tarifarios/tipo-de-cambio", headers=sesion("consultor"),
                       json={"tasa": "5.4", "moneda_local": "BRL"}).status_code == 403
    # El arranque lo dice aparte del dolar a peso.
    a = cliente.get("/manual/arranque", headers=sesion("dirgeneral")).json()
    renglones = {x["clave"]: x for g in a["grupos"] for x in g["renglones"]}
    assert renglones["tipo_cambio_br"]["tono"] == "ok"
    assert renglones["tipo_cambio_br"]["como"].startswith("R$6.00 por dólar")
    assert renglones["tipo_cambio"]["tono"] == "grave"


def test_el_eventual_de_brasil_escoge_reales_o_dolares(db, filtros, de_brasil,
                                                       cliente, sesion):
    """Seccion 120 con Brasil: el cliente en la general escoge entre la de
    reales y la de dolares; Amazon, con su lista, no escoge."""
    _real(db)
    _leido(db, OdooFalso(mundo_brasil()))
    h = sesion("consultor")
    r = cliente.get(f"/cotizaciones/eventual/lista-de-precios?cliente_id={de_brasil.cliente}",
                    headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["monedas"] == ["BRL", "USD"]
    assert r.json()["tarifario"]["nombre"] == "Brasil · General"
    dolares = cliente.get(f"/cotizaciones/eventual/lista-de-precios?cliente_id="
                          f"{de_brasil.cliente}&moneda=USD", headers=h).json()
    assert dolares["tarifario"]["nombre"] == "Brasil · General USD"
    # El paquete del mes no es un precio por dia: no se cotiza en un
    # eventual. La Minivan, si: la lista de Amazon la cobra a su «Precio de
    # venta», como Odoo.
    from app import cotizacion as cot

    roles, unidades = cot.lo_que_tiene_precio(db, tarifario(db, 35).id)
    assert roles == [] and [u["nombre"] for u in unidades] == ["Minivan"]


# ================================================================ la propuesta

def _propuesta(db, amazon, datos, **extra):
    sao_paulo = db.query(m.Plaza).filter_by(nombre="Sao Paulo").one()
    perfiles, categorias = datos["perfiles"], datos["categorias"]
    return {
        "cliente_id": amazon,
        "solicitante_nombre": "Beatriz", "solicitante_apellidos": "Souza",
        "solicitante_correo": "beatriz.souza@ejemplo.com",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "plaza_id": sao_paulo.id, "tipo_servicio": "Motorista executivo",
        "valida_hasta": str(date.today() + timedelta(days=60)),
        "idioma": "pt", "con_iva": False, "inicio": "2029-10-01",
        "dias_servicio": "lunes_viernes", "viaticos": "incluidos",
        "posiciones": [{"tipo": "paquete", "cantidad": 1,
                        "perfil_id": perfiles["conductor_seguridad"]["id"],
                        "categoria_id": categorias["minivan_blindada"]["id"]}],
        **extra}


def test_la_propuesta_de_amazon_brasil(db, filtros, de_brasil, cliente, sesion,
                                       datos):
    _leido(db, OdooFalso(mundo_brasil()))
    # Tudo incluído: finanzas marca que sus paquetes traen los viaticos.
    lista = tarifario(db, 35)
    r = cliente.patch(f"/tarifarios/{lista.id}/viaticos", json={"incluidos": True},
                      headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    h = sesion("consultor")
    amazon = de_brasil.amazon

    info = cliente.get(f"/cotizaciones/propuesta/lista-de-precios?cliente_id={amazon}",
                       headers=h).json()
    assert info["moneda"] == "USD" and info["lista"]["paquetes_con_viaticos"] is True
    [paquete] = [x for x in info["paquetes"] if x["precio_mes"] is not None]
    assert (paquete["precio_mes"], paquete["precio_dia"], paquete["hora_extra"]) == (
        16855.0, None, 112.0)
    assert paquete["producto"] == PAQUETE_PT

    # El mensual es el de la lista, tal cual; el dia, el mensual entre 22.
    r = cliente.post("/cotizaciones/propuesta/precios", headers=h,
                     json=_propuesta(db, amazon, datos))
    assert r.status_code == 200, r.text
    vista = r.json()
    [p] = vista["posiciones"]
    assert (p["precio_mes"], p["lista_precio_mes"], p["precio_dia"]) == (
        16855.0, 16855.0, 766.14)
    assert p["lista_por_mes"] is True and p["especial"] is False
    assert (vista["subtotal"], vista["dia_adicional"], vista["hora_extra"]) == (
        16855.0, 766.14, 112.0)
    assert vista["moneda"] == "USD" and vista["faltan_precios"] == []
    # Con el mes completo no hay dia adicional, y el mensual no cambia.
    todos = cliente.post("/cotizaciones/propuesta/precios", headers=h,
                         json=_propuesta(db, amazon, datos,
                                         dias_servicio="todos")).json()
    assert todos["subtotal"] == 16855.0 and todos["dia_adicional"] is None
    # Con mas viaticos el paquete no va: trae los gastos dentro.
    aparte = cliente.post("/cotizaciones/propuesta/precios", headers=h,
                          json=_propuesta(db, amazon, datos, viaticos="aparte"))
    assert aparte.status_code == 400
    assert aparte.json()["detail"]["clave"] == "paquete_con_gastos"

    # Guardada, enviada: el mismo mensual, sin redondeos.
    creada = cliente.post("/cotizaciones/propuesta", headers=h,
                          json=_propuesta(db, amazon, datos))
    assert creada.status_code == 201, creada.text
    pid = creada.json()["id"]
    enviada = cliente.post(f"/cotizaciones/propuesta/{pid}/enviar", headers=h)
    assert enviada.status_code == 200, enviada.text
    [p] = enviada.json()["posiciones"]
    assert (p["precio_mes"], p["lista_precio_mes"], p["lista_por_mes"]) == (
        16855.0, 16855.0, True)
    assert enviada.json()["subtotal"] == 16855.0

    # Sin el dolar a real no se autoriza.
    autorizar = {"autorizada_por": "Beatriz Souza", "autorizada_el": str(date.today())}
    r = cliente.post(f"/cotizaciones/propuesta/{pid}/autorizar", data=autorizar,
                     headers=h)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["motivo"] == "sin_tipo_de_cambio"
    assert (r.json()["detail"]["moneda"], r.json()["detail"]["local"]) == ("USD", "BRL")
    r = cliente.put("/tarifarios/tipo-de-cambio", headers=sesion("finanzas"),
                    json={"tasa": "6.00", "moneda_local": "BRL"})
    assert r.status_code == 200, r.text
    r = cliente.post(f"/cotizaciones/propuesta/{pid}/autorizar", data=autorizar,
                     headers=h)
    assert r.status_code == 200, r.text
    servicio = db.get(m.Servicio, r.json()["servicio_id"])

    # El mes nace con lo pactado: USD 16,855 al mes, el dia adicional y la
    # hora extra, en dolares con el dolar a real de ese dia.
    terminos = motor_propuesta.terminos_del_primer_mes(db, servicio)
    assert terminos["precio_mes_completo"] == D(16855)
    assert terminos["precio_dia_adicional"] == D("766.14")
    assert terminos["precio_hora_extra"] == D(112)
    assert terminos["moneda"] == m.Moneda.USD
    assert Decimal(str(terminos["tipo_cambio"])) == Decimal("6.00")

    # La prefactura del mes: el paquete con su producto y la hora extra con
    # la suya.
    cot = motor_propuesta.autorizada_de(db, servicio.id)
    contrato = SimpleNamespace(servicio=servicio, modalidad=None)
    [puesto] = odoo_facturacion_mes.puestos_del_mes(db, contrato, cot)
    assert (puesto.tipo, puesto.mes, puesto.dia, puesto.he) == (
        "paquete", D(16855), D("766.14"), D(112))
    faltan = []
    productos = odoo_facturacion_mes.Productos(db, contrato,
                                               lambda *a, **k: faltan.append(a))
    paquete, extra = _producto_de(db, PAQUETE_BR), _producto_de(db, EXTRA_BR)
    assert productos.del_puesto(puesto) == paquete.id
    assert productos.de_hora_extra(puesto.perfil_id) == extra.id
    assert productos.variante(paquete.id, "paquete") == (PAQUETE_BR + 1000, PAQUETE_PT)
    assert faltan == []

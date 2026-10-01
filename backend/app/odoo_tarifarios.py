# -*- coding: utf-8 -*-
"""Los tarifarios, leidos de Odoo (seccion 77).

Salvador, 26 de septiembre: los tarifarios viven en Odoo. Cada pais
tiene su lista general --la que trae su pais en Odoo-- y el cliente que
negocio tiene la suya, puesta en su ficha. Centauro las lee de ahi y ya
no se capturan aqui.

Funciona como las otras lecturas: ensayo que no guarda nada, la primera a
mano y de ahi cada hora sola. Nunca escribe en Odoo. Y tres cuidados que
son de esta lectura:

  * Solo pone precio lo que finanzas ya confirmo en la tabla de
    productos. Lo sugerido espera: un precio mal leido se cobra.
  * A un cliente no se le cambia a una lista que todavia no tiene ningun
    precio que Centauro sepa leer: se queda con el tarifario que tenia y
    se dice. Asi el primer dia nadie se queda sin poder cotizar.
  * Una lista en otra moneda que la de su pais --Amazon, en dolares-- se
    lee en su moneda (seccion 82). Lo que toma de otra lista en pesos se
    convierte con el tipo de cambio que puso finanzas en Centauro, no con
    el de Odoo: el que se pone aplica para todo. Solo la lista en una
    moneda que Centauro no convierte --dolares en Brasil-- se dice y no
    se lee.

Solo lo de Proteccion Ejecutiva (seccion 112, pedido de Salvador): Odoo
vende tambien el GPS, la Central de Inteligencia y ATLAS, y antes se leia
todo. Ahora se leen los productos de la categoria de Odoo
`odoo_categoria_productos` --con sus subcategorias; tambien los que una
lista nombra aunque ya no esten a la venta-- y las listas cuyo nombre
empieza con `odoo_prefijo_listas` («PE · General México»). Si esa
categoria no esta en Odoo no se toca nada: leer todo seria volver a traer
el GPS.

Las reglas --que es cada producto, cuanto cuesta en cada lista-- viven en
odoo_tarifarios_reglas.py, sin base de datos.
"""
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app import accesos, odoo_api
from app import models as m
from app import odoo_tarifarios_reglas as reglas
from app import tipo_cambio
from app.config import settings
from app.odoo_personal_reglas import nombre_de, normal, texto

registro = logging.getLogger("centauro.odoo")

TIPO = "tarifarios"
CAMPOS_LISTA = ["name", "currency_id", "country_group_ids", "active"]
CAMPOS_REGLA = ["pricelist_id", "applied_on", "product_tmpl_id", "product_id",
                "categ_id", "min_quantity", "compute_price", "fixed_price",
                "percent_price", "base", "base_pricelist_id",
                "price_discount", "price_surcharge", "price_round",
                "price_min_margin", "price_max_margin", "date_start",
                "date_end"]
CAMPOS_PRODUCTO = ["name", "list_price", "categ_id", "uom_id", "type",
                   "sale_ok", "active",
                   # La variante con que se factura (seccion 116).
                   "product_variant_id", "product_variant_count"]
MONEDAS = {mo.value: mo for mo in m.Moneda}


def _utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def en_marcha(db: Session) -> bool:
    """Si ya se hizo la primera lectura a mano: desde entonces el
    tarifario de los clientes de Odoo lo pone Odoo."""
    return db.query(m.SincronizacionOdoo.id).filter_by(
        tipo=TIPO, automatica=False).first() is not None


# ================================================================ productos

def _catalogos(db: Session) -> tuple[dict, dict]:
    perfiles = [{"id": p.id, "codigo": p.codigo, "nombre": p.nombre}
                for p in db.query(m.PerfilPersonal).filter_by(activo=True)]
    categorias = [{"id": c.id, "codigo": c.codigo, "nombre": c.nombre,
                   "blindado": c.blindado}
                  for c in db.query(m.CategoriaVehiculo).filter_by(activo=True)]
    return (reglas.perfiles_por_tipo(perfiles),
            reglas.categorias_por_tipo(categorias))


class SinCategoria(Exception):
    """La categoria de los productos de Proteccion Ejecutiva no esta en
    Odoo (seccion 112)."""


CAMPOS_CATEGORIA = ["name", "complete_name", "parent_path"]


def categorias_de_pe(odoo, filas: list | None = None) -> set | None:
    """Los ids de las categorias de productos de Proteccion Ejecutiva: la
    de `odoo_categoria_productos` y todas las que cuelgan de ella. None:
    la configuracion no pide filtro y se lee todo, como antes de la
    seccion 112. Si la categoria no esta en Odoo, `SinCategoria`."""
    nombre = (settings.odoo_categoria_productos or "").strip()
    if not nombre:
        return None
    if filas is None:
        filas = odoo.leer("product.category", [], CAMPOS_CATEGORIA)
    buscada = normal(nombre)
    raices = {c["id"] for c in filas
              if buscada in (normal(c.get("name")), normal(c.get("complete_name")))}
    if not raices:
        raise SinCategoria(nombre)
    salida = set()
    for c in filas:
        # «1/5/9/»: de la raiz a ella misma.
        camino = {int(x) for x in texto(c.get("parent_path")).split("/")
                  if x.isdigit()} | {c["id"]}
        if camino & raices:
            salida.add(c["id"])
    return salida


def es_de_pe(producto: dict, en_pe: set | None) -> bool:
    """Si un producto de Odoo es de Proteccion Ejecutiva, por su categoria."""
    return en_pe is None or reglas.id_de(producto.get("categ_id")) in en_pe


# Los puntos que se confunden con el «·» del prefijo: el que se teclea
# en el telefono o se copia de otro lado tambien vale.
PUNTOS = str.maketrans({c: "·" for c in "•∙‧⋅・"})


def _para_prefijo(texto_) -> str:
    return " ".join(normal(texto_).translate(PUNTOS).replace("·", " · ").split())


def es_lista_de_pe(nombre) -> bool:
    """Si una lista de precios es de Proteccion Ejecutiva, por como empieza
    su nombre (seccion 112): «PE · General México». Sin mayusculas,
    acentos ni espacios de sobra, y con cualquier punto medio. Sin prefijo
    en la configuracion, todas."""
    prefijo = _para_prefijo(settings.odoo_prefijo_listas)
    return not prefijo or _para_prefijo(nombre).startswith(prefijo)


def _nombrados(db: Session, producto_id: int) -> bool:
    """Si algun tarifario todavia nombra ese producto de la tabla: por un
    precio o por su hora extra (seccion 116)."""
    return (any(db.query(modelo.id).filter_by(producto_odoo_id=producto_id).first()
                for modelo in (m.TarifaRecurso, m.TarifaVehiculo, m.TarifaPaquete))
            or any(db.query(modelo.id)
                   .filter_by(producto_hora_extra_id=producto_id).first()
                   for modelo in (m.TarifaRecurso, m.Tarifario)))


def es_el_de_gastos(producto: dict | str | None) -> bool:
    """Si es el producto con que se facturan los gastos del eventual
    (seccion 116): «Gastos de Operación (Viáticos)», por su nombre, sin
    mayusculas ni acentos. Vale la fila de Odoo o el nombre."""
    buscado = normal(settings.odoo_producto_gastos or "")
    nombre = producto.get("name") if isinstance(producto, dict) else producto
    return bool(buscado) and normal(texto(nombre)) == buscado


# `leer_productos` sin `en_pe`: las categorias se leen ahi mismo.
POR_LEER = object()


def leer_productos(db: Session, odoo, referenciados=(), ahora=None,
                   en_pe=POR_LEER) -> dict:
    """Trae de Odoo los productos que se venden --y los que nombra alguna
    lista aunque ya no se vendan-- y los deja en la tabla de productos.

    Solo los de Proteccion Ejecutiva (seccion 112): los de su categoria.
    Lo que ya estaba en la tabla y no es de ahi --el GPS, la Central de
    Inteligencia-- sale de la tabla, salvo que algun tarifario lo nombre.

    Lo nuevo llega con su sugerencia. Lo que finanzas ya confirmo no se
    vuelve a sugerir: solo se le pone al dia el nombre, la unidad y el
    «Precio de venta». Lo de PE que Odoo ya no trae se queda, marcado como
    que ya no se vende. No hace commit: lo hace quien llama. `en_pe`: las
    categorias de PE, si quien llama ya las tiene.
    """
    ahora = ahora or _utc()
    if en_pe is POR_LEER:
        en_pe = categorias_de_pe(odoo)
    dominio = [["sale_ok", "=", True]]
    if referenciados:
        dominio = ["|", ["sale_ok", "=", True],
                   ["id", "in", sorted(referenciados)]]
    # El de los gastos entra aunque no sea de la categoria de PE: con el
    # se facturan los gastos del eventual (seccion 116).
    filas = [f for f in odoo.leer("product.template", dominio, CAMPOS_PRODUCTO,
                                  archivados=True)
             if es_de_pe(f, en_pe) or es_el_de_gastos(f)]
    perfiles, categorias = _catalogos(db)
    existentes = {p.odoo_id: p for p in db.query(m.ProductoOdoo).all()}
    vistos, nuevos, sugeridos = set(), 0, 0
    for f in filas:
        vistos.add(f["id"])
        producto = existentes.get(f["id"])
        if producto is None:
            producto = m.ProductoOdoo(odoo_id=f["id"], confirmado=False)
            db.add(producto)
            nuevos += 1
        producto.nombre = texto(f.get("name"))[:200] or f"#{f['id']}"
        producto.unidad = texto(nombre_de(f.get("uom_id")))[:60] or None
        producto.tipo_odoo = texto(f.get("type"))[:20] or None
        producto.precio_venta = f.get("list_price") or 0
        producto.vendible = bool(f.get("sale_ok")) and f.get("active", True) is not False
        # La variante con que Odoo lo factura (seccion 116): con una sola,
        # esa; con varias, ninguna --no se adivina-- y la lectura lo dice.
        cuantas = f.get("product_variant_count")
        producto.variantes = (cuantas if isinstance(cuantas, int)
                              and not isinstance(cuantas, bool) else None)
        producto.variante_odoo_id = (reglas.id_de(f.get("product_variant_id"))
                                     if producto.variantes == 1 else None)
        producto.odoo_sincronizado_en = ahora
        if not producto.confirmado:
            s = reglas.sugerir(f, perfiles, categorias)
            producto.clase = s["clase"]
            producto.perfil_id = s["perfil_id"]
            producto.categoria_id = s["categoria_id"]
            producto.modalidad = s["modalidad"]
            sugeridos += 1 if s["clase"] else 0
    faltan = [p for odoo_id, p in existentes.items() if odoo_id not in vistos]
    for producto in faltan:
        producto.vendible = False
    # Lo que ya estaba y no es de Proteccion Ejecutiva --el GPS, la Central
    # de Inteligencia, ATLAS-- sale de la tabla (seccion 112). Lo de PE que
    # ya no se vende se queda, en gris; y lo que algun tarifario todavia
    # nombra tambien, aunque no sea de PE: sin el, ese renglon no se lee.
    # Lo que Odoo ya ni trae se queda como estaba.
    quitados = 0
    if en_pe is not None and faltan:
        suyas = {f["id"]: f for f in odoo.leer(
            "product.template", [["id", "in", sorted(p.odoo_id for p in faltan)]],
            ["categ_id"], archivados=True)}
        for producto in faltan:
            fila = suyas.get(producto.odoo_id)
            if fila is None or es_de_pe(fila, en_pe) or _nombrados(db, producto.id):
                continue
            db.delete(producto)
            quitados += 1
    db.flush()
    return {"leidos": len(filas), "nuevos": nuevos, "sugeridos": sugeridos,
            "quitados": quitados}


def tabla_de_productos(db: Session) -> list[dict]:
    return [{"id": p.id, "odoo_id": p.odoo_id, "nombre": p.nombre,
             "unidad": p.unidad, "tipo_odoo": p.tipo_odoo,
             "precio_venta": p.precio_venta, "vendible": p.vendible,
             "clase": p.clase, "perfil_id": p.perfil_id,
             "categoria_id": p.categoria_id, "modalidad": p.modalidad,
             "confirmado": p.confirmado, "preferido": p.preferido,
             "confirmado_en": (p.confirmado_en.isoformat()
                               if p.confirmado_en else None),
             # Para la factura (seccion 116): cuantas variantes tiene en
             # Odoo --con varias no se sabe con cual cobrar-- y si es el de
             # los gastos.
             "variantes": p.variantes,
             "de_gastos": es_el_de_gastos(p.nombre)}
            for p in db.query(m.ProductoOdoo)
            .order_by(m.ProductoOdoo.vendible.desc(), m.ProductoOdoo.nombre)]


# ================================================================ la lectura

def campo_de_implantados(odoo) -> str | None:
    """El campo de la ficha del cliente con la lista de sus implantados:
    el que se llama «Lista de implantados», o el nombre tecnico que diga
    la configuracion. Mientras finanzas no lo agregue con Studio, no hay."""
    try:
        campos = odoo.campos("res.partner", ["string", "type", "relation"])
    except Exception:           # un Odoo que no contesta fields_get
        return None
    candidatos = [n for n, c in campos.items()
                  if c.get("type") == "many2one"
                  and c.get("relation") == "product.pricelist"
                  and (normal(c.get("string")) == "lista de implantados"
                       or n == settings.odoo_campo_implantados)]
    return sorted(candidatos)[0] if candidatos else None


def _leer_odoo(db: Session, odoo) -> dict:
    """Todo lo que la lectura necesita de Odoo, de una vez.

    Solo lo de Proteccion Ejecutiva (seccion 112): las listas que empiezan
    con el prefijo y los productos de su categoria. Las demas listas solo
    se cuentan --y se nombran si un cliente de PE trae una de ellas--; el
    producto que una lista de PE nombra y no es de la categoria se dice.
    Sin la categoria en Odoo, `SinCategoria`: no se lee nada."""
    todas = odoo.leer("product.pricelist", [["active", "=", True]],
                      CAMPOS_LISTA)
    listas = [l for l in todas if es_lista_de_pe(l.get("name"))]
    fuera = [{"id": l["id"], "nombre": texto(l.get("name"))}
             for l in todas if not es_lista_de_pe(l.get("name"))]
    filas_categoria = odoo.leer("product.category", [], CAMPOS_CATEGORIA)
    en_pe = categorias_de_pe(odoo, filas_categoria)
    ids = [l["id"] for l in listas]
    reglas_odoo = (odoo.leer("product.pricelist.item",
                             [["pricelist_id", "in", ids]], CAMPOS_REGLA)
                   if ids else [])
    referenciados = {reglas.id_de(r.get("product_tmpl_id"))
                     for r in reglas_odoo} - {None}
    variantes = {reglas.id_de(r.get("product_id")) for r in reglas_odoo} - {None}
    leidos = odoo.leer("product.template",
                       ["|", ["sale_ok", "=", True],
                        ["id", "in", sorted(referenciados)]]
                       if referenciados else [["sale_ok", "=", True]],
                       ["list_price", "categ_id", "name"], archivados=True)
    productos = [p for p in leidos if es_de_pe(p, en_pe)]
    productos_fuera = {p["id"]: texto(p.get("name")) for p in leidos
                       if p["id"] in referenciados and not es_de_pe(p, en_pe)}
    de_variante = {}
    if variantes:
        de_variante = {v["id"]: reglas.id_de(v.get("product_tmpl_id"))
                       for v in odoo.leer("product.product",
                                          [["id", "in", sorted(variantes)]],
                                          ["product_tmpl_id"], archivados=True)}
    categorias = {c["id"]: texto(c.get("parent_path")) for c in filas_categoria}
    monedas = odoo.leer("res.currency", [["active", "=", True]],
                        ["name", "rate"])
    grupos_ids = sorted({g for l in listas
                         for g in reglas.ids_de(l.get("country_group_ids"))})
    grupos = {}
    if grupos_ids:
        filas = odoo.leer("res.country.group", [["id", "in", grupos_ids]],
                          ["country_ids"])
        paises_ids = sorted({p for g in filas
                             for p in reglas.ids_de(g.get("country_ids"))})
        codigos = {p["id"]: texto(p.get("code")).upper() for p in odoo.leer(
            "res.country", [["id", "in", paises_ids]], ["code"])} if paises_ids else {}
        grupos = {g["id"]: {codigos[p] for p in reglas.ids_de(g.get("country_ids"))
                            if p in codigos} for g in filas}
    campo = campo_de_implantados(odoo)
    socios_ids = [c.odoo_id for c in db.query(m.Cliente)
                  .filter(m.Cliente.odoo_id.isnot(None)).all()]
    socios = (odoo.leer("res.partner", [["id", "in", socios_ids]],
                        ["property_product_pricelist"] + ([campo] if campo else []),
                        archivados=True) if socios_ids else [])
    return {"listas": listas, "reglas": reglas_odoo, "productos": productos,
            "referenciados": referenciados, "variantes": de_variante,
            "categorias": categorias, "monedas": monedas, "grupos": grupos,
            "campo_implantados": campo, "socios": socios,
            "fuera": fuera, "en_pe": en_pe, "productos_fuera": productos_fuera}


def tasas_de_centauro(db: Session, tasas: dict, empresa: str) -> dict:
    """Las tasas de Odoo, con el tipo de cambio de Centauro entre dolares y
    pesos en lugar del de Odoo (seccion 82): el que puso finanzas aplica
    para todo, tambien para pasar a dolares lo que la lista de Amazon toma
    de la General. Sin el, esa conversion no se hace y el precio sale sin
    tipo de cambio: no se inventa uno.

    Odoo dice cada tasa como cuantas unidades de esa moneda vale una de
    la empresa, y la de la empresa vale 1."""
    tasas = dict(tasas)
    tc = tipo_cambio.vigente(db, m.Moneda.USD, m.Moneda.MXN)
    if empresa == "USD":
        if tc:
            tasas["MXN"] = tc["tasa"]
        else:
            tasas.pop("MXN", None)
    elif tc and tasas.get("MXN"):
        tasas["USD"] = Decimal(str(tasas["MXN"])) / tc["tasa"]
    else:
        tasas.pop("USD", None)
    return tasas


def _plan(db: Session, datos: dict, hoy) -> dict:
    """Que tarifario sale de cada lista y que lista le toca a cada cliente,
    sin guardar nada."""
    empresa = next((texto(mo.get("name")) for mo in datos["monedas"]
                    if float(mo.get("rate") or 0) == 1.0), "MXN")
    tasas = tasas_de_centauro(db, {texto(mo.get("name")): mo.get("rate")
                                   for mo in datos["monedas"] if mo.get("rate")},
                              empresa)
    listas = {l["id"]: {"nombre": texto(l.get("name")),
                        "moneda": texto(nombre_de(l.get("currency_id"))).upper()[:3],
                        "grupos": reglas.ids_de(l.get("country_group_ids"))}
              for l in datos["listas"]}
    productos = {p["id"]: {"precio": p.get("list_price") or 0,
                           "categoria": reglas.id_de(p.get("categ_id"))}
                 for p in datos["productos"]}
    motor = reglas.Listas(listas, datos["reglas"], productos,
                          datos["categorias"], tasas, hoy, empresa=empresa,
                          variantes=datos["variantes"])

    # Lo confirmado que Odoo ya no vende y ninguna lista nombra no pone
    # precio en ningun lado: no se pregunta por el.
    confirmados = [{"id": p.id, "odoo_id": p.odoo_id, "nombre": p.nombre,
                    "vendible": p.vendible, "clase": p.clase,
                    "perfil_id": p.perfil_id, "categoria_id": p.categoria_id,
                    "modalidad": p.modalidad, "preferido": p.preferido}
                   for p in db.query(m.ProductoOdoo).filter_by(confirmado=True)
                   if p.odoo_id in productos]
    conocidos = {p.odoo_id: p for p in db.query(m.ProductoOdoo).all()}
    paises = {p.codigo.upper(): p.id for p in db.query(m.Pais).all()}
    nombres_pais = {p.id: p.nombre for p in db.query(m.Pais).all()}
    moneda_del_pais = {p.id: p.moneda_local for p in db.query(m.Pais).all()}

    # Los clientes de Centauro que vienen de Odoo, con la lista de su ficha.
    clientes = {c.odoo_id: c for c in db.query(m.Cliente)
                .filter(m.Cliente.odoo_id.isnot(None)).all()}
    campo = datos["campo_implantados"]
    lista_de, implantados_de, nombre_de_lista = {}, {}, {}
    for s in datos["socios"]:
        cliente = clientes.get(s["id"])
        if cliente is None:
            continue
        for clave, destino in (("property_product_pricelist", lista_de),
                               (campo, implantados_de)):
            if not clave:
                continue
            lista_id = reglas.id_de(s.get(clave))
            destino[cliente.id] = lista_id
            if lista_id:
                # Por si la lista ya no se lee --archivada--: su nombre.
                nombre_de_lista.setdefault(lista_id,
                                           nombre_de(s.get(clave)))
    # Solo los clientes activos cuentan como «de» una lista.
    activos = {c.id for c in clientes.values() if c.activo}
    clientes_por_lista, implantados_por_lista = {}, {}
    for origen, destino in ((lista_de, clientes_por_lista),
                            (implantados_de, implantados_por_lista)):
        for cliente_id, lista_id in origen.items():
            if lista_id and cliente_id in activos:
                destino.setdefault(lista_id, []).append(cliente_id)
    por_id = {c.id: c for c in clientes.values()}

    generales = {lid for lid, l in listas.items() if l["grupos"]}
    plan_listas, pendientes = [], []
    # Dos productos que dicen lo mismo chocan en cada lista que los hereda:
    # se dicen una vez, con las listas donde pasa.
    choques = {}
    otra_moneda = {}                     # lista de Odoo -> su moneda
    sin_confirmar = {}                   # productos de las listas por confirmar
    # Lo que una lista de PE nombra y no es de la categoria de PE: no se
    # lee, y se dice en que listas esta (seccion 112).
    fuera_de_categoria = {}
    for r in datos["reglas"]:
        odoo_id = reglas.id_de(r.get("product_tmpl_id"))
        if odoo_id in datos.get("productos_fuera", {}):
            fuera_de_categoria.setdefault(odoo_id, set()).add(
                listas.get(reglas.id_de(r.get("pricelist_id")), {}).get("nombre", ""))
            continue
        producto = conocidos.get(odoo_id)
        if odoo_id and (producto is None or not producto.confirmado):
            nombre = (producto.nombre if producto else
                      nombre_de(r.get("product_tmpl_id")) or f"#{odoo_id}")
            sin_confirmar[odoo_id] = nombre

    # Dos reglas para el mismo producto en la misma lista: gana la mas
    # nueva, como en Odoo, pero casi siempre es un descuido.
    vistas = {}
    for r in datos["reglas"]:
        if texto(r.get("applied_on")) not in ("0_product_variant", "1_product"):
            continue
        clave = (reglas.id_de(r.get("pricelist_id")),
                 reglas.id_de(r.get("product_tmpl_id")))
        vistas.setdefault(clave, []).append(r)
    for (lista_id, _), rs in vistas.items():
        if len(rs) > 1 and lista_id in listas:
            pendientes.append({
                "tipo": "reglas_repetidas", "lista": listas[lista_id]["nombre"],
                "producto": nombre_de(rs[0].get("product_tmpl_id")),
                "precios": [str(r.get("fixed_price") or 0) for r in rs]})

    for lista_id, lista in listas.items():
        moneda = MONEDAS.get(lista["moneda"])
        suyos = sorted(set(clientes_por_lista.get(lista_id, [])))
        de_implantados = sorted(set(implantados_por_lista.get(lista_id, [])))
        paises_de_clientes = {por_id[c].pais_id
                              for c in set(suyos) | set(de_implantados)}
        pais_id, de_grupos = reglas.pais_de_la_lista(
            lista, paises_de_clientes, paises, datos["grupos"])
        general = lista_id in generales
        if moneda is None:
            pendientes.append({"tipo": "moneda", "lista": lista["nombre"],
                               "moneda": lista["moneda"]})
            continue
        if pais_id is None:
            if general and len(de_grupos) > 1:
                pendientes.append({"tipo": "general_varios_paises",
                                   "lista": lista["nombre"],
                                   "paises": [nombres_pais[p] for p in de_grupos]})
            else:
                pendientes.append({"tipo": "sin_pais", "lista": lista["nombre"]})
            continue
        # Una lista en otra moneda que la de su pais --Amazon, en dolares--
        # se lee en su moneda: la cotizacion sale en dolares y guarda el
        # tipo de cambio que este puesto al autorizarse (seccion 82). Solo
        # la que Centauro no convierte --dolares en Brasil-- se dice y no
        # se lee; la utilidad y la comision restarian una moneda de otra.
        if not tipo_cambio.se_puede(moneda, moneda_del_pais.get(pais_id)):
            otra_moneda[lista_id] = moneda.value
            pendientes.append({"tipo": "otra_moneda", "lista": lista["nombre"],
                               "moneda": moneda.value,
                               "pais": nombres_pais.get(pais_id)})
            continue
        precios, conflictos, problemas = reglas.precios_de_la_lista(
            motor, lista_id, confirmados, generales)
        for c in conflictos:
            choque = choques.setdefault(
                tuple(sorted(n for n, _ in c["productos"])),
                {"tipo": "conflicto", "listas": [],
                 "productos": [[n, str(p)] for n, p in c["productos"]]})
            choque["listas"].append(lista["nombre"])
        for p in problemas:
            pendientes.append({"tipo": "regla", "lista": lista["nombre"],
                               "producto": p["producto"],
                               "problema": p["problema"]})
        resto, resto_id = motor.resto_de(lista_id)
        if not suyos and not de_implantados and not general:
            pendientes.append({"tipo": "lista_sin_cliente",
                               "lista": lista["nombre"], "precios": len(precios),
                               "propios": sum(1 for p in precios.values()
                                              if p["origen"] == reglas.PROPIO)})
        plan_listas.append({
            "odoo_id": lista_id, "nombre": lista["nombre"],
            "moneda": moneda, "pais_id": pais_id, "general": general,
            "resto_de": resto or None,
            "resto_general": resto_id in generales if resto_id else False,
            "precios": precios, "clientes": suyos,
            "implantados": de_implantados})

    pendientes.extend(choques.values())
    if not generales:
        pendientes.append({"tipo": "sin_general"})
    for odoo_id, nombre in sorted(sin_confirmar.items(), key=lambda x: x[1]):
        pendientes.append({"tipo": "producto_sin_confirmar", "producto": nombre})
    for odoo_id, en in sorted(fuera_de_categoria.items(),
                              key=lambda x: datos["productos_fuera"][x[0]]):
        pendientes.append({"tipo": "producto_fuera",
                           "producto": datos["productos_fuera"][odoo_id],
                           "listas": sorted(x for x in en if x),
                           "categoria": settings.odoo_categoria_productos})
    return {"listas": plan_listas, "lista_de": lista_de,
            "implantados_de": implantados_de, "clientes": por_id,
            "pendientes": pendientes, "campo_implantados": campo,
            "nombres_pais": nombres_pais, "nombre_de_lista": nombre_de_lista,
            "otra_moneda": otra_moneda, "leidas": len(listas)}


def _modalidades(db: Session) -> dict:
    return {(mo.pais_id, mo.codigo.value): mo
            for mo in db.query(m.Modalidad).all()}


def _filas_de(precios: dict, pais_id: int, modalidades: dict) -> tuple:
    """(recurso, vehiculo, paquete, hora extra, faltan) de una lista: lo
    que va en las tablas del tarifario. La modalidad es la del pais."""
    recurso, vehiculo, paquete, faltan = [], [], [], set()
    extra_general = precios.get((reglas.HORA_EXTRA, None, None, None))
    extras = {k[1]: v for k, v in precios.items() if k[0] == reglas.HORA_EXTRA}
    for (clase, perfil, categoria, codigo), p in precios.items():
        if clase == reglas.HORA_EXTRA:
            continue
        modalidad = modalidades.get((pais_id, codigo))
        if modalidad is None:
            faltan.add(codigo)
            continue
        fila = {"modalidad_id": modalidad.id, "precio": p["precio"],
                "origen": p["origen"], "producto_odoo_id": p["producto_id"]}
        if clase == reglas.ROL:
            extra = extras.get(perfil) or extra_general
            lleva = bool(extra) and modalidad.aplica_horas_extra
            recurso.append({**fila, "perfil_id": perfil,
                            "precio_hora_extra": extra["precio"] if lleva else None,
                            # Con que producto sale en la factura (seccion 116).
                            "producto_hora_extra_id": (extra["producto_id"]
                                                       if lleva else None)})
        elif clase == reglas.UNIDAD:
            vehiculo.append({**fila, "categoria_id": categoria})
        else:
            paquete.append({**fila, "perfil_id": perfil,
                            "categoria_id": categoria})
    return recurso, vehiculo, paquete, extra_general, sorted(faltan)


def sincronizar(db: Session, odoo, ensayo: bool = True,
                quien: m.Usuario | None = None,
                automatica: bool = False) -> dict:
    """Lee las listas de precios de Odoo y, si no es ensayo, las guarda."""
    if not ensayo:
        odoo_api.candado(db, TIPO)
    ahora = _utc()
    try:
        datos = _leer_odoo(db, odoo)
    except SinCategoria as error:
        # Sin la categoria no se sabe que es de Proteccion Ejecutiva: no
        # se toca nada. Leer todo seria volver a traer el GPS (seccion 112).
        return {"ensayo": ensayo, "sin_categoria": str(error), "leidas": 0,
                "fuera": 0, "prefijo": settings.odoo_prefijo_listas,
                "categoria": settings.odoo_categoria_productos,
                "generales": [], "por_cliente": [], "sin_cliente": [],
                "precios": 0, "clientes": 0, "clientes_con_general": 0,
                "cambian": [], "implantados": 0, "campo_implantados": None,
                "pendientes": []}
    if not ensayo:
        # Los productos nuevos llegan con su sugerencia antes del plan:
        # asi finanzas los ve en la tabla aunque todavia no pongan precio.
        leer_productos(db, odoo, datos["referenciados"], ahora,
                       en_pe=datos["en_pe"])
    plan = _plan(db, datos, ahora.date())
    # Lo que la factura no sabria con que producto cobrar (seccion 116):
    # el que pone un precio --o el de los gastos-- y en Odoo tiene varias
    # variantes.
    for p in (db.query(m.ProductoOdoo)
              .filter(m.ProductoOdoo.vendible.is_(True),
                      m.ProductoOdoo.variantes > 1)
              .order_by(m.ProductoOdoo.nombre)):
        if ((p.confirmado and p.clase in reglas.CON_PRECIO)
                or es_el_de_gastos(p.nombre)):
            plan["pendientes"].append({"tipo": "producto_variantes",
                                       "producto": p.nombre,
                                       "variantes": p.variantes})
    modalidades = _modalidades(db)
    existentes = {t.odoo_id: t for t in db.query(m.Tarifario)
                  .filter(m.Tarifario.odoo_id.isnot(None)).all()}

    listas_informe, con_precios = [], set()
    for pl in plan["listas"]:
        recurso, vehiculo, paquete, extra, faltan = _filas_de(
            pl["precios"], pl["pais_id"], modalidades)
        for codigo in faltan:
            plan["pendientes"].append({"tipo": "modalidad", "lista": pl["nombre"],
                                       "modalidad": codigo})
        total = len(recurso) + len(vehiculo) + len(paquete) + (1 if extra else 0)
        if total:
            con_precios.add(pl["odoo_id"])
        pl.update(recurso=recurso, vehiculo=vehiculo, paquete=paquete,
                  extra=extra, total=total)
        listas_informe.append({
            "odoo_id": pl["odoo_id"], "nombre": pl["nombre"],
            "moneda": pl["moneda"].value, "general": pl["general"],
            "pais": plan["nombres_pais"].get(pl["pais_id"]),
            "resto_de": pl["resto_de"], "precios": total,
            "propios": sum(1 for p in pl["precios"].values()
                           if p["origen"] == reglas.PROPIO),
            "clientes": [plan["clientes"][c].nombre for c in pl["clientes"]],
            "implantados": [plan["clientes"][c].nombre
                            for c in pl["implantados"]],
            "nueva": pl["odoo_id"] not in existentes})

    # A que tarifario cambia cada cliente. A una lista sin precios que
    # Centauro sepa leer no se le cambia: se queda como estaba y se dice.
    cambios, retenidos = [], []
    # Las listas que no son de PE no se leen (seccion 112). El cliente que
    # trae una se queda con el tarifario que tenia --aunque sea el de esa
    # misma lista: sus precios ya no se ponen al dia-- y se dice.
    no_pe = {l["id"]: l["nombre"] for l in datos["fuera"]}
    for cliente_id, lista_id in sorted(plan["lista_de"].items()):
        cliente = plan["clientes"][cliente_id]
        actual = cliente.tarifario.odoo_id if cliente.tarifario else None
        if lista_id in no_pe:
            retenidos.append({"tipo": "lista_no_pe", "cliente": cliente.nombre,
                              "lista": no_pe[lista_id],
                              "prefijo": settings.odoo_prefijo_listas})
            continue
        if lista_id is None or lista_id == actual:
            continue
        nombre = next((l["nombre"] for l in plan["listas"]
                       if l["odoo_id"] == lista_id),
                      plan["nombre_de_lista"].get(lista_id))
        if lista_id in plan["otra_moneda"]:
            retenidos.append({"tipo": "lista_otra_moneda", "cliente": cliente.nombre,
                              "lista": nombre, "moneda": plan["otra_moneda"][lista_id]})
            continue
        if lista_id not in con_precios:
            retenidos.append({"tipo": "lista_sin_precios", "cliente": cliente.nombre,
                              "lista": nombre})
            continue
        cambios.append({"cliente_id": cliente_id, "cliente": cliente.nombre,
                        "lista_id": lista_id, "lista": nombre,
                        "antes": cliente.tarifario.nombre if cliente.tarifario else None})
    plan["pendientes"].extend(retenidos)
    # La de los implantados, igual: a una lista que no se leyo --en otra
    # moneda, sin pais-- no se le cambia.
    leidas = {pl["odoo_id"] for pl in plan["listas"]}
    implantados = []
    for cliente_id, lista_id in sorted(plan["implantados_de"].items()):
        cliente = plan["clientes"][cliente_id]
        actual = (cliente.tarifario_implantado.odoo_id
                  if cliente.tarifario_implantado else None)
        if lista_id in no_pe:
            plan["pendientes"].append({
                "tipo": "lista_no_pe", "cliente": cliente.nombre,
                "lista": no_pe[lista_id], "implantados": True,
                "prefijo": settings.odoo_prefijo_listas})
            continue
        if lista_id != actual and (lista_id is None or lista_id in leidas):
            implantados.append({"cliente_id": cliente_id, "cliente": cliente.nombre,
                                "lista_id": lista_id})

    generales = [l for l in listas_informe if l["general"]]
    informe = {
        "ensayo": ensayo,
        "leidas": plan["leidas"],
        # Las listas activas de Odoo que no son de PE: solo se cuentan.
        "fuera": len(datos["fuera"]),
        "prefijo": settings.odoo_prefijo_listas,
        "categoria": settings.odoo_categoria_productos,
        "generales": generales,
        "por_cliente": [l for l in listas_informe if not l["general"]
                        and (l["clientes"] or l["implantados"])],
        "sin_cliente": [l for l in listas_informe if not l["general"]
                        and not l["clientes"] and not l["implantados"]],
        "precios": sum(l["precios"] for l in listas_informe),
        "clientes": len(plan["lista_de"]),
        "clientes_con_general": sum(
            1 for c, l in plan["lista_de"].items()
            if any(g["odoo_id"] == l for g in generales)),
        "cambian": [{k: c[k] for k in ("cliente", "lista", "antes")}
                    for c in cambios],
        "implantados": len([i for i in implantados if i["lista_id"]]),
        "campo_implantados": plan["campo_implantados"],
        "pendientes": plan["pendientes"],
    }
    if ensayo:
        return informe

    # ------------------------------------------------------------ aplicar
    for pl in plan["listas"]:
        t = existentes.get(pl["odoo_id"])
        if t is None:
            t = m.Tarifario(odoo_id=pl["odoo_id"], vigencia_desde=ahora.date())
            db.add(t)
            existentes[pl["odoo_id"]] = t
        t.nombre = pl["nombre"][:120]
        t.pais_id = pl["pais_id"]
        t.moneda = pl["moneda"]
        t.activo = True
        t.general = pl["general"]
        t.resto_de = pl["resto_de"]
        t.precio_hora_extra = pl["extra"]["precio"] if pl["extra"] else None
        t.producto_hora_extra_id = (pl["extra"]["producto_id"] if pl["extra"]
                                    else None)
        t.odoo_sincronizado_en = ahora
        db.flush()
        # Lo de Odoo se reemplaza entero: una lista es lo que dice hoy.
        for modelo in (m.TarifaRecurso, m.TarifaVehiculo, m.TarifaPaquete):
            db.query(modelo).filter_by(tarifario_id=t.id).delete()
        for f in pl["recurso"]:
            db.add(m.TarifaRecurso(tarifario_id=t.id, **f))
        for f in pl["vehiculo"]:
            db.add(m.TarifaVehiculo(tarifario_id=t.id, **f))
        for f in pl["paquete"]:
            db.add(m.TarifaPaquete(tarifario_id=t.id, **f))
    # Las que Odoo ya no trae --archivadas o borradas-- dejan de ofrecerse.
    leidas = {pl["odoo_id"] for pl in plan["listas"]}
    for odoo_id, t in existentes.items():
        if odoo_id not in leidas and t.activo:
            t.activo = False
    db.flush()
    for c in cambios:
        db.get(m.Cliente, c["cliente_id"]).tarifario_id = existentes[c["lista_id"]].id
    for i in implantados:
        destino = existentes.get(i["lista_id"]) if i["lista_id"] else None
        db.get(m.Cliente, i["cliente_id"]).tarifario_implantado_id = (
            destino.id if destino else None)

    hubo_algo = bool(cambios or implantados or any(l["nueva"] for l in listas_informe))
    fila = m.SincronizacionOdoo(
        tipo=TIPO, automatica=automatica,
        hecha_por_id=quien.persona_id if quien else None,
        leidos=plan["leidas"],
        altas=sum(1 for l in listas_informe if l["nueva"]),
        cambios=len(cambios) + len(implantados), bajas=0,
        pendientes=len(plan["pendientes"]),
        detalle=(json.dumps(informe, ensure_ascii=False, default=str)
                 if hubo_algo or not automatica else None))
    db.add(fila)
    db.flush()
    if quien is not None:
        accesos.anotar(db, quien, "tarifarios leidos de odoo",
                       "sincronizacion_odoo", fila.id,
                       despues=(f"{plan['leidas']} listas, "
                                f"{informe['precios']} precios, "
                                f"{len(cambios)} clientes cambian"))
    db.commit()
    return informe


def resumen(informe: dict) -> dict:
    return {"leidas": informe["leidas"], "precios": informe["precios"],
            "cambian": len(informe["cambian"]),
            "pendientes": len(informe["pendientes"])}


def sincronizar_si_toca(db: Session, odoo=None) -> dict:
    """La tarea de cada hora. No arranca sola: espera a que alguien haya
    hecho la primera lectura a mano, despues de ver el ensayo."""
    from app import odoo_api

    if not en_marcha(db):
        return {"omitido": "falta la primera lectura a mano"}
    if odoo is None:
        if not odoo_api.hay_conexion():
            return {"omitido": "Odoo no esta conectado"}
        odoo = odoo_api.cliente()
    try:
        return resumen(sincronizar(db, odoo, ensayo=False, automatica=True))
    except odoo_api.NoResponde as error:
        db.rollback()
        registro.warning("odoo no respondio al leer los tarifarios: %s", error)
        return {"error": str(error)}

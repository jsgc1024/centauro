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

Cada pais lee lo suyo (seccion 123, pedido de Salvador del 2 de octubre):
Mexico, la categoria «Proteccion Ejecutiva» y las listas «PE ·», en
espanol de Mexico; Brasil, «Protecao Executiva Brasil» y las listas
«Brasil ·», en portugues. La lista es del pais de su grupo de paises, de
su compania o de su nombre, y sus precios salen de los productos de su
pais. La lista de la ficha de un cliente se lee desde la compania de su
pais --desde la de Mexico, Odoo le ponia a un cliente de Brasil una lista
de Mexico-- y una lista de otro pais nunca se le pone. El que en Odoo se
cobra por «Mes» es del mes, y la hora extra de un rol que solo va en
paquete se guarda con el paquete.

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
# La compania de cada lista (seccion 123): la de Amazon Brasil no trae
# grupo de paises, y es de la de Brasil.
CAMPOS_LISTA = ["name", "currency_id", "country_group_ids", "active",
                "company_id"]
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


def lecturas() -> list[dict]:
    """Lo que se lee de cada pais (seccion 123): su categoria de productos,
    el prefijo de sus listas, el idioma de sus nombres y su compania de
    Odoo. La de Mexico es la de la seccion 112; vacia, se lee todo, como
    antes. La de Brasil, vacia, no se lee."""
    return [
        {"pais": "MX", "compania": odoo_api.COMPANIAS["MX"],
         "categoria": (settings.odoo_categoria_productos or "").strip(),
         "prefijo": (settings.odoo_prefijo_listas or "").strip(),
         "idioma": settings.odoo_idioma or "es_MX"},
        {"pais": "BR", "compania": odoo_api.COMPANIAS["BR"],
         "categoria": (settings.odoo_categoria_productos_br or "").strip(),
         "prefijo": (settings.odoo_prefijo_listas_br or "").strip(),
         "idioma": settings.odoo_idioma_br or "pt_BR"},
    ]


def categorias_por_pais(filas: list) -> dict:
    """{pais: categorias} de los paises cuya categoria esta en Odoo: la que
    se llama asi y todas las que cuelgan de ella. Sin la de Mexico
    configurada no hay ninguno: se lee todo, como antes.

    Cada categoria es de un solo pais: si la de Brasil cuelga de la de
    Mexico, lo de abajo es de Brasil --manda la raiz mas cercana--."""
    lee = lecturas()
    if not lee[0]["categoria"]:
        return {}
    raices = {}
    for x in lee:
        if not x["categoria"]:
            continue
        buscada = normal(x["categoria"])
        for c in filas:
            if buscada in (normal(c.get("name")), normal(c.get("complete_name"))):
                raices.setdefault(c["id"], x["pais"])
    salida = {}
    for c in filas:
        # «1/5/9/»: de la raiz a ella misma.
        camino = [int(x) for x in texto(c.get("parent_path")).split("/")
                  if x.isdigit()]
        if c["id"] not in camino:
            camino.append(c["id"])
        pais = next((raices[i] for i in reversed(camino) if i in raices), None)
        if pais:
            salida.setdefault(pais, set()).add(c["id"])
    return salida


def categorias_de_pe(odoo, filas: list | None = None) -> set | None:
    """Los ids de las categorias de productos de Proteccion Ejecutiva: la
    de `odoo_categoria_productos` --la de Mexico-- y la de Brasil (seccion
    123), con todas las que cuelgan de ellas. None: la configuracion no
    pide filtro y se lee todo, como antes de la seccion 112. Si la de
    Mexico no esta en Odoo, `SinCategoria`; la de Brasil que falta solo
    deja a Brasil sin productos."""
    nombre = (settings.odoo_categoria_productos or "").strip()
    if not nombre:
        return None
    if filas is None:
        filas = odoo.leer("product.category", [], CAMPOS_CATEGORIA)
    por_pais = categorias_por_pais(filas)
    if "MX" not in por_pais:
        raise SinCategoria(nombre)
    return set().union(*por_pais.values())


def es_de_pe(producto: dict, en_pe: set | None) -> bool:
    """Si un producto de Odoo es de Proteccion Ejecutiva, por su categoria."""
    return en_pe is None or reglas.id_de(producto.get("categ_id")) in en_pe


def pais_del_producto(producto: dict, por_pais: dict) -> str | None:
    """De que pais es un producto, por su categoria (seccion 123)."""
    categoria = reglas.id_de(producto.get("categ_id"))
    return next((p for p, rama in por_pais.items() if categoria in rama), None)


# Los puntos que se confunden con el «·» del prefijo: el que se teclea
# en el telefono o se copia de otro lado tambien vale.
PUNTOS = str.maketrans({c: "·" for c in "•∙‧⋅・"})


def _para_prefijo(texto_) -> str:
    return " ".join(normal(texto_).translate(PUNTOS).replace("·", " · ").split())


def pais_por_prefijo(nombre) -> str | None:
    """El pais cuyo prefijo trae el nombre de la lista (seccion 123):
    «Brasil · Amazon Implantados (USD)» es de Brasil."""
    for x in lecturas():
        prefijo = _para_prefijo(x["prefijo"])
        if prefijo and _para_prefijo(nombre).startswith(prefijo):
            return x["pais"]
    return None


def es_lista_de_pe(nombre) -> bool:
    """Si una lista de precios es de Proteccion Ejecutiva, por como empieza
    su nombre (seccion 112): «PE · General México» y, de Brasil (seccion
    123), «Brasil · Amazon Implantados (USD)». Sin mayusculas, acentos ni
    espacios de sobra, y con cualquier punto medio. Sin el prefijo de
    Mexico en la configuracion, todas."""
    if not _para_prefijo(settings.odoo_prefijo_listas):
        return True
    return pais_por_prefijo(nombre) is not None


def prefijos() -> list[str]:
    """Los prefijos que se leen, para decirlos."""
    return [x["prefijo"] for x in lecturas() if x["prefijo"]]


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
                   en_pe=POR_LEER, por_pais=POR_LEER) -> dict:
    """Trae de Odoo los productos que se venden --y los que nombra alguna
    lista aunque ya no se vendan-- y los deja en la tabla de productos.

    Solo los de Proteccion Ejecutiva (seccion 112): los de su categoria.
    Lo que ya estaba en la tabla y no es de ahi --el GPS, la Central de
    Inteligencia-- sale de la tabla, salvo que algun tarifario lo nombre.

    Lo nuevo llega con su sugerencia. Lo que finanzas ya confirmo no se
    vuelve a sugerir: solo se le pone al dia el nombre, la unidad y el
    «Precio de venta». Lo de PE que Odoo ya no trae se queda, marcado como
    que ya no se vende. No hace commit: lo hace quien llama. `en_pe`: las
    categorias de PE, si quien llama ya las tiene; `por_pais`, las de cada
    pais.

    Cada producto es del pais de su categoria (seccion 123), y su nombre
    se lee en el idioma de ese pais: los de Brasil, en portugues.
    """
    ahora = ahora or _utc()
    if en_pe is POR_LEER or por_pais is POR_LEER:
        if (settings.odoo_categoria_productos or "").strip():
            filas_categoria = odoo.leer("product.category", [], CAMPOS_CATEGORIA)
            if en_pe is POR_LEER:
                en_pe = categorias_de_pe(odoo, filas_categoria)
            if por_pais is POR_LEER:
                por_pais = categorias_por_pais(filas_categoria)
        else:
            en_pe = None if en_pe is POR_LEER else en_pe
            por_pais = {} if por_pais is POR_LEER else por_pais
    dominio = [["sale_ok", "=", True]]
    if referenciados:
        dominio = ["|", ["sale_ok", "=", True],
                   ["id", "in", sorted(referenciados)]]
    # El de los gastos entra aunque no sea de la categoria de PE: con el
    # se facturan los gastos del eventual (seccion 116).
    filas = [f for f in odoo.leer("product.template", dominio, CAMPOS_PRODUCTO,
                                  archivados=True)
             if es_de_pe(f, en_pe) or es_el_de_gastos(f)]
    de_cada = {f["id"]: pais_del_producto(f, por_pais or {}) for f in filas}
    _en_su_idioma(odoo, filas, de_cada)
    paises = {x.codigo.upper(): x.id for x in db.query(m.Pais).all()}
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
        producto.pais_id = paises.get(de_cada.get(f["id"]))
        if not producto.confirmado:
            s = reglas.sugerir(f, perfiles, categorias)
            producto.clase = s["clase"]
            producto.perfil_id = s["perfil_id"]
            producto.categoria_id = s["categoria_id"]
            producto.modalidad = s["modalidad"]
            sugeridos += 1 if s["clase"] else 0
    # Los productos de un pais cuya categoria esta configurada y Odoo no
    # trae en esta lectura se quedan como estaban (seccion 127, hallazgo
    # r5-01): si alguien renombra «Proteção Executiva Brasil», los de
    # Brasil no se ponen en gris ni se borran con lo que finanzas
    # confirmo; la lectura lo dice en pendientes.
    paises_sin_categoria = {paises.get(x["pais"]) for x in lecturas()
                            if x["categoria"] and x["pais"] not in (por_pais or {})
                            and en_pe is not None}
    faltan = [p for odoo_id, p in existentes.items() if odoo_id not in vistos
              and (p.pais_id is None or p.pais_id not in paises_sin_categoria)]
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


def _en_su_idioma(odoo, filas: list, de_cada: dict) -> None:
    """Los nombres de cada pais en su idioma (seccion 123): los de Brasil,
    en portugues. Se leen aparte y se ponen en las mismas filas."""
    base = settings.odoo_idioma or "es_MX"
    for x in lecturas():
        ids = sorted(i for i, codigo in de_cada.items() if codigo == x["pais"])
        if not ids or not x["idioma"] or x["idioma"] == base:
            continue
        nombres = {f["id"]: texto(f.get("name")) for f in odoo.leer(
            "product.template", [["id", "in", ids]], ["name"], archivados=True,
            idioma=x["idioma"])}
        for f in filas:
            if nombres.get(f["id"]):
                f["name"] = nombres[f["id"]]


def tabla_de_productos(db: Session) -> list[dict]:
    paises = {x.id: x for x in db.query(m.Pais).all()}
    return [{"id": p.id, "odoo_id": p.odoo_id, "nombre": p.nombre,
             # De que pais es, por su categoria en Odoo (seccion 123).
             "pais": paises[p.pais_id].codigo.upper() if p.pais_id in paises else None,
             "pais_nombre": paises[p.pais_id].nombre if p.pais_id in paises else None,
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
    Sin la categoria en Odoo, `SinCategoria`: no se lee nada.

    Cada pais con lo suyo (seccion 123): las categorias de cada pais, el
    pais de cada producto y la lista de la ficha de cada cliente leida
    desde la compania de su pais."""
    todas = odoo.leer("product.pricelist", [["active", "=", True]],
                      CAMPOS_LISTA)
    listas = [l for l in todas if es_lista_de_pe(l.get("name"))]
    fuera = [{"id": l["id"], "nombre": texto(l.get("name"))}
             for l in todas if not es_lista_de_pe(l.get("name"))]
    filas_categoria = odoo.leer("product.category", [], CAMPOS_CATEGORIA)
    en_pe = categorias_de_pe(odoo, filas_categoria)
    por_pais = categorias_por_pais(filas_categoria) if en_pe is not None else {}
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
                       ["list_price", "categ_id", "name", "currency_id"],
                       archivados=True)
    productos = [p for p in leidos if es_de_pe(p, en_pe)]
    pais_de_producto = {p["id"]: pais_del_producto(p, por_pais) for p in productos}
    productos_fuera = {p["id"]: texto(p.get("name")) for p in leidos
                       if p["id"] in referenciados and not es_de_pe(p, en_pe)}
    de_variante = {}
    if variantes:
        de_variante = {v["id"]: reglas.id_de(v.get("product_tmpl_id"))
                       for v in odoo.leer("product.product",
                                          [["id", "in", sorted(variantes)]],
                                          ["product_tmpl_id"], archivados=True)}
    categorias = {c["id"]: texto(c.get("parent_path")) for c in filas_categoria}
    # Las tasas, vistas desde la compania de Mexico (seccion 123): desde
    # la de Brasil todas valen 1, porque alla no tienen tipo de cambio.
    monedas = odoo.leer("res.currency", [["active", "=", True]],
                        ["name", "rate"], compania=odoo_api.COMPANIAS["MX"])
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
    # La lista de la ficha es de cada compania (seccion 123): la de un
    # cliente de Brasil se lee desde la de Brasil. Desde la de Mexico,
    # Odoo le ponia la primera lista de Mexico sin grupo de paises.
    codigos = {x.id: x.codigo.upper() for x in db.query(m.Pais).all()}
    por_compania = {}
    for c in (db.query(m.Cliente).filter(m.Cliente.odoo_id.isnot(None))
              .order_by(m.Cliente.id).all()):
        por_compania.setdefault(odoo_api.COMPANIAS.get(codigos.get(c.pais_id)),
                                []).append(c.odoo_id)
    socios = []
    for compania, socios_ids in por_compania.items():
        socios += odoo.leer("res.partner", [["id", "in", socios_ids]],
                            ["property_product_pricelist"] + ([campo] if campo else []),
                            archivados=True, compania=compania)
    # El nombre de la compania de cada pais, para decir de donde lee cada
    # uno (seccion 123). Si no se puede leer, no se dice.
    try:
        companias = {c["id"]: texto(c.get("name")) for c in odoo.leer(
            "res.company", [["id", "in", sorted(odoo_api.COMPANIAS.values())]],
            ["name"])}
    except odoo_api.NoResponde:
        companias = {}
    return {"listas": listas, "reglas": reglas_odoo, "productos": productos,
            "referenciados": referenciados, "variantes": de_variante,
            "categorias": categorias, "monedas": monedas, "grupos": grupos,
            "campo_implantados": campo, "socios": socios,
            "fuera": fuera, "en_pe": en_pe, "productos_fuera": productos_fuera,
            "categorias_pais": por_pais, "pais_de_producto": pais_de_producto,
            "companias": companias}


# Las monedas que convierte el tipo de cambio de Centauro: con ellas nunca
# se usa el de Odoo.
DE_CENTAURO = ("USD", "MXN", "BRL")


def tasas_de_centauro(db: Session, tasas: dict) -> dict:
    """Las tasas con que la lectura convierte, del tipo de cambio de
    Centauro: el dolar a peso (seccion 82) y el dolar a real (seccion 123)
    que pone finanzas aplican para todo, tambien para pasar a dolares lo
    que la lista de Amazon toma de la General. El de Odoo no se usa para
    esas monedas --en la compania de Mexico el real vale 1: nadie le puso
    el suyo--. Sin el de Centauro, esa conversion no se hace y el precio
    sale sin tipo de cambio: no se inventa uno.

    Cada tasa dice cuantas unidades de esa moneda vale un dolar: al
    convertir solo cuenta el cociente entre dos, y asi el dolar a real
    sirve aunque falte el dolar a peso. Las demas monedas, con lo que
    dice Odoo (`tasas`: cuantas de cada una vale una de la empresa), si
    Odoo dice cuanto vale el dolar."""
    tc = tipo_cambio.vigente(db, m.Moneda.USD, m.Moneda.MXN)
    tc_real = tipo_cambio.vigente(db, m.Moneda.USD, m.Moneda.BRL)
    salida = {"USD": Decimal("1")}
    if tc:
        salida["MXN"] = tc["tasa"]
    if tc_real:
        salida["BRL"] = tc_real["tasa"]
    dolar = tasas.get("USD")
    if dolar:
        for moneda, tasa in tasas.items():
            if moneda not in DE_CENTAURO and tasa:
                salida[moneda] = Decimal(str(tasa)) / Decimal(str(dolar))
    return salida


def _plan(db: Session, datos: dict, hoy) -> dict:
    """Que tarifario sale de cada lista y que lista le toca a cada cliente,
    sin guardar nada."""
    # La moneda de la empresa es la que vale 1. El peso, si vale 1: en Odoo
    # el real tambien vale 1 mientras nadie le ponga tipo de cambio.
    unos = [texto(mo.get("name")) for mo in datos["monedas"]
            if float(mo.get("rate") or 0) == 1.0]
    empresa = "MXN" if "MXN" in unos else (unos[0] if unos else "MXN")
    tasas = tasas_de_centauro(db, {texto(mo.get("name")): mo.get("rate")
                                   for mo in datos["monedas"] if mo.get("rate")})
    # De que pais dice cada compania de Odoo (seccion 123).
    pais_de_compania = {v: k for k, v in odoo_api.COMPANIAS.items()}
    listas = {l["id"]: {"nombre": texto(l.get("name")),
                        "moneda": texto(nombre_de(l.get("currency_id"))).upper()[:3],
                        "grupos": reglas.ids_de(l.get("country_group_ids")),
                        # Lo que dicen su compania y su nombre (seccion 123):
                        # la de Amazon Brasil no trae grupo de paises.
                        "por_compania": pais_de_compania.get(
                            reglas.id_de(l.get("company_id"))),
                        "compania": nombre_de(l.get("company_id")) or None,
                        "por_nombre": pais_por_prefijo(l.get("name"))}
              for l in datos["listas"]}
    # El «Precio de venta» va en la moneda del producto (seccion 123): los
    # de Brasil, en reales. Sin decirla, la de la empresa.
    productos = {p["id"]: {"precio": p.get("list_price") or 0,
                           "categoria": reglas.id_de(p.get("categ_id")),
                           "moneda": (texto(nombre_de(p.get("currency_id")))
                                      .upper()[:3] or None)}
                 for p in datos["productos"]}
    motor = reglas.Listas(listas, datos["reglas"], productos,
                          datos["categorias"], tasas, hoy, empresa=empresa,
                          variantes=datos["variantes"])

    # Lo confirmado que Odoo ya no vende y ninguna lista nombra no pone
    # precio en ningun lado: no se pregunta por el.
    # Cada uno con el pais de su categoria (seccion 123): una lista solo
    # pone precio con los productos de su pais, si su pais tiene categoria.
    pais_de_producto = datos.get("pais_de_producto") or {}
    confirmados = [{"id": p.id, "odoo_id": p.odoo_id, "nombre": p.nombre,
                    "vendible": p.vendible, "clase": p.clase,
                    "perfil_id": p.perfil_id, "categoria_id": p.categoria_id,
                    "modalidad": p.modalidad, "preferido": p.preferido,
                    "pais": pais_de_producto.get(p.odoo_id)}
                   for p in db.query(m.ProductoOdoo).filter_by(confirmado=True)
                   if p.odoo_id in productos]
    con_categoria = set(datos.get("categorias_pais") or {})
    # Los paises con categoria configurada que Odoo no trae (seccion 127).
    sin_categoria_pais = {x["pais"] for x in lecturas()
                          if x["categoria"] and x["pais"] not in con_categoria}
    intactas = set()
    conocidos = {p.odoo_id: p for p in db.query(m.ProductoOdoo).all()}
    paises = {p.codigo.upper(): p.id for p in db.query(m.Pais).all()}
    codigo_de_pais = {v: k for k, v in paises.items()}
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
    plan_listas, pendientes, de_otro_pais = [], [], []
    # Dos productos que dicen lo mismo chocan en cada lista que los hereda:
    # se dicen una vez, con las listas donde pasa.
    choques = {}
    otra_moneda = {}                     # lista de Odoo -> su moneda
    sin_confirmar = {}                   # productos de las listas por confirmar
    # Lo que una lista de PE nombra y no es de la categoria de PE: no se
    # lee, y se dice en que listas esta (seccion 112) y en que categoria
    # tendria que estar: la del pais de esas listas (seccion 123).
    fuera_de_categoria, fuera_de_paises = {}, {}
    # Lo que nombra cada lista, para ver si es de su pais (seccion 123).
    nombrados, nombre_producto = {}, {}
    for r in datos["reglas"]:
        odoo_id = reglas.id_de(r.get("product_tmpl_id"))
        de_lista = listas.get(reglas.id_de(r.get("pricelist_id")), {})
        plantilla = odoo_id or datos["variantes"].get(reglas.id_de(r.get("product_id")))
        if plantilla:
            nombrados.setdefault(reglas.id_de(r.get("pricelist_id")), set()).add(plantilla)
            nombre_producto.setdefault(plantilla, nombre_de(r.get("product_tmpl_id"))
                                       or nombre_de(r.get("product_id")))
        if odoo_id in datos.get("productos_fuera", {}):
            fuera_de_categoria.setdefault(odoo_id, set()).add(
                de_lista.get("nombre", ""))
            fuera_de_paises.setdefault(odoo_id, set()).add(
                de_lista.get("por_nombre") or "MX")
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
            lista, paises_de_clientes, paises, datos["grupos"],
            compania=lista["por_compania"], prefijo=lista["por_nombre"])
        general = lista_id in generales
        # Su compania tiene que cuadrar con su pais y con su nombre
        # (seccion 123): «Brasil · ...» en la compania de Mexico no se lee,
        # porque no se sabe de cual es. Sin compania, como antes.
        de_compania = paises.get(lista["por_compania"])
        de_nombre = paises.get(lista["por_nombre"])
        if pais_id is not None and de_compania is not None and (
                pais_id != de_compania
                or (de_nombre is not None and de_nombre != de_compania)):
            # El pais que dice su grupo o su nombre, el que no es el de su
            # compania.
            otro = pais_id if pais_id != de_compania else de_nombre
            pendientes.append({"tipo": "lista_no_cuadra", "lista": lista["nombre"],
                               "pais": nombres_pais.get(otro),
                               "compania": lista["compania"]})
            continue
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
        codigo = codigo_de_pais.get(pais_id)
        # El pais cuya categoria no esta en Odoo no lee sus listas
        # (seccion 127, hallazgo r5-01): se quedan como estaban y se
        # dice. Antes, sin la de Brasil, sus listas tomaban todos los
        # confirmados --los de Mexico-- con su «Precio de venta»
        # convertido a reales. Sin ninguna categoria configurada se lee
        # todo, como antes de la 112.
        if con_categoria and codigo in sin_categoria_pais:
            intactas.add(lista_id)
            continue
        suyos_productos = [x for x in confirmados
                           if not x["pais"] or x["pais"] == codigo
                           or not con_categoria]
        # Lo que la lista nombra y es de otro pais no pone precio en ella
        # (seccion 123): se dice.
        if codigo in con_categoria:
            for odoo_id in sorted(nombrados.get(lista_id, ())):
                suyo = pais_de_producto.get(odoo_id)
                if suyo and suyo != codigo:
                    de_otro_pais.append({
                        "tipo": "producto_de_otro_pais", "lista": lista["nombre"],
                        "producto": (conocidos[odoo_id].nombre if odoo_id in conocidos
                                     else nombre_producto.get(odoo_id)) or f"#{odoo_id}",
                        "pais": nombres_pais.get(paises.get(suyo)),
                        "pais_lista": nombres_pais.get(pais_id)})
        precios, conflictos, problemas = reglas.precios_de_la_lista(
            motor, lista_id, suyos_productos, generales)
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
    # La general de cada pais (seccion 123): el pais con listas o con
    # clientes de Odoo y sin general lo dice. Su cliente sin lista nunca
    # se cotiza con la de otro pais.
    con_general = {pl["pais_id"] for pl in plan_listas if pl["general"]}
    vistos = ({pl["pais_id"] for pl in plan_listas}
              | {c.pais_id for c in clientes.values() if c.activo})
    for pais_id in sorted(vistos - con_general,
                          key=lambda x: nombres_pais.get(x) or ""):
        pendientes.append({"tipo": "sin_general",
                           "pais": nombres_pais.get(pais_id)})
    # La categoria de un pais que tiene listas y no esta en Odoo: sus
    # listas no tienen de donde sacar productos (seccion 123).
    for x in lecturas():
        if (x["pais"] in con_categoria or not x["categoria"]
                or not (settings.odoo_categoria_productos or "").strip()):
            continue
        if any(l["por_nombre"] == x["pais"] for l in listas.values()):
            pendientes.append({"tipo": "sin_categoria_pais",
                               "pais": nombres_pais.get(paises.get(x["pais"])),
                               "categoria": x["categoria"]})
    for odoo_id, nombre in sorted(sin_confirmar.items(), key=lambda x: x[1]):
        pendientes.append({"tipo": "producto_sin_confirmar", "producto": nombre})
    categoria_de = {x["pais"]: x["categoria"] for x in lecturas() if x["categoria"]}
    for odoo_id, en in sorted(fuera_de_categoria.items(),
                              key=lambda x: datos["productos_fuera"][x[0]]):
        pendientes.append({"tipo": "producto_fuera",
                           "producto": datos["productos_fuera"][odoo_id],
                           "listas": sorted(x for x in en if x),
                           "categoria": " / ".join(sorted(
                               {categoria_de.get(c) or settings.odoo_categoria_productos
                                for c in fuera_de_paises.get(odoo_id, {"MX"})}))})
    pendientes.extend(de_otro_pais)
    # Cuantas listas se leyeron de cada pais, por su prefijo (seccion 123).
    leidas_de = {}
    for l in listas.values():
        if l["por_nombre"]:
            leidas_de[l["por_nombre"]] = leidas_de.get(l["por_nombre"], 0) + 1
    return {"listas": plan_listas, "lista_de": lista_de,
            "implantados_de": implantados_de, "clientes": por_id,
            "pendientes": pendientes, "campo_implantados": campo,
            "nombres_pais": nombres_pais, "nombre_de_lista": nombre_de_lista,
            "otra_moneda": otra_moneda, "leidas": len(listas),
            "pais_de_lista": {pl["odoo_id"]: pl["pais_id"] for pl in plan_listas},
            "leidas_de": leidas_de,
            # Las listas del pais sin categoria: ni se reemplazan ni se
            # apagan (seccion 127).
            "intactas": sorted(intactas),
            "paises_sin_categoria": sorted(sin_categoria_pais)}


def no_pe_ids(datos: dict) -> set:
    return {l["id"] for l in datos.get("fuera") or ()}


def _modalidades(db: Session) -> dict:
    return {(mo.pais_id, mo.codigo.value): mo
            for mo in db.query(m.Modalidad).all()}


def modalidad_guardada(codigo: str) -> str:
    """Con que modalidad de Centauro se guarda un precio de la lista: lo
    que en Odoo se cobra por «Mes» (seccion 123) va con la del implantado,
    que se cobra al mes; lo demas, con la suya."""
    return (m.CodigoModalidad.IMPLANTADO.value if codigo == reglas.MES
            else codigo)


def _filas_de(precios: dict, pais_id: int, modalidades: dict) -> tuple:
    """(recurso, vehiculo, paquete, hora extra, faltan) de una lista: lo
    que va en las tablas del tarifario. La modalidad es la del pais.

    El precio por mes (seccion 123) se guarda con la modalidad del
    implantado de su pais. La hora extra de un rol va con su precio y,
    desde la seccion 123, tambien con su paquete: la lista de Amazon
    Brasil pacta el conductor con la Minivan y su hora extra, sin precio
    suelto del conductor, y sin esto su hora extra se perdia."""
    recurso, vehiculo, paquete, faltan = [], [], [], set()
    extra_general = precios.get((reglas.HORA_EXTRA, None, None, None))
    extras = {k[1]: v for k, v in precios.items() if k[0] == reglas.HORA_EXTRA}
    for (clase, perfil, categoria, codigo), p in precios.items():
        if clase == reglas.HORA_EXTRA:
            continue
        modalidad = modalidades.get((pais_id, modalidad_guardada(codigo)))
        if modalidad is None:
            faltan.add(modalidad_guardada(codigo))
            continue
        fila = {"modalidad_id": modalidad.id, "precio": p["precio"],
                "origen": p["origen"], "producto_odoo_id": p["producto_id"]}
        extra = (extras.get(perfil) or extra_general) if perfil else None
        lleva = bool(extra) and modalidad.aplica_horas_extra
        # Con que producto sale en la factura (seccion 116).
        con_extra = {"precio_hora_extra": extra["precio"] if lleva else None,
                     "producto_hora_extra_id": extra["producto_id"] if lleva else None}
        if clase == reglas.ROL:
            recurso.append({**fila, "perfil_id": perfil, **con_extra})
        elif clase == reglas.UNIDAD:
            vehiculo.append({**fila, "categoria_id": categoria})
        else:
            paquete.append({**fila, "perfil_id": perfil,
                            "categoria_id": categoria, **con_extra})
    return recurso, vehiculo, paquete, extra_general, sorted(faltan)


def _flota_sin_precio(db: Session, plan: dict) -> list[dict]:
    """Las unidades de la flota de un pais que su general no cobra (seccion
    123): las seis Corolla Cross de Brasil son «CUV Blindada», y las
    generales de Brasil todavia no le ponen precio. Se dice; no detiene
    nada --la unidad se asigna igual--. Solo la flota de Odoo, de los
    paises con general."""
    con_precio = {}
    for pl in plan["listas"]:
        if pl["general"]:
            con_precio.setdefault(pl["pais_id"], set()).update(
                f["categoria_id"] for f in pl["vehiculo"])
    if not con_precio:
        return []
    cuenta = {}
    for v in (db.query(m.Vehiculo)
              .filter(m.Vehiculo.activo.is_(True), m.Vehiculo.odoo_id.isnot(None),
                      m.Vehiculo.pais_id.in_(sorted(con_precio)))):
        if v.categoria_id not in con_precio[v.pais_id]:
            llave = (v.pais_id, v.categoria_id)
            cuenta[llave] = cuenta.get(llave, 0) + 1
    categorias = {c.id: c.nombre for c in db.query(m.CategoriaVehiculo).all()}
    return [{"tipo": "flota_sin_precio", "pais": plan["nombres_pais"].get(pais_id),
             "categoria": categorias.get(categoria_id), "unidades": n}
            for (pais_id, categoria_id), n in sorted(
                cuenta.items(), key=lambda x: (plan["nombres_pais"].get(x[0][0]) or "",
                                               categorias.get(x[0][1]) or ""))]


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
                "prefijos": prefijos(), "lecturas": [], "por_pais": [],
                "generales": [], "por_cliente": [], "sin_cliente": [],
                "precios": 0, "clientes": 0, "clientes_con_general": 0,
                "cambian": [], "implantados": 0, "campo_implantados": None,
                "pendientes": []}
    if not ensayo:
        # Los productos nuevos llegan con su sugerencia antes del plan:
        # asi finanzas los ve en la tabla aunque todavia no pongan precio.
        leer_productos(db, odoo, datos["referenciados"], ahora,
                       en_pe=datos["en_pe"], por_pais=datos["categorias_pais"])
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
        # Cada precio que pone la lista: sus renglones y cada hora extra, la
        # de todos y la de cada rol (seccion 123: la de Brasil trae la de
        # cada puesto).
        total = (len(recurso) + len(vehiculo) + len(paquete)
                 + sum(1 for k in pl["precios"] if k[0] == reglas.HORA_EXTRA))
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

    plan["pendientes"].extend(_flota_sin_precio(db, plan))

    # A que tarifario cambia cada cliente. A una lista sin precios que
    # Centauro sepa leer no se le cambia: se queda como estaba y se dice.
    cambios, retenidos = [], []
    # Las listas que Odoo trajo hoy, leidas o no: la que falta esta
    # archivada o borrada alla.
    leidas_ahora = {l["id"] for l in datos["listas"]} | set(no_pe_ids(datos))
    # Las listas que no son de PE no se leen (seccion 112). El cliente que
    # trae una se queda con el tarifario que tenia --aunque sea el de esa
    # misma lista: sus precios ya no se ponen al dia-- y se dice, con el
    # prefijo de su pais (seccion 123).
    no_pe = {l["id"]: l["nombre"] for l in datos["fuera"]}
    paises = {p.id: p for p in db.query(m.Pais).all()}
    prefijo_de = {x["pais"]: x["prefijo"] for x in lecturas() if x["prefijo"]}

    def prefijo_del(cliente) -> str:
        pais = paises.get(cliente.pais_id)
        return (prefijo_de.get(pais.codigo.upper() if pais else None)
                or settings.odoo_prefijo_listas)

    # Una lista de otro pais nunca se le pone a un cliente (seccion 123):
    # se queda con lo que tenia y se dice.
    def de_otro_pais(cliente, lista_id, implantados=False) -> dict | None:
        suyo = plan["pais_de_lista"].get(lista_id)
        if suyo is None or suyo == cliente.pais_id:
            return None
        return {"tipo": "lista_de_otro_pais", "cliente": cliente.nombre,
                "lista": nombre_de_la(lista_id),
                "pais_lista": plan["nombres_pais"].get(suyo),
                "pais": plan["nombres_pais"].get(cliente.pais_id),
                **({"implantados": True} if implantados else {})}

    def nombre_de_la(lista_id):
        return next((l["nombre"] for l in plan["listas"]
                     if l["odoo_id"] == lista_id),
                    plan["nombre_de_lista"].get(lista_id))

    for cliente_id, lista_id in sorted(plan["lista_de"].items()):
        cliente = plan["clientes"][cliente_id]
        actual = cliente.tarifario.odoo_id if cliente.tarifario else None
        if lista_id in no_pe:
            retenidos.append({"tipo": "lista_no_pe", "cliente": cliente.nombre,
                              "lista": no_pe[lista_id],
                              "prefijo": prefijo_del(cliente)})
            continue
        otro = de_otro_pais(cliente, lista_id)
        if otro is not None:
            retenidos.append(otro)
            continue
        if lista_id is None or lista_id == actual:
            # Su ficha sigue nombrando una lista que Odoo ya no trae
            # --archivada-- (seccion 127, hallazgo r5-05): el cliente se
            # queda con ella y con sus precios de la ultima lectura, y
            # eso hay que decirlo; antes no lo decia nadie.
            if (lista_id is not None and lista_id not in leidas_ahora
                    and lista_id not in plan.get("intactas", ())):
                retenidos.append({"tipo": "lista_archivada",
                                  "cliente": cliente.nombre,
                                  "lista": nombre_de_la(lista_id)})
            continue
        nombre = nombre_de_la(lista_id)
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
                "prefijo": prefijo_del(cliente)})
            continue
        otro = de_otro_pais(cliente, lista_id, implantados=True)
        if otro is not None:
            plan["pendientes"].append(otro)
            continue
        if lista_id != actual and (lista_id is None or lista_id in leidas):
            implantados.append({"cliente_id": cliente_id, "cliente": cliente.nombre,
                                "lista_id": lista_id})

    generales = [l for l in listas_informe if l["general"]]
    # Lo que se lee de cada pais (seccion 123): su categoria, sus listas y
    # su compania. Sin la categoria de Mexico se lee todo, como antes, y
    # no se dice por pais.
    por_codigo = {p.codigo.upper(): p for p in paises.values()}
    con_categoria = set(datos.get("categorias_pais") or {})
    leen = ([x for x in lecturas() if x["categoria"] and x["prefijo"]]
            if datos["en_pe"] is not None and _para_prefijo(settings.odoo_prefijo_listas)
            else [])
    informe = {
        "ensayo": ensayo,
        "leidas": plan["leidas"],
        # Las listas activas de Odoo que no son de PE: solo se cuentan.
        "fuera": len(datos["fuera"]),
        "prefijo": settings.odoo_prefijo_listas,
        "categoria": settings.odoo_categoria_productos,
        "prefijos": [x["prefijo"] for x in leen] or prefijos(),
        "lecturas": [{"codigo": x["pais"],
                      "pais": (por_codigo[x["pais"]].nombre if x["pais"] in por_codigo
                               else x["pais"]),
                      "categoria": x["categoria"], "prefijo": x["prefijo"],
                      "idioma": x["idioma"],
                      "compania": (datos.get("companias") or {}).get(x["compania"]),
                      "en_odoo": x["pais"] in con_categoria}
                     for x in leen],
        "por_pais": [{"codigo": x["pais"],
                      "pais": (por_codigo[x["pais"]].nombre if x["pais"] in por_codigo
                               else x["pais"]),
                      "leidas": plan["leidas_de"].get(x["pais"], 0)}
                     for x in leen] if len(leen) > 1 else [],
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
    # Las del pais cuya categoria no esta en Odoo se quedan como estaban
    # (seccion 127, hallazgo r5-01).
    leidas = {pl["odoo_id"] for pl in plan["listas"]} | set(plan.get("intactas") or ())
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

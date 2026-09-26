# -*- coding: utf-8 -*-
"""Las reglas de los tarifarios que vienen de Odoo, sin base de datos.

Seccion 77. Salvador, 26 de septiembre: los tarifarios viven en Odoo --una
lista general por pais y, cuando el cliente negocio la suya, la del
cliente-- y Centauro los lee de ahi. Aprobo las cinco recomendaciones de
la propuesta (Propuesta_tarifarios_desde_Odoo.pdf).

Aqui viven dos cosas, las dos sin leer ni escribir nada:

  * Que es cada producto de Odoo, sugerido por su nombre: un rol, una
    unidad, un paquete conductor + unidad, la hora extra, los viaticos o
    algo que no es de Proteccion Ejecutiva. Finanzas lo confirma; aqui
    solo se sugiere.
  * Cuanto cuesta cada cosa en cada lista, con las MISMAS reglas con que
    Odoo le pone precio a una cotizacion. Si Centauro calculara distinto,
    el comparativo del cierre y la factura dirian dos precios para el
    mismo servicio. Lo que Odoo hace y aqui no se sabe leer no se
    adivina: se reporta.

La regla de Odoo, en corto: de las reglas de la lista que le aplican al
producto gana la mas especifica (variante, producto, categoria, todo);
si ninguna aplica, el «Precio de venta» del producto. Una regla puede
decir un precio fijo, un descuento, o «lo de otra lista»; asi se hace en
Odoo que lo que el cliente no negocio salga de la general de su pais.
"""
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.odoo_personal_reglas import normal, texto

CERO = Decimal("0")
UNO = Decimal("1")
CIEN = Decimal("100")
CENTAVO = Decimal("0.01")

# Las clases de producto. Van como texto: agregar una no toca la base.
ROL, UNIDAD, PAQUETE = "rol", "unidad", "paquete"
HORA_EXTRA, VIATICOS, NO_EP = "hora_extra", "viaticos", "no_ep"
CLASES = (ROL, UNIDAD, PAQUETE, HORA_EXTRA, VIATICOS, NO_EP)
# Las que ponen un precio en el tarifario.
CON_PRECIO = (ROL, UNIDAD, PAQUETE, HORA_EXTRA)

FULL_DAY, MEDIO_DIA, TRANSFER = "full_day", "medio_dia", "transfer"
MODALIDADES = (FULL_DAY, MEDIO_DIA, TRANSFER)

# De donde salio un precio. El orden es la preferencia cuando dos
# productos dicen lo mismo: lo que la lista pacto gana a lo que hereda, y
# lo que hereda gana al «Precio de venta».
PROPIO, GENERAL, OTRA, PRECIO_VENTA = "propio", "general", "otra", "precio_venta"
RANGO = {PROPIO: 0, GENERAL: 1, OTRA: 1, PRECIO_VENTA: 2}

# Hasta donde se sigue una cadena de «lo de otra lista». Odoo no pone
# limite; aqui una lista que se nombra a si misma no debe colgar nada.
PROFUNDIDAD = 5


# ================================================================ palabras

def palabras(nombre) -> list[str]:
    """El nombre en palabras sueltas, sin acentos ni signos: «MINIVAN
    Blindada (Transfer)» es minivan, blindada, transfer. Asi «minivan» no
    se confunde con «van»."""
    return re.findall(r"[a-z0-9]+", normal(nombre))


def _frase(nombre) -> str:
    return " " + " ".join(palabras(nombre)) + " "


# Los roles de Centauro, dichos como los escriben en Odoo --en espanol y
# en ingles, porque Amazon y Crisol facturan en ingles--.
SINONIMOS_ROL = {
    "conductor": {"conductor", "driver", "chofer", "motorista"},
    "agente": {"agente", "agent", "escolta", "bodyguard", "guardia"},
    "coordinador": {"coordinador", "coordinator", "coordinadora"},
    "consultor": {"consultor", "consultant", "consultora"},
}
# Lo que hace de un rol OTRO rol, con otro precio: el «Conductor de
# Seguridad Federal» no es el conductor de siempre. Con esto no se
# sugiere nada y finanzas decide.
CALIFICADORES = {"federal"}

SINONIMOS_UNIDAD = {
    "cuv": {"cuv", "rav", "rav4", "crossover"},
    "minivan": {"minivan", "sienna", "odyssey"},
    "suv": {"suv", "suburban", "tahoe", "yukon", "escalade"},
    "van": {"van", "hiace", "sprinter", "urvan", "transit"},
    "sedan": {"sedan"},
}
BLINDAJE = {"blindada", "blindado", "blindaje", "armored", "armoured"}

HORA_EXTRA_FRASES = (" hora extra ", " horas extra ", " overtime ",
                     " extra hour ", " extra hours ")
VIATICOS_PALABRAS = {"expense", "expenses", "viatico", "viaticos", "gasto",
                     "gastos", "meals", "meal", "food", "comida", "comidas",
                     "alimentos", "hospedaje", "hotel", "casetas", "caseta",
                     "peaje", "peajes", "toll", "tolls", "combustible",
                     "gasolina", "fuel"}
VIATICOS_FRASES = (" booking fee ", " booking fees ")
NO_EP_FRASES = (" central de inteligencia ", " monitoreo ", " rastreo ",
                " gps ")


def tipo_de_rol(nombre) -> str | None:
    """conductor, agente, coordinador o consultor; None si no se sabe o
    si trae un calificador que lo hace otro rol."""
    p = set(palabras(nombre))
    if p & CALIFICADORES:
        return None
    hallados = [t for t, sin in SINONIMOS_ROL.items() if p & sin]
    return hallados[0] if len(hallados) == 1 else None


def tipo_de_unidad(nombre) -> tuple[str | None, bool]:
    """(tipo, blindada). El tipo es None si no se reconoce o si dice dos."""
    p = set(palabras(nombre))
    hallados = [t for t, sin in SINONIMOS_UNIDAD.items() if p & sin]
    return (hallados[0] if len(hallados) == 1 else None), bool(p & BLINDAJE)


def modalidad_de(nombre) -> str:
    """La modalidad dicha en el nombre; sin decir nada, dia completo. Asi
    cobra Odoo al conductor o a la unidad solos: un precio por dia."""
    f = _frase(nombre)
    if " transfer " in f or " traslado " in f:
        return TRANSFER
    if " medio dia " in f or " half day " in f or " medio " in f:
        return MEDIO_DIA
    return FULL_DAY


def perfiles_por_tipo(perfiles: list) -> dict:
    """{tipo: perfil_id} de los roles de Centauro, reconocidos por su
    codigo y su nombre. Un tipo que coincide con dos roles no se sugiere."""
    vistos = {}
    for p in perfiles:
        tipo = tipo_de_rol(f"{p.get('codigo', '')} {p.get('nombre', '')}")
        if tipo:
            vistos.setdefault(tipo, []).append(p["id"])
    return {t: ids[0] for t, ids in vistos.items() if len(ids) == 1}


def categorias_por_tipo(categorias: list) -> dict:
    """{(tipo, blindada): categoria_id} de las unidades de Centauro."""
    vistos = {}
    for c in categorias:
        tipo, blindada = tipo_de_unidad(
            f"{c.get('codigo', '')} {c.get('nombre', '')}")
        blindada = bool(c.get("blindado")) or blindada
        if tipo:
            vistos.setdefault((tipo, blindada), []).append(c["id"])
    return {k: ids[0] for k, ids in vistos.items() if len(ids) == 1}


def sugerir(producto: dict, perfiles: dict, categorias: dict) -> dict:
    """Que es este producto, por su nombre.

    `perfiles` y `categorias` salen de `perfiles_por_tipo` y
    `categorias_por_tipo`. Devuelve {clase, perfil_id, categoria_id,
    modalidad}; clase None quiere decir que no se supo y lo decide
    finanzas.
    """
    nada = {"clase": None, "perfil_id": None, "categoria_id": None,
            "modalidad": None}
    nombre = texto(producto.get("name"))
    f = _frase(nombre)
    p = set(palabras(nombre))

    # Lo que no es un servicio --GPS, relojes, rastreadores-- se vende en
    # Odoo, pero no es de Proteccion Ejecutiva.
    if texto(producto.get("type")) in ("consu", "product", "combo"):
        return {**nada, "clase": NO_EP}
    if any(x in f for x in HORA_EXTRA_FRASES):
        return {**nada, "clase": HORA_EXTRA}
    if p & VIATICOS_PALABRAS or any(x in f for x in VIATICOS_FRASES):
        return {**nada, "clase": VIATICOS}
    if any(x in f for x in NO_EP_FRASES):
        return {**nada, "clase": NO_EP}

    modalidad = modalidad_de(nombre)
    if "+" in nombre:
        persona, _, unidad = nombre.partition("+")
        perfil = perfiles.get(tipo_de_rol(persona))
        tipo, blindada = tipo_de_unidad(unidad)
        categoria = categorias.get((tipo, blindada))
        if perfil and categoria:
            return {"clase": PAQUETE, "perfil_id": perfil,
                    "categoria_id": categoria, "modalidad": modalidad}
        return nada

    perfil = perfiles.get(tipo_de_rol(nombre))
    tipo, blindada = tipo_de_unidad(nombre)
    categoria = categorias.get((tipo, blindada))
    if perfil and not categoria:
        return {**nada, "clase": ROL, "perfil_id": perfil,
                "modalidad": modalidad}
    if categoria and not perfil:
        return {**nada, "clase": UNIDAD, "categoria_id": categoria,
                "modalidad": modalidad}
    return nada


# ================================================================ precios

def id_de(valor) -> int | None:
    """El id de un many2one, venga como [id, nombre], como dict o suelto."""
    if valor in (False, None, ""):
        return None
    if isinstance(valor, (list, tuple)):
        return int(valor[0]) if valor else None
    if isinstance(valor, dict):
        return int(valor["id"]) if valor.get("id") else None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def ids_de(valor) -> list[int]:
    """Los ids de un many2many."""
    if not valor:
        return []
    return [i for i in (id_de(v) for v in valor) if i]


def _dinero(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _redondear(precio: Decimal, paso) -> Decimal:
    """El «Redondeo» de una regla de Odoo: al multiplo mas cercano."""
    paso = _dinero(paso)
    if paso <= 0:
        return precio
    return (precio / paso).quantize(UNO, rounding=ROUND_HALF_UP) * paso


class Listas:
    """Las listas de precios de Odoo, listas para preguntarles precios.

    `listas`: {id: {nombre, moneda, activa}}. `reglas`: las de todas las
    listas, como las lee Odoo. `productos`: {id de plantilla: {precio
    (el «Precio de venta», en la moneda de la empresa), categoria}}.
    `categorias`: {id: ruta de padres, «1/5/9/»}. `tasas`: {moneda:
    cuantas unidades de esa moneda vale una de la empresa} --la de la
    empresa vale 1--. `hoy`: la fecha contra la que se ven las reglas
    con vigencia. `empresa`: la moneda de la empresa, en la que esta el
    «Precio de venta». `variantes`: {variante: plantilla}, para las
    reglas que Odoo guarda por variante.
    """

    def __init__(self, listas: dict, reglas: list, productos: dict,
                 categorias: dict, tasas: dict, hoy: date,
                 empresa: str = "MXN", variantes: dict | None = None):
        self.listas = listas
        self.productos = productos
        self.categorias = categorias
        self.tasas = tasas
        self.hoy = hoy
        self.empresa = empresa
        self.variantes = variantes or {}
        self.por_lista = {}
        for r in reglas:
            self.por_lista.setdefault(id_de(r.get("pricelist_id")), []).append(r)
        for rs in self.por_lista.values():
            # El orden de Odoo: lo mas especifico primero, a igualdad la
            # cantidad minima mayor, la categoria de id mayor y la regla
            # mas nueva.
            rs.sort(key=lambda r: (texto(r.get("applied_on")) or "3_global",
                                   -float(r.get("min_quantity") or 0),
                                   -(id_de(r.get("categ_id")) or 0),
                                   -int(r.get("id") or 0)))

    # ------------------------------------------------------------ monedas
    def convertir(self, monto: Decimal, de: str, a: str) -> Decimal | None:
        if de == a:
            return monto
        tasa_de, tasa_a = self.tasas.get(de), self.tasas.get(a)
        if not tasa_de or not tasa_a:
            return None
        return monto * _dinero(tasa_a) / _dinero(tasa_de)

    # ------------------------------------------------------------ reglas
    def _aplica(self, regla: dict, producto_id: int) -> bool:
        if float(regla.get("min_quantity") or 0) > 1:
            return False
        desde = texto(regla.get("date_start"))[:10]
        hasta = texto(regla.get("date_end"))[:10]
        if desde and date.fromisoformat(desde) > self.hoy:
            return False
        if hasta and date.fromisoformat(hasta) < self.hoy:
            return False
        donde = texto(regla.get("applied_on")) or "3_global"
        if donde == "3_global":
            return True
        if donde == "1_product":
            return id_de(regla.get("product_tmpl_id")) == producto_id
        if donde == "0_product_variant":
            # La plantilla de la variante: los productos de servicio de
            # Centauro son de una sola variante.
            plantilla = (id_de(regla.get("product_tmpl_id"))
                         or self.variantes.get(id_de(regla.get("product_id"))))
            return plantilla == producto_id
        if donde == "2_product_category":
            categoria = id_de(regla.get("categ_id"))
            ruta = self.categorias.get(
                (self.productos.get(producto_id) or {}).get("categoria"), "")
            return bool(categoria) and f"/{categoria}/" in f"/{ruta}"
        return False

    def precio(self, lista_id: int, producto_id: int,
               _profundidad: int = 0) -> dict:
        """El precio de un producto en una lista, como lo calcula Odoo.

        {precio, origen, regla, problema}: `origen` dice de donde salio
        --PROPIO, de OTRA lista (o de la GENERAL, lo decide quien llama),
        o PRECIO_VENTA--; `problema` dice por que no se pudo, y entonces
        no hay precio.
        """
        lista = self.listas.get(lista_id)
        producto = self.productos.get(producto_id)
        if lista is None or producto is None:
            return {"precio": None, "origen": None, "regla": None,
                    "problema": "no esta en Odoo"}
        if _profundidad > PROFUNDIDAD:
            return {"precio": None, "origen": None, "regla": None,
                    "problema": "las listas se nombran unas a otras sin fin"}

        regla = next((r for r in self.por_lista.get(lista_id, [])
                      if self._aplica(r, producto_id)), None)
        if regla is None:
            return self._de_la_venta(lista, producto)

        especifica = texto(regla.get("applied_on")) in ("0_product_variant",
                                                       "1_product")
        como = texto(regla.get("compute_price")) or "fixed"
        if como == "fixed":
            return {"precio": _dinero(regla.get("fixed_price")).quantize(CENTAVO),
                    "origen": PROPIO, "regla": regla.get("id"),
                    "problema": None}

        # Descuento o formula: sobre el «Precio de venta» o sobre lo que
        # diga otra lista.
        base = texto(regla.get("base")) or "list_price"
        if base == "list_price":
            partida = self._de_la_venta(lista, producto)
            origen = PROPIO if especifica else PRECIO_VENTA
        elif base == "pricelist":
            otra = id_de(regla.get("base_pricelist_id"))
            partida = self.precio(otra, producto_id, _profundidad + 1)
            if partida["precio"] is not None:
                convertido = self.convertir(
                    partida["precio"], (self.listas.get(otra) or {}).get("moneda"),
                    lista["moneda"])
                partida = {**partida, "precio": convertido}
                if convertido is None:
                    partida["problema"] = "sin tipo de cambio"
            origen = PROPIO if especifica else OTRA
        else:
            return {"precio": None, "origen": None, "regla": regla.get("id"),
                    "problema": f"regla sobre «{base}», que Centauro no lee"}
        if partida["precio"] is None:
            return {**partida, "regla": regla.get("id")}

        precio = partida["precio"]
        if como == "percentage":
            precio = precio - precio * _dinero(regla.get("percent_price")) / CIEN
        elif como == "formula":
            if _dinero(regla.get("price_min_margin")) or _dinero(
                    regla.get("price_max_margin")):
                return {"precio": None, "origen": None, "regla": regla.get("id"),
                        "problema": "regla con margen, que Centauro no lee"}
            precio = precio - precio * _dinero(regla.get("price_discount")) / CIEN
            precio = _redondear(precio, regla.get("price_round"))
            precio = precio + _dinero(regla.get("price_surcharge"))
        else:
            return {"precio": None, "origen": None, "regla": regla.get("id"),
                    "problema": f"regla «{como}», que Centauro no lee"}
        return {"precio": precio.quantize(CENTAVO, rounding=ROUND_HALF_UP),
                "origen": (partida["origen"] if origen == OTRA
                           and partida["origen"] == PRECIO_VENTA else origen),
                "regla": regla.get("id"), "problema": None,
                "de_lista": (id_de(regla.get("base_pricelist_id"))
                             if base == "pricelist" else None)}

    def _de_la_venta(self, lista: dict, producto: dict) -> dict:
        precio = self.convertir(_dinero(producto.get("precio")),
                                self.empresa, lista["moneda"])
        if precio is None:
            return {"precio": None, "origen": None, "regla": None,
                    "problema": "sin tipo de cambio"}
        return {"precio": precio.quantize(CENTAVO, rounding=ROUND_HALF_UP),
                "origen": PRECIO_VENTA, "regla": None, "problema": None}

    def resto_de(self, lista_id: int) -> tuple[str, int | None]:
        """De donde sale lo que la lista no trae: («lista», id) si su
        ultima regla es «todo lo demas, de otra lista»; si no, el «Precio
        de venta» (None)."""
        for r in self.por_lista.get(lista_id, []):
            if (texto(r.get("applied_on")) or "3_global") != "3_global":
                continue
            if texto(r.get("base")) == "pricelist" and texto(
                    r.get("compute_price")) in ("formula", "percentage"):
                otra = id_de(r.get("base_pricelist_id"))
                return (self.listas.get(otra) or {}).get("nombre", ""), otra
            return "", None
        return "", None


# ================================================================ el plan

def concepto_de(producto: dict) -> tuple | None:
    """La llave de lo que pone precio un producto: (clase, perfil,
    categoria, modalidad). La hora extra no tiene modalidad."""
    clase = producto.get("clase")
    if clase not in CON_PRECIO:
        return None
    if clase == HORA_EXTRA:
        return (HORA_EXTRA, producto.get("perfil_id"), None, None)
    if clase == ROL and producto.get("perfil_id") and producto.get("modalidad"):
        return (ROL, producto["perfil_id"], None, producto["modalidad"])
    if clase == UNIDAD and producto.get("categoria_id") and producto.get("modalidad"):
        return (UNIDAD, None, producto["categoria_id"], producto["modalidad"])
    if (clase == PAQUETE and producto.get("perfil_id")
            and producto.get("categoria_id") and producto.get("modalidad")):
        return (PAQUETE, producto["perfil_id"], producto["categoria_id"],
                producto["modalidad"])
    return None


def precios_de_la_lista(listas: Listas, lista_id: int, productos: list,
                        generales: set) -> tuple[dict, list, list]:
    """({concepto: {precio, origen, producto}}, conflictos, problemas) de
    una lista.

    `productos`: los de la tabla de Centauro ya confirmados, con su
    odoo_id. `generales`: los ids de las listas generales, para decir
    GENERAL y no OTRA cuando el precio sale de la de su pais.

    Si dos productos dicen lo mismo --«Conductor + Minivan (Transfer)» y
    su gemelo en ingles-- gana el que la lista pacto. Si los dos estan
    en el mismo escalon, manda el que finanzas marco como preferido; si
    no hay y dicen precios distintos no se escoge: se reporta y ese
    concepto se queda sin precio hasta que se aclare.
    """
    candidatos = {}
    problemas = []
    for prod in productos:
        concepto = concepto_de(prod)
        if concepto is None:
            continue
        r = listas.precio(lista_id, prod["odoo_id"])
        if r["precio"] is None:
            problemas.append({"producto": prod["nombre"],
                              "problema": r["problema"]})
            continue
        origen = r["origen"]
        if origen == OTRA and r.get("de_lista") in generales:
            origen = GENERAL
        candidatos.setdefault(concepto, []).append(
            {"precio": r["precio"], "origen": origen,
             "producto_id": prod["id"], "producto": prod["nombre"],
             "vendible": prod.get("vendible", True),
             "preferido": bool(prod.get("preferido"))})

    precios, conflictos = {}, []
    for concepto, lista in candidatos.items():
        # Lo que ya no se vende solo cuenta si la lista lo pacto: un
        # producto viejo con su «Precio de venta» no debe ganarle a nadie.
        lista = [c for c in lista if c["vendible"] or c["origen"] == PROPIO]
        if not lista:
            continue
        mejor = min(RANGO[c["origen"]] for c in lista)
        empatados = [c for c in lista if RANGO[c["origen"]] == mejor]
        preferidos = [c for c in empatados if c["preferido"]]
        if len(preferidos) == 1:
            precios[concepto] = preferidos[0]
            continue
        distintos = {c["precio"] for c in empatados}
        if len(distintos) > 1:
            conflictos.append({"concepto": concepto,
                               "productos": [(c["producto"], c["precio"])
                                             for c in empatados]})
            continue
        elegido = min(empatados, key=lambda c: c["producto_id"])
        precios[concepto] = elegido
    return precios, conflictos, problemas


def pais_de_la_lista(lista: dict, paises_de_clientes: set, paises: dict,
                     grupos: dict) -> tuple[int | None, list]:
    """(pais_id, paises de sus grupos). La general dice su pais con el
    grupo de paises de Odoo; la de un cliente toma el de sus clientes, y
    si no tiene clientes, el de su moneda.

    `paises`: {codigo: pais_id}. `grupos`: {grupo_id: {codigos}}.
    """
    codigos = set()
    for g in lista.get("grupos") or []:
        codigos |= grupos.get(g, set())
    de_grupos = sorted({paises[c] for c in codigos if c in paises})
    if de_grupos:
        return (de_grupos[0] if len(de_grupos) == 1 else None), de_grupos
    if len(paises_de_clientes) == 1:
        return next(iter(paises_de_clientes)), []
    por_moneda = {"MXN": "MX", "BRL": "BR", "VES": "VE"}.get(lista.get("moneda"))
    if por_moneda in paises:
        return paises[por_moneda], []
    return paises.get("MX"), []

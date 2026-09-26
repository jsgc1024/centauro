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
    dice y no se lee: los costos van en la moneda del pais y la utilidad
    y la comision del consultor restarian dolares menos pesos (BITACORA,
    «La moneda», que Salvador decidio dejar para el final).

Las reglas --que es cada producto, cuanto cuesta en cada lista-- viven en
odoo_tarifarios_reglas.py, sin base de datos.
"""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import accesos
from app import models as m
from app import odoo_tarifarios_reglas as reglas
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
                   "sale_ok", "active"]
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


def leer_productos(db: Session, odoo, referenciados=(), ahora=None) -> dict:
    """Trae de Odoo los productos que se venden --y los que nombra alguna
    lista aunque ya no se vendan-- y los deja en la tabla de productos.

    Lo nuevo llega con su sugerencia. Lo que finanzas ya confirmo no se
    vuelve a sugerir: solo se le pone al dia el nombre, la unidad y el
    «Precio de venta». Lo que Odoo ya no trae se queda, marcado como que
    ya no se vende. No hace commit: lo hace quien llama.
    """
    ahora = ahora or _utc()
    dominio = [["sale_ok", "=", True]]
    if referenciados:
        dominio = ["|", ["sale_ok", "=", True],
                   ["id", "in", sorted(referenciados)]]
    filas = odoo.leer("product.template", dominio, CAMPOS_PRODUCTO,
                      archivados=True)
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
        producto.odoo_sincronizado_en = ahora
        if not producto.confirmado:
            s = reglas.sugerir(f, perfiles, categorias)
            producto.clase = s["clase"]
            producto.perfil_id = s["perfil_id"]
            producto.categoria_id = s["categoria_id"]
            producto.modalidad = s["modalidad"]
            sugeridos += 1 if s["clase"] else 0
    for odoo_id, producto in existentes.items():
        if odoo_id not in vistos:
            producto.vendible = False
    db.flush()
    return {"leidos": len(filas), "nuevos": nuevos, "sugeridos": sugeridos}


def tabla_de_productos(db: Session) -> list[dict]:
    return [{"id": p.id, "odoo_id": p.odoo_id, "nombre": p.nombre,
             "unidad": p.unidad, "tipo_odoo": p.tipo_odoo,
             "precio_venta": p.precio_venta, "vendible": p.vendible,
             "clase": p.clase, "perfil_id": p.perfil_id,
             "categoria_id": p.categoria_id, "modalidad": p.modalidad,
             "confirmado": p.confirmado, "preferido": p.preferido,
             "confirmado_en": (p.confirmado_en.isoformat()
                               if p.confirmado_en else None)}
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
    """Todo lo que la lectura necesita de Odoo, de una vez."""
    listas = odoo.leer("product.pricelist", [["active", "=", True]],
                       CAMPOS_LISTA)
    ids = [l["id"] for l in listas]
    reglas_odoo = (odoo.leer("product.pricelist.item",
                             [["pricelist_id", "in", ids]], CAMPOS_REGLA)
                   if ids else [])
    referenciados = {reglas.id_de(r.get("product_tmpl_id"))
                     for r in reglas_odoo} - {None}
    variantes = {reglas.id_de(r.get("product_id")) for r in reglas_odoo} - {None}
    productos = odoo.leer("product.template",
                          ["|", ["sale_ok", "=", True],
                           ["id", "in", sorted(referenciados)]]
                          if referenciados else [["sale_ok", "=", True]],
                          ["list_price", "categ_id", "name"], archivados=True)
    de_variante = {}
    if variantes:
        de_variante = {v["id"]: reglas.id_de(v.get("product_tmpl_id"))
                       for v in odoo.leer("product.product",
                                          [["id", "in", sorted(variantes)]],
                                          ["product_tmpl_id"], archivados=True)}
    categorias = {c["id"]: texto(c.get("parent_path"))
                  for c in odoo.leer("product.category", [], ["parent_path"])}
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
            "campo_implantados": campo, "socios": socios}


def _plan(db: Session, datos: dict, hoy) -> dict:
    """Que tarifario sale de cada lista y que lista le toca a cada cliente,
    sin guardar nada."""
    empresa = next((texto(mo.get("name")) for mo in datos["monedas"]
                    if float(mo.get("rate") or 0) == 1.0), "MXN")
    tasas = {texto(mo.get("name")): mo.get("rate") for mo in datos["monedas"]
             if mo.get("rate")}
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
    for r in datos["reglas"]:
        odoo_id = reglas.id_de(r.get("product_tmpl_id"))
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
        # Los costos --viaticos, comisiones, nomina-- van siempre en la
        # moneda del pais, y la utilidad y la comision del consultor restan
        # una de otra sin convertir (BITACORA, «La moneda»: Salvador decidio
        # que eso espere). Una lista en otra moneda --Amazon, en dolares--
        # se dice y no se lee hasta que Centauro sepa convertir.
        if moneda != moneda_del_pais.get(pais_id):
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
            recurso.append({**fila, "perfil_id": perfil,
                            "precio_hora_extra": (extra["precio"]
                                                  if extra and modalidad.aplica_horas_extra
                                                  else None)})
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
    ahora = _utc()
    datos = _leer_odoo(db, odoo)
    if not ensayo:
        # Los productos nuevos llegan con su sugerencia antes del plan:
        # asi finanzas los ve en la tabla aunque todavia no pongan precio.
        leer_productos(db, odoo, datos["referenciados"], ahora)
    plan = _plan(db, datos, ahora.date())
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
    for cliente_id, lista_id in sorted(plan["lista_de"].items()):
        cliente = plan["clientes"][cliente_id]
        actual = cliente.tarifario.odoo_id if cliente.tarifario else None
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
        if lista_id != actual and (lista_id is None or lista_id in leidas):
            implantados.append({"cliente_id": cliente_id, "cliente": cliente.nombre,
                                "lista_id": lista_id})

    generales = [l for l in listas_informe if l["general"]]
    informe = {
        "ensayo": ensayo,
        "leidas": plan["leidas"],
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

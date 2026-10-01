# -*- coding: utf-8 -*-
"""La factura del eventual en Odoo: la prefactura en borrador (seccion 116).

Decision de Salvador (1 oct): al dar el visto bueno, Connect manda a Odoo
una factura de cliente en borrador y el facturista la revisa, la confirma
y la timbra alla. «Nunca action_post ni timbrar: eso lo hace el
facturista.» Connect tampoco la cambia despues ni la borra.

Tres piezas. En la entrega 1 nadie las llama desde el visto bueno: solo
el programa que revisa Odoo (`reconocer_facturacion.py`), que no escribe.

* **La conexion que solo crea borradores** (`Conexion`). Lee como la de
  siempre y le agrega una sola cosa: crear UNA factura de cliente
  (`account.move`, `out_invoice`) con los campos de `CAMPOS` y renglones
  con los de `CAMPOS_RENGLON`. Ni `state`, ni `name`, ni contexto: con un
  `default_state` en el contexto Odoo la crearia confirmada. Cualquier
  otra cosa truena antes de salir a la red. Va con su propia llave,
  ODOO_FACTURACION_API_KEY, para poder cambiarla sin tocar codigo.
* **La prefactura** (`prefactura`): lo que se mandaria, renglon por
  renglon y con el producto de Odoo de cada uno, sin mandarlo; y lo que
  falta para poder mandarla. Suma lo mismo que la factura de siempre
  (`facturacion.armar`): lo ejecutado al tarifario del cliente, o la
  cotizacion tal cual en la cancelacion que se cobra completa, y los
  gastos en su renglon.
* **Mandarla sin duplicar** (`crear`): antes de crear busca en Odoo la
  del mismo servicio; si ya hay una viva --en borrador o timbrada--, no
  crea otra. La cancelada no cuenta: al corregir sale una nueva.

El IVA lo pone Odoo con el impuesto de cada producto, como cuando la hace
el facturista a mano; el diario, el de ventas de siempre; la fecha, la
del dia en que el facturista la confirma.
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import cierre as motor_cierre
from app import models as m
from app import odoo_api, tipo_cambio
from app.config import settings
from app.odoo_tarifarios import es_el_de_gastos

MODELO = "account.move"
TIPO = "out_invoice"
# Lo unico que Connect le pone a la factura. La crea en borrador porque
# asi nace toda factura en Odoo; el folio lo pone Odoo al confirmarla.
CAMPOS = frozenset({"move_type", "partner_id", "ref", "currency_id",
                    "invoice_origin", "invoice_line_ids"})
CAMPOS_RENGLON = frozenset({"product_id", "name", "quantity", "price_unit"})
# La nota del renglon --la cancelacion que se cobra completa--: texto y
# nada mas.
CAMPOS_NOTA = frozenset({"display_type", "name"})
# Preguntarle a Odoo si la llave puede, sin hacer nada.
PREGUNTAS = frozenset({"has_access", "check_access_rights"})
# El documento de origen: asi la encuentra el facturista --el filtro
# «Prefacturas de Connect»-- y asi la busca Connect antes de mandar otra.
ORIGEN = "Connect"

CERO = Decimal("0")
CENTAVO = Decimal("0.01")


def hay_llave() -> bool:
    return bool(settings.odoo_base and settings.odoo_facturacion_api_key)


# ================================================================ la conexion

def _entero(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def es_prefactura(args: dict) -> bool:
    """Si lo que se le pide a Odoo es crear una sola factura de cliente,
    con lo que Connect sabe ponerle y nada mas."""
    if set(args) != {"vals_list"}:
        return False                    # sin contexto: ver arriba
    lista = args["vals_list"]
    if not isinstance(lista, list) or len(lista) != 1:
        return False
    v = lista[0]
    if not isinstance(v, dict) or not set(v) <= CAMPOS:
        return False
    if (v.get("move_type") != TIPO or not _entero(v.get("partner_id"))
            or not _entero(v.get("currency_id"))
            or not isinstance(v.get("ref"), str)
            or not str(v.get("invoice_origin") or "").startswith(ORIGEN)):
        return False
    renglones = v.get("invoice_line_ids")
    if not isinstance(renglones, list) or not renglones:
        return False
    for r in renglones:
        # Solo «crea este renglon» (0, 0, {...}): nada de ligar, cambiar o
        # borrar renglones que ya existan.
        if not (isinstance(r, (list, tuple)) and len(r) == 3
                and r[0] == 0 and r[1] == 0 and isinstance(r[2], dict)):
            return False
        campos = r[2]
        if "display_type" in campos:
            if set(campos) != CAMPOS_NOTA or campos["display_type"] != "line_note":
                return False
        elif not set(campos) <= CAMPOS_RENGLON or not _entero(campos.get("product_id")):
            return False
    return True


class Conexion(odoo_api.Odoo):
    """La conexion de la factura: lee, pregunta si puede, y crea la
    prefactura en borrador. Nada mas: ni confirmar (`action_post`), ni
    cambiar (`write`), ni borrar (`unlink`), ni timbrar."""

    NO_PUEDE = ("no se puede: esta conexion solo lee y crea la prefactura "
                "en borrador")

    def permitido(self, modelo: str, metodo: str, args: dict) -> bool:
        if metodo in odoo_api.LECTURA or metodo in PREGUNTAS:
            return True
        return modelo == MODELO and metodo == "create" and es_prefactura(args)


class Revision(Conexion):
    """La del programa que revisa Odoo: con la llave de la factura, pero
    sin crear nada. Lee y pregunta si podria."""

    NO_PUEDE = "no se puede: el programa que revisa Odoo solo lee"

    def permitido(self, modelo: str, metodo: str, args: dict) -> bool:
        return metodo in odoo_api.LECTURA or metodo in PREGUNTAS


def conexion(clase=Conexion) -> Conexion:
    if not hay_llave():
        raise odoo_api.SinConexion(
            "Falta la llave de la factura (ODOO_FACTURACION_API_KEY) en el "
            ".env del servidor.")
    return clase(settings.odoo_base, settings.odoo_facturacion_api_key,
                 settings.odoo_bd or None, settings.odoo_timeout)


# ================================================================ la prefactura

# Lo que el cliente lee en cada renglon, en el idioma de su cotizacion.
TEXTOS = {
    "es": {"equipo": "Equipo", "fijos": "monto fijo",
           "comprobados": "comprobados, con su desglose",
           "origen": " ({moneda} {importe} al tipo de cambio {tc})",
           "cancelado": "Servicio cancelado: se cobra completo, como se "
                        "autorizó."},
    "en": {"equipo": "Team", "fijos": "fixed amount",
           "comprobados": "as receipted, with their breakdown",
           "origen": " ({moneda} {importe} at an exchange rate of {tc})",
           "cancelado": "Cancelled service: charged in full, as "
                        "authorized."},
    "pt": {"equipo": "Equipe", "fijos": "valor fixo",
           "comprobados": "comprovadas, com o seu detalhamento",
           "origen": " ({moneda} {importe} à taxa de câmbio de {tc})",
           "cancelado": "Serviço cancelado: cobra-se integral, conforme "
                        "autorizado."},
}

# Lo que impide mandarla, dicho para quien lo corrige.
FALTA = {
    "cliente_sin_odoo": "El cliente {cliente} no tiene su ficha en Odoo.",
    "sin_cotizacion": "El servicio no tiene cotización autorizada.",
    "sin_precio": "{texto}",
    "sin_producto": "«{que}»: su precio no salió de un producto de Odoo; "
                    "la lista del cliente se capturó a mano en Connect.",
    "producto_por_leer": "«{que}»: todavía no se sabe con qué producto de "
                         "Odoo se cobra; lo trae la lectura de los "
                         "tarifarios.",
    "sin_variante": "«{producto}»: todavía no se sabe con qué variante de "
                    "Odoo se cobra; la trae la lectura de los tarifarios.",
    "varias_variantes": "«{producto}»: en Odoo tiene {variantes} variantes "
                        "y no se sabe con cuál se cobra.",
    "sin_producto_gastos": "No está en la tabla de productos «{producto}», "
                           "con el que se facturan los gastos.",
    "varios_de_gastos": "Hay {n} productos «{producto}» en la tabla y no se "
                        "sabe con cuál se facturan los gastos.",
    "sin_tipo_de_cambio": "{texto}",
    "no_cuadra": "Los renglones suman {suma} y el servicio {total}.",
}

# El orden de los renglones de un dia: lo que va junto primero y la hora
# extra al final, como en el cierre.
ORDEN = {"paquete": 0, "recurso": 1, "vehiculo": 2, "horas_extra": 3}


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


class _Faltan:
    """Lo que falta, una vez cada cosa: un producto sin variante en diez
    dias es una sola correccion."""

    def __init__(self):
        self.lista, self._vistos = [], set()

    def __call__(self, clave: str, **datos):
        llave = (clave, tuple(sorted((k, str(v)) for k, v in datos.items())))
        if llave in self._vistos:
            return
        self._vistos.add(llave)
        self.lista.append({"clave": clave, **datos,
                           "texto": FALTA[clave].format(**datos)})


def _fecha(iso: str) -> str:
    """«2026-10-28» → «28/10/2026», como se lee en Mexico."""
    a, mes, d = iso.split("-")
    return f"{d}/{mes}/{a}"


def _producto_de_la_linea(db: Session, tarifario_id: int | None,
                          linea: m.LineaCotizacion) -> int | None:
    """El producto de Odoo del precio de un renglon de la cotizacion: el
    de su lista, para la cancelacion que se cobra completa."""
    if not tarifario_id:
        return None
    if linea.tipo == m.TipoLinea.RECURSO:
        fila = (db.query(m.TarifaRecurso)
                .filter_by(tarifario_id=tarifario_id, perfil_id=linea.perfil_id,
                           modalidad_id=linea.modalidad_id).first())
    elif linea.tipo == m.TipoLinea.VEHICULO:
        fila = (db.query(m.TarifaVehiculo)
                .filter_by(tarifario_id=tarifario_id,
                           categoria_id=linea.categoria_id,
                           modalidad_id=linea.modalidad_id).first())
    else:
        fila = (db.query(m.TarifaPaquete)
                .filter_by(tarifario_id=tarifario_id, perfil_id=linea.perfil_id,
                           categoria_id=linea.categoria_id,
                           modalidad_id=linea.modalidad_id).first())
    return fila.producto_odoo_id if fila else None


def producto_de_gastos(db: Session) -> tuple:
    """(producto, lo que falta) con que se facturan los gastos: el de la
    tabla que se llama como `odoo_producto_gastos`."""
    nombre = settings.odoo_producto_gastos
    todos = [p for p in db.query(m.ProductoOdoo).order_by(m.ProductoOdoo.id)
             if es_el_de_gastos(p.nombre)]
    vivos = [p for p in todos if p.vendible] or todos
    if not vivos:
        return None, ("sin_producto_gastos", {"producto": nombre})
    if len(vivos) > 1:
        return None, ("varios_de_gastos", {"producto": nombre, "n": len(vivos)})
    return vivos[0], None


def prefactura(db: Session, cierre: m.Cierre) -> dict:
    """La prefactura de un eventual tal como se mandaria a Odoo, sin
    mandarla. `faltan` vacio: se puede mandar.

    Un renglon por dia, equipo y lo que se cobra --el paquete, el rol o
    la unidad--, con el producto de Odoo de su precio en la lista del
    cliente; la hora extra en su renglon, con el producto de la de su
    rol; y los gastos en uno solo.
    """
    from app import cotizacion as cot
    from app.cotizacion_pdf import MODALIDAD

    if cierre.contrato_id:
        raise ValueError("El mes del implantado se factura como hoy: no va "
                         "a Odoo como prefactura.")
    servicio = cierre.servicio
    cliente = servicio.cliente
    faltan = _Faltan()
    salida = {"cierre_id": cierre.id, "servicio_id": servicio.id,
              "referencia": servicio.folio,
              "origen": f"{ORIGEN} · {servicio.folio}",
              "cliente": {"id": cliente.id if cliente else None,
                          "nombre": cliente.nombre if cliente else None,
                          "odoo_id": cliente.odoo_id if cliente else None},
              "moneda": None, "nota": None, "renglones": [], "total": CERO,
              "faltan": faltan.lista}
    if cliente is None or not cliente.odoo_id:
        faltan("cliente_sin_odoo",
               cliente=cliente.nombre if cliente else "del servicio")
    cotizacion = cot.vigente(db, servicio.id)
    if cotizacion is None:
        faltan("sin_cotizacion")
        return salida
    salida["moneda"] = cotizacion.moneda.value
    idioma = cotizacion.idioma if cotizacion.idioma in TEXTOS else "es"
    textos, modalidades = TEXTOS[idioma], MODALIDAD[idioma]
    productos = {p.id: p for p in db.query(m.ProductoOdoo)}
    lista = (db.get(m.Tarifario, cotizacion.tarifario_id)
             if cotizacion.tarifario_id else None)
    # La lista de Odoo sabe con que producto se cobra cada precio desde la
    # primera lectura; la hora extra, desde la primera de la seccion 116.
    de_odoo = bool(lista and lista.odoo_id)

    def producto(producto_id, que):
        """(variante de Odoo, nombre) del producto de un renglon; si no se
        sabe con cual se cobra, lo dice y deja la variante vacia."""
        p = productos.get(producto_id) if producto_id else None
        if p is None:
            faltan("producto_por_leer" if de_odoo else "sin_producto", que=que)
            return None, que
        if not p.variante_odoo_id:
            if (p.variantes or 0) > 1:
                faltan("varias_variantes", producto=p.nombre,
                       variantes=p.variantes)
            else:
                faltan("sin_variante", producto=p.nombre)
        return p.variante_odoo_id, p.nombre

    renglones = []

    def renglon(tipo, fecha, equipo, detalle, producto_id, que, cantidad,
                precio, importe):
        variante, nombre = producto(producto_id, que)
        partes = [nombre]
        if fecha:
            partes.append(_fecha(fecha))
        if equipo:
            partes.append(f"{textos['equipo']} {equipo}")
        if detalle:
            partes.append(detalle)
        renglones.append({"tipo": tipo, "fecha": fecha, "equipo": equipo,
                          "producto_id": producto_id, "producto": nombre,
                          "variante_odoo_id": variante,
                          "etiqueta": " · ".join(partes),
                          "cantidad": cantidad, "precio": _d(precio),
                          "importe": _d(importe)})

    try:
        if motor_cierre.se_cobra_completo(cierre):
            # La cancelacion que se cobra completa (seccion 105): la
            # cotizacion autorizada tal cual, renglon por renglon, con su
            # nota.
            for linea in sorted(cotizacion.lineas,
                                key=lambda l: (l.fecha, l.equipo_clave, l.id)):
                if linea.tipo == m.TipoLinea.VIATICOS:
                    continue
                codigo = linea.modalidad.codigo.value if linea.modalidad else None
                que = (linea.producto or linea.descripcion
                       or (linea.perfil.nombre if linea.perfil else None)
                       or (linea.categoria.nombre if linea.categoria else "?"))
                renglon(linea.tipo.value, linea.fecha.isoformat(),
                        linea.equipo_clave, modalidades.get(codigo, codigo),
                        _producto_de_la_linea(db, cotizacion.tarifario_id, linea),
                        que, linea.cantidad, linea.precio_unitario,
                        linea.subtotal)
            total_servicio = (_d(cotizacion.total)
                              - motor_cierre.gastos_cotizados(cotizacion))
            salida["nota"] = textos["cancelado"]
        else:
            ejecutado = motor_cierre.ejecutado(db, servicio,
                                               cotizacion.tarifario_id,
                                               cot.con_paquetes(db, cotizacion))
            total_servicio = ejecutado["total"]
            base, extra = {}, {}
            for l in ejecutado["detalle"]:
                clave = (l["fecha"], l["equipo"], l["tipo"],
                         str(l["referencia_id"]), l.get("modalidad"),
                         l.get("precio"), l.get("producto_odoo_id"))
                r = base.setdefault(clave, {**l, "cantidad": 0, "importe": CERO})
                r["cantidad"] += l["cantidad"]
                r["importe"] += l["importe"] - (l.get("importe_horas_extra") or CERO)
                if l.get("importe_horas_extra"):
                    clave = (l["fecha"], l["equipo"], l.get("rol_hora_extra"),
                             l.get("precio_hora_extra"),
                             l.get("producto_hora_extra_id"))
                    e = extra.setdefault(clave, {**l, "horas": 0, "importe": CERO})
                    e["horas"] += l.get("horas_extra") or 0
                    e["importe"] += l["importe_horas_extra"]
            filas = ([("base", r) for r in base.values()]
                     + [("extra", e) for e in extra.values()])
            filas.sort(key=lambda x: (x[1]["fecha"], x[1]["equipo"] or "",
                                      ORDEN["horas_extra"] if x[0] == "extra"
                                      else ORDEN.get(x[1]["tipo"], 9),
                                      x[1].get("descripcion") or ""))
            for de, r in filas:
                if de == "base":
                    renglon(r["tipo"], r["fecha"], r["equipo"],
                            modalidades.get(r.get("modalidad"), r.get("modalidad")),
                            r.get("producto_odoo_id"), r.get("descripcion") or "?",
                            r["cantidad"], r["precio"], r["importe"])
                else:
                    renglon("horas_extra", r["fecha"], r["equipo"],
                            f"{r['horas']} h", r.get("producto_hora_extra_id"),
                            f"hora extra · {r.get('rol_hora_extra') or '?'}",
                            r["horas"], r["precio_hora_extra"], r["importe"])
    except HTTPException as error:
        # Sin precio en la lista no hay a cuanto facturar: lo mismo que
        # frena el visto bueno.
        detalle = error.detail
        faltan("sin_precio", texto=(detalle.get("mensaje") if isinstance(detalle, dict)
                                    else str(detalle)))
        return salida

    # Los gastos, en su renglon (seccion 59): a precio alzado, el monto
    # fijo; netos, lo comprobado valido, al tipo de cambio del visto bueno
    # si la cotizacion es de otra moneda (seccion 82).
    try:
        gastos = motor_cierre.viaticos_por_cobrar(db, servicio.id, cotizacion)
    except HTTPException as error:
        detalle = error.detail
        faltan("sin_tipo_de_cambio",
               texto=(detalle.get("mensaje") if isinstance(detalle, dict)
                      else str(detalle)))
        gastos = None
    if gastos:
        de_gastos, falta = producto_de_gastos(db)
        if falta:
            faltan(falta[0], **falta[1])
        modo = textos["fijos" if cotizacion.viaticos_incluidos else "comprobados"]
        otra, tc = motor_cierre.tipo_de_cambio_de_gastos(db, servicio, cotizacion)
        if otra and tc and not cotizacion.viaticos_incluidos:
            local = tipo_cambio.local_del_pais(db, servicio.pais_id)
            pesos = motor_cierre.viaticos_por_cobrar_local(db, servicio.id,
                                                           cotizacion)
            modo += textos["origen"].format(
                moneda=local.value if local else "", importe=f"{pesos:,.2f}",
                tc=tipo_cambio.corto(tipo_cambio.texto(tc["tasa"])))
        nombre = de_gastos.nombre if de_gastos else settings.odoo_producto_gastos
        variante = de_gastos.variante_odoo_id if de_gastos else None
        if de_gastos and not variante:
            if (de_gastos.variantes or 0) > 1:
                faltan("varias_variantes", producto=nombre,
                       variantes=de_gastos.variantes)
            else:
                faltan("sin_variante", producto=nombre)
        renglones.append({"tipo": "gastos", "fecha": None, "equipo": None,
                          "producto_id": de_gastos.id if de_gastos else None,
                          "producto": nombre, "variante_odoo_id": variante,
                          "etiqueta": f"{nombre} · {servicio.folio} · {modo}",
                          "cantidad": 1, "precio": _d(gastos),
                          "importe": _d(gastos)})

    salida["renglones"] = renglones
    salida["total"] = sum((r["importe"] for r in renglones), CERO)
    # Lo mismo que la factura de siempre: si no cuadra, algo se perdio en
    # el camino y no se manda.
    esperado = total_servicio + (gastos or CERO)
    if gastos is not None and salida["total"] != esperado:
        faltan("no_cuadra", suma=f"{salida['total']:,.2f}",
               total=f"{esperado:,.2f}")
    for r in renglones:
        if r["precio"] * r["cantidad"] != r["importe"]:
            faltan("no_cuadra", suma=f"{r['importe']:,.2f}",
                   total=f"{r['precio'] * r['cantidad']:,.2f}")
    return salida


# ================================================================ a Odoo

def valores(pre: dict, moneda_id: int) -> dict:
    """La factura de cliente en borrador, como la recibe Odoo. Solo con lo
    que deja pasar `es_prefactura`."""
    if pre["faltan"]:
        raise ValueError("A esta prefactura le falta algo: no se manda.")
    lineas = [[0, 0, {"product_id": r["variante_odoo_id"],
                      "name": r["etiqueta"],
                      "quantity": float(r["cantidad"]),
                      "price_unit": float(r["precio"])}]
              for r in pre["renglones"]]
    if pre.get("nota"):
        lineas.insert(0, [0, 0, {"display_type": "line_note",
                                 "name": pre["nota"]}])
    return {"move_type": TIPO, "partner_id": pre["cliente"]["odoo_id"],
            "ref": pre["referencia"], "currency_id": moneda_id,
            "invoice_origin": pre["origen"], "invoice_line_ids": lineas}


def moneda_de(odoo, codigo: str) -> int | None:
    """El id de la moneda en Odoo --«MXN», «USD»--, si esta activa. Una
    factura en una moneda apagada Odoo no la acepta."""
    filas = odoo.leer("res.currency", [["name", "=", codigo]],
                      ["name", "active"], archivados=True)
    activas = [f["id"] for f in filas if f.get("active")]
    return activas[0] if len(activas) == 1 else None


def buscar(odoo, origen: str) -> list:
    """Las facturas de cliente de Odoo que salieron de ese servicio."""
    return odoo.leer(MODELO, [["move_type", "=", TIPO],
                              ["invoice_origin", "=", origen]],
                     ["name", "state", "ref", "amount_untaxed", "currency_id"])


def crear(odoo: Conexion, pre: dict, moneda_id: int) -> dict:
    """Manda la prefactura sin duplicar: si en Odoo ya hay una viva del
    mismo servicio --en borrador o timbrada-- no crea otra. La cancelada
    no cuenta: al corregir el servicio sale una nueva, con la misma
    referencia."""
    vals = valores(pre, moneda_id)
    vivas = [f for f in buscar(odoo, pre["origen"]) if f.get("state") != "cancel"]
    if vivas:
        return {"id": vivas[0]["id"], "nueva": False,
                "estado": vivas[0].get("state")}
    ids = odoo.llamar(MODELO, "create", vals_list=[vals])
    nuevo = ids[0] if isinstance(ids, list) else ids
    return {"id": int(nuevo), "nueva": True, "estado": "draft"}

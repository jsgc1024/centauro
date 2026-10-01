# -*- coding: utf-8 -*-
"""Lo que hay que mirar en Odoo antes de mandarle la prefactura del
eventual (seccion 116). De SOLO LECTURA.

Responde desde el propio Odoo, con la llave de la factura, lo que el
proyecto «La factura del eventual en Odoo» dejo por ver:

  1. Que la llave entre y pueda crear facturas de cliente --sin crear
     ninguna: se le pregunta a Odoo si podria--.
  2. Como se llaman en este Odoo el UUID del CFDI y el estado del timbre,
     y si se puede leer el historial de la factura, que es de donde sale
     quien la timbro.
  3. El diario de ventas, y MXN y USD activas.
  4. El producto «Gastos de Operación (Viáticos)», las variantes de los
     productos de PE y el producto de la hora extra de cada lista.
  5. Los clientes de Connect con lo que pide el CFDI: RFC, codigo postal
     y regimen fiscal.
  6. El filtro «Prefacturas de Connect» y las facturas que hoy ya llevan
     el folio del servicio.
  7. La prefactura de los ultimos eventuales con visto bueno, en ensayo:
     lo que se mandaria y lo que le falta. No se manda.

Lo que NO hace, y esta amarrado en el codigo:
  * No escribe en Odoo: usa `odoo_facturacion.Revision`, que solo lee y
    pregunta; si alguien le pide crear, truena antes de salir a la red.
  * No guarda nada en Connect: nunca hace commit.
  * No imprime la llave.

En el servidor, con la aplicacion ya actualizada:

    docker compose -f docker-compose.prod.yml run --rm api python reconocer_facturacion.py
"""
import sys
from decimal import Decimal

from app import models as m
from app import odoo_api, odoo_facturacion
from app.config import settings
from app.db import SessionLocal
from app.odoo_tarifarios import es_el_de_gastos

# Los campos de la factura con que trabaja Connect: los que manda y los
# que lee de vuelta.
CAMPOS_FACTURA = ["move_type", "partner_id", "ref", "currency_id",
                  "invoice_origin", "invoice_line_ids", "journal_id", "state",
                  "name", "amount_untaxed", "amount_total", "invoice_date",
                  "payment_state"]
CAMPOS_RENGLON = ["product_id", "name", "quantity", "price_unit",
                  "display_type", "tax_ids"]
# Lo que el CFDI le pide a la ficha del cliente.
CAMPOS_FISCALES = ["vat", "zip", "country_id"]
ULTIMOS = 8


def titulo(texto: str) -> None:
    print(f"\n== {texto}")


def bien(texto: str) -> None:
    print(f"  ok  {texto}")


def mal(texto: str) -> None:
    print(f"  !!  {texto}")


def nota(texto: str) -> None:
    print(f"      {texto}")


def _nombre(valor) -> str:
    """El nombre de un many2one ([id, nombre])."""
    if isinstance(valor, (list, tuple)) and len(valor) > 1:
        return str(valor[1])
    return "—" if valor in (False, None) else str(valor)


def puede(odoo, modelo: str, operacion: str) -> tuple:
    """(si/no/None, como se supo) que la llave pueda hacer `operacion` en
    `modelo`. Se le pregunta a Odoo; no se intenta."""
    ultimo = None
    for metodo, args in (("has_access", {"operation": operacion}),
                         ("check_access_rights", {"operation": operacion,
                                                  "raise_exception": False})):
        try:
            return bool(odoo.llamar(modelo, metodo, **args)), metodo
        except odoo_api.NoResponde as error:
            ultimo = error
    return None, str(ultimo)


def la_llave(odoo) -> bool:
    titulo("1. La llave de la factura")
    misma = settings.odoo_facturacion_api_key == settings.odoo_api_key
    bien("ODOO_FACTURACION_API_KEY puesta"
         + (" (la misma que ODOO_API_KEY)" if misma else
            " (distinta de ODOO_API_KEY)"))
    try:
        odoo.leer("res.currency", [["name", "=", "MXN"]], ["name"],
                  archivados=True)
    except odoo_api.NoResponde as error:
        mal(f"La llave no entra a Odoo: {error}")
        return False
    bien(f"La llave entra a Odoo ({odoo.base})")
    for modelo, operacion, para in (
            ("account.move", "create", "crear la prefactura"),
            ("account.move", "read", "leerla de vuelta"),
            ("account.move.line", "create", "crear sus renglones"),
            ("mail.message", "read", "leer su historial (quien la timbro)"),
            ("mail.tracking.value", "read", "leer los cambios de estado")):
        si, como = puede(odoo, modelo, operacion)
        if si is None:
            mal(f"No se pudo saber si puede {para} ({modelo}): {como}")
        elif si:
            bien(f"Puede {para} ({modelo}, {operacion})")
        else:
            mal(f"NO puede {para} ({modelo}, {operacion})")
    return True


def la_factura(odoo) -> None:
    titulo("2. La factura de cliente en este Odoo")
    campos = odoo.campos("account.move", ["string", "type", "selection"])
    faltan = [c for c in CAMPOS_FACTURA if c not in campos]
    if faltan:
        mal("La factura no tiene: " + ", ".join(faltan))
    else:
        bien(f"La factura tiene los {len(CAMPOS_FACTURA)} campos con que "
             "trabaja Connect")
    estados = campos.get("state", {}).get("selection") or []
    nota("Estados: " + ", ".join(f"{k} ({v})" for k, v in estados))
    renglon = odoo.campos("account.move.line", ["string", "type", "selection"])
    faltan = [c for c in CAMPOS_RENGLON if c not in renglon]
    if faltan:
        mal("El renglon no tiene: " + ", ".join(faltan))
    else:
        bien("El renglon tiene producto, descripcion, cantidad, precio e "
             "impuestos")
    tipos = [k for k, _ in renglon.get("display_type", {}).get("selection") or []]
    (bien if "line_note" in tipos else mal)(
        "Renglon de nota (line_note): " + ("si" if "line_note" in tipos
                                           else "no; tipos: " + ", ".join(tipos)))
    # El CFDI: de Mexico, los campos l10n_mx_edi_*.
    del_cfdi = sorted(c for c in campos if c.startswith("l10n_mx_edi"))
    if not del_cfdi:
        mal("No hay campos del CFDI (l10n_mx_edi_*) en la factura")
        return
    bien(f"Campos del CFDI en la factura: {len(del_cfdi)}")
    for c in del_cfdi:
        f = campos[c]
        texto = f"{(f.get('string') or '').lower()} {c}"
        if any(x in texto for x in ("uuid", "folio fiscal", "fiscal folio",
                                    "state", "estado", "status", "sat",
                                    "cfdi", "timbr", "stamp")):
            valores = f.get("selection") or []
            nota(f"{c} · {f.get('type')} · «{f.get('string')}»"
                 + (" · " + ", ".join(k for k, _ in valores) if valores else ""))


def diario_y_monedas(odoo) -> None:
    titulo("3. El diario de ventas y las monedas")
    diarios = odoo.leer("account.journal", [["type", "=", "sale"]],
                        ["name", "code", "currency_id", "active"],
                        archivados=True)
    activos = [d for d in diarios if d.get("active", True)]
    if not activos:
        mal("No hay diario de ventas activo")
    for d in diarios:
        (bien if d.get("active", True) else nota)(
            f"Diario de ventas «{d.get('name')}» ({d.get('code')}), moneda "
            f"{_nombre(d.get('currency_id'))}"
            + ("" if d.get("active", True) else ", archivado"))
    if len(activos) > 1:
        nota("Hay varios: Odoo usa el primero de la lista, como cuando la "
             "factura se hace a mano.")
    for codigo in ("MXN", "USD"):
        moneda = odoo_facturacion.moneda_de(odoo, codigo)
        (bien if moneda else mal)(
            f"{codigo}: " + (f"activa (id {moneda})" if moneda
                             else "no esta activa en Odoo"))


def productos(odoo, db) -> None:
    titulo("4. Los productos de la factura")
    nombre = settings.odoo_producto_gastos
    # Por su primera palabra: Odoo compara con acentos, y «Operacion» sin
    # acento no saldria buscando «Operación».
    clave = (nombre.split() or [nombre])[0]
    en_odoo = odoo.leer("product.template", [["name", "ilike", clave]],
                        ["name", "categ_id", "sale_ok", "active",
                         "product_variant_count", "taxes_id"], archivados=True)
    exactos = [p for p in en_odoo if es_el_de_gastos(p)]
    if not exactos:
        mal(f"En Odoo no esta «{nombre}»"
            + (": se parecen " + ", ".join(f"«{p['name']}»" for p in en_odoo[:8])
               if en_odoo else ""))
    impuestos = {}
    ids = sorted({i for p in exactos for i in (p.get("taxes_id") or [])})
    if ids:
        impuestos = {t["id"]: t.get("name") for t in odoo.leer(
            "account.tax", [["id", "in", ids]], ["name"], archivados=True)}
    for p in exactos:
        bien(f"«{p['name']}» en Odoo (#{p['id']}): categoria "
             f"{_nombre(p.get('categ_id'))}, "
             f"{'se vende' if p.get('sale_ok') else 'NO se vende'}"
             f"{'' if p.get('active', True) else ', archivado'}, "
             f"{p.get('product_variant_count')} variante(s), impuestos: "
             + (", ".join(impuestos.get(i, f"#{i}") for i in p.get("taxes_id") or [])
                or "ninguno"))
    de_gastos, falta = odoo_facturacion.producto_de_gastos(db)
    if de_gastos:
        (bien if de_gastos.variante_odoo_id else mal)(
            f"En la tabla de Connect: «{de_gastos.nombre}»"
            + (f", variante {de_gastos.variante_odoo_id}"
               if de_gastos.variante_odoo_id else
               ", todavia sin su variante: la trae la lectura de los "
               "tarifarios de cada hora"))
    else:
        mal(odoo_facturacion.FALTA[falta[0]].format(**falta[1])
            + " Entra con la lectura de los tarifarios de cada hora.")

    con_precio = ("rol", "unidad", "paquete", "hora_extra")
    tabla = (db.query(m.ProductoOdoo)
             .filter(m.ProductoOdoo.confirmado.is_(True),
                     m.ProductoOdoo.vendible.is_(True),
                     m.ProductoOdoo.clase.in_(con_precio)).all())
    una = [p for p in tabla if p.variante_odoo_id]
    varias = [p for p in tabla if (p.variantes or 0) > 1]
    sin_leer = [p for p in tabla if p.variantes is None]
    (bien if len(una) == len(tabla) else nota)(
        f"Productos de PE con precio: {len(tabla)}; con su variante: "
        f"{len(una)}")
    for p in varias:
        mal(f"«{p.nombre}» tiene {p.variantes} variantes en Odoo: no se sabe "
            "con cual cobrar")
    if sin_leer:
        nota(f"{len(sin_leer)} todavia sin leer su variante: la trae la "
             "lectura de los tarifarios de cada hora")

    # La hora extra de cada lista de Odoo, con su producto.
    de_odoo = (db.query(m.Tarifario)
               .filter(m.Tarifario.odoo_id.isnot(None),
                       m.Tarifario.activo.is_(True)).all())
    ids = [t.id for t in de_odoo]
    sin_producto = (db.query(m.TarifaRecurso)
                    .filter(m.TarifaRecurso.tarifario_id.in_(ids),
                            m.TarifaRecurso.precio_hora_extra.isnot(None),
                            m.TarifaRecurso.producto_hora_extra_id.is_(None))
                    .count()) if ids else 0
    generales = sum(1 for t in de_odoo if t.precio_hora_extra
                    and not t.producto_hora_extra_id)
    if sin_producto or generales:
        nota(f"Hora extra sin su producto todavia: {sin_producto} precio(s) "
             f"de rol y {generales} de lista; los trae la lectura de los "
             "tarifarios de cada hora")
    else:
        bien("La hora extra de cada lista ya sabe con que producto se cobra")


def clientes(odoo, db) -> None:
    titulo("5. Los clientes, con lo que pide el CFDI")
    suyos = (db.query(m.Cliente)
             .filter(m.Cliente.odoo_id.isnot(None), m.Cliente.activo.is_(True))
             .order_by(m.Cliente.nombre).all())
    sin_odoo = (db.query(m.Cliente)
                .filter(m.Cliente.odoo_id.is_(None), m.Cliente.activo.is_(True))
                .count())
    if sin_odoo:
        nota(f"{sin_odoo} cliente(s) de Connect sin ficha en Odoo: no se les "
             "puede mandar la prefactura")
    if not suyos:
        mal("Ningun cliente de Connect tiene su ficha en Odoo")
        return
    campos = odoo.campos("res.partner", ["string", "type"])
    regimen = next((c for c in campos if "fiscal_regime" in c), None)
    pedir = CAMPOS_FISCALES + ([regimen] if regimen else [])
    fichas = {f["id"]: f for f in odoo.leer(
        "res.partner", [["id", "in", [c.odoo_id for c in suyos]]], pedir,
        archivados=True)}
    faltas = {"RFC": [], "codigo postal": [], "regimen fiscal": [],
              "ficha (archivada o borrada)": []}
    for c in suyos:
        f = fichas.get(c.odoo_id)
        if f is None:
            faltas["ficha (archivada o borrada)"].append(c.nombre)
            continue
        if not f.get("vat"):
            faltas["RFC"].append(c.nombre)
        if not f.get("zip"):
            faltas["codigo postal"].append(c.nombre)
        if regimen and not f.get(regimen):
            faltas["regimen fiscal"].append(c.nombre)
    bien(f"Clientes de Connect con ficha en Odoo: {len(suyos)}")
    if not regimen:
        nota("La ficha del cliente no tiene campo de regimen fiscal "
             "(l10n_mx_edi_fiscal_regime)")
    for que, quienes in faltas.items():
        if quienes:
            mal(f"Sin {que}: {len(quienes)} — " + ", ".join(quienes[:12])
                + (" …" if len(quienes) > 12 else ""))


def filtro_y_folios(odoo) -> None:
    titulo("6. El filtro del facturista y las facturas de hoy")
    try:
        filtros = odoo.leer("ir.filters", [["model_id", "=", "account.move"]],
                            ["name", "domain", "user_id"])
        suyo = [f for f in filtros if "connect" in (f.get("name") or "").lower()]
        if suyo:
            for f in suyo:
                bien(f"Filtro «{f['name']}»: {f.get('domain')}")
        else:
            nota("Todavia no esta el filtro «Prefacturas de Connect» "
                 "(Documento origen contiene «Connect»): se hace en Odoo")
    except odoo_api.NoResponde as error:
        nota(f"No se pudieron leer los filtros: {error}")
    con_folio = odoo.leer("account.move", [["move_type", "=", "out_invoice"],
                                           ["ref", "ilike", "EP/"]],
                          ["state"])
    por_estado = {}
    for f in con_folio:
        por_estado[f.get("state")] = por_estado.get(f.get("state"), 0) + 1
    nota(f"Facturas de cliente que ya llevan un folio de Connect en la "
         f"referencia: {len(con_folio)}"
         + (" (" + ", ".join(f"{k}: {v}" for k, v in sorted(por_estado.items()))
            + ")" if por_estado else ""))
    de_connect = odoo.leer("account.move", [["invoice_origin", "ilike",
                                             odoo_facturacion.ORIGEN]],
                           ["state"])
    nota(f"Facturas con documento origen «{odoo_facturacion.ORIGEN}»: "
         f"{len(de_connect)}")


def ensayo(db) -> None:
    titulo(f"7. La prefactura de los ultimos {ULTIMOS} eventuales con visto "
           "bueno (ensayo: no se manda)")
    cierres = (db.query(m.Cierre)
               .filter(m.Cierre.contrato_id.is_(None),
                       m.Cierre.estatus.in_((m.EstatusCierre.ENVIADO_FINANZAS,
                                             m.EstatusCierre.APROBADO,
                                             m.EstatusCierre.FACTURADO)))
               .order_by(m.Cierre.enviado_en.desc().nullslast())
               .limit(ULTIMOS).all())
    if not cierres:
        nota("Todavia no hay eventuales con visto bueno")
        return
    muestra = None
    for c in cierres:
        try:
            pre = odoo_facturacion.prefactura(db, c)
        except Exception as error:                      # noqa: BLE001
            mal(f"{c.servicio.folio}: no se pudo armar: {error}")
            continue
        visto = Decimal(str(c.total_ejecutado or 0))
        cuadra = pre["total"] == visto
        (bien if not pre["faltan"] and cuadra else mal)(
            f"{pre['referencia']} · {pre['cliente']['nombre']} · "
            f"{len(pre['renglones'])} renglones · {pre['total']:,.2f}"
            + (f" {pre['moneda']}" if pre["moneda"] else "")
            + ("" if cuadra else f" · el visto bueno dijo {visto:,.2f}")
            + (f" · factura {c.factura_odoo}" if c.factura_odoo else ""))
        for f in pre["faltan"]:
            nota(f"falta: {f['texto']}")
        if muestra is None and not pre["faltan"]:
            muestra = pre
    if muestra:
        print(f"\n   Asi llegaria la de {muestra['referencia']} "
              f"(origen «{muestra['origen']}»):")
        if muestra.get("nota"):
            nota(f"nota: {muestra['nota']}")
        for r in muestra["renglones"][:10]:
            nota(f"[{r['variante_odoo_id']}] {r['etiqueta']} · "
                 f"{r['cantidad']} × {r['precio']:,.2f} = {r['importe']:,.2f}")
        if len(muestra["renglones"]) > 10:
            nota(f"… y {len(muestra['renglones']) - 10} renglones mas")


def main() -> int:
    print("Reconocimiento de la factura del eventual en Odoo (seccion 116). "
          "Solo lee: no escribe en Odoo ni en Connect.")
    if not settings.odoo_base:
        mal("Falta ODOO_BASE en el .env")
        return 1
    if not settings.odoo_facturacion_api_key:
        mal("Falta ODOO_FACTURACION_API_KEY en el .env del servidor")
        return 1
    odoo = odoo_facturacion.conexion(odoo_facturacion.Revision)
    if not la_llave(odoo):
        return 1
    db = SessionLocal()
    try:
        for paso in (lambda: la_factura(odoo), lambda: diario_y_monedas(odoo),
                     lambda: productos(odoo, db), lambda: clientes(odoo, db),
                     lambda: filtro_y_folios(odoo), lambda: ensayo(db)):
            try:
                paso()
            except Exception as error:                  # noqa: BLE001
                mal(f"Este paso no termino: {error}")
                db.rollback()
    finally:
        db.rollback()
        db.close()
    print("\nListo. No se escribio nada en Odoo ni en Connect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""El desglose de gastos que se le manda al cliente.

Decision de Salvador, 23 de septiembre (seccion 59). Hay clientes que
pagan los gastos netos: al final se les manda el desglose de lo que se
gasto, con sus comprobantes. Hasta hoy eso se armaba a mano; aqui sale
del sistema, con los mismos numeros que la factura.

Solo van los gastos comprobados validos del servicio --o del mes, en el
implantado--: lo rechazado no es gasto del servicio y lo que se desconto
al personal tampoco se le cobra al cliente. Cada gasto con su fecha, su
concepto y su comprobante; el total por concepto; y al final las copias
de los comprobantes.

Va en el idioma del cliente: el de quien solicita el servicio, o el de
su pais. Solo se traducen las etiquetas; lo que escribio la persona en
su ticket queda como lo escribio.
"""
import html as _html
from collections import OrderedDict
from datetime import date
from decimal import Decimal

from app import models as m
from app.marca import logo_incrustado

LINEA = "AI/EP"
CERO = Decimal("0")

TEXTOS = {
    "es": {
        "titulo": "Desglose de gastos",
        "cliente": "Cliente", "servicio": "Servicio", "factura": "Factura",
        "linea": "Protección ejecutiva",
        "fecha": "Fecha", "concepto": "Concepto",
        "comprobante": "Comprobante", "importe": "Importe",
        "total": "Total de gastos",
        "nota": ("Solo van gastos comprobados del servicio. Las copias de "
                 "los comprobantes van anexas."),
        "copias": "Copias de los comprobantes",
        "sin_gastos": "Este servicio no tiene gastos comprobados.",
        "imprimir": "Imprimir o guardar como PDF",
        "tipo": {"factura": "Factura", "nota": "Ticket"},
        "conceptos": {"alimentos": "Alimentos", "hospedaje": "Hospedaje",
                      "combustible": "Gasolina", "casetas": "Casetas",
                      "traslado_personal": "Traslado del personal",
                      "otros": "Otros"},
        "dias": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
        "dias_largos": ["lunes", "martes", "miércoles", "jueves", "viernes",
                        "sábado", "domingo"],
        "meses": ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                  "julio", "agosto", "septiembre", "octubre", "noviembre",
                  "diciembre"],
        "meses_cortos": ["ene", "feb", "mar", "abr", "may", "jun", "jul",
                         "ago", "sep", "oct", "nov", "dic"],
        "y": "y", "del": "del", "al": "al", "de": "de",
    },
    "en": {
        "titulo": "Expense breakdown",
        "cliente": "Client", "servicio": "Service", "factura": "Invoice",
        "linea": "Executive Protection",
        "fecha": "Date", "concepto": "Item",
        "comprobante": "Receipt", "importe": "Amount",
        "total": "Total expenses",
        "nota": ("Only proven expenses of the service are included. Copies "
                 "of the receipts are attached."),
        "copias": "Copies of the receipts",
        "sin_gastos": "This service has no proven expenses.",
        "imprimir": "Print or save as PDF",
        "tipo": {"factura": "Invoice", "nota": "Receipt"},
        "conceptos": {"alimentos": "Meals", "hospedaje": "Lodging",
                      "combustible": "Fuel", "casetas": "Tolls",
                      "traslado_personal": "Staff transport",
                      "otros": "Other"},
        "dias": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "dias_largos": ["Monday", "Tuesday", "Wednesday", "Thursday",
                        "Friday", "Saturday", "Sunday"],
        "meses": ["January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November",
                  "December"],
        "meses_cortos": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul",
                         "Aug", "Sep", "Oct", "Nov", "Dec"],
        "y": "and", "del": "from", "al": "to", "de": "",
    },
    "pt": {
        "titulo": "Detalhamento de despesas",
        "cliente": "Cliente", "servicio": "Serviço", "factura": "Nota fiscal",
        "linea": "Proteção executiva",
        "fecha": "Data", "concepto": "Item",
        "comprobante": "Comprovante", "importe": "Valor",
        "total": "Total de despesas",
        "nota": ("Somente despesas comprovadas do serviço. As cópias dos "
                 "comprovantes vão anexas."),
        "copias": "Cópias dos comprovantes",
        "sin_gastos": "Este serviço não tem despesas comprovadas.",
        "imprimir": "Imprimir ou salvar como PDF",
        "tipo": {"factura": "Nota fiscal", "nota": "Recibo"},
        "conceptos": {"alimentos": "Alimentação", "hospedaje": "Hospedagem",
                      "combustible": "Combustível", "casetas": "Pedágios",
                      "traslado_personal": "Transporte da equipe",
                      "otros": "Outros"},
        "dias": ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"],
        "dias_largos": ["segunda-feira", "terça-feira", "quarta-feira",
                        "quinta-feira", "sexta-feira", "sábado", "domingo"],
        "meses": ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                  "julho", "agosto", "setembro", "outubro", "novembro",
                  "dezembro"],
        "meses_cortos": ["jan", "fev", "mar", "abr", "mai", "jun", "jul",
                         "ago", "set", "out", "nov", "dez"],
        "y": "e", "del": "de", "al": "a", "de": "de",
    },
}


def idioma_del_cliente(db, servicio: m.Servicio) -> str:
    """El de quien solicita el servicio; si no dijo, el de su pais."""
    if servicio.idioma_solicitante in TEXTOS:
        return servicio.idioma_solicitante
    pais = db.get(m.Pais, servicio.pais_id)
    return pais.idioma if pais and pais.idioma in TEXTOS else "es"


def _esc(valor) -> str:
    return _html.escape(str(valor if valor is not None else ""))


def _dinero(monto: Decimal, moneda: str | None = None) -> str:
    texto = f"${monto:,.2f}"
    return f"{texto} {moneda}" if moneda else texto


def _dia_corto(f: date, t: dict) -> str:
    """"lun 21 sep", "Mon 21 Sep"."""
    return f"{t['dias'][f.weekday()]} {f.day} {t['meses_cortos'][f.month - 1]}"


def _de_mes(f: date, t: dict) -> str:
    """"septiembre de 2026", "September 2026"."""
    if t["de"]:
        return f"{t['de']} {t['meses'][f.month - 1]} {t['de']} {f.year}"
    return f"{t['meses'][f.month - 1]} {f.year}"


def periodo_de(fechas: list, t: dict) -> str:
    """Los dias del servicio en una frase: "lunes 21 y martes 22 de
    septiembre de 2026", "del 21 al 25 de septiembre de 2026"."""
    if not fechas:
        return ""
    fechas = sorted(set(fechas))
    primero, ultimo = fechas[0], fechas[-1]
    largo = t["dias_largos"]
    if len(fechas) == 1:
        return f"{largo[primero.weekday()]} {primero.day} {_de_mes(primero, t)}"
    if len(fechas) == 2 and primero.month == ultimo.month:
        return (f"{largo[primero.weekday()]} {primero.day} {t['y']} "
                f"{largo[ultimo.weekday()]} {ultimo.day} {_de_mes(ultimo, t)}")
    if primero.month == ultimo.month and primero.year == ultimo.year:
        return f"{t['del']} {primero.day} {t['al']} {ultimo.day} {_de_mes(ultimo, t)}"
    return (f"{t['del']} {primero.day} {_de_mes(primero, t)} {t['al']} "
            f"{ultimo.day} {_de_mes(ultimo, t)}")


def gastos(viaticos: list) -> list[dict]:
    """Los gastos comprobados validos, en orden: sin lo rechazado ni el
    dinero cancelado."""
    salida = []
    for v in viaticos:
        if v.estatus == m.EstatusViatico.CANCELADO:
            continue
        fecha = v.jornada.fecha if v.jornada else None
        for c in v.comprobantes:
            if c.rechazado:
                continue
            salida.append({"fecha": fecha, "concepto": c.concepto.value,
                           "descripcion": c.descripcion,
                           "tipo": c.tipo.value, "monto": Decimal(str(c.monto)),
                           "imagen": c.imagen, "subido_en": c.subido_en,
                           "id": c.id})
    salida.sort(key=lambda g: (g["fecha"] or date.min,
                               g["subido_en"].isoformat() if g["subido_en"]
                               else "", g["id"]))
    return salida


def _etiqueta(g: dict, t: dict) -> str:
    """El concepto como se lee: "Otros" con la nota de la persona dice
    que fue ("Estacionamiento"); los demas, su nombre."""
    if g["concepto"] == "otros" and (g["descripcion"] or "").strip():
        return g["descripcion"].strip()
    return t["conceptos"].get(g["concepto"], g["concepto"])


def render(servicio: m.Servicio, plaza: str | None, viaticos: list,
           idioma: str, moneda: str | None, factura: str | None = None,
           periodo: tuple[int, int] | None = None) -> str:
    """El documento completo, listo para imprimir o guardar como PDF."""
    t = TEXTOS.get(idioma, TEXTOS["es"])
    filas = gastos(viaticos)
    if periodo:
        cuando = _de_mes(date(periodo[0], periodo[1], 1), t)
        if t["de"]:
            cuando = cuando[len(t["de"]) + 1:]
    else:
        cuando = periodo_de([v.jornada.fecha for v in viaticos
                             if v.jornada and v.estatus
                             != m.EstatusViatico.CANCELADO]
                            or [j.fecha for e in servicio.equipos
                                for j in e.jornadas
                                if j.estatus != m.EstatusJornada.CANCELADA],
                            t)
    por_concepto: "OrderedDict[str, Decimal]" = OrderedDict()
    for g in filas:
        clave = _etiqueta(g, t)
        por_concepto[clave] = por_concepto.get(clave, CERO) + g["monto"]
    total = sum((g["monto"] for g in filas), CERO)

    logo = logo_incrustado()
    marca = (f'<img class="logo" src="{logo}" alt="Centauro">' if logo
             else '<span class="marca-texto">CENTAURO</span>')
    renglones = "".join(
        f'<tr><td>{_esc(_dia_corto(g["fecha"], t)) if g["fecha"] else ""}</td>'
        f'<td>{_esc(_etiqueta(g, t))}</td>'
        f'<td class="gris">{_esc(t["tipo"].get(g["tipo"], g["tipo"]))}</td>'
        f'<td class="der num">{_dinero(g["monto"])}</td></tr>'
        for g in filas)
    resumen = "".join(
        f'<tr class="resumen"><td class="gris">{_esc(k)}</td>'
        f'<td class="der num">{_dinero(v)}</td></tr>'
        for k, v in por_concepto.items())
    copias = "".join(
        f'<figure><img src="{g["imagen"]}" alt=""><figcaption>'
        f'{_esc(_dia_corto(g["fecha"], t)) if g["fecha"] else ""} · '
        f'{_esc(_etiqueta(g, t))} · {_dinero(g["monto"])}</figcaption></figure>'
        for g in filas if (g["imagen"] or "").startswith("data:image"))
    factura_fila = (f'<b>{t["factura"]}</b><span>{_esc(factura)}</span>'
                    if factura else "")
    cuerpo = (f'''<table><thead><tr><th>{t["fecha"]}</th><th>{t["concepto"]}</th>
<th>{t["comprobante"]}</th><th class="der">{t["importe"]}</th></tr></thead>
<tbody>{renglones}</tbody></table>
<table class="totales"><tbody>{resumen}
<tr class="total"><td>{t["total"]}</td><td class="der num">{_dinero(total, moneda)}</td></tr>
</tbody></table>
<p class="nota">{t["nota"]}</p>''' if filas else
              f'<p class="nota">{t["sin_gastos"]}</p>')

    return f"""<!doctype html>
<html lang="{idioma}"><head><meta charset="utf-8">
<title>{_esc(servicio.folio)} · {t["titulo"]}</title>
<style>
  * {{ box-sizing: border-box; }}
  :root {{ --centauro: #1B1546; --suave: #f0f3f5; }}
  body {{ margin: 0; background: var(--suave); padding: 20px;
         font: 13px/1.45 Inter, -apple-system, "Segoe UI", system-ui, sans-serif;
         color: #1a1d21; }}
  .hoja {{ max-width: 760px; margin: 0 auto 18px; background: #fff;
          border: 1px solid #dfe2e6; border-top: 5px solid var(--centauro);
          border-radius: 8px; padding: 26px 30px 22px; }}
  .marca {{ display: flex; align-items: flex-end; gap: 14px; margin-bottom: 18px; }}
  .logo {{ height: 44px; width: auto; }}
  .marca-texto {{ font-weight: 700; letter-spacing: 3px; color: var(--centauro); }}
  .placa {{ background: var(--centauro); color: #fff; font-weight: 700;
           font-size: 11px; padding: 2px 8px; border-radius: 4px; margin-bottom: 4px; }}
  h1 {{ font-size: 21px; color: var(--centauro); margin: 0 0 4px; }}
  h2 {{ font-size: 15px; color: var(--centauro); margin: 0 0 14px; }}
  .sub {{ color: #78828c; font-size: 13.5px; margin: 0 0 16px; }}
  .ficha {{ display: grid; grid-template-columns: 120px 1fr; gap: 4px 12px;
           font-size: 13px; margin-bottom: 18px; }}
  .ficha b {{ color: #78828c; font-size: 11px; letter-spacing: .6px;
             text-transform: uppercase; font-weight: 650; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; font-size: 10.5px; letter-spacing: .6px;
       text-transform: uppercase; color: #78828c; padding: 8px;
       border-bottom: 1px solid #e0e4e8; background: #fafbfc; }}
  td {{ padding: 8px; border-bottom: 1px solid #f0f2f4; }}
  .der {{ text-align: right; }} .num {{ font-variant-numeric: tabular-nums; }}
  .gris {{ color: #78828c; }}
  .totales {{ margin-top: 14px; }}
  .resumen td {{ border-bottom: 0; padding: 4px 8px; }}
  .total td {{ border-top: 2px solid var(--centauro); font-weight: 700;
              font-size: 14px; padding-top: 10px; }}
  .nota {{ font-size: 12px; color: #78828c; margin: 16px 0 0; line-height: 1.5; }}
  .pie {{ border-top: 1px solid #eef0f2; margin-top: 18px; padding-top: 12px;
         font-size: 11.5px; color: #78828c; }}
  .copias {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  figure {{ margin: 0; break-inside: avoid; }}
  figure img {{ width: 100%; max-height: 420px; object-fit: contain;
               border: 1px solid #e0e4e8; border-radius: 6px; background: #fafbfc; }}
  figcaption {{ font-size: 11.5px; color: #5b646d; margin-top: 4px; }}
  .imprimir {{ max-width: 760px; margin: 0 auto 12px; text-align: right; }}
  .imprimir button {{ font: inherit; font-weight: 600; color: #fff;
                     background: var(--centauro); border: 0; border-radius: 6px;
                     padding: 8px 14px; cursor: pointer; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .hoja {{ border: 0; border-radius: 0; max-width: none; margin: 0; }}
    .anexo {{ break-before: page; }}
    .imprimir {{ display: none; }}
  }}
</style></head><body>
<div class="imprimir"><button onclick="window.print()">{t["imprimir"]}</button></div>
<div class="hoja">
<div class="marca">{marca}<span class="placa">{LINEA}</span></div>
<h1>{t["titulo"]}</h1>
<p class="sub">{_esc(servicio.folio)} · {_esc(cuando)}</p>
<div class="ficha"><b>{t["cliente"]}</b><span>{_esc(servicio.cliente.nombre if servicio.cliente else "")}</span>
<b>{t["servicio"]}</b><span>{t["linea"]}{" · " + _esc(plaza) if plaza else ""}</span>
{factura_fila}</div>
{cuerpo}
<div class="pie">Centauro · {t["linea"]}</div>
</div>
{f'<div class="hoja anexo"><h2>{t["copias"]}</h2><div class="copias">{copias}</div></div>' if copias else ""}
</body></html>"""

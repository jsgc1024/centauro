# -*- coding: utf-8 -*-
"""El PDF de la cotizacion que se le manda al cliente (seccion 114).

El diseno es el de la cotizacion de ejemplo de Salvador (la 01036 de
Henkel), con lo que se le agrego al revisarla:

  * Cada renglon dice su modalidad --sin horario, decision de Salvador--:
    en el ejemplo el mismo renglon valia $3,100 y $8,430 sin decir por que.
  * La ciudad de cada dia, y si es foraneo.
  * Cantidad y precio unitario.
  * Los gastos dichos una sola vez, segun su modo.
  * Subtotal, IVA y total (decision 4).
  * La hora extra de cada rol, de la lista del cliente (seccion 113).
  * Las modalidades con sus horas, de Catalogos.
  * El folio con su version, y la vigencia en un solo lugar.
  * La firma y el contacto del consultor (decision 5), el RFC del
    cliente, la razon social y el RFC de Centauro al pie, y las
    condiciones de pago y facturacion.

Lo arma el servidor con WeasyPrint, con su letra adentro (Inter, en
`app/fuentes`): sale igual en cualquier computadora, y el que se manda se
guarda tal como salio. En espanol, ingles o portugues; los nombres de los
productos van como estan en Odoo.
"""
import html
import re
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app import cotizacion as motor
from app import cotizacion_cliente as cc
from app import marca
from app import models as m
from app import reloj

FUENTES = Path(__file__).parent / "fuentes"

MESES = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
           "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
}
DIAS = {
    "es": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado",
           "Domingo"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
           "Saturday", "Sunday"],
    "pt": ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
           "Sexta-feira", "Sábado", "Domingo"],
}
MODALIDAD = {
    "es": {"transfer": "Transfer", "medio_dia": "Medio día",
           "full_day": "Día completo"},
    "en": {"transfer": "Transfer", "medio_dia": "Half day",
           "full_day": "Full day"},
    "pt": {"transfer": "Transfer", "medio_dia": "Meio período",
           "full_day": "Dia inteiro"},
}
MONEDA = {
    "es": {"MXN": "Pesos mexicanos (MXN)", "USD": "Dólares estadounidenses (USD)",
           "BRL": "Reales brasileños (BRL)", "VES": "Bolívares (VES)"},
    "en": {"MXN": "Mexican pesos (MXN)", "USD": "US dollars (USD)",
           "BRL": "Brazilian reais (BRL)", "VES": "Bolívares (VES)"},
    "pt": {"MXN": "Pesos mexicanos (MXN)", "USD": "Dólares americanos (USD)",
           "BRL": "Reais (BRL)", "VES": "Bolívares (VES)"},
}

T = {
    "es": {
        "confidencial": "El contenido de este documento es confidencial",
        "titulo": "COTIZACIÓN", "borrador": "BORRADOR · todavía no se manda",
        "fecha": "FECHA", "folio": "FOLIO", "version": "Versión",
        "valida": "VÁLIDA HASTA", "moneda": "MONEDA",
        "tipo": "TIPO DE SERVICIO", "cliente": "CLIENTE", "rfc": "RFC",
        "atencion": "Atención", "servicio": "Servicio",
        "modalidad": "Modalidad", "cant": "Cant.",
        "unitario": "Precio unitario", "importe": "Importe",
        "foraneo": "servicio foráneo", "subtotal_dia": "Subtotal del día",
        "servicios": "Servicios", "gastos": "Gastos operativos",
        "g_dentro_corto": "incluidos en el precio de cada renglón",
        "g_fijo_corto": "monto fijo",
        "g_comprobar_corto": "se facturan aparte, según lo comprobado",
        "subtotal": "Subtotal", "iva": "IVA", "total_iva": "Total con IVA",
        "total": "Total", "sin_iva": "Precios sin IVA.",
        "incluye": "Incluye:", "no_incluye": "No incluye:",
        "no_incluye_he": "las horas extra, que se cobran como dice la "
                         "hoja de condiciones.",
        "h_modalidades": "Modalidades", "hasta_h": "hasta {h} horas de "
                                                    "servicio.",
        "h_he": "Horas extra",
        "he_regla": "Solo en día completo: a partir de la hora {h}, por "
                    "hora o fracción, al precio de cada rol.",
        "por_hora": "por hora", "h_gastos": "Gastos operativos",
        "gd": "Incluidos en el precio de cada renglón: no se cobran aparte, "
              "se gaste más o menos.",
        "gf": "Un monto fijo de {m}, se gaste más o menos.",
        "gc": "Se facturan aparte los gastos comprobados, con su desglose.",
        "h_pago": "Condiciones de pago y facturación",
        "h_aceptacion": "Aceptación", "h_cancelacion": "Cancelación",
        "h_vigencia": "Vigencia",
        "vigencia": "Estos precios son válidos hasta el {f}.",
        "atentamente": "Atentamente", "acepta": "Acepta",
        "firma_cliente": "Nombre, firma y fecha", "pagina": "Página",
        "de": "de",
        "intro": "A solicitud de {quien}, de {cliente}, presentamos la "
                 "cotización {del_tipo}{fechas}, en {lugares}.",
        "del_tipo": "del servicio de {tipo} ", "del_servicio": "del servicio ",
        "y": "y", "fechas_un_dia": "el {d}", "fechas_mes": "del {a} al {b}",
        "fechas_otro": "del {a} al {b}",
    },
    "en": {
        "confidencial": "The content of this document is confidential",
        "titulo": "QUOTATION", "borrador": "DRAFT · not sent yet",
        "fecha": "DATE", "folio": "REFERENCE", "version": "Version",
        "valida": "VALID UNTIL", "moneda": "CURRENCY",
        "tipo": "TYPE OF SERVICE", "cliente": "CLIENT", "rfc": "Tax ID",
        "atencion": "Attention", "servicio": "Service",
        "modalidad": "Modality", "cant": "Qty.",
        "unitario": "Unit price", "importe": "Amount",
        "foraneo": "out-of-town service", "subtotal_dia": "Day subtotal",
        "servicios": "Services", "gastos": "Operating expenses",
        "g_dentro_corto": "included in the price of each line",
        "g_fijo_corto": "fixed amount",
        "g_comprobar_corto": "invoiced separately, as incurred",
        "subtotal": "Subtotal", "iva": "VAT", "total_iva": "Total with VAT",
        "total": "Total", "sin_iva": "Prices exclude VAT.",
        "incluye": "Includes:", "no_incluye": "Does not include:",
        "no_incluye_he": "overtime, charged as stated on the terms page.",
        "h_modalidades": "Modalities", "hasta_h": "up to {h} hours of "
                                                  "service.",
        "h_he": "Overtime",
        "he_regla": "Full day only: from hour {h} on, per hour or fraction, "
                    "at the rate of each role.",
        "por_hora": "per hour", "h_gastos": "Operating expenses",
        "gd": "Included in the price of each line: not charged separately, "
              "whatever is spent.",
        "gf": "A fixed amount of {m}, whatever is spent.",
        "gc": "Expenses incurred are invoiced separately, with their "
              "breakdown.",
        "h_pago": "Payment and invoicing terms",
        "h_aceptacion": "Approval", "h_cancelacion": "Cancellation",
        "h_vigencia": "Validity",
        "vigencia": "These prices are valid until {f}.",
        "atentamente": "Sincerely", "acepta": "Approved by",
        "firma_cliente": "Name, signature and date", "pagina": "Page",
        "de": "of",
        "intro": "At the request of {quien}, of {cliente}, we present our "
                 "quotation {del_tipo}{fechas}, in {lugares}.",
        "del_tipo": "for {tipo} services ", "del_servicio": "for the service ",
        "y": "and", "fechas_un_dia": "on {d}", "fechas_mes": "from {a} to {b}",
        "fechas_otro": "from {a} to {b}",
    },
    "pt": {
        "confidencial": "O conteúdo deste documento é confidencial",
        "titulo": "COTAÇÃO", "borrador": "RASCUNHO · ainda não enviada",
        "fecha": "DATA", "folio": "REFERÊNCIA", "version": "Versão",
        "valida": "VÁLIDA ATÉ", "moneda": "MOEDA",
        "tipo": "TIPO DE SERVIÇO", "cliente": "CLIENTE", "rfc": "CNPJ/RFC",
        "atencion": "A/C", "servicio": "Serviço",
        "modalidad": "Modalidade", "cant": "Qtd.",
        "unitario": "Preço unitário", "importe": "Valor",
        "foraneo": "serviço fora da cidade", "subtotal_dia": "Subtotal do dia",
        "servicios": "Serviços", "gastos": "Despesas operacionais",
        "g_dentro_corto": "incluídas no preço de cada linha",
        "g_fijo_corto": "valor fixo",
        "g_comprobar_corto": "faturadas à parte, conforme comprovadas",
        "subtotal": "Subtotal", "iva": "Impostos", "total_iva": "Total com impostos",
        "total": "Total", "sin_iva": "Preços sem impostos.",
        "incluye": "Inclui:", "no_incluye": "Não inclui:",
        "no_incluye_he": "as horas extras, cobradas como diz a folha de "
                         "condições.",
        "h_modalidades": "Modalidades", "hasta_h": "até {h} horas de "
                                                   "serviço.",
        "h_he": "Horas extras",
        "he_regla": "Só no dia inteiro: a partir da hora {h}, por hora ou "
                    "fração, ao preço de cada função.",
        "por_hora": "por hora", "h_gastos": "Despesas operacionais",
        "gd": "Incluídas no preço de cada linha: não são cobradas à parte, "
              "gaste-se mais ou menos.",
        "gf": "Um valor fixo de {m}, gaste-se mais ou menos.",
        "gc": "As despesas comprovadas são faturadas à parte, com o seu "
              "detalhamento.",
        "h_pago": "Condições de pagamento e faturamento",
        "h_aceptacion": "Aprovação", "h_cancelacion": "Cancelamento",
        "h_vigencia": "Validade",
        "vigencia": "Estes preços são válidos até {f}.",
        "atentamente": "Atenciosamente", "acepta": "Aprovado por",
        "firma_cliente": "Nome, assinatura e data", "pagina": "Página",
        "de": "de",
        "intro": "A pedido de {quien}, de {cliente}, apresentamos a cotação "
                 "{del_tipo}{fechas}, em {lugares}.",
        "del_tipo": "do serviço de {tipo} ", "del_servicio": "do serviço ",
        "y": "e", "fechas_un_dia": "em {d}", "fechas_mes": "de {a} a {b}",
        "fechas_otro": "de {a} a {b}",
    },
}


# ------------------------------------------------------------- formatos

def _e(texto) -> str:
    return html.escape(str(texto or ""), quote=True)


def fecha_larga(f: date, idioma: str) -> str:
    mes = MESES[idioma][f.month - 1]
    if idioma == "en":
        return f"{mes} {f.day}, {f.year}"
    return f"{f.day} de {mes} de {f.year}"


def _sin_anio(f: date, idioma: str) -> str:
    mes = MESES[idioma][f.month - 1]
    return f"{mes} {f.day}" if idioma == "en" else f"{f.day} de {mes}"


def rango(desde: date, hasta: date, idioma: str) -> str:
    """«del 27 al 29 de septiembre de 2026», «from September 27 to 29,
    2026»."""
    t = T[idioma]
    if desde == hasta:
        return t["fechas_un_dia"].format(d=fecha_larga(desde, idioma))
    if (desde.year, desde.month) == (hasta.year, hasta.month):
        if idioma == "en":
            a = _sin_anio(desde, idioma)
            b = f"{hasta.day}, {hasta.year}"
        else:
            a, b = str(desde.day), fecha_larga(hasta, idioma)
        return t["fechas_mes"].format(a=a, b=b)
    a = (_sin_anio(desde, idioma) if desde.year == hasta.year
         else fecha_larga(desde, idioma))
    return t["fechas_otro"].format(a=a, b=fecha_larga(hasta, idioma))


def dia_largo(f: date, idioma: str) -> str:
    return f"{DIAS[idioma][f.weekday()]} {fecha_larga(f, idioma)}" \
        if idioma != "en" else f"{DIAS[idioma][f.weekday()]}, {fecha_larga(f, idioma)}"


def dinero(valor, moneda: str) -> str:
    v = Decimal(str(valor or 0)).quantize(Decimal("0.01"))
    texto = f"{abs(v):,.2f}"
    if moneda == "BRL":
        texto = texto.replace(",", "_").replace(".", ",").replace("_", ".")
        simbolo = "R$ "
    else:
        simbolo = {"USD": "US$", "VES": "Bs. "}.get(moneda, "$")
    return f"{'-' if v < 0 else ''}{simbolo}{texto}"


def tasa_texto(tasa) -> str:
    return f"{(Decimal(str(tasa)) * 100).normalize():f}%"


def _lista_y(cosas: list[str], idioma: str) -> str:
    cosas = [c for c in dict.fromkeys(cosas) if c]
    if len(cosas) <= 1:
        return "".join(cosas)
    return f"{', '.join(cosas[:-1])} {T[idioma]['y']} {cosas[-1]}"


def producto_limpio(nombre: str | None) -> str | None:
    """«Conductor de Seguridad Bilingüe + CUV (Todo incluido, Transfer)»
    -> «Conductor de Seguridad Bilingüe + CUV»: la modalidad tiene su
    columna y los gastos su renglon."""
    if not nombre:
        return None
    return re.sub(r"\s*\([^)]*\)\s*$", "", nombre).strip() or nombre


def _ascii(texto: str) -> str:
    limpio = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in limpio if unicodedata.category(c) != "Mn")


def dia_de_la_cotizacion(db: Session, cot: m.Cotizacion) -> date:
    """El dia en que se mando, en el pais de la cotizacion; la de un
    borrador, hoy alla. `enviada_en` va en UTC: mandada a las 8 de la
    noche en Mexico ya es el dia siguiente en el reloj del servidor, y el
    PDF salia con la fecha de manana."""
    relojes = reloj.Relojes(db)
    if cot.enviada_en:
        return reloj.ahora_en(relojes.pais(cot.pais_id), cot.enviada_en).date()
    return relojes.hoy(cot.pais_id)


def nombre_del_archivo(db: Session, cot: m.Cotizacion) -> str:
    """Como los de Centauro: fecha, folio, version, cliente y fechas.
    20260930_EP-COT-0001_V1_HENKEL_CAPITAL_27-29SEP.pdf"""
    cuando = dia_de_la_cotizacion(db, cot)
    palabras = re.findall(r"[A-Za-z0-9]+", _ascii(cc.cliente_texto(cot)))
    quien = "_".join(palabras[:2]).upper()[:24] or "CLIENTE"
    fechas = sorted({d.fecha for d in cot.dias})
    dias = ""
    if fechas:
        mes = MESES["es"][fechas[-1].month - 1][:3].upper()
        dias = (f"_{fechas[0].day:02d}{mes}" if fechas[0] == fechas[-1]
                else f"_{fechas[0].day:02d}-{fechas[-1].day:02d}{mes}")
    folio = cc.folio_texto(cot.folio).replace("/", "-")
    return f"{cuando:%Y%m%d}_{folio}_V{cot.version}_{quien}{dias}.pdf"


# ------------------------------------------------------------- los textos

def _textos(db: Session, pais_id: int | None, idioma: str) -> dict:
    datos = cc.textos_de(db, pais_id) if pais_id else None
    if not datos:
        return {"razon_social": None, "rfc": None, "textos": {}}
    textos = {clave: (por_idioma.get(idioma) or "").strip()
              for clave, por_idioma in datos["textos"].items()}
    return {"razon_social": datos["razon_social"], "rfc": datos["rfc"],
            "textos": textos}


def _con_datos(texto: str, cot: m.Cotizacion) -> str:
    """Los huecos que un texto de Catalogos puede traer."""
    consultor = cot.consultor
    return (texto.replace("{folio}", cc.nombre_de(cot))
            .replace("{correo_consultor}", (consultor.correo if consultor
                                            else ""))
            .replace("{consultor}", consultor.nombre if consultor else ""))


def intro_automatica(cot, idioma: str, marcado: bool = True) -> str:
    """La introduccion que Connect escribe con los datos: quien la pide,
    el cliente, el servicio, las fechas y las ciudades. En el PDF lleva
    sus negritas; en la pantalla sale como texto, para que el consultor la
    cambie si quiere. `cot` puede ser una cotizacion guardada o lo que se
    esta armando: solo se leen sus datos."""
    t = T[idioma]
    limpio = _e if marcado else (lambda x: str(x or ""))
    negrita = (lambda x: f"<b>{x}</b>") if marcado else (lambda x: x)
    fechas = sorted({d.fecha for d in cot.dias})
    lugares = []
    for d in sorted(cot.dias, key=lambda x: (x.fecha, cc.orden_de(x.equipo_clave))):
        if d.plaza:
            lugares.append(d.plaza.nombre)
        if d.es_foraneo and d.destino:
            lugares.append(d.destino)
    tipo = (cot.tipo_servicio or "").strip()
    del_tipo = (t["del_tipo"].format(tipo=limpio(tipo[:1].lower() + tipo[1:]))
                if tipo else t["del_servicio"])
    quien = m._nombre_completo(cot.solicitante_nombre,
                               cot.solicitante_apellidos) or "—"
    return t["intro"].format(
        quien=negrita(limpio(quien)),
        cliente=negrita(limpio(cc.cliente_texto(cot))),
        del_tipo=del_tipo,
        fechas=(negrita(rango(fechas[0], fechas[-1], idioma))
                if fechas else ""),
        lugares=limpio(_lista_y(lugares, idioma)) or "—")


def _intro(cot: m.Cotizacion, idioma: str, t: dict) -> str:
    if cot.introduccion:
        return _e(cot.introduccion)
    return intro_automatica(cot, idioma)


# ------------------------------------------------------------- el html

ESTILO = """
@font-face { font-family: Inter; font-weight: 400; src: url("{f}/Inter-Regular.ttf"); }
@font-face { font-family: Inter; font-weight: 600; src: url("{f}/Inter-SemiBold.ttf"); }
@font-face { font-family: Inter; font-weight: 700; src: url("{f}/Inter-Bold.ttf"); }
@font-face { font-family: Inter; font-weight: 800; src: url("{f}/Inter-ExtraBold.ttf"); }
@page {
  size: Letter; margin: 0.62in 0.7in 1.05in 0.7in;
  @top-right { content: "{conf}"; font: 400 7.5pt Inter; color: #555; vertical-align: bottom; padding-bottom: 6px; }
  @bottom-left { content: element(pie); vertical-align: top; }
  @bottom-right { content: "{folio}\\A {pagina} " counter(page) " {de} " counter(pages);
                  white-space: pre; font: 400 8.6pt Inter; color: #1f2233; text-align: right;
                  vertical-align: top; padding-top: 12px; }
}
* { box-sizing: border-box }
body { margin: 0; font-family: Inter, sans-serif; color: #1f2233; font-size: 9.4pt; line-height: 1.38 }
.pie { position: running(pie); border-top: 3px solid #0A0B3E; padding-top: 8px; width: 7.1in }
.pie img { height: 0.34in; vertical-align: middle }
.pie .razon { display: inline-block; vertical-align: middle; margin-left: 12px; font-size: 7.6pt; color: #444; line-height: 1.3 }
.marca { color: #9b2c1b; font-weight: 800; font-size: 8pt; letter-spacing: 1px; margin: 0 0 6px }
.cab { display: flex; justify-content: space-between; align-items: flex-start; gap: 18px }
.izq { width: 3.05in }
.logo { width: 2.7in; margin: 4px 0 18px }
.logo-texto { font-size: 22pt; font-weight: 800; color: #1B1547; letter-spacing: 1px; margin: 4px 0 18px }
.titulo { background: #1B1547; color: #fff; font-weight: 800; letter-spacing: 1.5px; font-size: 18pt; padding: 6px 22px; text-align: center; margin: 0 0 8px }
table.meta { border-collapse: collapse; font-size: 8.2pt; width: 3.5in }
.meta td { border: 1.4px solid #1B1547; padding: 2px 8px }
.meta td.e { background: #D3D0DA; font-weight: 800; text-align: right; color: #1B1547; width: 46%; font-size: 7.4pt; white-space: nowrap }
.meta td.v { text-align: center }
.cliente { border: 1.6px solid #1B1547 }
.cliente .c { background: #1B1547; color: #fff; font-weight: 800; text-align: center; letter-spacing: 1px; padding: 3px; font-size: 9.5pt }
.cliente .n { padding: 9px 12px 2px; font-weight: 700; color: #1B1547; font-size: 10.5pt; text-align: center }
.cliente .a { padding: 0 12px 9px; text-align: center; font-size: 8.6pt; color: #333 }
.intro { margin: 16px 0 10px; text-align: justify }
table.precios { width: 100%; border-collapse: collapse; font-size: 8.6pt; border: 1.6px solid #1B1547; table-layout: fixed }
.precios th { background: #1B1547; color: #fff; text-align: left; padding: 4px 7px; font-weight: 700 }
.precios td { padding: 2.6px 7px; border-bottom: 1px solid #e1e1e7; vertical-align: top }
.precios .n { text-align: right; white-space: nowrap }
.precios tr.dia td { background: #E2E1E8; font-weight: 700; color: #1B1547; border-top: 1.2px solid #1B1547 }
.precios .lugar { font-weight: 400 }
.precios tr.sub td { text-align: right; font-weight: 700; font-size: 8.3pt; color: #333 }
.precios tr.tot td { text-align: right; font-weight: 700; border-bottom: 1px solid #c9c9d3 }
.precios tr.tot td .nota { font-weight: 400 }
.precios tr.primero td { border-top: 1.4px solid #1B1547 }
.precios tr.gran td { text-align: right; font-weight: 800; background: #DAE9F7; color: #1B1547; font-size: 10.2pt; border-top: 1.4px solid #1B1547 }
.precios tr { page-break-inside: avoid }
.inc { margin: 10px 0 0; font-size: 8.8pt }
.inc b { color: #1B1547 }
.condiciones { page-break-before: always }
h3 { color: #1B1547; font-size: 10.5pt; margin: 14px 0 5px; padding-bottom: 3px; border-bottom: 1.4px solid #1B1547; page-break-after: avoid }
.condiciones h3:first-child { margin-top: 0 }
ul { margin: 0 0 4px 0; padding-left: 18px } li { margin: 0 0 2px }
.condiciones p { margin: 0 0 5px }
table.he { border-collapse: collapse; font-size: 8.8pt; margin: 4px 0 6px }
.he td { border: 1px solid #c9c9d3; padding: 3px 10px } .he td.n { text-align: right }
.firmas { display: flex; justify-content: space-between; margin-top: 28px; text-align: center; page-break-inside: avoid }
.firmas > div { width: 3.0in }
.firmas .q { font-size: 9.2pt; height: 0.8in }
.firmas .q img { display: block; margin: 4px auto 0; max-height: 0.55in; max-width: 2.4in }
.firmas .l { border-top: 1.2px solid #1B1547; padding-top: 5px; font-weight: 700 }
.firmas .d { font-size: 8.2pt; color: #444 }
"""


def _cabecera(db: Session, cot: m.Cotizacion, idioma: str, t: dict) -> str:
    logo = marca.logo_incrustado()
    logo_html = (f'<img class="logo" src="{logo}">' if logo
                 else '<div class="logo-texto">CENTAURO</div>')
    cuando = dia_de_la_cotizacion(db, cot)
    quien = m._nombre_completo(cot.solicitante_nombre, cot.solicitante_apellidos)
    rfc = cot.cliente.rfc if cot.cliente and cot.cliente.rfc else None
    renglones = [
        (t["fecha"], fecha_larga(cuando, idioma)),
        (t["folio"], f"<b>{_e(cc.folio_texto(cot.folio))}</b> · "
                     f"{t['version']} {cot.version}"),
        (t["valida"], fecha_larga(cot.valida_hasta, idioma)
         if cot.valida_hasta else "—"),
        (t["moneda"], MONEDA[idioma].get(cot.moneda.value, cot.moneda.value)),
        (t["tipo"], _e(cot.tipo_servicio) or "—"),
    ]
    meta = "".join(f'<tr><td class="e">{e}</td><td class="v">{v}</td></tr>'
                   for e, v in renglones)
    cliente = (f'<div class="cliente"><div class="c">{t["cliente"]}</div>'
               f'<div class="n">{_e(cc.cliente_texto(cot))}</div>'
               + (f'<div class="a">{t["rfc"]}: {_e(rfc)}</div>' if rfc else "")
               + (f'<div class="a">{t["atencion"]}: {_e(quien)}</div>'
                  if quien else "")
               + '</div>')
    return (f'<div class="cab"><div class="izq">{logo_html}{cliente}</div>'
            f'<div><div class="titulo">{t["titulo"]}</div>'
            f'<table class="meta">{meta}</table></div></div>')


def _tabla(db: Session, cot: m.Cotizacion, idioma: str, t: dict) -> str:
    moneda = cot.moneda.value
    dias = {(d.equipo_clave, d.fecha): d for d in cot.dias}
    trabajo = [l for l in cot.lineas if l.tipo != m.TipoLinea.VIATICOS]
    filas = []
    for fecha in sorted({l.fecha for l in trabajo}):
        del_dia = sorted([l for l in trabajo if l.fecha == fecha],
                         key=lambda l: (cc.orden_de(l.equipo_clave),
                                        motor.ORDEN_DE_TIPO.get(l.tipo, 9),
                                        l.id or 0))
        lugares, foraneo = [], False
        for l in del_dia:
            d = dias.get((l.equipo_clave, fecha))
            if d is None:
                continue
            if d.plaza:
                lugares.append(d.plaza.nombre)
            if d.es_foraneo:
                foraneo = True
                if d.destino:
                    lugares.append(d.destino)
        lugar = _e(_lista_y(lugares, idioma))
        if foraneo:
            lugar = f"{lugar} · <b>{t['foraneo']}</b>" if lugar else f"<b>{t['foraneo']}</b>"
        filas.append(f'<tr class="dia"><td colspan="5">{dia_largo(fecha, idioma)}'
                     + (f' <span class="lugar">· {lugar}</span>' if lugar else "")
                     + '</td></tr>')
        subtotal = Decimal("0")
        for l in del_dia:
            concepto = producto_limpio(l.producto) or l.descripcion or "—"
            modalidad = MODALIDAD[idioma].get(
                l.modalidad.codigo.value if l.modalidad else "", "—")
            subtotal += Decimal(str(l.subtotal))
            filas.append(
                f'<tr><td>{_e(concepto)}</td><td>{modalidad}</td>'
                f'<td class="n">{l.cantidad}</td>'
                f'<td class="n">{dinero(l.precio_unitario, moneda)}</td>'
                f'<td class="n">{dinero(l.subtotal, moneda)}</td></tr>')
        filas.append(f'<tr class="sub"><td colspan="4">{t["subtotal_dia"]}</td>'
                     f'<td class="n">{dinero(subtotal, moneda)}</td></tr>')

    modo = motor.modo_de_gastos(cot)
    fijos = cc.gastos_fijos(cot)
    tot = cc.totales(cot)
    if modo == motor.GASTOS_FIJOS:
        servicios = Decimal(str(cot.total or 0)) - fijos
        filas.append(f'<tr class="tot primero"><td colspan="4">{t["servicios"]}</td>'
                     f'<td class="n">{dinero(servicios, moneda)}</td></tr>')
        filas.append(f'<tr class="tot"><td colspan="4">{t["gastos"]} '
                     f'<span class="nota">· {t["g_fijo_corto"]}</span></td>'
                     f'<td class="n">{dinero(fijos, moneda)}</td></tr>')
        filas.append(f'<tr class="tot"><td colspan="4">{t["subtotal"]}</td>'
                     f'<td class="n">{dinero(tot["subtotal"], moneda)}</td></tr>')
    else:
        filas.append(f'<tr class="tot primero"><td colspan="4">{t["subtotal"]}</td>'
                     f'<td class="n">{dinero(tot["subtotal"], moneda)}</td></tr>')
        nota = t["g_dentro_corto"] if modo == motor.GASTOS_DENTRO \
            else t["g_comprobar_corto"]
        filas.append(f'<tr class="tot"><td colspan="4">{t["gastos"]} '
                     f'<span class="nota">· {nota}</span></td>'
                     f'<td class="n">—</td></tr>')
    con_iva = cot.con_iva and cot.tasa_iva is not None
    if con_iva:
        filas.append(f'<tr class="tot"><td colspan="4">{t["iva"]} '
                     f'{tasa_texto(cot.tasa_iva)}</td>'
                     f'<td class="n">{dinero(tot["iva"], moneda)}</td></tr>')
    filas.append(f'<tr class="gran"><td colspan="4">'
                 f'{t["total_iva"] if con_iva else t["total"]}</td>'
                 f'<td class="n">{dinero(tot["total"], moneda)}</td></tr>')
    return ('<table class="precios"><colgroup><col style="width:43%">'
            '<col style="width:21%"><col style="width:7%"><col style="width:14%">'
            '<col style="width:15%"></colgroup>'
            f'<thead><tr><th>{t["servicio"]}</th><th>{t["modalidad"]}</th>'
            f'<th class="n">{t["cant"]}</th><th class="n">{t["unitario"]}</th>'
            f'<th class="n">{t["importe"]}</th></tr></thead>'
            f'<tbody>{"".join(filas)}</tbody></table>')


def _condiciones(db: Session, cot: m.Cotizacion, idioma: str, t: dict,
                 textos: dict) -> str:
    moneda = cot.moneda.value
    partes = []
    modalidades = sorted(
        (db.query(m.Modalidad).filter(
            m.Modalidad.pais_id == cot.pais_id,
            m.Modalidad.codigo.in_(cc.MODALIDADES_DEL_EVENTUAL)).all()),
        key=lambda x: float(x.horas))
    if modalidades:
        partes.append(f'<h3>{t["h_modalidades"]}</h3><ul>' + "".join(
            f'<li><b>{MODALIDAD[idioma][x.codigo.value]}:</b> '
            f'{t["hasta_h"].format(h=_horas(x.horas))}</li>'
            for x in modalidades) + "</ul>")
    tarifario = db.get(m.Tarifario, cot.tarifario_id)
    perfiles = {l.perfil_id for l in cot.lineas if l.perfil_id}
    horas = cc.hora_extra(db, tarifario, perfiles, cot.pais_id) if tarifario else []
    completo = next((x for x in modalidades
                     if x.codigo == m.CodigoModalidad.FULL_DAY), None)
    if horas and completo is not None:
        filas = "".join(
            f'<tr><td>{_e(_rol_de_hora(x))}</td><td class="n"><b>'
            f'{dinero(x["precio"], moneda)}</b> {t["por_hora"]}</td></tr>'
            for x in horas)
        partes.append(f'<h3>{t["h_he"]}</h3><p>'
                      f'{t["he_regla"].format(h=_horas(completo.horas) + 1)}</p>'
                      f'<table class="he">{filas}</table>')
    modo = motor.modo_de_gastos(cot)
    gastos = {motor.GASTOS_DENTRO: t["gd"], motor.GASTOS_COMPROBAR: t["gc"],
              motor.GASTOS_FIJOS: t["gf"].format(
                  m=dinero(cc.gastos_fijos(cot), moneda))}[modo]
    partes.append(f'<h3>{t["h_gastos"]}</h3><p>{gastos}</p>')
    for clave, titulo in (("pago", "h_pago"), ("aceptacion", "h_aceptacion"),
                          ("cancelacion", "h_cancelacion")):
        texto = textos["textos"].get(clave)
        if texto:
            partes.append(f'<h3>{t[titulo]}</h3>' + "".join(
                f"<p>{_e(_con_datos(p, cot))}</p>"
                for p in texto.split("\n") if p.strip()))
    vigencia = (t["vigencia"].format(f=f"<b>{fecha_larga(cot.valida_hasta, idioma)}</b>")
                if cot.valida_hasta else "")
    cierre = textos["textos"].get("cierre") or ""
    if vigencia or cierre:
        partes.append(f'<h3>{t["h_vigencia"]}</h3><p>{vigencia} '
                      f'{_e(_con_datos(cierre, cot))}</p>')
    partes.append(_firmas(db, cot, t))
    return f'<section class="condiciones">{"".join(partes)}</section>'


def _horas(valor) -> int:
    return int(Decimal(str(valor)))


def _rol_de_hora(x: dict) -> str:
    """«Hora Extra Conductor de Seguridad Bilingüe» se lee como el rol."""
    producto = (x.get("producto") or "").strip()
    if producto.lower().startswith("hora extra "):
        return producto[len("hora extra "):].strip() or x["rol"]
    return x["rol"]


def _firmas(db: Session, cot: m.Cotizacion, t: dict) -> str:
    consultor = cot.consultor
    firma = cc.firma_de(db, cot.consultor_id)
    imagen = f'<img src="{firma}">' if firma else ""
    contacto = " · ".join(x for x in (
        consultor.correo if consultor else None,
        consultor.telefono if consultor else None) if x)
    quien = m._nombre_completo(cot.solicitante_nombre, cot.solicitante_apellidos)
    return (
        '<div class="firmas">'
        f'<div><div class="q">{t["atentamente"]}{imagen}</div>'
        f'<div class="l">{_e(consultor.nombre if consultor else "—")}</div>'
        f'<div class="d">{_e(contacto)}</div></div>'
        f'<div><div class="q">{t["acepta"]} · {_e(cc.cliente_texto(cot))}</div>'
        f'<div class="l">{_e(quien or "")}&nbsp;</div>'
        f'<div class="d">{t["firma_cliente"]}</div></div>'
        '</div>')


def html_de(db: Session, cot: m.Cotizacion) -> str:
    idioma = cot.idioma if cot.idioma in T else "es"
    t = T[idioma]
    textos = _textos(db, cot.pais_id, idioma)
    logo = marca.logo_incrustado()
    razon = " · ".join(x for x in (
        textos["razon_social"],
        f"RFC {textos['rfc']}" if textos["rfc"] else None) if x)
    pie = ('<div class="pie">'
           + (f'<img src="{logo}">' if logo else "<b>CENTAURO</b>")
           + (f'<span class="razon">{_e(razon)}</span>' if razon else "")
           + '</div>')
    estilo = (ESTILO.replace("{f}", FUENTES.as_uri())
              .replace("{conf}", t["confidencial"])
              .replace("{folio}", f'{cc.folio_texto(cot.folio)} · '
                                  f'{t["version"]} {cot.version}')
              .replace("{pagina}", t["pagina"]).replace("{de}", t["de"]))
    marca_borrador = (f'<div class="marca">{t["borrador"]}</div>'
                      if cot.estatus == m.EstatusCotizacion.BORRADOR else "")
    incluye = textos["textos"].get(f"incluye_{motor.modo_de_gastos(cot)}")
    inc = (f'<p class="inc"><b>{t["incluye"]}</b> {_e(incluye)} '
           f'<b>{t["no_incluye"]}</b> {t["no_incluye_he"]}</p>' if incluye else "")
    if not (cot.con_iva and cot.tasa_iva is not None):
        inc += f'<p class="inc">{t["sin_iva"]}</p>'
    return (f'<!doctype html><html lang="{idioma}"><head><meta charset="utf-8">'
            f'<style>{estilo}</style></head><body>{pie}{marca_borrador}'
            f'{_cabecera(db, cot, idioma, t)}'
            f'<p class="intro">{_intro(cot, idioma, t)}</p>'
            f'{_tabla(db, cot, idioma, t)}{inc}'
            f'{_condiciones(db, cot, idioma, t, textos)}</body></html>')


def pdf(db: Session, cot: m.Cotizacion) -> bytes:
    """El PDF, como lo ve el cliente."""
    from weasyprint import HTML

    return HTML(string=html_de(db, cot), base_url=str(FUENTES)).write_pdf()

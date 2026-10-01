# -*- coding: utf-8 -*-
"""El PDF de la propuesta del implantado (seccion 115).

Sale de la propuesta de ejemplo de Salvador (Siemens Energy, Queretaro)
con la letra y el diseno de la cotizacion del eventual (seccion 114), y
con lo que se le corrigio al revisarla:

  * Dice PROPUESTA, con un solo folio --EP/PRO-0001 y su version--.
  * La tabla dice la modalidad: «lunes a viernes, 22 dias al mes».
  * El mensual de cada puesto y cada unidad, el subtotal, el IVA y el
    mensual con IVA (decision 4); el cliente sin IVA lo dice una vez.
  * En un cuadro aparte, lo que se cobra cuando aplica: el dia adicional
    --el mensual entre los dias, calculado por Connect--, la hora extra
    y los viaticos segun lo comprobado.
  * Dias y horario se escriben solos con lo que se armo; lo de siempre
    --lo que incluye y lo que no, responsabilidades, confidencialidad,
    alcance de cada rol y aceptacion-- sale de Catalogos, en el idioma
    del PDF.
  * La firma del consultor, como en la cotizacion. El archivo se llama
    como los de Centauro: 20260930_SIEMENSENERGY_EP-PRO-0001_V1_QUERETARO.pdf
"""
import re
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app import cotizacion_cliente as cc
from app import cotizacion_pdf as cp
from app import marca
from app import models as m
from app import propuesta as motor

D = m.DiasServicio
_e = cp._e

T = {
    "es": {
        "titulo": "PROPUESTA", "ciudad": "CIUDAD",
        "tabla": "Servicio implantado · {modalidad}",
        "modalidad_tabla": {D.LUNES_VIERNES: "lunes a viernes, 22 días al mes",
                            D.LUNES_SABADO: "lunes a sábado, 26 días al mes",
                            D.TODOS: "mes completo, 30 días a costo fijo"},
        "precio_mes": "Precio mensual", "importe_mes": "Importe mensual",
        "subtotal_mes": "Subtotal mensual", "total_mes_iva": "Total mensual con IVA",
        "total_mes": "Total mensual",
        "aparte": "Cuando apliquen, se cobran aparte cada mes",
        "adicional_que": {D.LUNES_VIERNES: "Día adicional: el sábado o el "
                                           "domingo que se pida",
                          D.LUNES_SABADO: "Día adicional: el domingo que se "
                                          "pida"},
        "por_dia": "por día", "por_hora": "por hora",
        "he_que": "Hora extra, con previo aviso y autorización",
        "viaticos_que": "Viáticos, con su comprobante",
        "segun": "según lo comprobado",
        "h_dias": "Días y horario",
        "jornada": "Jornada de {h} horas a partir de que inicia el servicio.",
        "modalidad_regla": {
            D.LUNES_VIERNES: "De lunes a viernes: el mensual cubre 22 días al "
                             "mes, aunque el mes traiga 21 o 23 días hábiles.",
            D.LUNES_SABADO: "De lunes a sábado: el mensual cubre 26 días al "
                            "mes, aunque el mes traiga más o menos.",
            D.TODOS: "Todos los días: el mensual cubre el mes completo, 30 "
                     "días, a costo fijo."},
        "adicional_regla": {
            D.LUNES_VIERNES: "El sábado o el domingo que se pida el servicio "
                             "se cobra como día adicional, a {p}.",
            D.LUNES_SABADO: "El domingo que se pida el servicio se cobra como "
                            "día adicional, a {p}."},
        "he_regla": "Las horas adicionales se cobran a {p} por hora, con "
                    "previo aviso y autorización.",
        "primer_mes": "Si el servicio empieza a medio mes, el primer mes se "
                      "cobra por día de servicio, a {p} por día.",
        "h_viaticos": "Viáticos",
        "viaticos_dentro": "Van incluidos en el mensual: no se facturan "
                           "aparte.",
        "h_cliente": "Responsabilidades del cliente",
        "h_centauro": "Responsabilidades de Centauro y confidencialidad",
        "h_alcance": "Alcance del servicio",
        "intro": "A solicitud de {quien}, de {cliente}, presentamos la "
                 "propuesta {del_tipo}{en_ciudad}, {modalidad}{desde}.",
        "del_tipo": "del servicio implantado de {tipo}",
        "del_servicio": "del servicio implantado",
        "en_ciudad": " en {ciudad}",
        "modalidad_intro": {D.LUNES_VIERNES: "de lunes a viernes",
                            D.LUNES_SABADO: "de lunes a sábado",
                            D.TODOS: "todos los días"},
        "desde": ", a partir del {f}",
    },
    "en": {
        "titulo": "PROPOSAL", "ciudad": "CITY",
        "tabla": "Embedded service · {modalidad}",
        "modalidad_tabla": {D.LUNES_VIERNES: "Monday to Friday, 22 days a month",
                            D.LUNES_SABADO: "Monday to Saturday, 26 days a month",
                            D.TODOS: "full month, 30 days at a fixed cost"},
        "precio_mes": "Monthly price", "importe_mes": "Monthly amount",
        "subtotal_mes": "Monthly subtotal",
        "total_mes_iva": "Monthly total with VAT", "total_mes": "Monthly total",
        "aparte": "When applicable, charged separately each month",
        "adicional_que": {D.LUNES_VIERNES: "Additional day: a Saturday or "
                                           "Sunday requested",
                          D.LUNES_SABADO: "Additional day: a Sunday "
                                          "requested"},
        "por_dia": "per day", "por_hora": "per hour",
        "he_que": "Overtime, with prior notice and approval",
        "viaticos_que": "Expenses, with their receipts",
        "segun": "as incurred",
        "h_dias": "Days and hours",
        "jornada": "Working day of {h} hours from the start of the service.",
        "modalidad_regla": {
            D.LUNES_VIERNES: "Monday to Friday: the monthly fee covers 22 days "
                             "a month, whether the month has 21 or 23 "
                             "working days.",
            D.LUNES_SABADO: "Monday to Saturday: the monthly fee covers 26 "
                            "days a month, whether the month has more or "
                            "fewer.",
            D.TODOS: "Every day: the monthly fee covers the full month, 30 "
                     "days, at a fixed cost."},
        "adicional_regla": {
            D.LUNES_VIERNES: "A Saturday or Sunday on which the service is "
                             "requested is charged as an additional day, at "
                             "{p}.",
            D.LUNES_SABADO: "A Sunday on which the service is requested is "
                            "charged as an additional day, at {p}."},
        "he_regla": "Additional hours are charged at {p} per hour, with prior "
                    "notice and approval.",
        "primer_mes": "If the service starts partway through the month, the "
                      "first month is charged per day of service, at {p} per "
                      "day.",
        "h_viaticos": "Expenses",
        "viaticos_dentro": "They are included in the monthly fee: not invoiced "
                           "separately.",
        "h_cliente": "Client responsibilities",
        "h_centauro": "Centauro's responsibilities and confidentiality",
        "h_alcance": "Scope of the service",
        "intro": "At the request of {quien}, of {cliente}, we present our "
                 "proposal {del_tipo}{en_ciudad}, {modalidad}{desde}.",
        "del_tipo": "for an embedded {tipo} service",
        "del_servicio": "for an embedded service",
        "en_ciudad": " in {ciudad}",
        "modalidad_intro": {D.LUNES_VIERNES: "Monday to Friday",
                            D.LUNES_SABADO: "Monday to Saturday",
                            D.TODOS: "every day"},
        "desde": ", starting {f}",
    },
    "pt": {
        "titulo": "PROPOSTA", "ciudad": "CIDADE",
        "tabla": "Serviço implantado · {modalidad}",
        "modalidad_tabla": {D.LUNES_VIERNES: "segunda a sexta, 22 dias por mês",
                            D.LUNES_SABADO: "segunda a sábado, 26 dias por mês",
                            D.TODOS: "mês completo, 30 dias a custo fixo"},
        "precio_mes": "Preço mensal", "importe_mes": "Valor mensal",
        "subtotal_mes": "Subtotal mensal",
        "total_mes_iva": "Total mensal com impostos", "total_mes": "Total mensal",
        "aparte": "Quando se aplicarem, cobrados à parte a cada mês",
        "adicional_que": {D.LUNES_VIERNES: "Dia adicional: o sábado ou o "
                                           "domingo solicitado",
                          D.LUNES_SABADO: "Dia adicional: o domingo "
                                          "solicitado"},
        "por_dia": "por dia", "por_hora": "por hora",
        "he_que": "Hora extra, com aviso prévio e autorização",
        "viaticos_que": "Despesas, com o seu comprovante",
        "segun": "conforme comprovado",
        "h_dias": "Dias e horário",
        "jornada": "Jornada de {h} horas a partir do início do serviço.",
        "modalidad_regla": {
            D.LUNES_VIERNES: "De segunda a sexta: a mensalidade cobre 22 dias "
                             "por mês, mesmo que o mês tenha 21 ou 23 dias "
                             "úteis.",
            D.LUNES_SABADO: "De segunda a sábado: a mensalidade cobre 26 dias "
                            "por mês, mesmo que o mês tenha mais ou menos.",
            D.TODOS: "Todos os dias: a mensalidade cobre o mês completo, 30 "
                     "dias, a custo fixo."},
        "adicional_regla": {
            D.LUNES_VIERNES: "O sábado ou o domingo em que o serviço for "
                             "solicitado é cobrado como dia adicional, a {p}.",
            D.LUNES_SABADO: "O domingo em que o serviço for solicitado é "
                            "cobrado como dia adicional, a {p}."},
        "he_regla": "As horas adicionais são cobradas a {p} por hora, com "
                    "aviso prévio e autorização.",
        "primer_mes": "Se o serviço começar no meio do mês, o primeiro mês é "
                      "cobrado por dia de serviço, a {p} por dia.",
        "h_viaticos": "Despesas",
        "viaticos_dentro": "Estão incluídas na mensalidade: não são faturadas "
                           "à parte.",
        "h_cliente": "Responsabilidades do cliente",
        "h_centauro": "Responsabilidades da Centauro e confidencialidade",
        "h_alcance": "Escopo do serviço",
        "intro": "A pedido de {quien}, de {cliente}, apresentamos a proposta "
                 "{del_tipo}{en_ciudad}, {modalidad}{desde}.",
        "del_tipo": "do serviço implantado de {tipo}",
        "del_servicio": "do serviço implantado",
        "en_ciudad": " em {ciudad}",
        "modalidad_intro": {D.LUNES_VIERNES: "de segunda a sexta",
                            D.LUNES_SABADO: "de segunda a sábado",
                            D.TODOS: "todos os dias"},
        "desde": ", a partir de {f}",
    },
}

EXTRA = """
.cuando { width: 100%; border-collapse: collapse; font-size: 8.6pt; margin: 10px 0 0; border: 1.2px solid #1B1547; page-break-inside: avoid }
.cuando th { background: #E2E1E8; color: #1B1547; text-align: left; padding: 4px 7px; font-weight: 700 }
.cuando td { padding: 3px 7px; border-top: 1px solid #e1e1e7 }
.cuando td.n { text-align: right; white-space: nowrap; font-weight: 700 }
.inc ul { margin: 2px 0 6px }
.condiciones h3 { margin: 9px 0 4px }
.firmas { margin-top: 14px }
.firmas .q { height: 0.68in }
"""


def _idioma(cot) -> str:
    return cot.idioma if cot.idioma in T else "es"


def _horas(valor) -> str:
    numero = Decimal(str(valor)).normalize()
    return f"{numero:f}"


def _dias(cot) -> D:
    return D(cot.dias_servicio) if cot.dias_servicio else D.LUNES_VIERNES


# ------------------------------------------------------------- la introduccion

def intro_automatica(db: Session, cot, idioma: str, marcado: bool = True) -> str:
    """La introduccion que Connect escribe con los datos: quien la pide, el
    cliente, el servicio, la ciudad, la modalidad y desde cuando. `cot`
    puede ser una propuesta guardada o lo que se esta armando: solo se
    leen sus datos. En el PDF lleva negritas; en la pantalla, texto."""
    idioma = idioma if idioma in T else "es"
    t = T[idioma]
    limpio = _e if marcado else (lambda x: str(x or ""))
    negrita = (lambda x: f"<b>{x}</b>") if marcado else (lambda x: x)
    tipo = (cot.tipo_servicio or "").strip()
    del_tipo = (t["del_tipo"].format(tipo=limpio(tipo[:1].lower() + tipo[1:]))
                if tipo else t["del_servicio"])
    plaza = getattr(cot, "plaza", None)
    quien = m._nombre_completo(cot.solicitante_nombre,
                               cot.solicitante_apellidos) or "—"
    return t["intro"].format(
        quien=negrita(limpio(quien)),
        cliente=negrita(limpio(cc.cliente_texto(cot))),
        del_tipo=del_tipo,
        en_ciudad=(t["en_ciudad"].format(ciudad=negrita(limpio(plaza.nombre)))
                   if plaza else ""),
        modalidad=t["modalidad_intro"][_dias(cot)],
        desde=(t["desde"].format(f=negrita(cp.fecha_larga(cot.inicio, idioma)))
               if cot.inicio else ""))


# ------------------------------------------------------------- las partes

def _textos(db: Session, cot, idioma: str) -> dict:
    """Los de Catalogos que lee el PDF, en su idioma, con sus huecos."""
    salida = {c: motor.texto(db, cot.pais_id, c, idioma).strip()
              for c in motor.CLAVES_DE_TEXTO}
    salida["cierre"] = motor.texto(db, cot.pais_id, "cierre", idioma).strip()
    return {c: cp._con_datos(v, cot) for c, v in salida.items()}


def _vinetas(texto: str) -> str:
    renglones = [r.strip() for r in (texto or "").split("\n") if r.strip()]
    return "".join(f"<li>{_e(r)}</li>" for r in renglones)


def _parrafos(texto: str) -> str:
    return "".join(f"<p>{_e(p.strip())}</p>"
                   for p in re.split(r"\n\s*\n|\n", texto or "") if p.strip())


def _cabecera(db: Session, cot: m.Cotizacion, idioma: str) -> str:
    t, tc = T[idioma], cp.T[idioma]
    logo = marca.logo_incrustado()
    logo_html = (f'<img class="logo" src="{logo}">' if logo
                 else '<div class="logo-texto">CENTAURO</div>')
    cuando = cp.dia_de_la_cotizacion(db, cot)
    quien = m._nombre_completo(cot.solicitante_nombre, cot.solicitante_apellidos)
    rfc = cot.cliente.rfc if cot.cliente and cot.cliente.rfc else None
    renglones = [
        (tc["fecha"], cp.fecha_larga(cuando, idioma)),
        (tc["folio"], f"<b>{_e(motor.folio_de(cot))}</b> · "
                      f"{tc['version']} {cot.version}"),
        (tc["valida"], cp.fecha_larga(cot.valida_hasta, idioma)
         if cot.valida_hasta else "—"),
        (tc["moneda"], cp.MONEDA[idioma].get(cot.moneda.value,
                                             cot.moneda.value)),
        (tc["tipo"], _e(cot.tipo_servicio) or "—"),
        (t["ciudad"], _e(cot.plaza.nombre) if cot.plaza else "—"),
    ]
    meta = "".join(f'<tr><td class="e">{e}</td><td class="v">{v}</td></tr>'
                   for e, v in renglones)
    cliente = (f'<div class="cliente"><div class="c">{tc["cliente"]}</div>'
               f'<div class="n">{_e(cc.cliente_texto(cot))}</div>'
               + (f'<div class="a">{tc["rfc"]}: {_e(rfc)}</div>' if rfc else "")
               + (f'<div class="a">{tc["atencion"]}: {_e(quien)}</div>'
                  if quien else "")
               + '</div>')
    return (f'<div class="cab"><div class="izq">{logo_html}{cliente}</div>'
            f'<div><div class="titulo">{t["titulo"]}</div>'
            f'<table class="meta">{meta}</table></div></div>')


def _concepto(p: dict) -> str:
    return (p["descripcion"] or cp.producto_limpio(p["producto"])
            or p["nombre"] or "—")


def _tabla(cot: m.Cotizacion, calc: dict, idioma: str) -> str:
    t, tc = T[idioma], cp.T[idioma]
    moneda = cot.moneda.value
    filas = [f'<tr><td>{_e(_concepto(p))}</td><td class="n">{p["cantidad"]}</td>'
             f'<td class="n">{cp.dinero(p["precio_mes"], moneda)}</td>'
             f'<td class="n">{cp.dinero(p["importe"], moneda)}</td></tr>'
             for p in calc["posiciones"]]
    tasa = (Decimal(str(cot.tasa_iva)) if cot.tasa_iva is not None else None)
    tot = cc._totales(calc["subtotal"], cot.con_iva, tasa)
    con_iva = cot.con_iva and tasa is not None
    filas.append(f'<tr class="tot primero"><td colspan="3">{t["subtotal_mes"]}'
                 f'</td><td class="n">{cp.dinero(tot["subtotal"], moneda)}</td>'
                 '</tr>')
    if con_iva:
        filas.append(f'<tr class="tot"><td colspan="3">{tc["iva"]} '
                     f'{cp.tasa_texto(tasa)}</td>'
                     f'<td class="n">{cp.dinero(tot["iva"], moneda)}</td></tr>')
    filas.append(f'<tr class="gran"><td colspan="3">'
                 f'{t["total_mes_iva"] if con_iva else t["total_mes"]}</td>'
                 f'<td class="n">{cp.dinero(tot["total"], moneda)}</td></tr>')
    titulo = t["tabla"].format(modalidad=t["modalidad_tabla"][_dias(cot)])
    tabla = ('<table class="precios"><colgroup><col style="width:56%">'
             '<col style="width:8%"><col style="width:18%"><col style="width:18%">'
             f'</colgroup><thead><tr><th>{_e(titulo)}</th>'
             f'<th class="n">{tc["cant"]}</th><th class="n">{t["precio_mes"]}</th>'
             f'<th class="n">{t["importe_mes"]}</th></tr></thead>'
             f'<tbody>{"".join(filas)}</tbody></table>')

    aparte = []
    dias = _dias(cot)
    if calc["dia_adicional"] is not None and dias in t["adicional_que"]:
        aparte.append((t["adicional_que"][dias],
                       f'{cp.dinero(calc["dia_adicional"], moneda)} '
                       f'{t["por_dia"]}'))
    if calc["hora_extra"]:
        aparte.append((t["he_que"], f'{cp.dinero(calc["hora_extra"], moneda)} '
                                    f'{t["por_hora"]}'))
    if not cot.viaticos_incluidos:
        aparte.append((t["viaticos_que"], t["segun"]))
    if aparte:
        tabla += ('<table class="cuando"><colgroup><col style="width:64%">'
                  '<col style="width:36%"></colgroup>'
                  f'<tr><th colspan="2">{t["aparte"]}</th></tr>'
                  + "".join(f'<tr><td>{_e(q)}</td><td class="n">{v}</td></tr>'
                            for q, v in aparte)
                  + '</table>')
    return tabla


def _incluye(cot: m.Cotizacion, calc: dict, idioma: str, textos: dict) -> str:
    tc = cp.T[idioma]
    incluye = textos["pro_incluye"]
    if calc["unidades"]:
        incluye += "\n" + textos["pro_incluye_unidad"]
    if cot.viaticos_incluidos:
        incluye += "\n" + textos["pro_incluidos"]
    partes = []
    if incluye.strip():
        partes.append(f'<b>{tc["incluye"]}</b><ul>{_vinetas(incluye)}</ul>')
    if not cot.viaticos_incluidos and textos["pro_no_incluye"]:
        partes.append(f'<b>{tc["no_incluye"]}</b>'
                      f'<ul>{_vinetas(textos["pro_no_incluye"])}</ul>')
    salida = f'<div class="inc">{"".join(partes)}</div>' if partes else ""
    if not (cot.con_iva and cot.tasa_iva is not None):
        salida += f'<p class="inc">{tc["sin_iva"]}</p>'
    return salida


def _condiciones(db: Session, cot: m.Cotizacion, calc: dict, idioma: str,
                 textos: dict) -> str:
    t, tc = T[idioma], cp.T[idioma]
    moneda = cot.moneda.value
    dias = _dias(cot)
    horas = (cot.horas_jornada if cot.horas_jornada is not None
             else motor.horas_del_pais(db, cot.pais_id))
    reglas = []
    if horas is not None:
        reglas.append(t["jornada"].format(h=_horas(horas)))
    reglas.append(t["modalidad_regla"][dias])
    if calc["dia_adicional"] is not None and dias in t["adicional_regla"]:
        reglas.append(t["adicional_regla"][dias].format(
            p=f"<b>{cp.dinero(calc['dia_adicional'], moneda)}</b>"))
    if calc["hora_extra"]:
        reglas.append(t["he_regla"].format(
            p=f"<b>{cp.dinero(calc['hora_extra'], moneda)}</b>"))
    if calc["subtotal"]:
        por_dia = (calc["subtotal"] / calc["base"]).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        reglas.append(t["primer_mes"].format(
            p=f"<b>{cp.dinero(por_dia, moneda)}</b>"))
    partes = [f'<h3>{t["h_dias"]}</h3><ul>'
              + "".join(f"<li>{r}</li>" for r in reglas) + "</ul>"]
    viaticos = (t["viaticos_dentro"] if cot.viaticos_incluidos
                else _e(textos["pro_viaticos"]))
    if viaticos:
        partes.append(f'<h3>{t["h_viaticos"]}</h3><p>{viaticos}</p>')
    if textos["pro_cliente"]:
        partes.append(f'<h3>{t["h_cliente"]}</h3>'
                      f'<ul>{_vinetas(textos["pro_cliente"])}</ul>')
    if textos["pro_centauro"]:
        partes.append(f'<h3>{t["h_centauro"]}</h3>'
                      f'{_parrafos(textos["pro_centauro"])}')
    alcance = cot.alcance or motor.alcance_auto(
        db, cot.pais_id, idioma, [p["perfil_id"] for p in calc["posiciones"]])
    if alcance:
        partes.append(f'<h3>{t["h_alcance"]}</h3>{_parrafos(alcance)}')
    if textos["pro_aceptacion"]:
        partes.append(f'<h3>{tc["h_aceptacion"]}</h3>'
                      f'{_parrafos(textos["pro_aceptacion"])}')
    vigencia = (tc["vigencia"].format(
        f=f"<b>{cp.fecha_larga(cot.valida_hasta, idioma)}</b>")
        if cot.valida_hasta else "")
    if vigencia or textos["cierre"]:
        partes.append(f'<h3>{tc["h_vigencia"]}</h3><p>{vigencia} '
                      f'{_e(textos["cierre"])}</p>')
    partes.append(cp._firmas(db, cot, tc))
    return f'<section class="condiciones">{"".join(partes)}</section>'


def html_de(db: Session, cot: m.Cotizacion) -> str:
    idioma = _idioma(cot)
    tc = cp.T[idioma]
    calc = motor.de_la_guardada(cot)
    textos = _textos(db, cot, idioma)
    datos = cc.datos_del_pais(db, cot.pais_id)
    logo = marca.logo_incrustado()
    razon = " · ".join(x for x in (
        datos.razon_social if datos else None,
        f"RFC {datos.rfc}" if datos and datos.rfc else None) if x)
    pie = ('<div class="pie">'
           + (f'<img src="{logo}">' if logo else "<b>CENTAURO</b>")
           + (f'<span class="razon">{_e(razon)}</span>' if razon else "")
           + '</div>')
    estilo = (cp.ESTILO.replace("{f}", cp.FUENTES.as_uri())
              .replace("{conf}", tc["confidencial"])
              .replace("{folio}", f'{motor.folio_de(cot)} · '
                                  f'{tc["version"]} {cot.version}')
              .replace("{pagina}", tc["pagina"]).replace("{de}", tc["de"])
              ) + EXTRA
    marca_borrador = (f'<div class="marca">{tc["borrador"]}</div>'
                      if cot.estatus == m.EstatusCotizacion.BORRADOR else "")
    intro = (_e(cot.introduccion) if cot.introduccion
             else intro_automatica(db, cot, idioma))
    return (f'<!doctype html><html lang="{idioma}"><head><meta charset="utf-8">'
            f'<style>{estilo}</style></head><body>{pie}{marca_borrador}'
            f'{_cabecera(db, cot, idioma)}'
            f'<p class="intro">{intro}</p>'
            f'{_tabla(cot, calc, idioma)}{_incluye(cot, calc, idioma, textos)}'
            f'{_condiciones(db, cot, calc, idioma, textos)}</body></html>')


def pdf(db: Session, cot: m.Cotizacion) -> bytes:
    """El PDF, como lo ve el cliente."""
    from weasyprint import HTML

    return HTML(string=html_de(db, cot), base_url=str(cp.FUENTES)).write_pdf()


def nombre_del_archivo(db: Session, cot: m.Cotizacion) -> str:
    """Como el de Salvador: fecha, cliente, folio, version y ciudad.
    20260930_SIEMENSENERGY_EP-PRO-0001_V1_QUERETARO.pdf"""
    cuando = cp.dia_de_la_cotizacion(db, cot)
    palabras = re.findall(r"[A-Za-z0-9]+", cp._ascii(cc.cliente_texto(cot)))
    quien = "".join(palabras[:2]).upper()[:24] or "CLIENTE"
    folio = motor.folio_de(cot).replace("/", "-")
    ciudad = ("_" + "".join(re.findall(r"[A-Za-z0-9]+", cp._ascii(
        cot.plaza.nombre))).upper()[:20]) if cot.plaza else ""
    return f"{cuando:%Y%m%d}_{quien}_{folio}_V{cot.version}{ciudad}.pdf"

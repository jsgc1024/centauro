"""El armazon de los correos que salen de la empresa.

Misma identidad del task sheet y de la consola: filo azul arriba, el
logo, la placa AI/EP, la firma CONNECT, Inter, y de ahi para abajo sin
adornos. Es la cara que el ejecutivo ya conoce, y un correo que no se
parece a lo que el cliente conoce es un correo que se lee como si fuera
de otro.

Uno solo para los diez avisos. El armazon pone la marca, el folio, el
titulo y el pie; el cuerpo lo sigue escribiendo quien origina el aviso,
que es el que sabe que hay que decir.

Tres reglas que valen mas que el estilo:

  - **La ficha, no el parrafo.** Quien va, en que unidad y a que hora
    van en una tabla de dos columnas. Un dato metido en un parrafo hay
    que leerlo entero para encontrarlo, y esto se abre en el telefono a
    las seis de la manana.
  - **El nombre del personal de seguridad va con su telefono, y se
    marca de un toque.** Regla de Salvador (20 sep). El cliente que
    abre este correo suele necesitar algo AHORA --que baje el coche,
    que suba por una maleta-- y lo que hace es llamar. Sin el numero
    ahi, llama a la central para que la central le pase el numero.
  - **El boton, solo cuando hay a donde ir.** Dos de los diez llevan
    enlace. Un boton que no lleva a nada ensena a no picar ninguno.
  - **Tambien en texto plano.** Hay buzones que bloquean el HTML, y un
    correo que llega vacio es peor que uno feo.

Se escribe con tablas y estilos pegados a cada etiqueta, que es feo de
leer y es lo unico que se ve igual en Outlook, en Gmail y en el correo
del telefono. Una hoja de estilos aparte la tiran la mitad de los
buzones.
"""
import html
import json

from app.marca import logo_incrustado

CENTAURO = "#1B1546"
SUAVE = "#f0f3f5"
GRIS = "#78828c"
LINEA = "AI/EP"
PIE = "Centauro · Protección ejecutiva"

# La firma de la consola (secciones 72 y 76): CONNECT y debajo el lema,
# del mismo largo, en el dorado de la puerta de entrada. Es un nombre y
# no se traduce.
DORADO = "#8c6f14"
NOMBRE = "CONNECT"
LEMA = "HIGH PERFORMANCE"
ANCHO_FIRMA = 104          # lo que mide CONNECT en la cabecera de la consola
LETRA = "Inter,-apple-system,'Segoe UI',Arial,sans-serif"


def _esc(valor) -> str:
    return html.escape(str(valor)) if valor not in (None, "") else ""


def guardar_datos(pares) -> str | None:
    """La ficha, lista para guardarse en el aviso.

    `pares` son tuplas (clave, valor) o (clave, valor, telefono). El
    tercero es lo que hace que el nombre de quien va se pueda marcar de
    un toque: el cliente que abre esto necesita algo ahora.

    Lo que viene vacio no se guarda: un renglon con la clave y nada al
    lado ensena que la ficha trae relleno.
    """
    limpios = []
    for par in (pares or []):
        clave, valor = par[0], par[1]
        if valor in (None, ""):
            continue
        tel = par[2] if len(par) > 2 else None
        limpios.append([str(clave), str(valor), str(tel) if tel else None])
    return json.dumps(limpios, ensure_ascii=False) if limpios else None


def leer_datos(crudo: str | None) -> list:
    """Los pares, siempre de tres: (clave, valor, telefono o nulo)."""
    if not crudo:
        return []
    try:
        return [(par[0], par[1], par[2] if len(par) > 2 else None)
                for par in json.loads(crudo)]
    except (ValueError, TypeError, IndexError):
        # Un aviso con la ficha rota se manda sin ficha. Lo que no puede
        # pasar es que un correo no salga por un renglon de adorno.
        return []


def _para_marcar(telefono: str) -> str:
    """El numero como lo quiere un telefono: sin espacios ni guiones."""
    return "".join(c for c in str(telefono) if c.isdigit() or c == "+")


def _repartido(texto: str, tamano: int, peso: int, alto: int) -> str:
    """Un renglon de la firma: cada letra en su celda, repartidas a lo
    ancho de la firma.

    Es lo que hace la consola (web/firma.js), con tablas. El largo de
    una palabra depende de la letra que tenga cada buzon --Outlook no
    tiene Inter--, y con espaciado a ojo el lema quedaba mas corto o mas
    largo que CONNECT segun quien lo abriera. Repartidas en el mismo
    ancho, las dos miden lo mismo en cualquiera.
    """
    # Entre letra y letra, una celda vacia; todas del mismo ancho. Asi la
    # primera letra queda en la orilla izquierda, la ultima en la derecha
    # y los huecos iguales, como `space-between` en la consola.
    hueco = f"{100 / (len(texto) - 1):.2f}"
    celdas = []
    for i, letra in enumerate(texto):
        if i:
            celdas.append(f'<td width="{hueco}%" style="width:{hueco}%;'
                          f'font-size:0;line-height:0"></td>')
        celdas.append(
            f'<td style="padding:0;white-space:nowrap;font-family:{LETRA};'
            f'font-size:{tamano}px;line-height:{alto}px;font-weight:{peso};'
            f'color:{DORADO}">{"&nbsp;" if letra == " " else _esc(letra)}</td>')
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" '
            f'border="0" width="{ANCHO_FIRMA}" style="width:{ANCHO_FIRMA}px">'
            f'<tr>{"".join(celdas)}</tr></table>')


def firma() -> str:
    """CONNECT y debajo el lema, del mismo largo: la de la consola."""
    return _repartido(NOMBRE, 13, 700, 16) + _repartido(LEMA, 8, 600, 11)


def marca(alto: int = 46) -> str:
    """El logo, la placa de la linea y la firma: la cabecera de la consola.

    El logo ya trae su bajada --"Advanced Security Consulting"-- asi que
    la placa AI/EP va al lado, alineada abajo, y la firma CONNECT junto a
    la placa y centrada con ella, como en la consola (seccion 76). Un
    correo que se ve distinto de la consola se lee como si fuera de otro.

    En la computadora caben los tres en un renglon; en el telefono no:
    solo el logo mide 205 px y la caja del correo, ahi, 260. Por eso son
    dos bloques que se acomodan solos --la placa y la firma se bajan
    debajo del logo cuando no caben-- y, para Outlook, que no acomoda
    bloques, una tabla que solo el ve y que los deja al lado. Nada de
    flex: Outlook no lo pinta.
    """
    if logo_incrustado():
        izquierda = (f'<img src="{logo_incrustado()}" alt="Centauro" '
                     f'style="height:{alto}px;display:block;border:0">')
    else:
        izquierda = (f'<span style="font-weight:700;letter-spacing:3px;'
                     f'color:{CENTAURO};font-size:{max(12, alto // 3)}px">'
                     f'CENTAURO</span>')
    placa = (f'<span style="display:inline-block;font-weight:700;'
             f'font-size:11px;letter-spacing:.5px;color:#fff;'
             f'background:{CENTAURO};padding:2px 8px;border-radius:4px">'
             f'{LINEA}</span>')
    lado = ('<table role="presentation" cellpadding="0" cellspacing="0" '
            'border="0"><tr>'
            f'<td style="vertical-align:middle">{placa}</td>'
            f'<td style="vertical-align:middle;padding-left:12px">{firma()}'
            '</td></tr></table>')
    return ('<!--[if mso]><table role="presentation" cellpadding="0" '
            'cellspacing="0" border="0"><tr><td style="vertical-align:bottom">'
            '<![endif]-->'
            '<div style="display:inline-block;vertical-align:bottom;'
            f'margin:0 14px 0 0">{izquierda}</div>'
            '<!--[if mso]></td><td style="vertical-align:bottom;'
            'padding:0 0 4px 0"><![endif]-->'
            '<div style="display:inline-block;vertical-align:bottom;'
            f'padding:8px 0 4px">{lado}</div>'
            '<!--[if mso]></td></tr></table><![endif]-->')


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado",
        "domingo")


def dia_largo(fecha) -> str:
    """"sabado 19 de septiembre", no "2026-09-19".

    Una fecha en formato de base de datos obliga a traducirla mentalmente
    para saber si es hoy, manana o el jueves. El cliente no tiene por
    que hacer esa cuenta a las nueve de la noche.
    """
    return f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]}"


def _ficha(pares) -> str:
    if not pares:
        return ""
    renglones = []
    for i, par in enumerate(pares):
        clave, valor = par[0], par[1]
        telefono = par[2] if len(par) > 2 else None
        filo = "" if i == 0 else "border-top:1px solid #eef0f2;"
        # El telefono de quien va, marcable de un toque. Va al lado del
        # nombre y no en otro renglon: lo que se busca es "a quien llamo
        # ahorita", y son la misma pregunta.
        liga = (f' · <a href="tel:{_esc(_para_marcar(telefono))}" '
                f'style="color:{CENTAURO};font-weight:650;'
                f'text-decoration:none">{_esc(telefono)}</a>'
                if telefono else "")
        renglones.append(
            f'<tr><td style="{filo}padding:7px 0;width:38%;font-size:12px;'
            f'color:{GRIS};text-transform:uppercase;letter-spacing:.6px;'
            f'font-weight:650;vertical-align:top">{_esc(clave)}</td>'
            f'<td style="{filo}padding:7px 0;font-size:14px;'
            f'vertical-align:top">{_esc(valor)}{liga}</td></tr>')
    return (f'<tr><td style="padding:16px 26px 0">'
            f'<table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0">{"".join(renglones)}</table></td></tr>')


def armar(titulo: str, cuerpo: str, folio: str | None = None,
          pares=None, boton: tuple | None = None,
          nota: str | None = None) -> str:
    """El correo completo.

    `boton` es (texto, enlace) y solo se pinta si hay enlace de verdad.
    `nota` es el renglon chico de debajo del boton --lo que vence, lo
    que caduca-- que en un correo importa decir antes de que alguien lo
    guarde creyendo que sirve manana.
    """
    partes = [f'<tr><td style="padding:22px 26px 10px">{marca()}</td></tr>']
    if folio:
        partes.append(f'<tr><td style="padding:0 26px 4px;font-size:12px;'
                      f'color:{GRIS}">{_esc(folio)}</td></tr>')
    partes.append(f'<tr><td style="padding:14px 26px 0;font-size:19px;'
                  f'font-weight:650;line-height:1.35;color:{CENTAURO}">'
                  f'{_esc(titulo)}</td></tr>')
    if cuerpo:
        partes.append(f'<tr><td style="padding:12px 26px 0;font-size:15px;'
                      f'line-height:1.55">{_esc(cuerpo)}</td></tr>')
    partes.append(_ficha(pares))
    if boton and boton[1]:
        partes.append(
            f'<tr><td style="padding:20px 26px 4px">'
            f'<a href="{_esc(boton[1])}" style="display:inline-block;'
            f'background:{CENTAURO};color:#fff;text-decoration:none;'
            f'padding:12px 22px;border-radius:6px;font-weight:650;'
            f'font-size:14px">{_esc(boton[0])}</a></td></tr>')
    if nota:
        partes.append(f'<tr><td style="padding:8px 26px 0;font-size:11.5px;'
                      f'color:{GRIS}">{_esc(nota)}</td></tr>')
    partes.append(f'<tr><td style="padding:16px 26px 24px;margin-top:16px;'
                  f'font-size:11.5px;color:{GRIS};'
                  f'border-top:1px solid #eef0f2">{PIE}</td></tr>')

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
</head><body style="margin:0;padding:24px;background:{SUAVE};
  font-family:Inter,-apple-system,'Segoe UI',system-ui,sans-serif;color:#1a1d21">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
  style="max-width:520px;background:#fff;border:1px solid #dfe2e6;
         border-radius:8px;border-top:5px solid {CENTAURO};overflow:hidden">
{"".join(partes)}
</table>
</td></tr></table>
</body></html>"""


def plano(titulo: str, cuerpo: str, folio: str | None = None,
          pares=None, boton: tuple | None = None,
          nota: str | None = None) -> str:
    """El mismo correo en texto, para el buzon que no pinta HTML.

    No es un respaldo de adorno: se manda siempre, en el mismo mensaje.
    El que lo recibe asi tiene que poder hacer lo mismo que el otro, asi
    que el enlace va escrito completo y no escondido en un boton.
    """
    lineas = []
    if folio:
        lineas.append(folio)
    lineas.append(titulo)
    lineas.append("")
    if cuerpo:
        lineas += [cuerpo, ""]
    for par in (pares or []):
        telefono = par[2] if len(par) > 2 else None
        lineas.append(f"{par[0]}: {par[1]}"
                      + (f" · {telefono}" if telefono else ""))
    if pares:
        lineas.append("")
    if boton and boton[1]:
        lineas += [f"{boton[0]}: {boton[1]}", ""]
    if nota:
        lineas += [nota, ""]
    lineas.append(PIE)
    return "\n".join(lineas)

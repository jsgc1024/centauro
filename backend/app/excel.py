# -*- coding: utf-8 -*-
"""Un .xlsx sin librerias (seccion 69).

El historial de lo facturado se baja en Excel. Para eso bastan cinco
archivos de texto dentro de un zip: el libro, sus hojas y los estilos.
Se arma aqui con la biblioteca estandar, igual que el resto del sistema
habla con Google sin sus librerias: una dependencia mas es algo que
instalar en el servidor, que actualizar y que se rompe sola, y esto no
lo necesita.

Lo que trae cada hoja: el encabezado en negritas y fijo al bajar, el
filtro de Excel puesto, el ancho de cada columna, y los numeros y las
fechas como numeros y fechas de verdad --se suman y se ordenan en Excel,
no son texto que parece numero--.

Tipos de columna: "texto", "dinero", "entero", "fecha" y "momento"
(fecha con hora).
"""
import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

_ESTILO = {"texto": 0, "encabezado": 1, "dinero": 2, "fecha": 3,
           "entero": 4, "momento": 5}

# Lo que XML no acepta ni escapado.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_TIPOS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\
<Default Extension="xml" ContentType="application/xml"/>\
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>\
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>\
{hojas}</Types>"""

_RAIZ = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>\
</Relationships>"""

_ESTILOS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\
<numFmts count="3"><numFmt numFmtId="164" formatCode="#,##0.00"/>\
<numFmt numFmtId="165" formatCode="dd/mm/yyyy"/>\
<numFmt numFmtId="166" formatCode="dd/mm/yyyy hh:mm"/></numFmts>\
<fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font>\
<font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font></fonts>\
<fills count="3"><fill><patternFill patternType="none"/></fill>\
<fill><patternFill patternType="gray125"/></fill>\
<fill><patternFill patternType="solid"><fgColor rgb="FFE9EDF2"/><bgColor indexed="64"/></patternFill></fill></fills>\
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>\
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>\
<cellXfs count="6">\
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>\
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>\
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>\
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>\
<xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>\
<xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>\
</cellXfs>\
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>\
</styleSheet>"""


def columna(n: int) -> str:
    """1 -> A, 27 -> AA."""
    letras = ""
    while n:
        n, resto = divmod(n - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _serial(valor) -> float:
    """Los dias desde el 30 de diciembre de 1899: asi cuenta Excel."""
    base = datetime(1899, 12, 30)
    if isinstance(valor, datetime):
        # Excel no sabe de zonas: la hora va como se lee en el servidor.
        if valor.tzinfo is not None:
            valor = valor.astimezone().replace(tzinfo=None)
        delta = valor - base
        return delta.days + delta.seconds / 86400
    return (datetime(valor.year, valor.month, valor.day) - base).days


def _texto(valor) -> str:
    return escape(_CONTROL.sub("", str(valor)))


def _celda(ref: str, valor, tipo: str) -> str:
    if valor is None or valor == "":
        return ""
    if tipo in ("dinero", "entero"):
        numero = Decimal(str(valor))
        return f'<c r="{ref}" s="{_ESTILO[tipo]}"><v>{numero}</v></c>'
    if tipo in ("fecha", "momento") and isinstance(valor, (date, datetime)):
        return (f'<c r="{ref}" s="{_ESTILO[tipo]}">'
                f'<v>{_serial(valor)}</v></c>')
    texto = _texto(valor)
    espacio = ' xml:space="preserve"' if texto != texto.strip() else ""
    return (f'<c r="{ref}" t="inlineStr"><is><t{espacio}>{texto}</t>'
            f'</is></c>')


def _hoja(columnas: list, filas: list) -> str:
    ultima = columna(len(columnas))
    alto = len(filas) + 1
    anchos = "".join(
        f'<col min="{i}" max="{i}" width="{ancho}" customWidth="1"/>'
        for i, (_, _, ancho) in enumerate(columnas, start=1))
    encabezado = "".join(
        f'<c r="{columna(i)}1" t="inlineStr" s="1"><is><t>{_texto(titulo)}'
        f'</t></is></c>' for i, (titulo, _, _) in enumerate(columnas, start=1))
    renglones = [f'<row r="1">{encabezado}</row>']
    for n, fila in enumerate(filas, start=2):
        celdas = "".join(_celda(f"{columna(i)}{n}", valor, tipo)
                         for i, (valor, (_, tipo, _)) in
                         enumerate(zip(fila, columnas), start=1))
        renglones.append(f'<row r="{n}">{celdas}</row>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<dimension ref="A1:{ultima}{alto}"/>'
            '<sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>'
            '</sheetView></sheetViews>'
            '<sheetFormatPr defaultRowHeight="15"/>'
            f'<cols>{anchos}</cols>'
            f'<sheetData>{"".join(renglones)}</sheetData>'
            f'<autoFilter ref="A1:{ultima}{alto}"/>'
            '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" '
            'header="0.3" footer="0.3"/>'
            '</worksheet>')


def _nombre_de_hoja(nombre: str) -> str:
    """Excel no acepta estos signos en el nombre, ni mas de 31 letras."""
    return re.sub(r"[\[\]:*?/\\]", " ", nombre).strip()[:31] or "Hoja"


def libro(hojas: list[dict]) -> bytes:
    """hojas: [{"nombre": ..., "columnas": [(titulo, tipo, ancho)],
    "filas": [[valor, ...]]}]. Devuelve el .xlsx listo para bajar."""
    nombres = [_nombre_de_hoja(h["nombre"]) for h in hojas]
    libro_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>' + "".join(
            f'<sheet name="{escape(n, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
            for i, n in enumerate(nombres, start=1)) + '</sheets>'
        '<definedNames>' + "".join(
            f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" '
            f'hidden="1">\'{escape(n.replace(chr(39), chr(39) * 2))}\'!'
            f'$A$1:${columna(len(h["columnas"]))}${len(h["filas"]) + 1}'
            f'</definedName>'
            for i, (n, h) in enumerate(zip(nombres, hojas))) + '</definedNames>'
        '</workbook>')
    relaciones = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(hojas) + 1))
        + f'<Relationship Id="rId{len(hojas) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/></Relationships>')
    tipos = _TIPOS.format(hojas="".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, len(hojas) + 1)))

    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", tipos)
        z.writestr("_rels/.rels", _RAIZ)
        z.writestr("xl/workbook.xml", libro_xml)
        z.writestr("xl/_rels/workbook.xml.rels", relaciones)
        z.writestr("xl/styles.xml", _ESTILOS)
        for i, h in enumerate(hojas, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml",
                       _hoja(h["columnas"], h["filas"]))
    return salida.getvalue()


def leer(contenido: bytes) -> dict[str, list[list]]:
    """Lo que dice cada hoja, como texto. Es para las pruebas: confirma
    que lo que se escribio es lo que se lee, sin instalar nada."""
    import xml.etree.ElementTree as ET

    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        libro_xml = ET.fromstring(z.read("xl/workbook.xml"))
        salida = {}
        for i, hoja in enumerate(libro_xml.find("x:sheets", ns), start=1):
            datos = ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml"))
            filas = []
            for fila in datos.find("x:sheetData", ns):
                valores = {}
                for c in fila:
                    ref = re.match(r"[A-Z]+", c.get("r")).group(0)
                    t = c.find("x:is/x:t", ns)
                    v = c.find("x:v", ns)
                    valores[ref] = t.text if t is not None else (
                        v.text if v is not None else None)
                filas.append(valores)
            salida[hoja.get("name")] = filas
        return salida

#!/usr/bin/env python3
"""Revision estatica del proyecto, sin depender de nada instalado.

Existe por un error concreto: un `settings` que se usaba arriba y solo
se importaba dentro de una funcion de mas abajo. El codigo compilaba,
arrancaba, y reventaba en la primera peticion real —ocho pruebas en
rojo por una linea que ningun compilador iba a senalar.

Esta revision busca esa clase de cosa: lo que solo se descubre
ejecutando. Corre con la biblioteca estandar, asi que funciona en
cualquier maquina, con o sin red:

    python3 revisar.py

Devuelve 1 si encuentra algo. Lo que revisa:

  1. Nombres que se usan y no existen (Python).
  2. Imports que no se usan (Python).
  3. Funciones que se llaman y no estan declaradas (JS de la consola y
     de la app de campo).
  4. Claves de idioma que no existen en los tres idiomas.
  5. Actividades que un endpoint pide y nadie declaro.
  6. Bloques con "?" sin sus dos frases --y pantallas donde nadie
     decidio si lleva o no lleva.
  7. Texto visible escrito a mano, sin pasar por `t()`.
  8. Dos componentes con el mismo nombre de clase en la hoja de estilos.
  9. La cadena de migraciones: sin huecos, sin dos cabezas.
 10. Campos de la base que se usan y no existen en el modelo.
"""
import ast
import builtins
import io
import os
import re
import symtable
import sys
from collections import defaultdict

RAIZ = os.path.dirname(os.path.abspath(__file__))
CONOCIDOS = set(dir(builtins)) | {"__file__", "__name__", "__doc__",
                                  "__package__", "__spec__", "__builtins__",
                                  "__annotations__", "__debug__", "WindowsError"}

hallazgos = []


def apuntar(archivo: str, linea, que: str) -> None:
    rel = os.path.relpath(archivo, RAIZ)
    hallazgos.append(f"{rel}:{linea}: {que}")


def archivos(carpeta: str, extension: str):
    for base, dirs, nombres in os.walk(os.path.join(RAIZ, carpeta)):
        dirs[:] = [d for d in dirs
                   if d not in ("__pycache__", "_to_delete", ".git")]
        for n in sorted(nombres):
            if n.endswith(extension):
                yield os.path.join(base, n)


# ==================================================================
# 1 y 2 · Python: nombres que no existen, imports que sobran
# ==================================================================

def _globales(tabla: symtable.SymbolTable, techo: set, archivo: str) -> None:
    """Recorre los ambitos buscando nombres globales sin dueno.

    `symtable` ya resolvio a que ambito pertenece cada nombre. Un
    nombre marcado como global que no esta en el modulo ni es un
    builtin no lo va a encontrar nadie en tiempo de ejecucion.
    """
    for simbolo in tabla.get_symbols():
        nombre = simbolo.get_name()
        if (simbolo.is_global() and simbolo.is_referenced()
                and nombre not in techo and nombre not in CONOCIDOS):
            apuntar(archivo, tabla.get_lineno(),
                    f"usa '{nombre}' y no existe en este archivo "
                    f"(dentro de {tabla.get_name()})")
    for hija in tabla.get_children():
        _globales(hija, techo, archivo)


def _importados(arbol: ast.AST) -> dict:
    """Nombre local -> linea, para los imports de nivel de modulo."""
    traidos = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                traidos[(a.asname or a.name).split(".")[0]] = nodo.lineno
        elif isinstance(nodo, ast.ImportFrom):
            for a in nodo.names:
                if a.name != "*":
                    traidos[a.asname or a.name] = nodo.lineno
    return traidos


def _usados(arbol: ast.AST) -> set:
    usados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            usados.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            raiz = nodo
            while isinstance(raiz, ast.Attribute):
                raiz = raiz.value
            if isinstance(raiz, ast.Name):
                usados.add(raiz.id)
    # Lo que se nombra solo en anotaciones de texto ("Persona") tambien
    # cuenta: quitar ese import rompe el modelo al arrancar.
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            for palabra in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", nodo.value):
                usados.add(palabra)
    return usados


def revisar_python() -> None:
    for archivo in list(archivos("app", ".py")) + list(archivos("tests", ".py")):
        fuente = io.open(archivo, encoding="utf-8").read()
        try:
            arbol = ast.parse(fuente, archivo)
            tabla = symtable.symtable(fuente, archivo, "exec")
        except SyntaxError as e:
            apuntar(archivo, e.lineno, f"no compila: {e.msg}")
            continue

        techo = {s.get_name() for s in tabla.get_symbols()}
        _globales(tabla, techo, archivo)

        usados = _usados(arbol)
        renglones = fuente.split(chr(10))
        for nombre, linea in _importados(arbol).items():
            # `# noqa` en el renglon significa "esta aqui a proposito":
            # el import de models en main.py registra las tablas y
            # quitarlo rompe el arranque sin que nadie lo note hasta
            # la primera consulta.
            if '# noqa' in renglones[linea - 1]:
                continue
            if nombre not in usados:
                apuntar(archivo, linea, f"importa '{nombre}' y no lo usa")


# ==================================================================
# 3 · JS: funciones que se llaman y no estan
# ==================================================================

# Lo que el navegador trae puesto. No es exhaustivo a proposito: si
# algo legitimo aparece como hallazgo, se agrega aqui y ya.
DEL_NAVEGADOR = {
    "console", "document", "window", "navigator", "location", "fetch",
    "setTimeout", "setInterval", "clearInterval", "clearTimeout", "alert",
    "confirm", "prompt", "Date", "Math", "JSON", "Object", "Array", "String",
    "Number", "Boolean", "Promise", "Error", "Map", "Set", "RegExp", "URL",
    "localStorage", "sessionStorage", "FormData", "Blob", "File", "Image",
    "Intl", "parseInt", "parseFloat", "isNaN", "encodeURIComponent",
    "decodeURIComponent", "btoa", "atob", "structuredClone", "queueMicrotask",
    "requestAnimationFrame", "Notification", "self", "caches", "atob",
    "TextEncoder", "TextDecoder", "Uint8Array", "AbortController", "Event",
    "CustomEvent", "IntersectionObserver", "ResizeObserver", "crypto",
    "performance", "history", "screen", "matchMedia", "getComputedStyle",
    "Symbol", "BigInt", "Function", "Reflect", "Proxy", "WeakMap", "WeakSet",
    "if", "for", "while", "switch", "catch", "return", "typeof", "await",
    "function", "super", "this", "new", "else", "do", "try", "of", "in",
    "async", "yield", "delete", "void", "instanceof", "case",
    # `import("./x.js")` se escribe como una llamada y no lo es: es la
    # forma diferida de importar, la que carga una pantalla solo cuando
    # alguien la abre. Sin esto, cada carga perezosa se reportaba como
    # una funcion inventada.
    "import",
}

# Un parametro con valor por omision que ademas es una funcion
# —`disponibilidad = () => null`— parte la lista de parametros en dos
# para cualquier expresion regular ingenua, porque el parentesis que
# cierra llega antes de tiempo. Buscar el nombre por su igual lo
# resuelve sin tener que entender la firma completa.
ASIGNADO = re.compile(r"([A-Za-z_$][\w$]*)\s*=(?![=>])")

# Un metodo escrito corto —`token() { ... }` dentro de una clase o de un
# objeto— se declara aqui mismo. Sin esto, cada metodo se leia como una
# llamada a algo que no existe.
METODO = re.compile(r"^\s*(?:static\s+|async\s+|get\s+|set\s+|\*\s*)*"
                    r"([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.M)

# Y una propiedad de objeto (`hoy: ...`, `marcar(f)` como valor) tampoco
# es una funcion suelta.
PROPIEDAD = re.compile(r"([A-Za-z_$][\w$]*)\s*:", re.M)

DECLARA = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"
    r"|^\s*(?:export\s+)?(?:const|let|var|class)\s+([A-Za-z_$][\w$]*)"
    r"|^\s*import\s+.*?[{,\s]([A-Za-z_$][\w$]*)\s*[,}]"
    r"|^\s*import\s+([A-Za-z_$][\w$]*)\s+from", re.M)

LLAMA = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(")


def _limpiar(js: str) -> str:
    """Borra comentarios y textos, dejando los renglones en su sitio.

    Dos razones. Una: dentro de un texto en espanol hay parentesis
    —"marcar el panico (rojo)"— que se leen como llamadas a funciones
    que no existen, y idioma.js es practicamente puro texto. Otra: si
    al borrar se comen los saltos de linea, el numero de renglon que se
    reporta deja de coincidir con el archivo, y un hallazgo con el
    renglon equivocado hace perder mas tiempo del que ahorra.

    Por eso lo que se borra se reemplaza por espacios, y los saltos de
    linea se conservan tal cual.
    """
    salida = []
    i, n = 0, len(js)
    while i < n:
        c = js[i]
        par = js[i:i + 2]
        if par == "//":
            while i < n and js[i] != "\n":
                salida.append(" ")
                i += 1
        elif par == "/*":
            cierre = js.find("*/", i + 2)
            cierre = n if cierre == -1 else cierre + 2
            for ch in js[i:cierre]:
                salida.append("\n" if ch == "\n" else " ")
            i = cierre
        elif c in "\"'`":
            comilla = c
            salida.append(" ")
            i += 1
            while i < n:
                if js[i] == "\\":
                    salida.append("  ")
                    i += 2
                    continue
                if js[i] == comilla:
                    salida.append(" ")
                    i += 1
                    break
                salida.append("\n" if js[i] == "\n" else " ")
                i += 1
        else:
            salida.append(c)
            i += 1
    return "".join(salida)


def revisar_js() -> None:
    for archivo in list(archivos("app/web", ".js")):
        bruto = io.open(archivo, encoding="utf-8").read()
        js = _limpiar(bruto)

        # El primer argumento de `conAyuda` es la ETIQUETA --"h3"-- y el
        # segundo el texto. Pasarle un numero pasa el compilador, pasa
        # el barrido de textos, y revienta AL PINTAR con un
        # InvalidCharacterError que tumba la pantalla entera. Paso tres
        # veces el mismo dia y no se vio hasta que una no abrio.
        if archivo.endswith("util.js"):
            pass                 # ahi vive la definicion
        else:
            # Sobre el texto CRUDO: `_limpiar` vacia las cadenas para
            # que el barrido de claves no se confunda, y aqui lo que se
            # revisa es justamente si el primer argumento es una cadena.
            for m in re.finditer(r"conAyuda\(\s*([^,]+),", bruto):
                arg = m.group(1).strip()
                if arg.startswith('"') or arg.startswith("'"):
                    continue
                apuntar(archivo, bruto[:m.start()].count("\n") + 1,
                        f"conAyuda({arg}, ...): el primer argumento es la "
                        f"etiqueta, como \"h3\". Un numero tumba la "
                        f"pantalla al pintar")

        declarados = set()
        for grupos in DECLARA.findall(js):
            declarados |= {g for g in grupos if g}
        # Lo que llega por import con llaves, en cualquier forma.
        for bloque in re.findall(r"import\s*{([^}]*)}", js):
            for parte in bloque.split(","):
                parte = parte.strip().split(" as ")[-1].strip()
                if parte:
                    declarados.add(parte)
        # Parametros y variables de funcion: aqui no interesa el ambito
        # fino, solo que el nombre exista en alguna parte del archivo.
        for grupos in re.findall(r"(?:function\s*\w*\s*\(([^)]*)\)"
                                 r"|\(([^)]*)\)\s*=>"
                                 r"|([A-Za-z_$][\w$]*)\s*=>)", js):
            for g in grupos:
                for parte in re.split(r"[,\s{}\[\]:=.()]+", g):
                    if parte and not parte.startswith("..."):
                        declarados.add(parte.lstrip("."))
        for nombre in re.findall(r"(?:const|let|var)\s*[{\[]([^}\]]*)[}\]]", js):
            for parte in re.split(r"[,\s:]+", nombre):
                if parte:
                    declarados.add(parte)
        declarados |= set(METODO.findall(js))
        declarados |= set(PROPIEDAD.findall(js))
        declarados |= set(ASIGNADO.findall(js))

        for numero, linea in enumerate(js.split("\n"), 1):
            for nombre in LLAMA.findall(linea):
                if (nombre not in declarados and nombre not in DEL_NAVEGADOR
                        and not nombre[0].isupper()):
                    apuntar(archivo, numero,
                            f"llama a {nombre}() y no esta declarada aqui")


# ==================================================================
# 4 · Idioma: toda clave tiene que existir tres veces
# ==================================================================

def revisar_idioma() -> None:
    idioma = os.path.join(RAIZ, "app/web/idioma.js")
    if not os.path.exists(idioma):
        return
    fuente = io.open(idioma, encoding="utf-8").read()

    definidas = defaultdict(int)
    for clave in re.findall(r"^\s{4}([a-z][\w]*)\s*:", fuente, re.M):
        definidas[clave] += 1

    for clave, veces in sorted(definidas.items()):
        if veces != 3:
            apuntar(idioma, 0,
                    f"'{clave}' esta {veces} de 3 veces: falta en algun idioma")

    usadas = set()
    for archivo in archivos("app/web", ".js"):
        if archivo == idioma:
            continue
        fuente = io.open(archivo, encoding="utf-8").read()
        for clave in re.findall(r'\b(?:t|con)\(\s*["\']([\w]+)["\']', fuente):
            usadas.add((clave, archivo))
        # El menu de arriba nombra sus textos en una tabla --`texto:` es
        # lo que dice el boton y `cuenta:` lo que el recorrido de la
        # primera vez explica de esa entrada-- y de ahi salen como
        # variables, no como `t("...")`. Sin esto, agregar una pantalla
        # al menu y olvidar su texto no lo caza nadie: la barra saldria
        # con la clave escrita.
        for clave in re.findall(r'\b(?:texto|cuenta):\s*["\']([\w]+)["\']',
                                fuente):
            usadas.add((clave, archivo))

    for clave, archivo in sorted(usadas):
        if clave not in definidas:
            apuntar(archivo, 0, f"usa el texto '{clave}' y no esta traducido")


# ==================================================================
# 4 bis · Actividades: la que no existe no la puede nadie
# ==================================================================

def revisar_actividades() -> None:
    """Toda actividad que pide un endpoint tiene que estar declarada.

    `permisos.roles_de` devuelve un conjunto vacio para una actividad que
    no conoce, y `auth.puede` lo traduce a "nadie salvo el administrador".
    Asi que una letra de mas cierra una puerta para toda la empresa y no
    revienta nada: se descubre el dia que alguien no puede trabajar.

    Se revisan dos cosas. La primera es el caso comun: `puede("x")` con
    la cadena a la vista. La segunda es el que se escapa --las
    actividades que viajan dentro de una tabla, como las de `crud_router`
    en catalogos.py-- y para eso se mira cualquier texto que empiece con
    un prefijo ya declarado: si alguien escribe "viaticos.asigner", ese
    prefijo existe y el nombre completo no.
    """
    permisos = os.path.join(RAIZ, "app/permisos.py")
    if not os.path.exists(permisos):
        return
    fuente = io.open(permisos, encoding="utf-8").read()
    declaradas = set(re.findall(r'^\s{4}"([a-z][\w.]*)":\s*\{', fuente, re.M))
    if not declaradas:
        return
    prefijos = {a.split(".")[0] for a in declaradas}

    for archivo in archivos("app", ".py"):
        if archivo == permisos:
            continue
        texto = io.open(archivo, encoding="utf-8").read()
        for numero, linea in enumerate(texto.split("\n"), 1):
            dichas = set(re.findall(r'puede\(\s*["\']([\w.]+)["\']', linea))
            for actividad in dichas:
                if actividad not in declaradas:
                    apuntar(archivo, numero,
                            f"pide la actividad '{actividad}' y no esta "
                            "declarada en permisos.py: nadie podria hacerla")
            # El barrido suelto solo en los routers: ahi viven las tablas
            # que llevan la actividad adentro. En models.py una cadena con
            # punto es una llave foranea --"cierre.id"-- y no una
            # actividad.
            if "/routers/" not in archivo:
                continue
            for suelta in re.findall(r'["\']([a-z_]+\.[a-z_]+)["\']', linea):
                if suelta in dichas:
                    continue          # ya se dijo arriba, con mejor mensaje
                if suelta.split(".")[0] in prefijos and suelta not in declaradas:
                    apuntar(archivo, numero,
                            f"'{suelta}' parece una actividad y no esta "
                            "declarada en permisos.py")


# ==================================================================
# 5 · Migraciones: una sola cadena, una sola cabeza
# ==================================================================

# ==================================================================
# 4 ter · La ayuda en pantalla: el "?" que no puede mentir por omision
# ==================================================================

def revisar_ayuda() -> None:
    """Todo bloque con "?" tiene que traer sus dos frases, en los tres
    idiomas.

    `conAyuda()` arma las claves pegando sufijos al nombre que recibe,
    asi que una letra de mas no revienta nada: `t()` devuelve la clave
    cuando no la encuentra y el usuario ve `ay_fin_depozitos_para` escrito
    en la pantalla. Es el mismo agujero que dejaba una clave armada al
    vuelo, y la razon por la que `util.js` tiene escrito que eso no se
    hace.

    Aqui no se puede evitar --el sufijo es lo que da la estructura de las
    tres frases-- asi que en vez de prohibirlo, se revisa.

    `_numero` es opcional a proposito: solo tiene sentido donde hay una
    cifra que alguien va a querer cuadrar, y un renglon vacio con su
    titulito ensena que los "?" traen relleno.
    """
    idioma = os.path.join(RAIZ, "app/web/idioma.js")
    if not os.path.exists(idioma):
        return
    declaradas = set(re.findall(r"^\s{4}([a-z][\w]*)\s*:",
                                io.open(idioma, encoding="utf-8").read(), re.M))

    for archivo in archivos("app/web", ".js"):
        if archivo == idioma:
            continue
        texto = io.open(archivo, encoding="utf-8").read()
        for posicion, clave in _claves_de_ayuda(texto):
            numero = texto.count("\n", 0, posicion) + 1
            for sufijo in ("_para", "_cuando"):
                if clave + sufijo not in declaradas:
                    apuntar(archivo, numero,
                            f"el '?' de '{clave}' no tiene "
                            f"'{clave}{sufijo}' traducido")


# Texto que se pinta y que a simple vista no es texto: un guion largo,
# un separador, una unidad. No hace falta traducirlos.
NO_ES_TEXTO = {"—", "-", "·", "/", "km", "h", "m", "N/A", "OK", "ID",
               # Ejemplos que se enseñan tal cual: una placa, un
               # modelo, el nombre del letrero en el aeropuerto.
               "ABC-123-D", "Suburban", "Frankfurt", "MR. BROOKS",
               "Centauro", "CENTAURO", "0000", "0.00"}

# Donde mas se asoma el texto que no pasa por `t()`: un aviso, una
# confirmacion, un renglon que se reescribe a mano, la sombra de una
# caja de texto.
BOCAS = re.compile(
    r"(?:\balert\(|\bconfirm\(|\.textContent\s*=\s*"
    r"|\.placeholder\s*=\s*|\bplaceholder:\s*)"
    r'\s*"([^"]{3,})"')

# Un literal de JavaScript, de cualquiera de las tres formas.
LITERAL = re.compile(r'"([^"\\\n]*(?:\\.[^"\\\n]*)*)"'
                     r"|'([^'\\\n]*(?:\\.[^'\\\n]*)*)'"
                     r"|`([^`]*)`")

# Las letras que no se escriben en ingles ni en portugues igual que
# en espanol, mas los signos de apertura. Una cadena que las trae
# esta escrita en espanol y la va a leer alguien.
ACENTOS = "áéíóúüñÁÉÍÓÚÑ¿¡"

# Una plantilla de JavaScript, con lo que lleva dentro.
PLANTILLA = re.compile(r"`([^`]*)`")


def _sin_comentarios(texto: str) -> str:
    """El mismo archivo con los comentarios en blanco.

    Los comentarios de este sistema estan escritos en espanol y con
    acentos: si no se borran, cada parrafo explicando por que una
    pantalla hace lo que hace sale como un texto sin traducir. Se
    reemplazan por espacios y no se borran para que los renglones sigan
    cayendo donde estaban.
    """
    texto = re.sub(r"/\*.*?\*/",
                   lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                   texto, flags=re.S)
    renglones = []
    for linea in texto.split("\n"):
        i = linea.find("//")
        # Una barra doble dentro de comillas o detras de dos puntos es una
        # direccion de internet, no un comentario.
        while i >= 0 and (linea[i - 1:i] == ":" or linea[:i].count('"') % 2):
            i = linea.find("//", i + 2)
        renglones.append(linea[:i] if i >= 0 else linea)
    return "\n".join(renglones)


def revisar_texto_suelto() -> None:
    """Texto visible escrito a mano en una pantalla, sin pasar por `t()`.

    `revisar_idioma` barre las claves que se USAN: caza la que falta en un
    idioma, no la pantalla que no usa ninguna. Asi vivio `nomina.js` con
    cinco encabezados en espanol duro --tres llamadas a `t()` contra 364
    en servicio-- y nadie lo vio hasta que alguien fue a contarlas. Un
    usuario en Brasil abria la nomina y la leia en espanol.

    Se mira el tercer argumento de `h(...)`, que es donde van los hijos:
    lo que esta despues del objeto de atributos se pinta. Los dos
    primeros --la etiqueta y los atributos-- llevan clases, estilos y
    rutas, y esos no son texto de nadie.

    La app de campo estuvo excluida un rato: estaba escrita entera en
    espanol y traducirla era un trabajo aparte. Ya no lo esta --87 textos
    en tres idiomas, 19 sep-- y el candado la cubre como a la consola.
    """
    patron = re.compile(
        r'h\(\s*"[a-z0-9]+"\s*,\s*(?:\{[^{}]*\}|\{\})\s*,\s*"([^"]{2,})"')
    idioma = os.path.join(RAIZ, "app/web/idioma.js")

    for archivo in archivos("app/web", ".js"):
        if archivo == idioma:
            continue
        texto = io.open(archivo, encoding="utf-8").read()
        for encontrado in patron.finditer(texto):
            visible = encontrado.group(1)
            if visible.strip() in NO_ES_TEXTO:
                continue
            if not re.search(r"[A-Za-z\u00c0-\u017f]{3,}", visible):
                continue
            numero = texto.count("\n", 0, encontrado.start()) + 1
            apuntar(archivo, numero,
                    f'texto escrito a mano: "{visible[:45]}". Va en '
                    f"idioma.js y se pinta con t()")

        # Y el que va dentro de una plantilla. Es el que mas facil se
        # escapa: al traducir una pantalla se cambian las cadenas entre
        # comillas y las plantillas se quedan, porque no se ven como
        # texto sino como codigo. Asi quedo `Semana del ${fecha(...)}` en
        # la nomina, en medio de una pantalla ya traducida.
        for encontrado in PLANTILLA.finditer(texto):
            dentro = encontrado.group(1)
            if "${" not in dentro:
                continue            # sin huecos lo caza la regla de arriba
            # Fuera lo que no es texto: estilos, HTML, rutas de la API.
            if any(x in dentro for x in (";", "<", "</", "//")):
                continue
            # Una plantilla que ya llama a `t()` esta traducida: lo que
            # queda fuera de los huecos son separadores, no texto.
            if "t(" in dentro:
                continue
            sin_huecos = re.sub(r"\$\{[^}]*\}", "", dentro)
            if not re.search(r"[A-Za-z\u00c0-\u017f]{3,}", sin_huecos):
                continue
            if " " not in sin_huecos.strip():
                continue
            numero = texto.count("\n", 0, encontrado.start()) + 1
            apuntar(archivo, numero,
                    f'texto en una plantilla: "{dentro[:45]}". Va en '
                    f"idioma.js con {{huecos}} y se arma con replace()")

        # Y el que no se pinta con `h()` sino que se dice de otra forma:
        # un `alert`, un `confirm`, un renglon que se reescribe solo, la
        # sombra de una caja de texto. Asi sobrevivieron en la app de
        # campo cien textos a la primera traduccion: la regla de arriba
        # mira el tercer argumento de `h()` y estos no estan ahi.
        crudo = _sin_comentarios(texto)
        for encontrado in BOCAS.finditer(crudo):
            visible = encontrado.group(1)
            if visible.strip() in NO_ES_TEXTO:
                continue
            if not re.search(r"[A-Za-z\u00c0-\u017f]{3,}", visible):
                continue
            # Un ejemplo de una sola palabra --una placa, un modelo-- se
            # lee igual en los tres idiomas.
            if " " not in visible.strip():
                continue
            numero = crudo.count("\n", 0, encontrado.start()) + 1
            apuntar(archivo, numero,
                    f'texto sin traducir: "{visible[:45]}". Va en '
                    f"idioma.js y se pide con t()")

        # La ultima red, y la mas barata: una cadena con un acento o un
        # signo de apertura esta escrita en espanol, este donde este.
        for encontrado in LITERAL.finditer(crudo):
            visible = (encontrado.group(1) or encontrado.group(2)
                       or encontrado.group(3) or "")
            if not any(c in visible for c in ACENTOS):
                continue
            if visible.strip() in NO_ES_TEXTO:
                continue
            numero = crudo.count("\n", 0, encontrado.start()) + 1
            apuntar(archivo, numero,
                    f'texto en espanol: "{visible[:45]}". Va en '
                    f"idioma.js y se pide con t()")


def _claves_de_ayuda(texto: str):
    """El tercer argumento de cada `conAyuda(...)`.

    No se puede sacar con una expresion por renglon: la llamada casi
    siempre se parte en dos lineas y el titulo lleva comas adentro
    --`t("x").replace("{n}", filas.length)`--. Asi que se cuentan
    parentesis, comillas y llaves, igual que haria quien lo lee.
    """
    for encontrado in re.finditer(r"\bconAyuda\(", texto):
        i = encontrado.end()
        hondo, comas, inicio_arg = 1, 0, i
        while i < len(texto) and hondo:
            c = texto[i]
            if c in "([{":
                hondo += 1
            elif c in ")]}":
                hondo -= 1
            elif c in "\"'`":
                cierre = c
                i += 1
                while i < len(texto) and texto[i] != cierre:
                    i += 2 if texto[i] == "\\" else 1
            elif c == "," and hondo == 1:
                comas += 1
                if comas == 2:
                    inicio_arg = i + 1
                elif comas == 3:
                    break
            i += 1
        if comas >= 2:
            tercero = re.match(r'\s*"([\w]+)"', texto[inicio_arg:i])
            if tercero:
                yield encontrado.start(), tercero.group(1)


# El padron de los "?": cuantos lleva cada pantalla.
#
# `revisar_ayuda` le exige sus dos frases a cada bloque que YA tiene "?".
# Es la misma forma de agujero que dejo cien textos en espanol en la app
# de campo: una red que solo mira lo que alguien ya decidio marcar
# declara "terminado" lo que nunca se miro. Una pantalla nueva sin un
# solo "?" pasaba limpia, y nadie se enteraba de que a nadie le habian
# preguntado.
#
# Asi que cada pantalla dice su numero. Si manana hay menos, alguien
# borro un "?" sin querer. Si hay mas, el padron se quedo viejo y hay
# que decirlo aqui: escribir el numero es la forma de que el cambio pase
# por la cabeza de alguien.
#
# Un cero tambien es una respuesta --y de las buenas--. Lo que no se
# vale es que el archivo no este.
# El primer argumento de `conAyuda` es la ETIQUETA --"h3"-- y el segundo
# el texto. Pasarle un numero --conAyuda(2, h("h3", ...), clave)-- pasa
# el compilador, pasa el barrido de textos, y revienta al pintar con un
# InvalidCharacterError que tumba la pantalla entera. Paso tres veces el
# mismo dia y nadie lo vio hasta que una pantalla no abrio.
AYUDA_POR_PANTALLA = {
    # --- las que llevan
    "accesos.js": 1,
    "bonos.js": 2,
    "bitacora.js": 3,
    "encuestas.js": 1,
    "personal.js": 1,
    "categorias.js": 2,
    "central.js": 5,
    "consultor.js": 4,
    "facturacion.js": 1,
    "finanzas.js": 5,
    "implantado.js": 9,
    "nomina.js": 3,
    "panorama.js": 6,
    "servicio.js": 9,

    # --- las que no, y por que
    "api.js": 0,        # habla con el servidor; no pinta nada
    "app.js": 0,        # el armazon: la barra, las rutas, la entrada
    "catalogos.js": 0,  # tablas de catalogo: la columna se llama como lo que trae
    # La tarjeta de visto bueno y facturacion lleva su "?", pero la clave
    # la pone quien la pinta --servicio.js el del eventual, implantado.js
    # el del mes-- porque cada una explica otra cosa.
    "cierre.js": 0,
    "codigo.js": 0,     # cuatro digitos y una contrasena nueva; no hay alcance que explicar
    # Antes de entrar: crear la contrasena con el enlace del correo y
    # pedir ese enlace. Sus reglas van escritas en la misma tarjeta.
    "contrasena.js": 0,
    "idioma.js": 0,     # la tabla de textos
    "mapa.js": 0,       # el buscador de direcciones, que vive dentro de otra pantalla
    "util.js": 0,       # aqui vive `conAyuda`, entre otras cosas
    # El recorrido ES ayuda: la capa 3. Ponerle un "?" a la ayuda seria
    # explicar la explicacion.
    "recorrido.js": 0,

    # --- la app de campo no lleva "?", y es a proposito
    #
    # La consola se usa sentado: abrir un panel para leer tres renglones
    # cuesta un clic y se puede. El de campo va con una mano, con prisa y
    # media barra de senal; ahi la ayuda tiene que estar ya escrita en la
    # pantalla, sin tocar nada. Por eso cada tarjeta trae su pie
    # --`cmp_*_pie`-- y no un signo que haya que descubrir.
    "campo/app.js": 0,
    "campo/cola.js": 0,
    "campo/foto.js": 0,
    "campo/memoria.js": 0,
    "campo/sw.js": 0,
}


def revisar_padron_ayuda() -> None:
    """Que ninguna pantalla se quede sin que nadie le haya preguntado."""
    base = os.path.join(RAIZ, "app/web")
    if not os.path.isdir(base):
        return

    vistos = set()
    for archivo in archivos("app/web", ".js"):
        rel = os.path.relpath(archivo, base).replace(os.sep, "/")
        vistos.add(rel)
        texto = io.open(archivo, encoding="utf-8").read()
        cuantos = len(list(_claves_de_ayuda(texto)))

        if rel not in AYUDA_POR_PANTALLA:
            apuntar(archivo, 0,
                    "pantalla que nadie miro: di en AYUDA_POR_PANTALLA "
                    "cuantos '?' lleva. Cero tambien es una respuesta")
            continue

        esperados = AYUDA_POR_PANTALLA[rel]
        if cuantos < esperados:
            apuntar(archivo, 0,
                    f"tenia {esperados} '?' y quedan {cuantos}: se borro "
                    "uno. Si fue a proposito, cambia el numero")
        elif cuantos > esperados:
            apuntar(archivo, 0,
                    f"el padron dice {esperados} '?' y hay {cuantos}: "
                    "pon el numero nuevo en AYUDA_POR_PANTALLA")

    for rel in sorted(set(AYUDA_POR_PANTALLA) - vistos):
        apuntar(os.path.join(base, rel), 0,
                "esta en AYUDA_POR_PANTALLA y ya no existe: quitalo")


# Lo que decide la caja de un elemento. Si dos reglas distintas se lo
# ponen a la misma clase, no son dos ajustes: son dos componentes
# peleandose por un nombre.
CAJA = {"display", "position", "width", "height", "flex", "float"}


def _sin_arroba(texto: str) -> str:
    """El mismo archivo sin los bloques @media.

    Ahi la misma clase se ajusta a proposito para una pantalla chica, y
    eso no es un choque de nombres.
    """
    salida, i = [], 0
    while i < len(texto):
        j = texto.find("@media", i)
        if j < 0:
            salida.append(texto[i:])
            break
        salida.append(texto[i:j])
        k, hondo = texto.find("{", j), 0
        while k < len(texto):
            if texto[k] == "{":
                hondo += 1
            elif texto[k] == "}":
                hondo -= 1
                if not hondo:
                    break
            k += 1
        i = k + 1
    return "".join(salida)


def revisar_estilos() -> None:
    """Dos cosas distintas con el mismo nombre de clase.

    De aqui salio el peor rato de la consola. El panorama trajo una
    `.barra` --el tramo que pinta un servicio sobre el eje del dia-- y
    el encabezado de la consola es `<header class="barra">`. La regla
    nueva no declaraba `position`, que `header.barra` si declara y gana,
    pero si declaraba `height: 10px`, y eso nadie lo disputaba: con
    `box-sizing: border-box` el encabezado quedo en dieciocho pixeles de
    alto, con el logo y el menu colgando fuera de su caja. Como la caja
    no ocupaba lugar, la pantalla entera arrancaba debajo del filo azul
    y el titulo se pintaba ENCIMA del menu.

    En el mismo commit venia `.punto`, que ya era el renglon de "una
    persona con su palomita" de la central: cada integrante del equipo
    se volvio una bolita de nueve pixeles con el nombre desbordado sobre
    la lista de pendientes. Y `.atender`, que es componente y tambien
    nivel: `tarjeta estado atender` se llevaba el `display:flex` del
    renglon.

    Tres en un commit, ninguno lo vio nadie durante dias, y desde el
    codigo no se ve: cada archivo por separado esta bien escrito. Por
    eso se revisa la hoja, que es donde se cruzan.

    Un nombre generico --barra, punto, atender-- no falla el dia que se
    escribe. Falla el dia que alguien toca la otra cosa.
    """
    for archivo in archivos("app/web", ".css"):
        texto = re.sub(r"/\*.*?\*/", "", io.open(archivo, encoding="utf-8").read(),
                       flags=re.S)
        texto = _sin_arroba(texto)

        base = defaultdict(int)      # `.clase` sola, y le pone la caja
        con_etiqueta = defaultdict(set)   # `tag.clase`
        modificador = defaultdict(set)    # `.otra.clase`

        for selector, cuerpo in re.findall(r"([^{}]+)\{([^{}]*)\}", texto):
            props = {p.split(":")[0].strip() for p in cuerpo.split(";") if ":" in p}
            pone_caja = bool(props & CAJA)
            for uno in (x.strip() for x in selector.split(",")):
                # Solo los selectores de una pieza: un descendiente
                # (`.caja .punto`) ya esta acotado y no le pega a nadie mas.
                if not uno or any(c in uno for c in " >+~"):
                    continue
                partido = re.match(r"^([a-z]+)?((?:\.[\w-]+)+)(?::[\w-]+)?$", uno)
                if not partido:
                    continue
                etiqueta = partido.group(1)
                clases = partido.group(2).strip(".").split(".")
                if etiqueta:
                    if pone_caja:
                        con_etiqueta[clases[0]].add(uno)
                    continue
                if len(clases) == 1:
                    if pone_caja:
                        base[clases[0]] += 1
                else:
                    for c in clases[1:]:
                        modificador[c].add(uno)

        for clase, veces in sorted(base.items()):
            if veces > 1:
                apuntar(archivo, 0,
                        f"'.{clase}' tiene {veces} reglas que le ponen la "
                        "caja: son dos componentes con el mismo nombre")
            if clase in con_etiqueta:
                otro = sorted(con_etiqueta[clase])[0]
                apuntar(archivo, 0,
                        f"'.{clase}' existe suelta y tambien como '{otro}': "
                        "la suelta le pega tambien al otro")
            if clase in modificador:
                otro = sorted(modificador[clase])[0]
                apuntar(archivo, 0,
                        f"'.{clase}' es un componente y ademas el "
                        f"modificador de '{otro}'")


def revisar_migraciones() -> None:
    carpeta = os.path.join(RAIZ, "migrations/versions")
    if not os.path.isdir(carpeta):
        return

    padres, hijos = {}, defaultdict(list)
    for archivo in archivos("migrations/versions", ".py"):
        fuente = io.open(archivo, encoding="utf-8").read()
        rev = re.search(r'^revision(?:\s*:[^=]+)?\s*=\s*["\']([^"\']+)',
                        fuente, re.M)
        pad = re.search(r'^down_revision(?:\s*:[^=]+)?\s*=\s*'
                        r'(?:["\']([^"\']+)|None)', fuente, re.M)
        if not rev:
            apuntar(archivo, 0, "no declara revision")
            continue
        padres[rev.group(1)] = pad.group(1) if pad and pad.group(1) else None
        hijos[pad.group(1) if pad and pad.group(1) else None].append(
            (rev.group(1), archivo))

    cabezas = [r for r in padres if r not in {p for p in padres.values()}]
    if len(cabezas) > 1:
        hallazgos.append(
            "migrations: hay " + str(len(cabezas)) + " cabezas ("
            + ", ".join(sorted(cabezas)) + "). Alembic no sabe cual aplicar.")

    for padre, lista in hijos.items():
        if padre is not None and len(lista) > 1:
            hallazgos.append(
                f"migrations: {padre} tiene {len(lista)} hijas "
                + ", ".join(r for r, _ in lista) + ". La cadena se bifurca.")

    for rev, padre in padres.items():
        if padre is not None and padre not in padres:
            hallazgos.append(
                f"migrations: {rev} cuelga de {padre}, que no existe.")


# ==================================================================
# 6 * Los modelos: campos que no existen
# ==================================================================


MODELOS = os.path.join(RAIZ, "app/models.py")
# Lo que SQLAlchemy le cuelga a toda instancia sin que aparezca escrito.
DE_LA_CASA = {"metadata", "registry"}


def _destino(anotacion) -> tuple:
    """De `Mapped[list["Jornada"]]` saca ("Jornada", True). El segundo
    dice si es una lista, que es lo que se puede recorrer con un for."""
    texto = ast.unparse(anotacion) if anotacion is not None else ""
    if not texto.startswith("Mapped["):
        return None, False
    dentro = texto[len("Mapped["):-1].strip().strip('"\'')
    lista = dentro.startswith("list[")
    if lista:
        dentro = dentro[len("list["):-1]
    dentro = dentro.strip().strip('"\'').split("|")[0].strip().strip('"\'')
    return (dentro or None), lista


def _leer_modelos() -> tuple:
    if not os.path.isfile(MODELOS):
        return {}, {}, {}
    arbol = ast.parse(io.open(MODELOS, encoding="utf-8").read())
    campos, tipos, listas, padres = {}, {}, {}, {}
    for nodo in arbol.body:
        if not isinstance(nodo, ast.ClassDef):
            continue
        # Solo las tablas. Los enums viven en el mismo archivo y a ellos
        # si se les puede pedir .value y .name.
        if "Base" not in [ast.unparse(b) for b in nodo.bases]:
            continue
        nombres, suyos, delista = set(), {}, set()
        for base in nodo.bases:
            if isinstance(base, ast.Name) and base.id != "Base":
                padres[nodo.name] = base.id
        for hijo in nodo.body:
            if isinstance(hijo, ast.AnnAssign) and isinstance(hijo.target, ast.Name):
                nombres.add(hijo.target.id)
                destino, es_lista = _destino(hijo.annotation)
                if destino:
                    suyos[hijo.target.id] = destino
                    if es_lista:
                        delista.add(hijo.target.id)
            elif isinstance(hijo, ast.Assign):
                for t in hijo.targets:
                    if isinstance(t, ast.Name):
                        nombres.add(t.id)
            elif isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nombres.add(hijo.name)
        campos[nodo.name] = nombres
        tipos[nodo.name] = suyos
        listas[nodo.name] = delista
    for hijo, padre in padres.items():
        if padre in campos:
            campos[hijo] |= campos[padre]
            tipos[hijo] = {**tipos[padre], **tipos[hijo]}
    return campos, tipos, listas


CAMPOS, TIPOS, LISTAS = _leer_modelos()


def _clase_de(anotacion):
    """De `m.Jornada` o `"Jornada"` saca Jornada, si es una tabla."""
    if anotacion is None:
        return None
    t = ast.unparse(anotacion).strip().strip('"\'')
    t = t.split("|")[0].strip().strip('"\'')
    if t.startswith("m."):
        t = t[2:]
    return t if t in CAMPOS else None


def _cadena(nodo):
    """`j.equipo.servicio` -> ("j", ["equipo", "servicio"])."""
    pasos = []
    while isinstance(nodo, ast.Attribute):
        pasos.append(nodo.attr)
        nodo = nodo.value
    return (nodo.id, list(reversed(pasos))) if isinstance(nodo, ast.Name) else None


def _seguir(sabidos, raiz, pasos):
    clase, lista = sabidos.get(raiz), False
    for paso in pasos:
        if clase is None:
            return None, False
        lista = paso in LISTAS.get(clase, set())
        clase = TIPOS.get(clase, {}).get(paso)
    return clase, lista


class _Revisor(ast.NodeVisitor):
    def __init__(self, archivo, perdonados=None, reportar=True):
        self.archivo = archivo
        self.sabidos = {}
        self.perdonados = set() if perdonados is None else perdonados
        self.reportar = reportar
        # `s.pais.nombre if s.pais else None` pasa por `s.pais` tres
        # veces, y es un solo error.
        self.dichos = set()

    # ---- lo que da y lo que quita certeza sobre una variable
    def visit_FunctionDef(self, nodo):
        guardado = self.sabidos
        self.sabidos = dict(guardado)
        for arg in list(nodo.args.args) + list(nodo.args.kwonlyargs):
            clase = _clase_de(arg.annotation)
            if clase:
                self.sabidos[arg.arg] = clase
            else:
                self.sabidos.pop(arg.arg, None)
        self.generic_visit(nodo)
        self.sabidos = guardado

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_AnnAssign(self, nodo):
        self.generic_visit(nodo)
        if isinstance(nodo.target, ast.Name):
            clase = _clase_de(nodo.annotation)
            if clase:
                self.sabidos[nodo.target.id] = clase
            else:
                self.sabidos.pop(nodo.target.id, None)

    def visit_Assign(self, nodo):
        self.generic_visit(nodo)
        clase = self._de_db_get(nodo.value) or self._de_cadena(nodo.value)
        for t in nodo.targets:
            if isinstance(t, ast.Name):
                if clase:
                    self.sabidos[t.id] = clase
                else:
                    self.sabidos.pop(t.id, None)

    @staticmethod
    def _de_db_get(valor):
        if (isinstance(valor, ast.Call) and isinstance(valor.func, ast.Attribute)
                and valor.func.attr == "get" and valor.args):
            return _clase_de(valor.args[0])
        return None

    def _de_cadena(self, valor):
        """`servicio = j.equipo.servicio` tambien dice de que es. Solo si
        no es lista: `gente = j.personal` son muchos, no uno."""
        if not isinstance(valor, ast.Attribute):
            return None
        origen = _cadena(valor)
        if not origen:
            return None
        clase, lista = _seguir(self.sabidos, *origen)
        return None if lista else clase

    def visit_For(self, nodo):
        self.visit(nodo.iter)
        # El tipo de la variable del for vale DENTRO del for y nada mas.
        # Sin esto, un `for a in j.personal` seguido de un
        # `for a in j.vehiculos` le pegaba el tipo del segundo al primero.
        guardado = dict(self.sabidos)
        clase, lista = None, False
        origen = _cadena(nodo.iter)
        if origen:
            clase, lista = _seguir(self.sabidos, *origen)
        if isinstance(nodo.target, ast.Name):
            if clase and lista:
                self.sabidos[nodo.target.id] = clase
            else:
                self.sabidos.pop(nodo.target.id, None)
        for hijo in nodo.body:
            self.visit(hijo)
        self.sabidos = guardado
        for hijo in nodo.orelse:
            self.visit(hijo)

    visit_AsyncFor = visit_For

    def visit_If(self, nodo):
        # Cada rama con su copia: hay codigo que hace db.get(Persona) en
        # una rama y db.get(Vehiculo) en la otra, y cada una le pide lo
        # suyo. Las dos tienen razon.
        self.visit(nodo.test)
        guardado = dict(self.sabidos)
        for hijo in nodo.body:
            self.visit(hijo)
        self.sabidos = dict(guardado)
        for hijo in nodo.orelse:
            self.visit(hijo)
        self.sabidos = guardado

    def visit_Call(self, nodo):
        # getattr(x, "y", algo) es alguien diciendo "se que puede no
        # estar". A eso no se le reclama.
        if (isinstance(nodo.func, ast.Name) and nodo.func.id == "getattr"
                and len(nodo.args) == 3 and isinstance(nodo.args[0], ast.Name)
                and isinstance(nodo.args[1], ast.Constant)):
            clase = self.sabidos.get(nodo.args[0].id)
            if clase:
                self.perdonados.add((clase, nodo.args[1].value))
        self.generic_visit(nodo)

    # ---- la revision
    def visit_Attribute(self, nodo):
        self.generic_visit(nodo)
        origen = _cadena(nodo)
        if not origen:
            return
        raiz, pasos = origen
        clase = self.sabidos.get(raiz)
        for paso in pasos:
            if clase is None or clase not in CAMPOS:
                return
            if paso in DE_LA_CASA or (clase, paso) in self.perdonados:
                return
            if paso not in CAMPOS[clase]:
                senal = (nodo.lineno, clase, paso)
                if self.reportar and senal not in self.dichos:
                    self.dichos.add(senal)
                    apuntar(self.archivo, nodo.lineno,
                            f"{clase} no tiene '{paso}'")
                return
            clase = TIPOS.get(clase, {}).get(paso)


def revisar_charset() -> None:
    """Todo documento que sale de aqui dice en que alfabeto esta escrito.

    Existe por un error del 20 de septiembre: el correo salia con
    `<!doctype html>` y de ahi directo al `<body>`, sin declarar el
    juego de caracteres. El buzon del cliente entonces adivina, casi
    siempre latin-1, y lo que llega dice "sAbado" y "terminA3" donde
    iba el acento. Lo cazo Salvador en su pantalla, no el codigo.

    Las paginas --task sheet, hoja del implantado, encuesta-- si lo
    declaraban. La diferencia no era tecnica, era que esas se abrieron
    en un navegador mil veces y los correos nunca se habian visto.

    Se revisa lo que el archivo ESCRIBE, no lo que el archivo es: una
    plantilla de Python que arma HTML tiene que traer el meta dentro de
    la cadena que devuelve.
    """
    for archivo in archivos("app", ".py"):
        texto = io.open(archivo, encoding="utf-8").read()
        if "<!doctype html>" not in texto.lower():
            continue
        if "charset" in texto.lower():
            continue
        linea = next((i for i, l in enumerate(texto.splitlines(), 1)
                      if "<!doctype html>" in l.lower()), 1)
        apuntar(archivo, linea,
                "arma un documento HTML y no declara el charset: "
                "los acentos llegan rotos")


def revisar_modelos() -> None:
    """Existe por dos errores de la misma familia, el mismo dia.

    `Equipo` guarda `plaza_id` pero no tiene relacion con `Plaza`, y
    `Servicio` guarda `pais_id` sin relacion con `Pais`. El codigo las
    navegaba como si existieran. Python no dice nada --un atributo que no
    esta solo se sabe al pedirlo-- asi que la unica senal fue una pantalla
    en blanco y cinco minutos y medio de pruebas.

    Esto lee `models.py`, aprende que campos tiene cada tabla, y sigue las
    cadenas: de `j.equipo.servicio.folio` sabe que `j` es Jornada, que
    `equipo` lleva a Equipo, que `servicio` lleva a Servicio, y ahi pregunta
    si Servicio tiene `folio`.

    Es a proposito timido. Solo opina cuando esta seguro del tipo de la
    variable: parametros anotados, `db.get(m.X, ...)`, cadenas de campos, y
    la variable de un `for` sobre una relacion de lista. De todo lo demas se
    calla. Un revisor que grita en falso se termina ignorando, y entonces no
    sirve el dia que tiene razon.
    """
    if not CAMPOS:
        return
    for archivo in archivos("app", ".py"):
        try:
            arbol = ast.parse(io.open(archivo, encoding="utf-8").read())
        except SyntaxError:
            continue          # eso ya lo reclama la revision de Python
        # Primera pasada para juntar los getattr perdonados, que pueden
        # aparecer despues del uso.
        explorador = _Revisor(archivo, reportar=False)
        explorador.visit(arbol)
        _Revisor(archivo, perdonados=explorador.perdonados).visit(arbol)


# ==================================================================
# 6 · Rutas: dos veces el mismo camino es una que nadie alcanza
# ==================================================================

def revisar_rutas() -> None:
    """Dos endpoints con el mismo metodo y el mismo camino.

    FastAPI se queda con la primera que encuentra y la segunda deja de
    existir, sin un error, sin un aviso y sin que se rompa nada al
    arrancar: la pantalla que la usaba empieza a recibir la respuesta de
    otra. Costo encontrarlo una vez --`/jornadas/{id}/bitacora` escrita
    dos veces en el mismo archivo-- y la unica senal fue que un campo
    que siempre estuvo ahi de pronto no venia.

    El nombre del parametro no cuenta: `{id}` y `{jornada_id}` son el
    mismo camino para quien enruta, asi que se comparan normalizados.
    """
    metodo_camino = re.compile(
        r"@(\w+)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']")
    llave_suelta = re.compile(r"\{[^}]*\}")

    for archivo in archivos("app/routers", ".py"):
        bruto = io.open(archivo, encoding="utf-8").read()
        vistos = {}
        for m in metodo_camino.finditer(bruto):
            router, metodo, camino = m.groups()
            llave = (router, metodo, llave_suelta.sub("{}", camino))
            linea = bruto[:m.start()].count("\n") + 1
            if llave in vistos:
                apuntar(archivo, linea,
                        f"{metodo.upper()} {camino} repite el camino de la "
                        f"linea {vistos[llave]}: FastAPI se queda con la "
                        f"primera y esta no se alcanza nunca")
            else:
                vistos[llave] = linea


# ==================================================================
# replaceChildren con un hijo que puede ser null
# ==================================================================

def revisar_null_pintado() -> None:
    """`h()` ignora un hijo nulo. `replaceChildren` y `append` no.

    De aqui salio el "nullnull" de la pantalla Yo y el "null" suelto del
    tabulador del acuerdo: un ternario que devuelve null como hijo
    directo de replaceChildren acaba en la pantalla, en letras, donde el
    usuario lo lee. La forma segura es `...[ ... ].filter(Boolean)`.
    """
    import re as _re

    def cierre(texto, i):
        nivel, j = 1, i
        while j < len(texto) and nivel:
            if texto[j] == "(":
                nivel += 1
            elif texto[j] == ")":
                nivel -= 1
            j += 1
        return j - 1

    for archivo in archivos("app/web", ".js"):
        if archivo.endswith("idioma.js"):
            continue
        bruto = open(archivo, encoding="utf-8").read()
        for m in _re.finditer(r"\.(?:replaceChildren|append)\(", bruto):
            i = m.end()
            trozo = bruto[i:cierre(bruto, i)]
            if trozo.lstrip().startswith("...[") and ".filter(Boolean)" in trozo:
                continue
            # Los null que viven dentro de un h(...) no llegan a la
            # pantalla: esos los filtra h. Solo estorban los de fuera.
            sin_h = _re.sub(r"h\([^()]*(\([^()]*\)[^()]*)*\)", "", trozo)
            if (_re.search(r"(\?|:)\s*null", sin_h)
                    or _re.search(r"(^|,)\s*null\s*(,|$)", sin_h)):
                apuntar(archivo, bruto[:i].count("\n") + 1,
                        "un hijo que puede ser null: replaceChildren y "
                        "append pintan la palabra 'null' en la pantalla. "
                        "Envuelvelo en ...[ ... ].filter(Boolean)")


# ==================================================================

def main() -> int:
    revisar_python()
    revisar_js()
    revisar_idioma()
    revisar_actividades()
    revisar_ayuda()
    revisar_padron_ayuda()
    revisar_texto_suelto()
    revisar_estilos()
    revisar_charset()
    revisar_migraciones()
    revisar_modelos()
    revisar_rutas()
    revisar_null_pintado()

    if not hallazgos:
        print("Todo limpio.")
        return 0

    print(f"{len(hallazgos)} cosas que mirar:\n")
    for h in hallazgos:
        print("  " + h)
    return 1


if __name__ == "__main__":
    sys.exit(main())

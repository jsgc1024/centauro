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
  5. La cadena de migraciones: sin huecos, sin dos cabezas.
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
        renglones = fuente.split("\n")
        for nombre, linea in _importados(arbol).items():
            # `# noqa` en el renglon significa "esta aqui a proposito":
            # el import de models en main.py registra las tablas y
            # quitarlo rompe el arranque sin que nadie lo note hasta
            # la primera consulta.
            if "# noqa" in renglones[linea - 1]:
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
        for clave in re.findall(r'\bt\(\s*["\']([\w]+)["\']',
                                io.open(archivo, encoding="utf-8").read()):
            usadas.add((clave, archivo))

    for clave, archivo in sorted(usadas):
        if clave not in definidas:
            apuntar(archivo, 0, f"usa el texto '{clave}' y no esta traducido")


# ==================================================================
# 5 · Migraciones: una sola cadena, una sola cabeza
# ==================================================================

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

def main() -> int:
    revisar_python()
    revisar_js()
    revisar_idioma()
    revisar_migraciones()

    if not hallazgos:
        print("Todo limpio.")
        return 0

    print(f"{len(hallazgos)} cosas que mirar:\n")
    for h in hallazgos:
        print("  " + h)
    return 1


if __name__ == "__main__":
    sys.exit(main())

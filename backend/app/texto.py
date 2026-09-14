"""Regla de captura del sistema: lo escrito se guarda parejo.

Cada palabra queda con su inicial en mayuscula y el resto en minuscula,
venga como venga escrita: "JUAN CARLOS", "juan carlos" y "Juan carlos"
entran distinto y salen igual. Se hace al guardar y no al imprimir,
porque el mismo dato viaja al task sheet, al correo del cliente y a la
app del agente; si se corrige en un solo lugar, en los otros se ve mal.

Las palabras de enlace se quedan abajo: un apellido se lee "Maria de la
Cruz", no "Maria De La Cruz".

El numero de vuelo es la excepcion y va todo en mayuscula, porque asi lo
imprime la aerolinea y asi se busca en la pantalla del aeropuerto.
"""

MENUDAS = {"de", "del", "la", "las", "los", "y", "e", "el", "al",
           "da", "do", "dos", "van", "von", "di", "der",
           # Los lugares de la agenda tambien las llevan:
           # "Comida en San Angel", "Bank of America".
           "en", "a", "con", "por", "para", "of", "the"}


def titulo(valor):
    """Inicial mayuscula por palabra. Lo que no es texto pasa de largo."""
    if not isinstance(valor, str):
        return valor
    limpio = " ".join(valor.split())
    if not limpio:
        return limpio
    return " ".join(
        _palabra(p, primera=(i == 0))
        for i, p in enumerate(limpio.split(" "))
    )


def _palabra(palabra: str, primera: bool) -> str:
    bajo = palabra.lower()
    if not primera and bajo in MENUDAS:
        return bajo
    # Los compuestos con guion llevan las dos iniciales: Jean-Luc, Perez-Gomez.
    return "-".join(_inicial(t) for t in bajo.split("-"))


def _inicial(trozo: str) -> str:
    return trozo[:1].upper() + trozo[1:] if trozo else trozo


def mayusculas(valor):
    """Para el numero de vuelo: UA 1518, AM 57."""
    if not isinstance(valor, str):
        return valor
    return " ".join(valor.split()).upper()

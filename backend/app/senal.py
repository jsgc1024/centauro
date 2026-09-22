"""La senal de color: la paleta, y lo que se sabe de cada color.

Pedido de Salvador, 22 sep. La senal con la que el principal reconoce al
equipo puede ser un color: una pantalla de un solo color se distingue a
veinte metros sin leer nada, y no hay imagen que bajar ni guardar.

Esta es la UNICA copia de la paleta. La consola la recibe en la vista
previa del task sheet, la app en la ficha del dia, y la hoja del
principal la nombra en su idioma (`textos.py`, `color_<clave>`). El
color de la letra encima va decidido aqui, por color, y no calculado
en cada pantalla: asi se lee igual en el telefono, en la hoja y en la
consola.

Los ocho salieron de la propuesta; en el sistema no habia una paleta
secundaria de la marca. El dia que llegue el manual, se cambian los hex
aqui y nada mas.
"""

COLORES = {
    "naranja":  {"hex": "#F26B1D", "letra": "#ffffff"},
    "amarillo": {"hex": "#F2C200", "letra": "#000000"},
    "verde":    {"hex": "#22A05B", "letra": "#ffffff"},
    "turquesa": {"hex": "#12A5B4", "letra": "#000000"},
    "azul":     {"hex": "#2F7FE0", "letra": "#ffffff"},
    "morado":   {"hex": "#7B3FB8", "letra": "#ffffff"},
    "magenta":  {"hex": "#D4267E", "letra": "#ffffff"},
    "rojo":     {"hex": "#D93025", "letra": "#ffffff"},
}


def color(clave: str | None) -> dict | None:
    """Lo que se sabe de un color, por su clave. Nulo si no hay o si la
    clave ya no esta en la paleta: un dato viejo no truena, se calla."""
    if not clave or clave not in COLORES:
        return None
    return {"clave": clave, **COLORES[clave]}


def paleta() -> list[dict]:
    """Toda la paleta, en el orden en que se ofrece."""
    return [{"clave": clave, **datos} for clave, datos in COLORES.items()]

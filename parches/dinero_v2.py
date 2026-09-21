"""Paso 5b: cada endpoint del dinero pregunta por su actividad.

Se reescribe solo dentro de la firma de cada funcion, ubicada por el
arbol sintactico y no buscando texto suelto: un `Depends(CONSULTOR)` en
el cuerpo de otra funcion no se toca por accidente.
"""
import ast
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent / "backend/app/routers"


def cambiar_puertas(archivo: str, por_funcion: dict[str, str]) -> int:
    """Cambia el alias de la puerta de esas funciones."""
    ruta = RAIZ / archivo
    lineas = ruta.read_text().split("\n")
    arbol = ast.parse("\n".join(lineas))
    cambios = 0
    for n in ast.walk(arbol):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        nuevo = por_funcion.get(n.name)
        if not nuevo:
            continue
        # De la linea del `def` al primer renglon del cuerpo: ahi vive la
        # firma y nada mas.
        ini, fin = n.lineno - 1, n.body[0].lineno - 1
        for i in range(ini, fin):
            if "Depends(" in lineas[i]:
                import re
                lineas[i] = re.sub(r"Depends\([A-Z_]+\)", f"Depends({nuevo})",
                                   lineas[i])
                cambios += 1
                break
        else:
            raise AssertionError(f"{archivo}:{n.name} no tiene Depends en su firma")
    ruta.write_text("\n".join(lineas))
    return cambios


# --- viaticos: el que asigna dinero y el que revisa lo gastado -------
n = cambiar_puertas("viaticos.py", {
    f: "CIERRA" for f in ("rechazar_comprobante", "cerrar_con_descuento",
                          "cerrar", "validar_comprobante", "devolver")})
print(f"viaticos.py: {n} puertas al alias de cierre")

# --- nomina: calcular no es pagar, y el tabulador es otra cosa -------
n = cambiar_puertas("nomina.py", {"guardar_tabulador": "TABULADOR",
                                  "pagar": "PAGAR"})
print(f"nomina.py: {n} puertas separadas")

# --- cierre: cotizar no es cerrar -----------------------------------
n = cambiar_puertas("cierre.py", {"cotizar": "COTIZA", "autorizar": "COTIZA"})
print(f"cierre.py: {n} puertas a cotizacion")

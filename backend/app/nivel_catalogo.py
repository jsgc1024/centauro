"""Lo fijo del Nivel Centauro (seccion 135): los municipios con su
poblacion, los componentes, los pesos y los cortes de arranque, y que
delitos del Secretariado entran en cada componente.

Una sola copia, que leen la migracion (para el servidor) y la semilla
(para las pruebas).
"""
import csv
import pathlib

ARCHIVO_POBLACION = (pathlib.Path(__file__).parent / "datos"
                     / "conapo_poblacion_municipios.csv")
# Los anos que trae el archivo del CONAPO (proyeccion a mitad de ano).
ANIOS_POBLACION = (2025, 2026, 2027)

# El orden es el de la formula y el de las pantallas.
COMPONENTES = ("violencia_letal", "delitos_violencia",
               "delincuencia_organizada", "miedo", "no_denuncia",
               "cifra_negra")
OFICIALES = COMPONENTES[:3]

# Decision de Salvador, 2 oct 2026: la cifra negra de redes pesa 40% y
# los oficiales se reparten el 60% como en la propuesta.
PESOS_INICIALES = {"violencia_letal": 18, "delitos_violencia": 12,
                   "delincuencia_organizada": 10, "miedo": 12,
                   "no_denuncia": 8, "cifra_negra": 40}

# Los cinco rangos del tablero de Power BI de la Central (Bajo, Medio
# bajo, Medio, Medio alto, Alto). Dos cortes estan por confirmar con la
# Central: 42 y 80 son los que se ven en su tablero.
CORTES_INICIALES = [20, 42, 60, 80]
RANGOS = ("bajo", "medio_bajo", "medio", "medio_alto", "alto")

# Cuanto pesa un hecho de cifra negra segun su nivel.
PESO_DEL_HECHO = {1: 1, 2: 2, 3: 4, 4: 8}
DIAS_DE_CIFRA_NEGRA = 90


def componente_del_delito(tipo: str, subtipo: str, modalidad: str) -> str | None:
    """En que componente cae un renglon del Secretariado (metodologia
    2026). Las tentativas no cuentan: no hubo victima de ese delito."""
    if (tipo == "Homicidio" and subtipo == "Homicidio doloso") or \
            (tipo == "Feminicidio" and subtipo == "Feminicidio"):
        return "violencia_letal"
    if (tipo == "Robo" and modalidad == "Con violencia") or \
            (tipo == "Lesiones" and subtipo == "Lesiones dolosas"
             and modalidad == "Con arma de fuego"):
        return "delitos_violencia"
    if tipo == "Secuestro" or tipo == "Narcomenudeo" or \
            (tipo == "Extorsión" and subtipo in ("Extorsión presencial",
                                                 "Extorsión por otros medios")):
        return "delincuencia_organizada"
    return None


def municipios() -> list[dict]:
    """[{clave, entidad, nombre, poblacion: {2025: n, ...}}] del archivo
    del CONAPO que vive en el repositorio."""
    salida = []
    with open(ARCHIVO_POBLACION, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            clave = int(fila["clave"])
            salida.append({
                "clave": clave, "entidad": f"{clave // 1000:02d}",
                "nombre": fila["municipio"],
                "poblacion": {a: int(fila[f"pob_{a}"]) for a in ANIOS_POBLACION},
            })
    return salida

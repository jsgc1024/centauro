"""El punto de inicio: su radio y el candado del aeropuerto."""
from fastapi import HTTPException

# ------------------------------------------------------------- geocerca

# Un aeropuerto no cabe en medio kilometro: el conductor puede estar donde
# debe —terminal equivocada, estacionamiento, acceso de carga— y quedar
# fuera del circulo, y la app le negaria la llegada. En una direccion
# particular pasa lo contrario: con un kilometro se daba por llegado desde
# varias cuadras antes, asi que 500 m es lo que de verdad dice "estoy ahi".
GEOCERCA_AEROPUERTO = 2000
GEOCERCA_NORMAL = 500


def radio_de(aeropuerto: bool | None) -> int:
    return GEOCERCA_AEROPUERTO if aeropuerto else GEOCERCA_NORMAL


# ------------------------------------------------------------- candado

def revisar_aeropuerto(marcado: bool | None, segun_google: bool | None,
                       forzar: bool = False) -> None:
    """No se marca como aeropuerto una direccion que no lo es.

    La casilla no es una etiqueta: abre la geocerca de 500 m a 2 km. En un
    hotel eso significa que el conductor puede marcar su llegada desde
    cuatro cuadras antes, y la marca deja de probar nada. Ademas el dia
    empieza a pedir vuelo y meet and greet, que ahi no existen.

    El candado se abre a proposito y no por descuido: hay terminales
    privadas y aeropuertos chicos que Google no clasifica como tales, y
    esos si son aeropuertos. Por eso se puede forzar, y queda escrito.

    Sin dato de Google —una direccion escrita a mano— no hay nada que
    contradecir y no se traba.
    """
    if marcado and segun_google is False and not forzar:
        raise HTTPException(409, {
            "mensaje": "Google dice que ese lugar no es un aeropuerto",
            "que_hacer": "Si de verdad lo es —una terminal privada, una "
                         "pista chica— confirmalo y queda registrado. Si "
                         "no, quita la casilla: marcarla abre la geocerca "
                         "de 500 m a 2 km y el conductor podria marcar su "
                         "llegada desde lejos.",
            "campo": "origen_aeropuerto",
        })

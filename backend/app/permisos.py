"""Actividades del sistema y que rol puede hacer cada una.

La pregunta que se le hace al sistema no es "que rol tiene esta persona"
sino "puede hacer esta actividad". Hoy la respuesta sale de su rol, como
siempre; manana saldra de un panel donde se le dan actividades a cada
colaborador segun lo que realmente hace. Cuando llegue ese panel, lo
unico que cambia es esta tabla: los endpoints ya preguntan por actividad.

Se va llenando pantalla por pantalla. Lo que todavia no esta aqui sigue
funcionando con auth.requiere(...) y sus roles, sin cambio alguno.
"""
from app import models as m

R = m.Rol

# actividad -> roles que la traen de fabrica.
# La descripcion es la que vera el panel de permisos: se escribe pensando
# en quien la va a leer, no en el endpoint.
ACTIVIDADES: dict[str, dict] = {
    "servicios.alta": {
        "descripcion": "Dar de alta un servicio y dejarlo programado",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "mapas.buscar": {
        "descripcion": "Buscar un punto de encuentro en Google Maps",
        "roles": {R.CONSULTOR, R.CENTRAL, R.DIRECTOR_OPERACIONES},
    },
    "ciudades.alta": {
        "descripcion": "Agregar una ciudad donde se dan servicios",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "solicitantes.ver": {
        "descripcion": "Ver quien puede solicitar servicios de un cliente",
        "roles": {R.CONSULTOR, R.CENTRAL, R.DIRECTOR_OPERACIONES},
    },
    "solicitantes.alta": {
        "descripcion": "Dar de alta a quien solicita servicios",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "solicitantes.editar": {
        "descripcion": "Corregir o dar de baja a quien solicita servicios",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "servicios.ver": {
        "descripcion": "Ver los servicios y su avance",
        "roles": {R.CONSULTOR, R.CENTRAL, R.DIRECTOR_OPERACIONES},
    },
}


def roles_de(actividad: str) -> set:
    """Los roles que traen esa actividad. Una actividad desconocida no la
    puede nadie: mas vale un 403 visible que una puerta abierta."""
    entrada = ACTIVIDADES.get(actividad)
    return set(entrada["roles"]) if entrada else set()


def catalogo() -> list[dict]:
    """Para el panel de permisos y para la documentacion de la API."""
    return [{"actividad": nombre,
             "descripcion": datos["descripcion"],
             "roles": sorted(r.value for r in datos["roles"])}
            for nombre, datos in sorted(ACTIVIDADES.items())]

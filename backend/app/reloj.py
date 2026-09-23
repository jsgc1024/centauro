"""Qué hora es allá.

Centauro opera en varios países y todo el sistema decidía con un solo
reloj: el del servidor. Las columnas de fecha son *naive* y guardan la
hora de pared del país del servicio —un servicio de São Paulo que
arranca a las 07:00 guarda 07:00—, así que compararlas contra
`datetime.now()` del servidor da un resultado corrido por la diferencia
horaria.

Lo que eso provocaba, con el contenedor en México:

  - Un conductor en Brasil que marcaba puntual caía fuera de la ventana
    permitida por tres horas, se le levantaba alerta y su marca quedaba
    en revisión.
  - Todo servicio brasileño en curso aparecía "sin reporte" en la banda
    roja de la central, siempre.
  - El aviso preventivo de horas extra —una ventana de treinta
    minutos— nunca coincidía fuera de México: no existía.
  - El plazo de 24 horas del consultor para cerrar, que define si cobra
    su comisión, corría torcido desde que nacía.

Aquí vive la respuesta a una sola pregunta, y el resto del sistema la
usa en vez de preguntarle la hora al servidor:

    ahora_en(pais)      el instante, en hora de pared de ese país
    hoy_en(pais)        qué día es allá

Dos advertencias que vale tener presentes:

  - Esto NO convierte lo que ya está guardado. Las columnas siguen
    siendo hora de pared del país; lo que cambia es contra qué se
    comparan.
  - Una columna con `timezone=True` guarda un instante absoluto y no
    tiene nada que ver con esto: esas se comparan con `datetime.now(
    timezone.utc)` y ya estaban bien.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app import models as m

# Donde está la operación cuando nadie dice otra cosa. No es una
# elección técnica: es donde está la empresa.
ZONA_POR_OMISION = "America/Mexico_City"

# Las zonas se buscan por nombre en la base de datos del sistema y eso
# cuesta; son tres y no cambian, así que se guardan.
_zonas: dict[str, ZoneInfo] = {}


def zona(nombre: str | None) -> ZoneInfo:
    """La zona por su nombre IANA, o la de la casa si no se reconoce.

    Un nombre inválido no puede tumbar una pantalla de monitoreo: se cae
    a la zona de la casa, que deja el sistema exactamente como estaba
    antes de que existiera este módulo.
    """
    clave = (nombre or "").strip() or ZONA_POR_OMISION
    if clave not in _zonas:
        try:
            _zonas[clave] = ZoneInfo(clave)
        except (ZoneInfoNotFoundError, ValueError):
            _zonas[clave] = ZoneInfo(ZONA_POR_OMISION)
    return _zonas[clave]


def ahora_en(pais: m.Pais | None, ahora: datetime | None = None) -> datetime:
    """El instante, escrito como lo escribiría un reloj de pared de allá.

    Devuelve un datetime *naive* a propósito: es lo que hay que comparar
    contra las columnas del sistema, que también son naive y también
    guardan hora de pared.

    `ahora` sirve para las pruebas y para los endpoints que lo reciben
    por parámetro. Si viene sin zona se toma como un instante ya dado
    —la prueba sabe lo que está haciendo— y se devuelve tal cual.
    """
    if ahora is not None:
        if ahora.tzinfo is None:
            return ahora
        return ahora.astimezone(zona(getattr(pais, "zona_horaria", None))) \
            .replace(tzinfo=None)
    return (datetime.now(zona(getattr(pais, "zona_horaria", None)))
            .replace(tzinfo=None))


def hoy_en(pais: m.Pais | None, hoy: date | None = None) -> date:
    """Qué día es allá.

    Importa más de lo que parece. La pantalla del agente de campo abre
    en "hoy", y cerca de la medianoche el día del servidor y el del
    agente son distintos: se le enseñaría el día equivocado justo
    cuando más lo necesita.
    """
    if hoy is not None:
        return hoy
    return ahora_en(pais).date()


# --------------------------------------------------------------------
# Cómo se llega al país desde donde estés
#
# Casi siempre hay una jornada o un servicio a la mano. Estas funciones
# hacen el camino y guardan los países que van encontrando, porque un
# tablero recorre cientos de jornadas y no puede ir a la base por cada
# una.
# --------------------------------------------------------------------

class Relojes:
    """Los relojes de los países, traídos una vez.

    Un tablero de monitoreo mezcla servicios de los tres países en la
    misma pantalla y cada uno se juzga con su propia hora. Pedir el país
    jornada por jornada serían cientos de consultas para tres respuestas.
    """

    def __init__(self, db: Session, ahora: datetime | None = None):
        self._db = db
        self._fijo = ahora
        self._paises: dict[int, m.Pais] = {}

    def pais(self, pais_id: int | None) -> m.Pais | None:
        if pais_id is None:
            return None
        if pais_id not in self._paises:
            self._paises[pais_id] = self._db.get(m.Pais, pais_id)
        return self._paises[pais_id]

    def ahora(self, pais_id: int | None) -> datetime:
        return ahora_en(self.pais(pais_id), self._fijo)

    def hoy(self, pais_id: int | None) -> date:
        return self.ahora(pais_id).date()

    def de_la_jornada(self, jornada: m.Jornada) -> datetime:
        return self.ahora(pais_de_la_jornada(jornada))

    def del_servicio(self, servicio: m.Servicio | None) -> datetime:
        return self.ahora(servicio.pais_id if servicio else None)


def pais_de_la_jornada(jornada: m.Jornada | None) -> int | None:
    """jornada → equipo → servicio → país. Con cuidado en cada paso."""
    if not jornada:
        return None
    equipo = jornada.equipo
    servicio = equipo.servicio if equipo else None
    return servicio.pais_id if servicio else None


def pais_de_la_persona(persona: m.Persona | None) -> int | None:
    """Para lo que es del usuario y no del servicio.

    La pantalla del agente de campo abre en *su* hoy, no en el de cada
    servicio que trae; y el corte de la víspera de la central es el
    turno de quien está mirando la pantalla.
    """
    if not persona:
        return None
    return persona.plaza.pais_id if persona.plaza else None


def ahora_de_la_jornada(db: Session, jornada: m.Jornada,
                        ahora: datetime | None = None) -> datetime:
    """Atajo para un solo caso suelto. Para varios, usa `Relojes`."""
    return ahora_en(db.get(m.Pais, pais_de_la_jornada(jornada))
                    if pais_de_la_jornada(jornada) else None, ahora)


def ahora_del_servicio(db: Session, servicio: m.Servicio | None,
                       ahora: datetime | None = None) -> datetime:
    return ahora_en(db.get(m.Pais, servicio.pais_id) if servicio else None,
                    ahora)


def ahora_de_la_persona(db: Session, persona: m.Persona | None,
                        ahora: datetime | None = None) -> datetime:
    pais_id = pais_de_la_persona(persona)
    return ahora_en(db.get(m.Pais, pais_id) if pais_id else None, ahora)


def de_prueba(ahora: datetime | None) -> datetime | None:
    """El `ahora` que llega por parametro, solo fuera de produccion.

    Existe para que las pruebas muevan el reloj. En produccion se
    ignora: el visto bueno "en plazo" decide una comision, y no puede
    decidirlo quien escribe una hora en la direccion.
    """
    from app.config import es_desarrollo, settings
    return ahora if es_desarrollo(settings) else None


def margen_de_paises(db: Session) -> timedelta:
    """La mayor diferencia horaria entre los países activos.

    La usan las consultas que filtran por hora en SQL sobre servicios de
    varios países a la vez: no se puede escribir un solo `WHERE` con
    tres relojes, así que se ensancha la ventana por este margen y
    después se filtra en Python, país por país. Traer de más y descartar
    es correcto; traer de menos es perder un servicio.
    """
    referencia = datetime.now()
    desfases = [
        referencia.astimezone(zona(p.zona_horaria)).utcoffset()
        for p in db.query(m.Pais).filter(m.Pais.activo.is_(True)).all()
    ]
    desfases = [d for d in desfases if d is not None]
    if len(desfases) < 2:
        return timedelta(0)
    return max(desfases) - min(desfases)

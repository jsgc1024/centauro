"""Chico 2: la hora que el sistema propuso para el regreso, al lado.

El movimiento ya guardaba `hora_propuesta`: la del relevo que lo abrio.
Si el dia del regreso se parte, esa hora tambien decide cuanto cobra
cada quien --y tambien se puede corregir-- pero no quedaba la propuesta
contra la cual compararla. Sin eso no se puede saber si alguien la movio.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- modelo ----------------------------------------------------------
R = RAIZ / "backend/app/models.py"
s = R.read_text()
VIEJO = """    regreso_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    regreso_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
"""
NUEVO = """    regreso_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    regreso_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    # La hora que el sistema propuso para partir el dia del regreso: la
    # ultima marca del que cubria. Es la gemela de `hora_propuesta`, que
    # es la del relevo que abrio el movimiento. Si no coincide con la que
    # quedo en la asignacion, alguien la corrigio, y ese alguien es
    # `regreso_por_id`. Va vacia cuando el regreso no partio ningun dia.
    hora_propuesta_regreso: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
"""
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("models.py: hora_propuesta_regreso")

# --- motor -----------------------------------------------------------
R = RAIZ / "backend/app/contingencia.py"
s = R.read_text()
VIEJO = """    partidas = hecho["jornadas_partidas"]
    nuevo = db.get(m.ReemplazoRecurso, hecho["reemplazo_id"])
    if nuevo:
        db.delete(nuevo)
"""
NUEVO = """    partidas = hecho["jornadas_partidas"]
    nuevo = db.get(m.ReemplazoRecurso, hecho["reemplazo_id"])
    # La propuesta se rescata antes de borrar el movimiento temporal: es
    # el unico lugar donde quedo escrita, y sin ella no se puede saber
    # despues si el consultor corrigio la hora del regreso.
    propuesta = nuevo.hora_propuesta if nuevo else None
    if nuevo:
        db.delete(nuevo)
"""
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = """    r.regreso_en = reloj.ahora_de_la_jornada(db, vuelve)
    r.regreso_por_id = hecho_por_id"""
NUEVO = """    r.regreso_en = reloj.ahora_de_la_jornada(db, vuelve)
    r.regreso_por_id = hecho_por_id
    # Se vuelve a escribir cada vez: si el regreso se corrio y ya no
    # parte ningun dia, tampoco hay propuesta que guardar.
    r.hora_propuesta_regreso = propuesta"""
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("contingencia.py: la propuesta del regreso se guarda")

# --- historial -------------------------------------------------------
R = RAIZ / "backend/app/routers/contingencia.py"
s = R.read_text()
VIEJO = """            "regreso_por": _nombre(db, r.regreso_por_id),"""
NUEVO = """            "regreso_por": _nombre(db, r.regreso_por_id),
            # Lo que el sistema habria puesto solo, de los dos lados del
            # movimiento. Si no coincide con la hora que quedo en la
            # asignacion, alguien la corrigio.
            "hora_propuesta": (r.hora_propuesta.isoformat()
                               if r.hora_propuesta else None),
            "hora_propuesta_regreso": (r.hora_propuesta_regreso.isoformat()
                                       if r.hora_propuesta_regreso else None),"""
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("routers/contingencia.py: el historial trae las dos propuestas")

# --- migracion -------------------------------------------------------
(RAIZ / "backend/migrations/versions/b7f21c4e9a03_hora_propuesta_del_regreso.py"
 ).write_text('''"""La hora que el sistema propuso para el regreso

El movimiento ya guardaba `hora_propuesta`: la del relevo que lo abrio.
Si el dia del regreso se parte --el que cubria alcanzo a trabajar esa
manana-- hay una segunda hora que decide cuanto cobra cada quien, y el
consultor tambien la puede corregir.

Guardar la propuesta al lado es lo que deja ver que la corrigieron: si
no coincide con la que quedo en la asignacion, alguien la movio, y ese
alguien es el `regreso_por_id` del mismo movimiento.

Va vacia cuando el regreso no partio ningun dia.

Revision ID: b7f21c4e9a03
Revises: a4c9e1b70d28
"""
import sqlalchemy as sa
from alembic import op

revision = "b7f21c4e9a03"
down_revision = "a4c9e1b70d28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reemplazo_recurso",
                  sa.Column("hora_propuesta_regreso", sa.DateTime(),
                            nullable=True))


def downgrade() -> None:
    op.drop_column("reemplazo_recurso", "hora_propuesta_regreso")
''')
print("migracion b7f21c4e9a03")

"""Los indices con el nombre que dice el modelo (seccion 100)

Once indices se crearon en migraciones con un nombre y el modelo los
declara con otro (`index=True` los nombra ix_<tabla>_<columna>). No
mordia a nadie, pero el siguiente `alembic revision --autogenerate` los
propondria "arreglar" borrando y creando, y la bateria --que arma la
base desde el modelo-- corria con indices distintos a los de
produccion. Se renombran: es instantaneo y no toca datos.

Y el token de la encuesta: la base traia una restriccion UNIQUE mas un
indice normal, y el modelo un indice unico. Queda como el modelo.

Revision ID: a3b5c7d9e1f2
Revises: f2c4a6e8b0d1
Create Date: 2026-09-29
"""
from alembic import op

revision = "a3b5c7d9e1f2"
down_revision = "f2c4a6e8b0d1"
branch_labels = None
depends_on = None

RENOMBRES = [
    ("ix_ajuste_nomina_aplicado", "ix_ajuste_nomina_aplicado_en_nomina_id"),
    ("ix_capacitacion_persona", "ix_capacitacion_persona_id"),
    ("ix_deposito_equipo", "ix_deposito_bancario_equipo_id"),
    ("ix_deposito_persona", "ix_deposito_bancario_persona_id"),
    ("ix_foto_revision_revision", "ix_foto_revision_revision_id"),
    ("ix_persona_implantado_contrato", "ix_persona_implantado_contrato_id"),
    ("ix_revision_unidad_servicio", "ix_revision_unidad_servicio_id"),
    ("ix_revision_unidad_vehiculo", "ix_revision_unidad_vehiculo_id"),
    ("ix_taller_vehiculo_unidad", "ix_taller_vehiculo_vehiculo_id"),
    ("ix_unidad_implantado_contrato", "ix_unidad_implantado_contrato_id"),
]


def upgrade() -> None:
    for viejo, nuevo in RENOMBRES:
        op.execute(f"ALTER INDEX IF EXISTS {viejo} RENAME TO {nuevo}")
    op.execute("ALTER TABLE encuesta DROP CONSTRAINT IF EXISTS encuesta_token_key")
    op.execute("DROP INDEX IF EXISTS ix_encuesta_token")
    op.create_index("ix_encuesta_token", "encuesta", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_encuesta_token", table_name="encuesta")
    op.create_index("ix_encuesta_token", "encuesta", ["token"], unique=False)
    op.create_unique_constraint("encuesta_token_key", "encuesta", ["token"])
    for viejo, nuevo in RENOMBRES:
        op.execute(f"ALTER INDEX IF EXISTS {nuevo} RENAME TO {viejo}")

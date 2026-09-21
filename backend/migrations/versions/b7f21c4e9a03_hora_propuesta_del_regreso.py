"""La hora que el sistema propuso para el regreso

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

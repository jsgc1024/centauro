"""El nombre de la plantilla del correo cabe en cuarenta

Veinte era una trampa: "encuesta_recordatorio" mide veintiuno y
reventaba al guardar, no al escribirlo.

Revision ID: f3a17c08b542
Revises: e2b47d90c153
"""
import sqlalchemy as sa
from alembic import op

revision = "f3a17c08b542"
down_revision = "e2b47d90c153"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("notificacion", "plantilla",
                    type_=sa.String(40), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("notificacion", "plantilla",
                    type_=sa.String(20), existing_nullable=True)

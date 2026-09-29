"""notificacion.reintentar_en: la espera creciente del correo (seccion 100)

Revision ID: f2c4a6e8b0d1
Revises: e7b3d9a1c5f4
Create Date: 2026-09-29
"""
import sqlalchemy as sa
from alembic import op

revision = "f2c4a6e8b0d1"
down_revision = "e7b3d9a1c5f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notificacion",
                  sa.Column("reintentar_en", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("notificacion", "reintentar_en")

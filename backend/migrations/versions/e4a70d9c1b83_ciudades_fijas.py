"""Ciudades fijas y ciudades que se apagan solas

Revision ID: e4a70d9c1b83
Revises: d1c8b3e07f52
Create Date: 2026-09-13

Cuatro ciudades son la operacion de todos los dias y siempre estan en la
lista. Las demas salen a los 30 dias sin usarse, sin borrarse.
"""
import sqlalchemy as sa
from alembic import op

revision = "e4a70d9c1b83"
down_revision = "d1c8b3e07f52"
branch_labels = None
depends_on = None

FIJAS = ("Ciudad de Mexico", "Guadalajara", "Monterrey", "Queretaro")


def upgrade():
    op.add_column("plaza", sa.Column("fija", sa.Boolean(), nullable=False,
                                     server_default="false"))
    op.add_column("plaza", sa.Column(
        "creada_en", sa.DateTime(timezone=True),
        server_default=sa.func.now(), nullable=False))
    nombres = ", ".join(f"'{n}'" for n in FIJAS)
    op.execute(f"UPDATE plaza SET fija = true WHERE nombre IN ({nombres})")


def downgrade():
    op.drop_column("plaza", "creada_en")
    op.drop_column("plaza", "fija")

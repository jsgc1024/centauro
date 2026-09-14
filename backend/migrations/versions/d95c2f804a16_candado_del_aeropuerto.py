"""Guardar lo que Google dice del punto, aparte de lo que dice el consultor

Revision ID: d95c2f804a16
Revises: c74a91be05d3
Create Date: 2026-09-13

Marcar como aeropuerto un lugar que no lo es abre la geocerca de 500 m a
2 km, y en un hotel eso deja al conductor marcando su llegada desde
cuatro cuadras antes. Para poder trabar ese caso hay que poder comparar
las dos cosas, y hasta ahora solo se guardaba la decision del consultor.

Vacio quiere decir que la direccion se escribio a mano: ahi no hay
veredicto de Google que contradecir y no se traba nada.
"""
import sqlalchemy as sa
from alembic import op

revision = "d95c2f804a16"
down_revision = "c74a91be05d3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jornada", sa.Column("origen_google_aeropuerto",
                                       sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("jornada", "origen_google_aeropuerto")

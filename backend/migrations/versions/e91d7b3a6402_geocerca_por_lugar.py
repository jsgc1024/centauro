"""El radio de la geocerca segun el tipo de lugar

Revision ID: e91d7b3a6402
Revises: d0f39a5cb728
Create Date: 2026-09-13

Dos kilometros en aeropuerto, uno en cualquier otro lado. Un aeropuerto
no cabe en un kilometro y la app le negaria la llegada a alguien que
esta donde debe.
"""
import sqlalchemy as sa
from alembic import op

revision = "e91d7b3a6402"
down_revision = "d0f39a5cb728"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jornada", sa.Column(
        "origen_aeropuerto", sa.Boolean(), nullable=False,
        server_default="false"))
    # Lo que ya existe: si el dia trae vuelo, su punto es un aeropuerto.
    op.execute("""
        UPDATE jornada SET origen_aeropuerto = true
        WHERE vuelo_numero IS NOT NULL OR vuelo_aerolinea IS NOT NULL
    """)
    # Y a esos se les ensancha el circulo, salvo que alguien lo haya
    # movido a mano a algo distinto del kilometro de siempre.
    op.execute("""
        UPDATE jornada SET geocerca_metros = 2000
        WHERE origen_aeropuerto = true AND geocerca_metros = 1000
    """)


def downgrade():
    op.drop_column("jornada", "origen_aeropuerto")

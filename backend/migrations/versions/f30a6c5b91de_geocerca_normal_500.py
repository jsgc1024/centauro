"""Bajar la geocerca de direcciones particulares a 500 m

Revision ID: f30a6c5b91de
Revises: e91d7b3a6402
Create Date: 2026-09-13

Con un kilometro el conductor quedaba "dentro" desde varias cuadras
antes, asi que la llegada no probaba nada. Medio kilometro si dice que
esta en la direccion. El aeropuerto se queda en dos kilometros.
"""
from alembic import op

revision = "f30a6c5b91de"
down_revision = "e91d7b3a6402"
branch_labels = None
depends_on = None


def upgrade():
    # Solo los que traen el kilometro de siempre: si alguien puso otro
    # radio a mano fue por una razon del lugar y no se le toca.
    op.execute("""
        UPDATE jornada SET geocerca_metros = 500
        WHERE origen_aeropuerto = false AND geocerca_metros = 1000
    """)


def downgrade():
    op.execute("""
        UPDATE jornada SET geocerca_metros = 1000
        WHERE origen_aeropuerto = false AND geocerca_metros = 500
    """)

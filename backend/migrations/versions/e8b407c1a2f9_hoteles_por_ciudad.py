"""El catalogo de hoteles crece con la operacion y se limpia solo

Revision ID: e8b407c1a2f9
Revises: d95c2f804a16
Create Date: 2026-09-13

Un hotel entra la primera vez que alguien lo captura y queda disponible
para la ciudad donde se uso. El que lleva tres meses sin ocuparse sale de
la lista —no de la base, que sus servicios siguen apuntando ahi— para que
el consultor no busque entre cien hoteles los cuatro que de verdad usa.

Los que ya existian se quedan sin fecha de alta a proposito: cuentan como
viejos y se ganan su lugar en la lista usandose, no por antigüedad. Es la
limpieza que hacia falta: el catalogo arranca en blanco y se llena con lo
que de verdad se ocupa.
"""
import sqlalchemy as sa
from alembic import op

revision = "e8b407c1a2f9"
down_revision = "d95c2f804a16"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hotel", sa.Column(
        "creado_en", sa.DateTime(timezone=True),
        server_default=sa.func.now(), nullable=True))
    # Lo que ya estaba no tiene fecha: se comporta como viejo.
    op.execute("UPDATE hotel SET creado_en = NULL")


def downgrade():
    op.drop_column("hotel", "creado_en")

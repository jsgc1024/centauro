"""La marca guarda cuando se hizo y cuando llego

Revision ID: f3c81d5b620e
Revises: e26b47f0a318
"""
from alembic import op
import sqlalchemy as sa


revision = "f3c81d5b620e"
down_revision = "e26b47f0a318"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """La app puede marcar sin senal, y eso hay que poder distinguirlo.

    Un equipo que marca su llegada en un estacionamiento subterraneo
    guarda la marca en el telefono y la manda cuando vuelve la linea. Es
    lo que de verdad pasa en la calle y la app lo va a soportar.

    Pero la hora que manda el telefono es una afirmacion, no un hecho:
    si se guardara sola, cualquiera podria marcar su llegada desde su
    casa media hora despues. Por eso se guardan las dos —lo que dice el
    telefono y cuando llego al servidor— y la diferencia queda a la
    vista de la central en vez de desaparecer.
    """
    op.add_column("hito", sa.Column("recibido_en", sa.DateTime(),
                                    nullable=True))
    op.add_column("hito", sa.Column("diferido", sa.Boolean(), nullable=False,
                                    server_default=sa.text("false")))
    # Lo que ya existe se recibio cuando se marco: no habia otra forma.
    op.execute("UPDATE hito SET recibido_en = marcado_en "
               "WHERE recibido_en IS NULL")


def downgrade() -> None:
    op.drop_column("hito", "diferido")
    op.drop_column("hito", "recibido_en")

"""La llamada de la central al que va en camino.

El toque se le va a un telefono guardado en el bolsillo de alguien que
va manejando, la banda lo pinta en rojo y la central marca su numero.
Lo que contesta no tenia donde asentarse: el rojo se quedaba ahi,
mintiendo.

Se guarda quien lo registro y cuando --no basta con el estado: lo dicho
por telefono no se puede confundir nunca con una posicion del GPS-- y
una nota corta opcional.

Revision ID: e6b95c72d1a4
Revises: d4a7e0b91c35
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6b95c72d1a4"
down_revision: Union[str, None] = "d4a7e0b91c35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trayecto",
                  sa.Column("por_telefono_en", sa.DateTime(), nullable=True))
    op.add_column("trayecto",
                  sa.Column("por_telefono_por_id", sa.Integer(),
                            nullable=True))
    op.add_column("trayecto",
                  sa.Column("por_telefono_nota", sa.String(length=200),
                            nullable=True))
    op.create_foreign_key("fk_trayecto_por_telefono_por", "trayecto",
                          "persona", ["por_telefono_por_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_trayecto_por_telefono_por", "trayecto",
                       type_="foreignkey")
    op.drop_column("trayecto", "por_telefono_nota")
    op.drop_column("trayecto", "por_telefono_por_id")
    op.drop_column("trayecto", "por_telefono_en")

"""La senal de color.

La senal con la que el principal reconoce al equipo podia ser una
palabra o una imagen. Ahora tambien un color: una pantalla de un solo
color en el telefono, que se ve desde lejos. Se guarda la clave de la
paleta (`app/senal.py`), no el hex.

Revision ID: f3a8c1d2e5b7
Revises: e6b95c72d1a4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a8c1d2e5b7"
down_revision: Union[str, None] = "e6b95c72d1a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("servicio",
                  sa.Column("senal_color", sa.String(length=12), nullable=True))


def downgrade() -> None:
    op.drop_column("servicio", "senal_color")

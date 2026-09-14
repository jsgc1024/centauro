"""nombre y apellidos por separado

Quien solicita el servicio y el ejecutivo se capturan en dos campos:
el nombre y los apellidos. El nombre completo se arma al mostrarlo.

Lo que ya estaba capturado se queda tal cual en el nombre: se ve igual
que antes, y al editarlo el consultor lo acomoda en su lugar.

Revision ID: b2f6a0d47c19
Revises: a7d4e19c3b60
Create Date: 2026-09-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2f6a0d47c19"
down_revision: Union[str, None] = "a7d4e19c3b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("servicio", sa.Column("solicitante_apellidos",
                                        sa.String(160), nullable=True))
    op.add_column("servicio", sa.Column("ejecutivo_apellidos",
                                        sa.String(160), nullable=True))


def downgrade() -> None:
    op.drop_column("servicio", "ejecutivo_apellidos")
    op.drop_column("servicio", "solicitante_apellidos")

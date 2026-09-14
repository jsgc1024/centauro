"""vuelo del ejecutivo en la jornada

Revision ID: d3f18a6c5e92
Revises: c9e52f7b4d16
Create Date: 2026-09-12 08:35:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3f18a6c5e92'
down_revision: Union[str, None] = 'c9e52f7b4d16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jornada', sa.Column('vuelo_aerolinea', sa.String(length=80),
                                       nullable=True))
    op.add_column('jornada', sa.Column('vuelo_numero', sa.String(length=20),
                                       nullable=True))
    op.add_column('jornada', sa.Column('vuelo_hora', sa.DateTime(), nullable=True))
    op.add_column('jornada', sa.Column('vuelo_origen', sa.String(length=120),
                                       nullable=True))


def downgrade() -> None:
    op.drop_column('jornada', 'vuelo_origen')
    op.drop_column('jornada', 'vuelo_hora')
    op.drop_column('jornada', 'vuelo_numero')
    op.drop_column('jornada', 'vuelo_aerolinea')

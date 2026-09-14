"""llegada o salida en el vuelo de la jornada

Revision ID: e4a97c12b8d5
Revises: d3f18a6c5e92
Create Date: 2026-09-12 09:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4a97c12b8d5'
down_revision: Union[str, None] = 'd3f18a6c5e92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jornada', sa.Column('vuelo_tipo', sa.String(length=10),
                                       nullable=True))


def downgrade() -> None:
    op.drop_column('jornada', 'vuelo_tipo')

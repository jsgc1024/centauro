"""minutos de anticipacion del equipo, por pais

Revision ID: f5b03e87a1c4
Revises: e4a97c12b8d5
Create Date: 2026-09-12 09:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f5b03e87a1c4'
down_revision: Union[str, None] = 'e4a97c12b8d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pais', sa.Column('anticipacion_aeropuerto_min', sa.Integer(),
                                    server_default='45', nullable=False))
    op.add_column('pais', sa.Column('anticipacion_min', sa.Integer(),
                                    server_default='30', nullable=False))


def downgrade() -> None:
    op.drop_column('pais', 'anticipacion_min')
    op.drop_column('pais', 'anticipacion_aeropuerto_min')

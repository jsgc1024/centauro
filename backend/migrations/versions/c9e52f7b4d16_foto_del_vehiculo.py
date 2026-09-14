"""foto del vehiculo

Revision ID: c9e52f7b4d16
Revises: b7c41d9e2a03
Create Date: 2026-09-12 08:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9e52f7b4d16'
down_revision: Union[str, None] = 'b7c41d9e2a03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('vehiculo',
                  sa.Column('foto_url', sa.String(length=400), nullable=True))


def downgrade() -> None:
    op.drop_column('vehiculo', 'foto_url')

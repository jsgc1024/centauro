"""clave lada por pais

Revision ID: b7c41d9e2a03
Revises: e8ea5b992701
Create Date: 2026-09-12 07:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c41d9e2a03'
down_revision: Union[str, None] = 'e8ea5b992701'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pais', sa.Column('lada', sa.String(length=6),
                                    server_default='', nullable=False))
    # Los paises que ya existen se quedarian sin lada.
    for codigo, lada in (('MX', '+52'), ('BR', '+55'), ('VE', '+58')):
        op.execute(sa.text("UPDATE pais SET lada = :l WHERE codigo = :c "
                           "AND (lada IS NULL OR lada = '')")
                   .bindparams(l=lada, c=codigo))


def downgrade() -> None:
    op.drop_column('pais', 'lada')

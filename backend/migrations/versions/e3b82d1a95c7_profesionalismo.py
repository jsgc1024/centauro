"""tablero de profesionalismo

Revision ID: e3b82d1a95c7
Revises: d7a16c84f3b2
Create Date: 2026-09-12 13:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e3b82d1a95c7'
down_revision: Union[str, None] = 'd7a16c84f3b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dimension = postgresql.ENUM('ESTRELLAS', 'SATISFACCION', 'INCIDENCIAS',
                                'CAPACITACION', 'EXPERIENCIA',
                                name='dimensionprofesionalismo')
    dimension.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'peso_profesionalismo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('dimension', dimension, nullable=False),
        sa.Column('peso', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['pais_id'], ['pais.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pais_id', 'dimension'),
    )

    op.create_table(
        'parametro_profesionalismo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('meses_ventana', sa.Integer(), server_default='6',
                  nullable=False),
        sa.Column('horas_referencia', sa.Integer(), server_default='2000',
                  nullable=False),
        sa.Column('castigo_error_menor', sa.Numeric(precision=5, scale=2),
                  server_default='0', nullable=False),
        sa.Column('castigo_leve', sa.Numeric(precision=5, scale=2),
                  server_default='25', nullable=False),
        sa.Column('castigo_grave', sa.Numeric(precision=5, scale=2),
                  server_default='60', nullable=False),
        sa.ForeignKeyConstraint(['pais_id'], ['pais.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pais_id'),
    )


def downgrade() -> None:
    op.drop_table('parametro_profesionalismo')
    op.drop_table('peso_profesionalismo')
    op.execute('DROP TYPE IF EXISTS dimensionprofesionalismo')

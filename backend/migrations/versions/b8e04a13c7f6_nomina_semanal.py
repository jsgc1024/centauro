"""nomina semanal del personal de seguridad

Revision ID: b8e04a13c7f6
Revises: a1c73d5f9e28
Create Date: 2026-09-12 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b8e04a13c7f6'
down_revision: Union[str, None] = 'a1c73d5f9e28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    estatus = postgresql.ENUM('CALCULADA', 'PAGADA', name='estatusnomina')
    estatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'nomina_semanal',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('fecha_corte', sa.Date(), nullable=False),
        sa.Column('moneda', postgresql.ENUM(name='moneda', create_type=False),
                  nullable=False),
        sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('estatus', estatus, nullable=False),
        sa.Column('calculada_en', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('pagada_en', sa.DateTime(), nullable=True),
        sa.Column('pagada_por_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['pais_id'], ['pais.id']),
        sa.ForeignKeyConstraint(['pagada_por_id'], ['persona.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pais_id', 'fecha_corte'),
    )
    op.create_index('ix_nomina_semanal_fecha_corte', 'nomina_semanal',
                    ['fecha_corte'])

    op.create_table(
        'ajuste_nomina',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('servicio_id', sa.Integer(), nullable=True),
        sa.Column('jornada_id', sa.Integer(), nullable=True),
        sa.Column('monto', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('motivo', sa.String(length=400), nullable=False),
        sa.Column('pagado_en_nomina_id', sa.Integer(), nullable=True),
        sa.Column('aplicado_en_nomina_id', sa.Integer(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('creado_por_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['persona_id'], ['persona.id']),
        sa.ForeignKeyConstraint(['pais_id'], ['pais.id']),
        sa.ForeignKeyConstraint(['servicio_id'], ['servicio.id']),
        sa.ForeignKeyConstraint(['jornada_id'], ['jornada.id']),
        sa.ForeignKeyConstraint(['pagado_en_nomina_id'], ['nomina_semanal.id']),
        sa.ForeignKeyConstraint(['aplicado_en_nomina_id'], ['nomina_semanal.id']),
        sa.ForeignKeyConstraint(['creado_por_id'], ['persona.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ajuste_nomina_persona_id', 'ajuste_nomina', ['persona_id'])
    op.create_index('ix_ajuste_nomina_aplicado', 'ajuste_nomina',
                    ['aplicado_en_nomina_id'])

    op.create_table(
        'renglon_nomina',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nomina_id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['nomina_id'], ['nomina_semanal.id']),
        sa.ForeignKeyConstraint(['persona_id'], ['persona.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nomina_id', 'persona_id'),
    )

    op.create_table(
        'concepto_nomina',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('renglon_id', sa.Integer(), nullable=False),
        sa.Column('jornada_id', sa.Integer(), nullable=True),
        sa.Column('ajuste_id', sa.Integer(), nullable=True),
        sa.Column('descripcion', sa.String(length=300), nullable=False),
        sa.Column('monto', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('factor_festivo', sa.Numeric(precision=4, scale=2),
                  nullable=False),
        sa.Column('horas_extra', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['renglon_id'], ['renglon_nomina.id']),
        sa.ForeignKeyConstraint(['jornada_id'], ['jornada.id']),
        sa.ForeignKeyConstraint(['ajuste_id'], ['ajuste_nomina.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_concepto_nomina_jornada_id', 'concepto_nomina',
                    ['jornada_id'])


def downgrade() -> None:
    op.drop_table('concepto_nomina')
    op.drop_table('renglon_nomina')
    op.drop_table('ajuste_nomina')
    op.drop_table('nomina_semanal')
    op.execute('DROP TYPE IF EXISTS estatusnomina')

"""alertas de incidencia y reemplazo de recurso

Revision ID: a1c73d5f9e28
Revises: f5b03e87a1c4
Create Date: 2026-09-12 10:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a1c73d5f9e28'
down_revision: Union[str, None] = 'f5b03e87a1c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Un viatico que nunca recibio dinero y ya no aplica se cancela.
    op.execute("ALTER TYPE estatusviatico ADD VALUE IF NOT EXISTS 'CANCELADO'")

    canal = postgresql.ENUM('BOTON_APP', 'BOTON_VEHICULO', 'LLAMADA',
                            name='canalalerta')
    canal.create(op.get_bind(), checkfirst=True)
    estatus = postgresql.ENUM('ABIERTA', 'EN_ATENCION', 'CERRADA',
                              name='estatusalerta')
    estatus.create(op.get_bind(), checkfirst=True)
    tipo = postgresql.ENUM('PERSONAL', 'VEHICULO', name='tiporecurso')
    tipo.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'alerta_incidencia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('jornada_id', sa.Integer(), nullable=True),
        sa.Column('servicio_id', sa.Integer(), nullable=True),
        sa.Column('reporta_persona_id', sa.Integer(), nullable=True),
        sa.Column('canal', canal, nullable=False),
        sa.Column('descripcion', sa.String(length=600), nullable=True),
        sa.Column('lat', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('lon', sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column('reportada_en', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('estatus', estatus, nullable=False),
        sa.Column('tomada_por_id', sa.Integer(), nullable=True),
        sa.Column('tomada_en', sa.DateTime(), nullable=True),
        sa.Column('equipo_respuesta_enviado', sa.Boolean(), nullable=False),
        sa.Column('cerrada_por_id', sa.Integer(), nullable=True),
        sa.Column('cerrada_en', sa.DateTime(), nullable=True),
        sa.Column('resolucion', sa.String(length=600), nullable=True),
        sa.ForeignKeyConstraint(['jornada_id'], ['jornada.id']),
        sa.ForeignKeyConstraint(['servicio_id'], ['servicio.id']),
        sa.ForeignKeyConstraint(['reporta_persona_id'], ['persona.id']),
        sa.ForeignKeyConstraint(['tomada_por_id'], ['persona.id']),
        sa.ForeignKeyConstraint(['cerrada_por_id'], ['persona.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_alerta_incidencia_jornada_id', 'alerta_incidencia',
                    ['jornada_id'])
    op.create_index('ix_alerta_incidencia_servicio_id', 'alerta_incidencia',
                    ['servicio_id'])
    op.create_index('ix_alerta_incidencia_estatus', 'alerta_incidencia',
                    ['estatus'])

    op.create_table(
        'reemplazo_recurso',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alerta_id', sa.Integer(), nullable=True),
        sa.Column('servicio_id', sa.Integer(), nullable=False),
        sa.Column('desde_jornada_id', sa.Integer(), nullable=False),
        sa.Column('tipo', tipo, nullable=False),
        sa.Column('sale_persona_id', sa.Integer(), nullable=True),
        sa.Column('entra_persona_id', sa.Integer(), nullable=True),
        sa.Column('sale_vehiculo_id', sa.Integer(), nullable=True),
        sa.Column('entra_vehiculo_id', sa.Integer(), nullable=True),
        sa.Column('motivo', sa.String(length=600), nullable=False),
        sa.Column('jornadas_afectadas', sa.Integer(), nullable=False),
        sa.Column('hecho_por_id', sa.Integer(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['alerta_id'], ['alerta_incidencia.id']),
        sa.ForeignKeyConstraint(['servicio_id'], ['servicio.id']),
        sa.ForeignKeyConstraint(['desde_jornada_id'], ['jornada.id']),
        sa.ForeignKeyConstraint(['sale_persona_id'], ['persona.id']),
        sa.ForeignKeyConstraint(['entra_persona_id'], ['persona.id']),
        sa.ForeignKeyConstraint(['sale_vehiculo_id'], ['vehiculo.id']),
        sa.ForeignKeyConstraint(['entra_vehiculo_id'], ['vehiculo.id']),
        sa.ForeignKeyConstraint(['hecho_por_id'], ['persona.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_reemplazo_recurso_servicio_id', 'reemplazo_recurso',
                    ['servicio_id'])


def downgrade() -> None:
    op.drop_table('reemplazo_recurso')
    op.drop_table('alerta_incidencia')
    for nombre in ('tiporecurso', 'estatusalerta', 'canalalerta'):
        op.execute(f'DROP TYPE IF EXISTS {nombre}')
    # El valor del enum de viaticos no se quita: Postgres no lo permite.

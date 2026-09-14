"""encuestas de satisfaccion

Revision ID: d7a16c84f3b2
Revises: c2f95b706e41
Create Date: 2026-09-12 12:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd7a16c84f3b2'
down_revision: Union[str, None] = 'c2f95b706e41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tipo = postgresql.ENUM('EJECUTIVO', 'SOLICITANTE', name='tipoencuesta')
    tipo.create(op.get_bind(), checkfirst=True)
    estatus = postgresql.ENUM('ENVIADA', 'RESPONDIDA', 'EXPIRADA',
                              name='estatusencuesta')
    estatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'encuesta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('servicio_id', sa.Integer(), nullable=False),
        sa.Column('tipo', tipo, nullable=False),
        sa.Column('consultor_id', sa.Integer(), nullable=True),
        sa.Column('destinatario_nombre', sa.String(length=160), nullable=True),
        sa.Column('destinatario_correo', sa.String(length=160), nullable=True),
        sa.Column('idioma', sa.String(length=2), server_default='en',
                  nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('expira_en', sa.DateTime(), nullable=False),
        sa.Column('enviada_en', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('respondida_en', sa.DateTime(), nullable=True),
        sa.Column('estatus', estatus, nullable=False),
        sa.Column('calificacion', sa.Integer(), nullable=True),
        sa.Column('requiere_clasificacion', sa.Boolean(),
                  server_default='false', nullable=False),
        sa.Column('incidencia_id', sa.Integer(), nullable=True),
        sa.Column('clasificada_en', sa.DateTime(), nullable=True),
        sa.Column('nota_clasificacion', sa.String(length=600), nullable=True),
        sa.ForeignKeyConstraint(['servicio_id'], ['servicio.id']),
        sa.ForeignKeyConstraint(['consultor_id'], ['persona.id']),
        sa.ForeignKeyConstraint(['incidencia_id'], ['incidencia.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('servicio_id', 'tipo'),
        sa.UniqueConstraint('token'),
    )
    op.create_index('ix_encuesta_servicio_id', 'encuesta', ['servicio_id'])
    op.create_index('ix_encuesta_token', 'encuesta', ['token'])
    op.create_index('ix_encuesta_estatus', 'encuesta', ['estatus'])

    op.create_table(
        'respuesta_encuesta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('encuesta_id', sa.Integer(), nullable=False),
        sa.Column('pregunta', sa.String(length=40), nullable=False),
        sa.Column('valor', sa.Integer(), nullable=True),
        sa.Column('texto', sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(['encuesta_id'], ['encuesta.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('respuesta_encuesta')
    op.drop_table('encuesta')
    op.execute('DROP TYPE IF EXISTS estatusencuesta')
    op.execute('DROP TYPE IF EXISTS tipoencuesta')

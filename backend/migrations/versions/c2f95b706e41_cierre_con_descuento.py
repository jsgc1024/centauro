"""rechazo de comprobantes y cierre de viaticos con descuento

Revision ID: c2f95b706e41
Revises: b8e04a13c7f6
Create Date: 2026-09-12 11:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2f95b706e41'
down_revision: Union[str, None] = 'b8e04a13c7f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('comprobante', sa.Column('rechazado', sa.Boolean(),
                                           server_default='false', nullable=False))
    op.add_column('comprobante', sa.Column('motivo_rechazo', sa.String(length=300),
                                           nullable=True))

    op.add_column('asignacion_viatico',
                  sa.Column('cerrado_con_descuento', sa.Boolean(),
                            server_default='false', nullable=False))
    op.add_column('asignacion_viatico',
                  sa.Column('monto_descontado', sa.Numeric(precision=12, scale=2),
                            server_default='0', nullable=False))
    op.add_column('asignacion_viatico',
                  sa.Column('monto_absorbido', sa.Numeric(precision=12, scale=2),
                            server_default='0', nullable=False))
    op.add_column('asignacion_viatico',
                  sa.Column('motivo_cierre', sa.String(length=400), nullable=True))
    op.add_column('asignacion_viatico',
                  sa.Column('cerrado_por_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_asignacion_viatico_cerrado_por',
                          'asignacion_viatico', 'persona',
                          ['cerrado_por_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_asignacion_viatico_cerrado_por', 'asignacion_viatico',
                       type_='foreignkey')
    op.drop_column('asignacion_viatico', 'cerrado_por_id')
    op.drop_column('asignacion_viatico', 'motivo_cierre')
    op.drop_column('asignacion_viatico', 'monto_absorbido')
    op.drop_column('asignacion_viatico', 'monto_descontado')
    op.drop_column('asignacion_viatico', 'cerrado_con_descuento')
    op.drop_column('comprobante', 'motivo_rechazo')
    op.drop_column('comprobante', 'rechazado')

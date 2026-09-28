"""El deposito que salio con parte ya cancelada (seccion 98)

Finanzas vio tres dias, fue al banco, y mientras tanto el consultor
quito uno. El deposito se registra entero --asi salio-- y queda escrito
cuanto de el era de solicitudes ya canceladas: esa es la parte que el
consultor tiene que aplicar o pedir de vuelta, no el deposito completo.

Revision ID: e7b3d9a1c5f4
Revises: c4a8e2d6f193
"""
import sqlalchemy as sa
from alembic import op

revision = "e7b3d9a1c5f4"
down_revision = "c4a8e2d6f193"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deposito_bancario",
                  sa.Column("monto_sobre_cancelada", sa.Numeric(12, 2),
                            nullable=True))


def downgrade() -> None:
    op.drop_column("deposito_bancario", "monto_sobre_cancelada")

"""Los clientes, leidos de Odoo (seccion 75)

Tercer paso de la propuesta Puestos y Odoo (Salvador, 26 de septiembre):
los clientes se dan de alta en Odoo y Centauro los lee de ahi, con su
RFC. El tarifario sigue siendo de Centauro.

Revision ID: d8e2f6a4b1c3
Revises: c7d1e5f3a912
"""
import sqlalchemy as sa
from alembic import op

revision = "d8e2f6a4b1c3"
down_revision = "c7d1e5f3a912"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cliente", sa.Column("rfc", sa.String(30), nullable=True))
    op.add_column("cliente", sa.Column("odoo_sincronizado_en", sa.DateTime(),
                                       nullable=True))


def downgrade() -> None:
    op.drop_column("cliente", "odoo_sincronizado_en")
    op.drop_column("cliente", "rfc")

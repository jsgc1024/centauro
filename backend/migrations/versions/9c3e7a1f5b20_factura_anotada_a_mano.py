"""La factura que se hizo en Odoo, anotada a mano (seccion 96)

Mientras la factura no se conecta con Odoo, finanzas la hace alla y
anota aqui su folio y su fecha. Se guarda quien la anoto: la anotada a
mano se corrige aqui; la que llega de Odoo, en Odoo.

Revision ID: 9c3e7a1f5b20
Revises: 6e1f3b8c2d47
"""
import sqlalchemy as sa
from alembic import op

revision = "9c3e7a1f5b20"
down_revision = "6e1f3b8c2d47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cierre", sa.Column("factura_anotada_por_id", sa.Integer(),
                                      nullable=True))
    op.create_foreign_key("fk_cierre_factura_anotada_por", "cierre", "persona",
                          ["factura_anotada_por_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_cierre_factura_anotada_por", "cierre",
                       type_="foreignkey")
    op.drop_column("cierre", "factura_anotada_por_id")

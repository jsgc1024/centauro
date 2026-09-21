"""La factura del servicio aprobado.

`facturado` existia en el catalogo desde el principio y no lo escribia
nadie: despues de que finanzas aprobaba, el servicio se quedaba sin quien
dijera "ya se facturo". Aqui vive el folio que devuelve Odoo, cuando se
mando, y por que no salio si fallo.

Revision ID: b94c02e7f351
Revises: a83f1e6c05b7
"""
from alembic import op
import sqlalchemy as sa

revision = "b94c02e7f351"
down_revision = "a83f1e6c05b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cierre",
                  sa.Column("facturado_en", sa.DateTime(), nullable=True))
    op.add_column("cierre",
                  sa.Column("factura_odoo", sa.String(length=60),
                            nullable=True))
    op.add_column("cierre",
                  sa.Column("factura_error", sa.String(length=400),
                            nullable=True))


def downgrade() -> None:
    op.drop_column("cierre", "factura_error")
    op.drop_column("cierre", "factura_odoo")
    op.drop_column("cierre", "facturado_en")

"""La cotizacion autorizada, en el servicio (seccion 94)

Mientras Odoo no manda la cotizacion, el consultor la registra en
Centauro con los precios del tarifario del cliente. De la autorizacion
se guarda quien la dio del lado del cliente --eso ya estaba--, el dia en
que la dio y, si la cotizacion se hizo en Odoo, su folio.

Revision ID: 6e1f3b8c2d47
Revises: 4b7d2e9a1c63
"""
import sqlalchemy as sa
from alembic import op

revision = "6e1f3b8c2d47"
down_revision = "4b7d2e9a1c63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cotizacion", sa.Column("autorizada_el", sa.Date(), nullable=True))
    op.add_column("cotizacion", sa.Column("folio_odoo", sa.String(length=40),
                                          nullable=True))


def downgrade() -> None:
    op.drop_column("cotizacion", "folio_odoo")
    op.drop_column("cotizacion", "autorizada_el")

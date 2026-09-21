"""El deposito que llega cuando la solicitud ya se cancelo

El consultor cancela el deposito y, mientras tanto, finanzas ya fue al
banco. Vuelve a subir el comprobante y el sistema le contestaba 404: el
dinero salio y no habia donde registrarlo. Lo que no se puede registrar
se arregla por fuera, y lo que se arregla por fuera no se audita.

Tres columnas:

- `cancelacion_pedida_en` y `cancelacion_pedida_por_id`: lo que ya esta
  en manos de finanzas no lo cancela el consultor solo. Queda pedida y
  finanzas la cierra, porque el unico que sabe si el dinero ya salio del
  banco es finanzas.
- `sobre_cancelada`: el deposito que llego tarde. No se rechaza; queda
  marcado para que el consultor lo vea y decida si se aplica o se pide
  de vuelta.

Revision ID: a4b71c92e5d8
Revises: f1a20d64c9b3
"""
import sqlalchemy as sa
from alembic import op

revision = "a4b71c92e5d8"
down_revision = "f1a20d64c9b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("solicitud_transferencia",
                  sa.Column("cancelacion_pedida_en", sa.DateTime(),
                            nullable=True))
    op.add_column("solicitud_transferencia",
                  sa.Column("cancelacion_pedida_por_id", sa.Integer(),
                            sa.ForeignKey("persona.id"), nullable=True))
    op.add_column("deposito_bancario",
                  sa.Column("sobre_cancelada", sa.Boolean(), nullable=False,
                            server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("deposito_bancario", "sobre_cancelada")
    op.drop_column("solicitud_transferencia", "cancelacion_pedida_por_id")
    op.drop_column("solicitud_transferencia", "cancelacion_pedida_en")

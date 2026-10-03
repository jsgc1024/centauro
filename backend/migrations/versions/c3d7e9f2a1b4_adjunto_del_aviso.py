"""El archivo que viaja con un aviso (seccion 131, decision 16)

Cuando alguien manda una cotizacion o una propuesta firmada por otro
consultor, el titular recibe el aviso con el PDF que salio con su firma.
El aviso guarda la referencia al PDF que ya esta en `archivo_cotizacion`;
el despachador lo adjunta al correo.

Revision ID: c3d7e9f2a1b4
Revises: b7d3e9a1c5f2
"""
import sqlalchemy as sa
from alembic import op

revision = "c3d7e9f2a1b4"
down_revision = "b7d3e9a1c5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notificacion",
        sa.Column("adjunto_id", sa.Integer(),
                  sa.ForeignKey("archivo_cotizacion.id", ondelete="SET NULL"),
                  nullable=True))


def downgrade() -> None:
    op.drop_column("notificacion", "adjunto_id")

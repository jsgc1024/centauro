"""La cotizacion eliminada (seccion 126)

La cotizacion autorizada cuyo servicio se elimino se quedaba atorada: ni
otra version --ya estaba autorizada-- ni su servicio. Ahora se vuelve a
crear su servicio o se elimina la cotizacion. De la eliminada queda su
renglon: que era, quien la quito y por que; y su folio no se vuelve a
usar.

Revision ID: b7d3e9a1c5f2
Revises: e4b8c2a6d9f1
"""
import sqlalchemy as sa
from alembic import op

revision = "b7d3e9a1c5f2"
down_revision = "e4b8c2a6d9f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cotizacion_eliminada",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clase", sa.String(12), nullable=False,
                  server_default="cotizacion"),
        sa.Column("folio", sa.Integer(), nullable=False),
        sa.Column("cliente", sa.String(200), nullable=True),
        sa.Column("resumen", sa.String(400), nullable=True),
        sa.Column("motivo", sa.String(300), nullable=True),
        sa.Column("eliminado_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("eliminado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cotizacion_eliminada")

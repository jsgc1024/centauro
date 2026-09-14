"""Bitacora de servicios eliminados

Revision ID: c9f402ba1d76
Revises: b3e7d1f95c42
Create Date: 2026-09-12

Un servicio se puede borrar mientras no se haya movido. Su bitacora se
va con el, asi que el rastro de la eliminacion se guarda aparte.
"""
import sqlalchemy as sa
from alembic import op

revision = "c9f402ba1d76"
down_revision = "b3e7d1f95c42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "servicio_eliminado",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("folio", sa.String(20), nullable=False),
        sa.Column("cliente", sa.String(160), nullable=True),
        sa.Column("resumen", sa.String(400), nullable=True),
        sa.Column("motivo", sa.String(300), nullable=True),
        sa.Column("eliminado_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id"), nullable=True),
        sa.Column("eliminado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("servicio_eliminado")

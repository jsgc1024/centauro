"""El arranque: lo que se confirma a mano (seccion 97)

El respaldo y sus alertas viven en el servidor, fuera del alcance del
sistema: el arranque los confirma a mano, con nombre y fecha.

Revision ID: c4a8e2d6f193
Revises: 9c3e7a1f5b20
"""
import sqlalchemy as sa
from alembic import op

revision = "c4a8e2d6f193"
down_revision = "9c3e7a1f5b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "confirmacion_arranque",
        sa.Column("clave", sa.String(length=40), primary_key=True),
        sa.Column("confirmado_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("confirmado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("confirmacion_arranque")

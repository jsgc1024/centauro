"""La nota de turno de la bitacora.

Lo que la central averigua por telefono no tenia donde vivir: se quedaba
en la cabeza de quien contesto y el turno siguiente no lo heredaba.

Revision ID: c7a35e91b0d4
Revises: b4e29c07d1f8
"""
from alembic import op
import sqlalchemy as sa

revision = "c7a35e91b0d4"
down_revision = "b4e29c07d1f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nota_bitacora",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("jornada_id", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.Integer(), nullable=False),
        sa.Column("texto", sa.String(length=600), nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["jornada_id"], ["jornada.id"]),
        sa.ForeignKeyConstraint(["persona_id"], ["persona.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_nota_bitacora_jornada", "nota_bitacora",
                    ["jornada_id"])


def downgrade() -> None:
    op.drop_index("ix_nota_bitacora_jornada", table_name="nota_bitacora")
    op.drop_table("nota_bitacora")

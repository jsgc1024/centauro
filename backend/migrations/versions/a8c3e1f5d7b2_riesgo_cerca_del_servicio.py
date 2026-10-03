"""El riesgo cerca del servicio, en la app de campo (seccion 137)

A quien del personal de seguridad se le aviso de un evento de riesgo por
caer cerca de su servicio de hoy: uno por evento, persona y nivel.

Revision ID: a8c3e1f5d7b2
Revises: f2d8a4c6e0b3
"""
import sqlalchemy as sa
from alembic import op

revision = "a8c3e1f5d7b2"
down_revision = "f2d8a4c6e0b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aviso_riesgo_campo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evento_id", sa.Integer(),
                  sa.ForeignKey("evento_riesgo.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("persona_id", sa.Integer(),
                  sa.ForeignKey("persona.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("jornada_id", sa.Integer(),
                  sa.ForeignKey("jornada.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("nivel", sa.Integer(), nullable=False),
        sa.Column("km", sa.Numeric(6, 1), nullable=False),
        sa.Column("telefonos", sa.Integer(), server_default="0",
                  nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("evento_id", "persona_id", "nivel",
                            name="uq_aviso_riesgo_campo"),
    )
    op.create_index("ix_aviso_riesgo_campo_evento_id", "aviso_riesgo_campo",
                    ["evento_id"])
    op.create_index("ix_aviso_riesgo_campo_persona_id", "aviso_riesgo_campo",
                    ["persona_id"])


def downgrade() -> None:
    op.drop_index("ix_aviso_riesgo_campo_persona_id",
                  table_name="aviso_riesgo_campo")
    op.drop_index("ix_aviso_riesgo_campo_evento_id",
                  table_name="aviso_riesgo_campo")
    op.drop_table("aviso_riesgo_campo")

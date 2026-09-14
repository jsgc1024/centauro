"""El telefono del equipo puede recibir avisos

Revision ID: b58d30f4a916
Revises: a47e92b0c5d3
"""
from alembic import op
import sqlalchemy as sa


revision = "b58d30f4a916"
down_revision = "a47e92b0c5d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """A donde mandarle un aviso a cada telefono.

    La confirmacion de la vispera dependia de que alguien se acordara de
    abrir la app. Con esto el aviso llega solo, sin costo por mensaje y
    sin terceros: lo entrega el propio navegador.

    Una persona puede tener varios telefonos —el suyo y el de la empresa,
    o uno nuevo— y cada uno es una suscripcion aparte. El endpoint es la
    direccion que da el navegador; cuando deja de existir, el servicio de
    avisos contesta que ya no vale y esa fila se apaga sola.
    """
    op.create_table(
        "suscripcion_push",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("agente", sa.String(300), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("creada_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("ultimo_aviso_en", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["persona_id"], ["persona.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint", name="uq_suscripcion_endpoint"),
    )
    op.create_index("ix_suscripcion_push_persona_id", "suscripcion_push",
                    ["persona_id"])


def downgrade() -> None:
    op.drop_index("ix_suscripcion_push_persona_id",
                  table_name="suscripcion_push")
    op.drop_table("suscripcion_push")

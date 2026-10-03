"""El acceso a la app del cliente de la Central (seccion 136)

Los enlaces para poner la contrasena: la invitacion al darlo de alta y
el de «olvide mi contrasena». Del token se guarda solo su huella.

Revision ID: f2d8a4c6e0b3
Revises: e6c4a2f0b8d1
"""
import sqlalchemy as sa
from alembic import op

revision = "f2d8a4c6e0b3"
down_revision = "e6c4a2f0b8d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enlace_cliente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_cliente_id", sa.Integer(),
                  sa.ForeignKey("usuario_cliente.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("huella", sa.String(64), nullable=False, unique=True),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anulado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correo_id", sa.Integer(),
                  sa.ForeignKey("notificacion.id", ondelete="SET NULL"),
                  nullable=True),
    )
    op.create_index("ix_enlace_cliente_usuario_cliente_id", "enlace_cliente",
                    ["usuario_cliente_id"])


def downgrade() -> None:
    op.drop_index("ix_enlace_cliente_usuario_cliente_id",
                  table_name="enlace_cliente")
    op.drop_table("enlace_cliente")

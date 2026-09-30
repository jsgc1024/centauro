"""Entrar con huella o cara: las llaves de acceso

Decision de Salvador, 30 sep: en la consola y en la app de campo se
entra con la huella o la cara del telefono (o el Touch ID de la
computadora) en vez de escribir la contrasena cada vez. Los telefonos
son de cada quien, no se prestan. La huella no sale del telefono: aqui
se guarda la llave publica que el telefono crea para este sistema.

Una tabla nueva, `llave_acceso`. Lo que ya existe no cambia.

Revision ID: f1b3d5a7c9e2
Revises: f0b2d4e6a8c0
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op

revision = "f1b3d5a7c9e2"
down_revision = "f0b2d4e6a8c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llave_acceso",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuario.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("credencial_id", sa.String(400), nullable=False),
        sa.Column("llave_publica", sa.Text(), nullable=False),
        sa.Column("contador", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("usada_en", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("credencial_id"),
    )
    op.create_index("ix_llave_acceso_usuario_id", "llave_acceso",
                    ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_llave_acceso_usuario_id", table_name="llave_acceso")
    op.drop_table("llave_acceso")

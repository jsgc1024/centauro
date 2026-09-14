"""catalogo de solicitantes por cliente

Quien pide servicios a nombre de un cliente se da de alta la primera vez
y queda guardado: en los siguientes se elige de la lista.

Revision ID: c4d91b7e2f08
Revises: b2f6a0d47c19
Create Date: 2026-09-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d91b7e2f08"
down_revision: Union[str, None] = "b2f6a0d47c19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "solicitante",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("apellidos", sa.String(length=160), nullable=True),
        sa.Column("correo", sa.String(length=160), nullable=True),
        sa.Column("telefono", sa.String(length=40), nullable=True),
        sa.Column("puesto", sa.String(length=120), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["cliente_id"], ["cliente.id"]),
        sa.PrimaryKeyConstraint("id"),
        # Un mismo correo no se da de alta dos veces en el mismo cliente.
        sa.UniqueConstraint("cliente_id", "correo"),
    )
    op.add_column("servicio", sa.Column("solicitante_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_servicio_solicitante", "servicio", "solicitante",
                          ["solicitante_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_servicio_solicitante", "servicio", type_="foreignkey")
    op.drop_column("servicio", "solicitante_id")
    op.drop_table("solicitante")

"""Cuando vio el recorrido de la primera vez

Va en el usuario y no en el navegador: quien ya lo vio no tiene que
volver a verlo porque cambio de computadora, y quien nunca lo vio lo ve
aunque entre desde una que ya lo mostro.

En nulo quiere decir que todavia no lo ha visto. Todos los usuarios que
ya existen entran asi --nadie lo ha visto, porque no existia-- y les va
a salir la proxima vez que entren.

Revision ID: a7d2c48f91e0
Revises: f0b82e4c15d7
"""
import sqlalchemy as sa
from alembic import op

revision = "a7d2c48f91e0"
down_revision = "f0b82e4c15d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usuario",
                  sa.Column("recorrido_en", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("usuario", "recorrido_en")

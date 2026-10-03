"""Lo de nivel 3 y 4 muy confirmado tambien sale solo (seccion 147)

Las dos reglas nuevas en los parametros del lector: nivel 3 y nivel 4 muy
confirmados (una fuente oficial y dos medios mas, o cuatro medios). Nacen
encendidas: Salvador, 3 oct.

Revision ID: b7d9f1a3c5e8
Revises: a5c7e9b1d3f6
"""
import sqlalchemy as sa
from alembic import op

revision = "b7d9f1a3c5e8"
down_revision = "a5c7e9b1d3f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for regla in ("solo_alto", "solo_critico"):
        op.add_column("parametros_lector",
                      sa.Column(regla, sa.Boolean(), server_default="true",
                                nullable=False))


def downgrade() -> None:
    op.drop_column("parametros_lector", "solo_critico")
    op.drop_column("parametros_lector", "solo_alto")

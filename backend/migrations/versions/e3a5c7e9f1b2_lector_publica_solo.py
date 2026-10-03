"""Lo que Connect publica solo, sin analista (seccion 143)

Las reglas en los parametros del lector, el texto para el cliente que
escribe Claude en el hallazgo, y en el evento por que regla salio solo.

Revision ID: e3a5c7e9f1b2
Revises: d2f4a6c8e0b1
"""
import sqlalchemy as sa
from alembic import op

revision = "e3a5c7e9f1b2"
down_revision = "d2f4a6c8e0b1"
branch_labels = None
depends_on = None

REGLAS = ("solo_activo", "solo_oficial", "solo_confirmado",
          "solo_informativo")


def upgrade() -> None:
    for regla in REGLAS:
        op.add_column("parametros_lector",
                      sa.Column(regla, sa.Boolean(), server_default="true",
                                nullable=False))
    op.add_column("hallazgo_lector",
                  sa.Column("texto_cliente", sa.Text(), server_default="",
                            nullable=False))
    op.add_column("evento_riesgo",
                  sa.Column("auto_regla", sa.String(12), nullable=True))
    op.add_column("evento_riesgo",
                  sa.Column("auto_dato", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("evento_riesgo", "auto_dato")
    op.drop_column("evento_riesgo", "auto_regla")
    op.drop_column("hallazgo_lector", "texto_cliente")
    for regla in REGLAS:
        op.drop_column("parametros_lector", regla)

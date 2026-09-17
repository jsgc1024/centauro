"""La alerta dice a quien se refiere

Cuando alguien intenta marcar su llegada desde tres kilometros, el
sistema rechaza la marca y no guarda el hito: lo unico que queda es la
alerta. Sin un nombre en ella, la direccion ve que hubo un intento y no
tiene a quien preguntarle.

Queda opcional a proposito: las alertas de la jornada entera --sin
reporte, horas extra por venir-- no son de nadie en particular.

Revision ID: d61e8b47c095
Revises: c58d2a91f403
"""
import sqlalchemy as sa
from alembic import op

revision = "d61e8b47c095"
down_revision = "c58d2a91f403"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerta", sa.Column("persona_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_alerta_persona", "alerta", "persona",
                          ["persona_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_alerta_persona", "alerta", type_="foreignkey")
    op.drop_column("alerta", "persona_id")

"""El sello de la confirmacion.

El agente sin la app instalada no podia confirmar de ninguna manera, y
la central lo confirmaba por telefono sin que eso pudiera quedar en
ningun lado. Ahora se registra, y se registra sellado: quien confirmo
por el, cuando, y con que nota. Una confirmacion de otro no es la misma
cosa que la de la persona.

Revision ID: d1f8a3c60b92
Revises: c7a35e91b0d4
"""
from alembic import op
import sqlalchemy as sa

revision = "d1f8a3c60b92"
down_revision = "c7a35e91b0d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("asignacion_personal",
                  sa.Column("confirmado_en", sa.DateTime(), nullable=True))
    op.add_column("asignacion_personal",
                  sa.Column("confirmado_por_id", sa.Integer(), nullable=True))
    op.add_column("asignacion_personal",
                  sa.Column("nota_confirmacion", sa.String(length=200),
                            nullable=True))
    op.create_foreign_key("fk_asignacion_personal_confirmado_por",
                          "asignacion_personal", "persona",
                          ["confirmado_por_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_asignacion_personal_confirmado_por",
                       "asignacion_personal", type_="foreignkey")
    op.drop_column("asignacion_personal", "nota_confirmacion")
    op.drop_column("asignacion_personal", "confirmado_por_id")
    op.drop_column("asignacion_personal", "confirmado_en")

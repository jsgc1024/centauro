"""El meet and greet registrado a mano por la central.

Ajustar un hito corrige la hora de una marca que existe. Esto crea una
marca que nunca se hizo, cuando el equipo llego al punto y nadie marco
desde la app. De `inicio_real` salen las horas que se le facturan al
cliente, asi que la diferencia entre lo marcado desde la calle y lo
firmado desde una oficina tiene que quedar sellada para siempre.

Revision ID: b4e29c07d1f8
Revises: a6d81f39c204
"""
from alembic import op
import sqlalchemy as sa

revision = "b4e29c07d1f8"
down_revision = "a6d81f39c204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hito", sa.Column("registrado_a_mano_por_id",
                                    sa.Integer(), nullable=True))
    op.add_column("hito", sa.Column("registrado_a_mano_en",
                                    sa.DateTime(), nullable=True))
    op.add_column("hito", sa.Column("motivo_a_mano",
                                    sa.String(length=400), nullable=True))
    op.create_foreign_key("fk_hito_registrado_a_mano_por", "hito", "persona",
                          ["registrado_a_mano_por_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_hito_registrado_a_mano_por", "hito",
                       type_="foreignkey")
    op.drop_column("hito", "motivo_a_mano")
    op.drop_column("hito", "registrado_a_mano_en")
    op.drop_column("hito", "registrado_a_mano_por_id")

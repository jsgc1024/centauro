"""La marca de fin que se anula al reabrir un dia.

La central podia deshacer solo lo que ella misma habia cerrado. Un dia
cerrado por el equipo desde la calle no se podia reabrir de ninguna
manera, y en pruebas --y en la calle-- eso pasa: se marca el fin en el
servicio equivocado, o el equipo sigue trabajando despues de cerrar.

La marca no se borra: se anula, con quien lo hizo y por que.

Revision ID: c07b53a91e46
Revises: b94c02e7f351
"""
from alembic import op
import sqlalchemy as sa

revision = "c07b53a91e46"
down_revision = "b94c02e7f351"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hito", sa.Column("anulado_en", sa.DateTime(), nullable=True))
    op.add_column("hito", sa.Column("anulado_por_id", sa.Integer(),
                                    nullable=True))
    op.add_column("hito", sa.Column("motivo_anulacion", sa.String(length=400),
                                    nullable=True))
    op.create_foreign_key("fk_hito_anulado_por", "hito", "persona",
                          ["anulado_por_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_hito_anulado_por", "hito", type_="foreignkey")
    op.drop_column("hito", "motivo_anulacion")
    op.drop_column("hito", "anulado_por_id")
    op.drop_column("hito", "anulado_en")

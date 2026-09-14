"""La central puede cerrar un dia a mano, y queda firmado

Un dia que se trabajo y que nadie marco no puede quedarse abierto para
siempre: mientras lo este, no entra a nomina y su servicio no se puede
cerrar para facturar. Alguien tiene que poder cerrarlo.

Pero cerrarlo a mano es decir "yo doy fe de que esto ocurrio asi" sin
que haya una marca desde la calle que lo respalde, y eso tiene que
verse. Por eso no se guarda solo la hora: se guarda quien lo cerro,
cuando lo cerro y por que. Un cierre a mano sin firma seria un dia
inventado que se ve igual que uno trabajado.

Revision ID: d72b90ae5c14
Revises: c61f28a94db7
"""
import sqlalchemy as sa
from alembic import op

revision = "d72b90ae5c14"
down_revision = "c61f28a94db7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jornada", sa.Column("cerrada_a_mano_por_id", sa.Integer(),
                                       nullable=True))
    op.add_column("jornada", sa.Column("cerrada_a_mano_en", sa.DateTime(),
                                       nullable=True))
    op.add_column("jornada", sa.Column("cierre_motivo", sa.Text(),
                                       nullable=True))
    op.create_foreign_key("fk_jornada_cerrada_a_mano_por", "jornada",
                          "persona", ["cerrada_a_mano_por_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_jornada_cerrada_a_mano_por", "jornada",
                       type_="foreignkey")
    op.drop_column("jornada", "cierre_motivo")
    op.drop_column("jornada", "cerrada_a_mano_en")
    op.drop_column("jornada", "cerrada_a_mano_por_id")

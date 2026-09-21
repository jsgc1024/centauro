"""El regreso cierra el movimiento, no abre otro

Marta se enferma el 10 y Luis la cubre. Marta se recupera y regresa el
25; Luis trabaja hasta el 24 por orden del consultor. Eso es un solo
hecho --"Luis cubrio a Marta del 10 al 24"-- y asi tiene que leerse en
el historial y en el corte del mes.

Si el regreso abriera su propio movimiento, el mismo mes mostraria dos
cambios cruzados y nadie sabria cual cierra a cual. En vez de eso el
regreso recorre el `hasta` del movimiento original y lo firma: quien lo
ordeno y cuando.

Revision ID: a4c9e1b70d28
Revises: e73f2c095a41
"""
import sqlalchemy as sa
from alembic import op

revision = "a4c9e1b70d28"
down_revision = "e73f2c095a41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reemplazo_recurso",
                  sa.Column("regreso_en", sa.DateTime(), nullable=True))
    op.add_column("reemplazo_recurso",
                  sa.Column("regreso_por_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_reemplazo_recurso_regreso_por",
                          "reemplazo_recurso", "persona",
                          ["regreso_por_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_reemplazo_recurso_regreso_por",
                       "reemplazo_recurso", type_="foreignkey")
    op.drop_column("reemplazo_recurso", "regreso_por_id")
    op.drop_column("reemplazo_recurso", "regreso_en")

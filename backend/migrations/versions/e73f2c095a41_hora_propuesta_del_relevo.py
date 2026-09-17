"""La hora que el sistema propuso para partir el dia

El dia que se parte se reparte por una hora, y esa hora decide cuanto
cobra cada uno y cuanto se le factura al cliente. Sale de la ultima
marca de quien salio, pero el consultor puede corregirla cuando sabe que
fue otra --un dia estatico puede no tener marcas desde la manana--.

Guardar la propuesta al lado deja ver cuando la corrigieron: si no
coincide con la que quedo en la asignacion, alguien la movio, y ese
alguien es el `hecho_por_id` del mismo movimiento.

Va vacia cuando el cambio no partio ningun dia.

Revision ID: e73f2c095a41
Revises: d61e8b47c095
"""
import sqlalchemy as sa
from alembic import op

revision = "e73f2c095a41"
down_revision = "d61e8b47c095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reemplazo_recurso",
                  sa.Column("hora_propuesta", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("reemplazo_recurso", "hora_propuesta")

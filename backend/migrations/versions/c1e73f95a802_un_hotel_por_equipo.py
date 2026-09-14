"""Un hotel por equipo

Revision ID: c1e73f95a802
Revises: b8d4f27a013c
Create Date: 2026-09-13

Cada equipo cuida a su ejecutivo principal y ese ejecutivo duerme en un
hotel. Poder cargar dos dejaba la duda de a cual de los dos llegar, que
es justo lo que la hoja tiene que resolver.

Lo que ya existe se queda como esta: las estancias viejas cuelgan del
servicio, sin equipo, y se siguen viendo en la hoja hasta que alguien
las vuelva a capturar. Solo se acomoda el caso claro: servicio de un
solo equipo con una sola estancia.
"""
import sqlalchemy as sa
from alembic import op

revision = "c1e73f95a802"
down_revision = "b8d4f27a013c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hospedaje", sa.Column("equipo_id", sa.Integer(),
                                         nullable=True))
    op.create_foreign_key("fk_hospedaje_equipo", "hospedaje", "equipo",
                          ["equipo_id"], ["id"], ondelete="CASCADE")

    # Servicio con un solo equipo y una sola estancia: no hay a que otro
    # equipo pudiera pertenecer.
    op.execute("""
        UPDATE hospedaje h SET equipo_id = (
            SELECT e.id FROM equipo e WHERE e.servicio_id = h.servicio_id
        )
        WHERE (SELECT count(*) FROM equipo e
               WHERE e.servicio_id = h.servicio_id) = 1
          AND (SELECT count(*) FROM hospedaje x
               WHERE x.servicio_id = h.servicio_id) = 1
    """)

    op.create_unique_constraint("uq_hospedaje_equipo", "hospedaje",
                                ["equipo_id"])


def downgrade():
    op.drop_constraint("uq_hospedaje_equipo", "hospedaje", type_="unique")
    op.drop_constraint("fk_hospedaje_equipo", "hospedaje", type_="foreignkey")
    op.drop_column("hospedaje", "equipo_id")

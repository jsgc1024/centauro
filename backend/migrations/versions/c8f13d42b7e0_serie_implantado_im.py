"""La serie del implantado se escribe EP/IM: EP/I-001 -> EP/IM-001

Revision ID: c8f13d42b7e0
Revises: b41e7c90d258
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "c8f13d42b7e0"
down_revision = "b41e7c90d258"
branch_labels = None
depends_on = None

CORTO = re.compile(r"^EP/I-(\d+)$")
LARGO = re.compile(r"^EP/IM-(\d+)$")


def upgrade() -> None:
    """Solo cambia la forma; el numero se queda donde esta.

    La migracion anterior alcanzo a correr con la serie escrita EP/I. En
    la base de desarrollo eso son a lo mucho un par de folios, pero el
    folio es lo que el cliente tiene escrito en algun lado, asi que se
    corrige en la base y no a mano.
    """
    conexion = op.get_bind()
    for tabla in ("servicio", "servicio_eliminado"):
        for fila_id, folio in conexion.execute(sa.text(
            f"SELECT id, folio FROM {tabla} ORDER BY id"
        )).fetchall():
            coincide = CORTO.match(folio or "")
            if not coincide:
                continue
            conexion.execute(
                sa.text(f"UPDATE {tabla} SET folio = :f WHERE id = :i"),
                {"f": f"EP/IM-{int(coincide.group(1)):03d}", "i": fila_id},
            )


def downgrade() -> None:
    conexion = op.get_bind()
    for tabla in ("servicio", "servicio_eliminado"):
        for fila_id, folio in conexion.execute(sa.text(
            f"SELECT id, folio FROM {tabla} ORDER BY id"
        )).fetchall():
            coincide = LARGO.match(folio or "")
            if not coincide:
                continue
            conexion.execute(
                sa.text(f"UPDATE {tabla} SET folio = :f WHERE id = :i"),
                {"f": f"EP/I-{int(coincide.group(1)):03d}", "i": fila_id},
            )

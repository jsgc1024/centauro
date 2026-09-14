"""Los folios viejos pasan a la serie por tipo: EP-0007 -> EP/E-007

Revision ID: b41e7c90d258
Revises: a3f60d8b4e17
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "b41e7c90d258"
down_revision = "a3f60d8b4e17"
branch_labels = None
depends_on = None

VIEJO = re.compile(r"^EP-(\d+)$")
NUEVO = re.compile(r"^EP/(E|IM)-(\d+)$")


def upgrade() -> None:
    """Reescribe la serie unica en dos series, una por tipo de servicio.

    El numero del eventual se conserva tal cual (EP-0007 -> EP/E-007) para
    no romper el rastro de lo que ya salio por correo; solo cambia la
    forma. Los implantados que alcanzaron a nacer con la serie vieja se
    renumeran desde 1 en su propia serie, que hasta hoy estaba vacia.

    servicio_eliminado no guarda el tipo. Todo lo eliminado hasta esta
    migracion es eventual —la pantalla de implantados no existia—, asi
    que se trata como tal.
    """
    conexion = op.get_bind()

    # Los implantados primero: necesitan numero propio, empezando en 1.
    # upper() porque el enum guarda el nombre del miembro, no su valor, y
    # una base vieja podria tener la minuscula.
    filas = conexion.execute(sa.text(
        "SELECT id, folio FROM servicio "
        "WHERE upper(tipo::text) = 'IMPLANTADO' ORDER BY id"
    )).fetchall()
    consecutivo = 0
    for servicio_id, folio in filas:
        if not folio or not VIEJO.match(folio):
            continue
        consecutivo += 1
        conexion.execute(
            sa.text("UPDATE servicio SET folio = :f WHERE id = :i"),
            {"f": f"EP/IM-{consecutivo:03d}", "i": servicio_id},
        )

    # Los eventuales conservan su numero.
    for tabla in ("servicio", "servicio_eliminado"):
        filas = conexion.execute(sa.text(
            f"SELECT id, folio FROM {tabla} ORDER BY id"
        )).fetchall()
        for fila_id, folio in filas:
            if not folio:
                continue
            coincide = VIEJO.match(folio)
            if not coincide:
                continue
            numero = int(coincide.group(1))
            conexion.execute(
                sa.text(f"UPDATE {tabla} SET folio = :f WHERE id = :i"),
                {"f": f"EP/E-{numero:03d}", "i": fila_id},
            )


def downgrade() -> None:
    """Vuelve a la serie unica. Los implantados se acomodan al final.

    No es un espejo exacto: el implantado no tenia lugar en la serie
    vieja, asi que se le da el numero que sigue del ultimo eventual.
    """
    conexion = op.get_bind()
    usado = set()

    for tabla in ("servicio", "servicio_eliminado"):
        for fila_id, folio in conexion.execute(sa.text(
            f"SELECT id, folio FROM {tabla} ORDER BY id"
        )).fetchall():
            coincide = NUEVO.match(folio or "")
            if not coincide or coincide.group(1) != "E":
                continue
            numero = int(coincide.group(2))
            usado.add(numero)
            conexion.execute(
                sa.text(f"UPDATE {tabla} SET folio = :f WHERE id = :i"),
                {"f": f"EP-{numero:04d}", "i": fila_id},
            )

    siguiente = max(usado, default=0)
    for servicio_id, folio in conexion.execute(sa.text(
        "SELECT id, folio FROM servicio ORDER BY id"
    )).fetchall():
        coincide = NUEVO.match(folio or "")
        if not coincide or coincide.group(1) != "IM":
            continue
        siguiente += 1
        conexion.execute(
            sa.text("UPDATE servicio SET folio = :f WHERE id = :i"),
            {"f": f"EP-{siguiente:04d}", "i": servicio_id},
        )

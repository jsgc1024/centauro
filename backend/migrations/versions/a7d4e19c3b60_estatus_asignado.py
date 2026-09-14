"""estatus asignado del servicio

Entre planeado y en curso: el servicio ya tiene personal y unidad en
todas sus jornadas, pero todavia no sale a la calle.

Revision ID: a7d4e19c3b60
Revises: e3b82d1a95c7
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a7d4e19c3b60"
down_revision: Union[str, None] = "e3b82d1a95c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Un valor nuevo en una lista existente se agrega a mano: Alembic no
    # lo deduce del modelo.
    op.execute("ALTER TYPE estatusservicio ADD VALUE IF NOT EXISTS "
               "'ASIGNADO' AFTER 'PLANEADO'")


def downgrade() -> None:
    # Postgres no sabe quitar un valor de una lista. Para revertir habria
    # que recrear el tipo completo; no vale la pena para un valor nuevo
    # que nadie mas usa.
    pass

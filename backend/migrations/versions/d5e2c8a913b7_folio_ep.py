"""el folio del servicio queda en EP-0001

Se quita el prefijo AI del folio: el servicio se identifica como EP-0025.
Los que ya estaban dados de alta se renombran para que no convivan dos
formas de escribir lo mismo.

Revision ID: d5e2c8a913b7
Revises: c4d91b7e2f08
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d5e2c8a913b7"
down_revision: Union[str, None] = "c4d91b7e2f08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE servicio SET folio = replace(folio, 'AI/EP-', 'EP-')")


def downgrade() -> None:
    op.execute("UPDATE servicio SET folio = replace(folio, 'EP-', 'AI/EP-')")

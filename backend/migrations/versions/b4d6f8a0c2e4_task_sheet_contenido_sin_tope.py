"""task_sheet.contenido sin tope (seccion 101)

La hoja congelada trae las fotos de la gente y de las unidades
incrustadas; con las fotos de 512 px que ahora manda Odoo una hoja pasa
de los 20,000 caracteres y publicarla contestaba "un texto es mas largo
de lo que cabe". Pasa a TEXT: mismo contenido, sin tope.

Revision ID: b4d6f8a0c2e4
Revises: a3b5c7d9e1f2
Create Date: 2026-09-29
"""
import sqlalchemy as sa
from alembic import op

revision = "b4d6f8a0c2e4"
down_revision = "a3b5c7d9e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("task_sheet", "contenido", type_=sa.Text(),
                    existing_type=sa.String(20000), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("task_sheet", "contenido", type_=sa.String(20000),
                    existing_type=sa.Text(), existing_nullable=False)

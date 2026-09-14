"""La hora de la jornada: confirmada o heredada

Revision ID: b7e04c31da95
Revises: a2d5c81f640b
Create Date: 2026-09-13

Solo el primer dia trae hora propia; los demas la heredan. Saber cual es
cual evita tratar un supuesto como si fuera un dato.
"""
import sqlalchemy as sa
from alembic import op

revision = "b7e04c31da95"
down_revision = "a2d5c81f640b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jornada", sa.Column(
        "hora_confirmada", sa.Boolean(), nullable=False,
        server_default="false"))
    # Lo que ya existe: el primer dia de cada equipo si traia hora propia
    # desde el alta; los demas la heredaron.
    op.execute("""
        UPDATE jornada SET hora_confirmada = true
        WHERE id IN (
            SELECT DISTINCT ON (equipo_id) id FROM jornada
            ORDER BY equipo_id, fecha
        )
    """)


def downgrade():
    op.drop_column("jornada", "hora_confirmada")

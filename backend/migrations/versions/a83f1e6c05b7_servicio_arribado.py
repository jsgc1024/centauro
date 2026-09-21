"""El servicio con el equipo ya parado en el punto.

La cartera decia "asignado" con la gente alla. Decision de Salvador, 20
sep. Lo enciende la llegada al punto y lo apaga el contacto con el
principal, igual que en la jornada.

Revision ID: a83f1e6c05b7
Revises: f2c90a15e7d4
"""
from alembic import op

revision = "a83f1e6c05b7"
down_revision = "f2c90a15e7d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE estatusservicio ADD VALUE IF NOT EXISTS 'ARRIBADO' "
               "BEFORE 'EN_CURSO'")


def downgrade() -> None:
    # Postgres no deja quitar un valor de un enum: los servicios vuelven
    # a `asignado`, que es de donde salieron, y el valor se queda en el
    # tipo sin nadie que lo use.
    op.execute("UPDATE servicio SET estatus = 'ASIGNADO' "
               "WHERE estatus = 'ARRIBADO'")

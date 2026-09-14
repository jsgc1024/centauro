"""El implantado nace solicitado, no en borrador

Revision ID: e59c2a137b04
Revises: d48a1b07c359
"""
from alembic import op

revision = "e59c2a137b04"
down_revision = "d48a1b07c359"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Un estatus mas para el servicio: solicitado.

    Con el cliente y el acuerdo capturados ya hay un compromiso
    esperando gente. "Borrador" decia que alguien estaba escribiendo;
    esto dice que el cliente ya pidio.

    El eventual no lo usa: sigue naciendo en borrador. Agregar un valor
    al tipo no cambia nada de lo que ya existe.
    """
    # IF NOT EXISTS porque una base que ya lo tenga no debe reventar.
    op.execute("ALTER TYPE estatusservicio ADD VALUE IF NOT EXISTS "
               "'SOLICITADO' AFTER 'BORRADOR'")


def downgrade() -> None:
    """Postgres no quita valores de un enum sin recrear el tipo entero, y
    recrearlo aqui se llevaria por delante las filas que lo usan."""

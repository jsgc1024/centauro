"""La coordinacion del servicio lleva apellido

Revision ID: d6a04e91b3c7
Revises: c8f13d42b7e0
"""
from alembic import op
import sqlalchemy as sa

revision = "d6a04e91b3c7"
down_revision = "c8f13d42b7e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nombre y apellido por separado, como en todo contacto del sistema.

    Un solo campo de nombre obliga a escribir "Lic. Marta Ruiz de la
    Vega" completo y despues nadie puede ordenar ni buscar por apellido.
    """
    op.add_column("acuerdo_implantado",
                  sa.Column("reporta_a_apellidos", sa.String(160),
                            nullable=True))


def downgrade() -> None:
    op.drop_column("acuerdo_implantado", "reporta_a_apellidos")

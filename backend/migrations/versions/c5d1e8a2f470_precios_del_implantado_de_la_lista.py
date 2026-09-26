"""Los precios del implantado, de su lista de implantados (seccion 80)

La marca de si los terminos del mes son los de la lista de implantados
del cliente: con ella, el mes que sigue los vuelve a tomar de la lista.

Revision ID: c5d1e8a2f470
Revises: b7e3a9c1d562
"""
import sqlalchemy as sa
from alembic import op

revision = "c5d1e8a2f470"
down_revision = "b7e3a9c1d562"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Los meses que ya existen se quedan con sus precios: los capturo
    # alguien a mano y nadie dijo que fueran los de la lista.
    op.add_column("contrato_implantado",
                  sa.Column("precios_de_la_lista", sa.Boolean(),
                            nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("contrato_implantado", "precios_de_la_lista")

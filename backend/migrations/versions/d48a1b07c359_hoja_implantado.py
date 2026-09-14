"""La hoja del implantado lleva version

Revision ID: d48a1b07c359
Revises: c3f91d68a204
"""
from alembic import op
import sqlalchemy as sa

revision = "d48a1b07c359"
down_revision = "c3f91d68a204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Cuantas veces se ha liberado la hoja y cuando fue la ultima.

    Vive en el acuerdo y no en el servicio porque la hoja del implantado
    es la del acuerdo: se vuelve a liberar cuando cambia el trato o el
    equipo de planta, no cuando se cubre un sabado.
    """
    op.add_column("acuerdo_implantado",
                  sa.Column("version_hoja", sa.Integer(), nullable=False,
                            server_default="0"))
    op.add_column("acuerdo_implantado",
                  sa.Column("hoja_en", sa.DateTime(timezone=True),
                            nullable=True))


def downgrade() -> None:
    op.drop_column("acuerdo_implantado", "hoja_en")
    op.drop_column("acuerdo_implantado", "version_hoja")

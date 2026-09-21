"""El codigo de cuatro digitos del personal de campo

El agente llama a su consultor --o a la central, que esta despierta a las
5:40-- y le dictan cuatro digitos. No va por correo: el correo del
personal de campo es personal y la empresa no lo controla.

Cuatro digitos son diez mil combinaciones, asi que el contador de fallos
vive aqui y no en Redis: `intentos.py` se abre si Redis no contesta --que
para el inicio de sesion es lo correcto-- y eso dejaria el codigo sin
candado justo el dia malo. A los cinco fallos se muere y hay que pedir
otro.

Revision ID: e1a742c9b366
Revises: d5b93f61c208
"""
import sqlalchemy as sa
from alembic import op

revision = "e1a742c9b366"
down_revision = "d5b93f61c208"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE tipoinvitacion ADD VALUE IF NOT EXISTS 'CODIGO_CAMPO'")
    op.add_column("invitacion",
                  sa.Column("fallos", sa.Integer(), nullable=True))
    op.execute("UPDATE invitacion SET fallos = 0 WHERE fallos IS NULL")
    op.alter_column("invitacion", "fallos", nullable=False,
                    server_default="0")


def downgrade() -> None:
    op.drop_column("invitacion", "fallos")
    # El valor del enum no se quita: Postgres no sabe quitar valores de
    # un tipo, y dejarlo no estorba.

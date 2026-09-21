"""El rol de Recursos Humanos

Autoriza el bono del mes y reparte los accesos. No deposita: autorizar
el bono y pagarlo son el unico control que tiene ese dinero, y juntos en
una mano el control es la buena fe.

Revision ID: d5e90c3f41a7
Revises: c8f3b17ae402
"""
from alembic import op

revision = "d5e90c3f41a7"
down_revision = "c8f3b17ae402"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # El valor se guarda con el NOMBRE del miembro, en mayusculas, que es
    # como SQLAlchemy escribe los enum de Postgres en este esquema.
    op.execute("ALTER TYPE rol ADD VALUE IF NOT EXISTS 'RECURSOS_HUMANOS'")


def downgrade() -> None:
    """Postgres no quita valores de un enum sin recrear el tipo entero, y
    recrearlo aqui se llevaria por delante las filas que lo usan."""

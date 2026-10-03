"""El lector avisa cuando Claude no contesta (seccion 141)

Que paso, lo que dijo Claude y desde cuando, para que la consola lo
muestre en vez de quedarse callada.

Revision ID: d2f4a6c8e0b1
Revises: c9d1e3f5a7b0
"""
import sqlalchemy as sa
from alembic import op

revision = "d2f4a6c8e0b1"
down_revision = "c9d1e3f5a7b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parametros_lector",
                  sa.Column("ia_falla", sa.String(20), nullable=True))
    op.add_column("parametros_lector",
                  sa.Column("ia_detalle", sa.String(300), nullable=True))
    op.add_column("parametros_lector",
                  sa.Column("ia_falla_en", sa.DateTime(timezone=True),
                            nullable=True))


def downgrade() -> None:
    op.drop_column("parametros_lector", "ia_falla_en")
    op.drop_column("parametros_lector", "ia_detalle")
    op.drop_column("parametros_lector", "ia_falla")

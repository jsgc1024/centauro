"""La agenda del dia, parada por parada

Revision ID: f6b21e9d40a7
Revises: e4a70d9c1b83
Create Date: 2026-09-13

La agenda cambia durante el dia: corregir una parada no debe obligar a
reescribir el dia entero.
"""
import sqlalchemy as sa
from alembic import op

revision = "f6b21e9d40a7"
down_revision = "e4a70d9c1b83"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "parada_agenda",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jornada_id", sa.Integer(), sa.ForeignKey("jornada.id"),
                  nullable=False, index=True),
        sa.Column("hora", sa.Time(), nullable=True),
        sa.Column("lugar", sa.String(200), nullable=False),
        sa.Column("direccion", sa.String(300), nullable=True),
        sa.Column("notas", sa.String(300), nullable=True),
        sa.Column("creada_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("parada_agenda")

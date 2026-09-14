"""El hospedaje sin fechas obligatorias

Revision ID: c5183ba7e9d0
Revises: b7e04c31da95
Create Date: 2026-09-13

Lo que se necesita del hotel es a donde llegar y a que numero llamar.
Las fechas repetian las del servicio; se quedan para la estancia que
cambia de hotel a media semana, pero ya no se piden.
"""
import sqlalchemy as sa
from alembic import op

revision = "c5183ba7e9d0"
down_revision = "b7e04c31da95"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("hospedaje", "desde", existing_type=sa.Date(),
                    nullable=True)
    op.alter_column("hospedaje", "hasta", existing_type=sa.Date(),
                    nullable=True)


def downgrade():
    op.execute("UPDATE hospedaje SET desde = CURRENT_DATE WHERE desde IS NULL")
    op.execute("UPDATE hospedaje SET hasta = CURRENT_DATE WHERE hasta IS NULL")
    op.alter_column("hospedaje", "hasta", existing_type=sa.Date(),
                    nullable=False)
    op.alter_column("hospedaje", "desde", existing_type=sa.Date(),
                    nullable=False)

"""El certificado recuerda cuando se aviso

La tarea corre diario y hay dos momentos que avisan --treinta dias antes
y el dia que vence--, asi que sin esto un mismo aviso sale cada vez que
la tarea se corre otra vez el mismo dia.

Revision ID: a6d81f39c204
Revises: f3a17c08b542
"""
import sqlalchemy as sa
from alembic import op

revision = "a6d81f39c204"
down_revision = "f3a17c08b542"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("capacitacion", sa.Column(
        "avisado_en", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("capacitacion", "avisado_en")

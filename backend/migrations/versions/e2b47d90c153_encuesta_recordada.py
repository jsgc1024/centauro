"""La encuesta recuerda si ya se recordo

Un solo recordatorio por encuesta. El campo es lo que impide que la
tarea diaria mande el mismo correo todos los dias.

Revision ID: e2b47d90c153
Revises: d5e90c3f41a7
"""
import sqlalchemy as sa
from alembic import op

revision = "e2b47d90c153"
down_revision = "d5e90c3f41a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("encuesta", sa.Column(
        "recordada_en", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("encuesta", "recordada_en")

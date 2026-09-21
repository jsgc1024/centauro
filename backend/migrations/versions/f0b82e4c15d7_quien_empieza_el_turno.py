"""Quien empieza el turno en 12x36

El consultor marca cual de las dos personas entra el primer dia, y de
ahi se alterna. Decision de Salvador (20 sep): el orden en que se
capturaron es un accidente, y de esto sale quien trabaja el dia 1 de
cada mes que se abra despues.

En los implantados de 12 horas naturales no aplica y queda en falso.

Revision ID: f0b82e4c15d7
Revises: e4c19d70b3a8
"""
import sqlalchemy as sa
from alembic import op

revision = "f0b82e4c15d7"
down_revision = "e4c19d70b3a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("persona_implantado",
                  sa.Column("empieza", sa.Boolean(), nullable=False,
                            server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("persona_implantado", "empieza")

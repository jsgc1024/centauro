"""El lugar de la parada lleva tambien su direccion

Revision ID: a2d5c81f640b
Revises: f6b21e9d40a7
Create Date: 2026-09-13

En la pantalla el lugar y la direccion se capturan juntos, como los
dicta el cliente: "Oficinas corporativas, Reforma 250 piso 12". Con 200
caracteres se quedaba corto.
"""
import sqlalchemy as sa
from alembic import op

revision = "a2d5c81f640b"
down_revision = "f6b21e9d40a7"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("parada_agenda", "lugar",
                    existing_type=sa.String(200), type_=sa.String(400),
                    existing_nullable=False)


def downgrade():
    op.alter_column("parada_agenda", "lugar",
                    existing_type=sa.String(400), type_=sa.String(200),
                    existing_nullable=False)

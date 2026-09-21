"""La ficha del aviso

Los avisos traen quien va, en que unidad y a que hora pegados dentro de
un parrafo. Un dato metido en un parrafo es un dato que hay que leer
entero para encontrar, y el correo se abre en el telefono a las seis de
la manana: lo que se busca es la placa.

Se guarda como JSON de texto --una lista de pares-- para no atar la
tabla a un tipo de Postgres por cuatro renglones.

Revision ID: c5e93b02fa71
Revises: b3f5a1c87d64
"""
import sqlalchemy as sa
from alembic import op

revision = "c5e93b02fa71"
down_revision = "b3f5a1c87d64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notificacion", sa.Column("datos", sa.Text(), nullable=True))
    op.add_column("notificacion",
                  sa.Column("plantilla", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("notificacion", "plantilla")
    op.drop_column("notificacion", "datos")

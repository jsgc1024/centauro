"""Ciudad por equipo y km tipicos por modalidad

Revision ID: d1c8b3e07f52
Revises: c9f402ba1d76
Create Date: 2026-09-13

Un proyecto mueve al ejecutivo de una ciudad a otra con un solo
servicio: la ciudad pasa a ser del equipo. Y el recorrido tipico del dia
vive en la modalidad: transfer 40 km, medio dia 80, dia completo 150.
"""
import sqlalchemy as sa
from alembic import op

revision = "d1c8b3e07f52"
down_revision = "c9f402ba1d76"
branch_labels = None
depends_on = None

KILOMETROS = {"FULL_DAY": 150, "MEDIO_DIA": 80, "TRANSFER": 40}


def upgrade():
    op.add_column("equipo", sa.Column("plaza_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_equipo_plaza", "equipo", "plaza",
                          ["plaza_id"], ["id"])
    op.add_column("modalidad",
                  sa.Column("km_estimados", sa.Integer(), nullable=True))
    for codigo, km in KILOMETROS.items():
        op.execute(f"UPDATE modalidad SET km_estimados = {km} "
                   f"WHERE codigo = '{codigo}'")


def downgrade():
    op.drop_column("modalidad", "km_estimados")
    op.drop_constraint("fk_equipo_plaza", "equipo", type_="foreignkey")
    op.drop_column("equipo", "plaza_id")

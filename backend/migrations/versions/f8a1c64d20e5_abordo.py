"""Quien va a bordo de que unidad

Revision ID: f8a1c64d20e5
Revises: e7c3a52f1d84
Create Date: 2026-09-12

Con una sola unidad no hace falta; con dos o mas, el consultor dice quien
aborda cual. Se borra sola si la unidad deja de estar asignada.
"""
import sqlalchemy as sa
from alembic import op

revision = "f8a1c64d20e5"
down_revision = "e7c3a52f1d84"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("asignacion_personal",
                  sa.Column("vehiculo_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_asignacion_personal_vehiculo",
                          "asignacion_personal", "vehiculo",
                          ["vehiculo_id"], ["id"], ondelete="SET NULL")


def downgrade():
    op.drop_constraint("fk_asignacion_personal_vehiculo",
                       "asignacion_personal", type_="foreignkey")
    op.drop_column("asignacion_personal", "vehiculo_id")

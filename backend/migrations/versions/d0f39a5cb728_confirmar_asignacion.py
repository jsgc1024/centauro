"""La firma del consultor sobre la asignacion

Revision ID: d0f39a5cb728
Revises: c5183ba7e9d0
Create Date: 2026-09-13

Que haya gente y unidad todos los dias no quiere decir que el consultor
haya terminado. Confirmar es su firma, y es lo que la central espera.
"""
import sqlalchemy as sa
from alembic import op

revision = "d0f39a5cb728"
down_revision = "c5183ba7e9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("servicio", sa.Column(
        "asignacion_confirmada_en", sa.DateTime(timezone=True), nullable=True))
    op.add_column("servicio", sa.Column(
        "asignacion_confirmada_por_id", sa.Integer(),
        sa.ForeignKey("persona.id"), nullable=True))


def downgrade():
    op.drop_column("servicio", "asignacion_confirmada_por_id")
    op.drop_column("servicio", "asignacion_confirmada_en")

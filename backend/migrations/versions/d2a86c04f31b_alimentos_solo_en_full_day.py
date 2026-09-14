"""Alimentos: 350 al dia y solo en full day

Revision ID: d2a86c04f31b
Revises: c1e73f95a802
Create Date: 2026-09-13

Alimentos queda parejo en los dos escenarios de full day. En medio dia y
en transfer no se cubre comida: la jornada no da para eso, y el renglon
en cero solo confundia al consultor.

Los escenarios que salen se desactivan en vez de borrarse: los viaticos
ya asignados con ese renglon siguen apuntando a lo que se les dijo.
"""
from alembic import op

revision = "d2a86c04f31b"
down_revision = "c1e73f95a802"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE tabulador_viatico SET monto = 350
        WHERE concepto = 'ALIMENTOS'
          AND escenario IN ('FULL_DAY_LOCAL', 'FULL_DAY_FORANEO')
    """)
    op.execute("""
        UPDATE tabulador_viatico SET activo = false
        WHERE concepto = 'ALIMENTOS'
          AND escenario IN ('MEDIO_DIA', 'TRANSFER')
    """)


def downgrade():
    op.execute("""
        UPDATE tabulador_viatico SET activo = true
        WHERE concepto = 'ALIMENTOS'
          AND escenario IN ('MEDIO_DIA', 'TRANSFER')
    """)
    op.execute("""
        UPDATE tabulador_viatico SET monto = 250
        WHERE concepto = 'ALIMENTOS' AND escenario = 'FULL_DAY_LOCAL'
    """)
    op.execute("""
        UPDATE tabulador_viatico SET monto = 450
        WHERE concepto = 'ALIMENTOS' AND escenario = 'FULL_DAY_FORANEO'
    """)

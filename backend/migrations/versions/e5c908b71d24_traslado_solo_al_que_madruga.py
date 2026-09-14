"""El traslado del personal: solo en full day y solo al que madruga

Revision ID: e5c908b71d24
Revises: d2a86c04f31b
Create Date: 2026-09-13

Sale de medio dia y de transfer, y en full day deja de ser automatico:
se cubre cuando la presentacion cae antes de las 6:30, que es cuando el
agente no tiene transporte publico con que llegar a la base y termina
pagandose un taxi de su bolsa. Mas tarde llega como llega cualquier dia.

La hora la mira el motor al calcular la propuesta, no el tabulador: el
tabulador dice cuanto, no cuando aplica. Aqui solo se apagan los dos
escenarios que ya no lo llevan nunca.
"""
from alembic import op

revision = "e5c908b71d24"
down_revision = "d2a86c04f31b"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE tabulador_viatico SET activo = false
        WHERE concepto = 'TRASLADO_PERSONAL'
          AND escenario IN ('MEDIO_DIA', 'TRANSFER')
    """)


def downgrade():
    op.execute("""
        UPDATE tabulador_viatico SET activo = true
        WHERE concepto = 'TRASLADO_PERSONAL'
          AND escenario IN ('MEDIO_DIA', 'TRANSFER')
    """)

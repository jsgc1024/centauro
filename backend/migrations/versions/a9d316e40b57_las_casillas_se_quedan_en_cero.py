"""Alimentos y traslado se quedan a la vista en medio dia y transfer

Revision ID: a9d316e40b57
Revises: f47b1a6cd903
Create Date: 2026-09-13

Hoy no se cubren, pero el renglon vale mas puesto en cero que borrado:
el dia que la direccion decida pagar algo ahi es cambiar el monto y no
volver a abrir la tabla, y mientras tanto el consultor ve que el cero es
una decision y no un tabulador a medio cargar.

Combustible y el estacionamiento del aeropuerto si aplican en medio dia
y en transfer, y siempre estuvieron: se calculan, no salen de aqui.
"""
from alembic import op

revision = "a9d316e40b57"
down_revision = "f47b1a6cd903"
branch_labels = None
depends_on = None

REGLA = """
    WHERE concepto IN ('ALIMENTOS', 'TRASLADO_PERSONAL')
      AND escenario IN ('MEDIO_DIA', 'TRANSFER')
"""


def upgrade():
    op.execute("UPDATE tabulador_viatico SET activo = true, monto = 0"
               + REGLA)


def downgrade():
    op.execute("UPDATE tabulador_viatico SET activo = false" + REGLA)

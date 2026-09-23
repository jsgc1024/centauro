"""El cierre, sesion 3: las pantallas y sus reglas.

Decisiones de Salvador, 23 de septiembre (seccion 59 de la bitacora):

* El gasto del implantado a precio alzado lleva su monto fijo del mes
  (`contrato_implantado.gastos_mes`).
* Si finanzas regresa un servicio, el consultor tiene 24 horas desde el
  regreso (`cierre.devuelto_en`) y lo "en plazo" de su primer visto
  bueno se queda (`cierre.visto_bueno_en`). Los cierres que ya se
  mandaron toman como primer visto bueno su envio.
* Si ya tenia factura, esa se anula (`cierre.factura_anulada`) y con el
  nuevo visto bueno sale otra.
* La bandeja de por facturar dice cuantas veces se intento y cuando
  (`cierre.factura_intentos`, `cierre.factura_intento_en`).

Revision ID: f2a9c4e71b36
Revises: e8c3a1f5d7b9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a9c4e71b36"
down_revision: Union[str, None] = "e8c3a1f5d7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contrato_implantado",
                  sa.Column("gastos_mes", sa.Numeric(12, 2), nullable=True))
    op.add_column("cierre",
                  sa.Column("factura_intentos", sa.Integer(),
                            server_default=sa.text("0"), nullable=False))
    op.add_column("cierre",
                  sa.Column("factura_intento_en", sa.DateTime(),
                            nullable=True))
    op.add_column("cierre",
                  sa.Column("factura_anulada", sa.String(length=60),
                            nullable=True))
    op.add_column("cierre",
                  sa.Column("visto_bueno_en", sa.DateTime(), nullable=True))
    op.add_column("cierre",
                  sa.Column("devuelto_en", sa.DateTime(), nullable=True))
    # Lo que ya se mando conserva su veredicto: su primer visto bueno es
    # el envio que ya tiene.
    op.execute("UPDATE cierre SET visto_bueno_en = enviado_en "
               "WHERE enviado_en IS NOT NULL")


def downgrade() -> None:
    op.drop_column("cierre", "devuelto_en")
    op.drop_column("cierre", "visto_bueno_en")
    op.drop_column("cierre", "factura_anulada")
    op.drop_column("cierre", "factura_intento_en")
    op.drop_column("cierre", "factura_intentos")
    op.drop_column("contrato_implantado", "gastos_mes")

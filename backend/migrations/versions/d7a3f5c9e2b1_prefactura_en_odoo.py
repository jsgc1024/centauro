"""La factura del eventual y del mes del implantado en Odoo, 2: la
prefactura (seccion 117)

Con el visto bueno --del servicio eventual o del mes del implantado--
Connect manda a Odoo una factura de cliente en borrador; el facturista la
confirma y la timbra alla. El cierre guarda cual es:

- `cierre.prefactura_odoo_id`, `prefactura_en`, `prefactura_total` y
  `prefactura_detalle` (lo que se mando, renglon por renglon).
- `cierre.prefactura_anulada_id`: la que se quedo viva en Odoo cuando
  finanzas regreso el servicio, hasta que el facturista la cancele.
- `cierre.prefactura_desde`: el primer intento. Lo que tuvo su visto bueno
  antes de la llave de la factura no lo tiene y no se manda solo.

Revision ID: d7a3f5c9e2b1
Revises: c5e2a9d7f1b3
"""
import sqlalchemy as sa
from alembic import op

revision = "d7a3f5c9e2b1"
down_revision = "c5e2a9d7f1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cierre", sa.Column("prefactura_odoo_id", sa.Integer(),
                                      nullable=True))
    op.add_column("cierre", sa.Column("prefactura_en", sa.DateTime(),
                                      nullable=True))
    op.add_column("cierre", sa.Column("prefactura_total",
                                      sa.Numeric(12, 2), nullable=True))
    op.add_column("cierre", sa.Column("prefactura_detalle", sa.Text(),
                                      nullable=True))
    op.add_column("cierre", sa.Column("prefactura_anulada_id", sa.Integer(),
                                      nullable=True))
    op.add_column("cierre", sa.Column("prefactura_desde", sa.DateTime(),
                                      nullable=True))


def downgrade() -> None:
    for columna in ("prefactura_desde", "prefactura_anulada_id",
                    "prefactura_detalle",
                    "prefactura_total", "prefactura_en",
                    "prefactura_odoo_id"):
        op.drop_column("cierre", columna)

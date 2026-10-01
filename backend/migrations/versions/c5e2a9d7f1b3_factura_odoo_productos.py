"""La factura del eventual en Odoo, 1: con que producto sale cada renglon
(seccion 116)

Salvador (1 oct): al dar el visto bueno, Connect manda a Odoo una
prefactura en borrador; el facturista la confirma y la timbra alla. En
una factura de Odoo cada renglon lleva el producto exacto
(product.product), y Connect guardaba solo su plantilla
(product.template): la lectura de los tarifarios ahora trae tambien su
variante y cuantas tiene. Y la hora extra sale con el producto de su rol:
cada tarifario guarda de que producto salio el precio de cada una.

- `producto_odoo.variante_odoo_id` y `producto_odoo.variantes`.
- `tarifa_recurso.producto_hora_extra_id` y
  `tarifario.producto_hora_extra_id`.

Revision ID: c5e2a9d7f1b3
Revises: b8e1d4f6a9c3
"""
import sqlalchemy as sa
from alembic import op

revision = "c5e2a9d7f1b3"
down_revision = "b8e1d4f6a9c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("producto_odoo", sa.Column("variante_odoo_id", sa.Integer(),
                                             nullable=True))
    op.add_column("producto_odoo", sa.Column("variantes", sa.Integer(),
                                             nullable=True))
    for tabla in ("tarifa_recurso", "tarifario"):
        op.add_column(tabla, sa.Column("producto_hora_extra_id", sa.Integer(),
                                       nullable=True))
        op.create_foreign_key(f"fk_{tabla}_producto_hora_extra", tabla,
                              "producto_odoo", ["producto_hora_extra_id"],
                              ["id"], ondelete="SET NULL")


def downgrade() -> None:
    for tabla in ("tarifario", "tarifa_recurso"):
        op.drop_constraint(f"fk_{tabla}_producto_hora_extra", tabla,
                           type_="foreignkey")
        op.drop_column(tabla, "producto_hora_extra_id")
    op.drop_column("producto_odoo", "variantes")
    op.drop_column("producto_odoo", "variante_odoo_id")

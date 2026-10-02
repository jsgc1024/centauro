"""El tarifario de Brasil desde Odoo (seccion 123)

Cada pais lee de Odoo su categoria de productos y sus listas. Lo de Brasil
trae dos cosas que Mexico no tenia:

- `producto_odoo.pais_id`: de que pais es cada producto, por su
  categoria en Odoo. La tabla de productos se ve por pais.
- El paquete por mes: el de Amazon Brasil se cobra al mes. Se guarda con
  la modalidad `implantado` de su pais, y su hora extra va con el:
  `tarifa_paquete.precio_hora_extra` y `producto_hora_extra_id`, como en
  el precio de un rol. La lista de Amazon Brasil no trae precio suelto
  del conductor, y sin esto su hora extra se perdia.
- `posicion_propuesta.lista_precio_mes`: el mensual de la lista tal cual,
  para que la propuesta lo diga sin redondeos (16,855.00, no 22 veces
  766.14).

Revision ID: e4b8c2a6d9f1
Revises: 846d45af40d2
"""
import sqlalchemy as sa
from alembic import op

revision = "e4b8c2a6d9f1"
down_revision = "846d45af40d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("producto_odoo", sa.Column("pais_id", sa.Integer(), nullable=True))
    op.create_foreign_key("producto_odoo_pais_id_fkey", "producto_odoo", "pais",
                          ["pais_id"], ["id"])
    op.add_column("tarifa_paquete", sa.Column("precio_hora_extra",
                                              sa.Numeric(12, 2), nullable=True))
    op.add_column("tarifa_paquete", sa.Column("producto_hora_extra_id",
                                              sa.Integer(), nullable=True))
    op.create_foreign_key("tarifa_paquete_producto_hora_extra_id_fkey",
                          "tarifa_paquete", "producto_odoo",
                          ["producto_hora_extra_id"], ["id"], ondelete="SET NULL")
    op.add_column("posicion_propuesta", sa.Column("lista_precio_mes",
                                                  sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("posicion_propuesta", "lista_precio_mes")
    op.drop_constraint("tarifa_paquete_producto_hora_extra_id_fkey",
                       "tarifa_paquete", type_="foreignkey")
    op.drop_column("tarifa_paquete", "producto_hora_extra_id")
    op.drop_column("tarifa_paquete", "precio_hora_extra")
    op.drop_constraint("producto_odoo_pais_id_fkey", "producto_odoo",
                       type_="foreignkey")
    op.drop_column("producto_odoo", "pais_id")

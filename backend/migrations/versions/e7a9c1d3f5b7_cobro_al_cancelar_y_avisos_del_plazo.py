"""El cobro al cancelar y los avisos del plazo del cierre (seccion 105)

Decision 1 de Salvador (29 sep): al cancelar con el equipo en la calle
el consultor elige si al cliente se le cobra la cotizacion completa o lo
ejecutado, y direccion de operaciones lo autoriza desde la tarjeta del
cierre. El cierre guarda esa eleccion (`cobro`), quien la autorizo y
cuando; sin la autorizacion no se manda a finanzas. Vacio en los cierres
por termino y en las cancelaciones anteriores, que siguen cobrando lo
ejecutado.

Decision 12: al vencer cada plazo del cierre se avisa por correo y
telefono al consultor y a direccion de operaciones, y a la mitad al
consultor. `aviso_mitad_en` y `aviso_vencido_en` son la memoria de que
ya se aviso, para no repetirlo en cada vuelta del reloj.

Revision ID: e7a9c1d3f5b7
Revises: d6f8b0c2e4a6
Create Date: 2026-09-29
"""
import sqlalchemy as sa
from alembic import op

revision = "e7a9c1d3f5b7"
down_revision = "d6f8b0c2e4a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cierre", sa.Column("cobro", sa.String(12), nullable=True))
    op.add_column("cierre", sa.Column("cobro_autorizado_en", sa.DateTime(),
                                      nullable=True))
    op.add_column("cierre", sa.Column("cobro_autorizado_por_id", sa.Integer(),
                                      nullable=True))
    op.create_foreign_key("fk_cierre_cobro_autorizado_por", "cierre",
                          "persona", ["cobro_autorizado_por_id"], ["id"])
    op.add_column("cierre", sa.Column("aviso_mitad_en", sa.DateTime(),
                                      nullable=True))
    op.add_column("cierre", sa.Column("aviso_vencido_en", sa.DateTime(),
                                      nullable=True))


def downgrade() -> None:
    op.drop_column("cierre", "aviso_vencido_en")
    op.drop_column("cierre", "aviso_mitad_en")
    op.drop_constraint("fk_cierre_cobro_autorizado_por", "cierre",
                       type_="foreignkey")
    op.drop_column("cierre", "cobro_autorizado_por_id")
    op.drop_column("cierre", "cobro_autorizado_en")
    op.drop_column("cierre", "cobro")

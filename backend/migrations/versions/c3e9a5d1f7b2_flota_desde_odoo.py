"""La flota y el taller, leidos de Odoo.

Etapa 2 de la conexion con Odoo (seccion 52 de la bitacora): la unidad
guarda con que numero vive en Odoo, cuando se leyo y cuando Odoo la dio de
baja; las fotos representativas de cada categoria, una por color; un tipo
de alerta nuevo para la central; y la categoria Sedan, que Odoo ya tenia y
Centauro no.

Revision ID: c3e9a5d1f7b2
Revises: b7d2f4a9c1e3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3e9a5d1f7b2"
down_revision: Union[str, None] = "b7d2f4a9c1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vehiculo", sa.Column("odoo_id", sa.Integer(), nullable=True))
    op.create_unique_constraint("vehiculo_odoo_id_key", "vehiculo", ["odoo_id"])
    op.add_column("vehiculo", sa.Column("odoo_sincronizado_en", sa.DateTime(),
                                        nullable=True))
    op.add_column("vehiculo", sa.Column("baja_odoo_en", sa.DateTime(),
                                        nullable=True))
    op.create_table(
        "foto_categoria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("categoria_id", sa.Integer(),
                  sa.ForeignKey("categoria_vehiculo.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("color", sa.String(length=40), server_default="",
                  nullable=False),
        sa.Column("foto_url", sa.Text(), nullable=False),
        sa.Column("cargada_en", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("categoria_id", "color"),
    )
    op.create_index("ix_foto_categoria_categoria_id", "foto_categoria",
                    ["categoria_id"])
    op.execute("ALTER TYPE tipoalerta ADD VALUE IF NOT EXISTS "
               "'UNIDAD_DE_BAJA' AFTER 'PERSONAL_DE_BAJA'")
    # El Sedan ya estaba en Odoo y faltaba aqui. Solo la categoria: sus
    # tarifas se cargan con el tarifario real.
    op.execute("INSERT INTO categoria_vehiculo "
               "(codigo, nombre, blindado, rendimiento_km_litro, activo) "
               "SELECT 'sedan', 'Sedán', false, 15.0, true "
               "WHERE NOT EXISTS (SELECT 1 FROM categoria_vehiculo "
               "WHERE codigo = 'sedan')")


def downgrade() -> None:
    op.execute("DELETE FROM alerta WHERE tipo = 'UNIDAD_DE_BAJA'")
    op.drop_index("ix_foto_categoria_categoria_id", table_name="foto_categoria")
    op.drop_table("foto_categoria")
    op.drop_column("vehiculo", "baja_odoo_en")
    op.drop_column("vehiculo", "odoo_sincronizado_en")
    op.drop_constraint("vehiculo_odoo_id_key", "vehiculo", type_="unique")
    op.drop_column("vehiculo", "odoo_id")
    # La categoria Sedan se queda: puede tener unidades y tarifas.

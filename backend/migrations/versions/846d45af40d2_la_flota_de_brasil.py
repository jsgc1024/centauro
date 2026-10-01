"""La flota de Brasil desde Odoo (seccion 118)

En Odoo cada pais es una compania y su flota trae su etiqueta: Mexico,
CENTAURO ASS con «PROTECCION EJECUTIVA»; Brasil, Centauro Brasil con
«PROTECCION EJECUTIVA BRASIL». Las unidades de Brasil llegan sin VIN,
color ni Ubicacion --se capturan despues-- y entran igual:

- `vehiculo.pais_id`: de que flota es la unidad. Se llena con el pais de
  su ciudad para las que ya estan.
- `vehiculo.plaza_id` deja de ser obligatoria: la unidad de Brasil vive
  sin ciudad hasta que Odoo le ponga Ubicacion. Nunca sin las dos.
- La categoria «CUV Blindada», que Brasil usa y Centauro no tenia. Solo la
  categoria: sus tarifas se cargan con el tarifario real.

Revision ID: 846d45af40d2
Revises: d7a3f5c9e2b1
"""
import sqlalchemy as sa
from alembic import op

revision = "846d45af40d2"
down_revision = "d7a3f5c9e2b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehiculo", sa.Column("pais_id", sa.Integer(), nullable=True))
    op.create_foreign_key("vehiculo_pais_id_fkey", "vehiculo", "pais",
                          ["pais_id"], ["id"])
    op.execute("UPDATE vehiculo SET pais_id = plaza.pais_id FROM plaza "
               "WHERE vehiculo.plaza_id = plaza.id "
               "AND vehiculo.pais_id IS NULL")
    op.alter_column("vehiculo", "plaza_id", existing_type=sa.Integer(),
                    nullable=True)
    op.create_check_constraint("ck_vehiculo_con_pais", "vehiculo",
                               "plaza_id IS NOT NULL OR pais_id IS NOT NULL")
    op.execute("INSERT INTO categoria_vehiculo "
               "(codigo, nombre, blindado, rendimiento_km_litro, activo) "
               "SELECT 'cuv_blindada', 'CUV Blindada', true, 9.0, true "
               "WHERE NOT EXISTS (SELECT 1 FROM categoria_vehiculo "
               "WHERE codigo = 'cuv_blindada')")


def downgrade() -> None:
    # Si ya hay unidades de Brasil sin ciudad, volver a exigirla falla a
    # proposito: para bajar no se borra ninguna unidad. Primero se les
    # pone su ciudad en Odoo y se deja leer.
    op.drop_constraint("ck_vehiculo_con_pais", "vehiculo", type_="check")
    op.alter_column("vehiculo", "plaza_id", existing_type=sa.Integer(),
                    nullable=False)
    op.drop_constraint("vehiculo_pais_id_fkey", "vehiculo", type_="foreignkey")
    op.drop_column("vehiculo", "pais_id")
    # La categoria CUV Blindada se queda: puede tener unidades y tarifas.

"""Los tarifarios, leidos de Odoo (seccion 77)

Salvador, 26 de septiembre: los tarifarios viven en Odoo y Centauro los
lee de ahi --una lista general por pais y, cuando el cliente negocio la
suya, la del cliente--. Aprobo las cinco recomendaciones de la propuesta.

Todo nace vacio: los tarifarios que ya existen se quedan como estan
hasta que la primera lectura de Odoo, hecha a mano, los reemplace.

Revision ID: f4a8c2d6b913
Revises: d8e2f6a4b1c3
"""
import sqlalchemy as sa
from alembic import op

revision = "f4a8c2d6b913"
down_revision = "d8e2f6a4b1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "producto_odoo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("odoo_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("unidad", sa.String(60), nullable=True),
        sa.Column("tipo_odoo", sa.String(20), nullable=True),
        sa.Column("precio_venta", sa.Numeric(12, 2), nullable=True),
        sa.Column("vendible", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("clase", sa.String(20), nullable=True),
        sa.Column("perfil_id", sa.Integer(),
                  sa.ForeignKey("perfil_personal.id"), nullable=True),
        sa.Column("categoria_id", sa.Integer(),
                  sa.ForeignKey("categoria_vehiculo.id"), nullable=True),
        sa.Column("modalidad", sa.String(20), nullable=True),
        sa.Column("confirmado", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("preferido", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("confirmado_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id"), nullable=True),
        sa.Column("confirmado_en", sa.DateTime(), nullable=True),
        sa.Column("odoo_sincronizado_en", sa.DateTime(), nullable=True),
    )

    op.add_column("tarifario", sa.Column("odoo_id", sa.Integer(),
                                         nullable=True))
    op.create_unique_constraint("uq_tarifario_odoo_id", "tarifario",
                                ["odoo_id"])
    op.add_column("tarifario", sa.Column("odoo_sincronizado_en",
                                         sa.DateTime(), nullable=True))
    op.add_column("tarifario", sa.Column("general", sa.Boolean(),
                                         nullable=False,
                                         server_default=sa.false()))
    op.add_column("tarifario", sa.Column("resto_de", sa.String(160),
                                         nullable=True))
    op.add_column("tarifario", sa.Column("precio_hora_extra",
                                         sa.Numeric(12, 2), nullable=True))

    for tabla in ("tarifa_recurso", "tarifa_vehiculo"):
        op.add_column(tabla, sa.Column("origen", sa.String(20),
                                       nullable=True))
        op.add_column(tabla, sa.Column(
            "producto_odoo_id", sa.Integer(),
            sa.ForeignKey("producto_odoo.id"), nullable=True))

    op.create_table(
        "tarifa_paquete",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tarifario_id", sa.Integer(),
                  sa.ForeignKey("tarifario.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("perfil_id", sa.Integer(),
                  sa.ForeignKey("perfil_personal.id"), nullable=False),
        sa.Column("categoria_id", sa.Integer(),
                  sa.ForeignKey("categoria_vehiculo.id"), nullable=False),
        sa.Column("modalidad_id", sa.Integer(),
                  sa.ForeignKey("modalidad.id"), nullable=False),
        sa.Column("precio", sa.Numeric(12, 2), nullable=False),
        sa.Column("origen", sa.String(20), nullable=True),
        sa.Column("producto_odoo_id", sa.Integer(),
                  sa.ForeignKey("producto_odoo.id"), nullable=True),
        sa.UniqueConstraint("tarifario_id", "perfil_id", "categoria_id",
                            "modalidad_id"),
    )

    op.add_column("cliente", sa.Column(
        "tarifario_implantado_id", sa.Integer(),
        sa.ForeignKey("tarifario.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("cliente", "tarifario_implantado_id")
    op.drop_table("tarifa_paquete")
    for tabla in ("tarifa_vehiculo", "tarifa_recurso"):
        op.drop_column(tabla, "producto_odoo_id")
        op.drop_column(tabla, "origen")
    for columna in ("precio_hora_extra", "resto_de", "general",
                    "odoo_sincronizado_en"):
        op.drop_column("tarifario", columna)
    op.drop_constraint("uq_tarifario_odoo_id", "tarifario", type_="unique")
    op.drop_column("tarifario", "odoo_id")
    op.drop_table("producto_odoo")

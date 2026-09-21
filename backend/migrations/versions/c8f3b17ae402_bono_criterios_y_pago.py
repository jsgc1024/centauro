"""Criterios nuevos del bono, tolerancia, lo pidio el cliente y el pago del mes

Revision ID: c8f3b17ae402
Revises: a4b71c92e5d8
"""
import sqlalchemy as sa
from alembic import op

revision = "c8f3b17ae402"
down_revision = "a4b71c92e5d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dos criterios mas. Agregar un valor al tipo no toca lo que ya
    # existe; IF NOT EXISTS porque una base que ya los tenga no revienta.
    op.execute("ALTER TYPE codigocriterio ADD VALUE IF NOT EXISTS "
               "'ENTREGA_UNIDAD'")
    op.execute("ALTER TYPE codigocriterio ADD VALUE IF NOT EXISTS "
               "'RECOMPRA'")

    # El margen del criterio: tantos minutos, tantas veces al mes. En
    # cero se porta como hasta hoy, asi que las filas viejas no cambian.
    op.add_column("criterio_estrella", sa.Column(
        "tolerancia_minutos", sa.Integer(), nullable=False,
        server_default="0"))
    op.add_column("criterio_estrella", sa.Column(
        "tolerancia_ocasiones", sa.Integer(), nullable=False,
        server_default="0"))
    # Si su monto se reparte cuando el criterio no aplica. Los que ya
    # existen si reparten, que es como se han portado siempre.
    op.add_column("criterio_estrella", sa.Column(
        "reparte", sa.Boolean(), nullable=False, server_default="true"))

    # Lo marca el consultor al armar el equipo.
    op.add_column("asignacion_personal", sa.Column(
        "pedido_por_cliente", sa.Boolean(), nullable=False,
        server_default="false"))

    # Cuando se dio el visto bueno de la incidencia.
    op.add_column("incidencia", sa.Column(
        "visto_bueno_en", sa.DateTime(timezone=True), nullable=True))

    # Quien y cuando autorizo el bono.
    op.add_column("evaluacion_mensual", sa.Column(
        "autorizada_en", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evaluacion_mensual", sa.Column(
        "autorizada_por_id", sa.Integer(), nullable=True))
    op.create_foreign_key("evaluacion_mensual_autorizada_por_id_fkey",
                          "evaluacion_mensual", "persona",
                          ["autorizada_por_id"], ["id"])

    # El deposito del bono. La llave unica sobre la evaluacion es el
    # candado del doble pago.
    op.create_table(
        "pago_bono",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evaluacion_id", sa.Integer(), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("moneda", sa.Enum("MXN", "BRL", "USD", "VES",
                                   name="moneda"), nullable=False),
        sa.Column("referencia", sa.String(120), nullable=False),
        sa.Column("comprobante", sa.Text(), nullable=True),
        sa.Column("pagado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("pagado_por_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["evaluacion_id"], ["evaluacion_mensual.id"]),
        sa.ForeignKeyConstraint(["pagado_por_id"], ["persona.id"]),
    )
    op.create_index("ix_pago_bono_evaluacion_id", "pago_bono",
                    ["evaluacion_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_pago_bono_evaluacion_id", table_name="pago_bono")
    op.drop_table("pago_bono")
    op.drop_constraint("evaluacion_mensual_autorizada_por_id_fkey",
                       "evaluacion_mensual", type_="foreignkey")
    op.drop_column("evaluacion_mensual", "autorizada_por_id")
    op.drop_column("evaluacion_mensual", "autorizada_en")
    op.drop_column("incidencia", "visto_bueno_en")
    op.drop_column("asignacion_personal", "pedido_por_cliente")
    op.drop_column("criterio_estrella", "reparte")
    op.drop_column("criterio_estrella", "tolerancia_ocasiones")
    op.drop_column("criterio_estrella", "tolerancia_minutos")
    # Postgres no quita valores de un enum sin recrear el tipo entero, y
    # recrearlo aqui se llevaria por delante las filas que lo usan.

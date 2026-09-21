"""La devolucion del dinero que sobro.

Existia un endpoint que sumaba al devuelto y nada mas: sin evidencia,
sin quien lo registro, y con el monto viajando en la direccion. Ahora la
devolucion es una transferencia al reves --la persona transfiere y manda
su comprobante, finanzas confirma cuando la ve entrar-- y declarada no
es confirmada, por la misma razon por la que autorizado no es
depositado.

Revision ID: e5b71c04da38
Revises: d1f8a3c60b92
"""
from alembic import op
import sqlalchemy as sa

revision = "e5b71c04da38"
down_revision = "d1f8a3c60b92"
branch_labels = None
depends_on = None

ESTATUS = sa.Enum("DECLARADA", "CONFIRMADA", "RECHAZADA",
                  name="estatusdevolucion")


def upgrade() -> None:
    ESTATUS.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "devolucion_viatico",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asignacion_id", sa.Integer(), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("moneda",
                  sa.Enum(name="moneda", create_type=False), nullable=False),
        sa.Column("referencia", sa.String(length=120), nullable=True),
        sa.Column("comprobante", sa.Text(), nullable=True),
        sa.Column("estatus", ESTATUS, nullable=False,
                  server_default="DECLARADA"),
        sa.Column("declarada_por_id", sa.Integer(), nullable=True),
        sa.Column("declarada_en", sa.DateTime(), nullable=True),
        sa.Column("confirmada_por_id", sa.Integer(), nullable=True),
        sa.Column("confirmada_en", sa.DateTime(), nullable=True),
        sa.Column("motivo_rechazo", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(["asignacion_id"], ["asignacion_viatico.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["declarada_por_id"], ["persona.id"]),
        sa.ForeignKeyConstraint(["confirmada_por_id"], ["persona.id"]),
    )
    op.create_index("ix_devolucion_viatico_asignacion_id",
                    "devolucion_viatico", ["asignacion_id"])


def downgrade() -> None:
    op.drop_index("ix_devolucion_viatico_asignacion_id",
                  table_name="devolucion_viatico")
    op.drop_table("devolucion_viatico")
    ESTATUS.drop(op.get_bind(), checkfirst=True)

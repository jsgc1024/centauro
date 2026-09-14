"""Las compras especiales: lo que no se deposita, se compra

Revision ID: b8d4f27a013c
Revises: a4c9e2f61b80
Create Date: 2026-09-13

Un boleto de avion o un hotel no se le dan en efectivo a nadie. El
consultor escribe lo que hace falta, finanzas lo busca, lo compra o lo
reserva y contesta con el numero de reserva o la imagen de la compra.

Va por equipo y no por persona: el vuelo o el hotel se gestionan para
todo el equipo de una vez, no agente por agente.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b8d4f27a013c"
down_revision = "a4c9e2f61b80"
branch_labels = None
depends_on = None

TIPOS = ("vuelo", "hospedaje", "transporte", "otro")
ESTATUS = ("solicitada", "en_gestion", "confirmada", "rechazada", "cancelada")


def upgrade():
    tipo = sa.Enum(*TIPOS, name="tipocompra")
    estatus = sa.Enum(*ESTATUS, name="estatuscompra")
    tipo.create(op.get_bind(), checkfirst=True)
    estatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "compra_especial",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("tipo", tipo, nullable=False),
        sa.Column("solicitud", sa.Text(), nullable=False),
        sa.Column("monto_estimado", sa.Numeric(12, 2), nullable=True),
        # El tipo moneda ya existe en la base: se nombra, no se recrea.
        sa.Column("moneda", postgresql.ENUM(name="moneda", create_type=False),
                  nullable=False),
        sa.Column("estatus", estatus, nullable=False,
                  server_default="solicitada"),
        sa.Column("solicitada_por_id", sa.Integer(), nullable=True),
        sa.Column("solicitada_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("confirmacion", sa.String(length=200), nullable=True),
        # La imagen viaja dentro del registro, como la senal: el equipo la
        # abre desde un aeropuerto y un enlace caido lo deja sin nada que
        # ensenar en el mostrador.
        sa.Column("comprobante", sa.Text(), nullable=True),
        sa.Column("monto_real", sa.Numeric(12, 2), nullable=True),
        sa.Column("respuesta", sa.Text(), nullable=True),
        sa.Column("atendida_por_id", sa.Integer(), nullable=True),
        sa.Column("atendida_en", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipo.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["solicitada_por_id"], ["persona.id"]),
        sa.ForeignKeyConstraint(["atendida_por_id"], ["persona.id"]),
    )
    op.create_index("ix_compra_especial_equipo", "compra_especial",
                    ["equipo_id"])


def downgrade():
    op.drop_index("ix_compra_especial_equipo", table_name="compra_especial")
    op.drop_table("compra_especial")
    sa.Enum(name="estatuscompra").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tipocompra").drop(op.get_bind(), checkfirst=True)

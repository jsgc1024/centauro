"""Cada implantado trae su propio tabulador de viaticos

Revision ID: a71d95c2e480
Revises: e59c2a137b04
"""
from alembic import op
import sqlalchemy as sa


revision = "a71d95c2e480"
down_revision = "e59c2a137b04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """El tabulador del implantado vive en el acuerdo, no en el pais.

    El de la empresa sirve para el eventual, que es un dia suelto con las
    mismas reglas para todos. El implantado se negocia cliente por
    cliente —lo que se le da de comer al equipo, si se le paga el
    traslado, que pasa con la gasolina— y ese trato queda escrito en el
    acuerdo. Meterlo en la tabla del pais obligaba a que un solo numero
    valiera para dos clientes que acordaron cosas distintas.

    El de la empresa se queda donde esta y el eventual no se entera.
    """
    op.create_table(
        "tabulador_implantado",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("servicio_id", sa.Integer(), nullable=False),
        sa.Column("concepto",
                  sa.Enum("ALIMENTOS", "HOSPEDAJE", "COMBUSTIBLE", "CASETAS",
                          "TRASLADO_PERSONAL", "OTROS",
                          name="conceptoviatico", create_type=False),
                  nullable=False),
        # Lo que se le da por dia y por persona. Por dia porque asi se
        # comprueba y asi se reparte cuando el consultor fija el mes.
        sa.Column("monto", sa.Numeric(12, 2), nullable=False,
                  server_default="0"),
        # El concepto que existe pero no tiene numero fijo: el consultor
        # captura descripcion y monto cuando toca.
        sa.Column("monto_abierto", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("nota", sa.String(300), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["servicio_id"], ["servicio.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("servicio_id", "concepto"),
    )
    op.create_index("ix_tabulador_implantado_servicio_id",
                    "tabulador_implantado", ["servicio_id"])


def downgrade() -> None:
    op.drop_index("ix_tabulador_implantado_servicio_id",
                  table_name="tabulador_implantado")
    op.drop_table("tabulador_implantado")

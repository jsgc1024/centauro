"""La unidad en el taller deja de ofrecerse

Revision ID: c3f91d68a204
Revises: b2e47a05c918
"""
from alembic import op
import sqlalchemy as sa

revision = "c3f91d68a204"
down_revision = "b2e47a05c918"
branch_labels = None
depends_on = None

# El tipo ya existe: es el mismo con que se explica un cambio de recurso.
MOTIVO = sa.Enum(name="motivocambio", create_type=False)


def upgrade() -> None:
    """Donde se guarda lo que Odoo dice del taller.

    El mantenimiento de la flota vive en Odoo; de este lado solo hace
    falta saber en que rango cada unidad esta fuera, para dejar de
    ofrecerla. Sin esto un coche desarmado le aparece libre a cualquier
    servicio.
    """
    op.create_table(
        "taller_vehiculo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehiculo_id", sa.Integer(), nullable=False),
        sa.Column("desde", sa.Date(), nullable=False),
        # Vacio: sigue adentro. El correctivo casi nunca trae fecha de
        # salida, y ponerle una inventada es peor que no tenerla.
        sa.Column("hasta", sa.Date(), nullable=True),
        sa.Column("tipo", MOTIVO, nullable=True),
        sa.Column("taller", sa.String(160), nullable=True),
        sa.Column("folio", sa.String(60), nullable=True),
        sa.Column("nota", sa.String(300), nullable=True),
        sa.Column("odoo_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("recibido_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["vehiculo_id"], ["vehiculo.id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_taller_vehiculo_unidad", "taller_vehiculo",
                    ["vehiculo_id"])


def downgrade() -> None:
    op.drop_index("ix_taller_vehiculo_unidad", table_name="taller_vehiculo")
    op.drop_table("taller_vehiculo")

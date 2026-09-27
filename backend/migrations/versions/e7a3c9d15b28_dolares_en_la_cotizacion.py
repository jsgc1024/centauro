"""Dolares en la cotizacion (seccion 82)

El tipo de cambio que pone finanzas a mano, con su historia; de cuando
es el de la cotizacion; el de los gastos del cierre; la moneda del mes
del implantado con su tipo de cambio; y de que moneda venia lo facturado
de una comision.

Revision ID: e7a3c9d15b28
Revises: c5d1e8a2f470
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e7a3c9d15b28"
down_revision = "c5d1e8a2f470"
branch_labels = None
depends_on = None


def _moneda():
    return postgresql.ENUM(name="moneda", create_type=False)


def upgrade() -> None:
    op.create_table(
        "tipo_cambio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("moneda", _moneda(), nullable=False),
        sa.Column("moneda_local", _moneda(), nullable=False),
        sa.Column("tasa", sa.Numeric(10, 4), nullable=False),
        sa.Column("puesto_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("puesto_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id"), nullable=True),
    )
    op.create_index("ix_tipo_cambio_par", "tipo_cambio",
                    ["moneda", "moneda_local", "puesto_en"])

    op.add_column("cotizacion", sa.Column("tipo_cambio_fecha", sa.Date(),
                                          nullable=True))
    op.add_column("cierre", sa.Column("tipo_cambio_gastos",
                                      sa.Numeric(10, 4), nullable=True))
    op.add_column("cierre", sa.Column("tipo_cambio_gastos_fecha", sa.Date(),
                                      nullable=True))
    op.add_column("contrato_implantado", sa.Column("moneda", _moneda(),
                                                   nullable=True))
    op.add_column("contrato_implantado", sa.Column("tipo_cambio",
                                                   sa.Numeric(10, 4),
                                                   nullable=True))
    op.add_column("contrato_implantado", sa.Column("tipo_cambio_fecha",
                                                   sa.Date(), nullable=True))
    op.add_column("comision_consultor", sa.Column("moneda_facturada",
                                                  _moneda(), nullable=True))
    op.add_column("comision_consultor", sa.Column("facturado_en_moneda",
                                                  sa.Numeric(12, 2),
                                                  nullable=True))
    op.add_column("comision_consultor", sa.Column("servicio_en_moneda",
                                                  sa.Numeric(12, 2),
                                                  nullable=True))
    op.add_column("comision_consultor", sa.Column("tipo_cambio",
                                                  sa.Numeric(10, 4),
                                                  nullable=True))


def downgrade() -> None:
    op.drop_column("comision_consultor", "tipo_cambio")
    op.drop_column("comision_consultor", "servicio_en_moneda")
    op.drop_column("comision_consultor", "facturado_en_moneda")
    op.drop_column("comision_consultor", "moneda_facturada")
    op.drop_column("contrato_implantado", "tipo_cambio_fecha")
    op.drop_column("contrato_implantado", "tipo_cambio")
    op.drop_column("contrato_implantado", "moneda")
    op.drop_column("cierre", "tipo_cambio_gastos_fecha")
    op.drop_column("cierre", "tipo_cambio_gastos")
    op.drop_column("cotizacion", "tipo_cambio_fecha")
    op.drop_index("ix_tipo_cambio_par", table_name="tipo_cambio")
    op.drop_table("tipo_cambio")

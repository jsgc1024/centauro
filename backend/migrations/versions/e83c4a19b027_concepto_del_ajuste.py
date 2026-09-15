"""El ajuste de nomina dice de que es

Habia dos ajustes muy distintos compartiendo una tabla y una llave:
corregir lo que se pago por un dia, y descontar viaticos que no se
comprobaron. Como no se distinguian, se tapaban uno al otro —un
descuento de viaticos hacia que la correccion de nomina de ese mismo
dia nunca se generara— y la correccion se volvia a generar completa en
cada corrida, porque lo ya ajustado no contaba como pagado.

El respaldo se hace por el texto del motivo, que es el unico rastro que
quedo: los de viaticos siempre dicen "viaticos sin comprobar".

Revision ID: e83c4a19b027
Revises: d72b90ae5c14
"""
import sqlalchemy as sa
from alembic import op

revision = "e83c4a19b027"
down_revision = "d72b90ae5c14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ajuste_nomina",
                  sa.Column("concepto", sa.String(30), nullable=False,
                            server_default="manual"))

    # Lo que ya existe se clasifica por su motivo. Los de viaticos son
    # los unicos que dicen "viaticos sin comprobar"; los que trae el
    # formato "se pago X, corresponde Y" son correcciones de jornada; el
    # resto lo capturo finanzas a mano.
    op.execute("""
        UPDATE ajuste_nomina
           SET concepto = 'viatico_no_comprobado'
         WHERE motivo LIKE '%viaticos sin comprobar%'
    """)
    op.execute("""
        UPDATE ajuste_nomina
           SET concepto = 'correccion_jornada'
         WHERE motivo LIKE '%se pago%corresponde%'
           AND concepto = 'manual'
    """)


def downgrade() -> None:
    op.drop_column("ajuste_nomina", "concepto")

"""El acuerdo guarda cuando arranca y que dias corre

Revision ID: f1c85b3e60d4
Revises: e7c4b0d95a21
"""
from alembic import op
import sqlalchemy as sa

revision = "f1c85b3e60d4"
down_revision = "e7c4b0d95a21"
branch_labels = None
depends_on = None

DIAS = sa.Enum("LUNES_VIERNES", "LUNES_SABADO", "TODOS", name="diasservicio",
               create_type=False)


def upgrade() -> None:
    """El dia de inicio y los dias de servicio pasan a vivir en el acuerdo.

    Estaban solo en el contrato del mes, y el acuerdo se guarda antes: el
    consultor captura el trato hoy y abre el mes manana. Sin esto, el dia
    de inicio se perdia en medio.
    """
    op.add_column("acuerdo_implantado",
                  sa.Column("fecha_inicio", sa.Date(), nullable=True))
    op.add_column("acuerdo_implantado",
                  sa.Column("dias_servicio", DIAS, nullable=True))

    # Lo que ya tiene contrato se copia del primer mes abierto.
    op.execute("""
        UPDATE acuerdo_implantado a
           SET fecha_inicio = make_date(c.anio, c.mes,
                                        COALESCE(c.desde_dia, 1)),
               dias_servicio = c.dias_servicio
          FROM contrato_implantado c
         WHERE c.servicio_id = a.servicio_id
           AND c.id = (SELECT MIN(id) FROM contrato_implantado
                        WHERE servicio_id = a.servicio_id)
    """)


def downgrade() -> None:
    op.drop_column("acuerdo_implantado", "dias_servicio")
    op.drop_column("acuerdo_implantado", "fecha_inicio")

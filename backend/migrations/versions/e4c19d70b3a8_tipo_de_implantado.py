"""El tipo de implantado: 12 horas naturales o 12x36

Pedido de Salvador (20 sep). Son dos operaciones distintas y hay que
decir cual es desde el alta, porque de ahi sale el calendario del mes:

  natural  una persona, doce horas corridas, los dias que diga el
           acuerdo. Es lo que Centauro opera en Mexico y es lo que
           habia hasta hoy.
  12x36    dos personas de la misma categoria que se alternan dia con
           dia y cubren los siete dias de la semana. Es la escala de
           Brasil: doce horas de trabajo por treinta y seis de
           descanso. El mes sale entero en verde.

Todo lo que ya existe queda en "natural", que es lo que es. Esta
migracion solo abre la puerta: el calendario y la nomina del 12x36 se
construyen despues, y hasta entonces elegirlo no cambia nada.

Va como texto de dos codigos y no como ENUM de Postgres, igual que el
resto de las columnas que llevan un codigo.

Revision ID: e4c19d70b3a8
Revises: d1a73f5b0e62
"""
import sqlalchemy as sa
from alembic import op

revision = "e4c19d70b3a8"
down_revision = "d1a73f5b0e62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("acuerdo_implantado",
                  sa.Column("turno", sa.String(10), nullable=False,
                            server_default="natural"))


def downgrade() -> None:
    op.drop_column("acuerdo_implantado", "turno")

"""Las horas extra: quien corrige las horas del dia y su precio en el
implantado.

Decisiones de Salvador, 24 de septiembre (seccion 65 de la bitacora):

* Cada hora del dia que alguien corrige despues --el meet and greet o
  el fin del servicio-- deja su renglon en `correccion_horas`: que hora
  era, cual quedo, quien la cambio y por que. Lo corrige la central y,
  hasta su visto bueno, el consultor del servicio.
* En el implantado las horas extra se cobran en la factura del mes, con
  su propio precio en los terminos (`contrato_implantado.
  precio_hora_extra`). Los meses que ya existen quedan sin precio: no se
  cobra nada hasta que alguien lo ponga.

Revision ID: c3e7a1f94b2d
Revises: b5d8e3a1c7f4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3e7a1f94b2d"
down_revision: Union[str, None] = "b5d8e3a1c7f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "correccion_horas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jornada_id", sa.Integer(), sa.ForeignKey("jornada.id"),
                  nullable=False),
        sa.Column("campo", sa.String(length=10), nullable=False),
        sa.Column("antes", sa.DateTime(), nullable=True),
        sa.Column("despues", sa.DateTime(), nullable=False),
        sa.Column("persona_id", sa.Integer(), sa.ForeignKey("persona.id"),
                  nullable=True),
        sa.Column("motivo", sa.String(length=400), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_correccion_horas_jornada_id", "correccion_horas",
                    ["jornada_id"])
    op.add_column("contrato_implantado",
                  sa.Column("precio_hora_extra", sa.Numeric(12, 2),
                            nullable=True))


def downgrade() -> None:
    op.drop_column("contrato_implantado", "precio_hora_extra")
    op.drop_index("ix_correccion_horas_jornada_id",
                  table_name="correccion_horas")
    op.drop_table("correccion_horas")

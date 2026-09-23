"""El cierre en dos relojes.

Al terminar el eventual corren las 24 h del personal para comprobar sus
viaticos; al vencer --o antes, si todo el dinero ya cerro-- corren las
24 h del consultor para el visto bueno, que es cuando sale la factura.
Dos estatus nuevos en el servicio (sin_visto_bueno, en_facturacion),
uno en el cierre (sin_visto_bueno) y tres columnas en el cierre.

Revision ID: a1c4e7b9d2f6
Revises: f3a8c1d2e5b7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e7b9d2f6"
down_revision: Union[str, None] = "f3a8c1d2e5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE estatusservicio ADD VALUE IF NOT EXISTS "
               "'SIN_VISTO_BUENO' AFTER 'TERMINADO'")
    op.execute("ALTER TYPE estatusservicio ADD VALUE IF NOT EXISTS "
               "'EN_FACTURACION' AFTER 'SIN_VISTO_BUENO'")
    op.execute("ALTER TYPE estatuscierre ADD VALUE IF NOT EXISTS "
               "'SIN_VISTO_BUENO' AFTER 'ABIERTO'")
    op.add_column("cierre", sa.Column("comprobacion_hasta", sa.DateTime(),
                                      nullable=True))
    op.add_column("cierre", sa.Column("visto_bueno_desde", sa.DateTime(),
                                      nullable=True))
    op.add_column("cierre", sa.Column("motivo_apertura",
                                      sa.String(length=20), nullable=True))


def downgrade() -> None:
    # Postgres no deja quitar un valor de un enum: lo que este en los
    # estatus nuevos vuelve al anterior y el valor se queda en el tipo.
    op.execute("UPDATE servicio SET estatus = 'TERMINADO' "
               "WHERE estatus IN ('SIN_VISTO_BUENO', 'EN_FACTURACION')")
    op.execute("UPDATE cierre SET estatus = 'ABIERTO' "
               "WHERE estatus = 'SIN_VISTO_BUENO'")
    op.drop_column("cierre", "motivo_apertura")
    op.drop_column("cierre", "visto_bueno_desde")
    op.drop_column("cierre", "comprobacion_hasta")

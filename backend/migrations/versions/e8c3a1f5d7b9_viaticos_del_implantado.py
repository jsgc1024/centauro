"""Como se cobran los viaticos del implantado.

Decision de Salvador, 23 de septiembre (seccion 57 de la bitacora): la
cotizacion dice si los viaticos van incluidos en el precio o se cobran
aparte, por lo comprobado. El implantado no tiene cotizacion por dia:
sus precios viven en los terminos de cada mes, y ahi va la misma
opcion. Los meses que ya existen quedan con los viaticos incluidos, que
es lo que el sistema suponia hasta hoy.

Revision ID: e8c3a1f5d7b9
Revises: d4f1b8e2a6c9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8c3a1f5d7b9"
down_revision: Union[str, None] = "d4f1b8e2a6c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contrato_implantado",
                  sa.Column("viaticos_incluidos", sa.Boolean(),
                            server_default=sa.text("true"), nullable=False))


def downgrade() -> None:
    op.drop_column("contrato_implantado", "viaticos_incluidos")

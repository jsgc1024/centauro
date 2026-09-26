"""Los paquetes conductor + unidad en la cotizacion y el cierre (seccion 79)

El renglon de paquete en la cotizacion, y si los paquetes de una lista
traen los viaticos del dia --los de HASBRO si--, que marca finanzas.

Revision ID: b7e3a9c1d562
Revises: f4a8c2d6b913
"""
import sqlalchemy as sa
from alembic import op

revision = "b7e3a9c1d562"
down_revision = "f4a8c2d6b913"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # El renglon de un paquete: el rol en perfil_id y la unidad en
    # categoria_id, las dos columnas que la linea ya tenia.
    op.execute("ALTER TYPE tipolinea ADD VALUE IF NOT EXISTS 'PAQUETE'")
    op.add_column("tarifario", sa.Column("paquetes_con_viaticos", sa.Boolean(),
                                         nullable=False,
                                         server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("tarifario", "paquetes_con_viaticos")
    # El valor del enum no se quita: Postgres no sabe quitar valores de un
    # tipo. Una cotizacion con paquetes, bajada a una version sin ellos, se
    # vuelve a hacer.

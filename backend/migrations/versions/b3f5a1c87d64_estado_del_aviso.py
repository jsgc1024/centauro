"""El aviso sabe si salio o no

Hasta hoy `Notificacion` solo registraba: se escribia el aviso y ahi se
quedaba. Escribirlo y entregarlo son dos cosas distintas --entre una y
otra hay un proveedor que puede estar caido, una direccion mal escrita y
una bandeja que lo rebota-- y el aviso tiene que poder decir en cual de
las dos esta.

Todo lo que ya existe entra como "pendiente", que es lo que es: escrito
y sin entregar. Cuando se configure el correo, esa cola sale sola.
Cuidado con eso: si hay meses de avisos viejos acumulados, lo primero
que hace el despachador es mandarlos todos.

Revision ID: b3f5a1c87d64
Revises: a7d2c48f91e0
"""
import sqlalchemy as sa
from alembic import op

revision = "b3f5a1c87d64"
down_revision = "a7d2c48f91e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notificacion",
                  sa.Column("estado", sa.String(12), nullable=False,
                            server_default="pendiente"))
    op.add_column("notificacion",
                  sa.Column("intentos", sa.Integer(), nullable=False,
                            server_default=sa.text("0")))
    op.add_column("notificacion",
                  sa.Column("salio_en", sa.DateTime(), nullable=True))
    op.add_column("notificacion",
                  sa.Column("ultimo_error", sa.String(300), nullable=True))
    op.create_index("ix_notificacion_estado", "notificacion", ["estado"])


def downgrade() -> None:
    op.drop_index("ix_notificacion_estado", table_name="notificacion")
    op.drop_column("notificacion", "ultimo_error")
    op.drop_column("notificacion", "salio_en")
    op.drop_column("notificacion", "intentos")
    op.drop_column("notificacion", "estado")

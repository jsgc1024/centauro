"""El taller siempre sabe cuando llego

`TallerVehiculo.recibido_en` se declara obligatoria en el modelo y la
migracion que creo la tabla la dejo opcional. En la practica nunca
llega vacia —tiene `server_default` y nadie la escribe a mano— pero el
modelo promete un `datetime` y la base puede entregar None, y esa clase
de mentira revienta lejos del lugar donde se origino: en un
`.isoformat()` a media pantalla, semanas despues.

Se llenan primero las que hayan quedado vacias, si es que hay alguna, y
despues se cierra la columna.

Revision ID: b2f47c10d938
Revises: a71c3e5b9d84
"""
import sqlalchemy as sa
from alembic import op

revision = "b2f47c10d938"
down_revision = "a71c3e5b9d84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Si alguna quedo vacia, la fecha en que se recibio la unidad es lo
    # mas cercano que hay: el dia en que entro al taller.
    # `desde` es un date y la columna un timestamptz: se convierte a
    # mano en vez de dejarselo a Postgres.
    op.execute("UPDATE taller_vehiculo "
               "SET recibido_en = COALESCE(desde::timestamptz, now()) "
               "WHERE recibido_en IS NULL")
    op.alter_column("taller_vehiculo", "recibido_en",
                    existing_type=sa.DateTime(timezone=True),
                    nullable=False,
                    existing_server_default=sa.func.now())


def downgrade() -> None:
    op.alter_column("taller_vehiculo", "recibido_en",
                    existing_type=sa.DateTime(timezone=True),
                    nullable=True,
                    existing_server_default=sa.func.now())

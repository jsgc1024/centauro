"""Los enums nuevos van con los nombres, no con los valores

Revision ID: b06f4e28c517
Revises: a9d316e40b57
Create Date: 2026-09-13

SQLAlchemy guarda el NOMBRE del miembro del enum —SATURACION—, no su
valor —saturacion—. Los tipos que cree para el auto rentado y para las
compras especiales quedaron con los valores en minuscula, asi que el
primer INSERT reventaba con "invalid input value for enum".

Las pruebas no lo vieron porque la base de pruebas se arma desde el
modelo y no desde las migraciones: ahi el tipo salia bien. Es un hueco
del arnes, no del codigo.

Se recrea cada tipo con las etiquetas correctas y se convierte lo que
haya en la tabla subiendolo a mayusculas.
"""
from alembic import op

revision = "b06f4e28c517"
down_revision = "a9d316e40b57"
branch_labels = None
depends_on = None

TIPOS = [
    ("motivorenta", "vehiculo", "motivo_renta", None,
     ["CATEGORIA_NO_DISPONIBLE", "SATURACION", "PEDIDO_ESPECIAL"]),
    ("tipocompra", "compra_especial", "tipo", None,
     ["VUELO", "HOSPEDAJE", "TRANSPORTE", "OTRO"]),
    ("estatuscompra", "compra_especial", "estatus", "SOLICITADA",
     ["SOLICITADA", "EN_GESTION", "CONFIRMADA", "RECHAZADA", "CANCELADA"]),
]


def _rehacer(nombre, tabla, columna, defecto, etiquetas, arriba=True):
    conversion = "upper" if arriba else "lower"
    valores = ", ".join(f"'{e if arriba else e.lower()}'" for e in etiquetas)

    op.execute(f"ALTER TYPE {nombre} RENAME TO {nombre}_anterior")
    op.execute(f"CREATE TYPE {nombre} AS ENUM ({valores})")
    # El defecto se quita antes de cambiar el tipo: Postgres no puede
    # convertir un default que todavia apunta al tipo viejo.
    if defecto:
        op.execute(f"ALTER TABLE {tabla} ALTER COLUMN {columna} DROP DEFAULT")
    op.execute(
        f"ALTER TABLE {tabla} ALTER COLUMN {columna} TYPE {nombre} "
        f"USING {conversion}({columna}::text)::{nombre}")
    if defecto:
        etiqueta = defecto if arriba else defecto.lower()
        op.execute(f"ALTER TABLE {tabla} ALTER COLUMN {columna} "
                   f"SET DEFAULT '{etiqueta}'")
    op.execute(f"DROP TYPE {nombre}_anterior")


def upgrade():
    for nombre, tabla, columna, defecto, etiquetas in TIPOS:
        _rehacer(nombre, tabla, columna, defecto, etiquetas, arriba=True)


def downgrade():
    for nombre, tabla, columna, defecto, etiquetas in TIPOS:
        _rehacer(nombre, tabla, columna, defecto, etiquetas, arriba=False)

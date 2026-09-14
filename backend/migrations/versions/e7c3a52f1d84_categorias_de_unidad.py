"""las categorias de unidad de Centauro

Dejan de nombrarse por marca y modelo y pasan a las categorias reales de
la operacion: CUV, Minivan, Minivan Blindada, SUV, SUV Blindada y
Van 10 pax. El mismo servicio se cubre con la SUV que haya disponible, no
con una Suburban en particular.

Se renombran las que ya existen para no perder tarifas ni unidades, y se
agrega la SUV sin blindar, que no estaba.

Revision ID: e7c3a52f1d84
Revises: d5e2c8a913b7
Create Date: 2026-09-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7c3a52f1d84"
down_revision: Union[str, None] = "d5e2c8a913b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# codigo viejo -> (codigo nuevo, nombre nuevo)
RENOMBRE = {
    "rav4": ("cuv", "CUV"),
    "sienna": ("minivan", "Minivan"),
    "sienna_blindada": ("minivan_blindada", "Minivan Blindada"),
    "suburban_blindada": ("suv_blindada", "SUV Blindada"),
    "hiace": ("van_10", "Van 10 pax"),
}


def upgrade() -> None:
    for viejo, (nuevo, nombre) in RENOMBRE.items():
        op.execute(sa.text(
            "UPDATE categoria_vehiculo SET codigo = :nuevo, nombre = :nombre "
            "WHERE codigo = :viejo").bindparams(
                nuevo=nuevo, nombre=nombre, viejo=viejo))

    # La SUV sin blindar no existia. El rendimiento es de ejemplo, como el
    # resto: la direccion carga los reales.
    op.execute(sa.text(
        "INSERT INTO categoria_vehiculo "
        "  (codigo, nombre, blindado, rendimiento_km_litro, activo) "
        "SELECT 'suv', 'SUV', false, 7.0, true "
        "WHERE NOT EXISTS "
        "  (SELECT 1 FROM categoria_vehiculo WHERE codigo = 'suv')"))


def downgrade() -> None:
    op.execute("DELETE FROM categoria_vehiculo WHERE codigo = 'suv'")
    for viejo, (nuevo, _) in RENOMBRE.items():
        op.execute(sa.text(
            "UPDATE categoria_vehiculo SET codigo = :viejo "
            "WHERE codigo = :nuevo").bindparams(viejo=viejo, nuevo=nuevo))

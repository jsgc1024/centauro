"""El rol de Sistema y calidad (seccion 85)

Administra el sistema --accesos, Odoo y catalogos-- y mide la calidad
del servicio. No mueve dinero ni opera.

Y a los puestos que entran como Direccion de operaciones se les agregan
dos actividades nuevas: ver Calidad y fijar lo que en los catalogos
decide dinero. Decision de Salvador (27 sep, propuesta de administracion
del sistema y calidad). Solo se agregan: lo que alguien ajusto en esos
puestos se queda como estaba.

Revision ID: f4c1a9d27e63
Revises: e7a3c9d15b28
"""
from alembic import op

revision = "f4c1a9d27e63"
down_revision = "e7a3c9d15b28"
branch_labels = None
depends_on = None

A_DIRECCION_DE_OPERACIONES = ("calidad.ver", "catalogos.dinero")


def upgrade() -> None:
    # El valor se guarda con el NOMBRE del miembro, en mayusculas, que es
    # como SQLAlchemy escribe los enum de Postgres en este esquema.
    op.execute("ALTER TYPE rol ADD VALUE IF NOT EXISTS 'SISTEMA_CALIDAD'")
    for actividad in A_DIRECCION_DE_OPERACIONES:
        op.execute(f"""
            INSERT INTO actividad_de_categoria (categoria_id, actividad)
            SELECT c.id, '{actividad}' FROM categoria_acceso c
            WHERE c.rol = 'DIRECTOR_OPERACIONES'
              AND NOT EXISTS (SELECT 1 FROM actividad_de_categoria a
                              WHERE a.categoria_id = c.id
                                AND a.actividad = '{actividad}')""")


def downgrade() -> None:
    """Las dos actividades se quitan. El valor del enum se queda: Postgres
    no quita valores sin recrear el tipo entero, y recrearlo se llevaria
    las filas que lo usan."""
    for actividad in A_DIRECCION_DE_OPERACIONES:
        op.execute(f"""
            DELETE FROM actividad_de_categoria
            WHERE actividad = '{actividad}'
              AND categoria_id IN (SELECT id FROM categoria_acceso
                                   WHERE rol = 'DIRECTOR_OPERACIONES')""")

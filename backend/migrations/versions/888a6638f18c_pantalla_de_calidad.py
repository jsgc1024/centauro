"""La pantalla de Calidad (seccion 89)

Los puestos que ya existen y traen `calidad.ver` --el de sistema y
calidad y el de direccion de operaciones-- traen la pantalla nueva en su
menu.

Solo agrega: a un puesto que dice sus pantallas se le suma una; al que
no las dice --entra con el menu de su rol-- no se le toca nada.

Revision ID: 888a6638f18c
Revises: d4453bd77820
"""
from alembic import op

revision = "888a6638f18c"
down_revision = "d4453bd77820"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE categoria_acceso c
        SET pantallas = c.pantallas || ',calidad'
        WHERE c.pantallas IS NOT NULL AND c.pantallas <> ''
          AND NOT ('calidad' = ANY(string_to_array(c.pantallas, ',')))
          AND EXISTS (SELECT 1 FROM actividad_de_categoria a
                      WHERE a.categoria_id = c.id
                        AND a.actividad = 'calidad.ver')""")


def downgrade() -> None:
    op.execute("""
        UPDATE categoria_acceso
        SET pantallas = NULLIF(array_to_string(
            array_remove(string_to_array(pantallas, ','), 'calidad'), ','), '')
        WHERE pantallas IS NOT NULL
          AND 'calidad' = ANY(string_to_array(pantallas, ','))""")

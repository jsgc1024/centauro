"""La pantalla de Catalogos (seccion 86)

Los puestos que ya existen y llevan un catalogo o leen la bitacora
--catalogos.editar, catalogos.dinero o bitacora.ver-- traen la pantalla
nueva en su menu. Y el de sistema y calidad, buscar en Google Maps: lleva
los hospitales y los hoteles, y con Google salen con su direccion y su
ubicacion.

Solo agrega: a un puesto que dice sus pantallas se le suma una; al que
no las dice --entra con el menu de su rol-- no se le toca nada.

Revision ID: d4453bd77820
Revises: f4c1a9d27e63
"""
from alembic import op

revision = "d4453bd77820"
down_revision = "f4c1a9d27e63"
branch_labels = None
depends_on = None

LA_LLENAN = ("catalogos.editar", "catalogos.dinero", "bitacora.ver")


def upgrade() -> None:
    lista = ", ".join(f"'{a}'" for a in LA_LLENAN)
    op.execute(f"""
        UPDATE categoria_acceso c
        SET pantallas = c.pantallas || ',catalogos'
        WHERE c.pantallas IS NOT NULL AND c.pantallas <> ''
          AND NOT ('catalogos' = ANY(string_to_array(c.pantallas, ',')))
          AND EXISTS (SELECT 1 FROM actividad_de_categoria a
                      WHERE a.categoria_id = c.id
                        AND a.actividad IN ({lista}))""")
    # El rol se compara como texto: en una base nueva, todas las
    # migraciones corren en una sola transaccion, y Postgres no deja usar
    # como valor del enum el que se agrego en ella misma (f4c1a9d27e63)
    # hasta que se confirma. Como texto no lo usa como enum.
    op.execute("""
        INSERT INTO actividad_de_categoria (categoria_id, actividad)
        SELECT c.id, 'mapas.buscar' FROM categoria_acceso c
        WHERE c.rol::text = 'SISTEMA_CALIDAD'
          AND NOT EXISTS (SELECT 1 FROM actividad_de_categoria a
                          WHERE a.categoria_id = c.id
                            AND a.actividad = 'mapas.buscar')""")


def downgrade() -> None:
    op.execute("""
        UPDATE categoria_acceso
        SET pantallas = NULLIF(array_to_string(
            array_remove(string_to_array(pantallas, ','), 'catalogos'), ','), '')
        WHERE pantallas IS NOT NULL
          AND 'catalogos' = ANY(string_to_array(pantallas, ','))""")
    op.execute("""
        DELETE FROM actividad_de_categoria
        WHERE actividad = 'mapas.buscar'
          AND categoria_id IN (SELECT id FROM categoria_acceso
                               WHERE rol::text = 'SISTEMA_CALIDAD')""")

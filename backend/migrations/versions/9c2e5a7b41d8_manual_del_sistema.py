"""El manual del sistema (seccion 90)

Dos tablas: la ultima vuelta de cada tarea del reloj y los casos
resueltos. Y la pantalla nueva: el puesto de sistema y calidad trae
`manual.ver`, y los puestos que dicen sus pantallas y la traen suman
«manual» a su menu. Direccion general y administracion entran con su rol
y la alcanzan por el.

Solo agrega: a un puesto que no dice sus pantallas --entra con el menu de
su rol-- no se le toca nada.

Revision ID: 9c2e5a7b41d8
Revises: 888a6638f18c
"""
import sqlalchemy as sa
from alembic import op

revision = "9c2e5a7b41d8"
down_revision = "888a6638f18c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vuelta_del_reloj",
        sa.Column("tarea", sa.String(length=80), nullable=False),
        sa.Column("empezo_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termino_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estado", sa.String(length=10), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("error_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nota", sa.String(length=200), nullable=True),
        sa.Column("vueltas", sa.Integer(), server_default=sa.text("0"),
                  nullable=False),
        sa.PrimaryKeyConstraint("tarea"),
    )
    op.create_table(
        "caso_resuelto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("que_se_vio", sa.Text(), nullable=False),
        sa.Column("causa", sa.Text(), nullable=False),
        sa.Column("solucion", sa.Text(), nullable=False),
        sa.Column("area", sa.String(length=60), nullable=True),
        sa.Column("falla", sa.String(length=10), server_default="no_se",
                  nullable=False),
        sa.Column("escrito_por_id", sa.Integer(), nullable=True),
        sa.Column("escrito_en", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("editado_por_id", sa.Integer(), nullable=True),
        sa.Column("editado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["escrito_por_id"], ["persona.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["editado_por_id"], ["persona.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # El rol se compara como texto, como en d4453bd77820: en una base
    # nueva todas las migraciones corren en una transaccion y Postgres no
    # deja usar el valor del enum que se agrego en ella misma.
    op.execute("""
        INSERT INTO actividad_de_categoria (categoria_id, actividad)
        SELECT c.id, 'manual.ver' FROM categoria_acceso c
        WHERE c.rol::text = 'SISTEMA_CALIDAD'
          AND NOT EXISTS (SELECT 1 FROM actividad_de_categoria a
                          WHERE a.categoria_id = c.id
                            AND a.actividad = 'manual.ver')""")
    op.execute("""
        UPDATE categoria_acceso c
        SET pantallas = c.pantallas || ',manual'
        WHERE c.pantallas IS NOT NULL AND c.pantallas <> ''
          AND NOT ('manual' = ANY(string_to_array(c.pantallas, ',')))
          AND EXISTS (SELECT 1 FROM actividad_de_categoria a
                      WHERE a.categoria_id = c.id
                        AND a.actividad = 'manual.ver')""")


def downgrade() -> None:
    op.execute("""
        UPDATE categoria_acceso
        SET pantallas = NULLIF(array_to_string(
            array_remove(string_to_array(pantallas, ','), 'manual'), ','), '')
        WHERE pantallas IS NOT NULL
          AND 'manual' = ANY(string_to_array(pantallas, ','))""")
    op.execute("""
        DELETE FROM actividad_de_categoria
        WHERE actividad = 'manual.ver'
          AND categoria_id IN (SELECT id FROM categoria_acceso
                               WHERE rol::text = 'SISTEMA_CALIDAD')""")
    op.drop_table("caso_resuelto")
    op.drop_table("vuelta_del_reloj")

"""El rol vive en la asignacion, no en la persona

Revision ID: b83f16a09d2e
Revises: a71d95c2e480
"""
from alembic import op
import sqlalchemy as sa


revision = "b83f16a09d2e"
down_revision = "a71d95c2e480"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """El personal de seguridad es general; el rol lo decide el consultor.

    Hasta hoy cada persona traia un puesto fijo en su ficha y de ahi
    salian el precio al cliente y la comision que se le paga. Pero el
    mismo agente que hoy conduce manana coordina, y cobrarlo siempre
    igual era cobrar mal.

    Asi que el rol pasa a la asignacion: al dia, en el eventual, y a la
    plantilla del mes en el implantado. Lo que ya existe se copia desde
    el puesto que traia la persona, para que ningun servicio cerrado
    pierda de donde salio su numero.
    """
    for tabla in ("asignacion_personal", "persona_implantado"):
        op.add_column(tabla, sa.Column("rol_id", sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_{tabla}_rol", tabla, "perfil_personal",
                              ["rol_id"], ["id"])
        op.execute(f"""
            UPDATE {tabla} SET rol_id = persona.perfil_id
            FROM persona WHERE persona.id = {tabla}.persona_id
        """)

    # Los cuatro roles con el nombre que se usa en la calle. El
    # coordinador y el consultor tambien cubren servicio: dejaron de ser
    # personal de casa el dia que el cliente pidio uno.
    op.execute("UPDATE perfil_personal SET codigo = 'coordinador_seguridad', "
               "nombre = 'Coordinador de seguridad' WHERE codigo = 'coordinador'")
    op.execute("UPDATE perfil_personal SET codigo = 'consultor_seguridad', "
               "nombre = 'Consultor de seguridad' WHERE codigo = 'consultor'")

    # Y la ficha de la persona se queda sin puesto: es personal de
    # seguridad, a secas.
    op.drop_column("persona", "perfil_id")


def downgrade() -> None:
    op.add_column("persona", sa.Column("perfil_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_persona_perfil", "persona", "perfil_personal",
                          ["perfil_id"], ["id"])
    # Se devuelve el rol mas reciente de cada quien, que es lo mas
    # parecido al puesto que tenia.
    op.execute("""
        UPDATE persona SET perfil_id = ultimo.rol_id FROM (
            SELECT DISTINCT ON (persona_id) persona_id, rol_id
            FROM asignacion_personal WHERE rol_id IS NOT NULL
            ORDER BY persona_id, id DESC) AS ultimo
        WHERE persona.id = ultimo.persona_id
    """)
    op.execute("UPDATE perfil_personal SET codigo = 'coordinador', "
               "nombre = 'Coordinador' WHERE codigo = 'coordinador_seguridad'")
    op.execute("UPDATE perfil_personal SET codigo = 'consultor', "
               "nombre = 'Consultor' WHERE codigo = 'consultor_seguridad'")
    for tabla in ("persona_implantado", "asignacion_personal"):
        op.drop_constraint(f"fk_{tabla}_rol", tabla, type_="foreignkey")
        op.drop_column(tabla, "rol_id")

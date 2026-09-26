"""El personal de oficina, leido de Odoo (seccion 74)

Segundo paso de la propuesta Puestos y Odoo, aprobada por Salvador el 26
de septiembre: la gente de oficina que tiene correo de trabajo en Odoo
llega a Centauro con su puesto y su departamento, y Recursos Humanos le
da su acceso a la consola con el puesto que eso sugiere.

`oficina` nace en falso para todos: nadie de los que ya existen cambia
de lista hasta que la lectura de Odoo lo reconozca.

Revision ID: c7d1e5f3a912
Revises: e2b9c4d7a813
"""
import sqlalchemy as sa
from alembic import op

revision = "c7d1e5f3a912"
down_revision = "e2b9c4d7a813"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("persona", sa.Column("oficina", sa.Boolean(),
                                       nullable=False,
                                       server_default=sa.false()))
    op.add_column("persona", sa.Column("puesto_odoo", sa.String(120),
                                       nullable=True))
    op.add_column("persona", sa.Column("area_odoo", sa.String(120),
                                       nullable=True))


def downgrade() -> None:
    for columna in ("area_odoo", "puesto_odoo", "oficina"):
        op.drop_column("persona", columna)

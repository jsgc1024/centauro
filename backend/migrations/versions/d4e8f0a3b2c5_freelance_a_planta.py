"""El freelance que pasa a planta, y el que vuelve de Odoo (seccion 132,
decision 6)

RH pasa a planta al freelance que Centauro contrato: su ficha se cierra
como historia (cuando y quien) y la lectura de Odoo lo toma por su
correo. Y el alta de freelance reutiliza a la persona que se fue de Odoo
con el mismo correo: su ficha guarda el empleado de Odoo que fue.

Revision ID: d4e8f0a3b2c5
Revises: c3d7e9f2a1b4
"""
import sqlalchemy as sa
from alembic import op

revision = "d4e8f0a3b2c5"
down_revision = "c3d7e9f2a1b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("freelance", sa.Column("planta_en", sa.DateTime(timezone=True),
                                         nullable=True))
    op.add_column("freelance", sa.Column("planta_por_id", sa.Integer(),
                                         sa.ForeignKey("persona.id"),
                                         nullable=True))
    op.add_column("freelance", sa.Column("odoo_id_anterior", sa.Integer(),
                                         nullable=True))


def downgrade() -> None:
    op.drop_column("freelance", "odoo_id_anterior")
    op.drop_column("freelance", "planta_por_id")
    op.drop_column("freelance", "planta_en")

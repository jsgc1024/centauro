"""El idioma de cada pais

Decision de Salvador (19 sep): la app de campo no lleva selector de
idioma. El agente va con una mano y prisa, y un boton que se toca sin
querer y le deja la app en portugues a las seis de la manana es peor que
el problema que resuelve. Lo toma del pais donde esta su plaza.

Va como texto de dos letras y no como ENUM de Postgres, igual que el
resto de las columnas que llevan un codigo: agregar un idioma manana no
deberia necesitar tocar la base. Es la decision vieja que ya ahorro tres
migraciones.

Todos entran en espanol y Brasil pasa a portugues, que es el unico pais
sembrado donde no se habla espanol. Si manana hay otro, se cambia desde
el catalogo de paises, no desde aqui.

Revision ID: c8e40b17a935
Revises: b6d3f90a172c
"""
import sqlalchemy as sa
from alembic import op

revision = "c8e40b17a935"
down_revision = "b6d3f90a172c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pais", sa.Column("idioma", sa.String(2), nullable=False,
                                    server_default="es"))
    op.execute("UPDATE pais SET idioma = 'pt' WHERE codigo = 'BR'")


def downgrade() -> None:
    op.drop_column("pais", "idioma")

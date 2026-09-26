"""Los puestos de verdad (seccion 73)

Decision de Salvador, 26 de septiembre: cada quien entra con el puesto
que tiene en Odoo y ve solo lo de su trabajo. El puesto ya existia como
lista de actividades; aqui gana lo que le faltaba para ser un puesto:
con que rol entra quien lo trae, en que area del organigrama vive, que
pantallas le salen en el menu, a que puestos de Odoo se parece y en que
orden se lista.

Todas las columnas nacen vacias: un puesto que ya existia sigue haciendo
exactamente lo mismo --sin pantallas, el menu sale de su rol--.

Revision ID: e2b9c4d7a813
Revises: b8e4f1a2c739
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e2b9c4d7a813"
down_revision = "b8e4f1a2c739"
branch_labels = None
depends_on = None

# El mismo tipo que ya usa usuario.rol: no se crea otro.
ROL = postgresql.ENUM("PERSONAL_SEGURIDAD", "CENTRAL", "CONSULTOR",
                      "DIRECTOR_OPERACIONES", "DIRECTOR_GENERAL", "FINANZAS",
                      "RECURSOS_HUMANOS", "ADMIN", name="rol",
                      create_type=False)


def upgrade() -> None:
    op.add_column("categoria_acceso", sa.Column("rol", ROL, nullable=True))
    op.add_column("categoria_acceso", sa.Column("area", sa.String(60),
                                                nullable=True))
    op.add_column("categoria_acceso", sa.Column("pantallas", sa.Text(),
                                                nullable=True))
    op.add_column("categoria_acceso", sa.Column("puestos_odoo", sa.Text(),
                                                nullable=True))
    op.add_column("categoria_acceso", sa.Column("orden", sa.Integer(),
                                                nullable=True))


def downgrade() -> None:
    for columna in ("orden", "puestos_odoo", "pantallas", "area", "rol"):
        op.drop_column("categoria_acceso", columna)

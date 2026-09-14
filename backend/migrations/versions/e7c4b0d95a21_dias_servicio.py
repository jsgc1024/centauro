"""El implantado dice que dias de la semana cubre

Revision ID: e7c4b0d95a21
Revises: d6a04e91b3c7
"""
from alembic import op
import sqlalchemy as sa

revision = "e7c4b0d95a21"
down_revision = "d6a04e91b3c7"
branch_labels = None
depends_on = None

# El enum guarda el nombre del miembro, no su valor: asi lo escribe
# SQLAlchemy y asi tiene que existir en Postgres.
DIAS = sa.Enum("LUNES_VIERNES", "LUNES_SABADO", "TODOS", name="diasservicio")


def upgrade() -> None:
    """De un si/no de fines de semana a los tres esquemas que existen.

    Lunes a viernes, lunes a sabado o todos los dias. El si/no se queda
    donde esta —la puerta del contrato mensual lo sigue mandando— y los
    contratos que ya existen se traducen: el que tenia fines de semana
    pasa a todos los dias, el que no, a lunes a viernes.
    """
    DIAS.create(op.get_bind(), checkfirst=True)
    op.add_column("contrato_implantado",
                  sa.Column("dias_servicio", DIAS, nullable=True))
    # Postgres no convierte texto a enum por su cuenta: hay que decirselo.
    op.execute("UPDATE contrato_implantado SET dias_servicio = "
               "(CASE WHEN incluye_fines_de_semana THEN 'TODOS' "
               "ELSE 'LUNES_VIERNES' END)::diasservicio")
    op.alter_column("contrato_implantado", "dias_servicio", nullable=False,
                    server_default=sa.text("'LUNES_VIERNES'::diasservicio"))


def downgrade() -> None:
    op.drop_column("contrato_implantado", "dias_servicio")
    DIAS.drop(op.get_bind(), checkfirst=True)

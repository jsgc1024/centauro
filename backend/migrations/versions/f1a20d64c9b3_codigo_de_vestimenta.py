"""El codigo de vestimenta del equipo

Lo pide el consultor al dar de alta el servicio y lo leen tres: el
personal de seguridad en la app la noche anterior --que es cuando de
verdad sirve, porque es cuando se decide que ponerse--, el cliente en el
task sheet, y la central cuando alguien pregunta.

Lista cerrada de tres --casual, semiformal, formal-- y no texto libre:
"traje oscuro sin corbata" escrito a mano en cada servicio se lee
distinto cada vez.

Nulo a proposito. Los servicios que ya existen no dicen nada en vez de
decir algo que nadie acordo, y el implantado no la usa: ese trabaja
todos los dias con el mismo cliente y su vestimenta se acuerda una sola
vez. Decision de Salvador (20 sep).

Revision ID: f1a20d64c9b3
Revises: e8c41a95b307
"""
import sqlalchemy as sa
from alembic import op

revision = "f1a20d64c9b3"
down_revision = "e8c41a95b307"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # String y no ENUM de Postgres: agregar un valor a un ENUM en
    # produccion es una migracion aparte, y esta lista puede crecer.
    op.add_column("servicio",
                  sa.Column("vestimenta", sa.String(12), nullable=True))


def downgrade() -> None:
    op.drop_column("servicio", "vestimenta")

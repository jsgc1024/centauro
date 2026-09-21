"""El camino al meet and greet

El conductor que se queda dormido no manda una senal equivocada: no
manda ninguna, y el silencio no disparaba nada. La central se enteraba
cuando llamaba el cliente.

Reponer a alguien toma hasta hora y media, asi que enterarse a la hora
de la presentacion es enterarse tarde. Estas dos tablas guardan el
camino: los toques que se le mandan desde dos horas antes y donde estaba
cada vez que contesto.

La distancia va en linea recta y en metros. No se calcula ruta ni
trafico --eso seria una API de Google en cada lectura-- porque lo que se
quiere saber no es a que hora llega, sino si se esta moviendo hacia
alla.

Revision ID: e8c41a95b307
Revises: d7f10b3c85a2
"""
import sqlalchemy as sa
from alembic import op

revision = "e8c41a95b307"
down_revision = "d7f10b3c85a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trayecto",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("jornada_id", sa.Integer,
                  sa.ForeignKey("jornada.id"), nullable=False, index=True),
        sa.Column("persona_id", sa.Integer,
                  sa.ForeignKey("persona.id"), nullable=False, index=True),
        # El estado va como texto y no como ENUM de Postgres: es la
        # decision vieja de la casa, y ya ahorro varias migraciones.
        sa.Column("estado", sa.String(14), nullable=False,
                  server_default="esperando"),
        sa.Column("toques", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ultimo_toque_en", sa.DateTime, nullable=True),
        sa.Column("distancia_inicial_m", sa.Integer, nullable=True),
        sa.Column("distancia_ultima_m", sa.Integer, nullable=True),
        sa.Column("ultima_lectura_en", sa.DateTime, nullable=True),
        sa.Column("sin_avanzar", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("alertado", sa.Boolean, nullable=False,
                  server_default="false"),
        sa.UniqueConstraint("jornada_id", "persona_id",
                            name="uq_trayecto_jornada_persona"),
    )
    op.create_table(
        "lectura_trayecto",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trayecto_id", sa.Integer,
                  sa.ForeignKey("trayecto.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("momento", sa.DateTime, nullable=False),
        sa.Column("lat", sa.Numeric(10, 7), nullable=False),
        sa.Column("lon", sa.Numeric(10, 7), nullable=False),
        sa.Column("distancia_m", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("lectura_trayecto")
    op.drop_table("trayecto")

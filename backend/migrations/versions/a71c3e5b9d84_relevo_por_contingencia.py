"""El relevo a media jornada

Un reemplazo por contingencia mutaba la asignacion: `persona_id` cambiaba
de dueno y quien se habia presentado esa manana desaparecia del dia. La
nomina paga por asignacion, asi que el que trabajo cuatro horas cobraba
cero, y nada en el sistema recordaba que estuvo ahi.

Con estas dos columnas el dia se parte en vez de mutarse: la asignacion
de quien sale se queda, marcada con la hora en que lo relevaron y con
quien entro en su lugar, y la de quien entra se crea aparte. Las dos
entran a nomina; al cliente se le cobra una sola, porque el cierre y la
cotizacion ignoran la relevada.

Nada de lo que ya existe cambia de comportamiento: una asignacion sin
relevar es exactamente lo que era.

Revision ID: a71c3e5b9d84
Revises: f94d1a2e70b5
"""
import sqlalchemy as sa
from alembic import op

revision = "a71c3e5b9d84"
down_revision = "f94d1a2e70b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Naive a proposito: como todas las columnas de operacion, guarda
    # hora de pared del pais del servicio (ver app/reloj.py).
    op.add_column("asignacion_personal",
                  sa.Column("relevado_en", sa.DateTime(), nullable=True))
    op.add_column("asignacion_personal",
                  sa.Column("relevado_por_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_asignacion_personal_relevado_por",
                          "asignacion_personal", "persona",
                          ["relevado_por_id"], ["id"])

    # La unidad se releva igual que la persona, y por la misma razon:
    # si la asignacion vieja se muta, la camioneta que salio desaparece
    # del servicio y ya no se le puede hacer la revision de devolucion.
    # Un golpe en esa unidad se queda sin dueno, que es justo lo que la
    # revision con fotos vino a resolver.
    op.add_column("asignacion_vehiculo",
                  sa.Column("relevado_en", sa.DateTime(), nullable=True))
    op.add_column("asignacion_vehiculo",
                  sa.Column("relevado_por_vehiculo_id", sa.Integer(),
                            nullable=True))
    op.create_foreign_key("fk_asignacion_vehiculo_relevado_por",
                          "asignacion_vehiculo", "vehiculo",
                          ["relevado_por_vehiculo_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_asignacion_vehiculo_relevado_por",
                       "asignacion_vehiculo", type_="foreignkey")
    op.drop_column("asignacion_vehiculo", "relevado_por_vehiculo_id")
    op.drop_column("asignacion_vehiculo", "relevado_en")
    op.drop_constraint("fk_asignacion_personal_relevado_por",
                       "asignacion_personal", type_="foreignkey")
    op.drop_column("asignacion_personal", "relevado_por_id")
    op.drop_column("asignacion_personal", "relevado_en")

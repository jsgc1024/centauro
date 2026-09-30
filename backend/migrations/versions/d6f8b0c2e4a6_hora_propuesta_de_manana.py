"""La hora de manana que captura el conductor pasa por la central

Seccion 105, decision 5 de Salvador. La hora que el conductor captura al
cerrar el dia --"el principal dijo que manana a las 7:30"-- se asentaba
directo en el dia siguiente, con aviso a los companeros y moviendo el
punto de encuentro con el GPS del telefono, sin que la central la
revisara. Ahora se guarda como propuesta en la jornada de manana: la
central la confirma o la rechaza con un clic desde "Manana", y si nadie
la toca antes de las 22:00 del pais el reloj la confirma como la
capturo el conductor. El punto ya no se mueve solo.

Cinco columnas en `jornada`, todas vacias en lo que ya existe: la hora
propuesta, quien la propuso y cuando (hora de pared del pais), la nota
con la que la explico, y como se resolvio (confirmada_central,
confirmada_reloj o rechazada; vacia con hora es que sigue pendiente).

Revision ID: d6f8b0c2e4a6
Revises: b4d6f8a0c2e4
Create Date: 2026-09-29
"""
import sqlalchemy as sa
from alembic import op

revision = "d6f8b0c2e4a6"
down_revision = "b4d6f8a0c2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jornada", sa.Column("hora_propuesta", sa.Time(),
                                       nullable=True))
    op.add_column("jornada", sa.Column("hora_propuesta_por_id", sa.Integer(),
                                       nullable=True))
    op.create_foreign_key("fk_jornada_hora_propuesta_por", "jornada",
                          "persona", ["hora_propuesta_por_id"], ["id"])
    op.add_column("jornada", sa.Column("hora_propuesta_en", sa.DateTime(),
                                       nullable=True))
    op.add_column("jornada", sa.Column("hora_propuesta_nota", sa.String(600),
                                       nullable=True))
    op.add_column("jornada", sa.Column("hora_propuesta_resuelta",
                                       sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("jornada", "hora_propuesta_resuelta")
    op.drop_column("jornada", "hora_propuesta_nota")
    op.drop_column("jornada", "hora_propuesta_en")
    op.drop_constraint("fk_jornada_hora_propuesta_por", "jornada",
                       type_="foreignkey")
    op.drop_column("jornada", "hora_propuesta_por_id")
    op.drop_column("jornada", "hora_propuesta")

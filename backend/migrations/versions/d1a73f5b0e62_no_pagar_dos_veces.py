"""El candado de no pagar dos veces baja a la base

Vivia solo en Python: `jornadas_pendientes` saca lo que ya se pago y lo
descuenta. Entre leer eso y escribir el corte hay una rendija --dos
cortes calculados al mismo tiempo leen los dos que la jornada esta
libre-- y lo que se cuela por ahi es dinero pagado dos veces.

La nomina de la misma semana ya estaba protegida: `nomina_semanal` es
unica por pais y fecha de corte, asi que dos corridas simultaneas de la
misma semana chocan. Lo que no estaba son dos cortes de semanas
DISTINTAS del mismo pais, que no se filtran por fecha a proposito
--manda que la jornada este terminada y su servicio vaya a
facturacion-- y podian llevarse la misma jornada.

El candado no cabe en una sola tabla como esta: la jornada vive en
`concepto_nomina` y la persona en `renglon_nomina`, y una jornada de
equipo tiene VARIAS personas --por eso una restriccion sobre
`jornada_id` sola seria falsa y reventaria cualquier dia de dos
escoltas--. Asi que la persona baja al concepto, duplicada a proposito,
y la restriccion va sobre el par.

Si esta migracion falla al crear la restriccion, el mensaje no es un
problema de esquema: son dos renglones con la misma jornada y la misma
persona, o sea un dia pagado dos veces que ya esta en la base. Hay que
mirarlos antes de seguir.

Revision ID: d1a73f5b0e62
Revises: c8e40b17a935
"""
import sqlalchemy as sa
from alembic import op

revision = "d1a73f5b0e62"
down_revision = "c8e40b17a935"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("concepto_nomina",
                  sa.Column("persona_id", sa.Integer(), nullable=True))
    # De donde sale: del renglon al que cuelga, que es donde vive hoy.
    op.execute("""
        UPDATE concepto_nomina c
           SET persona_id = r.persona_id
          FROM renglon_nomina r
         WHERE c.renglon_id = r.id
    """)
    op.alter_column("concepto_nomina", "persona_id", nullable=False)
    op.create_foreign_key("fk_concepto_persona", "concepto_nomina",
                          "persona", ["persona_id"], ["id"])
    op.create_unique_constraint("uq_concepto_jornada_persona",
                                "concepto_nomina",
                                ["jornada_id", "persona_id"])


def downgrade() -> None:
    op.drop_constraint("uq_concepto_jornada_persona", "concepto_nomina",
                       type_="unique")
    op.drop_constraint("fk_concepto_persona", "concepto_nomina",
                       type_="foreignkey")
    op.drop_column("concepto_nomina", "persona_id")

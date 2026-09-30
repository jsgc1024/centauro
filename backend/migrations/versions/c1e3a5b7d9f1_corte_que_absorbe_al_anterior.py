"""El corte de nomina que absorbe al que no se pago (seccion 105)

Decision 11 de Salvador (29 sep): un corte listo que no se paga sigue a
la vista hasta pagarse, y si llega al lunes siguiente, el corte nuevo se
lo lleva entero y sale un corte de dos semanas (se van juntando).

  - `estatusnomina` gana `ABSORBIDA`: el corte que otro se llevo. No se
    paga ni se tira.
  - `nomina_semanal.desde`: desde que lunes cubre el corte. Para los que
    ya existen es su propio `fecha_corte`.
  - `nomina_semanal.absorbida_por_id`: quien se lo llevo.
  - `concepto_nomina.semana_origen`: de que corte venia cada renglon
    heredado, para que el recibo diga "semana del 21".

Revision ID: c1e3a5b7d9f1
Revises: e7a9c1d3f5b7
Create Date: 2026-09-29
"""
import sqlalchemy as sa
from alembic import op

revision = "c1e3a5b7d9f1"
down_revision = "e7a9c1d3f5b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Un valor nuevo de un ENUM no entra dentro de la transaccion de la
    # migracion: va aparte, como el de las alertas del GPS.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE estatusnomina ADD VALUE IF NOT EXISTS "
                   "'ABSORBIDA'")

    # `desde` es obligatoria: se agrega vacia, se rellena con el propio
    # lunes de cada corte y entonces se exige.
    op.add_column("nomina_semanal",
                  sa.Column("desde", sa.Date(), nullable=True))
    op.execute("UPDATE nomina_semanal SET desde = fecha_corte")
    op.alter_column("nomina_semanal", "desde", nullable=False)
    op.add_column("nomina_semanal",
                  sa.Column("absorbida_por_id", sa.Integer(),
                            sa.ForeignKey("nomina_semanal.id"),
                            nullable=True))
    op.add_column("concepto_nomina",
                  sa.Column("semana_origen", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("concepto_nomina", "semana_origen")
    op.drop_column("nomina_semanal", "absorbida_por_id")
    op.drop_column("nomina_semanal", "desde")
    # Postgres no deja quitar un valor de un enum: los cortes absorbidos
    # vuelven a `CALCULADA`, que es de donde salieron, y el valor se
    # queda en el tipo sin nadie que lo use.
    op.execute("UPDATE nomina_semanal SET estatus = 'CALCULADA' "
               "WHERE estatus = 'ABSORBIDA'")

"""Cada dia pagado guarda con que rol se pago

Revision ID: d15a83c6e074
Revises: c92e40b7a531
"""
from alembic import op
import sqlalchemy as sa


revision = "d15a83c6e074"
down_revision = "c92e40b7a531"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """De donde salio el monto de ese dia.

    Desde que el rol es de la tarea, la comision de una jornada depende
    del rol con el que fue la persona: el mismo agente cobra distinto si
    el martes condujo y el miercoles coordino. El recibo tiene que poder
    decirlo, y el corte tiene que poder sumarse por rol.

    Se congela aqui y no se lee de la asignacion al momento de mirar el
    recibo, porque el rol de la asignacion se puede corregir despues y
    entonces el recibo de una semana ya pagada cambiaria solo.
    """
    op.add_column("concepto_nomina",
                  sa.Column("rol_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_concepto_nomina_rol", "concepto_nomina",
                          "perfil_personal", ["rol_id"], ["id"])

    # Lo que ya se pago se rellena con el rol que hoy tiene su jornada.
    # Es lo mas cercano a la verdad que existe; no hay otra fuente.
    op.execute("""
        UPDATE concepto_nomina AS c
        SET rol_id = a.rol_id
        FROM renglon_nomina AS r, asignacion_personal AS a
        WHERE c.renglon_id = r.id
          AND a.jornada_id = c.jornada_id
          AND a.persona_id = r.persona_id
          AND c.jornada_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_constraint("fk_concepto_nomina_rol", "concepto_nomina",
                       type_="foreignkey")
    op.drop_column("concepto_nomina", "rol_id")

"""Tabulador de viaticos aparte para eventual y para implantado

Revision ID: f47b1a6cd903
Revises: e5c908b71d24
Create Date: 2026-09-13

No es la misma operacion. El eventual es un dia suelto que muchas veces
arranca en un aeropuerto y termina en otra ciudad; el implantado es la
misma persona en el mismo lugar todos los dias del mes. Con una sola
tabla, un concepto significaba dos cosas segun quien lo leyera.

Lo que ya existe se marca como eventual, que es lo que era, y se copia
tal cual a implantado para que ningun servicio implantado se quede sin
propuesta de un dia para otro. Los montos de implantado se ajustan
despues: la copia es un punto de partida, no una decision.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f47b1a6cd903"
down_revision = "e5c908b71d24"
branch_labels = None
depends_on = None


def upgrade():
    # El tipo ya existe en la base desde el esquema inicial: se nombra,
    # no se recrea.
    tipo = postgresql.ENUM(name="tiposervicio", create_type=False)
    op.add_column("tabulador_viatico", sa.Column(
        "tipo_servicio", tipo, nullable=False, server_default="EVENTUAL"))

    op.execute("ALTER TABLE tabulador_viatico DROP CONSTRAINT IF EXISTS "
               "tabulador_viatico_pais_id_concepto_escenario_key")
    op.create_unique_constraint(
        "uq_tabulador_pais_tipo_concepto_escenario", "tabulador_viatico",
        ["pais_id", "tipo_servicio", "concepto", "escenario"])

    # La copia para implantado, con todo y el activo que traiga cada fila.
    op.execute("""
        INSERT INTO tabulador_viatico
            (pais_id, tipo_servicio, concepto, escenario, monto,
             monto_abierto, activo)
        SELECT pais_id, 'IMPLANTADO', concepto, escenario, monto,
               monto_abierto, activo
        FROM tabulador_viatico
        WHERE tipo_servicio = 'EVENTUAL'
    """)


def downgrade():
    op.execute("DELETE FROM tabulador_viatico WHERE tipo_servicio = 'IMPLANTADO'")
    op.drop_constraint("uq_tabulador_pais_tipo_concepto_escenario",
                       "tabulador_viatico", type_="unique")
    op.create_unique_constraint(
        "tabulador_viatico_pais_id_concepto_escenario_key",
        "tabulador_viatico", ["pais_id", "concepto", "escenario"])
    op.drop_column("tabulador_viatico", "tipo_servicio")

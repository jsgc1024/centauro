"""La comision se separa por tipo de servicio

Revision ID: e26b47f0a318
Revises: d15a83c6e074
"""
from alembic import op
import sqlalchemy as sa


revision = "e26b47f0a318"
down_revision = "d15a83c6e074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Un dia de eventual y un dia de implantado no se pagan igual.

    El tabulador de viaticos ya llevaba tabla aparte por tipo de
    servicio; el de comisiones no, y eso obligaba a que un mismo numero
    valiera para las dos operaciones. No son la misma: el eventual es un
    dia suelto que puede arrancar en un aeropuerto y terminar en otra
    ciudad, y el implantado es la misma persona en el mismo lugar todos
    los dias del mes.

    Lo que ya existia se queda como eventual y se copia a implantado con
    los mismos montos: asi nada cambia de precio el dia de la migracion,
    y de ahi en adelante cada tabla se ajusta por su lado.
    """
    op.add_column(
        "comision_personal",
        sa.Column("tipo_servicio",
                  sa.Enum("EVENTUAL", "IMPLANTADO", name="tiposervicio",
                          create_type=False),
                  nullable=False, server_default="EVENTUAL"))

    op.drop_constraint("comision_personal_pais_id_perfil_id_modalidad_id_key",
                       "comision_personal", type_="unique")
    op.create_unique_constraint(
        "uq_comision_pais_tipo_perfil_modalidad", "comision_personal",
        ["pais_id", "tipo_servicio", "perfil_id", "modalidad_id"])

    # La copia para implantado, con los mismos montos.
    op.execute("""
        INSERT INTO comision_personal
            (pais_id, tipo_servicio, perfil_id, modalidad_id, monto,
             monto_hora_extra, moneda)
        SELECT pais_id, 'IMPLANTADO', perfil_id, modalidad_id, monto,
               monto_hora_extra, moneda
        FROM comision_personal
        WHERE tipo_servicio = 'EVENTUAL'
    """)


def downgrade() -> None:
    op.execute("DELETE FROM comision_personal WHERE tipo_servicio = 'IMPLANTADO'")
    op.drop_constraint("uq_comision_pais_tipo_perfil_modalidad",
                       "comision_personal", type_="unique")
    op.create_unique_constraint(
        "comision_personal_pais_id_perfil_id_modalidad_id_key",
        "comision_personal", ["pais_id", "perfil_id", "modalidad_id"])
    op.drop_column("comision_personal", "tipo_servicio")

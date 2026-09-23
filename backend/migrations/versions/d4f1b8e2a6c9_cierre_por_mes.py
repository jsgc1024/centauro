"""El cierre por mes del implantado.

Sesion 2 del cierre en dos relojes (PROPUESTA_CIERRE_24H.md, regla 8;
seccion 56 de la bitacora). El cierre deja de ser uno por servicio: uno
por servicio en el eventual y uno por mes de contrato en el implantado.
La comision del consultor, igual: la del implantado es por mes.

La regla del eventual no se afloja: sigue habiendo a lo mas un cierre y
una comision por servicio cuando no son de un mes, ahora como indice
parcial en lugar de la restriccion de columna.

Revision ID: d4f1b8e2a6c9
Revises: c3e9a5d1f7b2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4f1b8e2a6c9"
down_revision: Union[str, None] = "c3e9a5d1f7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _quitar_unica(tabla: str, columnas: list) -> None:
    """Quita la restriccion unica de esas columnas, se llame como se llame.

    Se crearon sin nombre, asi que el nombre lo puso Postgres; se busca
    por las columnas para no depender de como lo haya escrito.
    """
    nombre = op.get_bind().execute(sa.text(
        "SELECT c.conname FROM pg_constraint c "
        "JOIN pg_class t ON t.oid = c.conrelid "
        "WHERE t.relname = :tabla AND c.contype = 'u' "
        "AND ARRAY(SELECT a.attname::text FROM unnest(c.conkey) AS k(n) "
        "          JOIN pg_attribute a "
        "            ON a.attrelid = t.oid AND a.attnum = k.n "
        "          ORDER BY 1) = CAST(:columnas AS text[])"),
        {"tabla": tabla, "columnas": sorted(columnas)}).scalar()
    if nombre:
        op.drop_constraint(nombre, tabla, type_="unique")


def upgrade() -> None:
    # El cierre: el mes de contrato, en el implantado.
    op.add_column("cierre", sa.Column("contrato_id", sa.Integer(),
                                      nullable=True))
    op.create_foreign_key("cierre_contrato_id_fkey", "cierre",
                          "contrato_implantado", ["contrato_id"], ["id"])
    op.create_unique_constraint("cierre_contrato_id_key", "cierre",
                                ["contrato_id"])
    _quitar_unica("cierre", ["servicio_id"])
    op.create_index("uq_cierre_del_eventual", "cierre", ["servicio_id"],
                    unique=True,
                    postgresql_where=sa.text("contrato_id IS NULL"))

    # La comision del consultor: la del implantado es por mes.
    op.add_column("comision_consultor", sa.Column("contrato_id",
                                                  sa.Integer(),
                                                  nullable=True))
    op.create_foreign_key("comision_consultor_contrato_id_fkey",
                          "comision_consultor", "contrato_implantado",
                          ["contrato_id"], ["id"])
    _quitar_unica("comision_consultor", ["servicio_id", "consultor_id"])
    op.create_index("uq_comision_del_servicio", "comision_consultor",
                    ["servicio_id", "consultor_id"], unique=True,
                    postgresql_where=sa.text("contrato_id IS NULL"))
    op.create_index("uq_comision_del_mes", "comision_consultor",
                    ["contrato_id", "consultor_id"], unique=True,
                    postgresql_where=sa.text("contrato_id IS NOT NULL"))


def downgrade() -> None:
    # Lo que era de un mes no cabe en la regla de antes: se va.
    op.drop_index("uq_comision_del_mes", table_name="comision_consultor")
    op.drop_index("uq_comision_del_servicio", table_name="comision_consultor")
    op.execute("DELETE FROM comision_consultor WHERE contrato_id IS NOT NULL")
    op.drop_column("comision_consultor", "contrato_id")
    op.create_unique_constraint(
        "comision_consultor_servicio_id_consultor_id_key",
        "comision_consultor", ["servicio_id", "consultor_id"])

    op.drop_index("uq_cierre_del_eventual", table_name="cierre")
    op.execute("DELETE FROM desviacion WHERE cierre_id IN "
               "(SELECT id FROM cierre WHERE contrato_id IS NOT NULL)")
    op.execute("DELETE FROM cierre WHERE contrato_id IS NOT NULL")
    op.drop_column("cierre", "contrato_id")
    op.create_unique_constraint("cierre_servicio_id_key", "cierre",
                                ["servicio_id"])

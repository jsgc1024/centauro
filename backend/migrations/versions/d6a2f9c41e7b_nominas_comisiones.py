"""Nominas: el corte del lunes y las comisiones de los consultores.

Decisiones de Salvador, 25 de septiembre (seccion 66 de la bitacora):

* El corte del personal se arma solo el lunes a las 7:00 y a las 11:00
  queda listo para pagar (`nomina_semanal.lista_en`); desde ahi no se
  recalcula. `calculada_por_id` dice quien lo armo; vacio es el reloj.
* Nadie cobra en negativo: si una diferencia se come lo de la semana, la
  persona queda en cero con un renglon marcado (`concepto_nomina.
  saldo_en_contra`) y lo que falta pasa al lunes siguiente. El concepto
  guarda tambien cuanto de su monto son horas extra.
* La comision del consultor se paga con un corte mensual por pais
  (`corte_comision`, `pago_comision`): direccion de operaciones da el
  visto bueno y finanzas registra cada pago con su referencia.
* `ajuste_comision` deja de ser solo la factura que no se cobro: lleva
  su clase (`tipo`), su pais, su servicio, quien la capturo y el corte
  que la llevo. La que ya existia es de la clase de siempre.

Revision ID: d6a2f9c41e7b
Revises: c3e7a1f94b2d
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6a2f9c41e7b"
down_revision: Union[str, None] = "c3e7a1f94b2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "corte_comision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pais_id", sa.Integer(), sa.ForeignKey("pais.id"),
                  nullable=False),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("estatus", sa.String(length=20), nullable=False),
        sa.Column("autorizado_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id"), nullable=True),
        sa.Column("autorizado_en", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("pagado_en", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("pais_id", "anio", "mes"),
    )
    op.create_table(
        "pago_comision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("corte_id", sa.Integer(),
                  sa.ForeignKey("corte_comision.id"), nullable=False),
        sa.Column("consultor_id", sa.Integer(), sa.ForeignKey("persona.id"),
                  nullable=False),
        sa.Column("moneda", sa.String(length=3), nullable=False),
        sa.Column("se_paga", sa.Numeric(12, 2), nullable=False),
        sa.Column("diferencias", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("saldo_en_contra", sa.Numeric(12, 2), nullable=False),
        sa.Column("referencia", sa.String(length=120), nullable=True),
        sa.Column("pagado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pagado_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id"), nullable=True),
        sa.UniqueConstraint("corte_id", "consultor_id", "moneda"),
    )

    op.add_column("comision_consultor",
                  sa.Column("corte_id", sa.Integer(),
                            sa.ForeignKey("corte_comision.id"),
                            nullable=True))

    op.alter_column("ajuste_comision", "comision_id",
                    existing_type=sa.Integer(), nullable=True)
    op.add_column("ajuste_comision",
                  sa.Column("tipo", sa.String(length=30),
                            server_default="no_cobrada", nullable=False))
    op.add_column("ajuste_comision",
                  sa.Column("pais_id", sa.Integer(),
                            sa.ForeignKey("pais.id"), nullable=True))
    op.add_column("ajuste_comision",
                  sa.Column("servicio_id", sa.Integer(),
                            sa.ForeignKey("servicio.id"), nullable=True))
    op.add_column("ajuste_comision",
                  sa.Column("creado_por_id", sa.Integer(),
                            sa.ForeignKey("persona.id"), nullable=True))
    op.add_column("ajuste_comision",
                  sa.Column("corte_id", sa.Integer(),
                            sa.ForeignKey("corte_comision.id"),
                            nullable=True))
    # Las que ya existian: su pais y su servicio salen de su comision.
    op.execute("""
        UPDATE ajuste_comision a
           SET servicio_id = c.servicio_id,
               pais_id = s.pais_id
          FROM comision_consultor c
          JOIN servicio s ON s.id = c.servicio_id
         WHERE a.comision_id = c.id
    """)

    op.add_column("nomina_semanal",
                  sa.Column("lista_en", sa.DateTime(), nullable=True))
    op.add_column("nomina_semanal",
                  sa.Column("calculada_por_id", sa.Integer(),
                            sa.ForeignKey("persona.id"), nullable=True))

    op.add_column("concepto_nomina",
                  sa.Column("monto_horas_extra", sa.Numeric(12, 2),
                            nullable=True))
    op.add_column("concepto_nomina",
                  sa.Column("saldo_en_contra", sa.Boolean(),
                            server_default=sa.text("false"), nullable=False))


def downgrade() -> None:
    op.drop_column("concepto_nomina", "saldo_en_contra")
    op.drop_column("concepto_nomina", "monto_horas_extra")
    op.drop_column("nomina_semanal", "calculada_por_id")
    op.drop_column("nomina_semanal", "lista_en")
    op.drop_column("ajuste_comision", "corte_id")
    op.drop_column("ajuste_comision", "creado_por_id")
    op.drop_column("ajuste_comision", "servicio_id")
    op.drop_column("ajuste_comision", "pais_id")
    op.drop_column("ajuste_comision", "tipo")
    # Las que no cuelgan de una comision no caben en el esquema de antes.
    op.execute("DELETE FROM ajuste_comision WHERE comision_id IS NULL")
    op.alter_column("ajuste_comision", "comision_id",
                    existing_type=sa.Integer(), nullable=False)
    op.drop_column("comision_consultor", "corte_id")
    op.drop_table("pago_comision")
    op.drop_table("corte_comision")

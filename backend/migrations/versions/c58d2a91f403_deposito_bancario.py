"""El deposito bancario

Finanzas paga un deposito por persona y equipo, pero el sistema solo
tenia una solicitud por jornada: la pantalla las agrupaba al vuelo y
eso que de verdad sale del banco --una transferencia, con su referencia
y su comprobante-- no existia en ninguna tabla. Por eso no habia a que
colgarle la evidencia.

Aqui nace. Las solicitudes cuelgan de el, asi que el comprobante se
guarda UNA vez por deposito y no una por dia: con cuatro dias eran 1.2
MB de la misma imagen repetida dentro de la base.

Se rellena hacia atras: por cada grupo de solicitudes ya confirmadas con
la misma persona y equipo se crea su deposito, con la referencia, la
fecha y quien la despacho que ya tenian. Nada de lo que esta pagado se
pierde ni cambia de sentido.

Y de paso los datos bancarios en `persona`. Vienen de Odoo, como el
telefono y la foto; mientras esa conexion no exista finanzas los puede
llenar, y el dia que Odoo conecte, Odoo manda.

Revision ID: c58d2a91f403
Revises: b2f47c10d938
"""
import sqlalchemy as sa
from alembic import op

revision = "c58d2a91f403"
down_revision = "b2f47c10d938"
branch_labels = None
depends_on = None

MONEDA = sa.Enum("MXN", "BRL", "USD", "VES", name="moneda", create_type=False)


def upgrade() -> None:
    op.create_table(
        "deposito_bancario",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("persona_id", sa.Integer(), nullable=False),
        # De que equipo son los dias que cubre. Un deposito por persona y
        # equipo: asi cada transferencia queda amarrada a un servicio y
        # su rentabilidad cuadra sola.
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("moneda", MONEDA, nullable=False),
        # El folio del banco: SPEI, clave de rastreo, lo que entregue.
        sa.Column("referencia", sa.String(120), nullable=True),
        # La captura del banco, dentro del registro. Como el resto de las
        # imagenes del sistema: una hoja que se imprime o se manda por
        # correo no puede depender de que cargue un enlace.
        sa.Column("comprobante", sa.Text(), nullable=True),
        # Naive: hora de pared del pais del servicio, como todas las
        # columnas de operacion (ver app/reloj.py).
        sa.Column("depositado_en", sa.DateTime(), nullable=True),
        sa.Column("despachado_por_id", sa.Integer(), nullable=True),
        # Quien corrigio la evidencia y cuando. Subir el archivo correcto
        # es lo mas comun que pasa despues, y sin esto no queda rastro.
        sa.Column("corregido_en", sa.DateTime(), nullable=True),
        sa.Column("corregido_por_id", sa.Integer(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["persona_id"], ["persona.id"]),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipo.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["despachado_por_id"], ["persona.id"]),
        sa.ForeignKeyConstraint(["corregido_por_id"], ["persona.id"]),
    )
    op.create_index("ix_deposito_persona", "deposito_bancario", ["persona_id"])
    op.create_index("ix_deposito_equipo", "deposito_bancario", ["equipo_id"])

    op.add_column("solicitud_transferencia",
                  sa.Column("deposito_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_solicitud_deposito", "solicitud_transferencia",
                          "deposito_bancario", ["deposito_id"], ["id"],
                          ondelete="SET NULL")

    # ---- el relleno hacia atras
    #
    # Un deposito por cada grupo de solicitudes confirmadas de la misma
    # persona en el mismo equipo. Se conserva lo que ya tenian: la
    # referencia, cuando se confirmo y quien la despacho. Sin comprobante,
    # porque nunca hubo forma de subirlo.
    op.execute("""
        INSERT INTO deposito_bancario
            (persona_id, equipo_id, monto, moneda, referencia,
             depositado_en, despachado_por_id, creado_en)
        SELECT v.persona_id,
               j.equipo_id,
               SUM(s.monto),
               MIN(s.moneda),
               MIN(s.referencia_odoo),
               MIN(s.confirmada_en),
               MIN(s.confirmada_por_id),
               now()
          FROM solicitud_transferencia s
          JOIN asignacion_viatico v ON v.id = s.asignacion_id
          JOIN jornada j            ON j.id = v.jornada_id
         WHERE s.estatus = 'CONFIRMADA'
         GROUP BY v.persona_id, j.equipo_id
    """)
    op.execute("""
        UPDATE solicitud_transferencia s
           SET deposito_id = d.id
          FROM asignacion_viatico v, jornada j, deposito_bancario d
         WHERE v.id = s.asignacion_id
           AND j.id = v.jornada_id
           AND d.persona_id = v.persona_id
           AND d.equipo_id  = j.equipo_id
           AND s.estatus = 'CONFIRMADA'
    """)

    # ---- los datos bancarios, que vienen de Odoo
    op.add_column("persona", sa.Column("banco", sa.String(80), nullable=True))
    op.add_column("persona", sa.Column("clabe", sa.String(40), nullable=True))
    op.add_column("persona",
                  sa.Column("titular_cuenta", sa.String(160), nullable=True))


def downgrade() -> None:
    op.drop_column("persona", "titular_cuenta")
    op.drop_column("persona", "clabe")
    op.drop_column("persona", "banco")
    op.drop_constraint("fk_solicitud_deposito", "solicitud_transferencia",
                       type_="foreignkey")
    op.drop_column("solicitud_transferencia", "deposito_id")
    op.drop_index("ix_deposito_equipo", table_name="deposito_bancario")
    op.drop_index("ix_deposito_persona", table_name="deposito_bancario")
    op.drop_table("deposito_bancario")

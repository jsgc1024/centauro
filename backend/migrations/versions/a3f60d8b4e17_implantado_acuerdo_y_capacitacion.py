"""Lo que le faltaba al implantado: acuerdo, capacitacion y cambios con fin

Revision ID: a3f60d8b4e17
Revises: f5d2091ac8b4
Create Date: 2026-09-14

Tres cosas.

El acuerdo del servicio —que cubre, que no, hasta donde llega, donde se
presenta el equipo y con quien se reporta— vive aparte del contrato
mensual, porque el contrato es el mes que se factura y esto es el trato.
Repetirlo en cada mes serian doce copias de lo mismo.

La capacitacion del personal, con vigencia: en un implantado el cliente
recibe a la misma persona todos los dias y pregunta quien es.

Y el cambio de recurso ahora puede tener fin. "De ahi en adelante" es
como se resuelve una contingencia; unas vacaciones se acaban y la unidad
sale del taller, y decirlo evita que el titular regrese y nadie se
acuerde de devolverle sus dias.
"""
import sqlalchemy as sa
from alembic import op

revision = "a3f60d8b4e17"
down_revision = "f5d2091ac8b4"
branch_labels = None
depends_on = None

MOTIVOS = ("VACACIONES", "ENFERMEDAD", "DESCANSO", "CONTINGENCIA", "BAJA",
           "MANTENIMIENTO_PREVENTIVO", "MANTENIMIENTO_CORRECTIVO", "OTRO")


def upgrade():
    motivo = sa.Enum(*MOTIVOS, name="motivocambio")
    motivo.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "acuerdo_implantado",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("servicio_id", sa.Integer(), nullable=False),
        sa.Column("cubre", sa.Text(), nullable=True),
        sa.Column("no_cubre", sa.Text(), nullable=True),
        sa.Column("zona_operacion", sa.String(length=300), nullable=True),
        sa.Column("dias_semana", sa.String(length=80), nullable=True),
        sa.Column("origen_direccion", sa.String(length=300), nullable=True),
        sa.Column("origen_lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("origen_lon", sa.Numeric(10, 7), nullable=True),
        sa.Column("geocerca_metros", sa.Integer(), nullable=False,
                  server_default="500"),
        sa.Column("reporta_a_nombre", sa.String(length=160), nullable=True),
        sa.Column("reporta_a_telefono", sa.String(length=40), nullable=True),
        sa.Column("reporta_a_correo", sa.String(length=160), nullable=True),
        sa.Column("protocolo_contacto", sa.Text(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["servicio_id"], ["servicio.id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("servicio_id"),
    )

    op.create_table(
        "capacitacion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("persona_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("institucion", sa.String(length=160), nullable=True),
        sa.Column("obtenida_en", sa.Date(), nullable=True),
        sa.Column("vigencia_hasta", sa.Date(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False,
                  server_default="true"),
        sa.ForeignKeyConstraint(["persona_id"], ["persona.id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_capacitacion_persona", "capacitacion", ["persona_id"])

    op.add_column("reemplazo_recurso", sa.Column(
        "hasta_jornada_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_reemplazo_hasta", "reemplazo_recurso",
                          "jornada", ["hasta_jornada_id"], ["id"])
    op.add_column("reemplazo_recurso", sa.Column(
        "motivo_tipo", motivo, nullable=True))

    op.add_column("contrato_implantado", sa.Column(
        "desde_dia", sa.Integer(), nullable=True))

    # La plantilla del mes: cualquier combinacion de gente y unidades,
    # con quien maneja cada una. Antes cabia una sola persona en el
    # contrato y el resto se inventaba a mano cada dia.
    op.create_table(
        "persona_implantado",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contrato_id", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.Integer(), nullable=False),
        sa.Column("vehiculo_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["contrato_id"], ["contrato_implantado.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["persona_id"], ["persona.id"]),
        sa.ForeignKeyConstraint(["vehiculo_id"], ["vehiculo.id"],
                                ondelete="SET NULL"),
        sa.UniqueConstraint("contrato_id", "persona_id"),
    )
    op.create_index("ix_persona_implantado_contrato", "persona_implantado",
                    ["contrato_id"])

    op.create_table(
        "unidad_implantado",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contrato_id", sa.Integer(), nullable=False),
        sa.Column("vehiculo_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["contrato_id"], ["contrato_implantado.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehiculo_id"], ["vehiculo.id"]),
        sa.UniqueConstraint("contrato_id", "vehiculo_id"),
    )
    op.create_index("ix_unidad_implantado_contrato", "unidad_implantado",
                    ["contrato_id"])

    # Los contratos que ya existian se pasan a la plantilla con lo que
    # tenian: su titular y su unidad.
    op.execute("""
        INSERT INTO persona_implantado (contrato_id, persona_id, vehiculo_id)
        SELECT id, titular_id, vehiculo_id FROM contrato_implantado
        WHERE titular_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO unidad_implantado (contrato_id, vehiculo_id)
        SELECT id, vehiculo_id FROM contrato_implantado
        WHERE vehiculo_id IS NOT NULL
    """)


def downgrade():
    op.drop_index("ix_unidad_implantado_contrato",
                  table_name="unidad_implantado")
    op.drop_table("unidad_implantado")
    op.drop_index("ix_persona_implantado_contrato",
                  table_name="persona_implantado")
    op.drop_table("persona_implantado")
    op.drop_column("contrato_implantado", "desde_dia")
    op.drop_column("reemplazo_recurso", "motivo_tipo")
    op.drop_constraint("fk_reemplazo_hasta", "reemplazo_recurso",
                       type_="foreignkey")
    op.drop_column("reemplazo_recurso", "hasta_jornada_id")
    op.drop_index("ix_capacitacion_persona", table_name="capacitacion")
    op.drop_table("capacitacion")
    op.drop_table("acuerdo_implantado")
    sa.Enum(name="motivocambio").drop(op.get_bind(), checkfirst=True)

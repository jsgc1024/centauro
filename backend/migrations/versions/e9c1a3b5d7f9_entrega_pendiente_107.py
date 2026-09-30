"""La entrega de la unidad como proceso aparte del fin del dia

Seccion 107, decision de Salvador (30 sep). El fin del dia es cuando el
ejecutivo corta --"hasta aqui me dejas"-- y ahi se cierran las horas.
Llevar la camioneta a la oficina y entregarla con sus cinco fotos es
otro proceso, que pasa despues y tiene su propio plazo: 24 horas desde
el fin, las mismas que los viaticos. Hasta la seccion 106 la entrega
era un candado en el fin del dia (18 sep): sin entrega no habia fin, y
eso obligaba a marcar el fin desde la oficina o a topar con el rechazo
con el cliente en el coche.

Una tabla nueva, `entrega_pendiente`: nace con el fin del dia para cada
unidad que ese dia deja el servicio sin revision de entrega, se cierra
con la revision, y si nadie la hace queda escrito quien la dio por
entregada sin revision y por que. Lo que ya existe no cambia.

Revision ID: e9c1a3b5d7f9
Revises: d7f9a1b3c5e7
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op

revision = "e9c1a3b5d7f9"
down_revision = "d7f9a1b3c5e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entrega_pendiente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("servicio_id", sa.Integer(),
                  sa.ForeignKey("servicio.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("vehiculo_id", sa.Integer(), sa.ForeignKey("vehiculo.id"),
                  nullable=False),
        sa.Column("jornada_id", sa.Integer(),
                  sa.ForeignKey("jornada.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("persona_id", sa.Integer(), sa.ForeignKey("persona.id"),
                  nullable=False),
        sa.Column("abierta_en", sa.DateTime(), nullable=False),
        sa.Column("vence_en", sa.DateTime(), nullable=False),
        sa.Column("aviso_vencido_en", sa.DateTime(), nullable=True),
        sa.Column("cerrada_en", sa.DateTime(), nullable=True),
        sa.Column("revision_id", sa.Integer(),
                  sa.ForeignKey("revision_unidad.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("sin_revision", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("justificacion", sa.Text(), nullable=True),
        sa.Column("justificada_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id"), nullable=True),
        sa.UniqueConstraint("servicio_id", "vehiculo_id",
                            name="uq_entrega_pendiente_unidad"),
    )
    op.create_index("ix_entrega_pendiente_servicio_id", "entrega_pendiente",
                    ["servicio_id"])
    op.create_index("ix_entrega_pendiente_vehiculo_id", "entrega_pendiente",
                    ["vehiculo_id"])
    op.create_index("ix_entrega_pendiente_jornada_id", "entrega_pendiente",
                    ["jornada_id"])
    op.create_index("ix_entrega_pendiente_persona_id", "entrega_pendiente",
                    ["persona_id"])


def downgrade() -> None:
    op.drop_index("ix_entrega_pendiente_persona_id",
                  table_name="entrega_pendiente")
    op.drop_index("ix_entrega_pendiente_jornada_id",
                  table_name="entrega_pendiente")
    op.drop_index("ix_entrega_pendiente_vehiculo_id",
                  table_name="entrega_pendiente")
    op.drop_index("ix_entrega_pendiente_servicio_id",
                  table_name="entrega_pendiente")
    op.drop_table("entrega_pendiente")

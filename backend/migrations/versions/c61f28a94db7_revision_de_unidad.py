"""La unidad se revisa cuando cambia de manos

Revision ID: c61f28a94db7
Revises: b58d30f4a916
"""
from alembic import op
import sqlalchemy as sa


revision = "c61f28a94db7"
down_revision = "b58d30f4a916"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """El dano al vehiculo siempre aparece despues y sin dueno.

    Un golpe que nadie vio al recibir la unidad es un golpe que se
    discute tres semanas despues, sin forma de saber quien la traia. Se
    resuelve con cuatro fotos y una firma en el momento en que la unidad
    cambia de manos, que es el unico momento en que todavia se puede
    saber.

    Las fotos llevan hora y ubicacion, igual que los hitos: una foto sin
    cuando ni donde no prueba nada.
    """
    op.create_table(
        "revision_unidad",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("servicio_id", sa.Integer(), nullable=False),
        sa.Column("vehiculo_id", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.Integer(), nullable=False),
        # recibe: la unidad pasa a manos del equipo
        # entrega: el equipo la devuelve
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("kilometraje", sa.Integer(), nullable=True),
        # El tanque como se lee en el tablero: octavos, de 0 a 8.
        sa.Column("combustible_octavos", sa.Integer(), nullable=True),
        sa.Column("nota", sa.Text(), nullable=True),
        sa.Column("firma", sa.Text(), nullable=True),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lon", sa.Numeric(10, 7), nullable=True),
        sa.Column("momento", sa.DateTime(), nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["servicio_id"], ["servicio.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehiculo_id"], ["vehiculo.id"]),
        sa.ForeignKeyConstraint(["persona_id"], ["persona.id"]),
        sa.PrimaryKeyConstraint("id"),
        # Una por servicio, unidad y momento: recibir dos veces la misma
        # camioneta en el mismo servicio es una correccion, no dos
        # entregas, y se resuelve borrando la primera.
        sa.UniqueConstraint("servicio_id", "vehiculo_id", "tipo",
                            name="uq_revision_servicio_unidad_tipo"),
    )
    op.create_index("ix_revision_unidad_vehiculo", "revision_unidad",
                    ["vehiculo_id"])
    op.create_index("ix_revision_unidad_servicio", "revision_unidad",
                    ["servicio_id"])

    op.create_table(
        "foto_revision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        # frente, atras, izquierdo, derecho, dano
        sa.Column("angulo", sa.String(12), nullable=False),
        sa.Column("imagen", sa.Text(), nullable=False),
        sa.Column("nota", sa.String(200), nullable=True),
        sa.Column("momento", sa.DateTime(), nullable=True),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lon", sa.Numeric(10, 7), nullable=True),
        sa.ForeignKeyConstraint(["revision_id"], ["revision_unidad.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_foto_revision_revision", "foto_revision",
                    ["revision_id"])


def downgrade() -> None:
    op.drop_table("foto_revision")
    op.drop_table("revision_unidad")

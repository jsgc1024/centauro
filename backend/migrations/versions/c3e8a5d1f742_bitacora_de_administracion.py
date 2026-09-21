"""Bitacora de lo que no pasa sobre un servicio

La bitacora que existia --`registro_accion`-- tiene `servicio_id`
obligatorio: esta amarrada a un servicio por diseno. Un cambio de acceso
no tiene servicio al cual colgarse, y tampoco un cambio de tarifario.

Por eso cerrarle la puerta a alguien, cambiarle el puesto o mover un
precio no dejaban rastro de quien lo hizo. El primero no se podia hacer
siquiera; los otros dos si, y en silencio.

Revision ID: c3e8a5d1f742
Revises: b7f21c4e9a03
"""
import sqlalchemy as sa
from alembic import op

revision = "c3e8a5d1f742"
down_revision = "b7f21c4e9a03"
branch_labels = None
depends_on = None

ROL = sa.Enum("personal_seguridad", "central", "consultor",
              "director_operaciones", "director_general", "finanzas", "admin",
              name="rol", create_type=False)


def upgrade() -> None:
    op.create_table(
        "registro_admin",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.Integer(), nullable=True),
        sa.Column("rol", ROL, nullable=False),
        sa.Column("accion", sa.String(80), nullable=False),
        sa.Column("objeto", sa.String(40), nullable=False),
        sa.Column("objeto_id", sa.Integer(), nullable=True),
        sa.Column("antes", sa.String(200), nullable=True),
        sa.Column("despues", sa.String(200), nullable=True),
        sa.Column("detalle", sa.String(400), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["persona_id"], ["persona.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_registro_admin_objeto", "registro_admin", ["objeto"])


def downgrade() -> None:
    op.drop_index("ix_registro_admin_objeto", table_name="registro_admin")
    op.drop_table("registro_admin")

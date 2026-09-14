"""Repara la plantilla del implantado si falta en la base

Revision ID: b2e47a05c918
Revises: f1c85b3e60d4
"""
from alembic import op
import sqlalchemy as sa

revision = "b2e47a05c918"
down_revision = "f1c85b3e60d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crea persona_implantado y unidad_implantado si no estan.

    Las creo la migracion del acuerdo, pero una base de desarrollo puede
    haberse quedado sin ellas —se sembro con create_all y despues se
    marco al dia, o una migracion se corto a medias—. Esto lo arregla sin
    tocar la base que si las tiene: se revisa antes de crear.

    En una base sana no hace nada. Esa es la idea.
    """
    tablas = set(sa.inspect(op.get_bind()).get_table_names())

    if "persona_implantado" not in tablas:
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
        # Los contratos que ya existian pasan a la plantilla con lo que
        # tenian: su titular y su unidad.
        op.execute("""
            INSERT INTO persona_implantado (contrato_id, persona_id, vehiculo_id)
            SELECT id, titular_id, vehiculo_id FROM contrato_implantado
            WHERE titular_id IS NOT NULL
        """)

    if "unidad_implantado" not in tablas:
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
        op.execute("""
            INSERT INTO unidad_implantado (contrato_id, vehiculo_id)
            SELECT id, vehiculo_id FROM contrato_implantado
            WHERE vehiculo_id IS NOT NULL
        """)


def downgrade() -> None:
    """No borra nada: estas tablas son de la migracion del acuerdo, y
    quitarlas aqui se llevaria lo que aquella creo."""

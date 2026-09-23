"""El personal de seguridad, leido de Odoo.

Centauro lee de Odoo al personal de seguridad (seccion 51 de la
bitacora): cuatro columnas en la persona --referencia, fecha de ingreso,
cuando se leyo de Odoo y cuando Odoo la dio de baja--, la foto pasa a
texto largo porque llega como data URI, un tipo de alerta nuevo para la
central y la tabla donde queda cada lectura.

Revision ID: b7d2f4a9c1e3
Revises: a1c4e7b9d2f6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2f4a9c1e3"
down_revision: Union[str, None] = "a1c4e7b9d2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("persona", "foto_url", type_=sa.Text(),
                    existing_type=sa.String(length=400), existing_nullable=True)
    op.add_column("persona", sa.Column("referencia", sa.String(length=40),
                                       nullable=True))
    op.create_index("ix_persona_referencia", "persona", ["referencia"])
    op.add_column("persona", sa.Column("fecha_ingreso", sa.Date(),
                                       nullable=True))
    op.add_column("persona", sa.Column("odoo_sincronizado_en", sa.DateTime(),
                                       nullable=True))
    op.add_column("persona", sa.Column("baja_odoo_en", sa.DateTime(),
                                       nullable=True))
    op.execute("ALTER TYPE tipoalerta ADD VALUE IF NOT EXISTS "
               "'PERSONAL_DE_BAJA' AFTER 'VEHICULO_SIN_ASIGNAR'")
    op.create_table(
        "sincronizacion_odoo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("hecha_en", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("automatica", sa.Boolean(), server_default="false",
                  nullable=False),
        sa.Column("hecha_por_id", sa.Integer(), sa.ForeignKey("persona.id"),
                  nullable=True),
        sa.Column("leidos", sa.Integer(), server_default="0", nullable=False),
        sa.Column("altas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cambios", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bajas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pendientes", sa.Integer(), server_default="0",
                  nullable=False),
        sa.Column("detalle", sa.Text(), nullable=True),
    )
    op.create_index("ix_sincronizacion_odoo_tipo", "sincronizacion_odoo",
                    ["tipo"])


def downgrade() -> None:
    op.drop_index("ix_sincronizacion_odoo_tipo",
                  table_name="sincronizacion_odoo")
    op.drop_table("sincronizacion_odoo")
    # Postgres no deja quitar un valor de un enum: las alertas de baja se
    # borran y el valor se queda en el tipo, sin uso.
    op.execute("DELETE FROM alerta WHERE tipo = 'PERSONAL_DE_BAJA'")
    op.drop_column("persona", "baja_odoo_en")
    op.drop_column("persona", "odoo_sincronizado_en")
    op.drop_column("persona", "fecha_ingreso")
    op.drop_index("ix_persona_referencia", table_name="persona")
    op.drop_column("persona", "referencia")
    # Una foto de Odoo no cabe en 400 caracteres: se quitan antes de
    # regresar la columna a su tamano.
    op.execute("UPDATE persona SET foto_url = NULL "
               "WHERE length(foto_url) > 400")
    op.alter_column("persona", "foto_url", type_=sa.String(length=400),
                    existing_type=sa.Text(), existing_nullable=True)

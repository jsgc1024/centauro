"""Reportar una falla (seccion 92)

El caso resuelto aprende a nacer como reporte: quien lo reporto y cuando,
lo que esperaba, lo que se manda solo --la pantalla, el servicio, la
version, el navegador o el telefono y lo ultimo que le salio--, la
captura, y su estado: por revisar, con Claude o resuelto. Los casos que
ya existen se anotaron a mano y quedan resueltos.

Revision ID: 4b7d2e9a1c63
Revises: 9c2e5a7b41d8
"""
import sqlalchemy as sa
from alembic import op

revision = "4b7d2e9a1c63"
down_revision = "9c2e5a7b41d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("caso_resuelto", sa.Column(
        "estado", sa.String(length=12), server_default="resuelto",
        nullable=False))
    op.add_column("caso_resuelto", sa.Column(
        "reportado_por_id", sa.Integer(), nullable=True))
    op.add_column("caso_resuelto", sa.Column(
        "reportado_en", sa.DateTime(timezone=True), nullable=True))
    op.add_column("caso_resuelto", sa.Column("esperaba", sa.Text(), nullable=True))
    op.add_column("caso_resuelto", sa.Column("contexto", sa.Text(), nullable=True))
    op.add_column("caso_resuelto", sa.Column("captura", sa.Text(), nullable=True))
    op.add_column("caso_resuelto", sa.Column(
        "con_claude_en", sa.DateTime(timezone=True), nullable=True))
    op.add_column("caso_resuelto", sa.Column(
        "resuelto_por_id", sa.Integer(), nullable=True))
    op.add_column("caso_resuelto", sa.Column(
        "resuelto_en", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_caso_reportado_por", "caso_resuelto", "persona",
                          ["reportado_por_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_caso_resuelto_por", "caso_resuelto", "persona",
                          ["resuelto_por_id"], ["id"], ondelete="SET NULL")
    # Los reportes abiertos se buscan por estado y por quien los mando.
    op.create_index("ix_caso_resuelto_estado", "caso_resuelto", ["estado"])
    op.create_index("ix_caso_resuelto_reportado", "caso_resuelto",
                    ["reportado_por_id", "reportado_en"])


def downgrade() -> None:
    op.drop_index("ix_caso_resuelto_reportado", table_name="caso_resuelto")
    op.drop_index("ix_caso_resuelto_estado", table_name="caso_resuelto")
    op.drop_constraint("fk_caso_resuelto_por", "caso_resuelto", type_="foreignkey")
    op.drop_constraint("fk_caso_reportado_por", "caso_resuelto", type_="foreignkey")
    for columna in ("resuelto_en", "resuelto_por_id", "con_claude_en", "captura",
                    "contexto", "esperaba", "reportado_en", "reportado_por_id",
                    "estado"):
        op.drop_column("caso_resuelto", columna)

"""Categorias de acceso: un puesto configurable

Hasta hoy lo que alguien podia tocar salia de su rol, escrito en el
codigo. Una categoria es un puesto que se arma desde el panel: que
actividades trae y cuanto dura su sesion.

La regla que decidio la direccion: **las categorias quitan, las
excepciones solo dan**. Si alguien no debe poder algo, se le hace una
categoria que no lo traiga --"Consultor junior"-- y su renglon dice la
verdad. Una excepcion que quitara dejaria el renglon diciendo "Consultor"
cuando no lo es.

Nadie nace con categoria: `usuario.categoria_id` vacio cae en los
permisos de su rol, que es como funcionaba el sistema hasta ahora. Por
eso aplicar esta migracion no le cambia nada a nadie.

Revision ID: f0c47a2e5b91
Revises: e1a742c9b366
"""
import sqlalchemy as sa
from alembic import op

revision = "f0c47a2e5b91"
down_revision = "e1a742c9b366"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categoria_acceso",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("descripcion", sa.String(300), nullable=True),
        sa.Column("horas_sesion", sa.Integer(), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )
    op.create_table(
        "actividad_de_categoria",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("categoria_id", sa.Integer(), nullable=False),
        sa.Column("actividad", sa.String(60), nullable=False),
        sa.ForeignKeyConstraint(["categoria_id"], ["categoria_acceso.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("categoria_id", "actividad"),
    )
    op.create_index("ix_actividad_de_categoria_actividad",
                    "actividad_de_categoria", ["actividad"])
    op.create_table(
        "permiso_extra",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("actividad", sa.String(60), nullable=False),
        sa.Column("dado_por_id", sa.Integer(), nullable=True),
        sa.Column("motivo", sa.String(300), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dado_por_id"], ["persona.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "actividad"),
    )
    op.add_column("usuario",
                  sa.Column("categoria_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_usuario_categoria", "usuario",
                          "categoria_acceso", ["categoria_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_usuario_categoria", "usuario", type_="foreignkey")
    op.drop_column("usuario", "categoria_id")
    op.drop_table("permiso_extra")
    op.drop_index("ix_actividad_de_categoria_actividad",
                  table_name="actividad_de_categoria")
    op.drop_table("actividad_de_categoria")
    op.drop_table("categoria_acceso")

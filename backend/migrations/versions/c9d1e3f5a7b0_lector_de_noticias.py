"""El lector de noticias y redes de la Central de Inteligencia (seccion 140)

Sus fuentes, las notas que lee, los hallazgos que arma para el analista
y el tope de X. Siembra la primera lista de fuentes.

Revision ID: c9d1e3f5a7b0
Revises: b5e7c9a1d3f2
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "c9d1e3f5a7b0"
down_revision = "b5e7c9a1d3f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuente_lector",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("direccion", sa.String(600), nullable=False),
        sa.Column("regiones", sa.Text(), server_default="[]",
                  nullable=False),
        sa.Column("oficial", sa.Boolean(), server_default="false",
                  nullable=False),
        sa.Column("cada_min", sa.Integer(), server_default="15",
                  nullable=False),
        sa.Column("activa", sa.Boolean(), server_default="true",
                  nullable=False),
        sa.Column("leida_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("desde_id", sa.String(40), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("error_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creada_por_id", sa.Integer(),
                  sa.ForeignKey("usuario.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("creada_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "hallazgo_lector",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pais_id", sa.Integer(), sa.ForeignKey("pais.id"),
                  nullable=False),
        sa.Column("estado", sa.String(20), server_default="por_revisar",
                  nullable=False),
        sa.Column("titulo", sa.String(300), nullable=False),
        sa.Column("resumen", sa.Text(), server_default="", nullable=False),
        sa.Column("tipo_id", sa.Integer(),
                  sa.ForeignKey("tipo_evento.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("region.id"),
                  nullable=True),
        sa.Column("municipio_id", sa.Integer(),
                  sa.ForeignKey("municipio.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("lugar", sa.String(300), nullable=True),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lon", sa.Numeric(10, 7), nullable=True),
        sa.Column("nivel", sa.Integer(), nullable=True),
        sa.Column("razon", sa.String(300), nullable=True),
        sa.Column("ocurrio_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sigue", sa.Boolean(), nullable=True),
        sa.Column("con_ia", sa.Boolean(), server_default="false",
                  nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("revisado_por_id", sa.Integer(),
                  sa.ForeignKey("usuario.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("revisado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo", sa.String(40), nullable=True),
        sa.Column("evento_id", sa.Integer(),
                  sa.ForeignKey("evento_riesgo.id", ondelete="SET NULL"),
                  nullable=True),
    )
    op.create_index("ix_hallazgo_lector_estado", "hallazgo_lector",
                    ["estado"])
    op.create_table(
        "nota_lector",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fuente_id", sa.Integer(),
                  sa.ForeignKey("fuente_lector.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("huella", sa.String(64), nullable=False, unique=True),
        sa.Column("url", sa.String(600), nullable=True),
        sa.Column("titulo", sa.String(400), nullable=False),
        sa.Column("texto", sa.Text(), server_default="", nullable=False),
        sa.Column("medio", sa.String(120), nullable=True),
        sa.Column("publicada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leida_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("estado", sa.String(20), server_default="nueva",
                  nullable=False),
        sa.Column("hallazgo_id", sa.Integer(),
                  sa.ForeignKey("hallazgo_lector.id", ondelete="SET NULL"),
                  nullable=True),
    )
    op.create_index("ix_nota_lector_fuente_id", "nota_lector", ["fuente_id"])
    op.create_index("ix_nota_lector_leida_en", "nota_lector", ["leida_en"])
    op.create_index("ix_nota_lector_hallazgo_id", "nota_lector",
                    ["hallazgo_id"])
    op.create_table(
        "parametros_lector",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tope_x_dia", sa.Integer(), server_default="1500",
                  nullable=False),
        sa.Column("pausado", sa.Boolean(), server_default="false",
                  nullable=False),
    )

    # La primera lista de fuentes, para que la Central la revise.
    from app import lector_catalogo
    con = op.get_bind()
    regiones = dict(con.execute(sa.text(
        "SELECT r.nombre, r.id FROM region r JOIN pais p ON p.id = r.pais_id "
        "WHERE p.codigo = 'MX'")).fetchall())
    tabla = sa.table("fuente_lector", sa.column("tipo"), sa.column("nombre"),
                     sa.column("direccion"), sa.column("regiones"),
                     sa.column("cada_min"))
    filas = []
    for f in lector_catalogo.iniciales():
        ids = [regiones[n] for n in f["regiones"] if n in regiones]
        filas.append({"tipo": f["tipo"], "nombre": f["nombre"],
                      "direccion": f["direccion"],
                      "regiones": json.dumps(ids), "cada_min": f["cada_min"]})
    if filas:
        op.bulk_insert(tabla, filas)


def downgrade() -> None:
    op.drop_table("parametros_lector")
    op.drop_index("ix_nota_lector_hallazgo_id", table_name="nota_lector")
    op.drop_index("ix_nota_lector_leida_en", table_name="nota_lector")
    op.drop_index("ix_nota_lector_fuente_id", table_name="nota_lector")
    op.drop_table("nota_lector")
    op.drop_index("ix_hallazgo_lector_estado", table_name="hallazgo_lector")
    op.drop_table("hallazgo_lector")
    op.drop_table("fuente_lector")

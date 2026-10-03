"""El riesgo de fondo: el Nivel Centauro (seccion 138)

Los municipios de Mexico con su poblacion del CONAPO, lo que llega del
Secretariado y de las encuestas del INEGI, y el nivel de cada mes por
estado y por municipio, con su borrador, su ajuste y su publicacion.

Revision ID: b5e7c9a1d3f2
Revises: a8c3e1f5d7b2
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "b5e7c9a1d3f2"
down_revision = "a8c3e1f5d7b2"
branch_labels = None
depends_on = None


def _ahora():
    return sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "municipio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("region.id"),
                  nullable=False, index=True),
        sa.Column("clave", sa.Integer(), nullable=False, unique=True),
        sa.Column("nombre", sa.String(120), nullable=False))
    op.create_table(
        "poblacion_municipio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("municipio_id", sa.Integer(),
                  sa.ForeignKey("municipio.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("habitantes", sa.Integer(), nullable=False),
        sa.UniqueConstraint("municipio_id", "anio",
                            name="uq_poblacion_municipio"))
    op.create_table(
        "cifra_oficial",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fuente", sa.String(30), nullable=False),
        sa.Column("componente", sa.String(30), nullable=False),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("region.id"),
                  nullable=False, index=True),
        sa.Column("municipio_id", sa.Integer(),
                  sa.ForeignKey("municipio.id", ondelete="CASCADE"),
                  nullable=True, index=True),
        sa.Column("periodo", sa.Date(), nullable=False, index=True),
        sa.Column("valor", sa.Integer(), nullable=False),
        sa.UniqueConstraint("fuente", "componente", "region_id",
                            "municipio_id", "periodo",
                            name="uq_cifra_oficial"))
    op.create_table(
        "encuesta_valor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fuente", sa.String(30), nullable=False, index=True),
        sa.Column("periodo", sa.Date(), nullable=False),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("region.id"),
                  nullable=False, index=True),
        sa.Column("municipio_id", sa.Integer(),
                  sa.ForeignKey("municipio.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("etiqueta", sa.String(120), nullable=True),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False))
    op.create_table(
        "carga_fuente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fuente", sa.String(30), nullable=False, index=True),
        sa.Column("periodo", sa.Date(), nullable=False),
        sa.Column("origen", sa.String(12), nullable=False),
        sa.Column("archivo", sa.String(200), nullable=True),
        sa.Column("filas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("nota", sa.Text(), nullable=True),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuario.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("en", _ahora(), server_default=sa.func.now(),
                  nullable=False))
    op.create_table(
        "nivel_mes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pais_id", sa.Integer(), sa.ForeignKey("pais.id"),
                  nullable=False),
        sa.Column("periodo", sa.Date(), nullable=False),
        sa.Column("estado", sa.String(12), server_default="borrador",
                  nullable=False),
        sa.Column("calculado_en", _ahora(), nullable=False),
        sa.Column("resumen", sa.Text(), nullable=False),
        sa.Column("publicado_en", _ahora(), nullable=True),
        sa.Column("publicado_por_id", sa.Integer(),
                  sa.ForeignKey("usuario.id", ondelete="SET NULL"),
                  nullable=True),
        sa.UniqueConstraint("pais_id", "periodo", name="uq_nivel_mes"))
    op.create_table(
        "parametros_nivel",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pais_id", sa.Integer(), sa.ForeignKey("pais.id"),
                  nullable=False, unique=True),
        sa.Column("pesos", sa.Text(), nullable=False),
        sa.Column("cortes", sa.Text(), nullable=False),
        sa.Column("suavizado", sa.Integer(), server_default="50000",
                  nullable=False),
        sa.Column("referencia_id", sa.Integer(),
                  sa.ForeignKey("nivel_mes.id", ondelete="SET NULL"),
                  nullable=True))
    op.create_table(
        "nivel_lugar",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nivel_mes_id", sa.Integer(),
                  sa.ForeignKey("nivel_mes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("region.id"),
                  nullable=False),
        sa.Column("municipio_id", sa.Integer(),
                  sa.ForeignKey("municipio.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("calculado", sa.Numeric(6, 2), nullable=False),
        sa.Column("valor", sa.Numeric(6, 2), nullable=False),
        sa.Column("componentes", sa.Text(), nullable=False),
        sa.Column("sin_reporte", sa.Boolean(), server_default="false",
                  nullable=False),
        sa.Column("ajuste_motivo", sa.String(400), nullable=True),
        sa.Column("ajustado_por_id", sa.Integer(),
                  sa.ForeignKey("usuario.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("ajustado_en", _ahora(), nullable=True))
    op.create_index("ix_nivel_lugar_mes_region", "nivel_lugar",
                    ["nivel_mes_id", "region_id"])

    # Los municipios y su poblacion, del archivo del CONAPO del
    # repositorio; los pesos y cortes de arranque.
    from app import nivel_catalogo as nc
    con = op.get_bind()
    pais = con.execute(sa.text("SELECT id FROM pais WHERE codigo = 'MX'")
                       ).scalar()
    if pais is None:
        return
    con.execute(sa.text(
        "INSERT INTO parametros_nivel (pais_id, pesos, cortes) "
        "VALUES (:p, :pe, :co)"),
        {"p": pais, "pe": json.dumps(nc.PESOS_INICIALES),
         "co": json.dumps(nc.CORTES_INICIALES)})
    regiones = dict(con.execute(sa.text(
        "SELECT clave, id FROM region WHERE pais_id = :p"), {"p": pais}).all())
    for mun in nc.municipios():
        if mun["entidad"] not in regiones:
            continue
        mid = con.execute(sa.text(
            "INSERT INTO municipio (region_id, clave, nombre) "
            "VALUES (:r, :c, :n) RETURNING id"),
            {"r": regiones[mun["entidad"]], "c": mun["clave"],
             "n": mun["nombre"]}).scalar()
        for anio, n in mun["poblacion"].items():
            con.execute(sa.text(
                "INSERT INTO poblacion_municipio (municipio_id, anio, "
                "habitantes) VALUES (:m, :a, :h)"),
                {"m": mid, "a": anio, "h": n})


def downgrade() -> None:
    op.drop_index("ix_nivel_lugar_mes_region", table_name="nivel_lugar")
    op.drop_table("nivel_lugar")
    op.drop_table("parametros_nivel")
    op.drop_table("nivel_mes")
    op.drop_table("carga_fuente")
    op.drop_table("encuesta_valor")
    op.drop_table("cifra_oficial")
    op.drop_table("poblacion_municipio")
    op.drop_table("municipio")

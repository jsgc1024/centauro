"""El mapa de riesgo de la Central de Inteligencia (seccion 133)

La segunda linea de operacion de Connect, AI/CI. Su pieza es el evento
de riesgo: algo que paso en un lugar y a una hora, con su nivel (1 a 4),
su vigencia, sus fuentes y su bitacora. Llegan tambien los estados de
Mexico y Brasil --la zona que sigue cada cliente-- y los tipos de evento
de la cifra negra de la central, con sus definiciones.

Los puestos que ya existen toman sus actividades: la central captura y
publica, el supervisor de central (jefe de turno) confirma el nivel 4.

Revision ID: c1a7e5d3b9f0
Revises: d4e8f0a3b2c5
"""
import sqlalchemy as sa
from alembic import op

revision = "c1a7e5d3b9f0"
down_revision = "d4e8f0a3b2c5"
branch_labels = None
depends_on = None

ESTADO = sa.Enum("PROPUESTO", "POR_CONFIRMAR", "PUBLICADO", "CERRADO",
                 "DESCARTADO", name="estadoevento")
VERIFICACION = sa.Enum("SIN_CONFIRMAR", "CONFIRMADO", "OFICIAL",
                       name="verificacionevento")
TENDENCIA = sa.Enum("PERSISTENTE", "CRECIENTE", "DECRECIENTE",
                    name="tendenciaevento")

ACTIVIDADES = {
    "Dirección de operaciones": ["riesgo.ver", "riesgo.publicar",
                                 "riesgo.confirmar", "riesgo.catalogo"],
    "Supervisor de central": ["riesgo.ver", "riesgo.publicar",
                              "riesgo.confirmar"],
    "Monitorista": ["riesgo.ver", "riesgo.publicar"],
    "Administración del sistema y calidad": ["riesgo.catalogo"],
}


def _usuario_fk():
    return sa.ForeignKey("usuario.id", ondelete="SET NULL")


def upgrade() -> None:
    op.create_table(
        "region",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pais_id", sa.Integer(), sa.ForeignKey("pais.id"),
                  nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("clave", sa.String(4), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False,
                  server_default="true"),
        sa.UniqueConstraint("pais_id", "nombre", name="uq_region_pais_nombre"),
    )
    op.create_table(
        "tipo_evento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pais_id", sa.Integer(), sa.ForeignKey("pais.id"),
                  nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("definicion", sa.Text(), nullable=False,
                  server_default=""),
        sa.Column("radio_m", sa.Integer(), nullable=False,
                  server_default="2000"),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean(), nullable=False,
                  server_default="true"),
        sa.UniqueConstraint("pais_id", "nombre",
                            name="uq_tipo_evento_pais_nombre"),
    )
    op.create_table(
        "evento_riesgo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("folio", sa.String(16), nullable=False, unique=True),
        sa.Column("pais_id", sa.Integer(), sa.ForeignKey("pais.id"),
                  nullable=False),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("region.id"),
                  nullable=False),
        sa.Column("municipio", sa.String(120), nullable=True),
        sa.Column("tipo_id", sa.Integer(), sa.ForeignKey("tipo_evento.id"),
                  nullable=False),
        sa.Column("nivel", sa.Integer(), nullable=False),
        sa.Column("nivel_pendiente", sa.Integer(), nullable=True),
        sa.Column("titulo", sa.String(160), nullable=False),
        sa.Column("texto_cliente", sa.Text(), nullable=False,
                  server_default=""),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lon", sa.Numeric(10, 7), nullable=True),
        sa.Column("radio_m", sa.Integer(), nullable=True),
        sa.Column("lugar", sa.String(300), nullable=True),
        sa.Column("ocurrio_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vigente_hasta", sa.DateTime(timezone=True),
                  nullable=False),
        sa.Column("verificacion", VERIFICACION, nullable=False),
        sa.Column("tendencia", TENDENCIA, nullable=True),
        sa.Column("estado", ESTADO, nullable=False),
        sa.Column("origen", sa.String(12), nullable=False,
                  server_default="analista"),
        sa.Column("creado_por_id", sa.Integer(), _usuario_fk(),
                  nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("publicado_por_id", sa.Integer(), _usuario_fk(),
                  nullable=True),
        sa.Column("publicado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("critico_pedido_por_id", sa.Integer(), _usuario_fk(),
                  nullable=True),
        sa.Column("critico_confirmado_por_id", sa.Integer(), _usuario_fk(),
                  nullable=True),
        sa.Column("critico_confirmado_en", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("terminado_por_id", sa.Integer(), _usuario_fk(),
                  nullable=True),
        sa.Column("terminado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo", sa.String(400), nullable=True),
        sa.CheckConstraint("nivel BETWEEN 1 AND 4", name="ck_evento_nivel"),
        sa.CheckConstraint("nivel_pendiente IS NULL OR nivel_pendiente = 4",
                           name="ck_evento_nivel_pendiente"),
    )
    op.create_index("ix_evento_estado_vigencia", "evento_riesgo",
                    ["estado", "vigente_hasta"])
    op.create_table(
        "fuente_evento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evento_id", sa.Integer(),
                  sa.ForeignKey("evento_riesgo.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("url", sa.String(600), nullable=True),
        sa.Column("descripcion", sa.String(300), nullable=False),
        sa.Column("oficial", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("registrada_por_id", sa.Integer(), _usuario_fk(),
                  nullable=True),
        sa.Column("registrada_en", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fuente_evento_evento_id", "fuente_evento",
                    ["evento_id"])
    op.create_table(
        "cambio_evento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evento_id", sa.Integer(),
                  sa.ForeignKey("evento_riesgo.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("usuario_id", sa.Integer(), _usuario_fk(), nullable=True),
        sa.Column("quien", sa.String(160), nullable=False, server_default=""),
        sa.Column("accion", sa.String(40), nullable=False),
        sa.Column("detalle", sa.Text(), nullable=False, server_default=""),
        sa.Column("en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_cambio_evento_evento_id", "cambio_evento",
                    ["evento_id"])

    from app import riesgo_catalogo as cat

    con = op.get_bind()
    for codigo, regiones in cat.REGIONES.items():
        pais = con.execute(sa.text("SELECT id FROM pais WHERE codigo = :c"),
                           {"c": codigo}).first()
        if pais is None:
            continue
        for clave, nombre in regiones:
            con.execute(sa.text(
                "INSERT INTO region (pais_id, nombre, clave) "
                "VALUES (:p, :n, :c) ON CONFLICT DO NOTHING"),
                {"p": pais.id, "n": nombre, "c": clave})
    for codigo, tipos in cat.TIPOS.items():
        pais = con.execute(sa.text("SELECT id FROM pais WHERE codigo = :c"),
                           {"c": codigo}).first()
        if pais is None:
            continue
        for orden, (nombre, radio, definicion) in enumerate(tipos, 1):
            con.execute(sa.text(
                "INSERT INTO tipo_evento (pais_id, nombre, radio_m, "
                "definicion, orden) VALUES (:p, :n, :r, :d, :o) "
                "ON CONFLICT DO NOTHING"),
                {"p": pais.id, "n": nombre, "r": radio, "d": definicion,
                 "o": orden})

    # Los puestos que ya existen toman las actividades nuevas.
    for puesto, actividades in ACTIVIDADES.items():
        categoria = con.execute(sa.text(
            "SELECT id FROM categoria_acceso WHERE nombre = :n"),
            {"n": puesto}).first()
        if categoria is None:
            continue
        for actividad in actividades:
            con.execute(sa.text(
                "INSERT INTO actividad_de_categoria (categoria_id, actividad) "
                "SELECT CAST(:c AS INTEGER), CAST(:a AS VARCHAR(60)) "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM actividad_de_categoria "
                "  WHERE categoria_id = CAST(:c AS INTEGER) "
                "  AND actividad = CAST(:a AS VARCHAR(60)))"),
                {"c": categoria.id, "a": actividad})


def downgrade() -> None:
    con = op.get_bind()
    todas = sorted({a for lista in ACTIVIDADES.values() for a in lista})
    for actividad in todas:
        con.execute(sa.text(
            "DELETE FROM actividad_de_categoria WHERE actividad = :a"),
            {"a": actividad})
    op.drop_index("ix_cambio_evento_evento_id", table_name="cambio_evento")
    op.drop_table("cambio_evento")
    op.drop_index("ix_fuente_evento_evento_id", table_name="fuente_evento")
    op.drop_table("fuente_evento")
    op.drop_index("ix_evento_estado_vigencia", table_name="evento_riesgo")
    op.drop_table("evento_riesgo")
    op.drop_table("tipo_evento")
    op.drop_table("region")
    for enum in (ESTADO, VERIFICACION, TENDENCIA):
        enum.drop(con, checkfirst=True)

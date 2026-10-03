"""Los clientes de la Central y sus alertas (seccion 131)

El cliente de la Central es el de Odoo: aqui se marca que tiene el
servicio, que estados sigue y quien de su gente entra a su app. Su gente
tiene su propio acceso --no es personal de Centauro--, sus telefonos
suscritos y sus alertas, una por evento, persona y nivel.

Revision ID: d4b2f8e6a1c3
Revises: c1a7e5d3b9f0
"""
import sqlalchemy as sa
from alembic import op

revision = "d4b2f8e6a1c3"
down_revision = "c1a7e5d3b9f0"
branch_labels = None
depends_on = None

PERFIL = sa.Enum("GERENTE", "VIAJERO", "OPERADOR", name="perfilcliente")

ACTIVIDADES = {
    "Dirección de operaciones": ["riesgo.clientes"],
    "Administración del sistema y calidad": ["riesgo.clientes"],
}


def _usuario_fk():
    return sa.ForeignKey("usuario.id", ondelete="SET NULL")


def upgrade() -> None:
    # Un valor nuevo para el destinatario del correo. Va en su propio
    # bloque autocommit: Postgres no deja usar un valor de ENUM en la
    # misma transaccion que lo agrego.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE destinatario ADD VALUE IF NOT EXISTS "
                   "'CLIENTE_CI'")

    op.create_table(
        "cliente_central",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("cliente.id"),
                  nullable=False, unique=True),
        sa.Column("activo", sa.Boolean(), nullable=False,
                  server_default="true"),
        sa.Column("alta_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("alta_por_id", sa.Integer(), _usuario_fk(), nullable=True),
    )
    op.create_table(
        "zona_cliente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cliente_central_id", sa.Integer(),
                  sa.ForeignKey("cliente_central.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("region.id"),
                  nullable=False),
        sa.UniqueConstraint("cliente_central_id", "region_id",
                            name="uq_zona_cliente"),
    )
    op.create_index("ix_zona_cliente_cliente_central_id", "zona_cliente",
                    ["cliente_central_id"])
    op.create_table(
        "usuario_cliente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cliente_central_id", sa.Integer(),
                  sa.ForeignKey("cliente_central.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("apellidos", sa.String(120), nullable=False,
                  server_default=""),
        sa.Column("correo", sa.String(160), nullable=False),
        sa.Column("telefono", sa.String(40), nullable=True),
        sa.Column("perfil", PERFIL, nullable=False),
        sa.Column("idioma", sa.String(2), nullable=False,
                  server_default="es"),
        sa.Column("hash_contrasena", sa.String(200), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False,
                  server_default="true"),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("alta_por_usuario_id", sa.Integer(), _usuario_fk(),
                  nullable=True),
        sa.Column("alta_por_cliente_id", sa.Integer(),
                  sa.ForeignKey("usuario_cliente.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("ultimo_acceso", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("sesiones_desde", sa.DateTime(timezone=True),
                  nullable=True),
    )
    op.create_index("ix_usuario_cliente_correo", "usuario_cliente",
                    ["correo"], unique=True)
    op.create_index("ix_usuario_cliente_cliente_central_id",
                    "usuario_cliente", ["cliente_central_id"])
    op.create_table(
        "suscripcion_push_cliente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_cliente_id", sa.Integer(),
                  sa.ForeignKey("usuario_cliente.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("agente", sa.String(300), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False,
                  server_default="true"),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_suscripcion_push_cliente_usuario_cliente_id",
                    "suscripcion_push_cliente", ["usuario_cliente_id"])
    op.create_table(
        "alerta_cliente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evento_id", sa.Integer(),
                  sa.ForeignKey("evento_riesgo.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("usuario_cliente_id", sa.Integer(),
                  sa.ForeignKey("usuario_cliente.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("nivel", sa.Integer(), nullable=False),
        sa.Column("motivo", sa.String(8), nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("telefonos", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("correo_id", sa.Integer(),
                  sa.ForeignKey("notificacion.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("en_resumen", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("requiere_acuse", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("acuse_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("llamar_desde", sa.DateTime(timezone=True), nullable=True),
        sa.Column("llamada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("llamada_por_id", sa.Integer(), _usuario_fk(),
                  nullable=True),
        sa.Column("llamada_nota", sa.String(400), nullable=True),
        sa.UniqueConstraint("evento_id", "usuario_cliente_id", "nivel",
                            name="uq_alerta_cliente"),
    )
    op.create_index("ix_alerta_cliente_evento_id", "alerta_cliente",
                    ["evento_id"])
    op.create_index("ix_alerta_cliente_usuario_cliente_id", "alerta_cliente",
                    ["usuario_cliente_id"])

    con = op.get_bind()
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
    con.execute(sa.text("DELETE FROM actividad_de_categoria "
                        "WHERE actividad = 'riesgo.clientes'"))
    for tabla in ("alerta_cliente", "suscripcion_push_cliente",
                  "usuario_cliente", "zona_cliente", "cliente_central"):
        op.drop_table(tabla)
    PERFIL.drop(con, checkfirst=True)
    # El valor CLIENTE_CI del destinatario se queda: Postgres no quita
    # valores de un ENUM, y sin filas que lo usen no estorba.

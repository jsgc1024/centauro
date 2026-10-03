"""Respuesta a emergencias: su rol, su panel y el panico del cliente (seccion 145)

El area de guardia 24/7 que atiende los panicos: su rol y su puesto; el
canal del panico de la app del cliente de la Central; en la alerta, quien
la levanto desde esa app, su ultima ubicacion y lo que hizo el area; el
recorrido de quien pidio ayuda (`punto_alerta`) y la bitacora de cada
alerta (`nota_alerta`); el contacto de emergencia de cada cliente de la
Central. Direccion de operaciones, que es su respaldo, ve el panel.

Los valores de los enums se agregan fuera de la transaccion: Postgres no
deja usar un valor en la misma transaccion que lo agrego. Correrla dos
veces no duplica nada.

Revision ID: a5c7e9b1d3f6
Revises: f4b6d8f0a2c3
"""
import sqlalchemy as sa
from alembic import op

revision = "a5c7e9b1d3f6"
down_revision = "f4b6d8f0a2c3"
branch_labels = None
depends_on = None

# Lo mismo que dice `puestos_base`. Una prueba cuida que no se separen.
NOMBRE = "Respuesta a emergencias"
AREA = "Respuesta a emergencias"
DESCRIPCION = ("La guardia 24/7 que atiende los pánicos —del cliente de la "
               "Central, de la app de campo y de los vehículos—: los toma, "
               "manda al equipo de respuesta y los cierra con su "
               "resolución.")
PANTALLAS = "emergencias"
PUESTOS_ODOO = ("Respuesta a Emergencias, Operador de Respuesta a "
                "Emergencias, Operador de Emergencias")
ACTIVIDADES = ["emergencias.ver", "emergencias.atender"]


def _id_del_puesto(con):
    fila = con.execute(sa.text(
        "SELECT id FROM categoria_acceso WHERE nombre = :n"),
        {"n": NOMBRE}).first()
    return fila.id if fila else None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE rol ADD VALUE IF NOT EXISTS "
                   "'RESPUESTA_EMERGENCIAS'")
        op.execute("ALTER TYPE canalalerta ADD VALUE IF NOT EXISTS "
                   "'BOTON_CI'")

    con = op.get_bind()
    columnas = {c["name"] for c in sa.inspect(con).get_columns(
        "alerta_incidencia")}
    nuevas = [
        sa.Column("usuario_cliente_id", sa.Integer(),
                  sa.ForeignKey("usuario_cliente.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("precision_m", sa.Integer(), nullable=True),
        sa.Column("ubicacion_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("equipo_enviado_en", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("autoridades_en", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("dijo_error_en", sa.DateTime(timezone=True), nullable=True),
    ]
    for columna in nuevas:
        if columna.name not in columnas:
            op.add_column("alerta_incidencia", columna)
    if "usuario_cliente_id" not in columnas:
        op.create_index("ix_alerta_incidencia_usuario_cliente_id",
                        "alerta_incidencia", ["usuario_cliente_id"])

    op.create_table(
        "punto_alerta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alerta_id", sa.Integer(),
                  sa.ForeignKey("alerta_incidencia.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("lat", sa.Numeric(10, 7), nullable=False),
        sa.Column("lon", sa.Numeric(10, 7), nullable=False),
        sa.Column("precision_m", sa.Integer(), nullable=True),
        sa.Column("en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False))
    op.create_index("ix_punto_alerta_alerta_id", "punto_alerta",
                    ["alerta_id"])
    op.create_table(
        "nota_alerta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alerta_id", sa.Integer(),
                  sa.ForeignKey("alerta_incidencia.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuario.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("quien", sa.String(160), nullable=False),
        sa.Column("accion", sa.String(30), nullable=False),
        sa.Column("detalle", sa.String(600), server_default="",
                  nullable=False))
    op.create_index("ix_nota_alerta_alerta_id", "nota_alerta", ["alerta_id"])

    op.add_column("cliente_central",
                  sa.Column("contacto_emergencia", sa.String(120),
                            nullable=True))
    op.add_column("cliente_central",
                  sa.Column("telefono_emergencia", sa.String(40),
                            nullable=True))

    # El puesto del area, si no existe.
    if _id_del_puesto(con) is None:
        con.execute(sa.text(
            "INSERT INTO categoria_acceso "
            "(nombre, descripcion, activa, rol, area, pantallas, "
            "puestos_odoo, orden) VALUES (:n, :d, true, "
            "CAST('RESPUESTA_EMERGENCIAS' AS rol), :a, :p, :o, 35)"),
            {"n": NOMBRE, "d": DESCRIPCION, "a": AREA, "p": PANTALLAS,
             "o": PUESTOS_ODOO})
        categoria_id = _id_del_puesto(con)
        for actividad in ACTIVIDADES:
            con.execute(sa.text(
                "INSERT INTO actividad_de_categoria (categoria_id, actividad) "
                "VALUES (:c, :a)"), {"c": categoria_id, "a": actividad})

    # Direccion de operaciones, el respaldo: su puesto ve el panel. Solo
    # se agrega; al puesto que no dice sus pantallas no se le toca nada.
    for actividad in ACTIVIDADES:
        op.execute(f"""
            INSERT INTO actividad_de_categoria (categoria_id, actividad)
            SELECT c.id, '{actividad}' FROM categoria_acceso c
            WHERE c.rol::text = 'DIRECTOR_OPERACIONES'
              AND NOT EXISTS (SELECT 1 FROM actividad_de_categoria a
                              WHERE a.categoria_id = c.id
                                AND a.actividad = '{actividad}')""")
    op.execute("""
        UPDATE categoria_acceso c
        SET pantallas = c.pantallas || ',emergencias'
        WHERE c.rol::text = 'DIRECTOR_OPERACIONES'
          AND c.pantallas IS NOT NULL AND c.pantallas <> ''
          AND NOT ('emergencias' = ANY(string_to_array(c.pantallas, ',')))""")


def downgrade() -> None:
    """Las tablas se van con lo que guardaron. El puesto se quita y quien
    lo traiga vuelve a entrar con lo de su rol. Los valores de los enums
    se quedan: Postgres no los quita sin recrear el tipo. Los panicos del
    cliente de la Central se borran: el codigo de antes no sabe leer ese
    canal, y la central y el panorama tronarian al encontrarlos. Quien
    tenga el rol del area hay que pasarlo a otro rol a mano antes de
    bajar: el codigo de antes tampoco lo conoce."""
    con = op.get_bind()
    op.execute("DELETE FROM alerta_incidencia WHERE canal::text = 'BOTON_CI'")
    op.execute("""
        UPDATE categoria_acceso
        SET pantallas = NULLIF(array_to_string(
            array_remove(string_to_array(pantallas, ','), 'emergencias'),
            ','), '')
        WHERE pantallas IS NOT NULL
          AND 'emergencias' = ANY(string_to_array(pantallas, ','))""")
    op.execute("""
        DELETE FROM actividad_de_categoria
        WHERE actividad IN ('emergencias.ver', 'emergencias.atender')""")
    categoria_id = _id_del_puesto(con)
    if categoria_id is not None:
        con.execute(sa.text(
            "UPDATE usuario SET categoria_id = NULL WHERE categoria_id = :c"),
            {"c": categoria_id})
        con.execute(sa.text("DELETE FROM categoria_acceso WHERE id = :c"),
                    {"c": categoria_id})
    op.drop_column("cliente_central", "telefono_emergencia")
    op.drop_column("cliente_central", "contacto_emergencia")
    op.drop_index("ix_nota_alerta_alerta_id", table_name="nota_alerta")
    op.drop_table("nota_alerta")
    op.drop_index("ix_punto_alerta_alerta_id", table_name="punto_alerta")
    op.drop_table("punto_alerta")
    op.drop_index("ix_alerta_incidencia_usuario_cliente_id",
                  table_name="alerta_incidencia")
    for nombre in ("dijo_error_en", "autoridades_en", "equipo_enviado_en",
                   "ubicacion_en", "precision_m", "usuario_cliente_id"):
        op.drop_column("alerta_incidencia", nombre)

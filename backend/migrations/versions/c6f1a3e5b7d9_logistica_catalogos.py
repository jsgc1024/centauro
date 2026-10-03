"""Logistica, bloque 1: los catalogos con su fecha (seccion 150)

Lo que el margen, el anticipo y la nomina de cada viaje de Logistica van
a usar, capturado una vez y con su fecha: el tabulador de comisiones, el
diesel con su holgura y su tolerancia, los alimentos, el margen minimo,
el costo del operador, el rendimiento y el costo por dia de cada tipo de
unidad, el bono de movilidad y la garantia del tracto. Y lo que lleva
sistema y calidad: los tipos de unidad y los patios.

Decisiones de Salvador, 3 de octubre: lo que decide dinero lo fija Karla
Rios, la gerencia de Logistica --su rol y su puesto nacen aqui--; los
tipos de unidad y los patios los lleva sistema y calidad. Arranca solo
con los cuatro tipos de unidad y Base Cuautitlan, sin ubicacion todavia:
ningun monto se siembra, la pantalla dice que falta y de quien.

El rol se agrega fuera de la transaccion: Postgres no deja usar un valor
de enum en la misma transaccion que lo agrego, y el puesto de abajo entra
con el. Correrla dos veces no duplica nada.

Revision ID: c6f1a3e5b7d9
Revises: b5e7c9a1d3f2
"""
import sqlalchemy as sa
from alembic import op

revision = "c6f1a3e5b7d9"
down_revision = "b5e7c9a1d3f2"
branch_labels = None
depends_on = None

# Los mismos de `lg_catalogos.TIPOS_DE_ARRANQUE`: nombre, capacidad en
# toneladas y como se decia en Tango. Una prueba cuida que digan lo mismo.
TIPOS = [("1.5 ton", "1.5", "1.5 t"),
         ("4 ton", "4", "4 t seco"),
         ("Torton 15 ton", "15", "TH"),
         ("Tracto", None, "Tracto")]
PATIO = "Base Cuautitlán"
GEOCERCA = 300

NOMBRE = "Gerente de Logística"
DESCRIPCION = ("La gerencia de Centauro Logística: fija lo que decide el "
               "dinero de cada viaje —el tabulador de comisiones, el "
               "diésel, los alimentos, el margen mínimo y los costos— y "
               "autoriza lo que pide su firma.")
PANTALLAS = "lg_catalogos"
PUESTOS_ODOO = "Gerente de Logística, Gerente de Logistica"
ACTIVIDADES = ["lg.catalogos.ver", "lg.catalogos.dinero"]
# Sistema y calidad lleva los tipos de unidad y los patios, y ve lo demas.
A_SISTEMA = ("lg.catalogos.ver", "lg.catalogos.editar")


def _ahora():
    return sa.DateTime(timezone=True)


def _id_del_puesto(con):
    fila = con.execute(sa.text(
        "SELECT id FROM categoria_acceso WHERE nombre = :n"),
        {"n": NOMBRE}).first()
    return fila.id if fila else None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE rol ADD VALUE IF NOT EXISTS 'LOGISTICA'")

    op.create_table(
        "lg_tipo_unidad",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(60), nullable=False, unique=True),
        sa.Column("capacidad_ton", sa.Numeric(6, 2), nullable=True),
        sa.Column("nombre_tango", sa.String(60), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("creado_en", _ahora(), nullable=False,
                  server_default=sa.func.now()))
    op.create_table(
        "lg_patio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(80), nullable=False, unique=True),
        sa.Column("direccion", sa.String(300), nullable=True),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lon", sa.Numeric(10, 7), nullable=True),
        sa.Column("geocerca_metros", sa.Integer(), nullable=False,
                  server_default="300"),
        sa.Column("activo", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("creado_en", _ahora(), nullable=False,
                  server_default=sa.func.now()))
    op.create_table(
        "lg_valor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clave", sa.String(30), nullable=False),
        sa.Column("tipo_unidad_id", sa.Integer(),
                  sa.ForeignKey("lg_tipo_unidad.id"), nullable=True),
        sa.Column("valor", sa.Numeric(14, 4), nullable=True),
        sa.Column("datos", sa.Text(), nullable=True),
        sa.Column("vigente_desde", sa.Date(), nullable=False),
        sa.Column("motivo", sa.String(200), nullable=True),
        sa.Column("capturado_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id"), nullable=True),
        sa.Column("capturado_en", _ahora(), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("reemplazado_en", _ahora(), nullable=True),
        sa.Column("reemplazado_por_id", sa.Integer(),
                  sa.ForeignKey("lg_valor.id"), nullable=True),
        sa.Column("quitado_en", _ahora(), nullable=True),
        sa.Column("quitado_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id"), nullable=True))
    op.create_index("ix_lg_valor_vigencia", "lg_valor",
                    ["clave", "tipo_unidad_id", "vigente_desde"])

    con = op.get_bind()
    for orden, (nombre, capacidad, tango) in enumerate(TIPOS, 1):
        con.execute(sa.text(
            "INSERT INTO lg_tipo_unidad (nombre, capacidad_ton, nombre_tango, orden) "
            "SELECT CAST(:n AS VARCHAR(60)), CAST(:c AS NUMERIC(6, 2)), "
            "CAST(:t AS VARCHAR(60)), CAST(:o AS INTEGER) "
            "WHERE NOT EXISTS (SELECT 1 FROM lg_tipo_unidad "
            "WHERE nombre = CAST(:n AS VARCHAR(60)))"),
            {"n": nombre, "c": capacidad, "t": tango, "o": orden})
    con.execute(sa.text(
        "INSERT INTO lg_patio (nombre, geocerca_metros) "
        "SELECT CAST(:n AS VARCHAR(80)), CAST(:g AS INTEGER) "
        "WHERE NOT EXISTS (SELECT 1 FROM lg_patio "
        "WHERE nombre = CAST(:n AS VARCHAR(80)))"),
        {"n": PATIO, "g": GEOCERCA})

    # El puesto de la gerencia de Logistica, si no existe.
    if _id_del_puesto(con) is None:
        con.execute(sa.text(
            "INSERT INTO categoria_acceso "
            "(nombre, descripcion, activa, rol, area, pantallas, puestos_odoo, orden) "
            "VALUES (:n, :d, true, CAST('LOGISTICA' AS rol), :a, :p, :o, 15)"),
            {"n": NOMBRE, "d": DESCRIPCION, "a": "Logística",
             "p": PANTALLAS, "o": PUESTOS_ODOO})
        categoria_id = _id_del_puesto(con)
        for actividad in ACTIVIDADES:
            con.execute(sa.text(
                "INSERT INTO actividad_de_categoria (categoria_id, actividad) "
                "VALUES (:c, :a)"), {"c": categoria_id, "a": actividad})

    # Sistema y calidad: sus actividades y la pantalla en su menu. Solo se
    # agrega; al puesto que no dice sus pantallas no se le toca nada.
    for actividad in A_SISTEMA:
        op.execute(f"""
            INSERT INTO actividad_de_categoria (categoria_id, actividad)
            SELECT c.id, '{actividad}' FROM categoria_acceso c
            WHERE c.rol::text = 'SISTEMA_CALIDAD'
              AND NOT EXISTS (SELECT 1 FROM actividad_de_categoria a
                              WHERE a.categoria_id = c.id
                                AND a.actividad = '{actividad}')""")
    op.execute("""
        UPDATE categoria_acceso c
        SET pantallas = c.pantallas || ',lg_catalogos'
        WHERE c.rol::text = 'SISTEMA_CALIDAD'
          AND c.pantallas IS NOT NULL AND c.pantallas <> ''
          AND NOT ('lg_catalogos' = ANY(string_to_array(c.pantallas, ',')))""")


def downgrade() -> None:
    """Las tablas se van con lo capturado. El puesto se quita y quien lo
    traiga vuelve a entrar con lo de su rol. El valor del enum se queda:
    Postgres no quita valores sin recrear el tipo entero."""
    con = op.get_bind()
    op.execute("""
        UPDATE categoria_acceso
        SET pantallas = NULLIF(array_to_string(
            array_remove(string_to_array(pantallas, ','), 'lg_catalogos'), ','), '')
        WHERE pantallas IS NOT NULL
          AND 'lg_catalogos' = ANY(string_to_array(pantallas, ','))""")
    op.execute("""
        DELETE FROM actividad_de_categoria
        WHERE actividad IN ('lg.catalogos.ver', 'lg.catalogos.dinero',
                            'lg.catalogos.editar')""")
    categoria_id = _id_del_puesto(con)
    if categoria_id is not None:
        con.execute(sa.text(
            "UPDATE usuario SET categoria_id = NULL WHERE categoria_id = :c"),
            {"c": categoria_id})
        con.execute(sa.text("DELETE FROM categoria_acceso WHERE id = :c"),
                    {"c": categoria_id})
    op.drop_index("ix_lg_valor_vigencia", table_name="lg_valor")
    op.drop_table("lg_valor")
    op.drop_table("lg_patio")
    op.drop_table("lg_tipo_unidad")

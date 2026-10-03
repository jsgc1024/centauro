"""Logistica, bloque 2: la flota, los operadores y su jornada (seccion 151)

Las unidades y los operadores de la compania «Centauro Logistic» de Odoo,
cada uno en su tabla --si entraran a las de Proteccion Ejecutiva se
ofrecerian para sus servicios--: el expediente, el odometro, el plan
preventivo, los servicios, las llantas, el costo por dia con su fecha, la
marca de jornada en el patio y el acceso propio de los operadores a su
app, LG Connect.

Decisiones de Salvador, 3 de octubre: quien lleva la flota edita unidades,
documentos y servicios --su puesto nace aqui--; la gerencia de Logistica
ve todo, da el codigo de LG Connect y captura la licencia; la Central
valida las marcas fuera del patio (el monitorista no, como no corrige
hitos). Los tipos de unidad ganan sus llantas: 1.5 ton 4, 4 ton 6, torton
y tracto 10, sin la refaccion.

Correrla dos veces no duplica nada.

Revision ID: e2a4c6b8d0f1
Revises: f4b6d8f0a2c3
"""
import sqlalchemy as sa
from alembic import op

revision = "e2a4c6b8d0f1"
# Cuelga de la ultima del lector de la Central (seccion 144), que ya
# estaba en main cuando subio esta: una sola cabeza.
down_revision = "f4b6d8f0a2c3"
branch_labels = None
depends_on = None

# Las mismas de `lg_flota.LLANTAS_DE_ARRANQUE`. Una prueba cuida que digan
# lo mismo.
LLANTAS = {"1.5 ton": 4, "4 ton": 6, "Torton 15 ton": 10, "Tracto": 10}

GERENCIA = "Gerente de Logística"
A_GERENCIA = ("lg.flota.ver", "lg.jornada.ver", "lg.operadores.editar",
              "lg.en_viaje.marcar")
# Como se llama ese puesto en Odoo (la lectura de la compania 3 del 3 de
# octubre): «Jefatura Logística». Se agrega para que Accesos lo sugiera;
# solo si nadie le cambio lo que dejo la 150.
PUESTOS_ODOO_GERENCIA_150 = "Gerente de Logística, Gerente de Logistica"
PUESTOS_ODOO_GERENCIA = ("Gerente de Logística, Gerente de Logistica, "
                         "Jefatura Logística, Jefatura Logistica")
FLOTA = "Responsable de flota LG"
DESCRIPCION_FLOTA = ("Lleva la flota de Centauro Logística: cada unidad con su "
                     "expediente, su odómetro, su plan preventivo, sus servicios "
                     "y sus llantas, y el acceso de los operadores a LG Connect.")
A_FLOTA = ("lg.catalogos.ver", "lg.flota.ver", "lg.flota.editar", "lg.jornada.ver",
           "lg.operadores.editar", "lg.en_viaje.marcar")
PUESTOS_ODOO_FLOTA = "Responsable de Flota, Responsable de Flotillas"
A_SISTEMA = ("lg.flota.ver", "lg.jornada.ver")


def _hora():
    return sa.DateTime(timezone=True)


def _ahora():
    return sa.text("now()")


def _por(columna):
    return sa.Column(columna, sa.Integer, sa.ForeignKey("persona.id"), nullable=True)


def _id_de(con, nombre):
    fila = con.execute(sa.text("SELECT id FROM categoria_acceso WHERE nombre = :n"),
                       {"n": nombre}).first()
    return fila.id if fila else None


def _actividad(con, categoria_id, actividad):
    con.execute(sa.text(
        "INSERT INTO actividad_de_categoria (categoria_id, actividad) "
        "SELECT :c, CAST(:a AS VARCHAR) WHERE NOT EXISTS (SELECT 1 FROM "
        "actividad_de_categoria WHERE categoria_id = :c AND actividad = CAST(:a AS VARCHAR))"),
        {"c": categoria_id, "a": actividad})


def _pantalla(where_sql, pantalla):
    op.execute(f"""
        UPDATE categoria_acceso c
        SET pantallas = c.pantallas || ',{pantalla}'
        WHERE {where_sql}
          AND c.pantallas IS NOT NULL AND c.pantallas <> ''
          AND NOT ('{pantalla}' = ANY(string_to_array(c.pantallas, ',')))""")


def upgrade() -> None:
    con = op.get_bind()
    insp = sa.inspect(con)

    # Las llantas de cada tipo de unidad.
    columnas = {c["name"] for c in insp.get_columns("lg_tipo_unidad")}
    if "llantas" not in columnas:
        op.add_column("lg_tipo_unidad", sa.Column("llantas", sa.Integer, nullable=True))
    if "vida_llanta_km" not in columnas:
        op.add_column("lg_tipo_unidad", sa.Column("vida_llanta_km", sa.Integer,
                                                  nullable=True))
    for nombre, llantas in LLANTAS.items():
        con.execute(sa.text("UPDATE lg_tipo_unidad SET llantas = :l "
                            "WHERE nombre = :n AND llantas IS NULL"),
                    {"l": llantas, "n": nombre})

    tablas = set(insp.get_table_names())
    if "lg_unidad" not in tablas:
        op.create_table(
            "lg_unidad",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("odoo_id", sa.Integer, nullable=True, unique=True),
            sa.Column("placa", sa.String(20), nullable=False, index=True),
            sa.Column("clase", sa.String(12), nullable=False, server_default="unidad"),
            sa.Column("categoria_odoo", sa.String(80)),
            sa.Column("marca_modelo", sa.String(120)),
            sa.Column("anio", sa.Integer),
            sa.Column("chasis", sa.String(40)),
            sa.Column("iave", sa.String(40)),
            sa.Column("odoo_sincronizado_en", _hora()),
            sa.Column("baja_odoo_en", _hora()),
            sa.Column("numero_economico", sa.String(20)),
            sa.Column("economico_llave", sa.String(20), unique=True),
            sa.Column("tipo_id", sa.Integer, sa.ForeignKey("lg_tipo_unidad.id")),
            sa.Column("rendimiento_ref", sa.Numeric(6, 2)),
            sa.Column("odometro_km", sa.Integer),
            sa.Column("odometro_fecha", sa.Date),
            sa.Column("estado", sa.String(20), nullable=False, server_default="disponible"),
            sa.Column("estado_motivo", sa.String(300)),
            sa.Column("estado_desde", _hora()),
            sa.Column("estado_hasta", sa.Date),
            sa.Column("patio_id", sa.Integer, sa.ForeignKey("lg_patio.id")),
            sa.Column("valor_compra", sa.Numeric(14, 2)),
            sa.Column("anios_vida", sa.Numeric(5, 2)),
            sa.Column("seguro_anual", sa.Numeric(12, 2)),
            sa.Column("tenencia_anual", sa.Numeric(12, 2)),
            sa.Column("verificacion_anual", sa.Numeric(12, 2)),
            sa.Column("gps_anual", sa.Numeric(12, 2)),
            sa.Column("llantas_por_km", sa.Numeric(10, 4)),
            sa.Column("mantenimiento_anual", sa.Numeric(12, 2)),
            sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("creado_en", _hora(), nullable=False, server_default=_ahora()))
    if "lg_lectura_odometro" not in tablas:
        op.create_table(
            "lg_lectura_odometro",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("unidad_id", sa.Integer, sa.ForeignKey("lg_unidad.id"),
                      nullable=False, index=True),
            sa.Column("km", sa.Integer, nullable=False),
            sa.Column("fecha", sa.Date, nullable=False),
            sa.Column("fuente", sa.String(12), nullable=False, server_default="manual"),
            sa.Column("motivo", sa.String(300)),
            _por("registrado_por_id"),
            sa.Column("registrado_en", _hora(), nullable=False, server_default=_ahora()))
    if "lg_archivo" not in tablas:
        op.create_table(
            "lg_archivo",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("nombre", sa.String(200), nullable=False),
            sa.Column("tipo", sa.String(60), nullable=False),
            sa.Column("tamano", sa.Integer, nullable=False),
            sa.Column("md5", sa.String(32), nullable=False),
            sa.Column("contenido", sa.LargeBinary),
            sa.Column("objeto", sa.String(400)),
            _por("subido_por_id"),
            sa.Column("subido_en", _hora(), nullable=False, server_default=_ahora()))
    if "lg_operador" not in tablas:
        op.create_table(
            "lg_operador",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("odoo_id", sa.Integer, nullable=True, unique=True),
            sa.Column("nombre", sa.String(160), nullable=False),
            sa.Column("correo", sa.String(160), unique=True),
            sa.Column("telefono", sa.String(30)),
            sa.Column("puesto_odoo", sa.String(120)),
            sa.Column("fecha_ingreso", sa.Date),
            sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("odoo_sincronizado_en", _hora()),
            sa.Column("baja_odoo_en", _hora()),
            sa.Column("hash_contrasena", sa.String(200)),
            sa.Column("sesiones_desde", _hora()),
            sa.Column("ultimo_acceso", _hora()),
            sa.Column("idioma", sa.String(5), nullable=False, server_default="es"),
            sa.Column("creado_en", _hora(), nullable=False, server_default=_ahora()))
    if "lg_documento" not in tablas:
        op.create_table(
            "lg_documento",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("unidad_id", sa.Integer, sa.ForeignKey("lg_unidad.id"), index=True),
            sa.Column("operador_id", sa.Integer, sa.ForeignKey("lg_operador.id"),
                      index=True),
            sa.Column("tipo", sa.String(30), nullable=False),
            sa.Column("folio", sa.String(80)),
            sa.Column("detalle", sa.String(120)),
            sa.Column("vence_en", sa.Date),
            sa.Column("archivo_id", sa.Integer, sa.ForeignKey("lg_archivo.id")),
            _por("capturado_por_id"),
            sa.Column("capturado_en", _hora(), nullable=False, server_default=_ahora()),
            sa.Column("reemplazado_en", _hora()),
            sa.Column("aviso_previo_en", _hora()),
            sa.Column("aviso_vencido_en", _hora()),
            sa.CheckConstraint("(unidad_id IS NULL) <> (operador_id IS NULL)",
                               name="ck_lg_documento_de_quien"))
    if "lg_plan_servicio" not in tablas:
        op.create_table(
            "lg_plan_servicio",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tipo_id", sa.Integer, sa.ForeignKey("lg_tipo_unidad.id")),
            sa.Column("clase", sa.String(12), nullable=False, server_default="unidad"),
            sa.Column("nombre", sa.String(80), nullable=False),
            sa.Column("cada_km", sa.Integer, nullable=False),
            sa.Column("costo_aprox", sa.Numeric(12, 2)),
            sa.Column("orden", sa.Integer, nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("creado_en", _hora(), nullable=False, server_default=_ahora()))
    if "lg_servicio" not in tablas:
        op.create_table(
            "lg_servicio",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("unidad_id", sa.Integer, sa.ForeignKey("lg_unidad.id"),
                      nullable=False, index=True),
            sa.Column("plan_id", sa.Integer, sa.ForeignKey("lg_plan_servicio.id")),
            sa.Column("nombre", sa.String(120), nullable=False),
            sa.Column("fecha", sa.Date, nullable=False),
            sa.Column("km", sa.Integer),
            sa.Column("costo", sa.Numeric(12, 2), nullable=False),
            sa.Column("taller", sa.String(120)),
            sa.Column("factura", sa.String(60)),
            sa.Column("archivo_id", sa.Integer, sa.ForeignKey("lg_archivo.id")),
            _por("registrado_por_id"),
            sa.Column("registrado_en", _hora(), nullable=False, server_default=_ahora()),
            sa.Column("anulado_en", _hora()),
            sa.Column("anulado_motivo", sa.String(300)))
    if "lg_llanta" not in tablas:
        op.create_table(
            "lg_llanta",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("unidad_id", sa.Integer, sa.ForeignKey("lg_unidad.id"),
                      nullable=False, index=True),
            sa.Column("posicion", sa.String(8), nullable=False),
            sa.Column("instalada_km", sa.Integer, nullable=False),
            sa.Column("instalada_en", sa.Date, nullable=False),
            sa.Column("detalle", sa.String(120)),
            sa.Column("costo", sa.Numeric(12, 2)),
            sa.Column("retirada_km", sa.Integer),
            sa.Column("retirada_en", sa.Date),
            _por("registrado_por_id"),
            sa.Column("registrado_en", _hora(), nullable=False, server_default=_ahora()))
    if "lg_costo_dia" not in tablas:
        op.create_table(
            "lg_costo_dia",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("unidad_id", sa.Integer, sa.ForeignKey("lg_unidad.id"),
                      nullable=False),
            sa.Column("vigente_desde", sa.Date, nullable=False),
            sa.Column("total", sa.Numeric(12, 2), nullable=False),
            sa.Column("desglose", sa.Text, nullable=False),
            sa.Column("origen", sa.String(12), nullable=False),
            sa.Column("motivo", sa.String(300)),
            _por("creado_por_id"),
            sa.Column("creado_en", _hora(), nullable=False, server_default=_ahora()))
        op.create_index("ix_lg_costo_dia_vigencia", "lg_costo_dia",
                        ["unidad_id", "vigente_desde"])
    if "lg_viaje_manual" not in tablas:
        op.create_table(
            "lg_viaje_manual",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("operador_id", sa.Integer,
                      sa.ForeignKey("lg_operador.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("desde", sa.Date, nullable=False),
            sa.Column("hasta", sa.Date, nullable=False),
            _por("creado_por_id"),
            sa.Column("creado_en", _hora(), nullable=False, server_default=_ahora()),
            sa.Column("quitado_en", _hora()))
    if "lg_codigo_acceso" not in tablas:
        op.create_table(
            "lg_codigo_acceso",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("operador_id", sa.Integer,
                      sa.ForeignKey("lg_operador.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("hash", sa.String(200), nullable=False),
            sa.Column("expira_en", _hora(), nullable=False),
            sa.Column("fallos", sa.Integer, nullable=False, server_default="0"),
            sa.Column("usado_en", _hora()),
            sa.Column("anulado_en", _hora()),
            _por("dado_por_id"),
            sa.Column("creado_en", _hora(), nullable=False, server_default=_ahora()))
    if "lg_llave" not in tablas:
        op.create_table(
            "lg_llave",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("operador_id", sa.Integer,
                      sa.ForeignKey("lg_operador.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("credencial_id", sa.String(400), nullable=False, unique=True),
            sa.Column("llave_publica", sa.Text, nullable=False),
            sa.Column("contador", sa.Integer, nullable=False, server_default="0"),
            sa.Column("nombre", sa.String(120), nullable=False),
            sa.Column("creada_en", _hora(), nullable=False, server_default=_ahora()),
            sa.Column("usada_en", _hora()))
    if "lg_jornada" not in tablas:
        op.create_table(
            "lg_jornada",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("operador_id", sa.Integer, sa.ForeignKey("lg_operador.id"),
                      nullable=False, index=True),
            sa.Column("fecha", sa.Date, nullable=False, index=True),
            sa.Column("marcada_en", _hora(), nullable=False),
            sa.Column("lat", sa.Numeric(10, 7)),
            sa.Column("lon", sa.Numeric(10, 7)),
            sa.Column("precision_m", sa.Integer),
            sa.Column("patio_id", sa.Integer, sa.ForeignKey("lg_patio.id")),
            sa.Column("distancia_m", sa.Integer),
            sa.Column("dentro", sa.Boolean, nullable=False),
            sa.Column("nota", sa.String(200)),
            sa.Column("estado", sa.String(12), nullable=False),
            _por("revisada_por_id"),
            sa.Column("revisada_en", _hora()),
            sa.Column("justificacion", sa.String(300)),
            sa.UniqueConstraint("operador_id", "fecha"))

    # La gerencia de Logistica: ve la flota y la jornada, da el codigo y
    # captura la licencia, y marca el «en viaje» mientras siga Tango.
    gerencia = _id_de(con, GERENCIA)
    if gerencia is not None:
        for actividad in A_GERENCIA:
            _actividad(con, gerencia, actividad)
        for pantalla in ("lg_flota", "lg_jornada"):
            _pantalla(f"c.id = {int(gerencia)}", pantalla)
        con.execute(sa.text(
            "UPDATE categoria_acceso SET puestos_odoo = :nuevo "
            "WHERE id = :c AND puestos_odoo = :viejo"),
            {"nuevo": PUESTOS_ODOO_GERENCIA, "viejo": PUESTOS_ODOO_GERENCIA_150,
             "c": gerencia})

    # Quien lleva la flota: su puesto, si no existe.
    if _id_de(con, FLOTA) is None:
        con.execute(sa.text(
            "INSERT INTO categoria_acceso "
            "(nombre, descripcion, activa, rol, area, pantallas, puestos_odoo, orden) "
            "VALUES (:n, :d, true, CAST('LOGISTICA' AS rol), :a, :p, :o, 16)"),
            {"n": FLOTA, "d": DESCRIPCION_FLOTA, "a": "Logística",
             "p": "lg_catalogos,lg_flota,lg_jornada", "o": PUESTOS_ODOO_FLOTA})
        flota = _id_de(con, FLOTA)
        for actividad in A_FLOTA:
            _actividad(con, flota, actividad)

    # Sistema y calidad: ve la flota y la jornada.
    for actividad in A_SISTEMA:
        op.execute(f"""
            INSERT INTO actividad_de_categoria (categoria_id, actividad)
            SELECT c.id, '{actividad}' FROM categoria_acceso c
            WHERE c.rol::text = 'SISTEMA_CALIDAD'
              AND NOT EXISTS (SELECT 1 FROM actividad_de_categoria a
                              WHERE a.categoria_id = c.id AND a.actividad = '{actividad}')""")
    for pantalla in ("lg_flota", "lg_jornada"):
        _pantalla("c.rol::text = 'SISTEMA_CALIDAD'", pantalla)

    # La Central: ve la jornada; la valida quien corrige hitos (el
    # monitorista no).
    op.execute("""
        INSERT INTO actividad_de_categoria (categoria_id, actividad)
        SELECT c.id, 'lg.jornada.ver' FROM categoria_acceso c
        WHERE c.rol::text = 'CENTRAL'
          AND NOT EXISTS (SELECT 1 FROM actividad_de_categoria a
                          WHERE a.categoria_id = c.id AND a.actividad = 'lg.jornada.ver')""")
    op.execute("""
        INSERT INTO actividad_de_categoria (categoria_id, actividad)
        SELECT c.id, 'lg.jornada.validar' FROM categoria_acceso c
        WHERE c.rol::text = 'CENTRAL'
          AND EXISTS (SELECT 1 FROM actividad_de_categoria a
                      WHERE a.categoria_id = c.id AND a.actividad = 'operacion.corregir')
          AND NOT EXISTS (SELECT 1 FROM actividad_de_categoria a
                          WHERE a.categoria_id = c.id AND a.actividad = 'lg.jornada.validar')""")
    _pantalla("c.rol::text = 'CENTRAL'", "lg_jornada")


def downgrade() -> None:
    """Las tablas se van con lo capturado. El puesto de flota se quita y
    quien lo traiga vuelve a entrar con lo de su rol."""
    con = op.get_bind()
    for pantalla in ("lg_flota", "lg_jornada"):
        op.execute(f"""
            UPDATE categoria_acceso
            SET pantallas = NULLIF(array_to_string(
                array_remove(string_to_array(pantallas, ','), '{pantalla}'), ','), '')
            WHERE pantallas IS NOT NULL
              AND '{pantalla}' = ANY(string_to_array(pantallas, ','))""")
    op.execute("""
        DELETE FROM actividad_de_categoria
        WHERE actividad IN ('lg.flota.ver', 'lg.flota.editar', 'lg.jornada.ver',
                            'lg.jornada.validar', 'lg.operadores.editar',
                            'lg.en_viaje.marcar')""")
    con.execute(sa.text(
        "UPDATE categoria_acceso SET puestos_odoo = :viejo "
        "WHERE nombre = :n AND puestos_odoo = :nuevo"),
        {"viejo": PUESTOS_ODOO_GERENCIA_150, "nuevo": PUESTOS_ODOO_GERENCIA, "n": GERENCIA})
    flota = _id_de(con, FLOTA)
    if flota is not None:
        con.execute(sa.text("UPDATE usuario SET categoria_id = NULL WHERE categoria_id = :c"),
                    {"c": flota})
        con.execute(sa.text("DELETE FROM actividad_de_categoria WHERE categoria_id = :c"),
                    {"c": flota})
        con.execute(sa.text("DELETE FROM categoria_acceso WHERE id = :c"), {"c": flota})
    for tabla in ("lg_jornada", "lg_llave", "lg_codigo_acceso", "lg_viaje_manual",
                  "lg_costo_dia",
                  "lg_llanta", "lg_servicio", "lg_plan_servicio", "lg_documento",
                  "lg_operador", "lg_archivo", "lg_lectura_odometro", "lg_unidad"):
        op.execute(f"DROP TABLE IF EXISTS {tabla}")
    op.execute("ALTER TABLE lg_tipo_unidad DROP COLUMN IF EXISTS vida_llanta_km")
    op.execute("ALTER TABLE lg_tipo_unidad DROP COLUMN IF EXISTS llantas")

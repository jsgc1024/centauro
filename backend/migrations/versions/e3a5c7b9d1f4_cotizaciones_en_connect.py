"""Cotizaciones en Connect (seccion 114)

Salvador (30 sep): la cotizacion del eventual se arma en Connect, en una
pantalla nueva; sale su PDF, el consultor se la manda al cliente y,
cuando el cliente la autoriza, el servicio nace solo con ella adentro.
Con sus decisiones del 1 de octubre: folio nuevo de Connect (EP/COT), se
puede cotizar a una empresa que todavia no esta en Odoo, la autorizacion
la registra el consultor, el PDF lleva el IVA, y cada consultor sube su
firma.

- `cotizacion` puede vivir sin servicio y trae lo suyo: folio, cliente o
  el nombre de la empresa, pais, quien la pidio, quien la firma, tipo de
  servicio, introduccion, valida hasta, idioma, IVA, cuando se mando o se
  rechazo, y el folio del servicio que nacio de ella. Estatus nuevo:
  `vencida`.
- `dia_cotizacion`: los dias de cada equipo, con lo que lleva.
- `archivo_cotizacion`: el PDF que se mando y el comprobante de la
  autorizacion.
- `datos_cotizacion` y `texto_cotizacion`: la razon social, el RFC y la
  tasa de IVA de cada pais, y los textos de las condiciones por idioma.
  Mexico nace con los de la cotizacion de ejemplo de Salvador; las
  condiciones de pago quedan por escribir en Catalogos, igual que el RFC.
- `firma_consultor`: la firma de cada consultor.
- `linea_cotizacion.producto`: el nombre del producto de Odoo del renglon.

Y los puestos que ya existen toman la pantalla y las actividades nuevas
(`crear_puestos` no pisa un puesto existente). Solo suma; correrla dos
veces no duplica.

Revision ID: e3a5c7b9d1f4
Revises: cd3b659a42f6
Create Date: 2026-10-01
"""
import sqlalchemy as sa
from alembic import op

revision = "e3a5c7b9d1f4"
down_revision = "cd3b659a42f6"
branch_labels = None
depends_on = None

# Lo mismo que `app.cotizacion_cliente.DATOS_MEXICO` y `TEXTOS_MEXICO`;
# una prueba cuida que digan lo mismo. Se copia y no se importa: una
# migracion no puede depender de como este el codigo el dia que se corra.
DATOS_MEXICO = {"razon_social": "Centauro ASS, S.A. de C.V.",
                "tasa_iva": "0.1600"}
TEXTOS_MEXICO = {
    "incluye_dentro": {
        "es": "El personal y las unidades que se describen, con los gastos "
              "operativos del servicio: combustible, casetas, "
              "estacionamientos y alimentos del personal.",
        "en": "The personnel and vehicles described, including the "
              "operating expenses of the service: fuel, tolls, parking and "
              "meals for the personnel.",
        "pt": "O pessoal e as unidades descritos, com as despesas "
              "operacionais do serviço: combustível, pedágios, "
              "estacionamentos e alimentação do pessoal.",
    },
    "incluye_fijo": {
        "es": "El personal y las unidades que se describen. Los gastos "
              "operativos se cobran como el monto fijo que dice esta "
              "cotización.",
        "en": "The personnel and vehicles described. Operating expenses "
              "are charged as the fixed amount stated in this quotation.",
        "pt": "O pessoal e as unidades descritos. As despesas operacionais "
              "são cobradas como o valor fixo indicado nesta cotação.",
    },
    "incluye_comprobar": {
        "es": "El personal y las unidades que se describen. Los gastos "
              "operativos —combustible, casetas, estacionamientos, "
              "alimentos y hospedaje del personal— se facturan aparte, "
              "según lo comprobado y con su desglose.",
        "en": "The personnel and vehicles described. Operating expenses "
              "—fuel, tolls, parking, meals and lodging for the "
              "personnel— are invoiced separately, as incurred and with "
              "their breakdown.",
        "pt": "O pessoal e as unidades descritos. As despesas operacionais "
              "—combustível, pedágios, estacionamentos, alimentação e "
              "hospedagem do pessoal— são faturadas à parte, conforme "
              "comprovadas e com o seu detalhamento.",
    },
    "aceptacion": {
        "es": "Para autorizarla, responda por correo a {correo_consultor} "
              "con copia a salvador.carrasco@centauro.lat y "
              "luis.pichardo@centauro.lat, indicando el folio {folio}. "
              "Nuestros servicios se confirman diariamente: le agradecemos "
              "su aceptación con 72 horas de anticipación para agendar a "
              "nuestros elementos y vehículos.",
        "en": "To approve it, please reply by email to {correo_consultor}, "
              "copying salvador.carrasco@centauro.lat and "
              "luis.pichardo@centauro.lat, and quote reference {folio}. "
              "Our services are confirmed daily: we appreciate your "
              "approval 72 hours in advance so we can schedule our "
              "personnel and vehicles.",
        "pt": "Para aprová-la, responda por e-mail para {correo_consultor}, "
              "com cópia para salvador.carrasco@centauro.lat e "
              "luis.pichardo@centauro.lat, indicando a referência {folio}. "
              "Nossos serviços são confirmados diariamente: agradecemos a "
              "sua aprovação com 72 horas de antecedência para agendarmos "
              "nossos agentes e veículos.",
    },
    "cancelacion": {
        "es": "Si se cancela con más de 24 horas de anticipación al inicio "
              "del servicio, no hay cargo. Con menos de 24 horas, se cobra "
              "el 15% del valor del servicio.",
        "en": "Cancellations made more than 24 hours before the start of "
              "the service are free of charge. With less than 24 hours' "
              "notice, 15% of the value of the service is charged.",
        "pt": "Cancelamentos feitos com mais de 24 horas de antecedência do "
              "início do serviço não têm custo. Com menos de 24 horas, é "
              "cobrado 15% do valor do serviço.",
    },
    "cierre": {
        "es": "Agradecemos la oportunidad de presentarle esta propuesta. "
              "Quedamos a sus órdenes para cualquier duda o comentario.",
        "en": "Thank you for the opportunity to present this proposal. We "
              "remain at your disposal for any questions or comments.",
        "pt": "Agradecemos a oportunidade de apresentar esta proposta. "
              "Ficamos à disposição para qualquer dúvida ou comentário.",
    },
}

ACTIVIDADES = {
    "Dirección de operaciones": ["cotizaciones.ver", "cotizaciones.armar"],
    "Consultor de seguridad": ["cotizaciones.ver", "cotizaciones.armar"],
    "Consultor JR": ["cotizaciones.ver", "cotizaciones.armar"],
    "Administración del sistema y calidad": ["cotizaciones.ver"],
}
PANTALLAS = {nombre: ["cotizaciones"] for nombre in ACTIVIDADES}

FKS = [("fk_cotizacion_cliente", "cliente", ["cliente_id"]),
       ("fk_cotizacion_pais", "pais", ["pais_id"]),
       ("fk_cotizacion_solicitante", "solicitante", ["solicitante_id"]),
       ("fk_cotizacion_consultor", "persona", ["consultor_id"]),
       ("fk_cotizacion_enviada_por", "persona", ["enviada_por_id"])]


def upgrade() -> None:
    # El estatus nuevo. Postgres 16 lo deja agregar dentro de la
    # transaccion; no se usa en esta misma migracion.
    op.execute("ALTER TYPE estatuscotizacion ADD VALUE IF NOT EXISTS "
                "'VENCIDA'")

    op.create_table(
        "datos_cotizacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pais_id", sa.Integer(), nullable=False),
        sa.Column("razon_social", sa.String(length=200), nullable=True),
        sa.Column("rfc", sa.String(length=30), nullable=True),
        sa.Column("tasa_iva", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.ForeignKeyConstraint(["pais_id"], ["pais.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pais_id"))
    op.create_table(
        "texto_cotizacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pais_id", sa.Integer(), nullable=False),
        sa.Column("clave", sa.String(length=30), nullable=False),
        sa.Column("idioma", sa.String(length=2), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["pais_id"], ["pais.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pais_id", "clave", "idioma"))
    op.create_table(
        "firma_consultor",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.Integer(), nullable=False),
        sa.Column("imagen", sa.Text(), nullable=False),
        sa.Column("actualizada_en", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["persona_id"], ["persona.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("persona_id"))
    op.create_table(
        "archivo_cotizacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cotizacion_id", sa.Integer(), nullable=False),
        sa.Column("clase", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("tipo", sa.String(length=80), nullable=False),
        sa.Column("tamano", sa.Integer(), nullable=False),
        sa.Column("contenido", sa.LargeBinary(), nullable=False),
        sa.Column("subido_en", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("subido_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["cotizacion_id"], ["cotizacion.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subido_por_id"], ["persona.id"]),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_archivo_cotizacion_cotizacion_id",
                    "archivo_cotizacion", ["cotizacion_id"], unique=False)
    op.create_table(
        "dia_cotizacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cotizacion_id", sa.Integer(), nullable=False),
        sa.Column("equipo_clave", sa.String(length=20), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("modalidad_id", sa.Integer(), nullable=False),
        sa.Column("plaza_id", sa.Integer(), nullable=True),
        sa.Column("hora", sa.Time(), nullable=True),
        sa.Column("es_foraneo", sa.Boolean(), server_default=sa.text("false"),
                  nullable=False),
        sa.Column("destino", sa.String(length=120), nullable=True),
        sa.Column("lleva", sa.Text(), server_default="[]", nullable=False),
        sa.ForeignKeyConstraint(["cotizacion_id"], ["cotizacion.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["modalidad_id"], ["modalidad.id"]),
        sa.ForeignKeyConstraint(["plaza_id"], ["plaza.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cotizacion_id", "equipo_clave", "fecha"))
    op.create_index("ix_dia_cotizacion_cotizacion_id", "dia_cotizacion",
                    ["cotizacion_id"], unique=False)

    for nombre, tipo in (("folio", sa.Integer()),
                         ("cliente_id", sa.Integer()),
                         ("prospecto", sa.String(length=160)),
                         ("pais_id", sa.Integer()),
                         ("solicitante_id", sa.Integer()),
                         ("solicitante_nombre", sa.String(length=160)),
                         ("solicitante_apellidos", sa.String(length=160)),
                         ("solicitante_correo", sa.String(length=160)),
                         ("solicitante_telefono", sa.String(length=40)),
                         ("consultor_id", sa.Integer()),
                         ("tipo_servicio", sa.String(length=120)),
                         ("introduccion", sa.Text()),
                         ("valida_hasta", sa.Date()),
                         ("idioma", sa.String(length=2)),
                         ("tasa_iva", sa.Numeric(precision=6, scale=4)),
                         ("actualizada_en", sa.DateTime(timezone=True)),
                         ("enviada_en", sa.DateTime(timezone=True)),
                         ("enviada_por_id", sa.Integer()),
                         ("rechazada_en", sa.DateTime(timezone=True)),
                         ("rechazo_motivo", sa.String(length=300)),
                         ("servicio_folio", sa.String(length=24))):
        op.add_column("cotizacion", sa.Column(nombre, tipo, nullable=True))
    op.add_column("cotizacion", sa.Column(
        "con_iva", sa.Boolean(), server_default=sa.text("true"),
        nullable=False))
    op.alter_column("cotizacion", "servicio_id", existing_type=sa.INTEGER(),
                    nullable=True)
    op.create_index("ix_cotizacion_folio", "cotizacion", ["folio"],
                    unique=False)
    op.create_unique_constraint("cotizacion_folio_version_key", "cotizacion",
                                ["folio", "version"])
    for nombre, tabla, columnas in FKS:
        op.create_foreign_key(nombre, "cotizacion", tabla, columnas, ["id"])
    op.add_column("linea_cotizacion", sa.Column(
        "producto", sa.String(length=200), nullable=True))

    con = op.get_bind()
    _sembrar_mexico(con)
    _puestos(con)


def _sembrar_mexico(con) -> None:
    """Los datos y los textos de Mexico, si Mexico existe en esta base y
    todavia no los tiene."""
    pais = con.execute(sa.text(
        "SELECT id FROM pais WHERE codigo = 'MX'")).first()
    if pais is None:
        return
    con.execute(sa.text(
        "INSERT INTO datos_cotizacion (pais_id, razon_social, tasa_iva) "
        "SELECT CAST(:p AS INTEGER), CAST(:r AS VARCHAR(200)), "
        "CAST(:t AS NUMERIC(6,4)) "
        "WHERE NOT EXISTS (SELECT 1 FROM datos_cotizacion "
        "WHERE pais_id = CAST(:p AS INTEGER))"),
        {"p": pais.id, "r": DATOS_MEXICO["razon_social"],
         "t": DATOS_MEXICO["tasa_iva"]})
    for clave, por_idioma in TEXTOS_MEXICO.items():
        for idioma, texto in por_idioma.items():
            con.execute(sa.text(
                "INSERT INTO texto_cotizacion (pais_id, clave, idioma, texto) "
                "SELECT CAST(:p AS INTEGER), CAST(:c AS VARCHAR(30)), "
                "CAST(:i AS VARCHAR(2)), CAST(:x AS TEXT) "
                "WHERE NOT EXISTS (SELECT 1 FROM texto_cotizacion "
                "WHERE pais_id = CAST(:p AS INTEGER) "
                "AND clave = CAST(:c AS VARCHAR(30)) "
                "AND idioma = CAST(:i AS VARCHAR(2)))"),
                {"p": pais.id, "c": clave, "i": idioma, "x": texto})


def _categoria(con, nombre):
    return con.execute(sa.text(
        "SELECT id, pantallas FROM categoria_acceso WHERE nombre = :n"),
        {"n": nombre}).first()


def _puestos(con) -> None:
    for nombre, actividades in ACTIVIDADES.items():
        fila = _categoria(con, nombre)
        if fila is None:
            continue
        for actividad in actividades:
            con.execute(sa.text(
                "INSERT INTO actividad_de_categoria (categoria_id, actividad) "
                "SELECT CAST(:c AS INTEGER), CAST(:a AS VARCHAR(60)) "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM actividad_de_categoria "
                "  WHERE categoria_id = CAST(:c AS INTEGER) "
                "  AND actividad = CAST(:a AS VARCHAR(60)))"),
                {"c": fila.id, "a": actividad})
    for nombre, pantallas in PANTALLAS.items():
        fila = _categoria(con, nombre)
        # Sin lista de pantallas el menu sale del rol, que ya trae la
        # pantalla nueva: no hay nada que agregar.
        if fila is None or not fila.pantallas:
            continue
        puestas = [x for x in fila.pantallas.split(",") if x]
        nuevas = [p for p in pantallas if p not in puestas]
        if nuevas:
            con.execute(sa.text(
                "UPDATE categoria_acceso SET pantallas = :p WHERE id = :c"),
                {"p": ",".join(puestas + nuevas), "c": fila.id})


def downgrade() -> None:
    con = op.get_bind()
    for nombre, actividades in ACTIVIDADES.items():
        fila = _categoria(con, nombre)
        if fila is None:
            continue
        for actividad in actividades:
            con.execute(sa.text(
                "DELETE FROM actividad_de_categoria "
                "WHERE categoria_id = :c AND actividad = :a"),
                {"c": fila.id, "a": actividad})
    for nombre, pantallas in PANTALLAS.items():
        fila = _categoria(con, nombre)
        if fila is None or not fila.pantallas:
            continue
        quedan = [x for x in fila.pantallas.split(",")
                  if x and x not in pantallas]
        con.execute(sa.text(
            "UPDATE categoria_acceso SET pantallas = :p WHERE id = :c"),
            {"p": ",".join(quedan), "c": fila.id})

    # Las cotizaciones que vivian sin servicio no caben en la tabla de
    # antes: se van, con sus renglones.
    con.execute(sa.text(
        "DELETE FROM linea_cotizacion WHERE cotizacion_id IN "
        "(SELECT id FROM cotizacion WHERE servicio_id IS NULL)"))
    con.execute(sa.text("DELETE FROM cotizacion WHERE servicio_id IS NULL"))
    con.execute(sa.text(
        "UPDATE cotizacion SET estatus = 'SUSTITUIDA' "
        "WHERE estatus = 'VENCIDA'"))
    op.drop_column("linea_cotizacion", "producto")
    for nombre, _tabla, _columnas in FKS:
        op.drop_constraint(nombre, "cotizacion", type_="foreignkey")
    op.drop_constraint("cotizacion_folio_version_key", "cotizacion",
                       type_="unique")
    op.drop_index("ix_cotizacion_folio", table_name="cotizacion")
    op.alter_column("cotizacion", "servicio_id", existing_type=sa.INTEGER(),
                    nullable=False)
    for nombre in ("servicio_folio", "rechazo_motivo", "rechazada_en",
                   "enviada_por_id", "enviada_en", "actualizada_en",
                   "tasa_iva", "con_iva", "idioma", "valida_hasta",
                   "introduccion", "tipo_servicio", "consultor_id",
                   "solicitante_telefono", "solicitante_correo",
                   "solicitante_apellidos", "solicitante_nombre",
                   "solicitante_id", "pais_id", "prospecto", "cliente_id",
                   "folio"):
        op.drop_column("cotizacion", nombre)
    op.drop_index("ix_dia_cotizacion_cotizacion_id",
                  table_name="dia_cotizacion")
    op.drop_table("dia_cotizacion")
    op.drop_index("ix_archivo_cotizacion_cotizacion_id",
                  table_name="archivo_cotizacion")
    op.drop_table("archivo_cotizacion")
    op.drop_table("firma_consultor")
    op.drop_table("texto_cotizacion")
    op.drop_table("datos_cotizacion")
    # Postgres no quita un valor de un ENUM: `vencida` se queda en el
    # tipo, sin uso.

"""El freelance en Connect (seccion 111)

Salvador (30 sep): un lugar para dar de alta al freelance con su foto y
sus datos --los que salen en la hoja del servicio--, otro donde se cargue
todo lo que pide Recursos Humanos para activarlo, y sus costos propios de
dia completo, medio dia y transfer, solo para eventuales. Con las doce
decisiones que contesto una por una.

Cinco tablas nuevas:

- `freelance`: la ficha, al lado de su persona --tipo (programado o de
  emergencia), nombre y apellidos, quien lo dio de alta y el plazo del
  de emergencia que repite--.
- `requisito_freelance`: la lista de Recursos Humanos por pais. Mexico
  nace con la tabla que mando Salvador y el aviso de privacidad (decision
  8); Brasil se llena cuando se opere alla.
- `documento_freelance` y `archivo_freelance`: su expediente. Nada se
  borra (decision 7).
- `autorizacion_freelance`: la urgencia que autoriza direccion de
  operaciones para un servicio (decision 4).

Y lo que ya existe: cada persona marcada como freelance recibe su ficha
--programado, con el expediente por completar y sus tarifas como
estaban--, y los puestos que ya estan en la base toman las actividades
nuevas (`crear_puestos` no pisa un puesto existente). Solo suma; correrla
dos veces no duplica.

Revision ID: cd3b659a42f6
Revises: f1b3d5a7c9e2
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op

revision = "cd3b659a42f6"
down_revision = "f1b3d5a7c9e2"
branch_labels = None
depends_on = None

# La misma lista de `app.freelance.REQUISITOS_MEXICO`; una prueba cuida
# que digan lo mismo. Se copia y no se importa: una migracion no puede
# depender de como este el codigo el dia que se corra.
# (clave, nombre, detalle, programado, emergencia, captura, vigencia,
#  vigencia_meses, antiguedad_meses, orden)
REQUISITOS_MEXICO = [
    ("licencia", "Licencia de conducir vigente", None, True, True,
     "archivo", "documento", None, None, 10),
    ("ine", "INE vigente", None, True, True, "archivo", "documento", None,
     None, 20),
    ("domicilio", "Comprobante de domicilio",
     "No mayor a 3 meses; vale un año", True, True, "archivo", "meses", 12,
     3, 30),
    ("antecedentes", "Antecedentes penales", "Vale un año", True, False,
     "archivo", "meses", 12, None, 40),
    ("curp", "CURP", None, True, False, "numero", "ninguna", None, None, 50),
    ("rfc", "CIF (RFC)", "Constancia de situación fiscal, con su RFC", True,
     True, "archivo_numero", "ninguna", None, None, 60),
    ("nss", "NSS", "Número de seguridad social", True, True, "numero",
     "ninguna", None, None, 70),
    ("banco", "Datos bancarios",
     "Banco, CLABE, titular y la carátula del estado de cuenta", True, True,
     "banco", "ninguna", None, None, 80),
    ("toxicologica", "Prueba toxicológica en laboratorio", "Cada 6 meses",
     True, False, "archivo", "meses", 6, None, 90),
    ("caseta", "Prueba toxicológica rápida y alcoholemia",
     "La aplica la caseta en cada servicio", False, True, "prueba",
     "servicio", None, None, 95),
    ("veritas", "Evaluación Veritas", "Apegada a integridad: riesgo 1, 2 o 3",
     True, False, "riesgo", "ninguna", None, None, 100),
    ("rotacion", "Análisis de rotación", "Semanas cotizadas ante el IMSS",
     True, False, "archivo", "ninguna", None, None, 110),
    ("responsiva", "Responsiva por daño a unidad con dolo", "Firmada", True,
     True, "archivo", "ninguna", None, None, 120),
    ("entrevista", "Entrevista técnica", None, True, False, "entrevista",
     "ninguna", None, None, 130),
    ("referencias", "Referencia laboral", "Cartas de recomendación", True,
     False, "archivo", "ninguna", None, None, 140),
    ("contactos", "Contactos de emergencia",
     "Dos: nombre, parentesco y teléfono", True, True, "contactos",
     "ninguna", None, None, 150),
    ("privacidad", "Aviso de privacidad firmado",
     "Hay datos personales sensibles en el expediente", True, True,
     "archivo", "ninguna", None, None, 160),
]

# Los puestos que ya existen y lo que toman (decisiones 2, 3, 4 y 6).
ACTIVIDADES = {
    "Dirección de operaciones": ["freelance.ver", "freelance.alta",
                                 "freelance.expediente",
                                 "freelance.autorizar"],
    "Consultor de seguridad": ["freelance.ver", "freelance.alta"],
    "Consultor JR": ["freelance.ver", "freelance.alta"],
    "Supervisor de central": ["freelance.ver"],
    "Monitorista": ["freelance.ver"],
    "Gerente de administración": ["freelance.ver"],
    "Recursos Humanos": ["freelance.ver", "freelance.alta",
                         "freelance.expediente", "freelance.validar"],
    "Capacitación": ["freelance.ver"],
    "Administración del sistema y calidad": ["freelance.ver"],
}


def _partir(completo: str) -> tuple[str, str]:
    partes = (completo or "").split()
    if len(partes) <= 1:
        return (completo or "").strip(), ""
    if len(partes) == 2:
        return partes[0], partes[1]
    return " ".join(partes[:-2]), " ".join(partes[-2:])


def upgrade() -> None:
    op.create_table(
        "freelance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("persona_id", sa.Integer(),
                  sa.ForeignKey("persona.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("tipo", sa.String(12), nullable=False,
                  server_default="programado"),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("apellidos", sa.String(120), nullable=False,
                  server_default=""),
        sa.Column("alta_por_id", sa.Integer(), sa.ForeignKey("persona.id"),
                  nullable=True),
        sa.Column("alta_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("plazo_programado", sa.Date(), nullable=True),
        sa.Column("plazo_puesto_en", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("plazo_avisado_en", sa.Date(), nullable=True),
    )
    op.create_table(
        "requisito_freelance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pais_id", sa.Integer(), sa.ForeignKey("pais.id"),
                  nullable=False),
        sa.Column("clave", sa.String(40), nullable=False),
        sa.Column("nombre", sa.String(160), nullable=False),
        sa.Column("detalle", sa.String(200), nullable=True),
        sa.Column("programado", sa.Boolean(), nullable=False,
                  server_default="true"),
        sa.Column("emergencia", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("captura", sa.String(20), nullable=False,
                  server_default="archivo"),
        sa.Column("vigencia", sa.String(12), nullable=False,
                  server_default="ninguna"),
        sa.Column("vigencia_meses", sa.Integer(), nullable=True),
        sa.Column("antiguedad_meses", sa.Integer(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean(), nullable=False,
                  server_default="true"),
        sa.UniqueConstraint("pais_id", "clave",
                            name="uq_requisito_freelance_clave"),
    )
    op.create_table(
        "documento_freelance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("persona_id", sa.Integer(),
                  sa.ForeignKey("persona.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("requisito_id", sa.Integer(),
                  sa.ForeignKey("requisito_freelance.id"), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False,
                  server_default="por_revisar"),
        sa.Column("datos", sa.Text(), nullable=True),
        sa.Column("fecha_documento", sa.Date(), nullable=True),
        sa.Column("vence_en", sa.Date(), nullable=True),
        sa.Column("subido_por_id", sa.Integer(), sa.ForeignKey("persona.id"),
                  nullable=True),
        sa.Column("subido_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("revisado_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id"), nullable=True),
        sa.Column("revisado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_rechazo", sa.String(300), nullable=True),
        sa.Column("reemplazado_en", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("aviso_por_vencer_en", sa.Date(), nullable=True),
        sa.Column("aviso_vencido_en", sa.Date(), nullable=True),
    )
    op.create_index("ix_documento_freelance_persona_id",
                    "documento_freelance", ["persona_id"])
    op.create_index("ix_documento_freelance_requisito_id",
                    "documento_freelance", ["requisito_id"])
    op.create_table(
        "archivo_freelance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("documento_id", sa.Integer(),
                  sa.ForeignKey("documento_freelance.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("tipo", sa.String(80), nullable=False),
        sa.Column("tamano", sa.Integer(), nullable=False),
        sa.Column("md5", sa.String(32), nullable=False),
        sa.Column("contenido", sa.LargeBinary(), nullable=True),
        sa.Column("objeto", sa.String(400), nullable=True),
        sa.Column("subido_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_archivo_freelance_documento_id", "archivo_freelance",
                    ["documento_id"])
    op.create_table(
        "autorizacion_freelance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("persona_id", sa.Integer(),
                  sa.ForeignKey("persona.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("servicio_id", sa.Integer(),
                  sa.ForeignKey("servicio.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("estado", sa.String(12), nullable=False,
                  server_default="pedida"),
        sa.Column("motivo", sa.String(400), nullable=False),
        sa.Column("faltaba", sa.String(400), nullable=True),
        sa.Column("pedida_por_id", sa.Integer(), sa.ForeignKey("persona.id"),
                  nullable=True),
        sa.Column("pedida_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("resuelta_por_id", sa.Integer(),
                  sa.ForeignKey("persona.id"), nullable=True),
        sa.Column("resuelta_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("respuesta", sa.String(400), nullable=True),
        sa.UniqueConstraint("persona_id", "servicio_id",
                            name="uq_autorizacion_freelance"),
    )
    op.create_index("ix_autorizacion_freelance_persona_id",
                    "autorizacion_freelance", ["persona_id"])
    op.create_index("ix_autorizacion_freelance_servicio_id",
                    "autorizacion_freelance", ["servicio_id"])

    con = op.get_bind()

    # Los requisitos de Mexico, si Mexico existe y no tiene ninguno.
    mx = con.execute(sa.text("SELECT id FROM pais WHERE codigo = 'MX'")).first()
    if mx is not None and con.execute(sa.text(
            "SELECT 1 FROM requisito_freelance WHERE pais_id = :p"),
            {"p": mx.id}).first() is None:
        for (clave, nombre, detalle, programado, emergencia, captura,
             vigencia, meses, antiguedad, orden) in REQUISITOS_MEXICO:
            con.execute(sa.text(
                "INSERT INTO requisito_freelance (pais_id, clave, nombre, "
                "detalle, programado, emergencia, captura, vigencia, "
                "vigencia_meses, antiguedad_meses, orden, activo) VALUES "
                "(:p, :c, :n, :d, :pr, :em, :ca, :vi, :vm, :an, :o, true)"),
                {"p": mx.id, "c": clave, "n": nombre, "d": detalle,
                 "pr": programado, "em": emergencia, "ca": captura,
                 "vi": vigencia, "vm": meses, "an": antiguedad, "o": orden})

    # Cada freelance que ya existia recibe su ficha: programado, con el
    # expediente por completar. Sus tarifas se quedan como estan.
    for fila in con.execute(sa.text(
            "SELECT p.id, p.nombre FROM persona p "
            "WHERE p.es_freelance AND NOT EXISTS "
            "(SELECT 1 FROM freelance f WHERE f.persona_id = p.id)")).all():
        nombre, apellidos = _partir(fila.nombre)
        con.execute(sa.text(
            "INSERT INTO freelance (persona_id, tipo, nombre, apellidos) "
            "VALUES (:p, 'programado', :n, :a)"),
            {"p": fila.id, "n": nombre[:80], "a": apellidos[:120]})

    # Los puestos que ya existen toman las actividades nuevas.
    for puesto, actividades in ACTIVIDADES.items():
        categoria = con.execute(sa.text(
            "SELECT id FROM categoria_acceso WHERE nombre = :n"),
            {"n": puesto}).first()
        if categoria is None:
            continue
        for actividad in actividades:
            # Con el tipo dicho (seccion 105): psycopg no deduce el del
            # parametro que se usa dos veces en la misma sentencia.
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
    op.drop_index("ix_autorizacion_freelance_servicio_id",
                  table_name="autorizacion_freelance")
    op.drop_index("ix_autorizacion_freelance_persona_id",
                  table_name="autorizacion_freelance")
    op.drop_table("autorizacion_freelance")
    op.drop_index("ix_archivo_freelance_documento_id",
                  table_name="archivo_freelance")
    op.drop_table("archivo_freelance")
    op.drop_index("ix_documento_freelance_requisito_id",
                  table_name="documento_freelance")
    op.drop_index("ix_documento_freelance_persona_id",
                  table_name="documento_freelance")
    op.drop_table("documento_freelance")
    op.drop_table("requisito_freelance")
    op.drop_table("freelance")

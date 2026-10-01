"""La propuesta del implantado en Connect (seccion 115)

Salvador (30 sep): la propuesta del implantado --«esta no se llama
cotizacion, se llama propuesta»-- se arma en Connect, junto a la
cotizacion del eventual. Sus decisiones del 1 de octubre, una por una:

  1. Folio de Connect, EP/PRO-0001, con su version.
  2. Los precios salen de la lista de implantados del cliente; el que no
     tiene --la empresa nueva-- o el precio que se pacta distinto lo
     escribe el consultor con su motivo, y direccion de operaciones lo
     autoriza antes de que se pueda mandar.
  3. Tres modalidades: lunes a viernes, 22 dias al mes mas los dias
     adicionales; lunes a sabado, 26 mas los adicionales; o el mes
     completo, 30 dias a costo fijo. En las tres, mas viaticos o con los
     viaticos incluidos.
  4. El mensual antes de IVA, el IVA y el mensual con IVA.
  5. Cuando el cliente la autoriza nace el implantado, con la propuesta
     adentro.

- `cotizacion.clase`: «cotizacion» o «propuesta», cada una con su serie.
  El candado de folio y version pasa a ser de clase, folio y version: la
  EP/COT-0001 y la EP/PRO-0001 son dos. `tarifario_id` puede ir vacio: la
  propuesta de una empresa nueva no tiene lista.
- `cotizacion`: la ciudad, la modalidad, la jornada, la hora del
  encuentro, el inicio, el alcance, y el precio especial --su motivo,
  quien lo pidio y cuando, quien lo decidio, cuando y su nota, y la
  huella de los precios autorizados--.
- `posicion_propuesta`: lo que lleva al mes, con su precio por dia, su
  mensual, su hora extra y lo que decia la lista.
- `texto_cotizacion.clave` crece a 60 letras: el alcance de cada rol
  lleva su codigo.
- `contrato_implantado.dias_del_mensual`: los dias que cubre el precio
  fijo del mes en las modalidades de la propuesta (22, 26 o 30). Con el,
  el dia fuera de la modalidad se cobra aparte y el primer mes que no
  empieza el dia 1 se cobra por dia. Los contratos de antes lo dejan
  vacio y siguen cobrando como estaban.
- Mexico nace con los textos de la propuesta de ejemplo de Salvador.
- El puesto «Direccion de operaciones» toma la actividad nueva
  `propuestas.precio_especial` (`crear_puestos` no pisa un puesto que ya
  existe).

Solo suma; correrla dos veces no duplica.

Revision ID: b8e1d4f6a9c3
Revises: e3a5c7b9d1f4
Create Date: 2026-10-01
"""
import sqlalchemy as sa
from alembic import op

revision = "b8e1d4f6a9c3"
down_revision = "e3a5c7b9d1f4"
branch_labels = None
depends_on = None

DIAS = sa.Enum("LUNES_VIERNES", "LUNES_SABADO", "TODOS", name="diasservicio",
               create_type=False)

# Lo mismo que `app.propuesta.TEXTOS_MEXICO`; una prueba cuida que digan lo
# mismo. Se copia y no se importa: una migracion no puede depender de como
# este el codigo el dia que se corra.
TEXTOS_MEXICO = {
    "pro_incluye": {
        "es": "Personal de seguridad debidamente capacitado, con las "
              "certificaciones y entrenamientos correspondientes.",
        "en": "Security personnel duly trained, with the corresponding "
              "certifications and training.",
        "pt": "Pessoal de segurança devidamente capacitado, com as "
              "certificações e treinamentos correspondentes.",
    },
    "pro_incluye_unidad": {
        "es": "Unidad de nueva generación con monitoreo activo mediante "
              "sistema IVMS y botón de pánico para atención y respuesta "
              "ante cualquier eventualidad.\n"
              "Mantenimiento preventivo de la unidad cada 10,000 km. Si una "
              "reparación puede afectar la operación, la unidad se "
              "reemplaza de inmediato para garantizar la continuidad y la "
              "seguridad del servicio.",
        "en": "Latest-generation vehicle with active monitoring through an "
              "IVMS system and a panic button for response to any event.\n"
              "Preventive maintenance of the vehicle every 10,000 km. If a "
              "repair could affect the operation, the vehicle is replaced "
              "immediately to ensure the continuity and safety of the "
              "service.",
        "pt": "Veículo de nova geração com monitoramento ativo por sistema "
              "IVMS e botão de pânico para atendimento e resposta a "
              "qualquer eventualidade.\n"
              "Manutenção preventiva do veículo a cada 10.000 km. Se um "
              "reparo puder afetar a operação, o veículo é substituído "
              "imediatamente para garantir a continuidade e a segurança do "
              "serviço.",
    },
    "pro_incluidos": {
        "es": "Los gastos de operación del servicio: gasolina, tag, "
              "estacionamientos y alimentos del personal.",
        "en": "The operating expenses of the service: fuel, tolls, parking "
              "and meals for the personnel.",
        "pt": "As despesas operacionais do serviço: combustível, pedágios, "
              "estacionamentos e alimentação do pessoal.",
    },
    "pro_no_incluye": {
        "es": "Los gastos de operación: hospedaje cuando la operación lo "
              "requiera, amenidades cuando sean necesarias para el "
              "servicio, estacionamientos, gasolina y tag.\n"
              "Cualquier otro gasto que pida el cliente o que sea "
              "indispensable para la operación, aprobado antes por el "
              "cliente.",
        "en": "Operating expenses: lodging when the operation requires it, "
              "amenities when needed for the service, parking, fuel and "
              "tolls.\n"
              "Any other expense requested by the client or essential to "
              "the operation, approved in advance by the client.",
        "pt": "As despesas operacionais: hospedagem quando a operação "
              "exigir, amenidades quando forem necessárias para o serviço, "
              "estacionamentos, combustível e pedágios.\n"
              "Qualquer outra despesa solicitada pelo cliente ou "
              "indispensável para a operação, aprovada previamente pelo "
              "cliente.",
    },
    "pro_viaticos": {
        "es": "Los gastos de operación se facturan cada mes, junto con el "
              "servicio y con su desglose. Cada gasto lleva su comprobante: "
              "lo presenta el personal de seguridad y Centauro lo revisa y "
              "lo valida.",
        "en": "Operating expenses are invoiced every month, together with "
              "the service and with their breakdown. Each expense comes "
              "with its receipt: the security personnel submit it and "
              "Centauro reviews and validates it.",
        "pt": "As despesas operacionais são faturadas todo mês, junto com o "
              "serviço e com o seu detalhamento. Cada despesa tem o seu "
              "comprovante: o pessoal de segurança o apresenta e a Centauro "
              "o revisa e valida.",
    },
    "pro_cliente": {
        "es": "Proporcionar itinerario, horarios y puntos de servicio con "
              "anticipación.\n"
              "Reportar cualquier incidente durante el servicio de manera "
              "inmediata.",
        "en": "Provide the itinerary, schedules and service locations in "
              "advance.\n"
              "Report any incident during the service immediately.",
        "pt": "Informar o itinerário, os horários e os pontos de serviço com "
              "antecedência.\n"
              "Comunicar imediatamente qualquer incidente durante o "
              "serviço.",
    },
    "pro_centauro": {
        "es": "Centauro cumple los protocolos de seguridad y "
              "confidencialidad: toda la información relacionada con el "
              "servicio, los pasajeros y la operación se trata como "
              "confidencial.",
        "en": "Centauro complies with its security and confidentiality "
              "protocols: all information related to the service, the "
              "passengers and the operation is treated as confidential.",
        "pt": "A Centauro cumpre os protocolos de segurança e "
              "confidencialidade: todas as informações relacionadas ao "
              "serviço, aos passageiros e à operação são tratadas como "
              "confidenciais.",
    },
    "pro_aceptacion": {
        "es": "Para autorizarla, responda por correo a {correo_consultor} "
              "con copia a luis.pichardo@centauro.lat, indicando el folio "
              "{folio}. Le agradecemos su aceptación con 72 horas de "
              "anticipación al inicio del servicio, para agendar a nuestros "
              "elementos y vehículos.",
        "en": "To approve it, please reply by email to {correo_consultor}, "
              "copying luis.pichardo@centauro.lat, and quote reference "
              "{folio}. We appreciate your approval 72 hours before the "
              "start of the service so we can schedule our personnel and "
              "vehicles.",
        "pt": "Para aprová-la, responda por e-mail para {correo_consultor}, "
              "com cópia para luis.pichardo@centauro.lat, indicando a "
              "referência {folio}. Agradecemos a sua aprovação com 72 horas "
              "de antecedência do início do serviço, para agendarmos nossos "
              "agentes e veículos.",
    },
    "alcance:conductor_seguridad": {
        "es": "El servicio de conductor de seguridad tiene como finalidad "
              "proporcionar traslados seguros, discretos y eficientes al "
              "principal y a su familia, mediante la aplicación de medidas "
              "preventivas orientadas a salvaguardar su integridad física "
              "durante cada desplazamiento.\n\n"
              "El conductor es responsable de operar la unidad asignada con "
              "apego a la normatividad vigente, realizar inspecciones "
              "preventivas del vehículo, planificar las rutas considerando "
              "factores de seguridad y movilidad, y mantener una actitud "
              "profesional, discreta y de absoluta confidencialidad "
              "respecto a la información, los itinerarios y las actividades "
              "del cliente. Asimismo, identifica y reporta oportunamente "
              "cualquier situación de riesgo, aplica los protocolos de "
              "seguridad establecidos por la empresa y mantiene "
              "comunicación con el centro de operaciones o el responsable "
              "del servicio cuando la operación así lo requiera.\n\n"
              "El alcance del servicio se limita exclusivamente a las "
              "funciones inherentes al transporte seguro y la protección "
              "preventiva durante los desplazamientos. En consecuencia, el "
              "conductor no realiza actividades ajenas a su función, como "
              "labores domésticas, asistencia personal, manejo de recursos "
              "económicos del cliente o cualquier otra actividad que no "
              "haya sido previamente acordada y autorizada por escrito como "
              "parte del servicio contratado.",
        "en": "The purpose of the security driver service is to provide "
              "safe, discreet and efficient transportation for the "
              "principal and their family, applying preventive measures "
              "aimed at safeguarding their physical integrity during every "
              "trip.\n\n"
              "The driver is responsible for operating the assigned vehicle "
              "in compliance with current regulations, carrying out "
              "preventive vehicle inspections, planning routes with "
              "security and mobility in mind, and maintaining a "
              "professional, discreet attitude and absolute confidentiality "
              "regarding the client's information, itineraries and "
              "activities. The driver also identifies and promptly reports "
              "any risk situation, applies the company's security protocols "
              "and keeps in contact with the operations center or the "
              "person in charge of the service when the operation requires "
              "it.\n\n"
              "The scope of the service is limited exclusively to the "
              "functions inherent to secure transportation and preventive "
              "protection during trips. Accordingly, the driver does not "
              "perform activities outside their role, such as domestic "
              "chores, personal assistance, handling the client's money or "
              "any other activity not previously agreed and authorized in "
              "writing as part of the contracted service.",
        "pt": "O serviço de motorista de segurança tem como finalidade "
              "oferecer deslocamentos seguros, discretos e eficientes ao "
              "principal e à sua família, com a aplicação de medidas "
              "preventivas voltadas a salvaguardar a sua integridade física "
              "em cada deslocamento.\n\n"
              "O motorista é responsável por operar o veículo designado em "
              "conformidade com a legislação vigente, realizar inspeções "
              "preventivas do veículo, planejar as rotas considerando "
              "fatores de segurança e mobilidade, e manter uma atitude "
              "profissional, discreta e de absoluta confidencialidade em "
              "relação às informações, aos itinerários e às atividades do "
              "cliente. Além disso, identifica e comunica oportunamente "
              "qualquer situação de risco, aplica os protocolos de "
              "segurança da empresa e mantém comunicação com a central de "
              "operações ou com o responsável pelo serviço quando a "
              "operação exigir.\n\n"
              "O escopo do serviço limita-se exclusivamente às funções "
              "inerentes ao transporte seguro e à proteção preventiva "
              "durante os deslocamentos. Assim, o motorista não realiza "
              "atividades alheias à sua função, como tarefas domésticas, "
              "assistência pessoal, manejo de recursos financeiros do "
              "cliente ou qualquer outra atividade que não tenha sido "
              "previamente acordada e autorizada por escrito como parte do "
              "serviço contratado.",
    },
}

ACTIVIDADES = {"Dirección de operaciones": ["propuestas.precio_especial"]}

COLUMNAS = (("plaza_id", sa.Integer()),
            ("dias_servicio", DIAS),
            ("horas_jornada", sa.Numeric(precision=4, scale=2)),
            ("hora_presentacion", sa.String(length=8)),
            ("inicio", sa.Date()),
            ("precio_hora_extra", sa.Numeric(precision=12, scale=2)),
            ("alcance", sa.Text()),
            ("especial_motivo", sa.String(length=400)),
            ("especial_estatus", sa.String(length=12)),
            ("especial_pedido_por_id", sa.Integer()),
            ("especial_pedido_en", sa.DateTime(timezone=True)),
            ("especial_por_id", sa.Integer()),
            ("especial_en", sa.DateTime(timezone=True)),
            ("especial_nota", sa.String(length=400)),
            ("especial_huella", sa.String(length=64)))

FKS = [("fk_cotizacion_plaza", "plaza", ["plaza_id"]),
       ("fk_cotizacion_especial_pedido_por", "persona",
        ["especial_pedido_por_id"]),
       ("fk_cotizacion_especial_por", "persona", ["especial_por_id"])]


def upgrade() -> None:
    op.add_column("cotizacion", sa.Column(
        "clase", sa.String(length=12), server_default="cotizacion",
        nullable=False))
    op.drop_constraint("cotizacion_folio_version_key", "cotizacion",
                       type_="unique")
    op.create_unique_constraint("cotizacion_clase_folio_version_key",
                                "cotizacion", ["clase", "folio", "version"])
    op.alter_column("cotizacion", "tarifario_id", existing_type=sa.INTEGER(),
                    nullable=True)
    for nombre, tipo in COLUMNAS:
        op.add_column("cotizacion", sa.Column(nombre, tipo, nullable=True))
    for nombre, tabla, columnas in FKS:
        op.create_foreign_key(nombre, "cotizacion", tabla, columnas, ["id"])

    op.create_table(
        "posicion_propuesta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cotizacion_id", sa.Integer(), nullable=False),
        sa.Column("orden", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tipo", sa.String(length=10), nullable=False),
        sa.Column("perfil_id", sa.Integer(), nullable=True),
        sa.Column("categoria_id", sa.Integer(), nullable=True),
        sa.Column("cantidad", sa.Integer(), server_default="1",
                  nullable=False),
        sa.Column("precio_dia", sa.Numeric(precision=12, scale=2),
                  nullable=True),
        sa.Column("precio_mes", sa.Numeric(precision=12, scale=2),
                  nullable=True),
        sa.Column("precio_hora_extra", sa.Numeric(precision=12, scale=2),
                  nullable=True),
        sa.Column("especial", sa.Boolean(), server_default=sa.text("false"),
                  nullable=False),
        sa.Column("lista_precio_dia", sa.Numeric(precision=12, scale=2),
                  nullable=True),
        sa.Column("producto", sa.String(length=200), nullable=True),
        sa.Column("descripcion", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["cotizacion_id"], ["cotizacion.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["perfil_id"], ["perfil_personal.id"]),
        sa.ForeignKeyConstraint(["categoria_id"], ["categoria_vehiculo.id"]),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_posicion_propuesta_cotizacion_id",
                    "posicion_propuesta", ["cotizacion_id"], unique=False)

    op.alter_column("texto_cotizacion", "clave",
                    existing_type=sa.String(length=30),
                    type_=sa.String(length=60), existing_nullable=False)
    # Los dias que cubre el precio fijo del mes en las modalidades de la
    # propuesta. Vacio en los contratos de antes: siguen como estaban.
    op.add_column("contrato_implantado",
                  sa.Column("dias_del_mensual", sa.Integer(), nullable=True))

    con = op.get_bind()
    _sembrar_mexico(con)
    _puestos(con)


def _sembrar_mexico(con) -> None:
    """Los textos de la propuesta de Mexico, si Mexico existe en esta base
    y todavia no los tiene."""
    pais = con.execute(sa.text(
        "SELECT id FROM pais WHERE codigo = 'MX'")).first()
    if pais is None:
        return
    for clave, por_idioma in TEXTOS_MEXICO.items():
        for idioma, texto in por_idioma.items():
            con.execute(sa.text(
                "INSERT INTO texto_cotizacion (pais_id, clave, idioma, texto) "
                "SELECT CAST(:p AS INTEGER), CAST(:c AS VARCHAR(60)), "
                "CAST(:i AS VARCHAR(2)), CAST(:x AS TEXT) "
                "WHERE NOT EXISTS (SELECT 1 FROM texto_cotizacion "
                "WHERE pais_id = CAST(:p AS INTEGER) "
                "AND clave = CAST(:c AS VARCHAR(60)) "
                "AND idioma = CAST(:i AS VARCHAR(2)))"),
                {"p": pais.id, "c": clave, "i": idioma, "x": texto})


def _categoria(con, nombre):
    return con.execute(sa.text(
        "SELECT id FROM categoria_acceso WHERE nombre = :n"),
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

    # Las propuestas no caben en la tabla de antes: se van, con lo suyo.
    con.execute(sa.text(
        "DELETE FROM archivo_cotizacion WHERE cotizacion_id IN "
        "(SELECT id FROM cotizacion WHERE clase = 'propuesta')"))
    con.execute(sa.text("DELETE FROM cotizacion WHERE clase = 'propuesta'"))
    con.execute(sa.text(
        "DELETE FROM texto_cotizacion WHERE clave LIKE 'pro\\_%' "
        "OR clave LIKE 'alcance:%'"))
    op.drop_column("contrato_implantado", "dias_del_mensual")
    op.alter_column("texto_cotizacion", "clave",
                    existing_type=sa.String(length=60),
                    type_=sa.String(length=30), existing_nullable=False)
    op.drop_index("ix_posicion_propuesta_cotizacion_id",
                  table_name="posicion_propuesta")
    op.drop_table("posicion_propuesta")
    for nombre, _tabla, _columnas in FKS:
        op.drop_constraint(nombre, "cotizacion", type_="foreignkey")
    for nombre, _tipo in reversed(COLUMNAS):
        op.drop_column("cotizacion", nombre)
    op.alter_column("cotizacion", "tarifario_id", existing_type=sa.INTEGER(),
                    nullable=False)
    op.drop_constraint("cotizacion_clase_folio_version_key", "cotizacion",
                       type_="unique")
    op.create_unique_constraint("cotizacion_folio_version_key", "cotizacion",
                                ["folio", "version"])
    op.drop_column("cotizacion", "clase")

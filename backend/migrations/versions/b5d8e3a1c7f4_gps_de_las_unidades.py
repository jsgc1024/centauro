"""El GPS de las unidades: Pegasus, de solo lectura.

Decisiones de Salvador, 23 de septiembre (seccion 60 de la bitacora):

* Los dos grupos de Proteccion Ejecutiva de Pegasus, uno por pais
  (`grupo_gps`), y cada unidad con lo ultimo que dijo (`unidad_gps`),
  ligada por la placa con la de Centauro. De la posicion solo la
  ultima: el recorrido no se guarda.
* El camino al punto tambien lo dice la unidad (`trayecto.unidad_*`).
* El segundo testigo de cada marca (`hito.unidad_*`).
* Lo que recorrio cada unidad en el dia y lo que conto de su manejo
  (`asignacion_vehiculo.km_gps`, `excesos_gps`, `bruscos_gps`).
* Las alertas de la unidad: el panico del vehiculo sabe de que unidad
  salio y no se repite (`alerta_incidencia.vehiculo_id`, `origen`); el
  inhibidor y la corriente cortada son alertas del dia con su unidad
  (`alerta.vehiculo_id`).
* El manejo entra a la calificacion del personal con 10 %, que sale de
  estrellas (30 -> 25) e incidencias (25 -> 20). Solo se mueven los
  pesos de los paises que siguen con los de ejemplo; donde alguien ya
  puso los suyos, el manejo entra en cero y lo decide quien los puso.

Revision ID: b5d8e3a1c7f4
Revises: f2a9c4e71b36
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5d8e3a1c7f4"
down_revision: Union[str, None] = "f2a9c4e71b36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DE_EJEMPLO = {"ESTRELLAS": 30, "SATISFACCION": 25, "INCIDENCIAS": 25,
              "CAPACITACION": 10, "EXPERIENCIA": 10}
NUEVOS = {"ESTRELLAS": 25, "INCIDENCIAS": 20}


def upgrade() -> None:
    # Un valor nuevo de un ENUM no se puede usar en la misma transaccion
    # que lo agrega, y abajo se insertan los pesos del manejo.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE tipoalerta ADD VALUE IF NOT EXISTS "
                   "'INHIBIDOR'")
        op.execute("ALTER TYPE tipoalerta ADD VALUE IF NOT EXISTS "
                   "'SIN_CORRIENTE'")
        op.execute("ALTER TYPE dimensionprofesionalismo ADD VALUE IF NOT "
                   "EXISTS 'MANEJO'")

    op.create_table(
        "grupo_gps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pais_id", sa.Integer(), sa.ForeignKey("pais.id"),
                  nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("pegasus_id", sa.Integer(), nullable=True),
        sa.Column("leido_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("panico_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("error_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unidades", sa.Integer(), server_default=sa.text("0"),
                  nullable=False),
        sa.UniqueConstraint("pais_id"),
    )
    op.create_table(
        "unidad_gps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pegasus_id", sa.Integer(), nullable=False),
        sa.Column("grupo_id", sa.Integer(),
                  sa.ForeignKey("grupo_gps.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("placa", sa.String(length=20), nullable=True),
        sa.Column("placa_normal", sa.String(length=20), nullable=True),
        sa.Column("marca_modelo", sa.String(length=80), nullable=True),
        sa.Column("color", sa.String(length=40), nullable=True),
        sa.Column("anio", sa.Integer(), nullable=True),
        sa.Column("vehiculo_id", sa.Integer(),
                  sa.ForeignKey("vehiculo.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("reporte_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lon", sa.Numeric(10, 7), nullable=True),
        sa.Column("velocidad_kmh", sa.Integer(), nullable=True),
        sa.Column("en_movimiento", sa.Boolean(), nullable=True),
        sa.Column("parada_desde", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encendida", sa.Boolean(), nullable=True),
        sa.Column("encendida_desde", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("corriente", sa.Boolean(), nullable=True),
        sa.Column("corriente_desde", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("inhibidor", sa.Boolean(), nullable=True),
        sa.Column("inhibidor_desde", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("odometro_km", sa.Numeric(10, 1), nullable=True),
        sa.Column("leida_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("en_el_grupo", sa.Boolean(), server_default="true",
                  nullable=False),
        sa.UniqueConstraint("pegasus_id"),
    )
    op.create_index("ix_unidad_gps_grupo_id", "unidad_gps", ["grupo_id"])
    op.create_index("ix_unidad_gps_placa_normal", "unidad_gps",
                    ["placa_normal"])
    op.create_index("ix_unidad_gps_vehiculo_id", "unidad_gps",
                    ["vehiculo_id"])

    # El camino, visto por la unidad.
    op.add_column("trayecto", sa.Column(
        "unidad_vehiculo_id", sa.Integer(),
        sa.ForeignKey("vehiculo.id", ondelete="SET NULL"), nullable=True))
    op.add_column("trayecto", sa.Column("unidad_estado", sa.String(14),
                                        nullable=True))
    for columna in ("unidad_distancia_m", "unidad_distancia_anterior_m"):
        op.add_column("trayecto", sa.Column(columna, sa.Integer(),
                                            nullable=True))
    for columna in ("unidad_leida_en", "unidad_anterior_en", "unidad_desde"):
        op.add_column("trayecto", sa.Column(columna, sa.DateTime(),
                                            nullable=True))
    op.add_column("trayecto", sa.Column("unidad_apagada", sa.Boolean(),
                                        nullable=True))

    # El segundo testigo de cada marca.
    op.add_column("hito", sa.Column(
        "unidad_vehiculo_id", sa.Integer(),
        sa.ForeignKey("vehiculo.id", ondelete="SET NULL"), nullable=True))
    op.add_column("hito", sa.Column("unidad_distancia_m", sa.Integer(),
                                    nullable=True))
    op.add_column("hito", sa.Column("unidad_guardada_en", sa.DateTime(),
                                    nullable=True))
    op.add_column("hito", sa.Column("unidad_guardada_m", sa.Integer(),
                                    nullable=True))
    op.add_column("hito", sa.Column("unidad_revisada_en",
                                    sa.DateTime(timezone=True),
                                    nullable=True))

    # Lo que recorrio cada unidad en el dia.
    op.add_column("asignacion_vehiculo",
                  sa.Column("km_gps", sa.Numeric(8, 1), nullable=True))
    for columna in ("km_gps_desde", "km_gps_hasta"):
        op.add_column("asignacion_vehiculo",
                      sa.Column(columna, sa.DateTime(), nullable=True))
    for columna in ("excesos_gps", "bruscos_gps"):
        op.add_column("asignacion_vehiculo",
                      sa.Column(columna, sa.Integer(), nullable=True))
    op.add_column("asignacion_vehiculo",
                  sa.Column("gps_cerrado_en", sa.DateTime(timezone=True),
                            nullable=True))

    # Las alertas de la unidad.
    op.add_column("alerta", sa.Column(
        "vehiculo_id", sa.Integer(),
        sa.ForeignKey("vehiculo.id", ondelete="SET NULL"), nullable=True))
    op.add_column("alerta_incidencia", sa.Column(
        "vehiculo_id", sa.Integer(),
        sa.ForeignKey("vehiculo.id", ondelete="SET NULL"), nullable=True))
    op.add_column("alerta_incidencia",
                  sa.Column("origen", sa.String(80), nullable=True))
    op.create_unique_constraint("alerta_incidencia_origen_key",
                                "alerta_incidencia", ["origen"])

    # El manejo en la calificacion.
    op.add_column("parametro_profesionalismo",
                  sa.Column("puntos_por_evento_manejo", sa.Numeric(5, 2),
                            server_default="3", nullable=False))
    conexion = op.get_bind()
    filas = conexion.execute(sa.text(
        "SELECT pais_id, dimension, peso, activo "
        "FROM peso_profesionalismo")).fetchall()
    por_pais: dict = {}
    for pais_id, dimension, peso, activo in filas:
        por_pais.setdefault(pais_id, {})[str(dimension)] = (
            float(peso) if activo else None)
    for pais_id, pesos in por_pais.items():
        if "MANEJO" in pesos:
            continue
        de_ejemplo = pesos == {k: float(v) for k, v in DE_EJEMPLO.items()}
        if de_ejemplo:
            for dimension, peso in NUEVOS.items():
                conexion.execute(sa.text(
                    "UPDATE peso_profesionalismo SET peso = :peso "
                    "WHERE pais_id = :pais AND dimension = :dim"),
                    {"peso": peso, "pais": pais_id, "dim": dimension})
        conexion.execute(sa.text(
            "INSERT INTO peso_profesionalismo (pais_id, dimension, peso, "
            "activo) VALUES (:pais, 'MANEJO', :peso, true)"),
            {"pais": pais_id, "peso": 10 if de_ejemplo else 0})


def downgrade() -> None:
    conexion = op.get_bind()
    conexion.execute(sa.text(
        "DELETE FROM peso_profesionalismo WHERE dimension = 'MANEJO'"))
    for dimension, peso in NUEVOS.items():
        conexion.execute(sa.text(
            "UPDATE peso_profesionalismo SET peso = :viejo "
            "WHERE dimension = :dim AND peso = :nuevo"),
            {"viejo": DE_EJEMPLO[dimension], "dim": dimension,
             "nuevo": peso})
    op.drop_column("parametro_profesionalismo", "puntos_por_evento_manejo")
    op.drop_constraint("alerta_incidencia_origen_key", "alerta_incidencia",
                       type_="unique")
    op.drop_column("alerta_incidencia", "origen")
    op.drop_column("alerta_incidencia", "vehiculo_id")
    op.execute("DELETE FROM alerta WHERE tipo IN "
               "('INHIBIDOR', 'SIN_CORRIENTE')")
    op.drop_column("alerta", "vehiculo_id")
    for columna in ("gps_cerrado_en", "bruscos_gps", "excesos_gps",
                    "km_gps_hasta", "km_gps_desde", "km_gps"):
        op.drop_column("asignacion_vehiculo", columna)
    for columna in ("unidad_revisada_en", "unidad_guardada_m",
                    "unidad_guardada_en", "unidad_distancia_m",
                    "unidad_vehiculo_id"):
        op.drop_column("hito", columna)
    for columna in ("unidad_apagada", "unidad_desde", "unidad_anterior_en",
                    "unidad_leida_en", "unidad_distancia_anterior_m",
                    "unidad_distancia_m", "unidad_estado",
                    "unidad_vehiculo_id"):
        op.drop_column("trayecto", columna)
    op.drop_index("ix_unidad_gps_vehiculo_id", table_name="unidad_gps")
    op.drop_index("ix_unidad_gps_placa_normal", table_name="unidad_gps")
    op.drop_index("ix_unidad_gps_grupo_id", table_name="unidad_gps")
    op.drop_table("unidad_gps")
    op.drop_table("grupo_gps")

"""El auto subarrendado: se renta para un servicio y se devuelve

Revision ID: a4c9e2f61b80
Revises: f30a6c5b91de
Create Date: 2026-09-13

Cuando no hay la categoria que pide el cliente, o la flota esta saturada,
el consultor renta el auto. Vive en la misma tabla que la flota propia
porque para la operacion es una unidad igual —se asigna, se le sube gente,
sale en el task sheet— y lo que la distingue es el sello de rentado y el
servicio que la pidio.

La placa deja de ser unica en toda la tabla: entre las propias si, pero
un auto de renta puede volver meses despues en otro servicio y eso es un
alta nueva, no un choque. Dos indices parciales guardan las dos reglas.
"""
import sqlalchemy as sa
from alembic import op

revision = "a4c9e2f61b80"
down_revision = "f30a6c5b91de"
branch_labels = None
depends_on = None

MOTIVOS = ("categoria_no_disponible", "saturacion", "pedido_especial")


def upgrade():
    motivo = sa.Enum(*MOTIVOS, name="motivorenta")
    motivo.create(op.get_bind(), checkfirst=True)

    op.add_column("vehiculo", sa.Column(
        "rentado", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("vehiculo", sa.Column(
        "servicio_id", sa.Integer(), nullable=True))
    op.add_column("vehiculo", sa.Column(
        "marca_modelo", sa.String(length=80), nullable=True))
    op.add_column("vehiculo", sa.Column(
        "arrendadora", sa.String(length=120), nullable=True))
    op.add_column("vehiculo", sa.Column(
        "arrendadora_telefono", sa.String(length=40), nullable=True))
    op.add_column("vehiculo", sa.Column("motivo_renta", motivo, nullable=True))
    op.create_foreign_key("fk_vehiculo_servicio", "vehiculo", "servicio",
                          ["servicio_id"], ["id"])

    # La unica de toda la tabla se cambia por las dos reglas que de
    # verdad aplican.
    op.execute("ALTER TABLE vehiculo DROP CONSTRAINT IF EXISTS vehiculo_placa_key")
    op.execute("""
        CREATE UNIQUE INDEX uq_vehiculo_placa_propia
        ON vehiculo (placa) WHERE rentado = false
    """)
    # Y la misma renta capturada dos veces en el mismo servicio tampoco.
    op.execute("""
        CREATE UNIQUE INDEX uq_vehiculo_placa_rentada
        ON vehiculo (servicio_id, placa) WHERE rentado = true
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_vehiculo_placa_rentada")
    op.execute("DROP INDEX IF EXISTS uq_vehiculo_placa_propia")
    # Los rentados se van: sin ellos la placa vuelve a ser unica.
    op.execute("DELETE FROM asignacion_vehiculo WHERE vehiculo_id IN "
               "(SELECT id FROM vehiculo WHERE rentado = true)")
    op.execute("DELETE FROM vehiculo WHERE rentado = true")
    op.drop_constraint("fk_vehiculo_servicio", "vehiculo", type_="foreignkey")
    for columna in ("motivo_renta", "arrendadora_telefono", "arrendadora",
                    "marca_modelo", "servicio_id", "rentado"):
        op.drop_column("vehiculo", columna)
    sa.Enum(name="motivorenta").drop(op.get_bind(), checkfirst=True)
    op.create_unique_constraint("vehiculo_placa_key", "vehiculo", ["placa"])

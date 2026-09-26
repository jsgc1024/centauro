"""El archivo de los comprobantes (seccion 69)

Decision de Salvador, 25 de septiembre: tres meses despues de la factura
--o de la aprobacion de finanzas, mientras Odoo no este conectado--, la
foto del ticket y la de la devolucion salen de la base y se van a un
deposito de Google, donde se guardan seis anos. La foto se muda; el
registro se queda.

Aqui solo se agregan las columnas que dicen donde quedo cada foto, su
huella y cuando se fue. La migracion no mueve ninguna foto: eso lo hace
la tarea de la noche, y solo cuando el archivo se prende en el .env.

Revision ID: b8e4f1a2c739
Revises: d6a2f9c41e7b
"""
import sqlalchemy as sa
from alembic import op

revision = "b8e4f1a2c739"
down_revision = "d6a2f9c41e7b"
branch_labels = None
depends_on = None

TABLAS = ("comprobante", "devolucion_viatico")


def upgrade() -> None:
    for tabla in TABLAS:
        op.add_column(tabla, sa.Column("archivado_en", sa.DateTime(),
                                       nullable=True))
        op.add_column(tabla, sa.Column("archivo_objeto", sa.String(300),
                                       nullable=True))
        op.add_column(tabla, sa.Column("archivo_md5", sa.String(32),
                                       nullable=True))
        op.add_column(tabla, sa.Column("archivo_bytes", sa.Integer(),
                                       nullable=True))


def downgrade() -> None:
    # Bajar la migracion no trae las fotos de vuelta: siguen en el
    # archivo, y sin estas columnas nadie sabria donde. Por eso se niega
    # si ya hay alguna archivada.
    conexion = op.get_bind()
    for tabla in TABLAS:
        archivadas = conexion.execute(sa.text(
            f"SELECT count(*) FROM {tabla} WHERE archivado_en IS NOT NULL"
        )).scalar()
        if archivadas:
            raise RuntimeError(
                f"{tabla} tiene {archivadas} fotos en el archivo. Sin estas "
                "columnas nadie sabria donde estan: no se baja.")
    for tabla in TABLAS:
        for columna in ("archivo_bytes", "archivo_md5", "archivo_objeto",
                        "archivado_en"):
            op.drop_column(tabla, columna)

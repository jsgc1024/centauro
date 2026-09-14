"""El comprobante guarda la foto, no un enlace

Revision ID: a47e92b0c5d3
Revises: f3c81d5b620e
"""
from alembic import op
import sqlalchemy as sa


revision = "a47e92b0c5d3"
down_revision = "f3c81d5b620e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """La foto del ticket vive dentro del registro.

    El comprobante tenia un `archivo_url` de 400 caracteres, pensado para
    un enlace a un archivo en otro lado. Pero el que comprueba es un
    agente parado en una gasolinera con el ticket en la mano: lo que
    tiene es la camara del telefono, no un archivo que subir a ningun
    lado.

    Se guarda como data URI dentro del propio registro, igual que el
    comprobante de una compra y la senal de identificacion: el dia que
    un enlace no cargue, la comprobacion se queda sin prueba y el
    descuento se lo come alguien que si gasto el dinero.
    """
    op.add_column("comprobante", sa.Column("imagen", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("comprobante", "imagen")

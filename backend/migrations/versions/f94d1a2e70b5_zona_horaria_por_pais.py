"""Cada pais tiene su hora

Todo el sistema decidia con un solo reloj: el del servidor. Las columnas
de fecha son naive y guardan hora de pared del pais del servicio, asi
que compararlas contra la hora del servidor dejaba a Brasil corrido tres
horas y a Venezuela dos: el conductor puntual caia fuera de la ventana
permitida, el servicio en curso salia siempre "sin reporte" en la banda
roja de la central, y el aviso de horas extra —una ventana de media
hora— no coincidia nunca.

Las filas que ya existen quedan en la hora de Mexico, que es lo que el
sistema venia asumiendo para todas: asi nada cambia de comportamiento
hasta que alguien le ponga su zona a Brasil, y ahi es cuando Brasil
empieza a estar bien.

Revision ID: f94d1a2e70b5
Revises: e83c4a19b027
"""
import sqlalchemy as sa
from alembic import op

revision = "f94d1a2e70b5"
down_revision = "e83c4a19b027"
branch_labels = None
depends_on = None

# Nombre IANA por codigo de pais. Lo que no este aqui se queda con la
# hora de la casa, que es como estaba antes.
ZONAS = {
    "MX": "America/Mexico_City",
    "BR": "America/Sao_Paulo",
    "VE": "America/Caracas",
    "CO": "America/Bogota",
    "AR": "America/Argentina/Buenos_Aires",
    "CL": "America/Santiago",
    "PE": "America/Lima",
    "PA": "America/Panama",
}


def upgrade() -> None:
    op.add_column("pais", sa.Column(
        "zona_horaria", sa.String(64), nullable=False,
        server_default="America/Mexico_City"))
    for codigo, zona in ZONAS.items():
        op.execute(sa.text(
            "UPDATE pais SET zona_horaria = :zona WHERE codigo = :codigo"
        ).bindparams(zona=zona, codigo=codigo))


def downgrade() -> None:
    op.drop_column("pais", "zona_horaria")

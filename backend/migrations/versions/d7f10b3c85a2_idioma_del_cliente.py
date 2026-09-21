"""En que idioma lee cada quien

Los diez correos salian en espanol fijo, mientras el task sheet del
mismo servicio salia en ingles, portugues o espanol. Asi que un
ejecutivo extranjero recibia su hoja en su idioma y dos horas despues un
correo que no entendia.

Dos columnas y no una porque casi nunca coinciden: el principal suele
ser extranjero --arranca en ingles, que es la regla que textos.py ya
tenia escrita-- y el solicitante es gente local del pais donde se
ejecuta el servicio. Decision de Salvador (20 sep).

El solicitante admite nulo a proposito: vacio quiere decir "el idioma de
su pais", que se resuelve al mandar. Asi los servicios que ya existen
quedan con la regla nueva sin tener que rellenarlos uno por uno.

Revision ID: d7f10b3c85a2
Revises: c5e93b02fa71
"""
import sqlalchemy as sa
from alembic import op

revision = "d7f10b3c85a2"
down_revision = "c5e93b02fa71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("servicio",
                  sa.Column("idioma_ejecutivo", sa.String(2),
                            nullable=False, server_default="en"))
    op.add_column("servicio",
                  sa.Column("idioma_solicitante", sa.String(2), nullable=True))
    # Y el aviso guarda en que idioma se escribio, porque el despachador
    # todavia pone cosas suyas encima --el texto del boton, la linea de
    # lo que vence-- y tiene que decirlas en el mismo idioma.
    op.add_column("notificacion",
                  sa.Column("idioma", sa.String(2), nullable=True))


def downgrade() -> None:
    op.drop_column("notificacion", "idioma")
    op.drop_column("servicio", "idioma_solicitante")
    op.drop_column("servicio", "idioma_ejecutivo")

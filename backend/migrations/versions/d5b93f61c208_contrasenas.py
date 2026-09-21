"""Recuperar la contrasena, y tirar las sesiones al cambiarla

Tres columnas:

`invitacion.tipo` separa la primera contrasena de la olvidada. Usan el
mismo esqueleto y no duran lo mismo: la invitacion tres dias, porque
quien entra nuevo quiza no revisa el correo hoy; la recuperacion dos
horas, porque es la llave de una cuenta que ya tiene cosas adentro.

`invitacion.anulado_en` deja que un enlace nuevo mate a los anteriores.
Sin eso, el correo de recuperacion de hace una semana sigue abriendo la
cuenta.

`usuario.sesiones_desde` invalida todo token emitido antes de esa hora.
Es lo que hace que cambiar la contrasena tire las sesiones abiertas: el
token no tiene estado, asi que sin esta columna el que se la robo
seguiria adentro doce horas mas, con la contrasena ya cambiada.

Revision ID: d5b93f61c208
Revises: c3e8a5d1f742
"""
import sqlalchemy as sa
from alembic import op

revision = "d5b93f61c208"
down_revision = "c3e8a5d1f742"
branch_labels = None
depends_on = None

TIPO = sa.Enum("INVITACION", "RECUPERACION", name="tipoinvitacion")


def upgrade() -> None:
    TIPO.create(op.get_bind(), checkfirst=True)
    op.add_column("invitacion",
                  sa.Column("tipo", TIPO, nullable=True))
    op.execute("UPDATE invitacion SET tipo = 'INVITACION' WHERE tipo IS NULL")
    op.alter_column("invitacion", "tipo", nullable=False)
    op.add_column("invitacion",
                  sa.Column("anulado_en", sa.DateTime(), nullable=True))
    op.add_column("usuario",
                  sa.Column("sesiones_desde", sa.DateTime(timezone=True),
                            nullable=True))


def downgrade() -> None:
    op.drop_column("usuario", "sesiones_desde")
    op.drop_column("invitacion", "anulado_en")
    op.drop_column("invitacion", "tipo")
    TIPO.drop(op.get_bind(), checkfirst=True)

"""Paso 2a: lo que la base necesita para contrasenas.

Dos cosas:

`Invitacion.tipo` --la primera contrasena y la olvidada usan el mismo
esqueleto pero no son lo mismo: una invitacion vive tres dias porque el
que entra nuevo quiza no revisa el correo hoy; una recuperacion tiene que
durar poco, porque es la llave de una cuenta que ya existe.

`Usuario.sesiones_desde` --cambiar la contrasena tiene que tirar las
sesiones abiertas. Si alguien te robo la sesion y cambias la contrasena,
esperas que se salga; con un token sin estado no se salia, y la contrasena
nueva no le quitaba nada durante doce horas.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

R = RAIZ / "backend/app/models.py"
s = R.read_text()

VIEJO = '''class Invitacion(Base):
    """Token que se manda por correo para que el empleado cree su contrasena."""
    __tablename__ = "invitacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    token: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime)
    usado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    usuario: Mapped[Usuario] = relationship()'''
NUEVO = '''class TipoInvitacion(str, enum.Enum):
    """Las dos razones por las que se manda un enlace de contrasena.

    Usan el mismo esqueleto y no son lo mismo: la invitacion vive tres
    dias porque quien entra nuevo quiza no revisa el correo hoy; la
    recuperacion dura poco, porque es la llave de una cuenta que ya
    existe y ya tiene cosas adentro.
    """
    INVITACION = "invitacion"
    RECUPERACION = "recuperacion"


class Invitacion(Base):
    """Token que se manda por correo para crear o recuperar la contrasena."""
    __tablename__ = "invitacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    token: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    tipo: Mapped[TipoInvitacion] = mapped_column(
        Enum(TipoInvitacion), default=TipoInvitacion.INVITACION)
    expira_en: Mapped[datetime] = mapped_column(DateTime)
    usado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Un enlace nuevo mata a los anteriores: si no, el correo de hace una
    # semana sigue abriendo la cuenta.
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    usuario: Mapped[Usuario] = relationship()'''
assert s.count(VIEJO) == 1, "no encontre Invitacion"
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    persona: Mapped[Persona] = relationship()'''
NUEVO = '''    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Todo token emitido antes de esta hora deja de valer. Es lo que hace
    # que cambiar la contrasena tire las sesiones abiertas: con un token
    # sin estado, el que te la robo seguiria adentro doce horas mas.
    sesiones_desde: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    persona: Mapped[Persona] = relationship()'''
assert s.count(VIEJO) == 1, "no encontre Usuario"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("models.py: tipo de invitacion y sesiones_desde")

(RAIZ / "backend/migrations/versions/d5b93f61c208_contrasenas.py").write_text(
'''"""Recuperar la contrasena, y tirar las sesiones al cambiarla

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
''')
print("migracion d5b93f61c208")

"""Paso 3a: lo que la base necesita para el codigo de campo.

`TipoInvitacion.CODIGO_CAMPO` --el tercer motivo por el que se abre una
puerta de contrasena: el agente llamo a su consultor y el consultor le
dicto cuatro digitos.

`Invitacion.fallos` --el contador de intentos fallidos vive en la base y
no en Redis a proposito. `intentos.py` se abre si Redis no contesta, que
para el inicio de sesion es lo correcto --mejor que se pueda intentar de
mas un rato a que nadie pueda trabajar-- pero aqui seria dejar cuatro
digitos sin candado, y diez mil combinaciones se prueban en segundos.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

R = RAIZ / "backend/app/models.py"
s = R.read_text()

VIEJO = '''    INVITACION = "invitacion"
    RECUPERACION = "recuperacion"'''
NUEVO = '''    INVITACION = "invitacion"
    RECUPERACION = "recuperacion"
    # Cuatro digitos que el consultor o la central le dictan por
    # telefono al personal de campo. Su correo es personal y la empresa
    # no lo controla, asi que lo suyo no va por correo.
    CODIGO_CAMPO = "codigo_campo"'''
assert s.count(VIEJO) == 1, "no encontre TipoInvitacion"
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    # Un enlace nuevo mata a los anteriores: si no, el correo de hace una
    # semana sigue abriendo la cuenta.
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)'''
NUEVO = '''    # Un enlace nuevo mata a los anteriores: si no, el correo de hace una
    # semana sigue abriendo la cuenta.
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Cuantas veces se fallo. Solo cuenta para el codigo de cuatro
    # digitos: a los cinco fallos el codigo se muere y hay que pedir
    # otro. Vive aqui y no en Redis porque `intentos.py` se abre si Redis
    # no contesta, y eso dejaria diez mil combinaciones sin candado.
    fallos: Mapped[int] = mapped_column(Integer, default=0)'''
assert s.count(VIEJO) == 1, "no encontre anulado_en"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("models.py: codigo de campo y contador de fallos")

(RAIZ / "backend/migrations/versions/e1a742c9b366_codigo_de_campo.py").write_text(
'''"""El codigo de cuatro digitos del personal de campo

El agente llama a su consultor --o a la central, que esta despierta a las
5:40-- y le dictan cuatro digitos. No va por correo: el correo del
personal de campo es personal y la empresa no lo controla.

Cuatro digitos son diez mil combinaciones, asi que el contador de fallos
vive aqui y no en Redis: `intentos.py` se abre si Redis no contesta --que
para el inicio de sesion es lo correcto-- y eso dejaria el codigo sin
candado justo el dia malo. A los cinco fallos se muere y hay que pedir
otro.

Revision ID: e1a742c9b366
Revises: d5b93f61c208
"""
import sqlalchemy as sa
from alembic import op

revision = "e1a742c9b366"
down_revision = "d5b93f61c208"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE tipoinvitacion ADD VALUE IF NOT EXISTS 'CODIGO_CAMPO'")
    op.add_column("invitacion",
                  sa.Column("fallos", sa.Integer(), nullable=True))
    op.execute("UPDATE invitacion SET fallos = 0 WHERE fallos IS NULL")
    op.alter_column("invitacion", "fallos", nullable=False,
                    server_default="0")


def downgrade() -> None:
    op.drop_column("invitacion", "fallos")
    # El valor del enum no se quita: Postgres no sabe quitar valores de
    # un tipo, y dejarlo no estorba.
''')
print("migracion e1a742c9b366")

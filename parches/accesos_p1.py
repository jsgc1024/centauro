"""Paso 1a: la bitacora de administracion.

La que existe esta amarrada a un servicio --`RegistroAccion.servicio_id`
es obligatorio-- y un cambio de acceso no tiene servicio al cual
colgarse. Esta es para lo que no pasa sobre un servicio: accesos hoy,
catalogos y tarifarios despues.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

R = RAIZ / "backend/app/models.py"
s = R.read_text()

ANCLA = "# ================================================================ COTIZACION"
NUEVO = '''class RegistroAdmin(Base):
    """Bitacora de lo que no pasa sobre un servicio.

    Quien le cerro la puerta a quien, quien le cambio el puesto, quien
    movio un precio. La otra bitacora --`RegistroAccion`-- exige un
    servicio, y ninguna de estas cosas lo tiene.

    Guarda el antes y el despues en texto a proposito: dentro de un ano,
    "consultor -> finanzas" se lee sin tener que reconstruir que
    significaba el numero 3 en aquel momento.
    """
    __tablename__ = "registro_admin"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    # Se guarda tambien la persona y el rol de quien actuo: si su acceso
    # se borra o cambia de rol despues, el renglon sigue diciendo quien
    # era cuando lo hizo.
    persona_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    rol: Mapped[Rol] = mapped_column(Enum(Rol))

    accion: Mapped[str] = mapped_column(String(80))
    # Sobre que: "usuario", "tarifario", "comision"...
    objeto: Mapped[str] = mapped_column(String(40), index=True)
    objeto_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    antes: Mapped[str | None] = mapped_column(String(200), nullable=True)
    despues: Mapped[str | None] = mapped_column(String(200), nullable=True)
    detalle: Mapped[str | None] = mapped_column(String(400), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    persona: Mapped["Persona | None"] = relationship(foreign_keys=[persona_id])


# ================================================================ COTIZACION'''
assert s.count(ANCLA) == 1, "no encontre el separador de cotizacion"
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("models.py: RegistroAdmin")

(RAIZ / "backend/migrations/versions/c3e8a5d1f742_bitacora_de_administracion.py"
 ).write_text('''"""Bitacora de lo que no pasa sobre un servicio

La bitacora que existia --`registro_accion`-- tiene `servicio_id`
obligatorio: esta amarrada a un servicio por diseno. Un cambio de acceso
no tiene servicio al cual colgarse, y tampoco un cambio de tarifario.

Por eso cerrarle la puerta a alguien, cambiarle el puesto o mover un
precio no dejaban rastro de quien lo hizo. El primero no se podia hacer
siquiera; los otros dos si, y en silencio.

Revision ID: c3e8a5d1f742
Revises: b7f21c4e9a03
"""
import sqlalchemy as sa
from alembic import op

revision = "c3e8a5d1f742"
down_revision = "b7f21c4e9a03"
branch_labels = None
depends_on = None

ROL = sa.Enum("personal_seguridad", "central", "consultor",
              "director_operaciones", "director_general", "finanzas", "admin",
              name="rol", create_type=False)


def upgrade() -> None:
    op.create_table(
        "registro_admin",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.Integer(), nullable=True),
        sa.Column("rol", ROL, nullable=False),
        sa.Column("accion", sa.String(80), nullable=False),
        sa.Column("objeto", sa.String(40), nullable=False),
        sa.Column("objeto_id", sa.Integer(), nullable=True),
        sa.Column("antes", sa.String(200), nullable=True),
        sa.Column("despues", sa.String(200), nullable=True),
        sa.Column("detalle", sa.String(400), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["persona_id"], ["persona.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_registro_admin_objeto", "registro_admin", ["objeto"])


def downgrade() -> None:
    op.drop_index("ix_registro_admin_objeto", table_name="registro_admin")
    op.drop_table("registro_admin")
''')
print("migracion c3e8a5d1f742")

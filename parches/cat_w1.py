"""Paso 5e: las categorias de acceso.

Tres piezas y una regla:

  CategoriaAcceso      un puesto configurable: que actividades trae y
                       cuanto dura su sesion.
  ActividadDeCategoria que actividades trae cada una.
  PermisoExtra         lo que una persona puede de mas que su categoria.

**La regla, decidida por Salvador: las categorias quitan, las
excepciones solo dan.** Si alguien no debe poder algo, se le hace una
categoria que no lo traiga --"Consultor junior"-- y su renglon dice la
verdad. Una excepcion que quitara dejaria el renglon diciendo "Consultor"
cuando no lo es, y para saber que puede habria que abrir su ficha y
acordarse de que existe.

Sin categoria asignada, el usuario cae en los permisos de su rol, que es
como funciona hoy. Por eso el dia que esto se aplique no cambia nada
para nadie.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

R = RAIZ / "backend/app/models.py"
s = R.read_text()

ANCLA = '''class TipoInvitacion(str, enum.Enum):'''
NUEVO = '''class CategoriaAcceso(Base):
    """Un puesto configurable: que puede tocar y cuanto dura su sesion.

    Existe para que "consultor junior --consultor que no decide cuanto
    dinero se deposita--" sea una cosa con nombre, y no un permiso
    suelto colgado de una persona.
    """
    __tablename__ = "categoria_acceso"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Cuanto dura la sesion de quien la trae. Vacio: las doce horas de
    # siempre. Doce parejas para todos no sirven: quien esta en la calle
    # vuelve a entrar a media jornada, y una computadora de oficina que
    # se queda prendida sigue abierta toda la tarde.
    horas_sesion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    actividades: Mapped[list["ActividadDeCategoria"]] = relationship(
        back_populates="categoria", cascade="all, delete-orphan")


class ActividadDeCategoria(Base):
    """Que trae una categoria. Una fila por actividad."""
    __tablename__ = "actividad_de_categoria"
    __table_args__ = (UniqueConstraint("categoria_id", "actividad"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    categoria_id: Mapped[int] = mapped_column(
        ForeignKey("categoria_acceso.id", ondelete="CASCADE"))
    # El nombre de la actividad, como lo declara `permisos.py`. Se guarda
    # el texto y no una llave foranea porque el catalogo vive en el
    # codigo: es el codigo el que sabe que puertas existen.
    actividad: Mapped[str] = mapped_column(String(60), index=True)

    categoria: Mapped[CategoriaAcceso] = relationship(
        back_populates="actividades")


class PermisoExtra(Base):
    """Lo que una persona puede de mas que su categoria.

    Solo da, nunca quita. Una excepcion que quitara dejaria su renglon
    diciendo "Consultor" cuando no lo es; para quitar se le hace una
    categoria propia, que si se lee de un vistazo.

    Lleva quien lo dio y cuando: un permiso suelto sin dueno es el que
    nadie se atreve a quitar.
    """
    __tablename__ = "permiso_extra"
    __table_args__ = (UniqueConstraint("usuario_id", "actividad"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"))
    actividad: Mapped[str] = mapped_column(String(60))
    dado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    dado_por: Mapped["Persona | None"] = relationship(
        foreign_keys=[dado_por_id])


class TipoInvitacion(str, enum.Enum):'''
assert s.count(ANCLA) == 1, "no encontre TipoInvitacion"
s = s.replace(ANCLA, NUEVO)

VIEJO = '''    rol: Mapped[Rol] = mapped_column(Enum(Rol))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)'''
NUEVO = '''    rol: Mapped[Rol] = mapped_column(Enum(Rol))
    # Su puesto configurable. Vacio: cae en los permisos de su rol, que
    # es como funciono el sistema hasta que existieron las categorias.
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categoria_acceso.id"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)'''
assert s.count(VIEJO) == 1, "no encontre el modelo Usuario"
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    persona: Mapped[Persona] = relationship()


class TipoRevision(str, enum.Enum):'''
NUEVO = '''    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    persona: Mapped[Persona] = relationship()
    categoria: Mapped["CategoriaAcceso | None"] = relationship()


class TipoRevision(str, enum.Enum):'''
assert s.count(VIEJO) == 1, "no encontre el final de Usuario"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("models.py: CategoriaAcceso, ActividadDeCategoria y PermisoExtra")

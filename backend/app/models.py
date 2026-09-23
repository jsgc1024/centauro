"""Modelo de datos - Catalogos y tarifario de Centauro."""
import enum
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer,
    Numeric, String, Text, Time, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


# ---------------------------------------------------------------- enums

class CodigoModalidad(str, enum.Enum):
    FULL_DAY = "full_day"
    MEDIO_DIA = "medio_dia"
    TRANSFER = "transfer"


class ConceptoViatico(str, enum.Enum):
    ALIMENTOS = "alimentos"
    HOSPEDAJE = "hospedaje"
    COMBUSTIBLE = "combustible"
    CASETAS = "casetas"
    TRASLADO_PERSONAL = "traslado_personal"
    OTROS = "otros"


class TipoServicio(str, enum.Enum):
    """Vive aqui arriba, con los demas enums, porque el tabulador de
    viaticos lo necesita y ese se declara mucho antes que el servicio."""
    EVENTUAL = "eventual"
    IMPLANTADO = "implantado"


class CodigoVestimenta(str, enum.Enum):
    """Como se presenta el equipo. Lista cerrada de tres y no texto
    libre: "traje oscuro sin corbata" escrito a mano en cada servicio se
    lee distinto cada vez, y quien lo tiene que cumplir es alguien que
    lee la app a las cinco de la manana.

    Solo aplica al eventual. El implantado trabaja todos los dias con el
    mismo cliente y su vestimenta se acuerda una vez, no servicio por
    servicio. Decision de Salvador (20 sep).
    """
    CASUAL = "casual"
    SEMIFORMAL = "semiformal"
    FORMAL = "formal"


class NivelHospital(str, enum.Enum):
    """Hasta donde llega un hospital.

    Es lista cerrada y no texto libre porque de aqui sale la regla que
    garantiza un quirofano en la referencia medica. Escrito a mano,
    "3er nivel" no coincidia con nada, contaba como cero y la regla
    dejaba de proteger sin avisarle a nadie.
    """
    PRIMERO = "primer_nivel"
    SEGUNDO = "segundo_nivel"
    TERCERO = "tercer_nivel"


class EscenarioViatico(str, enum.Enum):
    FULL_DAY_LOCAL = "full_day_local"
    FULL_DAY_FORANEO = "full_day_foraneo"
    MEDIO_DIA = "medio_dia"
    TRANSFER = "transfer"


class Moneda(str, enum.Enum):
    MXN = "MXN"
    BRL = "BRL"
    USD = "USD"
    VES = "VES"


# ---------------------------------------------------------------- pais / plaza

class Pais(Base):
    """Cada pais define su propia jornada laboral y moneda."""
    __tablename__ = "pais"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(2), unique=True)          # MX, BR, VE
    nombre: Mapped[str] = mapped_column(String(80))
    # Clave lada internacional: +52, +55, +58. El ejecutivo suele ser
    # extranjero y marca desde su celular, asi que ningun telefono del
    # task sheet puede ir sin ella.
    lada: Mapped[str] = mapped_column(String(6), server_default="")
    # Cuanto antes tiene que estar el equipo en el punto de encuentro.
    # En aeropuerto se mide contra la hora del vuelo; en cualquier otro
    # lugar, contra la hora de presentacion.
    anticipacion_aeropuerto_min: Mapped[int] = mapped_column(
        Integer, default=45, server_default="45")
    anticipacion_min: Mapped[int] = mapped_column(
        Integer, default=30, server_default="30")
    moneda_local: Mapped[Moneda] = mapped_column(Enum(Moneda))
    # En que idioma se le habla a la gente de este pais. Decision de
    # Salvador (19 sep) para la app de campo: el agente no elige idioma
    # --va con una mano y prisa, y un boton que se toca sin querer y le
    # deja la app en portugues a las seis de la manana es peor que el
    # problema que resuelve--. Lo toma del pais donde esta su plaza.
    #
    # Va como texto de dos letras y no como ENUM de Postgres, igual que
    # el resto: agregar un idioma manana no deberia necesitar tocar la
    # base.
    idioma: Mapped[str] = mapped_column(String(2), default="es",
                                        server_default="es")
    # Que hora es alla. Nombre IANA: America/Mexico_City,
    # America/Sao_Paulo, America/Caracas.
    #
    # Las columnas de fecha del sistema son naive y guardan hora de
    # pared del pais del servicio: un servicio de Sao Paulo que arranca
    # a las 07:00 guarda 07:00. Sin esta columna, todo se comparaba
    # contra el reloj del servidor, y con el contenedor en Mexico eso
    # dejaba a Brasil corrido tres horas: el conductor puntual caia
    # fuera de la ventana permitida, el servicio en curso salia siempre
    # "sin reporte" en la banda roja de la central, y el aviso de horas
    # extra —una ventana de media hora— no coincidia nunca.
    zona_horaria: Mapped[str] = mapped_column(
        String(64), default="America/Mexico_City",
        server_default="America/Mexico_City")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    plazas: Mapped[list["Plaza"]] = relationship(back_populates="pais")
    modalidades: Mapped[list["Modalidad"]] = relationship(back_populates="pais")


class Plaza(Base):
    """Ciudad con recurso local (personal y flota) o sin el."""
    __tablename__ = "plaza"
    __table_args__ = (UniqueConstraint("pais_id", "nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    nombre: Mapped[str] = mapped_column(String(80))
    tiene_recurso_local: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Las plazas de operacion permanente: siempre estan en la lista,
    # tengan servicio esta semana o no.
    fija: Mapped[bool] = mapped_column(Boolean, default=False,
                                       server_default="false")
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    pais: Mapped[Pais] = relationship(back_populates="plazas")


# ---------------------------------------------------------------- recursos

class PerfilPersonal(Base):
    """Los roles con los que se cubre un servicio.

    Conductor de seguridad, agente de seguridad, coordinador de
    seguridad y consultor de seguridad. En la consola se llaman roles y
    no perfiles porque no son lo que una persona *es*, sino con que va
    ese dia: el personal de seguridad es general y el rol lo decide el
    consultor en cada tarea.

    De aqui cuelgan el precio al cliente y la comision que se le paga,
    asi que es lista cerrada: escrito a mano, un rol nuevo no coincide
    con ninguna tarifa y el servicio sale sin precio.
    """
    __tablename__ = "perfil_personal"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CategoriaVehiculo(Base):
    """El rendimiento se define por categoria; sirve para estimar combustible."""
    __tablename__ = "categoria_vehiculo"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    blindado: Mapped[bool] = mapped_column(Boolean, default=False)
    rendimiento_km_litro: Mapped[float] = mapped_column(Numeric(5, 2))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Sus fotos representativas, una por color (seccion 52).
    variantes: Mapped[list["FotoCategoria"]] = relationship(
        back_populates="categoria", cascade="all, delete-orphan")

    @property
    def fotos(self) -> list[str]:
        """Los colores que tienen foto; "" es la base. La lista de
        categorias dice esto y no carga las imagenes."""
        return sorted(f.color for f in self.variantes)


class FotoCategoria(Base):
    """La foto representativa de una categoria, en un color.

    Decision de Salvador (23 sep): la unidad no lleva su foto real sino
    la de su categoria, pero respetando su color --la Suburban negra se
    ve negra--. La base va sin color ("") y cada color aparte; la
    unidad ensena la de su color y, si no hay, la base.
    """
    __tablename__ = "foto_categoria"
    __table_args__ = (UniqueConstraint("categoria_id", "color"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    categoria_id: Mapped[int] = mapped_column(
        ForeignKey("categoria_vehiculo.id", ondelete="CASCADE"), index=True)
    # Como lo deja color_de(): la primera palabra, sin acentos.
    color: Mapped[str] = mapped_column(String(40), default="",
                                       server_default="")
    # Diferida: saber que colores hay no tiene por que traer las fotos.
    foto_url: Mapped[str] = mapped_column(Text, deferred=True)
    cargada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    categoria: Mapped[CategoriaVehiculo] = relationship(
        back_populates="variantes")


class Modalidad(Base):
    """Jornada parametrizable por pais: MX full day 12h, BR eventual 10h."""
    __tablename__ = "modalidad"
    __table_args__ = (UniqueConstraint("pais_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    codigo: Mapped[CodigoModalidad] = mapped_column(Enum(CodigoModalidad))
    horas: Mapped[float] = mapped_column(Numeric(4, 2))
    horas_descanso: Mapped[float] = mapped_column(Numeric(4, 2), default=0)
    aplica_horas_extra: Mapped[bool] = mapped_column(Boolean, default=False)
    bloquea_dia_completo: Mapped[bool] = mapped_column(Boolean, default=False)
    # Recorrido tipico del dia. Se usa para proponer el combustible sin
    # que nadie tenga que adivinar; el consultor lo corrige cuando el
    # servicio no se parece al promedio.
    km_estimados: Mapped[int | None] = mapped_column(Integer, nullable=True)

    pais: Mapped[Pais] = relationship(back_populates="modalidades")


# ---------------------------------------------------------------- cliente

class Cliente(Base):
    """El maestro vive en Odoo; aqui solo la referencia y su tarifario."""
    __tablename__ = "cliente"

    id: Mapped[int] = mapped_column(primary_key=True)
    odoo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    nombre: Mapped[str] = mapped_column(String(160))
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    tarifario_id: Mapped[int | None] = mapped_column(ForeignKey("tarifario.id"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    tarifario: Mapped["Tarifario | None"] = relationship(back_populates="clientes")
    solicitantes: Mapped[list["Solicitante"]] = relationship(back_populates="cliente")


class Solicitante(Base):
    """Quien pide servicios a nombre de un cliente.

    Se da de alta la primera vez que pide un servicio y queda guardado:
    en los siguientes el consultor lo elige de la lista en vez de volver a
    capturar correo y telefono. Es tambien la lista de quien esta
    autorizado a solicitar servicios de ese cliente.
    """
    __tablename__ = "solicitante"
    __table_args__ = (UniqueConstraint("cliente_id", "correo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    nombre: Mapped[str] = mapped_column(String(160))
    apellidos: Mapped[str | None] = mapped_column(String(160), nullable=True)
    correo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)
    puesto: Mapped[str | None] = mapped_column(String(120), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    cliente: Mapped["Cliente"] = relationship(back_populates="solicitantes")

    @property
    def completo(self) -> str | None:
        return _nombre_completo(self.nombre, self.apellidos)


# ---------------------------------------------------------------- tarifario

class Tarifario(Base):
    """Por cliente, aunque muchos comparten el mismo."""
    __tablename__ = "tarifario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    vigencia_desde: Mapped[date] = mapped_column(Date)
    vigencia_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    clientes: Mapped[list[Cliente]] = relationship(back_populates="tarifario")
    tarifas_recurso: Mapped[list["TarifaRecurso"]] = relationship(
        back_populates="tarifario", cascade="all, delete-orphan")
    tarifas_vehiculo: Mapped[list["TarifaVehiculo"]] = relationship(
        back_populates="tarifario", cascade="all, delete-orphan")


class TarifaRecurso(Base):
    """Precio de venta por perfil de personal y modalidad."""
    __tablename__ = "tarifa_recurso"
    __table_args__ = (UniqueConstraint("tarifario_id", "perfil_id", "modalidad_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tarifario_id: Mapped[int] = mapped_column(ForeignKey("tarifario.id"))
    perfil_id: Mapped[int] = mapped_column(ForeignKey("perfil_personal.id"))
    modalidad_id: Mapped[int] = mapped_column(ForeignKey("modalidad.id"))
    precio: Mapped[float] = mapped_column(Numeric(12, 2))
    precio_hora_extra: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    tarifario: Mapped[Tarifario] = relationship(back_populates="tarifas_recurso")
    perfil: Mapped[PerfilPersonal] = relationship()
    modalidad: Mapped[Modalidad] = relationship()


class TarifaVehiculo(Base):
    """Precio de venta por categoria de vehiculo y modalidad."""
    __tablename__ = "tarifa_vehiculo"
    __table_args__ = (UniqueConstraint("tarifario_id", "categoria_id", "modalidad_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tarifario_id: Mapped[int] = mapped_column(ForeignKey("tarifario.id"))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria_vehiculo.id"))
    modalidad_id: Mapped[int] = mapped_column(ForeignKey("modalidad.id"))
    precio: Mapped[float] = mapped_column(Numeric(12, 2))
    precio_mensual: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    tarifario: Mapped[Tarifario] = relationship(back_populates="tarifas_vehiculo")
    categoria: Mapped[CategoriaVehiculo] = relationship()
    modalidad: Mapped[Modalidad] = relationship()


# ---------------------------------------------------------------- viaticos

class TabuladorViatico(Base):
    """Identico para toda la empresa dentro de cada pais y tipo de servicio.

    Eventual e implantado llevan tabla aparte. No es la misma operacion:
    el eventual es un dia suelto que muchas veces arranca en un
    aeropuerto y termina en otra ciudad, y el implantado es la misma
    persona en el mismo lugar todos los dias del mes. Meterlos en la
    misma tabla obligaba a que un concepto significara dos cosas segun
    quien lo leyera.
    """
    __tablename__ = "tabulador_viatico"
    __table_args__ = (
        UniqueConstraint("pais_id", "tipo_servicio", "concepto", "escenario"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    tipo_servicio: Mapped["TipoServicio"] = mapped_column(
        Enum(TipoServicio), server_default="EVENTUAL")
    concepto: Mapped[ConceptoViatico] = mapped_column(Enum(ConceptoViatico))
    escenario: Mapped[EscenarioViatico] = mapped_column(Enum(EscenarioViatico))
    monto: Mapped[float] = mapped_column(Numeric(12, 2))
    monto_abierto: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------- comisiones

class ComisionPersonal(Base):
    """Pago al personal por servicio, aparte de su salario fijo.

    Por pais, por tipo de servicio, por rol y por modalidad. Eventual e
    implantado llevan tabla aparte: no son la misma operacion, y un solo
    numero para las dos obligaba a pagar igual un dia suelto que arranca
    en un aeropuerto y un dia de la misma persona en el mismo lugar.

    El `perfil_id` es el rol con el que se cubrio el dia, no un puesto de
    la persona: el mismo agente cobra distinto si conduce o si coordina.
    """
    __tablename__ = "comision_personal"
    __table_args__ = (
        UniqueConstraint("pais_id", "tipo_servicio", "perfil_id",
                         "modalidad_id",
                         name="uq_comision_pais_tipo_perfil_modalidad"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    tipo_servicio: Mapped["TipoServicio"] = mapped_column(
        Enum(TipoServicio), default=TipoServicio.EVENTUAL,
        server_default="EVENTUAL")
    perfil_id: Mapped[int] = mapped_column(ForeignKey("perfil_personal.id"))
    modalidad_id: Mapped[int] = mapped_column(ForeignKey("modalidad.id"))
    monto: Mapped[float] = mapped_column(Numeric(12, 2))
    monto_hora_extra: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))

    perfil: Mapped[PerfilPersonal] = relationship()
    modalidad: Mapped[Modalidad] = relationship()


# ================================================================ PERSONAL Y FLOTA

class Persona(Base):
    """Personal de seguridad. El maestro de empleados vive en Odoo;
    el freelance se da de alta aqui con tarifa propia."""
    __tablename__ = "persona"

    id: Mapped[int] = mapped_column(primary_key=True)
    odoo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    nombre: Mapped[str] = mapped_column(String(160))
    correo: Mapped[str] = mapped_column(String(160), unique=True)
    # Sin puesto fijo, a proposito: el mismo agente que hoy conduce
    # manana coordina. Con que rol va se decide al asignarlo, y de ahi
    # salen lo que se cobra y lo que se le paga.
    plaza_id: Mapped[int] = mapped_column(ForeignKey("plaza.id"))
    es_freelance: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Para el task sheet: la foto y el telefono vienen de Odoo. La foto
    # llega como data URI --la de 128 px de Odoo, unos KB-- y se guarda
    # dentro del registro como las demas imagenes del sistema: por eso es
    # texto largo y no los 400 caracteres de cuando se penso como enlace.
    telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)
    foto_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Lo demas que llega de Odoo (seccion 51). La referencia es el numero
    # de empleado de RH: con el se le busca para dictarle su codigo, y es
    # algo mas que preguntarle por telefono.
    referencia: Mapped[str | None] = mapped_column(String(40), nullable=True,
                                                   index=True)
    fecha_ingreso: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Cuando se leyo de Odoo por ultima vez y cuando Odoo la dio de baja,
    # en UTC y sin zona, como el write_date de Odoo con el que se compara.
    # La baja se queda anotada para cerrarle el acceso en cuanto
    # compruebe sus viaticos, si se fue debiendo.
    odoo_sincronizado_en: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    baja_odoo_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                          nullable=True)
    # A donde se le deposita. Vienen de Odoo igual que el telefono y la
    # foto: el maestro de empleados vive alla. Mientras esa conexion no
    # exista, finanzas los puede llenar y se van poblando conforme se
    # deposita; el dia que Odoo conecte, Odoo manda.
    #
    # Solo finanzas y direccion los ven: es el dato mas sensible que
    # guarda el sistema sobre su gente.
    banco: Mapped[str | None] = mapped_column(String(80), nullable=True)
    clabe: Mapped[str | None] = mapped_column(String(40), nullable=True)
    titular_cuenta: Mapped[str | None] = mapped_column(String(160),
                                                        nullable=True)

    plaza: Mapped[Plaza] = relationship()


class SincronizacionOdoo(Base):
    """Cada lectura de Odoo: cuando, quien y que cambio.

    La de cada hora espera a que exista una hecha a mano: la primera
    vez alguien mira el ensayo y decide. `detalle` guarda el informe
    completo --con nombres--; la de cada hora sin novedades deja su
    renglon sin repetirlo.
    """
    __tablename__ = "sincronizacion_odoo"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20), index=True)   # personal
    hecha_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    automatica: Mapped[bool] = mapped_column(Boolean, default=False,
                                             server_default="false")
    hecha_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    leidos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    altas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cambios: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    bajas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pendientes: Mapped[int] = mapped_column(Integer, default=0,
                                            server_default="0")
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)


class TarifaFreelance(Base):
    """Cada freelance lleva trato aparte: tarifa personalizada por modalidad."""
    __tablename__ = "tarifa_freelance"
    __table_args__ = (UniqueConstraint("persona_id", "modalidad_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    modalidad_id: Mapped[int] = mapped_column(ForeignKey("modalidad.id"))
    costo: Mapped[float] = mapped_column(Numeric(12, 2))
    costo_hora_extra: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))


class MotivoRenta(str, enum.Enum):
    """Por que se subarrendo. Con el tiempo dice si conviene comprar."""
    CATEGORIA_NO_DISPONIBLE = "categoria_no_disponible"
    SATURACION = "saturacion"
    PEDIDO_ESPECIAL = "pedido_especial"


class Vehiculo(Base):
    """Unidad de la flota. El costo diario alimenta la rentabilidad por servicio.

    Tambien vive aqui el auto subarrendado: se renta cuando no hay la
    categoria que pide el cliente o cuando la flota esta saturada, y se
    devuelve al terminar el servicio. Es la misma tabla porque para la
    operacion es una unidad como cualquier otra —se asigna, se le sube
    gente, sale en el task sheet— y separarla obligaria a duplicar todo
    ese camino. Lo que la distingue es el sello: `rentado` y el servicio
    que la pidio.
    """
    __tablename__ = "vehiculo"
    __table_args__ = (
        # La placa es unica entre las propias, pero un auto de renta
        # puede volver meses despues en otro servicio y eso es un alta
        # nueva, no un choque. Lo que si es choque: capturar dos veces
        # la misma renta en el mismo servicio.
        Index("uq_vehiculo_placa_propia", "placa", unique=True,
              postgresql_where=text("rentado = false")),
        Index("uq_vehiculo_placa_rentada", "servicio_id", "placa",
              unique=True, postgresql_where=text("rentado = true")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    placa: Mapped[str] = mapped_column(String(20))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria_vehiculo.id"))
    plaza_id: Mapped[int] = mapped_column(ForeignKey("plaza.id"))
    costo_diario: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Para que el ejecutivo identifique la unidad de un vistazo.
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    modelo_anio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Suburban, Tahoe, Sprinter. En la flota propia se sabe de memoria;
    # en un auto de renta es lo primero que pregunta el que lo va a
    # recibir en el estacionamiento.
    marca_modelo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # La que ve el ejecutivo es la de su categoria en su color (`foto`,
    # abajo; seccion 52). Esta queda de respaldo: se ensena solo si la
    # categoria todavia no tiene ninguna.
    foto_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # Con que numero vive en Odoo (seccion 52), cuando se leyo por
    # ultima vez y cuando Odoo la dio de baja. En UTC y sin zona.
    odoo_id: Mapped[int | None] = mapped_column(Integer, nullable=True,
                                                unique=True)
    odoo_sincronizado_en: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    baja_odoo_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                          nullable=True)

    # ------------------------------------------------------- subarrendo
    rentado: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    # El auto se pidio para este servicio y con el se devuelve: no se le
    # ofrece a ningun otro, aunque el registro se quede para la historia.
    servicio_id: Mapped[int | None] = mapped_column(
        ForeignKey("servicio.id"), nullable=True)
    arrendadora: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # A quien se le llama si la unidad falla a media jornada.
    arrendadora_telefono: Mapped[str | None] = mapped_column(
        String(40), nullable=True)
    motivo_renta: Mapped[MotivoRenta | None] = mapped_column(
        Enum(MotivoRenta), nullable=True)
    # El folio del servicio que la pidio, escrito aparte del enlace: el
    # servicio se puede borrar y la renta sigue corriendo con la
    # arrendadora. Sin el folio, finanzas no sabe de que renta hablamos.
    renta_folio: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # Se dejo de ocupar y alguien tiene que hablarle a la arrendadora.
    # Un auto que se devuelve solo es un auto que se sigue cobrando.
    renta_por_cancelar: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    renta_cancelada_en: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    renta_cancelada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)

    categoria: Mapped[CategoriaVehiculo] = relationship()
    plaza: Mapped[Plaza] = relationship()

    @property
    def foto(self) -> str | None:
        """La que se ensena: la de su categoria en su color, o la base
        de la categoria, o la propia. Decision de Salvador (23 sep):
        basta una foto representativa, pero del color de la unidad."""
        from app.odoo_flota_reglas import color_de

        fotos = {f.color: f for f in (self.categoria.variantes
                                      if self.categoria else [])}
        elegida = fotos.get(color_de(self.color)) or fotos.get("")
        return elegida.foto_url if elegida else self.foto_url


# ================================================================ SERVICIOS

class EstatusServicio(str, enum.Enum):
    BORRADOR = "borrador"
    # El implantado nace aqui: el cliente ya pidio el servicio y el
    # acuerdo esta capturado, pero todavia no se le asigna a nadie.
    # "Borrador" decia que alguien estaba escribiendo; "solicitado" dice
    # que hay un compromiso con el cliente esperando gente.
    SOLICITADO = "solicitado"
    # Reservado: hoy no lo escribe nadie. La cotizacion se hace y se
    # autoriza en Odoo (decision de Salvador, 21 sep), asi que el
    # servicio que llega de alla nace ya `autorizado`; el rato entre
    # "se cotizo" y "el cliente dijo que si" no pasa aqui. Se queda en
    # el catalogo para que un dato viejo no truene y por si algun dia
    # la cotizacion vuelve a vivir en Centauro.
    COTIZADO = "cotizado"
    AUTORIZADO = "autorizado"
    PLANEADO = "planeado"
    # Ya tiene personal y unidad en todas sus jornadas, pero todavia no sale.
    ASIGNADO = "asignado"
    # El equipo ya esta parado en el punto, esperando al principal.
    # Decision de Salvador, 20 sep: mirando la cartera queria saber que
    # su gente ya llego, y "asignado" no se lo decia.
    #
    # No lo promueve `programacion.evaluar`: lo enciende la llegada al
    # punto, igual que en la jornada. Y de aqui solo se sale hacia
    # adelante --el contacto con el principal lo pasa a en curso-- o por
    # el cierre del ultimo dia.
    ARRIBADO = "arribado"
    EN_CURSO = "en_curso"
    TERMINADO = "terminado"
    # El cierre en dos relojes (decision de Salvador, 22 sep). Al
    # terminar corren las 24 h del personal para comprobar; al vencer
    # --o antes, si todo el dinero ya cerro-- el servicio queda sin
    # visto bueno y corren las 24 h del consultor; su visto bueno lo
    # manda a facturar y finanzas lo cierra. Hoy solo el eventual pasa
    # por aqui; el implantado corta a mes y llega en su propia sesion.
    SIN_VISTO_BUENO = "sin_visto_bueno"
    EN_FACTURACION = "en_facturacion"
    CERRADO = "cerrado"
    CANCELADO = "cancelado"


# Todo lo que pasa ANTES de que el servicio salga a la calle.
#
# Vive aqui y no en cada archivo porque tres lugares distintos preguntan
# lo mismo --¿este servicio ya arranco?-- y el dia que no coincidieron
# paso esto: un servicio con la cotizacion ya autorizada no llegaba
# nunca a `en curso` ni a `terminado`, porque el que enciende el motor
# miraba una lista corta que no incluia `autorizado`. El servicio se
# trabajaba, se cerraba el dia, y en la cartera seguia viendose como uno
# que todavia no sale.
ANTES_DE_ARRANCAR = (
    EstatusServicio.BORRADOR,
    EstatusServicio.SOLICITADO,
    EstatusServicio.COTIZADO,
    EstatusServicio.AUTORIZADO,
    EstatusServicio.PLANEADO,
    EstatusServicio.ASIGNADO,
)


class EstatusJornada(str, enum.Enum):
    PLANEADA = "planeada"
    CONFIRMADA = "confirmada"
    PROXIMA_A_INICIAR = "proxima_a_iniciar"
    # Llego al punto y espera al principal. Decision de Salvador, 20 sep.
    #
    # Llegar y esperar veinte minutos a que el ejecutivo baje no es tener
    # el servicio corriendo, y decir "en curso" ahi le quitaba a la
    # central la unica pantalla donde se ve ese rato --que es justo el
    # rato en que todavia se puede hacer algo si el equipo no esta--.
    #
    # Para todo lo demas cuenta como arrancado: esta en la calle, se le
    # mide el silencio, su dia ya no se borra y sus horas cuentan. Lo
    # unico que cambia es lo que dice la pantalla. Ver ARRANCADAS.
    ARRIBADO = "arribado"
    EN_CURSO = "en_curso"
    TERMINADA = "terminada"
    CANCELADA = "cancelada"


# Los dias que ya arrancaron. Quien tenga que preguntar "¿ya empezo?" lo
# pregunta con esto y no con una lista propia: el dia que se agrego
# `arribado`, cada lista suelta era un lugar donde alguien parado en la
# calle desaparecia de una pantalla.
ARRANCADAS = (EstatusJornada.ARRIBADO, EstatusJornada.EN_CURSO)


def _nombre_completo(nombre: str | None, apellidos: str | None) -> str | None:
    """Nombre y apellidos en una sola linea, sin espacios de mas cuando
    falta alguno de los dos."""
    partes = [p.strip() for p in (nombre, apellidos) if p and p.strip()]
    return " ".join(partes) or None


class Servicio(Base):
    """Un servicio agrupa uno o varios equipos; cada equipo es independiente."""
    __tablename__ = "servicio"

    id: Mapped[int] = mapped_column(primary_key=True)
    folio: Mapped[str] = mapped_column(String(24), unique=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    plaza_id: Mapped[int] = mapped_column(ForeignKey("plaza.id"))
    tipo: Mapped[TipoServicio] = mapped_column(Enum(TipoServicio))
    estatus: Mapped[EstatusServicio] = mapped_column(
        Enum(EstatusServicio), default=EstatusServicio.BORRADOR)
    consultor_id: Mapped[int | None] = mapped_column(ForeignKey("persona.id"), nullable=True)
    # El nombre y los apellidos se capturan aparte y se juntan al mostrarlos:
    # asi se puede saludar por su nombre sin partir una cadena a la mitad.
    # De donde salieron los datos. El servicio guarda su propia copia: si
    # manana cambia el telefono del contacto, el servicio de ayer conserva
    # el que se uso.
    solicitante_id: Mapped[int | None] = mapped_column(
        ForeignKey("solicitante.id"), nullable=True)
    solicitante_nombre: Mapped[str | None] = mapped_column(String(160), nullable=True)
    solicitante_apellidos: Mapped[str | None] = mapped_column(String(160), nullable=True)
    solicitante_correo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    solicitante_telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ejecutivo_nombre: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ejecutivo_apellidos: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ejecutivo_correo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ejecutivo_telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # En que idioma lee cada uno. El principal arranca en ingles --suele
    # ser extranjero, que es la regla que textos.py ya tenia escrita para
    # el task sheet-- y el solicitante en el idioma del pais donde se
    # ejecuta el servicio, porque casi siempre es gente local: la
    # asistente, el area de seguridad del cliente. Decision de Salvador
    # (20 sep).
    #
    # El del solicitante admite nulo a proposito: vacio quiere decir "el
    # de su pais" y se resuelve al escribir el aviso, asi los servicios
    # viejos quedan con la regla nueva sin rellenarlos uno por uno.
    idioma_ejecutivo: Mapped[str] = mapped_column(
        String(2), default="en", server_default="en")
    idioma_solicitante: Mapped[str | None] = mapped_column(
        String(2), nullable=True)

    @property
    def solicitante_completo(self) -> str | None:
        return _nombre_completo(self.solicitante_nombre, self.solicitante_apellidos)

    @property
    def ejecutivo_completo(self) -> str | None:
        return _nombre_completo(self.ejecutivo_nombre, self.ejecutivo_apellidos)
    # Senal de identificacion: lo que el equipo muestra para que el ejecutivo
    # los reconozca al salir del filtro del aeropuerto o en el lobby.
    # La firma del consultor: la asignacion ya no esta a medias.
    asignacion_confirmada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    asignacion_confirmada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    # Como va vestido el equipo. Nulo a proposito: los servicios que ya
    # existen no dicen nada en vez de decir algo que nadie acordo, y el
    # implantado no la usa nunca.
    vestimenta: Mapped[str | None] = mapped_column(String(12), nullable=True)
    senal_texto: Mapped[str | None] = mapped_column(String(80), nullable=True)
    senal_imagen: Mapped[str | None] = mapped_column(Text, nullable=True)
    senal_nota: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # La clave del color de la paleta (`senal.py`), no el hex: el nombre
    # sale en la hoja del principal en su idioma, y el hex puede cambiar
    # el dia que llegue el manual de marca sin tocar ningun servicio.
    senal_color: Mapped[str | None] = mapped_column(String(12), nullable=True)
    # Referencia cruzada: extension abierta como servicio nuevo por choque de recursos.
    servicio_origen_id: Mapped[int | None] = mapped_column(ForeignKey("servicio.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cliente: Mapped[Cliente] = relationship()
    equipos: Mapped[list["Equipo"]] = relationship(
        back_populates="servicio", cascade="all, delete-orphan")


class Equipo(Base):
    """Desde un vehiculo con conductor hasta dos vehiculos, dos conductores y un agente.
    Lleva sus propios controles, horas extra, viaticos y cierre."""
    __tablename__ = "equipo"

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicio.id"))
    # Alias operativo del equipo, del alfabeto griego: Alfa, Beta, Gamma...
    alias: Mapped[str] = mapped_column(String(20), server_default="Alfa")
    clave: Mapped[str] = mapped_column(String(40))
    descripcion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Donde opera ESTE equipo. Un mismo proyecto mueve al ejecutivo de
    # una ciudad a otra: Alfa en Ciudad de Mexico, Beta en Monterrey.
    # Vacio significa la del servicio.
    plaza_id: Mapped[int | None] = mapped_column(
        ForeignKey("plaza.id"), nullable=True)
    # El ejecutivo principal de ESTE equipo. Cuando el servicio trae uno
    # solo se captura arriba y el equipo lo hereda; con dos o mas, cada
    # uno lleva al suyo y cada task sheet sale a su nombre.
    ejecutivo_nombre: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ejecutivo_apellidos: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ejecutivo_correo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ejecutivo_telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)

    servicio: Mapped[Servicio] = relationship(back_populates="equipos")
    jornadas: Mapped[list["Jornada"]] = relationship(
        back_populates="equipo", cascade="all, delete-orphan")

    # La ciudad donde opera: la suya si la tiene, si no la del servicio.
    @property
    def ciudad_id(self) -> int:
        return self.plaza_id or self.servicio.plaza_id

    # Lo propio si lo hay; si no, lo del servicio. Nunca los dos mezclados:
    # un equipo con ejecutivo propio no toma el telefono del otro.
    @property
    def tiene_ejecutivo_propio(self) -> bool:
        return bool(self.ejecutivo_nombre or self.ejecutivo_apellidos)

    def _suyo(self, campo: str):
        if self.tiene_ejecutivo_propio:
            return getattr(self, f"ejecutivo_{campo}")
        return getattr(self.servicio, f"ejecutivo_{campo}", None)

    @property
    def ejecutivo_completo(self) -> str | None:
        return _nombre_completo(self._suyo("nombre"), self._suyo("apellidos"))

    @property
    def ejecutivo_correo_efectivo(self) -> str | None:
        return self._suyo("correo")

    @property
    def ejecutivo_telefono_efectivo(self) -> str | None:
        return self._suyo("telefono")


class Jornada(Base):
    """La modalidad es de cada dia, no del servicio completo."""
    __tablename__ = "jornada"
    __table_args__ = (UniqueConstraint("equipo_id", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    equipo_id: Mapped[int] = mapped_column(ForeignKey("equipo.id"))
    fecha: Mapped[date] = mapped_column(Date)
    modalidad_id: Mapped[int] = mapped_column(ForeignKey("modalidad.id"))
    inicio_programado: Mapped[datetime] = mapped_column(DateTime)
    fin_programado: Mapped[datetime] = mapped_column(DateTime)
    # Si la hora la dijo alguien o se heredo del primer dia. La heredada
    # sirve para calcular, pero no es un dato confirmado y la pantalla lo
    # dice en vez de aparentar que si.
    hora_confirmada: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    es_foraneo: Mapped[bool] = mapped_column(Boolean, default=False)
    km_estimados: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estatus: Mapped[EstatusJornada] = mapped_column(
        Enum(EstatusJornada), default=EstatusJornada.PLANEADA)
    # Candado 1: geocerca obligatoria en el punto de origen.
    origen_lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    origen_lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    # El circulo que el conductor tiene que pisar para poder marcar su
    # llegada. Dos kilometros en aeropuerto, uno en cualquier otro lado:
    # un aeropuerto no cabe en un kilometro y la app le negaria la
    # llegada a alguien que esta donde debe.
    geocerca_metros: Mapped[int] = mapped_column(Integer, default=500)
    # Lo dice Google al elegir el lugar, o el consultor con la casilla.
    origen_aeropuerto: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")
    # Lo que dijo Google del lugar elegido, guardado aparte de lo que
    # decidio el consultor. Son dos cosas distintas y hay que poder
    # compararlas: marcar como aeropuerto un hotel abre la geocerca a
    # dos kilometros. Vacio quiere decir que la direccion se escribio a
    # mano y no hay nada que contradecir.
    origen_google_aeropuerto: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True)
    origen_direccion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Vuelo del ejecutivo. El equipo lo sigue para saber si llega tarde y
    # el ejecutivo lo lee en el meet and greet para confirmar que es su vuelo.
    vuelo_aerolinea: Mapped[str | None] = mapped_column(String(80), nullable=True)
    vuelo_numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vuelo_hora: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    vuelo_origen: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # "llegada" o "salida". Casi siempre se deduce (primer dia llega, ultimo
    # sale), pero un transfer de un solo dia puede ser cualquiera de los dos,
    # asi que el consultor lo puede decir.
    vuelo_tipo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # En implantados: dia fuera de la base contratada, con costo extra.
    es_dia_adicional: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default='false')
    # Hora real de termino, la marca el conductor y la central puede ajustarla.
    inicio_real: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fin_real: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Cuando un dia se trabajo y nadie lo marco, la central puede
    # cerrarlo. Eso es dar fe de algo sin evidencia desde la calle, asi
    # que queda firmado: quien, cuando y por que. Un cierre a mano que
    # se viera igual que un dia marcado seria una puerta abierta para
    # inventar dias trabajados.
    cerrada_a_mano_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    cerrada_a_mano_en: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    cierre_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)

    equipo: Mapped[Equipo] = relationship(back_populates="jornadas")
    cerrada_a_mano_por: Mapped["Persona"] = relationship(
        foreign_keys=[cerrada_a_mano_por_id])
    modalidad: Mapped[Modalidad] = relationship()
    personal: Mapped[list["AsignacionPersonal"]] = relationship(
        back_populates="jornada", cascade="all, delete-orphan")
    vehiculos: Mapped[list["AsignacionVehiculo"]] = relationship(
        back_populates="jornada", cascade="all, delete-orphan")


class AsignacionPersonal(Base):
    __tablename__ = "asignacion_personal"
    __table_args__ = (UniqueConstraint("jornada_id", "persona_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int] = mapped_column(ForeignKey("jornada.id"))
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    # Con que rol va ese dia. De aqui salen el precio al cliente y la
    # comision: el mismo agente cobra distinto si el martes conduce y el
    # miercoles coordina.
    rol_id: Mapped[int | None] = mapped_column(
        ForeignKey("perfil_personal.id"), nullable=True)
    confirmado: Mapped[bool] = mapped_column(Boolean, default=False)
    # Cuando y por quien. Vacio el segundo quiere decir que confirmo la
    # propia persona desde su app, que es el caso normal.
    #
    # Lo llena la central cuando el agente no trae la app --o no la
    # tiene encendida-- y lo confirmo por telefono. Va sellado a
    # proposito: una confirmacion registrada por otro NO es la misma
    # cosa que la de la persona, y la pantalla no las pinta igual. Sin
    # el sello, el dia que alguien no llegue nadie podria saber si
    # confirmo el o lo confirmaron por el.
    confirmado_en: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    confirmado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    nota_confirmacion: Mapped[str | None] = mapped_column(
        String(200), nullable=True)
    # Reemplazo por contingencia: a quien sustituye esta asignacion.
    reemplaza_a_id: Mapped[int | None] = mapped_column(ForeignKey("persona.id"), nullable=True)
    # El otro lado del mismo cambio: esta asignacion fue relevada a media
    # jornada y quien la relevo. El dia no se muta, se parte: el que se
    # presento esa manana se queda aqui y cobra su dia, y el que entro
    # tiene su propia asignacion. Vacio quiere decir que nadie la
    # relevo, que es el caso de siempre.
    relevado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    relevado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    # En que unidad va esa persona. Con una sola unidad sobra decirlo;
    # cuando el equipo lleva dos o mas, es lo que ordena las salidas y le
    # dice a la central con quien va cada vehiculo.
    vehiculo_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehiculo.id", ondelete="SET NULL"), nullable=True)

    # El cliente lo pidio por nombre. Lo marca el consultor al armar el
    # equipo, y es lo unico que distingue "me lo volvieron a pedir" de
    # "coincidimos porque estaba libre". Nace apagado: un campo vacio no
    # castiga a nadie --el criterio simplemente no aplica--.
    pedido_por_cliente: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")

    jornada: Mapped[Jornada] = relationship(back_populates="personal")
    persona: Mapped[Persona] = relationship(foreign_keys=[persona_id])
    relevado_por: Mapped["Persona | None"] = relationship(
        foreign_keys=[relevado_por_id])
    confirmado_por: Mapped["Persona | None"] = relationship(
        foreign_keys=[confirmado_por_id])
    rol: Mapped["PerfilPersonal | None"] = relationship()
    vehiculo: Mapped["Vehiculo | None"] = relationship()


class AsignacionVehiculo(Base):
    __tablename__ = "asignacion_vehiculo"
    __table_args__ = (UniqueConstraint("jornada_id", "vehiculo_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int] = mapped_column(ForeignKey("jornada.id"))
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("vehiculo.id"))
    # Relevada a media jornada, igual que la del personal: la unidad que
    # salio se queda en el servicio para que se le pueda hacer su
    # revision de devolucion. Al cliente se le cobra una sola.
    relevado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    relevado_por_vehiculo_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehiculo.id"), nullable=True)

    jornada: Mapped[Jornada] = relationship(back_populates="vehiculos")
    vehiculo: Mapped[Vehiculo] = relationship(foreign_keys=[vehiculo_id])
    relevado_por_vehiculo: Mapped["Vehiculo | None"] = relationship(
        foreign_keys=[relevado_por_vehiculo_id])


# ================================================================ VIATICOS

class EstatusViatico(str, enum.Enum):
    ASIGNADO = "asignado"
    SOLICITADO = "solicitado"          # instruccion enviada a finanzas
    TRANSFERIDO = "transferido"        # el dinero ya esta con la persona
    EN_COMPROBACION = "en_comprobacion"
    CERRADO = "cerrado"
    DEVUELTO = "devuelto"              # servicio cancelado, regreso el dinero
    CANCELADO = "cancelado"            # nunca se transfirio y ya no aplica


class OrigenMonto(str, enum.Enum):
    TABULADOR = "tabulador"
    ESTIMADO = "estimado"              # combustible calculado por kilometros
    MANUAL = "manual"                  # el consultor captura el monto


class TipoComprobante(str, enum.Enum):
    FACTURA = "factura"
    NOTA = "nota"


class ParametroCombustible(Base):
    """Precio por litro y holgura para el estimado a precio alzado.
    Lleva vigencia porque el precio se mueve."""
    __tablename__ = "parametro_combustible"

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    precio_litro: Mapped[float] = mapped_column(Numeric(10, 2))
    holgura_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=20)
    vigencia_desde: Mapped[date] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class AsignacionViatico(Base):
    """Los viaticos se manejan de forma individual por persona y por jornada."""
    __tablename__ = "asignacion_viatico"
    __table_args__ = (UniqueConstraint("jornada_id", "persona_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int] = mapped_column(ForeignKey("jornada.id"))
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    escenario: Mapped[EscenarioViatico] = mapped_column(Enum(EscenarioViatico))
    monto_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    monto_comprobado: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    monto_devuelto: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    estatus: Mapped[EstatusViatico] = mapped_column(
        Enum(EstatusViatico), default=EstatusViatico.ASIGNADO)
    asignado_por_id: Mapped[int | None] = mapped_column(ForeignKey("persona.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    limite_comprobacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Cierre forzado: el conductor no pudo resolver su comprobacion y el
    # consultor cerro por el, mandando a descuento lo que no aplica.
    cerrado_con_descuento: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default='false')
    monto_descontado: Mapped[float] = mapped_column(
        Numeric(12, 2), default=0, server_default='0')
    monto_absorbido: Mapped[float] = mapped_column(
        Numeric(12, 2), default=0, server_default='0')
    motivo_cierre: Mapped[str | None] = mapped_column(String(400), nullable=True)
    cerrado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)

    jornada: Mapped[Jornada] = relationship()
    persona: Mapped[Persona] = relationship(foreign_keys=[persona_id])
    conceptos: Mapped[list["ConceptoAsignado"]] = relationship(
        back_populates="asignacion", cascade="all, delete-orphan")
    comprobantes: Mapped[list["Comprobante"]] = relationship(
        back_populates="asignacion", cascade="all, delete-orphan")
    devoluciones: Mapped[list["DevolucionViatico"]] = relationship(
        back_populates="asignacion", cascade="all, delete-orphan")


class ConceptoAsignado(Base):
    """Desglose del viatico. En 'otros' el consultor especifica descripcion y monto."""
    __tablename__ = "concepto_asignado"

    id: Mapped[int] = mapped_column(primary_key=True)
    asignacion_id: Mapped[int] = mapped_column(ForeignKey("asignacion_viatico.id"))
    concepto: Mapped[ConceptoViatico] = mapped_column(Enum(ConceptoViatico))
    monto: Mapped[float] = mapped_column(Numeric(12, 2))
    descripcion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    origen: Mapped[OrigenMonto] = mapped_column(Enum(OrigenMonto))
    # Viaticos adicionales solicitados durante el servicio o en el ajuste.
    es_adicional: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asignacion: Mapped[AsignacionViatico] = relationship(back_populates="conceptos")


class Comprobante(Base):
    """El personal sube factura, o nota cuando no hay factura."""
    __tablename__ = "comprobante"

    id: Mapped[int] = mapped_column(primary_key=True)
    asignacion_id: Mapped[int] = mapped_column(ForeignKey("asignacion_viatico.id"))
    concepto: Mapped[ConceptoViatico] = mapped_column(Enum(ConceptoViatico))
    tipo: Mapped[TipoComprobante] = mapped_column(Enum(TipoComprobante))
    monto: Mapped[float] = mapped_column(Numeric(12, 2))
    archivo_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # La foto del ticket, dentro del registro. El que comprueba es un
    # agente parado en una gasolinera: lo que tiene es la camara, no un
    # archivo que subir a otro lado. Y un enlace que no carga el dia de
    # la revision deja sin prueba a alguien que si gasto el dinero.
    imagen: Mapped[str | None] = mapped_column(Text, nullable=True)
    descripcion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    validado: Mapped[bool] = mapped_column(Boolean, default=False)
    # Gasto que no aplica al servicio. No cuenta como comprobado, no se le
    # cobra al cliente y se le descuenta a quien lo hizo.
    rechazado: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default='false')
    motivo_rechazo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    observacion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    subido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asignacion: Mapped[AsignacionViatico] = relationship(back_populates="comprobantes")


class EstatusTransferencia(str, enum.Enum):
    PENDIENTE = "pendiente"
    ENVIADA = "enviada"          # instruccion ya en Odoo / finanzas
    CONFIRMADA = "confirmada"    # finanzas confirmo el deposito
    CANCELADA = "cancelada"


class EstatusDevolucion(str, enum.Enum):
    DECLARADA = "declarada"      # la persona dice que ya transfirio
    CONFIRMADA = "confirmada"    # finanzas la vio entrar a la cuenta
    RECHAZADA = "rechazada"      # no llego, o no cuadra


class DevolucionViatico(Base):
    """El dinero que regresa: la transferencia al reves.

    Sobro dinero, o el servicio se cancelo con el deposito ya hecho. La
    persona transfiere de vuelta y manda su comprobante; finanzas
    confirma cuando lo ve entrar en la cuenta de la empresa.

    **Declarada no es confirmada**, por la misma razon por la que
    autorizado no es depositado. Si lo declarado contara de una vez, a
    la persona se le apagaria sola su deuda --y con ella el plazo de
    comprobacion-- diciendo que devolvio un dinero que la empresa
    todavia no ha visto. Ese es exactamente el defecto que tenia la app
    del otro lado, y cuesta lo mismo no repetirlo aqui.

    `AsignacionViatico.monto_devuelto` guarda SOLO lo confirmado: es lo
    que leen la rentabilidad, el bono y el tablero de dinero en la
    calle, y ninguno de esos puede moverse con una promesa.
    """
    __tablename__ = "devolucion_viatico"

    id: Mapped[int] = mapped_column(primary_key=True)
    asignacion_id: Mapped[int] = mapped_column(
        ForeignKey("asignacion_viatico.id", ondelete="CASCADE"), index=True)
    monto: Mapped[float] = mapped_column(Numeric(12, 2))
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    # El folio del banco y la imagen. Misma regla que el deposito: sin
    # evidencia, la unica prueba de que el dinero volvio es la palabra
    # de quien lo capturo.
    referencia: Mapped[str | None] = mapped_column(String(120), nullable=True)
    comprobante: Mapped[str | None] = mapped_column(Text, nullable=True)
    estatus: Mapped[EstatusDevolucion] = mapped_column(
        Enum(EstatusDevolucion), default=EstatusDevolucion.DECLARADA)
    # Quien dijo que transfirio. Es la propia persona desde su app, o
    # finanzas capturandola cuando la vio llegar sin que nadie avisara.
    declarada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    declarada_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                          nullable=True)
    confirmada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    confirmada_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                           nullable=True)
    motivo_rechazo: Mapped[str | None] = mapped_column(String(300),
                                                       nullable=True)

    asignacion: Mapped["AsignacionViatico"] = relationship(
        back_populates="devoluciones")
    declarada_por: Mapped["Persona | None"] = relationship(
        foreign_keys=[declarada_por_id])
    confirmada_por: Mapped["Persona | None"] = relationship(
        foreign_keys=[confirmada_por_id])


class SolicitudTransferencia(Base):
    """Por el volumen no se transfiere en tiempo real: ventanas y barridos por lote."""
    __tablename__ = "solicitud_transferencia"

    id: Mapped[int] = mapped_column(primary_key=True)
    asignacion_id: Mapped[int] = mapped_column(ForeignKey("asignacion_viatico.id"))
    monto: Mapped[float] = mapped_column(Numeric(12, 2))
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    estatus: Mapped[EstatusTransferencia] = mapped_column(
        Enum(EstatusTransferencia), default=EstatusTransferencia.PENDIENTE)
    lote: Mapped[str | None] = mapped_column(String(40), nullable=True)
    referencia_odoo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # La firma del deposito: cuando salio el dinero y quien lo despacho.
    # Sin esto, en cuanto el renglon sale de la bandeja de finanzas la
    # unica forma de saber si a alguien ya se le pago es preguntarle.
    confirmada_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                           nullable=True)
    confirmada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    # El consultor quiere echarse para atras algo que YA esta en manos de
    # finanzas. No lo cancela el solo: el unico que sabe si el dinero ya
    # salio del banco es finanzas, y cancelar aqui una transferencia que
    # ya se hizo deja dinero entregado sin registro. Queda pedida, y
    # finanzas la cierra --o la deposita, si ya era tarde--.
    cancelacion_pedida_en: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    cancelacion_pedida_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    # De que deposito salio. Varias solicitudes --los dias de una persona
    # en un equipo-- se pagan con una sola transferencia, y es ahi donde
    # vive la evidencia.
    deposito_id: Mapped[int | None] = mapped_column(
        ForeignKey("deposito_bancario.id", ondelete="SET NULL"),
        nullable=True)

    asignacion: Mapped[AsignacionViatico] = relationship()
    deposito: Mapped["DepositoBancario | None"] = relationship(
        back_populates="solicitudes")


class DepositoBancario(Base):
    """La transferencia que de verdad sale del banco.

    El sistema tenia una solicitud por jornada, pero finanzas paga un
    deposito por persona y equipo: son cuatro dias y una sola
    transferencia. Esa transferencia no existia en ninguna tabla --la
    pantalla la armaba al vuelo-- y por eso no habia a que colgarle la
    referencia ni el comprobante.

    Aqui vive, y las solicitudes cuelgan de ella. El comprobante se
    guarda UNA vez por deposito: colgado de cada solicitud serian cuatro
    copias de la misma imagen dentro de la base.

    Un deposito por persona y equipo, a proposito. Si alguien anda en dos
    servicios recibe dos depositos el mismo dia: es mas movimiento en el
    banco, pero cada transferencia queda amarrada a un servicio y la
    rentabilidad de ese servicio cuadra sola.
    """
    __tablename__ = "deposito_bancario"

    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"),
                                            index=True)
    equipo_id: Mapped[int] = mapped_column(
        ForeignKey("equipo.id", ondelete="CASCADE"), index=True)
    monto: Mapped[float] = mapped_column(Numeric(12, 2))
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    # El folio del banco. Sin el y sin comprobante no se registra: es la
    # misma regla que ya tienen las compras especiales, y es el punto de
    # todo esto.
    referencia: Mapped[str | None] = mapped_column(String(120), nullable=True)
    comprobante: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Naive: hora de pared del pais del servicio, como el resto de la
    # operacion.
    depositado_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                            nullable=True)
    despachado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    # El dinero salio del banco DESPUES de que alguien cancelo la
    # solicitud. No se rechaza --un deposito real siempre tiene donde
    # registrarse, o se arregla por fuera y lo que se arregla por fuera
    # no se audita-- pero queda marcado: es dinero que hay que aplicar o
    # pedir de vuelta, y el consultor tiene que verlo.
    sobre_cancelada: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"))
    # Subir el archivo correcto es lo mas comun que pasa despues de
    # registrar. Se permite siempre, y queda quien lo cambio y cuando.
    corregido_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                           nullable=True)
    corregido_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    persona: Mapped["Persona"] = relationship(foreign_keys=[persona_id])
    equipo: Mapped["Equipo"] = relationship()
    despachado_por: Mapped["Persona | None"] = relationship(
        foreign_keys=[despachado_por_id])
    corregido_por: Mapped["Persona | None"] = relationship(
        foreign_keys=[corregido_por_id])
    solicitudes: Mapped[list["SolicitudTransferencia"]] = relationship(
        back_populates="deposito")


# ------------------------------------------------- compras especiales

class TipoCompra(str, enum.Enum):
    VUELO = "vuelo"
    HOSPEDAJE = "hospedaje"
    TRANSPORTE = "transporte"          # tren, autobus, renta de auto
    OTRO = "otro"


class EstatusCompra(str, enum.Enum):
    SOLICITADA = "solicitada"          # el consultor ya la pidio
    EN_GESTION = "en_gestion"          # finanzas la esta buscando
    CONFIRMADA = "confirmada"          # comprada o reservada, con folio
    RECHAZADA = "rechazada"
    CANCELADA = "cancelada"


class CompraEspecial(Base):
    """Lo que no se deposita: se compra.

    Un boleto de avion o un hotel no se le dan en efectivo a nadie. El
    consultor escribe lo que hace falta, finanzas lo busca, lo compra o
    lo reserva y contesta con el numero de reserva o la imagen de la
    compra. Va por equipo y no por persona: el vuelo o el hotel se
    gestionan para todo el equipo de una vez, no agente por agente.
    """
    __tablename__ = "compra_especial"

    id: Mapped[int] = mapped_column(primary_key=True)
    equipo_id: Mapped[int] = mapped_column(
        ForeignKey("equipo.id", ondelete="CASCADE"))
    tipo: Mapped[TipoCompra] = mapped_column(Enum(TipoCompra))
    # Lo que pide el consultor, con sus palabras: ruta, fechas, cuantas
    # personas, preferencias. Es lo unico que finanzas va a leer.
    solicitud: Mapped[str] = mapped_column(Text)
    monto_estimado: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True)
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    estatus: Mapped[EstatusCompra] = mapped_column(
        Enum(EstatusCompra), default=EstatusCompra.SOLICITADA)

    solicitada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    solicitada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    # -------------------------------------------- respuesta de finanzas
    # El folio con el que el equipo se presenta en el mostrador. Sin esto
    # la compra no sirve de nada aunque este pagada.
    confirmacion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # La imagen de la compra viaja dentro del registro, como la senal:
    # el equipo la abre desde un aeropuerto y un enlace que no cargue
    # deja al agente sin nada que ensenar en el mostrador.
    comprobante: Mapped[str | None] = mapped_column(Text, nullable=True)
    monto_real: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    respuesta: Mapped[str | None] = mapped_column(Text, nullable=True)
    atendida_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    atendida_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    equipo: Mapped["Equipo"] = relationship()
    solicitada_por: Mapped["Persona | None"] = relationship(
        foreign_keys=[solicitada_por_id])
    atendida_por: Mapped["Persona | None"] = relationship(
        foreign_keys=[atendida_por_id])

    @property
    def tiene_comprobante(self) -> bool:
        """La imagen no se manda en la lista: pesa y casi nunca se abre.
        La pantalla solo necesita saber que existe para ofrecer verla."""
        return bool(self.comprobante)


# ================================================================ CICLO DIARIO

class TipoHito(str, enum.Enum):
    LLEGADA_ORIGEN = "llegada_origen"        # esta en el lugar citado, en espera
    CONTACTO_EJECUTIVO = "contacto_ejecutivo"  # inicio formal del servicio
    LLEGADA_DESTINO = "llegada_destino"
    SALIDA_RUTA = "salida_ruta"
    STANDBY = "standby"                      # reporte periodico de que sigue en espera
    FIN_SERVICIO = "fin_servicio"


class TipoAlerta(str, enum.Enum):
    FUERA_DE_GEOCERCA = "fuera_de_geocerca"
    FUERA_DE_VENTANA = "fuera_de_ventana"
    SIN_REPORTE = "sin_reporte"
    HORAS_EXTRA_PROXIMAS = "horas_extra_proximas"
    RECURSO_SIN_CONFIRMAR = "recurso_sin_confirmar"
    VIATICO_NO_TRANSFERIDO = "viatico_no_transferido"
    VEHICULO_SIN_ASIGNAR = "vehiculo_sin_asignar"
    # Odoo archivo a alguien que tenia dias asignados (seccion 51): hay
    # que reemplazarlo.
    PERSONAL_DE_BAJA = "personal_de_baja"
    # Odoo archivo una unidad que tenia dias asignados (seccion 52).
    UNIDAD_DE_BAJA = "unidad_de_baja"


class Destinatario(str, enum.Enum):
    SOLICITANTE = "solicitante"
    EJECUTIVO = "ejecutivo"
    CENTRAL = "central"
    CONSULTOR = "consultor"
    PERSONAL = "personal"
    # Alguien de la empresa, por algo que no es un servicio: su
    # invitacion de acceso, el enlace para recuperar su contrasena, un
    # aviso de administracion. Los cinco de arriba son papeles dentro de
    # un servicio; este es una persona a secas.
    COLABORADOR = "colaborador"


class Canal(str, enum.Enum):
    CORREO = "correo"
    WHATSAPP = "whatsapp"
    AMBOS = "ambos"
    APP = "app"


class Hito(Base):
    """Cada marca del conductor en la app, con su geolocalizacion.
    Los registros van ligados a ubicacion para dificultar el falseo."""
    __tablename__ = "hito"

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int] = mapped_column(ForeignKey("jornada.id"))
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    tipo: Mapped[TipoHito] = mapped_column(Enum(TipoHito))
    marcado_en: Mapped[datetime] = mapped_column(DateTime)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    distancia_origen_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dentro_geocerca: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fuera_de_ventana: Mapped[bool] = mapped_column(Boolean, default=False)
    requiere_revision: Mapped[bool] = mapped_column(Boolean, default=False)
    nota: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Cuando llego la marca al servidor. La hora que manda el telefono es
    # una afirmacion; esta es un hecho. Se guardan las dos porque la app
    # puede marcar sin senal y mandar despues, y la diferencia entre
    # ambas es justo lo que la central tiene que poder ver.
    recibido_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                          nullable=True)
    diferido: Mapped[bool] = mapped_column(Boolean, default=False,
                                           server_default=text("false"))
    # Ajuste por la central: la justificacion es obligatoria.
    ajustado_por_id: Mapped[int | None] = mapped_column(ForeignKey("persona.id"), nullable=True)
    marcado_original: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    justificacion_ajuste: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # Registrado por la central porque nadie lo marco desde la calle.
    #
    # No es lo mismo que un ajuste. Ajustar corrige la hora de una marca
    # que existe; esto CREA una marca que nunca se hizo, y esa diferencia
    # tiene que poder verse para siempre: `inicio_real` sale de aqui, y
    # de `inicio_real` salen las horas que se le facturan al cliente.
    # Un dia que alguien firmo desde una oficina no se puede confundir
    # con uno que alguien marco parado en la calle.
    registrado_a_mano_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    registrado_a_mano_en: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    motivo_a_mano: Mapped[str | None] = mapped_column(String(400),
                                                      nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # La marca anulada. Pasa cuando la central reabre un dia que el
    # equipo ya habia cerrado desde la calle: ese fin de servicio deja
    # de contar, pero NO se borra. Una marca real que desaparece sin
    # rastro es lo que este sistema no hace; dentro de seis meses
    # alguien va a querer saber por que ese dia se cerro dos veces.
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                        nullable=True)
    anulado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    motivo_anulacion: Mapped[str | None] = mapped_column(String(400),
                                                         nullable=True)

    jornada: Mapped[Jornada] = relationship()
    persona: Mapped[Persona] = relationship(foreign_keys=[persona_id])
    registrado_a_mano_por: Mapped[Persona | None] = relationship(
        foreign_keys=[registrado_a_mano_por_id])
    anulado_por: Mapped[Persona | None] = relationship(
        foreign_keys=[anulado_por_id])


class NotaBitacora(Base):
    """Lo que alguien de la casa supo y escribio en el dia.

    Las otras cuatro fuentes de la bitacora son automaticas: el plan lo
    dicto el cliente, los hitos los marco el equipo, las alertas las
    levanto el sistema y las acciones quedaron al tocar otra pantalla.
    Faltaba la quinta, y era la que hace que una bitacora sea una
    bitacora: lo que la central averigua por telefono.

    "Hable con Juan, va en camino, hay manifestacion en Reforma." "El
    cliente avisa que se extiende hasta las 22:00." Eso vivia en la
    cabeza de quien contesto o en un WhatsApp, y el turno siguiente no
    lo heredaba.

    **No se edita ni se borra.** Una bitacora que se puede corregir
    despues no sirve para lo unico que sirve una bitacora: reconstruir
    que se sabia y en que momento. Si algo quedo mal escrito, se
    escribe otra nota --y las dos se leen, en orden.
    """
    __tablename__ = "nota_bitacora"

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int] = mapped_column(ForeignKey("jornada.id"))
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    texto: Mapped[str] = mapped_column(String(600))
    # La hora la pone el servidor: una nota con hora a eleccion de quien
    # escribe deja de ser un registro de cuando se supo algo.
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    persona: Mapped[Persona] = relationship(foreign_keys=[persona_id])


class EstadoTrayecto(str, enum.Enum):
    """Como va quien todavia no ha llegado al punto."""
    ESPERANDO = "esperando"          # se le pregunto y no ha contestado
    EN_CAMINO = "en_camino"          # contesto y se esta acercando
    CERCA = "cerca"                  # ya esta al lado del punto
    LLEGO = "llego"                  # marco su llegada; se apaga
    SIN_RESPUESTA = "sin_respuesta"  # no contesta los toques
    NO_LLEGA = "no_llega"            # se mueve, pero no le alcanza el tiempo
    # La central hablo con el por telefono y dijo que ya va. Vale, y se
    # ve distinto de la posicion que manda el telefono solo: una es un
    # dato, la otra es la palabra de alguien. Y no vale para siempre:
    # pasado el plazo se vuelve a vigilar.
    POR_TELEFONO = "por_telefono"


class Trayecto(Base):
    """El camino al meet and greet, de una persona en un dia.

    Existe por el caso que no daba ninguna senal: el conductor que se
    queda dormido. No marca nada --el sistema no recibe un dato
    equivocado, no recibe ninguno-- y el silencio no disparaba nada; la
    central se enteraba cuando llamaba el cliente.

    Y reponer a alguien toma hasta hora y media (dato de Salvador, 20
    sep), asi que enterarse a la hora de la presentacion es enterarse
    tarde. Por eso el primer toque va a DOS horas de la hora de estar en
    el punto: con hora y media, el reemplazo llegaria quince minutos
    despues del servicio.

    La ventana se abre con el primer toque y se cierra al marcar la
    llegada o al acercarse al punto. Fuera de ella no se toma nada: esto
    es el tiempo de la persona, no el del servicio.
    """
    __tablename__ = "trayecto"
    __table_args__ = (UniqueConstraint("jornada_id", "persona_id",
                                       name="uq_trayecto_jornada_persona"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int] = mapped_column(ForeignKey("jornada.id"), index=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"), index=True)
    estado: Mapped[EstadoTrayecto] = mapped_column(
        String(14), default=EstadoTrayecto.ESPERANDO)
    # Cuantas veces se le pregunto. Tres y ya: mas toques no dan mas
    # informacion, solo ensenan a ignorar los avisos.
    toques: Mapped[int] = mapped_column(Integer, default=0,
                                        server_default=text("0"))
    ultimo_toque_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                             nullable=True)
    # La primera lectura y la ultima. Con estas dos y el reloj sale todo
    # lo que hay que saber, sin preguntarle nada a nadie.
    distancia_inicial_m: Mapped[int | None] = mapped_column(Integer,
                                                            nullable=True)
    distancia_ultima_m: Mapped[int | None] = mapped_column(Integer,
                                                           nullable=True)
    ultima_lectura_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                               nullable=True)
    # Cuantas lecturas seguidas sin avanzar. Una es trafico; dos ya no.
    sin_avanzar: Mapped[int] = mapped_column(Integer, default=0,
                                             server_default=text("0"))
    # Para no levantar la misma alerta cada cinco minutos.
    alertado: Mapped[bool] = mapped_column(Boolean, default=False,
                                           server_default="false")
    # La llamada de la central. Lo que se guarda no es "va en camino"
    # --eso lo dice el estado-- sino QUIEN lo dijo y CUANDO, que es lo
    # unico que distingue la palabra de una persona de una posicion del
    # GPS. El dia que alguien no llegue, esa diferencia es la pregunta.
    por_telefono_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                             nullable=True)
    por_telefono_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    por_telefono_nota: Mapped[str | None] = mapped_column(String(200),
                                                          nullable=True)

    jornada: Mapped["Jornada"] = relationship()
    persona: Mapped["Persona"] = relationship(foreign_keys=[persona_id])
    por_telefono_por: Mapped["Persona | None"] = relationship(
        foreign_keys=[por_telefono_por_id])
    lecturas: Mapped[list["LecturaTrayecto"]] = relationship(
        cascade="all, delete-orphan", order_by="LecturaTrayecto.momento")


class LecturaTrayecto(Base):
    """Donde estaba cada vez que contesto."""
    __tablename__ = "lectura_trayecto"

    id: Mapped[int] = mapped_column(primary_key=True)
    trayecto_id: Mapped[int] = mapped_column(
        ForeignKey("trayecto.id", ondelete="CASCADE"), index=True)
    momento: Mapped[datetime] = mapped_column(DateTime)
    lat: Mapped[float] = mapped_column(Numeric(10, 7))
    lon: Mapped[float] = mapped_column(Numeric(10, 7))
    # En linea recta al punto de origen. Lo que importa no es el numero,
    # es si baja.
    distancia_m: Mapped[int] = mapped_column(Integer)


class Alerta(Base):
    """Lo que la central de inteligencia debe atender."""
    __tablename__ = "alerta"

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int] = mapped_column(ForeignKey("jornada.id"))
    tipo: Mapped[TipoAlerta] = mapped_column(Enum(TipoAlerta))
    # A quien se refiere, cuando se refiere a alguien. Una llegada
    # marcada desde lejos se rechaza y el hito no se guarda, asi que sin
    # esto no quedaria a quien preguntarle. Las alertas de la jornada
    # entera --sin reporte, horas extra-- la dejan vacia.
    persona_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    mensaje: Mapped[str] = mapped_column(String(400))
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atendida: Mapped[bool] = mapped_column(Boolean, default=False)
    atendida_por_id: Mapped[int | None] = mapped_column(ForeignKey("persona.id"), nullable=True)
    resolucion: Mapped[str | None] = mapped_column(String(400), nullable=True)

    jornada: Mapped[Jornada] = relationship()
    # Hay dos llaves a persona --esta y atendida_por_id-- asi que hay que
    # decir cual: sin esto el modelo entero no se puede armar.
    persona: Mapped["Persona | None"] = relationship(foreign_keys=[persona_id])


class Notificacion(Base):
    """Un aviso que sale de la empresa: correo o WhatsApp.

    En el demo se registra; el envio real se conecta despues.

    `servicio_id` era obligatorio, y con eso el sistema no sabia mandar
    nada que no fuera sobre un servicio: ni la invitacion de acceso de
    alguien que acaba de entrar, ni el enlace de "olvide mi contrasena".
    Por eso esos dos los sigue entregando administracion a mano.

    Es la tercera tabla con la misma suposicion metida --"todo lo que
    pasa aqui pasa dentro de un servicio"--. `RegistroAccion` la tenia y
    por eso nacio `RegistroAdmin`. Aqui se quito en vez de hacer una
    tabla nueva: un aviso a una persona y un aviso sobre un servicio son
    la misma cosa saliendo por el mismo canal, y partirlos en dos habria
    dejado dos bandejas que revisar.
    """
    __tablename__ = "notificacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int | None] = mapped_column(ForeignKey("jornada.id"), nullable=True)
    # Vacio: el aviso no es sobre un servicio. Va a una persona.
    servicio_id: Mapped[int | None] = mapped_column(
        ForeignKey("servicio.id"), nullable=True)
    destinatario: Mapped[Destinatario] = mapped_column(Enum(Destinatario))
    canal: Mapped[Canal] = mapped_column(Enum(Canal))
    correo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    asunto: Mapped[str] = mapped_column(String(200))
    cuerpo: Mapped[str] = mapped_column(String(2000))
    enlace_seguimiento: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # La ficha del aviso: pares "clave: valor" que se pintan en una tabla
    # de dos columnas. Quien va, en que unidad, a que hora.
    #
    # Va aqui y no dentro del cuerpo porque un dato metido en un parrafo
    # es un dato que hay que leer entero para encontrar: el correo se
    # abre en el telefono a las seis de la manana y lo que se busca es la
    # placa. Se guarda como JSON de texto --lista de pares-- para no
    # atar la tabla a un tipo de Postgres por cuatro renglones.
    datos: Mapped[str | None] = mapped_column(Text, nullable=True)
    # En que idioma se escribio. El cuerpo y el asunto ya vienen
    # traducidos de quien origina el aviso; esto es para lo que el
    # despachador pone encima: el texto del boton y la linea de lo que
    # vence. Vacio: ingles, que es la omision de la casa.
    idioma: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # Con que cara sale. Vacio quiere decir el armazon de la casa; la
    # encuesta tiene el suyo --una sola llamada a la accion, en tres
    # idiomas-- porque lo que le pide al cliente es distinto.
    # El nombre de la plantilla del correo. Veinte caracteres era una
    # trampa: "encuesta_recordatorio" mide veintiuno y reventaba al
    # guardar, no al escribirlo. Un nombre de plantilla se lee en el
    # codigo y tiene que poder decir lo que es.
    plantilla: Mapped[str | None] = mapped_column(String(40), nullable=True)
    expira_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Cuando se ESCRIBIO el aviso. El nombre viene de cuando esta tabla
    # solo registraba; se queda porque ya hay codigo y pruebas que lo
    # leen, y renombrarlo no le devuelve el dia a nadie.
    enviada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Y cuando salio de verdad. Escribir el aviso y entregarlo son dos
    # cosas distintas: entre una y otra hay un proveedor que puede estar
    # caido, una direccion mal escrita y una bandeja que lo rebota.
    #
    #   pendiente  escrito, todavia no sale
    #   enviada    el proveedor lo acepto
    #   fallida    se intento lo suficiente y no se pudo
    #   sin_correo no hay a donde mandarlo (aviso interno, o sin direccion)
    #   vencida    se escribio y no salio a tiempo; ya no tiene sentido
    #              mandarlo (ver correo.HORAS_DE_VIDA)
    estado: Mapped[str] = mapped_column(String(12), default="pendiente",
                                        server_default="pendiente", index=True)
    intentos: Mapped[int] = mapped_column(Integer, default=0,
                                          server_default=text("0"))
    salio_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Lo ultimo que dijo el proveedor cuando dijo que no. Se guarda
    # porque "no salio" no le sirve a nadie: lo que se necesita saber es
    # si fue la direccion, la clave o que el buzon esta lleno.
    ultimo_error: Mapped[str | None] = mapped_column(String(300), nullable=True)

    servicio: Mapped[Servicio | None] = relationship()


# ================================================================ ACCESO

class Rol(str, enum.Enum):
    """Que puede hacer cada quien dentro del sistema."""
    PERSONAL_SEGURIDAD = "personal_seguridad"   # marca hitos, sube comprobantes
    CENTRAL = "central"                         # monitorea, ajusta con justificacion
    CONSULTOR = "consultor"                     # asigna, autoriza, cierra
    DIRECTOR_OPERACIONES = "director_operaciones"
    DIRECTOR_GENERAL = "director_general"       # decide en incidencias graves
    FINANZAS = "finanzas"
    # Autoriza el bono del mes y reparte los accesos. Lo que NO trae, y
    # es a proposito: depositar. Autorizar el bono y pagarlo son el
    # unico control que tiene ese dinero, y juntos en una mano el
    # control es la buena fe.
    RECURSOS_HUMANOS = "recursos_humanos"
    ADMIN = "admin"


class Usuario(Base):
    """Acceso ligado al correo del empleado y a su registro en Odoo.
    La contrasena la crea el propio empleado desde su correo."""
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"), unique=True)
    correo: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    hash_contrasena: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rol: Mapped[Rol] = mapped_column(Enum(Rol))
    # Su puesto configurable. Vacio: cae en los permisos de su rol, que
    # es como funciono el sistema hasta que existieron las categorias.
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categoria_acceso.id"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Cuando vio el recorrido de la primera vez. Va en el usuario y no en
    # el navegador: quien ya lo vio no tiene que volver a verlo porque
    # cambio de computadora, y quien nunca lo vio lo ve aunque entre
    # desde una que ya lo mostro.
    recorrido_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                          nullable=True)
    # Todo token emitido antes de esta hora deja de valer. Es lo que hace
    # que cambiar la contrasena tire las sesiones abiertas: con un token
    # sin estado, el que te la robo seguiria adentro doce horas mas.
    sesiones_desde: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    persona: Mapped[Persona] = relationship()
    categoria: Mapped["CategoriaAcceso | None"] = relationship()


class TipoRevision(str, enum.Enum):
    """En que sentido cambia de manos la unidad."""
    RECIBE = "recibe"        # la unidad pasa a manos del equipo
    ENTREGA = "entrega"      # el equipo la devuelve


class TipoDano(str, enum.Enum):
    """De que fue el golpe.

    Con nombre y no como texto libre por la misma razon que
    `MotivoCambio`: de aqui salen cuentas que la direccion va a pedir
    --cuantas unidades vuelven con dano al mes, de que tipo, en que
    plazas-- y escrito a mano no se puede contar. La descripcion en
    texto va aparte y es obligatoria; esto solo sirve para agrupar.

    La lista es corta a proposito: se elige de un vistazo en un telefono,
    a las seis de la manana. `OTRO` existe para que nadie se quede
    atorado escogiendo.
    """
    RAYON = "rayon"
    GOLPE = "golpe"            # abolladura
    CRISTAL = "cristal"
    LLANTA = "llanta"
    MECANICO = "mecanico"
    OTRO = "otro"


class AnguloFoto(str, enum.Enum):
    FRENTE = "frente"
    ATRAS = "atras"
    IZQUIERDO = "izquierdo"
    DERECHO = "derecho"
    # El tablero con el kilometraje a la vista. Los cuatro lados prueban
    # como estaba la lata; este prueba el numero, que hasta hoy era un
    # dato tecleado y nada mas: al entregar, "recorrio 1,800 km" salia de
    # dos cifras que alguien escribio de memoria.
    ODOMETRO = "odometro"
    DANO = "dano"            # un golpe en particular, de cerca


class RevisionUnidad(Base):
    """El estado de la unidad cuando cambia de manos.

    El dano al vehiculo siempre aparece despues y sin dueno: un golpe
    que nadie vio al recibir se discute tres semanas mas tarde, sin
    forma de saber quien la traia. Cuatro fotos y una firma en el
    momento en que cambia de manos son lo unico que lo resuelve, porque
    es el unico momento en que todavia se puede saber.

    Va por servicio y solo cuando cambia de manos: un implantado que usa
    la misma camioneta veintidos dias no se revisa veintidos veces.
    """
    __tablename__ = "revision_unidad"
    __table_args__ = (
        UniqueConstraint("servicio_id", "vehiculo_id", "tipo",
                         name="uq_revision_servicio_unidad_tipo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(
        ForeignKey("servicio.id", ondelete="CASCADE"), index=True)
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("vehiculo.id"),
                                             index=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    tipo: Mapped[TipoRevision] = mapped_column(String(10))
    kilometraje: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # El tanque como se lee en el tablero: octavos, de 0 a 8. Pedir
    # litros es pedir que alguien invente un numero.
    combustible_octavos: Mapped[int | None] = mapped_column(Integer,
                                                             nullable=True)
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)

    # La declaracion de dano. Una sola pregunta, y lo que significa lo
    # dice `tipo`:
    #
    #   recibe  + hubo_dano   la recibio golpeada. No es suyo, y
    #                         declararlo es lo que lo protege.
    #   entrega + hubo_dano   se golpeo durante su servicio, y ahi dice
    #                         que paso.
    #
    # Por eso no hacen falta dos juegos de columnas. Y por eso la
    # pregunta es obligatoria: una casilla opcional se queda vacia, y
    # quien recibe una camioneta golpeada con prisa no va a documentar
    # por su cuenta un dano que no hizo --que es justo donde le hara
    # falta tres semanas despues--.
    hubo_dano: Mapped[bool] = mapped_column(Boolean, default=False)
    dano_tipo: Mapped[TipoDano | None] = mapped_column(String(12),
                                                       nullable=True)
    dano_nota: Mapped[str | None] = mapped_column(Text, nullable=True)

    firma: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    momento: Mapped[datetime] = mapped_column(DateTime)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    vehiculo: Mapped["Vehiculo"] = relationship()
    persona: Mapped["Persona"] = relationship()
    fotos: Mapped[list["FotoRevision"]] = relationship(
        cascade="all, delete-orphan")


class FotoRevision(Base):
    """Cada foto, con su hora y su lugar.

    Una foto sin cuando ni donde no prueba nada: es la misma razon por
    la que los hitos llevan geolocalizacion.
    """
    __tablename__ = "foto_revision"

    id: Mapped[int] = mapped_column(primary_key=True)
    revision_id: Mapped[int] = mapped_column(
        ForeignKey("revision_unidad.id", ondelete="CASCADE"), index=True)
    angulo: Mapped[AnguloFoto] = mapped_column(String(12))
    imagen: Mapped[str] = mapped_column(Text)
    nota: Mapped[str | None] = mapped_column(String(200), nullable=True)
    momento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)


class SuscripcionPush(Base):
    """A donde mandarle un aviso al telefono de alguien.

    Una persona puede tener varios: el suyo y el de la empresa, o uno
    nuevo. Cada uno es una fila. El endpoint lo da el navegador y es
    unico; cuando el telefono se pierde o desinstala la app, el servicio
    de avisos contesta que ya no vale y la fila se apaga sola.
    """
    __tablename__ = "suscripcion_push"
    __table_args__ = (UniqueConstraint("endpoint",
                                       name="uq_suscripcion_endpoint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[int] = mapped_column(
        ForeignKey("persona.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    agente: Mapped[str | None] = mapped_column(String(300), nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True,
                                         server_default=text("true"))
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    ultimo_aviso_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                              nullable=True)

    persona: Mapped["Persona"] = relationship()


class CategoriaAcceso(Base):
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


class TipoInvitacion(str, enum.Enum):
    """Las dos razones por las que se manda un enlace de contrasena.

    Usan el mismo esqueleto y no son lo mismo: la invitacion vive tres
    dias porque quien entra nuevo quiza no revisa el correo hoy; la
    recuperacion dura poco, porque es la llave de una cuenta que ya
    existe y ya tiene cosas adentro.
    """
    INVITACION = "invitacion"
    RECUPERACION = "recuperacion"
    # Cuatro digitos que el consultor o la central le dictan por
    # telefono al personal de campo. Su correo es personal y la empresa
    # no lo controla, asi que lo suyo no va por correo.
    CODIGO_CAMPO = "codigo_campo"


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
    # Cuantas veces se fallo. Solo cuenta para el codigo de cuatro
    # digitos: a los cinco fallos el codigo se muere y hay que pedir
    # otro. Vive aqui y no en Redis porque `intentos.py` se abre si Redis
    # no contesta, y eso dejaria diez mil combinaciones sin candado.
    fallos: Mapped[int] = mapped_column(Integer, default=0)

    usuario: Mapped[Usuario] = relationship()


class RegistroAccion(Base):
    """Bitacora de quien hizo que sobre cada servicio.

    Los consultores pueden trabajar la cartera de otro para cubrir ausencias;
    cuando eso pasa, la accion queda marcada como cobertura y se identifica
    tanto a quien actuo como al consultor titular del servicio.
    """
    __tablename__ = "registro_accion"

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicio.id"))
    jornada_id: Mapped[int | None] = mapped_column(ForeignKey("jornada.id"), nullable=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    rol: Mapped[Rol] = mapped_column(Enum(Rol))
    accion: Mapped[str] = mapped_column(String(80))
    detalle: Mapped[str | None] = mapped_column(String(400), nullable=True)
    en_cobertura: Mapped[bool] = mapped_column(Boolean, default=False)
    titular_id: Mapped[int | None] = mapped_column(ForeignKey("persona.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    persona: Mapped[Persona] = relationship(foreign_keys=[persona_id])


class RegistroAdmin(Base):
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


# ================================================================ COTIZACION

class EstatusCotizacion(str, enum.Enum):
    BORRADOR = "borrador"
    ENVIADA = "enviada"
    AUTORIZADA = "autorizada"
    RECHAZADA = "rechazada"
    SUSTITUIDA = "sustituida"        # la reemplazo una recotizacion


class TipoLinea(str, enum.Enum):
    RECURSO = "recurso"
    VEHICULO = "vehiculo"
    VIATICOS = "viaticos"


class Cotizacion(Base):
    """Lo que se le cotizo al cliente. Es la referencia del comparativo de cierre.
    Una recotizacion crea una version nueva y deja la anterior como sustituida."""
    __tablename__ = "cotizacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicio.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    tarifario_id: Mapped[int] = mapped_column(ForeignKey("tarifario.id"))
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    tipo_cambio: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    viaticos_incluidos: Mapped[bool] = mapped_column(Boolean, default=True)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    estatus: Mapped[EstatusCotizacion] = mapped_column(
        Enum(EstatusCotizacion), default=EstatusCotizacion.BORRADOR)
    motivo_recotizacion: Mapped[str | None] = mapped_column(String(400), nullable=True)
    creada_por_id: Mapped[int | None] = mapped_column(ForeignKey("persona.id"), nullable=True)
    autorizada_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    autorizada_por: Mapped[str | None] = mapped_column(String(160), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    servicio: Mapped[Servicio] = relationship()
    lineas: Mapped[list["LineaCotizacion"]] = relationship(
        back_populates="cotizacion", cascade="all, delete-orphan")


class LineaCotizacion(Base):
    """Una linea por dia y por recurso cotizado."""
    __tablename__ = "linea_cotizacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizacion.id"))
    fecha: Mapped[date] = mapped_column(Date)
    equipo_clave: Mapped[str] = mapped_column(String(40), default="EQ-1")
    modalidad_id: Mapped[int] = mapped_column(ForeignKey("modalidad.id"))
    tipo: Mapped[TipoLinea] = mapped_column(Enum(TipoLinea))
    perfil_id: Mapped[int | None] = mapped_column(ForeignKey("perfil_personal.id"), nullable=True)
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categoria_vehiculo.id"), nullable=True)
    cantidad: Mapped[int] = mapped_column(Integer, default=1)
    precio_unitario: Mapped[float] = mapped_column(Numeric(12, 2))
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2))
    descripcion: Mapped[str | None] = mapped_column(String(200), nullable=True)

    cotizacion: Mapped[Cotizacion] = relationship(back_populates="lineas")
    modalidad: Mapped[Modalidad] = relationship()
    perfil: Mapped[PerfilPersonal | None] = relationship()
    categoria: Mapped[CategoriaVehiculo | None] = relationship()


# ================================================================ CIERRE

class EstatusCierre(str, enum.Enum):
    ABIERTO = "abierto"                      # comprobacion: las 24 h del personal
    SIN_VISTO_BUENO = "sin_visto_bueno"      # las 24 h del consultor
    EN_REVISION_IA = "en_revision_ia"
    ENVIADO_FINANZAS = "enviado_finanzas"
    DEVUELTO_A_OPERACION = "devuelto_a_operacion"
    APROBADO = "aprobado"
    FACTURADO = "facturado"


class TipoDesviacion(str, enum.Enum):
    DIAS_DE_MAS = "dias_de_mas"
    DIAS_DE_MENOS = "dias_de_menos"
    RECURSO_NO_COTIZADO = "recurso_no_cotizado"
    HORAS_EXTRA = "horas_extra"
    VIATICO_EXCEDIDO = "viatico_excedido"
    VIATICO_SIN_COMPROBAR = "viatico_sin_comprobar"
    VIATICO_NO_CERRADO = "viatico_no_cerrado"
    COBRO_MENOR = "cobro_menor"


class Cierre(Base):
    """El consultor tiene 24 horas tras el cierre de viaticos del personal.
    Maximo 48 horas tras el termino del servicio para cerrar y facturar.

    Uno por servicio en el eventual y uno por mes de contrato en el
    implantado (seccion 56): el implantado no termina, cada mes recorre
    la cadena de dos relojes por su cuenta.
    """
    __tablename__ = "cierre"
    # El eventual conserva su regla --a lo mas un cierre por servicio--
    # como indice parcial. La restriccion de columna no dejaba vivir al
    # implantado, que lleva un cierre por mes con el mismo folio.
    __table_args__ = (
        Index("uq_cierre_del_eventual", "servicio_id", unique=True,
              postgresql_where=text("contrato_id IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicio.id"))
    # El mes de contrato, en el implantado; vacio en el eventual.
    contrato_id: Mapped[int | None] = mapped_column(
        ForeignKey("contrato_implantado.id"), nullable=True, unique=True)
    abierto_en: Mapped[datetime] = mapped_column(DateTime)
    limite_consultor: Mapped[datetime] = mapped_column(DateTime)
    # Los dos relojes. `abierto_en` es T0 --el termino general, o la
    # cancelacion--; `comprobacion_hasta` = T0 + 24 h es el plazo del
    # personal; `visto_bueno_desde` es T1, cuando arranco el consultor,
    # y `limite_consultor` = T1 + 24 h. Mientras T1 no llega, el limite
    # del consultor queda provisional en T0 + 48 h.
    comprobacion_hasta: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    visto_bueno_desde: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    # "termino" o "cancelacion": la cancelacion es un termino con su
    # propia revision.
    motivo_apertura: Mapped[str | None] = mapped_column(
        String(20), nullable=True)
    estatus: Mapped[EstatusCierre] = mapped_column(
        Enum(EstatusCierre), default=EstatusCierre.ABIERTO)
    total_cotizado: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total_ejecutado: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cerrado_por_id: Mapped[int | None] = mapped_column(ForeignKey("persona.id"), nullable=True)
    dentro_de_plazo: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    devuelto_motivo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    aprobado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    aprobado_por_id: Mapped[int | None] = mapped_column(ForeignKey("persona.id"), nullable=True)
    # La factura, del lado de Odoo. `factura_odoo` guarda el folio que
    # Odoo devuelve: es lo unico que permite contestar "¿ya se facturo?"
    # sin abrir Odoo, y lo que amarra este servicio con ese documento.
    #
    # `factura_error` guarda por que no salio. Un envio que falla en
    # silencio deja un servicio aprobado que nadie cobra: el error tiene
    # que verse en la bandeja, no en un log que nadie lee.
    facturado_en: Mapped[datetime | None] = mapped_column(DateTime,
                                                          nullable=True)
    factura_odoo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    factura_error: Mapped[str | None] = mapped_column(String(400),
                                                      nullable=True)

    servicio: Mapped[Servicio] = relationship()
    contrato: Mapped["ContratoImplantado | None"] = relationship()
    desviaciones: Mapped[list["Desviacion"]] = relationship(
        back_populates="cierre", cascade="all, delete-orphan")


class Desviacion(Base):
    """Solo las desviaciones sin respaldo detonan el escalamiento.
    Respaldada = recotizada y autorizada por el cliente."""
    __tablename__ = "desviacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    cierre_id: Mapped[int] = mapped_column(ForeignKey("cierre.id"))
    tipo: Mapped[TipoDesviacion] = mapped_column(Enum(TipoDesviacion))
    descripcion: Mapped[str] = mapped_column(String(500))
    monto: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    respaldada: Mapped[bool] = mapped_column(Boolean, default=False)
    justificacion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    escalada: Mapped[bool] = mapped_column(Boolean, default=False)
    detectada_por: Mapped[str] = mapped_column(String(40), default="sistema")

    cierre: Mapped[Cierre] = relationship(back_populates="desviaciones")


# ================================================================ IMPLANTADOS

class DiasServicio(str, enum.Enum):
    """Que dias de la semana cubre el implantado.

    El fin de semana que no entra aqui no es servicio: no se cobra, nadie
    se presenta y en el calendario se ve gris. El que si entra se cobra
    como dia adicional y hay que decir quien lo cubre, porque el que
    trabajo de lunes a viernes descansa.
    """
    LUNES_VIERNES = "lunes_viernes"
    LUNES_SABADO = "lunes_sabado"
    TODOS = "todos"


class EsquemaCotizacionImplantado(str, enum.Enum):
    POR_DIA = "por_dia"              # 22 dias base mas fines de semana aparte
    MES_COMPLETO = "mes_completo"    # un costo total por el mes, con todo incluido


class MotivoReemplazo(str, enum.Enum):
    DESCANSO = "descanso"
    ENFERMEDAD = "enfermedad"
    CONTINGENCIA = "contingencia"
    BAJA = "baja"


class ContratoImplantado(Base):
    """Servicio de contratacion mensual con recursos fijos asignados.

    El procedimiento diario es igual al eventual; lo que cambia es que se
    contrata por mes, con una base de dias habiles, y los fines de semana
    son dias adicionales.
    """
    __tablename__ = "contrato_implantado"
    __table_args__ = (UniqueConstraint("servicio_id", "anio", "mes"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicio.id"))
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    dias_servicio: Mapped[DiasServicio] = mapped_column(
        Enum(DiasServicio), default=DiasServicio.LUNES_VIERNES)
    esquema: Mapped[EsquemaCotizacionImplantado] = mapped_column(
        Enum(EsquemaCotizacionImplantado),
        default=EsquemaCotizacionImplantado.POR_DIA)
    incluye_fines_de_semana: Mapped[bool] = mapped_column(Boolean, default=False)
    # El primer mes casi nunca empieza el dia 1. Se cobra lo que se
    # trabajo y el corte cae el ultimo dia del mes: el siguiente arranca
    # limpio el dia 1. Vacio quiere decir mes completo.
    desde_dia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dias_base: Mapped[int] = mapped_column(Integer, default=22)
    hora_presentacion: Mapped[str] = mapped_column(String(8), default="08:00:00")
    modalidad_id: Mapped[int] = mapped_column(ForeignKey("modalidad.id"))

    # Recursos fijos del mes
    titular_id: Mapped[int | None] = mapped_column(ForeignKey("persona.id"), nullable=True)
    titular_rotacion_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)   # esquema 12 por 36 (Brasil)
    vehiculo_id: Mapped[int | None] = mapped_column(ForeignKey("vehiculo.id"), nullable=True)

    # Precios del mes
    precio_mes_vehiculo: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    precio_dia_personal: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    precio_dia_adicional: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    precio_mes_completo: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    generado: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    servicio: Mapped[Servicio] = relationship()
    # Se conservan por comodidad de lectura —son el primer conductor y la
    # primera unidad de la plantilla— pero la que manda es la plantilla.
    titular: Mapped[Persona | None] = relationship(foreign_keys=[titular_id])
    vehiculo: Mapped[Vehiculo | None] = relationship()
    modalidad: Mapped[Modalidad] = relationship()
    plantilla: Mapped[list["PersonaImplantado"]] = relationship(
        cascade="all, delete-orphan")
    unidades: Mapped[list["UnidadImplantado"]] = relationship(
        cascade="all, delete-orphan")


class TabuladorImplantado(Base):
    """El tabulador de viaticos de UN servicio implantado.

    El de la empresa (`TabuladorViatico`) sirve para el eventual: un dia
    suelto, con las mismas reglas para todos. El implantado se negocia
    cliente por cliente —que se le da de comer al equipo, si se le paga
    el traslado, que pasa con la gasolina— y ese trato es parte del
    acuerdo, no del pais. Por eso cuelga del servicio: dos implantados
    de la misma ciudad pueden tener numeros distintos y los dos estar
    bien.

    Los montos son por dia y por persona, que es como se comprueban y
    como se reparten cuando el consultor fija el mes.
    """
    __tablename__ = "tabulador_implantado"
    __table_args__ = (UniqueConstraint("servicio_id", "concepto"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(
        ForeignKey("servicio.id", ondelete="CASCADE"), index=True)
    concepto: Mapped[ConceptoViatico] = mapped_column(Enum(ConceptoViatico))
    monto: Mapped[float] = mapped_column(Numeric(12, 2), default=0,
                                         server_default="0")
    # El concepto que existe pero no tiene numero fijo: el consultor
    # captura descripcion y monto el dia que toca.
    monto_abierto: Mapped[bool] = mapped_column(Boolean, default=False,
                                                server_default=text("false"))
    nota: Mapped[str | None] = mapped_column(String(300), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True,
                                         server_default=text("true"))


class AcuerdoImplantado(Base):
    """El alcance del servicio implantado, que no cambia mes con mes.

    Vive aparte del contrato porque el contrato es el mes que se factura
    y esto es el trato: que cubre, que no, hasta donde llega y donde se
    presenta el equipo todos los dias. Repetirlo en cada mes seria doce
    copias de lo mismo y doce lugares donde corregirlo.

    Es tambien lo que la hoja del implantado imprime: el que llega a
    cubrir un dia no conoce el servicio, y "lo de siempre" no le dice
    nada.
    """
    __tablename__ = "acuerdo_implantado"
    __table_args__ = (UniqueConstraint("servicio_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(
        ForeignKey("servicio.id", ondelete="CASCADE"))

    # Que si y que no. Lo segundo importa tanto como lo primero: el
    # conflicto con el cliente casi siempre nace de algo que nadie dijo
    # que no estaba incluido.
    cubre: Mapped[str | None] = mapped_column(Text, nullable=True)
    no_cubre: Mapped[str | None] = mapped_column(Text, nullable=True)
    zona_operacion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    dias_semana: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Cuando arranca y que dias corre. Viven en el acuerdo y no en el
    # contrato del mes porque son parte del trato —es lo que se le dijo
    # al cliente— y porque el acuerdo se guarda antes: el contrato puede
    # abrirse manana y el dia de inicio no se puede perder en el camino.
    fecha_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    dias_servicio: Mapped[DiasServicio | None] = mapped_column(
        Enum(DiasServicio), nullable=True)

    # Como se cubre el puesto. Son dos operaciones distintas y hay que
    # decir cual es desde el alta, porque de aqui sale el calendario:
    #
    #   natural  una persona, doce horas corridas, los dias que diga el
    #            acuerdo. Es lo que opera Centauro en Mexico.
    #   12x36    dos personas que se alternan dia con dia y cubren los
    #            siete dias de la semana. Es la escala de Brasil: doce
    #            horas de trabajo por treinta y seis de descanso.
    #
    # Va como texto de codigo y no como ENUM de Postgres, igual que el
    # resto de las columnas que llevan un codigo: agregar una escala
    # manana no deberia necesitar tocar la base.
    turno: Mapped[str] = mapped_column(String(10), default="natural",
                                       server_default="natural")

    # El punto de inicio es el mismo todos los dias: se captura una vez
    # y cada jornada del mes lo hereda.
    origen_direccion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    origen_lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    origen_lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    geocerca_metros: Mapped[int] = mapped_column(Integer, default=500)

    # Con quien se reporta el conductor al llegar, y a quien le avisa si
    # algo cambia. En un eventual lo resuelve el consultor por telefono;
    # en un implantado el conductor esta solo todos los dias.
    reporta_a_nombre: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reporta_a_apellidos: Mapped[str | None] = mapped_column(String(160),
                                                            nullable=True)
    reporta_a_telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reporta_a_correo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    protocolo_contacto: Mapped[str | None] = mapped_column(Text, nullable=True)

    # La version de la hoja y cuando se libero. Vive aqui y no en el
    # servicio porque la hoja del implantado es la del acuerdo: se
    # vuelve a liberar cuando el acuerdo cambia, no cuando cambia un dia.
    version_hoja: Mapped[int] = mapped_column(Integer, default=0,
                                              server_default="0")
    hoja_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)

    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    servicio: Mapped["Servicio"] = relationship()


class Capacitacion(Base):
    """Lo que el conductor sabe hacer, aparte de manejar.

    En un eventual el cliente ve al equipo un dia; en un implantado le
    entrega a su ejecutivo la misma persona todos los dias del ano, y
    pregunta quien es. Manejo defensivo, primeros auxilios, la licencia:
    eso es lo que contesta esa pregunta.

    Lleva vigencia porque una certificacion vencida no es una
    certificacion, y el dia que importe nadie va a revisar la fecha.
    """
    __tablename__ = "capacitacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[int] = mapped_column(
        ForeignKey("persona.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(160))
    institucion: Mapped[str | None] = mapped_column(String(160), nullable=True)
    obtenida_en: Mapped[date | None] = mapped_column(Date, nullable=True)
    vigencia_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # El dia en que se aviso por ultima vez. La tarea corre diario y hay
    # dos momentos que avisan --treinta dias antes y el dia que vence--,
    # asi que sin esto un solo aviso se manda cada vez que alguien
    # reinicia la tarea el mismo dia.
    avisado_en: Mapped[date | None] = mapped_column(Date, nullable=True)

    persona: Mapped["Persona"] = relationship()

    @property
    def vigente(self) -> bool:
        """Sin fecha se toma por vigente: hay cursos que no caducan."""
        return self.vigencia_hasta is None or self.vigencia_hasta >= date.today()


class PersonaImplantado(Base):
    """La plantilla de personal del mes.

    Un implantado puede ser un conductor solo, o un conductor y un
    agente, o dos de cada uno: la combinacion la pide el cliente y se
    repite igual todos los dias del mes. Antes cabia una sola persona en
    el contrato y eso obligaba a inventar el resto a mano cada dia.

    Dos reglas que el sistema no deja romper: siempre hay al menos un
    conductor de seguridad, y toda unidad lleva su conductor. Una unidad
    sin conductor no es una unidad, es un coche estacionado.
    """
    __tablename__ = "persona_implantado"
    __table_args__ = (UniqueConstraint("contrato_id", "persona_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contrato_implantado.id", ondelete="CASCADE"), index=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    # Con que rol va todos los dias del mes. Cada dia lo hereda al
    # generarse, y ahi se puede cambiar si un dia toca otra cosa.
    rol_id: Mapped[int | None] = mapped_column(
        ForeignKey("perfil_personal.id"), nullable=True)
    # En que unidad va. Para el conductor es la que maneja; para el
    # agente, en la que se transporta.
    vehiculo_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehiculo.id", ondelete="SET NULL"), nullable=True)
    # Solo en 12x36: cual de las dos entra el primer dia. Lo dice el
    # consultor y no el orden en que se capturaron, porque el orden de
    # captura es un accidente y de esto sale quien trabaja el dia 1 de
    # cada mes que se abra despues.
    empieza: Mapped[bool] = mapped_column(Boolean, default=False,
                                          server_default=text("false"))

    persona: Mapped["Persona"] = relationship()
    rol: Mapped["PerfilPersonal | None"] = relationship()
    vehiculo: Mapped["Vehiculo | None"] = relationship()


class UnidadImplantado(Base):
    """Las unidades fijas del mes. Siempre las mismas, salvo taller."""
    __tablename__ = "unidad_implantado"
    __table_args__ = (UniqueConstraint("contrato_id", "vehiculo_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contrato_implantado.id", ondelete="CASCADE"), index=True)
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("vehiculo.id"))

    vehiculo: Mapped["Vehiculo"] = relationship()


class Reemplazo(Base):
    """Los reemplazos por descanso se resuelven sobre la marcha.
    El consultor da seguimiento durante el mes a los cambios de personal."""
    __tablename__ = "reemplazo"

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int] = mapped_column(ForeignKey("jornada.id"))
    sale_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    entra_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    motivo: Mapped[MotivoReemplazo] = mapped_column(Enum(MotivoReemplazo))
    nota: Mapped[str | None] = mapped_column(String(400), nullable=True)
    registrado_por_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    jornada: Mapped[Jornada] = relationship()
    sale: Mapped[Persona] = relationship(foreign_keys=[sale_id])
    entra: Mapped[Persona] = relationship(foreign_keys=[entra_id])


class DiaFestivo(Base):
    """Los festivos se trabajan como dias normales, pero la comision del
    personal se paga con un factor (al doble en Mexico)."""
    __tablename__ = "dia_festivo"
    __table_args__ = (UniqueConstraint("pais_id", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    fecha: Mapped[date] = mapped_column(Date, index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    factor_comision: Mapped[float] = mapped_column(Numeric(4, 2), default=2)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


# ================================================================ BONOS

class CodigoCriterio(str, enum.Enum):
    PUNTUALIDAD = "puntualidad"
    SEGUIMIENTO_APP = "seguimiento_app"
    CAPACITACION = "capacitacion"
    CIERRE_VIATICOS = "cierre_viaticos"
    # Que la unidad se entregue documentada: la revision de entrega
    # existe y esta completa. Ojo con lo que NO mide: el dano. El dano
    # lo declara quien recibe, asi que medirlo aqui seria dejar que la
    # palabra de uno le cueste el bono a otro sin que nadie lo revise.
    # El dano ya tiene su camino --avisa al consultor, y si amerita se
    # vuelve incidencia con visto bueno-- y la incidencia apaga el mes.
    ENTREGA_UNIDAD = "entrega_unidad"
    # Que el cliente lo pida por nombre. La unica senal de calidad que
    # el sistema puede contar solo, y la marca un humano: el consultor
    # al armar el equipo.
    RECOMPRA = "recompra"


class GravedadIncidencia(str, enum.Enum):
    ERROR_MENOR = "error_menor"    # solo retroalimentacion documentada
    LEVE = "leve"                  # quita todas las estrellas del mes
    GRAVE = "grave"                # lo gestiona RRHH, puede derivar en baja


class EstatusEvaluacion(str, enum.Enum):
    CALCULADA = "calculada"
    AUTORIZADA = "autorizada"
    PAGADA = "pagada"


class CriterioEstrella(Base):
    """Catalogo parametrizable: cada estrella tiene su monto mensual."""
    __tablename__ = "criterio_estrella"
    __table_args__ = (UniqueConstraint("pais_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    codigo: Mapped[CodigoCriterio] = mapped_column(Enum(CodigoCriterio))
    nombre: Mapped[str] = mapped_column(String(120))
    umbral_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=100)
    monto_mensual: Mapped[float] = mapped_column(Numeric(12, 2))
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    # El margen. Un umbral de 100 por ciento castiga igual al que llego
    # dos minutos tarde una vez y al que llego cuarenta tarde tres
    # veces, y lo que no distingue no motiva. Los dos numeros van
    # juntos: tantos minutos, tantas veces en el mes. En cero, no hay
    # margen y el umbral manda solo --que es como estaba.
    tolerancia_minutos: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    tolerancia_ocasiones: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    # Si su monto entra al reparto cuando el criterio no aplica.
    #
    # Casi siempre si: un mes sin viaticos no debe cobrarse de menos,
    # asi que esos 390 se reparten entre los demas. Pero hay uno que
    # tiene que SUMAR y no restar --que el cliente lo vuelva a pedir--,
    # y con reparto no sumaba nada: si al que no lo pidieron le
    # repartian sus 130 entre los otros criterios, terminaba cobrando
    # exactamente igual que al que si pidieron. El criterio quedaba de
    # adorno. En `false`, su monto se queda fuera y el mes perfecto sin
    # recompra paga 2,470 en vez de 2,600: los 130 son lo que se gana
    # por que lo pidan, no lo que se pierde por que no.
    reparte: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Incidencia(Base):
    """La clasificacion la define el consultor y requiere visto bueno del
    director de operaciones antes de impactar el bono."""
    __tablename__ = "incidencia"

    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    servicio_id: Mapped[int | None] = mapped_column(ForeignKey("servicio.id"), nullable=True)
    jornada_id: Mapped[int | None] = mapped_column(ForeignKey("jornada.id"), nullable=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    gravedad: Mapped[GravedadIncidencia] = mapped_column(Enum(GravedadIncidencia))
    descripcion: Mapped[str] = mapped_column(String(600))
    clasificada_por_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    visto_bueno_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    autorizada: Mapped[bool] = mapped_column(Boolean, default=False)
    # Cuando se dio el visto bueno. Importa por el calendario del bono:
    # el mes se calcula el dia 3 y se paga el 5. Una incidencia
    # autorizada despues de eso no alcanza ese mes, y hay que poder
    # demostrar que llego tarde, no que se ignoro.
    visto_bueno_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    resolucion_direccion: Mapped[str | None] = mapped_column(String(600), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    persona: Mapped[Persona] = relationship(foreign_keys=[persona_id])


class EvaluacionMensual(Base):
    """Mensual y por persona, no por servicio: se agregan todas sus jornadas
    del mes, sean de servicios eventuales o implantados."""
    __tablename__ = "evaluacion_mensual"
    __table_args__ = (UniqueConstraint("persona_id", "anio", "mes"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    jornadas_evaluadas: Mapped[int] = mapped_column(Integer, default=0)
    estrellas: Mapped[int] = mapped_column(Integer, default=0)
    monto_bono: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    anulado_por_incidencia: Mapped[bool] = mapped_column(Boolean, default=False)
    incidencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidencia.id"), nullable=True)
    capacitacion_cumplida: Mapped[bool] = mapped_column(Boolean, default=False)
    estatus: Mapped[EstatusEvaluacion] = mapped_column(
        Enum(EstatusEvaluacion), default=EstatusEvaluacion.CALCULADA)
    calculada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    autorizada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    autorizada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)

    persona: Mapped[Persona] = relationship(foreign_keys=[persona_id])
    detalle: Mapped[list["ResultadoCriterio"]] = relationship(
        back_populates="evaluacion", cascade="all, delete-orphan")
    # Uno o ninguno: la llave unica del otro lado es el candado del
    # doble pago.
    pago: Mapped["PagoBono | None"] = relationship(
        back_populates="evaluacion", uselist=False)


class ResultadoCriterio(Base):
    __tablename__ = "resultado_criterio"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluacion_id: Mapped[int] = mapped_column(ForeignKey("evaluacion_mensual.id"))
    criterio_id: Mapped[int] = mapped_column(ForeignKey("criterio_estrella.id"))
    valor_medido: Mapped[float] = mapped_column(Numeric(5, 2))
    umbral: Mapped[float] = mapped_column(Numeric(5, 2))
    cumplido: Mapped[bool] = mapped_column(Boolean, default=False)
    # Un criterio no aplica cuando la persona no tuvo oportunidad de cumplirlo
    # (por ejemplo, un mes sin viaticos asignados). Se excluye del reparto.
    aplica: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    monto: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    detalle: Mapped[str | None] = mapped_column(String(400), nullable=True)

    evaluacion: Mapped[EvaluacionMensual] = relationship(back_populates="detalle")
    criterio: Mapped[CriterioEstrella] = relationship()


class PagoBono(Base):
    """El deposito del bono del mes.

    Va aparte de la nomina semanal a proposito. El bono se paga el dia 5
    --o el primer habil despues del 5-- y el corte semanal cae donde
    cae: amarrar uno al otro haria que la fecha de pago se moviera entre
    el 2 y el 8 segun el ano.

    La llave unica sobre la evaluacion es el candado del doble pago: una
    evaluacion tiene un pago o no tiene ninguno.
    """
    __tablename__ = "pago_bono"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluacion_id: Mapped[int] = mapped_column(
        ForeignKey("evaluacion_mensual.id"), unique=True, index=True)
    monto: Mapped[float] = mapped_column(Numeric(12, 2))
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    # El folio del banco. Mismo trato que el deposito de viaticos: sin
    # referencia no se registra, porque es lo unico que amarra el
    # movimiento del banco con el renglon del sistema.
    referencia: Mapped[str] = mapped_column(String(120))
    comprobante: Mapped[str | None] = mapped_column(Text, nullable=True)
    pagado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    pagado_por_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))

    evaluacion: Mapped["EvaluacionMensual"] = relationship(
        back_populates="pago")


# ================================================================ COMISION CONSULTOR

class EstatusComision(str, enum.Enum):
    GENERADA = "generada"
    RETENIDA = "retenida"         # incidencia grave: la decide el director general
    PAGADA = "pagada"
    PERDIDA = "perdida"           # cierre fuera de plazo, o decision de direccion
    AJUSTADA = "ajustada"         # factura no cobrada, se resta en el corte siguiente


class ComisionConsultor(Base):
    """1 por ciento en implantados, 3 por ciento en eventuales,
    en ambos casos descontando los viaticos. Se detona con el cierre
    validado por finanzas dentro de las 24 horas."""
    __tablename__ = "comision_consultor"
    # Una por servicio y consultor en el eventual; en el implantado, una
    # por mes de contrato (seccion 56): se factura mes con mes.
    __table_args__ = (
        Index("uq_comision_del_servicio", "servicio_id", "consultor_id",
              unique=True, postgresql_where=text("contrato_id IS NULL")),
        Index("uq_comision_del_mes", "contrato_id", "consultor_id",
              unique=True,
              postgresql_where=text("contrato_id IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicio.id"))
    # El mes de contrato, en el implantado; vacio en el eventual.
    contrato_id: Mapped[int | None] = mapped_column(
        ForeignKey("contrato_implantado.id"), nullable=True)
    consultor_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    facturacion: Mapped[float] = mapped_column(Numeric(12, 2))
    viaticos: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    base: Mapped[float] = mapped_column(Numeric(12, 2))
    porcentaje: Mapped[float] = mapped_column(Numeric(5, 2))
    monto: Mapped[float] = mapped_column(Numeric(12, 2))
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    estatus: Mapped[EstatusComision] = mapped_column(
        Enum(EstatusComision), default=EstatusComision.GENERADA)
    motivo: Mapped[str | None] = mapped_column(String(400), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    consultor: Mapped[Persona] = relationship(foreign_keys=[consultor_id])
    servicio: Mapped[Servicio] = relationship()


class PorcentajeComision(Base):
    """1 por ciento en implantados, 3 por ciento en eventuales.
    Parametrizable por pais para tropicalizar cada operacion."""
    __tablename__ = "porcentaje_comision"
    __table_args__ = (UniqueConstraint("pais_id", "tipo_servicio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    tipo_servicio: Mapped[TipoServicio] = mapped_column(Enum(TipoServicio))
    porcentaje: Mapped[float] = mapped_column(Numeric(5, 2))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class AjusteComision(Base):
    """Si una factura ya comisionada no se cobra, se resta en el corte siguiente."""
    __tablename__ = "ajuste_comision"

    id: Mapped[int] = mapped_column(primary_key=True)
    comision_id: Mapped[int] = mapped_column(ForeignKey("comision_consultor.id"))
    consultor_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    monto: Mapped[float] = mapped_column(Numeric(12, 2))   # negativo
    motivo: Mapped[str] = mapped_column(String(400))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    comision: Mapped[ComisionConsultor] = relationship()


# ================================================================ TASK SHEET

class EstatusTaskSheet(str, enum.Enum):
    BORRADOR = "borrador"
    PUBLICADO = "publicado"


class Hospital(Base):
    """Catalogo para proponer los tres mas cercanos al punto de origen."""
    __tablename__ = "hospital"

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    plaza_id: Mapped[int | None] = mapped_column(ForeignKey("plaza.id"), nullable=True)
    nombre: Mapped[str] = mapped_column(String(160))
    direccion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lat: Mapped[float] = mapped_column(Numeric(10, 7))
    lon: Mapped[float] = mapped_column(Numeric(10, 7))
    nivel_atencion: Mapped[NivelHospital | None] = mapped_column(
        Enum(NivelHospital), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class AgendaJornada(Base):
    """La agenda del dia, segun modalidad. La carga el consultor o la central."""
    __tablename__ = "agenda_jornada"

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int] = mapped_column(ForeignKey("jornada.id"), unique=True)
    resumen: Mapped[str | None] = mapped_column(String(300), nullable=True)
    puntos: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    archivo_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    cargada_por_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    actualizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    jornada: Mapped[Jornada] = relationship()


class ParadaAgenda(Base):
    """Una parada del dia: su hora y a donde se va.

    Van por separado y no en un bloque de texto porque la agenda cambia
    durante el dia: se mueve una comida, se cae una reunion, se agrega
    una escala. Corregir un renglon no debe obligar a reescribir el dia.
    """
    __tablename__ = "parada_agenda"

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int] = mapped_column(ForeignKey("jornada.id"), index=True)
    hora: Mapped[time | None] = mapped_column(Time, nullable=True)
    # El lugar y su direccion van juntos, como los dicta el cliente:
    # "Oficinas corporativas, Reforma 250 piso 12".
    lugar: Mapped[str] = mapped_column(String(400))
    # De cuando se capturaban por separado. Se sigue imprimiendo.
    direccion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notas: Mapped[str | None] = mapped_column(String(300), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    jornada: Mapped[Jornada] = relationship()


class TaskSheet(Base):
    """Ficha del servicio. Se comparte con el equipo y con el cliente.
    Cada publicacion crea una version; si hay cambios se les actualiza
    con la mas reciente."""
    __tablename__ = "task_sheet"
    __table_args__ = (UniqueConstraint("equipo_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicio.id"))
    # Un task sheet por equipo: cada equipo es independiente y su ejecutivo
    # solo debe ver lo suyo.
    equipo_id: Mapped[int] = mapped_column(ForeignKey("equipo.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    estatus: Mapped[EstatusTaskSheet] = mapped_column(
        Enum(EstatusTaskSheet), default=EstatusTaskSheet.BORRADOR)
    contenido: Mapped[str] = mapped_column(String(20000))   # JSON congelado
    motivo_cambio: Mapped[str | None] = mapped_column(String(300), nullable=True)
    publicado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    servicio: Mapped[Servicio] = relationship()
    equipo: Mapped[Equipo] = relationship()


class ServicioEliminado(Base):
    """Lo que queda de un servicio borrado: que era y quien lo quito.

    La bitacora del servicio se va con el servicio, asi que el rastro de
    la eliminacion tiene que vivir fuera de el.
    """
    __tablename__ = "servicio_eliminado"

    id: Mapped[int] = mapped_column(primary_key=True)
    folio: Mapped[str] = mapped_column(String(20))
    cliente: Mapped[str | None] = mapped_column(String(160), nullable=True)
    resumen: Mapped[str | None] = mapped_column(String(400), nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    eliminado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    eliminado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class Hotel(Base):
    """Donde se hospeda el ejecutivo. Muchas veces es el punto de origen.

    El catalogo crece con la operacion, no se llena de antemano: el
    hotel entra la primera vez que alguien lo captura y se queda
    disponible para la ciudad donde se uso. El que lleva tres meses sin
    ocuparse sale de la lista —no de la base— para que el consultor no
    tenga que buscar entre cien hoteles los cuatro que de verdad usa.
    """
    __tablename__ = "hotel"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Vacio en los que existian antes de la regla: cuentan como viejos y
    # se ganan su lugar en la lista usandose, no por antigüedad.
    creado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    plaza_id: Mapped[int | None] = mapped_column(ForeignKey("plaza.id"), nullable=True)
    nombre: Mapped[str] = mapped_column(String(160))
    direccion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    plaza: Mapped[Plaza | None] = relationship()


class Hospedaje(Base):
    """Donde se hospeda el ejecutivo durante el servicio.

    Uno por equipo y nada mas: cada equipo cuida a su ejecutivo principal
    y ese ejecutivo duerme en un hotel. Poder cargar dos dejaba la duda
    de a cual de los dos llegar, que es justo lo que la hoja tiene que
    resolver. Si el ejecutivo cambia de hotel, se corrige el que hay.

    Lo que hace falta es a donde llegar y a que numero llamar. Las fechas
    son opcionales: solo importan en la estancia larga que cambia de
    hotel a media semana, y ahi si dicen desde cuando."""
    __tablename__ = "hospedaje"
    __table_args__ = (UniqueConstraint("equipo_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicio.id"))
    equipo_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipo.id", ondelete="CASCADE"), nullable=True)
    hotel_id: Mapped[int | None] = mapped_column(ForeignKey("hotel.id"), nullable=True)
    # Si el hotel no esta en catalogo, se captura a mano.
    nombre_libre: Mapped[str | None] = mapped_column(String(160), nullable=True)
    direccion_libre: Mapped[str | None] = mapped_column(String(300), nullable=True)
    telefono_libre: Mapped[str | None] = mapped_column(String(40), nullable=True)
    habitacion: Mapped[str | None] = mapped_column(String(40), nullable=True)
    desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    notas: Mapped[str | None] = mapped_column(String(300), nullable=True)

    servicio: Mapped[Servicio] = relationship()
    equipo: Mapped["Equipo | None"] = relationship()
    hotel: Mapped[Hotel | None] = relationship()

    @property
    def nombre(self) -> str | None:
        return self.hotel.nombre if self.hotel else self.nombre_libre

    @property
    def direccion(self) -> str | None:
        return self.hotel.direccion if self.hotel else self.direccion_libre

    @property
    def telefono(self) -> str | None:
        return self.hotel.telefono if self.hotel else self.telefono_libre


# ================================================================ CONTINGENCIA

class CanalAlerta(str, enum.Enum):
    """Los tres canales para reportar una incidencia durante el servicio."""
    BOTON_APP = "boton_app"            # boton de panico de la app
    BOTON_VEHICULO = "boton_vehiculo"  # boton fisico, llega por el GPS
    LLAMADA = "llamada"                # a la central o directo al consultor


class EstatusAlerta(str, enum.Enum):
    ABIERTA = "abierta"                # nadie la ha tomado todavia
    EN_ATENCION = "en_atencion"        # la central la esta atendiendo
    CERRADA = "cerrada"


class AlertaIncidencia(Base):
    """Lo que pasa durante el servicio y obliga a actuar.

    No es lo mismo que Incidencia: aquella clasifica a una persona para el
    bono y la define el consultor despues. Esta es el hecho operativo, en
    vivo, y la atiende la central.
    """
    __tablename__ = "alerta_incidencia"

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int | None] = mapped_column(
        ForeignKey("jornada.id"), nullable=True, index=True)
    servicio_id: Mapped[int | None] = mapped_column(
        ForeignKey("servicio.id"), nullable=True, index=True)
    reporta_persona_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    canal: Mapped[CanalAlerta] = mapped_column(Enum(CanalAlerta))
    descripcion: Mapped[str | None] = mapped_column(String(600), nullable=True)
    # Donde estaba quien la disparo. El boton de panico casi nunca viene
    # con descripcion, asi que la ubicacion es lo unico que hay.
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    reportada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    estatus: Mapped[EstatusAlerta] = mapped_column(
        Enum(EstatusAlerta), default=EstatusAlerta.ABIERTA, index=True)
    tomada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    tomada_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    equipo_respuesta_enviado: Mapped[bool] = mapped_column(Boolean, default=False)
    cerrada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolucion: Mapped[str | None] = mapped_column(String(600), nullable=True)

    jornada: Mapped["Jornada | None"] = relationship()
    reporta: Mapped["Persona | None"] = relationship(
        foreign_keys=[reporta_persona_id])
    # Hay tres llaves a persona en esta tabla --quien reporta, quien toma
    # y quien cierra-- asi que cada relacion tiene que decir cual usa.
    tomada_por: Mapped["Persona | None"] = relationship(
        foreign_keys=[tomada_por_id])


class TipoRecurso(str, enum.Enum):
    PERSONAL = "personal"
    VEHICULO = "vehiculo"


class MotivoCambio(str, enum.Enum):
    """Por que cambio el recurso.

    Con nombre y no como texto libre porque de aqui salen dos cuentas que
    la direccion va a pedir: cuanto ausentismo hay y cuanto tiempo pasan
    las unidades en el taller. Escrito a mano no se puede contar.
    """
    VACACIONES = "vacaciones"
    ENFERMEDAD = "enfermedad"
    DESCANSO = "descanso"
    CONTINGENCIA = "contingencia"
    BAJA = "baja"
    MANTENIMIENTO_PREVENTIVO = "mantenimiento_preventivo"
    MANTENIMIENTO_CORRECTIVO = "mantenimiento_correctivo"
    OTRO = "otro"


class TallerVehiculo(Base):
    """Cuando una unidad esta fuera de circulacion.

    El dato es de Odoo, que es donde vive el mantenimiento de la flota:
    aqui solo se recibe y se respeta. Lo que importa de este lado es que
    una unidad en el taller deje de ofrecerse —hoy, sin esto, un coche
    desarmado le aparece libre a cualquier servicio, y asi es como se le
    promete al cliente un vehiculo que no existe—.

    El rango vive aparte de las jornadas a proposito: una unidad puede
    estar bloqueada sin tener servicio asignado, y es justo entonces
    cuando alguien se la da a otro.
    """
    __tablename__ = "taller_vehiculo"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehiculo_id: Mapped[int] = mapped_column(
        ForeignKey("vehiculo.id", ondelete="CASCADE"), index=True)
    desde: Mapped[date] = mapped_column(Date)
    # Vacio: sigue en el taller y no hay fecha de salida. Es lo normal en
    # un correctivo: nadie sabe cuando entrega el taller.
    hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    tipo: Mapped["MotivoCambio | None"] = mapped_column(
        Enum(MotivoCambio), nullable=True)
    taller: Mapped[str | None] = mapped_column(String(160), nullable=True)
    folio: Mapped[str | None] = mapped_column(String(60), nullable=True)
    nota: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Con que id vino de Odoo, para poder actualizarlo sin duplicarlo.
    odoo_id: Mapped[int | None] = mapped_column(Integer, nullable=True,
                                                unique=True)
    recibido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    vehiculo: Mapped["Vehiculo"] = relationship()

    def cubre(self, dia: date) -> bool:
        """Si ese dia la unidad esta fuera."""
        if dia < self.desde:
            return False
        return self.hasta is None or dia <= self.hasta


class ReemplazoRecurso(Base):
    """Cambio de recurso por contingencia.

    Lo hace el consultor, no la central: la central estabiliza el servicio,
    el consultor formaliza el cambio en el sistema.
    """
    __tablename__ = "reemplazo_recurso"

    id: Mapped[int] = mapped_column(primary_key=True)
    alerta_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerta_incidencia.id"), nullable=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicio.id"), index=True)
    desde_jornada_id: Mapped[int] = mapped_column(ForeignKey("jornada.id"))
    # Hasta cuando dura el cambio. Vacio quiere decir "de ahi en
    # adelante", que es como se resuelve una contingencia: nadie sabe
    # cuando vuelve el que salio. Lo planeado si tiene fin —unas
    # vacaciones se acaban, la unidad sale del taller— y decirlo evita
    # que el titular regrese y nadie se acuerde de devolverle sus dias.
    hasta_jornada_id: Mapped[int | None] = mapped_column(
        ForeignKey("jornada.id"), nullable=True)
    tipo: Mapped[TipoRecurso] = mapped_column(Enum(TipoRecurso))
    motivo_tipo: Mapped["MotivoCambio | None"] = mapped_column(
        Enum(MotivoCambio), nullable=True)

    sale_persona_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    entra_persona_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    sale_vehiculo_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehiculo.id"), nullable=True)
    entra_vehiculo_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehiculo.id"), nullable=True)

    motivo: Mapped[str] = mapped_column(String(600))
    # La hora que el sistema propuso para partir el dia: la ultima marca
    # de quien salio. Si no coincide con la que quedo en la asignacion,
    # alguien la corrigio, y ese alguien es `hecho_por_id`. Va vacia
    # cuando el cambio no partio ningun dia.
    hora_propuesta: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    jornadas_afectadas: Mapped[int] = mapped_column(Integer, default=0)
    hecho_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    # Cuando el titular volvio. El regreso no abre otro movimiento: recorre
    # el `hasta` de este y lo firma, para que el mes lea "Luis cubrio a
    # Marta del 10 al 24" y no dos cambios cruzados que nadie sabe cual
    # cierra a cual.
    regreso_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    regreso_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    # La hora que el sistema propuso para partir el dia del regreso: la
    # ultima marca del que cubria. Es la gemela de `hora_propuesta`, que
    # es la del relevo que abrio el movimiento. Si no coincide con la que
    # quedo en la asignacion, alguien la corrigio, y ese alguien es
    # `regreso_por_id`. Va vacia cuando el regreso no partio ningun dia.
    hora_propuesta_regreso: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)


# ================================================================ NOMINA SEMANAL

class EstatusNomina(str, enum.Enum):
    CALCULADA = "calculada"        # se puede recalcular las veces que haga falta
    PAGADA = "pagada"              # ya salio el dinero, solo se corrige por ajuste


class NominaSemanal(Base):
    """El pago al personal de seguridad corre los lunes despues de mediodia.

    Corta todo lo que ya va en camino a facturacion y no se ha pagado. Si
    despues un servicio se regresa y cambia, la diferencia no se reabre
    aqui: se arrastra como ajuste a la nomina siguiente.
    """
    __tablename__ = "nomina_semanal"
    __table_args__ = (UniqueConstraint("pais_id", "fecha_corte"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    fecha_corte: Mapped[date] = mapped_column(Date, index=True)
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda))
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    estatus: Mapped[EstatusNomina] = mapped_column(
        Enum(EstatusNomina), default=EstatusNomina.CALCULADA)
    calculada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    pagada_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pagada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)

    renglones: Mapped[list["RenglonNomina"]] = relationship(
        back_populates="nomina", cascade="all, delete-orphan")


class RenglonNomina(Base):
    """Lo que se le paga a una persona en ese corte."""
    __tablename__ = "renglon_nomina"
    __table_args__ = (UniqueConstraint("nomina_id", "persona_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nomina_id: Mapped[int] = mapped_column(ForeignKey("nomina_semanal.id"))
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    nomina: Mapped[NominaSemanal] = relationship(back_populates="renglones")
    persona: Mapped[Persona] = relationship()
    conceptos: Mapped[list["ConceptoNomina"]] = relationship(
        back_populates="renglon", cascade="all, delete-orphan")


class ConceptoNomina(Base):
    """Cada jornada pagada, o cada ajuste arrastrado, con su monto.

    Sirve de doble proposito: es el detalle que ve la persona y es el
    candado que impide pagar dos veces la misma jornada.

    Ese candado vivia solo en Python --`jornadas_pendientes` saca lo que
    ya esta pagado y lo descuenta-- y entre leerlo y escribirlo hay una
    rendija: dos cortes calculados al mismo tiempo leen los dos que la
    jornada esta libre y los dos la toman. La nomina de la MISMA semana
    ya no puede duplicarse (`nomina_semanal` es unica por pais y fecha),
    pero dos cortes de semanas distintas del mismo pais si podian
    llevarse la misma jornada. Lo que sale por ahi es dinero pagado dos
    veces, y se descubre al mes siguiente o nunca.

    Por eso la base tambien lo sabe: una jornada se le paga a una
    persona una sola vez, en el corte que sea.

    `persona_id` esta duplicada a proposito --vive en el renglon-- y es
    el precio de que el candado quepa en una sola tabla. No se actualiza
    nunca: un concepto no se edita, y recalcular un corte borra sus
    renglones y los vuelve a escribir.
    """
    __tablename__ = "concepto_nomina"
    __table_args__ = (
        UniqueConstraint("jornada_id", "persona_id",
                         name="uq_concepto_jornada_persona"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    renglon_id: Mapped[int] = mapped_column(ForeignKey("renglon_nomina.id"))
    jornada_id: Mapped[int | None] = mapped_column(
        ForeignKey("jornada.id"), nullable=True, index=True)
    # A quien se le pago. Un ajuste no cuelga de ninguna jornada, y ahi
    # `jornada_id` va en nulo: Postgres no compara nulos entre si, asi
    # que la restriccion de arriba no le estorba a los ajustes --se
    # pueden arrastrar varios de la misma persona sin pelearse.
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"))
    ajuste_id: Mapped[int | None] = mapped_column(
        ForeignKey("ajuste_nomina.id"), nullable=True)
    descripcion: Mapped[str] = mapped_column(String(300))
    monto: Mapped[float] = mapped_column(Numeric(12, 2))
    factor_festivo: Mapped[float] = mapped_column(Numeric(4, 2), default=1)
    horas_extra: Mapped[int] = mapped_column(Integer, default=0)
    # Con que rol se pago ese dia. Se congela aqui y no se lee de la
    # asignacion: si alguien corrige el rol despues, el recibo de una
    # semana ya pagada no puede cambiar solo.
    rol_id: Mapped[int | None] = mapped_column(
        ForeignKey("perfil_personal.id"), nullable=True)

    renglon: Mapped[RenglonNomina] = relationship(back_populates="conceptos")
    rol: Mapped["PerfilPersonal | None"] = relationship()


class AjusteNomina(Base):
    """Diferencia que se arrastra a la semana siguiente.

    Se genera cuando un servicio ya pagado se regresa a operacion y cambia:
    el dinero ya salio, asi que la correccion viaja hacia adelante. El monto
    va con signo: positivo si se le debe, negativo si hay que descontarle.
    """
    __tablename__ = "ajuste_nomina"

    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("persona.id"), index=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    servicio_id: Mapped[int | None] = mapped_column(
        ForeignKey("servicio.id"), nullable=True)
    jornada_id: Mapped[int | None] = mapped_column(
        ForeignKey("jornada.id"), nullable=True)
    # De que es el ajuste. Sin esto, dos ajustes muy distintos —corregir
    # lo que se pago por un dia, y descontar viaticos que no se
    # comprobaron— compartian la llave (jornada, persona) y se tapaban
    # uno al otro: un descuento de viaticos hacia que la correccion de
    # nomina de ese mismo dia nunca se generara.
    concepto: Mapped[str] = mapped_column(
        String(30), default="manual", server_default="manual")
    monto: Mapped[float] = mapped_column(Numeric(12, 2))
    motivo: Mapped[str] = mapped_column(String(400))
    pagado_en_nomina_id: Mapped[int | None] = mapped_column(
        ForeignKey("nomina_semanal.id"), nullable=True)
    aplicado_en_nomina_id: Mapped[int | None] = mapped_column(
        ForeignKey("nomina_semanal.id"), nullable=True, index=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    creado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)

    persona: Mapped[Persona] = relationship(foreign_keys=[persona_id])


# ================================================================ ENCUESTAS

class TipoEncuesta(str, enum.Enum):
    EJECUTIVO = "ejecutivo"        # califica el servicio y al equipo
    SOLICITANTE = "solicitante"    # califica al consultor


class EstatusEncuesta(str, enum.Enum):
    ENVIADA = "enviada"
    RESPONDIDA = "respondida"
    EXPIRADA = "expirada"


class Encuesta(Base):
    """Encuesta corta al cierre del servicio.

    Son dos distintas: al ejecutivo se le pregunta por el servicio y el
    equipo; al solicitante, por el consultor que lo atendio. Van por
    correo con un enlace que expira.
    """
    __tablename__ = "encuesta"
    __table_args__ = (UniqueConstraint("servicio_id", "tipo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicio.id"), index=True)
    tipo: Mapped[TipoEncuesta] = mapped_column(Enum(TipoEncuesta))
    # A quien se evalua cuando es la del solicitante.
    consultor_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)

    destinatario_nombre: Mapped[str | None] = mapped_column(String(160), nullable=True)
    destinatario_correo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    idioma: Mapped[str] = mapped_column(String(2), server_default="en")

    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime)
    enviada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    respondida_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Cuando se le recordo. Uno solo por encuesta: el campo es lo que
    # impide que la tarea diaria mande el mismo recordatorio cada dia
    # --al ejecutivo de un cliente grande, diez correos por un servicio
    # no se leen como interes, se leen como acoso--.
    recordada_en: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    estatus: Mapped[EstatusEncuesta] = mapped_column(
        Enum(EstatusEncuesta), default=EstatusEncuesta.ENVIADA, index=True)

    calificacion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Una mala calificacion NO baja el bono sola: la clasifica el consultor,
    # igual que una incidencia.
    requiere_clasificacion: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default='false')
    incidencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidencia.id"), nullable=True)
    clasificada_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    nota_clasificacion: Mapped[str | None] = mapped_column(String(600), nullable=True)

    servicio: Mapped[Servicio] = relationship()
    respuestas: Mapped[list["RespuestaEncuesta"]] = relationship(
        back_populates="encuesta", cascade="all, delete-orphan")


class RespuestaEncuesta(Base):
    __tablename__ = "respuesta_encuesta"

    id: Mapped[int] = mapped_column(primary_key=True)
    encuesta_id: Mapped[int] = mapped_column(ForeignKey("encuesta.id"))
    pregunta: Mapped[str] = mapped_column(String(40))
    valor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    texto: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    encuesta: Mapped[Encuesta] = relationship(back_populates="respuestas")


# ================================================ TABLERO DE PROFESIONALISMO

class DimensionProfesionalismo(str, enum.Enum):
    ESTRELLAS = "estrellas"          # cumplimiento de los criterios del bono
    SATISFACCION = "satisfaccion"    # como lo califican los ejecutivos
    INCIDENCIAS = "incidencias"      # historial, solo las ya autorizadas
    CAPACITACION = "capacitacion"    # meses con la capacitacion al corriente
    EXPERIENCIA = "experiencia"      # horas acumuladas en Centauro


class PesoProfesionalismo(Base):
    """Cuanto pesa cada dimension en la calificacion. Suma 100.

    Vive en catalogo y no en el codigo porque es una decision de negocio
    que va a cambiar conforme se use el tablero.
    """
    __tablename__ = "peso_profesionalismo"
    __table_args__ = (UniqueConstraint("pais_id", "dimension"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"))
    dimension: Mapped[DimensionProfesionalismo] = mapped_column(
        Enum(DimensionProfesionalismo))
    peso: Mapped[float] = mapped_column(Numeric(5, 2))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ParametroProfesionalismo(Base):
    """Lo que no es peso: ventana de tiempo y castigo por incidencia."""
    __tablename__ = "parametro_profesionalismo"

    id: Mapped[int] = mapped_column(primary_key=True)
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id"), unique=True)
    meses_ventana: Mapped[int] = mapped_column(Integer, default=6,
                                               server_default="6")
    # Horas con las que se considera experiencia plena. No es un tope de
    # carrera: es la referencia para normalizar la dimension.
    horas_referencia: Mapped[int] = mapped_column(Integer, default=2000,
                                                  server_default="2000")
    castigo_error_menor: Mapped[float] = mapped_column(
        Numeric(5, 2), default=0, server_default="0")
    castigo_leve: Mapped[float] = mapped_column(
        Numeric(5, 2), default=25, server_default="25")
    castigo_grave: Mapped[float] = mapped_column(
        Numeric(5, 2), default=60, server_default="60")

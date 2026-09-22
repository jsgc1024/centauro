"""Esquemas de entrada y salida de la API."""
from datetime import date
from typing import Literal
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import texto

from app.models import (CodigoModalidad, CodigoVestimenta, ConceptoViatico,
                        EscenarioViatico, Moneda, MotivoRenta, NivelHospital,
                        TipoServicio)


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Regla de captura del sistema. Se declara una vez y cada esquema dice a
# que campos suyos aplica: los que teclea una persona, no los catalogos.
def _titulo(cls, v):
    return texto.titulo(v)


def _mayusculas(cls, v):
    return texto.mayusculas(v)


def capturado(*campos):
    """Inicial mayuscula por palabra."""
    return field_validator(*campos, mode="before")(_titulo)


def en_mayusculas(*campos):
    """Todo en mayuscula: el numero de vuelo."""
    return field_validator(*campos, mode="before")(_mayusculas)


# ---- pais / plaza
class PaisIn(Base):
    codigo: str
    nombre: str
    moneda_local: Moneda
    lada: str = ""          # clave internacional: +52, +55, +58
    anticipacion_aeropuerto_min: int = 45
    anticipacion_min: int = 30
    # Nombre IANA. De aqui sale la hora con la que se juzga todo lo de
    # ese pais: la ventana de marcado, el silencio de un servicio en
    # curso, el plazo del consultor para cerrar.
    zona_horaria: str = "America/Mexico_City"
    # En que lengua ve la app el personal de campo de este pais. No lo
    # elige el agente: sale de su plaza.
    idioma: str = "es"


class PaisOut(PaisIn):
    id: int
    activo: bool


class PlazaIn(Base):
    pais_id: int
    nombre: str
    tiene_recurso_local: bool = True


class PlazaOut(PlazaIn):
    fija: bool = False
    id: int
    activo: bool


# ---- recursos
class PerfilIn(Base):
    codigo: str
    nombre: str


class PerfilOut(PerfilIn):
    id: int
    activo: bool


class CategoriaVehiculoIn(Base):
    codigo: str
    nombre: str
    blindado: bool = False
    rendimiento_km_litro: Decimal


class CategoriaVehiculoOut(CategoriaVehiculoIn):
    id: int
    activo: bool


class ModalidadIn(Base):
    pais_id: int
    codigo: CodigoModalidad
    horas: Decimal
    horas_descanso: Decimal = Decimal("0")
    aplica_horas_extra: bool = False
    bloquea_dia_completo: bool = False
    # El recorrido tipico del dia, para proponer el combustible.
    km_estimados: int | None = None


class ModalidadOut(ModalidadIn):
    id: int


# ---- cliente
class ClienteIn(Base):
    nombre: str
    pais_id: int
    odoo_id: int | None = None
    tarifario_id: int | None = None


class ClienteOut(ClienteIn):
    id: int
    activo: bool


class SolicitanteIn(Base):
    cliente_id: int
    nombre: str
    apellidos: str | None = None
    correo: str | None = None
    telefono: str | None = None
    puesto: str | None = None

    _capturado = capturado("nombre", "apellidos", "puesto")


class SolicitanteOut(SolicitanteIn):
    id: int
    activo: bool
    completo: str | None = None


# ---- tarifario
class TarifarioIn(Base):
    nombre: str
    pais_id: int
    moneda: Moneda
    vigencia_desde: date
    vigencia_hasta: date | None = None


class TarifarioOut(TarifarioIn):
    id: int
    activo: bool


class TarifaRecursoIn(Base):
    tarifario_id: int
    perfil_id: int
    modalidad_id: int
    precio: Decimal
    precio_hora_extra: Decimal | None = None


class TarifaRecursoOut(TarifaRecursoIn):
    id: int


class TarifaVehiculoIn(Base):
    tarifario_id: int
    categoria_id: int
    modalidad_id: int
    precio: Decimal
    precio_mensual: Decimal | None = None


class TarifaVehiculoOut(TarifaVehiculoIn):
    id: int


# ---- viaticos
class TabuladorIn(Base):
    pais_id: int
    # Eventual e implantado llevan tabla aparte: no es la misma operacion.
    tipo_servicio: TipoServicio = TipoServicio.EVENTUAL
    concepto: ConceptoViatico
    escenario: EscenarioViatico
    monto: Decimal
    monto_abierto: bool = False


class TabuladorOut(TabuladorIn):
    id: int
    activo: bool


# ---- comisiones
class ComisionIn(Base):
    """Lo que se le paga al personal por un dia de servicio.

    Eventual e implantado llevan tabla aparte, y el perfil es el rol con
    el que se cubrio el dia.
    """
    pais_id: int
    tipo_servicio: TipoServicio = TipoServicio.EVENTUAL
    perfil_id: int
    modalidad_id: int
    monto: Decimal
    monto_hora_extra: Decimal | None = None
    moneda: Moneda


class ComisionOut(ComisionIn):
    id: int


# ================================================================ PERSONAL Y FLOTA
from datetime import datetime, time  # noqa: E402

from app.models import (EstatusCompra, EstatusJornada,  # noqa: E402
                        EstatusServicio, TipoCompra)


class PersonaIn(Base):
    """Personal de seguridad, sin puesto fijo.

    El rol —conductor, agente, coordinador, consultor de seguridad— no
    vive aqui: lo decide el consultor en cada tarea, y de ahi salen el
    precio al cliente y la comision que se le paga.
    """
    nombre: str
    correo: str
    plaza_id: int
    odoo_id: int | None = None
    es_freelance: bool = False


class PersonaOut(PersonaIn):
    id: int
    activo: bool
    # Vienen de Odoo, no se capturan aqui, pero el task sheet y las
    # pantallas los leen.
    telefono: str | None = None
    foto_url: str | None = None


class TarifaFreelanceIn(Base):
    persona_id: int
    modalidad_id: int
    costo: Decimal
    costo_hora_extra: Decimal | None = None
    moneda: Moneda


class TarifaFreelanceOut(TarifaFreelanceIn):
    id: int


class VehiculoIn(Base):
    placa: str
    categoria_id: int
    plaza_id: int
    costo_diario: Decimal | None = None
    color: str | None = None
    modelo_anio: int | None = None
    marca_modelo: str | None = None
    foto_url: str | None = None     # viene de Odoo

    # La marca, el modelo y el color NO pasan por la regla de captura, y
    # es por dos razones que apuntan al mismo lado.
    #
    # La primera: la unidad ya no se teclea. La manda Odoo, que es la
    # fuente de verdad de la flota.
    #
    # La segunda es la que mordia. Estos validadores corren en `before`,
    # o sea tambien al SALIR hacia la pantalla: el dato entraba bien,
    # se guardaba bien, y la consola lo enseñaba mal. "Chevrolet
    # Suburban LT" salia "Chevrolet Suburban Lt", y con el se perdian
    # AMG, GLS, 4x4 y cualquier placa de version. La regla es una ayuda
    # para quien teclea, no una correccion para quien ya escribio bien.
    #
    # El auto subarrendado si se captura a mano y si la conserva: vive
    # en `VehiculoSubarrendadoIn`, aqui abajo.
    _mayusculas = en_mayusculas("placa")


class VehiculoOut(VehiculoIn):
    id: int
    activo: bool
    rentado: bool = False
    arrendadora: str | None = None
    arrendadora_telefono: str | None = None
    motivo_renta: MotivoRenta | None = None
    renta_folio: str | None = None
    renta_por_cancelar: bool = False


class VehiculoRentadoIn(Base):
    """El auto que se subarrenda para un servicio.

    Aqui casi todo es obligatorio, al reves que en la flota propia: de la
    unidad de casa se sabe todo aunque el alta venga incompleta, y de un
    auto que se recibe en un estacionamiento no se sabe nada si no queda
    escrito hoy. Sin placas y color el equipo no lo reconoce, sin
    arrendadora y telefono nadie sabe a quien reclamarle si falla, y sin
    costo el servicio se ve mas rentable de lo que fue.
    """
    placa: str = Field(min_length=3, max_length=20)
    categoria_id: int
    plaza_id: int | None = None       # por defecto, la ciudad del equipo
    color: str = Field(min_length=2, max_length=40)
    marca_modelo: str = Field(min_length=2, max_length=80)
    modelo_anio: int = Field(ge=1990, le=2100)
    costo_diario: Decimal = Field(gt=0)
    arrendadora: str = Field(min_length=2, max_length=120)
    arrendadora_telefono: str = Field(min_length=7, max_length=40)
    motivo_renta: MotivoRenta
    forzar: bool = False

    _capturado = capturado("color", "marca_modelo", "arrendadora")
    _mayusculas = en_mayusculas("placa")


# ================================================================ SERVICIOS

class ParadaIn(Base):
    """Una parada del dia: su hora y a donde se va. Sin hora se queda al
    final, como pendiente de confirmar, que es como la manda el cliente
    muchas veces."""
    hora: time | None = None
    lugar: str
    direccion: str | None = None
    notas: str | None = None

    _capturado = capturado("lugar")


class JornadaIn(Base):
    fecha: date
    modalidad_id: int
    # Solo el dia 1 la trae: es la que amarra el arranque del servicio.
    # Los demas dias salen de su agenda y, mientras no la tengan, heredan
    # la del primer dia.
    hora_presentacion: time | None = None
    es_foraneo: bool = False
    km_estimados: int | None = None
    # El punto de inicio y el vuelo se pueden capturar desde el alta: son
    # parte del minimo para dar el servicio por programado. Siguen siendo
    # opcionales porque un implantado da de alta el mes entero de un golpe
    # y esos datos llegan dia con dia.
    origen_direccion: str | None = None
    origen_lat: Decimal | None = None
    origen_lon: Decimal | None = None
    geocerca_metros: int | None = None
    origen_aeropuerto: bool = False
    # Lo que dijo Google del lugar, aparte de lo que decidio el consultor.
    origen_google_aeropuerto: bool | None = None
    forzar_aeropuerto: bool = False
    vuelo_aerolinea: str | None = None
    vuelo_numero: str | None = None
    vuelo_hora: datetime | None = None
    vuelo_origen: str | None = None
    vuelo_tipo: Literal["llegada", "salida"] | None = None
    # La agenda del dia se puede capturar desde el alta: el consultor la
    # tiene en el correo del cliente cuando esta dando de alta. Va parada
    # por parada, como se lee y como se imprime.
    paradas: list["ParadaIn"] = []
    # De cuando la agenda era un bloque de texto. Se sigue aceptando.
    agenda_resumen: str | None = None
    agenda_puntos: str | None = None

    _capturado = capturado("vuelo_aerolinea", "vuelo_origen")
    _clave = en_mayusculas("vuelo_numero")


class EquipoIn(Base):
    # El alias lo pone el sistema (Alfa, Beta, Gamma...).
    clave: str | None = None
    descripcion: str | None = None
    # Donde opera. Vacio: la ciudad del servicio.
    plaza_id: int | None = None
    # A quien cuida este equipo. Si viene vacio, hereda el del servicio.
    ejecutivo_nombre: str | None = None
    ejecutivo_apellidos: str | None = None
    ejecutivo_correo: str | None = None
    ejecutivo_telefono: str | None = None
    jornadas: list[JornadaIn] = []

    _capturado = capturado("ejecutivo_nombre", "ejecutivo_apellidos")


class ServicioIn(Base):
    cliente_id: int
    pais_id: int
    plaza_id: int
    tipo: TipoServicio = TipoServicio.EVENTUAL
    consultor_id: int | None = None
    # Se elige de la lista del cliente, o se capturan los datos y se da de
    # alta solo.
    solicitante_id: int | None = None
    solicitante_nombre: str | None = None
    solicitante_apellidos: str | None = None
    solicitante_correo: str | None = None
    solicitante_telefono: str | None = None
    ejecutivo_nombre: str | None = None
    ejecutivo_apellidos: str | None = None
    ejecutivo_correo: str | None = None
    ejecutivo_telefono: str | None = None
    # Vacio en el solicitante: el idioma de su pais. Ver models.Servicio.
    idioma_ejecutivo: str = "en"
    idioma_solicitante: str | None = None
    # Casual, semiformal o formal. Solo el eventual la lleva.
    vestimenta: CodigoVestimenta | None = None
    servicio_origen_id: int | None = None
    equipos: list[EquipoIn] = []

    _capturado = capturado("solicitante_nombre", "solicitante_apellidos",
                           "ejecutivo_nombre", "ejecutivo_apellidos")


class VestimentaIn(Base):
    """Vacio la quita: un servicio sin codigo no dice nada, que no es lo
    mismo que decir "casual"."""
    vestimenta: CodigoVestimenta | None = None


class JornadaOut(Base):
    id: int
    fecha: date
    modalidad_id: int
    inicio_programado: datetime
    fin_programado: datetime
    es_foraneo: bool
    km_estimados: int | None
    estatus: EstatusJornada
    # Falso: la hora se heredo del dia 1 y nadie la ha confirmado.
    hora_confirmada: bool = False
    # El punto del dia y su vuelo: la pantalla los pinta ya capturados
    # en vez de abrir el formulario en blanco cada vez.
    origen_direccion: str | None = None
    origen_lat: Decimal | None = None
    origen_lon: Decimal | None = None
    geocerca_metros: int | None = None
    origen_aeropuerto: bool = False
    origen_google_aeropuerto: bool | None = None
    vuelo_aerolinea: str | None = None
    vuelo_numero: str | None = None
    vuelo_hora: datetime | None = None
    vuelo_origen: str | None = None
    vuelo_tipo: str | None = None


class EquipoOut(Base):
    id: int
    alias: str
    clave: str
    descripcion: str | None
    plaza_id: int | None = None
    # Ya resuelta: la suya o la del servicio.
    ciudad_id: int | None = None
    # Lo capturado en el equipo y, ya resuelto, a quien cuida de verdad:
    # la pantalla pinta el completo sin tener que repetir la herencia.
    ejecutivo_nombre: str | None = None
    ejecutivo_apellidos: str | None = None
    ejecutivo_correo: str | None = None
    ejecutivo_telefono: str | None = None
    ejecutivo_completo: str | None = None
    jornadas: list[JornadaOut] = []


class ServicioOut(Base):
    id: int
    folio: str
    # Cuando el consultor dio por cerrada la asignacion, si ya lo hizo.
    asignacion_confirmada_en: datetime | None = None
    cliente_id: int
    pais_id: int
    plaza_id: int
    tipo: TipoServicio
    estatus: EstatusServicio
    consultor_id: int | None
    solicitante_id: int | None
    solicitante_nombre: str | None
    solicitante_apellidos: str | None
    # El nombre completo lo arma el modelo: la pantalla no vuelve a pegarlo.
    solicitante_completo: str | None = None
    ejecutivo_nombre: str | None
    ejecutivo_apellidos: str | None
    ejecutivo_completo: str | None = None
    ejecutivo_telefono: str | None
    vestimenta: CodigoVestimenta | None = None
    servicio_origen_id: int | None
    equipos: list[EquipoOut] = []


class DiaIn(Base):
    """Un dia que se agrega o se corrige con el servicio ya dado de alta."""
    fecha: date | None = None
    modalidad_id: int | None = None
    hora_presentacion: time | None = None
    km_estimados: int | None = None
    es_foraneo: bool | None = None


class CancelarIn(Base):
    """Cancelar si pide motivo: es lo que el cliente va a preguntar."""
    motivo: str


class EliminarIn(Base):
    """Por que se borra. Se guarda aunque el servicio ya no exista."""
    motivo: str | None = None


class AsignarPersonalIn(Base):
    persona_id: int
    # Con que rol va. El personal de seguridad es general: el mismo
    # agente que hoy conduce manana coordina, y de este rol salen el
    # precio al cliente y la comision que se le paga.
    rol_id: int | None = None
    forzar: bool = False          # el consultor decide ante una alerta de riesgo


class AbordoIn(Base):
    """En que unidad va una persona del equipo. Nulo la desliga."""
    vehiculo_id: int | None = None


class AsignarVehiculoIn(Base):
    vehiculo_id: int
    forzar: bool = False


# ================================================================ VIATICOS
from app.models import (  # noqa: E402
    EstatusTransferencia, EstatusViatico, OrigenMonto, TipoComprobante,
)


class ParametroCombustibleIn(Base):
    pais_id: int
    precio_litro: Decimal
    holgura_pct: Decimal = Decimal("20")
    vigencia_desde: date


class ParametroCombustibleOut(ParametroCombustibleIn):
    id: int
    activo: bool


class ConceptoIn(Base):
    concepto: ConceptoViatico
    monto: Decimal
    descripcion: str | None = None
    origen: OrigenMonto = OrigenMonto.TABULADOR


class AsignarViaticoIn(Base):
    jornada_id: int
    persona_id: int
    conceptos: list[ConceptoIn]
    # Quien autoriza NO viene en el cuerpo: sale de la sesion. Venia de
    # aqui, nadie lo mandaba nunca, y por eso finanzas no sabia a quien
    # preguntarle por un gasto. Y aunque alguien lo hubiera mandado,
    # seria el cliente diciendo quien autorizo, que es peor que no
    # saberlo.


class ConceptoOut(Base):
    id: int
    concepto: ConceptoViatico
    monto: Decimal
    descripcion: str | None
    origen: OrigenMonto
    es_adicional: bool


class ComprobanteIn(Base):
    concepto: ConceptoViatico
    tipo: TipoComprobante
    monto: Decimal
    archivo_url: str | None = None
    descripcion: str | None = None


class RechazoDevolucionIn(Base):
    """Por que no se acepto.

    Se exige: una devolucion rechazada sin motivo deja a la persona sin
    saber que arreglar, y a quien la revise en dos meses sin saber que
    paso.
    """
    motivo: str = Field(min_length=5, max_length=300)


class ComprobanteOut(ComprobanteIn):
    id: int
    validado: bool
    rechazado: bool = False
    motivo_rechazo: str | None = None
    observacion: str | None


class ViaticoOut(Base):
    id: int
    jornada_id: int
    persona_id: int
    escenario: EscenarioViatico
    monto_total: Decimal
    monto_comprobado: Decimal
    monto_devuelto: Decimal
    moneda: Moneda
    estatus: EstatusViatico
    limite_comprobacion: datetime | None
    cerrado_con_descuento: bool = False
    monto_descontado: Decimal = Decimal("0")
    monto_absorbido: Decimal = Decimal("0")
    motivo_cierre: str | None = None
    conceptos: list[ConceptoOut] = []
    comprobantes: list[ComprobanteOut] = []


class AdicionalIn(Base):
    concepto: ConceptoViatico
    monto: Decimal
    descripcion: str | None = None


# ------------------------------------------- viaticos por equipo

class ViaticoDeEquipoIn(Base):
    """Lo que el consultor decide depositarle a una persona por todo su
    paso por el equipo. Un solo numero: es un solo deposito."""
    persona_id: int
    monto: Decimal = Field(ge=0)


class SolicitarDepositoIn(Base):
    """Sin persona, va por todo el equipo."""
    persona_id: int | None = None


class DepositoIn(Base):
    """Lo que confirma finanzas: un movimiento por persona."""
    equipo_id: int
    persona_id: int
    referencia: str | None = Field(default=None, max_length=80)


# ------------------------------------------- compras especiales

class CompraIn(Base):
    tipo: TipoCompra
    solicitud: str = Field(min_length=10, max_length=4000)
    monto_estimado: Decimal | None = None


class RespuestaCompraIn(Base):
    """Lo que contesta finanzas. El folio es lo que de verdad importa:
    es con lo que el equipo se presenta en el mostrador. La imagen de la
    compra se sube aparte, por su propio endpoint."""
    confirmacion: str | None = Field(default=None, max_length=200)
    monto_real: Decimal | None = None
    respuesta: str | None = Field(default=None, max_length=4000)


class CompraOut(Base):
    id: int
    equipo_id: int
    tipo: TipoCompra
    solicitud: str
    monto_estimado: Decimal | None
    monto_real: Decimal | None
    moneda: Moneda
    estatus: EstatusCompra
    confirmacion: str | None
    tiene_comprobante: bool = False
    respuesta: str | None
    solicitada_en: datetime | None
    atendida_en: datetime | None


class TransferenciaOut(Base):
    id: int
    asignacion_id: int
    monto: Decimal
    moneda: Moneda
    estatus: EstatusTransferencia
    lote: str | None
    referencia_odoo: str | None


# ================================================================ CICLO DIARIO
from app.models import TipoHito  # noqa: E402


class OrigenIn(Base):
    """El pin puede llegar despues que la direccion: en el alta el
    consultor escribe donde es, y las coordenadas de la geocerca se fijan
    antes de que el servicio entre a la ventana de dos horas.

    La geocerca se dibuja sobre ese mismo pin, no sobre otro punto."""
    origen_lat: Decimal | None = None
    origen_lon: Decimal | None = None
    geocerca_metros: int | None = None
    origen_direccion: str | None = None
    # Cuando se dice, el radio se ajusta solo: 2 km en aeropuerto, 500 m
    # en cualquier otro lado.
    origen_aeropuerto: bool | None = None
    # Lo que dijo Google del lugar elegido. Si se contradice con la
    # casilla, el sistema traba y pide confirmarlo a proposito.
    origen_google_aeropuerto: bool | None = None
    forzar_aeropuerto: bool = False


class VueloIn(Base):
    """Vuelo del ejecutivo para ese dia. Todo opcional: a veces solo se
    sabe la aerolinea y el numero, y la hora llega despues."""
    vuelo_aerolinea: str | None = None
    vuelo_numero: str | None = None
    vuelo_hora: datetime | None = None
    vuelo_origen: str | None = None
    vuelo_tipo: Literal["llegada", "salida"] | None = None

    _capturado = capturado("vuelo_aerolinea", "vuelo_origen")
    _clave = en_mayusculas("vuelo_numero")


class HitoIn(Base):
    tipo: TipoHito
    lat: Decimal | None = None
    lon: Decimal | None = None
    marcado_en: datetime | None = None
    nota: str | None = None


class AjusteHitoIn(Base):
    nuevo_momento: datetime
    justificacion: str


class CierreAManoIn(Base):
    """La central da fe de que ese dia se trabajo.

    Las horas son opcionales: si no se dicen, valen las programadas, que
    es lo que casi siempre paso. La justificacion no es opcional.
    """
    justificacion: str
    inicio_real: datetime | None = None
    fin_real: datetime | None = None


class HitoAManoIn(Base):
    """La central registra el contacto que nadie marco desde la app.

    Los tres campos se exigen. La hora, porque de ahi sale `inicio_real`
    y de `inicio_real` las horas que se le facturan al cliente: no puede
    valer una por omision. La persona, porque el meet and greet se le
    acredita a quien iba. Y el motivo, porque esto crea una marca que no
    ocurrio en la app y dentro de seis meses alguien va a querer saber
    quien la puso y por que.
    """
    tipo: Literal["llegada_origen", "contacto_ejecutivo"]
    persona_id: int
    momento: datetime
    justificacion: str = Field(min_length=5, max_length=400)


class ConfirmarAManoIn(Base):
    """La central registra que esa persona confirmo por telefono.

    La nota es opcional y corta: aqui no hay una hora que fije horas
    extra ni dinero que se mueva --lo unico que hay es la palabra de
    quien lo registro, y esa ya queda sellada con su nombre--. Pedir un
    motivo de cinco lineas para esto solo lograria que nadie lo use y
    que el renglon se quede rojo, que es justo lo que se quiere evitar.
    """
    persona_id: int
    nota: str | None = Field(default=None, max_length=200)


class PorTelefonoIn(Base):
    """La central hablo con el y dijo que ya va en camino.

    La nota es opcional y corta --"va en Periferico", "sale en diez"--
    porque lo que importa ya queda sellado sin escribir nada: quien lo
    registro y a que hora. Pedir un motivo largo para esto solo
    lograria que nadie lo use y que el renglon se quede rojo, que es lo
    que se quiere evitar.
    """
    persona_id: int
    nota: str | None = Field(default=None, max_length=200)


class NotaBitacoraIn(Base):
    """Lo que se supo, en las palabras de quien lo supo.

    Un minimo bajo a proposito: "ok" no es una nota, pero "llame a Juan"
    si. El tope de 600 caracteres es el de la tabla; lo que no cabe ahi
    son dos notas, y dos notas se leen mejor que un parrafo.
    """
    texto: str = Field(min_length=3, max_length=600)


class HoraDeManianaIn(Base):
    """A que hora arranca el dia siguiente, dicho al cerrar el de hoy."""
    hora: time
    nota: str | None = Field(default=None, max_length=600)


class ReabrirDiaIn(Base):
    justificacion: str




class DiaFestivoIn(Base):
    pais_id: int
    fecha: date
    nombre: str
    factor_comision: Decimal = Decimal("2")


class DiaFestivoOut(DiaFestivoIn):
    id: int
    activo: bool


# ================================================================ TASK SHEET

class HospitalIn(Base):
    pais_id: int
    nombre: str
    lat: Decimal
    lon: Decimal
    plaza_id: int | None = None
    direccion: str | None = None
    telefono: str | None = None
    nivel_atencion: NivelHospital | None = None


class HospitalOut(HospitalIn):
    id: int
    activo: bool


class HotelIn(Base):
    pais_id: int
    nombre: str
    plaza_id: int | None = None
    direccion: str | None = None
    telefono: str | None = None
    lat: Decimal | None = None
    lon: Decimal | None = None


class HotelOut(HotelIn):
    id: int
    activo: bool


class HospedajeIn(Base):
    servicio_id: int | None = None      # sale del equipo
    # Uno por equipo: cada equipo cuida a su ejecutivo principal y ese
    # ejecutivo duerme en un hotel.
    equipo_id: int | None = None
    # Opcionales: solo se capturan cuando la estancia cambia de hotel.
    desde: date | None = None
    hasta: date | None = None
    hotel_id: int | None = None
    nombre_libre: str | None = None
    direccion_libre: str | None = None
    telefono_libre: str | None = None
    # El pin del hotel, cuando viene de Google. Sirve para los hospitales
    # cercanos el dia que el hotel sea el punto de origen.
    hotel_lat: Decimal | None = None
    hotel_lon: Decimal | None = None
    habitacion: str | None = None
    notas: str | None = None

    _capturado = capturado("nombre_libre")


class HospedajeOut(HospedajeIn):
    id: int


class AgendaIn(Base):
    resumen: str | None = None
    puntos: str | None = None
    archivo_url: str | None = None


class ParadaEdicion(Base):
    """Lo que se puede corregir de una parada ya capturada."""
    hora: time | None = None
    lugar: str | None = None
    direccion: str | None = None
    notas: str | None = None

    _capturado = capturado("lugar")


class ParadaOut(Base):
    id: int
    hora: time | None = None
    lugar: str
    direccion: str | None = None
    notas: str | None = None


class PublicarTaskSheetIn(Base):
    motivo: str | None = None
    forzar: bool = False
    # Apagado por omision: publicar y avisarle al cliente son dos actos
    # distintos. Ver el docstring de tasksheet.publicar.
    avisar: bool = False


class SenalIn(Base):
    """La senal: un color de la paleta (con palabra encima o sin ella),
    una palabra sola, o una imagen."""
    texto: str | None = None
    imagen: str | None = None      # data URI o URL
    nota: str | None = None
    color: str | None = None       # clave de la paleta (app/senal.py)


# ================================================================ ODOO

class EmpleadoOdoo(Base):
    """Lo que Odoo manda de cada empleado. El correo es la llave."""
    correo: str
    nombre: str | None = None
    telefono: str | None = None
    foto_url: str | None = None


from app.models import MotivoCambio  # noqa: E402


class VehiculoOdoo(Base):
    """Lo que Odoo manda de cada unidad. La placa es la llave.

    La marca y el modelo entran por aqui --Suburban, Tahoe, Sprinter--
    porque la flota vive en Odoo: aqui no se capturan, se reciben.
    """
    placa: str
    marca_modelo: str | None = None
    color: str | None = None
    modelo_anio: int | None = None
    foto_url: str | None = None


class CapacitacionOdoo(Base):
    """Un certificado del personal, como lo manda Odoo.

    La llave es el correo mas el nombre del curso. `vigencia_hasta` es
    lo que decide si cuenta: una certificacion vencida no es una
    certificacion, y el dia que importa nadie va a revisar la fecha.
    """
    correo: str
    nombre: str
    institucion: str | None = None
    obtenida_en: date | None = None
    vigencia_hasta: date | None = None
    # Para retirar un curso. No se retira solo por dejar de mandarlo.
    activo: bool | None = None


class TallerOdoo(Base):
    """Una unidad fuera de circulacion, como la manda Odoo.

    La placa es la llave, igual que en la flota. hasta vacio quiere decir
    que sigue adentro: el correctivo casi nunca trae fecha de salida.
    """
    placa: str
    desde: date
    hasta: date | None = None
    tipo: MotivoCambio | None = None
    taller: str | None = None
    folio: str | None = None
    nota: str | None = None
    odoo_id: int | None = None


# ================================================================ CONTINGENCIA

from app.models import CanalAlerta, EstatusAlerta  # noqa: E402


class AlertaIn(Base):
    """Lo que manda la app o captura la central al recibir una llamada."""
    canal: CanalAlerta
    jornada_id: int | None = None
    servicio_id: int | None = None
    reporta_persona_id: int | None = None
    descripcion: str | None = None
    lat: Decimal | None = None
    lon: Decimal | None = None


class AlertaOut(Base):
    id: int
    canal: CanalAlerta
    estatus: EstatusAlerta
    jornada_id: int | None = None
    servicio_id: int | None = None
    reporta_persona_id: int | None = None
    descripcion: str | None = None
    lat: Decimal | None = None
    lon: Decimal | None = None
    reportada_en: datetime
    tomada_por_id: int | None = None
    tomada_en: datetime | None = None
    equipo_respuesta_enviado: bool
    resolucion: str | None = None
    # Si el consultor ya formalizo el cambio que esta alerta provoco. La
    # central estabiliza y el consultor formaliza; asi la central ve que
    # lo suyo ya siguio su camino, sin tener que llamar a preguntar.
    cambio: str | None = None


class TomarAlertaIn(Base):
    equipo_respuesta_enviado: bool = False
    nota: str | None = None


class CerrarAlertaIn(Base):
    resolucion: str


class ReemplazoPersonalIn(Base):
    desde_jornada_id: int
    sale_persona_id: int
    entra_persona_id: int
    motivo: str
    alerta_id: int | None = None
    # Por que cambio. Con nombre y no como texto libre porque de aqui
    # salen dos cuentas que la direccion va a pedir: cuanto ausentismo
    # hay y cuanto tiempo pasan las unidades en el taller.
    motivo_tipo: MotivoCambio | None = None
    # Hasta cuando dura. Vacio es "de ahi en adelante", que es como se
    # resuelve una contingencia. Lo planeado si tiene fin.
    hasta_jornada_id: int | None = None
    # La hora en que ocurrio el relevo, que es la que parte el dia y
    # reparte el pago. Vacia: el sistema propone la ultima marca de quien
    # sale. El consultor la manda cuando sabe que fue otra --un dia
    # estatico puede no tener marcas desde la manana--.
    relevado_en: datetime | None = None


class RegresoIn(Base):
    """El titular vuelve. No pide motivo: el motivo es el del cambio que
    cierra."""
    # El primer dia que vuelve a ser suyo.
    desde: date
    # Si el que cubria alcanzo a trabajar la manana de ese dia, la hora
    # en que lo relevaron. Vacia: el sistema propone su ultima marca.
    relevado_en: datetime | None = None


class ReemplazoVehiculoIn(Base):
    desde_jornada_id: int
    sale_vehiculo_id: int
    entra_vehiculo_id: int
    motivo: str
    alerta_id: int | None = None
    motivo_tipo: MotivoCambio | None = None
    hasta_jornada_id: int | None = None
    # La hora en que la unidad cambio de manos. De ella cuelga la
    # revision de entrega: quien la recibio y en que estado. Vacia es la
    # de ahora, que es lo normal cuando se captura en el momento.
    relevado_en: datetime | None = None


# ================================================================ NOMINA

class CalcularNominaIn(Base):
    pais_id: int
    # El lunes de la semana. Si no viene, el lunes de hoy.
    fecha_corte: date | None = None


class AjusteNominaIn(Base):
    persona_id: int
    pais_id: int
    monto: Decimal          # con signo: negativo es descuento
    motivo: str
    servicio_id: int | None = None
    jornada_id: int | None = None
    # De que es. Sin esto, un descuento por viaticos y una correccion
    # del pago del mismo dia compartian la llave (jornada, persona) y se
    # tapaban uno al otro: el descuento hacia que la correccion nunca se
    # generara. Lo que captura finanzas a mano es "manual".
    concepto: Literal["correccion_jornada", "viatico_no_comprobado",
                      "manual"] = "manual"


class CierreConDescuentoIn(Base):
    """Cierre forzado del consultor cuando el conductor no pudo resolver."""
    motivo: str
    # Por omision se descuenta todo lo que quedo sin cubrir.
    monto_descuento: Decimal | None = None
    motivo_absorcion: str | None = None


# ================================================================ ENCUESTAS

class RespuestaEncuestaIn(Base):
    """La calificacion general y las respuestas de la rama que toque.

    Los valores de escala van como entero; los abiertos, como texto.
    """
    calificacion: int
    respuestas: dict[str, int | str] = {}


class ClasificarEncuestaIn(Base):
    nota: str
    incidencia_id: int | None = None


class PesosProfesionalismoIn(Base):
    """Los cinco pesos, que tienen que sumar 100."""
    pais_id: int
    pesos: dict[str, Decimal]
    meses_ventana: int | None = None
    horas_referencia: int | None = None
    castigo_error_menor: Decimal | None = None
    castigo_leve: Decimal | None = None
    castigo_grave: Decimal | None = None

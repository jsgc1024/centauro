"""Servicios implantados: contrato mensual, calendario, dias adicionales
y reemplazos de personal."""
import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auditoria, auth
from app import bolson
from app import desglose
from app import disponibilidad as disp
from app import cierre_mes
from app import comisiones
from app import reloj
from app import implantado as motor
from app import tasksheet
from app import viaticos_implantado as viaticos
from app import models as m
from app.db import get_db
from app.routers.servicios import siguiente_folio

router = APIRouter(prefix="/implantados", tags=["Implantados"])

CONSULTOR = auth.puede("implantado.armar")
TABULADOR = auth.puede("implantado.tabulador")
DINERO = auth.puede("implantado.viaticos")
LECTURA = auth.puede("implantado.ver")


class ContratoIn(BaseModel):
    servicio_id: int
    anio: int
    mes: int
    modalidad_id: int
    esquema: m.EsquemaCotizacionImplantado = m.EsquemaCotizacionImplantado.POR_DIA
    incluye_fines_de_semana: bool = False
    dias_servicio: m.DiasServicio | None = None
    hora_presentacion: str = "08:00:00"
    titular_id: int | None = None
    titular_rotacion_id: int | None = None
    vehiculo_id: int | None = None
    precio_mes_vehiculo: Decimal | None = None
    precio_dia_personal: Decimal | None = None
    precio_dia_adicional: Decimal | None = None
    precio_mes_completo: Decimal | None = None
    # Como se cobran los gastos (seccion 59): a precio alzado con su monto
    # fijo del mes, o netos, por lo comprobado.
    viaticos_incluidos: bool = True
    gastos_mes: Decimal | None = None
    # La hora extra del mes, aparte del esquema (seccion 65).
    precio_hora_extra: Decimal | None = None


class DiaAdicionalIn(BaseModel):
    fecha: date


@router.get("/calendario/{anio}/{mes}",
            summary="Dias habiles y fines de semana del mes")
def calendario(anio: int, mes: int, _=Depends(LECTURA)):
    """Sirve para cotizar: el mes puede tener mas o menos de 22 dias habiles."""
    return {"periodo": f"{mes:02d}/{anio}", **motor.resumen_calendario(anio, mes)}


@router.post("/contratos", status_code=201, summary="Alta del contrato mensual")
def crear_contrato(datos: ContratoIn, db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(CONSULTOR)):
    servicio = db.get(m.Servicio, datos.servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {datos.servicio_id}")
    if servicio.tipo != m.TipoServicio.IMPLANTADO:
        raise HTTPException(400, "El servicio no es de tipo implantado")

    existente = (db.query(m.ContratoImplantado)
                 .filter_by(servicio_id=datos.servicio_id, anio=datos.anio,
                            mes=datos.mes).first())
    if existente:
        raise HTTPException(409, f"Ya hay contrato para {datos.mes:02d}/{datos.anio}")

    # Esta puerta se abrio antes que el esquema de dias y sigue mandando
    # el si/no de fines de semana. Se traduce; si ademas viene el
    # esquema, manda el esquema, que dice mas.
    campos = datos.model_dump()
    esquema_dias = campos.pop("dias_servicio", None) or (
        m.DiasServicio.TODOS if datos.incluye_fines_de_semana
        else m.DiasServicio.LUNES_VIERNES)
    # Y del acuerdo sale la escala: en 12x36 el mes va entero, asi que
    # los dias base son todos los del mes y no solo los habiles.
    acuerdo_previo = (db.query(m.AcuerdoImplantado)
                      .filter_by(servicio_id=datos.servicio_id).first())
    turno_previo = (acuerdo_previo.turno if acuerdo_previo
                    and acuerdo_previo.turno else motor.TURNO_NATURAL)
    contrato = m.ContratoImplantado(
        **campos, dias_servicio=esquema_dias,
        # La base sale del calendario del mes, no de un numero fijo.
        dias_base=len(motor.dias_del_mes(datos.anio, datos.mes, esquema_dias,
                                         None, turno_previo)))
    db.add(contrato)
    auditoria.registrar(db, usuario, servicio, "alta contrato implantado",
                        f"{datos.mes:02d}/{datos.anio}")
    db.commit()
    db.refresh(contrato)
    return {"contrato_id": contrato.id, "periodo": f"{contrato.mes:02d}/{contrato.anio}",
            "esquema": contrato.esquema.value,
            "dias_base_del_mes": contrato.dias_base}


@router.post("/contratos/{contrato_id}/generar-mes",
             summary="Crear las jornadas del mes y asignar los recursos fijos")
def generar(contrato_id: int, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(CONSULTOR)):
    resultado = motor.generar_mes(db, contrato_id)
    contrato = db.get(m.ContratoImplantado, contrato_id)
    auditoria.registrar(db, usuario, contrato.servicio, "generar mes implantado",
                        f"{resultado['jornadas_creadas']} jornadas")
    db.commit()
    return resultado


@router.post("/contratos/{contrato_id}/dias-adicionales",
             summary="El usuario pide un dia extra")
def dia_adicional(contrato_id: int, datos: DiaAdicionalIn,
                  db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(CONSULTOR)):
    resultado = motor.agregar_dia(db, contrato_id, datos.fecha)
    contrato = db.get(m.ContratoImplantado, contrato_id)
    auditoria.registrar(db, usuario, contrato.servicio, "dia adicional",
                        f"{datos.fecha} con costo extra",
                        jornada_id=resultado["jornada_id"])
    db.commit()
    return resultado


@router.get("/contratos/{contrato_id}/resumen",
            summary="Resumen del mes para facturar")
def resumen(contrato_id: int, db: Session = Depends(get_db), _=Depends(LECTURA)):
    return motor.resumen_mensual(db, contrato_id)


@router.get("/contratos/{contrato_id}/cierre",
            summary="Que dias se trabajaron y quien los trabajo")
def cierre(contrato_id: int, db: Session = Depends(get_db), _=Depends(LECTURA)):
    """El papel del corte del mes.

    De un lado los dias de actividad que se le cobran al cliente, con su
    fecha; del otro los dias que cubrio cada persona, para su comision.
    Las dos listas salen de las mismas jornadas: asi cuadran.
    """
    return motor.cierre_del_mes(db, contrato_id)


@router.get("/contratos/{contrato_id}/cierre/estado",
            summary="El reloj del cierre del mes")
def estado_del_cierre(contrato_id: int, db: Session = Depends(get_db),
                      ahora: datetime | None = None,
                      usuario: m.Usuario = Depends(LECTURA)):
    """En que fase va el mes --comprobacion, sin visto bueno, en
    facturacion-- con sus relojes (seccion 56). El visto bueno y la
    aprobacion del mes van por las mismas rutas del cierre: `/cierre/
    {cierre_id}/enviar-finanzas` y `/cierre/{cierre_id}/aprobar`."""
    return comisiones.solo_la_suya(cierre_mes.estado(
        db, cierre_mes.contrato_o_404(db, contrato_id), ahora), usuario)


@router.get("/contratos/{contrato_id}/cierre/revision",
            summary="Revision del mes antes del visto bueno")
def revision_del_mes(contrato_id: int, db: Session = Depends(get_db),
                     ahora: datetime | None = None,
                     usuario: m.Usuario = Depends(LECTURA)):
    """Lo que el consultor tiene que resolver antes del visto bueno del
    mes: el comparativo contra el contrato, el dinero y las marcas."""
    return comisiones.solo_la_suya(cierre_mes.revisar(
        db, cierre_mes.contrato_o_404(db, contrato_id), ahora), usuario)


@router.get("/contratos/{contrato_id}/cierre/viaticos",
            summary="El dinero del personal del mes, persona por persona")
def viaticos_del_mes(contrato_id: int, db: Session = Depends(get_db),
                     _=Depends(auth.puede("viaticos.ver"))):
    """La misma revision que la del eventual, con el dinero del mes."""
    contrato = cierre_mes.contrato_o_404(db, contrato_id)
    ahora = reloj.ahora_del_servicio(db, contrato.servicio)
    viaticos = cierre_mes.viaticos_del_mes(db, contrato)
    # Con la gasolina del mes contra los kilometros del mes (seccion 60).
    from app import gps
    return {"momento": ahora.isoformat(), "periodo": cierre_mes.periodo(contrato),
            "personas": gps.con_gasolina(
                db, bolson.revision(viaticos, ahora), viaticos)}


@router.get("/contratos/{contrato_id}/desglose-gastos",
            response_class=HTMLResponse,
            summary="El desglose de gastos del mes para el cliente")
def desglose_del_mes(contrato_id: int, idioma: str | None = None,
                     db: Session = Depends(get_db),
                     _=Depends(auth.puede("cierre.ver"))):
    """Lo comprobado valido del mes, gasto por gasto, con sus
    comprobantes y en el idioma del cliente (seccion 59)."""
    contrato = cierre_mes.contrato_o_404(db, contrato_id)
    servicio = contrato.servicio
    cierre = cierre_mes.cierre_de(db, contrato)
    plaza = db.get(m.Plaza, servicio.plaza_id)
    pais = db.get(m.Pais, servicio.pais_id)
    return HTMLResponse(desglose.render(
        servicio, plaza.nombre if plaza else None,
        cierre_mes.viaticos_del_mes(db, contrato),
        idioma if idioma in desglose.TEXTOS
        else desglose.idioma_del_cliente(db, servicio),
        pais.moneda_local.value if pais else None,
        factura=cierre.factura_odoo if cierre else None,
        periodo=(contrato.anio, contrato.mes)))


class TerminosDelMesIn(BaseModel):
    """Como se cobra el mes. Lo que no venga se queda vacio: la pantalla
    manda los terminos completos."""
    esquema: m.EsquemaCotizacionImplantado
    precio_dia_personal: Decimal | None = Field(default=None, ge=0)
    precio_dia_adicional: Decimal | None = Field(default=None, ge=0)
    precio_mes_vehiculo: Decimal | None = Field(default=None, ge=0)
    precio_mes_completo: Decimal | None = Field(default=None, ge=0)
    # Seccion 59: verdadero, a precio alzado con su monto fijo del mes;
    # falso, gastos netos con desglose al final.
    viaticos_incluidos: bool = True
    gastos_mes: Decimal | None = Field(default=None, ge=0)
    # Seccion 65: cada hora extra del mes, en los dos esquemas.
    precio_hora_extra: Decimal | None = Field(default=None, ge=0)


def _terminos(db: Session, contrato: m.ContratoImplantado) -> dict:
    pais = db.get(m.Pais, contrato.servicio.pais_id)
    return {
        "contrato_id": contrato.id,
        "periodo": cierre_mes.periodo(contrato),
        "anio": contrato.anio, "mes": contrato.mes,
        "esquema": contrato.esquema.value,
        "precio_dia_personal": contrato.precio_dia_personal,
        "precio_dia_adicional": contrato.precio_dia_adicional,
        "precio_mes_vehiculo": contrato.precio_mes_vehiculo,
        "precio_mes_completo": contrato.precio_mes_completo,
        "viaticos_incluidos": contrato.viaticos_incluidos,
        "modo_gastos": ("precio_alzado" if contrato.viaticos_incluidos
                        else "netos"),
        "gastos_mes": contrato.gastos_mes,
        "precio_hora_extra": contrato.precio_hora_extra,
        "moneda": pais.moneda_local.value if pais else None,
        # Con el visto bueno dado ya no se cambian: la factura del mes
        # salio, o esta por salir, con estos precios.
        "editable": not cierre_mes.con_visto_bueno(db, contrato),
    }


@router.get("/contratos/{contrato_id}/terminos",
            summary="Como se cobra el mes")
def ver_terminos(contrato_id: int, db: Session = Depends(get_db),
                 _=Depends(LECTURA)):
    return _terminos(db, cierre_mes.contrato_o_404(db, contrato_id))


@router.put("/contratos/{contrato_id}/terminos",
            summary="Corregir como se cobra el mes")
def guardar_terminos(contrato_id: int, datos: TerminosDelMesIn,
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(CONSULTOR)):
    """Los precios del mes y el trato de sus gastos. Hasta hoy solo se
    capturaban al abrir el primer mes, y sin ellos el visto bueno de un
    mes cobrado por dia nunca pasaba (seccion 59). Pasan solos al mes
    siguiente; con el visto bueno del mes dado ya no se tocan."""
    contrato = cierre_mes.contrato_o_404(db, contrato_id)
    if cierre_mes.con_visto_bueno(db, contrato):
        raise HTTPException(409, {
            "mensaje": (f"El mes {cierre_mes.periodo(contrato)} ya tiene "
                        "visto bueno: sus terminos ya no se cambian"),
            "que_hacer": ("La factura del mes salio con estos precios. Si "
                          "hay que corregirla, finanzas lo regresa.")})
    antes = _terminos(db, contrato)
    for campo, valor in datos.model_dump().items():
        setattr(contrato, campo, valor)
    db.flush()
    despues = _terminos(db, contrato)
    cambios = [f"{k}: {antes[k]} -> {despues[k]}"
               for k in ("esquema", "precio_dia_personal",
                         "precio_dia_adicional", "precio_mes_vehiculo",
                         "precio_mes_completo", "modo_gastos", "gastos_mes",
                         "precio_hora_extra")
               if str(antes[k]) != str(despues[k])]
    if cambios:
        auditoria.registrar(db, usuario, contrato.servicio,
                            "terminos del mes",
                            (f"{cierre_mes.periodo(contrato)}: "
                             + "; ".join(cambios))[:400])
    db.commit()
    db.refresh(contrato)
    return _terminos(db, contrato)


@router.get("/contratos", summary="Contratos implantados")
def listar(db: Session = Depends(get_db), anio: int | None = None,
           mes: int | None = None, _=Depends(LECTURA)):
    consulta = db.query(m.ContratoImplantado)
    if anio:
        consulta = consulta.filter_by(anio=anio)
    if mes:
        consulta = consulta.filter_by(mes=mes)
    return [{"id": c.id, "servicio": c.servicio.folio,
             "periodo": f"{c.mes:02d}/{c.anio}", "esquema": c.esquema.value,
             "titular": c.titular.nombre if c.titular else None,
             "generado": c.generado} for c in consulta.all()]


# ==================================================== el implantado entero

# Un implantado no se da de alta como un eventual. El eventual se captura
# por dias; el implantado se captura una vez —el trato— y de ahi cada mes
# se abre solo. Por eso el alta crea las tres cosas de un golpe: el
# servicio, el acuerdo que no cambia, y el primer mes.

class AcuerdoIn(BaseModel):
    cubre: str | None = None
    no_cubre: str | None = None
    zona_operacion: str | None = None
    dias_semana: str | None = None
    fecha_inicio: date | None = None
    dias_servicio: m.DiasServicio | None = None
    # "natural" --una persona, doce horas corridas-- o "12x36" --dos
    # personas alternando, los siete dias--. Ver AcuerdoImplantado.turno.
    turno: Literal["natural", "12x36"] = "natural"
    origen_direccion: str | None = None
    origen_lat: Decimal | None = None
    origen_lon: Decimal | None = None
    geocerca_metros: int = 500
    reporta_a_nombre: str | None = None
    reporta_a_apellidos: str | None = None
    reporta_a_telefono: str | None = None
    reporta_a_correo: str | None = None
    protocolo_contacto: str | None = None


class EnPlantillaIn(BaseModel):
    """Quien va, con que rol y en que unidad.

    El rol es de la tarea, no de la persona: el mismo agente que hoy
    conduce manana coordina, y de ese rol salen el precio al cliente y
    la comision que se le paga.

    La unidad es la que lleva esa persona: la maneja si va de conductor,
    y si el servicio es de un agente solo, la maneja el agente.
    """
    persona_id: int
    rol_id: int | None = None
    vehiculo_id: int | None = None
    # Solo en 12x36: cual de las dos entra el primer dia. Ver
    # PersonaImplantado.empieza.
    empieza: bool = False


class PlantillaIn(BaseModel):
    personal: list[EnPlantillaIn] = []
    unidades: list[int] = []


class ServicioImplantadoIn(BaseModel):
    """Cliente, contacto y trato. La primera mitad del alta.

    Se guarda sola, en cuanto esta completa. Capturar el trato de un
    implantado toma su tiempo —el alcance, la coordinacion, el
    protocolo— y perderlo porque la plantilla del mes no cuadraba es la
    forma mas facil de que nadie quiera volver a capturar uno.
    """
    cliente_id: int
    pais_id: int
    plaza_id: int
    solicitante_id: int | None = None
    solicitante_nombre: str | None = None
    solicitante_apellidos: str | None = None
    solicitante_correo: str | None = None
    solicitante_telefono: str | None = None
    ejecutivo_nombre: str | None = None
    ejecutivo_apellidos: str | None = None
    ejecutivo_correo: str | None = None
    ejecutivo_telefono: str | None = None
    # En que idioma lee cada uno. Misma regla que el eventual: el
    # principal arranca en ingles y el solicitante, vacio, lee en el
    # idioma de su pais. Ver models.Servicio.
    idioma_ejecutivo: str = "en"
    idioma_solicitante: str | None = None
    consultor_id: int | None = None
    acuerdo: AcuerdoIn = AcuerdoIn()


class MesImplantadoIn(BaseModel):
    """La segunda mitad: el mes, la plantilla y lo que se cobra.

    La fecha y los dias pueden venir vacios: se toman del acuerdo, donde
    quedaron al capturarlo.
    """
    fecha_inicio: date | None = None
    dias_servicio: m.DiasServicio | None = None
    dias_cubiertos: list[date] = []
    modalidad_id: int
    hora_presentacion: str = "08:00:00"
    esquema: m.EsquemaCotizacionImplantado = m.EsquemaCotizacionImplantado.POR_DIA
    personal: list[EnPlantillaIn] = []
    unidades: list[int] = []
    precio_mes_vehiculo: Decimal | None = None
    precio_dia_personal: Decimal | None = None
    precio_dia_adicional: Decimal | None = None
    precio_mes_completo: Decimal | None = None
    # Como se cobran los gastos (seccion 59): a precio alzado con su monto
    # fijo del mes, o netos, por lo comprobado.
    viaticos_incluidos: bool = True
    gastos_mes: Decimal | None = None
    # La hora extra del mes, aparte del esquema (seccion 65).
    precio_hora_extra: Decimal | None = None


class AltaImplantadoIn(BaseModel):
    """El alta arranca igual que la del eventual y termina distinto."""
    cliente_id: int
    pais_id: int
    plaza_id: int
    solicitante_id: int | None = None
    solicitante_nombre: str | None = None
    solicitante_apellidos: str | None = None
    solicitante_correo: str | None = None
    solicitante_telefono: str | None = None
    ejecutivo_nombre: str | None = None
    ejecutivo_apellidos: str | None = None
    ejecutivo_correo: str | None = None
    ejecutivo_telefono: str | None = None
    # En que idioma lee cada uno. Misma regla que el eventual: el
    # principal arranca en ingles y el solicitante, vacio, lee en el
    # idioma de su pais. Ver models.Servicio.
    idioma_ejecutivo: str = "en"
    idioma_solicitante: str | None = None
    consultor_id: int | None = None

    # El servicio arranca el dia del meet and greet y corre hasta el
    # ultimo dia del mes: ahi cae el corte y el mes siguiente entra
    # limpio el dia 1. De esta fecha salen el anio, el mes y el dia en
    # que empieza; no se preguntan tres veces lo mismo.
    fecha_inicio: date
    dias_servicio: m.DiasServicio = m.DiasServicio.LUNES_VIERNES
    # Los dias que el consultor abrio desde el calendario del alta: el
    # fin de semana contratado que ya se sabe quien cubre, y el dia
    # suelto que el cliente pidio fuera del esquema —una cena el sabado
    # cuando el servicio es de lunes a viernes—. Los cubre el mismo
    # equipo, que es lo que pasa casi siempre.
    dias_cubiertos: list[date] = []
    modalidad_id: int
    hora_presentacion: str = "08:00:00"
    esquema: m.EsquemaCotizacionImplantado = m.EsquemaCotizacionImplantado.POR_DIA
    # La plantilla del mes: cualquier combinacion, siempre con al menos
    # un conductor de seguridad y toda unidad con el suyo.
    personal: list[EnPlantillaIn] = []
    unidades: list[int] = []
    precio_mes_vehiculo: Decimal | None = None
    precio_dia_personal: Decimal | None = None
    precio_dia_adicional: Decimal | None = None
    precio_mes_completo: Decimal | None = None
    # Como se cobran los gastos, la misma opcion que la cotizacion del
    # eventual (seccion 59): a precio alzado con su monto fijo del mes, o
    # netos, por lo comprobado.
    viaticos_incluidos: bool = True
    gastos_mes: Decimal | None = None
    # La hora extra del mes, aparte del esquema (seccion 65).
    precio_hora_extra: Decimal | None = None

    acuerdo: AcuerdoIn = AcuerdoIn()



class CambioRecursoIn(BaseModel):
    """El titular se va de vacaciones o la unidad entra al taller."""
    tipo: m.TipoRecurso
    desde: date
    hasta: date | None = None       # vacio: de ese dia en adelante
    entra_id: int
    # Sin nombre no hay cambio. Antes, vacio queria decir "el primero de
    # la lista de ese dia": en una plantilla de tres eso cambiaba al que
    # no era, y el fin de semana, cuando la plantilla rota, a cualquiera.
    sale_id: int
    motivo: m.MotivoCambio
    nota: str | None = None
    # La hora que parte el dia. Vacia: la ultima marca de quien sale.
    # El consultor la corrige cuando sabe que fue otra.
    relevado_en: datetime | None = None


class DiaFinDeSemanaIn(BaseModel):
    fecha: date
    persona_id: int | None = None   # vacio: el titular del contrato


def _servicio_implantado(db: Session, servicio_id: int) -> m.Servicio:
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    if servicio.tipo != m.TipoServicio.IMPLANTADO:
        raise HTTPException(400, "Ese servicio no es implantado")
    return servicio


def _contrato_del_mes(db: Session, servicio_id: int, anio: int, mes: int):
    return (db.query(m.ContratoImplantado)
            .filter_by(servicio_id=servicio_id, anio=anio, mes=mes).first())


def _idioma_del_pais(db: Session, pais_id: int) -> str:
    pais = db.get(m.Pais, pais_id)
    return pais.idioma if pais else "es"


def _guardar_servicio(db: Session, usuario: m.Usuario, datos) -> m.Servicio:
    """Crea el servicio y su acuerdo. No abre ningun mes todavia."""
    if not db.get(m.Cliente, datos.cliente_id):
        raise HTTPException(404, f"No existe el cliente {datos.cliente_id}")

    servicio = m.Servicio(
        folio="",           # se arma con el consecutivo, ya con id asignado
        cliente_id=datos.cliente_id, pais_id=datos.pais_id,
        plaza_id=datos.plaza_id, tipo=m.TipoServicio.IMPLANTADO,
        solicitante_id=datos.solicitante_id,
        solicitante_nombre=datos.solicitante_nombre,
        solicitante_apellidos=datos.solicitante_apellidos,
        solicitante_correo=datos.solicitante_correo,
        solicitante_telefono=datos.solicitante_telefono,
        ejecutivo_nombre=datos.ejecutivo_nombre,
        ejecutivo_apellidos=datos.ejecutivo_apellidos,
        ejecutivo_correo=datos.ejecutivo_correo,
        ejecutivo_telefono=datos.ejecutivo_telefono,
        idioma_ejecutivo=datos.idioma_ejecutivo or "en",
        # Vacio: el idioma del pais donde se ejecuta. Quien pide un
        # implantado casi siempre es del cliente, en el pais.
        idioma_solicitante=(datos.idioma_solicitante
                            or _idioma_del_pais(db, datos.pais_id)),
        consultor_id=datos.consultor_id or usuario.persona_id,
        # Con el acuerdo capturado el servicio ya esta pedido, no en
        # borrador: hay un compromiso con el cliente esperando gente.
        estatus=m.EstatusServicio.SOLICITADO)
    db.add(servicio)
    db.flush()
    servicio.folio = siguiente_folio(db, m.TipoServicio.IMPLANTADO)

    db.add(m.AcuerdoImplantado(servicio_id=servicio.id,
                               **datos.acuerdo.model_dump()))
    auditoria.registrar(db, usuario, servicio, "alta implantado",
                        "cliente y trato")
    db.flush()
    return servicio


@router.post("/servicio", status_code=201,
             summary="Guardar el cliente y el trato del implantado")
def alta_servicio(datos: ServicioImplantadoIn, db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(CONSULTOR)):
    """La primera mitad del alta, que se guarda sola.

    De aqui sale el folio. El servicio queda en borrador hasta que se le
    abra el primer mes: existe, se ve en la cartera y se puede seguir
    capturando manana.
    """
    servicio = _guardar_servicio(db, usuario, datos)
    db.commit()
    db.refresh(servicio)
    return {"servicio_id": servicio.id, "folio": servicio.folio,
            "estatus": servicio.estatus.value}


def _abrir_mes(db: Session, usuario: m.Usuario, servicio: m.Servicio,
               datos) -> dict:
    """El primer mes del servicio: contrato, plantilla y calendario."""
    if not db.get(m.Modalidad, datos.modalidad_id):
        raise HTTPException(404, f"No existe la modalidad {datos.modalidad_id}")

    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())
    inicio = datos.fecha_inicio or (acuerdo.fecha_inicio if acuerdo else None)
    if not inicio:
        raise HTTPException(409, {
            "mensaje": "El servicio no tiene dia de inicio",
            "que_hacer": "Se captura en el acuerdo, con el meet and greet."})
    dias_servicio = (datos.dias_servicio
                     or (acuerdo.dias_servicio if acuerdo else None)
                     or m.DiasServicio.LUNES_VIERNES)
    contrato = m.ContratoImplantado(
        servicio_id=servicio.id, anio=inicio.year, mes=inicio.month,
        desde_dia=inicio.day, modalidad_id=datos.modalidad_id,
        hora_presentacion=datos.hora_presentacion, esquema=datos.esquema,
        dias_servicio=dias_servicio,
        incluye_fines_de_semana=dias_servicio != m.DiasServicio.LUNES_VIERNES,
        precio_mes_vehiculo=datos.precio_mes_vehiculo,
        precio_dia_personal=datos.precio_dia_personal,
        precio_dia_adicional=datos.precio_dia_adicional,
        precio_mes_completo=datos.precio_mes_completo,
        viaticos_incluidos=datos.viaticos_incluidos,
        gastos_mes=datos.gastos_mes,
        precio_hora_extra=datos.precio_hora_extra,
        dias_base=len(motor.dias_del_mes(
            inicio.year, inicio.month, dias_servicio, inicio.day,
            (acuerdo.turno if acuerdo and acuerdo.turno
             else motor.TURNO_NATURAL))))
    db.add(contrato)
    auditoria.registrar(db, usuario, servicio, "primer mes implantado",
                        f"desde {inicio.isoformat()}")
    db.flush()

    # La plantilla se valida antes de generar el mes: mas vale trabar el
    # alta que generar veintidos dias con una unidad sin conductor.
    motor.guardar_plantilla(
        db, contrato,
        [(p.persona_id, p.vehiculo_id, p.rol_id, p.empieza)
         for p in datos.personal],
        datos.unidades)
    db.commit()
    db.refresh(contrato)

    generado = motor.generar_mes(db, contrato.id)

    # Los dias sueltos se abren despues de generar el mes: el fin de
    # semana contratado ya existe vacio y estos le ponen quien va, y el
    # dia fuera del esquema se crea aqui. Si uno ya quedo cubierto —el
    # sabado arrastra al domingo— se deja pasar en vez de reventar el
    # alta completa por un dia repetido.
    abiertos = []
    for dia in sorted(set(datos.dias_cubiertos)):
        if dia.year != inicio.year or dia.month != inicio.month:
            continue
        try:
            abiertos.append(motor.agregar_dia(db, contrato.id, dia))
        except HTTPException as error:
            if error.status_code != 409:
                raise
    generado["dias_abiertos"] = [a["fecha"] for a in abiertos]
    return generado


@router.post("/{servicio_id}/mes", status_code=201,
             summary="Abrir el primer mes de un implantado ya guardado")
def abrir_primer_mes(servicio_id: int, datos: MesImplantadoIn,
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(CONSULTOR)):
    """La segunda mitad del alta, sobre un servicio que ya existe."""
    servicio = _servicio_implantado(db, servicio_id)
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())
    inicio = datos.fecha_inicio or (acuerdo.fecha_inicio if acuerdo else None)
    if inicio and _contrato_del_mes(db, servicio.id, inicio.year, inicio.month):
        raise HTTPException(409, f"El mes {inicio.month:02d}/{inicio.year} "
                                 f"ya esta abierto")
    generado = _abrir_mes(db, usuario, servicio, datos)
    return {"servicio_id": servicio.id, "folio": servicio.folio, **generado}


@router.post("", status_code=201, summary="Dar de alta un implantado")
def alta(datos: AltaImplantadoIn, db: Session = Depends(get_db),
         usuario: m.Usuario = Depends(CONSULTOR)):
    """Las dos mitades de un golpe: servicio, acuerdo y primer mes."""
    servicio = _guardar_servicio(db, usuario, datos)
    generado = _abrir_mes(db, usuario, servicio, datos)
    # generado ya trae el contrato_id que armo el motor.
    return {"servicio_id": servicio.id, "folio": servicio.folio, **generado}


@router.get("/disponibilidad",
            summary="Quien y que unidad estan libres todo el mes")
def disponibilidad(plaza_id: int, desde: date, dias_servicio: m.DiasServicio,
                   hora: str = "08:00:00",
                   db: Session = Depends(get_db), _=Depends(LECTURA)):
    """La disponibilidad de un implantado no es la de un dia: es la del mes.

    Un eventual pregunta quien esta libre el martes. Un implantado
    pregunta quien esta libre los veintidos dias, porque es la misma
    persona todos los dias; alguien que trae otro servicio el dia 12 no
    sirve aunque este libre hoy.

    Por eso se cuenta dia por dia y se contesta con cuantos de los dias
    verdes del calendario puede cada quien, y en cuales choca. El
    consultor decide: veintidos de veintidos, o veinte y resolver dos.
    """
    plaza = db.get(m.Plaza, plaza_id)
    if not plaza:
        raise HTTPException(404, f"No existe la ciudad {plaza_id}")

    modalidad = (db.query(m.Modalidad)
                 .filter(m.Modalidad.pais_id == plaza.pais_id,
                         m.Modalidad.codigo == m.CodigoModalidad.FULL_DAY)
                 .first())
    if not modalidad:
        raise HTTPException(409, "Ese pais no tiene dia completo en el catalogo")

    dias = motor.dias_del_mes(desde.year, desde.month, dias_servicio, desde.day)
    # Los fines de semana se cubren aparte: la disponibilidad del mes se
    # mide contra los dias que corren de corrido.
    dias = [d for d in dias if d.weekday() < 5]
    if not dias:
        raise HTTPException(409, "Ese periodo no tiene dias de servicio")

    arranque = time.fromisoformat(hora)
    horas = float(modalidad.horas)
    ventanas = []
    for dia in dias:
        inicio = datetime.combine(dia, arranque)
        ventanas.append((dia, inicio, inicio + timedelta(hours=horas)))

    def contar(revisar, id_):
        """En cuantos dias cabe y en cuales choca."""
        choques = []
        for dia, inicio, fin in ventanas:
            hallazgos = revisar(db, id_, inicio, fin,
                                modalidad.bloquea_dia_completo)
            if any(x.nivel == "bloqueo" for x in hallazgos):
                choques.append(dia.isoformat())
        return choques

    gente = (db.query(m.Persona)
             .filter(m.Persona.plaza_id == plaza_id,
                     m.Persona.activo.is_(True),
                     # La oficina no entra a una plantilla (seccion 74).
                     m.Persona.oficina.is_(False)).all())
    personal = []
    for persona in gente:
        # Todo el personal de seguridad es candidato: el rol lo decide el
        # consultor al armar la plantilla, no el catalogo.
        choques = contar(disp.revisar_persona, persona.id)
        personal.append({
            "persona_id": persona.id, "nombre": persona.nombre,
            "libres": len(dias) - len(choques),
            "choques": choques,
        })
    personal.sort(key=lambda x: (-x["libres"], x["nombre"]))

    flota = (db.query(m.Vehiculo)
             .filter(m.Vehiculo.plaza_id == plaza_id,
                     m.Vehiculo.activo.is_(True),
                     m.Vehiculo.rentado.is_(False)).all())

    # El taller tambien ocupa la unidad, aunque no tenga servicio
    # asignado. Sin esto un coche desarmado le aparece libre a todos, y
    # asi es como se le promete al cliente un vehiculo que no existe.
    bloqueos = motor.taller_de(db, [v.id for v in flota])

    vehiculos = []
    for unidad in flota:
        choques = contar(disp.revisar_vehiculo, unidad.id)
        en_taller = [d.isoformat() for d in dias
                     if motor.en_taller(bloqueos.get(unidad.id), d)]
        fuera = sorted(set(choques) | set(en_taller))
        vehiculos.append({
            "vehiculo_id": unidad.id, "placa": unidad.placa,
            "categoria_id": unidad.categoria_id,
            "categoria": unidad.categoria.nombre if unidad.categoria else None,
            "marca_modelo": unidad.marca_modelo,
            "libres": len(dias) - len(fuera),
            "choques": fuera,
            "dias_en_taller": len(en_taller),
        })
    vehiculos.sort(key=lambda x: (-x["libres"], x["placa"]))

    return {"dias": len(dias),
            "desde": dias[0].isoformat(), "hasta": dias[-1].isoformat(),
            "personal": personal, "vehiculos": vehiculos}


@router.get("", summary="Cartera de implantados")
def cartera(db: Session = Depends(get_db), _=Depends(LECTURA)):
    """Uno por servicio, no uno por mes: el implantado es continuo."""
    servicios = (db.query(m.Servicio)
                 .filter(m.Servicio.tipo == m.TipoServicio.IMPLANTADO,
                         m.Servicio.estatus != m.EstatusServicio.CANCELADO)
                 .order_by(m.Servicio.id.desc()).all())
    # El servicio guarda el id de la ciudad, no la ciudad: se traen una
    # vez y se buscan aqui, en vez de una consulta por renglon.
    ciudades = {p.id: p.nombre for p in db.query(m.Plaza).all()}

    salida = []
    for s_ in servicios:
        meses = (db.query(m.ContratoImplantado)
                 .filter_by(servicio_id=s_.id)
                 .order_by(m.ContratoImplantado.anio.desc(),
                           m.ContratoImplantado.mes.desc()).all())
        ultimo = meses[0] if meses else None
        relojes = cierre_mes.relojes_de(db, meses)
        hoy = reloj.hoy_en(db.get(m.Pais, s_.pais_id))
        salida.append({
            "servicio_id": s_.id, "folio": s_.folio,
            "cliente": s_.cliente.nombre if s_.cliente else None,
            "ejecutivo": s_.ejecutivo_completo,
            "ciudad": ciudades.get(s_.plaza_id),
            "estatus": s_.estatus.value,
            "titular": ultimo.titular.nombre if ultimo and ultimo.titular else None,
            "unidad": ultimo.vehiculo.placa if ultimo and ultimo.vehiculo else None,
            "ultimo_mes": (f"{ultimo.mes:02d}/{ultimo.anio}" if ultimo else None),
            "meses": len(meses),
            # Los meses abiertos, del mas viejo al mas nuevo, y si se
            # puede abrir el que sigue. Con esto el panel pinta las
            # pestanas del mes y el boton, sin otra vuelta al servidor.
            "periodos": [{"anio": c.anio, "mes": c.mes,
                          "periodo": f"{c.mes:02d}/{c.anio}",
                          "contrato_id": c.id,
                          # En que va el cierre de cada mes; vacio
                          # mientras se trabaja (seccion 56). Con su
                          # reloj, si corre uno (seccion 59).
                          "fase": (relojes.get(c.id) or {}).get("fase"),
                          "reloj": (relojes.get(c.id) or {}).get("reloj"),
                          "sin_cierre": (None if c.id in relojes
                                         else _sin_cierre(db, c, hoy))}
                         for c in reversed(meses)],
            "siguiente": motor.estado_desde(ultimo, s_),
        })
    return salida


def _sin_cierre(db: Session, contrato: m.ContratoImplantado,
                hoy: date) -> str:
    """Como va un mes que todavia no tiene cierre.

    Por empezar, si es de despues; en curso, si es este. Uno que ya paso
    sin cierre tiene dias sin cerrar --su reloj no arranca hasta que se
    cierre su ultimo dia-- o no tuvo nada que cerrar.
    """
    clave, hoy_clave = contrato.anio * 100 + contrato.mes, hoy.year * 100 + hoy.month
    if clave > hoy_clave:
        return "por_empezar"
    if clave == hoy_clave:
        return "en_curso"
    pendientes = any(j.estatus not in (m.EstatusJornada.TERMINADA,
                                       m.EstatusJornada.CANCELADA)
                     for j in cierre_mes._dias(db, contrato))
    return "dias_sin_cerrar" if pendientes else "sin_nada"


def _contrato_vigente(db: Session, servicio_id: int):
    """El mes que manda hoy: el de este mes, y si no, el mas reciente."""
    hoy = date.today()
    delMes = _contrato_del_mes(db, servicio_id, hoy.year, hoy.month)
    if delMes:
        return delMes
    return (db.query(m.ContratoImplantado)
            .filter_by(servicio_id=servicio_id)
            .order_by(m.ContratoImplantado.anio.desc(),
                      m.ContratoImplantado.mes.desc())
            .first())


@router.get("/{servicio_id}/acuerdo", summary="El trato del implantado")
def ver_acuerdo(servicio_id: int, db: Session = Depends(get_db),
                _=Depends(LECTURA)):
    servicio = _servicio_implantado(db, servicio_id)
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())
    # La hora del encuentro vive en el contrato del mes, no en el
    # acuerdo. Viaja con el acuerdo porque es donde se lee y donde se
    # corrige: quien mira el trato quiere saber a que hora es.
    contrato = _contrato_vigente(db, servicio.id)
    delMes = {
        "hora_presentacion": contrato.hora_presentacion if contrato else None,
        "mes_anio": contrato.anio if contrato else None,
        "mes_mes": contrato.mes if contrato else None,
    }
    if not acuerdo:
        return {"servicio_id": servicio.id, **delMes}
    return {c.name: getattr(acuerdo, c.name)
            for c in acuerdo.__table__.columns} | delMes


class HoraDeEncuentroIn(BaseModel):
    """La hora del meet and greet de un mes ya abierto."""
    hora: str
    anio: int | None = None
    mes: int | None = None


@router.put("/{servicio_id}/hora-presentacion",
            summary="Cambiar la hora del meet and greet")
def cambiar_hora(servicio_id: int, datos: HoraDeEncuentroIn,
                 db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(CONSULTOR)):
    """Se captura al abrir el mes y no habia donde corregirla.

    Un cliente que mueve el encuentro media hora obligaba a reabrir el
    mes entero. Mueve los dias que todavia no arrancan; los que ya
    arrancaron se devuelven aparte, sin tocarlos.
    """
    servicio = _servicio_implantado(db, servicio_id)
    contrato = (_contrato_del_mes(db, servicio.id, datos.anio, datos.mes)
                if datos.anio and datos.mes
                else _contrato_vigente(db, servicio.id))
    if not contrato:
        raise HTTPException(409, {
            "mensaje": "Ese servicio no tiene ningun mes abierto",
            "que_hacer": "Abre el mes y ahi se captura la hora."})
    try:
        hecho = motor.cambiar_hora_presentacion(db, servicio, contrato,
                                                datos.hora)
    except ValueError:
        raise HTTPException(400, "Esa hora no se entiende. Usa 07:30:00.")
    auditoria.registrar(db, usuario, servicio, "hora de presentacion",
                        f"{datos.hora} · {len(hecho['dias_movidos'])} dia(s)")
    db.commit()
    return hecho


@router.put("/{servicio_id}/acuerdo", summary="Corregir el trato")
def guardar_acuerdo(servicio_id: int, datos: AcuerdoIn,
                    db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(CONSULTOR)):
    """El alcance se corrige sobre la marcha: el cliente pide algo nuevo
    y hay que decir si entra o no entra."""
    servicio = _servicio_implantado(db, servicio_id)
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())
    if not acuerdo:
        acuerdo = m.AcuerdoImplantado(servicio_id=servicio.id)
        db.add(acuerdo)
    antes = acuerdo.fecha_inicio
    for campo, valor in datos.model_dump().items():
        setattr(acuerdo, campo, valor)
    auditoria.registrar(db, usuario, servicio, "acuerdo implantado",
                        datos.zona_operacion or "alcance actualizado")
    db.commit()

    # Los dias del mes se generaron con el arranque viejo y siguen ahi.
    # No se borran solos --pueden traer gente confirmada y dinero
    # depositado-- pero se dicen, con nombre y fecha, para que el
    # consultor decida.
    fuera, contrato_ajustado, vuelven = [], None, []
    if acuerdo.fecha_inicio and acuerdo.fecha_inicio != antes:
        fuera = motor.dias_fuera_del_inicio(db, servicio,
                                            acuerdo.fecha_inicio)
        # Y la simetria: los que se habian cancelado y vuelven a caer
        # dentro del arranque. Se ofrecen, no se reviven solos.
        vuelven = motor.dias_cancelados_dentro(db, servicio,
                                               acuerdo.fecha_inicio)
        # El calendario se pinta desde el contrato, no desde las
        # jornadas: sin esto, los dias que se cierran siguen saliendo
        # verdes porque el contrato dice que ahi empieza el servicio. Y
        # de ese mismo campo salen los dias base del mes, que es lo que
        # se factura: se mueven juntos o el contrato miente por un lado.
        contrato = _contrato_del_mes(db, servicio.id,
                                     acuerdo.fecha_inicio.year,
                                     acuerdo.fecha_inicio.month)
        if contrato and contrato.desde_dia != acuerdo.fecha_inicio.day:
            base_antes = contrato.dias_base
            contrato.desde_dia = acuerdo.fecha_inicio.day
            contrato.dias_base = len(motor.dias_del_mes(
                contrato.anio, contrato.mes, contrato.dias_servicio,
                contrato.desde_dia,
                acuerdo.turno or motor.TURNO_NATURAL))
            auditoria.registrar(
                db, usuario, servicio, "arranque del mes",
                f"{contrato.mes:02d}/{contrato.anio} desde el dia "
                f"{contrato.desde_dia} · dias base {base_antes} -> "
                f"{contrato.dias_base}")
            db.commit()
            contrato_ajustado = {
                "periodo": f"{contrato.mes:02d}/{contrato.anio}",
                "desde_dia": contrato.desde_dia,
                "dias_base_antes": base_antes,
                "dias_base": contrato.dias_base,
            }

    # El acuerdo es la hoja maestra: el punto que se corrige aqui baja a
    # los dias que todavia no arrancan. Si no, la geocerca se queda en la
    # esquina vieja y el agente marca su llegada donde ya no es.
    bajados = motor.bajar_acuerdo_a_los_dias(db, servicio, acuerdo)
    if bajados:
        db.commit()
    # Y los que el contrato dice que existen y no estan: se borraron al
    # correr el arranque hacia adelante y la fecha nueva los reclama.
    faltantes = (motor.dias_que_faltan(db, servicio, acuerdo.fecha_inicio)
                 if acuerdo.fecha_inicio and acuerdo.fecha_inicio != antes
                 else [])
    return {"resultado": "acuerdo guardado", "servicio_id": servicio.id,
            "dias_fuera": fuera, "dias_actualizados": bajados,
            "dias_que_vuelven": vuelven, "dias_que_faltan": faltantes,
            "contrato_ajustado": contrato_ajustado}


@router.get("/{servicio_id}/mes/{anio}/{mes}",
            summary="El mes dia por dia: quien va y que cambio")
def panel_del_mes(servicio_id: int, anio: int, mes: int,
                  db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(LECTURA)):
    """Lo que el consultor mira todos los dias de un implantado.

    El eventual se arma y se ejecuta; el implantado ya esta armado y lo
    que cambia es la excepcion: quien falto, que fin de semana pidio el
    cliente, y como va el mes contra lo contratado.
    """
    servicio = _servicio_implantado(db, servicio_id)
    contrato = _contrato_del_mes(db, servicio.id, anio, mes)
    equipo = servicio.equipos[0] if servicio.equipos else None

    calendario = motor.resumen_calendario(anio, mes)
    dias = []
    if equipo:
        primero = date(anio, mes, 1)
        ultimo = date(anio, mes, calendar.monthrange(anio, mes)[1])
        for j in sorted([x for x in equipo.jornadas
                         if primero <= x.fecha <= ultimo],
                        key=lambda x: x.fecha):
            gente = [{"persona_id": a.persona_id,
                      "nombre": a.persona.nombre,
                      "reemplaza_a": (db.get(m.Persona, a.reemplaza_a_id).nombre
                                      if a.reemplaza_a_id else None),
                      "confirmado": a.confirmado}
                     for a in j.personal]
            dias.append({
                "jornada_id": j.id,
                "fecha": j.fecha.isoformat(),
                "dia_semana": j.fecha.weekday(),
                "fin_de_semana": j.fecha.weekday() >= 5,
                "adicional": j.es_dia_adicional,
                "estatus": j.estatus.value,
                "presentacion": j.inicio_programado.strftime("%H:%M"),
                "personal": gente,
                "unidades": [{"vehiculo_id": a.vehiculo_id,
                              "placa": a.vehiculo.placa,
                              "unidad": (a.vehiculo.categoria.nombre
                                         if a.vehiculo.categoria else None)}
                             for a in j.vehiculos],
            })

    # Los dias del mes que todavia no existen: los fines de semana que el
    # cliente puede pedir, y los habiles si el mes no se ha generado.
    puestos = {d["fecha"] for d in dias}
    sin_abrir = [x.isoformat()
                 for x in motor.dias_del_mes(anio, mes, True)
                 if x.isoformat() not in puestos]

    cambios = []
    if equipo:
        ids = [j.id for j in equipo.jornadas]
        for r in (db.query(m.ReemplazoRecurso)
                  .filter(m.ReemplazoRecurso.desde_jornada_id.in_(ids)).all()
                  if ids else []):
            desde = db.get(m.Jornada, r.desde_jornada_id)
            hasta = (db.get(m.Jornada, r.hasta_jornada_id)
                     if r.hasta_jornada_id else None)
            sale = (r.sale_persona_id and db.get(m.Persona, r.sale_persona_id)
                    or r.sale_vehiculo_id and db.get(m.Vehiculo, r.sale_vehiculo_id))
            entra = (r.entra_persona_id and db.get(m.Persona, r.entra_persona_id)
                     or r.entra_vehiculo_id and db.get(m.Vehiculo, r.entra_vehiculo_id))
            cambios.append({
                "tipo": r.tipo.value,
                "desde": desde.fecha.isoformat() if desde else None,
                "hasta": hasta.fecha.isoformat() if hasta else None,
                "sale": getattr(sale, "nombre", None) or getattr(sale, "placa", None),
                "entra": getattr(entra, "nombre", None) or getattr(entra, "placa", None),
                "motivo": r.motivo_tipo.value if r.motivo_tipo else None,
                "nota": r.motivo,
                "dias": r.jornadas_afectadas,
            })

    return {
        "servicio_id": servicio.id, "folio": servicio.folio,
        "cliente": servicio.cliente.nombre if servicio.cliente else None,
        "ejecutivo": servicio.ejecutivo_completo,
        "periodo": f"{mes:02d}/{anio}",
        "anio": anio, "mes": mes,
        "abierto": contrato is not None,
        "generado": contrato.generado if contrato else False,
        "contrato_id": contrato.id if contrato else None,
        "titular": (contrato.titular.nombre
                    if contrato and contrato.titular else None),
        "unidad": (contrato.vehiculo.placa
                   if contrato and contrato.vehiculo else None),
        "desde_dia": contrato.desde_dia if contrato else None,
        # De que turno es: la pantalla pinta distinto un 12x36 --el mes
        # entero, una persona por dia-- que un natural.
        "turno": motor.turno_del_servicio(db, servicio.id),
        "calendario": calendario,
        "dias": dias,
        "dias_sin_abrir": sin_abrir,
        "cambios": cambios,
        "resumen": motor.resumen_mensual(db, contrato.id) if contrato else None,
        # El cierre del mes: su fase y sus relojes (seccion 56). La
        # comision, solo si es suya (seccion 59).
        "cierre": (comisiones.solo_la_suya(cierre_mes.estado(db, contrato),
                                           usuario) if contrato else None),
    }


@router.post("/{servicio_id}/mes-siguiente",
             summary="Abrir el mes que sigue")
def abrir_siguiente(servicio_id: int, db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(CONSULTOR)):
    """El mes que sigue, con los terminos y la plantilla del que corre.

    No se vuelve a capturar nada: el implantado es continuo. El tope es
    un mes por delante del que se opera, y quien lo pide no elige cual
    —siempre es el siguiente— para que no se abran huecos en medio.
    """
    servicio = _servicio_implantado(db, servicio_id)
    abierto = motor.abrir_siguiente(db, servicio)
    auditoria.registrar(db, usuario, servicio, "abrir mes implantado",
                        f"{abierto['periodo']} con los terminos de "
                        f"{abierto['copiado_de']}")
    db.commit()
    return {"servicio_id": servicio.id, "folio": servicio.folio, **abierto}


@router.get("/{servicio_id}/mes-siguiente",
            summary="Que mes sigue y si se puede abrir")
def ver_siguiente(servicio_id: int, db: Session = Depends(get_db),
                  _=Depends(LECTURA)):
    servicio = _servicio_implantado(db, servicio_id)
    return motor.estado_del_siguiente(db, servicio)


@router.post("/{servicio_id}/mes/{anio}/{mes}/abrir",
             summary="Abrir el mes copiando los terminos del anterior")
def abrir_mes(servicio_id: int, anio: int, mes: int,
              db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(CONSULTOR)):
    """El implantado es continuo: el mes siguiente no se vuelve a
    capturar, se abre con los mismos terminos y se genera.

    El corte cae el ultimo dia del mes aunque el servicio haya empezado a
    media marcha, y el mes nuevo arranca limpio el dia 1.
    """
    servicio = _servicio_implantado(db, servicio_id)
    if _contrato_del_mes(db, servicio.id, anio, mes):
        raise HTTPException(409, f"El mes {mes:02d}/{anio} ya esta abierto")

    # Un solo camino para abrir meses: el de arriba. Pedir uno que no sea
    # el que sigue se contesta diciendo cual es.
    esperado = motor.estado_del_siguiente(db, servicio)
    if (esperado["anio"], esperado["mes"]) != (anio, mes):
        raise HTTPException(409, {
            "mensaje": f"El mes {mes:02d}/{anio} no es el que sigue",
            "que_hacer": (f"El que sigue es {esperado['periodo']}."
                          if esperado["periodo"] else esperado["razon"])})
    abierto = motor.abrir_siguiente(db, servicio)
    auditoria.registrar(db, usuario, servicio, "abrir mes implantado",
                        f"{abierto['periodo']} con los terminos de "
                        f"{abierto['copiado_de']}")
    db.commit()
    return abierto


@router.get("/{servicio_id}/calendario/{anio}/{mes}",
            summary="El mes pintado: que dia esta cubierto y cual no")
def calendario(servicio_id: int, anio: int, mes: int,
               db: Session = Depends(get_db), _=Depends(LECTURA)):
    """El calendario que ve el consultor, con el color de cada dia.

    Verde lo que ya esta cubierto, ambar el fin de semana contratado al
    que le falta quien lo cubra, y gris el dia que no es servicio. El
    color sale de lo que hay en la base, no de lo que alguien recuerde.
    """
    servicio = _servicio_implantado(db, servicio_id)
    contrato = _contrato_del_mes(db, servicio.id, anio, mes)
    if not contrato:
        raise HTTPException(409, f"El mes {mes:02d}/{anio} no esta abierto")

    equipo = servicio.equipos[0] if servicio.equipos else None
    cubiertos, cancelados = {}, set()
    if equipo:
        for jornada in equipo.jornadas:
            if jornada.fecha.year != anio or jornada.fecha.month != mes:
                continue
            # Un dia cancelado no esta cubierto: sale del servicio. Sin
            # esto seguia pintado de verde con el nombre de quien iba,
            # que es justo lo que uno cancela para dejar de ver.
            if jornada.estatus == m.EstatusJornada.CANCELADA:
                cancelados.add(jornada.fecha.isoformat())
                continue
            if jornada.personal:
                cubiertos[jornada.fecha.isoformat()] = ", ".join(
                    a.persona.nombre for a in jornada.personal)

    return {
        "servicio_id": servicio.id, "folio": servicio.folio,
        "periodo": f"{mes:02d}/{anio}",
        # El mes de contrato: de el cuelgan sus terminos y su cierre.
        "contrato_id": contrato.id,
        # El equipo es uno solo en el implantado, y de el cuelgan los
        # viaticos del mes: el panel lo necesita para pedirlos.
        "equipo_id": equipo.id if equipo else None,
        "dias_servicio": contrato.dias_servicio.value,
        "desde_dia": contrato.desde_dia,
        "turno": motor.turno_del_servicio(db, servicio.id),
        "cancelados": sorted(cancelados),
        "dias": motor.calendario_del_mes(
            anio, mes, contrato.dias_servicio, contrato.desde_dia, cubiertos,
            motor.turno_del_servicio(db, servicio.id), cancelados),
    }


class CubrirDiaIn(BaseModel):
    """Quien cubre ese dia, posicion por posicion."""
    personal: list[EnPlantillaIn] = []
    # Si el fin de semana trae los dos dias contratados, se resuelven los
    # dos juntos. Se puede apagar para cubrir uno solo.
    ambos_dias: bool = True


@router.get("/{servicio_id}/dia/{fecha}",
            summary="Como esta un dia y quien lo puede cubrir")
def ver_dia(servicio_id: int, fecha: date, db: Session = Depends(get_db),
            _=Depends(LECTURA)):
    servicio = _servicio_implantado(db, servicio_id)
    return motor.dia_del_servicio(db, servicio, fecha)


@router.post("/{servicio_id}/dia/{fecha}/cubrir",
             summary="Abrir o cubrir un dia con las posiciones del mes")
def cubrir_dia(servicio_id: int, fecha: date, datos: CubrirDiaIn,
               db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(CONSULTOR)):
    """El gris que pide el cliente y el ambar que hay que cubrir, por la
    misma puerta: los dos terminan con gente puesta en ese dia."""
    servicio = _servicio_implantado(db, servicio_id)
    resultado = motor.cubrir_dia(
        db, servicio, fecha,
        [p.model_dump() for p in datos.personal], datos.ambos_dias)
    auditoria.registrar(db, usuario, servicio, "cubrir dia",
                        ", ".join(resultado["dias"]))
    db.commit()
    return resultado


@router.delete("/{servicio_id}/dia/{fecha}",
               summary="Cerrar un dia que se abrio por error")
def cerrar_dia(servicio_id: int, fecha: date, db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(CONSULTOR)):
    servicio = _servicio_implantado(db, servicio_id)
    resultado = motor.cerrar_dia(db, servicio, fecha)
    auditoria.registrar(db, usuario, servicio, "cerrar dia", fecha.isoformat())
    db.commit()
    return resultado


@router.post("/{servicio_id}/mes/{anio}/{mes}/completar",
             summary="Generar los dias que el contrato reclama y no estan")
def completar_mes(servicio_id: int, anio: int, mes: int,
                  db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(CONSULTOR)):
    """Rellena los huecos con la plantilla del mes, sin tocar lo que ya
    existe. `generar_mes` salta los dias que ya estan, asi que esto no
    duplica nada ni pisa un dia cubierto.

    Va con `rellenando`: el mes de un hueco ya esta generado --si no, no
    habria hueco-- y sin eso el candado de "este mes ya se genero" dejaba
    el boton sin hacer nada. Lo caza test_mover_el_arranque_atras_avisa_
    de_los_dias_que_faltan."""
    servicio = _servicio_implantado(db, servicio_id)
    contrato = _contrato_del_mes(db, servicio.id, anio, mes)
    if not contrato:
        raise HTTPException(409, f"El mes {mes:02d}/{anio} no esta abierto")
    # Con el visto bueno del mes dado ya no entran dias; antes, los que
    # entren deshacen el termino del mes (seccion 56).
    if cierre_mes.con_visto_bueno(db, contrato):
        cierre_mes.deshacer_termino(db, contrato,
                                    "ya no se completan sus dias")
    hecho = motor.generar_mes(db, contrato.id,
                              rellenando=True)
    if hecho.get("jornadas_creadas"):
        cierre_mes.deshacer_termino(db, contrato,
                                    "ya no se completan sus dias")
    auditoria.registrar(db, usuario, servicio, "completar mes",
                        f"{mes:02d}/{anio}: {hecho.get('jornadas_creadas', 0)} dia(s)")
    db.commit()
    return hecho


@router.post("/{servicio_id}/dia/{fecha}/reactivar",
             summary="Devolver al servicio un dia cancelado")
def reactivar_dia(servicio_id: int, fecha: date, db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(CONSULTOR)):
    """La vuelta de `cerrar_dia`: el arranque se corrio hacia atras y
    ese dia vuelve a ser del servicio."""
    servicio = _servicio_implantado(db, servicio_id)
    resultado = motor.reactivar_dia(db, servicio, fecha)
    auditoria.registrar(db, usuario, servicio, "reactivar dia",
                        fecha.isoformat())
    db.commit()
    return resultado


@router.post("/{servicio_id}/dias", summary="Activar un dia del mes")
def activar_dia(servicio_id: int, datos: DiaFinDeSemanaIn,
                db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(CONSULTOR)):
    """Casi siempre un fin de semana que pide el cliente.

    Quien lo cubre se dice aqui: el titular descansa el fin de semana y
    muchas veces va alguien mas.
    """
    servicio = _servicio_implantado(db, servicio_id)
    contrato = _contrato_del_mes(db, servicio.id, datos.fecha.year,
                                 datos.fecha.month)
    if not contrato:
        raise HTTPException(409, f"El mes {datos.fecha.month:02d}/"
                                 f"{datos.fecha.year} no esta abierto")

    resultado = motor.agregar_dia(db, contrato.id, datos.fecha,
                                  datos.persona_id)
    auditoria.registrar(db, usuario, servicio, "dia adicional",
                        f"{datos.fecha} cubre "
                        f"{resultado.get('cubre') or 'sin asignar'}",
                        jornada_id=resultado["jornada_id"])
    db.commit()
    return resultado


@router.post("/{servicio_id}/cambios",
             summary="Cambiar personal o unidad en un tramo de dias")
def cambiar(servicio_id: int, datos: CambioRecursoIn,
            db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(CONSULTOR)):
    """Vacaciones, enfermedad, o la unidad en el taller."""
    servicio = _servicio_implantado(db, servicio_id)
    resultado = motor.cambiar_recurso(
        db, servicio.id, datos.tipo, datos.desde, datos.hasta,
        datos.entra_id, datos.motivo, usuario.persona_id,
        datos.sale_id, datos.nota, datos.relevado_en)
    partidos = resultado.get("jornadas_partidas") or []
    auditoria.registrar(db, usuario, servicio, "cambio de recurso",
                        f"{resultado['sale']} por {resultado['entra']} "
                        f"({datos.motivo.value}), "
                        f"{resultado['dias_cambiados']} dia(s)"
                        + (f"; dia partido: {', '.join(partidos)}"
                           if partidos else ""))
    db.commit()
    return resultado


@router.post("/{servicio_id}/cambios/vista-previa",
             summary="Que pasaria con este cambio, sin guardarlo")
def cambiar_previa(servicio_id: int, datos: CambioRecursoIn,
                   db: Session = Depends(get_db),
                   _: m.Usuario = Depends(CONSULTOR)):
    """Se ejecuta el cambio de verdad y se deshace.

    No hay una segunda implementacion que calcule "lo que pasaria": esa
    siempre acaba separandose de la primera, y entonces el recuadro que
    el consultor lee deja de ser lo que el sistema hace.

    Lo delicado no es el nombre de quien va: es que quien sale se queda
    con dinero que tiene que comprobar, que el dia puede partirse, y que
    un cambio sin fin llega hasta donde el sistema decida. Todo eso se
    dice antes de guardar.
    """
    servicio = _servicio_implantado(db, servicio_id)
    try:
        return motor.cambiar_recurso(
            db, servicio.id, datos.tipo, datos.desde, datos.hasta,
            datos.entra_id, datos.motivo, None,
            datos.sale_id, datos.nota, datos.relevado_en)
    finally:
        db.rollback()


@router.get("/{servicio_id}/hospitales",
            summary="Los hospitales que va a llevar la hoja")
def hospitales_del_servicio(servicio_id: int, db: Session = Depends(get_db),
                            _=Depends(LECTURA)):
    """Los tres mas cercanos al punto del servicio, de su ciudad.

    Salen del catalogo, que es de donde los toma la hoja: lo que se ve
    aqui es exactamente lo que va a leer el equipo en una emergencia. Si
    la ciudad no tiene hospitales cargados, la lista sale vacia y se
    dice, porque una hoja sin referencia medica no se manda.
    """
    servicio = _servicio_implantado(db, servicio_id)
    acuerdo = (db.query(m.AcuerdoImplantado)
               .filter_by(servicio_id=servicio.id).first())
    lat = acuerdo.origen_lat if acuerdo else None
    lon = acuerdo.origen_lon if acuerdo else None
    return {
        "servicio_id": servicio.id,
        "plaza_id": servicio.plaza_id,
        "pais_id": servicio.pais_id,
        "punto": acuerdo.origen_direccion if acuerdo else None,
        "lat": float(lat) if lat is not None else None,
        "lon": float(lon) if lon is not None else None,
        "hospitales": tasksheet.hospitales_cercanos(
            db, servicio.plaza_id, lat, lon),
    }


class RenglonTabuladorIn(BaseModel):
    """Un concepto del tabulador del acuerdo, por dia y por persona."""
    concepto: m.ConceptoViatico
    monto: Decimal = Decimal("0")
    # El concepto que existe pero no tiene numero fijo: se captura el dia
    # que toca. Un taxi que a veces hay y a veces no.
    monto_abierto: bool = False
    nota: str | None = None
    activo: bool = True


class TabuladorDelAcuerdoIn(BaseModel):
    renglones: list[RenglonTabuladorIn] = []


@router.get("/{servicio_id}/tabulador",
            summary="El tabulador de viaticos de este acuerdo")
def ver_tabulador(servicio_id: int, db: Session = Depends(get_db),
                  _=Depends(LECTURA)):
    """Lo que se acordo con ESTE cliente, por dia y por persona.

    El tabulador de la empresa vale para el eventual. El implantado se
    negocia uno por uno —que come el equipo, si se le paga el traslado,
    que pasa con la gasolina— y eso es parte del acuerdo. Lo que la
    empresa sugiere viene al lado, como punto de partida.
    """
    servicio = _servicio_implantado(db, servicio_id)
    return viaticos.ver_tabulador(db, servicio)


@router.put("/{servicio_id}/tabulador",
            summary="Guardar el tabulador de este acuerdo")
def guardar_tabulador(servicio_id: int, datos: TabuladorDelAcuerdoIn,
                      db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(TABULADOR)):
    servicio = _servicio_implantado(db, servicio_id)
    hecho = viaticos.guardar_tabulador(db, servicio, datos.renglones)
    auditoria.registrar(db, usuario, servicio, "tabulador de viaticos",
                        f"{hecho['total_dia']} por dia y por persona")
    db.commit()
    return hecho


class ViaticoDelMesIn(BaseModel):
    """Lo que se le deposita a una persona por sus dias de ese mes."""
    persona_id: int
    monto: Decimal


class DepositoDelMesIn(BaseModel):
    """Sin persona, va por todo el equipo de ese mes."""
    persona_id: int | None = None


# ---------------------------------------------------------- viaticos
#
# Los viaticos del implantado viven aparte de los del eventual. El
# calculo es el mismo —el tabulador es uno solo para toda la empresa—,
# pero el corte no: el eventual deposita una vez por todo el servicio y
# el implantado deposita, comprueba y cierra mes con mes, igual que
# factura. Por eso cada puerta de aqui lleva su anio y su mes.

@router.get("/{servicio_id}/viaticos/{anio}/{mes}",
            summary="Viaticos del mes, persona por persona")
def viaticos_del_mes(servicio_id: int, anio: int, mes: int,
                     db: Session = Depends(get_db), _=Depends(LECTURA)):
    servicio = _servicio_implantado(db, servicio_id)
    return viaticos.panel(db, servicio, anio, mes)


@router.post("/{servicio_id}/viaticos/{anio}/{mes}/persona",
             summary="Fijar cuanto se le deposita a una persona ese mes")
def fijar_viatico(servicio_id: int, anio: int, mes: int,
                  datos: ViaticoDelMesIn, db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(DINERO)):
    servicio = _servicio_implantado(db, servicio_id)
    hecho = viaticos.fijar(db, servicio, anio, mes, datos.persona_id,
                           datos.monto, usuario.persona_id)
    auditoria.registrar(db, usuario, servicio, "fijar viaticos",
                        f"{datos.monto} a persona {datos.persona_id} · "
                        f"{mes:02d}/{anio}, {hecho['dias']} dia(s)")
    db.commit()
    return viaticos.panel(db, servicio, anio, mes)


@router.post("/{servicio_id}/viaticos/{anio}/{mes}/persona/agregar",
             summary="Otro deposito para la misma persona en ese mes")
def agregar_viatico(servicio_id: int, anio: int, mes: int,
                    datos: ViaticoDelMesIn, db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(DINERO)):
    servicio = _servicio_implantado(db, servicio_id)
    viaticos.agregar(db, servicio, anio, mes, datos.persona_id,
                     datos.monto, usuario.persona_id)
    auditoria.registrar(db, usuario, servicio, "deposito adicional",
                        f"{datos.monto} a persona {datos.persona_id} · "
                        f"{mes:02d}/{anio}")
    db.commit()
    return viaticos.panel(db, servicio, anio, mes)


@router.post("/{servicio_id}/viaticos/{anio}/{mes}/solicitar",
             summary="Pedirle a finanzas el deposito del mes")
def solicitar_viatico(servicio_id: int, anio: int, mes: int,
                      datos: DepositoDelMesIn,
                      db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(DINERO)):
    servicio = _servicio_implantado(db, servicio_id)
    hecho = viaticos.solicitar(db, servicio, anio, mes, datos.persona_id)
    auditoria.registrar(db, usuario, servicio, "solicitar deposito",
                        f"{hecho['monto']} · {mes:02d}/{anio}, "
                        f"{hecho['depositos']} deposito(s)")
    db.commit()
    return viaticos.panel(db, servicio, anio, mes)


@router.post("/{servicio_id}/viaticos/{anio}/{mes}/cancelar",
             summary="Echar atras un deposito del mes que no se ha hecho")
def cancelar_viatico(servicio_id: int, anio: int, mes: int,
                     datos: DepositoDelMesIn,
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(DINERO)):
    servicio = _servicio_implantado(db, servicio_id)
    hecho = viaticos.cancelar(db, servicio, anio, mes, datos.persona_id)
    auditoria.registrar(db, usuario, servicio, "cancelar solicitud",
                        f"{hecho['monto']} · {mes:02d}/{anio}, "
                        f"{hecho['depositos']} deposito(s)")
    db.commit()
    return viaticos.panel(db, servicio, anio, mes)


class TallerIn(BaseModel):
    """La unidad entra al taller y otra toma su lugar.

    Es una sola decision del consultor y por eso es una sola puerta: el
    bloqueo de la unidad que sale y el cambio en los dias del tramo se
    guardan juntos. Registrarlos aparte es como se llega a un calendario
    donde la unidad bloqueada sigue asignada.

    El dato del taller normalmente viene de Odoo, que es donde vive el
    mantenimiento de la flota. Esto es para cuando la unidad se queda en
    el camino y hay que resolver el servicio de manana.
    """
    vehiculo_id: int | None = None      # vacio: la unidad del contrato
    desde: date
    # Vacio: sigue en el taller sin fecha de entrega. Es lo normal en un
    # correctivo, y el cambio corre de ese dia en adelante.
    hasta: date | None = None
    tipo: m.MotivoCambio = m.MotivoCambio.MANTENIMIENTO_CORRECTIVO
    entra_id: int                       # la unidad que toma su lugar
    taller: str | None = None
    folio: str | None = None
    nota: str | None = None


@router.get("/{servicio_id}/unidades-libres",
            summary="Que unidades pueden entrar en un tramo de dias")
def unidades_libres(servicio_id: int, desde: date, hasta: date | None = None,
                    db: Session = Depends(get_db), _=Depends(LECTURA)):
    """La flota de la ciudad medida contra los dias del tramo.

    Misma cuenta que en el alta: cuantos de esos dias puede cada unidad,
    contando el taller. Sale por categoria, que es como se pide —"otra
    blindada"— y no por placa, que es como se guarda.
    """
    servicio = _servicio_implantado(db, servicio_id)
    equipo = servicio.equipos[0] if servicio.equipos else None
    dias = sorted({j.fecha for j in (equipo.jornadas if equipo else [])
                   if j.estatus != m.EstatusJornada.CANCELADA
                   and j.fecha >= desde
                   and (hasta is None or j.fecha <= hasta)})
    if not dias:
        raise HTTPException(409, "No hay dias de servicio en ese tramo")

    modalidad = (db.query(m.Modalidad)
                 .filter(m.Modalidad.pais_id == servicio.pais_id,
                         m.Modalidad.codigo == m.CodigoModalidad.FULL_DAY)
                 .first())
    horas = float(modalidad.horas) if modalidad else 12.0
    bloquea = modalidad.bloquea_dia_completo if modalidad else True

    # La hora de presentacion es la del contrato del primer dia del tramo.
    contrato = _contrato_del_mes(db, servicio.id, dias[0].year, dias[0].month)
    arranque = time.fromisoformat(contrato.hora_presentacion
                                  if contrato else "08:00:00")

    flota = (db.query(m.Vehiculo)
             .filter(m.Vehiculo.plaza_id == servicio.plaza_id,
                     m.Vehiculo.activo.is_(True),
                     m.Vehiculo.rentado.is_(False)).all())
    bloqueos = motor.taller_de(db, [v.id for v in flota])

    salida = []
    for unidad in flota:
        choques = []
        for dia in dias:
            inicio = datetime.combine(dia, arranque)
            hallazgos = disp.revisar_vehiculo(db, unidad.id, inicio,
                                              inicio + timedelta(hours=horas),
                                              bloquea)
            if any(x.nivel == "bloqueo" for x in hallazgos):
                choques.append(dia.isoformat())
        en_taller = [d.isoformat() for d in dias
                     if motor.en_taller(bloqueos.get(unidad.id), d)]
        fuera = sorted(set(choques) | set(en_taller))
        salida.append({
            "vehiculo_id": unidad.id, "placa": unidad.placa,
            "categoria_id": unidad.categoria_id,
            "categoria": unidad.categoria.nombre if unidad.categoria else None,
            "marca_modelo": unidad.marca_modelo,
            "libres": len(dias) - len(fuera),
            "choques": fuera,
            "dias_en_taller": len(en_taller),
        })
    salida.sort(key=lambda x: (-x["libres"], x["placa"]))
    return {"dias": len(dias), "desde": dias[0].isoformat(),
            "hasta": dias[-1].isoformat(), "vehiculos": salida}


@router.post("/{servicio_id}/taller",
             summary="Meter una unidad al taller y poner otra en su lugar")
def al_taller(servicio_id: int, datos: TallerIn,
              db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(CONSULTOR)):
    """Dos cosas que son una sola: la unidad se bloquea y otra entra.

    El bloqueo vale para toda la empresa —la unidad deja de ofrecerse en
    cualquier servicio, tenga o no dias asignados— y el cambio solo toca
    los dias de este servicio.
    """
    servicio = _servicio_implantado(db, servicio_id)

    sale_id = datos.vehiculo_id
    if not sale_id:
        contrato = _contrato_del_mes(db, servicio.id, datos.desde.year,
                                     datos.desde.month)
        sale_id = contrato.vehiculo_id if contrato else None
    if not sale_id:
        raise HTTPException(409, "No se sabe que unidad sale. Digalo.")
    if sale_id == datos.entra_id:
        raise HTTPException(409, "La unidad que entra es la misma que sale")

    sale = db.get(m.Vehiculo, sale_id)
    if not sale:
        raise HTTPException(404, f"No existe la unidad {sale_id}")

    # Primero el cambio: si no hay dias en el tramo o la unidad que entra
    # no existe, revienta aqui y no queda un bloqueo suelto sin cambio.
    resultado = motor.cambiar_recurso(
        db, servicio.id, m.TipoRecurso.VEHICULO, datos.desde, datos.hasta,
        datos.entra_id, datos.tipo, usuario.persona_id, sale_id, datos.nota)

    db.add(m.TallerVehiculo(
        vehiculo_id=sale_id, desde=datos.desde, hasta=datos.hasta,
        tipo=datos.tipo, taller=datos.taller, folio=datos.folio,
        nota=datos.nota))
    auditoria.registrar(db, usuario, servicio, "unidad al taller",
                        f"{sale.placa} entra al taller "
                        f"({datos.tipo.value}) desde "
                        f"{datos.desde.isoformat()}; la cubre "
                        f"{resultado['entra']}")
    db.commit()
    return {"taller": {"placa": sale.placa,
                       "desde": datos.desde.isoformat(),
                       "hasta": datos.hasta.isoformat() if datos.hasta else None,
                       "tipo": datos.tipo.value},
            **resultado}


@router.get("/{servicio_id}/taller",
            summary="Unidades del servicio que estan o estuvieron fuera")
def taller_del_servicio(servicio_id: int, db: Session = Depends(get_db),
                        _=Depends(LECTURA)):
    servicio = _servicio_implantado(db, servicio_id)
    equipo = servicio.equipos[0] if servicio.equipos else None
    usadas = {a.vehiculo_id for j in (equipo.jornadas if equipo else [])
              for a in j.vehiculos}
    contratos = (db.query(m.ContratoImplantado)
                 .filter_by(servicio_id=servicio.id).all())
    usadas |= {c.vehiculo_id for c in contratos if c.vehiculo_id}
    if not usadas:
        return []

    hoy = date.today()
    filas = (db.query(m.TallerVehiculo)
             .filter(m.TallerVehiculo.vehiculo_id.in_(usadas))
             .order_by(m.TallerVehiculo.desde.desc()).all())
    return [{"id": f.id, "placa": f.vehiculo.placa if f.vehiculo else None,
             "desde": f.desde.isoformat(),
             "hasta": f.hasta.isoformat() if f.hasta else None,
             "tipo": f.tipo.value if f.tipo else None,
             "taller": f.taller, "folio": f.folio, "nota": f.nota,
             "hoy_fuera": f.cubre(hoy)}
            for f in filas]


@router.get("/{servicio_id}/mes/{anio}/{mes}/plantilla",
            summary="Quien va y en que unidad, ese mes")
def ver_plantilla(servicio_id: int, anio: int, mes: int,
                  db: Session = Depends(get_db), _=Depends(LECTURA)):
    servicio = _servicio_implantado(db, servicio_id)
    contrato = _contrato_del_mes(db, servicio.id, anio, mes)
    if not contrato:
        raise HTTPException(409, f"El mes {mes:02d}/{anio} no esta abierto")
    return {
        "contrato_id": contrato.id,
        "personal": [{"persona_id": f.persona_id,
                      "nombre": f.persona.nombre,
                      "rol_id": f.rol_id,
                      "rol": f.rol.nombre if f.rol else None,
                      "conduce": (f.rol.codigo == motor.ROL_CONDUCTOR
                                  if f.rol else False),
                      "vehiculo_id": f.vehiculo_id,
                      "placa": f.vehiculo.placa if f.vehiculo else None}
                     for f in contrato.plantilla],
        "unidades": [{"vehiculo_id": f.vehiculo_id,
                      "placa": f.vehiculo.placa,
                      "unidad": (f.vehiculo.categoria.nombre
                                 if f.vehiculo.categoria else None)}
                     for f in contrato.unidades],
    }


@router.put("/{servicio_id}/mes/{anio}/{mes}/plantilla",
            summary="Corregir quien va ese mes")
def guardar_plantilla(servicio_id: int, anio: int, mes: int,
                      datos: PlantillaIn, db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(CONSULTOR)):
    """Cambia la plantilla del mes y la vuelve a poner en todos sus dias.

    No toca los dias que ya se operaron ni los que traen un cambio: si
    alguien cubrio el martes, ese martes se queda como quedo. Lo que se
    reescribe es lo que todavia no ha pasado.
    """
    servicio = _servicio_implantado(db, servicio_id)
    contrato = _contrato_del_mes(db, servicio.id, anio, mes)
    if not contrato:
        raise HTTPException(409, f"El mes {mes:02d}/{anio} no esta abierto")

    motor.guardar_plantilla(
        db, contrato,
        [(p.persona_id, p.vehiculo_id, p.rol_id, p.empieza)
         for p in datos.personal],
        datos.unidades)
    rehechos = motor.rehacer_dias(db, contrato)
    auditoria.registrar(db, usuario, servicio, "plantilla implantado",
                        f"{mes:02d}/{anio}: {len(datos.personal)} persona(s), "
                        f"{len(datos.unidades)} unidad(es), "
                        f"{rehechos} dia(s) rehechos")
    db.commit()
    return {"resultado": "plantilla guardada", "dias_rehechos": rehechos}

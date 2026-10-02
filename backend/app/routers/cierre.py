"""Cotizacion, cierre del servicio, comparativo y rentabilidad."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auditoria, auth
from app import bolson
from app import desglose
from app import facturacion
from app import historial
from app import nomina
from app import cierre as motor
from app import cierre_mes
from app import cotizacion as cotmotor
from app import models as m
from app import comisiones as motor_comisiones
from app import odoo_facturacion
from app import reloj
from app import revisor
from app import tipo_cambio
from app.db import get_db

router = APIRouter(tags=["Cierre y cotizacion"])

# Cotizar no es cerrar: lo primero le pone precio al servicio y lo
# segundo lo manda a facturar. `DIRECCION` se fue porque no la usaba
# ningun endpoint: era un alias muerto.
#
# `COTIZA` tambien estaba muerto hasta la seccion 73: las dos puertas de
# la cotizacion pedian la de cerrar. Por rol daba lo mismo --las tienen
# los mismos--; con puestos no: el consultor JR cotiza y no cierra.
COTIZA = auth.puede("cierre.cotizar")
CONSULTOR = auth.puede("cierre.cerrar")
FINANZAS = auth.puede("cierre.facturar")
LECTURA = auth.puede("cierre.ver")
# Quien trae dinero encima y cuanto no lo ve cualquiera: la misma puerta
# que el panel de viaticos del equipo.
DINERO = auth.puede("viaticos.ver")
# El cobro de una cancelacion lo autoriza direccion de operaciones
# (seccion 105); direccion general lo alcanza por lo que hereda.
AUTORIZA_COBRO = auth.puede("cierre.autorizar_cobro")
# El historial de lo facturado (seccion 69): los mismos que abren
# Facturacion.
HISTORIAL = auth.puede("cierre.historial")


class LineaIn(BaseModel):
    fecha: date
    tipo: m.TipoLinea
    equipo_clave: str = "Alfa"
    perfil_id: int | None = None
    categoria_id: int | None = None
    cantidad: int = 1
    precio_unitario: Decimal | None = None
    descripcion: str | None = None


class CotizacionIn(BaseModel):
    servicio_id: int
    lineas: list[LineaIn]
    viaticos_incluidos: bool = True
    motivo: str | None = None


class AutorizarIn(BaseModel):
    autorizada_por: str


class LoQueLlevaIn(BaseModel):
    """Un rol o una unidad de un dia de un equipo (seccion 94)."""
    fecha: date
    tipo: m.TipoLinea
    equipo_clave: str = "Alfa"
    perfil_id: int | None = None
    categoria_id: int | None = None
    cantidad: int = 1


class VistaPreviaIn(BaseModel):
    servicio_id: int
    lineas: list[LoQueLlevaIn]
    # dentro | fijo | comprobar
    gastos: str
    monto_gastos: Decimal | None = None


class CotizacionAutorizadaIn(VistaPreviaIn):
    """La cotizacion nueva, ya autorizada: quien la autorizo del lado del
    cliente, el dia y, si se hizo en Odoo, su folio. Al recotizar, el
    motivo."""
    autorizada_por: str = Field(max_length=200)
    autorizada_el: date
    folio_odoo: str | None = Field(default=None, max_length=80)
    motivo: str | None = Field(default=None, max_length=600)


class FacturaDeOdooIn(BaseModel):
    """La factura que finanzas hizo en Odoo (seccion 96): su folio y su
    fecha."""
    folio: str = Field(max_length=200)
    fecha: date


class RespaldoIn(BaseModel):
    # Cabe en la columna (seccion 101): mas largo tronaba en la base.
    justificacion: str = Field(max_length=500)


class DevolucionIn(BaseModel):
    motivo: str


class CobroIn(BaseModel):
    """Como se cobra la cancelacion (seccion 105): completo o ejecutado,
    y la nota de operaciones si cambia lo que pidio el consultor."""
    cobro: str = Field(max_length=12)
    nota: str | None = Field(default=None, max_length=motor.LARGO_NOTA)


# ---------------------------------------------------------------- cotizacion

@router.post("/cotizaciones", status_code=201, summary="Generar cotizacion")
def cotizar(datos: CotizacionIn, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(COTIZA)):
    """Toma los precios del tarifario del cliente. Si ya habia cotizacion,
    esta queda como version nueva y la anterior como sustituida."""
    cotizacion = cotmotor.generar(
        db, datos.servicio_id,
        [l.model_dump() for l in datos.lineas],
        viaticos_incluidos=datos.viaticos_incluidos,
        creada_por_id=usuario.persona_id, motivo=datos.motivo)

    auditoria.registrar(db, usuario, cotizacion.servicio,
                        "cotizar" if cotizacion.version == 1 else "recotizar",
                        f"version {cotizacion.version}, total {cotizacion.total}")
    db.commit()

    return {"cotizacion_id": cotizacion.id, "version": cotizacion.version,
            "total": cotizacion.total, "moneda": cotizacion.moneda.value,
            "lineas": len(cotizacion.lineas), "estatus": cotizacion.estatus.value}


@router.post("/cotizaciones/{cotizacion_id}/autorizar",
             summary="El cliente autoriza la cotizacion")
def autorizar(cotizacion_id: int, datos: AutorizarIn, db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(COTIZA)):
    cotizacion = cotmotor.autorizar(db, cotizacion_id, datos.autorizada_por)
    auditoria.registrar(db, usuario, cotizacion.servicio, "autorizar cotizacion",
                        f"version {cotizacion.version} por {datos.autorizada_por}")
    db.commit()
    return {"resultado": "autorizada", "version": cotizacion.version,
            "total": cotizacion.total}


@router.get("/cotizaciones/servicio/{servicio_id}",
            summary="Cotizaciones de un servicio")
def ver_cotizaciones(servicio_id: int, db: Session = Depends(get_db),
                     _=Depends(LECTURA)):
    # Las del servicio: la propuesta del implantado no es una de ellas
    # (seccion 115).
    cotizaciones = (cotmotor.de_cotizacion(db.query(m.Cotizacion))
                    .filter_by(servicio_id=servicio_id)
                    .order_by(m.Cotizacion.version).all())
    return [{
        "id": c.id, "version": c.version, "estatus": c.estatus.value,
        "total": c.total, "moneda": c.moneda.value,
        "viaticos_incluidos": c.viaticos_incluidos,
        "motivo_recotizacion": c.motivo_recotizacion,
        "autorizada_por": c.autorizada_por,
        "autorizada_el": c.autorizada_el.isoformat() if c.autorizada_el else None,
        "folio_odoo": c.folio_odoo,
        "lineas": [{"fecha": l.fecha.isoformat(), "equipo": l.equipo_clave,
                    "tipo": l.tipo.value, "descripcion": l.descripcion,
                    "cantidad": l.cantidad, "precio": l.precio_unitario,
                    "subtotal": l.subtotal} for l in c.lineas],
    } for c in cotizaciones]


# ------------------------------------------------ la cotizacion en el servicio
#
# Seccion 94: mientras Odoo no la manda, el consultor --o quien lo
# cubre, que queda anotado como cobertura-- la registra en el servicio,
# con los precios del tarifario del cliente y ya autorizada.

@router.get("/cotizaciones/servicio/{servicio_id}/bloque",
            summary="La cotizacion del servicio y lo que hace falta para armarla")
def bloque_de_cotizacion(servicio_id: int, db: Session = Depends(get_db),
                         usuario: m.Usuario = Depends(LECTURA)):
    datos = cotmotor.bloque(db, servicio_id)
    datos["puede_cotizar"] = auth.puede_el_usuario(db, usuario, "cierre.cotizar")
    return datos


@router.post("/cotizaciones/vista-previa",
             summary="Los precios de lo que se va a cotizar, sin guardar nada")
def vista_previa_de_cotizacion(datos: VistaPreviaIn, db: Session = Depends(get_db),
                               _=Depends(COTIZA)):
    return cotmotor.vista_previa(
        db, datos.servicio_id, [l.model_dump() for l in datos.lineas],
        datos.gastos, datos.monto_gastos)


@router.post("/cotizaciones/autorizada", status_code=201,
             summary="Registrar la cotizacion que el cliente autorizo")
def registrar_cotizacion_autorizada(datos: CotizacionAutorizadaIn,
                                    db: Session = Depends(get_db),
                                    usuario: m.Usuario = Depends(COTIZA)):
    """Se guarda ya autorizada. Al recotizar, la nueva nace autorizada con
    su motivo y la de antes queda sustituida: el servicio nunca se queda
    sin cotizacion vigente. Si algo falla no se guarda nada."""
    cotizacion = cotmotor.registrar_autorizada(
        db, datos.servicio_id, [l.model_dump() for l in datos.lineas],
        datos.gastos, datos.monto_gastos, datos.autorizada_por,
        datos.autorizada_el, datos.folio_odoo, datos.motivo,
        usuario.persona_id)
    detalle = (f"version {cotizacion.version}, total {cotizacion.total} "
               f"{cotizacion.moneda.value}; la autorizo "
               f"{cotizacion.autorizada_por} el "
               f"{cotizacion.autorizada_el:%d/%m/%Y}")
    if cotizacion.folio_odoo:
        detalle += f"; folio de Odoo {cotizacion.folio_odoo}"
    if cotizacion.motivo_recotizacion:
        detalle += f"; motivo: {cotizacion.motivo_recotizacion}"
    auditoria.registrar(db, usuario, cotizacion.servicio,
                        "cotizar y autorizar" if cotizacion.version == 1
                        else "recotizar", detalle)
    db.commit()
    db.refresh(cotizacion)
    return cotmotor.resumen(db, cotizacion)


# ---------------------------------------------------------------- cierre

@router.post("/cierre/servicio/{servicio_id}/abrir",
             summary="Arrancar las 24 horas del consultor")
def abrir(servicio_id: int, db: Session = Depends(get_db),
          ahora: datetime | None = None,
          usuario: m.Usuario = Depends(CONSULTOR)):
    """Devuelve el cierre del servicio, abriendolo si hiciera falta.

    Desde que el cierre se abre solo al terminar el ultimo dia, esto casi
    siempre devuelve el que ya existe. Se deja por el servicio que quedo
    abierto de antes, y solo con el servicio ya terminado (seccion 101):
    abierto sobre uno en curso, nacia un cierre con el T0 que mandara
    quien llamaba --una ruta para regalar o quitar comisiones-- y al
    cerrar de verdad el ultimo dia ese cierre se respetaba, con el plazo
    del consultor ya vencido. El T0 lo pone el sistema: la hora del pais
    en que se abre; `ahora` solo cuenta fuera de produccion.

    Ya no recibe `idioma` ni manda encuestas: salen al terminar el
    servicio, cada una en el idioma de quien la va a contestar, y la que
    no nacio se manda desde la tarjeta del servicio.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    if servicio.estatus not in motor.YA_TERMINO:
        raise HTTPException(409, {
            "mensaje": "El servicio no ha terminado: su cierre arranca solo "
                       "al cerrar el último día.",
            "que_hacer": "Cierra el último día desde la app, o a mano en la "
                         "central, y el cierre nace con la hora del término.",
        })
    c = motor.abrir(db, servicio_id, reloj.de_prueba(ahora))
    db.commit()
    # Las del servicio, no solo las que se acaban de crear: quien abre
    # esta pantalla quiere saber si el cliente ya tiene su encuesta, no
    # si nacio en este segundo.
    suyas = db.query(m.Encuesta).filter_by(servicio_id=servicio_id).all()
    return {"cierre_id": c.id, "abierto_en": c.abierto_en.isoformat(),
            "comprobacion_hasta": (c.comprobacion_hasta.isoformat()
                                   if c.comprobacion_hasta else None),
            "limite_consultor": c.limite_consultor.isoformat(),
            "estatus": c.estatus.value,
            "encuestas_enviadas": [e.tipo.value for e in suyas]}


@router.get("/cierre/servicio/{servicio_id}/comparativo",
            summary="Cotizado contra ejecutado")
def comparativo(servicio_id: int, db: Session = Depends(get_db), _=Depends(LECTURA)):
    return motor.comparar(db, servicio_id)


@router.get("/cierre/servicio/{servicio_id}/rentabilidad",
            summary="Rentabilidad del servicio")
def rentabilidad(servicio_id: int, db: Session = Depends(get_db),
                 _=Depends(auth.puede("cierre.rentabilidad"))):
    """Facturacion, costo de personal y viaticos, y costo del vehiculo."""
    return motor.rentabilidad(db, servicio_id)


@router.get("/cierre/servicio/{servicio_id}/estado",
            summary="El reloj del consultor, sin el comparativo")
def estado_del_cierre(servicio_id: int, db: Session = Depends(get_db),
                      ahora: datetime | None = None,
                      usuario: m.Usuario = Depends(LECTURA)):
    """La pantalla lo pide aparte porque la revision revienta cuando no
    hay cotizacion autorizada, y el plazo corre igual."""
    return motor_comisiones.solo_la_suya(
        motor.estado(db, servicio_id, ahora), usuario)


@router.get("/cierre/servicio/{servicio_id}/revision",
            summary="Revision automatica antes de enviar a finanzas")
def revision(servicio_id: int, db: Session = Depends(get_db),
             ahora: datetime | None = None,
             usuario: m.Usuario = Depends(LECTURA)):
    """Acompana al consultor durante sus 24 horas y hace el primer filtro
    del comparativo para finanzas."""
    return motor_comisiones.solo_la_suya(
        revisor.revisar(db, servicio_id, ahora), usuario)


@router.get("/cierre/servicio/{servicio_id}/viaticos",
            summary="El dinero del personal, persona por persona")
def viaticos_del_servicio(servicio_id: int, db: Session = Depends(get_db),
                          _=Depends(DINERO)):
    """Para revisar antes del visto bueno: por persona lo depositado, lo
    comprobado y lo que falta; cada ticket con su foto, y lo que se puede
    hacer con ese dinero (cerrar, o cerrar con descuento si ya vencio su
    plazo). El dinero de una persona es uno solo (`app.bolson`)."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    ahora = reloj.ahora_del_servicio(db, servicio)
    viaticos = motor.viaticos_del_servicio(db, servicio_id)
    # Con la gasolina contra los kilometros de la unidad (seccion 60).
    from app import gps
    return {"momento": ahora.isoformat(),
            "personas": gps.con_gasolina(db, bolson.revision(viaticos, ahora),
                                         viaticos)}


@router.get("/cierre/servicio/{servicio_id}/desglose-gastos",
            response_class=HTMLResponse,
            summary="El desglose de gastos para el cliente")
def desglose_del_servicio(servicio_id: int, idioma: str | None = None,
                          db: Session = Depends(get_db), _=Depends(LECTURA)):
    """Lo comprobado valido, gasto por gasto y con sus comprobantes, en
    el idioma del cliente. Es lo que se le manda con la factura cuando
    paga los gastos netos (seccion 59)."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    cierre = (db.query(m.Cierre)
              .filter_by(servicio_id=servicio_id, contrato_id=None).first())
    plaza = db.get(m.Plaza, servicio.plaza_id)
    vigente = cotmotor.vigente(db, servicio_id)
    pais = db.get(m.Pais, servicio.pais_id)
    # Los gastos van en la moneda del pais, que es en la que se pagaron.
    # Si la factura es en otra --Amazon, en dolares--, el desglose dice
    # tambien el tipo de cambio y el total en esa moneda (seccion 82).
    # Antes salian los pesos rotulados en dolares.
    moneda = pais.moneda_local.value if pais else None
    cambio = None
    if vigente and not vigente.viaticos_incluidos:
        otra, tc = motor.tipo_de_cambio_de_gastos(db, servicio, vigente)
        if otra and tc:
            cambio = {"moneda": vigente.moneda.value, "tasa": tc["tasa"]}
    # Lo que va dentro de un paquete no se le cobra aparte, y no va en su
    # desglose (seccion 79).
    viaticos = (motor.viaticos_facturables(db, servicio, vigente.tarifario_id,
                                           cotmotor.con_paquetes(db, vigente))
                if vigente else motor.viaticos_del_servicio(db, servicio_id))
    return HTMLResponse(desglose.render(
        servicio, plaza.nombre if plaza else None, viaticos,
        idioma if idioma in desglose.TEXTOS
        else desglose.idioma_del_cliente(db, servicio),
        moneda, factura=cierre.factura_odoo if cierre else None,
        cambio=cambio))


@router.get("/cierre/relojes",
            summary="El reloj del cierre de cada eventual, para la cartera")
def relojes(db: Session = Depends(get_db), _=Depends(LECTURA)):
    """Junto al estatus, el tiempo que queda: el del personal mientras
    comprueba y el del consultor sin visto bueno. Uno por servicio, solo
    los que tienen un reloj corriendo."""
    relojes_ = reloj.Relojes(db)
    salida = []
    for fila in (db.query(m.Cierre)
                 .filter(m.Cierre.contrato_id.is_(None),
                         m.Cierre.estatus.in_((
                             m.EstatusCierre.ABIERTO,
                             m.EstatusCierre.SIN_VISTO_BUENO,
                             m.EstatusCierre.EN_REVISION_IA,
                             m.EstatusCierre.DEVUELTO_A_OPERACION)))
                 .all()):
        ahora = relojes_.del_servicio(fila.servicio)
        salida.append({"servicio_id": fila.servicio_id,
                       "fase": motor.FASES.get(fila.estatus),
                       "reloj": motor.reloj_de(fila, ahora)})
    return salida


@router.get("/cierre/facturacion",
            summary="La bandeja de facturacion de finanzas")
def bandeja_de_facturacion(db: Session = Depends(get_db),
                           usuario: m.Usuario = Depends(LECTURA)):
    """Por aprobar, por facturar y lo cerrado este mes (seccion 59)."""
    return motor_comisiones.solo_la_suya(facturacion.bandeja(db), usuario)


# ---------------------------------------------------------------- historial

@router.get("/cierre/historial",
            summary="Lo que ya se facturo, desde el primer servicio")
def historial_de_lo_facturado(desde: str | None = None,
                              hasta: str | None = None,
                              cliente_id: int | None = None,
                              consultor_id: int | None = None,
                              tipo: str | None = None,
                              folio: str | None = None,
                              pagina: int = 1, por_pagina: int = 50,
                              db: Session = Depends(get_db),
                              _=Depends(HISTORIAL)):
    """Un renglon por cierre --el implantado, por mes--, con lo que suma
    todo lo filtrado y como van sus fotos: cuantas siguen en Centauro y
    cuando se archivan (seccion 69). `desde` y `hasta` son meses,
    "2026-10", y cuentan por la fecha de la factura, o de la aprobacion
    si no la hubo."""
    return historial.consultar(
        db, historial.filtros(desde, hasta, cliente_id, consultor_id, tipo,
                              folio), pagina, por_pagina)


@router.get("/cierre/historial.xlsx",
            summary="El historial de lo facturado, en Excel")
def historial_en_excel(desde: str | None = None, hasta: str | None = None,
                       cliente_id: int | None = None,
                       consultor_id: int | None = None,
                       tipo: str | None = None, folio: str | None = None,
                       idioma: str = "es",
                       db: Session = Depends(get_db), _=Depends(HISTORIAL)):
    """Lo mismo que se filtro en la pantalla, completo, en dos hojas:
    los servicios y sus comprobantes. Las fotos no van."""
    contenido, nombre = historial.excel_del_historial(
        db, historial.filtros(desde, hasta, cliente_id, consultor_id, tipo,
                              folio), idioma)
    return Response(
        content=contenido,
        media_type=("application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"),
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/cierre/historial/{cierre_id}",
            summary="Un servicio del historial, con sus comprobantes")
def historial_de_un_servicio(cierre_id: int, db: Session = Depends(get_db),
                             usuario: m.Usuario = Depends(HISTORIAL)):
    """Sus numeros y, por persona, cada comprobante y cada devolucion con
    el estado de su foto: en Centauro, o archivada y desde cuando."""
    return historial.detalle(db, cierre_id, usuario)


@router.post("/cierre/{cierre_id}/desviaciones/respaldar",
             summary="Justificar una desviacion detectada")
def respaldar(cierre_id: int, descripcion: str, datos: RespaldoIn,
              db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(CONSULTOR)):
    """Solo las desviaciones sin respaldo detonan el escalamiento.

    Se justifica una desviacion viva del comparativo, tal como la dice
    la revision, y solo mientras el servicio espera el visto bueno
    (seccion 101). Antes entraba cualquier texto, sobre un cierre ya
    aprobado o facturado, y siempre como "recurso no cotizado": la
    justificacion se guarda con el tipo y el monto de la desviacion que
    de verdad tapa.
    """
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")
    if cierre.estatus not in (m.EstatusCierre.SIN_VISTO_BUENO,
                              m.EstatusCierre.DEVUELTO_A_OPERACION):
        raise HTTPException(409, {
            "mensaje": ("Una desviación se justifica mientras el servicio "
                        "espera el visto bueno; este está en "
                        f"{motor.nombre_estatus(cierre.estatus)}."),
            "que_hacer": "Lo que ya se mandó a finanzas se corrige con una "
                         "nota de crédito o regresándolo desde facturación.",
        })
    justificacion = " ".join(datos.justificacion.split())
    if len(justificacion) < 15:
        raise HTTPException(400, "Explica la desviacion con mas detalle")
    descripcion = " ".join((descripcion or "").split())
    if not descripcion:
        raise HTTPException(400, "Di cuál desviación justificas")

    # La desviacion tiene que estar en el comparativo de hoy, con su
    # texto: el dinero del personal no se justifica, se cierra.
    del_dinero = {m.TipoDesviacion.VIATICO_SIN_COMPROBAR.value,
                  m.TipoDesviacion.VIATICO_NO_CERRADO.value,
                  m.TipoDesviacion.VIATICO_EXCEDIDO.value}
    viva = next((d for d in motor.comparar(db, cierre.servicio_id)["desviaciones"]
                 if d["descripcion"] == descripcion and not d.get("respaldada")),
                None)
    if viva is None:
        raise HTTPException(409, {
            "mensaje": "Esa desviación no está en el comparativo de hoy.",
            "que_hacer": "Justifica una de las desviaciones que enseña la "
                         "revisión, tal como la dice.",
        })
    if viva["tipo"] in del_dinero:
        raise HTTPException(409, {
            "mensaje": "El dinero del personal no se justifica: se cierra.",
            "que_hacer": "Ciérralo en «Viáticos del personal», con descuento "
                         "si ya venció su plazo.",
        })
    if any(d.descripcion == descripcion and d.respaldada
           for d in cierre.desviaciones):
        raise HTTPException(409, {
            "mensaje": "Esa desviación ya tiene justificación.",
            "que_hacer": "La revisión ya la enseña como respaldada.",
        })

    db.add(m.Desviacion(cierre_id=cierre.id, tipo=m.TipoDesviacion(viva["tipo"]),
                        descripcion=descripcion, monto=viva["monto"],
                        respaldada=True, justificacion=justificacion,
                        detectada_por="consultor"))
    auditoria.registrar(db, usuario, cierre.servicio, "respaldar desviacion",
                        f"{viva['tipo']}: {descripcion}"[:200])
    db.commit()
    return {"resultado": "respaldada", "descripcion": descripcion,
            "tipo": viva["tipo"], "monto": viva["monto"]}


@router.post("/cierre/{cierre_id}/enviar-finanzas",
             summary="El consultor cierra y manda a facturar")
def enviar_finanzas(cierre_id: int, db: Session = Depends(get_db),
                    ahora: datetime | None = None,
                    usuario: m.Usuario = Depends(CONSULTOR)):
    """No se puede enviar con observaciones graves sin resolver."""
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")
    # La hora por parametro solo vale en pruebas: en produccion el plazo
    # se juzga con el reloj del servidor, en hora del pais del servicio.
    ahora = reloj.de_prueba(ahora)
    # El mes del implantado lleva su revision y su factura del mes;
    # lo de abajo es el eventual, sin cambios (seccion 56).
    if cierre.contrato_id:
        return cierre_mes.enviar_a_finanzas(db, cierre, usuario, ahora)

    # En hora del pais del servicio: de esta comparacion depende que el
    # consultor cobre su comision o la pierda.
    momento = reloj.ahora_del_servicio(db, cierre.servicio, ahora)

    # El reloj del sistema pudo no haber pasado todavia: si ya llego T1
    # --o todo el dinero ya cerro--, se avanza aqui mismo y se guarda,
    # pase lo que pase con la revision de abajo.
    if motor.avanzar(db, cierre, momento):
        db.commit()

    # Con la fila del cierre bloqueada hasta guardar (seccion 101): dos
    # "Dar visto bueno" en el mismo segundo --dos pestanas, o el
    # consultor y quien lo cubre-- leian los dos "sin visto bueno",
    # corrian los dos las diferencias de nomina y nacian dos ajustes por
    # la misma jornada y persona: la nomina siguiente pagaba la
    # correccion dos veces. El segundo espera a que el primero termine
    # y entonces ve "ya tiene visto bueno". Va despues de avanzar, que
    # guarda por su cuenta y soltaria el candado.
    cierre = motor.tomar(db, cierre_id)

    # Mientras corren las 24 h del personal, el visto bueno ni se abre:
    # no se le va a pedir al consultor que cierre con descuento un
    # dinero que su gente todavia tiene tiempo de comprobar. Y lo que ya
    # se envio no se envia dos veces.
    if cierre.estatus not in (m.EstatusCierre.SIN_VISTO_BUENO,
                              m.EstatusCierre.DEVUELTO_A_OPERACION):
        raise HTTPException(409, {
            "mensaje": ("Todavia corre la comprobacion de viaticos del personal"
                        if cierre.estatus == m.EstatusCierre.ABIERTO
                        else f"El cierre esta en "
                             f"{motor.nombre_estatus(cierre.estatus)}"),
            "hasta": (cierre.comprobacion_hasta.isoformat()
                      if cierre.comprobacion_hasta else None),
            "observaciones": [],
        })

    # Una cancelacion se manda con el cobro ya autorizado por direccion
    # de operaciones (seccion 105, decision 1): sin eso no hay cifra que
    # facturar, y la eleccion del consultor no es la ultima palabra.
    if motor.cobro_sin_autorizar(cierre):
        raise HTTPException(409, {
            "mensaje": (f"Falta que dirección de operaciones autorice el "
                        f"cobro de la cancelación (pediste "
                        f"{cierre.cobro})"),
            "que_hacer": "Pídele a dirección de operaciones que lo autorice "
                         "desde «Autorizar el cobro», en la tarjeta del "
                         "cierre. Mientras, el servicio espera.",
            "observaciones": [],
        })

    # Los gastos netos de una cotizacion en otra moneda se facturan al
    # tipo de cambio que esta puesto en el visto bueno (seccion 82): la
    # factura sale ahora. Se fija antes de la revision, para que lo que
    # ella compara sea lo que va a decir la factura. Si la revision no
    # deja mandarlo, no se guarda nada.
    motor.fijar_gastos_del_visto_bueno(db, cierre)

    revision = revisor.revisar(db, cierre.servicio_id, momento)

    if not revision["listo_para_finanzas"]:
        raise HTTPException(409, {
            "mensaje": "Hay puntos por corregir antes de enviar a finanzas",
            "observaciones": [o for o in revision["observaciones"]
                              if o["nivel"] == "corregir"],
        })

    comparativo = revision["comparativo"]
    cierre.total_cotizado = comparativo["cotizacion"]["total"]
    # Lo que se factura: lo ejecutado --o la cotizacion tal cual, en la
    # cancelacion que se cobra completa (seccion 105)-- y, si la
    # cotizacion cobra los viaticos aparte, lo comprobado (seccion 57).
    cierre.total_ejecutado = (comparativo["a_facturar"]["servicio"]
                              + comparativo["viaticos"]["facturable_al_cliente"])
    # El primer visto bueno juzga el plazo y se queda: si finanzas lo
    # regreso, este envio no lo vuelve a juzgar (decision 1, 23 sep).
    motor.dar_visto_bueno(cierre, momento)
    cierre.cerrado_por_id = usuario.persona_id
    # El visto bueno es el termino general: el servicio pasa a
    # facturacion. El cancelado se queda cancelado.
    if cierre.servicio.estatus in (m.EstatusServicio.TERMINADO,
                                   m.EstatusServicio.SIN_VISTO_BUENO):
        cierre.servicio.estatus = m.EstatusServicio.EN_FACTURACION

    moneda = comparativo.get("moneda") or ""
    auditoria.registrar(db, usuario, cierre.servicio, "enviar a finanzas",
                        f"cotizado {cierre.total_cotizado} {moneda}, "
                        f"ejecutado {cierre.total_ejecutado} {moneda}, "
                        f"{'en plazo' if cierre.dentro_de_plazo else 'FUERA DE PLAZO'}"
                        + (f", gastos al tipo de cambio "
                           f"{tipo_cambio.texto(cierre.tipo_cambio_gastos)}"
                           if cierre.tipo_cambio_gastos else ""))

    # Revision del periodo completo contra lo que ya se le pago al personal.
    # En eventuales atrapa el dia mal cargado que se corrigio despues del
    # pago; en implantados es el corte del mes, que siempre llega despues
    # de haber pagado varias semanas por adelantado.
    ajustes = nomina.diferencias_del_servicio(db, cierre.servicio_id,
                                              usuario.persona_id)
    if ajustes["ajustes_generados"]:
        auditoria.registrar(
            db, usuario, cierre.servicio, "ajustes de nomina",
            f"{len(ajustes['ajustes_generados'])} diferencias a la "
            f"siguiente nomina")
    db.commit()

    # Y a Odoo, en este momento: el visto bueno del consultor es el
    # termino general (decision de Salvador, 22 sep). Va despues del
    # commit a proposito: el envio ya quedo guardado y un Odoo caido no
    # lo deshace; el servicio se queda en la bandeja de por facturar
    # con el error a la vista y se reintenta desde ahi.
    factura = facturacion.enviar(db, cierre, usuario)
    db.commit()

    return {"resultado": "enviado a finanzas", "cierre_id": cierre.id,
            "factura": factura,
            "dentro_de_plazo": cierre.dentro_de_plazo,
            "comision_consultor": "se detona con la validacion de finanzas"
                                  if cierre.dentro_de_plazo
                                  else "se pierde por cierre fuera de plazo",
            "ajustes_de_nomina": ajustes["ajustes_generados"]}


@router.post("/cierre/{cierre_id}/autorizar-cobro",
             summary="Operaciones autoriza como se cobra una cancelacion")
def autorizar_cobro(cierre_id: int, datos: CobroIn,
                    db: Session = Depends(get_db),
                    ahora: datetime | None = None,
                    usuario: m.Usuario = Depends(AUTORIZA_COBRO)):
    """Completo --la cotizacion autorizada tal cual-- o ejecutado, sobre
    el cierre de un servicio cancelado (seccion 105, decision 1). Puede
    cambiar lo que pidio el consultor, con nota. Queda en la bitacora del
    servicio y al consultor le llega por correo y al telefono; hasta
    entonces el cierre no se manda a finanzas."""
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")
    # La hora por parametro solo vale en pruebas (seccion 99).
    resultado = motor.autorizar_cobro(db, cierre, datos.cobro, datos.nota,
                                      usuario, reloj.de_prueba(ahora))
    return {**resultado,
            "cierre": motor_comisiones.solo_la_suya(
                motor.estado(db, cierre.servicio_id), usuario)}


@router.post("/cierre/{cierre_id}/devolver",
             summary="Finanzas regresa el servicio a operacion")
def devolver(cierre_id: int, datos: DevolucionIn, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(FINANZAS)):
    """Solo lo que esta en facturacion, con su motivo. El consultor tiene
    24 horas desde el regreso y su primer visto bueno conserva su plazo;
    si la factura ya habia salido, se anula (seccion 59)."""
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")
    return motor.regresar(db, cierre, datos.motivo, usuario)


@router.post("/cierre/{cierre_id}/aprobar",
             summary="Finanzas valida y factura")
def aprobar(cierre_id: int, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(FINANZAS)):
    """La comision del consultor se detona con el cierre validado por finanzas
    dentro de las 24 horas, no con el cierre simplemente capturado."""
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")
    if cierre.estatus != m.EstatusCierre.ENVIADO_FINANZAS:
        raise HTTPException(409, {
            "mensaje": (f"Solo se aprueba lo que esta en facturacion; este "
                        f"esta en {motor.nombre_estatus(cierre.estatus)}")})
    # Sin porcentaje de comision en su pais, se dice antes de guardar
    # nada (seccion 91): antes quedaba aprobado a medias.
    falta = motor_comisiones.sin_porcentaje(db, cierre.servicio)
    if falta:
        raise HTTPException(409, falta)
    # El mes del implantado: se aprueba el mes, el servicio sigue vivo
    # y la comision es de ese mes (seccion 56).
    if cierre.contrato_id:
        return cierre_mes.aprobar(db, cierre, usuario)

    cierre.estatus = m.EstatusCierre.APROBADO
    # En hora del pais del servicio, como el resto del cierre (seccion
    # 101): de esta fecha salen el mes de la comision, el del historial
    # y "Cerrados del mes". Con la del servidor, una aprobacion de Brasil
    # entre las 21:00 y las 23:59 de Mexico del ultimo dia del mes caia
    # en el mes anterior.
    cierre.aprobado_en = reloj.ahora_del_servicio(db, cierre.servicio)
    cierre.aprobado_por_id = usuario.persona_id
    # El cancelado se queda cancelado: cierra su expediente, no cambia
    # de estatus.
    if cierre.servicio.estatus != m.EstatusServicio.CANCELADO:
        cierre.servicio.estatus = m.EstatusServicio.CERRADO

    auditoria.registrar(db, usuario, cierre.servicio, "aprobar cierre",
                        "validado por finanzas")
    db.commit()

    comision = None
    if cierre.servicio.consultor_id:
        c = motor_comisiones.generar(db, cierre.servicio_id)
        comision = {"comision_id": c.id, "consultor": c.consultor.nombre,
                    "base": c.base, "porcentaje": float(c.porcentaje),
                    "monto": c.monto, "estatus": c.estatus.value,
                    "motivo": c.motivo}

    # La factura salio con el visto bueno del consultor. Aqui solo se
    # reintenta si aquel envio fallo y, si ya esta, el cierre pasa a
    # facturado. Va despues del commit a proposito: el cierre ya quedo
    # aprobado y la comision ya se genero; si Odoo no contesta, eso no
    # se deshace y el servicio sigue en la bandeja de por facturar. La
    # prefactura (seccion 117) que nunca se intento --visto bueno de antes
    # de la llave-- no sale aqui: la manda finanzas si toca.
    factura = facturacion.enviar(db, cierre, usuario, primera_vez=False)
    db.commit()

    return {"resultado": "aprobado", "cierre_id": cierre.id,
            "comision_consultor": comision,
            "factura": factura,
            "rentabilidad": motor.rentabilidad(db, cierre.servicio_id)}


@router.get("/cierre/por-facturar",
            summary="Lo aprobado que todavia no tiene factura")
def pendientes_de_factura(db: Session = Depends(get_db), _=Depends(LECTURA)):
    """Sin esta lista, un servicio aprobado cuyo envio fallo se queda
    esperando para siempre y nadie se entera hasta que el cliente no
    paga."""
    return {"por_facturar": facturacion.por_facturar(db),
            "odoo_configurado": facturacion.hay_conexion()}


@router.put("/cierre/{cierre_id}/factura-de-odoo",
            summary="Anotar la factura que se hizo en Odoo")
def anotar_factura(cierre_id: int, datos: FacturaDeOdooIn,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(FINANZAS)):
    """Mientras la factura no se conecta con Odoo, finanzas la hace alla
    y aqui anota su folio y su fecha (seccion 96). La misma ruta corrige
    la que se anoto a mano; la que llego de Odoo se corrige en Odoo."""
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")
    fila = facturacion.anotar(db, cierre, datos.folio, datos.fecha, usuario)
    db.commit()
    return fila


@router.post("/cierre/{cierre_id}/revisar-en-odoo",
             summary="Volver a mirar en Odoo la prefactura de un cierre")
def revisar_en_odoo(cierre_id: int, db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(FINANZAS)):
    """«Volver a revisar en Odoo» (seccion 127): si el facturista cancelo
    o borro el borrador, Connect lo suelta y la vuelta de cada hora manda
    otro; si ya esta timbrado, lo dice para que finanzas lo anote; si
    sigue en borrador, no cambia nada."""
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")
    resultado = odoo_facturacion.revisar_en_odoo(db, cierre)
    if resultado["resultado"] in ("cancelada", "borrada"):
        auditoria.registrar(
            db, usuario, cierre.servicio, "prefactura revisada en odoo",
            resultado["motivo"][:400])
    db.commit()
    return resultado


@router.post("/cierre/{cierre_id}/facturar",
             summary="Reintentar el envio de la factura a Odoo")
def facturar(cierre_id: int, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(FINANZAS)):
    """El mismo envio de la aprobacion, a mano. Sirve para el dia que
    Odoo estaba caido, y para el primer envio cuando la conexion se
    configura despues. Con la llave de la factura (seccion 117) manda la
    prefactura en borrador, sin duplicar: tambien la de lo que tuvo su
    visto bueno antes de la llave, que no sale sola."""
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")

    resultado = facturacion.enviar(db, cierre, usuario)
    if resultado["resultado"] == "facturado":
        auditoria.registrar(db, usuario, cierre.servicio, "facturar",
                            f"factura {cierre.factura_odoo} en Odoo")
    db.commit()
    return resultado

"""Cotizacion, cierre del servicio, comparativo y rentabilidad."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auditoria, auth
from app import facturacion
from app import encuestas as motor_encuestas
from app import nomina
from app import cierre as motor
from app import cotizacion as cotmotor
from app import models as m
from app import comisiones as motor_comisiones
from app import reloj
from app import revisor
from app.db import get_db

router = APIRouter(tags=["Cierre y cotizacion"])

# Cotizar no es cerrar: lo primero le pone precio al servicio y lo
# segundo lo manda a facturar. `DIRECCION` se fue porque no la usaba
# ningun endpoint: era un alias muerto.
COTIZA = auth.puede("cierre.cotizar")
CONSULTOR = auth.puede("cierre.cerrar")
FINANZAS = auth.puede("cierre.facturar")
LECTURA = auth.puede("cierre.ver")


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


class RespaldoIn(BaseModel):
    justificacion: str


class DevolucionIn(BaseModel):
    motivo: str


# ---------------------------------------------------------------- cotizacion

@router.post("/cotizaciones", status_code=201, summary="Generar cotizacion")
def cotizar(datos: CotizacionIn, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(CONSULTOR)):
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
              usuario: m.Usuario = Depends(CONSULTOR)):
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
    cotizaciones = (db.query(m.Cotizacion).filter_by(servicio_id=servicio_id)
                    .order_by(m.Cotizacion.version).all())
    return [{
        "id": c.id, "version": c.version, "estatus": c.estatus.value,
        "total": c.total, "moneda": c.moneda.value,
        "viaticos_incluidos": c.viaticos_incluidos,
        "motivo_recotizacion": c.motivo_recotizacion,
        "autorizada_por": c.autorizada_por,
        "lineas": [{"fecha": l.fecha.isoformat(), "equipo": l.equipo_clave,
                    "tipo": l.tipo.value, "descripcion": l.descripcion,
                    "cantidad": l.cantidad, "precio": l.precio_unitario,
                    "subtotal": l.subtotal} for l in c.lineas],
    } for c in cotizaciones]


# ---------------------------------------------------------------- cierre

@router.post("/cierre/servicio/{servicio_id}/abrir",
             summary="Arrancar las 24 horas del consultor")
def abrir(servicio_id: int, db: Session = Depends(get_db),
          abierto_en: datetime | None = None,
          usuario: m.Usuario = Depends(CONSULTOR)):
    """Devuelve el cierre del servicio, abriendolo si hiciera falta.

    Desde que el cierre se abre solo al terminar el ultimo dia, esto casi
    siempre devuelve el que ya existe. Se deja porque hay dos casos que
    no pasan por ahi: el dia que se cierra a mano y el servicio que
    quedo abierto de antes.

    Ya no recibe `idioma`. Las encuestas salen al terminar el servicio,
    cada una en el idioma de quien la va a contestar --el principal en
    el suyo, el solicitante en el del pais--, y cuando esto corre ya
    estan creadas: el parametro no cambiaba nada y decia que si.
    """
    c = motor.abrir(db, servicio_id, abierto_en)
    # Por si el servicio se cerro a mano y nunca paso por el motor.
    motor_encuestas.generar(db, servicio_id)
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
                      ahora: datetime | None = None, _=Depends(LECTURA)):
    """La pantalla lo pide aparte porque la revision revienta cuando no
    hay cotizacion autorizada, y el plazo corre igual."""
    return motor.estado(db, servicio_id, ahora)


@router.get("/cierre/servicio/{servicio_id}/revision",
            summary="Revision automatica antes de enviar a finanzas")
def revision(servicio_id: int, db: Session = Depends(get_db),
             ahora: datetime | None = None, _=Depends(LECTURA)):
    """Acompana al consultor durante sus 24 horas y hace el primer filtro
    del comparativo para finanzas."""
    return revisor.revisar(db, servicio_id, ahora)


@router.post("/cierre/{cierre_id}/desviaciones/respaldar",
             summary="Justificar una desviacion detectada")
def respaldar(cierre_id: int, descripcion: str, datos: RespaldoIn,
              db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(CONSULTOR)):
    """Solo las desviaciones sin respaldo detonan el escalamiento."""
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")
    if len(datos.justificacion.strip()) < 15:
        raise HTTPException(400, "Explica la desviacion con mas detalle")

    db.add(m.Desviacion(cierre_id=cierre.id, tipo=m.TipoDesviacion.RECURSO_NO_COTIZADO,
                        descripcion=descripcion, respaldada=True,
                        justificacion=datos.justificacion,
                        detectada_por="consultor"))
    auditoria.registrar(db, usuario, cierre.servicio, "respaldar desviacion",
                        descripcion[:200])
    db.commit()
    return {"resultado": "respaldada", "descripcion": descripcion}


@router.post("/cierre/{cierre_id}/enviar-finanzas",
             summary="El consultor cierra y manda a facturar")
def enviar_finanzas(cierre_id: int, db: Session = Depends(get_db),
                    ahora: datetime | None = None,
                    usuario: m.Usuario = Depends(CONSULTOR)):
    """No se puede enviar con observaciones graves sin resolver."""
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")

    # En hora del pais del servicio: de esta comparacion depende que el
    # consultor cobre su comision o la pierda.
    momento = reloj.ahora_del_servicio(db, cierre.servicio, ahora)

    # El reloj del sistema pudo no haber pasado todavia: si ya llego T1
    # --o todo el dinero ya cerro--, se avanza aqui mismo y se guarda,
    # pase lo que pase con la revision de abajo.
    if motor.avanzar(db, cierre, momento):
        db.commit()

    # Mientras corren las 24 h del personal, el visto bueno ni se abre:
    # no se le va a pedir al consultor que cierre con descuento un
    # dinero que su gente todavia tiene tiempo de comprobar. Y lo que ya
    # se envio no se envia dos veces.
    if cierre.estatus not in (m.EstatusCierre.SIN_VISTO_BUENO,
                              m.EstatusCierre.DEVUELTO_A_OPERACION):
        raise HTTPException(409, {
            "mensaje": ("Todavia corre la comprobacion de viaticos del personal"
                        if cierre.estatus == m.EstatusCierre.ABIERTO
                        else f"El cierre esta en {cierre.estatus.value}"),
            "hasta": (cierre.comprobacion_hasta.isoformat()
                      if cierre.comprobacion_hasta else None),
            "observaciones": [],
        })

    revision = revisor.revisar(db, cierre.servicio_id, momento)

    if not revision["listo_para_finanzas"]:
        raise HTTPException(409, {
            "mensaje": "Hay puntos por corregir antes de enviar a finanzas",
            "observaciones": [o for o in revision["observaciones"]
                              if o["nivel"] == "corregir"],
        })

    comparativo = revision["comparativo"]
    cierre.total_cotizado = comparativo["cotizacion"]["total"]
    cierre.total_ejecutado = comparativo["ejecutado"]["total"]
    cierre.estatus = m.EstatusCierre.ENVIADO_FINANZAS
    cierre.enviado_en = momento
    cierre.cerrado_por_id = usuario.persona_id
    cierre.dentro_de_plazo = momento <= cierre.limite_consultor
    # El visto bueno es el termino general: el servicio pasa a
    # facturacion. El cancelado se queda cancelado.
    if cierre.servicio.estatus in (m.EstatusServicio.TERMINADO,
                                   m.EstatusServicio.SIN_VISTO_BUENO):
        cierre.servicio.estatus = m.EstatusServicio.EN_FACTURACION

    auditoria.registrar(db, usuario, cierre.servicio, "enviar a finanzas",
                        f"cotizado {cierre.total_cotizado}, "
                        f"ejecutado {cierre.total_ejecutado}, "
                        f"{'en plazo' if cierre.dentro_de_plazo else 'FUERA DE PLAZO'}")

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
    factura = facturacion.enviar(db, cierre)
    db.commit()

    return {"resultado": "enviado a finanzas", "cierre_id": cierre.id,
            "factura": factura,
            "dentro_de_plazo": cierre.dentro_de_plazo,
            "comision_consultor": "se detona con la validacion de finanzas"
                                  if cierre.dentro_de_plazo
                                  else "se pierde por cierre fuera de plazo",
            "ajustes_de_nomina": ajustes["ajustes_generados"]}


@router.post("/cierre/{cierre_id}/devolver",
             summary="Finanzas regresa el servicio a operacion")
def devolver(cierre_id: int, datos: DevolucionIn, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(FINANZAS)):
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")
    cierre.estatus = m.EstatusCierre.DEVUELTO_A_OPERACION
    cierre.devuelto_motivo = datos.motivo
    # Vuelve al consultor: el servicio regresa a sin visto bueno.
    if cierre.servicio.estatus == m.EstatusServicio.EN_FACTURACION:
        cierre.servicio.estatus = m.EstatusServicio.SIN_VISTO_BUENO
    auditoria.registrar(db, usuario, cierre.servicio, "devolver a operacion",
                        datos.motivo)
    db.commit()
    return {"resultado": "devuelto a operacion", "motivo": datos.motivo}


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
        raise HTTPException(409, f"El cierre esta en {cierre.estatus.value}")

    cierre.estatus = m.EstatusCierre.APROBADO
    cierre.aprobado_en = datetime.now()
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
    # se deshace y el servicio sigue en la bandeja de por facturar.
    factura = facturacion.enviar(db, cierre)
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


@router.post("/cierre/{cierre_id}/facturar",
             summary="Reintentar el envio de la factura a Odoo")
def facturar(cierre_id: int, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(FINANZAS)):
    """El mismo envio de la aprobacion, a mano. Sirve para el dia que
    Odoo estaba caido, y para el primer envio cuando la conexion se
    configura despues."""
    cierre = db.get(m.Cierre, cierre_id)
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")

    resultado = facturacion.enviar(db, cierre)
    if resultado["resultado"] == "facturado":
        auditoria.registrar(db, usuario, cierre.servicio, "facturar",
                            f"factura {cierre.factura_odoo} en Odoo")
    db.commit()
    return resultado

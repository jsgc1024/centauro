"""Cotizacion, cierre del servicio, comparativo y rentabilidad."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auditoria, auth
from app import bolson
from app import desglose
from app import facturacion
from app import encuestas as motor_encuestas
from app import nomina
from app import cierre as motor
from app import cierre_mes
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
# Quien trae dinero encima y cuanto no lo ve cualquiera: la misma puerta
# que el panel de viaticos del equipo.
DINERO = auth.puede("viaticos.ver")


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
    return {"momento": ahora.isoformat(),
            "personas": bolson.revision(viaticos, ahora)}


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
    moneda = (vigente.moneda.value if vigente else
              pais.moneda_local.value if pais else None)
    return HTMLResponse(desglose.render(
        servicio, plaza.nombre if plaza else None,
        motor.viaticos_del_servicio(db, servicio_id),
        idioma if idioma in desglose.TEXTOS
        else desglose.idioma_del_cliente(db, servicio),
        moneda, factura=cierre.factura_odoo if cierre else None))


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

    revision = revisor.revisar(db, cierre.servicio_id, momento)

    if not revision["listo_para_finanzas"]:
        raise HTTPException(409, {
            "mensaje": "Hay puntos por corregir antes de enviar a finanzas",
            "observaciones": [o for o in revision["observaciones"]
                              if o["nivel"] == "corregir"],
        })

    comparativo = revision["comparativo"]
    cierre.total_cotizado = comparativo["cotizacion"]["total"]
    # Lo que se factura: lo ejecutado y, si la cotizacion cobra los
    # viaticos aparte, lo comprobado (seccion 57).
    cierre.total_ejecutado = (comparativo["ejecutado"]["total"]
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
    # El mes del implantado: se aprueba el mes, el servicio sigue vivo
    # y la comision es de ese mes (seccion 56).
    if cierre.contrato_id:
        return cierre_mes.aprobar(db, cierre, usuario)

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

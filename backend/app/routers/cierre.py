"""Cotizacion, cierre del servicio, comparativo y rentabilidad."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auditoria, auth
from app import encuestas as motor_encuestas
from app import nomina
from app import cierre as motor
from app import cotizacion as cotmotor
from app import models as m
from app import comisiones as motor_comisiones
from app import revisor
from app.db import get_db

router = APIRouter(tags=["Cierre y cotizacion"])

CONSULTOR = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES)
FINANZAS = auth.requiere(m.Rol.FINANZAS)
DIRECCION = auth.requiere(m.Rol.DIRECTOR_OPERACIONES, m.Rol.DIRECTOR_GENERAL)
LECTURA = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES,
                        m.Rol.FINANZAS, m.Rol.CENTRAL)


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
          abierto_en: datetime | None = None, idioma: str = "en",
          usuario: m.Usuario = Depends(CONSULTOR)):
    c = motor.abrir(db, servicio_id, abierto_en)
    # El servicio termino: es el momento de preguntar, mientras el
    # ejecutivo todavia lo tiene fresco.
    enviadas = motor_encuestas.generar(db, servicio_id, idioma)
    db.commit()
    return {"cierre_id": c.id, "abierto_en": c.abierto_en.isoformat(),
            "limite_consultor": c.limite_consultor.isoformat(),
            "estatus": c.estatus.value,
            "encuestas_enviadas": [e.tipo.value for e in enviadas]}


@router.get("/cierre/servicio/{servicio_id}/comparativo",
            summary="Cotizado contra ejecutado")
def comparativo(servicio_id: int, db: Session = Depends(get_db), _=Depends(LECTURA)):
    return motor.comparar(db, servicio_id)


@router.get("/cierre/servicio/{servicio_id}/rentabilidad",
            summary="Rentabilidad del servicio")
def rentabilidad(servicio_id: int, db: Session = Depends(get_db),
                 _=Depends(auth.requiere(m.Rol.CONSULTOR, m.Rol.FINANZAS,
                                         m.Rol.DIRECTOR_OPERACIONES))):
    """Facturacion, costo de personal y viaticos, y costo del vehiculo."""
    return motor.rentabilidad(db, servicio_id)


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

    momento = ahora or datetime.now()
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

    return {"resultado": "enviado a finanzas", "cierre_id": cierre.id,
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

    return {"resultado": "aprobado", "cierre_id": cierre.id,
            "comision_consultor": comision,
            "rentabilidad": motor.rentabilidad(db, cierre.servicio_id)}

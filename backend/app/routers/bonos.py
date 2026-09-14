"""Incidencias, estrellas del personal y comisiones del consultor."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auditoria, auth
from app import bonos as motor
from app import comisiones as motor_com
from app import models as m
from app.db import get_db

router = APIRouter(tags=["Bonos y comisiones"])

CONSULTOR = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES)
DIR_OPERACIONES = auth.requiere(m.Rol.DIRECTOR_OPERACIONES)
DIR_GENERAL = auth.requiere(m.Rol.DIRECTOR_GENERAL)
RRHH = auth.requiere(m.Rol.DIRECTOR_OPERACIONES, m.Rol.FINANZAS)
LECTURA = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES,
                        m.Rol.FINANZAS, m.Rol.CENTRAL)


class IncidenciaIn(BaseModel):
    persona_id: int
    fecha: date
    gravedad: m.GravedadIncidencia
    descripcion: str
    servicio_id: int | None = None
    jornada_id: int | None = None


class VistoBuenoIn(BaseModel):
    autorizar: bool
    resolucion: str


class EvaluarIn(BaseModel):
    persona_id: int
    anio: int
    mes: int
    capacitacion_cumplida: bool = False


class ResolucionIn(BaseModel):
    se_paga: bool
    resolucion: str


class NoCobroIn(BaseModel):
    anio: int
    mes: int
    motivo: str


# ---------------------------------------------------------------- incidencias

@router.post("/incidencias", status_code=201,
             summary="El consultor clasifica una incidencia")
def crear_incidencia(datos: IncidenciaIn, db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(CONSULTOR)):
    """La clasificacion la define el consultor, pero no impacta el bono
    hasta que el director de operaciones le da el visto bueno."""
    persona = db.get(m.Persona, datos.persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {datos.persona_id}")
    if len(datos.descripcion.strip()) < 15:
        raise HTTPException(400, "Describe la incidencia con mas detalle")

    incidencia = m.Incidencia(**datos.model_dump(),
                              clasificada_por_id=usuario.persona_id)
    db.add(incidencia)
    db.commit()
    db.refresh(incidencia)

    efecto = {
        m.GravedadIncidencia.ERROR_MENOR:
            "Retroalimentacion documentada. No afecta las estrellas del mes.",
        m.GravedadIncidencia.LEVE:
            "Si se autoriza, quita todas las estrellas del mes.",
        m.GravedadIncidencia.GRAVE:
            "Si se autoriza, quita todas las estrellas y lo gestiona Recursos "
            "Humanos. Puede derivar en baja.",
    }[incidencia.gravedad]

    return {"incidencia_id": incidencia.id, "persona": persona.nombre,
            "gravedad": incidencia.gravedad.value, "autorizada": False,
            "efecto_si_se_autoriza": efecto,
            "siguiente_paso": "Requiere visto bueno del director de operaciones"}


@router.post("/incidencias/{incidencia_id}/visto-bueno",
             summary="El director de operaciones autoriza o descarta")
def visto_bueno(incidencia_id: int, datos: VistoBuenoIn,
                db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(DIR_OPERACIONES)):
    incidencia = db.get(m.Incidencia, incidencia_id)
    if not incidencia:
        raise HTTPException(404, f"No existe la incidencia {incidencia_id}")
    if len(datos.resolucion.strip()) < 10:
        raise HTTPException(400, "Registra la resolucion")

    incidencia.autorizada = datos.autorizar
    incidencia.visto_bueno_por_id = usuario.persona_id
    incidencia.resolucion_direccion = datos.resolucion
    db.commit()

    return {"resultado": "autorizada" if datos.autorizar else "descartada",
            "incidencia_id": incidencia.id,
            "nota": ("Ya impacta el bono del mes. Hay que recalcular la evaluacion."
                     if datos.autorizar else "No impacta el bono.")}


@router.get("/incidencias", summary="Incidencias registradas")
def listar_incidencias(db: Session = Depends(get_db), persona_id: int | None = None,
                       solo_pendientes: bool = False, _=Depends(LECTURA)):
    consulta = db.query(m.Incidencia)
    if persona_id:
        consulta = consulta.filter_by(persona_id=persona_id)
    if solo_pendientes:
        consulta = consulta.filter(m.Incidencia.visto_bueno_por_id.is_(None))
    return [{"id": i.id, "persona": i.persona.nombre, "fecha": i.fecha.isoformat(),
             "gravedad": i.gravedad.value, "descripcion": i.descripcion,
             "autorizada": i.autorizada,
             "pendiente_visto_bueno": i.visto_bueno_por_id is None}
            for i in consulta.order_by(m.Incidencia.id.desc()).all()]


# ---------------------------------------------------------------- estrellas

@router.post("/evaluaciones", summary="Calcular las estrellas del mes")
def evaluar(datos: EvaluarIn, db: Session = Depends(get_db),
            _=Depends(CONSULTOR)):
    """Mensual y por persona: agrega todas sus jornadas del mes,
    de servicios eventuales e implantados."""
    evaluacion = motor.evaluar(db, datos.persona_id, datos.anio, datos.mes,
                               datos.capacitacion_cumplida)
    return motor.ficha(db, evaluacion)


@router.get("/evaluaciones/{persona_id}/{anio}/{mes}",
            summary="Ver la evaluacion de una persona")
def ver_evaluacion(persona_id: int, anio: int, mes: int,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(auth.usuario_actual)):
    if usuario.rol == m.Rol.PERSONAL_SEGURIDAD and usuario.persona_id != persona_id:
        raise HTTPException(403, "Solo puedes ver tu propia evaluacion")
    evaluacion = (db.query(m.EvaluacionMensual)
                  .filter_by(persona_id=persona_id, anio=anio, mes=mes).first())
    if not evaluacion:
        raise HTTPException(404, "No hay evaluacion calculada para ese periodo")
    return motor.ficha(db, evaluacion)


@router.post("/evaluaciones/{evaluacion_id}/autorizar",
             summary="Autorizar el pago del bono")
def autorizar_bono(evaluacion_id: int, db: Session = Depends(get_db),
                   _=Depends(RRHH)):
    evaluacion = db.get(m.EvaluacionMensual, evaluacion_id)
    if not evaluacion:
        raise HTTPException(404, f"No existe la evaluacion {evaluacion_id}")
    evaluacion.estatus = m.EstatusEvaluacion.AUTORIZADA
    db.commit()
    return {"resultado": "autorizada", "bono": evaluacion.monto_bono}


# ---------------------------------------------------------------- comisiones

@router.post("/comisiones/servicio/{servicio_id}",
             summary="Generar la comision del consultor")
def generar_comision(servicio_id: int, db: Session = Depends(get_db),
                     _=Depends(auth.requiere(m.Rol.FINANZAS,
                                             m.Rol.DIRECTOR_OPERACIONES))):
    c = motor_com.generar(db, servicio_id)
    return {"comision_id": c.id, "consultor": c.consultor.nombre,
            "facturacion": c.facturacion, "viaticos_descontados": c.viaticos,
            "base": c.base, "porcentaje": float(c.porcentaje), "monto": c.monto,
            "estatus": c.estatus.value, "motivo": c.motivo}


@router.post("/comisiones/{comision_id}/resolver",
             summary="Direccion general decide una comision retenida")
def resolver(comision_id: int, datos: ResolucionIn, db: Session = Depends(get_db),
             _=Depends(DIR_GENERAL)):
    """En incidencia grave no hay regla automatica: la consecuencia
    para el consultor la evalua y decide el director general."""
    c = motor_com.resolver_retenida(db, comision_id, datos.se_paga, datos.resolucion)
    return {"resultado": c.estatus.value, "monto": c.monto, "motivo": c.motivo}


@router.post("/comisiones/{comision_id}/factura-no-cobrada",
             summary="Ajuste por factura no cobrada")
def no_cobrada(comision_id: int, datos: NoCobroIn, db: Session = Depends(get_db),
               _=Depends(auth.requiere(m.Rol.FINANZAS))):
    """Nota de credito o cancelacion: resta en el corte siguiente."""
    return motor_com.cancelar_por_no_cobro(db, comision_id, datos.anio,
                                           datos.mes, datos.motivo)


@router.get("/comisiones/corte/{consultor_id}/{anio}/{mes}",
            summary="Corte mensual del consultor")
def corte(consultor_id: int, anio: int, mes: int, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(LECTURA)):
    if usuario.rol == m.Rol.CONSULTOR and usuario.persona_id != consultor_id:
        raise HTTPException(403, "Solo puedes ver tu propio corte")
    return motor_com.corte_mensual(db, consultor_id, anio, mes)

"""Incidencias, estrellas del personal y comisiones del consultor."""
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auth
from app import bonos as motor
from app import comisiones as motor_com
from app import models as m
from app.db import get_db

router = APIRouter(tags=["Bonos y comisiones"])

CONSULTOR = auth.puede("bonos.incidencia")
DIR_OPERACIONES = auth.puede("bonos.visto_bueno")
DIR_GENERAL = auth.puede("comisiones.resolver")
RRHH = auth.puede("bonos.autorizar")
PAGA = auth.puede("bonos.pagar")
CONFIGURA = auth.puede("bonos.configurar")
LECTURA = auth.puede("bonos.ver")

CERO = Decimal("0")


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
    # Vacio no es reprobado: sin dato el criterio no aplica y su monto
    # se reparte. Mandar false es decir que NO la cumplio.
    capacitacion_cumplida: bool | None = None


class CriterioIn(BaseModel):
    monto_mensual: Decimal
    umbral_pct: Decimal
    tolerancia_minutos: int = 0
    tolerancia_ocasiones: int = 0
    reparte: bool = True
    activo: bool = True


class LoteIn(BaseModel):
    evaluacion_ids: list[int]


class PagoIn(BaseModel):
    referencia: str
    comprobante: str | None = None


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
    incidencia.visto_bueno_en = datetime.now(timezone.utc)
    incidencia.resolucion_direccion = datos.resolucion

    # El bono de ese mes puede estar cerrado ya. Si se autorizo o se
    # pago, esta incidencia llego tarde y NO lo toca: el dinero no se
    # recalcula. Se dice aqui, en la respuesta, porque quien acaba de
    # firmar necesita saber que su firma no bajo ningun bono --y con la
    # fecha del visto bueno queda demostrado que llego tarde, no que se
    # ignoro--.
    cerrada = None
    if datos.autorizar:
        cerrada = (db.query(m.EvaluacionMensual)
                   .filter(m.EvaluacionMensual.persona_id == incidencia.persona_id,
                           m.EvaluacionMensual.anio == incidencia.fecha.year,
                           m.EvaluacionMensual.mes == incidencia.fecha.month,
                           m.EvaluacionMensual.estatus.in_(
                               [m.EstatusEvaluacion.AUTORIZADA,
                                m.EstatusEvaluacion.PAGADA]))
                   .first())
    db.commit()

    if cerrada is not None:
        nota = (f"El bono de {incidencia.fecha:%m/%Y} ya esta "
                f"{cerrada.estatus.value}: esta incidencia no lo toca. "
                f"Queda asentada con su fecha de visto bueno.")
    elif datos.autorizar:
        nota = "Ya impacta el bono del mes. Hay que recalcular la evaluacion."
    else:
        nota = "No impacta el bono."

    return {"resultado": "autorizada" if datos.autorizar else "descartada",
            "incidencia_id": incidencia.id,
            "bono_ya_cerrado": cerrada is not None,
            "nota": nota}


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


def _autorizar(db: Session, evaluacion: m.EvaluacionMensual, usuario) -> None:
    """Autorizar congela el monto. De aqui en adelante es dinero, y el
    dinero no se recalcula: se corrige con un ajuste que deja rastro."""
    if evaluacion.estatus == m.EstatusEvaluacion.PAGADA:
        raise HTTPException(409, "Ese bono ya se pago")
    evaluacion.estatus = m.EstatusEvaluacion.AUTORIZADA
    evaluacion.autorizada_en = datetime.now(timezone.utc)
    evaluacion.autorizada_por_id = usuario.persona_id


@router.post("/evaluaciones/{evaluacion_id}/autorizar",
             summary="Autorizar el pago del bono")
def autorizar_bono(evaluacion_id: int, db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(RRHH)):
    evaluacion = db.get(m.EvaluacionMensual, evaluacion_id)
    if not evaluacion:
        raise HTTPException(404, f"No existe la evaluacion {evaluacion_id}")
    _autorizar(db, evaluacion, usuario)
    db.commit()
    return {"resultado": "autorizada", "bono": evaluacion.monto_bono}


@router.post("/evaluaciones/autorizar-lote",
             summary="Autorizar varios bonos de una vez")
def autorizar_lote(datos: LoteIn, db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(RRHH)):
    """Treinta y ocho personas al mes no se autorizan de una en una. Los
    que ya se pagaron no truenan el lote: se reportan aparte, porque
    quien aprieta el boton necesita saber cuales no entraron y por que."""
    autorizadas, ya_pagadas, total = [], [], CERO
    for evaluacion_id in datos.evaluacion_ids:
        evaluacion = db.get(m.EvaluacionMensual, evaluacion_id)
        if not evaluacion:
            raise HTTPException(404, f"No existe la evaluacion {evaluacion_id}")
        if evaluacion.estatus == m.EstatusEvaluacion.PAGADA:
            ya_pagadas.append(evaluacion.persona.nombre)
            continue
        _autorizar(db, evaluacion, usuario)
        autorizadas.append(evaluacion.id)
        total += Decimal(str(evaluacion.monto_bono))
    db.commit()
    return {"autorizadas": len(autorizadas), "total": total,
            "ya_pagadas": ya_pagadas}


# ---------------------------------------------------------------- criterios

@router.get("/criterios/{pais_id}",
            summary="Que se le mide al personal y cuanto vale")
def ver_criterios(pais_id: int, db: Session = Depends(get_db),
                  _=Depends(LECTURA)):
    criterios = (db.query(m.CriterioEstrella).filter_by(pais_id=pais_id)
                 .order_by(m.CriterioEstrella.monto_mensual.desc()).all())
    if not criterios:
        raise HTTPException(404, "No hay criterios configurados para ese pais")
    posible = sum((Decimal(str(c.monto_mensual)) for c in criterios if c.activo),
                  CERO)
    return {
        "pais_id": pais_id,
        "bono_posible": posible,
        "moneda": criterios[0].moneda.value,
        "criterios": [{
            "id": c.id,
            "codigo": c.codigo.value if hasattr(c.codigo, "value") else c.codigo,
            "nombre": c.nombre,
            "monto_mensual": c.monto_mensual,
            # El peso no se guarda: se lee del monto. Un solo numero que
            # mover, y dos que nunca se pueden contradecir.
            "peso_pct": (float((Decimal(str(c.monto_mensual)) / posible * 100)
                               .quantize(Decimal("0.1"))) if posible and c.activo
                         else 0.0),
            "umbral_pct": c.umbral_pct,
            "tolerancia_minutos": c.tolerancia_minutos,
            "tolerancia_ocasiones": c.tolerancia_ocasiones,
            "reparte": c.reparte,
            "activo": c.activo,
        } for c in criterios],
    }


@router.put("/criterios/{criterio_id}", summary="Cambiar lo que vale un criterio")
def guardar_criterio(criterio_id: int, datos: CriterioIn,
                     db: Session = Depends(get_db), _=Depends(CONFIGURA)):
    """Lo que cambie aqui aplica del mes en curso en adelante. Los meses
    ya autorizados no se recalculan --son dinero-- y el motor ni
    siquiera los mira: `evaluar` se niega sobre una evaluacion pagada."""
    criterio = db.get(m.CriterioEstrella, criterio_id)
    if not criterio:
        raise HTTPException(404, f"No existe el criterio {criterio_id}")
    if datos.monto_mensual < 0:
        raise HTTPException(400, "El monto no puede ser negativo")
    criterio.monto_mensual = datos.monto_mensual
    criterio.umbral_pct = datos.umbral_pct
    criterio.tolerancia_minutos = datos.tolerancia_minutos
    criterio.tolerancia_ocasiones = datos.tolerancia_ocasiones
    criterio.reparte = datos.reparte
    criterio.activo = datos.activo
    db.commit()
    return {"resultado": "guardado", "criterio_id": criterio.id}


# ----------------------------------------------------------- el mes y el pago

def _renglon(evaluacion: m.EvaluacionMensual) -> dict:
    pago = evaluacion.pago
    return {
        "evaluacion_id": evaluacion.id,
        "persona_id": evaluacion.persona_id,
        "persona": evaluacion.persona.nombre,
        "plaza": evaluacion.persona.plaza.nombre if evaluacion.persona.plaza else None,
        "jornadas": evaluacion.jornadas_evaluadas,
        "estrellas": evaluacion.estrellas,
        "estrellas_posibles": sum(1 for r in evaluacion.detalle if r.aplica),
        "bono": evaluacion.monto_bono,
        "moneda": evaluacion.moneda.value,
        "estatus": evaluacion.estatus.value,
        "anulado_por_incidencia": evaluacion.anulado_por_incidencia,
        "autorizada_en": (evaluacion.autorizada_en.isoformat()
                          if evaluacion.autorizada_en else None),
        "pago": ({"referencia": pago.referencia,
                  "pagado_en": pago.pagado_en.isoformat(),
                  "tiene_comprobante": bool(pago.comprobante)} if pago else None),
    }


def _evaluaciones(db: Session, pais_id: int, anio: int, mes: int,
                  plaza_id: int | None = None):
    consulta = (db.query(m.EvaluacionMensual)
                .join(m.Persona, m.Persona.id == m.EvaluacionMensual.persona_id)
                .join(m.Plaza, m.Plaza.id == m.Persona.plaza_id)
                .filter(m.Plaza.pais_id == pais_id,
                        m.EvaluacionMensual.anio == anio,
                        m.EvaluacionMensual.mes == mes))
    if plaza_id:
        consulta = consulta.filter(m.Persona.plaza_id == plaza_id)
    return consulta.order_by(m.Persona.nombre).all()


@router.get("/mes/{pais_id}/{anio}/{mes}", summary="Quien gano que este mes")
def ver_mes(pais_id: int, anio: int, mes: int, plaza_id: int | None = None,
            db: Session = Depends(get_db), _=Depends(LECTURA)):
    evaluaciones = _evaluaciones(db, pais_id, anio, mes, plaza_id)
    renglones = [_renglon(e) for e in evaluaciones]
    completos = sum(1 for r in renglones
                    if r["estrellas_posibles"] and
                    r["estrellas"] == r["estrellas_posibles"])
    en_cero = sum(1 for r in renglones if Decimal(str(r["bono"])) == CERO)
    return {
        "periodo": f"{mes:02d}/{anio}",
        "evaluados": len(renglones),
        "bono_completo": completos,
        "bono_parcial": len(renglones) - completos - en_cero,
        "en_cero": en_cero,
        "por_autorizar": sum(
            (Decimal(str(r["bono"])) for r in renglones
             if r["estatus"] == m.EstatusEvaluacion.CALCULADA.value), CERO),
        "autorizado_sin_pagar": sum(
            (Decimal(str(r["bono"])) for r in renglones
             if r["estatus"] == m.EstatusEvaluacion.AUTORIZADA.value), CERO),
        "pagado": sum(
            (Decimal(str(r["bono"])) for r in renglones
             if r["estatus"] == m.EstatusEvaluacion.PAGADA.value), CERO),
        "personas": renglones,
    }


@router.get("/corte/{pais_id}/{anio}/{mes}",
            summary="Lo que finanzas tiene que pagar este mes")
def corte_de_finanzas(pais_id: int, anio: int, mes: int,
                      db: Session = Depends(get_db), _=Depends(LECTURA)):
    """La bandeja del dia 5. Solo lo autorizado: lo que sigue en
    calculada no es dinero todavia, y ponerlo aqui seria invitar a
    pagar un bono que nadie firmo.

    El bono va aparte de la nomina semanal a proposito: se paga el dia 5
    --o el primer habil despues-- y el corte semanal cae donde cae."""
    evaluaciones = [e for e in _evaluaciones(db, pais_id, anio, mes)
                    if e.estatus in (m.EstatusEvaluacion.AUTORIZADA,
                                     m.EstatusEvaluacion.PAGADA)]
    renglones = [_renglon(e) for e in evaluaciones
                 if Decimal(str(e.monto_bono)) > CERO]
    pendientes = [r for r in renglones if not r["pago"]]
    return {
        "periodo": f"{mes:02d}/{anio}",
        "por_pagar": len(pendientes),
        "monto_por_pagar": sum((Decimal(str(r["bono"])) for r in pendientes),
                               CERO),
        "pagados": len(renglones) - len(pendientes),
        "personas": renglones,
    }


@router.post("/evaluaciones/{evaluacion_id}/pagar",
             summary="Registrar el deposito del bono")
def pagar_bono(evaluacion_id: int, datos: PagoIn,
               db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(PAGA)):
    evaluacion = db.get(m.EvaluacionMensual, evaluacion_id)
    if not evaluacion:
        raise HTTPException(404, f"No existe la evaluacion {evaluacion_id}")
    if evaluacion.estatus == m.EstatusEvaluacion.PAGADA:
        raise HTTPException(409, "Ese bono ya se pago")
    if evaluacion.estatus != m.EstatusEvaluacion.AUTORIZADA:
        raise HTTPException(409, "Ese bono todavia no lo autoriza operaciones")
    if Decimal(str(evaluacion.monto_bono)) <= CERO:
        raise HTTPException(400, "Ese mes no genero bono: no hay que depositar")
    if not datos.referencia.strip():
        raise HTTPException(400, "Falta la referencia del banco")

    db.add(m.PagoBono(
        evaluacion_id=evaluacion.id,
        monto=evaluacion.monto_bono, moneda=evaluacion.moneda,
        referencia=datos.referencia.strip(), comprobante=datos.comprobante,
        pagado_por_id=usuario.persona_id))
    evaluacion.estatus = m.EstatusEvaluacion.PAGADA
    db.commit()
    return {"resultado": "pagado", "monto": evaluacion.monto_bono,
            "referencia": datos.referencia.strip()}


# ---------------------------------------------------------------- comisiones

@router.post("/comisiones/servicio/{servicio_id}",
             summary="Generar la comision del consultor")
def generar_comision(servicio_id: int, db: Session = Depends(get_db),
                     _=Depends(auth.puede("comisiones.generar"))):
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
               _=Depends(auth.puede("comisiones.ajustar"))):
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

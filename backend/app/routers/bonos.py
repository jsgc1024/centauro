"""Incidencias, estrellas del personal y comisiones del consultor."""
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import accesos, auditoria, auth
from app import bonos as motor
from app import comisiones as motor_com
from app import models as m
from app import reloj
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


# Los topes de lo que se teclea (seccion 101): un texto mas largo que su
# columna reventaba en la base, un umbral de 150 por ciento o una
# tolerancia negativa se guardaban y el bono se calculaba con eso.

class IncidenciaIn(BaseModel):
    persona_id: int
    fecha: date
    gravedad: m.GravedadIncidencia
    descripcion: str = Field(max_length=600)
    servicio_id: int | None = None
    jornada_id: int | None = None


class VistoBuenoIn(BaseModel):
    autorizar: bool
    resolucion: str = Field(max_length=600)


class EvaluarIn(BaseModel):
    persona_id: int
    # Con rango: un mes 13 o un ano de tres cifras reventaban al armar
    # la fecha del mes, con error del servidor en vez de 422.
    anio: int = Field(ge=2000, le=2100)
    mes: int = Field(ge=1, le=12)
    # Vacio no es reprobado: sin dato el criterio no aplica y su monto
    # se reparte. Mandar false es decir que NO la cumplio.
    capacitacion_cumplida: bool | None = None


class CriterioIn(BaseModel):
    monto_mensual: Decimal = Field(ge=0)
    umbral_pct: Decimal = Field(ge=0, le=100)
    tolerancia_minutos: int = Field(default=0, ge=0)
    tolerancia_ocasiones: int = Field(default=0, ge=0)
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
    # Sin anio ni mes: el mes del descuento lo pone el sistema --el que
    # siga abierto--, como en la diferencia a mano (seccion 101).
    motivo: str = Field(max_length=400)


# ---------------------------------------------------------------- incidencias

EFECTO_SI_SE_AUTORIZA = {
    m.GravedadIncidencia.ERROR_MENOR:
        "Retroalimentación documentada. No afecta las estrellas del mes.",
    m.GravedadIncidencia.LEVE:
        "Si se autoriza, quita todas las estrellas del mes.",
    m.GravedadIncidencia.GRAVE:
        "Si se autoriza, quita todas las estrellas, retiene la comisión del "
        "consultor y lo gestiona Recursos Humanos. Puede derivar en baja.",
}


@router.post("/incidencias", status_code=201,
             summary="Registrar una incidencia")
def crear_incidencia(datos: IncidenciaIn, db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(CONSULTOR)):
    """La registra el consultor del servicio --o quien lo cubre-- y
    tambien la central (decision 2 de Salvador, seccion 105), pero no
    impacta el bono hasta que el director de operaciones le da el visto
    bueno. Queda en la bitacora del servicio desde que se registra."""
    persona = db.get(m.Persona, datos.persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {datos.persona_id}")
    if len(datos.descripcion.strip()) < 15:
        raise HTTPException(400, "Describe la incidencia con mas detalle")
    # El servicio y el dia que no existen se dicen (seccion 101): antes
    # reventaban en la llave foranea, con un error que no decia cual.
    servicio = None
    if datos.servicio_id is not None:
        servicio = db.get(m.Servicio, datos.servicio_id)
        if not servicio:
            raise HTTPException(404, f"No existe el servicio {datos.servicio_id}")
    if datos.jornada_id is not None and not db.get(m.Jornada, datos.jornada_id):
        raise HTTPException(404, f"No existe la jornada {datos.jornada_id}")

    incidencia = m.Incidencia(**datos.model_dump(),
                              clasificada_por_id=usuario.persona_id)
    db.add(incidencia)
    db.flush()
    if servicio is not None:
        auditoria.registrar(
            db, usuario, servicio, "registrar incidencia",
            f"{persona.nombre}, {incidencia.gravedad.value}, "
            f"{incidencia.fecha:%d/%m/%Y}: {incidencia.descripcion}",
            jornada_id=datos.jornada_id)
    db.commit()
    db.refresh(incidencia)

    return {"incidencia_id": incidencia.id, "persona": persona.nombre,
            "gravedad": incidencia.gravedad.value, "autorizada": False,
            "efecto_si_se_autoriza": EFECTO_SI_SE_AUTORIZA[incidencia.gravedad],
            "siguiente_paso": "Requiere visto bueno del director de operaciones"}


@router.get("/incidencias/opciones/{servicio_id}",
            summary="Con que se llena el panel de registrar una incidencia")
def opciones_incidencia(servicio_id: int, db: Session = Depends(get_db),
                        _=Depends(CONSULTOR)):
    """La gente que va o fue en ese servicio --tambien los relevados--,
    el consultor titular, y los dias del servicio con el de hoy senalado
    (seccion 105). Es lo que el panel ofrece para no pedir numeros."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    hoy = reloj.hoy_en(db.get(m.Pais, servicio.pais_id))
    jornadas = (db.query(m.Jornada)
                .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                .filter(m.Equipo.servicio_id == servicio_id,
                        m.Jornada.estatus != m.EstatusJornada.CANCELADA)
                .order_by(m.Jornada.fecha.desc(), m.Jornada.id).all())
    personas: dict[int, dict] = {}
    for j in jornadas:
        for a in j.personal:
            fila = personas.setdefault(a.persona_id, {
                "persona_id": a.persona_id, "nombre": a.persona.nombre,
                "puesto": a.rol.nombre if a.rol else None, "dias": 0,
                "consultor": False})
            fila["dias"] += 1
    if servicio.consultor_id:
        titular = db.get(m.Persona, servicio.consultor_id)
        if titular:
            personas.setdefault(titular.id, {
                "persona_id": titular.id, "nombre": titular.nombre,
                "puesto": None, "dias": 0, "consultor": True})
    # Por omision el dia de hoy; si hoy no hay dia, el ultimo que paso.
    de_hoy = next((j for j in jornadas if j.fecha == hoy), None)
    pasado = next((j for j in jornadas if j.fecha <= hoy), None)
    propuesta = de_hoy or pasado or (jornadas[-1] if jornadas else None)
    return {
        "servicio_id": servicio.id, "folio": servicio.folio,
        "tipo": servicio.tipo.value, "hoy": hoy.isoformat(),
        "personas": sorted(personas.values(),
                           key=lambda p: (p["consultor"], p["nombre"])),
        "jornadas": [{"jornada_id": j.id, "fecha": j.fecha.isoformat(),
                      "equipo": j.equipo.alias, "estatus": j.estatus.value}
                     for j in jornadas],
        "jornada_propuesta": propuesta.id if propuesta else None,
    }


@router.post("/incidencias/{incidencia_id}/visto-bueno",
             summary="El director de operaciones autoriza o descarta")
def visto_bueno(incidencia_id: int, datos: VistoBuenoIn,
                db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(DIR_OPERACIONES)):
    """Autorizar es lo que le pega al bono y a la comision; descartar
    la deja en el expediente con su resolucion y no toca nada.

    Desde la seccion 105 la firma hace lo que antes solo pedia en una
    nota: recalcula el bono del mes si RRHH no lo ha autorizado, retiene
    la comision de la grave y le avisa a RRHH (`bonos.aplicar_visto_bueno`).
    Y una incidencia se firma una sola vez: la segunda firma pisaba la
    primera sin rastro y podia descartar lo que ya habia anulado un mes.
    """
    incidencia = db.get(m.Incidencia, incidencia_id)
    if not incidencia:
        raise HTTPException(404, f"No existe la incidencia {incidencia_id}")
    if len(datos.resolucion.strip()) < 10:
        raise HTTPException(400, "Registra la resolucion")
    if incidencia.visto_bueno_por_id is not None:
        raise HTTPException(409, {
            "mensaje": "Esa incidencia ya tiene visto bueno: quedó "
                       + ("autorizada" if incidencia.autorizada else "descartada")
                       + " y no se vuelve a firmar",
            "que_hacer": "Si hay que corregirla, regístrala otra vez con lo "
                         "que corresponda; la anterior se queda en el "
                         "expediente con su resolución."})

    incidencia.autorizada = datos.autorizar
    incidencia.visto_bueno_por_id = usuario.persona_id
    incidencia.visto_bueno_en = datetime.now(timezone.utc)
    incidencia.resolucion_direccion = datos.resolucion

    efecto = motor.aplicar_visto_bueno(db, incidencia)

    servicio = (db.get(m.Servicio, incidencia.servicio_id)
                if incidencia.servicio_id else None)
    if servicio is not None:
        auditoria.registrar(
            db, usuario, servicio,
            "autorizar incidencia" if datos.autorizar else "descartar incidencia",
            f"{incidencia.persona.nombre}, {incidencia.gravedad.value}, "
            f"{incidencia.fecha:%d/%m/%Y}: {datos.resolucion}",
            jornada_id=incidencia.jornada_id)
    db.commit()

    # La nota, en espanol para quien lee la API; la clave, para que la
    # consola lo diga en su idioma.
    periodo = f"{incidencia.fecha:%m/%Y}"
    if not datos.autorizar:
        nota, clave = "No impacta el bono ni la comisión.", "inc_vb_descartada"
    elif efecto["bono"] == "no_aplica":
        nota, clave = ("Error menor: retroalimentación documentada, no toca "
                       "las estrellas."), "inc_vb_error_menor"
    elif efecto["bono"] == "ya_autorizado":
        nota = (f"El bono de {periodo} ya está "
                f"{efecto['evaluacion']['estatus']}: la incidencia no lo toca "
                "y queda para el expediente.")
        clave = "inc_vb_ya_autorizado"
    elif efecto["bono"] == "recalculado":
        nota = f"El bono de {periodo} se volvió a calcular y queda en cero."
        clave = "inc_vb_recalculado"
    elif efecto["bono"] == "sin_evaluacion":
        nota = (f"El bono de {periodo} todavía no se calcula: cuando se "
                "calcule ya la va a tomar en cuenta.")
        clave = "inc_vb_sin_evaluacion"
    else:
        nota = (f"La incidencia quedó autorizada, pero el bono de {periodo} "
                f"no se pudo recalcular: {efecto.get('motivo')}")
        clave = "inc_vb_no_recalculado"

    return {"resultado": "autorizada" if datos.autorizar else "descartada",
            "incidencia_id": incidencia.id,
            "bono": efecto["bono"],
            "evaluacion": efecto["evaluacion"],
            "comisiones_retenidas": efecto["comisiones_retenidas"],
            "aviso_rrhh": efecto["aviso_rrhh"],
            # Se conserva para quien ya lo leia.
            "bono_ya_cerrado": efecto["bono"] == "ya_autorizado",
            "nota": nota, "clave": clave, "periodo": periodo,
            "anio": incidencia.fecha.year, "mes": incidencia.fecha.month}


@router.get("/incidencias", summary="Incidencias registradas")
def listar_incidencias(db: Session = Depends(get_db), persona_id: int | None = None,
                       servicio_id: int | None = None,
                       solo_pendientes: bool = False, _=Depends(LECTURA)):
    """Con quien la registro, quien la firmo y su resolucion (seccion
    105): la lista decia solo si estaba autorizada."""
    consulta = db.query(m.Incidencia)
    if persona_id:
        consulta = consulta.filter_by(persona_id=persona_id)
    if servicio_id:
        consulta = consulta.filter_by(servicio_id=servicio_id)
    if solo_pendientes:
        consulta = consulta.filter(m.Incidencia.visto_bueno_por_id.is_(None))
    return [motor.renglon_incidencia(db, i)
            for i in consulta.order_by(m.Incidencia.id.desc()).all()]


# ---------------------------------------------------------------- estrellas

def _si_o_no(valor) -> str | None:
    """Como se escribe un bool en la bitacora de administracion: la
    frase lo traduce ("si"/"no") al leerlo."""
    return None if valor is None else ("true" if valor else "false")


@router.post("/evaluaciones", summary="Calcular las estrellas del mes")
def evaluar(datos: EvaluarIn, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(CONSULTOR)):
    """Mensual y por persona: agrega todas sus jornadas del mes,
    de servicios eventuales e implantados.

    Una autorizada o pagada ya no se recalcula: el motor contesta 409.
    Y la capacitacion dicha a mano deja rastro en la bitacora de
    administracion con quien lo dijo (seccion 101): un bool que decide
    dinero entraba sin que quedara de quien fue.
    """
    antes = None
    if datos.capacitacion_cumplida is not None:
        previa = (db.query(m.EvaluacionMensual)
                  .filter_by(persona_id=datos.persona_id, anio=datos.anio,
                             mes=datos.mes).first())
        antes = previa.capacitacion_cumplida if previa else None
    evaluacion = motor.evaluar(db, datos.persona_id, datos.anio, datos.mes,
                               datos.capacitacion_cumplida)
    if datos.capacitacion_cumplida is not None:
        accesos.anotar(
            db, usuario, "capacitacion del bono a mano", "evaluacion_mensual",
            evaluacion.id, antes=_si_o_no(antes),
            despues=_si_o_no(datos.capacitacion_cumplida),
            detalle=f"{evaluacion.persona.nombre} {datos.mes:02d}/{datos.anio}")
        db.commit()
    return motor.ficha(db, evaluacion)


@router.get("/evaluaciones/{persona_id}/{anio}/{mes}",
            summary="Ver la evaluacion de una persona")
def ver_evaluacion(persona_id: int, anio: int, mes: int,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(auth.usuario_actual)):
    if usuario.rol == m.Rol.PERSONAL_SEGURIDAD:
        if usuario.persona_id != persona_id:
            raise HTTPException(403, "Solo puedes ver tu propia evaluacion")
    elif not auth.puede_el_usuario(db, usuario, "bonos.ver"):
        # Pedir sesion no es pedir permiso (seccion 99).
        raise HTTPException(403, {
            "mensaje": "Tu puesto no ve las evaluaciones del bono",
            "que_hacer": "Pide la actividad «ver bonos» a administracion."})
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
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(CONFIGURA)):
    """Lo que cambie aqui aplica del mes en curso en adelante. Los meses
    ya autorizados no se recalculan --son dinero-- y el motor ni
    siquiera los mira: `evaluar` se niega sobre una evaluacion pagada.

    Queda en la bitacora de administracion, como cualquier otro dinero
    (seccion 97): no se anotaba, y el arranque no podia saber si el bono
    ya tenia sus montos de verdad."""
    criterio = db.get(m.CriterioEstrella, criterio_id)
    if not criterio:
        raise HTTPException(404, f"No existe el criterio {criterio_id}")
    antes = _como_queda(criterio)
    criterio.monto_mensual = datos.monto_mensual
    criterio.umbral_pct = datos.umbral_pct
    criterio.tolerancia_minutos = datos.tolerancia_minutos
    criterio.tolerancia_ocasiones = datos.tolerancia_ocasiones
    criterio.reparte = datos.reparte
    criterio.activo = datos.activo
    despues = _como_queda(criterio)
    if despues != antes:
        accesos.anotar(db, usuario, "criterio del bono cambiado",
                       "criterio_estrella", criterio.id, antes=antes,
                       despues=despues, detalle=criterio.nombre)
    db.commit()
    return {"resultado": "guardado", "criterio_id": criterio.id}


def _como_queda(c: m.CriterioEstrella) -> str:
    """Lo que vale un criterio, en una linea para la bitacora."""
    return (f"{Decimal(str(c.monto_mensual)):.2f} {c.moneda.value}, umbral "
            f"{Decimal(str(c.umbral_pct)):.2f}, margen {c.tolerancia_minutos} min "
            f"x {c.tolerancia_ocasiones}, "
            f"{'reparte' if c.reparte else 'no reparte'}, "
            f"{'activo' if c.activo else 'inactivo'}")[:200]


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
    # El mes anulado por incidencia conserva sus estrellas y paga cero:
    # no es completo (seccion 89; antes contaba en completo y en cero a
    # la vez, y el parcial salia de menos).
    completos = sum(1 for r in renglones
                    if r["estrellas_posibles"]
                    and not r["anulado_por_incidencia"]
                    and r["estrellas"] == r["estrellas_posibles"])
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
def no_cobrada(comision_id: int, datos: NoCobroIn,
               ahora: datetime | None = None, db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(auth.puede("comisiones.ajustar"))):
    """Nota de credito o cancelacion: resta en el mes que siga abierto.
    Solo sobre una comision que se paga o ya se pago (seccion 101).
    `ahora` solo mueve el reloj en las pruebas."""
    return motor_com.cancelar_por_no_cobro(db, comision_id, datos.motivo,
                                           usuario, reloj.de_prueba(ahora))


@router.get("/comisiones/corte/{consultor_id}/{anio}/{mes}",
            summary="Corte mensual del consultor")
def corte(consultor_id: int, anio: int, mes: int, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(LECTURA)):
    if usuario.rol == m.Rol.CONSULTOR and usuario.persona_id != consultor_id:
        raise HTTPException(403, "Solo puedes ver tu propio corte")
    return motor_com.corte_mensual(db, consultor_id, anio, mes)

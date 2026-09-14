"""Asignacion, transferencia, comprobacion y cierre de viaticos."""
import base64
from datetime import date, datetime
from decimal import Decimal, ROUND_FLOOR

from fastapi import (APIRouter, Depends, File, HTTPException, Query,
                     Response, UploadFile)
from sqlalchemy.orm import Session

from app import auditoria
from app import auth
from app import imagenes
from app import models as m
from app import schemas as s
from app import finanzas as control
from app import viaticos as motor
from app.db import get_db

router = APIRouter(prefix="/viaticos", tags=["Viaticos"])

CONSULTOR = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES)
FINANZAS = auth.requiere(m.Rol.FINANZAS)
CAMPO = auth.requiere(m.Rol.PERSONAL_SEGURIDAD)
LECTURA = auth.requiere(m.Rol.CONSULTOR, m.Rol.DIRECTOR_OPERACIONES,
                        m.Rol.FINANZAS, m.Rol.CENTRAL)


def _obtener(db: Session, viatico_id: int) -> m.AsignacionViatico:
    obj = db.get(m.AsignacionViatico, viatico_id)
    if not obj:
        raise HTTPException(404, f"No existe la asignacion de viaticos {viatico_id}")
    return obj


def _recalcular_total(v: m.AsignacionViatico) -> None:
    v.monto_total = sum((Decimal(str(c.monto)) for c in v.conceptos), Decimal("0"))


# ---------------------------------------------------------------- asignacion

@router.get("/calcular", summary="Vista previa de viaticos segun el tabulador")
def calcular(jornada_id: int, persona_id: int, db: Session = Depends(get_db),
             _=Depends(CONSULTOR)):
    """Propone los montos. El consultor puede ajustarlos antes de asignar."""
    return motor.calcular(db, jornada_id, persona_id)


@router.post("/asignar", response_model=s.ViaticoOut, status_code=201,
             summary="Asignar viaticos a una persona en una jornada")
def asignar(datos: s.AsignarViaticoIn, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(CONSULTOR)):
    jornada = db.get(m.Jornada, datos.jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {datos.jornada_id}")

    existente = (db.query(m.AsignacionViatico)
                 .filter_by(jornada_id=datos.jornada_id, persona_id=datos.persona_id)
                 .first())
    if existente:
        raise HTTPException(409, {
            "mensaje": "Esa persona ya tiene viaticos asignados en esta jornada",
            "viatico_id": existente.id,
        })

    pais = db.get(m.Pais, jornada.equipo.servicio.pais_id)
    viatico = m.AsignacionViatico(
        jornada_id=datos.jornada_id,
        persona_id=datos.persona_id,
        escenario=motor.escenario_de(jornada),
        moneda=pais.moneda_local,
        asignado_por_id=datos.asignado_por_id,
    )
    db.add(viatico)
    db.flush()

    for c in datos.conceptos:
        db.add(m.ConceptoAsignado(asignacion_id=viatico.id, **c.model_dump()))
    db.flush()
    db.refresh(viatico)
    _recalcular_total(viatico)

    auditoria.registrar(db, usuario, jornada.equipo.servicio, "asignar viaticos",
                        f"{viatico.monto_total} {viatico.moneda.value} a "
                        f"{viatico.persona.nombre}", jornada_id=jornada.id)
    db.commit()
    db.refresh(viatico)
    return viatico


@router.get("/{viatico_id}", response_model=s.ViaticoOut, summary="Ver viaticos")
def ver(viatico_id: int, db: Session = Depends(get_db),
        _=Depends(auth.usuario_actual)):
    return _obtener(db, viatico_id)


@router.post("/{viatico_id}/adicional", response_model=s.ViaticoOut,
             summary="Solicitar viaticos adicionales")
def adicional(viatico_id: int, datos: s.AdicionalIn, db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(CONSULTOR)):
    """Puede ocurrir durante el servicio por situaciones extraordinarias,
    o en el ajuste del consultor cuando falto dinero."""
    v = _obtener(db, viatico_id)
    if v.estatus in (m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO):
        raise HTTPException(409, "Los viaticos ya estan cerrados")

    db.add(m.ConceptoAsignado(
        asignacion_id=v.id, concepto=datos.concepto, monto=datos.monto,
        descripcion=datos.descripcion, origen=m.OrigenMonto.MANUAL,
        es_adicional=True))
    auditoria.registrar(db, usuario, v.jornada.equipo.servicio, "viaticos adicionales",
                        f"{datos.monto} por {datos.concepto.value}",
                        jornada_id=v.jornada_id)
    db.flush()
    db.refresh(v)
    _recalcular_total(v)
    db.commit()
    db.refresh(v)
    return v


# ---------------------------------------------------------------- transferencia

@router.post("/{viatico_id}/solicitar-transferencia", response_model=s.TransferenciaOut,
             summary="Disparar la instruccion a finanzas")
def solicitar_transferencia(viatico_id: int, db: Session = Depends(get_db),
                            usuario: m.Usuario = Depends(CONSULTOR)):
    v = _obtener(db, viatico_id)
    pendiente = (db.query(m.SolicitudTransferencia)
                 .filter_by(asignacion_id=v.id,
                            estatus=m.EstatusTransferencia.PENDIENTE)
                 .first())
    if pendiente:
        return pendiente

    solicitud = m.SolicitudTransferencia(
        asignacion_id=v.id, monto=v.monto_total, moneda=v.moneda)
    db.add(solicitud)
    v.estatus = m.EstatusViatico.SOLICITADO
    auditoria.registrar(db, usuario, v.jornada.equipo.servicio,
                        "solicitar transferencia", f"{v.monto_total} {v.moneda.value}",
                        jornada_id=v.jornada_id)
    db.commit()
    db.refresh(solicitud)
    return solicitud


@router.get("/transferencias/ventana", summary="Cuando se dispara la transferencia")
def ventana(jornada_id: int, db: Session = Depends(get_db),
            _=Depends(LECTURA)):
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    return motor.ventana_de_transferencia(jornada.fecha)


@router.post("/transferencias/barrido", summary="Correr un barrido por lote")
def barrido(db: Session = Depends(get_db),
            lote: str | None = Query(None, description="Nombre del lote"),
            _=Depends(FINANZAS)):
    """Por el volumen de servicios en paralelo no se transfiere en tiempo real:
    se procesan ventanas y barridos por lote."""
    hoy = datetime.now()
    etiqueta = lote or f"LOTE-{hoy:%Y%m%d-%H%M}"

    pendientes = (db.query(m.SolicitudTransferencia)
                  .filter_by(estatus=m.EstatusTransferencia.PENDIENTE)
                  .all())

    enviadas = []
    for solicitud in pendientes:
        jornada = solicitud.asignacion.jornada
        cuando = motor.ventana_de_transferencia(jornada.fecha)
        if not cuando["inmediata"]:
            continue                       # todavia no toca su ventana
        solicitud.estatus = m.EstatusTransferencia.ENVIADA
        solicitud.lote = etiqueta
        solicitud.enviada_en = hoy
        enviadas.append({"solicitud_id": solicitud.id,
                         "persona": solicitud.asignacion.persona.nombre,
                         "monto": float(solicitud.monto),
                         "fecha_servicio": jornada.fecha.isoformat()})

    db.commit()
    return {"lote": etiqueta, "enviadas": len(enviadas),
            "pospuestas": len(pendientes) - len(enviadas), "detalle": enviadas}


@router.post("/transferencias/{solicitud_id}/confirmar",
             summary="Finanzas confirma el deposito")
def confirmar(solicitud_id: int, referencia_odoo: str | None = None,
              db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(FINANZAS)):
    solicitud = db.get(m.SolicitudTransferencia, solicitud_id)
    if not solicitud:
        raise HTTPException(404, f"No existe la solicitud {solicitud_id}")
    if solicitud.estatus == m.EstatusTransferencia.CONFIRMADA:
        raise HTTPException(409, {
            "mensaje": "Ese deposito ya estaba confirmado",
            "confirmada_en": (solicitud.confirmada_en.isoformat()
                              if solicitud.confirmada_en else None),
            "referencia_odoo": solicitud.referencia_odoo})

    solicitud.estatus = m.EstatusTransferencia.CONFIRMADA
    solicitud.referencia_odoo = referencia_odoo
    # La firma: cuando salio y quien lo despacho. Sin esto, en cuanto el
    # renglon sale de la bandeja la unica forma de saber si ya se pago
    # era preguntarle a la persona.
    solicitud.confirmada_en = datetime.now()
    solicitud.confirmada_por_id = usuario.persona_id
    solicitud.asignacion.estatus = m.EstatusViatico.TRANSFERIDO
    db.commit()
    return {"resultado": "confirmada", "solicitud_id": solicitud.id,
            "viatico_id": solicitud.asignacion_id,
            "nota": "Ya aparece en la app del personal como saldo disponible"}


# ---------------------------------------------------------------- comprobacion

@router.post("/{viatico_id}/comprobantes", response_model=s.ViaticoOut,
             summary="Subir comprobante desde la app")
def subir_comprobante(viatico_id: int, datos: s.ComprobanteIn,
                      db: Session = Depends(get_db),
                      usuario: m.Usuario = Depends(CAMPO)):
    """El personal puede ir subiendo comprobacion desde el dia uno del servicio."""
    v = _obtener(db, viatico_id)
    if v.persona_id != usuario.persona_id:
        raise HTTPException(403, "Solo puedes comprobar tus propios viaticos")
    if v.estatus in (m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO):
        raise HTTPException(409, "Los viaticos ya estan cerrados")

    db.add(m.Comprobante(asignacion_id=v.id, **datos.model_dump()))
    if v.estatus == m.EstatusViatico.TRANSFERIDO:
        v.estatus = m.EstatusViatico.EN_COMPROBACION
    db.flush()
    db.refresh(v)
    v.monto_comprobado = _comprobado(v)
    db.commit()
    db.refresh(v)
    return v


def _comprobado(v: m.AsignacionViatico) -> Decimal:
    """Lo rechazado no cuenta: ni como comprobado, ni como costo, ni se
    le cobra al cliente."""
    return sum((Decimal(str(c.monto)) for c in v.comprobantes
                if not c.rechazado), Decimal("0"))


@router.post("/{viatico_id}/rechazar-comprobante/{comprobante_id}",
             summary="El consultor rechaza un gasto que no aplica")
def rechazar_comprobante(viatico_id: int, comprobante_id: int, motivo: str,
                         db: Session = Depends(get_db),
                         usuario: m.Usuario = Depends(CONSULTOR)):
    """Un gasto que no corresponde al servicio deja de contar como
    comprobado. Eso abre una diferencia que el conductor tiene que cubrir,
    o que el consultor manda a descuento al cerrar."""
    v = _obtener(db, viatico_id)
    comprobante = next((c for c in v.comprobantes if c.id == comprobante_id), None)
    if not comprobante:
        raise HTTPException(404, "Ese comprobante no pertenece a esta asignacion")
    if v.estatus == m.EstatusViatico.CERRADO:
        raise HTTPException(409, "Los viaticos ya estan cerrados")

    comprobante.rechazado = True
    comprobante.validado = True          # revisado, aunque no aceptado
    comprobante.motivo_rechazo = motivo
    db.flush()
    db.refresh(v)
    v.monto_comprobado = _comprobado(v)

    auditoria.registrar(db, usuario, v.jornada.equipo.servicio,
                        "rechazar comprobante",
                        f"{comprobante.monto} de {comprobante.concepto.value}: {motivo}",
                        jornada_id=v.jornada_id)
    db.commit()
    db.refresh(v)
    pendiente = (Decimal(str(v.monto_total)) - Decimal(str(v.monto_comprobado))
                 - Decimal(str(v.monto_devuelto)))
    return {"resultado": "rechazado", "comprobante_id": comprobante_id,
            "monto_rechazado": float(comprobante.monto),
            "comprobado_ahora": float(v.monto_comprobado),
            "por_cubrir": float(pendiente)}


@router.post("/{viatico_id}/cerrar-con-descuento",
             summary="El consultor cierra por el conductor y manda a descuento")
def cerrar_con_descuento(viatico_id: int, datos: s.CierreConDescuentoIn,
                         db: Session = Depends(get_db),
                         usuario: m.Usuario = Depends(CONSULTOR)):
    """Cuando el conductor no puede resolver su comprobacion.

    Lo que quedo sin cubrir se le descuenta de su proxima nomina. El
    consultor puede decidir que la empresa absorba una parte, pero tiene
    que decir cuanto y por que: el descuento por omision es el total.
    """
    v = _obtener(db, viatico_id)
    if v.estatus == m.EstatusViatico.CERRADO:
        raise HTTPException(409, "Ya estaba cerrado")

    v.monto_comprobado = _comprobado(v)
    pendiente = (Decimal(str(v.monto_total)) - Decimal(str(v.monto_comprobado))
                 - Decimal(str(v.monto_devuelto)))
    if pendiente <= 0:
        raise HTTPException(409, {
            "mensaje": "No hay nada que descontar: use el cierre normal",
            "por_cubrir": float(pendiente)})

    descuento = (Decimal(str(datos.monto_descuento))
                 if datos.monto_descuento is not None else pendiente)
    if descuento < 0 or descuento > pendiente:
        raise HTTPException(409, {
            "mensaje": "El descuento no puede ser negativo ni mayor a lo pendiente",
            "por_cubrir": float(pendiente)})
    absorbido = pendiente - descuento
    if absorbido > 0 and not datos.motivo_absorcion:
        raise HTTPException(409,
                            "Si la empresa absorbe parte, hay que decir por que")

    servicio = v.jornada.equipo.servicio
    v.estatus = m.EstatusViatico.CERRADO
    v.cerrado_con_descuento = True
    v.monto_descontado = descuento
    v.monto_absorbido = absorbido
    v.motivo_cierre = datos.motivo
    v.cerrado_por_id = usuario.persona_id

    ajuste = None
    if descuento > 0:
        ajuste = m.AjusteNomina(
            persona_id=v.persona_id, pais_id=servicio.pais_id,
            servicio_id=servicio.id, jornada_id=v.jornada_id,
            monto=-descuento, creado_por_id=usuario.persona_id,
            motivo=(f"{servicio.folio} {v.jornada.fecha.isoformat()}: "
                    f"viaticos sin comprobar. {datos.motivo}"))
        db.add(ajuste)

    auditoria.registrar(
        db, usuario, servicio, "cierre de viaticos con descuento",
        f"descuento {descuento}" + (f", absorbido {absorbido}" if absorbido else "")
        + f": {datos.motivo}", jornada_id=v.jornada_id)
    db.commit()
    db.refresh(v)
    return {
        "resultado": "cerrado con descuento",
        "viatico_id": v.id,
        "asignado": float(v.monto_total),
        "comprobado": float(v.monto_comprobado),
        "descontado_al_personal": float(descuento),
        "absorbido_por_la_empresa": float(absorbido),
        "nota": ("El descuento entra en el proximo corte semanal de nomina. "
                 "Lo rechazado no se le cobra al cliente."),
    }


@router.post("/{viatico_id}/cerrar", summary="El consultor verifica y cierra")
def cerrar(viatico_id: int, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(CONSULTOR)):
    """Si falto dinero, el consultor solicita viaticos adicionales.
    Si sobro, se devuelve con comprobante."""
    v = _obtener(db, viatico_id)
    if v.estatus == m.EstatusViatico.CERRADO:
        raise HTTPException(409, "Ya estaba cerrado")

    asignado = Decimal(str(v.monto_total))
    comprobado = Decimal(str(v.monto_comprobado))
    devuelto = Decimal(str(v.monto_devuelto))
    diferencia = asignado - comprobado - devuelto

    sin_validar = [c.id for c in v.comprobantes if not c.validado]
    if sin_validar:
        raise HTTPException(409, {
            "mensaje": "Hay comprobantes sin validar",
            "comprobantes": sin_validar,
        })

    if diferencia > 0:
        return {"resultado": "pendiente",
                "mensaje": f"Sobran {diferencia} sin comprobar ni devolver",
                "accion": "Registrar la devolucion con su comprobante",
                "asignado": float(asignado), "comprobado": float(comprobado)}

    if diferencia < 0:
        return {"resultado": "pendiente",
                "mensaje": f"Falta cubrir {abs(diferencia)}",
                "accion": "Solicitar viaticos adicionales",
                "asignado": float(asignado), "comprobado": float(comprobado)}

    v.estatus = m.EstatusViatico.CERRADO
    auditoria.registrar(db, usuario, v.jornada.equipo.servicio, "cerrar viaticos",
                        f"asignado {asignado}, comprobado {comprobado}",
                        jornada_id=v.jornada_id)
    db.commit()
    return {"resultado": "cerrado", "viatico_id": v.id,
            "asignado": float(asignado), "comprobado": float(comprobado)}


@router.post("/{viatico_id}/validar-comprobante/{comprobante_id}",
             summary="El consultor valida un comprobante")
def validar_comprobante(viatico_id: int, comprobante_id: int,
                        observacion: str | None = None,
                        db: Session = Depends(get_db),
                        _=Depends(CONSULTOR)):
    v = _obtener(db, viatico_id)
    comprobante = next((c for c in v.comprobantes if c.id == comprobante_id), None)
    if not comprobante:
        raise HTTPException(404, "Ese comprobante no pertenece a esta asignacion")
    comprobante.validado = True
    comprobante.observacion = observacion
    db.commit()
    return {"resultado": "validado", "comprobante_id": comprobante_id}


@router.post("/{viatico_id}/devolver", summary="Registrar devolucion de dinero")
def devolver(viatico_id: int, monto: Decimal, archivo_url: str | None = None,
             db: Session = Depends(get_db),
             _=Depends(CONSULTOR)):
    """Si sobro dinero se devuelve con comprobante.
    Si el servicio se cancela despues de transferido, se devuelve todo."""
    v = _obtener(db, viatico_id)
    v.monto_devuelto = Decimal(str(v.monto_devuelto)) + monto
    db.add(m.Comprobante(
        asignacion_id=v.id, concepto=m.ConceptoViatico.OTROS,
        tipo=m.TipoComprobante.NOTA, monto=Decimal("0"),
        archivo_url=archivo_url, descripcion=f"Devolucion de {monto}",
        validado=True))
    db.commit()
    db.refresh(v)
    return {"resultado": "registrada", "monto_devuelto": float(v.monto_devuelto)}


@router.get("/jornada/{jornada_id}", response_model=list[s.ViaticoOut],
            summary="Viaticos de todas las personas de una jornada")
def por_jornada(jornada_id: int, db: Session = Depends(get_db),
                _=Depends(LECTURA)):
    return (db.query(m.AsignacionViatico)
            .filter_by(jornada_id=jornada_id).all())


# ================================================== viaticos por equipo

# El consultor no piensa en jornadas cuando reparte dinero: piensa en
# personas. "A Ramiro le deposito tres mil por los tres dias" es una sola
# decision y un solo deposito, aunque por dentro el viatico siga viviendo
# dia por dia —que es como se comprueba y como entra a la rentabilidad—.
# Todo lo de aqui traduce entre esas dos formas de verlo.

def _equipo(db: Session, equipo_id: int) -> m.Equipo:
    equipo = db.get(m.Equipo, equipo_id)
    if not equipo:
        raise HTTPException(404, f"No existe el equipo {equipo_id}")
    return equipo


def _dias_vivos(equipo: m.Equipo) -> list[m.Jornada]:
    return sorted([j for j in equipo.jornadas
                   if j.estatus != m.EstatusJornada.CANCELADA],
                  key=lambda j: j.fecha)


def _dias_de(persona_id: int, dias: list[m.Jornada]) -> list[m.Jornada]:
    return [j for j in dias
            if any(a.persona_id == persona_id for a in j.personal)]


def _rol_de(dias: list[m.Jornada], persona_id: int) -> str | None:
    """Con que rol va esa persona. El del primer dia: si cambio a media
    semana, lo que importa aqui es reconocerla en la lista."""
    for jornada in dias:
        for a in jornada.personal:
            if a.persona_id == persona_id and a.rol:
                return a.rol.nombre
    return None


# El semaforo que ve el consultor. Un solo color por persona, porque un
# deposito partido en cinco estados no le dice nada a nadie: lo que
# importa es si el dinero ya salio o todavia no.
POR_ASIGNAR = "por_asignar"      # gris: nadie ha dicho cuanto
ASIGNADO = "asignado"            # azul: hay monto, falta pedirlo
SOLICITADO = "solicitado"        # ambar: finanzas lo tiene
DEPOSITADO = "depositado"        # verde: el dinero ya esta con la persona

ADELANTADOS = (m.EstatusViatico.TRANSFERIDO, m.EstatusViatico.EN_COMPROBACION,
               m.EstatusViatico.CERRADO)

# Las solicitudes que siguen contando: la cancelada no le debe nada a
# nadie y no entra en ninguna suma.
VIVAS = (m.EstatusTransferencia.PENDIENTE, m.EstatusTransferencia.ENVIADA,
         m.EstatusTransferencia.CONFIRMADA)
EN_CAMINO = (m.EstatusTransferencia.PENDIENTE, m.EstatusTransferencia.ENVIADA)


def _solicitudes(db: Session, viaticos: list[m.AsignacionViatico]) -> list:
    if not viaticos:
        return []
    return (db.query(m.SolicitudTransferencia)
            .filter(m.SolicitudTransferencia.asignacion_id.in_(
                [v.id for v in viaticos]),
                m.SolicitudTransferencia.estatus.in_(VIVAS))
            .all())


def _dinero_de(db: Session, viaticos: list[m.AsignacionViatico]) -> dict:
    """Como va el dinero de una persona, en tres numeros.

    Un deposito no es un evento unico: se manda uno, se cae un dia y se
    manda otro, o el servicio se alarga y hace falta mas. Por eso las
    cuentas salen de las solicitudes y no del estatus del viatico, que
    solo puede contar una ronda a la vez.
    """
    asignado = sum((Decimal(str(v.monto_total)) for v in viaticos),
                   Decimal("0"))
    solicitudes = _solicitudes(db, viaticos)
    depositado = sum((Decimal(str(s_.monto)) for s_ in solicitudes
                      if s_.estatus == m.EstatusTransferencia.CONFIRMADA),
                     Decimal("0"))
    en_camino = sum((Decimal(str(s_.monto)) for s_ in solicitudes
                     if s_.estatus in EN_CAMINO), Decimal("0"))
    return {
        "asignado": asignado,
        "depositado": depositado,
        "en_camino": en_camino,
        # Lo que el consultor ya decidio pero todavia no le pide a nadie.
        "por_solicitar": asignado - depositado - en_camino,
    }


def _semaforo(dinero: dict) -> str:
    """Un solo color por persona. El que manda es el estado mas atrasado:
    si algo falta por pedir, el renglon no esta cerrado por mas que ya
    haya salido un deposito antes."""
    if dinero["asignado"] <= 0:
        return POR_ASIGNAR
    if dinero["por_solicitar"] > 0:
        return ASIGNADO
    if dinero["en_camino"] > 0:
        return SOLICITADO
    return DEPOSITADO


def _propuesta(db: Session, jornada: m.Jornada, persona_id: int) -> Decimal:
    """Lo que dice el tabulador para ese dia. Es una propuesta: el que
    decide es el consultor, que sabe si el dia trae caseta o no."""
    try:
        return Decimal(str(motor.calcular(db, jornada.id, persona_id)
                           ["total_propuesto"]))
    except HTTPException:
        return Decimal("0")


@router.get("/equipos/{equipo_id}", summary="Panel de viaticos del equipo")
def panel_de_equipo(equipo_id: int, db: Session = Depends(get_db),
                    _=Depends(LECTURA)):
    """Una linea por persona: lo que propone el sistema, lo que decidio el
    consultor y en que va el deposito. Debajo, las compras especiales."""
    equipo = _equipo(db, equipo_id)
    dias = _dias_vivos(equipo)
    pais = db.get(m.Pais, equipo.servicio.pais_id)

    # Quien esta en el equipo, sin repetir: la misma persona aparece una
    # vez por dia y aqui se ve una sola vez.
    personas: dict[int, m.Persona] = {}
    for jornada in dias:
        for a in jornada.personal:
            personas.setdefault(a.persona_id, a.persona)

    filas = []
    for persona_id, persona in personas.items():
        suyos = _dias_de(persona_id, dias)
        viaticos = (db.query(m.AsignacionViatico)
                    .filter(m.AsignacionViatico.persona_id == persona_id,
                            m.AsignacionViatico.jornada_id.in_(
                                [j.id for j in suyos]))
                    .all()) if suyos else []
        dinero = _dinero_de(db, viaticos)
        filas.append({
            "persona_id": persona_id,
            "nombre": persona.nombre,
            "puesto": _rol_de(suyos, persona_id),
            "dias": len(suyos),
            "propuesto": sum((_propuesta(db, j, persona_id) for j in suyos),
                             Decimal("0")),
            **dinero,
            "estatus": _semaforo(dinero),
            "comprobado": sum((Decimal(str(v.monto_comprobado))
                               for v in viaticos), Decimal("0")),
        })
    filas.sort(key=lambda f: f["nombre"])

    compras = (db.query(m.CompraEspecial)
               .filter(m.CompraEspecial.equipo_id == equipo.id)
               .order_by(m.CompraEspecial.id).all())

    return {
        "equipo": {"id": equipo.id, "alias": equipo.alias, "dias": len(dias)},
        "servicio_id": equipo.servicio_id,
        "moneda": pais.moneda_local.value if pais else None,
        "personal": filas,
        "total_propuesto": sum((f["propuesto"] for f in filas), Decimal("0")),
        "total_asignado": sum((f["asignado"] for f in filas), Decimal("0")),
        "total_depositado": sum((f["depositado"] for f in filas), Decimal("0")),
        "total_en_camino": sum((f["en_camino"] for f in filas), Decimal("0")),
        "total_por_solicitar": sum((f["por_solicitar"] for f in filas),
                                   Decimal("0")),
        "compras": [s.CompraOut.model_validate(c, from_attributes=True)
                    for c in compras],
    }


def _repartir(monto: Decimal, pesos: list[Decimal]) -> list[Decimal]:
    """Parte el monto entre los dias segun lo que pesa cada uno.

    Todo en unidades enteras, sin centavos: un viatico se entrega en
    efectivo o por transferencia y nadie anda partiendo pesos. Lo que
    sobra del reparto se le da un peso a la vez a los dias que quedaron
    mas cerca de subir, de mayor a menor resto, en vez de cargarselo
    todo al ultimo dia. Asi la suma de los dias da exactamente el numero
    que el consultor escribio: en finanzas, un peso de diferencia se
    convierte en una llamada.
    """
    if not pesos:
        return []
    monto = motor.redondear(monto)
    total = sum(pesos, Decimal("0"))
    if total <= 0:                       # sin propuesta, partes iguales
        pesos = [Decimal("1")] * len(pesos)
        total = Decimal(len(pesos))

    exactas = [monto * p / total for p in pesos]
    partes = [e.to_integral_value(rounding=ROUND_FLOOR) for e in exactas]
    sobran = int(monto - sum(partes, Decimal("0")))

    orden = sorted(range(len(pesos)), key=lambda i: exactas[i] - partes[i],
                   reverse=True)
    for i in orden[:sobran]:
        partes[i] += Decimal("1")
    return partes


@router.post("/equipos/{equipo_id}/persona",
             summary="Fijar cuanto se le deposita a una persona")
def fijar_monto(equipo_id: int, datos: s.ViaticoDeEquipoIn,
                db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(CONSULTOR)):
    """Un solo numero por persona, por todo su paso por el equipo.

    Por dentro se reparte entre sus dias segun lo que propone el
    tabulador para cada uno, y la diferencia contra la propuesta queda
    escrita como un ajuste con nombre y apellido. Asi la comprobacion
    sigue teniendo contra que comparar y se ve quien decidio que.
    """
    equipo = _equipo(db, equipo_id)
    suyos = _dias_de(datos.persona_id, _dias_vivos(equipo))
    if not suyos:
        raise HTTPException(409, "Esa persona no esta asignada al equipo")

    ya = (db.query(m.AsignacionViatico)
          .filter(m.AsignacionViatico.persona_id == datos.persona_id,
                  m.AsignacionViatico.jornada_id.in_([j.id for j in suyos]))
          .all())
    # Este endpoint reescribe el desglose desde cero, asi que solo sirve
    # mientras nadie haya pedido nada: si ya hay dinero con finanzas o en
    # la cuenta de la persona, lo que sigue es agregar otro deposito.
    fuera = _dinero_de(db, ya)
    if fuera["depositado"] > 0 or fuera["en_camino"] > 0:
        raise HTTPException(409, {
            "mensaje": "Esa persona ya tiene un deposito en marcha. "
                       "Agregue otro deposito en vez de mover el monto.",
            **{k: str(v) for k, v in fuera.items()},
        })

    pais = db.get(m.Pais, equipo.servicio.pais_id)
    propuestas = [_propuesta(db, j, datos.persona_id) for j in suyos]
    partes = _repartir(Decimal(str(datos.monto)), propuestas)
    por_jornada = {v.jornada_id: v for v in ya}

    for jornada, propuesto, toca in zip(suyos, propuestas, partes):
        viatico = por_jornada.get(jornada.id)
        if not viatico:
            viatico = m.AsignacionViatico(
                jornada_id=jornada.id, persona_id=datos.persona_id,
                escenario=motor.escenario_de(jornada),
                moneda=pais.moneda_local,
                asignado_por_id=usuario.persona_id)
            db.add(viatico)
            db.flush()

        # Se vuelve a escribir el desglose completo: el consultor puede
        # subir y bajar el numero varias veces antes de pedirlo, y
        # arrastrar los ajustes viejos dejaria un renglon por intento.
        for concepto in list(viatico.conceptos):
            db.delete(concepto)
        db.flush()

        detalle = motor.calcular(db, jornada.id, datos.persona_id)
        for c in detalle["conceptos"]:
            db.add(m.ConceptoAsignado(
                asignacion_id=viatico.id,
                concepto=m.ConceptoViatico(c["concepto"]),
                monto=c["monto"], descripcion=c["descripcion"],
                origen=m.OrigenMonto(c["origen"])))

        ajuste = toca - propuesto
        if ajuste != 0:
            db.add(m.ConceptoAsignado(
                asignacion_id=viatico.id, concepto=m.ConceptoViatico.OTROS,
                monto=ajuste, origen=m.OrigenMonto.MANUAL,
                descripcion="Ajuste del consultor"))
        db.flush()
        db.refresh(viatico)
        _recalcular_total(viatico)

    auditoria.registrar(db, usuario, equipo.servicio, "fijar viaticos",
                        f"{datos.monto} a persona {datos.persona_id} · "
                        f"{equipo.alias}, {len(suyos)} dia(s)")
    db.commit()
    return panel_de_equipo(equipo_id, db)


@router.post("/equipos/{equipo_id}/persona/agregar",
             summary="Otro deposito para la misma persona")
def agregar_deposito(equipo_id: int, datos: s.ViaticoDeEquipoIn,
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(CONSULTOR)):
    """Un deposito no cierra la puerta al siguiente.

    El servicio se alarga, se cae un dia y se repone, o simplemente
    falto dinero. Esto suma otro monto encima del que ya salio, sin
    tocar lo anterior: lo ya depositado sigue depositado y lo nuevo
    queda por solicitar.
    """
    equipo = _equipo(db, equipo_id)
    suyos = _dias_de(datos.persona_id, _dias_vivos(equipo))
    if not suyos:
        raise HTTPException(409, "Esa persona no esta asignada al equipo")
    if Decimal(str(datos.monto)) <= 0:
        raise HTTPException(400, "Un deposito adicional de cero no existe")

    ya = {v.jornada_id: v for v in
          db.query(m.AsignacionViatico)
          .filter(m.AsignacionViatico.persona_id == datos.persona_id,
                  m.AsignacionViatico.jornada_id.in_([j.id for j in suyos]))
          .all()}
    if not ya:
        raise HTTPException(409, "Esa persona todavia no tiene viaticos. "
                                 "Capture primero cuanto se le deposita.")

    pais = db.get(m.Pais, equipo.servicio.pais_id)
    # Se reparte igual que el primero, sobre el peso de cada dia.
    propuestas = [_propuesta(db, j, datos.persona_id) for j in suyos]
    partes = _repartir(Decimal(str(datos.monto)), propuestas)

    for jornada, toca in zip(suyos, partes):
        if toca == 0:
            continue
        viatico = ya.get(jornada.id)
        if not viatico:
            viatico = m.AsignacionViatico(
                jornada_id=jornada.id, persona_id=datos.persona_id,
                escenario=motor.escenario_de(jornada),
                moneda=pais.moneda_local,
                asignado_por_id=usuario.persona_id)
            db.add(viatico)
            db.flush()
        db.add(m.ConceptoAsignado(
            asignacion_id=viatico.id, concepto=m.ConceptoViatico.OTROS,
            monto=toca, origen=m.OrigenMonto.MANUAL, es_adicional=True,
            descripcion="Deposito adicional"))
        db.flush()
        db.refresh(viatico)
        _recalcular_total(viatico)
        # Si ya se habia cerrado, vuelve a estar en juego.
        if viatico.estatus in (m.EstatusViatico.CANCELADO,
                               m.EstatusViatico.DEVUELTO):
            viatico.estatus = m.EstatusViatico.ASIGNADO

    auditoria.registrar(db, usuario, equipo.servicio, "deposito adicional",
                        f"{datos.monto} a persona {datos.persona_id} · "
                        f"{equipo.alias}")
    db.commit()
    return panel_de_equipo(equipo_id, db)


@router.post("/equipos/{equipo_id}/solicitar",
             summary="Pedirle el deposito a finanzas")
def solicitar_deposito(equipo_id: int, datos: s.SolicitarDepositoIn,
                       db: Session = Depends(get_db),
                       usuario: m.Usuario = Depends(CONSULTOR)):
    """Sin persona, va por todo el equipo de una vez.

    Se pide el saldo, no el total: lo que ya se depositó o ya está con
    finanzas no se vuelve a pedir. Asi el segundo deposito de una misma
    persona sale por 500 y no por los 2,900 acumulados.
    """
    equipo = _equipo(db, equipo_id)
    dias = _dias_vivos(equipo)
    consulta = (db.query(m.AsignacionViatico)
                .filter(m.AsignacionViatico.jornada_id.in_([j.id for j in dias])))
    if datos.persona_id:
        consulta = consulta.filter(
            m.AsignacionViatico.persona_id == datos.persona_id)

    pedidos, monto = 0, Decimal("0")
    for viatico in consulta.all():
        saldo = _dinero_de(db, [viatico])["por_solicitar"]
        if saldo <= 0:
            continue          # nada que pedir: ya salio o ya esta pedido
        db.add(m.SolicitudTransferencia(
            asignacion_id=viatico.id, monto=saldo, moneda=viatico.moneda))
        # El estatus cuenta una ronda a la vez: solo se mueve el que
        # todavia no habia salido. Lo ya transferido sigue en su camino
        # de comprobacion, que es otro asunto.
        if viatico.estatus == m.EstatusViatico.ASIGNADO:
            viatico.estatus = m.EstatusViatico.SOLICITADO
        pedidos += 1
        monto += saldo

    if not pedidos:
        raise HTTPException(409, "No hay montos por solicitar. Capture "
                                 "primero cuanto se deposita.")

    auditoria.registrar(db, usuario, equipo.servicio, "solicitar deposito",
                        f"{monto} · {equipo.alias}, {pedidos} deposito(s)")
    db.commit()
    return panel_de_equipo(equipo_id, db)


@router.post("/equipos/{equipo_id}/cancelar-solicitud",
             summary="Echar atras un deposito que todavia no se hace")
def cancelar_solicitud(equipo_id: int, datos: s.SolicitarDepositoIn,
                       db: Session = Depends(get_db),
                       usuario: m.Usuario = Depends(CONSULTOR)):
    """Mientras el dinero no salga, el consultor puede echarse para atras.

    Pasa seguido: se pide el deposito y despues se cae un dia, cambia la
    gente o se capturo mal el monto. Sin esta salida la unica forma de
    corregir era depositar de mas y andar persiguiendo la devolucion.

    Lo ya depositado no entra aqui: eso se devuelve, no se cancela.
    """
    equipo = _equipo(db, equipo_id)
    dias = _dias_vivos(equipo)
    # Sin filtrar por estatus: quien ya recibio un deposito y tiene otro
    # en camino sigue en TRANSFERIDO, y ese segundo tambien se cancela.
    consulta = (db.query(m.AsignacionViatico)
                .filter(m.AsignacionViatico.jornada_id.in_([j.id for j in dias])))
    if datos.persona_id:
        consulta = consulta.filter(
            m.AsignacionViatico.persona_id == datos.persona_id)

    cancelados, monto = 0, Decimal("0")
    for viatico in consulta.all():
        vueltas = (db.query(m.SolicitudTransferencia)
                   .filter(m.SolicitudTransferencia.asignacion_id == viatico.id,
                           m.SolicitudTransferencia.estatus.in_(EN_CAMINO))
                   .all())
        if not vueltas:
            continue
        for solicitud in vueltas:
            solicitud.estatus = m.EstatusTransferencia.CANCELADA
            monto += Decimal(str(solicitud.monto))
        # Vuelve a quedar en manos del consultor, con su monto intacto:
        # casi siempre lo que sigue es corregirlo, no capturarlo de nuevo.
        # Al que ya recibio un deposito antes no se le toca el estatus:
        # ese dinero salio y su comprobacion sigue corriendo.
        if viatico.estatus == m.EstatusViatico.SOLICITADO:
            viatico.estatus = m.EstatusViatico.ASIGNADO
        cancelados += 1

    if not cancelados:
        raise HTTPException(409, "No hay depositos por cancelar. Si el "
                                 "dinero ya salio, se devuelve.")

    auditoria.registrar(db, usuario, equipo.servicio, "cancelar solicitud",
                        f"{monto} · {equipo.alias}, {cancelados} deposito(s)")
    db.commit()
    return panel_de_equipo(equipo_id, db)


# ================================================ compras especiales

# Hay gastos que no se depositan: se compran. Un boleto de avion, un
# hotel, un tren. El consultor no tiene la tarjeta de la empresa ni por
# que tenerla, asi que escribe lo que hace falta y finanzas lo compra.
# Va por equipo y no por persona: el vuelo o el hotel se gestionan para
# todo el equipo de una vez.

def _compra(db: Session, compra_id: int) -> m.CompraEspecial:
    compra = db.get(m.CompraEspecial, compra_id)
    if not compra:
        raise HTTPException(404, f"No existe la compra {compra_id}")
    return compra


ABIERTAS = (m.EstatusCompra.SOLICITADA, m.EstatusCompra.EN_GESTION)


@router.post("/equipos/{equipo_id}/compras", response_model=s.CompraOut,
             status_code=201, summary="Pedirle una compra a finanzas")
def pedir_compra(equipo_id: int, datos: s.CompraIn,
                 db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(CONSULTOR)):
    equipo = _equipo(db, equipo_id)
    pais = db.get(m.Pais, equipo.servicio.pais_id)
    compra = m.CompraEspecial(
        equipo_id=equipo.id, tipo=datos.tipo,
        solicitud=datos.solicitud.strip(),
        monto_estimado=datos.monto_estimado,
        moneda=pais.moneda_local,
        solicitada_por_id=usuario.persona_id)
    db.add(compra)
    auditoria.registrar(db, usuario, equipo.servicio, "pedir compra",
                        f"{datos.tipo.value} · {equipo.alias}")
    db.commit()
    db.refresh(compra)
    return compra


@router.get("/equipos/{equipo_id}/compras", response_model=list[s.CompraOut],
            summary="Compras especiales del equipo")
def compras_del_equipo(equipo_id: int, db: Session = Depends(get_db),
                       _=Depends(LECTURA)):
    _equipo(db, equipo_id)
    return (db.query(m.CompraEspecial)
            .filter(m.CompraEspecial.equipo_id == equipo_id)
            .order_by(m.CompraEspecial.id).all())


@router.patch("/compras/{compra_id}", response_model=s.CompraOut,
              summary="Corregir la solicitud antes de que la tomen")
def corregir_compra(compra_id: int, datos: s.CompraIn,
                    db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(CONSULTOR)):
    """Mientras finanzas no la haya tomado, el consultor la puede
    reescribir. Despues no: alguien ya esta buscando con ese texto."""
    compra = _compra(db, compra_id)
    if compra.estatus != m.EstatusCompra.SOLICITADA:
        raise HTTPException(409, {
            "mensaje": "Finanzas ya la esta atendiendo. Escribale en vez de "
                       "cambiarle la solicitud.",
            "estatus": compra.estatus.value,
        })
    compra.tipo = datos.tipo
    compra.solicitud = datos.solicitud.strip()
    compra.monto_estimado = datos.monto_estimado
    auditoria.registrar(db, usuario, compra.equipo.servicio,
                        "corregir compra", f"compra {compra.id}")
    db.commit()
    db.refresh(compra)
    return compra


@router.post("/compras/{compra_id}/cancelar", response_model=s.CompraOut,
             summary="Cancelar una compra que ya no hace falta")
def cancelar_compra(compra_id: int, db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(CONSULTOR)):
    compra = _compra(db, compra_id)
    if compra.estatus == m.EstatusCompra.CONFIRMADA:
        raise HTTPException(409, "Ya esta comprada. La cancelacion del "
                                 "boleto o la reserva la hace finanzas.")
    compra.estatus = m.EstatusCompra.CANCELADA
    auditoria.registrar(db, usuario, compra.equipo.servicio,
                        "cancelar compra", f"compra {compra.id}")
    db.commit()
    db.refresh(compra)
    return compra


@router.post("/compras/{compra_id}/tomar", response_model=s.CompraOut,
             summary="Finanzas la toma y empieza a buscar")
def tomar_compra(compra_id: int, db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(FINANZAS)):
    """Para que el consultor deje de preguntar si alguien la vio."""
    compra = _compra(db, compra_id)
    if compra.estatus not in ABIERTAS:
        raise HTTPException(409, f"La compra esta {compra.estatus.value}")
    compra.estatus = m.EstatusCompra.EN_GESTION
    compra.atendida_por_id = usuario.persona_id
    db.commit()
    db.refresh(compra)
    return compra


@router.post("/compras/{compra_id}/confirmar", response_model=s.CompraOut,
             summary="Finanzas contesta con la reserva")
def confirmar_compra(compra_id: int, datos: s.RespuestaCompraIn,
                     db: Session = Depends(get_db),
                     usuario: m.Usuario = Depends(FINANZAS)):
    """Sin folio ni comprobante no hay confirmacion: el equipo no se
    puede presentar en un mostrador con la palabra de que ya se compro."""
    compra = _compra(db, compra_id)
    if compra.estatus not in ABIERTAS:
        raise HTTPException(409, f"La compra esta {compra.estatus.value}")
    if not (datos.confirmacion or compra.comprobante):
        raise HTTPException(400, "Falta el numero de reserva o la imagen "
                                 "de la compra.")

    compra.estatus = m.EstatusCompra.CONFIRMADA
    compra.confirmacion = datos.confirmacion
    compra.monto_real = datos.monto_real
    compra.respuesta = datos.respuesta
    compra.atendida_por_id = usuario.persona_id
    compra.atendida_en = datetime.now()
    auditoria.registrar(db, usuario, compra.equipo.servicio,
                        "confirmar compra",
                        f"compra {compra.id} · {datos.confirmacion or 'con imagen'}")
    db.commit()
    db.refresh(compra)
    return compra


@router.post("/compras/{compra_id}/rechazar", response_model=s.CompraOut,
             summary="Finanzas no la puede resolver")
def rechazar_compra(compra_id: int, datos: s.RespuestaCompraIn,
                    db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(FINANZAS)):
    """Rechazar sin decir por que deja al consultor sin saber que hacer."""
    compra = _compra(db, compra_id)
    if compra.estatus not in ABIERTAS:
        raise HTTPException(409, f"La compra esta {compra.estatus.value}")
    if not datos.respuesta:
        raise HTTPException(400, "Diga por que no se puede: el consultor "
                                 "tiene que resolverlo de otra forma.")
    compra.estatus = m.EstatusCompra.RECHAZADA
    compra.respuesta = datos.respuesta
    compra.atendida_por_id = usuario.persona_id
    compra.atendida_en = datetime.now()
    auditoria.registrar(db, usuario, compra.equipo.servicio,
                        "rechazar compra", f"compra {compra.id}")
    db.commit()
    db.refresh(compra)
    return compra


@router.post("/compras/{compra_id}/comprobante", response_model=s.CompraOut,
             summary="Subir la imagen de la compra")
async def subir_comprobante_compra(compra_id: int,
                                   archivo: UploadFile = File(...),
                                   db: Session = Depends(get_db),
                                   usuario: m.Usuario = Depends(FINANZAS)):
    compra = _compra(db, compra_id)
    compra.comprobante = await imagenes.leer(archivo)
    db.commit()
    db.refresh(compra)
    return compra


@router.get("/compras/{compra_id}/comprobante",
            summary="Ver la imagen de la compra")
def ver_comprobante_compra(compra_id: int, db: Session = Depends(get_db),
                           _=Depends(LECTURA)):
    compra = _compra(db, compra_id)
    if not compra.comprobante:
        raise HTTPException(404, "Esa compra no trae imagen")
    cabeza, _, datos = compra.comprobante.partition(",")
    tipo = cabeza[5:].split(";")[0] or "image/png"
    return Response(content=base64.b64decode(datos), media_type=tipo)


# ==================================================== bandeja de finanzas

# Finanzas no trabaja servicio por servicio: abre una lista de lo que hay
# que pagar hoy y la despacha. Por eso todo lo pendiente se junta aqui,
# de los dos tipos: lo que se deposita y lo que se compra.

@router.get("/finanzas/bandeja", summary="Lo que finanzas tiene pendiente")
def bandeja(db: Session = Depends(get_db), _=Depends(LECTURA)):
    """Separada por pais.

    Cada pais lleva su propia caja, su propia moneda y su propia gente:
    juntar pesos y reales en una sola lista daba un total que no
    significaba nada y ponia a quien paga en Mexico a mirar depositos de
    Brasil que no le tocan.
    """
    paises = {p.id: p for p in db.query(m.Pais).all()}
    pendientes = (db.query(m.SolicitudTransferencia)
                  .filter(m.SolicitudTransferencia.estatus.in_(
                      (m.EstatusTransferencia.PENDIENTE,
                       m.EstatusTransferencia.ENVIADA)))
                  .order_by(m.SolicitudTransferencia.id).all())

    # Se agrupan por persona y equipo: son varios dias, pero es un solo
    # deposito. Que finanzas confirme cinco renglones del mismo agente es
    # como se pagan dos veces las cosas.
    depositos: dict[tuple, dict] = {}
    for solicitud in pendientes:
        viatico = solicitud.asignacion
        jornada = viatico.jornada
        equipo = jornada.equipo
        servicio = equipo.servicio
        clave = (equipo.id, viatico.persona_id)
        fila = depositos.setdefault(clave, {
            "pais_id": servicio.pais_id,
            "equipo_id": equipo.id, "equipo": equipo.alias,
            "servicio_id": servicio.id, "folio": servicio.folio,
            "cliente": servicio.cliente.nombre if servicio.cliente else None,
            "persona_id": viatico.persona_id,
            "persona": viatico.persona.nombre,
            "moneda": viatico.moneda.value,
            "monto": Decimal("0"), "dias": 0,
            "primera_jornada": jornada.fecha.isoformat(),
            "solicitudes": [],
        })
        fila["monto"] += Decimal(str(solicitud.monto))
        fila["dias"] += 1
        fila["solicitudes"].append(solicitud.id)
        fila["primera_jornada"] = min(fila["primera_jornada"],
                                      jornada.fecha.isoformat())

    compras = (db.query(m.CompraEspecial)
               .filter(m.CompraEspecial.estatus.in_(ABIERTAS))
               .order_by(m.CompraEspecial.id).all())

    # Autos de renta que ya no se ocupan. No es dinero por salir sino
    # dinero que sigue saliendo: mientras nadie le hable a la
    # arrendadora, el auto se cobra aunque este parado.
    rentas = (db.query(m.Vehiculo)
              .filter(m.Vehiculo.rentado.is_(True),
                      m.Vehiculo.renta_por_cancelar.is_(True))
              .order_by(m.Vehiculo.id).all())

    por_pais: dict[int, dict] = {}

    def caja(pais_id: int) -> dict:
        pais = paises.get(pais_id)
        return por_pais.setdefault(pais_id, {
            "pais_id": pais_id,
            "codigo": pais.codigo if pais else "??",
            "pais": pais.nombre if pais else "Sin pais",
            "moneda": pais.moneda_local.value if pais else None,
            "depositos": [], "compras": [], "rentas": [],
            "total_depositos": Decimal("0"),
        })

    for fila in sorted(depositos.values(),
                       key=lambda f: f["primera_jornada"]):
        destino = caja(fila["pais_id"])
        destino["depositos"].append(fila)
        destino["total_depositos"] += fila["monto"]

    for c in compras:
        servicio = c.equipo.servicio
        caja(servicio.pais_id)["compras"].append({
            **s.CompraOut.model_validate(c, from_attributes=True).model_dump(),
            "equipo": c.equipo.alias,
            "servicio_id": servicio.id,
            "folio": servicio.folio,
            "cliente": servicio.cliente.nombre if servicio.cliente else None,
        })

    for vehiculo in rentas:
        # El pais sale de la ciudad donde se rento: el servicio que la
        # pidio puede haberse borrado ya.
        pais_id = vehiculo.plaza.pais_id if vehiculo.plaza else None
        caja(pais_id)["rentas"].append({
            "vehiculo_id": vehiculo.id,
            "placa": vehiculo.placa,
            "unidad": vehiculo.categoria.nombre if vehiculo.categoria else None,
            "marca_modelo": vehiculo.marca_modelo,
            "color": vehiculo.color,
            "arrendadora": vehiculo.arrendadora,
            "telefono": vehiculo.arrendadora_telefono,
            "costo_diario": vehiculo.costo_diario,
            "folio": vehiculo.renta_folio,
            "ciudad": vehiculo.plaza.nombre if vehiculo.plaza else None,
            # Si el servicio ya no esta, no hay a donde ir: por eso el
            # folio se guarda aparte del enlace.
            "servicio_id": vehiculo.servicio_id,
        })

    return {"paises": sorted(por_pais.values(), key=lambda p: p["pais"])}


# ---------------------------------------------------- control del dinero
#
# La bandeja despacha; esto controla. Son dos trabajos distintos y por
# eso son cuatro vistas: lo que hay que pagar hoy, lo que ya se pago, lo
# que anda afuera sin comprobar y lo que tiene que regresar.

@router.get("/finanzas/corte", summary="Los numeros de arriba, por pais")
def corte(db: Session = Depends(get_db), ahora: datetime | None = None,
          _=Depends(LECTURA)):
    return control.corte(db, ahora)


@router.get("/finanzas/depositado", summary="Lo que ya se pago")
def depositado(desde: date | None = None, hasta: date | None = None,
               persona_id: int | None = None, folio: str | None = None,
               db: Session = Depends(get_db), _=Depends(LECTURA)):
    """Con su referencia y la firma de quien lo despacho.

    Sin rango sale el ultimo mes. Se puede buscar por persona o por
    folio, que es como se pregunta de verdad: "¿ya le pagamos a Juan?".
    """
    return control.depositado(db, desde, hasta, persona_id, folio)


@router.get("/finanzas/por-comprobar",
            summary="Quien trae dinero de la empresa y desde cuando")
def por_comprobar(db: Session = Depends(get_db),
                  ahora: datetime | None = None, _=Depends(LECTURA)):
    return control.por_comprobar(db, ahora)


@router.get("/finanzas/devoluciones",
            summary="Lo que tiene que regresar, por devolucion o descuento")
def devoluciones(db: Session = Depends(get_db), _=Depends(LECTURA)):
    return control.devoluciones(db)


@router.post("/finanzas/rentas/{vehiculo_id}/cancelada",
             summary="Finanzas ya cancelo la renta con la arrendadora")
def renta_cancelada(vehiculo_id: int, db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(FINANZAS)):
    """Sale de la lista cuando alguien hablo con la arrendadora, no
    cuando el servicio se borro. Queda firmado quien y cuando."""
    vehiculo = db.get(m.Vehiculo, vehiculo_id)
    if not vehiculo or not vehiculo.rentado:
        raise HTTPException(404, f"No existe el auto rentado {vehiculo_id}")
    if not vehiculo.renta_por_cancelar:
        raise HTTPException(409, "Esa renta no esta pendiente de cancelar")

    vehiculo.renta_por_cancelar = False
    vehiculo.renta_cancelada_en = datetime.now()
    vehiculo.renta_cancelada_por_id = usuario.persona_id
    db.commit()
    return {"resultado": "renta cancelada", "placa": vehiculo.placa,
            "arrendadora": vehiculo.arrendadora}


@router.post("/finanzas/depositar", summary="Finanzas confirma el deposito")
def depositar(datos: s.DepositoIn, db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(FINANZAS)):
    """Un solo movimiento por persona, aunque por dentro sean varios dias."""
    equipo = _equipo(db, datos.equipo_id)
    dias = _dias_vivos(equipo)
    solicitudes = (db.query(m.SolicitudTransferencia)
                   .join(m.AsignacionViatico,
                         m.SolicitudTransferencia.asignacion_id
                         == m.AsignacionViatico.id)
                   .filter(m.AsignacionViatico.persona_id == datos.persona_id,
                           m.AsignacionViatico.jornada_id.in_(
                               [j.id for j in dias]),
                           m.SolicitudTransferencia.estatus.in_(
                               (m.EstatusTransferencia.PENDIENTE,
                                m.EstatusTransferencia.ENVIADA)))
                   .all())
    if not solicitudes:
        raise HTTPException(404, "No hay depositos pendientes de esa persona")

    monto = Decimal("0")
    for solicitud in solicitudes:
        solicitud.estatus = m.EstatusTransferencia.CONFIRMADA
        solicitud.referencia_odoo = datos.referencia
        # Un segundo deposito no regresa a la persona al principio: si ya
        # estaba comprobando o cerrada, ahi se queda.
        if solicitud.asignacion.estatus in (m.EstatusViatico.ASIGNADO,
                                            m.EstatusViatico.SOLICITADO):
            solicitud.asignacion.estatus = m.EstatusViatico.TRANSFERIDO
        monto += Decimal(str(solicitud.monto))

    auditoria.registrar(db, usuario, equipo.servicio, "confirmar deposito",
                        f"{monto} a persona {datos.persona_id} · "
                        f"{datos.referencia or 'sin referencia'}")
    db.commit()
    return {"resultado": "depositado", "monto": monto,
            "depositos": len(solicitudes),
            "nota": "Ya aparece en la app del personal como saldo disponible"}

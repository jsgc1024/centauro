"""Asignacion, transferencia, comprobacion y cierre de viaticos."""
import base64
import logging
from datetime import date, datetime
from decimal import Decimal, ROUND_FLOOR

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Query,
                     Response, UploadFile)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auditoria
from app import auth
from app import bolson as motor_bolson
from app import depositos as motor_depositos
from app import devoluciones as devoluciones_motor
from app import imagenes
from app import models as m
from app import schemas as s
from app import finanzas as control
from app import nomina
from app import push
from app import reloj
from app import viaticos as motor
from app.db import get_db

router = APIRouter(prefix="/viaticos", tags=["Viaticos"])
registro = logging.getLogger("centauro.viaticos")

# Las puertas preguntan por actividad y no por rol. Hoy la respuesta es
# la misma --cada actividad nace con los roles que tenia-- pero el dia
# que exista el panel de categorias, estas puertas no se tocan.
#
# Decidir cuanto se deposita no es lo mismo que revisar lo que se gasto,
# asi que son dos actividades: es la diferencia entre un consultor y un
# consultor junior.
CONSULTOR = auth.puede("viaticos.asignar")
CIERRA = auth.puede("viaticos.cerrar")
FINANZAS = auth.puede("viaticos.transferir")
CAMPO = auth.puede("viaticos.comprobar")
LECTURA = auth.puede("viaticos.ver")
# La evidencia del deposito la ven finanzas y direccion, el consultor
# —que es quien recibe la llamada de "no me ha llegado"— y el agente,
# pero solo la suya. Lo ultimo se revisa dentro del endpoint, no aqui:
# la actividad deja pasar, la pertenencia decide.
EVIDENCIA = auth.puede("viaticos.evidencia")


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
        # Quien lo autorizo, tomado de la sesion. Es lo que finanzas lee
        # en la bandeja para saber a quien preguntarle por un gasto.
        asignado_por_id=usuario.persona_id,
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
        usuario: m.Usuario = Depends(auth.usuario_actual)):
    """El personal de seguridad solo ve los suyos.

    Aqui se ve cuanto efectivo trae encima cada quien y a quien le
    descontaron de nomina. Recorriendo los numeros se sacaba de toda la
    plantilla; y saber quien anda en la calle con dinero es justo lo que
    no debe saberse.
    """
    viatico = _obtener(db, viatico_id)
    if (usuario.rol == m.Rol.PERSONAL_SEGURIDAD
            and viatico.persona_id != usuario.persona_id):
        raise HTTPException(403, "Solo puedes ver tus propios viaticos")
    return viatico


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


def _avisar_sin_tumbar(que, *args) -> None:
    """Un aviso al telefono nunca detiene lo que lo llamo.

    El deposito ya esta guardado cuando se llama a esto. Si el envio
    fallara --un telefono desuscrito, una llave mal puesta-- lo que no
    puede pasar es que se caiga la operacion que ya ocurrio en el banco.
    """
    try:
        que(*args)
    except Exception:                     # noqa: BLE001
        registro.exception("no se pudo mandar el aviso de %s", que.__name__)


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

    # Esta es la puerta del barrido por lote y de lo que llega ya
    # confirmado de Odoo: no hay una persona subiendo una captura del
    # banco. El deposito se crea igual —para que todo lo confirmado
    # tenga a que colgarse— y sale marcado *sin comprobante*. Desde la
    # pantalla, en cambio, la evidencia es obligatoria.
    deposito = motor_depositos.registrar(
        db, [solicitud.id], referencia_odoo,
        despachado_por_id=usuario.persona_id, exige_evidencia=False)
    db.commit()
    # "¿Ya me depositaron?" es la pregunta que mas recibe la central, y
    # hasta hoy se contestaba mirando la bandeja.
    _avisar_sin_tumbar(push.avisar_deposito, db, deposito)
    db.commit()
    return {"resultado": "confirmada", "solicitud_id": solicitud.id,
            "viatico_id": solicitud.asignacion_id,
            "deposito_id": deposito.id,
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

    # Las mismas reglas que la app. Son la misma tabla y el mismo rol:
    # tener los topes en un solo endpoint era dejar la otra puerta
    # abierta, y la persona bloqueada por una entraba por la otra.
    mal = motor.revisar_comprobante(v, Decimal(str(datos.monto)),
                                    datos.concepto, datos.descripcion, db=db)
    if mal:
        raise HTTPException(mal.pop("codigo"), mal)

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


class MotivoIn(BaseModel):
    motivo: str


@router.post("/{viatico_id}/rechazar-comprobante/{comprobante_id}",
             summary="El consultor rechaza un gasto que no aplica")
def rechazar_comprobante(viatico_id: int, comprobante_id: int,
                         motivo: str | None = None,
                         datos: MotivoIn | None = None,
                         db: Session = Depends(get_db),
                         usuario: m.Usuario = Depends(CIERRA)):
    """Un gasto que no corresponde al servicio deja de contar como
    comprobado. Eso abre una diferencia que el conductor tiene que cubrir,
    o que el consultor manda a descuento al cerrar.

    El motivo llega en el cuerpo; en la direccion se sigue aceptando por
    lo que ya lo mandaba asi. Es lo que la persona lee en su telefono."""
    motivo = ((datos.motivo if datos else None) or motivo or "").strip()
    if len(motivo) < 3:
        raise HTTPException(400, {
            "mensaje": "Escribe por que no aplica",
            "que_hacer": "Es lo que la persona lee en su telefono."})
    v = _obtener(db, viatico_id)
    comprobante = next((c for c in v.comprobantes if c.id == comprobante_id), None)
    if not comprobante:
        raise HTTPException(404, "Ese comprobante no pertenece a esta asignacion")
    if v.estatus in (m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO):
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
    # Sin esto, el rechazo se entera de dos maneras: cuando ve el
    # descuento en su pago, o cuando alguien le habla. Y casi siempre
    # lo que paso es que el ticket salio borroso.
    _avisar_sin_tumbar(push.avisar_comprobante_rechazado, db, v, comprobante)
    db.commit()
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
                         usuario: m.Usuario = Depends(CIERRA)):
    """Cuando el conductor no puede resolver su comprobacion.

    Lo que quedo sin cubrir se le descuenta de su proxima nomina. El
    consultor puede decidir que la empresa absorba una parte, pero tiene
    que decir cuanto y por que: el descuento por omision es el total.
    """
    v = _obtener(db, viatico_id)
    if v.estatus == m.EstatusViatico.CERRADO:
        raise HTTPException(409, "Ya estaba cerrado")
    # Decision de Salvador (23 sep): solo despues de su plazo --antes
    # todavia puede comprobar-- y solo sobre dinero que ya se deposito.
    if v.estatus not in (m.EstatusViatico.TRANSFERIDO,
                         m.EstatusViatico.EN_COMPROBACION):
        raise HTTPException(409, {
            "mensaje": "Ese dinero todavia no se deposita",
            "que_hacer": "Lo que no salio del banco no se descuenta."})
    momento = reloj.ahora_de_la_jornada(db, v.jornada)
    if not v.limite_comprobacion or momento < v.limite_comprobacion:
        raise HTTPException(409, {
            "mensaje": ("Todavia esta en plazo para comprobar"
                        if v.limite_comprobacion else
                        "Su plazo para comprobar todavia no arranca"),
            "que_hacer": ("Cuando venza su plazo, lo que falte se puede "
                          "descontar."),
            "hasta": (v.limite_comprobacion.isoformat()
                      if v.limite_comprobacion else None)})

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
            concepto=nomina.AJUSTE_VIATICO,
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
           usuario: m.Usuario = Depends(CIERRA)):
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
                        _=Depends(CIERRA)):
    v = _obtener(db, viatico_id)
    comprobante = next((c for c in v.comprobantes if c.id == comprobante_id), None)
    if not comprobante:
        raise HTTPException(404, "Ese comprobante no pertenece a esta asignacion")
    if v.estatus in (m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO):
        raise HTTPException(409, "Los viaticos ya estan cerrados")
    if comprobante.rechazado:
        raise HTTPException(409, {
            "mensaje": "Ese comprobante ya se rechazo",
            "que_hacer": "Si era bueno, que la persona lo vuelva a subir."})
    comprobante.validado = True
    comprobante.observacion = observacion
    db.commit()
    return {"resultado": "validado", "comprobante_id": comprobante_id}


# ---------------------------------------------------------------- el bolson

# El dinero de una persona en el servicio es uno solo: se deposita junto
# y se gasta junto. Por dentro vive dia por dia, pero se revisa y se
# cierra por persona (`app.bolson`). Cualquiera de sus viaticos nombra
# el bolson: el servidor junta los demas.

@router.post("/{viatico_id}/bolson/cerrar",
             summary="Cerrar todo el dinero de una persona en el servicio")
def cerrar_bolson(viatico_id: int, db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(CIERRA)):
    """Cuando todo lo depositado quedo comprobado o devuelto y cada
    ticket tiene su revision. Si falta o sobra, dice que hacer."""
    return motor_bolson.cerrar(db, _obtener(db, viatico_id), usuario)


@router.post("/{viatico_id}/bolson/cerrar-con-descuento",
             summary="Cerrar con descuento lo que una persona no comprobo")
def cerrar_bolson_con_descuento(viatico_id: int,
                                datos: s.CierreConDescuentoIn,
                                db: Session = Depends(get_db),
                                usuario: m.Usuario = Depends(CIERRA)):
    """Solo despues de su plazo y solo sobre lo que se le deposito
    (decision de Salvador, 23 sep). Lo descontado entra al siguiente
    corte de nomina, en un solo ajuste."""
    return motor_bolson.cerrar_con_descuento(
        db, _obtener(db, viatico_id), datos, usuario)


@router.get("/{viatico_id}/comprobantes/{comprobante_id}/imagen",
            summary="La foto del ticket")
def ver_imagen_comprobante(viatico_id: int, comprobante_id: int,
                           db: Session = Depends(get_db),
                           usuario: m.Usuario = Depends(auth.usuario_actual)):
    """La ve quien revisa el dinero, y la persona la suya."""
    v = _obtener(db, viatico_id)
    if usuario.rol == m.Rol.PERSONAL_SEGURIDAD:
        if v.persona_id != usuario.persona_id:
            raise HTTPException(403, "Solo puedes ver tus propios comprobantes")
    elif not auth.puede_el_usuario(db, usuario, "viaticos.ver"):
        raise HTTPException(403, "Tu rol no puede ver comprobantes")
    comprobante = next((c for c in v.comprobantes if c.id == comprobante_id),
                       None)
    if not comprobante:
        raise HTTPException(404, "Ese comprobante no pertenece a esta asignacion")
    if not comprobante.imagen and comprobante.archivado_en:
        raise _archivada(comprobante.archivado_en)
    if not comprobante.imagen:
        raise HTTPException(404, "Ese comprobante no trae foto")
    return _imagen(comprobante.imagen)


def _archivada(cuando: datetime) -> HTTPException:
    """La foto ya se fue al archivo (seccion 69): no falta, esta en otro
    lado, y el mensaje dice donde."""
    return HTTPException(410, {
        "mensaje": f"La foto se archivo el {cuando:%d/%m/%Y}",
        "que_hacer": ("Se trae desde Facturacion, en el Historial, con "
                      "Ver del archivo (direccion general y finanzas).")})


@router.get("/devoluciones/{devolucion_id}/comprobante",
            summary="La foto de la transferencia de una devolucion")
def ver_comprobante_devolucion(devolucion_id: int,
                               db: Session = Depends(get_db),
                               usuario: m.Usuario = Depends(auth.usuario_actual)):
    """La ve quien revisa el dinero, y la persona la suya. Existia la foto
    y no habia por donde verla: finanzas confirmaba la devolucion con la
    referencia y nada mas (seccion 69)."""
    fila = db.get(m.DevolucionViatico, devolucion_id)
    if not fila:
        raise HTTPException(404, f"No existe la devolucion {devolucion_id}")
    if usuario.rol == m.Rol.PERSONAL_SEGURIDAD:
        if fila.asignacion.persona_id != usuario.persona_id:
            raise HTTPException(403, "Solo puedes ver tus propias devoluciones")
    elif not auth.puede_el_usuario(db, usuario, "viaticos.ver"):
        raise HTTPException(403, "Tu rol no puede ver comprobantes")
    if not fila.comprobante and fila.archivado_en:
        raise _archivada(fila.archivado_en)
    if not fila.comprobante:
        raise HTTPException(404, "Esa devolucion no trae foto")
    return _imagen(fila.comprobante)


@router.post("/{viatico_id}/devolver",
             summary="Finanzas registra una devolucion que ya entro")
async def devolver(viatico_id: int, monto: Decimal = Form(...),
                   referencia: str = Form(...),
                   archivo: UploadFile = File(...),
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(FINANZAS)):
    """La transferencia llego y nadie la habia declarado.

    Lo captura finanzas porque es quien mira la cuenta. Antes esto lo
    hacia el consultor, con el monto en la direccion y sin un solo
    papel: el consultor nunca vio ese dinero entrar, asi que lo unico
    que se estaba registrando era su buena fe.

    Referencia y comprobante son obligatorios, igual que en el deposito:
    es lo que permite rastrear el movimiento en el banco si despues no
    cuadra.
    """
    viatico = _obtener(db, viatico_id)
    comprobante = await imagenes.leer(archivo)
    fila = devoluciones_motor.declarar(
        db, viatico, monto, referencia, comprobante, usuario.persona_id,
        reloj.ahora_de_la_jornada(db, viatico.jornada), ya_confirmada=True)
    auditoria.registrar(db, usuario, viatico.jornada.equipo.servicio,
                        "devolucion de viaticos",
                        f"{viatico.persona.nombre}: {monto} "
                        f"{viatico.moneda.value}, ref {fila.referencia}",
                        jornada_id=viatico.jornada_id)
    db.commit()
    return {"resultado": "registrada", "devolucion_id": fila.id,
            "monto_devuelto": float(viatico.monto_devuelto)}


@router.post("/devoluciones/{devolucion_id}/confirmar",
             summary="Finanzas confirma que el dinero entro")
def confirmar_devolucion(devolucion_id: int, db: Session = Depends(get_db),
                         usuario: m.Usuario = Depends(FINANZAS)):
    """Hasta aqui el dinero no habia vuelto, solo estaba prometido."""
    fila = db.get(m.DevolucionViatico, devolucion_id)
    if not fila:
        raise HTTPException(404, f"No existe la devolucion {devolucion_id}")

    viatico = fila.asignacion
    devoluciones_motor.confirmar(
        db, fila, usuario.persona_id,
        reloj.ahora_de_la_jornada(db, viatico.jornada))
    auditoria.registrar(db, usuario, viatico.jornada.equipo.servicio,
                        "devolucion confirmada",
                        f"{viatico.persona.nombre}: {fila.monto} "
                        f"{fila.moneda.value}, ref {fila.referencia}",
                        jornada_id=viatico.jornada_id)
    db.commit()
    return {"resultado": "confirmada",
            "monto_devuelto": float(viatico.monto_devuelto)}


@router.post("/devoluciones/{devolucion_id}/rechazar",
             summary="La devolucion no llego o no cuadra")
def rechazar_devolucion(devolucion_id: int, datos: s.RechazoDevolucionIn,
                        db: Session = Depends(get_db),
                        usuario: m.Usuario = Depends(FINANZAS)):
    """No se borra: la persona dijo que transfirio y eso queda anotado,
    con el motivo por el que no se acepto. Una devolucion que desaparece
    deja la discusion sin papeles."""
    fila = db.get(m.DevolucionViatico, devolucion_id)
    if not fila:
        raise HTTPException(404, f"No existe la devolucion {devolucion_id}")

    viatico = fila.asignacion
    devoluciones_motor.rechazar(
        db, fila, usuario.persona_id, datos.motivo,
        reloj.ahora_de_la_jornada(db, viatico.jornada))
    auditoria.registrar(db, usuario, viatico.jornada.equipo.servicio,
                        "devolucion rechazada",
                        f"{viatico.persona.nombre}: {fila.monto} "
                        f"{fila.moneda.value} · {datos.motivo}",
                        jornada_id=viatico.jornada_id)
    db.commit()
    _avisar_sin_tumbar(push.avisar_devolucion_rechazada, db, fila)
    db.commit()
    return {"resultado": "rechazada", "motivo": fila.motivo_rechazo}


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

    # El dinero que salio del banco despues de que alguien cancelo la
    # solicitud. Es lo unico de este panel que no se resuelve solo: hay
    # que aplicarlo o pedirlo de vuelta, y si no se ve, no pasa ninguna
    # de las dos cosas.
    tardios: dict[int, Decimal] = {}
    for deposito in (db.query(m.DepositoBancario)
                     .filter(m.DepositoBancario.equipo_id == equipo.id,
                             m.DepositoBancario.sobre_cancelada.is_(True))
                     .all()):
        tardios[deposito.persona_id] = (tardios.get(deposito.persona_id,
                                                    Decimal("0"))
                                        + Decimal(str(deposito.monto)))

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
            # Se le depositó después de que se canceló: hay que aplicarlo
            # o pedirlo de vuelta.
            "depositado_tras_cancelar": tardios.get(persona_id, Decimal("0")),
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
        "total_tras_cancelar": sum(tardios.values(), Decimal("0")),
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

    ahora = datetime.now()
    cancelados, pedidos, monto, pedido = 0, 0, Decimal("0"), Decimal("0")
    for viatico in consulta.all():
        vueltas = (db.query(m.SolicitudTransferencia)
                   .filter(m.SolicitudTransferencia.asignacion_id == viatico.id,
                           m.SolicitudTransferencia.estatus.in_(EN_CAMINO))
                   .all())
        if not vueltas:
            continue
        suyas = 0
        for solicitud in vueltas:
            # Lo que ya salio en el barrido esta en manos de finanzas, y
            # puede estar transfiriendose AHORA MISMO. El unico que sabe
            # si el dinero ya salio del banco es finanzas: cancelarlo
            # aqui dejaria una transferencia hecha sin registro, y quien
            # la recibio con dinero que el sistema no conoce. Queda
            # pedida y finanzas la cierra.
            if solicitud.estatus == m.EstatusTransferencia.ENVIADA:
                if not solicitud.cancelacion_pedida_en:
                    solicitud.cancelacion_pedida_en = ahora
                    solicitud.cancelacion_pedida_por_id = usuario.persona_id
                    pedidos += 1
                    pedido += Decimal(str(solicitud.monto))
                continue
            solicitud.estatus = m.EstatusTransferencia.CANCELADA
            monto += Decimal(str(solicitud.monto))
            suyas += 1
        if not suyas:
            continue
        # Vuelve a quedar en manos del consultor, con su monto intacto:
        # casi siempre lo que sigue es corregirlo, no capturarlo de nuevo.
        # Al que ya recibio un deposito antes no se le toca el estatus:
        # ese dinero salio y su comprobacion sigue corriendo.
        if viatico.estatus == m.EstatusViatico.SOLICITADO:
            viatico.estatus = m.EstatusViatico.ASIGNADO
        cancelados += 1

    if not cancelados and not pedidos:
        raise HTTPException(409, "No hay depositos por cancelar. Si el "
                                 "dinero ya salio, se devuelve.")

    auditoria.registrar(
        db, usuario, equipo.servicio, "cancelar solicitud",
        f"{monto} · {equipo.alias}, {cancelados} deposito(s)"
        + (f"; {pedidos} pedido(s) a finanzas por {pedido}" if pedidos else ""))
    db.commit()
    panel = panel_de_equipo(equipo_id, db)
    # Lo que quedo pedido no esta cancelado todavia. Decirlo aqui es lo
    # que evita que el consultor lo de por hecho y borre el servicio.
    panel["cancelados"] = cancelados
    panel["pedidos_a_finanzas"] = pedidos
    return panel


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
    return _imagen(compra.comprobante)


def _imagen(data_uri: str) -> Response:
    """Un data URI guardado, servido como el archivo que era."""
    cabeza, _, datos = data_uri.partition(",")
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
        # El mes es la unidad del implantado: se factura, se opera y se
        # deposita por mes. Juntar dos meses en un renglon obligaba a
        # depositar 10,500 de un golpe y a que la pantalla del consultor
        # los mostrara partidos despues, sin que nadie hubiera decidido
        # ese reparto. El eventual sigue agrupado por equipo: ahi el
        # servicio es la unidad y casi nunca cruza el cambio de mes.
        por_mes = servicio.tipo == m.TipoServicio.IMPLANTADO
        periodo = (jornada.fecha.year, jornada.fecha.month) if por_mes else None
        clave = (equipo.id, viatico.persona_id, periodo)
        fila = depositos.setdefault(clave, {
            "pais_id": servicio.pais_id,
            "equipo_id": equipo.id, "equipo": equipo.alias,
            # Con que mes se deposita. Nulo en el eventual.
            "anio": periodo[0] if periodo else None,
            "mes": periodo[1] if periodo else None,
            "periodo": (f"{periodo[1]:02d}/{periodo[0]}" if periodo else None),
            "servicio_id": servicio.id, "folio": servicio.folio,
            "cliente": servicio.cliente.nombre if servicio.cliente else None,
            "persona_id": viatico.persona_id,
            "persona": viatico.persona.nombre,
            "moneda": viatico.moneda.value,
            "monto": Decimal("0"), "dias": 0,
            "primera_jornada": jornada.fecha.isoformat(),
            "solicitudes": [], "detalle": [],
            "solicito": None, "solicitada_en": None,
            # El consultor quiere echarse para atras algo que ya esta
            # aqui. No lo canceló él: el que sabe si el dinero ya salio
            # del banco es quien lo deposita. Sale en la bandeja para
            # que se cierre antes de ir al banco, no despues.
            "cancelacion_pedida": False, "cancelacion_pedida_en": None,
            # A donde se deposita. Viene de Odoo; mientras esa conexion
            # no exista, finanzas lo llena y se va poblando.
            "banco": viatico.persona.banco,
            "clabe": viatico.persona.clabe,
            "titular_cuenta": viatico.persona.titular_cuenta,
        })
        fila["monto"] += Decimal(str(solicitud.monto))
        fila["dias"] += 1
        fila["solicitudes"].append(solicitud.id)
        fila["primera_jornada"] = min(fila["primera_jornada"],
                                      jornada.fecha.isoformat())

        # De que se compone. Finanzas veia un total y nada mas: para
        # depositar alcanzaba, para revisar antes de depositar no. El
        # origen importa tanto como el monto —un numero del tabulador no
        # se discute, uno capturado a mano si— y hasta hoy no se podian
        # distinguir.
        fila["detalle"].append({
            "solicitud_id": solicitud.id,
            "fecha": jornada.fecha.isoformat(),
            "monto": Decimal(str(solicitud.monto)),
            "conceptos": [{"concepto": c.concepto.value,
                           "descripcion": c.descripcion,
                           "monto": Decimal(str(c.monto)),
                           "origen": c.origen.value,
                           "adicional": c.es_adicional}
                          for c in viatico.conceptos],
        })
        # Quien autorizo el gasto. El dato existia y nunca llegaba a la
        # pantalla: finanzas no sabia a quien preguntarle.
        if not fila["solicito"] and viatico.asignado_por_id:
            quien = db.get(m.Persona, viatico.asignado_por_id)
            fila["solicito"] = quien.nombre if quien else None
        if solicitud.creada_en:
            pedida = solicitud.creada_en.isoformat()
            fila["solicitada_en"] = min(fila["solicitada_en"] or pedida, pedida)
        if solicitud.cancelacion_pedida_en:
            cuando = solicitud.cancelacion_pedida_en.isoformat()
            fila["cancelacion_pedida"] = True
            fila["cancelacion_pedida_en"] = min(
                fila["cancelacion_pedida_en"] or cuando, cuando)

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
        fila["detalle"].sort(key=lambda d: d["fecha"])
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

# ------------------------------------------------------- el deposito

@router.patch("/depositos/{deposito_id}",
              summary="Corregir la referencia o el comprobante")
async def corregir_deposito(deposito_id: int,
                            referencia: str | None = Form(None),
                            archivo: UploadFile | None = File(None),
                            db: Session = Depends(get_db),
                            usuario: m.Usuario = Depends(FINANZAS)):
    """Subir el archivo correcto es lo mas comun que pasa despues.

    Se permite siempre, y queda escrito quien lo cambio: una evidencia
    que se reemplaza sin dejar rastro no es evidencia.
    """
    comprobante = await imagenes.leer(archivo) if archivo else None
    deposito = motor_depositos.corregir(db, deposito_id, referencia,
                                        comprobante,
                                        por_id=usuario.persona_id)
    auditoria.registrar(db, usuario, deposito.equipo.servicio,
                        "correccion de deposito",
                        f"deposito {deposito.id}, ref {deposito.referencia}")
    db.commit()
    db.refresh(deposito)
    return _deposito(deposito)


@router.post("/depositos/{deposito_id}/anular",
             summary="Anular un deposito mal registrado")
def anular_deposito(deposito_id: int, motivo: str = Form(...),
                    db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(FINANZAS)):
    """Solo mientras el agente no haya comprobado nada de ese dinero."""
    deposito = db.get(m.DepositoBancario, deposito_id)
    if not deposito:
        raise HTTPException(404, f"No existe el deposito {deposito_id}")
    servicio = deposito.equipo.servicio
    resultado = motor_depositos.anular(db, deposito_id, motivo,
                                       por_id=usuario.persona_id)
    auditoria.registrar(db, usuario, servicio, "deposito anulado",
                        f"deposito {deposito_id}: {motivo}")
    db.commit()
    return resultado


@router.get("/depositos/{deposito_id}/comprobante",
            summary="Ver el comprobante del deposito")
def ver_comprobante_deposito(deposito_id: int, db: Session = Depends(get_db),
                             usuario: m.Usuario = Depends(EVIDENCIA)):
    """El agente ve solo el suyo. Los demas roles, el de quien sea.

    Es la respuesta a la pregunta mas frecuente que recibe finanzas:
    "¿ya me depositaron?".
    """
    deposito = db.get(m.DepositoBancario, deposito_id)
    if not deposito:
        raise HTTPException(404, f"No existe el deposito {deposito_id}")
    if (usuario.rol == m.Rol.PERSONAL_SEGURIDAD
            and deposito.persona_id != usuario.persona_id):
        raise HTTPException(403, "Ese deposito no es tuyo")
    if not deposito.comprobante:
        raise HTTPException(404, "Ese deposito no tiene comprobante")
    return _imagen(deposito.comprobante)


def _deposito(d: m.DepositoBancario) -> dict:
    return {
        "id": d.id, "persona_id": d.persona_id,
        "persona": d.persona.nombre if d.persona else None,
        "equipo_id": d.equipo_id,
        "monto": d.monto, "moneda": d.moneda.value,
        "referencia": d.referencia,
        "tiene_comprobante": bool(d.comprobante),
        "depositado_en": (d.depositado_en.isoformat()
                          if d.depositado_en else None),
        "despacho": (d.despachado_por.nombre if d.despachado_por else None),
        "corregido_en": (d.corregido_en.isoformat()
                         if d.corregido_en else None),
        "corregido_por": (d.corregido_por.nombre if d.corregido_por else None),
        "solicitudes": [f.id for f in d.solicitudes],
    }


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


@router.post("/finanzas/transferencias/cancelar",
             summary="Finanzas confirma que el deposito no salio")
def cancelar_desde_finanzas(equipo_id: int, persona_id: int,
                            db: Session = Depends(get_db),
                            usuario: m.Usuario = Depends(FINANZAS)):
    """El consultor pidio echar atras un deposito que ya estaba aqui.

    Lo cierra finanzas y no el consultor porque el unico que sabe si el
    dinero ya salio del banco es quien lo manda. Si ya habia salido,
    esto no se usa: se sube el comprobante como cualquier otro deposito
    y el sistema lo marca como llegado tarde.
    """
    equipo = _equipo(db, equipo_id)
    dias = _dias_vivos(equipo)
    solicitudes = (db.query(m.SolicitudTransferencia)
                   .join(m.AsignacionViatico,
                         m.SolicitudTransferencia.asignacion_id
                         == m.AsignacionViatico.id)
                   .filter(m.AsignacionViatico.persona_id == persona_id,
                           m.AsignacionViatico.jornada_id.in_(
                               [j.id for j in dias]),
                           m.SolicitudTransferencia.estatus.in_(EN_CAMINO))
                   .all())
    pedidas = [x for x in solicitudes if x.cancelacion_pedida_en]
    if not pedidas:
        raise HTTPException(409, {
            "mensaje": "Nadie pidio cancelar este deposito",
            "que_hacer": ("La cancelacion la pide el consultor desde el "
                          "panel de viaticos del equipo."),
        })

    monto = Decimal("0")
    for solicitud in pedidas:
        solicitud.estatus = m.EstatusTransferencia.CANCELADA
        monto += Decimal(str(solicitud.monto))
        viatico = solicitud.asignacion
        if viatico.estatus == m.EstatusViatico.SOLICITADO:
            viatico.estatus = m.EstatusViatico.ASIGNADO

    auditoria.registrar(db, usuario, equipo.servicio, "cancelar deposito",
                        f"{monto} · {equipo.alias}, {len(pedidas)} "
                        f"solicitud(es) que el consultor pidio detener")
    db.commit()
    return {"resultado": "cancelado", "solicitudes": len(pedidas),
            "monto": monto,
            "nota": "El consultor ya puede corregir el monto o borrar el dia"}


@router.post("/finanzas/depositar", summary="Finanzas registra el deposito")
async def depositar(equipo_id: int = Form(...), persona_id: int = Form(...),
                    referencia: str = Form(...),
                    archivo: UploadFile = File(...),
                    anio: int | None = Form(None), mes: int | None = Form(None),
                    db: Session = Depends(get_db),
                    usuario: m.Usuario = Depends(FINANZAS)):
    """Un solo movimiento por persona, aunque por dentro sean varios dias.

    La referencia y el comprobante son obligatorios: es lo que contesta
    "¿ya me depositaron?" sin tener que creerle a nadie, y lo que sirve
    para rastrear el dinero en el banco si no llego.
    """
    equipo = _equipo(db, equipo_id)
    dias = _dias_vivos(equipo)
    # Acotado al mes cuando viene: asi es como la bandeja del implantado
    # presenta cada renglon, y confirmar de mas seria dar por depositado
    # un mes que nadie reviso.
    if anio and mes:
        dias = [j for j in dias
                if j.fecha.year == anio and j.fecha.month == mes]
        if not dias:
            raise HTTPException(404, f"Ese equipo no tiene dias en "
                                     f"{mes:02d}/{anio}")

    def _suyas(estatus) -> list:
        return (db.query(m.SolicitudTransferencia)
                .join(m.AsignacionViatico,
                      m.SolicitudTransferencia.asignacion_id
                      == m.AsignacionViatico.id)
                .filter(m.AsignacionViatico.persona_id == persona_id,
                        m.AsignacionViatico.jornada_id.in_(
                            [j.id for j in dias]),
                        m.SolicitudTransferencia.estatus.in_(estatus))
                .all())

    solicitudes = _suyas((m.EstatusTransferencia.PENDIENTE,
                          m.EstatusTransferencia.ENVIADA))

    # La puerta de atras. El consultor cancelo el deposito mientras
    # finanzas estaba en el banco, y finanzas vuelve con la referencia y
    # el comprobante de una transferencia que ya se hizo. Antes esto era
    # un 404 y el dinero se quedaba sin donde registrarse; lo que no se
    # puede registrar se arregla por fuera, y lo que se arregla por
    # fuera no se audita.
    #
    # Se acepta y queda marcado, para que el consultor lo vea y decida
    # si lo aplica o lo pide de vuelta.
    tardio = False
    if not solicitudes:
        solicitudes = [x for x in _suyas((m.EstatusTransferencia.CANCELADA,))
                       if not x.deposito_id]
        tardio = bool(solicitudes)

    if not solicitudes:
        raise HTTPException(404, {
            "mensaje": "No hay depositos pendientes de esa persona",
            "que_hacer": ("Si ya le transferiste, habla con el consultor: el "
                          "dia o el servicio pudo haberse borrado y el "
                          "deposito necesita a que colgarse."),
        })

    comprobante = await imagenes.leer(archivo)
    deposito = motor_depositos.registrar(
        db, [x.id for x in solicitudes], referencia, comprobante,
        despachado_por_id=usuario.persona_id, sobre_cancelada=tardio)

    auditoria.registrar(db, usuario, equipo.servicio, "deposito bancario",
                        f"{deposito.monto} {deposito.moneda.value} a "
                        f"{deposito.persona.nombre}, ref {deposito.referencia}"
                        + (" · SOBRE SOLICITUD CANCELADA" if tardio else ""))
    db.commit()
    db.refresh(deposito)
    _avisar_sin_tumbar(push.avisar_deposito, db, deposito)
    db.commit()
    return {"resultado": "depositado", "monto": deposito.monto,
            "deposito_id": deposito.id,
            "depositos": len(deposito.solicitudes),
            "sobre_cancelada": tardio,
            "nota": ("El consultor ya habia cancelado este deposito. Queda "
                     "registrado y marcado: el consultor tiene que aplicarlo "
                     "o pedir la devolucion."
                     if tardio else
                     "Ya aparece en la app del personal como saldo disponible")}

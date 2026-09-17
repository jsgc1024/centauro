"""El deposito bancario: lo que de verdad sale del banco.

Finanzas paga un deposito por persona y equipo. Son varios dias, varias
solicitudes, y una sola transferencia. Ese hecho --la transferencia-- no
vivia en ninguna tabla: la bandeja lo armaba al vuelo agrupando
solicitudes, y por eso no habia a que colgarle la referencia ni el
comprobante del banco.

Aqui se registra, y al registrarlo se confirman de golpe todas las
solicitudes que cubre. Un deposito, un registro, un comprobante.

Las reglas de la casa, escritas una sola vez:

  - Se deposita lo solicitado, ni un peso mas ni uno menos. El monto lo
    decide el consultor; finanzas ejecuta. Si esta mal, se corrige en la
    solicitud y se vuelve a pedir. Asi el desglose que el agente tiene
    que comprobar siempre cuadra con lo que recibio.
  - Referencia y comprobante, los dos, para poder registrar. Es lo mismo
    que ya exigen las compras especiales.
  - La evidencia se corrige siempre. El deposito se anula solo mientras
    el agente no haya subido ningun comprobante de gasto: despues de eso
    quedarian comprobaciones colgando de un deposito que ya no existe.
"""
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import reloj

# Lo que la solicitud puede ser cuando se va a depositar. Una cancelada
# no se paga, y una confirmada ya se pago.
PAGABLES = (m.EstatusTransferencia.PENDIENTE, m.EstatusTransferencia.ENVIADA)


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def por_pagar(db: Session, solicitud_ids: list[int]) -> list:
    """Las solicitudes de un deposito, validadas como grupo.

    Tienen que ser de la misma persona y del mismo equipo: eso es lo que
    hace que la transferencia quede amarrada a un servicio.
    """
    if not solicitud_ids:
        raise HTTPException(400, "Un deposito necesita al menos una solicitud")

    filas = (db.query(m.SolicitudTransferencia)
             .filter(m.SolicitudTransferencia.id.in_(solicitud_ids)).all())
    faltan = set(solicitud_ids) - {f.id for f in filas}
    if faltan:
        raise HTTPException(404, {
            "mensaje": "Hay solicitudes que no existen",
            "solicitudes": sorted(faltan)})

    ya = [f.id for f in filas if f.deposito_id]
    if ya:
        raise HTTPException(409, {
            "mensaje": "Esas solicitudes ya se depositaron",
            "que_hacer": "Recarga la bandeja: alguien mas las pago.",
            "solicitudes": ya})

    fuera = [f.id for f in filas if f.estatus not in PAGABLES]
    if fuera:
        raise HTTPException(409, {
            "mensaje": "Hay solicitudes que ya no se pueden pagar",
            "solicitudes": fuera})

    personas = {f.asignacion.persona_id for f in filas}
    equipos = {f.asignacion.jornada.equipo_id for f in filas}
    if len(personas) > 1 or len(equipos) > 1:
        raise HTTPException(409, {
            "mensaje": ("Un deposito es de una sola persona y un solo "
                        "equipo"),
            "que_hacer": ("Si esa persona anda en dos servicios, son dos "
                          "depositos.")})
    return filas


def registrar(db: Session, solicitud_ids: list[int], referencia: str | None,
              comprobante: str | None = None,
              despachado_por_id: int | None = None,
              cuando: datetime | None = None,
              exige_evidencia: bool = True) -> m.DepositoBancario:
    """Finanzas ya transfirio. Aqui queda el hecho y su evidencia.

    `exige_evidencia` es falso en un solo caso: lo que llega ya
    confirmado del barrido por lote o de Odoo, donde no hay una persona
    subiendo una captura. Esos depositos existen igual —para que todo lo
    confirmado tenga a que colgarse— y salen marcados *sin comprobante*,
    que es mejor que no verlos.

    Desde la pantalla siempre se exige: ahi si hay quien la suba, y sin
    evidencia la unica prueba de que se pago es la palabra de quien dice
    que pago.
    """
    if exige_evidencia:
        if not (referencia or "").strip():
            raise HTTPException(400, {
                "mensaje": "Falta la referencia del banco",
                "que_hacer": ("Es con lo que se rastrea el dinero si el "
                              "agente dice que no le llego.")})
        if not (comprobante or "").strip():
            raise HTTPException(400, {
                "mensaje": "Falta el comprobante del deposito",
                "que_hacer": ("Sube la captura del banco. Sin evidencia, la "
                              "unica prueba de que se pago es la palabra de "
                              "quien lo hizo.")})

    filas = por_pagar(db, solicitud_ids)
    primera = filas[0]
    jornada = primera.asignacion.jornada

    deposito = m.DepositoBancario(
        persona_id=primera.asignacion.persona_id,
        equipo_id=jornada.equipo_id,
        monto=sum(_d(f.monto) for f in filas),
        moneda=primera.moneda,
        referencia=(referencia or "").strip() or None,
        comprobante=comprobante,
        # En hora del pais del servicio, como el resto de la operacion.
        depositado_en=reloj.ahora_de_la_jornada(db, jornada, cuando),
        despachado_por_id=despachado_por_id)
    db.add(deposito)
    db.flush()

    for fila in filas:
        fila.deposito_id = deposito.id
        fila.estatus = m.EstatusTransferencia.CONFIRMADA
        fila.referencia_odoo = deposito.referencia
        fila.confirmada_en = deposito.depositado_en
        fila.confirmada_por_id = despachado_por_id
        # El dinero ya esta con la persona: su app lo enseña como saldo.
        # Un segundo deposito no la regresa al principio: si ya estaba
        # comprobando o cerrada, ahi se queda.
        if fila.asignacion.estatus in (m.EstatusViatico.ASIGNADO,
                                       m.EstatusViatico.SOLICITADO):
            fila.asignacion.estatus = m.EstatusViatico.TRANSFERIDO

    db.flush()
    return deposito


def corregir(db: Session, deposito_id: int, referencia: str | None = None,
             comprobante: str | None = None,
             por_id: int | None = None) -> m.DepositoBancario:
    """Subir el archivo correcto es lo mas comun que pasa despues.

    Se permite siempre, y queda escrito quien lo cambio y cuando: una
    evidencia que se puede reemplazar sin dejar rastro no es evidencia.
    """
    deposito = db.get(m.DepositoBancario, deposito_id)
    if not deposito:
        raise HTTPException(404, f"No existe el deposito {deposito_id}")
    if referencia is None and comprobante is None:
        raise HTTPException(400, "No hay nada que corregir")

    if referencia is not None:
        if not referencia.strip():
            raise HTTPException(400, "La referencia no se puede dejar vacia")
        deposito.referencia = referencia.strip()
        for fila in deposito.solicitudes:
            fila.referencia_odoo = deposito.referencia
    if comprobante is not None:
        if not comprobante.strip():
            raise HTTPException(400, "El comprobante no se puede dejar vacio")
        deposito.comprobante = comprobante

    deposito.corregido_en = datetime.now()
    deposito.corregido_por_id = por_id
    db.flush()
    return deposito


def comprobaciones(db: Session, deposito: m.DepositoBancario) -> int:
    """Cuantos comprobantes de gasto colgo ya el agente de este dinero."""
    ids = [f.asignacion_id for f in deposito.solicitudes]
    if not ids:
        return 0
    return (db.query(m.Comprobante)
            .filter(m.Comprobante.asignacion_id.in_(ids)).count())


def anular(db: Session, deposito_id: int, motivo: str,
           por_id: int | None = None) -> dict:
    """Solo mientras el agente no haya comprobado nada.

    Despues de eso, anularlo dejaria comprobaciones colgando de un
    deposito que ya no existe, y la forma de arreglarlo seria peor que el
    error. Lo que corresponde entonces es una devolucion.
    """
    deposito = db.get(m.DepositoBancario, deposito_id)
    if not deposito:
        raise HTTPException(404, f"No existe el deposito {deposito_id}")
    if not (motivo or "").strip():
        raise HTTPException(400, {
            "mensaje": "Anular un deposito necesita un motivo",
            "que_hacer": ("Es la unica huella que queda de dinero que "
                          "salio del banco y se dio por no salido.")})

    cuantos = comprobaciones(db, deposito)
    if cuantos:
        raise HTTPException(409, {
            "mensaje": ("Este deposito ya no se puede anular: el agente ya "
                        f"subio {cuantos} comprobante(s) de gasto."),
            "que_hacer": ("Si el dinero tiene que regresar, se registra "
                          "como devolucion.")})

    devueltas = []
    for fila in list(deposito.solicitudes):
        fila.deposito_id = None
        fila.estatus = m.EstatusTransferencia.PENDIENTE
        fila.referencia_odoo = None
        fila.confirmada_en = None
        fila.confirmada_por_id = None
        fila.asignacion.estatus = m.EstatusViatico.SOLICITADO
        devueltas.append(fila.id)

    db.delete(deposito)
    db.flush()
    return {"anulado": deposito_id, "solicitudes": devueltas,
            "motivo": motivo.strip(), "por_id": por_id}

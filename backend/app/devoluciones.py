# -*- coding: utf-8 -*-
"""El dinero que regresa.

Dos casos, un solo camino: sobro dinero de los viaticos, o el servicio
se cancelo con el deposito ya hecho y hay que regresar todo.

Antes esto era una linea que sumaba al `monto_devuelto` y nada mas: sin
evidencia, sin quien lo registro, y con el monto viajando en la
direccion. Un dinero que vuelve sin comprobante es la palabra de quien
lo capturo, y eso no es un registro contable.

Ahora es la transferencia al reves, con la misma regla que el deposito:

  * la persona transfiere y declara, con referencia y comprobante;
  * finanzas confirma cuando lo ve entrar a la cuenta.

**Declarada no es confirmada.** Si lo declarado contara de una vez, la
deuda de la persona se apagaria sola --y con ella el plazo de
comprobacion-- por un dinero que la empresa todavia no ha visto. Es el
mismo defecto que tenia la app cuando decia "te depositaron" con dinero
autorizado, del otro lado del mostrador.
"""
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m

CERO = Decimal("0.00")
# El dinero se dice con sus centavos SIEMPRE. "Quedan 0" y "quedan 0.00"
# se leen distinto en una pantalla de finanzas: el primero parece un
# contador, el segundo un saldo. Y el que compara contra un monto no
# tiene por que adivinar cual de los dos le toco.
CENTAVOS = Decimal("0.01")


def _d(x) -> Decimal:
    return Decimal(str(x or 0)).quantize(CENTAVOS)


def declarado_pendiente(viatico: m.AsignacionViatico) -> Decimal:
    """Lo que ya dijo que transfirio y finanzas no ha confirmado.

    Cuenta para el tope: sin esto, alguien podria declarar tres veces
    los mismos mil pesos mientras finanzas revisa la primera.
    """
    return sum((_d(x.monto) for x in viatico.devoluciones
                if x.estatus == m.EstatusDevolucion.DECLARADA), CERO
               ).quantize(CENTAVOS)


def por_devolver(viatico: m.AsignacionViatico) -> Decimal:
    """Lo que todavia puede regresar de ese dia.

    Lo depositado de verdad --las rondas que finanzas confirmo, no el
    total del viatico-- menos lo comprobado, lo ya devuelto, lo
    declarado a la espera y lo que ya se resolvio de otra forma: el
    descuento a nomina y lo que absorbio la empresa (seccion 98). Antes
    el descuento no se restaba, y un viatico cerrado con descuento
    seguia ofreciendo "devolver" por el mismo dinero: la persona
    transferia, finanzas confirmaba, y quedaban el descuento y la
    devolucion sobre los mismos mil pesos.
    """
    from app import viaticos as motor_viaticos

    queda = (_d(motor_viaticos.depositado(viatico))
             - _d(viatico.monto_comprobado)
             - _d(viatico.monto_devuelto)
             - declarado_pendiente(viatico)
             - _d(viatico.monto_descontado)
             - _d(viatico.monto_absorbido))
    return queda.quantize(CENTAVOS) if queda > CERO else CERO


def por_devolver_del_bolson(db: Session, viatico: m.AsignacionViatico) -> Decimal:
    """Lo que sobra del viaje entero de esa persona, no de un dia.

    El dinero se deposita junto y se gasta junto: tres dias de 1,000
    con 900 de tickets cada uno sobran 300, y ningun dia por separado
    los aceptaba --cada uno decia "quedan 100"--. El tope de una
    devolucion es el del bolson (seccion 98).
    """
    from app import viaticos as motor_viaticos

    suyos = motor_viaticos.bolson_del_servicio(db, viatico)
    queda = sum((_d(motor_viaticos.depositado(v))
                 - _d(v.monto_comprobado) - _d(v.monto_devuelto)
                 - declarado_pendiente(v)
                 - _d(v.monto_descontado) - _d(v.monto_absorbido)
                 for v in suyos), CERO)
    return queda.quantize(CENTAVOS) if queda > CERO else CERO


def declarar(db: Session, viatico: m.AsignacionViatico, monto: Decimal,
             referencia: str | None, comprobante: str | None,
             quien_id: int | None, ahora: datetime,
             ya_confirmada: bool = False,
             confirmada_por_id: int | None = None) -> m.DevolucionViatico:
    """Queda anotado que ese dinero viene de regreso.

    `ya_confirmada` es para finanzas: cuando la transferencia ya entro y
    nadie la habia declarado, capturarla y confirmarla son el mismo
    acto. Sigue siendo una sola fila, con su evidencia y su sello.
    """
    if monto <= CERO:
        raise HTTPException(400, {
            "mensaje": "La devolucion tiene que ser mayor a cero",
            "que_hacer": ("Si hay que corregir una devolucion anterior se "
                          "rechaza esa y se captura la buena, para que "
                          "quede el rastro de las dos.")})

    if viatico.estatus == m.EstatusViatico.CANCELADO:
        raise HTTPException(409, "Ese viatico esta cancelado")
    # Lo cerrado ya se resolvio: lo que falto se fue a nomina como
    # descuento, o lo absorbio la empresa. Aceptar aqui una devolucion
    # seria cobrarlo dos veces (seccion 98).
    if viatico.estatus in (m.EstatusViatico.CERRADO,
                           m.EstatusViatico.DEVUELTO):
        raise HTTPException(409, {
            "mensaje": "Ese dinero ya esta cerrado: no se le puede devolver",
            "que_hacer": ("Si se cerro con descuento, lo que falto ya va en "
                          "la nomina. Hablale a tu consultor si no cuadra.")})

    # El tope es el del viaje entero de esa persona, no el de este dia:
    # el dinero se deposita junto y se gasta junto (seccion 98).
    tope = (por_devolver_del_bolson(db, viatico) if db is not None
            else por_devolver(viatico))
    if monto > tope:
        raise HTTPException(409, {
            "mensaje": "Esa devolucion pasa de lo que queda por devolver",
            "que_hacer": (f"De lo depositado quedan {tope} por devolver, "
                          f"descontando lo comprobado, lo ya devuelto y lo "
                          f"que esta esperando confirmacion."),
            "por_devolver": str(tope)})

    fila = m.DevolucionViatico(
        asignacion_id=viatico.id, monto=monto, moneda=viatico.moneda,
        referencia=(referencia or "").strip() or None,
        comprobante=comprobante,
        estatus=(m.EstatusDevolucion.CONFIRMADA if ya_confirmada
                 else m.EstatusDevolucion.DECLARADA),
        declarada_por_id=quien_id, declarada_en=ahora)
    if ya_confirmada:
        fila.confirmada_por_id = confirmada_por_id or quien_id
        fila.confirmada_en = ahora
        viatico.monto_devuelto = _d(viatico.monto_devuelto) + monto
    db.add(fila)
    db.flush()
    return fila


def confirmar(db: Session, devolucion: m.DevolucionViatico,
              quien_id: int | None, ahora: datetime) -> m.DevolucionViatico:
    """Finanzas la vio entrar. Hasta aqui el dinero no habia vuelto."""
    if devolucion.estatus != m.EstatusDevolucion.DECLARADA:
        raise HTTPException(409, {
            "mensaje": f"Esa devolucion ya esta {devolucion.estatus.value}",
            "que_hacer": "Si hay que corregirla, captura una nueva."})

    devolucion.estatus = m.EstatusDevolucion.CONFIRMADA
    devolucion.confirmada_por_id = quien_id
    devolucion.confirmada_en = ahora
    viatico = devolucion.asignacion
    viatico.monto_devuelto = _d(viatico.monto_devuelto) + _d(devolucion.monto)
    db.flush()
    return devolucion


def rechazar(db: Session, devolucion: m.DevolucionViatico,
             quien_id: int | None, motivo: str,
             ahora: datetime) -> m.DevolucionViatico:
    """No llego, o no cuadra.

    No se borra: la persona dijo que transfirio y eso queda, con el
    motivo por el que no se acepto. Una devolucion que desaparece deja
    la discusion sin papeles.
    """
    if devolucion.estatus != m.EstatusDevolucion.DECLARADA:
        raise HTTPException(409, {
            "mensaje": f"Esa devolucion ya esta {devolucion.estatus.value}",
            "que_hacer": "Solo se puede rechazar lo que esta esperando."})

    devolucion.estatus = m.EstatusDevolucion.RECHAZADA
    devolucion.motivo_rechazo = motivo.strip()
    devolucion.confirmada_por_id = quien_id
    devolucion.confirmada_en = ahora
    db.flush()
    return devolucion

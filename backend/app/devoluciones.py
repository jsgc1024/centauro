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
    """Lo que todavia puede regresar.

    Lo entregado menos lo comprobado, lo ya devuelto y lo declarado a la
    espera. El descuento no se resta aqui: ese dinero no vuelve como
    dinero, se cruza en nomina, y restarlo dos veces dejaria el tope
    corto.
    """
    queda = (_d(viatico.monto_total)
             - _d(viatico.monto_comprobado)
             - _d(viatico.monto_devuelto)
             - declarado_pendiente(viatico))
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

    tope = por_devolver(viatico)
    if monto > tope:
        raise HTTPException(409, {
            "mensaje": "Esa devolucion pasa de lo que queda por devolver",
            "que_hacer": (f"Se entregaron {_d(viatico.monto_total)}, hay "
                          f"{_d(viatico.monto_comprobado)} comprobados, "
                          f"{_d(viatico.monto_devuelto)} ya devueltos y "
                          f"{declarado_pendiente(viatico)} esperando "
                          f"confirmacion: quedan {tope}."),
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

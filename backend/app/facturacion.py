# -*- coding: utf-8 -*-
"""La factura que sale hacia Odoo.

Odoo era hasta hoy una entrada: nos mandaba el personal, la flota, las
capacitaciones y las unidades en taller. No salia nada. El estatus
`facturado` existia en el catalogo desde el primer dia y no lo escribia
nadie, asi que un servicio aprobado por finanzas se quedaba sin quien
dijera "ya se cobro".

Una factura por servicio (decision de Salvador, 20 sep): cada folio
tiene su factura y la rentabilidad cuadra sola. Sale con el visto bueno
del consultor --el termino general del servicio (decision del 22 sep)--
y finanzas aprueba despues; `facturado` es el ultimo eslabon, cuando las
dos cosas ya pasaron.

**Lo que se factura es lo EJECUTADO, no lo cotizado.** La cotizacion es
lo que se ofrecio; el ejecutado es lo que de verdad se presto, valuado
al tarifario del cliente, con sus horas extra y sin los dias que no se
trabajaron. Facturar lo cotizado seria cobrar un dia que se cancelo.

**El envio no puede tumbar la aprobacion.** El cierre ya quedo aprobado
cuando esto corre: si Odoo no contesta, el servicio se queda en la
bandeja de "por facturar" con el error a la vista y se reintenta. Un
envio que falla en silencio deja un servicio aprobado que nadie cobra.
"""
import logging
from datetime import datetime

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import cierre as motor_cierre
from app import models as m
from app.config import settings

registro = logging.getLogger("centauro.facturacion")


def hay_conexion() -> bool:
    return bool(settings.odoo_url)


def armar(db: Session, cierre: m.Cierre) -> dict:
    """Lo que se le manda a Odoo para que emita la factura.

    Va el detalle renglon por renglon --cada dia, cada equipo, cada
    recurso-- y no un total: el dia que el cliente pregunte por que son
    esos pesos, la respuesta tiene que estar en la factura y no en una
    hoja aparte que alguien arme a mano.
    """
    from app import cotizacion as cot

    servicio = cierre.servicio
    cotizacion = cot.vigente(db, servicio.id)
    if not cotizacion:
        raise HTTPException(409, "El servicio no tiene cotizacion autorizada")
    # Al tarifario del cliente, que es el precio que se le vendio.
    ejecutado = motor_cierre.ejecutado(db, servicio, cotizacion.tarifario_id)
    cliente = servicio.cliente

    return {
        # El folio de Centauro viaja siempre: es la llave para conciliar
        # las dos bases el dia que no cuadren.
        "referencia": servicio.folio,
        "cierre_id": cierre.id,
        "cliente": {
            "id_odoo": cliente.odoo_id if cliente else None,
            "nombre": cliente.nombre if cliente else None,
        },
        "moneda": cotizacion.moneda.value,
        "fecha": (cierre.enviado_en or cierre.aprobado_en
                  or datetime.now()).date().isoformat(),
        "total": str(ejecutado["total"]),
        "conceptos": [{
            "fecha": linea["fecha"],
            "equipo": linea["equipo"],
            "tipo": linea["tipo"],
            "descripcion": linea["descripcion"],
            "cantidad": linea["cantidad"],
            "importe": str(linea["importe"]),
            "horas_extra": linea.get("horas_extra") or 0,
        } for linea in ejecutado["detalle"]],
    }


def enviar(db: Session, cierre: m.Cierre) -> dict:
    """Manda la factura y guarda lo que conteste Odoo.

    No levanta excepcion nunca: devuelve que paso. Quien la llama ya
    tiene algo guardado que no puede perder.
    """
    if cierre.estatus == m.EstatusCierre.FACTURADO or cierre.facturado_en:
        # Salio con el visto bueno del consultor. Si finanzas ya aprobo,
        # el cierre queda facturado: es el ultimo eslabon.
        if cierre.estatus == m.EstatusCierre.APROBADO:
            cierre.estatus = m.EstatusCierre.FACTURADO
            db.flush()
        return {"resultado": "ya estaba facturado",
                "factura": cierre.factura_odoo}

    if cierre.estatus not in (m.EstatusCierre.ENVIADO_FINANZAS,
                              m.EstatusCierre.APROBADO):
        return {"resultado": "no se factura",
                "motivo": f"el cierre esta en {cierre.estatus.value}"}

    if not hay_conexion():
        cierre.factura_error = ("Odoo no esta configurado en este servidor. "
                                "Queda por facturar.")
        db.flush()
        return {"resultado": "sin conexion", "motivo": cierre.factura_error}

    try:
        cuerpo = armar(db, cierre)
    except Exception as error:                        # noqa: BLE001
        # Sin cotizacion vigente no hay a que precio facturar. Se dice y
        # se queda en la bandeja: es un dato que falta, no una falla de
        # la conexion.
        cierre.factura_error = str(getattr(error, "detail", error))[:400]
        db.flush()
        return {"resultado": "fallo", "motivo": cierre.factura_error}

    cabeceras = {}
    if settings.odoo_token:
        cabeceras["Authorization"] = f"Bearer {settings.odoo_token}"

    try:
        r = httpx.post(settings.odoo_url, json=cuerpo, headers=cabeceras,
                       timeout=settings.odoo_timeout)
        r.raise_for_status()
        datos = r.json() if r.content else {}
    except Exception as error:                        # noqa: BLE001
        # El texto entra a la bandeja tal cual, recortado: quien lo lea
        # tiene que poder decidir si reintenta o le habla a sistemas.
        cierre.factura_error = str(error)[:400]
        db.flush()
        registro.warning("no se pudo facturar %s: %s",
                         cierre.servicio.folio, error)
        return {"resultado": "fallo", "motivo": cierre.factura_error}

    # Odoo contesta con el folio de su factura. Si no lo manda, se
    # guarda igual como facturado --el documento existe alla-- pero se
    # dice que llego sin folio: es lo que habria que ir a buscar a mano.
    folio = (datos.get("factura") or datos.get("numero")
             or datos.get("name") or datos.get("id"))
    # Facturado es el ultimo eslabon: solo cuando finanzas ya aprobo. Si
    # la factura sale con el visto bueno del consultor, el cierre sigue
    # enviado a finanzas, con su folio ya puesto.
    if cierre.estatus == m.EstatusCierre.APROBADO:
        cierre.estatus = m.EstatusCierre.FACTURADO
    cierre.facturado_en = datetime.now()
    cierre.factura_odoo = str(folio)[:60] if folio else None
    cierre.factura_error = None if folio else "Odoo contesto sin folio"
    db.flush()
    return {"resultado": "facturado", "factura": cierre.factura_odoo}


def por_facturar(db: Session) -> list[dict]:
    """Lo aprobado que todavia no tiene factura.

    Es la bandeja que faltaba: sin ella, un servicio aprobado cuyo envio
    fallo se queda esperando para siempre y nadie se entera hasta que el
    cliente no paga.
    """
    filas = (db.query(m.Cierre)
             .filter(m.Cierre.estatus.in_((m.EstatusCierre.ENVIADO_FINANZAS,
                                           m.EstatusCierre.APROBADO)),
                     m.Cierre.facturado_en.is_(None))
             .order_by(m.Cierre.enviado_en).all())
    return [{
        "cierre_id": c.id,
        "estatus": c.estatus.value,
        "enviado_en": c.enviado_en.isoformat() if c.enviado_en else None,
        "servicio_id": c.servicio_id,
        "folio": c.servicio.folio,
        "cliente": (c.servicio.cliente.nombre
                    if c.servicio.cliente else None),
        "total": str(c.total_ejecutado),
        "aprobado_en": c.aprobado_en.isoformat() if c.aprobado_en else None,
        "error": c.factura_error,
    } for c in filas]

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


SIN_CONEXION = ("Odoo no esta configurado en este servidor. "
                "Queda por facturar.")


def hay_conexion() -> bool:
    return bool(settings.odoo_url)


def que_paso(error: str | None) -> str | None:
    """Por que no salio la factura, en una palabra que la pantalla sabe
    decir en tres idiomas: sin conexion, Odoo la rechazo, Odoo no
    contesto, o falta un dato de este lado."""
    if not error:
        return None
    if error == SIN_CONEXION:
        return "sin_conexion"
    if "Client error" in error or "Odoo contesto sin folio" in error:
        return "rechazada"
    if ("Server error" in error or "timed out" in error.lower()
            or "connect" in error.lower() or "timeout" in error.lower()):
        return "sin_respuesta"
    return "falta_dato"


def armar(db: Session, cierre: m.Cierre) -> dict:
    """Lo que se le manda a Odoo para que emita la factura.

    Va el detalle renglon por renglon --cada dia, cada equipo, cada
    recurso-- y no un total: el dia que el cliente pregunte por que son
    esos pesos, la respuesta tiene que estar en la factura y no en una
    hoja aparte que alguien arme a mano.
    """
    from app import cotizacion as cot

    # El mes del implantado se factura con los precios de su contrato,
    # no con una cotizacion por dia (seccion 56).
    if cierre.contrato_id:
        from app import cierre_mes
        return cierre_mes.armar_factura(db, cierre)

    servicio = cierre.servicio
    cotizacion = cot.vigente(db, servicio.id)
    if not cotizacion:
        raise HTTPException(409, "El servicio no tiene cotizacion autorizada")
    # Al tarifario del cliente, que es el precio que se le vendio.
    ejecutado = motor_cierre.ejecutado(db, servicio, cotizacion.tarifario_id)
    cliente = servicio.cliente
    conceptos = [{
        "fecha": linea["fecha"],
        "equipo": linea["equipo"],
        "tipo": linea["tipo"],
        "descripcion": linea["descripcion"],
        "cantidad": linea["cantidad"],
        "importe": str(linea["importe"]),
        "horas_extra": linea.get("horas_extra") or 0,
    } for linea in ejecutado["detalle"]]
    # Los gastos, en su propio renglon (seccion 59): a precio alzado, el
    # monto fijo de la propuesta; netos, lo comprobado valido. Un precio
    # alzado sin monto quiere decir que van dentro del precio: no se suma.
    viaticos = motor_cierre.viaticos_por_cobrar(db, servicio.id, cotizacion)
    if viaticos:
        conceptos.append({"fecha": None, "equipo": None,
                          "tipo": "viaticos",
                          "descripcion": ("Gastos a precio alzado"
                                          if cotizacion.viaticos_incluidos
                                          else "Gastos comprobados"),
                          "cantidad": 1, "importe": str(viaticos),
                          "horas_extra": 0})

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
        "total": str(ejecutado["total"] + viaticos),
        "conceptos": conceptos,
        # Si finanzas regreso el servicio con la factura ya hecha, esa se
        # anulo: esta la sustituye (seccion 59).
        "sustituye_a": cierre.factura_anulada,
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

    # Cada intento se cuenta: la bandeja dice "3 intentos, el ultimo a
    # las 09:40", que es lo que decide si se reintenta o se llama a
    # sistemas.
    cierre.factura_intentos = (cierre.factura_intentos or 0) + 1
    cierre.factura_intento_en = datetime.now()

    if not hay_conexion():
        cierre.factura_error = SIN_CONEXION
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
    """Lo que ya tiene visto bueno y todavia no tiene factura.

    Es la bandeja que faltaba: sin ella, un servicio aprobado cuyo envio
    fallo se queda esperando para siempre y nadie se entera hasta que el
    cliente no paga.
    """
    filas = (db.query(m.Cierre)
             .filter(m.Cierre.estatus.in_((m.EstatusCierre.ENVIADO_FINANZAS,
                                           m.EstatusCierre.APROBADO)),
                     m.Cierre.facturado_en.is_(None))
             .order_by(m.Cierre.enviado_en).all())
    return [renglon(db, c) for c in filas]


def renglon(db: Session, c: m.Cierre) -> dict:
    """Un cierre como lo lee finanzas en su bandeja."""
    def iso(momento):
        return momento.isoformat() if momento else None

    servicio = c.servicio
    consultor = (db.get(m.Persona, servicio.consultor_id)
                 if servicio.consultor_id else None)
    # En que moneda se factura: la de la cotizacion en el eventual, la
    # del pais en el mes del implantado.
    moneda = None
    if not c.contrato_id:
        from app import cotizacion as cot
        vigente = cot.vigente(db, servicio.id)
        moneda = vigente.moneda.value if vigente else None
    if moneda is None:
        pais = db.get(m.Pais, servicio.pais_id)
        moneda = pais.moneda_local.value if pais else None
    return {
        "cierre_id": c.id,
        "estatus": c.estatus.value,
        "enviado_en": iso(c.enviado_en),
        "visto_bueno_en": iso(c.visto_bueno_en or c.enviado_en),
        "dentro_de_plazo": c.dentro_de_plazo,
        "servicio_id": c.servicio_id,
        "tipo": servicio.tipo.value,
        "folio": servicio.folio,
        # El mes, en el implantado: el mismo folio factura mes con mes.
        "contrato_id": c.contrato_id,
        "periodo": (f"{c.contrato.mes:02d}/{c.contrato.anio}"
                    if c.contrato_id else None),
        "anio": c.contrato.anio if c.contrato_id else None,
        "mes": c.contrato.mes if c.contrato_id else None,
        "cliente": servicio.cliente.nombre if servicio.cliente else None,
        "consultor": consultor.nombre if consultor else None,
        "consultor_id": servicio.consultor_id,
        "total": str(c.total_ejecutado),
        "moneda": moneda,
        "aprobado_en": iso(c.aprobado_en),
        "factura": c.factura_odoo,
        "factura_anulada": c.factura_anulada,
        "error": c.factura_error,
        "que_paso": que_paso(c.factura_error),
        "intentos": c.factura_intentos or 0,
        "ultimo_intento": iso(c.factura_intento_en),
        "devuelto_en": iso(c.devuelto_en),
    }


# ---------------------------------------------------------------- la bandeja

def gastos_del_cierre(db: Session, cierre: m.Cierre) -> dict:
    """Cuanto de lo que se factura son gastos, y con que trato: la
    bandeja dice "con $1,750 de gastos" y si van a precio alzado."""
    from decimal import Decimal

    if cierre.contrato_id:
        from app import cierre_mes
        contrato = cierre.contrato
        alzado = contrato.viaticos_incluidos
        if alzado:
            monto = Decimal(str(contrato.gastos_mes or 0))
        else:
            monto = sum((Decimal(str(v.monto_comprobado or 0))
                         for v in cierre_mes.viaticos_del_mes(db, contrato)),
                        Decimal("0"))
    else:
        from app import cotizacion as cot
        vigente = cot.vigente(db, cierre.servicio_id)
        if not vigente:
            return {"modo": None, "monto": Decimal("0")}
        alzado = vigente.viaticos_incluidos
        monto = motor_cierre.viaticos_por_cobrar(db, cierre.servicio_id,
                                                 vigente)
    return {"modo": motor_cierre.modo_de_gastos(alzado), "monto": monto}


def bandeja(db: Session, ahora: datetime | None = None) -> dict:
    """La pantalla de Facturacion de finanzas, completa.

    Por aprobar: lo que ya tiene el visto bueno del consultor. Por
    facturar: lo que Odoo no acepto, con lo que dijo. Cerrados: lo que
    finanzas ya cerro este mes. Un implantado va por mes.
    """
    from decimal import Decimal
    from app import comisiones

    ahora = ahora or datetime.now()
    primero = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def con_gastos(c):
        return {**renglon(db, c), "gastos": gastos_del_cierre(db, c)}

    aprobar = (db.query(m.Cierre)
               .filter(m.Cierre.estatus == m.EstatusCierre.ENVIADO_FINANZAS)
               .order_by(m.Cierre.enviado_en).all())
    cerrados = (db.query(m.Cierre)
                .filter(m.Cierre.estatus.in_((m.EstatusCierre.APROBADO,
                                              m.EstatusCierre.FACTURADO)),
                        m.Cierre.aprobado_en >= primero)
                .order_by(m.Cierre.aprobado_en.desc()).all())
    facturar = por_facturar(db)

    def suma(filas):
        return sum((Decimal(str(c.total_ejecutado or 0)) for c in filas),
                   Decimal("0"))

    return {
        "momento": ahora.isoformat(),
        "odoo_configurado": hay_conexion(),
        "resumen": {
            "por_aprobar": {"cuantos": len(aprobar), "monto": suma(aprobar)},
            "por_facturar": {"cuantos": len(facturar)},
            "cerrados": {"cuantos": len(cerrados), "monto": suma(cerrados),
                         "mes": ahora.month, "anio": ahora.year},
        },
        "por_aprobar": [con_gastos(c) for c in aprobar],
        "por_facturar": facturar,
        "cerrados": [{**renglon(db, c),
                      "comision": comisiones.del_cierre(db, c)}
                     for c in cerrados],
    }

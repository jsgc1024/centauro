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
import re
from datetime import date, datetime, time
from decimal import Decimal

import httpx
from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import cierre as motor_cierre
from app import models as m
from app import odoo_facturacion
from app import reloj
from app import tipo_cambio
from app.config import settings

registro = logging.getLogger("centauro.facturacion")


SIN_CONEXION = ("Odoo no esta configurado en este servidor. "
                "Queda por facturar.")


def hay_conexion() -> bool:
    return bool(settings.odoo_url)


def que_paso(error: str | None) -> str | None:
    """Por que no salio la factura, en una palabra que la pantalla sabe
    decir en tres idiomas: sin conexion, Odoo la rechazo, Odoo no
    contesto, o falta un dato de este lado. Y los de la prefactura
    (seccion 117): falta la llave, la anterior sigue viva en Odoo, o no
    cuadra con el visto bueno."""
    if not error:
        return None
    if error == SIN_CONEXION:
        return "sin_conexion"
    # Los de la prefactura van antes: los de abajo buscan «connect» en el
    # texto, y estos lo dicen.
    of = odoo_facturacion
    if error == of.SIN_LLAVE:
        return "sin_llave"
    if error.startswith(of.FALTA_DATO):
        return "falta_dato"
    if error.startswith(of.ANTERIOR_VIVA.split("(")[0]):
        return "anterior_viva"
    if error.startswith(of.NO_CUADRA_VB.split("{")[0]):
        return "no_cuadra"
    if (error.startswith(of.PREFACTURA_CANCELADA.split("#")[0])
            and ("se canceló" in error or "ya no existe" in error)):
        return "cancelada_en_odoo"
    if error.startswith(of.NO_SE_ENTIENDE) or error.startswith("Odoo no contesto"):
        return "sin_respuesta"
    if error.startswith("Odoo rechazo la llave"):
        return "rechazada"
    codigo = re.match(r"Odoo contesto (\d)\d\d", error)
    if codigo:
        return "sin_respuesta" if codigo.group(1) == "5" else "rechazada"
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
    cliente = servicio.cliente
    if motor_cierre.se_cobra_completo(cierre):
        # La cancelacion que se cobra completa (seccion 105, decision 1 de
        # Salvador): la factura lleva la cotizacion autorizada tal cual,
        # renglon por renglon, con los dias que ya no se trabajaron. Los
        # gastos van aparte, con su trato, como siempre.
        conceptos = [{
            "fecha": linea.fecha.isoformat(),
            "equipo": linea.equipo_clave,
            "tipo": linea.tipo.value,
            "descripcion": linea.descripcion,
            "cantidad": linea.cantidad,
            "importe": str(Decimal(str(linea.subtotal))),
            "horas_extra": 0,
        } for linea in sorted(cotizacion.lineas,
                              key=lambda l: (l.fecha, l.equipo_clave, l.id))
            if linea.tipo != m.TipoLinea.VIATICOS]
        total_servicio = (Decimal(str(cotizacion.total))
                          - motor_cierre.gastos_cotizados(cotizacion))
        nota = "Servicio cancelado: se cobra completo por decision de operaciones"
    else:
        # Al tarifario del cliente, que es el precio que se le vendio.
        ejecutado = motor_cierre.ejecutado(db, servicio, cotizacion.tarifario_id,
                                           cot.con_paquetes(db, cotizacion))
        conceptos = [{
            "fecha": linea["fecha"],
            "equipo": linea["equipo"],
            "tipo": linea["tipo"],
            "descripcion": linea["descripcion"],
            "cantidad": linea["cantidad"],
            "importe": str(linea["importe"]),
            "horas_extra": linea.get("horas_extra") or 0,
        } for linea in ejecutado["detalle"]]
        total_servicio = ejecutado["total"]
        nota = None
    # Los gastos, en su propio renglon (seccion 59): a precio alzado, el
    # monto fijo de la propuesta; netos, lo comprobado valido. Un precio
    # alzado sin monto quiere decir que van dentro del precio: no se suma.
    viaticos = motor_cierre.viaticos_por_cobrar(db, servicio.id, cotizacion)
    if viaticos:
        gastos = {"fecha": None, "equipo": None, "tipo": "viaticos",
                  "descripcion": ("Gastos a precio alzado"
                                  if cotizacion.viaticos_incluidos
                                  else "Gastos comprobados"),
                  "cantidad": 1, "importe": str(viaticos), "horas_extra": 0}
        # Netos en otra moneda (seccion 82): se pagaron en pesos y se
        # facturan en dolares al tipo de cambio del visto bueno. El renglon
        # lleva de donde sale la cifra, igual que el desglose del cliente.
        otra, tc = motor_cierre.tipo_de_cambio_de_gastos(db, servicio,
                                                         cotizacion)
        if otra and tc and not cotizacion.viaticos_incluidos:
            gastos["origen"] = origen_de_gastos(
                motor_cierre.viaticos_por_cobrar_local(db, servicio.id,
                                                       cotizacion),
                tipo_cambio.local_del_pais(db, servicio.pais_id), tc["tasa"])
            gastos["descripcion"] += descripcion_del_origen(gastos["origen"])
        conceptos.append(gastos)

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
        "total": str(total_servicio + viaticos),
        "conceptos": conceptos,
        # Si finanzas regreso el servicio con la factura ya hecha, esa se
        # anulo: esta la sustituye (seccion 59).
        "sustituye_a": cierre.factura_anulada,
        # Por que se cobra lo que no se trabajo (seccion 105).
        "nota": nota,
    }


def origen_de_gastos(monto_local, local, tasa) -> dict:
    """De donde sale el renglon de gastos de una factura en otra moneda:
    lo que se pago, en que moneda, y el tipo de cambio con que se paso
    (seccion 82). Lo mismo para el eventual y para el mes del implantado."""
    return {"moneda": local.value if hasattr(local, "value") else local,
            "importe": str(monto_local),
            "tipo_cambio": tipo_cambio.texto(tasa)}


def descripcion_del_origen(origen: dict) -> str:
    """" (MXN 2,204.00 al tipo de cambio 17.50)", para el renglon."""
    return (f" ({origen['moneda']} {Decimal(origen['importe']):,.2f} al tipo "
            f"de cambio {tipo_cambio.corto(origen['tipo_cambio'])})")


def _mandar_sin_reventar(db: Session, cierre: m.Cierre,
                         primera_vez: bool) -> dict:
    """`odoo_facturacion.mandar` dentro de un punto de guardado: si algo
    inesperado revienta a medio camino --no un «Odoo no contesto», que
    `mandar` ya atrapa--, se deshace solo lo suyo y el cierre queda como
    un intento fallido mas, con su error a la vista y en el reintento de
    cada hora (seccion 127, hallazgo r3-08). Antes el error tiraba la
    peticion entera y, con el visto bueno ya guardado, el cierre
    aparecia como «visto bueno de antes de la conexion», fuera del
    reintento y con «Mandar a Odoo» preguntando si ya se facturo a
    mano. Lo de la base (la conexion que se cae) sigue subiendo: ahi no
    hay nada que anotar."""
    from sqlalchemy.exc import SQLAlchemyError

    punto = db.begin_nested()
    try:
        resultado = odoo_facturacion.mandar(db, cierre, primera_vez=primera_vez)
        punto.commit()
        return resultado
    except SQLAlchemyError:
        punto.rollback()
        raise
    except Exception as error:                        # noqa: BLE001
        punto.rollback()
        registro.exception("la prefactura de %s reventó al mandarla",
                           cierre.servicio.folio)
        return odoo_facturacion.anotar_fallo(
            db, cierre, f"{odoo_facturacion.NO_SE_ENTIENDE} {error}"[:400])


def enviar(db: Session, cierre: m.Cierre, usuario: m.Usuario | None = None,
           primera_vez: bool = True) -> dict:
    """Manda la factura y guarda lo que conteste Odoo.

    No levanta excepcion nunca: devuelve que paso. Quien la llama ya
    tiene algo guardado que no puede perder.

    Con la llave de la factura (seccion 117) lo que sale es la prefactura
    en borrador (`odoo_facturacion.mandar`): el facturista la timbra en
    Odoo y el cierre sigue por facturar hasta entonces. `usuario`: quien
    la hizo salir, para la bitacora del servicio. `primera_vez=False`
    --la aprobacion de finanzas-- solo reintenta la que ya se intento.
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

    if sin_cobro(cierre):
        # Nada que facturar (seccion 131, decision 10): el mes sin dias
        # trabajados se cobro en cero. No sale prefactura ni factura; al
        # aprobarlo finanzas, el cierre queda facturado sin folio.
        if cierre.estatus == m.EstatusCierre.APROBADO:
            cierre.estatus = m.EstatusCierre.FACTURADO
            cierre.facturado_en = reloj.ahora_del_servicio(db, cierre.servicio)
            cierre.factura_error = None
            db.flush()
        return {"resultado": "nada que facturar", "factura": None}

    if odoo_facturacion.hay_llave():
        resultado = _mandar_sin_reventar(db, cierre, primera_vez)
        if usuario is not None and resultado["resultado"] == "en odoo":
            from app import auditoria
            auditoria.registrar(
                db, usuario, cierre.servicio, "prefactura en odoo",
                f"{_de_que(cierre)}: borrador #{resultado['prefactura']}, "
                f"{Decimal(resultado['total']):,.2f} {resultado['moneda']} "
                f"antes de IVA"
                + ("" if resultado["nueva"] else ", ya estaba en Odoo"))
            db.flush()
        return resultado

    # Cada intento se cuenta: la bandeja dice "3 intentos, el ultimo a
    # las 09:40", que es lo que decide si se reintenta o se llama a
    # sistemas. En hora del pais del servicio, como los demas sellos del
    # cierre (seccion 101): la de la maquina no es la de quien lo lee.
    ahora = reloj.ahora_del_servicio(db, cierre.servicio)
    cierre.factura_intentos = (cierre.factura_intentos or 0) + 1
    cierre.factura_intento_en = ahora

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

    # Odoo contesta con el folio de su factura. Sin folio no hay factura
    # que anotar (seccion 101): el cierre se queda por facturar con el
    # error a la vista, y desde la bandeja se reintenta o se anota a
    # mano el folio que se vaya a buscar a Odoo. Antes quedaba
    # "facturado" sin factura, fuera de la bandeja, y ni "Mandar otra
    # vez" ni "Ya se facturo en Odoo" lo aceptaban.
    folio = (datos.get("factura") or datos.get("numero")
             or datos.get("name") or datos.get("id"))
    if not folio:
        cierre.factura_error = "Odoo contesto sin folio"
        db.flush()
        registro.warning("Odoo contesto sin folio para %s",
                         cierre.servicio.folio)
        return {"resultado": "fallo", "motivo": cierre.factura_error}
    # Facturado es el ultimo eslabon: solo cuando finanzas ya aprobo. Si
    # la factura sale con el visto bueno del consultor, el cierre sigue
    # enviado a finanzas, con su folio ya puesto.
    if cierre.estatus == m.EstatusCierre.APROBADO:
        cierre.estatus = m.EstatusCierre.FACTURADO
    # En hora del pais del servicio: de esta fecha salen el mes del
    # historial y el reloj del archivo de comprobantes.
    cierre.facturado_en = ahora
    cierre.factura_odoo = str(folio)[:60]
    cierre.factura_error = None
    db.flush()
    return {"resultado": "facturado", "factura": cierre.factura_odoo}


# ---------------------------------------------------------------- a mano

LARGO_FOLIO = 60
SE_FACTURA = (m.EstatusCierre.ENVIADO_FINANZAS, m.EstatusCierre.APROBADO)


def anotar(db: Session, cierre: m.Cierre, folio: str | None,
           fecha: date | None, usuario: m.Usuario) -> dict:
    """La factura que finanzas hizo en Odoo, anotada aqui (seccion 96).

    Decision 5 de Salvador (28 sep): mientras la factura no se conecta
    con Odoo, finanzas la hace alla y aqui anota su folio y su fecha. El
    cierre queda como si Odoo la hubiera devuelto: sale de por facturar,
    su folio se ve en facturacion y en el historial, el aprobado pasa a
    facturado, y cuando la conexion llegue no se vuelve a mandar --`enviar`
    ve que ya esta--.

    La anotada a mano se corrige aqui mismo, con lo de antes en la
    bitacora; la que llego de Odoo se corrige en Odoo. No confirma.
    """
    from app import auditoria, reloj

    folio = " ".join((folio or "").split())
    if not folio:
        raise HTTPException(400, "Escribe el folio de la factura.")
    if len(folio) > LARGO_FOLIO:
        raise HTTPException(400, f"El folio de la factura es demasiado "
                                 f"largo: hasta {LARGO_FOLIO} caracteres.")
    if fecha is None:
        raise HTTPException(400, "Pon la fecha de la factura.")
    if fecha > reloj.Relojes(db).hoy(cierre.servicio.pais_id):
        raise HTTPException(400, "La fecha de la factura no puede ser "
                                 "despues de hoy.")

    corrige = bool(cierre.facturado_en or cierre.factura_odoo)
    if corrige and not cierre.factura_anotada_por_id:
        raise HTTPException(409, {
            "mensaje": "Esta factura llego de Odoo: se corrige en Odoo.",
            "que_hacer": "Aqui solo se corrige la que se anoto a mano.",
        })
    if not corrige and cierre.estatus not in SE_FACTURA:
        raise HTTPException(409, {
            "mensaje": (f"Este cierre todavia no se factura: esta en "
                        f"{motor_cierre.nombre_estatus(cierre.estatus)}"),
            "que_hacer": ("Se factura cuando el consultor da el visto "
                          "bueno y lo manda a finanzas."),
        })

    # Una factura es de un solo servicio --o de un solo mes del
    # implantado--, y la anulada no se vuelve a usar: en Odoo sigue
    # siendo la anulada.
    bajo = folio.lower()
    otro = (db.query(m.Cierre)
            .filter(m.Cierre.id != cierre.id,
                    or_(func.lower(m.Cierre.factura_odoo) == bajo,
                        func.lower(m.Cierre.factura_anulada) == bajo))
            .first())
    if otro:
        raise HTTPException(409, {
            "mensaje": (f"El folio {folio} ya es de la factura de "
                        f"{_de_que(otro)}"),
            "que_hacer": "Revisa el folio en Odoo: cada factura es de un "
                         "solo servicio.",
        })
    if cierre.factura_anulada and cierre.factura_anulada.lower() == bajo:
        raise HTTPException(409, {
            "mensaje": (f"El folio {folio} es de la factura que se anulo "
                        f"al regresar este servicio"),
            "que_hacer": "La factura nueva lleva otro folio en Odoo.",
        })

    antes = (cierre.factura_odoo,
             cierre.facturado_en.date() if cierre.facturado_en else None)
    cierre.factura_odoo = folio
    cierre.facturado_en = datetime.combine(fecha, time())
    cierre.factura_error = None
    cierre.factura_anotada_por_id = usuario.persona_id
    # Facturado es el ultimo eslabon: solo cuando finanzas ya aprobo. Si
    # todavia no, el cierre sigue por aprobar, ya con su folio, y al
    # aprobarlo pasa a facturado.
    if cierre.estatus == m.EstatusCierre.APROBADO:
        cierre.estatus = m.EstatusCierre.FACTURADO

    ahora = f"{folio} del {fecha:%d/%m/%Y}"
    if corrige:
        de_antes = (f"{antes[0] or 'sin folio'} del {antes[1]:%d/%m/%Y}"
                    if antes[1] else (antes[0] or "sin folio"))
        auditoria.registrar(db, usuario, cierre.servicio, "corregir factura",
                            f"{_de_que(cierre)}: {de_antes} -> {ahora}, "
                            f"anotada a mano")
    else:
        auditoria.registrar(db, usuario, cierre.servicio, "anotar factura",
                            f"{_de_que(cierre)}: {ahora}, hecha en Odoo y "
                            f"anotada a mano")
    db.flush()
    return {**renglon(db, cierre), "corregida": corrige}


def _de_que(cierre: m.Cierre) -> str:
    """El folio del servicio, y el mes si es de un implantado."""
    if cierre.contrato_id:
        return (f"{cierre.servicio.folio} {cierre.contrato.mes:02d}/"
                f"{cierre.contrato.anio}")
    return cierre.servicio.folio


def sin_cobro(cierre: m.Cierre) -> bool:
    """El cierre que se mando en cero (seccion 131, decision 10): el mes
    sin dias trabajados. No tiene nada que facturar."""
    return (cierre.total_ejecutado is not None
            and Decimal(str(cierre.total_ejecutado)) == Decimal("0"))


def sin_factura(db: Session) -> list[m.Cierre]:
    """Los cierres que ya tienen visto bueno y todavia no tienen factura.
    El que se cobro en cero no espera ninguna (decision 10)."""
    return [c for c in (db.query(m.Cierre)
                        .filter(m.Cierre.estatus.in_((
                            m.EstatusCierre.ENVIADO_FINANZAS,
                            m.EstatusCierre.APROBADO)),
                            m.Cierre.facturado_en.is_(None))
                        .order_by(m.Cierre.enviado_en).all())
            if not sin_cobro(c)]


def por_facturar(db: Session) -> list[dict]:
    """Lo que ya tiene visto bueno y todavia no tiene factura.

    Es la bandeja que faltaba: sin ella, un servicio aprobado cuyo envio
    fallo se queda esperando para siempre y nadie se entera hasta que el
    cliente no paga.
    """
    return [renglon(db, c) for c in sin_factura(db)]


def de_antes(c: m.Cierre, llave: bool | None = None) -> bool:
    """Si tuvo su visto bueno antes de la llave de la factura: su
    prefactura no sale sola (seccion 117), la manda finanzas si toca."""
    if llave is None:
        llave = odoo_facturacion.hay_llave()
    return bool(llave and c.enviado_en and not c.prefactura_desde
                and not c.prefactura_odoo_id)


def renglon(db: Session, c: m.Cierre) -> dict:
    """Un cierre como lo lee finanzas en su bandeja."""
    def iso(momento):
        return momento.isoformat() if momento else None

    antes = de_antes(c)

    servicio = c.servicio
    consultor = (db.get(m.Persona, servicio.consultor_id)
                 if servicio.consultor_id else None)
    anoto = (db.get(m.Persona, c.factura_anotada_por_id)
             if c.factura_anotada_por_id else None)
    aprobo = (db.get(m.Persona, c.aprobado_por_id)
              if c.aprobado_por_id else None)
    # En que moneda se factura: la de la cotizacion en el eventual, la
    # de los precios del mes en el implantado (seccion 82).
    moneda = motor_cierre.moneda_del_cierre(db, c)
    moneda = moneda.value if moneda else None
    # Lo aprobado sin factura se puede regresar (seccion 131, decision 9
    # de Salvador): la pantalla dice quien lo aprobo y como esta su
    # comision, que se cancela con el regreso si no entro a un corte.
    aprobado = c.estatus == m.EstatusCierre.APROBADO and not c.factura_odoo
    comision = None
    if aprobado:
        generada = motor_cierre.comision_del_cierre(db, c)
        if generada is not None:
            comision = {"estatus": generada.estatus.value,
                        "monto": str(generada.monto),
                        "moneda": generada.moneda.value,
                        "en_corte": generada.corte_id is not None,
                        "periodo": f"{generada.mes:02d}/{generada.anio}"}
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
        "aprobado_por": aprobo.nombre if aprobo else None,
        # Se puede regresar desde aqui (seccion 131): lo aprobado que no
        # tiene factura; la prefactura timbrada la detiene el motor.
        "se_regresa": aprobado,
        "comision": comision,
        # El mes que se mando en cero (seccion 131, decision 10): sin
        # nada que facturar.
        "sin_cobro": sin_cobro(c),
        "factura": c.factura_odoo,
        "facturado_en": iso(c.facturado_en),
        # La que se hizo en Odoo y se anoto aqui (seccion 96): se corrige
        # aqui. La que llega de Odoo, en Odoo.
        "factura_a_mano": bool(c.factura_anotada_por_id),
        "factura_anotada_por": (anoto.nombre if anoto else None),
        "factura_anulada": c.factura_anulada,
        "error": None if antes else c.factura_error,
        "que_paso": "de_antes" if antes else que_paso(c.factura_error),
        "intentos": c.factura_intentos or 0,
        "ultimo_intento": iso(c.factura_intento_en),
        "devuelto_en": iso(c.devuelto_en),
        # La prefactura en Odoo (seccion 117): su numero, cuando salio y
        # donde se abre. La anulada: la que se quedo en Odoo al regresarlo,
        # que cancela el facturista.
        "prefactura": ({"id": c.prefactura_odoo_id,
                        "en": iso(c.prefactura_en),
                        "total": (str(c.prefactura_total)
                                  if c.prefactura_total is not None else None),
                        "url": odoo_facturacion.url_en_odoo(
                            c.prefactura_odoo_id)}
                       if c.prefactura_odoo_id else None),
        "prefactura_anulada": c.prefactura_anulada_id,
        "prefactura_url_anulada": odoo_facturacion.url_en_odoo(
            c.prefactura_anulada_id),
        "de_antes": antes,
    }


# ---------------------------------------------------------------- la bandeja

def montos(db: Session, cierres: list) -> list[dict]:
    """Lo que suman esos cierres, uno por moneda: [{moneda, monto}], los
    dolares al final. Cada cierre se suma en la moneda en que se factura
    (seccion 82)."""
    suma: dict[str, Decimal] = {}
    for c in cierres:
        moneda = motor_cierre.moneda_del_cierre(db, c)
        clave = moneda.value if moneda else ""
        suma[clave] = suma.get(clave, Decimal("0")) + Decimal(
            str(c.total_ejecutado or 0))
    return [{"moneda": k or None, "monto": v}
            for k, v in sorted(suma.items(), key=lambda x: (x[0] == "USD", x[0]))]


def gastos_del_cierre(db: Session, cierre: m.Cierre) -> dict:
    """Cuanto de lo que se factura son gastos, y con que trato: la
    bandeja dice "con $1,750 de gastos" y si van a precio alzado."""
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
            # Un mes en dolares factura sus gastos en dolares (seccion 82).
            moneda, local = cierre_mes.moneda_del_mes(db, contrato)
            if moneda != local:
                tc = motor_cierre.tipo_de_cambio_del_cierre(db, cierre,
                                                            moneda, local)
                monto = tipo_cambio.de_local(monto, tc["tasa"]) if tc else None
    else:
        from app import cotizacion as cot
        vigente = cot.vigente(db, cierre.servicio_id)
        if not vigente:
            return {"modo": None, "monto": Decimal("0")}
        alzado = vigente.viaticos_incluidos
        try:
            monto = motor_cierre.viaticos_por_cobrar(db, cierre.servicio_id,
                                                     vigente)
        except HTTPException:
            # Sin tipo de cambio no hay cifra (seccion 82): la bandeja lo
            # dice, no se cae.
            monto = None
    return {"modo": motor_cierre.modo_de_gastos(alzado), "monto": monto}


def bandeja(db: Session, ahora: datetime | None = None) -> dict:
    """La pantalla de Facturacion de finanzas, completa.

    Por aprobar: lo que ya tiene el visto bueno del consultor. Por
    facturar: lo que Odoo no acepto, con lo que dijo. Cerrados: lo que
    finanzas ya cerro este mes. Un implantado va por mes.

    Con la llave de la factura (seccion 117) «Por facturar» se parte en
    dos: «En Odoo», las prefacturas que esperan al facturista, y «No se
    pudo mandar», con su porque. Los eventuales y los meses, juntos.
    """
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
    pendientes = sin_factura(db)
    facturar = [renglon(db, c) for c in pendientes]
    llave = odoo_facturacion.hay_llave()
    en_odoo = [c for c in pendientes if c.prefactura_odoo_id]
    no_salio = [c for c in pendientes if not c.prefactura_odoo_id]

    def suma(filas):
        return sum((Decimal(str(c.total_ejecutado or 0)) for c in filas),
                   Decimal("0"))

    return {
        "momento": ahora.isoformat(),
        "odoo_configurado": hay_conexion(),
        # La llave de la factura (seccion 117): con ella, las pestanas son
        # «En Odoo» y «No se pudo mandar»; sin ella, «Por facturar».
        "llave": llave,
        "en_odoo": [f for f in facturar if f["prefactura"]] if llave else [],
        "no_se_pudo": [f for f in facturar if not f["prefactura"]] if llave else [],
        "resumen": {
            # `monto` se queda para quien ya lo leia; `montos` es el que
            # vale: uno por moneda (seccion 82). Sumar dolares con pesos
            # daba un numero sin moneda.
            "por_aprobar": {"cuantos": len(aprobar), "monto": suma(aprobar),
                            "montos": montos(db, aprobar)},
            "por_facturar": {"cuantos": len(facturar)},
            "en_odoo": {"cuantos": len(en_odoo) if llave else 0,
                        "montos": montos(db, en_odoo) if llave else []},
            "no_se_pudo": {"cuantos": len(no_salio) if llave else 0,
                           "de_antes": (sum(1 for c in no_salio
                                            if de_antes(c, llave))
                                        if llave else 0)},
            "cerrados": {"cuantos": len(cerrados), "monto": suma(cerrados),
                         "montos": montos(db, cerrados),
                         "mes": ahora.month, "anio": ahora.year},
        },
        "por_aprobar": [con_gastos(c) for c in aprobar],
        "por_facturar": facturar,
        "cerrados": [_cerrado(db, c, comisiones) for c in cerrados],
    }


def _cerrado(db: Session, c: m.Cierre, comisiones) -> dict:
    """Un renglon de «Cerrados»: con su comision como la ve el consultor
    y, si todavia se puede regresar (seccion 131), en que corte quedo."""
    fila = renglon(db, c)
    del_corte = fila["comision"] or {}
    generada = comisiones.del_cierre(db, c)
    fila["comision"] = ({**generada,
                         "en_corte": del_corte.get("en_corte", False),
                         "periodo": del_corte.get("periodo")}
                        if generada else None)
    return fila

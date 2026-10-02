"""Cierre del servicio: comparativo contra la cotizacion y rentabilidad.

El comparativo busca desviaciones: dias de mas o de menos, recursos no
cotizados, horas extra, y viaticos mal dispersados o sin comprobar.
Solo las desviaciones sin respaldo detonan el escalamiento.
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import cotizacion as cot
from app import horas_extra
from app import models as m
from app import reloj
from app import tipo_cambio

# Los dos relojes (decision de Salvador, 22 sep). T0 es el termino
# general del servicio: de T0 a T0 + 24 el personal comprueba sus
# viaticos. T1 llega al vencer ese plazo --o antes, si todo el dinero
# ya cerro--: de T1 a T1 + 24 el consultor da el visto bueno. Si nadie
# se adelanta, los dos suman 48 horas desde el termino.
HORAS_PERSONAL = 24
HORAS_CONSULTOR = 24
HORAS_MAXIMO_TOTAL = HORAS_PERSONAL + HORAS_CONSULTOR
CERO = Decimal("0")
registro = logging.getLogger(__name__)

# Que se le cobra al cliente cuando el servicio se cancela (seccion 105,
# decision 1 de Salvador, 29 sep). "Completo" es la cotizacion autorizada
# tal cual, con los dias que ya no se trabajaron; "ejecutado" es lo que se
# trabajo, como en un servicio que termino. Lo elige el consultor al
# cancelar y lo autoriza direccion de operaciones.
COBRO_COMPLETO = "completo"
COBRO_EJECUTADO = "ejecutado"
COBROS = (COBRO_COMPLETO, COBRO_EJECUTADO)
# El motivo de apertura de un cierre que nacio de una cancelacion.
CANCELACION = "cancelacion"


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


# ---------------------------------------------------------------- ejecutado

def factor_festivo(db: Session, pais_id: int, fecha) -> Decimal:
    """En dia festivo la comision del personal se paga al doble.
    El festivo se trabaja como dia normal; lo que cambia es lo que se le paga."""
    festivo = (db.query(m.DiaFestivo)
               .filter_by(pais_id=pais_id, fecha=fecha, activo=True).first())
    return _d(festivo.factor_comision) if festivo else Decimal("1")


def _horas_extra(jornada: m.Jornada) -> int:
    """Las horas extra del dia, hora o fraccion. La regla vive en
    `horas_extra` (seccion 65): corren desde la presentacion, o desde el
    meet and greet si fue antes."""
    return horas_extra.horas(jornada)


def hora_extra_del_rol(db: Session, tarifario_id: int, rol_id: int | None,
                       modalidad: m.Modalidad | None) -> tuple:
    """(precio, producto de Odoo) de la hora extra de un rol: los de su
    renglon del tarifario en esa modalidad; si el tarifario no le pone
    precio suelto a ese rol --el conductor que solo va en paquete--, los
    de su paquete (seccion 123: la lista de Amazon Brasil trae la hora
    extra del conductor con la Minivan y no trae al conductor suelto) y,
    si no, los de la lista, en las modalidades que llevan horas extra
    (seccion 79). El producto es con el que sale en la factura (seccion
    116)."""
    if modalidad is None:
        return None, None
    fila = (db.query(m.TarifaRecurso)
            .filter_by(tarifario_id=tarifario_id, perfil_id=rol_id,
                       modalidad_id=modalidad.id).first()) if rol_id else None
    if fila and fila.precio_hora_extra:
        return fila.precio_hora_extra, fila.producto_hora_extra_id
    if rol_id and fila is None:
        paquete = (db.query(m.TarifaPaquete)
                   .filter(m.TarifaPaquete.tarifario_id == tarifario_id,
                           m.TarifaPaquete.perfil_id == rol_id,
                           m.TarifaPaquete.modalidad_id == modalidad.id,
                           m.TarifaPaquete.precio_hora_extra.isnot(None))
                   .order_by(m.TarifaPaquete.id).first())
        if paquete is not None:
            return paquete.precio_hora_extra, paquete.producto_hora_extra_id
    if modalidad.aplica_horas_extra:
        tarifario = db.get(m.Tarifario, tarifario_id)
        if tarifario and tarifario.precio_hora_extra:
            return tarifario.precio_hora_extra, tarifario.producto_hora_extra_id
    return None, None


def _precio_hora_extra(db: Session, tarifario_id: int, rol_id: int | None,
                       modalidad: m.Modalidad | None):
    """El precio de la hora extra de un rol (ver `hora_extra_del_rol`)."""
    return hora_extra_del_rol(db, tarifario_id, rol_id, modalidad)[0]


def _se_ejecuto(j: m.Jornada) -> bool:
    if j.estatus == m.EstatusJornada.CANCELADA:
        return False
    return j.fin_real is not None or j.estatus == m.EstatusJornada.TERMINADA


def con_paquetes_del_servicio(db: Session, servicio_id: int) -> bool:
    """Si el cierre del servicio cobra los paquetes de la lista: la misma
    regla con que se cotizo (`cot.usa_paquetes`, seccion 115). Sin
    cotizacion autorizada, como siempre."""
    vigente = cot.vigente(db, servicio_id)
    return cot.con_paquetes(db, vigente) if vigente is not None else True


def emparejar_el_dia(db: Session, tarifario_id: int, j: m.Jornada,
                     con_paquetes: bool = True) -> tuple:
    """(pares, personas, unidades) del dia de un equipo (seccion 79).

    `pares`: [(paquete, asignacion de la persona, asignacion de la
    unidad)] --el rol que la lista del cliente tiene en paquete con una
    unidad que ese dia fue en el equipo--; `personas` y `unidades`: lo que
    no hizo pareja y se cobra suelto. La asignacion relevada no cuenta: el
    cliente tuvo un conductor ese dia, no dos (ver `ejecutado`). Sin
    `con_paquetes` (seccion 115: gastos aparte con una lista cuyos
    paquetes los traen) no hay pares: todo va suelto.
    """
    personas = [a for a in j.personal if not a.relevado_en]
    unidades = [a for a in j.vehiculos if not a.relevado_en]
    pares = []
    if not con_paquetes:
        return pares, personas, unidades
    for paquete in cot.paquetes_del_tarifario(db, tarifario_id, j.modalidad_id):
        while True:
            a = next((x for x in personas if x.rol_id == paquete.perfil_id), None)
            v = next((x for x in unidades if x.vehiculo
                      and x.vehiculo.categoria_id == paquete.categoria_id), None)
            if a is None or v is None:
                break
            personas.remove(a)
            unidades.remove(v)
            pares.append((paquete, a, v))
    return pares, personas, unidades


def viaticos_en_paquete(db: Session, servicio: m.Servicio,
                        tarifario_id: int,
                        con_paquetes: bool | None = None) -> set:
    """{(jornada, persona)} cuyos viaticos van dentro del paquete: los de
    quien fue en un paquete ese dia, si la lista del cliente dice que sus
    paquetes traen los viaticos (seccion 79; HASBRO). Esos no se le
    facturan aparte.

    Desde la seccion 115 ese paquete solo se cobra con los gastos dentro
    del precio: con gastos aparte no hay paquete y todos los viaticos se
    facturan. `con_paquetes` vacio sale de la cotizacion del servicio."""
    tarifario = db.get(m.Tarifario, tarifario_id)
    if not tarifario or not tarifario.paquetes_con_viaticos:
        return set()
    if con_paquetes is None:
        con_paquetes = con_paquetes_del_servicio(db, servicio.id)
    if not con_paquetes:
        return set()
    dentro = set()
    for equipo in servicio.equipos:
        for j in equipo.jornadas:
            if _se_ejecuto(j):
                pares, _, _ = emparejar_el_dia(db, tarifario_id, j)
                dentro |= {(j.id, a.persona_id) for _, a, _ in pares}
    return dentro


def ejecutado(db: Session, servicio: m.Servicio, tarifario_id: int,
              con_paquetes: bool | None = None) -> dict:
    """Lo que realmente se presto, valuado al tarifario del cliente.

    Cada renglon dice su modalidad y su precio, para que el cierre lo
    pueda decir renglon por renglon (seccion 79). Los paquetes, con la
    misma regla que la cotizacion (seccion 115): `con_paquetes` vacio sale
    de la cotizacion autorizada del servicio."""
    if con_paquetes is None:
        con_paquetes = con_paquetes_del_servicio(db, servicio.id)
    detalle = []
    total = CERO
    horas_extra_total = 0
    importe_extra_total = CERO
    # Los dias con horas extra, para que el visto bueno las diga en
    # horas y no solo en dinero (seccion 65).
    dias_con_extra = []

    def horas_de_mas(linea, extras, precio_extra, rol, producto=None):
        """Suma al renglon las horas extra de quien las trabajo."""
        nonlocal importe_extra_total
        if extras and precio_extra:
            extra_importe = _d(precio_extra) * extras
            importe_extra_total += extra_importe
            linea["horas_extra"] = extras
            linea["importe_horas_extra"] = extra_importe
            linea["precio_hora_extra"] = _d(precio_extra)
            linea["rol_hora_extra"] = rol
            # Con que producto de Odoo sale en la factura (seccion 116).
            linea["producto_hora_extra_id"] = producto
            linea["importe"] = linea["importe"] + extra_importe
        elif extras:
            # Sin precio de hora extra no se cobran, y antes nadie se
            # enteraba: a la gente si se le pagan. El revisor lo dice en
            # el visto bueno.
            linea["horas_extra_sin_precio"] = extras

    for equipo in servicio.equipos:
        for j in equipo.jornadas:
            if not _se_ejecuto(j):
                continue

            extras = _horas_extra(j)
            horas_extra_total += extras
            if extras:
                dias_con_extra.append(j)
            codigo = j.modalidad.codigo.value if j.modalidad else None

            # La asignacion relevada no se le cobra al cliente. Ese dia
            # hubo dos personas porque una salio a media jornada y entro
            # otra: el cliente tuvo un conductor, no dos. A la empresa si
            # le costaron los dos (ver `utilidad`), y esa diferencia es el
            # costo de la contingencia. Lo mismo con la unidad relevada.
            #
            # Y los paquetes del dia (seccion 79): el rol que la lista del
            # cliente tiene en paquete con una unidad que ese dia fue en el
            # equipo se cobra con ella, en un solo renglon. Lo que no hace
            # pareja se cobra suelto, como siempre.
            pares, personas, unidades = emparejar_el_dia(
                db, tarifario_id, j, con_paquetes)
            for paquete, a, _ in pares:
                precio = _d(paquete.precio)
                linea = {"fecha": j.fecha.isoformat(), "equipo": equipo.alias,
                         "tipo": "paquete",
                         "referencia_id": f"{paquete.perfil_id}-{paquete.categoria_id}",
                         "descripcion": cot.nombre_del_paquete(paquete),
                         "cantidad": 1, "importe": precio,
                         "modalidad": codigo, "precio": precio,
                         # Con que producto de Odoo se factura (seccion 116):
                         # el del mismo precio de la lista.
                         "producto_odoo_id": paquete.producto_odoo_id,
                         "rol_id": a.rol_id}
                precio_extra, producto_extra = hora_extra_del_rol(
                    db, tarifario_id, a.rol_id, j.modalidad)
                horas_de_mas(linea, extras, precio_extra,
                             a.rol.nombre if a.rol else None, producto_extra)
                detalle.append(linea)
                total += linea["importe"]

            for a in personas:
                # Se cobra el rol con el que fue ese dia, no lo que la
                # persona es: eso es lo que se le vendio al cliente.
                tarifa = cot.precio_recurso(db, tarifario_id, a.rol_id,
                                            j.modalidad_id)
                precio = _d(tarifa.precio)
                linea = {"fecha": j.fecha.isoformat(), "equipo": equipo.alias,
                         "tipo": "recurso", "referencia_id": a.rol_id,
                         "descripcion": a.rol.nombre if a.rol else None,
                         "cantidad": 1, "importe": precio,
                         "modalidad": codigo, "precio": precio,
                         "producto_odoo_id": tarifa.producto_odoo_id,
                         "rol_id": a.rol_id}
                # La misma regla que la cotizacion (seccion 127, hallazgo
                # r3-duda6): la hora extra de su renglon y, si no la
                # trae, la de toda la lista. Las listas de Odoo llenan el
                # renglon; en las capturadas a mano la cotizacion la
                # prometia y el cierre la cobraba en cero.
                precio_extra, producto_extra = hora_extra_del_rol(
                    db, tarifario_id, a.rol_id, j.modalidad)
                horas_de_mas(linea, extras, precio_extra,
                             a.rol.nombre if a.rol else None, producto_extra)
                detalle.append(linea)
                total += linea["importe"]

            for a in unidades:
                tarifa = cot.precio_vehiculo(db, tarifario_id, a.vehiculo.categoria_id,
                                             j.modalidad_id)
                precio = _d(tarifa.precio)
                detalle.append({"fecha": j.fecha.isoformat(), "equipo": equipo.alias,
                                "tipo": "vehiculo", "referencia_id": a.vehiculo.categoria_id,
                                "descripcion": a.vehiculo.categoria.nombre,
                                "cantidad": 1, "importe": precio,
                                "modalidad": codigo, "precio": precio,
                                "producto_odoo_id": tarifa.producto_odoo_id})
                total += precio

    return {"detalle": detalle, "total": total, "horas_extra": horas_extra_total,
            "importe_horas_extra": importe_extra_total,
            "dias_con_extra": dias_con_extra}


# El orden en que se dicen los renglones: lo que va junto primero.
ORDEN_DE_RENGLON = {"paquete": 0, "recurso": 1, "vehiculo": 2, "horas_extra": 3}
ORDEN_DE_MODALIDAD = {"full_day": 0, "medio_dia": 1, "transfer": 2}


def renglones(detalle: list) -> list[dict]:
    """Lo que se factura, renglon por renglon (seccion 79): el detalle del
    ejecutado agrupado por lo que se cobra --el paquete, el rol o la
    unidad-- en su modalidad y a su precio; y aparte, las horas extra de
    cada rol. Suman lo mismo que el ejecutado."""
    base, extra = {}, {}
    for l in detalle:
        clave = (l["tipo"], str(l["referencia_id"]), l.get("modalidad"),
                 l.get("precio"))
        r = base.setdefault(clave, {
            "tipo": l["tipo"], "descripcion": l["descripcion"],
            "modalidad": l.get("modalidad"), "precio": l.get("precio"),
            "cantidad": 0, "importe": CERO})
        r["cantidad"] += l["cantidad"]
        r["importe"] += l["importe"] - (l.get("importe_horas_extra") or CERO)
        if l.get("importe_horas_extra"):
            clave = (l.get("rol_hora_extra") or l["descripcion"],
                     l.get("precio_hora_extra"))
            e = extra.setdefault(clave, {
                "tipo": "horas_extra", "descripcion": clave[0], "modalidad": None,
                "precio": clave[1], "cantidad": 0, "importe": CERO})
            e["cantidad"] += l.get("horas_extra") or 0
            e["importe"] += l["importe_horas_extra"]
    return sorted(list(base.values()) + list(extra.values()),
                  key=lambda r: (ORDEN_DE_RENGLON.get(r["tipo"], 9),
                                 r["descripcion"] or "",
                                 ORDEN_DE_MODALIDAD.get(r["modalidad"], 9)))


# ---------------------------------------------------------------- comparativo

def _clave(linea) -> tuple:
    return (linea["fecha"], linea["equipo"], linea["tipo"], linea["referencia_id"])


# ---------------------------------------------------------------- gastos

# Como se le cobran los gastos al cliente (decision de Salvador, 23 sep;
# seccion 59). Son sus dos tratos:
#
# * A precio alzado: el cliente pidio un monto fijo desde la propuesta y
#   la cotizacion lo lleva en sus renglones de gastos. Se factura ese
#   monto, se gaste mas o menos: lo que sobra es margen y lo que se pasa
#   lo absorbe Centauro. Sin renglones de gastos, los gastos van dentro
#   del precio y no se suma nada.
# * Gastos netos: se factura lo comprobado valido y el cliente recibe el
#   desglose al final.
#
# En los dos el personal comprueba todo igual: es el control de la casa.
# La columna se sigue llamando `viaticos_incluidos` (seccion 57, cuando
# se decia "incluidos o aparte"): verdadero es precio alzado.
PRECIO_ALZADO = "precio_alzado"
NETOS = "netos"


def modo_de_gastos(incluidos: bool) -> str:
    return PRECIO_ALZADO if incluidos else NETOS


def gastos_cotizados(cotizacion) -> Decimal:
    """El monto fijo de gastos de la propuesta: sus renglones de gastos."""
    return sum((_d(l.subtotal) for l in cotizacion.lineas
                if l.tipo == m.TipoLinea.VIATICOS), CERO)


MISMA_MONEDA = (False, None)


def _viatico_facturable(cotizacion, comprobado: Decimal,
                        cambio: tuple = MISMA_MONEDA) -> Decimal | None:
    """Cuanto de gastos lleva la factura del cliente, en la moneda de la
    cotizacion.

    A precio alzado, el monto fijo de la cotizacion, pase lo que pase
    con la comprobacion --hasta la seccion 59 ese monto no llegaba a la
    factura: el servicio se cobraba sin los gastos--. Netos, lo
    comprobado valido, que ya excluye lo rechazado.

    Lo comprobado es en la moneda del pais. `cambio` es lo que contesta
    `tipo_de_cambio_de_gastos`: si la cotizacion es de otra moneda, lo
    comprobado se pasa a la suya con el tipo de cambio de los gastos
    (seccion 82), y sin tipo de cambio no hay cifra --None--: un monto en
    pesos rotulado en dolares es justo lo que no puede pasar.
    """
    if cotizacion.viaticos_incluidos:
        return gastos_cotizados(cotizacion)
    otra, tc = cambio
    if not otra:
        return comprobado
    return tipo_cambio.de_local(comprobado, tc["tasa"]) if tc else None


def tipo_de_cambio_de_gastos(db: Session, servicio: m.Servicio,
                             cotizacion) -> tuple[bool, dict | None]:
    """(si la cotizacion es de otra moneda, su tipo de cambio de gastos).

    Los gastos se comprueban en la moneda del pais y se le facturan al
    cliente en la de su cotizacion, al tipo de cambio que esta puesto en
    el visto bueno --que es cuando sale la factura-- (seccion 82). Antes
    del visto bueno, el que esta puesto hoy, para que el consultor vea
    cuanto va a ser. (False, None) si la cotizacion es de la moneda del
    pais; (True, None) si es de otra y no hay tipo de cambio.
    """
    local = tipo_cambio.local_del_pais(db, servicio.pais_id)
    if not local or cotizacion.moneda == local:
        return MISMA_MONEDA
    cierre = (db.query(m.Cierre)
              .filter_by(servicio_id=servicio.id, contrato_id=None).first())
    return True, tipo_de_cambio_del_cierre(db, cierre, cotizacion.moneda, local)


def tipo_de_cambio_del_cierre(db: Session, cierre: m.Cierre | None,
                              moneda, local) -> dict | None:
    """El de los gastos de ese cierre: el que quedo fijo con el visto
    bueno ("fijo": True) o, mientras no lo hay, el que esta puesto. Lo
    mismo para el eventual y para el mes del implantado."""
    if cierre is not None and cierre.tipo_cambio_gastos:
        return tipo_cambio.fijo(cierre.tipo_cambio_gastos,
                                cierre.tipo_cambio_gastos_fecha)
    if not tipo_cambio.se_puede(moneda, local):
        return None
    tc = tipo_cambio.vigente(db, moneda, local)
    return {**tc, "fijo": False} if tc else None


def fijar_tipo_de_cambio_de_gastos(db: Session, cierre: m.Cierre, moneda,
                                   local) -> dict | None:
    """Con el visto bueno sale la factura: el tipo de cambio de los gastos
    queda fijo en el cierre, el que esta puesto en ese momento. Si
    finanzas lo regresa, se borra (`regresar`) y el visto bueno que sigue
    lo vuelve a fijar, porque sale otra factura. None si no hay: entonces
    no se fija nada, y la revision lo frena."""
    tc = (tipo_cambio.vigente(db, moneda, local)
          if tipo_cambio.se_puede(moneda, local) else None)
    cierre.tipo_cambio_gastos = tc["tasa"] if tc else None
    cierre.tipo_cambio_gastos_fecha = tc["fecha"] if tc else None
    db.flush()
    return tc


def fijar_gastos_del_visto_bueno(db: Session, cierre: m.Cierre) -> dict | None:
    """El visto bueno del eventual fija el tipo de cambio de sus gastos,
    si la cotizacion es de otra moneda y los cobra netos. A precio alzado
    no hace falta: el monto ya esta en la moneda de la cotizacion."""
    vigente = cot.vigente(db, cierre.servicio_id)
    local = tipo_cambio.local_del_pais(db, cierre.servicio.pais_id)
    if (vigente is None or local is None or vigente.moneda == local
            or vigente.viaticos_incluidos):
        return None
    return fijar_tipo_de_cambio_de_gastos(db, cierre, vigente.moneda, local)


def cambio_en_json(tc: dict | None) -> dict | None:
    """Un tipo de cambio para la pantalla: cuanto, de cuando, quien lo
    puso y si ya quedo fijo."""
    if tc is None:
        return None
    return {**tipo_cambio.en_json(tc), "fijo": bool(tc.get("fijo"))}


def moneda_del_cierre(db: Session, cierre: m.Cierre) -> m.Moneda | None:
    """En que moneda se factura ese cierre (seccion 82): la de la
    cotizacion vigente en el eventual, la de los precios del mes en el
    implantado; si no dicen, la del pais."""
    moneda = None
    if cierre.contrato_id:
        moneda = cierre.contrato.moneda if cierre.contrato else None
    else:
        vigente = cot.vigente(db, cierre.servicio_id)
        moneda = vigente.moneda if vigente else None
    return moneda or tipo_cambio.local_del_pais(db, cierre.servicio.pais_id)


def _viaticos_del_comparativo(cotizacion, asignado, comprobado, devuelto,
                              rechazado, descontado, absorbido,
                              en_paquete=CERO,
                              cambio: tuple = MISMA_MONEDA) -> dict:
    """El dinero del personal va en la moneda del pais; lo cotizado y lo
    facturable, en la de la cotizacion (seccion 82)."""
    alzado = cotizacion.viaticos_incluidos
    return {
        "asignado": asignado,
        "comprobado": comprobado,
        "devuelto": devuelto,
        "pendiente": asignado - comprobado - devuelto,
        # Lo rechazado no es costo de la empresa: se recupera del personal.
        "rechazado_no_facturable": rechazado,
        "descontado_al_personal": descontado,
        "absorbido_por_la_empresa": absorbido,
        "modo_cobro": modo_de_gastos(alzado),
        "gastos_cotizados": gastos_cotizados(cotizacion),
        # Lo que ya va dentro de un paquete no se cobra aparte (seccion 79).
        "en_paquete": en_paquete,
        "facturable_al_cliente": _viatico_facturable(
            cotizacion, comprobado - en_paquete, cambio),
        "nota_facturacion": (
            "A precio alzado se factura el monto fijo de la propuesta, se "
            "gaste mas o menos. Si no lleva monto, los gastos van dentro "
            "del precio."
            if alzado else
            "Gastos netos: se factura lo comprobado valido. Lo rechazado y "
            "lo que se desconto al personal no se le cobra al cliente."),
    }


def viaticos_por_cobrar(db: Session, servicio_id: int,
                        cotizacion) -> Decimal:
    """Los gastos que lleva la factura del cliente (seccion 59).

    A precio alzado, el monto fijo de la cotizacion; netos, lo
    comprobado valido --sin lo rechazado ni lo enviado a descuento, que
    no es gasto del servicio--.
    """
    if cotizacion.viaticos_incluidos:
        return gastos_cotizados(cotizacion)
    servicio = db.get(m.Servicio, servicio_id)
    comprobado = sum((_d(v.monto_comprobado) for v in viaticos_facturables(
        db, servicio, cotizacion.tarifario_id,
        cot.con_paquetes(db, cotizacion))), CERO)
    # En pesos; si la cotizacion es en dolares, a dolares (seccion 82).
    monto = _viatico_facturable(
        cotizacion, comprobado,
        tipo_de_cambio_de_gastos(db, servicio, cotizacion))
    if monto is None:
        raise HTTPException(409, cot.sin_tipo_de_cambio(
            db, cotizacion.moneda,
            tipo_cambio.local_del_pais(db, servicio.pais_id)))
    return monto


def viaticos_por_cobrar_local(db: Session, servicio_id: int, cotizacion,
                              tc: dict | None = None) -> Decimal:
    """Los mismos gastos de la factura, en la moneda del pais: para la
    utilidad y la comision, que son en pesos (seccion 82). Netos, lo
    comprobado --que ya es en pesos, sin convertir de ida y vuelta--; a
    precio alzado, el monto de la cotizacion a `tc`, el tipo de cambio de
    la cotizacion (`cot.tipo_de_cambio`). Sin `tc`, la cotizacion es de
    la moneda del pais."""
    if cotizacion.viaticos_incluidos:
        monto = gastos_cotizados(cotizacion)
        return tipo_cambio.a_local(monto, tc["tasa"]) if tc else monto
    servicio = db.get(m.Servicio, servicio_id)
    return sum((_d(v.monto_comprobado) for v in viaticos_facturables(
        db, servicio, cotizacion.tarifario_id,
        cot.con_paquetes(db, cotizacion))), CERO)


def viaticos_facturables(db: Session, servicio: m.Servicio,
                         tarifario_id: int,
                         con_paquetes: bool | None = None) -> list:
    """El dinero del servicio que se le puede cobrar al cliente con gastos
    netos: todo, menos lo de quien fue en un paquete que ya los trae
    (seccion 79). Es lo que suma la factura y lo que lleva el desglose."""
    dentro = viaticos_en_paquete(db, servicio, tarifario_id, con_paquetes)
    return [v for v in viaticos_del_servicio(db, servicio.id)
            if (v.jornada_id, v.persona_id) not in dentro]


def viaticos_del_servicio(db: Session, servicio_id: int) -> list:
    """Todo el dinero del servicio, dia por dia y persona por persona."""
    return (db.query(m.AsignacionViatico)
            .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == servicio_id).all())


def desviaciones_del_dinero(viaticos: list) -> list[dict]:
    """Lo que el dinero del servicio le dice a finanzas, persona por persona.

    El dinero de cada persona es un solo bolson (`bolson`): lo que falta
    se cuenta por persona y no por dia. Contado por dia, un ticket
    cargado el lunes dejaba al martes "sin comprobar" y al lunes
    "comprobado de mas": dos desviaciones por un dinero que cuadraba.
    """
    from app import bolson

    desviaciones = []
    for suyos in bolson.agrupar(viaticos):
        persona = suyos[0].persona
        nombre = persona.nombre if persona else str(suyos[0].persona_id)
        c = bolson.cuenta(suyos)
        if c["estatus"] == "con_descuento":
            # Ya esta resuelto: no es un pendiente, es una decision
            # tomada. Se informa para que finanzas lo vea, pero no frena.
            desviaciones.append({
                "tipo": m.TipoDesviacion.VIATICO_SIN_COMPROBAR.value,
                "descripcion": (f"{nombre}: cierre con descuento de "
                                f"{c['descontado']}"
                                + (f", {c['absorbido']} absorbido por la "
                                   f"empresa" if c["absorbido"] else "")
                                + f". {c['motivo_cierre'] or ''}").strip(),
                "monto": c["descontado"],
                "respaldada": True})
            continue
        if c["por_depositar"] > 0:
            desviaciones.append({
                "tipo": m.TipoDesviacion.VIATICO_NO_CERRADO.value,
                "descripcion": (f"{nombre}: {c['por_depositar']} autorizados "
                                "que no se depositaron"),
                "monto": c["por_depositar"]})
        if c["falta"] != CERO:
            desviaciones.append({
                "tipo": m.TipoDesviacion.VIATICO_SIN_COMPROBAR.value,
                "descripcion": (f"{nombre}: {abs(c['falta'])} "
                                + ("sin comprobar ni devolver"
                                   if c["falta"] > 0 else "comprobado de mas")),
                "monto": c["falta"]})
        if c["estatus"] == "abierto":
            desviaciones.append({
                "tipo": m.TipoDesviacion.VIATICO_NO_CERRADO.value,
                "descripcion": f"{nombre}: sus viaticos siguen sin cerrar",
                "monto": CERO})
    return desviaciones


def horas_por_dia(jornadas: list) -> list[dict]:
    """Las horas extra de cada dia, dichas en horas y con su porque: a que
    hora corrian las horas contratadas y a que hora termino. Lo mismo
    para el eventual y para el mes del implantado."""
    salida = []
    for j in sorted(jornadas, key=lambda x: (x.fecha, x.id)):
        tope = horas_extra.limite(j)
        salida.append({
            "jornada_id": j.id, "fecha": j.fecha.isoformat(),
            "equipo": j.equipo.alias if j.equipo else None,
            "horas": horas_extra.horas(j),
            "corren_hasta": f"{tope:%H:%M}" if tope else None,
            "termino": f"{j.fin_real:%H:%M}" if j.fin_real else None,
            "adelantado": bool(j.inicio_real and j.inicio_programado
                               and j.inicio_real < j.inicio_programado),
            "con_el_ejecutivo": (f"{j.inicio_real:%H:%M}"
                                 if j.inicio_real else None)})
    return salida


def del_eventual(db: Session, servicio_id: int) -> m.Cierre | None:
    """El cierre del servicio eventual, si ya nacio. El implantado lleva
    uno por mes y se lee por su contrato."""
    return (db.query(m.Cierre)
            .filter_by(servicio_id=servicio_id, contrato_id=None).first())


def cobro_del_cierre(db: Session, cierre: m.Cierre | None) -> dict | None:
    """Como se cobra una cancelacion, para las pantallas (seccion 105):
    lo que pidio el consultor, si direccion de operaciones ya lo
    autorizo, quien y cuando. None cuando el cierre no lleva cobro: un
    cierre por termino, o una cancelacion de antes de la seccion 105."""
    if cierre is None or not cierre.cobro:
        return None
    quien = (db.get(m.Persona, cierre.cobro_autorizado_por_id)
             if cierre.cobro_autorizado_por_id else None)
    return {"cobro": cierre.cobro,
            "autorizado": cierre.cobro_autorizado_en is not None,
            "autorizado_en": (cierre.cobro_autorizado_en.isoformat()
                              if cierre.cobro_autorizado_en else None),
            "autorizado_por": quien.nombre if quien else None}


def cobro_sin_autorizar(cierre: m.Cierre | None) -> bool:
    """Si el cierre espera el visto bueno de operaciones sobre el cobro:
    una cancelacion con cobro pedido y sin autorizar. Sin eso no se manda
    a finanzas (seccion 105)."""
    return bool(cierre is not None and cierre.cobro
                and cierre.cobro_autorizado_en is None)


def se_cobra_completo(cierre: m.Cierre | None) -> bool:
    """Si el servicio cancelado se factura con la cotizacion tal cual.
    Vale desde que el consultor lo pide: la tarjeta ensena lo que se va a
    cobrar, y el candado de la autorizacion vive en el envio a finanzas."""
    return bool(cierre is not None and cierre.cobro == COBRO_COMPLETO)


def dias_cancelados(servicio: m.Servicio) -> set:
    """{(fecha ISO, alias del equipo)} de los dias cancelados."""
    return {(j.fecha.isoformat(), e.alias) for e in servicio.equipos
            for j in e.jornadas if j.estatus == m.EstatusJornada.CANCELADA}


def comparar(db: Session, servicio_id: int) -> dict:
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    cotizacion = cot.vigente(db, servicio_id)
    if not cotizacion:
        raise HTTPException(409, "El servicio no tiene cotizacion autorizada")

    # En un servicio cancelado los dias que ya no se trabajaron no son
    # "dias de menos" que haya que recotizar o justificar (seccion 105):
    # se informan, y el cobro --completo o ejecutado-- lo decide
    # operaciones. En un servicio que termino, un dia cancelado si se
    # justifica: el consultor dice que paso con el boton de la tarjeta.
    cierre = del_eventual(db, servicio_id)
    cancelado = servicio.estatus == m.EstatusServicio.CANCELADO
    sin_trabajar = dias_cancelados(servicio) if cancelado else set()
    completo = se_cobra_completo(cierre)

    def referencia(l):
        if l.tipo == m.TipoLinea.PAQUETE:
            return f"{l.perfil_id}-{l.categoria_id}"
        return l.perfil_id if l.tipo == m.TipoLinea.RECURSO else l.categoria_id

    cotizado = [{
        "fecha": l.fecha.isoformat(), "equipo": l.equipo_clave,
        "tipo": l.tipo.value, "referencia_id": referencia(l),
        "descripcion": l.descripcion, "cantidad": l.cantidad,
        "importe": _d(l.subtotal),
    } for l in cotizacion.lineas if l.tipo != m.TipoLinea.VIATICOS]

    real = ejecutado(db, servicio, cotizacion.tarifario_id,
                     cot.con_paquetes(db, cotizacion))

    # agrupar por clave
    mapa_cot, mapa_eje = {}, {}
    for l in cotizado:
        k = _clave(l)
        mapa_cot.setdefault(k, {"cantidad": 0, "importe": CERO, "descripcion": l["descripcion"]})
        mapa_cot[k]["cantidad"] += l["cantidad"]
        mapa_cot[k]["importe"] += l["importe"]
    for l in real["detalle"]:
        k = _clave(l)
        mapa_eje.setdefault(k, {"cantidad": 0, "importe": CERO,
                                "extra": CERO, "descripcion": l["descripcion"]})
        mapa_eje[k]["cantidad"] += l["cantidad"]
        mapa_eje[k]["importe"] += l["importe"]
        # Cuanto de esa linea son horas extra. Se guarda por linea y no
        # por servicio: es lo unico que puede decir si el sobrecosto de
        # ESTE renglon se explica solo.
        mapa_eje[k]["extra"] += l.get("importe_horas_extra") or CERO

    desviaciones = []

    for k, v in mapa_cot.items():
        fecha, equipo, tipo, _ = k
        if k not in mapa_eje:
            if (fecha, equipo) in sin_trabajar:
                # El dia se cancelo con el servicio: informativo, con lo
                # que operaciones decidio cobrar (seccion 105).
                desviaciones.append({
                    "tipo": m.TipoDesviacion.DIAS_DE_MENOS.value,
                    "descripcion": (f"{fecha} {equipo}: se cotizo "
                                    f"{v['descripcion']} y el dia se cancelo "
                                    + ("(se cobra completo por decision de "
                                       "operaciones)" if completo
                                       else "(no se cobra)")),
                    "monto": CERO if completo else -v["importe"],
                    "informativa": True,
                    # Para que la pantalla lo diga en su idioma.
                    "fecha": fecha, "equipo": equipo, "que": v["descripcion"]})
                continue
            desviaciones.append({
                "tipo": m.TipoDesviacion.DIAS_DE_MENOS.value,
                "descripcion": f"{fecha} {equipo}: se cotizo {v['descripcion']} "
                               f"y no se ejecuto",
                "monto": -v["importe"]})

    for k, v in mapa_eje.items():
        fecha, equipo, tipo, _ = k
        if k not in mapa_cot:
            desviaciones.append({
                "tipo": m.TipoDesviacion.RECURSO_NO_COTIZADO.value,
                "descripcion": f"{fecha} {equipo}: se ejecuto {v['descripcion']} "
                               f"sin estar cotizado",
                "monto": v["importe"]})
        else:
            diferencia = v["importe"] - mapa_cot[k]["importe"]
            if diferencia > 0:
                # Horas extra solo si las de ESTE renglon lo explican
                # completo. Antes bastaba con que hubiera una sola hora
                # extra en cualquier dia del servicio para etiquetar asi
                # todos los sobrecostos, y "horas extra" es informativo:
                # el cobro de mas se iba a facturacion sin que nadie lo
                # recotizara. Lo que no explica la hora extra es un dia
                # de mas, y eso si hay que corregirlo antes de enviar.
                explicado = v["extra"] > 0 and diferencia <= v["extra"]
                desviaciones.append({
                    "tipo": (m.TipoDesviacion.HORAS_EXTRA.value if explicado
                             else m.TipoDesviacion.DIAS_DE_MAS.value),
                    "descripcion": f"{fecha} {equipo}: {v['descripcion']} cobra "
                                   f"{diferencia} mas de lo cotizado"
                                   + (f" ({v['extra']} son horas extra)"
                                      if v["extra"] and not explicado else ""),
                    "monto": diferencia})
            elif diferencia < 0:
                desviaciones.append({
                    "tipo": m.TipoDesviacion.COBRO_MENOR.value,
                    "descripcion": f"{fecha} {equipo}: {v['descripcion']} cobra "
                                   f"{abs(diferencia)} menos de lo cotizado",
                    "monto": diferencia})

    # ---- viaticos
    viaticos = viaticos_del_servicio(db, servicio_id)

    asignado = sum((_d(v.monto_total) for v in viaticos), CERO)
    comprobado = sum((_d(v.monto_comprobado) for v in viaticos), CERO)
    devuelto = sum((_d(v.monto_devuelto) for v in viaticos), CERO)

    descontado = sum((_d(v.monto_descontado) for v in viaticos), CERO)
    absorbido = sum((_d(v.monto_absorbido) for v in viaticos), CERO)
    rechazado = sum((_d(c.monto) for v in viaticos for c in v.comprobantes
                     if c.rechazado), CERO)

    # Cada desviacion dice en que moneda va su monto (seccion 82): las
    # del servicio, en la de la cotizacion; las del dinero del personal,
    # en la del pais.
    local = tipo_cambio.local_del_pais(db, servicio.pais_id) or cotizacion.moneda
    for d in desviaciones:
        d["moneda"] = cotizacion.moneda.value
    desviaciones.extend({**d, "moneda": local.value}
                        for d in desviaciones_del_dinero(viaticos))

    # Con gastos netos, lo de quien fue en un paquete que ya trae los
    # viaticos no se cobra aparte (seccion 79): va dentro del paquete.
    en_paquete = CERO
    if not cotizacion.viaticos_incluidos:
        dentro = viaticos_en_paquete(db, servicio, cotizacion.tarifario_id,
                                     cot.con_paquetes(db, cotizacion))
        en_paquete = sum((_d(v.monto_comprobado) for v in viaticos
                          if (v.jornada_id, v.persona_id) in dentro), CERO)

    # La cotizacion lleva el servicio y, a precio alzado, el monto fijo de
    # gastos. El comparativo los separa: la diferencia del servicio se
    # mide contra el servicio, y los gastos contra su propio trato.
    fijo = gastos_cotizados(cotizacion)
    total_cotizado = _d(cotizacion.total)
    servicio_cotizado = total_cotizado - fijo

    # La moneda (seccion 82). El servicio y lo cotizado van en la de la
    # cotizacion; el dinero del personal, en la del pais. Con gastos
    # netos en otra moneda, lo comprobado se pasa a la de la cotizacion
    # con el tipo de cambio del visto bueno --el que este puesto, mientras
    # no lo hay--; sin tipo de cambio no hay cifra de gastos, y la
    # revision no deja mandarlo.
    cambio = tipo_de_cambio_de_gastos(db, servicio, cotizacion)
    otra, tc_gastos = cambio
    netos = not cotizacion.viaticos_incluidos
    gastos_a_facturar = _viatico_facturable(cotizacion, comprobado - en_paquete,
                                            cambio)
    sin_cambio = gastos_a_facturar is None
    tc_cotizacion = cot.tipo_de_cambio(db, cotizacion) if otra else None
    # Lo que se le cobra del servicio (seccion 105): con el cobro completo
    # de una cancelacion, la cotizacion tal cual --los dias cancelados se
    # cobran--; si no, lo ejecutado. Los gastos van con su propio trato
    # en los dos casos.
    servicio_a_facturar = servicio_cotizado if completo else real["total"]
    return {
        "servicio": servicio.folio,
        "moneda": cotizacion.moneda.value,
        "moneda_local": local.value,
        # Como se cobra la cancelacion, y si operaciones ya lo autorizo.
        "cobro": cobro_del_cierre(db, cierre),
        "cotizacion": {"version": cotizacion.version, "total": total_cotizado,
                       "servicio": servicio_cotizado, "gastos": fijo,
                       "moneda": cotizacion.moneda.value,
                       "viaticos_incluidos": cotizacion.viaticos_incluidos,
                       # El de la autorizacion: con el se miden la utilidad
                       # y la comision, y no se mueve.
                       "tipo_cambio": tipo_cambio.en_json(tc_cotizacion),
                       "autorizada_en": (cotizacion.autorizada_en.isoformat()
                                         if cotizacion.autorizada_en else None)},
        "ejecutado": {"total": real["total"], "horas_extra": real["horas_extra"],
                      "importe_horas_extra": real["importe_horas_extra"],
                      "horas_extra_por_dia": horas_por_dia(
                          real["dias_con_extra"]),
                      "horas_extra_sin_precio": [
                          {"fecha": l["fecha"], "equipo": l["equipo"],
                           "descripcion": l["descripcion"],
                           "horas": l["horas_extra_sin_precio"]}
                          for l in real["detalle"]
                          if l.get("horas_extra_sin_precio")],
                      "dias": len({l["fecha"] for l in real["detalle"]}),
                      "equipos": len({l["equipo"] for l in real["detalle"]}),
                      # Lo que se factura, renglon por renglon (seccion 79).
                      "renglones": renglones(real["detalle"])},
        "diferencia": real["total"] - servicio_cotizado,
        "gastos": {"modo": modo_de_gastos(cotizacion.viaticos_incluidos),
                   # `cotizado` y `a_facturar`, en la moneda de la
                   # cotizacion; `comprobado` y `en_paquete`, en la del pais.
                   "cotizado": fijo, "comprobado": comprobado,
                   "en_paquete": en_paquete,
                   "a_facturar": gastos_a_facturar,
                   "moneda_local": local.value,
                   # Netos en otra moneda: de donde sale la cifra.
                   "tipo_cambio": (cambio_en_json(tc_gastos)
                                   if otra and netos else None),
                   "sin_tipo_de_cambio": (
                       cot.sin_tipo_de_cambio(db, cotizacion.moneda, local)
                       if sin_cambio else None),
                   # A precio alzado en otra moneda, el monto fijo en la
                   # del pais al tipo de cambio de la cotizacion: contra
                   # eso se mide lo que se gasto.
                   "cotizado_local": (tipo_cambio.a_local(fijo,
                                                          tc_cotizacion["tasa"])
                                      if otra and not netos and tc_cotizacion
                                      and fijo else None)},
        "a_facturar": {"servicio": servicio_a_facturar,
                       "gastos": gastos_a_facturar,
                       "total": (None if sin_cambio
                                 else servicio_a_facturar + gastos_a_facturar),
                       "completo": completo},
        "viaticos": _viaticos_del_comparativo(
            cotizacion, asignado, comprobado, devuelto, rechazado,
            descontado, absorbido, en_paquete, cambio),
        "desviaciones": desviaciones,
        "sin_desviaciones": not desviaciones,
    }


# ---------------------------------------------------------------- rentabilidad

def _facturado_en_otra_moneda(db: Session, servicio_id: int, cotizacion,
                              real: dict, tc: dict) -> dict:
    """Lo que dice la factura en la moneda de la cotizacion, al lado de
    lo que eso es en pesos: el servicio y los gastos, y el total. Los
    gastos pueden no tener cifra todavia (sin tipo de cambio): entonces
    tampoco el total."""
    try:
        gastos = viaticos_por_cobrar(db, servicio_id, cotizacion)
    except HTTPException:
        gastos = None
    return {"moneda": cotizacion.moneda.value,
            "servicio": real["total"],
            "gastos": gastos,
            "total": None if gastos is None else real["total"] + gastos,
            "tipo_cambio": tipo_cambio.en_json(tc)}


def rentabilidad(db: Session, servicio_id: int) -> dict:
    """Tres bloques: facturacion, costo directo de personal y viaticos,
    y costo del vehiculo."""
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    cotizacion = cot.vigente(db, servicio_id)
    if not cotizacion:
        raise HTTPException(409, "El servicio no tiene cotizacion autorizada")

    real = ejecutado(db, servicio, cotizacion.tarifario_id,
                     cot.con_paquetes(db, cotizacion))
    # Con el cobro completo de una cancelacion (seccion 105) se le factura
    # la cotizacion tal cual: la utilidad y la comision se miden contra
    # eso, no contra lo trabajado. Los costos siguen siendo los de los
    # dias que si se trabajaron.
    if se_cobra_completo(del_eventual(db, servicio_id)):
        real = {**real,
                "total": _d(cotizacion.total) - gastos_cotizados(cotizacion)}

    # Todo en la moneda del pais, que es la de los costos (seccion 82).
    # Una cotizacion en dolares se pasa a pesos con el tipo de cambio que
    # estaba puesto cuando se autorizo --fijo: la utilidad y la comision no
    # se mueven con el dolar--. Sin el, no hay utilidad que decir:
    # restaria dolares menos pesos.
    local = tipo_cambio.local_del_pais(db, servicio.pais_id) or cotizacion.moneda
    tc = None
    if cotizacion.moneda != local:
        tc = cot.tipo_de_cambio(db, cotizacion)
        if tc is None:
            raise HTTPException(409, cot.sin_tipo_de_cambio(
                db, cotizacion.moneda, local))
    servicio_local = (tipo_cambio.a_local(real["total"], tc["tasa"]) if tc
                      else real["total"])
    # Lo que se le factura: lo ejecutado y, si la cotizacion cobra los
    # viaticos aparte, lo comprobado (seccion 57). Sin esto la utilidad
    # y la comision restaban unos viaticos que no se facturaban.
    viaticos_cobrados = viaticos_por_cobrar_local(db, servicio_id, cotizacion, tc)
    facturacion = servicio_local + viaticos_cobrados

    costo_personal = CERO
    costo_vehiculo = CERO
    dias_vehiculo = 0
    dias_festivos = 0

    for equipo in servicio.equipos:
        for j in equipo.jornadas:
            if j.estatus == m.EstatusJornada.CANCELADA:
                continue
            if not (j.fin_real or j.estatus == m.EstatusJornada.TERMINADA):
                continue

            extras = _horas_extra(j)
            factor = factor_festivo(db, servicio.pais_id, j.fecha)
            if factor > 1:
                dias_festivos += 1
            # Aqui si entran las relevadas: a la empresa le costaron las
            # dos. Lo que el cliente no paga de ese dia es el costo de la
            # contingencia, y sale solo en esta resta.
            for a in j.personal:
                comision = None
                if a.rol_id:
                    comision = (db.query(m.ComisionPersonal)
                                .filter_by(pais_id=servicio.pais_id,
                                           perfil_id=a.rol_id,
                                           tipo_servicio=servicio.tipo,
                                           modalidad_id=j.modalidad_id).first())
                if comision:
                    costo_personal += _d(comision.monto) * factor
                    # Las horas extra son de quien se quedo: al relevado
                    # no se le pagan (ver `nomina.pago_de_jornada`), asi
                    # que tampoco le cuestan a la empresa.
                    if extras and comision.monto_hora_extra and not a.relevado_en:
                        costo_personal += _d(comision.monto_hora_extra) * extras * factor

            for a in j.vehiculos:
                if a.vehiculo.costo_diario:
                    costo_vehiculo += _d(a.vehiculo.costo_diario)
                dias_vehiculo += 1

    viaticos = (db.query(m.AsignacionViatico)
                .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
                .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                .filter(m.Equipo.servicio_id == servicio_id).all())
    # El costo real es lo comprobado, no lo dispersado.
    costo_viaticos = sum((_d(v.monto_comprobado) for v in viaticos), CERO)

    costo_total = costo_personal + costo_viaticos + costo_vehiculo
    utilidad = facturacion - costo_total
    margen = (utilidad / facturacion * 100) if facturacion else CERO

    return {
        "servicio": servicio.folio,
        # La de todas las cifras de aqui: la del pais.
        "moneda": local.value,
        "facturacion": facturacion,
        "servicio_facturado": servicio_local,
        "viaticos_cobrados": viaticos_cobrados,
        # Si la factura es en otra moneda, lo que dice la factura y el
        # tipo de cambio con que aqui se paso a pesos.
        "en_otra_moneda": (_facturado_en_otra_moneda(db, servicio_id,
                                                     cotizacion, real, tc)
                           if tc else None),
        "costos": {
            "personal": costo_personal,
            "dias_festivos_pagados_al_doble": dias_festivos,
            "viaticos_comprobados": costo_viaticos,
            "vehiculo": costo_vehiculo,
            "dias_vehiculo": dias_vehiculo,
            "total": costo_total,
        },
        "utilidad": utilidad,
        "margen_pct": round(float(margen), 2),
    }


# ---------------------------------------------------------------- flujo

def estado(db: Session, servicio_id: int,
           ahora: datetime | None = None) -> dict:
    """El reloj del cierre del eventual, sin el comparativo.

    Vive aparte de la revision a proposito: **el plazo corre igual**
    --arranca cuando el servicio termina, tenga cotizacion o no-- y hay
    pantallas que solo necesitan el reloj, sin cargar el comparativo
    entero para pintarlo.

    Se manda el limite Y el momento, los dos en hora del pais del
    servicio: la cuenta regresiva sale de la resta entre ellos y no del
    reloj de la maquina donde este abierta la consola. De este plazo
    depende que el consultor cobre su comision; no puede depender de la
    hora de una laptop.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    ahora = reloj.ahora_del_servicio(db, servicio, ahora)
    # El del servicio. El implantado lleva uno por mes y se lee con
    # `cierre_mes.estado`.
    fila = (db.query(m.Cierre)
            .filter_by(servicio_id=servicio_id, contrato_id=None).first())
    if not fila:
        return {"momento": ahora.isoformat(), **vacio()}
    return {"momento": ahora.isoformat(), **ficha_del_cierre(db, fila, ahora)}


# Lo que dice el reloj cuando todavia no hay cierre: el servicio no ha
# terminado, o el mes sigue trabajandose.
VACIO = {"existe": False, "cierre_id": None, "estatus": None, "fase": None,
         "abierto_en": None, "comprobacion_hasta": None,
         "visto_bueno_desde": None, "limite": None,
         "minutos_restantes": None, "viaticos_abiertos": None,
         "motivo": None, "factura": None, "factura_error": None,
         "factura_anulada": None, "dentro_de_plazo": None, "total": None,
         "moneda": None, "tipo_cambio_gastos": None,
         "visto_bueno_en": None, "enviado_en": None, "devuelto_en": None,
         "devuelto_motivo": None, "aprobado_en": None, "reloj": None,
         "consultor": None, "comision": None, "cobro": None,
         "cobro_por_autorizar": False, "llave_factura": False,
         "prefactura": None, "prefactura_anulada": None,
         "prefactura_url_anulada": None, "que_paso": None,
         "prefactura_de_antes": False}

def vacio() -> dict:
    """VACIO, y si ya hay llave de la factura: la tarjeta dice desde antes
    que el tercer paso es la prefactura en Odoo (seccion 117)."""
    from app import odoo_facturacion
    return {**VACIO, "llave_factura": odoo_facturacion.hay_llave()}


# Cuantas horas tiene el consultor desde que finanzas le regresa el
# servicio (decision 1 de Salvador, 23 sep).
HORAS_REGRESO = 24


def limite_vigente(cierre: m.Cierre) -> tuple[str, datetime] | None:
    """El reloj que corre ahora, y de quien es.

    En comprobacion corre el del personal; sin visto bueno, el del
    consultor; regresado por finanzas, 24 horas desde el regreso. Con el
    visto bueno dado ya no corre ninguno.
    """
    e = cierre.estatus
    if e == m.EstatusCierre.ABIERTO:
        hasta = cierre.comprobacion_hasta or cierre.limite_consultor
        return ("personal", hasta) if hasta else None
    if e == m.EstatusCierre.DEVUELTO_A_OPERACION and cierre.devuelto_en:
        return ("regreso",
                cierre.devuelto_en + timedelta(hours=HORAS_REGRESO))
    if e in (m.EstatusCierre.SIN_VISTO_BUENO, m.EstatusCierre.EN_REVISION_IA,
             m.EstatusCierre.DEVUELTO_A_OPERACION):
        return ("consultor", cierre.limite_consultor)
    return None


def reloj_de(cierre: m.Cierre, ahora: datetime) -> dict | None:
    vigente = limite_vigente(cierre)
    if not vigente:
        return None
    quien, hasta = vigente
    return {"quien": quien, "hasta": hasta.isoformat(),
            "minutos": int((hasta - ahora).total_seconds() // 60)}


def ficha_del_cierre(db: Session, fila: m.Cierre, ahora: datetime) -> dict:
    """El cierre como lo pinta la tarjeta de visto bueno y facturacion.

    Las mismas llaves para el eventual y para el mes del implantado: la
    tarjeta es una sola. Todo en hora del pais del servicio.
    """
    from app import comisiones

    def iso(momento):
        return momento.isoformat() if momento else None

    consultor = (db.get(m.Persona, fila.servicio.consultor_id)
                 if fila.servicio and fila.servicio.consultor_id else None)
    moneda = moneda_del_cierre(db, fila)
    return {
        "existe": True,
        "cierre_id": fila.id,
        "estatus": fila.estatus.value,
        # La fase, para las pantallas: en que reloj va.
        "fase": FASES.get(fila.estatus),
        "abierto_en": iso(fila.abierto_en),
        "comprobacion_hasta": iso(fila.comprobacion_hasta),
        "visto_bueno_desde": iso(fila.visto_bueno_desde),
        "limite": iso(fila.limite_consultor),
        "minutos_restantes": int(
            (fila.limite_consultor - ahora).total_seconds() / 60),
        "viaticos_abiertos": _dinero_afuera(db, fila),
        "motivo": fila.motivo_apertura,
        "factura": fila.factura_odoo,
        "factura_error": fila.factura_error,
        "factura_anulada": fila.factura_anulada,
        "dentro_de_plazo": fila.dentro_de_plazo,
        # Lo que se mando a facturar; antes del visto bueno no hay cifra.
        "total": str(fila.total_ejecutado) if fila.enviado_en else None,
        # En que moneda sale la factura (seccion 82), y el tipo de cambio
        # con que se pasaron los gastos si quedo fijo con el visto bueno.
        "moneda": moneda.value if moneda else None,
        "tipo_cambio_gastos": cambio_en_json(tipo_cambio.fijo(
            fila.tipo_cambio_gastos, fila.tipo_cambio_gastos_fecha)),
        "visto_bueno_en": iso(fila.visto_bueno_en or fila.enviado_en),
        "enviado_en": iso(fila.enviado_en),
        "devuelto_en": iso(fila.devuelto_en),
        "devuelto_motivo": fila.devuelto_motivo,
        "aprobado_en": iso(fila.aprobado_en),
        # El reloj que corre ahora, sea de quien sea.
        "reloj": reloj_de(fila, ahora),
        "consultor": ({"id": consultor.id, "nombre": consultor.nombre}
                      if consultor else None),
        "comision": comisiones.del_cierre(db, fila),
        # El cobro de la cancelacion (seccion 105): lo que pidio el
        # consultor y si operaciones ya lo autorizo. Sin autorizar, la
        # tarjeta lo dice y el visto bueno espera.
        "cobro": cobro_del_cierre(db, fila),
        "cobro_por_autorizar": cobro_sin_autorizar(fila),
        # La prefactura en Odoo (seccion 117): su numero, lo que se mando
        # y donde se abre; o por que no salio.
        **prefactura_de(fila),
    }


def prefactura_de(fila: m.Cierre) -> dict:
    """Lo de la prefactura para la tarjeta del cierre: si hay llave, la
    que salio, la que se quedo en Odoo al regresarlo y por que no sale."""
    from app import facturacion, odoo_facturacion

    llave = odoo_facturacion.hay_llave()
    return {
        "llave_factura": llave,
        "prefactura": odoo_facturacion.detalle(fila),
        "prefactura_anulada": fila.prefactura_anulada_id,
        "prefactura_url_anulada": odoo_facturacion.url_en_odoo(
            fila.prefactura_anulada_id),
        "que_paso": (facturacion.que_paso(fila.factura_error)
                     if fila.factura_error else None),
        "prefactura_de_antes": bool(llave and fila.enviado_en
                                    and not fila.prefactura_desde
                                    and not fila.prefactura_odoo_id),
    }


# Como se dice cada estatus del cierre en un mensaje. El valor de la
# base ("enviado_finanzas") no es una frase: salia tal cual en la
# pantalla.
NOMBRE_ESTATUS = {
    m.EstatusCierre.ABIERTO: "comprobacion",
    m.EstatusCierre.SIN_VISTO_BUENO: "sin visto bueno",
    m.EstatusCierre.EN_REVISION_IA: "sin visto bueno",
    m.EstatusCierre.ENVIADO_FINANZAS: "facturacion: ya tiene visto bueno",
    m.EstatusCierre.DEVUELTO_A_OPERACION: "regresado a operacion",
    m.EstatusCierre.APROBADO: "cerrado por finanzas",
    m.EstatusCierre.FACTURADO: "cerrado y facturado",
}


def nombre_estatus(estatus: m.EstatusCierre) -> str:
    return NOMBRE_ESTATUS.get(estatus, estatus.value.replace("_", " "))


# El servicio que ya termino --o se cancelo--: solo a esos se les abre
# el cierre a mano (seccion 101). Antes la ruta lo abria sobre uno en
# curso o planeado, con el T0 que se le mandara, y las encuestas al
# cliente salian antes de trabajar el servicio.
YA_TERMINO = (m.EstatusServicio.TERMINADO, m.EstatusServicio.SIN_VISTO_BUENO,
              m.EstatusServicio.EN_FACTURACION, m.EstatusServicio.CERRADO,
              m.EstatusServicio.CANCELADO)


def abrir(db: Session, servicio_id: int, abierto_en: datetime | None = None,
          motivo: str = "termino", cobro: str | None = None) -> m.Cierre:
    """Arranca el primer reloj: las 24 horas del personal.

    `abierto_en` es T0 --el termino general, o la cancelacion--. De ahi
    salen `comprobacion_hasta` (T0 + 24 h) y, provisional, el limite
    del consultor en T0 + 48 h: el de verdad lo pone `avanzar` cuando
    llega T1.

    `cobro` solo en una cancelacion (seccion 105): lo que el consultor
    pidio cobrar, que direccion de operaciones autoriza despues.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    # El implantado no termina: cierra por mes, solo, al cerrar el ultimo
    # dia trabajado de cada mes (`cierre_mes`, seccion 56). Un cierre del
    # servicio entero lo sacaria de esa cadena.
    if servicio.tipo == m.TipoServicio.IMPLANTADO:
        raise HTTPException(409, {
            "mensaje": "El implantado cierra por mes, no por servicio",
            "que_hacer": "El cierre de cada mes arranca solo al cerrar su "
                         "ultimo dia trabajado."})

    existente = (db.query(m.Cierre)
                 .filter_by(servicio_id=servicio_id, contrato_id=None).first())
    if existente:
        return existente

    # En hora del pais del servicio. El plazo de 24 horas del consultor
    # decide si cobra su comision: si nace con el reloj del contenedor y
    # se juzga con otro, queda torcido desde el principio.
    momento = reloj.ahora_del_servicio(db, servicio, abierto_en)
    hasta = momento + timedelta(hours=HORAS_PERSONAL)
    cierre = m.Cierre(servicio_id=servicio_id, abierto_en=momento,
                      comprobacion_hasta=hasta,
                      limite_consultor=hasta + timedelta(hours=HORAS_CONSULTOR),
                      motivo_apertura=motivo,
                      cobro=cobro if motivo == CANCELACION else None)
    db.add(cierre)
    # `flush` y no `commit`: esto se llama tambien desde adentro del
    # cierre del ultimo dia, y ahi commitear a media transaccion partiria
    # en dos una operacion que tiene que ser una sola --la marca de fin y
    # el arranque del reloj--. Quien llama decide cuando guardar.
    db.flush()
    return cierre


# ---------------------------------------------------------------- visto bueno y regreso

def _de_que(cierre: m.Cierre) -> str:
    """El folio, y el mes si es del implantado: el folio es el mismo todo
    el contrato."""
    if cierre.contrato_id:
        return (f"{cierre.servicio.folio} {cierre.contrato.mes:02d}/"
                f"{cierre.contrato.anio}")
    return cierre.servicio.folio


def _pantalla(cierre: m.Cierre) -> str:
    """Donde se da el visto bueno: la del servicio, o el panel del mes en
    el implantado (seccion 56). El consultor trabaja en la consola, no en
    la app de campo."""
    if cierre.contrato_id:
        return f"/consola/#/implantado/{cierre.servicio_id}"
    return f"/consola/#/servicio/{cierre.servicio_id}"


def correo_al_consultor(db: Session, cierre: m.Cierre, asunto: str,
                        cuerpo: str, que_hacer: str, hasta: datetime,
                        motivo: str | None = None,
                        datos: dict | None = None) -> bool:
    """Un correo al consultor titular, ademas del aviso al telefono
    (seccion 101).

    Los dos avisos que deciden la comision --arrancan tus 24 horas;
    finanzas lo regreso-- salian solo por push, y el push solo llega al
    telefono que tiene la app de campo suscrita. El consultor trabaja en
    la consola: si no instalo la app, o cambio de telefono, T1 llegaba,
    sus 24 horas corrian y nadie se lo decia. Va en el idioma del pais,
    como los demas avisos a la gente de la casa, y dice que servicio,
    hasta cuando y que hacer. `asunto`, `cuerpo` y `que_hacer` son
    claves de `textos_aviso`; `datos` son huecos de mas para el asunto y
    el cuerpo, {hueco: clave de `textos_aviso`}, que se dicen en la misma
    lengua (seccion 105). Solo escribe; quien llama guarda.
    """
    from app import correo_html
    from app import textos_aviso as ta

    servicio = cierre.servicio
    consultor = (db.get(m.Persona, servicio.consultor_id)
                 if servicio.consultor_id else None)
    if consultor is None or not consultor.correo:
        return False
    lengua = ta.idioma_de(db, servicio, m.Destinatario.CONSULTOR)
    de_que = _de_que(cierre)
    huecos = {k: ta.t(lengua, v) for k, v in (datos or {}).items()}
    pares = [(ta.t(lengua, "enc_servicio"), de_que),
             (ta.t(lengua, "cie_vence"), f"{hasta:%d/%m/%Y %H:%M}")]
    if motivo:
        pares.append((ta.t(lengua, "cie_motivo"), motivo))
    pares.append((ta.t(lengua, "cie_que_hacer"), ta.t(lengua, que_hacer)))
    db.add(m.Notificacion(
        servicio_id=servicio.id,
        destinatario=m.Destinatario.CONSULTOR, canal=m.Canal.CORREO,
        correo=consultor.correo, idioma=lengua,
        asunto=ta.t(lengua, asunto, de_que=de_que, **huecos)[:200],
        cuerpo=ta.t(lengua, cuerpo, de_que=de_que,
                    fecha=f"{hasta:%d/%m}", hora=f"{hasta:%H:%M}",
                    **huecos)[:2000],
        datos=correo_html.guardar_datos(pares),
        enlace_seguimiento=_pantalla(cierre)))
    return True


def tomar(db: Session, cierre_id: int) -> m.Cierre:
    """El cierre con su fila bloqueada hasta que quien llama guarde
    (seccion 101), como `nomina.pagar` toma el corte.

    Es el candado del visto bueno: dos envios del mismo cierre en el
    mismo segundo leian los dos "sin visto bueno" y los dos generaban los
    ajustes de nomina. Con la fila tomada, el segundo espera al primero
    y lo encuentra ya en facturacion.
    """
    # `populate_existing`: quien llama ya leyo el cierre en esta sesion y
    # sin esto la fila bloqueada se lee de la base pero el objeto se
    # queda con el estatus de antes de esperar --justo el que el
    # candado tiene que corregir--.
    cierre = (db.query(m.Cierre)
              .filter(m.Cierre.id == cierre_id)
              .populate_existing().with_for_update().first())
    if not cierre:
        raise HTTPException(404, f"No existe el cierre {cierre_id}")
    return cierre


def dar_visto_bueno(cierre: m.Cierre, momento: datetime) -> None:
    """El visto bueno del consultor: pasa a facturacion.

    El primero es el que juzga el plazo, y se queda (decision 1 de
    Salvador, 23 sep): si finanzas lo regresa y el consultor lo vuelve a
    mandar, aquel "en plazo" no se pierde por la vuelta, ni un "fuera de
    plazo" se limpia con ella. Solo escribe; guarda quien llama.
    """
    cierre.enviado_en = momento
    if cierre.visto_bueno_en is None:
        cierre.visto_bueno_en = momento
        cierre.dentro_de_plazo = momento <= cierre.limite_consultor
    cierre.estatus = m.EstatusCierre.ENVIADO_FINANZAS


def _la_prefactura_sigue_en_borrador(cierre: m.Cierre) -> bool:
    """Antes de regresar, lo que Odoo dice de la prefactura (seccion 127,
    hallazgo r3-03). Timbrada: 409. Devuelve si Odoo no contesto, para
    decirlo en la bitacora. Sin prefactura o sin llave, nada que mirar."""
    from app import odoo_api, odoo_facturacion

    if not cierre.prefactura_odoo_id or not odoo_facturacion.hay_llave():
        return False
    try:
        de_odoo = odoo_facturacion.estado_en_odoo(cierre.prefactura_odoo_id)
    except (odoo_api.SinConexion, odoo_api.NoResponde, RuntimeError):
        return True
    if de_odoo and de_odoo.get("estado") == "posted":
        raise HTTPException(409, {
            "mensaje": (f"La prefactura #{cierre.prefactura_odoo_id} ya está "
                        f"timbrada en Odoo ({de_odoo.get('nombre') or ''}): "
                        "no se regresa"),
            "que_hacer": ("Lo timbrado se corrige con una nota de crédito en "
                          "Odoo. Si la factura está bien, anótala aquí con "
                          "«Ya se facturó en Odoo»."),
            "timbrada": de_odoo.get("nombre")})
    return False


def regresar(db: Session, cierre: m.Cierre, motivo: str, usuario: m.Usuario,
             ahora: datetime | None = None) -> dict:
    """Finanzas regresa el servicio --o el mes-- a operacion.

    Solo lo que esta en facturacion: lo cerrado ya genero la comision y
    su factura, y lo que no tiene visto bueno todavia no es de finanzas.
    El motivo se exige porque es lo que el consultor lee en su tarjeta.

    Decisiones de Salvador (23 sep): el consultor tiene 24 horas desde el
    regreso, y lo "en plazo" de su primer visto bueno se queda. Si la
    factura ya salio, se anula: con el nuevo visto bueno sale otra, que
    lleva el folio de la anulada para que en Odoo se sepa cual sustituye.
    La prefactura en borrador (seccion 117) la cancela el facturista en
    Odoo; la nueva sale cuando ya este cancelada.
    """
    from app import auditoria

    if cierre.estatus != m.EstatusCierre.ENVIADO_FINANZAS:
        raise HTTPException(409, {
            "mensaje": (f"Solo se regresa lo que esta en facturacion; este "
                        f"esta en {nombre_estatus(cierre.estatus)}"),
            "que_hacer": ("Lo que ya se cerro se corrige con una nota de "
                          "credito, no regresandolo.")})
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise HTTPException(400, {
            "mensaje": "Escribe por que se regresa",
            "que_hacer": "Es lo que el consultor lee para corregirlo."})
    # La prefactura que el facturista ya timbro no se regresa (seccion
    # 127, hallazgo r3-03): regresarla dejaba el cierre esperando que
    # alguien cancelara un CFDI, con el nuevo visto bueno trabado en «la
    # anterior sigue viva». Lo timbrado se corrige con nota de credito,
    # o se anota aqui con «Ya se facturo en Odoo». Si Odoo no contesta,
    # se regresa igual y se dice.
    odoo_no_contesto = _la_prefactura_sigue_en_borrador(cierre)

    momento = reloj.ahora_del_servicio(db, cierre.servicio, ahora)
    cierre.estatus = m.EstatusCierre.DEVUELTO_A_OPERACION
    cierre.devuelto_motivo = motivo[:500]
    cierre.devuelto_en = momento
    anulada = None
    if cierre.factura_odoo:
        anulada = cierre.factura_odoo
        cierre.factura_anulada = cierre.factura_odoo
        cierre.factura_odoo = None
        cierre.facturado_en = None
    # La prefactura en Odoo (seccion 117) se queda alla: Connect no la
    # cancela ni la borra --no puede--. Se recuerda cual era para no
    # mandar la nueva mientras siga viva; la cancela el facturista.
    prefactura = cierre.prefactura_odoo_id
    if prefactura:
        cierre.prefactura_anulada_id = prefactura
        cierre.prefactura_odoo_id = None
        cierre.prefactura_en = None
        cierre.prefactura_total = None
        cierre.prefactura_detalle = None
    # La que se anoto a mano se anula igual (seccion 96): la que sigue
    # puede llegar de Odoo o anotarse otra vez.
    cierre.factura_anotada_por_id = None
    cierre.factura_error = None
    # La factura que sigue sale con el tipo de cambio de su visto bueno
    # (seccion 82): mientras tanto se ve el que este puesto.
    cierre.tipo_cambio_gastos = None
    cierre.tipo_cambio_gastos_fecha = None
    # Arranca otro plazo --las 24 horas del regreso-- y trae sus propios
    # avisos de la mitad y del vencimiento (seccion 105): los del plazo
    # que ya paso no cuentan para este.
    cierre.aviso_mitad_en = None
    cierre.aviso_vencido_en = None
    # Vuelve al consultor: el eventual regresa a sin visto bueno. El
    # implantado no cambia de estatus: la fase la lleva el mes.
    if (not cierre.contrato_id
            and cierre.servicio.estatus == m.EstatusServicio.EN_FACTURACION):
        cierre.servicio.estatus = m.EstatusServicio.SIN_VISTO_BUENO
    de_que = _de_que(cierre)
    auditoria.registrar(db, usuario, cierre.servicio, "devolver a operacion",
                        (f"{de_que}: {motivo}"
                         + (f" (factura {anulada} anulada)" if anulada
                            else "")
                         + (f" (la prefactura #{prefactura} quedo en Odoo: "
                            f"la cancela el facturista)" if prefactura
                            else "")
                         + (" (Odoo no contesto: no se pudo ver si ya "
                            "estaba timbrada)" if odoo_no_contesto
                            else ""))[:400])
    hasta = momento + timedelta(hours=HORAS_REGRESO)
    # El correo se guarda con el regreso (seccion 101): el push de abajo
    # solo llega al telefono suscrito, y de estas 24 horas depende que la
    # factura vuelva a salir.
    correo_al_consultor(db, cierre, "cie_reg_asunto", "cie_reg_cuerpo",
                        "cie_reg_que_hacer", hasta, motivo=motivo)
    db.commit()

    if cierre.servicio.consultor_id:
        from app import push
        pantalla = _pantalla(cierre)
        try:
            push.avisar(
                db, cierre.servicio.consultor_id,
                titulo=f"{de_que}: finanzas lo regreso",
                cuerpo=(f"{motivo[:140]} Tienes hasta el "
                        f"{hasta:%d/%m a las %H:%M} para volver a mandarlo."),
                url=pantalla, etiqueta=f"regreso-{cierre.id}")
            db.commit()
        except Exception:                 # noqa: BLE001
            # Un aviso que no sale no deshace el regreso.
            db.rollback()
            registro.exception("no se pudo avisar el regreso de %s", de_que)
    return {"resultado": "devuelto a operacion", "motivo": motivo,
            "hasta": hasta.isoformat(), "factura_anulada": anulada,
            "prefactura_anulada": prefactura}


# ---------------------------------------------------------------- el segundo reloj

# La fase, para las pantallas: lo que cada estatus del cierre quiere
# decir en la cadena de dos relojes.
FASES = {
    m.EstatusCierre.ABIERTO: "comprobacion",
    m.EstatusCierre.SIN_VISTO_BUENO: "sin_visto_bueno",
    m.EstatusCierre.EN_REVISION_IA: "sin_visto_bueno",
    m.EstatusCierre.DEVUELTO_A_OPERACION: "devuelto",
    m.EstatusCierre.ENVIADO_FINANZAS: "en_facturacion",
    m.EstatusCierre.APROBADO: "aprobado",
    m.EstatusCierre.FACTURADO: "facturado",
}

# Lo que ya no cuenta como dinero afuera.
VIATICO_RESUELTO = (m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO,
                    m.EstatusViatico.CANCELADO)


def viaticos_abiertos(db: Session, servicio_id: int) -> int:
    """Cuantos viaticos del servicio siguen sin cerrar."""
    return (db.query(m.AsignacionViatico)
            .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == servicio_id,
                    m.AsignacionViatico.estatus.notin_(VIATICO_RESUELTO))
            .count())


def _dinero_afuera(db: Session, cierre: m.Cierre) -> int:
    """Los viaticos sin cerrar de lo que cierra: el servicio entero en
    el eventual; en el implantado, solo los del mes (seccion 56)."""
    if cierre.contrato_id:
        from app import cierre_mes
        return cierre_mes.viaticos_abiertos(db, cierre.contrato)
    return viaticos_abiertos(db, cierre.servicio_id)


def avanzar(db: Session, cierre: m.Cierre,
            ahora: datetime | None = None) -> bool:
    """De la comprobacion al visto bueno: pone T1 y el limite del consultor.

    Lo mueve el reloj del sistema, no una persona. T1 llega cuando
    vencen las 24 h del personal (T0 + 24) o antes, si todos los
    viaticos del servicio ya cerraron, se devolvieron o se cancelaron:
    no hay nada que esperar (decision 2 de la propuesta).

    Solo escribe; quien llama decide cuando guardar. Devuelve si movio.
    """
    if cierre.estatus != m.EstatusCierre.ABIERTO:
        return False
    servicio = cierre.servicio
    ahora = reloj.ahora_del_servicio(db, servicio, ahora)

    viejo = cierre.comprobacion_hasta is None
    if viejo:
        # Nacio antes de los dos relojes: su plazo era el de siempre, 24 h
        # desde que se abrio. Se respeta tal cual (regla 10 de la
        # propuesta): lo ya terminado no se toca.
        t1, limite = cierre.abierto_en, cierre.limite_consultor
    elif ahora >= cierre.comprobacion_hasta:
        t1 = cierre.comprobacion_hasta
        limite = t1 + timedelta(hours=HORAS_CONSULTOR)
    elif _dinero_afuera(db, cierre) == 0:
        t1 = ahora
        limite = t1 + timedelta(hours=HORAS_CONSULTOR)
    else:
        return False

    cierre.visto_bueno_desde = t1
    cierre.limite_consultor = limite
    cierre.estatus = m.EstatusCierre.SIN_VISTO_BUENO
    # El cancelado se queda cancelado: su rastro es el cierre.
    if servicio.estatus == m.EstatusServicio.TERMINADO:
        servicio.estatus = m.EstatusServicio.SIN_VISTO_BUENO

    if servicio.consultor_id and not viejo:
        from app import push
        # En el implantado el visto bueno es del mes y se da en su
        # panel (seccion 56).
        de_que = _de_que(cierre)
        pantalla = _pantalla(cierre)
        # Y por correo (seccion 101): el push solo llega al telefono que
        # tiene la app suscrita, y de este plazo depende la comision.
        correo_al_consultor(db, cierre, "cie_vb_asunto", "cie_vb_cuerpo",
                            "cie_vb_que_hacer", limite)
        try:
            push.avisar(
                db, servicio.consultor_id,
                titulo=f"{de_que}: tienes 24 h para el visto bueno",
                cuerpo=("La comprobacion del personal termino. Tu plazo "
                        f"vence el {limite:%d/%m a las %H:%M}."),
                # El consultor trabaja en la consola, no en la app de campo.
                url=pantalla,
                etiqueta=f"visto-bueno-{cierre.id}")
        except Exception:                 # noqa: BLE001
            # Un aviso que no sale no puede frenar el reloj.
            registro.exception("no se pudo avisar el visto bueno de %s",
                               servicio.folio)
    return True


def avanzar_cierres(db: Session, ahora: datetime | None = None) -> list[str]:
    """El barrido de cada cinco minutos: lo que llego a T1 pasa a sin
    visto bueno. Devuelve los folios que movio."""
    movidos = []
    for cierre in (db.query(m.Cierre)
                   .filter(m.Cierre.estatus == m.EstatusCierre.ABIERTO)
                   .all()):
        if avanzar(db, cierre, ahora):
            # El mes del implantado se dice con su mes: el folio es el
            # mismo todo el contrato.
            movidos.append(
                cierre.servicio.folio if not cierre.contrato_id else
                f"{cierre.servicio.folio} {cierre.contrato.mes:02d}/"
                f"{cierre.contrato.anio}")
    db.commit()
    return movidos


# ---------------------------------------------------------------- el cobro al cancelar
#
# Seccion 105, decision 1 de Salvador (29 sep): al cancelar, el consultor
# elige si al cliente se le cobra la cotizacion completa o lo ejecutado,
# y direccion de operaciones lo autoriza desde la tarjeta del cierre.
# Mientras no lo autorice, el cierre no se manda a finanzas.

LARGO_NOTA = 400
# Con el visto bueno dado la factura ya salio, o esta por salir, con ese
# cobro: ya no se autoriza otro. Lo que cambie lo regresa finanzas.
YA_SE_MANDO = (m.EstatusCierre.ENVIADO_FINANZAS, m.EstatusCierre.APROBADO,
               m.EstatusCierre.FACTURADO)
# La clave de `textos_aviso` que dice cada cobro.
NOMBRE_DEL_COBRO = {COBRO_COMPLETO: "cie_cobro_completo",
                    COBRO_EJECUTADO: "cie_cobro_ejecutado"}


def autorizar_cobro(db: Session, cierre: m.Cierre, cobro: str,
                    nota: str | None, usuario: m.Usuario,
                    ahora: datetime | None = None) -> dict:
    """Direccion de operaciones decide como se cobra la cancelacion.

    Puede quedarse con lo que pidio el consultor o cambiarlo; si lo
    cambia, dice por que. Queda en la bitacora del servicio con quien y
    cuando, y al consultor le llega por correo y al telefono: es lo que
    destraba su visto bueno. Guarda y avisa.
    """
    from app import auditoria, push

    if cierre.contrato_id or cierre.motivo_apertura != CANCELACION:
        raise HTTPException(409, {
            "mensaje": "El cobro solo se autoriza en un servicio cancelado",
            "que_hacer": "Un servicio que terminó se factura por lo "
                         "ejecutado: no hay nada que autorizar."})
    if cobro not in COBROS:
        raise HTTPException(400, {
            "mensaje": "Di si se cobra completo o lo ejecutado",
            "que_hacer": "Completo es la cotización autorizada tal cual; "
                         "ejecutado es lo que se trabajó."})
    if cierre.estatus in YA_SE_MANDO:
        raise HTTPException(409, {
            "mensaje": (f"El cierre ya se mandó a finanzas con el cobro "
                        f"{cierre.cobro or COBRO_EJECUTADO}"),
            "que_hacer": "Si hay que cambiarlo, finanzas lo regresa a "
                         "operación y se vuelve a autorizar."})
    nota = " ".join((nota or "").split()) or None
    if nota and len(nota) > LARGO_NOTA:
        raise HTTPException(400, {
            "mensaje": "La nota es demasiado larga",
            "que_hacer": f"Caben {LARGO_NOTA} letras."})
    pedido = cierre.cobro
    if pedido and cobro != pedido and not nota:
        raise HTTPException(400, {
            "mensaje": f"El consultor pidió cobrar {pedido}: di por qué "
                       f"se cobra {cobro}",
            "que_hacer": "Escribe una nota; es lo que el consultor lee "
                         "en su correo y lo que queda en la bitácora."})

    momento = reloj.ahora_del_servicio(db, cierre.servicio, ahora)
    cierre.cobro = cobro
    cierre.cobro_autorizado_en = momento
    cierre.cobro_autorizado_por_id = usuario.persona_id
    de_que = _de_que(cierre)
    auditoria.registrar(
        db, usuario, cierre.servicio, "autorizar cobro",
        (f"{de_que}: se cobra {cobro}"
         + (f" (el consultor pidió {pedido})" if pedido and pedido != cobro
            else "")
         + (f" · {nota}" if nota else ""))[:400])
    # Por correo, con lo que falta: su visto bueno y hasta cuando.
    correo_al_consultor(db, cierre, "cie_cobro_asunto", "cie_cobro_cuerpo",
                        "cie_cobro_que_hacer", cierre.limite_consultor,
                        motivo=nota, datos={"cobro": NOMBRE_DEL_COBRO[cobro]})
    db.commit()

    if cierre.servicio.consultor_id:
        lengua = push.idioma_de(db, cierre.servicio.consultor_id)
        try:
            push.avisar(
                db, cierre.servicio.consultor_id,
                titulo=push.tx(lengua, "cie_cobro_titulo", de_que=de_que,
                               cobro=push.tx(lengua, f"cobro_{cobro}")),
                cuerpo=push.tx(lengua, "cie_cobro_cuerpo"),
                url=_pantalla(cierre), etiqueta=f"cobro-{cierre.id}")
            db.commit()
        except Exception:                 # noqa: BLE001
            # Un aviso que no sale no deshace la autorizacion.
            db.rollback()
            registro.exception("no se pudo avisar el cobro de %s", de_que)
    quien = db.get(m.Persona, usuario.persona_id) if usuario.persona_id else None
    return {"resultado": "cobro autorizado", "cobro": cobro, "pedido": pedido,
            "autorizado_en": momento.isoformat(),
            "autorizado_por": quien.nombre if quien else None,
            "nota": nota}


def _totales_de_la_cancelacion(db: Session, servicio: m.Servicio) -> tuple:
    """(total cotizado, total ejecutado, moneda) de un cancelado, para la
    bandeja del director. Sin cotizacion, o con algo que la lista no
    cotiza, la cifra que no se puede decir va vacia: la bandeja no se
    cae por un servicio a medio capturar."""
    vigente = cot.vigente(db, servicio.id)
    if vigente is None:
        return None, None, None
    try:
        trabajado = ejecutado(db, servicio, vigente.tarifario_id,
                              cot.con_paquetes(db, vigente))["total"]
    except HTTPException:
        trabajado = None
    return _d(vigente.total), trabajado, vigente.moneda.value


def cobros_por_autorizar(db: Session) -> list[dict]:
    """Las cancelaciones que esperan que operaciones diga como se cobran
    (seccion 105), para la pantalla del director de operaciones.

    Un renglon por cierre de cancelacion con cobro pedido y sin
    autorizar, del mas viejo al mas nuevo: el servicio, su cliente y su
    consultor, lo que el consultor pidio, cuando se cancelo, y lo que
    vale cada opcion --el total cotizado y lo trabajado--. Lo que ya
    cerro finanzas no espera nada.
    """
    filas = (db.query(m.Cierre)
             .filter(m.Cierre.contrato_id.is_(None),
                     m.Cierre.motivo_apertura == CANCELACION,
                     m.Cierre.cobro.isnot(None),
                     m.Cierre.cobro_autorizado_en.is_(None),
                     m.Cierre.estatus.notin_((m.EstatusCierre.APROBADO,
                                              m.EstatusCierre.FACTURADO)))
             .order_by(m.Cierre.abierto_en, m.Cierre.id).all())
    salida = []
    for c in filas:
        servicio = c.servicio
        consultor = (db.get(m.Persona, servicio.consultor_id)
                     if servicio.consultor_id else None)
        cotizado, trabajado, moneda = _totales_de_la_cancelacion(db, servicio)
        salida.append({
            "cierre_id": c.id, "servicio_id": servicio.id,
            "folio": servicio.folio,
            "cliente": servicio.cliente.nombre if servicio.cliente else None,
            "consultor": consultor.nombre if consultor else None,
            "consultor_id": servicio.consultor_id,
            "cobro": c.cobro,
            "cancelado_en": c.abierto_en.isoformat() if c.abierto_en else None,
            "total_cotizado": cotizado, "total_ejecutado": trabajado,
            "moneda": moneda,
            "fase": FASES.get(c.estatus),
            "pantalla": _pantalla(c),
        })
    return salida


# ---------------------------------------------------------------- los plazos del cierre
#
# Seccion 105, decision 12 de Salvador (29 sep): vencido el plazo del
# consultor nada se movia ni avisaba a nadie (hallazgo 59). Ahora, a la
# mitad del plazo se le avisa al consultor y, al vencer, al consultor y
# al director de operaciones, por correo y al telefono. El servicio sigue
# esperando su visto bueno --o el de direccion, como cobertura--, ya sin
# comision. Los dos plazos que se vigilan son los del consultor: sus 24
# horas y las 24 horas del regreso de finanzas. El fin de las 24 horas
# del personal ya tiene su aviso: "arrancan tus 24 horas" (seccion 101).

DEL_CONSULTOR = (m.EstatusCierre.SIN_VISTO_BUENO, m.EstatusCierre.EN_REVISION_IA,
                 m.EstatusCierre.DEVUELTO_A_OPERACION)


def plazo_desde(cierre: m.Cierre, quien: str) -> datetime | None:
    """Cuando arranco el plazo que corre: T1 para el del consultor --o
    la apertura, en un cierre de antes de los dos relojes--, y el regreso
    de finanzas para el suyo."""
    if quien == "regreso":
        return cierre.devuelto_en
    return cierre.visto_bueno_desde or cierre.abierto_en


def directores_de_operaciones(db: Session, pais_id: int | None) -> list:
    """A quien se le avisa por direccion de operaciones: los de ese pais
    con acceso abierto; si el pais no tiene el suyo, los que haya (como
    la escalacion del task sheet, seccion 101)."""
    filas = (db.query(m.Persona)
             .join(m.Usuario, m.Usuario.persona_id == m.Persona.id)
             .filter(m.Usuario.rol == m.Rol.DIRECTOR_OPERACIONES,
                     m.Usuario.activo.is_(True))
             .order_by(m.Persona.id).all())
    del_pais = [p for p in filas if p.plaza and p.plaza.pais_id == pais_id]
    return del_pais or filas


def _desde_hace(minutos: int) -> str:
    """"3 h 20 min", "2 d 5 h": cuanto lleva vencido, para la pantalla."""
    if minutos < 60:
        return f"{minutos} min"
    horas, resto = divmod(minutos, 60)
    if horas < 24:
        return f"{horas} h {resto} min" if resto else f"{horas} h"
    dias, horas = divmod(horas, 24)
    return f"{dias} d {horas} h" if horas else f"{dias} d"


def plazos_vencidos(db: Session, ahora: datetime | None = None) -> list[dict]:
    """Los cierres cuyo plazo del consultor ya vencio (seccion 105), para
    la pantalla del director de operaciones.

    Un renglon por cierre --el mes del implantado con su mes-- que sigue
    esperando el visto bueno con el plazo pasado: que plazo vencio (el
    del consultor, o el del regreso de finanzas), cuando, desde hace
    cuanto y si ya se aviso. Los mas vencidos primero. Todo en hora del
    pais del servicio.
    """
    relojes = reloj.Relojes(db, ahora)
    salida = []
    for c in (db.query(m.Cierre)
              .filter(m.Cierre.estatus.in_(DEL_CONSULTOR)).all()):
        vigente = limite_vigente(c)
        if not vigente:
            continue
        quien, hasta = vigente
        momento = relojes.del_servicio(c.servicio)
        if momento < hasta:
            continue
        servicio = c.servicio
        consultor = (db.get(m.Persona, servicio.consultor_id)
                     if servicio.consultor_id else None)
        minutos = int((momento - hasta).total_seconds() // 60)
        salida.append({
            "cierre_id": c.id, "servicio_id": servicio.id,
            "folio": servicio.folio, "de_que": _de_que(c),
            "tipo": servicio.tipo.value,
            "contrato_id": c.contrato_id,
            "periodo": (f"{c.contrato.mes:02d}/{c.contrato.anio}"
                        if c.contrato_id else None),
            "cliente": servicio.cliente.nombre if servicio.cliente else None,
            "consultor": consultor.nombre if consultor else None,
            "consultor_id": servicio.consultor_id,
            "plazo": quien,
            "fase": FASES.get(c.estatus),
            "vencio_en": hasta.isoformat(),
            "desde_hace_minutos": minutos,
            "desde_hace": _desde_hace(minutos),
            "avisado_en": (c.aviso_vencido_en.isoformat()
                           if c.aviso_vencido_en else None),
            "pantalla": _pantalla(c),
        })
    salida.sort(key=lambda x: -x["desde_hace_minutos"])
    return salida


def _correo_al_director(db: Session, cierre: m.Cierre, director: m.Persona,
                        quien: str, hasta: datetime,
                        consultor: m.Persona | None) -> bool:
    """El correo del plazo vencido a direccion de operaciones, en el
    idioma de su pais. Solo escribe; quien llama guarda."""
    from app import correo_html
    from app import textos_aviso as ta

    if not director.correo:
        return False
    pais = db.get(m.Pais, director.plaza.pais_id) if director.plaza else None
    lengua = pais.idioma if pais else "es"
    de_que = _de_que(cierre)
    nombre = consultor.nombre if consultor else "—"
    cuerpo = "cie_venc_dir_reg_cuerpo" if quien == "regreso" else "cie_venc_dir_cuerpo"
    db.add(m.Notificacion(
        servicio_id=cierre.servicio_id,
        destinatario=m.Destinatario.COLABORADOR, canal=m.Canal.CORREO,
        correo=director.correo, idioma=lengua,
        asunto=ta.t(lengua, "cie_venc_dir_asunto", de_que=de_que,
                    consultor=nombre)[:200],
        cuerpo=ta.t(lengua, cuerpo, de_que=de_que, consultor=nombre,
                    fecha=f"{hasta:%d/%m}", hora=f"{hasta:%H:%M}")[:2000],
        datos=correo_html.guardar_datos([
            (ta.t(lengua, "enc_servicio"), de_que),
            (ta.t(lengua, "cie_consultor"), nombre,
             consultor.telefono if consultor else None),
            (ta.t(lengua, "cie_vence"), f"{hasta:%d/%m/%Y %H:%M}"),
            (ta.t(lengua, "cie_que_hacer"),
             ta.t(lengua, "cie_venc_dir_que_hacer"))]),
        enlace_seguimiento=_pantalla(cierre)))
    return True


def _push_del_plazo(db: Session, persona_id: int, cierre: m.Cierre,
                    titulo: str, cuerpo: str, etiqueta: str, **datos) -> None:
    """Un aviso al telefono por el plazo, en el idioma de quien lo recibe.
    Nunca frena el barrido."""
    from app import push

    lengua = push.idioma_de(db, persona_id)
    try:
        push.avisar(db, persona_id,
                    titulo=push.tx(lengua, titulo, de_que=_de_que(cierre),
                                   **datos),
                    cuerpo=push.tx(lengua, cuerpo, **datos),
                    url=_pantalla(cierre), etiqueta=f"{etiqueta}-{cierre.id}")
    except Exception:                     # noqa: BLE001
        registro.exception("no se pudo avisar el plazo de %s", _de_que(cierre))


def avisar_plazos(db: Session, ahora: datetime | None = None) -> dict:
    """El barrido de los plazos del consultor (seccion 105, decision 12).

    Por cada cierre que espera el visto bueno: a la mitad del plazo que
    corre, correo y telefono al consultor titular; al vencer, correo y
    telefono al consultor y al director de operaciones del pais. Cada
    aviso una sola vez, con su fecha en el cierre; la vuelta que llega
    cuando el plazo ya vencio manda solo el del vencimiento. El regreso
    de finanzas limpia las dos fechas y arranca sus propios avisos.
    Devuelve los folios avisados.
    """
    relojes = reloj.Relojes(db, ahora)
    mitad, vencidos = [], []
    for cierre in (db.query(m.Cierre)
                   .filter(m.Cierre.estatus.in_(DEL_CONSULTOR)).all()):
        vigente = limite_vigente(cierre)
        if not vigente:
            continue
        quien, hasta = vigente
        servicio = cierre.servicio
        momento = relojes.del_servicio(servicio)
        de_que = _de_que(cierre)
        consultor = (db.get(m.Persona, servicio.consultor_id)
                     if servicio.consultor_id else None)
        regreso = quien == "regreso"
        datos = {"fecha": f"{hasta:%d/%m}", "hora": f"{hasta:%H:%M}"}

        if cierre.aviso_vencido_en is None and momento >= hasta:
            cierre.aviso_vencido_en = momento
            correo_al_consultor(
                db, cierre, "cie_venc_asunto",
                "cie_venc_reg_cuerpo" if regreso else "cie_venc_cuerpo",
                "cie_venc_que_hacer", hasta)
            if consultor:
                _push_del_plazo(db, consultor.id, cierre, "cie_venc_titulo",
                                "cie_venc_reg_cuerpo" if regreso
                                else "cie_venc_cuerpo", "plazo-vencido", **datos)
            for director in directores_de_operaciones(db, servicio.pais_id):
                _correo_al_director(db, cierre, director, quien, hasta, consultor)
                _push_del_plazo(db, director.id, cierre, "cie_venc_dir_titulo",
                                "cie_venc_dir_reg_cuerpo" if regreso
                                else "cie_venc_dir_cuerpo", "plazo-vencido",
                                consultor=consultor.nombre if consultor else "—",
                                **datos)
            vencidos.append(de_que)
            continue

        desde = plazo_desde(cierre, quien)
        if (cierre.aviso_mitad_en is None and cierre.aviso_vencido_en is None
                and desde is not None and momento < hasta
                and momento >= desde + (hasta - desde) / 2):
            cierre.aviso_mitad_en = momento
            correo_al_consultor(
                db, cierre, "cie_mitad_asunto",
                "cie_mitad_reg_cuerpo" if regreso else "cie_mitad_cuerpo",
                "cie_mitad_que_hacer", hasta)
            if consultor:
                _push_del_plazo(db, consultor.id, cierre, "cie_mitad_titulo",
                                "cie_mitad_cuerpo", "plazo-mitad", **datos)
            mitad.append(de_que)
    db.commit()
    return {"mitad": mitad, "vencidos": vencidos}

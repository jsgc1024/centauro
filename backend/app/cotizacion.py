"""Cotizacion del servicio. Es la referencia contra la que se compara el cierre."""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models as m
from app import tipo_cambio


# La serie de las cotizaciones que se arman en Cotizaciones (seccion 114,
# decision 1 de Salvador: numeracion nueva de Connect). Cuatro digitos:
# se hacen mas cotizaciones que servicios.
SERIE = "EP/COT"

# La propuesta del implantado vive en la misma tabla, con su serie
# (seccion 115, decision 1): EP/PRO-0001. Lo que busca la cotizacion de
# un servicio --la vigente, sus versiones, la que compara el cierre--
# busca solo las de clase «cotizacion»: la propuesta queda en su
# implantado, pero no es la cotizacion de nadie.
COTIZACION = "cotizacion"
PROPUESTA = "propuesta"
SERIES = {COTIZACION: SERIE, PROPUESTA: "EP/PRO"}


def folio_texto(numero: int | None, clase: str = COTIZACION) -> str | None:
    return f"{SERIES[clase]}-{numero:04d}" if numero else None


def de_cotizacion(consulta):
    """Solo las cotizaciones: sin las propuestas del implantado."""
    return consulta.filter(m.Cotizacion.clase == COTIZACION)


def general_del_pais(db: Session, pais_id: int,
                     moneda=None) -> m.Tarifario | None:
    """La lista que paga quien no negocio la suya: la general de su pais
    en Odoo (seccion 77). Con generales en dos monedas (seccion 120), la
    de la moneda que se pide o, sin decir cual, la de la moneda del pais.
    Con dos de la misma moneda, la que viene de Odoo."""
    consulta = (db.query(m.Tarifario)
                .filter(m.Tarifario.pais_id == pais_id,
                        m.Tarifario.general.is_(True),
                        m.Tarifario.activo.is_(True)))
    orden = [m.Tarifario.odoo_id.is_(None), m.Tarifario.id]
    if moneda is not None:
        consulta = consulta.filter(m.Tarifario.moneda == m.Moneda(moneda))
    else:
        local = tipo_cambio.local_del_pais(db, pais_id)
        if local is not None:
            orden.insert(0, m.Tarifario.moneda != local)
    return consulta.order_by(*orden).first()


def monedas_generales(db: Session, pais_id: int) -> list[str]:
    """Las monedas en que el pais tiene lista general: la del pais
    primero. Con una sola no hay que escoger."""
    local = tipo_cambio.local_del_pais(db, pais_id)
    monedas = {t.moneda for t in db.query(m.Tarifario).filter(
        m.Tarifario.pais_id == pais_id, m.Tarifario.general.is_(True),
        m.Tarifario.activo.is_(True))}
    return [x.value for x in sorted(monedas, key=lambda x: (x != local, x.value))]


def _tarifario_de(db: Session, servicio: m.Servicio) -> m.Tarifario:
    """La lista con que se recotiza el servicio: la del cliente. Si el
    cliente esta en la general y la cotizacion autorizada salio en otra
    moneda (seccion 120), la general de esa moneda: la recotizacion sigue
    en la moneda que el cliente autorizo."""
    cliente = db.get(m.Cliente, servicio.cliente_id)
    if not cliente or not cliente.tarifario_id:
        raise HTTPException(400, "El cliente no tiene tarifario asignado")
    tarifario = db.get(m.Tarifario, cliente.tarifario_id)
    vig = vigente(db, servicio.id)
    if tarifario.general and vig is not None and vig.moneda != tarifario.moneda:
        otra = general_del_pais(db, servicio.pais_id, vig.moneda)
        if otra is not None:
            return otra
    return tarifario


def _sin_precio(que: str, modalidad: m.Modalidad | None) -> HTTPException:
    """La lista del cliente no cotiza eso. Con clave y datos (seccion
    101): la revision del cierre lo convierte en una observacion que la
    pantalla dice en su idioma, en vez de reventar con el texto crudo."""
    codigo = modalidad.codigo.value if modalidad else ""
    return HTTPException(400, {
        "mensaje": f"El tarifario no tiene precio para {que} en {codigo}",
        "que_hacer": "Corrige el rol o la unidad de la asignación, o pide "
                     "que la lista del cliente lo incluya.",
        "clave": "sin_precio", "que": que, "modalidad": codigo})


def precio_recurso(db: Session, tarifario_id: int, perfil_id: int | None,
                   modalidad_id: int) -> m.TarifaRecurso:
    """El precio del rol. Sin rol no hay precio que buscar."""
    if not perfil_id:
        raise HTTPException(400, {
            "mensaje": "Hay personal asignado sin rol. Diga con que rol va "
                       "antes de cotizar o cerrar.",
            "que_hacer": "Ponle su rol en el equipo del día.",
            "clave": "sin_rol"})
    tarifa = (db.query(m.TarifaRecurso)
              .filter_by(tarifario_id=tarifario_id, perfil_id=perfil_id,
                         modalidad_id=modalidad_id).first())
    if not tarifa:
        perfil = db.get(m.PerfilPersonal, perfil_id)
        raise _sin_precio(perfil.nombre if perfil else str(perfil_id),
                          db.get(m.Modalidad, modalidad_id))
    return tarifa


def precio_vehiculo(db: Session, tarifario_id: int, categoria_id: int,
                    modalidad_id: int) -> m.TarifaVehiculo:
    tarifa = (db.query(m.TarifaVehiculo)
              .filter_by(tarifario_id=tarifario_id, categoria_id=categoria_id,
                         modalidad_id=modalidad_id).first())
    if not tarifa:
        categoria = db.get(m.CategoriaVehiculo, categoria_id)
        raise _sin_precio(categoria.nombre if categoria else str(categoria_id),
                          db.get(m.Modalidad, modalidad_id))
    return tarifa


# Solo cuenta el paquete que la lista del cliente pacta: el que sale de su
# propia regla en Odoo. La lectura le pone a toda lista todos los paquetes
# que finanzas confirmo --si la lista no lo pacta, con el precio de la
# general o el «Precio de venta» del producto--, y un cliente que compra
# conductor y unidad por separado, como Control Risks, no compra el
# paquete porque el producto exista. Sin origen es lo que se capturo en
# Centauro, que es pactado por definicion.
PACTADO = "propio"


def es_pactado(tarifa: m.TarifaPaquete) -> bool:
    return tarifa.origen in (PACTADO, None)


def _pactados(db: Session):
    return db.query(m.TarifaPaquete).filter(
        or_(m.TarifaPaquete.origen == PACTADO, m.TarifaPaquete.origen.is_(None)))


def paquetes_del_tarifario(db: Session, tarifario_id: int,
                           modalidad_id: int) -> list[m.TarifaPaquete]:
    """Los paquetes conductor + unidad que la lista pacta en esa modalidad
    (seccion 79). En el orden en que se leyeron: si un rol cabe en dos
    paquetes el mismo dia, gana el primero, y asi siempre igual."""
    return (_pactados(db)
            .filter_by(tarifario_id=tarifario_id, modalidad_id=modalidad_id)
            .order_by(m.TarifaPaquete.id).all())


def precio_paquete(db: Session, tarifario_id: int, perfil_id: int | None,
                   categoria_id: int | None, modalidad_id: int) -> m.TarifaPaquete:
    if not perfil_id or not categoria_id:
        raise HTTPException(400, "Un paquete lleva el rol y la unidad.")
    tarifa = (_pactados(db)
              .filter_by(tarifario_id=tarifario_id, perfil_id=perfil_id,
                         categoria_id=categoria_id, modalidad_id=modalidad_id)
              .first())
    if not tarifa:
        perfil = db.get(m.PerfilPersonal, perfil_id)
        categoria = db.get(m.CategoriaVehiculo, categoria_id)
        modalidad = db.get(m.Modalidad, modalidad_id)
        raise HTTPException(400, f"La lista del cliente no pacta el paquete "
                                 f"{perfil.nombre} + {categoria.nombre} en "
                                 f"{modalidad.codigo.value}")
    return tarifa


def nombre_del_paquete(tarifa: m.TarifaPaquete) -> str:
    return f"{tarifa.perfil.nombre} + {tarifa.categoria.nombre}"


def usa_paquetes(tarifario: m.Tarifario | None, gastos: str) -> bool:
    """Si el conductor y la unidad del mismo dia van en el paquete de la
    lista (seccion 115, regla de Salvador del 1 de octubre).

    El paquete de una lista cuyos paquetes traen los gastos --«Todo
    incluido», como PE · General Mexico-- solo se usa cuando los gastos
    operativos van dentro del precio. Con monto fijo o por comprobar el
    paquete ya no cuadra: el cliente pagaria los gastos dos veces. Ahi el
    conductor y la unidad se cotizan a su precio unitario, sin gastos, y
    los gastos van aparte segun el modo. La lista cuyos paquetes no traen
    gastos los empareja en cualquier modo, como siempre.

    Vale igual para la cotizacion --la vista previa, al guardarla y la de
    Cotizaciones-- que para el cierre y la factura: lo cotizado y lo
    cobrado se comparan igual.
    """
    if tarifario is None or not tarifario.paquetes_con_viaticos:
        return True
    return gastos == GASTOS_DENTRO


def modo_de_las_lineas(viaticos_incluidos: bool, lineas: list[dict]) -> str:
    """El modo de gastos de lo que se va a cotizar: netos si no van
    incluidos; con un renglon de gastos con monto, monto fijo; si no,
    dentro del precio. Es `modo_de_gastos` antes de que exista la
    cotizacion."""
    if not viaticos_incluidos:
        return GASTOS_COMPROBAR
    if any(m.TipoLinea(l["tipo"]) == m.TipoLinea.VIATICOS
           and Decimal(str(l.get("precio_unitario") or 0)) > 0 for l in lineas):
        return GASTOS_FIJOS
    return GASTOS_DENTRO


def con_paquetes(db: Session, cotizacion: m.Cotizacion) -> bool:
    """`usa_paquetes` de una cotizacion que ya existe: con su lista y su
    modo de gastos."""
    tarifario = (db.get(m.Tarifario, cotizacion.tarifario_id)
                 if cotizacion.tarifario_id else None)
    return usa_paquetes(tarifario, modo_de_gastos(cotizacion))


def emparejar(roles: dict, unidades: dict, paquetes: list) -> list[tuple]:
    """[(paquete, cuantos)] del dia de un equipo. `roles`: {perfil: cuantos}
    y `unidades`: {categoria: cuantas}; lo que se va en paquetes se les
    descuenta, y lo que queda se cobra suelto.

    Asi se cobra lo que el cliente pacto (seccion 79): el dia en que el
    equipo lleva ese rol con esa unidad, y la lista pacta el paquete, un
    solo renglon con el precio del paquete, no los dos por separado.
    """
    salida = []
    for paquete in paquetes:
        cuantos = min(roles.get(paquete.perfil_id, 0),
                      unidades.get(paquete.categoria_id, 0))
        if cuantos:
            salida.append((paquete, cuantos))
            roles[paquete.perfil_id] -= cuantos
            unidades[paquete.categoria_id] -= cuantos
    return salida


def generar(db: Session, servicio_id: int, lineas: list[dict],
            viaticos_incluidos: bool = True, creada_por_id: int | None = None,
            motivo: str | None = None) -> m.Cotizacion:
    """Arma la cotizacion tomando los precios del tarifario del cliente.

    Cada linea: {fecha, equipo, tipo, perfil_id | categoria_id, cantidad}
    --el paquete trae los dos--. La modalidad se toma de la jornada de ese
    dia, porque la modalidad es de cada dia y no del servicio completo.

    El rol y la unidad del mismo dia y el mismo equipo que la lista del
    cliente tiene en paquete se cotizan como paquete (seccion 79): asi se
    cobran al cerrar, y lo cotizado y lo ejecutado se comparan igual.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    tarifario = _tarifario_de(db, servicio)

    # Version nueva si ya habia cotizacion: la anterior queda sustituida.
    anteriores = _versiones(db, servicio_id)
    version = (anteriores[0].version + 1) if anteriores else 1
    for vieja in anteriores:
        if vieja.estatus != m.EstatusCotizacion.SUSTITUIDA:
            vieja.estatus = m.EstatusCotizacion.SUSTITUIDA

    cotizacion = _armar(db, servicio, tarifario, lineas, viaticos_incluidos,
                        creada_por_id, motivo, version)
    db.commit()
    db.refresh(cotizacion)
    return cotizacion


def _versiones(db: Session, servicio_id: int) -> list[m.Cotizacion]:
    return (de_cotizacion(db.query(m.Cotizacion))
            .filter_by(servicio_id=servicio_id)
            .order_by(m.Cotizacion.version.desc()).all())


def _armar(db: Session, servicio: m.Servicio, tarifario: m.Tarifario,
           lineas: list[dict], viaticos_incluidos: bool,
           creada_por_id: int | None, motivo: str | None,
           version: int) -> m.Cotizacion:
    """La cotizacion con sus renglones y su total, sin guardar nada: ni
    confirma ni toca las versiones de antes. La usan `generar`, la vista
    previa --que la deshace-- y la que se registra ya autorizada."""
    servicio_id = servicio.id
    cotizacion = m.Cotizacion(
        servicio_id=servicio_id, version=version, tarifario_id=tarifario.id,
        moneda=tarifario.moneda, viaticos_incluidos=viaticos_incluidos,
        creada_por_id=creada_por_id, motivo_recotizacion=motivo)
    # La recotizacion de una que nacio en Cotizaciones (seccion 114)
    # sigue con su folio: es la version siguiente de la misma.
    anterior = (de_cotizacion(db.query(m.Cotizacion))
                .filter(m.Cotizacion.servicio_id == servicio_id,
                        m.Cotizacion.folio.isnot(None))
                .order_by(m.Cotizacion.version.desc()).first())
    if anterior is not None and version > 0:
        cotizacion.folio = anterior.folio
        cotizacion.cliente_id = anterior.cliente_id
        cotizacion.pais_id = anterior.pais_id
        # Y su cabecera (seccion 127, hallazgo r1-01): quien la pidio,
        # el consultor, el idioma, la vigencia y el IVA siguen siendo
        # los de la cotizacion; sin ellos la lista la pintaba con «—» y
        # el total sin IVA.
        for campo in CABECERA_QUE_SIGUE:
            setattr(cotizacion, campo, getattr(anterior, campo))
    db.add(cotizacion)
    db.flush()

    # Modalidad por fecha y equipo, tomada de las jornadas reales del servicio
    modalidad_por_dia = {}
    for equipo in servicio.equipos:
        for j in equipo.jornadas:
            modalidad_por_dia[(equipo.alias, j.fecha)] = j.modalidad_id

    total = Decimal("0")
    for renglon in renglones_con_precio(
            db, tarifario.id, modalidad_por_dia, lineas,
            con_paquetes=usa_paquetes(
                tarifario, modo_de_las_lineas(viaticos_incluidos, lineas))):
        db.add(m.LineaCotizacion(cotizacion_id=cotizacion.id, **renglon))
        total += renglon["subtotal"]
    cotizacion.total = total
    if cotizacion.folio is not None:
        _dias_del_servicio(db, cotizacion, servicio, lineas)
    db.flush()
    return cotizacion


# Lo que la version que nace al recotizar en el servicio hereda de la
# que nacio en Cotizaciones (seccion 127): la cabecera que la pantalla
# de Cotizaciones y «Volver a crear el servicio» leen de la ultima
# version. El folio, el cliente y el pais ya se copiaban desde la 114.
CABECERA_QUE_SIGUE = (
    "prospecto", "solicitante_id", "solicitante_nombre",
    "solicitante_apellidos", "solicitante_correo", "solicitante_telefono",
    "consultor_id", "tipo_servicio", "introduccion", "idioma",
    "valida_hasta", "con_iva", "tasa_iva", "servicio_folio")


def _dias_del_servicio(db: Session, cotizacion: m.Cotizacion,
                       servicio: m.Servicio, lineas: list[dict]) -> None:
    """Los dias de la cotizacion que sigue con folio, tomados de los dias
    reales del servicio (seccion 127): la ciudad del equipo, la fecha, la
    modalidad, la hora si ya esta confirmada, si es foraneo, y lo que
    lleva ese dia segun los renglones. Con ellos la version que nace al
    recotizar se puede volver a crear como servicio si este se elimina, y
    el detalle dice sus fechas, como la V1."""
    import json

    lleva = {}
    for linea in lineas:
        tipo = m.TipoLinea(linea["tipo"])
        if tipo not in (m.TipoLinea.RECURSO, m.TipoLinea.VEHICULO):
            continue
        clave = (linea.get("equipo_clave") or "Alfa", linea["fecha"])
        ident = (linea.get("perfil_id") if tipo == m.TipoLinea.RECURSO
                 else linea.get("categoria_id"))
        if not ident:
            continue
        que = ("recurso" if tipo == m.TipoLinea.RECURSO else "vehiculo", ident)
        por_dia = lleva.setdefault(clave, {})
        por_dia[que] = por_dia.get(que, 0) + int(linea.get("cantidad", 1) or 0)
    for equipo, jornada in _dias(servicio):
        suyo = lleva.get((equipo.alias, jornada.fecha), {})
        db.add(m.DiaCotizacion(
            cotizacion_id=cotizacion.id, equipo_clave=equipo.alias,
            fecha=jornada.fecha, modalidad_id=jornada.modalidad_id,
            plaza_id=equipo.ciudad_id,
            hora=(jornada.inicio_programado.time()
                  if jornada.hora_confirmada and jornada.inicio_programado
                  else None),
            es_foraneo=bool(jornada.es_foraneo),
            lleva=json.dumps([{"tipo": t, "id": i, "cantidad": n}
                              for (t, i), n in sorted(
                                  suyo.items(),
                                  key=lambda x: (x[0][0] != "recurso", x[0][1]))])))


def _producto(db: Session, tarifa, cache: dict) -> str | None:
    """El nombre del producto de Odoo del que salio el precio."""
    producto_id = getattr(tarifa, "producto_odoo_id", None)
    if not producto_id:
        return None
    if producto_id not in cache:
        producto = db.get(m.ProductoOdoo, producto_id)
        cache[producto_id] = producto.nombre if producto else None
    return cache[producto_id]


def renglones_con_precio(db: Session, tarifario_id: int,
                         modalidad_por_dia: dict,
                         lineas: list[dict],
                         con_paquetes: bool = True) -> list[dict]:
    """Los renglones con el precio de la lista, sin guardar nada.

    Cada linea: {fecha, equipo_clave, tipo, perfil_id | categoria_id,
    cantidad} --el paquete trae los dos--; los gastos de monto fijo traen
    su `precio_unitario`. La modalidad de cada dia sale de
    `modalidad_por_dia` {(equipo, fecha): modalidad_id}: la de las
    jornadas del servicio o, en Cotizaciones (seccion 114), la de los
    dias que capturo el consultor.

    El rol y la unidad del mismo dia y el mismo equipo que la lista del
    cliente tiene en paquete se cotizan como paquete (seccion 79): asi se
    cobran al cerrar, y lo cotizado y lo ejecutado se comparan igual.
    Sin `con_paquetes` --gastos aparte con una lista cuyos paquetes traen
    los gastos (`usa_paquetes`)--, cada uno va a su precio unitario.
    """
    # Primero, que se va en paquete cada dia de cada equipo.
    grupos = {}
    for linea in lineas:
        clave = linea.get("equipo_clave") or "Alfa"
        fecha = linea["fecha"]
        modalidad_id = modalidad_por_dia.get((clave, fecha))
        if not modalidad_id:
            raise HTTPException(400, f"No hay jornada del equipo {clave} el {fecha}")
        grupo = grupos.setdefault((clave, fecha), {
            "modalidad_id": modalidad_id, "roles": {}, "unidades": {}})
        tipo = m.TipoLinea(linea["tipo"])
        cantidad = int(linea.get("cantidad", 1))
        if tipo == m.TipoLinea.RECURSO and linea.get("perfil_id"):
            grupo["roles"][linea["perfil_id"]] = (
                grupo["roles"].get(linea["perfil_id"], 0) + cantidad)
        elif tipo == m.TipoLinea.VEHICULO and linea.get("categoria_id"):
            grupo["unidades"][linea["categoria_id"]] = (
                grupo["unidades"].get(linea["categoria_id"], 0) + cantidad)
    for grupo in grupos.values():
        disponibles_r, disponibles_u = dict(grupo["roles"]), dict(grupo["unidades"])
        grupo["paquetes"] = emparejar(
            disponibles_r, disponibles_u,
            paquetes_del_tarifario(db, tarifario_id, grupo["modalidad_id"])
            if con_paquetes else [])
        # Cuanto de cada rol y de cada unidad ya va dentro de un paquete.
        grupo["en_paquete_r"] = {k: grupo["roles"][k] - v
                                 for k, v in disponibles_r.items()}
        grupo["en_paquete_u"] = {k: grupo["unidades"][k] - v
                                 for k, v in disponibles_u.items()}
        grupo["escritos"] = False

    salida = []
    productos = {}

    def renglon(fecha, clave, modalidad_id, tipo, perfil_id, categoria_id,
                cantidad, unitario, descripcion, tarifa=None):
        salida.append({
            "fecha": fecha, "equipo_clave": clave, "modalidad_id": modalidad_id,
            "tipo": tipo, "perfil_id": perfil_id, "categoria_id": categoria_id,
            "cantidad": cantidad, "precio_unitario": unitario,
            "subtotal": unitario * cantidad, "descripcion": descripcion,
            "producto": _producto(db, tarifa, productos) if tarifa else None})

    for linea in lineas:
        clave = linea.get("equipo_clave") or "Alfa"
        fecha = linea["fecha"]
        grupo = grupos[(clave, fecha)]
        modalidad_id = grupo["modalidad_id"]
        cantidad = int(linea.get("cantidad", 1))
        tipo = m.TipoLinea(linea["tipo"])

        # Los paquetes del dia van antes que sus renglones sueltos.
        if not grupo["escritos"]:
            grupo["escritos"] = True
            for paquete, cuantos in grupo["paquetes"]:
                renglon(fecha, clave, modalidad_id, m.TipoLinea.PAQUETE,
                        paquete.perfil_id, paquete.categoria_id, cuantos,
                        Decimal(str(paquete.precio)),
                        nombre_del_paquete(paquete), paquete)

        # Lo que ya se fue en un paquete no se cobra suelto.
        usado = 0
        if tipo == m.TipoLinea.RECURSO and linea.get("perfil_id"):
            usado = min(cantidad, grupo["en_paquete_r"].get(linea["perfil_id"], 0))
            grupo["en_paquete_r"][linea["perfil_id"]] = (
                grupo["en_paquete_r"].get(linea["perfil_id"], 0) - usado)
        elif tipo == m.TipoLinea.VEHICULO and linea.get("categoria_id"):
            usado = min(cantidad, grupo["en_paquete_u"].get(linea["categoria_id"], 0))
            grupo["en_paquete_u"][linea["categoria_id"]] = (
                grupo["en_paquete_u"].get(linea["categoria_id"], 0) - usado)
        cantidad -= usado
        if usado and cantidad <= 0:
            continue

        if tipo == m.TipoLinea.PAQUETE:
            if not con_paquetes:
                raise HTTPException(400, {
                    "mensaje": "Con los gastos aparte no va el paquete de la "
                               "lista: trae los gastos dentro",
                    "que_hacer": "Cotiza el rol y la unidad por separado; "
                                 "los gastos van en su modo.",
                    "clave": "paquete_con_gastos"})
            tarifa = precio_paquete(db, tarifario_id, linea.get("perfil_id"),
                                    linea.get("categoria_id"), modalidad_id)
            renglon(fecha, clave, modalidad_id, tipo, tarifa.perfil_id,
                    tarifa.categoria_id, cantidad, Decimal(str(tarifa.precio)),
                    nombre_del_paquete(tarifa), tarifa)
            continue

        tarifa = None
        if tipo == m.TipoLinea.RECURSO:
            tarifa = precio_recurso(db, tarifario_id, linea["perfil_id"], modalidad_id)
            unitario = Decimal(str(tarifa.precio))
            perfil_id, categoria_id = linea["perfil_id"], None
            descripcion = db.get(m.PerfilPersonal, perfil_id).nombre
        elif tipo == m.TipoLinea.VEHICULO:
            tarifa = precio_vehiculo(db, tarifario_id, linea["categoria_id"], modalidad_id)
            unitario = Decimal(str(tarifa.precio))
            perfil_id, categoria_id = None, linea["categoria_id"]
            descripcion = db.get(m.CategoriaVehiculo, categoria_id).nombre
        else:
            unitario = Decimal(str(linea["precio_unitario"]))
            perfil_id = categoria_id = None
            descripcion = linea.get("descripcion", "Viaticos")

        renglon(fecha, clave, modalidad_id, tipo, perfil_id, categoria_id,
                cantidad, unitario, descripcion, tarifa)
    return salida


def autorizar(db: Session, cotizacion_id: int, autorizada_por: str) -> m.Cotizacion:
    cotizacion = db.get(m.Cotizacion, cotizacion_id)
    # La propuesta del implantado se autoriza en su pantalla (seccion 115).
    if not cotizacion or cotizacion.clase != COTIZACION:
        raise HTTPException(404, f"No existe la cotizacion {cotizacion_id}")
    if cotizacion.estatus == m.EstatusCotizacion.SUSTITUIDA:
        raise HTTPException(409, "Esa cotizacion fue sustituida por una version posterior")
    # La que nacio en Cotizaciones y todavia no tiene servicio se
    # autoriza alla (seccion 114); aqui no hay servicio del que tomar el
    # pais (seccion 127, hallazgo r1-06).
    if cotizacion.servicio_id is None:
        raise HTTPException(409, "Esa cotización se autoriza en Cotizaciones.")
    _autorizar(db, cotizacion, autorizada_por)
    db.commit()
    db.refresh(cotizacion)
    return cotizacion


def _autorizar(db: Session, cotizacion: m.Cotizacion, autorizada_por: str,
               autorizada_el=None, folio_odoo: str | None = None) -> None:
    """La marca de autorizada, sin confirmar: el tipo de cambio que queda
    fijo, quien, cuando y el estatus del servicio."""
    from datetime import datetime

    # En otra moneda que la del pais --Amazon, en dolares--, la cotizacion
    # se queda con el tipo de cambio que esta puesto al autorizarla, y ya
    # no se mueve: con el se calculan la utilidad y la comision (seccion
    # 82). Sin tipo de cambio no se autoriza: restarian dolares menos pesos.
    local = tipo_cambio.local_del_pais(db, cotizacion.servicio.pais_id)
    if local and cotizacion.moneda != local:
        tc = (tipo_cambio.vigente(db, cotizacion.moneda, local)
              if tipo_cambio.se_puede(cotizacion.moneda, local) else None)
        if tc is None:
            raise HTTPException(409, sin_tipo_de_cambio(db, cotizacion.moneda,
                                                        local))
        cotizacion.tipo_cambio = tc["tasa"]
        cotizacion.tipo_cambio_fecha = tc["fecha"]

    cotizacion.estatus = m.EstatusCotizacion.AUTORIZADA
    cotizacion.autorizada_en = datetime.now()
    cotizacion.autorizada_por = autorizada_por
    cotizacion.autorizada_el = autorizada_el
    cotizacion.folio_odoo = folio_odoo

    # El estatus del servicio no camina hacia atras.
    #
    # Esto lo ponia en `autorizado` mirara donde mirara. Autorizar una
    # cotizacion tarde --con el servicio ya terminado, que es
    # exactamente lo que pasa cuando la propuesta se captura despues--
    # lo regresaba al principio del ciclo: un servicio trabajado y
    # cerrado volvia a verse como uno que todavia no sale.
    if cotizacion.servicio.estatus in (m.EstatusServicio.BORRADOR,
                                       m.EstatusServicio.SOLICITADO,
                                       m.EstatusServicio.COTIZADO):
        cotizacion.servicio.estatus = m.EstatusServicio.AUTORIZADO


def sin_tipo_de_cambio(db: Session, moneda, local) -> dict:
    """Por que no hay tipo de cambio, y que hacer: lo mismo lo dice la
    cotizacion, el cierre y el mes del implantado. `motivo` va en clave
    para que la pantalla lo diga en su idioma; `mensaje` y `que_hacer`,
    para quien lee la API."""
    moneda, local = m.Moneda(moneda), m.Moneda(local)
    datos = {"moneda": moneda.value, "local": local.value}
    if not tipo_cambio.se_puede(moneda, local):
        return {**datos, "motivo": "no_se_convierte",
                "mensaje": (f"Es en {moneda.value} y se cobra en un pais de "
                            f"{local.value}: Centauro no convierte entre esas "
                            "dos monedas"),
                "que_hacer": ("Se convierte de dolares a pesos mexicanos y "
                              "de dolares a reales.")}
    return {**datos, "motivo": "sin_tipo_de_cambio",
            "mensaje": (f"No hay tipo de cambio de {moneda.value} a "
                        f"{local.value}"),
            "que_hacer": ("Finanzas lo pone en Tarifarios: el que se pone "
                          "aplica para todo hasta que se cambie.")}


def tipo_de_cambio(db: Session, cotizacion: m.Cotizacion) -> dict | None:
    """El de la cotizacion: el que se quedo al autorizarla. Una autorizada
    antes de la seccion 82 no lo trae: se toma el que este puesto. None si
    es de la moneda del pais o si no hay."""
    local = tipo_cambio.local_del_pais(db, cotizacion.servicio.pais_id)
    if not local or cotizacion.moneda == local:
        return None
    if cotizacion.tipo_cambio:
        return tipo_cambio.fijo(cotizacion.tipo_cambio,
                                cotizacion.tipo_cambio_fecha)
    if not tipo_cambio.se_puede(cotizacion.moneda, local):
        return None
    return tipo_cambio.vigente(db, cotizacion.moneda, local)


def vigente(db: Session, servicio_id: int) -> m.Cotizacion | None:
    """La cotizacion autorizada mas reciente. La propuesta del implantado
    no cuenta (seccion 115): el mes se cobra con su contrato."""
    return (de_cotizacion(db.query(m.Cotizacion))
            .filter_by(servicio_id=servicio_id,
                       estatus=m.EstatusCotizacion.AUTORIZADA)
            .order_by(m.Cotizacion.version.desc())
            .first())


def al_eliminar_equipo(db: Session, servicio: m.Servicio, eliminado: str,
                       renombres: dict[str, str]) -> int:
    """Los renglones de las cotizaciones del servicio siguen a sus
    equipos cuando se elimina uno (seccion 101). Devuelve cuantos
    renglones se tocaron.

    Los renglones van por alias (`equipo_clave`) y eliminar un equipo
    recorre los alias --si se va Beta, Gamma pasa a ser Beta--: la
    cotizacion se quedaba con los renglones de "Beta" apuntando al que
    era Gamma, los de "Gamma" huerfanos como dias de menos en el
    comparativo, y el total sumando un equipo que ya no existe. Aqui se
    quitan los del eliminado, se renombran los demas en el mismo paso y
    el total vuelve a ser la suma de lo que queda. El monto fijo de
    gastos no es de ningun equipo: si iba en el eliminado, pasa al
    primer dia del primer equipo que queda, que es donde lo pone
    `con_gastos`.
    """
    tocados = 0
    cotizaciones = (de_cotizacion(db.query(m.Cotizacion))
                    .filter_by(servicio_id=servicio.id).all())
    if not cotizaciones:
        return 0
    primer_dia = next(iter(_dias(servicio)), None)
    for cotizacion in cotizaciones:
        for linea in list(cotizacion.lineas):
            if linea.equipo_clave == eliminado:
                if linea.tipo == m.TipoLinea.VIATICOS and primer_dia:
                    # Los equipos que quedan ya traen su alias nuevo.
                    equipo, jornada = primer_dia
                    linea.equipo_clave = equipo.alias
                    linea.fecha = jornada.fecha
                    linea.modalidad_id = jornada.modalidad_id
                else:
                    cotizacion.lineas.remove(linea)
                tocados += 1
            elif linea.equipo_clave in renombres:
                linea.equipo_clave = renombres[linea.equipo_clave]
                tocados += 1
        cotizacion.total = sum((Decimal(str(l.subtotal))
                                for l in cotizacion.lineas), Decimal("0"))
        # Los dias de la que nacio en Cotizaciones (seccion 114) siguen
        # a sus equipos igual (seccion 127, hallazgo r1-04): si no, la
        # tabla de equipos y dias seguia diciendo tres equipos con los
        # renglones de dos, y «Volver a crear el servicio» nacia con el
        # equipo que se quito. Primero se van los del eliminado y
        # despues se renombran, para no chocar con el candado de
        # (cotizacion, equipo, fecha).
        if cotizacion.dias:
            for dia in list(cotizacion.dias):
                if dia.equipo_clave == eliminado:
                    cotizacion.dias.remove(dia)
                    tocados += 1
            db.flush()
            for dia in cotizacion.dias:
                if dia.equipo_clave in renombres:
                    dia.equipo_clave = renombres[dia.equipo_clave]
                    tocados += 1
    db.flush()
    return tocados


# ---------------------------------------------------------------- en el servicio
#
# Seccion 94, pieza 1 de «Para poder operar» (decisiones de Salvador, 28
# de septiembre): mientras Odoo no manda la cotizacion, el consultor --o
# quien lo cubre-- la registra en el servicio con los precios del
# tarifario del cliente. Solo dice que se cotizo, como se cobran los
# gastos y quien la autorizo del lado del cliente, que dia y, si se hizo
# en Odoo, con que folio. Se guarda ya autorizada: una recotizacion no
# deja nunca al servicio sin cotizacion vigente --la nueva nace
# autorizada, con su motivo, y la de antes queda sustituida--, y si algo
# falla no se guarda nada y la de antes sigue valiendo.

GASTOS_DENTRO = "dentro"        # van dentro del precio
GASTOS_FIJOS = "fijo"           # un monto fijo, se gaste mas o menos
GASTOS_COMPROBAR = "comprobar"  # se factura lo comprobado, con desglose
MODOS_DE_GASTOS = (GASTOS_DENTRO, GASTOS_FIJOS, GASTOS_COMPROBAR)

# Despues del visto bueno un cambio lo regresa finanzas, y ahi se recotiza.
YA_CON_VISTO_BUENO = (m.EstatusServicio.EN_FACTURACION,
                      m.EstatusServicio.CERRADO)
LARGO_QUIEN = 160
LARGO_FOLIO = 40
LARGO_MOTIVO = 400


def cancelado_con_visto_bueno(db: Session, servicio: m.Servicio) -> bool:
    """Si el cierre de un servicio cancelado ya tiene visto bueno: desde
    ahi la cotizacion ya no se toca, como en un servicio que termino. El
    estatus del cancelado no cambia con el visto bueno --se queda
    cancelado--, asi que se mira su cierre."""
    from app import cierre as motor_cierre
    from app import horas_extra

    cierre = motor_cierre.del_eventual(db, servicio.id)
    return bool(cierre and (cierre.facturado_en
                            or cierre.estatus in horas_extra.CON_VISTO_BUENO))


def _servicio_que_se_cotiza(db: Session, servicio_id: int) -> m.Servicio:
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    if servicio.tipo != m.TipoServicio.EVENTUAL:
        raise HTTPException(400, "El implantado no lleva esta cotizacion: sus "
                                 "precios van en el contrato del mes.")
    # El cancelado se cotiza mientras su cierre no tenga visto bueno
    # (seccion 105, hallazgo 6): se cancela con dias trabajados o dinero
    # afuera, y sin cotizacion su cierre no tenia salida.
    if (servicio.estatus == m.EstatusServicio.CANCELADO
            and cancelado_con_visto_bueno(db, servicio)):
        raise HTTPException(409, "El servicio esta cancelado y su cierre ya "
                                 "tiene visto bueno: si algo cambio, finanzas "
                                 "lo regresa y ahi se recotiza.")
    if servicio.estatus in YA_CON_VISTO_BUENO:
        raise HTTPException(409, "Ya tiene visto bueno: si el cliente cambio "
                                 "algo, finanzas lo regresa y ahi se recotiza.")
    return servicio


def _dias(servicio: m.Servicio) -> list:
    """(equipo, jornada) de los dias que se cotizan: los que no estan
    cancelados, en el orden de cada equipo.

    En un servicio cancelado entran tambien los cancelados (seccion
    105): la cotizacion autorizada es la del plan que el cliente
    autorizo, y con el cobro completo se factura tal cual, con los dias
    que ya no se trabajaron.
    """
    cancelado = servicio.estatus == m.EstatusServicio.CANCELADO
    return [(e, j) for e in servicio.equipos
            for j in sorted(e.jornadas, key=lambda x: x.fecha)
            if cancelado or j.estatus != m.EstatusJornada.CANCELADA]


def _renglones_de_lo_que_lleva(servicio: m.Servicio, lineas: list[dict]) -> list[dict]:
    """Lo que manda la pantalla: roles y unidades por dia. Los gastos van
    aparte (su modo) y el paquete lo arma la lista del cliente."""
    dias = {(e.alias, j.fecha) for e, j in _dias(servicio)}
    limpias = []
    for linea in lineas:
        tipo = m.TipoLinea(linea["tipo"])
        if tipo not in (m.TipoLinea.RECURSO, m.TipoLinea.VEHICULO):
            raise HTTPException(400, "Aqui solo se cotizan roles y unidades: "
                                     "los gastos van en su modo.")
        cantidad = int(linea.get("cantidad", 1) or 0)
        if cantidad <= 0:
            continue
        clave = linea.get("equipo_clave") or "Alfa"
        if (clave, linea["fecha"]) not in dias:
            raise HTTPException(400, f"El equipo {clave} no tiene dia el "
                                     f"{linea['fecha']}")
        limpias.append({**linea, "equipo_clave": clave, "cantidad": cantidad})
    if not limpias:
        raise HTTPException(400, "La cotizacion no lleva nada: di con que rol y "
                                 "que unidad va cada dia.")
    return limpias


def con_gastos(servicio: m.Servicio, lineas: list[dict], modo: str,
               monto=None) -> tuple[list[dict], bool]:
    """(renglones, viaticos_incluidos) segun como se cobran los gastos. El
    monto fijo es un renglon de gastos el primer dia del primer equipo:
    asi lo lee el cierre (seccion 59)."""
    if modo not in MODOS_DE_GASTOS:
        raise HTTPException(400, "Di como se cobran los gastos.")
    if modo == GASTOS_COMPROBAR:
        return lineas, False
    if modo == GASTOS_DENTRO:
        return lineas, True
    try:
        importe = Decimal(str(monto or 0)).quantize(Decimal("0.01"))
    except Exception:                                   # noqa: BLE001
        raise HTTPException(400, "El monto fijo de gastos no es un numero.")
    if importe <= 0:
        raise HTTPException(400, "El monto fijo de gastos tiene que ser mayor "
                                 "que cero.")
    equipo, jornada = _dias(servicio)[0]
    return lineas + [{"fecha": jornada.fecha, "equipo_clave": equipo.alias,
                      "tipo": m.TipoLinea.VIATICOS.value, "cantidad": 1,
                      "precio_unitario": importe, "descripcion": "Gastos"}], True


def modo_de_gastos(cotizacion: m.Cotizacion) -> str:
    """Con un renglon de gastos, monto fijo aunque el monto siga en cero
    (seccion 129, hallazgo r1-05): el borrador de Cotizaciones lo guarda
    asi mientras el consultor no lo escribe, y mandarla lo reclama."""
    if not cotizacion.viaticos_incluidos:
        return GASTOS_COMPROBAR
    con_gastos = any(l.tipo == m.TipoLinea.VIATICOS for l in cotizacion.lineas)
    return GASTOS_FIJOS if con_gastos else GASTOS_DENTRO


def resumen(db: Session, cotizacion: m.Cotizacion) -> dict:
    """Lo que la pantalla dice de una cotizacion, con sus renglones."""
    lineas = sorted(cotizacion.lineas,
                    key=lambda l: (l.fecha, l.equipo_clave,
                                   ORDEN_DE_TIPO.get(l.tipo, 9), l.id))
    fijos = sum((Decimal(str(l.subtotal)) for l in lineas
                 if l.tipo == m.TipoLinea.VIATICOS), Decimal("0"))
    trabajo = [l for l in lineas if l.tipo != m.TipoLinea.VIATICOS]
    tc = None
    if cotizacion.estatus == m.EstatusCotizacion.AUTORIZADA:
        tc = tipo_de_cambio(db, cotizacion)
    return {
        "id": cotizacion.id, "version": cotizacion.version,
        "estatus": cotizacion.estatus.value,
        "total": cotizacion.total, "moneda": cotizacion.moneda.value,
        "gastos": modo_de_gastos(cotizacion), "gastos_fijos": fijos,
        "autorizada_por": cotizacion.autorizada_por,
        "autorizada_el": (cotizacion.autorizada_el.isoformat()
                          if cotizacion.autorizada_el else None),
        "autorizada_en": (cotizacion.autorizada_en.isoformat()
                          if cotizacion.autorizada_en else None),
        "folio_odoo": cotizacion.folio_odoo,
        # La que nacio en Cotizaciones (seccion 114): su folio y si
        # guarda el PDF que se le mando al cliente.
        "folio": folio_texto(cotizacion.folio),
        "tiene_pdf": any(a.clase == "pdf" for a in cotizacion.archivos),
        "motivo": cotizacion.motivo_recotizacion,
        "registrada_por": (cotizacion.creada_por.nombre
                           if cotizacion.creada_por else None),
        "registrada_en": (cotizacion.creada_en.isoformat()
                          if cotizacion.creada_en else None),
        # El dia en el pais del servicio: registrada de noche en Mexico
        # es otro dia en el reloj del servidor.
        "registrada_el": _dia_en_el_pais(db, cotizacion),
        "tipo_cambio": ({"tasa": tc.get("tasa"),
                         "corta": tipo_cambio.corto(tc.get("tasa")), "fecha": (
                            tc["fecha"].isoformat() if hasattr(tc.get("fecha"), "isoformat")
                            else tc.get("fecha"))} if tc else None),
        "dias": len({(l.equipo_clave, l.fecha) for l in trabajo}),
        "equipos": len({l.equipo_clave for l in trabajo}),
        "lineas": [{
            "fecha": l.fecha.isoformat(), "equipo": l.equipo_clave,
            "modalidad": (l.modalidad.codigo.value if l.modalidad else None),
            "tipo": l.tipo.value, "perfil_id": l.perfil_id,
            "categoria_id": l.categoria_id, "descripcion": l.descripcion,
            "cantidad": l.cantidad, "precio": l.precio_unitario,
            "importe": l.subtotal} for l in lineas],
    }


def _dia_en_el_pais(db: Session, cotizacion: m.Cotizacion) -> str | None:
    from app import reloj
    if not cotizacion.creada_en:
        return None
    pais = (db.get(m.Pais, cotizacion.servicio.pais_id)
            if cotizacion.servicio else None)
    return reloj.ahora_en(pais, cotizacion.creada_en).date().isoformat()


# El paquete va antes que sus sueltos, como en el cierre.
ORDEN_DE_TIPO = {m.TipoLinea.PAQUETE: 0, m.TipoLinea.RECURSO: 1,
                 m.TipoLinea.VEHICULO: 2, m.TipoLinea.VIATICOS: 3}


def vista_previa(db: Session, servicio_id: int, lineas: list[dict],
                 gastos: str, monto=None) -> dict:
    """Los precios de lo que se va a cotizar, sin guardar nada: se arma
    igual que al guardarla --con los paquetes que la lista pacta-- y se
    deshace."""
    servicio = _servicio_que_se_cotiza(db, servicio_id)
    tarifario = _tarifario_de(db, servicio)
    renglones, incluidos = con_gastos(
        servicio, _renglones_de_lo_que_lleva(servicio, lineas), gastos, monto)
    punto = db.begin_nested()
    try:
        cotizacion = _armar(db, servicio, tarifario, renglones, incluidos,
                            None, None, 0)
        db.refresh(cotizacion)
        salida = resumen(db, cotizacion)
    finally:
        punto.rollback()
    return salida


def registrar_autorizada(db: Session, servicio_id: int, lineas: list[dict],
                         gastos: str, monto, autorizada_por: str,
                         autorizada_el, folio_odoo: str | None,
                         motivo: str | None,
                         creada_por_id: int | None) -> m.Cotizacion:
    """La cotizacion nueva, ya autorizada por el cliente, en un solo paso.

    No confirma: quien la llama anota en la bitacora y confirma. Si algo
    falla --un precio que la lista no tiene, el tipo de cambio que falta--
    no queda nada y la version de antes sigue vigente."""
    servicio = _servicio_que_se_cotiza(db, servicio_id)
    tarifario = _tarifario_de(db, servicio)

    quien = " ".join((autorizada_por or "").split())
    if not quien:
        raise HTTPException(400, "Di quien la autorizo del lado del cliente.")
    if len(quien) > LARGO_QUIEN:
        raise HTTPException(400, "El nombre de quien la autorizo es demasiado "
                                 "largo.")
    if autorizada_el is None:
        raise HTTPException(400, "Falta el dia en que el cliente la autorizo.")
    from app import reloj
    if autorizada_el > reloj.Relojes(db).hoy(servicio.pais_id):
        raise HTTPException(400, "El dia en que el cliente la autorizo no puede "
                                 "ser despues de hoy.")
    folio = " ".join((folio_odoo or "").split()) or None
    if folio and len(folio) > LARGO_FOLIO:
        raise HTTPException(400, "El folio de Odoo es demasiado largo.")
    motivo = " ".join((motivo or "").split()) or None
    if motivo and len(motivo) > LARGO_MOTIVO:
        raise HTTPException(400, "El motivo es demasiado largo.")
    if vigente(db, servicio_id) is not None and not motivo:
        raise HTTPException(400, "Di por que se recotiza: queda escrito en la "
                                 "version nueva.")

    renglones, incluidos = con_gastos(
        servicio, _renglones_de_lo_que_lleva(servicio, lineas), gastos, monto)
    anteriores = _versiones(db, servicio_id)
    version = (anteriores[0].version + 1) if anteriores else 1

    punto = db.begin_nested()
    try:
        cotizacion = _armar(db, servicio, tarifario, renglones, incluidos,
                            creada_por_id, motivo, version)
        _autorizar(db, cotizacion, quien, autorizada_el, folio)
        for vieja in anteriores:
            if vieja.estatus != m.EstatusCotizacion.SUSTITUIDA:
                vieja.estatus = m.EstatusCotizacion.SUSTITUIDA
        punto.commit()
    except Exception:
        punto.rollback()
        raise
    db.refresh(cotizacion)
    return cotizacion


def lo_asignado(servicio: m.Servicio) -> dict:
    """{equipo: {fecha: {"roles": {rol: n}, "unidades": {categoria: n}}}}:
    con quien va cada dia hoy, para «Tomar lo asignado». La asignacion
    relevada no cuenta: el cliente tuvo un conductor, no dos."""
    salida = {}
    for equipo, jornada in _dias(servicio):
        roles, unidades = {}, {}
        for a in jornada.personal:
            if not a.relevado_en and a.rol_id:
                roles[a.rol_id] = roles.get(a.rol_id, 0) + 1
        for a in jornada.vehiculos:
            if not a.relevado_en and a.vehiculo and a.vehiculo.categoria_id:
                cat = a.vehiculo.categoria_id
                unidades[cat] = unidades.get(cat, 0) + 1
        salida.setdefault(equipo.alias, {})[jornada.fecha.isoformat()] = {
            "roles": roles, "unidades": unidades}
    return salida


def lo_que_tiene_precio(db: Session, tarifario_id: int) -> tuple[list, list]:
    """(roles, unidades) que la lista del cliente cobra: sueltos o dentro de
    un paquete que pacta. Lo demas no se puede cotizar. Lo que la lista
    cobra al mes --con la modalidad del implantado (seccion 123)-- no se
    cotiza por dia."""
    del_mes = {mo.id for mo in db.query(m.Modalidad)
               .filter_by(codigo=m.CodigoModalidad.IMPLANTADO).all()}
    roles = {r.perfil_id for r in db.query(m.TarifaRecurso)
             .filter_by(tarifario_id=tarifario_id).all()
             if r.modalidad_id not in del_mes}
    unidades = {v.categoria_id for v in db.query(m.TarifaVehiculo)
                .filter_by(tarifario_id=tarifario_id).all()
                if v.modalidad_id not in del_mes}
    for p in _pactados(db).filter_by(tarifario_id=tarifario_id).all():
        if p.modalidad_id in del_mes:
            continue
        roles.add(p.perfil_id)
        unidades.add(p.categoria_id)
    perfiles = (db.query(m.PerfilPersonal)
                .filter(m.PerfilPersonal.id.in_(roles or {0})).all())
    categorias = (db.query(m.CategoriaVehiculo)
                  .filter(m.CategoriaVehiculo.id.in_(unidades or {0})).all())
    return ([{"id": p.id, "nombre": p.nombre} for p in
             sorted(perfiles, key=lambda x: x.nombre)],
            [{"id": c.id, "nombre": c.nombre} for c in
             sorted(categorias, key=lambda x: x.nombre)])


def bloque(db: Session, servicio_id: int) -> dict:
    """Todo lo que el bloque del servicio necesita para decir como esta la
    cotizacion y para armar una: la vigente, los dias con su modalidad,
    lo asignado, lo que la lista cobra y quien pudo autorizarla."""
    from app import reloj

    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    cliente = db.get(m.Cliente, servicio.cliente_id)
    tarifario = (_tarifario_de(db, servicio)
                 if cliente and cliente.tarifario_id else None)
    vig = vigente(db, servicio_id)
    versiones = _versiones(db, servicio_id)
    roles, unidades = (lo_que_tiene_precio(db, tarifario.id)
                       if tarifario else ([], []))

    # Quien pudo autorizarla: quien solicita primero, y los demas de la
    # lista del cliente. Otra persona se escribe a mano.
    quienes = []
    if servicio.solicitante_completo:
        quienes.append({"nombre": servicio.solicitante_completo,
                        "solicita": True})
    for s in (db.query(m.Solicitante)
              .filter_by(cliente_id=servicio.cliente_id, activo=True)
              .order_by(m.Solicitante.nombre).all()):
        nombre = s.completo
        if nombre and all(q["nombre"] != nombre for q in quienes):
            quienes.append({"nombre": nombre, "solicita": False})

    # El cancelado se cotiza mientras su cierre no tenga visto bueno
    # (seccion 105); despues, como el terminado, ya no.
    con_visto_bueno = (servicio.estatus in YA_CON_VISTO_BUENO
                       or (servicio.estatus == m.EstatusServicio.CANCELADO
                           and cancelado_con_visto_bueno(db, servicio)))
    return {
        "servicio_id": servicio.id,
        "se_cotiza": servicio.tipo == m.TipoServicio.EVENTUAL,
        "se_puede": (servicio.tipo == m.TipoServicio.EVENTUAL
                     and not con_visto_bueno),
        "con_visto_bueno": con_visto_bueno,
        "tarifario": ({"id": tarifario.id, "nombre": tarifario.nombre,
                       "moneda": tarifario.moneda.value,
                       # La general de la moneda que autorizo el cliente,
                       # no la de su ficha (seccion 120).
                       "escogida": tarifario.id != cliente.tarifario_id}
                      if tarifario else None),
        "vigente": resumen(db, vig) if vig else None,
        "versiones": [{
            "version": c.version, "estatus": c.estatus.value,
            "total": c.total, "moneda": c.moneda.value,
            "motivo": c.motivo_recotizacion,
            "autorizada_por": c.autorizada_por,
            "autorizada_el": (c.autorizada_el.isoformat()
                              if c.autorizada_el else None)} for c in versiones],
        "siguiente_version": (versiones[0].version + 1) if versiones else 1,
        "dias": [{"equipo": e.alias, "fecha": j.fecha.isoformat(),
                  "modalidad": j.modalidad.codigo.value if j.modalidad else None,
                  "horas": (float(j.modalidad.horas) if j.modalidad else None)}
                 for e, j in _dias(servicio)],
        "asignado": lo_asignado(servicio),
        "roles": roles, "unidades": unidades,
        "quienes": quienes,
        "hoy": reloj.Relojes(db).hoy(servicio.pais_id).isoformat(),
        # La moneda del pais: una cotizacion en otra se autoriza con el
        # tipo de cambio que este puesto (seccion 82).
        "moneda_local": _moneda_local(db, servicio),
    }


def _moneda_local(db: Session, servicio: m.Servicio) -> str | None:
    local = tipo_cambio.local_del_pais(db, servicio.pais_id)
    return local.value if local else None

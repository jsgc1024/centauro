"""Cotizacion del servicio. Es la referencia contra la que se compara el cierre."""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m


def _tarifario_de(db: Session, servicio: m.Servicio) -> m.Tarifario:
    cliente = db.get(m.Cliente, servicio.cliente_id)
    if not cliente or not cliente.tarifario_id:
        raise HTTPException(400, "El cliente no tiene tarifario asignado")
    return db.get(m.Tarifario, cliente.tarifario_id)


def precio_recurso(db: Session, tarifario_id: int, perfil_id: int | None,
                   modalidad_id: int) -> m.TarifaRecurso:
    """El precio del rol. Sin rol no hay precio que buscar."""
    if not perfil_id:
        raise HTTPException(400, "Hay personal asignado sin rol. Diga con "
                                 "que rol va antes de cotizar o cerrar.")
    tarifa = (db.query(m.TarifaRecurso)
              .filter_by(tarifario_id=tarifario_id, perfil_id=perfil_id,
                         modalidad_id=modalidad_id).first())
    if not tarifa:
        perfil = db.get(m.PerfilPersonal, perfil_id)
        modalidad = db.get(m.Modalidad, modalidad_id)
        raise HTTPException(400, f"El tarifario no tiene precio para "
                                 f"{perfil.nombre} en {modalidad.codigo.value}")
    return tarifa


def precio_vehiculo(db: Session, tarifario_id: int, categoria_id: int,
                    modalidad_id: int) -> m.TarifaVehiculo:
    tarifa = (db.query(m.TarifaVehiculo)
              .filter_by(tarifario_id=tarifario_id, categoria_id=categoria_id,
                         modalidad_id=modalidad_id).first())
    if not tarifa:
        categoria = db.get(m.CategoriaVehiculo, categoria_id)
        modalidad = db.get(m.Modalidad, modalidad_id)
        raise HTTPException(400, f"El tarifario no tiene precio para "
                                 f"{categoria.nombre} en {modalidad.codigo.value}")
    return tarifa


def paquetes_del_tarifario(db: Session, tarifario_id: int,
                           modalidad_id: int) -> list[m.TarifaPaquete]:
    """Los paquetes conductor + unidad que el tarifario tiene en esa
    modalidad (seccion 79). En el orden en que se leyeron: si un rol cabe
    en dos paquetes el mismo dia, gana el primero, y asi siempre igual."""
    return (db.query(m.TarifaPaquete)
            .filter_by(tarifario_id=tarifario_id, modalidad_id=modalidad_id)
            .order_by(m.TarifaPaquete.id).all())


def precio_paquete(db: Session, tarifario_id: int, perfil_id: int | None,
                   categoria_id: int | None, modalidad_id: int) -> m.TarifaPaquete:
    if not perfil_id or not categoria_id:
        raise HTTPException(400, "Un paquete lleva el rol y la unidad.")
    tarifa = (db.query(m.TarifaPaquete)
              .filter_by(tarifario_id=tarifario_id, perfil_id=perfil_id,
                         categoria_id=categoria_id, modalidad_id=modalidad_id)
              .first())
    if not tarifa:
        perfil = db.get(m.PerfilPersonal, perfil_id)
        categoria = db.get(m.CategoriaVehiculo, categoria_id)
        modalidad = db.get(m.Modalidad, modalidad_id)
        raise HTTPException(400, f"El tarifario no tiene el paquete "
                                 f"{perfil.nombre} + {categoria.nombre} en "
                                 f"{modalidad.codigo.value}")
    return tarifa


def nombre_del_paquete(tarifa: m.TarifaPaquete) -> str:
    return f"{tarifa.perfil.nombre} + {tarifa.categoria.nombre}"


def emparejar(roles: dict, unidades: dict, paquetes: list) -> list[tuple]:
    """[(paquete, cuantos)] del dia de un equipo. `roles`: {perfil: cuantos}
    y `unidades`: {categoria: cuantas}; lo que se va en paquetes se les
    descuenta, y lo que queda se cobra suelto.

    Asi se cobra lo que el cliente pacto (seccion 79): el dia en que el
    equipo lleva ese rol con esa unidad, y la lista tiene el paquete, un
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
    anteriores = (db.query(m.Cotizacion)
                  .filter_by(servicio_id=servicio_id)
                  .order_by(m.Cotizacion.version.desc()).all())
    version = (anteriores[0].version + 1) if anteriores else 1
    for vieja in anteriores:
        if vieja.estatus != m.EstatusCotizacion.SUSTITUIDA:
            vieja.estatus = m.EstatusCotizacion.SUSTITUIDA

    cotizacion = m.Cotizacion(
        servicio_id=servicio_id, version=version, tarifario_id=tarifario.id,
        moneda=tarifario.moneda, viaticos_incluidos=viaticos_incluidos,
        creada_por_id=creada_por_id, motivo_recotizacion=motivo)
    db.add(cotizacion)
    db.flush()

    # Modalidad por fecha y equipo, tomada de las jornadas reales del servicio
    modalidad_por_dia = {}
    for equipo in servicio.equipos:
        for j in equipo.jornadas:
            modalidad_por_dia[(equipo.alias, j.fecha)] = j.modalidad_id

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
            paquetes_del_tarifario(db, tarifario.id, grupo["modalidad_id"]))
        # Cuanto de cada rol y de cada unidad ya va dentro de un paquete.
        grupo["en_paquete_r"] = {k: grupo["roles"][k] - v
                                 for k, v in disponibles_r.items()}
        grupo["en_paquete_u"] = {k: grupo["unidades"][k] - v
                                 for k, v in disponibles_u.items()}
        grupo["escritos"] = False

    total = Decimal("0")

    def renglon(fecha, clave, modalidad_id, tipo, perfil_id, categoria_id,
                cantidad, unitario, descripcion):
        subtotal = unitario * cantidad
        db.add(m.LineaCotizacion(
            cotizacion_id=cotizacion.id, fecha=fecha, equipo_clave=clave,
            modalidad_id=modalidad_id, tipo=tipo, perfil_id=perfil_id,
            categoria_id=categoria_id, cantidad=cantidad,
            precio_unitario=unitario, subtotal=subtotal, descripcion=descripcion))
        return subtotal

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
                total += renglon(fecha, clave, modalidad_id, m.TipoLinea.PAQUETE,
                                 paquete.perfil_id, paquete.categoria_id, cuantos,
                                 Decimal(str(paquete.precio)),
                                 nombre_del_paquete(paquete))

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
            tarifa = precio_paquete(db, tarifario.id, linea.get("perfil_id"),
                                    linea.get("categoria_id"), modalidad_id)
            total += renglon(fecha, clave, modalidad_id, tipo, tarifa.perfil_id,
                             tarifa.categoria_id, cantidad,
                             Decimal(str(tarifa.precio)), nombre_del_paquete(tarifa))
            continue

        if tipo == m.TipoLinea.RECURSO:
            tarifa = precio_recurso(db, tarifario.id, linea["perfil_id"], modalidad_id)
            unitario = Decimal(str(tarifa.precio))
            perfil_id, categoria_id = linea["perfil_id"], None
            descripcion = db.get(m.PerfilPersonal, perfil_id).nombre
        elif tipo == m.TipoLinea.VEHICULO:
            tarifa = precio_vehiculo(db, tarifario.id, linea["categoria_id"], modalidad_id)
            unitario = Decimal(str(tarifa.precio))
            perfil_id, categoria_id = None, linea["categoria_id"]
            descripcion = db.get(m.CategoriaVehiculo, categoria_id).nombre
        else:
            unitario = Decimal(str(linea["precio_unitario"]))
            perfil_id = categoria_id = None
            descripcion = linea.get("descripcion", "Viaticos")

        total += renglon(fecha, clave, modalidad_id, tipo, perfil_id,
                         categoria_id, cantidad, unitario, descripcion)

    cotizacion.total = total
    db.commit()
    db.refresh(cotizacion)
    return cotizacion


def autorizar(db: Session, cotizacion_id: int, autorizada_por: str) -> m.Cotizacion:
    from datetime import datetime

    cotizacion = db.get(m.Cotizacion, cotizacion_id)
    if not cotizacion:
        raise HTTPException(404, f"No existe la cotizacion {cotizacion_id}")
    if cotizacion.estatus == m.EstatusCotizacion.SUSTITUIDA:
        raise HTTPException(409, "Esa cotizacion fue sustituida por una version posterior")

    cotizacion.estatus = m.EstatusCotizacion.AUTORIZADA
    cotizacion.autorizada_en = datetime.now()
    cotizacion.autorizada_por = autorizada_por

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
    db.commit()
    db.refresh(cotizacion)
    return cotizacion


def vigente(db: Session, servicio_id: int) -> m.Cotizacion | None:
    """La cotizacion autorizada mas reciente."""
    return (db.query(m.Cotizacion)
            .filter_by(servicio_id=servicio_id,
                       estatus=m.EstatusCotizacion.AUTORIZADA)
            .order_by(m.Cotizacion.version.desc())
            .first())

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


def generar(db: Session, servicio_id: int, lineas: list[dict],
            viaticos_incluidos: bool = True, creada_por_id: int | None = None,
            motivo: str | None = None) -> m.Cotizacion:
    """Arma la cotizacion tomando los precios del tarifario del cliente.

    Cada linea: {fecha, equipo, tipo, perfil_id | categoria_id, cantidad}
    La modalidad se toma de la jornada de ese dia, porque la modalidad es
    de cada dia y no del servicio completo.
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

    total = Decimal("0")
    for linea in lineas:
        clave = linea.get("equipo_clave") or "Alfa"
        fecha = linea["fecha"]
        modalidad_id = modalidad_por_dia.get((clave, fecha))
        if not modalidad_id:
            raise HTTPException(400, f"No hay jornada del equipo {clave} el {fecha}")

        cantidad = int(linea.get("cantidad", 1))
        tipo = m.TipoLinea(linea["tipo"])

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

        subtotal = unitario * cantidad
        total += subtotal

        db.add(m.LineaCotizacion(
            cotizacion_id=cotizacion.id, fecha=fecha, equipo_clave=clave,
            modalidad_id=modalidad_id, tipo=tipo, perfil_id=perfil_id,
            categoria_id=categoria_id, cantidad=cantidad,
            precio_unitario=unitario, subtotal=subtotal, descripcion=descripcion))

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

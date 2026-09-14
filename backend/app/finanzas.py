"""El control del dinero que sale a la calle.

Finanzas no trabaja servicio por servicio: abre una lista de lo que hay
que despachar hoy y la despacha. Pero despachar no es controlar. Para
controlar hacen falta tres cosas mas, y ninguna existia:

  - memoria de lo que ya se pago, con su referencia y su firma
  - la cuenta de quien trae dinero de la empresa sin comprobar
  - lo que tiene que regresar, por devolucion o por descuento

Todo se separa por pais. Juntar pesos y reales da un total que no
significa nada, y pone a quien paga en Mexico a mirar depositos de
Brasil que no le tocan.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app import models as m

CERO = Decimal("0")

# Cuando se mira "lo depositado" sin decir desde cuando.
DIAS_POR_OMISION = 30

EN_CAMINO = (m.EstatusTransferencia.PENDIENTE, m.EstatusTransferencia.ENVIADA)

# El dinero que ya salio y todavia no se cierra. Es lo que la empresa
# trae en la calle.
AFUERA = (m.EstatusViatico.TRANSFERIDO, m.EstatusViatico.EN_COMPROBACION)


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _de_donde(viatico: m.AsignacionViatico) -> dict:
    """El servicio del que cuelga un viatico, para poder ir a verlo."""
    jornada = viatico.jornada
    equipo = jornada.equipo if jornada else None
    servicio = equipo.servicio if equipo else None
    return {
        "jornada_id": viatico.jornada_id,
        "fecha": jornada.fecha.isoformat() if jornada else None,
        "equipo": equipo.alias if equipo else None,
        "servicio_id": servicio.id if servicio else None,
        "folio": servicio.folio if servicio else None,
        "tipo": servicio.tipo.value if servicio else None,
        "cliente": (servicio.cliente.nombre
                    if servicio and servicio.cliente else None),
        "pais_id": servicio.pais_id if servicio else None,
    }


def _por_pais(db: Session) -> dict:
    return {p.id: p for p in db.query(m.Pais).all()}


def _caja(cajas: dict, paises: dict, pais_id, **vacios) -> dict:
    pais = paises.get(pais_id)
    return cajas.setdefault(pais_id, {
        "pais_id": pais_id,
        "codigo": pais.codigo if pais else "??",
        "pais": pais.nombre if pais else "Sin pais",
        "moneda": pais.moneda_local.value if pais else None,
        **{k: (v() if callable(v) else v) for k, v in vacios.items()},
    })


# ==================================================================
# Depositado: la memoria de lo que salio
# ==================================================================

def depositado(db: Session, desde: date | None = None,
               hasta: date | None = None, persona_id: int | None = None,
               folio: str | None = None) -> dict:
    """Lo que ya se pago, con su referencia y quien lo despacho.

    Es lo que contesta "¿cuanto depositamos esta semana?" y "¿ya le
    pagamos a Juan el martes?". Antes eso solo se podia contestar
    preguntandole a la persona.
    """
    hasta = hasta or date.today()
    desde = desde or (hasta - timedelta(days=DIAS_POR_OMISION))

    consulta = (db.query(m.SolicitudTransferencia)
                .filter(m.SolicitudTransferencia.estatus
                        == m.EstatusTransferencia.CONFIRMADA))
    filas = consulta.order_by(m.SolicitudTransferencia.id.desc()).all()

    paises, cajas = _por_pais(db), {}
    nombres = {p.id: p.nombre for p in db.query(m.Persona).all()}

    for solicitud in filas:
        cuando = solicitud.confirmada_en or solicitud.creada_en
        if cuando and not (desde <= cuando.date() <= hasta):
            continue
        viatico = solicitud.asignacion
        if not viatico:
            continue
        if persona_id and viatico.persona_id != persona_id:
            continue
        origen = _de_donde(viatico)
        if folio and folio.lower() not in (origen["folio"] or "").lower():
            continue

        caja = _caja(cajas, paises, origen["pais_id"],
                     depositos=list, total=CERO)
        caja["depositos"].append({
            "solicitud_id": solicitud.id,
            "viatico_id": viatico.id,
            "persona_id": viatico.persona_id,
            "persona": nombres.get(viatico.persona_id),
            "monto": _d(solicitud.monto),
            "moneda": solicitud.moneda.value,
            "referencia_odoo": solicitud.referencia_odoo,
            "lote": solicitud.lote,
            "confirmada_en": cuando.isoformat() if cuando else None,
            # Con firma o sin ella: los depositos de antes de que esto
            # existiera no tienen quien, y se dice en vez de dejar un
            # hueco que parece un error.
            "confirmada_por": nombres.get(solicitud.confirmada_por_id),
            **origen,
        })
        caja["total"] += _d(solicitud.monto)

    for caja in cajas.values():
        caja["depositos"].sort(key=lambda x: x["confirmada_en"] or "",
                               reverse=True)
        caja["cuantos"] = len(caja["depositos"])

    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "paises": sorted(cajas.values(), key=lambda p: p["pais"])}


# ==================================================================
# Por comprobar: el dinero que la empresa trae en la calle
# ==================================================================

def por_comprobar(db: Session, ahora: datetime | None = None) -> dict:
    """Quien trae dinero de la empresa y desde cuando.

    Perseguir comprobacion es trabajo de finanzas, no del consultor: el
    consultor valida que el gasto aplique al servicio, pero el que tiene
    que saber cuanto anda afuera es quien paga.

    Lo vencido va primero. El limite son 24 horas despues de que termina
    el servicio, y lo calcula el motor de viaticos al transferir.
    """
    ahora = ahora or datetime.now()
    viaticos = (db.query(m.AsignacionViatico)
                .filter(m.AsignacionViatico.estatus.in_(AFUERA)).all())

    paises, cajas = _por_pais(db), {}
    nombres = {p.id: p.nombre for p in db.query(m.Persona).all()}

    for v in viaticos:
        origen = _de_donde(v)
        entregado = _d(v.monto_total)
        comprobado = _d(v.monto_comprobado)
        devuelto = _d(v.monto_devuelto)
        pendiente = entregado - comprobado - devuelto
        if pendiente <= CERO:
            continue

        limite = v.limite_comprobacion
        vencido = bool(limite and limite < ahora)
        dias = None
        if limite:
            dias = int((ahora - limite).total_seconds() / 86400)

        caja = _caja(cajas, paises, origen["pais_id"],
                     personas=list, total=CERO, vencido=CERO)
        caja["personas"].append({
            "viatico_id": v.id,
            "persona_id": v.persona_id,
            "persona": nombres.get(v.persona_id),
            "entregado": entregado,
            "comprobado": comprobado,
            "devuelto": devuelto,
            "pendiente": pendiente,
            "moneda": v.moneda.value,
            "estatus": v.estatus.value,
            "limite": limite.isoformat() if limite else None,
            "vencido": vencido,
            "dias_vencido": dias if vencido else None,
            "comprobantes": len(v.comprobantes),
            "sin_validar": len([c for c in v.comprobantes
                                if not c.validado and not c.rechazado]),
            **origen,
        })
        caja["total"] += pendiente
        if vencido:
            caja["vencido"] += pendiente

    for caja in cajas.values():
        # Lo vencido primero, y dentro de eso lo mas viejo.
        caja["personas"].sort(
            key=lambda x: (not x["vencido"], -(x["dias_vencido"] or 0)))
        caja["cuantos"] = len(caja["personas"])
        caja["cuantos_vencidos"] = len([p for p in caja["personas"]
                                        if p["vencido"]])

    return {"momento": ahora.isoformat(),
            "paises": sorted(cajas.values(), key=lambda p: p["pais"])}


# ==================================================================
# Devoluciones: lo que tiene que regresar
# ==================================================================

def devoluciones(db: Session) -> dict:
    """Dos caminos distintos que terminan en lo mismo: dinero de vuelta.

    El servicio que se cancelo con el deposito ya hecho, y el viatico
    que se cerro mandando a descuento lo que nadie comprobo. Los dos
    existian en el backend y ninguno se veia en pantalla.
    """
    paises, cajas = _por_pais(db), {}
    nombres = {p.id: p.nombre for p in db.query(m.Persona).all()}

    # Lo que se cerro con descuento: va a nomina y finanzas tiene que
    # saber que ese dinero no vuelve como efectivo.
    con_descuento = (db.query(m.AsignacionViatico)
                     .filter(m.AsignacionViatico.cerrado_con_descuento
                             .is_(True)).all())
    for v in con_descuento:
        if _d(v.monto_descontado) <= CERO:
            continue
        origen = _de_donde(v)
        caja = _caja(cajas, paises, origen["pais_id"],
                     descuentos=list, devueltos=list,
                     total_descuento=CERO, total_devuelto=CERO)
        caja["descuentos"].append({
            "viatico_id": v.id,
            "persona_id": v.persona_id,
            "persona": nombres.get(v.persona_id),
            "monto": _d(v.monto_descontado),
            "absorbido": _d(v.monto_absorbido),
            "moneda": v.moneda.value,
            "motivo": v.motivo_cierre,
            "cerrado_por": nombres.get(v.cerrado_por_id),
            **origen,
        })
        caja["total_descuento"] += _d(v.monto_descontado)

    # Lo que sí regreso como dinero.
    devueltos = (db.query(m.AsignacionViatico)
                 .filter(m.AsignacionViatico.monto_devuelto > 0).all())
    for v in devueltos:
        origen = _de_donde(v)
        caja = _caja(cajas, paises, origen["pais_id"],
                     descuentos=list, devueltos=list,
                     total_descuento=CERO, total_devuelto=CERO)
        caja["devueltos"].append({
            "viatico_id": v.id,
            "persona_id": v.persona_id,
            "persona": nombres.get(v.persona_id),
            "monto": _d(v.monto_devuelto),
            "moneda": v.moneda.value,
            "estatus": v.estatus.value,
            **origen,
        })
        caja["total_devuelto"] += _d(v.monto_devuelto)

    for caja in cajas.values():
        caja["cuantos"] = len(caja["descuentos"]) + len(caja["devueltos"])

    return {"paises": sorted(cajas.values(), key=lambda p: p["pais"])}


# ==================================================================
# El corte: los cuatro numeros de arriba
# ==================================================================

def corte(db: Session, ahora: datetime | None = None) -> dict:
    """Lo que finanzas necesita saber de un vistazo, por pais.

    Comprometido es lo que ya se pidio y no ha salido; afuera es lo que
    salio y no se ha comprobado. Son dos cosas distintas y confundirlas
    es como se acaba el mes creyendo que se debe menos de lo que se debe.
    """
    ahora = ahora or datetime.now()
    paises, cajas = _por_pais(db), {}

    pendientes = (db.query(m.SolicitudTransferencia)
                  .filter(m.SolicitudTransferencia.estatus.in_(EN_CAMINO))
                  .all())
    for s_ in pendientes:
        v = s_.asignacion
        if not v:
            continue
        caja = _caja(cajas, paises, _de_donde(v)["pais_id"],
                     comprometido=CERO, afuera=CERO, vencido=CERO,
                     depositado_mes=CERO, compras_abiertas=0)
        caja["comprometido"] += _d(s_.monto)

    afuera = por_comprobar(db, ahora)
    for c in afuera["paises"]:
        caja = _caja(cajas, paises, c["pais_id"],
                     comprometido=CERO, afuera=CERO, vencido=CERO,
                     depositado_mes=CERO, compras_abiertas=0)
        caja["afuera"] += c["total"]
        caja["vencido"] += c["vencido"]

    primero = date(ahora.year, ahora.month, 1)
    del_mes = depositado(db, desde=primero, hasta=ahora.date())
    for c in del_mes["paises"]:
        caja = _caja(cajas, paises, c["pais_id"],
                     comprometido=CERO, afuera=CERO, vencido=CERO,
                     depositado_mes=CERO, compras_abiertas=0)
        caja["depositado_mes"] += c["total"]

    abiertas = (db.query(m.CompraEspecial)
                .filter(m.CompraEspecial.estatus.in_(
                    (m.EstatusCompra.SOLICITADA,
                     m.EstatusCompra.EN_GESTION))).all())
    for compra in abiertas:
        servicio = compra.equipo.servicio if compra.equipo else None
        caja = _caja(cajas, paises, servicio.pais_id if servicio else None,
                     comprometido=CERO, afuera=CERO, vencido=CERO,
                     depositado_mes=CERO, compras_abiertas=0)
        caja["compras_abiertas"] += 1

    return {"momento": ahora.isoformat(),
            "paises": sorted(cajas.values(), key=lambda p: p["pais"])}

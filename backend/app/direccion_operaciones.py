"""La ventana del director de operaciones (seccion 105).

Salvador la pidio al resolver las incidencias (decision 2, 29 sep): una
pantalla exclusiva donde le lleguen sus autorizaciones --las
incidencias, el cobro al cancelar, los plazos vencidos-- y "algunos
puntos de la operacion que puedan ser interesantes". Los puntos se
definen mas adelante; hoy es el tablero de abajo y nada mas.

Es una bandeja, no un tablero de monitoreo: la Central es la cola del
que actua minuto a minuto y el Panorama la foto de si estamos bien. Aqui
lo que hay son firmas pendientes y las cuentas del dia, por pais, para
quien decide. Cada renglon sale listo para pintar, con el id para abrir
la ficha; los numeros del tablero llevan detras la lista de servicios,
porque una cifra que no se puede abrir no se puede cuestionar.

Todo por pais y con el reloj de cada pais, como el Panorama (seccion
101): "hoy" en Ciudad de Mexico y en Sao Paulo no es el mismo dia a las
diez de la noche, y no se suman pesos con reales.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import bonos
from app import cierre as motor_cierre
from app import models as m
from app import reloj


def bandeja(db: Session, ahora: datetime | None = None) -> dict:
    """Las secciones de la pantalla."""
    from app import freelance, propuesta
    relojes = reloj.Relojes(db, ahora)
    return {
        "momento": (ahora or datetime.now()).isoformat(),
        "incidencias_por_autorizar": incidencias_por_autorizar(db),
        # El freelance con el expediente incompleto que alguien quiere
        # mandar por urgencia (seccion 111, decision 4): lo autoriza
        # direccion de operaciones, para ese servicio, con su motivo.
        "freelance_por_autorizar": freelance.urgencias(db, "pedida"),
        # El precio especial de una propuesta de implantado (seccion 115,
        # decision 2): sin su visto bueno no se puede mandar.
        "precios_especiales": propuesta.por_autorizar(db),
        "plazos_vencidos": plazos_vencidos(db, relojes),
        "cobros_por_autorizar": cobros_por_autorizar(db),
        # Las tres que vivian en otras pantallas (seccion 131, decision 19
        # de Salvador): el panel avisa y abre, no duplica la firma.
        "comisiones_por_firmar": comisiones_por_firmar(db, relojes),
        "malas_calificaciones": malas_calificaciones(db),
        "cierres_por_firmar": cierres_por_firmar(db, relojes),
        "hoy": tablero_de_hoy(db, relojes),
    }


def _ruta(servicio: m.Servicio | None, del_mes: bool = False) -> str | None:
    """Donde se abre: la operacion del servicio, o el panel del mes del
    implantado cuando lo que hay que ver es su cierre."""
    if servicio is None:
        return None
    if del_mes and servicio.tipo == m.TipoServicio.IMPLANTADO:
        return f"#/implantado/{servicio.id}"
    return f"#/servicio/{servicio.id}"


# ============================================================ incidencias

def incidencias_por_autorizar(db: Session) -> list[dict]:
    """Las que nadie ha firmado, la mas vieja primero: es la que mas
    tiempo lleva sin que el bono de alguien sepa a que atenerse."""
    filas = (db.query(m.Incidencia)
             .filter(m.Incidencia.visto_bueno_por_id.is_(None))
             .order_by(m.Incidencia.fecha, m.Incidencia.id).all())
    salida = []
    for i in filas:
        renglon = bonos.renglon_incidencia(db, i)
        servicio = db.get(m.Servicio, i.servicio_id) if i.servicio_id else None
        renglon["ruta"] = _ruta(servicio)
        renglon["cliente"] = (servicio.cliente.nombre
                              if servicio and servicio.cliente else None)
        salida.append(renglon)
    return salida


# ========================================================= plazos vencidos

def plazos_vencidos(db: Session, relojes: reloj.Relojes | None = None
                    ) -> list[dict]:
    """Los cierres cuyo plazo del consultor ya vencio sin visto bueno.

    Con las columnas que ya tiene `Cierre` y el reloj que corre en cada
    estatus (`cierre.limite_vigente`): sin visto bueno corre el del
    consultor; regresado por finanzas, las 24 horas desde el regreso. Se
    mide con la hora del pais del servicio. Es chica a proposito: otro
    grupo escribe `cierre.plazos_vencidos(db)` con lo mismo y quien
    integra decide cual queda.
    """
    relojes = relojes or reloj.Relojes(db)
    filas = (db.query(m.Cierre)
             .filter(m.Cierre.estatus.in_((
                 m.EstatusCierre.SIN_VISTO_BUENO,
                 m.EstatusCierre.EN_REVISION_IA,
                 m.EstatusCierre.DEVUELTO_A_OPERACION)))
             .all())
    salida = []
    for c in filas:
        vigente = motor_cierre.limite_vigente(c)
        if not vigente:
            continue
        quien, hasta = vigente
        ahora = relojes.del_servicio(c.servicio)
        if hasta >= ahora:
            continue
        consultor = (db.get(m.Persona, c.servicio.consultor_id)
                     if c.servicio and c.servicio.consultor_id else None)
        salida.append({
            "cierre_id": c.id, "servicio_id": c.servicio_id,
            "folio": c.servicio.folio, "tipo": c.servicio.tipo.value,
            "cliente": c.servicio.cliente.nombre if c.servicio.cliente else None,
            "periodo": (f"{c.contrato.mes:02d}/{c.contrato.anio}"
                        if c.contrato_id and c.contrato else None),
            "estatus": c.estatus.value,
            "regresado": c.estatus == m.EstatusCierre.DEVUELTO_A_OPERACION,
            "reloj": quien,
            "consultor_id": consultor.id if consultor else None,
            "consultor": consultor.nombre if consultor else None,
            "vencio": hasta.isoformat(),
            "minutos_vencido": int((ahora - hasta).total_seconds() // 60),
            "ruta": _ruta(c.servicio, del_mes=True),
        })
    salida.sort(key=lambda x: -x["minutos_vencido"])
    return salida


# ======================================================= cobros al cancelar

def cobros_por_autorizar(db: Session) -> list[dict]:
    """El cobro al cancelar --completo o lo ejecutado-- que espera el
    visto bueno del director de operaciones (decision 1 de Salvador,
    seccion 105).

    Los renglones los arma el motor del cierre (`cierre.cobros_por_autorizar`);
    aqui solo se les pone la ruta de la consola, que es donde esta el
    boton «Autorizar el cobro» (la tarjeta del cierre del servicio).
    """
    salida = []
    for c in motor_cierre.cobros_por_autorizar(db):
        c["ruta"] = f"#/servicio/{c['servicio_id']}"
        salida.append(c)
    return salida


# ===================================================== lo que vivia en otras pantallas
#
# Seccion 131, decision 19 de Salvador (2 oct): de lo que direccion de
# operaciones firma, tres cosas vivian solo en otras pantallas --el visto
# bueno del corte de comisiones del mes (Nominas), las malas
# calificaciones por clasificar (Encuestas) y los cierres que esperan su
# visto bueno (la tarjeta de cada servicio)--. Entran al panel como
# tarjetas con sus cuentas y «Abrir»; la firma sigue donde siempre.

def comisiones_por_firmar(db: Session, relojes: reloj.Relojes | None = None
                          ) -> list[dict]:
    """Los meses terminados, por pais, cuyo corte de comisiones espera
    el visto bueno: con lo que finanzas valido en el mes y las
    diferencias que cayeron en el. Un mes sin nada no espera nada."""
    from app import comisiones

    relojes = relojes or reloj.Relojes(db)
    salida = []
    for pais in (db.query(m.Pais).filter_by(activo=True)
                 .order_by(m.Pais.id).all()):
        hoy = relojes.hoy(pais.id)
        meses = set()
        for c in (db.query(m.ComisionConsultor.anio, m.ComisionConsultor.mes)
                  .join(m.Servicio,
                        m.ComisionConsultor.servicio_id == m.Servicio.id)
                  .filter(m.Servicio.pais_id == pais.id).distinct().all()):
            meses.add((c.anio, c.mes))
        for a in (db.query(m.AjusteComision.anio, m.AjusteComision.mes)
                  .filter(m.AjusteComision.pais_id == pais.id)
                  .distinct().all()):
            meses.add((a.anio, a.mes))
        for anio, mes in sorted(meses):
            if (anio, mes) >= (hoy.year, hoy.month):
                continue            # el mes que corre todavia no se firma
            if comisiones.corte_de(db, pais.id, anio, mes):
                continue
            vista = comisiones.corte_del_mes(db, pais.id, anio, mes,
                                             ahora=relojes.ahora(pais.id))
            consultores = [f for f in vista["consultores"]
                           if f["se_paga"] or f["diferencias"]
                           or f["no_se_paga"]]
            if not consultores:
                continue
            salida.append({
                "pais_id": pais.id, "pais": pais.nombre,
                "anio": anio, "mes": mes, "periodo": f"{mes:02d}/{anio}",
                "consultores": len(consultores),
                "a_pagar": vista["totales"]["a_pagar"],
                "moneda": vista["moneda"],
                "se_puede_autorizar": vista["se_puede_autorizar"],
                "ruta": f"#/nomina/comisiones/{pais.id}/{anio}-{mes:02d}",
            })
    return salida


def malas_calificaciones(db: Session) -> list[dict]:
    """Las encuestas con calificacion baja que nadie ha clasificado, la
    mas vieja primero: la del solicitante --que califica al consultor-- la
    decide direccion de operaciones; la del ejecutivo, el consultor del
    servicio, y aqui se ve si lleva dias esperando."""
    filas = (db.query(m.Encuesta)
             .filter_by(requiere_clasificacion=True, incidencia_id=None)
             .filter(m.Encuesta.clasificada_en.is_(None))
             .order_by(m.Encuesta.respondida_en, m.Encuesta.id).all())
    salida = []
    for e in filas:
        servicio = e.servicio
        consultor = (db.get(m.Persona, servicio.consultor_id)
                     if servicio and servicio.consultor_id else None)
        comentario = next((r.texto for r in e.respuestas if r.texto), None)
        salida.append({
            "encuesta_id": e.id, "servicio_id": e.servicio_id,
            "folio": servicio.folio if servicio else None,
            "cliente": (servicio.cliente.nombre
                        if servicio and servicio.cliente else None),
            "tipo": e.tipo.value,
            "quien": e.destinatario_nombre or e.destinatario_correo,
            "calificacion": e.calificacion,
            "respondida_en": (e.respondida_en.isoformat()
                              if e.respondida_en else None),
            "comentario": comentario,
            # A quien le toca: direccion, o el consultor del servicio.
            "le_toca": ("direccion" if e.tipo == m.TipoEncuesta.SOLICITANTE
                        else "consultor"),
            "consultor": consultor.nombre if consultor else None,
            "ruta": "#/encuestas",
        })
    return salida


def cierres_por_firmar(db: Session, relojes: reloj.Relojes | None = None
                       ) -> list[dict]:
    """Los cierres --servicios y meses-- que esperan el visto bueno del
    consultor y siguen en plazo, con lo que hay que cobrar y cuanto les
    queda. Los que ya vencieron estan en «Plazos vencidos». Direccion de
    operaciones puede dar ese visto bueno en lugar del consultor."""
    from app import cierre_mes
    from app import cotizacion as cot

    relojes = relojes or reloj.Relojes(db)
    filas = (db.query(m.Cierre)
             .filter(m.Cierre.estatus.in_((
                 m.EstatusCierre.SIN_VISTO_BUENO,
                 m.EstatusCierre.EN_REVISION_IA,
                 m.EstatusCierre.DEVUELTO_A_OPERACION)))
             .all())
    salida = []
    for c in filas:
        vigente = motor_cierre.limite_vigente(c)
        if not vigente:
            continue
        quien, hasta = vigente
        ahora = relojes.del_servicio(c.servicio)
        if hasta < ahora:
            continue            # vencido: esta en su propia tarjeta
        consultor = (db.get(m.Persona, c.servicio.consultor_id)
                     if c.servicio and c.servicio.consultor_id else None)
        monto = moneda = None
        try:
            if c.contrato_id:
                comparativo = cierre_mes.comparar(db, c.contrato)
                monto = comparativo["a_facturar"]["total"]
                moneda = comparativo["moneda"]
            else:
                vigente_cot = cot.vigente(db, c.servicio_id)
                if vigente_cot is not None:
                    monto = vigente_cot.total
                    moneda = vigente_cot.moneda.value
        except Exception:                                   # noqa: BLE001
            # Sin precio o sin tipo de cambio no hay cifra: la tarjeta
            # igual lo lista, sin monto.
            monto = moneda = None
        salida.append({
            "cierre_id": c.id, "servicio_id": c.servicio_id,
            "folio": c.servicio.folio, "tipo": c.servicio.tipo.value,
            "cliente": c.servicio.cliente.nombre if c.servicio.cliente else None,
            "periodo": (f"{c.contrato.mes:02d}/{c.contrato.anio}"
                        if c.contrato_id and c.contrato else None),
            "estatus": c.estatus.value,
            "regresado": c.estatus == m.EstatusCierre.DEVUELTO_A_OPERACION,
            "reloj": quien,
            "consultor_id": consultor.id if consultor else None,
            "consultor": consultor.nombre if consultor else None,
            "vence": hasta.isoformat(),
            "minutos_restantes": int((hasta - ahora).total_seconds() // 60),
            "monto": monto, "moneda": moneda,
            "ruta": _ruta(c.servicio, del_mes=True),
        })
    salida.sort(key=lambda x: x["minutos_restantes"])
    return salida


# ================================================================ el tablero

def _cuenta(servicios: dict[int, m.Servicio]) -> dict:
    """Un numero con la lista de servicios detras, para abrirlos."""
    lista = sorted(servicios.values(), key=lambda s: s.folio or "")
    return {"n": len(lista),
            "lista": [{"servicio_id": s.id, "folio": s.folio,
                       "tipo": s.tipo.value,
                       "cliente": s.cliente.nombre if s.cliente else None,
                       "ruta": _ruta(s)} for s in lista]}


def _servicios_del_dia(db: Session, pais_id: int, dia) -> dict[int, m.Servicio]:
    """Los servicios con un dia no cancelado en esa fecha: el eventual
    por su fecha, el implantado por el dia activo de su mes."""
    jornadas = (db.query(m.Jornada)
                .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
                .filter(m.Servicio.pais_id == pais_id,
                        m.Jornada.fecha == dia,
                        m.Jornada.estatus != m.EstatusJornada.CANCELADA)
                .all())
    return {j.equipo.servicio_id: j.equipo.servicio for j in jornadas}


def _en_curso(db: Session, pais_id: int) -> dict[int, m.Servicio]:
    """Lo que esta en la calle ahora: el equipo que llego al punto o ya
    arranco. La misma lista que la central (`ARRANCADAS`)."""
    jornadas = (db.query(m.Jornada)
                .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
                .filter(m.Servicio.pais_id == pais_id,
                        m.Jornada.estatus.in_(m.ARRANCADAS))
                .all())
    return {j.equipo.servicio_id: j.equipo.servicio for j in jornadas}


def _con_alerta(db: Session, pais_id: int) -> dict[int, m.Servicio]:
    """Las alertas que levanto el campo --panico, llamada-- y la central
    no ha cerrado (`contingencia`)."""
    alertas = (db.query(m.AlertaIncidencia)
               .join(m.Servicio, m.AlertaIncidencia.servicio_id == m.Servicio.id)
               .filter(m.Servicio.pais_id == pais_id,
                       m.AlertaIncidencia.estatus != m.EstatusAlerta.CERRADA)
               .all())
    salida = {}
    for a in alertas:
        servicio = db.get(m.Servicio, a.servicio_id)
        if servicio:
            salida[servicio.id] = servicio
    return salida


def _cambios_en_curso(db: Session, pais_id: int, hoy) -> dict[int, m.Servicio]:
    """Los cambios por contingencia que siguen corriendo hoy: arrancaron
    ya, el titular no ha vuelto, y su ultimo dia --el `hasta`, o el
    ultimo dia del servicio si el cambio fue de ahi en adelante-- no ha
    pasado."""
    cambios = (db.query(m.ReemplazoRecurso)
               .join(m.Servicio, m.ReemplazoRecurso.servicio_id == m.Servicio.id)
               .filter(m.Servicio.pais_id == pais_id,
                       m.ReemplazoRecurso.regreso_en.is_(None))
               .all())
    salida = {}
    for r in cambios:
        desde = db.get(m.Jornada, r.desde_jornada_id)
        if not desde or desde.fecha > hoy:
            continue
        if r.hasta_jornada_id:
            hasta = db.get(m.Jornada, r.hasta_jornada_id)
            fin = hasta.fecha if hasta else None
        else:
            fin = max((j.fecha for j in desde.equipo.jornadas
                       if j.estatus != m.EstatusJornada.CANCELADA),
                      default=None)
        if fin is not None and fin < hoy:
            continue
        servicio = db.get(m.Servicio, r.servicio_id)
        if servicio:
            salida[servicio.id] = servicio
    return salida


def _incidencias_del_mes(db: Session, pais_id: int, hoy) -> dict:
    """Las del mes que corre en ese pais, por gravedad, contando solo las
    que ya tienen visto bueno favorable; las pendientes van aparte. El
    pais es el del servicio: una incidencia sin servicio no tiene pais
    y no entra al tablero (si a la bandeja de arriba)."""
    filas = (db.query(m.Incidencia)
             .join(m.Servicio, m.Incidencia.servicio_id == m.Servicio.id)
             .filter(m.Servicio.pais_id == pais_id,
                     m.Incidencia.fecha >= hoy.replace(day=1),
                     m.Incidencia.fecha <= hoy)
             .all())
    por_gravedad = {g.value: {} for g in m.GravedadIncidencia}
    pendientes, descartadas = 0, 0
    for i in filas:
        if i.visto_bueno_por_id is None:
            pendientes += 1
            continue
        if not i.autorizada:
            descartadas += 1
            continue
        servicio = db.get(m.Servicio, i.servicio_id)
        if servicio:
            por_gravedad[i.gravedad.value][servicio.id] = servicio
    return {
        "periodo": f"{hoy.month:02d}/{hoy.year}",
        **{g: _cuenta(lista) for g, lista in por_gravedad.items()},
        "pendientes": pendientes,
        "descartadas": descartadas,
    }


def tablero_de_hoy(db: Session, relojes: reloj.Relojes | None = None
                   ) -> list[dict]:
    """Un renglon por pais activo, con su hoy y su hora."""
    relojes = relojes or reloj.Relojes(db)
    salida = []
    for pais in (db.query(m.Pais).filter_by(activo=True)
                 .order_by(m.Pais.id).all()):
        hoy = relojes.hoy(pais.id)
        salida.append({
            "pais_id": pais.id, "pais": pais.nombre, "codigo": pais.codigo,
            "hoy": hoy.isoformat(),
            "ahora": relojes.ahora(pais.id).isoformat(),
            "servicios_hoy": _cuenta(_servicios_del_dia(db, pais.id, hoy)),
            "servicios_manana": _cuenta(
                _servicios_del_dia(db, pais.id, hoy + timedelta(days=1))),
            "en_curso": _cuenta(_en_curso(db, pais.id)),
            "alertas_abiertas": _cuenta(_con_alerta(db, pais.id)),
            "cambios_en_curso": _cuenta(_cambios_en_curso(db, pais.id, hoy)),
            "incidencias_mes": _incidencias_del_mes(db, pais.id, hoy),
        })
    return salida

"""Nomina semanal del personal de seguridad.

Se paga los lunes a mediodia. El corte toma todo lo que ya va camino a
facturacion y todavia no se ha pagado.

La regla que le da forma a todo el modulo: el dinero ya salio no se
reabre. Si un servicio se regresa y cambia despues del pago, la
diferencia viaja como ajuste a la nomina siguiente, con signo.

El lunes (seccion 66, decisiones de Salvador del 25 de septiembre), en
hora de cada pais:

  7:00   el reloj arma el borrador con todo lo que ya se debe
  11:00  lo recalcula por ultima vez y queda listo para pagar; lo que
         llegue despues pasa al lunes siguiente
  12:00  finanzas paga y lo marca pagado

Y nadie cobra en negativo: si una diferencia se come lo de la semana, la
persona queda en cero y lo que falta pasa a su siguiente corte, las
veces que haga falta, hasta saldarse.

El corte que no se pago el lunes (seccion 105, decision 11 de Salvador,
29 de septiembre): sigue a la vista hasta pagarse --un martes, un
jueves--, y si llega al lunes siguiente sin pagarse, el corte nuevo se
lo lleva entero: sus dias y sus ajustes pasan al nuevo con su semana de
origen, sale un solo corte de dos semanas, y el viejo queda "absorbido"
apuntando al que se lo llevo. Se van juntando las veces que haga falta.
"""
import calendar
import logging
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, contains_eager, joinedload

from app import models as m
from app import reloj
from app.cierre import _horas_extra, factor_festivo, limite_vigente

registro = logging.getLogger("centauro.nomina")

CERO = Decimal("0")

# El horario del lunes, en hora del pais.
HORA_BORRADOR = time(7, 0)
HORA_CIERRE = time(11, 0)
HORA_PAGO = time(12, 0)

# Un servicio eventual entra al corte cuando el consultor ya lo mando.
# No se espera a que finanzas apruebe: el personal no tiene por que pagar
# el tiempo de revision. Si algo cambia, se ajusta la semana siguiente.
EN_FACTURACION = (m.EstatusCierre.ENVIADO_FINANZAS,
                  m.EstatusCierre.APROBADO,
                  m.EstatusCierre.FACTURADO)


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def lunes_de(dia: date | None = None) -> date:
    """El lunes de esa semana. Es la fecha con la que se identifica el corte."""
    dia = dia or date.today()
    return dia - timedelta(days=dia.weekday())


# ---------------------------------------------------------------- tarifas

def _tipo_de(asignacion: m.AsignacionPersonal) -> m.TipoServicio:
    """De que operacion es ese dia. Eventual e implantado se pagan con
    tablas distintas: no es la misma operacion."""
    jornada = asignacion.jornada
    equipo = jornada.equipo if jornada else None
    servicio = equipo.servicio if equipo else None
    return servicio.tipo if servicio else m.TipoServicio.EVENTUAL


def hay_tarifa(db: Session, asignacion: m.AsignacionPersonal,
               modalidad_id: int, pais_id: int) -> bool:
    """Si no hay tarifa, esa jornada no se puede pagar. Sin excepciones.

    La tarifa se busca por el rol con el que la persona fue ese dia, no
    por lo que la persona es: el mismo agente que el martes conduce y el
    miercoles coordina cobra distinto cada dia, y eso es justo lo que se
    esta pagando.
    """
    return que_falta_de_tarifa(db, asignacion, modalidad_id, pais_id) is None


def que_falta_de_tarifa(db: Session, asignacion: m.AsignacionPersonal,
                        modalidad_id: int, pais_id: int,
                        jornada: m.Jornada | None = None) -> str | None:
    """Que le falta a esa jornada para poder pagarse: "tarifa", "hora
    extra", o nada. La hora extra solo hace falta si el dia la tuvo
    (seccion 98)."""
    persona = asignacion.persona
    if persona.es_freelance:
        tarifa = (db.query(m.TarifaFreelance)
                  .filter_by(persona_id=persona.id,
                             modalidad_id=modalidad_id).first())
        if not tarifa:
            return "tarifa"
        extra = tarifa.costo_hora_extra
    else:
        if not asignacion.rol_id:
            return "tarifa"     # sin rol no hay tarifa que buscar
        comision = (db.query(m.ComisionPersonal)
                    .filter_by(pais_id=pais_id, perfil_id=asignacion.rol_id,
                               tipo_servicio=_tipo_de(asignacion),
                               modalidad_id=modalidad_id).first())
        if not comision:
            return "tarifa"
        extra = comision.monto_hora_extra
    if (jornada is not None and extra is None and not asignacion.relevado_en
            and _horas_extra(jornada)):
        return "hora extra"
    return None


def pago_de_jornada(db: Session, jornada: m.Jornada,
                    asignacion: m.AsignacionPersonal,
                    pais_id: int) -> dict | None:
    """Lo que se le debe a una persona por una jornada.

    El freelance cobra su tarifa personalizada; el de planta, el
    tabulador de comisiones del rol con el que fue ese dia. En dia
    festivo ambos van con factor.
    """
    persona = asignacion.persona
    if persona.es_freelance:
        tarifa = (db.query(m.TarifaFreelance)
                  .filter_by(persona_id=persona.id,
                             modalidad_id=jornada.modalidad_id).first())
        base = _d(tarifa.costo) if tarifa else None
        hora_extra = (None if tarifa is None or tarifa.costo_hora_extra is None
                      else _d(tarifa.costo_hora_extra))
        fuente = "tarifa freelance"
    else:
        comision = None
        if asignacion.rol_id:
            comision = (db.query(m.ComisionPersonal)
                        .filter_by(pais_id=pais_id, perfil_id=asignacion.rol_id,
                                   tipo_servicio=_tipo_de(asignacion),
                                   modalidad_id=jornada.modalidad_id).first())
        base = _d(comision.monto) if comision else None
        hora_extra = (None if comision is None or comision.monto_hora_extra is None
                      else _d(comision.monto_hora_extra))
        fuente = "tabulador de comisiones"

    if base is None:
        # Sin tarifa no se inventa un monto: se reporta para que lo carguen.
        return None

    factor = factor_festivo(db, pais_id, jornada.fecha)
    # Quien fue relevado a media jornada cobra su dia completo —se
    # presento y perdio el dia, y no fue su culpa— pero no las horas
    # extra: esas las trabajo quien se quedo hasta el final.
    #
    # Y quien no alcanzo a marcar su llegada no aparece aqui siquiera:
    # el reemplazo no le deja asignacion, porque no trabajo. La regla
    # vive en `contingencia.se_presento`, donde se puede verificar sola.
    extras = 0 if asignacion.relevado_en else _horas_extra(jornada)
    # La hora extra vacia es dato que falta, no cero (seccion 98): un
    # dia con dos horas extra y la celda "h. extra" en blanco decia
    # "2 h extra" y pagaba cero por ellas. Sin tarifa, el corte no sale.
    if extras and hora_extra is None:
        return None
    de_horas_extra = (hora_extra or CERO) * extras * factor
    monto = base * factor + de_horas_extra

    modalidad = jornada.modalidad.codigo.value
    partes = [f"{jornada.fecha.isoformat()} {modalidad}"]
    # El rol va en la descripcion porque es lo que explica el monto: dos
    # dias iguales con distinto rol se pagan distinto, y un recibo que no
    # lo dice se lee como un error de la empresa.
    if asignacion.rol:
        partes.append(asignacion.rol.nombre)
    # El recibo tiene que decir por que ese dia se pago a dos personas.
    if asignacion.relevado_en:
        partes.append(f"relevado {asignacion.relevado_en.strftime('%H:%M')}")
    elif asignacion.reemplaza_a_id:
        partes.append("entra por relevo")
    if extras:
        partes.append(f"{extras} h extra")
    if factor > 1:
        partes.append(f"festivo x{factor.normalize()}")

    return {"monto": monto, "factor": factor, "horas_extra": extras,
            "monto_horas_extra": de_horas_extra if extras else None,
            "rol_id": asignacion.rol_id,
            "descripcion": " · ".join(partes), "fuente": fuente}


# ---------------------------------------------------------------- que entra

def _ya_pagada(excepto_nomina_id: int | None = None):
    """La condicion de que ese par (jornada, persona) ya esta pagado o
    apartado por otro corte, para pedirselo a la base en la misma
    consulta y no cargar todos los conceptos de la historia."""
    condiciones = [m.ConceptoNomina.jornada_id == m.Jornada.id,
                   m.ConceptoNomina.persona_id == m.AsignacionPersonal.persona_id]
    if excepto_nomina_id:
        condiciones.append(m.RenglonNomina.nomina_id != excepto_nomina_id)
    return (select(m.ConceptoNomina.id)
            .select_from(m.ConceptoNomina)
            .join(m.RenglonNomina,
                  m.ConceptoNomina.renglon_id == m.RenglonNomina.id)
            .where(and_(*condiciones))
            .exists())


def _estatus_del_cierre():
    """El estatus del ultimo cierre del servicio (el eventual tiene uno;
    si por algo tuviera dos, vale el mas nuevo, como antes)."""
    return (select(m.Cierre.estatus)
            .where(m.Cierre.servicio_id == m.Servicio.id)
            .order_by(m.Cierre.id.desc()).limit(1)
            .scalar_subquery())


def _terminadas_con_su_gente(db: Session, pais_id: int):
    """Las jornadas terminadas del pais con cada asignacion, cargadas con
    su equipo, su servicio y su modalidad en la misma consulta."""
    return (db.query(m.Jornada, m.AsignacionPersonal)
            .join(m.AsignacionPersonal,
                  m.AsignacionPersonal.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
            .filter(m.Servicio.pais_id == pais_id,
                    m.Jornada.estatus == m.EstatusJornada.TERMINADA)
            .options(contains_eager(m.Jornada.equipo)
                     .contains_eager(m.Equipo.servicio),
                     joinedload(m.Jornada.modalidad),
                     joinedload(m.AsignacionPersonal.persona),
                     joinedload(m.AsignacionPersonal.rol)))


def jornadas_pendientes(db: Session, pais_id: int,
                        excepto_nomina_id: int | None = None,
                        persona_id: int | None = None,
                        limite: int | None = None,
                        ) -> list[tuple[m.Jornada, m.AsignacionPersonal]]:
    """Pares (jornada, persona) que se deben y no se han pagado.

    El eventual entra cuando su cierre ya va camino a facturacion. El
    implantado entra por dia trabajado, sin esperar al cierre mensual: su
    contrato se factura al mes, pero su gente cobra cada semana. Al cerrar
    el mes se revisa el periodo completo y lo que salga distinto se
    arrastra como ajuste (ver diferencias_del_servicio).

    Una sola consulta con sus joins (seccion 101): antes traia todos los
    conceptos pagados de la historia, todos los cierres y todas las
    jornadas terminadas del pais, y cargaba una por una su servicio y su
    gente. "Pagos" en la app lo hacia por cada agente para quedarse con
    sus propios dias; con `persona_id` la base entrega solo los suyos.
    `limite` es para quien solo quiere saber si hay algo.
    """
    # Lo que ya esta pagado o apartado por OTRO corte. La diferencia
    # importa: un borrador que nadie pago no puede excluir esas jornadas
    # para siempre —eso dejaba a alguien sin cobrar sin que nada lo
    # avisara— pero mientras exista tampoco puede pagarse dos veces. Por
    # eso un borrador se puede descartar (ver `descartar`), y mientras
    # no se descarte, aparta.
    consulta = (_terminadas_con_su_gente(db, pais_id)
                .filter(~_ya_pagada(excepto_nomina_id),
                        or_(m.Servicio.tipo == m.TipoServicio.IMPLANTADO,
                            _estatus_del_cierre().in_(EN_FACTURACION)))
                .order_by(m.Jornada.fecha, m.Jornada.id, m.AsignacionPersonal.id))
    if persona_id:
        consulta = consulta.filter(m.AsignacionPersonal.persona_id == persona_id)
    if limite:
        consulta = consulta.limit(limite)
    return [(j, a) for j, a in consulta.all()]


# ---------------------------------------------------------------- calculo

def _sin_tarifa(db: Session, pais_id: int,
                pendientes: list[tuple[m.Jornada, m.AsignacionPersonal]]
                ) -> list[dict]:
    """De lo que entraria al corte, lo que no se puede pagar y por que:
    la tabla que detiene el corte y que la pantalla ensena con nombre y
    dia. Es una sola para el calculo, la vista previa y el borrador que
    no cerro (seccion 101)."""
    faltan = []
    for jornada, a in pendientes:
        falta = que_falta_de_tarifa(db, a, jornada.modalidad_id, pais_id,
                                    jornada)
        if falta:
            faltan.append({
                "persona": a.persona.nombre,
                "fecha": jornada.fecha.isoformat(),
                "modalidad": jornada.modalidad.codigo.value,
                "rol": a.rol.nombre if a.rol else None,
                "tipo": "freelance" if a.persona.es_freelance else "de planta",
                # Que es lo que falta: la tarifa del dia, o solo la hora
                # extra de un dia que las tuvo.
                "falta": falta})
    return faltan


def sin_tarifa_pendiente(db: Session, pais_id: int,
                         excepto_nomina_id: int | None = None) -> list[dict]:
    """Lo que hoy detendria el corte: las jornadas que se deben, no estan
    en otro corte, y no tienen tarifa. Con `excepto_nomina_id` se mira
    lo que veria el recalculo de ese borrador."""
    return _sin_tarifa(db, pais_id,
                       jornadas_pendientes(db, pais_id, excepto_nomina_id))


def candado_del_pais(db: Session, pais_id: int) -> None:
    """Un armado de nomina de ese pais a la vez, hasta que confirme
    (seccion 105).

    Dos vueltas del reloj encimadas --o el reloj y "Armar el corte de
    hoy" al mismo tiempo-- leian las dos que el corte de hoy no existia
    y las dos se llevaban el corte de la semana pasada: sus renglones
    se duplicaban o el segundo reventaba a medias. Con el candado, el
    segundo espera y encuentra el corte ya armado. Vive en la
    transaccion, como el de Odoo y el de las asignaciones.
    """
    import zlib

    from sqlalchemy import text

    db.execute(text("SELECT pg_advisory_xact_lock(:llave)"),
               {"llave": zlib.crc32(f"nomina:{pais_id}".encode())})


def _absorbido_por(db: Session, nomina: m.NominaSemanal) -> HTTPException:
    """El 409 de un corte absorbido: se paga desde el que se lo llevo."""
    otro = (db.get(m.NominaSemanal, nomina.absorbida_por_id)
            if nomina.absorbida_por_id else None)
    cuando = f" del lunes {otro.fecha_corte:%d/%m/%Y}" if otro else " siguiente"
    return HTTPException(409, {
        "mensaje": f"Este corte lo absorbió el{cuando}: págalo desde ahí",
        "que_hacer": "Sus días y sus ajustes ya están en ese corte, con su "
                     "semana de origen. Este ya no se paga ni se tira.",
        "nomina_id": otro.id if otro else None})


def _heredado(c: m.ConceptoNomina, persona_id: int, semana: date) -> dict:
    """Un concepto de un corte absorbido, tal como lo escribe el corte
    nuevo: los mismos numeros, sin recalcular, con su semana de origen."""
    return {"persona_id": persona_id, "monto": _d(c.monto),
            "factor": _d(c.factor_festivo) if c.factor_festivo is not None
            else Decimal("1"),
            "horas_extra": c.horas_extra or 0, "descripcion": c.descripcion,
            "jornada_id": c.jornada_id, "ajuste_id": c.ajuste_id,
            "rol_id": c.rol_id,
            "monto_horas_extra": (_d(c.monto_horas_extra)
                                  if c.monto_horas_extra is not None else None),
            "semana_origen": semana}


def _absorber(db: Session, nomina: m.NominaSemanal) -> list[dict]:
    """Los cortes anteriores del pais que nadie pago pasan a este
    (seccion 105, decision 11).

    Se lleva sus renglones tal cual --el dia, la hora extra, el ajuste,
    el descuento-- con el lunes de donde vienen; el renglon del saldo en
    contra no, porque no es dinero sino la cuenta que dejo a alguien en
    cero, y esa cuenta se vuelve a hacer con las dos semanas juntas. Sus
    ajustes apartados pasan a estar apartados por este. El viejo queda
    absorbido, sin renglones, apuntando a este; y este cubre desde el
    lunes del mas viejo que trae.

    Con la fila del viejo bloqueada: si finanzas lo esta marcando pagado
    en ese instante, se espera a que termine y ya no se absorbe (quedo
    pagado), y al reves, "Marcar pagado" espera y encuentra que ya lo
    absorbio este. Un corte viejo sin renglones no tiene nada que
    llevarse: se quita, que es lo mismo que tirar un borrador vacio.
    """
    heredados = []
    viejos = (db.query(m.NominaSemanal)
              .filter(m.NominaSemanal.pais_id == nomina.pais_id,
                      m.NominaSemanal.fecha_corte < nomina.fecha_corte,
                      m.NominaSemanal.estatus == m.EstatusNomina.CALCULADA)
              .order_by(m.NominaSemanal.fecha_corte)
              .with_for_update().all())
    for viejo in viejos:
        for a in db.query(m.AjusteNomina).filter_by(
                pagado_en_nomina_id=viejo.id).all():
            a.pagado_en_nomina_id = nomina.id
        if not viejo.renglones:
            for hija in db.query(m.NominaSemanal).filter_by(
                    absorbida_por_id=viejo.id).all():
                hija.absorbida_por_id = nomina.id
            db.delete(viejo)
            continue
        for r in viejo.renglones:
            for c in r.conceptos:
                if c.saldo_en_contra:
                    continue
                heredados.append(_heredado(
                    c, r.persona_id, c.semana_origen or viejo.fecha_corte))
        for r in list(viejo.renglones):
            db.delete(r)
        viejo.estatus = m.EstatusNomina.ABSORBIDA
        viejo.absorbida_por_id = nomina.id
        nomina.desde = min(nomina.desde, viejo.desde)
    # Los conceptos viejos se borran antes de escribir los nuevos: una
    # jornada se le paga a una persona una sola vez, y la base lo cuida.
    db.flush()
    return heredados


def calcular(db: Session, pais_id: int, fecha_corte: date | None = None,
             quien_id: int | None = None) -> dict:
    """Arma (o rearma) el corte de la semana. No paga: deja la propuesta.

    `quien_id` es quien lo pidio; vacio es el reloj del lunes.

    Desde la seccion 105 el corte nuevo se lleva los cortes anteriores
    del pais que nadie pago (decision 11): el del 28 trae la semana del
    21, y el del 5 se lleva al del 28 con todo y la del 21. Lo heredado
    no se recalcula --ese corte ya habia cerrado-- y se conserva tal cual
    en cada "Recalcular". Armado a mano despues de las 11:00 ("Armar el
    corte de hoy" porque el reloj no corrio) queda como borrador: la
    siguiente vuelta del reloj lo cierra, y si el reloj sigue caido se
    paga como borrador, que es cerrarlo.
    """
    pais = db.get(m.Pais, pais_id)
    if not pais:
        raise HTTPException(404, f"No existe el pais {pais_id}")
    corte = lunes_de(fecha_corte)
    candado_del_pais(db, pais_id)

    nomina = (db.query(m.NominaSemanal)
              .filter_by(pais_id=pais_id, fecha_corte=corte)
              .with_for_update().first())
    if nomina and nomina.estatus == m.EstatusNomina.PAGADA:
        raise HTTPException(409, {
            "mensaje": "Esa nomina ya se pago; lo que cambie va como ajuste "
                       "a la siguiente",
            "nomina_id": nomina.id})
    if nomina and nomina.estatus == m.EstatusNomina.ABSORBIDA:
        raise _absorbido_por(db, nomina)
    # Desde las 11:00 el corte esta listo para pagar y no se mueve: lo
    # que tenga su visto bueno despues entra solo al lunes siguiente.
    # Recalcularlo mientras finanzas paga cambiaria las cifras debajo de
    # quien esta transfiriendo.
    if nomina and nomina.lista_en:
        raise HTTPException(409, {
            "mensaje": "Ese corte ya cerro a las 11:00",
            "que_hacer": "Lo que llego despues entra solo al corte del "
                         "lunes siguiente.",
            "nomina_id": nomina.id})
    heredados: list[dict] = []
    if nomina:
        # Lo que este corte ya heredo de otros se conserva tal cual: el
        # corte de donde vino ya no existe como para volver a leerlo.
        heredados = [_heredado(c, r.persona_id, c.semana_origen)
                     for r in nomina.renglones for c in r.conceptos
                     if c.semana_origen is not None]
        # Recalcular es rehacerla: mientras no se pague, no hay nada que
        # cuidar. Lo que si hay que hacer es soltar lo apartado, o los
        # ajustes quedarian retenidos por un borrador que ya no los
        # incluye.
        for a in db.query(m.AjusteNomina).filter_by(
                pagado_en_nomina_id=nomina.id).all():
            a.pagado_en_nomina_id = None
        for r in list(nomina.renglones):
            db.delete(r)
        db.flush()
    else:
        nomina = m.NominaSemanal(pais_id=pais_id, fecha_corte=corte,
                                 desde=corte, moneda=pais.moneda_local)
        db.add(nomina)
        db.flush()

    # No se filtra por fecha: lo que manda es que la jornada este
    # terminada y su servicio ya vaya a facturacion. Una jornada no puede
    # estar terminada sin haber ocurrido. Se lee ANTES de absorber: los
    # cortes viejos todavia apartan lo suyo, que entra por herencia y no
    # como jornada pendiente.
    pendientes = jornadas_pendientes(db, pais_id, excepto_nomina_id=nomina.id)

    # Antes de armar nada: si algo no tiene tarifa, el corte no sale.
    # Pagar de menos a alguien que trabajo es peor que retrasar el corte,
    # y dejarlo fuera en silencio seria justo eso.
    sin_tarifa = _sin_tarifa(db, pais_id, pendientes)
    if sin_tarifa:
        raise HTTPException(409, {
            "mensaje": ("Hay jornadas trabajadas sin tarifa cargada. Carga la "
                        "comision (o la tarifa del freelance), con su hora "
                        "extra si el dia las tuvo, y vuelve a calcular."),
            "sin_tarifa": sin_tarifa,
        })

    heredados += _absorber(db, nomina)
    # Los ajustes heredados siguen apartados por este corte y no se
    # vuelven a tomar como ajustes de la semana.
    de_otros = {h["ajuste_id"] for h in heredados if h["ajuste_id"]}
    for ajuste_id in de_otros:
        db.get(m.AjusteNomina, ajuste_id).pagado_en_nomina_id = nomina.id

    # Primero lo heredado, que es lo mas viejo: el recibo se lee en
    # orden, la semana del 21 antes que la del 28.
    por_persona: dict[int, list[dict]] = {}
    for h in heredados:
        por_persona.setdefault(h["persona_id"], []).append(h)
    for jornada, a in pendientes:
        pago = pago_de_jornada(db, jornada, a, pais_id)
        pago["jornada_id"] = jornada.id
        por_persona.setdefault(a.persona_id, []).append(pago)

    # Los ajustes de semanas pasadas entran a este corte. Los que ya
    # aparto otro borrador no: dos borradores con fechas de corte
    # distintas podian llevarse el mismo ajuste, y al pagar los dos la
    # persona cobraba la diferencia dos veces. Los heredados ya vienen
    # en su renglon con su semana de origen.
    ajustes = [a for a in db.query(m.AjusteNomina)
               .filter_by(pais_id=pais_id, aplicado_en_nomina_id=None).all()
               if a.pagado_en_nomina_id in (None, nomina.id)
               and a.id not in de_otros]
    for ajuste in ajustes:
        ajuste.pagado_en_nomina_id = nomina.id
    for ajuste in ajustes:
        por_persona.setdefault(ajuste.persona_id, []).append({
            "monto": _d(ajuste.monto), "factor": Decimal("1"), "horas_extra": 0,
            "descripcion": f"Ajuste: {ajuste.motivo}",
            "jornada_id": None, "ajuste_id": ajuste.id})

    # Nadie cobra en negativo. Si lo que se le descuenta pasa de lo que
    # gano esta semana, el renglon queda en cero con un concepto que lo
    # dice, y al pagar el corte ese resto pasa a su siguiente lunes. Con
    # semanas absorbidas la cuenta es de todas juntas: el descuento de la
    # semana del 21 se cobra de lo que gano la del 28.
    en_contra = 0
    for persona_id, conceptos in por_persona.items():
        suma = sum((c["monto"] for c in conceptos), CERO)
        if suma < CERO:
            en_contra += 1
            conceptos.append({
                "monto": -suma, "factor": Decimal("1"), "horas_extra": 0,
                "descripcion": ("Queda en contra: pasa al corte del lunes "
                                f"{corte + timedelta(days=7):%d/%m/%Y}"),
                "jornada_id": None, "saldo_en_contra": True})

    total = CERO
    for persona_id, conceptos in por_persona.items():
        renglon = m.RenglonNomina(nomina_id=nomina.id, persona_id=persona_id)
        db.add(renglon)
        db.flush()
        subtotal = CERO
        for c in conceptos:
            db.add(m.ConceptoNomina(
                renglon_id=renglon.id, persona_id=persona_id,
                jornada_id=c.get("jornada_id"),
                ajuste_id=c.get("ajuste_id"), descripcion=c["descripcion"],
                monto=c["monto"], factor_festivo=c["factor"],
                horas_extra=c["horas_extra"], rol_id=c.get("rol_id"),
                monto_horas_extra=c.get("monto_horas_extra"),
                saldo_en_contra=bool(c.get("saldo_en_contra")),
                semana_origen=c.get("semana_origen")))
            subtotal += c["monto"]
        renglon.total = subtotal
        total += subtotal

    nomina.total = total
    # Columna con zona: el instante, no la hora de pared del servidor.
    nomina.calculada_en = datetime.now(timezone.utc)
    nomina.calculada_por_id = quien_id
    db.flush()
    return {"nomina_id": nomina.id, "fecha_corte": corte.isoformat(),
            "desde": nomina.desde.isoformat(),
            "moneda": pais.moneda_local.value, "total": total,
            "personas": len(por_persona),
            "ajustes_aplicados": len(ajustes),
            "heredados": len(heredados),
            "en_contra": en_contra}


def pagar(db: Session, nomina_id: int, persona_id: int | None = None) -> dict:
    """Marca el corte como pagado. A partir de aqui solo se corrige por ajuste."""
    # Con la fila bloqueada (seccion 98): dos "Marcar pagado" al mismo
    # tiempo --dos pestanas, dos personas de finanzas-- leian los dos
    # "calculada", pasaban los dos, y el saldo en contra se arrastraba
    # dos veces. El segundo espera a que el primero termine y entonces
    # ve "ya estaba pagada".
    nomina = (db.query(m.NominaSemanal)
              .filter(m.NominaSemanal.id == nomina_id)
              .with_for_update().first())
    if not nomina:
        raise HTTPException(404, f"No existe la nomina {nomina_id}")
    if nomina.estatus == m.EstatusNomina.PAGADA:
        raise HTTPException(409, "Esa nomina ya estaba pagada")
    # El que se llevo otro corte se paga desde ese otro (seccion 105).
    if nomina.estatus == m.EstatusNomina.ABSORBIDA:
        raise _absorbido_por(db, nomina)
    if not nomina.renglones:
        raise HTTPException(409, "La nomina no tiene nada que pagar")
    # Un borrador que no cerro porque le falta una tarifa no se paga
    # como si fuera el corte (seccion 101): es el de las 7:00, y lo que
    # llego despues --con tarifa o sin ella-- se quedo fuera porque el
    # recalculo de las 11:00 no pudo salir. La regla es la misma del
    # armado: sin tarifa el corte no sale; se carga y se recalcula.
    if not nomina.lista_en:
        faltan = sin_tarifa_pendiente(db, nomina.pais_id,
                                      excepto_nomina_id=nomina.id)
        if faltan:
            raise HTTPException(409, {
                "mensaje": ("Este corte es el borrador de las 7:00 y no cerró: "
                            "hay días trabajados sin tarifa que se quedaron "
                            "fuera"),
                "que_hacer": ("Carga la tarifa que falta en el Tabulador --la "
                              "del freelance, en su ficha (Personal de "
                              "seguridad → Freelance)-- y recalcula el corte; "
                              "entonces se marca pagado."),
                "sin_tarifa": faltan})

    nomina.estatus = m.EstatusNomina.PAGADA
    # Sin zona, como `lista_en`: la hora de pared del pais del corte.
    nomina.pagada_en = reloj.ahora_en(db.get(m.Pais, nomina.pais_id))
    nomina.pagada_por_id = persona_id

    aplicados, repetidos = 0, []
    for renglon in nomina.renglones:
        for concepto in renglon.conceptos:
            if not concepto.ajuste_id:
                continue
            ajuste = db.get(m.AjusteNomina, concepto.ajuste_id)
            if not ajuste:
                continue
            # Un ajuste que ya se salgo en otro corte no se vuelve a
            # pagar. Es el ultimo candado: si algo se coló hasta aqui,
            # el corte no sale y dice cual.
            if ajuste.aplicado_en_nomina_id not in (None, nomina.id):
                repetidos.append(
                    f"{ajuste.motivo} (ya se pago en la nomina "
                    f"{ajuste.aplicado_en_nomina_id})")
                continue
            ajuste.aplicado_en_nomina_id = nomina.id
            aplicados += 1

    if repetidos:
        raise HTTPException(409, {
            "mensaje": "Este corte trae ajustes que ya se pagaron",
            "que_hacer": "Vuelve a calcular el corte antes de pagarlo.",
            "repetidos": repetidos})

    # Pagado, ya no se recalcula; si nadie lo cerro a las 11:00, queda
    # cerrado ahora.
    if not nomina.lista_en:
        nomina.lista_en = reloj.ahora_en(db.get(m.Pais, nomina.pais_id))

    # Quien quedo en cero porque se le descontaba mas de lo que gano: lo
    # que falta pasa a su siguiente corte, hasta saldarse.
    pasan = 0
    for renglon in nomina.renglones:
        for concepto in renglon.conceptos:
            if not concepto.saldo_en_contra:
                continue
            db.add(m.AjusteNomina(
                persona_id=renglon.persona_id, pais_id=nomina.pais_id,
                concepto=AJUSTE_SALDO, monto=-_d(concepto.monto),
                motivo=("Saldo en contra del corte del lunes "
                        f"{nomina.fecha_corte:%d/%m/%Y}"),
                creado_por_id=persona_id))
            pasan += 1
    db.flush()
    return {"nomina_id": nomina.id, "total": nomina.total,
            "personas": len(nomina.renglones), "ajustes_saldados": aplicados,
            "saldos_en_contra": pasan}


def descartar(db: Session, nomina_id: int) -> dict:
    """Tira un borrador de corte que no se va a pagar.

    Hace falta porque un borrador aparta: mientras exista, sus jornadas
    y sus ajustes no entran a ningun otro corte. Sin forma de tirarlo,
    una corrida "para ver como queda" dejaba a esa gente sin cobrar en
    el corte de verdad, y nada lo avisaba.
    """
    nomina = db.get(m.NominaSemanal, nomina_id)
    if not nomina:
        raise HTTPException(404, f"No existe la nomina {nomina_id}")
    if nomina.estatus == m.EstatusNomina.PAGADA:
        raise HTTPException(409, {
            "mensaje": "Esa nomina ya se pago y no se puede tirar",
            "que_hacer": "Lo que haya que corregir va como ajuste al "
                         "siguiente corte."})
    if nomina.estatus == m.EstatusNomina.ABSORBIDA:
        raise _absorbido_por(db, nomina)
    # Listo a las 11:00 es listo: tirarlo dejaria que el reloj lo volviera
    # a armar con lo que llego despues, que ya es del lunes siguiente.
    if nomina.lista_en:
        raise HTTPException(409, {
            "mensaje": "Ese corte ya cerro a las 11:00 y no se puede tirar",
            "que_hacer": "Se paga como quedo. Lo que haya que corregir va "
                         "como ajuste al siguiente corte."})

    for a in db.query(m.AjusteNomina).filter_by(
            pagado_en_nomina_id=nomina.id).all():
        a.pagado_en_nomina_id = None
    renglones = len(nomina.renglones)
    db.delete(nomina)
    db.flush()
    return {"resultado": "borrador descartado", "nomina_id": nomina_id,
            "renglones": renglones,
            "nota": "Sus jornadas y ajustes vuelven a estar disponibles "
                    "para el siguiente corte."}


# ---------------------------------------------------------------- ajustes

# De que es un ajuste. Importa porque dos ajustes del mismo dia y la
# misma persona pueden ser cosas completamente distintas.
AJUSTE_CORRECCION = "correccion_jornada"   # se pago de mas o de menos ese dia
AJUSTE_VIATICO = "viatico_no_comprobado"   # dinero de la empresa sin comprobar
AJUSTE_MANUAL = "manual"                   # lo captura finanzas a mano
# Lo que quedo en contra en un corte pagado y pasa al siguiente (seccion
# 66). No es una correccion de ningun dia: no entra a `_pagado_de`.
AJUSTE_SALDO = "saldo_en_contra"


def _pagado_de(db: Session, jornada_id: int, persona_id: int) -> Decimal | None:
    """Todo lo que ya salio por esa jornada: el dia y sus correcciones.

    Los ajustes se guardan con `jornada_id = None` en el concepto de
    nomina, asi que sumar solo el concepto del dia dejaba fuera lo que
    ya se corrigio. El efecto era feo: pagado 800, corresponde 1100,
    ajuste de +300; se paga el ajuste; la siguiente corrida vuelve a
    ver 800 contra 1100 y genera otros +300. Cada vez que el servicio
    se movia, 300 mas. Aqui se suma lo que de verdad salio.

    Solo cuentan las correcciones de la jornada. Un descuento por
    viaticos no comprobados salio del mismo bolsillo, pero no es pago
    por el dia: contarlo aqui generaria una "diferencia" a favor que
    devolveria el descuento.
    """
    base = (db.query(m.ConceptoNomina)
            .join(m.RenglonNomina, m.ConceptoNomina.renglon_id == m.RenglonNomina.id)
            .join(m.NominaSemanal, m.RenglonNomina.nomina_id == m.NominaSemanal.id)
            .filter(m.ConceptoNomina.jornada_id == jornada_id,
                    m.RenglonNomina.persona_id == persona_id,
                    m.NominaSemanal.estatus == m.EstatusNomina.PAGADA)
            .first())
    if not base:
        return None

    corregido = (db.query(m.AjusteNomina)
                 .filter(m.AjusteNomina.jornada_id == jornada_id,
                         m.AjusteNomina.persona_id == persona_id,
                         m.AjusteNomina.concepto == AJUSTE_CORRECCION,
                         m.AjusteNomina.aplicado_en_nomina_id.isnot(None))
                 .all())
    return _d(base.monto) + sum((_d(a.monto) for a in corregido), CERO)


def diferencias_del_servicio(db: Session, servicio_id: int,
                             creado_por_id: int | None = None) -> dict:
    """Compara lo pagado contra lo que hoy corresponde y arrastra la diferencia.

    Se corre cuando un servicio vuelve a moverse despues de haberse pagado:
    un dia mal cargado que se corrigio, una jornada cancelada, horas extra
    que no eran. El pago no se toca; la correccion va a la semana siguiente.
    """
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")

    # Solo los ajustes de correccion tapan una nueva correccion. Un
    # descuento de viaticos pendiente es otra cosa y no tiene por que
    # impedir que se corrija lo que se pago por ese dia.
    pendientes = {
        (a.jornada_id, a.persona_id)
        for a in db.query(m.AjusteNomina)
        .filter_by(servicio_id=servicio_id, aplicado_en_nomina_id=None,
                   concepto=AJUSTE_CORRECCION).all()
    }

    generados = []
    # Se parte de lo pagado, no solo de lo asignado (seccion 98): la
    # persona que ya no esta en el dia --la sacaron despues del pago--
    # no aparecia en ninguna asignacion y su pago nunca se reclamaba.
    vistos: set[tuple[int, int]] = set()

    def _corregir(jornada, asignacion, persona, pagado, debido):
        diferencia = debido - pagado
        if diferencia == CERO:
            return
        if (jornada.id, persona.id) in pendientes:
            return          # ya hay un ajuste esperando por esa jornada
        if asignacion is None:
            por_que = f"ya no va en ese dia y se le habian pagado {pagado:,.2f}"
        elif jornada.estatus == m.EstatusJornada.CANCELADA:
            por_que = f"el dia se cancelo y ya se habia pagado {pagado:,.2f}"
        else:
            por_que = f"se pagaron {pagado:,.2f} y corresponden {debido:,.2f}"
        db.add(m.AjusteNomina(
            persona_id=persona.id, pais_id=servicio.pais_id,
            servicio_id=servicio_id, jornada_id=jornada.id,
            concepto=AJUSTE_CORRECCION,
            monto=diferencia, creado_por_id=creado_por_id,
            # Dicho como lo va a leer la persona en su recibo.
            motivo=f"{servicio.folio} {jornada.fecha:%d/%m/%Y}: {por_que}"))
        generados.append({"persona": persona.nombre,
                          "fecha": jornada.fecha.isoformat(),
                          "monto": diferencia})

    for equipo in servicio.equipos:
        for jornada in equipo.jornadas:
            for asignacion in jornada.personal:
                persona = asignacion.persona
                vistos.add((jornada.id, persona.id))
                pagado = _pagado_de(db, jornada.id, persona.id)
                if pagado is None:
                    continue        # todavia no se le paga: se corrige solo

                if jornada.estatus == m.EstatusJornada.CANCELADA:
                    debido = CERO
                else:
                    pago = pago_de_jornada(db, jornada, asignacion,
                                           servicio.pais_id)
                    debido = pago["monto"] if pago else CERO
                _corregir(jornada, asignacion, persona, pagado, debido)

            # Lo pagado por ese dia a quien ya no esta asignado.
            pagados = (db.query(m.RenglonNomina.persona_id)
                       .join(m.ConceptoNomina,
                             m.ConceptoNomina.renglon_id == m.RenglonNomina.id)
                       .join(m.NominaSemanal,
                             m.RenglonNomina.nomina_id == m.NominaSemanal.id)
                       .filter(m.ConceptoNomina.jornada_id == jornada.id,
                               m.NominaSemanal.estatus == m.EstatusNomina.PAGADA)
                       .distinct().all())
            for (persona_id,) in pagados:
                if (jornada.id, persona_id) in vistos:
                    continue
                persona = db.get(m.Persona, persona_id)
                pagado = _pagado_de(db, jornada.id, persona_id)
                if persona is None or pagado is None:
                    continue
                _corregir(jornada, None, persona, pagado, CERO)
    db.flush()
    return {"servicio": servicio.folio, "ajustes_generados": generados}


# ---------------------------------------------------------------- el lunes

def _hay_que_pagar(db: Session, pais_id: int) -> bool:
    """Si hay algo que llevar al corte: dias debidos o ajustes.

    Un ajuste que otro borrador ya aparto no cuenta (seccion 101): el
    corte nuevo no lo va a incluir --`calcular` lo excluye--, y creer
    que si armaba un corte sin renglones que a las 11:00 quedaba listo
    para siempre: no se podia pagar ni tirar.
    """
    if jornadas_pendientes(db, pais_id, limite=1):
        return True
    return (db.query(m.AjusteNomina.id)
            .filter_by(pais_id=pais_id, aplicado_en_nomina_id=None,
                       pagado_en_nomina_id=None)
            .first()) is not None


def reloj_del_lunes(db: Session, ahora: datetime | None = None) -> list[dict]:
    """El corte del lunes, en hora de cada pais (seccion 66).

    Lo llama el beat cada quince minutos y aqui se decide que le toca a
    cada pais: a las 7:00 se arma el borrador; a las 11:00 se recalcula
    por ultima vez y queda listo para pagar. Si el reloj se perdio una
    vuelta, la siguiente lo alcanza --pero solo el mismo lunes: lo que
    llega el martes ya es del lunes que sigue--.

    Un pais sin nada que pagar no arma un corte vacio. Uno al que le
    falta una tarifa no lo arma: la pantalla dice cual falta y finanzas
    lo recalcula en cuanto la carga.

    Al armar el corte de hoy se lleva el de la semana pasada si nadie lo
    pago (seccion 105): eso lo hace `calcular`. Un pais con un corte
    viejo sin pagar y nada nuevo no arma corte: el viejo sigue a la
    vista hasta que se pague.
    """
    hechos = []
    for pais in (db.query(m.Pais).filter(m.Pais.activo.is_(True))
                 .order_by(m.Pais.id).all()):
        local = reloj.ahora_en(pais, ahora)
        if local.weekday() != 0:
            continue
        lunes = local.date()
        if local < datetime.combine(lunes, HORA_BORRADOR):
            continue
        # Dos vueltas encimadas (seccion 105): la segunda espera a que la
        # primera confirme y entonces ve el corte ya armado o ya listo.
        candado_del_pais(db, pais.id)
        nomina = (db.query(m.NominaSemanal)
                  .filter_by(pais_id=pais.id, fecha_corte=lunes).first())
        if nomina and (nomina.estatus != m.EstatusNomina.CALCULADA
                       or nomina.lista_en):
            continue
        cierra = local >= datetime.combine(lunes, HORA_CIERRE)
        if nomina is not None and not cierra:
            continue            # el borrador de las 7:00 ya esta
        if nomina is None and not _hay_que_pagar(db, pais.id):
            continue
        try:
            resultado = calcular(db, pais.id, lunes)
            if not resultado["personas"]:
                # Sin renglones no hay corte (seccion 101): lo que habia
                # a las 7:00 se cancelo o lo aparto otro borrador. Dejarlo
                # listo lo volvia un corte vacio que ensuciaba el
                # historial y no se podia pagar ni tirar.
                vacia = db.get(m.NominaSemanal, resultado["nomina_id"])
                # Los renglones del borrador ya se borraron al recalcular:
                # se vuelven a leer para no borrarlos dos veces.
                db.expire(vacia, ["renglones"])
                db.delete(vacia)
                db.commit()
                hechos.append({"pais": pais.codigo, "resultado": "vacio"})
                continue
            if cierra:
                db.get(m.NominaSemanal, resultado["nomina_id"]).lista_en = local
            db.commit()
        except HTTPException as e:
            db.rollback()
            detalle = e.detail if isinstance(e.detail, dict) else {}
            hechos.append({"pais": pais.codigo, "resultado": "no_salio",
                           "sin_tarifa": len(detalle.get("sin_tarifa", []))})
            continue
        except Exception as error:                        # noqa: BLE001
            # Un pais no tumba al otro (seccion 100): con Mexico reventando
            # por algo que no era un 409, Brasil, que viene despues, se
            # quedaba sin corte en esa vuelta y en todas.
            db.rollback()
            registro.exception("el corte de %s revento", pais.codigo)
            hechos.append({"pais": pais.codigo, "resultado": "error",
                           "error": str(error)[:200]})
            continue
        hechos.append({"pais": pais.codigo, "nomina_id": resultado["nomina_id"],
                       "resultado": "listo" if cierra else "borrador",
                       "total": str(resultado["total"])})
    return hechos


# ---------------------------------------------------------------- lo que se ve

def _servicio(db: Session, cache: dict, servicio_id: int | None):
    if servicio_id is None:
        return None
    if servicio_id not in cache:
        cache[servicio_id] = db.get(m.Servicio, servicio_id)
    return cache[servicio_id]


def _nombre(db: Session, persona_id: int | None) -> str | None:
    persona = db.get(m.Persona, persona_id) if persona_id else None
    return persona.nombre if persona else None


def _iso(valor) -> str | None:
    return valor.isoformat() if valor else None


def armar_detalle(db: Session, filas: list[dict], fecha_corte: date) -> dict:
    """El corte tal como se lee: de donde sale cada peso, por persona y
    por rol (seccion 66).

    `filas` son los conceptos --guardados o calculados al vuelo-- con su
    persona, su jornada o su ajuste. Lo mismo sirve para un corte armado
    y para lo que va juntandose para el lunes que sigue.
    """
    servicios: dict = {}
    grupos: dict = {}
    personas: dict = {}
    por_rol: dict = {}
    pasan = []
    resumen = {"eventual": CERO, "implantado": CERO, "diferencias": CERO,
               "pasan": CERO, "horas_extra": 0}

    for f in filas:
        monto = _d(f["monto"])
        p = personas.setdefault(f["persona_id"], {
            "persona_id": f["persona_id"], "persona": f["persona"],
            "dias": 0, "horas_extra": 0, "diferencias": CERO,
            "total": CERO, "en_contra": CERO, "conceptos": []})
        p["total"] += monto
        jornada, ajuste = f.get("jornada"), f.get("ajuste")
        servicio = (jornada.equipo.servicio if jornada is not None
                    else _servicio(db, servicios,
                                   ajuste.servicio_id if ajuste else None))
        p["conceptos"].append({
            "descripcion": f["descripcion"], "monto": monto,
            "folio": servicio.folio if servicio else None,
            "rol": f.get("rol"), "horas_extra": f.get("horas_extra") or 0,
            "es_ajuste": ajuste is not None,
            "saldo_en_contra": bool(f.get("saldo_en_contra")),
            # De que corte absorbido viene, para que el recibo lo diga
            # (seccion 105). Vacio: de la semana de este corte.
            "semana": _iso(f.get("semana_origen"))})

        if f.get("saldo_en_contra"):
            p["en_contra"] += monto
            resumen["pasan"] += monto
            pasan.append({"persona": f["persona"], "monto": monto})
            continue

        if jornada is not None:
            implantado = servicio.tipo == m.TipoServicio.IMPLANTADO
            p["dias"] += 1
            p["horas_extra"] += f.get("horas_extra") or 0
            resumen["implantado" if implantado else "eventual"] += monto
            resumen["horas_extra"] += f.get("horas_extra") or 0
            g = grupos.setdefault(("servicio", servicio.id), {
                "origen": "implantado" if implantado else "eventual",
                "folio": servicio.folio, "servicio_id": servicio.id,
                "fechas": set(), "personas": set(), "monto": CERO,
                "horas_extra": 0, "monto_horas_extra": CERO})
            g["fechas"].add(jornada.fecha)
            g["personas"].add(f["persona_id"])
            g["monto"] += monto
            g["horas_extra"] += f.get("horas_extra") or 0
            g["monto_horas_extra"] += _d(f.get("monto_horas_extra"))
            fila_rol = por_rol.setdefault(f.get("rol_id") or 0, {
                "rol_id": f.get("rol_id"), "rol": f.get("rol") or "Sin rol",
                "dias": 0, "monto": CERO})
            fila_rol["dias"] += 1
            fila_rol["monto"] += monto
            continue

        # Un ajuste: dice de donde viene.
        p["diferencias"] += monto
        resumen["diferencias"] += monto
        concepto = ajuste.concepto if ajuste else AJUSTE_MANUAL
        if concepto == AJUSTE_CORRECCION and servicio is not None:
            dia = (db.get(m.Jornada, ajuste.jornada_id)
                   if ajuste.jornada_id else None)
            if servicio.tipo == m.TipoServicio.IMPLANTADO and dia:
                clave = ("mes", servicio.id, dia.fecha.year, dia.fecha.month)
                origen = "mes"
            else:
                clave = ("regreso", servicio.id)
                origen = "regreso"
        elif concepto == AJUSTE_VIATICO:
            clave, origen = ("viaticos", servicio.id if servicio else 0), "viaticos"
        elif concepto == AJUSTE_SALDO:
            clave, origen = ("saldo",), "saldo"
        else:
            clave, origen = ("manual",), "manual"
        g = grupos.setdefault(clave, {
            "origen": origen, "folio": servicio.folio if servicio else None,
            "servicio_id": servicio.id if servicio else None,
            "fechas": set(), "personas": set(), "monto": CERO,
            "horas_extra": 0, "monto_horas_extra": CERO})
        if origen == "mes":
            g["anio"], g["mes"] = clave[2], clave[3]
        g["personas"].add(f["persona_id"])
        g["monto"] += monto

    # Por que entra cada grupo, dicho con lo que la pantalla necesita.
    orden = {"eventual": 0, "implantado": 1, "mes": 2, "regreso": 3,
             "viaticos": 4, "manual": 5, "saldo": 6}
    salida = []
    for g in grupos.values():
        servicio = _servicio(db, servicios, g["servicio_id"])
        por_que = {"clave": g["origen"]}
        if g["origen"] == "eventual":
            cierre = (db.query(m.Cierre)
                      .filter_by(servicio_id=servicio.id, contrato_id=None)
                      .first())
            por_que.update({"clave": "visto_bueno",
                            "consultor": _nombre(db, servicio.consultor_id),
                            "fecha": _iso(cierre.enviado_en if cierre else None)})
        elif g["origen"] == "implantado":
            por_que.update({"clave": "dias",
                            "desde": min(g["fechas"]).isoformat(),
                            "hasta": max(g["fechas"]).isoformat()})
        elif g["origen"] == "mes":
            contrato = (db.query(m.ContratoImplantado)
                        .filter_by(servicio_id=servicio.id, anio=g["anio"],
                                   mes=g["mes"]).first())
            cierre = (db.query(m.Cierre).filter_by(contrato_id=contrato.id)
                      .first() if contrato else None)
            por_que.update({"anio": g["anio"], "mes": g["mes"],
                            "fecha": _iso(cierre.enviado_en if cierre else None),
                            "consultor": _nombre(db, servicio.consultor_id)})
        elif g["origen"] == "regreso" and servicio is not None:
            cierre = (db.query(m.Cierre)
                      .filter_by(servicio_id=servicio.id, contrato_id=None)
                      .first())
            por_que["fecha"] = _iso(cierre.enviado_en if cierre else None)
        salida.append({
            "origen": g["origen"], "folio": g["folio"],
            "servicio_id": g["servicio_id"],
            "anio": g.get("anio"), "mes": g.get("mes"),
            "dias": len(g["fechas"]), "personas": len(g["personas"]),
            "monto": g["monto"], "horas_extra": g["horas_extra"],
            "monto_horas_extra": g["monto_horas_extra"],
            "por_que": por_que})
    salida.sort(key=lambda x: (orden[x["origen"]], x["folio"] or "",
                               x.get("anio") or 0, x.get("mes") or 0))

    total = sum((p["total"] for p in personas.values()), CERO)
    return {
        "fecha_corte": fecha_corte.isoformat(),
        "siguiente_lunes": (fecha_corte + timedelta(days=7)).isoformat(),
        "total": total,
        "resumen": {**resumen, "personas": len(personas),
                    "en_contra": len(pasan)},
        "por_origen": salida,
        "pasan": pasan,
        "por_rol": sorted(por_rol.values(), key=lambda x: -x["monto"]),
        "por_persona": sorted(personas.values(),
                              key=lambda x: (x["persona"] or "").lower()),
    }


def _fila(db: Session, r: m.RenglonNomina, c: m.ConceptoNomina) -> dict:
    return {
        "persona_id": r.persona_id, "persona": r.persona.nombre,
        "jornada": db.get(m.Jornada, c.jornada_id) if c.jornada_id else None,
        "ajuste": db.get(m.AjusteNomina, c.ajuste_id) if c.ajuste_id else None,
        "descripcion": c.descripcion, "monto": c.monto,
        "horas_extra": c.horas_extra,
        "monto_horas_extra": c.monto_horas_extra,
        "rol_id": c.rol_id, "rol": c.rol.nombre if c.rol else None,
        "saldo_en_contra": c.saldo_en_contra,
        "semana_origen": c.semana_origen}


def filas_del_corte(db: Session, nomina: m.NominaSemanal) -> list[dict]:
    """Los conceptos guardados de un corte, como los lee `armar_detalle`."""
    return [_fila(db, r, c) for r in nomina.renglones for c in r.conceptos]


def filas_de_un_absorbido(db: Session, nomina: m.NominaSemanal) -> list[dict]:
    """Lo que traia un corte absorbido, leido de donde vive hoy (seccion
    105): sus renglones pasaron al corte que se lo llevo --y quiza de
    ahi a otro-- con su lunes como semana de origen. Un lunes es de un
    solo corte por pais, asi que con eso se vuelve a armar."""
    pares = (db.query(m.RenglonNomina, m.ConceptoNomina)
             .join(m.ConceptoNomina,
                   m.ConceptoNomina.renglon_id == m.RenglonNomina.id)
             .join(m.NominaSemanal,
                   m.RenglonNomina.nomina_id == m.NominaSemanal.id)
             .filter(m.NominaSemanal.pais_id == nomina.pais_id,
                     m.ConceptoNomina.semana_origen == nomina.fecha_corte)
             .order_by(m.RenglonNomina.persona_id, m.ConceptoNomina.id)
             .all())
    return [_fila(db, r, c) for r, c in pares]


def absorbidas_por(db: Session,
                   nomina: m.NominaSemanal) -> list[m.NominaSemanal]:
    """Los cortes que este se llevo, del mas viejo al mas nuevo (seccion
    105): el del 28 trae al del 21; el del 5 trae al del 28 y, por el,
    al del 21. La cadena es lineal, asi que se sigue hasta el final."""
    salida, cola = [], [nomina.id]
    while cola:
        hijas = (db.query(m.NominaSemanal)
                 .filter(m.NominaSemanal.absorbida_por_id.in_(cola)).all())
        salida.extend(hijas)
        cola = [h.id for h in hijas]
    return sorted(salida, key=lambda n: n.fecha_corte)


def vista_previa(db: Session, pais_id: int, fecha_corte: date) -> dict:
    """Lo que va juntandose para el lunes que sigue, sin guardar nada.

    Es el mismo calculo del corte --las mismas tarifas, los mismos
    ajustes, el mismo saldo en contra-- hecho al vuelo. Lo que no tiene
    tarifa no suma: sale aparte, que es lo que detiene el corte.
    """
    filas = []
    pendientes = jornadas_pendientes(db, pais_id)
    # La misma tabla de faltantes que detiene el corte, con que es lo
    # que falta --la tarifa del dia o solo la hora extra-- (seccion 101).
    sin_tarifa = _sin_tarifa(db, pais_id, pendientes)
    for jornada, a in pendientes:
        pago = pago_de_jornada(db, jornada, a, pais_id)
        if not pago:
            continue
        filas.append({"persona_id": a.persona_id, "persona": a.persona.nombre,
                      "jornada": jornada, "ajuste": None,
                      "descripcion": pago["descripcion"], "monto": pago["monto"],
                      "horas_extra": pago["horas_extra"],
                      "monto_horas_extra": pago["monto_horas_extra"],
                      "rol_id": a.rol_id,
                      "rol": a.rol.nombre if a.rol else None})
    for ajuste in (db.query(m.AjusteNomina)
                   .filter_by(pais_id=pais_id, aplicado_en_nomina_id=None,
                              pagado_en_nomina_id=None).all()):
        filas.append({"persona_id": ajuste.persona_id,
                      "persona": ajuste.persona.nombre, "jornada": None,
                      "ajuste": ajuste, "descripcion": f"Ajuste: {ajuste.motivo}",
                      "monto": ajuste.monto})
    # El mismo saldo en contra que pondria el corte.
    sumas: dict = {}
    for f in filas:
        sumas.setdefault(f["persona_id"], [f["persona"], CERO])
        sumas[f["persona_id"]][1] += _d(f["monto"])
    for persona_id, (nombre, suma) in sumas.items():
        if suma < CERO:
            filas.append({"persona_id": persona_id, "persona": nombre,
                          "jornada": None, "ajuste": None,
                          "descripcion": ("Queda en contra: pasa al corte del "
                                          "lunes "
                                          f"{fecha_corte + timedelta(days=7):%d/%m/%Y}"),
                          "monto": -suma, "saldo_en_contra": True})
    detalle = armar_detalle(db, filas, fecha_corte)
    detalle["sin_tarifa"] = sin_tarifa
    return detalle


# Estatus en los que el eventual todavia no entra al corte, y que le falta.
def _que_falta(servicio: m.Servicio, cierre: m.Cierre | None) -> dict:
    if cierre is None:
        terminado = servicio.estatus in (m.EstatusServicio.TERMINADO,
                                         m.EstatusServicio.SIN_VISTO_BUENO,
                                         m.EstatusServicio.CANCELADO)
        return {"clave": "comprobacion" if terminado else "en_curso",
                "hasta": None}
    # El mismo reloj que ve el cierre: regresado por finanzas corre desde
    # el regreso, no desde el plazo original del consultor.
    vigente = limite_vigente(cierre)
    hasta = _iso(vigente[1]) if vigente else None
    if cierre.estatus == m.EstatusCierre.ABIERTO:
        return {"clave": "comprobacion", "hasta": hasta}
    if cierre.estatus == m.EstatusCierre.DEVUELTO_A_OPERACION:
        return {"clave": "regresado", "hasta": hasta}
    if cierre.estatus in (m.EstatusCierre.SIN_VISTO_BUENO,
                          m.EstatusCierre.EN_REVISION_IA):
        return {"clave": "visto_bueno", "hasta": hasta}
    return {"clave": "revision", "hasta": None}


def todavia_no_entra(db: Session, pais_id: int) -> list[dict]:
    """Los eventuales que ya trabajaron y todavia no entran al corte: su
    consultor no ha dado el visto bueno (seccion 66). Con lo que les
    falta y cuanto seria, para que nadie pregunte el lunes por que un
    servicio que ya termino no viene en la nomina."""
    # La misma consulta del corte, al reves (seccion 101): lo terminado
    # del eventual cuyo cierre todavia no va a facturacion, sin cargar
    # todos los cierres ni todos los conceptos pagados de la historia.
    filas = (_terminadas_con_su_gente(db, pais_id)
             .filter(m.Servicio.tipo == m.TipoServicio.EVENTUAL,
                     ~_ya_pagada(),
                     or_(_estatus_del_cierre().is_(None),
                         _estatus_del_cierre().notin_(EN_FACTURACION)))
             .order_by(m.Jornada.fecha, m.Jornada.id, m.AsignacionPersonal.id)
             .all())
    cierres: dict = {}
    for servicio_id in {j.equipo.servicio_id for j, _ in filas}:
        cierres[servicio_id] = (db.query(m.Cierre)
                                .filter_by(servicio_id=servicio_id,
                                           contrato_id=None)
                                .order_by(m.Cierre.id.desc()).first())

    por_servicio: dict = {}
    for j, a in filas:
        servicio = j.equipo.servicio
        cierre = cierres.get(servicio.id)
        fila = por_servicio.setdefault(servicio.id, {
            "servicio_id": servicio.id, "folio": servicio.folio,
            "consultor": _nombre(db, servicio.consultor_id),
            "termino": None, "dias": set(), "personas": set(),
            "monto": CERO, "sin_tarifa": False,
            "que_falta": _que_falta(servicio, cierre)})
        fin = j.fin_real
        if fin and (fila["termino"] is None or fin > fila["termino"]):
            fila["termino"] = fin
        fila["dias"].add(j.fecha)
        fila["personas"].add(a.persona_id)
        pago = pago_de_jornada(db, j, a, pais_id)
        if pago:
            fila["monto"] += pago["monto"]
        else:
            fila["sin_tarifa"] = True

    salida = []
    for f in por_servicio.values():
        salida.append({**f, "termino": _iso(f["termino"]),
                       "dias": len(f["dias"]), "personas": len(f["personas"])})
    return sorted(salida, key=lambda x: x["termino"] or "")


def meses_implantado(db: Session, pais_id: int, ahora: datetime | None = None,
                     meses: int = 3) -> list[dict]:
    """El corte general del mes de cada implantado (seccion 66).

    Cada semana se pagan los dias trabajados; con el visto bueno del mes
    se compara lo pagado contra lo que corresponde y la diferencia se
    paga o se descuenta el lunes siguiente. El mes queda cerrado cuando
    ya se pago todo: sus dias y sus diferencias. Si a alguien no le
    alcanzo, su saldo en contra sigue en sus cortes: es de la persona,
    ya no del mes.
    """
    from app import cierre_mes

    pais = db.get(m.Pais, pais_id)
    local = reloj.ahora_en(pais, ahora)
    hoy = local.date()
    # Un lunes antes de las 11:00 lo que se debe todavia entra hoy.
    entra_hoy = (hoy.weekday() == 0
                 and local < datetime.combine(hoy, HORA_CIERRE))
    anio, mes = hoy.year, hoy.month
    ventana = []
    for _ in range(meses):
        ventana.append((anio, mes))
        anio, mes = (anio, mes - 1) if mes > 1 else (anio - 1, 12)

    contratos = (db.query(m.ContratoImplantado)
                 .join(m.Servicio,
                       m.ContratoImplantado.servicio_id == m.Servicio.id)
                 .filter(m.Servicio.pais_id == pais_id).all())
    pagadas = {n.id: n for n in db.query(m.NominaSemanal)
               .filter_by(pais_id=pais_id,
                          estatus=m.EstatusNomina.PAGADA).all()}
    lunes_que_viene = lunes_de(hoy) + timedelta(days=7)
    lunes_de_hoy = (db.query(m.NominaSemanal)
                    .filter_by(pais_id=pais_id, fecha_corte=lunes_de(hoy))
                    .first())

    salida = []
    for contrato in contratos:
        if (contrato.anio, contrato.mes) not in ventana:
            continue
        servicio = contrato.servicio
        # Todos los dias del mes, los cancelados incluidos: un dia que se
        # pago y despues se cancelo cuenta en lo pagado, y su diferencia
        # es justo la que hay que ver aqui. Sin trabajo en el mes no hay
        # nada que cuadrar.
        todos = cierre_mes._dias(db, contrato)
        dias = [j for j in todos
                if j.estatus == m.EstatusJornada.TERMINADA and j.personal]
        ids = {j.id for j in todos}
        conceptos = (db.query(m.ConceptoNomina, m.RenglonNomina)
                     .join(m.RenglonNomina,
                           m.ConceptoNomina.renglon_id == m.RenglonNomina.id)
                     .filter(m.ConceptoNomina.jornada_id.in_(ids)).all()
                     if ids else [])
        if not dias and not conceptos:
            continue
        pagado = sum((_d(c.monto) for c, r in conceptos
                      if r.nomina_id in pagadas), CERO)
        semanas = len({r.nomina_id for c, r in conceptos
                       if r.nomina_id in pagadas})
        pagados = {(c.jornada_id, c.persona_id) for c, r in conceptos
                   if r.nomina_id in pagadas}
        sin_pagar = sum(1 for j in dias for a in j.personal
                        if (j.id, a.persona_id) not in pagados)
        ajustes = (db.query(m.AjusteNomina)
                   .filter(m.AjusteNomina.jornada_id.in_(ids),
                           m.AjusteNomina.concepto == AJUSTE_CORRECCION)
                   .order_by(m.AjusteNomina.id).all())
        cierre = cierre_mes.cierre_de(db, contrato)
        ultimo = date(contrato.anio, contrato.mes,
                      calendar.monthrange(contrato.anio, contrato.mes)[1])
        visto = bool(cierre and cierre.estatus in EN_FACTURACION)

        por_pagar = [a for a in ajustes if a.aplicado_en_nomina_id not in pagadas]
        entra_el = None
        if visto and (por_pagar or sin_pagar):
            estado = "por_cerrar"
            apartado = next((a.pagado_en_nomina_id for a in por_pagar
                             if a.pagado_en_nomina_id), None)
            if apartado:
                entra_el = db.get(m.NominaSemanal, apartado).fecha_corte
            elif lunes_de_hoy and lunes_de_hoy.estatus != m.EstatusNomina.PAGADA \
                    and not lunes_de_hoy.lista_en:
                entra_el = lunes_de_hoy.fecha_corte
            elif lunes_de_hoy is None and entra_hoy:
                entra_el = hoy
            else:
                entra_el = lunes_que_viene
        elif visto:
            estado = "cerrado"
        elif hoy > ultimo:
            estado = "sin_visto_bueno"
        else:
            estado = "en_curso"

        cerrado_en = None
        if estado == "cerrado":
            # El dia que se pago su ultima diferencia; sin diferencias, el
            # de su visto bueno.
            fechas = [pagadas[a.aplicado_en_nomina_id].pagada_en
                      for a in ajustes
                      if a.aplicado_en_nomina_id in pagadas
                      and pagadas[a.aplicado_en_nomina_id].pagada_en]
            cerrado_en = max(fechas) if fechas else cierre.enviado_en

        diferencia = sum((_d(a.monto) for a in ajustes), CERO)
        salida.append({
            "contrato_id": contrato.id, "servicio_id": servicio.id,
            "folio": servicio.folio, "anio": contrato.anio,
            "mes": contrato.mes, "estado": estado,
            "consultor": _nombre(db, servicio.consultor_id),
            "visto_bueno": _iso(cierre.enviado_en if visto else None),
            "limite": _iso(cierre.limite_consultor
                           if cierre and not visto else None),
            "entra_el": _iso(entra_el), "cerrado_en": _iso(cerrado_en),
            "semanas_pagadas": semanas, "dias_sin_pagar": sin_pagar,
            "pagado": pagado,
            "corresponde": pagado + diferencia if visto else None,
            "diferencia": diferencia if visto else None,
            "diferencias": [_diferencia_del_dia(db, a, pagadas)
                            for a in ajustes],
        })
    orden = {"por_cerrar": 0, "sin_visto_bueno": 1, "en_curso": 2,
             "cerrado": 3}
    salida.sort(key=lambda x: (orden[x["estado"]], -x["anio"], -x["mes"],
                               x["folio"]))
    return salida


def _diferencia_del_dia(db: Session, a: m.AjusteNomina, pagadas: dict) -> dict:
    """Una diferencia del mes, dicha con lo que la pantalla necesita: de
    quien, de que dia y si ese dia se cancelo despues de pagarse."""
    dia = db.get(m.Jornada, a.jornada_id) if a.jornada_id else None
    return {"persona": a.persona.nombre,
            "fecha": _iso(dia.fecha if dia else None),
            "monto": a.monto, "motivo": a.motivo,
            "cancelado": bool(dia and dia.estatus == m.EstatusJornada.CANCELADA),
            "pagada": a.aplicado_en_nomina_id in pagadas}


def corte_pendiente(db: Session, pais_id: int,
                    lunes: date) -> m.NominaSemanal | None:
    """El corte mas viejo del pais que quedo listo y nadie pago, de un
    lunes anterior a este (seccion 105, decision 11). Sigue a la vista
    hasta pagarse: un martes, un jueves. Al armarse el corte de un lunes
    nuevo se lo lleva, asi que a lo mas hay uno."""
    return (db.query(m.NominaSemanal)
            .filter(m.NominaSemanal.pais_id == pais_id,
                    m.NominaSemanal.fecha_corte < lunes,
                    m.NominaSemanal.estatus == m.EstatusNomina.CALCULADA,
                    m.NominaSemanal.lista_en.isnot(None))
            .order_by(m.NominaSemanal.fecha_corte).first())


def semana(db: Session, pais_id: int, ahora: datetime | None = None) -> dict:
    """La pestana del personal: el corte de este lunes, o lo que va para
    el siguiente, y lo que todavia no entra (seccion 66).

    Desde la seccion 105: si no hay corte de este lunes pero quedo uno
    listo sin pagar de un lunes anterior, la pestana es ese, con sus
    botones de pagar; y mientras sea lunes y el corte de hoy no exista,
    ofrece armarlo a mano, tambien despues de las 11:00.
    """
    pais = db.get(m.Pais, pais_id)
    if not pais:
        raise HTTPException(404, f"No existe el pais {pais_id}")
    local = reloj.ahora_en(pais, ahora)
    lunes = lunes_de(local.date())
    nomina = (db.query(m.NominaSemanal)
              .filter_by(pais_id=pais_id, fecha_corte=lunes).first())
    pendiente = None
    if nomina is None or nomina.estatus != m.EstatusNomina.CALCULADA:
        pendiente = corte_pendiente(db, pais_id, lunes)
    # El reloj ya debio armar el corte de hoy y no esta: no corrio, o
    # fallo por una tarifa. Mientras sea lunes se puede armar a mano, y
    # despues de las 11:00 tambien (el corte de hoy no se pierde por un
    # reloj caido). Sin nada que pagar no hay corte que armar.
    armar_hoy = (nomina is None and local.weekday() == 0
                 and local >= datetime.combine(lunes, HORA_BORRADOR)
                 and _hay_que_pagar(db, pais_id))

    corte = None
    no_salio = False
    falta_hoy: list[dict] = []
    if nomina and nomina.estatus == m.EstatusNomina.CALCULADA:
        corte = {**armar_detalle(db, filas_del_corte(db, nomina), lunes),
                 **ficha(db, nomina), "pendiente": False}
        proximo = None
        if not nomina.lista_en:
            # El borrador de las 7:00 que el reloj no puede cerrar
            # (seccion 101): entre las 7:00 y las 11:00 llego un dia sin
            # tarifa, el recalculo de las 11:00 falla y vuelve a fallar
            # cada quince minutos, y la pantalla ensenaba el borrador
            # como si nada. Aqui va la tabla de lo que falta --lo que
            # veria ese recalculo--, y pasada la hora del cierre se dice
            # que no salio.
            corte["sin_tarifa"] = sin_tarifa_pendiente(
                db, pais_id, excepto_nomina_id=nomina.id)
            no_salio = bool(corte["sin_tarifa"]) and (
                local >= datetime.combine(lunes, HORA_CIERRE))
    elif pendiente is not None:
        # El corte listo de un lunes anterior que nadie pago (seccion
        # 104): sigue aqui, con sus botones, hasta que se pague. Lo que
        # va juntandose no se ensena aparte: entra al corte de hoy en
        # cuanto se arme, y ese se lleva a este.
        corte = {**armar_detalle(db, filas_del_corte(db, pendiente),
                                 pendiente.fecha_corte),
                 **ficha(db, pendiente), "pendiente": True}
        proximo = None
        if armar_hoy:
            falta_hoy = sin_tarifa_pendiente(db, pais_id)
    else:
        # Sin corte de este lunes que pagar: lo que va juntandose. Es para
        # este mismo lunes antes de las 11:00, o si el reloj no lo pudo
        # armar y finanzas todavia puede; para el que sigue si el de hoy
        # ya se pago o ya paso la hora --lo que llega despues de las 11:00
        # espera al lunes siguiente--.
        antes = local < datetime.combine(lunes, HORA_CIERRE)
        para = lunes if (nomina is None and antes) else lunes + timedelta(days=7)
        proximo = vista_previa(db, pais_id, para)
        if (nomina is None and local.weekday() == 0
                and local >= datetime.combine(lunes, HORA_BORRADOR)):
            # El reloj ya debio armarlo y no pudo: casi siempre es una
            # tarifa. Se ensena lo de este lunes, que es lo que se arma.
            hoy = proximo if para == lunes else vista_previa(db, pais_id, lunes)
            no_salio = bool(hoy["sin_tarifa"]) or (
                antes and bool(hoy["por_persona"]))
            if no_salio:
                proximo = hoy
        if armar_hoy:
            falta_hoy = proximo["sin_tarifa"]

    ultimo = (db.query(m.NominaSemanal)
              .filter_by(pais_id=pais_id, estatus=m.EstatusNomina.PAGADA)
              .order_by(m.NominaSemanal.fecha_corte.desc()).first())
    return {
        "ahora": local.isoformat(),
        "lunes": lunes.isoformat(),
        "es_lunes": local.weekday() == 0,
        "horario": {"borrador": HORA_BORRADOR.strftime("%H:%M"),
                    "cierre": HORA_CIERRE.strftime("%H:%M"),
                    "pago": HORA_PAGO.strftime("%H:%M")},
        "moneda": pais.moneda_local.value,
        "corte": corte,
        "proximo": proximo,
        "no_salio": no_salio,
        # "Armar el corte de hoy" (seccion 105) y lo que le faltaria.
        "armar_hoy": armar_hoy,
        "falta_hoy": falta_hoy,
        "todavia_no": todavia_no_entra(db, pais_id),
        "ultimo_pagado": ({"nomina_id": ultimo.id,
                           "fecha_corte": ultimo.fecha_corte.isoformat(),
                           "total": ultimo.total,
                           "personas": len(ultimo.renglones),
                           "pagada_en": _iso(ultimo.pagada_en)}
                          if ultimo else None),
    }


def ficha(db: Session, nomina: m.NominaSemanal) -> dict:
    """Lo que dice la cabeza de un corte: su estado y quien lo armo, y
    desde la seccion 105 que semanas trae y quien se lo llevo."""
    if nomina.estatus == m.EstatusNomina.PAGADA:
        estado = "pagado"
    elif nomina.estatus == m.EstatusNomina.ABSORBIDA:
        estado = "absorbido"
    elif nomina.lista_en:
        estado = "listo"
    else:
        estado = "borrador"
    otro = (db.get(m.NominaSemanal, nomina.absorbida_por_id)
            if nomina.absorbida_por_id else None)
    return {"nomina_id": nomina.id, "estado": estado,
            "estatus": nomina.estatus.value,
            "moneda": nomina.moneda.value,
            "calculada_en": _iso(nomina.calculada_en),
            "calculada_por": _nombre(db, nomina.calculada_por_id),
            "lista_en": _iso(nomina.lista_en),
            "pagada_en": _iso(nomina.pagada_en),
            "pagada_por": _nombre(db, nomina.pagada_por_id),
            # Desde que lunes cubre y que semanas se llevo: "corte del 28,
            # incluye la semana del 21".
            "desde": _iso(nomina.desde),
            "semanas": [_iso(n.fecha_corte) for n in absorbidas_por(db, nomina)],
            "absorbida_por": ({"nomina_id": otro.id,
                               "fecha_corte": _iso(otro.fecha_corte)}
                              if otro else None)}

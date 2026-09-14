"""Nomina semanal del personal de seguridad.

Se paga los lunes despues de mediodia. El corte toma todo lo que ya va
camino a facturacion y todavia no se ha pagado.

La regla que le da forma a todo el modulo: el dinero ya salio no se
reabre. Si un servicio se regresa y cambia despues del pago, la
diferencia viaja como ajuste a la nomina siguiente, con signo.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app.cierre import _horas_extra, factor_festivo

CERO = Decimal("0")

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
    persona = asignacion.persona
    if persona.es_freelance:
        return bool(db.query(m.TarifaFreelance)
                    .filter_by(persona_id=persona.id,
                               modalidad_id=modalidad_id).first())
    if not asignacion.rol_id:
        return False        # sin rol no hay tarifa que buscar
    return bool(db.query(m.ComisionPersonal)
                .filter_by(pais_id=pais_id, perfil_id=asignacion.rol_id,
                           tipo_servicio=_tipo_de(asignacion),
                           modalidad_id=modalidad_id).first())


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
        base, hora_extra = (_d(tarifa.costo),
                            _d(tarifa.costo_hora_extra)) if tarifa else (None, CERO)
        fuente = "tarifa freelance"
    else:
        comision = None
        if asignacion.rol_id:
            comision = (db.query(m.ComisionPersonal)
                        .filter_by(pais_id=pais_id, perfil_id=asignacion.rol_id,
                                   tipo_servicio=_tipo_de(asignacion),
                                   modalidad_id=jornada.modalidad_id).first())
        base, hora_extra = (_d(comision.monto),
                            _d(comision.monto_hora_extra)) if comision else (None, CERO)
        fuente = "tabulador de comisiones"

    if base is None:
        # Sin tarifa no se inventa un monto: se reporta para que lo carguen.
        return None

    factor = factor_festivo(db, pais_id, jornada.fecha)
    extras = _horas_extra(jornada)
    monto = base * factor + hora_extra * extras * factor

    modalidad = jornada.modalidad.codigo.value
    partes = [f"{jornada.fecha.isoformat()} {modalidad}"]
    # El rol va en la descripcion porque es lo que explica el monto: dos
    # dias iguales con distinto rol se pagan distinto, y un recibo que no
    # lo dice se lee como un error de la empresa.
    if asignacion.rol:
        partes.append(asignacion.rol.nombre)
    if extras:
        partes.append(f"{extras} h extra")
    if factor > 1:
        partes.append(f"festivo x{factor.normalize()}")

    return {"monto": monto, "factor": factor, "horas_extra": extras,
            "rol_id": asignacion.rol_id,
            "descripcion": " · ".join(partes), "fuente": fuente}


# ---------------------------------------------------------------- que entra

def jornadas_pendientes(db: Session,
                        pais_id: int) -> list[tuple[m.Jornada,
                                                    m.AsignacionPersonal]]:
    """Pares (jornada, persona) que se deben y no se han pagado.

    El eventual entra cuando su cierre ya va camino a facturacion. El
    implantado entra por dia trabajado, sin esperar al cierre mensual: su
    contrato se factura al mes, pero su gente cobra cada semana. Al cerrar
    el mes se revisa el periodo completo y lo que salga distinto se
    arrastra como ajuste (ver diferencias_del_servicio).
    """
    ya_pagadas = {
        (c.jornada_id, r.persona_id)
        for c, r in db.query(m.ConceptoNomina, m.RenglonNomina)
        .join(m.RenglonNomina, m.ConceptoNomina.renglon_id == m.RenglonNomina.id)
        .filter(m.ConceptoNomina.jornada_id.isnot(None)).all()
    }

    cierres = {c.servicio_id: c.estatus for c in db.query(m.Cierre).all()}

    filas = (db.query(m.Jornada)
             .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
             .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
             .filter(m.Servicio.pais_id == pais_id,
                     m.Jornada.estatus == m.EstatusJornada.TERMINADA)
             .order_by(m.Jornada.fecha).all())

    pendientes = []
    for j in filas:
        servicio = j.equipo.servicio
        if servicio.tipo != m.TipoServicio.IMPLANTADO:
            if cierres.get(servicio.id) not in EN_FACTURACION:
                continue
        for a in j.personal:
            if (j.id, a.persona_id) in ya_pagadas:
                continue
            pendientes.append((j, a))
    return pendientes


# ---------------------------------------------------------------- calculo

def calcular(db: Session, pais_id: int, fecha_corte: date | None = None) -> dict:
    """Arma (o rearma) el corte de la semana. No paga: deja la propuesta."""
    pais = db.get(m.Pais, pais_id)
    if not pais:
        raise HTTPException(404, f"No existe el pais {pais_id}")
    corte = lunes_de(fecha_corte)

    nomina = (db.query(m.NominaSemanal)
              .filter_by(pais_id=pais_id, fecha_corte=corte).first())
    if nomina and nomina.estatus == m.EstatusNomina.PAGADA:
        raise HTTPException(409, {
            "mensaje": "Esa nomina ya se pago; lo que cambie va como ajuste "
                       "a la siguiente",
            "nomina_id": nomina.id})
    if nomina:
        # Recalcular es rehacerla: mientras no se pague, no hay nada que cuidar.
        for r in list(nomina.renglones):
            db.delete(r)
        db.flush()
    else:
        nomina = m.NominaSemanal(pais_id=pais_id, fecha_corte=corte,
                                 moneda=pais.moneda_local)
        db.add(nomina)
        db.flush()

    # No se filtra por fecha: lo que manda es que la jornada este
    # terminada y su servicio ya vaya a facturacion. Una jornada no puede
    # estar terminada sin haber ocurrido.
    pendientes = jornadas_pendientes(db, pais_id)

    # Antes de armar nada: si algo no tiene tarifa, el corte no sale.
    # Pagar de menos a alguien que trabajo es peor que retrasar el corte,
    # y dejarlo fuera en silencio seria justo eso.
    sin_tarifa = [
        {"persona": a.persona.nombre,
         "fecha": jornada.fecha.isoformat(),
         "modalidad": jornada.modalidad.codigo.value,
         "rol": a.rol.nombre if a.rol else None,
         "tipo": "freelance" if a.persona.es_freelance else "de planta"}
        for jornada, a in pendientes
        if not hay_tarifa(db, a, jornada.modalidad_id, pais_id)
    ]
    if sin_tarifa:
        raise HTTPException(409, {
            "mensaje": ("Hay jornadas trabajadas sin tarifa cargada. Carga la "
                        "comision (o la tarifa del freelance) y vuelve a "
                        "calcular."),
            "sin_tarifa": sin_tarifa,
        })

    por_persona: dict[int, list[dict]] = {}
    for jornada, a in pendientes:
        pago = pago_de_jornada(db, jornada, a, pais_id)
        pago["jornada_id"] = jornada.id
        por_persona.setdefault(a.persona_id, []).append(pago)

    # Los ajustes de semanas pasadas entran a este corte.
    ajustes = (db.query(m.AjusteNomina)
               .filter_by(pais_id=pais_id, aplicado_en_nomina_id=None).all())
    for ajuste in ajustes:
        por_persona.setdefault(ajuste.persona_id, []).append({
            "monto": _d(ajuste.monto), "factor": Decimal("1"), "horas_extra": 0,
            "descripcion": f"Ajuste: {ajuste.motivo}",
            "jornada_id": None, "ajuste_id": ajuste.id})

    total = CERO
    for persona_id, conceptos in por_persona.items():
        renglon = m.RenglonNomina(nomina_id=nomina.id, persona_id=persona_id)
        db.add(renglon)
        db.flush()
        subtotal = CERO
        for c in conceptos:
            db.add(m.ConceptoNomina(
                renglon_id=renglon.id, jornada_id=c.get("jornada_id"),
                ajuste_id=c.get("ajuste_id"), descripcion=c["descripcion"],
                monto=c["monto"], factor_festivo=c["factor"],
                horas_extra=c["horas_extra"], rol_id=c.get("rol_id")))
            subtotal += c["monto"]
        renglon.total = subtotal
        total += subtotal

    nomina.total = total
    nomina.calculada_en = datetime.now()
    db.flush()
    return {"nomina_id": nomina.id, "fecha_corte": corte.isoformat(),
            "moneda": pais.moneda_local.value, "total": total,
            "personas": len(por_persona),
            "ajustes_aplicados": len(ajustes)}


def pagar(db: Session, nomina_id: int, persona_id: int | None = None) -> dict:
    """Marca el corte como pagado. A partir de aqui solo se corrige por ajuste."""
    nomina = db.get(m.NominaSemanal, nomina_id)
    if not nomina:
        raise HTTPException(404, f"No existe la nomina {nomina_id}")
    if nomina.estatus == m.EstatusNomina.PAGADA:
        raise HTTPException(409, "Esa nomina ya estaba pagada")
    if not nomina.renglones:
        raise HTTPException(409, "La nomina no tiene nada que pagar")

    nomina.estatus = m.EstatusNomina.PAGADA
    nomina.pagada_en = datetime.now()
    nomina.pagada_por_id = persona_id

    aplicados = 0
    for renglon in nomina.renglones:
        for concepto in renglon.conceptos:
            if concepto.ajuste_id:
                ajuste = db.get(m.AjusteNomina, concepto.ajuste_id)
                if ajuste:
                    ajuste.aplicado_en_nomina_id = nomina.id
                    aplicados += 1
    db.flush()
    return {"nomina_id": nomina.id, "total": nomina.total,
            "personas": len(nomina.renglones), "ajustes_saldados": aplicados}


# ---------------------------------------------------------------- ajustes

def _pagado_de(db: Session, jornada_id: int, persona_id: int) -> Decimal | None:
    """Lo que ya se le pago por esa jornada, si la nomina salio."""
    fila = (db.query(m.ConceptoNomina)
            .join(m.RenglonNomina, m.ConceptoNomina.renglon_id == m.RenglonNomina.id)
            .join(m.NominaSemanal, m.RenglonNomina.nomina_id == m.NominaSemanal.id)
            .filter(m.ConceptoNomina.jornada_id == jornada_id,
                    m.RenglonNomina.persona_id == persona_id,
                    m.NominaSemanal.estatus == m.EstatusNomina.PAGADA)
            .first())
    return _d(fila.monto) if fila else None


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

    pendientes = {
        (a.jornada_id, a.persona_id)
        for a in db.query(m.AjusteNomina)
        .filter_by(servicio_id=servicio_id, aplicado_en_nomina_id=None).all()
    }

    generados = []
    for equipo in servicio.equipos:
        for jornada in equipo.jornadas:
            for asignacion in jornada.personal:
                persona = asignacion.persona
                pagado = _pagado_de(db, jornada.id, persona.id)
                if pagado is None:
                    continue        # todavia no se le paga: se corrige solo

                if jornada.estatus == m.EstatusJornada.CANCELADA:
                    debido = CERO
                else:
                    pago = pago_de_jornada(db, jornada, asignacion,
                                           servicio.pais_id)
                    debido = pago["monto"] if pago else CERO

                diferencia = debido - pagado
                if diferencia == CERO:
                    continue
                if (jornada.id, persona.id) in pendientes:
                    continue        # ya hay un ajuste esperando por esa jornada

                ajuste = m.AjusteNomina(
                    persona_id=persona.id, pais_id=servicio.pais_id,
                    servicio_id=servicio_id, jornada_id=jornada.id,
                    monto=diferencia, creado_por_id=creado_por_id,
                    motivo=(f"{servicio.folio} {jornada.fecha.isoformat()}: "
                            f"se pago {pagado}, corresponde {debido}"))
                db.add(ajuste)
                generados.append({"persona": persona.nombre,
                                  "fecha": jornada.fecha.isoformat(),
                                  "monto": diferencia})
    db.flush()
    return {"servicio": servicio.folio, "ajustes_generados": generados}

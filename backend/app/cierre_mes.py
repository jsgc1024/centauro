# -*- coding: utf-8 -*-
"""El cierre por mes del implantado.

Decision de Salvador, 22 de septiembre (PROPUESTA_CIERRE_24H.md, regla
8); sesion 2 de tres. El implantado nunca termina: cuando cierra un mes,
el siguiente ya esta abierto. Asi que la cadena de dos relojes no la
recorre el servicio sino el mes de contrato:

* **T0** es el cierre del ultimo dia trabajado del mes: la hora real de
  termino, o la firma si se cerro tarde --un plazo que nace vencido no
  es un plazo--. Todos los viaticos del mes vencen en T0 + 24 h; cerrar
  cada dia ya no abre plazo. El del relevado corre desde su relevo.
* **T1** llega al vencer ese plazo, o antes si todo el dinero del mes ya
  cerro: el consultor tiene 24 h para el visto bueno. Lo mueve la misma
  tarea de cada cinco minutos que mueve al eventual.
* **El visto bueno** manda la factura del mes, a los precios del
  contrato. Finanzas valida y cierra el mes; si el visto bueno fue en
  plazo se detona la comision del consultor por ese mes.

Un cierre por mes, en la misma tabla que el del eventual (camino A,
decision del 23 sep): el eventual sigue con uno por servicio y su camino
no cambia. El estatus del servicio tampoco se mueve --sigue en la calle
con el mes que corre--: la fase la lleva cada mes.

Un dia que se reabre o que entra despues de T0 deshace el termino del
mes mientras no haya visto bueno; despues ya no, porque la factura del
mes salio con esos dias. Cancelar el implantado cierra, con lo
trabajado, cada mes que tenga algo que cerrar.
"""
import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import auditoria
from app import cierre as motor
from app import comisiones
from app import facturacion
from app import implantado as motor_implantado
from app import models as m
from app import nomina
from app import reloj
from app import viaticos as motor_viaticos
from app.revisor import (AVISO, GRAVE, INFO, observaciones_del_dinero,
                         observaciones_del_plazo)

CERO = Decimal("0")

# Con el visto bueno dado, la factura del mes ya salio o esta por salir:
# ya no se reabre un dia ni entra uno nuevo. Los mismos del eventual.
CON_VISTO_BUENO = (m.EstatusCierre.EN_REVISION_IA,
                   m.EstatusCierre.ENVIADO_FINANZAS,
                   m.EstatusCierre.APROBADO, m.EstatusCierre.FACTURADO)


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def periodo(contrato: m.ContratoImplantado) -> str:
    return f"{contrato.mes:02d}/{contrato.anio}"


def contrato_o_404(db: Session, contrato_id: int) -> m.ContratoImplantado:
    contrato = db.get(m.ContratoImplantado, contrato_id)
    if not contrato:
        raise HTTPException(404, f"No existe el contrato {contrato_id}")
    return contrato


def contrato_de(db: Session, jornada: m.Jornada | None
                ) -> m.ContratoImplantado | None:
    """El mes de contrato de un dia del implantado, si lo tiene."""
    if jornada is None or jornada.equipo is None:
        return None
    return (db.query(m.ContratoImplantado)
            .filter_by(servicio_id=jornada.equipo.servicio_id,
                       anio=jornada.fecha.year, mes=jornada.fecha.month)
            .first())


def cierre_de(db: Session, contrato: m.ContratoImplantado | None
              ) -> m.Cierre | None:
    if contrato is None:
        return None
    return db.query(m.Cierre).filter_by(contrato_id=contrato.id).first()


def _dias(db: Session, contrato: m.ContratoImplantado) -> list:
    """Todos los dias del mes, los cancelados incluidos, leidos de la base.

    De la base y no de la lista del equipo: quien llama acaba de cancelar
    o de borrar un dia, y la lista cargada en memoria todavia lo tendria.
    """
    ultimo = calendar.monthrange(contrato.anio, contrato.mes)[1]
    return (db.query(m.Jornada)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == contrato.servicio_id,
                    m.Jornada.fecha >= date(contrato.anio, contrato.mes, 1),
                    m.Jornada.fecha <= date(contrato.anio, contrato.mes,
                                            ultimo))
            .order_by(m.Jornada.fecha).all())


def viaticos_del_mes(db: Session, contrato: m.ContratoImplantado) -> list:
    """Todo el dinero del mes: el de sus dias --tambien el de quien cubrio
    uno-- y el de los dias que se cancelaron con el dinero ya afuera."""
    ids = [j.id for j in _dias(db, contrato)]
    if not ids:
        return []
    return (db.query(m.AsignacionViatico)
            .filter(m.AsignacionViatico.jornada_id.in_(ids)).all())


def viaticos_abiertos(db: Session, contrato: m.ContratoImplantado) -> int:
    """Cuantos viaticos del mes siguen sin cerrar."""
    return sum(1 for v in viaticos_del_mes(db, contrato)
               if v.estatus not in motor.VIATICO_RESUELTO)


# ------------------------------------------------------------ T0 del mes

def abrir(db: Session, contrato: m.ContratoImplantado,
          abierto_en: datetime | None = None,
          motivo: str = "termino") -> m.Cierre:
    """El primer reloj del mes: las 24 horas del personal.

    Todos los viaticos del mes reciben el mismo limite, T0 + 24 h. Se
    respeta el que ya tenga uno --el del relevado, que corre desde su
    relevo-- y el dinero que ya cerro, se devolvio o se cancelo no recibe
    plazo: ya no esta afuera. Solo escribe; guarda quien llama.
    """
    existente = cierre_de(db, contrato)
    if existente:
        return existente

    # En hora del pais del servicio, como el eventual: de este plazo
    # depende la comision del consultor.
    momento = reloj.ahora_del_servicio(db, contrato.servicio, abierto_en)
    hasta = momento + timedelta(hours=motor.HORAS_PERSONAL)
    cierre = m.Cierre(
        servicio_id=contrato.servicio_id, contrato_id=contrato.id,
        abierto_en=momento, comprobacion_hasta=hasta,
        limite_consultor=hasta + timedelta(hours=motor.HORAS_CONSULTOR),
        motivo_apertura=motivo)
    db.add(cierre)

    limite = motor_viaticos.limite_de_comprobacion(momento)
    for viatico in viaticos_del_mes(db, contrato):
        if (viatico.limite_comprobacion
                or viatico.estatus in motor.VIATICO_RESUELTO):
            continue
        viatico.limite_comprobacion = limite
    db.flush()
    return cierre


def terminar_si_cerro_el_mes(db: Session,
                             contrato: m.ContratoImplantado | None,
                             registrado: datetime | None = None
                             ) -> m.Cierre | None:
    """Si al mes ya no le queda dia por trabajar, arranca su cierre.

    Se llama al cerrar un dia --desde la app o a mano--, al cancelar uno
    y desde la tarea de cada cinco minutos: lo que importa es que el mes
    quedo completo, no por donde. Un dia cancelado no es pendiente.

    T0 es la hora de termino del ultimo dia trabajado o `registrado`, lo
    que sea despues: un dia firmado tarde no hace nacer vencido el plazo
    (decision 4 de la propuesta). Sin dias trabajados ni dinero que haya
    salido no hay nada que cerrar, y no arranca ningun reloj.
    """
    if contrato is None or cierre_de(db, contrato):
        return None

    # Quien llama acaba de mover un dia y todavia no guarda: sin esto la
    # cuenta de abajo no lo ve. Es el mismo caso del eventual, ver
    # `operacion.terminar_si_cerro_el_ultimo_dia`.
    db.flush()
    dias = _dias(db, contrato)
    if any(j.estatus not in (m.EstatusJornada.TERMINADA,
                             m.EstatusJornada.CANCELADA) for j in dias):
        return None
    trabajados = [j for j in dias if j.estatus == m.EstatusJornada.TERMINADA]
    salio = [v for v in viaticos_del_mes(db, contrato)
             if v.estatus != m.EstatusViatico.CANCELADO]
    if not trabajados and not salio:
        return None

    momentos = [j.fin_real for j in trabajados if j.fin_real]
    if registrado:
        momentos.append(registrado)
    return abrir(db, contrato, max(momentos) if momentos else None)


def abrir_los_que_terminaron(db: Session,
                             ahora: datetime | None = None) -> list[str]:
    """La red de la tarea de cada cinco minutos.

    El mes que quedo completo sin que el cierre de un dia lo disparara
    --se cancelaron o se borraron sus ultimos dias-- arranca aqui su
    cierre, con T0 = ahora. Mira solo el mes en curso y el anterior, los
    que no tienen cierre: un mes viejo sin nada que cerrar no se vuelve a
    revisar cada cinco minutos para siempre. Devuelve los que abrio.
    """
    referencia = (ahora or datetime.now()).date()
    anterior = (referencia.replace(day=1) - timedelta(days=1))
    desde = anterior.year * 100 + anterior.month
    hasta = referencia.year * 100 + referencia.month
    clave = m.ContratoImplantado.anio * 100 + m.ContratoImplantado.mes
    candidatos = (db.query(m.ContratoImplantado)
                  .outerjoin(m.Cierre,
                             m.Cierre.contrato_id == m.ContratoImplantado.id)
                  .filter(m.Cierre.id.is_(None), clave >= desde,
                          clave <= hasta)
                  .all())
    abiertos = []
    for contrato in candidatos:
        momento = reloj.ahora_del_servicio(db, contrato.servicio, ahora)
        if terminar_si_cerro_el_mes(db, contrato, registrado=momento):
            abiertos.append(f"{contrato.servicio.folio} {periodo(contrato)}")
    db.commit()
    return abiertos


def al_cancelar(db: Session, servicio: m.Servicio) -> list[m.Cierre]:
    """Cancelar el implantado es un termino para cada mes con algo que
    cerrar (regla 11 de la propuesta).

    T0 es el momento de cancelar: los viaticos del mes que salieron
    reciben su plazo y el consultor revisa el mes cancelado, que se
    factura con lo trabajado. Los meses sin dias trabajados ni dinero
    afuera --los que ya estaban abiertos para despues-- se quedan sin
    relojes. El mes que ya tenia su cierre sigue el suyo.
    """
    db.flush()
    momento = reloj.ahora_del_servicio(db, servicio)
    abiertos = []
    for contrato in (db.query(m.ContratoImplantado)
                     .filter_by(servicio_id=servicio.id)
                     .order_by(m.ContratoImplantado.anio,
                               m.ContratoImplantado.mes).all()):
        if cierre_de(db, contrato):
            continue
        trabajados = any(j.estatus == m.EstatusJornada.TERMINADA
                         for j in _dias(db, contrato))
        salio = any(v.estatus != m.EstatusViatico.CANCELADO
                    for v in viaticos_del_mes(db, contrato))
        if trabajados or salio:
            abiertos.append(abrir(db, contrato, momento,
                                  motivo="cancelacion"))
    return abiertos


def con_visto_bueno(db: Session,
                    contrato: m.ContratoImplantado | None) -> bool:
    """Si el mes ya tiene visto bueno: su factura salio o esta por salir."""
    cierre = cierre_de(db, contrato)
    return bool(cierre and (cierre.facturado_en
                            or cierre.estatus in CON_VISTO_BUENO))


def deshacer_termino(db: Session, contrato: m.ContratoImplantado | None,
                     que: str) -> bool:
    """Un dia que se reabre, o que entra, despues de T0.

    Con el mes en comprobacion o sin visto bueno, el termino se deshace:
    el cierre se borra con sus plazos y el mes vuelve a cerrar cuando
    quede completo otra vez, con su nuevo ultimo dia. Con el visto bueno
    dado ya no: la factura del mes salio, o esta por salir, con esos dias.
    `que` completa el mensaje: "no se puede reabrir un dia".
    """
    cierre = cierre_de(db, contrato)
    if cierre is None:
        return False
    if con_visto_bueno(db, contrato):
        raise HTTPException(409, {
            "mensaje": (f"El mes {periodo(contrato)} ya tiene visto bueno: "
                        f"{que}"),
            "que_hacer": ("Lo que cambie de ese mes se corrige con finanzas: "
                          "la factura del mes ya salio con esos dias.")})
    for viatico in viaticos_del_mes(db, contrato):
        if viatico.limite_comprobacion == cierre.comprobacion_hasta:
            viatico.limite_comprobacion = None
    db.delete(cierre)
    db.flush()
    return True


# ------------------------------------------------------------ el reloj del mes

def estado(db: Session, contrato: m.ContratoImplantado,
           ahora: datetime | None = None) -> dict:
    """El reloj del mes, para su panel y para la cartera.

    Las mismas llaves que el del eventual (`cierre.estado`), mas el mes;
    el limite y el momento van los dos en hora del pais del servicio.
    """
    ahora = reloj.ahora_del_servicio(db, contrato.servicio, ahora)
    fila = cierre_de(db, contrato)
    base = {"contrato_id": contrato.id, "periodo": periodo(contrato),
            "momento": ahora.isoformat()}
    if fila is None:
        return {**base, **motor.VACIO}
    return {**base, **motor.ficha_del_cierre(db, fila, ahora)}


def relojes_de(db: Session, contratos: list,
               ahora: datetime | None = None) -> dict:
    """La fase y el reloj de varios meses de una vez, para la cartera:
    {contrato_id: {"fase", "reloj"}}. El mes sin cierre no aparece."""
    ids = [c.id for c in contratos]
    if not ids:
        return {}
    salida = {}
    for fila in (db.query(m.Cierre)
                 .filter(m.Cierre.contrato_id.in_(ids)).all()):
        momento = reloj.ahora_del_servicio(db, fila.servicio, ahora)
        salida[fila.contrato_id] = {
            "fase": motor.FASES.get(fila.estatus),
            "reloj": motor.reloj_de(fila, momento),
            "dentro_de_plazo": fila.dentro_de_plazo}
    return salida


def fases_de(db: Session, contratos: list) -> dict:
    """La fase del cierre de varios meses de una vez: {contrato_id: fase}.
    El mes sin cierre no aparece: todavia se esta trabajando."""
    ids = [c.id for c in contratos]
    if not ids:
        return {}
    return {c.contrato_id: motor.FASES.get(c.estatus)
            for c in (db.query(m.Cierre)
                      .filter(m.Cierre.contrato_id.in_(ids)).all())}


# ------------------------------------------------------------ comparativo

def comparar(db: Session, contrato: m.ContratoImplantado) -> dict:
    """Lo contratado del mes contra lo trabajado, y el dinero del mes.

    Sale del corte (`implantado.cierre_del_mes`): los dias que tuvieron
    gente y no se cancelaron, base y adicionales, a los precios del
    contrato; la unidad va por mes completo. Se factura lo trabajado, no
    lo contratado: un dia que el cliente cancelo no se cobra, y se dice.
    Un dia que quedo sin cubrir, o un precio que falta, se tiene que
    resolver antes del visto bueno.
    """
    corte = motor_implantado.cierre_del_mes(db, contrato.id)
    base = corte["cliente"]["base"]
    adicionales = corte["cliente"]["adicionales"]
    precios = {"dia": _d(contrato.precio_dia_personal),
               "dia_adicional": _d(contrato.precio_dia_adicional),
               "unidad_mes": _d(contrato.precio_mes_vehiculo),
               "mes_completo": _d(contrato.precio_mes_completo)}
    mes_completo = (contrato.esquema
                    == m.EsquemaCotizacionImplantado.MES_COMPLETO)
    desviaciones, notas = [], []

    if mes_completo:
        contratado = trabajado = precios["mes_completo"]
        desglose = {"mes_completo": trabajado}
        if not contrato.precio_mes_completo:
            desviaciones.append({
                "tipo": m.TipoDesviacion.COBRO_MENOR.value,
                "descripcion": (f"{periodo(contrato)}: el contrato no tiene "
                                "el precio del mes completo"),
                "monto": CERO})
    else:
        contratado = precios["dia"] * contrato.dias_base + precios["unidad_mes"]
        desglose = {"dias_base": precios["dia"] * base,
                    "dias_adicionales": precios["dia_adicional"] * adicionales,
                    "vehiculo_mes": precios["unidad_mes"]}
        trabajado = sum(desglose.values(), CERO)
        if base and not contrato.precio_dia_personal:
            desviaciones.append({
                "tipo": m.TipoDesviacion.COBRO_MENOR.value,
                "descripcion": (f"{periodo(contrato)}: el contrato no tiene "
                                "precio por dia"),
                "monto": CERO})
        if adicionales and not contrato.precio_dia_adicional:
            desviaciones.append({
                "tipo": m.TipoDesviacion.COBRO_MENOR.value,
                "descripcion": (f"{periodo(contrato)}: {adicionales} dia(s) "
                                "adicional(es) sin precio en el contrato"),
                "monto": CERO})
        if base < contrato.dias_base:
            notas.append(f"Se trabajaron {base} de {contrato.dias_base} dias "
                         "base: se cobran los trabajados")
    if adicionales:
        notas.append(f"{adicionales} dia(s) adicional(es): "
                     + ", ".join(corte["cliente"]["fechas_adicionales"]))

    # El dia que existio y nadie cubrio: ni se cobra ni se paga, pero es
    # un dia que el cliente pidio y no tuvo. Se explica antes de facturar.
    for fecha in corte["dias_sin_cubrir"]:
        desviaciones.append({
            "tipo": m.TipoDesviacion.DIAS_DE_MENOS.value,
            "descripcion": (f"{fecha}: el dia quedo sin cubrir; no se cobra "
                            "ni se paga"),
            "monto": CERO if mes_completo else -precios["dia"]})

    viaticos = viaticos_del_mes(db, contrato)
    asignado = sum((_d(v.monto_total) for v in viaticos), CERO)
    comprobado = sum((_d(v.monto_comprobado) for v in viaticos), CERO)
    devuelto = sum((_d(v.monto_devuelto) for v in viaticos), CERO)
    descontado = sum((_d(v.monto_descontado) for v in viaticos), CERO)
    absorbido = sum((_d(v.monto_absorbido) for v in viaticos), CERO)
    for v in viaticos:
        if v.cerrado_con_descuento:
            quien = v.persona.nombre if v.persona else v.persona_id
            notas.append(f"{quien}: cierre con descuento de "
                         f"{_d(v.monto_descontado)}"
                         + (f", {_d(v.monto_absorbido)} absorbido por la "
                            "empresa" if _d(v.monto_absorbido) else ""))

    # Los gastos del mes, segun el trato de sus terminos (seccion 59): a
    # precio alzado, el monto fijo del mes, se gaste mas o menos --sin
    # monto, van dentro del precio--; netos, lo comprobado valido.
    alzado = contrato.viaticos_incluidos
    fijo = _d(contrato.gastos_mes)
    por_cobrar = fijo if alzado else comprobado

    return {
        "servicio": contrato.servicio.folio,
        "periodo": periodo(contrato),
        "esquema": contrato.esquema.value,
        "precios": precios,
        "contratado": {"dias_base": contrato.dias_base,
                       "importe": contratado},
        "trabajado": {"dias_base": base, "dias_adicionales": adicionales,
                      "fechas_adicionales":
                          corte["cliente"]["fechas_adicionales"],
                      "importe": trabajado, "desglose": desglose},
        "diferencia": trabajado - contratado,
        "viaticos": {"asignado": asignado, "comprobado": comprobado,
                     "devuelto": devuelto,
                     "pendiente": asignado - comprobado - devuelto,
                     "descontado_al_personal": descontado,
                     "absorbido_por_la_empresa": absorbido,
                     "modo_cobro": motor.modo_de_gastos(alzado),
                     "gastos_cotizados": fijo,
                     "facturable_al_cliente": por_cobrar},
        "gastos": {"modo": motor.modo_de_gastos(alzado),
                   "cotizado": fijo if alzado else CERO,
                   "comprobado": comprobado, "a_facturar": por_cobrar},
        # Lo que sale en la factura del mes: el servicio y, si se cobran
        # aparte, los viaticos comprobados.
        "a_facturar": {"servicio": trabajado, "viaticos": por_cobrar,
                       "total": trabajado + por_cobrar},
        "desviaciones": desviaciones,
        "notas": notas,
        "sin_desviaciones": not desviaciones,
    }


# ------------------------------------------------------------ la revision

def revisar(db: Session, contrato: m.ContratoImplantado,
            ahora: datetime | None = None) -> dict:
    """La revision del mes antes del visto bueno.

    Las mismas reglas que la del eventual (`revisor.revisar`), sobre los
    dias y el dinero de este mes, y con el comparativo contra el contrato
    en lugar de una cotizacion. Vive aparte a proposito: la del eventual
    no se toca (el implantado no mueve nada del eventual).
    """
    servicio = contrato.servicio
    ahora = reloj.ahora_del_servicio(db, servicio, ahora)
    comparativo = comparar(db, contrato)
    fila = cierre_de(db, contrato)
    respaldadas = ({d.descripcion for d in fila.desviaciones if d.respaldada}
                   if fila else set())
    observaciones = []

    for nota in comparativo["notas"]:
        observaciones.append({
            "nivel": INFO, "asunto": "Del mes", "mensaje": nota,
            "accion": "Informativo."})
    for d in comparativo["desviaciones"]:
        if d["descripcion"] in respaldadas:
            observaciones.append({
                "nivel": INFO, "asunto": "Desviacion respaldada",
                "mensaje": d["descripcion"],
                "accion": "Ya tiene justificacion registrada, no escala."})
            continue
        observaciones.append({
            "nivel": GRAVE, "asunto": d["tipo"], "mensaje": d["descripcion"],
            "accion": ("Captura el precio en el contrato del mes: sin el, la "
                       "factura sale en cero."
                       if d["tipo"] == m.TipoDesviacion.COBRO_MENOR.value
                       else "Justifica la desviacion o corrige el mes.")})

    dias = _dias(db, contrato)
    for j in dias:
        if j.estatus != m.EstatusJornada.CANCELADA and not j.fin_real:
            observaciones.append({
                "nivel": GRAVE, "asunto": "Jornada sin termino",
                "mensaje": f"{j.fecha}: el conductor no marco el fin del servicio",
                "accion": "Pide a la central que registre el corte con "
                          "justificacion."})

    # El dinero que nadie cerro, persona por persona. Grave por lo mismo
    # que en el eventual: con el visto bueno el gasto desaparece de la
    # app de quien lo debe.
    observaciones.extend(observaciones_del_dinero(
        viaticos_del_mes(db, contrato), ahora))

    ids = [j.id for j in dias]
    if ids:
        for h in (db.query(m.Hito)
                  .filter(m.Hito.jornada_id.in_(ids),
                          m.Hito.requiere_revision.is_(True)).all()):
            observaciones.append({
                "nivel": AVISO, "asunto": "Marca fuera de horario sin revisar",
                "mensaje": (f"{h.tipo.value} del {h.marcado_en:%d/%m %H:%M} "
                            "sigue marcado para revision de la central"),
                "accion": "La central debe validarla o ajustarla antes del "
                          "cierre."})
        alertas = (db.query(m.Alerta)
                   .filter(m.Alerta.jornada_id.in_(ids),
                           m.Alerta.atendida.is_(False)).count())
        if alertas:
            observaciones.append({
                "nivel": AVISO, "asunto": "Alertas sin atender",
                "mensaje": f"{alertas} alerta(s) de la central siguen abiertas",
                "accion": "Cierra cada alerta con su resolucion."})

    # Los dos relojes del mes.
    if fila is None:
        observaciones.append({
            "nivel": AVISO, "asunto": "El mes sigue abierto",
            "mensaje": "El cierre del mes arranca al cerrar su ultimo dia "
                       "trabajado.",
            "accion": "Nada que hacer todavia."})
    elif fila.estatus == m.EstatusCierre.ABIERTO:
        hasta = fila.comprobacion_hasta
        observaciones.append({
            "nivel": AVISO, "asunto": "Comprobacion en curso",
            "mensaje": (f"El personal tiene hasta el {hasta:%d/%m %H:%M} "
                        "para comprobar sus viaticos del mes" if hasta else
                        "El personal esta comprobando sus viaticos del mes"),
            "accion": "El visto bueno se abre cuando venza ese plazo, o "
                      "antes si todos los viaticos del mes ya cerraron."})
    else:
        observaciones.extend(observaciones_del_plazo(fila, ahora, del_mes=True))

    graves = [o for o in observaciones if o["nivel"] == GRAVE]
    return {
        "servicio": servicio.folio,
        "periodo": periodo(contrato),
        "revisado_en": ahora.isoformat(),
        "cierre": estado(db, contrato, ahora),
        "listo_para_finanzas": not graves,
        "resumen": ("Sin observaciones que corregir" if not graves
                    else f"{len(graves)} punto(s) por corregir antes de "
                         "enviar a finanzas"),
        "observaciones": observaciones,
        "comparativo": comparativo,
    }


# ------------------------------------------------------------ visto bueno y finanzas

def enviar_a_finanzas(db: Session, cierre: m.Cierre, usuario: m.Usuario,
                      ahora: datetime | None = None) -> dict:
    """El visto bueno del mes: su termino general.

    El mismo recorrido que el del eventual (`routers/cierre.py`), con la
    revision del mes: solo desde T1, sin viaticos del mes abiertos y con
    el comparativo contra el contrato. En plazo si llega antes de T1 +
    24 h; de eso depende la comision. La factura del mes sale en ese
    momento; si Odoo no contesta, el mes queda por facturar. El servicio
    no cambia de estatus: sigue en la calle con el mes que corre.
    """
    contrato = cierre.contrato
    momento = reloj.ahora_del_servicio(db, cierre.servicio, ahora)

    # Si ya llego T1 --o todo el dinero del mes ya cerro-- y la tarea de
    # cada cinco minutos no ha pasado, se avanza aqui y se guarda.
    if motor.avanzar(db, cierre, momento):
        db.commit()

    if cierre.estatus not in (m.EstatusCierre.SIN_VISTO_BUENO,
                              m.EstatusCierre.DEVUELTO_A_OPERACION):
        raise HTTPException(409, {
            "mensaje": ("Todavia corre la comprobacion de viaticos del personal"
                        if cierre.estatus == m.EstatusCierre.ABIERTO
                        else f"El cierre del mes esta en "
                             f"{motor.nombre_estatus(cierre.estatus)}"),
            "hasta": (cierre.comprobacion_hasta.isoformat()
                      if cierre.comprobacion_hasta else None),
            "observaciones": [],
        })

    revision = revisar(db, contrato, momento)
    if not revision["listo_para_finanzas"]:
        raise HTTPException(409, {
            "mensaje": "Hay puntos por corregir antes de enviar a finanzas",
            "observaciones": [o for o in revision["observaciones"]
                              if o["nivel"] == GRAVE],
        })

    comparativo = revision["comparativo"]
    cierre.total_cotizado = comparativo["contratado"]["importe"]
    cierre.total_ejecutado = comparativo["a_facturar"]["total"]
    motor.dar_visto_bueno(cierre, momento)
    cierre.cerrado_por_id = usuario.persona_id
    auditoria.registrar(db, usuario, cierre.servicio, "enviar a finanzas",
                        f"{periodo(contrato)}: contratado "
                        f"{cierre.total_cotizado}, trabajado "
                        f"{cierre.total_ejecutado}, "
                        f"{'en plazo' if cierre.dentro_de_plazo else 'FUERA DE PLAZO'}")

    # Lo pagado cada semana contra lo que corresponde al corte del mes:
    # las diferencias van a la nomina siguiente, como en el eventual.
    ajustes = nomina.diferencias_del_servicio(db, cierre.servicio_id,
                                              usuario.persona_id)
    if ajustes["ajustes_generados"]:
        auditoria.registrar(
            db, usuario, cierre.servicio, "ajustes de nomina",
            f"{len(ajustes['ajustes_generados'])} diferencias a la "
            f"siguiente nomina")
    db.commit()

    # La factura del mes, despues de guardar: un Odoo caido no deshace el
    # visto bueno, el mes se queda por facturar con el error a la vista.
    factura = facturacion.enviar(db, cierre)
    db.commit()

    return {"resultado": "enviado a finanzas", "cierre_id": cierre.id,
            "periodo": periodo(contrato),
            "factura": factura,
            "dentro_de_plazo": cierre.dentro_de_plazo,
            "comision_consultor": ("se detona con la validacion de finanzas"
                                   if cierre.dentro_de_plazo
                                   else "se pierde por cierre fuera de plazo"),
            "ajustes_de_nomina": ajustes["ajustes_generados"]}


def aprobar(db: Session, cierre: m.Cierre, usuario: m.Usuario) -> dict:
    """Finanzas valida el mes.

    El mes queda aprobado; el servicio no se cierra, sigue vivo con el mes
    que corre. Si el visto bueno fue en plazo se detona la comision del
    consultor por ese mes. La rentabilidad del mes viene despues, con la
    moneda.
    """
    cierre.estatus = m.EstatusCierre.APROBADO
    cierre.aprobado_en = datetime.now()
    cierre.aprobado_por_id = usuario.persona_id
    auditoria.registrar(db, usuario, cierre.servicio, "aprobar cierre",
                        f"{periodo(cierre.contrato)}, validado por finanzas")
    db.commit()

    comision = None
    if cierre.servicio.consultor_id:
        c = comisiones.generar_del_mes(db, cierre)
        comision = {"comision_id": c.id, "consultor": c.consultor.nombre,
                    "base": c.base, "porcentaje": float(c.porcentaje),
                    "monto": c.monto, "estatus": c.estatus.value,
                    "motivo": c.motivo}

    # Solo reintenta si el envio del visto bueno fallo; si ya salio, el
    # mes pasa a facturado.
    factura = facturacion.enviar(db, cierre)
    db.commit()

    return {"resultado": "aprobado", "cierre_id": cierre.id,
            "periodo": periodo(cierre.contrato),
            "comision_consultor": comision,
            "factura": factura,
            "rentabilidad": None}


def armar_factura(db: Session, cierre: m.Cierre) -> dict:
    """La factura del mes, renglon por renglon, a los precios del contrato.

    El folio de Centauro y el mes viajan siempre: son la llave para
    conciliar las dos bases el dia que no cuadren. Los viaticos van en
    su renglon cuando los terminos del mes los cobran aparte (seccion
    57); incluidos, ya van en el precio.
    """
    contrato = cierre.contrato
    servicio = cierre.servicio
    comparativo = comparar(db, contrato)
    trabajado = comparativo["trabajado"]
    precios = comparativo["precios"]
    de_que = periodo(contrato)

    conceptos = []
    if contrato.esquema == m.EsquemaCotizacionImplantado.MES_COMPLETO:
        conceptos.append({
            "tipo": "mes_completo",
            "descripcion": f"Servicio implantado {de_que}, mes completo",
            "cantidad": 1, "precio": str(precios["mes_completo"]),
            "importe": str(precios["mes_completo"])})
    else:
        if trabajado["dias_base"]:
            conceptos.append({
                "tipo": "dias_base",
                "descripcion": f"Servicio implantado {de_que}, dias de servicio",
                "cantidad": trabajado["dias_base"],
                "precio": str(precios["dia"]),
                "importe": str(trabajado["desglose"]["dias_base"])})
        if trabajado["dias_adicionales"]:
            conceptos.append({
                "tipo": "dias_adicionales",
                "descripcion": f"Dias adicionales {de_que}",
                "cantidad": trabajado["dias_adicionales"],
                "precio": str(precios["dia_adicional"]),
                "importe": str(trabajado["desglose"]["dias_adicionales"]),
                "fechas": trabajado["fechas_adicionales"]})
        if precios["unidad_mes"]:
            conceptos.append({
                "tipo": "vehiculo_mes",
                "descripcion": f"Unidad {de_que}, mes completo",
                "cantidad": 1, "precio": str(precios["unidad_mes"]),
                "importe": str(precios["unidad_mes"])})

    a_facturar = comparativo["a_facturar"]
    if a_facturar["viaticos"]:
        conceptos.append({
            "tipo": "viaticos",
            "descripcion": (f"Gastos a precio alzado {de_que}"
                            if contrato.viaticos_incluidos
                            else f"Gastos comprobados {de_que}"),
            "cantidad": 1, "precio": str(a_facturar["viaticos"]),
            "importe": str(a_facturar["viaticos"])})

    pais = db.get(m.Pais, servicio.pais_id)
    cliente = servicio.cliente
    return {
        "referencia": f"{servicio.folio} {de_que}",
        "cierre_id": cierre.id,
        "periodo": de_que,
        "cliente": {"id_odoo": cliente.odoo_id if cliente else None,
                    "nombre": cliente.nombre if cliente else None},
        "moneda": pais.moneda_local.value if pais else None,
        "fecha": (cierre.enviado_en or cierre.aprobado_en
                  or datetime.now()).date().isoformat(),
        "total": str(a_facturar["total"]),
        "conceptos": conceptos,
        # La que se anulo cuando finanzas regreso el mes: esta la sustituye.
        "sustituye_a": cierre.factura_anulada,
    }

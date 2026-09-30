"""Calculo y asignacion de viaticos.

El tabulador es identico para toda la empresa dentro de cada pais.
El consultor asigna el monto con base en el escenario de la jornada.
El combustible se propone como estimado a precio alzado segun los kilometros
a recorrer, mas una holgura, para que el consultor sepa el gasto aproximado.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import reloj

# Cuanto se tolera de mas al comprobar. No es cero porque pasa de
# verdad: alguien pone de su bolsa la diferencia de una caseta o de una
# comida y sube el ticket completo. Pero no puede ser libre, porque lo
# comprobado es lo que se le factura al cliente y lo que decide si hay
# descuento de nomina.
TOLERANCIA_COMPROBADO = Decimal("1.20")

# Cuanto tiempo cuenta como "el mismo toque". Un ticket identico un
# minuto despues es la app mandando dos veces con mala senal; el mismo
# ticket tres horas despues son dos casetas, una de ida y otra de
# vuelta, y esas son dos de verdad.
MINUTOS_DOBLE_TOQUE = 3


# ---------------------------------------------------- lo que de verdad salio
#
# Seccion 98. El estatus del viatico cuenta una ronda a la vez: con un
# primer deposito hecho y un segundo pedido, dice TRANSFERIDO, y todo lo
# que sumaba `monto_total` --el segundo incluido-- se leia como dinero en
# la cuenta de la persona: la app decia "te depositaron 1,600" con 600
# todavia en finanzas, el consultor podia cerrar con descuento sobre
# esos 600, y el deposito que llegaba despues caia sobre un viatico ya
# cerrado. Lo depositado son las solicitudes que finanzas confirmo; lo
# demas esta en camino o sin pedir.

def depositado(viatico) -> Decimal:
    """Lo que finanzas confirmo de este viatico, ronda por ronda."""
    return sum((Decimal(str(s.monto)) for s in viatico.solicitudes
                if s.estatus == m.EstatusTransferencia.CONFIRMADA),
               Decimal("0"))


def en_camino(viatico) -> Decimal:
    """Lo pedido que finanzas todavia no deposita."""
    return sum((Decimal(str(s.monto)) for s in viatico.solicitudes
                if s.estatus in (m.EstatusTransferencia.PENDIENTE,
                                 m.EstatusTransferencia.ENVIADA)),
               Decimal("0"))


# Ya salio del banco, o se resolvio despues de haber salido.
CON_DINERO_AFUERA = (m.EstatusViatico.TRANSFERIDO,
                     m.EstatusViatico.EN_COMPROBACION,
                     m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO)


def cancelar(db: Session, viatico, ahora: datetime | None = None,
             por_id: int | None = None) -> dict:
    """Ese viatico ya no va a salir: la persona no trabaja ese dia.

    Solo lo que no ha salido del banco (asignado o solicitado). Sus
    solicitudes se resuelven con el: la pendiente se cancela, y la que
    ya esta enviada --en manos de finanzas, quiza en el banco ahora
    mismo-- queda con la cancelacion pedida, como cuando la pide el
    consultor (seccion 41): la cierra finanzas, que es quien sabe si el
    dinero salio.

    Antes cada camino cancelaba el viatico y dejaba la solicitud viva:
    finanzas la seguia viendo en su bandeja como dinero por pagar --y lo
    pagaba a alguien que ya no iba, o se quedaba atorada para siempre--.
    Un servicio cancelado, un dia quitado y un reemplazo por contingencia
    pasaban por aqui sin pasar por aqui.
    """
    if viatico.estatus not in (m.EstatusViatico.ASIGNADO,
                               m.EstatusViatico.SOLICITADO):
        return {"cancelado": False, "canceladas": 0, "pedidas": 0}
    viatico.estatus = m.EstatusViatico.CANCELADO
    canceladas = pedidas = 0
    for solicitud in viatico.solicitudes:
        if solicitud.estatus == m.EstatusTransferencia.PENDIENTE:
            solicitud.estatus = m.EstatusTransferencia.CANCELADA
            canceladas += 1
        elif (solicitud.estatus == m.EstatusTransferencia.ENVIADA
              and not solicitud.cancelacion_pedida_en):
            solicitud.cancelacion_pedida_en = ahora or datetime.now()
            solicitud.cancelacion_pedida_por_id = por_id
            pedidas += 1
    return {"cancelado": True, "canceladas": canceladas, "pedidas": pedidas}


def bolson_del_servicio(db: Session, viatico) -> list:
    """Todos los viaticos de esa persona en ese servicio.

    El dinero se deposita junto --un movimiento por persona, por todos
    sus dias-- y se gasta junto. El reparto por dia es como el consultor
    calculo el monto, no un sobre por dia que la persona tenga que
    respetar.
    """
    jornada = getattr(viatico, "jornada", None)
    equipo = getattr(jornada, "equipo", None)
    if db is None or equipo is None:
        return [viatico]
    hermanos = (db.query(m.AsignacionViatico)
                .join(m.Jornada,
                      m.AsignacionViatico.jornada_id == m.Jornada.id)
                .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                .filter(m.Equipo.servicio_id == equipo.servicio_id,
                        m.AsignacionViatico.persona_id == viatico.persona_id,
                        m.AsignacionViatico.estatus
                        != m.EstatusViatico.CANCELADO)
                .all())
    # El bolson es lo que se deposito junto. En el eventual eso es el
    # servicio; en el implantado es el mes, porque el equipo abarca
    # meses enteros y cada uno se deposita por separado.
    servicio = getattr(equipo, "servicio", None)
    if servicio is not None and servicio.tipo == m.TipoServicio.IMPLANTADO:
        suyo = jornada.fecha
        hermanos = [v for v in hermanos
                    if v.jornada and v.jornada.fecha.year == suyo.year
                    and v.jornada.fecha.month == suyo.month]
    return hermanos


def revisar_comprobante(viatico, monto, concepto, descripcion, ahora=None,
                        db: Session | None = None):
    """Las reglas de un ticket, en un solo lugar.

    Hay dos endpoints que escriben la misma tabla —el de la consola y el
    de la app— con el mismo rol. Poner las reglas en uno solo era dejar
    la otra puerta abierta, que es exactamente lo que pasaba.

    Devuelve None si todo esta bien, o un dict con el error.
    """
    ahora = ahora or datetime.now()

    if monto <= 0:
        return {"codigo": 400,
                "mensaje": "El monto del ticket tiene que ser mayor a cero",
                "que_hacer": "Escribe lo que dice el ticket."}

    # El tope es lo que trae para TODO el servicio, no lo que le tocaba
    # ese dia. Un dia se gasta mas y otro menos; lo que tiene que cuadrar
    # es el total. Topar por dia bloqueaba a alguien que iba bien en su
    # cuenta y lo empujaba a repartir el mismo ticket entre dias.
    hermanos = bolson_del_servicio(db, viatico)
    # Se cuenta lo asignado, no solo lo ya depositado: el tope existe
    # para que nadie comprobe de mas, y un dia que todavia no sale del
    # banco sigue siendo dinero autorizado de ese servicio. Quien mira
    # si el dinero ya salio es la tarjeta de la app, que lo dice aparte.
    entregado = sum((Decimal(str(v.monto_total or 0)) for v in hermanos),
                    Decimal("0"))
    devuelto = sum((Decimal(str(v.monto_devuelto or 0)) for v in hermanos),
                   Decimal("0"))
    ya = sum((Decimal(str(c.monto)) for v in hermanos
              for c in v.comprobantes if not c.rechazado), Decimal("0"))
    disponible = entregado - devuelto

    # Con cero entregado no hay contra que topar: puede ser un dia que el
    # tabulador dejo en cero y el gasto salio igual. Se deja pasar y lo
    # revisa el consultor, que es quien puede decidirlo.
    if disponible > 0 and ya + monto > disponible * TOLERANCIA_COMPROBADO:
        return {"codigo": 409,
                "mensaje": "Ese ticket pasa de lo que se entrego",
                "que_hacer": (f"Llevas comprobado {ya} de {disponible} de "
                              f"todo el servicio. Si de verdad se gasto mas, "
                              f"eso se resuelve con viaticos adicionales, no "
                              f"con un comprobante."),
                "entregado": str(disponible), "comprobado": str(ya)}

    # El mismo ticket dos veces seguidas: un doble toque con media barra
    # de senal, que es la situacion normal en una gasolinera.
    desde = ahora - timedelta(minutes=MINUTOS_DOBLE_TOQUE)
    for c in viatico.comprobantes:
        if c.rechazado:
            continue
        cuando = getattr(c, "subido_en", None)
        if cuando is not None:
            # `subido_en` lleva zona horaria: guarda un instante
            # absoluto en UTC. Quitarle la zona con `replace` no
            # convertia nada —dejaba la hora UTC como si fuera local— y
            # al compararla contra la hora local quedaba corrida por el
            # desfase del servidor. Resultado: la ventana de tres
            # minutos no disparaba nunca, ni en Mexico. Hay que
            # convertir, no truncar.
            if cuando.tzinfo:
                cuando = cuando.astimezone().replace(tzinfo=None)
            if cuando < desde:
                continue
        if (Decimal(str(c.monto)) == monto and c.concepto == concepto
                and (c.descripcion or "") == (descripcion or "")):
            return {"codigo": 409,
                    "mensaje": "Ese ticket se acaba de subir",
                    "que_hacer": "Si son dos gastos distintos por el mismo "
                                 "monto, escribe en la nota de que fue cada "
                                 "uno.",
                    "comprobante_id": c.id}
    return None

HORAS_PARA_COMPROBAR = 24

# A esa hora no hay transporte publico con el que llegar a la base, y el
# que se presenta antes tiene que pagarse un taxi de su bolsa. Por eso el
# traslado del personal se cubre solo cuando la presentacion cae antes de
# las 6:30: mas tarde, el agente llega como llega cualquier dia.
HORA_TRASLADO = time(6, 30)

# Lo que cobra el estacionamiento del aeropuerto por una vuelta. No es un
# monto de tabulador porque no depende del escenario sino de cuantas
# veces entra la unidad ese dia: recoger al ejecutivo es una, dejarlo es
# otra, y hay dias que son las dos.
ESTACIONAMIENTO_AEROPUERTO = Decimal("100")

ENTERO = Decimal("1")


def redondear(monto: Decimal) -> Decimal:
    """Al entero de arriba, siempre.

    Un viatico se entrega en efectivo o por transferencia y nadie anda
    con centavos: 217.60 se deposita como 218. Y va hacia arriba y no al
    mas cercano porque quedarse corto es mandar al agente a poner de su
    bolsa, mientras que sobrar cuarenta centavos no le hace dano a nadie.
    """
    return Decimal(monto).quantize(ENTERO, rounding=ROUND_CEILING)


def escenario_de(jornada: m.Jornada) -> m.EscenarioViatico:
    """El escenario sale de la modalidad del dia y de si es local o foraneo.

    El implantado es un dia completo con su propia jornada (seccion
    105): sus viaticos son los del dia completo, local o foraneo.
    """
    codigo = jornada.modalidad.codigo
    if codigo in (m.CodigoModalidad.FULL_DAY, m.CodigoModalidad.IMPLANTADO):
        return (m.EscenarioViatico.FULL_DAY_FORANEO if jornada.es_foraneo
                else m.EscenarioViatico.FULL_DAY_LOCAL)
    if codigo == m.CodigoModalidad.MEDIO_DIA:
        return m.EscenarioViatico.MEDIO_DIA
    return m.EscenarioViatico.TRANSFER


def al_volante(jornada: m.Jornada, vehiculo_id: int) -> int | None:
    """A quien se le propone la gasolina de esa unidad ese dia.

    Decision 9 de Salvador (seccion 105): el combustible se propone una
    vez por unidad, a quien va al volante --la persona con rol de
    conductor a bordo de esa unidad--; si la unidad no trae conductor
    asignado, a quien vaya en ella (el agente puede quedar a cargo de
    la unidad). Con dos a bordo del mismo rol se lo lleva el primero
    asignado: la propuesta tiene que caer en alguien, y el consultor la
    mueve si iba al reves.

    Es la misma regla con la que la central sabe quien trae la unidad al
    punto (`gps.la_traen`); se importa aqui adentro porque `gps`
    arrastra la operacion entera y este modulo se carga antes que ella.
    """
    from app import gps

    gente = sorted(gps.la_traen(jornada, vehiculo_id), key=lambda a: a.id)
    return gente[0].persona_id if gente else None


def unidad_que_conduce(jornada: m.Jornada, persona_id: int
                       ) -> m.AsignacionVehiculo | None:
    """La unidad cuya gasolina le toca a esa persona ese dia, si alguna.

    Con dos unidades cada conductor recibe lo de la suya, con el
    rendimiento de esa unidad y no el de la primera del dia (seccion
    105). La que salio a media jornada ya no cuenta: su gasolina la trae
    quien la relevo.
    """
    for asignacion in sorted(jornada.vehiculos, key=lambda a: a.id):
        if asignacion.relevado_en is not None or not asignacion.vehiculo_id:
            continue
        if al_volante(jornada, asignacion.vehiculo_id) == persona_id:
            return asignacion
    return None


def estimar_combustible(db: Session, jornada: m.Jornada, pais_id: int,
                        persona_id: int | None = None) -> dict | None:
    """Kilometros / rendimiento de la categoria * precio por litro, mas holgura.

    Por unidad y para quien la conduce (seccion 105). Antes se calculaba
    con la primera unidad del dia y se le proponia a cada persona del
    equipo: conductor y agente en la misma camioneta recibian cada uno
    el tanque completo, "Usar el propuesto" lo depositaba dos veces y
    con dos unidades el segundo conductor recibia el rendimiento de la
    primera. Sin `persona_id` se calcula con la primera unidad vigente,
    como antes: es lo que sirve para saber cuanto cuesta el dia.

    Devuelve None cuando no hay como estimar --sin kilometros, sin
    unidad, sin precio del litro-- y `{"monto": 0, ...}` cuando si hay
    unidad pero la gasolina no le toca a esa persona.
    """
    if not jornada.km_estimados:
        return None

    vigentes = [a for a in sorted(jornada.vehiculos, key=lambda a: a.id)
                if a.relevado_en is None and a.vehiculo_id]
    if not vigentes:
        return None
    if persona_id is None:
        asignacion_vehiculo = vigentes[0]
    else:
        asignacion_vehiculo = unidad_que_conduce(jornada, persona_id)
        if asignacion_vehiculo is None:
            return {"monto": Decimal("0"),
                    "detalle": "La gasolina se propone a quien conduce "
                               "la unidad"}

    rendimiento = Decimal(str(asignacion_vehiculo.vehiculo.categoria.rendimiento_km_litro))
    if rendimiento <= 0:
        return None

    parametro = (db.query(m.ParametroCombustible)
                 .filter(m.ParametroCombustible.pais_id == pais_id,
                         m.ParametroCombustible.activo.is_(True))
                 .order_by(m.ParametroCombustible.vigencia_desde.desc())
                 .first())
    if not parametro:
        return None

    litros = Decimal(jornada.km_estimados) / rendimiento
    base = litros * Decimal(str(parametro.precio_litro))
    holgura = Decimal(str(parametro.holgura_pct)) / Decimal("100")
    total = redondear(base * (Decimal("1") + holgura))

    placa = (asignacion_vehiculo.vehiculo.placa
             if asignacion_vehiculo.vehiculo else None)
    return {
        "monto": total,
        "detalle": (f"{jornada.km_estimados} km / "
                    f"{rendimiento} km-l = {litros.quantize(Decimal('0.01'))} l "
                    f"x {parametro.precio_litro} + {parametro.holgura_pct}% de holgura"
                    + (f" · unidad {placa}" if placa else "")),
    }


def vueltas_al_aeropuerto(jornada: m.Jornada) -> int:
    """Cuantas veces entra la unidad al aeropuerto ese dia.

    Una por recoger —el dia arranca ahi— y otra por dejar, cuando el dia
    lleva vuelo de salida. Un transfer redondo del mismo dia cuenta dos.
    """
    vueltas = 1 if jornada.origen_aeropuerto else 0
    if (jornada.vuelo_tipo or "").lower() == "salida":
        vueltas += 1
    return vueltas


def calcular(db: Session, jornada_id: int, persona_id: int) -> dict:
    """Propuesta de viaticos. No guarda nada: es la vista previa del consultor."""
    jornada = db.get(m.Jornada, jornada_id)
    if not jornada:
        raise HTTPException(404, f"No existe la jornada {jornada_id}")
    persona = db.get(m.Persona, persona_id)
    if not persona:
        raise HTTPException(404, f"No existe la persona {persona_id}")

    asignacion = next((a for a in jornada.personal
                       if a.persona_id == persona_id), None)
    if not asignacion:
        raise HTTPException(400, "La persona no esta asignada a esa jornada")

    servicio = jornada.equipo.servicio
    pais = db.get(m.Pais, servicio.pais_id)
    escenario = escenario_de(jornada)

    # Cada tipo de servicio lee su propia tabla: un dia de implantado y
    # un dia de eventual no se gastan igual, aunque la modalidad se
    # llame igual.
    filas = (db.query(m.TabuladorViatico)
             .filter(m.TabuladorViatico.pais_id == pais.id,
                     m.TabuladorViatico.tipo_servicio == servicio.tipo,
                     m.TabuladorViatico.escenario == escenario,
                     m.TabuladorViatico.activo.is_(True))
             .all())

    # La presentacion del dia manda sobre el traslado. Se mira aqui y no
    # en el tabulador porque el tabulador no sabe a que hora arranca la
    # jornada: dice cuanto, no cuando aplica.
    madruga = jornada.inicio_programado.time() < HORA_TRASLADO
    vueltas = vueltas_al_aeropuerto(jornada)

    conceptos = []
    for fila in filas:
        if (fila.concepto == m.ConceptoViatico.TRASLADO_PERSONAL
                and not madruga):
            # El renglon se queda a la vista, en cero y con el motivo. Que
            # desapareciera dejaba al consultor preguntandose si el
            # tabulador estaba mal cargado o si la regla lo saco.
            conceptos.append({
                "concepto": fila.concepto.value, "monto": Decimal("0"),
                "descripcion": "Solo cuando la presentacion es antes de "
                               "las 6:30",
                "origen": m.OrigenMonto.TABULADOR.value, "editable": True,
            })
            continue
        if fila.concepto == m.ConceptoViatico.COMBUSTIBLE:
            # Por unidad y para quien la conduce (seccion 105): al que
            # va de copiloto le sale en cero, editable, y no el tanque
            # otra vez.
            estimado = estimar_combustible(db, jornada, pais.id, persona_id)
            if estimado:
                conceptos.append({
                    "concepto": fila.concepto.value,
                    "monto": estimado["monto"],
                    "descripcion": estimado["detalle"],
                    "origen": m.OrigenMonto.ESTIMADO.value,
                    "editable": True,
                })
            else:
                conceptos.append({
                    "concepto": fila.concepto.value, "monto": Decimal("0"),
                    "descripcion": "Falta kilometraje o vehiculo asignado",
                    "origen": m.OrigenMonto.MANUAL.value, "editable": True,
                })
        elif fila.concepto == m.ConceptoViatico.OTROS and vueltas:
            # El estacionamiento del aeropuerto es lo unico de "otros"
            # que se puede anticipar: se sabe desde que se arma el dia.
            # Lo demas de ese concepto lo sigue capturando el consultor,
            # encima de este monto.
            conceptos.append({
                "concepto": fila.concepto.value,
                "monto": ESTACIONAMIENTO_AEROPUERTO * vueltas,
                "descripcion": (f"Estacionamiento del aeropuerto, "
                                f"{vueltas} vuelta(s)"),
                "origen": m.OrigenMonto.ESTIMADO.value, "editable": True,
            })
        elif fila.monto_abierto:
            conceptos.append({
                "concepto": fila.concepto.value, "monto": Decimal("0"),
                "descripcion": "El consultor captura descripcion y monto",
                "origen": m.OrigenMonto.MANUAL.value, "editable": True,
            })
        else:
            conceptos.append({
                "concepto": fila.concepto.value,
                "monto": redondear(fila.monto),
                "descripcion": None,
                "origen": m.OrigenMonto.TABULADOR.value,
                "editable": True,
            })

    # Cada renglon ya viene entero, asi que el total lo es tambien y la
    # suma que ve el consultor cuadra con lo que suman los renglones.
    total = sum((c["monto"] for c in conceptos), Decimal("0"))

    return {
        "jornada_id": jornada.id,
        "fecha": jornada.fecha.isoformat(),
        "servicio": servicio.folio,
        "persona": {"id": persona.id, "nombre": persona.nombre,
                    "perfil": (asignacion.rol.codigo
                               if asignacion and asignacion.rol else None)},
        "escenario": escenario.value,
        # De que tabla salio la propuesta: el consultor tiene que poder
        # ver que se leyo la de implantado y no la de eventual.
        "tipo_servicio": servicio.tipo.value,
        "moneda": pais.moneda_local.value,
        "conceptos": conceptos,
        "total_propuesto": total,
    }


def limite_de_comprobacion(termino: datetime) -> datetime:
    """24 horas desde el termino del servicio para cerrar viaticos."""
    return termino + timedelta(hours=HORAS_PARA_COMPROBAR)


# ------------------------------------------------- la bandeja de finanzas
#
# Decision 8 de Salvador (seccion 105): ya no hay barrido ni ventana de
# "un dia antes". Lo solicitado entra a la bandeja en cuanto se pide y
# finanzas decide cuando transferir, mirando la fecha del servicio: lo
# vencido sin depositar hasta arriba y en rojo, luego lo de hoy, lo de
# manana y lo demas con su fecha. La regla vieja vivia en una ruta que
# nadie corria: la bandeja ensenaba todo igual, un servicio de manana y
# uno de dentro de treinta dias.

VENCIDA, HOY, MANANA, DESPUES = "vencida", "hoy", "manana", "despues"
# El orden en que se despacha.
ORDEN_URGENCIA = {VENCIDA: 0, HOY: 1, MANANA: 2, DESPUES: 3}


def urgencia_del_deposito(fecha_servicio: date, hoy: date) -> str:
    """Que tan urgente es depositar, contra el dia de hoy DEL PAIS.

    `fecha_servicio` es el primer dia pendiente de pago de esa persona en
    ese equipo (en el implantado, dentro del mes). Anterior a hoy y sin
    depositar es dinero que ya debia estar en la calle.
    """
    if fecha_servicio < hoy:
        return VENCIDA
    if fecha_servicio == hoy:
        return HOY
    if fecha_servicio == hoy + timedelta(days=1):
        return MANANA
    return DESPUES


# ---------------------------------------------- dinero nuevo tras el cierre
#
# Decision 10 de Salvador (seccion 105): en un servicio cancelado, en
# facturacion o cerrado ya no entra dinero nuevo --ni se abre un
# viatico, ni se pide, ni se deposita--. Lo pedido antes del cierre no se
# toca: se deposita, se comprueba y se devuelve como siempre. Si de
# verdad hace falta mas dinero, primero finanzas regresa el servicio, se
# mueve el dinero y se vuelve a cerrar. Antes el consultor fijaba 1,500
# en un servicio ya facturado, lo pedia y finanzas lo depositaba: el
# agente recibia dinero sin tarjeta en la app, sin plazo y con la
# factura ya hecha.

CANCELADO, EN_FACTURACION, CERRADO = "cancelado", "en_facturacion", "cerrado"

# Lo que ya tiene visto bueno en el cierre de un mes del implantado. El
# servicio implantado no cambia de estatus mes con mes: la fase la lleva
# el cierre de cada mes, y por eso aqui se lee el cierre y no el servicio.
_MES_EN_FACTURACION = (m.EstatusCierre.ENVIADO_FINANZAS,)
_MES_CERRADO = (m.EstatusCierre.APROBADO, m.EstatusCierre.FACTURADO)


def cierre_del_dinero(db: Session, servicio: m.Servicio,
                      anio: int | None = None, mes: int | None = None
                      ) -> tuple[str, datetime | None] | None:
    """Si ya no entra dinero nuevo, por que y desde cuando.

    Devuelve `(motivo, desde)` o None si el servicio sigue abierto al
    dinero. `motivo` es cancelado, en_facturacion o cerrado; `desde` es
    la hora de pared del pais desde la que quedo cerrado --el visto bueno
    del consultor, la aprobacion de finanzas o la cancelacion--, o None
    cuando no hay cierre del que leerla.

    En el eventual lo dice el estatus del servicio: el visto bueno lo
    pone en facturacion, la aprobacion de finanzas lo cierra y el regreso
    de finanzas lo devuelve a sin visto bueno. En el implantado el
    servicio se queda en curso y cierra por mes (seccion 56): con `anio`
    y `mes` se lee el cierre de ese mes.
    """
    cierre = None
    if servicio.tipo == m.TipoServicio.IMPLANTADO and anio and mes:
        contrato = (db.query(m.ContratoImplantado)
                    .filter_by(servicio_id=servicio.id, anio=anio, mes=mes)
                    .first())
        if contrato is not None:
            cierre = (db.query(m.Cierre)
                      .filter_by(contrato_id=contrato.id).first())
    elif servicio.estatus in (m.EstatusServicio.CANCELADO,
                              m.EstatusServicio.CERRADO,
                              m.EstatusServicio.EN_FACTURACION):
        # Solo entonces hace falta el cierre: la bandeja pregunta esto
        # por cada solicitud, y un servicio abierto se contesta sin ir
        # a la base.
        cierre = (db.query(m.Cierre)
                  .filter_by(servicio_id=servicio.id, contrato_id=None)
                  .first())
    else:
        return None

    if servicio.estatus == m.EstatusServicio.CANCELADO:
        return CANCELADO, (cierre.abierto_en if cierre else None)
    if servicio.estatus == m.EstatusServicio.CERRADO:
        return CERRADO, (cierre.enviado_en if cierre else None)
    if servicio.estatus == m.EstatusServicio.EN_FACTURACION:
        return EN_FACTURACION, (cierre.enviado_en if cierre else None)
    if cierre is not None and cierre.contrato_id:
        if cierre.estatus in _MES_CERRADO:
            return CERRADO, cierre.enviado_en
        if cierre.estatus in _MES_EN_FACTURACION:
            return EN_FACTURACION, cierre.enviado_en
    return None


def cerrado_al_dinero(db: Session, servicio: m.Servicio,
                      anio: int | None = None, mes: int | None = None
                      ) -> str | None:
    """Solo el motivo, para las pantallas: cancelado, en_facturacion,
    cerrado, o None si sigue entrando dinero."""
    cierre = cierre_del_dinero(db, servicio, anio, mes)
    return cierre[0] if cierre else None


QUE_HACER_CERRADO = {
    CANCELADO: ("Un servicio cancelado no lleva dinero nuevo. Lo que ya se "
                "había pedido se deposita, se comprueba y se devuelve como "
                "siempre."),
    EN_FACTURACION: ("Si de verdad hace falta más dinero, pídele a finanzas "
                     "que regrese el servicio, muévelo y vuélvanlo a cerrar."),
    # Lo aprobado por finanzas ya no se regresa (lo cerrado se corrige
    # con nota de credito, no reabriendolo), asi que mandar a "regresar"
    # seria mandar a un boton que contesta que no.
    CERRADO: ("Ya lo aprobó finanzas y no se regresa: si de verdad hace "
              "falta más dinero, resuélvelo con finanzas fuera de este "
              "servicio."),
}
NOMBRE_CERRADO = {CANCELADO: "cancelado", EN_FACTURACION: "en facturación",
                  CERRADO: "cerrado"}


def frenar_si_cerrado(db: Session, servicio: m.Servicio,
                      anio: int | None = None, mes: int | None = None) -> None:
    """Una sola puerta para todo el dinero nuevo (seccion 105).

    La llaman abrir o fijar el viatico, agregar un deposito y pedirlo a
    finanzas, en el eventual y en el mes del implantado. No la llaman
    comprobar, devolver ni depositar lo que ya estaba pedido: eso es
    dinero de antes del cierre y sigue su camino.
    """
    motivo = cerrado_al_dinero(db, servicio, anio, mes)
    if not motivo:
        return
    # En el implantado lo que cierra es el mes; el cancelado es el
    # servicio entero.
    que = "El mes" if (anio and mes and motivo != CANCELADO) else "El servicio"
    raise HTTPException(409, {
        "mensaje": f"{que} está {NOMBRE_CERRADO[motivo]}: ya no entra "
                   f"dinero nuevo",
        "que_hacer": QUE_HACER_CERRADO[motivo],
        "motivo": motivo,
    })


def _de_donde(solicitud: m.SolicitudTransferencia) -> tuple:
    """(servicio, anio, mes) de una solicitud: el mes solo en el
    implantado, que es donde cierra el mes y no el servicio."""
    viatico = solicitud.asignacion
    jornada = viatico.jornada if viatico else None
    equipo = jornada.equipo if jornada else None
    servicio = equipo.servicio if equipo else None
    if servicio is not None and servicio.tipo == m.TipoServicio.IMPLANTADO:
        return servicio, jornada.fecha.year, jornada.fecha.month
    return servicio, None, None


def pedida_tras_el_cierre(db: Session, solicitud: m.SolicitudTransferencia
                          ) -> bool:
    """Si esa solicitud nacio con el servicio (o el mes) ya cerrado al dinero.

    No deberia existir --las puertas de arriba ya no la dejan nacer--,
    pero si existe, finanzas no la deposita: la bandeja no le pone
    boton y la ruta la rechaza. Lo pedido antes del cierre se deposita
    como siempre. Sin cierre del que leer la hora se toma como de antes:
    la duda no le quita a nadie un deposito que si iba.
    """
    servicio, anio, mes = _de_donde(solicitud)
    if servicio is None:
        return False
    cierre = cierre_del_dinero(db, servicio, anio, mes)
    if not cierre or cierre[1] is None or solicitud.creada_en is None:
        return False
    # `creada_en` es un instante (con zona); el cierre guarda hora de
    # pared del pais. Se compara en la hora del pais.
    pais = db.get(m.Pais, servicio.pais_id)
    pedida = reloj.ahora_en(pais, solicitud.creada_en)
    return pedida > cierre[1]


def frenar_si_pedida_tras_el_cierre(db: Session,
                                    solicitudes: list) -> None:
    """Finanzas no deposita lo que se pidio con el servicio ya cerrado.

    Con el mismo mensaje que las demas puertas: dice por que y que hacer.
    """
    for solicitud in solicitudes:
        if pedida_tras_el_cierre(db, solicitud):
            servicio, anio, mes = _de_donde(solicitud)
            frenar_si_cerrado(db, servicio, anio, mes)

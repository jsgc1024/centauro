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


def revisar_comprobante(viatico, monto, concepto, descripcion, ahora=None):
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

    entregado = Decimal(str(viatico.monto_total or 0))
    ya = sum((Decimal(str(c.monto)) for c in viatico.comprobantes
              if not c.rechazado), Decimal("0"))

    # Con cero entregado no hay contra que topar: puede ser un dia que el
    # tabulador dejo en cero y el gasto salio igual. Se deja pasar y lo
    # revisa el consultor, que es quien puede decidirlo.
    if entregado > 0 and ya + monto > entregado * TOLERANCIA_COMPROBADO:
        return {"codigo": 409,
                "mensaje": "Ese ticket pasa de lo que se entrego",
                "que_hacer": (f"Lleva comprobado {ya} de {entregado}. Si de "
                              f"verdad se gasto mas, eso se resuelve con "
                              f"viaticos adicionales, no con un comprobante."),
                "entregado": str(entregado), "comprobado": str(ya)}

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
    """El escenario sale de la modalidad del dia y de si es local o foraneo."""
    codigo = jornada.modalidad.codigo
    if codigo == m.CodigoModalidad.FULL_DAY:
        return (m.EscenarioViatico.FULL_DAY_FORANEO if jornada.es_foraneo
                else m.EscenarioViatico.FULL_DAY_LOCAL)
    if codigo == m.CodigoModalidad.MEDIO_DIA:
        return m.EscenarioViatico.MEDIO_DIA
    return m.EscenarioViatico.TRANSFER


def estimar_combustible(db: Session, jornada: m.Jornada, pais_id: int) -> dict | None:
    """Kilometros / rendimiento de la categoria * precio por litro, mas holgura."""
    if not jornada.km_estimados:
        return None

    asignacion_vehiculo = jornada.vehiculos[0] if jornada.vehiculos else None
    if not asignacion_vehiculo:
        return None

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

    return {
        "monto": total,
        "detalle": (f"{jornada.km_estimados} km / "
                    f"{rendimiento} km-l = {litros.quantize(Decimal('0.01'))} l "
                    f"x {parametro.precio_litro} + {parametro.holgura_pct}% de holgura"),
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
            estimado = estimar_combustible(db, jornada, pais.id)
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


def ventana_de_transferencia(fecha_servicio: date, hoy: date | None = None) -> dict:
    """La solicitud se dispara un dia antes del servicio.
    Si el servicio inicia el mismo dia, entra de inmediato al primer barrido."""
    hoy = hoy or date.today()
    dispara_en = fecha_servicio - timedelta(days=1)

    if fecha_servicio <= hoy:
        return {"inmediata": True, "dispara_en": hoy.isoformat(),
                "nota": "El servicio inicia hoy o ya inicio: entra al primer barrido."}
    if dispara_en <= hoy:
        return {"inmediata": True, "dispara_en": hoy.isoformat(),
                "nota": "El servicio inicia manana: entra al barrido de hoy."}
    return {"inmediata": False, "dispara_en": dispara_en.isoformat(),
            "nota": "Queda programada para el barrido del dia previo al servicio."}


def limite_de_comprobacion(termino: datetime) -> datetime:
    """24 horas desde el termino del servicio para cerrar viaticos."""
    return termino + timedelta(hours=HORAS_PARA_COMPROBAR)

# -*- coding: utf-8 -*-
"""Las reglas del GPS de las unidades, sin base de datos (seccion 60).

Todo lo que se decide con lo que dice Pegasus vive aqui y se prueba sin
red ni base: como se lee una unidad, cuando la unidad "viene" al punto y
cuando ya no sale a tiempo, si una marca cuadra con la unidad, cuanto
recorrio en el dia y cuanta gasolina dan esos kilometros.

Las horas que entran son instantes con zona (Pegasus manda UTC); quien
llama las pasa a la hora del pais cuando las compara con una jornada.
"""
import re
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal

KM_POR_MILLA = 1.609344

# Por debajo de esto esta parada: el GPS de una camioneta estacionada
# nunca marca cero parejo.
KMH_EN_MOVIMIENTO = 5
# Durante el servicio, mas que esto sin reportar es "no reporta".
MINUTOS_SIN_SENAL = 10
# En la pantalla de Unidades, "sin senal" es mas de un dia callada: lo
# que hay que ir a revisar al taller, no un tunel.
HORAS_SIN_SENAL = 24

# El camino al punto. Las mismas medidas del telefono (trayecto.py): a
# menos de un kilometro ya esta en el punto, y avanzar menos de 300 m
# entre dos lecturas es no avanzar.
METROS_EN_EL_PUNTO = 1000
METROS_DE_AVANCE = 300
FRACCION_MINIMA = 0.6
# A cuanto se supone que va una camioneta en linea recta para decir que
# ya tendria que haber salido. La linea recta miente a favor --las
# calles dan vuelta-- asi que 40 km/h en linea recta es ir bien.
KMH_DE_REFERENCIA = 40

# El segundo testigo: la unidad a menos de un kilometro de donde se
# marco, cuadra; en el fin, la que se guardo lejos del ultimo punto mas
# de media hora antes de la marca, no.
METROS_TESTIGO = 1000
MINUTOS_GUARDADA = 30
# Una parada de media hora o mas es "se guardo": de ahi a que salio y
# de ahi a que la guardaron se cuentan los kilometros del dia.
MINUTOS_PARADA_LARGA = 30

# La corriente cortada tiene que durar esto para sonar: un brinco de la
# bateria al arrancar no es nadie desconectando el equipo.
MINUTOS_SIN_CORRIENTE = 2

# Lo que Pegasus cuenta como manejo. "aggdrv" no entra: no se sabe que
# junta, y contarlo junto con los otros dos podria contar doble.
EXCESO = "spd"
BRUSCOS = ("posac", "negac")
PANICO = "panic"


# ---------------------------------------------------------------- lectura

def normal_placa(texto) -> str | None:
    """'ABC-123-D ' -> 'ABC123D': asi se compara una placa."""
    s = re.sub(r"[^A-Za-z0-9]", "", str(texto or "")).upper()
    return s or None


def momento(valor) -> datetime | None:
    """Fecha ISO o epoch (segundos o milisegundos). Sin zona es UTC."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        if valor > 1e12:
            valor = valor / 1000
        if 1e9 < valor < 4e9:
            return datetime.fromtimestamp(valor, tz=timezone.utc)
        return None
    if isinstance(valor, str):
        try:
            d = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


def _numero(valor) -> float | None:
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _dato(data: dict, clave: str) -> tuple:
    """(valor, cuando se reporto, desde cuando tiene ese valor)."""
    d = data.get(clave)
    if not isinstance(d, dict):
        return None, None, None
    cambio = d.get("change") if isinstance(d.get("change"), dict) else {}
    return (d.get("value"), momento(d.get("evtime")),
            momento(cambio.get("evtime")))


def _si_no(valor) -> bool | None:
    """Un si/no de Pegasus. Llega como booleano, pero hay equipos que lo
    mandan como 0/1 o como texto; lo demas no se adivina."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)) and valor in (0, 1):
        return bool(valor)
    if isinstance(valor, str) and valor.strip().lower() in ("true", "false",
                                                            "1", "0"):
        return valor.strip().lower() in ("true", "1")
    return None


def kmh(mph) -> int | None:
    n = _numero(mph)
    return None if n is None else int(round(n * KM_POR_MILLA))


def estado_de_la_unidad(u: dict) -> dict:
    """Una unidad de /vehicles, como la guarda Centauro.

    Solo lo que sirve: placa, que auto es, y lo ultimo que dijo su
    equipo. El nombre de la unidad en Pegasus no se toma --a veces trae
    el de una persona-- ni el VIN ni el IMEI."""
    info = u.get("info") if isinstance(u.get("info"), dict) else {}
    equipo = u.get("device") if isinstance(u.get("device"), dict) else {}
    ultimo = equipo.get("latest") if isinstance(equipo.get("latest"), dict) else {}
    loc = ultimo.get("loc") if isinstance(ultimo.get("loc"), dict) else {}
    data = ultimo.get("data") if isinstance(ultimo.get("data"), dict) else {}
    cuentas = (ultimo.get("counters")
               if isinstance(ultimo.get("counters"), dict) else {})
    vcuentas = (ultimo.get("vcounters")
                if isinstance(ultimo.get("vcounters"), dict) else {})

    # La hora del ultimo reporte: la de su posicion, o la mas nueva que
    # traiga cualquiera de sus datos.
    horas = [momento(loc.get("evtime")), momento(cuentas.get("evtime"))]
    horas += [momento(v.get("evtime")) for v in data.values()
              if isinstance(v, dict)]
    horas = [h for h in horas if h]
    reporte = momento(loc.get("evtime")) or (max(horas) if horas else None)

    lat = _numero(loc.get("lat"))
    lon = _numero(loc.get("lon"))
    if lat is None or lon is None:
        lat, lon = _numero(_dato(data, "lat")[0]), _numero(_dato(data, "lon")[0])
    if lat is not None and lon is not None and lat == 0 and lon == 0:
        lat = lon = None

    mph = loc.get("mph") if loc.get("mph") is not None else _dato(data, "mph")[0]
    velocidad = kmh(mph)
    anda_dato, _cuando, anda_desde = _dato(data, "moving")
    anda = _si_no(anda_dato)
    if anda is None:
        anda = _si_no(loc.get("moving"))
    if isinstance(anda, bool):
        en_movimiento = anda
    elif velocidad is not None:
        en_movimiento = velocidad >= KMH_EN_MOVIMIENTO
    else:
        en_movimiento = None
    parada_desde = None
    if en_movimiento is False:
        if isinstance(anda, bool):
            parada_desde = anda_desde
        else:
            valor_mph, _c, desde_mph = _dato(data, "mph")
            if _numero(valor_mph) == 0:
                parada_desde = desde_mph

    encendida, _c1, encendida_desde = _dato(data, "io_ign")
    corriente, _c2, corriente_desde = _dato(data, "io_pwr")
    inhibidor, _c3, inhibidor_desde = _dato(data, "jamm_detected")
    encendida, corriente, inhibidor = (_si_no(encendida), _si_no(corriente),
                                       _si_no(inhibidor))

    odometro = _numero(vcuentas.get("vehicle_dev_dist"))
    if not odometro:
        odometro = _numero(cuentas.get("dev_dist"))
    marca = " ".join(str(info.get(k) or "").strip().title()
                     for k in ("make", "model")).strip() or None
    anio = _numero(info.get("year"))

    return {
        "pegasus_id": int(u["id"]),
        "placa": (str(info.get("license_plate") or "").strip()[:20] or None),
        "placa_normal": normal_placa(info.get("license_plate")),
        "marca_modelo": marca[:80] if marca else None,
        "color": (str(info.get("color") or "").strip()[:40] or None),
        "anio": int(anio) if anio and 1950 < anio < 2100 else None,
        "reporte_en": reporte,
        "lat": lat, "lon": lon,
        "velocidad_kmh": velocidad,
        "en_movimiento": en_movimiento,
        "parada_desde": parada_desde,
        "encendida": encendida if isinstance(encendida, bool) else None,
        "encendida_desde": encendida_desde if isinstance(encendida, bool) else None,
        "corriente": corriente if isinstance(corriente, bool) else None,
        "corriente_desde": corriente_desde if isinstance(corriente, bool) else None,
        "inhibidor": inhibidor if isinstance(inhibidor, bool) else None,
        "inhibidor_desde": inhibidor_desde if isinstance(inhibidor, bool) else None,
        "odometro_km": round(odometro / 1000, 1) if odometro else None,
    }


def callada(reporte_en: datetime | None, ahora: datetime,
            minutos: int = MINUTOS_SIN_SENAL) -> bool:
    """Si hace mas de `minutos` que no reporta (o nunca reporto)."""
    if reporte_en is None:
        return True
    return (ahora - reporte_en).total_seconds() / 60 > minutos


# ---------------------------------------------------------------- el camino

def evaluar_camino(distancia_m: int, anterior_m: int | None,
                   minutos_entre: float | None, minutos_faltan: float,
                   en_movimiento: bool | None,
                   apagada: bool | None) -> tuple[str, str | None]:
    """Como va la unidad que tiene que llegar al punto.

    La misma regla del telefono (seccion 38): linea recta y reloj, sin
    preguntarle a Google, y se alerta solo cuando va claramente corta.
    Devuelve el estado y, si hay que alertar, el motivo:

      en_el_punto  a menos de un kilometro; ya no dice nada del camino
      viene        se mueve y se acerca, y le alcanza
      se_mueve     se mueve, todavia no se sabe hacia donde
      quieta       parada, pero todavia tiene tiempo de salir
      no_sale      parada, y ya no le alcanza el tiempo
      no_llega     se mueve, pero ya no le alcanza
    """
    if distancia_m <= METROS_EN_EL_PUNTO:
        return "en_el_punto", None
    km = distancia_m / 1000
    necesarios = km / KMH_DE_REFERENCIA * 60

    if en_movimiento:
        if anterior_m is None:
            return "se_mueve", None
        avance = anterior_m - distancia_m
        if avance >= METROS_DE_AVANCE:
            if minutos_faltan <= 0:
                return "no_llega", ("trae una unidad que sigue en camino y la "
                                    "hora de estar en el punto ya paso")
            necesita = distancia_m / minutos_faltan
            lleva = avance / max(1.0, minutos_entre or 0)
            if lleva < necesita * FRACCION_MINIMA:
                return "no_llega", (f"trae una unidad que va a "
                                    f"{lleva * 60 / 1000:.0f} km/h en linea "
                                    f"recta y le faltan {km:.0f} km en "
                                    f"{int(minutos_faltan)} min")
            return "viene", None
        if minutos_faltan < necesarios:
            return "no_llega", ("trae una unidad que se mueve pero no se "
                                f"acerca al punto: esta a {km:.0f} km y ya "
                                "no le alcanza el tiempo")
        return "se_mueve", None

    if minutos_faltan < necesarios:
        como = "apagada" if apagada else "parada"
        return "no_sale", (f"trae una unidad que sigue {como} a {km:.0f} km "
                           "del punto y ya tendria que haber salido")
    return "quieta", None


# ---------------------------------------------------------------- el testigo

def veredicto_marca(distancia_m: int | None) -> str | None:
    """ok si la unidad estaba donde se marco; alerta si no; nada si no
    hubo como saberlo."""
    if distancia_m is None:
        return None
    return "ok" if distancia_m <= METROS_TESTIGO else "alerta"


def veredicto_fin(marca: datetime, guardada_en: datetime | None,
                  guardada_m: int | None,
                  distancia_m: int | None) -> str | None:
    """El fin no cuadra cuando la unidad ya se habia guardado lejos del
    ultimo punto mas de media hora antes de la marca. Si se quedo
    estacionada donde estaba el principal, es normal."""
    if (guardada_en is not None and guardada_m is not None
            and guardada_m > METROS_TESTIGO
            and (marca - guardada_en).total_seconds() / 60 > MINUTOS_GUARDADA):
        return "alerta"
    if distancia_m is not None:
        return veredicto_marca(distancia_m)
    if guardada_en is not None:
        return "ok"
    return None


def mas_cercano(eventos: list[dict], cuando: datetime,
                antes_min: int = 5, despues_min: int = 3) -> dict | None:
    """El evento con posicion mas cercano a una hora, dentro de la
    ventana."""
    mejor, mejor_dif = None, None
    for e in eventos:
        m = momento(e.get("event_time"))
        lat, lon = _numero(e.get("lat")), _numero(e.get("lon"))
        if m is None or lat is None or lon is None or (lat == 0 and lon == 0):
            continue
        dif = (m - cuando).total_seconds() / 60
        if dif < -antes_min or dif > despues_min:
            continue
        if mejor_dif is None or abs(dif) < mejor_dif:
            mejor, mejor_dif = {**e, "_momento": m, "_lat": lat, "_lon": lon}, abs(dif)
    return mejor


# ---------------------------------------------------------------- los tramos

def tramos_ordenados(tramos: list[dict]) -> list[dict]:
    """Los tramos de Pegasus, con horas y kilometros de verdad."""
    salida = []
    for t in tramos:
        inicio = momento(t.get("start_time"))
        if inicio is None:
            continue
        distancia = _numero(t.get("distance"))
        if distancia is None:
            distancia = _numero(t.get("dev_dist"))
        salida.append({
            "movimiento": bool(t.get("moving")),
            "inicio": inicio,
            "fin": momento(t.get("end_time")),
            "km": (distancia or 0) / 1000,
            "lat": _numero(t.get("start_lat")),
            "lon": _numero(t.get("start_lon")),
            "vid": t.get("vid"),
        })
    salida.sort(key=lambda t: t["inicio"])
    return salida


def _fin(t: dict, ahora: datetime) -> datetime:
    return t["fin"] or ahora


def parada_en(tramos: list[dict], cuando: datetime,
              ahora: datetime) -> dict | None:
    """La parada que estaba corriendo a esa hora, si la unidad estaba
    parada. Con dos minutos de holgura: la parada puede cerrar un poco
    antes de la marca por el retraso de los reportes."""
    for t in tramos:
        if t["movimiento"]:
            continue
        if t["inicio"] <= cuando <= _fin(t, ahora) + timedelta(minutes=2):
            return t
    return None


def _larga(t: dict, ahora: datetime) -> bool:
    return (not t["movimiento"]
            and (_fin(t, ahora) - t["inicio"]).total_seconds() / 60
            >= MINUTOS_PARADA_LARGA)


def ventana_del_dia(tramos: list[dict], llegada: datetime, fin: datetime,
                    ahora: datetime) -> tuple[datetime, datetime] | None:
    """De que salio hacia el punto a que se guardo despues del fin.

    Salio: al terminar la ultima parada larga antes de la llegada. Se
    guardo: al empezar la primera parada larga despues del fin. Sin
    tramos no hay dia."""
    if not tramos:
        return None
    antes = [t for t in tramos if _larga(t, ahora) and _fin(t, ahora) <= llegada]
    desde = _fin(antes[-1], ahora) if antes else tramos[0]["inicio"]
    despues = [t for t in tramos if _larga(t, ahora) and t["inicio"] >= fin]
    hasta = despues[0]["inicio"] if despues else max(_fin(t, ahora) for t in tramos)
    if hasta <= desde:
        return None
    return desde, hasta


def km_en(tramos: list[dict], desde: datetime, hasta: datetime,
          ahora: datetime) -> float:
    """Los kilometros de los trayectos dentro de la ventana. Un trayecto
    que la cruza cuenta en proporcion al rato que cae adentro."""
    total = 0.0
    for t in tramos:
        if not t["movimiento"] or t["km"] <= 0:
            continue
        ini, fin = t["inicio"], _fin(t, ahora)
        dentro = (min(fin, hasta) - max(ini, desde)).total_seconds()
        if dentro <= 0:
            continue
        largo = (fin - ini).total_seconds()
        total += t["km"] * (min(1.0, dentro / largo) if largo > 0 else 1.0)
    return round(total, 1)


def contar_manejo(eventos: list[dict], desde: datetime,
                  hasta: datetime) -> tuple[int, int]:
    """(excesos, bruscos) dentro de la ventana."""
    excesos = bruscos = 0
    for e in eventos:
        m = momento(e.get("event_time"))
        if m is None or not (desde <= m <= hasta):
            continue
        etiqueta = str(e.get("label") or "").lower()
        if etiqueta == EXCESO:
            excesos += 1
        elif etiqueta in BRUSCOS:
            bruscos += 1
    return excesos, bruscos


def duracion_hacia_atras(desde: datetime, ahora: datetime,
                         margen_min: int = 2) -> str:
    """La duracion ISO que alcanza desde `desde` hasta ahora, con margen.
    Nunca mas de tres dias: lo viejo ya no se busca."""
    minutos = int((ahora - desde).total_seconds() // 60) + margen_min
    minutos = max(5, min(minutos, 3 * 24 * 60))
    return f"PT{minutos}M"


# ---------------------------------------------------------------- la gasolina

def cuenta_gasolina(km, rendimiento, precio, holgura_pct) -> Decimal | None:
    """La misma cuenta del deposito (viaticos.estimar_combustible), con
    los kilometros que dio el GPS: km entre el rendimiento de la
    categoria, por el precio del litro, mas la holgura; al entero de
    arriba, como el deposito."""
    if km is None or not rendimiento or Decimal(str(rendimiento)) <= 0:
        return None
    litros = Decimal(str(km)) / Decimal(str(rendimiento))
    base = litros * Decimal(str(precio))
    total = base * (Decimal("1") + Decimal(str(holgura_pct)) / Decimal("100"))
    return total.quantize(Decimal("1"), rounding=ROUND_CEILING)


# ---------------------------------------------------------------- el manejo

def valor_manejo(km: float, eventos: int,
                 puntos_por_evento) -> tuple[Decimal, Decimal]:
    """(valor de 0 a 100, eventos por cada mil km)."""
    por_mil = Decimal(str(eventos)) / (Decimal(str(km)) / Decimal("1000"))
    valor = Decimal("100") - por_mil * Decimal(str(puntos_por_evento))
    return max(Decimal("0"), valor), por_mil

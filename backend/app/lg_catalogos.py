# -*- coding: utf-8 -*-
"""Centauro Logistica, bloque 1: los catalogos con vigencia por fecha
(seccion 150).

Lo que el margen, el anticipo y la nomina de cada viaje van a usar,
capturado una vez y con su fecha. La especificacion lo pide asi: montos y
reglas en catalogos con vigencia, nunca fijos en el codigo, y un viaje
cerrado conserva las tarifas con las que se calculo.

Ocho catalogos en dos grupos (decision de Salvador, 3 oct):

  - Los que deciden dinero los fija la gerencia de Logistica --Karla
    Rios--: el tabulador de comisiones; el diesel con la holgura del
    anticipo y la tolerancia del rendimiento; los alimentos por dia y el
    margen minimo; el costo del operador; el rendimiento y el costo por
    dia de cada tipo de unidad; el bono de movilidad y la garantia del
    tracto.
  - Los tipos de unidad y los patios los lleva sistema y calidad.

Las reglas de la vigencia, en un solo lugar:

  1. Cada valor rige desde su fecha. Uno nuevo no borra el anterior:
     cada viaje toma el que regia en su fecha.
  2. Lo que ya rige no se edita. Un error se corrige capturando el bueno
     desde la misma fecha, con su porque; el malo se queda marcado como
     reemplazado, con quien y cuando.
  3. Lo programado --fecha que no ha llegado-- se corrige o se quita
     mientras no llega su dia.
  4. Con fecha pasada se puede, pero pide el motivo.

Nada se siembra con montos: arranca con los cuatro tipos y Base
Cuautitlan, y la pantalla dice que falta y quien lo da.
"""
import json
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import accesos, reloj
from app import models as m

CENTAVO = Decimal("0.01")
DIAS_DEL_ANIO = Decimal(365)

# Con lo que arranca (decision de Salvador, 3 oct). La migracion trae la
# misma lista; una prueba cuida que digan lo mismo.
TIPOS_DE_ARRANQUE = (("1.5 ton", "1.5", "1.5 t"),
                     ("4 ton", "4", "4 t seco"),
                     ("Torton 15 ton", "15", "TH"),
                     ("Tracto", None, "Tracto"))
PATIO_DE_ARRANQUE = ("Base Cuautitlán", 300)

# Los ocho catalogos de la pantalla, en su orden. Los seis primeros
# deciden dinero.
CATALOGOS = ("tabulador", "diesel", "alimentos", "operador", "costos",
             "bono", "tipos", "patios")
DE_DINERO = CATALOGOS[:6]
DE_SISTEMA = CATALOGOS[6:]
# Con que nombre entra cada uno a la bitacora de administracion.
OBJETOS = tuple(f"lg_{c}" for c in CATALOGOS)

# Cada valor que se captura con su fecha, y de que catalogo es.
PARAMETROS = {
    "tabulador": "tabulador",
    "diesel": "diesel", "holgura": "diesel", "tolerancia": "diesel",
    "alimentos": "alimentos", "margen": "alimentos",
    "operador": "operador",
    "unidad": "costos",
    "bono": "bono", "garantia": "bono",
}
# Los que son de un tipo de unidad.
POR_TIPO = {"unidad"}
CLAVES_DE: dict[str, list[str]] = {}
for _clave, _catalogo in PARAMETROS.items():
    CLAVES_DE.setdefault(_catalogo, []).append(_clave)

# Quien da lo que falta, cuando no lo decide la gerencia: lo dice la
# especificacion en sus pendientes.
LO_DA = {"operador": "rh", "bono": "rh", "garantia": "rh", "unidad": "flota"}

# El ejemplo de la tabla del tabulador: el viaje del mapa operativo del
# boceto, 1,450 km cargados.
KM_DE_EJEMPLO = Decimal(1450)

# Hasta donde llega una fecha. No es regla de negocio: es el tope de un
# dedazo en el ano.
DESDE_MINIMO = date(2020, 1, 1)
DIAS_HACIA_ADELANTE = 730


class FaltaValor(Exception):
    """Lo que un calculo pide y no hay para esa fecha."""

    def __init__(self, clave: str, fecha: date, tipo: str | None = None):
        self.clave, self.fecha, self.tipo = clave, fecha, tipo
        de = f" de {tipo}" if tipo else ""
        super().__init__(f"No hay {NOMBRES['es'][clave].lower()}{de} que "
                         f"rija el {fecha.strftime('%d/%m/%Y')}.")


def hoy_lg() -> date:
    """Que dia es en Logistica: solo opera en Mexico."""
    return reloj.hoy_en(None)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _no(detalle, codigo: int = 400):
    """El «no se puede», con su que hacer cuando lo hay. El que trae que
    hacer va como diccionario escrito aqui mismo: asi lo encuentra el
    manual del sistema y sale en su lista de mensajes."""
    if isinstance(detalle, str):
        detalle = {"mensaje": detalle}
    return HTTPException(codigo, detalle)


# ================================================================ numeros

def _numero(valor, nombre: str, minimo=None, maximo=None, mayor_que=None,
            entero: bool = False, decimales: int = 4) -> Decimal:
    """Un numero de la captura, revisado. La coma no se acepta: en la
    mitad del mundo es el punto decimal, y «24,34» leido como 2434 es
    justo el dedazo que se cuela."""
    cap = f"{nombre[0].upper()}{nombre[1:]}"
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise _no(f"Falta {nombre}.")
    if isinstance(valor, bool):
        raise _no(f"{cap}: no es un número.")
    try:
        d = Decimal(str(valor).strip())
    except InvalidOperation:
        raise _no({"mensaje": f"{cap}: «{valor}» no es un número.",
                   "que_hacer": "Escríbelo con punto decimal y sin comas."})
    if not d.is_finite():
        raise _no(f"{cap}: no es un número.")
    if entero and d != d.to_integral_value():
        raise _no(f"{cap}: va sin decimales.")
    if mayor_que is not None and d <= Decimal(mayor_que):
        raise _no(f"{cap}: tiene que ser mayor que {mayor_que}.")
    if minimo is not None and d < Decimal(minimo):
        raise _no(f"{cap}: no puede ser menor que {minimo}.")
    if maximo is not None and d > Decimal(maximo):
        raise _no({"mensaje": f"{cap}: no puede pasar de {maximo}.",
                   "que_hacer": "Revisa el punto decimal."})
    if not entero and d.as_tuple().exponent < -decimales:
        raise _no(f"{cap}: lleva a lo más {decimales} decimales.")
    return d


def _txt(d: Decimal) -> str:
    """Como se guarda un numero en el JSON: sin ceros de mas, sin
    notacion cientifica. «220.00» -> «220», «0.520» -> «0.52»."""
    texto = format(d.normalize(), "f")
    return "0" if texto in ("-0", "") else texto


def _dec(texto) -> Decimal:
    return Decimal(str(texto))


def _centavos(d: Decimal) -> Decimal:
    return d.quantize(CENTAVO, rounding=ROUND_HALF_UP)


# ================================================================ los calculos
#
# Sobre los datos de un renglon, sin tocar la base: asi los prueban los
# ejemplos de los bocetos sin armar nada, y los bloques que siguen
# --el margen, la nomina-- calculan con el renglon que guardaron.

def comision_con(datos: dict, tipo_unidad_id: int, km_cargados) -> dict | None:
    """La comision del operador por un viaje: un monto por los primeros
    km cargados y otro por cada km cargado adicional. Km cargados son los
    de la ruta planeada con carga mas los adicionales autorizados, nunca
    los del odometro. Sin el tipo en el tabulador, None."""
    del_tipo = (datos.get("tipos") or {}).get(str(tipo_unidad_id))
    if not del_tipo:
        return None
    km = _dec(km_cargados)
    km_base = _dec(datos["km_base"])
    base = _dec(del_tipo["base"])
    por_km = _dec(del_tipo["por_km"])
    km_extra = max(km - km_base, Decimal(0))
    extra = _centavos(km_extra * por_km)
    return {"comision": _centavos(base + extra), "base": base,
            "km_base": km_base, "km": km, "km_extra": km_extra,
            "por_km": por_km, "extra": extra}


def costo_operador_con(datos: dict) -> Decimal:
    """Lo que cuesta un dia de operador: lo que cuesta al mes --salario,
    prestaciones y cuotas-- entre los dias laborables del mes."""
    return _centavos(_dec(datos["costo_mensual"]) / _dec(datos["dias_laborables"]))


COMPONENTES_UNIDAD = ("depreciacion", "seguro", "mantenimiento", "llantas",
                      "gps")


def costo_unidad_con(datos: dict) -> dict:
    """El costo por dia de un tipo de unidad, por componente, como en el
    boceto de Flota: depreciacion (compra / anos de vida / 365), seguro,
    mantenimiento, llantas y GPS-verificacion-tenencia (cada uno al ano /
    365). Cada componente se redondea a centavos y el total es su suma:
    asi el desglose de la pantalla cuadra a la vista."""
    partes = {
        "depreciacion": _centavos(_dec(datos["compra"]) / _dec(datos["anios"])
                                  / DIAS_DEL_ANIO),
        "seguro": _centavos(_dec(datos["seguro"]) / DIAS_DEL_ANIO),
        "mantenimiento": _centavos(_dec(datos["mantenimiento"]) / DIAS_DEL_ANIO),
        "llantas": _centavos(_dec(datos["llantas"]) / DIAS_DEL_ANIO),
        "gps": _centavos(_dec(datos["gps"]) / DIAS_DEL_ANIO),
    }
    partes["costo_dia"] = sum(partes.values(), Decimal(0))
    return partes


def bono_con(datos: dict, anios_cumplidos: int) -> Decimal:
    """El porcentaje del bono de movilidad por antiguedad: el del tramo
    mas alto al que ya llego. Los anos son cumplidos."""
    pct = Decimal(0)
    for tramo in sorted(datos["tramos"], key=lambda x: int(x["desde_anios"])):
        if int(anios_cumplidos) >= int(tramo["desde_anios"]):
            pct = _dec(tramo["pct"])
    return pct


# ================================================================ la vigencia

def _vivos(db: Session, clave: str, tipo_unidad_id: int | None = None):
    consulta = db.query(m.LgValor).filter(
        m.LgValor.clave == clave,
        m.LgValor.reemplazado_en.is_(None), m.LgValor.quitado_en.is_(None))
    if tipo_unidad_id:
        return consulta.filter(m.LgValor.tipo_unidad_id == tipo_unidad_id)
    return consulta.filter(m.LgValor.tipo_unidad_id.is_(None))


def vigente(db: Session, clave: str, fecha: date | None = None,
            tipo_unidad_id: int | None = None) -> m.LgValor | None:
    """El renglon que rige en esa fecha: el vivo con la fecha mas reciente
    que no la pase. Un viaje guarda este renglon y no el numero suelto:
    asi conserva lo que uso aunque despues cambie."""
    fecha = fecha or hoy_lg()
    return (_vivos(db, clave, tipo_unidad_id)
            .filter(m.LgValor.vigente_desde <= fecha)
            .order_by(m.LgValor.vigente_desde.desc(), m.LgValor.id.desc())
            .first())


def datos_de(fila: m.LgValor) -> dict:
    return json.loads(fila.datos) if fila.datos else {}


def _nombre_tipo(db: Session, tipo_unidad_id) -> str | None:
    tipo = db.get(m.LgTipoUnidad, tipo_unidad_id) if tipo_unidad_id else None
    return tipo.nombre if tipo else None


def numero(db: Session, clave: str, fecha: date | None = None) -> Decimal:
    """El de un solo numero que rige: el diesel, la holgura, la
    tolerancia, los alimentos o el margen."""
    fecha = fecha or hoy_lg()
    fila = vigente(db, clave, fecha)
    if fila is None or fila.valor is None:
        raise FaltaValor(clave, fecha)
    return Decimal(fila.valor)


def comision(db: Session, tipo_unidad_id: int, km_cargados,
             fecha: date | None = None) -> dict:
    """La comision de un viaje con el tabulador que regia en su fecha."""
    fecha = fecha or hoy_lg()
    fila = vigente(db, "tabulador", fecha)
    if fila is None:
        raise FaltaValor("tabulador", fecha)
    calculo = comision_con(datos_de(fila), tipo_unidad_id, km_cargados)
    if calculo is None:
        raise FaltaValor("tabulador", fecha, _nombre_tipo(db, tipo_unidad_id))
    return {**calculo, "valor_id": fila.id, "vigente_desde": fila.vigente_desde}


def costo_operador(db: Session, fecha: date | None = None) -> dict:
    fecha = fecha or hoy_lg()
    fila = vigente(db, "operador", fecha)
    if fila is None:
        raise FaltaValor("operador", fecha)
    datos = datos_de(fila)
    return {"costo_dia": costo_operador_con(datos),
            "costo_mensual": _dec(datos["costo_mensual"]),
            "dias_laborables": int(datos["dias_laborables"]),
            "valor_id": fila.id, "vigente_desde": fila.vigente_desde}


def costo_unidad(db: Session, tipo_unidad_id: int,
                 fecha: date | None = None) -> dict:
    """El rendimiento y el costo por dia de un tipo de unidad. Sirven
    para el alta del viaje, cuando todavia no hay unidad asignada."""
    fecha = fecha or hoy_lg()
    fila = vigente(db, "unidad", fecha, tipo_unidad_id)
    if fila is None:
        raise FaltaValor("unidad", fecha, _nombre_tipo(db, tipo_unidad_id))
    datos = datos_de(fila)
    return {**costo_unidad_con(datos), "rendimiento": _dec(datos["rendimiento"]),
            "valor_id": fila.id, "vigente_desde": fila.vigente_desde}


def bono_pct(db: Session, anios_cumplidos: int,
             fecha: date | None = None) -> Decimal:
    fecha = fecha or hoy_lg()
    fila = vigente(db, "bono", fecha)
    if fila is None:
        raise FaltaValor("bono", fecha)
    return bono_con(datos_de(fila), anios_cumplidos)


# ================================================================ la captura

def _activos(db: Session) -> list[m.LgTipoUnidad]:
    return (db.query(m.LgTipoUnidad).filter(m.LgTipoUnidad.activo.is_(True))
            .order_by(m.LgTipoUnidad.orden, m.LgTipoUnidad.id).all())


PORCENTAJES = {"holgura": "la holgura del anticipo",
               "tolerancia": "la tolerancia de rendimiento",
               "margen": "el margen mínimo"}


def _validar(db: Session, clave: str, entrada: dict) -> tuple:
    """Lo capturado, revisado y en su forma de guardar: (valor, datos)."""
    if clave == "diesel":
        return _numero(entrada.get("valor"), "el precio por litro",
                       mayor_que=0, maximo=100, decimales=4), None
    if clave in PORCENTAJES:
        return _numero(entrada.get("valor"), PORCENTAJES[clave], minimo=0,
                       maximo=100, decimales=2), None
    if clave == "alimentos":
        return _numero(entrada.get("valor"), "el monto por día", mayor_que=0,
                       maximo=10000, decimales=2), None

    datos = entrada.get("datos")
    if not isinstance(datos, dict):
        raise _no("Faltan los datos de este valor.")

    if clave == "operador":
        costo = _numero(datos.get("costo_mensual"),
                        "el costo mensual por operador", mayor_que=0,
                        maximo=1000000, decimales=2)
        dias = _numero(datos.get("dias_laborables"),
                       "los días laborables al mes", minimo=1, maximo=31,
                       entero=True)
        return None, {"costo_mensual": _txt(costo), "dias_laborables": int(dias)}

    if clave == "unidad":
        def anual(campo, nombre):
            return _txt(_numero(datos.get(campo), nombre, minimo=0,
                                maximo=100000000, decimales=2))
        return None, {
            "rendimiento": _txt(_numero(datos.get("rendimiento"),
                                        "el rendimiento (km por litro)",
                                        mayor_que=0, maximo=50, decimales=2)),
            "compra": anual("compra", "el valor de compra"),
            "anios": _txt(_numero(datos.get("anios"), "los años de vida",
                                  mayor_que=0, maximo=50, decimales=1)),
            "seguro": anual("seguro", "el seguro al año"),
            "mantenimiento": anual("mantenimiento", "el mantenimiento al año"),
            "llantas": anual("llantas", "las llantas al año"),
            "gps": anual("gps", "el GPS, la verificación y la tenencia al año"),
        }

    if clave == "tabulador":
        km_base = _numero(datos.get("km_base"),
                          "los km que cubre el primer monto", minimo=0,
                          maximo=10000, entero=True)
        tipos_in = datos.get("tipos")
        if not isinstance(tipos_in, dict):
            raise _no("Faltan los montos de cada tipo de unidad.")
        activos = _activos(db)
        if not activos:
            raise _no({"mensaje": "No hay tipos de unidad.",
                       "que_hacer": "Sistema y calidad los da de alta en «Tipos de unidad»."})
        conocidos = {str(t.id) for t in activos}
        extranos = set(map(str, tipos_in)) - conocidos
        if extranos:
            raise _no("El tabulador trae un tipo de unidad que no existe o "
                      "ya se quitó.")
        salida = {}
        for tipo in activos:
            del_tipo = tipos_in.get(str(tipo.id)) or {}
            if not isinstance(del_tipo, dict):
                del_tipo = {}
            base = _numero(del_tipo.get("base"),
                           f"el monto de los primeros {int(km_base)} km de "
                           f"{tipo.nombre}", minimo=0, maximo=100000,
                           decimales=2)
            por_km = _numero(del_tipo.get("por_km"),
                             f"el monto por km adicional de {tipo.nombre}",
                             minimo=0, maximo=1000, decimales=4)
            salida[str(tipo.id)] = {"base": _txt(base), "por_km": _txt(por_km)}
        return None, {"km_base": int(km_base), "tipos": salida}

    if clave == "bono":
        tramos_in = datos.get("tramos")
        if not isinstance(tramos_in, list) or not tramos_in:
            raise _no("Falta al menos un tramo del bono.")
        if len(tramos_in) > 6:
            raise _no("El bono lleva a lo más seis tramos.")
        tramos = []
        for tramo in tramos_in:
            if not isinstance(tramo, dict):
                raise _no("Un tramo del bono viene mal.")
            desde = _numero(tramo.get("desde_anios"),
                            "desde cuántos años cumplidos", minimo=0,
                            maximo=60, entero=True)
            pct = _numero(tramo.get("pct"), "el porcentaje del bono",
                          minimo=0, maximo=100, decimales=2)
            tramos.append((int(desde), pct))
        tramos.sort(key=lambda x: x[0])
        if tramos[0][0] != 0:
            raise _no({"mensaje": "El primer tramo del bono empieza en 0 años.",
                       "que_hacer": "Así nadie se queda sin porcentaje."})
        if len({d for d, _ in tramos}) != len(tramos):
            raise _no("Dos tramos del bono empiezan en los mismos años.")
        dias = _numero(datos.get("dias_requeridos"),
                       "los días de jornada que pide el bono", minimo=1,
                       maximo=7, entero=True)
        return None, {"tramos": [{"desde_anios": d, "pct": _txt(p)}
                                 for d, p in tramos],
                      "dias_requeridos": int(dias)}

    if clave == "garantia":
        try:
            tipo_id = int(datos.get("tipo_unidad_id"))
        except (TypeError, ValueError):
            tipo_id = None
        tipo = db.get(m.LgTipoUnidad, tipo_id) if tipo_id else None
        if tipo is None or not tipo.activo:
            raise _no("Escoge el tipo de unidad de la garantía.")
        monto = _numero(datos.get("monto_semanal"),
                        "el monto de la garantía semanal", minimo=0,
                        maximo=100000, decimales=2)
        exige = datos.get("exige_dias_completos")
        sobre = datos.get("bono_sobre_garantia")
        if not isinstance(exige, bool) or not isinstance(sobre, bool):
            raise _no({"mensaje": "Faltan las dos reglas de la garantía.",
                       "que_hacer": "Si exige los días completos y si el bono se calcula "
                                    "sobre la garantía: sí o no."})
        return None, {"tipo_unidad_id": tipo.id, "monto_semanal": _txt(monto),
                      "exige_dias_completos": exige,
                      "bono_sobre_garantia": sobre}

    raise _no(f"No existe el valor «{clave}».")


def _tipo_del_parametro(db: Session, clave: str, tipo_unidad_id) -> int | None:
    if clave not in POR_TIPO:
        if tipo_unidad_id:
            raise _no("Este valor no es de un tipo de unidad.")
        return None
    tipo = db.get(m.LgTipoUnidad, tipo_unidad_id) if tipo_unidad_id else None
    if tipo is None or not tipo.activo:
        raise _no("Escoge el tipo de unidad.")
    return tipo.id


def _revisar_fecha(fecha: date, hoy: date) -> None:
    if fecha is None:
        raise _no("Falta desde cuándo rige.")
    if fecha < DESDE_MINIMO or fecha > hoy + timedelta(days=DIAS_HACIA_ADELANTE):
        raise _no({"mensaje": "Esa fecha no se ve bien.",
                   "que_hacer": "Revisa el año: rige desde una fecha de los últimos años "
                                "o de los dos que siguen."})


def _compacto(fila: m.LgValor) -> str:
    """Lo capturado tal cual, para la columna «Después» del Excel de la
    bitacora: quien audita ve lo que se guardo."""
    if fila.valor is not None:
        return _txt(Decimal(fila.valor))
    return (fila.datos or "")[:200]


def _nuevo(db: Session, actor: m.Usuario, clave: str, tipo_unidad_id,
           fecha: date, valor, datos, motivo) -> m.LgValor:
    fila = m.LgValor(
        clave=clave, tipo_unidad_id=tipo_unidad_id, valor=valor,
        datos=json.dumps(datos, ensure_ascii=False) if datos is not None else None,
        vigente_desde=fecha, motivo=motivo, capturado_por_id=actor.persona_id,
        capturado_en=_ahora())
    db.add(fila)
    db.flush()
    return fila


def capturar(db: Session, actor: m.Usuario, clave: str, vigente_desde: date,
             entrada: dict, tipo_unidad_id: int | None = None,
             motivo: str | None = None, hoy: date | None = None) -> m.LgValor:
    """Un valor nuevo desde una fecha.

    Si ya hay uno vivo desde esa misma fecha, este lo reemplaza: si aquel
    ya regia, pide el porque; si estaba programado, no. Con fecha que ya
    paso, tambien pide el porque."""
    if clave not in PARAMETROS:
        raise _no(f"No existe el valor «{clave}».")
    tipo_unidad_id = _tipo_del_parametro(db, clave, tipo_unidad_id)
    hoy = hoy or hoy_lg()
    _revisar_fecha(vigente_desde, hoy)
    motivo = (motivo or "").strip()[:200] or None
    valor, datos = _validar(db, clave, entrada)

    anterior = (_vivos(db, clave, tipo_unidad_id)
                .filter(m.LgValor.vigente_desde == vigente_desde).first())
    if anterior is not None and anterior.vigente_desde <= hoy and not motivo:
        raise _no({"mensaje": "Ya hay un valor que rige desde esa fecha.",
                   "que_hacer": "Para corregirlo, escribe por qué: el de antes se queda "
                                "marcado como reemplazado."})
    if anterior is None and vigente_desde < hoy and not motivo:
        raise _no({"mensaje": "Es una fecha que ya pasó: escribe por qué.",
                   "que_hacer": "Los viajes ya cerrados conservan lo que usaron; los "
                                "abiertos se recalculan con este."})

    nuevo = _nuevo(db, actor, clave, tipo_unidad_id, vigente_desde, valor,
                   datos, motivo)
    if anterior is not None:
        anterior.reemplazado_en = _ahora()
        anterior.reemplazado_por_id = nuevo.id
    accesos.anotar(db, actor,
                   "lg valor reemplazado" if anterior else "lg valor puesto",
                   f"lg_{PARAMETROS[clave]}", nuevo.id,
                   antes=str(anterior.id) if anterior else None,
                   despues=_compacto(nuevo), detalle=motivo)
    return nuevo


def editar_programado(db: Session, actor: m.Usuario, valor_id: int,
                      vigente_desde: date, entrada: dict,
                      motivo: str | None = None,
                      hoy: date | None = None) -> m.LgValor:
    """Corregir lo programado mientras no llega su dia. No se toca el
    renglon: se reemplaza por uno nuevo y queda dicho, como todo."""
    fila = db.get(m.LgValor, valor_id)
    if fila is None:
        raise _no("Ese valor no existe.", codigo=404)
    if fila.reemplazado_en or fila.quitado_en:
        raise _no({"mensaje": "Ese valor ya se reemplazó o se quitó.",
                   "que_hacer": "Vuelve a abrir la pantalla."})
    hoy = hoy or hoy_lg()
    if fila.vigente_desde <= hoy:
        raise _no({"mensaje": "Lo que ya rige no se edita.",
                   "que_hacer": "Si está mal, captura el bueno desde la misma fecha, con su "
                                "porqué: el de antes se queda marcado como reemplazado."})
    _revisar_fecha(vigente_desde, hoy)
    if vigente_desde <= hoy:
        raise _no({"mensaje": "Lo programado se mueve a otra fecha que todavía no llega.",
                   "que_hacer": "Si debe regir desde hoy o antes, captúralo como valor "
                                "nuevo."})
    otro = (_vivos(db, fila.clave, fila.tipo_unidad_id)
            .filter(m.LgValor.vigente_desde == vigente_desde,
                    m.LgValor.id != fila.id).first())
    if otro is not None:
        raise _no({"mensaje": "Ya hay otro valor programado para esa fecha.",
                   "que_hacer": "Corrige ese o quítalo."})
    valor, datos = _validar(db, fila.clave, entrada)
    motivo = (motivo or "").strip()[:200] or None
    nuevo = _nuevo(db, actor, fila.clave, fila.tipo_unidad_id, vigente_desde,
                   valor, datos, motivo)
    fila.reemplazado_en = _ahora()
    fila.reemplazado_por_id = nuevo.id
    accesos.anotar(db, actor, "lg valor reemplazado",
                   f"lg_{PARAMETROS[fila.clave]}", nuevo.id,
                   antes=str(fila.id), despues=_compacto(nuevo), detalle=motivo)
    return nuevo


def quitar_programado(db: Session, actor: m.Usuario, valor_id: int,
                      hoy: date | None = None) -> m.LgValor:
    fila = db.get(m.LgValor, valor_id)
    if fila is None:
        raise _no("Ese valor no existe.", codigo=404)
    if fila.reemplazado_en or fila.quitado_en:
        raise _no({"mensaje": "Ese valor ya se reemplazó o se quitó.",
                   "que_hacer": "Vuelve a abrir la pantalla."})
    hoy = hoy or hoy_lg()
    if fila.vigente_desde <= hoy:
        raise _no({"mensaje": "Lo que ya rige no se quita.",
                   "que_hacer": "Si está mal, captura el bueno desde la misma fecha, con su "
                                "porqué."})
    fila.quitado_en = _ahora()
    fila.quitado_por_id = actor.persona_id
    accesos.anotar(db, actor, "lg valor quitado",
                   f"lg_{PARAMETROS[fila.clave]}", fila.id,
                   antes=_compacto(fila))
    return fila


# ================================================================ tipos y patios

def _resumen(obj, campos: tuple) -> dict:
    salida = {}
    for campo in campos:
        valor = getattr(obj, campo)
        if isinstance(valor, Decimal):
            valor = _txt(valor)
        salida[campo] = "" if valor is None else str(valor)
    return salida


def _diferencia(antes: dict, despues: dict) -> tuple[str | None, str | None]:
    """«campo: valor; campo: valor», solo lo que cambio: la forma que lee
    la bitacora."""
    cambiaron = [k for k in despues if antes.get(k) != despues.get(k)]
    if not cambiaron:
        return None, None
    return ("; ".join(f"{k}: {antes.get(k) or 'None'}" for k in cambiaron),
            "; ".join(f"{k}: {despues.get(k) or 'None'}" for k in cambiaron))


CAMPOS_TIPO = ("nombre", "capacidad_ton", "nombre_tango", "orden")
CAMPOS_PATIO = ("nombre", "direccion", "lat", "lon", "geocerca_metros")


def _nombre_libre(db: Session, modelo, nombre: str, salvo: int | None = None):
    """El nombre, si nadie mas lo trae --sin contar mayusculas--. Son
    catalogos de unos cuantos renglones: se revisan todos."""
    nombre = " ".join((nombre or "").split())
    if not nombre:
        raise _no("Falta el nombre.")
    for x in db.query(modelo).all():
        if x.id != salvo and x.nombre.strip().lower() == nombre.lower():
            if not x.activo:
                raise _no({"mensaje": f"Ya hay uno que se llama «{x.nombre}», quitado.",
                           "que_hacer": "Vuélvelo a poner desde su renglón con "
                                        "«Reactivar»."})
            raise _no(f"Ya hay uno que se llama «{x.nombre}».")
    return nombre


def _datos_tipo(datos: dict) -> dict:
    capacidad = datos.get("capacidad_ton")
    if capacidad in ("", None):
        capacidad = None
    else:
        capacidad = _numero(capacidad, "la capacidad en toneladas",
                            mayor_que=0, maximo=100, decimales=2)
    tango = (datos.get("nombre_tango") or "").strip()[:60] or None
    orden = datos.get("orden")
    orden = 0 if orden in ("", None) else int(_numero(
        orden, "el orden", minimo=0, maximo=999, entero=True))
    return {"capacidad_ton": capacidad, "nombre_tango": tango, "orden": orden}


def alta_tipo(db: Session, actor: m.Usuario, datos: dict) -> m.LgTipoUnidad:
    nombre = _nombre_libre(db, m.LgTipoUnidad, datos.get("nombre"))[:60]
    resto = _datos_tipo(datos)
    if datos.get("orden") in ("", None):
        mayor = max((t.orden for t in db.query(m.LgTipoUnidad).all()), default=0)
        resto["orden"] = mayor + 1
    tipo = m.LgTipoUnidad(nombre=nombre, **resto)
    db.add(tipo)
    db.flush()
    accesos.anotar(db, actor, "catalogo creado", "lg_tipos", tipo.id,
                   despues=nombre)
    return tipo


def cambiar_tipo(db: Session, actor: m.Usuario, tipo_id: int,
                 datos: dict) -> m.LgTipoUnidad:
    tipo = db.get(m.LgTipoUnidad, tipo_id)
    if tipo is None:
        raise _no("Ese tipo de unidad no existe.", codigo=404)
    antes = _resumen(tipo, CAMPOS_TIPO)
    tipo.nombre = _nombre_libre(db, m.LgTipoUnidad, datos.get("nombre"),
                                salvo=tipo.id)[:60]
    for campo, valor in _datos_tipo(datos).items():
        setattr(tipo, campo, valor)
    db.flush()
    a, d = _diferencia(antes, _resumen(tipo, CAMPOS_TIPO))
    if a is not None:
        accesos.anotar(db, actor, "catalogo cambiado", "lg_tipos", tipo.id,
                       antes=a, despues=d, detalle=tipo.nombre)
    return tipo


def _datos_patio(datos: dict) -> dict:
    direccion = (datos.get("direccion") or "").strip()[:300] or None
    # El punto de Google trae mas decimales de los que caben: se redondea
    # a siete, que es un centimetro.
    siete = Decimal("0.0000001")
    lat, lon = datos.get("lat"), datos.get("lon")
    lat = None if lat in ("", None) else _numero(
        lat, "la latitud", minimo=-90, maximo=90, decimales=20).quantize(siete)
    lon = None if lon in ("", None) else _numero(
        lon, "la longitud", minimo=-180, maximo=180, decimales=20).quantize(siete)
    if (lat is None) != (lon is None):
        raise _no({"mensaje": "El punto va completo: latitud y longitud.",
                   "que_hacer": "Búscalo en Google y escoge el lugar, o escribe las dos."})
    geocerca = _numero(datos.get("geocerca_metros"),
                       "el radio de la geocerca", minimo=50, maximo=5000,
                       entero=True)
    return {"direccion": direccion, "lat": lat, "lon": lon,
            "geocerca_metros": int(geocerca)}


def alta_patio(db: Session, actor: m.Usuario, datos: dict) -> m.LgPatio:
    nombre = _nombre_libre(db, m.LgPatio, datos.get("nombre"))[:80]
    patio = m.LgPatio(nombre=nombre, **_datos_patio(datos))
    db.add(patio)
    db.flush()
    accesos.anotar(db, actor, "catalogo creado", "lg_patios", patio.id,
                   despues=nombre)
    return patio


def cambiar_patio(db: Session, actor: m.Usuario, patio_id: int,
                  datos: dict) -> m.LgPatio:
    patio = db.get(m.LgPatio, patio_id)
    if patio is None:
        raise _no("Ese patio no existe.", codigo=404)
    antes = _resumen(patio, CAMPOS_PATIO)
    patio.nombre = _nombre_libre(db, m.LgPatio, datos.get("nombre"),
                                 salvo=patio.id)[:80]
    for campo, valor in _datos_patio(datos).items():
        setattr(patio, campo, valor)
    db.flush()
    a, d = _diferencia(antes, _resumen(patio, CAMPOS_PATIO))
    if a is not None:
        accesos.anotar(db, actor, "catalogo cambiado", "lg_patios", patio.id,
                       antes=a, despues=d, detalle=patio.nombre)
    return patio


def prender(db: Session, actor: m.Usuario, modelo, objeto: str, obj_id: int,
            activo: bool):
    """Quitar o volver a poner un tipo o un patio. No se borra: lo que ya
    lo usaba nunca se fue."""
    obj = db.get(modelo, obj_id)
    if obj is None:
        raise _no("No existe.", codigo=404)
    if obj.activo == activo:
        return obj
    obj.activo = activo
    accesos.anotar(db, actor,
                   "catalogo reactivado" if activo else "catalogo desactivado",
                   objeto, obj.id, detalle=obj.nombre)
    return obj


def sembrar(db: Session) -> None:
    """Los cuatro tipos y Base Cuautitlan, si no estan. Lo que ya existe no
    se toca: lo lleva sistema y calidad."""
    for orden, (nombre, capacidad, tango) in enumerate(TIPOS_DE_ARRANQUE, 1):
        if not db.query(m.LgTipoUnidad).filter_by(nombre=nombre).first():
            db.add(m.LgTipoUnidad(
                nombre=nombre, nombre_tango=tango, orden=orden,
                capacidad_ton=Decimal(capacidad) if capacidad else None))
    nombre, geocerca = PATIO_DE_ARRANQUE
    if not db.query(m.LgPatio).filter_by(nombre=nombre).first():
        db.add(m.LgPatio(nombre=nombre, geocerca_metros=geocerca))
    db.flush()


# ================================================================ la pantalla

def estado(fila: m.LgValor, hoy: date, vigente_id: int | None) -> str:
    if fila.quitado_en:
        return "quitado"
    if fila.reemplazado_en:
        return "reemplazado"
    if fila.vigente_desde > hoy:
        return "programado"
    return "vigente" if fila.id == vigente_id else "anterior"


def _calculo(fila: m.LgValor, datos: dict, activos) -> dict | None:
    """Lo que la pantalla ensena calculado junto al renglon: el costo por
    dia del operador y de la unidad, y el ejemplo del tabulador."""
    if fila.clave == "operador":
        return {"costo_dia": str(costo_operador_con(datos))}
    if fila.clave == "unidad":
        return {k: str(v) for k, v in costo_unidad_con(datos).items()}
    if fila.clave == "tabulador":
        ejemplos = {}
        for tipo in activos:
            c = comision_con(datos, tipo.id, KM_DE_EJEMPLO)
            if c:
                ejemplos[str(tipo.id)] = str(c["comision"])
        return {"km": int(KM_DE_EJEMPLO), "ejemplos": ejemplos}
    return None


def _iso(momento) -> str | None:
    return momento.isoformat() if momento else None


def renglon(fila: m.LgValor, hoy: date, vigente_id, activos) -> dict:
    datos = datos_de(fila) if fila.datos else None
    return {
        "id": fila.id, "clave": fila.clave,
        "tipo_unidad_id": fila.tipo_unidad_id,
        "valor": _txt(Decimal(fila.valor)) if fila.valor is not None else None,
        "datos": datos,
        "vigente_desde": fila.vigente_desde.isoformat(),
        "motivo": fila.motivo,
        "capturado_por": fila.capturado_por.nombre if fila.capturado_por else None,
        "capturado_en": _iso(fila.capturado_en),
        "estado": estado(fila, hoy, vigente_id),
        "reemplazado_en": _iso(fila.reemplazado_en),
        "reemplazado_por_id": fila.reemplazado_por_id,
        "quitado_en": _iso(fila.quitado_en),
        "quitado_por": fila.quitado_por.nombre if fila.quitado_por else None,
        "calculo": _calculo(fila, datos, activos) if datos else None,
    }


def _tipo_dict(t: m.LgTipoUnidad) -> dict:
    return {"id": t.id, "nombre": t.nombre,
            "capacidad_ton": _txt(Decimal(t.capacidad_ton))
            if t.capacidad_ton is not None else None,
            "nombre_tango": t.nombre_tango, "orden": t.orden,
            "activo": t.activo}


def _patio_dict(p: m.LgPatio) -> dict:
    return {"id": p.id, "nombre": p.nombre, "direccion": p.direccion,
            "lat": float(p.lat) if p.lat is not None else None,
            "lon": float(p.lon) if p.lon is not None else None,
            "geocerca_metros": p.geocerca_metros, "activo": p.activo}


def faltas(db: Session, hoy: date, vigentes: dict, tipos, patios) -> dict:
    """Lo que le falta a cada catalogo, para la lista de la izquierda: las
    claves sin valor que rija hoy, o los tipos y patios que se quedan
    cortos."""
    activos = [t for t in tipos if t["activo"]]
    salida = {c: [] for c in CATALOGOS}
    tab = vigentes.get("tabulador")
    if tab is None:
        salida["tabulador"].append("tabulador")
    else:
        del_tab = (tab["datos"] or {}).get("tipos") or {}
        salida["tabulador"] += [t["nombre"] for t in activos
                                if str(t["id"]) not in del_tab]
    for catalogo in ("diesel", "alimentos", "operador", "bono"):
        salida[catalogo] = [c for c in CLAVES_DE[catalogo]
                            if vigentes.get(c) is None]
    salida["costos"] = [t["nombre"] for t in activos
                        if (vigentes.get("unidad") or {}).get(str(t["id"])) is None]
    if not activos:
        salida["tipos"].append("tipos")
    vivos = [p for p in patios if p["activo"]]
    if not vivos:
        salida["patios"].append("patios")
    salida["patios"] += [p["nombre"] for p in vivos if p["lat"] is None]
    return salida


def todo(db: Session, hoy: date | None = None) -> dict:
    """La pantalla entera de una vez: son catalogos chicos, y con todo a
    la mano la lista de la izquierda dice que le falta a cada uno sin
    abrirlo."""
    hoy = hoy or hoy_lg()
    tipos_obj = (db.query(m.LgTipoUnidad)
                 .order_by(m.LgTipoUnidad.orden, m.LgTipoUnidad.id).all())
    activos = [t for t in tipos_obj if t.activo]
    tipos = [_tipo_dict(t) for t in tipos_obj]
    patios = [_patio_dict(p) for p in
              db.query(m.LgPatio).order_by(m.LgPatio.nombre).all()]

    valores = {c: [] for c in PARAMETROS}
    vigentes: dict = {c: None for c in PARAMETROS if c not in POR_TIPO}
    vigentes["unidad"] = {}
    filas = (db.query(m.LgValor)
             .order_by(m.LgValor.vigente_desde.desc(),
                       m.LgValor.capturado_en.desc(), m.LgValor.id.desc())
             .all())
    # El que rige, por clave y tipo: el vivo mas reciente que no pase de hoy.
    rige = {}
    for f in filas:
        if f.reemplazado_en or f.quitado_en or f.vigente_desde > hoy:
            continue
        rige.setdefault((f.clave, f.tipo_unidad_id), f.id)
    for f in filas:
        if f.clave not in valores:
            continue
        r = renglon(f, hoy, rige.get((f.clave, f.tipo_unidad_id)), activos)
        valores[f.clave].append(r)
        if r["estado"] == "vigente":
            if f.clave in POR_TIPO:
                vigentes[f.clave][str(f.tipo_unidad_id)] = r
            else:
                vigentes[f.clave] = r
    mx = db.query(m.Pais).filter_by(codigo="MX").first()
    return {
        "hoy": hoy.isoformat(),
        "pais_id": mx.id if mx else None,
        "tipos": tipos, "patios": patios,
        "valores": valores, "vigentes": vigentes,
        "faltas": faltas(db, hoy, vigentes, tipos, patios),
        "lo_da": LO_DA,
    }


# ================================================================ la bitacora

MESES = {"es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago",
                "sep", "oct", "nov", "dic"),
         "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
                "Sep", "Oct", "Nov", "Dec"),
         "pt": ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago",
                "set", "out", "nov", "dez")}

NOMBRES = {
    "es": {"tabulador": "Tabulador de comisiones",
           "diesel": "Precio del diésel", "holgura": "Holgura del anticipo",
           "tolerancia": "Tolerancia de rendimiento",
           "alimentos": "Alimentos por día", "margen": "Margen mínimo",
           "operador": "Costo del operador",
           "unidad": "Rendimiento y costo",
           "bono": "Bono de movilidad", "garantia": "Garantía semanal"},
    "en": {"tabulador": "Commission table",
           "diesel": "Diesel price", "holgura": "Advance buffer",
           "tolerancia": "Fuel efficiency tolerance",
           "alimentos": "Meals per day", "margen": "Minimum margin",
           "operador": "Driver cost",
           "unidad": "Fuel efficiency and cost",
           "bono": "Mobility bonus", "garantia": "Weekly guarantee"},
    "pt": {"tabulador": "Tabela de comissões",
           "diesel": "Preço do diesel", "holgura": "Folga do adiantamento",
           "tolerancia": "Tolerância de rendimento",
           "alimentos": "Alimentação por dia", "margen": "Margem mínima",
           "operador": "Custo do motorista",
           "unidad": "Rendimento e custo",
           "bono": "Bônus de mobilidade", "garantia": "Garantia semanal"},
}

DONDE = {
    "es": {"tabulador": "Tabulador de comisiones",
           "diesel": "Diésel y anticipo",
           "alimentos": "Alimentos y margen mínimo",
           "operador": "Costo del operador",
           "costos": "Rendimiento y costo por tipo",
           "bono": "Bono de movilidad y garantía",
           "tipos": "Tipos de unidad", "patios": "Patios",
           "prefijo": "Logística"},
    "en": {"tabulador": "Commission table",
           "diesel": "Diesel and advance",
           "alimentos": "Meals and minimum margin",
           "operador": "Driver cost",
           "costos": "Fuel efficiency and cost by type",
           "bono": "Mobility bonus and guarantee",
           "tipos": "Vehicle types", "patios": "Yards",
           "prefijo": "Logistics"},
    "pt": {"tabulador": "Tabela de comissões",
           "diesel": "Diesel e adiantamento",
           "alimentos": "Alimentação e margem mínima",
           "operador": "Custo do motorista",
           "costos": "Rendimento e custo por tipo",
           "bono": "Bônus de mobilidade e garantia",
           "tipos": "Tipos de veículo", "patios": "Pátios",
           "prefijo": "Logística"},
}

FRASES = {
    "es": {
        "puesto": "{que}: {valor}, desde el {fecha}",
        "programado": "Programó {que}: {valor}, desde el {fecha}",
        "reemplazado": "Reemplazó {que}: {antes} → {valor}, desde el {fecha}",
        "quitado": "Quitó {que} {valor}, programado para el {fecha}",
        "motivo": ": «{motivo}»",
        "creado_tipos": "Agregó el tipo «{nombre}»",
        "creado_patios": "Agregó el patio «{nombre}»",
        "cambiado": "«{nombre}»: {cambios}",
        "desactivado": "Quitó «{nombre}»",
        "reactivado": "Volvió a poner «{nombre}»",
        "por_litro": "{v} por litro", "por_dia": "{v} por día",
        "operador": "{mes} al mes ÷ {dias} días = {dia} por día",
        "unidad": "{rend} km/l · {dia} por día",
        "primeros": "primeros {km} km",
        "tramo": "{pct}% desde {n} años",
        "dias_bono": "con {d} días de jornada",
        "garantia": "{tipo} {monto} a la semana; exige los días completos: "
                    "{exige}; bono sobre la garantía: {sobre}",
        "si": "sí", "no": "no", "ninguno": "ninguno",
        "campos": {"nombre": "nombre", "capacidad_ton": "capacidad (t)",
                   "nombre_tango": "en Tango", "orden": "orden",
                   "direccion": "dirección", "lat": "latitud",
                   "lon": "longitud", "geocerca_metros": "geocerca (m)"},
    },
    "en": {
        "puesto": "{que}: {valor}, from {fecha}",
        "programado": "Scheduled {que}: {valor}, from {fecha}",
        "reemplazado": "Replaced {que}: {antes} → {valor}, from {fecha}",
        "quitado": "Removed {que} {valor}, scheduled for {fecha}",
        "motivo": ": “{motivo}”",
        "creado_tipos": "Added the type “{nombre}”",
        "creado_patios": "Added the yard “{nombre}”",
        "cambiado": "“{nombre}”: {cambios}",
        "desactivado": "Removed “{nombre}”",
        "reactivado": "Put “{nombre}” back",
        "por_litro": "{v} per litre", "por_dia": "{v} per day",
        "operador": "{mes} a month ÷ {dias} days = {dia} per day",
        "unidad": "{rend} km/l · {dia} per day",
        "primeros": "first {km} km",
        "tramo": "{pct}% from {n} years",
        "dias_bono": "with {d} working days",
        "garantia": "{tipo} {monto} a week; requires the full days: {exige}; "
                    "bonus on the guarantee: {sobre}",
        "si": "yes", "no": "no", "ninguno": "none",
        "campos": {"nombre": "name", "capacidad_ton": "capacity (t)",
                   "nombre_tango": "in Tango", "orden": "order",
                   "direccion": "address", "lat": "latitude",
                   "lon": "longitude", "geocerca_metros": "geofence (m)"},
    },
    "pt": {
        "puesto": "{que}: {valor}, desde {fecha}",
        "programado": "Programou {que}: {valor}, a partir de {fecha}",
        "reemplazado": "Substituiu {que}: {antes} → {valor}, desde {fecha}",
        "quitado": "Retirou {que} {valor}, programado para {fecha}",
        "motivo": ": “{motivo}”",
        "creado_tipos": "Adicionou o tipo “{nombre}”",
        "creado_patios": "Adicionou o pátio “{nombre}”",
        "cambiado": "“{nombre}”: {cambios}",
        "desactivado": "Retirou “{nombre}”",
        "reactivado": "Voltou a colocar “{nombre}”",
        "por_litro": "{v} por litro", "por_dia": "{v} por dia",
        "operador": "{mes} por mês ÷ {dias} dias = {dia} por dia",
        "unidad": "{rend} km/l · {dia} por dia",
        "primeros": "primeiros {km} km",
        "tramo": "{pct}% a partir de {n} anos",
        "dias_bono": "com {d} dias de jornada",
        "garantia": "{tipo} {monto} por semana; exige os dias completos: "
                    "{exige}; bônus sobre a garantia: {sobre}",
        "si": "sim", "no": "não", "ninguno": "nenhum",
        "campos": {"nombre": "nome", "capacidad_ton": "capacidade (t)",
                   "nombre_tango": "no Tango", "orden": "ordem",
                   "direccion": "endereço", "lat": "latitude",
                   "lon": "longitude", "geocerca_metros": "geocerca (m)"},
    },
}


def _lengua(idioma: str) -> str:
    return idioma if idioma in FRASES else "es"


def fecha_texto(fecha: date, idioma: str) -> str:
    """«5 oct 2026»: sin la duda entre dia/mes y mes/dia."""
    return f"{fecha.day} {MESES[_lengua(idioma)][fecha.month - 1]} {fecha.year}"


def pesos(valor, centavos: bool | None = None) -> str:
    """Como se escribe un monto en pesos, en cualquier idioma: la moneda
    manda, no quien mira (util.js hace lo mismo)."""
    d = _dec(valor)
    if centavos is None:
        centavos = d != d.to_integral_value()
    if centavos:
        return f"${_centavos(d):,.2f}"
    return f"${int(d):,}"


def _por_km(valor) -> str:
    d = _dec(valor)
    return f"${d:,.2f}" if d == _centavos(d) else f"${_txt(d)}"


def resumen_de(db: Session, fila: m.LgValor, idioma: str) -> str:
    """Lo capturado, dicho para la bitacora."""
    f = FRASES[_lengua(idioma)]
    if fila.clave == "diesel":
        return f["por_litro"].replace("{v}", pesos(fila.valor, True))
    if fila.clave in PORCENTAJES:
        return f"{_txt(Decimal(fila.valor))}%"
    if fila.clave == "alimentos":
        return f["por_dia"].replace("{v}", pesos(fila.valor))
    datos = datos_de(fila)
    if fila.clave == "operador":
        return (f["operador"].replace("{mes}", pesos(datos["costo_mensual"]))
                .replace("{dias}", str(datos["dias_laborables"]))
                .replace("{dia}", pesos(costo_operador_con(datos), True)))
    if fila.clave == "unidad":
        return (f["unidad"].replace("{rend}", datos["rendimiento"])
                .replace("{dia}", pesos(costo_unidad_con(datos)["costo_dia"], True)))
    if fila.clave == "tabulador":
        partes = []
        for tipo_id, montos in (datos.get("tipos") or {}).items():
            nombre = _nombre_tipo(db, int(tipo_id)) or f"#{tipo_id}"
            partes.append(f"{nombre} {pesos(montos['base'])} + "
                          f"{_por_km(montos['por_km'])}")
        return (", ".join(partes) + " ("
                + f["primeros"].replace("{km}", str(datos.get("km_base"))) + ")")
    if fila.clave == "bono":
        tramos = ", ".join(
            f["tramo"].replace("{pct}", t["pct"]).replace("{n}", str(t["desde_anios"]))
            if int(t["desde_anios"]) else f"{t['pct']}%"
            for t in datos.get("tramos", []))
        return f"{tramos}; " + f["dias_bono"].replace(
            "{d}", str(datos.get("dias_requeridos")))
    if fila.clave == "garantia":
        return (f["garantia"]
                .replace("{tipo}", _nombre_tipo(db, datos.get("tipo_unidad_id")) or "—")
                .replace("{monto}", pesos(datos.get("monto_semanal", "0")))
                .replace("{exige}", f["si"] if datos.get("exige_dias_completos") else f["no"])
                .replace("{sobre}", f["si"] if datos.get("bono_sobre_garantia") else f["no"]))
    return _compacto(fila)


def _que(db: Session, fila: m.LgValor, idioma: str) -> str:
    nombre = NOMBRES[_lengua(idioma)][fila.clave]
    tipo = _nombre_tipo(db, fila.tipo_unidad_id)
    return f"{nombre} · {tipo}" if tipo else nombre


def donde(objeto: str, idioma: str) -> str:
    """En que catalogo paso, para la columna «Donde» de la bitacora."""
    t = DONDE[_lengua(idioma)]
    catalogo = objeto[3:] if objeto.startswith("lg_") else objeto
    if catalogo not in t:
        return objeto
    return f"{t['prefijo']} · {t[catalogo]}"


def _cambios(antes: str | None, despues: str | None, idioma: str) -> str:
    f = FRASES[_lengua(idioma)]

    def partes(texto):
        salida = {}
        for pedazo in (texto or "").split("; "):
            campo, dos, valor = pedazo.partition(": ")
            if dos:
                salida[campo] = valor
        return salida

    a, d = partes(antes), partes(despues)
    dichos = []
    for campo in dict.fromkeys([*d, *a]):
        etiqueta = f["campos"].get(campo, campo.replace("_", " "))
        va = a.get(campo) if a.get(campo) not in (None, "", "None") else f["ninguno"]
        vd = d.get(campo) if d.get(campo) not in (None, "", "None") else f["ninguno"]
        dichos.append(f"{etiqueta} {va} → {vd}")
    return "; ".join(dichos)


def que_cambio(r: m.RegistroAdmin, idioma: str, db: Session) -> str:
    """Un renglon de la bitacora de Logistica, contado en el idioma de
    quien lo lee. Los valores se leen de su renglon --que nunca se
    borra--, asi que la frase dice lo que se capturo, no lo que se
    alcanzo a guardar en doscientas letras."""
    f = FRASES[_lengua(idioma)]
    if r.accion.startswith("lg valor"):
        fila = db.get(m.LgValor, r.objeto_id) if r.objeto_id else None
        if fila is None:
            return f"{r.accion}: {r.despues or ''}".strip()
        valor = resumen_de(db, fila, idioma)
        que = _que(db, fila, idioma)
        cuando = fecha_texto(fila.vigente_desde, idioma)
        if r.accion == "lg valor quitado":
            texto = (f["quitado"].replace("{que}", que)
                     .replace("{valor}", valor).replace("{fecha}", cuando))
        elif r.accion == "lg valor reemplazado":
            viejo = None
            try:
                viejo = db.get(m.LgValor, int(r.antes)) if r.antes else None
            except ValueError:
                viejo = None
            texto = (f["reemplazado"].replace("{que}", que)
                     .replace("{antes}", resumen_de(db, viejo, idioma) if viejo else "—")
                     .replace("{valor}", valor).replace("{fecha}", cuando))
        else:
            capturado = (r.creado_en.astimezone(reloj.zona(None)).date()
                         if r.creado_en else fila.vigente_desde)
            plantilla = f["programado" if fila.vigente_desde > capturado else "puesto"]
            texto = (plantilla.replace("{que}", que).replace("{valor}", valor)
                     .replace("{fecha}", cuando))
        if r.detalle:
            texto += f["motivo"].replace("{motivo}", r.detalle)
        return texto

    nombre = r.detalle or r.despues or r.antes or ""
    catalogo = r.objeto[3:]
    if r.accion == "catalogo creado":
        return f.get(f"creado_{catalogo}", f["creado_tipos"]).replace("{nombre}", r.despues or "")
    if r.accion == "catalogo cambiado":
        return (f["cambiado"].replace("{nombre}", nombre)
                .replace("{cambios}", _cambios(r.antes, r.despues, idioma)))
    if r.accion == "catalogo desactivado":
        return f["desactivado"].replace("{nombre}", nombre)
    if r.accion == "catalogo reactivado":
        return f["reactivado"].replace("{nombre}", nombre)
    extra = " → ".join(x for x in (r.antes, r.despues) if x)
    return f"{r.accion}: {extra}" if extra else r.accion


POR_PAGINA = 50


def bitacora(db: Session, catalogo: str | None = None, pagina: int = 1,
             idioma: str = "es") -> dict:
    """Lo que le ha pasado a los catalogos de Logistica, lo mas nuevo
    arriba. Con `catalogo`, solo lo de uno: lo de abajo de cada tarjeta."""
    objetos = (f"lg_{catalogo}",) if catalogo in CATALOGOS else OBJETOS
    pagina = max(1, pagina)
    consulta = (db.query(m.RegistroAdmin)
                .filter(m.RegistroAdmin.objeto.in_(objetos))
                .order_by(m.RegistroAdmin.creado_en.desc(),
                          m.RegistroAdmin.id.desc()))
    total = consulta.count()
    filas = consulta.offset((pagina - 1) * POR_PAGINA).limit(POR_PAGINA).all()
    return {
        "filas": [{"id": r.id, "cuando": _iso(r.creado_en),
                   "quien": r.persona.nombre if r.persona else None,
                   "catalogo": r.objeto[3:], "donde": donde(r.objeto, idioma),
                   "que": que_cambio(r, idioma, db)} for r in filas],
        "total": total, "pagina": pagina, "por_pagina": POR_PAGINA,
    }

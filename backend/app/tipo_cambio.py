# -*- coding: utf-8 -*-
"""Cuanto vale un dolar (seccion 82).

Como `reloj.py` es el unico que dice que hora es, este es el unico que
convierte de una moneda a otra.

Decision de Salvador, 26 de septiembre: el tipo de cambio lo pone
finanzas a mano, en Tarifarios, y **el que se pone se queda y aplica para
todo hasta que alguien lo cambie**. Primero se penso leer el FIX del
Banco de Mexico; sacarlo daba mas problemas que ponerlo.

Tres reglas:

  * **Cada monto se guarda en su moneda, con su moneda al lado.** Nunca
    se guarda un numero ya convertido como si fuera nativo: los gastos
    siguen en pesos, la cotizacion en dolares, y lo que se convierte se
    convierte al leer, con un tipo de cambio que dice de cuando es.
  * **Lo que ya se fijo no se mueve.** La cotizacion se queda con el tipo
    de cambio que estaba puesto cuando se autorizo --con el se calculan
    la utilidad y la comision--; los gastos netos, con el del visto
    bueno, que es cuando sale la factura; el mes del implantado, con el
    del dia en que se abrio. Cambiarlo aplica a lo que venga.
  * **Sin tipo de cambio no se inventa uno.** Mientras nadie lo ponga, lo
    que no se puede convertir se dice, y la cotizacion no se autoriza.

Hoy solo se convierte de dolares a pesos mexicanos: es lo que hace falta
(Amazon). Un servicio en Brasil cotizado en dolares no tiene de donde
tomarlo, y se dice.
"""
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import reloj

CENTAVO = Decimal("0.01")
DIEZMILESIMA = Decimal("0.0001")
UNO = Decimal("1")

# Lo que se sabe convertir: dolares a pesos mexicanos.
PARES = {(m.Moneda.USD, m.Moneda.MXN)}
# El dia de un tipo de cambio se cuenta en Mexico: es donde se usa.
ZONA = "America/Mexico_City"
# Un tipo de cambio fuera de esto es un dedo que se resbalo, no un dolar.
MINIMO, MAXIMO = Decimal("0.0001"), Decimal("9999")


def _d(valor) -> Decimal:
    return Decimal(str(valor))


def _moneda(valor) -> m.Moneda:
    return valor if isinstance(valor, m.Moneda) else m.Moneda(valor)


def local_del_pais(db: Session, pais_id: int | None) -> m.Moneda | None:
    pais = db.get(m.Pais, pais_id) if pais_id else None
    return pais.moneda_local if pais else None


def se_puede(moneda, local) -> bool:
    """Si esas dos monedas se saben convertir."""
    moneda, local = _moneda(moneda), _moneda(local)
    return moneda == local or (moneda, local) in PARES


def _fecha(momento: datetime | None) -> date | None:
    if momento is None:
        return None
    if momento.tzinfo is None:
        return momento.date()
    return momento.astimezone(reloj.zona(ZONA)).date()


def _de_la_fila(fila: m.TipoCambio) -> dict:
    quien = fila.puesto_por.nombre if fila.puesto_por else None
    return {"tasa": _d(fila.tasa), "fecha": _fecha(fila.puesto_en),
            "puesto_en": fila.puesto_en, "por": quien}


def vigente(db: Session, moneda, local) -> dict | None:
    """El que esta puesto: el ultimo que se capturo. {tasa, fecha,
    puesto_en, por} o None si nunca se ha puesto. La tasa es cuantas
    unidades de `local` vale una de `moneda`: pesos por dolar."""
    moneda, local = _moneda(moneda), _moneda(local)
    if moneda == local:
        return {"tasa": UNO, "fecha": None, "puesto_en": None, "por": None}
    fila = (db.query(m.TipoCambio)
            .filter(m.TipoCambio.moneda == moneda,
                    m.TipoCambio.moneda_local == local)
            .order_by(m.TipoCambio.puesto_en.desc(), m.TipoCambio.id.desc())
            .first())
    return _de_la_fila(fila) if fila else None


def a_local(monto, tasa) -> Decimal:
    """De la moneda de la cotizacion a la del pais: dolares por la tasa."""
    return (_d(monto) * _d(tasa)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def de_local(monto, tasa) -> Decimal:
    """De la moneda del pais a la de la cotizacion: pesos entre la tasa."""
    return (_d(monto) / _d(tasa)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def texto(tasa) -> str | None:
    """La tasa con cuatro decimales. Va como texto para que viaje igual
    por la API, por Celery y por la factura."""
    if tasa is None:
        return None
    return str(_d(tasa).quantize(DIEZMILESIMA, rounding=ROUND_HALF_UP))


def corto(tasa) -> str | None:
    """Como se lee: "17.50", no "17.5000"; los decimales que traiga de mas
    se quedan ("17.4523"). Para el desglose y la factura, que lee gente."""
    largo = texto(tasa)
    if largo is None:
        return None
    enteros, decimales = largo.split(".")
    return f"{enteros}.{decimales.rstrip('0').ljust(2, '0')}"


def en_json(tc: dict | None) -> dict | None:
    if tc is None:
        return None
    fecha, puesto_en = tc.get("fecha"), tc.get("puesto_en")
    return {"tasa": texto(tc["tasa"]),
            "fecha": fecha.isoformat() if fecha else None,
            "puesto_en": puesto_en.isoformat() if puesto_en else None,
            "por": tc.get("por")}


def fijo(tasa, fecha: date | None) -> dict | None:
    """Un tipo de cambio que ya quedo fijo en algo --una cotizacion, un
    cierre, un mes--, con la forma de los de arriba."""
    if not tasa:
        return None
    return {"tasa": _d(tasa), "fecha": fecha, "puesto_en": None, "por": None,
            "fijo": True}


# ---------------------------------------------------------------- ponerlo

def poner(db: Session, tasa, usuario: m.Usuario, moneda=m.Moneda.USD,
          local=m.Moneda.MXN) -> dict:
    """Finanzas pone el tipo de cambio. Desde ese momento es el que vale
    para todo lo que se fije; lo ya fijado se queda con el suyo. Los
    anteriores no se borran: son la historia de quien lo cambio y cuando.
    Si es el mismo que ya estaba, no se escribe nada."""
    moneda, local = _moneda(moneda), _moneda(local)
    if (moneda, local) not in PARES:
        raise HTTPException(400, {
            "mensaje": f"Centauro no convierte de {moneda.value} a {local.value}",
            "que_hacer": "Hoy solo se convierte de dolares a pesos mexicanos."})
    try:
        tasa = _d(tasa).quantize(DIEZMILESIMA, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        tasa = None
    if tasa is None or not MINIMO <= tasa <= MAXIMO:
        raise HTTPException(400, {
            "mensaje": "El tipo de cambio tiene que ser un numero mayor que cero",
            "que_hacer": f"Cuantos {local.value} vale un {moneda.value}: "
                         "por ejemplo, 17.50."})
    actual = vigente(db, moneda, local)
    if actual and actual["tasa"] == tasa:
        return actual
    db.add(m.TipoCambio(moneda=moneda, moneda_local=local, tasa=tasa,
                        puesto_por_id=usuario.persona_id if usuario else None))
    db.flush()
    return vigente(db, moneda, local)


def estado(db: Session, moneda=m.Moneda.USD, local=m.Moneda.MXN,
           cuantos: int = 5) -> dict:
    """Lo que sabe la pantalla: el que esta puesto y los anteriores."""
    moneda, local = _moneda(moneda), _moneda(local)
    filas = (db.query(m.TipoCambio)
             .filter(m.TipoCambio.moneda == moneda,
                     m.TipoCambio.moneda_local == local)
             .order_by(m.TipoCambio.puesto_en.desc(), m.TipoCambio.id.desc())
             .limit(cuantos).all())
    return {"moneda": moneda.value, "moneda_local": local.value,
            "vigente": en_json(_de_la_fila(filas[0])) if filas else None,
            "anteriores": [en_json(_de_la_fila(f)) for f in filas[1:]]}

# -*- coding: utf-8 -*-
"""El freelance en Connect (seccion 111).

Salvador (30 sep): "tambien tenemos al personal freelance. Me gustaria
que crees un lugar donde los podamos dar de alta con su foto y sus datos
para que pueda ser tomada para el TS. Tambien un lugar donde se pueda
cargar toda la informacion que solicita RRHH". Cada freelance tiene sus
propios costos --dia completo, medio dia y transfer-- y solo aplican en
servicios eventuales, no en implantados.

Lo que habia: una marca en la persona (`es_freelance`) y una tarifa por
modalidad en Catalogos. Sin donde darlo de alta con foto y telefono --al
de planta le llegan de Odoo, al freelance de ningun lado--, salia en la
hoja sin foto, y su documentacion no tenia donde vivir.

Las doce decisiones de Salvador, una por una:

1. Vive en Connect: no es empleado y no llega de Odoo.
2. Lo dan de alta el consultor, direccion de operaciones y Recursos
   Humanos; el expediente lo valida solo Recursos Humanos.
3. Sus costos los fijan direccion de operaciones y la gerencia de
   administracion (`catalogos.dinero`). Sin costos no se asigna.
4. Con el expediente incompleto o vencido no se asigna, salvo urgencia
   autorizada por direccion de operaciones para ese servicio, con motivo.
5. El de emergencia que repite: al asignarle su segundo servicio tiene
   quince dias desde el ultimo para completar lo de programado; pasado
   el plazo no se le asigna hasta completarlo.
6. Los documentos los abren Recursos Humanos, direccion general y
   direccion de operaciones. Finanzas ve los datos bancarios. Quien
   asigna ve solo si esta listo y la ficha de la hoja.
7. Se guardan mientras colabore y seis anos despues de su ultimo servicio.
8. El aviso de privacidad firmado es requisito en los dos tipos.
9. Sus datos bancarios, en su expediente; el numero completo solo lo ven
   finanzas y direccion general.
10. Solo eventuales: no se ofrece en implantados.
11. Su propio costo por hora extra del dia completo.
12. La lista de requisitos, en Catalogos por pais, la lleva sistema y
    calidad.
"""
import base64
import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import accesos, archivo as archivo_motor, auth, reloj, telefonos
from app import models as m
from app.config import settings

registro = logging.getLogger("centauro.freelance")

PROGRAMADO, EMERGENCIA = "programado", "emergencia"
TIPOS = (PROGRAMADO, EMERGENCIA)

POR_REVISAR, VALIDADO, RECHAZADO = "por_revisar", "validado", "rechazado"

CAPTURAS = ("archivo", "numero", "archivo_numero", "banco", "riesgo",
            "entrevista", "contactos", "prueba")
VIGENCIAS = ("ninguna", "meses", "documento", "servicio")
# Lo que no se puede cargar sin archivo.
CON_ARCHIVO = {"archivo", "archivo_numero", "banco", "riesgo"}

# Treinta dias antes de vencer, y el dia que vence: los dos avisos a
# Recursos Humanos, como los de los certificados.
DIAS_DE_AVISO = 30
# El de emergencia que repite (decision 5).
DIAS_DEL_PLAZO = 15

LIMITE_ARCHIVO = 10 * 1024 * 1024
MAX_ARCHIVOS = 6
TIPOS_DE_ARCHIVO = {"application/pdf": ".pdf", "image/jpeg": ".jpg",
                    "image/png": ".png", "image/webp": ".webp",
                    "image/heic": ".heic", "image/heif": ".heif"}

# Los costos del freelance, en el orden de la ficha.
MODALIDADES = ("full_day", "medio_dia", "transfer")

# Lo que ya no se arma: ahi no se pide ni se usa una urgencia.
YA_NO_SE_ARMA = (m.EstatusServicio.CANCELADO, m.EstatusServicio.CERRADO,
                 m.EstatusServicio.EN_FACTURACION,
                 m.EstatusServicio.SIN_VISTO_BUENO,
                 m.EstatusServicio.TERMINADO)

UNA_VEZ_NO_SE_ASIGNA = ("Si es una urgencia, dirección de operaciones lo "
                        "autoriza para este servicio, con el motivo.")

NO_EN_IMPLANTADO = {
    "mensaje": "El freelance no se asigna en implantados: sus costos son "
               "solo de servicios eventuales.",
    "que_hacer": "El implantado se cubre con personal de planta.",
    "codigo": "freelance_implantado",
}


# Lo que Recursos Humanos pidio para Mexico (la tabla que mando Salvador
# el 30 sep), mas el aviso de privacidad firmado (decision 8). Programado:
# quince mas el aviso. Emergencia: nueve mas el aviso; la prueba rapida y
# la alcoholemia las aplica la caseta en cada servicio y no se piden
# antes de asignar. La migracion 111 siembra esta misma lista en
# produccion; una prueba cuida que digan lo mismo.
REQUISITOS_MEXICO = [
    {"clave": "licencia", "nombre": "Licencia de conducir vigente",
     "detalle": None, "programado": True, "emergencia": True,
     "captura": "archivo", "vigencia": "documento", "vigencia_meses": None,
     "antiguedad_meses": None, "orden": 10},
    {"clave": "ine", "nombre": "INE vigente", "detalle": None,
     "programado": True, "emergencia": True, "captura": "archivo",
     "vigencia": "documento", "vigencia_meses": None,
     "antiguedad_meses": None, "orden": 20},
    {"clave": "domicilio", "nombre": "Comprobante de domicilio",
     "detalle": "No mayor a 3 meses; vale un año", "programado": True,
     "emergencia": True, "captura": "archivo", "vigencia": "meses",
     "vigencia_meses": 12, "antiguedad_meses": 3, "orden": 30},
    {"clave": "antecedentes", "nombre": "Antecedentes penales",
     "detalle": "Vale un año", "programado": True, "emergencia": False,
     "captura": "archivo", "vigencia": "meses", "vigencia_meses": 12,
     "antiguedad_meses": None, "orden": 40},
    {"clave": "curp", "nombre": "CURP", "detalle": None, "programado": True,
     "emergencia": False, "captura": "numero", "vigencia": "ninguna",
     "vigencia_meses": None, "antiguedad_meses": None, "orden": 50},
    {"clave": "rfc", "nombre": "CIF (RFC)",
     "detalle": "Constancia de situación fiscal, con su RFC",
     "programado": True, "emergencia": True, "captura": "archivo_numero",
     "vigencia": "ninguna", "vigencia_meses": None,
     "antiguedad_meses": None, "orden": 60},
    {"clave": "nss", "nombre": "NSS", "detalle": "Número de seguridad social",
     "programado": True, "emergencia": True, "captura": "numero",
     "vigencia": "ninguna", "vigencia_meses": None,
     "antiguedad_meses": None, "orden": 70},
    {"clave": "banco", "nombre": "Datos bancarios",
     "detalle": "Banco, CLABE, titular y la carátula del estado de cuenta",
     "programado": True, "emergencia": True, "captura": "banco",
     "vigencia": "ninguna", "vigencia_meses": None,
     "antiguedad_meses": None, "orden": 80},
    {"clave": "toxicologica", "nombre": "Prueba toxicológica en laboratorio",
     "detalle": "Cada 6 meses", "programado": True, "emergencia": False,
     "captura": "archivo", "vigencia": "meses", "vigencia_meses": 6,
     "antiguedad_meses": None, "orden": 90},
    {"clave": "caseta", "nombre": "Prueba toxicológica rápida y alcoholemia",
     "detalle": "La aplica la caseta en cada servicio",
     "programado": False, "emergencia": True, "captura": "prueba",
     "vigencia": "servicio", "vigencia_meses": None,
     "antiguedad_meses": None, "orden": 95},
    {"clave": "veritas", "nombre": "Evaluación Veritas",
     "detalle": "Apegada a integridad: riesgo 1, 2 o 3",
     "programado": True, "emergencia": False, "captura": "riesgo",
     "vigencia": "ninguna", "vigencia_meses": None,
     "antiguedad_meses": None, "orden": 100},
    {"clave": "rotacion", "nombre": "Análisis de rotación",
     "detalle": "Semanas cotizadas ante el IMSS", "programado": True,
     "emergencia": False, "captura": "archivo", "vigencia": "ninguna",
     "vigencia_meses": None, "antiguedad_meses": None, "orden": 110},
    {"clave": "responsiva", "nombre": "Responsiva por daño a unidad con dolo",
     "detalle": "Firmada", "programado": True, "emergencia": True,
     "captura": "archivo", "vigencia": "ninguna", "vigencia_meses": None,
     "antiguedad_meses": None, "orden": 120},
    {"clave": "entrevista", "nombre": "Entrevista técnica", "detalle": None,
     "programado": True, "emergencia": False, "captura": "entrevista",
     "vigencia": "ninguna", "vigencia_meses": None,
     "antiguedad_meses": None, "orden": 130},
    {"clave": "referencias", "nombre": "Referencia laboral",
     "detalle": "Cartas de recomendación", "programado": True,
     "emergencia": False, "captura": "archivo", "vigencia": "ninguna",
     "vigencia_meses": None, "antiguedad_meses": None, "orden": 140},
    {"clave": "contactos", "nombre": "Contactos de emergencia",
     "detalle": "Dos: nombre, parentesco y teléfono", "programado": True,
     "emergencia": True, "captura": "contactos", "vigencia": "ninguna",
     "vigencia_meses": None, "antiguedad_meses": None, "orden": 150},
    {"clave": "privacidad", "nombre": "Aviso de privacidad firmado",
     "detalle": "Hay datos personales sensibles en el expediente",
     "programado": True, "emergencia": True, "captura": "archivo",
     "vigencia": "ninguna", "vigencia_meses": None,
     "antiguedad_meses": None, "orden": 160},
]


# ================================================================= apoyo

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _hoy(db: Session, persona: m.Persona, ahora: datetime | None = None) -> date:
    """Hoy en el pais donde opera: un documento vence a la medianoche de
    su pais, no de la del servidor."""
    pais_id = persona.plaza.pais_id if persona.plaza else None
    return reloj.Relojes(db, ahora).hoy(pais_id)


def sumar_meses(dia: date, meses: int) -> date:
    return archivo_motor.sumar_meses(dia, meses)


def recorte(valor: str | None) -> str | None:
    """Los ultimos cuatro: lo que se ensena de un numero sensible."""
    if not valor:
        return None
    limpio = str(valor).strip()
    return "····" + limpio[-4:] if len(limpio) > 4 else "····"


def _anotar(db: Session, actor: m.Usuario, persona: m.Persona, accion: str,
            antes: str | None = None, despues: str | None = None,
            detalle: str | None = None) -> None:
    """Su historial: en la bitacora de administracion, con el freelance
    como objeto. La ficha lo ensena."""
    accesos.anotar(db, actor, accion, "freelance", persona.id,
                   antes=antes, despues=despues, detalle=detalle)


def ficha_de(db: Session, persona_id: int) -> tuple[m.Persona, m.Freelance]:
    persona = db.get(m.Persona, persona_id)
    if not persona or not persona.es_freelance:
        raise HTTPException(404, f"No existe el freelance {persona_id}")
    ficha = db.query(m.Freelance).filter_by(persona_id=persona.id).first()
    if ficha is None:
        # Un freelance de antes de la seccion 111 que la migracion no
        # alcanzo (dado de alta por la API vieja entre la migracion y el
        # arranque): se le arma su ficha con lo que hay.
        nombre, apellidos = partir_nombre(persona.nombre)
        ficha = m.Freelance(persona_id=persona.id, tipo=PROGRAMADO,
                            nombre=nombre, apellidos=apellidos)
        db.add(ficha)
        db.flush()
    return persona, ficha


def partir_nombre(completo: str) -> tuple[str, str]:
    """"Raul Ortiz" -> ("Raul", "Ortiz"); "Maria del Carmen Lopez Diaz"
    -> ("Maria del Carmen", "Lopez Diaz"). Con dos apellidos al final,
    como se escribe en Mexico; si solo hay una palabra, sin apellidos."""
    partes = (completo or "").split()
    if len(partes) <= 1:
        return (completo or "").strip(), ""
    if len(partes) == 2:
        return partes[0], partes[1]
    return " ".join(partes[:-2]), " ".join(partes[-2:])


def nombre_completo(nombre: str, apellidos: str) -> str:
    return " ".join(f"{nombre} {apellidos}".split())


# ============================================================ los costos

def _modalidades_del_pais(db: Session, pais_id: int) -> dict[str, m.Modalidad]:
    return {x.codigo.value: x for x in db.query(m.Modalidad)
            .filter_by(pais_id=pais_id).all()
            if x.codigo.value in MODALIDADES}


def costos_por_persona(db: Session, persona_ids: list[int]) -> dict[int, dict]:
    """{persona_id: {"full_day": 2000.0, "medio_dia": ..., "transfer":
    ..., "hora_extra": 200.0, "moneda": "MXN"}} de una sola consulta."""
    salida: dict[int, dict] = {}
    if not persona_ids:
        return salida
    filas = (db.query(m.TarifaFreelance, m.Modalidad)
             .join(m.Modalidad, m.Modalidad.id == m.TarifaFreelance.modalidad_id)
             .filter(m.TarifaFreelance.persona_id.in_(persona_ids)).all())
    for tarifa, modalidad in filas:
        codigo = modalidad.codigo.value
        if codigo not in MODALIDADES:
            continue
        caja = salida.setdefault(tarifa.persona_id, {})
        caja[codigo] = float(tarifa.costo)
        caja["moneda"] = tarifa.moneda.value
        if codigo == "full_day":
            caja["hora_extra"] = (float(tarifa.costo_hora_extra)
                                  if tarifa.costo_hora_extra is not None
                                  else None)
    return salida


def _monto(valor, campo: str, obligatorio: bool = True) -> Decimal | None:
    if valor is None or str(valor).strip() == "":
        if obligatorio:
            raise HTTPException(400, {
                "mensaje": f"Falta el costo de {campo}.",
                "que_hacer": "Sin sus costos no se le puede asignar ni "
                             "pagar."})
        return None
    try:
        monto = Decimal(str(valor).replace(",", "").strip())
    except InvalidOperation:
        raise HTTPException(400, f"El costo de {campo} no es un número.")
    if monto < 0 or (obligatorio and monto == 0):
        raise HTTPException(400, f"El costo de {campo} tiene que ser mayor "
                                 "que cero.")
    return monto.quantize(Decimal("0.01"))


def _texto_costos(c: dict) -> str:
    def f(x):
        return "—" if x is None else f"{x:,.2f}"
    return (f"día completo {f(c.get('full_day'))} · medio día "
            f"{f(c.get('medio_dia'))} · transfer {f(c.get('transfer'))} · "
            f"hora extra {f(c.get('hora_extra'))}")


def poner_costos(db: Session, actor: m.Usuario, persona: m.Persona,
                 dia_completo, medio_dia, transfer, hora_extra) -> dict:
    """Sus cuatro costos (decisiones 3 y 11), en la moneda de su pais.

    Viven donde siempre --`TarifaFreelance`, una por modalidad--, que es
    de donde el corte del lunes le paga. La hora extra va en la del dia
    completo: es la unica modalidad que la genera.
    """
    pais = persona.plaza.pais if persona.plaza else None
    if pais is None:
        raise HTTPException(409, "El freelance no tiene ciudad: sin ella no "
                                 "se sabe en que moneda se le paga.")
    montos = {"full_day": _monto(dia_completo, "día completo"),
              "medio_dia": _monto(medio_dia, "medio día"),
              "transfer": _monto(transfer, "transfer")}
    extra = _monto(hora_extra, "hora extra", obligatorio=False)
    modalidades = _modalidades_del_pais(db, pais.id)
    faltan = [c for c in MODALIDADES if c not in modalidades]
    if faltan:
        raise HTTPException(409, f"{pais.nombre} no tiene las modalidades "
                                 f"{', '.join(faltan)} en Catálogos.")
    antes = costos_por_persona(db, [persona.id]).get(persona.id, {})
    for codigo, monto in montos.items():
        modalidad = modalidades[codigo]
        tarifa = (db.query(m.TarifaFreelance)
                  .filter_by(persona_id=persona.id,
                             modalidad_id=modalidad.id).first())
        if tarifa is None:
            tarifa = m.TarifaFreelance(persona_id=persona.id,
                                       modalidad_id=modalidad.id,
                                       costo=monto, moneda=pais.moneda_local)
            db.add(tarifa)
        tarifa.costo = monto
        tarifa.moneda = pais.moneda_local
        tarifa.costo_hora_extra = extra if codigo == "full_day" else None
    db.flush()
    despues = costos_por_persona(db, [persona.id]).get(persona.id, {})
    if _texto_costos(antes) != _texto_costos(despues):
        _anotar(db, actor, persona, "costos",
                antes=_texto_costos(antes) if antes else None,
                despues=_texto_costos(despues), detalle=persona.nombre)
    return despues


def faltan_costos(db: Session, persona: m.Persona,
                  modalidades: set[str]) -> list[str]:
    """Las modalidades de estas jornadas que no tienen su costo."""
    costos = costos_por_persona(db, [persona.id]).get(persona.id, {})
    return sorted(x for x in modalidades if x in MODALIDADES
                  and costos.get(x) is None)


# ======================================================= los requisitos

def requisitos_de(db: Session, pais_id: int | None) -> list[m.RequisitoFreelance]:
    if pais_id is None:
        return []
    return (db.query(m.RequisitoFreelance)
            .filter_by(pais_id=pais_id, activo=True)
            .order_by(m.RequisitoFreelance.orden, m.RequisitoFreelance.id)
            .all())


def del_tipo(requisitos: list, tipo: str) -> list:
    return [r for r in requisitos
            if (r.emergencia if tipo == EMERGENCIA else r.programado)]


def documentos_de(db: Session, persona_ids: list[int]) -> dict[int, dict[int, list]]:
    """{persona_id: {requisito_id: [documentos sin reemplazar]}}."""
    salida: dict[int, dict[int, list]] = {}
    if not persona_ids:
        return salida
    for d in (db.query(m.DocumentoFreelance)
              .filter(m.DocumentoFreelance.persona_id.in_(persona_ids),
                      m.DocumentoFreelance.reemplazado_en.is_(None))
              .order_by(m.DocumentoFreelance.id).all()):
        salida.setdefault(d.persona_id, {}).setdefault(
            d.requisito_id, []).append(d)
    return salida


def renglon(requisito: m.RequisitoFreelance, docs: list, hoy: date) -> dict:
    """Como esta un requisito: su estado y los dos documentos que cuentan
    --el validado que rige y el nuevo que espera--."""
    efectivo = next((d for d in reversed(docs) if d.estado == VALIDADO), None)
    pendiente = next((d for d in reversed(docs) if d.estado != VALIDADO), None)
    if requisito.vigencia == "servicio":
        # La de la caseta: se aplica en cada servicio y no se pide antes
        # de asignar. Solo detiene si la ultima salio positiva.
        ultimo = docs[-1] if docs else None
        estado = RECHAZADO if ultimo and ultimo.estado == RECHAZADO else "caseta"
        return {"requisito": requisito, "estado": estado, "cuenta": False,
                "efectivo": efectivo, "pendiente": pendiente, "dias": None}
    dias = None
    if efectivo is not None:
        if efectivo.vence_en is not None:
            dias = (efectivo.vence_en - hoy).days
        if dias is not None and dias < 0:
            estado = "vencido"
        elif dias is not None and dias <= DIAS_DE_AVISO:
            estado = "por_vencer"
        else:
            estado = VALIDADO
    elif pendiente is not None:
        estado = pendiente.estado
    else:
        estado = "falta"
    return {"requisito": requisito, "estado": estado, "cuenta": True,
            "efectivo": efectivo, "pendiente": pendiente, "dias": dias}


def resumir(tipo: str, renglones: list[dict], ficha: m.Freelance | None,
            hoy: date) -> dict:
    """El estado de su expediente, en una palabra y con su porque."""
    cuentan = [r for r in renglones if r["cuenta"]]
    buenos = [r for r in cuentan if r["estado"] in (VALIDADO, "por_vencer")]
    faltan = [r for r in renglones if r["estado"] in ("falta", RECHAZADO)]
    por_revisar = [r for r in cuentan if r["estado"] == POR_REVISAR]
    vencidos = [r for r in cuentan if r["estado"] == "vencido"]
    por_vencer = [r for r in cuentan if r["estado"] == "por_vencer"]
    # Lo que espera a Recursos Humanos, tambien la renovacion que se subio
    # antes de que venciera la anterior: es su lista de trabajo.
    esperan = sum(1 for r in renglones if r["pendiente"] is not None
                  and r["pendiente"].estado == POR_REVISAR)
    plazo = ficha.plazo_programado if ficha is not None else None

    if not renglones:
        estado = "sin_requisitos"
    elif vencidos:
        estado = "vencido"
    elif faltan:
        estado = "faltan"
    elif por_revisar:
        estado = POR_REVISAR
    elif tipo == EMERGENCIA and plazo is not None:
        estado = "plazo_vencido" if hoy > plazo else "plazo"
    else:
        estado = "listo"

    con_fecha = [r for r in cuentan if r["efectivo"] is not None
                 and r["efectivo"].vence_en is not None]
    proximo = min(con_fecha, key=lambda r: r["efectivo"].vence_en,
                  default=None)
    return {
        "tipo": tipo,
        "estado": estado,
        "asignable": estado in ("listo", "plazo"),
        "validados": len(buenos),
        "total": len(cuentan),
        "faltan": [r["requisito"].nombre for r in faltan],
        "rechazados": [r["requisito"].nombre for r in faltan
                       if r["estado"] == RECHAZADO],
        "por_revisar": len(por_revisar),
        "esperan_revision": esperan,
        "vencidos": [{"nombre": r["requisito"].nombre,
                      "fecha": r["efectivo"].vence_en.isoformat()}
                     for r in vencidos],
        "por_vencer": [{"nombre": r["requisito"].nombre,
                        "fecha": r["efectivo"].vence_en.isoformat(),
                        "dias": r["dias"]} for r in por_vencer],
        "proximo_vencimiento": ({"nombre": proximo["requisito"].nombre,
                                 "fecha": proximo["efectivo"].vence_en.isoformat()}
                                if proximo else None),
        "plazo_programado": plazo.isoformat() if plazo else None,
        "dias_de_plazo": (plazo - hoy).days if plazo else None,
    }


def expediente(db: Session, persona: m.Persona, ficha: m.Freelance,
               hoy: date | None = None, requisitos: list | None = None,
               docs: dict | None = None) -> dict:
    """El resumen de su tipo, y --si es de emergencia-- cuanto le falta
    para programado."""
    hoy = hoy or _hoy(db, persona)
    pais_id = persona.plaza.pais_id if persona.plaza else None
    requisitos = requisitos if requisitos is not None else requisitos_de(db, pais_id)
    suyos = (docs if docs is not None
             else documentos_de(db, [persona.id]).get(persona.id, {}))
    renglones = [renglon(r, suyos.get(r.id, []), hoy)
                 for r in del_tipo(requisitos, ficha.tipo)]
    salida = resumir(ficha.tipo, renglones, ficha, hoy)
    if ficha.tipo == EMERGENCIA:
        de_programado = [renglon(r, suyos.get(r.id, []), hoy)
                         for r in del_tipo(requisitos, PROGRAMADO)]
        falta = [r["requisito"].nombre for r in de_programado
                 if r["cuenta"] and r["estado"] not in (VALIDADO, "por_vencer")]
        salida["para_programado"] = {
            "faltan": falta,
            "total": sum(1 for r in de_programado if r["cuenta"])}
    return salida


def resumen_por_persona(db: Session, personas: list, fichas: dict,
                        ahora: datetime | None = None) -> dict[int, dict]:
    """El resumen de muchos de una vez: para la lista y para asignar."""
    relojes = reloj.Relojes(db, ahora)
    docs = documentos_de(db, [p.id for p in personas])
    por_pais: dict = {}
    salida = {}
    for p in personas:
        ficha = fichas.get(p.id)
        if ficha is None:
            continue
        pais_id = p.plaza.pais_id if p.plaza else None
        if pais_id not in por_pais:
            por_pais[pais_id] = requisitos_de(db, pais_id)
        salida[p.id] = expediente(db, p, ficha, relojes.hoy(pais_id),
                                  por_pais[pais_id], docs.get(p.id, {}))
    return salida


# ======================================================= los documentos

def _limpio(valor) -> str:
    return " ".join(str(valor or "").split())


CURP = re.compile(r"^[A-Z][AEIOUX][A-Z]{2}\d{6}[HMX][A-Z]{5}[A-Z0-9]\d$")
RFC = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")


def clabe_valida(clabe: str) -> bool:
    """La CLABE de Mexico: 18 digitos y el ultimo es de control (pesos 3,
    7 y 1). Un digito mal escrito deja el deposito en otra cuenta o
    rebotado, y nadie lo nota hasta el lunes."""
    if not re.fullmatch(r"\d{18}", clabe or ""):
        return False
    pesos = (3, 7, 1) * 6
    suma = sum((int(d) * w) % 10 for d, w in zip(clabe[:17], pesos))
    return (10 - suma % 10) % 10 == int(clabe[17])


def _numero(requisito: m.RequisitoFreelance, crudo, pais_codigo: str) -> str:
    numero = re.sub(r"[\s-]", "", str(crudo or "")).upper()
    if not numero:
        raise HTTPException(400, f"Falta el número de {requisito.nombre}.")
    if pais_codigo == "MX":
        if requisito.clave == "curp" and not CURP.fullmatch(numero):
            raise HTTPException(400, "La CURP no tiene la forma de una CURP: "
                                     "18 letras y números.")
        if requisito.clave == "nss" and not re.fullmatch(r"\d{11}", numero):
            raise HTTPException(400, "El NSS son 11 dígitos.")
        if requisito.clave == "rfc" and not RFC.fullmatch(numero):
            raise HTTPException(400, "El RFC no tiene la forma de un RFC: 13 "
                                     "letras y números.")
    return numero[:40]


def _fecha(valor, que: str) -> date | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        raise HTTPException(400, f"La fecha {que} no es una fecha.")


def preparar(db: Session, persona: m.Persona, requisito: m.RequisitoFreelance,
             datos: dict, fecha_documento, vence_en, archivos: list,
             hoy: date) -> dict:
    """Revisa lo que se carga y lo deja listo para guardar: los datos
    limpios, la fecha del documento y cuando vence. Lo que no cuadra se
    dice aqui, antes de guardar nada."""
    pais = persona.plaza.pais if persona.plaza else None
    codigo = pais.codigo if pais else ""
    captura = requisito.captura
    datos = datos or {}
    limpio: dict = {}
    fecha_doc = _fecha(fecha_documento, "del documento")
    vence = _fecha(vence_en, "de vencimiento")

    if captura in CON_ARCHIVO and not archivos:
        raise HTTPException(400, f"Falta el archivo de {requisito.nombre}: "
                                 "PDF o foto.")
    if len(archivos) > MAX_ARCHIVOS:
        raise HTTPException(400, f"Son muchos archivos: hasta {MAX_ARCHIVOS} "
                                 "por requisito.")

    if captura in ("numero", "archivo_numero"):
        limpio["numero"] = _numero(requisito, datos.get("numero"), codigo)
    elif captura == "banco":
        banco = _limpio(datos.get("banco"))
        clabe = re.sub(r"\s", "", str(datos.get("clabe") or ""))
        titular = _limpio(datos.get("titular"))
        if not banco or not clabe or not titular:
            raise HTTPException(400, "Faltan el banco, la CLABE o el titular "
                                     "de la cuenta.")
        if codigo == "MX" and not clabe_valida(clabe):
            raise HTTPException(400, "La CLABE no es válida: son 18 dígitos y "
                                     "el último no cuadra con los demás. "
                                     "Revísala contra la carátula.")
        limpio.update(banco=banco[:80], clabe=clabe[:40], titular=titular[:160])
    elif captura == "riesgo":
        riesgo = str(datos.get("riesgo") or "").strip()
        if riesgo not in ("1", "2", "3"):
            raise HTTPException(400, "El riesgo de la Veritas es 1, 2 o 3.")
        limpio["riesgo"] = int(riesgo)
    elif captura == "entrevista":
        cuando = _fecha(datos.get("fecha"), "de la entrevista")
        quien = _limpio(datos.get("quien"))
        resultado = str(datos.get("resultado") or "")
        if cuando is None or not quien or resultado not in ("apto", "no_apto"):
            raise HTTPException(400, "De la entrevista va la fecha, quién la "
                                     "hizo y si salió apto.")
        if cuando > hoy:
            raise HTTPException(400, "La entrevista no puede ser de un día que "
                                     "no ha llegado.")
        limpio.update(fecha=cuando.isoformat(), quien=quien[:120],
                      resultado=resultado,
                      notas=_limpio(datos.get("notas"))[:300] or None)
        fecha_doc = cuando
    elif captura == "contactos":
        filas = datos.get("contactos") or []
        buenos = []
        for x in filas:
            nombre = _limpio((x or {}).get("nombre"))
            parentesco = _limpio((x or {}).get("parentesco"))
            telefono = telefonos.normalizar(
                db, _limpio((x or {}).get("telefono")),
                pais.id if pais else None)
            if nombre or parentesco or telefono:
                if not (nombre and parentesco and telefono):
                    raise HTTPException(400, "De cada contacto van su nombre, "
                                             "su parentesco y su teléfono.")
                buenos.append({"nombre": nombre[:120],
                               "parentesco": parentesco[:60],
                               "telefono": telefono[:40]})
        if len(buenos) < 2:
            raise HTTPException(400, "Son dos contactos de emergencia.")
        limpio["contactos"] = buenos[:3]
    elif captura == "prueba":
        resultado = str(datos.get("resultado") or "")
        aplico = _limpio(datos.get("aplico"))
        if resultado not in ("negativo", "positivo") or not aplico:
            raise HTTPException(400, "De la prueba de la caseta va el "
                                     "resultado y quién la aplicó.")
        if fecha_doc is None:
            fecha_doc = hoy
        limpio.update(resultado=resultado, aplico=aplico[:120],
                      servicio=_limpio(datos.get("servicio"))[:40] or None)
    nota = _limpio(datos.get("nota"))[:300]
    if nota:
        limpio["nota"] = nota

    if requisito.vigencia == "documento":
        if vence is None:
            raise HTTPException(400, f"Falta hasta cuándo vale "
                                     f"{requisito.nombre}: la fecha que trae "
                                     "el documento.")
        if vence < hoy:
            raise HTTPException(400, f"{requisito.nombre} ya venció el "
                                     f"{vence:%d/%m/%Y}: se necesita una "
                                     "vigente.")
    elif requisito.vigencia == "meses":
        if fecha_doc is None:
            raise HTTPException(400, f"Falta la fecha de {requisito.nombre}: "
                                     "la que trae el documento.")
        if fecha_doc > hoy:
            raise HTTPException(400, "La fecha del documento no puede ser de "
                                     "un día que no ha llegado.")
        if (requisito.antiguedad_meses
                and fecha_doc < sumar_meses(hoy, -requisito.antiguedad_meses)):
            raise HTTPException(400, {
                "mensaje": f"{requisito.nombre} tiene más de "
                           f"{requisito.antiguedad_meses} meses: es del "
                           f"{fecha_doc:%d/%m/%Y}.",
                "que_hacer": "Pídele uno reciente."})
        vence = sumar_meses(fecha_doc, requisito.vigencia_meses or 12)
        if vence < hoy:
            raise HTTPException(400, f"{requisito.nombre} ya venció: es del "
                                     f"{fecha_doc:%d/%m/%Y} y valía hasta el "
                                     f"{vence:%d/%m/%Y}.")
    else:
        vence = None
    return {"datos": limpio, "fecha_documento": fecha_doc, "vence_en": vence}


def revisar_archivo(nombre: str, tipo: str | None, contenido: bytes) -> tuple[str, str]:
    """PDF o foto, hasta 10 MB. Devuelve el nombre y el tipo limpios."""
    tipo = (tipo or "").split(";")[0].strip().lower()
    if tipo == "image/jpg":
        tipo = "image/jpeg"
    if tipo not in TIPOS_DE_ARCHIVO:
        raise HTTPException(400, {
            "mensaje": f"«{nombre}» no es un PDF ni una foto.",
            "que_hacer": "Súbelo como PDF, JPG o PNG."})
    if not contenido:
        raise HTTPException(400, f"«{nombre}» llegó vacío.")
    if len(contenido) > LIMITE_ARCHIVO:
        raise HTTPException(400, f"«{nombre}» pasa de 10 MB "
                                 f"({len(contenido) / 1024 / 1024:.1f} MB).")
    if tipo == "application/pdf" and not contenido.startswith(b"%PDF"):
        raise HTTPException(400, f"«{nombre}» dice ser PDF y no lo es.")
    limpio = re.sub(r"[\x00-\x1f/\\]", "_", nombre or "archivo").strip() or "archivo"
    return limpio[-200:], tipo


def cargar(db: Session, actor: m.Usuario, persona: m.Persona,
           ficha: m.Freelance, requisito: m.RequisitoFreelance,
           preparado: dict, archivos: list, validar: bool,
           ahora: datetime | None = None) -> m.DocumentoFreelance:
    """Guarda lo que se cargo para un requisito.

    Quien valida --Recursos Humanos-- lo deja validado al cargarlo si asi
    lo dice: lo que tiene en la mano ya lo reviso. Lo que carga otro
    espera su visto bueno. La prueba de la caseta se resuelve con su
    resultado: negativa, vale; positiva, detiene.
    """
    persona_pais = persona.plaza.pais_id if persona.plaza else None
    if requisito.pais_id != persona_pais:
        raise HTTPException(409, "Ese requisito es de otro país.")
    if not requisito.activo:
        raise HTTPException(409, "Ese requisito ya no se pide.")
    momento = ahora or _ahora()
    datos = preparado["datos"]

    estado, motivo = POR_REVISAR, None
    if requisito.captura == "prueba":
        estado = VALIDADO if datos["resultado"] == "negativo" else RECHAZADO
        motivo = "Resultado positivo" if estado == RECHAZADO else None
    elif requisito.captura == "entrevista" and datos["resultado"] == "no_apto":
        estado, motivo = RECHAZADO, "No apto en la entrevista técnica"
    elif validar:
        if not auth.puede_el_usuario(db, actor, "freelance.validar"):
            raise HTTPException(403, "Solo Recursos Humanos valida el "
                                     "expediente.")
        estado = VALIDADO

    # Lo que esperaba revision --o se rechazo-- lo reemplaza lo nuevo.
    for viejo in (db.query(m.DocumentoFreelance)
                  .filter_by(persona_id=persona.id, requisito_id=requisito.id)
                  .filter(m.DocumentoFreelance.reemplazado_en.is_(None),
                          m.DocumentoFreelance.estado != VALIDADO).all()):
        viejo.reemplazado_en = momento

    doc = m.DocumentoFreelance(
        persona_id=persona.id, requisito_id=requisito.id, estado=estado,
        datos=json.dumps(datos, ensure_ascii=False) if datos else None,
        fecha_documento=preparado["fecha_documento"],
        vence_en=preparado["vence_en"], subido_por_id=actor.persona_id,
        subido_en=momento, motivo_rechazo=motivo)
    if estado != POR_REVISAR:
        doc.revisado_por_id = actor.persona_id
        doc.revisado_en = momento
    db.add(doc)
    db.flush()
    for nombre, tipo, contenido in archivos:
        guardar_archivo(db, doc, nombre, tipo, contenido)
    _anotar(db, actor, persona, "documento cargado",
            despues=estado, detalle=requisito.nombre)
    if estado == VALIDADO:
        _al_validar(db, actor, persona, ficha, doc, momento)
    db.flush()
    return doc


def _al_validar(db: Session, actor: m.Usuario, persona: m.Persona,
                ficha: m.Freelance, doc: m.DocumentoFreelance,
                momento: datetime) -> None:
    """Lo que pasa cuando un documento queda validado: el anterior se
    retira, la cuenta bancaria pasa a la persona --de ahi deposita
    finanzas-- y el de emergencia que ya completo lo de programado pasa
    a programado."""
    for anterior in (db.query(m.DocumentoFreelance)
                     .filter_by(persona_id=persona.id,
                                requisito_id=doc.requisito_id,
                                estado=VALIDADO)
                     .filter(m.DocumentoFreelance.reemplazado_en.is_(None),
                             m.DocumentoFreelance.id != doc.id).all()):
        anterior.reemplazado_en = momento
    requisito = doc.requisito or db.get(m.RequisitoFreelance, doc.requisito_id)
    if requisito.captura == "banco" and doc.datos:
        datos = json.loads(doc.datos)
        persona.banco = datos.get("banco")
        persona.clabe = datos.get("clabe")
        persona.titular_cuenta = datos.get("titular")
    db.flush()
    if ficha.tipo == EMERGENCIA:
        info = expediente(db, persona, ficha)
        if not info["para_programado"]["faltan"]:
            ficha.tipo = PROGRAMADO
            ficha.plazo_programado = None
            ficha.plazo_puesto_en = None
            ficha.plazo_avisado_en = None
            _anotar(db, actor, persona, "paso a programado",
                    antes=EMERGENCIA, despues=PROGRAMADO,
                    detalle="completó lo de programado")


def validar(db: Session, actor: m.Usuario, doc: m.DocumentoFreelance,
            ahora: datetime | None = None) -> None:
    if doc.reemplazado_en is not None:
        raise HTTPException(409, "Ese documento ya fue reemplazado por otro.")
    if doc.estado != POR_REVISAR:
        raise HTTPException(409, "Ese documento ya fue revisado.")
    persona, ficha = ficha_de(db, doc.persona_id)
    momento = ahora or _ahora()
    doc.estado = VALIDADO
    doc.revisado_por_id = actor.persona_id
    doc.revisado_en = momento
    doc.motivo_rechazo = None
    _anotar(db, actor, persona, "documento validado",
            detalle=doc.requisito.nombre)
    _al_validar(db, actor, persona, ficha, doc, momento)


def rechazar(db: Session, actor: m.Usuario, doc: m.DocumentoFreelance,
             motivo: str, ahora: datetime | None = None) -> None:
    motivo = _limpio(motivo)
    if len(motivo) < 5:
        raise HTTPException(400, "Di por qué se rechaza: es lo que lee quien "
                                 "tiene que conseguir el documento otra vez.")
    if doc.reemplazado_en is not None:
        raise HTTPException(409, "Ese documento ya fue reemplazado por otro.")
    if doc.estado != POR_REVISAR:
        raise HTTPException(409, "Ese documento ya fue revisado.")
    persona, _ = ficha_de(db, doc.persona_id)
    doc.estado = RECHAZADO
    doc.revisado_por_id = actor.persona_id
    doc.revisado_en = ahora or _ahora()
    doc.motivo_rechazo = motivo[:300]
    _anotar(db, actor, persona, "documento rechazado", despues=motivo[:200],
            detalle=doc.requisito.nombre)


# ========================================================= los archivos

def _destino() -> str:
    return (settings.expedientes_destino or "").strip()


def guardar_archivo(db: Session, doc: m.DocumentoFreelance, nombre: str,
                    tipo: str, contenido: bytes,
                    google: archivo_motor.Google | None = None) -> m.ArchivoFreelance:
    """El archivo, al deposito de Google si esta puesto; si no --o si
    Google no contesta--, aqui adentro hasta la mudanza de cada hora."""
    fila = m.ArchivoFreelance(documento_id=doc.id, nombre=nombre, tipo=tipo,
                              tamano=len(contenido),
                              md5=hashlib.md5(contenido).hexdigest(),
                              contenido=contenido)
    db.add(fila)
    db.flush()
    if _destino():
        try:
            mudar(db, fila, google)
        except archivo_motor.Fallo as error:
            registro.warning("el archivo %s se queda en la base: %s",
                             fila.id, error)
    return fila


def _ruta(fila: m.ArchivoFreelance) -> str:
    doc = fila.documento
    extension = TIPOS_DE_ARCHIVO.get(fila.tipo, "")
    return (f"freelance-{doc.persona_id}/{doc.requisito.clave}-"
            f"{doc.id}-{fila.id}-{fila.md5[:8]}{extension}")


def mudar(db: Session, fila: m.ArchivoFreelance,
          google: archivo_motor.Google | None = None) -> None:
    """Lo sube sin escribir encima de nada, pregunta que llego y solo si
    la huella cuadra lo quita de la base. Si ya estaba --se subio y no se
    alcanzo a anotar--, se compara la huella y se termina."""
    if fila.objeto or fila.contenido is None:
        return
    google = google or archivo_motor.Google(_destino())
    ruta = google.ruta(_ruta(fila))
    try:
        google.subir(ruta, fila.contenido, fila.tipo,
                     {"persona": str(fila.documento.persona_id),
                      "requisito": fila.documento.requisito.clave})
    except archivo_motor.YaExiste:
        pass
    dicho = google.describir(ruta) or {}
    huella = base64.b64decode(dicho.get("md5Hash", "")).hex() if dicho.get("md5Hash") else ""
    if huella != fila.md5 or int(dicho.get("size") or -1) != fila.tamano:
        raise archivo_motor.Fallo(f"Google no tiene completo el archivo {fila.id}")
    fila.objeto = f"gs://{google.deposito}/{ruta}"
    fila.contenido = None
    db.flush()


def mudar_pendientes(db: Session, limite: int = 200,
                     google: archivo_motor.Google | None = None) -> dict:
    """La tarea de cada hora: lo que se quedo en la base, al deposito."""
    if not _destino():
        return {"mudados": 0, "omitido": "sin EXPEDIENTES_DESTINO"}
    filas = (db.query(m.ArchivoFreelance)
             .filter(m.ArchivoFreelance.objeto.is_(None),
                     m.ArchivoFreelance.contenido.isnot(None))
             .order_by(m.ArchivoFreelance.id).limit(limite).all())
    mudados, fallas = 0, 0
    google = google or archivo_motor.Google(_destino())
    for fila in filas:
        try:
            mudar(db, fila, google)
            db.commit()
            mudados += 1
        except archivo_motor.Fallo as error:
            db.rollback()
            fallas += 1
            registro.error("no se pudo mudar el archivo %s: %s", fila.id, error)
            if fallas >= archivo_motor.SEGUIDAS:
                break
    return {"mudados": mudados, "fallas": fallas}


def leer_archivo(fila: m.ArchivoFreelance,
                 google: archivo_motor.Google | None = None) -> bytes:
    if fila.contenido is not None:
        return fila.contenido
    if not fila.objeto:
        raise HTTPException(404, "Ese archivo no tiene contenido.")
    try:
        deposito, ruta = archivo_motor.partir(fila.objeto)
        google = google or archivo_motor.Google(f"gs://{deposito}")
        datos, _ = google.bajar(ruta)
    except archivo_motor.Fallo as error:
        raise HTTPException(502, f"El depósito de Google no entregó el "
                                 f"archivo: {error}")
    return datos


# ======================================================= para asignar

def _otros_servicios(db: Session, persona_id: int,
                     servicio_id: int | None) -> list[tuple[int, date]]:
    """Los otros servicios de esta persona y el ultimo dia de cada uno,
    sin los dias cancelados."""
    filas = (db.query(m.Equipo.servicio_id, m.Jornada.fecha)
             .join(m.Jornada, m.Jornada.equipo_id == m.Equipo.id)
             .join(m.AsignacionPersonal,
                   m.AsignacionPersonal.jornada_id == m.Jornada.id)
             .filter(m.AsignacionPersonal.persona_id == persona_id,
                     m.Jornada.estatus != m.EstatusJornada.CANCELADA).all())
    ultimos: dict[int, date] = {}
    for sid, fecha in filas:
        if sid == servicio_id:
            continue
        ultimos[sid] = max(fecha, ultimos.get(sid, fecha))
    return sorted(ultimos.items(), key=lambda x: x[1])


def autorizacion_de(db: Session, persona_id: int,
                    servicio_id: int) -> m.AutorizacionFreelance | None:
    return (db.query(m.AutorizacionFreelance)
            .filter_by(persona_id=persona_id, servicio_id=servicio_id).first())


def _razon(info: dict) -> str:
    """Por que no se asigna, dicho en una frase."""
    e = info["estado"]
    if e == "vencido":
        v = info["vencidos"][0]
        return (f"{v['nombre']} venció el "
                f"{date.fromisoformat(v['fecha']):%d/%m/%Y}")
    if e == "faltan":
        n = len(info["faltan"])
        return (f"le falta {info['faltan'][0]}" if n == 1
                else f"le faltan {n} requisitos: " + ", ".join(info["faltan"][:4]))
    if e == POR_REVISAR:
        return (f"{info['por_revisar']} documento(s) esperan a Recursos "
                "Humanos")
    if e == "plazo_vencido":
        return ("venció su plazo para completar lo de programado el "
                f"{date.fromisoformat(info['plazo_programado']):%d/%m/%Y}")
    if e == "sin_requisitos":
        return ("su país no tiene requisitos de freelance en Catálogos")
    return ""


def para_asignar(db: Session, persona: m.Persona, servicio: m.Servicio,
                 modalidades: set[str] | None = None,
                 ahora: datetime | None = None,
                 info: dict | None = None,
                 ficha: m.Freelance | None = None) -> dict:
    """Si se le puede asignar este servicio al freelance, y por que no.

    El orden: implantado nunca (decision 10); sin costos no (3); con la
    urgencia autorizada si; con el expediente incompleto o vencido no
    (4); y el de emergencia que repite, con su plazo (5).
    """
    if servicio.tipo == m.TipoServicio.IMPLANTADO:
        return {"asignable": False, "motivo": "implantado",
                "mensaje": NO_EN_IMPLANTADO["mensaje"], "puede_pedir": False}
    if not persona.activo:
        return {"asignable": False, "motivo": "baja", "puede_pedir": False,
                "mensaje": f"{persona.nombre} está dado de baja."}
    if ficha is None:
        _, ficha = ficha_de(db, persona.id)
    faltan = faltan_costos(db, persona, modalidades or set())
    if faltan:
        return {"asignable": False, "motivo": "costos", "puede_pedir": False,
                "faltan_costos": faltan,
                "mensaje": f"{persona.nombre} no tiene su costo de "
                           + ", ".join(_modalidad_texto(x) for x in faltan)
                           + ": sin costos no se le asigna."}
    info = info or expediente(db, persona, ficha,
                              _hoy(db, persona, ahora))
    hoy = _hoy(db, persona, ahora)
    autorizacion = autorizacion_de(db, persona.id, servicio.id)
    resp = {"asignable": info["asignable"], "motivo": None, "expediente": info,
            "autorizacion": ({"id": autorizacion.id,
                              "estado": autorizacion.estado,
                              "respuesta": autorizacion.respuesta}
                             if autorizacion else None),
            "puede_pedir": True, "plazo_nuevo": None}
    if autorizacion is not None and autorizacion.estado == "autorizada":
        resp.update(asignable=True, motivo="autorizada")
        return resp
    if not info["asignable"]:
        resp.update(motivo=info["estado"],
                    mensaje=f"{persona.nombre} no se asigna todavía: "
                            f"{_razon(info)}.")
        return resp
    # El de emergencia que repite (decision 5): con este, su segundo
    # servicio. El plazo cuenta desde el ultimo que tuvo.
    if ficha.tipo == EMERGENCIA and ficha.plazo_programado is None:
        otros = _otros_servicios(db, persona.id, servicio.id)
        if otros:
            plazo = otros[-1][1] + timedelta(days=DIAS_DEL_PLAZO)
            resp["plazo_nuevo"] = plazo.isoformat()
            if hoy > plazo and info.get("para_programado", {}).get("faltan"):
                resp.update(asignable=False, motivo="plazo_vencido",
                            mensaje=f"{persona.nombre} no se asigna: es su "
                                    "segundo servicio y el último fue el "
                                    f"{otros[-1][1]:%d/%m/%Y}; el plazo de "
                                    f"{DIAS_DEL_PLAZO} días para completar lo "
                                    "de programado ya venció.")
    return resp


def _modalidad_texto(codigo: str) -> str:
    return {"full_day": "día completo", "medio_dia": "medio día",
            "transfer": "transfer"}.get(codigo, codigo)


def revisar_para_asignar(db: Session, persona: m.Persona,
                         servicio: m.Servicio, modalidades: set[str],
                         ahora: datetime | None = None) -> dict | None:
    """La puerta de toda asignacion: el freelance que no se puede asignar
    no entra, y la respuesta dice por que y que se puede hacer."""
    if not persona.es_freelance:
        return None
    if servicio.tipo == m.TipoServicio.IMPLANTADO:
        raise HTTPException(409, NO_EN_IMPLANTADO)
    resp = para_asignar(db, persona, servicio, modalidades, ahora)
    if resp["asignable"]:
        return resp
    raise HTTPException(409, {
        "mensaje": resp["mensaje"],
        "que_hacer": (UNA_VEZ_NO_SE_ASIGNA if resp.get("puede_pedir")
                      else "Dirección de operaciones o la gerencia de "
                           "administración ponen sus costos en su ficha, en "
                           "Personal de seguridad → Freelance."
                      if resp["motivo"] == "costos" else None),
        "codigo": "freelance_no_asignable",
        "freelance": {"persona_id": persona.id, "servicio_id": servicio.id,
                      "motivo": resp["motivo"],
                      "puede_pedir": resp.get("puede_pedir", False),
                      "autorizacion": resp.get("autorizacion")},
    })


def al_asignar(db: Session, actor: m.Usuario, persona: m.Persona,
               servicio: m.Servicio, revisado: dict | None) -> None:
    """Despues de asignar: si era el segundo servicio del de emergencia,
    arranca su plazo y Recursos Humanos se entera."""
    if not persona.es_freelance or not revisado:
        return
    plazo = revisado.get("plazo_nuevo")
    if not plazo:
        return
    _, ficha = ficha_de(db, persona.id)
    if ficha.tipo != EMERGENCIA or ficha.plazo_programado is not None:
        return
    ficha.plazo_programado = date.fromisoformat(plazo)
    ficha.plazo_puesto_en = _ahora()
    _anotar(db, actor, persona, "plazo de programado",
            despues=ficha.plazo_programado.isoformat(),
            detalle=f"segundo servicio: {servicio.folio}")
    db.flush()
    try:
        avisar_plazo(db, persona, ficha, servicio)
    except Exception:                                   # noqa: BLE001
        registro.exception("no salio el aviso del plazo de %s", persona.id)


def fichas_para_asignar(db: Session, personas: list, servicio: m.Servicio,
                        modalidades: set[str],
                        ahora: datetime | None = None) -> dict[int, dict]:
    """Lo que la lista de a quien asignar necesita de cada freelance."""
    personas = [p for p in personas if p.es_freelance]
    if not personas:
        return {}
    fichas = {f.persona_id: f for f in db.query(m.Freelance).filter(
        m.Freelance.persona_id.in_([p.id for p in personas])).all()}
    for p in personas:
        if p.id not in fichas:
            fichas[p.id] = ficha_de(db, p.id)[1]
    resumenes = resumen_por_persona(db, personas, fichas, ahora)
    costos = costos_por_persona(db, [p.id for p in personas])
    salida = {}
    for p in personas:
        info = resumenes.get(p.id)
        r = para_asignar(db, p, servicio, modalidades, ahora, info, fichas[p.id])
        c = costos.get(p.id, {})
        salida[p.id] = {
            "servicio_id": servicio.id,
            "tipo": fichas[p.id].tipo,
            "asignable": r["asignable"],
            "motivo": r["motivo"],
            "mensaje": r.get("mensaje"),
            "puede_pedir": r.get("puede_pedir", False),
            "autorizacion": r.get("autorizacion"),
            "estado": info["estado"] if info else None,
            "faltan": (info or {}).get("faltan", [])[:4],
            "por_revisar": (info or {}).get("por_revisar", 0),
            "vencidos": (info or {}).get("vencidos", []),
            "plazo": (info or {}).get("plazo_programado") or r.get("plazo_nuevo"),
            "plazo_nuevo": r.get("plazo_nuevo"),
            "costos": {k: c.get(k) for k in (*MODALIDADES, "hora_extra")},
            "moneda": c.get("moneda"),
        }
    return salida


GRUPOS = ("disponibles", "con_alerta", "no_disponibles", "de_otras_ciudades")


def enriquecer(db: Session, bloque: dict, servicio: m.Servicio,
               modalidades: set[str], ahora: datetime | None = None) -> dict:
    """La lista de a quien asignar, con lo del freelance en cada ficha.

    En un implantado el freelance no se ofrece (decision 10): se quita de
    la lista. En un eventual se queda con su estado --listo, lo que le
    falta, su plazo o la urgencia-- para que la pantalla lo diga antes
    del clic, y no despues con un rechazo.
    """
    ids = {f["persona_id"] for g in GRUPOS for f in bloque.get(g) or []
           if f.get("es_freelance")}
    if not ids:
        return bloque
    if servicio.tipo == m.TipoServicio.IMPLANTADO:
        for g in GRUPOS:
            if bloque.get(g):
                bloque[g] = [f for f in bloque[g] if not f.get("es_freelance")]
        return bloque
    personas = db.query(m.Persona).filter(m.Persona.id.in_(ids)).all()
    datos = fichas_para_asignar(db, personas, servicio, modalidades, ahora)
    for g in GRUPOS:
        for f in bloque.get(g) or []:
            if f["persona_id"] in datos:
                f["freelance"] = datos[f["persona_id"]]
                f["foto"] = next((p.foto_url for p in personas
                                  if p.id == f["persona_id"]), None)
    return bloque


# ============================================================ la urgencia

def pedir_urgencia(db: Session, actor: m.Usuario, persona: m.Persona,
                   servicio: m.Servicio, motivo: str) -> m.AutorizacionFreelance:
    """Quien asigna la pide; si la pide direccion de operaciones, queda
    autorizada de una vez: es quien la da."""
    motivo = _limpio(motivo)
    if len(motivo) < 10:
        raise HTTPException(400, "Di por qué es urgente: queda escrito y es lo "
                                 "que lee dirección de operaciones.")
    if servicio.tipo == m.TipoServicio.IMPLANTADO:
        raise HTTPException(409, NO_EN_IMPLANTADO)
    if servicio.estatus in YA_NO_SE_ARMA:
        raise HTTPException(409, "Ese servicio ya no se arma.")
    _, ficha = ficha_de(db, persona.id)
    info = expediente(db, persona, ficha)
    faltaba = _razon(info) or info["estado"]
    fila = autorizacion_de(db, persona.id, servicio.id)
    if fila is not None and fila.estado == "autorizada":
        return fila
    if fila is None:
        fila = m.AutorizacionFreelance(persona_id=persona.id,
                                       servicio_id=servicio.id, motivo=motivo)
        db.add(fila)
    fila.estado = "pedida"
    fila.motivo = motivo[:400]
    fila.faltaba = faltaba[:400]
    fila.pedida_por_id = actor.persona_id
    fila.pedida_en = _ahora()
    fila.resuelta_por_id = fila.resuelta_en = fila.respuesta = None
    db.flush()
    _anotar(db, actor, persona, "urgencia pedida", despues=servicio.folio,
            detalle=motivo[:400])
    if auth.puede_el_usuario(db, actor, "freelance.autorizar"):
        resolver_urgencia(db, actor, fila, True, motivo)
    else:
        try:
            avisar_urgencia(db, fila, persona, servicio)
        except Exception:                               # noqa: BLE001
            registro.exception("no salio el aviso de la urgencia %s", fila.id)
    return fila


def resolver_urgencia(db: Session, actor: m.Usuario,
                      fila: m.AutorizacionFreelance, autorizar: bool,
                      respuesta: str | None) -> None:
    respuesta = _limpio(respuesta)
    if not autorizar and len(respuesta) < 5:
        raise HTTPException(400, "Di por qué no se autoriza: lo lee quien la "
                                 "pidió.")
    if fila.estado != "pedida":
        raise HTTPException(409, "Esa urgencia ya se resolvió.")
    persona = db.get(m.Persona, fila.persona_id)
    servicio = db.get(m.Servicio, fila.servicio_id)
    fila.estado = "autorizada" if autorizar else "rechazada"
    fila.resuelta_por_id = actor.persona_id
    fila.resuelta_en = _ahora()
    fila.respuesta = respuesta[:400] or None
    _anotar(db, actor, persona,
            "urgencia autorizada" if autorizar else "urgencia rechazada",
            despues=servicio.folio if servicio else None,
            detalle=(respuesta or fila.motivo)[:400])
    db.flush()


def urgencias(db: Session, estado: str | None = "pedida") -> list[dict]:
    q = db.query(m.AutorizacionFreelance)
    if estado:
        q = q.filter_by(estado=estado)
    salida = []
    for a in q.order_by(m.AutorizacionFreelance.pedida_en).all():
        persona = db.get(m.Persona, a.persona_id)
        servicio = db.get(m.Servicio, a.servicio_id)
        pidio = db.get(m.Persona, a.pedida_por_id) if a.pedida_por_id else None
        resolvio = (db.get(m.Persona, a.resuelta_por_id)
                    if a.resuelta_por_id else None)
        salida.append({
            "id": a.id, "estado": a.estado, "motivo": a.motivo,
            "faltaba": a.faltaba, "respuesta": a.respuesta,
            "persona_id": a.persona_id,
            "persona": persona.nombre if persona else None,
            "servicio_id": a.servicio_id,
            "folio": servicio.folio if servicio else None,
            "cliente": (servicio.cliente.nombre
                        if servicio and servicio.cliente else None),
            "ruta": f"#/servicio/{a.servicio_id}",
            "pidio": pidio.nombre if pidio else None,
            "pedida_en": a.pedida_en.isoformat() if a.pedida_en else None,
            "resolvio": resolvio.nombre if resolvio else None,
            "resuelta_en": a.resuelta_en.isoformat() if a.resuelta_en else None,
        })
    return salida


# =============================================================== el acceso

def dar_acceso(db: Session, actor: m.Usuario, persona: m.Persona,
               ficha: m.Freelance) -> m.Usuario:
    """Su acceso a EP Connect, con su correo, como el del personal de
    planta: la central le dicta su codigo y el pone su contrasena.

    Se abre con el expediente listo, o con una urgencia autorizada para
    un servicio que sigue vivo.
    """
    if not persona.activo:
        raise HTTPException(409, f"{persona.nombre} está dado de baja.")
    if db.query(m.Usuario).filter_by(persona_id=persona.id).first():
        raise HTTPException(409, f"{persona.nombre} ya tiene acceso a la app.")
    info = expediente(db, persona, ficha)
    urgencia = (db.query(m.AutorizacionFreelance)
                .join(m.Servicio,
                      m.Servicio.id == m.AutorizacionFreelance.servicio_id)
                .filter(m.AutorizacionFreelance.persona_id == persona.id,
                        m.AutorizacionFreelance.estado == "autorizada",
                        m.Servicio.estatus.notin_(YA_NO_SE_ARMA))
                .first())
    if not info["asignable"] and urgencia is None:
        raise HTTPException(409, {
            "mensaje": f"El acceso se abre cuando su expediente está listo: "
                       f"{_razon(info)}.",
            "que_hacer": "Si hay un servicio urgente, dirección de operaciones "
                         "lo autoriza y entonces se le puede dar."})
    llave = (persona.correo or "").strip().lower()
    otro = (db.query(m.Usuario)
            .filter(func.lower(func.trim(m.Usuario.correo)) == llave).first())
    if otro is not None:
        raise HTTPException(409, "Su correo ya es el acceso de otra persona: "
                                 "corrígelo en su ficha.")
    usuario = m.Usuario(persona_id=persona.id, correo=persona.correo,
                        rol=m.Rol.PERSONAL_SEGURIDAD, activo=True)
    db.add(usuario)
    db.flush()
    accesos.anotar(db, actor, "acceso creado", "usuario", usuario.id,
                   despues=usuario.rol.value, detalle=usuario.correo)
    _anotar(db, actor, persona, "acceso a la app", detalle=persona.correo)
    return usuario


# =============================================================== los avisos

def _quienes(db: Session, actividad: str) -> list[m.Usuario]:
    """A quien le toca: quien trae esa actividad por su puesto o su rol.
    Sin administracion ni direccion general, que la traen por herencia y
    no llevan el expediente de nadie."""
    salida = []
    for u in (db.query(m.Usuario).filter(m.Usuario.activo.is_(True))
              .order_by(m.Usuario.id).all()):
        if u.rol in (m.Rol.ADMIN, m.Rol.DIRECTOR_GENERAL):
            continue
        if u.persona is None or not u.persona.activo:
            continue
        if auth.puede_el_usuario(db, u, actividad):
            salida.append(u)
    return salida


def _avisar(db: Session, usuarios: list, asunto: str, cuerpo: str,
            pares: list, enlace: str, etiqueta: str,
            urgente: bool = False, **datos) -> int:
    """Correo y telefono a cada uno, en el idioma de su pais."""
    from app import correo_html, push
    from app import textos_aviso as ta
    avisados = 0
    for u in usuarios:
        plaza = u.persona.plaza if u.persona else None
        lengua = plaza.pais.idioma if plaza and plaza.pais else "es"
        titulo = ta.t(lengua, asunto, **datos)
        texto = ta.t(lengua, cuerpo, **datos)
        if u.correo:
            db.add(m.Notificacion(
                destinatario=m.Destinatario.COLABORADOR,
                canal=m.Canal.CORREO, correo=u.correo, idioma=lengua,
                asunto=titulo[:200], cuerpo=texto[:2000],
                datos=correo_html.guardar_datos(
                    [(ta.t(lengua, k), v) for k, v in pares]),
                enlace_seguimiento=enlace))
        try:
            push.avisar(db, u.persona_id, titulo, texto, url=enlace,
                        etiqueta=etiqueta, urgente=urgente)
        except Exception:                               # noqa: BLE001
            pass
        avisados += 1
    return avisados


def _de_rrhh(db: Session) -> list[m.Usuario]:
    """Recursos Humanos; si todavia no hay nadie, direccion de
    operaciones, para que el aviso no caiga en el vacio."""
    return _quienes(db, "freelance.validar") or _quienes(db, "freelance.autorizar")


def avisar_plazo(db: Session, persona: m.Persona, ficha: m.Freelance,
                 servicio: m.Servicio) -> int:
    return _avisar(
        db, _de_rrhh(db), "fre_plazo_asunto", "fre_plazo_cuerpo",
        [("fre_quien", persona.nombre), ("fre_servicio", servicio.folio),
         ("fre_hasta", f"{ficha.plazo_programado:%d/%m/%Y}")],
        f"/consola/#/freelance/{persona.id}", f"freelance-plazo-{persona.id}",
        quien=persona.nombre, folio=servicio.folio,
        fecha=f"{ficha.plazo_programado:%d/%m/%Y}")


def avisar_urgencia(db: Session, fila: m.AutorizacionFreelance,
                    persona: m.Persona, servicio: m.Servicio) -> int:
    return _avisar(
        db, _quienes(db, "freelance.autorizar"), "fre_urgencia_asunto",
        "fre_urgencia_cuerpo",
        [("fre_quien", persona.nombre), ("fre_servicio", servicio.folio),
         ("fre_motivo", fila.motivo), ("fre_faltaba", fila.faltaba or "-")],
        "/consola/#/direccion", f"freelance-urgencia-{fila.id}", urgente=True,
        quien=persona.nombre, folio=servicio.folio)


def revisar_vencimientos(db: Session, ahora: datetime | None = None,
                         hoy: date | None = None) -> dict:
    """La tarea de cada manana: lo que vence en treinta dias, lo que vence
    hoy y el plazo del de emergencia que se cumplio. Dos avisos por
    documento, como los certificados, y uno por plazo.

    `hoy` es para las pruebas: el mismo dia para todos los paises."""
    rrhh = _de_rrhh(db)
    relojes = reloj.Relojes(db, ahora)

    def dia(persona):
        return hoy or relojes.hoy(persona.plaza.pais_id if persona.plaza
                                  else None)
    avisados = []
    filas = (db.query(m.DocumentoFreelance, m.Persona)
             .join(m.Persona, m.Persona.id == m.DocumentoFreelance.persona_id)
             .filter(m.DocumentoFreelance.estado == VALIDADO,
                     m.DocumentoFreelance.reemplazado_en.is_(None),
                     m.DocumentoFreelance.vence_en.isnot(None),
                     m.Persona.activo.is_(True),
                     m.Persona.es_freelance.is_(True)).all())
    for doc, persona in filas:
        el_dia = dia(persona)
        dias = (doc.vence_en - el_dia).days
        if dias > DIAS_DE_AVISO:
            continue
        if dias > 0:
            if doc.aviso_por_vencer_en is not None:
                continue
            doc.aviso_por_vencer_en = el_dia
            clave = "fre_vence_pronto"
        else:
            if doc.aviso_vencido_en is not None:
                continue
            doc.aviso_vencido_en = el_dia
            if doc.aviso_por_vencer_en is None:
                doc.aviso_por_vencer_en = el_dia
            clave = "fre_vence_hoy" if dias == 0 else "fre_vencio"
        requisito = doc.requisito
        _avisar(db, rrhh, clave, "fre_vence_cuerpo",
                [("fre_quien", persona.nombre),
                 ("fre_documento", requisito.nombre),
                 ("fre_vence", f"{doc.vence_en:%d/%m/%Y}")],
                f"/consola/#/freelance/{persona.id}",
                f"freelance-vence-{doc.id}", quien=persona.nombre,
                documento=requisito.nombre, dias=dias,
                fecha=f"{doc.vence_en:%d/%m/%Y}")
        avisados.append({"persona": persona.nombre,
                         "documento": requisito.nombre, "dias": dias})

    plazos = []
    for ficha in (db.query(m.Freelance)
                  .filter(m.Freelance.tipo == EMERGENCIA,
                          m.Freelance.plazo_programado.isnot(None),
                          m.Freelance.plazo_avisado_en.is_(None)).all()):
        persona = db.get(m.Persona, ficha.persona_id)
        if not persona or not persona.activo:
            continue
        el_dia = dia(persona)
        # Vale hasta su ultimo dia: el aviso sale al dia siguiente, que es
        # cuando ya no se le asigna.
        if el_dia <= ficha.plazo_programado:
            continue
        ficha.plazo_avisado_en = el_dia
        _avisar(db, rrhh, "fre_plazo_vencio_asunto", "fre_plazo_vencio_cuerpo",
                [("fre_quien", persona.nombre),
                 ("fre_hasta", f"{ficha.plazo_programado:%d/%m/%Y}")],
                f"/consola/#/freelance/{persona.id}",
                f"freelance-plazo-{persona.id}", quien=persona.nombre,
                fecha=f"{ficha.plazo_programado:%d/%m/%Y}")
        plazos.append(persona.nombre)
    db.commit()
    return {"avisados": len(avisados), "detalle": avisados,
            "plazos": plazos}


# ======================================================== para la siembra

def sembrar_requisitos(db: Session) -> int:
    """Los requisitos de Mexico, si Mexico no tiene ninguno todavia. Lo
    que ya este no se toca: la lista la lleva sistema y calidad."""
    mx = db.query(m.Pais).filter_by(codigo="MX").first()
    if mx is None or db.query(m.RequisitoFreelance).filter_by(
            pais_id=mx.id).first():
        return 0
    for r in REQUISITOS_MEXICO:
        db.add(m.RequisitoFreelance(pais_id=mx.id, activo=True, **r))
    db.flush()
    return len(REQUISITOS_MEXICO)


def fichas_que_faltan(db: Session) -> int:
    """El freelance que existia antes de la seccion 111 --una marca en la
    persona-- recibe su ficha: programado, con el expediente por
    completar y sus tarifas como estaban."""
    tienen = {x for (x,) in db.query(m.Freelance.persona_id).all()}
    nuevos = 0
    for p in (db.query(m.Persona)
              .filter(m.Persona.es_freelance.is_(True)).all()):
        if p.id in tienen:
            continue
        nombre, apellidos = partir_nombre(p.nombre)
        db.add(m.Freelance(persona_id=p.id, tipo=PROGRAMADO, nombre=nombre,
                           apellidos=apellidos))
        nuevos += 1
    db.flush()
    return nuevos

# -*- coding: utf-8 -*-
"""Logistica, bloque 2 (seccion 151): la flota.

Cada unidad de la compania «Centauro Logistic» de Odoo con lo que vive en
Connect: su numero economico, su tipo, su rendimiento de referencia, su
odometro, su estado, su patio, su expediente, su plan preventivo, sus
servicios, sus llantas y lo que cuesta tenerla un dia.

Decisiones de Salvador, 3 de octubre:
  * Las unidades son las de la compania «Centauro Logistic SA CV» (solo
    una traia la etiqueta «Logistica»). Las dos cajas secas entran, con
    su expediente, su plan y su costo, pero no se asignan solas: van con
    su tracto. El Prius utilitario no entra.
  * Un documento vencido no deja salir a la unidad; uno sin capturar solo
    avisa. Lo mismo la licencia del operador.
  * El mantenimiento sale de los servicios registrados aqui, con su
    factura: en Odoo no hay facturas de taller de Logistic.

Lo que decide si una unidad puede salir vive en `lg_disponibilidad`, una
sola funcion para la pantalla de flota, la de jornada y el bloque 4.
"""
import base64
import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import accesos
from app import archivo as archivo_motor
from app import lg_catalogos
from app import models as m
from app.config import settings

registro = logging.getLogger("centauro.lg")

ESTADOS = ("disponible", "en_viaje", "en_taller", "fuera_de_servicio")
CON_MOTIVO = ("en_taller", "fuera_de_servicio")
CLASES = ("unidad", "remolque")
# El expediente de cada unidad, en el orden de la pantalla.
DOCUMENTOS = ("tarjeta_circulacion", "poliza_seguro", "permiso_sct",
              "verificacion", "gps")
LICENCIA = "licencia"
DIAS_AVISO = 30
KM_AVISO = 2000
DIAS_DEL_ANIO = Decimal(365)
CENTAVO = Decimal("0.01")
# Objetos de la bitacora de administracion.
OBJETOS = ("lg_unidades", "lg_plan", "lg_operadores", "lg_jornada",
           "lg_carga")

# Las posiciones de las llantas por cuantas lleva el tipo. «R» es la
# refaccion. La caja seca lleva dos ejes de cuatro y no trae refaccion.
POSICIONES = {
    4: ("DI", "DD", "TI", "TD", "R"),
    6: ("DI", "DD", "TIE", "TII", "TDI", "TDE", "R"),
    10: ("DI", "DD", "1IE", "1II", "1DI", "1DE", "2IE", "2II", "2DI", "2DE", "R"),
}
POSICIONES_REMOLQUE = ("1IE", "1II", "1DI", "1DE", "2IE", "2II", "2DI", "2DE")

_no = lg_catalogos._no
_numero = lg_catalogos._numero


def hoy() -> date:
    return lg_catalogos.hoy_lg()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _centavos(d: Decimal) -> Decimal:
    return d.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _d(valor) -> Decimal | None:
    return None if valor is None else Decimal(str(valor))


def _iso(valor) -> str | None:
    return valor.isoformat() if valor else None


def _texto(valor, largo: int) -> str | None:
    limpio = " ".join(str(valor or "").split())
    return limpio[:largo] or None


def _anotar(db: Session, actor: m.Usuario, accion: str, objeto: str,
            objeto_id: int | None, datos: dict) -> None:
    """La bitacora de administracion, con lo que paso en JSON corto:
    `que_cambio` lo cuenta en el idioma de quien lee."""
    accesos.anotar(db, actor, accion, objeto, objeto_id,
                   detalle=json.dumps(datos, ensure_ascii=False, default=str))


# ================================================================ la unidad

def llave_economico(texto) -> str | None:
    """El numero economico sin «Eco», espacios, guiones ni ceros a la
    izquierda: «Eco 01», «01» y «1» son el mismo, y no se repite."""
    limpio = re.sub(r"[\s\-_.]", "", str(texto or "")).upper()
    if limpio.startswith("ECO"):
        limpio = limpio[3:]
    if not limpio:
        return None
    if limpio.isdigit():
        limpio = str(int(limpio))
    return limpio[:20]


def posiciones(unidad: m.LgUnidad) -> tuple:
    if unidad.clase == "remolque":
        return POSICIONES_REMOLQUE
    cuantas = unidad.tipo.llantas if unidad.tipo else None
    return POSICIONES.get(cuantas or 0, ())


def unidad_o_404(db: Session, unidad_id: int) -> m.LgUnidad:
    unidad = db.get(m.LgUnidad, unidad_id)
    if not unidad:
        raise HTTPException(404, "No existe esa unidad")
    return unidad


def nombre_de(unidad: m.LgUnidad) -> str:
    return (f"Eco {unidad.numero_economico}" if unidad.numero_economico
            else unidad.placa)


def _economico_libre(db: Session, llave: str, salvo: int | None) -> None:
    otra = db.query(m.LgUnidad).filter(m.LgUnidad.economico_llave == llave)
    if salvo:
        otra = otra.filter(m.LgUnidad.id != salvo)
    otra = otra.first()
    if otra:
        raise _no({"mensaje": f"El número económico {llave} ya es de la unidad "
                              f"con placas {otra.placa}.",
                   "que_hacer": "Cada unidad lleva su propio número económico: "
                                "revisa cuál es el de cada una."}, 409)


CAMPOS_COSTO = ("valor_compra", "anios_vida", "seguro_anual", "tenencia_anual",
                "verificacion_anual", "gps_anual", "llantas_por_km",
                "mantenimiento_anual")
# Los topes de dedazo de cada costo.
TOPES = {"valor_compra": 20_000_000, "anios_vida": 40, "seguro_anual": 2_000_000,
         "tenencia_anual": 500_000, "verificacion_anual": 200_000,
         "gps_anual": 200_000, "llantas_por_km": 100,
         "mantenimiento_anual": 2_000_000}
NOMBRES_COSTO = {"valor_compra": "el valor de compra", "anios_vida": "los años de vida",
                 "seguro_anual": "el seguro anual",
                 "tenencia_anual": "la tenencia y placas al año",
                 "verificacion_anual": "la verificación al año",
                 "gps_anual": "el GPS al año",
                 "llantas_por_km": "lo que gastan sus llantas por km",
                 "mantenimiento_anual": "el mantenimiento de un año"}


def revisar_datos(db: Session, unidad: m.LgUnidad | None, datos: dict) -> dict:
    """Lo que se captura de una unidad, revisado. Solo vienen los campos
    que se cambian; un campo vacio lo deja sin dato."""
    limpio: dict = {}
    if "numero_economico" in datos:
        texto = _texto(datos["numero_economico"], 20)
        if texto:
            texto = re.sub(r"^(eco)\s*", "", texto, flags=re.I).strip() or texto
            llave = llave_economico(texto)
            _economico_libre(db, llave, unidad.id if unidad else None)
            limpio["numero_economico"], limpio["economico_llave"] = texto, llave
        else:
            limpio["numero_economico"] = limpio["economico_llave"] = None
    if "tipo_id" in datos:
        tipo_id = datos["tipo_id"]
        if tipo_id in (None, ""):
            limpio["tipo_id"] = None
        else:
            tipo = db.get(m.LgTipoUnidad, int(tipo_id))
            if not tipo or not tipo.activo:
                raise _no("Ese tipo de unidad no existe o está quitado.")
            limpio["tipo_id"] = tipo.id
    if "patio_id" in datos:
        patio_id = datos["patio_id"]
        if patio_id in (None, ""):
            limpio["patio_id"] = None
        else:
            patio = db.get(m.LgPatio, int(patio_id))
            if not patio or not patio.activo:
                raise _no("Ese patio no existe o está quitado.")
            limpio["patio_id"] = patio.id
    if "rendimiento_ref" in datos:
        valor = datos["rendimiento_ref"]
        limpio["rendimiento_ref"] = (None if valor in (None, "") else _numero(
            valor, "el rendimiento de referencia", mayor_que=0, maximo=30,
            decimales=2))
    for campo in CAMPOS_COSTO:
        if campo in datos:
            valor = datos[campo]
            limpio[campo] = (None if valor in (None, "") else _numero(
                valor, NOMBRES_COSTO[campo],
                mayor_que=0 if campo == "anios_vida" else None, minimo=0,
                maximo=TOPES[campo], decimales=4 if campo == "llantas_por_km" else 2))
    if "clase" in datos:
        if datos["clase"] not in CLASES:
            raise _no("La clase es «unidad» o «remolque».")
        limpio["clase"] = datos["clase"]
    return limpio


def editar(db: Session, actor: m.Usuario, unidad: m.LgUnidad, datos: dict) -> m.LgUnidad:
    limpio = revisar_datos(db, unidad, datos)
    cambios = {}
    for campo, nuevo in limpio.items():
        if campo == "economico_llave":
            continue
        viejo = getattr(unidad, campo)
        if (str(viejo) if viejo is not None else None) != (
                str(nuevo) if nuevo is not None else None):
            cambios[campo] = [None if viejo is None else str(viejo),
                              None if nuevo is None else str(nuevo)]
        setattr(unidad, campo, nuevo)
    if "economico_llave" in limpio:
        unidad.economico_llave = limpio["economico_llave"]
    if cambios:
        _anotar(db, actor, "lg unidad cambiada", "lg_unidades", unidad.id,
                {"k": "datos", "u": nombre_de(unidad), "c": cambios})
    db.flush()
    return unidad


# ================================================================ el estado

def cambiar_estado(db: Session, actor: m.Usuario, unidad: m.LgUnidad, estado: str,
                   motivo: str | None = None, hasta: date | None = None) -> m.LgUnidad:
    """Libre, en viaje, en taller o fuera de servicio. Taller y fuera de
    servicio piden motivo y quedan en la bitacora. «En viaje» se marca a
    mano mientras los viajes sigan en Tango; desde el bloque 4 lo pone el
    viaje."""
    if estado not in ESTADOS:
        raise _no("Ese estado no existe.")
    motivo = _texto(motivo, 300)
    if estado in CON_MOTIVO and (not motivo or len(motivo) < 5):
        raise _no({"mensaje": "Falta el motivo: en taller y fuera de servicio "
                              "quedan en la bitácora con su porqué.",
                   "que_hacer": "Escribe qué tiene la unidad, por ejemplo "
                                "«frenos: cambio de balatas»."})
    if hasta is not None and hasta < hoy():
        raise _no("La fecha de regreso ya pasó.")
    antes = unidad.estado
    unidad.estado = estado
    unidad.estado_motivo = motivo if estado != "disponible" else None
    unidad.estado_hasta = hasta if estado != "disponible" else None
    unidad.estado_desde = _ahora()
    _anotar(db, actor, "lg unidad estado", "lg_unidades", unidad.id,
            {"k": "estado", "u": nombre_de(unidad), "de": antes, "a": estado,
             "m": motivo, "h": hasta})
    db.flush()
    return unidad


# ================================================================ el odometro

def capturar_odometro(db: Session, actor: m.Usuario | None, unidad: m.LgUnidad,
                      km, fecha: date | None = None, motivo: str | None = None,
                      fuente: str = "manual") -> m.LgLecturaOdometro:
    """Una lectura. Menor que la anterior pide el porque: o se capturo mal
    aquella, o esta."""
    km = int(_numero(km, "el odómetro", minimo=0, maximo=5_000_000, entero=True))
    fecha = fecha or hoy()
    if fecha > hoy():
        raise _no("La fecha de la lectura todavía no llega.")
    if fecha < date(2000, 1, 1):
        raise _no("Revisa la fecha de la lectura.")
    motivo = _texto(motivo, 300)
    anterior = (db.query(m.LgLecturaOdometro)
                .filter(m.LgLecturaOdometro.unidad_id == unidad.id,
                        m.LgLecturaOdometro.fecha <= fecha)
                .order_by(m.LgLecturaOdometro.fecha.desc(),
                          m.LgLecturaOdometro.id.desc()).first())
    if anterior and km < anterior.km and not motivo:
        raise _no({"mensaje": f"Es menos que la lectura anterior ({anterior.km:,} km "
                              f"del {anterior.fecha.strftime('%d/%m/%Y')}).",
                   "que_hacer": "Escribe por qué, o corrige el número."})
    lectura = m.LgLecturaOdometro(
        unidad_id=unidad.id, km=km, fecha=fecha, fuente=fuente, motivo=motivo,
        registrado_por_id=actor.persona_id if actor else None,
        registrado_en=_ahora())
    db.add(lectura)
    if unidad.odometro_fecha is None or fecha >= unidad.odometro_fecha:
        unidad.odometro_km, unidad.odometro_fecha = km, fecha
    if actor and fuente == "manual":
        _anotar(db, actor, "lg odometro", "lg_unidades", unidad.id,
                {"k": "odometro", "u": nombre_de(unidad), "km": km, "f": fecha,
                 "m": motivo})
    db.flush()
    return lectura


def km_por_dia(db: Session, unidad_id: int, fecha: date) -> Decimal | None:
    """Lo que la unidad recorre al dia, con sus lecturas del ultimo ano.
    Hace falta que cubran al menos un mes."""
    desde = fecha - timedelta(days=365)
    lecturas = (db.query(m.LgLecturaOdometro)
                .filter(m.LgLecturaOdometro.unidad_id == unidad_id,
                        m.LgLecturaOdometro.fecha > desde,
                        m.LgLecturaOdometro.fecha <= fecha)
                .order_by(m.LgLecturaOdometro.fecha, m.LgLecturaOdometro.id).all())
    if len(lecturas) < 2:
        return None
    dias = (lecturas[-1].fecha - lecturas[0].fecha).days
    recorrido = lecturas[-1].km - lecturas[0].km
    if dias < 30 or recorrido <= 0:
        return None
    return Decimal(recorrido) / Decimal(dias)


# ================================================================ los archivos

TIPOS_DE_ARCHIVO = {"application/pdf": ".pdf", "image/jpeg": ".jpg",
                    "image/png": ".png", "image/webp": ".webp",
                    "image/heic": ".heic"}


def _destino() -> str:
    return (settings.expedientes_destino or "").strip()


def guardar_archivo(db: Session, actor: m.Usuario, nombre: str, tipo: str | None,
                    contenido: bytes, google=None) -> m.LgArchivo:
    """PDF o foto, hasta 10 MB, como el expediente del freelance."""
    from app import freelance
    nombre, tipo = freelance.revisar_archivo(nombre, tipo, contenido)
    fila = m.LgArchivo(nombre=nombre, tipo=tipo, tamano=len(contenido),
                       md5=hashlib.md5(contenido).hexdigest(), contenido=contenido,
                       subido_por_id=actor.persona_id, subido_en=_ahora())
    db.add(fila)
    db.flush()
    if _destino():
        try:
            mudar(db, fila, google)
        except archivo_motor.Fallo as error:
            registro.warning("el archivo lg %s se queda en la base: %s", fila.id, error)
    return fila


def mudar(db: Session, fila: m.LgArchivo, google=None) -> None:
    if fila.objeto or fila.contenido is None:
        return
    google = google or archivo_motor.Google(_destino())
    ruta = google.ruta(f"logistica/{fila.id}-{fila.md5[:8]}"
                       f"{TIPOS_DE_ARCHIVO.get(fila.tipo, '')}")
    try:
        google.subir(ruta, fila.contenido, fila.tipo, {"logistica": str(fila.id)})
    except archivo_motor.YaExiste:
        pass
    dicho = google.describir(ruta) or {}
    huella = (base64.b64decode(dicho.get("md5Hash", "")).hex()
              if dicho.get("md5Hash") else "")
    if huella != fila.md5 or int(dicho.get("size") or -1) != fila.tamano:
        raise archivo_motor.Fallo(f"Google no tiene completo el archivo lg {fila.id}")
    fila.objeto = f"gs://{google.deposito}/{ruta}"
    fila.contenido = None
    db.flush()


def mudar_pendientes(db: Session, limite: int = 200, google=None) -> dict:
    if not _destino():
        return {"mudados": 0, "omitido": "sin EXPEDIENTES_DESTINO"}
    filas = (db.query(m.LgArchivo)
             .filter(m.LgArchivo.objeto.is_(None), m.LgArchivo.contenido.isnot(None))
             .order_by(m.LgArchivo.id).limit(limite).all())
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
            registro.error("no se pudo mudar el archivo lg %s: %s", fila.id, error)
            if fallas >= archivo_motor.SEGUIDAS:
                break
    return {"mudados": mudados, "fallas": fallas}


def leer_archivo(fila: m.LgArchivo, google=None) -> bytes:
    if fila.contenido is not None:
        return fila.contenido
    if not fila.objeto:
        raise HTTPException(404, "Ese archivo no tiene contenido.")
    try:
        deposito, ruta = archivo_motor.partir(fila.objeto)
        google = google or archivo_motor.Google(f"gs://{deposito}")
        datos, _ = google.bajar(ruta)
    except archivo_motor.Fallo as error:
        raise HTTPException(502, f"El depósito de Google no entregó el archivo: {error}")
    return datos


# ================================================================ el expediente

def estado_documento(doc: m.LgDocumento | None, fecha: date) -> dict:
    """falta, vigente, por_vencer (a 30 dias) o vencido."""
    if doc is None:
        return {"estado": "falta"}
    if doc.vence_en is None:
        return {"estado": "vigente", "vence_en": None}
    dias = (doc.vence_en - fecha).days
    if dias < 0:
        return {"estado": "vencido", "vence_en": doc.vence_en.isoformat(), "dias": dias}
    if dias <= DIAS_AVISO:
        return {"estado": "por_vencer", "vence_en": doc.vence_en.isoformat(),
                "dias": dias}
    return {"estado": "vigente", "vence_en": doc.vence_en.isoformat(), "dias": dias}


def vigentes(db: Session, unidad_ids=None, operador_ids=None) -> dict:
    """Los documentos que estan en pie (no reemplazados), por
    (`u` o `o`, id) y tipo."""
    consulta = db.query(m.LgDocumento).filter(m.LgDocumento.reemplazado_en.is_(None))
    if unidad_ids is not None:
        consulta = consulta.filter(m.LgDocumento.unidad_id.in_(list(unidad_ids) or [0]))
    if operador_ids is not None:
        consulta = consulta.filter(m.LgDocumento.operador_id.in_(list(operador_ids) or [0]))
    salida: dict = {}
    for doc in consulta.order_by(m.LgDocumento.id).all():
        llave = ("u", doc.unidad_id) if doc.unidad_id else ("o", doc.operador_id)
        salida.setdefault(llave, {})[doc.tipo] = doc
    return salida


def capturar_documento(db: Session, actor: m.Usuario, tipo: str,
                       unidad: m.LgUnidad | None = None,
                       operador: m.LgOperador | None = None,
                       folio: str | None = None, detalle: str | None = None,
                       vence_en: date | None = None,
                       archivo: m.LgArchivo | None = None) -> m.LgDocumento:
    """Uno nuevo reemplaza al que estaba: el de antes se queda, marcado."""
    if unidad is not None and tipo not in DOCUMENTOS:
        raise _no("Ese documento no es del expediente de la unidad.")
    if operador is not None and tipo != LICENCIA:
        raise _no("Del operador se lleva su licencia federal.")
    if vence_en is not None and vence_en < date(2000, 1, 1):
        raise _no("Revisa la fecha de vencimiento.")
    if vence_en is not None and vence_en > hoy() + timedelta(days=365 * 15):
        raise _no("Revisa la fecha de vencimiento: pasa de 15 años.")
    consulta = db.query(m.LgDocumento).filter(m.LgDocumento.tipo == tipo,
                                              m.LgDocumento.reemplazado_en.is_(None))
    consulta = (consulta.filter(m.LgDocumento.unidad_id == unidad.id) if unidad
                else consulta.filter(m.LgDocumento.operador_id == operador.id))
    ahora = _ahora()
    for viejo in consulta.all():
        viejo.reemplazado_en = ahora
    doc = m.LgDocumento(
        unidad_id=unidad.id if unidad else None,
        operador_id=operador.id if operador else None, tipo=tipo,
        folio=_texto(folio, 80), detalle=_texto(detalle, 120), vence_en=vence_en,
        archivo_id=archivo.id if archivo else None,
        capturado_por_id=actor.persona_id, capturado_en=ahora)
    db.add(doc)
    if unidad is not None:
        _anotar(db, actor, "lg documento", "lg_unidades", unidad.id,
                {"k": "documento", "u": nombre_de(unidad), "t": tipo, "v": vence_en})
    else:
        _anotar(db, actor, "lg licencia", "lg_operadores", operador.id,
                {"k": "licencia", "o": operador.nombre, "v": vence_en,
                 "d": doc.detalle})
    db.flush()
    return doc


# ================================================================ el plan preventivo

def plan_de(db: Session, unidad: m.LgUnidad) -> list[m.LgPlanServicio]:
    consulta = db.query(m.LgPlanServicio).filter(m.LgPlanServicio.activo.is_(True))
    if unidad.clase == "remolque":
        consulta = consulta.filter(m.LgPlanServicio.clase == "remolque")
    elif unidad.tipo_id:
        consulta = consulta.filter(m.LgPlanServicio.tipo_id == unidad.tipo_id)
    else:
        return []
    return consulta.order_by(m.LgPlanServicio.orden, m.LgPlanServicio.id).all()


def ultimos_servicios(db: Session, unidad_ids) -> dict:
    """{(unidad_id, plan_id): (km, fecha)} del ultimo servicio de cada
    renglon del plan, sin los anulados."""
    salida: dict = {}
    filas = (db.query(m.LgServicio)
             .filter(m.LgServicio.unidad_id.in_(list(unidad_ids) or [0]),
                     m.LgServicio.plan_id.isnot(None),
                     m.LgServicio.anulado_en.is_(None))
             .order_by(m.LgServicio.fecha, m.LgServicio.id).all())
    for s in filas:
        llave = (s.unidad_id, s.plan_id)
        anterior = salida.get(llave)
        if s.km is not None and (anterior is None or (anterior[0] or 0) <= s.km):
            salida[llave] = (s.km, s.fecha)
        elif anterior is None:
            salida[llave] = (s.km, s.fecha)
    return salida


def proximos(plan: list, ultimos: dict, unidad: m.LgUnidad) -> list[dict]:
    """A que km le toca cada servicio del plan, con su ultimo. Sin ultimo
    registrado no se adivina: se pide."""
    salida = []
    for p in plan:
        km_ultimo, fecha_ultimo = ultimos.get((unidad.id, p.id), (None, None))
        renglon = {"plan_id": p.id, "nombre": p.nombre, "cada_km": p.cada_km,
                   "costo_aprox": str(p.costo_aprox) if p.costo_aprox is not None else None,
                   "ultimo_km": km_ultimo, "ultimo_fecha": _iso(fecha_ultimo)}
        if km_ultimo is None:
            renglon.update({"toca_km": None, "faltan_km": None, "estado": "sin_ultimo"})
        else:
            toca = km_ultimo + p.cada_km
            faltan = toca - unidad.odometro_km if unidad.odometro_km is not None else None
            estado = ("sin_odometro" if faltan is None else "vencido" if faltan <= 0
                      else "proximo" if faltan < KM_AVISO else "ok")
            renglon.update({"toca_km": toca, "faltan_km": faltan, "estado": estado})
        salida.append(renglon)
    return salida


def el_mas_cercano(lista: list[dict]) -> dict | None:
    con_km = [x for x in lista if x.get("faltan_km") is not None]
    return min(con_km, key=lambda x: x["faltan_km"]) if con_km else None


def _revisar_plan(datos: dict) -> dict:
    nombre = _texto(datos.get("nombre"), 80)
    if not nombre:
        raise _no("Falta el nombre del servicio.")
    cada = int(_numero(datos.get("cada_km"), "cada cuántos km", mayor_que=0,
                       maximo=1_000_000, entero=True))
    costo = datos.get("costo_aprox")
    costo = None if costo in (None, "") else _numero(costo, "el costo aproximado",
                                                     minimo=0, maximo=5_000_000,
                                                     decimales=2)
    return {"nombre": nombre, "cada_km": cada, "costo_aprox": costo,
            "orden": int(datos.get("orden") or 0)}


def alta_plan(db: Session, actor: m.Usuario, datos: dict) -> m.LgPlanServicio:
    clase = datos.get("clase") or "unidad"
    if clase not in CLASES:
        raise _no("La clase es «unidad» o «remolque».")
    tipo_id = datos.get("tipo_id")
    if clase == "unidad":
        tipo = db.get(m.LgTipoUnidad, int(tipo_id)) if tipo_id else None
        if not tipo:
            raise _no("Falta el tipo de unidad del servicio.")
        tipo_id = tipo.id
    else:
        tipo_id = None
    limpio = _revisar_plan(datos)
    fila = m.LgPlanServicio(tipo_id=tipo_id, clase=clase, **limpio)
    db.add(fila)
    db.flush()
    _anotar(db, actor, "lg plan alta", "lg_plan", fila.id,
            {"k": "plan", "n": fila.nombre, "c": fila.cada_km,
             "t": tipo_id, "r": clase == "remolque"})
    return fila


def cambiar_plan(db: Session, actor: m.Usuario, plan_id: int, datos: dict) -> m.LgPlanServicio:
    fila = db.get(m.LgPlanServicio, plan_id)
    if not fila:
        raise HTTPException(404, "No existe ese servicio del plan")
    limpio = _revisar_plan({**{"nombre": fila.nombre, "cada_km": fila.cada_km,
                               "costo_aprox": fila.costo_aprox, "orden": fila.orden},
                            **datos})
    antes = {"n": fila.nombre, "c": fila.cada_km, "p": str(fila.costo_aprox)}
    for campo, valor in limpio.items():
        setattr(fila, campo, valor)
    if "activo" in datos:
        fila.activo = bool(datos["activo"])
    _anotar(db, actor, "lg plan cambio", "lg_plan", fila.id,
            {"k": "plan_cambio", "n": fila.nombre, "antes": antes,
             "c": fila.cada_km, "p": str(fila.costo_aprox), "a": fila.activo})
    db.flush()
    return fila


# ================================================================ los servicios

def registrar_servicio(db: Session, actor: m.Usuario, unidad: m.LgUnidad,
                       datos: dict, archivo: m.LgArchivo | None = None) -> m.LgServicio:
    plan = None
    if datos.get("plan_id"):
        plan = db.get(m.LgPlanServicio, int(datos["plan_id"]))
        if not plan or plan not in plan_de(db, unidad):
            raise _no("Ese servicio no es del plan de esta unidad.")
    nombre = plan.nombre if plan else _texto(datos.get("nombre"), 120)
    if not nombre:
        raise _no("Falta qué servicio se hizo.")
    fecha = datos.get("fecha")
    fecha = date.fromisoformat(fecha) if isinstance(fecha, str) else fecha
    if not fecha:
        raise _no("Falta la fecha del servicio.")
    if fecha > hoy():
        raise _no("La fecha del servicio todavía no llega.")
    km = datos.get("km")
    km = None if km in (None, "") else int(_numero(km, "el odómetro del servicio",
                                                   minimo=0, maximo=5_000_000,
                                                   entero=True))
    if plan and km is None:
        raise _no({"mensaje": "Falta el odómetro: con él se calcula cuándo toca "
                              "el siguiente.",
                   "que_hacer": "Escribe el kilometraje que traía la unidad ese día."})
    costo = _numero(datos.get("costo"), "el costo", minimo=0, maximo=5_000_000,
                    decimales=2)
    servicio = m.LgServicio(
        unidad_id=unidad.id, plan_id=plan.id if plan else None, nombre=nombre,
        fecha=fecha, km=km, costo=costo, taller=_texto(datos.get("taller"), 120),
        factura=_texto(datos.get("factura"), 60),
        archivo_id=archivo.id if archivo else None,
        registrado_por_id=actor.persona_id, registrado_en=_ahora())
    db.add(servicio)
    db.flush()
    if km is not None and (unidad.odometro_km is None or km > unidad.odometro_km):
        capturar_odometro(db, None, unidad, km, fecha, fuente="servicio")
    _anotar(db, actor, "lg servicio", "lg_unidades", unidad.id,
            {"k": "servicio", "u": nombre_de(unidad), "n": nombre, "f": fecha,
             "km": km, "p": str(costo)})
    return servicio


def anular_servicio(db: Session, actor: m.Usuario, servicio_id: int,
                    motivo: str) -> m.LgServicio:
    servicio = db.get(m.LgServicio, servicio_id)
    if not servicio or servicio.anulado_en:
        raise HTTPException(404, "No existe ese servicio o ya se anuló")
    motivo = _texto(motivo, 300)
    if not motivo or len(motivo) < 5:
        raise _no("Falta el motivo para anularlo.")
    servicio.anulado_en, servicio.anulado_motivo = _ahora(), motivo
    unidad = db.get(m.LgUnidad, servicio.unidad_id)
    _anotar(db, actor, "lg servicio anulado", "lg_unidades", servicio.unidad_id,
            {"k": "servicio_anulado", "u": nombre_de(unidad), "n": servicio.nombre,
             "f": servicio.fecha, "m": motivo})
    db.flush()
    return servicio


# ================================================================ las llantas

def llantas_actuales(db: Session, unidad: m.LgUnidad) -> dict:
    filas = (db.query(m.LgLlanta)
             .filter(m.LgLlanta.unidad_id == unidad.id, m.LgLlanta.retirada_en.is_(None))
             .order_by(m.LgLlanta.id).all())
    return {f.posicion: f for f in filas}


def cambiar_llanta(db: Session, actor: m.Usuario, unidad: m.LgUnidad, posicion: str,
                   km, fecha: date | None = None, detalle: str | None = None,
                   costo=None) -> m.LgLlanta:
    if posicion not in posiciones(unidad):
        raise _no("Esa posición no es de esta unidad.")
    km = int(_numero(km, "el odómetro al instalarla", minimo=0, maximo=5_000_000,
                     entero=True))
    fecha = fecha or hoy()
    if fecha > hoy():
        raise _no("La fecha todavía no llega.")
    costo = None if costo in (None, "") else _numero(costo, "el costo de la llanta",
                                                     minimo=0, maximo=200_000,
                                                     decimales=2)
    actual = llantas_actuales(db, unidad).get(posicion)
    if actual:
        if km < actual.instalada_km:
            raise _no("El odómetro es menor que el de cuando se instaló la anterior.")
        actual.retirada_km, actual.retirada_en = km, fecha
    nueva = m.LgLlanta(unidad_id=unidad.id, posicion=posicion, instalada_km=km,
                       instalada_en=fecha, detalle=_texto(detalle, 120), costo=costo,
                       registrado_por_id=actor.persona_id, registrado_en=_ahora())
    db.add(nueva)
    _anotar(db, actor, "lg llanta", "lg_unidades", unidad.id,
            {"k": "llanta", "u": nombre_de(unidad), "pos": posicion, "km": km,
             "f": fecha})
    db.flush()
    return nueva


# ================================================================ el costo por dia

COMPONENTES = ("depreciacion", "seguro", "gps", "mantenimiento", "llantas")


def _por_dia(anual: Decimal) -> Decimal:
    return _centavos(anual / DIAS_DEL_ANIO)


def _del_tipo(db: Session, unidad: m.LgUnidad, fecha: date) -> dict | None:
    if not unidad.tipo_id:
        return None
    try:
        return lg_catalogos.costo_unidad(db, unidad.tipo_id, fecha)
    except lg_catalogos.FaltaValor:
        return None


def _mantenimiento(db: Session, unidad: m.LgUnidad, fecha: date) -> tuple:
    """(monto al dia, fuente, detalle). Con un ano de servicios registrados,
    de ellos; antes, del mantenimiento anual de la carga inicial; sin
    nada de la unidad, el promedio de su tipo; y si no, el de la 150."""
    desde = fecha - timedelta(days=365)
    servicios = (db.query(m.LgServicio)
                 .filter(m.LgServicio.unidad_id == unidad.id,
                         m.LgServicio.anulado_en.is_(None),
                         m.LgServicio.fecha <= fecha)
                 .order_by(m.LgServicio.fecha).all())
    del_anio = [s for s in servicios if s.fecha > desde]
    total = sum((Decimal(str(s.costo)) for s in del_anio), Decimal(0))
    con_un_anio = bool(servicios) and servicios[0].fecha <= desde
    if del_anio and con_un_anio:
        return _por_dia(total), "servicios", {"total": str(total), "n": len(del_anio)}
    if unidad.mantenimiento_anual is not None:
        anual = Decimal(str(unidad.mantenimiento_anual))
        return _por_dia(anual), "carga", {"anual": str(anual)}
    if del_anio:
        return _por_dia(total), "servicios", {"total": str(total), "n": len(del_anio)}
    if unidad.tipo_id:
        hermanas = (db.query(m.LgServicio.unidad_id, m.LgServicio.costo)
                    .join(m.LgUnidad, m.LgUnidad.id == m.LgServicio.unidad_id)
                    .filter(m.LgUnidad.tipo_id == unidad.tipo_id,
                            m.LgUnidad.activo.is_(True),
                            m.LgServicio.anulado_en.is_(None),
                            m.LgServicio.fecha > desde, m.LgServicio.fecha <= fecha)
                    .all())
        if hermanas:
            unidades = {u for u, _ in hermanas}
            suma = sum((Decimal(str(c)) for _, c in hermanas), Decimal(0))
            promedio = suma / Decimal(len(unidades))
            return (_por_dia(promedio), "promedio_tipo",
                    {"anual": str(_centavos(promedio)), "unidades": len(unidades)})
    tipo = _del_tipo(db, unidad, fecha)
    if tipo:
        return tipo["mantenimiento"], "tipo", {}
    return None, "falta", {}


def calcular_costo(db: Session, unidad: m.LgUnidad, fecha: date | None = None) -> dict:
    """El costo por dia de la unidad en esa fecha, por componente, con de
    donde sale cada uno: la unidad, sus servicios, la carga inicial, el
    promedio de su tipo o el costo de su tipo (seccion 150). Cada
    componente a centavos y el total, su suma."""
    fecha = fecha or hoy()
    tipo = _del_tipo(db, unidad, fecha)
    partes: dict = {}

    if unidad.valor_compra is not None and unidad.anios_vida:
        compra, anios = Decimal(str(unidad.valor_compra)), Decimal(str(unidad.anios_vida))
        partes["depreciacion"] = (_centavos(compra / anios / DIAS_DEL_ANIO), "unidad",
                                  {"compra": str(compra), "anios": str(anios)})
    elif tipo:
        partes["depreciacion"] = (tipo["depreciacion"], "tipo", {})

    if unidad.seguro_anual is not None:
        anual = Decimal(str(unidad.seguro_anual))
        partes["seguro"] = (_por_dia(anual), "unidad", {"anual": str(anual)})
    elif tipo:
        partes["seguro"] = (tipo["seguro"], "tipo", {})

    anuales = [unidad.tenencia_anual, unidad.verificacion_anual, unidad.gps_anual]
    if any(x is not None for x in anuales):
        anual = sum((Decimal(str(x)) for x in anuales if x is not None), Decimal(0))
        partes["gps"] = (_por_dia(anual), "unidad", {"anual": str(anual)})
    elif tipo:
        partes["gps"] = (tipo["gps"], "tipo", {})

    monto, fuente, detalle = _mantenimiento(db, unidad, fecha)
    if monto is not None:
        partes["mantenimiento"] = (monto, fuente, detalle)

    por_dia = km_por_dia(db, unidad.id, fecha)
    sin_km = {}
    if unidad.llantas_por_km is not None and por_dia is not None:
        tasa = Decimal(str(unidad.llantas_por_km))
        partes["llantas"] = (_centavos(tasa * por_dia), "unidad",
                             {"por_km": str(tasa), "km_dia": str(_centavos(por_dia))})
    elif tipo:
        partes["llantas"] = (tipo["llantas"], "tipo", {})
    elif unidad.llantas_por_km is not None:
        # Trae su costo por km, pero no sus km al dia: se dice que es eso
        # lo que falta, no el costo.
        sin_km = {"por_km": str(Decimal(str(unidad.llantas_por_km))), "sin_km": True}

    desglose = {c: {"monto": str(partes[c][0]), "fuente": partes[c][1],
                    "detalle": partes[c][2]} if c in partes
                else {"monto": None, "fuente": "falta",
                      "detalle": sin_km if c == "llantas" else {}}
                for c in COMPONENTES}
    total = sum((partes[c][0] for c in partes), Decimal(0))
    return {"fecha": fecha.isoformat(), "total": str(_centavos(total)),
            "completo": len(partes) == len(COMPONENTES), "desglose": desglose}


def costo_vigente(db: Session, unidad_id: int, fecha: date | None = None) -> m.LgCostoDia | None:
    """El renglon que rige en esa fecha: el mas reciente que no la pasa.
    Un viaje guarda este renglon, no el numero suelto."""
    fecha = fecha or hoy()
    return (db.query(m.LgCostoDia)
            .filter(m.LgCostoDia.unidad_id == unidad_id,
                    m.LgCostoDia.vigente_desde <= fecha)
            .order_by(m.LgCostoDia.vigente_desde.desc(), m.LgCostoDia.id.desc())
            .first())


def guardar_costo(db: Session, unidad: m.LgUnidad, desde: date, origen: str,
                  actor: m.Usuario | None = None, motivo: str | None = None) -> m.LgCostoDia | None:
    """Calcula y guarda el costo desde esa fecha. Si ya rige uno igual, no
    se repite; y si no hay con que calcular ni una parte, no se guarda un
    costo en cero: un viaje lo tomaria por bueno."""
    calculo = calcular_costo(db, unidad, desde)
    if _faltan(calculo["desglose"]) == len(COMPONENTES):
        return None
    vigente = costo_vigente(db, unidad.id, desde)
    if vigente and str(vigente.total) == calculo["total"] and \
            json.loads(vigente.desglose) == calculo["desglose"]:
        return None
    fila = m.LgCostoDia(unidad_id=unidad.id, vigente_desde=desde,
                        total=Decimal(calculo["total"]),
                        desglose=json.dumps(calculo["desglose"], ensure_ascii=False),
                        origen=origen, motivo=_texto(motivo, 300),
                        creado_por_id=actor.persona_id if actor else None,
                        creado_en=_ahora())
    db.add(fila)
    db.flush()
    return fila


def recalcular(db: Session, actor: m.Usuario, unidad: m.LgUnidad,
               motivo: str) -> m.LgCostoDia | None:
    """A mano, desde hoy, con su porque: cuando cambia algo a media mes."""
    motivo = _texto(motivo, 300)
    if not motivo or len(motivo) < 5:
        raise _no("Falta el motivo para recalcular a media mes.")
    fila = guardar_costo(db, unidad, hoy(), "recalculo", actor, motivo)
    _anotar(db, actor, "lg costo recalculado", "lg_unidades", unidad.id,
            {"k": "costo", "u": nombre_de(unidad),
             "t": str(fila.total) if fila else None, "m": motivo})
    return fila


def primero_del_mes(fecha: date) -> date:
    return fecha.replace(day=1)


def _faltan(desglose: dict) -> int:
    return sum(1 for v in desglose.values() if v.get("fuente") == "falta")


def costos_del_mes(db: Session, fecha: date | None = None) -> dict:
    """La tarea del dia: cada unidad activa con su costo del mes. El dia 1
    nace el del mes; si a alguna le falta, se le pone.

    Y el del mes que quedo incompleto --su tipo no tenia costo ese dia, o
    la unidad todavia no traia sus datos-- se completa desde hoy en cuanto
    hay con que: un mes entero con una parte en cero no le sirve a nadie.
    Lo que ya estaba completo no se mueve a media mes sin su porque. La
    que el dia 1 no tenia con que calcular nada empieza desde el dia en que
    lo tiene."""
    fecha = fecha or hoy()
    desde = primero_del_mes(fecha)
    hechos = completados = 0
    for unidad in db.query(m.LgUnidad).filter(m.LgUnidad.activo.is_(True)).all():
        vigente = costo_vigente(db, unidad.id, fecha)
        if vigente is None or vigente.vigente_desde < desde:
            fila = guardar_costo(db, unidad, desde, "mensual")
            if fila is None:
                if fecha > desde and guardar_costo(db, unidad, fecha, "completo"):
                    completados += 1
                continue
            hechos += 1
            vigente = fila
        # El del mes, a medias: desde hoy, con lo que ya hay.
        antes = _faltan(json.loads(vigente.desglose))
        if fecha > vigente.vigente_desde and antes and \
                _faltan(calcular_costo(db, unidad, fecha)["desglose"]) < antes:
            if guardar_costo(db, unidad, fecha, "completo"):
                completados += 1
    db.commit()
    return {"guardados": hechos, "completados": completados, "desde": desde.isoformat()}


# ================================================================ lo que se ensena

def _documentos_dict(docs: dict, fecha: date, tipos=DOCUMENTOS) -> list[dict]:
    salida = []
    for tipo in tipos:
        doc = docs.get(tipo)
        renglon = {"tipo": tipo, **estado_documento(doc, fecha)}
        if doc:
            renglon.update({"id": doc.id, "folio": doc.folio, "detalle": doc.detalle,
                            "archivo_id": doc.archivo_id,
                            "capturado_en": _iso(doc.capturado_en)})
        salida.append(renglon)
    return salida


def faltas(unidad: m.LgUnidad) -> list[str]:
    """Lo que le falta para estar completa: economico, tipo, rendimiento."""
    salida = []
    if not unidad.numero_economico:
        salida.append("economico")
    if unidad.clase == "unidad" and not unidad.tipo_id:
        salida.append("tipo")
    if unidad.clase == "unidad" and unidad.rendimiento_ref is None:
        salida.append("rendimiento")
    return salida


def _unidad_base(u: m.LgUnidad) -> dict:
    return {"id": u.id, "placa": u.placa, "numero_economico": u.numero_economico,
            "clase": u.clase, "marca_modelo": u.marca_modelo, "anio": u.anio,
            "chasis": u.chasis, "iave": u.iave, "categoria_odoo": u.categoria_odoo,
            "tipo_id": u.tipo_id, "tipo": u.tipo.nombre if u.tipo else None,
            "rendimiento_ref": str(u.rendimiento_ref) if u.rendimiento_ref is not None else None,
            "odometro_km": u.odometro_km, "odometro_fecha": _iso(u.odometro_fecha),
            "estado": u.estado, "estado_motivo": u.estado_motivo,
            "estado_hasta": _iso(u.estado_hasta), "estado_desde": _iso(u.estado_desde),
            "patio_id": u.patio_id, "patio": u.patio.nombre if u.patio else None,
            "activo": u.activo, "baja_odoo_en": _iso(u.baja_odoo_en),
            "faltas": faltas(u)}


def orden_de_lista(u: m.LgUnidad) -> tuple:
    """Las unidades antes que las cajas; cada una por su numero economico
    como numero --la 8 antes que la 12--, y las que no lo tienen al final,
    por placa."""
    llave = u.economico_llave or ""
    return (u.clase != "unidad", not llave, not llave.isdigit(),
            int(llave) if llave.isdigit() else 0, llave, u.placa or "")


def lista(db: Session, fecha: date | None = None) -> dict:
    """La pantalla de Flota LG: cada unidad con su estado, si puede salir,
    su proximo servicio y su costo por dia, y las cifras de arriba."""
    from app import lg_disponibilidad
    fecha = fecha or hoy()
    unidades = sorted(db.query(m.LgUnidad).filter(m.LgUnidad.activo.is_(True)).all(),
                      key=orden_de_lista)
    ids = [u.id for u in unidades]
    docs = vigentes(db, unidad_ids=ids)
    ultimos = ultimos_servicios(db, ids)
    planes: dict = {}
    salida, cifras = [], {"unidades": 0, "en_viaje": 0, "libres": 0, "taller": 0,
                          "no_pueden": 0, "servicio_proximo": 0, "documentos": 0,
                          "por_completar": 0, "remolques": 0}
    for u in unidades:
        llave = ("r",) if u.clase == "remolque" else ("t", u.tipo_id)
        if llave not in planes:
            planes[llave] = plan_de(db, u)
        prox = proximos(planes[llave], ultimos, u)
        mios = docs.get(("u", u.id), {})
        dispo = lg_disponibilidad.evaluar_unidad(
            lg_disponibilidad.datos_unidad(u, mios, prox), fecha, fecha, None, fecha)
        costo = costo_vigente(db, u.id, fecha)
        desglose = json.loads(costo.desglose) if costo else {}
        documentos = _documentos_dict(mios, fecha)
        renglon = {**_unidad_base(u), "proximo": el_mas_cercano(prox),
                   # Para decir por que no hay proximo: sin plan para su
                   # tipo, o con plan y sin su ultimo servicio registrado.
                   "plan_n": len(prox),
                   "sin_ultimo": sum(1 for x in prox if x["estado"] == "sin_ultimo"),
                   "documentos": documentos, "disponibilidad": dispo,
                   "costo_dia": str(costo.total) if costo else None,
                   "costo_completo": (all(v["fuente"] != "falta" for v in desglose.values())
                                      if costo else None)}
        salida.append(renglon)
        if u.clase == "remolque":
            cifras["remolques"] += 1
            continue
        cifras["unidades"] += 1
        # La que solo no sale porque le falta su tipo se cuenta por
        # completar, no entre las que tienen algo vencido.
        bloqueos = [x["clave"] for x in dispo["motivos"] if x["nivel"] == "bloqueo"]
        if u.estado == "en_viaje":
            cifras["en_viaje"] += 1
        elif u.estado in CON_MOTIVO:
            cifras["taller"] += 1
        elif bloqueos and set(bloqueos) <= {"sin_tipo"}:
            pass
        elif bloqueos:
            cifras["no_pueden"] += 1
        else:
            cifras["libres"] += 1
        if any(x["estado"] in ("proximo", "vencido") for x in prox):
            cifras["servicio_proximo"] += 1
        if any(d["estado"] in ("por_vencer", "vencido") for d in documentos):
            cifras["documentos"] += 1
        if renglon["faltas"]:
            cifras["por_completar"] += 1
    return {"hoy": fecha.isoformat(), "unidades": salida, "cifras": cifras}


def detalle(db: Session, unidad_id: int, fecha: date | None = None) -> dict:
    from app import lg_disponibilidad
    fecha = fecha or hoy()
    u = unidad_o_404(db, unidad_id)
    mios = vigentes(db, unidad_ids=[u.id]).get(("u", u.id), {})
    prox = proximos(plan_de(db, u), ultimos_servicios(db, [u.id]), u)
    dispo = lg_disponibilidad.evaluar_unidad(
        lg_disponibilidad.datos_unidad(u, mios, prox), fecha, fecha, None, fecha)
    costo = costo_vigente(db, u.id, fecha)
    historial_costo = (db.query(m.LgCostoDia).filter(m.LgCostoDia.unidad_id == u.id)
                       .order_by(m.LgCostoDia.vigente_desde.desc(),
                                 m.LgCostoDia.id.desc()).limit(12).all())
    servicios = (db.query(m.LgServicio).filter(m.LgServicio.unidad_id == u.id)
                 .order_by(m.LgServicio.fecha.desc(), m.LgServicio.id.desc()).all())
    desde = fecha - timedelta(days=365)
    del_anio = [s for s in servicios if not s.anulado_en and s.fecha > desde]
    actuales = llantas_actuales(db, u)
    lecturas = (db.query(m.LgLecturaOdometro).filter(m.LgLecturaOdometro.unidad_id == u.id)
                .order_by(m.LgLecturaOdometro.fecha.desc(),
                          m.LgLecturaOdometro.id.desc()).limit(10).all())
    return {
        "hoy": fecha.isoformat(), "unidad": _unidad_base(u),
        "costos": {c: (str(getattr(u, c)) if getattr(u, c) is not None else None)
                   for c in CAMPOS_COSTO},
        "disponibilidad": dispo,
        "documentos": _documentos_dict(mios, fecha),
        "plan": prox,
        "costo": ({"id": costo.id, "vigente_desde": costo.vigente_desde.isoformat(),
                   "total": str(costo.total), "desglose": json.loads(costo.desglose),
                   "origen": costo.origen, "motivo": costo.motivo} if costo else None),
        "costo_hoy": calcular_costo(db, u, fecha),
        "historial_costo": [{"vigente_desde": c.vigente_desde.isoformat(),
                             "total": str(c.total), "origen": c.origen,
                             "motivo": c.motivo} for c in historial_costo],
        "servicios": [{"id": s.id, "fecha": s.fecha.isoformat(), "km": s.km,
                       "nombre": s.nombre, "plan_id": s.plan_id, "costo": str(s.costo),
                       "taller": s.taller, "factura": s.factura,
                       "archivo_id": s.archivo_id, "anulado": bool(s.anulado_en),
                       "anulado_motivo": s.anulado_motivo} for s in servicios[:50]],
        "servicios_anio": {"n": len(del_anio),
                           "total": str(sum((Decimal(str(s.costo)) for s in del_anio),
                                            Decimal(0)))},
        "llantas": [{"posicion": p, "instalada_km": actuales[p].instalada_km,
                     "instalada_en": actuales[p].instalada_en.isoformat(),
                     "detalle": actuales[p].detalle,
                     "km": (u.odometro_km - actuales[p].instalada_km
                            if u.odometro_km is not None else None)}
                    if p in actuales else {"posicion": p, "instalada_km": None}
                    for p in posiciones(u)],
        "vida_llanta_km": u.tipo.vida_llanta_km if u.tipo else None,
        "lecturas": [{"km": x.km, "fecha": x.fecha.isoformat(), "fuente": x.fuente,
                      "motivo": x.motivo} for x in lecturas],
        "rendimiento": {"referencia": str(u.rendimiento_ref) if u.rendimiento_ref is not None
                        else None, "promedio_10": None, "alerta": None},
    }


def planes(db: Session) -> dict:
    """La pestana del plan preventivo: el de cada tipo y el de las cajas."""
    tipos = (db.query(m.LgTipoUnidad).filter(m.LgTipoUnidad.activo.is_(True))
             .order_by(m.LgTipoUnidad.orden, m.LgTipoUnidad.id).all())
    filas = (db.query(m.LgPlanServicio)
             .order_by(m.LgPlanServicio.orden, m.LgPlanServicio.id).all())

    def de(cond):
        return [{"id": p.id, "nombre": p.nombre, "cada_km": p.cada_km,
                 "costo_aprox": str(p.costo_aprox) if p.costo_aprox is not None else None,
                 "orden": p.orden, "activo": p.activo} for p in filas if cond(p)]
    return {"tipos": [{"id": t.id, "nombre": t.nombre, "llantas": t.llantas,
                       "vida_llanta_km": t.vida_llanta_km,
                       "plan": de(lambda p, t=t: p.tipo_id == t.id and p.clase == "unidad")}
                      for t in tipos],
            "remolque": de(lambda p: p.clase == "remolque")}


# ================================================================ la bitacora

NOMBRES_ESTADO = {
    "es": {"disponible": "libre", "en_viaje": "en viaje", "en_taller": "en taller",
           "fuera_de_servicio": "fuera de servicio"},
    "en": {"disponible": "available", "en_viaje": "on a trip", "en_taller": "in the shop",
           "fuera_de_servicio": "out of service"},
    "pt": {"disponible": "livre", "en_viaje": "em viagem", "en_taller": "na oficina",
           "fuera_de_servicio": "fora de serviço"},
}
NOMBRES_DOC = {
    "es": {"tarjeta_circulacion": "tarjeta de circulación", "poliza_seguro": "póliza de seguro",
           "permiso_sct": "permiso SCT", "verificacion": "verificación físico-mecánica",
           "gps": "GPS Pegasus", "licencia": "licencia federal"},
    "en": {"tarjeta_circulacion": "registration card", "poliza_seguro": "insurance policy",
           "permiso_sct": "SCT permit", "verificacion": "mechanical inspection",
           "gps": "Pegasus GPS", "licencia": "federal driver's license"},
    "pt": {"tarjeta_circulacion": "documento do veículo", "poliza_seguro": "apólice de seguro",
           "permiso_sct": "licença SCT", "verificacion": "inspeção mecânica",
           "gps": "GPS Pegasus", "licencia": "habilitação federal"},
}
FRASES = {
    "es": {"estado": "{u}: de {de} a {a}", "odometro": "{u}: odómetro {km} km del {f}",
           "documento": "{u}: {t}", "licencia": "{o}: licencia federal",
           "servicio": "{u}: servicio {n} del {f}, {p}", "servicio_anulado": "{u}: anuló el servicio {n}",
           "llanta": "{u}: llanta nueva · {pos}", "datos": "{u}: cambió sus datos",
           "costo": "{u}: recalculó el costo por día", "plan": "Plan preventivo: {n} cada {c} km",
           "plan_cambio": "Plan preventivo: {n}", "carga": "Carga inicial del Excel: {n} unidades",
           "jornada": "{o}: marca del {f} {r}", "codigo": "{o}: código de la app",
           "viaje": "{o}: en viaje del {f} al {h}", "regreso": "{o}: ya regresó de viaje ({f})", "lectura": "Lectura de Odoo: {n} altas",
           "validada": "validada", "rechazada": "rechazada", "vence": "vence {v}",
           "sin_vencimiento": "sin vencimiento", "motivo": "«{m}»", "hasta": "hasta el {h}"},
    "en": {"estado": "{u}: from {de} to {a}", "odometro": "{u}: odometer {km} km on {f}",
           "documento": "{u}: {t}", "licencia": "{o}: federal license",
           "servicio": "{u}: service {n} on {f}, {p}", "servicio_anulado": "{u}: voided service {n}",
           "llanta": "{u}: new tire · {pos}", "datos": "{u}: changed its data",
           "costo": "{u}: recalculated the daily cost", "plan": "Maintenance plan: {n} every {c} km",
           "plan_cambio": "Maintenance plan: {n}", "carga": "Initial Excel load: {n} units",
           "jornada": "{o}: check-in of {f} {r}", "codigo": "{o}: app code",
           "viaje": "{o}: on a trip from {f} to {h}", "regreso": "{o}: back from the trip ({f})", "lectura": "Odoo read: {n} new",
           "validada": "validated", "rechazada": "rejected", "vence": "expires {v}",
           "sin_vencimiento": "no expiry", "motivo": "“{m}”", "hasta": "until {h}"},
    "pt": {"estado": "{u}: de {de} para {a}", "odometro": "{u}: hodômetro {km} km em {f}",
           "documento": "{u}: {t}", "licencia": "{o}: habilitação federal",
           "servicio": "{u}: serviço {n} em {f}, {p}", "servicio_anulado": "{u}: anulou o serviço {n}",
           "llanta": "{u}: pneu novo · {pos}", "datos": "{u}: mudou seus dados",
           "costo": "{u}: recalculou o custo por dia", "plan": "Plano preventivo: {n} a cada {c} km",
           "plan_cambio": "Plano preventivo: {n}", "carga": "Carga inicial do Excel: {n} unidades",
           "jornada": "{o}: marcação de {f} {r}", "codigo": "{o}: código do app",
           "viaje": "{o}: em viagem de {f} a {h}", "regreso": "{o}: já voltou de viagem ({f})", "lectura": "Leitura do Odoo: {n} inclusões",
           "validada": "validada", "rechazada": "rejeitada", "vence": "vence {v}",
           "sin_vencimiento": "sem vencimento", "motivo": "«{m}»", "hasta": "até {h}"},
}


# Las posiciones de las llantas como se leen, las mismas de la pantalla.
NOMBRES_POSICION = {
    "es": {"DI": "Delantera izq.", "DD": "Delantera der.", "TI": "Trasera izq.",
           "TD": "Trasera der.", "TIE": "Trasera izq. ext.", "TII": "Trasera izq. int.",
           "TDI": "Trasera der. int.", "TDE": "Trasera der. ext.", "1IE": "Eje 1 izq. ext.",
           "1II": "Eje 1 izq. int.", "1DI": "Eje 1 der. int.", "1DE": "Eje 1 der. ext.",
           "2IE": "Eje 2 izq. ext.", "2II": "Eje 2 izq. int.", "2DI": "Eje 2 der. int.",
           "2DE": "Eje 2 der. ext.", "R": "Refacción"},
    "en": {"DI": "Front left", "DD": "Front right", "TI": "Rear left", "TD": "Rear right",
           "TIE": "Rear left outer", "TII": "Rear left inner", "TDI": "Rear right inner",
           "TDE": "Rear right outer", "1IE": "Axle 1 left outer", "1II": "Axle 1 left inner",
           "1DI": "Axle 1 right inner", "1DE": "Axle 1 right outer",
           "2IE": "Axle 2 left outer", "2II": "Axle 2 left inner",
           "2DI": "Axle 2 right inner", "2DE": "Axle 2 right outer", "R": "Spare"},
    "pt": {"DI": "Dianteiro esq.", "DD": "Dianteiro dir.", "TI": "Traseiro esq.",
           "TD": "Traseiro dir.", "TIE": "Traseiro esq. ext.", "TII": "Traseiro esq. int.",
           "TDI": "Traseiro dir. int.", "TDE": "Traseiro dir. ext.", "1IE": "Eixo 1 esq. ext.",
           "1II": "Eixo 1 esq. int.", "1DI": "Eixo 1 dir. int.", "1DE": "Eixo 1 dir. ext.",
           "2IE": "Eixo 2 esq. ext.", "2II": "Eixo 2 esq. int.", "2DI": "Eixo 2 dir. int.",
           "2DE": "Eixo 2 dir. ext.", "R": "Estepe"},
}


def _fecha_txt(valor, idioma: str) -> str:
    if not valor:
        return ""
    try:
        return lg_catalogos.fecha_texto(date.fromisoformat(str(valor)[:10]), idioma)
    except ValueError:
        return str(valor)


def que_cambio(r: m.RegistroAdmin, idioma: str) -> str:
    """Lo que dice un renglon de la bitacora de Logistica en el idioma de
    quien lee."""
    lengua = idioma if idioma in FRASES else "es"
    f, est, docs = FRASES[lengua], NOMBRES_ESTADO[lengua], NOMBRES_DOC[lengua]
    try:
        d = json.loads(r.detalle or "{}")
    except ValueError:
        return r.detalle or r.accion
    k = d.get("k")
    if k not in f:
        return r.accion
    texto = f[k].format(
        u=d.get("u", ""), o=d.get("o", ""), de=est.get(d.get("de"), d.get("de", "")),
        a=est.get(d.get("a"), d.get("a", "")),
        km=f"{d['km']:,}" if isinstance(d.get("km"), int) else d.get("km", ""),
        t=docs.get(d.get("t"), d.get("t", "")), n=d.get("n", ""),
        p=lg_catalogos.pesos(Decimal(d["p"])) if d.get("p") not in (None, "None") else "",
        pos=NOMBRES_POSICION[lengua].get(d.get("pos"), d.get("pos", "")), c=f"{d['c']:,}" if isinstance(d.get("c"), int) else d.get("c", ""),
        f=_fecha_txt(d.get("f"), lengua), h=_fecha_txt(d.get("h"), lengua),
        r=f.get(d.get("r"), "") if d.get("r") else "")
    extras = []
    if k in ("documento", "licencia"):
        extras.append(f["vence"].format(v=_fecha_txt(d["v"], lengua)) if d.get("v")
                      else f["sin_vencimiento"])
    if k == "estado" and d.get("h"):
        extras.append(f["hasta"].format(h=_fecha_txt(d["h"], lengua)))
    if d.get("m"):
        extras.append(f["motivo"].format(m=d["m"]))
    return " · ".join([texto] + extras)


POR_PAGINA = 50


def bitacora(db: Session, objetos: tuple, pagina: int = 1, idioma: str = "es",
             objeto_id: int | None = None) -> dict:
    """Lo que le ha pasado a la flota o a la jornada, lo mas nuevo arriba."""
    pagina = max(1, pagina)
    consulta = (db.query(m.RegistroAdmin).filter(m.RegistroAdmin.objeto.in_(objetos))
                .order_by(m.RegistroAdmin.creado_en.desc(), m.RegistroAdmin.id.desc()))
    if objeto_id is not None:
        consulta = consulta.filter(m.RegistroAdmin.objeto_id == objeto_id)
    total = consulta.count()
    filas = consulta.offset((pagina - 1) * POR_PAGINA).limit(POR_PAGINA).all()
    return {"filas": [{"id": r.id, "cuando": _iso(r.creado_en),
                       "quien": r.persona.nombre if r.persona else None,
                       "objeto": r.objeto, "que": que_cambio(r, idioma)} for r in filas],
            "total": total, "pagina": pagina, "por_pagina": POR_PAGINA}


def tipo_de_flota(db: Session, actor: m.Usuario, tipo_id: int, datos: dict) -> m.LgTipoUnidad:
    """Lo de flota de un tipo de unidad: cuantas llantas lleva y cuantos km
    dura una llanta. El nombre y lo demas los lleva sistema y calidad."""
    tipo = db.get(m.LgTipoUnidad, tipo_id)
    if not tipo:
        raise HTTPException(404, "No existe ese tipo de unidad")
    antes = {"l": tipo.llantas, "v": tipo.vida_llanta_km}
    if "llantas" in datos:
        valor = datos["llantas"]
        if valor in (None, ""):
            tipo.llantas = None
        else:
            valor = int(_numero(valor, "las llantas", entero=True, minimo=2, maximo=22))
            if valor not in POSICIONES:
                raise _no("Las llantas son 4, 6 o 10, sin la refacción.")
            tipo.llantas = valor
    if "vida_llanta_km" in datos:
        valor = datos["vida_llanta_km"]
        tipo.vida_llanta_km = None if valor in (None, "") else int(_numero(
            valor, "la vida de una llanta", entero=True, minimo=1000, maximo=500_000))
    _anotar(db, actor, "lg tipo de flota", "lg_plan", tipo.id,
            {"k": "plan_cambio", "n": tipo.nombre, "antes": antes,
             "l": tipo.llantas, "v": tipo.vida_llanta_km})
    db.flush()
    return tipo


# Las llantas de cada tipo con que arranca (sin la refaccion). La
# migracion e2a4c6b8d0f1 pone lo mismo; una prueba cuida que digan igual.
LLANTAS_DE_ARRANQUE = {"1.5 ton": 4, "4 ton": 6, "Torton 15 ton": 10, "Tracto": 10}


def sembrar(db: Session) -> None:
    """Las llantas de los cuatro tipos, si no las tienen. Lo demas lo
    captura quien lleva la flota."""
    for tipo in db.query(m.LgTipoUnidad).all():
        if tipo.llantas is None and tipo.nombre in LLANTAS_DE_ARRANQUE:
            tipo.llantas = LLANTAS_DE_ARRANQUE[tipo.nombre]
    db.flush()


DONDE = {
    "es": {"prefijo": "Logística", "lg_unidades": "Flota", "lg_plan": "Plan preventivo",
           "lg_carga": "Carga inicial", "lg_operadores": "Operadores",
           "lg_jornada": "Jornada"},
    "en": {"prefijo": "Logistics", "lg_unidades": "Fleet", "lg_plan": "Maintenance plan",
           "lg_carga": "Initial load", "lg_operadores": "Drivers",
           "lg_jornada": "Workday"},
    "pt": {"prefijo": "Logística", "lg_unidades": "Frota", "lg_plan": "Plano preventivo",
           "lg_carga": "Carga inicial", "lg_operadores": "Motoristas",
           "lg_jornada": "Jornada"},
}


def donde(objeto: str, idioma: str) -> str | None:
    """En que parte de Logistica paso, para la bitacora de administracion."""
    t = DONDE.get(idioma) or DONDE["es"]
    if objeto not in t:
        return None
    return f"{t['prefijo']} · {t[objeto]}"


# ================================================================ los avisos

def _a_quien(db: Session, actividad: str, respaldo: str) -> list[m.Usuario]:
    from app import freelance
    return freelance._quienes(db, actividad) or freelance._quienes(db, respaldo)


def _avisar(db: Session, usuarios: list, clave: str, enlace: str, etiqueta: str,
            quien: str, tipo: str, vence: date) -> int:
    """Correo y telefono a cada uno, en el idioma de su pais, con el
    nombre del documento en ese idioma."""
    from app import correo_html, push
    from app import textos_aviso as ta
    for u in usuarios:
        plaza = u.persona.plaza if u.persona else None
        lengua = plaza.pais.idioma if plaza and plaza.pais else "es"
        nombres = NOMBRES_DOC.get(lengua) or NOMBRES_DOC["es"]
        datos = {"quien": quien, "documento": nombres.get(tipo, tipo),
                 "fecha": vence.strftime("%d/%m/%Y")}
        titulo = ta.t(lengua, f"{clave}_asunto", **datos)
        texto = ta.t(lengua, f"{clave}_cuerpo", **datos)
        if u.correo:
            db.add(m.Notificacion(
                destinatario=m.Destinatario.COLABORADOR, canal=m.Canal.CORREO,
                correo=u.correo, idioma=lengua, asunto=titulo[:200], cuerpo=texto[:2000],
                datos=correo_html.guardar_datos(
                    [(ta.t(lengua, "lg_quien"), quien),
                     (ta.t(lengua, "lg_documento"), datos["documento"]),
                     (ta.t(lengua, "lg_vence"), datos["fecha"])]),
                enlace_seguimiento=enlace))
        try:
            push.avisar(db, u.persona_id, titulo, texto, url=enlace, etiqueta=etiqueta)
        except Exception:                                  # noqa: BLE001
            pass
    return len(usuarios)


def avisar_vencimientos(db: Session, fecha: date | None = None) -> dict:
    """A 30 dias de vencer y el dia que vence, una vez cada uno: los
    documentos de las unidades a quien lleva la flota; las licencias a
    quien da el acceso de los operadores."""
    fecha = fecha or hoy()
    ahora = _ahora()
    cuenta = {"previos": 0, "vencidos": 0}
    docs = (db.query(m.LgDocumento)
            .filter(m.LgDocumento.reemplazado_en.is_(None),
                    m.LgDocumento.vence_en.isnot(None)).all())
    flota = licencias = None
    for doc in docs:
        dias = (doc.vence_en - fecha).days
        if dias < 0 and doc.aviso_vencido_en is None:
            clave = "lg_vencido"
        elif 0 <= dias <= DIAS_AVISO and doc.aviso_previo_en is None:
            clave = "lg_por_vencer"
        else:
            continue
        if doc.unidad_id:
            unidad = db.get(m.LgUnidad, doc.unidad_id)
            if not unidad or not unidad.activo:
                continue
            if flota is None:
                flota = _a_quien(db, "lg.flota.editar", "lg.flota.ver")
            usuarios, quien = flota, nombre_de(unidad)
            enlace = f"/consola/#/lg/flota/{unidad.id}"
        else:
            operador = db.get(m.LgOperador, doc.operador_id)
            if not operador or not operador.activo:
                continue
            if licencias is None:
                licencias = _a_quien(db, "lg.operadores.editar", "lg.jornada.ver")
            usuarios, quien = licencias, operador.nombre
            enlace = "/consola/#/lg/jornada"
        if not usuarios:
            continue
        _avisar(db, usuarios, clave, enlace, f"lg-doc-{doc.id}", quien, doc.tipo,
                doc.vence_en)
        if clave == "lg_vencido":
            doc.aviso_vencido_en = ahora
            doc.aviso_previo_en = doc.aviso_previo_en or ahora
            cuenta["vencidos"] += 1
        else:
            doc.aviso_previo_en = ahora
            cuenta["previos"] += 1
    db.commit()
    return cuenta


def diaria(db: Session, fecha: date | None = None) -> dict:
    """La tarea de cada manana: los avisos de vencimiento y el costo del
    mes de cada unidad."""
    return {"avisos": avisar_vencimientos(db, fecha), "costos": costos_del_mes(db, fecha)}

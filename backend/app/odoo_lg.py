# -*- coding: utf-8 -*-
"""Logistica (seccion 151): las unidades y los operadores, leidos de Odoo.

Lo que dijo Odoo el 3 de octubre (dos lecturas de solo conteos):
  * Las 52 unidades de Logistica estan en la compania 3, «Centauro
    Logistic SA CV»; solo una trae la etiqueta «Logistica». Por eso se
    toman por la compania y no por la etiqueta: las de EP son de otra.
  * Entre ellas hay dos cajas secas («Remolque») y un Prius
    («Utilitario»). Decision de Salvador: las cajas entran, sin asignarse
    solas; el Prius no.
  * Los operadores son los de la compania 3 con puesto «Operador» (34).
    Su correo personal --con el que entran a LG Connect, como en EP--,
    su telefono y su fecha de ingreso vienen de Odoo; sus datos
    bancarios se quedan alla. Odoo no tiene su licencia.

Como las de EP: nunca escribe en Odoo; primero el ensayo y la primera
lectura a mano; despues, cada hora. Lo que manda Odoo --placa, modelo,
ano, chasis, IAVE; nombre, correo, telefono, ingreso-- se toma de Odoo;
lo de Connect --economico, tipo, odometro, expediente, licencia-- no se
toca. Si Odoo deja de mandar algo que Connect tiene activo, se da de
baja; si una lectura trae cero y Connect tiene activos, se detiene.
"""
import json
import logging
import re
import unicodedata
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app import lg_flota
from app import models as m
from app import odoo_api
from app.odoo_api import COMPANIA_LOGISTIC
from app.odoo_flota_reglas import marca_modelo_de

registro = logging.getLogger("centauro.odoo")

COMPANIA = COMPANIA_LOGISTIC
TIPO_FLOTA = "lg_flota"
TIPO_OPERADORES = "lg_operadores"
CAMPOS_UNIDAD = ["license_plate", "category_id", "model_id", "model_year", "vin_sn",
                 "company_id"]
IAVE = "x_studio_iave"
CAMPOS_OPERADOR = ["name", "job_id", "job_title", "private_email", "mobile_phone",
                   "private_phone", "first_contract_date", "company_id"]
PUESTO_OPERADOR = "operador"
# La categoria de Odoo y el tipo de unidad de la seccion 150 que le toca.
# Solo se sugiere: el tipo es de Connect y no se pisa.
TIPO_DE_CATEGORIA = (("remolque", None), ("utilitario", None),
                     ("1 tonelada", "1.5 ton"), ("1.5", "1.5 ton"),
                     ("4 tonelada", "4 ton"), ("torton", "Torton 15 ton"),
                     ("15 tonelada", "Torton 15 ton"), ("tr ", "Tracto"),
                     ("tracto", "Tracto"), ("25 tonelada", "Tracto"))


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def normal(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(t.lower().split())


def placa_de(texto) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(texto or "").upper())


def _nombre(valor) -> str:
    if isinstance(valor, (list, tuple)) and len(valor) > 1:
        return str(valor[1] or "").strip()
    return ""


def _texto(valor, largo: int) -> str | None:
    if valor in (None, False):
        return None
    limpio = " ".join(str(valor).split())
    return limpio[:largo] or None


def clase_de(categoria: str) -> str | None:
    """«remolque», «unidad», o None si no es de la flota (el utilitario)."""
    c = normal(categoria)
    if "remolque" in c:
        return "remolque"
    if "utilitario" in c:
        return None
    return "unidad"


def tipo_sugerido(categoria: str) -> str | None:
    c = normal(categoria) + " "
    for pista, tipo in TIPO_DE_CATEGORIA:
        if c.startswith(pista) or pista in c:
            return tipo
    return None


def es_operador(empleado: dict) -> bool:
    puesto = normal(_nombre(empleado.get("job_id")) or empleado.get("job_title"))
    return puesto.startswith(PUESTO_OPERADOR)


def _fecha(valor) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _anio(valor) -> int | None:
    try:
        anio = int(str(valor)[:4])
    except (TypeError, ValueError):
        return None
    return anio if 1950 <= anio <= 2100 else None


# ================================================================ las unidades

def datos_de_unidad(v: dict) -> dict:
    categoria = _nombre(v.get("category_id"))
    return {"odoo_id": v["id"], "placa": placa_de(v.get("license_plate")) or None,
            "clase": clase_de(categoria), "categoria_odoo": _texto(categoria, 80),
            # «International/City Star» como se lee, igual que la flota de EP.
            "marca_modelo": _texto(marca_modelo_de(v.get("model_id")), 120),
            "anio": _anio(v.get("model_year")), "chasis": _texto(v.get("vin_sn"), 40),
            "iave": _texto(v.get(IAVE), 40), "tipo_sugerido": tipo_sugerido(categoria)}


DE_ODOO_UNIDAD = ("placa", "clase", "categoria_odoo", "marca_modelo", "anio", "chasis",
                  "iave")


def planear_unidades(leidas: list[dict], existentes: list[m.LgUnidad]) -> dict:
    """Que haria la lectura, sin tocar nada."""
    por_odoo = {u.odoo_id: u for u in existentes if u.odoo_id}
    por_placa: dict = {}
    for u in existentes:
        por_placa.setdefault(placa_de(u.placa), []).append(u)
    plan = {"altas": [], "cambios": [], "vinculadas": [], "bajas": [], "pendientes": [],
            "fuera": [], "sin_cambio": 0}
    vistos = set()
    for v in leidas:
        d = datos_de_unidad(v)
        if d["clase"] is None:
            plan["fuera"].append({"odoo_id": d["odoo_id"], "placa": d["placa"],
                                  "categoria": d["categoria_odoo"]})
            continue
        if not d["placa"]:
            plan["pendientes"].append({"odoo_id": d["odoo_id"], "placa": None,
                                       "motivo": "sin placa en Odoo"})
            continue
        unidad = por_odoo.get(d["odoo_id"])
        if unidad is None:
            candidatas = [u for u in por_placa.get(d["placa"], []) if not u.odoo_id]
            if len(candidatas) == 1:
                unidad = candidatas[0]
                plan["vinculadas"].append({"id": unidad.id, **d})
        if unidad is None:
            plan["altas"].append(d)
            continue
        vistos.add(unidad.id)
        cambios = {c: [getattr(unidad, c), d[c]] for c in DE_ODOO_UNIDAD
                   if d[c] is not None and getattr(unidad, c) != d[c]}
        if not unidad.activo:
            cambios["activo"] = [False, True]
        if cambios:
            plan["cambios"].append({"id": unidad.id, "placa": d["placa"],
                                    "cambios": cambios, "datos": d})
        else:
            plan["sin_cambio"] += 1
    for u in existentes:
        if u.odoo_id and u.activo and u.id not in vistos and not any(
                x.get("id") == u.id for x in plan["vinculadas"]):
            plan["bajas"].append({"id": u.id, "placa": u.placa})
    return plan


def _leer_unidades(odoo) -> list[dict]:
    campos = list(CAMPOS_UNIDAD)
    try:
        if IAVE in (odoo.campos("fleet.vehicle") or {}):
            campos.append(IAVE)
    except Exception as error:                             # noqa: BLE001
        registro.warning("no se pudieron leer los campos de la flota: %s", error)
    return odoo.leer("fleet.vehicle", [["company_id", "=", COMPANIA]], campos,
                     compania=COMPANIA)


def _tipos(db: Session) -> dict:
    return {t.nombre: t.id for t in db.query(m.LgTipoUnidad)
            .filter(m.LgTipoUnidad.activo.is_(True)).all()}


def aplicar_unidades(db: Session, plan: dict) -> None:
    ahora = _utc()
    tipos = _tipos(db)
    for d in plan["altas"]:
        db.add(m.LgUnidad(
            odoo_id=d["odoo_id"], placa=d["placa"], clase=d["clase"],
            categoria_odoo=d["categoria_odoo"], marca_modelo=d["marca_modelo"],
            anio=d["anio"], chasis=d["chasis"], iave=d["iave"],
            tipo_id=tipos.get(d["tipo_sugerido"]) if d["clase"] == "unidad" else None,
            odoo_sincronizado_en=ahora, estado="disponible", activo=True))
    for d in plan["vinculadas"]:
        unidad = db.get(m.LgUnidad, d["id"])
        unidad.odoo_id = d["odoo_id"]
    for c in plan["cambios"]:
        unidad = db.get(m.LgUnidad, c["id"])
        for campo, (_, nuevo) in c["cambios"].items():
            setattr(unidad, campo, nuevo)
        if c["cambios"].get("activo"):
            unidad.baja_odoo_en = None
        unidad.odoo_sincronizado_en = ahora
    for b in plan["bajas"]:
        unidad = db.get(m.LgUnidad, b["id"])
        unidad.activo, unidad.baja_odoo_en = False, ahora
    db.flush()


# ================================================================ los operadores

def datos_de_operador(e: dict) -> dict:
    correo = (_texto(e.get("private_email"), 160) or "").lower() or None
    telefono = _texto(e.get("mobile_phone"), 30) or _texto(e.get("private_phone"), 30)
    return {"odoo_id": e["id"], "nombre": _texto(e.get("name"), 160) or f"#{e['id']}",
            "correo": correo, "telefono": telefono,
            "puesto_odoo": _texto(_nombre(e.get("job_id")) or e.get("job_title"), 120),
            "fecha_ingreso": _fecha(e.get("first_contract_date"))}


DE_ODOO_OPERADOR = ("nombre", "correo", "telefono", "puesto_odoo", "fecha_ingreso")


def planear_operadores(leidos: list[dict], existentes: list[m.LgOperador]) -> dict:
    por_odoo = {o.odoo_id: o for o in existentes if o.odoo_id}
    operadores = [datos_de_operador(e) for e in leidos if es_operador(e)]
    # Los demas empleados de la compania (la gerencia, quien lleva la
    # flota) no entran; solo se cuentan, para que el ensayo cuadre.
    plan = {"altas": [], "cambios": [], "bajas": [], "pendientes": [], "sin_cambio": 0,
            "otros": len(leidos) - len(operadores)}
    correos: dict = {}
    for d in operadores:
        if d["correo"]:
            correos.setdefault(d["correo"], []).append(d["odoo_id"])
    vistos = set()
    for d in operadores:
        if d["correo"] and len(correos[d["correo"]]) > 1:
            plan["pendientes"].append({"odoo_id": d["odoo_id"], "nombre": d["nombre"],
                                       "motivo": "su correo lo tiene otro operador en Odoo"})
            d = {**d, "correo": None}
        operador = por_odoo.get(d["odoo_id"])
        if operador is None:
            plan["altas"].append(d)
            continue
        vistos.add(operador.id)
        cambios = {c: [str(getattr(operador, c)) if getattr(operador, c) is not None else None,
                       str(d[c]) if d[c] is not None else None]
                   for c in DE_ODOO_OPERADOR
                   if d[c] is not None and getattr(operador, c) != d[c]}
        if not operador.activo:
            cambios["activo"] = [False, True]
        if cambios:
            plan["cambios"].append({"id": operador.id, "nombre": d["nombre"],
                                    "cambios": cambios, "datos": d})
        else:
            plan["sin_cambio"] += 1
    for o in existentes:
        if o.odoo_id and o.activo and o.id not in vistos:
            plan["bajas"].append({"id": o.id, "nombre": o.nombre})
    return plan


def _leer_operadores(odoo) -> list[dict]:
    return odoo.leer("hr.employee", [["company_id", "=", COMPANIA]], CAMPOS_OPERADOR,
                     compania=COMPANIA)


def aplicar_operadores(db: Session, plan: dict) -> None:
    ahora = _utc()
    for d in plan["altas"]:
        if d["correo"] and db.query(m.LgOperador).filter_by(correo=d["correo"]).first():
            d = {**d, "correo": None}
        db.add(m.LgOperador(odoo_id=d["odoo_id"], nombre=d["nombre"], correo=d["correo"],
                            telefono=d["telefono"], puesto_odoo=d["puesto_odoo"],
                            fecha_ingreso=d["fecha_ingreso"], activo=True,
                            odoo_sincronizado_en=ahora))
    for c in plan["cambios"]:
        operador = db.get(m.LgOperador, c["id"])
        for campo in DE_ODOO_OPERADOR:
            nuevo = c["datos"][campo]
            if nuevo is not None:
                setattr(operador, campo, nuevo)
        if c["cambios"].get("activo"):
            operador.activo, operador.baja_odoo_en = True, None
        operador.odoo_sincronizado_en = ahora
    for b in plan["bajas"]:
        operador = db.get(m.LgOperador, b["id"])
        # Su acceso a LG Connect se cierra con su baja.
        operador.activo, operador.baja_odoo_en = False, ahora
        operador.sesiones_desde = ahora
    db.flush()


# ================================================================ la vuelta

def _registrar(db: Session, tipo: str, plan: dict, leidos: int, quien: m.Usuario | None,
               automatica: bool) -> None:
    db.add(m.SincronizacionOdoo(
        tipo=tipo, automatica=automatica, hecha_por_id=quien.persona_id if quien else None,
        leidos=leidos, altas=len(plan["altas"]), cambios=len(plan["cambios"]),
        bajas=len(plan["bajas"]), pendientes=len(plan["pendientes"]),
        detalle=json.dumps(plan, ensure_ascii=False, default=str)))


def _resumen(plan: dict, leidos: int, ensayo: bool, detenida: bool = False) -> dict:
    return {"ensayo": ensayo, "detenida": detenida, "leidos": leidos,
            "altas": plan["altas"], "cambios": plan["cambios"], "bajas": plan["bajas"],
            "pendientes": plan["pendientes"], "fuera": plan.get("fuera", []),
            "vinculadas": plan.get("vinculadas", []), "sin_cambio": plan["sin_cambio"],
            "otros": plan.get("otros", 0)}


def sincronizar_flota(db: Session, odoo, ensayo: bool = True,
                      quien: m.Usuario | None = None, automatica: bool = False) -> dict:
    # Una lectura a la vez, como las de EP (seccion 100): la de cada hora
    # y la de a mano calcularian las mismas altas.
    if not ensayo:
        odoo_api.candado(db, TIPO_FLOTA)
    leidas = _leer_unidades(odoo)
    existentes = db.query(m.LgUnidad).all()
    plan = planear_unidades(leidas, existentes)
    activos = sum(1 for u in existentes if u.activo and u.odoo_id)
    if not leidas and activos:
        return _resumen(plan, 0, ensayo, detenida=True)
    if not ensayo:
        aplicar_unidades(db, plan)
        _registrar(db, TIPO_FLOTA, plan, len(leidas), quien, automatica)
        if quien and not automatica:
            lg_flota._anotar(db, quien, "lg lectura de odoo", "lg_carga", None,
                             {"k": "lectura", "n": len(plan["altas"])})
        db.commit()
    return _resumen(plan, len(leidas), ensayo)


def sincronizar_operadores(db: Session, odoo, ensayo: bool = True,
                           quien: m.Usuario | None = None, automatica: bool = False) -> dict:
    if not ensayo:
        odoo_api.candado(db, TIPO_OPERADORES)
    leidos = _leer_operadores(odoo)
    existentes = db.query(m.LgOperador).all()
    plan = planear_operadores(leidos, existentes)
    activos = sum(1 for o in existentes if o.activo and o.odoo_id)
    if not any(es_operador(e) for e in leidos) and activos:
        return _resumen(plan, 0, ensayo, detenida=True)
    if not ensayo:
        aplicar_operadores(db, plan)
        _registrar(db, TIPO_OPERADORES, plan, len(leidos), quien, automatica)
        if quien and not automatica:
            lg_flota._anotar(db, quien, "lg lectura de odoo", "lg_operadores", None,
                             {"k": "lectura", "n": len(plan["altas"])})
        db.commit()
    return _resumen(plan, len(leidos), ensayo)


def sincronizar_si_toca(db: Session, odoo=None) -> dict:
    """La tarea de cada hora: solo despues de la primera lectura a mano de
    cada una."""
    salida = {}
    for tipo, funcion in ((TIPO_FLOTA, sincronizar_flota),
                          (TIPO_OPERADORES, sincronizar_operadores)):
        primera = (db.query(m.SincronizacionOdoo)
                   .filter_by(tipo=tipo, automatica=False).first())
        if primera is None:
            salida[tipo] = {"omitido": "falta la primera lectura a mano"}
            continue
        if odoo is None:
            if not odoo_api.hay_conexion():
                return {"omitido": "Odoo no esta conectado"}
            odoo = odoo_api.cliente()
        try:
            r = funcion(db, odoo, ensayo=False, automatica=True)
            salida[tipo] = {k: (len(v) if isinstance(v, list) else v) for k, v in r.items()}
        except odoo_api.NoResponde as error:
            db.rollback()
            registro.warning("odoo no respondio al leer %s: %s", tipo, error)
            salida[tipo] = {"error": str(error)}
    return salida


def ultima(db: Session, tipo: str) -> dict | None:
    fila = (db.query(m.SincronizacionOdoo).filter_by(tipo=tipo)
            .order_by(m.SincronizacionOdoo.hecha_en.desc()).first())
    if not fila:
        return None
    return {"hecha_en": fila.hecha_en.isoformat(), "automatica": fila.automatica,
            "leidos": fila.leidos, "altas": fila.altas, "cambios": fila.cambios,
            "bajas": fila.bajas, "pendientes": fila.pendientes}

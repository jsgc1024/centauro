# -*- coding: utf-8 -*-
"""Logistica (seccion 151): la jornada de los operadores.

Cada operador marca su inicio de jornada en su app, LG Connect, dentro de
la geocerca del patio (300 m), tenga viaje o no. Esa marca dice quien
esta libre para asignar ese dia y cuenta los dias activos de la semana
para el bono de movilidad: 5 de 5, de lunes a viernes.

Fuera de la geocerca puede marcar diciendo donde esta; la marca queda por
validar y la Central la valida o la rechaza con su justificacion, como
corrige las marcas de Proteccion Ejecutiva. Nadie valida sus propias
marcas: el operador no es usuario de la consola.

Un dia que el operador amanece en carretera cuenta como activo: en viaje
no puede marcar en el patio. Mientras los viajes sigan en Tango, ese «en
viaje» se marca a mano, cada viaje en su renglon (`LgViajeManual`); desde
el bloque 4 lo pone el viaje.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import lg_disponibilidad, lg_flota
from app import models as m
from app.operacion import distancia_metros

_no = lg_flota._no
DIAS_DE_LA_SEMANA = 7
LABORABLES = 5
LARGO_JUSTIFICACION = 10
MEXICO = ZoneInfo("America/Mexico_City")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def lunes_de(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def anios_cumplidos(desde: date | None, fecha: date) -> int | None:
    if not desde:
        return None
    anios = fecha.year - desde.year - ((fecha.month, fecha.day) < (desde.month, desde.day))
    return max(anios, 0)


def antiguedad(desde: date | None, fecha: date) -> dict | None:
    """Anos y meses cumplidos, para la pantalla; los anos, para el bono."""
    if not desde:
        return None
    meses = (fecha.year - desde.year) * 12 + fecha.month - desde.month
    if fecha.day < desde.day:
        meses -= 1
    meses = max(meses, 0)
    return {"anios": meses // 12, "meses": meses % 12, "desde": desde.isoformat()}


DIAS_ATRAS = 14
DIAS_MAXIMOS = 60


def viajes_de(db: Session, operador_ids, desde: date | None = None,
              hasta: date | None = None) -> dict:
    """{operador_id: [(desde, hasta), ...]} de sus viajes a mano vivos que
    tocan esas fechas (todos, sin fechas)."""
    consulta = db.query(m.LgViajeManual).filter(
        m.LgViajeManual.operador_id.in_(list(operador_ids) or [0]),
        m.LgViajeManual.quitado_en.is_(None))
    if desde is not None:
        consulta = consulta.filter(m.LgViajeManual.hasta >= desde)
    if hasta is not None:
        consulta = consulta.filter(m.LgViajeManual.desde <= hasta)
    salida: dict = {}
    for v in consulta.order_by(m.LgViajeManual.desde).all():
        salida.setdefault(v.operador_id, []).append((v.desde, v.hasta))
    return salida


def en_viaje(viajes: list, dia: date) -> tuple | None:
    """El viaje a mano en el que iba ese dia, o None."""
    return next(((a, b) for a, b in viajes or [] if a <= dia <= b), None)


# ================================================================ la marca

def patio_mas_cercano(db: Session, lat, lon) -> tuple:
    """(patio, metros) del patio activo con punto mas cercano; (None, None)
    si ningun patio tiene punto todavia."""
    mejor, distancia = None, None
    for patio in db.query(m.LgPatio).filter(m.LgPatio.activo.is_(True)).all():
        if patio.lat is None or patio.lon is None:
            continue
        d = distancia_metros(lat, lon, patio.lat, patio.lon)
        if distancia is None or d < distancia:
            mejor, distancia = patio, d
    return mejor, distancia


def _redondo(valor, paso: str):
    """El GPS del telefono manda quince decimales; aqui se guardan los que
    sirven. Se redondea, no se rechaza: lo que no es numero lo dice
    `_numero`."""
    if isinstance(valor, bool) or valor is None:
        return valor
    try:
        return Decimal(str(valor).strip()).quantize(Decimal(paso), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return valor


def _coordenada(valor, nombre: str, tope: int) -> Decimal:
    # Siete decimales: un centimetro.
    return lg_flota._numero(_redondo(valor, "0.0000001"), nombre, minimo=-tope,
                            maximo=tope, decimales=7)


def marcar(db: Session, operador: m.LgOperador, lat, lon, precision=None,
           nota: str | None = None, fecha: date | None = None) -> m.LgJornada:
    """La marca del dia. Dentro del patio queda valida; fuera, pide donde
    esta y queda por validar con la Central."""
    fecha = fecha or lg_flota.hoy()
    lat = _coordenada(lat, "la latitud", 90)
    lon = _coordenada(lon, "la longitud", 180)
    precision = None if precision in (None, "") else int(
        lg_flota._numero(_redondo(precision, "1"), "la precisión", minimo=0,
                         maximo=100_000))
    ya = db.query(m.LgJornada).filter(m.LgJornada.operador_id == operador.id,
                                      m.LgJornada.fecha == fecha).first()
    if ya:
        hora = ya.marcada_en.astimezone(MEXICO).strftime("%H:%M")
        raise _no({"mensaje": f"Ya marcaste tu jornada hoy a las {hora}.",
                   "que_hacer": "Una marca por día. Si algo salió mal, avísale a "
                                "tu gerente.", "codigo": "ya_marcada"}, 409)
    patio, distancia = patio_mas_cercano(db, lat, lon)
    dentro = bool(patio and distancia is not None and distancia <= patio.geocerca_metros)
    nota = lg_flota._texto(nota, 200)
    if not dentro and patio is not None and (not nota or len(nota) < 3):
        raise _no({"mensaje": f"Estás a {distancia:,} m de {patio.nombre}: fuera del patio.",
                   "que_hacer": "Para marcar tienes que estar dentro del patio. Si de "
                                "veras estás ahí, escribe dónde y la Central revisa tu "
                                "marca.", "codigo": "fuera_del_patio",
                   "distancia_m": distancia, "patio": patio.nombre}, 409)
    jornada = m.LgJornada(
        operador_id=operador.id, fecha=fecha, marcada_en=_ahora(), lat=lat, lon=lon,
        precision_m=precision, patio_id=patio.id if patio else None,
        distancia_m=distancia, dentro=dentro, nota=nota,
        estado="valida" if dentro else "por_validar")
    db.add(jornada)
    db.flush()
    return jornada


def revisar(db: Session, actor: m.Usuario, jornada_id: int, validar: bool,
            justificacion: str) -> m.LgJornada:
    """La Central valida o rechaza una marca fuera del patio, con su
    justificacion."""
    jornada = db.get(m.LgJornada, jornada_id)
    if not jornada:
        raise HTTPException(404, "No existe esa marca")
    if jornada.estado != "por_validar":
        raise _no("Esa marca ya se revisó.", 409)
    justificacion = lg_flota._texto(justificacion, 300)
    if not justificacion or len(justificacion) < LARGO_JUSTIFICACION:
        raise _no({"mensaje": "Falta la justificación.",
                   "que_hacer": "Escribe con qué la revisaste, por ejemplo «llamé al "
                                "patio y el vigilante lo confirma»."})
    jornada.estado = "valida" if validar else "rechazada"
    jornada.revisada_por_id = actor.persona_id
    jornada.revisada_en = _ahora()
    jornada.justificacion = justificacion
    lg_flota._anotar(db, actor, "lg jornada " + ("validada" if validar else "rechazada"),
                     "lg_jornada", jornada.id,
                     {"k": "jornada", "o": jornada.operador.nombre, "f": jornada.fecha,
                      "r": "validada" if validar else "rechazada", "m": justificacion})
    db.flush()
    return jornada


# ================================================================ el viaje a mano

def marcar_en_viaje(db: Session, actor: m.Usuario, operador: m.LgOperador,
                    desde: date | None, hasta: date) -> m.LgViajeManual:
    """Un viaje a mano, mientras los viajes sigan en Tango. Se puede
    anotar el que ya paso --hasta dos semanas atras--: el bono cuenta esos
    dias. No se encima con otro."""
    hoy = lg_flota.hoy()
    desde = desde or hoy
    if hasta < desde:
        raise _no("El regreso es antes de la salida.")
    if desde < hoy - timedelta(days=DIAS_ATRAS):
        raise _no(f"Revisa la salida: se anotan viajes de hasta {DIAS_ATRAS} días atrás.")
    if (hasta - desde).days > DIAS_MAXIMOS:
        raise _no(f"Revisa las fechas: el viaje pasa de {DIAS_MAXIMOS} días.")
    otro = viajes_de(db, [operador.id], desde, hasta).get(operador.id)
    if otro:
        a, b = otro[0]
        raise _no({"mensaje": f"Ya está en viaje del {a.strftime('%d/%m')} al "
                              f"{b.strftime('%d/%m')}.",
                   "que_hacer": "Marca su regreso o ajusta las fechas."}, 409)
    viaje = m.LgViajeManual(operador_id=operador.id, desde=desde, hasta=hasta,
                            creado_por_id=actor.persona_id, creado_en=_ahora())
    db.add(viaje)
    lg_flota._anotar(db, actor, "lg operador en viaje", "lg_operadores", operador.id,
                     {"k": "viaje", "o": operador.nombre, "f": desde, "h": hasta})
    db.flush()
    return viaje


def terminar_viaje(db: Session, actor: m.Usuario, operador: m.LgOperador,
                   regreso: date | None = None) -> int:
    """«Ya regreso»: el viaje en curso termina el ultimo dia que paso en
    carretera --ayer, si no se dice otro-- y el que todavia no empezaba se
    quita. Hoy ya esta de vuelta: puede salir a otro viaje, y para contar
    el dia marca en el patio, como todos."""
    hoy = lg_flota.hoy()
    ayer = hoy - timedelta(days=1)
    regreso = min(regreso or ayer, ayer)
    vivos = (db.query(m.LgViajeManual)
             .filter(m.LgViajeManual.operador_id == operador.id,
                     m.LgViajeManual.quitado_en.is_(None),
                     m.LgViajeManual.hasta >= hoy).all())
    for v in vivos:
        if v.desde > regreso:
            v.quitado_en = _ahora()
        else:
            v.hasta = regreso
    if vivos:
        lg_flota._anotar(db, actor, "lg operador regreso", "lg_operadores", operador.id,
                         {"k": "regreso", "o": operador.nombre, "f": hoy})
    db.flush()
    return len(vivos)


# ================================================================ lo que se ensena

def _marca_dict(j: m.LgJornada | None) -> dict | None:
    if not j:
        return None
    return {"id": j.id, "estado": j.estado, "marcada_en": j.marcada_en.isoformat(),
            "distancia_m": j.distancia_m, "dentro": j.dentro,
            "patio": j.patio.nombre if j.patio else None, "nota": j.nota,
            "precision_m": j.precision_m, "justificacion": j.justificacion,
            "revisada_por": j.revisada_por.nombre if j.revisada_por else None}


def activos(db: Session) -> list[m.LgOperador]:
    return (db.query(m.LgOperador).filter(m.LgOperador.activo.is_(True))
            .order_by(m.LgOperador.nombre).all())


def dia(db: Session, fecha: date | None = None) -> dict:
    """La pestana Hoy: cada operador con su marca, su licencia y si puede
    salir, y las cifras de arriba."""
    hoy = lg_flota.hoy()
    fecha = fecha or hoy
    gente = activos(db)
    ids = [o.id for o in gente]
    marcas = {j.operador_id: j for j in db.query(m.LgJornada).filter(
        m.LgJornada.fecha == fecha, m.LgJornada.operador_id.in_(ids or [0])).all()}
    licencias = lg_flota.vigentes(db, operador_ids=ids)
    viajes = viajes_de(db, ids, min(fecha, hoy))
    cifras = {"operadores": len(gente), "presentes": 0, "en_viaje": 0, "por_validar": 0,
              "rechazadas": 0, "ausentes": 0}
    salida = []
    for o in gente:
        marca = marcas.get(o.id)
        licencia = licencias.get(("o", o.id), {}).get(lg_flota.LICENCIA)
        viaje = en_viaje(viajes.get(o.id), fecha)
        if marca and marca.estado == "valida":
            cifras["presentes"] += 1
            situacion = "presente"
        elif marca and marca.estado == "por_validar":
            cifras["por_validar"] += 1
            situacion = "por_validar"
        elif viaje:
            cifras["en_viaje"] += 1
            situacion = "en_viaje"
        elif marca and marca.estado == "rechazada":
            cifras["rechazadas"] += 1
            situacion = "rechazada"
        else:
            cifras["ausentes"] += 1
            situacion = "ausente"
        renglon = {"id": o.id, "nombre": o.nombre, "puesto": o.puesto_odoo,
                   "antiguedad": antiguedad(o.fecha_ingreso, fecha),
                   "situacion": situacion, "marca": _marca_dict(marca),
                   "en_viaje": {"desde": viaje[0].isoformat(),
                                "hasta": viaje[1].isoformat()} if viaje else None,
                   "licencia": {**lg_flota.estado_documento(licencia, fecha),
                                "detalle": licencia.detalle if licencia else None}}
        if fecha == hoy:
            datos = lg_disponibilidad.datos_operador(
                o, licencia, {hoy: marca.estado} if marca else {}, None, viajes.get(o.id))
            renglon["disponibilidad"] = lg_disponibilidad.evaluar_operador(datos, hoy, hoy, hoy)
        salida.append(renglon)
    return {"fecha": fecha.isoformat(), "hoy": hoy.isoformat(), "operadores": salida,
            "cifras": cifras}


def semana(db: Session, lunes: date | None = None) -> dict:
    """La pestana Semana: cada operador de lunes a domingo y sus dias
    activos de lunes a viernes, que deciden el bono de movilidad."""
    hoy = lg_flota.hoy()
    lunes = lunes_de(lunes or hoy)
    dias = [lunes + timedelta(days=i) for i in range(DIAS_DE_LA_SEMANA)]
    gente = activos(db)
    ids = [o.id for o in gente]
    viajes = viajes_de(db, ids, dias[0], dias[-1])
    marcas: dict = {}
    for j in db.query(m.LgJornada).filter(m.LgJornada.operador_id.in_(ids or [0]),
                                          m.LgJornada.fecha >= dias[0],
                                          m.LgJornada.fecha <= dias[-1]).all():
        marcas[(j.operador_id, j.fecha)] = j.estado
    salida = []
    for o in gente:
        renglon, activos_, pendientes = [], 0, 0
        for i, d in enumerate(dias):
            estado = marcas.get((o.id, d))
            if estado == "valida":
                codigo = "marca"
            elif en_viaje(viajes.get(o.id), d):
                codigo = "viaje"
            elif estado == "por_validar":
                codigo = "por_validar"
            elif estado == "rechazada":
                codigo = "rechazada"
            elif d > hoy:
                codigo = "pendiente"
            else:
                codigo = "falta" if i < LABORABLES else "libre"
            if i < LABORABLES:
                if codigo in ("marca", "viaje"):
                    activos_ += 1
                elif codigo in ("por_validar", "pendiente"):
                    pendientes += 1
            renglon.append({"fecha": d.isoformat(), "codigo": codigo})
        bono = ("si" if activos_ >= LABORABLES
                else "pendiente" if activos_ + pendientes >= LABORABLES else "no")
        salida.append({"id": o.id, "nombre": o.nombre, "dias": renglon,
                       "activos": activos_, "bono": bono})
    return {"lunes": lunes.isoformat(), "hoy": hoy.isoformat(),
            "dias": [d.isoformat() for d in dias], "operadores": salida}


def dias_activos(db: Session, operador_id: int, lunes: date) -> int:
    """Los dias activos de lunes a viernes de esa semana: con su marca
    valida en el patio o en viaje. La nomina (bloque 8) los toma de aqui."""
    o = db.get(m.LgOperador, operador_id)
    if not o:
        return 0
    lunes = lunes_de(lunes)
    viajes = viajes_de(db, [operador_id], lunes,
                       lunes + timedelta(days=LABORABLES - 1)).get(operador_id)
    validas = {j.fecha for j in db.query(m.LgJornada).filter(
        m.LgJornada.operador_id == operador_id, m.LgJornada.estado == "valida",
        m.LgJornada.fecha >= lunes,
        m.LgJornada.fecha < lunes + timedelta(days=LABORABLES)).all()}
    return sum(1 for i in range(LABORABLES)
               if (lunes + timedelta(days=i)) in validas
               or en_viaje(viajes, lunes + timedelta(days=i)))


def por_validar(db: Session) -> list[dict]:
    filas = (db.query(m.LgJornada).filter(m.LgJornada.estado == "por_validar")
             .order_by(m.LgJornada.fecha, m.LgJornada.marcada_en).all())
    return [{**_marca_dict(j), "fecha": j.fecha.isoformat(),
             "operador": {"id": j.operador_id, "nombre": j.operador.nombre}} for j in filas]


def operadores(db: Session, fecha: date | None = None) -> dict:
    """La pestana Operadores: cada uno con su antiguedad, su licencia y su
    acceso a LG Connect."""
    fecha = fecha or lg_flota.hoy()
    gente = (db.query(m.LgOperador)
             .order_by(m.LgOperador.activo.desc(), m.LgOperador.nombre).all())
    ids = [o.id for o in gente]
    licencias = lg_flota.vigentes(db, operador_ids=ids)
    viajes = viajes_de(db, ids, fecha)
    con_huella = {x for (x,) in db.query(m.LgLlave.operador_id).filter(
        m.LgLlave.operador_id.in_(ids or [0])).all()}
    salida = []
    for o in gente:
        licencia = licencias.get(("o", o.id), {}).get(lg_flota.LICENCIA)
        app = ("huella" if o.id in con_huella else
               "contrasena" if o.hash_contrasena else "sin_acceso")
        salida.append({
            "id": o.id, "nombre": o.nombre, "puesto": o.puesto_odoo, "correo": o.correo,
            "activo": o.activo, "baja_odoo_en": lg_flota._iso(o.baja_odoo_en),
            "antiguedad": antiguedad(o.fecha_ingreso, fecha),
            "licencia": {**lg_flota.estado_documento(licencia, fecha),
                         "id": licencia.id if licencia else None,
                         "detalle": licencia.detalle if licencia else None,
                         "folio": licencia.folio if licencia else None,
                         "archivo_id": licencia.archivo_id if licencia else None},
            "app": app, "ultimo_acceso": lg_flota._iso(o.ultimo_acceso),
            # El viaje en curso o el que sigue.
            "en_viaje": ({"desde": viajes[o.id][0][0].isoformat(),
                          "hasta": viajes[o.id][0][1].isoformat()}
                         if viajes.get(o.id) else None)})
    return {"fecha": fecha.isoformat(), "operadores": salida}

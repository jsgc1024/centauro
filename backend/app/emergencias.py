"""Respuesta a emergencias (seccion 145).

El area de guardia 24/7 que atiende los panicos. Llegan tres, y los tres
son la misma alerta (`AlertaIncidencia`), para que nada se atienda dos
veces ni se quede sin atender por estar en otra pantalla:

- el del cliente de la Central de Inteligencia, desde su app: mantiene el
  boton tres segundos y manda donde esta cada quince mientras la alerta
  siga abierta (canal `boton_ci`, nuevo);
- el de la app de campo (`boton_app`), que ademas sigue en el tablero de
  la central, como siempre;
- el del boton de la camioneta, que llega por el GPS (`boton_vehiculo`).

Lo que el area hace queda en `NotaAlerta`, con su hora y quien: tomarla,
el equipo de respuesta, el aviso a las autoridades, sus notas y el
cierre. Tomarla o cerrarla aqui es lo mismo que en la central: los mismos
campos de la alerta, y en el servicio, si lo hay, su misma auditoria.
"""
import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings
from app.riesgo_campo import distancia_km

E = m.EstatusAlerta
C = m.CanalAlerta

# Cada cuanto manda la app su ubicacion mientras la alerta esta abierta, y
# lo menos que se guarda: dos lecturas mas juntas que esto son una.
CADA_SEGUNDOS = 15
MINIMO_ENTRE_PUNTOS = 5
# Un recorrido de horas no cabe en la ficha: se guarda hasta aqui.
MAXIMO_DE_PUNTOS = 2000
EN_LA_FICHA = 240
# Lo que se busca alrededor de quien pidio ayuda.
RIESGO_A_KM = 15
UNIDADES_A_KM = 150
UNIDAD_FRESCA = timedelta(minutes=30)
MINIMO_RESOLUCION = 10


def _ahora(ahora: datetime | None = None) -> datetime:
    return ahora or datetime.now(timezone.utc)


def folio(alerta: m.AlertaIncidencia) -> str:
    return f"E-{alerta.id:04d}"


def telefono() -> str:
    """El telefono del area. Mientras no tenga uno propio, el de la
    Central."""
    return settings.telefono_emergencias or settings.telefono_central


def quien(usuario: m.Usuario | None) -> str:
    if usuario is None:
        return "Connect"
    persona = getattr(usuario, "persona", None)
    return persona.nombre if persona else usuario.correo


def anotar(db: Session, alerta: m.AlertaIncidencia, usuario: m.Usuario | None,
           accion: str, detalle: str = "", ahora: datetime | None = None,
           nombre: str | None = None) -> m.NotaAlerta:
    nota = m.NotaAlerta(alerta_id=alerta.id, en=_ahora(ahora),
                        usuario_id=usuario.id if usuario else None,
                        quien=(nombre or quien(usuario))[:160],
                        accion=accion, detalle=(detalle or "")[:600])
    db.add(nota)
    db.flush()
    return nota


# ============================================================ la ubicacion

def _coordenada(valor, minimo: float, maximo: float) -> float | None:
    try:
        x = float(valor)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and minimo <= x <= maximo else None


def poner_punto(db: Session, alerta: m.AlertaIncidencia, lat, lon,
                precision=None, ahora: datetime | None = None) -> bool:
    """Una lectura mas del recorrido. La ultima queda tambien en la
    alerta, que es lo que leen la central y el panel de un vistazo.
    Devuelve si se guardo."""
    ahora = _ahora(ahora)
    lat = _coordenada(lat, -90, 90)
    lon = _coordenada(lon, -180, 180)
    if lat is None or lon is None:
        return False
    try:
        precision = float(precision)
        precision = (max(0, min(int(precision), 100000))
                     if math.isfinite(precision) else None)
    except (TypeError, ValueError):
        precision = None
    if alerta.ubicacion_en and \
            ahora - alerta.ubicacion_en < timedelta(seconds=MINIMO_ENTRE_PUNTOS):
        return False
    cuantos = (db.query(func.count(m.PuntoAlerta.id))
               .filter_by(alerta_id=alerta.id).scalar() or 0)
    if cuantos >= MAXIMO_DE_PUNTOS:
        # Lo reciente es lo que importa: se va el mas viejo.
        viejo = (db.query(m.PuntoAlerta).filter_by(alerta_id=alerta.id)
                 .order_by(m.PuntoAlerta.id).first())
        db.delete(viejo)
    db.add(m.PuntoAlerta(alerta_id=alerta.id, lat=round(lat, 7),
                         lon=round(lon, 7), precision_m=precision, en=ahora))
    alerta.lat, alerta.lon = round(lat, 7), round(lon, 7)
    alerta.precision_m = precision
    alerta.ubicacion_en = ahora
    db.flush()
    return True


# ================================================ el panico del cliente CI

def abierta_de(db: Session, gente: m.UsuarioCliente) -> m.AlertaIncidencia | None:
    return (db.query(m.AlertaIncidencia)
            .filter(m.AlertaIncidencia.usuario_cliente_id == gente.id,
                    m.AlertaIncidencia.canal == C.BOTON_CI,
                    m.AlertaIncidencia.estatus != E.CERRADA)
            .order_by(m.AlertaIncidencia.id.desc()).first())


def levantar_del_cliente(db: Session, gente: m.UsuarioCliente, lat=None,
                         lon=None, precision=None,
                         ahora: datetime | None = None) -> m.AlertaIncidencia:
    """El boton del cliente. Si ya tiene una abierta, es la misma: apretar
    otra vez (o que la app reintente sin senal) no levanta dos."""
    ahora = _ahora(ahora)
    # Dos pedidos a la vez (la app que reintenta sin senal) no levantan
    # dos: el segundo espera al primero y encuentra su alerta.
    db.query(m.UsuarioCliente).filter_by(id=gente.id).with_for_update().first()
    alerta = abierta_de(db, gente)
    if alerta is None:
        alerta = m.AlertaIncidencia(canal=C.BOTON_CI, usuario_cliente_id=gente.id,
                                    estatus=E.ABIERTA, reportada_en=ahora)
        db.add(alerta)
        db.flush()
        anotar(db, alerta, None, "levanto",
               "Mantuvo el botón de pánico de la app del cliente",
               ahora, nombre=gente.nombre_completo)
    else:
        anotar(db, alerta, None, "otra_vez", "Volvió a apretar el botón",
               ahora, nombre=gente.nombre_completo)
    poner_punto(db, alerta, lat, lon, precision, ahora)
    return alerta


def dijo_error(db: Session, gente: m.UsuarioCliente,
               ahora: datetime | None = None) -> m.AlertaIncidencia:
    """Dice que fue un error. La alerta sigue abierta: alguien del area le
    llama para confirmarlo, porque bajo amenaza tambien se dice."""
    ahora = _ahora(ahora)
    alerta = abierta_de(db, gente)
    if alerta is None:
        raise HTTPException(404, "No tienes una alerta abierta")
    if alerta.dijo_error_en is None:
        alerta.dijo_error_en = ahora
        anotar(db, alerta, None, "dijo_error",
               "Dijo en la app que fue un error", ahora,
               nombre=gente.nombre_completo)
    return alerta


def atiende(db: Session, alerta: m.AlertaIncidencia,
            para_quien_pidio: bool = False) -> str | None:
    """Quien la tomo, como lo dice su bitacora (o la persona de la
    central que la tomo antes de que hubiera bitacora). A quien pidio
    ayuda no se le dice un correo interno: si quien la tomo no tiene su
    ficha de persona, solo que ya la atienden."""
    nota = (db.query(m.NotaAlerta)
            .filter_by(alerta_id=alerta.id, accion="tomo")
            .order_by(m.NotaAlerta.id.desc()).first())
    nombre = nota.quien if nota else None
    if nombre is None and alerta.tomada_por_id:
        persona = db.get(m.Persona, alerta.tomada_por_id)
        nombre = persona.nombre if persona else None
    if para_quien_pidio and nombre and "@" in nombre:
        return None
    return nombre


def vista_del_cliente(db: Session, alerta: m.AlertaIncidencia | None) -> dict:
    """Lo que ve en su app quien aprieto el boton: que llego, quien lo
    atiende y a donde llamar. Nada de la bitacora del area."""
    if alerta is None:
        return {"abierta": False, "telefono": telefono(),
                "cada_segundos": CADA_SEGUNDOS}
    return {"abierta": alerta.estatus != E.CERRADA, "id": alerta.id,
            "estatus": alerta.estatus.value,
            "recibida_en": alerta.reportada_en.isoformat(),
            "atiende": atiende(db, alerta, para_quien_pidio=True),
            "atendida": alerta.estatus == E.EN_ATENCION,
            "dijo_error": alerta.dijo_error_en is not None,
            "ubicacion_en": (alerta.ubicacion_en.isoformat()
                             if alerta.ubicacion_en else None),
            "precision_m": alerta.precision_m,
            "lat": float(alerta.lat) if alerta.lat is not None else None,
            "lon": float(alerta.lon) if alerta.lon is not None else None,
            "llave_mapa": settings.google_maps_key_navegador or None,
            "telefono": telefono(), "cada_segundos": CADA_SEGUNDOS}


# ============================================================ el panel

def alerta_de(db: Session, alerta_id: int) -> m.AlertaIncidencia:
    alerta = db.get(m.AlertaIncidencia, alerta_id)
    if not alerta:
        raise HTTPException(404, "No existe esa alerta")
    return alerta


def _servicio(db: Session, alerta: m.AlertaIncidencia) -> m.Servicio | None:
    if alerta.servicio_id:
        return db.get(m.Servicio, alerta.servicio_id)
    if alerta.jornada_id:
        jornada = db.get(m.Jornada, alerta.jornada_id)
        if jornada:
            return jornada.equipo.servicio
    return None


def _quien_pidio(db: Session, alerta: m.AlertaIncidencia) -> dict:
    """Quien pidio ayuda y de que: su nombre, su telefono y lo que lo
    ubica (el cliente, el servicio o la unidad)."""
    if alerta.canal == C.BOTON_CI:
        g = alerta.usuario_cliente
        return {"nombre": g.nombre_completo if g else "—",
                "telefono": g.telefono if g else None,
                "de": g.cliente_central.cliente.nombre if g else None}
    servicio = _servicio(db, alerta)
    unidad = alerta.vehiculo.placa if alerta.vehiculo else None
    if alerta.reporta:
        return {"nombre": alerta.reporta.nombre,
                "telefono": alerta.reporta.telefono,
                "de": servicio.folio if servicio else unidad}
    return {"nombre": unidad or "—", "telefono": None,
            "de": servicio.folio if servicio else None}


def renglon(db: Session, alerta: m.AlertaIncidencia, ahora: datetime) -> dict:
    pidio = _quien_pidio(db, alerta)
    return {
        "id": alerta.id, "folio": folio(alerta), "canal": alerta.canal.value,
        "estatus": alerta.estatus.value,
        "quien": pidio["nombre"], "de": pidio["de"],
        "reportada_en": alerta.reportada_en.isoformat(),
        "segundos": max(0, int((ahora - alerta.reportada_en).total_seconds())),
        "atiende": atiende(db, alerta),
        "dijo_error": alerta.dijo_error_en is not None,
        "lat": float(alerta.lat) if alerta.lat is not None else None,
        "lon": float(alerta.lon) if alerta.lon is not None else None,
        # La del vehiculo y la de antes de esta seccion no la anotaban:
        # su ubicacion es de cuando se levanto.
        "ubicacion_en": ((alerta.ubicacion_en or alerta.reportada_en).isoformat()
                         if alerta.lat is not None else None),
    }


def panel(db: Session, ahora: datetime | None = None) -> dict:
    """Lo activo --primero lo que nadie ha tomado, lo mas viejo arriba--
    y como va el dia."""
    ahora = _ahora(ahora)
    activas = (db.query(m.AlertaIncidencia)
               .filter(m.AlertaIncidencia.estatus != E.CERRADA)
               .order_by(m.AlertaIncidencia.reportada_en).all())
    activas.sort(key=lambda a: a.estatus != E.ABIERTA)
    desde = ahora - timedelta(hours=24)
    del_dia = (db.query(m.AlertaIncidencia)
               .filter(m.AlertaIncidencia.reportada_en >= desde).all())
    # Cuando se tomo cada una, en una sola consulta.
    tomas = dict(db.query(m.NotaAlerta.alerta_id, func.min(m.NotaAlerta.en))
                 .filter(m.NotaAlerta.alerta_id.in_([a.id for a in del_dia]),
                         m.NotaAlerta.accion == "tomo")
                 .group_by(m.NotaAlerta.alerta_id).all()) if del_dia else {}
    tiempos = [max(0, int((tomas[a.id] - a.reportada_en).total_seconds()))
               for a in del_dia if a.id in tomas]
    return {
        "activas": [renglon(db, a, ahora) for a in activas],
        "sin_tomar": sum(1 for a in activas if a.estatus == E.ABIERTA),
        "dia": {"total": len(del_dia),
                "cerradas": sum(1 for a in del_dia if a.estatus == E.CERRADA),
                "para_tomar_s": (round(sum(tiempos) / len(tiempos))
                                 if tiempos else None)},
        "telefono": telefono(),
    }


def _riesgo_cerca(db: Session, lat: float, lon: float,
                  ahora: datetime) -> list[dict]:
    eventos = (db.query(m.EventoRiesgo)
               .filter(m.EventoRiesgo.estado == m.EstadoEvento.PUBLICADO,
                       m.EventoRiesgo.vigente_hasta > ahora,
                       m.EventoRiesgo.lat.isnot(None)).all())
    cerca = []
    for e in eventos:
        km = distancia_km(lat, lon, float(e.lat), float(e.lon))
        km = max(0.0, km - (e.radio_m or 0) / 1000)
        if km <= RIESGO_A_KM:
            cerca.append({"id": e.id, "folio": e.folio, "nivel": e.nivel,
                          "titulo": e.titulo, "km": round(km, 1)})
    return sorted(cerca, key=lambda x: (-x["nivel"], x["km"]))[:5]


def _unidades_cerca(db: Session, lat: float, lon: float,
                    ahora: datetime) -> list[dict]:
    """Las unidades con GPS que reportaron hace poco, por distancia. Solo
    cuantos kilometros y cual: el panel no es un rastreo de la flota."""
    filas = (db.query(m.UnidadGps)
             .filter(m.UnidadGps.en_el_grupo.is_(True),
                     m.UnidadGps.lat.isnot(None),
                     m.UnidadGps.reporte_en >= ahora - UNIDAD_FRESCA).all())
    cerca = []
    for u in filas:
        km = distancia_km(lat, lon, float(u.lat), float(u.lon))
        if km <= UNIDADES_A_KM:
            cerca.append({"placa": (u.vehiculo.placa if u.vehiculo
                                    else u.placa),
                          "km": round(km, 1),
                          "hace_min": int((ahora - u.reporte_en)
                                          .total_seconds() // 60)})
    return sorted(cerca, key=lambda x: x["km"])[:3]


def _contactos(db: Session, alerta: m.AlertaIncidencia) -> list[dict]:
    """A quien mas llamar: el contacto de emergencia del cliente de la
    Central, o el consultor del servicio."""
    if alerta.canal == C.BOTON_CI:
        g = alerta.usuario_cliente
        cc = g.cliente_central if g else None
        if cc and (cc.contacto_emergencia or cc.telefono_emergencia):
            return [{"nombre": cc.contacto_emergencia or "—",
                     "telefono": cc.telefono_emergencia,
                     "que": "cliente"}]
        return []
    servicio = _servicio(db, alerta)
    if servicio and servicio.consultor_id:
        consultor = db.get(m.Persona, servicio.consultor_id)
        if consultor:
            return [{"nombre": consultor.nombre,
                     "telefono": consultor.telefono, "que": "consultor"}]
    return []


def _bitacora(db: Session, alerta: m.AlertaIncidencia) -> list[dict]:
    notas = (db.query(m.NotaAlerta).filter_by(alerta_id=alerta.id)
             .order_by(m.NotaAlerta.en, m.NotaAlerta.id).all())
    salida = [{"en": n.en.isoformat(), "quien": n.quien,
               "accion": n.accion, "detalle": n.detalle} for n in notas]
    if not any(n.accion == "levanto" for n in notas):
        # Las de la app de campo y del vehiculo no se anotan al nacer:
        # su primer renglon sale de la alerta misma.
        pidio = _quien_pidio(db, alerta)
        salida.insert(0, {"en": alerta.reportada_en.isoformat(),
                          "quien": pidio["nombre"], "accion": "levanto",
                          "detalle": alerta.descripcion or ""})
    return salida


def ficha(db: Session, alerta: m.AlertaIncidencia,
          ahora: datetime | None = None) -> dict:
    ahora = _ahora(ahora)
    datos = renglon(db, alerta, ahora)
    pidio = _quien_pidio(db, alerta)
    puntos = (db.query(m.PuntoAlerta).filter_by(alerta_id=alerta.id)
              .order_by(m.PuntoAlerta.en.desc()).limit(EN_LA_FICHA).all())
    datos.update({
        "telefono_de_quien": pidio["telefono"],
        "precision_m": alerta.precision_m,
        "descripcion": alerta.descripcion,
        "resolucion": alerta.resolucion,
        "equipo_enviado": bool(alerta.equipo_respuesta_enviado),
        "autoridades": alerta.autoridades_en is not None,
        "puntos": [{"lat": float(p.lat), "lon": float(p.lon),
                    "en": p.en.isoformat()} for p in reversed(puntos)],
        "contactos": _contactos(db, alerta),
        "bitacora": _bitacora(db, alerta),
        "riesgo_cerca": [], "unidades_cerca": [],
    })
    if alerta.lat is not None:
        lat, lon = float(alerta.lat), float(alerta.lon)
        datos["riesgo_cerca"] = _riesgo_cerca(db, lat, lon, ahora)
        datos["unidades_cerca"] = _unidades_cerca(db, lat, lon, ahora)
    return datos


# ========================================================= lo que hace el area

def _abierta(alerta: m.AlertaIncidencia) -> None:
    if alerta.estatus == E.CERRADA:
        raise HTTPException(409, "Esa alerta ya está cerrada")


def _auditar(db: Session, usuario: m.Usuario, alerta: m.AlertaIncidencia,
             que: str, detalle: str = "") -> None:
    """En el servicio, si lo hay, lo mismo que deja la central."""
    from app import auditoria
    servicio = _servicio(db, alerta)
    if servicio:
        auditoria.registrar(db, usuario, servicio, que, detalle,
                            jornada_id=alerta.jornada_id)


def tomar(db: Session, usuario: m.Usuario, alerta: m.AlertaIncidencia,
          ahora: datetime | None = None) -> m.AlertaIncidencia:
    _abierta(alerta)
    if alerta.estatus == E.EN_ATENCION:
        raise HTTPException(409, {
            "mensaje": f"Ya la atiende {atiende(db, alerta) or 'alguien'}",
            "que_hacer": "Recarga el panel."})
    alerta.estatus = E.EN_ATENCION
    alerta.tomada_por_id = usuario.persona_id
    # La columna de la central es sin zona (la hora del servidor), como
    # la escribe ella.
    alerta.tomada_en = datetime.now()
    anotar(db, alerta, usuario, "tomo", "", ahora)
    _auditar(db, usuario, alerta, "alerta tomada por respuesta a emergencias")
    return alerta


def _tomada(db: Session, alerta: m.AlertaIncidencia) -> None:
    _abierta(alerta)
    if alerta.estatus == E.ABIERTA:
        raise HTTPException(409, {"mensaje": "Primero hay que tomarla",
                                  "que_hacer": "Toma la alerta y luego "
                                               "anota lo que se hizo."})


def mandar_equipo(db: Session, usuario: m.Usuario, alerta: m.AlertaIncidencia,
                  nota: str = "", ahora: datetime | None = None):
    _tomada(db, alerta)
    ahora = _ahora(ahora)
    alerta.equipo_respuesta_enviado = True
    alerta.equipo_enviado_en = ahora
    anotar(db, alerta, usuario, "equipo", nota, ahora)
    _auditar(db, usuario, alerta, "equipo de respuesta enviado", nota[:120])
    return alerta


def avisar_autoridades(db: Session, usuario: m.Usuario,
                       alerta: m.AlertaIncidencia, nota: str = "",
                       ahora: datetime | None = None):
    _tomada(db, alerta)
    ahora = _ahora(ahora)
    alerta.autoridades_en = ahora
    anotar(db, alerta, usuario, "autoridades", nota, ahora)
    return alerta


def poner_nota(db: Session, usuario: m.Usuario, alerta: m.AlertaIncidencia,
               texto: str, ahora: datetime | None = None):
    _abierta(alerta)
    texto = (texto or "").strip()
    if len(texto) < 3:
        raise HTTPException(400, "Escribe la nota")
    anotar(db, alerta, usuario, "nota", texto, ahora)
    return alerta


def cerrar(db: Session, usuario: m.Usuario, alerta: m.AlertaIncidencia,
           resolucion: str, ahora: datetime | None = None):
    _tomada(db, alerta)
    resolucion = (resolucion or "").strip()
    if len(resolucion) < MINIMO_RESOLUCION:
        raise HTTPException(400, {
            "mensaje": "Falta la resolución",
            "que_hacer": f"Qué pasó y cómo terminó, en al menos "
                         f"{MINIMO_RESOLUCION} letras."})
    alerta.estatus = E.CERRADA
    alerta.resolucion = resolucion[:600]
    alerta.cerrada_por_id = usuario.persona_id
    alerta.cerrada_en = datetime.now()
    anotar(db, alerta, usuario, "cerro", resolucion, ahora)
    _auditar(db, usuario, alerta, "alerta cerrada", resolucion[:120])
    return alerta

"""El riesgo cerca del servicio, en la app de campo (seccion 137).

Lo que la Central de Inteligencia publica tambien le sirve al equipo que
esta en la calle. La regla, aprobada por Salvador el 2 de octubre sobre
los bocetos:

- **En la tarjeta de Hoy:** lo publicado y vigente de nivel 2 o mas a
  menos de 25 km del punto de encuentro de su servicio de hoy.
- **Al telefono:** solo el 3 y el 4, cuando se publica o sube de nivel.
  Uno por evento, persona y nivel.

La distancia es del punto de encuentro a la orilla del circulo del
evento: un bloqueo de 2 km de radio a 6 km del hotel esta a 4 km. Un
evento sin punto --de todo el estado-- no tiene distancia y no entra:
el equipo no puede hacer nada con "algo en Tamaulipas". Un dia sin punto
capturado tampoco: no hay de donde medir. Connect no guarda el destino
del servicio, asi que se mide solo desde el punto de encuentro.
"""
import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m
from app import push, reloj

RADIO_KM = 25
NIVEL_TARJETA = 2
NIVEL_AVISO = 3

TEXTOS = {
    "es": {"titulo": "Riesgo nivel {n} cerca de tu servicio",
           "cuerpo": "{titulo} · a {km} km del punto de encuentro de {folio}."},
    "pt": {"titulo": "Risco nível {n} perto do seu serviço",
           "cuerpo": "{titulo} · a {km} km do ponto de encontro de {folio}."},
    "en": {"titulo": "Level {n} risk near your service",
           "cuerpo": "{titulo} · {km} km from the meeting point of {folio}."},
}


def _ahora(ahora: datetime | None) -> datetime:
    return ahora or datetime.now(timezone.utc)


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine: en linea recta sobre la Tierra, en kilometros."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def _km(evento: m.EventoRiesgo, jornada: m.Jornada) -> float | None:
    if evento.lat is None or jornada.origen_lat is None:
        return None
    centro = distancia_km(float(evento.lat), float(evento.lon),
                          float(jornada.origen_lat), float(jornada.origen_lon))
    return max(0.0, centro - (evento.radio_m or 0) / 1000)


def _vigentes(db: Session, nivel_minimo: int,
              ahora: datetime) -> list[m.EventoRiesgo]:
    return (db.query(m.EventoRiesgo)
            .filter(m.EventoRiesgo.estado == m.EstadoEvento.PUBLICADO,
                    m.EventoRiesgo.vigente_hasta > ahora,
                    m.EventoRiesgo.nivel >= nivel_minimo,
                    m.EventoRiesgo.lat.isnot(None))
            .all())


def _local(instante: datetime | None, evento: m.EventoRiesgo) -> str | None:
    if instante is None:
        return None
    return instante.astimezone(
        reloj.zona(evento.pais.zona_horaria)).isoformat()


def vista(evento: m.EventoRiesgo, km: float, jornada: m.Jornada | None,
          ahora: datetime | None = None) -> dict:
    """Lo que el analista escribio para quien esta afuera. Como al
    cliente: nunca las fuentes ni la bitacora."""
    ahora = _ahora(ahora)
    return {
        "id": evento.id, "folio": evento.folio, "nivel": evento.nivel,
        "titulo": evento.titulo, "texto": evento.texto_cliente,
        "tipo": evento.tipo.nombre, "region": evento.region.nombre,
        "municipio": evento.municipio, "lugar": evento.lugar,
        "lat": float(evento.lat) if evento.lat is not None else None,
        "lon": float(evento.lon) if evento.lon is not None else None,
        "ocurrio_en": _local(evento.ocurrio_en, evento),
        "vigente_hasta": _local(evento.vigente_hasta, evento),
        "vigente": (evento.estado == m.EstadoEvento.PUBLICADO
                    and evento.vigente_hasta > ahora),
        "verificacion": evento.verificacion.value,
        "km": round(km, 1),
        "servicio": (jornada.equipo.servicio.folio
                     if jornada and jornada.equipo else None),
        "jornada_id": jornada.id if jornada else None,
    }


def cerca_de(db: Session, jornadas: list[m.Jornada],
             ahora: datetime | None = None) -> list[dict]:
    """Para la tarjeta de Hoy: lo vigente de nivel 2 o mas a menos de
    25 km del punto de alguno de sus dias. Cada evento una vez, con el
    dia que le queda mas cerca. Lo mas grave primero, luego lo mas
    cerca."""
    ahora = _ahora(ahora)
    con_punto = [j for j in jornadas if j.origen_lat is not None]
    if not con_punto:
        return []
    salida = []
    for evento in _vigentes(db, NIVEL_TARJETA, ahora):
        medidas = [(_km(evento, j), j) for j in con_punto]
        medidas = [(km, j) for km, j in medidas
                   if km is not None and km <= RADIO_KM]
        if not medidas:
            continue
        km, jornada = min(medidas, key=lambda x: x[0])
        salida.append(vista(evento, km, jornada, ahora))
    salida.sort(key=lambda e: (-e["nivel"], e["km"]))
    return salida


def del_dia(db: Session, persona_id: int, evento_id: int,
            jornadas: list[m.Jornada], ahora: datetime | None = None) -> dict:
    """El detalle, solo si le toca: cerca de su servicio de hoy, o uno
    que ya le llego al telefono."""
    evento = db.get(m.EventoRiesgo, evento_id)
    if evento and evento.estado in (m.EstadoEvento.PUBLICADO,
                                    m.EstadoEvento.CERRADO):
        medidas = [(_km(evento, j), j) for j in jornadas]
        medidas = [(km, j) for km, j in medidas if km is not None]
        cerca = [x for x in medidas if x[0] <= RADIO_KM]
        if cerca:
            km, jornada = min(cerca, key=lambda x: x[0])
            return vista(evento, km, jornada, ahora)
        aviso = (db.query(m.AvisoRiesgoCampo)
                 .filter_by(evento_id=evento_id, persona_id=persona_id)
                 .order_by(m.AvisoRiesgoCampo.id.desc()).first())
        if aviso:
            jornada = db.get(m.Jornada, aviso.jornada_id) \
                if aviso.jornada_id else None
            return vista(evento, float(aviso.km), jornada, ahora)
    raise HTTPException(404, "Ese evento no está cerca de tu servicio")


def _jornadas_del_dia(db: Session, evento: m.EventoRiesgo,
                      ahora: datetime) -> list[m.Jornada]:
    """Los dias que estan corriendo o por correr hoy, en el pais del
    evento, con punto capturado. Y los de ayer que siguen en la calle."""
    hoy = ahora.astimezone(reloj.zona(evento.pais.zona_horaria)).date()
    terminados = (m.EstatusJornada.TERMINADA, m.EstatusJornada.CANCELADA)
    de_hoy = (db.query(m.Jornada)
              .filter(m.Jornada.fecha == hoy,
                      m.Jornada.estatus.notin_(terminados),
                      m.Jornada.origen_lat.isnot(None)).all())
    de_ayer = (db.query(m.Jornada)
               .filter(m.Jornada.fecha == hoy - timedelta(days=1),
                       m.Jornada.estatus.in_(m.ARRANCADAS),
                       m.Jornada.origen_lat.isnot(None)).all())
    return de_hoy + de_ayer


def al_publicar(db: Session, evento: m.EventoRiesgo, motivo: str,
                ahora: datetime | None = None) -> dict:
    """Lo llama `riesgo` cuando un evento se publica o sube de nivel: el
    3 y el 4 llegan al telefono de quien trabaja hoy cerca."""
    ahora = _ahora(ahora)
    if evento.nivel < NIVEL_AVISO or evento.lat is None:
        return {"personas": 0, "telefonos": 0}
    # Por persona, el dia que le queda mas cerca.
    cerca: dict[int, tuple[float, m.Jornada]] = {}
    for jornada in _jornadas_del_dia(db, evento, ahora):
        km = _km(evento, jornada)
        if km is None or km > RADIO_KM:
            continue
        for asignacion in jornada.personal:
            if asignacion.relevado_en is not None or not asignacion.persona_id:
                continue
            previo = cerca.get(asignacion.persona_id)
            if previo is None or km < previo[0]:
                cerca[asignacion.persona_id] = (km, jornada)

    personas, telefonos = 0, 0
    for persona_id, (km, jornada) in sorted(cerca.items()):
        ya = (db.query(m.AvisoRiesgoCampo)
              .filter_by(evento_id=evento.id, persona_id=persona_id,
                         nivel=evento.nivel).first())
        if ya:
            continue
        lengua = push.idioma_de(db, persona_id)
        t = TEXTOS.get(lengua) or TEXTOS["es"]
        folio = jornada.equipo.servicio.folio if jornada.equipo else ""
        salida = push.avisar(
            db, persona_id, t["titulo"].format(n=evento.nivel),
            t["cuerpo"].format(titulo=evento.titulo, km=f"{km:.0f}",
                               folio=folio)[:240],
            url=f"/app/#/riesgo/{evento.id}", etiqueta=f"riesgo-{evento.id}",
            urgente=True)
        db.add(m.AvisoRiesgoCampo(
            evento_id=evento.id, persona_id=persona_id, jornada_id=jornada.id,
            nivel=evento.nivel, km=round(km, 1),
            telefonos=salida.get("enviados", 0)))
        personas += 1
        telefonos += salida.get("enviados", 0)

    if personas:
        from app import riesgo
        riesgo._anotar(db, evento, None, "aviso_campo",
                       f"Nivel {evento.nivel}: {personas} persona(s) del "
                       f"personal de seguridad cerca, {telefonos} teléfono(s)")
    return {"personas": personas, "telefonos": telefonos}

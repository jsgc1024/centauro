"""El evento de riesgo: la pieza de la Central de Inteligencia (seccion 130).

Un evento es algo que paso en un lugar y a una hora, y que cambia el
riesgo de quien pase por ahi. Su vida tiene pocas puertas, y aqui se
cuida cada una:

  propuesto ──publicar──▶ publicado ──cerrar / vence──▶ cerrado
      │  ╲                    ▲
      │   ╲ nivel 4           │ confirma el jefe de turno
      │    ▶ por_confirmar ───┘
      └──descartar──▶ descartado

Tres reglas sostienen todo lo demas:

1. **Nada llega al cliente sin que un analista lo publique.** Lo que
   propone el lector automatico (fase 2) nace igual que lo que captura
   un analista: propuesto, y solo la central lo ve.
2. **El nivel 4 lo confirma otra persona** (decision de Salvador, 2 oct):
   el jefe de turno, y nunca quien lo pidio. Un evento ya publicado que
   sube a 4 sigue en su nivel mientras tanto: el 4 espera en
   `nivel_pendiente`, para que la alerta critica no salga sin la segunda
   firma pero el cliente tampoco deje de ver lo que ya veia.
3. **Todo evento tiene vigencia.** Sin ella, el mapa se llena de lo que
   paso hace un mes; con ella, el reloj lo cierra solo.

La verificacion no la escoge el analista: sale de las fuentes. Una sola,
sin confirmar; dos o mas, confirmado; una oficial, oficial. Asi el
cliente puede creerle a la etiqueta.

Quien recibe la alerta lo decide el modulo de alertas (seccion 131), que
se cuelga de `AL_PUBLICAR`: aqui solo se dice cuando un evento empieza a
ser publico o sube de nivel.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app import reloj

E = m.EstadoEvento
NIVELES = {1: "Informativo", 2: "Precaución", 3: "Alto", 4: "Crítico"}
MINIMO_MOTIVO = 10
# La vigencia mas larga que se acepta. Un evento de mas de 30 dias deja
# de ser un evento y se vuelve riesgo de fondo, que va por otro lado.
VIGENCIA_MAXIMA = timedelta(days=30)

# Lo que se hace cuando un evento empieza a verse o sube de nivel:
# f(db, evento, motivo) con motivo "nuevo" o "sube". Lo llena el modulo
# de alertas al importarse.
AL_PUBLICAR: list = []


def _ahora(ahora: datetime | None) -> datetime:
    return ahora or datetime.now(timezone.utc)


def _quien(usuario: m.Usuario | None) -> str:
    if usuario is None:
        return "El sistema"
    persona = getattr(usuario, "persona", None)
    return persona.nombre if persona else usuario.correo


def _anotar(db: Session, evento: m.EventoRiesgo, usuario: m.Usuario | None,
            accion: str, detalle: str = "") -> None:
    db.add(m.CambioEvento(evento_id=evento.id,
                          usuario_id=usuario.id if usuario else None,
                          quien=_quien(usuario), accion=accion,
                          detalle=detalle[:2000]))


def _motivo(motivo: str | None, que: str) -> str:
    motivo = (motivo or "").strip()
    if len(motivo) < MINIMO_MOTIVO:
        raise HTTPException(400, {
            "mensaje": f"Falta decir por qué se {que}",
            "que_hacer": f"Escribe al menos {MINIMO_MOTIVO} letras: queda "
                         "en la bitácora del evento."})
    return motivo[:400]


def _instante(valor, pais: m.Pais) -> datetime:
    """Una hora que llega como texto o como datetime. Sin zona, es la hora
    del pais del evento: la central captura en su reloj."""
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor)
        except ValueError:
            raise HTTPException(400, f"No entiendo la hora «{valor}»")
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=reloj.zona(pais.zona_horaria))
    return valor.astimezone(timezone.utc)


def _folio_siguiente(db: Session) -> str:
    ultimo = db.scalar(select(func.max(m.EventoRiesgo.id))) or 0
    numero = ultimo + 1
    while db.scalar(select(m.EventoRiesgo.id).where(
            m.EventoRiesgo.folio == f"CI-{numero:04d}")):
        numero += 1
    return f"CI-{numero:04d}"


def _verificacion(evento: m.EventoRiesgo) -> m.VerificacionEvento:
    if any(f.oficial for f in evento.fuentes):
        return m.VerificacionEvento.OFICIAL
    if len(evento.fuentes) >= 2:
        return m.VerificacionEvento.CONFIRMADO
    return m.VerificacionEvento.SIN_CONFIRMAR


# ----------------------------------------------------------- lectura

def evento_de(db: Session, evento_id: int) -> m.EventoRiesgo:
    evento = db.get(m.EventoRiesgo, evento_id)
    if not evento:
        raise HTTPException(404, f"No existe el evento {evento_id}")
    return evento


def vigente(evento: m.EventoRiesgo, ahora: datetime | None = None) -> bool:
    return (evento.estado == E.PUBLICADO
            and evento.vigente_hasta > _ahora(ahora))


def _local(instante: datetime | None, pais: m.Pais) -> str | None:
    """Las horas salen en la del pais del evento: un bloqueo en Reynosa
    se lee a la hora de Reynosa, este quien este mirando."""
    if instante is None:
        return None
    return instante.astimezone(reloj.zona(pais.zona_horaria)).isoformat()


def vista(evento: m.EventoRiesgo, completa: bool = True) -> dict:
    """Lo que ve la central. La del cliente es otra, mas corta, y no
    lleva quien lo capturo ni las fuentes que no son publicas."""
    pais = evento.pais
    datos = {
        "id": evento.id, "folio": evento.folio,
        "pais": evento.pais.codigo, "pais_id": evento.pais_id,
        "region_id": evento.region_id, "region": evento.region.nombre,
        "municipio": evento.municipio,
        "tipo_id": evento.tipo_id, "tipo": evento.tipo.nombre,
        "nivel": evento.nivel, "nivel_nombre": NIVELES[evento.nivel],
        "nivel_pendiente": evento.nivel_pendiente,
        "titulo": evento.titulo, "texto_cliente": evento.texto_cliente,
        "lat": float(evento.lat) if evento.lat is not None else None,
        "lon": float(evento.lon) if evento.lon is not None else None,
        "radio_m": evento.radio_m, "lugar": evento.lugar,
        "ocurrio_en": _local(evento.ocurrio_en, pais),
        "vigente_hasta": _local(evento.vigente_hasta, pais),
        "verificacion": evento.verificacion.value,
        "tendencia": evento.tendencia.value if evento.tendencia else None,
        "estado": evento.estado.value, "origen": evento.origen,
        "publicado_en": _local(evento.publicado_en, pais),
        "actualizado_en": _local(evento.actualizado_en, pais),
    }
    if completa:
        datos["fuentes"] = [{"id": f.id, "url": f.url,
                             "descripcion": f.descripcion,
                             "oficial": f.oficial} for f in evento.fuentes]
        datos["motivo"] = evento.motivo
        datos["critico_pedido_por_id"] = evento.critico_pedido_por_id
    return datos


def bitacora(db: Session, evento: m.EventoRiesgo) -> list[dict]:
    filas = (db.query(m.CambioEvento).filter_by(evento_id=evento.id)
             .order_by(m.CambioEvento.id).all())
    return [{"en": c.en.isoformat(), "quien": c.quien, "accion": c.accion,
             "detalle": c.detalle} for c in filas]


def del_mapa(db: Session, pais_id: int | None = None,
             ahora: datetime | None = None,
             con_trabajo: bool = True) -> dict:
    """Lo vigente para el mapa, y la cola del analista aparte.

    La cola es lo que espera una mano: lo propuesto y lo que espera al
    jefe de turno. Va primero lo critico.
    """
    ahora = _ahora(ahora)
    q = db.query(m.EventoRiesgo)
    if pais_id:
        q = q.filter(m.EventoRiesgo.pais_id == pais_id)
    publicados = (q.filter(m.EventoRiesgo.estado == E.PUBLICADO,
                           m.EventoRiesgo.vigente_hasta > ahora)
                  .order_by(m.EventoRiesgo.nivel.desc(),
                            m.EventoRiesgo.ocurrio_en.desc()).all())
    salida = {"publicados": [vista(e, completa=False) for e in publicados]}
    if con_trabajo:
        pendientes = (q.filter(m.EventoRiesgo.estado.in_(
            [E.PROPUESTO, E.POR_CONFIRMAR])).all())
        subiendo = [e for e in publicados if e.nivel_pendiente]
        cola = sorted(pendientes + subiendo,
                      key=lambda e: (e.estado != E.POR_CONFIRMAR
                                     and not e.nivel_pendiente,
                                     -e.nivel, e.creado_en))
        salida["cola"] = [vista(e) for e in cola]
    return salida


# ----------------------------------------------------------- escritura

CAMPOS = ("region_id", "municipio", "tipo_id", "nivel", "titulo",
          "texto_cliente", "lat", "lon", "radio_m", "lugar", "ocurrio_en",
          "vigente_hasta", "tendencia")


def _aplicar(db: Session, evento: m.EventoRiesgo, datos: dict,
             pais: m.Pais) -> list[str]:
    """Pone los datos que llegaron y dice cuales cambiaron. Valida todo
    antes de tocar nada."""
    nuevos = {k: datos[k] for k in CAMPOS if k in datos}

    if "region_id" in nuevos:
        region = db.get(m.Region, nuevos["region_id"])
        if not region or region.pais_id != pais.id or not region.activo:
            raise HTTPException(400, "Ese estado no es de este país")
    if "tipo_id" in nuevos:
        tipo = db.get(m.TipoEvento, nuevos["tipo_id"])
        if not tipo or tipo.pais_id != pais.id or not tipo.activo:
            raise HTTPException(400, "Ese tipo de evento no es de este país")
    if "nivel" in nuevos and nuevos["nivel"] not in NIVELES:
        raise HTTPException(400, "El nivel va del 1 (Informativo) al 4 "
                                 "(Crítico)")
    if "titulo" in nuevos:
        nuevos["titulo"] = (nuevos["titulo"] or "").strip()[:160]
        if len(nuevos["titulo"]) < 5:
            raise HTTPException(400, "Falta el título: qué pasó, en pocas "
                                     "palabras")
    for clave in ("ocurrio_en", "vigente_hasta"):
        if clave in nuevos and nuevos[clave] is not None:
            nuevos[clave] = _instante(nuevos[clave], pais)
    if "tendencia" in nuevos and nuevos["tendencia"]:
        try:
            nuevos["tendencia"] = m.TendenciaEvento(nuevos["tendencia"])
        except ValueError:
            raise HTTPException(400, "La tendencia es persistente, "
                                     "creciente o decreciente")
    lat = nuevos.get("lat", evento.lat)
    lon = nuevos.get("lon", evento.lon)
    if (lat is None) != (lon is None):
        raise HTTPException(400, "El punto lleva latitud y longitud, o "
                                 "ninguna de las dos")
    if lat is not None and not (-90 <= float(lat) <= 90
                                and -180 <= float(lon) <= 180):
        raise HTTPException(400, "Ese punto no existe en el mapa")
    for clave in ("lat", "lon"):
        if nuevos.get(clave) is not None:
            nuevos[clave] = Decimal(str(round(float(nuevos[clave]), 7)))
    if nuevos.get("radio_m") is not None and not (
            50 <= int(nuevos["radio_m"]) <= 200000):
        raise HTTPException(400, "El radio va de 50 metros a 200 km")

    ocurrio = nuevos.get("ocurrio_en", evento.ocurrio_en)
    vence = nuevos.get("vigente_hasta", evento.vigente_hasta)
    if ocurrio is None or vence is None:
        raise HTTPException(400, "Falta cuándo pasó y hasta cuándo afecta")
    if vence <= ocurrio:
        raise HTTPException(400, "La vigencia termina antes de que pasara "
                                 "el evento")
    if vence - ocurrio > VIGENCIA_MAXIMA:
        raise HTTPException(400, {
            "mensaje": "La vigencia pasa de 30 días",
            "que_hacer": "Un evento afecta por horas o días. Lo que dura "
                         "meses es riesgo de fondo de la zona."})

    cambiaron = []
    for clave, valor in nuevos.items():
        if getattr(evento, clave) != valor:
            setattr(evento, clave, valor)
            cambiaron.append(clave)
    # El radio de su tipo cuando el punto llega sin radio.
    if evento.lat is not None and not evento.radio_m:
        evento.radio_m = db.get(m.TipoEvento, evento.tipo_id).radio_m
    return cambiaron


def crear(db: Session, usuario: m.Usuario | None, datos: dict,
          origen: str = "analista") -> m.EventoRiesgo:
    pais = db.get(m.Pais, datos.get("pais_id"))
    if not pais:
        raise HTTPException(400, "Falta el país del evento")
    for clave in ("region_id", "tipo_id", "nivel", "titulo", "ocurrio_en",
                  "vigente_hasta"):
        if datos.get(clave) in (None, ""):
            raise HTTPException(400, {
                "mensaje": "Faltan datos del evento",
                "que_hacer": "Tipo, estado, nivel, título, cuándo pasó y "
                             "hasta cuándo afecta."})
    evento = m.EventoRiesgo(folio=_folio_siguiente(db), pais_id=pais.id,
                            estado=E.PROPUESTO, origen=origen,
                            creado_por_id=usuario.id if usuario else None,
                            ocurrio_en=None, vigente_hasta=None)
    _aplicar(db, evento, datos, pais)
    db.add(evento)
    db.flush()
    _anotar(db, evento, usuario, "creo",
            f"{evento.tipo.nombre}, nivel {evento.nivel}, "
            f"{evento.region.nombre}")
    return evento


def editar(db: Session, usuario: m.Usuario, evento: m.EventoRiesgo,
           datos: dict, ahora: datetime | None = None) -> m.EventoRiesgo:
    if evento.estado in (E.CERRADO, E.DESCARTADO):
        raise HTTPException(409, f"El evento {evento.folio} ya está "
                                 f"{evento.estado.value}: no se edita")
    nivel_antes = evento.nivel
    pide_nivel = datos.get("nivel")
    publicado = evento.estado == E.PUBLICADO
    # Un publicado que sube a 4 no sube solo: el 4 espera al jefe.
    if publicado and pide_nivel == 4 and nivel_antes < 4:
        datos = {k: v for k, v in datos.items() if k != "nivel"}
    cambiaron = _aplicar(db, evento, datos, evento.pais)
    detalle = ", ".join(cambiaron)

    if publicado and pide_nivel == 4 and nivel_antes < 4:
        evento.nivel_pendiente = 4
        evento.critico_pedido_por_id = usuario.id
        detalle = (detalle + "; " if detalle else "") + \
            "pide subir a nivel 4: espera al jefe de turno"
    elif publicado and pide_nivel is not None and pide_nivel < 4:
        # Si se baja, el 4 que esperaba ya no aplica.
        evento.nivel_pendiente = None

    if evento.estado == E.POR_CONFIRMAR:
        # Lo que el jefe iba a confirmar ya no es lo mismo: vuelve a
        # propuesto y se publica otra vez.
        evento.estado = E.PROPUESTO
        detalle += "; regresa a propuesto para volver a pedir confirmación"

    if not cambiaron and not evento.nivel_pendiente:
        return evento
    evento.actualizado_en = _ahora(ahora)
    _anotar(db, evento, usuario, "edito", detalle)
    if publicado and "nivel" in cambiaron and evento.nivel > nivel_antes:
        _avisar(db, evento, "sube")
    return evento


def publicar(db: Session, usuario: m.Usuario, evento: m.EventoRiesgo,
             ahora: datetime | None = None) -> m.EventoRiesgo:
    ahora = _ahora(ahora)
    if evento.estado != E.PROPUESTO:
        raise HTTPException(409, f"El evento {evento.folio} está "
                                 f"{evento.estado.value}: solo se publica "
                                 "lo propuesto")
    if len((evento.texto_cliente or "").strip()) < 20:
        raise HTTPException(400, {
            "mensaje": "Falta el texto para el cliente",
            "que_hacer": "Qué pasó, dónde y qué hacer, en una o dos "
                         "frases. Es lo que lee el cliente."})
    if evento.vigente_hasta <= ahora:
        raise HTTPException(400, "Su vigencia ya pasó: no hay nada que "
                                 "publicar")
    if evento.nivel == 4:
        evento.estado = E.POR_CONFIRMAR
        evento.critico_pedido_por_id = usuario.id
        evento.actualizado_en = ahora
        _anotar(db, evento, usuario, "pidio_critico",
                "Nivel 4: espera la confirmación del jefe de turno")
        return evento
    evento.estado = E.PUBLICADO
    evento.publicado_por_id = usuario.id
    evento.publicado_en = ahora
    evento.actualizado_en = ahora
    _anotar(db, evento, usuario, "publico", f"Nivel {evento.nivel}")
    _avisar(db, evento, "nuevo")
    return evento


def confirmar_critico(db: Session, usuario: m.Usuario,
                      evento: m.EventoRiesgo,
                      ahora: datetime | None = None) -> m.EventoRiesgo:
    ahora = _ahora(ahora)
    espera = (evento.estado == E.POR_CONFIRMAR
              or (evento.estado == E.PUBLICADO
                  and evento.nivel_pendiente == 4))
    if not espera:
        raise HTTPException(409, f"El evento {evento.folio} no espera "
                                 "confirmación de nivel 4")
    if evento.critico_pedido_por_id == usuario.id:
        raise HTTPException(409, {
            "mensaje": "El nivel 4 lo confirma otra persona",
            "que_hacer": "Quien lo pidió no lo confirma: lo hace el jefe "
                         "de turno."})
    if evento.vigente_hasta <= ahora:
        raise HTTPException(400, "Su vigencia ya pasó: no hay nada que "
                                 "confirmar")
    era_publico = evento.estado == E.PUBLICADO
    evento.nivel = 4
    evento.nivel_pendiente = None
    evento.critico_confirmado_por_id = usuario.id
    evento.critico_confirmado_en = ahora
    evento.actualizado_en = ahora
    if not era_publico:
        evento.estado = E.PUBLICADO
        evento.publicado_por_id = usuario.id
        evento.publicado_en = ahora
    _anotar(db, evento, usuario, "confirmo_critico",
            "Confirmó el nivel 4" + ("" if era_publico else " y lo publicó"))
    _avisar(db, evento, "sube" if era_publico else "nuevo")
    return evento


def devolver_critico(db: Session, usuario: m.Usuario, evento: m.EventoRiesgo,
                     motivo: str,
                     ahora: datetime | None = None) -> m.EventoRiesgo:
    """El jefe de turno no confirma el 4: regresa con su motivo."""
    motivo = _motivo(motivo, "devuelve")
    if evento.estado == E.POR_CONFIRMAR:
        evento.estado = E.PROPUESTO
    elif evento.estado == E.PUBLICADO and evento.nivel_pendiente == 4:
        evento.nivel_pendiente = None
    else:
        raise HTTPException(409, f"El evento {evento.folio} no espera "
                                 "confirmación de nivel 4")
    evento.actualizado_en = _ahora(ahora)
    _anotar(db, evento, usuario, "devolvio_critico", motivo)
    return evento


def cerrar(db: Session, usuario: m.Usuario, evento: m.EventoRiesgo,
           motivo: str, ahora: datetime | None = None) -> m.EventoRiesgo:
    motivo = _motivo(motivo, "cierra")
    if evento.estado != E.PUBLICADO:
        raise HTTPException(409, f"El evento {evento.folio} no está "
                                 "publicado: no hay nada que cerrar")
    _terminar(db, usuario, evento, E.CERRADO, motivo, _ahora(ahora))
    return evento


def descartar(db: Session, usuario: m.Usuario, evento: m.EventoRiesgo,
              motivo: str, ahora: datetime | None = None) -> m.EventoRiesgo:
    motivo = _motivo(motivo, "descarta")
    if evento.estado not in (E.PROPUESTO, E.POR_CONFIRMAR):
        raise HTTPException(409, {
            "mensaje": f"El evento {evento.folio} ya se publicó",
            "que_hacer": "Lo publicado no se descarta: se cierra, con su "
                         "motivo."})
    _terminar(db, usuario, evento, E.DESCARTADO, motivo, _ahora(ahora))
    return evento


def _terminar(db, usuario, evento, estado, motivo, ahora):
    evento.estado = estado
    evento.nivel_pendiente = None
    evento.motivo = motivo
    evento.terminado_por_id = usuario.id if usuario else None
    evento.terminado_en = ahora
    evento.actualizado_en = ahora
    _anotar(db, evento, usuario, estado.value, motivo)


def vencer(db: Session, ahora: datetime | None = None) -> int:
    """La tarea del reloj: cierra lo publicado cuya vigencia ya paso.

    Lo propuesto que vence no se cierra --nunca fue publico--: se
    descarta, para que la cola del analista no arrastre lo de ayer.
    """
    ahora = _ahora(ahora)
    vencidos = (db.query(m.EventoRiesgo)
                .filter(m.EventoRiesgo.estado.in_(
                    [E.PUBLICADO, E.PROPUESTO, E.POR_CONFIRMAR]),
                    m.EventoRiesgo.vigente_hasta <= ahora).all())
    for evento in vencidos:
        estado = E.CERRADO if evento.estado == E.PUBLICADO else E.DESCARTADO
        _terminar(db, None, evento, estado, "Venció su vigencia", ahora)
    return len(vencidos)


def agregar_fuente(db: Session, usuario: m.Usuario, evento: m.EventoRiesgo,
                   descripcion: str, url: str | None = None,
                   oficial: bool = False) -> m.FuenteEvento:
    if evento.estado in (E.CERRADO, E.DESCARTADO):
        raise HTTPException(409, f"El evento {evento.folio} ya terminó")
    descripcion = (descripcion or "").strip()
    if len(descripcion) < 3:
        raise HTTPException(400, "Di de dónde salió: el medio, la cuenta o "
                                 "la autoridad")
    url = (url or "").strip() or None
    if url and not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "El enlace empieza con http:// o https://")
    fuente = m.FuenteEvento(evento_id=evento.id, url=url,
                            descripcion=descripcion[:300], oficial=oficial,
                            registrada_por_id=usuario.id)
    evento.fuentes.append(fuente)
    db.flush()
    evento.verificacion = _verificacion(evento)
    _anotar(db, evento, usuario, "fuente",
            descripcion + (" (oficial)" if oficial else ""))
    return fuente


def quitar_fuente(db: Session, usuario: m.Usuario, evento: m.EventoRiesgo,
                  fuente_id: int) -> None:
    fuente = next((f for f in evento.fuentes if f.id == fuente_id), None)
    if not fuente:
        raise HTTPException(404, "Esa fuente no es de este evento")
    evento.fuentes.remove(fuente)
    db.flush()
    evento.verificacion = _verificacion(evento)
    _anotar(db, evento, usuario, "quito_fuente", fuente.descripcion)


def _avisar(db: Session, evento: m.EventoRiesgo, motivo: str) -> None:
    from app import alertas_riesgo, riesgo_campo
    alertas_riesgo.al_publicar(db, evento, motivo)
    # Y al personal de seguridad que trabaja hoy cerca (seccion 134).
    riesgo_campo.al_publicar(db, evento, motivo)
    for funcion in AL_PUBLICAR:
        funcion(db, evento, motivo)

"""A quien le llega cada evento, y por donde (seccion 134).

La regla de reparto es corta a proposito: **un evento publicado le llega
al gerente de cada cliente que sigue ese estado.** El analista no escoge
a mano a quien avisar --se le olvidaria uno el dia que importa--; lo
decide el estado del evento contra las zonas de cada cliente.

Por donde, segun el nivel (decision de Salvador, 2 oct):

  1 Informativo  solo el mapa: no es alerta
  2 Precaucion   aviso al telefono; por correo, en el resumen del dia
  3 Alto         aviso al telefono y correo al momento, con acuse
  4 Critico      lo mismo, y si nadie acusa en 15 minutos la central llama

Una alerta por evento, persona y nivel. Si el evento sube de 2 a 3 es
otra alerta --la que pide acuse--; si se corrige sin subir, no hay otra.
Una central que avisa de todo ensena a no leerla.

Los 15 minutos del nivel 4 son una propuesta de la casa: el tiempo de
que alguien vea el telefono y no tanto que una llamada llegue tarde.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import correo_html
from app import models as m
from app import push
from app import reloj

MINUTOS_PARA_LLAMAR = 15
HORA_DEL_RESUMEN = 20         # hora local del pais del cliente

TEXTOS = {
    "es": {
        "nivel": {1: "Informativo", 2: "Precaución", 3: "Alto", 4: "Crítico"},
        "asunto": "[Nivel {n} · {nombre}] {titulo}",
        "sube": "Sube a nivel {n}: {titulo}",
        "tipo": "Tipo", "donde": "Dónde", "lugar": "Lugar", "paso": "Pasó",
        "hasta": "Afecta hasta", "verif": "Verificación",
        "verificacion": {"sin_confirmar": "Sin confirmar",
                         "confirmado": "Confirmado",
                         "oficial": "Oficial"},
        "resumen_asunto": "Resumen de riesgo del día · {n} evento(s)",
        "resumen_cuerpo": "Lo que publicó la Central de Inteligencia hoy en "
                          "las zonas que sigues.",
    },
    "pt": {
        "nivel": {1: "Informativo", 2: "Precaução", 3: "Alto", 4: "Crítico"},
        "asunto": "[Nível {n} · {nombre}] {titulo}",
        "sube": "Sobe para nível {n}: {titulo}",
        "tipo": "Tipo", "donde": "Onde", "lugar": "Local", "paso": "Aconteceu",
        "hasta": "Afeta até", "verif": "Verificação",
        "verificacion": {"sin_confirmar": "Não confirmado",
                         "confirmado": "Confirmado",
                         "oficial": "Oficial"},
        "resumen_asunto": "Resumo de risco do dia · {n} evento(s)",
        "resumen_cuerpo": "O que a Central de Inteligência publicou hoje nas "
                          "zonas que você acompanha.",
    },
    "en": {
        "nivel": {1: "Informational", 2: "Caution", 3: "High", 4: "Critical"},
        "asunto": "[Level {n} · {nombre}] {titulo}",
        "sube": "Raised to level {n}: {titulo}",
        "tipo": "Type", "donde": "Where", "lugar": "Place", "paso": "When",
        "hasta": "In effect until", "verif": "Verification",
        "verificacion": {"sin_confirmar": "Unconfirmed",
                         "confirmado": "Confirmed",
                         "oficial": "Official"},
        "resumen_asunto": "Daily risk summary · {n} event(s)",
        "resumen_cuerpo": "What the Intelligence Center published today in "
                          "the areas you follow.",
    },
}


def _tx(idioma: str) -> dict:
    return TEXTOS.get(idioma) or TEXTOS["es"]


def _ahora(ahora: datetime | None) -> datetime:
    return ahora or datetime.now(timezone.utc)


def enlace_del_evento(evento_id: int) -> str | None:
    """A donde lleva el aviso: el evento dentro de la app del cliente."""
    from app import cliente_ci
    raiz = cliente_ci.raiz_app()
    # Sin direccion publica no hay a donde llevar a nadie desde un correo.
    return f"{raiz}/#/evento/{evento_id}" if raiz.startswith("http") else None


def destinatarios(db: Session, evento: m.EventoRiesgo) -> list[m.UsuarioCliente]:
    """Los gerentes activos de los clientes activos que siguen el estado
    del evento."""
    return (db.query(m.UsuarioCliente)
            .join(m.ClienteCentral,
                  m.ClienteCentral.id == m.UsuarioCliente.cliente_central_id)
            .join(m.ZonaCliente,
                  m.ZonaCliente.cliente_central_id == m.ClienteCentral.id)
            .filter(m.ZonaCliente.region_id == evento.region_id,
                    m.ClienteCentral.activo.is_(True),
                    m.UsuarioCliente.activo.is_(True),
                    m.UsuarioCliente.perfil == m.PerfilCliente.GERENTE)
            .order_by(m.UsuarioCliente.id).all())


def _hora_local(instante: datetime, evento: m.EventoRiesgo) -> str:
    return instante.astimezone(
        reloj.zona(evento.pais.zona_horaria)).strftime("%d/%m %H:%M")


def _pares(evento: m.EventoRiesgo, idioma: str) -> list[tuple[str, str]]:
    t = _tx(idioma)
    donde = evento.region.nombre
    if evento.municipio:
        donde = f"{evento.municipio}, {donde}"
    pares = [(t["tipo"], evento.tipo.nombre), (t["donde"], donde)]
    if evento.lugar:
        pares.append((t["lugar"], evento.lugar))
    pares += [(t["paso"], _hora_local(evento.ocurrio_en, evento)),
              (t["hasta"], _hora_local(evento.vigente_hasta, evento)),
              (t["verif"], t["verificacion"][evento.verificacion.value])]
    return pares


def _correo(db: Session, gente: m.UsuarioCliente, asunto: str, cuerpo: str,
            pares: list, enlace: str | None) -> m.Notificacion:
    aviso = m.Notificacion(
        destinatario=m.Destinatario.CLIENTE_CI, canal=m.Canal.CORREO,
        correo=gente.correo, idioma=gente.idioma, asunto=asunto[:200],
        cuerpo=cuerpo[:2000], datos=correo_html.guardar_datos(pares),
        enlace_seguimiento=enlace)
    db.add(aviso)
    db.flush()
    return aviso


def al_publicar(db: Session, evento: m.EventoRiesgo, motivo: str,
                ahora: datetime | None = None) -> dict:
    """Lo llama `riesgo` cuando un evento se publica o sube de nivel."""
    ahora = _ahora(ahora)
    if evento.nivel < 2:
        return {"alertas": 0}
    enlace = enlace_del_evento(evento.id)
    nuevas, telefonos, correos = 0, 0, 0
    for gente in destinatarios(db, evento):
        ya = (db.query(m.AlertaCliente)
              .filter_by(evento_id=evento.id, usuario_cliente_id=gente.id,
                         nivel=evento.nivel).first())
        if ya:
            continue
        t = _tx(gente.idioma)
        nombre = t["nivel"][evento.nivel]
        alerta = m.AlertaCliente(
            evento_id=evento.id, usuario_cliente_id=gente.id,
            nivel=evento.nivel, motivo=motivo, creada_en=ahora,
            requiere_acuse=evento.nivel >= 3,
            llamar_desde=(ahora + timedelta(minutes=MINUTOS_PARA_LLAMAR)
                          if evento.nivel == 4 else None))
        db.add(alerta)
        db.flush()

        titulo = (t["sube"].format(n=evento.nivel, titulo=evento.titulo)
                  if motivo == "sube" else
                  f"{nombre}: {evento.titulo}")
        filas = (db.query(m.SuscripcionPushCliente)
                 .filter_by(usuario_cliente_id=gente.id, activa=True).all())
        if filas and push.hay_llaves():
            import json
            carga = json.dumps({"titulo": titulo[:120],
                                "cuerpo": evento.texto_cliente[:240],
                                "url": f"/ci/#/evento/{evento.id}",
                                "etiqueta": f"evento-{evento.id}",
                                "accion": None, "botones": {}})
            salida = push.entregar(db, filas, carga,
                                   urgente=evento.nivel >= 3)
            alerta.telefonos = salida["enviados"]
            telefonos += salida["enviados"]
        if evento.nivel >= 3:
            asunto = t["asunto"].format(n=evento.nivel, nombre=nombre,
                                        titulo=evento.titulo)
            aviso = _correo(db, gente, asunto, evento.texto_cliente,
                            _pares(evento, gente.idioma), enlace)
            alerta.correo_id = aviso.id
            correos += 1
        nuevas += 1

    if nuevas:
        from app import riesgo
        riesgo._anotar(db, evento, None, "aviso",
                       f"Nivel {evento.nivel}: {nuevas} persona(s), "
                       f"{telefonos} teléfono(s), {correos} correo(s)")
    return {"alertas": nuevas, "telefonos": telefonos, "correos": correos}


def resumen_del_dia(db: Session, ahora: datetime | None = None) -> dict:
    """Cada hora: a quien ya le dieron las 20:00, su resumen del nivel 2.

    El nivel 2 no merece un correo por evento --se dejaria de leer--,
    pero tampoco puede quedarse solo en el telefono: el gerente que no
    tiene la app abierta lo lee al final del dia.
    """
    ahora = _ahora(ahora)
    pendientes = (db.query(m.AlertaCliente)
                  .filter(m.AlertaCliente.nivel == 2,
                          m.AlertaCliente.en_resumen.is_(False),
                          m.AlertaCliente.creada_en
                          >= ahora - timedelta(hours=36))
                  .order_by(m.AlertaCliente.id).all())
    por_persona: dict[int, list[m.AlertaCliente]] = {}
    for alerta in pendientes:
        gente = alerta.usuario_cliente
        pais = db.get(m.Pais, gente.cliente_central.cliente.pais_id)
        if ahora.astimezone(reloj.zona(pais.zona_horaria)).hour \
                != HORA_DEL_RESUMEN:
            continue
        por_persona.setdefault(gente.id, []).append(alerta)

    enviados = 0
    for alertas in por_persona.values():
        gente = alertas[0].usuario_cliente
        t = _tx(gente.idioma)
        pares = [(f"{t['nivel'][a.evento.nivel]} · "
                  f"{a.evento.region.nombre}", a.evento.titulo)
                 for a in alertas]
        aviso = _correo(db, gente,
                        t["resumen_asunto"].format(n=len(alertas)),
                        t["resumen_cuerpo"], pares,
                        enlace_del_evento(alertas[0].evento_id))
        for alerta in alertas:
            alerta.en_resumen = True
            alerta.correo_id = alerta.correo_id or aviso.id
        enviados += 1
    return {"resumenes": enviados}


def acusar(db: Session, gente: m.UsuarioCliente, alerta_id: int,
           ahora: datetime | None = None) -> m.AlertaCliente:
    alerta = db.get(m.AlertaCliente, alerta_id)
    if not alerta or alerta.usuario_cliente_id != gente.id:
        raise HTTPException(404, "Esa alerta no es tuya")
    if alerta.acuse_en is None:
        alerta.acuse_en = _ahora(ahora)
    return alerta


def por_llamar(db: Session, ahora: datetime | None = None) -> list[dict]:
    """Nivel 4 sin acuse a los 15 minutos: la central llama."""
    ahora = _ahora(ahora)
    filas = (db.query(m.AlertaCliente)
             .filter(m.AlertaCliente.llamar_desde.isnot(None),
                     m.AlertaCliente.llamar_desde <= ahora,
                     m.AlertaCliente.acuse_en.is_(None),
                     m.AlertaCliente.llamada_en.is_(None))
             .order_by(m.AlertaCliente.llamar_desde).all())
    return [vista_alerta(a) for a in filas]


def registrar_llamada(db: Session, usuario: m.Usuario, alerta_id: int,
                      nota: str, ahora: datetime | None = None
                      ) -> m.AlertaCliente:
    alerta = db.get(m.AlertaCliente, alerta_id)
    if not alerta:
        raise HTTPException(404, f"No existe la alerta {alerta_id}")
    nota = (nota or "").strip()
    if len(nota) < 5:
        raise HTTPException(400, "Di qué pasó en la llamada: si contestó y "
                                 "qué dijo")
    if alerta.llamada_en is not None:
        raise HTTPException(409, "Esa llamada ya se registró")
    alerta.llamada_en = _ahora(ahora)
    alerta.llamada_por_id = usuario.id
    alerta.llamada_nota = nota[:400]
    from app import riesgo
    riesgo._anotar(db, alerta.evento, usuario, "llamada",
                   f"{alerta.usuario_cliente.nombre_completo}: {nota}")
    return alerta


def vista_alerta(alerta: m.AlertaCliente) -> dict:
    gente = alerta.usuario_cliente
    return {
        "id": alerta.id, "evento_id": alerta.evento_id,
        "folio": alerta.evento.folio, "titulo": alerta.evento.titulo,
        "nivel": alerta.nivel, "motivo": alerta.motivo,
        "creada_en": alerta.creada_en.isoformat(),
        "persona": gente.nombre_completo, "correo": gente.correo,
        "telefono": gente.telefono,
        "cliente": gente.cliente_central.cliente.nombre,
        "telefonos": alerta.telefonos,
        "correo_enviado": alerta.correo_id is not None,
        "requiere_acuse": alerta.requiere_acuse,
        "acuse_en": alerta.acuse_en.isoformat() if alerta.acuse_en else None,
        "llamar_desde": (alerta.llamar_desde.isoformat()
                         if alerta.llamar_desde else None),
        "llamada_en": (alerta.llamada_en.isoformat()
                       if alerta.llamada_en else None),
        "llamada_nota": alerta.llamada_nota,
    }


def del_evento(db: Session, evento: m.EventoRiesgo) -> list[dict]:
    filas = (db.query(m.AlertaCliente).filter_by(evento_id=evento.id)
             .order_by(m.AlertaCliente.id).all())
    return [vista_alerta(a) for a in filas]

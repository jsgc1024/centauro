# -*- coding: utf-8 -*-
"""Reportar una falla (seccion 92).

El ciclo que aprobo Salvador el 27 de septiembre --«asi cerramos el
ciclo»--:

1. Quien ve la falla la reporta ahi mismo: en la consola, con el boton de
   arriba; en la app, en «Yo».
2. Escribe que paso y, si quiere, pega una captura. Lo demas se manda
   solo: la pantalla, el servicio, quien, la version, el navegador o el
   telefono y lo ultimo que le salio. Nunca la sesion ni contrasenas.
3. Llega a Manual del sistema -> Casos como «por revisar», y a sistema y
   calidad le llega el aviso.
4. Si es de datos o de uso, lo resuelve ella. Si es falla del sistema,
   «Copiar para Claude» lo deja listo para pegarlo en la conversacion con
   Claude, y el caso queda «con Claude» mientras se arregla.
5. Ya resuelto, se completa con la causa y como se arreglo, y a quien lo
   reporto le llega el aviso. De esos casos va a aprender el primer
   agente del sistema.

El reporte es un caso resuelto que todavia no se resuelve: la misma
tabla, con su estado. Asi el que se reporta y el que se anota a mano
terminan en el mismo lugar y se buscan igual.
"""
import base64
import binascii
import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models as m

POR_REVISAR = "por_revisar"
CON_CLAUDE = "con_claude"
RESUELTO = "resuelto"
ABIERTOS = (POR_REVISAR, CON_CLAUDE)

# Cuanto de cada cosa. Lo que llega de mas se recorta, no se rechaza: el
# reporte de alguien que tiene prisa no puede fallar por largo.
LARGO_QUE_PASO = 4000
LARGO_ESPERABA = 2000
# Una captura reducida a 1600 pixeles pesa unos 300 KB; en texto, un
# tercio mas. Cuatro millones de letras dejan pasar hasta una PNG grande
# sin abrirle la puerta a un archivo cualquiera.
LARGO_CAPTURA = 4_000_000
CAPTURA = re.compile(r"data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=\s]+")

# Nadie reporta diez fallas en una hora; quien lo hace esta repitiendo el
# boton o algo lo esta mandando solo. Se para ahi y se dice a quien llamar.
POR_HORA = 10

DESDE = ("consola", "app")


def _corto(texto, largo: int) -> str:
    texto = " ".join(str(texto or "").split()) if largo <= 300 else str(texto or "").strip()
    return texto[:largo]


def limpiar_contexto(contexto: dict | None) -> dict:
    """Solo lo que se sabe leer, y cada cosa de su tamano.

    Lo que manda la pantalla es una afirmacion, no una verdad: se guarda
    para leerlo, no se usa para decidir nada. Por eso se recorta en vez
    de rechazarse, y lo que no esta en la lista no se guarda.
    """
    c = contexto or {}
    salida = {
        "desde": c.get("desde") if c.get("desde") in DESDE else "consola",
        "pantalla": _corto(c.get("pantalla"), 80),
        "ruta": _corto(c.get("ruta"), 200),
        "navegador": _corto(c.get("navegador"), 300),
        "app": _corto(c.get("app"), 40),
    }
    for clave in ("servicio_id", "jornada_id"):
        valor = c.get(clave)
        salida[clave] = valor if isinstance(valor, int) and valor > 0 else None

    mensajes = []
    for x in (c.get("mensajes") or [])[:8]:
        if isinstance(x, dict) and x.get("texto"):
            mensajes.append({"cuando": _corto(x.get("cuando"), 40),
                             "texto": _corto(x.get("texto"), 300),
                             "tono": _corto(x.get("tono"), 10)})
    salida["mensajes"] = mensajes

    llamadas = []
    for x in (c.get("llamadas") or [])[:10]:
        if not isinstance(x, dict) or not x.get("ruta"):
            continue
        codigo = x.get("codigo")
        llamadas.append({"cuando": _corto(x.get("cuando"), 40),
                         "metodo": _corto(x.get("metodo"), 8).upper(),
                         # La ruta sin lo que va despues del ?: ahi viajan
                         # las busquedas, que pueden llevar nombres.
                         "ruta": _corto(str(x.get("ruta")).split("?")[0], 200),
                         "codigo": codigo if isinstance(codigo, int) else None,
                         "mensaje": _corto(x.get("mensaje"), 300)})
    salida["llamadas"] = llamadas
    return {k: v for k, v in salida.items() if v not in ("", None, [])}


def _resumen(texto: str, largo: int = 70) -> str:
    """El primer renglon, cortado donde acaba una palabra."""
    primero = (texto or "").strip().splitlines()[0] if (texto or "").strip() else ""
    primero = " ".join(primero.split())
    if len(primero) <= largo:
        return primero
    corte = primero[:largo].rsplit(" ", 1)[0] or primero[:largo]
    return corte.rstrip(".,;:") + "…"


def donde(contexto: dict) -> str:
    """Donde paso, como lo diria quien lo vio: el folio si era un
    servicio, si no la pantalla."""
    servicio = contexto.get("servicio") or {}
    if servicio.get("folio"):
        return servicio["folio"]
    if contexto.get("pantalla"):
        return contexto["pantalla"]
    return "App de campo" if contexto.get("desde") == "app" else "Consola"


def _captura_valida(captura: str | None) -> str | None:
    if not captura:
        return None
    captura = captura.strip()
    if len(captura) > LARGO_CAPTURA:
        raise HTTPException(413, {
            "mensaje": "La captura pesa demasiado",
            "que_hacer": "Manda el reporte sin ella, o recórtala y vuelve a pegarla.",
        })
    if not CAPTURA.fullmatch(captura):
        raise HTTPException(422, {
            "mensaje": "La captura no es una imagen",
            "que_hacer": "Pega una captura de pantalla o una foto.",
        })
    return captura


def _nombre_y_puesto(usuario: m.Usuario) -> dict:
    persona = usuario.persona
    puesto = usuario.categoria.nombre if usuario.categoria else None
    return {"nombre": (persona.nombre if persona else None) or usuario.correo,
            "rol": usuario.rol.value, "puesto": puesto}


def _zona_de(usuario: m.Usuario) -> str | None:
    persona = usuario.persona
    pais = persona.plaza.pais if persona and persona.plaza else None
    return pais.zona_horaria if pais else None


def crear(db: Session, usuario: m.Usuario, que_paso: str,
          esperaba: str | None = None, captura: str | None = None,
          contexto: dict | None = None,
          ahora: datetime | None = None) -> m.CasoResuelto:
    """El reporte, guardado como caso por revisar. Revienta con lo que
    hay que corregir antes de guardar nada."""
    from app import manual

    que_paso = (que_paso or "").strip()
    if len(que_paso) < 3:
        raise HTTPException(422, {
            "mensaje": "Falta qué pasó",
            "que_hacer": "Escribe qué estabas haciendo y qué salió.",
        })
    ahora = ahora or datetime.now(timezone.utc)

    recientes = (db.query(m.CasoResuelto.id)
                 .filter(m.CasoResuelto.reportado_por_id == usuario.persona_id,
                         m.CasoResuelto.reportado_en >= ahora - timedelta(hours=1))
                 .count())
    if recientes >= POR_HORA:
        raise HTTPException(429, {
            "mensaje": (f"Ya mandaste {recientes} reportes en la última hora; "
                        "este no se guardó"),
            "que_hacer": ("Si es urgente, llama a la central. Si no, "
                          "vuelve a intentarlo en un rato."),
        })

    captura = _captura_valida(captura)
    datos = limpiar_contexto(contexto)
    datos["quien"] = _nombre_y_puesto(usuario)
    datos["zona"] = _zona_de(usuario)
    version = manual.version("es")
    datos["version"] = {"seccion": version["seccion"], "fecha": version["fecha"]}
    if datos.get("servicio_id"):
        servicio = db.get(m.Servicio, datos["servicio_id"])
        if servicio:
            datos["servicio"] = {"id": servicio.id, "folio": servicio.folio,
                                 "tipo": servicio.tipo.value}
        else:
            datos.pop("servicio_id")

    caso = m.CasoResuelto(
        titulo=f"{donde(datos)} · {_resumen(que_paso)}"[:160],
        que_se_vio=que_paso[:LARGO_QUE_PASO], causa="", solucion="",
        esperaba=(esperaba or "").strip()[:LARGO_ESPERABA] or None,
        contexto=json.dumps(datos, ensure_ascii=False),
        captura=captura, estado=POR_REVISAR, falla="no_se",
        reportado_por_id=usuario.persona_id, reportado_en=ahora)
    db.add(caso)
    db.flush()
    avisar_nuevo(db, caso)
    db.commit()
    return caso


def contexto_de(caso: m.CasoResuelto) -> dict:
    try:
        return json.loads(caso.contexto) if caso.contexto else {}
    except ValueError:
        return {}


def imagen(caso: m.CasoResuelto) -> tuple[bytes, str] | None:
    """La captura, lista para entregarse: (bytes, tipo)."""
    if not caso.captura:
        return None
    cabeza, _, datos = caso.captura.partition(",")
    tipo = cabeza.split(";")[0].replace("data:", "") or "image/jpeg"
    try:
        return base64.b64decode(datos), tipo
    except (binascii.Error, ValueError):
        return None


# =================================================== copiar para Claude

def _hora(iso: str | None, zona: str | None) -> str:
    """"21:13" en la zona de quien lo reporto."""
    from app import reloj

    if not iso:
        return ""
    try:
        momento = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso)[:16]
    if momento.tzinfo is None:
        return momento.strftime("%H:%M")
    return momento.astimezone(reloj.zona(zona)).strftime("%H:%M")


def para_claude(db: Session, caso: m.CasoResuelto) -> str:
    """El reporte en un bloque de texto para pegarlo en la conversacion
    con Claude. Lleva lo que hace falta para encontrar la falla en el
    codigo --la pantalla, la ruta, la version, lo que contesto el
    servidor-- y nada que no deba salir: ni la sesion, ni contrasenas, ni
    la captura (esa se pega aparte si hace falta)."""
    from app import reloj

    c = contexto_de(caso)
    quien = c.get("quien") or {}
    zona = c.get("zona")
    cuando = ""
    if caso.reportado_en:
        local = caso.reportado_en.astimezone(reloj.zona(zona))
        cuando = f"{local:%d/%m/%Y %H:%M}, hora de {reloj.zona(zona).key}"
    version = c.get("version") or {}
    puesto = quien.get("puesto") or (quien.get("rol") or "").replace("_", " ")

    def bloque(etiqueta: str, texto: str | None) -> list[str]:
        if not texto:
            return []
        renglones = str(texto).strip().splitlines() or [""]
        salida = [f"{etiqueta:<11} {renglones[0]}"]
        salida += [f"{'':<11} {r}" for r in renglones[1:]]
        return salida

    lineas = [f"Falla en Connect · caso {caso.id} · {ESTADO_TEXTO.get(caso.estado, caso.estado)}"]
    # En un servicio, el titulo de la pantalla suele ser su folio: no se
    # repite.
    pantalla = c.get("pantalla") if c.get("servicio") else None
    lineas += bloque("Dónde:", " · ".join(x for x in (
        donde(c), pantalla if pantalla != donde(c) else None,
        c.get("ruta")) if x))
    lineas += bloque("Quién:", " · ".join(x for x in (
        quien.get("nombre"), puesto, cuando) if x))
    lineas += bloque("Desde:", " · ".join(x for x in (
        "la app de campo" if c.get("desde") == "app" else "la consola",
        c.get("app"), c.get("navegador")) if x))
    if version:
        lineas += bloque("Versión:", f"sección {version.get('seccion')}, "
                                     f"del {version.get('fecha')}")
    lineas += bloque("Qué pasó:", caso.que_se_vio)
    lineas += bloque("Esperaba:", caso.esperaba)
    if c.get("mensajes"):
        lineas.append("Lo último que le salió:")
        lineas += [f"  {_hora(x.get('cuando'), zona)}  «{x.get('texto')}»"
                   for x in c["mensajes"]]
    if c.get("llamadas"):
        lineas.append("Lo último que pidió al servidor:")
        for x in c["llamadas"]:
            partes = [f"{x.get('metodo', '')} {x.get('ruta', '')}".strip(),
                      str(x.get("codigo")) if x.get("codigo") is not None else "sin respuesta",
                      x.get("mensaje") or ""]
            lineas.append(f"  {_hora(x.get('cuando'), zona)}  "
                          + " · ".join(p for p in partes if p))
    lineas += bloque("Captura:", f"sí, en el caso {caso.id}"
                     if caso.captura is not None else None)
    return "\n".join(lineas)


ESTADO_TEXTO = {POR_REVISAR: "por revisar", CON_CLAUDE: "con Claude",
                RESUELTO: "resuelto"}


def copiado(db: Session, caso: m.CasoResuelto,
            ahora: datetime | None = None) -> str:
    """Copiar para Claude: el texto, y el caso pasa a «con Claude» si
    estaba por revisar. Uno ya resuelto se puede volver a copiar sin
    moverlo."""
    texto = para_claude(db, caso)
    if caso.estado == POR_REVISAR:
        caso.estado = CON_CLAUDE
        caso.con_claude_en = ahora or datetime.now(timezone.utc)
        db.commit()
        texto = para_claude(db, caso)
    return texto


# =================================================== resolver

def resolver(db: Session, caso: m.CasoResuelto, usuario: m.Usuario,
             valores: dict, ahora: datetime | None = None) -> m.CasoResuelto:
    """Se completa con la causa y como se arreglo, y a quien lo reporto
    le llega el aviso. `valores` ya viene limpio (manual.limpiar_caso)."""
    if caso.estado == RESUELTO:
        raise HTTPException(409, {
            "mensaje": "Ese caso ya está resuelto",
            "que_hacer": "Si hay que cambiar algo, corrígelo con «Corregir».",
        })
    for campo in ("causa", "solucion"):
        if not valores.get(campo):
            raise HTTPException(422, {
                "mensaje": ("Falta la causa: sin ella es una queja, no un caso "
                            "resuelto." if campo == "causa"
                            else "Falta cómo se arregló."),
                "que_hacer": "Corrígelo y vuelve a guardar.",
            })
    for campo, valor in valores.items():
        setattr(caso, campo, valor)
    ahora = ahora or datetime.now(timezone.utc)
    caso.estado = RESUELTO
    caso.resuelto_por_id = usuario.persona_id
    caso.resuelto_en = ahora
    # Quien lo escribio como caso es quien lo resolvio: el reporte lo
    # mando otra persona y eso queda en `reportado_por`.
    caso.escrito_por_id = usuario.persona_id
    db.flush()
    avisar_resuelto(db, caso)
    db.commit()
    return caso


# =================================================== los avisos

def revisores(db: Session) -> list[m.Usuario]:
    """A quien le llega un reporte: sistema y calidad. Si todavia no hay
    nadie con ese puesto, administracion, para que no se pierda."""
    activos = db.query(m.Usuario).filter(m.Usuario.activo.is_(True))
    suyos = activos.filter(m.Usuario.rol == m.Rol.SISTEMA_CALIDAD).all()
    return suyos or activos.filter(m.Usuario.rol == m.Rol.ADMIN).all()


def _correo(db: Session, usuario: m.Usuario, asunto: str, cuerpo: str,
            pares: list, enlace: str | None, lengua: str) -> None:
    from app import correo_html

    db.add(m.Notificacion(
        destinatario=m.Destinatario.COLABORADOR, canal=m.Canal.CORREO,
        correo=usuario.correo, idioma=lengua, asunto=asunto[:200],
        cuerpo=cuerpo[:2000], datos=correo_html.guardar_datos(pares),
        enlace_seguimiento=enlace))


def _push(db: Session, persona_id: int | None, titulo: str, cuerpo: str,
          url: str, etiqueta: str) -> None:
    """Un aviso que no sale no deshace el reporte ni su resolucion."""
    from app import push

    if not persona_id:
        return
    try:
        push.avisar(db, persona_id, titulo, cuerpo, url=url, etiqueta=etiqueta)
    except Exception:                     # noqa: BLE001
        pass


def avisar_nuevo(db: Session, caso: m.CasoResuelto) -> int:
    """A sistema y calidad: hay un reporte por revisar. Devuelve a cuantos."""
    from app import acceso_por_correo, textos_aviso as ta

    c = contexto_de(caso)
    quien = (c.get("quien") or {}).get("nombre") or "Alguien"
    avisados = 0
    for revisor in revisores(db):
        if revisor.persona_id == caso.reportado_por_id:
            continue
        lengua = acceso_por_correo.idioma_de(revisor)
        desde = ta.t(lengua, "falla_desde_app" if c.get("desde") == "app"
                     else "falla_desde_consola")
        asunto = ta.t(lengua, "falla_asunto", titulo=caso.titulo)
        cuerpo = ta.t(lengua, "falla_cuerpo", quien=quien, desde=desde)
        _correo(db, revisor, asunto, cuerpo,
                [(ta.t(lengua, "falla_donde"), donde(c)),
                 (ta.t(lengua, "falla_que_paso"), _corto(caso.que_se_vio, 300))],
                "/consola/#/manual/casos", lengua)
        _push(db, revisor.persona_id, asunto, cuerpo,
              "/consola/#/manual/casos", f"falla-{caso.id}")
        avisados += 1
    return avisados


def avisar_resuelto(db: Session, caso: m.CasoResuelto) -> bool:
    """A quien lo reporto: ya quedo, y que era."""
    from app import acceso_por_correo, reloj, textos_aviso as ta

    if not caso.reportado_por_id or caso.reportado_por_id == caso.resuelto_por_id:
        return False
    usuario = (db.query(m.Usuario)
               .filter_by(persona_id=caso.reportado_por_id, activo=True).first())
    if not usuario:
        return False
    lengua = acceso_por_correo.idioma_de(usuario)
    zona = contexto_de(caso).get("zona")
    dia = (ta.dia_largo(caso.reportado_en.astimezone(reloj.zona(zona)).date(), lengua)
           if caso.reportado_en else "")
    asunto = ta.t(lengua, "falla_resuelta_asunto")
    cuerpo = ta.t(lengua, "falla_resuelta_cuerpo", dia=dia)
    en_la_app = usuario.rol == m.Rol.PERSONAL_SEGURIDAD
    _correo(db, usuario, asunto, cuerpo,
            [(ta.t(lengua, "falla_lo_que_reportaste"), _corto(caso.que_se_vio, 300)),
             (ta.t(lengua, "falla_causa"), _corto(caso.causa, 300)),
             (ta.t(lengua, "falla_como"), _corto(caso.solucion, 300))],
            None, lengua)
    _push(db, usuario.persona_id, asunto, cuerpo,
          "/app/#/yo" if en_la_app else "/consola/", f"falla-{caso.id}")
    return True

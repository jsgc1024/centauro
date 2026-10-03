"""El correo que sale de la empresa.

Hasta hoy los avisos se escribian en `Notificacion` y ahi se quedaban.
El modelo lo decia desde el primer dia --"en el demo se registra; el
envio real se conecta despues"-- y seguia siendo cierto: la encuesta al
ejecutivo, el aviso al consultor de que alguien trabajo su servicio en
cobertura, la hoja liberada. Todo escrito, nada entregado.

Esto es el despachador. Lo que NO es: un sistema de plantillas. El
cuerpo del aviso lo escribe quien lo origina, que es el que sabe que hay
que decir; aqui solo se entrega.

**La costura.** Se habla SMTP y no la API de ningun proveedor. SMTP lo
hablan todos --SES, Postmark, Mailgun, Google Workspace, el servidor de
la casa-- asi que elegir proveedor es llenar cuatro renglones del `.env`
y no cambiar codigo. El dia que haga falta uno que solo hable HTTP, la
unica funcion que se reescribe es `entregar()`.

**Microsoft 365** (seccion 67). El correo de Centauro sale del buzon de
la empresa, y Microsoft apaga el SMTP con usuario y contrasena el 31 de
diciembre de 2026. Asi que ese camino no va por SMTP: va por Microsoft
Graph, con la aplicacion registrada en Entra y un permiso que solo deja
mandar desde el buzon de `CORREO_DE`. Se arma el mismo mensaje --texto y
HTML-- y se le entrega a Graph tal cual; lo demas no se entera.

**Apagado por omision.** Sin a donde mandar --SMTP o Microsoft-- y sin
`CORREO_DE` no sale nada: el aviso se queda pendiente y espera. Y desde
la seccion 86, tampoco sin `CORREO_ENCENDIDO=si`: la llave se pone y se
prueba con el correo apagado, y se enciende cuando ya salio la prueba. Un sistema que se cree configurado
y no lo esta es peor que uno apagado, porque nadie va a buscar el correo
que nunca llego.

**Se reintenta, pero no para siempre.** Un proveedor caido se levanta;
una direccion mal escrita no se arregla sola. Despues de TOPE_INTENTOS
el aviso queda en fallida, con lo ultimo que dijo el proveedor escrito
al lado, y deja de gastar la cola.
"""
import base64
import re
import smtplib
import socket
import ssl
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import correo_html
from app import encuestas_html
from app import models as m
from app import textos_aviso as ta
from app.config import settings

# Cuantas veces se intenta antes de darlo por perdido, cuando la falla
# no es del proveedor ni del destinatario (un error nuestro al armar el
# correo). Las otras dos tienen su regla propia (seccion 100): el
# destinatario que rechaza es fallida a la primera --volver a mandar a
# una direccion que no existe no la crea--, y el proveedor caido se
# reintenta con espera creciente mientras el aviso viva. Con cinco
# intentos parejos, una caida de veinticinco minutos dejaba toda la
# cola fallida y nadie podia reintentarla.
TOPE_INTENTOS = 5

# La espera antes de volver a intentar con el proveedor caido, por
# intento: 5, 15, 45 minutos y luego cada dos horas, hasta que el aviso
# venza.
ESPERAS_MINUTOS = (5, 15, 45, 120)

# Cuantos se despachan por vuelta. La cola se vacia en varias pasadas en
# vez de en una sola que tarda diez minutos y bloquea al worker.
POR_VUELTA = 50

# Cuanto vive un aviso desde que se escribe. Pasado esto no se manda:
# queda en "vencida" y se ve en el estado de la cola.
#
# Decision de Salvador (20 sep). Los diez avisos son operativos --llego
# al punto, faltan 30 minutos, termino el servicio, task sheet nuevo-- y
# ninguno sirve al dia siguiente. Un correo que dice "su equipo de
# seguridad esta en el lugar" de un servicio de hace un mes no es un
# correo tarde: es un correo que hace dudar de todo el sistema.
#
# Muerde dos dias distintos. El primero, cuando se enciendan las
# credenciales: hay semanas de avisos escritos esperando, y sin esto
# saldrian todos de golpe a clientes reales. Y despues, cada vez que el
# proveedor se caiga mas de un dia.
HORAS_DE_VIDA = 24

# Los avisos que viven lo que vive su enlace, y no las 24 horas: la
# invitacion de acceso (72 h), el enlace de "olvide mi contrasena", la
# encuesta y su recordatorio (15 dias). Con el correo apagado y los
# accesos repartiendose, las invitaciones de hace dos dias morian en la
# cola al encender aunque su enlace siguiera vigente (seccion 100). La
# decision del 20 sep fue sobre los avisos operativos, no sobre estos.
CON_VIDA_PROPIA = {"acceso_invitacion", "acceso_recuperacion",
                   "encuesta", "encuesta_recordatorio",
                   # El acceso a la app del cliente de la Central
                   # (seccion 133): vive lo que vive su enlace.
                   "ci_invitacion", "ci_recuperacion"}


# Microsoft Graph: de donde sale el permiso y a donde se entrega.
LOGIN_MICROSOFT = "https://login.microsoftonline.com"
GRAPH = "https://graph.microsoft.com/v1.0"
# El permiso dura una hora; se pide otro cinco minutos antes, para que no
# venza a media vuelta.
MARGEN_TOKEN = 300
_token_microsoft = {"valor": None, "vence": 0.0}


def por_microsoft() -> bool:
    """Si el correo sale por Microsoft 365. Con los tres datos de la
    aplicacion puestos manda Microsoft, aunque haya SMTP configurado."""
    return bool(settings.correo_ms_tenant and settings.correo_ms_cliente
                and settings.correo_ms_secreto)


def listo() -> bool:
    """Si hay a donde entregar: el proveedor --SMTP o Microsoft-- y de
    donde sale. Es lo que prueba `probar_correo.py`."""
    return bool((settings.correo_host or por_microsoft())
                and settings.correo_de)


def encendido() -> bool:
    """Si el interruptor dice que salga (seccion 86): CORREO_ENCENDIDO=si."""
    return (settings.correo_encendido or "").strip().lower() in (
        "si", "s\u00ed", "yes", "true", "1")


# Los papeles de la empresa. Los otros dos --quien solicita y el
# ejecutivo-- son del cliente.
INTERNOS = (m.Destinatario.CENTRAL, m.Destinatario.CONSULTOR,
            m.Destinatario.PERSONAL, m.Destinatario.COLABORADOR)


def solo_internos() -> bool:
    """La primera etapa (29 sep): sale solo lo de la gente de la empresa;
    lo de los clientes espera. CORREO_SOLO_INTERNOS=si."""
    return (settings.correo_solo_internos or "").strip().lower() in (
        "si", "sí", "yes", "true", "1")


def configurado() -> bool:
    """Si el correo del sistema sale: listo y encendido. Sin esto, la cola
    solo se acumula."""
    return encendido() and listo()


def con_dominio(enlace: str | None) -> str | None:
    """El enlace, con el dominio delante.

    Dentro del sistema los enlaces son rutas --`/encuestas/pagina/abc`--
    porque el navegador ya sabe de donde cuelgan. En un correo no: ahi
    una ruta sola no lleva a ningun lado.
    """
    if not enlace or enlace.startswith("http"):
        return enlace
    raiz = (settings.url_publica or "").rstrip("/")
    return f"{raiz}{enlace}" if raiz else None


# Una imagen metida en el HTML como texto: el logo de la cabecera.
IMAGEN_ADENTRO = re.compile(
    r'src="data:(image/[a-z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)"')


def imagenes_pegadas(html: str) -> tuple[str, list]:
    """El HTML con cada imagen `data:` cambiada por una pegada al correo.

    El armazon incrusta el logo como texto --asi la hoja y la vista
    previa no dependen de internet--, pero Gmail y Outlook no pintan esa
    forma: el correo llegaba sin logo justo en los dos buzones que mas
    se usan (seccion 76). Pegada al mensaje con su Content-ID, la pintan
    todos. La misma imagen dos veces va una sola vez.

    Devuelve (html, [(bytes, tipo, subtipo, cid)]); el cid va con sus
    <> y en el HTML sin ellos, como pide el estandar.
    """
    pegadas, vistas = [], {}

    def pegar(encontrada):
        tipo, datos = encontrada.group(1), "".join(encontrada.group(2).split())
        if (tipo, datos) not in vistas:
            cid = make_msgid(domain="centauro.lat")
            vistas[(tipo, datos)] = cid
            principal, secundario = tipo.split("/", 1)
            pegadas.append((base64.b64decode(datos), principal, secundario, cid))
        return f'src="cid:{vistas[(tipo, datos)][1:-1]}"'

    return IMAGEN_ADENTRO.sub(pegar, html), pegadas


def entregar(destino: str, asunto: str, cuerpo: str,
             html: str | None = None) -> None:
    """La unica funcion que sabe de SMTP. Revienta si no pudo.

    Lo que revienta aqui lo atrapa `despachar` y lo guarda en el aviso:
    de eso vive el `ultimo_error`, que es lo que despues explica si fue
    la direccion, la clave o el buzon lleno.

    Las dos versiones van en el mismo mensaje y el buzon elige: el texto
    primero, el HTML como alternativa. Asi el que bloquea HTML lee el
    aviso completo en vez de un mensaje vacio.
    """
    mensaje = EmailMessage()
    mensaje["From"] = settings.correo_de
    mensaje["To"] = destino
    mensaje["Subject"] = asunto
    # Seccion 84: el servicio de envio no tiene buzon; lo que contesten
    # llega a una persona.
    if settings.correo_responder_a:
        mensaje["Reply-To"] = settings.correo_responder_a
    # El charset, dicho: el acento de "Proteccion" viaja en dos bytes y
    # el buzon que no sabe cual es el juego de caracteres los pinta como
    # basura. Va aqui y tambien dentro del HTML, porque hay clientes que
    # miran uno y clientes que miran el otro.
    mensaje.set_content(cuerpo, charset="utf-8")
    if html:
        html, pegadas = imagenes_pegadas(html)
        mensaje.add_alternative(html, subtype="html", charset="utf-8")
        parte_html = mensaje.get_payload()[-1]
        for datos, principal, secundario, cid in pegadas:
            parte_html.add_related(datos, maintype=principal,
                                   subtype=secundario, cid=cid,
                                   disposition="inline")

    if por_microsoft():
        _por_microsoft(mensaje)
        return
    with smtplib.SMTP(settings.correo_host, settings.correo_puerto,
                      timeout=20) as servidor:
        # Con el certificado comprobado: sin `context`, starttls no
        # verifica con quien habla y la llave SMTP de Amazon era la unica
        # credencial del sistema que salia asi (seccion 100).
        servidor.starttls(context=ssl.create_default_context())
        if settings.correo_usuario:
            servidor.login(settings.correo_usuario, settings.correo_clave)
        servidor.send_message(mensaje)


def _lo_que_dijo(respuesta: httpx.Response) -> str:
    """El porque de un rechazo de Microsoft, corto y legible.

    Es lo que queda en el `ultimo_error` del aviso: ahi se lee si fue el
    secreto vencido, el permiso que falta o el buzon que no existe. Nunca
    trae el secreto ni el permiso: Microsoft no los repite.
    """
    try:
        datos = respuesta.json()
    except ValueError:
        return respuesta.text[:200]
    falla = datos.get("error")
    if isinstance(falla, dict):             # Graph
        return f"{falla.get('code')}: {falla.get('message')}"[:200]
    return f"{falla}: {datos.get('error_description', '')}"[:200]


def _permiso_de_microsoft(renovar: bool = False) -> str:
    """El permiso para mandar, pedido con el secreto de la aplicacion.

    Se guarda mientras dura: pedirlo por cada correo es una vuelta mas a
    Microsoft por nada, y con muchos avisos juntos, un freno.
    """
    ahora = time.monotonic()
    if (not renovar and _token_microsoft["valor"]
            and ahora < _token_microsoft["vence"]):
        return _token_microsoft["valor"]
    respuesta = httpx.post(
        f"{LOGIN_MICROSOFT}/{settings.correo_ms_tenant}/oauth2/v2.0/token",
        data={"client_id": settings.correo_ms_cliente,
              "client_secret": settings.correo_ms_secreto,
              "scope": "https://graph.microsoft.com/.default",
              "grant_type": "client_credentials"},
        timeout=20)
    if respuesta.status_code != 200:
        raise RuntimeError(
            f"Microsoft no dio el permiso para mandar "
            f"({respuesta.status_code}) {_lo_que_dijo(respuesta)}")
    datos = respuesta.json()
    _token_microsoft["valor"] = datos["access_token"]
    _token_microsoft["vence"] = (ahora + int(datos.get("expires_in", 3600))
                                 - MARGEN_TOKEN)
    return _token_microsoft["valor"]


def _por_microsoft(mensaje: EmailMessage) -> None:
    """Entrega el mensaje armado a Microsoft Graph, en MIME.

    Va el mismo mensaje que iria por SMTP --texto y HTML en uno--, en
    base64, al buzon de `correo_de`. Microsoft lo deja en Enviados de ese
    buzon. Si el permiso guardado ya no sirve, se pide otro una vez.
    """
    remitente = parseaddr(settings.correo_de)[1]
    cuerpo = base64.b64encode(
        mensaje.as_bytes(policy=mensaje.policy.clone(linesep="\r\n")))
    for intento in (1, 2):
        respuesta = httpx.post(
            f"{GRAPH}/users/{remitente}/sendMail", content=cuerpo,
            headers={"Authorization":
                     f"Bearer {_permiso_de_microsoft(renovar=intento == 2)}",
                     "Content-Type": "text/plain"},
            timeout=30)
        if respuesta.status_code != 401:
            break
    if respuesta.status_code >= 300:
        raise RuntimeError(
            f"Microsoft no acepto el correo ({respuesta.status_code}) "
            f"{_lo_que_dijo(respuesta)}")


def cuerpo_con_enlace(aviso: m.Notificacion) -> str:
    """El cuerpo tal cual, con el enlace al final si lo trae."""
    liga = con_dominio(aviso.enlace_seguimiento)
    return f"{aviso.cuerpo}\n\n{liga}" if liga else aviso.cuerpo


# Lo que dice el boton, por ruta. El texto del boton no es decoracion:
# dice a donde lleva, y de eso depende que lo piquen. Un aviso sin
# enlace no lleva boton --uno que no lleva a nada ensena a no picar
# ninguno.
BOTONES = (
    ("/seguimiento/", "boton_seguir"),
    ("/encuestas/", "boton_encuesta"),
)


def _boton_de(enlace: str | None, idioma: str | None = None) -> tuple | None:
    liga = con_dominio(enlace)
    if not liga:
        return None
    for trozo, clave in BOTONES:
        if trozo in liga:
            return (ta.t(idioma, clave), liga)
    return (ta.t(idioma, "boton_abrir"), liga)


def _nota_de(aviso: m.Notificacion) -> str | None:
    """El renglon chico de abajo. Hoy solo lo que vence.

    Se dice antes de que alguien guarde el correo creyendo que le sirve
    manana: el enlace de seguimiento muere con el servicio.
    """
    if not aviso.expira_en or not aviso.enlace_seguimiento:
        return None
    return ta.t(aviso.idioma, "enlace_vence",
                cuando=f"{aviso.expira_en:%d/%m/%Y %H:%M}")


def _folio_de(db: Session, aviso: m.Notificacion) -> str | None:
    if not aviso.servicio_id:
        return None
    servicio = db.get(m.Servicio, aviso.servicio_id)
    return servicio.folio if servicio else None


def _encuesta_de(db: Session, aviso: m.Notificacion):
    """La encuesta de este aviso, por el token de su enlace."""
    if not aviso.enlace_seguimiento:
        return None
    token = aviso.enlace_seguimiento.rstrip("/").rsplit("/", 1)[-1]
    return db.query(m.Encuesta).filter_by(token=token).first()


def versiones(db: Session, aviso: m.Notificacion) -> tuple:
    """(texto plano, HTML) del aviso. Las dos salen en el mismo mensaje.

    La encuesta tiene su propio correo, escrito desde hace meses y en
    tres idiomas: ahi las estrellas se pican desde el mensaje, y meterlo
    en el armazon general seria pedirle lo mismo con menos.
    """
    if aviso.plantilla in ("acceso_invitacion", "acceso_recuperacion"):
        # La invitacion y la recuperacion de contrasena: el boton y la
        # nota dependen de cual es, y la hora que vence se dice en la
        # del pais de quien lo recibe (ver `acceso_por_correo`).
        from app import acceso_por_correo
        return acceso_por_correo.versiones(db, aviso)

    if aviso.plantilla in ("ci_invitacion", "ci_recuperacion"):
        # El acceso a la app del cliente de la Central (seccion 133).
        from app import cliente_ci
        return cliente_ci.versiones(db, aviso)

    if aviso.plantilla in ("encuesta", "encuesta_recordatorio"):
        encuesta = _encuesta_de(db, aviso)
        liga = con_dominio(aviso.enlace_seguimiento)
        if encuesta and liga:
            # El recordatorio usa el mismo armazon --las estrellas se
            # pican desde el mensaje-- mas un parrafo que dice que es el
            # segundo intento y cuando se cierra. Sin eso llegaba
            # identico al primero.
            texto = (aviso.cuerpo
                     if aviso.plantilla == "encuesta_recordatorio" else "")
            return (cuerpo_con_enlace(aviso),
                    encuestas_html.correo(encuesta, liga, recordatorio=texto))
        # Sin encuesta o sin dominio publico no hay a donde mandar a
        # nadie: sale el texto y ya. No se inventa un boton muerto.
        return cuerpo_con_enlace(aviso), None

    pares = correo_html.leer_datos(aviso.datos)
    folio = _folio_de(db, aviso)
    boton = _boton_de(aviso.enlace_seguimiento, aviso.idioma)
    nota = _nota_de(aviso)
    texto = correo_html.plano(aviso.asunto, aviso.cuerpo, folio=folio,
                              pares=pares, boton=boton, nota=nota)
    html = correo_html.armar(aviso.asunto, aviso.cuerpo, folio=folio,
                             pares=pares, boton=boton, nota=nota)
    return texto, html


def vencio(aviso: m.Notificacion, ahora: datetime | None = None) -> bool:
    """Si este aviso ya no tiene sentido mandarlo.

    Dos motivos. El primero es la edad: pasadas HORAS_DE_VIDA desde que
    se escribio, lo que dice ya paso.

    El segundo es el enlace: un aviso cuyo enlace ya murio --el
    seguimiento en vivo, la encuesta-- llegaria con un boton que no
    lleva a ningun lado, y eso es peor que no llegar.
    """
    ahora = ahora or datetime.now(timezone.utc)
    if aviso.expira_en is not None:
        # expira_en se guarda en hora de pared; se compara contra la
        # misma vara con la que se escribio.
        if aviso.expira_en < ahora.astimezone().replace(tzinfo=None):
            return True
        # Y para estos, esa es toda su vida (ver CON_VIDA_PROPIA).
        if aviso.plantilla in CON_VIDA_PROPIA:
            return False
    nacio = aviso.enviada_en
    if nacio is None:
        return False
    if nacio.tzinfo is None:
        nacio = nacio.replace(tzinfo=timezone.utc)
    return (ahora - nacio) > timedelta(hours=HORAS_DE_VIDA)


def pendientes(db: Session, limite: int = POR_VUELTA, solo=None,
               bloquear: bool = False) -> list:
    """Lo que falta por salir.

    `solo` limita a unos avisos en particular: el correo de acceso sale
    al guardar y no espera a la vuelta de cinco minutos.

    `bloquear` es para quien los va a mandar. Desde que ese correo sale
    al guardar puede haber dos despachadores a la vez --el de la vuelta
    y el del alta--, y sin esto los dos tomarian el mismo aviso y saldria
    dos veces. Cada uno se queda con los que el otro no tiene tomados.
    """
    consulta = db.query(m.Notificacion).filter(
        m.Notificacion.estado == "pendiente",
        # El que espera su reintento no se toma antes de tiempo.
        or_(m.Notificacion.reintentar_en.is_(None),
            m.Notificacion.reintentar_en <= datetime.now()))
    if solo is not None:
        consulta = consulta.filter(m.Notificacion.id.in_(list(solo)))
    # En la primera etapa lo de los clientes ni se toma: se queda en la
    # cola sin gastar el cupo de la vuelta, y vencer_lo_viejo lo vence a
    # su hora como a cualquier otro.
    if solo_internos():
        consulta = consulta.filter(m.Notificacion.destinatario.in_(INTERNOS))
    consulta = consulta.order_by(m.Notificacion.id).limit(limite)
    if bloquear:
        consulta = consulta.with_for_update(skip_locked=True)
    return consulta.all()


def despachar(db: Session, limite: int = POR_VUELTA, solo=None) -> dict:
    """Saca lo que este pendiente. Devuelve la cuenta de la vuelta.

    Con `solo`, saca nada mas esos avisos (ver `pendientes`)."""
    if not configurado():
        return {"configurado": False, "enviados": 0, "fallidos": 0,
                "pendientes": db.query(m.Notificacion)
                                .filter(m.Notificacion.estado == "pendiente")
                                .count()}

    # Lo vencido se marca de una vez, sin gastar el cupo de la vuelta:
    # el dia que se encienda el correo hay cientos de avisos viejos, y
    # el operativo escrito hoy esperaba dieciseis vueltas detras de
    # ellos (seccion 100).
    vencidos = vencer_lo_viejo(db) if solo is None else 0
    db.commit()

    enviados, fallidos, sin_correo = 0, 0, 0
    for aviso in pendientes(db, limite, solo=solo, bloquear=True):
        if vencio(aviso):
            # No se borra: queda dicho que se escribio y no salio. "No
            # llego el correo" y "no se mando" son dos conversaciones
            # distintas, y la pantalla tiene que poder separarlas.
            aviso.estado = "vencida"
            vencidos += 1
        elif not aviso.correo:
            # Un aviso sin direccion no es un error del proveedor: es un
            # aviso que no tenia a donde ir. Se aparta para que no ande
            # dando vueltas en la cola para siempre.
            aviso.estado = "sin_correo"
            sin_correo += 1
        else:
            aviso.intentos = (aviso.intentos or 0) + 1
            try:
                texto, html = versiones(db, aviso)
                entregar(aviso.correo, aviso.asunto, texto, html)
                aviso.estado = "enviada"
                aviso.salio_en = datetime.now()
                aviso.ultimo_error = None
                aviso.reintentar_en = None
                enviados += 1
            except Exception as falla:               # noqa: BLE001
                if _anotar_falla(aviso, falla):
                    fallidos += 1
        # Uno por uno, no al final del lote: un reinicio del worker a
        # media vuelta --el despliegue lo mata a los diez segundos--
        # dejaba sin marcar los ya entregados, y al levantar salian
        # otra vez (seccion 100). El candado por fila sigue valiendo.
        db.commit()
    return {"configurado": True, "enviados": enviados, "fallidos": fallidos,
            "sin_correo": sin_correo, "vencidos": vencidos,
            "pendientes": db.query(m.Notificacion)
                            .filter(m.Notificacion.estado == "pendiente")
                            .count()}


def _anotar_falla(aviso: m.Notificacion, falla: Exception) -> bool:
    """Que hacer con un aviso que no salio. True si quedo fallido.

    Tres fallas distintas (seccion 100). El destinatario que rechaza:
    fallida a la primera, porque volver a mandar a una direccion que no
    existe no la crea. El proveedor caido o la red: se reintenta con
    espera creciente mientras el aviso viva. Lo demas --un error
    nuestro al armar el correo-- cuenta intentos como siempre.
    """
    aviso.ultimo_error = str(falla)[:300]
    if _rechazo_del_destinatario(falla):
        aviso.estado = "fallida"
        return True
    if _proveedor_caido(falla):
        paso = min(aviso.intentos or 1, len(ESPERAS_MINUTOS)) - 1
        aviso.reintentar_en = (datetime.now()
                               + timedelta(minutes=ESPERAS_MINUTOS[paso]))
        return False
    if aviso.intentos >= TOPE_INTENTOS:
        aviso.estado = "fallida"
        return True
    return False


def _rechazo_del_destinatario(falla: Exception) -> bool:
    """El servidor de correo dijo que no a ESTA direccion."""
    if isinstance(falla, (smtplib.SMTPRecipientsRefused,
                          smtplib.SMTPSenderRefused)):
        return True
    if isinstance(falla, smtplib.SMTPDataError):
        return 500 <= falla.smtp_code < 600
    texto = str(falla).lower()
    # Microsoft contesta con un 4xx propio cuando el buzon no existe.
    return isinstance(falla, RuntimeError) and (
        "recipient" in texto or "destinatario" in texto
        or "invalid" in texto and "address" in texto)


def _proveedor_caido(falla: Exception) -> bool:
    """No se pudo hablar con el proveedor, o contesto que ahora no."""
    if isinstance(falla, (smtplib.SMTPConnectError,
                          smtplib.SMTPServerDisconnected,
                          smtplib.SMTPHeloError,
                          smtplib.SMTPAuthenticationError,
                          httpx.HTTPError, socket.timeout, OSError)):
        return True
    if isinstance(falla, smtplib.SMTPResponseException):
        return 400 <= falla.smtp_code < 500
    texto = str(falla).lower()
    return isinstance(falla, RuntimeError) and (
        "(5" in texto or "(429" in texto or "timeout" in texto)


def vencer_lo_viejo(db: Session, ahora: datetime | None = None) -> int:
    """Marca vencido de un golpe lo pendiente que ya no tiene sentido.

    La misma regla de `vencio`, escrita en una sola consulta: por su
    enlace los que viven lo que el vive, y por edad los demas.
    """
    ahora = ahora or datetime.now(timezone.utc)
    pared = ahora.astimezone().replace(tzinfo=None)
    N = m.Notificacion
    por_enlace = (db.query(N).filter(N.estado == "pendiente",
                                     N.expira_en.isnot(None),
                                     N.expira_en < pared)
                  .update({"estado": "vencida"}, synchronize_session=False))
    por_edad = (db.query(N).filter(N.estado == "pendiente",
                                   or_(N.plantilla.is_(None),
                                       N.plantilla.notin_(CON_VIDA_PROPIA)),
                                   N.enviada_en < ahora - timedelta(hours=HORAS_DE_VIDA))
                .update({"estado": "vencida"}, synchronize_session=False))
    return por_enlace + por_edad


def reintentar_fallidas(db: Session) -> int:
    """Lo fallido vuelve a la cola, desde la pantalla (seccion 100).

    Sale en la siguiente vuelta; lo que ya vencio se marca vencido ahi
    mismo en vez de salir tarde. Se aparta lo que rechazo el propio
    destinatario: la direccion no va a existir por insistir.
    """
    filas = (db.query(m.Notificacion)
             .filter(m.Notificacion.estado == "fallida").all())
    cuantos = 0
    for aviso in filas:
        if vencio(aviso):
            aviso.estado = "vencida"
            continue
        aviso.estado = "pendiente"
        aviso.intentos = 0
        aviso.reintentar_en = None
        cuantos += 1
    return cuantos


def estado(db: Session) -> dict:
    """Como esta la cola. Es lo que se mira cuando alguien dice que no
    le llego nada."""
    cuenta = {}
    for fila in db.query(m.Notificacion.estado,
                         m.Notificacion.id).all():
        cuenta[fila[0] or "pendiente"] = cuenta.get(fila[0] or "pendiente", 0) + 1
    # Lo que se mira antes de encender: de la cola pendiente, cuantos
    # saldrian y cuantos ya no. El numero de "viejos" es el que dice si
    # hay que mirar la cola antes de poner las credenciales.
    en_espera = pendientes(db, limite=1000)
    viejos = sum(1 for a in en_espera if vencio(a))
    # Las fallidas que cuentan son las de hoy: una direccion mal escrita
    # de hace tres meses no es una falla de hoy, y la tarjeta decia "con
    # fallas" de por vida (seccion 100).
    recientes = (db.query(m.Notificacion)
                 .filter(m.Notificacion.estado == "fallida",
                         m.Notificacion.enviada_en
                         >= datetime.now(timezone.utc) - timedelta(hours=24))
                 .count())
    return {
        "fallidas_recientes": recientes,
        "configurado": configurado(),
        "listo": listo(),
        "encendido": encendido(),
        "desde": settings.correo_de or None,
        "por": ("microsoft" if por_microsoft()
                else "smtp" if settings.correo_host else None),
        "servidor": ("graph.microsoft.com" if por_microsoft()
                     else settings.correo_host or None),
        "url_publica": settings.url_publica or None,
        "horas_de_vida": HORAS_DE_VIDA,
        "saldrian": len(en_espera) - viejos,
        "viejos": viejos,
        # La etapa (29 sep): con solo internos, `saldrian` cuenta lo de la
        # empresa y `retenidos` lo de los clientes que espera.
        "solo_internos": solo_internos(),
        "retenidos": (db.query(m.Notificacion)
                      .filter(m.Notificacion.estado == "pendiente",
                              m.Notificacion.destinatario.notin_(INTERNOS))
                      .count() if solo_internos() else 0),
        "avisos": cuenta,
    }

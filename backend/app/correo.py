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

**Apagado por omision.** Sin `CORREO_HOST` y `CORREO_DE` no sale nada:
el aviso se queda pendiente y espera. Un sistema que se cree configurado
y no lo esta es peor que uno apagado, porque nadie va a buscar el correo
que nunca llego.

**Se reintenta, pero no para siempre.** Un proveedor caido se levanta;
una direccion mal escrita no se arregla sola. Despues de TOPE_INTENTOS
el aviso queda en fallida, con lo ultimo que dijo el proveedor escrito
al lado, y deja de gastar la cola.
"""
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app import correo_html
from app import encuestas_html
from app import models as m
from app import textos_aviso as ta
from app.config import settings

# Cuantas veces se intenta antes de darlo por perdido. Cinco cubre el
# proveedor que se cae un rato; mas que eso ya no es el proveedor.
TOPE_INTENTOS = 5

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


def configurado() -> bool:
    """Si hay a donde entregar. Sin esto, la cola solo se acumula."""
    return bool(settings.correo_host and settings.correo_de)


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
    # El charset, dicho: el acento de "Proteccion" viaja en dos bytes y
    # el buzon que no sabe cual es el juego de caracteres los pinta como
    # basura. Va aqui y tambien dentro del HTML, porque hay clientes que
    # miran uno y clientes que miran el otro.
    mensaje.set_content(cuerpo, charset="utf-8")
    if html:
        mensaje.add_alternative(html, subtype="html", charset="utf-8")

    with smtplib.SMTP(settings.correo_host, settings.correo_puerto,
                      timeout=20) as servidor:
        servidor.starttls()
        if settings.correo_usuario:
            servidor.login(settings.correo_usuario, settings.correo_clave)
        servidor.send_message(mensaje)


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
    nacio = aviso.enviada_en
    if nacio is None:
        return False
    if nacio.tzinfo is None:
        nacio = nacio.replace(tzinfo=timezone.utc)
    return (ahora - nacio) > timedelta(hours=HORAS_DE_VIDA)


def pendientes(db: Session, limite: int = POR_VUELTA) -> list:
    return (db.query(m.Notificacion)
            .filter(m.Notificacion.estado == "pendiente")
            .order_by(m.Notificacion.id)
            .limit(limite).all())


def despachar(db: Session, limite: int = POR_VUELTA) -> dict:
    """Saca lo que este pendiente. Devuelve la cuenta de la vuelta."""
    if not configurado():
        return {"configurado": False, "enviados": 0, "fallidos": 0,
                "pendientes": db.query(m.Notificacion)
                                .filter(m.Notificacion.estado == "pendiente")
                                .count()}

    enviados, fallidos, sin_correo, vencidos = 0, 0, 0, 0
    for aviso in pendientes(db, limite):
        if vencio(aviso):
            # No se borra: queda dicho que se escribio y no salio. "No
            # llego el correo" y "no se mando" son dos conversaciones
            # distintas, y la pantalla tiene que poder separarlas.
            aviso.estado = "vencida"
            vencidos += 1
            continue
        if not aviso.correo:
            # Un aviso sin direccion no es un error del proveedor: es un
            # aviso que no tenia a donde ir. Se aparta para que no ande
            # dando vueltas en la cola para siempre.
            aviso.estado = "sin_correo"
            sin_correo += 1
            continue
        aviso.intentos = (aviso.intentos or 0) + 1
        try:
            texto, html = versiones(db, aviso)
            entregar(aviso.correo, aviso.asunto, texto, html)
            aviso.estado = "enviada"
            aviso.salio_en = datetime.now()
            aviso.ultimo_error = None
            enviados += 1
        except Exception as falla:               # noqa: BLE001
            aviso.ultimo_error = str(falla)[:300]
            if aviso.intentos >= TOPE_INTENTOS:
                aviso.estado = "fallida"
                fallidos += 1
    db.commit()
    return {"configurado": True, "enviados": enviados, "fallidos": fallidos,
            "sin_correo": sin_correo, "vencidos": vencidos,
            "pendientes": db.query(m.Notificacion)
                            .filter(m.Notificacion.estado == "pendiente")
                            .count()}


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
    return {
        "configurado": configurado(),
        "desde": settings.correo_de or None,
        "servidor": settings.correo_host or None,
        "url_publica": settings.url_publica or None,
        "horas_de_vida": HORAS_DE_VIDA,
        "saldrian": len(en_espera) - viejos,
        "viejos": viejos,
        "avisos": cuenta,
    }

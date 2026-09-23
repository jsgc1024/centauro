"""La invitacion y la recuperacion, por correo.

Hasta hoy los dos enlaces de contrasena se generaban y se quedaban en la
base: la invitacion de quien acaba de entrar y el "olvide mi
contrasena". Los entregaba administracion a mano, copiandolos del panel,
porque el sistema no sabia mandar un correo que no fuera sobre un
servicio. Ahora salen por correo, con tres reglas:

**Solo a quien trabaja en la consola.** Administracion, consultores,
central, finanzas, recursos humanos y direccion: su correo es de la
empresa. El personal de seguridad no: su correo es personal, la empresa
no lo controla, y lo suyo sigue siendo el codigo de cuatro digitos que
le dicta su consultor o la central (`contrasenas.POR_CORREO`). Quien
decide si un correo sale es quien lo pide; aqui solo se escribe.

**Sale al guardar, no en la siguiente vuelta.** El despachador pasa
cada cinco minutos, y para esto es mucho: quien pidio el enlace esta
frente a la pantalla esperandolo. En cuanto se confirma el alta o el
pedido se despacha ese correo y solo ese, en segundo plano --la
respuesta ya salio, asi que nada espera a que el proveedor conteste--.
La vuelta de cinco minutos sigue siendo la red: si el proveedor no
contesta, la reintenta ella.

**El enlace vive en la consola, detras del "#".**
`/#/crear-contrasena/...` y no `/crear-contrasena/...`: lo que va
despues del "#" el navegador no lo manda al servidor, asi que el token
no queda escrito en ninguna bitacora de acceso del camino.
"""
import logging
from email.utils import parseaddr

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app import correo, correo_html, reloj
from app import models as m
from app import textos_aviso as ta
from app.config import settings
from app.db import SessionLocal

registro = logging.getLogger("centauro.acceso")

# Las dos caras del correo de acceso. Son plantillas y no el armazon
# general porque el boton y la nota de abajo dependen de cual es.
INVITACION = "acceso_invitacion"
RECUPERACION = "acceso_recuperacion"
PLANTILLAS = (INVITACION, RECUPERACION)


def ruta(token: str) -> str:
    return f"/#/crear-contrasena/{token}"


def enlace(token: str) -> str:
    """El enlace completo si hay dominio publico; si no, la ruta, que
    desde la misma consola tambien lleva."""
    return correo.con_dominio(ruta(token)) or ruta(token)


def encendido() -> bool:
    """Si el correo de acceso de verdad sale.

    Hace falta el proveedor y tambien el dominio: sin `URL_PUBLICA` el
    correo llegaria con un boton que no lleva a ningun lado.
    """
    return correo.configurado() and bool((settings.url_publica or "").strip())


def remitente() -> str | None:
    """La direccion de la que sale, sin el nombre: "ai@centauro.lat"."""
    return parseaddr(settings.correo_de or "")[1] or None


def _pais(usuario: m.Usuario | None) -> m.Pais | None:
    persona = usuario.persona if usuario else None
    return persona.plaza.pais if persona and persona.plaza else None


def idioma_de(usuario: m.Usuario) -> str:
    """El idioma de su pais, la misma regla de la app de campo."""
    pais = _pais(usuario)
    return pais.idioma if pais and pais.idioma else "es"


def escribir(db: Session, usuario: m.Usuario,
             invitacion: m.Invitacion) -> m.Notificacion:
    """Deja escrito el correo de este enlace. Salir, sale despues."""
    lengua = idioma_de(usuario)
    nombre = ((usuario.persona.nombre if usuario.persona else "")
              or "").split()
    primero = nombre[0] if nombre else usuario.correo.split("@")[0]

    if invitacion.tipo == m.TipoInvitacion.INVITACION:
        plantilla = INVITACION
        asunto = ta.t(lengua, "acc_inv_asunto")
        cuerpo = ta.t(lengua, "acc_inv_cuerpo", nombre=primero)
        pares = [(ta.t(lengua, "acc_tu_correo"), usuario.correo),
                 (ta.t(lengua, "acc_entras_como"),
                  ta.t(lengua, f"rol_{usuario.rol.value}"))]
    else:
        plantilla = RECUPERACION
        asunto = ta.t(lengua, "acc_rec_asunto")
        cuerpo = ta.t(lengua, "acc_rec_cuerpo")
        pares = [(ta.t(lengua, "acc_tu_correo"), usuario.correo)]

    aviso = m.Notificacion(
        destinatario=m.Destinatario.COLABORADOR, canal=m.Canal.CORREO,
        correo=usuario.correo, idioma=lengua, asunto=asunto,
        cuerpo=cuerpo, datos=correo_html.guardar_datos(pares),
        enlace_seguimiento=ruta(invitacion.token), plantilla=plantilla,
        # El correo vive lo que vive su enlace: pasada esa hora ya no
        # sale, porque llegaria con un boton muerto.
        expira_en=invitacion.expira_en)
    db.add(aviso)
    db.flush()
    return aviso


def retirar_pendientes(db: Session, usuario: m.Usuario) -> int:
    """Los correos de acceso de esa persona que no han salido y ya no
    sirven.

    Un enlace nuevo mata a los anteriores, y usar uno los mata a todos.
    Si su correo todavia no salio --el proveedor estaba caido, o el
    reloj no ha pasado--, tampoco debe salir: llegaria con un enlace
    muerto, que es peor que no llegar.

    No espera a nadie: el que se esta mandando en este momento lo tiene
    tomado el despachador, y ese ya va a salir de todas formas.
    """
    tomados = [fila.id for fila in (
        db.query(m.Notificacion.id)
        .filter(m.Notificacion.estado == "pendiente",
                m.Notificacion.plantilla.in_(PLANTILLAS),
                m.Notificacion.correo == usuario.correo)
        .with_for_update(skip_locked=True).all())]
    if not tomados:
        return 0
    return (db.query(m.Notificacion)
            .filter(m.Notificacion.id.in_(tomados),
                    m.Notificacion.estado == "pendiente")
            .update({"estado": "vencida"}, synchronize_session=False))


def _nota(db: Session, aviso: m.Notificacion) -> str | None:
    """Cuando deja de servir el enlace, en la hora de quien lo recibe.

    La columna guarda la hora del servidor, que esta en Mexico. A quien
    trabaja en Sao Paulo decirle "13:10" de Mexico es decirle una hora
    que no es: se convierte a la de su pais.
    """
    if not aviso.expira_en:
        return None
    usuario = db.query(m.Usuario).filter_by(correo=aviso.correo).first()
    pais = _pais(usuario)
    vence = aviso.expira_en.astimezone(
        reloj.zona(pais.zona_horaria if pais else None))
    hora = f"{vence:%H:%M}"
    if aviso.plantilla == RECUPERACION:
        return ta.t(aviso.idioma, "acc_rec_nota", hora=hora)
    return ta.t(aviso.idioma, "acc_inv_nota", hora=hora,
                dia=ta.dia_largo(vence.date(), aviso.idioma))


def versiones(db: Session, aviso: m.Notificacion) -> tuple:
    """(texto plano, HTML) del correo de acceso.

    Sin dominio publico se deja reventar a proposito: el despachador
    guarda el error al lado del aviso --"falta URL_PUBLICA"-- y lo
    reintenta. Mandarlo sin boton seria mandar un correo que pide crear
    una contrasena y no dice donde.
    """
    liga = correo.con_dominio(aviso.enlace_seguimiento)
    if not liga:
        raise RuntimeError("Falta URL_PUBLICA: el enlace del correo no "
                           "llevaria a ningun lado")
    clave = "acc_inv_boton" if aviso.plantilla == INVITACION else "acc_rec_boton"
    boton = (ta.t(aviso.idioma, clave), liga)
    pares = correo_html.leer_datos(aviso.datos)
    nota = _nota(db, aviso)
    return (correo_html.plano(aviso.asunto, aviso.cuerpo, pares=pares,
                              boton=boton, nota=nota),
            correo_html.armar(aviso.asunto, aviso.cuerpo, pares=pares,
                              boton=boton, nota=nota))


def despachar_ya(ids: list[int]) -> None:
    """Saca estos correos ahora, sin esperar la vuelta de cinco minutos.

    Corre despues de que la respuesta ya salio. Si algo falla aqui no se
    levanta nada: el aviso sigue pendiente y la vuelta de cinco minutos
    lo vuelve a intentar.
    """
    db = SessionLocal()
    try:
        correo.despachar(db, solo=ids)
    except Exception:                                   # noqa: BLE001
        db.rollback()
        registro.exception("El correo de acceso no salio al guardar; "
                           "lo reintenta la vuelta de cinco minutos")
    finally:
        db.close()


def despachar_despues(tareas: BackgroundTasks, *avisos) -> None:
    """Pide que estos correos salgan en cuanto termine la respuesta.

    Se llama despues del commit: el despachador abre su propia sesion y
    tiene que encontrar el aviso ya escrito.
    """
    ids = [a.id for a in avisos if a is not None]
    if ids and encendido():
        tareas.add_task(despachar_ya, ids)

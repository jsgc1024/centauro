"""Poner, cambiar y recuperar la contrasena.

Tres reglas sostienen todo esto:

**La contrasena nueva tira las sesiones abiertas.** Si alguien te robo la
sesion y cambias la contrasena, esperas que se salga. El token no tiene
estado, asi que sin `Usuario.sesiones_desde` el ladron seguia adentro
doce horas mas, con la contrasena ya cambiada.

**Un enlace nuevo mata a los anteriores.** Si no, el correo de
recuperacion de hace una semana sigue abriendo la cuenta.

**Pedir recuperacion no dice si la cuenta existe.** La respuesta es la
misma siempre. Decir "ese correo no esta registrado" le regala media
lista a quien esta probando.

Los enlaces --la invitacion y la recuperacion-- salen por correo a quien
trabaja en la consola (ver `acceso_por_correo`). Al personal de campo
no: lo suyo es el codigo de cuatro digitos, al final de este archivo.
"""
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import acceso_por_correo, accesos, auth
from app import models as m
from app import reloj

LARGO_MINIMO = 8
HORAS_RECUPERACION = 2

# El personal de campo no recupera por correo: su correo es personal y la
# empresa no lo controla. Si ese gmail se compromete --o si la persona
# salio hace tres meses y su gmail sigue vivo-- la recuperacion por
# correo le entrega la cuenta. Lo suyo va por su consultor.
POR_CORREO = {m.Rol.CONSULTOR, m.Rol.CENTRAL, m.Rol.FINANZAS,
              m.Rol.DIRECTOR_OPERACIONES, m.Rol.DIRECTOR_GENERAL,
              m.Rol.ADMIN, m.Rol.RECURSOS_HUMANOS}

# Los que viajan como enlace. El codigo de campo tambien vive en la
# tabla de invitaciones, pero guardado cifrado y con su propia puerta:
# no se usa como enlace aunque alguien consiguiera el renglon.
CON_ENLACE = (m.TipoInvitacion.INVITACION, m.TipoInvitacion.RECUPERACION)

# La de demostracion esta en el codigo y en la bitacora: es la primera
# que alguien va a volver a poner "para no olvidarla".
OBVIAS = {"centauro2026", "centauro", "12345678", "contrasena",
          "password", "qwertyui", "11111111", "centauro1"}


# ------------------------------------------------------------- las reglas

def validar(nueva: str, usuario: m.Usuario | None = None) -> None:
    """Lo minimo, y ni una regla mas.

    Exigir mayusculas, numeros y simbolos no hace contrasenas mas
    fuertes: hace que la gente escriba `Centauro2026!` y la pegue en un
    papel debajo del teclado. Lo que si se rechaza es lo que ya esta
    escrito en algun lado.
    """
    if len(nueva) < LARGO_MINIMO:
        raise HTTPException(400, f"La contrasena debe tener al menos "
                                 f"{LARGO_MINIMO} caracteres")
    if nueva.lower() in OBVIAS:
        raise HTTPException(400, {
            "mensaje": "Esa contrasena es de las primeras que alguien prueba.",
            "que_hacer": "Usa una frase que solo tu digas asi.",
        })
    if len(set(nueva)) < 4:
        raise HTTPException(400, "Esa contrasena tiene muy poca variedad")
    if usuario:
        local = (usuario.correo or "").split("@")[0].lower()
        if local and len(local) >= 4 and local in nueva.lower():
            raise HTTPException(400, "La contrasena no puede llevar tu correo "
                                     "adentro")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _anular_pendientes(db: Session, usuario_id: int) -> int:
    """Los enlaces vivos de esa cuenta dejan de servir.

    Y su correo, si todavia no salio, tampoco sale: llegaria con un
    enlace muerto.
    """
    vivos = (db.query(m.Invitacion)
             .filter(m.Invitacion.usuario_id == usuario_id,
                     m.Invitacion.usado_en.is_(None),
                     m.Invitacion.anulado_en.is_(None))
             .all())
    for enlace in vivos:
        enlace.anulado_en = datetime.now()
    usuario = db.get(m.Usuario, usuario_id)
    if usuario:
        acceso_por_correo.retirar_pendientes(db, usuario)
    return len(vivos)


def _asentar(db: Session, usuario: m.Usuario, nueva: str) -> None:
    """Guarda la contrasena y cierra todo lo que estaba abierto."""
    usuario.hash_contrasena = auth.cifrar(nueva)
    usuario.sesiones_desde = _ahora()
    _anular_pendientes(db, usuario.id)


# --------------------------------------------------- cambiarla uno mismo

def cambiar(db: Session, usuario: m.Usuario, actual: str, nueva: str) -> dict:
    """La cambia el propio dueno, estando dentro.

    Se pide la actual aunque ya tenga la sesion abierta: sin eso, una
    sesion robada se convierte en una cuenta robada para siempre. Con
    esto, el ladron tiene la sesion hasta que expire y nada mas.
    """
    if not auth.verificar(actual, usuario.hash_contrasena):
        raise HTTPException(401, "La contrasena actual no es correcta")
    if actual == nueva:
        raise HTTPException(400, "La contrasena nueva es la misma de antes")
    validar(nueva, usuario)

    _asentar(db, usuario, nueva)
    accesos.anotar(db, usuario, "contrasena cambiada", "usuario", usuario.id,
                   detalle="la cambio el propio dueno")
    db.flush()
    return {
        "resultado": "contrasena cambiada",
        # Las demas sesiones se caen: si alguien mas la tenia abierta, se
        # entera aqui.
        "otras_sesiones_cerradas": True,
    }


# ------------------------------------------------------ la olvidada

def misma_respuesta() -> dict:
    """La misma respuesta exista o no la cuenta.

    Dice los dos caminos, para que el de campo no se quede esperando un
    correo que no va a llegar. Y dice si el correo esta encendido, que
    no es un dato de nadie: mientras no lo este, el enlace lo entrega
    administracion, y la pantalla tiene que decirlo en vez de mandar a
    alguien a esperar un correo que no va a salir.
    """
    encendido = acceso_por_correo.encendido()
    return {
        "resultado": "pedido",
        "mensaje": ("Si ese correo tiene acceso, en un momento le llega un "
                    "enlace para poner una contrasena nueva."
                    if encendido else
                    "Si ese correo tiene acceso, se genero un enlace. El "
                    "correo todavia no esta encendido: lo entrega "
                    "administracion."),
        "personal_de_campo": ("Si eres personal de seguridad, tu contrasena "
                              "la recuperas con tu consultor o con la "
                              "central, no por correo."),
        "por_correo": encendido,
        "de": acceso_por_correo.remitente() if encendido else None,
        "horas": HORAS_RECUPERACION,
    }


def pedir_recuperacion(db: Session, correo: str) -> tuple:
    """Genera el enlace y deja escrito su correo. Nunca dice si la
    cuenta existe.

    Devuelve (respuesta, aviso): el aviso es para que quien llama lo
    mande en cuanto confirme, y es nulo cuando no hay a quien mandarle
    nada --que la respuesta no deja ver--.

    El enlace no viaja en esta respuesta a proposito: este endpoint es
    publico, y devolverlo aqui seria regalar la cuenta a cualquiera que
    escriba un correo ajeno. Viaja por el correo de la persona.
    """
    usuario = db.query(m.Usuario).filter_by(correo=(correo or "").strip()).first()
    if not usuario or not usuario.activo or usuario.rol not in POR_CORREO:
        return misma_respuesta(), None

    _anular_pendientes(db, usuario.id)
    enlace = m.Invitacion(
        usuario_id=usuario.id, token=secrets.token_urlsafe(32),
        tipo=m.TipoInvitacion.RECUPERACION,
        expira_en=datetime.now() + timedelta(hours=HORAS_RECUPERACION))
    db.add(enlace)
    db.flush()
    aviso = acceso_por_correo.escribir(db, usuario, enlace)
    accesos.anotar(db, usuario, "recuperacion pedida", "usuario", usuario.id,
                   detalle=f"vence en {HORAS_RECUPERACION} horas")
    db.flush()
    return misma_respuesta(), aviso


# --------------------------------------------------- la primera vez

def invitar(db: Session, usuario: m.Usuario) -> tuple:
    """El enlace de la primera vez y, si trabaja en la consola, su
    correo. Devuelve (enlace, aviso); el aviso es nulo para el personal
    de campo.

    Un enlace nuevo mata a los anteriores: reenviar la invitacion deja
    sin valor la que se mando antes.
    """
    _anular_pendientes(db, usuario.id)
    token, expira = auth.token_invitacion()
    enlace = m.Invitacion(usuario_id=usuario.id, token=token,
                          tipo=m.TipoInvitacion.INVITACION, expira_en=expira)
    db.add(enlace)
    db.flush()
    aviso = (acceso_por_correo.escribir(db, usuario, enlace)
             if usuario.rol in POR_CORREO else None)
    return enlace, aviso


def reinvitar(db: Session, usuario: m.Usuario, actor: m.Usuario) -> tuple:
    """Otra invitacion para quien todavia no estrena su acceso.

    Se le paso el correo, vencio a los tres dias o no le llego. Quien ya
    tiene contrasena no la necesita: si la olvido, la recupera el solo
    desde la entrada.
    """
    if not usuario.activo:
        raise HTTPException(409, {
            "mensaje": "Ese acceso esta cerrado.",
            "que_hacer": "Si tiene que volver a entrar, reabrelo primero.",
        })
    if usuario.persona and not usuario.persona.activo:
        raise HTTPException(409, {
            "mensaje": "Esa persona esta dada de baja como empleado.",
            "que_hacer": "Si volvio, reactivala primero como empleada.",
        })
    if usuario.rol not in POR_CORREO:
        raise HTTPException(409, {
            "mensaje": "El personal de seguridad no recibe invitacion por "
                       "correo.",
            "que_hacer": "Pone su contrasena con el codigo de cuatro "
                         "digitos que le dicta su consultor o la central.",
        })
    if usuario.hash_contrasena is not None:
        raise HTTPException(409, {
            "mensaje": "Ya creo su contrasena.",
            "que_hacer": "Si la olvido, la recupera ella misma desde la "
                         "entrada.",
        })
    enlace, aviso = invitar(db, usuario)
    accesos.anotar(db, actor, "invitacion reenviada", "usuario", usuario.id,
                   detalle=f"vence {enlace.expira_en:%d/%m/%Y %H:%M}")
    db.flush()
    return enlace, aviso


def estado_de_invitacion(db: Session, usuario: m.Usuario) -> dict:
    """Lo que el panel de accesos dice de la invitacion de alguien: si
    su enlace sigue vivo y que paso con su correo.

    "No le llego" tiene cuatro respuestas distintas y cada una se
    arregla distinto: el correo esta por salir, no salio (y el proveedor
    dijo por que), el correo todavia no esta encendido, o el enlace ya
    vencio. Decir solo "pendiente" deja a quien mira adivinando cual.
    """
    enlace = (db.query(m.Invitacion)
              .filter(m.Invitacion.usuario_id == usuario.id,
                      m.Invitacion.tipo == m.TipoInvitacion.INVITACION)
              .order_by(m.Invitacion.id.desc()).first())
    if not enlace:
        estado = "ninguna"
    elif enlace.usado_en:
        estado = "usada"
    elif enlace.anulado_en:
        estado = "anulada"
    elif enlace.expira_en < datetime.now():
        estado = "vencida"
    else:
        estado = "vigente"

    # El correo de ESTE enlace; el de uno anterior no dice nada de este.
    aviso = None
    if enlace:
        aviso = (db.query(m.Notificacion)
                 .filter(m.Notificacion.plantilla == acceso_por_correo.INVITACION,
                         m.Notificacion.enlace_seguimiento
                         == acceso_por_correo.ruta(enlace.token))
                 .order_by(m.Notificacion.id.desc()).first())
    return {
        "por_correo": usuario.rol in POR_CORREO,
        "estrenado": usuario.hash_contrasena is not None,
        "estado": estado,
        "expira_en": enlace.expira_en.isoformat() if enlace else None,
        "correo": ({
            "estado": aviso.estado,
            "salio_en": aviso.salio_en.isoformat() if aviso.salio_en else None,
            "error": aviso.ultimo_error,
        } if aviso else None),
        "correo_encendido": acceso_por_correo.encendido(),
    }


def enlace_pendiente(db: Session, usuario_id: int) -> dict:
    """El enlace vivo de esa cuenta, para que administracion lo copie.

    Nacio cuando el sistema no sabia mandar estos correos y el enlace lo
    entregaba una persona. Ya salen por correo, y esto se queda para
    cuando el correo no llega --un buzon que lo manda a no deseados, el
    correo todavia sin encender--. Solo administracion (decision de
    Salvador, 23 sep): con el enlace en la mano se le pone la contrasena
    a otra persona y se entra como ella.
    """
    enlace = (db.query(m.Invitacion)
              .filter(m.Invitacion.usuario_id == usuario_id,
                      m.Invitacion.tipo.in_(CON_ENLACE),
                      m.Invitacion.usado_en.is_(None),
                      m.Invitacion.anulado_en.is_(None))
              .order_by(m.Invitacion.id.desc()).first())
    if not enlace:
        raise HTTPException(404, "Esa cuenta no tiene ningun enlace pendiente")
    if enlace.expira_en < datetime.now():
        raise HTTPException(409, "El ultimo enlace ya vencio. Pide uno nuevo.")
    return {
        "tipo": enlace.tipo.value,
        "enlace": acceso_por_correo.enlace(enlace.token),
        "expira_en": enlace.expira_en.isoformat(),
    }


# ------------------------------------------------------ usar el enlace

def _enlace_de(db: Session, token: str) -> m.Invitacion | None:
    return (db.query(m.Invitacion)
            .filter(m.Invitacion.token == (token or ""),
                    m.Invitacion.tipo.in_(CON_ENLACE))
            .first())


def revisar_enlace(db: Session, token: str) -> dict:
    """Lo que la pagina del enlace necesita antes de pedir nada.

    Sin esto la pagina pedia la contrasena dos veces y hasta el final
    decia que el enlace habia vencido. Se dice primero.

    Los datos de la persona --su correo, con que entra-- solo salen con
    un enlace vivo: quien lo tiene es quien lo recibio. Con uno muerto
    solo se dice que esta muerto, y por que.
    """
    enlace = _enlace_de(db, token)
    if not enlace:
        return {"estado": "invalido"}
    if enlace.usado_en:
        return {"estado": "usado"}
    if enlace.anulado_en:
        return {"estado": "anulado"}
    if enlace.expira_en < datetime.now():
        return {"estado": "vencido"}
    usuario = enlace.usuario
    if not usuario.activo:
        return {"estado": "cerrado"}
    return {
        "estado": "vivo",
        "tipo": enlace.tipo.value,
        "correo": usuario.correo,
        "rol": usuario.rol.value,
        # La pagina se abre en el idioma en que le llego el correo.
        "idioma": acceso_por_correo.idioma_de(usuario),
        "expira_en": enlace.expira_en.isoformat(),
    }


def usar_enlace(db: Session, token: str, nueva: str) -> dict:
    """Pone la contrasena con un enlace, sea de invitacion o de olvido."""
    enlace = _enlace_de(db, token)
    if not enlace:
        raise HTTPException(404, "Enlace invalido")
    if enlace.usado_en:
        raise HTTPException(409, "Ese enlace ya se uso")
    if enlace.anulado_en:
        raise HTTPException(409, "Ese enlace ya no sirve: se pidio uno nuevo")
    if enlace.expira_en < datetime.now():
        raise HTTPException(409, "El enlace expiro, pide uno nuevo")

    usuario = enlace.usuario
    if not usuario.activo:
        raise HTTPException(403, "Ese acceso esta desactivado")

    validar(nueva, usuario)
    # Se marca usado antes de asentar: `_asentar` anula los pendientes, y
    # si este todavia contara como pendiente quedaria usado y anulado a
    # la vez, que no es lo que paso.
    enlace.usado_en = datetime.now()
    _asentar(db, usuario, nueva)
    accesos.anotar(db, usuario, "contrasena puesta", "usuario", usuario.id,
                   detalle=enlace.tipo.value)
    db.flush()
    return {"resultado": "contrasena creada", "correo": usuario.correo}


# ==================================================================
# El codigo de campo: cuatro digitos dictados por telefono
# ==================================================================

# Cuatro y no seis porque se dictan por telefono a las seis de la manana,
# y la friccion tambien es seguridad: un codigo que se dicta mal tres
# veces acaba en que alguien lo mande por WhatsApp.
#
# Diez mil combinaciones se prueban en segundos, asi que el tope de
# fallos no es opcional: cinco y el codigo se muere. Con eso, la
# probabilidad de adivinarlo es cinco entre diez mil, y solo durante los
# diez minutos que vive.
DIGITOS = 4
MINUTOS_CODIGO = 10
FALLOS_MAXIMOS = 5

# Desde hace cuanto cuenta como "su gente". Un consultor le da codigo a
# quien trabaja con el, no a cualquiera del padron. La ventana es de
# dias, asi que el desfase de horas entre paises no la mueve.
DIAS_DE_SU_GENTE = 30

# La central siempre; el consultor cuando esa persona este asignada a
# alguno de sus servicios. Nadie mas: lo unico que protege este camino es
# que quien entrega el codigo reconozca la voz de quien llama, y cada
# persona que puede darlo sin conocer al agente es una puerta.
SIEMPRE_PUEDEN = {m.Rol.CENTRAL, m.Rol.ADMIN, m.Rol.DIRECTOR_GENERAL}


def _es_de_su_gente(db: Session, actor: m.Usuario, persona_id: int) -> bool:
    """Si esa persona trabaja en alguno de los servicios del consultor."""
    desde = date.today() - timedelta(days=DIAS_DE_SU_GENTE)
    return (db.query(m.AsignacionPersonal.id)
            .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
            .filter(m.AsignacionPersonal.persona_id == persona_id,
                    m.Servicio.consultor_id == actor.persona_id,
                    m.Jornada.fecha >= desde)
            .first()) is not None


def puede_dar_codigo(db: Session, actor: m.Usuario, persona_id: int) -> bool:
    if actor.rol in SIEMPRE_PUEDEN:
        return True
    if actor.rol != m.Rol.CONSULTOR:
        return False
    return _es_de_su_gente(db, actor, persona_id)


def _donde_esta_hoy(db: Session, persona_id: int) -> str | None:
    """El servicio que trae hoy, si trae alguno.

    Es contexto que tambien verifica: si dice que entra a las seis y el
    sistema no le ve nada hoy, algo no cuadra.
    """
    relojes = reloj.Relojes(db)
    filas = (db.query(m.Jornada)
             .join(m.AsignacionPersonal,
                   m.AsignacionPersonal.jornada_id == m.Jornada.id)
             .filter(m.AsignacionPersonal.persona_id == persona_id,
                     m.Jornada.estatus != m.EstatusJornada.CANCELADA)
             .order_by(m.Jornada.fecha).all())
    for j in filas:
        servicio = j.equipo.servicio if j.equipo else None
        if not servicio:
            continue
        if j.fecha == relojes.hoy(servicio.pais_id):
            return (f"{servicio.folio} · arranca "
                    f"{j.inicio_programado.strftime('%H:%M')}")
    return None


def _ficha_de_campo(db: Session, persona: m.Persona,
                    usuario: m.Usuario) -> dict:
    """Lo que ve quien va a dictar el codigo.

    La foto, el telefono y el numero de empleado no son adorno: le dan al
    consultor algo mas que la voz para saber con quien habla --"de que
    numero me llamas", "cual es tu numero de empleado"-- y la foto de
    Odoo para verle la cara.
    """
    return {
        "persona_id": persona.id,
        "usuario_id": usuario.id,
        "nombre": persona.nombre,
        "telefono": persona.telefono,
        "foto": persona.foto_url,
        "referencia": persona.referencia,
        "correo": usuario.correo,
        "hoy": _donde_esta_hoy(db, persona.id),
        "estrenado": usuario.hash_contrasena is not None,
        # Si ya trae uno vivo, la pantalla avisa antes de generar otro:
        # asi el consultor no dicta tres seguidos y el agente no sabe
        # cual va.
        "codigo_vigente_hasta": _vence_el_codigo(db, usuario.id),
    }


def _vence_el_codigo(db: Session, usuario_id: int) -> str | None:
    vigente = codigo_vigente(db, usuario_id)
    return vigente.expira_en.isoformat() if vigente else None


def buscar_para_codigo(db: Session, actor: m.Usuario, q: str) -> list[dict]:
    """El buscador de la pantalla del codigo: por nombre o por el numero
    de empleado de Odoo, completo.

    Pide al menos dos letras a proposito: una busqueda que devuelve a
    todos es el padron completo en la pantalla de cualquier consultor.
    """
    q = (q or "").strip()
    if len(q) < 2:
        return []
    filas = (db.query(m.Usuario)
             .join(m.Persona, m.Usuario.persona_id == m.Persona.id)
             .filter(m.Usuario.rol == m.Rol.PERSONAL_SEGURIDAD,
                     m.Usuario.activo.is_(True),
                     m.Persona.activo.is_(True),
                     or_(m.Persona.nombre.ilike(f"%{q}%"),
                         # El numero de empleado, completo: un pedazo
                         # de numero traeria a medio padron.
                         m.Persona.referencia.ilike(q)))
             .order_by(m.Persona.nombre).limit(20).all())
    return [_ficha_de_campo(db, u.persona, u) for u in filas
            if puede_dar_codigo(db, actor, u.persona_id)][:10]


def codigo_vigente(db: Session, usuario_id: int) -> m.Invitacion | None:
    """El codigo que todavia sirve, si hay uno."""
    fila = (db.query(m.Invitacion)
            .filter(m.Invitacion.usuario_id == usuario_id,
                    m.Invitacion.tipo == m.TipoInvitacion.CODIGO_CAMPO,
                    m.Invitacion.usado_en.is_(None),
                    m.Invitacion.anulado_en.is_(None))
            .order_by(m.Invitacion.id.desc()).first())
    if fila and fila.expira_en > datetime.now():
        return fila
    return None


def generar_codigo(db: Session, actor: m.Usuario, persona_id: int) -> dict:
    """Los cuatro digitos que el consultor le va a dictar."""
    persona = db.get(m.Persona, persona_id)
    if not persona or not persona.activo:
        raise HTTPException(404, "Esa persona no existe o esta dada de baja")

    usuario = db.query(m.Usuario).filter_by(persona_id=persona_id).first()
    if not usuario or not usuario.activo:
        raise HTTPException(409, {
            "mensaje": f"{persona.nombre} no tiene acceso activo al sistema.",
            "que_hacer": "Administracion tiene que darle acceso primero.",
        })
    if usuario.rol != m.Rol.PERSONAL_SEGURIDAD:
        raise HTTPException(409, {
            "mensaje": "El codigo por telefono es para el personal de campo.",
            "que_hacer": "Quien trabaja desde la computadora recupera su "
                         "contrasena por correo.",
        })
    if not puede_dar_codigo(db, actor, persona_id):
        raise HTTPException(403, {
            "mensaje": f"{persona.nombre} no trabaja en tus servicios.",
            "que_hacer": "Su consultor o la central pueden darle el codigo. "
                         "Lo que protege este camino es que quien lo entrega "
                         "reconozca la voz de quien llama.",
        })

    _anular_pendientes(db, usuario.id)
    codigo = f"{secrets.randbelow(10 ** DIGITOS):0{DIGITOS}d}"
    # Se guarda cifrado: diez minutos es poco tiempo, pero un codigo en
    # texto plano en la base es una cuenta regalada si la base se filtra.
    db.add(m.Invitacion(
        usuario_id=usuario.id, token=auth.cifrar(codigo),
        tipo=m.TipoInvitacion.CODIGO_CAMPO, fallos=0,
        expira_en=datetime.now() + timedelta(minutes=MINUTOS_CODIGO)))
    accesos.anotar(db, actor, "codigo de campo entregado", "usuario",
                   usuario.id, detalle=f"a {persona.nombre}")
    db.flush()

    return {
        # La unica vez que se ve. Si se cierra la tarjeta, se acabo: hay
        # que generar otro, y ese mata a este.
        "codigo": codigo,
        "minutos": MINUTOS_CODIGO,
        "persona": _ficha_de_campo(db, persona, usuario),
    }


def usar_codigo(db: Session, correo: str, codigo: str, nueva: str) -> dict:
    """El agente pone su contrasena con los cuatro digitos que le dictaron."""
    malo = HTTPException(401, "El codigo no es correcto o ya vencio")

    usuario = db.query(m.Usuario).filter_by(correo=(correo or "").strip()).first()
    if not usuario or not usuario.activo:
        raise malo
    vigente = codigo_vigente(db, usuario.id)
    if not vigente:
        raise malo

    if not auth.verificar((codigo or "").strip(), vigente.token):
        vigente.fallos = (vigente.fallos or 0) + 1
        quedan = FALLOS_MAXIMOS - vigente.fallos
        if quedan <= 0:
            vigente.anulado_en = datetime.now()
        # Se confirma antes de reventar: si no, la sesion se cierra sin
        # guardar y el contador vuelve a cero en cada intento, que es lo
        # mismo que no tener tope.
        db.commit()
        raise HTTPException(401, {
            "mensaje": "El codigo no es correcto.",
            "que_hacer": ("Pidele otro a tu consultor." if quedan <= 0
                          else f"Te quedan {quedan} intento(s)."),
        })

    validar(nueva, usuario)
    vigente.usado_en = datetime.now()
    _asentar(db, usuario, nueva)
    accesos.anotar(db, usuario, "contrasena puesta", "usuario", usuario.id,
                   detalle="codigo de campo")
    db.flush()
    return {"resultado": "contrasena creada", "correo": usuario.correo}

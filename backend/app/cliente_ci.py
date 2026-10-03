"""La app del cliente de la Central de Inteligencia (seccion 136).

La gente del cliente no es personal de Centauro: no tiene `Usuario`, no
ve la consola y no comparte la sesion. Entra a su propia app
(ci.mycentauro.lat) con su correo y su contrasena, y ve solo lo suyo: lo
publicado en los estados que sigue su empresa y los avisos que le
llegaron a el.

**Su sesion no abre ninguna otra puerta.** Su token va firmado con la
misma clave que las de la consola pero lleva `tipo: cliente_ci`, y
`auth._es_sesion` rechaza cualquier token con `tipo`: con el no se entra
a nada de Centauro. Al reves igual: aqui solo vale un token de cliente.

**Lo que ve es lo que el analista escribio para el.** El titulo, el
texto para el cliente, el lugar, las horas y la verificacion. Nunca las
fuentes, el motivo, quien lo capturo ni la bitacora: eso es trabajo de
la Central.

**El acceso, como del lado de Centauro** (`contrasenas`): la invitacion
y el «olvide mi contrasena» salen por correo con un enlace que vale una
vez; un enlace nuevo mata a los anteriores; pedir recuperacion contesta
lo mismo exista o no la cuenta; la contrasena nueva tira las sesiones
abiertas. Del token del enlace solo se guarda su huella.
"""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import auth, contrasenas, correo, correo_html, intentos, push
from app import models as m
from app import nivel_centauro as nivel_mes
from app import reloj
from app.config import settings
from app.db import get_db

TIPO_SESION = "cliente_ci"
# El gerente abre la app cuando le llega un aviso, a veces dias despues
# del ultimo: pedirle la contrasena cada doce horas es ensenarle a no
# abrirla. Treinta dias, y cerrar el acceso o cambiar la contrasena tira
# la sesion al momento (`sesiones_desde`).
DIAS_SESION = 30
HORAS_INVITACION = 72
HORAS_RECUPERACION = 2
INVITACION, RECUPERACION = "invitacion", "recuperacion"
PLANTILLAS = ("ci_invitacion", "ci_recuperacion")
# Los avisos de mas atras no se ensenan: la app es de lo que pasa.
DIAS_DE_AVISOS = 60

esquema = OAuth2PasswordBearer(tokenUrl="/ci-api/entrar", auto_error=False)

TEXTOS = {
    "es": {
        "inv_asunto": "Tu acceso a la Central de Inteligencia de Centauro",
        "inv_cuerpo": ("Hola, {nombre}. Centauro te dio acceso a la Central "
                       "de Inteligencia por {cliente}: el mapa de riesgo de "
                       "los estados que sigue tu empresa y los avisos de lo "
                       "que pasa en ellos. Pon tu contraseña para entrar."),
        "inv_boton": "Crear mi contraseña",
        "rec_asunto": "Para poner una contraseña nueva",
        "rec_cuerpo": ("Alguien pidió cambiar la contraseña de tu acceso a la "
                       "Central de Inteligencia. Si no fuiste tú, ignora este "
                       "correo: tu contraseña sigue igual."),
        "rec_boton": "Poner mi contraseña nueva",
        "tu_correo": "Tu correo", "empresa": "Empresa",
        "nota": "El enlace sirve una sola vez y vence el {cuando}.",
        "prueba_titulo": "Así te llegan los avisos",
        "prueba_cuerpo": "Este teléfono recibe los avisos de la Central.",
    },
    "pt": {
        "inv_asunto": "Seu acesso à Central de Inteligência da Centauro",
        "inv_cuerpo": ("Olá, {nombre}. A Centauro deu a você acesso à Central "
                       "de Inteligência por {cliente}: o mapa de risco dos "
                       "estados que a sua empresa acompanha e os avisos do "
                       "que acontece neles. Crie a sua senha para entrar."),
        "inv_boton": "Criar minha senha",
        "rec_asunto": "Para criar uma senha nova",
        "rec_cuerpo": ("Alguém pediu para trocar a senha do seu acesso à "
                       "Central de Inteligência. Se não foi você, ignore este "
                       "e-mail: a sua senha continua igual."),
        "rec_boton": "Criar minha senha nova",
        "tu_correo": "Seu e-mail", "empresa": "Empresa",
        "nota": "O link funciona uma só vez e vence em {cuando}.",
        "prueba_titulo": "Assim chegam os avisos",
        "prueba_cuerpo": "Este telefone recebe os avisos da Central.",
    },
    "en": {
        "inv_asunto": "Your access to the Centauro Intelligence Center",
        "inv_cuerpo": ("Hi, {nombre}. Centauro gave you access to the "
                       "Intelligence Center for {cliente}: the risk map of "
                       "the states your company follows and the alerts of "
                       "what happens there. Set your password to sign in."),
        "inv_boton": "Create my password",
        "rec_asunto": "To set a new password",
        "rec_cuerpo": ("Someone asked to change the password of your access to "
                       "the Intelligence Center. If it wasn't you, ignore this "
                       "email: your password stays the same."),
        "rec_boton": "Set my new password",
        "tu_correo": "Your email", "empresa": "Company",
        "nota": "The link works only once and expires on {cuando}.",
        "prueba_titulo": "This is how alerts arrive",
        "prueba_cuerpo": "This phone receives the Center's alerts.",
    },
}


def _tx(idioma: str | None) -> dict:
    return TEXTOS.get(idioma or "es") or TEXTOS["es"]


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def raiz_app() -> str:
    """De donde cuelga la app: su direccion propia, o /ci de la consola.

    Siempre con /ci al final: el proxy manda la raiz de ci.mycentauro.lat
    a /ci/, pero un enlace que ya lleva la ruta no depende de ese salto.
    """
    propia = (settings.url_ci or "").rstrip("/")
    if propia:
        return f"{propia}/ci"
    publica = (settings.url_publica or "").rstrip("/")
    return f"{publica}/ci" if publica else "/ci"


def _zona_horaria(db: Session, gente: m.UsuarioCliente) -> str:
    pais = db.get(m.Pais, gente.cliente_central.cliente.pais_id)
    return pais.zona_horaria if pais else "America/Mexico_City"


# ================================================================ sesion

def crear_token(gente: m.UsuarioCliente) -> str:
    ahora = _ahora()
    carga = {"sub": str(gente.id), "tipo": TIPO_SESION, "iat": ahora,
             "emitido": ahora.timestamp(),
             "exp": ahora + timedelta(days=DIAS_SESION)}
    return jwt.encode(carga, auth._clave(), algorithm=auth.ALGORITMO)


def _puede_entrar(gente: m.UsuarioCliente | None) -> bool:
    return bool(gente and gente.activo and gente.cliente_central.activo)


def gente_actual(token: str | None = Depends(esquema),
                 db: Session = Depends(get_db)) -> m.UsuarioCliente:
    sin_acceso = HTTPException(status.HTTP_401_UNAUTHORIZED,
                               "Se requiere iniciar sesion",
                               headers={"WWW-Authenticate": "Bearer"})
    if not token:
        raise sin_acceso
    try:
        carga = jwt.decode(token, auth._clave(), algorithms=[auth.ALGORITMO])
    except jwt.PyJWTError:
        raise sin_acceso
    if carga.get("tipo") != TIPO_SESION or not str(
            carga.get("sub") or "").isdigit():
        raise sin_acceso
    gente = db.get(m.UsuarioCliente, int(carga["sub"]))
    if not _puede_entrar(gente):
        raise sin_acceso
    desde = gente.sesiones_desde
    if desde and float(carga.get("emitido") or 0) < desde.timestamp():
        raise sin_acceso
    return gente


def _por_correo(db: Session, correo_: str) -> m.UsuarioCliente | None:
    llave = auth.llave_de_correo(correo_)
    if not llave:
        return None
    return (db.query(m.UsuarioCliente)
            .filter(func.lower(func.trim(m.UsuarioCliente.correo)) == llave)
            .first())


_RELLENO: list[str] = []


def _hash_de_relleno() -> str:
    if not _RELLENO:
        _RELLENO.append(auth.cifrar(secrets.token_urlsafe(16)))
    return _RELLENO[0]


def entrar(db: Session, correo_: str, contrasena: str,
           ip: str | None = None) -> dict:
    """Con el mismo tope de intentos que la consola, en su propio carril:
    el gerente que se equivoca no le cierra la puerta a nadie de
    Centauro, ni al reves."""
    llave = auth.llave_de_correo(correo_)
    carril = f"ci:{llave}"
    intentos.revisar(carril, ip)
    gente = _por_correo(db, llave)
    hash_ = gente.hash_contrasena if gente else None
    # Contra una de a mentiras si no hay cuenta o no tiene contrasena: que
    # tarde lo mismo, para que el tiempo no diga que correos existen.
    if not auth.verificar(contrasena or "", hash_ or _hash_de_relleno()) \
            or not hash_:
        intentos.fallo(carril, ip)
        raise HTTPException(401, "Correo o contrasena incorrectos")
    if not _puede_entrar(gente):
        raise HTTPException(403, "Ese acceso esta cerrado. Pídele a la "
                                 "Central que lo abra.")
    intentos.exito(carril, ip)
    gente.ultimo_acceso = _ahora()
    return {"token": crear_token(gente), "idioma": gente.idioma}


# ================================================================ enlaces

def _huella(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def _anular_pendientes(db: Session, gente: m.UsuarioCliente) -> None:
    ahora = _ahora()
    vivos = (db.query(m.EnlaceCliente)
             .filter(m.EnlaceCliente.usuario_cliente_id == gente.id,
                     m.EnlaceCliente.usado_en.is_(None),
                     m.EnlaceCliente.anulado_en.is_(None)).all())
    for enlace in vivos:
        enlace.anulado_en = ahora
    # Y su correo, si no ha salido: llegaria con un enlace muerto.
    (db.query(m.Notificacion)
     .filter(m.Notificacion.estado == "pendiente",
             m.Notificacion.plantilla.in_(PLANTILLAS),
             m.Notificacion.correo == gente.correo)
     .delete(synchronize_session=False))


def nuevo_enlace(db: Session, gente: m.UsuarioCliente,
                 tipo: str) -> tuple[m.EnlaceCliente, m.Notificacion]:
    """Crea el enlace y deja escrito su correo. Salir, sale despues."""
    _anular_pendientes(db, gente)
    token = secrets.token_urlsafe(32)
    horas = HORAS_INVITACION if tipo == INVITACION else HORAS_RECUPERACION
    enlace = m.EnlaceCliente(usuario_cliente_id=gente.id, tipo=tipo,
                             huella=_huella(token),
                             expira_en=_ahora() + timedelta(hours=horas))
    db.add(enlace)
    db.flush()

    t = _tx(gente.idioma)
    cliente = gente.cliente_central.cliente.nombre
    if tipo == INVITACION:
        asunto = t["inv_asunto"]
        cuerpo = t["inv_cuerpo"].format(nombre=gente.nombre.split()[0],
                                        cliente=cliente)
        pares = [(t["tu_correo"], gente.correo), (t["empresa"], cliente)]
    else:
        asunto, cuerpo = t["rec_asunto"], t["rec_cuerpo"]
        pares = [(t["tu_correo"], gente.correo)]
    aviso = m.Notificacion(
        destinatario=m.Destinatario.CLIENTE_CI, canal=m.Canal.CORREO,
        correo=gente.correo, idioma=gente.idioma, asunto=asunto,
        cuerpo=cuerpo, datos=correo_html.guardar_datos(pares),
        # Detras del "#": el navegador no manda al servidor lo que va
        # despues, y el token no queda en ninguna bitacora de acceso.
        enlace_seguimiento=f"{raiz_app()}/#/enlace/{token}",
        plantilla=f"ci_{tipo}",
        # El correo vive lo que vive su enlace, en la hora de pared con
        # la que el despachador compara.
        expira_en=enlace.expira_en.astimezone().replace(tzinfo=None))
    db.add(aviso)
    db.flush()
    enlace.correo_id = aviso.id
    return enlace, aviso


def versiones(db: Session, aviso: m.Notificacion) -> tuple:
    """(texto, HTML) del correo de acceso del cliente."""
    liga = correo.con_dominio(aviso.enlace_seguimiento)
    if not liga:
        raise RuntimeError("Falta URL_PUBLICA o URL_CI: el enlace del correo "
                           "no llevaria a ningun lado")
    t = _tx(aviso.idioma)
    boton = (t["inv_boton"] if aviso.plantilla == "ci_invitacion"
             else t["rec_boton"], liga)
    nota = None
    enlace = db.query(m.EnlaceCliente).filter_by(correo_id=aviso.id).first()
    if enlace:
        gente = enlace.usuario_cliente
        cuando = enlace.expira_en.astimezone(
            reloj.zona(_zona_horaria(db, gente))).strftime("%d/%m/%Y %H:%M")
        nota = t["nota"].format(cuando=cuando)
    pares = correo_html.leer_datos(aviso.datos)
    return (correo_html.plano(aviso.asunto, aviso.cuerpo, pares=pares,
                              boton=boton, nota=nota, linea="ci"),
            correo_html.armar(aviso.asunto, aviso.cuerpo, pares=pares,
                              boton=boton, nota=nota, linea="ci"))


def _enlace(db: Session, token: str) -> m.EnlaceCliente | None:
    if not token:
        return None
    return db.query(m.EnlaceCliente).filter_by(huella=_huella(token)).first()


def revisar_enlace(db: Session, token: str) -> dict:
    """Lo que la pantalla necesita antes de pedir la contrasena. Los datos
    de la persona solo salen con un enlace vivo."""
    enlace = _enlace(db, token)
    if not enlace:
        return {"estado": "invalido"}
    if enlace.usado_en:
        return {"estado": "usado"}
    if enlace.anulado_en:
        return {"estado": "anulado"}
    if enlace.expira_en < _ahora():
        return {"estado": "vencido"}
    gente = enlace.usuario_cliente
    if not _puede_entrar(gente):
        return {"estado": "cerrado"}
    return {"estado": "vivo", "tipo": enlace.tipo, "correo": gente.correo,
            "nombre": gente.nombre,
            "cliente": gente.cliente_central.cliente.nombre,
            "idioma": gente.idioma}


def usar_enlace(db: Session, token: str, nueva: str) -> dict:
    """Pone la contrasena y entra: el boton dice «Guardar y entrar»."""
    estado = revisar_enlace(db, token)
    if estado["estado"] != "vivo":
        raise HTTPException(409, {"mensaje": "Ese enlace ya no sirve",
                                  "estado": estado["estado"]})
    enlace = _enlace(db, token)
    gente = enlace.usuario_cliente
    _validar(nueva, gente)
    enlace.usado_en = _ahora()
    _asentar(db, gente, nueva)
    gente.ultimo_acceso = _ahora()
    return {"token": crear_token(gente), "idioma": gente.idioma}


def _validar(nueva: str, gente: m.UsuarioCliente) -> None:
    contrasenas.validar(nueva or "")
    local = (gente.correo or "").split("@")[0].lower()
    if local and len(local) >= 4 and local in (nueva or "").lower():
        raise HTTPException(400, "La contrasena no puede llevar tu correo "
                                 "adentro")


def _asentar(db: Session, gente: m.UsuarioCliente, nueva: str) -> None:
    gente.hash_contrasena = auth.cifrar(nueva)
    gente.sesiones_desde = _ahora()
    _anular_pendientes(db, gente)


def recuperar(db: Session, correo_: str) -> m.Notificacion | None:
    """Siempre contesta lo mismo quien lo llama; aqui solo se decide si
    sale un correo. A un acceso cerrado no: no tiene a donde entrar."""
    gente = _por_correo(db, correo_)
    if not _puede_entrar(gente):
        return None
    # Quien todavia no pone su contrasena recibe otra invitacion, no un
    # enlace de dos horas: asi pedir el olvido con su correo no le cambia
    # la invitacion de 72 horas por una que vence enseguida.
    tipo = RECUPERACION if gente.hash_contrasena else INVITACION
    _, aviso = nuevo_enlace(db, gente, tipo)
    return aviso


def cambiar(db: Session, gente: m.UsuarioCliente, actual: str,
            nueva: str) -> dict:
    if not auth.verificar(actual or "", gente.hash_contrasena):
        # 403 y no 401: la app toma cualquier 401 como sesion vencida.
        raise HTTPException(403, "Tu contraseña actual no es esa")
    _validar(nueva, gente)
    _asentar(db, gente, nueva)
    # La sesion de este telefono sigue: se le da un token nuevo.
    return {"token": crear_token(gente)}


# ================================================================ lo que ve

def _regiones(gente: m.UsuarioCliente) -> list[int]:
    return [z.region_id for z in gente.cliente_central.zonas]


def _local(instante: datetime | None, zona: str) -> str | None:
    if instante is None:
        return None
    return instante.astimezone(reloj.zona(zona)).isoformat()


def vista_evento(evento: m.EventoRiesgo, ahora: datetime | None = None
                 ) -> dict:
    """Lo que el analista escribio para el cliente, y nada mas."""
    zona = evento.pais.zona_horaria
    ahora = ahora or _ahora()
    vigente = (evento.estado == m.EstadoEvento.PUBLICADO
               and evento.vigente_hasta > ahora)
    return {
        "id": evento.id, "folio": evento.folio,
        "tipo": evento.tipo.nombre, "region": evento.region.nombre,
        "municipio": evento.municipio, "nivel": evento.nivel,
        "titulo": evento.titulo, "texto": evento.texto_cliente,
        "lugar": evento.lugar,
        "lat": float(evento.lat) if evento.lat is not None else None,
        "lon": float(evento.lon) if evento.lon is not None else None,
        "radio_m": evento.radio_m,
        "ocurrio_en": _local(evento.ocurrio_en, zona),
        "vigente_hasta": _local(evento.vigente_hasta, zona),
        "verificacion": evento.verificacion.value,
        "tendencia": evento.tendencia.value if evento.tendencia else None,
        "vigente": vigente,
    }


def yo(db: Session, gente: m.UsuarioCliente) -> dict:
    cc = gente.cliente_central
    return {
        "id": gente.id, "nombre": gente.nombre, "apellidos": gente.apellidos,
        "correo": gente.correo, "perfil": gente.perfil.value,
        "idioma": gente.idioma, "cliente": cc.cliente.nombre,
        "zonas": sorted(z.region.nombre for z in cc.zonas),
        "telefono_central": settings.telefono_central,
        "por_confirmar": _por_confirmar(db, gente),
    }


def _por_confirmar(db: Session, gente: m.UsuarioCliente) -> int:
    return (db.query(func.count(m.AlertaCliente.id))
            .filter(m.AlertaCliente.usuario_cliente_id == gente.id,
                    m.AlertaCliente.requiere_acuse.is_(True),
                    m.AlertaCliente.acuse_en.is_(None)).scalar() or 0)


def mapa(db: Session, gente: m.UsuarioCliente) -> list[dict]:
    """Lo vigente en sus estados, lo mas grave primero."""
    ahora = _ahora()
    regiones = _regiones(gente)
    if not regiones:
        return []
    eventos = (db.query(m.EventoRiesgo)
               .filter(m.EventoRiesgo.region_id.in_(regiones),
                       m.EventoRiesgo.estado == m.EstadoEvento.PUBLICADO,
                       m.EventoRiesgo.vigente_hasta > ahora)
               .order_by(m.EventoRiesgo.nivel.desc(),
                         m.EventoRiesgo.ocurrio_en.desc()).all())
    return [vista_evento(e, ahora) for e in eventos]


# ------------------------------------------------- el riesgo de fondo

# Los municipios que se le ensenan al cliente en la ficha de un estado.
MUNICIPIOS_EN_LA_FICHA = 5


def _pais_de(db: Session, gente: m.UsuarioCliente) -> m.Pais | None:
    """Mexico, el unico con nivel por ahora, si sigue algun estado de
    alla; si no, el pais de sus estados."""
    paises = [z.region.pais for z in gente.cliente_central.zonas]
    for pais in paises:
        if pais.codigo == "MX":
            return pais
    if paises:
        return paises[0]
    return db.query(m.Pais).filter_by(codigo="MX").first()


def _lugar_para_cliente(lugar: dict, mios: set[int]) -> dict:
    """El numero y como se compone. Sin el motivo de un ajuste ni lo que
    calculo Connect antes de ajustarlo: eso es trabajo de la Central."""
    return {"region_id": lugar["region_id"], "region": lugar["region"],
            "clave_region": lugar["clave_region"],
            "municipio": lugar["municipio"],
            "clave_municipio": lugar["clave_municipio"],
            "valor": lugar["valor"], "rango": lugar["rango"],
            "vs_mes": lugar["vs_mes"], "vs_ano": lugar["vs_ano"],
            "componentes": {c: d.get("p")
                            for c, d in lugar["componentes"].items()},
            "mio": lugar["region_id"] in mios}


def fondo(db: Session, gente: m.UsuarioCliente) -> dict:
    """El ultimo mes publicado, por estado: todo el pais se pinta, y sus
    estados van marcados. Un borrador nunca llega aqui."""
    pais = _pais_de(db, gente)
    mes = nivel_mes.vigente(db, pais) if pais else None
    if not mes:
        return {"mes": None}
    vista = nivel_mes.vista_mes(db, mes)
    mios = set(_regiones(gente))
    # De los estados que no sigue, solo lo que pinta el mapa.
    solo_color = ("region_id", "region", "clave_region", "valor", "rango",
                  "mio")
    estados = []
    for x in vista["lugares"]:
        lugar = _lugar_para_cliente(x, mios)
        estados.append(lugar if lugar["mio"]
                       else {k: lugar[k] for k in solo_color})
    return {"mes": {"id": mes.id, "periodo": vista["periodo"],
                    "cortes": vista["cortes"], "faltan": vista["faltan"]},
            "estados": estados}


def fondo_estado(db: Session, gente: m.UsuarioCliente, region_id: int
                 ) -> dict:
    """La ficha de uno de SUS estados: como se compone y sus municipios
    mas altos. De los demas solo ve el color en el mapa."""
    if region_id not in _regiones(gente):
        raise HTTPException(404, "Ese estado no está en tu servicio")
    pais = _pais_de(db, gente)
    mes = nivel_mes.vigente(db, pais) if pais else None
    if not mes:
        raise HTTPException(404, "Todavía no hay un nivel publicado")
    mios = {region_id}
    estados = nivel_mes.vista_mes(db, mes, region_id=region_id)["lugares"]
    if not estados:
        raise HTTPException(404, "Ese estado no está en el nivel del mes")
    municipios = nivel_mes.vista_mes(db, mes, region_id=region_id,
                                 con_municipios=True)["lugares"]
    vigentes = (db.query(func.count(m.EventoRiesgo.id))
                .filter(m.EventoRiesgo.region_id == region_id,
                        m.EventoRiesgo.estado == m.EstadoEvento.PUBLICADO,
                        m.EventoRiesgo.vigente_hasta > _ahora()).scalar())
    return {"mes": {"id": mes.id, "periodo": mes.periodo.isoformat(),
                    "cortes": json.loads(mes.resumen).get("cortes"),
                    "faltan": json.loads(mes.resumen).get("faltan", [])},
            "estado": _lugar_para_cliente(estados[0], mios),
            "municipios": [_lugar_para_cliente(x, mios) for x in
                           municipios[:MUNICIPIOS_EN_LA_FICHA]],
            "vigentes": vigentes or 0}


def _vista_aviso(alerta: m.AlertaCliente, ahora: datetime) -> dict:
    zona = alerta.evento.pais.zona_horaria
    return {
        "id": alerta.id, "nivel": alerta.nivel, "motivo": alerta.motivo,
        "creada_en": _local(alerta.creada_en, zona),
        "requiere_acuse": alerta.requiere_acuse,
        "acuse_en": _local(alerta.acuse_en, zona),
        "en_resumen": alerta.en_resumen,
        "evento": vista_evento(alerta.evento, ahora),
    }


def avisos(db: Session, gente: m.UsuarioCliente) -> dict:
    """Los suyos: primero los que esperan su «Enterado»."""
    ahora = _ahora()
    filas = (db.query(m.AlertaCliente)
             .filter(m.AlertaCliente.usuario_cliente_id == gente.id,
                     m.AlertaCliente.creada_en
                     >= ahora - timedelta(days=DIAS_DE_AVISOS))
             .order_by(m.AlertaCliente.creada_en.desc(),
                       m.AlertaCliente.id.desc()).limit(200).all())
    pendientes = [a for a in filas if a.requiere_acuse and not a.acuse_en]
    # Por evento, la alerta mas nueva: si subio de 2 a 3, el 2 ya no se
    # ensena aparte.
    vistos = {a.evento_id for a in pendientes}
    anteriores = []
    for a in filas:
        if a in pendientes or a.evento_id in vistos:
            continue
        vistos.add(a.evento_id)
        anteriores.append(a)
    pendientes.sort(key=lambda a: (-a.nivel, a.creada_en))
    return {"por_confirmar": [_vista_aviso(a, ahora) for a in pendientes],
            "anteriores": [_vista_aviso(a, ahora) for a in anteriores]}


def evento(db: Session, gente: m.UsuarioCliente, evento_id: int) -> dict:
    """Un evento de sus estados ya publicado, o uno que le llego."""
    ev = db.get(m.EventoRiesgo, evento_id)
    suyas = (db.query(m.AlertaCliente)
             .filter_by(evento_id=evento_id, usuario_cliente_id=gente.id)
             .order_by(m.AlertaCliente.nivel.desc()).all()) if ev else []
    publicado = ev is not None and ev.publicado_en is not None and \
        ev.estado in (m.EstadoEvento.PUBLICADO, m.EstadoEvento.CERRADO)
    if not ev or not (suyas or (publicado
                                and ev.region_id in _regiones(gente))):
        raise HTTPException(404, "Ese evento no está en tus estados")
    datos = vista_evento(ev)
    pendiente = next((a for a in suyas
                      if a.requiere_acuse and not a.acuse_en), None)
    datos["alerta_por_confirmar"] = pendiente.id if pendiente else None
    return datos


def acusar(db: Session, gente: m.UsuarioCliente, alerta_id: int) -> dict:
    from app import alertas_riesgo, riesgo
    previa = db.get(m.AlertaCliente, alerta_id)
    ya = previa is not None and previa.acuse_en is not None
    alerta = alertas_riesgo.acusar(db, gente, alerta_id)
    if not ya:
        riesgo._anotar(db, alerta.evento, None, "acuse",
                       f"{gente.nombre_completo} "
                       f"({gente.cliente_central.cliente.nombre}): enterado")
    return {"acuse_en": _local(alerta.acuse_en,
                               alerta.evento.pais.zona_horaria)}


# ================================================================ telefono

# Los servicios de avisos de los navegadores. La direccion la manda el
# telefono, y el servidor le escribe ahi cada vez que se publica algo: sin
# esta lista, alguien de fuera podia hacer que el servidor tocara
# direcciones internas, o una que nunca contesta y atora la publicacion.
SERVICIOS_DE_AVISOS = ("fcm.googleapis.com", ".push.services.mozilla.com",
                       "web.push.apple.com", ".notify.windows.com")
TELEFONOS_MAXIMO = 5


def _servicio_valido(endpoint: str) -> bool:
    from urllib.parse import urlparse
    partes = urlparse(endpoint or "")
    host = (partes.hostname or "").lower()
    return partes.scheme == "https" and any(
        host == s.lstrip(".") or (s.startswith(".") and host.endswith(s))
        for s in SERVICIOS_DE_AVISOS)


def suscribir(db: Session, gente: m.UsuarioCliente, endpoint: str,
              p256dh: str, auth_: str, agente: str | None) -> None:
    if not _servicio_valido(endpoint):
        raise HTTPException(400, "Esa dirección de avisos no es de un "
                                 "navegador conocido")
    fila = (db.query(m.SuscripcionPushCliente)
            .filter_by(endpoint=endpoint).first())
    # Cinco telefonos por persona: el mas viejo deja su lugar.
    otros = (db.query(m.SuscripcionPushCliente)
             .filter(m.SuscripcionPushCliente.usuario_cliente_id == gente.id,
                     m.SuscripcionPushCliente.activa.is_(True),
                     m.SuscripcionPushCliente.endpoint != endpoint)
             .order_by(m.SuscripcionPushCliente.creada_en.desc(),
                       m.SuscripcionPushCliente.id.desc()).all())
    for vieja in otros[TELEFONOS_MAXIMO - 1:]:
        vieja.activa = False
    if not fila:
        fila = m.SuscripcionPushCliente(endpoint=endpoint,
                                        usuario_cliente_id=gente.id,
                                        p256dh=p256dh, auth=auth_)
        db.add(fila)
    fila.usuario_cliente_id = gente.id
    fila.p256dh, fila.auth = p256dh, auth_
    fila.agente = (agente or "")[:300] or None
    fila.activa = True


def desuscribir(db: Session, gente: m.UsuarioCliente, endpoint: str) -> None:
    fila = (db.query(m.SuscripcionPushCliente)
            .filter_by(endpoint=endpoint, usuario_cliente_id=gente.id).first())
    if fila:
        fila.activa = False


def estado_push(db: Session, gente: m.UsuarioCliente,
                endpoint: str | None) -> dict:
    filas = (db.query(m.SuscripcionPushCliente)
             .filter_by(usuario_cliente_id=gente.id, activa=True).all())
    return {"activo": push.hay_llaves(), "llave": settings.vapid_public,
            "telefonos": len(filas),
            "este_telefono": bool(endpoint and any(f.endpoint == endpoint
                                                   for f in filas))}


def probar(db: Session, gente: m.UsuarioCliente) -> dict:
    filas = (db.query(m.SuscripcionPushCliente)
             .filter_by(usuario_cliente_id=gente.id, activa=True).all())
    if not filas:
        raise HTTPException(409, "Este teléfono todavía no tiene los avisos "
                                 "activados")
    if not push.hay_llaves():
        raise HTTPException(503, "Los avisos al teléfono no están "
                                 "encendidos en el servidor")
    t = _tx(gente.idioma)
    carga = json.dumps({"titulo": t["prueba_titulo"],
                        "cuerpo": t["prueba_cuerpo"], "url": "/ci/#/yo",
                        "etiqueta": "prueba", "accion": None, "botones": {}})
    return push.entregar(db, filas, carga)

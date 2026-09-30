"""Entrar con huella o cara: las llaves de acceso (WebAuthn).

Decision de Salvador, 30 sep: en la consola y en la app de campo se
entra con la huella o la cara del telefono --o el Touch ID de la
computadora-- en vez de escribir la contrasena cada vez. Los telefonos
son de cada quien y no se prestan (lo dijo el): por eso se ofrece a
todos, tambien al personal de seguridad.

Como funciona, en corto. Al activarla, el telefono crea un par de llaves
para este sistema: la privada no sale nunca del telefono y solo se usa
despues de la huella; la publica se guarda aqui (`LlaveAcceso`). Al
entrar, el sistema manda un reto, el telefono lo firma tras la huella, y
aqui se comprueba la firma con la llave publica. La huella nunca viaja:
el sistema no la ve ni la guarda.

Lo que se cuida:

  - **El dominio.** Una llave vale solo para el sitio que la creo. La
    consola vive en mycentauro.lat y la app en appep.mycentauro.lat: la
    llave se ata al dominio de la empresa (`mycentauro.lat`), que cubre
    los dos, y solo se aceptan firmas hechas en esas direcciones.
  - **El reto se usa una vez.** Va firmado con la clave del sistema y
    vence en cinco minutos; ademas, el que ya se uso se anota en Redis y
    no se acepta otra vez.
  - **La cuenta tiene que seguir viva.** Una llave de alguien dado de
    baja no abre nada.
  - **La contrasena sigue sirviendo.** La huella es un atajo, no la unica
    puerta: si el telefono se pierde o se cambia, se entra con la
    contrasena y se quita la llave vieja.
"""
import base64
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import jwt
from fastapi import HTTPException
from sqlalchemy.orm import Session
from webauthn import (generate_authentication_options,
                      generate_registration_options, options_to_json,
                      verify_authentication_response,
                      verify_registration_response)
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
                                      PublicKeyCredentialDescriptor,
                                      ResidentKeyRequirement,
                                      UserVerificationRequirement)

from app import auth, intentos
from app import models as m
from app.config import es_desarrollo, settings

registro = logging.getLogger(__name__)

NOMBRE = "Centauro Connect"
MINUTOS_RETO = 5
# Cuantas llaves puede tener una persona: una por telefono o computadora.
MAXIMO_POR_PERSONA = 10


# ------------------------------------------------------------ el sitio

def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def _de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower() if url else ""


def sitio() -> str:
    """El dominio al que se atan las llaves: el de la consola sin `www.`
    --mycentauro.lat--, que cubre tambien a appep.mycentauro.lat. En la
    maquina de desarrollo, localhost."""
    host = _host(settings.url_publica)
    if not host:
        return "localhost"
    return host[4:] if host.startswith("www.") else host


def origenes() -> list[str]:
    """Las direcciones desde donde se acepta una huella: la consola, con
    y sin www, y la app de campo. En desarrollo, tambien localhost."""
    base = sitio()
    salida = []
    if base != "localhost":
        salida += [f"https://{base}", f"https://www.{base}"]
        campo = (settings.dominio_campo or "").strip().lower()
        if campo:
            salida.append(f"https://{campo}")
    if base == "localhost" or es_desarrollo(settings):
        salida += ["http://localhost:8000", "http://127.0.0.1:8000",
                   "http://localhost"]
    return salida


# ------------------------------------------------------------ el reto

def _firmar_reto(reto: bytes, uso: str, usuario_id: int | None) -> str:
    carga = {"reto": _b64(reto), "uso": uso,
             "exp": datetime.now(timezone.utc) + timedelta(minutes=MINUTOS_RETO)}
    if usuario_id is not None:
        carga["sub"] = str(usuario_id)
    return jwt.encode(carga, auth._clave(), algorithm=auth.ALGORITMO)


def _leer_reto(estado: str, uso: str) -> dict:
    try:
        carga = jwt.decode(estado or "", auth._clave(),
                           algorithms=[auth.ALGORITMO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(400, "Se tardo demasiado: vuelve a intentar.")
    except jwt.PyJWTError:
        raise HTTPException(400, "No se reconoce la solicitud: vuelve a intentar.")
    if carga.get("uso") != uso:
        raise HTTPException(400, "No se reconoce la solicitud: vuelve a intentar.")
    return carga


def _gastar_reto(reto: str) -> None:
    """Un reto se usa una sola vez. Sin Redis se confia en el vencimiento
    de cinco minutos, como el limite de intentos."""
    r = intentos._redis()
    if not r:
        return
    try:
        nuevo = r.set(f"llave:reto:{reto}", "1", nx=True,
                      ex=MINUTOS_RETO * 60 + 60)
    except Exception as error:                            # noqa: BLE001
        registro.warning("no se pudo anotar el reto: %s", error)
        return
    if not nuevo:
        raise HTTPException(400, "Esa solicitud ya se uso: vuelve a intentar.")


# ------------------------------------------------------------ dar de alta

def opciones_de_alta(db: Session, usuario: m.Usuario, contrasena: str,
                     ip: str | None = None) -> dict:
    """Lo que el telefono necesita para crear la llave de esta persona.

    Pide la contrasena otra vez, aunque ya haya sesion: quien se quedo
    con una sesion abierta ajena podria, si no, dar de alta su propio
    telefono y entrar para siempre. En la pantalla que se ofrece justo al
    entrar, la contrasena la manda la propia pantalla: no se escribe dos
    veces."""
    llave = auth.llave_de_correo(usuario.correo)
    intentos.revisar(llave, ip)
    if not auth.verificar(contrasena or "", usuario.hash_contrasena):
        intentos.fallo(llave, ip)
        # 403 y no 401: con sesion abierta, un 401 le diria a la pantalla
        # que la sesion vencio y la mandaria a la entrada.
        raise HTTPException(403, "La contrasena no es correcta.")
    ya = db.query(m.LlaveAcceso).filter_by(usuario_id=usuario.id).all()
    if len(ya) >= MAXIMO_POR_PERSONA:
        raise HTTPException(409, (
            f"Ya tienes {MAXIMO_POR_PERSONA} equipos con huella. Quita "
            "alguno que ya no uses para agregar este."))
    reto = secrets.token_bytes(32)
    opciones = generate_registration_options(
        rp_id=sitio(), rp_name=NOMBRE,
        user_id=str(usuario.id).encode(),
        user_name=usuario.correo,
        user_display_name=usuario.persona.nombre if usuario.persona else usuario.correo,
        challenge=reto,
        # La llave se queda en el telefono y se pide la huella (o el PIN
        # del equipo): una llave que no pide nada no es una huella.
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED),
        # El mismo telefono no se da de alta dos veces.
        exclude_credentials=[PublicKeyCredentialDescriptor(id=_de_b64(k.credencial_id))
                             for k in ya])
    return {"opciones": options_to_json(opciones),
            "estado": _firmar_reto(reto, "alta", usuario.id)}


def dar_de_alta(db: Session, usuario: m.Usuario, credencial: dict,
                estado: str, nombre: str | None) -> m.LlaveAcceso:
    carga = _leer_reto(estado, "alta")
    if carga.get("sub") != str(usuario.id):
        raise HTTPException(400, "No se reconoce la solicitud: vuelve a intentar.")
    _gastar_reto(carga["reto"])
    try:
        hecho = verify_registration_response(
            credential=credencial, expected_challenge=_de_b64(carga["reto"]),
            expected_rp_id=sitio(), expected_origin=origenes(),
            require_user_verification=True)
    except Exception as error:                            # noqa: BLE001
        registro.info("alta de llave rechazada: %s", error)
        raise HTTPException(400, "El equipo no pudo registrar la huella: "
                                 "vuelve a intentar.")
    credencial_id = _b64(hecho.credential_id)
    if db.query(m.LlaveAcceso).filter_by(credencial_id=credencial_id).first():
        raise HTTPException(409, "Este equipo ya tiene la huella activada.")
    llave = m.LlaveAcceso(
        usuario_id=usuario.id, credencial_id=credencial_id,
        llave_publica=_b64(hecho.credential_public_key),
        contador=hecho.sign_count,
        nombre=(nombre or "").strip()[:120] or "Este equipo")
    db.add(llave)
    db.commit()
    db.refresh(llave)
    return llave


# ------------------------------------------------------------ entrar

def opciones_de_entrada(db: Session, correo: str | None) -> dict:
    """El reto para entrar. Con el correo, el telefono ofrece solo las
    llaves de esa persona; sin el, las que tenga para este sistema. La
    respuesta es la misma exista o no la cuenta: decir "ese correo no
    tiene huella" regalaria que el correo existe."""
    reto = secrets.token_bytes(32)
    permitidas = []
    llave_de = auth.llave_de_correo(correo) if correo else None
    if llave_de:
        usuario = auth.usuario_por_correo(db, llave_de)
        if usuario:
            permitidas = [PublicKeyCredentialDescriptor(id=_de_b64(k.credencial_id))
                          for k in db.query(m.LlaveAcceso)
                                     .filter_by(usuario_id=usuario.id).all()]
    opciones = generate_authentication_options(
        rp_id=sitio(), challenge=reto, allow_credentials=permitidas or None,
        user_verification=UserVerificationRequirement.REQUIRED)
    return {"opciones": options_to_json(opciones),
            "estado": _firmar_reto(reto, "entrada", None)}


def entrar(db: Session, credencial: dict, estado: str) -> m.Usuario:
    """Comprueba la firma y devuelve a quien entra."""
    carga = _leer_reto(estado, "entrada")
    credencial_id = (credencial or {}).get("id") or ""
    llave = db.query(m.LlaveAcceso).filter_by(credencial_id=credencial_id).first()
    if not llave:
        raise HTTPException(401, "Este equipo no tiene la huella activada. "
                                 "Entra con tu contrasena y vuelve a activarla.")
    _gastar_reto(carga["reto"])
    try:
        hecho = verify_authentication_response(
            credential=credencial, expected_challenge=_de_b64(carga["reto"]),
            expected_rp_id=sitio(), expected_origin=origenes(),
            credential_public_key=_de_b64(llave.llave_publica),
            credential_current_sign_count=llave.contador,
            require_user_verification=True)
    except Exception as error:                            # noqa: BLE001
        registro.info("entrada con llave rechazada: %s", error)
        raise HTTPException(401, "No se pudo comprobar la huella: vuelve a "
                                 "intentar o entra con tu contrasena.")
    usuario = llave.usuario
    if not usuario or not usuario.activo:
        raise HTTPException(403, "Ese acceso esta desactivado")
    llave.contador = hecho.new_sign_count
    llave.usada_en = datetime.now(timezone.utc)
    usuario.ultimo_acceso = datetime.now()
    db.commit()
    return usuario


# ------------------------------------------------------------ las suyas

def de(db: Session, usuario: m.Usuario) -> list[dict]:
    return [{"id": k.id, "nombre": k.nombre,
             "creada_en": k.creada_en.isoformat() if k.creada_en else None,
             "usada_en": k.usada_en.isoformat() if k.usada_en else None,
             "credencial_id": k.credencial_id}
            for k in (db.query(m.LlaveAcceso)
                        .filter_by(usuario_id=usuario.id)
                        .order_by(m.LlaveAcceso.id).all())]


def quitar(db: Session, usuario: m.Usuario, llave_id: int) -> None:
    """Solo las suyas: una llave ajena da 404, igual que una que no existe."""
    llave = db.get(m.LlaveAcceso, llave_id)
    if not llave or llave.usuario_id != usuario.id:
        raise HTTPException(404, "No existe esa llave")
    db.delete(llave)
    db.commit()

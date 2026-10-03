# -*- coding: utf-8 -*-
"""LG Connect: la app de los operadores de Logistica (seccion 151).

Decision de Salvador, 3 de octubre: los operadores de Logistica no usan la
app de campo de Proteccion Ejecutiva. Tienen la suya, en su propia
direccion (applg.mycentauro.lat), con sus propios usuarios: un operador
de Logistica no ve nada de EP ni un agente de EP ve nada de Logistica.
Por debajo usa las mismas piezas que la de EP --la contrasena, el limite
de intentos, la huella o la cara, la geocerca--, pero su sesion es otra:
su token lleva `tipo` y la consola y la app de EP no aceptan ningun token
con `tipo` (`auth._es_sesion`); esta, solo los suyos.

Entra con su correo personal --el que tiene en Odoo, como en EP-- y su
contrasena. La primera vez, o si la olvida, con los cuatro digitos que le
dicta por telefono Karla o quien lleve la flota: diez minutos, cinco
intentos, guardados cifrados. Despues puede entrar con huella o cara.

En este bloque la app solo deja entrar y marcar la jornada; viajes,
hitos, evidencias, gastos y panico llegan en el bloque 6.
"""
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from webauthn import (generate_authentication_options,
                      generate_registration_options, options_to_json,
                      verify_authentication_response,
                      verify_registration_response)
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
                                      PublicKeyCredentialDescriptor,
                                      ResidentKeyRequirement,
                                      UserVerificationRequirement)

from app import auth, contrasenas, intentos, lg_flota, lg_jornada, llaves
from app import models as m
from app.db import get_db

TIPO_SESION = "operador_lg"
DIAS_SESION = 30
DIGITOS = contrasenas.DIGITOS
MINUTOS_CODIGO = contrasenas.MINUTOS_CODIGO
FALLOS_MAXIMOS = contrasenas.FALLOS_MAXIMOS
NOMBRE_APP = "LG Connect"

_no = lg_flota._no


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ================================================================ la sesion

def crear_token(operador: m.LgOperador) -> str:
    ahora = _ahora()
    carga = {"sub": str(operador.id), "tipo": TIPO_SESION, "iat": ahora,
             "emitido": ahora.timestamp(), "exp": ahora + timedelta(days=DIAS_SESION)}
    return jwt.encode(carga, auth._clave(), algorithm=auth.ALGORITMO)


def operador_actual(token: str | None = Depends(auth.esquema),
                    db: Session = Depends(get_db)) -> m.LgOperador:
    """Solo un token de LG Connect abre la app de los operadores: ni el de
    la consola ni el de la app de EP, que no llevan este `tipo`."""
    sin_acceso = HTTPException(status.HTTP_401_UNAUTHORIZED, "Se requiere iniciar sesion",
                               headers={"WWW-Authenticate": "Bearer"})
    if not token:
        raise sin_acceso
    try:
        carga = jwt.decode(token, auth._clave(), algorithms=[auth.ALGORITMO])
    except jwt.PyJWTError:
        raise sin_acceso
    if carga.get("tipo") != TIPO_SESION or not str(carga.get("sub") or "").isdigit():
        raise sin_acceso
    operador = db.get(m.LgOperador, int(carga["sub"]))
    if not operador or not operador.activo:
        raise sin_acceso
    desde = operador.sesiones_desde
    if desde and float(carga.get("emitido") or 0) < desde.timestamp():
        raise sin_acceso
    return operador


def por_correo(db: Session, correo: str | None) -> m.LgOperador | None:
    llave = auth.llave_de_correo(correo)
    if not llave:
        return None
    return (db.query(m.LgOperador)
            .filter(func.lower(func.trim(m.LgOperador.correo)) == llave).first())


_RELLENO: list[str] = []


def _hash_de_relleno() -> str:
    if not _RELLENO:
        _RELLENO.append(auth.cifrar(secrets.token_urlsafe(16)))
    return _RELLENO[0]


def _sesion(operador: m.LgOperador) -> dict:
    operador.ultimo_acceso = _ahora()
    return {"access_token": crear_token(operador), "token_type": "bearer",
            "correo": operador.correo, "nombre": operador.nombre,
            "idioma": operador.idioma}


def entrar(db: Session, correo: str, contrasena: str, ip: str | None = None) -> dict:
    """Con el mismo tope de intentos que la consola, en su propio carril."""
    llave = auth.llave_de_correo(correo)
    carril = f"lg:{llave}"
    intentos.revisar(carril, ip)
    operador = por_correo(db, llave)
    hash_ = operador.hash_contrasena if operador else None
    # Contra una de a mentiras si no hay cuenta: que tarde lo mismo, para
    # que el tiempo no diga que correos existen.
    if not auth.verificar(contrasena or "", hash_ or _hash_de_relleno()) or not hash_:
        intentos.fallo(carril, ip)
        raise HTTPException(401, "Correo o contrasena incorrectos")
    if not operador.activo:
        raise HTTPException(403, "Ese acceso esta cerrado. Pídele a tu gerente que lo abra.")
    intentos.exito(carril, ip)
    return _sesion(operador)


# ================================================================ el codigo

def _anular_codigos(db: Session, operador_id: int) -> None:
    ahora = _ahora()
    for c in db.query(m.LgCodigoAcceso).filter(
            m.LgCodigoAcceso.operador_id == operador_id,
            m.LgCodigoAcceso.usado_en.is_(None), m.LgCodigoAcceso.anulado_en.is_(None)):
        c.anulado_en = ahora


def dar_codigo(db: Session, actor: m.Usuario, operador_id: int) -> dict:
    """Los cuatro digitos que se le dictan al operador por telefono. Se
    ven una sola vez: si se cierra la tarjeta, se genera otro y ese mata
    a este."""
    operador = db.get(m.LgOperador, operador_id)
    if not operador or not operador.activo:
        raise HTTPException(404, "Ese operador no existe o está dado de baja")
    if not operador.correo:
        raise _no({"mensaje": f"{operador.nombre} no tiene correo en Odoo.",
                   "que_hacer": "Recursos Humanos tiene que capturar su correo personal "
                                "en Odoo: con él entra a LG Connect."}, 409)
    _anular_codigos(db, operador.id)
    codigo = f"{secrets.randbelow(10 ** DIGITOS):0{DIGITOS}d}"
    expira = _ahora() + timedelta(minutes=MINUTOS_CODIGO)
    db.add(m.LgCodigoAcceso(operador_id=operador.id, hash=auth.cifrar(codigo),
                            expira_en=expira, fallos=0, dado_por_id=actor.persona_id))
    lg_flota._anotar(db, actor, "lg codigo de la app", "lg_operadores", operador.id,
                     {"k": "codigo", "o": operador.nombre})
    db.flush()
    return {"codigo": codigo, "expira_en": expira.isoformat(), "minutos": MINUTOS_CODIGO,
            "correo": operador.correo, "nombre": operador.nombre}


def usar_codigo(db: Session, correo: str, codigo: str, nueva: str,
                ip: str | None = None) -> dict:
    """Con el codigo, el operador crea su contrasena y queda adentro."""
    llave = auth.llave_de_correo(correo)
    carril = f"lg:{llave}"
    intentos.revisar(carril, ip)
    operador = por_correo(db, llave)
    vigente = None
    if operador:
        vigente = (db.query(m.LgCodigoAcceso)
                   .filter(m.LgCodigoAcceso.operador_id == operador.id,
                           m.LgCodigoAcceso.usado_en.is_(None),
                           m.LgCodigoAcceso.anulado_en.is_(None),
                           m.LgCodigoAcceso.expira_en > _ahora())
                   .order_by(m.LgCodigoAcceso.id.desc()).first())
    if not vigente:
        intentos.fallo(carril, ip)
        raise _no({"mensaje": "Ese código no sirve o ya venció.",
                   "que_hacer": "Pídele uno nuevo a tu gerente: dura diez minutos."}, 400)
    if not auth.verificar(str(codigo or "").strip(), vigente.hash):
        vigente.fallos += 1
        if vigente.fallos >= FALLOS_MAXIMOS:
            vigente.anulado_en = _ahora()
        intentos.fallo(carril, ip)
        db.commit()
        raise _no({"mensaje": "Ese código no sirve o ya venció.",
                   "que_hacer": "Pídele uno nuevo a tu gerente: dura diez minutos."}, 400)
    contrasenas.validar(nueva or "", operador)
    vigente.usado_en = _ahora()
    operador.hash_contrasena = auth.cifrar(nueva)
    # Cambiar la contrasena cierra las sesiones de antes y quita sus
    # huellas, como en la consola: quien la cambia es porque algo paso.
    operador.sesiones_desde = _ahora()
    db.query(m.LgLlave).filter(m.LgLlave.operador_id == operador.id).delete()
    intentos.exito(carril, ip)
    return _sesion(operador)


def cambiar_contrasena(db: Session, operador: m.LgOperador, actual: str, nueva: str) -> dict:
    if not auth.verificar(actual or "", operador.hash_contrasena):
        raise HTTPException(403, "La contraseña actual no es correcta.")
    contrasenas.validar(nueva or "", operador)
    operador.hash_contrasena = auth.cifrar(nueva)
    operador.sesiones_desde = _ahora()
    db.query(m.LgLlave).filter(m.LgLlave.operador_id == operador.id).delete()
    return _sesion(operador)


# ================================================================ la huella

def opciones_de_alta(db: Session, operador: m.LgOperador, contrasena: str,
                     ip: str | None = None) -> dict:
    carril = f"lg:{auth.llave_de_correo(operador.correo)}"
    intentos.revisar(carril, ip)
    if not auth.verificar(contrasena or "", operador.hash_contrasena):
        intentos.fallo(carril, ip)
        raise HTTPException(403, "La contraseña no es correcta.")
    intentos.exito(carril, ip)
    ya = db.query(m.LgLlave).filter_by(operador_id=operador.id).all()
    if len(ya) >= llaves.MAXIMO_POR_PERSONA:
        raise HTTPException(409, "Ya tienes demasiados teléfonos con huella. Quita "
                                 "alguno que ya no uses.")
    reto = secrets.token_bytes(32)
    opciones = generate_registration_options(
        rp_id=llaves.sitio(), rp_name=NOMBRE_APP,
        user_id=f"lg-{operador.id}".encode(), user_name=operador.correo or operador.nombre,
        user_display_name=operador.nombre, challenge=reto,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=llaves._de_b64(k.credencial_id))
                             for k in ya])
    return {"opciones": options_to_json(opciones),
            "estado": llaves._firmar_reto(reto, "lg_alta", operador.id)}


def dar_de_alta(db: Session, operador: m.LgOperador, credencial: dict, estado: str,
                nombre: str | None) -> m.LgLlave:
    carga = llaves._leer_reto(estado, "lg_alta")
    if carga.get("sub") != str(operador.id):
        raise HTTPException(400, "No se reconoce la solicitud: vuelve a intentar.")
    llaves._gastar_reto(carga["reto"])
    try:
        hecho = verify_registration_response(
            credential=credencial, expected_challenge=llaves._de_b64(carga["reto"]),
            expected_rp_id=llaves.sitio(), expected_origin=llaves.origenes(),
            require_user_verification=True)
    except Exception:                                      # noqa: BLE001
        raise HTTPException(400, "El teléfono no pudo registrar la huella: "
                                 "vuelve a intentar.")
    credencial_id = llaves._b64(hecho.credential_id)
    if db.query(m.LgLlave).filter_by(credencial_id=credencial_id).first():
        raise HTTPException(409, "Este teléfono ya tiene la huella activada.")
    llave = m.LgLlave(operador_id=operador.id, credencial_id=credencial_id,
                      llave_publica=llaves._b64(hecho.credential_public_key),
                      contador=hecho.sign_count,
                      nombre=(nombre or "").strip()[:120] or "Este teléfono")
    db.add(llave)
    db.flush()
    return llave


def opciones_de_entrada(db: Session, correo: str | None) -> dict:
    reto = secrets.token_bytes(32)
    permitidas = []
    llave_de = auth.llave_de_correo(correo) if correo else None
    if llave_de:
        operador = por_correo(db, llave_de)
        if operador:
            permitidas = [PublicKeyCredentialDescriptor(id=llaves._de_b64(k.credencial_id))
                          for k in db.query(m.LgLlave).filter_by(operador_id=operador.id)]
        permitidas = permitidas or llaves._de_mentira(f"lg:{llave_de}")
    opciones = generate_authentication_options(
        rp_id=llaves.sitio(), challenge=reto, allow_credentials=permitidas or None,
        user_verification=UserVerificationRequirement.REQUIRED)
    return {"opciones": options_to_json(opciones),
            "estado": llaves._firmar_reto(reto, "lg_entrada", None)}


def entrar_con_huella(db: Session, credencial: dict, estado: str) -> dict:
    carga = llaves._leer_reto(estado, "lg_entrada")
    credencial_id = (credencial or {}).get("id") or ""
    if not isinstance(credencial_id, str) or len(credencial_id) > 1024:
        raise HTTPException(400, "No se reconoce la solicitud: vuelve a intentar.")
    llave = db.query(m.LgLlave).filter_by(credencial_id=credencial_id).first()
    if not llave:
        raise HTTPException(401, {
            "mensaje": "Este teléfono ya no tiene la huella activada.",
            "que_hacer": "Entra con tu contraseña y vuelve a activarla.",
            "codigo": "huella_desconocida"})
    llaves._gastar_reto(carga["reto"])
    try:
        hecho = verify_authentication_response(
            credential=credencial, expected_challenge=llaves._de_b64(carga["reto"]),
            expected_rp_id=llaves.sitio(), expected_origin=llaves.origenes(),
            credential_public_key=llaves._de_b64(llave.llave_publica),
            credential_current_sign_count=llave.contador, require_user_verification=True)
    except Exception:                                      # noqa: BLE001
        raise HTTPException(401, {
            "mensaje": "No se pudo comprobar la huella: vuelve a intentar o entra "
                       "con tu contraseña.",
            "que_hacer": "Si sigue fallando, entra con tu contraseña, quita la huella "
                         "de este teléfono y actívala otra vez.",
            "codigo": "huella_rechazada"})
    operador = llave.operador
    if not operador or not operador.activo:
        raise HTTPException(403, "Ese acceso esta cerrado. Pídele a tu gerente que lo abra.")
    llave.contador = hecho.new_sign_count
    llave.usada_en = _ahora()
    return _sesion(operador)


def mis_llaves(db: Session, operador: m.LgOperador) -> list[dict]:
    return [{"id": k.id, "nombre": k.nombre, "credencial_id": k.credencial_id,
             "creada_en": lg_flota._iso(k.creada_en), "usada_en": lg_flota._iso(k.usada_en)}
            for k in db.query(m.LgLlave).filter_by(operador_id=operador.id)
                       .order_by(m.LgLlave.id)]


def quitar_llave(db: Session, operador: m.LgOperador, llave_id: int) -> None:
    llave = db.get(m.LgLlave, llave_id)
    if not llave or llave.operador_id != operador.id:
        raise HTTPException(404, "No existe esa llave")
    db.delete(llave)


# ================================================================ mi dia

def mi_dia(db: Session, operador: m.LgOperador) -> dict:
    """Lo que ve el operador al abrir: su marca de hoy, su semana y los
    patios con su geocerca para saber si esta adentro antes de marcar."""
    hoy = lg_flota.hoy()
    marca = (db.query(m.LgJornada).filter(m.LgJornada.operador_id == operador.id,
                                          m.LgJornada.fecha == hoy).first())
    semana = lg_jornada.semana(db, hoy)
    mia = next((x for x in semana["operadores"] if x["id"] == operador.id), None)
    patios = [{"id": p.id, "nombre": p.nombre, "lat": float(p.lat), "lon": float(p.lon),
               "radio": p.geocerca_metros}
              for p in db.query(m.LgPatio).filter(m.LgPatio.activo.is_(True)).all()
              if p.lat is not None and p.lon is not None]
    return {"hoy": hoy.isoformat(), "nombre": operador.nombre, "correo": operador.correo,
            "idioma": operador.idioma, "marca": lg_jornada._marca_dict(marca),
            "en_viaje": bool(lg_jornada.en_viaje(
                lg_jornada.viajes_de(db, [operador.id], hoy, hoy).get(operador.id), hoy)),
            "semana": {"dias": mia["dias"] if mia else [], "activos": mia["activos"] if mia else 0,
                       "bono": mia["bono"] if mia else "no"},
            "patios": patios}

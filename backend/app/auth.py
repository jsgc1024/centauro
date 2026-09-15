"""Autenticacion y permisos por rol."""
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings
from app.db import get_db

ALGORITMO = "HS256"
HORAS_SESION = 12
HORAS_INVITACION = 72

esquema = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def _clave() -> str:
    # Sin segunda copia de la clave. Tenerla escrita aqui abajo
    # contradecia la revision que se hace al arrancar: dejaba una firma
    # valida a la mano de cualquiera que leyera el codigo.
    clave = getattr(settings, "secret_key", None)
    if not clave:
        raise RuntimeError("No hay SECRET_KEY configurada.")
    return clave


# ---------------------------------------------------------------- contrasenas

def cifrar(contrasena: str) -> str:
    return bcrypt.hashpw(contrasena.encode(), bcrypt.gensalt()).decode()


def verificar(contrasena: str, hash_guardado: str | None) -> bool:
    if not hash_guardado:
        return False
    return bcrypt.checkpw(contrasena.encode(), hash_guardado.encode())


def token_invitacion() -> tuple[str, datetime]:
    return secrets.token_urlsafe(32), datetime.now() + timedelta(hours=HORAS_INVITACION)


# ---------------------------------------------------------------- sesion

def crear_token(usuario: m.Usuario) -> str:
    ahora = datetime.now(timezone.utc)
    carga = {
        "sub": str(usuario.id),
        "correo": usuario.correo,
        "rol": usuario.rol.value,
        "persona_id": usuario.persona_id,
        "iat": ahora,
        "exp": ahora + timedelta(hours=HORAS_SESION),
    }
    return jwt.encode(carga, _clave(), algorithm=ALGORITMO)


def usuario_opcional(token: str | None = Depends(esquema),
                     db: Session = Depends(get_db)) -> m.Usuario | None:
    """Quien sea que venga, o nadie. No levanta 401.

    Para las pocas puertas cuyo permiso no depende solo del rol —el
    sembrado inicial se abre mientras la base no tenga ni un usuario, y
    se cierra sola en cuanto lo tiene.
    """
    if not token:
        return None
    try:
        carga = jwt.decode(token, _clave(), algorithms=[ALGORITMO])
    except jwt.PyJWTError:
        return None
    usuario = db.get(m.Usuario, int(carga["sub"]))
    return usuario if usuario and usuario.activo else None


def usuario_actual(token: str | None = Depends(esquema),
                   db: Session = Depends(get_db)) -> m.Usuario:
    sin_acceso = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Se requiere iniciar sesion",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise sin_acceso
    try:
        carga = jwt.decode(token, _clave(), algorithms=[ALGORITMO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "La sesion expiro, vuelve a iniciar sesion")
    except jwt.InvalidTokenError:
        raise sin_acceso

    usuario = db.get(m.Usuario, int(carga["sub"]))
    if not usuario or not usuario.activo:
        raise sin_acceso
    return usuario


# La direccion general alcanza todo lo operativo, pero no la administracion
# de catalogos y tarifarios, que queda en el rol de administracion.
HEREDA = {
    m.Rol.DIRECTOR_GENERAL: {
        m.Rol.DIRECTOR_OPERACIONES, m.Rol.CONSULTOR,
        m.Rol.CENTRAL, m.Rol.FINANZAS,
    },
}


def requiere(*roles: m.Rol):
    """Dependencia que restringe un endpoint a ciertos roles."""
    permitidos = set(roles)

    def verificador(usuario: m.Usuario = Depends(usuario_actual)) -> m.Usuario:
        # Solo el administrador pasa por ser administrador. Que el endpoint
        # pida rol de administracion NO abre la puerta a los demas.
        if usuario.rol == m.Rol.ADMIN:
            return usuario
        if HEREDA.get(usuario.rol, set()) & permitidos:
            return usuario
        if usuario.rol not in permitidos:
            raise HTTPException(403, {
                "mensaje": "Tu rol no tiene permiso para esta accion",
                "tu_rol": usuario.rol.value,
                "roles_permitidos": sorted(r.value for r in permitidos),
            })
        return usuario

    return verificador


def puede(actividad: str):
    """Dependencia que restringe un endpoint a una actividad con nombre.

    Por dentro sigue siendo el mismo control por rol de siempre; lo que
    cambia es la pregunta. Cuando exista el panel de permisos, la lista de
    roles de cada actividad saldra de la base y estos endpoints no se
    tocan.
    """
    from app import permisos

    def verificador(usuario: m.Usuario = Depends(usuario_actual)) -> m.Usuario:
        permitidos = permisos.roles_de(actividad)
        if usuario.rol == m.Rol.ADMIN:
            return usuario
        if HEREDA.get(usuario.rol, set()) & permitidos:
            return usuario
        if usuario.rol not in permitidos:
            raise HTTPException(403, {
                "mensaje": "Tu rol no tiene permiso para esta accion",
                "actividad": actividad,
                "tu_rol": usuario.rol.value,
                "roles_permitidos": sorted(r.value for r in permitidos),
            })
        return usuario

    return verificador


def es_su_propia_jornada(db: Session, usuario: m.Usuario, jornada_id: int) -> bool:
    """El personal de seguridad solo puede actuar sobre jornadas donde esta asignado."""
    return (db.query(m.AsignacionPersonal)
            .filter_by(jornada_id=jornada_id, persona_id=usuario.persona_id)
            .first() is not None)

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
        # La misma hora, con fracciones. `iat` va en segundos enteros por
        # estandar, y comparar segundos contra fracciones deja una
        # ventana de hasta un segundo en la que un token emitido justo
        # antes de cambiar la contrasena sobrevive al cambio.
        "emitido": ahora.timestamp(),
        "exp": ahora + timedelta(hours=horas_de_sesion(usuario)),
    }
    return jwt.encode(carga, _clave(), algorithm=ALGORITMO)


def _token_viejo(usuario: m.Usuario, carga: dict) -> bool:
    """Si ese token se emitio antes del ultimo cambio de contrasena.

    El token no tiene estado: una vez firmado vale doce horas y no hay
    lista de sesiones que cancelar. Sin esta comparacion, cambiar la
    contrasena no le quitaba nada a quien ya tenia la sesion abierta, que
    es justo de quien uno se quiere deshacer al cambiarla.
    """
    desde = usuario.sesiones_desde
    if not desde:
        return False

    emitido = carga.get("emitido")
    if emitido is not None:
        # Las dos horas exactas: sin ventana ciega.
        return float(emitido) < desde.timestamp()

    # Token de antes de que se firmara la hora exacta. Se comparan los
    # dos lados truncados al segundo, que es lo mas que se puede saber de
    # el. Estos se acaban solos cuando expiran, a las doce horas.
    return int(carga.get("iat") or 0) < int(desde.timestamp())


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
    if not usuario or not usuario.activo or _token_viejo(usuario, carga):
        return None
    return usuario


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
    if _token_viejo(usuario, carga):
        raise HTTPException(401, "La contrasena cambio, vuelve a iniciar sesion")
    return usuario


# La direccion general alcanza todo, administracion incluida.
#
# Antes no: llegaba a todo lo operativo pero no a catalogos ni
# tarifarios, y la razon era de control interno --quien aprueba un margen
# no deberia poder cambiar en silencio el precio con el que se calcula
# ese margen--. Se le planteo asi a la direccion y decidio alcanzarlo
# todo. Queda escrito que fue una decision y no un descuido.
#
# La consecuencia: un cambio de precio hecho por direccion general ya no
# tiene candado que lo detenga, solo bitacora que lo cuente. Por eso la
# bitacora de catalogos dejo de ser un lujo (ver PROPUESTA_ACCESOS.md).
HEREDA = {
    m.Rol.DIRECTOR_GENERAL: {
        m.Rol.DIRECTOR_OPERACIONES, m.Rol.CONSULTOR,
        m.Rol.CENTRAL, m.Rol.FINANZAS, m.Rol.ADMIN,
        m.Rol.RECURSOS_HUMANOS,
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


def puede_el_usuario(db: Session, usuario: m.Usuario, actividad: str) -> bool:
    """La pregunta completa: esta persona, esta actividad.

    El orden importa:

    1. **Administracion pasa siempre.** Si no, un error de configuracion
       deja a la empresa sin poder arreglar la configuracion.
    2. **Un permiso extra** que alguien le dio a esta persona de mas.
       Solo dan, nunca quitan: para quitar se le hace una categoria que
       no lo traiga, y entonces su renglon dice la verdad.
    3. **Su categoria**, si la tiene. Manda sobre el rol: de eso se trata.
    4. **Su rol**, si no tiene categoria. Es como funciono el sistema
       hasta que las categorias existieron, y por eso el dia que se
       aplican no le cambia nada a nadie.

    Una categoria desactivada sigue mandando para quien ya la trae: el
    `activa` solo decide si se ofrece al asignar. Apagar una categoria y
    que su gente ganara permisos de golpe seria lo contrario de lo que
    uno quiere al apagarla.
    """
    from app import permisos

    if usuario.rol == m.Rol.ADMIN:
        return True

    suelto = (db.query(m.PermisoExtra.id)
              .filter_by(usuario_id=usuario.id, actividad=actividad).first())
    if suelto:
        return True

    if usuario.categoria_id:
        return (db.query(m.ActividadDeCategoria.id)
                .filter_by(categoria_id=usuario.categoria_id,
                           actividad=actividad).first()) is not None

    permitidos = permisos.roles_de(actividad)
    if usuario.rol in permitidos:
        return True
    return bool(HEREDA.get(usuario.rol, set()) & permitidos)


def _puestos_que_traen(db: Session, actividad: str) -> list[str]:
    """Los puestos activos que traen esta actividad, en el orden de la
    pantalla de accesos."""
    filas = (db.query(m.CategoriaAcceso.nombre)
             .join(m.ActividadDeCategoria,
                   m.ActividadDeCategoria.categoria_id == m.CategoriaAcceso.id)
             .filter(m.ActividadDeCategoria.actividad == actividad,
                     m.CategoriaAcceso.activa.is_(True))
             .order_by(m.CategoriaAcceso.orden.asc().nulls_last(),
                       m.CategoriaAcceso.nombre)
             .all())
    return [n for (n,) in filas]


def puede(actividad: str):
    """Dependencia que restringe un endpoint a una actividad con nombre.

    Lo que cambia con las categorias no es esto: los endpoints preguntan
    igual que antes. Lo que cambia es de donde sale la respuesta.
    """
    def verificador(usuario: m.Usuario = Depends(usuario_actual),
                    db: Session = Depends(get_db)) -> m.Usuario:
        if puede_el_usuario(db, usuario, actividad):
            return usuario
        from app import permisos
        quienes = sorted(r.value.replace("_", " ")
                         for r in permisos.roles_de(actividad))
        # Quien si puede, dicho en el mensaje y no solo en el detalle.
        # "No tienes permiso" a secas deja a alguien mirando un boton sin
        # saber a quien hablarle, y la pantalla no lo puede adivinar.
        if usuario.categoria:
            # Con puesto, el rol no explica nada: un consultor JR es
            # consultor y aun asi no asigna viaticos. Se dice su puesto y
            # que puestos si lo traen (seccion 73).
            puestos = _puestos_que_traen(db, actividad)
            que_hacer = (f"Tu puesto, {usuario.categoria.nombre}, no lo "
                         f"incluye. " + (f"Lo hace: {', '.join(puestos)}."
                                         if puestos else
                                         "Se da desde la pantalla de "
                                         "accesos."))
        elif quienes:
            que_hacer = (f"Esto lo hace: {', '.join(quienes)}. "
                         f"Tu entraste como "
                         f"{usuario.rol.value.replace('_', ' ')}.")
        else:
            que_hacer = ("Nadie tiene esta actividad asignada todavia; "
                         "se da desde la pantalla de accesos.")
        raise HTTPException(403, {
            "mensaje": "No tienes permiso para esta accion",
            "que_hacer": que_hacer,
            "actividad": actividad,
            "tu_rol": usuario.rol.value,
            "tu_categoria": (usuario.categoria.nombre
                             if usuario.categoria else None),
            "roles_permitidos": sorted(
                r.value for r in permisos.roles_de(actividad)),
        })

    return verificador


def horas_de_sesion(usuario: m.Usuario) -> int:
    """Cuanto le dura la sesion a esta persona.

    Doce horas parejas para todos no sirven: quien esta en la calle
    vuelve a entrar a media jornada, y una computadora de oficina que se
    queda prendida sigue abierta toda la tarde.
    """
    categoria = usuario.categoria
    if categoria and categoria.horas_sesion:
        return categoria.horas_sesion
    return HORAS_SESION


def es_su_propia_jornada(db: Session, usuario: m.Usuario, jornada_id: int) -> bool:
    """El personal de seguridad solo puede actuar sobre jornadas donde esta asignado."""
    return (db.query(m.AsignacionPersonal)
            .filter_by(jornada_id=jornada_id, persona_id=usuario.persona_id)
            .first() is not None)

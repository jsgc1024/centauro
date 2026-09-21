"""Paso 1b: las puertas, y el alcance de direccion general.

Decision de Salvador (18 sep): direccion general queda como super
administrador, con alcance a todo. Eso cambia a proposito la raya que
`HEREDA` tenia puesta --le daba todo lo operativo pero no la
administracion de catalogos y tarifarios-- y queda escrito en
PROPUESTA_ACCESOS.md por que se quito.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- 1. direccion general alcanza administracion --------------------
R = RAIZ / "backend/app/auth.py"
s = R.read_text()
VIEJO = '''# La direccion general alcanza todo lo operativo, pero no la administracion
# de catalogos y tarifarios, que queda en el rol de administracion.
HEREDA = {
    m.Rol.DIRECTOR_GENERAL: {
        m.Rol.DIRECTOR_OPERACIONES, m.Rol.CONSULTOR,
        m.Rol.CENTRAL, m.Rol.FINANZAS,
    },
}'''
NUEVO = '''# La direccion general alcanza todo, administracion incluida.
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
    },
}'''
assert s.count(VIEJO) == 1, "no encontre HEREDA"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("auth.py: direccion general alcanza administracion")

# --- 2. las puertas -------------------------------------------------
R = RAIZ / "backend/app/routers/acceso.py"
s = R.read_text()

VIEJO = '''from app import auth, intentos
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["Acceso"])


class AltaUsuarioIn(BaseModel):
    persona_id: int
    rol: m.Rol
'''
NUEVO = '''from app import accesos, auth, intentos
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["Acceso"])

# Administracion y direccion general. La segunda alcanza esto por
# `HEREDA`, pero se nombra aqui para que se lea sin ir a buscarlo.
ADMINISTRA = auth.requiere(m.Rol.ADMIN, m.Rol.DIRECTOR_GENERAL)


class AltaUsuarioIn(BaseModel):
    persona_id: int
    rol: m.Rol


class MotivoIn(BaseModel):
    """Por que se cierra o se abre una puerta. Opcional, pero si se
    escribe queda en la bitacora y es lo que se lee un ano despues."""
    motivo: str | None = None


class CambioRolIn(BaseModel):
    rol: m.Rol
    motivo: str | None = None
'''
assert s.count(VIEJO) == 1, "no encontre la cabecera"
s = s.replace(VIEJO, NUEVO)

ANCLA = '''@router.post("/establecer-contrasena", summary="El empleado crea su contrasena")'''
PUERTAS = '''@router.get("/usuarios", summary="Quien tiene acceso al sistema")
def listar_usuarios(db: Session = Depends(get_db), incluir_inactivos: bool = True,
                    _: m.Usuario = Depends(ADMINISTRA)):
    """La lista con lo que hace falta para decidir: quien es, con que rol
    entra, si sigue activo y cuando entro por ultima vez.

    Lo ultimo es el dato que nadie miraba: una cuenta que nunca se uso es
    un acceso que se dio y no se ocupo, y una que lleva meses dormida es
    una puerta abierta a nombre de alguien que quiza ya no esta.
    """
    consulta = db.query(m.Usuario)
    if not incluir_inactivos:
        consulta = consulta.filter(m.Usuario.activo.is_(True))
    filas = consulta.order_by(m.Usuario.correo).all()
    return [{
        "usuario_id": u.id,
        "persona_id": u.persona_id,
        "nombre": u.persona.nombre if u.persona else None,
        "correo": u.correo,
        "rol": u.rol.value,
        "activo": u.activo,
        # Sin contrasena: se le dio el acceso y nunca lo estreno.
        "estrenado": u.hash_contrasena is not None,
        "ultimo_acceso": (u.ultimo_acceso.isoformat()
                          if u.ultimo_acceso else None),
        # Dado de baja como empleado pero con el acceso abierto. Hoy no
        # deberia pasar; el dia que Odoo mande las bajas, esta es la
        # senal de que algo quedo a medias.
        "persona_de_baja": bool(u.persona and not u.persona.activo),
    } for u in filas]


@router.post("/usuarios/{usuario_id}/desactivar",
             summary="Cerrarle la puerta a alguien")
def desactivar_usuario(usuario_id: int, datos: MotivoIn,
                       db: Session = Depends(get_db),
                       actor: m.Usuario = Depends(ADMINISTRA)):
    """La sesion que tenga abierta muere en su siguiente peticion.

    No lo saca de la operacion: si estaba asignado a los servicios de
    manana, la respuesta dice cuales quedan sin el.
    """
    resultado = accesos.desactivar(db, usuario_id, actor, datos.motivo)
    db.commit()
    return resultado


@router.post("/usuarios/{usuario_id}/reactivar",
             summary="Volverle a abrir la puerta")
def reactivar_usuario(usuario_id: int, datos: MotivoIn,
                      db: Session = Depends(get_db),
                      actor: m.Usuario = Depends(ADMINISTRA)):
    resultado = accesos.reactivar(db, usuario_id, actor, datos.motivo)
    db.commit()
    return resultado


@router.post("/usuarios/{usuario_id}/rol", summary="Cambiarle el puesto")
def cambiar_rol_usuario(usuario_id: int, datos: CambioRolIn,
                        db: Session = Depends(get_db),
                        actor: m.Usuario = Depends(ADMINISTRA)):
    """Del rol sale todo lo que esa persona puede tocar, asi que es la
    operacion mas delicada del sistema. Surte efecto en su siguiente
    peticion, sin cerrarle la sesion."""
    resultado = accesos.cambiar_rol(db, usuario_id, datos.rol, actor,
                                    datos.motivo)
    db.commit()
    return resultado


@router.get("/usuarios/{usuario_id}/historial",
            summary="Que se le ha hecho a ese acceso, y quien")
def historial_usuario(usuario_id: int, db: Session = Depends(get_db),
                      _: m.Usuario = Depends(ADMINISTRA)):
    return accesos.historial(db, usuario_id)


@router.post("/establecer-contrasena", summary="El empleado crea su contrasena")'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, PUERTAS)

# El alta tambien la puede hacer direccion general, y tambien se anota.
VIEJO = '''                 actor: m.Usuario = Depends(auth.requiere(m.Rol.ADMIN))):'''
NUEVO = '''                 actor: m.Usuario = Depends(ADMINISTRA)):'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    token, expira = auth.token_invitacion()
    db.add(m.Invitacion(usuario_id=usuario.id, token=token, expira_en=expira))
    db.commit()'''
NUEVO = '''    token, expira = auth.token_invitacion()
    db.add(m.Invitacion(usuario_id=usuario.id, token=token, expira_en=expira))
    accesos.anotar(db, actor, "acceso creado", "usuario", usuario.id,
                   despues=usuario.rol.value, detalle=usuario.correo)
    db.commit()'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

R.write_text(s)
print("routers/acceso.py: listar, desactivar, reactivar, cambiar rol e historial")

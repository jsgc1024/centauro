"""Paso 2b: el orden al usar el enlace, el candado de sesiones y las puertas."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- 1. el enlace se marca usado antes de anular los demas ----------
R = RAIZ / "backend/app/contrasenas.py"
s = R.read_text()
VIEJO = """    validar(nueva, usuario)
    _asentar(db, usuario, nueva)
    enlace.usado_en = datetime.now()"""
NUEVO = """    validar(nueva, usuario)
    # Se marca usado antes de asentar: `_asentar` anula los pendientes, y
    # si este todavia contara como pendiente quedaria usado y anulado a
    # la vez, que no es lo que paso.
    enlace.usado_en = datetime.now()
    _asentar(db, usuario, nueva)"""
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("contrasenas.py: el orden al usar el enlace")

# --- 2. el token viejo deja de valer --------------------------------
R = RAIZ / "backend/app/auth.py"
s = R.read_text()

VIEJO = '''    usuario = db.get(m.Usuario, int(carga["sub"]))
    return usuario if usuario and usuario.activo else None'''
NUEVO = '''    usuario = db.get(m.Usuario, int(carga["sub"]))
    if not usuario or not usuario.activo or _token_viejo(usuario, carga):
        return None
    return usuario'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    usuario = db.get(m.Usuario, int(carga["sub"]))
    if not usuario or not usuario.activo:
        raise sin_acceso
    return usuario'''
NUEVO = '''    usuario = db.get(m.Usuario, int(carga["sub"]))
    if not usuario or not usuario.activo:
        raise sin_acceso
    if _token_viejo(usuario, carga):
        raise HTTPException(401, "La contrasena cambio, vuelve a iniciar sesion")
    return usuario'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

ANCLA = '''def usuario_opcional(token: str | None = Depends(esquema),'''
CANDADO = '''def _token_viejo(usuario: m.Usuario, carga: dict) -> bool:
    """Si ese token se emitio antes del ultimo cambio de contrasena.

    El token no tiene estado: una vez firmado vale doce horas y no hay
    lista de sesiones que cancelar. Sin esta comparacion, cambiar la
    contrasena no le quitaba nada a quien ya tenia la sesion abierta, que
    es justo de quien uno se quiere deshacer al cambiarla.
    """
    desde = usuario.sesiones_desde
    if not desde:
        return False
    return float(carga.get("iat") or 0) < desde.timestamp()


def usuario_opcional(token: str | None = Depends(esquema),'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, CANDADO)
R.write_text(s)
print("auth.py: el token emitido antes del cambio deja de valer")

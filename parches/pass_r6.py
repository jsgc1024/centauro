"""El token dice a que hora se emitio, con fracciones.

El primer intento comparaba el `iat` --segundos enteros-- contra una hora
con fracciones, y se comia tokens recien emitidos. El segundo trunco los
dos lados y dejo una ventana ciega de hasta un segundo: un token emitido
en el mismo segundo del cambio sobrevivia.

La ventana se cierra sola si el token trae su propia hora exacta. `iat`
no sirve porque el estandar lo define en segundos enteros; una marca
nuestra al lado si.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/auth.py"
s = R.read_text()

VIEJO = '''        "iat": ahora,
        "exp": ahora + timedelta(hours=HORAS_SESION),
    }'''
NUEVO = '''        "iat": ahora,
        # La misma hora, con fracciones. `iat` va en segundos enteros por
        # estandar, y comparar segundos contra fracciones deja una
        # ventana de hasta un segundo en la que un token emitido justo
        # antes de cambiar la contrasena sobrevive al cambio.
        "emitido": ahora.timestamp(),
        "exp": ahora + timedelta(hours=HORAS_SESION),
    }'''
assert s.count(VIEJO) == 1, "no encontre la carga del token"
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    desde = usuario.sesiones_desde
    if not desde:
        return False
    # Los dos lados truncados al segundo. El `iat` que firma el token ya
    # viene en segundos enteros, asi que compararlo contra una hora con
    # fracciones rechazaba tokens recien emitidos: poner la contrasena a
    # las 10:00:00.7 y entrar a las 10:00:00.9 daba un token que decia
    # 10:00:00 y quedaba "antes" del cambio.
    #
    # El precio es una ventana de menos de un segundo en la que un token
    # emitido justo antes del cambio sobrevive. La sesion de la que uno
    # se quiere deshacer al cambiar la contrasena tiene minutos u horas,
    # no milisegundos.
    return int(carga.get("iat") or 0) < int(desde.timestamp())'''
NUEVO = '''    desde = usuario.sesiones_desde
    if not desde:
        return False

    emitido = carga.get("emitido")
    if emitido is not None:
        # Las dos horas exactas: sin ventana ciega.
        return float(emitido) < desde.timestamp()

    # Token de antes de que se firmara la hora exacta. Se comparan los
    # dos lados truncados al segundo, que es lo mas que se puede saber de
    # el. Estos se acaban solos cuando expiran, a las doce horas.
    return int(carga.get("iat") or 0) < int(desde.timestamp())'''
assert s.count(VIEJO) == 1, "no encontre la comparacion"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("auth.py: el token trae su hora exacta")

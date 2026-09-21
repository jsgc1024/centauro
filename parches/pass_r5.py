"""Dos arreglos.

1. El candado de sesiones comparaba un segundo entero contra uno con
   fracciones, y se comia tokens legitimos: poner la contrasena a las
   10:00:00.7 y entrar a las 10:00:00.9 daba un token que decia
   10:00:00 --menor-- y el sistema lo tomaba por viejo. En produccion
   eso es "crea tu contrasena, entra, te saca, en bucle".

2. La prueba buscaba la palabra "enlace" para ver si se filtraba el
   enlace, y esa palabra esta en el mensaje generico. Lo que importa es
   que no vaya la direccion.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

R = RAIZ / "backend/app/auth.py"
s = R.read_text()
VIEJO = '''    desde = usuario.sesiones_desde
    if not desde:
        return False
    return float(carga.get("iat") or 0) < desde.timestamp()'''
NUEVO = '''    desde = usuario.sesiones_desde
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
assert s.count(VIEJO) == 1, "no encontre la comparacion"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("auth.py: los dos lados truncados al segundo")

R = RAIZ / "backend/tests/test_contrasenas.py"
s = R.read_text()
VIEJO = '''    # Y el enlace no viaja en la respuesta: esta puerta es publica.
    assert "enlace" not in real.text and "token" not in real.text'''
NUEVO = '''    # Y el enlace no viaja en la respuesta: esta puerta es publica.
    # Se busca la direccion y no la palabra "enlace", que sale en el
    # mensaje generico.
    assert "crear-contrasena" not in real.text
    assert "https://" not in real.text'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# Y que la prueba de la contrasena actual pase por su propia razon.
VIEJO = '''    r = cliente.post("/auth/mi-contrasena", headers=suyo,
                     json={"actual": "la que sea", "nueva": "camino largo"})
    assert r.status_code == 401, r.text
    assert _entrar(cliente, cuenta).status_code == 200'''
NUEVO = '''    r = cliente.post("/auth/mi-contrasena", headers=suyo,
                     json={"actual": "la que sea", "nueva": "camino largo"})
    assert r.status_code == 401, r.text
    # Que falle por la contrasena y no por la sesion: esta prueba llego a
    # pasar por accidente cuando el candado de sesiones se comia tokens
    # buenos, y decia que si a algo que no habia verificado.
    assert "actual" in r.text
    assert _entrar(cliente, cuenta).status_code == 200'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("test_contrasenas.py: la prueba mira lo que debe")

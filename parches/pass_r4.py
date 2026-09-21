"""El contador de la recuperacion es suyo, no el del login.

Con el mismo contador, ocho peticiones al endpoint publico con el correo
de alguien lo dejaban sin poder entrar quince minutos. El limite sigue
--pedir enlaces sin fin tampoco--, pero en su propio carril.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/routers/acceso.py"
s = R.read_text()

VIEJO = '''    ip = peticion.client.host if peticion.client else None
    intentos.revisar(datos.correo, ip)
    intentos.fallo(datos.correo, ip)   # cuenta como intento, exista o no
    resultado = contrasenas.pedir_recuperacion(db, datos.correo)'''
NUEVO = '''    ip = peticion.client.host if peticion.client else None
    # En su propio carril, no en el del inicio de sesion: con el mismo
    # contador, ocho peticiones aqui con un correo ajeno dejaban a esa
    # persona sin poder entrar quince minutos. El limite sigue --pedir
    # enlaces sin fin tampoco-- pero solo frena la recuperacion.
    carril = f"recuperar:{datos.correo}"
    intentos.revisar(carril, ip)
    intentos.fallo(carril, ip)
    resultado = contrasenas.pedir_recuperacion(db, datos.correo)'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("routers/acceso.py: la recuperacion tiene su propio contador")

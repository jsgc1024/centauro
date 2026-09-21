"""Paso 5d: revisar.py cuida las actividades.

Una actividad mal escrita no revienta: `permisos.roles_de` devuelve un
conjunto vacio y esa puerta se cierra para todos menos el administrador.
Nada avisa. Es el tipo de error que se descubre el dia que alguien no
puede trabajar.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/revisar.py"
s = R.read_text()

ANCLA = """# ==================================================================
# 5 · Migraciones: una sola cadena, una sola cabeza
# =================================================================="""

NUEVA = '''# ==================================================================
# 4 bis · Actividades: la que no existe no la puede nadie
# ==================================================================

def revisar_actividades() -> None:
    """Toda actividad que pide un endpoint tiene que estar declarada.

    `permisos.roles_de` devuelve un conjunto vacio para una actividad que
    no conoce, y `auth.puede` lo traduce a "nadie salvo el administrador".
    Asi que una letra de mas cierra una puerta para toda la empresa y no
    revienta nada: se descubre el dia que alguien no puede trabajar.

    Se revisan dos cosas. La primera es el caso comun: `puede("x")` con
    la cadena a la vista. La segunda es el que se escapa --las
    actividades que viajan dentro de una tabla, como las de `crud_router`
    en catalogos.py-- y para eso se mira cualquier texto que empiece con
    un prefijo ya declarado: si alguien escribe "viaticos.asigner", ese
    prefijo existe y el nombre completo no.
    """
    permisos = os.path.join(RAIZ, "app/permisos.py")
    if not os.path.exists(permisos):
        return
    fuente = io.open(permisos, encoding="utf-8").read()
    declaradas = set(re.findall(r'^\\s{4}"([a-z][\\w.]*)":\\s*\\{', fuente, re.M))
    if not declaradas:
        return
    prefijos = {a.split(".")[0] for a in declaradas}

    for archivo in archivos("app", ".py"):
        if archivo == permisos:
            continue
        texto = io.open(archivo, encoding="utf-8").read()
        for numero, linea in enumerate(texto.split("\\n"), 1):
            for actividad in re.findall(r'puede\\(\\s*["\\\']([\\w.]+)["\\\']', linea):
                if actividad not in declaradas:
                    apuntar(archivo, numero,
                            f"pide la actividad '{actividad}' y no esta "
                            "declarada en permisos.py: nadie podria hacerla")
            for suelta in re.findall(r'["\\\']([a-z_]+\\.[a-z_]+)["\\\']', linea):
                if suelta.split(".")[0] in prefijos and suelta not in declaradas:
                    apuntar(archivo, numero,
                            f"'{suelta}' parece una actividad y no esta "
                            "declarada en permisos.py")


# ==================================================================
# 5 · Migraciones: una sola cadena, una sola cabeza
# =================================================================='''

assert s.count(ANCLA) == 1, "no encontre el separador de migraciones"
s = s.replace(ANCLA, NUEVA)

VIEJO = """    revisar_idioma()
    revisar_migraciones()"""
NUEVO = """    revisar_idioma()
    revisar_actividades()
    revisar_migraciones()"""
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("revisar.py: sexta revision, las actividades")

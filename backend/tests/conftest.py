"""Base de pruebas.

Corre contra una base propia (centauro_test), separada de la de desarrollo.
Los catalogos se siembran una sola vez; las tablas de operacion se vacian
antes de cada prueba, para que ninguna dependa de lo que dejo la anterior.
"""
import os

# Antes que cualquier otra cosa: la direccion de la base de pruebas.
#
# La configuracion se arma una sola vez, al importar app.config, y de ahi
# sale el motor. Si esto se hiciera adentro de una fixture, cualquier
# prueba que importe algo de app al cargarse —y hay varias— ya habria
# dejado la configuracion apuntando a la base de desarrollo, y la bateria
# entera correria contra los servicios de verdad, borrandolos antes de
# cada prueba. Aqui arriba se hace antes de que se importe nada.
BASE_DE_PRUEBAS = "postgresql+psycopg://centauro:centauro_dev@db:5432/centauro_test"
os.environ["DATABASE_URL"] = BASE_DE_PRUEBAS

# Ni una prueba sale a Pegasus (seccion 60). Desde que se encendio la
# lectura, el contenedor trae en su entorno el usuario de verdad, y una
# prueba que llamo a la lectura sin su Pegasus de mentiras leyo el GPS
# real --97 unidades, a la base de pruebas--. Las que necesitan un
# Pegasus lo arman ellas; aqui se deja la conexion sin usuario.
for _variable in ("PEGASUS_SITIO", "PEGASUS_USUARIO", "PEGASUS_CLAVE",
                  "PEGASUS_SECRETO_AVISO"):
    os.environ[_variable] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

# Las tablas que guardan movimiento. Los catalogos no se tocan.
TABLAS_DE_OPERACION = [
    # Configuracion que las pruebas cambian: los pesos del tablero y los
    # castigos por incidencia. Se vacian como el movimiento, para que cada
    # prueba arranque de los valores por omision y no de lo que dejo otra.
    "peso_profesionalismo", "parametro_profesionalismo",
    "ajuste_comision", "comision_consultor", "resultado_criterio",
    "evaluacion_mensual", "incidencia", "reemplazo", "contrato_implantado",
    "desviacion", "cierre", "linea_cotizacion", "cotizacion",
    "registro_accion", "registro_admin", "notificacion", "alerta", "hito",
    # El telefono suscrito a los avisos es movimiento, no catalogo: lo
    # da de alta el propio agente desde su app. Faltaba aqui, asi que
    # las suscripciones se acumulaban de una prueba a la siguiente y la
    # misma persona terminaba con tres telefonos.
    "suscripcion_push",
    # Los certificados tampoco son catalogo: los manda Odoo, y cada
    # prueba que los siembra se los dejaba puestos a la siguiente. La
    # que revisa el padron vacio los encontraba llenos.
    "capacitacion",
    # Cada lectura de Odoo deja su renglon, y la tarea de cada hora espera
    # a que exista uno hecho a mano: sin vaciarlo, la prueba que revisa
    # esa espera encontraria el de la prueba anterior.
    "sincronizacion_odoo",
    "reemplazo_recurso", "alerta_incidencia",
    "concepto_nomina", "renglon_nomina", "ajuste_nomina", "nomina_semanal",
    "respuesta_encuesta", "encuesta",
    "solicitud_transferencia", "devolucion_viatico",
    "comprobante", "concepto_asignado",
    "asignacion_viatico", "asignacion_vehiculo", "asignacion_personal",
    "jornada", "equipo", "servicio", "solicitante",
    "task_sheet", "agenda_jornada", "parada_agenda", "hospedaje",
    # La flota se vacia con el movimiento porque el auto subarrendado
    # vive en la misma tabla y apunta a su servicio: al vaciar servicio,
    # Postgres se lleva vehiculo por el CASCADE, quiera uno o no. Se
    # vuelve a sembrar despues de cada vaciado.
    "vehiculo",
    # Lo que se leyo de Pegasus (seccion 60): cada prueba arma su propio
    # Pegasus de mentiras y no puede heredar las unidades de otra.
    "unidad_gps", "grupo_gps",
]


def _crear_base_de_pruebas():
    """Rehace centauro_test desde cero.

    Se borra y se vuelve a crear en cada corrida: si solo se crearan las
    tablas faltantes, una columna nueva no llegaria a las tablas que ya
    existen y las pruebas fallarian por un desfase que no es real.
    """
    import psycopg

    url = "postgresql://centauro:centauro_dev@db:5432/postgres"
    with psycopg.connect(url, autocommit=True) as con:
        con.execute("DROP DATABASE IF EXISTS centauro_test WITH (FORCE)")
        con.execute("CREATE DATABASE centauro_test")


@pytest.fixture(scope="session", autouse=True)
def base_de_pruebas():
    _crear_base_de_pruebas()

    from app.db import Base, engine

    # Candado: si por lo que sea el motor no quedo en centauro_test, la
    # bateria se detiene aqui. Lo siguiente que hace es vaciar tablas, y
    # eso en la base de desarrollo se lleva los servicios del dia.
    if engine.url.database != "centauro_test":
        raise RuntimeError(
            f"Las pruebas apuntan a '{engine.url.database}' y no a "
            "centauro_test. No se corre nada: vaciarian la base de "
            "desarrollo.")
    from app import models  # noqa: F401
    from app.seed import (sembrar, sembrar_accesos, sembrar_bonos,
                          sembrar_festivos, sembrar_lugares,
                          sembrar_parametros, sembrar_recursos)

    Base.metadata.create_all(bind=engine)
    sembrar()
    sembrar_recursos()
    sembrar_parametros()
    sembrar_accesos()
    sembrar_festivos()
    sembrar_bonos()
    sembrar_lugares()
    yield engine


@pytest.fixture(autouse=True)
def base_limpia(base_de_pruebas):
    """Vacia el movimiento antes de cada prueba."""
    from app.seed import sembrar_recursos

    with base_de_pruebas.begin() as con:
        con.execute(text(
            f"TRUNCATE {', '.join(TABLAS_DE_OPERACION)} RESTART IDENTITY CASCADE"))
    # La flota se fue con el vaciado y no es movimiento: es el catalogo
    # con el que trabaja casi toda la bateria. Se vuelve a poner desde la
    # misma semilla, para que no haya dos versiones de la verdad.
    sembrar_recursos()
    yield


@pytest.fixture
def cliente():
    from app.main import app
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- sesiones

CUENTAS = {
    "admin": "admin@centauro.lat",
    "consultor": "ana.solis@centauro.lat",
    "consultor2": "beatriz.roman@centauro.lat",
    "central": "central@centauro.lat",
    "finanzas": "finanzas@centauro.lat",
    "rrhh": "rrhh@centauro.lat",
    "diroperaciones": "operaciones@centauro.lat",
    "dirgeneral": "direccion@centauro.lat",
    "juan": "juan.ramirez@centauro.lat",
    "luis": "luis.mendoza@centauro.lat",
    "carlos": "carlos.vega@centauro.lat",
}


@pytest.fixture
def sesion(cliente):
    """sesion('consultor') devuelve las cabeceras con su token."""
    cache = {}

    def entrar(quien: str) -> dict:
        if quien not in cache:
            correo = CUENTAS[quien]
            r = cliente.post("/auth/token",
                             data={"username": correo, "password": "centauro2026"})
            assert r.status_code == 200, f"No se pudo entrar como {quien}: {r.text}"
            cache[quien] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return cache[quien]

    return entrar


# ---------------------------------------------------------------- catalogos

@pytest.fixture
def datos(cliente, sesion):
    """Referencias de catalogo que casi toda prueba necesita."""
    h = sesion("admin")

    def traer(ruta):
        r = cliente.get(ruta, headers=h)
        assert r.status_code == 200, f"{ruta}: {r.text}"
        return r.json()

    paises = traer("/catalogos/paises")
    mx = next(p for p in paises if p["codigo"] == "MX")
    mods = {x["codigo"]: x for x in traer("/catalogos/modalidades")
            if x["pais_id"] == mx["id"]}
    perfiles = {p["codigo"]: p for p in traer("/catalogos/perfiles")}
    categorias = {c["codigo"]: c for c in traer("/catalogos/categorias-vehiculo")}
    plazas = {p["nombre"]: p for p in traer("/catalogos/plazas")}
    personal = {p["nombre"]: p for p in traer("/catalogos/personal")}
    vehiculos = traer("/catalogos/vehiculos")

    return {
        "mx": mx,
        "cdmx": plazas["Ciudad de Mexico"],
        "gdl": plazas["Guadalajara"],
        "modalidades": mods,
        "perfiles": perfiles,
        "categorias": categorias,
        "personal": personal,
        "vehiculos": vehiculos,
        "cliente_id": traer("/catalogos/clientes")[0]["id"],
        "suburban": next(v for v in vehiculos
                         if v["categoria_id"] == categorias["suv_blindada"]["id"]),
        # Con todos=true: la lista normal esconde los que llevan tres
        # meses sin ocuparse, y los de la semilla nunca se han ocupado.
        "hoteles": traer("/catalogos/hoteles?todos=true"),
    }

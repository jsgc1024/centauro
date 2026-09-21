"""Lo que el sistema publica sin que nadie haya entrado.

Dos puertas tiene una aplicacion antes de pedir sesion: la que arranca
--si arranca con la clave de demo, cualquiera que lea el codigo se firma
una sesion de director general-- y la que ensena el mapa: `/docs`,
`/redoc` y `/openapi.json`, que son el plano completo del sistema, con
el formulario para probar cada endpoint al lado.

El mapa no ensena datos; todo lo de adentro sigue pidiendo sesion. Lo
que regala es el trabajo de adivinar por donde buscarle la vuelta. En
desarrollo vale su peso en oro; en produccion, quien lo necesite que lo
levante en su maquina.
"""
import pytest

from app.config import (CLAVE_DE_DEMO, Settings, es_desarrollo,
                        puertas_de_la_api, revisar_secretos)


def _con(entorno):
    s = Settings()
    s.app_env = entorno
    return s


def test_un_entorno_que_nadie_reconoce_se_trata_como_produccion():
    """Se enumera lo que SI es desarrollo, no lo que no.

    Al reves --"si dice produccion, cierra"-- un `APP_ENV=prod`, un
    `staging` o un renglon vacio en el `.env` dejarian la puerta
    abierta. Una puerta que se abre sola cuando no entiende el nombre
    del entorno es una puerta abierta.
    """
    for adentro in ("local", "Pruebas", " ci ", "desarrollo"):
        assert es_desarrollo(_con(adentro)), adentro
    for afuera in ("produccion", "prod", "staging", "", "   ", None):
        assert not es_desarrollo(_con(afuera)), afuera


def test_el_mapa_de_la_api_no_se_publica_fuera_de_desarrollo():
    for llave, ruta in (("docs_url", "/docs"), ("redoc_url", "/redoc"),
                        ("openapi_url", "/openapi.json")):
        assert puertas_de_la_api(_con("local"))[llave] == ruta
        assert puertas_de_la_api(_con("produccion"))[llave] is None


def test_la_aplicacion_de_verdad_usa_esa_decision():
    """Que no se quede en una funcion que nadie llama.

    Es el mismo error que esta bitacora tiene contado dos veces: el
    umbral escrito lejos de su candado, el tope del mes escrito lejos de
    donde se aplica. La regla y el lugar donde muerde tienen que ser el
    mismo.
    """
    from app.config import settings
    from app.main import app

    esperado = puertas_de_la_api(settings)
    assert app.docs_url == esperado["docs_url"]
    assert app.redoc_url == esperado["redoc_url"]
    assert app.openapi_url == esperado["openapi_url"]
    # Y la bateria corre en un entorno de desarrollo, asi que aqui esta
    # abierto: si esto cambiara, el `.env` de pruebas se movio.
    assert app.docs_url == "/docs"


def test_con_la_clave_de_demo_no_arranca_fuera_de_desarrollo():
    s = _con("produccion")
    s.secret_key = CLAVE_DE_DEMO
    with pytest.raises(RuntimeError) as falla:
        revisar_secretos(s)
    assert "SECRET_KEY" in str(falla.value)

    # En la maquina de quien desarrolla, la de demo se acepta: lo que no
    # se vale es llevarsela a un servidor.
    revisar_secretos(_con("local"))


# ================================================== el recorrido

def test_el_recorrido_se_ofrece_una_vez_y_por_persona(cliente, sesion):
    """La tercera capa de la ayuda: la que solo hace falta la primera vez.

    Va marcada en el usuario y no en el navegador. Por navegador es
    gratis y esta mal de dos maneras: quien ya lo vio lo vuelve a ver al
    cambiar de computadora, y quien nunca lo vio no lo ve si entra desde
    una que ya lo mostro.

    Y se marca al abrirlo, no al terminarlo: el que lo salta en el
    primer paso tambien lo vio. Un recorrido que no se deja cerrar se
    aprende a odiar.
    """
    h = sesion("consultor")
    yo = cliente.get("/auth/yo", headers=h).json()
    assert yo["recorrido_pendiente"] is True

    r = cliente.post("/auth/recorrido-visto", headers=h, json={})
    assert r.status_code == 200, r.text
    assert cliente.get("/auth/yo",
                       headers=h).json()["recorrido_pendiente"] is False

    # Y a otra persona le sigue tocando: es de cada quien.
    otro = cliente.get("/auth/yo", headers=sesion("finanzas")).json()
    assert otro["recorrido_pendiente"] is True

    # Marcarlo dos veces no revienta ni mueve la fecha.
    assert cliente.post("/auth/recorrido-visto", headers=h,
                        json={}).status_code == 200

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


def test_la_consola_se_abre_tambien_en_consola_con_diagonal():
    """Los avisos al telefono del consultor llevan /consola/#/servicio/...
    y la app de campo manda a /consola/ a quien entra con una cuenta que
    no es de campo. Antes de la seccion 71, /consola/ contestaba 404: el
    montaje no servia el index de la carpeta."""
    from fastapi.testclient import TestClient
    from app.main import app

    cliente = TestClient(app)
    raiz = cliente.get("/")
    con_diagonal = cliente.get("/consola/")
    assert raiz.status_code == 200 and con_diagonal.status_code == 200
    assert con_diagonal.text == raiz.text
    assert "<title>Centauro Connect</title>" in con_diagonal.text
    assert con_diagonal.headers["cache-control"] == "no-store"
    # Lo demas de la carpeta se sigue sirviendo igual.
    assert cliente.get("/consola/app.js").status_code == 200
    assert cliente.get("/consola/no-existe.js").status_code == 404


def test_la_consola_y_la_app_traen_el_escudo_de_centauro():
    """Seccion 72: el icono sale del escudo que mando Salvador. El de antes
    salio de una imagen chica y en el telefono se veia borroso; la consola
    no tenia ninguno y la pestana ensenaba el globo del navegador.

    Cada tamano se revisa contra lo que dice ser: un icono que dice 512 y
    mide 180 el telefono lo estira, que es justo como se veia borroso. El
    de iPhone va sin transparencia: iOS pinta de negro lo transparente.
    El tamano y el tipo se leen de la cabecera del PNG (IHDR), sin
    librerias de imagen: el servidor no las trae."""
    import json
    import struct

    from fastapi.testclient import TestClient

    from app.main import app

    cliente = TestClient(app)

    def png(ruta):
        """(ancho, alto, tipo de color) de la cabecera: 2 es RGB, 6 RGBA."""
        r = cliente.get(ruta)
        assert r.status_code == 200, ruta
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n", ruta
        assert r.content[12:16] == b"IHDR", ruta
        ancho, alto = struct.unpack(">II", r.content[16:24])
        return ancho, alto, r.content[25]

    consola = cliente.get("/").text
    for ruta, lado in (("/consola/icono-32.png", 32), ("/consola/icono-192.png", 192),
                       ("/consola/icono-apple-180.png", 180)):
        assert f'href="{ruta}"' in consola, ruta
        assert png(ruta)[:2] == (lado, lado), ruta

    app_campo = cliente.get("/app/").text
    for ruta, lado in (("/app/icono-32.png", 32), ("/app/icono-192.png", 192),
                       ("/app/icono-apple-180.png", 180)):
        assert f'href="{ruta}"' in app_campo, ruta
        assert png(ruta)[:2] == (lado, lado), ruta

    # Y el nombre debajo del icono: EP Connect, no Centauro (decision de
    # Salvador, 26 sep). iOS lo lee de la pagina; Android, del manifiesto.
    assert '<meta name="apple-mobile-web-app-title" content="EP Connect">' in app_campo
    manifiesto = json.loads(cliente.get("/app/manifiesto.json").text)
    assert manifiesto["short_name"] == manifiesto["name"] == "EP Connect"
    for icono in manifiesto["icons"]:
        lado = int(icono["sizes"].split("x")[0])
        assert png(icono["src"])[:2] == (lado, lado), icono["src"]

    for ruta in ("/consola/icono-apple-180.png", "/app/icono-apple-180.png"):
        assert png(ruta)[2] == 2, ruta

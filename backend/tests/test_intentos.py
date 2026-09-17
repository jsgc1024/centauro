"""El limite de intentos del login.

Sin el, `POST /auth/token` acepta intentos sin fin: una lista de correos
y un diccionario bastan para entrar, y en la bitacora de accesos no
queda nada raro, porque cada intento es una peticion normal.

Dos cosas se verifican aqui, y la segunda importa tanto como la primera:
que el candado cierre, y que **no se cierre de mas**. Un limite que deja
fuera a quien se equivoco dos veces y luego le atino es un limite que
alguien va a querer apagar.
"""
import pytest

from app import intentos

CORREO = "nadie.existe@centauro.lat"


@pytest.fixture(autouse=True)
def limpio():
    """Los contadores viven en Redis y no se van con el vaciado de la
    base: sin esto, correr la bateria dos veces seguidas fallaria la
    segunda."""
    intentos.limpiar(CORREO, "testclient")
    intentos.limpiar("juan.ramirez@centauro.lat", "testclient")
    yield
    intentos.limpiar(CORREO, "testclient")
    intentos.limpiar("juan.ramirez@centauro.lat", "testclient")


def _intentar(cliente, correo=CORREO, contrasena="loquesea"):
    return cliente.post("/auth/token",
                        data={"username": correo, "password": contrasena})


def test_al_octavo_intento_se_cierra(cliente, datos):
    """Ocho fallos seguidos no los hace quien se equivoco de contrasena:
    los hace un programa."""
    for _ in range(intentos.MAXIMO):
        assert _intentar(cliente).status_code == 401

    r = _intentar(cliente)
    assert r.status_code == 429, r.text
    assert "minuto" in r.text.lower(), "tiene que decir cuanto esperar"


def test_no_dice_si_la_cuenta_existe(cliente, datos):
    """El mismo mensaje exista o no el correo. Decir "ese correo no
    existe" regala la mitad del trabajo a quien esta probando."""
    inexistente = _intentar(cliente)
    real = _intentar(cliente, "juan.ramirez@centauro.lat", "la que no es")
    assert inexistente.status_code == real.status_code == 401
    assert inexistente.json()["detail"] == real.json()["detail"]


def test_quien_le_atina_no_arrastra_los_fallos(cliente, datos):
    """Se equivoco tres veces y a la cuarta entro. No puede quedar a un
    fallo de que lo dejen fuera el resto de la tarde."""
    correo = "juan.ramirez@centauro.lat"
    for _ in range(3):
        assert _intentar(cliente, correo, "la que no es").status_code == 401

    bien = _intentar(cliente, correo, "centauro2026")
    assert bien.status_code == 200, bien.text

    # El contador se borro: vuelve a tener sus ocho.
    for _ in range(intentos.MAXIMO):
        assert _intentar(cliente, correo, "la que no es").status_code == 401


def test_sin_redis_se_abre_y_no_se_cierra(cliente, datos, monkeypatch):
    """Un candado que depende de un servicio que puede caerse dejaria a
    toda la operacion sin entrar justo el dia malo. Que se pueda
    intentar de mas un rato es peor que nadie pueda trabajar."""
    monkeypatch.setattr(intentos, "_redis", lambda: None)
    for _ in range(intentos.MAXIMO + 5):
        assert _intentar(cliente).status_code == 401

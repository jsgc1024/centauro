"""La busqueda del punto de encuentro en Google.

Aqui no se llama a Google: se verifica quien puede pedirlo y que el
sistema diga con claridad cuando falta la llave, que es el error que se
va a ver el dia que alguien despliegue sin configurarla.
"""
from app import mapas


def test_sin_llave_lo_dice_con_todas_sus_letras(cliente, sesion, monkeypatch):
    monkeypatch.setattr(mapas.settings, "google_maps_key", "")
    r = cliente.get("/mapas/lugares?texto=Aeropuerto Benito Juarez",
                    headers=sesion("consultor"))
    assert r.status_code == 503
    assert "GOOGLE_MAPS_KEY" in r.json()["detail"]["mensaje"]


def test_el_personal_de_seguridad_no_busca_lugares(cliente, sesion):
    r = cliente.get("/mapas/lugares?texto=hotel", headers=sesion("juan"))
    assert r.status_code == 403
    assert r.json()["detail"]["actividad"] == "mapas.buscar"


def test_un_texto_muy_corto_no_gasta_una_busqueda(cliente, sesion, monkeypatch):
    """Cada busqueda se cobra: dos letras no salen del sistema."""
    llamadas = []
    monkeypatch.setattr(mapas.settings, "google_maps_key", "llave-de-prueba")
    monkeypatch.setattr(mapas.httpx, "post",
                        lambda *a, **k: llamadas.append(a) or None)

    r = cliente.get("/mapas/lugares?texto=ae", headers=sesion("consultor"))
    assert r.status_code == 200
    assert r.json()["lugares"] == []
    assert llamadas == []


def test_el_enlace_prefiere_el_pin_sobre_el_texto(cliente=None):
    """Una direccion escrita se interpreta de dos formas; un pin no."""
    con_pin = mapas.enlace("Las Alcobas, Polanco", 19.4326, -99.1962)
    assert "19.4326%2C-99.1962" in con_pin

    sin_pin = mapas.enlace("Las Alcobas, Polanco")
    assert "Las%20Alcobas" in sin_pin
    assert mapas.enlace(None) is None

"""La senal con la que el principal reconoce al equipo, en el telefono.

Ya existia en el servicio y en el task sheet. Pedido de Salvador, 22 sep:
que el equipo la levante desde su telefono, a pantalla completa, a la
hora del arribo.
"""
import base64

from ayudas import PIXEL
from test_campo import _servicio_de_juan

PNG = "data:image/png;base64," + base64.b64encode(PIXEL).decode()


def _con_senal(cliente, sesion, datos, **senal):
    servicio, j = _servicio_de_juan(cliente, sesion, datos, dia=0)
    r = cliente.put(f"/servicios/{servicio['id']}/senal", json=senal,
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return servicio, j


def _ficha(cliente, sesion, servicio):
    dia = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    return next(f for f in dia["hoy"] if f["servicio_id"] == servicio["id"])


def test_la_ficha_dice_que_hay_senal_sin_cargar_la_imagen(cliente, sesion,
                                                          datos):
    """La ficha se guarda en el telefono: trae el texto, la nota y si hay
    imagen, pero la imagen no. Esa se baja aparte."""
    servicio, _ = _con_senal(cliente, sesion, datos, texto="CARTER",
                             imagen=PNG, nota="A la salida del filtro")
    f = _ficha(cliente, sesion, servicio)
    assert f["senal"] == {"texto": "CARTER", "nota": "A la salida del filtro",
                          "imagen": True, "color": None}
    assert "base64" not in str(f), "la imagen viajo dentro de la ficha"


def test_sin_senal_la_ficha_no_inventa_una(cliente, sesion, datos):
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    assert _ficha(cliente, sesion, servicio)["senal"] is None


def test_la_imagen_baja_como_imagen_y_solo_para_quien_va(cliente, sesion,
                                                         datos):
    """Como imagen de verdad, para que el telefono la guarde. Y solo a
    quien va en ese servicio: en manos de otro, la senal es una forma de
    hacerse pasar por el equipo."""
    servicio, _ = _con_senal(cliente, sesion, datos, imagen=PNG)
    ruta = f"/campo/servicios/{servicio['id']}/senal/imagen"

    r = cliente.get(ruta, headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png"), r.headers
    assert r.content == PIXEL

    r = cliente.get(ruta, headers=sesion("luis"))
    assert r.status_code == 403, r.text


def test_si_la_senal_es_solo_una_palabra_no_hay_imagen_que_bajar(cliente,
                                                                 sesion, datos):
    servicio, _ = _con_senal(cliente, sesion, datos, texto="CARTER")
    f = _ficha(cliente, sesion, servicio)
    assert f["senal"]["imagen"] is False
    r = cliente.get(f"/campo/servicios/{servicio['id']}/senal/imagen",
                    headers=sesion("juan"))
    assert r.status_code == 404, r.text

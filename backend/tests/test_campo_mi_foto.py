"""Su foto en la app, junto a su puesto.

Caso de Alberto Arredondo, 28 sep: "no se ve la foto del conductor en la
app". La tarjeta del dia decia su puesto y no su cara; la consola si la
ensena. La foto baja aparte, como imagen, igual que la senal: `mi-dia`
se consulta seguido y se guarda en el telefono.
"""
import base64

from ayudas import PIXEL

PNG = "data:image/png;base64," + base64.b64encode(PIXEL).decode()


def _poner_foto(datos, quien, foto):
    from app import models as m
    from app.db import SessionLocal

    with SessionLocal() as db:
        persona = db.get(m.Persona, datos["personal"][quien]["id"])
        persona.foto_url = foto
        db.commit()


def test_su_foto_baja_como_imagen(cliente, sesion, datos):
    _poner_foto(datos, "Juan Ramirez", PNG)
    r = cliente.get("/campo/mi-foto", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png"), r.headers
    assert r.content == PIXEL


def test_cada_quien_baja_la_suya(cliente, sesion, datos):
    """La ruta no recibe a quien: es siempre la de la sesion."""
    _poner_foto(datos, "Juan Ramirez", PNG)
    r = cliente.get("/campo/mi-foto", headers=sesion("luis"))
    assert r.status_code == 404, r.text


def test_sin_foto_no_hay_nada_que_bajar(cliente, sesion, datos):
    _poner_foto(datos, "Juan Ramirez", None)
    r = cliente.get("/campo/mi-foto", headers=sesion("juan"))
    assert r.status_code == 404, r.text


def test_la_foto_no_viaja_en_el_dia(cliente, sesion, datos):
    """El dia se guarda en el telefono y se pide seguido: la foto no va
    adentro."""
    _poner_foto(datos, "Juan Ramirez", PNG)
    dia = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    assert "base64" not in str(dia)


def test_solo_la_app_de_campo(cliente, sesion, datos):
    r = cliente.get("/campo/mi-foto", headers=sesion("consultor"))
    assert r.status_code == 403, r.text

"""Los hospitales de la hoja.

De aqui sale la referencia medica en una emergencia: los tres mas
cercanos al punto del servicio, dentro de su ciudad, y nunca sin un
tercer nivel. Google llena los datos; el nivel lo marca Centauro.
"""

from tests.test_mes_siguiente import _alta


def test_la_hoja_toma_los_de_la_ciudad_del_servicio(cliente, sesion, datos):
    alta, h = _alta(cliente, sesion, datos)
    r = cliente.get(f"/implantados/{alta['servicio_id']}/hospitales", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["plaza_id"] == datos["cdmx"]["id"]


def test_monterrey_y_guadalajara_ya_estan_cargados(cliente, sesion, datos):
    """Mientras Google no llene el catalogo, las tres ciudades donde se
    opera tienen que traer los principales."""
    h = sesion("admin")
    todos = cliente.get("/catalogos/hospitales", headers=h).json()
    por_ciudad = {}
    for hospital in todos:
        por_ciudad.setdefault(hospital["plaza_id"], []).append(hospital)

    plazas = {p["nombre"]: p["id"] for p in
              cliente.get("/catalogos/plazas", headers=h).json()}
    for ciudad in ("Ciudad de Mexico", "Monterrey", "Guadalajara"):
        suyos = por_ciudad.get(plazas[ciudad], [])
        assert len(suyos) >= 3, f"{ciudad} tiene {len(suyos)} hospitales"
        assert any(x["nivel_atencion"] == "tercer_nivel" for x in suyos), \
            f"{ciudad} no tiene un tercer nivel"


def test_el_nivel_no_se_adivina(cliente, sesion, datos):
    """Google no sabe hasta donde llega un hospital, asi que se puede dar
    de alta sin nivel. Lo que no pasa es que el sistema se lo invente: sin
    nivel no cuenta como tercer nivel para la regla de la hoja."""
    from app import tasksheet
    from app.db import SessionLocal

    h = sesion("admin")
    plazas = {p["nombre"]: p["id"] for p in
              cliente.get("/catalogos/plazas", headers=h).json()}
    # En una ciudad sin hospitales cargados, para no moverle la
    # referencia medica a ningun servicio de las tres donde se opera.
    queretaro = plazas["Queretaro"]

    r = cliente.post("/catalogos/hospitales", json={
        "pais_id": datos["mx"]["id"], "plaza_id": queretaro,
        "nombre": "Clinica sin nivel", "lat": "20.5888", "lon": "-100.3899",
    }, headers=h)
    assert r.status_code in (200, 201), r.text
    assert r.json()["nivel_atencion"] is None

    db = SessionLocal()
    try:
        cerca = tasksheet.hospitales_cercanos(db, queretaro, 20.5888, -100.3899)
        assert [x["nivel"] for x in cerca] == [None], cerca
    finally:
        db.close()

    # Se recoge lo que se ensucio: el catalogo no se vacia entre pruebas
    # —no es movimiento— y dejar una clinica suelta en Queretaro le
    # cambia la referencia medica a la prueba de al lado.
    cliente.delete(f"/catalogos/hospitales/{r.json()['id']}", headers=h)

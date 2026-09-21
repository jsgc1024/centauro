"""Las pruebas de lo que la tarjeta lee y de la vista previa del regreso."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/tests/test_relevo.py"
s = R.read_text()

ANCLA = "# ================================================== la raya con implantado"
NUEVO = '''def test_la_vista_previa_del_regreso_no_guarda_nada(cliente, sesion, datos):
    """Lo mismo que con el cambio: se ejecuta de verdad y se deshace.

    El regreso no es solo un nombre: puede partir un dia y mueve dinero
    de los dos lados. El consultor tiene que poder verlo antes.
    """
    servicio = _montado(cliente, sesion, datos, offset=680, dias=4)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()

    r = cliente.post(
        f"/contingencia/reemplazos/{hecho['reemplazo_id']}/regreso/vista-previa",
        headers=h, json={"desde": dias[3]["fecha"]})
    assert r.status_code == 200, r.text
    previa = r.json()
    assert previa["hasta"] == dias[2]["fecha"]
    assert previa["jornadas_devueltas"] == [dias[3]["fecha"]]

    # No guardo nada: el dia 3 sigue siendo de Luis y el movimiento sigue
    # abierto.
    assert _asignados(cliente, sesion, dias[3]["id"]) == ["Luis Mendoza"]
    historial = cliente.get(
        f"/contingencia/reemplazos/servicio/{servicio['id']}", headers=h).json()
    assert historial[0]["en_curso"] is True
    assert historial[0]["regreso_en"] is None

    # Y el regreso de verdad dice lo mismo que dijo la previa.
    hecho2 = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[3]["fecha"])
    assert hecho2.status_code == 200, hecho2.text
    assert hecho2.json()["hasta"] == previa["hasta"]


def test_el_historial_dice_el_estado_y_el_dia_partido(cliente, sesion, datos):
    """Lo que la tarjeta necesita para no mentir.

    Un movimiento en curso y uno que ya termino se veian identicos, y el
    dia partido --la prueba de que quien trabajo media jornada cobra
    media jornada-- solo se veia abriendo la nomina.
    """
    servicio = _montado(cliente, sesion, datos, offset=720, dias=4)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")

    _se_presenta(cliente, sesion, dias[1])
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()

    fila = cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                       headers=h).json()[0]
    assert fila["en_curso"] is True
    assert [x["fecha"] for x in fila["partidos"]] == [dias[1]["fecha"]]
    assert len(fila["partidos"][0]["hora"]) == 5, fila["partidos"][0]
    # Un eventual no se vuelve a pedir: eso es del implantado.
    assert fila["se_vuelve_a_pedir"] is False

    # Cerrado: deja de estar en curso y queda firmado.
    _regreso(cliente, sesion, hecho["reemplazo_id"], dias[3]["fecha"])
    fila = cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                       headers=h).json()[0]
    assert fila["en_curso"] is False
    assert fila["regreso_por"] == "Ana Solis"


# ================================================== la raya con implantado'''

assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("test_relevo.py: dos pruebas mas")

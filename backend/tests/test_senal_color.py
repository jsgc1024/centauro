"""La senal de color: la paleta, el servicio, la hoja y el telefono.

Pedido de Salvador, 22 sep. La senal con la que el principal reconoce
al equipo puede ser un color --una pantalla de un solo color en el
telefono--, con una palabra encima o sin ella.
"""
from test_campo import _servicio_de_juan

NARANJA = {"clave": "naranja", "hex": "#F26B1D", "letra": "#ffffff"}


def _senal(cliente, sesion, servicio, **datos):
    return cliente.put(f"/servicios/{servicio['id']}/senal", json=datos,
                       headers=sesion("consultor"))


def _vista(cliente, sesion, servicio):
    r = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


def _ficha(cliente, sesion, servicio):
    dia = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    return next(f for f in dia["hoy"] if f["servicio_id"] == servicio["id"])


def test_la_paleta_viaja_con_la_vista_previa(cliente, sesion, datos):
    """La consola dibuja los circulos con lo que le manda el servidor:
    una sola copia de los colores."""
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    paleta = _vista(cliente, sesion, servicio)["senal_colores"]
    assert len(paleta) == 8
    assert paleta[0] == NARANJA
    for c in paleta:
        assert c["hex"].startswith("#") and c["letra"] in ("#ffffff", "#000000")


def test_el_color_se_guarda_con_su_hex_y_su_letra(cliente, sesion, datos):
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    r = _senal(cliente, sesion, servicio, color="naranja", texto="CARTER",
               nota="A la salida del filtro")
    assert r.status_code == 200, r.text
    assert r.json()["color"] == "naranja"

    senal = _vista(cliente, sesion, servicio)["senal"]
    assert senal["color"] == NARANJA
    assert senal["texto"] == "CARTER" and senal["nota"] == "A la salida del filtro"
    assert senal["imagen"] is None

    # Y el telefono lo recibe resuelto: el hex y la letra, sin paleta.
    f = _ficha(cliente, sesion, servicio)
    assert f["senal"]["color"] == NARANJA
    assert f["senal"]["texto"] == "CARTER"
    assert f["senal"]["imagen"] is False


def test_el_color_puede_ir_solo(cliente, sesion, datos):
    """Sin palabra y sin imagen: el color es senal suficiente."""
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    assert _senal(cliente, sesion, servicio, color="verde").status_code == 200
    senal = _vista(cliente, sesion, servicio)["senal"]
    assert senal["color"]["clave"] == "verde"
    assert senal["texto"] is None and senal["imagen"] is None
    assert _ficha(cliente, sesion, servicio)["senal"]["color"]["clave"] == "verde"


def test_un_color_fuera_de_la_paleta_no_entra(cliente, sesion, datos):
    """Solo los de la paleta tienen nombre en los tres idiomas, y el
    nombre es lo que lee el principal."""
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    r = _senal(cliente, sesion, servicio, color="fucsia")
    assert r.status_code == 400, r.text
    assert "naranja" in r.json()["detail"]["colores"]
    assert _vista(cliente, sesion, servicio)["senal"] is None


def test_la_hoja_del_principal_dice_el_color_en_su_idioma(cliente, sesion,
                                                           datos):
    """Es lo que el principal lee antes de llegar: que buscar."""
    h = sesion("consultor")
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    assert _senal(cliente, sesion, servicio, color="naranja",
                  texto="CARTER").status_code == 200
    assert cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                        json={"motivo": "prueba"}, headers=h).status_code in (200, 201)
    assert cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion",
                        headers=h).status_code == 200, "no se libero el TS"

    hojas = {}
    for idioma in ("es", "en", "pt"):
        r = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja?idioma={idioma}",
                        headers=h)
        assert r.status_code == 200, r.text
        hojas[idioma] = r.text
        assert "#F26B1D" in r.text, f"la hoja en {idioma} no pinta el color"
        assert "CARTER" in r.text
    assert "en naranja" in hojas["es"] and "y la palabra CARTER" in hojas["es"]
    assert "in orange" in hojas["en"] and "and the word CARTER" in hojas["en"]
    assert "em laranja" in hojas["pt"] and "e a palavra CARTER" in hojas["pt"]


def test_quitar_la_senal_quita_el_color(cliente, sesion, datos):
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    assert _senal(cliente, sesion, servicio, color="azul",
                  texto="CARTER").status_code == 200
    r = cliente.delete(f"/servicios/{servicio['id']}/senal",
                       headers=sesion("consultor"))
    assert r.status_code == 204, r.text
    assert _vista(cliente, sesion, servicio)["senal"] is None
    assert _ficha(cliente, sesion, servicio)["senal"] is None


def test_la_nota_se_puede_mandar_sola_si_ya_hay_imagen(cliente, sesion, datos):
    """Es lo que hace la consola despues de subir la imagen: manda la
    nota en un segundo paso, y la imagen se tiene que quedar."""
    servicio, _ = _servicio_de_juan(cliente, sesion, datos, dia=0)
    pixel = "data:image/png;base64,iVBORw0KGgo="
    assert _senal(cliente, sesion, servicio, imagen=pixel).status_code == 200
    r = _senal(cliente, sesion, servicio, nota="En el lobby")
    assert r.status_code == 200, r.text
    senal = _vista(cliente, sesion, servicio)["senal"]
    assert senal["imagen"] == pixel and senal["nota"] == "En el lobby"
    assert senal["color"] is None

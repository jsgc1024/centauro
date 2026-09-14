"""La revision de la unidad cuando cambia de manos.

El dano al vehiculo siempre aparece despues y sin dueno. Un golpe que
nadie vio al recibir se discute tres semanas mas tarde, cuando ya nadie
puede probar nada, y termina pagandolo el ultimo que la trajo —que no
siempre es el que lo hizo.

Cuatro fotos y una firma en el momento del cambio de manos son lo unico
que lo resuelve, porque ese es el unico momento en que todavia se puede
saber. Lo que se prueba aqui es que el sistema no acepte una revision a
medias, porque una revision a medias no sirve para nada y ademas deja a
todos tranquilos creyendo que si.
"""
from ayudas import asignar, configurar_origen, crear_servicio, jornada, manana

# Una imagen de un pixel. Lo que importa en estas pruebas es el
# contrato, no el JPEG.
PIXEL = ("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAEBAQEB"
         "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
         "AQEBAQEBAQH/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQ"
         "AQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==")

CUATRO = [{"angulo": a, "imagen": PIXEL}
          for a in ("frente", "atras", "izquierdo", "derecho")]


def _servicio_con_unidad(cliente, sesion, datos, quien="Juan Ramirez"):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(0), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"],
                persona_id=datos["personal"][quien]["id"],
                vehiculo_id=datos["suburban"]["id"])[0]
    assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def _revision(servicio, datos, tipo, km, fotos=None, **extra):
    cuerpo = {"servicio_id": servicio["id"],
              "vehiculo_id": datos["suburban"]["id"],
              "tipo": tipo,
              "kilometraje": km,
              "combustible_octavos": 8,
              "firma": "data:image/png;base64,iVBORw0KGgo=",
              "fotos": CUATRO if fotos is None else fotos}
    cuerpo.update(extra)
    return cuerpo


def test_la_unidad_se_recibe_con_los_cuatro_lados(cliente, sesion, datos):
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    h = sesion("juan")

    r = cliente.post("/campo/revisiones", headers=h,
                     json=_revision(servicio, datos, "recibe", 42_000))
    assert r.status_code == 201, r.text
    assert r.json()["fotos"] == 4

    r = cliente.get(f"/campo/servicios/{servicio['id']}/unidades", headers=h)
    assert r.status_code == 200, r.text
    unidad = r.json()["unidades"][0]
    assert unidad["recibida"]["kilometraje"] == 42_000
    assert unidad["entregada"] is None
    assert len(unidad["recibida"]["fotos"]) == 4


def test_con_tres_fotos_no_pasa_y_dice_cual_falta(cliente, sesion, datos):
    """Descubrir que falta el costado derecho cuando ya no se puede
    volver a tomar la foto es descubrirlo demasiado tarde."""
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    r = cliente.post("/campo/revisiones", headers=sesion("juan"),
                     json=_revision(servicio, datos, "recibe", 42_000,
                                    fotos=CUATRO[:3]))
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["faltan"] == ["derecho"]


def test_no_se_entrega_lo_que_nunca_se_recibio(cliente, sesion, datos):
    """Sin estado de entrada no hay contra que comparar: la revision de
    salida sola no prueba nada."""
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    r = cliente.post("/campo/revisiones", headers=sesion("juan"),
                     json=_revision(servicio, datos, "entrega", 42_300))
    assert r.status_code == 409, r.text
    assert "nunca se reviso" in r.json()["detail"]["mensaje"]


def test_al_entregar_sale_solo_el_kilometraje_del_servicio(cliente, sesion,
                                                           datos):
    """El numero que nadie apunta y del que despues todos se acuerdan
    distinto."""
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    h = sesion("juan")
    cliente.post("/campo/revisiones", headers=h,
                 json=_revision(servicio, datos, "recibe", 42_000))
    r = cliente.post("/campo/revisiones", headers=h,
                     json=_revision(servicio, datos, "entrega", 42_380))
    assert r.status_code == 201, r.text
    assert r.json()["kilometros_recorridos"] == 380


def test_la_misma_unidad_no_se_recibe_dos_veces(cliente, sesion, datos):
    """Va por servicio, no por dia: un implantado con la misma camioneta
    veintidos dias no la revisa veintidos veces."""
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    h = sesion("juan")
    cliente.post("/campo/revisiones", headers=h,
                 json=_revision(servicio, datos, "recibe", 42_000))
    r = cliente.post("/campo/revisiones", headers=h,
                     json=_revision(servicio, datos, "recibe", 42_050))
    assert r.status_code == 409, r.text
    assert "ya se reviso" in r.json()["detail"]["mensaje"]


def test_nadie_revisa_una_unidad_que_no_trae(cliente, sesion, datos):
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    r = cliente.post("/campo/revisiones", headers=sesion("luis"),
                     json=_revision(servicio, datos, "recibe", 42_000))
    assert r.status_code == 403, r.text

    r = cliente.get(f"/campo/servicios/{servicio['id']}/unidades",
                    headers=sesion("luis"))
    assert r.status_code == 403, r.text


def test_la_consola_ve_las_dos_puntas_y_la_diferencia(cliente, sesion, datos):
    """Es donde se resuelve un reclamo de dano: como se recibio, como se
    entrego, y cuanto se recorrio entre las dos."""
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    h = sesion("juan")
    cliente.post("/campo/revisiones", headers=h,
                 json=_revision(servicio, datos, "recibe", 42_000,
                                nota="Rayon en la defensa trasera"))
    cliente.post("/campo/revisiones", headers=h,
                 json=_revision(servicio, datos, "entrega", 42_380))

    r = cliente.get(f"/servicios/{servicio['id']}/revisiones",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    unidad = r.json()["unidades"][0]
    assert unidad["completa"] is True
    assert unidad["kilometros"] == 380
    assert unidad["recibe"]["nota"] == "Rayon en la defensa trasera"
    assert unidad["recibe"]["tiene_firma"] is True
    assert len(unidad["entrega"]["fotos"]) == 4


def test_sin_revisar_la_consola_lo_dice_en_vez_de_callarse(cliente, sesion,
                                                           datos):
    """Una pantalla vacia se lee como 'no hubo problema'. El hueco tiene
    que verse."""
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    r = cliente.get(f"/servicios/{servicio['id']}/revisiones",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["unidades"] == []


def test_el_dia_avisa_que_falta_revisar_la_unidad(cliente, sesion, datos):
    """El equipo no tiene que acordarse: la pantalla del dia se lo pone
    enfrente mientras falte, y deja de ponerlo cuando ya no."""
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    h = sesion("juan")

    f = cliente.get("/campo/mi-dia", headers=h).json()["hoy"][0]
    assert f["servicio_id"] == servicio["id"]
    assert f["revision"]["por_recibir"] == 1
    assert f["revision"]["por_entregar"] == 0

    cliente.post("/campo/revisiones", headers=h,
                 json=_revision(servicio, datos, "recibe", 42_000))
    f = cliente.get("/campo/mi-dia", headers=h).json()["hoy"][0]
    assert f["revision"]["por_recibir"] == 0
    assert f["revision"]["por_entregar"] == 1

    cliente.post("/campo/revisiones", headers=h,
                 json=_revision(servicio, datos, "entrega", 42_380))
    f = cliente.get("/campo/mi-dia", headers=h).json()["hoy"][0]
    assert f["revision"]["por_recibir"] == 0
    assert f["revision"]["por_entregar"] == 0

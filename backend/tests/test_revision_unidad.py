"""La revision de la unidad cuando cambia de manos.

El dano al vehiculo siempre aparece despues y sin dueno. Un golpe que
nadie vio al recibir se discute tres semanas mas tarde, cuando ya nadie
puede probar nada, y termina pagandolo el ultimo que la trajo —que no
siempre es el que lo hizo.

Cuatro fotos de la lata, una del tablero y una firma en el momento del
cambio de manos son lo unico que lo resuelve, porque ese es el unico
momento en que todavia se puede saber. Lo que se prueba aqui es que el
sistema no acepte una revision a medias, porque una revision a medias no
sirve para nada y ademas deja a todos tranquilos creyendo que si.

Y quien firma importa tanto como las fotos: una revision firmada por
quien no traia la unidad es papel. Eso vive en `_suya`, y las ultimas
pruebas de este archivo son las suyas.
"""
from ayudas import asignar, configurar_origen, crear_servicio, jornada, manana

# Una imagen de un pixel. Lo que importa en estas pruebas es el
# contrato, no el JPEG.
PIXEL = ("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAEBAQEB"
         "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
         "AQEBAQEBAQH/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQ"
         "AQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==")

# Los cuatro lados y el tablero. El odometro se pide desde el 18 de
# septiembre: sin el, el kilometraje era un numero tecleado y la cuenta
# que sale al entregar no tenia con que comprobarse.
COMPLETAS = [{"angulo": a, "imagen": PIXEL}
             for a in ("frente", "atras", "izquierdo", "derecho", "odometro")]


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
              # Una firma de verdad son cientos de puntos; el backend
              # exige que lo parezca para que no pase un lienzo vacio.
              "firma": "data:image/png;base64," + ("A" * 200),
              "hubo_dano": False,
              "fotos": COMPLETAS if fotos is None else fotos}
    cuerpo.update(extra)
    return cuerpo


def test_la_unidad_se_recibe_con_los_cuatro_lados(cliente, sesion, datos):
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    h = sesion("juan")

    r = cliente.post("/campo/revisiones", headers=h,
                     json=_revision(servicio, datos, "recibe", 42_000))
    assert r.status_code == 201, r.text
    assert r.json()["fotos"] == 5

    r = cliente.get(f"/campo/servicios/{servicio['id']}/unidades", headers=h)
    assert r.status_code == 200, r.text
    unidad = r.json()["unidades"][0]
    assert unidad["recibida"]["kilometraje"] == 42_000
    assert unidad["entregada"] is None
    # La lista dice cuantas fotos hay pero no las manda: son medio mega
    # cada una, y esta pantalla se abre en un estacionamiento con media
    # barra de senal. Antes venian todas las de todas las unidades del
    # servicio en cada consulta.
    assert unidad["recibida"]["cuantas_fotos"] == 5
    assert unidad["recibida"]["fotos"] is None

    # Se piden de una revision a la vez, cuando se van a ver.
    una = cliente.get(f"/campo/revisiones/{unidad['recibida']['id']}",
                      headers=h)
    assert una.status_code == 200, una.text
    assert len(una.json()["fotos"]) == 5

    # Y solo si el servicio es suyo.
    ajeno = cliente.get(f"/campo/revisiones/{unidad['recibida']['id']}",
                        headers=sesion("luis"))
    assert ajeno.status_code == 403, ajeno.text


def test_con_tres_fotos_no_pasa_y_dice_cuales_faltan(cliente, sesion, datos):
    """Descubrir que falta el costado derecho cuando ya no se puede
    volver a tomar la foto es descubrirlo demasiado tarde."""
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    r = cliente.post("/campo/revisiones", headers=sesion("juan"),
                     json=_revision(servicio, datos, "recibe", 42_000,
                                    fotos=COMPLETAS[:3]))
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["faltan"] == ["derecho", "odometro"]


def test_los_cuatro_lados_sin_el_tablero_no_bastan(cliente, sesion, datos):
    """El odometro no es una foto mas.

    Los cuatro lados prueban como estaba la lata; el tablero prueba el
    numero. Sin el, "recorrio 1,800 km" sale de dos cifras que alguien
    escribio de memoria, y esa es justo la cuenta de la que despues todos
    se acuerdan distinto.
    """
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    r = cliente.post("/campo/revisiones", headers=sesion("juan"),
                     json=_revision(servicio, datos, "recibe", 42_000,
                                    fotos=COMPLETAS[:4]))
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["faltan"] == ["odometro"]


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
    assert len(unidad["entrega"]["fotos"]) == 5


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


# ================================================== quién puede firmarla

def _dos_unidades(cliente, sesion, datos):
    """Un equipo de dos, con dos camionetas, cada quien en la suya."""
    h = sesion("consultor")
    # De la misma ciudad que la primera: una unidad de otra plaza se
    # asigna igual con `forzar`, pero deja la prueba midiendo otra cosa.
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"]
                and v["plaza_id"] == datos["suburban"]["plaza_id"])
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(0), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]

    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    for persona in (juan, luis):
        for r in asignar(cliente, h, j["id"], persona_id=persona):
            assert r.status_code == 200, r.text
    for unidad in (datos["suburban"]["id"], otra["id"]):
        for r in asignar(cliente, h, j["id"], vehiculo_id=unidad):
            assert r.status_code == 200, r.text

    for persona, unidad in ((juan, datos["suburban"]["id"]),
                            (luis, otra["id"])):
        r = cliente.patch(
            f"/servicios/jornadas/{j['id']}/personal/{persona}/unidad",
            json={"vehiculo_id": unidad}, headers=h)
        assert r.status_code == 200, r.text

    configurar_origen(cliente, h, j["id"])
    return servicio, otra


def test_no_se_firma_la_revision_de_la_unidad_de_otro(cliente, sesion, datos):
    """Lo que estaba abierto hasta hoy.

    La comprobación recibía la unidad como dato y no la miraba: solo
    veía que la persona estuviera en el servicio. En un equipo de cuatro
    con dos camionetas, el conductor de la primera podía firmar la
    recepción de la segunda —y la firma es justo lo que hace que la
    revisión sirva para discutir un golpe tres semanas después.
    """
    servicio, otra = _dos_unidades(cliente, sesion, datos)

    r = cliente.post("/campo/revisiones", headers=sesion("juan"), json={
        **_revision(servicio, datos, "recibe", 42_000),
        "vehiculo_id": otra["id"]})
    assert r.status_code == 403, r.text
    cuerpo = r.json()["detail"]
    assert "no es la tuya" in cuerpo["mensaje"].lower()
    # Y le dice cuál sí, que es la mitad útil del mensaje.
    assert cuerpo["la_tuya"] == datos["suburban"]["placa"]


def test_cada_quien_firma_la_suya(cliente, sesion, datos):
    """El otro lado del mismo candado: con la unidad correcta, pasa."""
    servicio, otra = _dos_unidades(cliente, sesion, datos)

    assert cliente.post("/campo/revisiones", headers=sesion("juan"),
                        json=_revision(servicio, datos, "recibe",
                                       42_000)).status_code == 201
    r = cliente.post("/campo/revisiones", headers=sesion("luis"), json={
        **_revision(servicio, datos, "recibe", 71_000),
        "vehiculo_id": otra["id"]})
    assert r.status_code == 201, r.text


def test_con_una_sola_unidad_no_hace_falta_decir_quien_la_trae(cliente,
                                                               sesion, datos):
    """Es la regla del propio modelo: "con una sola unidad sobra decirlo".

    Si se exigiera siempre que la asignación dijera quién trae la
    camioneta, el equipo de un solo vehículo —que es la mayoría— se
    quedaría sin poder revisarla hasta que el consultor capturara un dato
    que no le sirve a nadie más.
    """
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(0), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    for persona in ("Juan Ramirez", "Luis Mendoza"):
        asignar(cliente, h, j["id"], persona_id=datos["personal"][persona]["id"])
    asignar(cliente, h, j["id"], vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])

    r = cliente.post("/campo/revisiones", headers=sesion("luis"),
                     json=_revision(servicio, datos, "recibe", 42_000))
    assert r.status_code == 201, r.text


def test_una_unidad_que_no_anda_en_ese_servicio(cliente, sesion, datos):
    """Placa equivocada. Es el error de dedo, no el abuso, pero el
    mensaje tiene que distinguirlo del otro: aquí no hay "la tuya" que
    ofrecer porque el problema es la unidad, no la persona."""
    servicio, _ = _servicio_con_unidad(cliente, sesion, datos)
    ajena = next(v for v in datos["vehiculos"]
                 if v["id"] != datos["suburban"]["id"])

    r = cliente.post("/campo/revisiones", headers=sesion("juan"), json={
        **_revision(servicio, datos, "recibe", 42_000),
        "vehiculo_id": ajena["id"]})
    assert r.status_code == 403, r.text
    assert "no va en tus dias" in r.json()["detail"]["mensaje"].lower()

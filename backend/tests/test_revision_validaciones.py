"""Lo que la revision de unidad no debe aceptar, y lo que reabrir deshace.

La revision existe para poder discutir un dano tres semanas despues. Una
revision con un kilometraje imposible, sin firma, o con fotos que nunca
llegaron por su peso, no sirve para eso —y lo peor es que se ve igual
que una buena hasta que alguien la necesita.
"""
from ayudas import asignar, configurar_origen, crear_servicio, jornada, manana

PIXEL = ("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAEBAQEB"
         "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
         "AQEBAQEBAQH/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQ"
         "AQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==")
FIRMA = "data:image/png;base64," + ("A" * 200)
# Los cuatro lados y el tablero. El odometro se pide desde el 18 de
# septiembre: sin el, el kilometraje era un numero tecleado y la cuenta
# que sale al entregar no tenia con que comprobarse.
COMPLETAS = [{"angulo": a, "imagen": PIXEL}
             for a in ("frente", "atras", "izquierdo", "derecho", "odometro")]


def _servicio(cliente, sesion, datos, dias_atras=0):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(-dias_atras), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])[0]
    assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def _cuerpo(servicio, datos, tipo, km=42_000, **extra):
    cuerpo = {"servicio_id": servicio["id"],
              "vehiculo_id": datos["suburban"]["id"],
              "tipo": tipo, "kilometraje": km,
              "combustible_octavos": 8, "firma": FIRMA,
              "hubo_dano": False, "fotos": COMPLETAS}
    cuerpo.update(extra)
    return cuerpo


# ======================================================= la revision

def test_sin_firma_no_se_guarda(cliente, sesion, datos):
    """La promesa es "cuatro fotos y una firma". Media promesa vivia en
    el JavaScript del telefono: una peticion directa guardaba una
    revision sin firmar y nadie se enteraba hasta el reclamo."""
    servicio, _ = _servicio(cliente, sesion, datos)
    r = cliente.post("/campo/revisiones", headers=sesion("juan"),
                     json=_cuerpo(servicio, datos, "recibe", firma=None))
    assert r.status_code == 409, r.text
    assert "firma" in r.json()["detail"]["mensaje"].lower()


def test_el_kilometraje_no_puede_ser_negativo(cliente, sesion, datos):
    servicio, _ = _servicio(cliente, sesion, datos)
    r = cliente.post("/campo/revisiones", headers=sesion("juan"),
                     json=_cuerpo(servicio, datos, "recibe", km=-50))
    assert r.status_code == 422, r.text


def test_el_tanque_se_lee_en_octavos_y_nada_mas(cliente, sesion, datos):
    """Con 99 se guardaba y la pantalla ensenaba "Tanque undefined"."""
    servicio, _ = _servicio(cliente, sesion, datos)
    r = cliente.post("/campo/revisiones", headers=sesion("juan"),
                     json=_cuerpo(servicio, datos, "recibe",
                                  combustible_octavos=99))
    assert r.status_code == 422, r.text


def test_no_se_entrega_con_menos_kilometros_de_los_que_tenia(cliente, sesion,
                                                             datos):
    """Un dedazo al entregar —45000 donde decia 145000— dejaba a la
    consola ensenando "-100,000 km recorridos" sin marcarlo como raro."""
    servicio, _ = _servicio(cliente, sesion, datos)
    h = sesion("juan")
    r = cliente.post("/campo/revisiones", headers=h,
                     json=_cuerpo(servicio, datos, "recibe", km=145_000))
    assert r.status_code == 201, r.text

    r = cliente.post("/campo/revisiones", headers=h,
                     json=_cuerpo(servicio, datos, "entrega", km=45_000))
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["al_recibir"] == 145_000


def test_una_foto_enorme_no_pasa(cliente, sesion, datos):
    """Van como data URI dentro del JSON, y del otro lado hay un
    telefono con media barra de senal."""
    servicio, _ = _servicio(cliente, sesion, datos)
    gordas = [{"angulo": a, "imagen": "data:image/jpeg;base64," + "A" * 3_100_000}
              for a in ("frente", "atras", "izquierdo", "derecho")]
    r = cliente.post("/campo/revisiones", headers=sesion("juan"),
                     json=_cuerpo(servicio, datos, "recibe", fotos=gordas))
    assert r.status_code == 413, r.text


def test_la_consola_no_baja_las_fotos_si_no_se_las_piden(cliente, sesion,
                                                          datos):
    """Son varios megas por servicio y la ficha se recarga sola en casi
    cada accion del consultor."""
    servicio, _ = _servicio(cliente, sesion, datos)
    cliente.post("/campo/revisiones", headers=sesion("juan"),
                 json=_cuerpo(servicio, datos, "recibe"))

    h = sesion("consultor")
    ligero = cliente.get(f"/servicios/{servicio['id']}/revisiones",
                         headers=h).json()
    fotos = ligero["unidades"][0]["recibe"]["fotos"]
    assert len(fotos) == 5
    assert "imagen" not in fotos[0], "la foto viajo sin que nadie la pidiera"

    completo = cliente.get(f"/servicios/{servicio['id']}/revisiones?fotos=true",
                           headers=h).json()
    assert completo["unidades"][0]["recibe"]["fotos"][0]["imagen"]


# ======================================================= reabrir

def test_reabrir_borra_tambien_la_hora_que_tecleo_la_central(cliente, sesion,
                                                             datos):
    """Dejarla era peor que no haber cerrado: quedaba una hora escrita
    en una oficina, sin firma, que se lee igual que una marcada desde la
    calle."""
    _, j = _servicio(cliente, sesion, datos, dias_atras=2)
    h = sesion("central")
    motivo = "El equipo se quedo sin bateria; confirmado por telefono"

    cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                 json={"justificacion": motivo}, headers=h)
    b = cliente.get(f"/operacion/jornadas/{j['id']}/bitacora",
                    headers=h).json()
    assert b["jornada"]["inicio_real"] is not None

    r = cliente.post(f"/operacion/jornadas/{j['id']}/reabrir",
                     json={"justificacion": "Me equivoque de jornada"},
                     headers=h)
    assert r.status_code == 200, r.text

    b = cliente.get(f"/operacion/jornadas/{j['id']}/bitacora",
                    headers=h).json()
    assert b["jornada"]["inicio_real"] is None
    assert b["jornada"]["fin_real"] is None
    assert b["jornada"]["cerrada_a_mano"] is None


def test_un_dia_reabierto_no_queda_como_si_estuviera_pasando(cliente, sesion,
                                                             datos):
    """EN_CURSO significa "esta pasando ahora mismo" para el pulso de la
    central: un dia reabierto de hace tres semanas subia a la banda roja
    con "sin reporte hace 512 horas"."""
    _, j = _servicio(cliente, sesion, datos, dias_atras=2)
    h = sesion("central")
    motivo = "El equipo se quedo sin bateria; confirmado por telefono"

    cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                 json={"justificacion": motivo}, headers=h)
    cliente.post(f"/operacion/jornadas/{j['id']}/reabrir",
                 json={"justificacion": "Me equivoque de jornada"}, headers=h)

    b = cliente.get(f"/operacion/jornadas/{j['id']}/bitacora",
                    headers=h).json()
    assert b["jornada"]["estatus"] == "planeada"

    # Y vuelve a la lista de lo que falta cerrar, que es donde debe estar.
    pendientes = cliente.get("/operacion/dias-sin-cerrar", headers=h).json()
    assert [d for d in pendientes["dias"] if d["jornada_id"] == j["id"]]

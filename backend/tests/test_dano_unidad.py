"""La declaración de daño de la unidad.

Pedido por Salvador (18 sep): que quien recibe la unidad declare si la
recibe con algún daño, y que al entregarla declare si se dañó durante el
servicio y explique qué pasó.

Antes había una nota libre y fotos de golpe, las dos opcionales. **El
caso normal de una casilla opcional es que se quede vacía.** Quien recibe
una camioneta golpeada a las seis de la mañana, con prisa, no va a
documentar por su cuenta un daño que no hizo —y ahí es exactamente donde
le va a hacer falta tres semanas después.

Lo que estas pruebas cuidan, además de que los campos existan, es **la
regla que hace que el dato sirva**:

> Si declarar un daño propio costara caro, nadie declararía nunca, y
> tendríamos una casilla que siempre dice "no" y una falsa sensación de
> estar documentando.

Por eso: contestar "no" es un clic; declarar un daño al recibir no
dispara nada contra quien lo declara; y declarar uno al entregar avisa al
consultor sin clasificar nada solo. Decisión de Salvador, 19 sep.
"""
from ayudas import asignar, configurar_origen, crear_servicio, jornada, manana

PIXEL = ("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAEBAQEB"
         "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
         "AQEBAQEBAQH/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQ"
         "AQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==")
FIRMA = "data:image/png;base64," + ("A" * 200)
COMPLETAS = [{"angulo": a, "imagen": PIXEL}
             for a in ("frente", "atras", "izquierdo", "derecho", "odometro")]
GOLPE = {"angulo": "dano", "imagen": PIXEL, "nota": "Defensa trasera"}


def _servicio(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(0), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    return servicio


def _cuerpo(servicio, datos, tipo, km=42_000, **extra):
    cuerpo = {"servicio_id": servicio["id"],
              "vehiculo_id": datos["suburban"]["id"],
              "tipo": tipo, "kilometraje": km, "combustible_octavos": 8,
              "firma": FIRMA, "fotos": list(COMPLETAS)}
    cuerpo.update(extra)
    return cuerpo


def _revisar(cliente, sesion, cuerpo):
    return cliente.post("/campo/revisiones", headers=sesion("juan"), json=cuerpo)


# ======================================= la pregunta no se puede saltar

def test_sin_contestar_no_se_firma(cliente, sesion, datos):
    """Lo que cambia todo. Antes la nota era opcional y el caso normal
    era que nadie escribiera nada."""
    servicio = _servicio(cliente, sesion, datos)
    r = _revisar(cliente, sesion, _cuerpo(servicio, datos, "recibe"))
    assert r.status_code == 409, r.text
    assert "dano" in r.json()["detail"]["mensaje"].lower()


def test_la_pregunta_es_distinta_en_cada_punta(cliente, sesion, datos):
    """Al recibir se pregunta si la recibe golpeada; al entregar, si se
    golpeó con él. Es la distinción que decide quién responde, y el
    mensaje tiene que decirla con las palabras de cada momento."""
    servicio = _servicio(cliente, sesion, datos)

    entrada = _revisar(cliente, sesion, _cuerpo(servicio, datos, "recibe"))
    assert "recibes" in entrada.json()["detail"]["mensaje"]
    assert "protege" in entrada.json()["detail"]["que_hacer"]

    _revisar(cliente, sesion, _cuerpo(servicio, datos, "recibe",
                                      hubo_dano=False))
    salida = _revisar(cliente, sesion, _cuerpo(servicio, datos, "entrega",
                                               km=42_300))
    assert "durante tu servicio" in salida.json()["detail"]["mensaje"]


def test_decir_que_no_es_un_clic(cliente, sesion, datos):
    """La condición para que el dato sirva: declarar no puede costar más
    que no declarar. Si contestar "no" pidiera algo, la casilla diría
    "no" siempre y no estaríamos documentando nada."""
    servicio = _servicio(cliente, sesion, datos)
    r = _revisar(cliente, sesion, _cuerpo(servicio, datos, "recibe",
                                          hubo_dano=False))
    assert r.status_code == 201, r.text
    assert "declaracion" not in r.json()


# ============================================ declarar, con lo que lleva

def test_un_dano_declarado_va_con_tipo_texto_y_foto(cliente, sesion, datos):
    servicio = _servicio(cliente, sesion, datos)

    # Sin tipo.
    r = _revisar(cliente, sesion, _cuerpo(
        servicio, datos, "recibe", hubo_dano=True,
        dano_nota="Rayon largo en la puerta del copiloto",
        fotos=COMPLETAS + [GOLPE]))
    assert r.status_code == 409 and "de que fue" in r.json()["detail"]["mensaje"]
    assert "rayon" in r.json()["detail"]["opciones"]

    # Sin explicación.
    r = _revisar(cliente, sesion, _cuerpo(
        servicio, datos, "recibe", hubo_dano=True, dano_tipo="rayon",
        dano_nota="ok", fotos=COMPLETAS + [GOLPE]))
    assert r.status_code == 409 and "describir" in r.json()["detail"]["mensaje"]

    # Sin foto del golpe. El texto dice qué pasó; la foto dice cómo se
    # ve. Sin la segunda no hay contra qué comparar después.
    r = _revisar(cliente, sesion, _cuerpo(
        servicio, datos, "recibe", hubo_dano=True, dano_tipo="rayon",
        dano_nota="Rayon largo en la puerta del copiloto"))
    assert r.status_code == 409 and "foto" in r.json()["detail"]["mensaje"]

    # Completa.
    r = _revisar(cliente, sesion, _cuerpo(
        servicio, datos, "recibe", hubo_dano=True, dano_tipo="rayon",
        dano_nota="Rayon largo en la puerta del copiloto",
        fotos=COMPLETAS + [GOLPE]))
    assert r.status_code == 201, r.text


def test_al_entregar_se_pide_explicar_que_paso(cliente, sesion, datos):
    """No es lo mismo describir un golpe que venía que explicar uno que
    hiciste. El mensaje cambia porque la pregunta es otra."""
    servicio = _servicio(cliente, sesion, datos)
    _revisar(cliente, sesion, _cuerpo(servicio, datos, "recibe",
                                      hubo_dano=False))

    r = _revisar(cliente, sesion, _cuerpo(
        servicio, datos, "entrega", km=42_300, hubo_dano=True,
        dano_tipo="golpe", dano_nota="corto",
        fotos=COMPLETAS + [GOLPE]))
    assert r.status_code == 409
    assert "que paso" in r.json()["detail"]["mensaje"]


# =========================================== lo que NO hace el sistema

def test_declarar_al_recibir_no_dispara_nada(cliente, sesion, datos):
    """Quien declara un daño que ya venía no hizo nada: se está
    protegiendo. Frenarlo, alertar a alguien o dejarle un renglón en su
    expediente sería castigar justo lo que queremos que haga."""
    servicio = _servicio(cliente, sesion, datos)
    r = _revisar(cliente, sesion, _cuerpo(
        servicio, datos, "recibe", hubo_dano=True, dano_tipo="golpe",
        dano_nota="Abolladura en la defensa trasera, ya venia",
        fotos=COMPLETAS + [GOLPE]))
    assert r.status_code == 201, r.text
    assert r.json()["declaracion"]["lo_revisa_tu_consultor"] is False

    # Nada en su expediente: el sistema no clasifica solo.
    ficha = cliente.get(
        f"/profesionalismo/persona/{datos['personal']['Juan Ramirez']['id']}",
        headers=sesion("consultor"))
    assert ficha.status_code == 200, ficha.text


def test_un_dano_nuevo_avisa_al_consultor_y_nada_mas(cliente, sesion, datos):
    """Decisión de Salvador (19 sep). Sin alerta que cerrar y sin
    incidencia automática —ni siquiera de las que no quitan estrellas—:
    el sistema no clasifica solo, eso es del consultor con visto bueno de
    dirección, y un renglón que nadie juzgó es algo que después hay que
    explicar."""
    from app import models as m
    from app.db import SessionLocal

    servicio = _servicio(cliente, sesion, datos)
    _revisar(cliente, sesion, _cuerpo(servicio, datos, "recibe",
                                      hubo_dano=False))
    r = _revisar(cliente, sesion, _cuerpo(
        servicio, datos, "entrega", km=42_300, hubo_dano=True,
        dano_tipo="golpe",
        dano_nota="Me golpearon estacionado afuera del hotel",
        fotos=COMPLETAS + [GOLPE]))
    assert r.status_code == 201, r.text
    assert r.json()["declaracion"]["lo_revisa_tu_consultor"] is True

    db = SessionLocal()
    try:
        assert db.query(m.Incidencia).count() == 0, "se clasifico solo"
        assert db.query(m.AlertaIncidencia).count() == 0, "levanto una alerta"
    finally:
        db.close()


# ================================================ lo que ve el consultor

def test_la_consola_marca_la_unidad_que_volvio_golpeada(cliente, sesion,
                                                        datos):
    """El renglón que hay que atender, calculado en el servidor y no en
    la pantalla: es la pregunta que se hace al abrir, no un detalle que
    se busca."""
    servicio = _servicio(cliente, sesion, datos)
    _revisar(cliente, sesion, _cuerpo(servicio, datos, "recibe",
                                      hubo_dano=False))
    _revisar(cliente, sesion, _cuerpo(
        servicio, datos, "entrega", km=42_300, hubo_dano=True,
        dano_tipo="cristal", dano_nota="Se estrello el parabrisas con una piedra",
        fotos=COMPLETAS + [GOLPE]))

    r = cliente.get(f"/servicios/{servicio['id']}/revisiones",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    unidad = r.json()["unidades"][0]
    assert unidad["dano_nuevo"] is True
    assert unidad["ya_venia_danada"] is False
    assert unidad["entrega"]["dano_tipo"] == "cristal"
    assert "piedra" in unidad["entrega"]["dano_nota"]


def test_la_que_ya_venia_golpeada_se_distingue_de_la_que_se_golpeo(
        cliente, sesion, datos):
    """Las dos banderas son distintas a propósito: una protege a la
    persona, la otra abre una pregunta. Confundirlas es cobrarle a quien
    se portó bien."""
    servicio = _servicio(cliente, sesion, datos)
    _revisar(cliente, sesion, _cuerpo(
        servicio, datos, "recibe", hubo_dano=True, dano_tipo="rayon",
        dano_nota="Rayon en la puerta, asi me la entregaron",
        fotos=COMPLETAS + [GOLPE]))
    _revisar(cliente, sesion, _cuerpo(servicio, datos, "entrega", km=42_300,
                                      hubo_dano=False))

    unidad = cliente.get(f"/servicios/{servicio['id']}/revisiones",
                         headers=sesion("consultor")).json()["unidades"][0]
    assert unidad["ya_venia_danada"] is True
    assert unidad["dano_nuevo"] is False
    assert unidad["recibe"]["dano_tipo"] == "rayon"


def test_el_panorama_cuenta_las_que_volvieron_golpeadas(cliente, sesion,
                                                        datos):
    """El aviso al consultor, sin estado: no hay nada que "cerrar" aquí.
    Se ve, se entra al servicio y se decide —clasificar una incidencia, o
    nada— que es de personas."""
    servicio = _servicio(cliente, sesion, datos)
    antes = cliente.get("/panorama", headers=sesion("consultor")).json()
    partida = antes["calidad"]["unidades_con_dano_nuevo"]

    _revisar(cliente, sesion, _cuerpo(servicio, datos, "recibe",
                                      hubo_dano=False))
    _revisar(cliente, sesion, _cuerpo(
        servicio, datos, "entrega", km=42_300, hubo_dano=True,
        dano_tipo="llanta", dano_nota="Ponchadura en la llanta trasera derecha",
        fotos=COMPLETAS + [GOLPE]))

    despues = cliente.get("/panorama", headers=sesion("consultor")).json()
    assert despues["calidad"]["unidades_con_dano_nuevo"] == partida + 1

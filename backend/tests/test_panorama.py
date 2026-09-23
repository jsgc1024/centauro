"""Panorama: el estado de la operacion, para quien decide.

Lo que se prueba aqui no es que la pantalla pinte bonito. Es que diga la
verdad el dia que todo esta bien —de eso depende que alguien le crea el
dia que no— y que mida el silencio con el mismo numero que la central.
Durante un tiempo la central decia 60 minutos y esta pantalla 120, asi
que un equipo podia estar en rojo para el operador y verse normal para
la direccion.
"""
from datetime import date, datetime, time, timedelta

from ayudas import (LEJOS, asignar, configurar_origen, crear_servicio,
                    jornada, marcar)

HOY = date.today()


def _momento(hora=12, minuto=0):
    return datetime.combine(HOY, time(hora, minuto))


def _servicio_hoy(cliente, h, datos, hora="07:00:00", tipo="eventual",
                  consultor_id=None):
    return crear_servicio(
        cliente, h, datos,
        [jornada(HOY, datos["modalidades"]["full_day"]["id"], hora=hora)],
        tipo=tipo, consultor_id=consultor_id)


def _panorama(cliente, h, ahora):
    r = cliente.get(f"/panorama?ahora={ahora.isoformat()}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _arrancar(cliente, h, hp, datos, servicio, persona_id, cuando):
    """Deja la jornada en curso con su llegada marcada a esa hora."""
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=persona_id)
    configurar_origen(cliente, h, j["id"])
    r = marcar(cliente, hp, j["id"], "llegada_origen", cuando)
    assert r.status_code in (200, 201), r.text
    return j


# ==================================================================
# El dia tranquilo
# ==================================================================

def test_un_dia_sin_nada_no_tiene_nada_que_atender(cliente, sesion, datos):
    """La pantalla se vacia cuando todo esta bien. Si estuviera siempre
    llena, nadie la leeria el dia que importa."""
    h = sesion("dirgeneral")
    p = _panorama(cliente, h, _momento())

    assert p["estado"]["nivel"] == "normal"
    assert p["estado"]["atender"] == []
    assert p["estado"]["mas"] == 0
    assert p["en_la_calle"]["personas"] == 0
    assert p["en_la_calle"]["todos_reportando"] is True


def test_el_umbral_de_silencio_es_el_mismo_que_el_de_la_central(cliente,
                                                                sesion, datos):
    from app import central

    h = sesion("dirgeneral")
    p = _panorama(cliente, h, _momento())
    assert p["umbral_silencio"] == central.SILENCIO_ROJO


# ==================================================================
# La gente en la calle
# ==================================================================

def test_cuenta_personas_y_no_folios(cliente, sesion, datos):
    """El negocio es cuidar gente. Un servicio con dos personas pesa dos
    personas y un solo folio."""
    h = sesion("consultor")
    hp = sesion("juan")
    servicio = _servicio_hoy(cliente, h, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    _arrancar(cliente, h, hp, datos, servicio, juan, _momento(11, 40))

    p = _panorama(cliente, sesion("dirgeneral"), _momento(12))
    calle = p["en_la_calle"]
    assert calle["personas"] == 1
    assert calle["servicios"] == 1
    assert calle["eventual"] == 1
    assert calle["implantado"] == 0
    # Con un solo equipo el ejecutivo se captura en el servicio y el
    # equipo lo hereda; si se leen nada mas los campos del equipo, esto
    # da cero.
    assert calle["ejecutivos"] == 1


def test_el_corte_por_pais_suma_lo_mismo_que_el_total(cliente, sesion, datos):
    h = sesion("consultor")
    hp = sesion("juan")
    servicio = _servicio_hoy(cliente, h, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    _arrancar(cliente, h, hp, datos, servicio, juan, _momento(11, 40))

    p = _panorama(cliente, sesion("dirgeneral"), _momento(12))
    assert sum(f["personas"] for f in p["paises"]) == p["en_la_calle"]["personas"]
    assert [f["pais"] for f in p["paises"]] == ["Mexico"]
    # Cada pais trae su hora, no la del contenedor.
    assert p["paises"][0]["hora_local"]


# ==================================================================
# El silencio
# ==================================================================

def test_un_equipo_callado_sube_al_rengon_de_arriba(cliente, sesion, datos):
    """A los 61 minutos, no a los 120: el mismo momento en que la central
    ya lo tiene en rojo."""
    h = sesion("consultor")
    hp = sesion("juan")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    # La hora de la marca no puede estar en el futuro: el candado la
    # cambiaria por la del servidor y el silencio medido despues saldria
    # de horas. Las 10:00 cuando ya pasaron; cuando no, hace un minuto.
    # Las distancias --treinta minutos y sesenta y uno-- son lo que esta
    # prueba mide, y esas no cambian.
    arranque = min(_momento(10, 0),
                   datetime.now().replace(second=0, microsecond=0)
                   - timedelta(minutes=1))
    # Y el servicio arranca a esa misma hora. Arrancaba a las 7:00, y
    # corrida de madrugada el panorama lo veia por arrancar, sin unidad,
    # y pedia atenderlo: la prueba media otra cosa que el silencio.
    servicio = _servicio_hoy(cliente, h, datos,
                             hora=arranque.strftime("%H:%M:00"))
    _arrancar(cliente, h, hp, datos, servicio, juan, arranque)

    hd = sesion("dirgeneral")

    tranquilo = _panorama(cliente, hd, arranque + timedelta(minutes=30))
    assert tranquilo["estado"]["nivel"] == "normal", tranquilo["estado"]

    callado = _panorama(cliente, hd, arranque + timedelta(minutes=61))
    cosas = callado["estado"]["atender"]
    assert [c["tipo"] for c in cosas] == ["silencio"]
    assert cosas[0]["servicio"] == servicio["folio"]
    assert cosas[0]["minutos_callado"] >= 60
    assert callado["estado"]["nivel"] == "grave"
    assert callado["en_la_calle"]["todos_reportando"] is False


# ==================================================================
# Lo que arranca sin estar listo
# ==================================================================

def test_lo_que_falta_viaja_en_clave_y_no_en_espanol(cliente, sesion, datos):
    """La consola habla tres idiomas: el motor manda 'unidad', no 'sin
    unidad', y cada idioma pone su palabra."""
    h = sesion("consultor")
    servicio = _servicio_hoy(cliente, h, datos, hora="13:00:00")

    p = _panorama(cliente, sesion("dirgeneral"), _momento(12))
    cosas = [c for c in p["estado"]["atender"] if c["tipo"] == "sin_listo"]
    assert cosas, p["estado"]
    suyo = next(c for c in cosas if c["servicio"] == servicio["folio"])
    assert set(suyo["faltas"]) <= {"personal", "confirmar", "unidad",
                                   "meet_and_greet"}
    assert "personal" in suyo["faltas"]


def test_quien_va_en_camino_ya_no_aparece_como_falta_de_confirmar(
        cliente, sesion, datos):
    """Ir manejando hacia el punto dice más que confirmar.

    La dirección veía "le falta confirmar al equipo" mientras la persona
    estaba en la carretera: la confirmación sólo se apagaba con el botón
    de Confirmar, y quien ya iba en camino nunca volvía a tocarlo. Un
    renglón rojo que miente enseña a ignorar los renglones rojos.
    """
    h = sesion("consultor")
    hp = sesion("juan")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = _servicio_hoy(cliente, h, datos, hora="13:00:00")
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)
    configurar_origen(cliente, h, j["id"])

    def faltas():
        p = _panorama(cliente, sesion("dirgeneral"), _momento(12))
        suyo = next((c for c in p["estado"]["atender"]
                     if c.get("jornada_id") == j["id"]), None)
        assert suyo is not None, p["estado"]
        return suyo["faltas"]

    assert "confirmar" in faltas()

    r = cliente.post(f"/campo/jornadas/{j['id']}/en-camino",
                     json=LEJOS, headers=hp)
    assert r.status_code == 200, r.text

    assert "confirmar" not in faltas()


def test_quien_ya_marco_su_llegada_tampoco_aparece_sin_confirmar(
        cliente, sesion, datos):
    """El caso que de verdad se ve feo: la persona parada en el punto,
    con su llegada marcada, y la dirección leyendo que falta confirmar.

    Pasaba siempre en un servicio de hoy para hoy: el aviso de la
    víspera nunca le tocó, así que nadie podía apagar ese renglón.
    """
    h = sesion("consultor")
    hp = sesion("juan")
    juan = datos["personal"]["Juan Ramirez"]["id"]

    # Anclado al reloj real, no a una hora fija del dia.
    #
    # `registrar_hito` no acepta marcas del futuro: si la hora que manda
    # el telefono va mas de dos minutos adelante de la del servidor, se
    # guarda la del servidor. Con una llegada escrita a las 12:30 fijas,
    # esta prueba pasaba por la tarde y fallaba por la manana --la marca
    # quedaba a la hora real y el panorama, leido en su reloj falso de
    # las 12:00, veia al equipo callado tres horas y sacaba la tarjeta de
    # silencio en vez de la de "le falta algo"--. Una prueba que depende
    # de la hora a la que se corre no prueba nada.
    ahora = datetime.now().replace(second=0, microsecond=0)
    llegada = ahora - timedelta(minutes=5)
    arranca = ahora + timedelta(hours=1)

    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(arranca.date(), datos["modalidades"]["full_day"]["id"],
                 hora=arranca.strftime("%H:%M:%S"))])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)
    configurar_origen(cliente, h, j["id"])

    def faltas():
        p = _panorama(cliente, sesion("dirgeneral"), ahora)
        suyo = next((c for c in p["estado"]["atender"]
                     if c.get("jornada_id") == j["id"]), None)
        assert suyo is not None, p["estado"]
        # Con la tarjeta entera en el mensaje: un KeyError suelto no dice
        # cual de los tres tipos de tarjeta salio, que es justo el dato.
        assert "faltas" in suyo, suyo
        return suyo["faltas"]

    assert "confirmar" in faltas()

    r = marcar(cliente, hp, j["id"], "llegada_origen", llegada)
    assert r.status_code in (200, 201), r.text

    assert "confirmar" not in faltas()


# ==================================================================
# La calidad del reporte
# ==================================================================

def test_un_intento_de_marcar_lejos_del_punto_queda_contado(cliente, sesion,
                                                           datos):
    """El sistema no deja marcar la llegada desde tres kilometros: la
    rechaza de plano. Pero el intento queda anotado, y eso es justo lo
    que la direccion nunca ve, porque hoy solo sale al cerrar el
    servicio, uno por uno."""
    h = sesion("consultor")
    hp = sesion("juan")
    servicio = _servicio_hoy(cliente, h, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    asignar(cliente, h, j["id"], persona_id=juan)
    configurar_origen(cliente, h, j["id"])

    r = marcar(cliente, hp, j["id"], "llegada_origen", _momento(11, 40),
               ubicacion=LEJOS)
    assert r.status_code == 409, r.text

    hd = sesion("dirgeneral")
    p = _panorama(cliente, hd, _momento(12))
    assert p["calidad"]["intentos_fuera_de_geocerca"] == 1
    # La marca se rechazo, asi que nadie quedo en la calle.
    assert p["en_la_calle"]["personas"] == 0

    r = cliente.get(f"/panorama/marcas?ahora={_momento(12).isoformat()}",
                    headers=hd)
    assert r.status_code == 200, r.text
    intentos = r.json()["intentos_fuera_de_geocerca"]
    assert len(intentos) == 1
    assert intentos[0]["servicio"] == servicio["folio"]
    # El nombre es el punto: el hito rechazado no se guarda, asi que si
    # la alerta no lo carga, la direccion ve el intento y no tiene a
    # quien preguntarle.
    assert intentos[0]["persona"] == "Juan Ramirez"
    # Y el mensaje carga la distancia y el limite.
    assert "250" in intentos[0]["mensaje"]


# ==================================================================
# Quien ve que
# ==================================================================

def test_el_consultor_ve_toda_la_operacion_no_solo_la_suya(cliente, sesion,
                                                           datos):
    """A proposito, y no por descuido.

    Cualquier consultor puede trabajar la cartera de otro para cubrir una
    ausencia --asi esta hecho el sistema, y cada accion sobre un servicio
    ajeno queda marcada como cobertura--. Esconderle que el equipo de
    otro lleva dos horas callado seria lo contrario de para lo que sirve
    esta pantalla.
    """
    h = sesion("consultor")
    hp = sesion("juan")
    personas = cliente.get("/catalogos/personal", headers=sesion("admin")).json()
    ana = next(p for p in personas if p["nombre"].startswith("Ana"))
    beatriz = next(p for p in personas if p["nombre"].startswith("Beatriz"))

    de_ana = _servicio_hoy(cliente, h, datos, consultor_id=ana["id"])
    de_beatriz = _servicio_hoy(cliente, h, datos, hora="08:00:00",
                               consultor_id=beatriz["id"])
    juan = datos["personal"]["Juan Ramirez"]["id"]
    _arrancar(cliente, h, hp, datos, de_ana, juan, _momento(11, 40))

    esperados = {de_ana["folio"], de_beatriz["folio"]}
    for quien in ("dirgeneral", "consultor", "consultor2"):
        p = _panorama(cliente, sesion(quien), _momento(12))
        folios = {b["servicio"] for tira in p["dia"] for b in tira["barras"]}
        assert esperados <= folios, quien
        assert p["en_la_calle"]["personas"] == 1, quien


# ==================================================================
# La tira del dia
# ==================================================================

def test_la_tira_del_dia_va_por_pais_con_su_propia_hora(cliente, sesion, datos):
    """Un solo eje con Mexico y Brasil encima no querria decir nada: las
    14:00 de la tira son las 14:00 de donde esta parado el equipo."""
    h = sesion("consultor")
    servicio = _servicio_hoy(cliente, h, datos)

    p = _panorama(cliente, sesion("dirgeneral"), _momento(12))
    assert len(p["dia"]) == 1
    tira = p["dia"][0]
    assert tira["pais"] == "Mexico"
    assert tira["ahora"]
    barra = next(b for b in tira["barras"]
                 if b["servicio"] == servicio["folio"])
    assert barra["inicio"].endswith("07:00:00")
    assert barra["estatus"] in ("planeada", "confirmada", "proxima_a_iniciar")

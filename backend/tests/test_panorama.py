"""Panorama: el estado de la operacion, para quien decide.

Lo que se prueba aqui no es que la pantalla pinte bonito. Es que diga la
verdad el dia que todo esta bien —de eso depende que alguien le crea el
dia que no— y que mida el silencio con el mismo numero que la central.
Durante un tiempo la central decia 60 minutos y esta pantalla 120, asi
que un equipo podia estar en rojo para el operador y verse normal para
la direccion.
"""
from datetime import date, datetime, time

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
    servicio = _servicio_hoy(cliente, h, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    _arrancar(cliente, h, hp, datos, servicio, juan, _momento(10, 0))

    hd = sesion("dirgeneral")

    tranquilo = _panorama(cliente, hd, _momento(10, 30))
    assert tranquilo["estado"]["nivel"] == "normal", tranquilo["estado"]

    callado = _panorama(cliente, hd, _momento(11, 1))
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
    # El mensaje de la alerta carga la distancia y el limite, que es lo
    # unico que queda: el hito rechazado no guarda a quien lo intento.
    assert "250" in intentos[0]["mensaje"]


# ==================================================================
# Quien ve que
# ==================================================================

def test_el_consultor_solo_ve_su_cartera(cliente, sesion, datos):
    """La misma pantalla, recortada. La direccion ve las dos."""
    h = sesion("consultor")
    hp = sesion("juan")
    personas = cliente.get("/catalogos/personal", headers=sesion("admin")).json()
    ana = next(p for p in personas if p["nombre"].startswith("Ana"))
    beatriz = next(p for p in personas if p["nombre"].startswith("Beatriz"))

    mio = _servicio_hoy(cliente, h, datos, consultor_id=ana["id"])
    ajeno = _servicio_hoy(cliente, h, datos, hora="08:00:00",
                          consultor_id=beatriz["id"])
    juan = datos["personal"]["Juan Ramirez"]["id"]
    _arrancar(cliente, h, hp, datos, mio, juan, _momento(11, 40))

    direccion = _panorama(cliente, sesion("dirgeneral"), _momento(12))
    folios = {b["servicio"] for tira in direccion["dia"] for b in tira["barras"]}
    assert {mio["folio"], ajeno["folio"]} <= folios

    suyo = _panorama(cliente, sesion("consultor2"), _momento(12))
    folios2 = {b["servicio"] for tira in suyo["dia"] for b in tira["barras"]}
    assert mio["folio"] not in folios2
    assert ajeno["folio"] in folios2


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

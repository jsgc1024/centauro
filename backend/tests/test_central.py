"""La central de inteligencia.

Lo que se prueba aqui no es que la pantalla pinte: es que la vispera se
calcule bien. Una central que dice "todo listo" cuando falta la unidad
es peor que no tener pantalla, porque alguien le cree.
"""
from datetime import date, datetime, time, timedelta

from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana)


def _mediodia(dia: date) -> datetime:
    return datetime.combine(dia, time(12, 0))


def _servicio_de_manana(cliente, h, datos, hora_inicio="09:00:00"):
    """Un eventual que arranca manana, sin nada mas puesto."""
    return crear_servicio(cliente, h, datos, [jornada(
        date.today() + timedelta(days=1),
        datos["modalidades"]["full_day"]["id"], hora=hora_inicio)])


def _claves(ficha):
    return {p["clave"]: p["listo"] for p in ficha["revision"]}


def test_manana_ordena_por_la_hora_en_que_llega_el_equipo(cliente, sesion,
                                                          datos):
    """La hora que se puede perder no es la del servicio: es la de la
    presentacion del equipo, media hora antes."""
    h = sesion("consultor")
    tarde = _servicio_de_manana(cliente, h, datos, "14:00:00")
    temprano = _servicio_de_manana(cliente, h, datos, "07:00:00")

    r = cliente.get("/central/manana", headers=h)
    assert r.status_code == 200, r.text
    fichas = r.json()["servicios"]
    folios = [f["folio"] for f in fichas]
    assert folios.index(temprano["folio"]) < folios.index(tarde["folio"])

    suyo = next(f for f in fichas if f["folio"] == temprano["folio"])
    # 07:00 de servicio, el equipo esta parado a las 06:30.
    assert suyo["equipo_llega"].endswith("06:30:00")
    assert suyo["anticipacion_minutos"] == 30
    assert suyo["contra_vuelo"] is False


def test_un_dia_sin_nada_dice_todo_lo_que_le_falta(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = _servicio_de_manana(cliente, h, datos)

    ficha = next(f for f in cliente.get("/central/manana", headers=h).json()
                 ["servicios"] if f["folio"] == servicio["folio"])
    assert ficha["listo"] is False
    listo = _claves(ficha)
    assert listo["punto_de_encuentro"] is False
    assert listo["personal"] is False
    assert listo["unidad"] is False
    assert listo["hoja"] is False

    # Y cada renglon dice que hacer, no "pendiente".
    for p in ficha["revision"]:
        if not p["listo"]:
            assert p["que_hacer"], p


def test_asignar_sin_confirmar_no_cuenta_como_listo(cliente, sesion, datos):
    """Que alguien este asignado no quiere decir que sepa que manana
    trabaja. Son dos cosas y la vispera las distingue."""
    h = sesion("consultor")
    servicio = _servicio_de_manana(cliente, h, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])

    ficha = next(f for f in cliente.get("/central/manana", headers=h).json()
                 ["servicios"] if f["folio"] == servicio["folio"])
    listo = _claves(ficha)
    assert listo["personal"] is True
    assert listo["unidad"] is True
    assert listo["punto_de_encuentro"] is True
    assert listo["confirmacion"] is False, "nadie confirmo y dice que si"
    assert listo["rol"] is True, "el rol lo puso el helper"


def test_el_corte_de_la_vispera_cambia_lo_que_es_urgente(cliente, sesion,
                                                         datos):
    """Antes del corte, lo que falta es trabajo del dia. Despues, es un
    problema de esta noche y sube a la banda roja."""
    from app import central as motor
    from app.db import SessionLocal

    h = sesion("consultor")
    _servicio_de_manana(cliente, h, datos)

    db = SessionLocal()
    try:
        temprano = datetime.combine(date.today(), time(10, 0))
        tarde = datetime.combine(date.today(), time(21, 0))

        antes = motor.tablero(db, temprano)
        assert antes["paso_el_corte"] is False
        assert antes["roto"]["manana_vencido"] == []

        despues = motor.tablero(db, tarde)
        assert despues["paso_el_corte"] is True
        assert despues["roto"]["manana_vencido"], "el corte no levanto nada"
        assert despues["roto"]["hay"] is True
    finally:
        db.close()


def test_el_silencio_se_mide_contra_el_ultimo_hito(cliente, sesion, datos):
    from app import central as motor

    assert motor._color_del_silencio(None) == "sin_reporte"
    assert motor._color_del_silencio(5) == "verde"
    assert motor._color_del_silencio(motor.SILENCIO_AMBAR) == "ambar"
    assert motor._color_del_silencio(motor.SILENCIO_ROJO) == "rojo"


def test_la_tira_de_dias_cuenta_lo_que_viene(cliente, sesion, datos):
    h = sesion("consultor")
    _servicio_de_manana(cliente, h, datos)

    tablero = cliente.get("/central/tablero", headers=h).json()
    tira = tablero["semana"]
    assert len(tira) == 7
    assert tira[0]["fecha"] == date.today().isoformat()

    manana_ = tira[1]
    assert manana_["servicios"] >= 1
    # Recien creado no tiene ni gente ni punto: cuenta como incompleto.
    assert manana_["incompletos"] >= 1


def test_la_banda_roja_no_existe_cuando_no_hay_nada(cliente, sesion, datos):
    """Una franja que siempre dice 'todo bien' deja de leerse."""
    from app import central as motor
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        temprano = datetime.combine(date.today(), time(10, 0))
        assert motor.tablero(db, temprano)["roto"]["hay"] is False
    finally:
        db.close()

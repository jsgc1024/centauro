# -*- coding: utf-8 -*-
"""La bitácora deja de ser solo lectura.

Tres cosas se capturan desde ahí, y ninguna más: la **nota de turno**,
que es lo único que no tenía casa en ningún lado; la **corrección de la
hora de una marca**, que el servidor sabía hacer desde hace tiempo y que
ninguna pantalla alcanzaba; y **la hora de mañana**, dicha al cerrar el
día de hoy.

Lo que deliberadamente NO se captura desde aquí: cerrar el día a mano.
Ese camino ya existe y hace más cosas que poner un hito —fija el fin
real, cierra la jornada y abre el plazo de comprobación—. Dos puertas
para la misma escritura son dos lugares donde mantener las mismas
reglas.
"""
from datetime import datetime, timedelta

from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana, marcar)

PUNTO = "Las Alcobas, Polanco - lobby"


def _servicio(cliente, sesion, datos, dias=1, atras=1):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(-atras + i), datos["modalidades"]["full_day"]["id"],
                 origen_direccion=PUNTO)
         for i in range(dias)])
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        configurar_origen(cliente, h, j["id"])
    return servicio


def _dia(cliente, sesion, jornada_id, quien="central"):
    r = cliente.get(f"/operacion/jornadas/{jornada_id}/dia",
                    headers=sesion(quien))
    assert r.status_code == 200, r.text
    return r.json()


# ======================================================= la nota de turno

def test_la_nota_queda_firmada_y_sale_en_la_bitacora(cliente, sesion, datos):
    """Lo que la central averigua por teléfono vivía en la cabeza de
    quien contestó. El turno siguiente no lo heredaba."""
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    r = cliente.post(f"/operacion/jornadas/{j['id']}/notas",
                     headers=sesion("central"),
                     json={"texto": "Hablé con Juan, hay manifestación en "
                                    "Reforma, llega 20 minutos tarde"})
    assert r.status_code == 201, r.text
    assert r.json()["persona"], "la nota va firmada con quien la escribió"

    d = _dia(cliente, sesion, j["id"])
    suya = next(x for x in d["renglones"] if x["fuente"] == "nota")
    assert "manifestación" in suya["detalle"]
    assert suya["titulo"], "el título de una nota es el nombre de quien la puso"
    assert suya["momento"], "y lleva la hora en que se supo"


def test_el_consultor_puede_anotar(cliente, sesion, datos):
    """Decisión de Salvador: quien pueda ver el día puede escribir en él.
    Una nota no toca lo que se factura ni lo que se paga. Y es al
    consultor a quien le llama el cliente: si no pudiera escribir lo que
    le dijeron, ese dato no entraría nunca."""
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    r = cliente.post(f"/operacion/jornadas/{j['id']}/notas",
                     headers=sesion("consultor"),
                     json={"texto": "El cliente avisa que se extiende "
                                    "hasta las 22:00"})
    assert r.status_code == 201, r.text


def test_una_nota_vacia_no_es_una_nota(cliente, sesion, datos):
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    r = cliente.post(f"/operacion/jornadas/{j['id']}/notas",
                     headers=sesion("central"), json={"texto": "ok"})
    assert r.status_code == 422, r.text


# ==================================================== la hora de mañana

def test_la_hora_de_manana_mueve_el_dia_siguiente_de_ese_equipo(
        cliente, sesion, datos):
    """El principal lo dice al cerrar el día de hoy, y quien lo escucha
    es la central."""
    servicio = _servicio(cliente, sesion, datos, dias=2, atras=1)
    hoy, manana_ = servicio["equipos"][0]["jornadas"]

    r = cliente.post(f"/operacion/jornadas/{hoy['id']}/hora-de-manana",
                     headers=sesion("central"),
                     json={"hora": "06:30:00",
                           "nota": "Lo pidió el principal al cerrar"})
    assert r.status_code == 200, r.text
    assert r.json()["jornada_id"] == manana_["id"]
    assert r.json()["inicio"].endswith("06:30:00")

    # Y queda contado en la bitácora del día en que se supo, que es hoy
    # y no mañana: lo que se registra es que el principal lo dijo.
    d = _dia(cliente, sesion, hoy["id"])
    notas = [x["detalle"] for x in d["renglones"] if x["fuente"] == "nota"]
    assert any("06:30" in n for n in notas), notas


def test_el_consultor_no_fija_la_hora_de_manana(cliente, sesion, datos):
    """Candado de central y dirección, decisión de Salvador: se usa a
    deshoras y sobre un día que ya tiene gente confirmada."""
    servicio = _servicio(cliente, sesion, datos, dias=2, atras=1)
    hoy = servicio["equipos"][0]["jornadas"][0]

    r = cliente.post(f"/operacion/jornadas/{hoy['id']}/hora-de-manana",
                     headers=sesion("consultor"), json={"hora": "06:30:00"})
    assert r.status_code == 403, r.text


def test_sin_dia_siguiente_no_hay_hora_de_manana(cliente, sesion, datos):
    """Y lo dice con lo que hay que hacer, en vez de fallar callado."""
    servicio = _servicio(cliente, sesion, datos, dias=1)
    j = servicio["equipos"][0]["jornadas"][0]

    r = cliente.post(f"/operacion/jornadas/{j['id']}/hora-de-manana",
                     headers=sesion("central"), json={"hora": "06:30:00"})
    assert r.status_code == 409, r.text
    assert "que_hacer" in r.json()["detail"]


# ================================================ las marcas a mano

def test_el_contacto_a_mano_pide_primero_la_llegada(cliente, sesion, datos):
    """El orden manda también cuando la marca la pone la central: un
    contacto con el ejecutivo sin haber llegado cuenta una historia que
    no ocurrió, y la app no lo permitiría."""
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    arranca = datetime.fromisoformat(j["inicio_programado"])

    r = cliente.post(f"/operacion/jornadas/{j['id']}/marca-a-mano",
                     headers=sesion("central"),
                     json={"tipo": "contacto_ejecutivo",
                           "persona_id": datos["personal"]["Juan Ramirez"]["id"],
                           "momento": arranca.isoformat(),
                           "justificacion": "el cliente confirmó por teléfono"})
    assert r.status_code == 409, r.text

    # Con la llegada asentada primero, sí pasa.
    for tipo, cuando in (("llegada_origen", arranca - timedelta(minutes=10)),
                         ("contacto_ejecutivo", arranca)):
        r = cliente.post(f"/operacion/jornadas/{j['id']}/marca-a-mano",
                         headers=sesion("central"),
                         json={"tipo": tipo,
                               "persona_id":
                                   datos["personal"]["Juan Ramirez"]["id"],
                               "momento": cuando.isoformat(),
                               "justificacion": "se quedaron sin batería"})
        assert r.status_code == 200, (tipo, r.text)


def test_el_fin_del_dia_no_se_pone_por_esta_puerta(cliente, sesion, datos):
    """Ese camino ya existe —cerrar el día a mano— y hace más cosas que
    poner un hito. Y la respuesta dice cuál es la puerta buena."""
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    r = cliente.post(f"/operacion/jornadas/{j['id']}/marca-a-mano",
                     headers=sesion("central"),
                     json={"tipo": "fin_servicio",
                           "persona_id": datos["personal"]["Juan Ramirez"]["id"],
                           "momento": j["fin_programado"],
                           "justificacion": "se les pasó marcar el fin"})
    assert r.status_code == 422, r.text

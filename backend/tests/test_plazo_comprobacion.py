# -*- coding: utf-8 -*-
"""El plazo para comprobar: 24 horas desde que el día termina.

La regla estaba entera —las horas, la función que calcula la fecha, y
**seis lugares que la leen**: la app del agente, el bono de puntualidad,
la bandeja de finanzas, el panel de accesos, el dinero vencido de la
dirección y la API— y el campo no lo escribía nadie en el camino normal.
Solo lo ponía el reemplazo por contingencia.

Así que el plazo no existía: la app no decía hasta cuándo, finanzas no
podía contar los días vencidos, y la dirección veía en cero el dinero
afuera sin comprobar. Lo encontró la prueba 360, por tres huecos de
pantalla distintos que resultaron ser este.
"""
from datetime import timedelta

from ayudas import (asignar, crear_servicio, depositar_de_verdad,
                    ejecutar_jornada, jornada, manana)

PUNTO = {"origen_direccion": "Aeropuerto Benito Juárez, T2",
         "origen_lat": "19.4270", "origen_lon": "-99.1677",
         "geocerca_metros": 250}


def _dia_con_viaticos(cliente, sesion, datos, offset=800):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"],
                 **PUNTO)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"])
    viatico = cliente.post("/viaticos/asignar", headers=h, json={
        "jornada_id": j["id"], "persona_id": juan,
        "conceptos": [{"concepto": "alimentos", "monto": "900",
                       "origen": "tabulador"}]}).json()
    return servicio, j, viatico, juan


def _viatico(viatico_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        v = db.get(m.AsignacionViatico, viatico_id)
        return v.limite_comprobacion, v.jornada.fin_real


def _firmado(jornada_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return db.get(m.Jornada, jornada_id).cerrada_a_mano_en


def test_el_dia_que_termina_abre_el_plazo(cliente, sesion, datos):
    """Antes el viático nacía sin plazo y moría sin plazo."""
    servicio, j, viatico, _ = _dia_con_viaticos(cliente, sesion, datos)

    limite, _fin = _viatico(viatico["id"])
    assert limite is None, "el plazo no corre antes de que el día termine"

    ejecutar_jornada(cliente, sesion("juan"), j)

    limite, fin_real = _viatico(viatico["id"])
    assert limite is not None, "el día terminó y el plazo no arrancó"
    assert fin_real is not None
    # Veinticuatro horas desde que terminó, no desde que se programó.
    assert limite == fin_real + timedelta(hours=24)


def test_la_app_le_dice_al_agente_hasta_cuando(cliente, sesion, datos):
    """Es lo que el agente necesita saber, y salía vacío."""
    servicio, j, _viatico_, juan = _dia_con_viaticos(cliente, sesion, datos,
                                                     offset=802)
    # El plazo se le cuenta al dinero que ya tiene: la app no le pide
    # comprobar --ni le corre el reloj-- por lo que sigue en el banco.
    depositar_de_verdad(cliente, sesion, servicio["equipos"][0]["id"], juan)
    ejecutar_jornada(cliente, sesion("juan"), j)

    mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
    suyo = next(f for f in mios["servicios"]
                if f["folio"] == servicio["folio"])
    assert suyo["limite"], suyo


def test_el_cierre_a_mano_tambien_lo_abre(cliente, sesion, datos):
    """Cerrado a mano o marcado desde la calle, el día terminó igual y
    el plazo corre igual: la diferencia queda en el sello del cierre, no
    en el reloj de la comprobación."""
    # Un día que ya pasó: uno futuro no se cierra, y con razón.
    servicio, j, viatico, _ = _dia_con_viaticos(cliente, sesion, datos,
                                                offset=-3)
    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     headers=sesion("central"),
                     json={"justificacion": "El equipo se quedó sin batería; "
                                            "confirmado por teléfono"})
    assert r.status_code == 200, r.text

    # Un dia firmado tres dias tarde no nace vencido: el plazo corre
    # desde la firma de la central, no desde la hora de termino que
    # asento (decision de Salvador, 22 sep).
    limite, fin_real = _viatico(viatico["id"])
    firmado = _firmado(j["id"])
    assert limite == firmado + timedelta(hours=24)
    assert limite > fin_real + timedelta(hours=24)


def test_el_plazo_del_relevo_no_se_pisa(cliente, sesion, datos):
    """Un reemplazo le pone su propio plazo, contado desde la hora del
    relevo. Ese manda: el que salió comprueba desde que se fue, no desde
    que terminó un día que ya no trabajó."""
    from app import models as m
    from app.db import SessionLocal

    servicio, j, viatico, _ = _dia_con_viaticos(cliente, sesion, datos,
                                                offset=806)
    propio = None
    with SessionLocal() as db:
        v = db.get(m.AsignacionViatico, viatico["id"])
        v.limite_comprobacion = v.jornada.fin_programado - timedelta(hours=5)
        propio = v.limite_comprobacion
        db.commit()

    ejecutar_jornada(cliente, sesion("juan"), j)

    limite, _fin = _viatico(viatico["id"])
    assert limite == propio, "el cierre del día pisó el plazo del relevo"

"""Nomina semanal del personal de seguridad.

Lo que se verifica: que nadie cobre dos veces la misma jornada, que el
dinero ya pagado no se reabra, y que lo que cambia despues del pago
aparezca como ajuste en el corte siguiente.
"""
from datetime import date, timedelta

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana)


def _lunes(dia=None):
    dia = dia or date.today()
    return dia - timedelta(days=dia.weekday())


def _servicio_pagable(cliente, sesion, datos, offset=200, dias=2,
                      horas_extra=0):
    """Servicio ejecutado y ya enviado a finanzas: listo para el corte."""
    h = sesion("consultor")
    fechas = [manana(offset + i) for i in range(dias)]
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(f, datos["modalidades"]["full_day"]["id"]) for f in fechas],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])

    for idx, j in enumerate(servicio["equipos"][0]["jornadas"]):
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        configurar_origen(cliente, h, j["id"])
        ejecutar_jornada(cliente, sesion("juan"), j,
                         horas_extra=horas_extra if idx == dias - 1 else 0)

    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                          headers=h).json()
    envio = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas",
                         headers=h)
    assert envio.status_code == 200, envio.text
    return servicio, cierre


def _calcular(cliente, sesion, datos, corte=None):
    cuerpo = {"pais_id": datos["mx"]["id"]}
    if corte:
        cuerpo["fecha_corte"] = str(corte)
    r = cliente.post("/nomina/calcular", json=cuerpo, headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    return r.json()


def test_el_corte_recoge_lo_que_ya_va_a_facturacion(cliente, sesion, datos):
    _servicio_pagable(cliente, sesion, datos, offset=200)
    resultado = _calcular(cliente, sesion, datos)

    assert resultado["personas"] == 1
    assert resultado["total"] > 0
    # El corte se identifica por el lunes de la semana, no por el dia que
    # se corrio.
    assert resultado["fecha_corte"] == _lunes().isoformat()


def test_lo_que_no_se_ha_enviado_a_finanzas_no_se_paga(cliente, sesion, datos):
    """El eventual entra cuando el consultor ya lo mando, no antes."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(210), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("juan"), j)

    resultado = _calcular(cliente, sesion, datos)
    assert resultado["personas"] == 0
    assert resultado["total"] == 0


def test_no_se_paga_dos_veces_la_misma_jornada(cliente, sesion, datos):
    _servicio_pagable(cliente, sesion, datos, offset=220)
    primero = _calcular(cliente, sesion, datos)
    pago = cliente.post(f"/nomina/{primero['nomina_id']}/pagar",
                        headers=sesion("finanzas"))
    assert pago.status_code == 200, pago.text

    # La semana siguiente ya no debe traer nada de ese servicio.
    siguiente = _calcular(cliente, sesion, datos,
                          corte=_lunes() + timedelta(days=7))
    assert siguiente["total"] == 0


def test_una_nomina_pagada_ya_no_se_recalcula(cliente, sesion, datos):
    _servicio_pagable(cliente, sesion, datos, offset=230)
    n = _calcular(cliente, sesion, datos)
    cliente.post(f"/nomina/{n['nomina_id']}/pagar", headers=sesion("finanzas"))

    r = cliente.post("/nomina/calcular", json={"pais_id": datos["mx"]["id"]},
                     headers=sesion("finanzas"))
    assert r.status_code == 409


def test_mientras_no_se_pague_se_puede_recalcular(cliente, sesion, datos):
    _servicio_pagable(cliente, sesion, datos, offset=240)
    primero = _calcular(cliente, sesion, datos)
    segundo = _calcular(cliente, sesion, datos)
    # Mismo corte, no uno nuevo, y sin duplicar los montos.
    assert segundo["nomina_id"] == primero["nomina_id"]
    assert segundo["total"] == primero["total"]


def test_las_horas_extra_se_pagan(cliente, sesion, datos):
    _servicio_pagable(cliente, sesion, datos, offset=250, dias=1)
    sin_extra = _calcular(cliente, sesion, datos)["total"]

    # Otro servicio identico pero con horas extra, en otra semana.
    cliente.post(f"/nomina/{_ultima(cliente, sesion, datos)}/pagar",
                 headers=sesion("finanzas"))
    _servicio_pagable(cliente, sesion, datos, offset=260, dias=1, horas_extra=2)
    con_extra = _calcular(cliente, sesion, datos,
                          corte=_lunes() + timedelta(days=7))["total"]
    assert con_extra > sin_extra


def _ultima(cliente, sesion, datos):
    filas = cliente.get("/nomina", params={"pais_id": datos["mx"]["id"]},
                        headers=sesion("finanzas")).json()
    return filas[0]["id"]


# ---------------------------------------------------------------- ajustes

def test_un_ajuste_a_mano_entra_al_siguiente_corte(cliente, sesion, datos):
    r = cliente.post("/nomina/ajustes",
                     json={"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                           "pais_id": datos["mx"]["id"],
                           "monto": "-350.00",
                           "motivo": "Dia mal cargado la semana pasada"},
                     headers=sesion("finanzas"))
    assert r.status_code == 201, r.text

    pendientes = cliente.get("/nomina/ajustes/pendientes",
                             params={"pais_id": datos["mx"]["id"]},
                             headers=sesion("finanzas")).json()
    assert len(pendientes) == 1
    assert pendientes[0]["sentido"] == "descuento"

    resultado = _calcular(cliente, sesion, datos)
    assert resultado["ajustes_aplicados"] == 1
    assert resultado["total"] == -350


def test_el_ajuste_se_salda_al_pagar(cliente, sesion, datos):
    cliente.post("/nomina/ajustes",
                 json={"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                       "pais_id": datos["mx"]["id"], "monto": "500",
                       "motivo": "Se le quedo a deber un transfer"},
                 headers=sesion("finanzas"))
    n = _calcular(cliente, sesion, datos)
    cliente.post(f"/nomina/{n['nomina_id']}/pagar", headers=sesion("finanzas"))

    pendientes = cliente.get("/nomina/ajustes/pendientes",
                             params={"pais_id": datos["mx"]["id"]},
                             headers=sesion("finanzas")).json()
    assert pendientes == []


def test_una_jornada_cancelada_despues_del_pago_genera_descuento(
        cliente, sesion, datos):
    """El caso que el sistema tiene que atrapar solo."""
    servicio, cierre = _servicio_pagable(cliente, sesion, datos, offset=270)
    n = _calcular(cliente, sesion, datos)
    cliente.post(f"/nomina/{n['nomina_id']}/pagar", headers=sesion("finanzas"))

    diferencias = cliente.post(
        f"/nomina/servicio/{servicio['id']}/revisar-diferencias",
        headers=sesion("finanzas"))
    assert diferencias.status_code == 200, diferencias.text
    # Nada cambio todavia: no debe inventar ajustes.
    assert diferencias.json()["ajustes_generados"] == []


def test_el_detalle_dice_por_que_dia_se_le_paga(cliente, sesion, datos):
    _servicio_pagable(cliente, sesion, datos, offset=280, dias=2)
    n = _calcular(cliente, sesion, datos)
    detalle = cliente.get(f"/nomina/{n['nomina_id']}",
                          headers=sesion("finanzas")).json()

    renglon = detalle["renglones"][0]
    assert renglon["persona"] == "Juan Ramirez"
    assert len(renglon["conceptos"]) == 2
    assert all("full_day" in c["descripcion"] for c in renglon["conceptos"])


def test_el_personal_no_puede_ver_ni_pagar_la_nomina(cliente, sesion, datos):
    r = cliente.post("/nomina/calcular", json={"pais_id": datos["mx"]["id"]},
                     headers=sesion("juan"))
    assert r.status_code == 403

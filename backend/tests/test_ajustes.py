"""Los ajustes de nomina: que la correccion se haga una vez y bien.

Un ajuste es la unica forma de corregir un pago que ya salio. Si se
genera de mas, se paga de mas; si se tapa, alguien trabajo y no cobra.
Las dos cosas pasaban.

El origen de las dos era el mismo: `AjusteNomina` no decia de que era.
Corregir lo que se pago por un dia y descontar viaticos que no se
comprobaron son cosas distintas que compartian la llave (jornada,
persona), asi que se pisaban.
"""
from datetime import date, timedelta
from decimal import Decimal

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana)


def _lunes(dia=None):
    dia = dia or date.today()
    return dia - timedelta(days=dia.weekday())


def _dia_pagado(cliente, sesion, datos, offset=300):
    """Un dia trabajado, enviado a finanzas y ya pagado en un corte."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])

    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("juan"), j)

    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                          headers=h).json()
    envio = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas",
                         headers=h)
    assert envio.status_code == 200, envio.text

    # El corte del dia trabajado se paga en su propia semana, para que
    # la semana en curso quede libre: es donde van a caer los ajustes.
    f = sesion("finanzas")
    r = cliente.post("/nomina/calcular", headers=f,
                     json={"pais_id": datos["mx"]["id"],
                           "fecha_corte": str(_lunes() - timedelta(days=14))})
    assert r.status_code == 200, r.text
    pagado = cliente.post(f"/nomina/{r.json()['nomina_id']}/pagar", headers=f)
    assert pagado.status_code == 200, pagado.text

    return (servicio, j, datos["personal"]["Juan Ramirez"]["id"],
            datos["mx"]["id"])


def _pendientes(cliente, sesion, pais_id):
    r = cliente.get(f"/nomina/ajustes/pendientes?pais_id={pais_id}",
                    headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    return r.json()


def _ajuste(cliente, sesion, **campos):
    r = cliente.post("/nomina/ajustes", headers=sesion("finanzas"),
                     json=campos)
    assert r.status_code == 201, r.text
    return r.json()


def test_la_misma_diferencia_no_se_arrastra_dos_veces(cliente, sesion, datos):
    """Era el error mas caro de todos.

    `_pagado_de` solo miraba el concepto del dia, y los ajustes se
    guardan aparte. Una vez pagado el ajuste, la siguiente corrida
    volvia a ver "se pago 800, corresponde 1100" y generaba otros 300.
    Cada vez que el servicio se movia, 300 mas, para siempre.
    """
    servicio, j, juan, pais_id = _dia_pagado(cliente, sesion, datos)
    h = sesion("finanzas")

    _ajuste(cliente, sesion, persona_id=juan, pais_id=pais_id,
            servicio_id=servicio["id"], jornada_id=j["id"],
            concepto="correccion_jornada", monto="300",
            motivo="Horas extra que no se habian cargado")
    assert len(_pendientes(cliente, sesion, pais_id)) == 1

    # Se paga el ajuste, en el corte de esta semana.
    r = cliente.post("/nomina/calcular", headers=h,
                     json={"pais_id": pais_id, "fecha_corte": str(_lunes())})
    assert r.status_code == 200, r.text
    cliente.post(f"/nomina/{r.json()['nomina_id']}/pagar", headers=h)
    assert _pendientes(cliente, sesion, pais_id) == []

    # Y aqui estaba el agujero: volver a revisar el servicio generaba
    # otra vez la misma diferencia, y otra, y otra.
    for _ in range(2):
        cliente.post(f"/nomina/servicio/{servicio['id']}/revisar-diferencias",
                     headers=h)
    despues = _pendientes(cliente, sesion, pais_id)
    assert despues == [], f"se volvio a generar: {despues}"


def test_un_descuento_de_viaticos_no_tapa_la_correccion_del_dia(cliente, sesion,
                                                                datos):
    """Son dos cosas distintas que caian en la misma llave. El descuento
    hacia que la correccion de nomina de ese dia nunca se generara, y no
    quedaba rastro de la omision."""
    servicio, j, juan, pais_id = _dia_pagado(cliente, sesion, datos)

    _ajuste(cliente, sesion, persona_id=juan, pais_id=pais_id,
            servicio_id=servicio["id"], jornada_id=j["id"],
            concepto="viatico_no_comprobado", monto="-600",
            motivo="Viaticos sin comprobar")
    _ajuste(cliente, sesion, persona_id=juan, pais_id=pais_id,
            servicio_id=servicio["id"], jornada_id=j["id"],
            concepto="correccion_jornada", monto="200",
            motivo="Dos horas extra")

    pendientes = _pendientes(cliente, sesion, pais_id)
    assert len(pendientes) == 2, pendientes
    assert {p["concepto"] for p in pendientes} == {
        "viatico_no_comprobado", "correccion_jornada"}
    # Y cada uno se lee por lo que es, no por un codigo.
    assert {p["de_que"] for p in pendientes} == {
        "Viaticos sin comprobar", "Correccion del pago del dia"}


def test_un_ajuste_no_se_paga_en_dos_cortes(cliente, sesion, datos):
    """Dos borradores con fechas de corte distintas se llevaban el mismo
    ajuste, y al pagar los dos la persona cobraba la diferencia dos
    veces."""
    servicio, j, juan, pais_id = _dia_pagado(cliente, sesion, datos)
    h = sesion("finanzas")
    _ajuste(cliente, sesion, persona_id=juan, pais_id=pais_id,
            servicio_id=servicio["id"], jornada_id=j["id"],
            concepto="correccion_jornada", monto="1200",
            motivo="Diferencia de la semana pasada")

    a = cliente.post("/nomina/calcular", headers=h,
                     json={"pais_id": pais_id, "fecha_corte": str(_lunes())})
    assert a.status_code == 200, a.text
    b = cliente.post("/nomina/calcular", headers=h,
                     json={"pais_id": pais_id,
                           "fecha_corte": str(_lunes() + timedelta(days=7))})
    assert b.status_code == 200, b.text

    # El primero se lo llevo; el segundo no lo vuelve a tomar.
    assert Decimal(str(a.json()["total"])) >= Decimal("1200")
    assert Decimal(str(b.json()["total"])) < Decimal("1200")


def test_un_borrador_se_puede_tirar_y_suelta_lo_que_aparto(cliente, sesion,
                                                            datos):
    """Un borrador aparta. Sin forma de tirarlo, una corrida "para ver
    como queda" dejaba ese dinero retenido, y nada lo avisaba."""
    servicio, j, juan, pais_id = _dia_pagado(cliente, sesion, datos)
    h = sesion("finanzas")
    _ajuste(cliente, sesion, persona_id=juan, pais_id=pais_id,
            concepto="manual", monto="500", motivo="Apoyo de transporte")

    borrador = cliente.post(
        "/nomina/calcular", headers=h,
        json={"pais_id": pais_id, "fecha_corte": str(_lunes())}).json()

    r = cliente.delete(f"/nomina/{borrador['nomina_id']}", headers=h)
    assert r.status_code == 200, r.text

    # Y lo que tenia apartado vuelve a estar disponible.
    r = cliente.post("/nomina/calcular", headers=h,
                     json={"pais_id": pais_id,
                           "fecha_corte": str(_lunes() + timedelta(days=7))})
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["total"])) >= Decimal("500")


def test_una_nomina_pagada_no_se_tira(cliente, sesion, datos):
    """Lo que haya que corregir despues de pagar va como ajuste."""
    _, _, _, pais_id = _dia_pagado(cliente, sesion, datos)
    h = sesion("finanzas")
    cortes = cliente.get(f"/nomina?pais_id={pais_id}", headers=h).json()
    pagada = next(c for c in cortes if c["estatus"] == "pagada")
    r = cliente.delete(f"/nomina/{pagada['id']}", headers=h)
    assert r.status_code == 409, r.text

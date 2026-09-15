"""Los ajustes de nomina: que la correccion se haga una vez y bien.

Un ajuste es la unica forma de corregir un pago que ya salio. Si se
genera de mas, se paga de mas; si se tapa, alguien trabajo y no cobra.
Las dos cosas pasaban.

El origen de las dos era el mismo: `AjusteNomina` no decia de que era.
Corregir lo que se pago por un dia y descontar viaticos que no se
comprobaron son cosas distintas que compartian la llave (jornada,
persona), asi que se pisaban.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana)


def _lunes(dia=None):
    dia = dia or date.today()
    return dia - timedelta(days=dia.weekday())


def _dia_pagado(cliente, sesion, datos, offset=300):
    """Un dia trabajado, enviado a finanzas y ya pagado en un corte.

    El corte se paga con fecha de hace dos semanas para dejar libre la
    semana en curso: es donde van a caer los ajustes de las pruebas.
    """
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


def _ajuste(cliente, sesion, esperado=201, **campos):
    r = cliente.post("/nomina/ajustes", headers=sesion("finanzas"),
                     json=campos)
    assert r.status_code == esperado, r.text
    return r


def _alargar_el_dia(cliente, sesion, jornada_id, horas):
    """Mueve la marca de fin para que el dia salga con horas extra.

    Es el escenario que de verdad genera una correccion: el dia ya se
    pago, la central ajusta la hora de termino, y lo que corresponde
    sube. Inventar el ajuste a mano no prueba nada, porque el motor
    compara contra la tarifa y no contra lo que alguien tecleo.
    """
    h = sesion("central")
    b = cliente.get(f"/operacion/jornadas/{jornada_id}/bitacora",
                    headers=h).json()
    fin = next(x for x in b["hitos"] if x["tipo"] == "fin_servicio")
    nuevo = datetime.fromisoformat(fin["marcado_en"]) + timedelta(hours=horas)
    r = cliente.post(f"/operacion/hitos/{fin['id']}/ajustar", headers=h,
                     json={"nuevo_momento": nuevo.isoformat(),
                           "justificacion": "El servicio se alargo y el "
                                            "equipo marco tarde el fin."})
    assert r.status_code == 200, r.text


def test_la_misma_diferencia_no_se_arrastra_dos_veces(cliente, sesion, datos):
    """Era el error mas caro de todos.

    `_pagado_de` solo miraba el concepto del dia, y los ajustes se
    guardan aparte. Una vez pagado el ajuste, la siguiente corrida
    volvia a ver "se pago 800, corresponde 1100" y generaba otros 300.
    Cada vez que el servicio se movia, 300 mas.
    """
    servicio, j, _, pais_id = _dia_pagado(cliente, sesion, datos)
    h = sesion("finanzas")

    # El dia resulta que fue mas largo: ahora corresponde mas.
    _alargar_el_dia(cliente, sesion, j["id"], horas=3)

    r = cliente.post(f"/nomina/servicio/{servicio['id']}/revisar-diferencias",
                     headers=h)
    assert r.status_code == 200, r.text
    pendientes = _pendientes(cliente, sesion, pais_id)
    assert len(pendientes) == 1, pendientes
    assert pendientes[0]["concepto"] == "correccion_jornada"
    diferencia = Decimal(str(pendientes[0]["monto"]))
    assert diferencia > 0, "las horas extra se le deben"

    # Se paga la diferencia.
    corte = cliente.post("/nomina/calcular", headers=h,
                         json={"pais_id": pais_id,
                               "fecha_corte": str(_lunes())})
    assert corte.status_code == 200, corte.text
    cliente.post(f"/nomina/{corte.json()['nomina_id']}/pagar", headers=h)
    assert _pendientes(cliente, sesion, pais_id) == []

    # Y aqui estaba el agujero: revisar otra vez generaba la misma
    # diferencia, y otra, y otra, cada vez que el servicio se movia.
    for _ in range(3):
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
    h = sesion("finanzas")

    # Un descuento por viaticos no comprobados, del mismo dia.
    _ajuste(cliente, sesion, persona_id=juan, pais_id=pais_id,
            servicio_id=servicio["id"], jornada_id=j["id"],
            concepto="viatico_no_comprobado", monto="-600",
            motivo="Viaticos sin comprobar")

    # Y el mismo dia resulta que fue mas largo.
    _alargar_el_dia(cliente, sesion, j["id"], horas=2)
    cliente.post(f"/nomina/servicio/{servicio['id']}/revisar-diferencias",
                 headers=h)

    pendientes = _pendientes(cliente, sesion, pais_id)
    assert len(pendientes) == 2, pendientes
    assert {p["concepto"] for p in pendientes} == {
        "viatico_no_comprobado", "correccion_jornada"}
    # Y cada uno se lee por lo que es, no por un codigo.
    assert {p["de_que"] for p in pendientes} == {
        "Viaticos sin comprobar", "Correccion del pago del dia"}


def test_la_correccion_de_un_dia_no_se_captura_a_mano(cliente, sesion, datos):
    """La calcula el motor comparando contra la tarifa.

    Un ajuste capturado con ese concepto se mete en esa comparacion y el
    sistema lo lee como un pago de mas: en la siguiente revision genera
    otro ajuste para quitarlo. Un bono acordado a mano se desharia solo,
    sin que nadie entienda por que.
    """
    servicio, j, juan, pais_id = _dia_pagado(cliente, sesion, datos)
    r = _ajuste(cliente, sesion, esperado=400,
                persona_id=juan, pais_id=pais_id,
                servicio_id=servicio["id"], jornada_id=j["id"],
                concepto="correccion_jornada", monto="300",
                motivo="Horas extra que no se habian cargado")
    assert "lo pone el sistema" in r.json()["detail"]["mensaje"]

    # Lo que se captura a mano es "manual", y ese si pasa.
    _ajuste(cliente, sesion, persona_id=juan, pais_id=pais_id,
            servicio_id=servicio["id"], concepto="manual", monto="300",
            motivo="Bono acordado con direccion")


def test_un_ajuste_manual_no_lo_deshace_el_sistema(cliente, sesion, datos):
    """Es la otra mitad de lo mismo: lo capturado a mano no entra a la
    comparacion contra la tarifa, asi que sobrevive a las revisiones."""
    servicio, _, juan, pais_id = _dia_pagado(cliente, sesion, datos)
    h = sesion("finanzas")
    _ajuste(cliente, sesion, persona_id=juan, pais_id=pais_id,
            servicio_id=servicio["id"], concepto="manual", monto="500",
            motivo="Apoyo de transporte acordado con direccion")

    for _ in range(2):
        cliente.post(f"/nomina/servicio/{servicio['id']}/revisar-diferencias",
                     headers=h)

    pendientes = _pendientes(cliente, sesion, pais_id)
    assert len(pendientes) == 1, pendientes
    assert pendientes[0]["concepto"] == "manual"
    assert Decimal(str(pendientes[0]["monto"])) == Decimal("500")


def test_un_ajuste_no_se_paga_en_dos_cortes(cliente, sesion, datos):
    """Dos borradores con fechas de corte distintas se llevaban el mismo
    ajuste, y al pagar los dos la persona cobraba la diferencia dos
    veces."""
    servicio, _, juan, pais_id = _dia_pagado(cliente, sesion, datos)
    h = sesion("finanzas")
    _ajuste(cliente, sesion, persona_id=juan, pais_id=pais_id,
            servicio_id=servicio["id"], concepto="manual", monto="1200",
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
    servicio, _, juan, pais_id = _dia_pagado(cliente, sesion, datos)
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

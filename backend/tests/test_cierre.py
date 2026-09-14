"""Comparativo, revision antes de facturar, rentabilidad y comision."""
from datetime import datetime, timedelta

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana)


def _servicio_ejecutado(cliente, sesion, datos, dias=2, offset=50,
                        horas_extra=0, agente_extra=False):
    """Servicio cotizado, autorizado y ejecutado completo."""
    h = sesion("consultor")
    ana = datos["personal"]["Ana Solis"]["id"]
    fechas = [manana(offset + i) for i in range(dias)]
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(f, datos["modalidades"]["full_day"]["id"]) for f in fechas],
        consultor_id=ana)

    cotizacion = cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])

    for idx, j in enumerate(servicio["equipos"][0]["jornadas"]):
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        if agente_extra and idx == dias - 1:
            # Va como agente, y lo cotizado era un conductor: ese es el
            # recurso que aparecio en la calle sin estar en el trato.
            # El rol es de la tarea, asi que se dice aqui.
            asignar(cliente, h, j["id"],
                    persona_id=datos["personal"]["Miguel Torres"]["id"],
                    rol="agente_seguridad")
        configurar_origen(cliente, h, j["id"])
        ejecutar_jornada(cliente, sesion("juan"), j,
                         horas_extra=horas_extra if idx == dias - 1 else 0)

    return servicio, cotizacion


def test_servicio_sin_desviaciones_pasa_a_finanzas(cliente, sesion, datos):
    servicio, cotizacion = _servicio_ejecutado(cliente, sesion, datos, offset=50)
    h = sesion("consultor")

    comparativo = cliente.get(f"/cierre/servicio/{servicio['id']}/comparativo",
                              headers=h).json()
    assert comparativo["sin_desviaciones"] is True
    assert comparativo["ejecutado"]["total"] == comparativo["cotizacion"]["total"]

    revision = cliente.get(f"/cierre/servicio/{servicio['id']}/revision",
                           headers=h).json()
    assert revision["listo_para_finanzas"] is True


def test_recurso_no_cotizado_frena_el_cierre(cliente, sesion, datos):
    servicio, _ = _servicio_ejecutado(cliente, sesion, datos, offset=53,
                                      agente_extra=True)
    h = sesion("consultor")

    comparativo = cliente.get(f"/cierre/servicio/{servicio['id']}/comparativo",
                              headers=h).json()
    tipos = {d["tipo"] for d in comparativo["desviaciones"]}
    assert "recurso_no_cotizado" in tipos

    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                          headers=h).json()
    envio = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas", headers=h)
    assert envio.status_code == 409


def test_las_horas_extra_se_cobran_y_no_frenan(cliente, sesion, datos):
    servicio, _ = _servicio_ejecutado(cliente, sesion, datos, offset=56,
                                      horas_extra=3)
    h = sesion("consultor")

    comparativo = cliente.get(f"/cierre/servicio/{servicio['id']}/comparativo",
                              headers=h).json()
    assert comparativo["ejecutado"]["horas_extra"] == 3
    assert comparativo["ejecutado"]["total"] > comparativo["cotizacion"]["total"]

    revision = cliente.get(f"/cierre/servicio/{servicio['id']}/revision",
                           headers=h).json()
    assert revision["listo_para_finanzas"] is True, \
        "las horas extra no deben frenar el cierre"
    horas = [o for o in revision["observaciones"] if o["asunto"] == "Horas extra"]
    assert horas and horas[0]["nivel"] == "informativo"


def test_jornada_sin_termino_frena_el_cierre(cliente, sesion, datos):
    h = sesion("consultor")
    ana = datos["personal"]["Ana Solis"]["id"]
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(59), datos["modalidades"]["full_day"]["id"])], consultor_id=ana)
    cotizar_y_autorizar(cliente, h, servicio,
                        datos["perfiles"]["conductor_seguridad"]["id"],
                        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    # No se marca ningun hito: el servicio quedo sin ejecutar

    revision = cliente.get(f"/cierre/servicio/{servicio['id']}/revision",
                           headers=h).json()
    assert revision["listo_para_finanzas"] is False
    asuntos = {o["asunto"] for o in revision["observaciones"]}
    assert "Jornada sin termino" in asuntos


def test_rentabilidad_con_sus_tres_bloques(cliente, sesion, datos):
    servicio, _ = _servicio_ejecutado(cliente, sesion, datos, offset=60)
    rent = cliente.get(f"/cierre/servicio/{servicio['id']}/rentabilidad",
                       headers=sesion("consultor")).json()

    assert rent["facturacion"] > 0
    assert rent["costos"]["personal"] > 0
    assert rent["costos"]["vehiculo"] > 0
    esperado = (rent["costos"]["personal"] + rent["costos"]["viaticos_comprobados"]
                + rent["costos"]["vehiculo"])
    assert abs(rent["costos"]["total"] - esperado) < 0.01
    assert abs(rent["utilidad"] - (rent["facturacion"] - rent["costos"]["total"])) < 0.01


def test_la_comision_se_detona_al_aprobar_finanzas(cliente, sesion, datos):
    servicio, _ = _servicio_ejecutado(cliente, sesion, datos, offset=63)
    h = sesion("consultor")

    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir", headers=h).json()
    envio = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas", headers=h)
    assert envio.status_code == 200
    assert envio.json()["dentro_de_plazo"] is True

    aprobacion = cliente.post(f"/cierre/{cierre['cierre_id']}/aprobar",
                              headers=sesion("finanzas"))
    assert aprobacion.status_code == 200
    comision = aprobacion.json()["comision_consultor"]
    assert comision["estatus"] == "generada"
    assert float(comision["porcentaje"]) == 3.0, "eventual paga 3 por ciento"

    rent = cliente.get(f"/cierre/servicio/{servicio['id']}/rentabilidad",
                       headers=h).json()
    base_esperada = rent["facturacion"] - rent["costos"]["viaticos_comprobados"]
    assert abs(float(comision["base"]) - base_esperada) < 0.01


def test_comision_perdida_si_se_cierra_fuera_de_plazo(cliente, sesion, datos):
    servicio, _ = _servicio_ejecutado(cliente, sesion, datos, offset=66)
    h = sesion("consultor")

    hace_dos_dias = (datetime.now() - timedelta(days=2)).isoformat()
    cierre = cliente.post(
        f"/cierre/servicio/{servicio['id']}/abrir?abierto_en={hace_dos_dias}",
        headers=h).json()

    envio = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas", headers=h)
    assert envio.status_code == 200
    assert envio.json()["dentro_de_plazo"] is False

    aprobacion = cliente.post(f"/cierre/{cierre['cierre_id']}/aprobar",
                              headers=sesion("finanzas")).json()
    comision = aprobacion["comision_consultor"]
    assert comision["estatus"] == "perdida"
    assert float(comision["monto"]) == 0


def test_recotizar_crea_version_nueva(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(69), datos["modalidades"]["full_day"]["id"])])
    cotizar_y_autorizar(cliente, h, servicio,
                        datos["perfiles"]["conductor_seguridad"]["id"],
                        datos["categorias"]["suv_blindada"]["id"])

    segunda = cotizar_y_autorizar(cliente, h, servicio,
                                  datos["perfiles"]["agente_seguridad"]["id"],
                                  datos["categorias"]["minivan_blindada"]["id"])
    assert segunda["version"] == 2

    historial = cliente.get(f"/cotizaciones/servicio/{servicio['id']}",
                            headers=h).json()
    assert historial[0]["estatus"] == "sustituida"
    assert historial[1]["estatus"] == "autorizada"


# ------------------------------------ como se le factura el viatico al cliente

def test_viaticos_incluidos_no_se_suman_a_la_factura(cliente, sesion, datos):
    """Si iban dentro del precio, la comprobacion no mueve la factura."""
    servicio, _ = _servicio_ejecutado(cliente, sesion, datos, offset=400)
    comparativo = cliente.get(f"/cierre/servicio/{servicio['id']}/comparativo",
                              headers=sesion("consultor")).json()
    assert comparativo["viaticos"]["modo_cobro"] == "incluidos_en_cotizacion"
    assert comparativo["viaticos"]["facturable_al_cliente"] == 0

"""Borrar un servicio que ya paso por todo.

Las pruebas de borrado que habia solo borraban servicios en borrador,
donde no cuelga nada. Por eso nunca se vio que un servicio ya cotizado
reventaba con un 500: la cotizacion, el cierre, la comision del
consultor y el contrato del implantado apuntan al servicio con llaves
que no admiten nulo, y nadie las estaba quitando.

Esta prueba borra un servicio que ya recorrio el camino completo. Si
alguien agrega una tabla nueva que cuelgue del servicio y no la limpia,
se cae aqui —que es donde tiene que caerse, y no en la pantalla de un
consultor a las once de la noche.
"""
from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, jornada, manana)


def _borrar(cliente, headers, ruta, motivo):
    return cliente.request("DELETE", ruta, json={"motivo": motivo},
                           headers=headers)


def test_un_servicio_cotizado_se_puede_borrar(cliente, sesion, datos):
    """Cotizar deja renglones colgando del servicio. Sin limpiarlos, el
    borrado explotaba con una violacion de llave foranea."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(40), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])

    r = _borrar(cliente, h, f"/servicios/{servicio['id']}",
                "Se capturo al cliente equivocado")
    assert r.status_code == 200, r.text
    assert cliente.get(f"/servicios/{servicio['id']}",
                       headers=h).status_code == 404


def test_no_se_borra_un_equipo_con_un_vuelo_ya_comprado(cliente, sesion, datos):
    """La compra cuelga del equipo con borrado en cascada: borrar el
    equipo la desaparecia de la base. El dinero ya salio de la empresa y
    no quedaba ni el numero de reserva."""
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(30), datos["modalidades"]["full_day"]["id"])])
    equipo = servicio["equipos"][0]
    j = equipo["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])

    compra = cliente.post(f"/viaticos/equipos/{equipo['id']}/compras",
                          headers=h,
                          json={"tipo": "vuelo",
                                "solicitud": "MEX-MTY ida y vuelta para dos",
                                "monto_estimado": "8400"})
    assert compra.status_code == 201, compra.text

    # Finanzas la resuelve: a partir de aqui hay dinero comprometido y un
    # folio de reserva que alguien tendria que cancelar.
    conf = cliente.post(f"/viaticos/compras/{compra.json()['id']}/confirmar",
                        headers=sesion("finanzas"),
                        json={"monto_real": "8150",
                              "confirmacion": "AM-4471-XZ"})
    assert conf.status_code == 200, conf.text

    r = _borrar(cliente, h, f"/servicios/{servicio['id']}",
                "Ya no se necesita este servicio")
    assert r.status_code == 409, r.text
    assert "compra" in r.json()["detail"]["mensaje"]


def test_una_compra_que_nadie_tomo_no_impide_borrar(cliente, sesion, datos):
    """Pedir una compra es papel. Lo que cierra la puerta es que finanzas
    ya la haya resuelto, igual que con los viaticos: lo que importa es si
    el dinero salio."""
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(31), datos["modalidades"]["full_day"]["id"])])
    equipo = servicio["equipos"][0]

    compra = cliente.post(f"/viaticos/equipos/{equipo['id']}/compras",
                          headers=h,
                          json={"tipo": "hotel",
                                "solicitud": "Dos noches cerca del corporativo",
                                "monto_estimado": "5200"})
    assert compra.status_code == 201, compra.text

    r = _borrar(cliente, h, f"/servicios/{servicio['id']}",
                "El cliente lo echo para atras")
    assert r.status_code == 200, r.text

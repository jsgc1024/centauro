"""El control del dinero que sale a la calle.

Esta pantalla maneja los gastos del servicio —viaticos y compras— y no
la nomina del personal de seguridad, que va por su cuenta.

Lo que se prueba: que finanzas tenga memoria de lo que pago, que sepa
cuanto anda afuera sin comprobar, y que un deposito no se confirme dos
veces.
"""

from ayudas import asignar, crear_servicio, jornada, manana


def _con_viaticos(cliente, sesion, datos, monto="3000", dia=20,
                  quien="Juan Ramirez"):
    """Un eventual con una persona y su deposito ya solicitado.

    El dia y la persona se pueden cambiar porque nadie puede estar en dos
    servicios el mismo dia: dos escenarios en la misma fecha con la
    misma gente chocan, y el choque es correcto.
    """
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(dia), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    equipo_id = servicio["equipos"][0]["id"]
    juan = datos["personal"][quien]["id"]
    r = asignar(cliente, h, j["id"], persona_id=juan,
                vehiculo_id=datos["suburban"]["id"])[0]
    assert r.status_code == 200, r.text

    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                     json={"persona_id": juan, "monto": monto}, headers=h)
    assert r.status_code == 200, r.text
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar", json={},
                     headers=h)
    assert r.status_code == 200, r.text
    return servicio, equipo_id, juan


def _solicitud_de(cliente, h, folio):
    bandeja = cliente.get("/viaticos/finanzas/bandeja", headers=h).json()
    for pais in bandeja["paises"]:
        for d in pais["depositos"]:
            if d["folio"] == folio:
                return d
    raise AssertionError(f"{folio} no esta en la bandeja")


def test_el_deposito_queda_firmado(cliente, sesion, datos):
    """Quien lo despacho y cuando. Sin eso, en cuanto el renglon sale de
    la bandeja no hay forma de saber si ya se pago."""
    servicio, _, juan = _con_viaticos(cliente, sesion, datos)
    f = sesion("finanzas")
    deposito = _solicitud_de(cliente, f, servicio["folio"])

    for solicitud_id in deposito["solicitudes"]:
        r = cliente.post(
            f"/viaticos/transferencias/{solicitud_id}/confirmar"
            f"?referencia_odoo=TR-9001", headers=f)
        assert r.status_code == 200, r.text

    historial = cliente.get("/viaticos/finanzas/depositado", headers=f).json()
    suyos = [d for pais in historial["paises"] for d in pais["depositos"]
             if d["folio"] == servicio["folio"]]
    assert suyos, "el deposito no quedo en el historial"
    assert all(d["referencia_odoo"] == "TR-9001" for d in suyos)
    assert all(d["confirmada_en"] for d in suyos)
    assert all(d["confirmada_por"] == "Jorge Diaz" for d in suyos), suyos


def test_un_deposito_no_se_confirma_dos_veces(cliente, sesion, datos):
    """Confirmar dos veces el mismo deposito es como se paga dos veces."""
    servicio, _, _ = _con_viaticos(cliente, sesion, datos)
    f = sesion("finanzas")
    solicitud_id = _solicitud_de(cliente, f,
                                 servicio["folio"])["solicitudes"][0]

    assert cliente.post(f"/viaticos/transferencias/{solicitud_id}/confirmar",
                        headers=f).status_code == 200
    r = cliente.post(f"/viaticos/transferencias/{solicitud_id}/confirmar",
                     headers=f)
    assert r.status_code == 409, r.text
    assert "ya estaba confirmado" in str(r.json()["detail"])


def test_lo_depositado_sale_del_historial_y_no_de_la_bandeja(cliente, sesion,
                                                             datos):
    """La bandeja es lo que falta por pagar; el historial es lo que ya se
    pago. Un renglon no puede estar en los dos."""
    servicio, _, _ = _con_viaticos(cliente, sesion, datos)
    f = sesion("finanzas")
    for sid in _solicitud_de(cliente, f, servicio["folio"])["solicitudes"]:
        cliente.post(f"/viaticos/transferencias/{sid}/confirmar", headers=f)

    bandeja = cliente.get("/viaticos/finanzas/bandeja", headers=f).json()
    pendientes = [d for p in bandeja["paises"] for d in p["depositos"]
                  if d["folio"] == servicio["folio"]]
    assert not pendientes, "sigue en la bandeja despues de pagarse"


def test_el_dinero_afuera_se_ve_con_su_limite(cliente, sesion, datos):
    """Lo transferido y sin comprobar es lo que la empresa trae en la
    calle. Es la cuenta que nadie estaba llevando."""
    servicio, _, juan = _con_viaticos(cliente, sesion, datos, monto="2500")
    f = sesion("finanzas")
    for sid in _solicitud_de(cliente, f, servicio["folio"])["solicitudes"]:
        cliente.post(f"/viaticos/transferencias/{sid}/confirmar", headers=f)

    afuera = cliente.get("/viaticos/finanzas/por-comprobar", headers=f).json()
    suyos = [x for p in afuera["paises"] for x in p["personas"]
             if x["folio"] == servicio["folio"]]
    assert suyos, "el dinero transferido no aparece como afuera"
    x = suyos[0]
    assert float(x["entregado"]) == 2500
    assert float(x["comprobado"]) == 0
    assert float(x["pendiente"]) == 2500
    assert x["persona_id"] == juan


def test_el_corte_separa_comprometido_de_afuera(cliente, sesion, datos):
    """Comprometido es lo pedido y sin salir; afuera es lo que salio y no
    se ha comprobado. Confundirlos es como se acaba el mes creyendo que
    se debe menos de lo que se debe."""
    servicio, _, _ = _con_viaticos(cliente, sesion, datos, monto="1800")
    f = sesion("finanzas")

    antes = cliente.get("/viaticos/finanzas/corte", headers=f).json()
    mx = next(p for p in antes["paises"] if p["codigo"] == "MX")
    assert float(mx["comprometido"]) >= 1800
    comprometido_antes = float(mx["comprometido"])

    for sid in _solicitud_de(cliente, f, servicio["folio"])["solicitudes"]:
        cliente.post(f"/viaticos/transferencias/{sid}/confirmar", headers=f)

    despues = cliente.get("/viaticos/finanzas/corte", headers=f).json()
    mx = next(p for p in despues["paises"] if p["codigo"] == "MX")
    # El dinero se movio de un lado al otro: ya no esta comprometido,
    # ahora esta afuera.
    assert float(mx["comprometido"]) == comprometido_antes - 1800
    assert float(mx["afuera"]) >= 1800
    assert float(mx["depositado_mes"]) >= 0


def test_el_historial_se_puede_buscar_por_folio(cliente, sesion, datos):
    servicio, _, _ = _con_viaticos(cliente, sesion, datos)
    # Otro dia y otra persona: nadie esta en dos servicios a la vez.
    otro, _, _ = _con_viaticos(cliente, sesion, datos, dia=21,
                               quien="Luis Mendoza")
    f = sesion("finanzas")
    for s_ in (servicio, otro):
        for sid in _solicitud_de(cliente, f, s_["folio"])["solicitudes"]:
            cliente.post(f"/viaticos/transferencias/{sid}/confirmar", headers=f)

    r = cliente.get(f"/viaticos/finanzas/depositado?folio={servicio['folio']}",
                    headers=f).json()
    folios = {d["folio"] for p in r["paises"] for d in p["depositos"]}
    assert folios == {servicio["folio"]}, folios

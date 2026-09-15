"""Los limites del dinero que anda en la calle.

Lo comprobado no es un numero cualquiera: es lo que se le factura al
cliente y lo que decide si hay descuento de nomina. Sin topes, el mismo
campo servia para cobrarle de mas al cliente y para que un descuento
dejara de ser posible.
"""
from ayudas import asignar, configurar_origen, crear_servicio, jornada, manana


def _viatico(cliente, sesion, datos, monto="1500"):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(0), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])

    r = cliente.post("/viaticos/asignar", headers=h,
                     json={"jornada_id": j["id"], "persona_id": juan,
                           "conceptos": [{"concepto": "combustible",
                                          "monto": monto,
                                          "origen": "tabulador"}]})
    assert r.status_code == 201, r.text
    return r.json()


def _ticket(cliente, sesion, viatico_id, monto, nota=None):
    return cliente.post(f"/campo/viaticos/{viatico_id}/comprobante",
                        headers=sesion("juan"),
                        json={"concepto": "combustible", "tipo": "nota",
                              "monto": monto, "descripcion": nota})


def test_no_se_comprueba_mas_de_lo_que_se_entrego(cliente, sesion, datos):
    """Quien recibio 1500 y no gasto nada subia un "comprobante" de 1500
    y el descuento de nomina dejaba de ser posible: el sistema contestaba
    "no hay nada que descontar"."""
    v = _viatico(cliente, sesion, datos, monto="1500")
    r = _ticket(cliente, sesion, v["id"], "5000")
    assert r.status_code == 409, r.text
    assert "pasa de lo que se entrego" in r.json()["detail"]["mensaje"]


def test_un_ticket_de_cero_o_negativo_no_es_un_ticket(cliente, sesion, datos):
    v = _viatico(cliente, sesion, datos)
    assert _ticket(cliente, sesion, v["id"], "0").status_code == 400
    assert _ticket(cliente, sesion, v["id"], "-200").status_code == 400


def test_el_mismo_ticket_no_se_sube_dos_veces(cliente, sesion, datos):
    """Un doble toque con media barra de senal, que es la situacion
    normal en una gasolinera. Las dos filas sumaban, y lo comprobado es
    lo que se le factura al cliente."""
    v = _viatico(cliente, sesion, datos)
    assert _ticket(cliente, sesion, v["id"], "800",
                   "Gasolina Pemex Reforma").status_code == 200
    r = _ticket(cliente, sesion, v["id"], "800", "Gasolina Pemex Reforma")
    assert r.status_code == 409, r.text
    assert "se acaba de subir" in r.json()["detail"]["mensaje"]

    # Dos gastos de verdad distintos, con su nota, si pasan.
    assert _ticket(cliente, sesion, v["id"], "800",
                   "Gasolina de regreso").status_code == 200


def test_no_se_devuelve_mas_de_lo_que_queda(cliente, sesion, datos):
    """Mandar el POST dos veces dejaba el devuelto al doble, el pendiente
    en negativo, y a la persona fuera del tablero de dinero en la
    calle —que filtra por pendiente mayor a cero."""
    v = _viatico(cliente, sesion, datos, monto="1500")
    h = sesion("consultor")

    r = cliente.post(f"/viaticos/{v['id']}/devolver?monto=1500", headers=h)
    assert r.status_code == 200, r.text

    r = cliente.post(f"/viaticos/{v['id']}/devolver?monto=1500", headers=h)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["por_devolver"] == "0.00"


def test_una_devolucion_negativa_no_borra_una_real(cliente, sesion, datos):
    """Con un monto negativo se deshacia una devolucion de verdad sin
    dejar mas rastro que una nota."""
    v = _viatico(cliente, sesion, datos, monto="1500")
    h = sesion("consultor")
    cliente.post(f"/viaticos/{v['id']}/devolver?monto=500", headers=h)
    r = cliente.post(f"/viaticos/{v['id']}/devolver?monto=-500", headers=h)
    assert r.status_code == 400, r.text

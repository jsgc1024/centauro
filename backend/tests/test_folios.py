"""La serie del folio y la cartera van por tipo de servicio.

Eventual e implantado son dos operaciones distintas: mezclarlas en un
solo consecutivo dejaba la serie del eventual llena de huecos, y la
cartera de eventuales mostrando servicios que no se operan ahi.
"""


def _alta(cliente, h, datos, tipo):
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": tipo,
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_cada_tipo_lleva_su_letra(cliente, sesion, datos):
    h = sesion("consultor")
    eventual = _alta(cliente, h, datos, "eventual")
    implantado = _alta(cliente, h, datos, "implantado")

    assert eventual["folio"].startswith("EP/E-"), eventual["folio"]
    assert implantado["folio"].startswith("EP/IM-"), implantado["folio"]


def test_el_implantado_no_gasta_numeros_del_eventual(cliente, sesion, datos):
    """Dar de alta un implantado en medio no debe saltarse un numero del
    eventual: el consultor lleva la cuenta de su serie."""
    h = sesion("consultor")
    primero = _alta(cliente, h, datos, "eventual")
    _alta(cliente, h, datos, "implantado")
    segundo = _alta(cliente, h, datos, "eventual")

    numero = lambda folio: int(folio.rsplit("-", 1)[-1])
    assert numero(segundo["folio"]) == numero(primero["folio"]) + 1


def test_la_cartera_de_eventuales_no_muestra_implantados(cliente, sesion, datos):
    h = sesion("consultor")
    eventual = _alta(cliente, h, datos, "eventual")
    implantado = _alta(cliente, h, datos, "implantado")

    cartera = cliente.get("/servicios", headers=h).json()
    folios = [s["folio"] for s in cartera]
    assert eventual["folio"] in folios
    assert implantado["folio"] not in folios

    # Quien necesite ver la operacion completa pide los dos.
    todos = [s["folio"] for s in
             cliente.get("/servicios?todos=true", headers=h).json()]
    assert eventual["folio"] in todos and implantado["folio"] in todos

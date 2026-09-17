"""El dinero del equipo: viaticos y compras especiales.

Dos caminos distintos. Lo que se deposita —alimentos, combustible,
casetas— va a la cuenta de cada persona y lo decide el consultor. Lo que
se compra —un vuelo, un hotel— no se le da en efectivo a nadie: el
consultor lo pide y finanzas lo compra y contesta con la reserva.
"""
from datetime import date, timedelta

from ayudas import depositar

MANANA = date.today() + timedelta(days=1)


def equipo_armado(cliente, h, datos, dias=2):
    """Un equipo con dos personas y su unidad, listo para repartir dinero."""
    jornadas = [{
        "fecha": str(MANANA + timedelta(days=i)),
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "hora_presentacion": "08:00:00",
        "origen_direccion": "Las Alcobas, Polanco - lobby",
        "origen_lat": "19.4284", "origen_lon": "-99.1957",
    } for i in range(dias)]

    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": jornadas}],
    }, headers=h)
    assert r.status_code == 201, r.text
    servicio = r.json()
    equipo_id = servicio["equipos"][0]["id"]

    for persona in ("Luis Mendoza", "Juan Ramirez"):
        r = cliente.post(f"/servicios/equipos/{equipo_id}/asignar-personal",
                         json={"persona_id": datos["personal"][persona]["id"],
                               "forzar": True}, headers=h)
        assert r.status_code == 200, r.text
    cliente.post(f"/servicios/equipos/{equipo_id}/asignar-vehiculo",
                 json={"vehiculo_id": datos["suburban"]["id"],
                       "forzar": True}, headers=h)
    return servicio, equipo_id


# ------------------------------------------------------------ viaticos

def test_el_panel_propone_y_arranca_en_gris(cliente, sesion, datos):
    """Antes de que nadie diga cuanto, la propuesta ya esta ahi."""
    h = sesion("consultor")
    _, equipo_id = equipo_armado(cliente, h, datos)

    panel = cliente.get(f"/viaticos/equipos/{equipo_id}", headers=h).json()
    assert len(panel["personal"]) == 2
    for fila in panel["personal"]:
        assert fila["dias"] == 2
        assert float(fila["propuesto"]) > 0, "el tabulador debe proponer algo"
        assert float(fila["asignado"]) == 0
        assert fila["estatus"] == "por_asignar"


def test_el_monto_del_consultor_se_reparte_entre_sus_dias(cliente, sesion, datos):
    """El consultor escribe un numero por persona; por dentro se reparte
    entre sus dias, y la suma tiene que dar exactamente ese numero, ya
    subido al entero de arriba."""
    h = sesion("consultor")
    _, equipo_id = equipo_armado(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]["id"]

    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                     json={"persona_id": persona, "monto": "3333.33"},
                     headers=h)
    assert r.status_code == 200, r.text

    fila = next(f for f in r.json()["personal"] if f["persona_id"] == persona)
    assert float(fila["asignado"]) == 3334
    assert fila["estatus"] == "asignado"
    # El otro sigue sin nada: el dinero es por persona.
    otro = next(f for f in r.json()["personal"] if f["persona_id"] != persona)
    assert otro["estatus"] == "por_asignar"


def test_el_monto_se_puede_corregir_antes_de_pedirlo(cliente, sesion, datos):
    """Subir y bajar el numero no deja un renglon por intento."""
    h = sesion("consultor")
    _, equipo_id = equipo_armado(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]["id"]

    for monto in ("1000", "2500", "1800"):
        cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                     json={"persona_id": persona, "monto": monto}, headers=h)

    panel = cliente.get(f"/viaticos/equipos/{equipo_id}", headers=h).json()
    fila = next(f for f in panel["personal"] if f["persona_id"] == persona)
    assert float(fila["asignado"]) == 1800


def test_el_circuito_completo_del_deposito(cliente, sesion, datos):
    """De gris a verde: el consultor decide, finanzas deposita."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    _, equipo_id = equipo_armado(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]["id"]

    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": persona, "monto": "2400"}, headers=h)

    r = cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar",
                     json={"persona_id": persona}, headers=h)
    assert r.status_code == 200, r.text
    fila = next(f for f in r.json()["personal"] if f["persona_id"] == persona)
    assert fila["estatus"] == "solicitado"

    # Finanzas lo ve como un solo renglon, aunque por dentro sean dos
    # dias, y dentro del apartado de su pais con su moneda.
    bandeja = cliente.get("/viaticos/finanzas/bandeja", headers=finanzas).json()
    mexico = next(p for p in bandeja["paises"] if p["codigo"] == "MX")
    assert mexico["moneda"] == "MXN"
    suyo = [d for d in mexico["depositos"] if d["persona_id"] == persona]
    assert len(suyo) == 1, "un renglon por persona, no uno por dia"
    assert float(suyo[0]["monto"]) == 2400
    assert suyo[0]["dias"] == 2

    r = depositar(cliente, finanzas, equipo_id, persona, "SPEI 88213")
    assert r.status_code == 200, r.text

    panel = cliente.get(f"/viaticos/equipos/{equipo_id}", headers=h).json()
    fila = next(f for f in panel["personal"] if f["persona_id"] == persona)
    assert fila["estatus"] == "depositado"


def test_se_puede_mandar_otro_deposito_encima_del_primero(
        cliente, sesion, datos):
    """El servicio se alarga o falta dinero: un deposito no cierra la
    puerta al siguiente, y las cuentas se ven por separado."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    _, equipo_id = equipo_armado(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]["id"]

    def fila():
        panel = cliente.get(f"/viaticos/equipos/{equipo_id}", headers=h).json()
        return next(f for f in panel["personal"]
                    if f["persona_id"] == persona)

    # Primera ronda, hasta el deposito.
    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": persona, "monto": "2400"}, headers=h)
    cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar",
                 json={"persona_id": persona}, headers=h)
    depositar(cliente, finanzas, equipo_id, persona)
    assert fila()["estatus"] == "depositado"

    # Segunda: 500 mas.
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona/agregar",
                     json={"persona_id": persona, "monto": "500"}, headers=h)
    assert r.status_code == 200, r.text
    f = fila()
    assert float(f["depositado"]) == 2400
    assert float(f["por_solicitar"]) == 500
    assert float(f["asignado"]) == 2900
    assert f["estatus"] == "asignado", "hay algo por pedir otra vez"

    # Y finanzas recibe los 500, no los 2,900.
    cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar",
                 json={"persona_id": persona}, headers=h)
    bandeja = cliente.get("/viaticos/finanzas/bandeja", headers=finanzas).json()
    mexico = next(p for p in bandeja["paises"] if p["codigo"] == "MX")
    suyo = next(d for d in mexico["depositos"] if d["persona_id"] == persona)
    assert float(suyo["monto"]) == 500

    f = fila()
    assert float(f["en_camino"]) == 500
    assert f["estatus"] == "solicitado"

    depositar(cliente, finanzas, equipo_id, persona)
    f = fila()
    assert float(f["depositado"]) == 2900
    assert float(f["por_solicitar"]) == 0
    assert f["estatus"] == "depositado"


def test_el_monto_ya_solicitado_no_se_mueve(cliente, sesion, datos):
    """A esas alturas mover el numero es un viatico adicional, no una
    correccion: finanzas ya tiene una instruccion con otra cifra."""
    h = sesion("consultor")
    _, equipo_id = equipo_armado(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]["id"]

    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": persona, "monto": "2400"}, headers=h)
    cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar",
                 json={"persona_id": persona}, headers=h)

    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                     json={"persona_id": persona, "monto": "900"}, headers=h)
    assert r.status_code == 409, r.text


def test_el_monto_se_deposita_en_enteros(cliente, sesion, datos):
    """Nadie entrega centavos. Lo capturado sube al entero de arriba y la
    suma de los dias da exactamente ese numero."""
    h = sesion("consultor")
    _, equipo_id = equipo_armado(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]["id"]

    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                     json={"persona_id": persona, "monto": "217.60"},
                     headers=h)
    assert r.status_code == 200, r.text
    fila = next(f for f in r.json()["personal"] if f["persona_id"] == persona)
    assert float(fila["asignado"]) == 218

    # Y la propuesta del sistema tampoco trae centavos.
    assert float(fila["propuesto"]) == int(float(fila["propuesto"]))


def test_cada_pais_lleva_su_moneda(cliente, sesion, datos):
    """Un servicio en Mexico se deposita en pesos. La moneda sale del
    pais del servicio, no de una constante."""
    h = sesion("consultor")
    _, equipo_id = equipo_armado(cliente, h, datos)
    panel = cliente.get(f"/viaticos/equipos/{equipo_id}", headers=h).json()
    assert panel["moneda"] == "MXN"


def test_el_deposito_se_cancela_mientras_el_dinero_no_salga(
        cliente, sesion, datos):
    """Se cae un dia o se capturo mal el monto: mientras finanzas no haya
    depositado, el consultor se echa para atras y corrige."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    _, equipo_id = equipo_armado(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]["id"]

    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": persona, "monto": "2400"}, headers=h)
    cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar",
                 json={"persona_id": persona}, headers=h)

    r = cliente.post(f"/viaticos/equipos/{equipo_id}/cancelar-solicitud",
                     json={"persona_id": persona}, headers=h)
    assert r.status_code == 200, r.text
    fila = next(f for f in r.json()["personal"] if f["persona_id"] == persona)
    assert fila["estatus"] == "asignado"
    # El monto se queda: lo que sigue casi siempre es corregirlo.
    assert float(fila["asignado"]) == 2400

    # Y finanzas ya no lo tiene en su bandeja.
    bandeja = cliente.get("/viaticos/finanzas/bandeja", headers=finanzas).json()
    for pais in bandeja["paises"]:
        assert all(d["persona_id"] != persona for d in pais["depositos"])

    # Ya se puede volver a mover.
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                     json={"persona_id": persona, "monto": "1800"}, headers=h)
    assert r.status_code == 200, r.text


def test_lo_ya_depositado_no_se_cancela(cliente, sesion, datos):
    """El dinero ya esta con la persona: eso se devuelve, no se cancela."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    _, equipo_id = equipo_armado(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]["id"]

    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": persona, "monto": "2400"}, headers=h)
    cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar",
                 json={"persona_id": persona}, headers=h)
    depositar(cliente, finanzas, equipo_id, persona)

    r = cliente.post(f"/viaticos/equipos/{equipo_id}/cancelar-solicitud",
                     json={"persona_id": persona}, headers=h)
    assert r.status_code == 409, r.text


def test_no_se_pide_un_deposito_que_nadie_capturo(cliente, sesion, datos):
    h = sesion("consultor")
    _, equipo_id = equipo_armado(cliente, h, datos)
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar", json={},
                     headers=h)
    assert r.status_code == 409, r.text


# --------------------------------------------------- compras especiales

def pedir(cliente, h, equipo_id, **cambios):
    cuerpo = {"tipo": "vuelo",
              "solicitud": "Dos boletos Mexico - Monterrey el 16, saliendo "
                           "antes de las 8 am.",
              "monto_estimado": "9000"}
    cuerpo.update(cambios)
    return cliente.post(f"/viaticos/equipos/{equipo_id}/compras",
                        json=cuerpo, headers=h)


def test_la_compra_va_por_equipo_y_finanzas_la_contesta(cliente, sesion, datos):
    """El consultor escribe que necesita; finanzas compra y contesta con
    el folio, que es con lo que el equipo se presenta en el mostrador."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    _, equipo_id = equipo_armado(cliente, h, datos)

    r = pedir(cliente, h, equipo_id)
    assert r.status_code == 201, r.text
    compra = r.json()["id"]
    assert r.json()["estatus"] == "solicitada"

    bandeja = cliente.get("/viaticos/finanzas/bandeja", headers=finanzas).json()
    mexico = next(p for p in bandeja["paises"] if p["codigo"] == "MX")
    assert any(c["id"] == compra for c in mexico["compras"])

    r = cliente.post(f"/viaticos/compras/{compra}/tomar", headers=finanzas)
    assert r.json()["estatus"] == "en_gestion"

    r = cliente.post(f"/viaticos/compras/{compra}/confirmar",
                     json={"confirmacion": "AM-4471 / PNR XKDLQ2",
                           "monto_real": "8740.50",
                           "respuesta": "Aeromexico 7:05 am, documentado."},
                     headers=finanzas)
    assert r.status_code == 200, r.text
    assert r.json()["estatus"] == "confirmada"

    # Y el consultor lo ve en su panel, sin ir a preguntar.
    panel = cliente.get(f"/viaticos/equipos/{equipo_id}", headers=h).json()
    vista = next(c for c in panel["compras"] if c["id"] == compra)
    assert vista["confirmacion"] == "AM-4471 / PNR XKDLQ2"
    assert float(vista["monto_real"]) == 8740.50


def test_no_hay_confirmacion_sin_folio_ni_imagen(cliente, sesion, datos):
    """El equipo no se puede presentar en un mostrador con la palabra de
    que ya se compro."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    _, equipo_id = equipo_armado(cliente, h, datos)
    compra = pedir(cliente, h, equipo_id).json()["id"]

    r = cliente.post(f"/viaticos/compras/{compra}/confirmar",
                     json={"respuesta": "Ya quedo"}, headers=finanzas)
    assert r.status_code == 400, r.text


def test_rechazar_sin_decir_por_que_no_se_puede(cliente, sesion, datos):
    """El consultor tiene que resolverlo de otra forma y necesita saber
    que paso."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    _, equipo_id = equipo_armado(cliente, h, datos)
    compra = pedir(cliente, h, equipo_id).json()["id"]

    r = cliente.post(f"/viaticos/compras/{compra}/rechazar", json={},
                     headers=finanzas)
    assert r.status_code == 400, r.text

    r = cliente.post(f"/viaticos/compras/{compra}/rechazar",
                     json={"respuesta": "No hay vuelos a esa hora."},
                     headers=finanzas)
    assert r.json()["estatus"] == "rechazada"


def test_la_solicitud_ya_tomada_no_se_reescribe(cliente, sesion, datos):
    """Alguien ya esta buscando con ese texto."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    _, equipo_id = equipo_armado(cliente, h, datos)
    compra = pedir(cliente, h, equipo_id).json()["id"]
    cliente.post(f"/viaticos/compras/{compra}/tomar", headers=finanzas)

    r = cliente.patch(f"/viaticos/compras/{compra}",
                      json={"tipo": "vuelo",
                            "solicitud": "Mejor tres boletos el dia 17."},
                      headers=h)
    assert r.status_code == 409, r.text


def test_el_consultor_no_deposita_ni_finanzas_pide(cliente, sesion, datos):
    """Cada quien en su carril: quien pide el dinero no es quien lo suelta."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    _, equipo_id = equipo_armado(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]["id"]

    r = depositar(cliente, h, equipo_id, persona)
    assert r.status_code == 403, r.text

    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                     json={"persona_id": persona, "monto": "500"},
                     headers=finanzas)
    assert r.status_code == 403, r.text


# ------------------------------------------------------- un solo hotel

def test_un_hotel_por_equipo(cliente, sesion, datos):
    """Dos hoteles en la hoja dejan la duda de a cual llegar. El segundo
    corrige al primero en vez de agregarse."""
    h = sesion("consultor")
    _, equipo_id = equipo_armado(cliente, h, datos)

    r = cliente.post("/hospedajes", json={
        "equipo_id": equipo_id, "nombre_libre": "hyatt regency polanco",
        "direccion_libre": "Campos Eliseos 204, Polanco",
        "telefono_libre": "+52 55 5083 1234"}, headers=h)
    assert r.status_code == 201, r.text

    r = cliente.post("/hospedajes", json={
        "equipo_id": equipo_id, "nombre_libre": "las alcobas",
        "direccion_libre": "Presidente Masaryk 390, Polanco"}, headers=h)
    assert r.status_code == 201, r.text

    estancias = cliente.get(f"/hospedajes/equipo/{equipo_id}",
                            headers=h).json()
    assert len(estancias) == 1, "uno por equipo"
    assert estancias[0]["hotel"] == "Las Alcobas"

    r = cliente.request("DELETE", f"/hospedajes/equipo/{equipo_id}", headers=h)
    assert r.status_code == 200, r.text
    assert cliente.get(f"/hospedajes/equipo/{equipo_id}", headers=h).json() == []


def test_quitar_el_hotel_se_lleva_lo_que_la_hoja_muestra(cliente, sesion, datos):
    """Los servicios de antes de la regla traen su estancia colgada del
    servicio, sin equipo. Se ve en la hoja del equipo, asi que quitar el
    hotel tiene que quitar esa tambien: si no, el boton parece roto."""
    from app.db import SessionLocal
    from app import models as m

    h = sesion("consultor")
    servicio, equipo_id = equipo_armado(cliente, h, datos)

    with SessionLocal() as db:
        db.add(m.Hospedaje(servicio_id=servicio["id"], equipo_id=None,
                           nombre_libre="Hotel de Antes",
                           direccion_libre="Reforma 1"))
        db.commit()

    visto = cliente.get(f"/hospedajes/equipo/{equipo_id}", headers=h).json()
    assert visto and visto[0]["hotel"] == "Hotel de Antes"

    r = cliente.request("DELETE", f"/hospedajes/equipo/{equipo_id}", headers=h)
    assert r.status_code == 200, r.text
    assert cliente.get(f"/hospedajes/equipo/{equipo_id}", headers=h).json() == []


def test_guardar_adopta_la_estancia_vieja_en_vez_de_duplicar(cliente, sesion, datos):
    """Si no, quedaba una fila invisible atras de la que si se ve."""
    from app.db import SessionLocal
    from app import models as m

    h = sesion("consultor")
    servicio, equipo_id = equipo_armado(cliente, h, datos)

    with SessionLocal() as db:
        db.add(m.Hospedaje(servicio_id=servicio["id"], equipo_id=None,
                           nombre_libre="Hotel de Antes"))
        db.commit()

    r = cliente.post("/hospedajes", json={
        "equipo_id": equipo_id, "nombre_libre": "las alcobas"}, headers=h)
    assert r.status_code == 201, r.text

    with SessionLocal() as db:
        cuantas = (db.query(m.Hospedaje)
                   .filter_by(servicio_id=servicio["id"]).count())
    assert cuantas == 1, "la vieja se adopta, no se queda escondida"


# ------------------------------------------------- catalogo de hoteles

def test_el_hotel_capturado_entra_al_catalogo_de_su_ciudad(
        cliente, sesion, datos):
    """El catalogo crece con la operacion: la segunda vez que ese
    ejecutivo va a esa ciudad, su hotel ya esta en la lista."""
    h = sesion("consultor")
    _, equipo_id = equipo_armado(cliente, h, datos)

    r = cliente.post("/hospedajes", json={
        "equipo_id": equipo_id, "nombre_libre": "hotel de la montana",
        "direccion_libre": "Sierra Madre 100",
        "telefono_libre": "+52 55 5000 1000",
        "hotel_lat": "19.4284", "hotel_lon": "-99.1957"}, headers=h)
    assert r.status_code == 201, r.text

    cdmx = datos["cdmx"]["id"]
    lista = cliente.get(f"/catalogos/hoteles?plaza_id={cdmx}", headers=h).json()
    nuevo = next(x for x in lista if x["nombre"] == "Hotel de la Montana")
    assert nuevo["plaza_id"] == cdmx
    assert nuevo["telefono"] == "+52 55 5000 1000"
    assert nuevo["lat"] is not None, "el pin sirve para los hospitales"

    # Y en otra ciudad no aparece.
    gdl = datos["gdl"]["id"]
    otra = cliente.get(f"/catalogos/hoteles?plaza_id={gdl}", headers=h).json()
    assert all(x["nombre"] != "Hotel de la Montana" for x in otra)


def _envejecer(hotel_id, dias=200):
    """Le quita la juventud a un hotel, para poder mirar la regla sin
    esperar tres meses."""
    from datetime import datetime, timedelta, timezone
    from app.db import SessionLocal
    from app import models as m

    with SessionLocal() as db:
        hotel = db.get(m.Hotel, hotel_id)
        hotel.creado_en = datetime.now(timezone.utc) - timedelta(days=dias)
        db.commit()


def test_el_hotel_que_nadie_ocupa_sale_de_la_lista(cliente, sesion, datos):
    """Tres meses sin usarse y deja de estorbar. No se borra: sigue en la
    base y en la pantalla de catalogos."""
    h = sesion("consultor")
    hotel = datos["hoteles"][0]
    _envejecer(hotel["id"])

    ofrecidos = [x["id"] for x in
                 cliente.get("/catalogos/hoteles", headers=h).json()]
    assert hotel["id"] not in ofrecidos

    todos = [x["id"] for x in
             cliente.get("/catalogos/hoteles?todos=true", headers=h).json()]
    assert hotel["id"] in todos, "sigue en la base"


def test_el_recien_capturado_no_se_esconde(cliente, sesion, datos):
    """Todavia no tiene servicio y no por eso se le esconde a quien lo
    acaba de dar de alta."""
    h = sesion("consultor")
    r = cliente.post("/catalogos/hoteles", json={
        "pais_id": datos["mx"]["id"], "plaza_id": datos["cdmx"]["id"],
        "nombre": "Hotel Recien Nacido"}, headers=sesion("admin"))
    assert r.status_code == 201, r.text

    ofrecidos = [x["id"] for x in
                 cliente.get("/catalogos/hoteles", headers=h).json()]
    assert r.json()["id"] in ofrecidos


def test_usar_un_hotel_lo_devuelve_a_la_lista(cliente, sesion, datos):
    """Se gana su lugar usandose, no por antigüedad."""
    h = sesion("consultor")
    _, equipo_id = equipo_armado(cliente, h, datos)
    hotel = datos["hoteles"][0]
    _envejecer(hotel["id"])

    r = cliente.post("/hospedajes", json={
        "equipo_id": equipo_id, "hotel_id": hotel["id"]}, headers=h)
    assert r.status_code == 201, r.text

    ofrecidos = [x["id"] for x in
                 cliente.get("/catalogos/hoteles", headers=h).json()]
    assert hotel["id"] in ofrecidos

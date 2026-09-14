"""La agenda del dia, parada por parada.

Se agrega, se corrige y se quita cada parada por separado, porque la
agenda se mueve durante el dia. Y el task sheet las imprime en orden.
"""
from datetime import date, timedelta

MANANA = date.today() + timedelta(days=1)


def alta(cliente, h, datos):
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [{
            "fecha": str(MANANA),
            "modalidad_id": datos["modalidades"]["full_day"]["id"],
            "hora_presentacion": "07:30:00",
            "origen_direccion": "Las Alcobas, Polanco - lobby",
            "origen_lat": "19.4284", "origen_lon": "-99.1957"}]}],
    }, headers=h)
    assert r.status_code == 201, r.text
    servicio = r.json()
    return servicio, servicio["equipos"][0]["jornadas"][0]["id"]


def test_se_agrega_se_corrige_y_se_quita_una_parada(cliente, sesion, datos):
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)
    ruta = f"/operacion/jornadas/{jornada_id}/agenda/paradas"

    r = cliente.post(ruta, json={"hora": "09:00:00",
                                 "lugar": "oficinas corporativas",
                                 "direccion": "Reforma 250, piso 12"}, headers=h)
    assert r.status_code == 201, r.text
    parada = r.json()
    # La regla de captura tambien aplica aqui.
    assert parada["lugar"] == "Oficinas Corporativas"

    # Se recorre la hora sin tocar lo demas.
    r = cliente.patch(f"/operacion/paradas/{parada['id']}",
                      json={"hora": "09:45:00"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["hora"] == "09:45:00"
    assert r.json()["direccion"] == "Reforma 250, piso 12"

    assert cliente.delete(f"/operacion/paradas/{parada['id']}",
                          headers=h).status_code == 204
    assert cliente.get(ruta, headers=h).json() == []


def test_las_paradas_salen_en_orden_de_reloj(cliente, sesion, datos):
    """Y las que aun no tienen hora se van al final: son las que el
    cliente todavia no confirma."""
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)
    ruta = f"/operacion/jornadas/{jornada_id}/agenda/paradas"

    for hora, lugar in [("13:30:00", "Comida en San Angel"),
                        (None, "Posible visita a planta"),
                        ("09:00:00", "Oficinas Reforma")]:
        assert cliente.post(ruta, json={"hora": hora, "lugar": lugar},
                            headers=h).status_code == 201

    orden = [p["lugar"] for p in cliente.get(ruta, headers=h).json()]
    assert orden == ["Oficinas Reforma", "Comida en San Angel",
                     "Posible Visita a Planta"]


def test_la_hoja_imprime_las_paradas_con_su_hora(cliente, sesion, datos):
    h = sesion("consultor")
    servicio, jornada_id = alta(cliente, h, datos)
    cliente.post(f"/operacion/jornadas/{jornada_id}/agenda/paradas",
                 json={"hora": "09:00:00",
                       "lugar": "Oficinas Reforma 250, piso 12"}, headers=h)

    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                       headers=h).json()
    agenda = hoja["dias"][0]["agenda"]
    assert agenda["paradas"][0]["hora"] == "09:00"
    assert agenda["paradas"][0]["lugar"] == "Oficinas Reforma 250, Piso 12"
    # Con paradas capturadas la agenda ya no esta abierta.
    assert hoja["dias"][0]["agenda_abierta"] is False


def test_una_parada_necesita_lugar(cliente, sesion, datos):
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)
    r = cliente.post(f"/operacion/jornadas/{jornada_id}/agenda/paradas",
                     json={"hora": "09:00:00"}, headers=h)
    assert r.status_code == 422


# ------------------------------------------- el punto y el vuelo del dia

def test_el_vuelo_se_corrige_sin_borrar_lo_demas(cliente, sesion, datos):
    """Mover la hora del vuelo no debe tumbar la aerolinea ni el numero:
    la captura llega por partes."""
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)
    ruta = f"/operacion/jornadas/{jornada_id}/vuelo"

    cliente.patch(ruta, json={"vuelo_aerolinea": "United",
                              "vuelo_numero": "UA 1518",
                              "vuelo_origen": "Houston",
                              "vuelo_tipo": "llegada"}, headers=h)
    r = cliente.patch(ruta, json={"vuelo_hora": f"{MANANA}T13:50:00"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["aerolinea"] == "United"
    assert r.json()["vuelo"] == "UA 1518"
    assert r.json()["hora"] is not None


def test_quitarle_el_aeropuerto_al_dia_borra_su_vuelo(cliente, sesion, datos):
    """Si no, la hoja seguiria anunciando un vuelo que ya no existe."""
    h = sesion("consultor")
    servicio, jornada_id = alta(cliente, h, datos)
    ruta = f"/operacion/jornadas/{jornada_id}/vuelo"

    cliente.patch(ruta, json={"vuelo_aerolinea": "United",
                              "vuelo_numero": "UA 1518",
                              "vuelo_hora": f"{MANANA}T13:50:00",
                              "vuelo_tipo": "llegada"}, headers=h)
    r = cliente.patch(ruta, json={"vuelo_aerolinea": None, "vuelo_numero": None,
                                  "vuelo_origen": None, "vuelo_tipo": None,
                                  "vuelo_hora": None}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["vuelo"] is None

    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                       headers=h).json()
    assert hoja["dias"][0]["vuelo"] is None


def test_se_quita_un_pin_mal_puesto(cliente, sesion, datos):
    """Vaciar las coordenadas es quitar el pin, no dejarlo como estaba."""
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)
    ruta = f"/operacion/jornadas/{jornada_id}/origen"

    r = cliente.patch(ruta, json={"origen_lat": None, "origen_lon": None},
                      headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["con_pin"] is False
    # Y la direccion sigue en su lugar.
    assert r.json()["direccion"] == "Las Alcobas, Polanco - lobby"


def test_el_vuelo_manda_la_hora_de_presentacion_del_primer_dia(
        cliente, sesion, datos):
    """El equipo no se presenta cuando aterriza el ejecutivo: se presenta
    45 minutos antes, porque puede salir del filtro temprano. Si el vuelo
    se mueve, la presentacion se mueve con el."""
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)

    r = cliente.patch(f"/operacion/jornadas/{jornada_id}/vuelo",
                      json={"vuelo_numero": "UA 1518", "vuelo_tipo": "llegada",
                            "vuelo_hora": f"{MANANA}T13:50:00"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["presentacion"] == "13:05"
    assert r.json()["presentacion_movida"] is True

    # Se recorre el vuelo dos horas: la presentacion se recorre igual.
    r = cliente.patch(f"/operacion/jornadas/{jornada_id}/vuelo",
                      json={"vuelo_hora": f"{MANANA}T15:50:00"}, headers=h)
    assert r.json()["presentacion"] == "15:05"


def test_el_vuelo_de_salida_no_mueve_la_presentacion(cliente, sesion, datos):
    """Ese dia el ejecutivo sale de su hotel: la referencia es su hora
    acordada, no el avion."""
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)
    r = cliente.patch(f"/operacion/jornadas/{jornada_id}/vuelo",
                      json={"vuelo_numero": "UA 1519", "vuelo_tipo": "salida",
                            "vuelo_hora": f"{MANANA}T19:00:00"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["presentacion"] == "07:30"
    assert r.json()["presentacion_movida"] is False


def test_al_quitar_el_dia_1_el_siguiente_toma_su_lugar(cliente, sesion, datos):
    """El meet and greet es del primer dia que quede en pie, y el dia que
    se va se lleva su agenda."""
    h = sesion("consultor")
    servicio, jornada_id = alta(cliente, h, datos)
    equipo = servicio["equipos"][0]

    segundo = cliente.post(f"/servicios/equipos/{equipo['id']}/jornadas", json={
        "fecha": str(MANANA + timedelta(days=1)),
        "modalidad_id": datos["modalidades"]["full_day"]["id"]}, headers=h)
    assert segundo.status_code == 201, segundo.text

    cliente.post(f"/operacion/jornadas/{jornada_id}/agenda/paradas",
                 json={"hora": "09:00:00", "lugar": "Oficinas"}, headers=h)

    r = cliente.delete(f"/servicios/jornadas/{jornada_id}", headers=h)
    assert r.status_code == 200, r.text

    quedan = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    jornadas = quedan["equipos"][0]["jornadas"]
    assert len(jornadas) == 1
    assert jornadas[0]["fecha"] == str(MANANA + timedelta(days=1))
    # La agenda del dia que se fue no se queda colgando.
    assert cliente.get(f"/operacion/jornadas/{jornada_id}/agenda/paradas",
                       headers=h).status_code == 404


def test_la_hora_heredada_se_distingue_de_la_capturada(cliente, sesion, datos):
    """El dia 1 trae hora propia; los demas la heredan mientras nadie la
    confirme. Con esa hora se calculan empalmes, asi que conviene saber
    cual es dato y cual es supuesto."""
    h = sesion("consultor")
    servicio, jornada_id = alta(cliente, h, datos)
    equipo = servicio["equipos"][0]

    r = cliente.post(f"/servicios/equipos/{equipo['id']}/jornadas", json={
        "fecha": str(MANANA + timedelta(days=1)),
        "modalidad_id": datos["modalidades"]["full_day"]["id"]}, headers=h)
    assert r.status_code == 201, r.text
    segundo = r.json()["jornada_id"]

    dias = {j["id"]: j for j in cliente.get(
        f"/servicios/{servicio['id']}", headers=h).json()["equipos"][0]["jornadas"]}
    assert dias[jornada_id]["hora_confirmada"] is True
    assert dias[segundo]["hora_confirmada"] is False
    # Heredada, pero util: el dia arranca a la hora del primero.
    assert dias[segundo]["inicio_programado"].endswith("07:30:00")

    cliente.patch(f"/servicios/jornadas/{segundo}",
                  json={"hora_presentacion": "09:00:00"}, headers=h)
    dias = {j["id"]: j for j in cliente.get(
        f"/servicios/{servicio['id']}", headers=h).json()["equipos"][0]["jornadas"]}
    assert dias[segundo]["hora_confirmada"] is True
    assert dias[segundo]["inicio_programado"].endswith("09:00:00")


def test_la_hoja_imprime_hora_y_lugar_de_cada_parada(cliente, sesion, datos):
    """Para eso sirve la hoja: a donde hay que ir y a que hora. La parada
    sin hora lo dice, que es informacion, no un hueco."""
    h = sesion("consultor")
    servicio, jornada_id = alta(cliente, h, datos)
    ruta = f"/operacion/jornadas/{jornada_id}/agenda/paradas"
    cliente.post(ruta, json={"hora": "09:00:00",
                             "lugar": "Oficinas Reforma 250"}, headers=h)
    cliente.post(ruta, json={"lugar": "Posible visita a planta"}, headers=h)

    # La hoja no se publica sin equipo ni unidad: es parte de lo que dice.
    equipo_id = servicio["equipos"][0]["id"]
    cliente.post(f"/servicios/equipos/{equipo_id}/asignar-personal",
                 json={"persona_id": datos["personal"]["Luis Mendoza"]["id"],
                       "forzar": True}, headers=h)
    cliente.post(f"/servicios/equipos/{equipo_id}/asignar-vehiculo",
                 json={"vehiculo_id": datos["suburban"]["id"], "forzar": True},
                 headers=h)

    publicado = cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                             json={"motivo": "prueba"}, headers=h)
    assert publicado.status_code in (200, 201), publicado.text
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja?idioma=es",
                       headers=h)
    assert hoja.status_code == 200, hoja.text
    assert "09:00" in hoja.text
    assert "Oficinas Reforma 250" in hoja.text
    # La que no tiene hora se imprime igual, marcada.
    assert "Por confirmar" in hoja.text
    assert "Posible Visita a Planta" in hoja.text


def test_el_alta_puede_traer_las_paradas_del_dia(cliente, sesion, datos):
    """El consultor tiene la agenda en el correo del cliente cuando esta
    dando de alta: no tiene por que volver a entrar a capturarla."""
    h = sesion("consultor")
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [{
            "fecha": str(MANANA),
            "modalidad_id": datos["modalidades"]["full_day"]["id"],
            "hora_presentacion": "08:00:00",
            "origen_direccion": "Las Alcobas, Polanco - lobby",
            "paradas": [
                {"hora": "09:00:00", "lugar": "oficinas reforma 250"},
                {"lugar": "posible visita a planta"},
            ]}]}],
    }, headers=h)
    assert r.status_code == 201, r.text
    jornada_id = r.json()["equipos"][0]["jornadas"][0]["id"]

    paradas = cliente.get(f"/operacion/jornadas/{jornada_id}/agenda/paradas",
                          headers=h).json()
    assert [p["lugar"] for p in paradas] == ["Oficinas Reforma 250",
                                             "Posible Visita a Planta"]
    assert paradas[0]["hora"] == "09:00:00"
    # La que no trae hora se va al final.
    assert paradas[1]["hora"] is None


def test_el_radio_de_la_geocerca_sale_del_tipo_de_lugar(cliente, sesion, datos):
    """Dos kilometros en aeropuerto y uno en cualquier otro lado: un
    aeropuerto no cabe en un kilometro y la app le negaria la llegada a
    alguien que esta donde debe."""
    h = sesion("consultor")
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [
            {"fecha": str(MANANA),
             "modalidad_id": datos["modalidades"]["transfer"]["id"],
             "hora_presentacion": "07:30:00",
             "origen_direccion": "Aeropuerto Benito Juarez, T2",
             "origen_lat": "19.4353", "origen_lon": "-99.0719",
             "origen_aeropuerto": True},
            {"fecha": str(MANANA + timedelta(days=1)),
             "modalidad_id": datos["modalidades"]["full_day"]["id"],
             "origen_direccion": "Las Alcobas, Polanco - lobby",
             "origen_lat": "19.4325", "origen_lon": "-99.1975"},
        ]}]}, headers=h)
    assert r.status_code == 201, r.text
    por_fecha = {j["fecha"]: j for j in r.json()["equipos"][0]["jornadas"]}
    assert por_fecha[str(MANANA)]["geocerca_metros"] == 2000
    assert por_fecha[str(MANANA + timedelta(days=1))]["geocerca_metros"] == 500


def test_marcar_el_punto_como_aeropuerto_ensancha_el_circulo(cliente, sesion, datos):
    """Y quitarle la marca lo vuelve a cerrar, mientras nadie haya fijado
    un radio a mano."""
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)
    ruta = f"/operacion/jornadas/{jornada_id}/origen"

    r = cliente.patch(ruta, json={"origen_aeropuerto": True}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["geocerca_metros"] == 2000

    r = cliente.patch(ruta, json={"origen_aeropuerto": False}, headers=h)
    assert r.json()["geocerca_metros"] == 500

    # Un radio capturado a mano manda sobre la regla.
    r = cliente.patch(ruta, json={"origen_aeropuerto": True,
                                  "geocerca_metros": 350}, headers=h)
    assert r.json()["geocerca_metros"] == 350


# ---------------------------------------------------- candado del aeropuerto

def _alta_cruda(cliente, h, datos, **jornada):
    """El alta tal cual, para poder mirar el codigo cuando debe fallar."""
    dia = {"fecha": str(MANANA),
           "modalidad_id": datos["modalidades"]["full_day"]["id"],
           "hora_presentacion": "07:30:00"}
    dia.update(jornada)
    return cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [dia]}],
    }, headers=h)


def test_no_se_marca_como_aeropuerto_lo_que_google_dice_que_no_lo_es(
        cliente, sesion, datos):
    """La casilla no es una etiqueta: abre la geocerca de 500 m a 2 km.
    En un hotel eso deja al conductor marcando su llegada desde cuatro
    cuadras antes, y la marca deja de probar nada."""
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)

    r = cliente.patch(f"/operacion/jornadas/{jornada_id}/origen", json={
        "origen_direccion": "Las Alcobas, Polanco - lobby",
        "origen_google_aeropuerto": False,
        "origen_aeropuerto": True}, headers=h)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["campo"] == "origen_aeropuerto"


def test_una_terminal_privada_se_puede_forzar(cliente, sesion, datos):
    """Hay pistas chicas y terminales privadas que Google no clasifica.
    Esas si son aeropuertos: el candado se abre a proposito."""
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)

    r = cliente.patch(f"/operacion/jornadas/{jornada_id}/origen", json={
        "origen_direccion": "Terminal ejecutiva, Toluca",
        "origen_google_aeropuerto": False,
        "origen_aeropuerto": True,
        "forzar_aeropuerto": True}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["geocerca_metros"] == 2000


def test_sin_veredicto_de_google_no_hay_nada_que_trabar(cliente, sesion, datos):
    """Una direccion escrita a mano no tiene contra que compararse."""
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)

    r = cliente.patch(f"/operacion/jornadas/{jornada_id}/origen", json={
        "origen_direccion": "Pista de Atizapan",
        "origen_aeropuerto": True}, headers=h)
    assert r.status_code == 200, r.text


def test_el_candado_tambien_aplica_al_dar_de_alta(cliente, sesion, datos):
    """No sirve de nada trabar la correccion si el alta lo deja pasar."""
    h = sesion("consultor")
    r = _alta_cruda(cliente, h, datos,
                    origen_direccion="Las Alcobas, Polanco - lobby",
                    origen_google_aeropuerto=False,
                    origen_aeropuerto=True)
    assert r.status_code == 409, r.text

    r = _alta_cruda(cliente, h, datos,
                    origen_direccion="Terminal ejecutiva, Toluca",
                    origen_google_aeropuerto=False,
                    origen_aeropuerto=True, forzar_aeropuerto=True)
    assert r.status_code == 201, r.text


def test_el_candado_recuerda_lo_que_google_dijo(cliente, sesion, datos):
    """Se elige el lugar un dia y se marca la casilla otro: el veredicto
    quedo guardado y sigue trabando."""
    h = sesion("consultor")
    _, jornada_id = alta(cliente, h, datos)

    cliente.patch(f"/operacion/jornadas/{jornada_id}/origen", json={
        "origen_direccion": "Las Alcobas, Polanco - lobby",
        "origen_google_aeropuerto": False}, headers=h)

    r = cliente.patch(f"/operacion/jornadas/{jornada_id}/origen",
                      json={"origen_aeropuerto": True}, headers=h)
    assert r.status_code == 409, r.text

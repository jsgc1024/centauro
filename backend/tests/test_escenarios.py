"""Escenarios completos, de la llamada del cliente al task sheet.

Las demas pruebas miran una regla a la vez. Estas caminan un servicio de
punta a punta, como llega de verdad: un transfer suelto de aeropuerto, un
proyecto de varios dias con hotel, uno que se mueve entre dos ciudades,
uno que el cliente nunca detalla, y uno que se cae con dinero afuera.

Sirven para lo que una prueba unitaria no ve: que las reglas, cada una
correcta por su lado, se estorben entre ellas.
"""
from decimal import Decimal

from ayudas import asignar, crear_servicio, depositar, jornada, manana


def _equipo(servicio):
    return servicio["equipos"][0]


def _programacion(cliente, h, servicio):
    return cliente.get(f"/servicios/{servicio['id']}/programacion",
                       headers=h).json()


def _poner_punto(cliente, h, jornada_id, direccion="Aeropuerto Benito Juarez",
                 lat="19.4361", lon="-99.0719", aeropuerto=True):
    r = cliente.patch(f"/operacion/jornadas/{jornada_id}/origen", json={
        "origen_direccion": direccion, "origen_lat": lat, "origen_lon": lon,
        "origen_aeropuerto": aeropuerto,
        "origen_google_aeropuerto": aeropuerto}, headers=h)
    assert r.status_code == 200, r.text


# ============================================================ escenario 1

def test_transfer_de_aeropuerto_de_un_solo_dia(cliente, sesion, datos):
    """Lo mas comun que entra: "recoge a mi director en el aeropuerto el
    martes". Un dia, un conductor, una unidad, y la hoja publicada."""
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(200), datos["modalidades"]["transfer"]["id"], hora="13:05:00",
        origen_direccion="Aeropuerto Benito Juarez, Terminal 1",
        origen_lat="19.4361", origen_lon="-99.0719",
        origen_aeropuerto=True, origen_google_aeropuerto=True,
        vuelo_aerolinea="United", vuelo_numero="UA 1518",
        vuelo_tipo="llegada",
        vuelo_hora=f"{manana(200)}T13:50:00")])

    # Con el minimo capturado, el servicio ya esta programado.
    assert servicio["estatus"] == "planeado"
    equipo = _equipo(servicio)
    dia = equipo["jornadas"][0]

    # El vuelo manda la hora: el equipo se presenta antes de que aterrice.
    assert dia["inicio_programado"] < f"{manana(200)}T13:50:00"
    # Y el aeropuerto ensancha la geocerca.
    assert dia["geocerca_metros"] == 2000

    asignar(cliente, h, dia["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])

    estado = _programacion(cliente, h, servicio)
    assert estado["listo"] is True and estado["faltantes"] == []

    r = cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion",
                     headers=h)
    assert r.status_code == 200, r.text

    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja",
                       headers=h)
    assert hoja.status_code == 200
    assert "UA 1518" in hoja.text, "el vuelo va en el meet and greet"


# ============================================================ escenario 2

def test_proyecto_de_tres_dias_con_hotel_y_viaticos(cliente, sesion, datos):
    """Un ejecutivo que llega el lunes y se va el miercoles: hotel,
    viaticos depositados y hospitales medidos desde donde duerme."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    fechas = [manana(210 + i) for i in range(3)]
    servicio = crear_servicio(cliente, h, datos, [
        jornada(f, datos["modalidades"]["full_day"]["id"], hora="07:00:00")
        for f in fechas])
    equipo = _equipo(servicio)

    for j in equipo["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
    # Solo el primer dia trae punto: el resto lo va diciendo el ejecutivo.
    _poner_punto(cliente, h, equipo["jornadas"][0]["id"])

    # El hotel, buscado en Google, entra al catalogo de la ciudad.
    r = cliente.post("/hospedajes", json={
        "equipo_id": equipo["id"], "nombre_libre": "hotel del sur",
        "direccion_libre": "Insurgentes Sur 4000",
        "telefono_libre": "+52 55 5000 2000",
        "hotel_lat": "19.2980", "hotel_lon": "-99.1620"}, headers=h)
    assert r.status_code == 201, r.text

    # Viaticos: el sistema propone, el consultor decide, finanzas paga.
    panel = cliente.get(f"/viaticos/equipos/{equipo['id']}", headers=h).json()
    fila = panel["personal"][0]
    assert float(fila["propuesto"]) > 0
    assert fila["estatus"] == "por_asignar"

    cliente.post(f"/viaticos/equipos/{equipo['id']}/persona",
                 json={"persona_id": fila["persona_id"],
                       "monto": str(fila["propuesto"])}, headers=h)
    cliente.post(f"/viaticos/equipos/{equipo['id']}/solicitar", json={},
                 headers=h)
    r = depositar(cliente, finanzas, equipo["id"], fila["persona_id"],
                  "SPEI 1001")
    assert r.status_code == 200, r.text

    panel = cliente.get(f"/viaticos/equipos/{equipo['id']}", headers=h).json()
    assert panel["personal"][0]["estatus"] == "depositado"
    assert panel["moneda"] == "MXN"

    # Y la hoja sale con la referencia medica desde el hotel.
    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()
    assert ficha["listo_para_publicar"] is True, ficha.get("faltantes")
    assert ficha["constantes"]["hospitales_desde"] == "hotel"
    assert ficha["hospedaje"][0]["hotel"] == "Hotel del Sur"


# ============================================================ escenario 3

def test_un_proyecto_que_se_mueve_entre_dos_ciudades(cliente, sesion, datos):
    """El ejecutivo trabaja lunes en Ciudad de Mexico y martes en
    Guadalajara. Son dos equipos, cada uno con su gente local, su ciudad
    y su propia hoja."""
    h = sesion("consultor")
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [
            {"plaza_id": datos["cdmx"]["id"], "jornadas": [jornada(
                manana(220), datos["modalidades"]["full_day"]["id"])]},
            {"plaza_id": datos["gdl"]["id"], "jornadas": [jornada(
                manana(221), datos["modalidades"]["full_day"]["id"])]},
        ]}, headers=h)
    assert r.status_code == 201, r.text
    servicio = r.json()
    alfa, beta = servicio["equipos"]
    assert (alfa["alias"], beta["alias"]) == ("Alfa", "Beta")

    # A cada equipo se le recomienda gente de SU ciudad.
    perfil = datos["perfiles"]["conductor_seguridad"]["id"]
    categoria = datos["categorias"]["suv_blindada"]["id"]
    for equipo, ciudad in ((alfa, "Ciudad de Mexico"), (beta, "Guadalajara")):
        r = cliente.get(f"/servicios/equipos/{equipo['id']}/recomendaciones"
                        f"?perfil_id={perfil}&categoria_id={categoria}",
                        headers=h).json()
        locales = r["personal"]["disponibles"] + r["personal"]["con_alerta"]
        assert locales, f"{equipo['alias']} se quedo sin gente local"
        assert all(p["ciudad"] == ciudad for p in locales), equipo["alias"]

    # Con dos equipos, la hoja del servicio ya no es una sola.
    r = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                    headers=h)
    assert r.status_code == 409
    assert len(r.json()["detail"]["equipos"]) == 2


# ============================================================ escenario 4

def test_el_cliente_que_no_comparte_la_agenda(cliente, sesion, datos):
    """Pasa seguido: dan el vuelo de llegada y nada mas. El conductor le
    pregunta al ejecutivo un dia antes. La hoja se publica igual."""
    h = sesion("consultor")
    fechas = [manana(230 + i) for i in range(3)]
    servicio = crear_servicio(cliente, h, datos, [
        jornada(f, datos["modalidades"]["full_day"]["id"], hora="07:00:00")
        for f in fechas])
    equipo = _equipo(servicio)

    for j in equipo["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
    _poner_punto(cliente, h, equipo["jornadas"][0]["id"])

    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()
    assert ficha["listo_para_publicar"] is True, ficha.get("faltantes")

    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja"
                       "?idioma=es", headers=h)
    assert hoja.status_code == 200
    # Los dias sin punto lo dicen, en vez de dejar creer que es el mismo.
    assert "confirma con el ejecutivo" in hoja.text


# ============================================================ escenario 5

def test_sin_unidad_propia_se_renta_y_el_servicio_se_cae(cliente, sesion, datos):
    """El cliente pide una categoria que no hay, se renta el auto, y a
    los dos dias el cliente se echa para atras. La renta no se cancela
    sola: le queda a finanzas."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(240), datos["modalidades"]["full_day"]["id"])])
    equipo = _equipo(servicio)

    r = cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                     json={"placa": "abc-000-z",
                           "categoria_id": datos["categorias"]["van_10"]["id"],
                           "color": "blanco", "marca_modelo": "sprinter",
                           "modelo_anio": 2025, "costo_diario": "4200",
                           "arrendadora": "avis", "arrendadora_telefono": "+52 55 5555 5555",
                           "motivo_renta": "categoria_no_disponible"},
                     headers=h)
    assert r.status_code == 201, r.text

    # La unidad rentada cuenta como unidad del dia.
    vista = cliente.get(f"/servicios/equipos/{equipo['id']}/asignaciones",
                        headers=h).json()
    assert vista["vehiculos"][0]["rentado"] is True

    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "El cliente se echo para atras"},
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["autos_rentados_por_devolver"] == ["ABC-000-Z"]

    pendientes = [x for pais in cliente.get(
        "/viaticos/finanzas/bandeja", headers=finanzas).json()["paises"]
        for x in pais["rentas"]]
    assert any(x["placa"] == "ABC-000-Z" for x in pendientes)


# ============================================================ escenario 6

def test_el_servicio_con_dinero_afuera_ya_no_se_borra(cliente, sesion, datos):
    """Antes del deposito, un error de captura se borra y ya. Despues no:
    ese dinero tiene que comprobarse, y el rastro se conserva."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(250), datos["modalidades"]["full_day"]["id"])])
    equipo = _equipo(servicio)
    persona = datos["personal"]["Juan Ramirez"]["id"]
    asignar(cliente, h, equipo["jornadas"][0]["id"], persona_id=persona,
            vehiculo_id=datos["suburban"]["id"])

    # Con viaticos asignados pero sin depositar, todavia se borra.
    cliente.post(f"/viaticos/equipos/{equipo['id']}/persona",
                 json={"persona_id": persona, "monto": "1500"}, headers=h)
    cliente.post(f"/viaticos/equipos/{equipo['id']}/solicitar", json={},
                 headers=h)
    depositar(cliente, finanzas, equipo["id"], persona)

    r = cliente.request("DELETE", f"/servicios/{servicio['id']}", headers=h)
    assert r.status_code == 409, r.text
    assert "cancelalo" in r.json()["detail"]["que_hacer"].lower()

    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "Ya no viaja el ejecutivo"}, headers=h)
    assert r.status_code == 200, r.text
    por_devolver = r.json()["viaticos_por_devolver"]
    assert por_devolver and Decimal(str(por_devolver[0]["monto"])) == Decimal("1500")


# ============================================================ escenario 7

def test_los_hospitales_son_de_la_ciudad_y_siempre_hay_uno_de_tercer_nivel(
        cliente, sesion, datos):
    """Un servicio en Guadalajara no se atiende con un hospital de
    Ciudad de Mexico. Y de los que hay, los mas cercanos, pero nunca sin
    un tercer nivel: una clinica a ochocientos metros no sustituye a un
    quirofano."""
    h = sesion("consultor")
    admin = sesion("admin")

    # Dos clinicas chicas pegadas al punto de encuentro.
    for nombre, lat, lon in (("Clinica Reforma", "19.4250", "-99.1702"),
                             ("Clinica Polanco", "19.4255", "-99.1710")):
        r = cliente.post("/catalogos/hospitales", json={
            "pais_id": datos["mx"]["id"], "plaza_id": datos["cdmx"]["id"],
            "nombre": nombre, "lat": lat, "lon": lon,
            "nivel_atencion": "primer_nivel"}, headers=admin)
        assert r.status_code == 201, r.text

    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(260), datos["modalidades"]["full_day"]["id"])])
    equipo = _equipo(servicio)
    asignar(cliente, h, equipo["jornadas"][0]["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    _poner_punto(cliente, h, equipo["jornadas"][0]["id"],
                 direccion="Paseo de la Reforma 500", lat="19.4247",
                 lon="-99.1700", aeropuerto=False)

    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()
    lista = ficha["constantes"]["hospitales_cercanos"]
    assert len(lista) == 3
    nombres = [x["nombre"] for x in lista]
    assert "Clinica Reforma" in nombres, "los de al lado si entran"
    assert any(x["nivel"] == "tercer_nivel" for x in lista), \
        "la lista nunca se queda sin quirofano"


def test_una_ciudad_sin_hospitales_lo_dice_en_vez_de_callarse(
        cliente, sesion, datos):
    """Que la hoja no diga nada se lee como que no hace falta. Lo que
    pasa es que a esa ciudad no le han cargado hospitales, y un hueco
    que se ve es un hueco que alguien tapa.

    Se prueba en Queretaro, que es la ciudad del catalogo a la que
    todavia no se le cargan hospitales. La gente y la unidad vienen de
    Guadalajara: mandar a alguien de otra ciudad es lo normal en una
    plaza donde no hay equipo propio, y no es lo que esta prueba mira.
    """
    h = sesion("consultor")
    plazas = {p["nombre"]: p for p in
              cliente.get("/catalogos/plazas", headers=h).json()}
    qro = plazas["Queretaro"]["id"]
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": qro, "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"plaza_id": qro, "jornadas": [jornada(
            manana(270), datos["modalidades"]["full_day"]["id"])]}],
    }, headers=h)
    assert r.status_code == 201, r.text
    servicio = r.json()
    equipo = _equipo(servicio)
    asignar(cliente, h, equipo["jornadas"][0]["id"],
            persona_id=datos["personal"]["Carlos Vega"]["id"],
            vehiculo_id=next(v["id"] for v in datos["vehiculos"]
                             if v["plaza_id"] == datos["gdl"]["id"]))
    _poner_punto(cliente, h, equipo["jornadas"][0]["id"],
                 direccion="Av. Antea 1000, Queretaro",
                 lat="20.5888", lon="-100.3899", aeropuerto=False)

    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()
    assert ficha["constantes"]["hospitales_cercanos"] == []

    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja"
                       "?idioma=es", headers=h)
    assert "Sin hospitales cargados para esta ciudad" in hoja.text

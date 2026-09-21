"""Task sheet: contenido, publicacion, versiones y quien lo ve."""
from ayudas import asignar, crear_servicio, jornada, manana


def _servicio_planeado(cliente, sesion, datos, offset=80, con_agenda=True,
                       con_hospedaje=True):
    h = sesion("consultor")
    fechas = [manana(offset), manana(offset + 1)]
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(f, datos["modalidades"]["full_day"]["id"]) for f in fechas],
        consultor_id=datos["personal"]["Ana Solis"]["id"])

    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        # Origen: el hotel sobre Reforma
        cliente.patch(f"/operacion/jornadas/{j['id']}/origen",
                      json={"origen_lat": "19.4270", "origen_lon": "-99.1677",
                            "geocerca_metros": 250,
                            "origen_direccion": "Paseo de la Reforma 500"},
                      headers=h)
        if con_agenda:
            cliente.put(f"/operacion/jornadas/{j['id']}/agenda", json={
                "resumen": "Traslados corporativos en Reforma y Polanco",
                "puntos": "08:00 Salida del hotel\n09:00 Oficinas Reforma\n"
                          "14:00 Comida Polanco\n18:00 Regreso al hotel"},
                headers=h)

    if con_hospedaje:
        cliente.post("/hospedajes", json={
            "servicio_id": servicio["id"], "hotel_id": datos["hoteles"][0]["id"],
            "habitacion": "1204", "desde": str(fechas[0]), "hasta": str(fechas[1]),
            "notas": "Entrada por lobby principal"}, headers=h)

    return servicio


def test_el_task_sheet_trae_equipo_unidad_y_agenda(cliente, sesion, datos):
    servicio = _servicio_planeado(cliente, sesion, datos, 80)
    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=sesion("consultor")).json()

    assert ficha["listo_para_publicar"] is True
    assert len(ficha["dias"]) == 2

    dia = ficha["dias"][0]
    assert dia["personal"][0]["nombre"] == "Juan Ramirez"
    assert dia["personal"][0]["telefono"], "el task sheet necesita el telefono"
    assert dia["unidades"][0]["placas"] == "ABC-1234"
    assert dia["unidades"][0]["blindada"] is True
    assert dia["agenda"]["resumen"]


def test_propone_los_tres_hospitales_mas_cercanos(cliente, sesion, datos):
    servicio = _servicio_planeado(cliente, sesion, datos, 83)
    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=sesion("consultor")).json()

    hospitales = ficha["dias"][0]["hospitales_cercanos"]
    assert len(hospitales) == 3, "deben ser los tres mas cercanos"
    distancias = [h["km"] for h in hospitales]
    assert distancias == sorted(distancias), "deben venir del mas cercano al mas lejano"
    # Desde Reforma 500, el Espanol y el Mocel quedan mas cerca que Medica Sur
    assert "Medica Sur" not in [h["nombre"] for h in hospitales]


def test_incluye_el_hospedaje_del_ejecutivo(cliente, sesion, datos):
    servicio = _servicio_planeado(cliente, sesion, datos, 86)
    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=sesion("consultor")).json()

    hospedaje = ficha["hospedaje"]
    assert len(hospedaje) == 1
    assert hospedaje[0]["hotel"], "debe traer el nombre del hotel"
    assert hospedaje[0]["direccion"], "debe traer la direccion del hotel"
    assert "habitacion" not in hospedaje[0], "nunca se sabe el numero de habitacion"


def test_trae_los_dos_niveles_de_escalacion(cliente, sesion, datos):
    servicio = _servicio_planeado(cliente, sesion, datos, 89)
    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=sesion("consultor")).json()

    niveles = ficha["escalacion"]
    assert [n["nivel"] for n in niveles] == [1, 2]
    assert niveles[0]["cargo"] == "Consultor asignado"
    assert niveles[1]["cargo"] == "Director de operaciones"


def test_se_publica_sin_agenda_porque_hay_clientes_que_no_la_dan(cliente, sesion, datos):
    """Hay clientes que comparten toda la agenda y otros que no la tienen:
    el servicio se va desarrollando sobre la marcha."""
    servicio = _servicio_planeado(cliente, sesion, datos, 92, con_agenda=False)
    h = sesion("consultor")

    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()
    assert ficha["listo_para_publicar"] is True
    assert ficha["dias"][0]["agenda_abierta"] is True

    r = cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                     json={}, headers=h)
    assert r.status_code == 200

    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja", headers=h)
    assert "Open itinerary" in hoja.text


def test_sin_punto_de_origen_no_se_publica(cliente, sesion, datos):
    """El origen si es obligatorio: de ahi sale la geocerca y los hospitales."""
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(93), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    # No se configura el origen

    r = cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                     json={}, headers=h)
    assert r.status_code == 409
    assert any("origen" in f for f in r.json()["detail"]["faltantes"])


def test_sin_unidad_asignada_no_se_publica(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(94), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"])
    cliente.patch(f"/operacion/jornadas/{j['id']}/origen",
                  json={"origen_lat": "19.4270", "origen_lon": "-99.1677",
                        "origen_direccion": "Reforma 500"}, headers=h)

    r = cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                     json={}, headers=h)
    assert r.status_code == 409
    assert any("unidad" in f for f in r.json()["detail"]["faltantes"])


def test_publicar_lo_comparte_y_cada_cambio_crea_version(cliente, sesion, datos):
    servicio = _servicio_planeado(cliente, sesion, datos, 95)
    h = sesion("consultor")

    primera = cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                           json={}, headers=h)
    assert primera.status_code == 200
    assert primera.json()["version"] == 1
    # Publicar no avisa: el correo sale solo si se pide.
    assert primera.json()["compartido_con"] == []

    segunda = cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                           json={"motivo": "Cambio de hora de presentacion"},
                           headers=h)
    assert segunda.json()["version"] == 2

    versiones = cliente.get(f"/task-sheets/servicio/{servicio['id']}/versiones",
                            headers=h).json()
    assert len(versiones) == 2
    assert versiones[1]["motivo_cambio"] == "Cambio de hora de presentacion"

    vigente = cliente.get(f"/task-sheets/servicio/{servicio['id']}", headers=h).json()
    assert vigente["version"] == 2


def test_publicar_no_manda_correo_y_avisar_si(cliente, sesion, datos):
    """El task sheet se corrige varias veces mientras se arma. Un correo
    por version le ensena al cliente a no abrir ninguno, y el que
    importaba era ese. Decision de Salvador (20 sep)."""
    servicio = _servicio_planeado(cliente, sesion, datos, 96)
    h = sesion("consultor")

    from app import models as m
    from app.db import SessionLocal

    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=h)
    with SessionLocal() as db:
        assert db.query(m.Notificacion).filter_by(
            servicio_id=servicio["id"]).count() == 0

    r = cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                     json={"motivo": "Cambio de hora", "avisar": True},
                     headers=h)
    assert r.json()["compartido_con"] == ["solicitante", "ejecutivo"]
    with SessionLocal() as db:
        avisos = (db.query(m.Notificacion)
                  .filter_by(servicio_id=servicio["id"]).all())
        assert len(avisos) == 2
        # Lo que cambio va en la ficha, no perdido al final del parrafo.
        assert any("Cambio de hora" in (a.datos or "") for a in avisos)


def test_el_personal_ve_el_de_sus_servicios_y_no_otros(cliente, sesion, datos):
    servicio = _servicio_planeado(cliente, sesion, datos, 98)
    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=sesion("consultor"))

    ruta = f"/task-sheets/servicio/{servicio['id']}"
    assert cliente.get(ruta, headers=sesion("juan")).status_code == 200
    assert cliente.get(ruta, headers=sesion("luis")).status_code == 403


def test_la_hoja_imprimible_se_genera(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = _servicio_planeado(cliente, sesion, datos, 101)
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    r = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja",
                    headers=sesion("consultor"))
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    for esperado in ("Juan Ramirez", "ABC-1234", "Hospital",
                     "Confidential", "Updated", "EP/E-"):
        assert esperado in r.text, f"la hoja debe mostrar {esperado}"


def test_lo_que_no_cambia_se_muestra_una_sola_vez(cliente, sesion, datos):
    """Mismo equipo y unidad todos los dias: no hay que repetirlos."""
    servicio = _servicio_planeado(cliente, sesion, datos, 104)
    h = sesion("consultor")
    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()

    assert ficha["constantes"] is not None
    assert ficha["constantes"]["personal"][0]["nombre"] == "Juan Ramirez"
    assert all(d["igual_todo_el_servicio"] for d in ficha["dias"])

    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=h)
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja", headers=h).text
    assert hoja.count("Juan Ramirez") == 1, "el conductor no debe repetirse por dia"
    assert hoja.count("ABC-1234") == 1, "la unidad no debe repetirse por dia"


def test_solo_el_dia_distinto_muestra_lo_que_cambia(cliente, sesion, datos):
    """El equipo base va arriba una vez. El dia que se sale de lo normal
    dice solo su diferencia; los demas dias no repiten nada."""
    servicio = _servicio_planeado(cliente, sesion, datos, 107)
    h = sesion("consultor")

    # Solo el segundo dia se suma un agente
    segunda = servicio["equipos"][0]["jornadas"][1]
    asignar(cliente, h, segunda["id"],
            persona_id=datos["personal"]["Miguel Torres"]["id"])

    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()

    # El base sigue existiendo: es el conductor con su unidad
    assert ficha["constantes"] is not None
    nombres_base = [p["nombre"] for p in ficha["constantes"]["personal"]]
    assert nombres_base == ["Juan Ramirez"]

    dias = ficha["dias"]
    assert dias[0]["igual_todo_el_servicio"] is True
    assert dias[1]["igual_todo_el_servicio"] is False
    assert [p["nombre"] for p in dias[1]["cambios"]["personal_se_suma"]] \
        == ["Miguel Torres"]

    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=h)
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja", headers=h).text
    assert hoja.count("Juan Ramirez") == 1, "el conductor base no se repite"
    assert hoja.count("Miguel Torres") == 1, "el agente solo en su dia"
    assert "Added this day" in hoja, "por defecto la hoja va en ingles"


def test_el_folio_y_los_alias_de_equipo(cliente, sesion, datos):
    """Folio AI-S consecutivo y equipos con alias del alfabeto griego."""
    from ayudas import crear_servicio, jornada, manana

    h = sesion("consultor")
    dia = manana(110)
    cuerpo = {
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "equipos": [
            {"jornadas": [jornada(dia, datos["modalidades"]["full_day"]["id"])]},
            {"jornadas": [jornada(dia, datos["modalidades"]["full_day"]["id"],
                                  hora="09:00:00")]},
            {"jornadas": [jornada(dia, datos["modalidades"]["transfer"]["id"],
                                  hora="11:00:00")]},
        ],
    }
    r = cliente.post("/servicios", json=cuerpo, headers=h)
    assert r.status_code == 201, r.text
    servicio = r.json()

    # Cada tipo lleva su serie: el eventual es la E.
    assert servicio["folio"].startswith("EP/E-"), servicio["folio"]
    numero = servicio["folio"].removeprefix("EP/E-")
    assert numero.isdigit() and len(numero) >= 3, "consecutivo de al menos 3 digitos"

    alias = [e["alias"] for e in servicio["equipos"]]
    assert alias == ["Alfa", "Beta", "Gamma"]


def test_la_senal_de_identificacion_va_en_hoja_aparte(cliente, sesion, datos):
    """Lo que el equipo muestra para que el ejecutivo los reconozca."""
    servicio = _servicio_planeado(cliente, sesion, datos, 113)
    h = sesion("consultor")

    r = cliente.put(f"/servicios/{servicio['id']}/senal",
                    json={"texto": "MR. CARTER",
                          "nota": "Cartel negro con letras blancas"}, headers=h)
    assert r.status_code == 200

    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()
    assert ficha["senal"]["texto"] == "MR. CARTER"

    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=h)
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja",
                       headers=h).text
    assert "MR. CARTER" in hoja
    assert "hoja-senal" in hoja
    assert "page-break-before" in hoja, "debe imprimirse en su propia hoja"


def test_la_senal_necesita_texto_o_imagen(cliente, sesion, datos):
    servicio = _servicio_planeado(cliente, sesion, datos, 116)
    r = cliente.put(f"/servicios/{servicio['id']}/senal", json={},
                    headers=sesion("consultor"))
    assert r.status_code == 400


def test_el_telefono_del_ejecutivo_aparece_en_la_hoja(cliente, sesion, datos):
    from ayudas import asignar, configurar_origen, crear_servicio, jornada, manana

    h = sesion("consultor")
    cuerpo = {
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "ejecutivo_nombre": "Mr. John Carter",
        "ejecutivo_correo": "jc@cliente.com",
        "ejecutivo_telefono": "+1 555 010 2030",
        "equipos": [{"jornadas": [
            jornada(manana(119), datos["modalidades"]["full_day"]["id"])]}],
    }
    servicio = cliente.post("/servicios", json=cuerpo, headers=h).json()
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    cliente.patch(f"/operacion/jornadas/{j['id']}/origen",
                  json={"origen_lat": "19.4270", "origen_lon": "-99.1677",
                        "origen_direccion": "Reforma 500"}, headers=h)

    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=h)
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja",
                       headers=h).text
    assert "+1 555 010 2030" in hoja


def test_el_hospedaje_va_al_final_y_el_equipo_arriba(cliente, sesion, datos):
    servicio = _servicio_planeado(cliente, sesion, datos, 122)
    h = sesion("consultor")
    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=h)
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja",
                       headers=h).text

    equipo = hoja.index("Security team")
    programa = hoja.index("Schedule</h3>")
    hospedaje = hoja.index("Accommodation")
    assert equipo < programa < hospedaje, \
        "primero quien va, luego que pasa cada dia, y al final donde se queda"


def test_las_horas_de_experiencia_aparecen_bajo_el_nombre(cliente, sesion, datos):
    """Lo que el ejecutivo quiere saber: a quien le esta confiando su seguridad."""
    from ayudas import ejecutar_jornada

    h = sesion("consultor")
    # Una jornada ya ejecutada le deja horas acumuladas a Juan
    pasado = _servicio_planeado(cliente, sesion, datos, 125, con_hospedaje=False)
    for j in pasado["equipos"][0]["jornadas"]:
        ejecutar_jornada(cliente, sesion("juan"), j)

    servicio = _servicio_planeado(cliente, sesion, datos, 130)
    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()

    persona = ficha["constantes"]["personal"][0]
    assert persona["horas_en_centauro"] >= 24, "dos full days ya suman 24 horas"

    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=h)
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja",
                       headers=h).text
    assert "h of service at Centauro" in hoja


def test_la_hoja_usa_los_colores_institucionales(cliente, sesion, datos):
    servicio = _servicio_planeado(cliente, sesion, datos, 134)
    h = sesion("consultor")
    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=h)
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja",
                       headers=h).text
    assert "#1B1546" in hoja, "el azul institucional de Centauro"
    assert "data:image/" in hoja or "CENTAURO" in hoja, \
        "el logo incrustado o la marca en texto"


def test_el_vehiculo_tampoco_se_repite(cliente, sesion, datos):
    """Misma regla para la unidad: arriba una vez, y solo el dia que cambia."""
    from ayudas import asignar

    servicio = _servicio_planeado(cliente, sesion, datos, 137)
    h = sesion("consultor")

    otra_unidad = next(v for v in datos["vehiculos"]
                       if v["id"] != datos["suburban"]["id"]
                       and v["plaza_id"] == datos["cdmx"]["id"])
    segunda = servicio["equipos"][0]["jornadas"][1]
    asignar(cliente, h, segunda["id"], vehiculo_id=otra_unidad["id"])

    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()
    placas_base = [u["placas"] for u in ficha["constantes"]["unidades"]]
    assert placas_base == [datos["suburban"]["placa"]]

    cambios = ficha["dias"][1]["cambios"]
    assert [u["placas"] for u in cambios["unidad_se_suma"]] == [otra_unidad["placa"]]

    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=h)
    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja",
                       headers=h).text
    assert hoja.count(datos["suburban"]["placa"]) == 1
    assert "Additional vehicle" in hoja


def test_un_task_sheet_por_equipo(cliente, sesion, datos):
    """Un servicio puede traer varios equipos; cada uno lleva el suyo
    y el ejecutivo de un equipo no ve al otro."""
    from ayudas import asignar, jornada, manana

    h = sesion("consultor")
    dia = manana(140)
    cuerpo = {
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "ejecutivo_nombre": "Mr. Carter",
        "equipos": [
            {"jornadas": [jornada(dia, datos["modalidades"]["full_day"]["id"])]},
            {"jornadas": [jornada(dia, datos["modalidades"]["full_day"]["id"])]},
        ],
    }
    servicio = cliente.post("/servicios", json=cuerpo, headers=h).json()
    alfa, beta = servicio["equipos"]
    assert [alfa["alias"], beta["alias"]] == ["Alfa", "Beta"]

    otra_unidad = next(v for v in datos["vehiculos"]
                       if v["id"] != datos["suburban"]["id"]
                       and v["plaza_id"] == datos["cdmx"]["id"])
    for equipo, persona, unidad in (
        (alfa, "Juan Ramirez", datos["suburban"]["id"]),
        (beta, "Luis Mendoza", otra_unidad["id"]),
    ):
        j = equipo["jornadas"][0]
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"][persona]["id"], vehiculo_id=unidad)
        cliente.patch(f"/operacion/jornadas/{j['id']}/origen",
                      json={"origen_lat": "19.4270", "origen_lon": "-99.1677",
                            "origen_direccion": "Reforma 500"}, headers=h)

    # Con dos equipos, el atajo por servicio avisa que hay que elegir
    r = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                    headers=h)
    assert r.status_code == 409
    assert len(r.json()["detail"]["equipos"]) == 2

    publicado = cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                             json={}, headers=h).json()
    assert len(publicado["equipos"]) == 2

    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    hoja_alfa = cliente.get(f"/task-sheets/equipo/{alfa['id']}/hoja",
                            headers=h).text
    assert "Juan Ramirez" in hoja_alfa
    assert "Luis Mendoza" not in hoja_alfa, "cada equipo ve solo lo suyo"
    assert "Team Alfa" in hoja_alfa

    # Y el personal de un equipo no alcanza el task sheet del otro
    assert cliente.get(f"/task-sheets/equipo/{beta['id']}",
                       headers=sesion("juan")).status_code == 403


def test_la_hoja_va_en_ingles_y_se_puede_pedir_en_espanol(cliente, sesion, datos):
    servicio = _servicio_planeado(cliente, sesion, datos, 145)
    h = sesion("consultor")
    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=h)

    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    ingles = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja",
                         headers=h).text
    assert "Security team" in ingles
    assert "Confidential" in ingles
    assert "Accommodation" in ingles

    espanol = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja?idioma=es",
                          headers=h).text
    assert "Equipo de seguridad" in espanol
    assert "Hospedaje" in espanol

    portugues = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja?idioma=pt",
                            headers=h).text
    assert "Equipe de segurança" in portugues


def test_la_hoja_dice_a_que_linea_de_operacion_pertenece(cliente, sesion, datos):
    """Vienen mas lineas de negocio: el documento tiene que decir en el
    encabezado que este servicio es de Proteccion Ejecutiva, con el mismo
    prefijo que lleva su folio."""
    servicio = _servicio_planeado(cliente, sesion, datos, 148)
    h = sesion("consultor")
    cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                 json={}, headers=h)

    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    ingles = cliente.get(f"/task-sheets/servicio/{servicio['id']}/hoja",
                         headers=h).text
    assert "AI/EP" in ingles
    assert "Executive Protection" in ingles

    espanol = cliente.get(
        f"/task-sheets/servicio/{servicio['id']}/hoja?idioma=es",
        headers=h).text
    assert "Protección Ejecutiva" in espanol


def test_el_hospedaje_no_necesita_fechas(cliente, sesion, datos):
    """Centauro no reserva el hotel: lo captura para que el equipo sepa a
    donde llegar. Las fechas serian las del servicio, que ya estan."""
    h = sesion("consultor")
    servicio = _servicio_planeado(cliente, sesion, datos, offset=95,
                                  con_hospedaje=False)

    r = cliente.post("/hospedajes", json={
        "servicio_id": servicio["id"], "hotel_id": datos["hoteles"][0]["id"],
        "habitacion": "1204"}, headers=h)
    assert r.status_code in (200, 201), r.text

    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                       headers=h).json()
    estancia = hoja["hospedaje"][0]
    assert estancia["hotel"]
    assert estancia["desde"] is None


def test_los_hospitales_se_miden_desde_el_punto_que_si_tiene_pin(
        cliente, sesion, datos):
    """Los dias de en medio pueden ir sin punto —el conductor lo pregunta
    un dia antes— y entonces el dia que mas se repite no tiene desde
    donde medir. La referencia medica sale del primer dia con pin, que es
    el meet and greet y siempre lo trae."""
    h = sesion("consultor")
    fechas = [manana(150), manana(151), manana(152)]
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(f, datos["modalidades"]["full_day"]["id"]) for f in fechas])

    jornadas = servicio["equipos"][0]["jornadas"]
    for j in jornadas:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])

    # Solo el primer dia trae punto: los otros dos, que son mayoria,
    # quedan sin decir donde arrancan.
    cliente.patch(f"/operacion/jornadas/{jornadas[0]['id']}/origen",
                  json={"origen_direccion": "Paseo de la Reforma 500",
                        "origen_lat": "19.4270", "origen_lon": "-99.1677"},
                  headers=h)

    ficha = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()
    assert ficha["listo_para_publicar"] is True, ficha.get("faltantes")
    hospitales = ficha["constantes"]["hospitales_cercanos"]
    assert hospitales, "la hoja tiene que traer la referencia medica"
    assert hospitales[0]["km"] is not None
    # Y la cabeza de la hoja tampoco se queda sin decir donde arranca.
    assert ficha["constantes"]["origen"] == "Paseo de la Reforma 500"


def test_los_hospitales_se_miden_desde_el_hotel(cliente, sesion, datos):
    """Ahi duerme el ejecutivo, y una emergencia de madrugada encuentra
    al equipo justo ahi. El punto de encuentro es el respaldo."""
    h = sesion("consultor")
    servicio = _servicio_planeado(cliente, sesion, datos, offset=160,
                                  con_hospedaje=False)
    equipo_id = servicio["equipos"][0]["id"]

    sin_hotel = cliente.get(
        f"/task-sheets/servicio/{servicio['id']}/vista-previa",
        headers=h).json()["constantes"]
    assert sin_hotel["hospitales_desde"] == "encuentro"

    # Un hotel al sur de la ciudad cambia cual queda mas cerca.
    r = cliente.post("/hospedajes", json={
        "equipo_id": equipo_id, "nombre_libre": "hotel del sur",
        "direccion_libre": "Insurgentes Sur 4000",
        "hotel_lat": "19.2980", "hotel_lon": "-99.1620"}, headers=h)
    assert r.status_code == 201, r.text

    con_hotel = cliente.get(
        f"/task-sheets/servicio/{servicio['id']}/vista-previa",
        headers=h).json()["constantes"]
    assert con_hotel["hospitales_desde"] == "hotel"
    assert (con_hotel["hospitales_cercanos"][0]["nombre"]
            != sin_hotel["hospitales_cercanos"][0]["nombre"]), \
        "desde el sur el mas cercano es otro"
    assert con_hotel["hospitales_cercanos"][0]["km"] < 5

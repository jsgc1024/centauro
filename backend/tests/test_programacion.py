"""Cuando un servicio queda programado y cuando no.

El minimo del alta: cliente, quien solicita, el dia con su hora de inicio
y el punto donde arranca el servicio (direccion, vuelo, o los dos).
"""
from datetime import date, timedelta

MANANA = date.today() + timedelta(days=1)


def alta(cliente, headers, datos, **extra):
    """Alta con el minimo, salvo lo que la prueba quiera quitar o cambiar."""
    jornada = {
        "fecha": str(MANANA),
        "modalidad_id": datos["modalidades"]["transfer"]["id"],
        "hora_presentacion": "14:20:00",
        "origen_direccion": "Aeropuerto Benito Juarez, Terminal 1",
    }
    jornada.update(extra.pop("jornada", {}))
    cuerpo = {
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [jornada]}],
    }
    cuerpo.update(extra)
    return cliente.post("/servicios", json=cuerpo, headers=headers)


def test_el_minimo_deja_el_servicio_programado(cliente, sesion, datos):
    r = alta(cliente, sesion("consultor"), datos)
    assert r.status_code == 201, r.text
    assert r.json()["estatus"] == "planeado"

    estado = cliente.get(f"/servicios/{r.json()['id']}/programacion",
                         headers=sesion("consultor")).json()
    assert estado["listo"] is True
    assert estado["faltantes"] == []


def test_los_datos_del_vuelo_bastan_como_punto_de_inicio(cliente, sesion, datos):
    """Sin direccion escrita, pero con el vuelo: el servicio ya se puede
    programar. La direccion sigue haciendo falta para el task sheet."""
    r = alta(cliente, sesion("consultor"), datos, jornada={
        "origen_direccion": None,
        "vuelo_aerolinea": "United", "vuelo_numero": "UA 1518",
        "vuelo_hora": f"{MANANA}T13:50:00", "vuelo_tipo": "llegada"})
    assert r.status_code == 201, r.text
    assert r.json()["estatus"] == "planeado"


def test_sin_solicitante_no_queda_programado(cliente, sesion, datos):
    r = alta(cliente, sesion("consultor"), datos, solicitante_nombre=None)
    assert r.status_code == 201, r.text
    assert r.json()["estatus"] == "borrador"

    estado = cliente.get(f"/servicios/{r.json()['id']}/programacion",
                         headers=sesion("consultor")).json()
    assert estado["listo"] is False
    assert any("solicita" in f.lower() for f in estado["faltantes"])


def test_sin_punto_de_inicio_no_queda_programado(cliente, sesion, datos):
    r = alta(cliente, sesion("consultor"), datos,
             jornada={"origen_direccion": None})
    assert r.status_code == 201, r.text
    assert r.json()["estatus"] == "borrador"

    estado = cliente.get(f"/servicios/{r.json()['id']}/programacion",
                         headers=sesion("consultor")).json()
    assert any("punto de inicio" in f.lower() for f in estado["faltantes"])


def test_capturar_el_origen_despues_completa_la_programacion(cliente, sesion, datos):
    """El alta sin punto de inicio queda en borrador; en cuanto se captura
    la direccion, el servicio pasa a programado solo."""
    h = sesion("consultor")
    r = alta(cliente, h, datos, jornada={"origen_direccion": None})
    servicio = r.json()
    jornada_id = servicio["equipos"][0]["jornadas"][0]["id"]

    puesto = cliente.patch(f"/operacion/jornadas/{jornada_id}/origen",
                           json={"origen_direccion": "Las Alcobas, Polanco - lobby"},
                           headers=h)
    assert puesto.status_code == 200, puesto.text
    assert puesto.json()["con_pin"] is False

    estado = cliente.get(f"/servicios/{servicio['id']}/programacion",
                         headers=h).json()
    assert estado["estatus"] == "planeado"


def test_la_direccion_no_borra_el_pin_ni_el_pin_la_direccion(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = alta(cliente, h, datos).json()
    jornada_id = servicio["equipos"][0]["jornadas"][0]["id"]

    cliente.patch(f"/operacion/jornadas/{jornada_id}/origen",
                  json={"origen_lat": "19.4361", "origen_lon": "-99.0719",
                        "geocerca_metros": 300}, headers=h)
    r = cliente.patch(f"/operacion/jornadas/{jornada_id}/origen",
                      json={"origen_direccion": "Terminal 1, llegadas"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["con_pin"] is True
    assert r.json()["geocerca_metros"] == 300
    assert r.json()["direccion"] == "Terminal 1, llegadas"


def test_el_alta_guarda_el_vuelo_del_primer_dia(cliente, sesion, datos):
    h = sesion("consultor")
    r = alta(cliente, h, datos, jornada={
        "vuelo_aerolinea": "United", "vuelo_numero": "UA 1518",
        "vuelo_hora": f"{MANANA}T13:50:00", "vuelo_origen": "Houston",
        "vuelo_tipo": "llegada"})
    servicio = r.json()
    jornada_id = servicio["equipos"][0]["jornadas"][0]["id"]

    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                       headers=h).json()
    vuelo = hoja["dias"][0]["vuelo"]
    assert vuelo["numero"] == "UA 1518"
    assert vuelo["procedencia"] == "Houston"
    # El equipo llega 45 minutos antes de que aterrice el vuelo.
    assert hoja["dias"][0]["llegada_equipo"]["hora"] == "13:05"
    assert jornada_id  # la jornada existe y es la del dia 1


def test_la_central_no_puede_dar_de_alta_un_servicio(cliente, sesion, datos):
    """La actividad servicios.alta es del consultor y de operaciones."""
    r = alta(cliente, sesion("central"), datos)
    assert r.status_code == 403
    assert r.json()["detail"]["actividad"] == "servicios.alta"


# ---------------------------------------------------------------- asignado

def test_con_equipo_y_unidad_el_servicio_pasa_a_asignado(cliente, sesion, datos):
    """Planeado es 'ya se sabe que, cuando y donde'. Asignado es 'ya se
    sabe quien y con que unidad', en todos los dias del servicio."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos).json()
    assert servicio["estatus"] == "planeado"
    jornada_id = servicio["equipos"][0]["jornadas"][0]["id"]

    persona = datos["personal"]["Luis Mendoza"]
    r = cliente.post(f"/servicios/jornadas/{jornada_id}/asignar-personal",
                     json={"persona_id": persona["id"], "forzar": True}, headers=h)
    assert r.status_code == 200, r.text
    # Con personal pero sin unidad todavia no: falta la mitad.
    assert r.json()["estatus_servicio"] == "planeado"
    assert r.json()["faltantes_de_recursos"]

    r = cliente.post(f"/servicios/jornadas/{jornada_id}/asignar-vehiculo",
                     json={"vehiculo_id": datos["suburban"]["id"], "forzar": True},
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["estatus_servicio"] == "asignado"
    assert r.json()["faltantes_de_recursos"] == []


def test_un_dia_sin_recursos_deja_el_servicio_en_planeado(cliente, sesion, datos):
    """Basta con que un solo dia quede sin equipo para que el servicio no
    se pueda dar por asignado."""
    h = sesion("consultor")
    segundo = MANANA + timedelta(days=1)
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [
            {"fecha": str(MANANA),
             "modalidad_id": datos["modalidades"]["transfer"]["id"],
             "hora_presentacion": "14:20:00",
             "origen_direccion": "Aeropuerto Benito Juarez, Terminal 1"},
            {"fecha": str(segundo),
             "modalidad_id": datos["modalidades"]["full_day"]["id"],
             "hora_presentacion": "08:00:00"},
        ]}]}, headers=h)
    assert r.status_code == 201, r.text
    servicio = r.json()
    assert servicio["estatus"] == "planeado"

    primera = min(servicio["equipos"][0]["jornadas"], key=lambda j: j["fecha"])
    persona = datos["personal"]["Luis Mendoza"]
    cliente.post(f"/servicios/jornadas/{primera['id']}/asignar-personal",
                 json={"persona_id": persona["id"], "forzar": True}, headers=h)
    r = cliente.post(f"/servicios/jornadas/{primera['id']}/asignar-vehiculo",
                     json={"vehiculo_id": datos["suburban"]["id"], "forzar": True},
                     headers=h)
    assert r.status_code == 200, r.text
    # El segundo dia sigue sin nadie: el servicio no puede darse por asignado.
    assert r.json()["estatus_servicio"] == "planeado"
    assert len(r.json()["faltantes_de_recursos"]) == 1
    assert str(segundo) in r.json()["faltantes_de_recursos"][0]


# ---------------------------------------------------------------- el nombre

def test_el_nombre_y_los_apellidos_se_juntan_al_mostrarlos(cliente, sesion, datos):
    """Se capturan aparte para poder saludar por el nombre; se muestran
    juntos donde se lee la ficha."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos).json()
    assert servicio["solicitante_completo"] == "Karen Whitfield"
    assert servicio["ejecutivo_completo"] == "James Caldwell"

    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                       headers=h).json()
    assert hoja["ejecutivo"] == "James Caldwell"
    assert hoja["solicitante"] == "Karen Whitfield"


def test_sin_apellidos_el_servicio_no_queda_planeado(cliente, sesion, datos):
    r = alta(cliente, sesion("consultor"), datos, solicitante_apellidos=None)
    assert r.status_code == 201, r.text
    assert r.json()["estatus"] == "borrador"

    estado = cliente.get(f"/servicios/{r.json()['id']}/programacion",
                         headers=sesion("consultor")).json()
    assert any("apellidos" in f.lower() for f in estado["faltantes"])


def test_solo_el_nombre_se_muestra_solo(cliente, sesion, datos):
    """Un ejecutivo con nombre y sin apellidos no sale con un espacio
    colgando al final, aunque asi el servicio no quede planeado."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos, ejecutivo_apellidos=None).json()
    assert servicio["ejecutivo_completo"] == "James"


def test_la_geocerca_cubre_medio_kilometro_alrededor_del_punto(cliente, sesion, datos):
    """El circulo se dibuja sobre el mismo pin del punto de encuentro. En una
    direccion normal abarca medio kilometro: con mas, el conductor quedaba
    dentro desde varias cuadras antes y la llegada no probaba nada. El
    aeropuerto se ensancha aparte, cuando el punto se marca como tal."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos, jornada={
        "origen_direccion": "Aeropuerto Benito Juarez, Terminal 1",
        "origen_lat": "19.4361", "origen_lon": "-99.0719"}).json()
    jornada_id = servicio["equipos"][0]["jornadas"][0]["id"]

    r = cliente.patch(f"/operacion/jornadas/{jornada_id}/origen",
                      json={"origen_direccion": "Terminal 1, llegadas"},
                      headers=h)
    assert r.json()["geocerca_metros"] == 500
    assert r.json()["con_pin"] is True


def test_sin_ejecutivo_el_servicio_no_queda_planeado(cliente, sesion, datos):
    """El servicio es para alguien: sin saber a quien se protege no esta
    planeado. El correo y el telefono si pueden llegar despues, porque hay
    clientes que no los dan."""
    r = alta(cliente, sesion("consultor"), datos, ejecutivo_nombre=None)
    assert r.status_code == 201, r.text
    assert r.json()["estatus"] == "borrador"

    estado = cliente.get(f"/servicios/{r.json()['id']}/programacion",
                         headers=sesion("consultor")).json()
    assert any("ejecutivo" in f.lower() for f in estado["faltantes"])


def test_el_ejecutivo_sin_correo_ni_telefono_si_queda_planeado(cliente, sesion, datos):
    r = alta(cliente, sesion("consultor"), datos,
             ejecutivo_correo=None, ejecutivo_telefono=None)
    assert r.status_code == 201, r.text
    assert r.json()["estatus"] == "planeado"

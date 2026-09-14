"""Quien va a bordo de que unidad.

Solo importa cuando el equipo lleva dos o mas unidades. El dato vive en
la asignacion de la persona: una unidad lleva varias personas, pero una
persona va en una sola.
"""
from datetime import date, timedelta

MANANA = date.today() + timedelta(days=1)


def jornada_con_equipo(cliente, h, datos):
    """Un dia con dos personas y dos unidades asignadas."""
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "equipos": [{"jornadas": [{
            "fecha": str(MANANA),
            "modalidad_id": datos["modalidades"]["full_day"]["id"],
            "hora_presentacion": "08:00:00",
            "origen_direccion": "Las Alcobas, Polanco - lobby",
            # La hoja no se publica sin el pin: de ahi salen la geocerca
            # y los hospitales cercanos.
            "origen_lat": "19.4284", "origen_lon": "-99.1957"}]}],
    }, headers=h)
    assert r.status_code == 201, r.text
    servicio = r.json()
    jornada_id = servicio["equipos"][0]["jornadas"][0]["id"]

    equipo_id = servicio["equipos"][0]["id"]
    for persona in ("Luis Mendoza", "Juan Ramirez"):
        r = cliente.post(f"/servicios/equipos/{equipo_id}/asignar-personal",
                         json={"persona_id": datos["personal"][persona]["id"],
                               "forzar": True}, headers=h)
        assert r.status_code == 200, r.text
    # Dos unidades: es el caso en el que hay que decir quien aborda cual.
    segunda = next(v for v in datos["vehiculos"]
                   if v["id"] != datos["suburban"]["id"])
    for unidad in (datos["suburban"], segunda):
        r = cliente.post(f"/servicios/equipos/{equipo_id}/asignar-vehiculo",
                         json={"vehiculo_id": unidad["id"], "forzar": True},
                         headers=h)
        assert r.status_code == 200, r.text
    return servicio, jornada_id, segunda


def test_una_persona_se_liga_a_la_unidad_que_aborda(cliente, sesion, datos):
    h = sesion("consultor")
    _, jornada_id, segunda = jornada_con_equipo(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]

    r = cliente.patch(
        f"/servicios/jornadas/{jornada_id}/personal/{persona['id']}/unidad",
        json={"vehiculo_id": datos["suburban"]["id"]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["placa"] == datos["suburban"]["placa"]

    vista = cliente.get(f"/servicios/jornadas/{jornada_id}/asignaciones",
                        headers=h).json()
    quien = next(p for p in vista["personal"] if p["persona_id"] == persona["id"])
    assert quien["abordo"] == datos["suburban"]["placa"]
    # A quien no se le dijo nada se queda sin unidad, no en la primera.
    otro = next(p for p in vista["personal"] if p["persona_id"] != persona["id"])
    assert otro["abordo"] is None


def test_no_se_puede_subir_a_alguien_a_una_unidad_de_otro_dia(cliente, sesion, datos):
    """La unidad tiene que estar asignada a esa misma jornada: si no, el
    consultor estaria mandando a su gente a un vehiculo que trae otro
    equipo."""
    h = sesion("consultor")
    _, jornada_id, segunda = jornada_con_equipo(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]

    ajena = next(v for v in cliente.get("/catalogos/vehiculos", headers=h).json()
                 if v["id"] not in (datos["suburban"]["id"], segunda["id"]))
    r = cliente.patch(
        f"/servicios/jornadas/{jornada_id}/personal/{persona['id']}/unidad",
        json={"vehiculo_id": ajena["id"]}, headers=h)
    assert r.status_code == 400
    assert "no esta asignada" in r.json()["detail"]["mensaje"]


def test_se_puede_desligar(cliente, sesion, datos):
    h = sesion("consultor")
    _, jornada_id, segunda = jornada_con_equipo(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]
    ruta = f"/servicios/jornadas/{jornada_id}/personal/{persona['id']}/unidad"

    cliente.patch(ruta, json={"vehiculo_id": datos["suburban"]["id"]}, headers=h)
    r = cliente.patch(ruta, json={"vehiculo_id": None}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["vehiculo_id"] is None


def test_quien_no_esta_asignado_no_aborda_nada(cliente, sesion, datos):
    h = sesion("consultor")
    _, jornada_id, segunda = jornada_con_equipo(cliente, h, datos)
    ajeno = next(p for p in cliente.get("/catalogos/personal", headers=h).json()
                 if p["nombre"] not in ("Luis Mendoza", "Juan Ramirez"))

    r = cliente.patch(
        f"/servicios/jornadas/{jornada_id}/personal/{ajeno['id']}/unidad",
        json={"vehiculo_id": datos["suburban"]["id"]}, headers=h)
    assert r.status_code == 404


def test_la_hoja_dice_quien_aborda_cual_solo_con_mas_de_una_unidad(
        cliente, sesion, datos):
    """Con una sola unidad la linea seria la misma debajo de cada
    persona; con dos, es lo que ordena las salidas."""
    h = sesion("consultor")
    servicio, jornada_id, _ = jornada_con_equipo(cliente, h, datos)
    persona = datos["personal"]["Luis Mendoza"]
    cliente.patch(
        f"/servicios/jornadas/{jornada_id}/personal/{persona['id']}/unidad",
        json={"vehiculo_id": datos["suburban"]["id"]}, headers=h)

    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                       headers=h).json()
    quien = next(p for p in hoja["constantes"]["personal"]
                 if p["nombre"] == persona["nombre"])
    assert quien["abordo"] == datos["suburban"]["placa"]

    publicado = cliente.post(
        f"/task-sheets/servicio/{servicio['id']}/publicar",
        json={"motivo": "prueba de abordo"}, headers=h)
    assert publicado.status_code in (200, 201), publicado.text

    cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion", headers=h)
    impresa = cliente.get(
        f"/task-sheets/servicio/{servicio['id']}/hoja?idioma=es", headers=h)
    assert impresa.status_code == 200, impresa.text
    assert "Aborda" in impresa.text
    assert datos["suburban"]["placa"] in impresa.text


# ------------------------------------------------ recursos por equipo

def test_el_recurso_se_asigna_a_todos_los_dias_del_equipo(cliente, sesion, datos):
    """El conductor que recoge al ejecutivo el lunes es el que lo lleva al
    aeropuerto el jueves: se decide una vez, no dia por dia."""
    h = sesion("consultor")
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [
            {"fecha": str(MANANA),
             "modalidad_id": datos["modalidades"]["full_day"]["id"],
             "hora_presentacion": "08:00:00",
             "origen_direccion": "Las Alcobas, Polanco - lobby"},
            {"fecha": str(MANANA + timedelta(days=1)),
             "modalidad_id": datos["modalidades"]["full_day"]["id"]},
            {"fecha": str(MANANA + timedelta(days=2)),
             "modalidad_id": datos["modalidades"]["full_day"]["id"]},
        ]}]}, headers=h)
    assert r.status_code == 201, r.text
    servicio = r.json()
    equipo_id = servicio["equipos"][0]["id"]

    persona = datos["personal"]["Luis Mendoza"]
    r = cliente.post(f"/servicios/equipos/{equipo_id}/asignar-personal",
                     json={"persona_id": persona["id"], "forzar": True},
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["dias"] == 3

    r = cliente.post(f"/servicios/equipos/{equipo_id}/asignar-vehiculo",
                     json={"vehiculo_id": datos["suburban"]["id"],
                           "forzar": True}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["dias"] == 3
    # Con todos los dias cubiertos el servicio pasa a asignado.
    assert r.json()["estatus_servicio"] == "asignado"

    vista = cliente.get(f"/servicios/equipos/{equipo_id}/asignaciones",
                        headers=h).json()
    assert vista["dias"] == 3
    assert vista["personal"][0]["dias"] == 3
    assert vista["vehiculos"][0]["dias"] == 3


def test_quien_no_esta_libre_todos_los_dias_no_se_asigna(cliente, sesion, datos):
    """De nada sirve el conductor libre el lunes si el miercoles trae
    otro servicio: se avisa antes, no a media semana."""
    h = sesion("consultor")
    persona = datos["personal"]["Luis Mendoza"]

    # Un servicio de un dia se lleva al conductor ese miercoles.
    ocupado = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [{
            "fecha": str(MANANA + timedelta(days=2)),
            "modalidad_id": datos["modalidades"]["full_day"]["id"],
            "hora_presentacion": "08:00:00",
            "origen_direccion": "Otro punto"}]}]}, headers=h).json()
    cliente.post(f"/servicios/equipos/{ocupado['equipos'][0]['id']}"
                 "/asignar-personal",
                 json={"persona_id": persona["id"], "forzar": True}, headers=h)

    # Y ahora se le quiere para los tres dias, uno de los cuales choca.
    nuevo = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [
            {"fecha": str(MANANA),
             "modalidad_id": datos["modalidades"]["full_day"]["id"],
             "hora_presentacion": "08:00:00",
             "origen_direccion": "Las Alcobas"},
            {"fecha": str(MANANA + timedelta(days=2)),
             "modalidad_id": datos["modalidades"]["full_day"]["id"]},
        ]}]}, headers=h).json()

    r = cliente.post(f"/servicios/equipos/{nuevo['equipos'][0]['id']}"
                     "/asignar-personal",
                     json={"persona_id": persona["id"], "forzar": True},
                     headers=h)
    assert r.status_code == 409
    assert "todos los dias" in r.json()["detail"]["mensaje"]
    # Y no se asigno ninguno: dejar el servicio a medias es peor.
    vista = cliente.get(f"/servicios/equipos/{nuevo['equipos'][0]['id']}"
                        "/asignaciones", headers=h).json()
    assert vista["personal"] == []


def test_confirmar_la_asignacion_es_la_firma_del_consultor(cliente, sesion, datos):
    """Que el sistema vea gente y unidad todos los dias no basta: el
    consultor puede estar probando quien cabe. Confirmar cierra su parte."""
    h = sesion("consultor")
    servicio, jornada_id, _ = jornada_con_equipo(cliente, h, datos)

    # Con dias sin recursos todavia no se puede confirmar.
    equipo_id = servicio["equipos"][0]["id"]
    otro = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [{
            "fecha": str(MANANA),
            "modalidad_id": datos["modalidades"]["transfer"]["id"],
            "hora_presentacion": "07:30:00",
            "origen_direccion": "Aeropuerto Benito Juarez, T1"}]}],
    }, headers=h).json()
    r = cliente.post(f"/servicios/{otro['id']}/confirmar-asignacion", headers=h)
    assert r.status_code == 409
    assert "sin equipo o sin unidad" in r.json()["detail"]["mensaje"]

    # El que si tiene todo se confirma y queda firmado.
    r = cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion",
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["confirmada_en"]
    assert equipo_id and jornada_id

    de_nuevo = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    assert de_nuevo["asignacion_confirmada_en"] is not None


# ------------------------------------------------------ quitar recursos

def test_se_quita_a_una_persona_de_todos_los_dias(cliente, sesion, datos):
    """Asignar sin poder desasignar deja al consultor probando quien cabe
    sin marcha atras."""
    h = sesion("consultor")
    servicio, jornada_id, _ = jornada_con_equipo(cliente, h, datos)
    equipo_id = servicio["equipos"][0]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]

    r = cliente.request(
        "DELETE", f"/servicios/equipos/{equipo_id}/personal/{luis}", headers=h)
    assert r.status_code == 200, r.text

    vista = cliente.get(f"/servicios/equipos/{equipo_id}/asignaciones",
                        headers=h).json()
    assert all(p["persona_id"] != luis for p in vista["personal"])
    assert len(vista["personal"]) == 1, "el otro se queda"


def test_al_quitar_la_unidad_nadie_se_queda_a_bordo_de_ella(
        cliente, sesion, datos):
    """Quien iba en esa unidad se queda sin unidad, no colgado de una que
    ya no va."""
    h = sesion("consultor")
    servicio, jornada_id, _ = jornada_con_equipo(cliente, h, datos)
    equipo_id = servicio["equipos"][0]["id"]
    unidad = datos["suburban"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]

    cliente.patch(f"/servicios/equipos/{equipo_id}/personal/{luis}/unidad",
                  json={"vehiculo_id": unidad}, headers=h)

    r = cliente.request(
        "DELETE", f"/servicios/equipos/{equipo_id}/vehiculos/{unidad}",
        headers=h)
    assert r.status_code == 200, r.text

    vista = cliente.get(f"/servicios/equipos/{equipo_id}/asignaciones",
                        headers=h).json()
    assert all(v["vehiculo_id"] != unidad for v in vista["vehiculos"])
    quien = next(p for p in vista["personal"] if p["persona_id"] == luis)
    assert quien["abordo"] is None


def test_no_se_quita_a_quien_ya_recibio_viaticos(cliente, sesion, datos):
    """Ese dinero tiene que comprobarse. Sacarlo de la lista lo dejaria
    sin dueno: para eso esta el reemplazo por contingencia."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    servicio, _, _ = jornada_con_equipo(cliente, h, datos)
    equipo_id = servicio["equipos"][0]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]

    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": luis, "monto": "1200"}, headers=h)
    cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar",
                 json={"persona_id": luis}, headers=h)
    cliente.post("/viaticos/finanzas/depositar",
                 json={"equipo_id": equipo_id, "persona_id": luis},
                 headers=finanzas)

    r = cliente.request(
        "DELETE", f"/servicios/equipos/{equipo_id}/personal/{luis}", headers=h)
    assert r.status_code == 409, r.text


def test_antes_del_deposito_se_quita_con_todo_y_viaticos(cliente, sesion, datos):
    """Lo que nunca salio de la caja se va con la persona, sin dejar un
    viatico huerfano que cuadrar despues."""
    h = sesion("consultor")
    servicio, _, _ = jornada_con_equipo(cliente, h, datos)
    equipo_id = servicio["equipos"][0]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]

    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": luis, "monto": "1200"}, headers=h)
    r = cliente.request(
        "DELETE", f"/servicios/equipos/{equipo_id}/personal/{luis}", headers=h)
    assert r.status_code == 200, r.text

    panel = cliente.get(f"/viaticos/equipos/{equipo_id}", headers=h).json()
    assert all(f["persona_id"] != luis for f in panel["personal"])
    assert float(panel["total_asignado"]) == 0

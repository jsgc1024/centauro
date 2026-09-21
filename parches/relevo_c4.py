"""Paso C4: las pruebas del regreso."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/tests/test_relevo.py"
s = R.read_text()

ANCLA = "# ================================================== la raya con implantado"
NUEVO = '''# ================================================== el regreso del titular

def _regreso(cliente, sesion, reemplazo_id, dia, **extra):
    return cliente.post(f"/contingencia/reemplazos/{reemplazo_id}/regreso",
                        headers=sesion("consultor"),
                        json={"desde": dia, **extra})


def test_el_regreso_cierra_el_cambio_no_abre_otro(cliente, sesion, datos):
    """Un solo hecho: "Luis cubrio a Juan del 2 al 3".

    Si el regreso abriera su propio movimiento, el mismo mes mostraria
    dos cambios cruzados —Luis por Juan, Juan por Luis— y nadie sabria
    cual cierra a cual. El regreso recorre el `hasta` del que ya existe.
    """
    servicio = _montado(cliente, sesion, datos, offset=520, dias=5)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")

    # Sin fecha de fin: del segundo dia en adelante es de Luis.
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()
    assert hecho["jornadas_afectadas"] == [d["fecha"] for d in dias[1:]]

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[3]["fecha"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["regresa"] == "Juan Ramirez"
    assert cuerpo["sale"] == "Luis Mendoza"
    assert cuerpo["desde"] == dias[1]["fecha"]
    assert cuerpo["hasta"] == dias[2]["fecha"]
    assert cuerpo["dias_cubiertos"] == 2

    esperado = ["Juan Ramirez", "Luis Mendoza", "Luis Mendoza",
                "Juan Ramirez", "Juan Ramirez"]
    for dia, quien in zip(dias, esperado):
        assert _asignados(cliente, sesion, dia["id"]) == [quien], dia["fecha"]

    # Un movimiento, no dos.
    historial = cliente.get(
        f"/contingencia/reemplazos/servicio/{servicio['id']}", headers=h).json()
    assert len(historial) == 1, historial
    assert historial[0]["desde"] == dias[1]["fecha"]
    assert historial[0]["hasta"] == dias[2]["fecha"]
    assert historial[0]["jornadas_afectadas"] == 2
    assert historial[0]["regreso_en"], "no quedo firmado quien lo cerro"
    assert historial[0]["regreso_por"] == "Ana Solis"


def test_el_que_cubria_cobra_la_manana_del_dia_del_regreso(cliente, sesion, datos):
    """El regreso tambien parte el dia, con los nombres al reves.

    Si Luis alcanzo a marcar su llegada la manana que Juan volvio, ese
    dia lo trabajaron los dos y los dos lo cobran. Y ese dia sigue
    contando como cubierto por Luis: el `hasta` es ese, no el anterior.
    """
    servicio = _montado(cliente, sesion, datos, offset=600, dias=4)
    dias = servicio["equipos"][0]["jornadas"]
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()

    inicio = datetime.fromisoformat(dias[2]["inicio_programado"])
    llego = marcar(cliente, sesion("luis"), dias[2]["id"], "llegada_origen",
                   inicio - timedelta(minutes=10))
    assert llego.status_code == 200, llego.text

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[2]["fecha"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["dias_partidos"] == [dias[2]["fecha"]]
    assert cuerpo["hasta"] == dias[2]["fecha"]
    assert cuerpo["dias_cubiertos"] == 2

    # Ese dia el equipo tiene dos personas en el mismo rol: la que salio
    # a media jornada y la que entro.
    assert sorted(_asignados(cliente, sesion, dias[2]["id"])) == [
        "Juan Ramirez", "Luis Mendoza"]
    assert _asignados(cliente, sesion, dias[3]["id"]) == ["Juan Ramirez"]


def test_el_regreso_no_puede_ser_antes_de_que_empiece_el_cambio(cliente, sesion,
                                                                datos):
    """Si el cambio se hizo por error, se deshace; no se "regresa" al
    dia anterior."""
    servicio = _montado(cliente, sesion, datos, offset=640, dias=4)
    dias = servicio["equipos"][0]["jornadas"]
    hecho = _relevo(cliente, sesion, datos, dias[2]).json()

    for dia in (dias[1], dias[2]):
        r = _regreso(cliente, sesion, hecho["reemplazo_id"], dia["fecha"])
        assert r.status_code == 409, (dia["fecha"], r.text)

    # Y una sola vez: el segundo regreso ya no tiene que cerrar.
    assert _regreso(cliente, sesion, hecho["reemplazo_id"],
                    dias[3]["fecha"]).status_code == 200
    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[3]["fecha"])
    assert r.status_code == 409, r.text


def test_marta_regresa_a_su_implantado(cliente, sesion, datos):
    """La historia tal cual la conto la operacion.

    Juan trabaja hasta el 10 y se enferma; Luis lo releva y entra el 11.
    A los dias Juan se recupera, avisa al consultor, y el consultor
    coordina que regrese el 25: Luis trabaja hasta el 24 por orden del
    consultor.
    """
    h = sesion("consultor")
    servicio = cliente.post("/servicios", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "implantado",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}).json()
    contrato = cliente.post("/implantados/contratos", headers=h, json={
        "servicio_id": servicio["id"], "anio": 2029, "mes": 5,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia", "incluye_fines_de_semana": False,
        "hora_presentacion": "08:00:00",
        "titular_id": datos["personal"]["Juan Ramirez"]["id"],
        "vehiculo_id": datos["suburban"]["id"],
        "precio_mes_vehiculo": "66000", "precio_dia_personal": "2900",
        "precio_dia_adicional": "3500"}).json()
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    # Se enferma: Luis entra el 11 y no se dice hasta cuando.
    cambio = cliente.post(f"/implantados/{servicio['id']}/cambios", headers=h, json={
        "tipo": "personal", "desde": "2029-05-11",
        "sale_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_id": datos["personal"]["Luis Mendoza"]["id"],
        "motivo": "enfermedad"})
    assert cambio.status_code == 200, cambio.text
    assert cambio.json()["tope_automatico"] is True

    # Se recupera: el consultor coordina el regreso el 25.
    r = _regreso(cliente, sesion, cambio.json()["reemplazo_id"], "2029-05-25")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["desde"] == "2029-05-11"    # viernes
    assert cuerpo["hasta"] == "2029-05-24"    # jueves, el dia antes
    assert cuerpo["dias_partidos"] == []      # programado: limpio

    # El mes lee un solo movimiento, del 11 al 24.
    resumen = cliente.get(
        f"/implantados/contratos/{contrato['contrato_id']}/resumen",
        headers=h).json()
    assert resumen["total_reemplazos"] == 1, resumen["reemplazos"]
    assert resumen["reemplazos"][0]["desde"] == "2029-05-11"
    assert resumen["reemplazos"][0]["hasta"] == "2029-05-24"

    # Y el 25 en adelante vuelve a ser de Juan.
    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    for j in detalle["equipos"][0]["jornadas"]:
        if j["fecha"] >= "2029-05-25":
            assert _asignados(cliente, sesion, j["id"]) == ["Juan Ramirez"], j["fecha"]


'''

assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO + ANCLA)
R.write_text(s)
print("test_relevo.py: cuatro pruebas del regreso")

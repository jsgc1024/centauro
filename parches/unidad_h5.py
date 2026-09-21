"""Las pruebas de los chicos: la unidad regresa y la hora queda al lado."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/tests/test_relevo.py"
s = R.read_text()

ANCLA = "# ================================================== la raya con implantado"
NUEVO = '''def _unidades(cliente, sesion, jornada_id):
    r = cliente.get(f"/servicios/jornadas/{jornada_id}/asignaciones",
                    headers=sesion("consultor"))
    return [v["placa"] for v in r.json()["vehiculos"]]


def test_la_unidad_tambien_regresa(cliente, sesion, datos):
    """La camioneta sale del taller y vuelve a su servicio.

    Es el mismo motor con los nombres al reves, igual que con las
    personas. Lo unico que no aplica es el candado del dinero: la unidad
    no mueve viaticos, el combustible y las casetas siguen siendo del
    conductor, que es el mismo.
    """
    servicio = _montado(cliente, sesion, datos, offset=920, dias=5)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"])

    cambio = cliente.post("/contingencia/reemplazos/vehiculo", headers=h, json={
        "desde_jornada_id": dias[1]["id"],
        "sale_vehiculo_id": datos["suburban"]["id"],
        "entra_vehiculo_id": otra["id"],
        "motivo": "Entro al taller"})
    assert cambio.status_code == 200, cambio.text

    r = _regreso(cliente, sesion, cambio.json()["reemplazo_id"],
                 dias[3]["fecha"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["tipo"] == "vehiculo"
    assert cuerpo["regresa"] == datos["suburban"]["placa"]
    assert cuerpo["sale"] == otra["placa"]
    assert cuerpo["hasta"] == dias[2]["fecha"]
    assert cuerpo["dias_cubiertos"] == 2

    esperado = [datos["suburban"]["placa"], otra["placa"], otra["placa"],
                datos["suburban"]["placa"], datos["suburban"]["placa"]]
    for dia, placa in zip(dias, esperado):
        assert _unidades(cliente, sesion, dia["id"]) == [placa], dia["fecha"]

    filas = _historial(cliente, sesion, servicio)
    assert len(filas) == 1, filas
    assert filas[0]["tipo"] == "vehiculo"
    assert filas[0]["regreso_por"] == "Ana Solis"


def test_la_hora_que_el_sistema_propuso_para_el_regreso_queda_al_lado(
        cliente, sesion, datos):
    """Sin la propuesta guardada no se puede saber si alguien la corrigio.

    El movimiento ya guardaba la del relevo que lo abrio. La del regreso
    --que tambien decide cuanto cobra cada quien-- vivia solo en la
    asignacion.
    """
    servicio = _montado(cliente, sesion, datos, offset=960, dias=4)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()

    inicio = datetime.fromisoformat(dias[2]["inicio_programado"])
    marca = inicio + timedelta(hours=2)
    assert marcar(cliente, sesion("luis"), dias[2]["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    marcar(cliente, sesion("luis"), dias[2]["id"], "contacto_ejecutivo", marca)

    # El consultor corrige la hora: dice que fue una hora despues.
    corregida = (marca + timedelta(hours=1)).isoformat()
    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[2]["fecha"],
                 relevado_en=corregida)
    assert r.status_code == 200, r.text
    assert r.json()["jornadas_partidas"] == [dias[2]["fecha"]]

    fila = _historial(cliente, sesion, servicio)[0]
    # Lo que el sistema habria puesto: la ultima marca de Luis.
    assert fila["hora_propuesta_regreso"] == marca.isoformat()
    # Y lo que quedo en la asignacion es lo que dijo el consultor. Que no
    # coincidan es justo lo que deja ver la correccion.
    assert fila["partidos"][0]["hora"] == corregida[11:16]
    assert fila["regreso_por"] == "Ana Solis"


# ================================================== la raya con implantado'''

assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)

# _regreso tiene que poder mandar la hora corregida.
VIEJO = '''def _regreso(cliente, sesion, reemplazo_id, dia, **extra):
    return cliente.post(f"/contingencia/reemplazos/{reemplazo_id}/regreso",
                        headers=sesion("consultor"),
                        json={"desde": dia, **extra})'''
assert s.count(VIEJO) == 1, "no encontre _regreso"
R.write_text(s)
print("test_relevo.py: dos pruebas de los chicos")

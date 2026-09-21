"""Entrega 4d: las pruebas de mover un regreso."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/tests/test_relevo.py"
s = R.read_text()

ANCLA = "# ================================================== la raya con implantado"
NUEVO = '''# ============================================ mover un regreso capturado

def _historial(cliente, sesion, servicio):
    return cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                       headers=sesion("consultor")).json()


def test_el_regreso_se_puede_atrasar(cliente, sesion, datos):
    """Juan dijo que volvia el jueves y el miercoles avisa que mejor el
    lunes. El movimiento se recorre; no se abre otro."""
    servicio = _montado(cliente, sesion, datos, offset=760, dias=6)
    dias = servicio["equipos"][0]["jornadas"]
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()
    assert _regreso(cliente, sesion, hecho["reemplazo_id"],
                    dias[3]["fecha"]).status_code == 200

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[5]["fecha"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["hasta"] == dias[4]["fecha"]
    assert cuerpo["jornadas_recuperadas"] == [dias[3]["fecha"], dias[4]["fecha"]]
    assert cuerpo["jornadas_devueltas"] == []
    assert cuerpo["dias_cubiertos"] == 4

    esperado = ["Juan Ramirez", "Luis Mendoza", "Luis Mendoza",
                "Luis Mendoza", "Luis Mendoza", "Juan Ramirez"]
    for dia, quien in zip(dias, esperado):
        assert _asignados(cliente, sesion, dia["id"]) == [quien], dia["fecha"]

    # Un solo movimiento, del 1 al 4, firmado otra vez.
    filas = _historial(cliente, sesion, servicio)
    assert len(filas) == 1, filas
    assert filas[0]["hasta"] == dias[4]["fecha"]
    assert filas[0]["jornadas_afectadas"] == 4


def test_el_regreso_se_puede_adelantar(cliente, sesion, datos):
    """Juan se recupero antes de lo que dijo."""
    servicio = _montado(cliente, sesion, datos, offset=800, dias=6)
    dias = servicio["equipos"][0]["jornadas"]
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()
    assert _regreso(cliente, sesion, hecho["reemplazo_id"],
                    dias[4]["fecha"]).status_code == 200

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[2]["fecha"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["hasta"] == dias[1]["fecha"]
    assert cuerpo["jornadas_devueltas"] == [dias[2]["fecha"], dias[3]["fecha"]]
    assert cuerpo["jornadas_recuperadas"] == []
    assert cuerpo["dias_cubiertos"] == 1

    esperado = ["Juan Ramirez", "Luis Mendoza", "Juan Ramirez",
                "Juan Ramirez", "Juan Ramirez", "Juan Ramirez"]
    for dia, quien in zip(dias, esperado):
        assert _asignados(cliente, sesion, dia["id"]) == [quien], dia["fecha"]
    assert len(_historial(cliente, sesion, servicio)) == 1


def test_el_regreso_no_se_mueve_si_el_dinero_ya_se_movio(cliente, sesion, datos):
    """El candado del dinero, visto por este lado.

    En cuanto hay una transferencia y un plazo corriendo, correr el
    regreso a mano seria peor que el error: lo que corresponde es un
    cambio nuevo, con su rastro.
    """
    servicio = _montado(cliente, sesion, datos, offset=840, dias=5)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()
    assert _regreso(cliente, sesion, hecho["reemplazo_id"],
                    dias[3]["fecha"]).status_code == 200

    # Juan ya volvio el dia 3 y ya recibio su dinero de ese dia.
    viatico = cliente.post(
        "/viaticos/asignar", headers=h,
        json={"jornada_id": dias[3]["id"],
              "persona_id": datos["personal"]["Juan Ramirez"]["id"],
              "conceptos": [{"concepto": "alimentos", "monto": "500",
                             "origen": "tabulador"}]}).json()
    solicitud = cliente.post(f"/viaticos/{viatico['id']}/solicitar-transferencia",
                             headers=h).json()
    assert cliente.post(
        f"/viaticos/transferencias/{solicitud['id']}/confirmar",
        params={"referencia_odoo": "TRX-901"},
        headers=sesion("finanzas")).status_code == 200

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[4]["fecha"])
    assert r.status_code == 409, r.text
    assert "dinero" in r.text.lower()

    # Y nada se movio a medias: el dia 3 sigue siendo de Juan.
    assert _asignados(cliente, sesion, dias[3]["id"]) == ["Juan Ramirez"]
    assert _historial(cliente, sesion, servicio)[0]["hasta"] == dias[2]["fecha"]


def test_el_regreso_no_se_mueve_si_ese_dia_se_partio(cliente, sesion, datos):
    """Ese dia ya esta repartido entre los dos, con su hora. Moverlo
    seria rehacer una nomina."""
    servicio = _montado(cliente, sesion, datos, offset=880, dias=5)
    dias = servicio["equipos"][0]["jornadas"]
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()

    # Luis alcanza a trabajar la manana del dia en que Juan vuelve.
    inicio = datetime.fromisoformat(dias[3]["inicio_programado"])
    assert marcar(cliente, sesion("luis"), dias[3]["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200

    previo = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[3]["fecha"])
    assert previo.status_code == 200, previo.text
    assert previo.json()["jornadas_partidas"] == [dias[3]["fecha"]]

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[4]["fecha"])
    assert r.status_code == 409, r.text
    assert "parti" in r.text.lower()


# ================================================== la raya con implantado'''

assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("test_relevo.py: cuatro pruebas de mover el regreso")

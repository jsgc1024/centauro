"""Las pruebas de la regla del viatico."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/tests/test_accesos.py"
s = R.read_text()

ANCLA = "# ================================================== el rastro"
NUEVO = '''# ================================================== el que debe, no se va

def _con_viatico(cliente, sesion, datos, persona, dias=2, transferir=True):
    """Un servicio con esa persona y dinero encima."""
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [
        jornada(manana(60 + i), datos["modalidades"]["full_day"]["id"])
        for i in range(dias)])
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"], persona_id=persona,
                vehiculo_id=datos["suburban"]["id"])

    primera = servicio["equipos"][0]["jornadas"][0]
    viatico = cliente.post("/viaticos/asignar", headers=h, json={
        "jornada_id": primera["id"], "persona_id": persona,
        "conceptos": [{"concepto": "alimentos", "monto": "1200",
                       "origen": "tabulador"}]}).json()
    if transferir:
        solicitud = cliente.post(
            f"/viaticos/{viatico['id']}/solicitar-transferencia",
            headers=h).json()
        assert cliente.post(
            f"/viaticos/transferencias/{solicitud['id']}/confirmar",
            params={"referencia_odoo": "TRX-950"},
            headers=sesion("finanzas")).status_code == 200
    return servicio, viatico


def test_no_se_da_de_baja_a_quien_trae_dinero_sin_comprobar(
        cliente, sesion, datos, luis_vuelve):
    """Regla de la operacion: debe terminar su ciclo.

    Un viatico transferido y sin comprobar es dinero de la empresa que se
    queda sin dueno, y el servicio no cierra hasta que alguien lo
    comprueba. Cerrarle la puerta antes es perder las dos cosas.
    """
    _con_viatico(cliente, sesion, datos, datos["personal"]["Luis Mendoza"]["id"])
    uid = _id_de(cliente, sesion, "luis.mendoza@centauro.lat")

    r = cliente.post(f"/auth/usuarios/{uid}/desactivar",
                     json={"motivo": "Renuncio"}, headers=sesion("admin"))
    assert r.status_code == 409, r.text
    cuerpo = r.json()["detail"]
    assert len(cuerpo["viaticos"]) == 1
    assert cuerpo["viaticos"][0]["estatus"] == "transferido"
    assert cuerpo["viaticos"][0]["monto"] == 1200
    assert "ciclo" in cuerpo["que_hacer"].lower()

    # Y sigue entrando: el candado no se cerro a medias.
    filas = _usuarios(cliente, sesion)
    assert next(u for u in filas if u["usuario_id"] == uid)["activo"] is True


def test_asignada_pero_sin_dinero_si_se_puede(cliente, sesion, datos,
                                              luis_vuelve):
    """Si no hay dinero de por medio no afecta a la operacion: se va, y
    el consultor asigna a alguien mas.

    El viatico que nunca se transfirio no cuenta: quitarla del servicio
    lo borra con ella, sin rastro que cuadrar.
    """
    servicio, _ = _con_viatico(cliente, sesion, datos,
                               datos["personal"]["Luis Mendoza"]["id"],
                               transferir=False)
    uid = _id_de(cliente, sesion, "luis.mendoza@centauro.lat")

    r = cliente.post(f"/auth/usuarios/{uid}/desactivar",
                     json={"motivo": "Renuncio"}, headers=sesion("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["activo"] is False

    # Y dice lo que deja: esas jornadas hay que cubrirlas.
    pendientes = r.json()["jornadas_por_cubrir"]
    assert len(pendientes) == 1 and pendientes[0]["folio"] == servicio["folio"]


# ================================================== el rastro'''

assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)

# `luis_vuelve` se define mas abajo; se sube para que estas lo alcancen.
VIEJO = '''@pytest.fixture
def luis_vuelve(cliente, sesion):
    """Luis lo usan casi todas las baterias: pase lo que pase aqui,
    vuelve a entrar."""
    yield
    uid = _id_de(cliente, sesion, "luis.mendoza@centauro.lat")
    cliente.post(f"/auth/usuarios/{uid}/reactivar", json={},
                 headers=sesion("admin"))


'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, "")

ANCLA2 = '''# ================================================== cerrar la puerta'''
FIXTURE = '''@pytest.fixture
def luis_vuelve(cliente, sesion):
    """Luis lo usan casi todas las baterias: pase lo que pase aqui,
    vuelve a entrar."""
    yield
    uid = _id_de(cliente, sesion, "luis.mendoza@centauro.lat")
    cliente.post(f"/auth/usuarios/{uid}/reactivar", json={},
                 headers=sesion("admin"))


# ================================================== cerrar la puerta'''
assert s.count(ANCLA2) == 1
s = s.replace(ANCLA2, FIXTURE)

R.write_text(s)
print("test_accesos.py: dos pruebas de la regla del viatico")

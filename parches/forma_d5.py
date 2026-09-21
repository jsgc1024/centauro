"""La prueba de la vista previa."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/tests/test_implantados.py"
s = R.read_text()

ANCLA = "def test_sin_nombre_no_hay_cambio(cliente, sesion, datos):"
NUEVO = '''def test_la_vista_previa_no_guarda_nada(cliente, sesion, datos):
    """Se ejecuta el cambio de verdad y se deshace.

    No hay una segunda cuenta que calcule "lo que pasaria": esa siempre
    acaba separandose de la primera, y entonces el recuadro que el
    consultor lee deja de ser lo que el sistema hace.
    """
    servicio, contrato = _contrato(cliente, sesion, datos, 2030, 4)
    h = sesion("consultor")
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)
    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    jornadas = detalle["equipos"][0]["jornadas"]
    dia = jornadas[4]["fecha"]

    cambio = {"tipo": "personal", "desde": dia,
              "sale_id": datos["personal"]["Juan Ramirez"]["id"],
              "entra_id": datos["personal"]["Luis Mendoza"]["id"],
              "motivo": "vacaciones"}

    r = cliente.post(f"/implantados/{servicio['id']}/cambios/vista-previa",
                     headers=h, json=cambio)
    assert r.status_code == 200, r.text
    previa = r.json()
    # Sin fecha de fin: la previa ya dice hasta donde llega y que el tope
    # lo puso el sistema.
    assert previa["tope_automatico"] is True
    assert previa["hasta"].startswith("2030-04")
    assert previa["jornadas_afectadas"][0] == dia

    # Y no guardo nada: ese dia sigue siendo de Juan y no hay historial.
    def quien(jornada_id):
        a = cliente.get(f"/servicios/jornadas/{jornada_id}/asignaciones",
                        headers=h).json()
        return [p["nombre"] for p in a["personal"]]

    assert quien(jornadas[4]["id"]) == ["Juan Ramirez"]
    assert cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                       headers=h).json() == []

    # El cambio de verdad da lo mismo que dijo la previa.
    hecho = cliente.post(f"/implantados/{servicio['id']}/cambios",
                         headers=h, json=cambio)
    assert hecho.status_code == 200, hecho.text
    assert hecho.json()["hasta"] == previa["hasta"]
    assert hecho.json()["dias_cambiados"] == previa["dias_cambiados"]
    assert quien(jornadas[4]["id"]) == ["Luis Mendoza"]


def test_sin_nombre_no_hay_cambio(cliente, sesion, datos):'''

assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("test_implantados.py: la vista previa no deja rastro")

"""La prueba del tope mira las asignaciones, no un conteo que podria
salir en cero por el motivo equivocado."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/tests/test_relevo.py"
s = R.read_text()

VIEJO = '''    assert cuerpo["tope_automatico"] is True
    assert cuerpo["hasta"].startswith("2029-03"), cuerpo["hasta"]

    # Abril no se movio: sigue siendo de Juan.
    abril = cliente.get(
        f"/implantados/contratos/{contratos[4]['contrato_id']}/resumen",
        headers=h).json()
    assert abril["total_reemplazos"] == 0, abril["reemplazos"]
'''

NUEVO = '''    assert cuerpo["tope_automatico"] is True
    assert cuerpo["hasta"].startswith("2029-03"), cuerpo["hasta"]

    # Ni un dia de abril se movio: se mira la asignacion, no un conteo,
    # porque un conteo en cero puede salir por el motivo equivocado.
    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    abril = [j for j in detalle["equipos"][0]["jornadas"]
             if j["fecha"].startswith("2029-04")]
    assert abril, "abril no se genero"
    for j in abril:
        assert _asignados(cliente, sesion, j["id"]) == ["Juan Ramirez"], j["fecha"]

    # Y marzo si: del 15 en adelante es de Luis.
    marzo = [j for j in detalle["equipos"][0]["jornadas"]
             if j["fecha"] >= "2029-03-15"]
    assert cuerpo["dias_cambiados"] == len(marzo), cuerpo["dias_cambiados"]
    for j in marzo:
        assert _asignados(cliente, sesion, j["id"]) == ["Luis Mendoza"], j["fecha"]
'''

assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("test_relevo.py: el tope se verifica en las asignaciones")

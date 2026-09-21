"""Paso 1c: la prueba que afirmaba lo contrario, y las nuevas."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- la prueba del alcance de direccion general ----------------------
R = RAIZ / "backend/tests/test_permisos.py"
s = R.read_text()
VIEJO = '''def test_direccion_general_alcanza_operacion_pero_no_catalogos(cliente, sesion, datos):
    h = sesion("dirgeneral")
    assert cliente.get("/servicios", headers=h).status_code == 200
    assert cliente.post("/viaticos/transferencias/barrido", headers=h).status_code == 200
    import uuid
    assert cliente.post("/catalogos/tarifarios",
                        json={"pais_id": datos["mx"]["id"], "moneda": "MXN",
                              "vigencia_desde": "2026-01-01",
                              "nombre": f"Tarifario {uuid.uuid4().hex[:8]}"},
                        headers=h).status_code == 403'''
NUEVO = '''def test_direccion_general_alcanza_todo(cliente, sesion, datos):
    """Antes esta prueba decia lo contrario.

    La raya estaba puesta a proposito: direccion general llegaba a todo
    lo operativo pero no a catalogos ni tarifarios, por control interno
    --quien aprueba un margen no deberia poder cambiar en silencio el
    precio con el que se calcula ese margen--.

    Se le planteo asi a la direccion y decidio alcanzarlo todo. La
    consecuencia es que un cambio de precio suyo ya no tiene candado que
    lo detenga, solo bitacora que lo cuente, y por eso la bitacora de
    catalogos dejo de ser un lujo.
    """
    h = sesion("dirgeneral")
    assert cliente.get("/servicios", headers=h).status_code == 200
    assert cliente.post("/viaticos/transferencias/barrido", headers=h).status_code == 200
    import uuid
    assert cliente.post("/catalogos/tarifarios",
                        json={"pais_id": datos["mx"]["id"], "moneda": "MXN",
                              "vigencia_desde": "2026-01-01",
                              "nombre": f"Tarifario {uuid.uuid4().hex[:8]}"},
                        headers=h).status_code == 201

    # Y el resto sigue sin alcanzarlo: que direccion general pase no
    # abre la puerta a los demas.
    assert cliente.post("/catalogos/tarifarios",
                        json={"pais_id": datos["mx"]["id"], "moneda": "MXN",
                              "vigencia_desde": "2026-01-01",
                              "nombre": f"Tarifario {uuid.uuid4().hex[:8]}"},
                        headers=sesion("consultor")).status_code == 403'''
assert s.count(VIEJO) == 1, "no encontre la prueba del alcance"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("test_permisos.py: la prueba dice lo que se decidio")

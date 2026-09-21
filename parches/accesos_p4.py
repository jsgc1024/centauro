"""Arreglos antes de correr.

1. `registro_admin` es movimiento: se vacia entre pruebas, como la otra
   bitacora. Sin eso, una prueba que cuenta renglones depende de lo que
   dejo la anterior.
2. El admin del sembrado se llama "Admin Sistema".
3. La prueba de la puerta de atras usaba a Maria Cruz y la habria dejado
   dada de baja para siempre: `PersonaIn` no tiene `activo`, asi que
   `PATCH /catalogos/personal` no la puede revivir. Se hace con una
   persona de usar y tirar.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- 1. la bitacora nueva se vacia entre pruebas --------------------
R = RAIZ / "backend/tests/conftest.py"
s = R.read_text()
VIEJO = '''    "registro_accion", "notificacion", "alerta", "hito",'''
NUEVO = '''    "registro_accion", "registro_admin", "notificacion", "alerta", "hito",'''
assert s.count(VIEJO) == 1, "no encontre registro_accion en la lista"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("conftest.py: registro_admin se vacia entre pruebas")

# --- 2 y 3. las pruebas ---------------------------------------------
R = RAIZ / "backend/tests/test_accesos.py"
s = R.read_text()

VIEJO = '''    assert cierre["quien"] == "Administrador"'''
NUEVO = '''    assert cierre["quien"] == "Admin Sistema"'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

ini = s.index("def test_no_se_reactiva_a_quien_esta_dado_de_baja")
NUEVO_TEST = '''def test_no_se_reactiva_a_quien_esta_dado_de_baja(cliente, sesion, datos):
    """El acceso no puede ser la puerta de atras de una baja.

    Si la persona ya no trabaja aqui, reactivarle el acceso seria
    abrirsela igual. Primero se corrige la baja donde vive.

    Se hace con una persona de usar y tirar: dar de baja a alguien del
    sembrado seria para siempre, porque `PersonaIn` no trae `activo` y
    no hay forma de revivirla desde la API (ver la nota al final).
    """
    import uuid
    h = sesion("admin")
    marca = uuid.uuid4().hex[:8]

    persona = cliente.post("/catalogos/personal", headers=h, json={
        "nombre": f"Pasajero {marca}", "correo": f"pasajero.{marca}@centauro.lat",
        "plaza_id": datos["cdmx"]["id"]})
    assert persona.status_code == 201, persona.text
    persona_id = persona.json()["id"]

    alta = cliente.post("/auth/usuarios", headers=h,
                        json={"persona_id": persona_id, "rol": "central"})
    assert alta.status_code == 201, alta.text
    uid = alta.json()["usuario_id"]

    # De paso: un acceso recien dado y nunca estrenado se ve como tal.
    ficha = next(u for u in _usuarios(cliente, sesion) if u["usuario_id"] == uid)
    assert ficha["estrenado"] is False
    assert ficha["ultimo_acceso"] is None

    cliente.post(f"/auth/usuarios/{uid}/desactivar", json={}, headers=h)
    assert cliente.delete(f"/catalogos/personal/{persona_id}",
                          headers=h).status_code == 204

    r = cliente.post(f"/auth/usuarios/{uid}/reactivar", json={}, headers=h)
    assert r.status_code == 409, r.text
    assert "baja" in r.text.lower()


def test_el_alta_de_un_acceso_tambien_queda_escrita(cliente, sesion, datos):
    """Dar una puerta es tan importante como cerrarla."""
    import uuid
    h = sesion("admin")
    marca = uuid.uuid4().hex[:8]
    persona = cliente.post("/catalogos/personal", headers=h, json={
        "nombre": f"Pasajero {marca}", "correo": f"pasajero.{marca}@centauro.lat",
        "plaza_id": datos["cdmx"]["id"]}).json()
    alta = cliente.post("/auth/usuarios", headers=h,
                        json={"persona_id": persona["id"], "rol": "consultor"})
    assert alta.status_code == 201, alta.text

    filas = cliente.get(f"/auth/usuarios/{alta.json()['usuario_id']}/historial",
                        headers=h).json()
    assert [f["accion"] for f in filas] == ["acceso creado"]
    assert filas[0]["despues"] == "consultor"
    assert filas[0]["quien"] == "Admin Sistema"
'''
s = s[:ini] + NUEVO_TEST
R.write_text(s)
print("test_accesos.py: la puerta de atras con persona de usar y tirar")

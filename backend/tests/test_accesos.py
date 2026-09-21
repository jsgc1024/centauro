"""Abrir y cerrar la puerta.

El candado de `Usuario.activo` existia desde el principio y funcionaba,
pero no habia forma de accionarlo: el campo se leia en tres lugares y no
se escribia en ninguno. Cortarle el acceso a alguien que se fue enojado
era un UPDATE a mano en Postgres. Lo mismo con el rol, que solo se
escribia en el sembrado de demostracion.

Las cuentas de prueba son `finanzas2` y `central2`, que no las usa
ninguna otra bateria: asi nadie se queda fuera por culpa de aqui. Cada
prueba deja las cosas como las encontro.
"""
import pytest

from ayudas import asignar, crear_servicio, jornada, manana

CONEJILLO = "finanzas2@centauro.lat"


def _usuarios(cliente, sesion):
    r = cliente.get("/auth/usuarios", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    return r.json()


def _id_de(cliente, sesion, correo):
    return next(u["usuario_id"] for u in _usuarios(cliente, sesion)
                if u["correo"] == correo)


def _entrar(cliente, correo):
    r = cliente.post("/auth/token",
                     data={"username": correo, "password": "centauro2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def conejillo(cliente, sesion):
    """Su id, y la promesa de devolverlo como estaba."""
    uid = _id_de(cliente, sesion, CONEJILLO)
    yield uid
    h = sesion("admin")
    cliente.post(f"/auth/usuarios/{uid}/reactivar", json={}, headers=h)
    cliente.post(f"/auth/usuarios/{uid}/rol",
                 json={"rol": "finanzas"}, headers=h)


@pytest.fixture
def luis_vuelve(cliente, sesion):
    """Luis lo usan casi todas las baterias: pase lo que pase aqui,
    vuelve a entrar."""
    yield
    uid = _id_de(cliente, sesion, "luis.mendoza@centauro.lat")
    cliente.post(f"/auth/usuarios/{uid}/reactivar", json={},
                 headers=sesion("admin"))


# ================================================== cerrar la puerta

def test_desactivar_corta_la_sesion_abierta(cliente, sesion, conejillo):
    """El punto de todo esto.

    No basta con que no pueda volver a entrar: el que se fue enojado ya
    tiene una sesion abierta, y son doce horas. Tiene que morirse en su
    siguiente clic.
    """
    suyo = _entrar(cliente, CONEJILLO)
    assert cliente.get("/auth/yo", headers=suyo).status_code == 200

    r = cliente.post(f"/auth/usuarios/{conejillo}/desactivar",
                     json={"motivo": "Dejo la empresa"},
                     headers=sesion("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["activo"] is False
    assert r.json()["sesion_cortada"] is True

    # El mismo token de hace un segundo ya no sirve.
    assert cliente.get("/auth/yo", headers=suyo).status_code == 401
    # Y tampoco puede volver a entrar.
    assert cliente.post("/auth/token",
                        data={"username": CONEJILLO,
                              "password": "centauro2026"}).status_code == 403


def test_no_se_desactiva_dos_veces(cliente, sesion, conejillo):
    h = sesion("admin")
    assert cliente.post(f"/auth/usuarios/{conejillo}/desactivar", json={},
                        headers=h).status_code == 200
    assert cliente.post(f"/auth/usuarios/{conejillo}/desactivar", json={},
                        headers=h).status_code == 409


# ================================================== los candados

def test_no_se_puede_desactivar_al_ultimo_administrador(cliente, sesion):
    """Quedarse sin administradores es no poder volver a entrar.

    Pasa el dia que alguien limpia accesos viejos y el ultimo
    administrador resulta ser una cuenta que nadie reconocia.
    """
    admin_id = _id_de(cliente, sesion, "admin@centauro.lat")
    # Lo intenta direccion general, que ahora alcanza administracion.
    r = cliente.post(f"/auth/usuarios/{admin_id}/desactivar", json={},
                     headers=sesion("dirgeneral"))
    assert r.status_code == 409, r.text
    assert "ultimo administrador" in r.text.lower()

    # Y tampoco por la puerta de atras: quitarle el rol.
    r = cliente.post(f"/auth/usuarios/{admin_id}/rol",
                     json={"rol": "consultor"}, headers=sesion("dirgeneral"))
    assert r.status_code == 409, r.text


def test_nadie_se_cierra_la_puerta_a_si_mismo(cliente, sesion):
    """Contra el error de dedo, y contra el atajo: un cambio sobre uno
    mismo no tiene quien lo revise."""
    admin_id = _id_de(cliente, sesion, "admin@centauro.lat")
    h = sesion("admin")
    assert cliente.post(f"/auth/usuarios/{admin_id}/desactivar", json={},
                        headers=h).status_code == 409
    assert cliente.post(f"/auth/usuarios/{admin_id}/rol",
                        json={"rol": "consultor"},
                        headers=h).status_code == 409


def test_el_panel_no_lo_toca_cualquiera(cliente, sesion, conejillo):
    """Consultor y central no reparten permisos."""
    for quien in ("consultor", "central", "finanzas"):
        assert cliente.get("/auth/usuarios",
                           headers=sesion(quien)).status_code == 403, quien
        assert cliente.post(f"/auth/usuarios/{conejillo}/desactivar", json={},
                            headers=sesion(quien)).status_code == 403, quien


# ================================================== cambiar el puesto

def test_cambiar_el_rol_manda_desde_el_siguiente_clic(cliente, sesion, conejillo):
    """El rol viaja dentro del token, pero nadie lo lee de ahi: cada
    peticion vuelve a buscar al usuario. Asi que el cambio surte efecto
    sin cerrarle la sesion."""
    suyo = _entrar(cliente, CONEJILLO)
    assert cliente.get("/auth/yo", headers=suyo).json()["rol"] == "finanzas"

    r = cliente.post(f"/auth/usuarios/{conejillo}/rol",
                     json={"rol": "central", "motivo": "Cambio de area"},
                     headers=sesion("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["antes"] == "finanzas"
    assert r.json()["rol"] == "central"

    # Con el mismo token de antes del cambio.
    assert cliente.get("/auth/yo", headers=suyo).json()["rol"] == "central"


def test_no_se_le_pone_el_rol_que_ya_tiene(cliente, sesion, conejillo):
    r = cliente.post(f"/auth/usuarios/{conejillo}/rol",
                     json={"rol": "finanzas"}, headers=sesion("admin"))
    assert r.status_code == 409, r.text


# ================================================== lo que deja atras

def test_desactivar_dice_que_jornadas_quedan_sin_cubrir(cliente, sesion, datos,
                                                        luis_vuelve):
    """Cerrarle la puerta a alguien no lo saca de la operacion.

    Si estaba asignado a los servicios de manana, esas jornadas se quedan
    sin el y nadie se entera hasta que el equipo no llega. No se quitan
    solo --eso seria el sistema dejando un servicio sin gente-- pero
    tampoco se callan.
    """
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [
        jornada(manana(40 + i), datos["modalidades"]["full_day"]["id"])
        for i in range(3)])
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Luis Mendoza"]["id"],
                vehiculo_id=datos["suburban"]["id"])

    uid = _id_de(cliente, sesion, "luis.mendoza@centauro.lat")
    r = cliente.post(f"/auth/usuarios/{uid}/desactivar",
                     json={"motivo": "Baja"}, headers=sesion("admin"))
    assert r.status_code == 200, r.text

    pendientes = r.json()["jornadas_por_cubrir"]
    assert len(pendientes) == 1, pendientes
    assert pendientes[0]["folio"] == servicio["folio"]
    assert pendientes[0]["dias"] == 3
    assert "cubrirlos" in (r.json()["aviso"] or "")

    # Y siguen asignadas: el sistema propone, el consultor decide.
    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    primera = detalle["equipos"][0]["jornadas"][0]["id"]
    asignados = cliente.get(f"/servicios/jornadas/{primera}/asignaciones",
                            headers=h).json()["personal"]
    assert [p["nombre"] for p in asignados] == ["Luis Mendoza"]


# ================================================== el que debe, no se va

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


# ================================================== el rastro

def test_todo_cambio_queda_escrito(cliente, sesion, conejillo):
    """La pregunta que se hace despues de un problema es quien se lo dio
    a quien. Si no esta escrita no hay respuesta."""
    h = sesion("admin")
    cliente.post(f"/auth/usuarios/{conejillo}/rol",
                 json={"rol": "central", "motivo": "Cambio de area"}, headers=h)
    cliente.post(f"/auth/usuarios/{conejillo}/desactivar",
                 json={"motivo": "Se fue"}, headers=h)

    r = cliente.get(f"/auth/usuarios/{conejillo}/historial", headers=h)
    assert r.status_code == 200, r.text
    filas = r.json()
    assert [f["accion"] for f in filas] == ["acceso desactivado", "rol cambiado"]

    cierre = filas[0]
    assert cierre["detalle"] == "Se fue"
    assert cierre["antes"] == "activo" and cierre["despues"] == "desactivado"
    assert cierre["quien"] == "Admin Sistema"
    assert cierre["rol_de_quien"] == "admin"

    cambio = filas[1]
    assert cambio["antes"] == "finanzas" and cambio["despues"] == "central"


# ================================================== la puerta de atras

def test_no_se_reactiva_a_quien_esta_dado_de_baja(cliente, sesion, datos):
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


def test_quien_soy_dice_de_que_pais_es(cliente, sesion, datos):
    """Las pantallas que se piden por país abrían en el primero del
    catálogo, que sale ordenado por nombre: al de México le abría Brasil
    y veía una tabla vacía sin saber por qué.

    El país viaja aquí por la misma razón que el idioma: es lo que la
    consola pregunta antes de pintar nada.
    """
    yo = cliente.get("/auth/yo", headers=sesion("consultor")).json()
    assert yo["pais_id"] == datos["mx"]["id"], yo
    assert yo["plaza_id"], yo

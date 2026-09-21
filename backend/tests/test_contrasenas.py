"""Poner, cambiar y recuperar la contrasena.

Cada prueba usa una cuenta de usar y tirar: cambiarle la contrasena a una
del sembrado dejaria a media bateria sin poder entrar, y ademas no se
podria devolver --la de demostracion esta en la lista de las que el
sistema ya no acepta--.
"""
from uuid import uuid4

BUENA = "jueves de tormenta"


def _cuenta(cliente, sesion, datos, rol="central", contrasena=BUENA):
    """Persona nueva, acceso nuevo y su contrasena ya puesta.

    De paso recorre el camino de la invitacion, que es el mismo enlace
    que usa la recuperacion.
    """
    h = sesion("admin")
    marca = uuid4().hex[:8]
    persona = cliente.post("/catalogos/personal", headers=h, json={
        "nombre": f"Prueba {marca}", "correo": f"prueba.{marca}@centauro.lat",
        "plaza_id": datos["cdmx"]["id"]})
    assert persona.status_code == 201, persona.text

    alta = cliente.post("/auth/usuarios", headers=h,
                        json={"persona_id": persona.json()["id"], "rol": rol})
    assert alta.status_code == 201, alta.text
    token = alta.json()["invitacion"]["enlace"].rsplit("/", 1)[-1]

    puesta = cliente.post("/auth/establecer-contrasena",
                          json={"token": token, "contrasena": contrasena})
    assert puesta.status_code == 200, puesta.text
    return {"usuario_id": alta.json()["usuario_id"],
            "correo": alta.json()["correo"], "contrasena": contrasena}


def _entrar(cliente, cuenta, contrasena=None):
    return cliente.post("/auth/token", data={
        "username": cuenta["correo"],
        "password": contrasena or cuenta["contrasena"]})


def _cabecera(cliente, cuenta, contrasena=None):
    r = _entrar(cliente, cuenta, contrasena)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ================================================== cambiarla uno mismo

def test_cambiar_la_propia_contrasena(cliente, sesion, datos):
    cuenta = _cuenta(cliente, sesion, datos)
    suyo = _cabecera(cliente, cuenta)

    r = cliente.post("/auth/mi-contrasena", headers=suyo,
                     json={"actual": BUENA, "nueva": "camino largo a casa"})
    assert r.status_code == 200, r.text

    # La vieja ya no entra, la nueva si.
    assert _entrar(cliente, cuenta, BUENA).status_code == 401
    assert _entrar(cliente, cuenta, "camino largo a casa").status_code == 200


def test_no_se_cambia_sin_saber_la_actual(cliente, sesion, datos):
    """Sin esto, una sesion robada se vuelve una cuenta robada para
    siempre: el que la tiene abierta se pondria su propia contrasena."""
    cuenta = _cuenta(cliente, sesion, datos)
    suyo = _cabecera(cliente, cuenta)

    r = cliente.post("/auth/mi-contrasena", headers=suyo,
                     json={"actual": "la que sea", "nueva": "camino largo"})
    assert r.status_code == 401, r.text
    # Que falle por la contrasena y no por la sesion: esta prueba llego a
    # pasar por accidente cuando el candado de sesiones se comia tokens
    # buenos, y decia que si a algo que no habia verificado.
    assert "actual" in r.text
    assert _entrar(cliente, cuenta).status_code == 200


def test_cambiarla_tira_la_sesion_que_ya_estaba_abierta(cliente, sesion, datos):
    """El token no tiene estado: una vez firmado vale doce horas.

    Sin el candado, cambiar la contrasena no le quitaba nada a quien ya
    tenia la sesion abierta, que es justo de quien uno se quiere
    deshacer al cambiarla.
    """
    cuenta = _cuenta(cliente, sesion, datos)
    viejo = _cabecera(cliente, cuenta)
    assert cliente.get("/auth/yo", headers=viejo).status_code == 200

    r = cliente.post("/auth/mi-contrasena", headers=viejo,
                     json={"actual": BUENA, "nueva": "otro dia de lluvia"})
    assert r.status_code == 200, r.text
    assert r.json()["otras_sesiones_cerradas"] is True

    # El mismo token de hace un segundo ya no vale.
    assert cliente.get("/auth/yo", headers=viejo).status_code == 401
    # Y con la nueva se entra otra vez, sin problema.
    assert cliente.get("/auth/yo",
                       headers=_cabecera(cliente, cuenta, "otro dia de lluvia")
                       ).status_code == 200


def test_la_de_demostracion_ya_no_se_acepta(cliente, sesion, datos):
    """Esta escrita en el codigo y en la bitacora: es la primera que
    alguien va a volver a poner para no olvidarla."""
    cuenta = _cuenta(cliente, sesion, datos)
    suyo = _cabecera(cliente, cuenta)
    r = cliente.post("/auth/mi-contrasena", headers=suyo,
                     json={"actual": BUENA, "nueva": "centauro2026"})
    assert r.status_code == 400, r.text


def test_la_contrasena_no_lleva_el_correo_adentro(cliente, sesion, datos):
    cuenta = _cuenta(cliente, sesion, datos)
    local = cuenta["correo"].split("@")[0]
    suyo = _cabecera(cliente, cuenta)
    r = cliente.post("/auth/mi-contrasena", headers=suyo,
                     json={"actual": BUENA, "nueva": f"{local}2026"})
    assert r.status_code == 400, r.text


# ================================================== la olvidada

def test_recuperar_no_dice_si_la_cuenta_existe(cliente, sesion, datos):
    """Decir "ese correo no esta registrado" le regala media lista a
    quien esta probando."""
    cuenta = _cuenta(cliente, sesion, datos)
    real = cliente.post("/auth/recuperar", json={"correo": cuenta["correo"]})
    falso = cliente.post("/auth/recuperar",
                         json={"correo": f"{uuid4().hex}@centauro.lat"})
    assert real.status_code == falso.status_code == 200
    assert real.json() == falso.json()
    # Y el enlace no viaja en la respuesta: esta puerta es publica.
    # Se busca la direccion y no la palabra "enlace", que sale en el
    # mensaje generico.
    assert "crear-contrasena" not in real.text
    assert "https://" not in real.text


def test_el_enlace_de_recuperacion_sirve_una_vez(cliente, sesion, datos):
    cuenta = _cuenta(cliente, sesion, datos)
    h = sesion("admin")
    assert cliente.post("/auth/recuperar",
                        json={"correo": cuenta["correo"]}).status_code == 200

    pendiente = cliente.get(
        f"/auth/usuarios/{cuenta['usuario_id']}/enlace-pendiente", headers=h)
    assert pendiente.status_code == 200, pendiente.text
    assert pendiente.json()["tipo"] == "recuperacion"
    token = pendiente.json()["enlace"].rsplit("/", 1)[-1]

    assert cliente.post("/auth/establecer-contrasena",
                        json={"token": token,
                              "contrasena": "tarde de viernes"}).status_code == 200
    # La segunda vez ya no.
    assert cliente.post("/auth/establecer-contrasena",
                        json={"token": token,
                              "contrasena": "otra mas"}).status_code == 409
    assert _entrar(cliente, cuenta, "tarde de viernes").status_code == 200


def test_un_enlace_nuevo_mata_al_anterior(cliente, sesion, datos):
    """Si no, el correo de hace una semana sigue abriendo la cuenta."""
    cuenta = _cuenta(cliente, sesion, datos)
    h = sesion("admin")

    cliente.post("/auth/recuperar", json={"correo": cuenta["correo"]})
    primero = cliente.get(
        f"/auth/usuarios/{cuenta['usuario_id']}/enlace-pendiente",
        headers=h).json()["enlace"].rsplit("/", 1)[-1]

    cliente.post("/auth/recuperar", json={"correo": cuenta["correo"]})
    segundo = cliente.get(
        f"/auth/usuarios/{cuenta['usuario_id']}/enlace-pendiente",
        headers=h).json()["enlace"].rsplit("/", 1)[-1]
    assert primero != segundo

    r = cliente.post("/auth/establecer-contrasena",
                     json={"token": primero, "contrasena": "no deberia entrar"})
    assert r.status_code == 409, r.text
    assert cliente.post("/auth/establecer-contrasena",
                        json={"token": segundo,
                              "contrasena": "si entra"}).status_code == 200


def test_el_personal_de_campo_no_recupera_por_correo(cliente, sesion, datos):
    """Su correo es personal y la empresa no lo controla.

    Si ese gmail se compromete --o si la persona salio hace tres meses y
    su gmail sigue vivo-- la recuperacion por correo le entrega la
    cuenta. Lo suyo va por su consultor.
    """
    cuenta = _cuenta(cliente, sesion, datos, rol="personal_seguridad")
    # La respuesta es la misma: no se le dice que su camino es otro por
    # una via que revelaria que la cuenta existe.
    r = cliente.post("/auth/recuperar", json={"correo": cuenta["correo"]})
    assert r.status_code == 200, r.text
    assert "consultor" in r.json()["personal_de_campo"]

    # Pero no se genero ningun enlace.
    pendiente = cliente.get(
        f"/auth/usuarios/{cuenta['usuario_id']}/enlace-pendiente",
        headers=sesion("admin"))
    assert pendiente.status_code == 404, pendiente.text


def test_un_acceso_desactivado_no_se_recupera(cliente, sesion, datos):
    cuenta = _cuenta(cliente, sesion, datos)
    h = sesion("admin")
    assert cliente.post(f"/auth/usuarios/{cuenta['usuario_id']}/desactivar",
                        json={}, headers=h).status_code == 200

    cliente.post("/auth/recuperar", json={"correo": cuenta["correo"]})
    assert cliente.get(f"/auth/usuarios/{cuenta['usuario_id']}/enlace-pendiente",
                       headers=h).status_code == 404


def test_el_enlace_pendiente_no_lo_ve_cualquiera(cliente, sesion, datos):
    """Un enlace de contrasena en manos de alguien es una cuenta en
    manos de alguien."""
    cuenta = _cuenta(cliente, sesion, datos)
    cliente.post("/auth/recuperar", json={"correo": cuenta["correo"]})
    for quien in ("consultor", "central", "finanzas"):
        assert cliente.get(
            f"/auth/usuarios/{cuenta['usuario_id']}/enlace-pendiente",
            headers=sesion(quien)).status_code == 403, quien


def test_entregar_el_enlace_queda_escrito(cliente, sesion, datos):
    cuenta = _cuenta(cliente, sesion, datos)
    h = sesion("admin")
    cliente.post("/auth/recuperar", json={"correo": cuenta["correo"]})
    cliente.get(f"/auth/usuarios/{cuenta['usuario_id']}/enlace-pendiente",
                headers=h)

    acciones = [f["accion"] for f in cliente.get(
        f"/auth/usuarios/{cuenta['usuario_id']}/historial", headers=h).json()]
    assert "enlace entregado" in acciones
    assert "recuperacion pedida" in acciones

"""Los cuatro digitos que el consultor le dicta al agente por telefono.

El personal de campo no recupera por correo: su correo es personal y la
empresa no lo controla. Llama a su consultor --o a la central, que esta
despierta a las 5:40, que es cuando de verdad pasa-- y le dictan cuatro
digitos.

Lo unico que protege este camino es que quien entrega el codigo reconozca
la voz de quien llama. Por eso importa tanto quien puede darlo.

Todas las pruebas usan gente de usar y tirar: cambiarle la contrasena a
alguien del sembrado dejaria media bateria sin poder entrar.
"""
from uuid import uuid4

from ayudas import asignar, crear_servicio, jornada, manana

BUENA = "manana sale el sol"


def _agente(cliente, sesion, datos, rol="personal_seguridad"):
    """Una persona nueva con acceso, sin contrasena todavia."""
    h = sesion("admin")
    marca = uuid4().hex[:8]
    persona = cliente.post("/catalogos/personal", headers=h, json={
        "nombre": f"Agente {marca}", "correo": f"agente.{marca}@centauro.lat",
        "plaza_id": datos["cdmx"]["id"]})
    assert persona.status_code == 201, persona.text
    alta = cliente.post("/auth/usuarios", headers=h, json={
        "persona_id": persona.json()["id"], "rol": rol})
    assert alta.status_code == 201, alta.text
    return {"persona_id": persona.json()["id"],
            "usuario_id": alta.json()["usuario_id"],
            "correo": alta.json()["correo"],
            "nombre": persona.json()["nombre"]}


def _en_servicio_de(cliente, sesion, datos, agente, quien="consultor"):
    """Lo pone a trabajar en un servicio de ese consultor."""
    h = sesion(quien)
    titular = {"consultor": "Ana Solis", "consultor2": "Beatriz Roman"}[quien]
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(3), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"][titular]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"], persona_id=agente["persona_id"])[0]
    assert r.status_code == 200, r.text
    return servicio


def _generar(cliente, sesion, agente, quien="consultor"):
    return cliente.post("/auth/campo/codigo", headers=sesion(quien),
                        json={"persona_id": agente["persona_id"]})


def _usar(cliente, agente, codigo, contrasena=BUENA):
    return cliente.post("/auth/campo/contrasena", json={
        "correo": agente["correo"], "codigo": codigo,
        "contrasena": contrasena})


# ================================================== el camino feliz

def test_el_consultor_le_dicta_el_codigo_a_su_gente(cliente, sesion, datos):
    agente = _agente(cliente, sesion, datos)
    _en_servicio_de(cliente, sesion, datos, agente)

    r = _generar(cliente, sesion, agente)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert len(cuerpo["codigo"]) == 4 and cuerpo["codigo"].isdigit()
    # La tarjeta le da al consultor algo mas que preguntar.
    assert cuerpo["persona"]["nombre"] == agente["nombre"]
    assert cuerpo["persona"]["estrenado"] is False

    assert _usar(cliente, agente, cuerpo["codigo"]).status_code == 200
    assert cliente.post("/auth/token", data={
        "username": agente["correo"],
        "password": BUENA}).status_code == 200


def test_el_codigo_sirve_una_vez(cliente, sesion, datos):
    agente = _agente(cliente, sesion, datos)
    _en_servicio_de(cliente, sesion, datos, agente)
    codigo = _generar(cliente, sesion, agente).json()["codigo"]

    assert _usar(cliente, agente, codigo).status_code == 200
    assert _usar(cliente, agente, codigo, "otra cosa larga").status_code == 401


def test_un_codigo_nuevo_mata_al_anterior(cliente, sesion, datos):
    """Para que el consultor no dicte tres seguidos y el agente no sepa
    cual va."""
    agente = _agente(cliente, sesion, datos)
    _en_servicio_de(cliente, sesion, datos, agente)

    primero = _generar(cliente, sesion, agente).json()["codigo"]
    segundo = _generar(cliente, sesion, agente).json()["codigo"]
    # Que salgan iguales es 1 en 10,000, pero una prueba que falla una
    # vez cada diez mil corridas es peor que no tenerla: nadie le cree.
    while segundo == primero:
        segundo = _generar(cliente, sesion, agente).json()["codigo"]

    assert _usar(cliente, agente, primero).status_code == 401
    assert _usar(cliente, agente, segundo).status_code == 200


# ================================================== quien puede darlo

def test_un_consultor_ajeno_no_le_da_codigo_a_quien_no_conoce(cliente, sesion,
                                                              datos):
    """Cada persona que puede generarlo sin conocer al agente es una
    puerta por la que alguien se cuela diciendo "soy Luis"."""
    agente = _agente(cliente, sesion, datos)
    _en_servicio_de(cliente, sesion, datos, agente, quien="consultor")

    r = _generar(cliente, sesion, agente, quien="consultor2")
    assert r.status_code == 403, r.text
    assert "voz" in r.text.lower()


def test_la_central_siempre_puede(cliente, sesion, datos):
    """Es la que esta despierta a las 5:40, y cubre al que regresa de
    descanso sin estar asignado a nada todavia."""
    agente = _agente(cliente, sesion, datos)   # sin servicio ninguno
    r = _generar(cliente, sesion, agente, quien="central")
    assert r.status_code == 200, r.text
    assert _usar(cliente, agente, r.json()["codigo"]).status_code == 200


def test_el_personal_de_campo_no_reparte_codigos(cliente, sesion, datos):
    agente = _agente(cliente, sesion, datos)
    assert cliente.post("/auth/campo/codigo", headers=sesion("juan"),
                        json={"persona_id": agente["persona_id"]}
                        ).status_code == 403
    assert cliente.get("/auth/campo/buscar?q=ag",
                       headers=sesion("juan")).status_code == 403


def test_el_codigo_no_es_para_el_personal_de_oficina(cliente, sesion, datos):
    """Quien trabaja desde la computadora recupera por correo."""
    oficina = _agente(cliente, sesion, datos, rol="central")
    r = _generar(cliente, sesion, oficina, quien="central")
    assert r.status_code == 409, r.text
    assert "campo" in r.text.lower()


# ================================================== el candado

def test_el_codigo_se_muere_a_los_cinco_fallos(cliente, sesion, datos):
    """Cuatro digitos son diez mil combinaciones: sin tope, un programa
    las prueba todas en segundos."""
    agente = _agente(cliente, sesion, datos)
    _en_servicio_de(cliente, sesion, datos, agente)
    bueno = _generar(cliente, sesion, agente).json()["codigo"]
    malo = "0000" if bueno != "0000" else "1111"

    for intento in range(5):
        r = _usar(cliente, agente, malo)
        assert r.status_code == 401, (intento, r.text)

    # Y el bueno ya no sirve: el codigo se murio con los fallos.
    assert _usar(cliente, agente, bueno).status_code == 401


def test_el_aviso_dice_cuantos_intentos_quedan(cliente, sesion, datos):
    agente = _agente(cliente, sesion, datos)
    _en_servicio_de(cliente, sesion, datos, agente)
    bueno = _generar(cliente, sesion, agente).json()["codigo"]
    malo = "0000" if bueno != "0000" else "1111"

    r = _usar(cliente, agente, malo)
    assert r.status_code == 401
    assert "4" in r.json()["detail"]["que_hacer"]


# ================================================== el buscador

def test_el_buscador_pide_dos_letras(cliente, sesion, datos):
    """Una busqueda que devuelve a todos es el padron completo en la
    pantalla de cualquier consultor."""
    h = sesion("central")
    assert cliente.get("/auth/campo/buscar?q=", headers=h).json() == []
    assert cliente.get("/auth/campo/buscar?q=a", headers=h).json() == []


def test_el_buscador_encuentra_por_nombre(cliente, sesion, datos):
    agente = _agente(cliente, sesion, datos)
    trozo = agente["nombre"].split()[-1][:6]
    filas = cliente.get(f"/auth/campo/buscar?q={trozo}",
                        headers=sesion("central")).json()
    # Se busca que este, no que sea el unico: la base de pruebas no se
    # vacia entre corridas y los agentes de usar y tirar se acumulan.
    assert agente["persona_id"] in [f["persona_id"] for f in filas]


def test_el_consultor_solo_ve_a_su_gente_en_el_buscador(cliente, sesion, datos):
    agente = _agente(cliente, sesion, datos)
    trozo = agente["nombre"].split()[-1][:6]
    _en_servicio_de(cliente, sesion, datos, agente, quien="consultor")

    suyo = cliente.get(f"/auth/campo/buscar?q={trozo}",
                       headers=sesion("consultor")).json()
    ajeno = cliente.get(f"/auth/campo/buscar?q={trozo}",
                        headers=sesion("consultor2")).json()
    assert agente["persona_id"] in [f["persona_id"] for f in suyo]
    assert agente["persona_id"] not in [f["persona_id"] for f in ajeno]


# ================================================== el rastro

def test_dictar_un_codigo_queda_escrito(cliente, sesion, datos):
    """Un codigo entregado sin dueno es el que nadie investiga."""
    agente = _agente(cliente, sesion, datos)
    _en_servicio_de(cliente, sesion, datos, agente)
    _generar(cliente, sesion, agente)

    filas = cliente.get(f"/auth/usuarios/{agente['usuario_id']}/historial",
                        headers=sesion("admin")).json()
    entrega = next(f for f in filas if f["accion"] == "codigo de campo entregado")
    assert entrega["quien"] == "Ana Solis"
    assert entrega["rol_de_quien"] == "consultor"

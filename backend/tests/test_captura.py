"""Regla de captura: lo que se teclea se guarda parejo.

El mismo nombre entra escrito de tres formas distintas segun quien lo
capture y a que hora. Se guarda una sola, para que el task sheet, el
correo al cliente y la app del agente digan lo mismo.
"""
from datetime import date, timedelta

from app import texto

MANANA = date.today() + timedelta(days=1)


def alta(cliente, headers, datos, **extra):
    cuerpo = {
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "karen", "solicitante_apellidos": "WHITFIELD",
        "ejecutivo_nombre": "JAMES", "ejecutivo_apellidos": "CALDWELL de la fuente",
        "equipos": [{"jornadas": [{
            "fecha": str(MANANA),
            "modalidad_id": datos["modalidades"]["transfer"]["id"],
            "hora_presentacion": "14:20:00",
            "origen_direccion": "Aeropuerto Benito Juarez, Terminal 1"}]}],
    }
    cuerpo.update(extra)
    return cliente.post("/servicios", json=cuerpo, headers=headers)


def test_los_nombres_se_guardan_con_inicial_mayuscula(cliente, sesion, datos):
    servicio = alta(cliente, sesion("consultor"), datos).json()
    assert servicio["solicitante_nombre"] == "Karen"
    assert servicio["solicitante_apellidos"] == "Whitfield"
    assert servicio["ejecutivo_nombre"] == "James"
    # Las palabras de enlace se quedan abajo: asi se lee un apellido.
    assert servicio["ejecutivo_apellidos"] == "Caldwell de la Fuente"


def test_el_numero_de_vuelo_va_todo_en_mayuscula(cliente, sesion, datos):
    """La aerolinea lo imprime asi y asi se busca en la pantalla del
    aeropuerto; la aerolinea y la procedencia son palabras normales."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos, equipos=[{"jornadas": [{
        "fecha": str(MANANA),
        "modalidad_id": datos["modalidades"]["transfer"]["id"],
        "hora_presentacion": "14:20:00",
        "origen_direccion": "Aeropuerto Benito Juarez, Terminal 1",
        "vuelo_aerolinea": "united", "vuelo_numero": "ua 1518",
        "vuelo_origen": "HOUSTON", "vuelo_tipo": "llegada",
        "vuelo_hora": f"{MANANA}T13:50:00"}]}]).json()

    jornada_id = servicio["equipos"][0]["jornadas"][0]["id"]
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                       headers=h).json()
    vuelo = hoja["dias"][0]["vuelo"]
    assert vuelo["numero"] == "UA 1518"
    assert vuelo["aerolinea"] == "United"
    assert vuelo["procedencia"] == "Houston"

    # Y tambien cuando el vuelo llega despues del alta, por la otra puerta.
    r = cliente.patch(f"/operacion/jornadas/{jornada_id}/vuelo",
                      json={"vuelo_numero": "am57", "vuelo_aerolinea": "aeromexico"},
                      headers=h)
    assert r.status_code == 200, r.text
    hoja = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                       headers=h).json()
    assert hoja["dias"][0]["vuelo"]["numero"] == "AM57"
    assert hoja["dias"][0]["vuelo"]["aerolinea"] == "Aeromexico"


def test_quien_solicita_queda_parejo_en_el_catalogo(cliente, sesion, datos):
    """Se captura una vez y se elige muchas: si entra desparejo, la lista
    del cliente se llena del mismo contacto escrito de tres formas."""
    h = sesion("consultor")
    alta(cliente, h, datos, solicitante_correo="kwhitfield@cliente.com")
    lista = cliente.get(f"/solicitantes?cliente_id={datos['cliente_id']}",
                        headers=h).json()
    assert [c["completo"] for c in lista] == ["Karen Whitfield"]


def test_la_regla_respeta_como_se_lee_un_nombre():
    assert texto.titulo("JUAN CARLOS de la CRUZ") == "Juan Carlos de la Cruz"
    assert texto.titulo("maria del carmen perez-gomez") == \
        "Maria del Carmen Perez-Gomez"
    # El enlace solo se queda abajo si no abre el nombre.
    assert texto.titulo("de la garza") == "De la Garza"
    assert texto.titulo("  ana   solis  ") == "Ana Solis"
    assert texto.titulo(None) is None
    assert texto.mayusculas(" ua  1518 ") == "UA 1518"

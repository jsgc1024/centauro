"""Quien solicita se captura una vez y despues se elige de la lista."""
from datetime import date, timedelta

MANANA = date.today() + timedelta(days=1)


def alta(cliente, headers, datos, **extra):
    cuerpo = {
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "solicitante_correo": "kwhitfield@cliente.com",
        "solicitante_telefono": "+1 713 555 0102",
        "equipos": [{"jornadas": [{
            "fecha": str(MANANA),
            "modalidad_id": datos["modalidades"]["transfer"]["id"],
            "hora_presentacion": "14:20:00",
            "origen_direccion": "Aeropuerto Benito Juarez, Terminal 1"}]}],
    }
    cuerpo.update(extra)
    return cliente.post("/servicios", json=cuerpo, headers=headers)


def test_el_primer_servicio_da_de_alta_a_quien_solicita(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = alta(cliente, h, datos).json()
    assert servicio["solicitante_id"]

    lista = cliente.get(f"/solicitantes?cliente_id={datos['cliente_id']}",
                        headers=h).json()
    assert [c["completo"] for c in lista] == ["Karen Whitfield"]
    assert lista[0]["correo"] == "kwhitfield@cliente.com"


def test_el_mismo_correo_no_se_da_de_alta_dos_veces(cliente, sesion, datos):
    """Aunque el nombre venga escrito de otra forma, el correo manda."""
    h = sesion("consultor")
    primero = alta(cliente, h, datos).json()
    segundo = alta(cliente, h, datos, solicitante_nombre="KAREN",
                   solicitante_apellidos="Whitfield M.").json()

    assert segundo["solicitante_id"] == primero["solicitante_id"]
    lista = cliente.get(f"/solicitantes?cliente_id={datos['cliente_id']}",
                        headers=h).json()
    assert len(lista) == 1


def test_elegir_uno_ya_registrado_trae_sus_datos(cliente, sesion, datos):
    """El segundo servicio solo manda el id: correo y telefono salen del
    contacto, no se vuelven a capturar."""
    h = sesion("consultor")
    primero = alta(cliente, h, datos).json()

    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_id": primero["solicitante_id"],
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [{
            "fecha": str(MANANA + timedelta(days=3)),
            "modalidad_id": datos["modalidades"]["transfer"]["id"],
            "hora_presentacion": "09:00:00",
            "origen_direccion": "Las Alcobas, Polanco - lobby"}]}]}, headers=h)
    assert r.status_code == 201, r.text
    segundo = r.json()
    assert segundo["solicitante_completo"] == "Karen Whitfield"
    assert segundo["estatus"] == "planeado"


def test_un_dato_que_faltaba_se_completa_solo(cliente, sesion, datos):
    """Si la primera vez no se supo el telefono y la segunda si, queda
    guardado; lo que ya estaba no se pisa."""
    h = sesion("consultor")
    alta(cliente, h, datos, solicitante_telefono=None)
    alta(cliente, h, datos, solicitante_telefono="+1 713 555 0199")

    lista = cliente.get(f"/solicitantes?cliente_id={datos['cliente_id']}",
                        headers=h).json()
    assert len(lista) == 1
    assert lista[0]["telefono"] == "+1 713 555 0199"


def test_el_contacto_de_otro_cliente_no_se_puede_usar(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = alta(cliente, h, datos).json()

    otro = cliente.post("/catalogos/clientes",
                        json={"nombre": "Otro cliente", "pais_id": datos["mx"]["id"]},
                        headers=sesion("admin")).json()
    r = alta(cliente, h, datos, cliente_id=otro["id"],
             solicitante_id=servicio["solicitante_id"])
    assert r.status_code == 400
    assert "otro cliente" in r.json()["detail"]["mensaje"].lower()


def test_el_servicio_conserva_los_datos_con_los_que_se_hizo(cliente, sesion, datos):
    """Si manana cambia el telefono del contacto, el servicio de ayer sigue
    diciendo el que se uso."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos).json()

    cliente.patch(f"/solicitantes/{servicio['solicitante_id']}",
                  json={"cliente_id": datos["cliente_id"], "nombre": "Karen",
                        "apellidos": "Whitfield", "telefono": "+1 713 555 0000"},
                  headers=h)

    hoja = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    assert hoja["solicitante_completo"] == "Karen Whitfield"


def test_dar_de_baja_lo_saca_de_la_lista(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = alta(cliente, h, datos).json()

    r = cliente.delete(f"/solicitantes/{servicio['solicitante_id']}", headers=h)
    assert r.status_code == 204
    assert cliente.get(f"/solicitantes?cliente_id={datos['cliente_id']}",
                       headers=h).json() == []


def test_el_personal_de_seguridad_no_ve_la_lista(cliente, sesion, datos):
    r = cliente.get(f"/solicitantes?cliente_id={datos['cliente_id']}",
                    headers=sesion("juan"))
    assert r.status_code == 403
    assert r.json()["detail"]["actividad"] == "solicitantes.ver"

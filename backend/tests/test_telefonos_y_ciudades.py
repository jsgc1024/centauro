"""Dos reglas generales del sistema.

Ningun telefono se guarda sin clave de pais, y las ciudades no son una
lista cerrada: se agregan durante la operacion.
"""
import uuid
from datetime import date, timedelta

MANANA = date.today() + timedelta(days=1)


def alta(cliente, headers, datos, **extra):
    cuerpo = {
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "solicitante_correo": "kwhitfield@cliente.com",
        "equipos": [{"jornadas": [{
            "fecha": str(MANANA),
            "modalidad_id": datos["modalidades"]["transfer"]["id"],
            "hora_presentacion": "14:20:00",
            "origen_direccion": "Aeropuerto Benito Juarez, Terminal 1"}]}],
    }
    cuerpo.update(extra)
    return cliente.post("/servicios", json=cuerpo, headers=headers)


# ---------------------------------------------------------------- telefonos

def test_el_telefono_se_guarda_con_la_clave_del_pais(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = alta(cliente, h, datos,
                    solicitante_telefono="55 1234 5678",
                    ejecutivo_nombre="James", ejecutivo_apellidos="Caldwell",
                    ejecutivo_telefono="55 8765 4321").json()

    ficha = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    assert ficha["ejecutivo_telefono"].startswith("+52")

    contacto = cliente.get(f"/solicitantes?cliente_id={datos['cliente_id']}",
                           headers=h).json()[0]
    assert contacto["telefono"] == "+52 55 1234 5678"


def test_un_telefono_de_otro_pais_se_respeta(cliente, sesion, datos):
    """El ejecutivo extranjero marca desde su celular: lo que se captura
    con '+' se queda tal cual."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos,
                    solicitante_telefono="+1 713 555 0102").json()
    contacto = cliente.get(f"/solicitantes?cliente_id={datos['cliente_id']}",
                           headers=h).json()[0]
    assert contacto["telefono"] == "+1 713 555 0102"
    assert servicio["folio"].startswith("EP/E-")


def test_el_telefono_que_llega_de_odoo_tambien_lleva_clave(cliente, sesion, datos):
    h = sesion("admin")
    persona = datos["personal"]["Juan Ramirez"]
    r = cliente.post("/odoo/personal",
                     json=[{"correo": persona["correo"],
                            "telefono": "55 4177 2089"}], headers=h)
    assert r.status_code == 200, r.text

    actualizada = cliente.get(f"/catalogos/personal/{persona['id']}",
                              headers=h).json()
    assert actualizada["telefono"] == "+52 55 4177 2089"


# ---------------------------------------------------------------- ciudades

def test_el_consultor_puede_agregar_una_ciudad(cliente, sesion, datos):
    """Un servicio en una ciudad donde nunca se ha trabajado no espera a
    que alguien mas la de de alta."""
    h = sesion("consultor")
    # Las ciudades son catalogo, no movimiento: no se borran entre pruebas,
    # asi que cada corrida da de alta una distinta.
    nombre = f"Merida {uuid.uuid4().hex[:6]}"
    r = cliente.post("/catalogos/plazas",
                     json={"nombre": nombre, "pais_id": datos["mx"]["id"]},
                     headers=h)
    assert r.status_code == 201, r.text
    ciudad = r.json()

    servicio = alta(cliente, h, datos, plaza_id=ciudad["id"]).json()
    assert servicio["plaza_id"] == ciudad["id"]

    ciudades = cliente.get("/catalogos/plazas", headers=h).json()
    assert nombre in [c["nombre"] for c in ciudades]


def test_el_personal_de_seguridad_no_agrega_ciudades(cliente, sesion, datos):
    r = cliente.post("/catalogos/plazas",
                     json={"nombre": f"Cancun {uuid.uuid4().hex[:6]}",
                           "pais_id": datos["mx"]["id"]},
                     headers=sesion("juan"))
    assert r.status_code == 403
    assert r.json()["detail"]["actividad"] == "ciudades.alta"


def test_el_tarifario_sigue_siendo_solo_de_administracion(cliente, sesion, datos):
    """Abrir las ciudades no abrio los catalogos de dinero."""
    r = cliente.post("/catalogos/tarifarios",
                     json={"nombre": f"Tarifario {uuid.uuid4().hex[:6]}",
                           "pais_id": datos["mx"]["id"],
                           "moneda": "MXN", "vigencia_desde": "2026-01-01"},
                     headers=sesion("consultor"))
    assert r.status_code == 403

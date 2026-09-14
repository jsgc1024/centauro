"""Varios equipos en un servicio, cada uno con su ejecutivo principal.

Alfa cuida al director y Beta a su esposa, con dias y punto de inicio
propios. Cada equipo publica su hoja, asi que cada hoja sale a nombre de
su ejecutivo.
"""
from datetime import date, timedelta

MANANA = date.today() + timedelta(days=1)
PASADO = MANANA + timedelta(days=1)


def dia(datos, fecha, modalidad="transfer", direccion="Aeropuerto Benito Juarez, T1"):
    return {"fecha": str(fecha),
            "modalidad_id": datos["modalidades"][modalidad]["id"],
            "hora_presentacion": "07:30:00",
            "origen_direccion": direccion}


def alta_dos_equipos(cliente, h, datos, **extra):
    cuerpo = {
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "equipos": [
            {"ejecutivo_nombre": "james", "ejecutivo_apellidos": "CALDWELL",
             "jornadas": [dia(datos, MANANA),
                          dia(datos, PASADO, "full_day",
                              "Las Alcobas, Polanco - lobby")]},
            {"ejecutivo_nombre": "helen", "ejecutivo_apellidos": "caldwell",
             "jornadas": [dia(datos, MANANA, "full_day",
                              "Las Alcobas, Polanco - lobby")]},
        ],
    }
    cuerpo.update(extra)
    return cliente.post("/servicios", json=cuerpo, headers=h)


def test_cada_equipo_guarda_su_ejecutivo_principal(cliente, sesion, datos):
    r = alta_dos_equipos(cliente, sesion("consultor"), datos)
    assert r.status_code == 201, r.text
    servicio = r.json()
    assert servicio["estatus"] == "planeado"

    alfa, beta = servicio["equipos"]
    assert alfa["alias"] == "Alfa" and beta["alias"] == "Beta"
    # Y con la regla de captura puesta.
    assert alfa["ejecutivo_completo"] == "James Caldwell"
    assert beta["ejecutivo_completo"] == "Helen Caldwell"
    # Cada quien con sus dias.
    assert len(alfa["jornadas"]) == 2
    assert len(beta["jornadas"]) == 1


def test_el_equipo_sin_ejecutivo_propio_hereda_el_del_servicio(cliente, sesion, datos):
    """El servicio de un solo equipo se sigue capturando como siempre:
    el ejecutivo va arriba y el equipo lo toma de ahi."""
    h = sesion("consultor")
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "Ingrid", "ejecutivo_apellidos": "Halvorsen",
        "equipos": [{"jornadas": [dia(datos, MANANA)]}],
    }, headers=h)
    assert r.status_code == 201, r.text
    servicio = r.json()
    assert servicio["estatus"] == "planeado"
    assert servicio["equipos"][0]["ejecutivo_nombre"] is None
    assert servicio["equipos"][0]["ejecutivo_completo"] == "Ingrid Halvorsen"


def test_un_equipo_sin_ejecutivo_deja_el_servicio_en_borrador(cliente, sesion, datos):
    """Si Beta no dice a quien cuida, su hoja no se puede publicar: el
    servicio no esta planeado aunque Alfa este completo."""
    h = sesion("consultor")
    r = alta_dos_equipos(cliente, h, datos)
    completo = r.json()

    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "equipos": [
            {"ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
             "jornadas": [dia(datos, MANANA)]},
            {"jornadas": [dia(datos, MANANA, "full_day")]},
        ],
    }, headers=h)
    assert r.status_code == 201, r.text
    assert completo["estatus"] == "planeado"
    assert r.json()["estatus"] == "borrador"

    estado = cliente.get(f"/servicios/{r.json()['id']}/programacion",
                         headers=h).json()
    assert any("Beta" in f for f in estado["faltantes"]), estado["faltantes"]


def test_la_hoja_de_cada_equipo_sale_a_nombre_de_su_ejecutivo(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = alta_dos_equipos(cliente, h, datos).json()

    hojas = {}
    for equipo in servicio["equipos"]:
        vista = cliente.get(
            f"/task-sheets/equipo/{equipo['id']}/vista-previa", headers=h).json()
        hojas[equipo["alias"]] = vista["ejecutivo"]

    assert hojas["Alfa"] == "James Caldwell"
    assert hojas["Beta"] == "Helen Caldwell"

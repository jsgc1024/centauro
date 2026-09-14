"""La lista de ciudades se limpia sola.

Cuatro son fijas. Las demas entran cuando un servicio cae ahi y salen a
los 30 dias sin usarse, sin borrarse: siguen en la base con sus
servicios y regresan solas cuando se vuelvan a ocupar.
"""
import uuid
from datetime import date, timedelta

from sqlalchemy import text

FIJAS = {"Ciudad de Mexico", "Guadalajara", "Monterrey", "Queretaro"}


def unica(nombre):
    """Los catalogos no se vacian entre corridas: cada prueba trae su
    propia ciudad para no chocar con la de la corrida anterior."""
    return f"{nombre} {uuid.uuid4().hex[:6]}"


def envejecer(motor, plaza_id, dias=200):
    """Deja el alta de la ciudad en el pasado, como si llevara meses."""
    with motor.begin() as con:
        con.execute(text("UPDATE plaza SET creada_en = now() - "
                         "make_interval(days => :d) WHERE id = :id"),
                    {"d": dias, "id": plaza_id})


def nombres(cliente, h, todas=False):
    ruta = "/catalogos/plazas" + ("?todas=true" if todas else "")
    return {p["nombre"] for p in cliente.get(ruta, headers=h).json()}


def test_las_cuatro_de_siempre_nunca_se_van(cliente, sesion, datos):
    h = sesion("consultor")
    assert FIJAS <= nombres(cliente, h)


def test_una_ciudad_recien_creada_aparece(cliente, sesion, datos):
    """Todavia no tiene servicio: esconderla seria esconderle al consultor
    la ciudad que acaba de dar de alta."""
    h = sesion("consultor")
    nombre = unica("Torreon")
    r = cliente.post("/catalogos/plazas",
                     json={"nombre": nombre, "pais_id": datos["mx"]["id"]},
                     headers=h)
    assert r.status_code == 201, r.text
    assert nombre in nombres(cliente, h)


def test_la_ciudad_con_servicio_por_venir_se_queda(cliente, sesion, datos):
    h = sesion("consultor")
    nombre = unica("Tampico")
    ciudad = cliente.post("/catalogos/plazas",
                          json={"nombre": nombre, "pais_id": datos["mx"]["id"]},
                          headers=h).json()
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": ciudad["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [{
            "fecha": str(date.today() + timedelta(days=20)),
            "modalidad_id": datos["modalidades"]["transfer"]["id"],
            "hora_presentacion": "07:30:00",
            "origen_direccion": "Hotel Camino Real"}]}],
    }, headers=h)
    assert r.status_code == 201, r.text
    assert nombre in nombres(cliente, h)


def test_la_ciudad_dormida_sale_de_la_lista_pero_no_de_la_base(
        cliente, sesion, datos, base_de_pruebas):
    """Su ultimo servicio fue hace medio año: deja de estorbar en el
    selector, pero sigue ahi con su historia."""
    h = sesion("consultor")
    nombre = unica("Culiacan")
    ciudad = cliente.post("/catalogos/plazas",
                          json={"nombre": nombre, "pais_id": datos["mx"]["id"]},
                          headers=h).json()
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": ciudad["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [{
            "fecha": str(date.today() - timedelta(days=180)),
            "modalidad_id": datos["modalidades"]["transfer"]["id"],
            "hora_presentacion": "07:30:00",
            "origen_direccion": "Hotel Lucerna"}]}],
    }, headers=h)
    assert r.status_code == 201, r.text

    # Se le envejece el alta: si no, la ciudad se queda en la lista por
    # recien creada y no por su servicio, que es lo que se esta probando.
    envejecer(base_de_pruebas, ciudad["id"])

    assert nombre not in nombres(cliente, h)
    # Pero sigue ahi con su historia, y la pantalla de catalogos la ve.
    assert nombre in nombres(cliente, h, todas=True)


def test_una_ciudad_con_gente_no_se_apaga(cliente, sesion, datos):
    """En Guadalajara vive personal: aunque no haya servicio esta
    temporada, la ciudad sigue en la lista."""
    h = sesion("consultor")
    assert "Guadalajara" in nombres(cliente, h)

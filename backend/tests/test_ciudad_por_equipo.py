"""La ciudad es del equipo, y los km salen de la modalidad.

Un mismo proyecto lleva al ejecutivo de Ciudad de Mexico a Monterrey:
un servicio, dos equipos, cada uno en su ciudad y con el mismo
ejecutivo principal.
"""
from datetime import date, timedelta

MANANA = date.today() + timedelta(days=1)
PASADO = MANANA + timedelta(days=1)


def dia(datos, fecha, modalidad="transfer", **extra):
    j = {"fecha": str(fecha),
         "modalidad_id": datos["modalidades"][modalidad]["id"],
         "hora_presentacion": "07:30:00",
         "origen_direccion": "Aeropuerto Benito Juarez, T1"}
    j.update(extra)
    return j


def test_cada_equipo_opera_en_su_ciudad(cliente, sesion, datos):
    h = sesion("consultor")
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [
            {"jornadas": [dia(datos, MANANA)]},
            {"plaza_id": datos["gdl"]["id"],
             "jornadas": [dia(datos, PASADO, "full_day")]},
        ],
    }, headers=h)
    assert r.status_code == 201, r.text
    alfa, beta = r.json()["equipos"]

    # Alfa no dijo ciudad: opera en la del servicio. Beta si dijo.
    assert alfa["plaza_id"] is None
    assert alfa["ciudad_id"] == datos["cdmx"]["id"]
    assert beta["ciudad_id"] == datos["gdl"]["id"]


def test_se_recomienda_gente_de_la_ciudad_del_equipo(cliente, sesion, datos):
    """Es la razon de bajar la ciudad al equipo: al equipo de Guadalajara
    se le proponen los de Guadalajara como locales, no los de Mexico."""
    h = sesion("consultor")
    servicio = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"plaza_id": datos["gdl"]["id"],
                     "jornadas": [dia(datos, MANANA)]}],
    }, headers=h).json()

    jornada_id = servicio["equipos"][0]["jornadas"][0]["id"]
    perfil = datos["perfiles"]["conductor_seguridad"]["id"]
    categoria = datos["categorias"]["suv_blindada"]["id"]
    r = cliente.get(f"/servicios/jornadas/{jornada_id}/recomendaciones"
                    f"?perfil_id={perfil}&categoria_id={categoria}",
                    headers=h).json()

    locales = [p["ciudad"] for p in r["personal"]["disponibles"]
               + r["personal"]["con_alerta"]]
    assert locales, "no propuso a nadie de Guadalajara"
    assert set(locales) == {"Guadalajara"}
    # Y los de Mexico salen aparte, como traslado.
    assert any(p["ciudad"] == "Ciudad de Mexico"
               for p in r["personal"]["de_otras_ciudades"])


def test_los_km_los_pone_la_modalidad(cliente, sesion, datos):
    """Transfer 40, medio dia 80, dia completo 150. Lo capturado manda."""
    h = sesion("consultor")
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [
            dia(datos, MANANA, "transfer"),
            dia(datos, PASADO, "full_day"),
            dia(datos, PASADO + timedelta(days=1), "medio_dia"),
            dia(datos, PASADO + timedelta(days=2), "full_day",
                km_estimados=320),
        ]}],
    }, headers=h)
    assert r.status_code == 201, r.text
    por_fecha = {j["fecha"]: j for j in r.json()["equipos"][0]["jornadas"]}

    assert por_fecha[str(MANANA)]["km_estimados"] == 40
    assert por_fecha[str(PASADO)]["km_estimados"] == 150
    assert por_fecha[str(PASADO + timedelta(days=1))]["km_estimados"] == 80
    # El servicio que no se parece al promedio: lo capturado gana.
    assert por_fecha[str(PASADO + timedelta(days=2))]["km_estimados"] == 320


def test_la_hoja_de_cada_equipo_dice_su_ciudad(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [
            {"jornadas": [dia(datos, MANANA)]},
            {"plaza_id": datos["gdl"]["id"],
             "jornadas": [dia(datos, PASADO, "full_day")]},
        ],
    }, headers=h).json()

    ciudades = {}
    for equipo in servicio["equipos"]:
        vista = cliente.get(
            f"/task-sheets/equipo/{equipo['id']}/vista-previa", headers=h).json()
        ciudades[equipo["alias"]] = vista["plaza"]

    assert ciudades == {"Alfa": "Ciudad de Mexico", "Beta": "Guadalajara"}

"""La unidad no se suelta sin revisar.

Decisión de Salvador (18 sep): candado duro en el fin de servicio. El
razonamiento que lo eligió está en la bitácora y vale repetirlo aquí,
porque es lo que explica por qué el candado está donde está: **un candado
que solo frenara al cerrar el servicio no salvaría nada.** Para entonces
la camioneta cambió de manos hace días, y las fotos de ese momento ya no
se pueden tomar. El único que sirve es el que muerde cuando la unidad
deja de estar en sus manos.

Y muerde poco a propósito. Un candado que estorbe todos los días es un
candado que alguien va a querer quitar:

* **solo el último día** de esa unidad en el servicio —un implantado con
  la misma camioneta veintidós días se revisa dos veces, no cuarenta y
  cuatro—;
* **solo a quien responde por ella** —el escolta que va de copiloto
  cierra su día normal; pedirle la revisión de una unidad que después no
  puede firmar lo dejaría trabado sin salida—.
"""
from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana, marcar)
from datetime import datetime, timedelta

PIXEL = ("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAEBAQEB"
         "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
         "AQEBAQEBAQH/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQ"
         "AQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==")
FIRMA = "data:image/png;base64," + ("A" * 200)
COMPLETAS = [{"angulo": a, "imagen": PIXEL}
             for a in ("frente", "atras", "izquierdo", "derecho", "odometro")]


def _revision(servicio_id, vehiculo_id, tipo, km):
    return {"servicio_id": servicio_id, "vehiculo_id": vehiculo_id,
            "tipo": tipo, "kilometraje": km, "combustible_octavos": 8,
            "firma": FIRMA, "hubo_dano": False, "fotos": COMPLETAS}


def _fin(cliente, headers, j):
    """Marca el dia completo hasta el fin de servicio.

    Desde el 20 de septiembre no se cierra un dia al que no se llego:
    el fin de servicio pide la llegada marcada. Estas pruebas son del
    candado de la unidad, asi que el dia se hace entero y el que tiene
    que morder es el otro.
    """
    inicio = datetime.fromisoformat(j["inicio_programado"])
    fin = datetime.fromisoformat(j["fin_programado"])
    marcar(cliente, headers, j["id"], "llegada_origen",
           inicio - timedelta(minutes=10))
    marcar(cliente, headers, j["id"], "contacto_ejecutivo", inicio)
    return cliente.post(f"/operacion/jornadas/{j['id']}/hitos", headers=headers,
                        json={"tipo": "fin_servicio", "marcado_en": fin.isoformat(),
                              "lat": 19.4326, "lon": -99.1332})


def _servicio(cliente, sesion, datos, dias=1, quien="Juan Ramirez"):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [
        jornada(manana(i), datos["modalidades"]["full_day"]["id"])
        for i in range(dias)])
    for j in servicio["equipos"][0]["jornadas"]:
        for r in asignar(cliente, h, j["id"],
                         persona_id=datos["personal"][quien]["id"],
                         vehiculo_id=datos["suburban"]["id"]):
            assert r.status_code == 200, r.text
        configurar_origen(cliente, h, j["id"])
    return servicio


# =========================================== el último día, sin entregar

def test_no_hay_fin_de_servicio_con_la_unidad_sin_entregar(cliente, sesion,
                                                           datos):
    """El candado, en su caso más simple: un día, una unidad."""
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    h = sesion("juan")

    assert cliente.post("/campo/revisiones", headers=h, json=_revision(
        servicio["id"], datos["suburban"]["id"], "recibe", 42_000)
    ).status_code == 201

    r = _fin(cliente, h, j)
    assert r.status_code == 409, r.text
    cuerpo = r.json()["detail"]
    assert datos["suburban"]["placa"] in cuerpo["mensaje"]
    assert cuerpo["unidades"][0]["vehiculo_id"] == datos["suburban"]["id"]
    assert cuerpo["unidades"][0]["sin_recepcion"] is False


def test_con_la_entrega_hecha_el_dia_cierra(cliente, sesion, datos):
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    h = sesion("juan")

    for tipo, km in (("recibe", 42_000), ("entrega", 42_380)):
        assert cliente.post("/campo/revisiones", headers=h, json=_revision(
            servicio["id"], datos["suburban"]["id"], tipo, km)
        ).status_code == 201

    assert _fin(cliente, h, j).status_code == 200


def test_sin_la_recepcion_lo_manda_con_su_consultor(cliente, sesion, datos):
    """Este no lo puede resolver solo, y el mensaje tiene que decirlo.

    Sin la revisión de entrada no se puede guardar la de salida —no hay
    contra qué comparar— así que mandarlo a "toma las fotos" sería
    mandarlo a una puerta cerrada.
    """
    servicio = _servicio(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    r = _fin(cliente, sesion("juan"), j)
    assert r.status_code == 409, r.text
    cuerpo = r.json()["detail"]
    assert cuerpo["unidades"][0]["sin_recepcion"] is True
    assert "consultor" in cuerpo["que_hacer"].lower()


# ================================================== donde NO debe estorbar

def test_el_dia_de_en_medio_cierra_sin_entregar_nada(cliente, sesion, datos):
    """La misma camioneta veintidós días se revisa dos veces, no cuarenta
    y cuatro. Si el candado pidiera la entrega cada tarde, a la semana
    alguien lo estaría pidiendo quitar —y tendría razón."""
    servicio = _servicio(cliente, sesion, datos, dias=3)
    jornadas = servicio["equipos"][0]["jornadas"]
    h = sesion("juan")

    assert cliente.post("/campo/revisiones", headers=h, json=_revision(
        servicio["id"], datos["suburban"]["id"], "recibe", 42_000)
    ).status_code == 201

    # Primer y segundo día: la unidad sigue mañana, así que no se pide.
    assert _fin(cliente, h, jornadas[0]).status_code == 200
    assert _fin(cliente, h, jornadas[1]).status_code == 200
    # El último sí.
    assert _fin(cliente, h, jornadas[2]).status_code == 409


def test_el_que_no_trae_unidad_cierra_su_dia(cliente, sesion, datos):
    """El escolta que va de copiloto no responde por la camioneta.

    Es el caso que haría insoportable un candado mal puesto: pedirle una
    revisión que `es_suya` después no lo va a dejar firmar es dejarlo
    encerrado en su propia app.
    """
    h = sesion("consultor")
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"]
                and v["plaza_id"] == datos["suburban"]["plaza_id"])
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(0), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]

    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    for persona in (juan, luis):
        for r in asignar(cliente, h, j["id"], persona_id=persona):
            assert r.status_code == 200, r.text
    for unidad in (datos["suburban"]["id"], otra["id"]):
        for r in asignar(cliente, h, j["id"], vehiculo_id=unidad):
            assert r.status_code == 200, r.text
    # Solo Juan trae unidad; Luis va de copiloto.
    assert cliente.patch(
        f"/servicios/jornadas/{j['id']}/personal/{juan}/unidad",
        json={"vehiculo_id": datos["suburban"]["id"]},
        headers=h).status_code == 200
    configurar_origen(cliente, h, j["id"])

    # Luis cierra sin problema: no responde por ninguna.
    assert _fin(cliente, sesion("luis"), j).status_code == 200
    # Juan no, porque la suya no está entregada.
    assert _fin(cliente, sesion("juan"), j).status_code == 409


# ============================================ la que se va a media jornada

def test_la_unidad_relevada_se_entrega_el_dia_que_sale(cliente, sesion, datos):
    """El hueco por el que se escapaba justo la que más importa.

    Cuando una camioneta se releva o se va al taller, deja de estar en las
    jornadas siguientes, y con eso desaparecía de la lista de "por
    entregar": nadie se la volvía a pedir. Y es la que más probable vuelve
    con un golpe, porque cambió de manos a media operación.
    """
    servicio = _servicio(cliente, sesion, datos, dias=2)
    jornadas = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"]
                and v["plaza_id"] == datos["suburban"]["plaza_id"])

    assert cliente.post("/campo/revisiones", headers=sesion("juan"),
                        json=_revision(servicio["id"], datos["suburban"]["id"],
                                       "recibe", 42_000)).status_code == 201

    r = cliente.post("/contingencia/reemplazos/vehiculo", headers=h, json={
        "desde_jornada_id": jornadas[1]["id"],
        "sale_vehiculo_id": datos["suburban"]["id"],
        "entra_vehiculo_id": otra["id"],
        "motivo": "Se fue al taller a media operacion"})
    assert r.status_code in (200, 201), r.text

    # El primer día cierra: la Suburban todavía va mañana.
    assert _fin(cliente, sesion("juan"), jornadas[0]).status_code == 200

    # El segundo es su último día —se va a media jornada— y ahí sí se le
    # pide. Y la que entró también, porque el servicio termina con ella.
    #
    # La relevada se queda colgada de su día a propósito, así que ese día
    # el equipo tiene dos unidades. Si eso contara como "equipo de dos
    # camionetas", nadie tendría unidad asignada y el día del cambio se
    # quedaría sin dueño: justo el único que de verdad importa. Por eso
    # la relevada y la que la sustituye son la misma silla.
    fin = _fin(cliente, sesion("juan"), jornadas[1])
    assert fin.status_code == 409, fin.text
    placas = {u["placa"] for u in fin.json()["detail"]["unidades"]}
    assert datos["suburban"]["placa"] in placas
    assert otra["placa"] in placas


# ================================================== que se vea antes

def test_la_app_lo_avisa_antes_de_que_lo_intente(cliente, sesion, datos):
    """Con candado duro, descubrirlo al intentar cerrar —a las ocho de la
    noche, con el cliente en el coche— es el peor momento posible."""
    servicio = _servicio(cliente, sesion, datos)
    h = sesion("juan")

    f = cliente.get("/campo/mi-dia", headers=h).json()["hoy"][0]
    pendiente = f["revision"]["entregar_hoy"]
    assert len(pendiente) == 1
    assert pendiente[0]["placa"] == datos["suburban"]["placa"]
    assert pendiente[0]["sin_recepcion"] is True

    for tipo, km in (("recibe", 42_000), ("entrega", 42_380)):
        cliente.post("/campo/revisiones", headers=h, json=_revision(
            servicio["id"], datos["suburban"]["id"], tipo, km))

    f = cliente.get("/campo/mi-dia", headers=h).json()["hoy"][0]
    assert f["revision"]["entregar_hoy"] == []

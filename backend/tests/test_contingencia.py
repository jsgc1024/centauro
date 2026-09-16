"""Incidencias durante el servicio y cambio de recurso por contingencia.

Lo que se verifica no es que el endpoint conteste 200, sino que el dinero
quede donde debe: quien sale no se lleva viaticos sin comprobar y quien
entra no trabaja sin viaticos.
"""
from ayudas import asignar, crear_servicio, jornada, manana


def _placa(datos, placa):
    return next(v["id"] for v in datos["vehiculos"] if v["placa"] == placa)


def _quien(cliente, headers, jornada_id):
    r = cliente.get(f"/servicios/jornadas/{jornada_id}/asignaciones",
                    headers=headers)
    assert r.status_code == 200, r.text
    return [p["nombre"] for p in r.json()["personal"]]


def _placas(cliente, headers, jornada_id):
    r = cliente.get(f"/servicios/jornadas/{jornada_id}/asignaciones",
                    headers=headers)
    return [v["placa"] for v in r.json()["vehiculos"]]


def _servicio_de_tres_dias(cliente, sesion, datos):
    """Tres full days seguidos con Juan y la Suburban."""
    h = sesion("consultor")
    jornadas = [jornada(manana(30 + i), datos["modalidades"]["full_day"]["id"],
                        km_estimados=120)
                for i in range(3)]
    servicio = crear_servicio(cliente, h, datos, jornadas,
                              consultor_id=datos["personal"]["Ana Solis"]["id"])
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=_placa(datos, "ABC-1234"))
    return servicio


# ---------------------------------------------------------------- alertas

def test_boton_de_panico_deja_registro_con_ubicacion(cliente, sesion, datos):
    servicio = _servicio_de_tres_dias(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    r = cliente.post("/contingencia/alertas",
                     json={"canal": "boton_app", "jornada_id": j["id"],
                           "lat": "19.4270", "lon": "-99.1677"},
                     headers=sesion("juan"))
    assert r.status_code == 201, r.text
    alerta = r.json()
    assert alerta["estatus"] == "abierta"
    # Quien aprieta el boton no escribe: la ubicacion es lo que hay.
    assert alerta["lat"] is not None
    # Y nunca es anonimo: queda firmado por quien tiene la sesion abierta.
    assert alerta["reporta_persona_id"] == datos["personal"]["Juan Ramirez"]["id"]


def test_la_alerta_se_cierra_solo_despues_de_tomarla(cliente, sesion, datos):
    servicio = _servicio_de_tres_dias(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    alerta = cliente.post("/contingencia/alertas",
                          json={"canal": "llamada", "jornada_id": j["id"],
                                "descripcion": "El conductor reporta bloqueo"},
                          headers=sesion("central")).json()

    directo = cliente.post(f"/contingencia/alertas/{alerta['id']}/cerrar",
                           json={"resolucion": "Ya paso"},
                           headers=sesion("central"))
    assert directo.status_code == 409

    tomada = cliente.post(f"/contingencia/alertas/{alerta['id']}/tomar",
                          json={"equipo_respuesta_enviado": True},
                          headers=sesion("central"))
    assert tomada.status_code == 200, tomada.text
    assert tomada.json()["estatus"] == "en_atencion"
    assert tomada.json()["equipo_respuesta_enviado"] is True

    cerrada = cliente.post(f"/contingencia/alertas/{alerta['id']}/cerrar",
                           json={"resolucion": "Ruta alterna, servicio continua"},
                           headers=sesion("central"))
    assert cerrada.status_code == 200
    assert cerrada.json()["estatus"] == "cerrada"


def test_el_personal_no_puede_tomar_alertas(cliente, sesion, datos):
    servicio = _servicio_de_tres_dias(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    alerta = cliente.post("/contingencia/alertas",
                          json={"canal": "boton_app", "jornada_id": j["id"]},
                          headers=sesion("juan")).json()
    r = cliente.post(f"/contingencia/alertas/{alerta['id']}/tomar",
                     json={}, headers=sesion("juan"))
    assert r.status_code == 403


# ------------------------------------------------------- cambio de personal

def test_el_reemplazo_cambia_de_ese_dia_en_adelante(cliente, sesion, datos):
    servicio = _servicio_de_tres_dias(cliente, sesion, datos)
    jornadas = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")

    r = cliente.post("/contingencia/reemplazos/personal",
                     json={"desde_jornada_id": jornadas[1]["id"],
                           "sale_persona_id": datos["personal"]["Juan Ramirez"]["id"],
                           "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
                           "motivo": "Accidente en ruta"},
                     headers=h)
    assert r.status_code == 200, r.text
    assert len(r.json()["jornadas_afectadas"]) == 2

    # El primer dia no se toca: ese ya lo trabajo Juan.
    nombres = [_quien(cliente, h, j["id"]) for j in jornadas]
    assert nombres[0] == ["Juan Ramirez"]
    assert nombres[1] == ["Luis Mendoza"]
    assert nombres[2] == ["Luis Mendoza"]


def test_quien_entra_tiene_que_volver_a_confirmar(cliente, sesion, datos):
    servicio = _servicio_de_tres_dias(cliente, sesion, datos)
    jornadas = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    cliente.post("/operacion/jornadas/%s/confirmar-recurso" % jornadas[1]["id"],
                 headers=sesion("juan"))

    cliente.post("/contingencia/reemplazos/personal",
                 json={"desde_jornada_id": jornadas[1]["id"],
                       "sale_persona_id": datos["personal"]["Juan Ramirez"]["id"],
                       "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
                       "motivo": "Enfermedad"},
                 headers=h)

    asignaciones = cliente.get(
        f"/servicios/jornadas/{jornadas[1]['id']}/asignaciones", headers=h).json()
    assert asignaciones["personal"][0]["nombre"] == "Luis Mendoza"
    assert asignaciones["personal"][0]["confirmado"] is False


def test_no_se_puede_reemplazar_por_la_misma_persona(cliente, sesion, datos):
    servicio = _servicio_de_tres_dias(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    r = cliente.post("/contingencia/reemplazos/personal",
                     json={"desde_jornada_id": j["id"],
                           "sale_persona_id": datos["personal"]["Juan Ramirez"]["id"],
                           "entra_persona_id": datos["personal"]["Juan Ramirez"]["id"],
                           "motivo": "Error de captura"},
                     headers=sesion("consultor"))
    assert r.status_code == 409


# ---------------------------------------------------------------- viaticos

def test_el_que_sale_con_dinero_entra_a_comprobacion(cliente, sesion, datos):
    """Lo critico del reemplazo: el dinero ya transferido no se evapora."""
    servicio = _servicio_de_tres_dias(cliente, sesion, datos)
    jornadas = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]

    viatico = cliente.post("/viaticos/asignar",
                           json={"jornada_id": jornadas[1]["id"], "persona_id": juan,
                                 "conceptos": [{"concepto": "alimentos",
                                                "monto": "500", "origen": "tabulador"}]},
                           headers=h).json()
    solicitud = cliente.post(
        f"/viaticos/{viatico['id']}/solicitar-transferencia",
        headers=h).json()
    confirmada = cliente.post(
        f"/viaticos/transferencias/{solicitud['id']}/confirmar",
        params={"referencia_odoo": "TRX-001"}, headers=sesion("finanzas"))
    assert confirmada.status_code == 200, confirmada.text

    r = cliente.post("/contingencia/reemplazos/personal",
                     json={"desde_jornada_id": jornadas[1]["id"],
                           "sale_persona_id": juan,
                           "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
                           "motivo": "Contingencia"},
                     headers=h)
    assert r.status_code == 200, r.text
    movimiento = r.json()["viaticos"]

    # Lo transferido pasa a comprobacion con su plazo, no se cancela.
    assert len(movimiento["a_comprobar"]) == 1
    assert movimiento["a_comprobar"][0]["viatico_id"] == viatico["id"]
    assert movimiento["a_comprobar"][0]["limite"]

    despues = cliente.get(f"/viaticos/{viatico['id']}", headers=h).json()
    assert despues["estatus"] == "en_comprobacion"


def test_el_que_sale_sin_dinero_se_cancela(cliente, sesion, datos):
    servicio = _servicio_de_tres_dias(cliente, sesion, datos)
    jornadas = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]

    viatico = cliente.post("/viaticos/asignar",
                           json={"jornada_id": jornadas[2]["id"], "persona_id": juan,
                                 "conceptos": [{"concepto": "alimentos",
                                                "monto": "500", "origen": "tabulador"}]},
                           headers=h).json()

    r = cliente.post("/contingencia/reemplazos/personal",
                     json={"desde_jornada_id": jornadas[1]["id"],
                           "sale_persona_id": juan,
                           "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
                           "motivo": "Contingencia"},
                     headers=h).json()

    assert [c["viatico_id"] for c in r["viaticos"]["cancelados"]] == [viatico["id"]]
    despues = cliente.get(f"/viaticos/{viatico['id']}", headers=h).json()
    assert despues["estatus"] == "cancelado"


def test_al_que_entra_se_le_proponen_viaticos(cliente, sesion, datos):
    """El sistema propone, el consultor decide.

    Antes se le abrian solos: el sistema decidiendo gastar sin que nadie
    lo pidiera, y de paso el cierre quedaba trabado con viaticos que
    nadie habia solicitado. Ahora sale la cuenta del tabulador —para que
    el consultor no tenga que ir a buscarla— y la solicitud la hace el.
    """
    servicio = _servicio_de_tres_dias(cliente, sesion, datos)
    jornadas = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")

    r = cliente.post("/contingencia/reemplazos/personal",
                     json={"desde_jornada_id": jornadas[1]["id"],
                           "sale_persona_id": datos["personal"]["Juan Ramirez"]["id"],
                           "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
                           "motivo": "Contingencia"},
                     headers=h).json()

    # Uno por cada dia que le queda al servicio, con monto del tabulador.
    propuestos = r["viaticos"]["propuestos"]
    assert len(propuestos) == 2
    assert all(n["monto"] > 0 for n in propuestos)

    # Propuestos quiere decir propuestos: no hay nada asignado todavia.
    suyos = cliente.get(
        "/viaticos/finanzas/por-comprobar", headers=sesion("finanzas")).json()
    de_luis = [x for p in suyos["paises"] for x in p["personas"]
               if x["persona"] == "Luis Mendoza"]
    assert de_luis == [], de_luis


# ---------------------------------------------------------------- unidad

def test_el_cambio_de_unidad_no_mueve_viaticos(cliente, sesion, datos):
    """El combustible y las casetas siguen siendo del conductor, que no cambio."""
    servicio = _servicio_de_tres_dias(cliente, sesion, datos)
    jornadas = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")

    r = cliente.post("/contingencia/reemplazos/vehiculo",
                     json={"desde_jornada_id": jornadas[1]["id"],
                           "sale_vehiculo_id": _placa(datos, "ABC-1234"),
                           "entra_vehiculo_id": _placa(datos, "ABC-5678"),
                           "motivo": "Falla mecanica"},
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["viaticos"] is None
    assert len(r.json()["jornadas_afectadas"]) == 2
    assert _placas(cliente, h, jornadas[0]["id"]) == ["ABC-1234"]
    assert _placas(cliente, h, jornadas[1]["id"]) == ["ABC-5678"]


def test_el_historial_guarda_el_motivo(cliente, sesion, datos):
    servicio = _servicio_de_tres_dias(cliente, sesion, datos)
    jornadas = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    cliente.post("/contingencia/reemplazos/personal",
                 json={"desde_jornada_id": jornadas[1]["id"],
                       "sale_persona_id": datos["personal"]["Juan Ramirez"]["id"],
                       "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
                       "motivo": "Choque en Periferico"},
                 headers=h)

    historial = cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                            headers=h).json()
    assert len(historial) == 1
    assert historial[0]["sale"] == "Juan Ramirez"
    assert historial[0]["entra"] == "Luis Mendoza"
    assert "Periferico" in historial[0]["motivo"]

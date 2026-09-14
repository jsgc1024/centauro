"""Eliminar un servicio o uno de sus equipos.

Se puede mientras no haya pasado nada: la captura equivocada, el
servicio que el cliente echo para atras el mismo dia. En cuanto hay
viaticos o el dia arranco, ya no se borra: se cancela.
"""
from datetime import date, timedelta

MANANA = date.today() + timedelta(days=1)


def dia(datos, fecha=MANANA, modalidad="transfer"):
    return {"fecha": str(fecha),
            "modalidad_id": datos["modalidades"][modalidad]["id"],
            "hora_presentacion": "07:30:00",
            "origen_direccion": "Aeropuerto Benito Juarez, T1"}


def alta(cliente, h, datos, equipos=None):
    r = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": equipos or [{"jornadas": [dia(datos)]}],
    }, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_se_elimina_un_servicio_que_no_se_ha_movido(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = alta(cliente, h, datos)

    r = cliente.request("DELETE", f"/servicios/{servicio['id']}",
                        json={"motivo": "El cliente lo echo para atras"},
                        headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["folio"] == servicio["folio"]
    assert cliente.get(f"/servicios/{servicio['id']}", headers=h).status_code == 404
    assert all(s["id"] != servicio["id"]
               for s in cliente.get("/servicios", headers=h).json())


def test_con_viaticos_asignados_todavia_se_borra(cliente, sesion, datos):
    """Asignar viaticos es papel: el consultor los calculo y los dejo
    listos, pero nadie ha recibido nada. Lo que cierra la puerta es el
    deposito confirmado, no el calculo."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos)
    jornada_id = servicio["equipos"][0]["jornadas"][0]["id"]
    persona = datos["personal"]["Luis Mendoza"]
    cliente.post(f"/servicios/jornadas/{jornada_id}/asignar-personal",
                 json={"persona_id": persona["id"], "forzar": True}, headers=h)
    propuesta = cliente.get(
        f"/viaticos/calcular?jornada_id={jornada_id}&persona_id={persona['id']}",
        headers=h).json()
    puesto = cliente.post("/viaticos/asignar", json={
        "jornada_id": jornada_id, "persona_id": persona["id"],
        "conceptos": [{"concepto": c["concepto"], "monto": str(c["monto"]),
                       "descripcion": c["descripcion"], "origen": c["origen"]}
                      for c in propuesta["conceptos"]]}, headers=h)
    assert puesto.status_code == 201, puesto.text

    r = cliente.request("DELETE", f"/servicios/{servicio['id']}",
                        json={"motivo": "Se cayo antes de depositar"},
                        headers=h)
    assert r.status_code == 200, r.text
    assert cliente.get(f"/servicios/{servicio['id']}", headers=h).status_code == 404


def test_se_elimina_un_equipo_y_los_demas_se_recorren(cliente, sesion, datos):
    """Los alias son por posicion: si se va Beta, Gamma pasa a ser Beta."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos, equipos=[
        {"ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
         "jornadas": [dia(datos)]},
        {"ejecutivo_nombre": "Helen", "ejecutivo_apellidos": "Caldwell",
         "jornadas": [dia(datos)]},
        {"ejecutivo_nombre": "Paul", "ejecutivo_apellidos": "Reyes",
         "jornadas": [dia(datos)]},
    ])
    beta = servicio["equipos"][1]

    r = cliente.request("DELETE", f"/servicios/equipos/{beta['id']}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["equipos_restantes"] == ["Alfa", "Beta"]

    quedan = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    assert [e["ejecutivo_completo"] for e in quedan["equipos"]] \
        == ["James Caldwell", "Paul Reyes"]


def test_el_unico_equipo_no_se_quita_solo(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = alta(cliente, h, datos)
    equipo = servicio["equipos"][0]

    r = cliente.request("DELETE", f"/servicios/equipos/{equipo['id']}", headers=h)
    assert r.status_code == 409
    assert "unico equipo" in r.json()["detail"]["mensaje"]


def test_la_central_no_puede_eliminar(cliente, sesion, datos):
    """Borrar es del consultor y de operaciones, como el alta."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos)
    r = cliente.request("DELETE", f"/servicios/{servicio['id']}",
                        headers=sesion("central"))
    assert r.status_code == 403


# ---------------------------------------------------------------- cancelar

def test_lo_que_ya_no_se_borra_se_cancela(cliente, sesion, datos):
    """Con viaticos entregados el servicio no desaparece: se cancela, y
    el dinero que anda afuera queda enlistado para que regrese."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos)
    jornada_id = servicio["equipos"][0]["jornadas"][0]["id"]
    persona = datos["personal"]["Luis Mendoza"]
    cliente.post(f"/servicios/jornadas/{jornada_id}/asignar-personal",
                 json={"persona_id": persona["id"], "forzar": True}, headers=h)
    propuesta = cliente.get(
        f"/viaticos/calcular?jornada_id={jornada_id}&persona_id={persona['id']}",
        headers=h).json()
    cliente.post("/viaticos/asignar", json={
        "jornada_id": jornada_id, "persona_id": persona["id"],
        "conceptos": [{"concepto": c["concepto"], "monto": str(c["monto"]),
                       "descripcion": c["descripcion"], "origen": c["origen"]}
                      for c in propuesta["conceptos"]]}, headers=h)

    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "El ejecutivo cambio de itinerario"},
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["dias_cancelados"] == 1

    de_nuevo = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    assert de_nuevo["estatus"] == "cancelado"


def test_al_cancelar_la_gente_queda_libre_ese_dia(cliente, sesion, datos):
    """Es la razon de cancelar en vez de dejarlo ahi: el conductor se
    puede mandar a otro servicio ese mismo dia."""
    h = sesion("consultor")
    primero = alta(cliente, h, datos)
    jornada_id = primero["equipos"][0]["jornadas"][0]["id"]
    persona = datos["personal"]["Luis Mendoza"]
    cliente.post(f"/servicios/jornadas/{jornada_id}/asignar-personal",
                 json={"persona_id": persona["id"], "forzar": True}, headers=h)

    segundo = alta(cliente, h, datos)
    otra = segundo["equipos"][0]["jornadas"][0]["id"]
    choca = cliente.post(f"/servicios/jornadas/{otra}/asignar-personal",
                         json={"persona_id": persona["id"]}, headers=h)
    assert choca.status_code == 409

    cliente.post(f"/servicios/{primero['id']}/cancelar",
                 json={"motivo": "Cancelado por el cliente"}, headers=h)
    libre = cliente.post(f"/servicios/jornadas/{otra}/asignar-personal",
                         json={"persona_id": persona["id"]}, headers=h)
    assert libre.status_code == 200, libre.text


def test_un_servicio_cancelado_no_se_vuelve_a_cancelar(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = alta(cliente, h, datos)
    cliente.post(f"/servicios/{servicio['id']}/cancelar",
                 json={"motivo": "Duplicado"}, headers=h)
    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "Otra vez"}, headers=h)
    assert r.status_code == 409

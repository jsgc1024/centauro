"""Encuestas de satisfaccion al cierre.

Lo que se verifica: que la encuesta sea corta cuando todo salio bien y
pregunte el detalle cuando salio mal, que el enlace no sirva dos veces, y
que una mala calificacion abra revision sin castigar a nadie sola.
"""
from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana)


def _servicio_cerrado(cliente, sesion, datos, offset=500, idioma="en"):
    """Servicio ejecutado y con el cierre abierto: ahi salen las encuestas."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("juan"), j)

    r = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                     params={"idioma": idioma}, headers=h)
    assert r.status_code == 200, r.text
    return servicio, r.json()


def _enlaces(cliente, sesion, servicio_id):
    filas = cliente.get(f"/encuestas/servicio/{servicio_id}",
                        headers=sesion("consultor")).json()
    return {f["tipo"]: f for f in filas}


def test_al_cerrar_el_servicio_salen_las_dos_encuestas(cliente, sesion, datos):
    servicio, apertura = _servicio_cerrado(cliente, sesion, datos, 500)
    assert set(apertura["encuestas_enviadas"]) == {"ejecutivo", "solicitante"}

    filas = _enlaces(cliente, sesion, servicio["id"])
    assert filas["ejecutivo"]["estatus"] == "enviada"
    assert filas["solicitante"]["estatus"] == "enviada"


def test_no_se_manda_dos_veces_la_misma_encuesta(cliente, sesion, datos):
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 505)
    r = cliente.post(f"/encuestas/servicio/{servicio['id']}/enviar",
                     headers=sesion("consultor")).json()
    assert r["resultado"] == "sin cambios"


def test_si_todo_salio_bien_solo_hay_una_pregunta_mas(cliente, sesion, datos):
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 510)
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")

    formulario = cliente.get(f"/encuestas/publica/{token}")
    assert formulario.status_code == 200, formulario.text
    assert "si_califica_4_o_5" in formulario.json()

    r = cliente.post(f"/encuestas/publica/{token}",
                     json={"calificacion": 5,
                           "respuestas": {"mas_valoro": "Always on time"}})
    assert r.status_code == 200, r.text
    assert r.json()["abre_revision"] is False


def test_si_salio_mal_se_pide_el_detalle(cliente, sesion, datos):
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 515)
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")

    # Con 3 o menos no se acepta sin el detalle: es la unica oportunidad
    # de saber que arreglar.
    incompleta = cliente.post(f"/encuestas/publica/{token}",
                              json={"calificacion": 2, "respuestas": {}})
    assert incompleta.status_code == 400
    assert "puntualidad" in incompleta.json()["detail"]["preguntas"]

    completa = cliente.post(
        f"/encuestas/publica/{token}",
        json={"calificacion": 2,
              "respuestas": {"puntualidad": 1, "trato": 3, "vehiculo": 2,
                             "molestia": "Llegaron 40 minutos tarde"}})
    assert completa.status_code == 200, completa.text
    assert completa.json()["abre_revision"] is True


def test_no_se_aceptan_preguntas_de_la_otra_rama(cliente, sesion, datos):
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 520)
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")
    r = cliente.post(f"/encuestas/publica/{token}",
                     json={"calificacion": 5,
                           "respuestas": {"mas_valoro": "ok", "puntualidad": 1}})
    assert r.status_code == 400


def test_el_enlace_no_sirve_dos_veces(cliente, sesion, datos):
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 525)
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")
    cliente.post(f"/encuestas/publica/{token}",
                 json={"calificacion": 4, "respuestas": {"mas_valoro": "bien"}})
    otra = cliente.post(f"/encuestas/publica/{token}",
                        json={"calificacion": 1,
                              "respuestas": {"puntualidad": 1, "trato": 1,
                                             "vehiculo": 1}})
    assert otra.status_code == 409


def test_la_del_solicitante_evalua_al_consultor(cliente, sesion, datos):
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 530)
    token = _buscar_token(cliente, sesion, servicio["id"], "solicitante")

    formulario = cliente.get(f"/encuestas/publica/{token}").json()
    assert set(formulario["siempre"]) == {"respuesta_cotizacion", "claridad",
                                          "seguimiento"}

    r = cliente.post(f"/encuestas/publica/{token}",
                     json={"calificacion": 5,
                           "respuestas": {"respuesta_cotizacion": 5,
                                          "claridad": 4, "seguimiento": 5}})
    assert r.status_code == 200, r.text

    ana = datos["personal"]["Ana Solis"]["id"]
    resumen = cliente.get(f"/encuestas/resumen/consultor/{ana}",
                          headers=sesion("consultor")).json()
    assert resumen["calificaciones"] == 1
    assert resumen["por_pregunta"]["claridad"] == 4


def test_una_mala_calificacion_no_castiga_sola(cliente, sesion, datos):
    """Abre revision del consultor; el castigo no es automatico."""
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 535)
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")
    cliente.post(f"/encuestas/publica/{token}",
                 json={"calificacion": 1,
                       "respuestas": {"puntualidad": 1, "trato": 2,
                                      "vehiculo": 3,
                                      "molestia": "El coche venia sucio"}})

    pendientes = cliente.get("/encuestas/por-clasificar",
                             headers=sesion("consultor")).json()
    assert len(pendientes) == 1
    encuesta = pendientes[0]

    r = cliente.post(f"/encuestas/{encuesta['id']}/clasificar",
                     json={"nota": "Se habla con el conductor, sin incidencia"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["incidencia_id"] is None

    # Ya no aparece pendiente.
    assert cliente.get("/encuestas/por-clasificar",
                       headers=sesion("consultor")).json() == []


def test_el_idioma_manda_las_preguntas_correctas(cliente, sesion, datos):
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 540, idioma="es")
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")
    formulario = cliente.get(f"/encuestas/publica/{token}").json()
    assert "califica" in formulario["general"]["pregunta"].lower()


def _buscar_token(cliente, sesion, servicio_id, tipo):
    """El token no sale en el listado: se pide a proposito."""
    encuesta = _enlaces(cliente, sesion, servicio_id)[tipo]
    r = cliente.get(f"/encuestas/{encuesta['id']}/enlace",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()["enlace"].rsplit("/", 1)[-1]



# ------------------------------------------------- la pagina y el correo

def test_la_pagina_de_la_encuesta_se_abre_sin_sesion(cliente, sesion, datos):
    """El ejecutivo no tiene usuario en el sistema."""
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 545)
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")

    r = cliente.get(f"/encuestas/pagina/{token}")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # Trae la identidad de Centauro y la pregunta, no un formulario pelon.
    assert "1B1546" in r.text
    assert "rate the security service" in r.text


def test_un_enlace_vencido_no_muestra_la_encuesta(cliente, sesion, datos):
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 550)
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")
    cliente.post(f"/encuestas/publica/{token}",
                 json={"calificacion": 5, "respuestas": {"mas_valoro": "bien"}})

    r = cliente.get(f"/encuestas/pagina/{token}")
    assert r.status_code == 409
    assert "contestada" in r.text


def test_el_correo_lleva_la_marca_y_un_solo_boton(cliente, sesion, datos):
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 555)
    encuesta = _enlaces(cliente, sesion, servicio["id"])["ejecutivo"]

    r = cliente.get(f"/encuestas/correo/{encuesta['id']}",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert servicio["folio"] in r.text
    assert r.text.count("<a href") == 1

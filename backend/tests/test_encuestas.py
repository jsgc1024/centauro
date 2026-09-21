"""Encuestas de satisfaccion al cierre.

Lo que se verifica: que la encuesta sea corta cuando todo salio bien y
pregunte el detalle cuando salio mal, que el enlace no sirva dos veces, y
que una mala calificacion abra revision sin castigar a nadie sola.
"""
from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana)


def _servicio_cerrado(cliente, sesion, datos, offset=500, idioma="en"):
    """Servicio ejecutado y con el cierre abierto: ahi salen las encuestas.

    El idioma se pone en el SERVICIO y no al abrir el cierre. Desde que
    las encuestas salen solas al terminar el ultimo dia, para cuando el
    cierre se abre ya estan creadas --cada una en el idioma de quien la
    va a contestar--, que es de donde tiene que salir.
    """
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"],
        idioma_ejecutivo=idioma, idioma_solicitante=idioma)
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("juan"), j)

    r = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir", headers=h)
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


# ==================================================================
# Que la queja le llegue a alguien, y que la encuesta tenga reloj
# ==================================================================

def _avisos(cliente, sesion, servicio_id, destinatario=None):
    from app import models as m
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        consulta = db.query(m.Notificacion).filter_by(servicio_id=servicio_id)
        if destinatario:
            consulta = consulta.filter_by(destinatario=destinatario)
        return [{"asunto": n.asunto, "correo": n.correo,
                 "cuerpo": n.cuerpo, "datos": n.datos or ""}
                for n in consulta.all()]
    finally:
        db.close()


def test_la_mala_calificacion_le_llega_al_consultor(cliente, sesion, datos):
    """Un ejecutivo molesto el viernes es una cuenta en riesgo el lunes.

    Hasta hoy la queja llegaba, abría revisión, y se quedaba en una
    bandeja que nadie abría porque no existía la pantalla.
    """
    from app import models as m

    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 560, idioma="es")
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")
    cliente.post(f"/encuestas/publica/{token}", json={
        "calificacion": 2,
        "respuestas": {"puntualidad": 1, "trato": 3, "vehiculo": 2,
                       "molestia": "Llegaron 40 minutos tarde"}})

    avisos = _avisos(cliente, sesion, servicio["id"], m.Destinatario.CONSULTOR)
    assert len(avisos) == 1, "al consultor se le avisa una vez"
    aviso = avisos[0]
    assert aviso["correo"] == datos["personal"]["Ana Solis"]["correo"]
    assert "2" in aviso["asunto"]
    # Lo que dijo el cliente viaja en el correo: un aviso que solo dice
    # "te calificaron mal" obliga a abrir el sistema para saber de que.
    assert "40 minutos tarde" in aviso["datos"]
    # Y no dice que alguien la rego: abre revision, no castigo.
    assert "revisión" in aviso["cuerpo"] or "revision" in aviso["cuerpo"]


def test_una_buena_calificacion_no_le_avisa_a_nadie(cliente, sesion, datos):
    from app import models as m

    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 565, idioma="es")
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")
    cliente.post(f"/encuestas/publica/{token}", json={
        "calificacion": 5, "respuestas": {"mas_valoro": "La puntualidad"}})

    assert _avisos(cliente, sesion, servicio["id"],
                   m.Destinatario.CONSULTOR) == []


def test_la_del_solicitante_no_la_revisa_el_propio_consultor(
        cliente, sesion, datos):
    """Esa encuesta califica AL CONSULTOR. Dejar que él mismo decida si
    amerita incidencia sería juez y parte: sube a operaciones."""
    from app import encuestas, models as m
    from app.db import SessionLocal

    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 570, idioma="es")
    token = _buscar_token(cliente, sesion, servicio["id"], "solicitante")
    cliente.post(f"/encuestas/publica/{token}", json={
        "calificacion": 2,
        "respuestas": {"respuesta_cotizacion": 2, "claridad": 1,
                       "seguimiento": 2, "comentario": "Nunca me contestó"}})

    db = SessionLocal()
    try:
        encuesta = (db.query(m.Encuesta)
                    .filter_by(servicio_id=servicio["id"],
                               tipo=m.TipoEncuesta.SOLICITANTE).first())
        quien = encuestas.quien_la_revisa(db, encuesta)
        assert quien is not None
        assert quien.correo == "operaciones@centauro.lat"
        assert quien.id != datos["personal"]["Ana Solis"]["id"]
    finally:
        db.close()


def test_a_los_cinco_dias_se_recuerda_una_sola_vez(cliente, sesion, datos):
    """Un recordatorio y se acabó. Al ejecutivo de un cliente grande,
    diez correos por un servicio no se leen como interés."""
    from datetime import timedelta

    from app import encuestas, models as m
    from app.db import SessionLocal

    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 575, idioma="es")

    db = SessionLocal()
    try:
        antes = db.query(m.Notificacion).filter_by(
            servicio_id=servicio["id"]).count()
        hoy = encuestas.datetime.now()

        # Al cuarto día todavía no toca.
        r = encuestas.pasar_lista(db, hoy + timedelta(days=4))
        assert r["recordadas"] == 0

        r = encuestas.pasar_lista(db, hoy + timedelta(days=6))
        assert r["recordadas"] == 2, "las dos encuestas del servicio"

        # Y al séptimo no se repite.
        r = encuestas.pasar_lista(db, hoy + timedelta(days=7))
        assert r["recordadas"] == 0

        despues = db.query(m.Notificacion).filter_by(
            servicio_id=servicio["id"]).count()
        assert despues == antes + 2
    finally:
        db.close()


def test_a_los_quince_dias_la_encuesta_se_vence_sola(cliente, sesion, datos):
    """EXPIRADA solo se escribía si alguien abría el enlace caducado, así
    que la que nadie contestó se quedaba en «enviada» para siempre y la
    tasa de respuesta nunca cerraba."""
    from datetime import timedelta

    from app import encuestas, models as m
    from app.db import SessionLocal

    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 580, idioma="es")

    db = SessionLocal()
    try:
        hoy = encuestas.datetime.now()
        r = encuestas.pasar_lista(db, hoy + timedelta(days=16))
        assert r["vencidas"] == 2
        assert r["recordadas"] == 0, "a la vencida ya no se le recuerda"

        estados = {e.estatus for e in db.query(m.Encuesta)
                   .filter_by(servicio_id=servicio["id"]).all()}
        assert estados == {m.EstatusEncuesta.EXPIRADA}
    finally:
        db.close()


def test_la_que_ya_contestaron_no_se_vence_ni_se_recuerda(cliente, sesion, datos):
    from datetime import timedelta

    from app import encuestas
    from app.db import SessionLocal

    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 585, idioma="es")
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")
    cliente.post(f"/encuestas/publica/{token}", json={
        "calificacion": 5, "respuestas": {"mas_valoro": "Todo bien"}})

    db = SessionLocal()
    try:
        hoy = encuestas.datetime.now()
        r = encuestas.pasar_lista(db, hoy + timedelta(days=16))
        assert r["vencidas"] == 1, "solo la del solicitante"
    finally:
        db.close()


def test_el_resumen_cuenta_la_tasa_de_respuesta(cliente, sesion, datos):
    """La tasa solo significa algo desde que las encuestas se vencen
    solas: antes el denominador nunca cerraba."""
    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 590, idioma="es")
    token = _buscar_token(cliente, sesion, servicio["id"], "ejecutivo")
    cliente.post(f"/encuestas/publica/{token}", json={
        "calificacion": 2,
        "respuestas": {"puntualidad": 1, "trato": 3, "vehiculo": 2,
                       "molestia": "Llegaron tarde"}})

    r = cliente.get("/encuestas/resumen",
                    headers=sesion("consultor")).json()
    assert r["enviadas"] >= 2
    assert r["respondidas"] >= 1
    assert r["por_revisar"] >= 1
    assert r["promedio"] is not None
    # El renglon de la bandeja se lee por servicio, no por numero de
    # encuesta: el folio y el cliente van en el.
    fila = next(e for e in r["ultimas"] if e["servicio_id"] == servicio["id"])
    assert fila["folio"] == servicio["folio"]
    assert fila["cliente"]


def test_el_recordatorio_no_llega_identico_al_primero(cliente, sesion, datos):
    """Este armazón ignora el cuerpo del aviso, así que el recordatorio
    salía idéntico al primer correo: quien lo recibía no podía distinguir
    un segundo intento de un correo repetido, y la fecha de cierre —que
    es lo que convierte «ahí luego contesto» en hoy— no aparecía."""
    from datetime import timedelta

    from app import encuestas, encuestas_html, models as m
    from app.db import SessionLocal

    servicio, _ = _servicio_cerrado(cliente, sesion, datos, 595, idioma="es")

    db = SessionLocal()
    try:
        encuestas.pasar_lista(db, encuestas.datetime.now() + timedelta(days=6))
        aviso = (db.query(m.Notificacion)
                 .filter_by(servicio_id=servicio["id"],
                            plantilla="encuesta_recordatorio").first())
        assert aviso is not None, "el recordatorio se manda con su plantilla"

        encuesta = (db.query(m.Encuesta)
                    .filter_by(servicio_id=servicio["id"],
                               tipo=m.TipoEncuesta.EJECUTIVO).first())
        primero = encuestas_html.correo(encuesta, "http://x/e/abc")
        segundo = encuestas_html.correo(encuesta, "http://x/e/abc",
                                        recordatorio=aviso.cuerpo)
        assert segundo != primero, "el segundo correo tiene que verse distinto"
        assert "sigue abierta" in segundo
        # Y dice cuándo se cierra: sin fecha, "ahí luego contesto" gana.
        assert f"{encuesta.expira_en:%d/%m}" in segundo
        # El enlace sigue siendo uno solo y el mismo: dos enlaces vivos
        # para lo mismo es la forma más fácil de contestar dos veces.
        assert segundo.count("<a href") == 1
    finally:
        db.close()

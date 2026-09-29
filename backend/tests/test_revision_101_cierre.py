# -*- coding: utf-8 -*-
"""Seccion 101, grupo g3: del termino a la factura.

Cuarta tanda de la revision del 28 de septiembre, hallazgos a4-03 a
a4-16 (y a6-09, a9-16): la encuesta del solicitante que el consultor no
clasifica, el correo de la encuesta sin regalar el enlace, el cierre que
solo se abre con el servicio terminado, la encuesta que no nacio y su
reenvio, los dos avisos del plazo tambien por correo, justificar una
desviacion viva, los sellos en hora del pais, la revision que reporta
lo que la lista no cotiza, el rango de la escala, la pagina cerrada en
su idioma, Odoo sin folio y dos vistos buenos a la vez.
"""
import re
import threading
from datetime import date, datetime, timedelta

import pytest

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana)


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


class Bandeja(list):
    """Lo que le llego a Odoo. `sin_folio` hace que conteste 200 sin
    numero de factura, que es el caso de a4-14."""
    sin_folio = False


@pytest.fixture
def odoo(monkeypatch):
    """Un Odoo de mentiras, como el de test_facturacion."""
    from app import facturacion

    recibidas = Bandeja()

    class Respuesta:
        status_code = 200
        content = b"{}"

        def raise_for_status(self):
            return None

        def json(self):
            if recibidas.sin_folio:
                return {"ok": True}
            return {"factura": f"FAC-{len(recibidas):04d}"}

    def falso(url, json=None, headers=None, timeout=None):
        recibidas.append({"url": url, "cuerpo": json, "cabeceras": headers})
        return Respuesta()

    monkeypatch.setattr(facturacion.settings, "odoo_url",
                        "https://odoo.example/facturas")
    monkeypatch.setattr(facturacion.settings, "odoo_token", "un-token")
    monkeypatch.setattr(facturacion.httpx, "post", falso)
    return recibidas


# ---------------------------------------------------------------- escenarios

def _servicio_ejecutado(cliente, sesion, datos, offset, dias=1,
                        agente_extra=False, **extra):
    """Un servicio cotizado, trabajado y terminado: su cierre ya nacio.
    Con `agente_extra`, el ultimo dia lleva a alguien que no estaba
    cotizado (una desviacion viva)."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"])
         for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"], **extra)
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    jornadas = servicio["equipos"][0]["jornadas"]
    for idx, j in enumerate(jornadas):
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        if agente_extra and idx == len(jornadas) - 1:
            asignar(cliente, h, j["id"],
                    persona_id=datos["personal"]["Miguel Torres"]["id"],
                    rol="agente_seguridad")
        configurar_origen(cliente, h, j["id"])
        r = ejecutar_jornada(cliente, sesion("juan"), j)
        assert r.status_code == 200, r.text
    return servicio


def _cierre(servicio_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()


def _encuestas(cliente, sesion, servicio_id, quien="consultor"):
    r = cliente.get(f"/encuestas/servicio/{servicio_id}", headers=sesion(quien))
    assert r.status_code == 200, r.text
    return {f["tipo"]: f for f in r.json()}


def _token(cliente, sesion, servicio_id, tipo):
    e = _encuestas(cliente, sesion, servicio_id)[tipo]
    r = cliente.get(f"/encuestas/{e['id']}/enlace", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return e["id"], r.json()["enlace"].rsplit("/", 1)[-1]


def _contestar(cliente, token, calificacion, respuestas):
    return cliente.post(f"/encuestas/publica/{token}",
                        json={"calificacion": calificacion,
                              "respuestas": respuestas})


def _avisos(servicio_id, destinatario=None, plantilla=None):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        q = db.query(m.Notificacion).filter_by(servicio_id=servicio_id)
        if destinatario:
            q = q.filter_by(destinatario=destinatario)
        if plantilla:
            q = q.filter_by(plantilla=plantilla)
        return [{"asunto": n.asunto, "cuerpo": n.cuerpo, "correo": n.correo,
                 "idioma": n.idioma, "datos": n.datos or "",
                 "enlace": n.enlace_seguimiento, "plantilla": n.plantilla}
                for n in q.order_by(m.Notificacion.id).all()]


def _bitacora(servicio_id, accion):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return [r.detalle for r in db.query(m.RegistroAccion)
                .filter_by(servicio_id=servicio_id, accion=accion)
                .order_by(m.RegistroAccion.id).all()]


# ================================================= 54 · juez y parte (a4-03)

def test_el_consultor_no_clasifica_la_encuesta_que_lo_califica(cliente, sesion, datos):
    """El solicitante califica con 1 a Ana. La encuesta la clasifica
    direccion de operaciones; Ana, que es la calificada, la veia en
    #/encuestas y la cerraba sin incidencia."""
    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2110)
    encuesta_id, token = _token(cliente, sesion, servicio["id"], "solicitante")
    r = _contestar(cliente, token, 1, {"respuesta_cotizacion": 1, "claridad": 1,
                                       "seguimiento": 1,
                                       "comentario": "Nunca me contesto"})
    assert r.status_code == 200, r.text

    # La bandeja se lo dice antes de que pique: no es suya.
    fila = next(e for e in cliente.get("/encuestas/por-clasificar",
                                       headers=sesion("consultor")).json()
                if e["id"] == encuesta_id)
    assert fila["juez_y_parte"] is True
    r = cliente.post(f"/encuestas/{encuesta_id}/clasificar",
                     headers=sesion("consultor"),
                     json={"nota": "No hubo tal cosa, el cliente exagera"})
    assert r.status_code == 403, r.text
    assert "operaciones" in r.json()["detail"]["que_hacer"]
    # Otro consultor que la cubre, tampoco.
    r = cliente.post(f"/encuestas/{encuesta_id}/clasificar",
                     headers=sesion("consultor2"),
                     json={"nota": "La cubro yo y digo que no paso nada"})
    assert r.status_code == 403, r.text

    # Direccion de operaciones si.
    fila = next(e for e in cliente.get("/encuestas/por-clasificar",
                                       headers=sesion("diroperaciones")).json()
                if e["id"] == encuesta_id)
    assert fila["juez_y_parte"] is False
    r = cliente.post(f"/encuestas/{encuesta_id}/clasificar",
                     headers=sesion("diroperaciones"),
                     json={"nota": "Se habla con Ana; sin incidencia"})
    assert r.status_code == 200, r.text


def test_la_clasificacion_es_una_sola_y_con_incidencia_del_servicio(
        cliente, sesion, datos, db):
    """La del ejecutivo si la clasifica el consultor: pero una sola vez,
    y la incidencia que liga tiene que ser de este servicio."""
    from app import models as m

    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2115)
    otro = _servicio_ejecutado(cliente, sesion, datos, offset=2117)
    encuesta_id, token = _token(cliente, sesion, servicio["id"], "ejecutivo")
    r = _contestar(cliente, token, 2, {"puntualidad": 1, "trato": 2,
                                       "vehiculo": 2, "molestia": "Tarde"})
    assert r.status_code == 200, r.text

    ajena = m.Incidencia(
        persona_id=datos["personal"]["Juan Ramirez"]["id"],
        servicio_id=otro["id"], fecha=date.today(),
        gravedad=m.GravedadIncidencia.LEVE, descripcion="De otro servicio",
        clasificada_por_id=datos["personal"]["Ana Solis"]["id"])
    db.add(ajena)
    db.commit()
    h = sesion("consultor")
    r = cliente.post(f"/encuestas/{encuesta_id}/clasificar", headers=h,
                     json={"nota": "Se liga la incidencia del otro dia",
                           "incidencia_id": ajena.id})
    assert r.status_code == 409, r.text
    assert "otro" in r.json()["detail"]["mensaje"] or \
        "no es de este servicio" in r.json()["detail"]["mensaje"]

    r = cliente.post(f"/encuestas/{encuesta_id}/clasificar", headers=h,
                     json={"nota": "Se habla con el conductor, sin incidencia"})
    assert r.status_code == 200, r.text
    r = cliente.post(f"/encuestas/{encuesta_id}/clasificar", headers=h,
                     json={"nota": "Ahora si con incidencia"})
    assert r.status_code == 409, r.text
    assert "clasificada" in r.json()["detail"]["mensaje"]


# ===================================== 55 · ver el correo (a4-04, a6-09)

def test_ver_el_correo_no_regala_el_enlace_a_quien_solo_ve(cliente, sesion, datos):
    """La central solo tiene ver encuestas: /enlace le contesta 403, pero
    /correo le entregaba el mismo token dentro del HTML y con el
    contestaba por el cliente. Ahora ve el correo con el enlace tapado."""
    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2120)
    e = _encuestas(cliente, sesion, servicio["id"], "central")["ejecutivo"]
    assert cliente.get(f"/encuestas/{e['id']}/enlace",
                       headers=sesion("central")).status_code == 403
    r = cliente.get(f"/encuestas/correo/{e['id']}", headers=sesion("central"))
    assert r.status_code == 200, r.text
    assert re.search(r"/encuestas/pagina/([A-Za-z0-9_-]+)", r.text) is None
    assert "[enlace de la encuesta]" in r.text
    assert servicio["folio"] in r.text
    assert _bitacora(servicio["id"], "recuperar enlace de encuesta") == []


def test_quien_puede_sacar_el_enlace_lo_ve_en_el_correo_con_rastro(
        cliente, sesion, datos):
    """El consultor si puede sacar el enlace: lo ve vivo en el correo, y
    queda en la bitacora igual que si lo hubiera pedido."""
    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2125)
    e = _encuestas(cliente, sesion, servicio["id"])["ejecutivo"]
    r = cliente.get(f"/encuestas/correo/{e['id']}", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    token = re.search(r"/encuestas/pagina/([A-Za-z0-9_-]+)", r.text).group(1)
    assert r.text.count("<a href") == 1
    rastro = _bitacora(servicio["id"], "recuperar enlace de encuesta")
    assert len(rastro) == 1 and "al ver el correo" in rastro[0]
    assert _contestar(cliente, token, 5, {"mas_valoro": "todo"}).status_code == 200


# ================================== 56 · abrir el cierre a destiempo (a4-05)

def test_no_se_abre_el_cierre_de_un_servicio_que_no_ha_terminado(
        cliente, sesion, datos):
    """Sobre un servicio planeado, /abrir creaba un cierre con el T0 que
    se le mandara y mandaba las encuestas antes de trabajar. Ahora solo
    con el servicio terminado."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(30), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    r = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir", headers=h,
                     params={"ahora": "2030-01-01T00:00:00"})
    assert r.status_code == 409, r.text
    assert "no ha terminado" in r.json()["detail"]["mensaje"]
    assert _cierre(servicio["id"]) is None
    assert all(e["estatus"] == "sin_enviar"
               for e in _encuestas(cliente, sesion, servicio["id"]).values())


def test_el_t0_lo_pone_el_sistema_y_abrir_no_manda_encuestas(
        cliente, sesion, datos, db):
    """El servicio que quedo terminado sin cierre --el caso viejo--: el
    cierre nace con la hora del pais, no con la que mande quien llama,
    y las encuestas no salen de aqui."""
    from app import models as m, reloj

    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2130)
    viejo = db.query(m.Cierre).filter_by(servicio_id=servicio["id"]).one()
    db.delete(viejo)
    db.query(m.Encuesta).filter_by(servicio_id=servicio["id"]).delete()
    db.commit()

    h = sesion("consultor")
    r = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir", headers=h,
                     params={"abierto_en": "2030-01-01T00:00:00"})
    assert r.status_code == 200, r.text
    assert r.json()["encuestas_enviadas"] == []
    abierto = datetime.fromisoformat(r.json()["abierto_en"])
    ahora = reloj.ahora_del_servicio(db, db.get(m.Servicio, servicio["id"]))
    assert abs((abierto - ahora).total_seconds()) < 120, (abierto, ahora)
    assert db.query(m.Encuesta).filter_by(servicio_id=servicio["id"]).count() == 0


# ================================== 57 · la encuesta que no nacio (a4-06)

def test_la_encuesta_que_no_nacio_sale_al_corregir_el_correo(cliente, sesion, datos):
    """Alta sin el correo del principal, servicio terminado: la encuesta
    del ejecutivo no se creo. Al capturar el correo en Corregir los
    contactos, sale."""
    from app import models as m

    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2135,
                                   ejecutivo_correo=None)
    antes = _encuestas(cliente, sesion, servicio["id"])
    assert antes["solicitante"]["estatus"] == "enviada"
    assert antes["ejecutivo"]["id"] is None
    assert antes["ejecutivo"]["estatus"] == "sin_enviar"
    assert antes["ejecutivo"]["motivo"] == "sin_correo"

    r = cliente.patch(f"/servicios/{servicio['id']}/contactos",
                      headers=sesion("consultor"), json={"ejecutivo": {
                          "nombre": "Ingrid", "apellidos": "Halvorsen",
                          "correo": "ingrid.halvorsen@clientedemo.com",
                          "idioma": "en"}})
    assert r.status_code == 200, r.text
    assert r.json()["encuestas_nuevas"] == ["ejecutivo"]

    despues = _encuestas(cliente, sesion, servicio["id"])["ejecutivo"]
    assert despues["id"] and despues["estatus"] == "enviada"
    assert despues["correo"] == "ingrid.halvorsen@clientedemo.com"
    correos = _avisos(servicio["id"], m.Destinatario.EJECUTIVO, plantilla="encuesta")
    assert len(correos) == 1 and correos[0]["idioma"] == "en"
    assert correos[0]["correo"] == "ingrid.halvorsen@clientedemo.com"
    assert any("al corregir el correo" in d
               for d in _bitacora(servicio["id"], "enviar encuestas"))


def test_reenviar_manda_el_correo_otra_vez_y_deja_rastro(cliente, sesion, datos):
    """La encuesta viva se reenvia con el mismo enlace, queda en la
    bitacora, y solo quien puede mandar encuestas lo hace. La contestada
    no se reenvia."""
    from app import models as m

    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2140)
    e = _encuestas(cliente, sesion, servicio["id"])["ejecutivo"]
    assert cliente.post(f"/encuestas/{e['id']}/reenviar",
                        headers=sesion("central")).status_code == 403

    r = cliente.post(f"/encuestas/{e['id']}/reenviar", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["para"] == "ejecutivo@cliente.com"
    token = r.json()["enlace"].rsplit("/", 1)[-1]
    correos = _avisos(servicio["id"], m.Destinatario.EJECUTIVO, plantilla="encuesta")
    assert len(correos) == 2, "el de siempre y el reenvio"
    assert all(c["enlace"].endswith(token) for c in correos), "el mismo enlace"
    rastro = _bitacora(servicio["id"], "reenviar encuesta")
    assert len(rastro) == 1 and "ejecutivo@cliente.com" in rastro[0]

    assert _contestar(cliente, token, 5, {"mas_valoro": "todo"}).status_code == 200
    r = cliente.post(f"/encuestas/{e['id']}/reenviar", headers=sesion("consultor"))
    assert r.status_code == 409, r.text


# ============================== 58 · los dos avisos por correo (a4-07)

def test_arrancan_tus_24_h_tambien_por_correo(cliente, sesion, datos):
    """T1 llega y el consultor tiene 24 horas: el aviso iba solo al
    telefono con la app suscrita. Ahora tambien por correo, en el idioma
    del pais, con el plazo y que hacer."""
    from app import models as m

    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2145)
    h = sesion("consultor")
    assert _avisos(servicio["id"], m.Destinatario.CONSULTOR) == []
    c = _cierre(servicio["id"])
    # Sin viaticos, T1 llega en cuanto alguien pregunta: el envio avanza
    # el reloj el mismo, y ahi sale el aviso.
    r = cliente.post(f"/cierre/{c.id}/enviar-finanzas", headers=h)
    assert r.status_code == 200, r.text

    avisos = _avisos(servicio["id"], m.Destinatario.CONSULTOR)
    assert len(avisos) == 1, avisos
    aviso = avisos[0]
    assert aviso["correo"] == datos["personal"]["Ana Solis"]["correo"]
    assert aviso["idioma"] == "es"
    assert aviso["asunto"] == f"{servicio['folio']}: tienes 24 h para el visto bueno"
    limite = datetime.fromisoformat(
        cliente.get(f"/cierre/servicio/{servicio['id']}/estado", headers=h)
        .json()["limite"])
    assert f"{limite:%d/%m}" in aviso["cuerpo"] and f"{limite:%H:%M}" in aviso["cuerpo"]
    assert "Qué hacer" in aviso["datos"]
    assert aviso["enlace"] == f"/consola/#/servicio/{servicio['id']}"


def test_finanzas_lo_regreso_tambien_por_correo(cliente, sesion, datos):
    """Finanzas regresa el servicio y corren otras 24 horas: el correo
    dice el motivo, hasta cuando, y que lo en plazo se queda."""
    from app import models as m

    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2150)
    c = _cierre(servicio["id"])
    assert cliente.post(f"/cierre/{c.id}/enviar-finanzas",
                        headers=sesion("consultor")).status_code == 200
    r = cliente.post(f"/cierre/{c.id}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "La hora de termino esta mal capturada"})
    assert r.status_code == 200, r.text
    hasta = datetime.fromisoformat(r.json()["hasta"])

    avisos = _avisos(servicio["id"], m.Destinatario.CONSULTOR)
    assert len(avisos) == 2, "las 24 h del visto bueno y el regreso"
    regreso = avisos[-1]
    assert regreso["asunto"] == f"{servicio['folio']}: finanzas lo regresó"
    assert f"{hasta:%d/%m}" in regreso["cuerpo"]
    assert "en plazo" in regreso["cuerpo"]
    assert "La hora de termino esta mal capturada" in regreso["datos"]
    assert regreso["correo"] == datos["personal"]["Ana Solis"]["correo"]


# ======================================= 60 · justificar (a4-08)

def test_justificar_una_desviacion_viva_con_su_tipo_y_solo_sin_visto_bueno(
        cliente, sesion, datos, db):
    """Se justifica una desviacion que la revision ensena, tal como la
    dice, y se guarda con su tipo y su monto; cualquier otro texto se
    rechaza, y con el cierre ya aprobado tambien."""
    from app import models as m

    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2155,
                                   agente_extra=True)
    c = _cierre(servicio["id"])
    h = sesion("consultor")
    comparativo = cliente.get(f"/cierre/servicio/{servicio['id']}/comparativo",
                              headers=h).json()
    viva = next(d for d in comparativo["desviaciones"]
                if d["tipo"] == "recurso_no_cotizado")
    justificacion = {"justificacion": "El cliente pidio un agente mas el ultimo dia"}

    # Antes del visto bueno el cierre esta en comprobacion: se abre
    # cuando llega T1, y como no hay viaticos llega en cuanto se pide.
    cliente.post(f"/cierre/{c.id}/enviar-finanzas", headers=h)
    r = cliente.post(f"/cierre/{c.id}/desviaciones/respaldar", headers=h,
                     params={"descripcion": "algo que no existe"}, json=justificacion)
    assert r.status_code == 409, r.text
    r = cliente.post(f"/cierre/{c.id}/desviaciones/respaldar", headers=h,
                     params={"descripcion": viva["descripcion"]},
                     json={"justificacion": "x" * 600})
    assert r.status_code == 422, r.text
    r = cliente.post(f"/cierre/{c.id}/desviaciones/respaldar", headers=h,
                     params={"descripcion": viva["descripcion"]}, json=justificacion)
    assert r.status_code == 200, r.text
    assert r.json()["tipo"] == "recurso_no_cotizado"
    guardada = db.query(m.Desviacion).filter_by(cierre_id=c.id).one()
    assert guardada.tipo == m.TipoDesviacion.RECURSO_NO_COTIZADO
    assert float(guardada.monto) == float(viva["monto"]) and guardada.respaldada
    # Dos veces, no.
    r = cliente.post(f"/cierre/{c.id}/desviaciones/respaldar", headers=h,
                     params={"descripcion": viva["descripcion"]}, json=justificacion)
    assert r.status_code == 409, r.text

    # Justificada, ya no frena; y aprobado, ya no se justifica nada.
    envio = cliente.post(f"/cierre/{c.id}/enviar-finanzas", headers=h)
    assert envio.status_code == 200, envio.text
    assert cliente.post(f"/cierre/{c.id}/aprobar",
                        headers=sesion("finanzas")).status_code == 200
    r = cliente.post(f"/cierre/{c.id}/desviaciones/respaldar", headers=h,
                     params={"descripcion": viva["descripcion"]}, json=justificacion)
    assert r.status_code == 409, r.text
    assert "finanzas" in r.json()["detail"]["mensaje"]


# ===================== 60 · los sellos en hora del pais (a4-10, a9-16)

def _zona_de_mexico(zona):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        mx = db.query(m.Pais).filter_by(codigo="MX").one()
        antes = mx.zona_horaria
        mx.zona_horaria = zona
        db.commit()
        return antes


def test_la_aprobacion_y_la_factura_se_sellan_con_la_hora_del_pais(
        cliente, sesion, datos, odoo):
    """Con el pais tres horas adelante del servidor, la aprobacion, la
    factura y su intento llevan la hora de alla: de esa fecha salen el
    mes de la comision y el del historial."""
    from app import models as m, reloj
    from app.db import SessionLocal

    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2160)
    c = _cierre(servicio["id"])
    antes = _zona_de_mexico("America/Sao_Paulo")
    try:
        assert cliente.post(f"/cierre/{c.id}/enviar-finanzas",
                            headers=sesion("consultor")).status_code == 200
        assert cliente.post(f"/cierre/{c.id}/aprobar",
                            headers=sesion("finanzas")).status_code == 200
        alla = reloj.ahora_en(type("P", (), {"zona_horaria": "America/Sao_Paulo"})())
        with SessionLocal() as db:
            fila = db.get(m.Cierre, c.id)
            assert fila.factura_odoo and fila.estatus == m.EstatusCierre.FACTURADO
            sellos = (fila.aprobado_en, fila.facturado_en, fila.factura_intento_en)
    finally:
        _zona_de_mexico(antes)
    for sello in sellos:
        assert sello is not None
        assert abs((sello - alla).total_seconds()) < 180, (sello, alla)
        # Y no la del servidor, que corre en hora de Mexico.
        assert abs((sello - datetime.now()).total_seconds()) > 3600


# ===================== 60 · lo que la lista no cotiza se reporta (a4-11)

def test_sin_rol_la_revision_lo_reporta_en_vez_de_reventar(cliente, sesion, datos):
    """Una asignacion sin rol: la revision contesta con una observacion
    que dice que hacer, y el envio a finanzas la devuelve como las
    demas, en vez de un 400 suelto."""
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(2165), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(cliente, h, servicio,
                        datos["perfiles"]["conductor_seguridad"]["id"],
                        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Luis Mendoza"]["id"],
            vehiculo_id=datos["suburban"]["id"], rol=None)
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("luis"), j)

    r = cliente.get(f"/cierre/servicio/{servicio['id']}/revision", headers=h)
    assert r.status_code == 200, r.text
    revision = r.json()
    assert revision["listo_para_finanzas"] is False
    assert revision["comparativo"] is None
    obs = revision["observaciones"][0]
    assert obs["nivel"] == "corregir" and obs["clave"] == "sin_rol"
    assert "sin rol" in obs["mensaje"]

    c = _cierre(servicio["id"])
    envio = cliente.post(f"/cierre/{c.id}/enviar-finanzas", headers=h)
    assert envio.status_code == 409, envio.text
    assert envio.json()["detail"]["observaciones"][0]["clave"] == "sin_rol"


def test_sin_precio_en_la_lista_la_revision_lo_reporta(cliente, sesion, datos, db):
    """El rol con el que fue no esta en la lista del cliente: la
    observacion dice cual y en que modalidad."""
    from app import models as m, revisor

    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2170)
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    full_day = datos["modalidades"]["full_day"]["id"]
    tarifa = (db.query(m.TarifaRecurso)
              .filter_by(perfil_id=conductor, modalidad_id=full_day).one())
    # Solo en esta sesion, que se deshace al terminar: la lista es catalogo.
    db.delete(tarifa)
    db.flush()
    revision = revisor.revisar(db, servicio["id"])
    assert revision["listo_para_finanzas"] is False
    obs = revision["observaciones"][0]
    assert obs["clave"] == "sin_precio"
    assert obs["datos"] == {"que": "Conductor de seguridad", "modalidad": "full_day"}
    assert "no tiene precio" in obs["mensaje"]
    db.rollback()


# ================================ 60 · el rango de la escala (a4-12)

def test_una_respuesta_de_escala_fuera_de_rango_se_rechaza(cliente, sesion, datos):
    """1000 en puntualidad entraba y se volvia el promedio; con
    negativos lo hundia. Las de escala van de 1 a 5 y las abiertas con
    texto; lo que se sale contesta 422."""
    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2175)
    _, token = _token(cliente, sesion, servicio["id"], "solicitante")
    base = {"respuesta_cotizacion": 5, "claridad": 4, "seguimiento": 5}
    for mal in ({**base, "respuesta_cotizacion": 1000},
                {**base, "claridad": -4},
                {**base, "claridad": 0},
                {**base, "seguimiento": "muy bien"},
                {**base, "comentario": 5}):
        r = _contestar(cliente, token, 5, mal)
        assert r.status_code == 422, (mal, r.text)
    r = _contestar(cliente, token, 5, {**base, "comentario": "Todo bien"})
    assert r.status_code == 200, r.text
    ana = datos["personal"]["Ana Solis"]["id"]
    resumen = cliente.get(f"/encuestas/resumen/consultor/{ana}",
                          headers=sesion("consultor")).json()
    assert resumen["por_pregunta"]["respuesta_cotizacion"] == 5


# ============================ 60 · la pagina cerrada en su idioma (a4-13)

def test_la_pagina_cerrada_habla_el_idioma_de_la_encuesta(cliente, sesion, datos, db):
    """El principal recibio la encuesta en ingles y el solicitante en
    portugues: la contestada, la vencida y el error de validacion les
    hablan en ese idioma, no en espanol."""
    from app import models as m

    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2180,
                                   idioma_solicitante="pt")
    _, token = _token(cliente, sesion, servicio["id"], "ejecutivo")
    r = _contestar(cliente, token, 2, {})
    assert r.status_code == 400
    assert r.json()["detail"]["mensaje"] == "Some questions are still unanswered."
    assert _contestar(cliente, token, 5, {"mas_valoro": "ok"}).status_code == 200
    r = cliente.get(f"/encuestas/pagina/{token}")
    assert r.status_code == 409
    assert "already answered" in r.text and "contestada" not in r.text
    assert 'lang="en"' in r.text
    r = cliente.get(f"/encuestas/publica/{token}")
    assert r.status_code == 409 and r.json()["detail"]["clave"] == "contestada"

    _, token = _token(cliente, sesion, servicio["id"], "solicitante")
    (db.query(m.Encuesta).filter_by(token=token)
     .update({"expira_en": datetime.now() - timedelta(days=1)}))
    db.commit()
    r = cliente.get(f"/encuestas/pagina/{token}")
    assert r.status_code == 410
    assert "já venceu" in r.text and "vencio" not in r.text


# ================================== 60 · Odoo contesta sin folio (a4-14)

def test_si_odoo_contesta_sin_folio_el_cierre_no_queda_facturado(
        cliente, sesion, datos, odoo):
    """Odoo contesta 200 sin numero de factura: el cierre no se da por
    facturado, se queda por facturar con el error, y se reintenta."""
    from app import models as m
    from app.db import SessionLocal

    odoo.sin_folio = True
    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2185)
    c = _cierre(servicio["id"])
    envio = cliente.post(f"/cierre/{c.id}/enviar-finanzas", headers=sesion("consultor"))
    assert envio.status_code == 200, envio.text
    assert envio.json()["factura"]["resultado"] == "fallo"
    assert "sin folio" in envio.json()["factura"]["motivo"]
    with SessionLocal() as db:
        fila = db.get(m.Cierre, c.id)
        assert fila.facturado_en is None and fila.factura_odoo is None
        assert fila.factura_error == "Odoo contesto sin folio"
        assert fila.estatus == m.EstatusCierre.ENVIADO_FINANZAS

    pendientes = cliente.get("/cierre/por-facturar",
                             headers=sesion("finanzas")).json()["por_facturar"]
    mio = next(p for p in pendientes if p["cierre_id"] == c.id)
    assert mio["que_paso"] == "rechazada" and mio["intentos"] == 1

    odoo.sin_folio = False
    r = cliente.post(f"/cierre/{c.id}/facturar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["resultado"] == "facturado" and r.json()["factura"]
    with SessionLocal() as db:
        fila = db.get(m.Cierre, c.id)
        assert fila.facturado_en is not None and fila.factura_error is None


# ============================ 60 · dos vistos buenos a la vez (a4-16)

def test_dos_vistos_buenos_a_la_vez_no_duplican_los_ajustes(
        cliente, sesion, datos, monkeypatch):
    """Dos pestanas mandan el mismo cierre en el mismo segundo. El
    segundo espera el candado del cierre y ve "ya tiene visto bueno";
    las diferencias de nomina se calculan una sola vez."""
    from app import nomina

    servicio = _servicio_ejecutado(cliente, sesion, datos, offset=2190)
    c = _cierre(servicio["id"])
    h = sesion("consultor")
    respuestas = {}
    llamadas = []
    original = nomina.diferencias_del_servicio

    def segundo():
        respuestas["b"] = cliente.post(f"/cierre/{c.id}/enviar-finanzas", headers=h)

    hilo = threading.Thread(target=segundo)

    def con_el_segundo_encima(db, servicio_id, creado_por_id=None):
        llamadas.append(servicio_id)
        if len(llamadas) == 1:
            # El segundo envio arranca ahora, con el primero a medio
            # camino y la fila tomada: se queda esperando el candado.
            hilo.start()
            hilo.join(timeout=2.0)
            assert hilo.is_alive(), "el segundo no espero el candado"
        return original(db, servicio_id, creado_por_id)

    monkeypatch.setattr(nomina, "diferencias_del_servicio", con_el_segundo_encima)
    primero = cliente.post(f"/cierre/{c.id}/enviar-finanzas", headers=h)
    hilo.join(timeout=30)
    assert not hilo.is_alive()
    assert primero.status_code == 200, primero.text
    assert respuestas["b"].status_code == 409, respuestas["b"].text
    assert "ya tiene visto bueno" in respuestas["b"].json()["detail"]["mensaje"]
    assert len(llamadas) == 1, "las diferencias de nomina se calcularon dos veces"

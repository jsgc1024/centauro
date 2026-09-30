# -*- coding: utf-8 -*-
"""Seccion 105 (g2): el eventual en la calle.

Ola 5 de la revision del 28 de septiembre, con las decisiones de
Salvador del 29: cambiar la unidad por contingencia en el eventual
(decision 3: boton "Cambiar" en la unidad, sin correo al cliente, con
"Deshacer"), cada persona marca su propia llegada (decision 4: la
geocerca de cada quien, un solo aviso al cliente, el camino vigila a
cada quien, la puntualidad del bono con la llegada propia) y la hora
de manana que captura el conductor pasa por la central (decision 5:
propuesta, "Confirmar" o "Dejar la de la hoja" desde "Manana", el
reloj de las 22:00, el punto no se mueve con el GPS).
"""
import os
from datetime import date, datetime, time, timedelta

import pytest

from ayudas import (ORIGEN, asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, jornada, manana, marcar, marcar_fin,
                    revisar_unidad, KM_RECEPCION)
from app import models as m
from app import push

RAIZ = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def avisos(monkeypatch):
    """Los avisos al telefono, anotados en vez de mandados."""
    llamadas = []

    def falso(db, persona_id, titulo, cuerpo, **extra):
        llamadas.append({"persona_id": persona_id, "titulo": titulo,
                         "cuerpo": cuerpo, **extra})
        return {"enviados": 1, "telefonos": 1, "apagadas": 0}

    monkeypatch.setattr(push, "avisar", falso)
    return llamadas


# ---------------------------------------------------------------- decorado

def _otra_unidad(datos):
    return next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"]
                and v["categoria_id"] == datos["suburban"]["categoria_id"])


def _montado(cliente, sesion, datos, offset=300, dias=2,
             gente=("Juan Ramirez",)):
    """Un eventual de `dias` dias en el futuro con la Suburban y su gente,
    cotizado y con su punto."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"])
         for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    for j in servicio["equipos"][0]["jornadas"]:
        for quien in gente:
            r = asignar(cliente, h, j["id"],
                        persona_id=datos["personal"][quien]["id"])[0]
            assert r.status_code == 200, r.text
        r = asignar(cliente, h, j["id"], vehiculo_id=datos["suburban"]["id"])[0]
        assert r.status_code == 200, r.text
        configurar_origen(cliente, h, j["id"])
    return servicio


def _de_hoy(cliente, sesion, datos, gente=("Juan Ramirez",), minutos=50):
    """Un servicio de hoy que arranco hace `minutos`, con la Suburban. El
    dia es el del arranque, por si la bateria corre pasada la medianoche."""
    ahora = datetime.now().replace(second=0, microsecond=0)
    inicio = ahora - timedelta(minutes=minutos)
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(inicio.date(), datos["modalidades"]["full_day"]["id"],
                 hora=inicio.strftime("%H:%M:00"))],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    for quien in gente:
        r = asignar(cliente, h, j["id"],
                    persona_id=datos["personal"][quien]["id"])[0]
        assert r.status_code == 200, r.text
    r = asignar(cliente, h, j["id"], vehiculo_id=datos["suburban"]["id"])[0]
    assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    return servicio, j, inicio


def _cambio_unidad(cliente, sesion, datos, j, entra=None, previa=False,
                   **extra):
    ruta = "/contingencia/reemplazos/vehiculo" + ("/vista-previa" if previa
                                                   else "")
    return cliente.post(ruta, headers=sesion("consultor"), json={
        "desde_jornada_id": j["id"],
        "sale_vehiculo_id": datos["suburban"]["id"],
        "entra_vehiculo_id": (entra or _otra_unidad(datos))["id"],
        "motivo": "Se poncho", **extra})


def _unidades(cliente, sesion, jornada_id):
    r = cliente.get(f"/servicios/jornadas/{jornada_id}/asignaciones",
                    headers=sesion("consultor"))
    return sorted(v["placa"] for v in r.json()["vehiculos"])


def _historial(cliente, sesion, servicio):
    return cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                       headers=sesion("consultor")).json()


def _correos(servicio_id):
    from app.db import SessionLocal
    with SessionLocal() as db:
        return (db.query(m.Notificacion)
                .filter_by(servicio_id=servicio_id).all())


def _estado(jornada_id):
    from app.db import SessionLocal
    with SessionLocal() as db:
        j = db.get(m.Jornada, jornada_id)
        return {"jornada": j.estatus.value,
                "hitos": db.query(m.Hito).filter_by(jornada_id=j.id).count(),
                "avisos": db.query(m.Notificacion)
                            .filter_by(jornada_id=j.id).count()}


def _mi_dia(cliente, sesion, quien, ahora=None):
    ruta = "/campo/mi-dia" + (f"?ahora={ahora.isoformat()}" if ahora else "")
    r = cliente.get(ruta, headers=sesion(quien))
    assert r.status_code == 200, r.text
    return r.json()


def _publicar_hoja(cliente, sesion, servicio):
    r = cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                     headers=sesion("consultor"), json={"forzar": True})
    assert r.status_code == 200, r.text
    return r.json()


def _revision_del_dia(cliente, sesion, jornada_id):
    r = cliente.get(f"/central/jornadas/{jornada_id}/revision",
                    headers=sesion("central"))
    assert r.status_code == 200, r.text
    return {p["clave"]: p for p in r.json()["revision"]}


def _web(nombre):
    return open(os.path.join(RAIZ, "app", "web", nombre),
                encoding="utf-8").read()


# ================================================ decision 3 · la unidad

def test_cambiar_la_unidad_no_avisa_al_cliente_y_la_persona_si(
        cliente, sesion, datos, avisos):
    """Se poncha la Suburban hoy. El cambio de unidad no le escribe al
    cliente (decision 3 de Salvador), pero al equipo le llega "cambio
    la unidad" al telefono. Cambiar a la persona ese mismo dia si
    manda el correo, como hoy."""
    servicio, j, _ = _de_hoy(cliente, sesion, datos)
    otra = _otra_unidad(datos)
    avisos.clear()                      # el "te acaban de asignar" del armado
    r = _cambio_unidad(cliente, sesion, datos, j, entra=otra)
    assert r.status_code == 200, r.text
    assert r.json()["cliente_avisado"] is False
    assert not [c for c in _correos(servicio["id"])
                if otra["placa"] in (c.cuerpo or "")]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    suyos = [a for a in avisos if a["persona_id"] == juan]
    assert len(suyos) == 1, avisos
    assert suyos[0]["titulo"] == push.tx("es", "cambio_unidad_titulo")
    assert otra["placa"] in suyos[0]["cuerpo"]
    assert datos["suburban"]["placa"] in suyos[0]["cuerpo"]
    assert push.tx("pt", "cambio_unidad_titulo") != push.tx("es", "cambio_unidad_titulo")

    r = cliente.post("/contingencia/reemplazos/personal",
                     headers=sesion("consultor"), json={
                         "desde_jornada_id": j["id"],
                         "sale_persona_id": juan,
                         "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
                         "motivo": "Se sintio mal"})
    assert r.status_code == 200, r.text
    assert r.json()["cliente_avisado"] is True
    assert [c for c in _correos(servicio["id"]) if "Luis" in (c.cuerpo or "")]


def test_el_cambio_de_unidad_vuelve_a_publicar_la_hoja_sin_correo(
        cliente, sesion, datos):
    """Con la hoja ya publicada, el cambio de unidad la vuelve a publicar
    solo, con la placa nueva y sin escribirle al cliente: la vigente es
    la que va, la tarjeta del cambio no la marca vieja y la revision de
    la vispera dice "hoja: lista"."""
    servicio = _montado(cliente, sesion, datos, offset=300, dias=2)
    dias = servicio["equipos"][0]["jornadas"]
    assert _publicar_hoja(cliente, sesion, servicio)["version"] == 1
    antes = len(_correos(servicio["id"]))

    r = _cambio_unidad(cliente, sesion, datos, dias[0])
    assert r.status_code == 200, r.text
    assert r.json()["hoja_republicada"] == 2
    assert r.json()["hoja_por_publicar"] is False
    assert len(_correos(servicio["id"])) == antes
    assert _historial(cliente, sesion, servicio)[0]["hoja_por_publicar"] is False
    assert _revision_del_dia(cliente, sesion, dias[1]["id"])["hoja"]["listo"]
    # La hoja nueva trae la placa que entro.
    hoja = cliente.get(f"/task-sheets/equipo/{servicio['equipos'][0]['id']}",
                       headers=sesion("consultor")).json()
    assert hoja["version"] == 2
    assert _otra_unidad(datos)["placa"] in str(hoja)

    # Sin hoja publicada no hay nada que republicar.
    otro = _montado(cliente, sesion, datos, offset=310, dias=1)
    r = _cambio_unidad(cliente, sesion, datos, otro["equipos"][0]["jornadas"][0])
    assert r.status_code == 200, r.text
    assert r.json()["hoja_republicada"] is None
    assert r.json()["hoja_por_publicar"] is False


def test_la_vista_previa_de_la_unidad_no_guarda_nada(cliente, sesion, datos):
    """El panel de la unidad ensena lo que va a pasar --los dias, la
    revision pendiente-- sin dejar rastro, como el de la persona."""
    servicio = _montado(cliente, sesion, datos, offset=320, dias=3)
    dias = servicio["equipos"][0]["jornadas"]
    r = _cambio_unidad(cliente, sesion, datos, dias[1], previa=True)
    assert r.status_code == 200, r.text
    assert r.json()["jornadas_afectadas"] == [dias[1]["fecha"], dias[2]["fecha"]]
    assert r.json()["jornadas_partidas"] == []
    assert r.json()["revision_pendiente"]["recepcion_de_la_que_entra"] is True
    assert _historial(cliente, sesion, servicio) == []
    for d in dias:
        assert _unidades(cliente, sesion, d["id"]) == [datos["suburban"]["placa"]]


def test_deshacer_un_cambio_de_unidad_recien_hecho(cliente, sesion, datos):
    """El consultor eligio la placa equivocada hace un minuto: deshacer
    devuelve la Suburban a sus dias y borra el movimiento. Antes el
    servidor contestaba "solo se deshacen los cambios de personal"."""
    servicio = _montado(cliente, sesion, datos, offset=340, dias=3)
    dias = servicio["equipos"][0]["jornadas"]
    otra = _otra_unidad(datos)
    hecho = _cambio_unidad(cliente, sesion, datos, dias[1], entra=otra).json()
    assert _unidades(cliente, sesion, dias[1]["id"]) == [otra["placa"]]

    r = cliente.post(f"/contingencia/reemplazos/{hecho['reemplazo_id']}/deshacer",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["jornadas"] == [dias[1]["fecha"], dias[2]["fecha"]]
    for d in dias:
        assert _unidades(cliente, sesion, d["id"]) == [datos["suburban"]["placa"]]
    assert _historial(cliente, sesion, servicio) == []


def test_deshacer_junta_el_dia_que_se_partio_y_devuelve_a_quien_iba_a_bordo(
        cliente, sesion, datos):
    """Hoy la Suburban ya rodo: el cambio parte el dia y Juan pasa a la
    unidad nueva. Deshacer junta el dia, borra la unidad que entro y
    regresa a Juan a la Suburban."""
    servicio, j, inicio = _de_hoy(cliente, sesion, datos)
    assert marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    otra = _otra_unidad(datos)
    hecho = _cambio_unidad(cliente, sesion, datos, j, entra=otra).json()
    assert hecho["jornadas_partidas"] == [j["fecha"]]
    assert _unidades(cliente, sesion, j["id"]) == sorted(
        [otra["placa"], datos["suburban"]["placa"]])

    r = cliente.post(f"/contingencia/reemplazos/{hecho['reemplazo_id']}/deshacer",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert _unidades(cliente, sesion, j["id"]) == [datos["suburban"]["placa"]]
    ficha = cliente.get(f"/servicios/jornadas/{j['id']}/asignaciones",
                        headers=sesion("consultor")).json()
    # Con una sola unidad nadie va "a bordo" de una en particular; lo
    # que no puede quedar es alguien colgado de la que ya no esta.
    assert ficha["personal"][0]["abordo"] != otra["placa"]
    assert _historial(cliente, sesion, servicio) == []


def test_deshacer_la_unidad_se_niega_si_ya_se_recibio_o_ya_regreso(
        cliente, sesion, datos):
    """El cambio ya ocurrio en la calle --la unidad que entro se recibio
    con sus fotos-- o el titular ya regreso: no se deshace, y el servidor
    dice que hacer."""
    servicio = _montado(cliente, sesion, datos, offset=360, dias=3)
    dias = servicio["equipos"][0]["jornadas"]
    otra = _otra_unidad(datos)
    hecho = _cambio_unidad(cliente, sesion, datos, dias[0], entra=otra).json()
    r = revisar_unidad(cliente, sesion("juan"), servicio["id"], otra["id"],
                       "recibe", KM_RECEPCION)
    assert r.status_code == 201, r.text

    r = cliente.post(f"/contingencia/reemplazos/{hecho['reemplazo_id']}/deshacer",
                     headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert "recibi" in r.json()["detail"]["mensaje"]
    assert r.json()["detail"]["que_hacer"]
    assert _unidades(cliente, sesion, dias[0]["id"]) == [otra["placa"]]

    # Con el regreso capturado tampoco: ese movimiento ya se cerro.
    otro = _montado(cliente, sesion, datos, offset=380, dias=3)
    dias = otro["equipos"][0]["jornadas"]
    hecho = _cambio_unidad(cliente, sesion, datos, dias[0], entra=otra).json()
    r = cliente.post(f"/contingencia/reemplazos/{hecho['reemplazo_id']}/regreso",
                     headers=sesion("consultor"), json={"desde": dias[2]["fecha"]})
    assert r.status_code == 200, r.text
    assert r.json()["cliente_avisado"] is False
    r = cliente.post(f"/contingencia/reemplazos/{hecho['reemplazo_id']}/deshacer",
                     headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert "regreso" in r.json()["detail"]["mensaje"].lower()


def test_la_ficha_de_recursos_dice_la_unidad_relevada_y_su_categoria(
        cliente, sesion, datos):
    """La tarjeta de recursos necesita saber que unidad ya fue relevada
    --a esa no se le ofrece "Cambiar" otra vez-- y de que categoria es,
    para buscar otra igual."""
    servicio, j, inicio = _de_hoy(cliente, sesion, datos)
    assert marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    otra = _otra_unidad(datos)
    assert _cambio_unidad(cliente, sesion, datos, j, entra=otra).status_code == 200

    equipo = servicio["equipos"][0]["id"]
    fichas = {v["placa"]: v for v in cliente.get(
        f"/servicios/equipos/{equipo}/asignaciones",
        headers=sesion("consultor")).json()["vehiculos"]}
    assert fichas[datos["suburban"]["placa"]]["relevado_en"]
    assert fichas[otra["placa"]]["relevado_en"] is None
    assert fichas[otra["placa"]]["categoria_id"] == otra["categoria_id"]


def test_la_pantalla_ofrece_cambiar_la_unidad_y_deshacer():
    """La consola: "Cambiar" en la unidad con su vista previa, y
    "Deshacer" en la tarjeta del cambio para personas y unidades, solo
    para quien releva."""
    js = _web("servicio.js")
    assert "function abrirCambioUnidad(" in js
    assert "/contingencia/reemplazos/vehiculo/vista-previa" in js
    assert 'api.post(\n          "/contingencia/reemplazos/vehiculo",' in js
    assert "function botonDeshacer(r)" in js
    assert "/contingencia/reemplazos/${r.id}/deshacer" in js
    assert 'tiene(sesion.usuario, "relevos.mover")' in js
    assert 'servicio.tipo === "eventual" && !v.relevado_en && puedeRelevar()' in js
    idioma = _web("idioma.js")
    for clave in ("ctg_cambiar_unidad", "ctg_deshacer", "ctg_deshacer_confirma",
                  "ctg_cambio_u_hecho"):
        assert idioma.count(f"    {clave}:") == 3, clave


# ================================================ decision 4 · la llegada

def test_cada_quien_marca_su_llegada_y_el_cliente_se_entera_una_vez(
        cliente, sesion, datos):
    """Equipo de dos. Juan marca su llegada: el dia queda arribado y
    salen los dos correos al cliente. Luis marca la suya: se guarda,
    ningun correo nuevo. Luis vuelve a marcar con otra hora: rechazada
    como duplicada; la misma marca repetida por la cola sigue siendo
    una sola."""
    servicio = _montado(cliente, sesion, datos, offset=900, dias=1,
                        gente=("Juan Ramirez", "Luis Mendoza"))
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])

    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=10))
    assert r.status_code == 200, r.text
    despues_de_juan = _estado(j["id"])
    assert despues_de_juan == {"jornada": "arribado", "hitos": 1, "avisos": 2}

    cuando = inicio - timedelta(minutes=5)
    r = marcar(cliente, sesion("luis"), j["id"], "llegada_origen", cuando)
    assert r.status_code == 200, r.text
    assert r.json()["dentro_geocerca"] is True
    despues_de_luis = _estado(j["id"])
    assert despues_de_luis == {"jornada": "arribado", "hitos": 2, "avisos": 2}

    otra_vez = marcar(cliente, sesion("luis"), j["id"], "llegada_origen",
                      inicio - timedelta(minutes=3))
    assert otra_vez.status_code == 409, otra_vez.text
    assert "Ya marcaste tu llegada" in otra_vez.json()["detail"]["mensaje"]
    assert otra_vez.json()["detail"]["que_hacer"]
    assert _estado(j["id"])["hitos"] == 2

    repetida = marcar(cliente, sesion("luis"), j["id"], "llegada_origen", cuando)
    assert repetida.status_code == 200, repetida.text
    assert repetida.json()["hito_id"] == r.json()["hito_id"]
    assert _estado(j["id"]) == despues_de_luis


def test_la_app_del_segundo_sigue_ofreciendo_marcar_llegada(
        cliente, sesion, datos):
    """Juan marco llegada y contacto. Antes la app de Luis le ofrecia
    "Fin de servicio" como siguiente paso; ahora le ofrece marcar SU
    llegada, y despues de marcarla sigue con lo de hoy."""
    servicio = _montado(cliente, sesion, datos, offset=901, dias=1,
                        gente=("Juan Ramirez", "Luis Mendoza"))
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])
    assert marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    assert marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo",
                  inicio).status_code == 200

    ahora = inicio + timedelta(minutes=30)
    de_luis = _mi_dia(cliente, sesion, "luis", ahora)["hoy"][0]
    assert de_luis["estatus"] == "en_curso"
    assert de_luis["siguiente"] == "llegada_origen"
    assert de_luis["sueltos"] == []
    de_juan = _mi_dia(cliente, sesion, "juan", ahora)["hoy"][0]
    assert de_juan["siguiente"] == "fin_servicio"

    assert marcar(cliente, sesion("luis"), j["id"], "llegada_origen",
                  inicio + timedelta(minutes=5)).status_code == 200
    de_luis = _mi_dia(cliente, sesion, "luis", ahora)["hoy"][0]
    assert de_luis["siguiente"] == "fin_servicio"
    assert len(de_luis["marcados"]) == 3


def test_el_camino_sigue_vigilando_al_que_no_ha_llegado(cliente, sesion, datos):
    """Dos unidades. Juan llego y el dia esta en el punto; Luis sigue
    dormido. Antes el pulso dejaba de mirar la jornada arribada y a Luis
    nadie lo tocaba ni lo alertaba. Ahora le toca a el, y solo a el; en
    cuanto marca su llegada, se apaga."""
    from app.db import SessionLocal
    from app import trayecto

    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(date.today(), datos["modalidades"]["full_day"]["id"],
                 hora="23:30:00")])
    j = servicio["equipos"][0]["jornadas"][0]
    for quien in ("Juan Ramirez", "Luis Mendoza"):
        asignar(cliente, h, j["id"], persona_id=datos["personal"][quien]["id"])
    asignar(cliente, h, j["id"], vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]

    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=10))
    assert r.status_code == 200, r.text
    assert _estado(j["id"])["jornada"] == "arribado"

    with SessionLocal() as db:
        estar = trayecto.hora_de_estar(db, db.get(m.Jornada, j["id"]))
        r = trayecto.pulsar(db, ahora=estar - timedelta(minutes=120))
        assert r["toques"] == 1, r
        vias = {v.persona_id: v for v in
                db.query(m.Trayecto).filter_by(jornada_id=j["id"]).all()}
        assert vias[juan].estado == m.EstadoTrayecto.LLEGO
        assert vias[luis].toques == 1
        # Quince minutos sin contestar: el silencio pesa, por persona.
        r = trayecto.pulsar(db, ahora=estar - timedelta(minutes=100))
        assert r["silencios"] == 1, r
        alertas = db.query(m.Alerta).filter_by(jornada_id=j["id"],
                                               tipo=m.TipoAlerta.SIN_REPORTE).all()
        assert [a.persona_id for a in alertas] == [luis]

    banda = cliente.get("/central/camino", headers=sesion("central")).json()
    assert [q["persona_id"] for q in banda["gente"]] == [luis]
    assert banda["gente"][0]["estado"] == "sin_respuesta"

    r = marcar(cliente, sesion("luis"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=5))
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert trayecto.pulsar(db, ahora=estar - timedelta(minutes=80))["toques"] == 0
        via = db.query(m.Trayecto).filter_by(jornada_id=j["id"],
                                             persona_id=luis).first()
        assert via.estado == m.EstadoTrayecto.LLEGO
        alerta = db.query(m.Alerta).filter_by(jornada_id=j["id"],
                                              persona_id=luis).first()
        assert alerta.atendida is True
    assert cliente.get("/central/camino",
                       headers=sesion("central")).json()["cuantos"] == 0


def test_la_central_ve_por_persona_quien_no_ha_llegado(cliente, sesion, datos,
                                                       db):
    """En el pulso, el renglon del dia dice quien del equipo todavia no
    marca su llegada, aunque el dia ya este corriendo con el otro."""
    from app import central

    servicio, j, inicio = _de_hoy(cliente, sesion, datos,
                                  gente=("Juan Ramirez", "Luis Mendoza"))
    assert marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    assert marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo",
                  inicio).status_code == 200

    def fila():
        db.expire_all()
        pulso = central.pulso(db, datetime.now())
        return next(f for f in pulso["eventuales"] if f["jornada_id"] == j["id"])

    assert fila()["sin_llegar"] == ["Luis Mendoza"]
    assert marcar(cliente, sesion("luis"), j["id"], "llegada_origen",
                  inicio + timedelta(minutes=5)).status_code == 200
    assert fila()["sin_llegar"] == []
    js = _web("central.js")
    assert "f.sin_llegar" in js and "cen_sin_llegar" in js


def test_la_central_asienta_la_llegada_del_segundo_a_mano(cliente, sesion,
                                                          datos):
    """Luis llego sin bateria y lo dijo por telefono. La central asienta
    su llegada aunque Juan ya haya marcado la suya: antes contestaba
    "ese dia ya tiene esa marca". La suya, dos veces, no."""
    servicio, j, inicio = _de_hoy(cliente, sesion, datos,
                                  gente=("Juan Ramirez", "Luis Mendoza"))
    assert marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    luis = datos["personal"]["Luis Mendoza"]["id"]
    cuerpo = {"tipo": "llegada_origen", "persona_id": luis,
              "momento": inicio.isoformat(),
              "justificacion": "se quedo sin bateria; llamo a la central"}
    r = cliente.post(f"/operacion/jornadas/{j['id']}/marca-a-mano",
                     headers=sesion("central"), json=cuerpo)
    assert r.status_code == 200, r.text
    assert _estado(j["id"])["hitos"] == 2

    r = cliente.post(f"/operacion/jornadas/{j['id']}/marca-a-mano",
                     headers=sesion("central"), json=cuerpo)
    assert r.status_code == 409, r.text
    assert "ya tiene su llegada" in r.json()["detail"]["mensaje"]


def test_el_bono_mide_la_llegada_de_cada_quien(cliente, sesion, datos):
    """Equipo de dos en un dia del mes. Juan marca su llegada, el
    contacto y el fin; Luis nunca marca la suya. Antes a Luis se le
    media con el contacto del equipo y salia puntual; ahora ese dia
    cuenta sin marca de llegada, y Juan sigue al cien."""
    h = sesion("consultor")
    hoy = date.today()
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(date(hoy.year, hoy.month, 12),
                 datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    for quien in ("Juan Ramirez", "Luis Mendoza"):
        r = asignar(cliente, h, j["id"],
                    persona_id=datos["personal"][quien]["id"],
                    vehiculo_id=(datos["suburban"]["id"]
                                 if quien == "Juan Ramirez" else None))
        assert r[0].status_code == 200, r[0].text
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    fin = datetime.fromisoformat(j["fin_programado"])
    assert marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    assert marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo",
                  inicio).status_code == 200
    assert marcar_fin(cliente, sesion("juan"), j["id"], fin).status_code == 200

    def evaluar(nombre):
        r = cliente.post("/evaluaciones", headers=h, json={
            "persona_id": datos["personal"][nombre]["id"],
            "anio": hoy.year, "mes": hoy.month, "capacitacion_cumplida": True})
        assert r.status_code in (200, 201), r.text
        return next(c for c in r.json()["criterios"]
                    if c["criterio"] == "Llegar al punto")

    de_juan = evaluar("Juan Ramirez")
    assert de_juan["cumplido"] is True and float(de_juan["medido"]) == 100.0
    de_luis = evaluar("Luis Mendoza")
    assert de_luis["aplica"] is True
    assert de_luis["cumplido"] is False
    assert float(de_luis["medido"]) == 0.0
    assert "Sin marca de llegada" in de_luis["detalle"]


# ============================================ decision 5 · la hora de manana

def _dos_dias(cliente, sesion, datos):
    """Hoy a las 08:00 y manana con la hora heredada, con Juan y Luis los
    dos dias y su punto. Luis ya confirmo el de manana."""
    h = sesion("consultor")
    modalidad = datos["modalidades"]["full_day"]["id"]
    servicio = crear_servicio(cliente, h, datos, [
        jornada(manana(0), modalidad, hora="08:00:00"),
        jornada(manana(1), modalidad, hora=None),
    ], consultor_id=datos["personal"]["Ana Solis"]["id"])
    dias = servicio["equipos"][0]["jornadas"]
    for j in dias:
        for quien in ("Juan Ramirez", "Luis Mendoza"):
            r = asignar(cliente, h, j["id"],
                        persona_id=datos["personal"][quien]["id"])[0]
            assert r.status_code == 200, r.text
        configurar_origen(cliente, h, j["id"])
    r = cliente.post(f"/operacion/jornadas/{dias[1]['id']}/confirmar-recurso",
                     headers=sesion("luis"))
    assert r.status_code == 200, r.text
    return servicio, dias


def _proponer(cliente, sesion, j, hora="07:30:00", **extra):
    return cliente.post(f"/campo/jornadas/{j['id']}/manana",
                        headers=sesion("juan"), json={"hora": hora, **extra})


def _jornada(db, jornada_id):
    db.expire_all()
    return db.get(m.Jornada, jornada_id)


def _ficha_de_manana(cliente, sesion, servicio):
    r = cliente.get("/central/manana", headers=sesion("central"))
    assert r.status_code == 200, r.text
    return next(f for f in r.json()["servicios"]
                if f["folio"] == servicio["folio"])


def test_la_hora_del_conductor_queda_como_propuesta(cliente, sesion, datos,
                                                    db, avisos):
    """(a) Juan manda 07:30 al cerrar hoy. Manana sigue con las 08:00 de
    la hoja y sin confirmar, nadie recibe "cambio tu hora", la app pinta
    "hora propuesta 07:30 · pendiente", la central la ve en "Manana" con
    quien y su nota, y queda en la bitacora del dia en que se supo."""
    servicio, dias = _dos_dias(cliente, sesion, datos)
    avisos.clear()
    r = _proponer(cliente, sesion, dias[0], direccion="Lobby del hotel",
                  nota="el principal sale temprano al aeropuerto")
    assert r.status_code == 200, r.text
    assert r.json()["pendiente"] is True
    assert r.json()["propuesta"]["hora"] == "07:30"
    assert r.json()["inicio"].endswith("08:00:00")

    j2 = _jornada(db, dias[1]["id"])
    assert j2.inicio_programado.strftime("%H:%M") == "08:00"
    assert j2.hora_confirmada is False
    assert j2.hora_propuesta.strftime("%H:%M") == "07:30"
    assert j2.hora_propuesta_resuelta is None
    assert j2.hora_propuesta_por_id == datos["personal"]["Juan Ramirez"]["id"]
    assert "Lobby del hotel" in j2.hora_propuesta_nota
    assert "aeropuerto" in j2.hora_propuesta_nota
    assert avisos == []

    de_luis = next(f for f in _mi_dia(cliente, sesion, "luis")["manana"]
                   if f["jornada_id"] == dias[1]["id"])
    assert de_luis["hora_confirmada"] is False
    assert de_luis["propuesta"]["hora"] == "07:30"
    assert de_luis["propuesta"]["por"] == "Juan Ramirez"

    ficha = _ficha_de_manana(cliente, sesion, servicio)
    assert ficha["hora_propuesta"]["hora"] == "07:30"
    assert ficha["hora_propuesta"]["por"] == "Juan Ramirez"
    assert ficha["hora_propuesta"]["de_la_hoja"] == "08:00"
    assert "Lobby" in ficha["hora_propuesta"]["nota"]
    assert ficha["servicio_inicia"].endswith("08:00:00")

    nota = db.query(m.NotaBitacora).filter_by(jornada_id=dias[0]["id"]).first()
    assert nota and "07:30" in nota.texto and "pendiente" in nota.texto


def test_la_central_confirma_la_propuesta(cliente, sesion, datos, db, avisos):
    """(b) La central confirma con un clic: manana arranca a las 07:30,
    la hora deja de ser heredada, a quien ya habia confirmado le llega
    "cambio tu hora", queda en la bitacora del servicio y la propuesta
    sale de "Manana". El consultor no puede: es de quien corrige."""
    servicio, dias = _dos_dias(cliente, sesion, datos)
    assert _proponer(cliente, sesion, dias[0]).status_code == 200
    avisos.clear()

    r = cliente.post(f"/central/manana/{dias[1]['id']}/confirmar-hora",
                     headers=sesion("consultor"))
    assert r.status_code == 403, r.text

    r = cliente.post(f"/central/manana/{dias[1]['id']}/confirmar-hora",
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    assert r.json()["inicio"].endswith("07:30:00")

    j2 = _jornada(db, dias[1]["id"])
    assert j2.inicio_programado.strftime("%H:%M") == "07:30"
    assert j2.fin_programado.strftime("%H:%M") == "19:30"
    assert j2.hora_confirmada is True
    assert j2.hora_propuesta_resuelta == "confirmada_central"

    luis = datos["personal"]["Luis Mendoza"]["id"]
    por_persona = {a["persona_id"]: a for a in avisos}
    assert luis in por_persona, avisos
    assert por_persona[luis]["titulo"] == push.tx("es", "cambio_hora_titulo")
    assert "07:30" in por_persona[luis]["cuerpo"]
    assert "08:00" in por_persona[luis]["cuerpo"]

    assert _ficha_de_manana(cliente, sesion, servicio)["hora_propuesta"] is None
    de_luis = next(f for f in _mi_dia(cliente, sesion, "luis")["manana"]
                   if f["jornada_id"] == dias[1]["id"])
    assert de_luis["propuesta"] is None
    assert de_luis["hora_confirmada"] is True
    assert de_luis["presentacion"].endswith("07:30:00")

    rastro = (db.query(m.RegistroAccion)
              .filter_by(servicio_id=servicio["id"], accion="hora de maniana")
              .first())
    assert rastro and "confirmada" in rastro.detalle

    # Ya resuelta, no se confirma dos veces.
    r = cliente.post(f"/central/manana/{dias[1]['id']}/confirmar-hora",
                     headers=sesion("central"))
    assert r.status_code == 409, r.text


def test_la_central_deja_la_de_la_hoja(cliente, sesion, datos, db, avisos):
    """(c) "Dejar la de la hoja": manana sigue a las 08:00, la propuesta
    queda rechazada y a Juan, que la propuso, le llega al telefono que
    se queda la hora de la hoja. A los demas, nada."""
    servicio, dias = _dos_dias(cliente, sesion, datos)
    assert _proponer(cliente, sesion, dias[0]).status_code == 200
    avisos.clear()

    r = cliente.post(f"/central/manana/{dias[1]['id']}/rechazar-hora",
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    assert r.json()["inicio"].endswith("08:00:00")

    j2 = _jornada(db, dias[1]["id"])
    assert j2.inicio_programado.strftime("%H:%M") == "08:00"
    assert j2.hora_confirmada is False
    assert j2.hora_propuesta_resuelta == "rechazada"

    juan = datos["personal"]["Juan Ramirez"]["id"]
    assert [a["persona_id"] for a in avisos] == [juan], avisos
    assert avisos[0]["titulo"] == push.tx("es", "hora_rechazada_titulo")
    assert "07:30" in avisos[0]["cuerpo"] and "08:00" in avisos[0]["cuerpo"]
    assert push.tx("pt", "hora_rechazada_titulo") != push.tx("es", "hora_rechazada_titulo")
    assert _ficha_de_manana(cliente, sesion, servicio)["hora_propuesta"] is None

    # Rechazada, ya no hay que confirmar. Y otra propuesta abre otra vez.
    r = cliente.post(f"/central/manana/{dias[1]['id']}/confirmar-hora",
                     headers=sesion("central"))
    assert r.status_code == 409, r.text
    assert _proponer(cliente, sesion, dias[0], hora="07:45:00").status_code == 200
    assert _jornada(db, dias[1]["id"]).hora_propuesta_resuelta is None


def test_el_reloj_confirma_lo_pendiente_a_las_22(cliente, sesion, datos, db,
                                                 avisos):
    """(d) Nadie toco la propuesta. A las 21:00 del pais el reloj no hace
    nada; a las 22:00 la confirma como la capturo el conductor, avisa
    "cambio tu hora", y una segunda vuelta no confirma dos veces."""
    from app import operacion
    from app.celery_app import celery
    from app import manual

    servicio, dias = _dos_dias(cliente, sesion, datos)
    assert _proponer(cliente, sesion, dias[0]).status_code == 200
    avisos.clear()
    hoy = date.fromisoformat(dias[0]["fecha"])

    r = operacion.confirmar_propuestas_vencidas(
        db, ahora=datetime.combine(hoy, time(21, 0)))
    assert r["confirmadas"] == []
    assert _jornada(db, dias[1]["id"]).hora_propuesta_resuelta is None
    assert avisos == []

    r = operacion.confirmar_propuestas_vencidas(
        db, ahora=datetime.combine(hoy, time(22, 5)))
    assert [c["jornada_id"] for c in r["confirmadas"]] == [dias[1]["id"]]
    assert r["confirmadas"][0]["hora"] == "07:30"
    j2 = _jornada(db, dias[1]["id"])
    assert j2.inicio_programado.strftime("%H:%M") == "07:30"
    assert j2.hora_confirmada is True
    assert j2.hora_propuesta_resuelta == "confirmada_reloj"
    luis = datos["personal"]["Luis Mendoza"]["id"]
    assert luis in {a["persona_id"] for a in avisos}, avisos
    assert all(a["titulo"] == push.tx("es", "cambio_hora_titulo") for a in avisos)

    avisos.clear()
    r = operacion.confirmar_propuestas_vencidas(
        db, ahora=datetime.combine(hoy, time(23, 5)))
    assert r["confirmadas"] == [] and avisos == []

    # La bitacora del dia en que se supo lo dice.
    notas = [n.texto for n in db.query(m.NotaBitacora)
             .filter_by(jornada_id=dias[0]["id"]).all()]
    assert any("nadie lo tocó" in n for n in notas), notas

    # Y el reloj la corre cada hora, con su renglon en el manual.
    tarea = celery.conf.beat_schedule["hora-de-manana-propuesta"]
    assert tarea["task"] == "campo.confirmar_hora_de_manana"
    assert "hora-de-manana-propuesta" in manual.TAREAS
    assert operacion.HORA_LIMITE_PROPUESTA == 22


def test_el_gps_del_conductor_no_mueve_el_punto(cliente, sesion, datos, db):
    """(e) El conductor manda su hora parado en otro lado, con su GPS:
    el punto de manana se queda el del task sheet, antes y despues de
    que la central confirme. Lo que escribio viaja en la nota."""
    servicio, dias = _dos_dias(cliente, sesion, datos)
    r = _proponer(cliente, sesion, dias[0], direccion="Oficina de Santa Fe",
                  lat="19.3600", lon="-99.2800")
    assert r.status_code == 200, r.text
    j2 = _jornada(db, dias[1]["id"])
    assert float(j2.origen_lat) == float(ORIGEN["origen_lat"])
    assert float(j2.origen_lon) == float(ORIGEN["origen_lon"])
    assert j2.origen_direccion == ORIGEN["origen_direccion"]
    assert "Oficina de Santa Fe" in j2.hora_propuesta_nota

    r = cliente.post(f"/central/manana/{dias[1]['id']}/confirmar-hora",
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    j2 = _jornada(db, dias[1]["id"])
    assert float(j2.origen_lat) == float(ORIGEN["origen_lat"])
    assert j2.origen_direccion == ORIGEN["origen_direccion"]
    assert j2.geocerca_metros == ORIGEN["geocerca_metros"]


def test_otra_propuesta_reemplaza_la_pendiente(cliente, sesion, datos, db):
    """Juan manda 07:30 y luego 07:45: la central ve una sola propuesta,
    la ultima. Y un dia que ya arranco no recibe propuestas."""
    servicio, dias = _dos_dias(cliente, sesion, datos)
    assert _proponer(cliente, sesion, dias[0], hora="07:30:00").status_code == 200
    assert _proponer(cliente, sesion, dias[0], hora="07:45:00").status_code == 200
    j2 = _jornada(db, dias[1]["id"])
    assert j2.hora_propuesta.strftime("%H:%M") == "07:45"
    assert j2.hora_propuesta_resuelta is None
    assert _ficha_de_manana(cliente, sesion, servicio)["hora_propuesta"]["hora"] == "07:45"


def test_la_app_y_la_central_hablan_de_la_propuesta():
    """La app manda la hora sin GPS y pinta "hora propuesta · pendiente";
    la central tiene los dos botones; el reloj tiene su tarea."""
    app = _web(os.path.join("campo", "app.js"))
    pantalla = app[app.index("function pantallaManana("):
                   app.index("/* ------------------------------------------- devolver")]
    assert "lat:" not in pantalla and "ubicacion()" not in pantalla
    assert 'alert(t("app_hora_propuesta"))' in pantalla
    assert 't("app_proponer_hora")' in pantalla
    assert 'app_hora_propuesta_pendiente' in app and "f.propuesta" in app

    central = _web("central.js")
    assert "function panelHoraPropuesta(f)" in central
    assert "confirmar-hora" in central and "rechazar-hora" in central
    assert "f.hora_propuesta ? panelHoraPropuesta(f)" in central

    idioma = _web("idioma.js")
    for clave in ("app_hora_propuesta", "app_hora_propuesta_pendiente",
                  "cen_hora_confirmar", "cen_hora_dejar", "cen_sin_llegar"):
        assert idioma.count(f"    {clave}:") == 3, clave

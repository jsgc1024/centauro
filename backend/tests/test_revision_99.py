# -*- coding: utf-8 -*-
"""Seccion 99: la app de campo y el ciclo del dia.

Segunda tanda de la revision del 28 de septiembre: el servicio
nocturno a medianoche, el relevado, las marcas repetidas y las que
llegan tarde, el dia que no ha llegado, el silencio, el standby en
espera, los avisos que se perdian, y las rutas que solo pedian sesion.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from ayudas import (DENTRO, asignar, configurar_origen, crear_servicio,
                    ejecutar_jornada, jornada, manana, marcar)

MX = ZoneInfo("America/Mexico_City")


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
def salieron(monkeypatch):
    """Los avisos al telefono que se habrian mandado, sin salir a internet."""
    import json

    import pywebpush
    from app import push

    mandados = []

    def falso(**kwargs):
        mandados.append(json.loads(kwargs["data"]))
        return True

    monkeypatch.setattr(pywebpush, "webpush", falso)
    monkeypatch.setattr(push.settings, "vapid_private", "llave-de-prueba")
    monkeypatch.setattr(push.settings, "vapid_public", "publica-de-prueba")
    return mandados


def _telefono(db, persona_id, endpoint="https://push.example/99"):
    from app import models as m
    fila = m.SuscripcionPush(persona_id=persona_id, endpoint=endpoint,
                             p256dh="clave-publica", auth="secreto")
    db.add(fila)
    db.commit()
    return fila


def _dia(cliente, sesion, datos, offset=900, hora="07:00:00",
         gente=("Juan Ramirez",), modalidad="full_day"):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"][modalidad]["id"],
                 hora=hora)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    for quien in gente:
        r = asignar(cliente, h, j["id"],
                    persona_id=datos["personal"][quien]["id"])[0]
        assert r.status_code == 200, r.text
    r = asignar(cliente, h, j["id"], vehiculo_id=datos["suburban"]["id"])[0]
    assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def _estado(jornada_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        j = db.get(m.Jornada, jornada_id)
        return {"jornada": j.estatus.value,
                "servicio": j.equipo.servicio.estatus.value,
                "hitos": db.query(m.Hito).filter_by(jornada_id=j.id).count(),
                "avisos": db.query(m.Notificacion)
                            .filter_by(jornada_id=j.id).count()}


def _mi_dia(cliente, sesion, quien, ahora=None):
    ruta = "/campo/mi-dia" + (f"?ahora={ahora.isoformat()}" if ahora else "")
    r = cliente.get(ruta, headers=sesion(quien))
    assert r.status_code == 200, r.text
    return r.json()


# ================================================== el dia en la calle

def test_el_servicio_nocturno_sigue_en_hoy_despues_de_medianoche(
        cliente, sesion, datos):
    """De 20:00 a 08:00. A la 01:00 el "hoy" del agente ya es otra fecha,
    y la app decia "no tienes servicios": sin boton de fin ni de
    standby, y el dia solo se cerraba a mano desde la central."""
    servicio, j = _dia(cliente, sesion, datos, offset=5, hora="20:00:00")
    inicio = datetime.fromisoformat(j["inicio_programado"])
    juan = sesion("juan")
    assert marcar(cliente, juan, j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    assert marcar(cliente, juan, j["id"], "contacto_ejecutivo",
                  inicio).status_code == 200

    # Y uno de hace tres dias que nadie cerro: ese ya no es de hoy para
    # nadie, lo recoge "Dias sin cerrar" en la central.
    _, viejo = _dia(cliente, sesion, datos, offset=2)
    arranque = datetime.fromisoformat(viejo["inicio_programado"])
    assert marcar(cliente, juan, viejo["id"], "llegada_origen",
                  arranque - timedelta(minutes=10)).status_code == 200
    assert marcar(cliente, juan, viejo["id"], "contacto_ejecutivo",
                  arranque).status_code == 200

    madrugada = inicio + timedelta(hours=5)          # 01:00 del dia siguiente
    dia = _mi_dia(cliente, sesion, "juan", madrugada)
    assert [f["jornada_id"] for f in dia["hoy"]] == [j["id"]], dia["hoy"]
    assert dia["hoy"][0]["siguiente"] == "fin_servicio"
    assert dia["manana"] == []

    # Y el fin se marca a las 08:00, ya con la otra fecha.
    fin = datetime.fromisoformat(j["fin_programado"])
    r = marcar(cliente, juan, j["id"], "fin_servicio", fin, ahora=fin)
    assert r.status_code in (200, 409), r.text     # 409 solo por la unidad
    if r.status_code == 409:
        assert "unidad" in r.json()["detail"]["mensaje"]


def test_una_llegada_tardia_no_reabre_un_dia_terminado(cliente, sesion, datos):
    """Dos en el equipo. Juan cierra el dia; la llegada de Luis sale de
    la cola despues: el dia se queda terminado y el servicio tambien."""
    servicio, j = _dia(cliente, sesion, datos, offset=900,
                       gente=("Juan Ramirez", "Luis Mendoza"))
    assert ejecutar_jornada(cliente, sesion("juan"), j).status_code == 200
    antes = _estado(j["id"])
    assert antes["jornada"] == "terminada" and antes["servicio"] == "terminado"

    inicio = datetime.fromisoformat(j["inicio_programado"])
    r = marcar(cliente, sesion("luis"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=5))
    assert r.status_code == 200, r.text
    despues = _estado(j["id"])
    assert despues["jornada"] == "terminada"
    assert despues["servicio"] == "terminado"
    # Su llegada se guardo, pero el cliente no recibio otro "su equipo
    # esta en el lugar".
    assert despues["hitos"] == antes["hitos"] + 1
    assert despues["avisos"] == antes["avisos"]


def test_la_misma_marca_dos_veces_es_una_sola(cliente, sesion, datos):
    """La cola reintenta cuando la respuesta se pierde: la segunda vuelta
    trae exactamente la misma marca, y el servidor la contesta sin
    volver a guardarla ni a mandar correos."""
    servicio, j = _dia(cliente, sesion, datos, offset=901)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    cuando = inicio - timedelta(minutes=10)
    primera = marcar(cliente, sesion("juan"), j["id"], "llegada_origen", cuando)
    assert primera.status_code == 200, primera.text
    antes = _estado(j["id"])
    assert antes["hitos"] == 1 and antes["avisos"] == 2

    segunda = marcar(cliente, sesion("juan"), j["id"], "llegada_origen", cuando)
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["hito_id"] == primera.json()["hito_id"]
    assert "ya estaba" in " ".join(segunda.json()["avisos"])
    despues = _estado(j["id"])
    assert despues["hitos"] == 1 and despues["avisos"] == 2


def test_el_dia_que_no_ha_llegado_no_se_marca(cliente, sesion, datos):
    """Parado en el punto de hoy, con su sesion, se podia cerrar el dia
    de manana con hora de manana: horas extra, cierre y encuestas hoy."""
    servicio, j = _dia(cliente, sesion, datos, offset=5)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    # El reloj del servidor se queda en hoy (`ahora=False`).
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=10), ahora=False)
    assert r.status_code == 409, r.text
    assert "no llega" in r.json()["detail"]["mensaje"]
    assert _estado(j["id"])["hitos"] == 0


def test_el_servicio_de_madrugada_se_marca_desde_la_vispera(
        cliente, sesion, datos):
    """Presentacion a las 00:30: el equipo sale de casa la noche anterior
    y marca su llegada a las 23:45, cuando la fecha del dia todavia no
    llega. Eso si entra: son las tres horas del meet and greet a mano."""
    servicio, j = _dia(cliente, sesion, datos, offset=6, hora="00:30:00")
    inicio = datetime.fromisoformat(j["inicio_programado"])
    cuando = inicio - timedelta(minutes=45)          # 23:45 de la vispera
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen", cuando,
               ahora=cuando)
    assert r.status_code == 200, r.text
    assert _estado(j["id"])["jornada"] == "arribado"


def test_una_marca_en_dia_cancelado_sigue_rechazada(cliente, sesion, datos):
    servicio, j = _dia(cliente, sesion, datos, offset=0)
    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "Cancelo el cliente"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               datetime.now() - timedelta(minutes=2))
    assert r.status_code == 409, r.text


# ================================================== el relevado

def test_el_relevado_ya_no_ve_el_dia_ni_lo_cierra(cliente, sesion, datos):
    """Juan se presenta, lo relevan y entra Luis. La app de Juan le
    seguia ofreciendo "Fin de servicio", y si lo tocaba desde su casa el
    dia terminaba con Luis todavia con el principal."""
    servicio, j = _dia(cliente, sesion, datos, offset=3)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    juan, h = sesion("juan"), sesion("consultor")
    assert marcar(cliente, juan, j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    assert marcar(cliente, juan, j["id"], "contacto_ejecutivo",
                  inicio).status_code == 200

    relevo = inicio + timedelta(hours=4)
    # El consultor lo captura una hora despues, con el reloj del servidor
    # ahi (seccion 101): una hora de relevo que todavia no llega ya no
    # se acepta.
    captura = (relevo + timedelta(hours=1)).isoformat()
    r = cliente.post(f"/contingencia/reemplazos/personal?ahora={captura}",
                     headers=h, json={
        "desde_jornada_id": j["id"],
        "sale_persona_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
        "motivo": "Se sintio mal", "relevado_en": relevo.isoformat()})
    assert r.status_code == 200, r.text

    # Su app: el dia ya no esta, y dice quien lo relevo y a que hora.
    dia = _mi_dia(cliente, sesion, "juan", relevo + timedelta(hours=1))
    assert dia["hoy"] == [], dia["hoy"]
    assert len(dia["relevado_hoy"]) == 1
    assert dia["relevado_hoy"][0]["por"] == "Luis Mendoza"
    assert dia["relevado_hoy"][0]["folio"] == servicio["folio"]

    # El fin desde su telefono, despues del relevo: no.
    fin = datetime.fromisoformat(j["fin_programado"])
    r = marcar(cliente, juan, j["id"], "fin_servicio", fin, ahora=fin)
    assert r.status_code == 409, r.text
    assert "relevaron" in r.json()["detail"]["mensaje"]
    assert _estado(j["id"])["jornada"] == "en_curso"
    # Tampoco fija la hora de manana.
    r = cliente.post(f"/campo/jornadas/{j['id']}/manana", headers=juan,
                     json={"hora": "08:00"})
    assert r.status_code in (403, 404, 409), r.text

    # Luis si ve el dia, sin Juan entre sus companeros.
    de_luis = _mi_dia(cliente, sesion, "luis", relevo + timedelta(hours=1))
    assert [f["jornada_id"] for f in de_luis["hoy"]] == [j["id"]]
    assert de_luis["hoy"][0]["companeros"] == []


def test_la_marca_del_relevado_de_antes_del_relevo_si_entra(
        cliente, sesion, datos):
    """La llegada que se quedo en la cola del telefono de Juan --de antes
    de que lo relevaran-- es suya y se guarda."""
    servicio, j = _dia(cliente, sesion, datos, offset=4)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    juan, h = sesion("juan"), sesion("consultor")
    assert marcar(cliente, juan, j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    # Capturado a las tres horas, con el reloj del servidor ahi (seccion
    # 101): una hora de relevo que todavia no llega ya no se acepta.
    captura = (inicio + timedelta(hours=3)).isoformat()
    r = cliente.post(f"/contingencia/reemplazos/personal?ahora={captura}",
                     headers=h, json={
        "desde_jornada_id": j["id"],
        "sale_persona_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
        "motivo": "Se sintio mal",
        "relevado_en": (inicio + timedelta(hours=2)).isoformat()})
    assert r.status_code == 200, r.text
    # El contacto de las 07:00 se quedo en la cola y llega a las 10:00,
    # ya relevado: es de antes del relevo, y entra.
    r = marcar(cliente, juan, j["id"], "contacto_ejecutivo", inicio,
               ahora=inicio + timedelta(hours=3))
    assert r.status_code == 200, r.text


# ================================================== el silencio y la espera

def test_esperando_al_principal_se_puede_decir_sigo_en_espera(
        cliente, sesion, datos):
    """Vuelo retrasado: llego y espera. El unico boton era el contacto, y
    a las dos horas saltaba la alerta de silencio."""
    servicio, j = _dia(cliente, sesion, datos, offset=902)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    juan = sesion("juan")
    assert marcar(cliente, juan, j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    ficha = cliente.get(f"/campo/jornadas/{j['id']}", headers=juan).json()
    assert ficha["siguiente"] == "contacto_ejecutivo"
    assert ficha["sueltos"] == ["standby"]

    r = marcar(cliente, juan, j["id"], "standby", inicio + timedelta(hours=1))
    assert r.status_code == 200, r.text


def test_la_alerta_de_silencio_se_cierra_sola_al_reportar(
        cliente, sesion, datos, db):
    """Calla dos horas, alerta; reporta standby: la alerta se cierra con
    quien y a que hora, y el siguiente silencio levanta la suya."""
    from app import models as m
    from app import operacion as motor

    servicio, j = _dia(cliente, sesion, datos, offset=903)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    juan = sesion("juan")
    assert marcar(cliente, juan, j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    assert marcar(cliente, juan, j["id"], "contacto_ejecutivo",
                  inicio).status_code == 200

    generadas = motor.revisar_standby(db, inicio + timedelta(hours=2, minutes=10))
    assert [g["jornada_id"] for g in generadas] == [j["id"]]

    r = marcar(cliente, juan, j["id"], "standby", inicio + timedelta(hours=2, minutes=20))
    assert r.status_code == 200, r.text
    db.expire_all()
    alertas = (db.query(m.Alerta)
               .filter_by(jornada_id=j["id"], tipo=m.TipoAlerta.SIN_REPORTE)
               .order_by(m.Alerta.id).all())
    assert len(alertas) == 1 and alertas[0].atendida is True
    assert "Juan Ramirez" in alertas[0].resolucion
    # Y la bitacora del dia dice como se cerro, no solo que se cerro.
    r = cliente.get(f"/operacion/jornadas/{j['id']}/dia", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    renglon = next(x for x in r.json()["renglones"] if x["fuente"] == "alerta")
    assert renglon["marca"] == "atendida"
    assert "Se resolvio sola: Juan Ramirez" in renglon["detalle"]

    # Otras dos horas callado con el principal a bordo: alerta nueva.
    generadas = motor.revisar_standby(db, inicio + timedelta(hours=4, minutes=30))
    assert [g["jornada_id"] for g in generadas] == [j["id"]]


# ================================================== los avisos que se perdian

def test_el_aviso_de_horas_extra_sale_aunque_el_reloj_llegue_tarde(
        cliente, sesion, datos, db):
    """El worker estuvo caido justo en la ventana de treinta minutos: la
    siguiente vuelta lo manda igual, diciendo que ya entro en horas
    extra. Y no lo repite."""
    from app import models as m
    from app import operacion as motor

    servicio, j = _dia(cliente, sesion, datos, offset=904)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    fin = datetime.fromisoformat(j["fin_programado"])
    juan = sesion("juan")
    assert marcar(cliente, juan, j["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    assert marcar(cliente, juan, j["id"], "contacto_ejecutivo",
                  inicio).status_code == 200

    avisos = motor.avisar_horas_extra(db, fin + timedelta(minutes=40))
    assert [a["jornada_id"] for a in avisos] == [j["id"]]
    assert avisos[0]["faltan_minutos"] < 0
    db.expire_all()
    notas = (db.query(m.Notificacion).filter_by(jornada_id=j["id"])
             .filter(m.Notificacion.asunto.ilike("%horas extra%")).all())
    assert notas and all("ya está en horas extra" in n.asunto for n in notas)
    # La segunda vuelta no vuelve a avisar.
    assert motor.avisar_horas_extra(db, fin + timedelta(minutes=45)) == []


def test_la_vispera_se_repone_en_la_primera_vuelta_que_falte(
        cliente, sesion, datos, db, salieron):
    """La tarea de las 17:00 corrio a las 18:05 porque el worker volvio
    tarde: el recordatorio sale igual, y a las 19:05 ya no se repite."""
    from app import push

    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    _telefono(db, juan)
    hoy_mx = datetime.now(MX).date()
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(hoy_mx + timedelta(days=1), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)

    a_las = lambda hh, mm: datetime.combine(hoy_mx, datetime.min.time()) \
        .replace(hour=hh, minute=mm, tzinfo=MX)
    visperas = lambda: [s for s in salieron if s["etiqueta"] == "vispera"]
    tarde = push.recordar_la_vispera(db, ahora=a_las(18, 5))
    assert "MX" in tarde["paises"], tarde
    assert any(a["persona_id"] == juan for a in tarde["avisados"])
    assert len(visperas()) == 1
    assert visperas()[0]["titulo"] == "Mañana trabajas"

    otra_vez = push.recordar_la_vispera(db, ahora=a_las(19, 5))
    assert "MX" not in otra_vez["paises"], otra_vez
    assert len(visperas()) == 1


def test_los_avisos_al_telefono_hablan_el_idioma_del_pais(db, datos, salieron):
    """A Brasil le llegaban en espanol. El idioma sale del pais de la
    plaza, como en la app; los botones de la notificacion tambien."""
    from app import models as m
    from app import push

    juan = datos["personal"]["Juan Ramirez"]["id"]
    _telefono(db, juan)
    assert push.idioma_de(db, juan) == "es"
    push.avisar(db, juan, "Centauro", push.tx("es", "prueba"),
                etiqueta="prueba", accion="confirmar")
    assert salieron[-1]["botones"]["confirmar"] == "Confirmo que voy"

    # La misma persona, con su plaza en Brasil.
    br = db.query(m.Pais).filter_by(codigo="BR").first()
    if br is None:
        pytest.skip("la semilla no trae Brasil")
    plaza = db.query(m.Plaza).filter_by(pais_id=br.id).first()
    if plaza is None:
        pytest.skip("Brasil sin plaza")
    persona = db.get(m.Persona, juan)
    original = persona.plaza_id
    persona.plaza_id = plaza.id
    db.commit()
    try:
        assert push.idioma_de(db, juan) == "pt"
        push.avisar(db, juan, push.tx("pt", "vispera_titulo"),
                    push.tx("pt", "vispera_cuerpo", hora="07:00", mas=""),
                    etiqueta="vispera", accion="confirmar")
        assert salieron[-1]["titulo"] == "Amanhã você trabalha"
        assert salieron[-1]["botones"]["confirmar"] == "Confirmo que vou"
    finally:
        persona.plaza_id = original
        db.commit()


# ================================================== los candados de hora

def test_cerrar_a_mano_ignora_la_hora_de_la_direccion_en_produccion(
        cliente, sesion, datos, monkeypatch):
    """Con el permiso de corregir se podia cerrar hoy un dia de la semana
    que entra mandando `ahora` en la direccion."""
    from app import config

    servicio, j = _dia(cliente, sesion, datos, offset=3)
    fin = datetime.fromisoformat(j["fin_programado"])
    monkeypatch.setattr(config, "es_desarrollo", lambda *_a, **_k: False)
    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     headers=sesion("central"),
                     params={"ahora": (fin + timedelta(hours=1)).isoformat()},
                     json={"justificacion": "Se cerro con la hora equivocada"})
    assert r.status_code == 409, r.text
    assert _estado(j["id"])["jornada"] != "terminada"


# ================================================== pedir sesion no es pedir permiso

def test_la_bitacora_del_dia_y_las_revisiones_piden_su_actividad(
        cliente, sesion, datos):
    servicio, j = _dia(cliente, sesion, datos, offset=907)
    for quien, esperado in (("consultor", 200), ("central", 200),
                            ("rrhh", 403), ("finanzas", 403)):
        r = cliente.get(f"/operacion/jornadas/{j['id']}/bitacora",
                        headers=sesion(quien))
        assert r.status_code == esperado, (quien, r.text)
    for quien, esperado in (("consultor", 200), ("rrhh", 403)):
        r = cliente.get(f"/servicios/{servicio['id']}/revisiones",
                        headers=sesion(quien))
        assert r.status_code == esperado, (quien, r.text)
    equipo_id = servicio["equipos"][0]["id"]
    # Sin task sheet publicado la oficina recibe 404: la puerta se
    # cierra antes, con 403, a quien no tiene la actividad.
    for quien, esperado in (("consultor", 404), ("finanzas", 404), ("rrhh", 403)):
        r = cliente.get(f"/task-sheets/equipo/{equipo_id}", headers=sesion(quien))
        assert r.status_code == esperado, (quien, r.text)
    for quien, esperado in (("consultor", 200), ("finanzas", 200), ("rrhh", 403)):
        r = cliente.get(f"/operacion/jornadas/{j['id']}/agenda/paradas",
                        headers=sesion(quien))
        assert r.status_code == esperado, (quien, r.text)
    # El personal sigue viendo lo suyo.
    r = cliente.get(f"/operacion/jornadas/{j['id']}/bitacora", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    r = cliente.get(f"/operacion/jornadas/{j['id']}/bitacora", headers=sesion("luis"))
    assert r.status_code == 403, r.text


# ================================================== lo que entra por la ruta

def test_la_geocerca_tiene_tope_y_deja_rastro(cliente, sesion, datos):
    from app import models as m
    from app.db import SessionLocal

    servicio, j = _dia(cliente, sesion, datos, offset=908)
    h = sesion("consultor")
    for metros in (50000, -1, 0, 10):
        r = cliente.patch(f"/operacion/jornadas/{j['id']}/origen", headers=h,
                          json={"geocerca_metros": metros})
        assert r.status_code == 422, (metros, r.text)
    r = cliente.patch(f"/operacion/jornadas/{j['id']}/origen", headers=h,
                      json={"geocerca_metros": 1500})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        rastro = (db.query(m.RegistroAccion)
                  .filter_by(servicio_id=servicio["id"], accion="mover geocerca")
                  .all())
    assert len(rastro) == 1 and "250 -> 1500" in rastro[0].detalle


def test_una_nota_larga_se_rechaza_en_vez_de_reventar(cliente, sesion, datos):
    servicio, j = _dia(cliente, sesion, datos, offset=0)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    r = cliente.post(f"/operacion/jornadas/{j['id']}/hitos", headers=sesion("juan"),
                     json={"tipo": "llegada_origen", **DENTRO,
                           "nota": "x" * 400})
    assert r.status_code == 422, r.text


def test_la_app_y_la_central_usan_la_anticipacion_del_pais(
        cliente, sesion, datos):
    """Si el pais cambia sus minutos en Catalogos, el task sheet, la app
    y la central dicen la misma hora."""
    from app import models as m
    from app.db import SessionLocal

    servicio, j = _dia(cliente, sesion, datos, offset=909)
    inicio = datetime.fromisoformat(j["inicio_programado"])
    with SessionLocal() as db:
        pais = db.get(m.Pais, datos["mx"]["id"])
        antes = pais.anticipacion_min
        pais.anticipacion_min = 45
        db.commit()
    try:
        ficha = cliente.get(f"/campo/jornadas/{j['id']}", headers=sesion("juan")).json()
        assert ficha["anticipacion_minutos"] == 45
        assert datetime.fromisoformat(ficha["llegar_a_las"]) == inicio - timedelta(minutes=45)
    finally:
        with SessionLocal() as db:
            db.get(m.Pais, datos["mx"]["id"]).anticipacion_min = antes
            db.commit()


def test_salir_de_la_app_da_de_baja_el_telefono(cliente, sesion, datos, db):
    """Es lo que la app llama al salir: el telefono que cambia de manos
    deja de recibir los avisos del anterior, y al entrar el siguiente
    se vuelve a colgar de el."""
    from app import models as m

    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    cuerpo = {"endpoint": "https://push.example/telefono-compartido",
              "p256dh": "clave", "auth": "secreto", "agente": "prueba"}
    r = cliente.post("/campo/push/suscribir", json=cuerpo, headers=sesion("juan"))
    assert r.status_code == 200, r.text
    r = cliente.delete("/campo/push/suscribir?endpoint="
                       "https://push.example/telefono-compartido",
                       headers=sesion("juan"))
    assert r.status_code == 204, r.text
    fila = db.query(m.SuscripcionPush).filter_by(endpoint=cuerpo["endpoint"]).one()
    assert fila.activa is False and fila.persona_id == juan

    r = cliente.post("/campo/push/suscribir", json=cuerpo, headers=sesion("luis"))
    assert r.status_code == 200, r.text
    db.expire_all()
    fila = db.query(m.SuscripcionPush).filter_by(endpoint=cuerpo["endpoint"]).one()
    assert fila.activa is True and fila.persona_id == luis

# -*- coding: utf-8 -*-
"""Seccion 105, grupo g1: el implantado.

Ola 5, lo que Salvador decidio el 29 de septiembre sobre el implantado:
la pantalla para cambiar la plantilla del mes (su implantado de prueba
con un solo conductor al que no se le podia agregar un vehiculo), la
jornada de doce horas con descansos por pais (decision 6: Brasil ya no
genera dos horas extra cada dia) y los cambios del acuerdo que aplican
desde el mes siguiente (decision 14).

Los meses son fijos --2030, que ninguna otra prueba usa-- salvo donde la
regla habla del mes en curso; ahi el "hoy" del pais del servicio se le
dice al motor.
"""
import calendar
from datetime import date, datetime, timedelta

import pytest
from test_revision_101_implantado import (_abrir_siguiente, _alta,
                                          _calendario, _dia_de_la_semana,
                                          _panel)

from app import models as m

MARZO, ABRIL = date(2030, 3, 1), (2030, 4)


def _habiles(anio, mes):
    return [date(anio, mes, d) for d in range(1, calendar.monthrange(anio, mes)[1] + 1)
            if date(anio, mes, d).weekday() < 5]


def _fines(anio, mes):
    return [date(anio, mes, d) for d in range(1, calendar.monthrange(anio, mes)[1] + 1)
            if date(anio, mes, d).weekday() >= 5]


def _plantilla(cliente, h, sid, anio, mes):
    r = cliente.get(f"/implantados/{sid}/mes/{anio}/{mes}/plantilla", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _guardar_plantilla(cliente, h, sid, anio, mes, personal, unidades,
                       tambien=True):
    return cliente.put(f"/implantados/{sid}/mes/{anio}/{mes}/plantilla",
                       headers=h, json={"personal": personal, "unidades": unidades,
                                        "tambien_meses_siguientes": tambien})


def _terminos(cliente, h, contrato_id):
    r = cliente.get(f"/implantados/contratos/{contrato_id}/terminos", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _guardar_terminos(cliente, h, contrato_id, **cambios):
    cuerpo = {"esquema": "por_dia", "precio_dia_personal": "2900",
              "precio_dia_adicional": "3500", "precio_mes_vehiculo": "66000",
              "viaticos_incluidos": True, "gastos_mes": None,
              "precio_hora_extra": None, **cambios}
    return cliente.put(f"/implantados/contratos/{contrato_id}/terminos",
                       headers=h, json=cuerpo)


def _contrato(contrato_id):
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = db.get(m.ContratoImplantado, contrato_id)
        return {"modalidad": c.modalidad.codigo.value, "dias_servicio": c.dias_servicio.value,
                "hora": c.hora_presentacion, "horas_jornada": c.horas_jornada,
                "horas_descanso": c.horas_descanso, "dias_base": c.dias_base}


def _hoy_en(monkeypatch, dia):
    """El hoy del pais del servicio, para hablar del mes en curso."""
    from app import implantado as motor
    monkeypatch.setattr(motor, "hoy_del_servicio", lambda db, servicio: dia)


@pytest.fixture
def brasil(cliente, sesion):
    """Brasil con su ciudad y un conductor de alla."""
    h = sesion("admin")
    br = next(p for p in cliente.get("/catalogos/paises", headers=h).json()
              if p["codigo"] == "BR")
    plazas = cliente.get("/catalogos/plazas?todas=true", headers=h).json()
    sp = next((p for p in plazas if p["pais_id"] == br["id"]), None)
    if not sp:
        sp = cliente.post("/catalogos/plazas", headers=h,
                          json={"pais_id": br["id"], "nombre": "Sao Paulo"}).json()
    gente = cliente.get("/catalogos/personal", headers=h).json()
    joao = next((p for p in gente if p["correo"] == "joao.silva@centauro.lat"), None)
    if not joao:
        joao = cliente.post("/catalogos/personal", headers=h, json={
            "nombre": "Joao Silva", "correo": "joao.silva@centauro.lat",
            "plaza_id": sp["id"]}).json()
    return {"pais": br, "plaza": sp, "joao": joao}


# ================================ A · cambiar la plantilla del mes (70)

def test_al_implantado_que_no_ha_arrancado_se_le_agrega_la_unidad(
        cliente, sesion, datos):
    """El caso de Salvador: un implantado con un solo conductor y sin
    unidad, con el primer mes generado y sin arrancar. Se le agrega la
    unidad desde la plantilla del mes: todos los dias quedan con ella y
    el conductor sigue."""
    juan = datos["personal"]["Juan Ramirez"]["id"]
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    alta, h = _alta(cliente, sesion, datos, inicio=MARZO,
                    personal=[{"persona_id": juan, "rol_id": conductor}],
                    unidades=[])
    sid = alta["servicio_id"]
    antes = _plantilla(cliente, h, sid, 2030, 3)
    assert antes["unidades"] == [] and antes["editable"] is True
    assert all(d["unidades"] == [] for d in _panel(cliente, h, sid, 2030, 3)["dias"])

    unidad = datos["suburban"]["id"]
    r = _guardar_plantilla(cliente, h, sid, 2030, 3,
                           [{"persona_id": juan, "rol_id": conductor,
                             "vehiculo_id": unidad}], [unidad])
    assert r.status_code == 200, r.text
    hecho = r.json()
    assert hecho["dias_rehechos"] == len(_habiles(2030, 3))
    assert hecho["meses_siguientes"] == [] and hecho["dias_rehechos_siguientes"] == 0

    panel = _panel(cliente, h, sid, 2030, 3)
    assert all([u["placa"] for u in d["unidades"]] == [datos["suburban"]["placa"]]
               for d in panel["dias"]), [(d["fecha"], d["unidades"]) for d in panel["dias"]]
    assert all([p["nombre"] for p in d["personal"]] == ["Juan Ramirez"]
               for d in panel["dias"])
    despues = _plantilla(cliente, h, sid, 2030, 3)
    assert [u["vehiculo_id"] for u in despues["unidades"]] == [unidad]
    assert despues["unidades"][0]["categoria_id"] == datos["suburban"]["categoria_id"]
    assert despues["personal"][0]["vehiculo_id"] == unidad


def test_la_plantilla_nueva_llega_a_los_meses_siguientes_ya_abiertos(
        cliente, sesion, datos):
    """Luis sale del equipo en marzo con abril ya abierto: con la casilla
    puesta, abril tambien se rehace y la respuesta dice cuantos dias.
    Sin la casilla, abril se queda como estaba."""
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    agente = datos["perfiles"]["agente_seguridad"]["id"]
    unidad = datos["suburban"]["id"]
    alta, h = _alta(cliente, sesion, datos, inicio=MARZO)
    sid = alta["servicio_id"]
    _abrir_siguiente(sid, date(2030, 3, 25))
    assert all(len(d["personal"]) == 2 for d in _panel(cliente, h, sid, *ABRIL)["dias"])

    solo_juan = [{"persona_id": juan, "rol_id": conductor, "vehiculo_id": unidad}]
    r = _guardar_plantilla(cliente, h, sid, 2030, 3, solo_juan, [unidad])
    assert r.status_code == 200, r.text
    hecho = r.json()
    assert [(x["periodo"], x["dias_rehechos"]) for x in hecho["meses_siguientes"]] == [
        ("04/2030", len(_habiles(2030, 4)))]
    assert hecho["dias_rehechos_siguientes"] == len(_habiles(2030, 4))
    abril = _panel(cliente, h, sid, *ABRIL)
    assert all([p["nombre"] for p in d["personal"]] == ["Juan Ramirez"]
               for d in abril["dias"]), [(d["fecha"], d["personal"]) for d in abril["dias"]]
    assert [p["persona_id"] for p in _plantilla(cliente, h, sid, *ABRIL)["personal"]] == [juan]

    # Luis vuelve solo a marzo: abril no se toca.
    con_luis = solo_juan + [{"persona_id": luis, "rol_id": agente}]
    r = _guardar_plantilla(cliente, h, sid, 2030, 3, con_luis, [unidad], tambien=False)
    assert r.status_code == 200, r.text
    assert r.json()["meses_siguientes"] == []
    assert all(len(d["personal"]) == 2 for d in _panel(cliente, h, sid, 2030, 3)["dias"])
    assert all(len(d["personal"]) == 1 for d in _panel(cliente, h, sid, *ABRIL)["dias"])


def test_la_plantilla_del_implantado_cancelado_ya_no_se_cambia(cliente, sesion,
                                                                 datos):
    """El cancelado se consulta y se cierra; su plantilla no se arma."""
    juan = datos["personal"]["Juan Ramirez"]["id"]
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    alta, h = _alta(cliente, sesion, datos, inicio=MARZO)
    sid = alta["servicio_id"]
    r = cliente.post(f"/servicios/{sid}/cancelar", headers=h,
                     json={"motivo": "No arranco"})
    assert r.status_code == 200, r.text
    r = _guardar_plantilla(cliente, h, sid, 2030, 3,
                           [{"persona_id": juan, "rol_id": conductor}], [])
    assert r.status_code == 409, r.text
    assert "cancelado" in r.json()["detail"]["mensaje"]


# ============================= B · decision 6: doce horas con descansos

def test_el_implantado_de_brasil_es_de_doce_horas_y_no_genera_horas_extra(
        cliente, sesion, datos, brasil):
    """Un implantado en Sao Paulo tomaba el full day de Brasil (10 h): el
    dia que cerraba a las doce horas exactas contaba dos horas extra. Ahora
    abre con la modalidad `implantado` del pais, de doce, y cerrar a las
    doce da cero."""
    from app.db import SessionLocal
    from app import horas_extra
    from app import implantado as motor

    h = sesion("consultor")
    r = cliente.post("/implantados", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": brasil["pais"]["id"],
        "plaza_id": brasil["plaza"]["id"],
        "solicitante_nombre": "Marina", "solicitante_apellidos": "Costa",
        "ejecutivo_nombre": "Pedro", "ejecutivo_apellidos": "Alves",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "fecha_inicio": "2030-03-01", "dias_servicio": "lunes_viernes",
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "personal": [{"persona_id": brasil["joao"]["id"],
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"]}],
        "unidades": [], "precio_dia_personal": "900", "precio_hora_extra": "80",
        "acuerdo": {"turno": "natural", "origen_direccion": "Av. Paulista 1000",
                    "origen_lat": "-23.5614", "origen_lon": "-46.6560",
                    "fecha_inicio": "2030-03-01", "dias_servicio": "lunes_viernes"},
    })
    assert r.status_code == 201, r.text
    sid, contrato = r.json()["servicio_id"], r.json()["contrato_id"]
    assert _contrato(contrato)["modalidad"] == "implantado"
    with SessionLocal() as db:
        assert motor.horas_de(db.get(m.ContratoImplantado, contrato), db) == (12, 0, 1)

    panel = _panel(cliente, h, sid, 2030, 3)
    primero = panel["dias"][0]
    with SessionLocal() as db:
        j = db.get(m.Jornada, primero["jornada_id"])
        assert j.fin_programado - j.inicio_programado == timedelta(hours=12)
        assert j.modalidad.codigo == m.CodigoModalidad.IMPLANTADO
        inicio = j.inicio_programado
    # La central lo cierra a las doce horas exactas.
    r = cliente.post(f"/operacion/jornadas/{primero['jornada_id']}/cerrar-a-mano",
                     headers=sesion("central"),
                     json={"justificacion": "Cerro a su hora, confirmado con el cliente",
                           "fin_real": (inicio + timedelta(hours=12)).isoformat()},
                     params={"ahora": (inicio + timedelta(hours=14)).isoformat()})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert horas_extra.horas(db.get(m.Jornada, primero["jornada_id"])) == 0
    rev = cliente.get(f"/implantados/contratos/{contrato}/cierre/revision", headers=h)
    assert rev.status_code == 200, rev.text
    assert rev.json()["comparativo"]["trabajado"]["horas_extra"] == 0


def test_las_horas_del_acuerdo_se_corrigen_por_contrato_y_pasan_al_mes_siguiente(
        cliente, sesion, datos):
    """Vacias, las horas son las del pais. El consultor las corrige desde
    los terminos del mes --con tope de 24 y el descanso dentro de la
    jornada-- y lo corregido viaja al mes que se abre."""
    alta, h = _alta(cliente, sesion, datos, inicio=MARZO)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    x = _terminos(cliente, h, contrato)
    assert (float(x["horas_jornada"]), float(x["horas_descanso"])) == (12, 0)
    assert x["horas_del_contrato"] is False and x["descanso_editable"] is True
    assert float(x["horas_del_pais"]["jornada"]) == 12

    assert _guardar_terminos(cliente, h, contrato, horas_jornada="30").status_code == 422
    assert _guardar_terminos(cliente, h, contrato, horas_jornada="10",
                             horas_descanso="10").status_code == 422
    r = _guardar_terminos(cliente, h, contrato, horas_jornada="10", horas_descanso="2")
    assert r.status_code == 200, r.text
    x = r.json()
    assert (float(x["horas_jornada"]), float(x["horas_descanso"])) == (10, 2)
    assert x["horas_del_contrato"] is True

    abierto = _abrir_siguiente(sid, date(2030, 3, 25))
    assert _contrato(abierto["contrato_id"])["horas_jornada"] == 10
    from app.db import SessionLocal
    with SessionLocal() as db:
        for d in _panel(cliente, h, sid, *ABRIL)["dias"]:
            j = db.get(m.Jornada, d["jornada_id"])
            assert j.fin_programado - j.inicio_programado == timedelta(hours=10)


def test_el_12x36_no_lleva_descanso_aunque_se_lo_manden(cliente, sesion, datos):
    """Dos personas que se alternan, sin descansos pactados con el
    cliente: el motor deja el descanso en cero."""
    alta, h = _alta(cliente, sesion, datos, inicio=MARZO, dias="todos",
                    turno="12x36")
    contrato = alta["contrato_id"]
    r = _guardar_terminos(cliente, h, contrato, horas_descanso="4")
    assert r.status_code == 200, r.text
    assert float(r.json()["horas_descanso"]) == 0
    assert r.json()["descanso_editable"] is False


def test_catalogos_lleva_la_jornada_del_implantado_y_la_app_la_ensena(
        cliente, sesion, datos):
    """La modalidad `implantado` esta en Catalogos para cada pais con su
    intervalo de descanso, con bitacora al cambiarla. Con descanso el dia
    del equipo en la app lo dice; con cero, no dice nada."""
    admin = sesion("admin")
    mods = cliente.get("/catalogos/modalidades", headers=admin).json()
    por_pais = {x["pais_id"]: x for x in mods if x["codigo"] == "implantado"}
    paises = cliente.get("/catalogos/paises", headers=admin).json()
    assert {p["id"] for p in paises} <= set(por_pais)
    mx = por_pais[datos["mx"]["id"]]
    assert (float(mx["horas"]), float(mx["horas_descanso"]),
            float(mx["intervalo_descanso"])) == (12, 0, 1)
    assert mx["aplica_horas_extra"] is True and mx["bloquea_dia_completo"] is True

    hoy = date(2030, 3, 4)                       # lunes
    alta, h = _alta(cliente, sesion, datos, inicio=MARZO)
    ahora = datetime.combine(hoy, datetime.min.time()).replace(hour=7).isoformat()

    def mi_dia():
        r = cliente.get(f"/campo/mi-dia?ahora={ahora}", headers=sesion("juan"))
        assert r.status_code == 200, r.text
        return next(f for f in r.json()["hoy"] if f["servicio_id"] == alta["servicio_id"])

    assert mi_dia()["descanso"] is None
    campos = {k: mx[k] for k in ("pais_id", "codigo", "horas", "horas_descanso",
                                 "intervalo_descanso", "aplica_horas_extra",
                                 "bloquea_dia_completo", "km_estimados")}
    try:
        r = cliente.patch(f"/catalogos/modalidades/{mx['id']}", headers=admin,
                          json={**campos, "horas_descanso": "4", "intervalo_descanso": "1"})
        assert r.status_code == 200, r.text
        assert mi_dia()["descanso"] == {"jornada": 12.0, "horas": 4.0, "intervalo": 1.0}
        historial = cliente.get(f"/catalogos/modalidades/{mx['id']}/historial",
                                headers=admin).json()
        assert historial[0]["accion"] == "catalogo cambiado"
        assert "horas_descanso" in historial[0]["despues"]
    finally:
        r = cliente.patch(f"/catalogos/modalidades/{mx['id']}", headers=admin, json=campos)
        assert r.status_code == 200, r.text


# ================= C · decision 14: el acuerdo aplica desde el mes siguiente

def test_cambiar_los_dias_de_servicio_llega_al_mes_siguiente_y_no_al_que_corre(
        cliente, sesion, datos, monkeypatch):
    """A medio marzo el cliente pide tambien los fines de semana, con
    abril ya abierto: abril gana sus sabados y domingos (por cubrir, como
    nace todo fin de semana) y marzo no cambia. El mes que se abra
    despues nace con el trato nuevo."""
    alta, h = _alta(cliente, sesion, datos, inicio=MARZO)
    sid = alta["servicio_id"]
    _abrir_siguiente(sid, date(2030, 3, 25))
    _hoy_en(monkeypatch, date(2030, 3, 15))

    antes = cliente.get(f"/implantados/{sid}/acuerdo", headers=h).json()
    r = cliente.put(f"/implantados/{sid}/acuerdo", headers=h, json={
        "fecha_inicio": antes["fecha_inicio"], "dias_servicio": "todos",
        "turno": "natural", "origen_direccion": antes["origen_direccion"],
        "origen_lat": antes["origen_lat"], "origen_lon": antes["origen_lon"],
        "geocerca_metros": antes["geocerca_metros"]})
    assert r.status_code == 200, r.text
    hecho = r.json()["acuerdo_aplicado"]
    assert hecho["desde"] == "04/2030"
    assert hecho["mes_en_curso"].startswith("03/2030")
    assert [x["periodo"] for x in hecho["meses"]] == ["04/2030"]
    abril = hecho["meses"][0]
    assert abril["campos"]["dias_servicio"] == ["lunes_viernes", "todos"]
    assert abril["creados"] == [d.isoformat() for d in _fines(2030, 4)]
    assert abril["quitados"] == [] and abril["no_tocados"] == []

    cal = _calendario(cliente, h, sid, *ABRIL)
    assert cal["dias_servicio"] == "todos"
    assert all(d["estado"] == "por_cubrir" for d in cal["dias"] if d["fin_de_semana"])
    assert len(_panel(cliente, h, sid, *ABRIL)["dias"]) == 30
    assert _contrato(_plantilla(cliente, h, sid, *ABRIL)["contrato_id"])["dias_base"] == 30

    marzo = _calendario(cliente, h, sid, 2030, 3)
    assert marzo["dias_servicio"] == "lunes_viernes"
    assert all(d["estado"] == "sin_servicio" for d in marzo["dias"] if d["fin_de_semana"])

    mayo = _abrir_siguiente(sid, date(2030, 4, 25))
    assert _contrato(mayo["contrato_id"])["dias_servicio"] == "todos"
    assert len(_panel(cliente, h, sid, 2030, 5)["dias"]) == 31


def test_cambiar_la_hora_del_trato_mueve_el_mes_siguiente_y_no_el_que_corre(
        cliente, sesion, datos, monkeypatch):
    """El cliente mueve el encuentro a las 7:30 con abril ya abierto: los
    dias de abril traen la hora nueva; los de marzo, la vieja. El trato
    dice la hora acordada y la del mes que corre."""
    alta, h = _alta(cliente, sesion, datos, inicio=MARZO)
    sid = alta["servicio_id"]
    _abrir_siguiente(sid, date(2030, 3, 25))
    _hoy_en(monkeypatch, date(2030, 3, 15))

    r = cliente.put(f"/implantados/{sid}/hora-presentacion", headers=h,
                    json={"hora": "07:30:00"})
    assert r.status_code == 200, r.text
    hecho = r.json()
    assert hecho["dias_movidos"] == [d.isoformat() for d in _habiles(2030, 4)]
    assert hecho["dias_trabados"] == []
    assert hecho["acuerdo_aplicado"]["mes_en_curso"].startswith("03/2030")

    assert all(d["presentacion"] == "07:30" for d in _panel(cliente, h, sid, *ABRIL)["dias"])
    assert all(d["presentacion"] == "08:00" for d in _panel(cliente, h, sid, 2030, 3)["dias"])
    trato = cliente.get(f"/implantados/{sid}/acuerdo", headers=h).json()
    assert (trato["hora_presentacion"], trato["hora_del_mes"]) == ("07:30:00", "08:00:00")

    mayo = _abrir_siguiente(sid, date(2030, 4, 25))
    assert _contrato(mayo["contrato_id"])["hora"] == "07:30:00"


def test_si_el_servicio_no_ha_arrancado_el_cambio_aplica_desde_el_primer_mes(
        cliente, sesion, datos):
    """No hay nada operado: el primer mes se rehace con la hora nueva y
    no hay mes en curso que corregir a mano."""
    alta, h = _alta(cliente, sesion, datos, inicio=MARZO)
    sid = alta["servicio_id"]
    r = cliente.put(f"/implantados/{sid}/hora-presentacion", headers=h,
                    json={"hora": "07:30:00"})
    assert r.status_code == 200, r.text
    hecho = r.json()["acuerdo_aplicado"]
    assert hecho["desde"] == "03/2030" and hecho["mes_en_curso"] is None
    assert hecho["meses"][0]["movidos"] == [d.isoformat() for d in _habiles(2030, 3)]
    assert all(d["presentacion"] == "07:30" for d in _panel(cliente, h, sid, 2030, 3)["dias"])


def test_el_dia_del_mes_siguiente_con_relevo_a_mano_se_conserva(cliente, sesion,
                                                                 datos, monkeypatch):
    """Carlos cubre un martes de abril desde la ficha. Al mover la hora
    del trato ese martes se queda como esta --con Carlos y con su hora--
    y la respuesta lo cuenta como no tocado."""
    alta, h = _alta(cliente, sesion, datos, inicio=MARZO)
    sid = alta["servicio_id"]
    _abrir_siguiente(sid, date(2030, 3, 25))
    martes = _dia_de_la_semana(2030, 4, 1)
    carlos = datos["personal"]["Carlos Vega"]["id"]
    r = cliente.post(f"/implantados/{sid}/dia/{martes}/cubrir", headers=h,
                     json={"personal": [{"persona_id": carlos,
                                         "vehiculo_id": datos["suburban"]["id"]}]})
    assert r.status_code == 200, r.text
    _hoy_en(monkeypatch, date(2030, 3, 15))

    r = cliente.put(f"/implantados/{sid}/hora-presentacion", headers=h,
                    json={"hora": "07:30:00"})
    assert r.status_code == 200, r.text
    abril = r.json()["acuerdo_aplicado"]["meses"][0]
    assert abril["no_tocados"] == [martes.isoformat()]
    assert martes.isoformat() not in abril["movidos"]
    ese = next(d for d in _panel(cliente, h, sid, *ABRIL)["dias"]
               if d["fecha"] == martes.isoformat())
    assert ese["presentacion"] == "08:00"
    assert [p["nombre"] for p in ese["personal"]] == ["Carlos Vega"]
    otros = [d for d in _panel(cliente, h, sid, *ABRIL)["dias"]
             if d["fecha"] != martes.isoformat()]
    assert all(d["presentacion"] == "07:30" for d in otros)


def test_los_terminos_del_mes_pasan_a_los_meses_futuros_abiertos(cliente, sesion,
                                                                  datos, monkeypatch):
    """El precio corregido en marzo con abril ya abierto llega a abril:
    los terminos son el acuerdo, y el mes que sigue no nace con los de
    antes. Marzo es el mes que se edito, asi que no hay nada que
    corregir a mano."""
    alta, h = _alta(cliente, sesion, datos, inicio=MARZO)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    abril_id = _abrir_siguiente(sid, date(2030, 3, 25))["contrato_id"]
    _hoy_en(monkeypatch, date(2030, 3, 15))

    r = _guardar_terminos(cliente, h, contrato, precio_dia_personal="3100",
                          precio_hora_extra="350")
    assert r.status_code == 200, r.text
    hecho = r.json()["acuerdo_aplicado"]
    assert hecho["mes_en_curso"] is None
    assert [x["periodo"] for x in hecho["meses"]] == ["04/2030"]
    campos = hecho["meses"][0]["campos"]
    assert set(campos) == {"precio_dia_personal", "precio_hora_extra"}
    abril = _terminos(cliente, h, abril_id)
    assert float(abril["precio_dia_personal"]) == 3100
    assert float(abril["precio_hora_extra"]) == 350

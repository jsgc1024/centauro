# -*- coding: utf-8 -*-
"""Seccion 101, grupo g4: el implantado.

Cuarta tanda de la revision del 28 de septiembre, lo del servicio
implantado: el trato que perdia el turno, el dia con rastro, el rol del
relevo, la ficha del 12x36, el mes que el reloj no abria, el mes del
cancelado, el dia cancelado que se cubria, la plantilla que aceptaba a
cualquiera y no se revalidaba, la plantilla que pisaba el fin de semana,
la unidad que no salia del taller, y los detalles.

Los meses son fijos --2030, que ninguna otra prueba usa-- salvo donde la
regla habla del mes en curso; ahi el "hoy" se le dice al servidor.
"""
import calendar
from datetime import date, timedelta

from app import models as m


def _alta(cliente, sesion, datos, inicio=None, dias="lunes_viernes",
          turno="natural", personal=None, unidades=None, **extra):
    """Un implantado en la capital: Juan conduce la Suburban y Luis va de
    agente; en 12x36 los dos son conductores y se alternan."""
    h = sesion("consultor")
    inicio = inicio or date.today().replace(day=1)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    unidad = datos["suburban"]["id"]
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    agente = datos["perfiles"]["agente_seguridad"]["id"]
    if personal is None:
        if turno == "12x36":
            personal = [{"persona_id": juan, "rol_id": conductor,
                         "vehiculo_id": unidad, "empieza": True},
                        {"persona_id": luis, "rol_id": conductor,
                         "vehiculo_id": unidad, "empieza": False}]
        else:
            personal = [{"persona_id": juan, "rol_id": conductor,
                         "vehiculo_id": unidad},
                        {"persona_id": luis, "rol_id": agente,
                         "vehiculo_id": None}]
    r = cliente.post("/implantados", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "fecha_inicio": str(inicio), "dias_servicio": dias,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "personal": personal,
        "unidades": [unidad] if unidades is None else unidades,
        "precio_dia_personal": "2900", "precio_mes_vehiculo": "66000",
        "precio_dia_adicional": "3500",
        "acuerdo": {"turno": turno, "origen_direccion": "Torre Mayor",
                    "origen_lat": "19.4270", "origen_lon": "-99.1677",
                    "geocerca_metros": 250, "fecha_inicio": str(inicio),
                    "dias_servicio": dias},
        **extra,
    }, headers=h)
    assert r.status_code == 201, r.text
    return r.json(), h


def _siguiente(hoy):
    return (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)


def _abrir_siguiente(sid, hoy):
    """El mes que sigue de un mes fijo: por el motor, con su hoy, porque
    el boton de la consola solo abre un mes por delante del de hoy."""
    from app import implantado as motor
    from app.db import SessionLocal
    with SessionLocal() as db:
        return motor.abrir_siguiente(db, db.get(m.Servicio, sid), hoy=hoy)


def _panel(cliente, h, sid, anio, mes):
    r = cliente.get(f"/implantados/{sid}/mes/{anio}/{mes}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _ficha_del_dia(cliente, h, sid, fecha):
    r = cliente.get(f"/implantados/{sid}/dia/{fecha}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _calendario(cliente, h, sid, anio, mes):
    r = cliente.get(f"/implantados/{sid}/calendario/{anio}/{mes}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _roles_del_dia(jornada_id):
    """{persona_id: codigo del rol} de quienes van ese dia."""
    from app.db import SessionLocal
    with SessionLocal() as db:
        j = db.get(m.Jornada, jornada_id)
        return {a.persona_id: (a.rol.codigo if a.rol else None)
                for a in j.personal}


def _dia_de_la_semana(anio, mes, weekday, desde=1):
    """La primera fecha del mes con ese dia de la semana (lunes es 0)."""
    ultimo = calendar.monthrange(anio, mes)[1]
    return next(date(anio, mes, d) for d in range(desde, ultimo + 1)
                if date(anio, mes, d).weekday() == weekday)


def _persona(persona_id, **cambios):
    """Cambia a una persona del catalogo y devuelve como estaba, para
    dejarla igual al terminar: el catalogo no se vacia entre pruebas."""
    from app.db import SessionLocal
    with SessionLocal() as db:
        p = db.get(m.Persona, persona_id)
        antes = {k: getattr(p, k) for k in cambios}
        for k, v in cambios.items():
            setattr(p, k, v)
        db.commit()
    return antes


# ================================================ 61 · el trato y el turno

def test_editar_el_trato_no_cambia_el_turno(cliente, sesion, datos):
    """El consultor corrige el protocolo de un 12x36 desde la consola
    --el cuerpo de la pantalla no traia el turno-- y el trato se volvia
    natural: el mes que sigue nacia con las dos personas todos los dias
    habiles y los fines de semana sin nadie."""
    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1),
                    dias="todos", turno="12x36")
    sid = alta["servicio_id"]
    antes = cliente.get(f"/implantados/{sid}/acuerdo", headers=h).json()
    assert antes["turno"] == "12x36"

    # Lo que mandaba la consola: el trato sin `turno`.
    r = cliente.put(f"/implantados/{sid}/acuerdo", headers=h, json={
        "cubre": "Traslados del ejecutivo", "no_cubre": None,
        "zona_operacion": "Valle de Mexico", "dias_semana": "Todos los dias",
        "fecha_inicio": antes["fecha_inicio"], "dias_servicio": "todos",
        "origen_direccion": antes["origen_direccion"],
        "origen_lat": antes["origen_lat"], "origen_lon": antes["origen_lon"],
        "geocerca_metros": antes["geocerca_metros"],
        "protocolo_contacto": "Llamar al coordinador",
    })
    assert r.status_code == 200, r.text
    despues = cliente.get(f"/implantados/{sid}/acuerdo", headers=h).json()
    assert despues["turno"] == "12x36", despues["turno"]
    assert despues["protocolo_contacto"] == "Llamar al coordinador"

    # Y el mes que sigue alterna: una persona por dia, los siete dias.
    _abrir_siguiente(sid, date(2030, 3, 25))
    panel = _panel(cliente, h, sid, 2030, 4)
    assert all(len(d["personal"]) == 1 for d in panel["dias"]), [
        (d["fecha"], len(d["personal"])) for d in panel["dias"]]
    assert len(panel["dias"]) == 30


def test_el_turno_no_se_cambia_con_un_mes_generado(cliente, sesion, datos):
    """Del turno salen los dias del mes y quien va en cada uno: con un
    mes ya en la calle, pasar de 12x36 a natural (o al reves) se rechaza
    y se dice que hacer."""
    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1),
                    dias="todos", turno="12x36")
    sid = alta["servicio_id"]
    antes = cliente.get(f"/implantados/{sid}/acuerdo", headers=h).json()
    r = cliente.put(f"/implantados/{sid}/acuerdo", headers=h, json={
        "fecha_inicio": antes["fecha_inicio"], "dias_servicio": "todos",
        "turno": "natural"})
    assert r.status_code == 409, r.text
    assert "que_hacer" in r.json()["detail"]
    assert cliente.get(f"/implantados/{sid}/acuerdo",
                       headers=h).json()["turno"] == "12x36"


# ============================================ 63 · cerrar un dia con rastro

def test_cerrar_un_dia_con_rastro_no_revienta(cliente, sesion, datos):
    """Tres dias con algo que apunta a ellos --gente puesta desde la
    pantalla del servicio, una alerta de baja de Odoo y un viatico con
    su solicitud cancelada colgando-- se cierran sin el 409 de la base.
    El que tiene rastro de verdad se cancela; el que no, se borra."""
    from ayudas import asignar
    from app.db import SessionLocal

    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid = alta["servicio_id"]
    panel = _panel(cliente, h, sid, 2030, 3)
    con_gente, con_alerta, con_viatico = panel["dias"][2:5]
    carlos = datos["personal"]["Carlos Vega"]["id"]

    # Alguien asignado desde la pantalla del servicio: la bitacora del
    # alta apunta a la jornada.
    for r in asignar(cliente, h, con_gente["jornada_id"], persona_id=carlos):
        assert r.status_code == 200, r.text
    # La alerta de la baja de Odoo.
    with SessionLocal() as db:
        db.add(m.Alerta(jornada_id=con_alerta["jornada_id"],
                        tipo=m.TipoAlerta.PERSONAL_DE_BAJA,
                        persona_id=datos["personal"]["Juan Ramirez"]["id"],
                        mensaje="Juan Ramirez fue dado de baja en Odoo"))
        db.commit()
    # Un viatico asignado cuya solicitud ya se cancelo.
    equipo_id = _calendario(cliente, h, sid, 2030, 3)["equipo_id"]
    v = cliente.post("/viaticos/asignar", headers=h, json={
        "jornada_id": con_viatico["jornada_id"],
        "persona_id": datos["personal"]["Juan Ramirez"]["id"],
        "conceptos": [{"concepto": "alimentos", "monto": "900",
                       "origen": "tabulador"}]})
    assert v.status_code in (200, 201), v.text
    assert cliente.post(f"/viaticos/{v.json()['id']}/solicitar-transferencia",
                        headers=h).status_code == 200
    assert cliente.post(f"/viaticos/equipos/{equipo_id}/cancelar-solicitud",
                        json={}, headers=h).status_code == 200

    r = cliente.delete(f"/implantados/{sid}/dia/{con_gente['fecha']}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json().get("cerrado") == con_gente["fecha"]
    r = cliente.delete(f"/implantados/{sid}/dia/{con_alerta['fecha']}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["borrado"] is False
    r = cliente.delete(f"/implantados/{sid}/dia/{con_viatico['fecha']}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json().get("cerrado") == con_viatico["fecha"]


# ============================================== 64 · el rol del relevo

def test_el_relevo_hereda_el_rol_de_la_posicion_que_cubre(cliente, sesion,
                                                          datos):
    """Plantilla capturada "coordinador, conductor". El sabado Carlos
    cubre al conductor; la consola mandaba persona y unidad sin rol y el
    motor le daba el rol de la primera fila: Carlos cobraba y se
    facturaba como coordinador."""
    luis = datos["personal"]["Luis Mendoza"]["id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    carlos = datos["personal"]["Carlos Vega"]["id"]
    coordinador = datos["perfiles"]["coordinador_seguridad"]["id"]
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1),
                    dias="lunes_sabado", personal=[
                        {"persona_id": luis, "rol_id": coordinador,
                         "vehiculo_id": None},
                        {"persona_id": juan, "rol_id": conductor,
                         "vehiculo_id": datos["suburban"]["id"]}])
    sid = alta["servicio_id"]
    sabado = _dia_de_la_semana(2030, 3, 5)
    ficha = _ficha_del_dia(cliente, h, sid, sabado)
    # Una fila por posicion, en su orden, sin rol: Luis sigue en la suya
    # y Carlos entra en la del conductor.
    cuerpo = {"personal": [
        {"persona_id": luis if p["rol_id"] == coordinador else carlos,
         "vehiculo_id": p["vehiculo_id"]} for p in ficha["posiciones"]]}
    r = cliente.post(f"/implantados/{sid}/dia/{sabado}/cubrir", headers=h,
                     json=cuerpo)
    assert r.status_code == 200, r.text
    roles = _roles_del_dia(_ficha_del_dia(cliente, h, sid, sabado)["jornada_id"])
    assert roles[carlos] == "conductor_seguridad", roles
    assert roles[luis] == "coordinador_seguridad", roles

    # Y el dia suelto que se abre con una sola persona: la posicion del
    # titular --quien maneja--, no la primera fila.
    otro_sabado = _dia_de_la_semana(2030, 3, 5, desde=sabado.day + 1)
    r = cliente.post(f"/implantados/{sid}/dias", headers=h,
                     json={"fecha": str(otro_sabado), "persona_id": carlos})
    assert r.status_code == 200, r.text
    assert _roles_del_dia(r.json()["jornada_id"])[carlos] == "conductor_seguridad"


def test_en_12x36_la_ficha_ofrece_una_sola_posicion(cliente, sesion, datos):
    """En 12x36 la ficha del dia listaba las dos posiciones con las dos
    personas preseleccionadas, y "Cubrir dia" dejaba el dia con las dos.
    Ahora ofrece una: la de quien le toca ese dia. Y el servidor rechaza
    dos personas para un dia de la escala."""
    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1),
                    dias="todos", turno="12x36")
    sid = alta["servicio_id"]
    panel = _panel(cliente, h, sid, 2030, 3)
    for dia in panel["dias"][:4]:
        assert len(dia["personal"]) == 1
        ficha = _ficha_del_dia(cliente, h, sid, dia["fecha"])
        assert len(ficha["posiciones"]) == 1, ficha["posiciones"]
        assert ficha["posiciones"][0]["persona_id"] == dia["personal"][0]["persona_id"]

    dia = panel["dias"][5]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    r = cliente.post(f"/implantados/{sid}/dia/{dia['fecha']}/cubrir", headers=h,
                     json={"personal": [{"persona_id": juan}, {"persona_id": luis}],
                           "ambos_dias": False})
    assert r.status_code == 409, r.text
    assert "una sola persona" in r.json()["detail"]["mensaje"]
    ese = next(d for d in _panel(cliente, h, sid, 2030, 3)["dias"]
               if d["fecha"] == dia["fecha"])
    assert len(ese["personal"]) == 1


# ==================================== 66 · la manana que abre el mes que falta

def test_la_manana_del_dia_uno_abre_el_mes_que_falta(cliente, sesion, datos):
    """El reloj no corrio la ultima semana. El dia 1 el mes en curso no
    existe y la ventana de siete dias no lo abria hasta el 24: ahora un
    implantado vivo sin el mes de hoy le toca en la primera vuelta."""
    from app import implantado as motor
    from app.db import SessionLocal

    hoy = date.today()
    alta, h = _alta(cliente, sesion, datos, inicio=hoy.replace(day=1))
    anio, mes = _siguiente(hoy)
    with SessionLocal() as db:
        resultado = motor.abrir_los_que_toquen(db, date(anio, mes, 1))
    abiertos = [x for x in resultado["abiertos"]
                if x["servicio_id"] == alta["servicio_id"]]
    assert [x["periodo"] for x in abiertos] == [f"{mes:02d}/{anio}"], resultado
    assert resultado["fallados"] == []


def test_dos_meses_atras_se_abren_en_la_misma_vuelta(cliente, sesion, datos):
    """Tras una caida larga, la primera vuelta deja abierto el mes en
    curso, no un mes por dia."""
    from app import implantado as motor
    from app.db import SessionLocal

    hoy = date.today()
    alta, h = _alta(cliente, sesion, datos, inicio=hoy.replace(day=1))
    anio1, mes1 = _siguiente(hoy)
    anio2, mes2 = _siguiente(date(anio1, mes1, 1))
    with SessionLocal() as db:
        resultado = motor.abrir_los_que_toquen(db, date(anio2, mes2, 1))
    abiertos = [x["periodo"] for x in resultado["abiertos"]
                if x["servicio_id"] == alta["servicio_id"]]
    assert abiertos == [f"{mes1:02d}/{anio1}", f"{mes2:02d}/{anio2}"], resultado
    ficha = cliente.get(f"/implantados/{alta['servicio_id']}/ficha", headers=h).json()
    assert ficha["ultimo_mes"] == f"{mes2:02d}/{anio2}"


# ====================================== 67 · el mes del implantado cancelado

def test_el_mes_del_implantado_cancelado_tiene_donde_cerrarse(cliente, sesion,
                                                              datos):
    """Se cancela con dias trabajados: el mes arranca su cierre y el
    aviso «24 h para el visto bueno» lleva a #/implantado/{id}. La
    cartera lo escondia y la pantalla decia «no existe»: ahora la ficha
    se lee por su numero, y la cartera lo trae mientras un mes suyo
    tenga cierre por terminar."""
    from test_cierre_mes import DIAS, _cerrar_mes, _cierre
    from test_cierre_mes import _alta as _alta_2029

    alta = _alta_2029(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    _cerrar_mes(cliente, sesion, sid, dias=DIAS[:3])
    h = sesion("consultor")
    r = cliente.post(f"/servicios/{sid}/cancelar", headers=h,
                     json={"motivo": "El ejecutivo regreso a su pais"})
    assert r.status_code == 200, r.text
    c = _cierre(contrato)
    assert c is not None and c["motivo"] == "cancelacion"

    ficha = cliente.get(f"/implantados/{sid}/ficha", headers=h)
    assert ficha.status_code == 200, ficha.text
    ficha = ficha.json()
    assert ficha["estatus"] == "cancelado"
    del_mes = next(p for p in ficha["periodos"] if p["contrato_id"] == contrato)
    assert del_mes["fase"] == "comprobacion"
    cartera = cliente.get("/implantados", headers=h).json()
    assert any(x["servicio_id"] == sid for x in cartera), "la cartera lo esconde"

    # Y ya no se arma: ni cubrir un dia ni devolver uno cancelado.
    r = cliente.post(f"/implantados/{sid}/dia/2029-09-27/cubrir", headers=h,
                     json={"personal": [{"persona_id":
                                         datos["personal"]["Juan Ramirez"]["id"]}]})
    assert r.status_code == 409, r.text
    assert "cancelado" in r.json()["detail"]["mensaje"]
    r = cliente.post(f"/implantados/{sid}/dia/2029-09-27/reactivar", headers=h)
    assert r.status_code == 409, r.text


def test_el_cancelado_sale_de_la_cartera_cuando_no_tiene_nada_que_cerrar(
        cliente, sesion, datos):
    """Un implantado cancelado sin un solo dia trabajado no tiene cierre:
    no estorba en la cartera, y su pantalla sigue abriendo por su enlace."""
    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid = alta["servicio_id"]
    r = cliente.post(f"/servicios/{sid}/cancelar", headers=h,
                     json={"motivo": "No arranco"})
    assert r.status_code == 200, r.text
    assert not any(x["servicio_id"] == sid
                   for x in cliente.get("/implantados", headers=h).json())
    ficha = cliente.get(f"/implantados/{sid}/ficha", headers=h)
    assert ficha.status_code == 200 and ficha.json()["estatus"] == "cancelado"


# ============================================= 68 · cubrir un dia cancelado

def test_cubrir_un_dia_cancelado_pide_reactivarlo_primero(cliente, sesion,
                                                          datos):
    """Un dia cancelado se cubria: contestaba 200, la ficha decia
    "cubierto", el calendario "cancelado" y el agente no lo veia. Ahora
    se rechaza con que hacer, la ficha lo dice cancelado y ofrece
    reactivarlo; reactivado, se cubre."""
    from app.db import SessionLocal

    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid = alta["servicio_id"]
    dia = _panel(cliente, h, sid, 2030, 3)["dias"][3]
    with SessionLocal() as db:
        db.get(m.Jornada, dia["jornada_id"]).estatus = m.EstatusJornada.CANCELADA
        db.commit()
    carlos = datos["personal"]["Carlos Vega"]["id"]
    cuerpo = {"personal": [{"persona_id": carlos,
                            "vehiculo_id": datos["suburban"]["id"]}]}

    r = cliente.post(f"/implantados/{sid}/dia/{dia['fecha']}/cubrir",
                     headers=h, json=cuerpo)
    assert r.status_code == 409, r.text
    assert "reactív" in r.json()["detail"]["que_hacer"]
    r = cliente.post(f"/implantados/{sid}/dias", headers=h,
                     json={"fecha": dia["fecha"], "persona_id": carlos})
    assert r.status_code == 409, r.text

    ficha = _ficha_del_dia(cliente, h, sid, dia["fecha"])
    assert ficha["estado"] == "cancelado"
    assert ficha["se_puede_reactivar"] is True
    assert ficha["se_puede_cerrar"] is False

    assert cliente.post(f"/implantados/{sid}/dia/{dia['fecha']}/reactivar",
                        headers=h).status_code == 200
    r = cliente.post(f"/implantados/{sid}/dia/{dia['fecha']}/cubrir",
                     headers=h, json=cuerpo)
    assert r.status_code == 200, r.text
    ficha = _ficha_del_dia(cliente, h, sid, dia["fecha"])
    assert ficha["estado"] == "cubierto"
    assert [c["persona_id"] for c in ficha["cubren"]] == [carlos]
    cal = _calendario(cliente, h, sid, 2030, 3)
    assert next(d for d in cal["dias"]
                if d["fecha"] == dia["fecha"])["estado"] == "cubierto"


# ================================================= 69 · la plantilla

def test_la_plantilla_no_acepta_oficina_ni_otra_ciudad(cliente, sesion, datos):
    """Por la API entraba un monitorista de oficina o una unidad de
    Guadalajara en un implantado de la capital. La consola ya lo
    filtraba; ahora el servidor tambien."""
    juan = datos["personal"]["Juan Ramirez"]["id"]
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    de_gdl = next(v for v in datos["vehiculos"]
                  if v["plaza_id"] == datos["gdl"]["id"])
    h = sesion("consultor")

    def alta(personal, unidades):
        return cliente.post("/implantados", headers=h, json={
            "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
            "plaza_id": datos["cdmx"]["id"],
            "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
            "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
            "fecha_inicio": "2030-03-01", "dias_servicio": "lunes_viernes",
            "modalidad_id": datos["modalidades"]["full_day"]["id"],
            "personal": personal, "unidades": unidades})

    antes = _persona(juan, oficina=True)
    try:
        r = alta([{"persona_id": juan, "rol_id": conductor}], [])
        assert r.status_code == 409, r.text
        assert "oficina" in r.json()["detail"]["mensaje"]
    finally:
        _persona(juan, **antes)

    carlos = datos["personal"]["Carlos Vega"]["id"]        # de Guadalajara
    r = alta([{"persona_id": carlos, "rol_id": conductor}], [])
    assert r.status_code == 409, r.text
    assert "Guadalajara" in r.json()["detail"]["mensaje"]

    r = alta([{"persona_id": juan, "rol_id": conductor,
               "vehiculo_id": de_gdl["id"]}], [de_gdl["id"]])
    assert r.status_code == 409, r.text
    assert de_gdl["placa"] in r.json()["detail"]["mensaje"]

    antes = _persona(juan, activo=False)
    try:
        r = alta([{"persona_id": juan, "rol_id": conductor}], [])
        assert r.status_code == 409, r.text
        assert "activo" in r.json()["detail"]["mensaje"]
    finally:
        _persona(juan, **antes)


def test_al_abrir_el_mes_la_baja_de_la_plantilla_queda_por_cubrir(
        cliente, sesion, datos):
    """Odoo dio de baja al titular a media marcha. El mes que sigue se
    abria con el asignado los veintidos dias y sin una alerta. Ahora se
    abre igual, pero su posicion no se pone: los dias quedan en ambar,
    cada uno con su alerta, y la respuesta lo dice."""
    from app.db import SessionLocal

    juan = datos["personal"]["Juan Ramirez"]["id"]
    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1),
                    personal=[{"persona_id": juan,
                               "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                               "vehiculo_id": datos["suburban"]["id"]}])
    sid = alta["servicio_id"]
    antes = _persona(juan, activo=False)
    try:
        abierto = _abrir_siguiente(sid, date(2030, 3, 25))
        assert abierto["plantilla_fuera"] == ["Juan Ramirez ya no está activo"]
        assert len(abierto["dias_sin_completar"]) == abierto["jornadas_creadas"]

        panel = _panel(cliente, h, sid, 2030, 4)
        assert all(d["personal"] == [] for d in panel["dias"])
        # La unidad si va: sigue en la flota.
        assert all(len(d["unidades"]) == 1 for d in panel["dias"])
        cal = _calendario(cliente, h, sid, 2030, 4)
        entre_semana = [d for d in cal["dias"] if not d["fin_de_semana"]]
        assert all(d["estado"] == "por_cubrir" for d in entre_semana), [
            (d["fecha"], d["estado"]) for d in entre_semana]
        with SessionLocal() as db:
            alertas = (db.query(m.Alerta)
                       .filter(m.Alerta.jornada_id.in_(
                           [d["jornada_id"] for d in panel["dias"]]))
                       .all())
        assert len(alertas) == len(panel["dias"])
        assert all(a.tipo == m.TipoAlerta.PERSONAL_DE_BAJA
                   and a.persona_id == juan for a in alertas)
        # Y la hoja no se libera con esos dias sin nadie.
        r = cliente.post(f"/task-sheets/implantado/{sid}/liberar", headers=h,
                         params={"ahora": "2030-04-01T08:00:00"})
        assert r.status_code == 409, r.text
        assert set(r.json()["detail"]["dias"]) >= {
            d["fecha"] for d in panel["dias"]}
    finally:
        _persona(juan, **antes)


def test_al_abrir_el_mes_la_unidad_en_el_taller_no_se_asigna(cliente, sesion,
                                                              datos):
    """La Suburban entro al taller sin fecha de salida. El mes que sigue
    la copiaba a la plantilla y la ponia en todos sus dias. Ahora el mes
    nace sin ella, con la alerta en cada dia y con la gente puesta."""
    from app.db import SessionLocal

    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid = alta["servicio_id"]
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"]
                and v["plaza_id"] == datos["cdmx"]["id"])
    r = cliente.post(f"/implantados/{sid}/taller", headers=h, json={
        "desde": "2030-03-20", "entra_id": otra["id"],
        "tipo": "mantenimiento_correctivo"})
    assert r.status_code == 200, r.text

    abierto = _abrir_siguiente(sid, date(2030, 3, 25))
    assert abierto["plantilla_fuera"] and "taller" in abierto["plantilla_fuera"][0]
    panel = _panel(cliente, h, sid, 2030, 4)
    assert all(d["unidades"] == [] for d in panel["dias"])
    assert all(len(d["personal"]) == 2 for d in panel["dias"])
    with SessionLocal() as db:
        alertas = (db.query(m.Alerta)
                   .filter(m.Alerta.jornada_id.in_(
                       [d["jornada_id"] for d in panel["dias"]]),
                       m.Alerta.tipo == m.TipoAlerta.VEHICULO_SIN_ASIGNAR)
                   .all())
    assert len(alertas) == len(panel["dias"])
    assert all(a.vehiculo_id == datos["suburban"]["id"] for a in alertas)


# ============================================ 71 · guardar la plantilla

def _plantilla_con_otra_unidad(cliente, h, sid, datos, anio, mes):
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"]
                and v["plaza_id"] == datos["cdmx"]["id"])
    plantilla = cliente.get(f"/implantados/{sid}/mes/{anio}/{mes}/plantilla",
                            headers=h).json()
    r = cliente.put(f"/implantados/{sid}/mes/{anio}/{mes}/plantilla", headers=h,
                    json={"personal": [{"persona_id": p["persona_id"],
                                        "rol_id": p["rol_id"],
                                        "vehiculo_id": otra["id"]
                                        if p["vehiculo_id"] else None}
                                       for p in plantilla["personal"]],
                          "unidades": [otra["id"]]})
    assert r.status_code == 200, r.text
    return otra, r.json()


def test_guardar_la_plantilla_no_toca_el_fin_de_semana(cliente, sesion, datos):
    """Carlos cubrio un sabado desde la ficha; el consultor cambia la
    unidad del mes. Todos los fines de semana quedaban con la plantilla
    fija --el titular que debia descansar-- y Carlos desaparecia."""
    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1),
                    dias="todos")
    sid = alta["servicio_id"]
    sabado = _dia_de_la_semana(2030, 3, 5)
    carlos = datos["personal"]["Carlos Vega"]["id"]
    r = cliente.post(f"/implantados/{sid}/dia/{sabado}/cubrir", headers=h,
                     json={"personal": [{"persona_id": carlos,
                                         "vehiculo_id": datos["suburban"]["id"]}]})
    assert r.status_code == 200, r.text

    otra, hecho = _plantilla_con_otra_unidad(cliente, h, sid, datos, 2030, 3)
    panel = _panel(cliente, h, sid, 2030, 3)
    fines = [d for d in panel["dias"] if d["fin_de_semana"]]
    ese = next(d for d in fines if d["fecha"] == sabado.isoformat())
    assert [p["nombre"] for p in ese["personal"]] == ["Carlos Vega"]
    domingo = next(d for d in fines
                   if d["fecha"] == (sabado + timedelta(days=1)).isoformat())
    assert [p["nombre"] for p in domingo["personal"]] == ["Carlos Vega"]
    otros = [d for d in fines if d["fecha"] not in (ese["fecha"], domingo["fecha"])]
    assert all(d["personal"] == [] for d in otros), [
        (d["fecha"], [p["nombre"] for p in d["personal"]]) for d in otros]
    # Entre semana si: la unidad nueva en todos los dias habiles.
    habiles = [d for d in panel["dias"] if not d["fin_de_semana"]]
    assert hecho["dias_rehechos"] == len(habiles)
    assert all([u["placa"] for u in d["unidades"]] == [otra["placa"]]
               for d in habiles)


def test_guardar_la_plantilla_no_pisa_al_relevo_entre_semana(cliente, sesion,
                                                              datos):
    """El martes lo cubre Carlos a mano --un relevo, no de la plantilla--
    y despues se corrige la unidad del mes: ese martes se queda con
    Carlos; los demas dias habiles se rehacen."""
    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid = alta["servicio_id"]
    martes = _dia_de_la_semana(2030, 3, 1)
    carlos = datos["personal"]["Carlos Vega"]["id"]
    r = cliente.post(f"/implantados/{sid}/dia/{martes}/cubrir", headers=h,
                     json={"personal": [{"persona_id": carlos,
                                         "vehiculo_id": datos["suburban"]["id"]}]})
    assert r.status_code == 200, r.text

    otra, hecho = _plantilla_con_otra_unidad(cliente, h, sid, datos, 2030, 3)
    panel = _panel(cliente, h, sid, 2030, 3)
    ese = next(d for d in panel["dias"] if d["fecha"] == martes.isoformat())
    assert [p["nombre"] for p in ese["personal"]] == ["Carlos Vega"]
    assert [u["placa"] for u in ese["unidades"]] == [datos["suburban"]["placa"]]
    assert hecho["dias_rehechos"] == len(panel["dias"]) - 1


# ================================================== 72 · salir del taller

def test_la_unidad_sale_del_taller_con_fecha(cliente, sesion, datos):
    """La unidad metida al taller sin fecha no tenia como salir: quedaba
    bloqueada para cualquier servicio para siempre. Con la fecha de
    salida, deja de estar fuera desde el dia siguiente."""
    from app.db import SessionLocal

    hoy = date.today()
    alta, h = _alta(cliente, sesion, datos, inicio=hoy.replace(day=1))
    sid = alta["servicio_id"]
    # Con el mes que sigue abierto, siempre hay dias por delante que medir.
    assert cliente.post(f"/implantados/{sid}/mes-siguiente",
                        headers=h).status_code == 200
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"]
                and v["plaza_id"] == datos["cdmx"]["id"])
    desde = hoy
    while desde.weekday() >= 5:
        desde += timedelta(days=1)
    r = cliente.post(f"/implantados/{sid}/taller", headers=h, json={
        "desde": str(desde), "entra_id": otra["id"]})
    assert r.status_code == 200, r.text
    fila = next(f for f in cliente.get(f"/implantados/{sid}/taller", headers=h).json()
                if f["placa"] == datos["suburban"]["placa"])
    assert fila["hasta"] is None and fila["de_odoo"] is False

    # Sale el dia que entro (un correctivo de horas); se mide la semana
    # que sigue a la salida.
    salida = desde
    tramo = (f"?desde={salida + timedelta(days=1)}"
             f"&hasta={salida + timedelta(days=7)}")
    libres = cliente.get(f"/implantados/{sid}/unidades-libres{tramo}", headers=h).json()
    suya = next(v for v in libres["vehiculos"] if v["vehiculo_id"] == datos["suburban"]["id"])
    assert libres["dias"] > 0 and suya["dias_en_taller"] == libres["dias"]

    # La salida es antes de la entrada: no.
    r = cliente.put(f"/implantados/{sid}/taller/{fila['id']}", headers=h,
                    json={"hasta": str(desde - timedelta(days=1))})
    assert r.status_code == 409, r.text
    r = cliente.put(f"/implantados/{sid}/taller/{fila['id']}", headers=h,
                    json={"hasta": str(salida)})
    assert r.status_code == 200, r.text
    fila = next(f for f in cliente.get(f"/implantados/{sid}/taller", headers=h).json()
                if f["placa"] == datos["suburban"]["placa"])
    assert fila["hasta"] == str(salida)
    libres = cliente.get(f"/implantados/{sid}/unidades-libres{tramo}", headers=h).json()
    suya = next(v for v in libres["vehiculos"] if v["vehiculo_id"] == datos["suburban"]["id"])
    assert suya["dias_en_taller"] == 0

    # Lo que vino de Odoo se cierra en Odoo.
    with SessionLocal() as db:
        de_odoo = m.TallerVehiculo(vehiculo_id=datos["suburban"]["id"],
                                   desde=hoy, hasta=None, odoo_id=987654,
                                   tipo=m.MotivoCambio.MANTENIMIENTO_CORRECTIVO)
        db.add(de_odoo)
        db.commit()
        de_odoo_id = de_odoo.id
    r = cliente.put(f"/implantados/{sid}/taller/{de_odoo_id}", headers=h,
                    json={"hasta": str(hoy)})
    assert r.status_code == 409, r.text
    assert "Odoo" in r.json()["detail"]["que_hacer"]


# ======================================================= 74 · los detalles

def test_cancelar_el_deposito_del_mes_deja_pedido_lo_enviado(cliente, sesion,
                                                              datos):
    """a5-15, resuelto en la seccion 98 y aqui amarrado: la solicitud que
    finanzas ya mando al banco no se cancela sola, queda pedida."""
    from app.db import SessionLocal

    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid = alta["servicio_id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    hd = sesion("diroperaciones")
    r = cliente.post(f"/implantados/{sid}/viaticos/2030/3/persona", headers=hd,
                     json={"persona_id": juan, "monto": "4200"})
    assert r.status_code == 200, r.text
    r = cliente.post(f"/implantados/{sid}/viaticos/2030/3/solicitar", headers=hd,
                     json={"persona_id": juan})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        primera = (db.query(m.SolicitudTransferencia)
                   .order_by(m.SolicitudTransferencia.id).first())
        primera.estatus = m.EstatusTransferencia.ENVIADA
        db.commit()
        primera_id = primera.id

    r = cliente.post(f"/implantados/{sid}/viaticos/2030/3/cancelar", headers=hd,
                     json={"persona_id": juan})
    assert r.status_code == 200, r.text
    assert r.json()["pedidos_a_finanzas"] == 1
    with SessionLocal() as db:
        s = db.get(m.SolicitudTransferencia, primera_id)
        assert s.estatus == m.EstatusTransferencia.ENVIADA
        assert s.cancelacion_pedida_en is not None


def test_reabrir_un_dia_habil_no_lo_cobra_como_adicional(cliente, sesion, datos):
    """Un martes borrado por error y vuelto a abrir por la API se
    facturaba al precio del dia adicional. Adicional es el fin de
    semana, como al cubrir un dia o al generar el mes."""
    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    martes = _dia_de_la_semana(2030, 3, 1)
    assert cliente.delete(f"/implantados/{sid}/dia/{martes}",
                          headers=h).status_code == 200
    r = cliente.post(f"/implantados/{sid}/dias", headers=h,
                     json={"fecha": str(martes)})
    assert r.status_code == 200, r.text
    assert r.json()["es_dia_adicional"] is False
    assert float(r.json()["costo_extra"]) == 0
    resumen = cliente.get(f"/implantados/contratos/{contrato}/resumen",
                          headers=h).json()
    assert resumen["dias"]["adicionales"] == 0
    # El sabado si es adicional, con su costo.
    sabado = _dia_de_la_semana(2030, 3, 5)
    r = cliente.post(f"/implantados/{sid}/dias", headers=h,
                     json={"fecha": str(sabado)})
    assert r.status_code == 200, r.text
    assert r.json()["es_dia_adicional"] is True
    assert float(r.json()["costo_extra"]) == 3500


def test_la_hoja_del_implantado_imprime_la_distancia_de_los_hospitales(
        cliente, sesion, datos):
    """La hoja leia `distancia_km` y la llave es `km`: la distancia de
    los hospitales nunca salia."""
    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid = alta["servicio_id"]
    hospitales = cliente.get(f"/implantados/{sid}/hospitales", headers=h).json()
    assert hospitales["hospitales"], "la capital tiene hospitales sembrados"
    r = cliente.get(f"/task-sheets/implantado/{sid}/hoja?idioma=es", headers=h)
    assert r.status_code == 200, r.text
    for x in hospitales["hospitales"]:
        assert f"{x['km']} km" in r.text, x


def test_las_entradas_del_implantado_se_validan(cliente, sesion, datos):
    """Un mes 13 o una hora "8:00" reventaban con un 500 al generar el
    mes; un monto negativo entraba al tabulador y al deposito del mes.
    Ahora contestan 422 con que corregir, y "08:00" se guarda con sus
    segundos."""
    h = sesion("consultor")
    servicio = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "implantado",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}, headers=h).json()

    def contrato(**cambios):
        return cliente.post("/implantados/contratos", headers=h, json={
            "servicio_id": servicio["id"], "anio": 2030, "mes": 5,
            "modalidad_id": datos["modalidades"]["full_day"]["id"],
            "titular_id": datos["personal"]["Juan Ramirez"]["id"],
            "precio_dia_personal": "2900", **cambios})

    assert contrato(mes=13).status_code == 422
    assert contrato(anio=99).status_code == 422
    r = contrato(hora_presentacion="8:00")
    assert r.status_code == 422, r.text
    assert "07:30:00" in r.text
    assert contrato(hora_presentacion="25:00").status_code == 422
    r = contrato(hora_presentacion="08:30")
    assert r.status_code == 201, r.text
    assert cliente.post(f"/implantados/contratos/{r.json()['contrato_id']}/generar-mes",
                        headers=h).status_code == 200
    panel = _panel(cliente, h, servicio["id"], 2030, 5)
    assert {d["presentacion"] for d in panel["dias"]} == {"08:30"}

    r = cliente.get("/implantados/disponibilidad", headers=h, params={
        "plaza_id": datos["cdmx"]["id"], "desde": "2030-05-01",
        "dias_servicio": "lunes_viernes", "hora": "8:00"})
    assert r.status_code == 422, r.text

    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid = alta["servicio_id"]
    r = cliente.put(f"/implantados/{sid}/tabulador", headers=h, json={
        "renglones": [{"concepto": "alimentos", "monto": "-5", "activo": True}]})
    assert r.status_code == 422, r.text
    r = cliente.post(f"/implantados/{sid}/viaticos/2030/3/persona",
                     headers=sesion("diroperaciones"),
                     json={"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                           "monto": "-100"})
    assert r.status_code == 422, r.text


def test_el_trato_habla_del_mes_de_hoy_en_el_pais_del_servicio(
        cliente, sesion, datos, monkeypatch):
    """El mes del que habla el trato es el que se opera hoy, con el hoy
    del pais del servicio y no el del servidor. La hora del mes es la de
    ese mes; la del trato es la acordada con el cliente (seccion 105):
    la herramienta del mes que movio abril no cambia el trato."""
    from app import implantado as motor

    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid = alta["servicio_id"]
    _abrir_siguiente(sid, date(2030, 3, 25))
    r = cliente.put(f"/implantados/{sid}/hora-presentacion", headers=h,
                    json={"hora": "07:30:00", "anio": 2030, "mes": 4})
    assert r.status_code == 200, r.text

    monkeypatch.setattr(motor, "hoy_del_servicio",
                        lambda db, servicio: date(2030, 3, 15))
    trato = cliente.get(f"/implantados/{sid}/acuerdo", headers=h).json()
    assert (trato["mes_anio"], trato["mes_mes"]) == (2030, 3)
    assert trato["hora_presentacion"] == "08:00:00"
    assert trato["hora_del_mes"] == "08:00:00"
    monkeypatch.setattr(motor, "hoy_del_servicio",
                        lambda db, servicio: date(2030, 4, 2))
    trato = cliente.get(f"/implantados/{sid}/acuerdo", headers=h).json()
    assert (trato["mes_anio"], trato["mes_mes"]) == (2030, 4)
    assert trato["hora_del_mes"] == "07:30:00"
    assert trato["hora_presentacion"] == "08:00:00"


def test_el_panel_del_mes_lista_solo_sus_cambios(cliente, sesion, datos):
    """El equipo es el mismo mes tras mes, y el panel de cada mes
    listaba los cambios de todos los meses."""
    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid = alta["servicio_id"]
    _abrir_siguiente(sid, date(2030, 3, 25))
    abril = _panel(cliente, h, sid, 2030, 4)["dias"]
    r = cliente.post(f"/implantados/{sid}/cambios", headers=h, json={
        "tipo": "personal", "desde": abril[1]["fecha"], "hasta": abril[3]["fecha"],
        "sale_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_id": datos["personal"]["Carlos Vega"]["id"],
        "motivo": "vacaciones"})
    assert r.status_code == 200, r.text
    assert _panel(cliente, h, sid, 2030, 3)["cambios"] == []
    cambios = _panel(cliente, h, sid, 2030, 4)["cambios"]
    assert len(cambios) == 1 and cambios[0]["desde"] == abril[1]["fecha"]


def test_guardar_la_plantilla_retoma_los_precios_de_la_lista(cliente, sesion,
                                                              datos, lista):
    """El mes iba con la lista de implantados con conductor y agente; se
    quita al agente de la plantilla y el mes seguia diciendo «va con la
    lista» con el precio de los dos."""
    from test_implantado_lista import (AGENTE, CONDUCTOR, _alta as _alta_lista,
                                       _equipo, _terminos, _unidad)

    lista()
    suv = _unidad(datos, "suv_blindada")
    alta = _alta_lista(cliente, sesion, datos, date(2030, 6, 3),
                       _equipo(datos, suv), [suv["id"]])
    sid, contrato_id = alta["servicio_id"], alta["contrato_id"]
    x = _terminos(cliente, sesion, contrato_id)
    assert x["precios_de_la_lista"] is True
    assert float(x["precio_dia_personal"]) == float(CONDUCTOR + AGENTE)

    h = sesion("consultor")
    r = cliente.put(f"/implantados/{sid}/mes/2030/6/plantilla", headers=h, json={
        "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": suv["id"]}],
        "unidades": [suv["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["precios_de_la_lista"] is True
    assert r.json()["precios_cambiados"]
    x = _terminos(cliente, sesion, contrato_id)
    assert float(x["precio_dia_personal"]) == float(CONDUCTOR)
    assert x["precios_de_la_lista"] is True and x["diferencias"] == []


def test_la_hoja_del_servicio_presenta_la_plantilla_del_mes_de_hoy(
        cliente, sesion, datos, monkeypatch):
    """Con el mes que sigue ya abierto y otra plantilla, la hoja «del
    servicio» presentaba a la gente del mes siguiente."""
    from app import hoja_implantado
    from app import implantado as motor
    from app.db import SessionLocal

    alta, h = _alta(cliente, sesion, datos, inicio=date(2030, 3, 1))
    sid = alta["servicio_id"]
    _abrir_siguiente(sid, date(2030, 3, 25))
    miguel = datos["personal"]["Miguel Torres"]["id"]
    r = cliente.put(f"/implantados/{sid}/mes/2030/4/plantilla", headers=h, json={
        "personal": [{"persona_id": miguel,
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": datos["suburban"]["id"]}],
        "unidades": [datos["suburban"]["id"]]})
    assert r.status_code == 200, r.text

    monkeypatch.setattr(motor, "hoy_del_servicio",
                        lambda db, servicio: date(2030, 3, 15))
    with SessionLocal() as db:
        hoja = hoja_implantado.armar(db, sid)
    assert hoja["periodo"] == "03/2030"
    assert sorted(p["nombre"] for p in hoja["equipo"]) == ["Juan Ramirez",
                                                           "Luis Mendoza"]


# Las fixtures de la lista de implantados viven en test_implantado_lista.
from test_implantado_lista import db, lista  # noqa: E402,F401

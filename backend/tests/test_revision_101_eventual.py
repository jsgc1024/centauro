# -*- coding: utf-8 -*-
"""Seccion 101, grupo g2: el servicio eventual, el alta, la hoja y la
cartera.

Cuarta tanda de la revision del 28 de septiembre (revisor a1): la hoja
con dos equipos, el principal corregido que no llegaba a la hoja, los
empalmes al mover un dia, el rastro del punto de encuentro y del vuelo,
la cotizacion al eliminar un equipo, la cartera sin tope, el vuelo de
salida con un solo dia, lo que tardaban "Asignar recursos" y "Pagos", y
los detalles del alta y de la hoja.
"""
import os
import re
import threading
import uuid
import zlib
from datetime import timedelta

import pytest
from sqlalchemy import event, text

from app import models as m
from ayudas import (ORIGEN, asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana)

WEB = os.path.join(os.path.dirname(__file__), "..", "app", "web")


def _js(nombre: str) -> str:
    return open(os.path.join(WEB, nombre), encoding="utf-8").read()


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
    import pywebpush
    from app import push

    mandados = []

    def falso(**kwargs):
        mandados.append(kwargs)
        return True

    monkeypatch.setattr(pywebpush, "webpush", falso)
    monkeypatch.setattr(push.settings, "vapid_private", "llave-de-prueba")
    monkeypatch.setattr(push.settings, "vapid_public", "publica-de-prueba")
    return mandados


def _telefono(db, persona_id, endpoint="https://push.example/101"):
    fila = m.SuscripcionPush(persona_id=persona_id, endpoint=endpoint,
                             p256dh="clave-publica", auth="secreto")
    db.add(fila)
    db.commit()


def _contar(cliente, metodo, ruta, headers, json=None):
    """La respuesta y cuantas consultas SQL costo."""
    from app.db import engine

    cuenta = {"n": 0}

    def contar(conn, cursor, statement, parameters, context, executemany):
        cuenta["n"] += 1

    event.listen(engine, "before_cursor_execute", contar)
    try:
        r = cliente.request(metodo, ruta, headers=headers, json=json)
    finally:
        event.remove(engine, "before_cursor_execute", contar)
    return r, cuenta["n"]


def _dia(datos, cuando, modalidad="full_day", hora="07:00:00", **extra):
    return jornada(manana(cuando), datos["modalidades"][modalidad]["id"],
                   hora=hora, **extra)


def _otra_unidad(datos):
    return next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"]
                and v["categoria_id"] == datos["categorias"]["suv_blindada"]["id"])


# ============================================ 7 · la hoja con dos equipos

def test_con_dos_equipos_la_hoja_se_arma_y_se_confirma_por_equipo(
        cliente, sesion, datos):
    """Alfa y Beta: el atajo por servicio contesta que hay que elegir,
    las rutas por equipo contestan cada una su hoja, y confirmar la
    asignacion libera las dos."""
    h = sesion("consultor")
    dia = _dia(datos, 40, **ORIGEN)
    servicio = crear_servicio(
        cliente, h, datos, [dia],
        equipos=[{"clave": "A", "jornadas": [dia]},
                 {"clave": "B", "ejecutivo_nombre": "Otro",
                  "ejecutivo_apellidos": "Principal", "jornadas": [dia]}])
    equipos = servicio["equipos"]
    assert [e["alias"] for e in equipos] == ["Alfa", "Beta"]
    asignar(cliente, h, equipos[0]["jornadas"][0]["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    asignar(cliente, h, equipos[1]["jornadas"][0]["id"],
            persona_id=datos["personal"]["Luis Mendoza"]["id"],
            vehiculo_id=_otra_unidad(datos)["id"])

    # Lo que la consola usaba: con dos equipos no contesta hoja.
    r = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                    headers=h)
    assert r.status_code == 409
    assert [e["alias"] for e in r.json()["detail"]["equipos"]] == ["Alfa", "Beta"]

    # Lo que la consola usa ahora: una vista por equipo.
    for equipo, quien in zip(equipos, ("Ingrid Halvorsen", "Otro Principal")):
        r = cliente.get(f"/task-sheets/equipo/{equipo['id']}/vista-previa",
                        headers=h)
        assert r.status_code == 200, r.text
        vista = r.json()
        assert vista["equipo"] == equipo["alias"]
        assert vista["equipos_del_servicio"] == 2
        assert vista["ejecutivo"] == quien
        assert vista["faltantes"] == []

    r = cliente.post(f"/servicios/{servicio['id']}/confirmar-asignacion",
                     headers=h)
    assert r.status_code == 200, r.text
    assert [v["equipo"] for v in r.json()["versiones"]] == ["Alfa", "Beta"]
    for equipo in equipos:
        r = cliente.get(f"/task-sheets/equipo/{equipo['id']}/hoja?idioma=es",
                        headers=h)
        assert r.status_code == 200, r.text
        assert "Otro Principal" in r.text or equipo["alias"] == "Alfa"


def test_la_consola_pinta_la_hoja_por_equipo():
    """El bloque del task sheet pide la vista y la hoja por equipo, y el
    boton de confirmar no depende de que la vista previa cargue."""
    js = _js("servicio.js")
    bloque = js[js.index("async function bloqueTaskSheet("):
                js.index("function bloqueVestimenta(")]
    assert "/task-sheets/equipo/${equipo.id}/vista-previa" in bloque
    assert "/task-sheets/equipo/${equipo.id}/hoja" in bloque
    # La vista y la hoja ya no se piden por servicio (con dos equipos el
    # servidor contesta 409). Publicar de nuevo si va por servicio: esa
    # ruta publica la hoja de cada equipo.
    assert "/task-sheets/servicio/${servicio.id}/vista-previa" not in bloque
    assert "/task-sheets/servicio/${servicio.id}/hoja" not in bloque
    # El confirmar sale aunque una vista falle: la falla se pinta y sigue.
    assert ".catch(err => ({ error: err }))" in bloque
    assert "confirmar-asignacion" in bloque


# ==================================== 9 · corregir el principal llega a todo

def _alta_como_la_consola_de_antes(cliente, h, datos):
    """El alta que hacia la consola: el principal del servicio copiado al
    primer equipo."""
    cuerpo = {
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "solicitante_nombre": "Patricia", "solicitante_apellidos": "Lundgren",
        "solicitante_correo": "solicitante@cliente.com",
        "ejecutivo_nombre": "Ingrid", "ejecutivo_apellidos": "Halvorsen",
        "ejecutivo_correo": "ejecutivo@cliente.com",
        "ejecutivo_telefono": "+47 900 00 001",
        "equipos": [{"plaza_id": datos["cdmx"]["id"],
                     "ejecutivo_nombre": "Ingrid",
                     "ejecutivo_apellidos": "Halvorsen",
                     "ejecutivo_correo": "ejecutivo@cliente.com",
                     "ejecutivo_telefono": "+47 900 00 001",
                     "jornadas": [_dia(datos, 41, **ORIGEN)]}],
    }
    r = cliente.post("/servicios", json=cuerpo, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_corregir_el_principal_llega_a_la_hoja_y_a_los_avisos(
        cliente, sesion, datos, db):
    """El equipo Alfa traia una copia del principal. Al corregir el del
    servicio, la copia se suelta: la hoja, el correo del TS y los avisos
    del dia leen el dato corregido, y la forma ya no pinta a Alfa como
    si cuidara a otro principal."""
    from app import tasksheet as motor

    h = sesion("consultor")
    servicio = _alta_como_la_consola_de_antes(cliente, h, datos)
    d = cliente.get(f"/servicios/{servicio['id']}/contactos", headers=h).json()
    assert [e["alias"] for e in d["equipos"]] == ["Alfa"]

    r = cliente.patch(f"/servicios/{servicio['id']}/contactos", json={
        "ejecutivo": {"nombre": "Ingrid", "apellidos": "Halvorsen",
                      "correo": "ingrid.nueva@cliente.com",
                      "telefono": "+47 900 00 999", "idioma": "en"}},
        headers=h)
    assert r.status_code == 200, r.text
    cambios = {(c["quien"], c["campo"]) for c in r.json()["cambios"]}
    assert ("equipo Alfa", "principal") in cambios

    vista = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()
    assert vista["ejecutivo_telefono"] == "+47 900 00 999"
    d = cliente.get(f"/servicios/{servicio['id']}/contactos", headers=h).json()
    assert d["equipos"] == []

    equipo = db.get(m.Equipo, servicio["equipos"][0]["id"])
    assert not equipo.tiene_ejecutivo_propio
    assert equipo.ejecutivo_correo_efectivo == "ingrid.nueva@cliente.com"
    # El correo del TS sale al correo corregido.
    motor.publicar(db, equipo.id, datos["personal"]["Ana Solis"]["id"],
                   forzar=True, avisar=True)
    correos = {n.correo for n in db.query(m.Notificacion)
               .filter_by(servicio_id=servicio["id"],
                          destinatario=m.Destinatario.EJECUTIVO).all()}
    assert "ingrid.nueva@cliente.com" in correos
    assert "ejecutivo@cliente.com" not in correos


def test_el_equipo_que_cuida_a_otro_principal_no_se_toca(cliente, sesion, datos):
    """Beta lleva a su propio principal: corregir el del servicio no se lo
    cambia."""
    h = sesion("consultor")
    dia = _dia(datos, 42, **ORIGEN)
    servicio = crear_servicio(
        cliente, h, datos, [dia],
        equipos=[{"clave": "A", "jornadas": [dia]},
                 {"clave": "B", "ejecutivo_nombre": "Otro",
                  "ejecutivo_apellidos": "Principal",
                  "ejecutivo_correo": "otro@cliente.com", "jornadas": [dia]}])
    r = cliente.patch(f"/servicios/{servicio['id']}/contactos", json={
        "ejecutivo": {"nombre": "Ingrid", "apellidos": "Halvorsen",
                      "correo": "ingrid.nueva@cliente.com", "idioma": "en"}},
        headers=h)
    assert r.status_code == 200, r.text
    d = cliente.get(f"/servicios/{servicio['id']}/contactos", headers=h).json()
    assert [(e["alias"], e["correo"]) for e in d["equipos"]] == [
        ("Beta", "otro@cliente.com")]


def test_el_alta_de_la_consola_ya_no_copia_el_principal_al_primer_equipo():
    """El primer equipo --y el que marca «mismo ejecutivo»-- hereda el
    principal del servicio en vez de mandar una copia."""
    js = _js("consultor.js")
    assert "eq.datos(i === 0 || eq.mismoEjecutivo.checked)" in js
    assert "ejecutivo_nombre: hereda ? null : " in js
    assert "ejecutivo_nombre: armados[0].ejecutivo_nombre" not in js


# ======================================== 10 · mover un dia revisa empalmes

def test_mover_la_fecha_encima_de_otro_servicio_se_bloquea(cliente, sesion, datos):
    """Juan esta en A el dia 10 y en B el 12. Adelantar B al 10 lo dejaba
    en dos servicios el mismo dia sin aviso; ahora es un bloqueo y la
    fecha no se mueve."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    a = crear_servicio(cliente, h, datos, [_dia(datos, 10)])
    b = crear_servicio(cliente, h, datos, [_dia(datos, 12)])
    ja = a["equipos"][0]["jornadas"][0]
    jb = b["equipos"][0]["jornadas"][0]
    for j in (ja, jb):
        assert asignar(cliente, h, j["id"], persona_id=juan)[0].status_code == 200

    r = cliente.patch(f"/servicios/jornadas/{jb['id']}",
                      json={"fecha": str(manana(10))}, headers=h)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["alertas"] and all(x["nivel"] == "bloqueo" for x in d["alertas"])
    assert d["alertas"][0]["quien"] == "Juan Ramirez"
    assert d["alertas"][0]["servicio"] == a["folio"]
    # Ni con forzar: el empalme real es bloqueo duro.
    r = cliente.patch(f"/servicios/jornadas/{jb['id']}",
                      json={"fecha": str(manana(10)), "forzar": True}, headers=h)
    assert r.status_code == 409, r.text
    assert cliente.get(f"/servicios/{b['id']}", headers=h).json()[
        "equipos"][0]["jornadas"][0]["fecha"] == str(manana(12))


def test_mover_la_hora_con_poco_margen_avisa_y_el_consultor_decide(
        cliente, sesion, datos):
    """Dos transfers el mismo dia con margen de sobra; acercar el segundo
    deja una hora entre los dos: alerta de riesgo, y con forzar se mueve
    y queda dicho en la bitacora."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    a = crear_servicio(cliente, h, datos, [_dia(datos, 14, "transfer", "07:00:00")])
    b = crear_servicio(cliente, h, datos, [_dia(datos, 14, "transfer", "14:00:00")])
    ja = a["equipos"][0]["jornadas"][0]
    jb = b["equipos"][0]["jornadas"][0]
    for j in (ja, jb):
        assert asignar(cliente, h, j["id"], persona_id=juan)[0].status_code == 200

    # A corre de 07:00 a 10:00; B a las 11:00 deja una hora de holgura.
    r = cliente.patch(f"/servicios/jornadas/{jb['id']}",
                      json={"hora_presentacion": "11:00:00"}, headers=h)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert all(x["nivel"] == "riesgo" for x in d["alertas"])
    assert "forzar" in d["mensaje"]

    r = cliente.patch(f"/servicios/jornadas/{jb['id']}",
                      json={"hora_presentacion": "11:00:00", "forzar": True},
                      headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["inicio"].endswith("T11:00:00")
    assert len(r.json()["alertas_aceptadas"]) == 1
    bitacora = cliente.get(f"/servicios/{b['id']}/auditoria", headers=h).json()
    ultimo = bitacora["movimientos"][-1]
    assert ultimo["accion"] == "corregir dia"
    assert "forzado sobre alerta" in ultimo["detalle"]


def test_el_vuelo_que_mueve_la_presentacion_tambien_revisa_los_empalmes(
        cliente, sesion, datos):
    """Juan hace un transfer de 07:00 en A y a las 14:00 arranca B. El
    vuelo de llegada de las 08:30 en B pondria la presentacion a las
    07:45, encima de A: se rechaza y el vuelo no se guarda."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    a = crear_servicio(cliente, h, datos, [_dia(datos, 16, "transfer", "07:00:00")])
    b = crear_servicio(cliente, h, datos, [_dia(datos, 16, "medio_dia", "14:00:00",
                                                **ORIGEN)])
    ja = a["equipos"][0]["jornadas"][0]
    jb = b["equipos"][0]["jornadas"][0]
    for j in (ja, jb):
        assert asignar(cliente, h, j["id"], persona_id=juan)[0].status_code == 200

    r = cliente.patch(f"/operacion/jornadas/{jb['id']}/vuelo", json={
        "vuelo_aerolinea": "Aeromexico", "vuelo_numero": "AM 57",
        "vuelo_hora": f"{jb['fecha']}T08:30:00", "vuelo_tipo": "llegada"},
        headers=h)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["alertas"][0]["nivel"] == "bloqueo"
    j = cliente.get(f"/servicios/{b['id']}", headers=h).json()["equipos"][0]["jornadas"][0]
    assert j["vuelo_numero"] is None
    assert j["inicio_programado"].endswith("T14:00:00")


def test_la_consola_ensena_el_choque_al_mover_un_dia_y_ofrece_forzar():
    """La tabla de dias pinta el choque debajo del dia y, con riesgo,
    ofrece mover igual; el panel del punto pregunta antes de forzar."""
    js = _js("servicio.js")
    assert "function choqueDeDia(err)" in js
    assert "function panelDeChoque(choque, acciones)" in js
    assert "guardar({ ...cambios, forzar: true })" in js
    assert "async function conForzar(pedir)" in js
    assert "hora_presentacion: `${presentacion.value}:00`, forzar" in js


# =============================== 11 · el punto y el vuelo dejan rastro

def test_el_punto_de_encuentro_y_el_vuelo_quedan_en_la_bitacora_en_cobertura(
        cliente, sesion, datos):
    """Quien cubre a Ana cambia el meet and greet y captura el vuelo: las
    dos acciones quedan en la bitacora del servicio marcadas como
    cobertura, como cualquier otra."""
    h = sesion("consultor")
    cubre = sesion("consultor2")
    servicio = crear_servicio(
        cliente, h, datos, [_dia(datos, 18)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]

    r = cliente.patch(f"/operacion/jornadas/{j['id']}/origen", json=ORIGEN,
                      headers=cubre)
    assert r.status_code == 200, r.text
    r = cliente.patch(f"/operacion/jornadas/{j['id']}/vuelo", json={
        "vuelo_aerolinea": "Aeromexico", "vuelo_numero": "AM 57",
        "vuelo_hora": f"{j['fecha']}T14:00:00", "vuelo_tipo": "llegada"},
        headers=cubre)
    assert r.status_code == 200, r.text
    assert r.json()["presentacion_movida"] is True

    bitacora = cliente.get(f"/servicios/{servicio['id']}/auditoria", headers=h).json()
    por_accion = {x["accion"]: x for x in bitacora["movimientos"]}
    assert "punto de encuentro" in por_accion
    assert ORIGEN["origen_direccion"] in por_accion["punto de encuentro"]["detalle"]
    assert por_accion["punto de encuentro"]["en_cobertura"] is True
    assert "capturar vuelo" in por_accion
    detalle = por_accion["capturar vuelo"]["detalle"]
    assert "AM 57" in detalle and "07:00 -> 13:15" in detalle
    assert por_accion["capturar vuelo"]["en_cobertura"] is True

    # Guardar lo mismo otra vez no escribe otro renglon.
    antes = len(bitacora["movimientos"])
    cliente.patch(f"/operacion/jornadas/{j['id']}/origen", json=ORIGEN, headers=cubre)
    cliente.patch(f"/operacion/jornadas/{j['id']}/vuelo", json={
        "vuelo_aerolinea": "Aeromexico", "vuelo_numero": "AM 57",
        "vuelo_hora": f"{j['fecha']}T14:00:00", "vuelo_tipo": "llegada"},
        headers=cubre)
    bitacora = cliente.get(f"/servicios/{servicio['id']}/auditoria", headers=h).json()
    assert len(bitacora["movimientos"]) == antes


def test_el_vuelo_que_mueve_la_hora_le_avisa_a_quien_ya_confirmo(
        cliente, sesion, datos, db, salieron):
    """Juan confirmo para las 07:00; el vuelo de las 14:00 pasa la
    presentacion a las 13:15 y le llega «Cambio tu hora»."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(cliente, h, datos, [_dia(datos, 19, **ORIGEN)])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)
    _telefono(db, juan)
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=sesion("juan"))
    assert r.status_code == 200, r.text

    r = cliente.patch(f"/operacion/jornadas/{j['id']}/vuelo", json={
        "vuelo_aerolinea": "Aeromexico", "vuelo_numero": "AM 57",
        "vuelo_hora": f"{j['fecha']}T14:00:00", "vuelo_tipo": "llegada"},
        headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["presentacion"] == "13:15"
    assert len(salieron) == 1, salieron
    carga = str(salieron[0]["data"])
    assert "Cambi" in carga and "13:15" in carga and "07:00" in carga


# ================================ 12 · eliminar un equipo y la cotizacion

def test_eliminar_un_equipo_acomoda_los_renglones_de_la_cotizacion(
        cliente, sesion, datos, db):
    """Alfa, Beta y Gamma cotizados; se elimina Beta. Gamma pasa a ser
    Beta y sus renglones con el; los de Beta se van, y el total vuelve a
    ser la suma de lo que queda."""
    h = sesion("consultor")
    dia = _dia(datos, 20, **ORIGEN)
    servicio = crear_servicio(
        cliente, h, datos, [dia],
        equipos=[{"clave": "A", "jornadas": [dia]},
                 {"clave": "B", "jornadas": [dia]},
                 {"clave": "C", "jornadas": [dia]}])
    assert [e["alias"] for e in servicio["equipos"]] == ["Alfa", "Beta", "Gamma"]
    perfil = datos["perfiles"]["conductor_seguridad"]["id"]
    categoria = datos["categorias"]["suv_blindada"]["id"]
    lineas = []
    for e in servicio["equipos"]:
        lineas.append({"fecha": dia["fecha"], "tipo": "recurso",
                       "perfil_id": perfil, "equipo_clave": e["alias"],
                       "cantidad": 1 if e["alias"] != "Gamma" else 2})
        lineas.append({"fecha": dia["fecha"], "tipo": "vehiculo",
                       "categoria_id": categoria, "equipo_clave": e["alias"]})
    r = cliente.post("/cotizaciones/autorizada", json={
        "servicio_id": servicio["id"], "lineas": lineas, "gastos": "fijo",
        "monto_gastos": "1500", "autorizada_por": "Patricia Lundgren",
        "autorizada_el": str(manana(0))}, headers=h)
    assert r.status_code == 201, r.text
    total_de_antes = db.query(m.Cotizacion).one().total

    beta = servicio["equipos"][1]["id"]
    r = cliente.delete(f"/servicios/equipos/{beta}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["equipos_restantes"] == ["Alfa", "Beta"]
    assert r.json()["renglones_de_cotizacion_ajustados"] > 0

    db.expire_all()
    cotizacion = db.query(m.Cotizacion).one()
    claves = sorted((l.equipo_clave, l.tipo.value, l.cantidad)
                    for l in cotizacion.lineas)
    assert not any(c[0] == "Gamma" for c in claves)
    # Lo de Gamma sigue vivo como Beta: el conductor doble sigue ahi.
    assert ("Beta", "recurso", 2) in claves
    assert ("Alfa", "recurso", 1) in claves
    # El monto fijo de gastos no se pierde.
    assert ("Alfa", "viaticos", 1) in claves
    assert cotizacion.total == sum(l.subtotal for l in cotizacion.lineas)
    assert cotizacion.total < total_de_antes
    # Y el comparativo del cierre ya no ve dias de menos de un equipo que
    # no existe.
    bloque = cliente.get(f"/cotizaciones/servicio/{servicio['id']}/bloque",
                         headers=h).json()
    assert bloque["vigente"]["equipos"] == 2


# ================================================= 13 · la cartera sin tope

def _sembrar_servicios(db, datos, cuantos, estatus, folio="CART"):
    filas = []
    for i in range(cuantos):
        filas.append(m.Servicio(
            folio=f"{folio}-{uuid.uuid4().hex[:8]}", cliente_id=datos["cliente_id"],
            pais_id=datos["mx"]["id"], plaza_id=datos["cdmx"]["id"],
            tipo=m.TipoServicio.EVENTUAL, estatus=estatus,
            ejecutivo_nombre="Gerardo", ejecutivo_apellidos="Muñoz",
            solicitante_nombre="Patricia", solicitante_apellidos="Lundgren"))
    db.add_all(filas)
    db.commit()
    return [f.id for f in filas]


def test_la_cartera_trae_todos_los_abiertos_sin_tope(cliente, sesion, datos, db):
    """Con 120 servicios vivos, la cartera pedia los ultimos 100 y el
    consultor creia que los demas no existian."""
    h = sesion("consultor")
    _sembrar_servicios(db, datos, 120, m.EstatusServicio.PLANEADO)
    _sembrar_servicios(db, datos, 3, m.EstatusServicio.CANCELADO)
    vivos = cliente.get("/servicios?vivos=true", headers=h).json()
    assert len(vivos) == 120
    assert {s["estatus"] for s in vivos} == {"planeado"}
    # Sin decir nada sigue contestando lo de siempre: los ultimos 100.
    assert len(cliente.get("/servicios", headers=h).json()) == 100


def test_los_cerrados_se_traen_por_paginas(cliente, sesion, datos, db):
    """Los cerrados y cancelados van por partes, del mas reciente al mas
    viejo, y `antes_de` sigue donde se quedo la pagina anterior."""
    h = sesion("consultor")
    _sembrar_servicios(db, datos, 2, m.EstatusServicio.PLANEADO)
    ids = _sembrar_servicios(db, datos, 60, m.EstatusServicio.CANCELADO)
    pagina = cliente.get("/servicios?vivos=false", headers=h).json()
    assert len(pagina) == 50
    assert pagina[0]["id"] == max(ids)
    assert all(s["estatus"] == "cancelado" for s in pagina)
    ultimo = pagina[-1]["id"]
    resto = cliente.get(f"/servicios?vivos=false&antes_de={ultimo}", headers=h).json()
    assert len(resto) == 10
    assert set(s["id"] for s in pagina + resto) == set(ids)


def test_el_buscador_busca_en_el_servidor_sin_acentos_ni_comodines(
        cliente, sesion, datos, db):
    """Por folio, cliente, principal o quien solicita; «munoz» encuentra a
    Muñoz y el `_` no es comodin."""
    h = sesion("consultor")
    ids = _sembrar_servicios(db, datos, 3, m.EstatusServicio.CERRADO, folio="EP/E-9")
    otro = m.Servicio(
        folio="EP/E-9000", cliente_id=datos["cliente_id"],
        pais_id=datos["mx"]["id"], plaza_id=datos["cdmx"]["id"],
        tipo=m.TipoServicio.EVENTUAL, estatus=m.EstatusServicio.CERRADO,
        ejecutivo_nombre="Sven", ejecutivo_apellidos="Larsen")
    db.add(otro)
    db.commit()

    def buscar(q):
        r = cliente.get(f"/servicios?vivos=false&q={q}", headers=h)
        assert r.status_code == 200, r.text
        return {s["id"] for s in r.json()}

    assert buscar("munoz") == set(ids)
    assert buscar("MU%C3%91OZ") == set(ids)          # Muñoz, con su eñe
    assert buscar("larsen") == {otro.id}
    assert buscar("lundgren") == set(ids)
    assert buscar("EP/E-9000") == {otro.id}
    assert buscar("EP/E-9_00") == set()                # el `_` se busca tal cual
    assert buscar("%25") == set()                      # y el `%` tambien
    cliente_nombre = cliente.get("/catalogos/clientes", headers=h).json()[0]["nombre"]
    assert otro.id in buscar(cliente_nombre.split()[0].lower())


def test_la_cartera_no_hace_una_consulta_por_servicio(cliente, sesion, datos):
    """Los equipos y sus dias vienen en la misma vuelta: la lista de
    ocho servicios cuesta lo mismo que la de dos."""
    h = sesion("consultor")
    for i in range(2):
        crear_servicio(cliente, h, datos, [_dia(datos, 50 + i)])
    _, con_dos = _contar(cliente, "GET", "/servicios?vivos=true", h)
    for i in range(6):
        crear_servicio(cliente, h, datos, [_dia(datos, 60 + i), _dia(datos, 70 + i)])
    r, con_ocho = _contar(cliente, "GET", "/servicios?vivos=true", h)
    assert len(r.json()) == 8
    assert con_ocho == con_dos <= 8, (con_dos, con_ocho)


def test_la_consola_pide_los_abiertos_sin_tope_y_busca_en_el_servidor():
    js = _js("consultor.js")
    assert 'api.get("/servicios?vivos=true")' in js
    assert "/servicios?vivos=false&q=" in js
    assert "/servicios?vivos=false&limite=" in js and "&antes_de=" in js


# ============================== 16 · un solo dia: el vuelo de salida

def test_con_un_solo_dia_el_vuelo_de_salida_no_recorre_la_presentacion(
        cliente, sesion, datos):
    """Transfer del hotel al aeropuerto: el vuelo de las 14:00 es el de
    salida. La presentacion se queda y la hoja lo dice como salida."""
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos,
                              [_dia(datos, 22, "transfer", "10:00:00", **ORIGEN)])
    j = servicio["equipos"][0]["jornadas"][0]
    r = cliente.patch(f"/operacion/jornadas/{j['id']}/vuelo", json={
        "vuelo_aerolinea": "Aeromexico", "vuelo_numero": "AM 57",
        "vuelo_hora": f"{j['fecha']}T14:00:00", "vuelo_tipo": "salida"},
        headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["presentacion_movida"] is False
    assert r.json()["presentacion"] == "10:00"
    vista = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                        headers=h).json()
    assert vista["dias"][0]["vuelo"]["tipo"] == "salida"
    assert vista["dias"][0]["llegada_equipo"]["contra_vuelo"] is False
    assert vista["dias"][0]["llegada_equipo"]["hora"] == "09:30"


def test_la_consola_ofrece_las_dos_casillas_con_un_solo_dia():
    """Con un dia --primero y ultimo a la vez-- se ofrecen «arranca» y
    «termina en aeropuerto», y el tipo del vuelo sale de cual se marca."""
    js = _js("servicio.js")
    assert 'const tipoVuelo = cual.primero ? "llegada" : "salida";' not in js
    assert "const soloUnDia = !!(cual.primero && cual.ultimo);" in js
    assert "terminaEnAeropuerto" in js
    assert "srv_un_solo_vuelo" in js


# ================================ 17 · asignar recursos y pagos, sin crecer

def test_asignar_recursos_no_crece_con_los_dias_ni_con_el_historial(
        cliente, sesion, datos):
    """Las recomendaciones del equipo costaban ~19 consultas por persona
    y por dia mas el historial de cada una (930 con 16 personas, tres
    dias y sesenta asignaciones). Ahora es un puno de consultas que no
    cambia con los dias del equipo ni con lo que la gente ya trabajo."""
    h = sesion("consultor")
    fd = datos["modalidades"]["full_day"]["id"]
    ruta = (lambda equipo_id:
            f"/servicios/equipos/{equipo_id}/recomendaciones"
            f"?perfil_id={datos['perfiles']['conductor_seguridad']['id']}"
            f"&categoria_id={datos['categorias']['suv_blindada']['id']}")
    un_dia = crear_servicio(cliente, h, datos, [_dia(datos, 5)])
    r, sin_historial = _contar(cliente, "GET", ruta(un_dia["equipos"][0]["id"]), h)
    assert r.status_code == 200, r.text
    assert sin_historial <= 40, sin_historial

    # Historial: 30 servicios con Juan y Luis, ya en el pasado.
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    for i in range(30):
        s = crear_servicio(cliente, h, datos, [jornada(manana(30 + i), fd)])
        j = s["equipos"][0]["jornadas"][0]["id"]
        asignar(cliente, h, j, persona_id=juan)
        asignar(cliente, h, j, persona_id=luis)

    tres_dias = crear_servicio(cliente, h, datos,
                               [_dia(datos, 5 + i) for i in range(3)])
    r, con_tres = _contar(cliente, "GET", ruta(tres_dias["equipos"][0]["id"]), h)
    assert r.status_code == 200, r.text
    assert r.json()["personal"]["disponibles"] or r.json()["personal"]["con_alerta"]
    _, otra_vez_uno = _contar(cliente, "GET", ruta(un_dia["equipos"][0]["id"]), h)
    assert con_tres == sin_historial == otra_vez_uno, (
        sin_historial, otra_vez_uno, con_tres)


def _facturable(cliente, sesion, datos, quien, cuenta, offset):
    """Un servicio de un dia trabajado por `quien` y ya enviado a
    finanzas: entra a la nomina."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos, [_dia(datos, offset)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(cliente, h, servicio,
                        datos["perfiles"]["conductor_seguridad"]["id"],
                        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=quien,
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    fin = ejecutar_jornada(cliente, sesion(cuenta), j)
    assert fin.status_code in (200, 201), fin.text
    r = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir", headers=h)
    assert r.status_code == 200, r.text
    r = cliente.post(f"/cierre/{r.json()['cierre_id']}/enviar-finanzas", headers=h)
    assert r.status_code == 200, r.text
    return servicio


def test_pagos_en_la_app_pide_solo_lo_de_esa_persona(cliente, sesion, datos):
    """«Pagos» recorria todas las jornadas terminadas del pais para
    quedarse con las de quien pregunta: lo que trabajaron los demas ya
    no le cuesta nada a Juan, y lo suyo sigue saliendo."""
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    _facturable(cliente, sesion, datos, juan, "juan", 900)
    r, antes = _contar(cliente, "GET", "/campo/mis-comisiones", sesion("juan"))
    assert r.status_code == 200, r.text
    assert len(r.json()["en_curso"]["dias"]) == 1

    for offset in (903, 906):
        _facturable(cliente, sesion, datos, luis, "luis", offset)
    r, despues = _contar(cliente, "GET", "/campo/mis-comisiones", sesion("juan"))
    assert len(r.json()["en_curso"]["dias"]) == 1
    assert despues == antes, (antes, despues)
    de_luis = cliente.get("/campo/mis-comisiones", headers=sesion("luis")).json()
    assert len(de_luis["en_curso"]["dias"]) == 2


def test_la_nomina_pendiente_se_pide_por_persona_a_la_base(cliente, sesion, datos, db):
    """El motor filtra por persona en la consulta, no en Python."""
    from app import nomina

    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    _facturable(cliente, sesion, datos, juan, "juan", 910)
    _facturable(cliente, sesion, datos, luis, "luis", 912)
    todos = nomina.jornadas_pendientes(db, datos["mx"]["id"])
    assert sorted(a.persona_id for _, a in todos) == sorted([juan, luis])
    solo_luis = nomina.jornadas_pendientes(db, datos["mx"]["id"], persona_id=luis)
    assert [a.persona_id for _, a in solo_luis] == [luis]
    assert nomina.jornadas_pendientes(db, datos["mx"]["id"], limite=1)


# ============================= 20 · eliminar un implantado recien capturado

def test_la_consola_ofrece_eliminar_en_los_mismos_estatus_que_el_servidor():
    """`solicitado` --como nace el implantado-- faltaba en la lista de la
    consola aunque el servidor ya lo aceptara."""
    js = _js("servicio.js")
    lista = re.search(r"const ANTES_DE_ARRANCAR = \[([^\]]*)\]", js).group(1)
    en_consola = set(re.findall(r'"([a-z_]+)"', lista))
    assert en_consola == {e.value for e in m.ANTES_DE_ARRANCAR}
    assert "solicitado" in en_consola


# ========================================= 21 · detalles del alta y la hoja

@pytest.fixture
def director_de_brasil(cliente, sesion, db):
    """Un director de operaciones con plaza en Sao Paulo, que se quita al
    terminar: las cuentas son catalogo."""
    h = sesion("admin")
    paises = cliente.get("/catalogos/paises", headers=h).json()
    br = next(p for p in paises if p["codigo"] == "BR")
    plazas = cliente.get("/catalogos/plazas?todas=true", headers=h).json()
    sp = next((p for p in plazas if p["pais_id"] == br["id"]), None)
    if not sp:
        sp = cliente.post("/catalogos/plazas", headers=h,
                          json={"pais_id": br["id"], "nombre": "Sao Paulo"}).json()
    persona = m.Persona(nombre="Director Brasil",
                        correo=f"{uuid.uuid4().hex[:8]}@revision-101.lat",
                        plaza_id=sp["id"], telefono="+55 11 99999 0000")
    db.add(persona)
    db.flush()
    usuario = m.Usuario(persona_id=persona.id, correo=persona.correo,
                        rol=m.Rol.DIRECTOR_OPERACIONES, activo=True)
    db.add(usuario)
    db.commit()
    yield {"pais": br, "plaza": sp, "persona_id": persona.id,
           "nombre": persona.nombre}
    db.execute(text("DELETE FROM usuario WHERE persona_id = :p"),
               {"p": persona.id})
    db.execute(text("DELETE FROM persona WHERE id = :p"), {"p": persona.id})
    db.commit()


def test_la_escalacion_de_la_hoja_toma_al_director_del_pais(
        cliente, sesion, datos, director_de_brasil):
    """La hoja de Sao Paulo sale con el director de Brasil; la de Mexico,
    con el de Mexico."""
    h = sesion("consultor")
    brasil = crear_servicio(
        cliente, h, datos, [_dia(datos, 24, **ORIGEN)],
        pais_id=director_de_brasil["pais"]["id"],
        plaza_id=director_de_brasil["plaza"]["id"])
    mexico = crear_servicio(cliente, h, datos, [_dia(datos, 24, **ORIGEN)])

    def director(servicio):
        vista = cliente.get(f"/task-sheets/servicio/{servicio['id']}/vista-previa",
                            headers=h).json()
        return next(n["nombre"] for n in vista["escalacion"] if n["nivel"] == 2)

    assert director(brasil) == director_de_brasil["nombre"]
    assert director(mexico) == "Jose Luis Pichardo"


def test_el_solicitante_se_reconoce_por_correo_exacto(cliente, sesion, datos):
    """`j_lopez@x.com` no es `jalopez@x.com`: el `_` era comodin y el
    servicio se ligaba al contacto equivocado."""
    h = sesion("consultor")
    r = cliente.post("/solicitantes", headers=h, json={
        "cliente_id": datos["cliente_id"], "nombre": "Jorge",
        "apellidos": "Lopez", "correo": "jalopez@x.com"})
    assert r.status_code == 201, r.text
    jalopez = r.json()["id"]

    servicio = crear_servicio(cliente, h, datos, [_dia(datos, 26)],
                              solicitante_nombre="Juana", solicitante_apellidos="Lopez",
                              solicitante_correo="j_lopez@x.com")
    assert servicio["solicitante_id"] != jalopez
    lista = cliente.get(f"/solicitantes?cliente_id={datos['cliente_id']}",
                        headers=h).json()
    assert {c["correo"] for c in lista} >= {"jalopez@x.com", "j_lopez@x.com"}

    # Y el mismo correo con otras mayusculas sigue siendo la misma persona.
    otro = crear_servicio(cliente, h, datos, [_dia(datos, 27)],
                          solicitante_nombre="Jorge", solicitante_apellidos="Lopez",
                          solicitante_correo="JALopez@x.com")
    assert otro["solicitante_id"] == jalopez


def test_la_encuesta_se_reapunta_con_la_hora_del_pais(cliente, sesion, datos, db,
                                                     director_de_brasil):
    """Una encuesta de Sao Paulo que vencio hace una hora alla todavia
    parece viva con el reloj de Mexico: no se re-apunta."""
    from app import reloj

    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos, [_dia(datos, 28)],
        pais_id=director_de_brasil["pais"]["id"],
        plaza_id=director_de_brasil["plaza"]["id"])
    fila = db.get(m.Servicio, servicio["id"])
    ahora_alla = reloj.ahora_del_servicio(db, fila)
    db.add(m.Encuesta(servicio_id=fila.id, tipo=m.TipoEncuesta.EJECUTIVO,
                      destinatario_nombre="Ingrid Halvorsen",
                      destinatario_correo="ejecutivo@cliente.com", idioma="en",
                      token=uuid.uuid4().hex, estatus=m.EstatusEncuesta.ENVIADA,
                      expira_en=ahora_alla - timedelta(hours=1)))
    db.commit()

    r = cliente.patch(f"/servicios/{servicio['id']}/contactos", json={
        "ejecutivo": {"nombre": "Ingrid", "apellidos": "Halvorsen",
                      "correo": "ingrid.nueva@cliente.com", "idioma": "en"}},
        headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["encuestas"] == 0
    db.expire_all()
    encuesta = db.query(m.Encuesta).filter_by(servicio_id=servicio["id"]).one()
    assert encuesta.destinatario_correo == "ejecutivo@cliente.com"


def test_los_textos_largos_del_alta_y_de_la_hoja_contestan_422(cliente, sesion, datos):
    """Lo que no cabe en su columna se rechaza con que corregir, en vez
    de reventar en la base."""
    h = sesion("consultor")

    def alta(**cambios):
        cuerpo = {
            "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
            "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
            "solicitante_nombre": "Patricia", "solicitante_apellidos": "Lundgren",
            "ejecutivo_nombre": "Ingrid", "ejecutivo_apellidos": "Halvorsen",
            "equipos": [{"clave": "EQ-1", "jornadas": [_dia(datos, 30)]}]}
        for llave, valor in cambios.items():
            if llave.startswith("jornada."):
                cuerpo["equipos"][0]["jornadas"][0][llave[8:]] = valor
            elif llave.startswith("equipo."):
                cuerpo["equipos"][0][llave[7:]] = valor
            else:
                cuerpo[llave] = valor
        return cliente.post("/servicios", json=cuerpo, headers=h)

    assert alta(**{"jornada.origen_direccion": "x" * 301}).status_code == 422
    assert alta(**{"jornada.vuelo_numero": "AM" * 20}).status_code == 422
    assert alta(**{"jornada.paradas": [{"lugar": "x" * 401}]}).status_code == 422
    assert alta(**{"jornada.agenda_resumen": "x" * 301}).status_code == 422
    assert alta(**{"equipo.descripcion": "x" * 201}).status_code == 422
    assert alta(**{"equipo.clave": "x" * 41}).status_code == 422
    servicio = alta().json()
    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "x" * 301}, headers=h)
    assert r.status_code == 422, r.text
    r = cliente.put(f"/servicios/{servicio['id']}/senal",
                    json={"imagen": "javascript:alert(1)"}, headers=h)
    assert r.status_code == 422, r.text
    r = cliente.post("/solicitantes", headers=h, json={
        "cliente_id": datos["cliente_id"], "nombre": "x" * 161})
    assert r.status_code == 422, r.text
    j = servicio["equipos"][0]["jornadas"][0]
    r = cliente.patch(f"/operacion/jornadas/{j['id']}/vuelo",
                      json={"vuelo_origen": "x" * 121}, headers=h)
    assert r.status_code == 422, r.text


def test_al_mover_solo_la_fecha_el_aviso_dice_que_cambio_la_fecha(
        cliente, sesion, datos, db, salieron):
    """Decia «ahora es a las 08:00 (antes 08:00)»: ahora dice la fecha de
    antes y la de ahora."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(cliente, h, datos, [_dia(datos, 32)])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)
    _telefono(db, juan)
    r = cliente.patch(f"/servicios/jornadas/{j['id']}",
                      json={"fecha": str(manana(33))}, headers=h)
    assert r.status_code == 200, r.text
    assert len(salieron) == 1, salieron
    carga = str(salieron[0]["data"])
    assert "fecha" in carga.lower()
    assert f"{manana(32):%d/%m}" in carga and f"{manana(33):%d/%m}" in carga
    assert "(antes 07:00)" not in carga


def test_la_consola_no_ofrece_cancelar_donde_el_servidor_lo_niega():
    """La lista de la consola es la misma `YA_NO_SE_CANCELA` del router."""
    from app.routers import servicios

    js = _js("servicio.js")
    lista = re.search(r"const YA_NO_SE_CANCELA = \[([^\]]*)\]", js).group(1)
    en_consola = set(re.findall(r'"([a-z_]+)"', lista))
    assert en_consola == {e.value for e in servicios.YA_NO_SE_CANCELA}
    assert "!YA_NO_SE_CANCELA.includes(servicio.estatus)" in js


def test_dos_consultores_no_asignan_al_mismo_recurso_a_la_vez(cliente, sesion, datos):
    """Ana esta a medio asignar a Juan --tiene su candado--; Beatriz lo
    asigna a otro servicio del mismo dia. La segunda espera a que la
    primera confirme, y entonces su revision ya encuentra a Juan ocupado."""
    from app.db import SessionLocal

    h = sesion("consultor")
    otra = sesion("consultor2")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    rol = datos["perfiles"]["conductor_seguridad"]["id"]
    a = crear_servicio(cliente, h, datos, [_dia(datos, 35, "transfer")])
    b = crear_servicio(cliente, h, datos, [_dia(datos, 35, "full_day")])
    ja = a["equipos"][0]["jornadas"][0]
    jb = b["equipos"][0]["jornadas"][0]

    # Ana, a medio camino: revisa a Juan y todavia no confirma.
    de_ana = SessionLocal()
    de_ana.execute(text("SELECT pg_advisory_xact_lock(:llave)"),
                   {"llave": zlib.crc32(f"asignar:persona:{juan}".encode())})

    resultado = {}

    def beatriz():
        resultado["r"] = cliente.post(
            f"/servicios/jornadas/{jb['id']}/asignar-personal",
            json={"persona_id": juan, "rol_id": rol, "forzar": True},
            headers=otra)

    hilo = threading.Thread(target=beatriz)
    hilo.start()
    hilo.join(2)
    try:
        assert hilo.is_alive(), "la segunda asignacion no espero al candado"
        # Ana confirma: Juan queda en A ese dia.
        de_ana.add(m.AsignacionPersonal(jornada_id=ja["id"], persona_id=juan,
                                        rol_id=rol))
        de_ana.commit()
    finally:
        de_ana.close()
    hilo.join(15)
    assert not hilo.is_alive()
    r = resultado["r"]
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["alertas"][0]["servicio"] == a["folio"]


def test_la_imagen_de_la_senal_se_escapa_en_la_hoja(cliente, sesion, datos, db):
    """Lo que haya en el campo sale escapado en el `src`: no se puede
    meter HTML en la hoja que abren los demas."""
    from app import tasksheet as motor
    from app import tasksheet_html

    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [_dia(datos, 36, **ORIGEN)])
    fila = db.get(m.Servicio, servicio["id"])
    fila.senal_imagen = 'x" onerror="alert(1)'
    db.commit()
    hoja = tasksheet_html.render(motor.armar(db, servicio["equipos"][0]["id"]),
                                 1, None, "es")
    assert 'onerror="alert(1)"' not in hoja
    assert 'src="x&quot; onerror=&quot;alert(1)"' in hoja

# -*- coding: utf-8 -*-
"""Seccion 107: el fin es cuando el ejecutivo corta; la entrega de la
unidad va despues, con sus 24 horas.

Decision de Salvador (30 sep), que quita el candado duro del 18 de
septiembre: "el servicio debe terminar al momento que el ejecutivo corta
el servicio... ya lo que tarde el conductor en llegar a la oficina y
entregar la unidad es otro proceso que no debe afectar los tiempos del
dia". Sin candado duro.

Lo que se prueba: el fin ya no se rechaza por la unidad; con el fin
nace la entrega pendiente (24 horas, aviso al telefono); la revision de
entrega la cierra; la app la trae arriba con su reloj; la central la
lista; al vencer avisa una sola vez a la persona, al consultor y a
direccion de operaciones; el cierre la reclama hasta que se entregue o
se registre sin revision con la razon; y donde no debe estorbar --el dia
de en medio, el copiloto-- sigue sin estorbar.
"""
import json
import re
import os
from datetime import datetime, timedelta

import pytest

from app import models as m
from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, jornada, manana, marcar, revisar_unidad,
                    KM_ENTREGA, KM_RECEPCION)

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


def _telefono(db, persona_id, endpoint):
    db.add(m.SuscripcionPush(persona_id=persona_id, endpoint=endpoint,
                             p256dh="clave-publica", auth="secreto"))
    db.commit()


def _fin(cliente, headers, j):
    """El dia completo hasta el fin de servicio, a su hora programada."""
    inicio = datetime.fromisoformat(j["inicio_programado"])
    fin = datetime.fromisoformat(j["fin_programado"])
    marcar(cliente, headers, j["id"], "llegada_origen",
           inicio - timedelta(minutes=10))
    marcar(cliente, headers, j["id"], "contacto_ejecutivo", inicio)
    return marcar(cliente, headers, j["id"], "fin_servicio", fin,
                  ubicacion={"lat": 19.4326, "lon": -99.1332})


def _servicio(cliente, sesion, datos, dias=1, desde=60, quien="Juan Ramirez",
              cotizado=False):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [
        jornada(manana(desde + i), datos["modalidades"]["full_day"]["id"])
        for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    if cotizado:
        cotizar_y_autorizar(
            cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
            datos["categorias"]["suv_blindada"]["id"])
    for j in servicio["equipos"][0]["jornadas"]:
        for r in asignar(cliente, h, j["id"],
                         persona_id=datos["personal"][quien]["id"],
                         vehiculo_id=datos["suburban"]["id"]):
            assert r.status_code == 200, r.text
        configurar_origen(cliente, h, j["id"])
    return servicio


def _pendiente(db, servicio_id, vehiculo_id):
    return (db.query(m.EntregaPendiente)
            .filter_by(servicio_id=servicio_id, vehiculo_id=vehiculo_id)
            .first())


# ====================================== el fin ya no espera a la entrega

def test_el_fin_se_marca_con_la_unidad_sin_entregar_y_abre_la_entrega(
        cliente, sesion, datos, db, salieron):
    """Un dia, una unidad recibida y sin entregar: el fin entra, las
    horas se cortan a esa hora, y nace la entrega pendiente con sus 24
    horas y su aviso al telefono."""
    servicio = _servicio(cliente, sesion, datos, desde=60)
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    h = sesion("juan")
    _telefono(db, juan, "https://push.example/107-a")
    assert revisar_unidad(cliente, h, servicio["id"], datos["suburban"]["id"],
                          "recibe", KM_RECEPCION).status_code == 201

    r = _fin(cliente, h, j)
    assert r.status_code == 200, r.text
    fin = datetime.fromisoformat(j["fin_programado"])
    cuerpo = r.json()
    assert len(cuerpo["entregas_pendientes"]) == 1
    assert cuerpo["entregas_pendientes"][0]["placa"] == datos["suburban"]["placa"]

    fila = db.get(m.Jornada, j["id"])
    db.refresh(fila)
    assert fila.estatus == m.EstatusJornada.TERMINADA
    assert fila.fin_real == fin

    pend = _pendiente(db, servicio["id"], datos["suburban"]["id"])
    assert pend is not None and pend.cerrada_en is None
    assert pend.persona_id == juan
    assert pend.abierta_en == fin
    assert pend.vence_en == fin + timedelta(hours=24)

    # El aviso: que falta entregar la unidad, y hasta cuando.
    assert len(salieron) == 1, salieron
    texto = str(salieron[0]["data"])
    assert datos["suburban"]["placa"] in texto
    assert "cinco fotos" in texto

    # El servicio de un dia ya termino: el plazo de los viaticos corre.
    estado = cliente.get(f"/servicios/{servicio['id']}",
                         headers=sesion("consultor")).json()
    assert estado["estatus"] == "terminado"


def test_la_revision_de_entrega_cierra_la_pendiente(cliente, sesion, datos, db):
    servicio = _servicio(cliente, sesion, datos, desde=63)
    j = servicio["equipos"][0]["jornadas"][0]
    h = sesion("juan")
    assert revisar_unidad(cliente, h, servicio["id"], datos["suburban"]["id"],
                          "recibe", KM_RECEPCION).status_code == 201
    assert _fin(cliente, h, j).status_code == 200

    fin = datetime.fromisoformat(j["fin_programado"])
    dia = cliente.get(f"/campo/mi-dia?ahora={(fin + timedelta(hours=2)).isoformat()}",
                      headers=h).json()
    assert len(dia["entregas_pendientes"]) == 1
    e = dia["entregas_pendientes"][0]
    assert e["placa"] == datos["suburban"]["placa"]
    assert e["sin_recepcion"] is False
    assert e["vencido"] is False
    assert 21 * 60 < e["minutos"] <= 22 * 60
    assert e["limite"] == (fin + timedelta(hours=24)).isoformat()

    r = revisar_unidad(cliente, h, servicio["id"], datos["suburban"]["id"],
                       "entrega", KM_ENTREGA)
    assert r.status_code == 201, r.text
    assert r.json()["entrega_pendiente_cerrada"] is True

    pend = _pendiente(db, servicio["id"], datos["suburban"]["id"])
    db.refresh(pend)
    assert pend.cerrada_en is not None and pend.revision_id == r.json()["revision_id"]
    assert pend.sin_revision is False
    dia = cliente.get(f"/campo/mi-dia?ahora={(fin + timedelta(hours=3)).isoformat()}",
                      headers=h).json()
    assert dia["entregas_pendientes"] == []


def test_sin_la_recepcion_la_app_lo_manda_con_su_consultor(cliente, sesion,
                                                          datos, salieron):
    """La unidad que nunca se reviso al recibirla tambien cierra su dia;
    la entrega queda pendiente y la app dice que hable con su consultor,
    porque sin recepcion no hay como guardar la entrega."""
    servicio = _servicio(cliente, sesion, datos, desde=66)
    j = servicio["equipos"][0]["jornadas"][0]
    h = sesion("juan")
    assert _fin(cliente, h, j).status_code == 200
    fin = datetime.fromisoformat(j["fin_programado"])
    dia = cliente.get(f"/campo/mi-dia?ahora={(fin + timedelta(hours=1)).isoformat()}",
                      headers=h).json()
    assert dia["entregas_pendientes"][0]["sin_recepcion"] is True


# ================================================== donde NO debe estorbar

def test_el_dia_de_en_medio_no_abre_nada(cliente, sesion, datos, db):
    """La misma camioneta tres dias: solo el ultimo deja la entrega
    pendiente."""
    servicio = _servicio(cliente, sesion, datos, dias=3, desde=70)
    jornadas = servicio["equipos"][0]["jornadas"]
    h = sesion("juan")
    assert revisar_unidad(cliente, h, servicio["id"], datos["suburban"]["id"],
                          "recibe", KM_RECEPCION).status_code == 201
    assert _fin(cliente, h, jornadas[0]).status_code == 200
    assert _pendiente(db, servicio["id"], datos["suburban"]["id"]) is None
    assert _fin(cliente, h, jornadas[1]).status_code == 200
    assert _pendiente(db, servicio["id"], datos["suburban"]["id"]) is None
    assert _fin(cliente, h, jornadas[2]).status_code == 200
    assert _pendiente(db, servicio["id"], datos["suburban"]["id"]) is not None


def test_con_dos_en_el_equipo_la_entrega_es_una_y_de_quien_trae_la_unidad(
        cliente, sesion, datos, db):
    """Juan conduce y Luis va de copiloto con dos unidades: la pendiente
    es una por unidad y responde el que la trae asignada. El copiloto
    cierra su dia sin que nada le pida nada."""
    h = sesion("consultor")
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"]
                and v["plaza_id"] == datos["suburban"]["plaza_id"])
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(75), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    for persona in (juan, luis):
        for r in asignar(cliente, h, j["id"], persona_id=persona):
            assert r.status_code == 200, r.text
    for unidad in (datos["suburban"]["id"], otra["id"]):
        for r in asignar(cliente, h, j["id"], vehiculo_id=unidad):
            assert r.status_code == 200, r.text
    assert cliente.patch(
        f"/servicios/jornadas/{j['id']}/personal/{juan}/unidad",
        json={"vehiculo_id": datos["suburban"]["id"]},
        headers=h).status_code == 200
    configurar_origen(cliente, h, j["id"])

    r = _fin(cliente, sesion("luis"), j)
    assert r.status_code == 200, r.text
    assert r.json()["entregas_pendientes"] == []
    r = _fin(cliente, sesion("juan"), j)
    assert r.status_code == 200, r.text
    assert [e["placa"] for e in r.json()["entregas_pendientes"]] == [
        datos["suburban"]["placa"]]
    pend = _pendiente(db, servicio["id"], datos["suburban"]["id"])
    assert pend.persona_id == juan
    fin = datetime.fromisoformat(j["fin_programado"])
    luego = (fin + timedelta(hours=1)).isoformat()
    assert cliente.get(f"/campo/mi-dia?ahora={luego}",
                       headers=sesion("luis")).json()["entregas_pendientes"] == []
    assert len(cliente.get(f"/campo/mi-dia?ahora={luego}",
                           headers=sesion("juan")).json()["entregas_pendientes"]) == 1


# ================================ la central, el vencimiento y el cierre

def test_la_central_la_lista_y_al_vencer_avisa_una_sola_vez(
        cliente, sesion, datos, db, salieron):
    from app import entregas
    servicio = _servicio(cliente, sesion, datos, desde=80)
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    ana = datos["personal"]["Ana Solis"]["id"]
    h = sesion("juan")
    _telefono(db, juan, "https://push.example/107-b")
    _telefono(db, ana, "https://push.example/107-c")
    assert revisar_unidad(cliente, h, servicio["id"], datos["suburban"]["id"],
                          "recibe", KM_RECEPCION).status_code == 201
    assert _fin(cliente, h, j).status_code == 200
    fin = datetime.fromisoformat(j["fin_programado"])
    del salieron[:]

    antes = (fin + timedelta(hours=5)).isoformat()
    lista = cliente.get(f"/operacion/entregas-pendientes?ahora={antes}",
                        headers=sesion("central")).json()
    assert lista["cuantos"] == 1 and lista["vencidas"] == 0
    assert lista["entregas"][0]["persona"] == "Juan Ramirez"
    assert lista["entregas"][0]["folio"] == servicio["folio"]

    # Antes de vencer, el barrido no manda nada.
    assert entregas.avisar_vencidas(db, fin + timedelta(hours=23)) == []
    assert salieron == []

    # Vencida: a Juan, a Ana (correo y telefono) y a direccion de
    # operaciones; una sola vez.
    avisadas = entregas.avisar_vencidas(db, fin + timedelta(hours=25))
    assert avisadas == [datos["suburban"]["placa"]]
    despues = (fin + timedelta(hours=25)).isoformat()
    lista = cliente.get(f"/operacion/entregas-pendientes?ahora={despues}",
                        headers=sesion("central")).json()
    assert lista["vencidas"] == 1 and lista["entregas"][0]["vencido"] is True
    textos = [json.loads(x["data"]) for x in salieron]
    assert any("Entrégala hoy" in x["cuerpo"] for x in textos), textos
    assert any("unidad sin entregar" in x["titulo"] for x in textos), textos
    correos = (db.query(m.Notificacion)
               .filter_by(servicio_id=servicio["id"], canal=m.Canal.CORREO)
               .filter(m.Notificacion.asunto.like("%no se entregó a tiempo%"))
               .all())
    assert len(correos) >= 1
    assert any(c.correo == "ana.solis@centauro.lat" for c in correos)
    assert entregas.avisar_vencidas(db, fin + timedelta(hours=26)) == []


def test_el_cierre_la_reclama_hasta_que_se_registre_sin_revision(
        cliente, sesion, datos, db):
    """Grave en la revision del cierre mientras siga abierta; el
    consultor la da por entregada sin revision con la razon y queda
    informativa, con quien y por que. Una razon corta no vale."""
    servicio = _servicio(cliente, sesion, datos, desde=85, cotizado=True)
    j = servicio["equipos"][0]["jornadas"][0]
    h = sesion("juan")
    assert revisar_unidad(cliente, h, servicio["id"], datos["suburban"]["id"],
                          "recibe", KM_RECEPCION).status_code == 201
    assert _fin(cliente, h, j).status_code == 200
    fin = datetime.fromisoformat(j["fin_programado"])
    luego = (fin + timedelta(hours=30)).isoformat()

    rev = cliente.get(f"/cierre/servicio/{servicio['id']}/revision?ahora={luego}",
                      headers=sesion("consultor")).json()
    graves = [o for o in rev["observaciones"] if o.get("clave") == "entrega_pendiente"]
    assert len(graves) == 1 and graves[0]["nivel"] == "corregir"
    assert graves[0]["datos"]["placa"] == datos["suburban"]["placa"]
    assert graves[0]["datos"]["vencido"] is True

    # La ficha del servicio la trae con su reloj.
    unidades = cliente.get(f"/servicios/{servicio['id']}/revisiones",
                           headers=sesion("consultor")).json()["unidades"]
    pend = next(u for u in unidades
                if u["vehiculo_id"] == datos["suburban"]["id"])["entrega_pendiente"]
    assert pend and pend["cerrada_en"] is None
    entrega_id = pend["entrega_id"]

    r = cliente.post(f"/operacion/entregas-pendientes/{entrega_id}/sin-revision",
                     json={"justificacion": "corta"}, headers=sesion("consultor"))
    assert r.status_code == 400, r.text
    # Otro consultor, sin corregir marcas, no puede.
    r = cliente.post(f"/operacion/entregas-pendientes/{entrega_id}/sin-revision",
                     json={"justificacion": "La unidad se quedo en el taller del cliente"},
                     headers=sesion("consultor2"))
    assert r.status_code == 403, r.text
    r = cliente.post(f"/operacion/entregas-pendientes/{entrega_id}/sin-revision",
                     json={"justificacion": "La unidad se quedo en el taller del cliente"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["sin_revision"] is True
    assert r.json()["justificada_por"] == "Ana Solis"

    rev = cliente.get(f"/cierre/servicio/{servicio['id']}/revision?ahora={luego}",
                      headers=sesion("consultor")).json()
    assert not [o for o in rev["observaciones"] if o.get("clave") == "entrega_pendiente"]
    info = [o for o in rev["observaciones"] if o.get("clave") == "entrega_sin_revision"]
    assert len(info) == 1 and info[0]["nivel"] == "informativo"
    assert "taller del cliente" in info[0]["mensaje"]
    # Dos veces no.
    r = cliente.post(f"/operacion/entregas-pendientes/{entrega_id}/sin-revision",
                     json={"justificacion": "La unidad se quedo en el taller del cliente"},
                     headers=sesion("central"))
    assert r.status_code == 409, r.text
    # Y en la ficha queda dicho.
    unidades = cliente.get(f"/servicios/{servicio['id']}/revisiones",
                           headers=sesion("consultor")).json()["unidades"]
    pend = next(u for u in unidades
                if u["vehiculo_id"] == datos["suburban"]["id"])["entrega_pendiente"]
    assert pend["sin_revision"] is True and "taller" in pend["justificacion"]


def test_el_dia_cerrado_a_mano_tambien_deja_la_entrega_pendiente(
        cliente, sesion, datos, db):
    """Nadie marco el fin y la central cerro el dia: la unidad salio
    igual, y el plazo corre desde la firma de la central."""
    servicio = _servicio(cliente, sesion, datos, desde=90)
    j = servicio["equipos"][0]["jornadas"][0]
    h = sesion("juan")
    assert revisar_unidad(cliente, h, servicio["id"], datos["suburban"]["id"],
                          "recibe", KM_RECEPCION).status_code == 201
    inicio = datetime.fromisoformat(j["inicio_programado"])
    marcar(cliente, h, j["id"], "llegada_origen", inicio - timedelta(minutes=10))
    fin = datetime.fromisoformat(j["fin_programado"])
    firma = fin + timedelta(hours=14)
    r = cliente.post(f"/operacion/jornadas/{j['id']}/cerrar-a-mano?ahora={firma.isoformat()}",
                     json={"justificacion": "El telefono se quedo sin bateria",
                           "fin_real": fin.isoformat()},
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    pend = _pendiente(db, servicio["id"], datos["suburban"]["id"])
    assert pend is not None and pend.persona_id == datos["personal"]["Juan Ramirez"]["id"]
    assert pend.vence_en == firma + timedelta(hours=24)


# ================================================ lo que dice la pantalla

def test_la_app_ofrece_el_fin_y_pone_la_entrega_arriba():
    app = _js("campo/app.js")
    assert "finDespues" not in app
    assert "} else if (paso) {" in app
    assert "function tarjetaEntrega(e)" in app
    assert "datos.entregas_pendientes" in app
    assert 't("cmp_ent_hoy")' in app
    assert "cmp_sin_esto_fin" not in app and "cmp_fin_despues_de_entregar" not in app
    idioma = _js("idioma.js")
    for clave in ("cmp_ent_titulo", "cmp_ent_pie", "cmp_ent_hoy", "cmp_ent_cerrado",
                  "ent_titulo", "ent_sin_revision", "ent_pastilla_vencida",
                  "cie_o_entrega_pendiente", "ay_cen_entregas_para"):
        assert idioma.count(f"    {clave}:") == 3, clave
    assert "async function bandaEntregas" in _js("central.js")
    assert "function entregaSinRevision(pend)" in _js("servicio.js")
    assert '"entrega_pendiente"' in _js("cierre.js")
    # La v22 (30 sep, entrar con huella) vino despues: basta con que la
    # version haya subido de la v20.
    assert re.search(r'CACHE = "centauro-campo-v(2[1-9]|[3-9]\d)"', _js("campo/sw.js"))

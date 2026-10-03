"""Logistica, bloque 2: la jornada de los operadores (seccion 151).

Cada operador marca su inicio de jornada en LG Connect dentro de la
geocerca del patio (300 m). Esa marca dice quien esta libre para asignar
ese dia y cuenta los dias activos de lunes a viernes para el bono de
movilidad: 5 de 5. Fuera de la geocerca la marca queda por validar y la
Central la valida o la rechaza con su justificacion.

Decision de Salvador, 3 oct: el dia que amanece en carretera cuenta como
activo; mientras los viajes sigan en Tango, el «en viaje» se marca a mano.
"""
from datetime import timedelta

import pytest
from fastapi import HTTPException

from ayudas_lg import (DENTRO, FUERA, admin, calidad, central, db, hoy,  # noqa: F401
                       karla, licencia, logistica, operador)
from app import lg_disponibilidad as dispo
from app import lg_jornada as jo
from app import models as m

PDF = b"%PDF-1.4\n%licencia\n"


def _marcar(db, o, punto, nota=None, fecha=None):
    j = jo.marcar(db, o, punto[0], punto[1], 12, nota, fecha)
    db.commit()
    return j


# ====================================================== la marca

def test_dentro_del_patio_la_marca_vale(db):
    o = operador(db)
    j = _marcar(db, o, DENTRO)
    assert (j.estado, j.dentro, j.patio.nombre) == ("valida", True, "Base Cuautitlán")
    assert 100 <= j.distancia_m <= 125
    # Una por dia.
    with pytest.raises(HTTPException) as error:
        _marcar(db, o, DENTRO)
    assert error.value.status_code == 409
    assert error.value.detail["codigo"] == "ya_marcada"


def test_fuera_del_patio_pide_donde_y_espera_a_la_central(cliente, karla, central, db):
    o = operador(db)
    with pytest.raises(HTTPException) as error:
        _marcar(db, o, FUERA)
    assert error.value.status_code == 409
    assert error.value.detail["codigo"] == "fuera_del_patio"
    assert 1900 <= error.value.detail["distancia_m"] <= 2100
    db.rollback()
    j = _marcar(db, o, FUERA, nota="en la caseta de la entrada norte")
    assert (j.estado, j.dentro) == ("por_validar", False)
    pendientes = cliente.get("/lg/jornada/por-validar", headers=karla).json()
    assert [x["operador"]["nombre"] for x in pendientes["marcas"]] == ["Pedro Lopez"]
    assert pendientes["puede"]["validar"] is False
    # La gerencia no valida: la Central si, con su justificacion.
    datos = {"validar": True, "justificacion": "llamé al patio y el vigilante lo confirma"}
    assert cliente.post(f"/lg/jornada/marcas/{j.id}/revisar", headers=karla,
                        json=datos).status_code == 403
    assert cliente.post(f"/lg/jornada/marcas/{j.id}/revisar", headers=central,
                        json={"validar": True, "justificacion": "ok"}).status_code == 400
    r = cliente.post(f"/lg/jornada/marcas/{j.id}/revisar", headers=central, json=datos)
    assert r.status_code == 200, r.text
    assert r.json()["marcas"] == []
    db.expire_all()
    j = db.get(m.LgJornada, j.id)
    assert j.estado == "valida" and j.justificacion == datos["justificacion"]
    assert j.revisada_por.nombre == "Sofia Navarro"
    # Lo revisado no se vuelve a revisar.
    assert cliente.post(f"/lg/jornada/marcas/{j.id}/revisar", headers=central,
                        json=datos).status_code == 409
    filas = cliente.get("/lg/jornada/bitacora", headers=karla).json()["filas"]
    assert filas[0]["que"].startswith("Pedro Lopez: marca del ")
    assert filas[0]["que"].endswith(" validada · «llamé al patio y el vigilante lo confirma»")


def test_sin_punto_en_el_patio_toda_marca_espera(db):
    """Mientras sistema y calidad no ponga el punto del patio no se puede
    medir: la marca entra, por validar."""
    patio = db.query(m.LgPatio).one()
    patio.lat = patio.lon = None
    db.commit()
    j = _marcar(db, operador(db), DENTRO)
    assert (j.estado, j.patio_id, j.distancia_m) == ("por_validar", None, None)


# ====================================================== el dia

def test_el_dia_dice_quien_se_presento(cliente, karla, central, calidad, sesion, db):
    presente = operador(db, "Ana Ruiz", "ana.ruiz@gmail.com")
    licencia(db, presente)
    espera = operador(db, "Beto Sanz", "beto.sanz@gmail.com")
    viaje = operador(db, "Ciro Paz", "ciro.paz@gmail.com")
    rechazado = operador(db, "Dora Gil", "dora.gil@gmail.com")
    operador(db, "Eloy Mora", "eloy.mora@gmail.com")              # no llego
    _marcar(db, presente, DENTRO)
    _marcar(db, espera, FUERA, nota="en la gasolinera de enfrente")
    j = _marcar(db, rechazado, FUERA, nota="en mi casa")
    assert cliente.post(f"/lg/jornada/marcas/{j.id}/revisar", headers=central,
                        json={"validar": False,
                              "justificacion": "el GPS lo ubica a 2 km del patio"}
                        ).status_code == 200
    r = cliente.post(f"/lg/jornada/operadores/{viaje.id}/en-viaje", headers=karla,
                     json={"hasta": (hoy() + timedelta(days=2)).isoformat()})
    assert r.status_code == 200, r.text
    d = cliente.get("/lg/jornada/dia", headers=karla).json()
    assert d["cifras"] == {"operadores": 5, "presentes": 1, "en_viaje": 1,
                           "por_validar": 1, "rechazadas": 1, "ausentes": 1}
    por_nombre = {x["nombre"]: x for x in d["operadores"]}
    assert por_nombre["Ana Ruiz"]["disponibilidad"]["estado"] == "libre"
    assert por_nombre["Beto Sanz"]["disponibilidad"]["motivos"][0]["clave"] == \
        "jornada_por_validar"
    assert por_nombre["Ciro Paz"]["situacion"] == "en_viaje"
    assert por_nombre["Dora Gil"]["situacion"] == "rechazada"
    assert {x["clave"] for x in por_nombre["Eloy Mora"]["disponibilidad"]["motivos"]} == {
        "sin_jornada", "licencia_falta"}
    assert por_nombre["Ana Ruiz"]["antiguedad"]["anios"] >= 6
    assert d["puede"] == {"validar": False, "operadores": True, "en_viaje": True}
    assert d["por_validar"] == 1
    # La Central y sistema y calidad la ven; Proteccion Ejecutiva no.
    assert cliente.get("/lg/jornada/dia", headers=central).json()["puede"]["validar"] is True
    assert cliente.get("/lg/jornada/dia", headers=calidad).status_code == 200
    for quien in ("consultor", "finanzas", "juan"):
        assert cliente.get("/lg/jornada/dia", headers=sesion(quien)).status_code == 403


def test_en_viaje_a_mano(cliente, karla, central, db):
    o = operador(db)
    url = f"/lg/jornada/operadores/{o.id}/en-viaje"
    assert cliente.post(url, headers=karla, json={
        "desde": hoy().isoformat(),
        "hasta": (hoy() - timedelta(days=1)).isoformat()}).status_code == 400
    assert cliente.post(url, headers=karla, json={
        "hasta": (hoy() + timedelta(days=61)).isoformat()}).status_code == 400
    assert cliente.post(url, headers=central, json={
        "hasta": (hoy() + timedelta(days=2)).isoformat()}).status_code == 403
    r = cliente.post(url, headers=karla, json={"hasta": (hoy() + timedelta(days=2)).isoformat()})
    yo = next(x for x in r.json()["operadores"] if x["id"] == o.id)
    assert yo["en_viaje"] == {"desde": hoy().isoformat(),
                              "hasta": (hoy() + timedelta(days=2)).isoformat()}
    # Encimado con el que ya tiene, no.
    assert cliente.post(url, headers=karla, json={
        "desde": (hoy() + timedelta(days=1)).isoformat(),
        "hasta": (hoy() + timedelta(days=4)).isoformat()}).status_code == 409
    # «Ya regreso» el mismo dia que salio: el viaje se quita.
    r = cliente.post(url, headers=karla, json={})
    assert next(x for x in r.json()["operadores"] if x["id"] == o.id)["en_viaje"] is None


def test_dos_viajes_en_la_semana_cuentan_los_dos(cliente, karla, db):
    """Cada viaje a mano es su renglon: marcar el segundo no le borra al
    primero sus dias. Y «ya regreso» termina el viaje ayer: hoy puede
    salir a otro."""
    o = operador(db)
    lunes = jo.lunes_de(hoy()) - timedelta(days=7)
    url = f"/lg/jornada/operadores/{o.id}/en-viaje"
    assert cliente.post(url, headers=karla, json={
        "desde": lunes.isoformat(),
        "hasta": (lunes + timedelta(days=1)).isoformat()}).status_code == 200
    assert cliente.post(url, headers=karla, json={
        "desde": (lunes + timedelta(days=3)).isoformat(),
        "hasta": (lunes + timedelta(days=4)).isoformat()}).status_code == 200
    _marcar(db, o, DENTRO, fecha=lunes + timedelta(days=2))
    s = jo.semana(db, lunes)
    assert [x["codigo"] for x in s["operadores"][0]["dias"][:5]] == [
        "viaje", "viaje", "marca", "viaje", "viaje"]
    assert s["operadores"][0]["bono"] == "si"
    # Uno en curso: salio antier, regresa en tres dias; ya volvio.
    assert cliente.post(url, headers=karla, json={
        "desde": (hoy() - timedelta(days=2)).isoformat(),
        "hasta": (hoy() + timedelta(days=3)).isoformat()}).status_code == 200
    assert dispo.operador(db, o.id)["motivos"][0]["clave"] == "en_viaje"
    cliente.post(url, headers=karla, json={})
    db.expire_all()
    v = db.query(m.LgViajeManual).filter_by(operador_id=o.id).order_by(m.LgViajeManual.id.desc()).first()
    assert (v.desde, v.hasta) == (hoy() - timedelta(days=2), hoy() - timedelta(days=1))
    assert "en_viaje" not in [x["clave"] for x in dispo.operador(db, o.id)["motivos"]]
    filas = cliente.get("/lg/jornada/bitacora", headers=karla).json()["filas"]
    assert filas[0]["que"].startswith("Pedro Lopez: ya regresó de viaje (")
    assert filas[1]["que"].startswith("Pedro Lopez: en viaje del ")


# ====================================================== la semana y el bono

def test_cinco_de_cinco_con_un_dia_en_carretera(db):
    lunes = jo.lunes_de(hoy()) - timedelta(days=7)          # la semana pasada
    completo = operador(db, "Ana Ruiz", "ana.ruiz@gmail.com")
    cuatro = operador(db, "Beto Sanz", "beto.sanz@gmail.com")
    pendiente = operador(db, "Ciro Paz", "ciro.paz@gmail.com")
    for i in range(4):
        _marcar(db, completo, DENTRO, fecha=lunes + timedelta(days=i))
        _marcar(db, cuatro, DENTRO, fecha=lunes + timedelta(days=i))
        _marcar(db, pendiente, DENTRO, fecha=lunes + timedelta(days=i))
    # El viernes Ana amanecio en carretera; Ciro marco fuera y espera.
    db.add(m.LgViajeManual(operador_id=completo.id, desde=lunes + timedelta(days=4),
                           hasta=lunes + timedelta(days=4)))
    db.commit()
    _marcar(db, pendiente, FUERA, nota="me mandaron a la bodega de Tultitlán",
            fecha=lunes + timedelta(days=4))
    s = jo.semana(db, lunes)
    por_nombre = {x["nombre"]: x for x in s["operadores"]}
    assert [x["codigo"] for x in por_nombre["Ana Ruiz"]["dias"]] == [
        "marca", "marca", "marca", "marca", "viaje", "libre", "libre"]
    assert (por_nombre["Ana Ruiz"]["activos"], por_nombre["Ana Ruiz"]["bono"]) == (5, "si")
    assert [x["codigo"] for x in por_nombre["Beto Sanz"]["dias"]][4] == "falta"
    assert (por_nombre["Beto Sanz"]["activos"], por_nombre["Beto Sanz"]["bono"]) == (4, "no")
    assert (por_nombre["Ciro Paz"]["activos"], por_nombre["Ciro Paz"]["bono"]) == (
        4, "pendiente")
    assert jo.dias_activos(db, completo.id, lunes) == 5
    assert jo.dias_activos(db, cuatro.id, lunes + timedelta(days=2)) == 4


def test_la_semana_en_curso_espera_a_los_dias_que_faltan(cliente, karla, db):
    o = operador(db)
    _marcar(db, o, DENTRO)
    s = cliente.get("/lg/jornada/semana", headers=karla).json()
    dias = s["operadores"][0]["dias"]
    i = hoy().weekday()
    assert dias[i]["codigo"] == "marca"
    assert all(d["codigo"] == "pendiente" for d in dias[i + 1:])
    # Los dias de la semana que ya pasaron sin marca son faltas.
    assert all(d["codigo"] == "falta" for d in dias[:min(i, 5)])


# ====================================================== la licencia

def test_la_licencia_se_captura_con_su_archivo(cliente, karla, db):
    o = operador(db)
    r = cliente.post(f"/lg/jornada/operadores/{o.id}/licencia", headers=karla,
                     data={"vence_en": (hoy() + timedelta(days=20)).isoformat(),
                           "detalle": "Tipo E", "folio": "LF-99812"},
                     files={"archivo": ("licencia.pdf", PDF, "application/pdf")})
    assert r.status_code == 201, r.text
    yo = r.json()["operadores"][0]
    assert yo["licencia"]["estado"] == "por_vencer"
    assert (yo["licencia"]["detalle"], yo["licencia"]["folio"]) == ("Tipo E", "LF-99812")
    archivo = cliente.get(f"/lg/flota/archivos/{yo['licencia']['archivo_id']}", headers=karla)
    assert archivo.content == PDF
    assert yo["app"] == "sin_acceso"
    filas = cliente.get("/lg/jornada/bitacora", headers=karla).json()["filas"]
    assert filas[0]["que"].startswith("Pedro Lopez: licencia federal · vence ")


def test_leer_operadores_sin_odoo_lo_dice(cliente, karla):
    r = cliente.post("/lg/jornada/odoo", headers=karla, json={"aplicar": False})
    assert r.status_code == 409
    assert "Odoo no está conectado" in r.json()["detail"]["mensaje"]

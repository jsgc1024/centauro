# -*- coding: utf-8 -*-
"""La flota y el taller, leidos de Odoo (seccion 52 de la bitacora).

Contra un Odoo de mentiras, en memoria: ninguna prueba sale a la red. La
flota se vacia y se vuelve a sembrar antes de cada prueba (conftest), asi
que las unidades que estas pruebas dan de alta no se quedan.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from ayudas import PIXEL, asignar, crear_servicio, jornada, manana
from app import models as m
from app import odoo_api, odoo_flota

ODOO0 = 8_000_000
ETIQUETAS = {1: "pe", 2: "Logística", 3: "PROTECCIÓN EJECUTIVA"}


def unidad(n, **cambios):
    u = {"id": ODOO0 + n, "license_plate": f"T{n:02d}ODO",
         "category_id": [9, "MINIVAN"], "location": "Ciudad de México",
         "model_id": [4, "Toyota/SIENNA XSE"], "color": "Blanco",
         "model_year": "2023", "tag_ids": [1],
         "write_date": "2026-01-01 10:00:00", "active": True}
    u.update(cambios)
    return u


def taller(n, dueno, **cambios):
    r = {"id": 9_000_000 + n, "vehicle_id": [ODOO0 + dueno, "x"],
         "service_type_id": [3, "Correctivo"], "state": "running",
         odoo_flota.ENTRADA: str(manana(2)), odoo_flota.SALIDA: str(manana(5)),
         "vendor_id": [7, "Taller Norte"], "description": "Frenos"}
    r.update(cambios)
    return r


class OdooFalso:
    def __init__(self, *unidades, taller=(), con_fechas=True):
        self.unidades = {u["id"]: u for u in unidades}
        self.taller = {r["id"]: r for r in taller}
        self.con_fechas = con_fechas

    def campos(self, modelo):
        assert modelo == "fleet.vehicle.log.services"
        campos = {c: {"type": "char"} for c in odoo_flota.CAMPOS_TALLER}
        if self.con_fechas:
            campos[odoo_flota.ENTRADA] = campos[odoo_flota.SALIDA] = {"type": "date"}
        return campos

    def leer(self, modelo, dominio, campos, archivados=False):
        if modelo == "fleet.vehicle.tag":
            return [{"id": i, "name": n} for i, n in ETIQUETAS.items()]
        if modelo == "fleet.vehicle.log.services":
            filas = list(self.taller.values())
        else:
            assert modelo == "fleet.vehicle"
            filas = [u for u in self.unidades.values()
                     if archivados or u.get("active", True)]
        for campo, operador, valor in dominio:
            assert (campo, operador) == ("id", "in")
            filas = [f for f in filas if f["id"] in valor]
        return [{"id": f["id"], **{c: f.get(c, False) for c in campos}}
                for f in filas]


class OdooCaido:
    def leer(self, *args, **kwargs):
        raise odoo_api.NoResponde("Odoo rechazo la llave; puede que haya vencido.")


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture(autouse=True)
def sin_fotos(base_de_pruebas):
    """La categoria es catalogo y no se vacia entre pruebas: la foto que
    sube una prueba no se queda para la siguiente."""
    yield
    with base_de_pruebas.begin() as con:
        con.execute(text("DELETE FROM foto_categoria"))


def leer(db, odoo, ensayo=False, **kwargs):
    # Como en produccion, donde cada lectura abre su propia sesion.
    db.expire_all()
    return odoo_flota.sincronizar(db, odoo, ensayo=ensayo, **kwargs)


def vehiculo(db, n):
    db.expire_all()
    return db.query(m.Vehiculo).filter_by(odoo_id=ODOO0 + n).one()


def de_odoo(db):
    db.expire_all()
    return db.query(m.Vehiculo).filter(m.Vehiculo.odoo_id >= ODOO0).count()


def dia_de_servicio(cliente, sesion, datos, dias=3):
    """Un dia de un servicio de Ana en la Ciudad de Mexico."""
    servicio = crear_servicio(
        cliente, sesion("consultor"), datos,
        [jornada(manana(dias), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    return servicio["equipos"][0]["jornadas"][0]


# ================================================================ unidades

def test_el_ensayo_dice_que_haria_y_no_guarda_nada(db):
    informe = leer(db, OdooFalso(unidad(1), unidad(2), taller=[taller(1, 1)]),
                   ensayo=True)
    assert informe["ensayo"] is True and len(informe["altas"]) == 2
    # El taller de una unidad que llega nueva tambien se cuenta.
    assert informe["taller"]["nuevas"] == 1
    assert de_odoo(db) == 0
    assert db.query(m.TallerVehiculo).count() == 0
    assert db.query(m.SincronizacionOdoo).count() == 0


def test_entran_las_de_proteccion_ejecutiva_con_su_categoria_y_plaza(
        db, datos):
    informe = leer(db, OdooFalso(
        unidad(1),
        unidad(2, tag_ids=[2, 3], category_id=[9, "VAN"],
               location="Estado de México"),
        unidad(3, category_id=[9, "SEDAN"], location="CDMX"),
        unidad(4, category_id=[9, "MINIVAN BLINDADA"], location="Guadalajara"),
        unidad(5, tag_ids=[2]),
        unidad(6, tag_ids=[])))
    assert informe["leidas"] == 4
    assert sorted(a["odoo_id"] - ODOO0 for a in informe["altas"]) == [1, 2, 3, 4]
    cat = datos["categorias"]
    assert vehiculo(db, 2).categoria_id == cat["van_10"]["id"]
    assert vehiculo(db, 3).categoria_id == cat["sedan"]["id"]
    assert vehiculo(db, 4).categoria_id == cat["minivan_blindada"]["id"]
    assert vehiculo(db, 2).plaza_id == datos["cdmx"]["id"]
    assert vehiculo(db, 3).plaza_id == datos["cdmx"]["id"]
    assert vehiculo(db, 4).plaza_id == datos["gdl"]["id"]
    v = vehiculo(db, 1)
    assert (v.placa, v.marca_modelo, v.color, v.modelo_anio) == (
        "T01ODO", "Toyota SIENNA XSE", "Blanco", 2023)
    assert v.activo and not v.rentado and v.odoo_sincronizado_en is not None


def test_lo_dudoso_queda_pendiente_y_no_se_toca(db):
    informe = leer(db, OdooFalso(
        unidad(1, category_id=False),
        unidad(2, category_id=[9, "MINIBUS"]),
        unidad(3, location=False),
        unidad(4, location="Tijuana"),
        unidad(5, license_plate="R99ODO"),
        unidad(6, license_plate="R99ODO")))
    assert not informe["altas"]
    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}
    assert faltas == {
        1: ["sin categoria"],
        2: ["la categoria «MINIBUS» no existe en Centauro"],
        3: ["sin plaza"],
        4: ["la plaza «Tijuana» no existe en Centauro"],
        5: ["placa repetida en Odoo"],
        6: ["placa repetida en Odoo"],
    }
    assert de_odoo(db) == 0


def test_la_unidad_que_ya_estaba_se_vincula_por_su_placa(db, datos):
    suburban = datos["suburban"]
    informe = leer(db, OdooFalso(unidad(
        1, license_plate=suburban["placa"].replace("-", ""),
        category_id=[9, "SUV BLINDADA"], model_id=[2, "Chevrolet/SUBURBAN"])))
    assert not informe["altas"]
    assert [x["vehiculo_id"] for x in informe["vinculadas"]] == [suburban["id"]]
    v = vehiculo(db, 1)
    assert v.id == suburban["id"] and v.marca_modelo == "Chevrolet SUBURBAN"
    # La misma placa escrita distinto no es un cambio.
    assert v.placa == suburban["placa"]


def test_lo_que_cambia_en_odoo_cambia_aqui_y_lo_vacio_no_borra(db, datos):
    odoo = OdooFalso(unidad(1))
    leer(db, odoo)
    odoo.unidades[ODOO0 + 1].update(color="Gris", location="Guadalajara",
                                    category_id=[9, "CUV"])
    informe = leer(db, odoo)
    assert informe["cambios"][0]["que"] == ["categoria", "plaza", "color"]
    v = vehiculo(db, 1)
    assert (v.color, v.plaza_id, v.categoria_id) == (
        "Gris", datos["gdl"]["id"], datos["categorias"]["cuv"]["id"])
    odoo.unidades[ODOO0 + 1].update(color=False, model_id=False)
    assert not leer(db, odoo)["cambios"]
    v = vehiculo(db, 1)
    assert (v.color, v.marca_modelo) == ("Gris", "Toyota SIENNA XSE")


def test_la_baja_en_odoo_avisa_en_cada_dia_que_tenia(cliente, sesion, datos, db):
    odoo = OdooFalso(unidad(1), unidad(2))
    leer(db, odoo)
    j = dia_de_servicio(cliente, sesion, datos)
    r = asignar(cliente, sesion("consultor"), j["id"],
                vehiculo_id=vehiculo(db, 1).id)[0]
    assert r.status_code == 200, r.text

    odoo.unidades[ODOO0 + 1]["active"] = False
    informe = leer(db, odoo)
    assert [(b["odoo_id"] - ODOO0, b["motivo"], b["dias_por_delante"])
            for b in informe["bajas"]] == [(1, "archivada en Odoo", 1)]
    v = vehiculo(db, 1)
    assert not v.activo and v.baja_odoo_en is not None
    alerta = (db.query(m.Alerta)
              .filter_by(jornada_id=j["id"],
                         tipo=m.TipoAlerta.UNIDAD_DE_BAJA).one())
    assert v.placa in alerta.mensaje
    assert vehiculo(db, 2).activo


def test_la_que_deja_de_ser_de_proteccion_queda_pendiente_sin_baja(db):
    odoo = OdooFalso(unidad(1))
    leer(db, odoo)
    odoo.unidades[ODOO0 + 1]["tag_ids"] = [2]
    informe = leer(db, odoo)
    assert not informe["bajas"]
    assert informe["pendientes"][0]["falta"] == [
        "ya no es de Proteccion Ejecutiva en Odoo"]
    assert vehiculo(db, 1).activo


# ================================================================ taller

def test_el_taller_de_odoo_saca_a_la_unidad_de_circulacion(
        cliente, sesion, datos, db):
    odoo = OdooFalso(unidad(1), taller=[taller(1, 1)])
    informe = leer(db, odoo)
    assert informe["taller"]["nuevas"] == 1
    fila = db.query(m.TallerVehiculo).filter_by(odoo_id=9_000_001).one()
    assert (fila.desde, fila.hasta, fila.tipo, fila.taller) == (
        manana(2), manana(5), m.MotivoCambio.MANTENIMIENTO_CORRECTIVO,
        "Taller Norte")

    # Al asignar un eventual ya no se ofrece como libre, y no se puede.
    j = dia_de_servicio(cliente, sesion, datos, dias=3)
    v = vehiculo(db, 1)
    h = sesion("consultor")
    servicio = cliente.get(f"/servicios/jornadas/{j['id']}/asignaciones",
                           headers=h)
    assert servicio.status_code == 200, servicio.text
    equipo_id = db.get(m.Jornada, j["id"]).equipo_id
    r = cliente.get(f"/servicios/equipos/{equipo_id}/recomendaciones"
                    f"?categoria_id={v.categoria_id}", headers=h).json()
    ficha = next(f for f in r["vehiculos"]["no_disponibles"]
                 if f["vehiculo_id"] == v.id)
    assert any("taller" in a["mensaje"] for a in ficha["alertas"])
    r = asignar(cliente, h, j["id"], vehiculo_id=v.id)[0]
    assert r.status_code == 409, r.text

    # Un dia despues de la salida ya se puede.
    despues = dia_de_servicio(cliente, sesion, datos, dias=6)
    assert asignar(cliente, h, despues["id"],
                   vehiculo_id=v.id)[0].status_code == 200


def test_sin_salida_se_da_por_adentro_y_lo_cancelado_deja_de_bloquear(db):
    odoo = OdooFalso(unidad(1), taller=[taller(1, 1, **{odoo_flota.SALIDA: False})])
    leer(db, odoo)
    fila = db.query(m.TallerVehiculo).filter_by(odoo_id=9_000_001).one()
    assert fila.hasta is None and fila.cubre(date.today() + timedelta(days=400))

    # Lo que se capturo a mano en Centauro no se toca.
    a_mano = m.TallerVehiculo(vehiculo_id=vehiculo(db, 1).id, desde=manana(30),
                              tipo=m.MotivoCambio.MANTENIMIENTO_PREVENTIVO)
    db.add(a_mano)
    db.commit()

    odoo.taller[9_000_001]["state"] = "cancelled"
    assert leer(db, odoo)["taller"]["borradas"] == 1
    db.expire_all()
    assert db.query(m.TallerVehiculo).filter_by(odoo_id=9_000_001).count() == 0
    assert db.query(m.TallerVehiculo).filter_by(id=a_mano.id).count() == 1


def test_lo_que_no_es_taller_no_saca_de_circulacion(db):
    informe = leer(db, OdooFalso(
        unidad(1), unidad(2, tag_ids=[2]),
        taller=[taller(1, 1, service_type_id=[8, "Resguardo de Unidad"]),
                taller(2, 2),
                taller(3, 1, **{odoo_flota.ENTRADA: False}),
                taller(4, 1, state="done", **{odoo_flota.SALIDA: False})]))
    t = informe["taller"]
    assert (t["nuevas"], t["de_otras_unidades"]) == (1, 1)
    faltas = {p["odoo_id"]: p["falta"] for p in t["pendientes"]}
    assert faltas[9_000_003] == ["sin fecha de entrada"]
    assert faltas[9_000_004][0].startswith("terminado sin fecha de salida")
    # El terminado sin salida no bloquea mas alla del dia que entro.
    fila = db.query(m.TallerVehiculo).filter_by(odoo_id=9_000_004).one()
    assert fila.hasta == fila.desde


def test_sin_los_campos_de_fecha_no_se_lee_el_taller(db):
    informe = leer(db, OdooFalso(unidad(1), taller=[taller(1, 1)],
                                 con_fechas=False))
    assert "no tiene los campos" in informe["taller"]["error"]
    assert len(informe["altas"]) == 1 and db.query(m.TallerVehiculo).count() == 0


# ================================================================ la foto

def test_la_foto_de_la_categoria_respeta_el_color_de_la_unidad(
        cliente, sesion, datos):
    """Una foto por categoria, y aparte una por color: la Suburban negra
    se ve negra. El color que no tiene foto ensena la base."""
    h = sesion("admin")
    suv = datos["categorias"]["suv_blindada"]
    ruta = f"/catalogos/categorias-vehiculo/{suv['id']}/foto"
    r = cliente.put(ruta, headers=h,
                    files={"archivo": ("suv.png", PIXEL, "image/png")})
    assert r.status_code == 200, r.text
    # La negra se distingue de la base por el tipo de imagen.
    r = cliente.put(ruta, headers=h, params={"color": "Negro metálico"},
                    files={"archivo": ("suv_negra.webp", PIXEL, "image/webp")})
    assert r.status_code == 200 and r.json()["color"] == "negro", r.text
    cats = {c["id"]: c for c in cliente.get("/catalogos/categorias-vehiculo",
                                            headers=h).json()}
    assert cats[suv["id"]]["fotos"] == ["", "negro"]
    assert "foto_url" not in cats[suv["id"]]      # la lista no carga fotos

    negra = datos["suburban"]
    otra = next(v for v in datos["vehiculos"]
                if v["categoria_id"] == suv["id"] and v["id"] != negra["id"])
    r = cliente.patch(f"/catalogos/vehiculos/{negra['id']}", headers=h, json={
        "placa": negra["placa"], "categoria_id": suv["id"],
        "plaza_id": negra["plaza_id"], "color": "Negro"})
    assert r.status_code == 200, r.text

    j = dia_de_servicio(cliente, sesion, datos)
    for unidad_id in (negra["id"], otra["id"]):
        assert asignar(cliente, sesion("consultor"), j["id"],
                       vehiculo_id=unidad_id)[0].status_code == 200
    fotos = {u["vehiculo_id"]: u["foto"] for u in cliente.get(
        f"/servicios/jornadas/{j['id']}/asignaciones",
        headers=sesion("consultor")).json()["vehiculos"]}
    assert fotos[negra["id"]].startswith("data:image/webp;base64,")
    assert fotos[otra["id"]].startswith("data:image/png;base64,")


def test_la_foto_la_sube_administracion_y_tiene_que_ser_imagen(
        cliente, sesion, datos):
    suv = datos["categorias"]["suv_blindada"]
    ruta = f"/catalogos/categorias-vehiculo/{suv['id']}/foto"
    archivo = {"archivo": ("suv.png", PIXEL, "image/png")}
    assert cliente.put(ruta, headers=sesion("consultor"),
                       files=archivo).status_code == 403
    r = cliente.put(ruta, headers=sesion("admin"),
                    files={"archivo": ("nota.txt", b"hola", "text/plain")})
    assert r.status_code == 400, r.text


# ================================================================ la consola

def test_lo_que_viene_de_odoo_no_se_edita_en_la_flota(cliente, sesion, db):
    leer(db, OdooFalso(unidad(1)))
    v = vehiculo(db, 1)
    h = sesion("admin")
    cuerpo = {"placa": v.placa, "categoria_id": v.categoria_id,
              "plaza_id": v.plaza_id}
    r = cliente.patch(f"/catalogos/vehiculos/{v.id}", headers=h,
                      json={**cuerpo, "placa": "OTRA123"})
    assert r.status_code == 409, r.text
    assert "Odoo" in r.json()["detail"]["mensaje"]
    # Lo que es de Centauro si se edita.
    r = cliente.patch(f"/catalogos/vehiculos/{v.id}", headers=h,
                      json={**cuerpo, "costo_diario": "950"})
    assert r.status_code == 200, r.text


def test_el_sedan_ya_es_categoria_de_centauro_con_tarifa(cliente, sesion,
                                                         datos):
    sedan = datos["categorias"]["sedan"]
    assert sedan["blindado"] is False
    tarifas = cliente.get("/catalogos/tarifas-vehiculo",
                          headers=sesion("admin")).json()
    assert any(t["categoria_id"] == sedan["id"] for t in tarifas)


def test_la_tarea_de_cada_hora_espera_la_primera_a_mano(db):
    odoo = OdooFalso(unidad(1))
    assert odoo_flota.sincronizar_si_toca(db, odoo) == {
        "omitido": "falta la primera lectura a mano"}
    leer(db, odoo, ensayo=True)
    assert "omitido" in odoo_flota.sincronizar_si_toca(db, odoo)
    leer(db, odoo)
    odoo.unidades[ODOO0 + 2] = unidad(2)
    r = odoo_flota.sincronizar_si_toca(db, odoo)
    assert (r["leidas"], r["altas"]) == (2, 1)
    assert "vencido" in odoo_flota.sincronizar_si_toca(db, OdooCaido())["error"]


def test_las_rutas_de_la_flota_son_de_administracion(cliente, sesion,
                                                     monkeypatch, db):
    from app.config import settings

    monkeypatch.setattr(settings, "odoo_base", "")
    monkeypatch.setattr(settings, "odoo_api_key", "")
    assert cliente.get("/odoo/flota/ensayo",
                       headers=sesion("consultor")).status_code == 403
    assert cliente.get("/odoo/flota/ensayo",
                       headers=sesion("admin")).status_code == 503

    monkeypatch.setattr(odoo_api, "cliente", lambda: OdooFalso(unidad(1)))
    r = cliente.get("/odoo/flota/ensayo", headers=sesion("admin"))
    assert r.status_code == 200 and r.json()["ensayo"] is True
    assert de_odoo(db) == 0
    r = cliente.post("/odoo/flota/sincronizar", headers=sesion("admin"))
    assert r.status_code == 200 and len(r.json()["altas"]) == 1
    assert db.query(m.SincronizacionOdoo).filter_by(tipo="flota").count() == 1

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
ETIQUETAS = {1: "pe", 2: "Logística", 3: "PROTECCIÓN EJECUTIVA",
             5: "PROTECCIÓN EJECUTIVA BRASIL"}
# Las companias de Odoo (seccion 118): cada pais la suya.
MEXICO = [1, "CENTAURO ASS"]
BRASIL = [5, "Centauro Brasil"]


def unidad(n, **cambios):
    u = {"id": ODOO0 + n, "license_plate": f"T{n:02d}ODO",
         "category_id": [9, "MINIVAN"], "location": "Ciudad de México",
         "model_id": [4, "Toyota/SIENNA XSE"], "color": "Blanco",
         "model_year": "2023", "tag_ids": [1], "company_id": MEXICO,
         "write_date": "2026-01-01 10:00:00", "active": True}
    u.update(cambios)
    return u


def de_brasil(n, **cambios):
    """Como llegan hoy las de Brasil: su compania y su etiqueta, y sin
    VIN, color ni Ubicacion."""
    return unidad(n, **{"license_plate": f"BRA{n}C{n:02d}",
                        "category_id": [21, "CUV BLINDADA"], "location": False,
                        "color": False, "tag_ids": [5], "company_id": BRASIL,
                        "model_id": [6, "Toyota/COROLLA CROSS"], **cambios})


def taller(n, dueno, **cambios):
    r = {"id": 9_000_000 + n, "vehicle_id": [ODOO0 + dueno, "x"],
         "service_type_id": [3, "Correctivo"], "state": "running",
         odoo_flota.ENTRADA: str(manana(2)), odoo_flota.SALIDA: str(manana(5)),
         "vendor_id": [7, "Taller Norte"], "description": "Frenos"}
    r.update(cambios)
    return r


class OdooFalso:
    def __init__(self, *unidades, taller=(), con_fechas=True, etiquetas=None):
        self.unidades = {u["id"]: u for u in unidades}
        self.taller = {r["id"]: r for r in taller}
        self.con_fechas = con_fechas
        self.etiquetas = ETIQUETAS if etiquetas is None else etiquetas

    def campos(self, modelo):
        assert modelo == "fleet.vehicle.log.services"
        campos = {c: {"type": "char"} for c in odoo_flota.CAMPOS_TALLER}
        if self.con_fechas:
            campos[odoo_flota.ENTRADA] = campos[odoo_flota.SALIDA] = {"type": "date"}
        return campos

    def leer(self, modelo, dominio, campos, archivados=False):
        if modelo == "fleet.vehicle.tag":
            return [{"id": i, "name": n} for i, n in self.etiquetas.items()]
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


# ================================================== la flota de Brasil (118)

def _brasil(db):
    pais = db.query(m.Pais).filter_by(codigo="BR").one()
    plaza = db.query(m.Plaza).filter_by(pais_id=pais.id,
                                        nombre="Sao Paulo").one()
    return pais, plaza


def test_cada_pais_lee_su_compania_con_su_etiqueta(db, datos):
    """Mexico: CENTAURO ASS con «PROTECCION EJECUTIVA»; Brasil: Centauro
    Brasil con «PROTECCION EJECUTIVA BRASIL». Y la CUV blindada ya es una
    categoria de Connect."""
    informe = leer(db, OdooFalso(
        unidad(1, tag_ids=[3]),
        de_brasil(2, location="São Paulo", color="Prata")))
    assert sorted(a["odoo_id"] - ODOO0 for a in informe["altas"]) == [1, 2]
    assert [(p["codigo"], p["leidas"]) for p in informe["por_pais"]] == [
        ("MX", 1), ("BR", 1)]
    assert not informe["pendientes"] and not informe["por_capturar"]
    br, sp = _brasil(db)
    v = vehiculo(db, 2)
    assert (v.plaza_id, v.pais_id, v.pais_de_la_unidad) == (sp.id, br.id, br.id)
    assert v.categoria_id == datos["categorias"]["cuv_blindada"]["id"]
    assert datos["categorias"]["cuv_blindada"]["blindado"] is True
    mx = vehiculo(db, 1)
    assert (mx.plaza_id, mx.pais_id) == (datos["cdmx"]["id"], datos["mx"]["id"])


def test_la_etiqueta_se_reconoce_por_su_numero_aunque_se_renombre(db):
    """Seccion 121: la de Mexico es la 3 y la de Brasil la 5 en Odoo. La
    de Mexico se va a llamar «PROTECCION EJECUTIVA MEXICO»; con cualquier
    nombre, el numero manda."""
    renombradas = {1: "pe", 2: "Logística", 3: "PROTECCIÓN EJECUTIVA MÉXICO",
                   5: "PE · Frota Brasil"}
    informe = leer(db, OdooFalso(
        unidad(1, tag_ids=[3]),
        de_brasil(2, location="São Paulo"),
        unidad(3, tag_ids=[2]), etiquetas=renombradas), ensayo=True)
    assert sorted(a["odoo_id"] - ODOO0 for a in informe["altas"]) == [1, 2]
    assert [(p["codigo"], p["leidas"]) for p in informe["por_pais"]] == [
        ("MX", 1), ("BR", 1)]
    assert informe["etiquetas"] == [
        {"pais": "México", "id": 3, "nombre": "PROTECCIÓN EJECUTIVA MÉXICO"},
        {"pais": "Brasil", "id": 5, "nombre": "PE · Frota Brasil"}]
    # Y la de Mexico con el nombre nuevo pero otro numero tambien vale, de
    # respaldo, como «pe».
    informe = leer(db, OdooFalso(
        unidad(4, tag_ids=[7]), unidad(5, tag_ids=[1]),
        etiquetas={1: "pe", 7: "Protección Ejecutiva México"}), ensayo=True)
    assert sorted(a["odoo_id"] - ODOO0 for a in informe["altas"]) == [4, 5]
    # Sin la etiqueta 3 en Odoo se dice: la de Mexico solo se reconoce por
    # el nombre, y renombrarla la sacaria.
    assert informe["etiquetas"][0] == {"pais": "México", "id": 3, "nombre": None}


def test_la_etiqueta_de_un_pais_con_la_compania_de_otro_no_entra(db):
    informe = leer(db, OdooFalso(
        unidad(1, company_id=BRASIL),
        de_brasil(2, company_id=MEXICO, location="São Paulo"),
        unidad(3, company_id=False),
        # Sin etiqueta de Proteccion Ejecutiva no es asunto de Connect,
        # sea de la compania que sea.
        unidad(4, tag_ids=[2], company_id=BRASIL)))
    assert not informe["altas"] and de_odoo(db) == 0
    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}
    assert faltas == {
        1: ["la etiqueta es de «México» y su compania en Odoo es «Centauro Brasil»"],
        2: ["la etiqueta es de «Brasil» y su compania en Odoo es «CENTAURO ASS»"],
        3: ["la etiqueta es de «México» y en Odoo no tiene compania"],
    }
    assert informe["leidas"] == 0
    r = odoo_flota.resumen(informe)
    assert r["pendientes"] == {"etiqueta de un pais y compania de otro": 3}


def test_brasil_entra_sin_color_ni_ubicacion_y_se_completa_despues(db, datos):
    """Las 13 de Brasil llegan sin VIN, color ni Ubicacion: entran igual,
    sin ciudad, y lo que falta sale como por capturar, no como pendiente.
    Cuando Odoo lo tiene, la siguiente lectura lo pone."""
    cat = datos["categorias"]
    odoo = OdooFalso(
        de_brasil(1, category_id=[9, "MINIVAN"]),
        de_brasil(2, category_id=[10, "MINIVAN BLINDADA"]),
        de_brasil(3),
        de_brasil(4, category_id=[11, "SUV BLINDADA"]))
    ensayo = leer(db, odoo, ensayo=True)
    assert len(ensayo["altas"]) == 4 and not ensayo["pendientes"]
    assert ensayo["altas"][0]["pais"] == "Brasil"
    assert ensayo["altas"][0]["plaza"] is None
    assert {tuple(c["falta"]) for c in ensayo["por_capturar"]} == {
        ("sin ubicacion", "sin color")}
    assert odoo_flota.resumen(ensayo)["por_capturar"] == {
        "sin ubicacion": 4, "sin color": 4}

    informe = leer(db, odoo)
    assert len(informe["altas"]) == 4 and not informe["pendientes"]
    br, sp = _brasil(db)
    v = vehiculo(db, 3)
    assert (v.plaza_id, v.pais_id, v.color) == (None, br.id, None)
    assert v.categoria_id == cat["cuv_blindada"]["id"]
    assert {vehiculo(db, n).categoria_id for n in (1, 2, 4)} == {
        cat["minivan"]["id"], cat["minivan_blindada"]["id"],
        cat["suv_blindada"]["id"]}
    fila = db.query(m.SincronizacionOdoo).filter_by(tipo="flota").one()
    assert (fila.altas, fila.pendientes) == (4, 0)

    # Se capturan en Odoo: la siguiente lectura las ubica.
    odoo.unidades[ODOO0 + 3].update(location="São Paulo", color="Blanco")
    informe = leer(db, odoo)
    assert [c["que"] for c in informe["cambios"]] == [["plaza", "color"]]
    assert {c["odoo_id"] - ODOO0 for c in informe["por_capturar"]} == {1, 2, 4}
    v = vehiculo(db, 3)
    assert (v.plaza_id, v.pais_id, v.color) == (sp.id, br.id, "Blanco")

    # Un campo vacio en Odoo no borra el de Centauro, y no se vuelve a
    # pedir lo que Centauro ya tiene.
    odoo.unidades[ODOO0 + 3].update(location=False, color=False)
    informe = leer(db, odoo)
    assert not informe["cambios"]
    assert ODOO0 + 3 not in {c["odoo_id"] for c in informe["por_capturar"]}
    assert vehiculo(db, 3).plaza_id == sp.id


def test_la_ubicacion_se_busca_entre_las_ciudades_de_su_pais(db, datos):
    """«Guadalajara» en una unidad de Brasil no la manda a Mexico: entra
    sin ciudad y se dice. En Mexico, «Sao Paulo» tampoco existe."""
    informe = leer(db, OdooFalso(
        de_brasil(1, location="Guadalajara"),
        unidad(2, location="São Paulo")))
    assert [a["odoo_id"] - ODOO0 for a in informe["altas"]] == [1]
    br, _ = _brasil(db)
    v = vehiculo(db, 1)
    assert (v.plaza_id, v.pais_id) == (None, br.id)
    capturar = {c["odoo_id"] - ODOO0: c["falta"] for c in informe["por_capturar"]}
    assert capturar == {1: [
        "la ubicacion «Guadalajara» no es una ciudad de «Brasil» en Centauro",
        "sin color"]}
    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}
    assert faltas == {2: ["la plaza «São Paulo» no existe en Centauro"]}


def test_una_unidad_no_cambia_de_pais_ni_se_da_de_baja_sola(db, datos):
    # La 9 se queda en la flota de Mexico: si Mexico leyera cero con sus
    # unidades activas, la vuelta se detendria (seccion 130, decision 3).
    odoo = OdooFalso(unidad(1), unidad(2), unidad(9))
    leer(db, odoo)
    # La 1 pasa entera a Brasil en Odoo; la 2 cambia de compania y se
    # queda con la etiqueta de Mexico.
    odoo.unidades[ODOO0 + 1].update(company_id=BRASIL, tag_ids=[5],
                                    location="São Paulo")
    odoo.unidades[ODOO0 + 2].update(company_id=BRASIL)
    informe = leer(db, odoo)
    assert not informe["bajas"] and not informe["cambios"]
    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}
    assert faltas == {
        1: ["en Odoo es de la flota de «Brasil» y en Centauro es de otro pais"],
        2: ["la etiqueta es de «México» y su compania en Odoo es «Centauro Brasil»"],
    }
    for n in (1, 2):
        v = vehiculo(db, n)
        assert v.activo and v.plaza_id == datos["cdmx"]["id"]


def test_la_placa_de_una_unidad_de_mexico_no_se_liga_a_una_de_brasil(db, datos):
    suburban = datos["suburban"]
    informe = leer(db, OdooFalso(de_brasil(
        1, license_plate=suburban["placa"], location="São Paulo")))
    assert not informe["altas"] and not informe["vinculadas"]
    assert informe["pendientes"][0]["falta"] == [
        "su placa ya es de una unidad de otro pais en Centauro"]
    assert informe["pendientes"][0]["vehiculo_id"] == suburban["id"]
    db.expire_all()
    assert db.get(m.Vehiculo, suburban["id"]).odoo_id is None


def test_la_unidad_sin_ciudad_se_ve_y_no_cruza_de_pais(cliente, sesion, db,
                                                       datos):
    """Sin ciudad sigue siendo de Brasil: su GPS se liga, sale en
    Unidades, se ofrece en los eventuales de Brasil como «sin ciudad» y
    no en los de Mexico; al implantado no va mientras no tenga ciudad."""
    from datetime import datetime

    from app import disponibilidad as disp
    from app import gps
    from app import implantado as imp

    leer(db, OdooFalso(de_brasil(1)))
    br, sp = _brasil(db)
    v = vehiculo(db, 1)
    assert gps._placas_de(db, br.id) == {"BRA1C01": v.id}
    assert v.id not in gps._placas_de(db, datos["mx"]["id"]).values()
    fila = next(f for f in gps.unidades(db, br.id)["unidades"]
                if f.get("vehiculo_id") == v.id)
    assert fila["sin_ciudad"] is True and fila["plaza"] is None
    assert all(f.get("vehiculo_id") != v.id
               for f in gps.unidades(db, datos["mx"]["id"])["unidades"])

    inicio = datetime.combine(manana(3), datetime.min.time()).replace(hour=8)
    fin = inicio.replace(hour=20)

    def ofrecidas(plaza_id, categoria_id):
        r = disp.recomendar_vehiculos(db, plaza_id, categoria_id, inicio, fin,
                                      True)
        return {f["vehiculo_id"]: f for grupo in ("disponibles", "con_alerta",
                                                  "no_disponibles",
                                                  "de_otras_ciudades")
                for f in r[grupo]}

    en_brasil = ofrecidas(sp.id, v.categoria_id)
    assert en_brasil[v.id]["sin_ciudad"] is True
    assert not ofrecidas(datos["cdmx"]["id"], v.categoria_id)
    # Y la de Mexico no se ofrece en Sao Paulo.
    suv = datos["categorias"]["suv_blindada"]["id"]
    assert ofrecidas(datos["cdmx"]["id"], suv)
    assert not ofrecidas(sp.id, suv)

    assert "todavía no tiene ciudad" in imp.por_que_no_sale(
        db, v, sp.id, [], None)

    # La lista de la flota la trae sin tronar, con su pais.
    lista = cliente.get("/catalogos/vehiculos", headers=sesion("admin")).json()
    suya = next(x for x in lista if x["id"] == v.id)
    assert (suya["plaza_id"], suya["pais_de_la_unidad"]) == (None, br.id)


def test_la_unidad_que_se_da_de_alta_a_mano_dice_su_ciudad(cliente, sesion,
                                                          datos):
    h = sesion("admin")
    cuerpo = {"placa": "MANO123",
              "categoria_id": datos["categorias"]["suv"]["id"]}
    r = cliente.post("/catalogos/vehiculos", headers=h, json=cuerpo)
    assert r.status_code == 400, r.text
    r = cliente.post("/catalogos/vehiculos", headers=h,
                     json={**cuerpo, "plaza_id": datos["gdl"]["id"]})
    assert r.status_code == 201, r.text
    assert r.json()["pais_de_la_unidad"] == datos["mx"]["id"]
    r = cliente.patch(f"/catalogos/vehiculos/{r.json()['id']}", headers=h,
                      json={**cuerpo, "plaza_id": None})
    assert r.status_code == 400, r.text

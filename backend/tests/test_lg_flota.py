"""Logistica, bloque 2: la flota (seccion 151).

Cada unidad de «Centauro Logistic» con su numero economico que no se
repite, su estado con motivo, su odometro, su expediente, su plan
preventivo, sus servicios, sus llantas por posicion y su costo por dia con
de donde sale cada parte.

Decisiones de Salvador, 3 oct: quien lleva la flota edita; la gerencia de
Logistica ve todo; un documento vencido frena la unidad y uno sin capturar
solo avisa; el mantenimiento sale de los servicios registrados en Connect.
"""
import json
from datetime import timedelta
from decimal import Decimal

from ayudas_lg import (CALIDAD, KARLA, admin, calidad, costo_del_tipo,  # noqa: F401
                       db, entrar, expediente, hoy, karla, logistica, tipo_id, unidad,
                       usuario)
from app import lg_catalogos
from app import lg_disponibilidad as dispo
from app import lg_flota as fl
from app import models as m

PDF = b"%PDF-1.4\n%prueba\n"


def _detalle(cliente, h, u):
    r = cliente.get(f"/lg/flota/unidades/{u.id}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# ====================================================== el numero economico

def test_el_economico_es_el_mismo_con_o_sin_eco_y_ceros():
    assert fl.llave_economico("Eco 01") == "1"
    assert fl.llave_economico("01") == "1"
    assert fl.llave_economico(" eco-1 ") == "1"
    assert fl.llave_economico("1") == "1"
    assert fl.llave_economico("A-07") == "A07"
    assert fl.llave_economico("") is None
    assert fl.llave_economico(None) is None


def test_el_economico_no_se_repite(cliente, admin, db):
    """En Tango el 01 estaba dos veces: aqui la segunda no entra."""
    a = unidad(db, "LGA1001")
    b = unidad(db, "LGB2002")
    r = cliente.patch(f"/lg/flota/unidades/{a.id}", headers=admin,
                      json={"numero_economico": "Eco 01"})
    assert r.status_code == 200, r.text
    assert r.json()["unidad"]["numero_economico"] == "01"
    r = cliente.patch(f"/lg/flota/unidades/{b.id}", headers=admin,
                      json={"numero_economico": "1"})
    assert r.status_code == 409
    assert "LGA1001" in r.json()["detail"]["mensaje"]
    # La misma unidad puede volver a escribir el suyo.
    assert cliente.patch(f"/lg/flota/unidades/{a.id}", headers=admin,
                         json={"numero_economico": "01"}).status_code == 200
    assert cliente.patch(f"/lg/flota/unidades/{b.id}", headers=admin,
                         json={"numero_economico": "02"}).status_code == 200
    db.expire_all()
    assert db.get(m.LgUnidad, b.id).economico_llave == "2"


def test_la_gerencia_ve_pero_no_edita_la_flota(cliente, karla, calidad, sesion, db):
    u = unidad(db)
    r = cliente.get("/lg/flota", headers=karla)
    assert r.status_code == 200, r.text
    assert r.json()["puede"] == {"editar": False, "en_viaje": True}
    assert [x["placa"] for x in r.json()["unidades"]] == ["LGA1001"]
    assert cliente.get("/lg/flota", headers=calidad).status_code == 200
    assert cliente.patch(f"/lg/flota/unidades/{u.id}", headers=karla,
                         json={"numero_economico": "5"}).status_code == 403
    # Proteccion Ejecutiva no ve nada de Logistica.
    for quien in ("consultor", "finanzas", "juan"):
        assert cliente.get("/lg/flota", headers=sesion(quien)).status_code == 403, quien


# ====================================================== el estado

def test_taller_y_fuera_de_servicio_piden_motivo(cliente, admin, db):
    u = unidad(db)
    r = cliente.post(f"/lg/flota/unidades/{u.id}/estado", headers=admin,
                     json={"estado": "en_taller"})
    assert r.status_code == 400
    r = cliente.post(f"/lg/flota/unidades/{u.id}/estado", headers=admin,
                     json={"estado": "en_taller", "motivo": "frenos: cambio de balatas",
                           "hasta": (hoy() + timedelta(days=2)).isoformat()})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["unidad"]["estado"] == "en_taller"
    assert d["disponibilidad"]["estado"] == "bloqueo"
    assert d["disponibilidad"]["motivos"][0]["clave"] == "en_taller"
    # Liberarla borra el motivo.
    r = cliente.post(f"/lg/flota/unidades/{u.id}/estado", headers=admin,
                     json={"estado": "disponible"})
    assert r.json()["unidad"]["estado_motivo"] is None
    filas = cliente.get(f"/lg/flota/bitacora?unidad_id={u.id}", headers=admin).json()["filas"]
    assert [x["que"] for x in filas] == [
        "LGA1001: de en taller a libre",
        "LGA1001: de libre a en taller · hasta el "
        f"{lg_catalogos.fecha_texto(hoy() + timedelta(days=2), 'es')} · «frenos: cambio de balatas»"]


def test_logistica_marca_en_viaje_pero_no_saca_del_taller(cliente, admin, karla, db):
    u = unidad(db)
    r = cliente.post(f"/lg/flota/unidades/{u.id}/estado", headers=karla,
                     json={"estado": "en_viaje",
                           "hasta": (hoy() + timedelta(days=3)).isoformat()})
    assert r.status_code == 200, r.text
    assert cliente.post(f"/lg/flota/unidades/{u.id}/estado", headers=karla,
                        json={"estado": "disponible"}).status_code == 200
    assert cliente.post(f"/lg/flota/unidades/{u.id}/estado", headers=karla,
                        json={"estado": "en_taller", "motivo": "llanta ponchada"}
                        ).status_code == 403
    cliente.post(f"/lg/flota/unidades/{u.id}/estado", headers=admin,
                 json={"estado": "en_taller", "motivo": "llanta ponchada"})
    r = cliente.post(f"/lg/flota/unidades/{u.id}/estado", headers=karla,
                     json={"estado": "disponible"})
    assert r.status_code == 403
    assert "quien lleva la flota" in r.json()["detail"]


# ====================================================== el odometro

def test_el_odometro_menor_que_el_anterior_pide_porque(cliente, admin, db):
    u = unidad(db)
    r = cliente.post(f"/lg/flota/unidades/{u.id}/odometro", headers=admin,
                     json={"km": 120500})
    assert r.status_code == 201, r.text
    r = cliente.post(f"/lg/flota/unidades/{u.id}/odometro", headers=admin,
                     json={"km": 12050})
    assert r.status_code == 400
    assert "120,500" in r.json()["detail"]["mensaje"]
    r = cliente.post(f"/lg/flota/unidades/{u.id}/odometro", headers=admin,
                     json={"km": 12050, "motivo": "la anterior llevaba un cero de más"})
    assert r.status_code == 201
    assert r.json()["unidad"]["odometro_km"] == 12050
    assert [x["km"] for x in r.json()["lecturas"]] == [12050, 120500]
    assert cliente.post(f"/lg/flota/unidades/{u.id}/odometro", headers=admin,
                        json={"km": "doce mil"}).status_code == 400


# ====================================================== el expediente

def test_cada_documento_dice_si_falta_vence_o_vencio(db):
    u = unidad(db)
    actor = usuario(db)
    hoy_ = hoy()
    fl.capturar_documento(db, actor, "poliza_seguro", unidad=u,
                          vence_en=hoy_ + timedelta(days=200))
    fl.capturar_documento(db, actor, "permiso_sct", unidad=u,
                          vence_en=hoy_ + timedelta(days=12))
    fl.capturar_documento(db, actor, "verificacion", unidad=u,
                          vence_en=hoy_ - timedelta(days=1))
    fl.capturar_documento(db, actor, "tarjeta_circulacion", unidad=u)
    db.commit()
    estados = {d["tipo"]: d["estado"] for d in fl.detalle(db, u.id)["documentos"]}
    assert estados == {"tarjeta_circulacion": "vigente", "poliza_seguro": "vigente",
                       "permiso_sct": "por_vencer", "verificacion": "vencido",
                       "gps": "falta"}
    # La nueva verificacion reemplaza a la vencida; la de antes se queda.
    fl.capturar_documento(db, actor, "verificacion", unidad=u,
                          vence_en=hoy_ + timedelta(days=180))
    db.commit()
    assert db.query(m.LgDocumento).filter_by(unidad_id=u.id, tipo="verificacion").count() == 2
    estados = {d["tipo"]: d["estado"] for d in fl.detalle(db, u.id)["documentos"]}
    assert estados["verificacion"] == "vigente"


def test_el_documento_sube_con_su_archivo(cliente, admin, karla, sesion, db):
    u = unidad(db)
    r = cliente.post(f"/lg/flota/unidades/{u.id}/documentos", headers=admin,
                     data={"tipo": "poliza_seguro", "folio": "QA-123",
                           "vence_en": (hoy() + timedelta(days=90)).isoformat()},
                     files={"archivo": ("poliza.pdf", PDF, "application/pdf")})
    assert r.status_code == 201, r.text
    doc = next(d for d in r.json()["documentos"] if d["tipo"] == "poliza_seguro")
    assert doc["folio"] == "QA-123" and doc["archivo_id"]
    archivo = cliente.get(f"/lg/flota/archivos/{doc['archivo_id']}", headers=karla)
    assert archivo.status_code == 200 and archivo.content == PDF
    assert cliente.get(f"/lg/flota/archivos/{doc['archivo_id']}",
                       headers=sesion("consultor")).status_code == 403
    # Un archivo que no es PDF ni foto no entra.
    r = cliente.post(f"/lg/flota/unidades/{u.id}/documentos", headers=admin,
                     data={"tipo": "gps"},
                     files={"archivo": ("gps.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400
    # Ni un documento que no es del expediente.
    assert cliente.post(f"/lg/flota/unidades/{u.id}/documentos", headers=admin,
                        data={"tipo": "licencia"}).status_code == 400


# ====================================================== el plan y los servicios

def _plan(db, nombre="Cambio de aceite", cada=10000, tipo="1.5 ton", costo="3500"):
    return fl.alta_plan(db, usuario(db), {"clase": "unidad", "tipo_id": tipo_id(db, tipo),
                                          "nombre": nombre, "cada_km": cada,
                                          "costo_aprox": costo})


def test_el_plan_dice_cuando_toca_cada_servicio(db):
    u = unidad(db, odometro_km=58500)
    aceite = _plan(db)
    frenos = _plan(db, "Frenos", 40000, costo="6000")
    db.commit()
    actor = usuario(db)
    fl.registrar_servicio(db, actor, u, {"plan_id": aceite.id, "fecha": hoy() - timedelta(
        days=40), "km": 50000, "costo": "3400", "taller": "Taller Norte"})
    db.commit()
    plan = {p["nombre"]: p for p in fl.detalle(db, u.id)["plan"]}
    assert plan["Cambio de aceite"]["toca_km"] == 60000
    assert plan["Cambio de aceite"]["faltan_km"] == 1500
    assert plan["Cambio de aceite"]["estado"] == "proximo"
    # Sin ultimo registrado no se adivina: se pide.
    assert plan["Frenos"]["estado"] == "sin_ultimo"
    # Rebasado, la unidad no sale.
    fl.capturar_odometro(db, actor, u, 60200)
    db.commit()
    d = fl.detalle(db, u.id)
    assert d["plan"][0]["estado"] == "vencido"
    assert any(x["clave"] == "servicio_vencido" for x in d["disponibilidad"]["motivos"])


def test_el_servicio_mueve_el_odometro_y_se_anula_con_motivo(cliente, admin, db):
    u = unidad(db, odometro_km=40000)
    aceite = _plan(db)
    db.commit()
    datos = {"plan_id": str(aceite.id), "fecha": hoy().isoformat(), "costo": "3,450.00"}
    # Del plan sin odometro no: con el se calcula el siguiente.
    assert cliente.post(f"/lg/flota/unidades/{u.id}/servicios", headers=admin,
                        data=datos).status_code == 400
    r = cliente.post(f"/lg/flota/unidades/{u.id}/servicios", headers=admin,
                     data={**datos, "costo": "3450", "km": "41000", "taller": "Taller Norte",
                           "factura": "F-778"},
                     files={"archivo": ("factura.pdf", PDF, "application/pdf")})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["unidad"]["odometro_km"] == 41000
    assert d["servicios"][0]["factura"] == "F-778" and d["servicios"][0]["archivo_id"]
    assert d["plan"][0]["toca_km"] == 51000
    assert d["servicios_anio"] == {"n": 1, "total": "3450.00"}
    s = d["servicios"][0]["id"]
    assert cliente.post(f"/lg/flota/servicios/{s}/anular", headers=admin,
                        json={"motivo": "no"}).status_code == 400
    r = cliente.post(f"/lg/flota/servicios/{s}/anular", headers=admin,
                     json={"motivo": "se capturó en la unidad equivocada"})
    assert r.status_code == 200
    assert r.json()["servicios"][0]["anulado"] is True
    assert r.json()["servicios_anio"]["n"] == 0
    assert r.json()["plan"][0]["estado"] == "sin_ultimo"


# ====================================================== las llantas

def test_las_llantas_van_por_posicion(cliente, admin, db):
    u = unidad(db, odometro_km=30000)
    caja = unidad(db, "LGC3003", clase="remolque")
    d = _detalle(cliente, admin, u)
    assert [x["posicion"] for x in d["llantas"]] == ["DI", "DD", "TI", "TD", "R"]
    assert len(_detalle(cliente, admin, caja)["llantas"]) == 8
    torton = unidad(db, "LGT4004", tipo="Torton 15 ton")
    assert len(_detalle(cliente, admin, torton)["llantas"]) == 11
    assert cliente.post(f"/lg/flota/unidades/{u.id}/llantas", headers=admin,
                        json={"posicion": "2IE", "km": 30000}).status_code == 400
    r = cliente.post(f"/lg/flota/unidades/{u.id}/llantas", headers=admin,
                     json={"posicion": "DI", "km": 25000, "detalle": "Michelin XZE"})
    assert r.status_code == 201, r.text
    di = r.json()["llantas"][0]
    assert di["instalada_km"] == 25000 and di["km"] == 5000
    # La que entra en su lugar retira a la anterior.
    r = cliente.post(f"/lg/flota/unidades/{u.id}/llantas", headers=admin,
                     json={"posicion": "DI", "km": 30000})
    assert r.json()["llantas"][0]["instalada_km"] == 30000
    assert db.query(m.LgLlanta).filter_by(unidad_id=u.id).count() == 2
    assert db.query(m.LgLlanta).filter(m.LgLlanta.unidad_id == u.id,
                                       m.LgLlanta.retirada_km == 30000).count() == 1


# ====================================================== el costo por dia

def test_el_costo_por_dia_con_los_datos_de_la_unidad(db):
    """Compra 600,000 en 5 anos, seguro 36,500, tenencia, verificacion y
    GPS 21,900, mantenimiento de la carga 73,000 y llantas a 50 centavos
    por km con 100 km al dia."""
    u = unidad(db, valor_compra=600000, anios_vida=5, seguro_anual=36500,
               tenencia_anual=7300, verificacion_anual=3650, gps_anual=10950,
               mantenimiento_anual=73000, llantas_por_km=Decimal("0.5"))
    actor = usuario(db)
    fl.capturar_odometro(db, actor, u, 100000, hoy() - timedelta(days=60))
    fl.capturar_odometro(db, actor, u, 106000, hoy())
    db.commit()
    c = fl.calcular_costo(db, u)
    partes = {k: (v["monto"], v["fuente"]) for k, v in c["desglose"].items()}
    assert partes == {"depreciacion": ("328.77", "unidad"), "seguro": ("100.00", "unidad"),
                      "gps": ("60.00", "unidad"), "mantenimiento": ("200.00", "carga"),
                      "llantas": ("50.00", "unidad")}
    assert c["total"] == "738.77" and c["completo"] is True


def test_la_caja_sin_odometro_dice_que_le_faltan_los_km(db):
    """Trae su costo de llantas por km, pero no sus km al dia: lo que
    falta son los km, no el costo."""
    caja = unidad(db, "LGR5005", clase="remolque", tipo=None, llantas_por_km=Decimal("0.4"))
    llantas = fl.calcular_costo(db, caja)["desglose"]["llantas"]
    assert llantas == {"monto": None, "fuente": "falta",
                       "detalle": {"por_km": "0.4000", "sin_km": True}}


def test_sin_datos_de_la_unidad_toma_el_costo_de_su_tipo(cliente, karla, db):
    u = unidad(db)
    sin_nada = fl.calcular_costo(db, u)
    assert sin_nada["total"] == "0.00" and sin_nada["completo"] is False
    assert {v["fuente"] for v in sin_nada["desglose"].values()} == {"falta"}
    costo_del_tipo(cliente, karla, db)
    c = fl.calcular_costo(db, u)
    assert c["total"] == "900.00" and c["completo"] is True
    assert {v["fuente"] for v in c["desglose"].values()} == {"tipo"}
    # Con el seguro propio, solo esa parte cambia de fuente.
    u.seguro_anual = 36500
    db.commit()
    c = fl.calcular_costo(db, u)
    assert c["desglose"]["seguro"] == {"monto": "100.00", "fuente": "unidad",
                                       "detalle": {"anual": "36500.00"}}
    assert c["total"] == "905.00"


def test_el_mantenimiento_sale_de_los_servicios(cliente, karla, db):
    """Con un ano de servicios, de ellos; antes, de la carga; sin nada de
    la unidad, el promedio de su tipo."""
    costo_del_tipo(cliente, karla, db)
    a = unidad(db, "LGA1001")
    b = unidad(db, "LGB2002")
    actor = usuario(db)
    fl.registrar_servicio(db, actor, b, {"nombre": "Afinación", "fecha": hoy() - timedelta(
        days=20), "costo": "36500"})
    db.commit()
    # A no tiene servicios: el promedio de su tipo (36,500 de una unidad).
    m_a = fl.calcular_costo(db, a)["desglose"]["mantenimiento"]
    assert (m_a["monto"], m_a["fuente"]) == ("100.00", "promedio_tipo")
    # B tiene menos de un ano de historia: con su carga manda la carga.
    b.mantenimiento_anual = 73000
    db.commit()
    m_b = fl.calcular_costo(db, b)["desglose"]["mantenimiento"]
    assert (m_b["monto"], m_b["fuente"]) == ("200.00", "carga")
    # Con un servicio de hace mas de un ano, ya mandan sus servicios.
    fl.registrar_servicio(db, actor, b, {"nombre": "Frenos", "fecha": hoy() - timedelta(
        days=400), "costo": "9000"})
    db.commit()
    m_b = fl.calcular_costo(db, b)["desglose"]["mantenimiento"]
    assert (m_b["monto"], m_b["fuente"]) == ("100.00", "servicios")


def test_el_costo_del_mes_se_guarda_con_su_fecha(cliente, karla, admin, db):
    costo_del_tipo(cliente, karla, db, desde=hoy() - timedelta(days=60))
    u = unidad(db)
    r = fl.costos_del_mes(db)
    assert r["guardados"] == 1
    assert fl.costos_del_mes(db)["guardados"] == 0          # no se repite
    db.expire_all()
    fila = fl.costo_vigente(db, u.id)
    assert fila.vigente_desde == hoy().replace(day=1) and fila.origen == "mensual"
    assert str(fila.total) == "900.00"
    # A media mes, con su porque, rige desde hoy; el del mes se queda.
    u.seguro_anual = 36500
    db.commit()
    assert cliente.post(f"/lg/flota/unidades/{u.id}/costo", headers=admin,
                        json={"motivo": "ok"}).status_code == 400
    r = cliente.post(f"/lg/flota/unidades/{u.id}/costo", headers=admin,
                     json={"motivo": "renovó la póliza con otra aseguradora"})
    assert r.status_code == 200, r.text
    assert r.json()["costo"]["total"] == "905.00"
    assert r.json()["costo"]["origen"] == "recalculo"
    assert [x["total"] for x in r.json()["historial_costo"]] == ["905.00", "900.00"]
    # Un viaje de ayer toma el del mes, no el de hoy.
    if hoy().day > 1:
        assert str(fl.costo_vigente(db, u.id, hoy() - timedelta(days=1)).total) == "900.00"


# ====================================================== la lista

def test_la_lista_cuenta_quien_puede_salir(cliente, karla, admin, db):
    lista_ = unidad(db, "LGA1001", numero_economico="01", economico_llave="1",
                    rendimiento_ref=7)
    expediente(db, lista_)
    taller = unidad(db, "LGB2002", numero_economico="02", economico_llave="2",
                    rendimiento_ref=7)
    expediente(db, taller)
    vencida = unidad(db, "LGC3003", numero_economico="03", economico_llave="3",
                     rendimiento_ref=7)
    expediente(db, vencida)
    fl.capturar_documento(db, usuario(db), "poliza_seguro", unidad=vencida,
                          vence_en=hoy() - timedelta(days=3))
    db.commit()
    unidad(db, "LGD4004")                                  # le falta todo
    unidad(db, "LGR5005", clase="remolque", numero_economico="C1", economico_llave="C1")
    cliente.post(f"/lg/flota/unidades/{taller.id}/estado", headers=admin,
                 json={"estado": "en_taller", "motivo": "servicio mayor"})
    d = cliente.get("/lg/flota", headers=karla).json()
    assert d["cifras"] == {"unidades": 4, "en_viaje": 0, "libres": 2, "taller": 1,
                           "no_pueden": 1, "servicio_proximo": 0, "documentos": 1,
                           "por_completar": 1, "remolques": 1}
    por_placa = {x["placa"]: x for x in d["unidades"]}
    assert por_placa["LGA1001"]["disponibilidad"]["estado"] == "libre"
    assert por_placa["LGD4004"]["disponibilidad"]["estado"] == "alerta"
    assert por_placa["LGD4004"]["faltas"] == ["economico", "rendimiento"]
    assert por_placa["LGC3003"]["disponibilidad"]["motivos"][0] == {
        "nivel": "bloqueo", "clave": "documento_vencido", "documento": "poliza_seguro",
        "vence": (hoy() - timedelta(days=3)).isoformat()}
    assert por_placa["LGR5005"]["disponibilidad"]["motivos"][0]["clave"] == "remolque"
    # Los remolques van al final.
    assert d["unidades"][-1]["placa"] == "LGR5005"


def test_la_disponibilidad_por_fechas_y_km(cliente, karla, db):
    u = unidad(db, odometro_km=58500)
    expediente(db, u, vence=hoy() + timedelta(days=5))
    aceite = _plan(db)
    db.commit()
    fl.registrar_servicio(db, usuario(db), u, {"plan_id": aceite.id, "fecha": hoy(),
                                               "km": 50000, "costo": "3400"})
    db.commit()
    r = cliente.get(f"/lg/flota/unidades/{u.id}/disponibilidad?desde={hoy()}"
                    f"&hasta={hoy() + timedelta(days=7)}&km=2000", headers=karla)
    assert r.status_code == 200, r.text
    claves = [x["clave"] for x in r.json()["motivos"]]
    assert r.json()["estado"] == "alerta"
    assert claves.count("documento_vence_en_viaje") == 5
    assert "servicio_en_viaje" in claves
    # Un viaje que sale despues de que vencen sus documentos no sale.
    r = cliente.get(f"/lg/flota/unidades/{u.id}/disponibilidad"
                    f"?desde={hoy() + timedelta(days=6)}", headers=karla)
    assert r.json()["estado"] == "bloqueo"
    assert dispo.unidad(db, u.id)["estado"] == "libre"


# ====================================================== el tipo y el plan en pantalla

def test_las_llantas_del_tipo_y_el_plan_de_las_cajas(cliente, admin, karla, db):
    assert cliente.patch(f"/lg/flota/tipos/{tipo_id(db)}", headers=admin,
                         json={"llantas": 8}).status_code == 400
    r = cliente.patch(f"/lg/flota/tipos/{tipo_id(db)}", headers=admin,
                      json={"llantas": 6, "vida_llanta_km": 80000})
    assert r.status_code == 200, r.text
    tipo = next(t for t in r.json()["tipos"] if t["nombre"] == "1.5 ton")
    assert (tipo["llantas"], tipo["vida_llanta_km"]) == (6, 80000)
    r = cliente.post("/lg/flota/plan", headers=admin,
                     json={"clase": "remolque", "nombre": "Engrasado de quinta rueda",
                           "cada_km": 15000, "costo_aprox": 900})
    assert r.status_code == 201, r.text
    assert [p["nombre"] for p in r.json()["remolque"]] == ["Engrasado de quinta rueda"]
    assert cliente.post("/lg/flota/plan", headers=karla,
                        json={"clase": "remolque", "nombre": "X",
                              "cada_km": 1}).status_code == 403
    plan_id = r.json()["remolque"][0]["id"]
    r = cliente.patch(f"/lg/flota/plan/{plan_id}", headers=admin, json={"activo": False})
    assert r.json()["remolque"][0]["activo"] is False


# ====================================================== los avisos

def test_el_aviso_de_vencimiento_sale_una_vez(cliente, karla, db):
    """A 30 dias y el dia que vence, a quien lleva la flota; si nadie la
    lleva todavia, a quien la ve (la gerencia)."""
    u = unidad(db, numero_economico="07", economico_llave="7")
    actor = usuario(db)
    fl.capturar_documento(db, actor, "permiso_sct", unidad=u,
                          vence_en=hoy() + timedelta(days=20))
    fl.capturar_documento(db, actor, "poliza_seguro", unidad=u,
                          vence_en=hoy() - timedelta(days=1))
    fl.capturar_documento(db, actor, "gps", unidad=u,
                          vence_en=hoy() + timedelta(days=90))
    db.commit()
    assert fl.avisar_vencimientos(db) == {"previos": 1, "vencidos": 1}
    assert fl.avisar_vencimientos(db) == {"previos": 0, "vencidos": 0}
    correos = (db.query(m.Notificacion).filter(m.Notificacion.correo == KARLA)
               .order_by(m.Notificacion.id).all())
    asuntos = sorted(c.asunto for c in correos)
    assert len(asuntos) == 2
    assert any("Eco 07" in a and "permiso SCT" in a for a in asuntos), asuntos
    assert any("venció póliza de seguro" in a for a in asuntos), asuntos


def test_el_puesto_de_quien_lleva_la_flota(cliente, sesion, karla, db):
    """Nace con la migracion e2a4c6b8d0f1: edita la flota con el rol de
    Logistica, sin nada de Proteccion Ejecutiva, y los avisos de la flota
    le llegan a el y ya no a la gerencia."""
    h = sesion("dirgeneral")
    assert cliente.post("/auth/categorias/base", headers=h).status_code == 200
    puesto = next(x for x in cliente.get("/auth/categorias", headers=h).json()
                  if x["nombre"] == "Responsable de flota LG")
    quien = next(x for x in cliente.get("/auth/usuarios", headers=h).json()
                 if x["correo"] == CALIDAD)
    r = cliente.post(f"/auth/usuarios/{quien['usuario_id']}/categoria",
                     json={"categoria_id": puesto["categoria_id"]}, headers=h)
    assert r.status_code == 200, r.text
    flota = entrar(cliente, CALIDAD)
    yo = cliente.get("/auth/yo", headers=flota).json()
    assert yo["rol"] == "logistica"
    assert yo["pantallas"] == ["lg_catalogos", "lg_flota", "lg_jornada"]
    assert {"lg.flota.editar", "lg.operadores.editar"} <= set(yo["actividades"])
    assert not {"servicios.ver", "panorama.ver", "operacion.ver",
                "lg.catalogos.dinero"} & set(yo["actividades"])
    u = unidad(db)
    assert cliente.patch(f"/lg/flota/unidades/{u.id}", headers=flota,
                         json={"numero_economico": "11"}).status_code == 200
    db.expire_all()
    assert [x.correo for x in fl._a_quien(db, "lg.flota.editar", "lg.flota.ver")] == [CALIDAD]


# ====================================================== la bitacora

def test_la_bitacora_en_tres_idiomas(cliente, admin, db):
    u = unidad(db, numero_economico="09", economico_llave="9")
    cliente.post(f"/lg/flota/unidades/{u.id}/llantas", headers=admin,
                 json={"posicion": "R", "km": 14000})
    cliente.post(f"/lg/flota/unidades/{u.id}/odometro", headers=admin, json={"km": 15000})
    cliente.post(f"/lg/flota/unidades/{u.id}/documentos", headers=admin,
                 data={"tipo": "permiso_sct", "vence_en": "2027-03-31"})
    es = [x["que"] for x in cliente.get("/lg/flota/bitacora", headers=admin).json()["filas"]]
    assert es[0] == "Eco 09: permiso SCT · vence 31 mar 2027"
    # La lectura dice de que dia es: puede ser una de antes, capturada hoy.
    assert es[1] == f"Eco 09: odómetro 15,000 km del {lg_catalogos.fecha_texto(hoy(), 'es')}"
    en = [x["que"] for x in cliente.get("/lg/flota/bitacora?idioma=en",
                                        headers=admin).json()["filas"]]
    assert en[1] == f"Eco 09: odometer 15,000 km on {lg_catalogos.fecha_texto(hoy(), 'en')}"
    # La posicion de la llanta, con su nombre y no con su clave.
    assert (es[2], en[2]) == ("Eco 09: llanta nueva · Refacción", "Eco 09: new tire · Spare")
    pt = [x["que"] for x in cliente.get("/lg/flota/bitacora?idioma=pt",
                                        headers=admin).json()["filas"]]
    assert pt[0] == "Eco 09: licença SCT · vence 31 mar 2027"
    assert en[0] == "Eco 09: SCT permit · expires 31 Mar 2027"
    # Y en la bitacora de administracion, con su lugar.
    todo = cliente.get("/bitacora-admin?que=catalogos&mes=", headers=admin).json()
    nuestras = [x for x in todo["filas"] if x["objeto"] == "lg_unidades"]
    assert len(nuestras) == 3
    assert nuestras[0]["donde"] == "Logística · Flota"


def test_el_desglose_guardado_es_json_del_calculo(cliente, karla, db):
    costo_del_tipo(cliente, karla, db)
    u = unidad(db)
    fila = fl.guardar_costo(db, u, hoy(), "mensual")
    db.commit()
    assert json.loads(fila.desglose) == fl.calcular_costo(db, u)["desglose"]
    assert fl.guardar_costo(db, u, hoy(), "mensual") is None


def test_el_costo_del_mes_incompleto_se_completa(cliente, karla, db):
    """El dia 1 su tipo todavia no tenia costo: no se guarda un costo en
    cero --un viaje lo tomaria por bueno--; el de la unidad empieza el dia
    en que la gerencia lo captura. Lo completo ya no se mueve a media mes
    sin su porque."""
    u = unidad(db)
    assert fl.costos_del_mes(db) == {"guardados": 0, "completados": 0,
                                     "desde": hoy().replace(day=1).isoformat()}
    assert fl.costo_vigente(db, u.id) is None
    costo_del_tipo(cliente, karla, db)
    r = fl.costos_del_mes(db)
    if hoy().day == 1:
        # El dia 1 el del tipo ya rige desde el primero: es el del mes.
        assert (r["guardados"], r["completados"]) == (1, 0)
    else:
        assert (r["guardados"], r["completados"]) == (0, 1)
        db.expire_all()
        fila = fl.costo_vigente(db, u.id)
        assert (fila.origen, str(fila.total), fila.vigente_desde) == (
            "completo", "900.00", hoy())
    assert fl.costos_del_mes(db)["completados"] == 0
    if hoy().day == 1:
        return
    # Uno que el dia 1 se queda a medias --solo trae su valor de compra, y
    # su tipo todavia no tenia costo--: en la misma vuelta nace el del mes
    # y se completa desde hoy.
    v = unidad(db, "LGV7007")
    v.valor_compra, v.anios_vida = Decimal("365000"), Decimal("5")
    db.commit()
    assert fl.costos_del_mes(db) == {"guardados": 1, "completados": 1,
                                     "desde": hoy().replace(day=1).isoformat()}
    db.expire_all()
    filas = (db.query(m.LgCostoDia).filter_by(unidad_id=v.id)
             .order_by(m.LgCostoDia.vigente_desde).all())
    assert [(f.origen, f.vigente_desde, str(f.total) if f.origen == "mensual" else None,
             fl._faltan(json.loads(f.desglose))) for f in filas] == [
        ("mensual", hoy().replace(day=1), "200.00", 4), ("completo", hoy(), None, 0)]

"""Logistica, bloque 2: la carga inicial del Excel (seccion 151).

«Costos_unidades_Centauro_Logistica.xlsx», hojas «Unidades» y «Plan
preventivo». Todo o nada: si un solo renglon trae error no se carga nada,
y cada error dice su hoja, su renglon, su columna y que pasa, con la
sugerencia cuando la hay.
"""
import io
from decimal import Decimal

from openpyxl import Workbook

from ayudas_lg import admin, db, hoy, karla, logistica, unidad  # noqa: F401
from app import models as m

ENCABEZADO = ["Placas", "Número económico", "Tipo", "Rendimiento (km/l)",
              "Valor de compra", "Años de vida", "Seguro anual", "Tenencia y placas",
              "Verificación", "GPS", "Llantas por km", "Mantenimiento anual",
              "Odómetro", "Patio base"]
BUENA = ["LGA-1001", "Eco 01", "1.5 ton", 7, 600000, 5, 36500, 7300, 3650, 10950,
         0.5, 73000, 125000, "Base Cuautitlán"]
PLAN = [["Tipo de unidad", "Servicio", "Cada cuántos km", "Costo aproximado"],
        ["1.5 ton", "Cambio de aceite", 10000, 3500],
        ["1.5 ton", "Frenos", 40000, 6000],
        ["Caja seca", "Engrasado", 15000, 900]]


def _excel(unidades, plan=PLAN, encabezado=ENCABEZADO) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Unidades"
    hoja.append(encabezado)
    for fila in unidades:
        hoja.append(fila)
    if plan is not None:
        otra = libro.create_sheet("Plan preventivo")
        for fila in plan:
            otra.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _subir(cliente, h, contenido, aplicar=False, codigo=200):
    r = cliente.post("/lg/flota/carga", headers=h, data={"aplicar": str(aplicar).lower()},
                     files={"archivo": ("Costos_unidades_Centauro_Logistica.xlsx", contenido,
                                        "application/vnd.openxmlformats-officedocument."
                                        "spreadsheetml.sheet")})
    assert r.status_code == codigo, r.text
    return r.json()


def _flota(db):
    a = unidad(db, "LGA1001")
    b = unidad(db, "LGB2002", tipo=None)
    caja = unidad(db, "LGR5005", clase="remolque")
    return a, b, caja


def test_un_renglon_malo_no_deja_cargar_nada(cliente, admin, db):
    a, b, _ = _flota(db)
    mala = ["LGB2O02", "02", "4 ton", "24,34"] + BUENA[4:]
    r = _subir(cliente, admin, _excel([BUENA, mala]), aplicar=True)
    assert r["ok"] is False and r["cargado"] is False
    assert r["errores"] == [
        {"hoja": "Unidades", "renglon": 3, "columna": "Placas",
         "que": "«LGB2O02» no es de ninguna unidad de Centauro Logistic en Odoo. "
                "¿Será «LGB2002»?"}]
    db.expire_all()
    assert db.get(m.LgUnidad, a.id).numero_economico is None
    assert db.query(m.LgPlanServicio).count() == 0
    # Con la placa bien, sale el siguiente error del mismo renglon.
    mala[0] = "LGB2002"
    r = _subir(cliente, admin, _excel([BUENA, mala]), aplicar=True)
    assert [(e["renglon"], e["columna"]) for e in r["errores"]] == [(3, "Rendimiento")]
    assert "lleva coma" in r["errores"][0]["que"]
    assert db.query(m.LgCostoDia).count() == 0


def test_revisar_y_luego_cargar(cliente, admin, karla, db):
    a, b, caja = _flota(db)
    filas = [BUENA, ["LGB2002", "2", "4 ton", 6.5, None, None, None, None, None, None,
                     None, None, 98000, None],
             ["LGR5005", "C1", "Caja seca", None, 180000, 10]]
    # La gerencia no carga: lleva la flota quien la lleva.
    _subir(cliente, karla, _excel(filas), codigo=403)
    r = _subir(cliente, admin, _excel(filas))
    assert (r["ok"], r["cargado"], r["unidades"], r["plan"]) == (True, False, 3, 3)
    assert r["sin_columna"] == {}
    db.expire_all()
    assert db.get(m.LgUnidad, a.id).numero_economico is None      # solo se reviso
    r = _subir(cliente, admin, _excel(filas), aplicar=True)
    assert r["cargado"] is True
    db.expire_all()
    a, b, caja = (db.get(m.LgUnidad, x.id) for x in (a, b, caja))
    assert (a.numero_economico, a.economico_llave, a.tipo.nombre) == ("01", "1", "1.5 ton")
    assert (a.valor_compra, a.llantas_por_km, a.odometro_km) == (
        Decimal("600000.00"), Decimal("0.5000"), 125000)
    assert a.patio.nombre == "Base Cuautitlán"
    assert (b.tipo.nombre, b.rendimiento_ref, b.odometro_km) == ("4 ton", Decimal("6.50"), 98000)
    assert (caja.numero_economico, caja.valor_compra) == ("C1", Decimal("180000.00"))
    lectura = db.query(m.LgLecturaOdometro).filter_by(unidad_id=a.id).one()
    assert (lectura.km, lectura.fuente) == (125000, "carga")
    plan = {(p.clase, p.nombre): p for p in db.query(m.LgPlanServicio).all()}
    assert plan[("unidad", "Cambio de aceite")].cada_km == 10000
    assert plan[("remolque", "Engrasado")].tipo_id is None
    # El costo de cada una, desde el primero del mes, con su origen.
    costo = db.query(m.LgCostoDia).filter_by(unidad_id=a.id).one()
    assert (costo.vigente_desde, costo.origen) == (hoy().replace(day=1), "carga")
    filas_b = cliente.get("/lg/flota/bitacora", headers=admin).json()["filas"]
    assert filas_b[0]["que"] == "Carga inicial del Excel: 3 unidades"
    # Subirla otra vez no duplica el plan.
    _subir(cliente, admin, _excel(filas), aplicar=True)
    assert db.query(m.LgPlanServicio).count() == 3


def test_el_economico_repetido_y_el_intercambio(cliente, admin, db):
    a, b, _ = _flota(db)
    a.numero_economico, a.economico_llave = "01", "1"
    b.numero_economico, b.economico_llave = "02", "2"
    db.commit()
    repetido = [["LGA1001", "07"], ["LGB2002", "Eco 7"]]
    r = _subir(cliente, admin, _excel(repetido, plan=None,
                                      encabezado=["Placas", "Número económico"]))
    assert r["errores"] == [{"hoja": "Unidades", "renglon": 3, "columna": "Número económico",
                             "que": "«Eco 7» ya está en el renglón 2. Cada unidad necesita "
                                    "su propio número económico."}]
    # Contra una que no viene en el Excel, tambien.
    r = _subir(cliente, admin, _excel([["LGA1001", "2"]], plan=None,
                                      encabezado=["Placas", "Número económico"]))
    assert r["errores"][0]["que"] == "«2» ya es de la unidad con placas LGB2002."
    # Un intercambio entre dos del mismo Excel no es repetido.
    cambio = [["LGA1001", "02"], ["LGB2002", "01"]]
    r = _subir(cliente, admin, _excel(cambio, plan=None,
                                      encabezado=["Placas", "Número económico"]), aplicar=True)
    assert r["cargado"] is True, r["errores"]
    db.expire_all()
    assert (db.get(m.LgUnidad, a.id).economico_llave,
            db.get(m.LgUnidad, b.id).economico_llave) == ("2", "1")


def test_lo_que_no_se_entiende_se_dice(cliente, admin, db):
    _flota(db)
    r = _subir(cliente, admin, _excel([["LGA1001", "Rojo"]], plan=None,
                                      encabezado=["Placas", "Color"]))
    assert r["ok"] is True and r["sin_columna"] == {"Unidades": ["Color"]}
    r = _subir(cliente, admin, _excel([["01"]], plan=None, encabezado=["Económico"]))
    assert r["errores"][0]["que"].startswith("Falta la columna de las placas")
    filas = [["LGA1001", "", "Remolque"], ["LGR5005", "", "Torton 15 ton"],
             ["LGA1001", "", "Rabón"]]
    r = _subir(cliente, admin, _excel(filas, plan=[PLAN[0], ["Rabón", "Aceite", 5000, 1]],
                                      encabezado=["Placas", "Número económico", "Tipo"]))
    assert [(e["hoja"], e["renglon"], e["que"][:30]) for e in r["errores"]] == [
        ("Unidades", 2, "En Odoo no es una caja seca."),
        ("Unidades", 3, "Es una caja seca: su tipo va v"),
        ("Unidades", 4, "La placa ya está en el renglón"),
        ("Plan preventivo", 2, "«Rabón» no es un tipo de unida")]
    assert _subir(cliente, admin, b"no soy un excel", codigo=400)

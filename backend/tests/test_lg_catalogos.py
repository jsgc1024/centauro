"""Centauro Logistica, bloque 1: los catalogos con vigencia por fecha
(seccion 150).

Cada regla numerica lleva su prueba con los ejemplos de los bocetos: la
comision de los viajes LG-0001 a LG-0012 y del mapa operativo, el costo
por dia del operador y del 1.5 ton, el bono por antiguedad. Y las reglas
de la vigencia: cada valor rige desde su fecha, lo que ya rige no se
edita sino que se reemplaza con su porque, lo programado se corrige o se
quita, y la fecha pasada pide motivo.

Decisiones de Salvador, 3 oct: lo que decide dinero lo fija la gerencia de
Logistica; los tipos de unidad y los patios, sistema y calidad. Arranca
solo con los cuatro tipos y Base Cuautitlan.

Los catalogos de Logistica no se vacian con el movimiento: aqui se
vuelven a sembrar antes de cada prueba, y las cuentas que hacen de Karla y
de sistema y calidad se dejan como estaban.
"""
import importlib.util
import os
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import lg_catalogos as lg
from app import models as m
from app import permisos, puestos_base

KARLA = "finanzas2@centauro.lat"      # la cuenta sembrada que hace de ella
CALIDAD = "central2@centauro.lat"     # y la que hace de sistema y calidad
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRACION = os.path.join(RAIZ, "migrations", "versions",
                         "c6f1a3e5b7d9_logistica_catalogos.py")

# El tabulador propuesto en la especificacion: primeros 100 km y cada km
# cargado adicional, por tipo.
PROPUESTO = {"1.5 ton": ("220", "0.52"), "4 ton": ("240", "0.60"),
             "Torton 15 ton": ("290", "0.76"), "Tracto": ("450", "1.12")}
# El desglose de 1.5 ton del boceto de Flota.
UNIDAD_15 = {"rendimiento": 7, "compra": 547500, "anios": 4, "seguro": 34675,
             "mantenimiento": 94900, "llantas": 40150, "gps": 21900}


@pytest.fixture(autouse=True)
def logistica_limpia(base_de_pruebas):
    with base_de_pruebas.begin() as con:
        con.execute(text("TRUNCATE lg_valor, lg_patio, lg_tipo_unidad "
                         "RESTART IDENTITY CASCADE"))
        cuentas = con.execute(text(
            "SELECT id, rol, categoria_id FROM usuario WHERE correo IN (:a, :b)"),
            {"a": KARLA, "b": CALIDAD}).all()
    with Session(base_de_pruebas) as db:
        lg.sembrar(db)
        db.commit()
    yield
    with base_de_pruebas.begin() as con:
        for u in cuentas:
            con.execute(text("UPDATE usuario SET rol = :rol, categoria_id = :c "
                             "WHERE id = :id"),
                        {"rol": u.rol, "c": u.categoria_id, "id": u.id})


@pytest.fixture
def db(base_de_pruebas):
    with Session(base_de_pruebas) as sesion_db:
        yield sesion_db


def _entrar(cliente, correo):
    r = cliente.post("/auth/token",
                     data={"username": correo, "password": "centauro2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _con_rol(base_de_pruebas, correo, rol):
    with base_de_pruebas.begin() as con:
        con.execute(text("UPDATE usuario SET rol = :r, categoria_id = NULL "
                         "WHERE correo = :c"), {"r": rol, "c": correo})


@pytest.fixture
def karla(cliente, base_de_pruebas):
    """La gerencia de Logistica, entrando con su rol."""
    _con_rol(base_de_pruebas, KARLA, "LOGISTICA")
    return _entrar(cliente, KARLA)


@pytest.fixture
def calidad(cliente, base_de_pruebas):
    _con_rol(base_de_pruebas, CALIDAD, "SISTEMA_CALIDAD")
    return _entrar(cliente, CALIDAD)


def _tipos(db) -> dict:
    return {t.nombre: t.id for t in db.query(m.LgTipoUnidad).all()}


def _tabulador(db, montos=PROPUESTO, km_base=100) -> dict:
    ids = _tipos(db)
    return {"km_base": km_base,
            "tipos": {str(ids[n]): {"base": b, "por_km": p}
                      for n, (b, p) in montos.items()}}


def _poner(cliente, h, clave, desde, valor=None, datos=None, motivo=None,
           tipo_unidad_id=None, codigo=201):
    r = cliente.post("/lg/catalogos/valores", headers=h, json={
        "clave": clave, "vigente_desde": desde.isoformat(), "valor": valor,
        "datos": datos, "motivo": motivo, "tipo_unidad_id": tipo_unidad_id})
    assert r.status_code == codigo, r.text
    return r.json()


def _comision(cliente, h, tipo_id, km, fecha):
    r = cliente.get(f"/lg/catalogos/comision?tipo_unidad_id={tipo_id}&km={km}"
                    f"&fecha={fecha.isoformat()}", headers=h)
    return r


# ====================================================== los calculos, con los bocetos

TIPO = {"1.5 ton": 1, "4 ton": 2, "Torton 15 ton": 3, "Tracto": 4}
DATOS = {"km_base": 100, "tipos": {str(TIPO[n]): {"base": b, "por_km": p}
                                   for n, (b, p) in PROPUESTO.items()}}


@pytest.mark.parametrize("folio,tipo,km,debe", [
    ("LG-0001", "1.5 ton", 1484, "939.68"),
    ("LG-0007", "1.5 ton", 320, "334.40"),
    ("LG-0004", "Tracto", 1950, "2522.00"),
    ("LG-0003", "4 ton", 450, "450.00"),
    ("LG-0008", "4 ton", 900, "720.00"),
    ("LG-0005", "Torton 15 ton", 1200, "1126.00"),
    ("LG-0002", "1.5 ton", 180, "261.60"),
    ("LG-0006", "1.5 ton", 600, "480.00"),
    ("LG-0012", "1.5 ton", 260, "303.20"),
])
def test_la_comision_de_los_viajes_del_boceto(folio, tipo, km, debe):
    assert lg.comision_con(DATOS, TIPO[tipo], km)["comision"] == Decimal(debe), folio


@pytest.mark.parametrize("tipo,debe", [("1.5 ton", "922.00"), ("4 ton", "1050.00"),
                                       ("Torton 15 ton", "1316.00"),
                                       ("Tracto", "1962.00")])
def test_el_mapa_operativo_de_1450_km(tipo, debe):
    assert lg.comision_con(DATOS, TIPO[tipo], 1450)["comision"] == Decimal(debe)


def test_el_viaje_corto_cobra_el_monto_completo():
    assert lg.comision_con(DATOS, 1, 60)["comision"] == Decimal("220.00")
    assert lg.comision_con(DATOS, 1, 100)["comision"] == Decimal("220.00")
    assert lg.comision_con(DATOS, 1, 101)["comision"] == Decimal("220.52")
    # Un tipo que el tabulador no trae no se paga con otro.
    assert lg.comision_con(DATOS, 99, 500) is None


def test_el_costo_del_operador_por_dia():
    assert lg.costo_operador_con({"costo_mensual": "11700",
                                  "dias_laborables": 26}) == Decimal("450.00")


def test_el_costo_por_dia_del_15_ton():
    c = lg.costo_unidad_con({k: str(v) for k, v in UNIDAD_15.items()})
    assert (c["depreciacion"], c["seguro"], c["mantenimiento"], c["llantas"],
            c["gps"]) == (Decimal("375.00"), Decimal("95.00"), Decimal("260.00"),
                          Decimal("110.00"), Decimal("60.00"))
    assert c["costo_dia"] == Decimal("900.00")


@pytest.mark.parametrize("anios,pct", [(0, "10"), (2, "10"), (3, "10"), (4, "20"),
                                       (12, "20")])
def test_el_bono_por_antiguedad(anios, pct):
    datos = {"tramos": [{"desde_anios": 0, "pct": "10"}, {"desde_anios": 4, "pct": "20"}],
             "dias_requeridos": 5}
    assert lg.bono_con(datos, anios) == Decimal(pct)


# ====================================================== como arranca

def test_arranca_solo_con_los_tipos_y_base_cuautitlan(cliente, karla):
    r = cliente.get("/lg/catalogos", headers=karla)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [(t["nombre"], t["nombre_tango"]) for t in d["tipos"]] == [
        ("1.5 ton", "1.5 t"), ("4 ton", "4 t seco"), ("Torton 15 ton", "TH"),
        ("Tracto", "Tracto")]
    assert [t["capacidad_ton"] for t in d["tipos"]] == ["1.5", "4", "15", None]
    assert [(p["nombre"], p["lat"], p["geocerca_metros"]) for p in d["patios"]] == [
        ("Base Cuautitlán", None, 300)]
    # Ningun monto: todo lo que decide dinero dice que falta.
    assert all(not filas for filas in d["valores"].values())
    for catalogo in lg.DE_DINERO:
        assert d["faltas"][catalogo], catalogo
    assert d["faltas"]["tipos"] == []
    assert d["faltas"]["patios"] == ["Base Cuautitlán"]       # sin ubicacion
    assert d["puede"] == {"dinero": True, "editar": False, "buscar": False}


def test_la_semilla_y_la_migracion_dicen_lo_mismo():
    spec = importlib.util.spec_from_file_location("migracion_lg", MIGRACION)
    migracion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracion)
    assert [tuple(t) for t in migracion.TIPOS] == [tuple(t) for t in lg.TIPOS_DE_ARRANQUE]
    assert (migracion.PATIO, migracion.GEOCERCA) == lg.PATIO_DE_ARRANQUE
    puesto = next(p for p in puestos_base.PUESTOS if p["nombre"] == migracion.NOMBRE)
    assert puesto["rol"] == m.Rol.LOGISTICA
    assert puesto["descripcion"] == migracion.DESCRIPCION
    assert puesto["pantallas"] == migracion.PANTALLAS.split(",")
    assert puesto["actividades"] == set(migracion.ACTIVIDADES)
    assert puesto["puestos_odoo"] == migracion.PUESTOS_ODOO
    calidad = next(p for p in puestos_base.PUESTOS
                   if p["rol"] == m.Rol.SISTEMA_CALIDAD)
    assert set(migracion.A_SISTEMA) <= calidad["actividades"]
    assert "lg_catalogos" in calidad["pantallas"]


# ====================================================== la vigencia

def test_cada_viaje_toma_el_tabulador_de_su_fecha(cliente, karla, db):
    """Un viaje el dia antes y el dia del cambio de tabulador: el viejo y
    el nuevo."""
    hoy = lg.hoy_lg()
    viejo = {n: ("200", "0.50") for n in PROPUESTO}
    _poner(cliente, karla, "tabulador", hoy - timedelta(days=10),
           datos=_tabulador(db, viejo), motivo="El de tramos de Tango, como referencia")
    _poner(cliente, karla, "tabulador", hoy - timedelta(days=3),
           datos=_tabulador(db), motivo="El propuesto, desde el lunes")
    tipo = _tipos(db)["1.5 ton"]
    antes = _comision(cliente, karla, tipo, 1484, hoy - timedelta(days=4))
    assert antes.status_code == 200, antes.text
    assert antes.json()["comision"] == "892.00"            # 200 + 1384 x 0.50
    el_dia = _comision(cliente, karla, tipo, 1484, hoy - timedelta(days=3)).json()
    assert el_dia["comision"] == "939.68"
    assert el_dia["vigente_desde"] == (hoy - timedelta(days=3)).isoformat()
    # Antes del primero no hay tabulador, y se dice.
    r = _comision(cliente, karla, tipo, 1484, hoy - timedelta(days=11))
    assert r.status_code == 400 and "tabulador" in r.json()["detail"]["mensaje"].lower()


def test_la_fecha_pasada_pide_su_porque(cliente, karla):
    ayer = lg.hoy_lg() - timedelta(days=1)
    r = _poner(cliente, karla, "diesel", ayer, valor=24.18, codigo=400)
    assert "ya pasó" in r["detail"]["mensaje"]
    _poner(cliente, karla, "diesel", ayer, valor=24.18,
           motivo="No se capturó el cambio; lo confirmó la factura de la estación")


def test_lo_que_ya_rige_no_se_edita_se_reemplaza(cliente, karla, db):
    hoy = lg.hoy_lg()
    malo = _poner(cliente, karla, "diesel", hoy, valor=42.34)
    # El mismo dia otra vez: pide el porque.
    r = _poner(cliente, karla, "diesel", hoy, valor=24.34, codigo=400)
    assert "rige desde esa fecha" in r["detail"]["mensaje"]
    bueno = _poner(cliente, karla, "diesel", hoy, valor=24.34,
                   motivo="se capturó con los dígitos al revés")
    assert lg.numero(db, "diesel") == Decimal("24.34")
    d = cliente.get("/lg/catalogos", headers=karla).json()
    estados = {v["id"]: v["estado"] for v in d["valores"]["diesel"]}
    assert estados == {malo["id"]: "reemplazado", bueno["id"]: "vigente"}
    assert d["vigentes"]["diesel"]["valor"] == "24.34"
    # Ni se edita ni se quita lo que ya rige.
    r = cliente.put(f"/lg/catalogos/valores/{bueno['id']}", headers=karla,
                    json={"vigente_desde": (hoy + timedelta(days=2)).isoformat(),
                          "valor": 25})
    assert r.status_code == 400 and "no se edita" in r.json()["detail"]["mensaje"]
    r = cliente.delete(f"/lg/catalogos/valores/{bueno['id']}", headers=karla)
    assert r.status_code == 400 and "no se quita" in r.json()["detail"]["mensaje"]
    # El reemplazado se queda: un viaje que lo uso puede apuntar a el.
    assert db.get(m.LgValor, malo["id"]).reemplazado_por_id == bueno["id"]


def test_lo_programado_se_corrige_y_se_quita(cliente, karla, db):
    hoy = lg.hoy_lg()
    _poner(cliente, karla, "diesel", hoy, valor=24.34)
    lunes = _poner(cliente, karla, "diesel", hoy + timedelta(days=2), valor=24.51)
    # Hoy sigue el de hoy; el programado rige desde su dia.
    assert lg.numero(db, "diesel") == Decimal("24.34")
    assert lg.numero(db, "diesel", hoy + timedelta(days=2)) == Decimal("24.51")
    # Se corrige: otro renglon, y el de antes queda marcado.
    r = cliente.put(f"/lg/catalogos/valores/{lunes['id']}", headers=karla,
                    json={"vigente_desde": (hoy + timedelta(days=3)).isoformat(),
                          "valor": 24.60})
    assert r.status_code == 200, r.text
    nuevo = r.json()["id"]
    db.expire_all()
    assert db.get(m.LgValor, lunes["id"]).reemplazado_por_id == nuevo
    assert lg.numero(db, "diesel", hoy + timedelta(days=2)) == Decimal("24.34")
    assert lg.numero(db, "diesel", hoy + timedelta(days=3)) == Decimal("24.60")
    # Moverlo a hoy no: eso es un valor nuevo.
    r = cliente.put(f"/lg/catalogos/valores/{nuevo}", headers=karla,
                    json={"vigente_desde": hoy.isoformat(), "valor": 24.60})
    assert r.status_code == 400
    # Y se quita.
    assert cliente.delete(f"/lg/catalogos/valores/{nuevo}",
                          headers=karla).status_code == 200
    db.expire_all()
    assert lg.numero(db, "diesel", hoy + timedelta(days=30)) == Decimal("24.34")
    d = cliente.get("/lg/catalogos", headers=karla).json()
    assert sorted(v["estado"] for v in d["valores"]["diesel"]) == [
        "quitado", "reemplazado", "vigente"]


def test_un_reemplazado_y_un_programado(cliente, karla, db):
    """Rige el bueno; el programado todavia no."""
    hoy = lg.hoy_lg()
    _poner(cliente, karla, "margen", hoy - timedelta(days=5), valor=12,
           motivo="El de arranque")
    _poner(cliente, karla, "margen", hoy - timedelta(days=5), valor=15,
           motivo="Era 15, no 12")
    _poner(cliente, karla, "margen", hoy + timedelta(days=7), valor=18)
    assert lg.numero(db, "margen") == Decimal("15")
    assert lg.numero(db, "margen", hoy + timedelta(days=7)) == Decimal("18")
    d = cliente.get("/lg/catalogos", headers=karla).json()
    assert d["vigentes"]["margen"]["valor"] == "15"
    assert d["faltas"]["alimentos"] == ["alimentos"]


# ====================================================== los costos y el bono

def test_el_costo_del_operador_y_de_cada_tipo(cliente, karla, db):
    hoy = lg.hoy_lg()
    _poner(cliente, karla, "operador", hoy,
           datos={"costo_mensual": 11700, "dias_laborables": 26})
    tipo = _tipos(db)["1.5 ton"]
    _poner(cliente, karla, "unidad", hoy, datos=UNIDAD_15, tipo_unidad_id=tipo)
    d = cliente.get("/lg/catalogos", headers=karla).json()
    assert d["vigentes"]["operador"]["calculo"]["costo_dia"] == "450.00"
    u = d["vigentes"]["unidad"][str(tipo)]
    assert u["calculo"]["costo_dia"] == "900.00"
    assert u["calculo"]["depreciacion"] == "375.00"
    assert d["faltas"]["costos"] == ["4 ton", "Torton 15 ton", "Tracto"]
    assert d["faltas"]["operador"] == []
    assert lg.costo_operador(db)["costo_dia"] == Decimal("450.00")
    assert lg.costo_unidad(db, tipo)["rendimiento"] == Decimal("7")
    with pytest.raises(lg.FaltaValor):
        lg.costo_unidad(db, _tipos(db)["Tracto"])
    # El de un tipo pide su tipo.
    _poner(cliente, karla, "unidad", hoy, datos=UNIDAD_15, codigo=400)


def test_el_bono_y_la_garantia(cliente, karla, db):
    hoy = lg.hoy_lg()
    _poner(cliente, karla, "bono", hoy, datos={
        "tramos": [{"desde_anios": 4, "pct": 20}, {"desde_anios": 0, "pct": 10}],
        "dias_requeridos": 5})
    assert lg.bono_pct(db, 2) == Decimal("10")
    assert lg.bono_pct(db, 4) == Decimal("20")
    tracto = _tipos(db)["Tracto"]
    _poner(cliente, karla, "garantia", hoy, datos={
        "tipo_unidad_id": tracto, "monto_semanal": 3000,
        "exige_dias_completos": True, "bono_sobre_garantia": False})
    d = cliente.get("/lg/catalogos", headers=karla).json()
    assert d["vigentes"]["garantia"]["datos"] == {
        "tipo_unidad_id": tracto, "monto_semanal": "3000",
        "exige_dias_completos": True, "bono_sobre_garantia": False}
    assert d["faltas"]["bono"] == []


@pytest.mark.parametrize("clave,valor,datos,dice", [
    ("diesel", 0, None, "mayor que 0"),
    ("diesel", 243.40, None, "no puede pasar de 100"),
    ("diesel", "24,34", None, "no es un número"),
    ("holgura", 120, None, "no puede pasar de 100"),
    ("alimentos", None, None, "Falta"),
    ("bono", None, {"tramos": [{"desde_anios": 1, "pct": 10}], "dias_requeridos": 5},
     "empieza en 0"),
    ("garantia", None, {"tipo_unidad_id": 4, "monto_semanal": 3000}, "dos reglas"),
    ("operador", None, {"costo_mensual": 11700, "dias_laborables": 26.5}, "sin decimales"),
    ("nada", 1, None, "No existe"),
])
def test_lo_que_no_se_guarda(cliente, karla, clave, valor, datos, dice):
    r = _poner(cliente, karla, clave, lg.hoy_lg(), valor=valor, datos=datos, codigo=400)
    assert dice in r["detail"]["mensaje"], r


def test_el_tabulador_va_completo(cliente, karla, db):
    sin_tracto = {k: v for k, v in PROPUESTO.items() if k != "Tracto"}
    r = _poner(cliente, karla, "tabulador", lg.hoy_lg(),
               datos=_tabulador(db, sin_tracto), codigo=400)
    assert "Tracto" in r["detail"]["mensaje"]


# ====================================================== quien puede que

@pytest.mark.parametrize("quien,ve", [("consultor", 403), ("finanzas", 403),
                                      ("diroperaciones", 403), ("central", 403),
                                      ("rrhh", 403), ("dirgeneral", 200),
                                      ("admin", 200)])
def test_quien_los_ve(cliente, sesion, quien, ve):
    assert cliente.get("/lg/catalogos", headers=sesion(quien)).status_code == ve


def test_karla_fija_el_dinero_y_no_los_tipos(cliente, karla):
    assert cliente.post("/lg/catalogos/tipos", headers=karla,
                        json={"nombre": "Rabón"}).status_code == 403
    assert cliente.post("/lg/catalogos/patios", headers=karla,
                        json={"nombre": "Base Monterrey"}).status_code == 403
    _poner(cliente, karla, "alimentos", lg.hoy_lg(), valor=325)


def test_sistema_y_calidad_lleva_tipos_y_patios_y_no_el_dinero(cliente, calidad, db):
    d = cliente.get("/lg/catalogos", headers=calidad).json()
    assert d["puede"] == {"dinero": False, "editar": True, "buscar": True}
    _poner(cliente, calidad, "alimentos", lg.hoy_lg(), valor=325, codigo=403)
    r = cliente.post("/lg/catalogos/tipos", headers=calidad,
                     json={"nombre": "Rabón", "capacidad_ton": 8, "nombre_tango": "RB"})
    assert r.status_code == 201, r.text
    rabon = r.json()["id"]
    # El nombre no se repite, ni con otras mayusculas.
    assert cliente.post("/lg/catalogos/tipos", headers=calidad,
                        json={"nombre": "rabón"}).status_code == 400
    d = cliente.get("/lg/catalogos", headers=calidad).json()
    assert d["tipos"][-1]["nombre"] == "Rabón" and d["tipos"][-1]["orden"] == 5
    # Quitarlo no lo borra; reactivarlo lo devuelve.
    assert cliente.delete(f"/lg/catalogos/tipos/{rabon}", headers=calidad).status_code == 200
    assert not db.get(m.LgTipoUnidad, rabon).activo
    assert cliente.post(f"/lg/catalogos/tipos/{rabon}/reactivar",
                        headers=calidad).status_code == 200
    # El patio toma su punto de Google, redondeado a siete decimales.
    patio = d["patios"][0]["id"]
    r = cliente.patch(f"/lg/catalogos/patios/{patio}", headers=calidad, json={
        "nombre": "Base Cuautitlán", "direccion": "Cuautitlán Izcalli, Méx.",
        "lat": 19.6545123456789, "lon": -99.2012345678901, "geocerca_metros": 300})
    assert r.status_code == 200, r.text
    db.expire_all()
    p = db.get(m.LgPatio, patio)
    assert p.lat == Decimal("19.6545123") and p.lon == Decimal("-99.2012346")
    r = cliente.patch(f"/lg/catalogos/patios/{patio}", headers=calidad, json={
        "nombre": "Base Cuautitlán", "lat": 19.65, "geocerca_metros": 300})
    assert r.status_code == 400 and "latitud y longitud" in r.json()["detail"]["mensaje"]
    d = cliente.get("/lg/catalogos", headers=calidad).json()
    assert d["faltas"]["patios"] == []


def test_un_tipo_nuevo_le_falta_al_tabulador(cliente, karla, calidad, db):
    _poner(cliente, karla, "tabulador", lg.hoy_lg(), datos=_tabulador(db))
    assert cliente.post("/lg/catalogos/tipos", headers=calidad,
                        json={"nombre": "Rabón"}).status_code == 201
    d = cliente.get("/lg/catalogos", headers=karla).json()
    assert d["faltas"]["tabulador"] == ["Rabón"]
    assert d["faltas"]["costos"][-1] == "Rabón"


# ====================================================== el puesto

def test_el_puesto_de_la_gerencia_de_logistica(cliente, sesion):
    p = next(x for x in puestos_base.PUESTOS if x["nombre"] == "Gerente de Logística")
    assert p["actividades"] == {"lg.catalogos.ver", "lg.catalogos.dinero"}
    for actividad in p["actividades"]:
        assert actividad in permisos.ACTIVIDADES
    h = sesion("dirgeneral")
    assert cliente.post("/auth/categorias/base", headers=h).status_code == 200
    puestos = {x["nombre"]: x for x in cliente.get("/auth/categorias", headers=h).json()}
    puesto = puestos["Gerente de Logística"]
    u = next(x for x in cliente.get("/auth/usuarios", headers=h).json()
             if x["correo"] == KARLA)
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/categoria",
                     json={"categoria_id": puesto["categoria_id"]}, headers=h)
    assert r.status_code == 200, r.text
    yo = cliente.get("/auth/yo", headers=_entrar(cliente, KARLA)).json()
    assert yo["rol"] == "logistica"
    assert yo["puesto"] == "Gerente de Logística"
    assert yo["pantallas"] == ["lg_catalogos"]
    assert {"lg.catalogos.ver", "lg.catalogos.dinero"} <= set(yo["actividades"])
    assert "lg.catalogos.editar" not in yo["actividades"]
    # Ni un aviso de Proteccion Ejecutiva: nada de la operacion.
    assert not {"servicios.ver", "panorama.ver", "operacion.ver"} & set(yo["actividades"])


# ====================================================== la bitacora

def test_la_bitacora_cuenta_cada_cambio(cliente, karla, sesion, db):
    hoy = lg.hoy_lg()
    _poner(cliente, karla, "diesel", hoy, valor=42.34)
    _poner(cliente, karla, "diesel", hoy, valor=24.34,
           motivo="se capturó con los dígitos al revés")
    _poner(cliente, karla, "diesel", hoy + timedelta(days=2), valor=24.51)
    r = cliente.get("/lg/catalogos/bitacora?catalogo=diesel", headers=karla)
    assert r.status_code == 200, r.text
    que = [x["que"] for x in r.json()["filas"]]
    assert que[0].startswith("Programó Precio del diésel: $24.51 por litro")
    assert que[1].startswith("Reemplazó Precio del diésel: $42.34 por litro → "
                             "$24.34 por litro, desde el ")
    assert que[1].endswith(": «se capturó con los dígitos al revés»")
    assert que[2].startswith("Precio del diésel: $42.34 por litro, desde el ")
    assert {x["quien"] for x in r.json()["filas"]} == {"Maria Cruz"}
    assert r.json()["filas"][0]["donde"] == "Logística · Diésel y anticipo"
    # En los otros idiomas, la misma frase en la suya.
    en = cliente.get("/lg/catalogos/bitacora?catalogo=diesel&idioma=en",
                     headers=karla).json()["filas"]
    assert en[0]["que"].startswith("Scheduled Diesel price: $24.51 per litre")
    pt = cliente.get("/lg/catalogos/bitacora?catalogo=diesel&idioma=pt",
                     headers=karla).json()["filas"]
    assert pt[1]["que"].startswith("Substituiu Preço do diesel")
    # Y en la bitacora de administracion, con los catalogos.
    todo = cliente.get("/bitacora-admin?que=catalogos&mes=", headers=sesion("admin")).json()
    nuestras = [x for x in todo["filas"] if x["objeto"] == "lg_diesel"]
    assert len(nuestras) == 3
    assert nuestras[0]["donde"] == "Logística · Diésel y anticipo"
    assert nuestras[0]["que"] == que[0]


def test_la_bitacora_de_tipos_y_patios(cliente, calidad):
    r = cliente.post("/lg/catalogos/tipos", headers=calidad,
                     json={"nombre": "Rabón", "capacidad_ton": 8})
    rabon = r.json()["id"]
    cliente.patch(f"/lg/catalogos/tipos/{rabon}", headers=calidad,
                  json={"nombre": "Rabón", "capacidad_ton": 9, "nombre_tango": "RB",
                        "orden": 5})
    cliente.delete(f"/lg/catalogos/tipos/{rabon}", headers=calidad)
    filas = cliente.get("/lg/catalogos/bitacora?catalogo=tipos",
                        headers=calidad).json()["filas"]
    assert [x["que"] for x in filas] == [
        "Quitó «Rabón»",
        "«Rabón»: capacidad (t) 8 → 9; en Tango ninguno → RB",
        "Agregó el tipo «Rabón»"]


# ====================================================== la consola

def _web(nombre):
    return open(os.path.join(RAIZ, "app", "web", nombre), encoding="utf-8").read()


def test_el_menu_la_ruta_y_el_sello():
    menu = _web("menu.js")
    assert 'clave: "lg_catalogos", necesita: "lg.catalogos.ver"' in menu
    # Su grupo va entre Operaciones EP y Operaciones CI.
    assert menu.index('grupo: "nav_operaciones_lg"') < menu.index('clave: "central"')
    assert 'logistica: "lg_catalogos"' in menu
    app_js = _web("app.js")
    assert "pantallaLgCatalogos" in app_js and "lg\\/catalogos" in app_js
    # El encabezado: AI/INT en Connect y AI/LG dentro de Logistica.
    assert 'const LINEA = "AI/INT";' in app_js and 'const LINEA_LG = "AI/LG";' in app_js
    assert '"AI/EP"' not in app_js
    assert "lg_catalogos" in permisos.PANTALLAS

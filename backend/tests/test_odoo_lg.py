"""Logistica, bloque 2: las unidades y los operadores, leidos de Odoo
(seccion 151).

Lo que dijo Odoo el 3 de octubre: las unidades de Logistica son las de la
compania 3, «Centauro Logistic SA CV» (solo una traia la etiqueta); entre
ellas dos cajas secas y un Prius utilitario. Los operadores son los de esa
compania con puesto «Operador». Decision de Salvador: las cajas entran sin
asignarse solas; el Prius no.

Como las lecturas de EP: nunca escribe en Odoo, primero el ensayo, lo de
Odoo se toma de Odoo y lo de Connect no se toca, y una lectura que trae
cero con unidades activas se detiene.
"""
from datetime import date

from ayudas_lg import db, logistica, operador, tipo_id, unidad  # noqa: F401
from app import models as m
from app import odoo_lg
from app import odoo_oficina_reglas as oficina

L = [3, "Centauro Logistic SA CV"]


def _vehiculo(i, placa, categoria, modelo="International/4300", anio="2019", **extra):
    return {"id": i, "license_plate": placa, "category_id": [10 + i, categoria],
            "model_id": [20 + i, modelo], "model_year": anio, "vin_sn": f"3HAMMAAR{i:09d}",
            "company_id": L, **extra}


def _empleado(i, nombre, puesto="Operador", correo=None, ingreso="2019-03-01"):
    return {"id": i, "name": nombre, "job_id": [5, puesto], "job_title": puesto,
            "private_email": correo or f"{nombre.split()[0].lower()}@gmail.com",
            "mobile_phone": "55 1111 2222", "private_phone": False,
            "first_contract_date": ingreso, "company_id": L}


class OdooFalso:
    def __init__(self, vehiculos=(), empleados=()):
        # Copias: una prueba que cambia lo que dice Odoo no se lo cambia
        # a la siguiente.
        self.vehiculos = [dict(x) for x in vehiculos]
        self.empleados = [dict(x) for x in empleados]
        self.lecturas = []

    def leer(self, modelo, dominio, campos, archivados=False, idioma=None, compania=None):
        self.lecturas.append((modelo, dominio, compania))
        assert dominio == [["company_id", "=", 3]] and compania == 3
        return [dict(x) for x in (self.vehiculos if modelo == "fleet.vehicle"
                                  else self.empleados)]

    def campos(self, modelo, atributos=None):
        return {"license_plate": {}, odoo_lg.IAVE: {}}


FLOTA = [_vehiculo(1, "LGA-1001", "1 Tonelada", x_studio_iave="IAVE-001"),
         _vehiculo(2, "lgb 2002", "Torton"),
         _vehiculo(3, "LGR5005", "Remolque", modelo="Fruehauf/Caja seca"),
         _vehiculo(4, "PRI0004", "Utilitario", modelo="Toyota/Prius"),
         _vehiculo(5, "", "Tracto")]


def test_la_clase_y_el_tipo_que_sugiere_la_categoria():
    assert odoo_lg.clase_de("Remolque") == "remolque"
    assert odoo_lg.clase_de("Utilitario") is None
    assert odoo_lg.clase_de("Torton") == "unidad"
    assert odoo_lg.tipo_sugerido("1 Tonelada") == "1.5 ton"
    assert odoo_lg.tipo_sugerido("4 Toneladas") == "4 ton"
    assert odoo_lg.tipo_sugerido("Torton") == "Torton 15 ton"
    assert odoo_lg.tipo_sugerido("TR") == "Tracto"
    assert odoo_lg.tipo_sugerido("Remolque") is None
    assert odoo_lg.tipo_sugerido("Camioneta") is None


def test_el_ensayo_no_toca_nada_y_aplicar_si(db):
    odoo = OdooFalso(FLOTA)
    r = odoo_lg.sincronizar_flota(db, odoo, ensayo=True)
    assert (r["ensayo"], r["leidos"]) == (True, 5)
    assert [x["placa"] for x in r["altas"]] == ["LGA1001", "LGB2002", "LGR5005"]
    assert [x["placa"] for x in r["fuera"]] == ["PRI0004"]
    assert r["pendientes"] == [{"odoo_id": 5, "placa": None, "motivo": "sin placa en Odoo"}]
    assert db.query(m.LgUnidad).count() == 0
    r = odoo_lg.sincronizar_flota(db, odoo, ensayo=False, quien=None)
    db.expire_all()
    unidades = {u.placa: u for u in db.query(m.LgUnidad).all()}
    assert set(unidades) == {"LGA1001", "LGB2002", "LGR5005"}
    a = unidades["LGA1001"]
    assert (a.clase, a.tipo.nombre, a.marca_modelo, a.anio, a.iave) == (
        "unidad", "1.5 ton", "International 4300", 2019, "IAVE-001")
    assert unidades["LGR5005"].clase == "remolque" and unidades["LGR5005"].tipo_id is None
    assert db.query(m.SincronizacionOdoo).filter_by(tipo="lg_flota").count() == 1


def test_lo_de_connect_no_se_toca_y_la_que_ya_no_viene_se_da_de_baja(db):
    odoo = OdooFalso(FLOTA[:3])
    odoo_lg.sincronizar_flota(db, odoo, ensayo=False)
    a = db.query(m.LgUnidad).filter_by(placa="LGA1001").one()
    a.numero_economico, a.economico_llave, a.tipo_id = "01", "1", tipo_id(db, "4 ton")
    db.commit()
    # Odoo cambia el ano y quita la caja.
    odoo.vehiculos[0]["model_year"] = "2020"
    odoo.vehiculos = odoo.vehiculos[:2]
    r = odoo_lg.sincronizar_flota(db, odoo, ensayo=False)
    assert [c["cambios"] for c in r["cambios"]] == [{"anio": [2019, 2020]}]
    assert [b["placa"] for b in r["bajas"]] == ["LGR5005"]
    db.expire_all()
    a = db.query(m.LgUnidad).filter_by(placa="LGA1001").one()
    assert (a.anio, a.numero_economico, a.tipo.nombre) == (2020, "01", "4 ton")
    caja = db.query(m.LgUnidad).filter_by(placa="LGR5005").one()
    assert caja.activo is False and caja.baja_odoo_en is not None
    # Si regresa, vuelve a estar activa.
    odoo.vehiculos.append(dict(FLOTA[2]))
    odoo_lg.sincronizar_flota(db, odoo, ensayo=False)
    db.expire_all()
    caja = db.query(m.LgUnidad).filter_by(placa="LGR5005").one()
    assert caja.activo is True and caja.baja_odoo_en is None


def test_la_unidad_capturada_antes_se_vincula_por_su_placa(db):
    a = unidad(db, "LGA1001", numero_economico="01", economico_llave="1")
    r = odoo_lg.sincronizar_flota(db, OdooFalso(FLOTA[:1]), ensayo=False)
    assert [x["id"] for x in r["vinculadas"]] == [a.id] and r["altas"] == []
    db.expire_all()
    assert db.get(m.LgUnidad, a.id).odoo_id == 1


def test_la_lectura_en_cero_se_detiene(db):
    odoo_lg.sincronizar_flota(db, OdooFalso(FLOTA[:3]), ensayo=False)
    r = odoo_lg.sincronizar_flota(db, OdooFalso([]), ensayo=False)
    assert r["detenida"] is True
    assert db.query(m.LgUnidad).filter_by(activo=True).count() == 3
    odoo_lg.sincronizar_operadores(db, OdooFalso(empleados=[_empleado(1, "Ana Ruiz")]),
                                   ensayo=False)
    r = odoo_lg.sincronizar_operadores(db, OdooFalso(empleados=[
        _empleado(9, "Karla Rios", puesto="Gerente de Logística")]), ensayo=False)
    assert r["detenida"] is True
    assert db.query(m.LgOperador).filter_by(activo=True).count() == 1


# ====================================================== los operadores

def test_solo_los_operadores_y_cada_uno_con_su_correo(db):
    gente = [_empleado(1, "Ana Ruiz", ingreso="2018-02-10"),
             _empleado(2, "Beto Sanz", correo="mismo@gmail.com"),
             _empleado(3, "Ciro Paz", correo="mismo@gmail.com"),
             _empleado(4, "Karla Rios", puesto="Gerente de Logística"),
             _empleado(5, "Dora Gil", puesto="Operador de Tracto")]
    r = odoo_lg.sincronizar_operadores(db, OdooFalso(empleados=gente), ensayo=False)
    assert sorted(x["nombre"] for x in r["altas"]) == [
        "Ana Ruiz", "Beto Sanz", "Ciro Paz", "Dora Gil"]
    assert sorted(x["nombre"] for x in r["pendientes"]) == ["Beto Sanz", "Ciro Paz"]
    # La gerente no entra, pero se cuenta: el ensayo dice 5 leidos.
    assert (r["leidos"], r["otros"]) == (5, 1)
    db.expire_all()
    por_nombre = {o.nombre: o for o in db.query(m.LgOperador).all()}
    assert por_nombre["Ana Ruiz"].correo == "ana@gmail.com"
    assert por_nombre["Ana Ruiz"].fecha_ingreso == date(2018, 2, 10)
    assert por_nombre["Beto Sanz"].correo is None and por_nombre["Ciro Paz"].correo is None


def test_la_baja_del_operador_cierra_su_acceso(db):
    o = operador(db, "Ana Ruiz", "ana@gmail.com", odoo_id=1, ingreso=date(2019, 3, 1),
                 telefono="55 1111 2222")
    r = odoo_lg.sincronizar_operadores(db, OdooFalso(empleados=[
        _empleado(1, "Ana Ruiz"), _empleado(2, "Beto Sanz")]), ensayo=False)
    assert r["cambios"] == [] and [x["nombre"] for x in r["altas"]] == ["Beto Sanz"]
    odoo_lg.sincronizar_operadores(db, OdooFalso(empleados=[_empleado(2, "Beto Sanz")]),
                                   ensayo=False)
    db.expire_all()
    o = db.get(m.LgOperador, o.id)
    assert o.activo is False and o.sesiones_desde is not None


def test_la_de_cada_hora_espera_a_la_primera_a_mano(db):
    r = odoo_lg.sincronizar_si_toca(db, OdooFalso(FLOTA[:2]))
    assert r == {"lg_flota": {"omitido": "falta la primera lectura a mano"},
                 "lg_operadores": {"omitido": "falta la primera lectura a mano"}}
    usuario = db.query(m.Usuario).filter_by(correo="admin@centauro.lat").one()
    odoo_lg.sincronizar_flota(db, OdooFalso(FLOTA[:2]), ensayo=False, quien=usuario)
    r = odoo_lg.sincronizar_si_toca(db, OdooFalso(FLOTA[:3]))
    assert r["lg_flota"]["altas"] == 1
    assert r["lg_operadores"] == {"omitido": "falta la primera lectura a mano"}


# ====================================================== la oficina de Logistic

def test_la_oficina_de_logistic_entra_a_la_consola_y_sus_operadores_no():
    karla = _empleado(4, "Karla Rios", puesto="Gerente de Logística")
    karla["work_email"] = "karla.rios@centauro.lat"
    assert oficina.es_operador_lg(_empleado(1, "Ana Ruiz")) is True
    assert oficina.es_operador_lg(karla) is False
    assert oficina.es_de_oficina(karla) is True
    assert oficina.es_de_oficina(_empleado(1, "Ana Ruiz")) is False
    assert oficina.grupo_de_oficina(3)["pais"] == "MX"
    # Las otras companias, como antes.
    assert oficina.grupo_de_oficina(99) is None


def test_la_jefatura_de_odoo_sugiere_la_gerencia():
    """En Odoo el puesto de la gerencia se llama «Jefatura Logística» (la
    lectura del 3 de octubre): al darle acceso, Accesos sugiere «Gerente
    de Logística». Quien lleva la flota se escoge a mano."""
    from app import puestos_base
    puestos = [{"tipo": "puesto", "categoria_id": i, "nombre": p["nombre"],
                "rol": p["rol"].value, "patrones": oficina.patrones(p.get("puestos_odoo"))}
               for i, p in enumerate(puestos_base.PUESTOS) if p.get("puestos_odoo")]
    assert oficina.sugerir("Jefatura Logística", puestos)["nombre"] == "Gerente de Logística"
    assert oficina.sugerir("Planeador Logística \"B\"", puestos) is None

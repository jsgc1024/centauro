# -*- coding: utf-8 -*-
"""El personal de Brasil desde Odoo (seccion 121).

Con Odoo ya listo, cada pais lee a su gente por su compania, como la
flota, y nunca se mezclan:

  * Mexico, CENTAURO ASS con «Personal de Seguridad» o «Security Driver»;
    Brasil, CENTAURO SOLUCOES AVANCADAS DE SEGURANCA LTDA con «Motorista
    Executivo Bilingue» o «Condutor Folguista». Los administrativos de
    Brasil son de oficina; la gente de otra compania --Centauro Logistic--
    no es de Connect.
  * La plaza, entre las de su pais: «Sao Paulo - Barueri» es Sao Paulo.
  * A Brasil le pueden faltar el CPF, la CNH y la cuenta: entra igual y se
    dice como por capturar, sin borrar lo que Connect ya tiene.

Contra un Odoo de mentiras, en memoria: ninguna prueba sale a la red.
"""
import pytest
from sqlalchemy import text

from app import models as m
from app import odoo_oficina, odoo_personal
from test_odoo_personal import (DOMINIO, ODOO0, OdooFalso, empleado, leer,
                                persona)

MEXICO = [1, "CENTAURO ASS"]
BRASIL = [5, "CENTAURO SOLUCOES AVANCADAS DE SEGURANCA LTDA"]
LOGISTIC = [9, "Centauro Logistic SA CV"]


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture(autouse=True)
def sin_rastro(base_de_pruebas):
    """La persona y su acceso son catalogo: lo que estas pruebas dan de
    alta se va al terminar."""
    yield
    from conftest import TABLAS_DE_OPERACION
    from app.seed import sembrar_recursos

    with base_de_pruebas.begin() as con:
        con.execute(text(f"TRUNCATE {', '.join(TABLAS_DE_OPERACION)} "
                         "RESTART IDENTITY CASCADE"))
        ids = [f[0] for f in con.execute(text(
            "SELECT id FROM persona WHERE odoo_id >= :o OR correo LIKE :d"),
            {"o": ODOO0, "d": f"%@{DOMINIO}"})]
        if ids:
            con.execute(text(
                "DELETE FROM invitacion WHERE usuario_id IN "
                "(SELECT id FROM usuario WHERE persona_id = ANY(:ids))"),
                {"ids": ids})
            con.execute(text("DELETE FROM usuario WHERE persona_id = ANY(:ids)"),
                        {"ids": ids})
            con.execute(text("DELETE FROM persona WHERE id = ANY(:ids)"),
                        {"ids": ids})
    sembrar_recursos()


class OdooConCampos(OdooFalso):
    """Como el de verdad: cada campo con su nombre visible, el CPF en
    «Numero de identificacion» y la CNH en «Licencia para conducir». Con
    `cuentas`, el usuario puede leer las cuentas bancarias."""

    def __init__(self, *empleados, cuentas=None):
        super().__init__(*empleados)
        self.cuentas = cuentas

    def campos(self, modelo, atributos=None):
        assert modelo == "hr.employee"
        campos = {c: {"type": "char", "string": c} for c in odoo_personal.CAMPOS}
        campos["identification_id"] = {"type": "char",
                                       "string": "Número de identificación"}
        campos["driving_license_name"] = {
            "type": "char", "string": "Nombre de la licencia para conducir"}
        if self.cuentas is not None:
            campos[odoo_personal.CAMPO_CUENTA] = {"type": "many2one",
                                                  "string": "Cuenta bancaria"}
        return campos

    def leer(self, modelo, dominio, campos, archivados=False):
        if modelo == odoo_personal.MODELO_CUENTA:
            ids = dominio[0][2]
            return [{"id": i, **self.cuentas[i]} for i in ids if i in self.cuentas]
        return super().leer(modelo, dominio, campos, archivados)


def motorista(n, puesto="Motorista Executivo Bilíngue", **cambios):
    """Como llega hoy la gente de Brasil: su compania, su puesto, su lugar
    de trabajo con el municipio, sin correo de trabajo."""
    return empleado(n, **{"job_id": [40, puesto], "job_title": puesto,
                          "work_location_id": [9, "São Paulo - Barueri"],
                          "company_id": BRASIL, "work_email": False,
                          "mobile_phone": f"11 9{n:04d} 0000", **cambios})


def _sao_paulo(db):
    return (db.query(m.Plaza).join(m.Pais, m.Plaza.pais_id == m.Pais.id)
            .filter(m.Pais.codigo == "BR", m.Plaza.nombre == "Sao Paulo").one())


# ================================================================ el personal

def test_cada_pais_lee_a_su_gente_por_su_compania(db, datos):
    odoo = OdooConCampos(
        empleado(1),
        motorista(2),
        motorista(3, puesto="Condutor Folguista"),
        # Administrativo de Brasil: es de oficina, no de esta lectura.
        empleado(4, job_id=[42, "Analista Financeiro Pleno"],
                 job_title="Analista Financeiro Pleno", company_id=BRASIL),
        # El puesto de un pais con la compania del otro no entra.
        empleado(5, company_id=BRASIL),
        motorista(6, company_id=MEXICO),
        # Otra compania que la conexion alcanza a ver.
        empleado(7, job_id=[50, "Operador"], job_title="Operador",
                 company_id=LOGISTIC))
    informe = leer(db, odoo)
    assert sorted(a["odoo_id"] - ODOO0 for a in informe["altas"]) == [1, 2, 3]
    assert [(p["codigo"], p["leidos"]) for p in informe["por_pais"]] == [
        ("MX", 1), ("BR", 2)]
    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}
    assert faltas == {
        5: ["el puesto es de «México» y su compania en Odoo es "
            "«CENTAURO SOLUCOES AVANCADAS DE SEGURANCA LTDA»"],
        6: ["el puesto es de «Brasil» y su compania en Odoo es «CENTAURO ASS»"],
    }
    sp = _sao_paulo(db)
    for n in (2, 3):
        p = persona(db, n)
        assert p.plaza_id == sp.id and not p.oficina
        assert p.telefono.startswith("+55")
        u = db.query(m.Usuario).filter_by(persona_id=p.id).one()
        assert u.rol == m.Rol.PERSONAL_SEGURIDAD
        assert u.correo == f"agente{n}@{DOMINIO}"
    assert persona(db, 1).plaza_id == datos["cdmx"]["id"]
    r = odoo_personal.resumen(informe)
    assert r["por_pais"] == {"MX": 1, "BR": 2}
    assert r["pendientes"] == {"puesto de un pais y compania de otro": 2}


def test_a_brasil_le_falta_lo_que_rh_captura_despues_y_entra_igual(db):
    odoo = OdooConCampos(
        motorista(1),
        motorista(2, identification_id="123.456.789-09"),
        motorista(3, identification_id="987.654.321-00",
                  driving_license_name="cnh_3.pdf"),
        empleado(4))
    informe = leer(db, odoo, ensayo=True)
    assert len(informe["altas"]) == 4 and not informe["pendientes"]
    faltan = {x["odoo_id"] - ODOO0: x["falta"] for x in informe["por_capturar"]}
    # Sin permiso de leer cuentas no se dice la cuenta; Mexico no lleva
    # nada por capturar.
    assert faltan == {1: ["sin CPF", "sin CNH"], 2: ["sin CNH"]}
    assert {x["pais"] for x in informe["por_capturar"]} == {"Brasil"}
    assert informe["campos_por_capturar"] == {
        "cpf": "Número de identificación", "cnh": "Licencia para conducir"}
    assert odoo_personal.resumen(informe)["por_capturar"] == {
        "sin CPF": 1, "sin CNH": 2}


def test_un_campo_que_diga_cpf_o_cnh_manda_sobre_los_de_odoo(db):
    class ConStudio(OdooConCampos):
        def campos(self, modelo, atributos=None):
            campos = super().campos(modelo, atributos)
            campos["x_studio_cpf"] = {"type": "char", "string": "CPF"}
            campos["x_studio_numero_da_cnh"] = {"type": "char",
                                                "string": "Número da CNH"}
            return campos
    informe = leer(db, ConStudio(
        motorista(1, identification_id="123", x_studio_cpf="123.456.789-09",
                  x_studio_numero_da_cnh="04567812345")), ensayo=True)
    assert informe["campos_por_capturar"] == {"cpf": "CPF", "cnh": "Número da CNH"}
    assert informe["por_capturar"] == []


def test_la_cuenta_que_falta_en_odoo_no_borra_la_de_brasil(db):
    cuentas = {501: {"acc_number": "0001 12345-6", "acc_holder_name": False,
                     "bank_id": [7, "Itaú"], "partner_id": [9, "Motorista 1"]},
               502: {"acc_number": "014180655000000001", "acc_holder_name": False,
                     "bank_id": [8, "Santander"], "partner_id": [10, "Agente 2"]}}
    odoo = OdooConCampos(
        motorista(1, primary_bank_account_id=[501, "Itaú"],
                  identification_id="1", driving_license_name="c.pdf"),
        empleado(2, primary_bank_account_id=[502, "Santander"]),
        motorista(3, identification_id="3", driving_license_name="c.pdf"),
        cuentas=cuentas)
    informe = leer(db, odoo)
    assert persona(db, 1).clabe == "0001 12345-6"
    assert persona(db, 2).clabe == "014180655000000001"
    # Quien llega sin cuenta a Odoo: por capturar, y entra.
    assert [(x["odoo_id"] - ODOO0, x["falta"]) for x in informe["por_capturar"]] == [
        (3, ["sin cuenta bancaria"])]

    # RH quita las cuentas en Odoo: en Mexico Odoo manda tambien para
    # vaciar (seccion 105); en Brasil lo que falta en Odoo no borra lo que
    # Connect ya tiene, y como ya la tiene, no se pide.
    odoo.cambiar(1, primary_bank_account_id=False)
    odoo.cambiar(2, primary_bank_account_id=False)
    informe = leer(db, odoo)
    assert persona(db, 1).clabe == "0001 12345-6"
    assert persona(db, 2).clabe is None
    assert [x["odoo_id"] - ODOO0 for x in informe["por_capturar"]] == [3]


def test_una_persona_no_cambia_de_pais_sola(db, datos):
    # Un registro mas que se queda en su compania: si el pais leyera cero
    # con gente activa, la vuelta se detendria (seccion 130, decision 3).
    odoo = OdooConCampos(empleado(1), empleado(9))
    leer(db, odoo)
    odoo.cambiar(1, company_id=BRASIL, job_id=[40, "Motorista Executivo Bilíngue"],
                 job_title="Motorista Executivo Bilíngue",
                 work_location_id=[9, "São Paulo - Barueri"])
    informe = leer(db, odoo)
    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}
    assert faltas == {1: ["en Odoo es de «Brasil» y en Centauro es de otro pais"]}
    assert persona(db, 1).plaza_id == datos["cdmx"]["id"]


def test_la_ciudad_se_busca_entre_las_de_su_pais(db):
    informe = leer(db, OdooConCampos(
        motorista(1, work_location_id=[2, "Guadalajara"]),
        motorista(2, work_location_id=[3, "Curitiba"])), ensayo=True)
    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}
    assert faltas == {
        1: ["la plaza «Guadalajara» no es una ciudad de «Brasil» en Centauro"],
        2: ["la plaza «Curitiba» no existe en Centauro"],
    }


# ================================================================ la oficina

def test_la_oficina_solo_lee_las_companias_de_connect(db):
    odoo = OdooConCampos(
        empleado(1, job_id=[70, "Monitorista Bilingüe"],
                 job_title="Monitorista Bilingüe"),
        empleado(2, job_id=[42, "Analista Financeiro Pleno"],
                 job_title="Analista Financeiro Pleno", company_id=BRASIL,
                 work_location_id=[9, "São Paulo - Barueri"]),
        empleado(3, job_id=[43, "Gerente Administrativo Financeiro"],
                 job_title="Gerente Administrativo Financeiro",
                 company_id=BRASIL, work_location_id=False),
        # El motorista con correo de trabajo sigue siendo de seguridad.
        motorista(4, work_email=f"motorista4@{DOMINIO}"),
        empleado(5, job_id=[50, "Operador"], job_title="Operador",
                 company_id=LOGISTIC),
        empleado(6, job_id=[51, "Analista RH LOG"], job_title="Analista RH LOG",
                 company_id=LOGISTIC, work_email=False))
    db.expire_all()
    informe = odoo_oficina.sincronizar(db, odoo, ensayo=True)
    altas = {a["odoo_id"] - ODOO0: a["plaza"] for a in informe["altas"]}
    sp = _sao_paulo(db)
    # El de Brasil sin lugar de trabajo queda en la oficina de su pais.
    assert altas == {1: "Ciudad de Mexico", 2: sp.nombre, 3: sp.nombre}
    assert informe["leidos"] == 3
    assert not informe["sin_correo"]


def test_la_gente_de_otra_compania_que_ya_estaba_sale(db, cliente, sesion):
    """Lo que paso en el servidor: la lectura de la oficina se trajo a 14
    personas de Centauro Logistic, sin acceso. Sin acceso se van solas;
    con acceso no se toca sola."""
    odoo = OdooConCampos(
        empleado(1, job_id=[52, "Jefatura Logística"],
                 job_title="Jefatura Logística"),
        empleado(2, job_id=[53, "Coordinadora de Administración"],
                 job_title="Coordinadora de Administración"),
        # Alguien que se queda en Centauro Mexico: sin nadie, la compania
        # leeria cero y la vuelta se detendria (seccion 130).
        empleado(9, job_id=[54, "Analista Contable"],
                 job_title="Analista Contable"))
    db.expire_all()
    odoo_oficina.sincronizar(db, odoo, ensayo=False)
    con_acceso = persona(db, 2)
    r = cliente.post("/auth/usuarios", json={"persona_id": con_acceso.id,
                                             "rol": "finanzas"},
                     headers=sesion("admin"))
    assert r.status_code == 201, r.text

    odoo.cambiar(1, company_id=LOGISTIC)
    odoo.cambiar(2, company_id=LOGISTIC)
    db.expire_all()
    informe = odoo_oficina.sincronizar(db, odoo, ensayo=False)
    assert [(b["odoo_id"] - ODOO0, b["motivo"], b["acceso"])
            for b in informe["bajas"]] == [(1, "es de otra compania en Odoo",
                                            "no tenia")]
    assert [(p["odoo_id"] - ODOO0, p["falta"]) for p in informe["pendientes"]] == [
        (2, ["en Odoo es de «Centauro Logistic SA CV»: no es de Connect"])]
    assert persona(db, 1).activo is False
    p2 = persona(db, 2)
    assert p2.activo is True
    assert db.query(m.Usuario).filter_by(persona_id=p2.id).one().activo is True

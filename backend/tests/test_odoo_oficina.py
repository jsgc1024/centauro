# -*- coding: utf-8 -*-
"""El personal de oficina, leido de Odoo (seccion 74).

Segundo paso de la propuesta Puestos y Odoo (Salvador, 26 sep). Contra un
Odoo de mentiras, en memoria: ninguna prueba sale a la red.

Lo que se cuida:

  * llega la persona, no su acceso: el acceso lo da Recursos Humanos, con
    el puesto que sugiere su puesto de Odoo;
  * quien no tiene correo de trabajo no llega: se lista para que RH se lo
    ponga en Odoo;
  * si Odoo lo archiva, su acceso se cierra;
  * la oficina no se revuelve con el personal de seguridad: ni en su
    lectura, ni en las listas de a quien se manda a la calle.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app import disponibilidad, odoo_api, odoo_oficina, odoo_personal
from app import models as m
from app import odoo_oficina_reglas as reglas

ODOO0 = 8_000_000
DOMINIO = "oficina-odoo.lat"


class OdooFalso:
    def __init__(self, *empleados):
        self.empleados = {e["id"]: e for e in empleados}

    def leer(self, modelo, dominio, campos, archivados=False):
        assert modelo == "hr.employee"
        filas = [e for e in self.empleados.values()
                 if archivados or e.get("active", True)]
        for campo, operador, valor in dominio:
            assert (campo, operador) == ("id", "in")
            filas = [e for e in filas if e["id"] in valor]
        return [{"id": e["id"], **{c: e.get(c, False) for c in campos}}
                for e in filas]

    def cambiar(self, n, **valores):
        self.empleados[ODOO0 + n].update(valores)

    def archivar(self, n):
        self.cambiar(n, active=False)


def empleado(n, puesto="Monitorista Bilingüe", **cambios):
    e = {"id": ODOO0 + n, "name": f"Oficina Odoo {n}",
         "job_id": [70, puesto], "job_title": puesto,
         "department_id": [5, "Central de Inteligencia"],
         "work_location_id": [30, "Ciudad de México"],
         "work_email": f"oficina{n}@{DOMINIO}",
         "write_date": "2026-09-01 10:00:00", "active": True}
    e.update(cambios)
    return e


def de_seguridad(n, **cambios):
    return empleado(n, puesto="Personal de Seguridad",
                    private_email=f"agente{n}@{DOMINIO}",
                    department_id=[6, "Consultoría en seguridad"], **cambios)


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture(autouse=True)
def sin_rastro(base_de_pruebas):
    """Lo que estas pruebas dan de alta se va al terminar, y a quien de las
    cuentas sembradas se reconocio por su correo se le deja como estaba."""
    yield
    from conftest import TABLAS_DE_OPERACION
    from app.seed import sembrar_recursos

    with base_de_pruebas.begin() as con:
        con.execute(text(f"TRUNCATE {', '.join(TABLAS_DE_OPERACION)} "
                         "RESTART IDENTITY CASCADE"))
        con.execute(text(
            "UPDATE persona SET odoo_id = NULL, oficina = false, "
            "puesto_odoo = NULL, area_odoo = NULL, odoo_sincronizado_en = NULL, "
            "baja_odoo_en = NULL, activo = true "
            "WHERE odoo_id >= :o AND correo NOT LIKE :d"),
            {"o": ODOO0, "d": f"%@{DOMINIO}"})
        ids = [f[0] for f in con.execute(text(
            "SELECT id FROM persona WHERE odoo_id >= :o OR correo LIKE :d"),
            {"o": ODOO0, "d": f"%@{DOMINIO}"})]
        if ids:
            con.execute(text(
                "DELETE FROM invitacion WHERE usuario_id IN "
                "(SELECT id FROM usuario WHERE persona_id = ANY(:ids))"),
                {"ids": ids})
            con.execute(text("DELETE FROM registro_admin WHERE objeto = 'usuario' "
                             "AND objeto_id IN (SELECT id FROM usuario "
                             "WHERE persona_id = ANY(:ids))"), {"ids": ids})
            con.execute(text("DELETE FROM usuario WHERE persona_id = ANY(:ids)"),
                        {"ids": ids})
            con.execute(text("DELETE FROM persona WHERE id = ANY(:ids)"),
                        {"ids": ids})
    sembrar_recursos()


def leer(db, odoo, ensayo=False, **kwargs):
    db.expire_all()
    return odoo_oficina.sincronizar(db, odoo, ensayo=ensayo, **kwargs)


def persona(db, n):
    db.expire_all()
    return db.query(m.Persona).filter_by(odoo_id=ODOO0 + n).one()


def usuario_de(db, persona_id):
    db.expire_all()
    return db.query(m.Usuario).filter_by(persona_id=persona_id).first()


# ================================================================ la lectura

def test_el_ensayo_no_guarda_nada(db):
    odoo = OdooFalso(empleado(1), empleado(2, "Facturista"), de_seguridad(3))
    informe = leer(db, odoo, ensayo=True)
    assert informe["ensayo"] is True
    assert informe["leidos"] == 2           # el de seguridad no es de aqui
    assert {a["odoo_id"] for a in informe["altas"]} == {ODOO0 + 1, ODOO0 + 2}
    assert db.query(m.Persona).filter(m.Persona.odoo_id >= ODOO0).count() == 0


def test_llega_la_persona_y_no_su_acceso(db):
    leer(db, OdooFalso(empleado(1), de_seguridad(3)))
    p = persona(db, 1)
    assert p.oficina is True
    assert p.correo == f"oficina1@{DOMINIO}"
    assert p.puesto_odoo == "Monitorista Bilingüe"
    assert p.area_odoo == "Central de Inteligencia"
    # El acceso lo da Recursos Humanos, no la lectura.
    assert usuario_de(db, p.id) is None
    # Y el de seguridad no lo trajo esta lectura.
    assert db.query(m.Persona).filter_by(odoo_id=ODOO0 + 3).count() == 0


def test_sin_correo_de_trabajo_no_llega_y_se_lista(db, cliente, sesion):
    leer(db, OdooFalso(empleado(1), empleado(2, work_email=False)),
         quien=None)
    assert db.query(m.Persona).filter_by(odoo_id=ODOO0 + 2).count() == 0
    r = cliente.get("/auth/oficina", headers=sesion("rrhh"))
    assert r.status_code == 200, r.text
    sin = r.json()["sin_correo"]
    assert [x["odoo_id"] for x in sin] == [ODOO0 + 2]
    assert sin[0]["puesto"] == "Monitorista Bilingüe"


def test_sin_lugar_queda_en_la_oficina_central(db):
    informe = leer(db, OdooFalso(empleado(1, work_location_id=False)))
    assert persona(db, 1).plaza.nombre == "Ciudad de Mexico"
    assert [x["odoo_id"] for x in informe["sin_lugar"]] == [ODOO0 + 1]


def test_a_quien_ya_estaba_se_le_reconoce_por_su_correo(db):
    """La cuenta de RH ya existia, capturada a mano: la lectura la liga a
    su ficha de Odoo sin tocarle el acceso."""
    rrhh = db.query(m.Persona).filter_by(correo="rrhh@centauro.lat").one()
    antes = usuario_de(db, rrhh.id)
    informe = leer(db, OdooFalso(empleado(
        5, "Coordinadora de RH", work_email="rrhh@centauro.lat",
        department_id=[8, "Recursos Humanos"])))
    assert [v["persona_id"] for v in informe["vinculadas"]] == [rrhh.id]
    db.expire_all()
    rrhh = db.get(m.Persona, rrhh.id)
    assert rrhh.odoo_id == ODOO0 + 5 and rrhh.oficina is True
    assert rrhh.puesto_odoo == "Coordinadora de RH"
    assert usuario_de(db, rrhh.id).rol == antes.rol


def test_lo_que_cambia_en_odoo_se_pone_al_dia(db):
    odoo = OdooFalso(empleado(1))
    leer(db, odoo)
    odoo.cambiar(1, job_title="Supervisor Analisis inteligencia",
                 department_id=[9, "Inteligencia"])
    informe = leer(db, odoo)
    cambio = informe["cambios"][0]
    assert set(cambio["que"]) == {"puesto", "área"}
    assert persona(db, 1).puesto_odoo == "Supervisor Analisis inteligencia"


def test_la_baja_en_odoo_le_cierra_el_acceso(db, cliente, sesion):
    odoo = OdooFalso(empleado(1))
    leer(db, odoo)
    p = persona(db, 1)
    r = cliente.post("/auth/usuarios", json={"persona_id": p.id,
                                             "rol": "central"},
                     headers=sesion("admin"))
    assert r.status_code == 201, r.text
    odoo.archivar(1)
    informe = leer(db, odoo)
    assert informe["bajas"][0]["acceso"] == "se cierra"
    p = persona(db, 1)
    assert p.activo is False
    assert usuario_de(db, p.id).activo is False


def test_quien_era_de_seguridad_no_se_toma(db):
    """Un cambio de puesto en Odoo no se adivina: queda pendiente."""
    odoo = OdooFalso(de_seguridad(3))
    odoo_personal.sincronizar(db, odoo, ensayo=False)
    odoo.cambiar(3, job_title="Monitorista", job_id=[70, "Monitorista"])
    informe = leer(db, odoo)
    assert informe["pendientes"][0]["falta"] == [
        "en Centauro es personal de seguridad; en Odoo ya no"]
    assert persona(db, 3).oficina is False


# ============================================ no se revuelve con la calle

def test_la_lectura_de_seguridad_no_toca_a_la_oficina(db):
    """Sin esto, cada hora la lectura del personal de seguridad diria de
    toda la oficina que «ya no tiene puesto de seguridad en Odoo»."""
    odoo = OdooFalso(empleado(1), de_seguridad(3))
    leer(db, odoo)
    informe = odoo_personal.sincronizar(db, odoo, ensayo=True)
    assert not [p for p in informe["pendientes"]
                if p["odoo_id"] == ODOO0 + 1]
    assert not informe["bajas"]


def test_la_oficina_no_se_manda_a_la_calle(db):
    leer(db, OdooFalso(empleado(1)))
    p = persona(db, 1)
    inicio = datetime.now() + timedelta(days=3)
    lista = disponibilidad.recomendar_personal(
        db, p.plaza_id, None, inicio, inicio + timedelta(hours=8), True)
    todos = [x["persona_id"] for grupo in ("disponibles", "con_alerta",
                                           "no_disponibles",
                                           "de_otras_ciudades")
             for x in lista[grupo]]
    assert p.id not in todos
    assert todos, "el resto del personal si sale"


# ============================================ el puesto sugerido

@pytest.mark.parametrize("puesto, sugerido", [
    ("Monitorista No Bilingüe", "Monitorista"),
    ("Monitorista Bilingüe", "Monitorista"),
    ("Asistente CI", "Monitorista"),
    ('CONSULTOR JR "B" PE', "Consultor JR"),
    ("Consultor de Seguridad", "Consultor de seguridad"),
    ("Coordinadora de RH", "Recursos Humanos"),
    ("Generalista de RH", "Recursos Humanos"),
    ("Facturista", "Facturación y cobranza"),
    ("Coordinador de Facturación y Cobranza", "Facturación y cobranza"),
    ("Analista de Finanzas", "Tesorería y gastos"),
    ("Auxiliar de gastos", "Tesorería y gastos"),
    ("Jefe de Finanzas", "Jefe de finanzas"),
    ("Coordinadora de nómina", "Nómina"),
    ("Supervisor Analisis inteligencia", "Supervisor de central"),
    ("Especialista Monitoreo de Seguridad", "Supervisor de central"),
    ("Director de Operaciones", "Dirección de operaciones"),
    ("Director General", "Dirección general"),
    ("Jefa de Desarrollo web", "Administración del sistema"),
    ('Asistente "A"', None),
])
def test_el_puesto_que_se_sugiere(puesto, sugerido):
    """Con los puestos de Odoo de la propuesta. Gana el parecido mas
    largo: a «Consultor JR B» le queda «Consultor JR», no «Consultor»."""
    from app import puestos_base

    puestos = [{"nombre": p["nombre"],
                "patrones": reglas.patrones(p["puestos_odoo"])}
               for p in puestos_base.PUESTOS + puestos_base.POR_ROL]
    hallado = reglas.sugerir(puesto, puestos)
    assert (hallado["nombre"] if hallado else None) == sugerido


def test_una_palabra_no_se_encuentra_dentro_de_otra():
    puestos = [{"nombre": "Consultor", "patrones": ["consultor"]}]
    assert reglas.sugerir("Consultoria externa", puestos) is None
    assert reglas.sugerir("Consultor externo", puestos)["nombre"] == "Consultor"


def test_recursos_humanos_ve_la_oficina_con_su_puesto_sugerido(db, cliente,
                                                               sesion):
    h = sesion("admin")
    cliente.post("/auth/categorias/base", headers=h)
    leer(db, OdooFalso(empleado(1), empleado(2, 'Asistente "A"'),
                       empleado(4, "Director General")))
    r = cliente.get("/auth/oficina", headers=sesion("rrhh"))
    assert r.status_code == 200, r.text
    por_odoo = {x["correo"]: x for x in r.json()["sin_acceso"]}
    mon = por_odoo[f"oficina1@{DOMINIO}"]["sugerido"]
    assert mon["nombre"] == "Monitorista" and mon["tipo"] == "puesto"
    assert mon["rol"] == "central" and mon["categoria_id"]
    assert por_odoo[f"oficina2@{DOMINIO}"]["sugerido"] is None
    dg = por_odoo[f"oficina4@{DOMINIO}"]["sugerido"]
    assert dg["tipo"] == "rol" and dg["rol"] == "director_general"

    # Dar el acceso con lo sugerido: entra con el rol del puesto y deja
    # la lista.
    p = persona(db, 1)
    r = cliente.post("/auth/usuarios",
                     json={"persona_id": p.id, "rol": "consultor",
                           "categoria_id": mon["categoria_id"]},
                     headers=sesion("rrhh"))
    assert r.status_code == 201, r.text
    u = usuario_de(db, p.id)
    assert u.rol == m.Rol.CENTRAL and u.categoria.nombre == "Monitorista"
    siguen = cliente.get("/auth/oficina", headers=sesion("rrhh")).json()
    assert f"oficina1@{DOMINIO}" not in {x["correo"] for x in siguen["sin_acceso"]}


def test_el_ensayo_dice_a_quien_no_se_le_podra_sugerir(db, cliente, sesion):
    cliente.post("/auth/categorias/base", headers=sesion("admin"))
    informe = leer(db, OdooFalso(empleado(1), empleado(2, 'Asistente "A"')),
                   ensayo=True)
    assert [x["odoo_id"] for x in informe["sin_sugerencia"]] == [ODOO0 + 2]


# ============================================ cada hora, y las puertas

def test_la_de_cada_hora_espera_a_la_primera_a_mano(db):
    odoo = OdooFalso(empleado(1))
    assert "omitido" in odoo_oficina.sincronizar_si_toca(db, odoo)
    leer(db, odoo, quien=None)
    db.expire_all()
    fila = db.query(m.SincronizacionOdoo).filter_by(tipo="oficina").one()
    assert fila.automatica is False
    odoo.cambiar(1, name="Oficina Odoo Uno")
    resultado = odoo_oficina.sincronizar_si_toca(db, odoo)
    assert resultado["cambios"] == 1


def test_las_puertas(cliente, sesion, monkeypatch):
    from app.config import settings

    odoo = OdooFalso(empleado(1))
    monkeypatch.setattr(odoo_api, "cliente", lambda: odoo)
    monkeypatch.setattr(settings, "odoo_base", "https://odoo.prueba")
    monkeypatch.setattr(settings, "odoo_api_key", "llave")
    assert cliente.get("/odoo/oficina/ensayo",
                       headers=sesion("admin")).status_code == 200
    assert cliente.get("/odoo/oficina/ensayo",
                       headers=sesion("rrhh")).status_code == 403
    assert cliente.post("/odoo/oficina/sincronizar",
                        headers=sesion("consultor")).status_code == 403
    assert cliente.get("/auth/oficina",
                       headers=sesion("consultor")).status_code == 403
    estado = cliente.get("/odoo/estado", headers=sesion("admin")).json()
    assert "oficina" in estado and estado["oficina"]["primera_hecha"] is False

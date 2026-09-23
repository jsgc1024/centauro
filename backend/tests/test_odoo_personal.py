# -*- coding: utf-8 -*-
"""El personal de seguridad, leido de Odoo (seccion 51 de la bitacora).

Contra un Odoo de mentiras, en memoria: ninguna prueba sale a la red.
Imita lo que importa del de verdad: sin `archivados` no devuelve a los
archivados, y a quien no tiene foto le da el circulo de iniciales, que
es un SVG y no una foto.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from ayudas import asignar, crear_servicio, jornada, manana
from app import models as m
from app import odoo_api, odoo_personal

ODOO0 = 7_000_000
DOMINIO = "prueba-odoo.lat"
PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9Q"
       "DwADhgGAWjR9awAAAABJRU5ErkJggg==")
SVG = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciLz4="


class OdooFalso:
    def __init__(self, *empleados, fotos=None):
        self.empleados = {e["id"]: e for e in empleados}
        self.fotos = dict(fotos or {})
        self.lecturas = []

    def leer(self, modelo, dominio, campos, archivados=False):
        assert modelo == "hr.employee"
        self.lecturas.append(list(campos))
        filas = [e for e in self.empleados.values()
                 if archivados or e.get("active", True)]
        for campo, operador, valor in dominio:
            assert (campo, operador) == ("id", "in")
            filas = [e for e in filas if e["id"] in valor]
        salida = []
        for e in filas:
            fila = {"id": e["id"]}
            for c in campos:
                fila[c] = (self.fotos.get(e["id"], SVG) if c == "image_128"
                           else e.get(c, False))
            salida.append(fila)
        return salida

    def cambiar(self, n, **valores):
        self.empleados[ODOO0 + n].update(valores)

    def archivar(self, n):
        self.cambiar(n, active=False)


class OdooCaido:
    def leer(self, *args, **kwargs):
        raise odoo_api.NoResponde("Odoo rechazo la llave; puede que haya vencido.")


def empleado(n, **cambios):
    e = {"id": ODOO0 + n, "name": f"Agente Odoo {n}",
         "job_id": [90, "Personal de Seguridad"],
         "job_title": "Personal de Seguridad",
         "work_location_id": [30, "Ciudad de México"],
         "work_email": f"agente{n}@{DOMINIO}", "private_email": False,
         "mobile_phone": f"55 5000 {n:04d}", "registration_number": f"PO-{n}",
         "first_contract_date": "2024-03-01",
         "write_date": "2026-01-01 10:00:00", "active": True}
    e.update(cambios)
    return e


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture(autouse=True)
def sin_rastro(base_de_pruebas):
    """Lo que estas pruebas dan de alta se va al terminar.

    La persona y su acceso son catalogo: no se vacian entre pruebas. Sin
    esto, la persona de una prueba seguiria «leida de Odoo» en la
    siguiente, y la siguiente la daria de baja por no venir en su Odoo.
    """
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


def leer(db, odoo, ensayo=False, **kwargs):
    # Como en produccion, donde cada lectura abre su propia sesion: se lee
    # la base como esta, no lo que esta sesion trae en memoria de antes.
    # Sin esto, la baja que la consola hizo por su lado no se veia.
    db.expire_all()
    return odoo_personal.sincronizar(db, odoo, ensayo=ensayo, **kwargs)


def persona(db, n):
    db.expire_all()
    return db.query(m.Persona).filter_by(odoo_id=ODOO0 + n).one()


def de_prueba(db):
    db.expire_all()
    return db.query(m.Persona).filter(m.Persona.odoo_id >= ODOO0).count()


def alerta_de_baja(db, jornada_id):
    return (db.query(m.Alerta)
            .filter_by(jornada_id=jornada_id,
                       tipo=m.TipoAlerta.PERSONAL_DE_BAJA).one())


def en_un_servicio(cliente, sesion, datos, persona_id):
    """Lo asigna a un dia de un servicio de Ana, dentro de tres dias."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(3), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"], persona_id=persona_id)[0]
    assert r.status_code == 200, r.text
    return j


# ================================================================ altas

def test_el_ensayo_dice_que_haria_y_no_guarda_nada(db):
    odoo = OdooFalso(empleado(1), empleado(2), fotos={ODOO0 + 1: PNG})
    informe = leer(db, odoo, ensayo=True)
    assert informe["ensayo"] is True
    assert [a["odoo_id"] - ODOO0 for a in informe["altas"]] == [1, 2]
    # Lee las fotos para que la cuenta sea la de verdad, pero no guarda.
    assert informe["fotos"] == {"revisadas": 2, "reales": 1,
                                "sin_foto_real": 1, "actualizadas": 0}
    assert de_prueba(db) == 0
    assert db.query(m.SincronizacionOdoo).count() == 0


def test_el_alta_trae_a_la_persona_y_su_acceso_sin_contrasena(db):
    informe = leer(db, OdooFalso(empleado(1), fotos={ODOO0 + 1: PNG}))
    assert len(informe["altas"]) == 1 and not informe["pendientes"]
    p = persona(db, 1)
    assert (p.nombre, p.correo) == ("Agente Odoo 1", f"agente1@{DOMINIO}")
    assert p.plaza.nombre == "Ciudad de Mexico"
    assert p.telefono == "+52 55 5000 0001"
    assert (p.referencia, p.fecha_ingreso) == ("PO-1", date(2024, 3, 1))
    assert p.foto_url == "data:image/png;base64," + PNG
    assert p.activo and p.odoo_sincronizado_en is not None
    usuario = db.query(m.Usuario).filter_by(persona_id=p.id).one()
    assert usuario.rol == m.Rol.PERSONAL_SEGURIDAD and usuario.activo
    assert usuario.correo == p.correo
    # Entra con el codigo que le dicta su consultor o la central.
    assert usuario.hash_contrasena is None
    fila = db.query(m.SincronizacionOdoo).one()
    assert (fila.altas, fila.automatica, fila.hecha_por_id) == (1, False, None)


def test_la_segunda_lectura_no_cambia_nada(db):
    odoo = OdooFalso(empleado(1), empleado(2))
    leer(db, odoo)
    informe = leer(db, odoo)
    assert not (informe["altas"] or informe["cambios"] or informe["bajas"])
    assert informe["sin_cambio"] == 2
    # Si Odoo no toco la ficha, la foto no se vuelve a pedir.
    assert informe["fotos"]["revisadas"] == 0
    assert odoo.lecturas.count(["image_128"]) == 1


def test_solo_entra_el_personal_de_seguridad(db):
    informe = leer(db, OdooFalso(
        empleado(1),
        empleado(2, job_id=False,
                 job_title="Security Driver (Protección Ejecutiva)"),
        empleado(3, job_id=False, job_title=" PERSONAL DE  SEGURIDAD GDL"),
        empleado(4, job_id=[91, "Monitorista Bilingüe"],
                 job_title="Monitorista Bilingüe"),
        empleado(5, job_id=False, job_title="Guardia de Seguridad"),
        empleado(6, job_id=False, job_title=False)))
    assert informe["leidos"] == 3
    assert sorted(a["odoo_id"] - ODOO0 for a in informe["altas"]) == [1, 2, 3]
    assert de_prueba(db) == 3


def test_lo_dudoso_queda_pendiente_y_no_se_toca(db):
    informe = leer(db, OdooFalso(
        empleado(1, work_location_id=False),
        empleado(2, work_location_id=[31, "Home"]),
        empleado(3, work_email="agente3@gamil.com"),
        empleado(4, work_email=f"repetido@{DOMINIO}"),
        empleado(5, work_email=f"repetido@{DOMINIO}"),
        empleado(6, work_email=False, private_email=False)))
    assert not informe["altas"]
    faltas = {p["odoo_id"] - ODOO0: p["falta"] for p in informe["pendientes"]}
    assert faltas == {
        1: ["sin plaza"],
        2: ["la plaza «Home» no existe en Centauro"],
        3: ["correo con error de dedo"],
        4: ["correo repetido en Odoo"],
        5: ["correo repetido en Odoo"],
        6: ["sin correo"],
    }
    assert de_prueba(db) == 0


def test_el_estado_de_mexico_va_como_ciudad_de_mexico(db):
    leer(db, OdooFalso(
        empleado(1, work_location_id=[32, "Estado de México"]),
        empleado(2, work_location_id=[33, "Guadalajara"])))
    assert persona(db, 1).plaza.nombre == "Ciudad de Mexico"
    assert persona(db, 2).plaza.nombre == "Guadalajara"


# ================================================================ cambios

def test_lo_que_cambia_en_odoo_cambia_aqui_y_lo_vacio_no_borra(db):
    odoo = OdooFalso(empleado(1))
    leer(db, odoo)
    odoo.cambiar(1, name="Agente Odoo Uno", work_email=f"uno@{DOMINIO}",
                 work_location_id=[33, "Guadalajara"],
                 mobile_phone="33 1111 2222")
    informe = leer(db, odoo)
    assert informe["cambios"][0]["que"] == ["nombre", "plaza", "celular",
                                            "correo"]
    p = persona(db, 1)
    assert (p.nombre, p.plaza.nombre, p.telefono, p.correo) == (
        "Agente Odoo Uno", "Guadalajara", "+52 33 1111 2222",
        f"uno@{DOMINIO}")
    # El acceso sigue a la persona: entra con su correo nuevo.
    assert (db.query(m.Usuario).filter_by(persona_id=p.id).one().correo
            == f"uno@{DOMINIO}")

    odoo.cambiar(1, mobile_phone=False, registration_number=False)
    assert not leer(db, odoo)["cambios"]
    p = persona(db, 1)
    assert (p.telefono, p.referencia) == ("+52 33 1111 2222", "PO-1")


def test_quien_ya_estaba_en_centauro_se_vincula_por_su_correo(
        cliente, sesion, datos, db):
    h = sesion("admin")
    r = cliente.post("/catalogos/personal", headers=h, json={
        "nombre": "Capturado A Mano", "correo": f"agente1@{DOMINIO}",
        "plaza_id": datos["cdmx"]["id"]})
    assert r.status_code == 201, r.text
    alta = cliente.post("/auth/usuarios", headers=h, json={
        "persona_id": r.json()["id"], "rol": "personal_seguridad"})
    assert alta.status_code == 201, alta.text

    informe = leer(db, OdooFalso(empleado(1)))
    assert not informe["altas"]
    assert [v["persona_id"] for v in informe["vinculadas"]] == [r.json()["id"]]
    p = persona(db, 1)
    # La misma persona, con lo que dice Odoo, y un solo acceso.
    assert (p.id, p.nombre) == (r.json()["id"], "Agente Odoo 1")
    assert db.query(m.Usuario).filter_by(persona_id=p.id).count() == 1


def test_el_circulo_de_iniciales_no_es_foto_y_la_foto_nueva_se_toma(db):
    odoo = OdooFalso(empleado(1))
    informe = leer(db, odoo)
    assert informe["fotos"]["sin_foto_real"] == 1
    assert persona(db, 1).foto_url is None

    # RH le sube una foto: Odoo mueve el write_date de la ficha.
    despues = datetime.now(timezone.utc) + timedelta(minutes=5)
    odoo.fotos[ODOO0 + 1] = PNG
    odoo.cambiar(1, write_date=despues.strftime("%Y-%m-%d %H:%M:%S"))
    assert leer(db, odoo)["fotos"]["actualizadas"] == 1
    assert persona(db, 1).foto_url == "data:image/png;base64," + PNG


# ================================================================ bajas

def test_la_baja_en_odoo_cierra_el_acceso_y_avisa_a_la_central(
        cliente, sesion, datos, db):
    odoo = OdooFalso(empleado(1), empleado(2))
    leer(db, odoo)
    p = persona(db, 1)
    j = en_un_servicio(cliente, sesion, datos, p.id)

    odoo.archivar(1)
    informe = leer(db, odoo)
    assert [(b["odoo_id"] - ODOO0, b["motivo"], b["dias_por_delante"],
             b["acceso"]) for b in informe["bajas"]] == [
        (1, "archivado en Odoo", 1, "se cierra")]
    p = persona(db, 1)
    assert not p.activo and p.baja_odoo_en is not None
    assert not db.query(m.Usuario).filter_by(persona_id=p.id).one().activo
    assert alerta_de_baja(db, j["id"]).persona_id == p.id
    assert persona(db, 2).activo


def test_quien_debe_viaticos_conserva_el_acceso_hasta_comprobarlos(
        cliente, sesion, datos, db):
    odoo = OdooFalso(empleado(1))
    leer(db, odoo)
    p = persona(db, 1)
    j = en_un_servicio(cliente, sesion, datos, p.id)
    viatico = (db.query(m.AsignacionViatico)
               .filter_by(jornada_id=j["id"], persona_id=p.id).first())
    if viatico is None:
        viatico = m.AsignacionViatico(
            jornada_id=j["id"], persona_id=p.id, moneda=m.Moneda.MXN,
            escenario=m.EscenarioViatico.FULL_DAY_LOCAL)
        db.add(viatico)
    viatico.monto_total = 1500
    viatico.estatus = m.EstatusViatico.TRANSFERIDO
    db.commit()

    odoo.archivar(1)
    baja = leer(db, odoo)["bajas"][0]
    assert baja["viaticos_sin_cerrar"] == 1
    assert baja["acceso"] == "sigue abierto hasta que compruebe sus viaticos"
    assert not persona(db, 1).activo
    assert db.query(m.Usuario).filter_by(persona_id=p.id).one().activo
    assert "viatico" in alerta_de_baja(db, j["id"]).mensaje

    # Comprueba, y en la siguiente lectura el acceso se cierra solo.
    viatico.estatus = m.EstatusViatico.CERRADO
    db.commit()
    assert [a["persona_id"] for a in leer(db, odoo)["accesos_cerrados"]] == [p.id]
    db.expire_all()
    assert not db.query(m.Usuario).filter_by(persona_id=p.id).one().activo
    assert not leer(db, odoo)["accesos_cerrados"]


def test_quien_desaparece_de_odoo_tambien_se_da_de_baja(db):
    odoo = OdooFalso(empleado(1))
    leer(db, odoo)
    del odoo.empleados[ODOO0 + 1]
    assert [b["motivo"] for b in leer(db, odoo)["bajas"]] == ["ya no esta en Odoo"]
    assert not persona(db, 1).activo


def test_quien_cambia_de_puesto_queda_pendiente_sin_baja(db):
    odoo = OdooFalso(empleado(1))
    leer(db, odoo)
    odoo.cambiar(1, job_id=[91, "Monitorista Bilingüe"],
                 job_title="Monitorista Bilingüe")
    informe = leer(db, odoo)
    assert not informe["bajas"]
    assert informe["pendientes"][0]["falta"] == [
        "ya no tiene puesto de seguridad en Odoo"]
    assert persona(db, 1).activo


def test_de_baja_en_centauro_y_activo_en_odoo_se_reactiva_a_mano(
        cliente, sesion, db):
    odoo = OdooFalso(empleado(1))
    leer(db, odoo)
    p = persona(db, 1)
    assert cliente.delete(f"/catalogos/personal/{p.id}",
                          headers=sesion("admin")).status_code == 204
    informe = leer(db, odoo)
    assert informe["pendientes"][0]["falta"] == [
        "activo en Odoo pero dado de baja en Centauro: reactivar a mano"]
    assert not persona(db, 1).activo


# ================================================================ la tarea

def test_la_tarea_de_cada_hora_espera_la_primera_a_mano(db):
    odoo = OdooFalso(empleado(1))
    assert odoo_personal.sincronizar_si_toca(db, odoo) == {
        "omitido": "falta la primera sincronizacion a mano"}
    assert not odoo.lecturas
    leer(db, odoo, ensayo=True)            # el ensayo no cuenta
    assert "omitido" in odoo_personal.sincronizar_si_toca(db, odoo)

    leer(db, odoo)                         # la primera, a mano
    odoo.empleados[ODOO0 + 2] = empleado(2)
    r = odoo_personal.sincronizar_si_toca(db, odoo)
    assert (r["leidos"], r["altas"]) == (2, 1)
    fila = db.query(m.SincronizacionOdoo).filter_by(automatica=True).one()
    assert fila.altas == 1 and fila.detalle

    # Una hora sin novedades deja su renglon, sin el detalle.
    odoo_personal.sincronizar_si_toca(db, odoo)
    ultima = (db.query(m.SincronizacionOdoo)
              .order_by(m.SincronizacionOdoo.id.desc()).first())
    assert ultima.automatica and ultima.detalle is None


def test_la_tarea_de_cada_hora_no_truena_si_odoo_no_contesta(db):
    leer(db, OdooFalso(empleado(1)))
    r = odoo_personal.sincronizar_si_toca(db, OdooCaido())
    assert "vencido" in r["error"]


# ================================================================ la consola

def test_lo_que_viene_de_odoo_no_se_edita_en_el_catalogo(
        cliente, sesion, db):
    leer(db, OdooFalso(empleado(1)))
    p = persona(db, 1)
    h = sesion("admin")
    cuerpo = {"nombre": p.nombre, "correo": p.correo, "plaza_id": p.plaza_id}
    r = cliente.patch(f"/catalogos/personal/{p.id}", headers=h,
                      json={**cuerpo, "nombre": "Otro Nombre"})
    assert r.status_code == 409, r.text
    assert "Odoo" in r.json()["detail"]["mensaje"]
    # Lo que es de Centauro si se edita, y la ficha trae lo de Odoo.
    r = cliente.patch(f"/catalogos/personal/{p.id}", headers=h,
                      json={**cuerpo, "es_freelance": False})
    assert r.status_code == 200, r.text
    assert (r.json()["referencia"], r.json()["fecha_ingreso"]) == (
        "PO-1", "2024-03-01")


def test_el_buscador_del_codigo_encuentra_por_numero_de_empleado(
        cliente, sesion, db):
    leer(db, OdooFalso(empleado(7)))
    p = persona(db, 7)
    h = sesion("central")
    filas = cliente.get("/auth/campo/buscar?q=po-7", headers=h).json()
    assert [f["persona_id"] for f in filas] == [p.id]
    assert filas[0]["referencia"] == "PO-7"
    # El numero va completo: un pedazo no trae a nadie por numero.
    filas = cliente.get("/auth/campo/buscar?q=po-", headers=h).json()
    assert p.id not in [f["persona_id"] for f in filas]


def test_las_rutas_son_de_administracion(cliente, sesion, monkeypatch, db):
    from app.config import settings

    monkeypatch.setattr(settings, "odoo_base", "")
    monkeypatch.setattr(settings, "odoo_api_key", "")
    assert cliente.get("/odoo/personal/ensayo",
                       headers=sesion("consultor")).status_code == 403
    r = cliente.get("/odoo/personal/ensayo", headers=sesion("admin"))
    assert r.status_code == 503, r.text
    assert "no esta conectado" in r.json()["detail"]["mensaje"]

    odoo = OdooFalso(empleado(1))
    monkeypatch.setattr(odoo_api, "cliente", lambda: odoo)
    r = cliente.get("/odoo/personal/ensayo", headers=sesion("admin"))
    assert r.status_code == 200 and r.json()["ensayo"] is True
    assert de_prueba(db) == 0
    r = cliente.post("/odoo/personal/sincronizar", headers=sesion("admin"))
    assert r.status_code == 200 and len(r.json()["altas"]) == 1
    admin = db.query(m.Usuario).filter_by(correo="admin@centauro.lat").one()
    assert db.query(m.SincronizacionOdoo).one().hecha_por_id == admin.persona_id
    assert db.query(m.RegistroAdmin).filter_by(
        objeto="sincronizacion_odoo").count() == 1


def test_si_odoo_no_contesta_se_dice_claro(cliente, sesion, monkeypatch):
    monkeypatch.setattr(odoo_api, "cliente", lambda: OdooCaido())
    r = cliente.post("/odoo/personal/sincronizar", headers=sesion("admin"))
    assert r.status_code == 502, r.text
    assert "vencido" in r.json()["detail"]["mensaje"]


def test_la_conexion_no_escribe_en_odoo():
    odoo = odoo_api.Odoo("https://odoo.invalid", "llave")
    for metodo in ("write", "create", "unlink"):
        with pytest.raises(RuntimeError):
            odoo.llamar("hr.employee", metodo, ids=[1], vals={})

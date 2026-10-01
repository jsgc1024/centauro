# -*- coding: utf-8 -*-
"""Seccion 105 (g5): cambiar al consultor titular y la cuenta bancaria
que viene de Odoo.

Decisiones 13 y 7 de Salvador (29 sep). Direccion de operaciones cambia
al titular desde la ficha, con bitacora y aviso a los dos; desde ese
momento los avisos, los plazos y la comision completa son del nuevo, y
lo cerrado y pagado al anterior no se toca; a un titular con servicios
vivos no se le cierra el acceso. Y la cuenta bancaria del personal se
lee de Odoo en la lectura de cada hora: con cuenta se copia, sin cuenta
se vacia, sin permiso no se toca; el numero solo lo ve quien deposita,
la ficha de la persona y el arranque dicen a quien le falta.
"""
from datetime import timedelta

import pytest
from sqlalchemy import text

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana,
                    servicio_para_cierre)
from app import models as m
from app import odoo_api, odoo_personal, push
from test_odoo_personal import DOMINIO, ODOO0, OdooFalso, empleado, leer, persona


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def avisos(monkeypatch):
    """Los avisos al telefono, anotados en vez de mandados."""
    llamadas = []

    def falso(db, persona_id, titulo, cuerpo, **extra):
        llamadas.append({"persona_id": persona_id, "titulo": titulo,
                         "cuerpo": cuerpo, **extra})
        return {"enviados": 1, "telefonos": 1, "apagadas": 0}

    monkeypatch.setattr(push, "avisar", falso)
    return llamadas


@pytest.fixture
def sin_personal_de_odoo(base_de_pruebas):
    """Lo que la lectura de Odoo da de alta se va al terminar: la persona
    y su acceso son catalogo y no se vacian entre pruebas."""
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


# ================================================================ decorado

def _eventual(cliente, sesion, datos, consultor, offset=300, dias=1):
    """Un eventual planeado a nombre de ese consultor."""
    return crear_servicio(
        cliente, sesion("diroperaciones"), datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"])
         for i in range(dias)],
        consultor_id=datos["personal"][consultor]["id"])


def _implantado(cliente, sesion, datos, consultor):
    r = cliente.post("/implantados/servicio", headers=sesion("diroperaciones"), json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
        "consultor_id": datos["personal"][consultor]["id"]})
    assert r.status_code == 201, r.text
    return r.json()["servicio_id"]


def _servicio_terminado(cliente, sesion, datos, offset=900):
    """Un eventual de Ana, cotizado y trabajado, con su cierre abierto
    (la comprobacion del personal) y todavia sin visto bueno."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("juan"), j)
    r = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir", headers=h)
    assert r.status_code == 200, r.text
    return servicio, r.json()["cierre_id"]


def _cambiar(cliente, sesion, servicio_id, consultor_id, quien="diroperaciones",
             motivo="Vacaciones de tres semanas"):
    return cliente.put(f"/servicios/{servicio_id}/titular", headers=sesion(quien),
                       json={"consultor_id": consultor_id, "motivo": motivo})


def _titular(cliente, sesion, servicio_id):
    r = cliente.get(f"/servicios/{servicio_id}", headers=sesion("dirgeneral"))
    assert r.status_code == 200, r.text
    return r.json()["consultor_id"]


def _usuario_de(cliente, sesion, correo):
    r = cliente.get("/auth/usuarios", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    return next(u for u in r.json() if u["correo"] == correo)


@pytest.fixture
def beatriz_con_acceso(cliente, sesion):
    """Pase lo que pase en la prueba, Beatriz termina con su acceso
    abierto: los accesos son catalogo y no se vacian entre pruebas."""
    yield
    u = _usuario_de(cliente, sesion, "beatriz.roman@centauro.lat")
    if not u["activo"]:
        r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/reactivar",
                         headers=sesion("admin"), json={"motivo": "fin de prueba"})
        assert r.status_code == 200, r.text


# ========================================================== decision 13

def test_el_titular_lo_cambia_direccion_de_operaciones(cliente, sesion, datos,
                                                       avisos):
    """Finanzas y el propio consultor no pueden (403); direccion de
    operaciones si, y direccion general por lo que hereda. El motivo es
    obligatorio: es lo que queda en la bitacora."""
    servicio = _eventual(cliente, sesion, datos, "Ana Solis")
    beatriz = datos["personal"]["Beatriz Roman"]["id"]
    for quien in ("finanzas", "consultor", "central"):
        r = _cambiar(cliente, sesion, servicio["id"], beatriz, quien)
        assert r.status_code == 403, (quien, r.text)
        assert r.json()["detail"]["actividad"] == "servicios.titular"
    r = _cambiar(cliente, sesion, servicio["id"], beatriz, motivo="   ")
    assert r.status_code == 400, r.text
    assert "motivo" in r.json()["detail"]["mensaje"]

    r = _cambiar(cliente, sesion, servicio["id"], beatriz)
    assert r.status_code == 200, r.text
    assert r.json()["nuevo"]["nombre"] == "Beatriz Roman"
    assert r.json()["anterior"]["nombre"] == "Ana Solis"
    assert _titular(cliente, sesion, servicio["id"]) == beatriz
    # Y de regreso, direccion general.
    ana = datos["personal"]["Ana Solis"]["id"]
    r = _cambiar(cliente, sesion, servicio["id"], ana, "dirgeneral")
    assert r.status_code == 200, r.text
    assert _titular(cliente, sesion, servicio["id"]) == ana


def test_solo_a_un_consultor_con_acceso_abierto_y_no_al_mismo(
        cliente, sesion, datos, avisos, beatriz_con_acceso):
    """A Juan, que es personal de campo, no; a Beatriz con el acceso
    cerrado, tampoco (409 con que hacer); y al que ya es titular, no."""
    servicio = _eventual(cliente, sesion, datos, "Ana Solis")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    r = _cambiar(cliente, sesion, servicio["id"], juan)
    assert r.status_code == 409, r.text
    assert "consultor con acceso abierto" in r.json()["detail"]["mensaje"]

    u = _usuario_de(cliente, sesion, "beatriz.roman@centauro.lat")
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/desactivar",
                     headers=sesion("admin"), json={"motivo": "prueba"})
    assert r.status_code == 200, r.text
    r = _cambiar(cliente, sesion, servicio["id"], datos["personal"]["Beatriz Roman"]["id"])
    assert r.status_code == 409, r.text
    assert "Accesos" in r.json()["detail"]["que_hacer"]

    r = _cambiar(cliente, sesion, servicio["id"], datos["personal"]["Ana Solis"]["id"])
    assert r.status_code == 409, r.text
    assert "ya es el consultor titular" in r.json()["detail"]["mensaje"]
    assert _titular(cliente, sesion, servicio["id"]) == datos["personal"]["Ana Solis"]["id"]


def test_el_cambio_deja_bitacora_avisa_a_los_dos_y_la_comision_es_del_nuevo(
        cliente, sesion, datos, avisos, db):
    """Ana lleva un servicio ya trabajado; se le pasa a Beatriz. Queda en
    la bitacora del servicio quien cambio a quien y por que, salen dos
    correos y dos avisos al telefono, la escalacion de la hoja lo trae a
    el, y cuando finanzas aprueba el cierre la comision completa es de
    Beatriz."""
    servicio, cierre_id = _servicio_terminado(cliente, sesion, datos, offset=910)
    ana = datos["personal"]["Ana Solis"]["id"]
    beatriz = datos["personal"]["Beatriz Roman"]["id"]

    r = _cambiar(cliente, sesion, servicio["id"], beatriz,
                 motivo="Ana sale de vacaciones tres semanas")
    assert r.status_code == 200, r.text
    assert r.json()["hojas_por_republicar"] == 0

    fila = (db.query(m.RegistroAccion)
            .filter_by(servicio_id=servicio["id"], accion="cambio de titular").one())
    assert fila.detalle == "Ana Solis -> Beatriz Roman: Ana sale de vacaciones tres semanas"
    assert fila.rol == m.Rol.DIRECTOR_OPERACIONES and not fila.en_cobertura
    assert fila.titular_id == beatriz

    correos = (db.query(m.Notificacion)
               .filter_by(servicio_id=servicio["id"], canal=m.Canal.CORREO,
                          destinatario=m.Destinatario.CONSULTOR)
               .filter(m.Notificacion.asunto.like(f"{servicio['folio']}:%"))
               .all())
    por_correo = {n.correo: n for n in correos}
    assert por_correo["beatriz.roman@centauro.lat"].asunto == (
        f"{servicio['folio']}: ahora eres su consultor titular")
    assert por_correo["ana.solis@centauro.lat"].asunto == (
        f"{servicio['folio']}: Beatriz Roman pasa a ser su consultor titular")
    assert "vacaciones" in por_correo["ana.solis@centauro.lat"].datos
    assert por_correo["beatriz.roman@centauro.lat"].enlace_seguimiento == (
        f"/consola/#/servicio/{servicio['id']}")

    telefonos = {a["persona_id"]: a for a in avisos}
    assert telefonos[beatriz]["titulo"] == push.tx(
        "es", "titular_entra_titulo", folio=servicio["folio"])
    assert telefonos[ana]["titulo"] == push.tx(
        "es", "titular_sale_titulo", nuevo="Beatriz Roman", folio=servicio["folio"])
    assert telefonos[ana]["url"] == f"/consola/#/servicio/{servicio['id']}"

    # La escalacion de la hoja: nivel 1 es el titular de ahora.
    from app import tasksheet
    niveles = tasksheet._escalacion(db, db.get(m.Servicio, servicio["id"]))
    assert niveles[0]["nombre"] == "Beatriz Roman"

    # Beatriz da el visto bueno; finanzas aprueba: la comision es suya.
    envio = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                         headers=sesion("consultor2"))
    assert envio.status_code == 200, envio.text
    aprobacion = cliente.post(f"/cierre/{cierre_id}/aprobar",
                              headers=sesion("finanzas"))
    assert aprobacion.status_code == 200, aprobacion.text
    comision = aprobacion.json()["comision_consultor"]
    assert comision["consultor"] == "Beatriz Roman"
    assert comision["estatus"] == "generada"
    filas = db.query(m.ComisionConsultor).filter_by(servicio_id=servicio["id"]).all()
    assert [c.consultor_id for c in filas] == [beatriz]
    # Ya cerrado, ya no cambia de titular.
    r = _cambiar(cliente, sesion, servicio["id"], ana)
    assert r.status_code == 409, r.text
    assert "cerrado" in r.json()["detail"]["mensaje"]


def test_la_comision_ya_pagada_al_anterior_sigue_igual(cliente, sesion, datos,
                                                       avisos, db):
    """Un servicio de Ana cerrado y con su comision pagada, y otro vivo
    que se le pasa a Beatriz: la comision pagada se queda con Ana tal
    cual, y el cerrado no acepta el cambio."""
    cerrado, cierre_id = servicio_para_cierre(cliente, sesion, datos, offset=920)
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    ana = datos["personal"]["Ana Solis"]["id"]
    beatriz = datos["personal"]["Beatriz Roman"]["id"]
    comision = db.query(m.ComisionConsultor).filter_by(servicio_id=cerrado["id"]).one()
    assert comision.consultor_id == ana
    comision.estatus = m.EstatusComision.PAGADA
    db.commit()
    monto = comision.monto

    vivo = _eventual(cliente, sesion, datos, "Ana Solis", offset=930)
    r = _cambiar(cliente, sesion, vivo["id"], beatriz)
    assert r.status_code == 200, r.text
    r = _cambiar(cliente, sesion, cerrado["id"], beatriz)
    assert r.status_code == 409, r.text

    db.expire_all()
    comision = db.query(m.ComisionConsultor).filter_by(servicio_id=cerrado["id"]).one()
    assert (comision.consultor_id, comision.estatus, comision.monto) == (
        ana, m.EstatusComision.PAGADA, monto)
    assert _titular(cliente, sesion, cerrado["id"]) == ana
    assert _titular(cliente, sesion, vivo["id"]) == beatriz


def test_con_el_cierre_abierto_el_plazo_sigue_y_el_aviso_va_al_nuevo(
        cliente, sesion, datos, avisos, db):
    """El cierre ya corre cuando cambia el titular: el plazo del visto
    bueno es el mismo, pero «arrancan tus 24 horas» le llega a Beatriz,
    por correo y al telefono, y no a Ana."""
    from app import cierre as motor
    servicio, cierre_id = _servicio_terminado(cliente, sesion, datos, offset=940)
    beatriz = datos["personal"]["Beatriz Roman"]["id"]
    assert _cambiar(cliente, sesion, servicio["id"], beatriz).status_code == 200
    avisos.clear()

    cierre = db.get(m.Cierre, cierre_id)
    assert cierre.estatus == m.EstatusCierre.ABIERTO
    t1 = cierre.comprobacion_hasta
    assert motor.avanzar(db, cierre, t1 + timedelta(minutes=1))
    db.commit()
    assert cierre.limite_consultor == t1 + timedelta(hours=motor.HORAS_CONSULTOR)

    aviso = (db.query(m.Notificacion)
             .filter_by(servicio_id=servicio["id"], canal=m.Canal.CORREO)
             .filter(m.Notificacion.asunto.like("%24 h para el visto bueno%"))
             .one())
    assert aviso.correo == "beatriz.roman@centauro.lat"
    assert [a["persona_id"] for a in avisos] == [beatriz]


def test_la_baja_del_acceso_de_un_titular_con_servicios_vivos_se_niega(
        cliente, sesion, datos, avisos, beatriz_con_acceso):
    """Beatriz lleva un eventual y un implantado; uno cancelado sin nada
    que cerrar no cuenta. Cerrarle el acceso --desde Accesos o desde la
    baja en Catalogos-- contesta 409 con cuantos y cuales; con los dos
    ya cambiados a Ana, el acceso se cierra."""
    eventual = _eventual(cliente, sesion, datos, "Beatriz Roman", offset=950)
    implantado = _implantado(cliente, sesion, datos, "Beatriz Roman")
    cancelado = _eventual(cliente, sesion, datos, "Beatriz Roman", offset=960)
    r = cliente.post(f"/servicios/{cancelado['id']}/cancelar",
                     headers=sesion("diroperaciones"), json={"motivo": "prueba"})
    assert r.status_code == 200, r.text

    u = _usuario_de(cliente, sesion, "beatriz.roman@centauro.lat")
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/desactivar",
                     headers=sesion("admin"), json={"motivo": "se va"})
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["mensaje"].startswith("Tiene 2 servicio(s) como titular")
    assert sorted(s["servicio_id"] for s in d["servicios"]) == sorted(
        [eventual["id"], implantado])
    assert eventual["folio"] in d["que_hacer"]
    # La baja desde Catalogos cierra el mismo acceso: mismo candado.
    beatriz = datos["personal"]["Beatriz Roman"]["id"]
    r = cliente.delete(f"/catalogos/personal/{beatriz}", headers=sesion("admin"))
    assert r.status_code == 409, r.text
    assert "como titular" in r.json()["detail"]["mensaje"]
    assert _usuario_de(cliente, sesion, "beatriz.roman@centauro.lat")["activo"]

    ana = datos["personal"]["Ana Solis"]["id"]
    for sid in (eventual["id"], implantado):
        assert _cambiar(cliente, sesion, sid, ana, motivo="Baja de Beatriz").status_code == 200
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/desactivar",
                     headers=sesion("admin"), json={"motivo": "se va"})
    assert r.status_code == 200, r.text
    assert not _usuario_de(cliente, sesion, "beatriz.roman@centauro.lat")["activo"]


def test_la_hoja_publicada_se_vuelve_a_publicar(cliente, sesion, datos, avisos, db):
    """La hoja publicada del eventual lleva al titular como nivel 1 de la
    escalacion y es una foto: con otro titular la respuesta dice cuantas
    hojas hay que volver a publicar."""
    servicio = _eventual(cliente, sesion, datos, "Ana Solis", offset=970)
    db.add(m.TaskSheet(servicio_id=servicio["id"],
                       equipo_id=servicio["equipos"][0]["id"], version=1,
                       estatus=m.EstatusTaskSheet.PUBLICADO, contenido="{}"))
    db.commit()
    r = _cambiar(cliente, sesion, servicio["id"], datos["personal"]["Beatriz Roman"]["id"])
    assert r.status_code == 200, r.text
    assert r.json()["hojas_por_republicar"] == 1


def test_la_consola_ofrece_cambiar_titular_solo_a_quien_puede():
    """Las dos fichas pintan el renglon del titular con su boton, que
    solo sale con `servicios.titular`, y Accesos dice de que servicios
    es titular quien no se pudo dar de baja."""
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / "app" / "web"
    titular = (web / "titular.js").read_text(encoding="utf-8")
    assert 'tiene(sesion.usuario, "servicios.titular")' in titular
    assert "/titular`" in titular and 't("tit_cambiar")' in titular
    for pantalla in ("servicio.js", "implantado.js"):
        fuente = (web / pantalla).read_text(encoding="utf-8")
        assert "bloqueTitular(servicio, cat)" in fuente, pantalla
    accesos = (web / "accesos.js").read_text(encoding="utf-8")
    assert 't("acc_titular_de")' in accesos


# =========================================================== decision 7

class OdooConCuentas(OdooFalso):
    """El Odoo de mentiras con las cuentas bancarias: `cuentas` son las
    filas de res.partner.bank por su id; `con_permiso` decide si la
    conexion ve el campo del empleado, y `bancos_accesibles` si puede
    leer las cuentas a las que apunta. `campo` es como se llama en este
    Odoo --la cuenta principal de saas~19.3, o bank_account_id en los de
    antes--; `existe` dice si lo tiene, y `catalogo_accesible` si la
    conexion puede leer ir.model.fields para saberlo."""

    def __init__(self, *empleados, cuentas=None, con_permiso=True,
                 bancos_accesibles=True, campo=odoo_personal.CAMPO_CUENTA,
                 existe=True, catalogo_accesible=True, **extra):
        super().__init__(*empleados, **extra)
        self.cuentas = dict(cuentas or {})
        self.con_permiso = con_permiso
        self.bancos_accesibles = bancos_accesibles
        self.campo = campo
        self.existe = existe
        self.catalogo_accesible = catalogo_accesible

    def campos(self, modelo, atributos=None):
        salida = super().campos(modelo, atributos)
        if self.con_permiso and self.existe:
            salida[self.campo] = {"type": "many2one"}
        return salida

    def leer(self, modelo, dominio, campos, archivados=False):
        if modelo == "ir.model.fields":
            if not self.catalogo_accesible:
                raise odoo_api.NoResponde(
                    "Odoo contesto 403: You are not allowed to access "
                    "'Fields' (ir.model.fields) records.")
            return [{"id": 1, "name": self.campo}] if self.existe else []
        if modelo != odoo_personal.MODELO_CUENTA:
            return super().leer(modelo, dominio, campos, archivados)
        self.lecturas.append(("bancos", list(campos)))
        if not self.bancos_accesibles:
            raise odoo_api.NoResponde(
                "Odoo contesto 403: You are not allowed to access "
                "'Bank Accounts' (res.partner.bank) records.")
        ids = dominio[0][2]
        return [{"id": i, **{c: self.cuentas[i].get(c, False) for c in campos}}
                for i in ids if i in self.cuentas]


CUENTA = {"acc_number": "012180001234567890", "acc_holder_name": False,
          "bank_id": [3, "BBVA"], "partner_id": [77, "Agente Odoo 1"]}


def _con_cuenta(n=1, cuenta_id=501, campo=odoo_personal.CAMPO_CUENTA,
                **cambios):
    return empleado(n, **{campo: [cuenta_id, "BBVA 012180001234567890"]},
                    **cambios)


def _bancarios(db, n):
    p = persona(db, n)
    return p.clabe, p.banco, p.titular_cuenta


def test_la_cuenta_de_odoo_se_copia_en_el_alta_y_cuando_cambia(
        sin_personal_de_odoo, db):
    """Con cuenta en Odoo entran la CLABE, el banco y el titular --el
    contacto dueno de la cuenta si RH no escribio otro nombre--, en una
    sola lectura por lote; si RH la corrige, cambia aqui."""
    odoo = OdooConCuentas(_con_cuenta(1), empleado(2), cuentas={501: CUENTA})
    informe = leer(db, odoo)
    assert len(informe["altas"]) == 2 and not informe["pendientes"]
    assert informe["cuentas"] == {"con_cuenta": 1, "sin_cuenta": 1, "error": None}
    assert _bancarios(db, 1) == ("012180001234567890", "BBVA", "Agente Odoo 1")
    assert _bancarios(db, 2) == (None, None, None)
    assert [l for l in odoo.lecturas if l[0] == "bancos"] == [
        ("bancos", odoo_personal.CAMPOS_CUENTA)]
    assert odoo_personal.resumen(informe)["cuentas"]["con_cuenta"] == 1

    odoo.cuentas[501] = {**CUENTA, "acc_number": "014180009876543210",
                         "acc_holder_name": "Maria Odoo Uno",
                         "bank_id": [4, "Santander"]}
    informe = leer(db, odoo)
    assert [c["que"] for c in informe["cambios"]] == [["cuenta bancaria"]]
    assert _bancarios(db, 1) == ("014180009876543210", "Santander", "Maria Odoo Uno")
    # Sin novedad, no hay cambio.
    assert not leer(db, odoo)["cambios"]


def test_con_permiso_y_sin_cuenta_se_vacia(sin_personal_de_odoo, db):
    """RH le quita la cuenta al empleado (o la deja sin numero): Odoo es
    el maestro, y una cuenta vieja no se queda en Connect."""
    odoo = OdooConCuentas(_con_cuenta(1), cuentas={501: CUENTA})
    leer(db, odoo)
    assert _bancarios(db, 1)[0] == "012180001234567890"

    odoo.cambiar(1, primary_bank_account_id=False)
    informe = leer(db, odoo)
    assert [c["que"] for c in informe["cambios"]] == [["cuenta bancaria"]]
    assert informe["cuentas"] == {"con_cuenta": 0, "sin_cuenta": 1, "error": None}
    assert _bancarios(db, 1) == (None, None, None)

    # Una cuenta sin numero tampoco sirve para depositar.
    odoo.cambiar(1, primary_bank_account_id=[502, "sin numero"])
    odoo.cuentas[502] = {**CUENTA, "acc_number": False}
    leer(db, odoo)
    assert _bancarios(db, 1) == (None, None, None)


def test_sin_permiso_de_leer_cuentas_no_se_toca_lo_guardado(
        sin_personal_de_odoo, db):
    """La conexion no ve el campo, o no alcanza res.partner.bank: la
    lectura sigue --altas, cambios, bajas-- sin cuentas, lo dice en el
    resultado, y la cuenta guardada se queda."""
    odoo = OdooConCuentas(_con_cuenta(1), cuentas={501: CUENTA})
    leer(db, odoo)

    sin_campo = OdooConCuentas(_con_cuenta(1, name="Agente Odoo Uno"),
                               cuentas={501: CUENTA}, con_permiso=False)
    informe = leer(db, sin_campo)
    assert informe["cuentas"]["error"].startswith("sin permiso para leer cuentas")
    assert [c["que"] for c in informe["cambios"]] == [["nombre"]]
    assert _bancarios(db, 1) == ("012180001234567890", "BBVA", "Agente Odoo 1")
    assert not [l for l in sin_campo.lecturas if l[0] == "bancos"]
    assert "sin permiso" in odoo_personal.resumen(informe)["cuentas"]["error"]

    sin_bancos = OdooConCuentas(_con_cuenta(1, name="Agente Odoo Uno"),
                                cuentas={501: CUENTA}, bancos_accesibles=False)
    informe = leer(db, sin_bancos)
    assert "sin permiso" in informe["cuentas"]["error"]
    assert "403" in informe["cuentas"]["error"]
    assert not informe["cambios"]
    assert _bancarios(db, 1) == ("012180001234567890", "BBVA", "Agente Odoo 1")

    # Y una cuenta a la que el empleado apunta y no vino: pendiente, sin
    # tocar lo guardado.
    odoo.cambiar(1, primary_bank_account_id=[999, "otra"])
    informe = leer(db, odoo)
    assert informe["pendientes"][0]["falta"] == ["su cuenta bancaria no se pudo leer de Odoo"]
    assert _bancarios(db, 1)[0] == "012180001234567890"


def test_la_cuenta_principal_y_la_de_antes(sin_personal_de_odoo, db):
    """La version saas~19.3 trae la cuenta principal
    (primary_bank_account_id); un Odoo de antes, bank_account_id. Las dos
    se leen igual: con el nombre viejo, la lectura de cada hora decia
    «sin permiso» con el usuario administrador (1 de octubre)."""
    assert odoo_personal.CAMPO_CUENTA == "primary_bank_account_id"
    de_antes = OdooConCuentas(_con_cuenta(1, campo="bank_account_id"),
                              cuentas={501: CUENTA}, campo="bank_account_id")
    informe = leer(db, de_antes)
    assert informe["cuentas"] == {"con_cuenta": 1, "sin_cuenta": 0, "error": None}
    assert _bancarios(db, 1)[0] == "012180001234567890"
    # Se pidio con el nombre que tiene ese Odoo, no con el nuevo.
    listas = [c for c in de_antes.lecturas if isinstance(c, list)]
    assert any("bank_account_id" in c for c in listas)
    assert not any(odoo_personal.CAMPO_CUENTA in c for c in listas)


def test_el_aviso_dice_si_el_campo_no_existe_o_es_permiso(
        sin_personal_de_odoo, db):
    """Sin el campo, la lectura sigue sin cuentas y no toca lo guardado
    (seccion 105), pero el aviso dice por que: que no existe en esta
    version, que el usuario no lo puede leer, o que no se pudo saber."""
    leer(db, OdooConCuentas(_con_cuenta(1), cuentas={501: CUENTA}))
    casos = [
        ({"existe": False}, "el campo de la cuenta bancaria no existe"),
        ({"con_permiso": False}, "sin permiso para leer cuentas"),
        ({"con_permiso": False, "catalogo_accesible": False},
         "no se pudo leer el campo de la cuenta bancaria"),
    ]
    for opciones, aviso in casos:
        odoo = OdooConCuentas(_con_cuenta(1), cuentas={501: CUENTA}, **opciones)
        informe = leer(db, odoo)
        assert informe["cuentas"]["error"].startswith(aviso), opciones
        assert not [l for l in odoo.lecturas if l[0] == "bancos"]
        assert _bancarios(db, 1) == ("012180001234567890", "BBVA", "Agente Odoo 1")
    assert "primary_bank_account_id" in odoo_personal.NO_EXISTE_CUENTA


def _con_deposito_pedido(cliente, sesion, datos, quien, offset):
    """Un dia con esa persona, con viaticos pedidos a finanzas."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=quien, vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    viatico = cliente.post("/viaticos/asignar", headers=h, json={
        "jornada_id": j["id"], "persona_id": quien,
        "conceptos": [{"concepto": "alimentos", "monto": "900",
                       "origen": "tabulador"}]})
    assert viatico.status_code in (200, 201), viatico.text
    r = cliente.post(f"/viaticos/{viatico.json()['id']}/solicitar-transferencia",
                     headers=h)
    assert r.status_code in (200, 201), r.text
    return servicio


def _fila(cliente, sesion, quien, folio):
    r = cliente.get("/viaticos/finanzas/bandeja", headers=sesion(quien))
    assert r.status_code == 200, r.text
    return next(f for p in r.json()["paises"] for f in p["depositos"]
                if f["folio"] == folio)


def test_finanzas_ve_el_numero_y_los_demas_si_tiene_o_falta(
        cliente, sesion, datos, db):
    """En la bandeja, finanzas y direccion general ven la CLABE con su
    banco y su titular; el consultor y la central solo «tiene» o
    «falta», nunca el numero. A quien le falta, le falta para todos."""
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    p = db.get(m.Persona, juan)
    p.clabe, p.banco, p.titular_cuenta = "012180001234567890", "BBVA", "Juan Ramirez"
    db.get(m.Persona, luis).clabe = None
    db.commit()
    try:
        con = _con_deposito_pedido(cliente, sesion, datos, juan, 980)
        sin = _con_deposito_pedido(cliente, sesion, datos, luis, 981)

        for quien in ("finanzas", "dirgeneral"):
            fila = _fila(cliente, sesion, quien, con["folio"])
            assert (fila["cuenta"], fila["clabe"], fila["banco"],
                    fila["titular_cuenta"]) == (
                "tiene", "012180001234567890", "BBVA", "Juan Ramirez"), quien
            fila = _fila(cliente, sesion, quien, sin["folio"])
            assert (fila["cuenta"], fila["clabe"]) == ("falta", None), quien
        for quien in ("consultor", "central"):
            fila = _fila(cliente, sesion, quien, con["folio"])
            assert fila["cuenta"] == "tiene", quien
            assert not ({"clabe", "banco", "titular_cuenta"} & set(fila)), quien
            assert _fila(cliente, sesion, quien, sin["folio"])["cuenta"] == "falta"

        # La ficha de la persona dice si esta o falta, y nunca el numero.
        ficha = cliente.get(f"/profesionalismo/persona/{juan}",
                            headers=sesion("consultor")).json()
        assert ficha["cuenta"] == "tiene" and "clabe" not in ficha
        ficha = cliente.get(f"/profesionalismo/persona/{luis}",
                            headers=sesion("consultor")).json()
        assert ficha["cuenta"] == "falta"
    finally:
        db.expire_all()
        p = db.get(m.Persona, juan)
        p.clabe = p.banco = p.titular_cuenta = None
        db.commit()


def test_en_connect_no_se_captura_la_cuenta(cliente, sesion, datos):
    """La cuenta bancaria vive en Odoo: el catalogo de personal no la
    acepta ni la devuelve."""
    juan = datos["personal"]["Juan Ramirez"]
    h = sesion("admin")
    r = cliente.patch(f"/catalogos/personal/{juan['id']}", headers=h, json={
        "nombre": juan["nombre"], "correo": juan["correo"],
        "plaza_id": juan["plaza_id"], "clabe": "012180001234567890",
        "banco": "BBVA"})
    assert r.status_code == 200, r.text
    assert "clabe" not in r.json() and "banco" not in r.json()
    from app.db import SessionLocal
    with SessionLocal() as db:
        assert db.get(m.Persona, juan["id"]).clabe is None


def test_el_arranque_cuenta_a_quien_le_falta_la_cuenta(cliente, sesion, datos, db):
    """El renglon «con cuenta bancaria en Odoo» del arranque: en rojo con
    todos sin cuenta, en camino cuando a alguien le falta --con sus
    nombres--, y listo cuando todos la tienen."""
    def renglon(idioma="es"):
        r = cliente.get(f"/manual/arranque?idioma={idioma}", headers=sesion("dirgeneral"))
        assert r.status_code == 200, r.text
        return next(x for g in r.json()["grupos"] for x in g["renglones"]
                    if x["clave"] == "cuentas_bancarias")

    # El mismo personal de campo que cuentan los renglones vecinos: activo,
    # de la calle y sin un acceso de oficina.
    de_oficina = (db.query(m.Usuario.persona_id)
                  .filter(m.Usuario.rol != m.Rol.PERSONAL_SEGURIDAD))
    campo = (db.query(m.Persona)
             .filter(m.Persona.activo.is_(True), m.Persona.oficina.is_(False),
                     m.Persona.id.notin_(de_oficina))
             .order_by(m.Persona.nombre).all())
    assert campo
    try:
        for p in campo:
            p.clabe = None
        db.commit()
        x = renglon()
        assert x["tono"] == "grave"
        assert x["como"].startswith(f"{len(campo)} de {len(campo)} personas de seguridad "
                                    "activas sin cuenta bancaria en Odoo")
        assert x["ir"] == "#/odoo" and x["quien"]
        assert sorted(x["sin_cuenta"]) == sorted(p.nombre for p in campo)

        for p in campo[1:]:
            p.clabe = "012180001234567890"
        db.commit()
        x = renglon()
        assert x["tono"] == "alerta"
        assert campo[0].nombre in x["como"] and x["sin_cuenta"] == [campo[0].nombre]
        assert "sem conta" in renglon("pt")["como"]

        campo[0].clabe = "012180001234567890"
        db.commit()
        x = renglon()
        assert x["tono"] == "ok" and x["sin_cuenta"] == []
    finally:
        for p in campo:
            p.clabe = None
        db.commit()

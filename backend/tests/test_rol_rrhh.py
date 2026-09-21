"""Recursos Humanos: firma el bono y reparte los accesos.

Lo que no trae, y es el punto: depositar. Autorizar el bono del mes y
pagarlo son el unico control que tiene ese dinero, y juntos en una mano
el control es la buena fe.

Y como RRHH ahora reparte los accesos --o sea, es quien podria darse lo
que le falta--, esa regla dejo de vivir en la costumbre y vive en el
codigo: nadie se da accesos a si mismo, y hay actividades que no pueden
juntarse ni por permiso suelto ni armando un puesto que ya las traiga.
"""
from datetime import date

from ayudas import asignar, configurar_origen, crear_servicio, \
    ejecutar_jornada, jornada


def _un_mes(cliente, sesion, datos, dia_base=22):
    h = sesion("consultor")
    hoy = date.today()
    fecha = date(hoy.year, hoy.month, min(max(1, dia_base), 27))
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(fecha, datos["modalidades"]["full_day"]["id"])])
    persona = datos["personal"]["Luis Mendoza"]["id"]
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=persona,
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("luis"), j)

    cliente.post("/evaluaciones",
                 json={"persona_id": persona, "anio": hoy.year,
                       "mes": hoy.month, "capacitacion_cumplida": True},
                 headers=h)

    from app import models as m
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        return (db.query(m.EvaluacionMensual)
                .filter_by(persona_id=persona, anio=hoy.year, mes=hoy.month)
                .first().id)
    finally:
        db.close()


def _id_de(cliente, sesion, correo):
    usuarios = cliente.get("/auth/usuarios", headers=sesion("admin")).json()
    fila = next(u for u in usuarios if u["correo"] == correo)
    return fila["usuario_id"]


# --------------------------------------------------------------- el bono

def test_rrhh_firma_el_bono(cliente, sesion, datos):
    evaluacion = _un_mes(cliente, sesion, datos, dia_base=22)
    r = cliente.post(f"/evaluaciones/{evaluacion}/autorizar",
                     headers=sesion("rrhh"))
    assert r.status_code == 200


def test_operaciones_ya_no_firma_el_bono(cliente, sesion, datos):
    """Se movio a RRHH por decision de Salvador, 20 de septiembre.
    Operaciones sigue clasificando incidencias: eso si es suyo."""
    evaluacion = _un_mes(cliente, sesion, datos, dia_base=23)
    r = cliente.post(f"/evaluaciones/{evaluacion}/autorizar",
                     headers=sesion("diroperaciones"))
    assert r.status_code == 403


def test_rrhh_no_deposita(cliente, sesion, datos):
    """Firma y no paga. Es la mitad del candado."""
    evaluacion = _un_mes(cliente, sesion, datos, dia_base=24)
    cliente.post(f"/evaluaciones/{evaluacion}/autorizar",
                 headers=sesion("rrhh"))
    r = cliente.post(f"/evaluaciones/{evaluacion}/pagar",
                     json={"referencia": "SPEI-77001"}, headers=sesion("rrhh"))
    assert r.status_code == 403


# ------------------------------------------------------------ los accesos

def test_rrhh_abre_la_pantalla_de_accesos(cliente, sesion, datos):
    r = cliente.get("/auth/usuarios", headers=sesion("rrhh"))
    assert r.status_code == 200


def test_nadie_se_da_accesos_a_si_mismo(cliente, sesion, datos):
    """La otra mitad del candado. Quien reparte permisos y puede
    dárselos a si mismo, los tiene todos."""
    yo = _id_de(cliente, sesion, "rrhh@centauro.lat")
    r = cliente.post(f"/auth/usuarios/{yo}/permisos",
                     json={"actividad": "bonos.pagar",
                           "motivo": "para cerrar mas rapido el mes"},
                     headers=sesion("rrhh"))
    assert r.status_code == 409
    assert "a ti mismo" in str(r.json()["detail"])


def test_firmar_y_depositar_no_caben_en_la_misma_persona(
        cliente, sesion, datos):
    """Finanzas ya deposita; darle ademas la firma juntaria las dos."""
    quien = _id_de(cliente, sesion, "finanzas@centauro.lat")
    r = cliente.post(f"/auth/usuarios/{quien}/permisos",
                     json={"actividad": "bonos.autorizar",
                           "motivo": "cubre vacaciones de RRHH"},
                     headers=sesion("rrhh"))
    assert r.status_code == 409
    assert "no puede convivir" in str(r.json()["detail"])


def test_un_puesto_tampoco_puede_traer_las_dos(cliente, sesion, datos):
    """Sin esto, el candado se esquiva armando un puesto que ya las
    trae juntas y poniendoselo a alguien."""
    r = cliente.post("/auth/categorias", json={
        "nombre": "Administracion del bono",
        "actividades": ["bonos.ver", "bonos.autorizar", "bonos.pagar"]},
        headers=sesion("rrhh"))
    assert r.status_code == 409
    assert "a la vez" in str(r.json()["detail"])


def test_un_puesto_con_una_sola_de_las_dos_si_se_arma(cliente, sesion, datos):
    r = cliente.post("/auth/categorias", json={
        "nombre": "Cierre del mes",
        "actividades": ["bonos.ver", "bonos.autorizar"]},
        headers=sesion("rrhh"))
    assert r.status_code == 201

"""La nomina paga por rol y por dia de servicio.

Desde que el rol es de la tarea, el mismo agente cobra distinto si el
martes condujo y el miercoles coordino. El corte tiene que poder decirlo
—el recibo lo va a reclamar quien no le cuadre— y tiene que poder
sumarse por rol, que es la cuenta que pide la direccion.
"""
from datetime import date

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana)


def _dos_dias_con_dos_roles(cliente, sesion, datos):
    """Juan trabaja dos dias: uno de conductor y otro de agente."""
    h = sesion("consultor")
    dias = [manana(70), manana(71)]
    servicio = crear_servicio(cliente, h, datos, [
        jornada(d, datos["modalidades"]["full_day"]["id"]) for d in dias],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    # Se cotiza lo que se va a ejecutar: un dia de conductor y uno de
    # agente. Cotizar dos de conductor y mandar un agente es una
    # desviacion, y el cierre la frena con razon.
    roles = ["conductor_seguridad", "agente_seguridad"]
    cotizar_y_autorizar(cliente, h, servicio,
                        datos["perfiles"]["conductor_seguridad"]["id"],
                        datos["categorias"]["suv_blindada"]["id"],
                        roles_por_dia=[datos["perfiles"][r]["id"]
                                       for r in roles])

    juan = datos["personal"]["Juan Ramirez"]["id"]
    for j, rol in zip(servicio["equipos"][0]["jornadas"], roles):
        r = asignar(cliente, h, j["id"], persona_id=juan,
                    vehiculo_id=datos["suburban"]["id"], rol=rol)[0]
        assert r.status_code == 200, r.text
        configurar_origen(cliente, h, j["id"])
        ejecutar_jornada(cliente, sesion("juan"), j)

    # El eventual entra al corte cuando su cierre ya va camino a
    # facturacion: hasta entonces el servicio todavia se puede mover.
    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                          headers=h).json()
    envio = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas",
                         headers=h)
    assert envio.status_code == 200, envio.text
    return servicio


def _corte(cliente, f, datos):
    r = cliente.post("/nomina/calcular", json={"pais_id": datos["mx"]["id"]},
                     headers=f)
    assert r.status_code == 200, r.text
    return cliente.get(f"/nomina/{r.json()['nomina_id']}", headers=f).json()


def test_cada_dia_se_paga_con_el_rol_de_ese_dia(cliente, sesion, datos):
    _dos_dias_con_dos_roles(cliente, sesion, datos)
    n = _corte(cliente, sesion("finanzas"), datos)

    juan = next(r for r in n["renglones"] if r["persona"] == "Juan Ramirez")
    roles = {c["rol"] for c in juan["conceptos"] if not c["es_ajuste"]}
    assert roles == {"Conductor de seguridad", "Agente de seguridad"}, roles

    # Y el recibo lo dice en la descripcion, que es lo que la persona lee.
    assert any("Conductor de seguridad" in c["descripcion"]
               for c in juan["conceptos"])


def test_el_corte_se_suma_por_rol(cliente, sesion, datos):
    """La cuenta que pide la direccion: cuanto se fue en conductores y
    cuanto en agentes. De un total plano no se saca."""
    _dos_dias_con_dos_roles(cliente, sesion, datos)
    n = _corte(cliente, sesion("finanzas"), datos)

    por_rol = {r["rol"]: r for r in n["por_rol"]}
    assert "Conductor de seguridad" in por_rol
    assert "Agente de seguridad" in por_rol
    # El agente se paga mas que el conductor en el tabulador de la semilla.
    assert float(por_rol["Agente de seguridad"]["monto"]) > \
        float(por_rol["Conductor de seguridad"]["monto"])
    assert sum(r["dias"] for r in n["por_rol"]) == n["dias_pagados"]


def test_el_rol_del_recibo_no_cambia_si_alguien_corrige_la_asignacion(
        cliente, sesion, datos):
    """El pago se congela con su rol. Si despues alguien corrige el rol
    de la jornada, el recibo de una semana ya pagada no puede moverse
    solo: eso es rehacer el pasado."""
    from app import models as m
    from app.db import SessionLocal

    _dos_dias_con_dos_roles(cliente, sesion, datos)
    f = sesion("finanzas")
    n = _corte(cliente, f, datos)
    juan = next(r for r in n["renglones"] if r["persona"] == "Juan Ramirez")
    antes = [c["rol"] for c in juan["conceptos"] if not c["es_ajuste"]]

    cliente.post(f"/nomina/{n['id']}/pagar", headers=f)

    # Alguien corrige el rol de esas jornadas despues de pagar.
    db = SessionLocal()
    try:
        coordinador = (db.query(m.PerfilPersonal)
                       .filter_by(codigo="coordinador_seguridad").first())
        for c in (db.query(m.ConceptoNomina)
                  .filter(m.ConceptoNomina.jornada_id.isnot(None)).all()):
            asignaciones = (db.query(m.AsignacionPersonal)
                            .filter_by(jornada_id=c.jornada_id).all())
            for a in asignaciones:
                a.rol_id = coordinador.id
        db.commit()
    finally:
        db.close()

    despues_n = cliente.get(f"/nomina/{n['id']}", headers=f).json()
    juan = next(r for r in despues_n["renglones"]
                if r["persona"] == "Juan Ramirez")
    despues = [c["rol"] for c in juan["conceptos"] if not c["es_ajuste"]]
    assert despues == antes, "el recibo pagado cambio solo"


def test_sin_rol_el_dinero_se_detiene_antes_de_la_nomina(cliente, sesion,
                                                         datos):
    """Un dia sin rol no tiene tarifa que buscar, ni para cobrarle al
    cliente ni para pagarle a la persona.

    Y se detiene en el cierre, que es el primer momento en que ese dia
    toca dinero: mas vale que el consultor lo resuelva al cerrar que
    descubrirlo el lunes, cuando finanzas no puede hacer nada.
    """
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(75), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(cliente, h, servicio,
                        datos["perfiles"]["conductor_seguridad"]["id"],
                        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    # Sin rol, a proposito.
    r = asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Luis Mendoza"]["id"],
                vehiculo_id=datos["suburban"]["id"], rol=None)[0]
    assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("luis"), j)

    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                          headers=h).json()
    envio = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas",
                         headers=h)
    assert envio.status_code == 400, envio.text
    assert "sin rol" in str(envio.json()["detail"]).lower()


# ------------------------------------------- el tabulador de comisiones

def test_las_dos_tablas_salen_completas(cliente, sesion, datos):
    """Todos los roles contra todas las modalidades, tengan monto o no.
    Un cruce que falta es un dia que no se va a poder pagar."""
    f = sesion("finanzas")
    r = cliente.get(f"/nomina/tabulador?pais_id={datos['mx']['id']}",
                    headers=f)
    assert r.status_code == 200, r.text
    tab = r.json()

    for tipo in ("eventual", "implantado"):
        renglones = tab[tipo]["renglones"]
        assert len(renglones) == 4, f"{tipo}: {len(renglones)} roles"
        for renglon in renglones:
            assert len(renglon["celdas"]) == len(tab[tipo]["modalidades"])

    # El implantado es siempre dia completo: una sola columna, y es esa.
    assert len(tab["implantado"]["modalidades"]) == 1
    assert tab["implantado"]["modalidades"][0]["codigo"] == "full_day"
    assert len(tab["eventual"]["modalidades"]) == len(tab["modalidades"])


def test_eventual_e_implantado_se_pagan_por_tablas_distintas(cliente, sesion,
                                                             datos):
    """Tocar una no mueve la otra: es justo lo que pasaba cuando era una
    sola tabla."""
    f = sesion("finanzas")
    mx = datos["mx"]["id"]
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    full_day = datos["modalidades"]["full_day"]["id"]

    r = cliente.put("/nomina/tabulador", json={
        "pais_id": mx, "tipo_servicio": "implantado",
        "renglones": [{"perfil_id": conductor, "modalidad_id": full_day,
                       "monto": "950", "monto_hora_extra": "120"}],
    }, headers=f)
    assert r.status_code == 200, r.text

    tab = cliente.get(f"/nomina/tabulador?pais_id={mx}", headers=f).json()

    def celda(tipo):
        renglon = next(x for x in tab[tipo]["renglones"]
                       if x["perfil_id"] == conductor)
        return next(c for c in renglon["celdas"]
                    if c["modalidad_id"] == full_day)

    assert float(celda("implantado")["monto"]) == 950
    assert float(celda("eventual")["monto"]) == 700, "se movio el eventual"


def test_el_dia_de_implantado_se_paga_con_la_tabla_de_implantado(
        cliente, sesion, datos):
    """La prueba de fondo: cambiar la tabla de implantado cambia lo que
    se le paga a la gente de un implantado, y solo a ella."""
    from app import models as m
    from app import nomina as motor
    from app.db import SessionLocal

    f = sesion("finanzas")
    mx = datos["mx"]["id"]
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    full_day = datos["modalidades"]["full_day"]["id"]
    cliente.put("/nomina/tabulador", json={
        "pais_id": mx, "tipo_servicio": "implantado",
        "renglones": [{"perfil_id": conductor, "modalidad_id": full_day,
                       "monto": "1234", "monto_hora_extra": None}],
    }, headers=f)

    from tests.test_mes_siguiente import _alta
    alta, h = _alta(cliente, sesion, datos)

    db = SessionLocal()
    try:
        servicio = db.get(m.Servicio, alta["servicio_id"])
        jornada = sorted(servicio.equipos[0].jornadas,
                         key=lambda j: j.fecha)[0]
        asignacion = next(a for a in jornada.personal
                          if a.rol_id == conductor)
        pago = motor.pago_de_jornada(db, jornada, asignacion, mx)
        assert float(pago["monto"]) == 1234, pago
    finally:
        db.close()

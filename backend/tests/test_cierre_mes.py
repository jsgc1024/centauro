# -*- coding: utf-8 -*-
"""El cierre por mes del implantado.

Decision de Salvador, 22 de septiembre (PROPUESTA_CIERRE_24H.md, regla
8), y el camino A del 23: un cierre por mes de contrato en la misma
tabla del eventual. Seccion 56 de la bitacora.

Todo pasa en septiembre de 2029, que acaba en domingo: del lunes 24 al
viernes 28 son cinco dias de servicio. La central cierra los dias a mano
con `ahora` en la mano --a las 21:00, una hora despues del termino--,
asi que nada depende del reloj de la maquina.
"""
from datetime import date, datetime, timedelta

H24 = timedelta(hours=24)
MOTIVO = "El equipo cerro por telefono; confirmado con el cliente"
DIAS = [date(2029, 9, d) for d in (24, 25, 26, 27, 28)]
SABADO = date(2029, 9, 29)
DOMINGO = date(2029, 9, 30)


def _alta(cliente, sesion, datos, inicio=DIAS[0]):
    """Un implantado de lunes a viernes, Juan con la Suburban, del 24 al
    fin de septiembre de 2029, con Ana de consultora."""
    r = cliente.post("/implantados", headers=sesion("consultor"), json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "fecha_inicio": str(inicio), "dias_servicio": "lunes_viernes",
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": datos["suburban"]["id"]}],
        "unidades": [datos["suburban"]["id"]],
        "precio_dia_personal": "2900", "precio_mes_vehiculo": "66000",
        "precio_dia_adicional": "3500",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _jornadas(cliente, sesion, servicio_id, anio=2029, mes=9):
    """{fecha: jornada_id} de los dias del mes."""
    panel = cliente.get(f"/implantados/{servicio_id}/mes/{anio}/{mes}",
                        headers=sesion("consultor"))
    assert panel.status_code == 200, panel.text
    return {date.fromisoformat(d["fecha"]): d["jornada_id"]
            for d in panel.json()["dias"]}


def _a_las_21(dia):
    return datetime.combine(dia, datetime.min.time()) + timedelta(hours=21)


def _cerrar(cliente, sesion, jornada_id, dia, ahora=None):
    """La central cierra el dia a mano; si no se dice cuando, una hora
    despues de su termino."""
    r = cliente.post(f"/operacion/jornadas/{jornada_id}/cerrar-a-mano",
                     headers=sesion("central"), json={"justificacion": MOTIVO},
                     params={"ahora": (ahora or _a_las_21(dia)).isoformat()})
    assert r.status_code == 200, r.text


def _cerrar_mes(cliente, sesion, servicio_id, dias=DIAS):
    jornadas = _jornadas(cliente, sesion, servicio_id)
    for dia in dias:
        _cerrar(cliente, sesion, jornadas[dia], dia)
    return jornadas


def _viatico(cliente, sesion, datos, jornada_id, monto="900"):
    r = cliente.post("/viaticos/asignar", headers=sesion("consultor"), json={
        "jornada_id": jornada_id,
        "persona_id": datos["personal"]["Juan Ramirez"]["id"],
        "conceptos": [{"concepto": "alimentos", "monto": monto,
                       "origen": "tabulador"}]})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _cierre(contrato_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = db.query(m.Cierre).filter_by(contrato_id=contrato_id).first()
        if not c:
            return None
        return {"id": c.id, "estatus": c.estatus.value,
                "abierto_en": c.abierto_en,
                "comprobacion_hasta": c.comprobacion_hasta,
                "visto_bueno_desde": c.visto_bueno_desde,
                "limite": c.limite_consultor, "motivo": c.motivo_apertura,
                "servicio_id": c.servicio_id,
                "total_cotizado": float(c.total_cotizado or 0),
                "total_ejecutado": float(c.total_ejecutado or 0)}


def _limites(vids):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return [db.get(m.AsignacionViatico, v).limite_comprobacion
                for v in vids]


def _avanzar(cierre_id, ahora):
    """Lo que hace la tarea de cada cinco minutos, a una hora dada."""
    from app import cierre as motor
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        movio = motor.avanzar(db, db.get(m.Cierre, cierre_id), ahora)
        db.commit()
        return movio


def _estatus(cliente, sesion, servicio_id):
    r = cliente.get(f"/servicios/{servicio_id}", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()["estatus"]


# El servicio no recorre la cadena: la recorre cada mes.
DEL_EVENTUAL = {"terminado", "sin_visto_bueno", "en_facturacion", "cerrado"}


# ------------------------------------------------------------ T0 del mes

def test_el_mes_arranca_su_cierre_al_cerrar_su_ultimo_dia(cliente, sesion,
                                                          datos):
    """Cerrar los dias de en medio ya no abre plazo a nadie. Al cerrar el
    viernes 28 --el mes acaba en domingo-- arranca el cierre del mes:
    todos sus viaticos vencen en T0 + 24 h y el servicio no se mueve."""
    alta = _alta(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    jornadas = _jornadas(cliente, sesion, sid)
    assert sorted(jornadas) == DIAS, "el mes son sus cinco dias habiles"
    vids = [_viatico(cliente, sesion, datos, jornadas[d])
            for d in (DIAS[0], DIAS[3])]

    for dia in DIAS[:4]:
        _cerrar(cliente, sesion, jornadas[dia], dia)
    assert _limites(vids) == [None, None], \
        "el plazo del implantado ya no es del dia: es del mes"
    assert _cierre(contrato) is None

    _cerrar(cliente, sesion, jornadas[DIAS[4]], DIAS[4])
    t0 = _a_las_21(DIAS[4])
    c = _cierre(contrato)
    assert c["estatus"] == "abierto" and c["motivo"] == "termino"
    assert c["servicio_id"] == sid
    assert c["abierto_en"] == t0, "T0 es la firma del ultimo dia"
    assert c["comprobacion_hasta"] == t0 + H24
    assert c["limite"] == t0 + 2 * H24, "provisional: T1 todavia no llega"
    assert _limites(vids) == [t0 + H24] * 2, "todos vencen a la misma hora"
    assert _estatus(cliente, sesion, sid) not in DEL_EVENTUAL

    # Su panel y la cartera lo dicen.
    h = sesion("consultor")
    estado = cliente.get(f"/implantados/contratos/{contrato}/cierre/estado",
                         headers=h).json()
    assert estado["fase"] == "comprobacion" and estado["periodo"] == "09/2029"
    assert estado["viaticos_abiertos"] == 2
    panel = cliente.get(f"/implantados/{sid}/mes/2029/9", headers=h).json()
    assert panel["cierre"]["cierre_id"] == c["id"]
    ficha = next(x for x in cliente.get("/implantados", headers=h).json()
                 if x["servicio_id"] == sid)
    assert [p["fase"] for p in ficha["periodos"]] == ["comprobacion"]

    # Y el eventual no puede abrir el suyo: el implantado cierra por mes.
    r = cliente.post(f"/cierre/servicio/{sid}/abrir", headers=h)
    assert r.status_code == 409, r.text


def test_sin_dinero_afuera_el_consultor_arranca_y_la_factura_es_del_mes(
        cliente, sesion, datos, monkeypatch):
    """Sin viaticos no hay nada que esperar: T1 llega en cuanto corre el
    reloj. El visto bueno manda la factura del mes --aqui sin Odoo, queda
    por facturar con su mes--; finanzas aprueba el mes, el servicio sigue
    vivo y la comision del consultor es de ese mes: 1 por ciento."""
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    alta = _alta(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    _cerrar_mes(cliente, sesion, sid)
    t0 = _a_las_21(DIAS[4])
    c = _cierre(contrato)
    assert _avanzar(c["id"], t0 + timedelta(hours=1)) is True
    c = _cierre(contrato)
    assert c["estatus"] == "sin_visto_bueno"
    assert c["visto_bueno_desde"] == t0 + timedelta(hours=1)
    assert c["limite"] == t0 + timedelta(hours=25)
    assert _estatus(cliente, sesion, sid) not in DEL_EVENTUAL

    h = sesion("consultor")
    revision = cliente.get(f"/implantados/contratos/{contrato}/cierre/revision",
                           headers=h,
                           params={"ahora": (t0 + timedelta(hours=2)).isoformat()})
    assert revision.status_code == 200, revision.text
    assert revision.json()["listo_para_finanzas"] is True, revision.json()
    comparativo = revision.json()["comparativo"]
    assert comparativo["trabajado"]["dias_base"] == 5
    assert float(comparativo["trabajado"]["importe"]) == 5 * 2900 + 66000

    envio = cliente.post(f"/cierre/{c['id']}/enviar-finanzas", headers=h,
                         params={"ahora": (t0 + timedelta(hours=2)).isoformat()})
    assert envio.status_code == 200, envio.text
    assert envio.json()["periodo"] == "09/2029"
    assert envio.json()["dentro_de_plazo"] is True
    assert envio.json()["factura"]["resultado"] == "sin conexion"
    c = _cierre(contrato)
    assert c["estatus"] == "enviado_finanzas"
    assert c["total_ejecutado"] == 5 * 2900 + 66000
    assert c["total_cotizado"] == 5 * 2900 + 66000
    assert _estatus(cliente, sesion, sid) not in DEL_EVENTUAL

    bandeja = cliente.get("/cierre/por-facturar", headers=sesion("finanzas"))
    suyo = next(x for x in bandeja.json()["por_facturar"]
                if x["cierre_id"] == c["id"])
    assert suyo["periodo"] == "09/2029" and suyo["error"]

    # La factura del mes: renglon por renglon, con el folio y el mes.
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        cuerpo = facturacion.armar(db, db.get(m.Cierre, c["id"]))
    assert cuerpo["referencia"].endswith(" 09/2029")
    assert cuerpo["total"] == "80500.00"
    assert [(x["tipo"], x["cantidad"]) for x in cuerpo["conceptos"]] == \
        [("dias_base", 5), ("vehiculo_mes", 1)]

    r = cliente.post(f"/cierre/{c['id']}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    comision = r.json()["comision_consultor"]
    assert comision["porcentaje"] == 1.0
    assert float(comision["monto"]) == 805.0
    assert comision["estatus"] == "generada"
    assert _cierre(contrato)["estatus"] == "aprobado"
    assert _estatus(cliente, sesion, sid) not in DEL_EVENTUAL, \
        "aprobar un mes no cierra el implantado"


def test_con_dinero_afuera_el_mes_espera_a_su_personal(cliente, sesion, datos):
    """Con un viatico del mes sin cerrar, a las 23 h no pasa nada y el
    consultor no se puede adelantar; a las 24 abre el visto bueno, pero
    no se da con ese dinero abierto."""
    alta = _alta(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    jornadas = _jornadas(cliente, sesion, sid)
    _viatico(cliente, sesion, datos, jornadas[DIAS[2]])
    _cerrar_mes(cliente, sesion, sid)
    t0 = _a_las_21(DIAS[4])
    c = _cierre(contrato)
    h = sesion("consultor")

    assert _avanzar(c["id"], t0 + timedelta(hours=23)) is False
    envio = cliente.post(f"/cierre/{c['id']}/enviar-finanzas", headers=h,
                         params={"ahora": (t0 + timedelta(hours=23)).isoformat()})
    assert envio.status_code == 409, envio.text
    assert "comprobacion" in envio.json()["detail"]["mensaje"].lower()

    assert _avanzar(c["id"], t0 + H24) is True
    assert _cierre(contrato)["limite"] == t0 + 2 * H24
    envio = cliente.post(f"/cierre/{c['id']}/enviar-finanzas", headers=h,
                         params={"ahora": (t0 + H24 + timedelta(hours=1)).isoformat()})
    assert envio.status_code == 409, envio.text
    asuntos = [o["asunto"] for o in envio.json()["detail"]["observaciones"]]
    assert "Viaticos sin cerrar" in asuntos, asuntos


# ------------------------------------------------------------ un dia despues de T0

def test_el_sabado_que_entra_despues_de_t0_mueve_el_termino(cliente, sesion,
                                                           datos):
    """El cliente pide el sabado cuando el viernes ya cerro: el termino
    del mes se deshace y vuelve a arrancar al cerrar el sabado, que se
    cobra aparte. Con el visto bueno dado ya no entra otro dia."""
    alta = _alta(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    jornadas = _jornadas(cliente, sesion, sid)
    vid = _viatico(cliente, sesion, datos, jornadas[DIAS[0]])
    _cerrar_mes(cliente, sesion, sid)
    assert _cierre(contrato) is not None
    h = sesion("consultor")

    r = cliente.post(f"/implantados/contratos/{contrato}/dias-adicionales",
                     json={"fecha": str(SABADO)}, headers=h)
    assert r.status_code == 200, r.text
    assert _cierre(contrato) is None, "el mes volvio a tener un dia por trabajar"
    assert _limites([vid]) == [None], "el plazo se fue con el termino"

    _cerrar(cliente, sesion, _jornadas(cliente, sesion, sid)[SABADO], SABADO)
    c = _cierre(contrato)
    assert c["abierto_en"] == _a_las_21(SABADO), "T0 paso al sabado"
    assert _limites([vid]) == [_a_las_21(SABADO) + H24]

    # Ese dinero nunca salio: se cancela. Sin nada afuera el consultor da
    # el visto bueno, y el domingo ya no entra.
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        db.get(m.AsignacionViatico, vid).estatus = m.EstatusViatico.CANCELADO
        db.commit()
    ahora = (_a_las_21(SABADO) + timedelta(hours=1)).isoformat()
    envio = cliente.post(f"/cierre/{c['id']}/enviar-finanzas", headers=h,
                         params={"ahora": ahora})
    assert envio.status_code == 200, envio.text
    assert _cierre(contrato)["total_ejecutado"] == 5 * 2900 + 3500 + 66000
    r = cliente.post(f"/implantados/contratos/{contrato}/dias-adicionales",
                     json={"fecha": str(DOMINGO)}, headers=h)
    assert r.status_code == 409, r.text
    assert "visto bueno" in r.text


def test_reabrir_un_dia_deshace_el_termino_del_mes(cliente, sesion, datos,
                                                   monkeypatch):
    """Antes del visto bueno, reabrir un dia borra el cierre del mes y
    volver a cerrarlo lo arranca de nuevo; con el visto bueno dado, el
    dia ya no se reabre."""
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    alta = _alta(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    jornadas = _cerrar_mes(cliente, sesion, sid)
    hc = sesion("central")

    r = cliente.post(f"/operacion/jornadas/{jornadas[DIAS[2]]}/reabrir",
                     headers=hc, json={"justificacion": MOTIVO})
    assert r.status_code == 200, r.text
    assert _cierre(contrato) is None

    # Se vuelve a cerrar el sabado en la manana: T0 es esa firma, que
    # llega despues del termino del viernes.
    firma = datetime(2029, 9, 29, 10, 0)
    _cerrar(cliente, sesion, jornadas[DIAS[2]], DIAS[2], ahora=firma)
    c = _cierre(contrato)
    assert c is not None and c["abierto_en"] == firma

    ahora = firma + timedelta(hours=1)
    assert _avanzar(c["id"], ahora) is True
    envio = cliente.post(f"/cierre/{c['id']}/enviar-finanzas",
                         headers=sesion("consultor"),
                         params={"ahora": ahora.isoformat()})
    assert envio.status_code == 200, envio.text
    r = cliente.post(f"/operacion/jornadas/{jornadas[DIAS[2]]}/reabrir",
                     headers=hc, json={"justificacion": MOTIVO})
    assert r.status_code == 409, r.text
    assert "visto bueno" in r.text


def test_cancelar_los_ultimos_dias_completa_el_mes(cliente, sesion, datos):
    """El cliente ya no necesita el viernes: el consultor lo quita y el mes
    queda completo sin que otro dia lo cierre. El cierre arranca ahi, con
    el termino del jueves."""
    alta = _alta(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    _cerrar_mes(cliente, sesion, sid, dias=DIAS[:4])
    assert _cierre(contrato) is None

    r = cliente.delete(f"/implantados/{sid}/dia/{DIAS[4]}",
                       headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    c = _cierre(contrato)
    assert c is not None and c["motivo"] == "termino"
    assert c["abierto_en"].date() >= DIAS[3]


def test_la_red_de_cada_cinco_minutos_abre_el_mes_que_quedo_completo(
        cliente, sesion, datos):
    """Un mes que se completo por un camino que no dispara el cierre lo
    encuentra la tarea de cada cinco minutos, y no lo abre dos veces."""
    from app import cierre_mes
    from app import models as m
    from app.db import SessionLocal

    alta = _alta(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    with SessionLocal() as db:
        for j in (db.query(m.Jornada).join(m.Equipo)
                  .filter(m.Equipo.servicio_id == sid).all()):
            j.estatus = m.EstatusJornada.TERMINADA
            j.inicio_real, j.fin_real = j.inicio_programado, j.fin_programado
        db.commit()
    assert _cierre(contrato) is None

    ahora = datetime(2029, 10, 1, 9, 0)
    with SessionLocal() as db:
        abiertos = cierre_mes.abrir_los_que_terminaron(db, ahora)
    assert len(abiertos) == 1 and abiertos[0].endswith("09/2029")
    assert _cierre(contrato)["abierto_en"] == ahora, \
        "lo encontro despues: el plazo corre desde ahi"
    with SessionLocal() as db:
        assert cierre_mes.abrir_los_que_terminaron(db, ahora) == []


def test_dos_meses_en_fases_distintas(cliente, sesion, datos):
    """Septiembre cierra mientras octubre ya esta abierto: cada mes lleva
    su fase, y el dinero de octubre no detiene a septiembre."""
    from app import implantado as motor
    from app import models as m
    from app.db import SessionLocal

    alta = _alta(cliente, sesion, datos)
    sid, septiembre = alta["servicio_id"], alta["contrato_id"]
    with SessionLocal() as db:
        abierto = motor.abrir_siguiente(db, db.get(m.Servicio, sid),
                                        hoy=date(2029, 9, 27))
    octubre = abierto["contrato_id"]
    de_octubre = _jornadas(cliente, sesion, sid, 2029, 10)
    vid = _viatico(cliente, sesion, datos, de_octubre[date(2029, 10, 1)])

    _cerrar_mes(cliente, sesion, sid)
    c = _cierre(septiembre)
    assert c is not None and _cierre(octubre) is None
    assert _limites([vid]) == [None], "el viatico de octubre no es de septiembre"
    # Sin dinero en septiembre, su consultor arranca aunque octubre deba.
    assert _avanzar(c["id"], _a_las_21(DIAS[4]) + timedelta(hours=1)) is True

    h = sesion("consultor")
    ficha = next(x for x in cliente.get("/implantados", headers=h).json()
                 if x["servicio_id"] == sid)
    assert [(p["periodo"], p["fase"]) for p in ficha["periodos"]] == \
        [("09/2029", "sin_visto_bueno"), ("10/2029", None)]
    assert cliente.get(f"/implantados/{sid}/mes/2029/10",
                       headers=h).json()["cierre"]["existe"] is False


def test_cancelar_el_implantado_cierra_el_mes_con_lo_trabajado(cliente, sesion,
                                                              datos):
    """Se cancela con tres dias trabajados: el mes arranca su cierre por
    cancelacion y se factura con lo trabajado. El mes de despues, sin
    nada que cerrar, se queda sin relojes."""
    from app import implantado as motor
    from app import models as m
    from app.db import SessionLocal

    alta = _alta(cliente, sesion, datos)
    sid, septiembre = alta["servicio_id"], alta["contrato_id"]
    with SessionLocal() as db:
        octubre = motor.abrir_siguiente(db, db.get(m.Servicio, sid),
                                        hoy=date(2029, 9, 27))["contrato_id"]
    _cerrar_mes(cliente, sesion, sid, dias=DIAS[:3])

    r = cliente.post(f"/servicios/{sid}/cancelar", headers=sesion("consultor"),
                     json={"motivo": "El ejecutivo regreso a su pais"})
    assert r.status_code == 200, r.text
    c = _cierre(septiembre)
    assert c is not None and c["motivo"] == "cancelacion"
    assert _cierre(octubre) is None
    with SessionLocal() as db:
        from app import cierre_mes
        comparativo = cierre_mes.comparar(db, db.get(m.ContratoImplantado,
                                                     septiembre))
    assert comparativo["trabajado"]["dias_base"] == 3


def test_la_app_esconde_solo_el_mes_con_visto_bueno(cliente, sesion, datos):
    """La tarjeta de viaticos del implantado es del mes: se va con el
    visto bueno de su mes, no con el de otro."""
    from app import models as m
    from app.db import SessionLocal
    from app.routers.campo import _con_visto_bueno

    alta = _alta(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    _cerrar_mes(cliente, sesion, sid)
    with SessionLocal() as db:
        cierre = db.query(m.Cierre).filter_by(contrato_id=contrato).first()
        cierre.estatus = m.EstatusCierre.ENVIADO_FINANZAS
        db.commit()
        assert _con_visto_bueno(db, sid, date(2029, 9, 26)) is True
        assert _con_visto_bueno(db, sid, date(2029, 10, 3)) is False
        # Sin mes, es la pregunta del eventual: el implantado no tiene
        # cierre de servicio entero.
        assert _con_visto_bueno(db, sid) is False

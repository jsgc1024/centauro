# -*- coding: utf-8 -*-
"""Seccion 101 (grupo g5): la nomina, las comisiones y el bono.

Cuarta tanda de la revision del 28 de septiembre, hallazgos del revisor
a9: la comision retenida que se cancelaba por factura no cobrada, la
evaluacion autorizada que se recalculaba, el borrador de las 7:00 que
no cierra a las 11:00 por una tarifa, el corte vacio que el reloj dejaba
listo, el relevado al que se le cobraba el fin que marco el otro, las
entradas sin validar del dinero de configuracion y el permiso de ver el
corte de todos que traian el consultor y la central.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana, marcar,
                    marcar_fin)
from test_nominas import (_aprobado, _calcular, _comisiones, _con_visto_bueno,
                          _este_mes, _primero_del_siguiente, _reloj)

MX = ZoneInfo("America/Mexico_City")


def _lunes(dia=None):
    dia = dia or date.today()
    return dia - timedelta(days=dia.weekday())


def _en_mexico(dia, hora, minuto=0):
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=MX)


def _semana(cliente, sesion, datos, ahora):
    r = cliente.get("/nomina/semana", headers=sesion("finanzas"),
                    params={"pais_id": datos["mx"]["id"],
                            "ahora": ahora.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def _incidencia_grave_autorizada(cliente, sesion, servicio, persona):
    hoy = date.today()
    incidencia = cliente.post("/incidencias", json={
        "persona_id": persona, "fecha": str(hoy), "gravedad": "grave",
        "servicio_id": servicio["id"],
        "descripcion": "Abandono el punto con el ejecutivo a bordo"},
        headers=sesion("consultor")).json()
    r = cliente.post(f"/incidencias/{incidencia['incidencia_id']}/visto-bueno",
                     json={"autorizar": True,
                           "resolucion": "Confirmado por la central"},
                     headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text


# ============================================ 104 · la comision retenida

def test_una_comision_retenida_no_se_cancela_por_no_cobro(cliente, sesion,
                                                          datos):
    """Retenida por incidencia grave: nunca se pago. Cancelarla por
    factura no cobrada contesta 409 con que hacer, no deja ajuste, y
    direccion general la sigue pudiendo decidir."""
    from app import models as m
    from app.db import SessionLocal

    servicio, cierre_id = _con_visto_bueno(cliente, sesion, datos, 440)
    _incidencia_grave_autorizada(cliente, sesion, servicio,
                                 datos["personal"]["Juan Ramirez"]["id"])
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    comision = r.json()["comision_consultor"]
    assert comision["estatus"] == "retenida"

    r = cliente.post(f"/comisiones/{comision['comision_id']}/factura-no-cobrada",
                     json={"motivo": "Nota de credito del cliente"},
                     headers=sesion("finanzas"))
    assert r.status_code == 409, r.text
    assert "retenida" in r.json()["detail"]["mensaje"]
    assert "dirección general" in r.json()["detail"]["que_hacer"]
    with SessionLocal() as db:
        assert db.query(m.AjusteComision).count() == 0
        assert (db.get(m.ComisionConsultor, comision["comision_id"]).estatus
                == m.EstatusComision.RETENIDA)

    decision = cliente.post(f"/comisiones/{comision['comision_id']}/resolver",
                            json={"se_paga": True,
                                  "resolucion": "La incidencia no fue del consultor"},
                            headers=sesion("dirgeneral"))
    assert decision.status_code == 200, decision.text
    assert decision.json()["resultado"] == "generada"


def test_una_comision_perdida_no_se_cancela_por_no_cobro(cliente, sesion, datos):
    """Perdida: tampoco se pago. Antes dejaba un ajuste de cero y borraba
    el estatus de perdida."""
    from test_cierre import test_comision_perdida_si_se_cierra_fuera_de_plazo
    test_comision_perdida_si_se_cierra_fuera_de_plazo(cliente, sesion, datos)
    anio, mes = _este_mes()
    corte = _comisiones(cliente, sesion("finanzas"), datos, anio, mes)
    ana = next(c for c in corte["consultores"] if c["consultor"] == "Ana Solis")
    perdida = ana["no_se_paga"][0]
    assert perdida["estatus"] == "perdida"

    r = cliente.post(f"/comisiones/{perdida['comision_id']}/factura-no-cobrada",
                     json={"motivo": "Nota de credito del cliente"},
                     headers=sesion("finanzas"))
    assert r.status_code == 409, r.text
    assert "perdió" in r.json()["detail"]["mensaje"]
    corte = _comisiones(cliente, sesion("finanzas"), datos, anio, mes)
    ana = next(c for c in corte["consultores"] if c["consultor"] == "Ana Solis")
    assert ana["no_se_paga"][0]["estatus"] == "perdida"
    assert ana["diferencias"] == []


def test_la_factura_no_cobrada_deja_quien_y_el_mes_lo_pone_el_sistema(
        cliente, sesion, datos):
    """Sobre una comision que si se paga: el ajuste sale con quien lo
    registro y en el mes que sigue abierto hoy, no en el que mande el
    cliente. La segunda vez ya no se registra."""
    from app import models as m
    from app.db import SessionLocal

    _, comision = _aprobado(cliente, sesion, datos, 445)
    assert comision["estatus"] == "generada"
    anio, mes = _este_mes()
    siguiente = _primero_del_siguiente(anio, mes)
    # El reloj en el mes siguiente: ahi cae el descuento, aunque el
    # cliente no diga --ni pueda decir-- ningun mes.
    r = cliente.post(f"/comisiones/{comision['comision_id']}/factura-no-cobrada",
                     json={"motivo": "Nota de credito del cliente",
                           "anio": 2031, "mes": 1},
                     headers=sesion("finanzas"),
                     params={"ahora": _en_mexico(siguiente, 9, 0).isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["se_resta_en"] == f"{siguiente.month:02d}/{siguiente.year}"
    with SessionLocal() as db:
        ajuste = db.query(m.AjusteComision).one()
        assert (ajuste.anio, ajuste.mes) == (siguiente.year, siguiente.month)
        assert Decimal(str(ajuste.monto)) == -Decimal(str(comision["monto"]))
        quien = db.get(m.Persona, ajuste.creado_por_id)
        assert quien is not None and quien.nombre == "Jorge Diaz"

    corte = _comisiones(cliente, sesion("finanzas"), datos, siguiente.year,
                        siguiente.month)
    ana = next(c for c in corte["consultores"] if c["consultor"] == "Ana Solis")
    assert [(d["tipo"], d["quien"]) for d in ana["diferencias"]] \
        == [("no_cobrada", "Jorge Diaz")]

    r = cliente.post(f"/comisiones/{comision['comision_id']}/factura-no-cobrada",
                     json={"motivo": "Nota de credito del cliente"},
                     headers=sesion("finanzas"))
    assert r.status_code == 409, r.text
    # Y sin motivo no entra: es lo que lee el consultor en su corte.
    _, otra = _aprobado(cliente, sesion, datos, 446)
    r = cliente.post(f"/comisiones/{otra['comision_id']}/factura-no-cobrada",
                     json={"motivo": "x"}, headers=sesion("finanzas"))
    assert r.status_code == 400, r.text


# ======================================== 105 · la evaluacion autorizada

def test_una_evaluacion_autorizada_no_se_recalcula(cliente, sesion, datos):
    """RRHH autoriza el bono; volver a calcular a esa persona contesta
    409 con que hacer, y la evaluacion sigue autorizada, con su firma."""
    from test_bono_desempeno import _dia, _evaluacion_id, _evaluar
    from app import models as m
    from app.db import SessionLocal

    _, persona, _ = _dia(cliente, sesion, datos, dia_base=17)
    _evaluar(cliente, sesion, persona)
    evaluacion = _evaluacion_id(cliente, sesion, persona)
    r = cliente.post(f"/evaluaciones/{evaluacion}/autorizar",
                     headers=sesion("rrhh"))
    assert r.status_code == 200, r.text

    hoy = date.today()
    r = cliente.post("/evaluaciones",
                     json={"persona_id": persona, "anio": hoy.year,
                           "mes": hoy.month, "capacitacion_cumplida": False},
                     headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert "autorizada" in r.json()["detail"]["mensaje"]
    assert r.json()["detail"]["que_hacer"]
    with SessionLocal() as db:
        fila = db.get(m.EvaluacionMensual, evaluacion)
        assert fila.estatus == m.EstatusEvaluacion.AUTORIZADA
        assert fila.autorizada_por_id is not None
    # Y sigue en la bandeja del dia 5.
    corte = cliente.get(f"/corte/{datos['mx']['id']}/{hoy.year}/{hoy.month}",
                        headers=sesion("finanzas")).json()
    assert [p["evaluacion_id"] for p in corte["personas"]] == [evaluacion]


def test_la_capacitacion_dicha_a_mano_deja_rastro(cliente, sesion, datos):
    """El bool de capacitacion a mano decide dinero: queda en la bitacora
    de administracion con quien lo dijo, antes y despues. Sin el bool no
    se anota nada."""
    from test_bono_desempeno import _dia
    from app import bitacora_admin
    from app import models as m
    from app.db import SessionLocal

    _, persona, _ = _dia(cliente, sesion, datos, dia_base=18)
    hoy = date.today()
    r = cliente.post("/evaluaciones",
                     json={"persona_id": persona, "anio": hoy.year,
                           "mes": hoy.month}, headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.query(m.RegistroAdmin).filter_by(
            objeto="evaluacion_mensual").count() == 0

    r = cliente.post("/evaluaciones",
                     json={"persona_id": persona, "anio": hoy.year,
                           "mes": hoy.month, "capacitacion_cumplida": False},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        fila = (db.query(m.RegistroAdmin).filter_by(objeto="evaluacion_mensual")
                .one())
        assert fila.accion == "capacitacion del bono a mano"
        assert fila.despues == "false"
        assert fila.persona.nombre == "Ana Solis"
        assert "Luis Mendoza" in fila.detalle
        frase = bitacora_admin.que_cambio(fila, "es",
                                          bitacora_admin._Nombres(db, [fila]))
        assert "Luis Mendoza" in frase and frase.endswith("→ no")
        assert bitacora_admin.grupo_de("evaluacion_mensual") == "catalogos"


# ===================================== 106 · el borrador que no cierra

def test_un_borrador_que_no_sale_a_las_11_lo_dice_la_pantalla(
        cliente, sesion, datos):
    """El reloj armo el borrador a las 7:00; entre las 7:00 y las 11:00
    llega un dia de agente sin tarifa. A las 11:00 no cierra: la pestana
    lo dice, con la tabla de lo que falta, y no se marca pagado hasta que
    la tarifa este cargada y el corte se recalcule."""
    from app import models as m
    from app.db import SessionLocal

    lunes = _lunes() + timedelta(days=7)
    _con_visto_bueno(cliente, sesion, datos, 420)
    hechos = _reloj(_en_mexico(lunes, 7, 5))
    assert [x["resultado"] for x in hechos] == ["borrador"]
    nomina_id = hechos[0]["nomina_id"]

    f = sesion("finanzas")
    mx = datos["mx"]["id"]
    agente = datos["perfiles"]["agente_seguridad"]["id"]
    full_day = datos["modalidades"]["full_day"]["id"]
    with SessionLocal() as db:
        fila = (db.query(m.ComisionPersonal)
                .filter_by(pais_id=mx, tipo_servicio=m.TipoServicio.EVENTUAL,
                           perfil_id=agente, modalidad_id=full_day).first())
        guardado = (str(fila.monto), fila.monto_hora_extra) if fila else None
        if fila:
            db.delete(fila)
            db.commit()
    try:
        h = sesion("consultor")
        servicio = crear_servicio(
            cliente, h, datos,
            [jornada(manana(423), full_day)],
            consultor_id=datos["personal"]["Ana Solis"]["id"])
        cotizar_y_autorizar(cliente, h, servicio, agente,
                            datos["categorias"]["suv_blindada"]["id"])
        j = servicio["equipos"][0]["jornadas"][0]
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Luis Mendoza"]["id"],
                vehiculo_id=datos["suburban"]["id"], rol="agente_seguridad")
        configurar_origen(cliente, h, j["id"])
        ejecutar_jornada(cliente, sesion("luis"), j)
        cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                              headers=h).json()
        envio = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas",
                             headers=h)
        assert envio.status_code == 200, envio.text

        # Antes de las 11:00 el borrador ya avisa lo que le va a faltar.
        semana = _semana(cliente, sesion, datos, _en_mexico(lunes, 10, 30))
        assert semana["corte"]["estado"] == "borrador"
        assert semana["no_salio"] is False
        assert [x["persona"] for x in semana["corte"]["sin_tarifa"]] \
            == ["Luis Mendoza"]

        hechos = _reloj(_en_mexico(lunes, 11, 5))
        assert [x["resultado"] for x in hechos] == ["no_salio"]

        semana = _semana(cliente, sesion, datos, _en_mexico(lunes, 11, 30))
        assert semana["corte"]["nomina_id"] == nomina_id
        assert semana["corte"]["estado"] == "borrador", \
            "el borrador de las 7:00 sigue ahi, sin cerrar"
        assert semana["no_salio"] is True
        falta = semana["corte"]["sin_tarifa"]
        assert [(x["persona"], x["falta"]) for x in falta] \
            == [("Luis Mendoza", "tarifa")]
        assert falta[0]["fecha"] == j["fecha"]

        # El borrador de las 7:00 no se paga como si fuera el corte.
        r = cliente.post(f"/nomina/{nomina_id}/pagar", headers=f)
        assert r.status_code == 409, r.text
        assert "no cerró" in r.json()["detail"]["mensaje"]
        assert r.json()["detail"]["sin_tarifa"][0]["persona"] == "Luis Mendoza"

        # Con la tarifa cargada se recalcula, cierra y se paga.
        r = cliente.put("/nomina/tabulador", headers=f, json={
            "pais_id": mx, "tipo_servicio": "eventual",
            "renglones": [{"perfil_id": agente, "modalidad_id": full_day,
                           "monto": guardado[0] if guardado else "800",
                           "monto_hora_extra": (str(guardado[1])
                                                if guardado and guardado[1] is not None
                                                else None)}]})
        assert r.status_code == 200, r.text
        r = cliente.post("/nomina/calcular", headers=f,
                         json={"pais_id": mx, "fecha_corte": str(lunes)})
        assert r.status_code == 200, r.text
        assert r.json()["personas"] == 2
        semana = _semana(cliente, sesion, datos, _en_mexico(lunes, 11, 40))
        assert semana["no_salio"] is False
        assert semana["corte"]["sin_tarifa"] == []
        hechos = _reloj(_en_mexico(lunes, 11, 50))
        assert [x["resultado"] for x in hechos] == ["listo"]
        assert cliente.post(f"/nomina/{nomina_id}/pagar", headers=f).status_code == 200
    finally:
        with SessionLocal() as db:
            fila = (db.query(m.ComisionPersonal)
                    .filter_by(pais_id=mx, tipo_servicio=m.TipoServicio.EVENTUAL,
                               perfil_id=agente, modalidad_id=full_day).first())
            if guardado and not fila:
                db.add(m.ComisionPersonal(
                    pais_id=mx, tipo_servicio=m.TipoServicio.EVENTUAL,
                    perfil_id=agente, modalidad_id=full_day,
                    moneda=m.Moneda.MXN, monto=Decimal(guardado[0]),
                    monto_hora_extra=guardado[1]))
            elif not guardado and fila:
                db.delete(fila)
            db.commit()


def test_recalcular_dice_cual_tarifa_falta(cliente, sesion, datos):
    """El error de 'Recalcular' trae la tabla con nombre, dia y que falta
    --la tarifa del dia o solo la hora extra--, tambien en la vista
    previa de la pestana."""
    f = sesion("finanzas")
    mx = datos["mx"]["id"]
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    full_day = datos["modalidades"]["full_day"]["id"]
    r = cliente.put("/nomina/tabulador", headers=f, json={
        "pais_id": mx, "tipo_servicio": "eventual",
        "renglones": [{"perfil_id": conductor, "modalidad_id": full_day,
                       "monto": "700", "monto_hora_extra": None}]})
    assert r.status_code == 200, r.text
    try:
        _con_visto_bueno(cliente, sesion, datos, 425, horas_extra=2)
        r = cliente.post("/nomina/calcular", json={"pais_id": mx}, headers=f)
        assert r.status_code == 409, r.text
        faltan = r.json()["detail"]["sin_tarifa"]
        assert [(x["persona"], x["falta"]) for x in faltan] \
            == [("Juan Ramirez", "hora extra")]
        semana = cliente.get("/nomina/semana", headers=f,
                             params={"pais_id": mx}).json()
        previa = semana["proximo"]["sin_tarifa"]
        assert [(x["persona"], x["falta"]) for x in previa] \
            == [("Juan Ramirez", "hora extra")]
    finally:
        cliente.put("/nomina/tabulador", headers=f, json={
            "pais_id": mx, "tipo_servicio": "eventual",
            "renglones": [{"perfil_id": conductor, "modalidad_id": full_day,
                           "monto": "700", "monto_hora_extra": "90"}]})


# ================================================ 108 · el corte vacio

def test_un_borrador_viejo_no_deja_un_corte_vacio_listo(cliente, sesion, datos):
    """Un borrador de la semana pasada que nadie pago aparta el unico
    ajuste. El lunes siguiente el reloj ya no arma un corte sin
    renglones."""
    f = sesion("finanzas")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    mx = datos["mx"]["id"]
    r = cliente.post("/nomina/ajustes", headers=f, json={
        "persona_id": juan, "pais_id": mx, "monto": "300",
        "motivo": "Transfer que se quedo a deber"})
    assert r.status_code == 201, r.text

    lunes = _lunes() + timedelta(days=7)
    viejo = _calcular(cliente, sesion, datos, lunes)
    assert viejo["ajustes_aplicados"] == 1

    assert _reloj(_en_mexico(lunes + timedelta(days=7), 11, 5)) == []
    cortes = cliente.get(f"/nomina?pais_id={mx}", headers=f).json()
    assert [c["fecha_corte"] for c in cortes] == [lunes.isoformat()]


def test_el_borrador_que_se_queda_sin_renglones_no_se_deja_listo(
        cliente, sesion, datos):
    """A las 7:00 habia un dia que pagar; antes de las 11:00 se cancelo.
    El reloj no deja un corte vacio listo: lo quita y lo anota."""
    from app import models as m
    from app.db import SessionLocal

    servicio, _ = _con_visto_bueno(cliente, sesion, datos, 430)
    lunes = _lunes() + timedelta(days=7)
    hechos = _reloj(_en_mexico(lunes, 7, 5))
    assert [x["resultado"] for x in hechos] == ["borrador"]
    with SessionLocal() as db:
        j = (db.query(m.Jornada).join(m.Equipo)
             .filter(m.Equipo.servicio_id == servicio["id"]).one())
        j.estatus = m.EstatusJornada.CANCELADA
        db.commit()

    hechos = _reloj(_en_mexico(lunes, 11, 5))
    assert [x["resultado"] for x in hechos] == ["vacio"]
    cortes = cliente.get(f"/nomina?pais_id={datos['mx']['id']}",
                         headers=sesion("finanzas")).json()
    assert cortes == []
    assert _reloj(_en_mexico(lunes, 11, 20)) == []


# ============================================ 108 · el relevado y el fin

def _relevo(cliente, sesion, datos, con_contacto):
    """Juan toma el dia y marca su llegada --y el contacto, si le dio
    tiempo--; Luis lo releva y cierra el dia."""
    from test_bonos import _dia_de_este_mes
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(_dia_de_este_mes(), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    inicio = datetime.fromisoformat(j["inicio_programado"])
    marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
           inicio - timedelta(minutes=10))
    if con_contacto:
        marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo", inicio)
    r = cliente.post("/contingencia/reemplazos/personal", headers=h,
                     json={"desde_jornada_id": j["id"],
                           "sale_persona_id": juan, "entra_persona_id": luis,
                           "motivo": "Se sintio mal"})
    assert r.status_code == 200, r.text
    if not con_contacto:
        r = marcar(cliente, sesion("luis"), j["id"], "contacto_ejecutivo",
                   inicio + timedelta(hours=1))
        assert r.status_code in (200, 201), r.text
    fin = datetime.fromisoformat(j["fin_programado"])
    r = marcar_fin(cliente, sesion("luis"), j["id"], fin)
    assert r.status_code in (200, 201), r.text
    return juan


def _seguimiento_de(cliente, sesion, persona):
    hoy = date.today()
    ficha = cliente.post("/evaluaciones",
                         json={"persona_id": persona, "anio": hoy.year,
                               "mes": hoy.month, "capacitacion_cumplida": True},
                         headers=sesion("consultor")).json()
    return next(c for c in ficha["criterios"]
                if c["criterio"] == "No dejar callada a la central")


def test_al_relevado_no_se_le_cobra_el_fin_que_marco_el_otro(cliente, sesion,
                                                             datos):
    """El dia del relevo es de quien lo empezo y se le mide; el fin lo
    marca quien se quedo. Antes ese fin ajeno reprobaba su seguimiento."""
    juan = _relevo(cliente, sesion, datos, con_contacto=True)
    seguimiento = _seguimiento_de(cliente, sesion, juan)
    assert seguimiento["cumplido"], seguimiento["detalle"]
    assert seguimiento["detalle"].startswith("1 de 1")


def test_al_relevado_antes_del_contacto_solo_se_le_pide_la_llegada(
        cliente, sesion, datos):
    """Lo relevaron esperando al ejecutivo: el contacto lo marco quien
    entro. Se le exige solo lo que paso antes del relevo."""
    juan = _relevo(cliente, sesion, datos, con_contacto=False)
    seguimiento = _seguimiento_de(cliente, sesion, juan)
    assert seguimiento["cumplido"], seguimiento["detalle"]


# ==================================== 108 · las entradas sin validar

def _otro_pais(cliente, sesion, datos):
    paises = cliente.get("/catalogos/paises", headers=sesion("admin")).json()
    br = next(p for p in paises if p["codigo"] == "BR")
    modalidades = cliente.get("/catalogos/modalidades",
                              headers=sesion("admin")).json()
    de_br = next(x for x in modalidades if x["pais_id"] == br["id"])
    return br, de_br


def test_el_tabulador_no_acepta_negativos_ni_modalidades_de_otro_pais(
        cliente, sesion, datos):
    f = sesion("finanzas")
    mx = datos["mx"]["id"]
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    full_day = datos["modalidades"]["full_day"]["id"]
    _, de_br = _otro_pais(cliente, sesion, datos)

    def poner(renglon):
        return cliente.put("/nomina/tabulador", headers=f, json={
            "pais_id": mx, "tipo_servicio": "eventual", "renglones": [renglon]})

    assert poner({"perfil_id": conductor, "modalidad_id": full_day,
                  "monto": "-700"}).status_code == 422
    assert poner({"perfil_id": conductor, "modalidad_id": full_day,
                  "monto": "700", "monto_hora_extra": "-1"}).status_code == 422
    r = poner({"perfil_id": conductor, "modalidad_id": de_br["id"],
               "monto": "700"})
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["que_hacer"]
    assert poner({"perfil_id": 999999, "modalidad_id": full_day,
                  "monto": "700"}).status_code == 404
    assert poner({"perfil_id": conductor, "modalidad_id": 999999,
                  "monto": "700"}).status_code == 404
    # Lo que si es un dato entra igual que antes.
    assert poner({"perfil_id": conductor, "modalidad_id": full_day,
                  "monto": "700", "monto_hora_extra": "90"}).status_code == 200


def test_el_criterio_del_bono_y_los_pesos_tienen_rango(cliente, sesion, datos):
    """Umbral de 0 a 100, tolerancias sin negativos; una dimension que no
    existe es 422 y no error del servidor; la ventana es de un mes por lo
    menos."""
    do = sesion("diroperaciones")
    mx = datos["mx"]["id"]
    criterio = cliente.get(f"/criterios/{mx}", headers=do).json()["criterios"][0]
    base = {"monto_mensual": str(criterio["monto_mensual"]),
            "umbral_pct": str(criterio["umbral_pct"]),
            "tolerancia_minutos": criterio["tolerancia_minutos"],
            "tolerancia_ocasiones": criterio["tolerancia_ocasiones"],
            "reparte": criterio["reparte"], "activo": criterio["activo"]}
    for cambio in ({"umbral_pct": "150"}, {"umbral_pct": "-1"},
                   {"tolerancia_minutos": -5}, {"tolerancia_ocasiones": -1},
                   {"monto_mensual": "-100"}):
        r = cliente.put(f"/criterios/{criterio['id']}", headers=do,
                        json={**base, **cambio})
        assert r.status_code == 422, (cambio, r.text)
    r = cliente.put(f"/criterios/{criterio['id']}", headers=do, json=base)
    assert r.status_code == 200, r.text

    pesos = {"estrellas": 30, "satisfaccion": 20, "incidencias": 20,
             "capacitacion": 10, "experiencia": 10, "manejo": 10}
    cuerpo = {"pais_id": mx, "pesos": pesos}
    r = cliente.put("/profesionalismo/pesos", headers=sesion("admin"),
                    json={"pais_id": mx, "pesos": {**pesos, "inventada": 0}})
    assert r.status_code == 422, r.text
    r = cliente.put("/profesionalismo/pesos", headers=sesion("admin"),
                    json={"pais_id": mx, "pesos": {**pesos, "estrellas": -10,
                                                   "manejo": 50}})
    assert r.status_code == 422, r.text
    for cambio in ({"meses_ventana": 0}, {"horas_referencia": 0},
                   {"castigo_leve": "-5"}, {"puntos_por_evento_manejo": "-1"}):
        r = cliente.put("/profesionalismo/pesos", headers=sesion("admin"),
                        json={**cuerpo, **cambio})
        assert r.status_code == 422, (cambio, r.text)
    r = cliente.put("/profesionalismo/pesos", headers=sesion("admin"),
                    json={**cuerpo, "meses_ventana": 3})
    assert r.status_code == 200, r.text


def test_el_festivo_tiene_piso_y_los_ajustes_tope(cliente, sesion, datos):
    """Un factor de cero pagaba el festivo a cero; un motivo de 401 letras
    reventaba en la base; un ajuste de otro pais nunca entraba a un corte
    de la persona; un servicio o un dia que no existen se dicen."""
    admin = sesion("admin")
    f = sesion("finanzas")
    mx = datos["mx"]["id"]
    br, _ = _otro_pais(cliente, sesion, datos)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    ana = datos["personal"]["Ana Solis"]["id"]

    festivo = {"pais_id": mx, "fecha": "2031-01-01", "nombre": "Prueba"}
    assert cliente.post("/catalogos/dias-festivos", headers=admin,
                        json={**festivo, "factor_comision": 0}).status_code == 422
    assert cliente.post("/catalogos/dias-festivos", headers=admin,
                        json={**festivo, "factor_comision": -2}).status_code == 422

    ajuste = {"persona_id": juan, "pais_id": mx, "monto": "300",
              "motivo": "Transfer que se quedo a deber"}
    assert cliente.post("/nomina/ajustes", headers=f, json={
        **ajuste, "motivo": "x" * 401}).status_code == 422
    assert cliente.post("/nomina/ajustes", headers=f, json={
        **ajuste, "monto": "10000000"}).status_code == 422
    r = cliente.post("/nomina/ajustes", headers=f, json={
        **ajuste, "pais_id": br["id"]})
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["que_hacer"]
    assert cliente.post("/nomina/ajustes", headers=f, json={
        **ajuste, "servicio_id": 999999}).status_code == 404
    assert cliente.post("/nomina/ajustes", headers=f, json={
        **ajuste, "jornada_id": 999999}).status_code == 404
    assert cliente.post("/nomina/ajustes", headers=f, json=ajuste).status_code == 201

    diferencia = {"pais_id": mx, "consultor_id": ana, "monto": "-100",
                  "motivo": "Nota de credito de julio"}
    assert cliente.post("/nomina/comisiones/diferencias", headers=f, json={
        **diferencia, "monto": "-10000000"}).status_code == 422
    r = cliente.post("/nomina/comisiones/diferencias", headers=f, json={
        **diferencia, "pais_id": br["id"]})
    assert r.status_code == 400, r.text
    assert cliente.post("/nomina/comisiones/diferencias", headers=f, json={
        **diferencia, "servicio_id": 999999}).status_code == 404
    assert cliente.post("/nomina/comisiones/diferencias", headers=f,
                        json=diferencia).status_code == 201


def test_el_anio_el_mes_y_la_incidencia_se_validan(cliente, sesion, datos):
    """Un ano de dos cifras o un mes 13 son 422, no error del servidor; la
    incidencia sobre un servicio o un dia que no existen contesta 404."""
    f = sesion("finanzas")
    mx = datos["mx"]["id"]
    hoy = date.today()
    r = cliente.get("/nomina/comisiones", headers=f,
                    params={"pais_id": mx, "anio": 99, "mes": 1})
    assert r.status_code == 422, r.text
    r = cliente.get("/nomina/comisiones", headers=f,
                    params={"pais_id": mx, "anio": hoy.year, "mes": 13})
    assert r.status_code == 422, r.text
    r = cliente.post("/nomina/comisiones/visto-bueno", headers=sesion("diroperaciones"),
                     json={"pais_id": mx, "anio": 99, "mes": 1})
    assert r.status_code == 422, r.text
    luis = datos["personal"]["Luis Mendoza"]["id"]
    r = cliente.post("/evaluaciones", headers=sesion("consultor"),
                     json={"persona_id": luis, "anio": hoy.year, "mes": 13})
    assert r.status_code == 422, r.text
    r = cliente.post("/evaluaciones", headers=sesion("consultor"),
                     json={"persona_id": luis, "anio": 99, "mes": 1})
    assert r.status_code == 422, r.text

    incidencia = {"persona_id": luis, "fecha": str(hoy), "gravedad": "leve",
                  "descripcion": "Queja del ejecutivo por el trato en el aeropuerto"}
    assert cliente.post("/incidencias", headers=sesion("consultor"), json={
        **incidencia, "servicio_id": 999999}).status_code == 404
    assert cliente.post("/incidencias", headers=sesion("consultor"), json={
        **incidencia, "jornada_id": 999999}).status_code == 404
    assert cliente.post("/incidencias", headers=sesion("consultor"), json={
        **incidencia, "descripcion": "x" * 601}).status_code == 422
    assert cliente.post("/incidencias", headers=sesion("consultor"),
                        json=incidencia).status_code == 201


# ============================================ 108 · ver el corte de todos

def test_el_consultor_y_la_central_ya_no_leen_el_corte_de_todos(cliente, sesion,
                                                                 datos):
    """`nomina.ver` es el corte de todos --el tabulador, cada recibo, los
    ajustes-- y lo traian el consultor y la central sin que la pantalla
    se los ensenara. Lo suyo, su comision, sigue por `comisiones.ver`."""
    from app import permisos
    from app import models as m

    assert not ({m.Rol.CONSULTOR, m.Rol.CENTRAL}
                & permisos.roles_de("nomina.ver"))
    mx = datos["mx"]["id"]
    _con_visto_bueno(cliente, sesion, datos, 450)
    n = _calcular(cliente, sesion, datos)
    rutas = (f"/nomina/tabulador?pais_id={mx}", f"/nomina/semana?pais_id={mx}",
             f"/nomina/implantados?pais_id={mx}", f"/nomina?pais_id={mx}",
             f"/nomina/{n['nomina_id']}", f"/nomina/ajustes/pendientes?pais_id={mx}")
    for quien in ("consultor", "central"):
        for ruta in rutas:
            r = cliente.get(ruta, headers=sesion(quien))
            assert r.status_code == 403, (quien, ruta, r.text)
    for quien in ("finanzas", "diroperaciones", "dirgeneral"):
        for ruta in rutas:
            r = cliente.get(ruta, headers=sesion(quien))
            assert r.status_code == 200, (quien, ruta, r.text)

    anio, mes = _este_mes()
    suyo = _comisiones(cliente, sesion("consultor"), datos, anio, mes)
    assert suyo["solo_el_suyo"] is True
    r = cliente.get("/nomina/comisiones", headers=sesion("central"),
                    params={"pais_id": mx, "anio": anio, "mes": mes})
    assert r.status_code == 403

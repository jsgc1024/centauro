# -*- coding: utf-8 -*-
"""Nominas (seccion 66): el corte del lunes del personal y el corte del
mes de las comisiones de los consultores.

Decisiones de Salvador, 25 de septiembre:

* El corte del personal se arma solo el lunes a las 7:00, a las 11:00
  se recalcula por ultima vez y queda listo para pagar; lo que llegue
  despues pasa al lunes siguiente. Finanzas paga a mediodia.
* Nadie cobra en negativo: quien queda debajo de cero cobra cero y lo
  que falta pasa a su siguiente corte, hasta saldarse. Lo mismo la
  comision del consultor, al mes siguiente.
* El implantado se paga cada semana; con el visto bueno del mes la
  diferencia se paga o se descuenta el lunes siguiente y el mes queda
  cerrado.
* La comision se paga con un corte mensual: entra lo que finanzas
  valido en el mes; direccion de operaciones le da el visto bueno con
  el mes terminado y finanzas registra cada pago con su referencia.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana)

MX = ZoneInfo("America/Mexico_City")


def _lunes(dia=None):
    dia = dia or date.today()
    return dia - timedelta(days=dia.weekday())


def _en_mexico(dia, hora, minuto=0):
    """Un instante con zona: el reloj del lunes lo lee en hora de cada
    pais."""
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=MX)


def _ejecutado(cliente, sesion, datos, offset, quien="Juan Ramirez",
               cuenta="juan", horas_extra=0):
    """Un eventual de un dia, cotizado, asignado y trabajado."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=datos["personal"][quien]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion(cuenta), j, horas_extra=horas_extra)
    return servicio


def _con_visto_bueno(cliente, sesion, datos, offset, **kw):
    """Trabajado y con el visto bueno de la consultora: entra al corte."""
    servicio = _ejecutado(cliente, sesion, datos, offset, **kw)
    h = sesion("consultor")
    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                          headers=h).json()
    envio = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas",
                         headers=h)
    assert envio.status_code == 200, envio.text
    return servicio, cierre["cierre_id"]


def _aprobado(cliente, sesion, datos, offset, **kw):
    """Con visto bueno y validado por finanzas: ya tiene comision."""
    servicio, cierre_id = _con_visto_bueno(cliente, sesion, datos, offset, **kw)
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    return servicio, r.json()["comision_consultor"]


def _calcular(cliente, sesion, datos, corte=None):
    cuerpo = {"pais_id": datos["mx"]["id"]}
    if corte:
        cuerpo["fecha_corte"] = str(corte)
    r = cliente.post("/nomina/calcular", json=cuerpo, headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    return r.json()


def _ver(cliente, sesion, nomina_id):
    r = cliente.get(f"/nomina/{nomina_id}", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    return r.json()


def _de(corte, persona):
    return next(p for p in corte["por_persona"] if p["persona"] == persona)


def _tabla_del_implantado(cliente, sesion, datos):
    """La tabla de implantado como la trae la siembra: 700 el dia y 90 la
    hora extra. Los catalogos no se vacian entre pruebas y otra prueba la
    cambia; esta la deja como la necesita."""
    r = cliente.put("/nomina/tabulador", headers=sesion("finanzas"), json={
        "pais_id": datos["mx"]["id"], "tipo_servicio": "implantado",
        "renglones": [{
            "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"],
            "modalidad_id": datos["modalidades"]["full_day"]["id"],
            "monto": "700", "monto_hora_extra": "90"}]})
    assert r.status_code == 200, r.text


def _reloj(ahora):
    from app import nomina
    from app.db import SessionLocal
    with SessionLocal() as db:
        return nomina.reloj_del_lunes(db, ahora)


# ---------------------------------------------------------------- personal

def test_nadie_cobra_en_negativo_y_el_saldo_pasa_al_siguiente(cliente, sesion,
                                                              datos):
    """Un descuento mas grande que la semana: la persona queda en cero y
    lo que falta se le descuenta el lunes siguiente, de lo que gane."""
    f = sesion("finanzas")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    r = cliente.post("/nomina/ajustes", headers=f, json={
        "persona_id": juan, "pais_id": datos["mx"]["id"], "monto": "-500",
        "motivo": "Uniforme que no regreso"})
    assert r.status_code == 201, r.text

    este = _lunes()
    primero = _calcular(cliente, sesion, datos, este)
    assert primero["en_contra"] == 1
    corte = _ver(cliente, sesion, primero["nomina_id"])
    suyo = _de(corte, "Juan Ramirez")
    assert Decimal(str(suyo["total"])) == 0
    assert Decimal(str(suyo["en_contra"])) == Decimal("500")
    saldo = [c for c in suyo["conceptos"] if c["saldo_en_contra"]]
    assert len(saldo) == 1 and Decimal(str(saldo[0]["monto"])) == 500
    assert [p["persona"] for p in corte["pasan"]] == ["Juan Ramirez"]
    assert Decimal(str(corte["total"])) == 0
    # El renglon del saldo no es un dia de nadie: no sale en el rol.
    assert corte["dias_pagados"] == 0 and corte["por_rol"] == []

    pago = cliente.post(f"/nomina/{primero['nomina_id']}/pagar", headers=f)
    assert pago.status_code == 200, pago.text
    assert pago.json()["saldos_en_contra"] == 1

    pendientes = cliente.get(
        f"/nomina/ajustes/pendientes?pais_id={datos['mx']['id']}",
        headers=f).json()
    assert [(a["concepto"], Decimal(str(a["monto"]))) for a in pendientes] \
        == [("saldo_en_contra", Decimal("-500"))]

    # La semana que sigue trabaja un dia: se le descuenta de ahi.
    _con_visto_bueno(cliente, sesion, datos, 301)
    segundo = _calcular(cliente, sesion, datos, este + timedelta(days=7))
    assert segundo["en_contra"] == 0
    suyo = _de(_ver(cliente, sesion, segundo["nomina_id"]), "Juan Ramirez")
    dia = next(c for c in suyo["conceptos"] if not c["es_ajuste"])
    assert Decimal(str(suyo["total"])) == Decimal(str(dia["monto"])) - 500
    assert Decimal(str(suyo["total"])) > 0


def test_el_reloj_arma_el_borrador_a_las_7_y_lo_cierra_a_las_11(cliente,
                                                                 sesion, datos):
    _con_visto_bueno(cliente, sesion, datos, 310)
    lunes = _lunes() + timedelta(days=7)

    assert _reloj(_en_mexico(lunes, 6, 50)) == []
    hechos = _reloj(_en_mexico(lunes, 7, 5))
    assert [h["resultado"] for h in hechos] == ["borrador"], \
        "solo Mexico tiene algo que pagar; Brasil no arma un corte vacio"
    nomina_id = hechos[0]["nomina_id"]
    corte = _ver(cliente, sesion, nomina_id)
    assert corte["estado"] == "borrador" and corte["calculada_por"] is None
    assert corte["fecha_corte"] == lunes.isoformat()

    # Entre las 7:00 y las 11:00 el reloj no lo toca; finanzas si.
    assert _reloj(_en_mexico(lunes, 9, 30)) == []
    r = cliente.post("/nomina/calcular", headers=sesion("finanzas"),
                     json={"pais_id": datos["mx"]["id"],
                           "fecha_corte": str(lunes)})
    assert r.status_code == 200, r.text
    assert _ver(cliente, sesion, nomina_id)["calculada_por"] == "Jorge Diaz"

    hechos = _reloj(_en_mexico(lunes, 11, 5))
    assert [h["resultado"] for h in hechos] == ["listo"]
    corte = _ver(cliente, sesion, nomina_id)
    assert corte["estado"] == "listo"
    assert corte["lista_en"].startswith(f"{lunes.isoformat()}T11:05")

    # Listo, ya no se recalcula.
    r = cliente.post("/nomina/calcular", headers=sesion("finanzas"),
                     json={"pais_id": datos["mx"]["id"],
                           "fecha_corte": str(lunes)})
    assert r.status_code == 409, r.text
    assert "11:00" in r.json()["detail"]["mensaje"]
    # Ni tirarlo: el reloj lo volveria a armar con lo que llego despues.
    r = cliente.delete(f"/nomina/{nomina_id}", headers=sesion("finanzas"))
    assert r.status_code == 409, r.text
    assert _reloj(_en_mexico(lunes, 11, 20)) == []
    # El martes ya no es lunes.
    assert _reloj(_en_mexico(lunes + timedelta(days=1), 7, 5)) == []


def test_lo_que_llega_despues_de_las_11_espera_al_lunes_siguiente(cliente,
                                                                   sesion, datos):
    primero, _ = _con_visto_bueno(cliente, sesion, datos, 320)
    lunes = _lunes() + timedelta(days=7)
    hechos = _reloj(_en_mexico(lunes, 11, 1))
    assert [h["resultado"] for h in hechos] == ["listo"]
    nomina_id = hechos[0]["nomina_id"]

    tarde, _ = _con_visto_bueno(cliente, sesion, datos, 322, quien="Luis Mendoza",
                                cuenta="luis")
    f = sesion("finanzas")
    semana = cliente.get("/nomina/semana", headers=f, params={
        "pais_id": datos["mx"]["id"],
        "ahora": _en_mexico(lunes, 11, 30).isoformat()}).json()
    folios = [g["folio"] for g in semana["corte"]["por_origen"]]
    assert folios == [primero["folio"]], "el que llego tarde no entra"
    assert semana["corte"]["estado"] == "listo"

    assert cliente.post(f"/nomina/{nomina_id}/pagar", headers=f).status_code == 200
    semana = cliente.get("/nomina/semana", headers=f, params={
        "pais_id": datos["mx"]["id"],
        "ahora": _en_mexico(lunes, 12, 30).isoformat()}).json()
    assert semana["corte"] is None
    assert semana["proximo"]["fecha_corte"] == \
        (lunes + timedelta(days=7)).isoformat()
    assert [g["folio"] for g in semana["proximo"]["por_origen"]] == \
        [tarde["folio"]]
    assert semana["ultimo_pagado"]["nomina_id"] == nomina_id


def test_sin_corte_a_las_11_lo_que_llega_ya_es_del_lunes_siguiente(
        cliente, sesion, datos):
    """Un lunes sin nada que pagar el reloj no arma nada. Lo que llega en
    la tarde ya no es de ese lunes: la pantalla lo pone en el siguiente,
    sin decir que el corte no salio."""
    lunes = _lunes() + timedelta(days=7)
    assert _reloj(_en_mexico(lunes, 11, 5)) == []
    tarde, _ = _con_visto_bueno(cliente, sesion, datos, 340)
    f = sesion("finanzas")

    def ver(hora, minuto):
        return cliente.get("/nomina/semana", headers=f, params={
            "pais_id": datos["mx"]["id"],
            "ahora": _en_mexico(lunes, hora, minuto).isoformat()}).json()

    semana = ver(11, 30)
    assert semana["corte"] is None and semana["no_salio"] is False
    assert semana["proximo"]["fecha_corte"] == \
        (lunes + timedelta(days=7)).isoformat()
    assert [g["folio"] for g in semana["proximo"]["por_origen"]] == \
        [tarde["folio"]]

    # Antes de las 11:00 si era de ese lunes, y el reloj ya debio armarlo.
    semana = ver(10, 30)
    assert semana["proximo"]["fecha_corte"] == lunes.isoformat()
    assert semana["no_salio"] is True


def test_la_semana_dice_por_que_entra_y_que_le_falta_al_que_no(cliente, sesion,
                                                                datos):
    entra, _ = _con_visto_bueno(cliente, sesion, datos, 330, horas_extra=2)
    espera = _ejecutado(cliente, sesion, datos, 333, quien="Luis Mendoza",
                        cuenta="luis")
    _calcular(cliente, sesion, datos)

    semana = cliente.get("/nomina/semana", headers=sesion("finanzas"),
                         params={"pais_id": datos["mx"]["id"]}).json()
    corte = semana["corte"] or semana["proximo"]
    grupo = next(g for g in corte["por_origen"] if g["folio"] == entra["folio"])
    assert grupo["origen"] == "eventual"
    assert grupo["por_que"]["clave"] == "visto_bueno"
    assert grupo["por_que"]["consultor"] == "Ana Solis"
    assert grupo["horas_extra"] == 2 and Decimal(str(grupo["monto_horas_extra"])) > 0
    assert Decimal(str(corte["resumen"]["eventual"])) == \
        Decimal(str(grupo["monto"]))

    falta = next(x for x in semana["todavia_no"] if x["folio"] == espera["folio"])
    assert falta["que_falta"]["clave"] in ("comprobacion", "visto_bueno")
    assert falta["consultor"] == "Ana Solis"
    assert Decimal(str(falta["monto"])) > 0 and falta["personas"] == 1
    assert all(x["folio"] != entra["folio"] for x in semana["todavia_no"])


def test_el_mes_del_implantado_se_cierra_cuando_se_paga_su_diferencia(
        cliente, sesion, datos, monkeypatch):
    """Se pagan los dias; la consultora corrige dos horas extra y da el
    visto bueno del mes: la diferencia entra al lunes siguiente y, pagada,
    el mes queda cerrado."""
    from app import facturacion
    from test_cierre_mes import (DIAS, _a_las_21, _alta, _avanzar, _cierre,
                                 _cerrar_mes)
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")
    _tabla_del_implantado(cliente, sesion, datos)

    alta = _alta(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    jornadas = _cerrar_mes(cliente, sesion, sid)
    f = sesion("finanzas")

    semana1 = _calcular(cliente, sesion, datos, date(2029, 9, 24))
    assert cliente.post(f"/nomina/{semana1['nomina_id']}/pagar",
                        headers=f).status_code == 200

    # Dos horas extra el lunes 24, corregidas por la consultora.
    lunes = jornadas[DIAS[0]]
    dia = cliente.get(f"/operacion/jornadas/{lunes}/dia",
                      headers=sesion("consultor")).json()["horas"]
    fin = datetime.fromisoformat(dia["fin_programado"]) + timedelta(hours=2)
    r = cliente.post(f"/operacion/jornadas/{lunes}/horas",
                     headers=sesion("consultor"),
                     params={"ahora": _a_las_21(DIAS[4]).isoformat()},
                     json={"fin": fin.isoformat(),
                           "justificacion": "El cliente pidio quedarse dos horas"})
    assert r.status_code == 200, r.text

    ahora = {"ahora": "2029-10-02T10:00:00"}
    meses = cliente.get("/nomina/implantados", headers=f, params={
        "pais_id": datos["mx"]["id"], **ahora}).json()["meses"]
    septiembre = next(x for x in meses if x["contrato_id"] == contrato)
    assert septiembre["estado"] == "sin_visto_bueno"
    assert septiembre["diferencia"] is None

    t0 = _a_las_21(DIAS[4])
    c = _cierre(contrato)
    assert _avanzar(c["id"], t0 + timedelta(hours=1)) is True
    envio = cliente.post(f"/cierre/{c['id']}/enviar-finanzas",
                         headers=sesion("consultor"),
                         params={"ahora": (t0 + timedelta(hours=2)).isoformat()})
    assert envio.status_code == 200, envio.text
    assert len(envio.json()["ajustes_de_nomina"]) == 1

    meses = cliente.get("/nomina/implantados", headers=f, params={
        "pais_id": datos["mx"]["id"], **ahora}).json()["meses"]
    septiembre = next(x for x in meses if x["contrato_id"] == contrato)
    assert septiembre["estado"] == "por_cerrar"
    pagado = Decimal(str(septiembre["pagado"]))
    diferencia = Decimal(str(septiembre["diferencia"]))
    assert diferencia > 0
    assert Decimal(str(septiembre["corresponde"])) == pagado + diferencia
    assert septiembre["semanas_pagadas"] == 1
    assert [d["persona"] for d in septiembre["diferencias"]] == ["Juan Ramirez"]

    semana2 = _calcular(cliente, sesion, datos, date(2029, 10, 1))
    corte = _ver(cliente, sesion, semana2["nomina_id"])
    grupo = next(g for g in corte["por_origen"] if g["origen"] == "mes")
    assert (grupo["anio"], grupo["mes"]) == (2029, 9)
    assert grupo["por_que"]["consultor"] == "Ana Solis"
    assert Decimal(str(grupo["monto"])) == diferencia
    assert cliente.post(f"/nomina/{semana2['nomina_id']}/pagar",
                        headers=f).status_code == 200

    meses = cliente.get("/nomina/implantados", headers=f, params={
        "pais_id": datos["mx"]["id"], **ahora}).json()["meses"]
    septiembre = next(x for x in meses if x["contrato_id"] == contrato)
    assert septiembre["estado"] == "cerrado"
    assert septiembre["cerrado_en"]
    assert all(d["pagada"] for d in septiembre["diferencias"])


def test_el_dia_pagado_que_se_cancela_sale_en_su_mes_y_nadie_queda_en_negativo(
        cliente, sesion, datos, monkeypatch):
    """Tres dias del implantado que ya se pagaron y despues se cancelan: su
    diferencia sale en el corte general del mes --lo pagado los cuenta--
    y, como se come la semana de Juan, lo que falta pasa al lunes que
    sigue."""
    from app import facturacion
    from app import models as m
    from app.db import SessionLocal
    from test_cierre_mes import (DIAS, _a_las_21, _alta, _avanzar, _cierre,
                                 _cerrar_mes)
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")
    _tabla_del_implantado(cliente, sesion, datos)

    alta = _alta(cliente, sesion, datos)
    sid, contrato = alta["servicio_id"], alta["contrato_id"]
    jornadas = _cerrar_mes(cliente, sesion, sid)
    f = sesion("finanzas")
    semana1 = _calcular(cliente, sesion, datos, date(2029, 9, 24))
    assert cliente.post(f"/nomina/{semana1['nomina_id']}/pagar",
                        headers=f).status_code == 200

    with SessionLocal() as db:
        for dia in DIAS[2:]:
            db.get(m.Jornada, jornadas[dia]).estatus = m.EstatusJornada.CANCELADA
        db.commit()
    t0 = _a_las_21(DIAS[4])
    c = _cierre(contrato)
    assert _avanzar(c["id"], t0 + timedelta(hours=1)) is True
    envio = cliente.post(f"/cierre/{c['id']}/enviar-finanzas",
                         headers=sesion("consultor"),
                         params={"ahora": (t0 + timedelta(hours=2)).isoformat()})
    assert envio.status_code == 200, envio.text
    assert len(envio.json()["ajustes_de_nomina"]) == 3

    meses = cliente.get("/nomina/implantados", headers=f, params={
        "pais_id": datos["mx"]["id"],
        "ahora": "2029-10-02T10:00:00"}).json()["meses"]
    septiembre = next(x for x in meses if x["contrato_id"] == contrato)
    assert septiembre["estado"] == "por_cerrar"
    pagado = Decimal(str(septiembre["pagado"]))
    diferencia = Decimal(str(septiembre["diferencia"]))
    assert diferencia < 0 and len(septiembre["diferencias"]) == 3
    assert Decimal(str(septiembre["corresponde"])) == pagado + diferencia
    assert pagado + diferencia == pagado * 2 / 5

    semana2 = _calcular(cliente, sesion, datos, date(2029, 10, 1))
    assert semana2["en_contra"] == 1
    juan = _de(_ver(cliente, sesion, semana2["nomina_id"]), "Juan Ramirez")
    assert Decimal(str(juan["total"])) == 0
    assert Decimal(str(juan["en_contra"])) == -diferencia


def test_pagar_el_corte_es_de_quien_paga(cliente, sesion, datos):
    _con_visto_bueno(cliente, sesion, datos, 340)
    n = _calcular(cliente, sesion, datos)
    r = cliente.post(f"/nomina/{n['nomina_id']}/pagar",
                     headers=sesion("consultor"))
    assert r.status_code == 403


# ---------------------------------------------------------------- comisiones

def _comisiones(cliente, headers, datos, anio, mes, **params):
    r = cliente.get("/nomina/comisiones", headers=headers, params={
        "pais_id": datos["mx"]["id"], "anio": anio, "mes": mes, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _este_mes():
    hoy = date.today()
    return hoy.year, hoy.month


def _primero_del_siguiente(anio, mes):
    return (date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1))


def _visto_bueno(cliente, headers, datos, anio, mes, ahora=None):
    params = {"ahora": ahora.isoformat()} if ahora else {}
    return cliente.post("/nomina/comisiones/visto-bueno", headers=headers,
                        params=params, json={"pais_id": datos["mx"]["id"],
                                             "anio": anio, "mes": mes})


def test_el_corte_de_comisiones_junta_lo_que_finanzas_valido(cliente, sesion,
                                                              datos):
    servicio, comision = _aprobado(cliente, sesion, datos, 350)
    anio, mes = _este_mes()
    corte = _comisiones(cliente, sesion("finanzas"), datos, anio, mes)
    assert corte["estado"] == "abierto" and corte["se_puede_autorizar"] is False
    ana = next(c for c in corte["consultores"] if c["consultor"] == "Ana Solis")
    assert [r["folio"] for r in ana["se_paga"]] == [servicio["folio"]]
    renglon = ana["se_paga"][0]
    assert renglon["porcentaje"] == 3.0
    assert Decimal(str(renglon["monto"])) == Decimal(str(comision["monto"]))
    assert Decimal(str(ana["totales"]["a_pagar"])) == \
        Decimal(str(comision["monto"]))
    assert ana["estado"] == "abierto"

    # La consultora ve el suyo; su companera no ve nada ajeno.
    suyo = _comisiones(cliente, sesion("consultor"), datos, anio, mes)
    assert suyo["solo_el_suyo"] is True
    assert [c["consultor"] for c in suyo["consultores"]] == ["Ana Solis"]
    ajeno = _comisiones(cliente, sesion("consultor2"), datos, anio, mes)
    assert ajeno["consultores"] == []


def test_el_visto_bueno_es_de_operaciones_y_el_pago_de_finanzas(cliente, sesion,
                                                                 datos):
    servicio, comision = _aprobado(cliente, sesion, datos, 355)
    anio, mes = _este_mes()
    despues = _en_mexico(_primero_del_siguiente(anio, mes), 9, 0)

    assert _visto_bueno(cliente, sesion("consultor"), datos, anio, mes,
                        despues).status_code == 403
    assert _visto_bueno(cliente, sesion("finanzas"), datos, anio, mes,
                        despues).status_code == 403
    temprano = _visto_bueno(cliente, sesion("diroperaciones"), datos, anio, mes)
    assert temprano.status_code == 409, "el mes todavia no termina"

    r = _visto_bueno(cliente, sesion("diroperaciones"), datos, anio, mes, despues)
    assert r.status_code == 200, r.text
    assert _visto_bueno(cliente, sesion("diroperaciones"), datos, anio, mes,
                        despues).status_code == 409

    corte = _comisiones(cliente, sesion("finanzas"), datos, anio, mes,
                        ahora=despues.isoformat())
    assert corte["estado"] == "autorizado"
    assert corte["autorizado_por"] == "Jose Luis Pichardo"
    ana = next(c for c in corte["consultores"] if c["consultor"] == "Ana Solis")
    assert ana["estado"] == "por_pagar"
    pago_id = ana["pago"]["pago_id"]
    assert Decimal(str(ana["pago"]["total"])) == Decimal(str(comision["monto"]))

    # Lo que finanzas valida despues del visto bueno ya es del mes que sigue.
    otro, _ = _aprobado(cliente, sesion, datos, 357)
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        nueva = (db.query(m.ComisionConsultor)
                 .filter_by(servicio_id=otro["id"]).one())
        siguiente = _primero_del_siguiente(anio, mes)
        assert (nueva.anio, nueva.mes) == (siguiente.year, siguiente.month)

    assert cliente.post(f"/nomina/comisiones/pagos/{pago_id}/pagar",
                        headers=sesion("diroperaciones"),
                        json={"referencia": "SPEI 4471"}).status_code == 403
    assert cliente.post(f"/nomina/comisiones/pagos/{pago_id}/pagar",
                        headers=sesion("finanzas"),
                        json={"referencia": "  "}).status_code == 400
    r = cliente.post(f"/nomina/comisiones/pagos/{pago_id}/pagar",
                     headers=sesion("finanzas"), json={"referencia": "SPEI 4471"})
    assert r.status_code == 200, r.text
    assert r.json()["corte"] == "pagado"

    corte = _comisiones(cliente, sesion("finanzas"), datos, anio, mes,
                        ahora=despues.isoformat())
    ana = next(c for c in corte["consultores"] if c["consultor"] == "Ana Solis")
    assert ana["estado"] == "pagado"
    assert ana["pago"]["referencia"] == "SPEI 4471"
    assert corte["estado"] == "pagado"
    with SessionLocal() as db:
        pagada = (db.query(m.ComisionConsultor)
                  .filter_by(servicio_id=servicio["id"]).one())
        assert pagada.estatus == m.EstatusComision.PAGADA


def test_si_las_diferencias_lo_dejan_debajo_de_cero_cobra_cero(cliente, sesion,
                                                                datos):
    _, comision = _aprobado(cliente, sesion, datos, 360)
    anio, mes = _este_mes()
    monto = Decimal(str(comision["monto"]))
    r = cliente.post("/nomina/comisiones/diferencias", headers=sesion("finanzas"),
                     json={"pais_id": datos["mx"]["id"],
                           "consultor_id": datos["personal"]["Ana Solis"]["id"],
                           "monto": str(-(monto + 500)),
                           "motivo": "Nota de credito de un servicio de julio"})
    assert r.status_code == 201, r.text
    assert (r.json()["anio"], r.json()["mes"]) == (anio, mes)

    corte = _comisiones(cliente, sesion("finanzas"), datos, anio, mes)
    ana = next(c for c in corte["consultores"] if c["consultor"] == "Ana Solis")
    assert Decimal(str(ana["totales"]["a_pagar"])) == 0
    assert Decimal(str(ana["totales"]["en_contra"])) == Decimal("-500")

    despues = _en_mexico(_primero_del_siguiente(anio, mes), 9, 0)
    assert _visto_bueno(cliente, sesion("diroperaciones"), datos, anio, mes,
                        despues).status_code == 200
    corte = _comisiones(cliente, sesion("finanzas"), datos, anio, mes,
                        ahora=despues.isoformat())
    ana = next(c for c in corte["consultores"] if c["consultor"] == "Ana Solis")
    assert ana["estado"] == "sin_pago"
    assert Decimal(str(ana["pago"]["saldo_en_contra"])) == Decimal("-500")
    assert corte["estado"] == "pagado", "no hay nada que transferir"

    siguiente = _primero_del_siguiente(anio, mes)
    que_sigue = _comisiones(cliente, sesion("finanzas"), datos, siguiente.year,
                            siguiente.month, ahora=despues.isoformat())
    ana = next(c for c in que_sigue["consultores"]
               if c["consultor"] == "Ana Solis")
    assert [(d["tipo"], Decimal(str(d["monto"]))) for d in ana["diferencias"]] \
        == [("saldo_en_contra", Decimal("-500"))]


def test_la_comision_perdida_dice_cuanto_y_por_que(cliente, sesion, datos):
    from test_cierre import test_comision_perdida_si_se_cierra_fuera_de_plazo
    test_comision_perdida_si_se_cierra_fuera_de_plazo(cliente, sesion, datos)
    anio, mes = _este_mes()
    corte = _comisiones(cliente, sesion("finanzas"), datos, anio, mes)
    ana = next(c for c in corte["consultores"] if c["consultor"] == "Ana Solis")
    assert ana["se_paga"] == []
    perdida = ana["no_se_paga"][0]
    assert perdida["estatus"] == "perdida"
    assert Decimal(str(perdida["monto"])) > 0, "dice cuanto se perdio"
    assert perdida["visto_bueno"] and perdida["limite"]
    assert Decimal(str(ana["totales"]["a_pagar"])) == 0


def test_volver_a_facturar_despues_del_visto_bueno_deja_una_diferencia(
        cliente, sesion, datos):
    """Antes del visto bueno del mes la comision se corrige en su lugar;
    despues, lo que cambia es una diferencia en el mes que sigue."""
    from app import comisiones as motor
    from app import models as m
    from app.db import SessionLocal

    servicio, comision = _aprobado(cliente, sesion, datos, 365)
    anio, mes = _este_mes()

    def mas_horas(horas):
        with SessionLocal() as db:
            j = (db.query(m.Jornada).join(m.Equipo)
                 .filter(m.Equipo.servicio_id == servicio["id"]).one())
            j.fin_real = j.fin_programado + timedelta(hours=horas)
            db.commit()
            c = motor.generar(db, servicio["id"])
            return Decimal(str(c.monto))

    antes = Decimal(str(comision["monto"]))
    corregida = mas_horas(2)
    assert corregida > antes, "sin visto bueno se corrige en su lugar"
    with SessionLocal() as db:
        assert db.query(m.AjusteComision).count() == 0

    despues = _en_mexico(_primero_del_siguiente(anio, mes), 9, 0)
    assert _visto_bueno(cliente, sesion("diroperaciones"), datos, anio, mes,
                        despues).status_code == 200
    assert mas_horas(4) == corregida, "con visto bueno su monto ya no se mueve"
    with SessionLocal() as db:
        ajuste = db.query(m.AjusteComision).one()
        assert ajuste.tipo == "refacturacion"
        assert Decimal(str(ajuste.monto)) > 0
        siguiente = _primero_del_siguiente(anio, mes)
        assert (ajuste.anio, ajuste.mes) == (siguiente.year, siguiente.month)
    # Otra vuelta igual no la vuelve a sumar.
    mas_horas(4)
    with SessionLocal() as db:
        assert db.query(m.AjusteComision).count() == 1

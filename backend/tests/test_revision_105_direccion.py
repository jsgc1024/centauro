# -*- coding: utf-8 -*-
"""Seccion 105 (grupo g4): las incidencias y la ventana del director de
operaciones.

Decision 2 de Salvador (29 sep): las incidencias las levanta el
consultor del servicio --y quien lo cubre-- y tambien la central; se
registran desde la ficha del servicio y desde la encuesta; el director
de operaciones las autoriza o las descarta desde su propia pantalla; al
autorizar se recalcula el bono del mes si RRHH no lo ha autorizado; la
grave retiene la comision del consultor y le llega a RRHH. Y la pantalla
"Direccion de operaciones": la bandeja de firmas y el tablero de hoy.
"""
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, manana)
from test_bonos import _mes_trabajado
from test_nominas import _aprobado, _comisiones, _con_visto_bueno

WEB = Path(__file__).resolve().parents[1] / "app" / "web"


def _js(nombre):
    return (WEB / nombre).read_text(encoding="utf-8")


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
    """Los avisos al telefono que salieron, sin salir de verdad."""
    from app import push

    salieron = []
    monkeypatch.setattr(push, "avisar", lambda db, persona_id, titulo, cuerpo,
                        **k: salieron.append((persona_id, titulo, k.get("url")))
                        or {"enviados": 1})
    return salieron


# ---------------------------------------------------------------- escenarios

def _registrar(cliente, headers, persona_id, servicio_id, gravedad="leve",
               fecha=None, jornada_id=None,
               descripcion="Queja del ejecutivo por la presentacion del vehiculo"):
    cuerpo = {"persona_id": persona_id, "fecha": str(fecha or date.today()),
              "gravedad": gravedad, "servicio_id": servicio_id,
              "descripcion": descripcion}
    if jornada_id:
        cuerpo["jornada_id"] = jornada_id
    return cliente.post("/incidencias", json=cuerpo, headers=headers)


def _firmar(cliente, headers, incidencia_id, autorizar=True,
            resolucion="Confirmado con la central y con el cliente"):
    return cliente.post(f"/incidencias/{incidencia_id}/visto-bueno",
                        json={"autorizar": autorizar, "resolucion": resolucion},
                        headers=headers)


def _evaluacion(cliente, sesion, persona_id):
    hoy = date.today()
    r = cliente.get(f"/evaluaciones/{persona_id}/{hoy.year}/{hoy.month}",
                    headers=sesion("diroperaciones"))
    assert r.status_code == 200, r.text
    return r.json()


def _evaluar(cliente, sesion, persona_id):
    hoy = date.today()
    r = cliente.post("/evaluaciones",
                     json={"persona_id": persona_id, "anio": hoy.year,
                           "mes": hoy.month, "capacitacion_cumplida": True},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


def _bitacora(servicio_id, accion):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as s:
        return [r.detalle for r in s.query(m.RegistroAccion)
                .filter_by(servicio_id=servicio_id, accion=accion)
                .order_by(m.RegistroAccion.id).all()]


def _correos_a(correo):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as s:
        return [(n.asunto, n.cuerpo, n.datos or "", n.enlace_seguimiento)
                for n in s.query(m.Notificacion).filter_by(correo=correo)
                .order_by(m.Notificacion.id).all()]


def _bandeja(cliente, headers):
    r = cliente.get("/direccion/bandeja", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ================================================= A. registrar (decision 2)

def test_la_central_registra_una_incidencia_y_finanzas_no(cliente, sesion, datos):
    """Salvador: la levanta el consultor y tambien la central. La central
    registra una leve sobre alguien del servicio: 201 y queda en la
    bitacora del servicio. Finanzas no trae la actividad: 403."""
    servicio, persona = _mes_trabajado(cliente, sesion, datos, dia_base=3)
    j = servicio["equipos"][0]["jornadas"][0]
    r = _registrar(cliente, sesion("central"), persona, servicio["id"],
                   fecha=j["fecha"], jornada_id=j["id"])
    assert r.status_code == 201, r.text
    assert r.json()["autorizada"] is False
    assert "visto bueno" in r.json()["siguiente_paso"]
    rastro = _bitacora(servicio["id"], "registrar incidencia")
    assert len(rastro) == 1 and "Luis Mendoza" in rastro[0] and "leve" in rastro[0]

    r = _registrar(cliente, sesion("finanzas"), persona, servicio["id"])
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["actividad"] == "bonos.incidencia"
    # Y la lista trae quien la registro, para la bandeja y el expediente.
    lista = cliente.get(f"/incidencias?servicio_id={servicio['id']}",
                        headers=sesion("central")).json()
    assert len(lista) == 1
    assert lista[0]["registrada_por"] == "Sofia Navarro"
    assert lista[0]["estado"] == "pendiente" and lista[0]["folio"] == servicio["folio"]


def test_las_opciones_del_panel_traen_a_la_gente_y_los_dias(cliente, sesion, datos):
    """El panel no pide numeros: ofrece a quien va o fue en el servicio
    --mas el consultor titular, para la encuesta que lo califica-- y
    los dias del servicio, con el de hoy o el ultimo que paso propuesto."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(3100 + i), datos["modalidades"]["full_day"]["id"])
         for i in range(2)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    jornadas = servicio["equipos"][0]["jornadas"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    asignar(cliente, h, jornadas[0]["id"], persona_id=juan)

    r = cliente.get(f"/incidencias/opciones/{servicio['id']}", headers=sesion("central"))
    assert r.status_code == 200, r.text
    o = r.json()
    gente = {p["persona_id"]: p for p in o["personas"]}
    assert gente[juan]["dias"] == 1 and gente[juan]["consultor"] is False
    ana = datos["personal"]["Ana Solis"]["id"]
    assert gente[ana]["consultor"] is True
    assert [j["jornada_id"] for j in o["jornadas"]] == [jornadas[1]["id"], jornadas[0]["id"]]
    # Ningun dia ha pasado: se propone el primero del servicio.
    assert o["jornada_propuesta"] == jornadas[0]["id"]
    assert o["hoy"] == date.today().isoformat()
    assert cliente.get(f"/incidencias/opciones/{servicio['id']}",
                       headers=sesion("finanzas")).status_code == 403


# ============================================ el visto bueno y el bono

def test_autorizar_recalcula_el_bono_que_sigue_calculado(cliente, sesion, datos):
    """El mes ya se calculo (el dia 3) y la leve se firma despues: antes
    la respuesta decia "hay que recalcular" y nadie recalculaba. Ahora la
    firma vuelve a calcular la evaluacion y el bono queda en cero."""
    servicio, persona = _mes_trabajado(cliente, sesion, datos, dia_base=5)
    antes = _evaluar(cliente, sesion, persona)
    assert antes["anulado_por_incidencia"] is False and float(antes["bono"]) > 0

    hoy = date.today()
    incidencia = _registrar(cliente, sesion("central"), persona, servicio["id"],
                            fecha=date(hoy.year, hoy.month, 5)).json()
    r = _firmar(cliente, sesion("diroperaciones"), incidencia["incidencia_id"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["resultado"] == "autorizada"
    assert d["bono"] == "recalculado" and d["clave"] == "inc_vb_recalculado"
    assert d["evaluacion"]["anulado_por_incidencia"] is True
    assert float(d["evaluacion"]["bono"]) == 0

    despues = _evaluacion(cliente, sesion, persona)
    assert despues["anulado_por_incidencia"] is True
    assert float(despues["bono"]) == 0 and despues["estatus"] == "calculada"
    assert despues["estrellas"] > 0, "las estrellas se conservan como referencia"
    rastro = _bitacora(servicio["id"], "autorizar incidencia")
    assert len(rastro) == 1 and "Confirmado con la central" in rastro[0]


def test_autorizar_no_toca_el_bono_que_rrhh_ya_autorizo(cliente, sesion, datos):
    """Con la evaluacion autorizada por RRHH el bono es dinero: no se
    recalcula (409 del motor, seccion 101) y la respuesta lo dice; la
    incidencia queda autorizada, para el expediente."""
    servicio, persona = _mes_trabajado(cliente, sesion, datos, dia_base=8)
    _evaluar(cliente, sesion, persona)
    hoy = date.today()
    mes = cliente.get(f"/mes/{datos['mx']['id']}/{hoy.year}/{hoy.month}",
                      headers=sesion("rrhh")).json()
    renglon = next(p for p in mes["personas"] if p["persona_id"] == persona)
    r = cliente.post(f"/evaluaciones/{renglon['evaluacion_id']}/autorizar",
                     headers=sesion("rrhh"))
    assert r.status_code == 200, r.text

    incidencia = _registrar(cliente, sesion("consultor"), persona, servicio["id"],
                            fecha=date(hoy.year, hoy.month, 8)).json()
    r = _firmar(cliente, sesion("diroperaciones"), incidencia["incidencia_id"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["bono"] == "ya_autorizado" and d["bono_ya_cerrado"] is True
    assert d["clave"] == "inc_vb_ya_autorizado"
    assert d["evaluacion"]["estatus"] == "autorizada"
    assert "ya está autorizada" in d["nota"] and "expediente" in d["nota"]

    despues = _evaluacion(cliente, sesion, persona)
    assert despues["estatus"] == "autorizada"
    assert despues["anulado_por_incidencia"] is False and float(despues["bono"]) > 0
    lista = cliente.get(f"/incidencias?persona_id={persona}",
                        headers=sesion("rrhh")).json()
    assert lista[0]["estado"] == "autorizada"
    assert lista[0]["visto_bueno_por"] == "Jose Luis Pichardo"


def test_descartar_deja_el_bono_intacto_y_queda_en_el_expediente(cliente, sesion,
                                                                  datos):
    """La descartada no toca bono ni comision, pero se queda en el
    expediente de la persona con su resolucion. Y una incidencia se
    firma una sola vez: la segunda firma contesta 409."""
    servicio, persona = _mes_trabajado(cliente, sesion, datos, dia_base=11)
    antes = _evaluar(cliente, sesion, persona)
    hoy = date.today()
    incidencia = _registrar(cliente, sesion("central"), persona, servicio["id"],
                            fecha=date(hoy.year, hoy.month, 11)).json()
    r = _firmar(cliente, sesion("diroperaciones"), incidencia["incidencia_id"],
                autorizar=False, resolucion="El ejecutivo se retracto de la queja")
    assert r.status_code == 200, r.text
    assert r.json()["resultado"] == "descartada"
    assert r.json()["bono"] == "descartada" and r.json()["clave"] == "inc_vb_descartada"

    despues = _evaluacion(cliente, sesion, persona)
    assert despues["anulado_por_incidencia"] is False
    assert float(despues["bono"]) == float(antes["bono"])
    assert _bitacora(servicio["id"], "descartar incidencia")

    exp = cliente.get(f"/profesionalismo/persona/{persona}/expediente",
                      headers=sesion("consultor")).json()
    assert len(exp["incidencias"]) == 1
    suya = exp["incidencias"][0]
    assert suya["estado"] == "descartada" and suya["autorizada"] is False
    assert suya["resolucion"] == "El ejecutivo se retracto de la queja"
    assert suya["registrada_por"] == "Sofia Navarro"
    assert suya["visto_bueno_por"] == "Jose Luis Pichardo"

    otra = _firmar(cliente, sesion("diroperaciones"), incidencia["incidencia_id"])
    assert otra.status_code == 409, otra.text
    assert "ya tiene visto bueno" in otra.json()["detail"]["mensaje"]
    assert otra.json()["detail"]["que_hacer"]


# ======================================= la grave: RRHH y la comision

def test_la_grave_autorizada_avisa_a_rrhh_y_la_comision_nace_retenida(
        cliente, sesion, datos, avisos):
    """La grave con visto bueno le llega a RRHH por correo y al telefono,
    y cuando finanzas cierra el servicio la comision del consultor nace
    retenida (la regla que ya existia en `comisiones.generar`)."""
    servicio, cierre_id = _con_visto_bueno(cliente, sesion, datos, 3110)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    incidencia = _registrar(cliente, sesion("central"), juan, servicio["id"],
                            gravedad="grave",
                            descripcion="Abandono el punto con el ejecutivo a bordo").json()
    r = _firmar(cliente, sesion("diroperaciones"), incidencia["incidencia_id"],
                resolucion="Confirmado por la central y por el cliente")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["aviso_rrhh"] == 1
    assert d["comisiones_retenidas"] == [], "todavia no hay comision que retener"

    correos = _correos_a("rrhh@centauro.lat")
    assert len(correos) == 1
    asunto, cuerpo, datos_correo, enlace = correos[0]
    assert "Incidencia grave" in asunto and "Juan Ramirez" in asunto
    assert servicio["folio"] in asunto and "retenida" in cuerpo
    assert "Abandono el punto" in datos_correo
    assert enlace == f"/consola/#/equipo/{juan}"
    # Al telefono de RRHH, con el mismo asunto y la misma pantalla. Los
    # otros avisos que salieron son los del cierre, al consultor.
    de_rrhh = [a for a in avisos if a[1] == asunto]
    assert len(de_rrhh) == 1 and de_rrhh[0][2] == enlace

    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["comision_consultor"]["estatus"] == "retenida"


def test_la_grave_que_llega_con_la_comision_generada_la_retiene(cliente, sesion,
                                                                 datos, db):
    """Lo normal: finanzas cierra primero y la firma llega despues. La
    comision seguia generada y se pagaba. Ahora el visto bueno retiene
    la que sigue generada y sin corte; direccion general la decide."""
    from app import models as m

    servicio, comision = _aprobado(cliente, sesion, datos, 3115)
    assert comision["estatus"] == "generada"
    juan = datos["personal"]["Juan Ramirez"]["id"]
    incidencia = _registrar(cliente, sesion("consultor"), juan, servicio["id"],
                            gravedad="grave",
                            descripcion="Dejo sola a la principal en el aeropuerto").json()
    r = _firmar(cliente, sesion("diroperaciones"), incidencia["incidencia_id"])
    assert r.status_code == 200, r.text
    retenidas = r.json()["comisiones_retenidas"]
    assert [c["comision_id"] for c in retenidas] == [comision["comision_id"]]
    assert retenidas[0]["consultor"] == "Ana Solis"

    fila = db.get(m.ComisionConsultor, comision["comision_id"])
    assert fila.estatus == m.EstatusComision.RETENIDA
    assert "incidencia grave" in fila.motivo

    anio, mes = fila.anio, fila.mes
    corte = _comisiones(cliente, sesion("finanzas"), datos, anio, mes)
    ana = next(c for c in corte["consultores"] if c["consultor"] == "Ana Solis")
    assert [x["folio"] for x in ana["no_se_paga"]] == [servicio["folio"]]
    assert ana["se_paga"] == []

    decision = cliente.post(f"/comisiones/{comision['comision_id']}/resolver",
                            json={"se_paga": True,
                                  "resolucion": "La incidencia no fue del consultor"},
                            headers=sesion("dirgeneral"))
    assert decision.status_code == 200, decision.text
    assert decision.json()["resultado"] == "generada"


# ======================================================== B. la pantalla

def test_la_bandeja_es_del_director_y_de_direccion_general(cliente, sesion):
    """Finanzas no abre `/direccion/bandeja` (403); el director de
    operaciones y direccion general si, con sus cuatro secciones."""
    r = cliente.get("/direccion/bandeja", headers=sesion("finanzas"))
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["actividad"] == "direccion.ver"
    assert cliente.get("/direccion/bandeja",
                       headers=sesion("consultor")).status_code == 403
    for quien in ("diroperaciones", "dirgeneral"):
        d = _bandeja(cliente, sesion(quien))
        assert set(d) >= {"incidencias_por_autorizar", "plazos_vencidos",
                          "cobros_por_autorizar", "hoy"}
        assert d["cobros_por_autorizar"] == []
        assert [p["codigo"] for p in d["hoy"]] and d["hoy"][0]["codigo"] == "MX"


def test_una_incidencia_pendiente_sale_en_la_bandeja_y_desaparece_al_autorizarla(
        cliente, sesion, datos):
    servicio, persona = _mes_trabajado(cliente, sesion, datos, dia_base=14)
    incidencia = _registrar(cliente, sesion("central"), persona, servicio["id"],
                            fecha=date.today().replace(day=14)).json()
    h = sesion("diroperaciones")
    pendientes = _bandeja(cliente, h)["incidencias_por_autorizar"]
    assert [i["id"] for i in pendientes] == [incidencia["incidencia_id"]]
    fila = pendientes[0]
    assert fila["persona"] == "Luis Mendoza" and fila["gravedad"] == "leve"
    assert fila["folio"] == servicio["folio"]
    assert fila["ruta"] == f"#/servicio/{servicio['id']}"
    assert fila["registrada_por"] == "Sofia Navarro" and fila["descripcion"]

    assert _firmar(cliente, h, incidencia["incidencia_id"]).status_code == 200
    assert _bandeja(cliente, h)["incidencias_por_autorizar"] == []


def _cierre_vencido(cliente, sesion, datos, offset, regresado=False):
    """Un servicio trabajado con su cierre en la fase del consultor y el
    plazo ya vencido: se mueven las columnas del cierre, que es lo que
    `plazos_vencidos` lee."""
    from app import models as m
    from app.db import SessionLocal

    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    ejecutar_jornada(cliente, sesion("juan"), j)
    r = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir", headers=h)
    assert r.status_code == 200, r.text
    cierre_id = r.json()["cierre_id"]

    ahora = datetime.now().replace(microsecond=0)
    with SessionLocal() as s:
        cierre = s.get(m.Cierre, cierre_id)
        if regresado:
            cierre.estatus = m.EstatusCierre.DEVUELTO_A_OPERACION
            cierre.devuelto_en = ahora - timedelta(hours=30)
            cierre.limite_consultor = ahora + timedelta(hours=10)
        else:
            cierre.estatus = m.EstatusCierre.SIN_VISTO_BUENO
            cierre.limite_consultor = ahora - timedelta(hours=3)
        s.commit()
    return servicio, cierre_id


def test_un_cierre_con_plazo_vencido_sale_en_plazos_vencidos(cliente, sesion, datos):
    """Sin visto bueno y con las 24 h del consultor vencidas: sale con el
    consultor y hace cuanto vencio. El regresado por finanzas se mide
    con las 24 h desde el regreso. El que sigue en plazo no sale."""
    vencido, cierre_vencido = _cierre_vencido(cliente, sesion, datos, 3120)
    regresado, cierre_regresado = _cierre_vencido(cliente, sesion, datos, 3122,
                                                  regresado=True)
    en_plazo, _ = _con_visto_bueno(cliente, sesion, datos, 3124)

    filas = _bandeja(cliente, sesion("diroperaciones"))["plazos_vencidos"]
    por_cierre = {f["cierre_id"]: f for f in filas}
    assert set(por_cierre) == {cierre_vencido, cierre_regresado}
    f = por_cierre[cierre_vencido]
    assert f["folio"] == vencido["folio"] and f["consultor"] == "Ana Solis"
    assert f["reloj"] == "consultor" and f["regresado"] is False
    assert 175 <= f["minutos_vencido"] <= 190
    assert f["ruta"] == f"#/servicio/{vencido['id']}"
    g = por_cierre[cierre_regresado]
    assert g["reloj"] == "regreso" and g["regresado"] is True
    assert 355 <= g["minutos_vencido"] <= 370
    assert en_plazo["folio"] not in {x["folio"] for x in filas}


def test_el_tablero_cuenta_los_servicios_de_hoy_del_pais(cliente, sesion, datos):
    """Hoy y manana por pais, con la lista de folios detras de cada
    numero, y las incidencias del mes por gravedad: solo las
    autorizadas cuentan; las pendientes van aparte."""
    h = sesion("consultor")
    hoy = date.today()
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(hoy, datos["modalidades"]["full_day"]["id"]),
         jornada(hoy + timedelta(days=1), datos["modalidades"]["full_day"]["id"])])
    juan = datos["personal"]["Juan Ramirez"]["id"]
    leve = _registrar(cliente, sesion("central"), juan, servicio["id"]).json()
    assert _firmar(cliente, sesion("diroperaciones"),
                   leve["incidencia_id"]).status_code == 200
    _registrar(cliente, sesion("central"), juan, servicio["id"], gravedad="grave",
               descripcion="Todavia sin visto bueno, no cuenta en el mes")

    tablero = _bandeja(cliente, sesion("diroperaciones"))["hoy"]
    mx = next(p for p in tablero if p["codigo"] == "MX")
    assert mx["hoy"] == hoy.isoformat()
    assert mx["servicios_hoy"]["n"] == 1
    assert mx["servicios_hoy"]["lista"][0]["folio"] == servicio["folio"]
    assert mx["servicios_hoy"]["lista"][0]["ruta"] == f"#/servicio/{servicio['id']}"
    assert mx["servicios_manana"]["n"] == 1
    assert mx["en_curso"]["n"] == 0 and mx["alertas_abiertas"]["n"] == 0
    assert mx["cambios_en_curso"]["n"] == 0
    inc = mx["incidencias_mes"]
    assert inc["periodo"] == f"{hoy.month:02d}/{hoy.year}"
    assert inc["leve"]["n"] == 1 and inc["leve"]["lista"][0]["folio"] == servicio["folio"]
    assert inc["grave"]["n"] == 0 and inc["error_menor"]["n"] == 0
    assert inc["pendientes"] == 1 and inc["descartadas"] == 0
    # Brasil no tiene nada hoy, y no se mezcla con Mexico.
    otros = [p for p in tablero if p["codigo"] != "MX"]
    assert all(p["servicios_hoy"]["n"] == 0 for p in otros)


# ============================================================ la consola

def test_la_consola_registra_y_firma_donde_toca():
    """El panel es uno (incidencias.js) y lo abren la ficha del eventual,
    la del implantado y la encuesta; la encuesta ya no pide teclear un
    numero; la pantalla de direccion tiene su ruta, su entrada en el menu
    y sus textos en los tres idiomas."""
    from app import permisos, puestos_base

    assert 'from "./incidencias.js"' in _js("servicio.js")
    assert "botonIncidencia(servicio.id, zonaIncidencia)" in _js("servicio.js")
    assert "botonIncidencia(servicioId, zonaIncidencia)" in _js("implantado.js")
    encuestas = _js("encuestas.js")
    assert "botonIncidencia(e.servicio_id, zonaIncidencia" in encuestas
    assert 'personaId: e.tipo === "solicitante" ? e.consultor_id : null' in encuestas
    assert "incidencia_id: ligada ? ligada.incidencia_id : null" in encuestas
    assert 'type: "number"' not in encuestas
    panel = _js("incidencias.js")
    assert 'api.get(`/incidencias/opciones/${servicioId}`)' in panel
    assert 'api.post("/incidencias", cuerpo)' in panel
    for g in ("error_menor", "leve", "grave"):
        assert f"inc_g_{g}_ayuda" in _js("idioma.js")

    direccion = _js("direccion.js")
    assert 'api.get("/direccion/bandeja")' in direccion
    assert "api.post(`/incidencias/${i.id}/visto-bueno`" in direccion
    assert "[/^#\\/direccion$/, pantallaDireccion, \"direccion\", DIRECCION]" in _js("app.js")
    menu = _js("menu.js")
    entrada = re.search(r'\{ ruta: "/direccion", clave: "direccion", necesita: '
                        r'"direccion.ver", texto: "nav_direccion", grupo: '
                        r'"nav_operaciones_ep",\s+cuenta: "rec_direccion", '
                        r'quienes: DIRECCION', menu)
    assert entrada, "la entrada del menu con el patron de las demas"
    assert "direccion" in permisos.PANTALLAS
    assert permisos.roles_de("direccion.ver") == {
        permisos.R.DIRECTOR_OPERACIONES, permisos.R.DIRECTOR_GENERAL}
    assert permisos.R.CENTRAL in permisos.roles_de("bonos.incidencia")
    direccion_ops = next(p for p in puestos_base.PUESTOS
                         if p["nombre"] == "Dirección de operaciones")
    assert "direccion" in direccion_ops["pantallas"]

    idioma = _js("idioma.js")
    for clave in ("nav_direccion", "rec_direccion", "inc_registrar", "inc_titulo",
                  "inc_vb_recalculado", "inc_vb_ya_autorizado", "dir_titulo",
                  "dir_inc_titulo", "dir_plazos_titulo", "dir_cobros_titulo",
                  "dir_hoy_titulo", "ay_dir_bandeja_para", "ay_dir_hoy_cuando",
                  "bit_accion_registrar_incidencia", "inc_exp_titulo"):
        assert idioma.count(f"    {clave}:") == 3, clave
    # El expediente de la persona ensena sus incidencias con su resolucion.
    assert "function bloqueIncidencias(exp)" in _js("personal.js")
    assert "bloqueIncidencias(exp)," in _js("personal.js")

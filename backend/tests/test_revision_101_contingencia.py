# -*- coding: utf-8 -*-
"""Seccion 101 (g6): la contingencia, el GPS, las unidades y la central.

Cuarta tanda de la revision del 28 de septiembre, grupo de contingencia:
lo que no llega de un cambio por contingencia (el cambio formalizado en
la ficha de panico, el aviso del regreso y del implantado, deshacer
despues del regreso o con un dia terminado, la hoja que se quedo vieja),
el tablero de la central que se repinta con la captura a medias, y los
detalles de unidades, GPS y panico (el secreto de Pegasus en los
registros, la unidad de baja en Odoo, el dinero de la vista previa en
Decimal, la hora del relevo que se revisa, la hora del panico en la hora
del pais).
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, jornada, manana, marcar, marcar_fin)
from app import models as m
from app import push
from app import reloj

RAIZ = os.path.join(os.path.dirname(__file__), "..")


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


# ---------------------------------------------------------------- decorado

def _montado(cliente, sesion, datos, offset=300, dias=2):
    """Un eventual de `dias` dias con Juan y la Suburban, cotizado."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"])
         for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    for j in servicio["equipos"][0]["jornadas"]:
        for r in asignar(cliente, h, j["id"],
                         persona_id=datos["personal"]["Juan Ramirez"]["id"],
                         vehiculo_id=datos["suburban"]["id"]):
            assert r.status_code == 200, r.text
        configurar_origen(cliente, h, j["id"])
    return servicio


def _servicio_de_hoy(cliente, sesion, datos, pais_id=None, plaza_id=None):
    """Un servicio de hoy con Juan y la Suburban, que arranco hace 50
    minutos. El dia es el del arranque, no el de hoy, por si la bateria
    corre pasada la medianoche."""
    ahora = datetime.now().replace(second=0, microsecond=0)
    inicio = ahora - timedelta(minutes=50)
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(inicio.date(), datos["modalidades"]["full_day"]["id"],
                 hora=inicio.strftime("%H:%M:00"))],
        pais_id=pais_id, plaza_id=plaza_id,
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    for r in asignar(cliente, h, j["id"],
                     persona_id=datos["personal"]["Juan Ramirez"]["id"],
                     vehiculo_id=datos["suburban"]["id"]):
        assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    return servicio, j, inicio


def _hoy_en_curso(cliente, sesion, datos):
    """El de hoy, ya arrancado: Juan llego y esta con el principal."""
    servicio, j, inicio = _servicio_de_hoy(cliente, sesion, datos)
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=10))
    assert r.status_code == 200, r.text
    r = marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo", inicio)
    assert r.status_code == 200, r.text
    return servicio, j


def _se_presenta(cliente, sesion, j):
    inicio = datetime.fromisoformat(j["inicio_programado"])
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=10))
    assert r.status_code == 200, r.text
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo", inicio)


def _cambio(datos, j, sale="Juan Ramirez", entra="Luis Mendoza", **extra):
    return {"desde_jornada_id": j["id"],
            "sale_persona_id": datos["personal"][sale]["id"],
            "entra_persona_id": datos["personal"][entra]["id"],
            "motivo": "Se sintio mal", **extra}


def _relevo(cliente, sesion, datos, j, ahora=None, **extra):
    ruta = "/contingencia/reemplazos/personal"
    if ahora is not None:
        ruta += f"?ahora={ahora.isoformat()}"
    return cliente.post(ruta, headers=sesion("consultor"),
                        json=_cambio(datos, j, **extra))


def _regreso(cliente, sesion, reemplazo_id, dia, ahora=None, **extra):
    ruta = f"/contingencia/reemplazos/{reemplazo_id}/regreso"
    if ahora is not None:
        ruta += f"?ahora={ahora.isoformat()}"
    return cliente.post(ruta, headers=sesion("consultor"),
                        json={"desde": dia, **extra})


def _panico(cliente, sesion, j=None, quien="juan"):
    cuerpo = {"canal": "boton_app", "lat": "19.4270", "lon": "-99.1677"}
    if j:
        cuerpo["jornada_id"] = j["id"]
    r = cliente.post("/contingencia/alertas", headers=sesion(quien),
                     json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


def _fichas_de_panico(db):
    from app import central as motor
    db.expire_all()
    return motor.tablero(db, datetime.now())["roto"]["panico"]


def _historial(cliente, sesion, servicio):
    return cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                       headers=sesion("consultor")).json()


def _asignados(cliente, sesion, jornada_id):
    r = cliente.get(f"/servicios/jornadas/{jornada_id}/asignaciones",
                    headers=sesion("consultor"))
    return sorted(p["nombre"] for p in r.json()["personal"])


def _publicar_hoja(cliente, sesion, servicio):
    r = cliente.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
                     headers=sesion("consultor"), json={"forzar": True})
    assert r.status_code == 200, r.text
    return r.json()


def _revision_del_dia(cliente, sesion, jornada_id):
    r = cliente.get(f"/central/jornadas/{jornada_id}/revision",
                    headers=sesion("central"))
    assert r.status_code == 200, r.text
    return {p["clave"]: p for p in r.json()["revision"]}


def _web(nombre):
    return open(os.path.join(RAIZ, "app", "web", nombre),
                encoding="utf-8").read()


# ================================================= 110 · el cambio formalizado

def test_la_ficha_de_panico_de_la_central_dice_el_cambio_formalizado(
        cliente, sesion, datos, db):
    """Juan aprieta el boton; el consultor formaliza el cambio ligado a
    esa alerta. La ficha del tablero de la central dice "Luis Mendoza
    entra por Juan Ramirez": antes el cambio se calculaba solo en una
    lista que ninguna pantalla pedia, y el enlace siempre iba vacio."""
    servicio, j = _hoy_en_curso(cliente, sesion, datos)
    alerta = _panico(cliente, sesion, j)
    assert _fichas_de_panico(db)[0]["cambio"] is None

    r = _relevo(cliente, sesion, datos, j, alerta_id=alerta["id"])
    assert r.status_code == 200, r.text

    ficha = next(f for f in _fichas_de_panico(db) if f["id"] == alerta["id"])
    assert ficha["cambio"] == "Luis Mendoza entra por Juan Ramirez"
    movimiento = db.get(m.ReemplazoRecurso, r.json()["reemplazo_id"])
    assert movimiento.alerta_id == alerta["id"]


def test_sin_enlace_la_ficha_toma_el_cambio_del_servicio_hecho_despues(
        cliente, sesion, datos, db):
    """Si el panel no ligo la alerta, cuenta el ultimo cambio del mismo
    servicio hecho despues de que sono. Uno de antes no: ese no es la
    respuesta a esta alerta."""
    servicio, j = _hoy_en_curso(cliente, sesion, datos)
    assert _relevo(cliente, sesion, datos, j).status_code == 200
    # Luis, que es quien esta en la calle ahora, aprieta el boton.
    alerta = _panico(cliente, sesion, j, quien="luis")
    ficha = next(f for f in _fichas_de_panico(db) if f["id"] == alerta["id"])
    assert ficha["cambio"] is None, "un cambio de antes no responde a la alerta"

    r = _relevo(cliente, sesion, datos, j, sale="Luis Mendoza",
                entra="Carlos Vega")
    assert r.status_code == 200, r.text
    ficha = next(f for f in _fichas_de_panico(db) if f["id"] == alerta["id"])
    assert ficha["cambio"] == "Carlos Vega entra por Luis Mendoza"


def test_las_alertas_se_piden_por_servicio_y_el_panel_manda_el_enlace(
        cliente, sesion, datos):
    """El panel del cambio busca la alerta abierta de SU servicio para
    ligarla; la lista se filtra por servicio y el JS manda `alerta_id`."""
    uno, j1 = _hoy_en_curso(cliente, sesion, datos)
    _panico(cliente, sesion, j1)
    _panico(cliente, sesion)                      # sin servicio
    r = cliente.get(f"/contingencia/alertas?servicio_id={uno['id']}",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert [a["servicio_id"] for a in r.json()] == [uno["id"]]
    assert len(cliente.get("/contingencia/alertas",
                           headers=sesion("consultor")).json()) == 2

    js = _web("servicio.js")
    assert "alerta_id: alerta ? alerta.id : null" in js
    assert "/contingencia/alertas?servicio_id=" in js


# ================================================= 110 · el aviso al telefono

def test_el_regreso_avisa_al_telefono_a_los_dos(cliente, sesion, datos,
                                               avisos):
    """Juan vuelve el dia 4 y Luis trabaja hasta el 3. Los dos lo saben
    en el momento: antes ninguno recibia nada, Luis podia presentarse el
    dia 4 y Juan solo se enteraba si abria la app."""
    servicio = _montado(cliente, sesion, datos, offset=330, dias=5)
    dias = servicio["equipos"][0]["jornadas"]
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()
    avisos.clear()

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[3]["fecha"])
    assert r.status_code == 200, r.text
    assert r.json()["regresa_el"] == dias[3]["fecha"]
    assert r.json()["avisado"]["enviados"] == 1

    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    por_persona = {a["persona_id"]: a for a in avisos}
    assert set(por_persona) == {juan, luis}, avisos
    assert por_persona[juan]["titulo"] == push.tx("es", "regreso_titular_titulo")
    assert dias[3]["fecha"] in por_persona[juan]["cuerpo"]
    assert "Luis Mendoza" in por_persona[juan]["cuerpo"]
    assert por_persona[juan]["accion"] == "confirmar"
    assert por_persona[luis]["titulo"] == push.tx("es", "regreso_cubre_titulo")
    assert dias[2]["fecha"] in por_persona[luis]["cuerpo"]
    assert "Juan Ramirez" in por_persona[luis]["cuerpo"]
    # Y en portugues, para la plaza de Brasil.
    assert push.tx("pt", "regreso_cubre_titulo") != push.tx("es", "regreso_cubre_titulo")


def test_el_cambio_del_implantado_avisa_a_quien_entra_y_a_quien_sale(
        cliente, sesion, datos, avisos):
    """A se enferma y entra C, en un implantado: C recibe "Entras a un
    servicio" y A "Ya no vas", como en el eventual. La vispera solo mira
    manana, y este es justo el urgente."""
    h = sesion("consultor")
    servicio = cliente.post("/servicios", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "implantado",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}).json()
    contrato = cliente.post("/implantados/contratos", headers=h, json={
        "servicio_id": servicio["id"], "anio": 2029, "mes": 6,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia", "incluye_fines_de_semana": False,
        "hora_presentacion": "08:00:00",
        "titular_id": datos["personal"]["Juan Ramirez"]["id"],
        "vehiculo_id": datos["suburban"]["id"],
        "precio_mes_vehiculo": "66000", "precio_dia_personal": "2900",
        "precio_dia_adicional": "3500"}).json()
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)
    avisos.clear()

    r = cliente.post(f"/implantados/{servicio['id']}/cambios", headers=h, json={
        "tipo": "personal", "desde": "2029-06-11",
        "sale_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_id": datos["personal"]["Luis Mendoza"]["id"],
        "motivo": "enfermedad"})
    assert r.status_code == 200, r.text
    assert r.json()["avisado"]["enviados"] == 1

    por_persona = {a["persona_id"]: a for a in avisos}
    luis = datos["personal"]["Luis Mendoza"]["id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    assert por_persona[luis]["titulo"] == push.tx("es", "relevo_entra_titulo")
    assert "2029-06-11" in por_persona[luis]["cuerpo"]
    assert por_persona[juan]["titulo"] == push.tx("es", "relevo_sale_titulo")


# ================================================= 110 · deshacer

def test_deshacer_despues_del_regreso_contesta_claro_y_no_toca_nada(
        cliente, sesion, datos):
    """Con el titular ya de vuelta, deshacer por la API reventaba con
    "Ese registro ya existe". Ahora dice que el cambio ya se cerro con el
    regreso y que hacer, y el movimiento se queda como estaba."""
    servicio = _montado(cliente, sesion, datos, offset=360, dias=4)
    dias = servicio["equipos"][0]["jornadas"]
    _se_presenta(cliente, sesion, dias[0])
    hecho = _relevo(cliente, sesion, datos, dias[0]).json()

    inicio = datetime.fromisoformat(dias[2]["inicio_programado"])
    assert marcar(cliente, sesion("luis"), dias[2]["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[2]["fecha"])
    assert r.status_code == 200, r.text
    assert r.json()["jornadas_partidas"] == [dias[2]["fecha"]]

    r = cliente.post(f"/contingencia/reemplazos/{hecho['reemplazo_id']}/deshacer",
                     headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    assert "regreso" in detalle["mensaje"].lower()
    assert detalle["que_hacer"]

    filas = _historial(cliente, sesion, servicio)
    assert len(filas) == 1 and filas[0]["regreso_en"], filas
    assert _asignados(cliente, sesion, dias[2]["id"]) == [
        "Juan Ramirez", "Luis Mendoza"]


def test_deshacer_con_un_dia_ya_terminado_no_deja_el_dia_partido(
        cliente, sesion, datos):
    """Juan se presento, entro Luis y Luis termino el dia. Deshacer
    borraba el movimiento y dejaba ese dia partido: la nomina pagaba a
    dos y nada lo explicaba. Ahora se niega, con el dia y que hacer."""
    servicio = _montado(cliente, sesion, datos, offset=380, dias=2)
    dias = servicio["equipos"][0]["jornadas"]
    _se_presenta(cliente, sesion, dias[0])
    hecho = _relevo(cliente, sesion, datos, dias[0]).json()
    assert hecho["jornadas_partidas"] == [dias[0]["fecha"]]

    fin = datetime.fromisoformat(dias[0]["fin_programado"])
    r = marcar_fin(cliente, sesion("luis"), dias[0]["id"], fin)
    assert r.status_code == 200, r.text

    r = cliente.post(f"/contingencia/reemplazos/{hecho['reemplazo_id']}/deshacer",
                     headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    assert detalle["dias"] == [dias[0]["fecha"]]
    assert "termin" in detalle["mensaje"].lower()
    assert detalle["que_hacer"]

    # El dia se queda como se trabajo, con su movimiento.
    assert _asignados(cliente, sesion, dias[0]["id"]) == [
        "Juan Ramirez", "Luis Mendoza"]
    assert len(_historial(cliente, sesion, servicio)) == 1


# ================================================= 110 · la hoja vieja

def test_el_cambio_para_otro_dia_pide_volver_a_publicar_la_hoja(
        cliente, sesion, datos):
    """El lunes se cambia al conductor del jueves: no hay correo y la
    hoja publicada trae el nombre viejo. La respuesta lo dice, la
    tarjeta del cambio lo dice, y la revision del dia de la central
    marca la hoja como pendiente hasta que se vuelve a publicar."""
    servicio = _montado(cliente, sesion, datos, offset=400, dias=3)
    dias = servicio["equipos"][0]["jornadas"]
    _publicar_hoja(cliente, sesion, servicio)
    assert _revision_del_dia(cliente, sesion, dias[1]["id"])["hoja"]["listo"]

    r = _relevo(cliente, sesion, datos, dias[1])
    assert r.status_code == 200, r.text
    assert r.json()["cliente_avisado"] is False
    assert r.json()["hoja_por_publicar"] is True

    hoja = _revision_del_dia(cliente, sesion, dias[1]["id"])["hoja"]
    assert hoja["listo"] is False
    assert "publicar" in hoja["que_hacer"].lower()
    assert _historial(cliente, sesion, servicio)[0]["hoja_por_publicar"] is True

    # Se vuelve a publicar: la hoja ya trae a Luis y todo queda en paz.
    assert _publicar_hoja(cliente, sesion, servicio)["version"] == 2
    assert _revision_del_dia(cliente, sesion, dias[1]["id"])["hoja"]["listo"]
    assert _historial(cliente, sesion, servicio)[0]["hoja_por_publicar"] is False


def test_con_el_correo_al_cliente_no_se_pide_republicar_y_sin_hoja_tampoco(
        cliente, sesion, datos):
    """El cambio de hoy avisa por correo con el equipo como queda: no
    hay que republicar. Y sin hoja publicada no hay nada que corregir."""
    servicio, j = _hoy_en_curso(cliente, sesion, datos)
    _publicar_hoja(cliente, sesion, servicio)
    r = _relevo(cliente, sesion, datos, j)
    assert r.status_code == 200, r.text
    assert r.json()["cliente_avisado"] is True
    assert r.json()["hoja_por_publicar"] is False

    otro = _montado(cliente, sesion, datos, offset=420, dias=2)
    r = _relevo(cliente, sesion, datos, otro["equipos"][0]["jornadas"][1])
    assert r.status_code == 200, r.text
    assert r.json()["cliente_avisado"] is False
    assert r.json()["hoja_por_publicar"] is False


# ================================================= 111 · el tablero no borra

def test_el_tablero_de_la_central_no_se_repinta_con_una_captura_en_curso():
    """La resolucion del panico y la marca a mano se escribian y a los
    45 segundos el repintado las borraba. La consola se cuida como la app
    de campo: con un campo con texto o con foco, la vuelta se salta."""
    js = _web("central.js")
    assert "function hayCaptura(zona)" in js
    refrescar = js[js.index("const refrescar = async"):js.index("await refrescar()")]
    assert "if (hayCaptura(zona)) return;" in refrescar
    assert refrescar.index("hayCaptura") < refrescar.index("pintar(zona)")
    assert "document.activeElement" in js


# ================================================= 112 · el secreto de Pegasus

def test_el_secreto_de_pegasus_no_queda_en_los_registros_de_acceso():
    """El renglon del access log de uvicorn sale con `***` en vez del
    secreto, y el proxy no escribe ese aviso."""
    from app.main import SinSecretoDePegasus, tapar_secreto

    registro = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
        ("172.16.0.5:1234", "POST", "/gps/pegasus/aviso/s3cr3t0-largo?x=1",
         "1.1", 202), None)
    assert SinSecretoDePegasus().filter(registro) is True
    assert "s3cr3t0-largo" not in registro.getMessage()
    assert "/gps/pegasus/aviso/***" in registro.getMessage()
    assert tapar_secreto("GET /gps/unidades?pais_id=1") == "GET /gps/unidades?pais_id=1"
    assert any(isinstance(f, SinSecretoDePegasus)
               for f in logging.getLogger("uvicorn.access").filters)

    caddy = open(os.path.join(RAIZ, "..", "despliegue", "Caddyfile"),
                 encoding="utf-8").read()
    assert "@pegasus path /gps/pegasus/aviso/*" in caddy
    assert "log_skip @pegasus" in caddy


def test_el_aviso_de_pegasus_tambien_entra_por_cabecera(
        cliente, datos, db, monkeypatch):
    """Con `X-Pegasus-Secreto` no hay secreto en la ruta. La de siempre
    sigue funcionando, y sin secreto o con el equivocado no hay puerta."""
    from app import gps
    from app.config import settings
    from test_gps import GRUPO_MX, PegasusFalso, unidad

    pegasus = PegasusFalso()
    monkeypatch.setattr(settings, "pegasus_secreto_aviso", "s3cr3t0-largo")
    monkeypatch.setattr(gps.conexion, "desde_la_configuracion",
                        lambda: pegasus)
    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [unidad(101, "ABC1234", ahora)]
    gps.leer(db, pegasus, ahora - timedelta(minutes=5))

    assert cliente.post("/gps/pegasus/aviso").status_code == 404
    assert cliente.post("/gps/pegasus/aviso",
                        headers={"X-Pegasus-Secreto": "otro"}).status_code == 404
    r = cliente.post("/gps/pegasus/aviso",
                     headers={"X-Pegasus-Secreto": "s3cr3t0-largo"},
                     json={"lo": "que sea"})
    assert r.status_code == 202, r.text
    assert r.json()["recibido"] is True
    assert cliente.post("/gps/pegasus/aviso/s3cr3t0-largo").status_code == 202


# ================================================= 112 · la unidad de baja

def test_la_unidad_de_baja_en_odoo_sale_en_su_renglon(cliente, sesion, datos,
                                                     db):
    """Odoo archiva una unidad que sigue en Pegasus: contaba como ligada
    y no salia en ningun renglon. Ahora sale, dicha como de baja, y las
    cifras cuadran con la tabla."""
    from app import gps
    from test_gps import GRUPO_MX, PegasusFalso, unidad

    vehiculo = db.query(m.Vehiculo).filter_by(placa="ABC-1234").one()
    vehiculo.activo = False
    db.commit()

    pegasus = PegasusFalso()
    ahora = datetime.now(timezone.utc)
    pegasus.unidades_[GRUPO_MX] = [unidad(101, "ABC1234", ahora),
                                   unidad(103, "ZZZ-999", ahora)]
    r = gps.leer(db, pegasus, ahora)
    assert r["conectado"] and not r.get("error"), r

    d = cliente.get(f"/gps/unidades?pais_id={datos['mx']['id']}",
                    headers=sesion("consultor")).json()
    ligadas = [f for f in d["unidades"] if f["tipo"] == "ligada"]
    assert d["cifras"]["ligadas"] == len(ligadas) == 1
    assert ligadas[0]["placa"] == "ABC-1234"
    assert ligadas[0]["de_baja"] is True
    assert all(f["de_baja"] is False for f in d["unidades"]
               if f["tipo"] == "centauro")
    js = _web("unidades.js")
    assert "uni_de_baja" in js and "f.de_baja" in js


# ================================================= 112 · el dinero en Decimal

def test_el_dinero_de_la_vista_previa_sale_en_decimal_como_cadena(
        cliente, sesion, datos):
    """Lo que se le ensena al consultor --lo que comprueba quien sale y
    lo que le tocaria a quien entra-- se cuenta en Decimal y sale como
    cadena, como el resto del dinero."""
    from app import implantado

    servicio = _montado(cliente, sesion, datos, offset=440, dias=2)
    j = servicio["equipos"][0]["jornadas"][0]
    h = sesion("consultor")
    viatico = cliente.post(
        "/viaticos/asignar", headers=h,
        json={"jornada_id": j["id"],
              "persona_id": datos["personal"]["Juan Ramirez"]["id"],
              "conceptos": [{"concepto": "alimentos", "monto": "700.10",
                             "origen": "tabulador"}]}).json()
    solicitud = cliente.post(f"/viaticos/{viatico['id']}/solicitar-transferencia",
                             headers=h).json()
    assert cliente.post(
        f"/viaticos/transferencias/{solicitud['id']}/confirmar",
        params={"referencia_odoo": "TRX-101"},
        headers=sesion("finanzas")).status_code == 200
    _se_presenta(cliente, sesion, j)

    r = cliente.post("/contingencia/reemplazos/personal/vista-previa",
                     headers=h, json=_cambio(datos, j))
    assert r.status_code == 200, r.text
    v = r.json()["viaticos"]
    assert v["a_comprobar"][0]["monto"] == "700.10"
    assert v["propuestos"], v
    for x in v["propuestos"]:
        assert isinstance(x["monto"], str), x
        assert Decimal(x["monto"]) > 0
    # Y la frase del implantado la lee igual.
    aviso = implantado._aviso_del_dinero(v, "Juan", "Luis")
    assert "por tabulador" in aviso


# ================================================= 112 · la hora del relevo

def test_la_hora_del_relevo_tiene_que_ser_del_dia_del_cambio(cliente, sesion,
                                                            datos):
    servicio = _montado(cliente, sesion, datos, offset=460, dias=2)
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])
    _se_presenta(cliente, sesion, j)

    r = _relevo(cliente, sesion, datos, j, ahora=inicio + timedelta(days=1, hours=6),
                relevado_en=(inicio + timedelta(days=1, hours=2)).isoformat())
    assert r.status_code == 409, r.text
    assert "día del cambio" in r.json()["detail"]["mensaje"]
    assert _asignados(cliente, sesion, j["id"]) == ["Juan Ramirez"]

    # La unidad, igual.
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"])
    r = cliente.post("/contingencia/reemplazos/vehiculo",
                     headers=sesion("consultor"),
                     json={"desde_jornada_id": j["id"],
                           "sale_vehiculo_id": datos["suburban"]["id"],
                           "entra_vehiculo_id": otra["id"],
                           "motivo": "Se poncho",
                           "relevado_en": (inicio - timedelta(days=1)).isoformat()})
    assert r.status_code == 409, r.text


def test_la_hora_del_relevo_no_puede_ser_del_futuro(cliente, sesion, datos):
    """Son las 09:00 en el pais del servicio y el consultor captura que
    lo relevaron a las 11:00: esa hora todavia no llega."""
    servicio = _montado(cliente, sesion, datos, offset=480, dias=2)
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])
    _se_presenta(cliente, sesion, j)

    r = _relevo(cliente, sesion, datos, j, ahora=inicio + timedelta(hours=2),
                relevado_en=(inicio + timedelta(hours=4)).isoformat())
    assert r.status_code == 409, r.text
    assert "todavía no llega" in r.json()["detail"]["mensaje"]
    assert r.json()["detail"]["que_hacer"]

    # A las 11:05 si: ya paso.
    r = _relevo(cliente, sesion, datos, j,
                ahora=inicio + timedelta(hours=4, minutes=5),
                relevado_en=(inicio + timedelta(hours=4)).isoformat())
    assert r.status_code == 200, r.text
    assert r.json()["relevado_en"] == (inicio + timedelta(hours=4)).isoformat()


def test_la_hora_del_relevo_no_es_anterior_a_la_llegada_de_quien_sale(
        cliente, sesion, datos):
    """Juan marco su llegada a las 06:50; relevarlo a las 05:00 es
    contar una historia que no ocurrio."""
    servicio = _montado(cliente, sesion, datos, offset=500, dias=2)
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])
    _se_presenta(cliente, sesion, j)

    r = _relevo(cliente, sesion, datos, j, ahora=inicio + timedelta(hours=3),
                relevado_en=(inicio - timedelta(hours=2)).isoformat())
    assert r.status_code == 409, r.text
    assert "llegada" in r.json()["detail"]["mensaje"].lower()
    assert r.json()["detail"]["llegada"] == (inicio - timedelta(minutes=10)).isoformat()

    # Y el regreso, que es el mismo relevo al reves, lleva el mismo
    # candado: se corrige la hora con la que Luis de verdad se fue.
    hecho = _relevo(cliente, sesion, datos, j, ahora=inicio + timedelta(hours=3),
                    relevado_en=(inicio + timedelta(hours=1)).isoformat()).json()
    j2 = servicio["equipos"][0]["jornadas"][1]
    inicio2 = datetime.fromisoformat(j2["inicio_programado"])
    assert marcar(cliente, sesion("luis"), j2["id"], "llegada_origen",
                  inicio2 - timedelta(minutes=5)).status_code == 200
    r = _regreso(cliente, sesion, hecho["reemplazo_id"], j2["fecha"],
                 ahora=inicio2 + timedelta(hours=2),
                 relevado_en=(inicio2 + timedelta(hours=5)).isoformat())
    assert r.status_code == 409, r.text
    assert "todavía no llega" in r.json()["detail"]["mensaje"]
    r = _regreso(cliente, sesion, hecho["reemplazo_id"], j2["fecha"],
                 ahora=inicio2 + timedelta(hours=2),
                 relevado_en=(inicio2 + timedelta(hours=1)).isoformat())
    assert r.status_code == 200, r.text
    assert r.json()["jornadas_partidas"] == [j2["fecha"]]


# ================================================= 112 · la hora del panico

def test_la_hora_del_panico_sale_en_la_hora_del_pais_del_servicio(
        cliente, sesion, datos, db):
    """Para un servicio de Brasil la ficha decia "reportada 11:00" (hora
    de Mexico del navegador) y "segun su ultima marca 14:00" (hora de
    alla) en la misma tarjeta. Sale ya en hora de pared de alla, sin
    zona, como las demas."""
    h = sesion("admin")
    paises = cliente.get("/catalogos/paises", headers=h).json()
    br = next(p for p in paises if p["codigo"] == "BR")
    plazas = cliente.get("/catalogos/plazas?todas=true", headers=h).json()
    sp = next(p for p in plazas if p["pais_id"] == br["id"])
    servicio, j, _ = _servicio_de_hoy(cliente, sesion, datos,
                                      pais_id=br["id"], plaza_id=sp["id"])
    alerta = _panico(cliente, sesion, j)

    ficha = next(f for f in _fichas_de_panico(db) if f["id"] == alerta["id"])
    pintada = datetime.fromisoformat(ficha["reportada_en"])
    assert pintada.tzinfo is None, "sale con zona y el navegador la corre"
    instante = db.get(m.AlertaIncidencia, alerta["id"]).reportada_en
    assert instante.tzinfo is not None
    pais = db.get(m.Pais, br["id"])
    assert pintada == reloj.ahora_en(pais, instante)
    assert pintada != reloj.ahora_en(db.get(m.Pais, datos["mx"]["id"]),
                                     instante)

    # Sin servicio, la hora de la plaza de quien la disparo.
    suelta = _panico(cliente, sesion)
    ficha = next(f for f in _fichas_de_panico(db) if f["id"] == suelta["id"])
    pintada = datetime.fromisoformat(ficha["reportada_en"])
    assert pintada.tzinfo is None
    assert pintada == reloj.ahora_en(
        db.get(m.Pais, datos["mx"]["id"]),
        db.get(m.AlertaIncidencia, suelta["id"]).reportada_en)

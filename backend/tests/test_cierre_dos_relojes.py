# -*- coding: utf-8 -*-
"""El cierre en dos relojes.

Decision de Salvador, 22 de septiembre (PROPUESTA_CIERRE_24H.md). T0 es
el termino general del eventual --el cierre del ultimo dia, o la
cancelacion--. Desde ahi corren las 24 horas del personal para
comprobar, todos con el mismo limite. Al vencer --o antes, si todo el
dinero ya cerro-- llega T1 y corren las 24 horas del consultor. Su
visto bueno manda la factura a Odoo; finanzas aprueba y cierra.

Solo el eventual. El implantado corta a mes: test_cierre_mes.py.
"""
from datetime import timedelta

from ayudas import (asignar, cotizar_y_autorizar, crear_servicio, depositar,
                    devolver, ejecutar_jornada, jornada, manana)

PUNTO = {"origen_direccion": "Aeropuerto Benito Juárez, T2",
         "origen_lat": "19.4270", "origen_lon": "-99.1677",
         "geocerca_metros": 250}
H24 = timedelta(hours=24)
MOTIVO = "El equipo se quedó sin batería; confirmado por teléfono"


def _armar(cliente, sesion, datos, dias=1, offset=1300, viaticos=True,
           cotizado=True):
    """Un eventual de `dias` dias con Juan, su unidad y, si se pide, un
    viatico por dia que todavia no sale de la caja."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"],
                 **PUNTO) for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    if cotizado:
        cotizar_y_autorizar(
            cliente, h, servicio,
            datos["perfiles"]["conductor_seguridad"]["id"],
            datos["categorias"]["suv_blindada"]["id"])
    juan = datos["personal"]["Juan Ramirez"]["id"]
    vids = []
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"], persona_id=juan,
                vehiculo_id=datos["suburban"]["id"])
        if viaticos:
            v = cliente.post("/viaticos/asignar", headers=h, json={
                "jornada_id": j["id"], "persona_id": juan,
                "conceptos": [{"concepto": "alimentos", "monto": "900",
                               "origen": "tabulador"}]})
            assert v.status_code in (200, 201), v.text
            vids.append(v.json()["id"])
    return servicio, vids, juan


def _cierre(servicio_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()
        if not c:
            return None
        return {"id": c.id, "estatus": c.estatus.value,
                "abierto_en": c.abierto_en,
                "comprobacion_hasta": c.comprobacion_hasta,
                "visto_bueno_desde": c.visto_bueno_desde,
                "limite": c.limite_consultor, "motivo": c.motivo_apertura}


def _limites(vids):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return [db.get(m.AsignacionViatico, v).limite_comprobacion
                for v in vids]


def _dia(jornada_id):
    """(fin_real, cerrada_a_mano_en, estatus) del dia."""
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        j = db.get(m.Jornada, jornada_id)
        return j.fin_real, j.cerrada_a_mano_en, j.estatus.value


def _estatus(cliente, sesion, servicio_id):
    r = cliente.get(f"/servicios/{servicio_id}", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()["estatus"]


def _avanzar(cierre_id, ahora):
    """Lo que hace la tarea de cada cinco minutos, a una hora dada."""
    from app import cierre as motor
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        movio = motor.avanzar(db, db.get(m.Cierre, cierre_id), ahora)
        db.commit()
        return movio


def _ahora_del(servicio_id):
    from app import models as m
    from app import reloj
    from app.db import SessionLocal
    with SessionLocal() as db:
        return reloj.ahora_del_servicio(db, db.get(m.Servicio, servicio_id))


def _sacar_dinero(cliente, sesion, servicio, vids, juan):
    """El viatico sale de la caja: se pide y finanzas lo deposita."""
    for vid in vids:
        r = cliente.post(f"/viaticos/{vid}/solicitar-transferencia",
                         headers=sesion("consultor"))
        assert r.status_code in (200, 201), r.text
    r = depositar(cliente, sesion("finanzas"),
                  servicio["equipos"][0]["id"], juan,
                  referencia=f"SPEI-2R-{servicio['id']}")
    assert r.status_code in (200, 201), r.text


def _devolver_y_cerrar(cliente, sesion, vid, monto="900"):
    r = devolver(cliente, sesion("finanzas"), vid, monto,
                 referencia=f"SPEI-DEV-2R-{vid}")
    assert r.status_code in (200, 201), r.text
    r = cliente.post(f"/viaticos/{vid}/cerrar", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["resultado"] == "cerrado", r.json()


# ------------------------------------------------------------ T0 y T0 + 24

def test_los_viaticos_vencen_juntos_al_terminar_el_servicio(cliente, sesion,
                                                            datos):
    """Tres dias, tres viaticos, un solo limite: T0 + 24 h. Cerrar los
    dias anteriores ya no abre plazo a nadie."""
    servicio, vids, _ = _armar(cliente, sesion, datos, dias=3, offset=1300)
    dias = servicio["equipos"][0]["jornadas"]
    hj = sesion("juan")

    for d in dias[:2]:
        r = ejecutar_jornada(cliente, hj, d)
        assert r.status_code == 200, r.text
    assert _limites(vids) == [None, None, None], \
        "el plazo no corre hasta el termino general"
    assert _cierre(servicio["id"]) is None
    assert _estatus(cliente, sesion, servicio["id"]) == "en_curso"

    r = ejecutar_jornada(cliente, hj, dias[2])
    assert r.status_code == 200, r.text
    t0, _, _ = _dia(dias[2]["id"])
    assert _limites(vids) == [t0 + H24] * 3, "todos vencen a la misma hora"

    c = _cierre(servicio["id"])
    assert c["estatus"] == "abierto" and c["motivo"] == "termino"
    assert c["abierto_en"] == t0
    assert c["comprobacion_hasta"] == t0 + H24
    assert c["limite"] == t0 + 2 * H24, "provisional: T1 todavia no llega"
    assert c["visto_bueno_desde"] is None
    assert _estatus(cliente, sesion, servicio["id"]) == "terminado"

    # La pantalla lo sabe: fase de comprobacion, con el dinero afuera.
    r = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["fase"] == "comprobacion"
    assert r.json()["viaticos_abiertos"] == 3


def test_el_reloj_del_sistema_abre_el_visto_bueno_a_las_24_horas(cliente,
                                                                sesion, datos):
    """A las 23 h no pasa nada y el consultor no puede adelantarse; a las
    24 el cierre queda sin visto bueno, el servicio tambien, y el
    consultor tiene hasta T1 + 24 h."""
    servicio, vids, _ = _armar(cliente, sesion, datos, offset=1305)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    t0, _, _ = _dia(d["id"])
    c = _cierre(servicio["id"])

    assert _avanzar(c["id"], t0 + timedelta(hours=23)) is False
    assert _cierre(servicio["id"])["estatus"] == "abierto"
    assert _estatus(cliente, sesion, servicio["id"]) == "terminado"

    envio = cliente.post(f"/cierre/{c['id']}/enviar-finanzas",
                         headers=sesion("consultor"),
                         params={"ahora": (t0 + timedelta(hours=23)).isoformat()})
    assert envio.status_code == 409, envio.text
    assert "comprobacion" in envio.json()["detail"]["mensaje"].lower()
    assert envio.json()["detail"]["hasta"] == (t0 + H24).isoformat()

    assert _avanzar(c["id"], t0 + H24) is True
    c = _cierre(servicio["id"])
    assert c["estatus"] == "sin_visto_bueno"
    assert c["visto_bueno_desde"] == t0 + H24
    assert c["limite"] == t0 + 2 * H24
    assert _estatus(cliente, sesion, servicio["id"]) == "sin_visto_bueno"
    # Y no se mueve dos veces.
    assert _avanzar(c["id"], t0 + 3 * H24) is False

    r = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                    headers=sesion("consultor"))
    assert r.json()["fase"] == "sin_visto_bueno"


def test_el_barrido_mueve_solo_lo_que_llego_a_su_hora(cliente, sesion, datos):
    """La tarea de Celery recorre todos los cierres abiertos y mueve los
    que ya llegaron a T1; los demas siguen esperando."""
    from app import cierre as motor
    from app.db import SessionLocal

    temprano, _, _ = _armar(cliente, sesion, datos, offset=1310)
    tarde, _, _ = _armar(cliente, sesion, datos, offset=1312)
    for s in (temprano, tarde):
        d = s["equipos"][0]["jornadas"][0]
        assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    t0_temprano = _cierre(temprano["id"])["abierto_en"]

    with SessionLocal() as db:
        movidos = motor.avanzar_cierres(db, t0_temprano + H24)
    assert temprano["folio"] in movidos
    assert tarde["folio"] not in movidos
    assert _cierre(temprano["id"])["estatus"] == "sin_visto_bueno"
    assert _cierre(tarde["id"])["estatus"] == "abierto"


def test_con_todo_el_dinero_cerrado_el_consultor_arranca_antes(cliente, sesion,
                                                              datos):
    """Si todos los viaticos ya cerraron, no hay nada que esperar: T1 es
    ese momento y el consultor tiene 24 h desde ahi."""
    servicio, vids, juan = _armar(cliente, sesion, datos, offset=1315)
    _sacar_dinero(cliente, sesion, servicio, vids, juan)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    t0, _, _ = _dia(d["id"])
    c = _cierre(servicio["id"])

    # Con el dinero afuera, a las dos horas no se mueve.
    assert _avanzar(c["id"], t0 + timedelta(hours=2)) is False

    _devolver_y_cerrar(cliente, sesion, vids[0])
    assert _avanzar(c["id"], t0 + timedelta(hours=2)) is True
    c = _cierre(servicio["id"])
    assert c["visto_bueno_desde"] == t0 + timedelta(hours=2)
    assert c["limite"] == t0 + timedelta(hours=26)


# ------------------------------------------------------------ el visto bueno

def test_el_visto_bueno_manda_a_facturar_y_finanzas_cierra(cliente, sesion,
                                                          datos, monkeypatch):
    """Sin viaticos, el consultor arranca de inmediato. Su visto bueno
    pone el servicio en facturacion y manda la factura --aqui sin Odoo,
    asi que queda por facturar con el error a la vista--. Finanzas
    aprueba y el servicio queda cerrado."""
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    servicio, _, _ = _armar(cliente, sesion, datos, offset=1320, viaticos=False)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    c = _cierre(servicio["id"])
    h = sesion("consultor")

    envio = cliente.post(f"/cierre/{c['id']}/enviar-finanzas", headers=h)
    assert envio.status_code == 200, envio.text
    assert envio.json()["dentro_de_plazo"] is True
    assert envio.json()["factura"]["resultado"] == "sin conexion"
    assert _estatus(cliente, sesion, servicio["id"]) == "en_facturacion"
    c = _cierre(servicio["id"])
    assert c["estatus"] == "enviado_finanzas"
    assert c["visto_bueno_desde"] is not None, "T1 llego solo: no habia dinero"
    assert c["limite"] == c["visto_bueno_desde"] + H24

    # Enviado no se envia dos veces.
    otra = cliente.post(f"/cierre/{c['id']}/enviar-finanzas", headers=h)
    assert otra.status_code == 409, otra.text

    # En la bandeja de finanzas, esperando Odoo.
    bandeja = cliente.get("/cierre/por-facturar", headers=sesion("finanzas"))
    suyo = next(x for x in bandeja.json()["por_facturar"]
                if x["cierre_id"] == c["id"])
    assert suyo["estatus"] == "enviado_finanzas" and suyo["error"]

    r = cliente.post(f"/cierre/{c['id']}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert _estatus(cliente, sesion, servicio["id"]) == "cerrado"
    assert _cierre(servicio["id"])["estatus"] == "aprobado"


def test_finanzas_devuelve_y_el_servicio_regresa_a_sin_visto_bueno(cliente,
                                                                  sesion, datos,
                                                                  monkeypatch):
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    servicio, _, _ = _armar(cliente, sesion, datos, offset=1322, viaticos=False)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    c = _cierre(servicio["id"])
    h = sesion("consultor")
    assert cliente.post(f"/cierre/{c['id']}/enviar-finanzas",
                        headers=h).status_code == 200

    r = cliente.post(f"/cierre/{c['id']}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "Falta el respaldo de las horas extra"})
    assert r.status_code == 200, r.text
    assert _estatus(cliente, sesion, servicio["id"]) == "sin_visto_bueno"

    # El consultor lo vuelve a mandar.
    r = cliente.post(f"/cierre/{c['id']}/enviar-finanzas", headers=h)
    assert r.status_code == 200, r.text
    assert _estatus(cliente, sesion, servicio["id"]) == "en_facturacion"


# ------------------------------------------------------------ dias firmados tarde

def test_un_dia_firmado_tarde_no_nace_vencido(cliente, sesion, datos):
    """La central cierra a mano un dia de hace tres dias: T0 es la firma,
    no la hora de termino que asento, y el plazo nace entero."""
    servicio, vids, _ = _armar(cliente, sesion, datos, offset=-6,
                               cotizado=False)
    d = servicio["equipos"][0]["jornadas"][0]
    r = cliente.post(f"/operacion/jornadas/{d['id']}/cerrar-a-mano",
                     headers=sesion("central"), json={"justificacion": MOTIVO})
    assert r.status_code == 200, r.text

    fin_real, firmado, _ = _dia(d["id"])
    assert firmado > fin_real + timedelta(days=5)
    c = _cierre(servicio["id"])
    assert c["abierto_en"] == firmado
    assert c["comprobacion_hasta"] == firmado + H24
    assert _limites(vids) == [firmado + H24]


# ------------------------------------------------------------ reabrir

def test_reabrir_antes_del_visto_bueno_deshace_el_termino(cliente, sesion,
                                                          datos):
    """El cierre se borra con sus plazos y el servicio vuelve a la calle.
    Al cerrar el dia otra vez nace un T0 nuevo."""
    servicio, vids, _ = _armar(cliente, sesion, datos, offset=-8,
                               cotizado=False)
    d = servicio["equipos"][0]["jornadas"][0]
    hc = sesion("central")
    r = cliente.post(f"/operacion/jornadas/{d['id']}/cerrar-a-mano",
                     headers=hc, json={"justificacion": MOTIVO})
    assert r.status_code == 200, r.text
    assert _cierre(servicio["id"]) is not None

    r = cliente.post(f"/operacion/jornadas/{d['id']}/reabrir", headers=hc,
                     json={"justificacion": "Me equivoque de jornada al cerrar"})
    assert r.status_code == 200, r.text
    assert _cierre(servicio["id"]) is None, "el termino se deshizo"
    assert _limites(vids) == [None], "y con el, el plazo del personal"
    assert _estatus(cliente, sesion, servicio["id"]) in ("asignado", "planeado")

    r = cliente.post(f"/operacion/jornadas/{d['id']}/cerrar-a-mano",
                     headers=hc, json={"justificacion": MOTIVO})
    assert r.status_code == 200, r.text
    c = _cierre(servicio["id"])
    assert c and c["estatus"] == "abierto"
    assert _limites(vids) == [c["comprobacion_hasta"]]
    assert _estatus(cliente, sesion, servicio["id"]) == "terminado"


def test_con_el_visto_bueno_dado_ya_no_se_reabre(cliente, sesion, datos,
                                                monkeypatch):
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    servicio, _, _ = _armar(cliente, sesion, datos, offset=1325, viaticos=False)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    c = _cierre(servicio["id"])
    assert cliente.post(f"/cierre/{c['id']}/enviar-finanzas",
                        headers=sesion("consultor")).status_code == 200

    r = cliente.post(f"/operacion/jornadas/{d['id']}/reabrir",
                     headers=sesion("central"),
                     json={"justificacion": "Me equivoque de jornada al cerrar"})
    assert r.status_code == 409, r.text
    assert "visto bueno" in r.json()["detail"]["mensaje"]
    assert _estatus(cliente, sesion, servicio["id"]) == "en_facturacion"


# ------------------------------------------------------------ cancelar

def test_cancelar_con_dinero_afuera_arranca_los_relojes(cliente, sesion, datos):
    """La cancelacion es un termino: T0 es ahora, el viatico que salio
    recibe su plazo, y cuando vuelve el dinero el consultor tiene sus
    24 h para revisar la cancelacion. El servicio se queda cancelado."""
    servicio, vids, juan = _armar(cliente, sesion, datos, offset=1330)
    _sacar_dinero(cliente, sesion, servicio, vids, juan)
    antes = _ahora_del(servicio["id"])

    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     headers=sesion("consultor"),
                     json={"motivo": "el cliente canceló el viaje"})
    assert r.status_code == 200, r.text
    assert len(r.json()["viaticos_por_devolver"]) == 1
    assert _estatus(cliente, sesion, servicio["id"]) == "cancelado"

    c = _cierre(servicio["id"])
    assert c and c["motivo"] == "cancelacion"
    assert timedelta(0) <= c["abierto_en"] - antes < timedelta(minutes=5)
    assert c["comprobacion_hasta"] == c["abierto_en"] + H24
    assert _limites(vids) == [c["comprobacion_hasta"]]

    # Con el dinero afuera, el consultor espera.
    assert _avanzar(c["id"], c["abierto_en"] + timedelta(hours=1)) is False

    _devolver_y_cerrar(cliente, sesion, vids[0])
    assert _avanzar(c["id"], c["abierto_en"] + timedelta(hours=1)) is True
    assert _cierre(servicio["id"])["estatus"] == "sin_visto_bueno"
    assert _estatus(cliente, sesion, servicio["id"]) == "cancelado", \
        "cancelado se queda cancelado: su rastro es el cierre"


def test_cancelar_sin_nada_que_cerrar_no_abre_relojes(cliente, sesion, datos):
    """Sin dinero afuera ni dias trabajados no hay nada que revisar."""
    servicio, vids, _ = _armar(cliente, sesion, datos, offset=1335)
    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     headers=sesion("consultor"),
                     json={"motivo": "el cliente canceló el viaje"})
    assert r.status_code == 200, r.text
    assert _cierre(servicio["id"]) is None
    assert _limites(vids) == [None], "el viatico que no salio se cancelo sin plazo"


def test_un_servicio_terminado_ya_no_se_cancela(cliente, sesion, datos):
    """Terminado es terminado: el termino general ya corrio y con el los
    relojes. Lo que haya que ajustar va por la revision del cierre."""
    servicio, _, _ = _armar(cliente, sesion, datos, offset=1340, viaticos=False)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     headers=sesion("consultor"), json={"motivo": "ya no"})
    assert r.status_code == 409, r.text

# -*- coding: utf-8 -*-
"""Seccion 98: el dinero y los dias trabajados.

Lo que salio de la revision del 28 de septiembre y no necesitaba
decision de nadie: lo que ya se trabajo se queda, el dinero se cuenta
por lo que finanzas confirmo, y cada camino que cancela un viatico
cancela tambien su solicitud.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, depositar, devolver, ejecutar_jornada,
                    jornada, manana, marcar, revisar_unidad, rol_por_omision)


# ---------------------------------------------------------------- decorado

def _servicio(cliente, sesion, datos, dias=2, offset=1, quien="Juan Ramirez",
              cotizado=False):
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"])
         for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    if cotizado:
        cotizar_y_autorizar(
            cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
            datos["categorias"]["suv_blindada"]["id"])
    persona = datos["personal"][quien]["id"]
    for j in servicio["equipos"][0]["jornadas"]:
        for r in asignar(cliente, h, j["id"], persona_id=persona,
                         vehiculo_id=datos["suburban"]["id"]):
            assert r.status_code == 200, r.text
        configurar_origen(cliente, h, j["id"])
    return servicio, servicio["equipos"][0]["id"], persona


def _fijar(cliente, sesion, equipo_id, persona, monto):
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                     json={"persona_id": persona, "monto": str(monto)},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


def _solicitar(cliente, sesion, equipo_id, persona=None):
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar",
                     json={"persona_id": persona}, headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


def _bandeja(cliente, sesion, folio):
    b = cliente.get("/viaticos/finanzas/bandeja",
                    headers=sesion("finanzas")).json()
    return [f for p in b["paises"] for f in p["depositos"] if f["folio"] == folio]


def _solicitudes(viatico_ids):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return [(s.asignacion_id, s.estatus.value, str(s.monto),
                 s.cancelacion_pedida_en is not None) for s in
                db.query(m.SolicitudTransferencia)
                .filter(m.SolicitudTransferencia.asignacion_id.in_(viatico_ids))
                .order_by(m.SolicitudTransferencia.id).all()]


def _enviada(viatico_ids):
    """La instruccion ya esta en manos de finanzas (`enviada`). Desde la
    seccion 105 no hay barrido que la ponga --la pondra la conexion con
    Odoo--, asi que la prueba la escribe directo en la base."""
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        for s in (db.query(m.SolicitudTransferencia)
                  .filter(m.SolicitudTransferencia.asignacion_id.in_(viatico_ids),
                          m.SolicitudTransferencia.estatus
                          == m.EstatusTransferencia.PENDIENTE).all()):
            s.estatus = m.EstatusTransferencia.ENVIADA
        db.commit()


def _viaticos(equipo_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        filas = (db.query(m.AsignacionViatico)
                 .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
                 .filter(m.Jornada.equipo_id == equipo_id)
                 .order_by(m.Jornada.fecha).all())
        return [{"id": v.id, "estatus": v.estatus.value, "persona": v.persona_id,
                 "jornada": v.jornada_id, "total": str(v.monto_total)}
                for v in filas]


def _depositar_lo_visto(cliente, sesion, equipo_id, persona_id, solicitudes,
                        referencia="SPEI-000001"):
    """Como lo hace la consola: con las solicitudes que finanzas vio."""
    import io
    from ayudas import PIXEL
    return cliente.post(
        "/viaticos/finanzas/depositar",
        data={"equipo_id": str(equipo_id), "persona_id": str(persona_id),
              "referencia": referencia,
              "solicitudes_ids": ",".join(str(x) for x in solicitudes)},
        files={"archivo": ("comprobante.png", io.BytesIO(PIXEL), "image/png")},
        headers=sesion("finanzas"))


def _app(cliente, sesion, folio, quien="juan"):
    app = cliente.get("/campo/mis-viaticos", headers=sesion(quien)).json()
    for lista in ("servicios", "cerrados"):
        for s in app[lista]:
            if s["folio"] == folio:
                return lista, s
    return None, None


def _asignaciones(cliente, sesion, equipo_id):
    r = cliente.get(f"/servicios/equipos/{equipo_id}/asignaciones",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()


def _jornada(jornada_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        j = db.get(m.Jornada, jornada_id)
        if j is None:
            return None
        return {"estatus": j.estatus.value,
                "personal": sorted(a.persona_id for a in j.personal),
                "vehiculos": sorted(a.vehiculo_id for a in j.vehiculos),
                "hitos": db.query(m.Hito).filter_by(jornada_id=j.id).count()}


# ================================================== los dias trabajados

def test_quitar_a_una_persona_deja_los_dias_que_ya_trabajo(cliente, sesion, datos):
    """Se quita de los dias pendientes; el lunes que ya trabajo se queda
    con su asignacion, para que la nomina se lo pague y el cierre lo
    facture. Sin dias pendientes, lo que hay es el cambio por
    contingencia."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=2,
                                          offset=900)
    dias = servicio["equipos"][0]["jornadas"]
    fin = ejecutar_jornada(cliente, sesion("juan"), dias[0])
    assert fin.status_code == 200, fin.text

    antes = _asignaciones(cliente, sesion, equipo_id)
    assert antes["dias"] == 2 and antes["dias_pendientes"] == 1
    ficha = next(p for p in antes["personal"] if p["persona_id"] == juan)
    assert ficha["dias"] == 2 and ficha["dias_pendientes"] == 1

    r = cliente.delete(f"/servicios/equipos/{equipo_id}/personal/{juan}",
                       headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["dias"] == 1 and r.json()["dias_trabajados"] == 1

    assert _jornada(dias[0]["id"])["personal"] == [juan]
    assert _jornada(dias[1]["id"])["personal"] == []

    # Ya no tiene dias pendientes: no se quita, se releva.
    r = cliente.delete(f"/servicios/equipos/{equipo_id}/personal/{juan}",
                       headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert "contingencia" in r.json()["detail"]["que_hacer"]


def test_quitar_una_unidad_deja_los_dias_que_ya_rodo(cliente, sesion, datos):
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=2,
                                          offset=900)
    dias = servicio["equipos"][0]["jornadas"]
    assert ejecutar_jornada(cliente, sesion("juan"), dias[0]).status_code == 200
    suburban = datos["suburban"]["id"]

    r = cliente.delete(f"/servicios/equipos/{equipo_id}/vehiculos/{suburban}",
                       headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["dias"] == 1 and r.json()["dias_trabajados"] == 1
    assert _jornada(dias[0]["id"])["vehiculos"] == [suburban]
    assert _jornada(dias[1]["id"])["vehiculos"] == []

    r = cliente.delete(f"/servicios/equipos/{equipo_id}/vehiculos/{suburban}",
                       headers=sesion("consultor"))
    assert r.status_code == 409, r.text


def test_quitar_a_una_persona_con_deposito_pedido_se_niega(cliente, sesion, datos):
    """Con la solicitud viva no se quita: primero se cancela la solicitud.
    Con el dinero ya afuera tampoco: eso es un reemplazo."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1)
    _fijar(cliente, sesion, equipo_id, juan, 900)
    _solicitar(cliente, sesion, equipo_id)
    vid = _viaticos(equipo_id)[0]["id"]

    r = cliente.delete(f"/servicios/equipos/{equipo_id}/personal/{juan}",
                       headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert "cancela la solicitud" in r.json()["detail"]["mensaje"]
    assert _solicitudes([vid])[0][1] == "pendiente"

    # Ya en manos de finanzas: igual.
    _enviada([vid])
    r = cliente.delete(f"/servicios/equipos/{equipo_id}/personal/{juan}",
                       headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert _solicitudes([vid])[0][1] == "enviada"

    # Y finanzas vuelve del banco con donde registrarlo.
    dep = depositar(cliente, sesion("finanzas"), equipo_id, juan)
    assert dep.status_code == 200, dep.text
    r = cliente.delete(f"/servicios/equipos/{equipo_id}/personal/{juan}",
                       headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert "recibio viaticos" in r.json()["detail"]["mensaje"]


def test_quitar_un_dia_trabajado_lo_cancela_con_sus_marcas(cliente, sesion, datos):
    """El dia terminado no se borra: se cancela y conserva sus marcas.
    Borrarlo se llevaba los hitos, las horas y el pago de quien lo
    trabajo."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=2,
                                          offset=900)
    dias = servicio["equipos"][0]["jornadas"]
    assert ejecutar_jornada(cliente, sesion("juan"), dias[0]).status_code == 200
    antes = _jornada(dias[0]["id"])
    assert antes["estatus"] == "terminada" and antes["hitos"] >= 3

    r = cliente.delete(f"/servicios/jornadas/{dias[0]['id']}",
                       headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["resultado"] == "dia cancelado"
    assert r.json()["borrado"] is False
    assert "ya se habia trabajado" in r.json()["nota"]

    despues = _jornada(dias[0]["id"])
    assert despues is not None, "el dia trabajado se borro"
    assert despues["estatus"] == "cancelada"
    assert despues["hitos"] == antes["hitos"]
    assert despues["personal"] == [juan]

    # Cancelado no se vuelve a quitar, ni se le agregan marcas.
    r = cliente.delete(f"/servicios/jornadas/{dias[0]['id']}",
                       headers=sesion("consultor"))
    assert r.status_code == 409, r.text


def test_un_dia_en_la_calle_no_se_quita(cliente, sesion, datos):
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=2,
                                          offset=0)
    dias = servicio["equipos"][0]["jornadas"]
    inicio = datetime.fromisoformat(dias[0]["inicio_programado"])
    r = marcar(cliente, sesion("juan"), dias[0]["id"], "llegada_origen",
               inicio - timedelta(minutes=10))
    assert r.status_code == 200, r.text
    assert _jornada(dias[0]["id"])["estatus"] == "arribado"

    r = cliente.delete(f"/servicios/jornadas/{dias[0]['id']}",
                       headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert "en la calle" in r.json()["detail"]["mensaje"]


def test_una_marca_en_un_dia_cancelado_se_niega(cliente, sesion, datos):
    """El servicio se cancela; la app ya no lo ensena, pero una marca que
    llegue tarde no puede revivir el dia."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1,
                                          offset=0)
    j = servicio["equipos"][0]["jornadas"][0]
    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "Cancelo el cliente"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert _jornada(j["id"])["estatus"] == "cancelada"

    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               datetime.now() - timedelta(minutes=2))
    assert r.status_code == 409, r.text
    assert _jornada(j["id"])["estatus"] == "cancelada"


def test_un_servicio_que_ya_no_se_arma_no_se_arma(cliente, sesion, datos):
    """Cancelado: ni gente, ni unidades, ni dias nuevos, ni fechas."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1,
                                          offset=3)
    j = servicio["equipos"][0]["jornadas"][0]
    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "Cancelo el cliente"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    h = sesion("consultor")
    luis = datos["personal"]["Luis Mendoza"]["id"]

    r = asignar(cliente, h, j["id"], persona_id=luis)[0]
    assert r.status_code == 409, r.text
    r = cliente.post(f"/servicios/equipos/{equipo_id}/asignar-personal",
                     json={"persona_id": luis, "forzar": True}, headers=h)
    assert r.status_code == 409, r.text
    r = cliente.post(f"/servicios/equipos/{equipo_id}/jornadas",
                     json={"fecha": str(manana(4)),
                           "modalidad_id": datos["modalidades"]["full_day"]["id"]},
                     headers=h)
    assert r.status_code == 409, r.text
    r = cliente.patch(f"/servicios/jornadas/{j['id']}",
                      json={"fecha": str(manana(5))}, headers=h)
    assert r.status_code == 409, r.text


def test_un_dia_pagado_no_se_quita(cliente, sesion, datos):
    """Ya se mando a finanzas y ya se pago: el dia no se toca desde el
    armado, y su renglon de nomina no se queda sin dia."""
    from test_ajustes import _dia_pagado
    from app import models as m
    from app.db import SessionLocal

    servicio, j, juan, pais_id = _dia_pagado(cliente, sesion, datos, offset=300)
    r = cliente.delete(f"/servicios/jornadas/{j['id']}",
                       headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    assert _jornada(j["id"]) is not None
    with SessionLocal() as db:
        huerfanos = (db.query(m.ConceptoNomina)
                     .filter(m.ConceptoNomina.jornada_id.is_(None),
                             m.ConceptoNomina.ajuste_id.is_(None),
                             m.ConceptoNomina.saldo_en_contra.is_(False)).count())
    assert huerfanos == 0


def test_asignar_al_equipo_a_media_semana_solo_cubre_lo_pendiente(
        cliente, sesion, datos):
    """Luis entra el martes: no se le mete al lunes que Juan ya trabajo,
    porque ese dia se le pagaria y se le cobraria al cliente."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=3,
                                          offset=900)
    dias = servicio["equipos"][0]["jornadas"]
    assert ejecutar_jornada(cliente, sesion("juan"), dias[0]).status_code == 200
    luis = datos["personal"]["Luis Mendoza"]["id"]

    r = cliente.post(f"/servicios/equipos/{equipo_id}/asignar-personal",
                     json={"persona_id": luis, "forzar": True,
                           "rol_id": rol_por_omision(cliente, sesion("consultor"))},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["dias"] == 2

    assert _jornada(dias[0]["id"])["personal"] == [juan]
    assert sorted(_jornada(dias[1]["id"])["personal"]) == sorted([juan, luis])

    fichas = _asignaciones(cliente, sesion, equipo_id)
    de_luis = next(p for p in fichas["personal"] if p["persona_id"] == luis)
    assert de_luis["dias"] == 2 and de_luis["dias_pendientes"] == 2
    de_juan = next(p for p in fichas["personal"] if p["persona_id"] == juan)
    assert de_juan["dias"] == 3 and de_juan["dias_pendientes"] == 2


# ================================================== el dinero que se cancela

def test_cancelar_el_servicio_cancela_la_solicitud_pendiente(cliente, sesion, datos):
    """Antes el viatico quedaba cancelado y la solicitud viva: finanzas
    la seguia viendo como dinero por pagar, sin forma de sacarla."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=2)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    _solicitar(cliente, sesion, equipo_id)
    assert len(_bandeja(cliente, sesion, servicio["folio"])) == 1

    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "El cliente cancelo"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["depositos_pedidos_a_finanzas"] == 0

    vs = _viaticos(equipo_id)
    assert all(v["estatus"] == "cancelado" for v in vs), vs
    assert all(s[1] == "cancelada" for s in _solicitudes([v["id"] for v in vs]))
    assert _bandeja(cliente, sesion, servicio["folio"]) == []
    corte = cliente.get("/viaticos/finanzas/corte",
                        headers=sesion("finanzas")).json()
    mx = next((p for p in corte["paises"] if p["codigo"] == "MX"), None)
    assert mx is None or Decimal(str(mx["comprometido"])) == Decimal("0")


def test_cancelar_con_el_deposito_ya_enviado_lo_pide_a_finanzas(
        cliente, sesion, datos):
    """Lo que ya esta con finanzas no se cancela solo: queda pedido, en
    la bandeja, para que finanzas lo cierre antes de ir al banco."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    _solicitar(cliente, sesion, equipo_id)
    vid = _viaticos(equipo_id)[0]["id"]
    _enviada([vid])

    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "El cliente cancelo"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["depositos_pedidos_a_finanzas"] == 1
    assert "en camino" in r.json()["nota"]
    assert _solicitudes([vid]) == [(vid, "enviada", "1000.00", True)]
    fila = _bandeja(cliente, sesion, servicio["folio"])
    assert fila and fila[0]["cancelacion_pedida"] is True

    # Finanzas lo cierra desde su bandeja aunque el dia este cancelado.
    can = cliente.post(f"/viaticos/finanzas/transferencias/cancelar"
                       f"?equipo_id={equipo_id}&persona_id={juan}",
                       headers=sesion("finanzas"))
    assert can.status_code == 200, can.text
    assert _solicitudes([vid])[0][1] == "cancelada"
    assert _bandeja(cliente, sesion, servicio["folio"]) == []


def test_quitar_un_dia_con_solicitud_pendiente_cuadra_el_deposito(
        cliente, sesion, datos):
    """Tres dias pedidos, se cae el tercero: finanzas ve 2,000 por dos
    dias y deposita 2,000. Antes veia 3,000 y registraba 2,000, y la
    solicitud del dia caido se quedaba pendiente para siempre."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=3)
    _fijar(cliente, sesion, equipo_id, juan, 3000)
    _solicitar(cliente, sesion, equipo_id)
    j3 = servicio["equipos"][0]["jornadas"][2]

    r = cliente.delete(f"/servicios/jornadas/{j3['id']}",
                       headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["borrado"] is False
    assert r.json()["pedidas_a_finanzas"] == 0

    fila = _bandeja(cliente, sesion, servicio["folio"])[0]
    assert Decimal(str(fila["monto"])) == Decimal("2000")
    assert fila["dias"] == 2

    dep = _depositar_lo_visto(cliente, sesion, equipo_id, juan, fila["solicitudes"])
    assert dep.status_code == 200, dep.text
    assert Decimal(str(dep.json()["monto"])) == Decimal("2000")
    assert dep.json()["sobre_cancelada"] is False
    assert _bandeja(cliente, sesion, servicio["folio"]) == []
    # Lo mismo otra vez --la respuesta se perdio-- no se registra doble.
    otra = _depositar_lo_visto(cliente, sesion, equipo_id, juan,
                               fila["solicitudes"], "SPEI-2")
    assert otra.status_code == 409, otra.text
    assert "ya se registro" in otra.json()["detail"]["mensaje"]


def test_el_deposito_que_salio_antes_de_quitar_el_dia_se_registra_entero(
        cliente, sesion, datos):
    """Finanzas vio 3,000 por tres dias y fue al banco. Mientras, el
    consultor quito el tercero. El deposito se registra como salio
    --3,000-- y los 1,000 del dia caido quedan marcados para que el
    consultor los aplique o los pida de vuelta."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=3)
    _fijar(cliente, sesion, equipo_id, juan, 3000)
    _solicitar(cliente, sesion, equipo_id)
    vistas = _bandeja(cliente, sesion, servicio["folio"])[0]["solicitudes"]
    assert len(vistas) == 3
    j3 = servicio["equipos"][0]["jornadas"][2]
    r = cliente.delete(f"/servicios/jornadas/{j3['id']}",
                       headers=sesion("consultor"))
    assert r.status_code == 200, r.text

    dep = _depositar_lo_visto(cliente, sesion, equipo_id, juan, vistas)
    assert dep.status_code == 200, dep.text
    assert Decimal(str(dep.json()["monto"])) == Decimal("3000")
    assert dep.json()["depositos"] == 3
    assert dep.json()["sobre_cancelada"] is True
    assert Decimal(str(dep.json()["monto_sobre_cancelada"])) == Decimal("1000")
    assert "1000" in dep.json()["nota"]
    panel = cliente.get(f"/viaticos/equipos/{equipo_id}",
                        headers=sesion("consultor")).json()
    assert Decimal(str(panel["total_tras_cancelar"])) == Decimal("1000")
    assert _bandeja(cliente, sesion, servicio["folio"]) == []


def test_el_reemplazo_cancela_la_solicitud_de_quien_sale(cliente, sesion, datos):
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=2, offset=3)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    _solicitar(cliente, sesion, equipo_id)
    j1 = servicio["equipos"][0]["jornadas"][0]

    r = cliente.post("/contingencia/reemplazos/personal", headers=sesion("consultor"),
                     json={"desde_jornada_id": j1["id"], "sale_persona_id": juan,
                           "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
                           "motivo": "Se enfermo"})
    assert r.status_code == 200, r.text
    cancelados = r.json()["viaticos"]["cancelados"]
    assert len(cancelados) == 2
    assert all(c["pedida_a_finanzas"] is False for c in cancelados)

    vs = _viaticos(equipo_id)
    assert all(v["estatus"] == "cancelado" for v in vs if v["persona"] == juan)
    assert all(s[1] == "cancelada" for s in _solicitudes([v["id"] for v in vs]))
    assert _bandeja(cliente, sesion, servicio["folio"]) == []


def test_solicitar_no_pide_los_dias_cancelados(cliente, sesion, datos):
    """Juan tenia 1,500 por tres dias; lo relevan desde el dia 2. Pedir
    el deposito del equipo pide solo su dia 1."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=3,
                                          offset=5)
    dias = servicio["equipos"][0]["jornadas"]
    _fijar(cliente, sesion, equipo_id, juan, 1500)
    r = cliente.post("/contingencia/reemplazos/personal", headers=sesion("consultor"),
                     json={"desde_jornada_id": dias[1]["id"], "sale_persona_id": juan,
                           "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
                           "motivo": "Se sintio mal"})
    assert r.status_code == 200, r.text
    assert len(r.json()["viaticos"]["cancelados"]) == 2

    _solicitar(cliente, sesion, equipo_id)
    fila = _bandeja(cliente, sesion, servicio["folio"])
    de_juan = [f for f in fila if f["persona_id"] == juan]
    assert de_juan and de_juan[0]["dias"] == 1, fila
    assert Decimal(str(de_juan[0]["monto"])) == Decimal("500")


def test_fijar_sobre_un_viatico_cancelado_lo_revive(cliente, sesion, datos):
    """Juan salio y regreso el dia 2: volver a fijarle dinero usa su
    viatico de ese dia, no deja uno cancelado con monto y otro nuevo."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=2, offset=3)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    dias = servicio["equipos"][0]["jornadas"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    r = cliente.post("/contingencia/reemplazos/personal", headers=sesion("consultor"),
                     json={"desde_jornada_id": dias[0]["id"], "sale_persona_id": juan,
                           "entra_persona_id": luis, "motivo": "Se enfermo"})
    assert r.status_code == 200, r.text
    r = cliente.post(f"/contingencia/reemplazos/{r.json()['reemplazo_id']}/regreso",
                     headers=sesion("consultor"), json={"desde": dias[1]["fecha"]})
    assert r.status_code == 200, r.text

    _fijar(cliente, sesion, equipo_id, juan, 800)
    _solicitar(cliente, sesion, equipo_id, juan)
    de_juan = [v for v in _viaticos(equipo_id) if v["persona"] == juan]
    vivos = [v for v in de_juan if v["estatus"] != "cancelado"]
    assert len(vivos) == 1 and vivos[0]["jornada"] == dias[1]["id"], de_juan
    assert Decimal(vivos[0]["total"]) == Decimal("800")
    sols = _solicitudes([v["id"] for v in de_juan])
    assert [s for s in sols if s[1] == "pendiente"] == [
        (vivos[0]["id"], "pendiente", "800.00", False)]
    fila = _bandeja(cliente, sesion, servicio["folio"])
    assert [f["dias"] for f in fila if f["persona_id"] == juan] == [1]
    lista, suyo = _app(cliente, sesion, servicio["folio"])
    assert lista == "servicios" and Decimal(str(suyo["por_depositar"])) == 800


# ================================================== lo que de verdad llego

def test_el_bolson_y_la_app_cuentan_solo_lo_depositado(cliente, sesion, datos):
    """Con un segundo deposito pedido, el viatico ya decia TRANSFERIDO y
    todo lo contaba como entregado. Se cuenta lo que finanzas confirmo."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1, offset=5)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    _solicitar(cliente, sesion, equipo_id)
    assert depositar(cliente, sesion("finanzas"), equipo_id, juan).status_code == 200
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona/agregar",
                     json={"persona_id": juan, "monto": "600"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    _solicitar(cliente, sesion, equipo_id)

    panel = cliente.get(f"/viaticos/equipos/{equipo_id}",
                        headers=sesion("consultor")).json()
    p = panel["personal"][0]
    assert Decimal(str(p["depositado"])) == Decimal("1000")
    assert Decimal(str(p["en_camino"])) == Decimal("600")

    from app import bolson, models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        v = db.query(m.AsignacionViatico).filter_by(persona_id=juan).first()
        c = bolson.cuenta(bolson.de_la_persona(db, v))
        vid = v.id
    assert c["depositado"] == Decimal("1000")
    assert c["por_depositar"] == Decimal("600")

    lista, suyo = _app(cliente, sesion, servicio["folio"])
    assert lista == "servicios"
    assert Decimal(str(suyo["entregado"])) == Decimal("1000")
    assert Decimal(str(suyo["por_depositar"])) == Decimal("600")
    assert Decimal(str(suyo["por_comprobar"])) == Decimal("1000")
    afuera = cliente.get("/viaticos/finanzas/por-comprobar",
                         headers=sesion("finanzas")).json()
    fila = next(x for p in afuera["paises"] for x in p["personas"]
                if x["folio"] == servicio["folio"])
    assert Decimal(str(fila["entregado"])) == Decimal("1000")

    # Con dinero por depositar no se cierra con descuento: se cancela lo
    # pendiente o se espera. Y lo que se descuenta es sobre lo que
    # recibio, no sobre el total.
    with SessionLocal() as db:
        vv = db.get(m.AsignacionViatico, vid)
        vv.limite_comprobacion = datetime.now() - timedelta(hours=1)
        db.commit()
    r = cliente.post(f"/viaticos/{vid}/bolson/cerrar-con-descuento",
                     json={"motivo": "No comprobo nada"}, headers=sesion("consultor"))
    assert r.status_code == 409, r.text
    vistas = _bandeja(cliente, sesion, servicio["folio"])[0]["solicitudes"]
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/cancelar-solicitud",
                     json={}, headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    # Cancelar una ronda posterior al deposito la quita de lo
    # autorizado: con dinero afuera ya no hay como corregirla con fijar.
    panel = cliente.get(f"/viaticos/equipos/{equipo_id}",
                        headers=sesion("consultor")).json()
    assert Decimal(str(panel["personal"][0]["asignado"])) == Decimal("1000")
    assert Decimal(str(panel["personal"][0]["por_solicitar"])) == Decimal("0")
    r = cliente.post(f"/viaticos/{vid}/bolson/cerrar-con-descuento",
                     json={"motivo": "No comprobo nada"}, headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["descontado_al_personal"])) == Decimal("1000")
    # Los 600 que finanzas alcanzo a ver ya no caen sobre un viatico
    # cerrado: nadie podria comprobarlos.
    dep = _depositar_lo_visto(cliente, sesion, equipo_id, juan, vistas, "SPEI-2")
    assert dep.status_code == 409, dep.text
    assert "cerrado" in dep.json()["detail"]["mensaje"]


def test_tras_el_descuento_la_app_no_pide_ni_acepta_devolucion(
        cliente, sesion, datos):
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1, offset=6)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    _solicitar(cliente, sesion, equipo_id)
    assert depositar(cliente, sesion("finanzas"), equipo_id, juan).status_code == 200
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        v = db.query(m.AsignacionViatico).filter_by(persona_id=juan).first()
        v.limite_comprobacion = datetime.now() - timedelta(hours=1)
        db.commit()
        vid = v.id
    r = cliente.post(f"/viaticos/{vid}/bolson/cerrar-con-descuento",
                     json={"motivo": "No comprobo nada"}, headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["descontado_al_personal"])) == Decimal("1000")

    lista, suyo = _app(cliente, sesion, servicio["folio"])
    assert lista == "cerrados", lista
    assert Decimal(str(suyo["por_comprobar"])) == Decimal("0")
    assert Decimal(str(suyo["por_devolver"])) == Decimal("0")
    d = cliente.post(f"/campo/viaticos/{vid}/devolucion", headers=sesion("juan"),
                     json={"monto": "1000", "referencia": "SPEI-DEV"})
    assert d.status_code == 409, d.text
    assert devolver(cliente, sesion("finanzas"), vid, "1000").status_code == 409


def test_un_adicional_negativo_se_rechaza(cliente, sesion, datos):
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1, offset=7)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    vid = _viaticos(equipo_id)[0]["id"]
    for monto in ("-400", "0"):
        r = cliente.post(f"/viaticos/{vid}/adicional", headers=sesion("consultor"),
                         json={"concepto": "otros", "monto": monto,
                               "descripcion": "ajuste"})
        assert r.status_code == 422, r.text


def test_solicitar_transferencia_por_viatico_pide_solo_lo_que_falta(
        cliente, sesion, datos):
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1, offset=8)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    _solicitar(cliente, sesion, equipo_id)
    assert depositar(cliente, sesion("finanzas"), equipo_id, juan).status_code == 200
    vid = _viaticos(equipo_id)[0]["id"]
    s = cliente.post(f"/viaticos/{vid}/solicitar-transferencia",
                     headers=sesion("consultor"))
    assert s.status_code == 409, s.text          # no hay nada que pedir
    r = cliente.post(f"/viaticos/{vid}/adicional", headers=sesion("consultor"),
                     json={"concepto": "otros", "monto": "200"})
    assert r.status_code == 200, r.text
    s = cliente.post(f"/viaticos/{vid}/solicitar-transferencia",
                     headers=sesion("consultor"))
    assert s.status_code == 200, s.text
    assert Decimal(str(s.json()["monto"])) == Decimal("200")
    assert _viaticos(equipo_id)[0]["estatus"] == "transferido"


def test_el_sobrante_del_bolson_cabe_en_una_sola_devolucion(cliente, sesion, datos):
    """Tres dias, 3,000; gasto 900 cada dia. Le sobran 300 del viaje y
    los regresa en un movimiento: la app lo acepta sobre cualquier dia."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=3, offset=9)
    _fijar(cliente, sesion, equipo_id, juan, 3000)
    _solicitar(cliente, sesion, equipo_id)
    assert depositar(cliente, sesion("finanzas"), equipo_id, juan).status_code == 200
    vs = _viaticos(equipo_id)
    for v in vs:
        r = cliente.post(f"/campo/viaticos/{v['id']}/comprobante", headers=sesion("juan"),
                         json={"concepto": "alimentos", "monto": "900",
                               "descripcion": "comida"})
        assert r.status_code == 200, r.text
    lista, suyo = _app(cliente, sesion, servicio["folio"])
    assert Decimal(str(suyo["por_comprobar"])) == Decimal("300")
    assert Decimal(str(suyo["por_devolver"])) == Decimal("300")

    d = cliente.post(f"/campo/viaticos/{vs[0]['id']}/devolucion", headers=sesion("juan"),
                     json={"monto": "300", "referencia": "SPEI-DEV"})
    assert d.status_code == 200, d.text
    lista, suyo = _app(cliente, sesion, servicio["folio"])
    assert Decimal(str(suyo["devolucion_en_revision"])) == Decimal("300")
    assert Decimal(str(suyo["por_devolver"])) == Decimal("0")
    # Mas de lo que sobra, no.
    d = cliente.post(f"/campo/viaticos/{vs[1]['id']}/devolucion", headers=sesion("juan"),
                     json={"monto": "100", "referencia": "SPEI-DEV-2"})
    assert d.status_code == 409, d.text


def test_ver_un_viatico_pide_permiso_y_no_solo_sesion(cliente, sesion, datos):
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1, offset=1)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    vid = _viaticos(equipo_id)[0]["id"]
    assert cliente.get(f"/viaticos/{vid}", headers=sesion("juan")).status_code == 200
    assert cliente.get(f"/viaticos/{vid}", headers=sesion("luis")).status_code == 403
    assert cliente.get(f"/viaticos/{vid}", headers=sesion("rrhh")).status_code == 403
    assert cliente.get(f"/viaticos/{vid}", headers=sesion("finanzas")).status_code == 200
    assert cliente.get(f"/viaticos/{vid}", headers=sesion("consultor")).status_code == 200


def test_el_comprobante_del_deposito_pide_sesion(cliente, sesion, datos):
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1, offset=1)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    _solicitar(cliente, sesion, equipo_id)
    dep = depositar(cliente, sesion("finanzas"), equipo_id, juan).json()
    ruta = f"/viaticos/depositos/{dep['deposito_id']}/comprobante"
    assert cliente.get(ruta).status_code == 401
    assert cliente.get(ruta, headers=sesion("finanzas")).status_code == 200
    assert cliente.get(ruta, headers=sesion("juan")).status_code == 200


def test_anular_un_deposito_cuyo_dinero_ya_regreso_se_niega(cliente, sesion, datos):
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1, offset=1)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    _solicitar(cliente, sesion, equipo_id)
    dep = depositar(cliente, sesion("finanzas"), equipo_id, juan).json()
    vid = _viaticos(equipo_id)[0]["id"]
    assert devolver(cliente, sesion("finanzas"), vid, "1000").status_code == 200
    r = cliente.post(f"/viaticos/depositos/{dep['deposito_id']}/anular",
                     data={"motivo": "Se registro mal"}, headers=sesion("finanzas"))
    assert r.status_code == 409, r.text
    assert _bandeja(cliente, sesion, servicio["folio"]) == []


# ================================================== el deposito registra lo que vio

def test_el_deposito_registra_lo_que_finanzas_vio_en_la_bandeja(
        cliente, sesion, datos):
    """Finanzas se va al banco con 1,000. Mientras, el consultor pide 500
    mas. El deposito registra 1,000; los 500 siguen en la bandeja."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1, offset=1)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    _solicitar(cliente, sesion, equipo_id)
    fila = _bandeja(cliente, sesion, servicio["folio"])[0]
    vistas = fila["solicitudes"]
    assert len(vistas) == 1

    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona/agregar",
                     json={"persona_id": juan, "monto": "500"},
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    _solicitar(cliente, sesion, equipo_id)

    dep = _depositar_lo_visto(cliente, sesion, equipo_id, juan, vistas, "SPEI-1")
    assert dep.status_code == 200, dep.text
    assert Decimal(str(dep.json()["monto"])) == Decimal("1000")
    lista, suyo = _app(cliente, sesion, servicio["folio"])
    assert Decimal(str(suyo["entregado"])) == Decimal("1000")
    assert Decimal(str(suyo["por_depositar"])) == Decimal("500")
    fila = _bandeja(cliente, sesion, servicio["folio"])
    assert fila and Decimal(str(fila[0]["monto"])) == Decimal("500")

    # Lo que vio y ya se pago no se vuelve a registrar: se le pide
    # recargar.
    dep = _depositar_lo_visto(cliente, sesion, equipo_id, juan,
                              vistas + fila[0]["solicitudes"], "SPEI-2")
    assert dep.status_code == 409, dep.text
    assert "ya se registro" in dep.json()["detail"]["mensaje"]
    assert dep.json()["detail"]["solicitudes"] == vistas


def test_la_misma_referencia_no_se_registra_dos_veces(cliente, sesion, datos):
    """El mismo formulario mandado dos veces --la respuesta se perdio--
    registraba dos depositos con la misma referencia del banco."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1, offset=1)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    _solicitar(cliente, sesion, equipo_id)
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/cancelar-solicitud",
                     json={}, headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    _fijar(cliente, sesion, equipo_id, juan, 800)
    _solicitar(cliente, sesion, equipo_id)
    primero = depositar(cliente, sesion("finanzas"), equipo_id, juan, "SPEI-1")
    assert primero.status_code == 200, primero.text
    assert Decimal(str(primero.json()["monto"])) == Decimal("800")
    segundo = depositar(cliente, sesion("finanzas"), equipo_id, juan, "SPEI-1")
    assert segundo.status_code == 409, segundo.text
    assert segundo.json()["detail"]["deposito_id"] == primero.json()["deposito_id"]
    lista, suyo = _app(cliente, sesion, servicio["folio"])
    assert [Decimal(str(d["monto"])) for d in suyo["depositos"]] == [Decimal("800")]


def test_el_deposito_sobre_una_solicitud_cancelada_entra_marcado(
        cliente, sesion, datos):
    """Finanzas vio la solicitud, fue al banco, y el consultor la cancelo
    mientras tanto: el deposito entra por la puerta de atras, marcado."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1, offset=1)
    _fijar(cliente, sesion, equipo_id, juan, 1000)
    _solicitar(cliente, sesion, equipo_id)
    vistas = _bandeja(cliente, sesion, servicio["folio"])[0]["solicitudes"]
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/cancelar-solicitud",
                     json={}, headers=sesion("consultor"))
    assert r.status_code == 200, r.text

    dep = _depositar_lo_visto(cliente, sesion, equipo_id, juan, vistas, "SPEI-TARDE")
    assert dep.status_code == 200, dep.text
    assert dep.json()["sobre_cancelada"] is True
    assert Decimal(str(dep.json()["monto"])) == Decimal("1000")


# ================================================== el cierre que finanzas regreso

def test_reabrir_con_el_cierre_regresado_lo_conserva(cliente, sesion, datos,
                                                     monkeypatch):
    """El cierre que finanzas regreso trae el primer visto bueno con su
    plazo y la factura anulada. Reabrir el dia para corregirlo no lo
    borra: se corrige y se vuelve a mandar con la misma historia."""
    from app import facturacion, models as m, reloj
    from app.db import SessionLocal
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")
    MOTIVO = "Se equivoco la hora de termino; confirmado por telefono"

    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=1,
                                          offset=-7, cotizado=True)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    h = sesion("consultor")

    with SessionLocal() as db:
        fila = db.query(m.Cierre).filter_by(servicio_id=servicio["id"]).first()
        cierre_id = fila.id
        ahora = reloj.ahora_del_servicio(db, fila.servicio)
        fila.abierto_en = ahora - timedelta(days=3)
        fila.comprobacion_hasta = ahora - timedelta(days=2)
        fila.limite_consultor = ahora - timedelta(days=1)
        db.commit()
    envio = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas", headers=h)
    assert envio.status_code == 200, envio.text
    assert envio.json()["dentro_de_plazo"] is False

    r = cliente.put(f"/cierre/{cierre_id}/factura-de-odoo", headers=sesion("finanzas"),
                    json={"folio": "INV/2026/00777", "fecha": manana(0).isoformat()})
    assert r.status_code == 200, r.text
    r = cliente.post(f"/cierre/{cierre_id}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "La hora de termino esta mal capturada"})
    assert r.status_code == 200, r.text

    r = cliente.post(f"/operacion/jornadas/{d['id']}/reabrir",
                     headers=sesion("central"), json={"justificacion": MOTIVO})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        c = db.get(m.Cierre, cierre_id)
        assert c is not None, "el cierre regresado se borro"
        assert c.estatus == m.EstatusCierre.DEVUELTO_A_OPERACION
        assert c.factura_anulada == "INV/2026/00777"
        assert c.dentro_de_plazo is False

    r = cliente.post(f"/operacion/jornadas/{d['id']}/cerrar-a-mano",
                     headers=sesion("central"), json={"justificacion": MOTIVO})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        cierres = db.query(m.Cierre).filter_by(servicio_id=servicio["id"]).all()
        assert [c.id for c in cierres] == [cierre_id]
        assert db.get(m.Servicio, servicio["id"]).estatus \
            == m.EstatusServicio.SIN_VISTO_BUENO

    envio = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas", headers=h)
    assert envio.status_code == 200, envio.text
    assert envio.json()["dentro_de_plazo"] is False
    with SessionLocal() as db:
        cuerpo = facturacion.armar(db, db.get(m.Cierre, cierre_id))
    assert cuerpo["sustituye_a"] == "INV/2026/00777"


# ================================================== la nomina

def test_horas_extra_sin_tarifa_de_hora_extra_detienen_el_corte(
        cliente, sesion, datos):
    """La celda vacia de hora extra es un dato que falta, no un cero."""
    from test_nominas import _con_visto_bueno
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
        _con_visto_bueno(cliente, sesion, datos, 410, horas_extra=2)
        r = cliente.post("/nomina/calcular", json={"pais_id": mx}, headers=f)
        assert r.status_code == 409, r.text
        faltan = r.json()["detail"]["sin_tarifa"]
        assert faltan and faltan[0]["falta"] == "hora extra"
    finally:
        cliente.put("/nomina/tabulador", headers=f, json={
            "pais_id": mx, "tipo_servicio": "eventual",
            "renglones": [{"perfil_id": conductor, "modalidad_id": full_day,
                           "monto": "700", "monto_hora_extra": "90"}]})


def test_pagar_dos_veces_al_mismo_tiempo_no_duplica_el_saldo(cliente, sesion,
                                                             datos):
    """Dos clics sobre "Marcar pagado" al mismo tiempo: uno paga y el
    otro ve que ya estaba pagada."""
    import threading
    from test_nominas import _calcular, _lunes
    from app import models as m
    from app import nomina as motor
    from app.db import SessionLocal

    f = sesion("finanzas")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    mx = datos["mx"]["id"]
    r = cliente.post("/nomina/ajustes", headers=f, json={
        "persona_id": juan, "pais_id": mx, "monto": "-500",
        "motivo": "Uniforme que no regreso"})
    assert r.status_code == 201, r.text
    n = _calcular(cliente, sesion, datos, _lunes())
    assert n["en_contra"] == 1

    barrera = threading.Barrier(2)
    salidas = []

    def pagar():
        db = SessionLocal()
        try:
            barrera.wait()
            try:
                motor.pagar(db, n["nomina_id"], None)
                db.commit()
                salidas.append("pagado")
            except Exception as error:      # noqa: BLE001
                db.rollback()
                salidas.append(type(error).__name__)
        finally:
            db.close()

    hilos = [threading.Thread(target=pagar) for _ in range(2)]
    for x in hilos:
        x.start()
    for x in hilos:
        x.join()

    assert sorted(salidas) == ["HTTPException", "pagado"], salidas
    with SessionLocal() as db:
        saldos = (db.query(m.AjusteNomina)
                  .filter_by(persona_id=juan, concepto=motor.AJUSTE_SALDO).all())
    assert len(saldos) == 1


def test_lo_pagado_a_quien_ya_no_esta_en_el_dia_se_reclama(cliente, sesion, datos):
    """Si por cualquier camino la asignacion de un dia pagado desaparece,
    la revision de diferencias parte de lo pagado y lo reclama."""
    from test_ajustes import _dia_pagado, _pendientes
    from app import models as m
    from app.db import SessionLocal

    servicio, j, juan, pais_id = _dia_pagado(cliente, sesion, datos, offset=300)
    with SessionLocal() as db:
        for a in db.query(m.AsignacionPersonal).filter_by(
                jornada_id=j["id"], persona_id=juan).all():
            db.delete(a)
        db.commit()

    r = cliente.post(f"/nomina/servicio/{servicio['id']}/revisar-diferencias",
                     headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    generados = r.json()["ajustes_generados"]
    assert len(generados) == 1 and Decimal(str(generados[0]["monto"])) < 0
    pendientes = _pendientes(cliente, sesion, pais_id)
    assert any("ya no va en ese dia" in p["motivo"] for p in pendientes)


# ================================================== la unidad que se cambia

def test_el_cambio_de_unidad_parte_solo_el_dia_del_cambio(cliente, sesion, datos):
    """La Suburban se recibio y el dia 2 se cambia por otra: el dia 2 se
    parte --hay que entregarla-- y el dia 3 solo trae la nueva."""
    servicio, equipo_id, juan = _servicio(cliente, sesion, datos, dias=3,
                                          offset=440, cotizado=True)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    suburban = datos["suburban"]
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != suburban["id"] and v["plaza_id"] == suburban["plaza_id"])
    assert revisar_unidad(cliente, sesion("juan"), servicio["id"],
                          suburban["id"], "recibe", 42_000).status_code == 201

    r = cliente.post("/contingencia/reemplazos/vehiculo", headers=h, json={
        "desde_jornada_id": dias[1]["id"], "sale_vehiculo_id": suburban["id"],
        "entra_vehiculo_id": otra["id"], "motivo": "Se quedo en el camino"})
    assert r.status_code == 200, r.text
    assert r.json()["jornadas_partidas"] == [dias[1]["fecha"]]

    assert _jornada(dias[2]["id"])["vehiculos"] == [otra["id"]]
    assert sorted(_jornada(dias[1]["id"])["vehiculos"]) == sorted(
        [suburban["id"], otra["id"]])
    ficha2 = cliente.get(f"/campo/jornadas/{dias[1]['id']}",
                         headers=sesion("juan")).json()
    assert [u["placa"] for u in ficha2["revision"]["entregar_hoy"]] == [
        suburban["placa"]]
    # El ultimo dia se entrega la que entro, no la que ya se fue.
    ficha3 = cliente.get(f"/campo/jornadas/{dias[2]['id']}",
                         headers=sesion("juan")).json()
    assert [u["placa"] for u in ficha3["revision"]["entregar_hoy"]] == [
        otra["placa"]]

    # Y el dia 3 la Suburban queda libre para otro servicio.
    segundo = crear_servicio(
        cliente, h, datos,
        [jornada(manana(442), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = segundo["equipos"][0]["jornadas"][0]
    r = cliente.post(f"/servicios/jornadas/{j['id']}/asignar-vehiculo",
                     json={"vehiculo_id": suburban["id"], "forzar": True},
                     headers=h)
    assert r.status_code == 200, r.text

# -*- coding: utf-8 -*-
"""Los viaticos en la factura.

Decision de Salvador, 23 de septiembre: la cotizacion dice si los
viaticos van incluidos en el precio o se cobran aparte; son dos opciones
distintas. Si se cobran, la factura suma lo comprobado valido; si van
incluidos, nada aparte. En el implantado la misma opcion vive en los
terminos del mes y pasa al siguiente.

La comision del consultor sigue siendo sobre lo facturado descontando
los viaticos. Con los viaticos cobrados ya dentro de la factura, deja de
restar unos que no se facturaban. Seccion 57 de la bitacora.

El viatico se da por comprobado directo en la base: aqui importa la
cuenta de la factura, no el camino de la comprobacion, que ya tiene sus
pruebas.
"""
from datetime import date, datetime

from ayudas import (asignar, configurar_origen, crear_servicio,
                    ejecutar_jornada, jornada, manana)

MOTIVO = "El equipo cerro por telefono; confirmado con el cliente"
DIAS = [date(2029, 9, d) for d in (24, 25, 26, 27, 28)]
SERVICIO_DEL_MES = 5 * 2900 + 66000      # cinco dias y la unidad del mes


def _viatico(cliente, sesion, datos, jornada_id, monto="900"):
    r = cliente.post("/viaticos/asignar", headers=sesion("consultor"), json={
        "jornada_id": jornada_id,
        "persona_id": datos["personal"]["Juan Ramirez"]["id"],
        "conceptos": [{"concepto": "alimentos", "monto": monto,
                       "origen": "tabulador"}]})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _comprobado(viatico_id, monto):
    """El viatico ya comprobado completo y cerrado por el consultor."""
    from decimal import Decimal

    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        v = db.get(m.AsignacionViatico, viatico_id)
        v.monto_comprobado = Decimal(monto)
        v.estatus = m.EstatusViatico.CERRADO
        db.commit()


def _armar(cierre_id):
    from app import facturacion
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return facturacion.armar(db, db.get(m.Cierre, cierre_id))


def _renglones(cuerpo):
    return [(c["tipo"], c["cantidad"], c["importe"]) for c in cuerpo["conceptos"]
            if c["tipo"] == "viaticos"]


# ---------------------------------------------------------------- el eventual

def _eventual(cliente, sesion, datos, incluidos, offset):
    """Un dia cotizado --con los viaticos incluidos o aparte--, con un
    viatico de 900 que se comprueba completo, y el dia trabajado."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    j = servicio["equipos"][0]["jornadas"][0]
    r = cliente.post("/cotizaciones", headers=h, json={
        "servicio_id": servicio["id"], "viaticos_incluidos": incluidos,
        "lineas": [
            {"fecha": j["fecha"], "tipo": "recurso",
             "perfil_id": datos["perfiles"]["conductor_seguridad"]["id"]},
            {"fecha": j["fecha"], "tipo": "vehiculo",
             "categoria_id": datos["categorias"]["suv_blindada"]["id"]}]})
    assert r.status_code == 201, r.text
    r = cliente.post(f"/cotizaciones/{r.json()['cotizacion_id']}/autorizar",
                     json={"autorizada_por": "Cliente de prueba"}, headers=h)
    assert r.status_code == 200, r.text
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    vid = _viatico(cliente, sesion, datos, j["id"])
    assert ejecutar_jornada(cliente, sesion("juan"), j).status_code == 200
    _comprobado(vid, "900")
    return servicio


def _visto_bueno_y_aprobacion(cliente, sesion, servicio_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        cierre_id = (db.query(m.Cierre)
                     .filter_by(servicio_id=servicio_id).first().id)
    envio = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                         headers=sesion("consultor"))
    assert envio.status_code == 200, envio.text
    aprobacion = cliente.post(f"/cierre/{cierre_id}/aprobar",
                              headers=sesion("finanzas"))
    assert aprobacion.status_code == 200, aprobacion.text
    return cierre_id, aprobacion.json()


def test_el_eventual_que_cobra_viaticos_los_factura(cliente, sesion, datos,
                                                   monkeypatch):
    """La cotizacion los cobra aparte: la factura suma lo comprobado en su
    propio renglon, la rentabilidad lo cuenta como facturado y la comision
    queda sobre el servicio --ya no le resta unos viaticos que antes ni
    se facturaban--."""
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    servicio = _eventual(cliente, sesion, datos, incluidos=False, offset=1400)
    h = sesion("consultor")
    comparativo = cliente.get(
        f"/cierre/servicio/{servicio['id']}/comparativo", headers=h).json()
    del_servicio = float(comparativo["ejecutado"]["total"])
    assert comparativo["viaticos"]["facturable_al_cliente"] == 900

    cierre_id, aprobacion = _visto_bueno_y_aprobacion(cliente, sesion,
                                                      servicio["id"])
    cuerpo = _armar(cierre_id)
    assert _renglones(cuerpo) == [("viaticos", 1, "900.00")]
    assert float(cuerpo["total"]) == del_servicio + 900

    bandeja = cliente.get("/cierre/por-facturar", headers=sesion("finanzas"))
    suyo = next(x for x in bandeja.json()["por_facturar"]
                if x["cierre_id"] == cierre_id)
    assert float(suyo["total"]) == del_servicio + 900

    rent = cliente.get(f"/cierre/servicio/{servicio['id']}/rentabilidad",
                       headers=h).json()
    assert float(rent["facturacion"]) == del_servicio + 900
    assert float(rent["viaticos_cobrados"]) == 900
    base = float(aprobacion["comision_consultor"]["base"])
    assert abs(base - del_servicio) < 0.01, \
        "la comision no resta los viaticos que el cliente paga aparte"


def test_el_eventual_con_viaticos_incluidos_no_los_suma(cliente, sesion, datos,
                                                       monkeypatch):
    """Van dentro del precio: la factura no lleva renglon de viaticos y la
    comision descuenta su costo, como siempre."""
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    servicio = _eventual(cliente, sesion, datos, incluidos=True, offset=1403)
    comparativo = cliente.get(
        f"/cierre/servicio/{servicio['id']}/comparativo",
        headers=sesion("consultor")).json()
    del_servicio = float(comparativo["ejecutado"]["total"])

    cierre_id, aprobacion = _visto_bueno_y_aprobacion(cliente, sesion,
                                                      servicio["id"])
    cuerpo = _armar(cierre_id)
    assert _renglones(cuerpo) == []
    assert float(cuerpo["total"]) == del_servicio
    base = float(aprobacion["comision_consultor"]["base"])
    assert abs(base - (del_servicio - 900)) < 0.01


# ---------------------------------------------------------------- el implantado

def _alta(cliente, sesion, datos, **extra):
    r = cliente.post("/implantados", headers=sesion("consultor"), json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "fecha_inicio": str(DIAS[0]), "dias_servicio": "lunes_viernes",
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                      "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                      "vehiculo_id": datos["suburban"]["id"]}],
        "unidades": [datos["suburban"]["id"]],
        "precio_dia_personal": "2900", "precio_mes_vehiculo": "66000",
        **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _mes_con_visto_bueno(cliente, sesion, datos, **extra):
    """Septiembre de 2029 con un viatico de 900 comprobado, trabajado
    completo y con el visto bueno dado. Devuelve el id del cierre."""
    from app import models as m
    from app.db import SessionLocal

    alta = _alta(cliente, sesion, datos, **extra)
    panel = cliente.get(f"/implantados/{alta['servicio_id']}/mes/2029/9",
                        headers=sesion("consultor")).json()
    jornadas = {date.fromisoformat(d["fecha"]): d["jornada_id"]
                for d in panel["dias"]}
    vid = _viatico(cliente, sesion, datos, jornadas[DIAS[1]])
    for dia in DIAS:
        r = cliente.post(
            f"/operacion/jornadas/{jornadas[dia]}/cerrar-a-mano",
            headers=sesion("central"), json={"justificacion": MOTIVO},
            params={"ahora": datetime.combine(dia, datetime.min.time())
                    .replace(hour=21).isoformat()})
        assert r.status_code == 200, r.text
    _comprobado(vid, "900")

    with SessionLocal() as db:
        cierre_id = (db.query(m.Cierre)
                     .filter_by(contrato_id=alta["contrato_id"]).first().id)
    ahora = datetime(2029, 9, 28, 22, 0)
    envio = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas",
                         headers=sesion("consultor"),
                         params={"ahora": ahora.isoformat()})
    assert envio.status_code == 200, envio.text
    return cierre_id


def test_el_mes_que_cobra_viaticos_los_factura(cliente, sesion, datos,
                                              monkeypatch):
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    cierre_id = _mes_con_visto_bueno(cliente, sesion, datos,
                                     viaticos_incluidos=False)
    cuerpo = _armar(cierre_id)
    assert [c["tipo"] for c in cuerpo["conceptos"]] == \
        ["dias_base", "vehiculo_mes", "viaticos"]
    assert _renglones(cuerpo) == [("viaticos", 1, "900.00")]
    assert float(cuerpo["total"]) == SERVICIO_DEL_MES + 900

    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    comision = r.json()["comision_consultor"]
    assert float(comision["base"]) == SERVICIO_DEL_MES
    assert float(comision["monto"]) == SERVICIO_DEL_MES / 100


def test_el_mes_con_viaticos_incluidos_no_los_suma(cliente, sesion, datos,
                                                  monkeypatch):
    """Por omision van incluidos, como en la cotizacion del eventual."""
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    cierre_id = _mes_con_visto_bueno(cliente, sesion, datos)
    cuerpo = _armar(cierre_id)
    assert _renglones(cuerpo) == []
    assert float(cuerpo["total"]) == SERVICIO_DEL_MES

    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert float(r.json()["comision_consultor"]["base"]) == SERVICIO_DEL_MES - 900


def test_el_mes_siguiente_hereda_como_se_cobran_los_viaticos(cliente, sesion,
                                                            datos):
    from app import implantado as motor
    from app import models as m
    from app.db import SessionLocal

    alta = _alta(cliente, sesion, datos, viaticos_incluidos=False)
    with SessionLocal() as db:
        abierto = motor.abrir_siguiente(
            db, db.get(m.Servicio, alta["servicio_id"]), hoy=date(2029, 9, 27))
        octubre = db.get(m.ContratoImplantado, abierto["contrato_id"])
        assert octubre.viaticos_incluidos is False

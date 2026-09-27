# -*- coding: utf-8 -*-
"""Aprobar sin porcentaje de comision en el pais (seccion 91).

Finanzas aprobaba, el cierre quedaba guardado como aprobado y despues,
al generar la comision del consultor, la API contestaba 400 porque el
pais --hoy, Brasil-- no tiene porcentaje. El servicio se quedaba aprobado
a medias: sin comision, sin intentar su factura y con un error en
pantalla de algo que si se habia guardado. Ahora se dice antes y no se
guarda nada.
"""
from ayudas import servicio_para_cierre


def _porcentaje_activo(tipo, activo):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        mx = db.query(m.Pais).filter_by(codigo="MX").one()
        fila = (db.query(m.PorcentajeComision)
                .filter_by(pais_id=mx.id, tipo_servicio=tipo).one())
        fila.activo = activo
        db.commit()


def _estatus_del_cierre(cierre_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return db.get(m.Cierre, cierre_id).estatus


def test_sin_porcentaje_no_se_aprueba_a_medias(cliente, sesion, datos):
    from app import models as m

    servicio, cierre_id = servicio_para_cierre(cliente, sesion, datos)
    _porcentaje_activo(m.TipoServicio.EVENTUAL, False)
    try:
        r = cliente.post(f"/cierre/{cierre_id}/aprobar",
                         headers=sesion("finanzas"))
        assert r.status_code == 409, r.text
        detalle = r.json()["detail"]
        assert detalle["clave"] == "sin_porcentaje_de_comision"
        assert "Mexico" in detalle["mensaje"] or "México" in detalle["mensaje"]
        # No se guardo nada: sigue esperando a finanzas.
        assert _estatus_del_cierre(cierre_id) == m.EstatusCierre.ENVIADO_FINANZAS
    finally:
        _porcentaje_activo(m.TipoServicio.EVENTUAL, True)

    # Con el porcentaje puesto se aprueba como siempre, con su comision.
    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert r.json()["comision_consultor"]["porcentaje"] == 3.0

"""El tabulador de viaticos del implantado vive en el acuerdo.

El de la empresa vale para el eventual: un dia suelto con las mismas
reglas para todos. El implantado se negocia cliente por cliente —que
come el equipo, si se le paga el traslado, que pasa con la gasolina— y
por eso cada servicio trae el suyo. Dos implantados de la misma ciudad
pueden tener numeros distintos y los dos estar bien.
"""
from datetime import date

from tests.test_mes_siguiente import _alta


def _guardar(cliente, h, servicio_id, renglones):
    r = cliente.put(f"/implantados/{servicio_id}/tabulador",
                    json={"renglones": renglones}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_sin_tabulador_la_propuesta_es_cero_y_se_dice(cliente, sesion, datos):
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]
    hoy = date.today()

    tab = cliente.get(f"/implantados/{servicio_id}/tabulador", headers=h).json()
    assert tab["capturado"] is False
    assert [r["concepto"] for r in tab["renglones"]][0] == "alimentos"

    panel = cliente.get(
        f"/implantados/{servicio_id}/viaticos/{hoy.year}/{hoy.month}",
        headers=h).json()
    assert float(panel["total_propuesto"]) == 0


def test_la_propuesta_sale_del_tabulador_del_acuerdo(cliente, sesion, datos):
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]
    hoy = date.today()

    _guardar(cliente, h, servicio_id, [
        {"concepto": "alimentos", "monto": "300", "activo": True},
        {"concepto": "casetas", "monto": "50", "activo": True},
        # Apagado: este cliente no paga hospedaje.
        {"concepto": "hospedaje", "monto": "0", "activo": False},
    ])

    tab = cliente.get(f"/implantados/{servicio_id}/tabulador", headers=h).json()
    assert tab["capturado"] is True
    assert float(tab["total_dia"]) == 350

    panel = cliente.get(
        f"/implantados/{servicio_id}/viaticos/{hoy.year}/{hoy.month}",
        headers=h).json()
    juan = next(p for p in panel["personal"]
                if p["persona_id"] == datos["personal"]["Juan Ramirez"]["id"])
    # 350 por dia, por cada dia que le toca.
    assert float(juan["propuesto"]) == 350 * juan["dias"]


def test_cada_servicio_trae_el_suyo(cliente, sesion, datos):
    """Dos implantados, dos acuerdos, dos numeros. Tocar uno no mueve el
    otro: es justo lo que pasaba cuando el tabulador era del pais."""
    uno, h = _alta(cliente, sesion, datos)
    otro, _ = _alta(cliente, sesion, datos)
    hoy = date.today()

    _guardar(cliente, h, uno["servicio_id"],
             [{"concepto": "alimentos", "monto": "300", "activo": True}])
    _guardar(cliente, h, otro["servicio_id"],
             [{"concepto": "alimentos", "monto": "180", "activo": True}])

    def propuesto(servicio_id):
        panel = cliente.get(
            f"/implantados/{servicio_id}/viaticos/{hoy.year}/{hoy.month}",
            headers=h).json()
        return float(panel["total_propuesto"])

    assert propuesto(uno["servicio_id"]) > propuesto(otro["servicio_id"])


def test_el_monto_abierto_se_ve_en_cero_y_lo_captura_el_consultor(
        cliente, sesion, datos):
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]
    hoy = date.today()

    _guardar(cliente, h, servicio_id, [
        {"concepto": "alimentos", "monto": "250", "activo": True},
        {"concepto": "otros", "monto": "0", "monto_abierto": True,
         "nota": "Taxi cuando el ejecutivo sale de zona", "activo": True},
    ])
    panel = cliente.get(
        f"/implantados/{servicio_id}/viaticos/{hoy.year}/{hoy.month}",
        headers=h).json()
    juan = next(p for p in panel["personal"]
                if p["persona_id"] == datos["personal"]["Juan Ramirez"]["id"])
    assert float(juan["propuesto"]) == 250 * juan["dias"]


def test_el_deposito_se_arma_con_los_conceptos_del_acuerdo(cliente, sesion,
                                                           datos):
    """Lo que se deposita se desglosa con los conceptos acordados, no con
    los de la tabla de la empresa: de ahi sale la comprobacion."""
    from app import models as m
    from app.db import SessionLocal

    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]
    hoy = date.today()
    juan = datos["personal"]["Juan Ramirez"]["id"]

    _guardar(cliente, h, servicio_id, [
        {"concepto": "alimentos", "monto": "300", "activo": True},
        {"concepto": "casetas", "monto": "50", "activo": True},
    ])
    cliente.post(
        f"/implantados/{servicio_id}/viaticos/{hoy.year}/{hoy.month}/persona",
        json={"persona_id": juan, "monto": "1000"}, headers=h)

    db = SessionLocal()
    try:
        servicio = db.get(m.Servicio, servicio_id)
        equipo = servicio.equipos[0]
        jornada = sorted(equipo.jornadas, key=lambda j: j.fecha)[0]
        viatico = (db.query(m.AsignacionViatico)
                   .filter_by(jornada_id=jornada.id, persona_id=juan).first())
        assert viatico, "no se creo el viatico del dia"
        conceptos = {c.concepto.value for c in viatico.conceptos}
        assert "alimentos" in conceptos
        assert "casetas" in conceptos
        assert "hospedaje" not in conceptos
    finally:
        db.close()


def test_el_eventual_sigue_leyendo_el_tabulador_de_la_empresa(cliente, sesion,
                                                              datos):
    """Nada de esto le movio el piso al eventual: su propuesta sigue
    saliendo de la tabla del pais."""
    h = sesion("consultor")
    r = cliente.get("/catalogos/tabulador-viaticos", headers=h)
    assert r.status_code == 200, r.text
    assert any(x["tipo_servicio"] == "eventual" for x in r.json())

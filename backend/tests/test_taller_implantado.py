"""La unidad entra al taller y otra toma su lugar.

Un coche desarmado que sigue apareciendo libre es como se le promete al
cliente un vehiculo que no existe. El bloqueo y el cambio son una sola
decision y por eso son una sola puerta.
"""
from datetime import date, timedelta

from tests.test_mes_siguiente import _alta


def _otra_unidad(cliente, h, datos, distinta_de):
    """Una unidad de la misma ciudad que no sea la del servicio."""
    return next(v for v in datos["vehiculos"]
                if v["id"] != distinta_de
                and v["plaza_id"] == datos["cdmx"]["id"]
                and not v.get("rentado"))


def _un_dia_habil(desde):
    dia = desde
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    return dia


def test_la_unidad_sale_de_circulacion_y_otra_la_cubre(cliente, sesion, datos):
    hoy = date.today()
    alta, h = _alta(cliente, sesion, datos, inicio=hoy.replace(day=1))
    servicio_id = alta["servicio_id"]
    sale = datos["suburban"]["id"]
    entra = _otra_unidad(cliente, h, datos, sale)

    desde = _un_dia_habil(max(hoy, hoy.replace(day=1)))
    r = cliente.post(f"/implantados/{servicio_id}/taller", json={
        "desde": str(desde), "tipo": "mantenimiento_correctivo",
        "entra_id": entra["id"], "taller": "Taller del sur",
        "folio": "OT-2211", "nota": "Se quedo en el camino",
    }, headers=h)
    assert r.status_code == 200, r.text
    hecho = r.json()
    assert hecho["entra"] == entra["placa"]
    assert hecho["dias_cambiados"] > 0

    # El bloqueo se ve, y la unidad que entra ya va en los dias.
    filas = cliente.get(f"/implantados/{servicio_id}/taller", headers=h).json()
    assert any(f["placa"] == datos["suburban"]["placa"] and f["hoy_fuera"]
               for f in filas), filas

    panel = cliente.get(f"/implantados/{servicio_id}/mes/{desde.year}/"
                        f"{desde.month}", headers=h).json()
    ese = next(d for d in panel["dias"] if d["fecha"] == desde.isoformat())
    assert [u["placa"] for u in ese["unidades"]] == [entra["placa"]]


def test_la_unidad_en_el_taller_deja_de_ofrecerse(cliente, sesion, datos):
    hoy = date.today()
    alta, h = _alta(cliente, sesion, datos, inicio=hoy.replace(day=1))
    servicio_id = alta["servicio_id"]
    sale = datos["suburban"]["id"]
    entra = _otra_unidad(cliente, h, datos, sale)
    desde = _un_dia_habil(max(hoy, hoy.replace(day=1)))

    cliente.post(f"/implantados/{servicio_id}/taller", json={
        "desde": str(desde), "entra_id": entra["id"]}, headers=h)

    libres = cliente.get(f"/implantados/{servicio_id}/unidades-libres"
                         f"?desde={desde}", headers=h).json()
    suya = next(v for v in libres["vehiculos"] if v["vehiculo_id"] == sale)
    assert suya["dias_en_taller"] > 0
    assert suya["libres"] < libres["dias"]


def test_no_se_cambia_una_unidad_por_ella_misma(cliente, sesion, datos):
    hoy = date.today()
    alta, h = _alta(cliente, sesion, datos, inicio=hoy.replace(day=1))
    desde = _un_dia_habil(max(hoy, hoy.replace(day=1)))
    r = cliente.post(f"/implantados/{alta['servicio_id']}/taller", json={
        "desde": str(desde), "entra_id": datos["suburban"]["id"]}, headers=h)
    assert r.status_code == 409, r.text


def test_sin_dias_en_el_tramo_no_queda_bloqueo_suelto(cliente, sesion, datos):
    """Si el cambio no se puede hacer, tampoco se guarda el taller: un
    bloqueo sin cambio deja la unidad fuera y el dia sin coche."""
    hoy = date.today()
    alta, h = _alta(cliente, sesion, datos, inicio=hoy.replace(day=1))
    servicio_id = alta["servicio_id"]
    entra = _otra_unidad(cliente, h, datos, datos["suburban"]["id"])

    lejos = date(hoy.year + 2, 1, 6)
    r = cliente.post(f"/implantados/{servicio_id}/taller", json={
        "desde": str(lejos), "entra_id": entra["id"]}, headers=h)
    assert r.status_code == 409, r.text
    assert cliente.get(f"/implantados/{servicio_id}/taller",
                       headers=h).json() == []

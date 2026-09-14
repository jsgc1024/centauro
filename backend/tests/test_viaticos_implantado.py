"""Los viaticos del implantado se cierran mes con mes.

El servicio corre sin fin, pero el dinero no: se deposita, se comprueba
y se cierra por mes, igual que se factura. Un deposito repartido entre
septiembre y octubre no habria forma de comprobarlo ni de cobrarlo.

Viven en su propia puerta, aparte del eventual: el calculo es el mismo
—el tabulador es uno solo— pero el corte no, y mezclarlos terminaria
moviendole el corte a quien no lo pidio.
"""
import calendar
from datetime import date

from tests.test_mes_siguiente import _alta, _siguiente


def _habiles(anio, mes):
    return sum(1 for d in range(1, calendar.monthrange(anio, mes)[1] + 1)
               if date(anio, mes, d).weekday() < 5)


def _panel(cliente, h, servicio_id, anio, mes):
    r = cliente.get(f"/implantados/{servicio_id}/viaticos/{anio}/{mes}",
                    headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_el_panel_solo_ve_los_dias_de_su_mes(cliente, sesion, datos):
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]
    hoy = date.today()
    cliente.post(f"/implantados/{servicio_id}/mes-siguiente", headers=h)
    anio, mes = _siguiente(hoy)

    este = _panel(cliente, h, servicio_id, hoy.year, hoy.month)
    otro = _panel(cliente, h, servicio_id, anio, mes)

    assert este["periodo"] == f"{hoy.month:02d}/{hoy.year}"
    assert otro["periodo"] == f"{mes:02d}/{anio}"
    assert este["dias"] == _habiles(hoy.year, hoy.month)
    assert otro["dias"] == _habiles(anio, mes)
    assert len(otro["personal"]) == 2, "el mes nuevo nacio sin gente"


def test_el_deposito_se_queda_en_su_mes(cliente, sesion, datos):
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]
    hoy = date.today()
    cliente.post(f"/implantados/{servicio_id}/mes-siguiente", headers=h)
    anio, mes = _siguiente(hoy)
    juan = datos["personal"]["Juan Ramirez"]["id"]

    r = cliente.post(
        f"/implantados/{servicio_id}/viaticos/{hoy.year}/{hoy.month}/persona",
        json={"persona_id": juan, "monto": "3000"}, headers=h)
    assert r.status_code == 200, r.text
    suyo = next(p for p in r.json()["personal"] if p["persona_id"] == juan)
    assert float(suyo["asignado"]) == 3000
    assert suyo["estatus"] == "asignado"

    otro = _panel(cliente, h, servicio_id, anio, mes)
    suyo = next(p for p in otro["personal"] if p["persona_id"] == juan)
    assert float(suyo["asignado"]) == 0, "el deposito se paso al otro mes"


def test_se_pide_y_se_cancela_por_mes(cliente, sesion, datos):
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]
    hoy = date.today()
    juan = datos["personal"]["Juan Ramirez"]["id"]
    base = f"/implantados/{servicio_id}/viaticos/{hoy.year}/{hoy.month}"

    cliente.post(f"{base}/persona", json={"persona_id": juan, "monto": "3000"},
                 headers=h)
    r = cliente.post(f"{base}/solicitar", json={}, headers=h)
    assert r.status_code == 200, r.text
    suyo = next(p for p in r.json()["personal"] if p["persona_id"] == juan)
    assert suyo["estatus"] == "solicitado"
    assert float(suyo["en_camino"]) == 3000

    # Mientras el dinero no salga, se puede echar para atras.
    r = cliente.post(f"{base}/cancelar", json={"persona_id": juan}, headers=h)
    assert r.status_code == 200, r.text
    suyo = next(p for p in r.json()["personal"] if p["persona_id"] == juan)
    assert suyo["estatus"] == "asignado"
    assert float(suyo["en_camino"]) == 0
    assert float(suyo["asignado"]) == 3000, "se perdio el monto al cancelar"


def test_el_cierre_del_mes_trae_los_viaticos(cliente, sesion, datos):
    alta, h = _alta(cliente, sesion, datos)
    servicio_id, contrato_id = alta["servicio_id"], alta["contrato_id"]
    hoy = date.today()
    juan = datos["personal"]["Juan Ramirez"]["id"]

    cliente.post(
        f"/implantados/{servicio_id}/viaticos/{hoy.year}/{hoy.month}/persona",
        json={"persona_id": juan, "monto": "3000"}, headers=h)

    cierre = cliente.get(f"/implantados/contratos/{contrato_id}/cierre",
                         headers=h).json()
    assert float(cierre["viaticos"]["asignado"]) == 3000
    suyo = next(p for p in cierre["personal"] if p["persona_id"] == juan)
    assert float(suyo["viaticos"]["asignado"]) == 3000
    assert float(suyo["viaticos"]["depositado"]) == 0


def test_el_eventual_quedo_intacto(cliente, sesion, datos):
    """La puerta del eventual no aprendio nada del mes: contesta igual
    que siempre, por todos los dias del equipo."""
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]
    hoy = date.today()
    equipo_id = cliente.get(
        f"/implantados/{servicio_id}/calendario/{hoy.year}/{hoy.month}",
        headers=h).json()["equipo_id"]
    cliente.post(f"/implantados/{servicio_id}/mes-siguiente", headers=h)

    todos = cliente.get(f"/viaticos/equipos/{equipo_id}", headers=h).json()
    uno = _panel(cliente, h, servicio_id, hoy.year, hoy.month)
    assert "periodo" not in todos
    assert todos["equipo"]["dias"] > uno["dias"]

"""Contrato mensual, dias adicionales y reemplazos."""
from datetime import date

import calendar


def _contrato(cliente, sesion, datos, anio=2027, mes=3):
    h = sesion("consultor")
    servicio = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "implantado",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}, headers=h).json()

    contrato = cliente.post("/implantados/contratos", json={
        "servicio_id": servicio["id"], "anio": anio, "mes": mes,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia", "incluye_fines_de_semana": False,
        "hora_presentacion": "08:00:00",
        "titular_id": datos["personal"]["Juan Ramirez"]["id"],
        "vehiculo_id": datos["suburban"]["id"],
        "precio_mes_vehiculo": "66000", "precio_dia_personal": "2900",
        "precio_dia_adicional": "3500"}, headers=h).json()
    return servicio, contrato


def _habiles(anio, mes):
    ultimo = calendar.monthrange(anio, mes)[1]
    return sum(1 for d in range(1, ultimo + 1)
               if date(anio, mes, d).weekday() < 5)


def test_la_base_es_la_del_calendario_no_un_numero_fijo(cliente, sesion, datos):
    _, contrato = _contrato(cliente, sesion, datos, 2027, 3)
    assert contrato["dias_base_del_mes"] == _habiles(2027, 3)


def test_generar_el_mes_crea_solo_dias_habiles(cliente, sesion, datos):
    _, contrato = _contrato(cliente, sesion, datos, 2027, 4)
    r = cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                     headers=sesion("consultor"))
    assert r.status_code == 200
    assert r.json()["jornadas_creadas"] == _habiles(2027, 4)


def test_el_dia_adicional_se_cobra_aparte(cliente, sesion, datos):
    _, contrato = _contrato(cliente, sesion, datos, 2027, 5)
    h = sesion("consultor")
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    sabado = next(date(2027, 5, d) for d in range(1, 29)
                  if date(2027, 5, d).weekday() == 5)
    r = cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/dias-adicionales",
                     json={"fecha": str(sabado)}, headers=h)
    assert r.status_code == 200
    assert r.json()["es_dia_adicional"] is True
    assert float(r.json()["costo_extra"]) == 3500

    resumen = cliente.get(f"/implantados/contratos/{contrato['contrato_id']}/resumen",
                          headers=h).json()
    assert resumen["dias"]["adicionales"] == 1
    esperado = (_habiles(2027, 5) * 2900) + 3500 + 66000
    assert abs(float(resumen["facturacion"]["total"]) - esperado) < 0.01


def test_el_reemplazo_queda_registrado(cliente, sesion, datos):
    servicio, contrato = _contrato(cliente, sesion, datos, 2027, 6)
    h = sesion("consultor")
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    jornada_id = detalle["equipos"][0]["jornadas"][5]["id"]

    r = cliente.post(f"/implantados/jornadas/{jornada_id}/reemplazo",
                     json={"entra_id": datos["personal"]["Luis Mendoza"]["id"],
                           "motivo": "enfermedad", "nota": "Incapacidad de un dia"},
                     headers=h)
    assert r.status_code == 200
    assert r.json()["sale"] == "Juan Ramirez"
    assert r.json()["entra"] == "Luis Mendoza"

    resumen = cliente.get(f"/implantados/contratos/{contrato['contrato_id']}/resumen",
                          headers=h).json()
    assert resumen["total_reemplazos"] == 1
    assert resumen["reemplazos"][0]["motivo"] == "enfermedad"


def test_no_se_duplica_el_contrato_del_mismo_mes(cliente, sesion, datos):
    servicio, _ = _contrato(cliente, sesion, datos, 2027, 7)
    r = cliente.post("/implantados/contratos", json={
        "servicio_id": servicio["id"], "anio": 2027, "mes": 7,
        "modalidad_id": datos["modalidades"]["full_day"]["id"]},
        headers=sesion("consultor"))
    assert r.status_code == 409

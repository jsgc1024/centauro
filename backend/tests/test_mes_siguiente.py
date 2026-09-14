"""El mes que sigue de un implantado.

El implantado es continuo: se vende una vez y se opera hasta que alguien
lo cancela. El mes nuevo no se vuelve a capturar, se abre con los mismos
terminos y la misma plantilla —a mano con el boton, o solo cuando al mes
en curso le quedan pocos dias—. El tope es uno por delante.
"""
from datetime import date

import calendar


def _alta(cliente, sesion, datos, inicio=None, dias="lunes_viernes"):
    """Un implantado con dos personas y una unidad, desde este mes."""
    h = sesion("consultor")
    inicio = inicio or date.today().replace(day=1)
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    unidad = datos["suburban"]["id"]
    # El rol es de la tarea: uno conduce y el otro va de agente. Sin rol
    # la plantilla no se guarda, y esta bien que no se guarde.
    conductor = datos["perfiles"]["conductor_seguridad"]["id"]
    agente = datos["perfiles"]["agente_seguridad"]["id"]

    r = cliente.post("/implantados", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"],
        "solicitante_nombre": "Rocio", "solicitante_apellidos": "Prado",
        "ejecutivo_nombre": "Andres", "ejecutivo_apellidos": "Lira",
        "fecha_inicio": str(inicio), "dias_servicio": dias,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "personal": [{"persona_id": juan, "rol_id": conductor,
                      "vehiculo_id": unidad},
                     {"persona_id": luis, "rol_id": agente,
                      "vehiculo_id": None}],
        "unidades": [unidad],
        "precio_dia_personal": "2900", "precio_mes_vehiculo": "66000",
    }, headers=h)
    assert r.status_code == 201, r.text
    return r.json(), h


def _siguiente(hoy):
    return (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)


def test_el_mes_siguiente_se_abre_con_la_misma_plantilla(cliente, sesion, datos):
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]

    r = cliente.post(f"/implantados/{servicio_id}/mes-siguiente", headers=h)
    assert r.status_code == 200, r.text
    abierto = r.json()

    anio, mes = _siguiente(date.today())
    assert abierto["periodo"] == f"{mes:02d}/{anio}"
    # La plantilla completa, no solo el titular.
    assert abierto["personas"] == 2
    assert abierto["unidades"] == 1

    # Y el mes nuevo nacio armado: todos sus dias habiles con la gente.
    habiles = sum(1 for d in range(1, calendar.monthrange(anio, mes)[1] + 1)
                  if date(anio, mes, d).weekday() < 5)
    assert abierto["jornadas_creadas"] == habiles

    panel = cliente.get(f"/implantados/{servicio_id}/mes/{anio}/{mes}",
                        headers=h).json()
    assert panel["abierto"] is True
    assert all(len(d["personal"]) == 2 for d in panel["dias"])


def test_solo_un_mes_por_delante(cliente, sesion, datos):
    """Abierto el que sigue, no se puede abrir otro mas."""
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]

    assert cliente.post(f"/implantados/{servicio_id}/mes-siguiente",
                        headers=h).status_code == 200
    r = cliente.post(f"/implantados/{servicio_id}/mes-siguiente", headers=h)
    assert r.status_code == 409, r.text
    assert "un solo mes" in str(r.json()["detail"])


def test_la_cartera_dice_cual_sigue_y_cuales_estan_abiertos(cliente, sesion, datos):
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]

    ficha = next(x for x in cliente.get("/implantados", headers=h).json()
                 if x["servicio_id"] == servicio_id)
    anio, mes = _siguiente(date.today())
    assert len(ficha["periodos"]) == 1
    assert ficha["siguiente"]["se_puede"] is True
    assert ficha["siguiente"]["periodo"] == f"{mes:02d}/{anio}"

    cliente.post(f"/implantados/{servicio_id}/mes-siguiente", headers=h)
    ficha = next(x for x in cliente.get("/implantados", headers=h).json()
                 if x["servicio_id"] == servicio_id)
    assert len(ficha["periodos"]) == 2
    assert ficha["siguiente"]["se_puede"] is False


def test_abrir_un_mes_no_regresa_a_planeado_lo_que_ya_arranco(cliente, sesion,
                                                              datos):
    """Un servicio con la hoja liberada no vuelve a planeado porque se
    haya abierto el mes que entra."""
    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]

    assert cliente.post(f"/task-sheets/implantado/{servicio_id}/liberar",
                        headers=h).status_code == 200
    antes = cliente.get(f"/servicios/{servicio_id}", headers=h).json()["estatus"]
    assert antes == "asignado"

    cliente.post(f"/implantados/{servicio_id}/mes-siguiente", headers=h)
    despues = cliente.get(f"/servicios/{servicio_id}", headers=h).json()["estatus"]
    assert despues == "asignado", "abrir el mes echo para atras el servicio"


def test_el_proceso_de_la_manana_solo_corre_al_final_del_mes(cliente, sesion,
                                                             datos):
    """Faltando muchos dias no toca a nadie; faltando pocos, abre."""
    from app import implantado as motor
    from app.db import SessionLocal

    alta, h = _alta(cliente, sesion, datos)
    servicio_id = alta["servicio_id"]

    hoy = date.today()
    ultimo = calendar.monthrange(hoy.year, hoy.month)[1]
    db = SessionLocal()
    try:
        temprano = date(hoy.year, hoy.month, 1)
        if ultimo - temprano.day > motor.DIAS_ANTES:
            assert motor.por_abrir(db, temprano) == []

        tarde = date(hoy.year, hoy.month, ultimo)
        resultado = motor.abrir_los_que_toquen(db, tarde)
        folios = [x["servicio_id"] for x in resultado["abiertos"]]
        assert servicio_id in folios, resultado
        # Y no lo abre dos veces.
        assert motor.abrir_los_que_toquen(db, tarde)["abiertos"] == []
    finally:
        db.close()


def test_el_mes_nuevo_arranca_el_dia_uno(cliente, sesion, datos):
    """El primer mes empieza el dia del meet and greet; el siguiente no
    hereda ese corte."""
    hoy = date.today()
    dia = min(hoy.day + 2, calendar.monthrange(hoy.year, hoy.month)[1])
    alta, h = _alta(cliente, sesion, datos,
                    inicio=date(hoy.year, hoy.month, dia))
    servicio_id = alta["servicio_id"]

    r = cliente.post(f"/implantados/{servicio_id}/mes-siguiente", headers=h)
    assert r.status_code == 200, r.text
    anio, mes = _siguiente(hoy)
    panel = cliente.get(f"/implantados/{servicio_id}/mes/{anio}/{mes}",
                        headers=h).json()
    assert panel["desde_dia"] is None
    primero = min(d["fecha"] for d in panel["dias"])
    assert primero <= f"{anio}-{mes:02d}-03"


# ------------------------------------------------- la traba de la hoja

def test_no_se_libera_la_hoja_con_dias_en_ambar(cliente, sesion, datos):
    """Un fin de semana contratado y sin nadie no se manda al cliente."""
    hoy = date.today()
    # Un mes que empieza hoy y corre los siete dias: los fines de semana
    # nacen en ambar, sin gente, a proposito.
    alta, h = _alta(cliente, sesion, datos, inicio=hoy, dias="todos")
    servicio_id = alta["servicio_id"]

    r = cliente.post(f"/task-sheets/implantado/{servicio_id}/liberar", headers=h)
    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    assert detalle["dias"], detalle
    assert all(date.fromisoformat(d).weekday() >= 5 for d in detalle["dias"])

    # Cubiertos todos, la hoja sale.
    for dia in list(detalle["dias"]):
        cliente.post(f"/implantados/{servicio_id}/dia/{dia}/cubrir", json={
            "personal": [{"persona_id": datos["personal"]["Juan Ramirez"]["id"],
                          "vehiculo_id": datos["suburban"]["id"]}],
        }, headers=h)

    r = cliente.post(f"/task-sheets/implantado/{servicio_id}/liberar", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["estatus"] == "asignado"


def test_el_ambar_de_lo_que_ya_paso_no_traba(cliente, sesion, datos):
    """Un sabado que ya se fue no se puede cubrir; trabar por el seria
    dejar el servicio sin hoja para siempre."""
    from app import implantado as motor
    from app.db import SessionLocal
    from app import models as m

    hoy = date.today()
    alta, h = _alta(cliente, sesion, datos,
                    inicio=hoy.replace(day=1), dias="todos")
    db = SessionLocal()
    try:
        servicio = db.get(m.Servicio, alta["servicio_id"])
        ambar = motor.dias_en_ambar(db, servicio)
        assert all(d >= hoy.isoformat() for d in ambar), ambar
    finally:
        db.close()

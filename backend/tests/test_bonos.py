"""Estrellas del personal, sancion por incidencia e implantados."""
from datetime import date, datetime, timedelta

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, ejecutar_jornada, jornada, marcar)


def _mes_trabajado(cliente, sesion, datos, persona_nombre="Luis Mendoza",
                   retraso_segunda=0, dia_base=None):
    """Dos jornadas dentro del mes en curso, ejecutadas completas."""
    h = sesion("consultor")
    hoy = date.today()
    base = dia_base or max(1, hoy.day - 6)
    fechas = [date(hoy.year, hoy.month, min(base, 27)),
              date(hoy.year, hoy.month, min(base + 1, 28))]

    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(f, datos["modalidades"]["full_day"]["id"]) for f in fechas])

    persona = datos["personal"][persona_nombre]["id"]
    quien = {"Luis Mendoza": "luis", "Juan Ramirez": "juan"}[persona_nombre]

    for idx, j in enumerate(servicio["equipos"][0]["jornadas"]):
        r = asignar(cliente, h, j["id"], persona_id=persona,
                    vehiculo_id=datos["suburban"]["id"])
        assert r[0].status_code == 200, f"no se asigno: {r[0].text}"
        configurar_origen(cliente, h, j["id"])
        ejecutar_jornada(cliente, sesion(quien), j,
                         retraso_minutos=retraso_segunda if idx == 1 else 0)

    return servicio, persona


def test_puntualidad_exige_el_cien_por_ciento(cliente, sesion, datos):
    _, persona = _mes_trabajado(cliente, sesion, datos, retraso_segunda=25,
                                dia_base=2)
    hoy = date.today()
    ficha = cliente.post("/evaluaciones",
                         json={"persona_id": persona, "anio": hoy.year,
                               "mes": hoy.month, "capacitacion_cumplida": True},
                         headers=sesion("consultor")).json()

    puntualidad = next(c for c in ficha["criterios"]
                       if c["criterio"] == "Llegar al punto")
    assert puntualidad["medido"] == 50.0
    assert puntualidad["cumplido"] is False


def test_mes_sin_viaticos_no_regala_la_estrella(cliente, sesion, datos):
    _, persona = _mes_trabajado(cliente, sesion, datos, dia_base=5)
    hoy = date.today()
    ficha = cliente.post("/evaluaciones",
                         json={"persona_id": persona, "anio": hoy.year,
                               "mes": hoy.month, "capacitacion_cumplida": True},
                         headers=sesion("consultor")).json()

    viaticos = next(c for c in ficha["criterios"]
                    if c["criterio"] == "Comprobar el dinero a tiempo")
    assert viaticos["aplica"] is False
    assert float(viaticos["monto"]) == 0
    # Cuatro posibles: llegar, no callarse, entregar la unidad
    # documentada y la capacitacion. Los viaticos no aplican --no le
    # asignaron-- y la recompra tampoco --nadie lo pidio por nombre--.
    assert ficha["estrellas_posibles"] == 4


def test_el_bono_se_reparte_entre_los_criterios_aplicables(cliente, sesion, datos):
    _, persona = _mes_trabajado(cliente, sesion, datos, dia_base=8)
    hoy = date.today()
    ficha = cliente.post("/evaluaciones",
                         json={"persona_id": persona, "anio": hoy.year,
                               "mes": hoy.month, "capacitacion_cumplida": True},
                         headers=sesion("consultor")).json()

    # Catalogo: 780 + 650 + 390 + 390 + 260 + 130 = 2600. Los viaticos
    # no aplican y sus 390 se reparten; la recompra tampoco aplica pero
    # NO reparte --es el que suma y no resta--, asi que el techo del mes
    # sin recompra es 2,470.
    assert ficha["estrellas"] == 4
    assert abs(float(ficha["bono"]) - 2470) < 0.05


def test_lo_que_no_aplica_se_reparte_a_prorrata_no_en_partes_iguales(
        cliente, sesion, datos):
    """El defecto que esto cuida: el reparto era en partes iguales, asi
    que aplanaba SIEMPRE el catalogo --con todo aplicando, puntualidad
    dejaba de valer 780 y capacitacion dejaba de valer 260: las dos
    pagaban lo mismo--. La pantalla dejaba configurar pesos y el motor
    los ignoraba."""
    _, persona = _mes_trabajado(cliente, sesion, datos, dia_base=20)
    hoy = date.today()
    ficha = cliente.post("/evaluaciones",
                         json={"persona_id": persona, "anio": hoy.year,
                               "mes": hoy.month, "capacitacion_cumplida": True},
                         headers=sesion("consultor")).json()

    llegar = next(c for c in ficha["criterios"]
                  if c["criterio"] == "Llegar al punto")
    central = next(c for c in ficha["criterios"]
                   if c["criterio"] == "No dejar callada a la central")

    # Los viaticos no aplicaron: lo suyo se reparte, asi que cada uno
    # paga mas de lo que dice el catalogo.
    assert float(llegar["monto"]) > 780
    assert float(central["monto"]) > 650
    # Y se reparte a prorrata: la proporcion del catalogo se conserva.
    assert abs(float(llegar["monto"]) / float(central["monto"])
               - 780 / 650) < 0.01


def test_incidencia_no_pega_sin_visto_bueno(cliente, sesion, datos):
    servicio, persona = _mes_trabajado(cliente, sesion, datos, dia_base=11)
    hoy = date.today()
    h = sesion("consultor")

    incidencia = cliente.post("/incidencias", json={
        "persona_id": persona, "fecha": str(date(hoy.year, hoy.month, 11)),
        "gravedad": "leve", "servicio_id": servicio["id"],
        "descripcion": "Queja del ejecutivo por presentacion del vehiculo"},
        headers=h).json()

    ficha = cliente.post("/evaluaciones",
                         json={"persona_id": persona, "anio": hoy.year,
                               "mes": hoy.month, "capacitacion_cumplida": True},
                         headers=h).json()
    assert ficha["anulado_por_incidencia"] is False
    assert float(ficha["bono"]) > 0

    cliente.post(f"/incidencias/{incidencia['incidencia_id']}/visto-bueno",
                 json={"autorizar": True, "resolucion": "Confirmada con el cliente"},
                 headers=sesion("diroperaciones"))

    ficha2 = cliente.post("/evaluaciones",
                          json={"persona_id": persona, "anio": hoy.year,
                                "mes": hoy.month, "capacitacion_cumplida": True},
                          headers=h).json()
    assert ficha2["anulado_por_incidencia"] is True
    assert float(ficha2["bono"]) == 0
    assert ficha2["estrellas"] > 0, "las estrellas se conservan como referencia"


def test_error_menor_no_toca_las_estrellas(cliente, sesion, datos):
    servicio, persona = _mes_trabajado(cliente, sesion, datos, dia_base=14)
    hoy = date.today()
    h = sesion("consultor")

    incidencia = cliente.post("/incidencias", json={
        "persona_id": persona, "fecha": str(date(hoy.year, hoy.month, 14)),
        "gravedad": "error_menor", "servicio_id": servicio["id"],
        "descripcion": "Olvido marcar un standby, se corrigio en el momento"},
        headers=h).json()
    cliente.post(f"/incidencias/{incidencia['incidencia_id']}/visto-bueno",
                 json={"autorizar": True, "resolucion": "Solo retroalimentacion"},
                 headers=sesion("diroperaciones"))

    ficha = cliente.post("/evaluaciones",
                         json={"persona_id": persona, "anio": hoy.year,
                               "mes": hoy.month, "capacitacion_cumplida": True},
                         headers=h).json()
    assert ficha["anulado_por_incidencia"] is False
    assert float(ficha["bono"]) > 0


def test_el_personal_solo_ve_su_evaluacion(cliente, sesion, datos):
    _, persona = _mes_trabajado(cliente, sesion, datos, dia_base=17)
    hoy = date.today()
    cliente.post("/evaluaciones",
                 json={"persona_id": persona, "anio": hoy.year, "mes": hoy.month},
                 headers=sesion("consultor"))

    ruta = f"/evaluaciones/{persona}/{hoy.year}/{hoy.month}"
    assert cliente.get(ruta, headers=sesion("juan")).status_code == 403
    assert cliente.get(ruta, headers=sesion("luis")).status_code == 200


# ==================================================================
# El dia del relevo es de quien lo empezo
# ==================================================================

def _dia_de_este_mes():
    """Un dia del mes en curso que siempre existe, hoy o antes."""
    hoy = date.today()
    return date(hoy.year, hoy.month, min(hoy.day, 28))


def _con_relevo(cliente, sesion, datos, se_presenta=True):
    """Juan toma el dia; si se presenta, Luis lo releva a media jornada.

    Devuelve la jornada y las dos personas.
    """
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(_dia_de_este_mes(), datos["modalidades"]["full_day"]["id"])],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])

    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    luis = datos["personal"]["Luis Mendoza"]["id"]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])

    if se_presenta:
        inicio = datetime.fromisoformat(j["inicio_programado"])
        marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=10))
        marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo", inicio)

    r = cliente.post("/contingencia/reemplazos/personal", headers=h,
                     json={"desde_jornada_id": j["id"],
                           "sale_persona_id": juan, "entra_persona_id": luis,
                           "motivo": "Se sintio mal"})
    assert r.status_code == 200, r.text
    return j, juan, luis


def test_el_dia_partido_no_cuenta_para_quien_entro(cliente, sesion, datos):
    """Luis llego a media manana: no tuvo hora de presentacion contra la
    cual medirse, ni marco la secuencia del dia.

    Antes ese dia entraba a su evaluacion y le hacia las dos cosas mal a
    la vez: le regalaba una puntualidad que no trabajo --la jornada
    arranco a tiempo, pero la arranco Juan-- y le cobraba un seguimiento
    incompleto por unas marcas que tampoco eran suyas.
    """
    from app import bonos
    from app.db import SessionLocal

    j, juan, luis = _con_relevo(cliente, sesion, datos, se_presenta=True)
    hoy = date.today()

    db = SessionLocal()
    try:
        de_luis = bonos.jornadas_del_mes(db, luis, hoy.year, hoy.month)
        de_juan = bonos.jornadas_del_mes(db, juan, hoy.year, hoy.month)
        assert j["id"] not in [x.id for x in de_luis], \
            "el dia del relevo no es de quien entro a media jornada"
        assert j["id"] in [x.id for x in de_juan], \
            "el dia si es de quien lo empezo y marco su llegada"
    finally:
        db.close()


def test_el_dia_que_cambio_limpio_si_es_de_quien_entro(cliente, sesion, datos):
    """Si Juan nunca se presento, el dia no se partio: cambio de dueno.
    Luis lo trabaja entero desde su hora, asi que se le mide como
    cualquier otro dia suyo."""
    from app import bonos
    from app.db import SessionLocal

    j, juan, luis = _con_relevo(cliente, sesion, datos, se_presenta=False)
    hoy = date.today()

    db = SessionLocal()
    try:
        de_luis = bonos.jornadas_del_mes(db, luis, hoy.year, hoy.month)
        de_juan = bonos.jornadas_del_mes(db, juan, hoy.year, hoy.month)
        assert j["id"] in [x.id for x in de_luis]
        assert j["id"] not in [x.id for x in de_juan], \
            "quien no se presento no deja rastro en el dia"
    finally:
        db.close()

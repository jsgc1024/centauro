"""Calculo, dispersion, comprobacion y cierre de viaticos."""
from decimal import Decimal, ROUND_CEILING

from ayudas import asignar, crear_servicio, jornada, manana


def _jornada_con_viaticos(cliente, sesion, datos, dia_offset, foraneo=True, km=420):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(dia_offset), datos["modalidades"]["full_day"]["id"],
        es_foraneo=foraneo, km_estimados=km)])
    j = servicio["equipos"][0]["jornadas"][0]
    carlos = datos["personal"]["Carlos Vega"]["id"]
    asignar(cliente, h, j["id"], persona_id=carlos,
            vehiculo_id=datos["suburban"]["id"])
    return servicio, j, carlos


def test_el_tabulador_propone_segun_el_escenario(cliente, sesion, datos):
    _, j, persona = _jornada_con_viaticos(cliente, sesion, datos, 40)
    r = cliente.get(f"/viaticos/calcular?jornada_id={j['id']}&persona_id={persona}",
                    headers=sesion("consultor"))
    assert r.status_code == 200
    propuesta = r.json()
    assert propuesta["escenario"] == "full_day_foraneo"
    conceptos = {c["concepto"]: c for c in propuesta["conceptos"]}
    assert conceptos["hospedaje"]["origen"] == "tabulador"
    assert conceptos["casetas"]["origen"] == "manual"


def _montos(cliente, h, datos, modalidad, offset, **extra):
    """La propuesta de un dia, como {concepto: monto}."""
    carlos = datos["personal"]["Carlos Vega"]["id"]
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(offset), datos["modalidades"][modalidad]["id"], **extra)])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=carlos,
            vehiculo_id=datos["suburban"]["id"])
    propuesta = cliente.get(
        f"/viaticos/calcular?jornada_id={j['id']}&persona_id={carlos}",
        headers=h).json()
    return {c["concepto"]: Decimal(str(c["monto"]))
            for c in propuesta["conceptos"]}


def test_el_traslado_se_cubre_solo_al_que_madruga(cliente, sesion, datos):
    """Antes de las 6:30 no hay con que llegar a la base y el agente se
    paga un taxi de su bolsa. Mas tarde llega como llega cualquier dia.

    El renglon se queda a la vista en cero: que desapareciera dejaba al
    consultor sin saber si el tabulador estaba mal cargado."""
    h = sesion("consultor")
    de = lambda hora, offset: _montos(  # noqa: E731
        cliente, h, datos, "full_day", offset, hora=hora,
        es_foraneo=False, km_estimados=150)

    assert de("05:45:00", 60)["traslado_personal"] == Decimal("200")
    assert de("07:00:00", 61)["traslado_personal"] == Decimal("0")
    # Justo a las 6:30 ya hay como llegar: la regla es antes de.
    assert de("06:30:00", 62)["traslado_personal"] == Decimal("0")


def test_alimentos_se_pagan_en_full_day_y_la_casilla_se_queda(
        cliente, sesion, datos):
    """Hoy medio dia y transfer no cubren comida, pero el renglon sigue
    ahi en cero: el dia que se decida pagar algo es cambiar el monto."""
    h = sesion("consultor")

    completo = _montos(cliente, h, datos, "full_day", 63, hora="09:00:00")
    assert completo["alimentos"] == Decimal("350")

    for modalidad, offset in (("medio_dia", 64), ("transfer", 65)):
        corto = _montos(cliente, h, datos, modalidad, offset, hora="09:00:00")
        assert corto["alimentos"] == Decimal("0"), modalidad
        assert corto["traslado_personal"] == Decimal("0"), modalidad
        # Estos si aplican en jornada corta, y salen calculados.
        assert corto["combustible"] > 0, modalidad
        assert "otros" in corto, modalidad


def test_el_estacionamiento_del_aeropuerto_se_cuenta_por_vuelta(
        cliente, sesion, datos):
    """Recoger es una vuelta y dejar es otra. Cien pesos cada una, que es
    lo que cobra el estacionamiento."""
    h = sesion("consultor")
    carlos = datos["personal"]["Carlos Vega"]["id"]

    def otros_de(offset, **extra):
        servicio = crear_servicio(cliente, h, datos, [jornada(
            manana(offset), datos["modalidades"]["full_day"]["id"],
            hora="09:00:00", **extra)])
        j = servicio["equipos"][0]["jornadas"][0]
        asignar(cliente, h, j["id"], persona_id=carlos,
                vehiculo_id=datos["suburban"]["id"])
        propuesta = cliente.get(
            f"/viaticos/calcular?jornada_id={j['id']}&persona_id={carlos}",
            headers=h).json()
        fila = next((c for c in propuesta["conceptos"]
                     if c["concepto"] == "otros"), None)
        return Decimal(str(fila["monto"])) if fila else None

    # Sin aeropuerto de por medio, "otros" sigue en cero y lo captura el
    # consultor si hace falta.
    assert otros_de(70) == Decimal("0")
    # Lo recoge en el aeropuerto: una vuelta.
    assert otros_de(71, origen_aeropuerto=True) == Decimal("100")
    # Lo recoge y lo deja el mismo dia: dos.
    assert otros_de(72, origen_aeropuerto=True,
                    vuelo_tipo="salida") == Decimal("200")


def test_el_estacionamiento_tambien_aplica_en_transfer(cliente, sesion, datos):
    """Un transfer al aeropuerto es justo el caso: entra, espera y sale."""
    h = sesion("consultor")
    corto = _montos(cliente, h, datos, "transfer", 73, hora="09:00:00",
                    origen_aeropuerto=True)
    assert corto["otros"] == Decimal("100")


def test_ningun_renglon_trae_centavos(cliente, sesion, datos):
    """El viatico se entrega en efectivo o por transferencia y nadie anda
    partiendo pesos. Todo sube al entero de arriba."""
    h = sesion("consultor")
    montos = _montos(cliente, h, datos, "transfer", 74, hora="09:00:00",
                     origen_aeropuerto=True, km_estimados=420)
    for concepto, monto in montos.items():
        assert monto == monto.to_integral_value(), concepto


def test_cada_tipo_de_servicio_lee_su_propia_tabla(cliente, sesion, datos):
    """Eventual e implantado no se gastan igual aunque la modalidad se
    llame igual, asi que cada uno lee su tabulador."""
    h = sesion("consultor")
    carlos = datos["personal"]["Carlos Vega"]["id"]

    for tipo in ("eventual", "implantado"):
        servicio = crear_servicio(cliente, h, datos, [jornada(
            manana(75 if tipo == "eventual" else 76),
            datos["modalidades"]["full_day"]["id"], hora="09:00:00")],
            tipo=tipo)
        j = servicio["equipos"][0]["jornadas"][0]
        asignar(cliente, h, j["id"], persona_id=carlos,
                vehiculo_id=datos["suburban"]["id"])
        propuesta = cliente.get(
            f"/viaticos/calcular?jornada_id={j['id']}&persona_id={carlos}",
            headers=h).json()
        assert propuesta["tipo_servicio"] == tipo
        assert propuesta["conceptos"], "cada tabla tiene que traer algo"


def test_el_combustible_se_estima_por_kilometros(cliente, sesion, datos):
    """420 km entre 5.5 km/l, por 24.50 el litro, mas 20% de holgura, y
    subido al entero de arriba: nadie deposita centavos."""
    _, j, persona = _jornada_con_viaticos(cliente, sesion, datos, 41, km=420)
    propuesta = cliente.get(
        f"/viaticos/calcular?jornada_id={j['id']}&persona_id={persona}",
        headers=sesion("consultor")).json()

    combustible = next(c for c in propuesta["conceptos"]
                       if c["concepto"] == "combustible")
    crudo = Decimal("420") / Decimal("5.5") * Decimal("24.50") * Decimal("1.20")
    esperado = crudo.to_integral_value(rounding=ROUND_CEILING)
    assert Decimal(str(combustible["monto"])) == esperado
    assert combustible["origen"] == "estimado"


def test_sin_kilometros_el_combustible_queda_manual(cliente, sesion, datos):
    """Vaciar los km a proposito es decir "no se cuantos son": el
    combustible se queda manual en vez de inventar un numero. Distinto de
    no capturarlos, que toma el recorrido tipico de la modalidad."""
    _, j, persona = _jornada_con_viaticos(cliente, sesion, datos, 42, km=None)
    propuesta = cliente.get(
        f"/viaticos/calcular?jornada_id={j['id']}&persona_id={persona}",
        headers=sesion("consultor")).json()
    combustible = next(c for c in propuesta["conceptos"]
                       if c["concepto"] == "combustible")
    assert combustible["origen"] == "manual"
    assert float(combustible["monto"]) == 0


def _asignar_viaticos(cliente, sesion, j, persona):
    h = sesion("consultor")
    propuesta = cliente.get(
        f"/viaticos/calcular?jornada_id={j['id']}&persona_id={persona}",
        headers=h).json()
    conceptos = [{"concepto": c["concepto"], "monto": str(c["monto"]),
                  "descripcion": c["descripcion"], "origen": c["origen"]}
                 for c in propuesta["conceptos"]]
    r = cliente.post("/viaticos/asignar",
                     json={"jornada_id": j["id"], "persona_id": persona,
                           "conceptos": conceptos}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_no_se_cierra_si_el_dinero_no_cuadra(cliente, sesion, datos):
    _, j, persona = _jornada_con_viaticos(cliente, sesion, datos, 43)
    viatico = _asignar_viaticos(cliente, sesion, j, persona)
    h = sesion("consultor")

    solicitud = cliente.post(f"/viaticos/{viatico['id']}/solicitar-transferencia",
                             headers=h).json()
    cliente.post("/viaticos/transferencias/barrido", headers=sesion("finanzas"))
    cliente.post(f"/viaticos/transferencias/{solicitud['id']}/confirmar",
                 headers=sesion("finanzas"))

    cliente.post(f"/viaticos/{viatico['id']}/comprobantes",
                 json={"concepto": "alimentos", "tipo": "nota", "monto": "450"},
                 headers=sesion("carlos"))

    estado = cliente.get(f"/viaticos/{viatico['id']}", headers=h).json()
    for comp in estado["comprobantes"]:
        cliente.post(f"/viaticos/{viatico['id']}/validar-comprobante/{comp['id']}",
                     headers=h)

    cierre = cliente.post(f"/viaticos/{viatico['id']}/cerrar", headers=h).json()
    assert cierre["resultado"] == "pendiente"
    assert "Sobran" in cierre["mensaje"]


def test_se_cierra_cuando_se_devuelve_el_sobrante(cliente, sesion, datos):
    _, j, persona = _jornada_con_viaticos(cliente, sesion, datos, 44)
    viatico = _asignar_viaticos(cliente, sesion, j, persona)
    h = sesion("consultor")

    solicitud = cliente.post(f"/viaticos/{viatico['id']}/solicitar-transferencia",
                             headers=h).json()
    cliente.post("/viaticos/transferencias/barrido", headers=sesion("finanzas"))
    cliente.post(f"/viaticos/transferencias/{solicitud['id']}/confirmar",
                 headers=sesion("finanzas"))

    cliente.post(f"/viaticos/{viatico['id']}/comprobantes",
                 json={"concepto": "alimentos", "tipo": "factura", "monto": "450"},
                 headers=sesion("carlos"))

    estado = cliente.get(f"/viaticos/{viatico['id']}", headers=h).json()
    for comp in estado["comprobantes"]:
        cliente.post(f"/viaticos/{viatico['id']}/validar-comprobante/{comp['id']}",
                     headers=h)

    sobrante = float(estado["monto_total"]) - float(estado["monto_comprobado"])
    # La devolucion la captura finanzas, que es quien mira la cuenta.
    from ayudas import devolver
    devolver(cliente, sesion("finanzas"), viatico["id"], f"{sobrante:.2f}")

    cierre = cliente.post(f"/viaticos/{viatico['id']}/cerrar", headers=h).json()
    assert cierre["resultado"] == "cerrado"


def test_el_personal_solo_comprueba_lo_suyo(cliente, sesion, datos):
    _, j, persona = _jornada_con_viaticos(cliente, sesion, datos, 45)
    viatico = _asignar_viaticos(cliente, sesion, j, persona)

    ajeno = cliente.post(f"/viaticos/{viatico['id']}/comprobantes",
                         json={"concepto": "alimentos", "tipo": "nota", "monto": "100"},
                         headers=sesion("juan"))
    assert ajeno.status_code == 403


def test_la_ventana_de_transferencia_respeta_el_dia_previo(cliente, sesion, datos):
    _, lejano, _ = _jornada_con_viaticos(cliente, sesion, datos, 46)
    r = cliente.get(f"/viaticos/transferencias/ventana?jornada_id={lejano['id']}",
                    headers=sesion("consultor")).json()
    assert r["inmediata"] is False

    _, manana_, _ = _jornada_con_viaticos(cliente, sesion, datos, 1)
    r2 = cliente.get(f"/viaticos/transferencias/ventana?jornada_id={manana_['id']}",
                     headers=sesion("consultor")).json()
    assert r2["inmediata"] is True


def test_el_barrido_pospone_lo_que_no_toca(cliente, sesion, datos):
    _, lejano, persona = _jornada_con_viaticos(cliente, sesion, datos, 47)
    viatico = _asignar_viaticos(cliente, sesion, lejano, persona)
    cliente.post(f"/viaticos/{viatico['id']}/solicitar-transferencia",
                 headers=sesion("consultor"))

    lote = cliente.post("/viaticos/transferencias/barrido",
                        headers=sesion("finanzas")).json()
    assert lote["enviadas"] == 0
    assert lote["pospuestas"] == 1


# ------------------------------------------- cierre forzado por el consultor

def _viatico_transferido(cliente, sesion, datos, offset):
    """Viaticos ya en manos del conductor, listos para comprobar."""
    h = sesion("consultor")
    _, j, persona = _jornada_con_viaticos(cliente, sesion, datos, offset)
    viatico = _asignar_viaticos(cliente, sesion, j, persona)
    solicitud = cliente.post(f"/viaticos/{viatico['id']}/solicitar-transferencia",
                             headers=h).json()
    cliente.post(f"/viaticos/transferencias/{solicitud['id']}/confirmar",
                 headers=sesion("finanzas"))
    return viatico, j, persona


def _plazo_vencido(viatico_id, horas=1):
    """Su plazo para comprobar ya paso. Cerrar con descuento solo se
    puede despues del plazo (decision de Salvador, 23 sep)."""
    from datetime import datetime, timedelta

    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        v = db.get(m.AsignacionViatico, viatico_id)
        v.limite_comprobacion = datetime.now() - timedelta(hours=horas)
        db.commit()


def test_un_gasto_rechazado_deja_de_contar_como_comprobado(cliente, sesion, datos):
    viatico, _, _ = _viatico_transferido(cliente, sesion, datos, 300)
    h = sesion("consultor")

    cliente.post(f"/viaticos/{viatico['id']}/comprobantes",
                 json={"concepto": "otros", "tipo": "nota", "monto": "900",
                       "descripcion": "Compra personal"},
                 headers=sesion("carlos"))
    estado = cliente.get(f"/viaticos/{viatico['id']}", headers=h).json()
    antes = Decimal(str(estado["monto_comprobado"]))
    comprobante = estado["comprobantes"][0]

    r = cliente.post(
        f"/viaticos/{viatico['id']}/rechazar-comprobante/{comprobante['id']}",
        params={"motivo": "No corresponde al servicio"}, headers=h)
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["comprobado_ahora"])) == antes - Decimal("900")


def test_el_consultor_cierra_y_manda_a_descuento(cliente, sesion, datos):
    """El conductor no pudo resolver: el consultor cierra por el."""
    viatico, j, persona = _viatico_transferido(cliente, sesion, datos, 310)
    _plazo_vencido(viatico["id"])
    h = sesion("consultor")

    r = cliente.post(f"/viaticos/{viatico['id']}/cerrar-con-descuento",
                     json={"motivo": "No presento comprobacion en 5 dias"},
                     headers=h)
    assert r.status_code == 200, r.text
    resultado = r.json()
    asignado = Decimal(str(resultado["asignado"]))
    assert Decimal(str(resultado["descontado_al_personal"])) == asignado
    assert Decimal(str(resultado["absorbido_por_la_empresa"])) == 0

    # El descuento espera en la nomina, con signo negativo.
    pendientes = cliente.get("/nomina/ajustes/pendientes",
                             params={"pais_id": datos["mx"]["id"]},
                             headers=sesion("finanzas")).json()
    assert len(pendientes) == 1
    assert pendientes[0]["sentido"] == "descuento"
    assert Decimal(str(pendientes[0]["monto"])) == -asignado


def test_la_empresa_puede_absorber_pero_tiene_que_decir_por_que(cliente, sesion,
                                                                datos):
    viatico, _, _ = _viatico_transferido(cliente, sesion, datos, 320)
    _plazo_vencido(viatico["id"])
    h = sesion("consultor")

    sin_motivo = cliente.post(f"/viaticos/{viatico['id']}/cerrar-con-descuento",
                              json={"motivo": "Perdio los tickets",
                                    "monto_descuento": "100"},
                              headers=h)
    assert sin_motivo.status_code == 409

    con_motivo = cliente.post(f"/viaticos/{viatico['id']}/cerrar-con-descuento",
                              json={"motivo": "Perdio los tickets",
                                    "monto_descuento": "100",
                                    "motivo_absorcion": "Gasto real del servicio"},
                              headers=h)
    assert con_motivo.status_code == 200, con_motivo.text
    assert Decimal(str(con_motivo.json()["descontado_al_personal"])) == 100
    assert Decimal(str(con_motivo.json()["absorbido_por_la_empresa"])) > 0


def test_no_se_puede_descontar_mas_de_lo_pendiente(cliente, sesion, datos):
    viatico, _, _ = _viatico_transferido(cliente, sesion, datos, 330)
    _plazo_vencido(viatico["id"])
    r = cliente.post(f"/viaticos/{viatico['id']}/cerrar-con-descuento",
                     json={"motivo": "Prueba", "monto_descuento": "999999"},
                     headers=sesion("consultor"))
    assert r.status_code == 409


def test_si_todo_cuadra_no_aplica_el_cierre_con_descuento(cliente, sesion, datos):
    viatico, _, _ = _viatico_transferido(cliente, sesion, datos, 340)
    _plazo_vencido(viatico["id"])
    h = sesion("consultor")
    total = Decimal(str(viatico["monto_total"]))
    cliente.post(f"/viaticos/{viatico['id']}/comprobantes",
                 json={"concepto": "alimentos", "tipo": "factura",
                       "monto": str(total)},
                 headers=sesion("carlos"))

    r = cliente.post(f"/viaticos/{viatico['id']}/cerrar-con-descuento",
                     json={"motivo": "No aplica"}, headers=h)
    assert r.status_code == 409


# ================== la app no dice "te depositaron" antes del deposito
#
# Encontrado en la calle el 21 de septiembre. La app sumaba el monto
# AUTORIZADO y lo rotulaba "te depositaron": alguien leia que ya tenia el
# dinero, salia a trabajar contando con el, y no estaba.
#
# Y pesaba mas de lo que parece: ese monto entraba a "te falta comprobar"
# y le corria el plazo de 24 horas, asi que podia quedar vencido por un
# dinero que nunca recibio.

def _mis_viaticos(cliente, sesion, quien="carlos"):
    r = cliente.get("/campo/mis-viaticos", headers=sesion(quien))
    assert r.status_code == 200, r.text
    return r.json()


def test_lo_autorizado_no_se_dice_depositado(cliente, sesion, datos):
    """Autorizado y depositado son dos cosas, y entre una y otra pasa
    finanzas. Hasta entonces el dinero existe en el sistema y no en su
    cuenta."""
    _, j, persona = _jornada_con_viaticos(cliente, sesion, datos, 44)
    viatico = _asignar_viaticos(cliente, sesion, j, persona)
    assert float(viatico["monto_total"]) > 0

    d = _mis_viaticos(cliente, sesion)
    suyo = next(s for s in d["servicios"]
                if any(x["viatico_id"] == viatico["id"] for x in s["dias"]))

    assert float(suyo["entregado"]) == 0, \
        "todavia no sale del banco: no se le puede decir que ya lo tiene"
    assert float(suyo["por_depositar"]) > 0, \
        "y se dice aparte, con su nombre, en vez de esconderlo"

    # Lo que de verdad importa: no se le pide comprobar lo que no recibio,
    # ni le corre el plazo por ello.
    assert float(suyo["por_comprobar"]) == 0
    assert suyo["vencido"] is False


def test_cuando_finanzas_deposita_la_app_lo_dice(cliente, sesion, datos):
    """Y entonces si: el dinero esta con la persona, aparece como
    entregado y empieza a correr su comprobacion."""
    from ayudas import depositar_de_verdad

    servicio, j, persona = _jornada_con_viaticos(cliente, sesion, datos, 45)
    viatico = _asignar_viaticos(cliente, sesion, j, persona)

    depositar_de_verdad(cliente, sesion, servicio["equipos"][0]["id"], persona)

    d = _mis_viaticos(cliente, sesion)
    suyo = next(s for s in d["servicios"]
                if any(x["viatico_id"] == viatico["id"] for x in s["dias"]))
    assert float(suyo["entregado"]) > 0
    assert float(suyo["por_depositar"]) == 0
    assert float(suyo["por_comprobar"]) > 0

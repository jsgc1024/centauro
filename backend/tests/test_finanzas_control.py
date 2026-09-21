"""El control del dinero que sale a la calle.

Esta pantalla maneja los gastos del servicio —viaticos y compras— y no
la nomina del personal de seguridad, que va por su cuenta.

Lo que se prueba: que finanzas tenga memoria de lo que pago, que sepa
cuanto anda afuera sin comprobar, y que un deposito no se confirme dos
veces.
"""

from ayudas import asignar, crear_servicio, jornada, manana


def _con_viaticos(cliente, sesion, datos, monto="3000", dia=20,
                  quien="Juan Ramirez"):
    """Un eventual con una persona y su deposito ya solicitado.

    El dia y la persona se pueden cambiar porque nadie puede estar en dos
    servicios el mismo dia: dos escenarios en la misma fecha con la
    misma gente chocan, y el choque es correcto.
    """
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(dia), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    equipo_id = servicio["equipos"][0]["id"]
    juan = datos["personal"][quien]["id"]
    r = asignar(cliente, h, j["id"], persona_id=juan,
                vehiculo_id=datos["suburban"]["id"])[0]
    assert r.status_code == 200, r.text

    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                     json={"persona_id": juan, "monto": monto}, headers=h)
    assert r.status_code == 200, r.text
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar", json={},
                     headers=h)
    assert r.status_code == 200, r.text
    return servicio, equipo_id, juan


def _solicitud_de(cliente, h, folio):
    bandeja = cliente.get("/viaticos/finanzas/bandeja", headers=h).json()
    for pais in bandeja["paises"]:
        for d in pais["depositos"]:
            if d["folio"] == folio:
                return d
    raise AssertionError(f"{folio} no esta en la bandeja")


def test_el_deposito_queda_firmado(cliente, sesion, datos):
    """Quien lo despacho y cuando. Sin eso, en cuanto el renglon sale de
    la bandeja no hay forma de saber si ya se pago."""
    servicio, _, juan = _con_viaticos(cliente, sesion, datos)
    f = sesion("finanzas")
    deposito = _solicitud_de(cliente, f, servicio["folio"])

    for solicitud_id in deposito["solicitudes"]:
        r = cliente.post(
            f"/viaticos/transferencias/{solicitud_id}/confirmar"
            f"?referencia_odoo=TR-9001", headers=f)
        assert r.status_code == 200, r.text

    historial = cliente.get("/viaticos/finanzas/depositado", headers=f).json()
    suyos = [d for pais in historial["paises"] for d in pais["depositos"]
             if d["folio"] == servicio["folio"]]
    assert suyos, "el deposito no quedo en el historial"
    assert all(d["referencia"] == "TR-9001" for d in suyos)
    assert all(d["confirmada_en"] for d in suyos)
    assert all(d["despacho"] == "Jorge Diaz" for d in suyos), suyos
    # Lo que llega por esta puerta --el barrido por lote, lo que viene
    # ya confirmado de Odoo-- no trae captura del banco: no hay una
    # persona subiendola. Se ve el hueco en vez de esconderlo.
    assert all(d["tiene_comprobante"] is False for d in suyos)


def test_un_deposito_no_se_confirma_dos_veces(cliente, sesion, datos):
    """Confirmar dos veces el mismo deposito es como se paga dos veces."""
    servicio, _, _ = _con_viaticos(cliente, sesion, datos)
    f = sesion("finanzas")
    solicitud_id = _solicitud_de(cliente, f,
                                 servicio["folio"])["solicitudes"][0]

    assert cliente.post(f"/viaticos/transferencias/{solicitud_id}/confirmar",
                        headers=f).status_code == 200
    r = cliente.post(f"/viaticos/transferencias/{solicitud_id}/confirmar",
                     headers=f)
    assert r.status_code == 409, r.text
    assert "ya estaba confirmado" in str(r.json()["detail"])


def test_lo_depositado_sale_del_historial_y_no_de_la_bandeja(cliente, sesion,
                                                             datos):
    """La bandeja es lo que falta por pagar; el historial es lo que ya se
    pago. Un renglon no puede estar en los dos."""
    servicio, _, _ = _con_viaticos(cliente, sesion, datos)
    f = sesion("finanzas")
    for sid in _solicitud_de(cliente, f, servicio["folio"])["solicitudes"]:
        cliente.post(f"/viaticos/transferencias/{sid}/confirmar", headers=f)

    bandeja = cliente.get("/viaticos/finanzas/bandeja", headers=f).json()
    pendientes = [d for p in bandeja["paises"] for d in p["depositos"]
                  if d["folio"] == servicio["folio"]]
    assert not pendientes, "sigue en la bandeja despues de pagarse"


def test_el_dinero_afuera_se_ve_con_su_limite(cliente, sesion, datos):
    """Lo transferido y sin comprobar es lo que la empresa trae en la
    calle. Es la cuenta que nadie estaba llevando."""
    servicio, _, juan = _con_viaticos(cliente, sesion, datos, monto="2500")
    f = sesion("finanzas")
    for sid in _solicitud_de(cliente, f, servicio["folio"])["solicitudes"]:
        cliente.post(f"/viaticos/transferencias/{sid}/confirmar", headers=f)

    afuera = cliente.get("/viaticos/finanzas/por-comprobar", headers=f).json()
    suyos = [x for p in afuera["paises"] for x in p["personas"]
             if x["folio"] == servicio["folio"]]
    assert suyos, "el dinero transferido no aparece como afuera"
    x = suyos[0]
    assert float(x["entregado"]) == 2500
    assert float(x["comprobado"]) == 0
    assert float(x["pendiente"]) == 2500
    assert x["persona_id"] == juan


def test_el_corte_separa_comprometido_de_afuera(cliente, sesion, datos):
    """Comprometido es lo pedido y sin salir; afuera es lo que salio y no
    se ha comprobado. Confundirlos es como se acaba el mes creyendo que
    se debe menos de lo que se debe."""
    servicio, _, _ = _con_viaticos(cliente, sesion, datos, monto="1800")
    f = sesion("finanzas")

    antes = cliente.get("/viaticos/finanzas/corte", headers=f).json()
    mx = next(p for p in antes["paises"] if p["codigo"] == "MX")
    assert float(mx["comprometido"]) >= 1800
    comprometido_antes = float(mx["comprometido"])

    for sid in _solicitud_de(cliente, f, servicio["folio"])["solicitudes"]:
        cliente.post(f"/viaticos/transferencias/{sid}/confirmar", headers=f)

    despues = cliente.get("/viaticos/finanzas/corte", headers=f).json()
    mx = next(p for p in despues["paises"] if p["codigo"] == "MX")
    # El dinero se movio de un lado al otro: ya no esta comprometido,
    # ahora esta afuera.
    assert float(mx["comprometido"]) == comprometido_antes - 1800
    assert float(mx["afuera"]) >= 1800
    assert float(mx["depositado_mes"]) >= 0


def test_el_historial_se_puede_buscar_por_folio(cliente, sesion, datos):
    servicio, _, _ = _con_viaticos(cliente, sesion, datos)
    # Otro dia y otra persona: nadie esta en dos servicios a la vez.
    otro, _, _ = _con_viaticos(cliente, sesion, datos, dia=21,
                               quien="Luis Mendoza")
    f = sesion("finanzas")
    for s_ in (servicio, otro):
        for sid in _solicitud_de(cliente, f, s_["folio"])["solicitudes"]:
            cliente.post(f"/viaticos/transferencias/{sid}/confirmar", headers=f)

    r = cliente.get(f"/viaticos/finanzas/depositado?folio={servicio['folio']}",
                    headers=f).json()
    folios = {d["folio"] for p in r["paises"] for d in p["depositos"]}
    assert folios == {servicio["folio"]}, folios


def test_lo_de_afuera_se_cuenta_por_persona_y_servicio(cliente, sesion, datos):
    """La deuda es una sola, aunque el servicio dure tres dias.

    Cada dia se juzgaba solo: un gasto cargado en el dia 1 dejaba ese
    dia fuera de la lista y los otros dos enteros, asi que finanzas leia
    una deuda mas grande que la real y salia a perseguir dinero que ya
    estaba comprobado. Es la pantalla de quien paga: aqui la resta tiene
    que cuadrar.
    """
    from ayudas import (asignar, crear_servicio, depositar_de_verdad,
                        jornada, manana)

    h = sesion("consultor")
    f = sesion("finanzas")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(940 + i), datos["modalidades"]["full_day"]["id"])
         for i in range(3)])
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"], persona_id=juan)

    equipo_id = servicio["equipos"][0]["id"]
    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": juan, "monto": "3000"}, headers=h)
    depositar_de_verdad(cliente, sesion, equipo_id, juan)

    mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
    fila = next(s for s in mios["servicios"]
                if s["folio"] == servicio["folio"])
    cliente.post(f"/campo/viaticos/{fila['dias'][0]['viatico_id']}/comprobante",
                 json={"concepto": "combustible", "tipo": "nota",
                       "monto": "2800"}, headers=sesion("juan"))

    afuera = cliente.get("/viaticos/finanzas/por-comprobar", headers=f).json()
    suyos = [x for p in afuera["paises"] for x in p["personas"]
             if x["folio"] == servicio["folio"]]
    assert len(suyos) == 1, "tres dias, tres renglones: la deuda es una"
    x = suyos[0]
    assert x["dias"] == 3
    assert float(x["entregado"]) == 3000
    assert float(x["comprobado"]) == 2800
    assert float(x["pendiente"]) == 200


def test_el_implantado_deposita_un_mes_a_la_vez(cliente, sesion, datos):
    """Cada deposito corresponde a su mes.

    La bandeja agrupaba por equipo y persona, y en un implantado el
    equipo abarca meses enteros: septiembre y octubre caian en el mismo
    renglon, se depositaban de un golpe y la pantalla del consultor los
    mostraba partidos despues, sin que nadie hubiera decidido ese
    reparto.
    """
    from datetime import date

    h = sesion("consultor")
    f = sesion("finanzas")
    juan = datos["personal"]["Juan Ramirez"]["id"]

    servicio = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "implantado",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}, headers=h).json()

    # Dos meses abiertos, con su plantilla.
    for anio, mes in ((2029, 1), (2029, 2)):
        contrato = cliente.post("/implantados/contratos", json={
            "servicio_id": servicio["id"], "anio": anio, "mes": mes,
            "modalidad_id": datos["modalidades"]["full_day"]["id"],
            "esquema": "por_dia", "incluye_fines_de_semana": False,
            "hora_presentacion": "08:00:00", "titular_id": juan,
            "vehiculo_id": datos["suburban"]["id"],
            "precio_mes_vehiculo": "66000", "precio_dia_personal": "2900",
            "precio_dia_adicional": "3500"}, headers=h).json()
        cliente.post(
            f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
            headers=h)
        r = cliente.post(
            f"/implantados/{servicio['id']}/viaticos/{anio}/{mes}/persona",
            json={"persona_id": juan, "monto": "1000"}, headers=h)
        assert r.status_code == 200, r.text
        cliente.post(
            f"/implantados/{servicio['id']}/viaticos/{anio}/{mes}/solicitar",
            json={"persona_id": juan}, headers=h)

    bandeja = cliente.get("/viaticos/finanzas/bandeja", headers=f).json()
    suyos = [d for p in bandeja["paises"] for d in p["depositos"]
             if d["servicio_id"] == servicio["id"]]
    assert len(suyos) == 2, "los dos meses cayeron en un solo deposito"
    assert {d["periodo"] for d in suyos} == {"01/2029", "02/2029"}

    # Y depositar uno no da por depositado el otro.
    enero = next(d for d in suyos if d["periodo"] == "01/2029")
    import io as _io

    from ayudas import PIXEL

    r = cliente.post(
        "/viaticos/finanzas/depositar", headers=f,
        data={"equipo_id": enero["equipo_id"], "persona_id": juan,
              "anio": 2029, "mes": 1, "referencia": "SPEI-1"},
        files={"archivo": ("dep.png", _io.BytesIO(PIXEL), "image/png")})
    assert r.status_code == 200, r.text

    quedan = cliente.get("/viaticos/finanzas/bandeja", headers=f).json()
    suyos = [d for p in quedan["paises"] for d in p["depositos"]
             if d["servicio_id"] == servicio["id"]]
    assert len(suyos) == 1, "se depositaron los dos meses de un golpe"
    assert suyos[0]["periodo"] == "02/2029"

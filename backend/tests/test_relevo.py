"""El relevo a media jornada.

Quien se presenta a las siete, trabaja cuatro horas y lo relevan, cobra
su dia. Antes no: el reemplazo mutaba la asignacion —`persona_id`
cambiaba de dueno— y como la nomina paga por asignacion, el que trabajo
desaparecia del dia y cobraba cero. Nada en el sistema recordaba que
estuvo ahi.

Ahora el dia del cambio se parte en dos. Eso deja el mismo dia con dos
personas en la base, y esa es justo la parte que hay que verificar de los
dos lados:

  - a la EMPRESA le cuestan las dos, y las dos salen en la nomina,
  - al CLIENTE se le cobra una, porque tuvo un conductor, no dos.

La diferencia es el costo de la contingencia.

Y la regla que lo cierra: cobra el dia quien alcanzo a marcar su llegada.
Quien no se presento no trabajo, y relevarlo es cambiar un nombre en una
lista.
"""
from datetime import datetime, timedelta

from ayudas import (asignar, configurar_origen, cotizar_y_autorizar,
                    crear_servicio, jornada, manana, marcar, marcar_fin)


def _montado(cliente, sesion, datos, offset=300, dias=2):
    """Un servicio de dos dias con Juan y la Suburban, cotizado."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"])
         for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    cotizar_y_autorizar(
        cliente, h, servicio, datos["perfiles"]["conductor_seguridad"]["id"],
        datos["categorias"]["suv_blindada"]["id"])
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])
        configurar_origen(cliente, h, j["id"])
    return servicio


def _se_presenta(cliente, sesion, j):
    """Juan llega y hace contacto: ya trabajo."""
    inicio = datetime.fromisoformat(j["inicio_programado"])
    r = marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
               inicio - timedelta(minutes=10))
    assert r.status_code == 200, r.text
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo", inicio)


def _cambio(datos, j, motivo="Se sintio mal", **extra):
    """El cuerpo del cambio: siempre sale Juan y entra Luis."""
    return {"desde_jornada_id": j["id"],
            "sale_persona_id": datos["personal"]["Juan Ramirez"]["id"],
            "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
            "motivo": motivo, **extra}


def _relevo(cliente, sesion, datos, j, motivo="Se sintio mal", **extra):
    return cliente.post("/contingencia/reemplazos/personal",
                        headers=sesion("consultor"),
                        json=_cambio(datos, j, motivo, **extra))


def _a_finanzas(cliente, sesion, servicio):
    """Cierra el servicio y lo manda a facturacion, que es lo que deja
    entrar las jornadas al corte de nomina."""
    h = sesion("consultor")
    cierre = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir",
                          headers=h).json()
    r = cliente.post(f"/cierre/{cierre['cierre_id']}/enviar-finanzas", headers=h)
    assert r.status_code == 200, r.text
    return cierre


def _nomina(cliente, sesion, datos):
    """Calcula el corte y devuelve su detalle, que es donde estan los
    renglones por persona."""
    f = sesion("finanzas")
    r = cliente.post("/nomina/calcular", json={"pais_id": datos["mx"]["id"]},
                     headers=f)
    assert r.status_code == 200, r.text
    return cliente.get(f"/nomina/{r.json()['nomina_id']}", headers=f).json()


def _asignados(cliente, sesion, jornada_id):
    r = cliente.get(f"/servicios/jornadas/{jornada_id}/asignaciones",
                    headers=sesion("consultor"))
    return [p["nombre"] for p in r.json()["personal"]]


# ================================================== el dia se parte

def test_el_que_trabajo_medio_dia_sigue_en_el_dia(cliente, sesion, datos):
    """El agujero que esto vino a tapar."""
    servicio = _montado(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    _se_presenta(cliente, sesion, j)

    r = _relevo(cliente, sesion, datos, j)
    assert r.status_code == 200, r.text
    assert r.json()["jornadas_partidas"] == [j["fecha"]], r.json()

    quienes = _asignados(cliente, sesion, j["id"])
    assert "Juan Ramirez" in quienes, "el que trabajo desaparecio del dia"
    assert "Luis Mendoza" in quienes


def test_el_que_no_se_presento_no_deja_rastro(cliente, sesion, datos):
    """Sin marcar la llegada no hay nada que pagar ni que partir: el dia
    cambia de dueno y ya."""
    servicio = _montado(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    r = _relevo(cliente, sesion, datos, j, motivo="No se presento")
    assert r.status_code == 200, r.text
    assert r.json()["jornadas_partidas"] == []

    quienes = _asignados(cliente, sesion, j["id"])
    assert quienes == ["Luis Mendoza"], quienes


def test_los_dias_que_siguen_cambian_de_dueno(cliente, sesion, datos):
    """Nadie los trabajo todavia: no hay nada que partir."""
    servicio = _montado(cliente, sesion, datos, dias=3)
    dias = servicio["equipos"][0]["jornadas"]
    _se_presenta(cliente, sesion, dias[0])

    r = _relevo(cliente, sesion, datos, dias[0])
    assert len(r.json()["jornadas_afectadas"]) == 3
    assert r.json()["jornadas_partidas"] == [dias[0]["fecha"]]

    assert _asignados(cliente, sesion, dias[1]["id"]) == ["Luis Mendoza"]


def test_el_cambio_puede_tener_fin(cliente, sesion, datos):
    """Una contingencia no tiene fin; unas vacaciones si. Decirlo evita
    que el titular regrese y nadie se acuerde de devolverle sus dias."""
    servicio = _montado(cliente, sesion, datos, dias=3)
    dias = servicio["equipos"][0]["jornadas"]

    r = _relevo(cliente, sesion, datos, dias[0], motivo="Vacaciones",
                motivo_tipo="vacaciones", hasta_jornada_id=dias[1]["id"])
    assert r.status_code == 200, r.text
    assert len(r.json()["jornadas_afectadas"]) == 2

    # El tercer dia sigue siendo del titular.
    assert _asignados(cliente, sesion, dias[2]["id"]) == ["Juan Ramirez"]


# ================================================== el dinero

def test_los_dos_cobran_su_dia(cliente, sesion, datos):
    """A la empresa le costaron los dos. Es el costo de la contingencia,
    y hasta ahora se lo estaba comiendo el que trabajo."""
    servicio = _montado(cliente, sesion, datos, dias=1)
    j = servicio["equipos"][0]["jornadas"][0]
    _se_presenta(cliente, sesion, j)
    relevo = _relevo(cliente, sesion, datos, j)
    assert relevo.status_code == 200, relevo.text

    # Luis termina la jornada y el servicio se va a facturacion.
    fin = datetime.fromisoformat(j["fin_programado"])
    marcar_fin(cliente, sesion("luis"), j["id"], fin)
    _a_finanzas(cliente, sesion, servicio)

    quienes = {x["persona"] for x in _nomina(cliente, sesion, datos)["renglones"]}
    assert "Juan Ramirez" in quienes, "el relevado no cobro su dia"
    assert "Luis Mendoza" in quienes


def test_al_cliente_se_le_cobra_un_solo_conductor(cliente, sesion, datos):
    """Ese dia el cliente tuvo un conductor, aunque en la base haya dos."""
    servicio = _montado(cliente, sesion, datos, dias=1)
    j = servicio["equipos"][0]["jornadas"][0]
    _se_presenta(cliente, sesion, j)
    assert _relevo(cliente, sesion, datos, j).status_code == 200

    fin = datetime.fromisoformat(j["fin_programado"])
    marcar_fin(cliente, sesion("luis"), j["id"], fin)
    h = sesion("consultor")
    cliente.post(f"/cierre/servicio/{servicio['id']}/abrir", headers=h)

    comp = cliente.get(f"/cierre/servicio/{servicio['id']}/comparativo",
                       headers=h).json()
    # Se cotizo un conductor y una unidad, y eso se ejecuto. Si la
    # asignacion relevada se le cobrara al cliente, lo ejecutado saldria
    # por encima de lo cotizado justo en el precio de un conductor.
    assert float(comp["diferencia"]) == 0, comp


def test_las_horas_extra_son_de_quien_se_quedo(cliente, sesion, datos):
    """El relevado cobra su dia, no las horas de mas que no trabajo."""
    servicio = _montado(cliente, sesion, datos, dias=1)
    j = servicio["equipos"][0]["jornadas"][0]
    _se_presenta(cliente, sesion, j)
    relevo = _relevo(cliente, sesion, datos, j)
    assert relevo.status_code == 200, relevo.text

    fin = datetime.fromisoformat(j["fin_programado"])
    marcar_fin(cliente, sesion("luis"), j["id"], fin + timedelta(hours=2))
    _a_finanzas(cliente, sesion, servicio)

    suyos = {x["persona"]: x for x in _nomina(cliente, sesion, datos)["renglones"]}
    juan, luis = suyos["Juan Ramirez"], suyos["Luis Mendoza"]
    assert all(c["horas_extra"] == 0 for c in juan["conceptos"]), juan
    assert any(c["horas_extra"] == 2 for c in luis["conceptos"]), luis


# ================================================== la vista previa

def test_la_vista_previa_no_guarda_nada(cliente, sesion, datos):
    """Se ejecuta el cambio de verdad y se deshace: no hay una segunda
    implementacion que calcule "lo que pasaria" y se separe de la
    primera."""
    servicio = _montado(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    _se_presenta(cliente, sesion, j)

    r = cliente.post("/contingencia/reemplazos/personal/vista-previa",
                     headers=sesion("consultor"),
                     json=_cambio(datos, j))
    assert r.status_code == 200, r.text
    assert r.json()["jornadas_partidas"] == [j["fecha"]]

    # Y sin embargo no paso nada.
    assert _asignados(cliente, sesion, j["id"]) == ["Juan Ramirez"]
    historial = cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                            headers=sesion("consultor")).json()
    assert historial == []


# ================================================== deshacer

def test_deshacer_devuelve_el_dia_a_su_dueno(cliente, sesion, datos):
    """Para el consultor que se equivoco de persona hace un minuto."""
    servicio = _montado(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    _se_presenta(cliente, sesion, j)
    hecho = _relevo(cliente, sesion, datos, j).json()

    r = cliente.post(f"/contingencia/reemplazos/{hecho['reemplazo_id']}/deshacer",
                     headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert _asignados(cliente, sesion, j["id"]) == ["Juan Ramirez"]

    historial = cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                            headers=sesion("consultor")).json()
    assert historial == []


def test_no_se_deshace_si_el_dinero_ya_se_movio(cliente, sesion, datos):
    """En cuanto hay una transferencia y un plazo corriendo, deshacer a
    mano seria peor que el error."""
    servicio = _montado(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    h = sesion("consultor")

    # Juan sale con dinero encima.
    viatico = cliente.post(
        "/viaticos/asignar", headers=h,
        json={"jornada_id": j["id"],
              "persona_id": datos["personal"]["Juan Ramirez"]["id"],
              "conceptos": [{"concepto": "alimentos", "monto": "500",
                             "origen": "tabulador"}]}).json()
    solicitud = cliente.post(f"/viaticos/{viatico['id']}/solicitar-transferencia",
                             headers=h).json()
    confirmada = cliente.post(
        f"/viaticos/transferencias/{solicitud['id']}/confirmar",
        params={"referencia_odoo": "TRX-900"}, headers=sesion("finanzas"))
    assert confirmada.status_code == 200, confirmada.text

    _se_presenta(cliente, sesion, j)
    hecho = _relevo(cliente, sesion, datos, j).json()

    r = cliente.post(f"/contingencia/reemplazos/{hecho['reemplazo_id']}/deshacer",
                     headers=h)
    assert r.status_code == 409, r.text
    # Y el cambio sigue en pie: no se deshizo a medias.
    assert "Luis Mendoza" in _asignados(cliente, sesion, j["id"])


# ================================================== el regreso del titular

def _regreso(cliente, sesion, reemplazo_id, dia, **extra):
    return cliente.post(f"/contingencia/reemplazos/{reemplazo_id}/regreso",
                        headers=sesion("consultor"),
                        json={"desde": dia, **extra})


def test_el_regreso_cierra_el_cambio_no_abre_otro(cliente, sesion, datos):
    """Un solo hecho: "Luis cubrio a Juan del 2 al 3".

    Si el regreso abriera su propio movimiento, el mismo mes mostraria
    dos cambios cruzados —Luis por Juan, Juan por Luis— y nadie sabria
    cual cierra a cual. El regreso recorre el `hasta` del que ya existe.
    """
    servicio = _montado(cliente, sesion, datos, offset=520, dias=5)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")

    # Sin fecha de fin: del segundo dia en adelante es de Luis.
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()
    assert hecho["jornadas_afectadas"] == [d["fecha"] for d in dias[1:]]

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[3]["fecha"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["regresa"] == "Juan Ramirez"
    assert cuerpo["sale"] == "Luis Mendoza"
    assert cuerpo["desde"] == dias[1]["fecha"]
    assert cuerpo["hasta"] == dias[2]["fecha"]
    assert cuerpo["dias_cubiertos"] == 2

    esperado = ["Juan Ramirez", "Luis Mendoza", "Luis Mendoza",
                "Juan Ramirez", "Juan Ramirez"]
    for dia, quien in zip(dias, esperado):
        assert _asignados(cliente, sesion, dia["id"]) == [quien], dia["fecha"]

    # Un movimiento, no dos.
    historial = cliente.get(
        f"/contingencia/reemplazos/servicio/{servicio['id']}", headers=h).json()
    assert len(historial) == 1, historial
    assert historial[0]["desde"] == dias[1]["fecha"]
    assert historial[0]["hasta"] == dias[2]["fecha"]
    assert historial[0]["jornadas_afectadas"] == 2
    assert historial[0]["regreso_en"], "no quedo firmado quien lo cerro"
    assert historial[0]["regreso_por"] == "Ana Solis"


def test_el_que_cubria_cobra_la_manana_del_dia_del_regreso(cliente, sesion, datos):
    """El regreso tambien parte el dia, con los nombres al reves.

    Si Luis alcanzo a marcar su llegada la manana que Juan volvio, ese
    dia lo trabajaron los dos y los dos lo cobran. Y ese dia sigue
    contando como cubierto por Luis: el `hasta` es ese, no el anterior.
    """
    servicio = _montado(cliente, sesion, datos, offset=600, dias=4)
    dias = servicio["equipos"][0]["jornadas"]
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()

    inicio = datetime.fromisoformat(dias[2]["inicio_programado"])
    llego = marcar(cliente, sesion("luis"), dias[2]["id"], "llegada_origen",
                   inicio - timedelta(minutes=10))
    assert llego.status_code == 200, llego.text

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[2]["fecha"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["jornadas_partidas"] == [dias[2]["fecha"]]
    assert cuerpo["hasta"] == dias[2]["fecha"]
    assert cuerpo["dias_cubiertos"] == 2

    # Ese dia el equipo tiene dos personas en el mismo rol: la que salio
    # a media jornada y la que entro.
    assert sorted(_asignados(cliente, sesion, dias[2]["id"])) == [
        "Juan Ramirez", "Luis Mendoza"]
    assert _asignados(cliente, sesion, dias[3]["id"]) == ["Juan Ramirez"]


def test_el_regreso_no_puede_ser_antes_de_que_empiece_el_cambio(cliente, sesion,
                                                                datos):
    """Si el cambio se hizo por error, se deshace; no se "regresa" al
    dia anterior."""
    servicio = _montado(cliente, sesion, datos, offset=640, dias=4)
    dias = servicio["equipos"][0]["jornadas"]
    hecho = _relevo(cliente, sesion, datos, dias[2]).json()

    for dia in (dias[1], dias[2]):
        r = _regreso(cliente, sesion, hecho["reemplazo_id"], dia["fecha"])
        assert r.status_code == 409, (dia["fecha"], r.text)

    # Y una sola vez: el segundo regreso ya no tiene que cerrar.
    assert _regreso(cliente, sesion, hecho["reemplazo_id"],
                    dias[3]["fecha"]).status_code == 200
    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[3]["fecha"])
    assert r.status_code == 409, r.text


def test_marta_regresa_a_su_implantado(cliente, sesion, datos):
    """La historia tal cual la conto la operacion.

    Juan trabaja hasta el 10 y se enferma; Luis lo releva y entra el 11.
    A los dias Juan se recupera, avisa al consultor, y el consultor
    coordina que regrese el 25: Luis trabaja hasta el 24 por orden del
    consultor.
    """
    h = sesion("consultor")
    servicio = cliente.post("/servicios", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "implantado",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}).json()
    contrato = cliente.post("/implantados/contratos", headers=h, json={
        "servicio_id": servicio["id"], "anio": 2029, "mes": 5,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia", "incluye_fines_de_semana": False,
        "hora_presentacion": "08:00:00",
        "titular_id": datos["personal"]["Juan Ramirez"]["id"],
        "vehiculo_id": datos["suburban"]["id"],
        "precio_mes_vehiculo": "66000", "precio_dia_personal": "2900",
        "precio_dia_adicional": "3500"}).json()
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    # Se enferma: Luis entra el 11 y no se dice hasta cuando.
    cambio = cliente.post(f"/implantados/{servicio['id']}/cambios", headers=h, json={
        "tipo": "personal", "desde": "2029-05-11",
        "sale_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_id": datos["personal"]["Luis Mendoza"]["id"],
        "motivo": "enfermedad"})
    assert cambio.status_code == 200, cambio.text
    assert cambio.json()["tope_automatico"] is True

    # Se recupera: el consultor coordina el regreso el 25.
    r = _regreso(cliente, sesion, cambio.json()["reemplazo_id"], "2029-05-25")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["desde"] == "2029-05-11"    # viernes
    assert cuerpo["hasta"] == "2029-05-24"    # jueves, el dia antes
    assert cuerpo["jornadas_partidas"] == []      # programado: limpio

    # El mes lee un solo movimiento, del 11 al 24.
    resumen = cliente.get(
        f"/implantados/contratos/{contrato['contrato_id']}/resumen",
        headers=h).json()
    assert resumen["total_reemplazos"] == 1, resumen["reemplazos"]
    assert resumen["reemplazos"][0]["desde"] == "2029-05-11"
    assert resumen["reemplazos"][0]["hasta"] == "2029-05-24"

    # Y el 25 en adelante vuelve a ser de Juan.
    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    for j in detalle["equipos"][0]["jornadas"]:
        if j["fecha"] >= "2029-05-25":
            assert _asignados(cliente, sesion, j["id"]) == ["Juan Ramirez"], j["fecha"]


def test_la_vista_previa_del_regreso_no_guarda_nada(cliente, sesion, datos):
    """Lo mismo que con el cambio: se ejecuta de verdad y se deshace.

    El regreso no es solo un nombre: puede partir un dia y mueve dinero
    de los dos lados. El consultor tiene que poder verlo antes.
    """
    servicio = _montado(cliente, sesion, datos, offset=680, dias=4)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()

    r = cliente.post(
        f"/contingencia/reemplazos/{hecho['reemplazo_id']}/regreso/vista-previa",
        headers=h, json={"desde": dias[3]["fecha"]})
    assert r.status_code == 200, r.text
    previa = r.json()
    assert previa["hasta"] == dias[2]["fecha"]
    assert previa["jornadas_devueltas"] == [dias[3]["fecha"]]

    # No guardo nada: el dia 3 sigue siendo de Luis y el movimiento sigue
    # abierto.
    assert _asignados(cliente, sesion, dias[3]["id"]) == ["Luis Mendoza"]
    historial = cliente.get(
        f"/contingencia/reemplazos/servicio/{servicio['id']}", headers=h).json()
    assert historial[0]["en_curso"] is True
    assert historial[0]["regreso_en"] is None

    # Y el regreso de verdad dice lo mismo que dijo la previa.
    hecho2 = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[3]["fecha"])
    assert hecho2.status_code == 200, hecho2.text
    assert hecho2.json()["hasta"] == previa["hasta"]


def test_el_historial_dice_el_estado_y_el_dia_partido(cliente, sesion, datos):
    """Lo que la tarjeta necesita para no mentir.

    Un movimiento en curso y uno que ya termino se veian identicos, y el
    dia partido --la prueba de que quien trabajo media jornada cobra
    media jornada-- solo se veia abriendo la nomina.
    """
    servicio = _montado(cliente, sesion, datos, offset=720, dias=4)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")

    _se_presenta(cliente, sesion, dias[1])
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()

    fila = cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                       headers=h).json()[0]
    assert fila["en_curso"] is True
    assert [x["fecha"] for x in fila["partidos"]] == [dias[1]["fecha"]]
    assert len(fila["partidos"][0]["hora"]) == 5, fila["partidos"][0]
    # Un eventual no se vuelve a pedir: eso es del implantado.
    assert fila["se_vuelve_a_pedir"] is False

    # Cerrado: deja de estar en curso y queda firmado.
    _regreso(cliente, sesion, hecho["reemplazo_id"], dias[3]["fecha"])
    fila = cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                       headers=h).json()[0]
    assert fila["en_curso"] is False
    assert fila["regreso_por"] == "Ana Solis"


# ============================================ mover un regreso capturado

def _historial(cliente, sesion, servicio):
    return cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                       headers=sesion("consultor")).json()


def test_el_regreso_se_puede_atrasar(cliente, sesion, datos):
    """Juan dijo que volvia el jueves y el miercoles avisa que mejor el
    lunes. El movimiento se recorre; no se abre otro."""
    servicio = _montado(cliente, sesion, datos, offset=760, dias=6)
    dias = servicio["equipos"][0]["jornadas"]
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()
    assert _regreso(cliente, sesion, hecho["reemplazo_id"],
                    dias[3]["fecha"]).status_code == 200

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[5]["fecha"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["hasta"] == dias[4]["fecha"]
    assert cuerpo["jornadas_recuperadas"] == [dias[3]["fecha"], dias[4]["fecha"]]
    assert cuerpo["jornadas_devueltas"] == []
    assert cuerpo["dias_cubiertos"] == 4

    esperado = ["Juan Ramirez", "Luis Mendoza", "Luis Mendoza",
                "Luis Mendoza", "Luis Mendoza", "Juan Ramirez"]
    for dia, quien in zip(dias, esperado):
        assert _asignados(cliente, sesion, dia["id"]) == [quien], dia["fecha"]

    # Un solo movimiento, del 1 al 4, firmado otra vez.
    filas = _historial(cliente, sesion, servicio)
    assert len(filas) == 1, filas
    assert filas[0]["hasta"] == dias[4]["fecha"]
    assert filas[0]["jornadas_afectadas"] == 4


def test_el_regreso_se_puede_adelantar(cliente, sesion, datos):
    """Juan se recupero antes de lo que dijo."""
    servicio = _montado(cliente, sesion, datos, offset=800, dias=6)
    dias = servicio["equipos"][0]["jornadas"]
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()
    assert _regreso(cliente, sesion, hecho["reemplazo_id"],
                    dias[4]["fecha"]).status_code == 200

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[2]["fecha"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["hasta"] == dias[1]["fecha"]
    assert cuerpo["jornadas_devueltas"] == [dias[2]["fecha"], dias[3]["fecha"]]
    assert cuerpo["jornadas_recuperadas"] == []
    assert cuerpo["dias_cubiertos"] == 1

    esperado = ["Juan Ramirez", "Luis Mendoza", "Juan Ramirez",
                "Juan Ramirez", "Juan Ramirez", "Juan Ramirez"]
    for dia, quien in zip(dias, esperado):
        assert _asignados(cliente, sesion, dia["id"]) == [quien], dia["fecha"]
    assert len(_historial(cliente, sesion, servicio)) == 1


def test_el_regreso_no_se_mueve_si_el_dinero_ya_se_movio(cliente, sesion, datos):
    """El candado del dinero, visto por este lado.

    En cuanto hay una transferencia y un plazo corriendo, correr el
    regreso a mano seria peor que el error: lo que corresponde es un
    cambio nuevo, con su rastro.
    """
    servicio = _montado(cliente, sesion, datos, offset=840, dias=5)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()
    assert _regreso(cliente, sesion, hecho["reemplazo_id"],
                    dias[3]["fecha"]).status_code == 200

    # Juan ya volvio el dia 3 y ya recibio su dinero de ese dia.
    viatico = cliente.post(
        "/viaticos/asignar", headers=h,
        json={"jornada_id": dias[3]["id"],
              "persona_id": datos["personal"]["Juan Ramirez"]["id"],
              "conceptos": [{"concepto": "alimentos", "monto": "500",
                             "origen": "tabulador"}]}).json()
    solicitud = cliente.post(f"/viaticos/{viatico['id']}/solicitar-transferencia",
                             headers=h).json()
    assert cliente.post(
        f"/viaticos/transferencias/{solicitud['id']}/confirmar",
        params={"referencia_odoo": "TRX-901"},
        headers=sesion("finanzas")).status_code == 200

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[4]["fecha"])
    assert r.status_code == 409, r.text
    assert "dinero" in r.text.lower()

    # Y nada se movio a medias: el dia 3 sigue siendo de Juan.
    assert _asignados(cliente, sesion, dias[3]["id"]) == ["Juan Ramirez"]
    assert _historial(cliente, sesion, servicio)[0]["hasta"] == dias[2]["fecha"]


def test_el_regreso_no_se_mueve_si_ese_dia_se_partio(cliente, sesion, datos):
    """Ese dia ya esta repartido entre los dos, con su hora. Moverlo
    seria rehacer una nomina."""
    servicio = _montado(cliente, sesion, datos, offset=880, dias=5)
    dias = servicio["equipos"][0]["jornadas"]
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()

    # Luis alcanza a trabajar la manana del dia en que Juan vuelve.
    inicio = datetime.fromisoformat(dias[3]["inicio_programado"])
    assert marcar(cliente, sesion("luis"), dias[3]["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200

    previo = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[3]["fecha"])
    assert previo.status_code == 200, previo.text
    assert previo.json()["jornadas_partidas"] == [dias[3]["fecha"]]

    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[4]["fecha"])
    assert r.status_code == 409, r.text
    assert "parti" in r.text.lower()


def _unidades(cliente, sesion, jornada_id):
    r = cliente.get(f"/servicios/jornadas/{jornada_id}/asignaciones",
                    headers=sesion("consultor"))
    return [v["placa"] for v in r.json()["vehiculos"]]


def test_la_unidad_tambien_regresa(cliente, sesion, datos):
    """La camioneta sale del taller y vuelve a su servicio.

    Es el mismo motor con los nombres al reves, igual que con las
    personas. Lo unico que no aplica es el candado del dinero: la unidad
    no mueve viaticos, el combustible y las casetas siguen siendo del
    conductor, que es el mismo.
    """
    servicio = _montado(cliente, sesion, datos, offset=920, dias=5)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"])

    cambio = cliente.post("/contingencia/reemplazos/vehiculo", headers=h, json={
        "desde_jornada_id": dias[1]["id"],
        "sale_vehiculo_id": datos["suburban"]["id"],
        "entra_vehiculo_id": otra["id"],
        "motivo": "Entro al taller"})
    assert cambio.status_code == 200, cambio.text

    r = _regreso(cliente, sesion, cambio.json()["reemplazo_id"],
                 dias[3]["fecha"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["tipo"] == "vehiculo"
    assert cuerpo["regresa"] == datos["suburban"]["placa"]
    assert cuerpo["sale"] == otra["placa"]
    assert cuerpo["hasta"] == dias[2]["fecha"]
    assert cuerpo["dias_cubiertos"] == 2

    esperado = [datos["suburban"]["placa"], otra["placa"], otra["placa"],
                datos["suburban"]["placa"], datos["suburban"]["placa"]]
    for dia, placa in zip(dias, esperado):
        assert _unidades(cliente, sesion, dia["id"]) == [placa], dia["fecha"]

    filas = _historial(cliente, sesion, servicio)
    assert len(filas) == 1, filas
    assert filas[0]["tipo"] == "vehiculo"
    assert filas[0]["regreso_por"] == "Ana Solis"


def test_la_hora_que_el_sistema_propuso_para_el_regreso_queda_al_lado(
        cliente, sesion, datos):
    """Sin la propuesta guardada no se puede saber si alguien la corrigio.

    El movimiento ya guardaba la del relevo que lo abrio. La del regreso
    --que tambien decide cuanto cobra cada quien-- vivia solo en la
    asignacion.
    """
    servicio = _montado(cliente, sesion, datos, offset=960, dias=4)
    dias = servicio["equipos"][0]["jornadas"]
    h = sesion("consultor")
    hecho = _relevo(cliente, sesion, datos, dias[1]).json()

    inicio = datetime.fromisoformat(dias[2]["inicio_programado"])
    marca = inicio + timedelta(hours=2)
    assert marcar(cliente, sesion("luis"), dias[2]["id"], "llegada_origen",
                  inicio - timedelta(minutes=10)).status_code == 200
    marcar(cliente, sesion("luis"), dias[2]["id"], "contacto_ejecutivo", marca)

    # El consultor corrige la hora: dice que fue una hora despues.
    corregida = (marca + timedelta(hours=1)).isoformat()
    r = _regreso(cliente, sesion, hecho["reemplazo_id"], dias[2]["fecha"],
                 relevado_en=corregida)
    assert r.status_code == 200, r.text
    assert r.json()["jornadas_partidas"] == [dias[2]["fecha"]]

    fila = _historial(cliente, sesion, servicio)[0]
    # Lo que el sistema habria puesto: la ultima marca de Luis.
    assert fila["hora_propuesta_regreso"] == marca.isoformat()
    # Y lo que quedo en la asignacion es lo que dijo el consultor. Que no
    # coincidan es justo lo que deja ver la correccion.
    assert fila["partidos"][0]["hora"] == corregida[11:16]
    assert fila["regreso_por"] == "Ana Solis"


# ================================================== la raya con implantado

def test_el_implantado_tiene_que_decir_hasta_cuando(cliente, sesion, datos):
    """El implantado si pasa por aqui, pero con fecha de fin.

    Antes este motor lo rechazaba de plano y el implantado tenia el suyo,
    que mutaba la asignacion: quien trabajo media jornada y fue relevado
    cobraba cero. Lo que el candado protegia sigue en pie: el implantado
    reutiliza el mismo equipo mes tras mes, asi que un cambio "de aqui en
    adelante" barreria tambien el mes siguiente si ya se genero, y
    abriria decenas de viaticos de un solo clic.
    """
    h = sesion("consultor")
    servicio = cliente.post("/servicios", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "implantado",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}).json()
    contrato = cliente.post("/implantados/contratos", headers=h, json={
        "servicio_id": servicio["id"], "anio": 2028, "mes": 3,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia", "incluye_fines_de_semana": False,
        "hora_presentacion": "08:00:00",
        "titular_id": datos["personal"]["Juan Ramirez"]["id"],
        "vehiculo_id": datos["suburban"]["id"],
        "precio_mes_vehiculo": "66000", "precio_dia_personal": "2900",
        "precio_dia_adicional": "3500"}).json()
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    jornada = detalle["equipos"][0]["jornadas"][5]

    # Sin fin, por la puerta de eventual: no.
    r = cliente.post("/contingencia/reemplazos/personal", headers=h, json={
        "desde_jornada_id": jornada["id"],
        "sale_persona_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
        "motivo": "Contingencia"})
    assert r.status_code == 409, r.text
    assert "implantado" in r.text.lower()

    # Por la suya, que siempre pone tope: si.
    suyo = cliente.post(f"/implantados/{servicio['id']}/cambios", headers=h, json={
        "tipo": "personal", "desde": jornada["fecha"], "hasta": jornada["fecha"],
        "sale_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_id": datos["personal"]["Luis Mendoza"]["id"],
        "motivo": "enfermedad"})
    assert suyo.status_code == 200, suyo.text


def test_en_el_implantado_el_dia_tambien_se_parte(cliente, sesion, datos):
    """La misma regla, entrando por la puerta del implantado.

    El implantado tenia su propia copia del reemplazo y la copia estaba
    mal: mutaba la asignacion, asi que quien trabajo media jornada y fue
    relevado cobraba cero. Ahora `cambiar_recurso` no cambia nada por su
    cuenta --traduce el tramo de fechas a jornadas y llama al mismo motor
    que el eventual-- y esta prueba es lo que lo sostiene: el dia que
    alguien le devuelva una implementacion propia, esto se pone en rojo.

    Dos implementaciones de la misma regla se separan con el tiempo. La
    unica forma de que no vuelva a pasar es que solo haya una, y que una
    prueba lo diga por cada puerta.
    """
    h = sesion("consultor")
    servicio = cliente.post("/servicios", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "implantado",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}).json()
    contrato = cliente.post("/implantados/contratos", headers=h, json={
        "servicio_id": servicio["id"], "anio": 2028, "mes": 3,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia", "incluye_fines_de_semana": False,
        "hora_presentacion": "08:00:00",
        "titular_id": datos["personal"]["Juan Ramirez"]["id"],
        "vehiculo_id": datos["suburban"]["id"],
        "precio_mes_vehiculo": "66000", "precio_dia_personal": "2900",
        "precio_dia_adicional": "3500"}).json()
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    dia = detalle["equipos"][0]["jornadas"][5]

    # Juan se presenta: llega al punto y hace contacto. A partir de aqui
    # ya trabajo, y su dia vale.
    configurar_origen(cliente, h, dia["id"])
    inicio = datetime.fromisoformat(dia["inicio_programado"])
    r = marcar(cliente, sesion("juan"), dia["id"], "llegada_origen",
               inicio - timedelta(minutes=10))
    assert r.status_code == 200, r.text
    marcar(cliente, sesion("juan"), dia["id"], "contacto_ejecutivo", inicio)

    cambio = cliente.post(f"/implantados/{servicio['id']}/cambios", headers=h,
                          json={"tipo": "personal", "desde": dia["fecha"],
                                "hasta": dia["fecha"],
                                "sale_id": datos["personal"]["Juan Ramirez"]["id"],
                                "entra_id": datos["personal"]["Luis Mendoza"]["id"],
                                "motivo": "enfermedad"})
    assert cambio.status_code == 200, cambio.text
    cuerpo = cambio.json()

    # El dia no cambio de dueno: se partio.
    assert cuerpo["dias_cambiados"] == 1, cuerpo
    assert cuerpo["jornadas_partidas"] == [dia["fecha"]], cuerpo

    quienes = _asignados(cliente, sesion, dia["id"])
    assert "Juan Ramirez" in quienes, "el que trabajo desaparecio del dia"
    assert "Luis Mendoza" in quienes


def test_el_cambio_sin_fin_se_detiene_el_ultimo_dia_del_mes(cliente, sesion, datos):
    """Un relevo que se come dos meses sin que nadie lo vuelva a mirar es
    peor que pedir el tramite dos veces.

    El implantado reutiliza el mismo equipo mes tras mes. Sin tope, "Luis
    cubre a Marta desde el jueves" se llevaria tambien los dias de abril
    que ya existan, sin que nadie lo pida y sin que aparezca en ninguna
    pantalla.
    """
    h = sesion("consultor")
    servicio = cliente.post("/servicios", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "implantado",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}).json()

    contratos = {}
    for mes in (3, 4):
        c = cliente.post("/implantados/contratos", headers=h, json={
            "servicio_id": servicio["id"], "anio": 2029, "mes": mes,
            "modalidad_id": datos["modalidades"]["full_day"]["id"],
            "esquema": "por_dia", "incluye_fines_de_semana": False,
            "hora_presentacion": "08:00:00",
            "titular_id": datos["personal"]["Juan Ramirez"]["id"],
            "vehiculo_id": datos["suburban"]["id"],
            "precio_mes_vehiculo": "66000", "precio_dia_personal": "2900",
            "precio_dia_adicional": "3500"}).json()
        contratos[mes] = c
        cliente.post(f"/implantados/contratos/{c['contrato_id']}/generar-mes",
                     headers=h)

    # Marzo y abril estan abiertos. El cambio arranca a mitad de marzo y
    # no dice hasta cuando.
    r = cliente.post(f"/implantados/{servicio['id']}/cambios", headers=h, json={
        "tipo": "personal", "desde": "2029-03-15",
        "sale_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_id": datos["personal"]["Luis Mendoza"]["id"],
        "motivo": "enfermedad"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["tope_automatico"] is True
    assert cuerpo["hasta"].startswith("2029-03"), cuerpo["hasta"]

    # Ni un dia de abril se movio: se mira la asignacion, no un conteo,
    # porque un conteo en cero puede salir por el motivo equivocado.
    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    abril = [j for j in detalle["equipos"][0]["jornadas"]
             if j["fecha"].startswith("2029-04")]
    assert abril, "abril no se genero"
    for j in abril:
        assert _asignados(cliente, sesion, j["id"]) == ["Juan Ramirez"], j["fecha"]

    # Y marzo si: del 15 al 31 es de Luis. Acotado por los dos lados,
    # porque como texto "2029-04-02" tambien es mayor que "2029-03-15".
    marzo = [j for j in detalle["equipos"][0]["jornadas"]
             if "2029-03-15" <= j["fecha"] <= "2029-03-31"]
    assert cuerpo["dias_cambiados"] == len(marzo), cuerpo["dias_cambiados"]
    for j in marzo:
        assert _asignados(cliente, sesion, j["id"]) == ["Luis Mendoza"], j["fecha"]


def test_al_que_entra_no_se_le_abre_dinero_solo(cliente, sesion, datos):
    """El sistema propone, el consultor decide.

    Si el reemplazo abriera viaticos por su cuenta, seria el sistema
    decidiendo gastar sin que nadie lo pidiera, y ademas dejaria el
    cierre trabado con dinero que nadie solicito.
    """
    servicio = _montado(cliente, sesion, datos, dias=2)
    j = servicio["equipos"][0]["jornadas"][0]
    _se_presenta(cliente, sesion, j)

    r = _relevo(cliente, sesion, datos, j)
    assert r.status_code == 200, r.text
    v = r.json()["viaticos"]

    # La cuenta esta: el consultor no tiene que ir a buscar el tabulador.
    assert v["propuestos"], v
    assert all(x["monto"] > 0 for x in v["propuestos"])

    # Pero nadie le asigno nada todavia.
    afuera = cliente.get("/viaticos/finanzas/por-comprobar",
                         headers=sesion("finanzas")).json()
    de_luis = [x for p in afuera["paises"] for x in p["personas"]
               if x["persona"] == "Luis Mendoza"]
    assert de_luis == [], de_luis


def test_lo_ya_depositado_sigue_siendo_de_quien_lo_recibio(cliente, sesion,
                                                            datos):
    """El dinero que ya salio no se mueve con la persona.

    Quien lo recibio se hace responsable de comprobarlo, y esa
    comprobacion hace falta para cerrar el servicio.
    """
    servicio = _montado(cliente, sesion, datos, dias=2)
    j = servicio["equipos"][0]["jornadas"][0]
    h = sesion("consultor")

    viatico = cliente.post(
        "/viaticos/asignar", headers=h,
        json={"jornada_id": j["id"],
              "persona_id": datos["personal"]["Juan Ramirez"]["id"],
              "conceptos": [{"concepto": "alimentos", "monto": "700",
                             "origen": "tabulador"}]}).json()
    solicitud = cliente.post(f"/viaticos/{viatico['id']}/solicitar-transferencia",
                             headers=h).json()
    cliente.post(f"/viaticos/transferencias/{solicitud['id']}/confirmar",
                 params={"referencia_odoo": "TRX-901"}, headers=sesion("finanzas"))

    _se_presenta(cliente, sesion, j)
    r = _relevo(cliente, sesion, datos, j)
    assert r.status_code == 200, r.text

    a_comprobar = r.json()["viaticos"]["a_comprobar"]
    assert [x["viatico_id"] for x in a_comprobar] == [viatico["id"]]
    assert a_comprobar[0]["limite"], "sin plazo no hay a quien perseguir"

    despues = cliente.get(f"/viaticos/{viatico['id']}", headers=h).json()
    assert despues["estatus"] == "en_comprobacion"
    assert despues["persona_id"] == datos["personal"]["Juan Ramirez"]["id"]


# ==================================================================
# La hora que parte el dia
# ==================================================================

def test_la_hora_sale_de_la_ultima_marca_y_no_del_reloj(cliente, sesion, datos):
    """El consultor captura el relevo cuando puede, no cuando pasa.

    Antes la hora era la del momento de capturar: un relevo de las 11:00
    registrado a las seis de la tarde le pagaba siete horas de mas a
    quien ya se habia ido, y se las quitaba a quien las trabajo. Ahora
    sale de la ultima vez que el sistema supo de quien salio.
    """
    servicio = _montado(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])

    marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
           inicio - timedelta(minutes=10))
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo", inicio)
    # Su ultima senal de vida: llego al destino a las cuatro horas.
    ultima = inicio + timedelta(hours=4)
    marcar(cliente, sesion("juan"), j["id"], "llegada_destino", ultima)

    r = _relevo(cliente, sesion, datos, j)
    assert r.status_code == 200, r.text
    cuerpo = r.json()

    assert cuerpo["hora_propuesta"] == ultima.isoformat()
    assert cuerpo["relevado_en"] == ultima.isoformat(), \
        "sin hora capturada, se usa la que propuso el sistema"


def test_el_consultor_puede_corregir_la_hora_y_se_nota(cliente, sesion, datos):
    """Un dia estatico puede no tener marcas desde la manana. El sistema
    propone lo que sabe; el consultor pone lo que fue, y la propuesta
    queda al lado para que se vea que la movio."""
    from app import models as m
    from app.db import SessionLocal

    servicio = _montado(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])

    marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
           inicio - timedelta(minutes=10))
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo", inicio)

    # El sistema propondria las 07:00; el consultor sabe que fue a las 11.
    de_verdad = inicio + timedelta(hours=4)
    r = _relevo(cliente, sesion, datos, j, relevado_en=de_verdad.isoformat())
    assert r.status_code == 200, r.text
    cuerpo = r.json()

    assert cuerpo["relevado_en"] == de_verdad.isoformat()
    assert cuerpo["hora_propuesta"] == inicio.isoformat()
    assert cuerpo["hora_propuesta"] != cuerpo["relevado_en"], \
        "si difieren, alguien la corrigio"

    db = SessionLocal()
    try:
        movimiento = db.get(m.ReemplazoRecurso, cuerpo["reemplazo_id"])
        assert movimiento.hora_propuesta == inicio
        assert movimiento.hecho_por_id, "y queda quien la movio"
    finally:
        db.close()


def test_quien_no_se_presento_no_deja_hora_propuesta(cliente, sesion, datos):
    """Sin dia partido no hay nada que repartir, asi que no hay hora que
    proponer ni que guardar."""
    from app import models as m
    from app.db import SessionLocal

    servicio = _montado(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    r = _relevo(cliente, sesion, datos, j)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["jornadas_partidas"] == []

    db = SessionLocal()
    try:
        movimiento = db.get(m.ReemplazoRecurso, cuerpo["reemplazo_id"])
        assert movimiento.hora_propuesta is None
    finally:
        db.close()


def test_la_unidad_tambien_acepta_la_hora_del_cambio(cliente, sesion, datos):
    """Del lado de las unidades la hora importa por otra razon: es el
    momento en que la camioneta cambia de manos, y de ahi cuelga la
    revision de entrega. El esquema tampoco la aceptaba."""
    servicio = _montado(cliente, sesion, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])
    cuando = inicio + timedelta(hours=3)

    otra = next(v for v in datos["vehiculos"]
                if v["id"] != datos["suburban"]["id"])
    r = cliente.post("/contingencia/reemplazos/vehiculo",
                     headers=sesion("consultor"),
                     json={"desde_jornada_id": j["id"],
                           "sale_vehiculo_id": datos["suburban"]["id"],
                           "entra_vehiculo_id": otra["id"],
                           "motivo": "Se poncho",
                           "relevado_en": cuando.isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["relevado_en"] == cuando.isoformat()


def test_a_quien_relevaron_queda_libre_el_resto_del_dia(cliente, sesion, datos):
    """Se releva a alguien a las seis y a las siete ya está libre.

    Su asignación sigue ahí —y tiene que seguir, porque ese día lo
    trabajó y se le paga—, pero la disponibilidad la leía como si
    siguiera ocupado hasta la medianoche: quien salía de un servicio por
    contingencia no se podía poner en ningún otro lado.
    """
    from app import disponibilidad as disp
    from app import models as m
    from app.db import SessionLocal
    from datetime import datetime, timedelta

    servicio = _montado(cliente, sesion, datos, offset=320, dias=1)
    j = servicio["equipos"][0]["jornadas"][0]
    _se_presenta(cliente, sesion, j)
    assert _relevo(cliente, sesion, datos, j).status_code == 200

    juan = datos["personal"]["Juan Ramirez"]["id"]
    arranca = datetime.fromisoformat(j["inicio_programado"])

    # La hora del relevo se fija a media jornada, a proposito.
    #
    # El motor la pone en el momento en que se hizo el cambio, y esta
    # prueba arma un servicio a trescientos veinte dias de hoy: el
    # relevo queda con la hora de HOY, muy anterior al dia. Con eso la
    # regla contesta bien --lo relevaron antes de que el dia empezara,
    # asi que ese dia no le ocupa nada-- pero no es el caso que se
    # quiere probar. Lo que se quiere probar es el de la calle: lo
    # relevaron a media tarde.
    with SessionLocal() as db:
        fila = (db.query(m.AsignacionPersonal)
                .filter_by(jornada_id=j["id"], persona_id=juan)
                .filter(m.AsignacionPersonal.relevado_en.isnot(None))
                .first())
        assert fila is not None, "el relevo no dejo hora"
        fila.relevado_en = arranca + timedelta(hours=4)
        db.commit()

    corte = arranca + timedelta(hours=4)
    with SessionLocal() as db:
        # Despues de que lo relevaron: libre.
        despues = disp.revisar_persona(db, juan, corte + timedelta(hours=1),
                                       corte + timedelta(hours=4), False)
        assert not [h for h in despues if h.nivel == "bloqueo"], despues

        # Y antes del relevo sigue ocupado: lo que cambia es hasta
        # cuando, no que el dia deje de contar.
        durante = disp.revisar_persona(db, juan, arranca,
                                       arranca + timedelta(hours=1), False)
        assert [h for h in durante if h.nivel == "bloqueo"], durante


def test_un_dia_ya_cerrado_no_ocupa_el_resto_de_la_tarde(cliente, sesion,
                                                         datos):
    """El transfer de 14:00 a 17:00 terminó. A las 17:01 está libre.

    La disponibilidad no miraba el cierre: un día trabajado seguía
    ocupando la agenda hasta la medianoche, y a esa persona no se le
    podía poner en nada más esa tarde aunque el servicio ya estuviera
    cerrado y firmado.
    """
    from app import disponibilidad as disp
    from app.db import SessionLocal
    from datetime import datetime, timedelta

    servicio = _montado(cliente, sesion, datos, offset=321, dias=1)
    j = servicio["equipos"][0]["jornadas"][0]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    arranca = datetime.fromisoformat(j["inicio_programado"])
    fin = datetime.fromisoformat(j["fin_programado"])

    with SessionLocal() as db:
        antes = disp.revisar_persona(db, juan, fin + timedelta(hours=2),
                                     fin + timedelta(hours=5), False)
        assert [h for h in antes if h.nivel == "bloqueo"], \
            "sin cerrar, el dia sigue siendo suyo"

    marcar(cliente, sesion("juan"), j["id"], "llegada_origen",
           arranca - timedelta(minutes=10))
    marcar(cliente, sesion("juan"), j["id"], "contacto_ejecutivo", arranca)
    marcar_fin(cliente, sesion("juan"), j["id"], fin)

    with SessionLocal() as db:
        despues = disp.revisar_persona(db, juan, fin + timedelta(hours=2),
                                       fin + timedelta(hours=5), False)
        assert not [h for h in despues if h.nivel == "bloqueo"], despues

    # Y el full day del mismo dia deja de ser imposible: pasa a ser un
    # aviso, porque se le vende el dia completo a otro cliente.
    with SessionLocal() as db:
        completo = disp.revisar_persona(db, juan, fin + timedelta(hours=2),
                                        fin + timedelta(hours=5), True)
        assert not [h for h in completo if h.nivel == "bloqueo"], completo
        assert [h for h in completo if h.nivel == "riesgo"], completo

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
                    crear_servicio, jornada, manana, marcar)


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
    marcar(cliente, sesion("luis"), j["id"], "fin_servicio", fin)
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
    marcar(cliente, sesion("luis"), j["id"], "fin_servicio", fin)
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
    marcar(cliente, sesion("luis"), j["id"], "fin_servicio",
           fin + timedelta(hours=2))
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


# ================================================== la raya con implantado

def test_el_implantado_no_pasa_por_aqui(cliente, sesion, datos):
    """No es separacion de gusto.

    El implantado reutiliza el mismo equipo mes tras mes, asi que un
    cambio "de aqui en adelante" barreria todas las jornadas abiertas
    —el mes en curso y el siguiente si ya se genero— y abriria decenas
    de viaticos de un solo clic. Su reemplazo va dia por dia, en su
    propio calendario (`/implantados/jornadas/{id}/reemplazo`).
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
    jornada_id = detalle["equipos"][0]["jornadas"][5]["id"]

    r = cliente.post("/contingencia/reemplazos/personal", headers=h, json={
        "desde_jornada_id": jornada_id,
        "sale_persona_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_persona_id": datos["personal"]["Luis Mendoza"]["id"],
        "motivo": "Contingencia"})
    assert r.status_code == 409, r.text
    assert "implantado" in r.text.lower()

    # Y el suyo si funciona: el dia que se pidio y ninguno mas.
    suyo = cliente.post(f"/implantados/jornadas/{jornada_id}/reemplazo",
                        json={"entra_id": datos["personal"]["Luis Mendoza"]["id"],
                              "motivo": "enfermedad"}, headers=h)
    assert suyo.status_code == 200, suyo.text


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

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


def test_el_cambio_de_un_dia_queda_registrado(cliente, sesion, datos):
    """Un dia suelto es un tramo de un dia.

    Ya no hay una puerta para el dia suelto y otra para el tramo: el
    consultor no tiene que aprender dos formas de hacer lo mismo segun si
    el que falta aviso con un mes o con una hora.
    """
    servicio, contrato = _contrato(cliente, sesion, datos, 2027, 6)
    h = sesion("consultor")
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    dia = detalle["equipos"][0]["jornadas"][5]["fecha"]

    r = cliente.post(f"/implantados/{servicio['id']}/cambios", headers=h, json={
        "tipo": "personal", "desde": dia, "hasta": dia,
        "sale_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_id": datos["personal"]["Luis Mendoza"]["id"],
        "motivo": "enfermedad", "nota": "Incapacidad de un dia"})
    assert r.status_code == 200, r.text
    assert r.json()["sale"] == "Juan Ramirez"
    assert r.json()["entra"] == "Luis Mendoza"
    assert r.json()["dias_cambiados"] == 1

    resumen = cliente.get(f"/implantados/contratos/{contrato['contrato_id']}/resumen",
                          headers=h).json()
    assert resumen["total_reemplazos"] == 1
    assert resumen["reemplazos"][0]["motivo"] == "enfermedad"
    assert resumen["reemplazos"][0]["desde"] == dia
    assert resumen["reemplazos"][0]["hasta"] == dia


def test_la_vista_previa_no_guarda_nada(cliente, sesion, datos):
    """Se ejecuta el cambio de verdad y se deshace.

    No hay una segunda cuenta que calcule "lo que pasaria": esa siempre
    acaba separandose de la primera, y entonces el recuadro que el
    consultor lee deja de ser lo que el sistema hace.
    """
    servicio, contrato = _contrato(cliente, sesion, datos, 2030, 4)
    h = sesion("consultor")
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)
    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    jornadas = detalle["equipos"][0]["jornadas"]
    dia = jornadas[4]["fecha"]

    cambio = {"tipo": "personal", "desde": dia,
              "sale_id": datos["personal"]["Juan Ramirez"]["id"],
              "entra_id": datos["personal"]["Luis Mendoza"]["id"],
              "motivo": "vacaciones"}

    r = cliente.post(f"/implantados/{servicio['id']}/cambios/vista-previa",
                     headers=h, json=cambio)
    assert r.status_code == 200, r.text
    previa = r.json()
    # Sin fecha de fin: la previa ya dice hasta donde llega y que el tope
    # lo puso el sistema.
    assert previa["tope_automatico"] is True
    assert previa["hasta"].startswith("2030-04")
    assert previa["jornadas_afectadas"][0] == dia

    # Y no guardo nada: ese dia sigue siendo de Juan y no hay historial.
    def quien(jornada_id):
        a = cliente.get(f"/servicios/jornadas/{jornada_id}/asignaciones",
                        headers=h).json()
        return [p["nombre"] for p in a["personal"]]

    assert quien(jornadas[4]["id"]) == ["Juan Ramirez"]
    assert cliente.get(f"/contingencia/reemplazos/servicio/{servicio['id']}",
                       headers=h).json() == []

    # El cambio de verdad da lo mismo que dijo la previa.
    hecho = cliente.post(f"/implantados/{servicio['id']}/cambios",
                         headers=h, json=cambio)
    assert hecho.status_code == 200, hecho.text
    assert hecho.json()["hasta"] == previa["hasta"]
    assert hecho.json()["dias_cambiados"] == previa["dias_cambiados"]
    assert quien(jornadas[4]["id"]) == ["Luis Mendoza"]


def test_sin_nombre_no_hay_cambio(cliente, sesion, datos):
    """Antes, no decir quien sale queria decir "el primero de la lista".

    En una plantilla de tres —un coordinador y dos agentes— eso cambiaba
    al que no era. El fin de semana, cuando la plantilla rota, cambiaba a
    cualquiera.
    """
    servicio, contrato = _contrato(cliente, sesion, datos, 2027, 11)
    h = sesion("consultor")
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)
    detalle = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    dia = detalle["equipos"][0]["jornadas"][3]["fecha"]

    r = cliente.post(f"/implantados/{servicio['id']}/cambios", headers=h, json={
        "tipo": "personal", "desde": dia, "hasta": dia,
        "entra_id": datos["personal"]["Luis Mendoza"]["id"],
        "motivo": "enfermedad"})
    assert r.status_code == 422, r.text


def test_no_se_duplica_el_contrato_del_mismo_mes(cliente, sesion, datos):
    servicio, _ = _contrato(cliente, sesion, datos, 2027, 7)
    r = cliente.post("/implantados/contratos", json={
        "servicio_id": servicio["id"], "anio": 2027, "mes": 7,
        "modalidad_id": datos["modalidades"]["full_day"]["id"]},
        headers=sesion("consultor"))
    assert r.status_code == 409


# ================================ la bitacora dentro de la ficha del dia
#
# El implantado ya tenia bitacora por el otro lado --la pantalla de
# operacion del servicio-- pero ahi los dias se listan uno por renglon y
# cada mes generado agrega veintitantos que no se van nunca: a los tres
# meses hay que buscar "ayer" entre setenta. El calendario del mes ya es
# el selector de dia que hacia falta, y su ficha decia quien iba sin
# decir que paso.

def test_la_ficha_del_dia_lleva_a_su_bitacora(cliente, sesion, datos):
    """La ficha tiene que traer el numero de la jornada: sin el, la
    pantalla puede pintar quien cubre el dia y no puede abrir lo que
    paso en el."""
    h = sesion("consultor")
    _, contrato = _contrato(cliente, sesion, datos, 2027, 5)
    assert cliente.post(
        f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
        headers=h).status_code == 200

    primero = next(date(2027, 5, d) for d in range(1, 32)
                   if date(2027, 5, d).weekday() < 5)
    servicio_id = contrato["servicio_id"] if "servicio_id" in contrato \
        else None
    if servicio_id is None:
        servicio_id = cliente.get("/implantados", headers=h).json()[0]["servicio_id"]

    ficha = cliente.get(f"/implantados/{servicio_id}/dia/{primero}",
                        headers=h).json()
    assert ficha["jornada_id"], "la ficha del dia tiene que decir cual jornada es"

    # Y ese numero abre la bitacora de verdad, no un 404.
    d = cliente.get(f"/operacion/jornadas/{ficha['jornada_id']}/dia",
                    headers=h).json()
    assert d["jornada_id"] == ficha["jornada_id"]
    assert d["fecha"] == primero.isoformat()


def test_un_dia_sin_servicio_no_tiene_bitacora_que_abrir(cliente, sesion,
                                                         datos):
    """Un sabado sin servicio no tiene jornada, asi que no tiene nada que
    contar. La pantalla no debe ofrecer abrir lo que no existe."""
    h = sesion("consultor")
    _, contrato = _contrato(cliente, sesion, datos, 2027, 5)
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)
    servicio_id = cliente.get("/implantados", headers=h).json()[0]["servicio_id"]

    sabado = next(date(2027, 5, d) for d in range(1, 32)
                  if date(2027, 5, d).weekday() == 5)
    ficha = cliente.get(f"/implantados/{servicio_id}/dia/{sabado}",
                        headers=h).json()
    assert ficha["estado"] == "sin_servicio"
    assert ficha["jornada_id"] is None


def test_mover_el_arranque_avisa_de_los_dias_que_quedaron_fuera(cliente,
                                                                sesion,
                                                                datos):
    """Los dias ya generados no se mueven solos, pero se dicen.

    El agente seguia viendo en su app un dia que para el consultor ya no
    existia: se corrio la fecha de inicio y las jornadas del mes
    --creadas al abrir el mes, con el arranque congelado en el contrato--
    se quedaron donde estaban, con su gente.
    """
    h = sesion("consultor")
    servicio, contrato = _contrato(cliente, sesion, datos, 2027, 6)
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    corte = date(2027, 6, 15)
    r = cliente.put(f"/implantados/{servicio['id']}/acuerdo", headers=h,
                    json={"fecha_inicio": corte.isoformat(),
                          "dias_servicio": "lunes_viernes"})
    assert r.status_code == 200, r.text
    fuera = r.json()["dias_fuera"]
    assert fuera, "nadie aviso de los dias que quedaron antes"
    assert all(d["fecha"] < corte.isoformat() for d in fuera)
    # Se dice quien iba: la decision no se toma sobre una fecha pelada.
    assert any(d["personal"] for d in fuera)
    assert all(d["se_puede_cerrar"] is True for d in fuera)

    # Guardar otra vez sin mover la fecha no vuelve a preguntar.
    otra = cliente.put(f"/implantados/{servicio['id']}/acuerdo", headers=h,
                       json={"fecha_inicio": corte.isoformat(),
                             "dias_servicio": "lunes_viernes"})
    assert otra.json()["dias_fuera"] == []


def test_la_hora_del_encuentro_se_corrige_sin_reabrir_el_mes(cliente, sesion,
                                                             datos):
    """El cliente mueve el encuentro media hora y el mes sigue en pie.

    La hora se capturaba al abrir el mes y ahi se quedaba: no salia en
    el acuerdo ni habia donde cambiarla. Cambiarla mueve los dias que
    todavia no arrancan, porque de esa hora salen la ventana del dia, la
    geocerca y lo que el agente ve en su app.
    """
    h = sesion("consultor")
    servicio, contrato = _contrato(cliente, sesion, datos, 2027, 7)
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    r = cliente.put(f"/implantados/{servicio['id']}/hora-presentacion",
                    json={"hora": "07:30:00", "anio": 2027, "mes": 7},
                    headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["dias_movidos"], "no movio ningun dia"
    assert r.json()["dias_trabados"] == []

    # Y se lee desde el acuerdo, que es donde alguien la va a buscar.
    acuerdo = cliente.get(f"/implantados/{servicio['id']}/acuerdo",
                          headers=h).json()
    assert acuerdo["hora_presentacion"] == "07:30:00"

    panel = cliente.get(f"/implantados/{servicio['id']}/mes/2027/7",
                        headers=h).json()
    assert panel["dias"], "el mes se quedo sin dias"
    assert all(d["presentacion"] == "07:30" for d in panel["dias"])


def test_corregir_el_punto_en_el_acuerdo_baja_a_los_dias(cliente, sesion,
                                                         datos):
    """El acuerdo es la hoja maestra; los dias son copias de trabajo.

    El punto se copiaba a cada jornada al generar el mes y ahi se
    quedaba: corregir la direccion en el acuerdo dejaba los veintidos
    dias con el punto viejo, la geocerca en la otra esquina y la app del
    agente diciendo algo distinto a la hoja.
    """
    h = sesion("consultor")
    servicio, contrato = _contrato(cliente, sesion, datos, 2027, 8)
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    cliente.put(f"/implantados/{servicio['id']}/acuerdo", headers=h, json={
        "origen_direccion": "Reforma 100", "origen_lat": "19.4300",
        "origen_lon": "-99.1700", "geocerca_metros": 400})

    r = cliente.put(f"/implantados/{servicio['id']}/acuerdo", headers=h, json={
        "origen_direccion": "Palmas 250", "origen_lat": "19.4200",
        "origen_lon": "-99.2100", "geocerca_metros": 400})
    assert r.status_code == 200, r.text
    assert r.json()["dias_actualizados"], "el punto no bajo a ningun dia"

    panel = cliente.get(f"/implantados/{servicio['id']}/mes/2027/8",
                        headers=h).json()
    assert panel["dias"], "el mes se quedo sin dias"


def test_mover_el_arranque_corrige_el_contrato_del_mes(cliente, sesion, datos):
    """El calendario se pinta desde el contrato, no desde las jornadas.

    Mover la fecha en el acuerdo dejaba el contrato diciendo que el mes
    arranca el dia 1: los dias cerrados seguian pintados de verde, dias
    que ya no existian. Y de ese mismo campo salen los dias base del
    mes, que es lo que se factura.
    """
    h = sesion("consultor")
    servicio, contrato = _contrato(cliente, sesion, datos, 2027, 9)
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    antes = cliente.get(f"/implantados/{servicio['id']}/calendario/2027/9",
                        headers=h).json()
    assert antes["desde_dia"] in (None, 1)

    r = cliente.put(f"/implantados/{servicio['id']}/acuerdo", headers=h,
                    json={"fecha_inicio": "2027-09-15",
                          "dias_servicio": "lunes_viernes"})
    assert r.status_code == 200, r.text
    ajuste = r.json()["contrato_ajustado"]
    assert ajuste and ajuste["desde_dia"] == 15
    # Los dias base bajan: el mes ya no son los habiles completos.
    assert ajuste["dias_base"] < ajuste["dias_base_antes"]

    despues = cliente.get(f"/implantados/{servicio['id']}/calendario/2027/9",
                          headers=h).json()
    assert despues["desde_dia"] == 15
    primeros = [d for d in despues["dias"]
                if d["fecha"] < "2027-09-15"]
    assert all(d["estado"] == "sin_servicio" for d in primeros), \
        "el calendario sigue pintando dias que ya no son del servicio"


def test_cerrar_un_dia_con_viaticos_depositados_no_borra_el_dinero(cliente,
                                                                   sesion,
                                                                   datos):
    """Un dia por el que ya salio dinero del banco se cancela, no se borra.

    La jornada no arrastra sus viaticos al borrarse, asi que esto
    reventaba contra la base con un 500: el dia no se cerraba, el aviso
    se iba solo y el calendario seguia pintando un dia que el consultor
    creia cerrado.
    """
    from ayudas import depositar_de_verdad

    h = sesion("consultor")
    servicio, contrato = _contrato(cliente, sesion, datos, 2027, 10)
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    panel = cliente.get(f"/implantados/{servicio['id']}/mes/2027/10",
                        headers=h).json()
    dia = panel["dias"][0]["fecha"]

    equipo_id = cliente.get(f"/implantados/{servicio['id']}/calendario/2027/10",
                            headers=h).json()["equipo_id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": juan, "monto": "3000"}, headers=h)
    depositar_de_verdad(cliente, sesion, equipo_id, juan)

    r = cliente.delete(f"/implantados/{servicio['id']}/dia/{dia}", headers=h)
    assert r.status_code == 200, r.text
    hecho = r.json()
    # Cancelado, no borrado: el viatico sobrevive con su deposito.
    assert hecho["borrado"] is False
    assert hecho["viaticos_vivos"] >= 1

    from app import models as m
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        equipo = db.get(m.Servicio, servicio["id"]).equipos[0]
        suya = next(j for j in equipo.jornadas if j.fecha.isoformat() == dia)
        assert suya.estatus == m.EstatusJornada.CANCELADA
        vivos = (db.query(m.AsignacionViatico)
                 .filter_by(jornada_id=suya.id).all())
        assert vivos, "se borro el rastro del dinero que salio del banco"
    finally:
        db.close()


def test_la_hora_de_un_implantado_no_sale_sin_confirmar(cliente, sesion,
                                                        datos):
    """En el implantado la hora no es una suposicion: es el acuerdo.

    La app esconde la hora de los dias sin confirmar —regla hecha para
    el eventual, donde el dia 2 hereda la del dia 1— y en el implantado
    dejaba al agente con "Sin hora" en todos sus dias, cuando la hora
    esta pactada con el cliente y es la misma siempre.
    """
    h = sesion("consultor")
    servicio, contrato = _contrato(cliente, sesion, datos, 2027, 11)
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    from app import models as m
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        equipo = db.get(m.Servicio, servicio["id"]).equipos[0]
        dias = [j for j in equipo.jornadas
                if j.fecha.year == 2027 and j.fecha.month == 11]
        assert dias, "el mes se genero sin dias"
        assert all(j.hora_confirmada for j in dias), \
            "el implantado nace con la hora sin confirmar"
    finally:
        db.close()


def test_un_dia_cancelado_no_se_pinta_como_cubierto(cliente, sesion, datos):
    """Se cancela un dia justamente para dejar de verlo.

    El calendario armaba la lista de cubiertos recorriendo todas las
    jornadas, canceladas incluidas, asi que un dia sacado del servicio
    seguia en verde con el nombre de quien iba. Quien lo cancelo no
    tenia como saber si habia funcionado.
    """
    h = sesion("consultor")
    servicio, contrato = _contrato(cliente, sesion, datos, 2027, 12)
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    antes = cliente.get(f"/implantados/{servicio['id']}/calendario/2027/12",
                        headers=h).json()
    dia = next(d["fecha"] for d in antes["dias"] if d["estado"] == "cubierto")

    from app import models as m
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        equipo = db.get(m.Servicio, servicio["id"]).equipos[0]
        suya = next(j for j in equipo.jornadas if j.fecha.isoformat() == dia)
        suya.estatus = m.EstatusJornada.CANCELADA
        db.commit()
    finally:
        db.close()

    despues = cliente.get(f"/implantados/{servicio['id']}/calendario/2027/12",
                          headers=h).json()
    ese = next(d for d in despues["dias"] if d["fecha"] == dia)
    assert ese["estado"] != "cubierto", "un dia cancelado sigue en verde"


def test_la_ficha_del_dia_aguanta_a_quien_tiene_un_choque(cliente, sesion,
                                                          datos):
    """La pantalla se caia justo cuando habia conflicto.

    La ficha pedia `como_dict()["mensaje"]` y esa llave nunca ha
    existido --es `motivo`--, asi que reventaba con KeyError en cuanto
    alguien tenia un choque de disponibilidad. Los dias que ya tenian
    jornada no fallaban solo porque al excluir la suya no quedaba
    ningun hallazgo: el error salia en el dia sin cubrir, que es
    exactamente donde se va a buscar quien lo cubre.
    """
    from datetime import date, timedelta

    from ayudas import asignar, crear_servicio, jornada as dia_de

    h = sesion("consultor")
    servicio, contrato = _contrato(cliente, sesion, datos, 2028, 3)
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    # Un sabado: el implantado es de lunes a viernes, asi que ese dia no
    # tiene jornada y la ficha lista candidatos.
    sabado = next(date(2028, 3, d) for d in range(1, 29)
                  if date(2028, 3, d).weekday() == 5)

    # Y ese mismo sabado, el titular trae un eventual.
    otro = crear_servicio(cliente, h, datos,
                          [dia_de(sabado, datos["modalidades"]["full_day"]["id"])])
    asignar(cliente, h, otro["equipos"][0]["jornadas"][0]["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"])

    r = cliente.get(f"/implantados/{servicio['id']}/dia/{sabado.isoformat()}",
                    headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    ocupado = next((c for c in d["candidatos"] if c["ocupado"]), None)
    assert ocupado, "nadie salio ocupado teniendo otro servicio ese dia"
    assert all(isinstance(a, str) and a for a in ocupado["avisos"]), \
        "el aviso del choque salio vacio"


def test_mover_el_arranque_atras_ofrece_devolver_los_cancelados(cliente,
                                                                sesion,
                                                                datos):
    """La simetria de cerrar los que sobran.

    Sin esto, quien corrige la fecha hacia atras ve dias grises dentro
    de su propio rango contratado, sin pista de por que ni como
    devolverlos. No se reviven solos: un dia puede estar cancelado
    porque el cliente no lo pidio.
    """
    h = sesion("consultor")
    servicio, contrato = _contrato(cliente, sesion, datos, 2028, 5)
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    # Se corre el arranque hacia adelante y quedan dias fuera.
    r = cliente.put(f"/implantados/{servicio['id']}/acuerdo", headers=h,
                    json={"fecha_inicio": "2028-05-15",
                          "dias_servicio": "lunes_viernes"})
    fuera = r.json()["dias_fuera"]
    assert fuera, "no aviso de los dias que quedaron antes"

    # Se cancelan, que es lo que hace el cierre cuando el dia trae
    # dinero: un dia SIN dinero se borra, y un dia borrado no vuelve.
    from app import models as m
    from app.db import SessionLocal

    cuales = [d["fecha"] for d in fuera[:2]]
    db = SessionLocal()
    try:
        equipo = db.get(m.Servicio, servicio["id"]).equipos[0]
        for j in equipo.jornadas:
            if j.fecha.isoformat() in cuales:
                j.estatus = m.EstatusJornada.CANCELADA
        db.commit()
    finally:
        db.close()

    # Y ahora de vuelta: esos dias vuelven a caer dentro.
    r = cliente.put(f"/implantados/{servicio['id']}/acuerdo", headers=h,
                    json={"fecha_inicio": "2028-05-01",
                          "dias_servicio": "lunes_viernes"})
    assert r.status_code == 200, r.text
    vuelven = r.json()["dias_que_vuelven"]
    assert vuelven, "nadie aviso de los cancelados que vuelven"

    # Se reactivan de uno en uno y el calendario los recupera.
    uno = vuelven[0]["fecha"]
    ok = cliente.post(f"/implantados/{servicio['id']}/dia/{uno}/reactivar",
                      headers=h)
    assert ok.status_code == 200, ok.text

    panel = cliente.get(f"/implantados/{servicio['id']}/calendario/2028/5",
                        headers=h).json()
    assert uno not in panel["cancelados"]
    ese = next(d for d in panel["dias"] if d["fecha"] == uno)
    assert ese["estado"] != "sin_servicio", "volvio pero sigue gris"


def test_mover_el_arranque_atras_avisa_de_los_dias_que_faltan(cliente, sesion,
                                                              datos):
    """Un dia borrado no vuelve solo, pero se dice que falta.

    Correr el arranque hacia adelante borra los dias que no traian
    dinero. Corregirlo despues dejaba un hueco invisible: el calendario
    los pinta verdes --entre semana el color sale del rango contratado--
    pero no hay jornada detras, asi que nadie tiene asignada esa fecha y
    el agente no la ve en su app.
    """
    h = sesion("consultor")
    servicio, contrato = _contrato(cliente, sesion, datos, 2028, 7)
    cliente.post(f"/implantados/contratos/{contrato['contrato_id']}/generar-mes",
                 headers=h)

    r = cliente.put(f"/implantados/{servicio['id']}/acuerdo", headers=h,
                    json={"fecha_inicio": "2028-07-17",
                          "dias_servicio": "lunes_viernes"})
    fuera = r.json()["dias_fuera"]
    assert fuera, "no aviso de los dias que quedaron antes"
    # Sin dinero se borran, que es lo que hace el cierre en ese caso.
    borrados = [d["fecha"] for d in fuera[:3]]
    for fecha in borrados:
        assert cliente.delete(
            f"/implantados/{servicio['id']}/dia/{fecha}",
            headers=h).status_code == 200

    # De vuelta al dia 1: el contrato reclama los que se borraron.
    r = cliente.put(f"/implantados/{servicio['id']}/acuerdo", headers=h,
                    json={"fecha_inicio": "2028-07-03",
                          "dias_servicio": "lunes_viernes"})
    assert r.status_code == 200, r.text
    faltan = r.json()["dias_que_faltan"]
    assert set(borrados) <= set(faltan), "no aviso de los dias que faltan"

    # Y se completan sin pisar lo que ya existe.
    ok = cliente.post(f"/implantados/{servicio['id']}/mes/2028/7/completar",
                      headers=h)
    assert ok.status_code == 200, ok.text

    otra = cliente.put(f"/implantados/{servicio['id']}/acuerdo", headers=h,
                       json={"fecha_inicio": "2028-07-04",
                             "dias_servicio": "lunes_viernes"})
    assert otra.json()["dias_que_faltan"] == []

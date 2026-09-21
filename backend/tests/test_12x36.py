"""El implantado 12 x 36: dos personas, los siete dias, sin dias adicionales.

La escala de Brasil. Un puesto de doce horas que cubren dos personas de
la misma categoria alternandose dia con dia: doce de trabajo por treinta
y seis de descanso. Lo que Centauro opera en Mexico --una persona, doce
horas corridas, los dias que diga el acuerdo-- es el otro tipo y no se
toca.

La regla que manda sobre todo lo demas, y de la que cuelgan estas
pruebas: **una persona no puede trabajar dos dias seguidos.** No es una
preferencia del armado; es lo que define la escala. La alternancia entre
meses, el reemplazo y el relevo se doblan ante ella.
"""


def _servicio(cliente, h, datos, turno="12x36"):
    servicio = cliente.post("/servicios", headers=h, json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "implantado",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}).json()
    r = cliente.put(f"/implantados/{servicio['id']}/acuerdo", headers=h, json={
        "zona_operacion": "Valle de Mexico", "turno": turno,
        "origen_direccion": "Torre Mayor", "origen_lat": "19.4270",
        "origen_lon": "-99.1677", "geocerca_metros": 250})
    assert r.status_code == 200, r.text
    return servicio


def _plantilla(datos, quienes, empieza=0, rol="conductor_seguridad"):
    return [{"persona_id": datos["personal"][n]["id"],
             "rol_id": datos["perfiles"][rol]["id"],
             "empieza": i == empieza}
            for i, n in enumerate(quienes)]


def _contrato(cliente, h, datos, servicio, anio=2029, mes=4, personal=None,
              unidades=None):
    cuerpo = {
        "servicio_id": servicio["id"], "anio": anio, "mes": mes,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia", "incluye_fines_de_semana": False,
        "hora_presentacion": "08:00:00",
        "titular_id": datos["personal"]["Juan Ramirez"]["id"],
        "precio_mes_vehiculo": "66000", "precio_dia_personal": "2900",
        "precio_dia_adicional": "3500"}
    if unidades is not None:
        cuerpo["vehiculo_id"] = unidades[0]
    r = cliente.post("/implantados/contratos", headers=h, json=cuerpo)
    assert r.status_code == 201, r.text
    contrato_id = r.json()["contrato_id"]

    if personal is not None:
        g = cliente.put(
            f"/implantados/{servicio['id']}/mes/{anio}/{mes}/plantilla",
            headers=h, json={"personal": personal,
                             "unidades": unidades or []})
        assert g.status_code == 200, g.text
    return contrato_id


def _dias(cliente, h, servicio, anio=2029, mes=4):
    """Los dias del mes con quien va en cada uno.

    Del panel del mes y no de la ficha del servicio: la ficha trae las
    jornadas pero no a quien se le asigno cada una.
    """
    panel = cliente.get(f"/implantados/{servicio['id']}/mes/{anio}/{mes}",
                        headers=h).json()
    return sorted(panel["dias"], key=lambda d: d["fecha"])


# ================================================== el mes entero

def test_el_mes_va_completo_y_nadie_trabaja_dos_dias_seguidos(cliente, sesion,
                                                              datos):
    """Las dos cosas que definen la escala, en una sola prueba porque son
    la misma: el mes se cubre entero porque son dos, y son dos porque
    nadie puede hacer dos dias seguidos."""
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos)
    contrato = _contrato(cliente, h, datos, servicio, personal=_plantilla(
        datos, ["Juan Ramirez", "Luis Mendoza"]))
    r = cliente.post(f"/implantados/contratos/{contrato}/generar-mes",
                     headers=h)
    assert r.status_code == 200, r.text
    hecho = r.json()

    # Abril de 2029 tiene 30 dias, y los 30 se generan.
    assert hecho["jornadas_creadas"] == 30, hecho
    assert hecho["turno"] == "12x36"

    dias = _dias(cliente, h, servicio)
    assert len(dias) == 30

    # Cada dia con una sola persona, y nunca la misma dos veces seguidas.
    anterior = None
    for j in dias:
        quienes = [x["persona_id"] for x in j["personal"]]
        assert len(quienes) == 1, (j["fecha"], quienes)
        assert quienes[0] != anterior, f"{j['fecha']}: dos dias seguidos"
        anterior = quienes[0]

    # Y entre las dos se reparten el mes: quince y quince.
    reparto = {}
    for j in dias:
        pid = j["personal"][0]["persona_id"]
        reparto[pid] = reparto.get(pid, 0) + 1
    assert sorted(reparto.values()) == [15, 15], reparto


def test_empieza_quien_el_consultor_marco(cliente, sesion, datos):
    """El orden en que se capturaron es un accidente; esto no."""
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos)
    # Se captura primero a Juan, pero empieza Luis.
    contrato = _contrato(cliente, h, datos, servicio, personal=_plantilla(
        datos, ["Juan Ramirez", "Luis Mendoza"], empieza=1))
    cliente.post(f"/implantados/contratos/{contrato}/generar-mes", headers=h)

    dias = _dias(cliente, h, servicio)
    assert dias[0]["personal"][0]["persona_id"] == \
        datos["personal"]["Luis Mendoza"]["id"]


def test_el_mes_sale_entero_en_verde(cliente, sesion, datos):
    """En 12x36 no existe el ambar del fin de semana: no hay dia que
    nazca sin saber quien lo cubre."""
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos)
    contrato = _contrato(cliente, h, datos, servicio, personal=_plantilla(
        datos, ["Juan Ramirez", "Luis Mendoza"]))
    cliente.post(f"/implantados/contratos/{contrato}/generar-mes", headers=h)

    panel = cliente.get(f"/implantados/{servicio['id']}/calendario/2029/4",
                        headers=h).json()
    assert panel["turno"] == "12x36"
    estados = {d["estado"] for d in panel["dias"]}
    assert "por_cubrir" not in estados, panel["dias"]
    assert "sin_servicio" not in estados, panel["dias"]


# ================================================== las reglas

def test_con_una_sola_persona_no_hay_escala(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos)
    r = cliente.post("/implantados/contratos", headers=h, json={
        "servicio_id": servicio["id"], "anio": 2029, "mes": 5,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia", "hora_presentacion": "08:00:00",
        "titular_id": datos["personal"]["Juan Ramirez"]["id"],
        "precio_dia_personal": "2900"})
    assert r.status_code == 201, r.text

    mala = cliente.put(f"/implantados/{servicio['id']}/mes/2029/5/plantilla",
                       headers=h, json={"personal": _plantilla(
                           datos, ["Juan Ramirez"]), "unidades": []})
    assert mala.status_code == 409, mala.text
    assert "dos personas" in mala.text


def test_las_dos_tienen_que_ser_de_la_misma_categoria(cliente, sesion, datos):
    """De la categoria salen el precio al cliente y la comision. Con dos
    distintas, lo que se cobra cambiaria segun el dia que caiga."""
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos)
    cliente.post("/implantados/contratos", headers=h, json={
        "servicio_id": servicio["id"], "anio": 2029, "mes": 6,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia", "hora_presentacion": "08:00:00",
        "titular_id": datos["personal"]["Juan Ramirez"]["id"],
        "precio_dia_personal": "2900"})

    revueltas = [
        {"persona_id": datos["personal"]["Juan Ramirez"]["id"],
         "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
         "empieza": True},
        {"persona_id": datos["personal"]["Luis Mendoza"]["id"],
         "rol_id": datos["perfiles"]["agente_seguridad"]["id"],
         "empieza": False},
    ]
    r = cliente.put(f"/implantados/{servicio['id']}/mes/2029/6/plantilla",
                    headers=h, json={"personal": revueltas, "unidades": []})
    assert r.status_code == 409, r.text
    assert "categoria" in r.text


def test_hay_que_decir_cual_empieza(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos)
    cliente.post("/implantados/contratos", headers=h, json={
        "servicio_id": servicio["id"], "anio": 2029, "mes": 7,
        "modalidad_id": datos["modalidades"]["full_day"]["id"],
        "esquema": "por_dia", "hora_presentacion": "08:00:00",
        "titular_id": datos["personal"]["Juan Ramirez"]["id"],
        "precio_dia_personal": "2900"})

    sin_marcar = [{"persona_id": datos["personal"][n]["id"],
                   "rol_id": datos["perfiles"]["conductor_seguridad"]["id"],
                   "empieza": False}
                  for n in ("Juan Ramirez", "Luis Mendoza")]
    r = cliente.put(f"/implantados/{servicio['id']}/mes/2029/7/plantilla",
                    headers=h, json={"personal": sin_marcar, "unidades": []})
    assert r.status_code == 409, r.text
    assert "empieza" in r.text


def test_no_hay_dias_adicionales(cliente, sesion, datos):
    """Lo que el cliente pida de mas sale como un eventual aparte."""
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos)
    contrato = _contrato(cliente, h, datos, servicio, personal=_plantilla(
        datos, ["Juan Ramirez", "Luis Mendoza"]))
    cliente.post(f"/implantados/contratos/{contrato}/generar-mes", headers=h)

    # Ningun dia del mes nace marcado como adicional.
    resumen = cliente.get(f"/implantados/contratos/{contrato}/resumen",
                          headers=h).json()
    assert resumen["dias"]["adicionales"] == 0, resumen["dias"]

    # Y la puerta para agregar uno esta cerrada, con la salida escrita.
    r = cliente.post(f"/implantados/contratos/{contrato}/dias-adicionales",
                     headers=h, json={"fecha": "2029-04-15"})
    assert r.status_code == 409, r.text
    assert "eventual" in r.text.lower()


# ================================================== el natural no se toca

def test_el_implantado_natural_sigue_igual(cliente, sesion, datos):
    """El 12x36 entra por una bifurcacion, no reescribiendo lo que opera.

    Un implantado de 12 horas naturales de lunes a viernes sigue con sus
    dias habiles, su fin de semana en ambar y su plantilla de una sola
    persona.
    """
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos, turno="natural")
    contrato = _contrato(cliente, h, datos, servicio, anio=2029, mes=8,
                         personal=_plantilla(datos, ["Juan Ramirez"]))
    r = cliente.post(f"/implantados/contratos/{contrato}/generar-mes",
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["turno"] == "natural"

    # Agosto de 2029 tiene 31 dias y 23 habiles.
    dias = _dias(cliente, h, servicio, 2029, 8)
    assert len(dias) == 23, len(dias)


# ================================================== el reemplazo

def _quienes(dias):
    """Un nombre por dia, en orden."""
    return [d["personal"][0]["nombre"] if d["personal"] else None
            for d in dias]


def _montar(cliente, h, datos, empieza=0):
    servicio = _servicio(cliente, h, datos)
    contrato = _contrato(cliente, h, datos, servicio, personal=_plantilla(
        datos, ["Juan Ramirez", "Luis Mendoza"], empieza=empieza))
    r = cliente.post(f"/implantados/contratos/{contrato}/generar-mes",
                     headers=h)
    assert r.status_code == 200, r.text
    return servicio, contrato


def test_el_que_cubre_toma_los_dias_del_que_falta_y_nada_mas(cliente, sesion,
                                                             datos):
    """La regla de Salvador: A se enferma, B sigue igual, entra C.

    Nada de intercambiar turnos entre A y B: eso le moveria los dias a
    quien no falto. C toma los dias de A y B no se entera.

    Esto no necesito codigo nuevo --el motor de relevo ya mira dia por
    dia si el que sale esta asignado, y el dia que no lo esta lo salta--
    pero si necesita esta prueba: es lo unico que garantiza que siga
    siendo cierto cuando alguien toque el motor por otra razon.
    """
    h = sesion("consultor")
    servicio, _ = _montar(cliente, h, datos)
    dias = _dias(cliente, h, servicio)
    antes = _quienes(dias)

    # Juan empieza, asi que los dias pares son suyos. Se enferma el tercero.
    assert antes[0] == "Juan Ramirez" and antes[1] == "Luis Mendoza"
    desde = dias[2]["fecha"]

    r = cliente.post(f"/implantados/{servicio['id']}/cambios", headers=h, json={
        "tipo": "personal", "desde": desde, "hasta": dias[-1]["fecha"],
        "sale_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_id": datos["personal"]["Miguel Torres"]["id"],
        "motivo": "enfermedad"})
    assert r.status_code == 200, r.text
    # Juan no se presento ningun dia: no hay nada que partir.
    assert r.json()["jornadas_partidas"] == [], r.json()

    despues = _quienes(_dias(cliente, h, servicio))

    # Los dos primeros dias no se tocan: ya pasaron por el calendario.
    assert despues[:2] == antes[:2]
    # De ahi en adelante, los dias de Juan son de Miguel...
    assert despues[2::2] == ["Miguel Torres"] * len(despues[2::2])
    # ...y los de Luis siguen siendo de Luis, intactos.
    assert despues[1::2] == antes[1::2] == ["Luis Mendoza"] * len(antes[1::2])

    # Y la escala se sostiene: nadie hace dos dias seguidos.
    for uno, otro in zip(despues, despues[1:]):
        assert uno != otro, despues


def test_si_el_que_falta_ya_arranco_el_dia_se_paga_a_los_dos(cliente, sesion,
                                                             datos):
    """El dia partido, en 12x36.

    Si el cambio se hace el dia que A ya arranco, ese turno se paga a los
    dos: A cobra lo que trabajo y el que lo cubre cobra su dia. Si se
    supiera con anticipacion no habria nada que partir --A no se
    presento-- y solo se pagarian los dias del que cubre.
    """
    from datetime import datetime, timedelta

    from ayudas import marcar

    h = sesion("consultor")
    servicio, _ = _montar(cliente, h, datos)
    dias = _dias(cliente, h, servicio)
    suyo = dias[2]                      # un dia de Juan

    # Juan llega a su punto: a partir de aqui su dia vale.
    panel = cliente.get(f"/servicios/{servicio['id']}", headers=h).json()
    jornada = next(j for j in panel["equipos"][0]["jornadas"]
                   if j["id"] == suyo["jornada_id"])
    inicio = datetime.fromisoformat(jornada["inicio_programado"])
    llegada = marcar(cliente, sesion("juan"), suyo["jornada_id"],
                     "llegada_origen", inicio - timedelta(minutes=10))
    assert llegada.status_code == 200, llegada.text

    r = cliente.post(f"/implantados/{servicio['id']}/cambios", headers=h, json={
        "tipo": "personal", "desde": suyo["fecha"], "hasta": dias[-1]["fecha"],
        "sale_id": datos["personal"]["Juan Ramirez"]["id"],
        "entra_id": datos["personal"]["Miguel Torres"]["id"],
        "motivo": "enfermedad"})
    assert r.status_code == 200, r.text
    assert r.json()["jornadas_partidas"] == [suyo["fecha"]], r.json()

    # Ese dia queda con los dos: el que trabajo la manana y el que entro.
    ese = next(d for d in _dias(cliente, h, servicio)
               if d["fecha"] == suyo["fecha"])
    nombres = {x["nombre"] for x in ese["personal"]}
    assert nombres == {"Juan Ramirez", "Miguel Torres"}, nombres


def test_el_12x36_cobra_paga_y_da_viaticos_por_el_mes_entero(cliente, sesion,
                                                             datos):
    """Las tres cuentas de la escala, en una sola pasada.

    * Se cobra el mes entero: todos los dias son base y ninguno
      adicional, porque aqui no hay fin de semana fuera del trato.
    * A cada quien se le pagan SUS dias: la pareja se alterna, asi que
      entre las dos suman el mes y ninguna lo trabaja completo.
    * Los viaticos van por mes y por persona, sobre los dias de cada
      quien y no sobre los del servicio.
    """
    h = sesion("consultor")
    servicio = _servicio(cliente, h, datos)
    contrato = _contrato(cliente, h, datos, servicio, anio=2029, mes=9,
                         personal=_plantilla(
                             datos, ["Juan Ramirez", "Luis Mendoza"]))
    cliente.post(f"/implantados/contratos/{contrato}/generar-mes", headers=h)

    # 1 · El cobro: septiembre entero, sin dias adicionales.
    resumen = cliente.get(f"/implantados/contratos/{contrato}/resumen",
                          headers=h).json()
    assert resumen["dias"]["base"] == 30, "no se cobra el mes entero"
    assert resumen["dias"]["adicionales"] == 0, "en 12x36 no hay adicionales"
    # Y el numero que la pantalla enseña dice lo mismo que la factura.
    alta = cliente.get(f"/implantados/{servicio['id']}/mes/2029/9",
                       headers=h).json()
    assert len(alta["dias"]) == 30

    # 2 · La paga: cada quien sus dias, y entre las dos el mes.
    dias = _dias(cliente, h, servicio, 2029, 9)
    reparto = {}
    for j in dias:
        reparto.setdefault(j["personal"][0]["persona_id"], set()).add(j["fecha"])
    assert len(reparto) == 2, "la escala es de dos personas"
    assert sum(len(v) for v in reparto.values()) == 30
    assert all(len(v) < 30 for v in reparto.values()), \
        "alguien aparece trabajando el mes entero"

    # 3 · Los viaticos: por mes y por persona, sobre los dias de cada uno.
    vista = cliente.get(f"/implantados/{servicio['id']}/viaticos/2029/9",
                        headers=h).json()
    assert vista["periodo"] == "09/2029"
    filas = {f["persona_id"]: f for f in vista["personal"]}
    assert set(filas) == set(reparto), "el panel no trae a las dos"
    for quien, fila in filas.items():
        assert fila["dias"] == len(reparto[quien]), \
            "los viaticos no salen de los dias de esa persona"

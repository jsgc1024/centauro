"""Paso B4: los que llamaban a la puerta vieja llaman a la unica."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- test_implantados ------------------------------------------------
R = RAIZ / "backend/tests/test_implantados.py"
s = R.read_text()
ini = s.index("def test_el_reemplazo_queda_registrado(cliente, sesion, datos):")
fin = s.index("def test_no_se_duplica_el_contrato_del_mismo_mes(cliente, sesion, datos):")
NUEVO = '''def test_el_cambio_de_un_dia_queda_registrado(cliente, sesion, datos):
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


'''
s = s[:ini] + NUEVO + s[fin:]
R.write_text(s)
print("test_implantados.py: el dia suelto pasa por la puerta unica")

# --- test_relevo: la raya cambia de forma ----------------------------
R = RAIZ / "backend/tests/test_relevo.py"
s = R.read_text()
ini = s.index("def test_el_implantado_no_pasa_por_aqui(cliente, sesion, datos):")
fin = s.index("def test_al_que_entra_no_se_le_abre_dinero_solo(cliente, sesion, datos):")
NUEVO = '''def test_el_implantado_tiene_que_decir_hasta_cuando(cliente, sesion, datos):
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

    # Abril no se movio: sigue siendo de Juan.
    abril = cliente.get(
        f"/implantados/contratos/{contratos[4]['contrato_id']}/resumen",
        headers=h).json()
    assert abril["total_reemplazos"] == 0, abril["reemplazos"]


'''
s = s[:ini] + NUEVO + s[fin:]
R.write_text(s)
print("test_relevo.py: la raya cambio de forma y el tope tiene prueba")

# --- el guion de humo ------------------------------------------------
R = RAIZ / "probar_implantado.py"
s = R.read_text()
VIEJO = '''c, rem = pedir("POST", f"/implantados/jornadas/{jornada_media['id']}/reemplazo",
               {"entra_id": luis["id"], "motivo": "enfermedad",
                "nota": "Incapacidad de un dia"}, token=ana)
print(f"   {rem['fecha']}: sale {rem['sale']}, entra {rem['entra']} "
      f"({rem['motivo']})")'''
NUEVO = '''c, rem = pedir("POST", f"/implantados/{srv['id']}/cambios",
               {"tipo": "personal", "desde": jornada_media["fecha"],
                "hasta": jornada_media["fecha"], "sale_id": juan["id"],
                "entra_id": luis["id"], "motivo": "enfermedad",
                "nota": "Incapacidad de un dia"}, token=ana)
print(f"   {rem['desde']}: sale {rem['sale']}, entra {rem['entra']} "
      f"({rem['motivo']})")
if rem.get("dias_partidos"):
    print(f"   dia partido: {', '.join(rem['dias_partidos'])} "
          f"—los dos cobran su parte")
if rem.get("aviso"):
    print(f"   {rem['aviso']}")'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("probar_implantado.py: al dia")

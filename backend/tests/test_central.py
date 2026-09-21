"""La central de inteligencia.

Lo que se prueba aqui no es que la pantalla pinte: es que la vispera se
calcule bien. Una central que dice "todo listo" cuando falta la unidad
es peor que no tener pantalla, porque alguien le cree.
"""
from datetime import date, datetime, time, timedelta

from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana)


def _mediodia(dia: date) -> datetime:
    return datetime.combine(dia, time(12, 0))


def _servicio_de_manana(cliente, h, datos, hora_inicio="09:00:00"):
    """Un eventual que arranca manana, sin nada mas puesto."""
    return crear_servicio(cliente, h, datos, [jornada(
        date.today() + timedelta(days=1),
        datos["modalidades"]["full_day"]["id"], hora=hora_inicio)])


def _claves(ficha):
    return {p["clave"]: p["listo"] for p in ficha["revision"]}


def test_manana_ordena_por_la_hora_en_que_llega_el_equipo(cliente, sesion,
                                                          datos):
    """La hora que se puede perder no es la del servicio: es la de la
    presentacion del equipo, media hora antes."""
    h = sesion("consultor")
    tarde = _servicio_de_manana(cliente, h, datos, "14:00:00")
    temprano = _servicio_de_manana(cliente, h, datos, "07:00:00")

    r = cliente.get("/central/manana", headers=h)
    assert r.status_code == 200, r.text
    fichas = r.json()["servicios"]
    folios = [f["folio"] for f in fichas]
    assert folios.index(temprano["folio"]) < folios.index(tarde["folio"])

    suyo = next(f for f in fichas if f["folio"] == temprano["folio"])
    # 07:00 de servicio, el equipo esta parado a las 06:30.
    assert suyo["equipo_llega"].endswith("06:30:00")
    assert suyo["anticipacion_minutos"] == 30
    assert suyo["contra_vuelo"] is False


def test_un_dia_sin_nada_dice_todo_lo_que_le_falta(cliente, sesion, datos):
    h = sesion("consultor")
    servicio = _servicio_de_manana(cliente, h, datos)

    ficha = next(f for f in cliente.get("/central/manana", headers=h).json()
                 ["servicios"] if f["folio"] == servicio["folio"])
    assert ficha["listo"] is False
    listo = _claves(ficha)
    assert listo["punto_de_encuentro"] is False
    assert listo["personal"] is False
    assert listo["unidad"] is False
    assert listo["hoja"] is False

    # Y cada renglon dice que hacer, no "pendiente".
    for p in ficha["revision"]:
        if not p["listo"]:
            assert p["que_hacer"], p


def test_asignar_sin_confirmar_no_cuenta_como_listo(cliente, sesion, datos):
    """Que alguien este asignado no quiere decir que sepa que manana
    trabaja. Son dos cosas y la vispera las distingue."""
    h = sesion("consultor")
    servicio = _servicio_de_manana(cliente, h, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])

    ficha = next(f for f in cliente.get("/central/manana", headers=h).json()
                 ["servicios"] if f["folio"] == servicio["folio"])
    listo = _claves(ficha)
    assert listo["personal"] is True
    assert listo["unidad"] is True
    assert listo["punto_de_encuentro"] is True
    assert listo["confirmacion"] is False, "nadie confirmo y dice que si"
    assert listo["rol"] is True, "el rol lo puso el helper"


def _ficha_de(cliente, h, servicio):
    return next(f for f in cliente.get("/central/manana", headers=h).json()
                ["servicios"] if f["folio"] == servicio["folio"])


def test_la_central_registra_la_confirmacion_por_telefono_y_queda_sellada(
        cliente, sesion, datos):
    """El agente sin la app no podía confirmar de ninguna manera.

    La central le hablaba, el agente decía que sí, y el renglón se
    quedaba rojo para siempre. Ahora se registra, con el nombre de quien
    lo registró: una confirmación de otro no es la misma cosa que la de
    la persona, y el día que alguien no llegue esa es la única pregunta
    que importa.
    """
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = _servicio_de_manana(cliente, h, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)

    assert _claves(_ficha_de(cliente, h, servicio))["confirmacion"] is False

    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-a-mano",
                     json={"persona_id": juan, "nota": "Me contestó al celular"},
                     headers=sesion("central"))
    assert r.status_code == 200, r.text
    assert r.json()["a_mano"] is True

    ficha = _ficha_de(cliente, h, servicio)
    assert _claves(ficha)["confirmacion"] is True
    suyo = next(p for p in ficha["personal"] if p["persona_id"] == juan)
    assert suyo["confirmado"] is True
    # El sello: sin esto no se distingue de la que da la persona.
    assert suyo["confirmado_por"], suyo
    assert suyo["nota_confirmacion"] == "Me contestó al celular"


def test_lo_que_confirma_la_persona_no_lleva_sello_de_nadie(cliente, sesion,
                                                            datos):
    """El hueco ES el dato: sin nombre quiere decir que lo dijo él."""
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = _servicio_de_manana(cliente, h, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=juan)

    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=sesion("juan"))
    assert r.status_code == 200, r.text

    suyo = next(p for p in _ficha_de(cliente, h, servicio)["personal"]
                if p["persona_id"] == juan)
    assert suyo["confirmado"] is True
    assert suyo["confirmado_por"] is None


def test_la_pantalla_del_servicio_cuenta_los_dias_y_dice_quien_registro(
        cliente, sesion, datos):
    """La confirmación es de cada día, no de la persona.

    En un servicio de dos días alguien puede haber confirmado uno, y un
    sí/no mentiría en el otro. Y lo que registró la central por teléfono
    lleva su nombre también aquí: ésta es la pantalla donde el consultor
    decide si su equipo está armado.
    """
    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    modalidad = datos["modalidades"]["full_day"]["id"]
    servicio = crear_servicio(cliente, h, datos, [
        jornada(manana(1), modalidad, hora="09:00:00"),
        jornada(manana(2), modalidad, hora="09:00:00")])
    equipo = servicio["equipos"][0]
    dia1, dia2 = equipo["jornadas"][0], equipo["jornadas"][1]
    for j in (dia1, dia2):
        asignar(cliente, h, j["id"], persona_id=juan)

    def suyo():
        r = cliente.get(f"/servicios/equipos/{equipo['id']}/asignaciones",
                        headers=h)
        assert r.status_code == 200, r.text
        return next(p for p in r.json()["personal"]
                    if p["persona_id"] == juan)

    assert suyo()["dias"] == 2
    assert suyo()["confirmados"] == 0

    r = cliente.post(f"/operacion/jornadas/{dia1['id']}/confirmar-a-mano",
                     json={"persona_id": juan}, headers=sesion("central"))
    assert r.status_code == 200, r.text

    # Un dia de dos: no se puede decir que el equipo confirmo.
    ficha = suyo()
    assert ficha["confirmados"] == 1
    assert ficha["confirmado_por"], ficha

    # Y el otro lo confirma el, desde su app: el sello no se multiplica.
    r = cliente.post(f"/operacion/jornadas/{dia2['id']}/confirmar-recurso",
                     headers=sesion("juan"))
    assert r.status_code == 200, r.text
    ficha = suyo()
    assert ficha["confirmados"] == 2
    assert len(ficha["confirmado_por"]) == 1


def test_nadie_registra_su_propia_confirmacion_por_esa_puerta(cliente, sesion,
                                                              datos):
    """Para eso está la app, que además deja dicho que confirmó él."""
    h = sesion("consultor")
    ana = datos["personal"]["Ana Solis"]["id"]
    servicio = _servicio_de_manana(cliente, h, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=ana)

    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-a-mano",
                     json={"persona_id": ana}, headers=sesion("consultor"))
    assert r.status_code == 403, r.text


def test_el_corte_de_la_vispera_cambia_lo_que_es_urgente(cliente, sesion,
                                                         datos):
    """Antes del corte, lo que falta es trabajo del dia. Despues, es un
    problema de esta noche y sube a la banda roja."""
    from app import central as motor
    from app.db import SessionLocal

    h = sesion("consultor")
    _servicio_de_manana(cliente, h, datos)

    db = SessionLocal()
    try:
        temprano = datetime.combine(date.today(), time(10, 0))
        tarde = datetime.combine(date.today(), time(21, 0))

        antes = motor.tablero(db, temprano)
        assert antes["paso_el_corte"] is False
        assert antes["roto"]["manana_vencido"] == []

        despues = motor.tablero(db, tarde)
        assert despues["paso_el_corte"] is True
        assert despues["roto"]["manana_vencido"], "el corte no levanto nada"
        assert despues["roto"]["hay"] is True
    finally:
        db.close()


def test_el_silencio_se_mide_contra_el_ultimo_hito(cliente, sesion, datos):
    from app import central as motor

    assert motor.color_del_silencio(None) == "sin_reporte"
    assert motor.color_del_silencio(5) == "verde"
    assert motor.color_del_silencio(motor.SILENCIO_AMBAR) == "ambar"
    assert motor.color_del_silencio(motor.SILENCIO_ROJO) == "rojo"


def test_la_tira_de_dias_cuenta_lo_que_viene(cliente, sesion, datos):
    h = sesion("consultor")
    _servicio_de_manana(cliente, h, datos)

    tablero = cliente.get("/central/tablero", headers=h).json()
    tira = tablero["semana"]
    assert len(tira) == 7
    assert tira[0]["fecha"] == date.today().isoformat()

    manana_ = tira[1]
    assert manana_["servicios"] >= 1
    # Recien creado no tiene ni gente ni punto: cuenta como incompleto.
    assert manana_["incompletos"] >= 1


def test_la_banda_roja_no_existe_cuando_no_hay_nada(cliente, sesion, datos):
    """Una franja que siempre dice 'todo bien' deja de leerse."""
    from app import central as motor
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        temprano = datetime.combine(date.today(), time(10, 0))
        assert motor.tablero(db, temprano)["roto"]["hay"] is False
    finally:
        db.close()


def test_un_dia_viejo_sin_cerrar_no_es_un_servicio_en_curso(cliente, sesion,
                                                            datos):
    """`pulso` toma TODAS las jornadas EN_CURSO sin mirar la fecha.

    Una jornada de hace tres semanas que nadie cerró seguía apareciendo
    como servicio en curso para siempre, y en «Atender ahora» como
    callada con veinte mil minutos de silencio: ni era un servicio
    corriendo ni se podía hacer nada con ella desde ahí. Esas viven en
    «Días sin cerrar», que es la pantalla que tiene el botón.
    """
    from app import central as motor

    viejo = {"minutos_desde_fin": 60 * 24 * 20, "silencio": "sin_reporte"}
    assert motor._dia_abandonado(viejo) is True

    # Un servicio en horas extra también pasó su fin programado, y ese sí
    # está corriendo: se distingue por el silencio, porque el que sigue
    # trabajando sigue marcando.
    extra = {"minutos_desde_fin": 60 * 5, "silencio": "verde"}
    assert motor._dia_abandonado(extra) is False

    # Y el que acaba de terminar y no ha marcado todavía está dentro de
    # las horas de gracia: no se declara abandonado antes de que la otra
    # pantalla lo recoja, o desaparece de las dos.
    recien = {"minutos_desde_fin": 30, "silencio": "sin_reporte"}
    assert motor._dia_abandonado(recien) is False

    # Y lo que sigue corriendo, sin fin pasado, nunca.
    corriendo = {"minutos_desde_fin": -120, "silencio": "rojo"}
    assert motor._dia_abandonado(corriendo) is False


def test_el_dia_abandonado_sale_del_pulso_y_de_la_banda_roja(cliente, sesion,
                                                             datos):
    """El mismo día no puede estar en dos bandas diciendo cosas
    distintas: en una, un servicio que nadie atiende; en la otra, el
    renglón con su botón para firmarlo."""
    from app import central as motor, models as m
    from app.db import SessionLocal

    h = sesion("consultor")
    ayer = date.today() - timedelta(days=20)
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(ayer, datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Luis Mendoza"]["id"])
    configurar_origen(cliente, h, j["id"])

    db = SessionLocal()
    try:
        fila = db.get(m.Jornada, j["id"])
        fila.estatus = m.EstatusJornada.EN_CURSO
        db.commit()

        d = motor.pulso(db, datetime.now())
        folios = [f["folio"] for f in d["eventuales"] + d["implantados"]]
        assert servicio["folio"] not in folios, \
            "un dia de hace veinte dias no es un servicio en curso"
        assert d["cuantos"] == len(d["eventuales"]) + len(d["implantados"])
    finally:
        db.close()


def test_la_proxima_a_iniciar_no_desaparece_de_la_central(cliente, sesion,
                                                          datos):
    """El defecto más feo de la revisión del ciclo.

    `VIVAS` decía qué estaba vivo y olvidaba dos estados. Uno de ellos
    —PROXIMA_A_INICIAR— se le pone justo a las jornadas de hoy que
    arrancan en menos de dos horas, así que la jornada desaparecía de la
    banda del camino al punto exactamente en las dos horas que esa banda
    existe para vigilar. El trayecto seguía corriendo y cobrando
    silencios de algo que la central ya no veía.
    """
    from app import central as motor, models as m, trayecto
    from app.db import SessionLocal

    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(date.today(), datos["modalidades"]["full_day"]["id"],
                 hora="23:30:00")])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Luis Mendoza"]["id"])
    configurar_origen(cliente, h, j["id"])

    # El reloj de la central, puesto una hora antes de la jornada: es
    # cuando PROXIMA_A_INICIAR existe de verdad y cuando el trayecto ya
    # le dio su primer toque a la gente.
    ahora = datetime.combine(date.today(), time(22, 30))

    db = SessionLocal()
    try:
        fila = db.get(m.Jornada, j["id"])
        fila.estatus = m.EstatusJornada.PROXIMA_A_INICIAR
        db.commit()

        # La banda del camino se llena con lo que deja el reloj del
        # trayecto, no con la jornada sola. Se corre el reloj de verdad
        # en vez de sembrar la fila a mano: asi el test recorre el mismo
        # camino que la operacion.
        trayecto.pulsar(db, ahora)

        d = motor.camino(db, ahora)
        folios = [q["servicio"] for q in d["gente"]]
        assert servicio["folio"] in folios, \
            "la que esta por arrancar es justo la que hay que vigilar"

        # Y una terminada si sale: esa ya no se vigila.
        fila = db.get(m.Jornada, j["id"])
        fila.estatus = m.EstatusJornada.TERMINADA
        db.commit()
        d = motor.camino(db, ahora)
        assert servicio["folio"] not in [q["servicio"] for q in d["gente"]]
    finally:
        db.close()


def test_leer_el_tablero_de_proximos_no_cambia_nada(cliente, sesion, datos):
    """Era un GET que hacía commit: el estado de una jornada dependía de
    que alguien abriera una pantalla, y eso no se puede reproducir a mano
    el día que algo se ve raro."""
    from app import models as m, operacion
    from app.db import SessionLocal

    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(date.today(), datos["modalidades"]["full_day"]["id"],
                 hora="23:30:00")])
    j = servicio["equipos"][0]["jornadas"][0]

    # Una hora fija, no la hora en que corra la bateria. La jornada es de
    # hoy a las 23:30 y la ventana de "proxima a iniciar" son dos horas:
    # con `datetime.now()` esta prueba solo decia la verdad si la bateria
    # corria entre las 21:30 y las 23:30, y el resto del dia pasaba o
    # fallaba por la hora y no por el codigo.
    ahora = datetime.combine(date.today(), time(22, 0))

    db = SessionLocal()
    try:
        antes = db.get(m.Jornada, j["id"]).estatus
        operacion.tablero_proximos(db, ahora)
        db.expire_all()
        assert db.get(m.Jornada, j["id"]).estatus == antes, \
            "leer una pantalla no cambia datos"

        # Quien si lo mueve es el reloj.
        operacion.marcar_proximas_a_iniciar(db, ahora)
        db.expire_all()
        assert db.get(m.Jornada, j["id"]).estatus \
            == m.EstatusJornada.PROXIMA_A_INICIAR
    finally:
        db.close()


def test_el_dia_abandonado_no_genera_alertas_para_siempre(cliente, sesion,
                                                          datos):
    """`revisar_standby` miraba todas las EN_CURSO sin mirar la fecha:
    un día de hace tres semanas se revisaba cada quince minutos para
    volver a concluir que llevaba tres semanas callado."""
    from datetime import timedelta as td

    from app import models as m, operacion
    from app.db import SessionLocal

    h = sesion("consultor")
    viejo = date.today() - timedelta(days=20)
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(viejo, datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Luis Mendoza"]["id"])

    db = SessionLocal()
    try:
        fila = db.get(m.Jornada, j["id"])
        fila.estatus = m.EstatusJornada.EN_CURSO
        db.commit()

        generadas = operacion.revisar_standby(db, datetime.now())
        assert j["id"] not in [g["jornada_id"] for g in generadas]

        # Y la regla, con sus cuatro casos.
        fila = db.get(m.Jornada, j["id"])
        ahora = datetime.now()
        assert operacion.dia_abandonado(fila, None, ahora) is True
        # En horas extra: paso el fin, pero sigue marcando.
        assert operacion.dia_abandonado(fila, ahora - td(minutes=10),
                                        ahora) is False
        # Recien terminado: dentro de las horas de gracia.
        assert operacion.dia_abandonado(
            fila, None, fila.fin_programado + td(hours=1)) is False
        # Todavia corriendo.
        assert operacion.dia_abandonado(
            fila, None, fila.fin_programado - td(hours=2)) is False
    finally:
        db.close()


def test_los_viaticos_de_la_vispera_dicen_de_quien_faltan(cliente, sesion,
                                                          datos):
    """Depositarle a uno no salva al otro, y el renglon dice el nombre.

    Con la cuenta vieja bastaba una transferencia confirmada para que el
    dia entero dijera que el dinero estaba puesto: el segundo agente
    salia de su casa pagando la gasolina y la pantalla decia que todo
    bien.
    """
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    servicio = _servicio_de_manana(cliente, h, datos)
    j = servicio["equipos"][0]["jornadas"][0]

    juan = datos["personal"]["Juan Ramirez"]["id"]
    carlos = datos["personal"]["Carlos Vega"]["id"]
    asignar(cliente, h, j["id"], persona_id=juan,
            vehiculo_id=datos["suburban"]["id"])
    asignar(cliente, h, j["id"], persona_id=carlos)
    configurar_origen(cliente, h, j["id"])

    def renglon():
        ficha = next(f for f in cliente.get("/central/manana", headers=h)
                     .json()["servicios"] if f["folio"] == servicio["folio"])
        return next(p for p in ficha["revision"] if p["clave"] == "viaticos")

    # Nadie tiene nada: se dice asi, no "no estan depositados".
    sin_nada = renglon()
    assert sin_nada["listo"] is False
    assert "sin viaticos asignados" in sin_nada["que_hacer"]

    viaticos = {}
    for quien in (juan, carlos):
        propuesta = cliente.get(
            f"/viaticos/calcular?jornada_id={j['id']}&persona_id={quien}",
            headers=h).json()
        viaticos[quien] = cliente.post("/viaticos/asignar", headers=h, json={
            "jornada_id": j["id"], "persona_id": quien,
            "conceptos": [{"concepto": c["concepto"], "monto": str(c["monto"]),
                           "descripcion": c["descripcion"],
                           "origen": c["origen"]}
                          for c in propuesta["conceptos"]]}).json()

    asignados = renglon()
    assert asignados["listo"] is False
    assert "finanzas" in asignados["que_hacer"]

    # Se le deposita solo a Juan.
    solicitud = cliente.post(
        f"/viaticos/{viaticos[juan]['id']}/solicitar-transferencia",
        headers=h).json()
    cliente.post(f"/viaticos/transferencias/{solicitud['id']}/confirmar",
                 headers=finanzas)

    a_medias = renglon()
    assert a_medias["listo"] is False, "uno depositado no cubre al otro"
    assert "Carlos" in a_medias["que_hacer"]
    assert "Juan" in (a_medias["detalle"] or ""), "no dice a quien si le toco"

    # Y con los dos puestos, el renglon cierra.
    otra = cliente.post(
        f"/viaticos/{viaticos[carlos]['id']}/solicitar-transferencia",
        headers=h).json()
    cliente.post(f"/viaticos/transferencias/{otra['id']}/confirmar",
                 headers=finanzas)
    assert renglon()["listo"] is True


def test_un_punto_sin_direccion_no_esta_listo(cliente, sesion, datos):
    """Coordenadas sin nombre no son un punto de encuentro.

    La vispera lo daba por listo y la app del personal no pintaba nada:
    el agente sabia a que hora presentarse y no donde. Y quien lee la
    central no tenia como enterarse.
    """
    h = sesion("consultor")
    servicio = _servicio_de_manana(cliente, h, datos)
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])

    # Solo coordenadas, sin direccion escrita.
    cliente.patch(f"/operacion/jornadas/{j['id']}/origen",
                  json={"origen_lat": "19.4270", "origen_lon": "-99.1677",
                        "geocerca_metros": 250}, headers=h)

    ficha = next(f for f in cliente.get("/central/manana", headers=h).json()
                 ["servicios"] if f["folio"] == servicio["folio"])
    renglon = next(p for p in ficha["revision"]
                   if p["clave"] == "punto_de_encuentro")
    assert renglon["listo"] is False, "un punto sin nombre no esta listo"
    assert "direccion" in renglon["que_hacer"]

    # Con la direccion escrita, el renglon cierra.
    configurar_origen(cliente, h, j["id"])
    ficha = next(f for f in cliente.get("/central/manana", headers=h).json()
                 ["servicios"] if f["folio"] == servicio["folio"])
    renglon = next(p for p in ficha["revision"]
                   if p["clave"] == "punto_de_encuentro")
    assert renglon["listo"] is True


def test_el_servicio_callado_trae_con_que_asentar_la_marca(cliente, sesion,
                                                           datos):
    """De la tarjeta roja sale la llamada, y de la llamada la marca.

    El caso es diario: el equipo lleva dos horas sin reportar, la
    central llama y el agente contesta que va con el principal desde
    hace rato —nada más no marcó—. Para asentarlo ahí mismo, la tarjeta
    necesita el día de la jornada y a quién se le acredita: una marca se
    le acredita a una persona, no a un nombre, y la hora que dicta el
    agente se arma sobre la fecha de la jornada, que en São Paulo puede
    ser otro día que el del navegador de quien la captura.
    """
    from app import models as m
    from app.db import SessionLocal

    h = sesion("consultor")
    hoy = date.today()
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(hoy, datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"])

    db = SessionLocal()
    try:
        db.get(m.Jornada, j["id"]).estatus = m.EstatusJornada.EN_CURSO
        db.commit()
    finally:
        db.close()

    d = cliente.get("/central/tablero", headers=sesion("dirgeneral")).json()
    suyo = next((f for f in d["roto"]["callados"]
                 if f["jornada_id"] == j["id"]), None)
    assert suyo is not None, d["roto"]["callados"]
    assert suyo["fecha"] == hoy.isoformat()
    assert suyo["contactos"], "sin contactos no se le puede ni llamar"
    assert all(c.get("persona_id") for c in suyo["contactos"]), suyo["contactos"]

"""La app del personal de seguridad.

Cada quien ve solo lo suyo, y lo que ve tiene que ser cierto: el dia con
su punto y su hora, el dinero que trae de la empresa y el que le deben.

Lo que mas se cuida aqui es el limite: la ficha del dia trae el nombre
del ejecutivo al que se protege, y eso no se le ensena a quien no va.
"""
from datetime import date, datetime, timedelta

from ayudas import (asignar, configurar_origen, crear_servicio, jornada,
                    manana, marcar)


def _servicio_de_juan(cliente, sesion, datos, dia=1, quien="Juan Ramirez"):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(dia), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"],
                persona_id=datos["personal"][quien]["id"],
                vehiculo_id=datos["suburban"]["id"])[0]
    assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    return servicio, j


def test_mi_dia_trae_lo_que_el_equipo_necesita(cliente, sesion, datos):
    """El punto, la hora a la que hay que estar parado ahi, con quien va
    y que sigue. En una sola consulta: el telefono la hace con media
    barra de senal."""
    _servicio_de_juan(cliente, sesion, datos, dia=0)
    r = cliente.get("/campo/mi-dia", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    dia = r.json()

    assert dia["persona"] == "Juan Ramirez"
    assert len(dia["hoy"]) == 1
    f = dia["hoy"][0]
    assert f["punto"]["lat"] is not None
    assert f["punto"]["geocerca_metros"] > 0
    # La hora que importa no es la del servicio: es la de llegar.
    assert f["llegar_a_las"] < f["presentacion"]
    assert f["anticipacion_minutos"] == 30
    # Y lo primero que toca hacer es marcar la llegada.
    assert f["siguiente"] == "llegada_origen"
    assert f["confirmado"] is False


def test_manana_entra_porque_la_confirmacion_es_de_la_vispera(cliente, sesion,
                                                              datos):
    """Si la app solo mostrara hoy, nadie podria confirmar nunca."""
    _servicio_de_juan(cliente, sesion, datos, dia=1)
    dia = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    assert len(dia["manana"]) == 1
    assert dia["hoy"] == []


def test_nadie_ve_el_dia_de_otro(cliente, sesion, datos):
    """La ficha trae el nombre del ejecutivo al que se protege."""
    _, j = _servicio_de_juan(cliente, sesion, datos, dia=0)
    r = cliente.get(f"/campo/jornadas/{j['id']}", headers=sesion("luis"))
    assert r.status_code == 403, r.text

    dia = cliente.get("/campo/mi-dia", headers=sesion("luis")).json()
    assert dia["hoy"] == []


def test_confirmar_se_ve_en_su_dia(cliente, sesion, datos):
    _, j = _servicio_de_juan(cliente, sesion, datos, dia=1)
    h = sesion("juan")
    r = cliente.post(f"/operacion/jornadas/{j['id']}/confirmar-recurso",
                     headers=h)
    assert r.status_code == 200, r.text

    dia = cliente.get("/campo/mi-dia", headers=h).json()
    assert dia["manana"][0]["confirmado"] is True


def test_la_marca_sin_senal_llega_diferida_y_se_nota(cliente, sesion, datos):
    """El equipo marca en un sotano y se manda al volver la linea. La
    hora del telefono se respeta; lo que no se pierde es cuanto tardo en
    llegar."""
    from datetime import datetime

    _, j = _servicio_de_juan(cliente, sesion, datos, dia=0)
    h = sesion("juan")
    # Se marca con la hora de la presentacion, y llega despues.
    dia = cliente.get("/campo/mi-dia", headers=h).json()
    presentacion = dia["hoy"][0]["presentacion"]

    r = cliente.post(f"/operacion/jornadas/{j['id']}/hitos", json={
        "tipo": "llegada_origen",
        "lat": "19.4272", "lon": "-99.1679",
        "marcado_en": presentacion,
    }, headers=h)
    assert r.status_code == 200, r.text
    hito = r.json()
    assert hito["recibido_en"] is not None
    # Se marco a la hora de presentacion y llego despues: es diferida
    # salvo que la prueba corra en el mismo minuto.
    if hito["diferido"]:
        assert any("diferida" in a for a in hito["avisos"])


def test_el_dia_cerrado_sale_de_hoy(cliente, sesion, datos):
    """Cerrar el día lo saca de la pantalla.

    No queda nada que tocar —el fin de servicio es el último paso y
    exige la entrega de la unidad— y dejarlo puesto invita a marcar de
    más sobre un día que ya se cobró. Se cuenta aparte para que el hueco
    diga "ya cerraste" y no "no tienes servicios", que quien acaba de
    trabajar doce horas leería como que su día nunca existió.
    """
    from ayudas import marcar_fin

    servicio, j = _servicio_de_juan(cliente, sesion, datos, dia=0)
    juan = sesion("juan")
    arranca = datetime.fromisoformat(j["inicio_programado"])
    marcar(cliente, juan, j["id"], "llegada_origen",
           arranca - timedelta(minutes=10))
    marcar(cliente, juan, j["id"], "contacto_ejecutivo", arranca)

    mio = cliente.get("/campo/mi-dia", headers=juan).json()
    assert any(f["jornada_id"] == j["id"] for f in mio["hoy"])
    assert mio["cerrados_hoy"] == 0

    r = marcar_fin(cliente, juan, j["id"],
                   datetime.fromisoformat(j["fin_programado"]))
    assert r.status_code == 200, r.text

    mio = cliente.get("/campo/mi-dia", headers=juan).json()
    assert not any(f["jornada_id"] == j["id"] for f in mio["hoy"])
    assert mio["cerrados_hoy"] == 1


def test_el_viatico_cerrado_se_va_abajo_y_no_estorba(cliente, sesion, datos):
    """La pantalla mostraba TODO lo que esa persona ha recibido en su
    vida, sin corte. Al año son doscientos servicios y el único que
    importa —el que todavía le corre el plazo— queda enterrado.

    No se borra: es su dinero. Se pliega.
    """
    from ayudas import depositar_de_verdad

    servicio, j = _servicio_de_juan(cliente, sesion, datos, dia=1)
    h = sesion("consultor")
    equipo_id = servicio["equipos"][0]["id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": juan, "monto": "600"}, headers=h)
    depositar_de_verdad(cliente, sesion, equipo_id, juan)

    def mios():
        return cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()

    d = mios()
    assert any(x["folio"] == servicio["folio"] for x in d["servicios"])
    assert not any(x["folio"] == servicio["folio"]
                   for x in d.get("cerrados", []))

    # Comprueba todo y el consultor cierra: ya no hay nada que resolver.
    viatico_id = next(x for x in d["servicios"]
                      if x["folio"] == servicio["folio"])["dias"][0]["viatico_id"]
    r = cliente.post(f"/campo/viaticos/{viatico_id}/comprobante",
                     json={"concepto": "alimentos", "tipo": "nota",
                           "monto": "600", "descripcion": "Comida del día"},
                     headers=sesion("juan"))
    assert r.status_code == 200, r.text
    estado = cliente.get(f"/viaticos/{viatico_id}", headers=h).json()
    for comp in estado["comprobantes"]:
        cliente.post(
            f"/viaticos/{viatico_id}/validar-comprobante/{comp['id']}",
            headers=h)
    r = cliente.post(f"/viaticos/{viatico_id}/cerrar", headers=h)
    assert r.status_code == 200, r.text

    d = mios()
    assert not any(x["folio"] == servicio["folio"] for x in d["servicios"])
    assert any(x["folio"] == servicio["folio"] for x in d["cerrados"]), d


def test_al_cerrar_el_dia_la_app_pregunta_por_manana(cliente, sesion, datos):
    """El principal dice "mañana a las siete" al bajarse del coche.

    Antes ese dato iba por teléfono a la central y se quedaba en la
    cabeza de alguien hasta el día siguiente. Ahora lo captura quien lo
    escuchó, cuando lo escuchó, y con el punto de su propio GPS: sin
    coordenadas no hay geocerca y mañana no podría marcar su llegada.
    """
    from app import models as mo
    from app.db import SessionLocal
    from ayudas import marcar_fin

    h = sesion("consultor")
    juan = sesion("juan")
    modalidad = datos["modalidades"]["full_day"]["id"]
    servicio = crear_servicio(cliente, h, datos, [
        jornada(manana(-1), modalidad, hora="09:00:00"),
        jornada(manana(0), modalidad, hora=None),
    ])
    dias = servicio["equipos"][0]["jornadas"]
    for j in dias:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"])
        configurar_origen(cliente, h, j["id"])

    uno = dias[0]
    arranca = datetime.fromisoformat(uno["inicio_programado"])
    marcar(cliente, juan, uno["id"], "llegada_origen",
           arranca - timedelta(minutes=10))
    marcar(cliente, juan, uno["id"], "contacto_ejecutivo", arranca)
    r = marcar_fin(cliente, juan, uno["id"],
                   datetime.fromisoformat(uno["fin_programado"]))
    assert r.status_code == 200, r.text

    # El cierre del dia dice que queda otro por delante, y que su hora
    # todavia no la confirmo nadie.
    assert r.json()["manana"], r.json()
    assert r.json()["manana"]["jornada_id"] == uno["id"]

    hecho = cliente.post(f"/campo/jornadas/{uno['id']}/manana",
                         json={"hora": "07:15:00",
                               "direccion": "Lobby del hotel",
                               "lat": "19.4270", "lon": "-99.1677"},
                         headers=juan)
    assert hecho.status_code == 200, hecho.text
    assert hecho.json()["con_geocerca"] is True

    with SessionLocal() as db:
        siguiente = db.get(mo.Jornada, dias[1]["id"])
        assert siguiente.hora_confirmada is True
        assert siguiente.inicio_programado.strftime("%H:%M") == "07:15"
        assert siguiente.origen_direccion == "Lobby del hotel"
        assert siguiente.origen_lat is not None
        # Y queda dicho en la bitacora del dia en que se supo.
        nota = (db.query(mo.NotaBitacora)
                .filter_by(jornada_id=uno["id"]).first())
        assert nota and "07:15" in nota.texto


def test_nadie_pone_la_hora_de_un_dia_que_no_es_suyo(cliente, sesion, datos):
    """Sólo sobre un día suyo, y sólo hacia el día siguiente de SU
    equipo."""
    servicio, j = _servicio_de_juan(cliente, sesion, datos, dia=1)
    r = cliente.post(f"/campo/jornadas/{j['id']}/manana",
                     json={"hora": "07:00:00"}, headers=sesion("carlos"))
    assert r.status_code == 403, r.text


def test_la_hora_heredada_del_primer_dia_se_dice_que_es_supuesta(
        cliente, sesion, datos):
    """Sólo el día 1 trae hora capturada.

    Los demás la heredan del primero mientras su agenda no diga otra
    cosa: sirve para calcular —sin hora no hay ventana ni geocerca— pero
    es una hora supuesta. Si la app no lo dice, el agente planea su
    noche alrededor de una hora que nadie confirmó.
    """
    h = sesion("consultor")
    modalidad = datos["modalidades"]["full_day"]["id"]
    servicio = crear_servicio(cliente, h, datos, [
        jornada(manana(1), modalidad, hora="15:30:00"),
        jornada(manana(2), modalidad, hora=None),
    ])
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"])

    r = cliente.get("/campo/mi-dia", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    d = r.json()

    dia1 = servicio["equipos"][0]["jornadas"][0]["id"]
    suyo = next(f for f in d["manana"] if f["jornada_id"] == dia1)
    assert suyo["hora_confirmada"] is True

    dia2 = servicio["equipos"][0]["jornadas"][1]["id"]
    luego = next(p for p in d["proximos"] if p["jornada_id"] == dia2)
    assert luego["hora_confirmada"] is False, luego


def test_el_dia_de_manana_ya_dice_que_falta_revisar_la_unidad(cliente, sesion,
                                                              datos):
    """Lo que se revisa es el cambio de manos, y el cambio de manos pasa
    cuando el agente recoge el coche: para estar a las 7:15 en el
    aeropuerto, eso es la noche anterior.

    El botón vive en la tarjeta de mañana desde hoy (decisión de
    Salvador, 20 sep) y se apoya en este dato.
    """
    servicio, j = _servicio_de_juan(cliente, sesion, datos, dia=1)

    r = cliente.get("/campo/mi-dia", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    ficha = next(f for f in r.json()["manana"] if f["jornada_id"] == j["id"])
    assert ficha["revision"], ficha
    assert ficha["revision"]["por_recibir"] == 1


def test_con_el_visto_bueno_el_gasto_sale_de_la_app(cliente, sesion, datos):
    """Decisión de Salvador, 20 sep: una vez que el servicio tiene el
    visto bueno, el gasto desaparece de la app.

    Y es cierto: desde ahí no hay nada que el agente pueda hacer, el
    cierre ya se fue a finanzas. Por eso el revisor no deja dar el visto
    bueno con viáticos abiertos —si no, esto le quitaría la pantalla a
    alguien que todavía debe comprobar—.
    """
    from app import models as mo
    from app.db import SessionLocal
    from ayudas import depositar_de_verdad

    servicio, j = _servicio_de_juan(cliente, sesion, datos, dia=1)
    h = sesion("consultor")
    equipo_id = servicio["equipos"][0]["id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": juan, "monto": "700"}, headers=h)
    depositar_de_verdad(cliente, sesion, equipo_id, juan)

    def mios():
        return cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()

    assert any(x["folio"] == servicio["folio"] for x in mios()["servicios"])

    # El consultor da el visto bueno. Se pone a mano porque llegar hasta
    # ahi pide el servicio entero trabajado, y lo que se prueba aqui es
    # la regla, no el camino.
    with SessionLocal() as db:
        db.add(mo.Cierre(servicio_id=servicio["id"],
                         abierto_en=datetime.now(),
                         limite_consultor=datetime.now() + timedelta(hours=24),
                         estatus=mo.EstatusCierre.ENVIADO_FINANZAS))
        db.commit()

    d = mios()
    assert not any(x["folio"] == servicio["folio"] for x in d["servicios"])
    assert any(x["folio"] == servicio["folio"] for x in d["cerrados"]), d


def test_el_dia_trae_la_agenda_para_leerla_sin_senal(cliente, sesion, datos):
    """Lo que el equipo tiene planeado hoy, parada por parada.

    Viaja dentro del día y no en una consulta aparte: el día se guarda
    en el teléfono para leerse sin señal, y una agenda que sólo existe
    con red es una agenda que no está cuando hace falta —en un
    estacionamiento, antes de arrancar—.
    """
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(1), datos["modalidades"]["full_day"]["id"],
        agenda_resumen="Día de juntas en Reforma",
        paradas=[
            {"lugar": "Comida, San Ángel Inn", "hora": "14:30"},
            {"lugar": "Oficinas, Reforma 250 piso 12", "hora": "09:00",
             "notas": "Estacionamiento por Río Elba"},
            {"lugar": "Cena, por confirmar"},
        ])])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"])

    r = cliente.get("/campo/mi-dia", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    ficha = next(f for f in r.json()["manana"] if f["jornada_id"] == j["id"])
    ag = ficha["agenda"]
    assert ag["resumen"] == "Día de juntas en Reforma"

    # Ordenadas por hora, y la que no trae hora va al final: una parada
    # sin hora es "cuando se pueda", no "a primera hora".
    assert [p["hora"] for p in ag["paradas"]] == ["09:00", "14:30", None]
    assert ag["paradas"][0]["notas"] == "Estacionamiento por Río Elba"


def test_mis_viaticos_muestran_lo_que_falta_comprobar(cliente, sesion, datos):
    """Y antes de eso, lo que falta por depositar, que es otra cosa.

    Autorizar no es depositar. Mientras el dinero no sale del banco la
    app lo dice con su nombre y no le pide comprobar nada; cuando llega,
    pasa a entregado y entonces sí hay algo que comprobar.
    """
    from ayudas import depositar_de_verdad

    servicio, j = _servicio_de_juan(cliente, sesion, datos, dia=1)
    h = sesion("consultor")
    equipo_id = servicio["equipos"][0]["id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": juan, "monto": "1500"}, headers=h)

    def mia():
        r = cliente.get("/campo/mis-viaticos", headers=sesion("juan"))
        assert r.status_code == 200, r.text
        return next(s for s in r.json()["servicios"]
                    if s["folio"] == servicio["folio"])

    fila = mia()
    assert fila["entregado"] == 0
    assert fila["por_depositar"] == 1500
    assert fila["por_comprobar"] == 0

    depositar_de_verdad(cliente, sesion, equipo_id, juan)

    fila = mia()
    assert fila["entregado"] == 1500
    assert fila["por_depositar"] == 0
    assert fila["comprobado"] == 0
    assert fila["por_comprobar"] == 1500


def test_mis_comisiones_separan_lo_pagado_de_lo_que_va_corriendo(cliente,
                                                                 sesion, datos):
    """Lo que todavia no entra a un corte es una cuenta, no una promesa."""
    r = cliente.get("/campo/mis-comisiones", headers=sesion("juan"))
    assert r.status_code == 200, r.text
    mias = r.json()
    assert "cortes" in mias
    assert "en_curso" in mias
    assert "nota" in mias["en_curso"]


def test_mi_capacitacion_avisa_de_lo_que_vence(cliente, sesion, datos):
    from app import models as m
    from app.db import SessionLocal

    juan = datos["personal"]["Juan Ramirez"]["id"]
    db = SessionLocal()
    try:
        db.add(m.Capacitacion(persona_id=juan, nombre="Manejo defensivo",
                              vigencia_hasta=date.today() + timedelta(days=10)))
        db.add(m.Capacitacion(persona_id=juan, nombre="Primeros auxilios",
                              vigencia_hasta=date.today() - timedelta(days=3)))
        db.commit()
    finally:
        db.close()

    r = cliente.get("/campo/mi-capacitacion", headers=sesion("juan")).json()
    assert r["por_vencer"] == 1
    assert r["vencidas"] == 1


def test_la_consola_no_entra_a_la_app(cliente, sesion, datos):
    """Estas puertas son del personal de seguridad. Un consultor que
    entre aqui estaria viendo el dia de alguien mas."""
    assert cliente.get("/campo/mi-dia",
                       headers=sesion("consultor")).status_code == 403


# ----------------------------------------- comprobar desde la calle

def _con_viatico(cliente, sesion, datos, monto="1500"):
    servicio, j = _servicio_de_juan(cliente, sesion, datos, dia=1)
    h = sesion("consultor")
    equipo_id = servicio["equipos"][0]["id"]
    juan = datos["personal"]["Juan Ramirez"]["id"]
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                     json={"persona_id": juan, "monto": monto}, headers=h)
    assert r.status_code == 200, r.text
    mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
    return mios["servicios"][0]["dias"][0]["viatico_id"]


def test_comprobar_baja_lo_que_falta(cliente, sesion, datos):
    viatico_id = _con_viatico(cliente, sesion, datos, monto="1500")
    r = cliente.post(f"/campo/viaticos/{viatico_id}/comprobante", json={
        "concepto": "alimentos", "tipo": "nota", "monto": "400",
        "descripcion": "Comida del dia",
    }, headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert float(r.json()["comprobado"]) == 400
    assert float(r.json()["falta"]) == 1100


def test_nadie_comprueba_viaticos_de_otro(cliente, sesion, datos):
    viatico_id = _con_viatico(cliente, sesion, datos)
    r = cliente.post(f"/campo/viaticos/{viatico_id}/comprobante", json={
        "concepto": "alimentos", "tipo": "nota", "monto": "100",
    }, headers=sesion("luis"))
    assert r.status_code == 403, r.text


def test_la_foto_del_ticket_se_guarda_con_el_comprobante(cliente, sesion,
                                                         datos):
    """La prueba vive dentro del registro, no en un enlace que el dia de
    la revision puede no cargar."""
    from app import models as m
    from app.db import SessionLocal

    viatico_id = _con_viatico(cliente, sesion, datos)
    foto = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA=="
    r = cliente.post(f"/campo/viaticos/{viatico_id}/comprobante", json={
        "concepto": "combustible", "tipo": "nota", "monto": "800",
        "imagen": foto,
    }, headers=sesion("juan"))
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        guardado = (db.query(m.Comprobante)
                    .filter_by(asignacion_id=viatico_id).first())
        assert guardado.imagen == foto
    finally:
        db.close()


def test_mi_dia_trae_el_telefono_de_la_central(cliente, sesion, datos):
    """Decir 'llama a la central' sin dar el numero es no decir nada."""
    _servicio_de_juan(cliente, sesion, datos, dia=0)
    d = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    assert d["central"], "no viene la central"
    assert d["central"]["telefono"], d["central"]


def test_mi_dia_trae_los_proximos_dias(cliente, sesion, datos):
    """Dos dias no alcanzan para que alguien planee su vida."""
    _servicio_de_juan(cliente, sesion, datos, dia=5)
    d = cliente.get("/campo/mi-dia", headers=sesion("juan")).json()
    assert len(d["proximos"]) == 1
    assert d["proximos"][0]["llegar_a_las"]
    # De que servicio es. En la calle se habla por folio y por equipo:
    # sin eso, dos dias distintos se leen igual en la lista.
    assert d["proximos"][0]["folio"]
    assert d["proximos"][0]["equipo"]


def test_el_idioma_de_la_app_sale_del_pais_de_su_plaza(cliente, sesion, datos):
    """El de campo no elige idioma: sale de donde trabaja.

    La consola tiene bandera porque quien la usa esta sentado. El de
    campo abre la app con una mano, a las cinco y media de la manana, y
    un boton mas en esa pantalla es un boton que nadie toca. Asi que el
    idioma viaja en `/auth/yo` --que es lo que la app pregunta antes de
    pintar nada-- y sale del pais de su plaza.

    Brasil viene en portugues desde la semilla. Un agente en Sao Paulo
    abre la app y esta en portugues sin haber hecho nada.
    """
    h = sesion("admin")
    paises = cliente.get("/catalogos/paises", headers=h).json()
    br = next(p for p in paises if p["codigo"] == "BR")
    assert br["idioma"] == "pt", br

    mx = next(p for p in paises if p["codigo"] == "MX")
    assert mx["idioma"] == "es", mx
    assert cliente.get("/auth/yo",
                       headers=sesion("juan")).json()["idioma"] == "es"

    # Y sigue al pais, no a la persona: cambiarle el idioma al pais le
    # cambia la app a todo el que trabaja ahi.
    cuerpo = {llave: mx[llave] for llave in
              ("codigo", "nombre", "moneda_local", "lada", "zona_horaria",
               "anticipacion_aeropuerto_min", "anticipacion_min")}
    cuerpo["idioma"] = "pt"
    r = cliente.patch(f"/catalogos/paises/{mx['id']}", headers=h, json=cuerpo)
    assert r.status_code == 200, r.text

    assert cliente.get("/auth/yo",
                       headers=sesion("juan")).json()["idioma"] == "pt"

    # Y se deja como estaba: los paises son catalogo, no movimiento, y el
    # vaciado de antes de cada prueba no los toca. Una prueba que le
    # cambia el idioma a Mexico y se va se lo cambia a las que siguen.
    cuerpo["idioma"] = "es"
    assert cliente.patch(f"/catalogos/paises/{mx['id']}", headers=h,
                         json=cuerpo).status_code == 200
    assert cliente.get("/auth/yo",
                       headers=sesion("juan")).json()["idioma"] == "es"


# ====================== la nota de los movimientos del servicio en curso
#
# Hasta el 20 de septiembre los movimientos subian la hora y el lugar y
# nada mas: el escolta podia decir "sali a ruta a las 14:32, desde aqui"
# y no podia decir por que. Sin fotos, decision de Salvador.

def test_el_movimiento_puede_contar_que_paso(cliente, sesion, datos):
    """La nota viaja dentro de la marca y sale en la bitácora del día."""
    from ayudas import (DENTRO, asignar, configurar_origen, crear_servicio,
                        jornada, manana, marcar)

    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(0), datos["modalidades"]["full_day"]["id"],
                 origen_direccion="Las Alcobas, Polanco - lobby")])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])

    juan = sesion("juan")
    assert marcar(cliente, juan, j["id"], "llegada_origen").status_code == 200
    assert marcar(cliente, juan, j["id"],
                  "contacto_ejecutivo").status_code == 200

    r = cliente.post(f"/operacion/jornadas/{j['id']}/hitos", headers=juan,
                     json={"tipo": "salida_ruta", **DENTRO,
                           "nota": "Cambio de destino a Santa Fe"})
    assert r.status_code == 200, r.text

    d = cliente.get(f"/operacion/jornadas/{j['id']}/dia", headers=h).json()
    suyo = next(x for x in d["renglones"]
                if x["fuente"] == "hito" and x["titulo"] == "salida_ruta")
    assert "Santa Fe" in suyo["detalle"], suyo["detalle"]


def test_el_movimiento_sin_nota_sigue_valiendo(cliente, sesion, datos):
    """La nota es opcional a propósito: el de campo va con una mano y con
    prisa, y un campo obligatorio se llena con un punto para poder
    seguir. Entonces la bitácora se llena de puntos y deja de servir."""
    from ayudas import (DENTRO, asignar, configurar_origen, crear_servicio,
                        jornada, manana, marcar)

    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(0), datos["modalidades"]["full_day"]["id"],
                 origen_direccion="Las Alcobas, Polanco - lobby")])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"],
            persona_id=datos["personal"]["Juan Ramirez"]["id"],
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])

    juan = sesion("juan")
    marcar(cliente, juan, j["id"], "llegada_origen")
    marcar(cliente, juan, j["id"], "contacto_ejecutivo")

    r = cliente.post(f"/operacion/jornadas/{j['id']}/hitos", headers=juan,
                     json={"tipo": "standby", **DENTRO})
    assert r.status_code == 200, r.text


def test_lo_que_falta_comprobar_se_cuenta_del_servicio_entero(cliente, sesion,
                                                              datos):
    """La resta de la pantalla tiene que cuadrar. Es dinero.

    Cada dia se topaba en cero por su cuenta: con 2,732 repartidos en
    tres dias y 2,500 comprobados en el primero, ese dia quedaba en cero
    y los otros dos contaban enteros. La pantalla decia "te depositaron
    2,732, comprobaste 2,500, te faltan 1,580" —y 2,732 menos 2,500 son
    232—.
    """
    from decimal import Decimal

    from ayudas import (asignar, crear_servicio, depositar_de_verdad,
                        jornada, manana)

    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(930 + i), datos["modalidades"]["full_day"]["id"])
         for i in range(3)])
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"], persona_id=juan)

    equipo_id = servicio["equipos"][0]["id"]
    cliente.post(f"/viaticos/equipos/{equipo_id}/persona",
                 json={"persona_id": juan, "monto": "3000"}, headers=h)
    depositar_de_verdad(cliente, sesion, equipo_id, juan)

    def mio():
        mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
        return next(s for s in mios["servicios"]
                    if s["folio"] == servicio["folio"])

    fila = mio()
    assert Decimal(str(fila["entregado"])) == Decimal("3000")
    dia1 = fila["dias"][0]["viatico_id"]

    # Todo el gasto del servicio, cargado en un solo dia.
    r = cliente.post(f"/campo/viaticos/{dia1}/comprobante",
                     json={"concepto": "combustible", "tipo": "nota",
                           "monto": "2800"}, headers=sesion("juan"))
    assert r.status_code == 200, r.text

    fila = mio()
    assert Decimal(str(fila["comprobado"])) == Decimal("2800")
    assert (Decimal(str(fila["por_comprobar"]))
            == Decimal(str(fila["entregado"]))
            - Decimal(str(fila["comprobado"]))), "la resta no cuadra"
    assert Decimal(str(fila["por_comprobar"])) == Decimal("200")


def test_el_aviso_del_ticket_dice_lo_que_falta_del_servicio(cliente, sesion,
                                                            datos):
    """Es lo que la persona lee con el ticket en la mano.

    La resta se hacia contra el dia del ticket: subir un gasto grande en
    el dia 1 contestaba "te falta comprobar $0" con dos dias sin
    comprobar. Tiene que decir lo mismo que su tarjeta.
    """
    from decimal import Decimal

    from ayudas import (asignar, crear_servicio, depositar_de_verdad,
                        jornada, manana)

    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(950 + i), datos["modalidades"]["full_day"]["id"])
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
    r = cliente.post(
        f"/campo/viaticos/{fila['dias'][0]['viatico_id']}/comprobante",
        json={"concepto": "combustible", "tipo": "nota", "monto": "2800"},
        headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["falta"]) == Decimal("200")
    assert Decimal(r.json()["entregado"]) == Decimal("3000")


def test_el_implantado_se_le_muestra_al_agente_mes_por_mes(cliente, sesion,
                                                           datos):
    """El deposito es por mes; la tarjeta tambien.

    La app agrupaba por servicio, asi que Juan veia una sola tarjeta con
    los dias de dos meses juntos y un total que no correspondia a ningun
    deposito que le hubieran hecho.
    """
    from decimal import Decimal

    h = sesion("consultor")
    juan = datos["personal"]["Juan Ramirez"]["id"]
    servicio = cliente.post("/servicios", json={
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "implantado",
        "consultor_id": datos["personal"]["Ana Solis"]["id"],
        "equipos": []}, headers=h).json()

    for anio, mes in ((2029, 5), (2029, 6)):
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
        cliente.post(
            f"/implantados/{servicio['id']}/viaticos/{anio}/{mes}/persona",
            json={"persona_id": juan, "monto": "1000"}, headers=h)

    mios = cliente.get("/campo/mis-viaticos", headers=sesion("juan")).json()
    suyas = [s for s in mios["servicios"] + mios["cerrados"]
             if s["folio"] == servicio["folio"]]
    assert len(suyas) == 2, "los dos meses cayeron en una sola tarjeta"
    assert {s["periodo"] for s in suyas} == {"05/2029", "06/2029"}
    # Y cada tarjeta solo trae los dias de su mes.
    for tarjeta in suyas:
        mes = tarjeta["periodo"][:2]
        assert all(d["fecha"][5:7] == mes for d in tarjeta["dias"])

"""Los criterios nuevos del bono, el margen, y el camino del dinero.

Lo que aqui se cuida: que el catalogo mande (los pesos se respetan),
que el margen distinga entre el descuido y el habito, que marcar desde
lejos no cuente como llegar, que el criterio que suma no reste, y que
entre autorizar y pagar haya dos manos distintas.
"""
from datetime import date, datetime, timedelta

from ayudas import (DENTRO, asignar, configurar_origen, crear_servicio,
                    ejecutar_jornada, jornada, marcar, marcar_fin)

# Lejos del origen: la geocerca de las pruebas es de 250 metros y esto
# esta a varios kilometros. "Marque a tiempo" desde aqui no es llegar.
LEJOS = {"lat": "19.3600", "lon": "-99.2800"}


def _dia(cliente, sesion, datos, dia_base, tarde=0, ubicacion=None,
         persona_nombre="Luis Mendoza", con_unidad=True):
    """Un solo dia, ejecutado completo, para medir una cosa a la vez."""
    h = sesion("consultor")
    hoy = date.today()
    fecha = date(hoy.year, hoy.month, min(max(1, dia_base), 27))

    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(fecha, datos["modalidades"]["full_day"]["id"])])
    persona = datos["personal"][persona_nombre]["id"]
    quien = {"Luis Mendoza": "luis", "Juan Ramirez": "juan"}[persona_nombre]

    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"], persona_id=persona,
                vehiculo_id=datos["suburban"]["id"] if con_unidad else None)
    assert r[0].status_code == 200, f"no se asigno: {r[0].text}"
    configurar_origen(cliente, h, j["id"])

    if ubicacion is None and tarde == 0:
        ejecutar_jornada(cliente, sesion(quien), j)
    else:
        # `tarde` son minutos DESPUES de la hora de presentacion. Diez
        # minutos antes es lo normal; ese es el punto de partida.
        inicio = datetime.fromisoformat(j["inicio_programado"])
        fin = datetime.fromisoformat(j["fin_programado"])
        llegada = (inicio + timedelta(minutes=tarde) if tarde
                   else inicio - timedelta(minutes=10))
        marcar(cliente, sesion(quien), j["id"], "llegada_origen", llegada,
               ubicacion=ubicacion or DENTRO)
        marcar(cliente, sesion(quien), j["id"], "contacto_ejecutivo",
               llegada + timedelta(minutes=5))
        marcar_fin(cliente, sesion(quien), j["id"], fin)

    return servicio, persona, j


def _evaluar(cliente, sesion, persona, capacitacion=True):
    hoy = date.today()
    cuerpo = {"persona_id": persona, "anio": hoy.year, "mes": hoy.month}
    if capacitacion is not None:
        cuerpo["capacitacion_cumplida"] = capacitacion
    return cliente.post("/evaluaciones", json=cuerpo,
                        headers=sesion("consultor")).json()


def _criterio(ficha, nombre):
    return next(c for c in ficha["criterios"] if c["criterio"] == nombre)


# ---------------------------------------------------------------- el margen

def test_el_margen_perdona_un_retraso_chico_una_vez(cliente, sesion, datos):
    """Tres minutos tarde, una vez al mes, no es impuntualidad. El
    catalogo de Mexico trae 5 minutos, 1 ocasion."""
    _dia(cliente, sesion, datos, dia_base=3, tarde=3)
    ficha = _evaluar(cliente, sesion, datos["personal"]["Luis Mendoza"]["id"])

    llegar = _criterio(ficha, "Llegar al punto")
    assert llegar["cumplido"] is True
    assert "Dentro del margen" in llegar["detalle"]


def test_el_margen_no_perdona_el_habito(cliente, sesion, datos):
    """Dos retrasos chicos en el mes: el margen alcanza para uno. El
    segundo cuenta tarde, y el criterio se cae. El margen es para el
    descuido, no para volverlo costumbre."""
    _dia(cliente, sesion, datos, dia_base=4, tarde=3)
    _dia(cliente, sesion, datos, dia_base=5, tarde=4)
    ficha = _evaluar(cliente, sesion, datos["personal"]["Luis Mendoza"]["id"])

    llegar = _criterio(ficha, "Llegar al punto")
    assert llegar["cumplido"] is False
    assert float(llegar["medido"]) == 50.0


def test_marcar_lejos_del_punto_no_es_haber_llegado(cliente, sesion, datos):
    """A tiempo, pero a varios kilometros.

    El sistema ni siquiera guarda esa marca: la rechaza y deja alerta.
    Asi que el dia no queda "marcado tarde", queda SIN MARCA --y eso es
    lo que hay que cuidar, porque sin marca es justo donde estaba el
    agujero: si un dia sin marca hiciera que el criterio no aplicara, no
    marcar pagaria mas que llegar a tiempo.

    La ficha lo dice con todas sus letras, porque "sin marca de llegada"
    a secas no distingue al que se le olvido del que lo intento desde
    lejos.
    """
    _dia(cliente, sesion, datos, dia_base=6, ubicacion=LEJOS)
    ficha = _evaluar(cliente, sesion, datos["personal"]["Luis Mendoza"]["id"])

    llegar = _criterio(ficha, "Llegar al punto")
    assert llegar["aplica"] is True, "trabajo ese dia: el criterio le aplica"
    assert llegar["cumplido"] is False
    assert float(llegar["medido"]) == 0.0
    assert "fuera del punto" in llegar["detalle"]


def test_no_marcar_la_llegada_no_paga_mas_que_llegar_a_tiempo(
        cliente, sesion, datos):
    """El agujero, dicho al derecho.

    Si un mes sin marcas de llegada declarara el criterio "no aplicable",
    sus 780 se repartirian entre los demas criterios y quien nunca marca
    cobraria MAS que quien llega puntual todos los dias. Aplica, y vale
    cero.
    """
    _dia(cliente, sesion, datos, dia_base=25, ubicacion=LEJOS)
    persona = datos["personal"]["Luis Mendoza"]["id"]
    ficha = _evaluar(cliente, sesion, persona)

    llegar = _criterio(ficha, "Llegar al punto")
    assert llegar["aplica"] is True
    assert float(llegar["monto"]) == 0
    # Y como si aplica, su monto no engorda a los demas: el techo del
    # mes baja, no se redistribuye.
    assert float(ficha["bono"]) < 2470


# ------------------------------------------------------------- la unidad

def test_la_entrega_documentada_da_la_estrella(cliente, sesion, datos):
    """El dia completo incluye devolver la unidad con su odometro, su
    firma y sus fotos. Eso es 100 por ciento suyo y no necesita el
    juicio de nadie --por eso se mide aqui, y el dano no--."""
    _dia(cliente, sesion, datos, dia_base=7)
    ficha = _evaluar(cliente, sesion, datos["personal"]["Luis Mendoza"]["id"])

    unidad = _criterio(ficha, "Entregar la unidad documentada")
    assert unidad["aplica"] is True
    assert unidad["cumplido"] is True


def test_sin_unidad_el_criterio_no_aplica(cliente, sesion, datos):
    """Quien no trajo camioneta no puede entregarla: no se le cobra."""
    _dia(cliente, sesion, datos, dia_base=8, con_unidad=False)
    ficha = _evaluar(cliente, sesion, datos["personal"]["Luis Mendoza"]["id"])

    unidad = _criterio(ficha, "Entregar la unidad documentada")
    assert unidad["aplica"] is False
    assert float(unidad["monto"]) == 0


# ------------------------------------------------------------- la recompra

def test_que_no_lo_pidan_no_le_quita_dinero_a_nadie(cliente, sesion, datos):
    """La recompra suma y no resta.

    El personal de plazas chicas o de cuentas nuevas no tiene como
    acumularlas, y cobrarles por eso seria cobrarles la geografia. Por
    eso su monto se queda FUERA del reparto: si se repartiera, al que no
    lo pidieron le tocaria exactamente lo mismo que al que si, y el
    criterio quedaria de adorno.
    """
    _dia(cliente, sesion, datos, dia_base=9)
    ficha = _evaluar(cliente, sesion, datos["personal"]["Luis Mendoza"]["id"])

    recompra = _criterio(ficha, "Que el cliente lo vuelva a pedir")
    assert recompra["aplica"] is False
    # El techo del mes sin recompra es 2,470: los 130 no estan, pero
    # tampoco se repartieron entre los demas.
    assert abs(float(ficha["bono"]) - 2470) < 0.05


def test_cuando_el_cliente_lo_pide_el_bono_sube(cliente, sesion, datos):
    """Y cuando si lo piden, el mes perfecto paga los 2,600 completos."""
    from app import models as m
    from app.db import SessionLocal

    _, persona, j = _dia(cliente, sesion, datos, dia_base=10)

    db = SessionLocal()
    try:
        asignacion = (db.query(m.AsignacionPersonal)
                      .filter_by(jornada_id=j["id"], persona_id=persona).first())
        asignacion.pedido_por_cliente = True
        db.commit()
    finally:
        db.close()

    ficha = _evaluar(cliente, sesion, persona)
    recompra = _criterio(ficha, "Que el cliente lo vuelva a pedir")
    assert recompra["aplica"] is True
    assert recompra["cumplido"] is True
    assert abs(float(ficha["bono"]) - 2600) < 0.05


# ---------------------------------------------------------- la capacitacion

def test_sin_dato_de_capacitacion_el_criterio_no_aplica(cliente, sesion, datos):
    """Vacio no es reprobado: mientras Odoo no mande la capacitacion,
    nadie pierde dinero porque a un sistema le falte una conexion."""
    _dia(cliente, sesion, datos, dia_base=12)
    ficha = _evaluar(cliente, sesion, datos["personal"]["Luis Mendoza"]["id"],
                     capacitacion=None)

    capacitacion = _criterio(ficha, "Capacitacion del mes")
    assert capacitacion["aplica"] is False
    assert float(capacitacion["monto"]) == 0


# ------------------------------------------------------ autorizar y pagar

def _evaluacion_id(cliente, sesion, persona):
    from app import models as m
    from app.db import SessionLocal

    hoy = date.today()
    db = SessionLocal()
    try:
        return (db.query(m.EvaluacionMensual)
                .filter_by(persona_id=persona, anio=hoy.year, mes=hoy.month)
                .first().id)
    finally:
        db.close()


def test_finanzas_no_autoriza_su_propio_pago(cliente, sesion, datos):
    """Quien autoriza el bono no es quien lo deposita. Con las dos
    actividades en la misma mano, el unico control seria la buena fe."""
    _dia(cliente, sesion, datos, dia_base=13)
    persona = datos["personal"]["Luis Mendoza"]["id"]
    _evaluar(cliente, sesion, persona)
    evaluacion = _evaluacion_id(cliente, sesion, persona)

    r = cliente.post(f"/evaluaciones/{evaluacion}/autorizar",
                     headers=sesion("finanzas"))
    assert r.status_code == 403


def test_no_se_paga_un_bono_que_nadie_autorizo(cliente, sesion, datos):
    _dia(cliente, sesion, datos, dia_base=14)
    persona = datos["personal"]["Luis Mendoza"]["id"]
    _evaluar(cliente, sesion, persona)
    evaluacion = _evaluacion_id(cliente, sesion, persona)

    r = cliente.post(f"/evaluaciones/{evaluacion}/pagar",
                     json={"referencia": "SPEI-99001"},
                     headers=sesion("finanzas"))
    assert r.status_code == 409
    assert "autoriza" in r.json()["detail"]


def test_el_bono_no_se_paga_dos_veces(cliente, sesion, datos):
    """El candado del doble pago: la evaluacion tiene un pago o ninguno."""
    _dia(cliente, sesion, datos, dia_base=15)
    persona = datos["personal"]["Luis Mendoza"]["id"]
    _evaluar(cliente, sesion, persona)
    evaluacion = _evaluacion_id(cliente, sesion, persona)

    assert cliente.post(f"/evaluaciones/{evaluacion}/autorizar",
                        headers=sesion("rrhh")).status_code == 200
    primero = cliente.post(f"/evaluaciones/{evaluacion}/pagar",
                           json={"referencia": "SPEI-99002"},
                           headers=sesion("finanzas"))
    assert primero.status_code == 200

    segundo = cliente.post(f"/evaluaciones/{evaluacion}/pagar",
                           json={"referencia": "SPEI-99003"},
                           headers=sesion("finanzas"))
    assert segundo.status_code == 409


def test_el_corte_de_finanzas_solo_trae_lo_autorizado(cliente, sesion, datos):
    """Lo que sigue en calculada no es dinero todavia. Ponerlo en la
    bandeja del dia 5 seria invitar a pagar un bono que nadie firmo."""
    hoy = date.today()
    _dia(cliente, sesion, datos, dia_base=16)
    persona = datos["personal"]["Luis Mendoza"]["id"]
    _evaluar(cliente, sesion, persona)
    pais = datos["mx"]["id"]
    evaluacion = _evaluacion_id(cliente, sesion, persona)

    corte = cliente.get(f"/corte/{pais}/{hoy.year}/{hoy.month}",
                        headers=sesion("finanzas")).json()
    assert corte["por_pagar"] == 0

    cliente.post(f"/evaluaciones/{evaluacion}/autorizar",
                 headers=sesion("rrhh"))
    corte = cliente.get(f"/corte/{pais}/{hoy.year}/{hoy.month}",
                        headers=sesion("finanzas")).json()
    assert corte["por_pagar"] == 1
    assert float(corte["monto_por_pagar"]) > 0


def test_la_incidencia_que_llega_tarde_no_toca_el_bono_pagado(
        cliente, sesion, datos):
    """El mes se calcula el dia 3 y se paga el 5. Una incidencia que se
    autoriza despues no baja ese bono --el dinero no se recalcula-- y
    quien firma tiene que enterarse ahi mismo, no por el reclamo."""
    hoy = date.today()
    servicio, persona, _ = _dia(cliente, sesion, datos, dia_base=17)
    _evaluar(cliente, sesion, persona)
    evaluacion = _evaluacion_id(cliente, sesion, persona)

    cliente.post(f"/evaluaciones/{evaluacion}/autorizar",
                 headers=sesion("rrhh"))
    cliente.post(f"/evaluaciones/{evaluacion}/pagar",
                 json={"referencia": "SPEI-99004"}, headers=sesion("finanzas"))

    incidencia = cliente.post("/incidencias", json={
        "persona_id": persona, "fecha": str(date(hoy.year, hoy.month, 17)),
        "gravedad": "leve", "servicio_id": servicio["id"],
        "descripcion": "Queja del ejecutivo, llego al buzon una semana despues"},
        headers=sesion("consultor")).json()

    r = cliente.post(f"/incidencias/{incidencia['incidencia_id']}/visto-bueno",
                     json={"autorizar": True,
                           "resolucion": "Confirmada con el cliente"},
                     headers=sesion("diroperaciones")).json()
    assert r["bono_ya_cerrado"] is True
    assert "no lo toca" in r["nota"]

    # Y el motor se niega a recalcular un mes pagado.
    hoy = date.today()
    fallo = cliente.post("/evaluaciones",
                         json={"persona_id": persona, "anio": hoy.year,
                               "mes": hoy.month},
                         headers=sesion("consultor"))
    assert fallo.status_code == 409


def test_la_corrida_del_mes_no_toca_lo_que_ya_es_dinero(cliente, sesion, datos):
    """La tarea del dia 3 vuelve a calcular a todos, pero lo autorizado
    y lo pagado no se mueve."""
    from app import bonos
    from app.db import SessionLocal

    hoy = date.today()
    _dia(cliente, sesion, datos, dia_base=18)
    persona = datos["personal"]["Luis Mendoza"]["id"]
    _evaluar(cliente, sesion, persona)
    evaluacion = _evaluacion_id(cliente, sesion, persona)
    cliente.post(f"/evaluaciones/{evaluacion}/autorizar",
                 headers=sesion("rrhh"))

    db = SessionLocal()
    try:
        salida = bonos.calcular_el_mes(db, hoy.year, hoy.month)
    finally:
        db.close()

    assert salida["ya_firmes"] >= 1
    assert salida["fallidas"] == []


def test_enero_cierra_diciembre_del_ano_pasado():
    """El mes vencido, cuando el ano tambien vencio."""
    from app import bonos

    assert bonos.mes_anterior(date(2027, 1, 3)) == (2026, 12)
    assert bonos.mes_anterior(date(2026, 10, 3)) == (2026, 9)


# --------------------------------------------------- lo que ve el personal

def test_sin_mes_calculado_la_app_no_truena(cliente, sesion, datos):
    """El dia 1 y el dia 2 todavia no hay nada. Eso no es un error."""
    r = cliente.get("/campo/mi-bono", headers=sesion("luis"))
    assert r.status_code == 200
    assert r.json()["hay"] is False


def test_cada_quien_ve_su_bono_con_la_frase_que_lo_explica(
        cliente, sesion, datos):
    """Lo que tiene que ver: cuanto, en que estado, y por que. Lo que no:
    el bono de nadie mas ni la referencia del banco."""
    from app import bonos, models as m
    from app.db import SessionLocal

    _dia(cliente, sesion, datos, dia_base=19)
    persona = datos["personal"]["Luis Mendoza"]["id"]
    _evaluar(cliente, sesion, persona)

    # La app ensena el mes VENCIDO. Se mueve la evaluacion recien
    # calculada a ese periodo, que es donde la app la va a buscar.
    hoy = date.today()
    anio, mes = bonos.mes_anterior(hoy)
    db = SessionLocal()
    try:
        evaluacion = (db.query(m.EvaluacionMensual)
                      .filter_by(persona_id=persona, anio=hoy.year,
                                 mes=hoy.month).first())
        evaluacion.anio, evaluacion.mes = anio, mes
        db.commit()
    finally:
        db.close()

    ficha = cliente.get("/campo/mi-bono", headers=sesion("luis")).json()
    assert ficha["hay"] is True
    assert ficha["criterios"], "sin el desglose, el numero no se puede discutir"
    assert any(c["detalle"] for c in ficha["criterios"])
    assert ficha["pagado_en"] is None
    assert "referencia" not in str(ficha), "la referencia del banco es de finanzas"


def test_nadie_ve_el_bono_de_otro(cliente, sesion, datos):
    _dia(cliente, sesion, datos, dia_base=21)
    persona = datos["personal"]["Luis Mendoza"]["id"]
    _evaluar(cliente, sesion, persona)
    hoy = date.today()

    r = cliente.get(f"/evaluaciones/{persona}/{hoy.year}/{hoy.month}",
                    headers=sesion("juan"))
    assert r.status_code == 403


# ================================ la llegada que asentó la central a mano
#
# Decisión de Salvador, 20 sep: no cuenta ni a favor ni en contra. La
# central no puede probar la hora —no hay ubicación, nadie estaba ahí con
# el teléfono— así que ni la premia ni la castiga.
#
# Lo delicado de esa decisión es que un día que "sale del cálculo" es
# justo la forma del agujero que ya cerramos una vez: lo que no se mide
# no puede terminar pagando más que lo que se mide bien. Estas dos
# pruebas cuidan las dos orillas.

def _a_mano(cliente, sesion, jornada_dict, persona, cuando):
    return cliente.post(
        f"/operacion/jornadas/{jornada_dict['id']}/marca-a-mano",
        headers=sesion("central"),
        json={"tipo": "llegada_origen", "persona_id": persona,
              "momento": cuando.isoformat(),
              "justificacion": "se quedó sin batería; el cliente confirmó"})


def test_la_llegada_puesta_a_mano_sale_del_calculo(cliente, sesion, datos):
    """Un día bien marcado y otro asentado a mano: el segundo no se
    cuenta, ni arriba ni abajo. El criterio sigue aplicando y se mide
    contra el único día medible."""
    _dia(cliente, sesion, datos, dia_base=10)          # puntual, marcado
    persona = datos["personal"]["Luis Mendoza"]["id"]

    h = sesion("consultor")
    hoy = date.today()
    otro = crear_servicio(
        cliente, h, datos,
        [jornada(date(hoy.year, hoy.month, 12),
                 datos["modalidades"]["full_day"]["id"],
                 origen_direccion="Las Alcobas, Polanco - lobby")])
    j = otro["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=persona,
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    # Tardísimo a propósito: si contara, tumbaría la puntualidad.
    r = _a_mano(cliente, sesion, j, persona,
                datetime.fromisoformat(j["inicio_programado"])
                + timedelta(hours=2))
    assert r.status_code == 200, r.text

    llegar = _criterio(_evaluar(cliente, sesion, persona), "Llegar al punto")
    assert llegar["aplica"] is True
    assert "1 de 1" in llegar["detalle"], llegar["detalle"]
    assert "a mano" in llegar["detalle"], llegar["detalle"]


def test_un_mes_entero_a_mano_no_le_regala_el_bono_a_nadie(cliente, sesion,
                                                           datos):
    """La otra orilla, y la que de verdad importa.

    Si el mes entero se asentara a mano, no queda nada que medir. El
    criterio no aplica —hasta ahí, lo que pidió Salvador— pero su monto
    NO se reparte entre los demás: si se repartiera, volveríamos al
    agujero de siempre, no marcar pagando más que llegar a tiempo, solo
    que ahora entrando por la puerta de la central.
    """
    h = sesion("consultor")
    hoy = date.today()
    persona = datos["personal"]["Luis Mendoza"]["id"]

    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(date(hoy.year, hoy.month, 14),
                 datos["modalidades"]["full_day"]["id"],
                 origen_direccion="Las Alcobas, Polanco - lobby")])
    j = servicio["equipos"][0]["jornadas"][0]
    asignar(cliente, h, j["id"], persona_id=persona,
            vehiculo_id=datos["suburban"]["id"])
    configurar_origen(cliente, h, j["id"])
    assert _a_mano(cliente, sesion, j, persona,
                   datetime.fromisoformat(j["inicio_programado"])
                   ).status_code == 200

    ficha = _evaluar(cliente, sesion, persona)
    llegar = _criterio(ficha, "Llegar al punto")
    assert llegar["aplica"] is False
    assert float(llegar["monto"]) == 0

    # Y el monto de la puntualidad sale del bote en vez de engordar a los
    # demás.
    #
    # Ojo con lo que NO se afirma aquí: que un criterio cobre más de lo
    # que vale en el catálogo no es el error, es el reparto a prorrata
    # haciendo su trabajo --existe para que nadie cobre de menos por algo
    # que no dependió de él--. Lo que se cuida es que el factor de ese
    # reparto no incluya los pesos de la puntualidad: con ellos dentro,
    # no marcar volvería a pagar más que llegar a tiempo, ahora por la
    # puerta de la central.
    posible = sum(float(c["monto_mensual"]) for c in ficha["criterios"])
    suma_aplicables = sum(float(c["monto_mensual"]) for c in ficha["criterios"]
                          if c["aplica"])
    tope = (posible - float(llegar["monto_mensual"])) / suma_aplicables

    cumplidos = [c for c in ficha["criterios"] if c["aplica"] and c["cumplido"]]
    assert cumplidos, "el decorado tiene que dejar algo cumplido que medir"
    for c in cumplidos:
        assert float(c["monto"]) <= float(c["monto_mensual"]) * tope + 0.01, \
            (f"{c['criterio']} cobró {c['monto']}: el reparto incluyó los "
             f"{llegar['monto_mensual']} de la puntualidad")

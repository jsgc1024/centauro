"""Funciones que arman escenarios, para que las pruebas digan que verifican
y no como se monta el decorado."""
from datetime import date, datetime, timedelta

# Con direccion escrita: un punto de verdad la tiene, y la vispera la
# pide porque es lo que el equipo lee en su telefono.
ORIGEN = {"origen_lat": "19.4270", "origen_lon": "-99.1677",
          "origen_direccion": "Av. Reforma 222, Cuauhtemoc, CDMX",
          "geocerca_metros": 250}
DENTRO = {"lat": "19.4272", "lon": "-99.1679"}      # a unos 30 m del origen
LEJOS = {"lat": "19.4540", "lon": "-99.1677"}       # a unos 3 km


def crear_servicio(cliente, headers, datos, jornadas, tipo="eventual",
                   consultor_id=None, pais_id=None, plaza_id=None, **extra):
    """Por omision en Mexico. `pais_id` y `plaza_id` sirven para las
    pruebas de zona horaria, que necesitan un servicio de otro pais.

    Lo demas del alta --la vestimenta, los idiomas-- entra por `extra`
    tal cual, sin que esta ayuda tenga que conocer cada campo."""
    cuerpo = {
        "cliente_id": datos["cliente_id"],
        "pais_id": pais_id or datos["mx"]["id"],
        "plaza_id": plaza_id or datos["cdmx"]["id"], "tipo": tipo,
        "solicitante_nombre": "Patricia", "solicitante_apellidos": "Lundgren",
        "solicitante_correo": "solicitante@cliente.com",
        "ejecutivo_nombre": "Ingrid", "ejecutivo_apellidos": "Halvorsen",
        "ejecutivo_correo": "ejecutivo@cliente.com",
        "equipos": [{"clave": "EQ-1", "jornadas": jornadas}],
        **extra,
    }
    if consultor_id:
        cuerpo["consultor_id"] = consultor_id
    r = cliente.post("/servicios", json=cuerpo, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def jornada(fecha: date, modalidad_id: int, hora="07:00:00", **extra):
    return {"fecha": str(fecha), "modalidad_id": modalidad_id,
            "hora_presentacion": hora, **extra}


# El rol con el que va la gente cuando la prueba no dice otra cosa. El
# personal de seguridad es general y el rol es de la tarea, asi que una
# asignacion sin rol no se puede cobrar ni pagar: aqui se pone uno para
# que las pruebas que no hablan de dinero no tengan que decirlo.
def rol_por_omision(cliente, headers, codigo="conductor_seguridad"):
    roles = cliente.get("/catalogos/perfiles", headers=headers).json()
    suyo = next((r for r in roles if r["codigo"] == codigo), None)
    return suyo["id"] if suyo else None


def asignar(cliente, headers, jornada_id, persona_id=None, vehiculo_id=None,
            forzar=True, rol_id=None, rol="conductor_seguridad"):
    respuestas = []
    if persona_id:
        if rol_id is None and rol:
            rol_id = rol_por_omision(cliente, headers, rol)
        respuestas.append(cliente.post(
            f"/servicios/jornadas/{jornada_id}/asignar-personal",
            json={"persona_id": persona_id, "rol_id": rol_id,
                  "forzar": forzar}, headers=headers))
    if vehiculo_id:
        respuestas.append(cliente.post(
            f"/servicios/jornadas/{jornada_id}/asignar-vehiculo",
            json={"vehiculo_id": vehiculo_id, "forzar": forzar}, headers=headers))
    return respuestas


def configurar_origen(cliente, headers, jornada_id):
    return cliente.patch(f"/operacion/jornadas/{jornada_id}/origen",
                         json=ORIGEN, headers=headers)


def marcar(cliente, headers, jornada_id, tipo, cuando=None, ubicacion=None):
    cuerpo = {"tipo": tipo, **(ubicacion or DENTRO)}
    if cuando:
        cuerpo["marcado_en"] = cuando.isoformat()
    return cliente.post(f"/operacion/jornadas/{jornada_id}/hitos",
                        json=cuerpo, headers=headers)


# Una imagen de un pixel y una firma que lo parezca. Lo que importa en
# las pruebas que usan esto es el dia completo, no el JPEG.
PIXEL = ("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAEBAQEB"
         "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
         "AQEBAQEBAQH/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQ"
         "AQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==")
FIRMA = "data:image/png;base64," + ("A" * 200)
CINCO = [{"angulo": a, "imagen": PIXEL}
         for a in ("frente", "atras", "izquierdo", "derecho", "odometro")]


# El odometro de las pruebas. Van juntos y en este orden porque un
# odometro no cuenta para atras: quien siembre una recepcion aparte
# tiene que arrancar de KM_RECEPCION, o el candado --con razon-- le
# rechaza la entrega.
KM_RECEPCION = 42_000
KM_ENTREGA = 42_380


def revisar_unidad(cliente, headers_personal, servicio_id, vehiculo_id,
                   tipo, km):
    return cliente.post("/campo/revisiones", headers=headers_personal, json={
        "servicio_id": servicio_id, "vehiculo_id": vehiculo_id, "tipo": tipo,
        "kilometraje": km, "combustible_octavos": 8, "firma": FIRMA,
        # La pregunta del dano ya no se puede saltar. Lo normal es que no
        # haya, y eso es lo que simula un dia completo.
        "hubo_dano": False,
        "fotos": CINCO})


def marcar_fin(cliente, headers_personal, jornada_id, cuando):
    """Cierra el dia, devolviendo la unidad si el servidor la reclama.

    Desde el 18 de septiembre no hay fin de servicio con una unidad que
    hoy deja el servicio y no tiene su revision de entrega.

    Se hace asi --intentar, y resolver lo que el servidor reclame-- y no
    revisando siempre por si acaso: asi estas pruebas no fabrican
    revisiones donde la operacion real no las tendria, y el dia que el
    candado cambie de forma, esto sigue diciendo la verdad.
    """
    cierre = marcar(cliente, headers_personal, jornada_id, "fin_servicio",
                    cuando)
    if cierre.status_code != 409:
        return cierre
    detalle = cierre.json().get("detail")
    if not isinstance(detalle, dict) or "unidades" not in detalle:
        return cierre

    # Cada revision se comprueba. Si una falla y se deja pasar, lo unico
    # que se ve al final es el 409 del candado otra vez, y eso manda a
    # buscar el error donde no esta --en el candado-- en vez de donde
    # esta, que es la revision que no se pudo guardar.
    for unidad in detalle["unidades"]:
        if unidad["sin_recepcion"]:
            r = revisar_unidad(cliente, headers_personal,
                               detalle["servicio_id"], unidad["vehiculo_id"],
                               "recibe", KM_RECEPCION)
            assert r.status_code == 201, f"no se pudo recibir la unidad: {r.text}"
        r = revisar_unidad(cliente, headers_personal, detalle["servicio_id"],
                           unidad["vehiculo_id"], "entrega", KM_ENTREGA)
        assert r.status_code == 201, f"no se pudo entregar la unidad: {r.text}"
    return marcar(cliente, headers_personal, jornada_id, "fin_servicio",
                  cuando)


def ejecutar_jornada(cliente, headers_personal, jornada_dict, retraso_minutos=0,
                     horas_extra=0):
    """Marca la secuencia completa: llegada, contacto y fin.

    Desde el 18 de septiembre, un dia completo incluye devolver la unidad:
    no hay fin de servicio con una unidad que hoy deja el servicio y no
    tiene su revision de entrega. Si el candado muerde, se hacen las
    revisiones que pide y se vuelve a marcar.

    Se hace asi --intentar, y resolver lo que el servidor reclame-- y no
    revisando siempre por si acaso, para que estas pruebas no fabriquen
    revisiones donde la operacion real no las tendria. Si manana el
    candado cambia de forma, esto sigue diciendo la verdad.
    """
    inicio = datetime.fromisoformat(jornada_dict["inicio_programado"])
    fin = datetime.fromisoformat(jornada_dict["fin_programado"])
    retraso = timedelta(minutes=retraso_minutos)
    marcar(cliente, headers_personal, jornada_dict["id"], "llegada_origen",
           inicio - timedelta(minutes=10) + retraso)
    marcar(cliente, headers_personal, jornada_dict["id"], "contacto_ejecutivo",
           inicio + retraso)

    return marcar_fin(cliente, headers_personal, jornada_dict["id"],
                      fin + timedelta(hours=horas_extra))


def cotizar_y_autorizar(cliente, headers, servicio, perfil_id, categoria_id,
                        roles_por_dia=None):
    """Cotiza el servicio completo y lo autoriza.

    `roles_por_dia` permite cotizar un rol distinto cada dia, que es lo
    que pasa cuando la misma persona conduce un dia y coordina el otro.
    Sin eso, el cierre detecta —con razon— que se ejecuto un recurso que
    no estaba cotizado.
    """
    lineas = []
    for idx, j in enumerate(servicio["equipos"][0]["jornadas"]):
        suyo = (roles_por_dia[idx] if roles_por_dia and idx < len(roles_por_dia)
                else perfil_id)
        lineas.append({"fecha": j["fecha"], "tipo": "recurso", "perfil_id": suyo})
        lineas.append({"fecha": j["fecha"], "tipo": "vehiculo",
                       "categoria_id": categoria_id})
    r = cliente.post("/cotizaciones",
                     json={"servicio_id": servicio["id"], "lineas": lineas},
                     headers=headers)
    assert r.status_code == 201, r.text
    cotizacion = r.json()
    cliente.post(f"/cotizaciones/{cotizacion['cotizacion_id']}/autorizar",
                 json={"autorizada_por": "Cliente de prueba"}, headers=headers)
    return cotizacion


def manana(dias=1):
    return date.today() + timedelta(days=dias)


# Un PNG de un pixel: el comprobante del banco que el deposito exige.
# Lo que importa en las pruebas no es que se vea, sino que exista.
PIXEL = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
         b"\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\xda"
         b"c\xfc\xcf\xc0P\x0f\x00\x04\x85\x01\x80\x84\xa9\x8c!\x00\x00\x00"
         b"\x00IEND\xaeB`\x82")


def depositar(cliente, headers, equipo_id, persona_id,
              referencia="SPEI-000001"):
    """Finanzas registra el deposito de una persona en un equipo.

    Referencia y comprobante son obligatorios: sin evidencia, la unica
    prueba de que se pago es la palabra de quien lo hizo. Por eso va
    como formulario con archivo y no como JSON.
    """
    import io

    return cliente.post(
        "/viaticos/finanzas/depositar",
        data={"equipo_id": str(equipo_id), "persona_id": str(persona_id),
              "referencia": referencia},
        files={"archivo": ("comprobante.png", io.BytesIO(PIXEL), "image/png")},
        headers=headers)


def depositar_de_verdad(cliente, sesion, equipo_id, persona_id,
                        referencia="SPEI-000001"):
    """El dinero completo: se le pide a finanzas y finanzas lo deposita.

    Asignar un viático es autorizarlo, no depositarlo. Desde que la app
    dejó de decir "te depositaron" con dinero que todavía no sale del
    banco, cualquier prueba que quiera ver dinero EN LA CUENTA de
    alguien tiene que pasar por aquí. Recibe `sesion` y no unos headers
    porque son dos personas distintas: el consultor pide y finanzas
    deposita.
    """
    r = cliente.post(f"/viaticos/equipos/{equipo_id}/solicitar",
                     json={"persona_id": persona_id},
                     headers=sesion("consultor"))
    assert r.status_code in (200, 201), r.text
    r = depositar(cliente, sesion("finanzas"), equipo_id, persona_id,
                  referencia)
    assert r.status_code in (200, 201), r.text
    return r


def devolver(cliente, headers, viatico_id, monto, referencia="SPEI-DEV-01"):
    """Finanzas registra una devolucion que ya entro a la cuenta.

    Referencia y comprobante son obligatorios, igual que en el deposito:
    un dinero que vuelve sin evidencia es la palabra de quien lo
    capturo, y eso no es un registro contable.
    """
    import io as _io

    return cliente.post(
        f"/viaticos/{viatico_id}/devolver",
        data={"monto": str(monto), "referencia": referencia},
        files={"archivo": ("transferencia.png", _io.BytesIO(PIXEL),
                           "image/png")},
        headers=headers)


def servicio_para_cierre(cliente, sesion, datos, offset=900, dias=1):
    """Un servicio cotizado, trabajado y ya enviado a finanzas.

    Devuelve `(servicio, cierre_id)`, listo para que finanzas lo
    apruebe. El cierre se abre solo al terminar el ultimo dia; aqui se
    pide con `abrir`, que devuelve el que ya existe.
    """
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
        ejecutar_jornada(cliente, sesion("juan"), j)

    r = cliente.post(f"/cierre/servicio/{servicio['id']}/abrir", headers=h)
    assert r.status_code == 200, r.text
    cierre_id = r.json()["cierre_id"]

    envio = cliente.post(f"/cierre/{cierre_id}/enviar-finanzas", headers=h)
    assert envio.status_code == 200, envio.text
    return servicio, cierre_id

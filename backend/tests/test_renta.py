"""El auto subarrendado.

Se renta cuando el cliente pide una categoria que no hay o cuando la
flota esta saturada, y se devuelve al terminar el servicio. Vive en la
misma tabla que la flota propia porque para la operacion es una unidad
igual, y lo que lo separa es el sello: rentado, y el servicio que lo
pidio.
"""
from datetime import date, timedelta

MANANA = date.today() + timedelta(days=1)


def alta(cliente, headers, datos, **extra):
    jornada = {
        "fecha": str(MANANA),
        "modalidad_id": datos["modalidades"]["transfer"]["id"],
        "hora_presentacion": "09:00:00",
        "origen_direccion": "Aeropuerto Benito Juarez, Terminal 1",
    }
    jornada.update(extra.pop("jornada", {}))
    cuerpo = {
        "cliente_id": datos["cliente_id"], "pais_id": datos["mx"]["id"],
        "plaza_id": datos["cdmx"]["id"], "tipo": "eventual",
        "solicitante_nombre": "Karen", "solicitante_apellidos": "Whitfield",
        "ejecutivo_nombre": "James", "ejecutivo_apellidos": "Caldwell",
        "equipos": [{"jornadas": [jornada]}],
    }
    cuerpo.update(extra)
    r = cliente.post("/servicios", json=cuerpo, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def renta(datos, **cambios):
    cuerpo = {
        "placa": "xyz-987-a",
        "categoria_id": datos["categorias"]["suv_blindada"]["id"],
        "color": "negro",
        "marca_modelo": "chevrolet suburban",
        "modelo_anio": 2024,
        "costo_diario": "3500.00",
        "arrendadora": "renta ejecutiva del bajio",
        "arrendadora_telefono": "+52 55 1234 5678",
        "motivo_renta": "categoria_no_disponible",
    }
    cuerpo.update(cambios)
    return cuerpo


def test_el_auto_rentado_se_da_de_alta_y_queda_asignado(cliente, sesion, datos):
    """Un solo paso: el consultor lo captura mientras asigna recursos y
    la unidad ya esta puesta en todos los dias del equipo."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos)
    equipo = servicio["equipos"][0]

    r = cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                     json=renta(datos), headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["rentado"] is True
    assert r.json()["dias"] == 1

    asignadas = cliente.get(f"/servicios/equipos/{equipo['id']}/asignaciones",
                            headers=h).json()["vehiculos"]
    assert len(asignadas) == 1
    unidad = asignadas[0]
    assert unidad["rentado"] is True
    # La regla de captura tambien aplica aqui: placa en mayuscula y lo
    # demas con inicial mayuscula.
    assert unidad["placa"] == "XYZ-987-A"
    assert unidad["marca_modelo"] == "Chevrolet Suburban"
    assert unidad["color"] == "Negro"
    assert unidad["arrendadora"] == "Renta Ejecutiva del Bajio"
    assert unidad["arrendadora_telefono"] == "+52 55 1234 5678"


def test_sin_los_datos_del_proveedor_no_se_guarda(cliente, sesion, datos):
    """De un auto de renta no se sabe nada despues: lo que no quede
    escrito hoy se pierde. Por eso aqui casi todo es obligatorio."""
    h = sesion("consultor")
    equipo = alta(cliente, h, datos)["equipos"][0]

    for falta in ("arrendadora", "arrendadora_telefono", "costo_diario",
                  "motivo_renta", "color", "marca_modelo", "modelo_anio"):
        cuerpo = renta(datos)
        cuerpo.pop(falta)
        r = cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                         json=cuerpo, headers=h)
        assert r.status_code == 422, f"{falta}: {r.text}"


def test_el_costo_de_la_renta_tiene_que_ser_mayor_a_cero(cliente, sesion, datos):
    """Un auto de renta en cero no existe, y dejaria el servicio viendose
    mas rentable de lo que fue."""
    h = sesion("consultor")
    equipo = alta(cliente, h, datos)["equipos"][0]
    r = cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                     json=renta(datos, costo_diario="0"), headers=h)
    assert r.status_code == 422, r.text


def test_el_auto_rentado_no_se_le_ofrece_a_otro_servicio(cliente, sesion, datos):
    """Se pidio para un servicio y con el se devuelve. En otro servicio
    no aparece, aunque siga en la base."""
    h = sesion("consultor")
    equipo = alta(cliente, h, datos)["equipos"][0]
    categoria = datos["categorias"]["suv_blindada"]["id"]
    cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                 json=renta(datos), headers=h)

    perfil = datos["perfiles"]["conductor_seguridad"]["id"]
    suyas = cliente.get(
        f"/servicios/equipos/{equipo['id']}/recomendaciones"
        f"?perfil_id={perfil}&categoria_id={categoria}", headers=h).json()
    placas = _placas(suyas["vehiculos"])
    assert "XYZ-987-A" in placas

    otro = alta(cliente, h, datos, jornada={"fecha": str(MANANA + timedelta(days=7))})
    ajenas = cliente.get(
        f"/servicios/equipos/{otro['equipos'][0]['id']}/recomendaciones"
        f"?perfil_id={perfil}&categoria_id={categoria}", headers=h).json()
    assert "XYZ-987-A" not in _placas(ajenas["vehiculos"])


def test_el_auto_rentado_no_entra_a_la_flota(cliente, sesion, datos):
    """La lista de flota son las unidades de la casa. Si el auto de renta
    saliera ahi, alguien lo asignaria a un servicio donde ya no esta."""
    h = sesion("consultor")
    equipo = alta(cliente, h, datos)["equipos"][0]
    cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                 json=renta(datos), headers=h)

    flota = cliente.get("/catalogos/vehiculos", headers=h).json()
    assert all(v["placa"] != "XYZ-987-A" for v in flota)
    assert all(v["rentado"] is False for v in flota)

    con_rentados = cliente.get("/catalogos/vehiculos?incluir_rentados=true",
                               headers=h).json()
    assert any(v["placa"] == "XYZ-987-A" for v in con_rentados)


def test_una_placa_de_la_casa_no_se_renta(cliente, sesion, datos):
    """Si la placa ya es de una unidad propia, no hay nada que rentar:
    se asigna por el camino normal."""
    h = sesion("consultor")
    equipo = alta(cliente, h, datos)["equipos"][0]
    r = cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                     json=renta(datos, placa=datos["suburban"]["placa"]),
                     headers=h)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["vehiculo_id"] == datos["suburban"]["id"]


def test_la_misma_renta_capturada_dos_veces_no_duplica_el_auto(cliente, sesion, datos):
    """Tropiezo comun: se captura, no se ve en pantalla y se vuelve a
    capturar. Es el mismo auto, no dos."""
    h = sesion("consultor")
    equipo = alta(cliente, h, datos)["equipos"][0]
    primera = cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                           json=renta(datos), headers=h)
    segunda = cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                           json=renta(datos, color="gris"), headers=h)
    assert segunda.status_code == 201, segunda.text
    assert segunda.json()["vehiculo_id"] == primera.json()["vehiculo_id"]

    asignadas = cliente.get(f"/servicios/equipos/{equipo['id']}/asignaciones",
                            headers=h).json()["vehiculos"]
    assert len(asignadas) == 1
    assert asignadas[0]["color"] == "Gris"


def test_el_auto_rentado_sale_en_el_task_sheet_como_cualquier_unidad(
        cliente, sesion, datos):
    """El ejecutivo tiene que reconocer la unidad en la banqueta. Que sea
    de renta es asunto nuestro y no sale en la hoja."""
    h = sesion("consultor")
    servicio = alta(cliente, h, datos)
    equipo = servicio["equipos"][0]
    jornada = equipo["jornadas"][0]["id"]
    cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                 json=renta(datos), headers=h)

    unidades = cliente.get(f"/servicios/jornadas/{jornada}/asignaciones",
                           headers=h).json()["vehiculos"]
    assert unidades[0]["marca_modelo"] == "Chevrolet Suburban"
    assert unidades[0]["rentado"] is True


def _placas(bloque):
    fichas = []
    for grupo in ("disponibles", "con_alerta", "no_disponibles",
                  "de_otras_ciudades"):
        fichas += bloque.get(grupo) or []
    return [f["placa"] for f in fichas]


def _rentas_pendientes(cliente, headers):
    bandeja = cliente.get("/viaticos/finanzas/bandeja", headers=headers).json()
    return [r for pais in bandeja["paises"] for r in pais["rentas"]]


def test_al_borrar_el_servicio_la_renta_le_queda_a_finanzas(
        cliente, sesion, datos):
    """Borrar el servicio no cancela la renta. El contrato sigue vivo y
    el auto se sigue cobrando: alguien tiene que hablarle a la
    arrendadora, y hasta entonces esto se lo recuerda."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    servicio = alta(cliente, h, datos)
    equipo = servicio["equipos"][0]
    r = cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                     json=renta(datos), headers=h)
    assert r.status_code == 201, r.text
    vehiculo_id = r.json()["vehiculo_id"]

    r = cliente.request("DELETE", f"/servicios/{servicio['id']}", headers=h)
    assert r.status_code == 200, r.text

    pendiente = next(x for x in _rentas_pendientes(cliente, finanzas)
                     if x["vehiculo_id"] == vehiculo_id)
    # El folio sobrevive al servicio: sin el, finanzas no sabe de que
    # renta le estamos hablando.
    assert pendiente["folio"] == servicio["folio"]
    assert pendiente["arrendadora"] == "Renta Ejecutiva del Bajio"
    assert pendiente["telefono"] == "+52 55 1234 5678"

    # Y ya no se ofrece para asignar en ningun lado.
    flota = cliente.get("/catalogos/vehiculos?incluir_rentados=true",
                        headers=h).json()
    assert all(v["placa"] != "XYZ-987-A" for v in flota)

    # Sale de la lista cuando alguien hablo, no cuando el servicio murio.
    r = cliente.post(f"/viaticos/finanzas/rentas/{vehiculo_id}/cancelada",
                     headers=finanzas)
    assert r.status_code == 200, r.text
    assert not _rentas_pendientes(cliente, finanzas)


def test_al_cancelar_el_servicio_la_renta_tambien_le_queda_a_finanzas(
        cliente, sesion, datos):
    """El servicio no va: el auto se regresa a la arrendadora."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    servicio = alta(cliente, h, datos)
    equipo = servicio["equipos"][0]
    cliente.post(f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
                 json=renta(datos), headers=h)

    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     json={"motivo": "El cliente se echo para atras"},
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["autos_rentados_por_devolver"] == ["XYZ-987-A"]

    placas = [x["placa"] for x in _rentas_pendientes(cliente, finanzas)]
    assert "XYZ-987-A" in placas

    vivos = cliente.get("/catalogos/vehiculos?incluir_rentados=true",
                        headers=h).json()
    assert all(v["placa"] != "XYZ-987-A" for v in vivos), "ya no se ofrece"


def test_quitar_la_unidad_rentada_tambien_avisa_a_finanzas(
        cliente, sesion, datos):
    """Se dejo de ocupar a media planeacion: la renta tampoco se cancela
    sola."""
    h = sesion("consultor")
    finanzas = sesion("finanzas")
    servicio = alta(cliente, h, datos)
    equipo = servicio["equipos"][0]
    vehiculo_id = cliente.post(
        f"/servicios/equipos/{equipo['id']}/vehiculo-rentado",
        json=renta(datos), headers=h).json()["vehiculo_id"]

    r = cliente.request(
        "DELETE", f"/servicios/equipos/{equipo['id']}/vehiculos/{vehiculo_id}",
        headers=h)
    assert r.status_code == 200, r.text

    placas = [x["placa"] for x in _rentas_pendientes(cliente, finanzas)]
    assert "XYZ-987-A" in placas

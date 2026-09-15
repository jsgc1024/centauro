"""Lo que no debe poder hacerse.

Cada prueba de aqui nacio de un agujero real que estuvo abierto. La
razon de escribirlas es que un agujero cerrado se vuelve a abrir solo:
alguien agrega un endpoint copiando el de al lado, y el de al lado tenia
`auth.usuario_actual` pelon.

El hilo comun de casi todas: pedir sesion no es pedir permiso. Un
elemento de seguridad freelance tiene sesion, y con ella llegaba al
itinerario de ejecutivos que no protege, a los viaticos de sus
companeros y al tarifario completo de la empresa.
"""
from ayudas import asignar, configurar_origen, crear_servicio, jornada, manana


def _servicio_de_juan(cliente, sesion, datos, dia=1):
    h = sesion("consultor")
    servicio = crear_servicio(cliente, h, datos, [jornada(
        manana(dia), datos["modalidades"]["full_day"]["id"])])
    j = servicio["equipos"][0]["jornadas"][0]
    r = asignar(cliente, h, j["id"],
                persona_id=datos["personal"]["Juan Ramirez"]["id"],
                vehiculo_id=datos["suburban"]["id"])[0]
    assert r.status_code == 200, r.text
    configurar_origen(cliente, h, j["id"])
    return servicio, j


# ================================================== el sembrado

def test_sembrar_catalogos_pide_credenciales(cliente):
    """Estuvo abierto sin contrasena y ademas reescribia el rol y la
    contrasena de todos los usuarios, y devolvia la contrasena en la
    respuesta. Dos peticiones y cualquiera era director general."""
    r = cliente.post("/sistema/sembrar-catalogos")
    assert r.status_code in (401, 403), r.text


def test_sembrar_catalogos_ya_no_toca_los_accesos(cliente, sesion):
    """Sembrar catalogos es cargar paises y tarifas. Reescribir las
    contrasenas de toda la empresa es otra cosa, y no puede ir colgada
    del mismo boton."""
    r = cliente.post("/sistema/sembrar-catalogos", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    assert "accesos" not in r.json()


# ================================================== lo de cada quien

def test_la_agenda_del_ejecutivo_no_es_de_todos(cliente, sesion, datos):
    """Dice a que hora y en que direccion va a estar el protegido. Es el
    dato mas delicado del sistema."""
    _, j = _servicio_de_juan(cliente, sesion, datos)
    r = cliente.post(f"/operacion/jornadas/{j['id']}/agenda/paradas",
                     json={"hora": "14:00:00", "lugar": "Comida",
                           "direccion": "Masaryk 201"},
                     headers=sesion("consultor"))
    assert r.status_code == 201, r.text

    # Juan si va en ese servicio.
    r = cliente.get(f"/operacion/jornadas/{j['id']}/agenda/paradas",
                    headers=sesion("juan"))
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1

    # Luis no.
    r = cliente.get(f"/operacion/jornadas/{j['id']}/agenda/paradas",
                    headers=sesion("luis"))
    assert r.status_code == 403, r.text


def test_nadie_ve_los_viaticos_de_otro(cliente, sesion, datos):
    """Aqui se ve cuanto efectivo trae encima cada quien. Saber quien
    anda en la calle con dinero es justo lo que no debe saberse."""
    _, j = _servicio_de_juan(cliente, sesion, datos)
    r = cliente.post("/viaticos/asignar", headers=sesion("consultor"),
                     json={"jornada_id": j["id"],
                           "persona_id": datos["personal"]["Juan Ramirez"]["id"],
                           "conceptos": [{"concepto": "alimentos",
                                          "monto": "500",
                                          "origen": "tabulador"}]})
    assert r.status_code == 201, r.text
    viatico_id = r.json()["id"]

    assert cliente.get(f"/viaticos/{viatico_id}",
                       headers=sesion("juan")).status_code == 200
    assert cliente.get(f"/viaticos/{viatico_id}",
                       headers=sesion("luis")).status_code == 403


def test_las_fotos_de_la_unidad_solo_las_ve_quien_opera(cliente, sesion, datos):
    """Ensenan placas, el interior y muchas veces el punto de encuentro."""
    servicio, _ = _servicio_de_juan(cliente, sesion, datos)
    assert cliente.get(f"/servicios/{servicio['id']}/revisiones",
                       headers=sesion("juan")).status_code == 200
    assert cliente.get(f"/servicios/{servicio['id']}/revisiones",
                       headers=sesion("luis")).status_code == 403


# ================================================== el catalogo

def test_el_tarifario_no_lo_ve_el_personal_de_campo(cliente, sesion):
    """Lo que se le cobra al cliente y lo que se le paga a cada rol.
    Con la sesion de un elemento se sacaba de corrido."""
    for ruta in ("/catalogos/personal", "/catalogos/comisiones",
                 "/catalogos/tarifas-recurso", "/catalogos/clientes"):
        r = cliente.get(ruta, headers=sesion("juan"))
        assert r.status_code == 403, f"{ruta}: {r.text}"
        assert cliente.get(ruta, headers=sesion("consultor")).status_code == 200


def test_el_catalogo_no_se_corta_en_silencio(cliente, sesion):
    """Estaba en 200 y las pantallas lo piden sin parametro: con mas de
    200 personas, la 201 no existia para nadie y nada lo avisaba."""
    r = cliente.get("/catalogos/personal", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    gente = r.json()
    # Y sale en orden: sin ORDER BY, dos cargas de la misma pantalla
    # podian traer las filas en distinto orden.
    assert [p["nombre"] for p in gente] == sorted(p["nombre"] for p in gente)


# ================================================== el panico

def test_el_panico_se_levanta_a_nombre_de_quien_lo_aprieta(cliente, sesion,
                                                           datos):
    """Aceptaba el nombre del cuerpo: se podia levantar un panico a
    nombre de otro elemento, y un panico mueve equipo de respuesta."""
    _, j = _servicio_de_juan(cliente, sesion, datos, dia=0)
    luis = datos["personal"]["Luis Mendoza"]["id"]

    r = cliente.post("/contingencia/alertas", headers=sesion("juan"),
                     json={"canal": "boton_app", "jornada_id": j["id"],
                           "reporta_persona_id": luis,
                           "lat": "19.43", "lon": "-99.13"})
    assert r.status_code == 201, r.text
    # Lo levanto Juan, diga lo que diga el cuerpo.
    assert r.json()["reporta_persona_id"] == \
        datos["personal"]["Juan Ramirez"]["id"]


def test_nadie_levanta_un_panico_en_un_servicio_ajeno(cliente, sesion, datos):
    """Sirve para saturar a la central, o para distraerla justo durante
    un servicio real."""
    _, j = _servicio_de_juan(cliente, sesion, datos, dia=0)
    r = cliente.post("/contingencia/alertas", headers=sesion("luis"),
                     json={"canal": "boton_app", "jornada_id": j["id"],
                           "lat": "19.43", "lon": "-99.13"})
    assert r.status_code == 403, r.text

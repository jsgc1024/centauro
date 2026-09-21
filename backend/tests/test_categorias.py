"""Las categorias de acceso: un puesto configurable.

El rol dice que es alguien en el organigrama. La categoria dice que puede
tocar en el sistema, que no siempre es lo mismo: hay consultores que no
deciden cuanto dinero se deposita, y gente de central que si.

La regla de fondo, y lo que casi todas estas pruebas comprueban de un
lado o del otro:

    **la categoria quita, la excepcion solo da.**

Quien trae categoria puede exactamente lo que dice su lista --su rol deja
de mandar-- y encima de eso puede llevar permisos sueltos. Al reves no:
no hay excepcion que quite. Si hubiera, su renglon en la lista diria
"Consultor" cuando no lo es, y para saber que puede de verdad habria que
abrir su ficha y acordarse de que existe una excepcion escondida.

El conejillo es Beatriz --consultor-- y cada prueba la devuelve como
estaba: sin categoria y sin permisos sueltos. Si no, la siguiente bateria
que la use se encontraria con una consultora que ya no puede dar de alta
un servicio y el fallo apareceria a diez archivos de aqui.
"""
import uuid

import jwt
import pytest

BEATRIZ = "beatriz.roman@centauro.lat"

# Lo que Beatriz trae por ser consultor, y lo que no. Son dos puertas
# baratas --una lectura y un barrido sin nada pendiente-- elegidas para
# que la prueba mida el permiso y no la operacion.
SUYA = "solicitantes.ver"
AJENA = "viaticos.transferir"


def _hace_lo_suyo(cliente, cabeceras) -> int:
    return cliente.get("/solicitantes", headers=cabeceras).status_code


def _hace_lo_ajeno(cliente, cabeceras) -> int:
    return cliente.post("/viaticos/transferencias/barrido",
                        headers=cabeceras).status_code


def _usuarios(cliente, sesion):
    r = cliente.get("/auth/usuarios", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    return r.json()


def _id_de(cliente, sesion, correo):
    return next(u["usuario_id"] for u in _usuarios(cliente, sesion)
                if u["correo"] == correo)


def _entrar(cliente, correo):
    r = cliente.post("/auth/token",
                     data={"username": correo, "password": "centauro2026"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def beatriz(cliente, sesion):
    """Su id, y la promesa de devolverla a su rol."""
    uid = _id_de(cliente, sesion, BEATRIZ)
    yield uid
    h = sesion("admin")
    cliente.post(f"/auth/usuarios/{uid}/categoria", json={}, headers=h)
    for p in cliente.get(f"/auth/usuarios/{uid}/permisos",
                         headers=h).json()["actividades"]:
        if p["de_donde"] == "permiso de mas":
            cliente.delete(f"/auth/usuarios/{uid}/permisos/{p['actividad']}",
                           headers=h)


@pytest.fixture
def crear(cliente, sesion):
    """Hace una categoria con nombre irrepetible.

    No hay forma de borrar una categoria --a proposito: borrarla dejaria
    a su gente sin puesto de un golpe-- asi que las de las pruebas se
    quedan. Por eso el nombre lleva un sufijo al azar: dos pruebas que
    quisieran llamarle igual chocarian por el nombre unico.
    """
    def hacer(actividades, **extra):
        cuerpo = {"nombre": f"Prueba {uuid.uuid4().hex[:8]}",
                  "actividades": actividades, **extra}
        r = cliente.post("/auth/categorias", json=cuerpo,
                         headers=sesion("admin"))
        assert r.status_code == 201, r.text
        return r.json()

    return hacer


# ====================================================== el catalogo

def test_el_catalogo_dice_para_que_sirve_cada_cosa(cliente, sesion):
    """Las casillas del panel se leen, no se adivinan.

    Quien reparte accesos no lee codigo: si la casilla dijera solo
    `viaticos.transferir`, la unica forma de saber que hace seria
    preguntarle a quien lo escribio.
    """
    r = cliente.get("/auth/actividades", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    catalogo = r.json()
    assert len(catalogo) >= 20
    for entrada in catalogo:
        assert entrada["descripcion"].strip()
        assert entrada["roles"]
    assert {SUYA, AJENA} <= {e["actividad"] for e in catalogo}


def test_solo_administracion_reparte(cliente, sesion, beatriz, crear):
    """Repartir permisos es la unica actividad que puede reescribirse a
    si misma: quien pueda darse permisos se los da todos."""
    h = sesion("consultor")
    assert cliente.get("/auth/actividades", headers=h).status_code == 403
    assert cliente.get("/auth/categorias", headers=h).status_code == 403
    assert cliente.post("/auth/categorias",
                        json={"nombre": "Mia", "actividades": []},
                        headers=h).status_code == 403
    assert cliente.post(f"/auth/usuarios/{beatriz}/permisos",
                        json={"actividad": AJENA},
                        headers=h).status_code == 403
    assert cliente.get(f"/auth/usuarios/{beatriz}/permisos",
                       headers=h).status_code == 403


# ====================================================== crear el puesto

def test_la_categoria_nueva_aparece_con_su_gente_contada(cliente, sesion,
                                                         crear):
    """Cuanta gente la trae puesta es el dato que hace falta antes de
    cambiarle algo: cambiarla es cambiarle el acceso a todos ellos."""
    hecha = crear([SUYA, AJENA], descripcion="Para la prueba")
    assert hecha["actividades"] == sorted([SUYA, AJENA])
    assert hecha["personas"] == 0
    assert hecha["activa"] is True

    lista = cliente.get("/auth/categorias", headers=sesion("admin")).json()
    mia = next(c for c in lista if c["categoria_id"] == hecha["categoria_id"])
    assert mia["descripcion"] == "Para la prueba"


def test_una_actividad_inventada_no_pasa(cliente, sesion):
    """Se guardaria sin protestar y seria una casilla que no protege
    ninguna puerta. El dia que alguien la necesitara, estaria cerrada
    para el y nadie sabria por que."""
    r = cliente.post("/auth/categorias",
                     json={"nombre": f"Mala {uuid.uuid4().hex[:6]}",
                           "actividades": ["viaticos.inventada"]},
                     headers=sesion("admin"))
    assert r.status_code == 400, r.text
    assert "viaticos.inventada" in str(r.json())


def test_no_hay_dos_puestos_con_el_mismo_nombre(cliente, sesion, crear):
    hecha = crear([SUYA])
    r = cliente.post("/auth/categorias",
                     json={"nombre": hecha["nombre"], "actividades": []},
                     headers=sesion("admin"))
    assert r.status_code == 409, r.text


def test_la_categoria_necesita_nombre(cliente, sesion):
    r = cliente.post("/auth/categorias",
                     json={"nombre": "   ", "actividades": []},
                     headers=sesion("admin"))
    assert r.status_code == 400, r.text


def test_una_categoria_que_no_existe(cliente, sesion, beatriz):
    r = cliente.post(f"/auth/usuarios/{beatriz}/categoria",
                     json={"categoria_id": 999999}, headers=sesion("admin"))
    assert r.status_code == 404, r.text


# ============================================ la categoria manda sobre el rol

def test_la_categoria_quita_lo_que_el_rol_traia(cliente, sesion, beatriz,
                                                crear):
    """Lo unico que no se podia hacer antes, y por lo que existe todo
    esto: bajarle el alcance a alguien sin cambiarle el puesto."""
    suyo = {"Authorization": f"Bearer {_entrar(cliente, BEATRIZ)}"}
    assert _hace_lo_suyo(cliente, suyo) == 200

    junior = crear([AJENA])
    r = cliente.post(f"/auth/usuarios/{beatriz}/categoria",
                     json={"categoria_id": junior["categoria_id"],
                           "motivo": "Todavia no decide depositos"},
                     headers=sesion("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["categoria"] == junior["nombre"]

    # Sin cerrarle la sesion: el mismo token de hace un segundo ya no
    # alcanza lo que alcanzaba, porque el permiso se busca en cada clic.
    assert _hace_lo_suyo(cliente, suyo) == 403


def test_la_categoria_da_lo_que_el_rol_no_traia(cliente, sesion, beatriz,
                                                crear):
    suyo = {"Authorization": f"Bearer {_entrar(cliente, BEATRIZ)}"}
    assert _hace_lo_ajeno(cliente, suyo) == 403

    puesto = crear([AJENA])
    cliente.post(f"/auth/usuarios/{beatriz}/categoria",
                 json={"categoria_id": puesto["categoria_id"]},
                 headers=sesion("admin"))
    assert _hace_lo_ajeno(cliente, suyo) == 200


def test_quitarsela_la_devuelve_a_su_rol(cliente, sesion, beatriz, crear):
    """Sin categoria vuelve a los permisos de su rol, que es de donde
    salio. Por eso el dia que esto se aplica no le cambia nada a nadie:
    nadie nace con categoria."""
    suyo = {"Authorization": f"Bearer {_entrar(cliente, BEATRIZ)}"}
    puesto = crear([AJENA])
    h = sesion("admin")
    cliente.post(f"/auth/usuarios/{beatriz}/categoria",
                 json={"categoria_id": puesto["categoria_id"]}, headers=h)
    assert _hace_lo_suyo(cliente, suyo) == 403

    r = cliente.post(f"/auth/usuarios/{beatriz}/categoria", json={},
                     headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["categoria"] is None
    assert _hace_lo_suyo(cliente, suyo) == 200
    assert _hace_lo_ajeno(cliente, suyo) == 403


def test_cambiar_el_puesto_le_cambia_el_acceso_a_su_gente(cliente, sesion,
                                                          beatriz, crear):
    """Se cambia una vez y manda para todos los que lo traen puesto. Es
    lo que hace util la categoria y lo que la hace peligrosa."""
    suyo = {"Authorization": f"Bearer {_entrar(cliente, BEATRIZ)}"}
    puesto = crear([AJENA])
    h = sesion("admin")
    cliente.post(f"/auth/usuarios/{beatriz}/categoria",
                 json={"categoria_id": puesto["categoria_id"]}, headers=h)
    assert _hace_lo_suyo(cliente, suyo) == 403

    r = cliente.patch(f"/auth/categorias/{puesto['categoria_id']}",
                      json={"actividades": [SUYA]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["actividades"] == [SUYA]
    # La lista se reemplaza entera: entra la suya y se va la ajena.
    assert _hace_lo_suyo(cliente, suyo) == 200
    assert _hace_lo_ajeno(cliente, suyo) == 403


def test_apagar_el_puesto_no_le_da_permisos_a_nadie(cliente, sesion, beatriz,
                                                    crear):
    """`activa` solo decide si el puesto se ofrece al asignar.

    Si apagarlo devolviera a su gente a los permisos del rol, apagar una
    categoria daria acceso, que es exactamente lo contrario de lo que uno
    quiere al apagarla.
    """
    suyo = {"Authorization": f"Bearer {_entrar(cliente, BEATRIZ)}"}
    puesto = crear([AJENA])
    h = sesion("admin")
    cliente.post(f"/auth/usuarios/{beatriz}/categoria",
                 json={"categoria_id": puesto["categoria_id"]}, headers=h)

    r = cliente.patch(f"/auth/categorias/{puesto['categoria_id']}",
                      json={"activa": False}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["activa"] is False
    assert _hace_lo_suyo(cliente, suyo) == 403
    assert _hace_lo_ajeno(cliente, suyo) == 200


def test_lo_que_no_se_manda_no_se_toca(cliente, sesion, crear):
    puesto = crear([SUYA], descripcion="La de siempre", horas_sesion=4)
    r = cliente.patch(f"/auth/categorias/{puesto['categoria_id']}",
                      json={"nombre": puesto["nombre"] + " bis"},
                      headers=sesion("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["descripcion"] == "La de siempre"
    assert r.json()["horas_sesion"] == 4
    assert r.json()["actividades"] == [SUYA]


# ============================================== las excepciones solo dan

def test_el_permiso_de_mas_va_encima_de_la_categoria(cliente, sesion,
                                                     beatriz, crear):
    suyo = {"Authorization": f"Bearer {_entrar(cliente, BEATRIZ)}"}
    puesto = crear([AJENA])
    h = sesion("admin")
    cliente.post(f"/auth/usuarios/{beatriz}/categoria",
                 json={"categoria_id": puesto["categoria_id"]}, headers=h)
    assert _hace_lo_suyo(cliente, suyo) == 403

    r = cliente.post(f"/auth/usuarios/{beatriz}/permisos",
                     json={"actividad": SUYA, "motivo": "Cubre vacaciones"},
                     headers=h)
    assert r.status_code == 200, r.text
    assert _hace_lo_suyo(cliente, suyo) == 200


def test_no_se_da_dos_veces_el_mismo_permiso(cliente, sesion, beatriz):
    h = sesion("admin")
    assert cliente.post(f"/auth/usuarios/{beatriz}/permisos",
                        json={"actividad": AJENA},
                        headers=h).status_code == 200
    assert cliente.post(f"/auth/usuarios/{beatriz}/permisos",
                        json={"actividad": AJENA},
                        headers=h).status_code == 409


def test_no_se_regala_un_permiso_inventado(cliente, sesion, beatriz):
    r = cliente.post(f"/auth/usuarios/{beatriz}/permisos",
                     json={"actividad": "dinero.todo"}, headers=sesion("admin"))
    assert r.status_code == 400, r.text


def test_quitar_un_permiso_que_no_se_dio(cliente, sesion, beatriz):
    r = cliente.delete(f"/auth/usuarios/{beatriz}/permisos/{AJENA}",
                       headers=sesion("admin"))
    assert r.status_code == 404, r.text


def test_quitar_la_excepcion_no_quita_lo_que_ya_traia(cliente, sesion,
                                                      beatriz):
    """Quita la excepcion, no el permiso.

    Es lo correcto --nadie pierde nada que no se le hubiera dado ahi--
    pero la pantalla tiene que decirlo, o parecera que el boton no hizo
    nada: Beatriz sigue viendo solicitantes porque su rol se los da.
    """
    suyo = {"Authorization": f"Bearer {_entrar(cliente, BEATRIZ)}"}
    h = sesion("admin")
    cliente.post(f"/auth/usuarios/{beatriz}/permisos",
                 json={"actividad": SUYA}, headers=h)
    r = cliente.delete(f"/auth/usuarios/{beatriz}/permisos/{SUYA}", headers=h)
    assert r.status_code == 200, r.text
    assert _hace_lo_suyo(cliente, suyo) == 200


# ================================================ por que Beatriz no puede

def test_la_ficha_dice_de_donde_le_viene_cada_cosa(cliente, sesion, beatriz,
                                                   crear):
    """La pantalla que contesta la pregunta que llega por telefono.

    Sin `de_donde`, el unico camino para entenderlo es leer el codigo, y
    quien reparte accesos no lee codigo.
    """
    h = sesion("admin")

    # Primero sin categoria: todo lo que puede le viene del rol.
    ficha = cliente.get(f"/auth/usuarios/{beatriz}/permisos",
                        headers=h).json()
    assert ficha["categoria"] is None
    de = {a["actividad"]: a for a in ficha["actividades"]}
    assert de[SUYA]["puede"] is True and de[SUYA]["de_donde"] == "rol"
    assert de[AJENA]["puede"] is False and de[AJENA]["de_donde"] is None

    # Con categoria y una excepcion encima, cada cosa dice de donde sale.
    puesto = crear([AJENA])
    cliente.post(f"/auth/usuarios/{beatriz}/categoria",
                 json={"categoria_id": puesto["categoria_id"]}, headers=h)
    cliente.post(f"/auth/usuarios/{beatriz}/permisos",
                 json={"actividad": SUYA}, headers=h)

    ficha = cliente.get(f"/auth/usuarios/{beatriz}/permisos",
                        headers=h).json()
    assert ficha["categoria"] == puesto["nombre"]
    assert ficha["rol"] == "consultor"
    de = {a["actividad"]: a for a in ficha["actividades"]}
    assert de[AJENA]["de_donde"] == "categoria"
    assert de[SUYA]["de_donde"] == "permiso de mas"


def test_la_lista_de_accesos_no_miente_por_omision(cliente, sesion, beatriz,
                                                   crear):
    """Con categoria puesta, el rol ya no es lo que manda. Si el renglon
    siguiera diciendo solo "Consultor", la lista mentiria justo en la
    pantalla donde se reparte el acceso."""
    puesto = crear([AJENA])
    cliente.post(f"/auth/usuarios/{beatriz}/categoria",
                 json={"categoria_id": puesto["categoria_id"]},
                 headers=sesion("admin"))
    fila = next(u for u in _usuarios(cliente, sesion)
                if u["usuario_id"] == beatriz)
    assert fila["rol"] == "consultor"
    assert fila["categoria"] == puesto["nombre"]


def test_queda_escrito_quien_le_cambio_el_acceso(cliente, sesion, beatriz,
                                                 crear):
    puesto = crear([AJENA])
    h = sesion("admin")
    cliente.post(f"/auth/usuarios/{beatriz}/categoria",
                 json={"categoria_id": puesto["categoria_id"],
                       "motivo": "Mientras aprende"}, headers=h)
    cliente.post(f"/auth/usuarios/{beatriz}/permisos",
                 json={"actividad": SUYA, "motivo": "Cubre vacaciones"},
                 headers=h)

    renglones = cliente.get(f"/auth/usuarios/{beatriz}/historial",
                            headers=h).json()
    acciones = {r["accion"]: r for r in renglones}
    assert acciones["categoria asignada"]["despues"] == puesto["nombre"]
    assert acciones["categoria asignada"]["detalle"] == "Mientras aprende"
    assert acciones["permiso de mas dado"]["despues"] == SUYA
    assert acciones["permiso de mas dado"]["rol_de_quien"] == "admin"


# ============================================== lo que no se puede romper

def test_administracion_pasa_aunque_su_categoria_este_vacia(cliente, sesion):
    """El candado contra encerrarse fuera del propio sistema.

    Sin esto, una categoria mal armada puesta a la persona equivocada
    deja a la empresa sin poder arreglar la configuracion, y el unico
    camino de vuelta es un UPDATE a mano en Postgres.
    """
    h = sesion("admin")
    uid = _id_de(cliente, sesion, "admin@centauro.lat")
    vacia = cliente.post("/auth/categorias",
                         json={"nombre": f"Vacia {uuid.uuid4().hex[:8]}",
                               "actividades": []}, headers=h).json()
    try:
        cliente.post(f"/auth/usuarios/{uid}/categoria",
                     json={"categoria_id": vacia["categoria_id"]}, headers=h)
        assert _hace_lo_suyo(cliente, h) == 200
        assert _hace_lo_ajeno(cliente, h) == 200
    finally:
        cliente.post(f"/auth/usuarios/{uid}/categoria", json={}, headers=h)


def test_la_sesion_dura_lo_que_diga_su_categoria(cliente, sesion, beatriz,
                                                 crear):
    """Doce horas parejas para todos no sirven: quien esta en la calle
    vuelve a entrar a media jornada, y una computadora de oficina que se
    queda prendida sigue abierta toda la tarde."""
    corta = crear([SUYA], horas_sesion=2)
    cliente.post(f"/auth/usuarios/{beatriz}/categoria",
                 json={"categoria_id": corta["categoria_id"]},
                 headers=sesion("admin"))

    carga = jwt.decode(_entrar(cliente, BEATRIZ), options={"verify_signature": False})
    duro = carga["exp"] - carga["iat"]
    assert 2 * 3600 - 5 <= duro <= 2 * 3600 + 5

    # Y sin categoria, las doce de siempre.
    cliente.post(f"/auth/usuarios/{beatriz}/categoria", json={},
                 headers=sesion("admin"))
    carga = jwt.decode(_entrar(cliente, BEATRIZ), options={"verify_signature": False})
    assert carga["exp"] - carga["iat"] >= 11 * 3600

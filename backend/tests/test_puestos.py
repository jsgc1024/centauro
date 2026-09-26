"""Los puestos de verdad (seccion 73).

Decision de Salvador, 26 de septiembre: cada quien entra con el puesto
que tiene en Odoo y ve solo lo de su trabajo. Un puesto dice con que rol
entra quien lo trae, que pantallas le salen en el menu y que puede hacer
en ellas; los once de la propuesta se crean con un boton.

Lo que estas pruebas cuidan, de un lado y del otro:

  * que los puestos de la propuesta no junten lo que no puede vivir en
    la misma mano, y que cada pantalla que ofrecen tenga con que llenarse;
  * que cada puesto haga lo suyo y nada mas: el consultor JR prepara y no
    decide el dinero, el monitorista no corrige, Nomina arma el corte y no
    lo paga, el jefe de finanzas lo paga y no lo arma;
  * que quien no tiene puesto siga exactamente como antes.

Los conejillos son las cuentas sembradas; cada prueba las devuelve como
estaban --sin puesto y con su rol--. Los puestos no se borran nunca, asi
que los de la propuesta se quedan creados para el resto de la bateria.
"""
import os
import re
import uuid

import pytest

from app import auth, permisos, puestos_base

MENU_JS = os.path.join(os.path.dirname(__file__), "..", "app", "web", "menu.js")


def _necesita_del_menu() -> dict:
    """clave -> actividades que llenan esa pantalla, leidas de menu.js:
    la misma lista que usa la consola, no una copia."""
    fuente = open(MENU_JS, encoding="utf-8").read()
    salida = {}
    for clave, necesita in re.findall(
            r'clave: "(\w+)", necesita: (null|"[\w.]+"|\[[^\]]*\])', fuente):
        salida[clave] = (None if necesita == "null"
                         else re.findall(r'"([\w.]+)"', necesita))
    return salida


def _usuarios(cliente, sesion):
    r = cliente.get("/auth/usuarios", headers=sesion("admin"))
    assert r.status_code == 200, r.text
    return r.json()


def _usuario(cliente, sesion, correo):
    return next(u for u in _usuarios(cliente, sesion) if u["correo"] == correo)


def _entrar(cliente, correo):
    r = cliente.post("/auth/token",
                     data={"username": correo, "password": "centauro2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _puestos(cliente, sesion):
    """Los de la propuesta, creados si faltan, por nombre."""
    h = sesion("admin")
    r = cliente.post("/auth/categorias/base", headers=h)
    assert r.status_code == 200, r.text
    return {p["nombre"]: p for p in cliente.get("/auth/categorias",
                                                headers=h).json()}


@pytest.fixture
def ponerle(cliente, sesion):
    """ponerle(correo, puesto) y, al terminar, se lo quita y le devuelve
    el rol con el que entraba."""
    h = sesion("admin")
    tocados = []

    def poner(correo, nombre):
        u = _usuario(cliente, sesion, correo)
        tocados.append((u["usuario_id"], u["rol"]))
        puesto = _puestos(cliente, sesion)[nombre]
        r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/categoria",
                         json={"categoria_id": puesto["categoria_id"]},
                         headers=h)
        assert r.status_code == 200, r.text
        return _entrar(cliente, correo)

    yield poner
    for uid, rol in tocados:
        cliente.post(f"/auth/usuarios/{uid}/categoria", json={}, headers=h)
        ahora = next(u for u in _usuarios(cliente, sesion)
                     if u["usuario_id"] == uid)
        if ahora["rol"] != rol:
            r = cliente.post(f"/auth/usuarios/{uid}/rol",
                             json={"rol": rol, "motivo": "fin de prueba"},
                             headers=h)
            assert r.status_code == 200, r.text


# ============================================ los puestos de la propuesta

def test_las_pantallas_del_servidor_son_las_del_menu():
    """El servidor revisa las pantallas que se guardan contra su lista, y
    la consola pinta el menu con la suya. Si se separan, una casilla del
    formulario no guardaria nada. Odoo no esta en ninguna de las dos para
    puestos: su puerta pide administracion por rol."""
    menu = _necesita_del_menu()
    assert "odoo" in menu and menu["odoo"] is None
    para_puestos = {c for c, n in menu.items() if n}
    assert para_puestos == set(permisos.PANTALLAS)


@pytest.mark.parametrize("puesto", puestos_base.PUESTOS,
                         ids=[p["nombre"] for p in puestos_base.PUESTOS])
def test_cada_puesto_de_la_propuesta_cuadra(puesto):
    actividades = puesto["actividades"]
    # Todas existen.
    assert actividades <= set(permisos.ACTIVIDADES), \
        actividades - set(permisos.ACTIVIDADES)
    # Nada de lo que no puede vivir en la misma mano.
    for a, b in permisos.INCOMPATIBLES:
        assert not ({a, b} <= actividades), (puesto["nombre"], a, b)
    # Entra con un rol de puesto.
    assert puesto["rol"] not in (auth.m.Rol.ADMIN, auth.m.Rol.DIRECTOR_GENERAL,
                                 auth.m.Rol.PERSONAL_SEGURIDAD)
    # Cada pantalla que ofrece tiene con que llenarse.
    menu = _necesita_del_menu()
    for pantalla in puesto["pantallas"]:
        assert pantalla in permisos.PANTALLAS, pantalla
        assert set(menu[pantalla]) & actividades, \
            f"{puesto['nombre']}: {pantalla} abriria vacia"


def test_los_de_la_propuesta_se_crean_una_sola_vez(cliente, sesion):
    h = sesion("admin")
    cliente.post("/auth/categorias/base", headers=h)
    r = cliente.get("/auth/categorias/base", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["faltan"] == []
    # Dos veces no duplica ni pisa: lo que ya esta se queda como esta.
    otra = cliente.post("/auth/categorias/base", headers=h).json()
    assert otra["creados"] == []
    assert len(otra["ya_estaban"]) == len(puestos_base.PUESTOS)

    todos = {p["nombre"]: p for p in cliente.get("/auth/categorias",
                                                 headers=h).json()}
    mon = todos["Monitorista"]
    assert mon["rol"] == "central"
    assert mon["area"] == "Operaciones CI"
    assert "central" in mon["pantallas"] and "codigo" in mon["pantallas"]
    assert "Monitorista" in mon["puestos_odoo"]
    # Y los dos que entran con su rol, para que la lista este completa.
    por_rol = {p["rol"] for p in r.json()["por_rol"]}
    assert por_rol == {"director_general", "admin"}


def test_crear_los_de_la_propuesta_es_de_quien_da_accesos(cliente, sesion):
    assert cliente.post("/auth/categorias/base",
                        headers=sesion("consultor")).status_code == 403
    assert cliente.get("/auth/categorias/base",
                       headers=sesion("central")).status_code == 403


# ============================================ cada puesto, lo suyo

def test_el_consultor_jr_prepara_pero_no_decide_el_dinero(cliente, sesion,
                                                          ponerle):
    h = ponerle("beatriz.roman@centauro.lat", "Consultor JR")
    yo = cliente.get("/auth/yo", headers=h).json()
    assert yo["puesto"] == "Consultor JR"
    assert yo["rol"] == "consultor"
    assert "servicios" in yo["pantallas"]
    assert "viaticos.asignar" not in yo["actividades"]
    assert "cierre.cerrar" not in yo["actividades"]
    assert {"servicios.alta", "cierre.cotizar"} <= set(yo["actividades"])

    # El dinero no: y el aviso dice su puesto y quien si lo hace.
    r = cliente.post("/viaticos/asignar", json={}, headers=h)
    assert r.status_code == 403, r.text
    que_hacer = r.json()["detail"]["que_hacer"]
    assert "Consultor JR" in que_hacer
    assert "Consultor de seguridad" in que_hacer

    # Cotizar si: la puerta de la cotizacion ya no pide la de cerrar.
    r = cliente.post("/cotizaciones", json={"servicio_id": 999999},
                     headers=h)
    assert r.status_code != 403, r.text


def test_el_monitorista_atiende_pero_no_corrige(cliente, sesion, ponerle):
    h = ponerle("central@centauro.lat", "Monitorista")
    yo = cliente.get("/auth/yo", headers=h).json()
    assert yo["puesto"] == "Monitorista"
    assert "operacion.corregir" not in yo["actividades"]
    assert {"operacion.ver", "codigo.dictar"} <= set(yo["actividades"])
    assert "equipo" not in yo["pantallas"]

    assert cliente.post("/operacion/jornadas/999999/reabrir",
                        json={"motivo": "prueba de puesto"},
                        headers=h).status_code == 403
    assert cliente.get("/central/tablero", headers=h).status_code == 200


def test_nomina_arma_el_corte_y_no_lo_paga(cliente, sesion, ponerle):
    """A quien entraba como finanzas --que de fabrica arma Y paga-- se le
    puede poner Nomina, que justo le quita pagar."""
    h = ponerle("finanzas@centauro.lat", "Nómina")
    assert cliente.post("/nomina/999999/pagar", headers=h).status_code == 403
    assert cliente.post("/nomina/calcular", json={},
                        headers=h).status_code == 422
    # Y lo que se paga por dia lo fija direccion de operaciones.
    assert cliente.put("/nomina/tabulador", json={},
                       headers=h).status_code == 403
    yo = cliente.get("/auth/yo", headers=h).json()
    assert yo["pantallas"] == ["bonos", "nomina"]


def test_el_jefe_de_finanzas_paga_y_no_arma(cliente, sesion, ponerle):
    h = ponerle("finanzas@centauro.lat", "Jefe de finanzas")
    assert cliente.post("/nomina/calcular", json={},
                        headers=h).status_code == 403
    assert cliente.post("/nomina/999999/pagar",
                        headers=h).status_code == 404


def test_direccion_de_operaciones_ya_no_marca_pagada_la_nomina(cliente,
                                                               sesion):
    """Decision del 26 de septiembre: la arma y la recalcula; la marca
    pagada finanzas. Por rol, sin puesto."""
    h = sesion("diroperaciones")
    assert cliente.post("/nomina/999999/pagar", headers=h).status_code == 403
    assert cliente.post("/nomina/calcular", json={},
                        headers=h).status_code == 422


def test_capacitacion_consulta_y_no_da_accesos(cliente, sesion, ponerle):
    antes = cliente.get("/auth/usuarios", headers=sesion("rrhh"))
    assert antes.status_code == 200, antes.text
    h = ponerle("rrhh@centauro.lat", "Capacitación")
    assert cliente.get("/auth/usuarios", headers=h).status_code == 403
    yo = cliente.get("/auth/yo", headers=h).json()
    assert yo["pantallas"] == ["equipo", "bonos"]


# ============================================ el rol lo pone el puesto

def test_el_puesto_le_pone_su_rol_y_el_rol_ya_no_se_cambia_a_mano(
        cliente, sesion, ponerle):
    ponerle("beatriz.roman@centauro.lat", "Monitorista")
    u = _usuario(cliente, sesion, "beatriz.roman@centauro.lat")
    assert u["rol"] == "central"
    assert u["rol_por_puesto"] is True

    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/rol",
                     json={"rol": "finanzas"}, headers=sesion("admin"))
    assert r.status_code == 409, r.text
    assert "Monitorista" in str(r.json())


@pytest.mark.parametrize("rol", ["admin", "director_general",
                                 "personal_seguridad"])
def test_un_puesto_no_entra_como_direccion_general_ni_administracion(
        cliente, sesion, rol):
    r = cliente.post("/auth/categorias",
                     json={"nombre": f"Prueba {uuid.uuid4().hex[:8]}",
                           "actividades": ["panorama.ver"], "rol": rol},
                     headers=sesion("admin"))
    assert r.status_code == 400, r.text


def test_las_pantallas_se_guardan_en_el_orden_del_menu(cliente, sesion):
    h = sesion("admin")
    r = cliente.post("/auth/categorias",
                     json={"nombre": f"Prueba {uuid.uuid4().hex[:8]}",
                           "actividades": ["panorama.ver", "nomina.ver"],
                           "rol": "finanzas",
                           "pantallas": ["nomina", "panorama"]},
                     headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["pantallas"] == ["panorama", "nomina"]


@pytest.mark.parametrize("pantalla", ["odoo", "inventada"])
def test_una_pantalla_que_ningun_puesto_abre_no_se_guarda(cliente, sesion,
                                                          pantalla):
    """Seria una casilla que no hace nada: la que el menu no conoce, y
    Odoo, cuya puerta pide administracion por rol. Se dice cual."""
    r = cliente.post("/auth/categorias",
                     json={"nombre": f"Prueba {uuid.uuid4().hex[:8]}",
                           "actividades": ["panorama.ver"],
                           "pantallas": ["panorama", pantalla]},
                     headers=sesion("admin"))
    assert r.status_code == 400, r.text
    assert pantalla in str(r.json())


def test_un_puesto_no_se_renombra_como_otro(cliente, sesion):
    h = sesion("admin")
    hechos = []
    for _ in range(2):
        r = cliente.post("/auth/categorias",
                         json={"nombre": f"Prueba {uuid.uuid4().hex[:8]}",
                               "actividades": ["panorama.ver"]}, headers=h)
        assert r.status_code == 201, r.text
        hechos.append(r.json())
    r = cliente.patch(f"/auth/categorias/{hechos[1]['categoria_id']}",
                      json={"nombre": hechos[0]["nombre"]}, headers=h)
    assert r.status_code == 409, r.text


@pytest.mark.parametrize("par", [("viaticos.asignar", "viaticos.transferir"),
                                 ("cierre.cerrar", "cierre.facturar"),
                                 ("nomina.calcular", "nomina.pagar")])
def test_los_candados_nuevos(cliente, sesion, par):
    """Quien decide el deposito no lo hace; quien da el visto bueno no
    factura; quien arma la nomina no la paga."""
    r = cliente.post("/auth/categorias",
                     json={"nombre": f"Prueba {uuid.uuid4().hex[:8]}",
                           "actividades": list(par)},
                     headers=sesion("admin"))
    assert r.status_code == 409, r.text


# ============================================ sin puesto, como siempre

def test_quien_no_tiene_puesto_sigue_con_lo_de_su_rol(cliente, sesion):
    yo = cliente.get("/auth/yo", headers=sesion("consultor")).json()
    assert yo["puesto"] is None
    assert yo["pantallas"] is None
    assert set(yo["actividades"]) == permisos.actividades_por_rol(
        auth.m.Rol.CONSULTOR, auth.HEREDA)

    dg = cliente.get("/auth/yo", headers=sesion("dirgeneral")).json()
    assert set(dg["actividades"]) == permisos.actividades_por_rol(
        auth.m.Rol.DIRECTOR_GENERAL, auth.HEREDA)
    adm = cliente.get("/auth/yo", headers=sesion("admin")).json()
    assert set(adm["actividades"]) == set(permisos.ACTIVIDADES)


def test_recursos_humanos_lee_los_catalogos_de_sus_pantallas(cliente, sesion):
    """Desempeno y Personal leen de /catalogos los paises, los perfiles y
    la plantilla. Recursos Humanos abre las dos y se habia quedado fuera
    de la lectura generica: su Desempeno abria con "Tu rol no tiene
    permiso". Lo encontro la prueba de humo de los puestos."""
    h = sesion("rrhh")
    for ruta in ("/catalogos/paises", "/catalogos/perfiles",
                 "/catalogos/modalidades", "/catalogos/categorias-vehiculo",
                 "/catalogos/personal", "/catalogos/clientes"):
        assert cliente.get(ruta, headers=h).status_code == 200, ruta
    # El personal de campo sigue sin leerlos: lo suyo va por /campo.
    assert cliente.get("/catalogos/personal",
                       headers=sesion("juan")).status_code == 403

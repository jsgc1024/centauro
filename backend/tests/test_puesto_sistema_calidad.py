"""El puesto de administracion del sistema y calidad (seccion 85).

Decision de Salvador, 27 de septiembre: la administracion del sistema va
junto con calidad, y es el puesto de Aridiai Morales. Administra --los
accesos junto con recursos humanos, las lecturas de Odoo y los
catalogos-- y mide la calidad del servicio; consulta la operacion sin
operarla, no mueve dinero y no clasifica nada. Entra con un rol propio,
«Sistema y calidad», y no con la llave maestra.

Lo que decide dinero en los catalogos --el tabulador de viaticos, las
horas de cada modalidad, las tarifas de freelance-- lo fija direccion de
operaciones.

Las cuentas, los puestos y los catalogos no se vacian entre pruebas: cada
prueba los deja como estaban.
"""
import pytest
from sqlalchemy import text

from app import permisos, puestos_base

PUESTO = "Administración del sistema y calidad"
ARIDIAI = "central2@centauro.lat"     # la cuenta sembrada que hace de ella


@pytest.fixture(autouse=True)
def como_estaba(base_de_pruebas):
    with base_de_pruebas.begin() as con:
        cuentas = con.execute(text(
            "SELECT id, rol, categoria_id, activo FROM usuario")).all()
        extras = [f[0] for f in con.execute(text("SELECT id FROM permiso_extra"))]
    yield
    with base_de_pruebas.begin() as con:
        con.execute(text("DELETE FROM permiso_extra WHERE NOT (id = ANY(:ids))"),
                    {"ids": extras})
        for u in cuentas:
            con.execute(text("UPDATE usuario SET rol = :rol, categoria_id = :c, "
                             "activo = :a WHERE id = :id"),
                        {"rol": u.rol, "c": u.categoria_id, "a": u.activo, "id": u.id})
        con.execute(text("DELETE FROM dia_festivo WHERE nombre LIKE 'Prueba85%'"))


def _entrar(cliente, correo):
    r = cliente.post("/auth/token",
                     data={"username": correo, "password": "centauro2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _puestos(cliente, sesion):
    h = sesion("dirgeneral")
    assert cliente.post("/auth/categorias/base", headers=h).status_code == 200
    return {p["nombre"]: p for p in cliente.get("/auth/categorias", headers=h).json()}


def _usuario(cliente, sesion, correo):
    return next(u for u in cliente.get("/auth/usuarios",
                                       headers=sesion("dirgeneral")).json()
                if u["correo"] == correo)


@pytest.fixture
def aridiai(cliente, sesion):
    """La cuenta con el puesto, puesto por direccion general."""
    puesto = _puestos(cliente, sesion)[PUESTO]
    u = _usuario(cliente, sesion, ARIDIAI)
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/categoria",
                     json={"categoria_id": puesto["categoria_id"]},
                     headers=sesion("dirgeneral"))
    assert r.status_code == 200, r.text
    return _entrar(cliente, ARIDIAI)


# ====================================================== el puesto

def test_el_puesto_esta_en_la_propuesta_y_reparte_accesos():
    p = next(x for x in puestos_base.PUESTOS if x["nombre"] == PUESTO)
    assert p["rol"] == permisos.m.Rol.SISTEMA_CALIDAD
    assert "odoo" in p["pantallas"] and "accesos" in p["pantallas"]
    # No se le sugiere a nadie desde Odoo: se da a mano (seccion 83).
    assert not p["puestos_odoo"]
    # Administra y consulta; no mueve dinero, no opera, no juzga.
    assert {"accesos.dar", "odoo.administrar", "catalogos.editar",
            "calidad.ver", "bitacora.ver"} <= p["actividades"]
    nada_de_esto = {
        "viaticos.asignar", "viaticos.transferir", "viaticos.cerrar",
        "cierre.cerrar", "cierre.facturar", "cierre.rentabilidad",
        "cierre.historial", "nomina.calcular", "nomina.pagar",
        "nomina.tabulador", "bonos.autorizar", "bonos.pagar",
        "bonos.incidencia", "bonos.visto_bueno", "comisiones.pagar",
        "servicios.alta", "asignaciones.mover", "operacion.corregir",
        "operacion.atender", "contingencia.atender", "encuestas.clasificar",
        "catalogos.dinero", "archivo.ver", "codigo.dictar"}
    assert not (nada_de_esto & p["actividades"]), nada_de_esto & p["actividades"]


def test_lo_crea_solo_direccion_general(cliente, sesion, base_de_pruebas):
    """Reparte accesos: el boton de los puestos de la propuesta no se lo
    crea a recursos humanos, y le dice quien lo crea."""
    with base_de_pruebas.begin() as con:
        cat = con.execute(text("SELECT id FROM categoria_acceso WHERE nombre = :n"),
                          {"n": PUESTO}).first()
        if cat:
            con.execute(text("UPDATE usuario SET categoria_id = NULL "
                             "WHERE categoria_id = :c"), {"c": cat.id})
            con.execute(text("DELETE FROM actividad_de_categoria "
                             "WHERE categoria_id = :c"), {"c": cat.id})
            con.execute(text("DELETE FROM categoria_acceso WHERE id = :c"),
                        {"c": cat.id})
    rh = sesion("rrhh")
    base = cliente.get("/auth/categorias/base", headers=rh).json()
    assert PUESTO in base["faltan"] and PUESTO in base["de_direccion"]
    r = cliente.post("/auth/categorias/base", headers=rh)
    assert r.status_code == 200, r.text
    assert PUESTO not in r.json()["creados"] and PUESTO in r.json()["de_direccion"]
    r = cliente.post("/auth/categorias/base", headers=sesion("dirgeneral"))
    assert PUESTO in r.json()["creados"], r.text
    puesto = _puestos(cliente, sesion)[PUESTO]
    assert puesto["reparte"] is True and puesto["rol"] == "sistema_calidad"


def test_recursos_humanos_no_se_lo_da_a_nadie(cliente, sesion):
    puesto = _puestos(cliente, sesion)[PUESTO]
    u = _usuario(cliente, sesion, ARIDIAI)
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/categoria",
                     json={"categoria_id": puesto["categoria_id"]},
                     headers=sesion("rrhh"))
    assert r.status_code == 403, r.text


def test_entra_con_su_rol_su_menu_y_lo_suyo(cliente, sesion, aridiai):
    yo = cliente.get("/auth/yo", headers=aridiai).json()
    assert yo["rol"] == "sistema_calidad"
    assert yo["puesto"] == PUESTO
    assert yo["es_direccion"] is False
    # Catalogos llego con la seccion 86, Calidad con la 89, el manual del
    # sistema con la 90, Cotizaciones --para consultarla-- con la 114 y el
    # Mapa de riesgo --sus clientes y sus tipos de evento-- con la 132. Van
    # en el orden de `permisos.PANTALLAS`: asi se guardan al crear el puesto.
    assert yo["pantallas"] == ["panorama", "cotizaciones", "servicios",
                               "implantados", "equipo", "unidades", "bonos",
                               "encuestas", "calidad", "accesos", "odoo",
                               "catalogos", "manual", "riesgo"]
    assert "cotizaciones.ver" in yo["actividades"]
    assert "cotizaciones.armar" not in yo["actividades"]
    assert "manual.ver" in yo["actividades"]
    assert "odoo.administrar" in yo["actividades"]
    assert "cierre.facturar" not in yo["actividades"]


def test_si_se_le_dio_la_llave_maestra_por_error_se_le_corrige(
        cliente, sesion, base_de_pruebas):
    """Salvador, 27 sep (seccion 88): a Aridiai se le dio el rol de
    administracion --confundido con el nombre de su puesto-- y al ponerle
    el puesto no lo dejaba guardar. Era la unica con ese rol, y el candado
    de la llave maestra no contaba a direccion general, que la tiene."""
    dg = sesion("dirgeneral")
    u = _usuario(cliente, sesion, ARIDIAI)
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/rol",
                     json={"rol": "admin"}, headers=dg)
    assert r.status_code == 200, r.text
    # Y es la unica: las demas cuentas de administracion no estan
    # (`como_estaba` las vuelve a abrir).
    with base_de_pruebas.begin() as con:
        con.execute(text("UPDATE usuario SET activo = false "
                         "WHERE rol::text = 'ADMIN' AND correo <> :ella"),
                    {"ella": ARIDIAI})
        solas = con.execute(text("SELECT correo FROM usuario "
                                 "WHERE activo AND rol::text = 'ADMIN'")).scalars().all()
    assert solas == [ARIDIAI]
    puesto = _puestos(cliente, sesion)[PUESTO]
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/categoria",
                     json={"categoria_id": puesto["categoria_id"]}, headers=dg)
    assert r.status_code == 200, r.text
    ella = _usuario(cliente, sesion, ARIDIAI)
    assert ella["rol"] == "sistema_calidad"
    assert ella["categoria"] == PUESTO


# ====================================================== lo que abre

@pytest.mark.parametrize("ruta", [
    "/panorama",
    "/encuestas/resumen",
    "/encuestas/por-clasificar",
    "/auth/usuarios",
    "/auth/categorias",
    "/auth/oficina",
    "/odoo/estado",
    "/catalogos/paises",
    "/catalogos/hoteles",
    "/catalogos/dias-festivos",
    "/catalogos/tabulador-viaticos",
])
def test_abre_lo_de_su_menu(cliente, aridiai, ruta):
    r = cliente.get(ruta, headers=aridiai)
    assert r.status_code == 200, (ruta, r.text[:300])


def test_odoo_ya_no_es_solo_de_la_llave_maestra(cliente, sesion, aridiai):
    assert cliente.get("/odoo/estado", headers=aridiai).status_code == 200
    assert cliente.get("/odoo/estado", headers=sesion("dirgeneral")).status_code == 200
    assert cliente.get("/odoo/estado", headers=sesion("consultor")).status_code == 403
    assert cliente.get("/odoo/estado", headers=sesion("rrhh")).status_code == 403


# ====================================================== lo que no hace

@pytest.mark.parametrize("metodo, ruta", [
    ("post", "/viaticos/transferencias/1/confirmar"),
    ("post", "/cierre/1/facturar"),
    ("put", "/tarifarios/tipo-de-cambio"),
    ("put", "/nomina/tabulador"),
    ("post", "/evaluaciones/1/autorizar"),
    ("post", "/encuestas/1/clasificar"),
    ("post", "/catalogos/tabulador-viaticos"),
    ("post", "/catalogos/modalidades"),
    ("post", "/catalogos/tarifas-freelance"),
])
def test_no_mueve_dinero_ni_juzga(cliente, aridiai, metodo, ruta):
    """La puerta contesta antes de mirar el cuerpo: con uno vacio, 403."""
    r = getattr(cliente, metodo)(ruta, json={}, headers=aridiai)
    assert r.status_code == 403, (ruta, r.status_code, r.text[:200])


# ====================================================== los catalogos

def test_los_catalogos_que_no_son_dinero_los_lleva_ella(cliente, sesion, aridiai):
    mx = next(p for p in cliente.get("/catalogos/paises", headers=aridiai).json()
              if p["codigo"] == "MX")
    r = cliente.post("/catalogos/dias-festivos", json={
        "pais_id": mx["id"], "fecha": "2031-12-24", "nombre": "Prueba85 Nochebuena",
        "factor_comision": 2}, headers=aridiai)
    assert r.status_code in (200, 201), r.text
    # Recursos humanos no.
    r = cliente.post("/catalogos/dias-festivos", json={
        "pais_id": mx["id"], "fecha": "2031-12-31", "nombre": "Prueba85 Fin",
        "factor_comision": 2}, headers=sesion("rrhh"))
    assert r.status_code == 403, r.text


def test_lo_que_decide_dinero_lo_fija_direccion_de_operaciones(cliente, sesion, aridiai):
    do = sesion("diroperaciones")
    fila = cliente.get("/catalogos/modalidades", headers=do).json()[0]
    cambios = {k: v for k, v in fila.items() if k not in ("id", "activo")}
    r = cliente.patch(f"/catalogos/modalidades/{fila['id']}", json=cambios, headers=do)
    assert r.status_code == 200, r.text
    r = cliente.patch(f"/catalogos/modalidades/{fila['id']}", json=cambios,
                      headers=aridiai)
    assert r.status_code == 403, r.text
    # Y Calidad la ve direccion de operaciones.
    yo = cliente.get("/auth/yo", headers=do).json()
    assert {"calidad.ver", "catalogos.dinero"} <= set(yo["actividades"])
    assert "catalogos.editar" not in yo["actividades"]


def test_la_llave_maestra_y_direccion_general_siguen_pudiendo(cliente, sesion):
    for quien in ("admin", "dirgeneral"):
        yo = cliente.get("/auth/yo", headers=sesion(quien)).json()
        assert {"odoo.administrar", "catalogos.editar", "catalogos.dinero",
                "calidad.ver", "bitacora.ver"} <= set(yo["actividades"]), quien

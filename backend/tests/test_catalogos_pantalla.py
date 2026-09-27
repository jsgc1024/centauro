"""La pantalla de Catalogos y la bitacora de administracion (seccion 86).

Tercer paso de lo aprobado el 27 de septiembre: los catalogos que no
deciden dinero los lleva sistema y calidad, los que si los fija direccion
de operaciones, y la bitacora de administracion --accesos, puestos,
catalogos y tipo de cambio-- se lee junta, con filtros y en Excel.

La bitacora se vacia entre pruebas; los catalogos, las cuentas y los
puestos no: cada prueba deja como estaban los que toca.
"""
import pytest
from sqlalchemy import text

from app import excel, permisos, puestos_base

PUESTO = "Administración del sistema y calidad"
ARIDIAI = "central2@centauro.lat"     # la cuenta sembrada que hace de ella
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


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
        con.execute(text("DELETE FROM dia_festivo WHERE nombre LIKE 'Prueba86%'"))
        con.execute(text("DELETE FROM hotel WHERE nombre LIKE 'Prueba86%'"))
        con.execute(text("DELETE FROM foto_categoria WHERE color = 'prueba86'"))


def _entrar(cliente, correo):
    r = cliente.post("/auth/token",
                     data={"username": correo, "password": "centauro2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def aridiai(cliente, sesion):
    """La cuenta con el puesto de sistema y calidad, dado por direccion
    general."""
    h = sesion("dirgeneral")
    assert cliente.post("/auth/categorias/base", headers=h).status_code == 200
    puesto = next(p for p in cliente.get("/auth/categorias", headers=h).json()
                  if p["nombre"] == PUESTO)
    u = next(x for x in cliente.get("/auth/usuarios", headers=h).json()
             if x["correo"] == ARIDIAI)
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/categoria",
                     json={"categoria_id": puesto["categoria_id"]}, headers=h)
    assert r.status_code == 200, r.text
    return _entrar(cliente, ARIDIAI)


def _mx(cliente, h):
    return next(p for p in cliente.get("/catalogos/paises", headers=h).json()
                if p["codigo"] == "MX")


def _festivo(cliente, h, nombre, fecha="2031-12-24"):
    r = cliente.post("/catalogos/dias-festivos", json={
        "pais_id": _mx(cliente, h)["id"], "fecha": fecha, "nombre": nombre,
        "factor_comision": 2}, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


# ====================================================== la pantalla

def test_la_pantalla_esta_en_el_menu_de_quien_lleva_catalogos():
    assert "catalogos" in permisos.PANTALLAS
    por_nombre = {p["nombre"]: p for p in puestos_base.PUESTOS}
    assert "catalogos" in por_nombre[PUESTO]["pantallas"]
    # Direccion de operaciones fija lo que decide dinero.
    assert "catalogos" in por_nombre["Dirección de operaciones"]["pantallas"]
    # Los hospitales y los hoteles se buscan en Google.
    assert "mapas.buscar" in por_nombre[PUESTO]["actividades"]


def test_aridiai_la_abre(cliente, aridiai):
    yo = cliente.get("/auth/yo", headers=aridiai).json()
    assert "catalogos" in yo["pantallas"]
    assert {"catalogos.editar", "bitacora.ver", "mapas.buscar"} <= set(yo["actividades"])
    assert "catalogos.dinero" not in yo["actividades"]


# ====================================================== la bitacora

def test_la_bitacora_cuenta_lo_que_paso(cliente, sesion, aridiai):
    _festivo(cliente, aridiai, "Prueba86 Nochebuena")
    yo = cliente.get("/auth/yo", headers=aridiai).json()

    r = cliente.get("/bitacora-admin?que=catalogos", headers=aridiai)
    assert r.status_code == 200, r.text
    fila = r.json()["filas"][0]
    assert fila["donde"] == "Días festivos"
    assert fila["que"] == "Agregó «Prueba86 Nochebuena»"
    assert fila["quien"] == yo["nombre"]
    assert fila["grupo"] == "catalogos"

    # En el idioma de quien la lee.
    fila = cliente.get("/bitacora-admin?que=catalogos&idioma=en",
                       headers=aridiai).json()["filas"][0]
    assert fila["donde"] == "Public holidays"
    assert fila["que"] == "Added “Prueba86 Nochebuena”"


def test_un_cambio_se_lee_con_nombres_y_no_con_numeros(cliente, sesion, aridiai):
    mx = _mx(cliente, aridiai)
    ciudades = [c for c in cliente.get("/catalogos/plazas?todas=true",
                                       headers=aridiai).json()
                if c["pais_id"] == mx["id"]]
    antes, despues = ciudades[0], ciudades[1]
    r = cliente.post("/catalogos/hoteles", json={
        "pais_id": mx["id"], "nombre": "Prueba86 Hotel", "plaza_id": antes["id"]},
        headers=aridiai)
    assert r.status_code in (200, 201), r.text
    hotel = r.json()
    cuerpo = {k: v for k, v in hotel.items() if k not in ("id", "activo")}
    cuerpo["plaza_id"] = despues["id"]
    r = cliente.patch(f"/catalogos/hoteles/{hotel['id']}", json=cuerpo, headers=aridiai)
    assert r.status_code == 200, r.text

    fila = cliente.get("/bitacora-admin?que=catalogos",
                       headers=aridiai).json()["filas"][0]
    assert fila["donde"] == "Hoteles"
    assert fila["que"] == (f"«Prueba86 Hotel»: ciudad {antes['nombre']} → "
                           f"{despues['nombre']}")
    assert "plaza_id" not in fila["que"]
    # Lo escrito tal cual se sigue entregando, para quien audita.
    assert fila["antes"] == f"plaza_id: {antes['id']}"


def test_quien_la_lee(cliente, sesion, aridiai):
    for quien in ("admin", "dirgeneral"):
        assert cliente.get("/bitacora-admin", headers=sesion(quien)).status_code == 200
    assert cliente.get("/bitacora-admin", headers=aridiai).status_code == 200
    # Direccion de operaciones fija lo que decide dinero, pero la bitacora
    # entera no es suya; la de sus catalogos si.
    for quien in ("diroperaciones", "consultor", "rrhh", "finanzas"):
        r = cliente.get("/bitacora-admin", headers=sesion(quien))
        assert r.status_code == 403, (quien, r.text)
    do = sesion("diroperaciones")
    assert cliente.get("/bitacora-admin/catalogo/tabulador-viaticos",
                       headers=do).status_code == 200
    assert cliente.get("/bitacora-admin/catalogo/tabulador-viaticos",
                       headers=sesion("consultor")).status_code == 403
    assert cliente.get("/bitacora-admin/catalogo/inventado",
                       headers=aridiai).status_code == 404
    assert cliente.get("/bitacora-admin/excel",
                       headers=sesion("consultor")).status_code == 403


def test_los_filtros(cliente, sesion, aridiai):
    _festivo(cliente, aridiai, "Prueba86 De ella")
    _festivo(cliente, sesion("admin"), "Prueba86 De admin", fecha="2031-12-25")

    catalogos = cliente.get("/bitacora-admin?que=catalogos", headers=aridiai).json()
    assert catalogos["total"] == 2
    ella = next(f["usuario_id"] for f in catalogos["filas"] if "De ella" in f["que"])
    assert ella in [q["usuario_id"] for q in catalogos["opciones"]["quienes"]]
    suyas = cliente.get(f"/bitacora-admin?que=catalogos&quien={ella}",
                        headers=aridiai).json()
    assert [f["que"] for f in suyas["filas"]] == ["Agregó «Prueba86 De ella»"]

    viejo = cliente.get("/bitacora-admin?mes=2001-01", headers=aridiai).json()
    assert viejo["total"] == 0

    # Lo que dejo darle su puesto --el puesto y el rol que trae-- esta en
    # accesos, contado con nombres.
    accesos = cliente.get("/bitacora-admin?que=accesos", headers=aridiai).json()
    ques = [f["que"] for f in accesos["filas"]]
    assert any(q.endswith(f"puesto ninguno → {PUESTO}") for q in ques), ques
    assert any(q.endswith("→ Sistema y calidad") and ": rol " in q for q in ques), ques
    assert all(f["donde"] == "Accesos" for f in accesos["filas"])


def test_las_lecturas_de_odoo_van_aparte(cliente, aridiai, base_de_pruebas):
    """La de cada hora deja su renglon aunque no cambie nada: en "todo"
    taparia lo que hizo una persona."""
    antes = cliente.get("/bitacora-admin", headers=aridiai).json()["total"]
    with base_de_pruebas.begin() as con:
        con.execute(text(
            "INSERT INTO registro_admin (usuario_id, persona_id, rol, accion, "
            "objeto, objeto_id, despues) SELECT id, persona_id, rol, "
            "'personal leido de odoo', 'sincronizacion_odoo', 1, "
            "'3 altas, 0 cambios, 0 bajas' FROM usuario "
            "WHERE correo = 'admin@centauro.lat'"))
    todo = cliente.get("/bitacora-admin", headers=aridiai).json()
    assert todo["total"] == antes
    assert all(f["grupo"] != "odoo" for f in todo["filas"])
    odoo = cliente.get("/bitacora-admin?que=odoo", headers=aridiai).json()
    assert odoo["total"] == 1
    assert odoo["filas"][0]["que"] == ("personal leido de odoo: "
                                       "3 altas, 0 cambios, 0 bajas")


def test_el_excel(cliente, aridiai):
    _festivo(cliente, aridiai, "Prueba86 Excel")
    r = cliente.get("/bitacora-admin/excel?que=catalogos", headers=aridiai)
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers["content-type"]
    assert r.headers["content-disposition"].startswith('attachment; filename="bitacora_')
    hojas = excel.leer(r.content)
    filas = hojas["Bitácora"]
    assert list(filas[0].values())[:5] == ["Cuándo", "Quién", "Con qué rol",
                                           "Dónde", "Qué cambió"]
    assert filas[1]["E"] == "Agregó «Prueba86 Excel»"
    assert filas[1]["F"] == "catalogo creado"


# ====================================================== los catalogos

def test_los_pesos_quedan_en_la_bitacora(cliente, sesion):
    do = sesion("diroperaciones")
    mx = _mx(cliente, do)
    r = cliente.put("/profesionalismo/pesos", json={
        "pais_id": mx["id"],
        "pesos": {"estrellas": 30, "satisfaccion": 25, "incidencias": 15,
                  "capacitacion": 10, "experiencia": 10, "manejo": 10},
        "castigo_grave": 70}, headers=do)
    assert r.status_code == 200, r.text
    r = cliente.get("/bitacora-admin/catalogo/profesionalismo", headers=do)
    assert r.status_code == 200, r.text
    fila = r.json()["filas"][0]
    assert fila["donde"] == "Pesos del profesionalismo"
    assert fila["que"] == (f"«{mx['nombre']}»: estrellas 25 → 30; "
                           "incidencias 20 → 15; castigo por incidencia "
                           "grave 60 → 70")
    # Guardar lo mismo otra vez no es un cambio.
    cliente.put("/profesionalismo/pesos", json={
        "pais_id": mx["id"],
        "pesos": {"estrellas": 30, "satisfaccion": 25, "incidencias": 15,
                  "capacitacion": 10, "experiencia": 10, "manejo": 10}}, headers=do)
    assert cliente.get("/bitacora-admin/catalogo/profesionalismo",
                       headers=do).json()["total"] == 1


def test_la_foto_de_una_categoria_se_ve_antes_de_cambiarla(cliente, sesion, aridiai):
    categoria = cliente.get("/catalogos/categorias-vehiculo", headers=aridiai).json()[0]
    ruta = f"/catalogos/categorias-vehiculo/{categoria['id']}/foto?color=prueba86"
    assert cliente.get(ruta, headers=aridiai).status_code == 404
    r = cliente.put(ruta, files={"archivo": ("x.png", PNG, "image/png")},
                    headers=aridiai)
    assert r.status_code == 200, r.text
    foto = cliente.get(ruta, headers=aridiai).json()
    assert foto["color"] == "prueba86"
    assert foto["foto"].startswith("data:image/png;base64,")
    # La ve tambien quien no la cambia.
    assert cliente.get(ruta, headers=sesion("consultor")).status_code == 200
    fila = cliente.get("/bitacora-admin/catalogo/categorias-vehiculo",
                       headers=aridiai).json()["filas"][0]
    assert fila["que"] == f"Puso la foto de «{categoria['nombre']}», prueba86"
    assert cliente.delete(ruta, headers=aridiai).status_code == 204


def test_lo_ligero_para_la_pantalla(cliente, sesion):
    h = sesion("diroperaciones")
    gente = cliente.get("/catalogos/freelance", headers=h)
    assert gente.status_code == 200, gente.text
    for p in gente.json():
        assert set(p) == {"id", "nombre", "activo"}
    colores = cliente.get("/catalogos/categorias-vehiculo/colores", headers=h)
    assert colores.status_code == 200, colores.text
    for lista_ in colores.json().values():
        assert lista_ == sorted(set(lista_)) and all(lista_)


# ====================================================== como se cuenta

@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_el_tipo_de_cambio_se_lee_como_se_lee(cliente, sesion, aridiai):
    fin = sesion("finanzas")
    for tasa in (17.25, 17.6200):
        r = cliente.put("/tarifarios/tipo-de-cambio", json={"tasa": tasa}, headers=fin)
        assert r.status_code == 200, r.text
    filas = cliente.get("/bitacora-admin?que=tipo_cambio", headers=aridiai).json()["filas"]
    assert [f["que"] for f in filas] == ["17.25 → 17.62 pesos por dólar",
                                         "ninguno → 17.25 pesos por dólar"]
    assert all(f["donde"] == "Tipo de cambio" for f in filas)


def test_un_puesto_al_que_solo_se_le_cambio_el_menu(db):
    """El puesto guarda en la bitacora las actividades que se le pusieron
    y quitaron; si solo cambio su menu, no se dice "ninguno"."""
    from app import bitacora_admin as ba
    from app import models as m

    r = m.RegistroAdmin(accion="categoria cambiada", objeto="categoria",
                        objeto_id=1, detalle="Monitorista")
    nombres = ba._Nombres(db, [r])
    assert ba.que_cambio(r, "es", nombres) == "«Monitorista»: cambió su menú o sus datos"
    assert ba.que_cambio(r, "en", nombres) == "“Monitorista”: changed its menu or its details"
    r.antes, r.despues = "operacion.corregir", "codigo.dictar"
    assert ba.que_cambio(r, "es", nombres) == ("«Monitorista»: agregó codigo.dictar; "
                                               "quitó operacion.corregir")


def test_lo_que_no_tiene_frase_se_dice_como_se_escribio(db):
    from app import bitacora_admin as ba
    from app import models as m

    r = m.RegistroAdmin(accion="algo nuevo", objeto="usuario", objeto_id=None,
                        antes="uno", despues="dos")
    assert ba.que_cambio(r, "pt", ba._Nombres(db, [r])) == "algo nuevo: uno → dos"

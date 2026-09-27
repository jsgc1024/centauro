"""Los candados de Accesos (seccion 83).

Decision de Salvador, 27 de septiembre, al aprobar el puesto de
administracion del sistema y calidad. Al revisarlo aparecieron dos huecos
que ya existian, y las dos pruebas de abajo que los dicen primero fallaban
antes de este cambio:

  * quien reparte accesos podia ampliar el puesto que el mismo trae
    --"nadie se da permisos a si mismo" se brincaba cambiando el puesto--;
  * y podia hacer a otra persona direccion general o administracion.

Desde aqui el puesto propio lo cambia otra persona, y direccion general,
administracion y el poder de repartir accesos solo los da, los quita o
los toca direccion general. Cerrarle la puerta a quien se va, si.

Las cuentas y los puestos son catalogo: no se vacian entre pruebas. Cada
prueba deja a las cuentas sembradas como estaban.
"""
import uuid

import pytest
from sqlalchemy import text

from app import models as m

DOMINIO = "candados83.lat"


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture(autouse=True)
def como_estaba(base_de_pruebas):
    """Se guarda el rol, el puesto y la puerta de cada cuenta, y sus
    permisos de mas, y al terminar se dejan como estaban. Lo que la prueba
    dio de alta --personas, accesos, puestos de prueba-- se va."""
    with base_de_pruebas.begin() as con:
        cuentas = con.execute(text(
            "SELECT id, rol, categoria_id, activo FROM usuario")).all()
        extras = [f[0] for f in con.execute(text("SELECT id FROM permiso_extra"))]
        puestos = {f[0]: f[1] for f in con.execute(text(
            "SELECT id, descripcion FROM categoria_acceso"))}
        actividades = con.execute(text(
            "SELECT categoria_id, actividad FROM actividad_de_categoria")).all()
    yield
    with base_de_pruebas.begin() as con:
        con.execute(text("DELETE FROM permiso_extra WHERE NOT (id = ANY(:ids))"),
                    {"ids": extras})
        ids = [f[0] for f in con.execute(text(
            "SELECT id FROM persona WHERE correo LIKE :d"), {"d": f"%@{DOMINIO}"})]
        if ids:
            con.execute(text("DELETE FROM invitacion WHERE usuario_id IN "
                             "(SELECT id FROM usuario WHERE persona_id = ANY(:ids))"),
                        {"ids": ids})
            con.execute(text("DELETE FROM usuario WHERE persona_id = ANY(:ids)"),
                        {"ids": ids})
            con.execute(text("DELETE FROM persona WHERE id = ANY(:ids)"), {"ids": ids})
        for u in cuentas:
            con.execute(text("UPDATE usuario SET rol = :rol, categoria_id = :c, "
                             "activo = :a WHERE id = :id"),
                        {"rol": u.rol, "c": u.categoria_id, "a": u.activo, "id": u.id})
        nuevos = [i for (i,) in con.execute(text("SELECT id FROM categoria_acceso"))
                  if i not in puestos]
        if nuevos:
            con.execute(text("UPDATE usuario SET categoria_id = NULL "
                             "WHERE categoria_id = ANY(:ids)"), {"ids": nuevos})
            con.execute(text("DELETE FROM actividad_de_categoria "
                             "WHERE categoria_id = ANY(:ids)"), {"ids": nuevos})
            con.execute(text("DELETE FROM categoria_acceso WHERE id = ANY(:ids)"),
                        {"ids": nuevos})
        con.execute(text("DELETE FROM actividad_de_categoria"))
        for categoria_id, actividad in actividades:
            con.execute(text("INSERT INTO actividad_de_categoria (categoria_id, actividad) "
                             "VALUES (:c, :a)"), {"c": categoria_id, "a": actividad})
        for categoria_id, descripcion in puestos.items():
            con.execute(text("UPDATE categoria_acceso SET descripcion = :d WHERE id = :id"),
                        {"d": descripcion, "id": categoria_id})


# ------------------------------------------------------------------ ayudas

def _entrar(cliente, correo):
    r = cliente.post("/auth/token",
                     data={"username": correo, "password": "centauro2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _usuarios(cliente, sesion):
    r = cliente.get("/auth/usuarios", headers=sesion("dirgeneral"))
    assert r.status_code == 200, r.text
    return {u["correo"]: u for u in r.json()}


def _puestos(cliente, sesion):
    h = sesion("dirgeneral")
    assert cliente.post("/auth/categorias/base", headers=h).status_code == 200
    return {p["nombre"]: p for p in cliente.get("/auth/categorias", headers=h).json()}


def _ponerle(cliente, sesion, correo, puesto):
    """Direccion general le pone el puesto; regresa su sesion nueva."""
    u = _usuarios(cliente, sesion)[correo]
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/categoria",
                     json={"categoria_id": puesto["categoria_id"]},
                     headers=sesion("dirgeneral"))
    assert r.status_code == 200, r.text
    return _entrar(cliente, correo)


def _persona_nueva(db, nombre="Persona Candado"):
    plaza = db.query(m.Plaza).first()
    p = m.Persona(nombre=nombre, correo=f"{uuid.uuid4().hex[:8]}@{DOMINIO}",
                  plaza_id=plaza.id)
    db.add(p)
    db.commit()
    return p.id


def _dice(r, texto):
    assert texto in r.text, r.text


# ============================================ los dos huecos que existian

def test_nadie_amplia_su_propio_puesto(cliente, sesion):
    """El hueco: RH se agregaba a su puesto pagar la nomina o facturar."""
    rh = _ponerle(cliente, sesion, "rrhh@centauro.lat",
                  _puestos(cliente, sesion)["Recursos Humanos"])
    puesto = _puestos(cliente, sesion)["Recursos Humanos"]
    r = cliente.patch(f"/auth/categorias/{puesto['categoria_id']}",
                      json={"actividades": puesto["actividades"] + ["nomina.pagar"]},
                      headers=rh)
    assert r.status_code == 409, r.text
    _dice(r, "Es tu puesto")
    yo = cliente.get("/auth/yo", headers=rh).json()
    assert "nomina.pagar" not in yo["actividades"]
    # Tampoco lo demas del puesto: ni el nombre ni la descripcion.
    r = cliente.patch(f"/auth/categorias/{puesto['categoria_id']}",
                      json={"descripcion": "otra"}, headers=rh)
    assert r.status_code == 409, r.text


def test_rrhh_no_hace_a_nadie_direccion_general_ni_administracion(cliente, sesion):
    """El hueco: RH le cambiaba el rol a otra persona a direccion general
    o a administracion."""
    u = _usuarios(cliente, sesion)["beatriz.roman@centauro.lat"]
    for rol in ("director_general", "admin"):
        r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/rol",
                         json={"rol": rol, "motivo": "prueba"},
                         headers=sesion("rrhh"))
        assert r.status_code == 403, r.text
        _dice(r, "Dirección general")
    assert _usuarios(cliente, sesion)["beatriz.roman@centauro.lat"]["rol"] == "consultor"


# ============================================ direccion general y la llave

def test_rrhh_no_da_un_acceso_de_direccion_ni_de_administracion(cliente, sesion, db):
    pid = _persona_nueva(db)
    for rol in ("director_general", "admin"):
        r = cliente.post("/auth/usuarios", json={"persona_id": pid, "rol": rol},
                         headers=sesion("rrhh"))
        assert r.status_code == 403, r.text
    # Direccion general si.
    r = cliente.post("/auth/usuarios", json={"persona_id": pid, "rol": "admin"},
                     headers=sesion("dirgeneral"))
    assert r.status_code == 201, r.text


def test_rrhh_no_toca_a_direccion_general(cliente, sesion):
    """Ni le cambia el rol, ni le cierra la puerta, ni le pone puesto."""
    dg = _usuarios(cliente, sesion)["direccion@centauro.lat"]
    rh = sesion("rrhh")
    r = cliente.post(f"/auth/usuarios/{dg['usuario_id']}/rol",
                     json={"rol": "consultor"}, headers=rh)
    assert r.status_code == 403, r.text
    r = cliente.post(f"/auth/usuarios/{dg['usuario_id']}/desactivar",
                     json={"motivo": "prueba"}, headers=rh)
    assert r.status_code == 403, r.text
    monitorista = _puestos(cliente, sesion)["Monitorista"]
    r = cliente.post(f"/auth/usuarios/{dg['usuario_id']}/categoria",
                     json={"categoria_id": monitorista["categoria_id"]}, headers=rh)
    assert r.status_code == 403, r.text
    assert _usuarios(cliente, sesion)["direccion@centauro.lat"]["activo"] is True


def test_direccion_general_si_hace_y_quita_administracion(cliente, sesion):
    u = _usuarios(cliente, sesion)["beatriz.roman@centauro.lat"]
    dg = sesion("dirgeneral")
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/rol",
                     json={"rol": "admin", "motivo": "emergencia"}, headers=dg)
    assert r.status_code == 200, r.text
    r = cliente.post(f"/auth/usuarios/{u['usuario_id']}/rol",
                     json={"rol": "consultor", "motivo": "ya paso"}, headers=dg)
    assert r.status_code == 200, r.text


# ============================================ el poder de repartir accesos

def test_un_puesto_que_reparte_accesos_lo_arma_y_lo_cambia_direccion_general(cliente, sesion):
    rh = sesion("rrhh")
    nombre = f"Prueba83 {uuid.uuid4().hex[:6]}"
    r = cliente.post("/auth/categorias", json={
        "nombre": nombre, "actividades": ["accesos.dar", "bonos.ver"]}, headers=rh)
    assert r.status_code == 403, r.text
    # Ponerle a otro puesto la casilla de repartir, tampoco.
    mon = _puestos(cliente, sesion)["Monitorista"]
    r = cliente.patch(f"/auth/categorias/{mon['categoria_id']}",
                      json={"actividades": mon["actividades"] + ["accesos.dar"]},
                      headers=rh)
    assert r.status_code == 403, r.text
    # Y el de Recursos Humanos, aunque RH no lo traiga puesto, es de
    # direccion general: reparte accesos.
    puesto_rh = _puestos(cliente, sesion)["Recursos Humanos"]
    r = cliente.patch(f"/auth/categorias/{puesto_rh['categoria_id']}",
                      json={"descripcion": "otra"}, headers=rh)
    assert r.status_code == 403, r.text
    # Direccion general, si.
    r = cliente.post("/auth/categorias", json={
        "nombre": nombre, "actividades": ["accesos.dar", "bonos.ver"]},
        headers=sesion("dirgeneral"))
    assert r.status_code == 201, r.text
    assert r.json()["reparte"] is True


def test_los_demas_puestos_los_sigue_cambiando_quien_reparte(cliente, sesion):
    """Un candado que impide lo de todos los dias no sirve: RH sigue
    armando y ajustando los puestos que no reparten accesos."""
    rh = sesion("rrhh")
    mon = _puestos(cliente, sesion)["Monitorista"]
    assert mon["reparte"] is False
    r = cliente.patch(f"/auth/categorias/{mon['categoria_id']}",
                      json={"descripcion": "Monitoreo y código."}, headers=rh)
    assert r.status_code == 200, r.text
    r = cliente.post("/auth/categorias", json={
        "nombre": f"Prueba83 {uuid.uuid4().hex[:6]}", "actividades": ["bonos.ver"]},
        headers=rh)
    assert r.status_code == 201, r.text


def test_el_acceso_que_reparte_accesos_lo_da_direccion_general(cliente, sesion, db):
    rh = sesion("rrhh")
    puestos = _puestos(cliente, sesion)
    pid = _persona_nueva(db)
    # Con el puesto de Recursos Humanos, o con su rol sin puesto: no.
    r = cliente.post("/auth/usuarios", json={
        "persona_id": pid, "rol": "consultor",
        "categoria_id": puestos["Recursos Humanos"]["categoria_id"]}, headers=rh)
    assert r.status_code == 403, r.text
    r = cliente.post("/auth/usuarios", json={"persona_id": pid, "rol": "recursos_humanos"},
                     headers=rh)
    assert r.status_code == 403, r.text
    # Capacitacion entra como recursos humanos y no reparte: ese si.
    r = cliente.post("/auth/usuarios", json={
        "persona_id": pid, "rol": "consultor",
        "categoria_id": puestos["Capacitación"]["categoria_id"]}, headers=rh)
    assert r.status_code == 201, r.text
    assert r.json()["rol"] == "recursos_humanos"


def test_el_permiso_de_repartir_y_el_acceso_de_quien_reparte(cliente, sesion):
    rh = sesion("rrhh")
    usuarios = _usuarios(cliente, sesion)
    beatriz = usuarios["beatriz.roman@centauro.lat"]
    # El permiso de repartir accesos, como permiso de mas: no.
    r = cliente.post(f"/auth/usuarios/{beatriz['usuario_id']}/permisos",
                     json={"actividad": "accesos.dar"}, headers=rh)
    assert r.status_code == 403, r.text
    # A quien ya reparte --otra de recursos humanos--, ni un permiso de mas
    # ni otro puesto: eso lo cambia direccion general.
    dg = sesion("dirgeneral")
    central2 = usuarios["central2@centauro.lat"]
    r = cliente.post(f"/auth/usuarios/{central2['usuario_id']}/rol",
                     json={"rol": "recursos_humanos"}, headers=dg)
    assert r.status_code == 200, r.text
    assert _usuarios(cliente, sesion)["central2@centauro.lat"]["reparte"] is True
    r = cliente.post(f"/auth/usuarios/{central2['usuario_id']}/permisos",
                     json={"actividad": "bonos.ver"}, headers=rh)
    assert r.status_code == 403, r.text
    mon = _puestos(cliente, sesion)["Monitorista"]
    r = cliente.post(f"/auth/usuarios/{central2['usuario_id']}/categoria",
                     json={"categoria_id": mon["categoria_id"]}, headers=rh)
    assert r.status_code == 403, r.text
    # Cerrarle la puerta cuando se va, si.
    r = cliente.post(f"/auth/usuarios/{central2['usuario_id']}/desactivar",
                     json={"motivo": "se fue"}, headers=rh)
    assert r.status_code == 200, r.text


def test_a_los_demas_rrhh_les_sigue_dando_su_acceso(cliente, sesion):
    """Lo de todos los dias no cambia: un puesto sin el poder de repartir
    y un permiso de mas a quien no reparte."""
    rh = sesion("rrhh")
    beatriz = _usuarios(cliente, sesion)["beatriz.roman@centauro.lat"]
    r = cliente.post(f"/auth/usuarios/{beatriz['usuario_id']}/permisos",
                     json={"actividad": "bonos.ver"}, headers=rh)
    assert r.status_code == 200, r.text
    jr = _puestos(cliente, sesion)["Consultor JR"]
    r = cliente.post(f"/auth/usuarios/{beatriz['usuario_id']}/categoria",
                     json={"categoria_id": jr["categoria_id"]}, headers=rh)
    assert r.status_code == 200, r.text


# ============================================ lo que la pantalla necesita

def test_la_pantalla_sabe_que_no_ofrecer(cliente, sesion):
    rh = _ponerle(cliente, sesion, "rrhh@centauro.lat",
                  _puestos(cliente, sesion)["Recursos Humanos"])
    yo = cliente.get("/auth/yo", headers=rh).json()
    assert yo["es_direccion"] is False
    assert yo["categoria_id"] == _puestos(cliente, sesion)["Recursos Humanos"]["categoria_id"]
    assert cliente.get("/auth/yo", headers=sesion("dirgeneral")).json()["es_direccion"] is True
    assert cliente.get("/auth/yo", headers=sesion("admin")).json()["es_direccion"] is True
    usuarios = _usuarios(cliente, sesion)
    assert usuarios["direccion@centauro.lat"]["alto"] is True
    assert usuarios["admin@centauro.lat"]["alto"] is True
    assert usuarios["rrhh@centauro.lat"]["reparte"] is True
    assert usuarios["beatriz.roman@centauro.lat"]["reparte"] is False
    puestos = _puestos(cliente, sesion)
    assert puestos["Recursos Humanos"]["reparte"] is True
    assert puestos["Capacitación"]["reparte"] is False


def test_direccion_y_la_llave_ya_no_se_sugieren(cliente, sesion):
    """Se sugerian por su puesto de Odoo --la llave maestra a quien era
    desarrollador-- y RH las daba con un clic. Siguen en la lista de
    puestos, con cuanta gente entra asi, sin a quien sugerirlas."""
    from app import odoo_oficina, odoo_oficina_reglas as reglas
    from app.db import SessionLocal

    with SessionLocal() as db:
        puestos = odoo_oficina.sugeribles(db)
    assert all(p["tipo"] == "puesto" for p in puestos)
    for titulo in ("Director General", "Jefa de Desarrollo web", "Desarrollador"):
        s = reglas.sugerir(titulo, puestos)
        assert s is None or s["rol"] not in ("admin", "director_general"), (titulo, s)
    base = cliente.get("/auth/categorias/base", headers=sesion("rrhh")).json()
    por_rol = {p["rol"]: p for p in base["por_rol"]}
    assert set(por_rol) == {"director_general", "admin"}
    assert all(not p["puestos_odoo"] for p in por_rol.values())
    assert por_rol["admin"]["nombre"] == "Administración (llave maestra)"

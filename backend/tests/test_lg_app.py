"""LG Connect, la app de los operadores de Logistica (seccion 151).

Decision de Salvador, 3 oct: los operadores no usan la app de Proteccion
Ejecutiva. Tienen la suya, en applg.mycentauro.lat, con sus propios
usuarios: un operador no ve nada de EP ni un agente de EP ve nada de
Logistica. Entran con su correo personal; la primera vez, con los cuatro
digitos que les dicta Karla o quien lleva la flota; despues, con huella o
cara.

Aqui: que cada sesion abra solo lo suyo, el codigo de una vez, la
contrasena que cierra lo de antes, la baja que cierra la puerta y la
marca de jornada desde la app.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from ayudas_lg import (DENTRO, FUERA, central, db, karla, logistica,  # noqa: F401
                       operador)
from app import auth, intentos
from app import models as m

CORREO = "pedro.lopez@gmail.com"
CLAVE = "camino al norte 2026"


@pytest.fixture(autouse=True)
def sin_intentos():
    """Los fallos de una prueba no le cuentan a la siguiente."""
    def limpiar():
        for correo in (CORREO, "nadie@gmail.com"):
            intentos.limpiar(f"lg:{correo}", "testclient")
    limpiar()
    yield
    limpiar()


def _codigo(cliente, h, o) -> str:
    r = cliente.post(f"/lg/jornada/operadores/{o.id}/codigo", headers=h)
    assert r.status_code == 200, r.text
    codigo = r.json()["codigo"]
    assert len(codigo) == 4 and codigo.isdigit()
    assert r.json()["minutos"] == 10
    return codigo


def _alta(cliente, karla, o, clave=CLAVE) -> dict:
    """El operador crea su contrasena con el codigo y queda adentro."""
    codigo = _codigo(cliente, karla, o)
    r = cliente.post("/lgapp-api/codigo", json={"correo": o.correo.upper(),
                                                "codigo": codigo, "nueva": clave})
    assert r.status_code == 200, r.text
    assert r.json()["nombre"] == o.nombre
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ====================================================== cada quien lo suyo

def test_cada_sesion_abre_solo_lo_suyo(cliente, karla, sesion, db):
    o = operador(db)
    lg = _alta(cliente, karla, o)
    assert cliente.get("/lgapp-api/yo", headers=lg).status_code == 200
    # La de LG Connect no abre la consola, ni la app de EP, ni la del
    # cliente de la Central.
    for ruta in ("/auth/yo", "/lg/flota", "/lg/jornada/dia", "/servicios",
                 "/ci-api/yo"):
        assert cliente.get(ruta, headers=lg).status_code == 401, ruta
    # Y ninguna otra abre LG Connect: ni la de la gerencia, ni la de un
    # agente de EP, ni la de la consola de administracion.
    for h in (karla, sesion("juan"), sesion("admin")):
        assert cliente.get("/lgapp-api/yo", headers=h).status_code == 401
    # Ni una del cliente de la Central con el mismo numero.
    ahora = datetime.now(timezone.utc)
    ci = jwt.encode({"sub": str(o.id), "tipo": "cliente_ci", "iat": ahora,
                     "emitido": ahora.timestamp(), "exp": ahora + timedelta(days=1)},
                    auth._clave(), algorithm=auth.ALGORITMO)
    assert cliente.get("/lgapp-api/yo",
                       headers={"Authorization": f"Bearer {ci}"}).status_code == 401
    assert cliente.get("/lgapp-api/yo").status_code == 401


def test_el_reto_de_la_huella_no_es_sesion(cliente, karla, db):
    o = operador(db)
    lg = _alta(cliente, karla, o)
    assert cliente.post("/lgapp-api/llaves/alta/opciones", headers=lg,
                        json={"contrasena": "otra cosa"}).status_code == 403
    r = cliente.post("/lgapp-api/llaves/alta/opciones", headers=lg,
                     json={"contrasena": CLAVE})
    assert r.status_code == 200, r.text
    opciones = json.loads(r.json()["opciones"])
    assert opciones["rp"]["name"] == "LG Connect"
    relleno = "=" * (-len(opciones["user"]["id"]) % 4)
    assert base64.urlsafe_b64decode(opciones["user"]["id"] + relleno) == f"lg-{o.id}".encode()
    estado = {"Authorization": f"Bearer {r.json()['estado']}"}
    for ruta in ("/lgapp-api/yo", "/auth/yo"):
        assert cliente.get(ruta, headers=estado).status_code == 401, ruta
    # Una huella que el sistema no conoce no entra.
    r = cliente.post("/lgapp-api/llaves/entrada/opciones", json={"correo": CORREO})
    assert r.status_code == 200
    r = cliente.post("/lgapp-api/llaves/entrada", json={
        "credencial": {"id": "no-existe", "rawId": "no-existe", "type": "public-key",
                       "response": {}}, "estado": r.json()["estado"]})
    assert r.status_code == 401
    assert r.json()["detail"]["codigo"] == "huella_desconocida"


# ====================================================== el codigo

def test_el_codigo_sirve_una_vez(cliente, karla, db):
    o = operador(db)
    codigo = _codigo(cliente, karla, o)
    datos = {"correo": CORREO, "codigo": codigo, "nueva": CLAVE}
    assert cliente.post("/lgapp-api/codigo", json=datos).status_code == 200
    r = cliente.post("/lgapp-api/codigo", json=datos)
    assert r.status_code == 400
    assert r.json()["detail"]["mensaje"] == "Ese código no sirve o ya venció."


def test_el_codigo_nuevo_mata_al_anterior_y_cinco_fallos_lo_anulan(cliente, karla, db):
    o = operador(db)
    viejo = _codigo(cliente, karla, o)
    nuevo = _codigo(cliente, karla, o)
    if viejo != nuevo:
        assert cliente.post("/lgapp-api/codigo", json={
            "correo": CORREO, "codigo": viejo, "nueva": CLAVE}).status_code == 400
    malo = "0000" if nuevo != "0000" else "1111"
    for _ in range(5):
        cliente.post("/lgapp-api/codigo", json={"correo": CORREO, "codigo": malo,
                                                "nueva": CLAVE})
    db.expire_all()
    vigentes = db.query(m.LgCodigoAcceso).filter(m.LgCodigoAcceso.operador_id == o.id,
                                                 m.LgCodigoAcceso.anulado_en.is_(None),
                                                 m.LgCodigoAcceso.usado_en.is_(None)).count()
    assert vigentes == 0
    assert cliente.post("/lgapp-api/codigo", json={
        "correo": CORREO, "codigo": nuevo, "nueva": CLAVE}).status_code in (400, 429)


def test_quien_da_el_codigo(cliente, karla, central, sesion, db):
    o = operador(db)
    sin_correo = operador(db, "Raul Diaz", None)
    assert cliente.post(f"/lg/jornada/operadores/{o.id}/codigo",
                        headers=central).status_code == 403
    assert cliente.post(f"/lg/jornada/operadores/{o.id}/codigo",
                        headers=sesion("consultor")).status_code == 403
    r = cliente.post(f"/lg/jornada/operadores/{sin_correo.id}/codigo", headers=karla)
    assert r.status_code == 409
    assert "no tiene correo en Odoo" in r.json()["detail"]["mensaje"]
    _codigo(cliente, karla, o)
    filas = cliente.get("/lg/jornada/bitacora", headers=karla).json()["filas"]
    assert filas[0]["que"] == "Pedro Lopez: código de la app"
    # El codigo no queda en la bitacora ni en la base en claro.
    assert all(len(c.hash) > 20 for c in db.query(m.LgCodigoAcceso).all())


# ====================================================== la contrasena y la baja

def test_entrar_con_contrasena(cliente, karla, db):
    o = operador(db)
    _alta(cliente, karla, o)
    r = cliente.post("/lgapp-api/entrar", json={"correo": " Pedro.Lopez@gmail.com ",
                                                "contrasena": CLAVE})
    assert r.status_code == 200, r.text
    assert cliente.post("/lgapp-api/entrar", json={"correo": CORREO,
                                                   "contrasena": "otra"}).status_code == 401
    assert cliente.post("/lgapp-api/entrar", json={"correo": "nadie@gmail.com",
                                                   "contrasena": CLAVE}).status_code == 401
    # La consola no conoce a los operadores.
    assert cliente.post("/auth/token", data={"username": CORREO,
                                             "password": CLAVE}).status_code == 401


def test_cambiar_la_contrasena_cierra_lo_de_antes(cliente, karla, db):
    o = operador(db)
    vieja = _alta(cliente, karla, o)
    assert cliente.post("/lgapp-api/contrasena", headers=vieja,
                        json={"actual": "no es", "nueva": "otra frase larga"}).status_code == 403
    r = cliente.post("/lgapp-api/contrasena", headers=vieja,
                     json={"actual": CLAVE, "nueva": "otra frase larga"})
    assert r.status_code == 200, r.text
    nueva = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert cliente.get("/lgapp-api/yo", headers=nueva).status_code == 200
    assert cliente.get("/lgapp-api/yo", headers=vieja).status_code == 401


def test_la_baja_cierra_la_puerta(cliente, karla, db):
    o = operador(db)
    lg = _alta(cliente, karla, o)
    o.activo = False
    db.commit()
    assert cliente.get("/lgapp-api/yo", headers=lg).status_code == 401
    r = cliente.post("/lgapp-api/entrar", json={"correo": CORREO, "contrasena": CLAVE})
    assert r.status_code == 403


# ====================================================== la marca desde la app

def test_marcar_la_jornada_desde_la_app(cliente, karla, db):
    o = operador(db)
    lg = _alta(cliente, karla, o)
    yo = cliente.get("/lgapp-api/yo", headers=lg).json()
    assert yo["marca"] is None
    assert yo["patios"] == [{"id": yo["patios"][0]["id"], "nombre": "Base Cuautitlán",
                             "lat": 19.672, "lon": -99.179, "radio": 300}]
    r = cliente.post("/lgapp-api/jornada", headers=lg,
                     json={"lat": float(FUERA[0]), "lon": float(FUERA[1]), "precision": 15})
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "fuera_del_patio"
    # Como lo manda el telefono: quince decimales, y la precision con los
    # suyos. Se redondea a siete (un centimetro), no se rechaza.
    r = cliente.post("/lgapp-api/jornada", headers=lg,
                     json={"lat": 19.672359319432176, "lon": -99.17900013284125,
                           "precision": 12.684})
    assert r.status_code == 201, r.text
    assert r.json()["marca"]["estado"] == "valida"
    j = db.query(m.LgJornada).filter_by(operador_id=o.id).one()
    assert (str(j.lat), str(j.lon), j.precision_m, j.distancia_m) == (
        "19.6723593", "-99.1790001", 13, 39)
    i = r.json()["semana"]["dias"]
    assert any(d["codigo"] == "marca" for d in i)
    assert cliente.post("/lgapp-api/jornada", headers=lg,
                        json={"lat": float(DENTRO[0]),
                              "lon": float(DENTRO[1])}).status_code == 409
    assert cliente.post("/lgapp-api/idioma", headers=lg,
                        json={"idioma": "pt"}).json() == {"idioma": "pt"}


def test_al_octavo_fallo_espera_en_su_propio_carril(cliente, karla, sesion, db):
    o = operador(db)
    _alta(cliente, karla, o)
    for _ in range(intentos.MAXIMO):
        assert cliente.post("/lgapp-api/entrar", json={
            "correo": CORREO, "contrasena": "no es"}).status_code == 401
    r = cliente.post("/lgapp-api/entrar", json={"correo": CORREO, "contrasena": CLAVE})
    assert r.status_code == 429
    # La consola desde la misma red sigue entrando.
    assert cliente.post("/auth/token", data={"username": "admin@centauro.lat",
                                             "password": "centauro2026"}).status_code == 200

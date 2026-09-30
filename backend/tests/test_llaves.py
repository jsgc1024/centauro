"""Entrar con huella o cara: las llaves de acceso (30 sep).

Aqui no hay telefono: se hace el papel del autenticador, con una llave
ES256 de verdad, y se le contesta al sistema exactamente como contestaria
un telefono (WebAuthn, sin certificado de fabricante). Lo que se cuida es
lo nuestro: que solo entre la firma buena, que el reto no se use dos
veces, que una llave no le abra la puerta a quien ya no trabaja aqui y
que cada quien vea y quite solo las suyas.
"""
import base64
import hashlib
import json
import os
import struct

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import text

from conftest import CUENTAS

ORIGEN = "http://localhost:8000"
SITIO = "localhost"
CLAVE = "centauro2026"


def b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


class Telefono:
    """Un autenticador de plataforma: guarda su llave y firma tras la
    huella. `origen` es la direccion desde donde firma."""

    def __init__(self, origen=ORIGEN, sitio=SITIO):
        self.privada = ec.generate_private_key(ec.SECP256R1())
        self.credencial = os.urandom(16)
        self.origen, self.sitio = origen, sitio
        self.contador = 0

    def _sitio(self) -> bytes:
        return hashlib.sha256(self.sitio.encode()).digest()

    def _cliente(self, tipo: str, reto: str) -> bytes:
        return json.dumps({"type": tipo, "challenge": reto,
                           "origin": self.origen,
                           "crossOrigin": False}).encode()

    def crear(self, opciones: dict) -> dict:
        numeros = self.privada.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1,
                            -2: numeros.x.to_bytes(32, "big"),
                            -3: numeros.y.to_bytes(32, "big")})
        datos = (self._sitio() + bytes([0x45]) + struct.pack(">I", 0)
                 + bytes(16) + struct.pack(">H", len(self.credencial))
                 + self.credencial + cose)
        objeto = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": datos})
        return {"id": b64(self.credencial), "rawId": b64(self.credencial),
                "type": "public-key",
                "response": {"clientDataJSON": b64(self._cliente(
                                 "webauthn.create", opciones["challenge"])),
                             "attestationObject": b64(objeto)}}

    def firmar(self, opciones: dict, huella=True) -> dict:
        # 0x05 = presente y verificado (la huella); 0x01 = solo presente.
        banderas = 0x05 if huella else 0x01
        datos = self._sitio() + bytes([banderas]) + struct.pack(">I", self.contador)
        cliente = self._cliente("webauthn.get", opciones["challenge"])
        firma = self.privada.sign(datos + hashlib.sha256(cliente).digest(),
                                  ec.ECDSA(hashes.SHA256()))
        return {"id": b64(self.credencial), "rawId": b64(self.credencial),
                "type": "public-key",
                "response": {"clientDataJSON": b64(cliente),
                             "authenticatorData": b64(datos),
                             "signature": b64(firma), "userHandle": None}}


@pytest.fixture(autouse=True)
def sin_llaves(base_de_pruebas):
    yield
    with base_de_pruebas.begin() as con:
        con.execute(text("TRUNCATE llave_acceso RESTART IDENTITY"))


def _activar(cliente, sesion, quien, telefono, nombre="Chrome en Android"):
    h = sesion(quien)
    r = cliente.post("/auth/llaves/alta/opciones", json={"contrasena": CLAVE},
                     headers=h)
    assert r.status_code == 200, r.text
    opciones = json.loads(r.json()["opciones"])
    r = cliente.post("/auth/llaves/alta", headers=h, json={
        "credencial": telefono.crear(opciones), "estado": r.json()["estado"],
        "nombre": nombre})
    assert r.status_code == 201, r.text
    return r.json()


def _entrar(cliente, telefono, correo=None, **firma):
    r = cliente.post("/auth/llaves/entrada/opciones", json={"correo": correo})
    assert r.status_code == 200, r.text
    opciones = json.loads(r.json()["opciones"])
    return cliente.post("/auth/llaves/entrada", json={
        "credencial": telefono.firmar(opciones, **firma),
        "estado": r.json()["estado"]}), opciones


def test_se_activa_y_se_entra_con_la_huella(cliente, sesion):
    tel = Telefono()
    _activar(cliente, sesion, "consultor", tel)
    r, _ = _entrar(cliente, tel)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["correo"] == CUENTAS["consultor"]
    # La sesion vale igual que la de la contrasena.
    yo = cliente.get("/auth/yo",
                     headers={"Authorization": f"Bearer {d['access_token']}"})
    assert yo.status_code == 200 and yo.json()["correo"] == CUENTAS["consultor"]


def test_tambien_el_personal_de_seguridad(cliente, sesion):
    """Los telefonos son de cada quien (Salvador, 30 sep)."""
    tel = Telefono(origen=ORIGEN)
    _activar(cliente, sesion, "juan", tel)
    r, _ = _entrar(cliente, tel, correo=CUENTAS["juan"])
    assert r.status_code == 200, r.text
    assert r.json()["rol"] == "personal_seguridad"


def test_activarla_pide_la_contrasena(cliente, sesion):
    """Con una sesion abierta ajena no se da de alta otro telefono."""
    r = cliente.post("/auth/llaves/alta/opciones",
                     json={"contrasena": "otra-cosa"},
                     headers=sesion("consultor"))
    assert r.status_code == 403
    r = cliente.post("/auth/llaves/alta/opciones", json={"contrasena": CLAVE})
    assert r.status_code == 401, "sin sesion no se activa nada"


def test_sin_la_huella_no_entra(cliente, sesion):
    """La llave que solo dice "alguien toco" no basta: tiene que haber
    huella, cara o PIN del equipo."""
    tel = Telefono()
    _activar(cliente, sesion, "consultor", tel)
    r, _ = _entrar(cliente, tel, huella=False)
    assert r.status_code == 401


def test_otra_llave_no_entra(cliente, sesion):
    tel = Telefono()
    _activar(cliente, sesion, "consultor", tel)
    impostor = Telefono()
    impostor.credencial = tel.credencial      # dice ser la misma llave
    r, _ = _entrar(cliente, impostor)
    assert r.status_code == 401


def test_desde_otro_sitio_no_entra(cliente, sesion):
    """Una firma hecha en una pagina que no es la nuestra no sirve."""
    tel = Telefono()
    _activar(cliente, sesion, "consultor", tel)
    tel.origen = "https://mycentauro-falso.lat"
    r, _ = _entrar(cliente, tel)
    assert r.status_code == 401


def test_el_reto_se_usa_una_vez(cliente, sesion):
    tel = Telefono()
    _activar(cliente, sesion, "consultor", tel)
    r = cliente.post("/auth/llaves/entrada/opciones", json={})
    estado = r.json()["estado"]
    firmada = tel.firmar(json.loads(r.json()["opciones"]))
    primera = cliente.post("/auth/llaves/entrada",
                           json={"credencial": firmada, "estado": estado})
    assert primera.status_code == 200, primera.text
    otra = cliente.post("/auth/llaves/entrada",
                        json={"credencial": firmada, "estado": estado})
    assert otra.status_code == 400


def test_quien_ya_no_trabaja_aqui_no_entra(cliente, sesion):
    from app import models as m
    from app.db import SessionLocal
    tel = Telefono()
    _activar(cliente, sesion, "consultor", tel)
    with SessionLocal() as db:
        u = db.query(m.Usuario).filter_by(correo=CUENTAS["consultor"]).one()
        u.activo = False
        db.commit()
    try:
        r, _ = _entrar(cliente, tel)
        assert r.status_code == 403
    finally:
        with SessionLocal() as db:
            u = db.query(m.Usuario).filter_by(correo=CUENTAS["consultor"]).one()
            u.activo = True
            db.commit()


def test_con_el_correo_el_telefono_solo_ofrece_sus_llaves(cliente, sesion):
    tel = Telefono()
    alta = _activar(cliente, sesion, "consultor", tel)
    _, opciones = _entrar(cliente, tel, correo=CUENTAS["consultor"])
    assert [c["id"] for c in opciones["allowCredentials"]] == [alta["credencial_id"]]


def test_el_correo_no_regala_si_existe(cliente, sesion):
    """Revision de la seccion 110: el correo con huella traia su lista y
    el que no, nada, asi que probando correos se sabia quien trabaja
    aqui. Ahora el que no tiene --exista o no la cuenta-- recibe una llave
    inventada, siempre la misma, que no abre nada."""
    def pedir(correo):
        r = cliente.post("/auth/llaves/entrada/opciones", json={"correo": correo})
        assert r.status_code == 200, r.text
        return [c["id"] for c in json.loads(r.json()["opciones"])["allowCredentials"]]

    nadie = pedir("nadie@centauro.lat")
    sin_huella = pedir(CUENTAS["central"])          # existe y no la tiene
    assert len(nadie) == 1 and len(sin_huella) == 1
    assert nadie != sin_huella
    # La misma cada vez, como la de verdad: si cambiara, se notaria.
    assert pedir(" Nadie@Centauro.lat") == nadie
    assert len(de_b64(nadie[0])) in (16, 20, 32)
    # Y no abre nada.
    tel = Telefono()
    tel.credencial = de_b64(nadie[0])
    r, _ = _entrar(cliente, tel, correo="nadie@centauro.lat")
    assert r.status_code == 401


def test_la_contrasena_nueva_quita_las_huellas(cliente, sesion, datos):
    """Revision de la seccion 110: quien se quedo con la contrasena pudo
    activar su propio telefono. Cambiarla lo saca de la sesion y tambien
    de la puerta; el equipo que la tenia se entera con su codigo, para
    olvidarla y volver a ofrecerla."""
    from test_contrasenas import BUENA, _cabecera, _cuenta
    cuenta = _cuenta(cliente, sesion, datos)
    suyo = _cabecera(cliente, cuenta)
    r = cliente.post("/auth/llaves/alta/opciones", json={"contrasena": BUENA},
                     headers=suyo)
    assert r.status_code == 200, r.text
    ajeno = Telefono()
    r = cliente.post("/auth/llaves/alta", headers=suyo, json={
        "credencial": ajeno.crear(json.loads(r.json()["opciones"])),
        "estado": r.json()["estado"], "nombre": "El del que la robo"})
    assert r.status_code == 201, r.text
    r, _ = _entrar(cliente, ajeno)
    assert r.status_code == 200, r.text

    r = cliente.post("/auth/mi-contrasena", headers=suyo,
                     json={"actual": BUENA, "nueva": "camino largo a casa"})
    assert r.status_code == 200, r.text

    r, _ = _entrar(cliente, ajeno)
    assert r.status_code == 401
    assert r.json()["detail"]["codigo"] == "huella_desconocida"
    nueva = _cabecera(cliente, cuenta, "camino largo a casa")
    assert cliente.get("/auth/llaves", headers=nueva).json() == []


def test_el_mismo_telefono_no_se_activa_dos_veces(cliente, sesion):
    tel = Telefono()
    _activar(cliente, sesion, "consultor", tel)
    h = sesion("consultor")
    r = cliente.post("/auth/llaves/alta/opciones", json={"contrasena": CLAVE},
                     headers=h)
    opciones = json.loads(r.json()["opciones"])
    assert [c["id"] for c in opciones["excludeCredentials"]] == [b64(tel.credencial)]
    r = cliente.post("/auth/llaves/alta", headers=h, json={
        "credencial": tel.crear(opciones), "estado": r.json()["estado"]})
    assert r.status_code == 409


def test_cada_quien_ve_y_quita_solo_las_suyas(cliente, sesion):
    tel = Telefono()
    alta = _activar(cliente, sesion, "consultor", tel, nombre="Safari en iPhone")
    mias = cliente.get("/auth/llaves", headers=sesion("consultor")).json()
    assert [(x["id"], x["nombre"]) for x in mias] == [(alta["id"], "Safari en iPhone")]
    assert cliente.get("/auth/llaves", headers=sesion("central")).json() == []

    ajena = cliente.delete(f"/auth/llaves/{alta['id']}", headers=sesion("central"))
    assert ajena.status_code == 404
    r = cliente.delete(f"/auth/llaves/{alta['id']}", headers=sesion("consultor"))
    assert r.status_code == 204
    # Quitada, ya no abre.
    r, _ = _entrar(cliente, tel)
    assert r.status_code == 401


def test_el_sitio_es_el_dominio_de_la_empresa(monkeypatch):
    """La consola y la app de campo comparten las llaves."""
    from app import llaves
    monkeypatch.setattr(llaves.settings, "url_publica", "https://www.mycentauro.lat")
    monkeypatch.setattr(llaves.settings, "dominio_campo", "appep.mycentauro.lat")
    monkeypatch.setattr(llaves.settings, "app_env", "produccion")
    assert llaves.sitio() == "mycentauro.lat"
    assert llaves.origenes() == ["https://mycentauro.lat",
                                 "https://www.mycentauro.lat",
                                 "https://appep.mycentauro.lat"]

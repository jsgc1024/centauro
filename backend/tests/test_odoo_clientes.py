# -*- coding: utf-8 -*-
"""Los clientes, leidos de Odoo (seccion 75).

Tercer paso de la propuesta Puestos y Odoo (Salvador, 26 sep). Contra un
Odoo de mentiras, en memoria: ninguna prueba sale a la red.

Lo que se cuida: es cliente la empresa con la etiqueta «Protección
ejecutiva» (seccion 77); llega de Odoo con su RFC y su pais, sin
tarifario; al que ya estaba se le reconoce por su RFC o por su nombre sin
la razon social, y solo si se parece a uno; sin RFC llega pero se cuenta
aparte; y un cliente de Centauro que no esta en Odoo no se toca.
"""
import uuid

import pytest
from sqlalchemy import text

from app import models as m
from app import odoo_api, odoo_clientes
from app.odoo_clientes_reglas import nombre_llave

ODOO0 = 9_000_000
PREFIJO = "Cliente Odoo"
# Las etiquetas de los contactos en Odoo: la de los clientes de Proteccion
# Ejecutiva y la de los de GPS, que no lo son.
ETIQUETA, GPS = 9_050_001, 9_050_002


class OdooFalso:
    def __init__(self, *partners):
        self.partners = {p["id"]: p for p in partners}
        self.etiquetas = [{"id": ETIQUETA, "name": "Protección ejecutiva"},
                          {"id": GPS, "name": "GPS"}]
        self.dominios = []

    def leer(self, modelo, dominio, campos, archivados=False):
        if modelo == "res.partner.category":
            return [dict(e) for e in self.etiquetas]
        assert modelo == "res.partner"
        self.dominios.append(dominio)
        filas = [p for p in self.partners.values()
                 if archivados or p.get("active", True)]
        for campo, operador, valor in dominio:
            if (campo, operador) == ("id", "in"):
                filas = [p for p in filas if p["id"] in valor]
            elif (campo, operador) == ("is_company", "="):
                filas = [p for p in filas if p.get("is_company", True) == valor]
            elif (campo, operador) == ("category_id", "in"):
                filas = [p for p in filas
                         if set(p.get("category_id") or []) & set(valor)]
            else:
                raise AssertionError((campo, operador))
        return [{"id": p["id"], **{c: p.get(c, False) for c in campos}}
                for p in filas]

    def cambiar(self, n, **valores):
        self.partners[ODOO0 + n].update(valores)

    def archivar(self, n):
        self.cambiar(n, active=False)


def partner(n, **cambios):
    p = {"id": ODOO0 + n, "name": f"{PREFIJO} {n} SA de CV",
         "vat": f"COD{n:06d}AB1", "country_id": [156, "México"],
         "is_company": True, "customer_rank": 1, "category_id": [ETIQUETA],
         "write_date": "2026-09-01 10:00:00", "active": True}
    p.update(cambios)
    return p


@pytest.fixture
def db():
    from app.db import SessionLocal

    sesion = SessionLocal()
    yield sesion
    sesion.close()


@pytest.fixture(autouse=True)
def sin_rastro(base_de_pruebas):
    yield
    with base_de_pruebas.begin() as con:
        con.execute(text("DELETE FROM sincronizacion_odoo"))
        con.execute(text(
            "DELETE FROM cliente WHERE odoo_id >= :o OR nombre LIKE :p"),
            {"o": ODOO0, "p": f"{PREFIJO}%"})


def leer(db, odoo, ensayo=False, **kwargs):
    db.expire_all()
    return odoo_clientes.sincronizar(db, odoo, ensayo=ensayo, **kwargs)


def el_cliente(db, n):
    db.expire_all()
    return db.query(m.Cliente).filter_by(odoo_id=ODOO0 + n).one()


def de_centauro(cliente_http, sesion, nombre, **extra):
    """Un cliente dado de alta a mano en Centauro, como los de hoy."""
    mx = next(p for p in cliente_http.get("/catalogos/paises",
                                          headers=sesion("admin")).json()
              if p["codigo"] == "MX")
    r = cliente_http.post("/catalogos/clientes",
                          json={"nombre": nombre, "pais_id": mx["id"], **extra},
                          headers=sesion("admin"))
    assert r.status_code in (200, 201), r.text
    return r.json()


# ================================================================ la lectura

def test_son_clientes_las_empresas_con_la_etiqueta(db):
    """Los contactos de cada empresa no --esos son los solicitantes-- ni
    las empresas sin la etiqueta: las de GPS y las de carga. La que
    todavia no tiene ventas llega igual, como Volvo."""
    assert odoo_clientes.dominio(7) == [["is_company", "=", True],
                                        ["category_id", "in", [7]]]
    informe = leer(db, OdooFalso(partner(1), partner(2, category_id=[GPS]),
                                 partner(3, customer_rank=0),
                                 partner(4, is_company=False)), ensayo=True)
    assert {a["odoo_id"] for a in informe["altas"]} == {ODOO0 + 1, ODOO0 + 3}


def test_sin_la_etiqueta_en_odoo_no_se_toca_nada(db):
    """Si alguien la borra o le cambia el nombre, no se sabe quien es
    cliente: no se lee a nadie, y la pantalla lo dice."""
    odoo = OdooFalso(partner(1))
    odoo.etiquetas = [{"id": GPS, "name": "GPS"}]
    informe = leer(db, odoo)
    assert informe["sin_etiqueta"] == "Protección ejecutiva"
    assert not informe["altas"] and not informe["bajas"]
    assert db.query(m.SincronizacionOdoo).count() == 0


def test_la_etiqueta_se_reconoce_sin_acentos_ni_mayusculas():
    odoo = OdooFalso()
    odoo.etiquetas = [{"id": 5, "name": "PROTECCION EJECUTIVA "}]
    assert odoo_clientes.etiqueta(odoo) == 5


def test_el_ensayo_no_guarda_nada(db):
    informe = leer(db, OdooFalso(partner(1), partner(2)), ensayo=True)
    assert {a["odoo_id"] for a in informe["altas"]} == {ODOO0 + 1, ODOO0 + 2}
    assert db.query(m.Cliente).filter(m.Cliente.odoo_id >= ODOO0).count() == 0


def test_llega_con_su_rfc_y_sin_tarifario(db):
    informe = leer(db, OdooFalso(partner(1),
                                 partner(2, is_company=False),
                                 partner(3, category_id=[GPS])))
    assert informe["leidos"] == 1
    c = el_cliente(db, 1)
    assert c.rfc == "COD000001AB1"
    assert c.nombre == f"{PREFIJO} 1 SA de CV"
    assert c.tarifario_id is None and c.activo is True
    assert informe["sin_tarifario"] == 1


def test_sin_rfc_llega_pero_se_cuenta_aparte(db):
    informe = leer(db, OdooFalso(partner(1, vat=False)))
    assert el_cliente(db, 1).rfc is None
    assert [x["odoo_id"] for x in informe["sin_rfc"]] == [ODOO0 + 1]


def test_el_pais(db):
    informe = leer(db, OdooFalso(
        partner(1, country_id=[31, "Brazil"], vat="12345678000190"),
        partner(2, country_id=False),                       # RFC mexicano
        partner(3, country_id=False, vat=False),
        partner(4, country_id=[48, "Colombia"])))
    assert el_cliente(db, 1).pais_id != el_cliente(db, 2).pais_id
    assert [x["odoo_id"] for x in informe["pais_por_rfc"]] == [ODOO0 + 2]
    faltas = {p["odoo_id"]: p["falta"] for p in informe["pendientes"]}
    assert faltas[ODOO0 + 3] == ["sin pais"]
    assert faltas[ODOO0 + 4] == ["el pais «Colombia» no existe en Centauro"]


def test_el_nombre_sin_la_razon_social():
    assert nombre_llave("Grupo Gamma, S.A.P.I. de C.V.") == "grupo gamma"
    assert nombre_llave("Servicios X S de RL de CV") == "servicios x"
    assert nombre_llave("Grupo Epsilon Brasil Ltda.") == "grupo epsilon brasil"


def test_a_quien_ya_estaba_se_le_liga(db, cliente, sesion):
    sufijo = uuid.uuid4().hex[:6]
    por_nombre = de_centauro(cliente, sesion, f"{PREFIJO} Gamma {sufijo}")
    por_rfc = de_centauro(cliente, sesion, f"{PREFIJO} Delta {sufijo}",
                          rfc="GDL020202CD2")
    informe = leer(db, OdooFalso(
        partner(1, name=f"{PREFIJO} Gamma {sufijo}, S.A. de C.V."),
        partner(2, name="Delta Logistica", vat="MX GDL020202CD2")))
    ligados = {v["cliente_id"]: v["odoo_id"] for v in informe["vinculadas"]}
    assert ligados == {por_nombre["id"]: ODOO0 + 1, por_rfc["id"]: ODOO0 + 2}
    assert not informe["altas"]
    # Y de ahi en adelante manda Odoo: nombre y RFC.
    c = el_cliente(db, 1)
    assert c.id == por_nombre["id"] and c.rfc == "COD000001AB1"
    assert el_cliente(db, 2).nombre == "Delta Logistica"


def test_si_se_parece_a_dos_no_se_adivina(db, cliente, sesion):
    sufijo = uuid.uuid4().hex[:6]
    de_centauro(cliente, sesion, f"{PREFIJO} Omega {sufijo}")
    de_centauro(cliente, sesion, f"{PREFIJO} Omega {sufijo} SA")
    informe = leer(db, OdooFalso(partner(1, name=f"{PREFIJO} Omega {sufijo} "
                                                 "S.A. de C.V.")), ensayo=True)
    assert informe["pendientes"][0]["falta"] == [
        "se parece a mas de un cliente de Centauro"]


def test_lo_que_cambia_en_odoo_se_pone_al_dia(db):
    odoo = OdooFalso(partner(1))
    leer(db, odoo)
    odoo.cambiar(1, name=f"{PREFIJO} Uno Nuevo", vat="NUE010101AB1")
    informe = leer(db, odoo)
    assert set(informe["cambios"][0]["que"]) == {"nombre", "rfc"}
    assert el_cliente(db, 1).rfc == "NUE010101AB1"


def test_la_baja_no_borra_y_lo_de_centauro_no_se_toca(db, cliente, sesion):
    propio = de_centauro(cliente, sesion, f"{PREFIJO} Brasil {uuid.uuid4().hex[:6]}")
    odoo = OdooFalso(partner(1))
    leer(db, odoo)
    odoo.archivar(1)
    informe = leer(db, odoo)
    assert [b["odoo_id"] for b in informe["bajas"]] == [ODOO0 + 1]
    assert el_cliente(db, 1).activo is False
    db.expire_all()
    assert db.get(m.Cliente, propio["id"]).activo is True


def test_lo_de_odoo_no_se_edita_en_centauro(db, cliente, sesion):
    leer(db, OdooFalso(partner(1)))
    c = el_cliente(db, 1)
    h = sesion("admin")
    r = cliente.patch(f"/catalogos/clientes/{c.id}",
                      json={"nombre": "Otro nombre", "pais_id": c.pais_id},
                      headers=h)
    assert r.status_code == 409, r.text
    # El tarifario si, mientras los tarifarios no se lean de Odoo
    # (seccion 77: desde la primera lectura, lo pone su ficha de Odoo).
    tarifario = cliente.get("/catalogos/tarifarios", headers=h).json()[0]
    r = cliente.patch(f"/catalogos/clientes/{c.id}",
                      json={"nombre": c.nombre, "pais_id": c.pais_id,
                            "tarifario_id": tarifario["id"]}, headers=h)
    assert r.status_code == 200, r.text
    assert el_cliente(db, 1).tarifario_id == tarifario["id"]


def test_el_que_pierde_la_etiqueta_no_se_da_de_baja(db):
    """Quitarle la etiqueta puede ser un descuido: se dice, no se apaga."""
    odoo = OdooFalso(partner(1))
    leer(db, odoo)
    odoo.cambiar(1, category_id=[GPS])
    informe = leer(db, odoo)
    assert not informe["bajas"]
    assert informe["pendientes"][0]["falta"] == [
        "ya no trae la etiqueta de Proteccion Ejecutiva en Odoo"]
    assert el_cliente(db, 1).activo is True


def test_la_de_cada_hora_espera_a_la_primera_a_mano(db):
    odoo = OdooFalso(partner(1))
    assert "omitido" in odoo_clientes.sincronizar_si_toca(db, odoo)
    leer(db, odoo)
    odoo.cambiar(1, name=f"{PREFIJO} Uno Cambiado")
    assert odoo_clientes.sincronizar_si_toca(db, odoo)["cambios"] == 1


def test_las_puertas(cliente, sesion, monkeypatch):
    from app.config import settings

    odoo = OdooFalso(partner(1))
    monkeypatch.setattr(odoo_api, "cliente", lambda: odoo)
    monkeypatch.setattr(settings, "odoo_base", "https://odoo.prueba")
    monkeypatch.setattr(settings, "odoo_api_key", "llave")
    assert cliente.get("/odoo/clientes/ensayo",
                       headers=sesion("admin")).status_code == 200
    assert cliente.get("/odoo/clientes/ensayo",
                       headers=sesion("finanzas")).status_code == 403
    assert cliente.post("/odoo/clientes/sincronizar",
                        headers=sesion("consultor")).status_code == 403
    estado = cliente.get("/odoo/estado", headers=sesion("admin")).json()
    assert estado["clientes"]["primera_hecha"] is False


def test_se_liga_a_mano_al_que_tiene_otro_nombre(db, cliente, sesion):
    """El ensayo dice que clientes de Centauro no encontro; si uno es de
    los que llegan con otro nombre, se le pone su No. Odoo antes de
    aplicar y no se da de alta dos veces."""
    viejo = de_centauro(cliente, sesion, f"{PREFIJO} Viejo {uuid.uuid4().hex[:6]}")
    odoo = OdooFalso(partner(1, name="Nombre Distinto SA de CV"))
    ensayo = leer(db, odoo, ensayo=True)
    assert viejo["id"] in {c["cliente_id"] for c in ensayo["sin_ligar"]}
    assert [a["odoo_id"] for a in ensayo["altas"]] == [ODOO0 + 1]

    r = cliente.patch(f"/catalogos/clientes/{viejo['id']}",
                      json={"nombre": viejo["nombre"], "pais_id": viejo["pais_id"],
                            "odoo_id": ODOO0 + 1}, headers=sesion("admin"))
    assert r.status_code == 200, r.text
    # El siguiente ensayo lo cuenta como lo que es: ligado por primera vez.
    otra_vez = leer(db, odoo, ensayo=True)
    assert [v["cliente_id"] for v in otra_vez["vinculadas"]] == [viejo["id"]]
    assert not otra_vez["altas"]
    assert viejo["id"] not in {c["cliente_id"] for c in otra_vez["sin_ligar"]}

    informe = leer(db, odoo)
    assert not informe["altas"]
    c = el_cliente(db, 1)
    assert c.id == viejo["id"] and c.nombre == "Nombre Distinto SA de CV"


def test_el_ligado_a_mano_se_deshace_hasta_la_primera_lectura(db, cliente, sesion):
    """Un error al escoger en la lista no se queda pegado: mientras no se
    aplique, se deshace. Ya leido de Odoo, el No. Odoo es de Odoo."""
    h = sesion("admin")
    viejo = de_centauro(cliente, sesion, f"{PREFIJO} Error {uuid.uuid4().hex[:6]}")
    odoo = OdooFalso(partner(1, name="El Que Si SA de CV"),
                     partner(2, name="El Que No SA de CV"))

    def ligar(odoo_id):
        return cliente.patch(f"/catalogos/clientes/{viejo['id']}",
                             json={"nombre": viejo["nombre"],
                                   "pais_id": viejo["pais_id"],
                                   "odoo_id": odoo_id}, headers=h)

    assert ligar(ODOO0 + 2).status_code == 200      # el equivocado
    assert ligar(None).status_code == 200           # se deshace
    ensayo = leer(db, odoo, ensayo=True)
    assert viejo["id"] in {c["cliente_id"] for c in ensayo["sin_ligar"]}
    assert len(ensayo["altas"]) == 2

    assert ligar(ODOO0 + 1).status_code == 200      # el bueno
    leer(db, odoo)
    assert el_cliente(db, 1).id == viejo["id"]
    r = ligar(None)
    assert r.status_code == 409, r.text
    assert "odoo_id" in r.json()["detail"]["campos"]

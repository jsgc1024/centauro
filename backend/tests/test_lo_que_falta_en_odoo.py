"""La lista de lo que falta en Odoo (seccion 89).

Para limpiar Odoo con cada area: los cinco ensayos de la pantalla de
Odoo, escritos en la terminal, mas quien del personal no tiene foto. Lee
y no guarda nada: ni aqui ni en Odoo --el cliente de Odoo ni siquiera
sabe escribir--.
"""
import io

import lo_que_falta_en_odoo as lista
from app import models as m
from app import odoo_api
from app.db import SessionLocal

SIN_RFC = {"id": 9_900_001, "name": "Prueba89 Sin RFC SA de CV", "vat": False,
           "country_id": [156, "México"], "is_company": True,
           "customer_rank": 1, "category_id": [1],
           "write_date": "2026-09-01 10:00:00", "active": True}


class OdooDePrueba:
    """Un Odoo con un solo cliente, sin RFC; lo demas, vacio."""

    def leer(self, modelo, dominio, campos, archivados=False, **contexto):
        if modelo == "res.partner.category":
            return [{"id": 1, "name": "Protección ejecutiva"}]
        if modelo == "res.partner":
            return [{"id": SIN_RFC["id"],
                     **{c: SIN_RFC.get(c, False) for c in campos}}]
        return []

    def campos(self, modelo, atributos=None):
        return {}


def _cuantas(tabla) -> int:
    with SessionLocal() as db:
        return db.query(tabla).count()


def test_escribe_cada_area_y_no_guarda_nada(monkeypatch):
    monkeypatch.setattr(odoo_api, "cliente", lambda: OdooDePrueba())
    antes = (_cuantas(m.Cliente), _cuantas(m.SincronizacionOdoo),
             _cuantas(m.Persona))
    salida = io.StringIO()
    assert lista.main(salida) == 0
    texto = salida.getvalue()
    for clave in ("personal", "flota", "oficina", "clientes", "tarifarios",
                  "fotos"):
        assert f"== {clave} |" in texto, clave
    assert "ERROR" not in texto, texto
    assert "== clientes | Los clientes | Finanzas | leidos 1" in texto
    renglones = texto.splitlines()
    i = renglones.index("-- sin_rfc | 1")
    assert "Prueba89 Sin RFC" in renglones[i + 1]
    assert renglones[-1] == "== fin"
    # El ensayo no dio de alta al cliente ni dejo su renglon de lectura.
    assert (_cuantas(m.Cliente), _cuantas(m.SincronizacionOdoo),
            _cuantas(m.Persona)) == antes


def test_sin_la_llave_lo_dice(monkeypatch):
    def sin_llave():
        raise odoo_api.SinConexion("falta la llave")
    monkeypatch.setattr(odoo_api, "cliente", sin_llave)
    salida = io.StringIO()
    assert lista.main(salida) == 1
    assert salida.getvalue().startswith("ALTO:")

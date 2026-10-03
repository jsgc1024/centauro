# -*- coding: utf-8 -*-
"""Seccion 108: el puesto «Gerente de administración».

Salvador (30 sep) pidio el puesto con la recomendacion de Claude: firma
el dinero y la gente sin operar. Aprueba y factura, fija los
tabuladores, autoriza el bono y ve toda la operacion; no deposita, no
arma ni paga el corte, no da accesos y no administra la conexion con
Odoo (lo que si hace con Odoo --listas de precios, productos, tipo de
cambio, prefacturas-- es parte de firmar el dinero; seccion 132). Lo que estas
pruebas cuidan: que el puesto de la propuesta y el de la migracion sean
el mismo, y que quien lo trae pueda lo suyo y nada mas.
"""
import importlib.util
import os

import pytest

from app import puestos_base

MIGRACION = os.path.join(os.path.dirname(__file__), "..", "migrations",
                         "versions",
                         "f0b2d4e6a8c0_puesto_gerente_de_administracion.py")
NOMBRE = "Gerente de administración"


def _puesto():
    return next(p for p in puestos_base.PUESTOS if p["nombre"] == NOMBRE)


def _migracion(archivo=MIGRACION, nombre="m108"):
    spec = importlib.util.spec_from_file_location(nombre, archivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# La seccion 111 le sumo al puesto ver a los freelance (sus costos los
# fija con `catalogos.dinero`); en produccion se lo da su migracion.
MIGRACION_111 = os.path.join(os.path.dirname(MIGRACION),
                             "cd3b659a42f6_freelance_en_connect.py")


def _entrar(cliente, correo):
    r = cliente.post("/auth/token",
                     data={"username": correo, "password": "centauro2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def gerente(cliente, sesion):
    """finanzas@ entra como gerente de administracion; al terminar vuelve
    a entrar con su rol, sin puesto."""
    h = sesion("admin")
    assert cliente.post("/auth/categorias/base", headers=h).status_code == 200
    puestos = {p["nombre"]: p for p in cliente.get("/auth/categorias",
                                                   headers=h).json()}
    usuario = next(u for u in cliente.get("/auth/usuarios", headers=h).json()
                   if u["correo"] == "finanzas@centauro.lat")
    r = cliente.post(f"/auth/usuarios/{usuario['usuario_id']}/categoria",
                     json={"categoria_id": puestos[NOMBRE]["categoria_id"]},
                     headers=h)
    assert r.status_code == 200, r.text
    yield _entrar(cliente, "finanzas@centauro.lat")
    cliente.post(f"/auth/usuarios/{usuario['usuario_id']}/categoria",
                 json={}, headers=h)


def test_la_migracion_y_la_propuesta_dicen_el_mismo_puesto():
    puesto = _puesto()
    migracion = _migracion()
    despues = _migracion(MIGRACION_111, "m111").ACTIVIDADES[NOMBRE]
    assert set(migracion.ACTIVIDADES) | set(despues) == puesto["actividades"]
    assert migracion.PANTALLAS.split(",") == sorted(
        puesto["pantallas"], key=puestos_base.permisos.PANTALLAS.index)
    assert migracion.DESCRIPCION == puesto["descripcion"]
    assert migracion.PUESTOS_ODOO == puesto["puestos_odoo"]
    assert puesto["rol"] == puestos_base.R.FINANZAS
    assert puesto["orden"] == 35 and puesto["area"] == "Administración"


def test_firma_el_dinero_y_no_lo_ejecuta(cliente, sesion, gerente):
    h = gerente
    yo = cliente.get("/auth/yo", headers=h).json()
    assert yo["pantallas"] == ["panorama", "servicios", "implantados", "equipo",
                               "bonos", "encuestas", "calidad", "finanzas",
                               "facturacion", "nomina", "catalogos"]
    # Ve la operacion y el dinero.
    assert cliente.get("/servicios", headers=h).status_code == 200
    assert cliente.get("/panorama", headers=h).status_code == 200
    assert cliente.get("/central/tablero", headers=h).status_code == 403
    # Factura y regresa (cierre.facturar), pero no cierra como consultor.
    assert cliente.post("/cierre/999999/aprobar", headers=h).status_code != 403
    # No deposita ni arma ni paga el corte.
    assert cliente.post("/nomina/calcular", json={}, headers=h).status_code == 403
    assert cliente.post("/nomina/999999/pagar", headers=h).status_code == 403
    # Fija el tabulador (lo que se paga por dia): no es 403.
    assert cliente.put("/nomina/tabulador", json={}, headers=h).status_code != 403
    # Autoriza el bono; no lo paga, no da accesos, no administra Odoo.
    assert cliente.get("/auth/categorias", headers=h).status_code == 403
    assert cliente.post("/auth/categorias/base", headers=h).status_code == 403
    assert cliente.get("/odoo/estado", headers=h).status_code in (403, 404)


def test_no_junta_lo_que_no_vive_en_la_misma_mano():
    puesto = _puesto()
    actividades = puesto["actividades"]
    for a, b in puestos_base.permisos.INCOMPATIBLES:
        assert not ({a, b} <= actividades), (a, b)
    for ejecuta in ("viaticos.transferir", "nomina.calcular", "nomina.pagar",
                    "bonos.pagar", "comisiones.pagar", "accesos.dar",
                    "odoo.administrar", "cierre.cerrar", "servicios.alta",
                    "operacion.corregir"):
        assert ejecuta not in actividades, ejecuta
    for firma in ("cierre.facturar", "nomina.tabulador", "bonos.autorizar",
                  "comisiones.ajustar", "catalogos.dinero", "calidad.ver"):
        assert firma in actividades, firma

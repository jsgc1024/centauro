# -*- coding: utf-8 -*-
"""El cliente, por pais (seccion 125).

Salvador, 2 de octubre: «¿podriamos colocar un filtro de cliente por
pais?». Aprobo la maqueta: una pestana por pais arriba de «Cliente» en la
cotizacion, la propuesta y el tarifario del cliente. La lista trae solo a
los clientes de ese pais; la empresa que todavia no esta en Odoo es del
pais de la pestana --ya no se pregunta aparte--; arranca en el ultimo pais
que se escogio en esa computadora y la que ya existe abre en el suyo.
"""
import pathlib

WEB = pathlib.Path(__file__).parent.parent / "app" / "web"


def _js(nombre: str) -> str:
    return (WEB / nombre).read_text(encoding="utf-8")


def test_las_pestanas_viven_en_un_solo_lugar():
    cat = _js("catalogos.js")
    for nombre in ("clientesDelPais", "paisesDeClientes", "paisDeArranque",
                   "recordarPais", "pestanasDeClientes"):
        assert f"export function {nombre}(" in cat, nombre
    # Lo recordado es una comodidad: si el navegador no deja guardarlo, no
    # truena y arranca en el pais con mas clientes.
    assert cat.count("localStorage") == 2 and cat.count("} catch {") >= 2
    assert "cuantos(b) - cuantos(a)" in cat
    # Con un solo pais no hay pestanas.
    assert "if (paises.length < 2) return null;" in cat


def test_la_cotizacion_y_la_propuesta_van_por_pais():
    for nombre in ("cotizaciones.js", "propuesta.js"):
        js = _js(nombre)
        assert "pestanasDeClientes(cat, e.pais_id, cambiarPais)" in js, nombre
        assert "clientesDelPais(cat, e.pais_id)" in js, nombre
        # La que ya existe abre en su pais; una nueva, en el ultimo escogido.
        assert "if (!e.pais_id) e.pais_id = paisDeArranque(cat);" in js, nombre
        assert "recordarPais(paisId);" in js, nombre
        # El cliente de otro pais se suelta al cambiar de pestana.
        assert "if (c && String(c.pais_id) !== String(paisId)) {" in js, nombre
        # La empresa nueva ya no pregunta el pais aparte: lo dice la pestana.
        assert "selPais" not in js and 't("ctz_pais")' not in js, nombre


def test_el_tarifario_del_cliente_va_por_pais():
    js = _js("tarifarios.js")
    assert "pestanasDeClientes(cat, paisId," in js
    assert "listas.filter(x => x.general && delPais(x))" in js
    assert "clientesDelPais(cat, paisId)" in js


def test_ya_no_queda_la_clave_del_pais_aparte():
    assert "ctz_pais:" not in _js("idioma.js")

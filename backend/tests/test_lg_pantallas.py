"""Logistica, bloque 2 (seccion 151): lo que amarra las piezas.

La migracion dice lo mismo que la semilla y que los puestos de la
propuesta; el menu, las rutas y la lista de pantallas del servidor
conocen Flota LG y Jornada LG; LG Connect se sirve en su ruta y el proxy
la manda a su propia direccion.
"""
import importlib.util
import os
import re

from app import lg_flota, permisos, puestos_base
from app import models as m

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRACION = os.path.join(RAIZ, "migrations", "versions",
                         "e2a4c6b8d0f1_logistica_flota_y_jornada.py")


def _web(nombre):
    return open(os.path.join(RAIZ, "app", "web", nombre), encoding="utf-8").read()


def _migracion():
    spec = importlib.util.spec_from_file_location("migracion_lg_151", MIGRACION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_la_migracion_dice_lo_mismo_que_la_semilla_y_los_puestos():
    mig = _migracion()
    assert mig.LLANTAS == lg_flota.LLANTAS_DE_ARRANQUE
    flota = next(p for p in puestos_base.PUESTOS if p["nombre"] == mig.FLOTA)
    assert flota["rol"] == m.Rol.LOGISTICA
    assert flota["descripcion"] == mig.DESCRIPCION_FLOTA
    assert flota["actividades"] == set(mig.A_FLOTA)
    assert flota["puestos_odoo"] == mig.PUESTOS_ODOO_FLOTA
    assert flota["pantallas"] == ["lg_catalogos", "lg_flota", "lg_jornada"]
    gerencia = next(p for p in puestos_base.PUESTOS if p["nombre"] == mig.GERENCIA)
    assert set(mig.A_GERENCIA) <= gerencia["actividades"]
    calidad = next(p for p in puestos_base.PUESTOS if p["rol"] == m.Rol.SISTEMA_CALIDAD)
    assert set(mig.A_SISTEMA) <= calidad["actividades"]
    assert {"lg_flota", "lg_jornada"} <= set(calidad["pantallas"])
    # La Central ve la jornada; la valida quien corrige hitos, no el
    # monitorista.
    supervisor = next(p for p in puestos_base.PUESTOS if p["nombre"] == "Supervisor de central")
    monitorista = next(p for p in puestos_base.PUESTOS if p["nombre"] == "Monitorista")
    assert {"lg.jornada.ver", "lg.jornada.validar"} <= supervisor["actividades"]
    assert "lg.jornada.ver" in monitorista["actividades"]
    assert "lg.jornada.validar" not in monitorista["actividades"]
    assert "lg_jornada" in supervisor["pantallas"] and "lg_jornada" in monitorista["pantallas"]


def test_quien_trae_cada_actividad_de_logistica():
    R = m.Rol
    assert permisos.roles_de("lg.flota.editar") == {R.ADMIN}
    assert R.LOGISTICA in permisos.roles_de("lg.flota.ver")
    assert R.CENTRAL in permisos.roles_de("lg.jornada.validar")
    assert R.LOGISTICA not in permisos.roles_de("lg.jornada.validar")
    # Nada de Logistica para la operacion de Proteccion Ejecutiva.
    for actividad in ("lg.flota.ver", "lg.jornada.ver", "lg.operadores.editar"):
        assert not {R.CONSULTOR, R.PERSONAL_SEGURIDAD, R.FINANZAS} & permisos.roles_de(actividad)


def test_el_menu_las_rutas_y_las_pantallas():
    menu = _web("menu.js")
    assert 'clave: "lg_flota", necesita: "lg.flota.ver"' in menu
    assert 'clave: "lg_jornada", necesita: "lg.jornada.ver"' in menu
    # Las tres de Logistica, juntas en su grupo y en este orden.
    claves = re.findall(r'clave: "(lg_\w+)"', menu)
    assert claves == ["lg_catalogos", "lg_flota", "lg_jornada"]
    app_js = _web("app.js")
    assert "pantallaLgFlota" in app_js and "lg\\/flota\\/(\\d+)" in app_js
    assert "pantallaLgJornada" in app_js and "lg\\/jornada" in app_js
    assert {"lg_flota", "lg_jornada"} <= set(permisos.PANTALLAS)


def test_lg_connect_se_sirve_en_su_ruta(cliente):
    r = cliente.get("/lgapp/")
    assert r.status_code == 200
    assert "<title>LG Connect</title>" in r.text
    assert '/lgapp/app.js' in r.text and '/app/estilo.css' in r.text
    assert cliente.get("/lgapp/app.js").status_code == 200
    manifiesto = cliente.get("/lgapp/manifiesto.json").json()
    assert manifiesto["scope"] == "/lgapp/" and manifiesto["name"] == "LG Connect"
    # Su propia sesion, en su propia llave del navegador.
    assert '"centauro_lg_token"' in _web("lgapp/app.js")


def test_el_proxy_manda_lg_connect_a_su_direccion():
    caddy = open(os.path.join(RAIZ, "..", "despliegue", "Caddyfile"), encoding="utf-8").read()
    assert "{$DOMINIO} {$DOMINIO_CAMPO} {$DOMINIO_CI} {$DOMINIO_LG} {" in caddy
    assert "redir @lg_raiz /lgapp/ 302" in caddy
    assert "redir @fuera_lg https://{$DOMINIO_LG}{uri} 302" in caddy
    # La raiz de LG Connect va antes que la de campo, que se queda con
    # cualquier direccion que no sea la consola.
    assert caddy.index("@lg_raiz {") < caddy.index("@campo_raiz {")
    assert "/lgapp/sw.js" in caddy
    compose = open(os.path.join(RAIZ, "..", "docker-compose.prod.yml"), encoding="utf-8").read()
    assert "DOMINIO_LG: ${DOMINIO_LG:-}" in compose


def test_la_huella_de_lg_connect_vale_en_su_direccion(monkeypatch):
    from app import llaves
    from app.config import settings
    monkeypatch.setattr(settings, "url_publica", "https://mycentauro.lat")
    monkeypatch.setattr(settings, "dominio_lg", "applg.mycentauro.lat")
    assert "https://applg.mycentauro.lat" in llaves.origenes()
    # Y las llaves se atan al dominio de la casa, que la cubre.
    assert llaves.sitio() == "mycentauro.lat"

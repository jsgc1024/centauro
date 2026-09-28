# -*- coding: utf-8 -*-
"""El arranque (seccion 97): lo que falta para operar todo en Connect y
apagar OVH, revisandose solo.

Pieza 5 de «Para poder operar», decision 6 de Salvador del 28 de
septiembre: vive en el sistema y se revisa solo, como el estado del
sistema.

Lo que aqui se cuida:

  * Trae sus cinco grupos, cada renglon con su estado, lo que dice, de
    quien es y a donde lleva, y las cuentas cuadran. Cada liga lleva a
    una pantalla que existe.
  * El respaldo se confirma a mano, con nombre, queda en la bitacora y
    se puede quitar; lo que se revisa solo no se confirma a mano.
  * El dinero de ejemplo falta, y un cambio lo pone listo con quien lo
    hizo: el tabulador y el bono, que ahora tambien se anota.
  * Lo que sale de la base dice su numero: las fallas por revisar.
  * Lo leen los mismos que leen el manual.
"""
import pytest

from app import models as m
from app.db import SessionLocal
from test_manual import _capitulos, _lleva_a_algo, _paginas_del_manual, \
    _rutas_de_la_consola


def _arranque(cliente, sesion, quien="dirgeneral", idioma="es"):
    r = cliente.get(f"/manual/arranque?idioma={idioma}", headers=sesion(quien))
    assert r.status_code == 200, r.text
    return r.json()


def _renglon(a, clave):
    return next(x for g in a["grupos"] for x in g["renglones"]
                if x["clave"] == clave)


def _existe(liga, capitulos, rutas):
    """Las del manual, por su pagina; las demas, contra las rutas."""
    if liga.startswith("#/manual/") and not liga.startswith("#/manual/leer/"):
        return liga[len("#/manual/"):].split("/")[0] in _paginas_del_manual()
    return _lleva_a_algo(liga, capitulos, rutas)


# ---------------------------------------------------------------- la pagina

def test_los_cinco_grupos_y_sus_cuentas(cliente, sesion):
    a = _arranque(cliente, sesion)
    assert [g["clave"] for g in a["grupos"]] == [
        "servidor", "odoo", "dinero", "gente", "operacion"]
    renglones = [x for g in a["grupos"] for x in g["renglones"]]
    r = a["resumen"]
    assert r["listos"] + r["en_camino"] + r["faltan"] == r["total"] == len(renglones)
    for x in renglones:
        assert x["tono"] in ("ok", "alerta", "grave"), x
        assert x["que"] and x["como"], x
    assert a["fecha"] == "2026-11-02" and isinstance(a["dias"], int)

    rutas, capitulos = _rutas_de_la_consola(), _capitulos("es")
    for x in renglones:
        if x["ir"]:
            assert _existe(x["ir"], capitulos, rutas), x["ir"]
            assert x["donde"], x

    # En portugues tambien; en ingles se lee en espanol, con su aviso.
    assert _arranque(cliente, sesion, idioma="pt")["grupos"][0]["titulo"] == "O servidor"
    en = _arranque(cliente, sesion, idioma="en")
    assert en["en_otro_idioma"] is True
    assert en["grupos"][0]["titulo"] == "El servidor"


@pytest.mark.parametrize("quien,codigo", [
    ("dirgeneral", 200), ("admin", 200), ("diroperaciones", 403),
    ("consultor", 403), ("finanzas", 403)])
def test_lo_leen_los_que_leen_el_manual(cliente, sesion, quien, codigo):
    assert cliente.get("/manual/arranque",
                       headers=sesion(quien)).status_code == codigo


# ---------------------------------------------------------------- a mano

def test_el_respaldo_se_confirma_a_mano_con_nombre(cliente, sesion):
    assert _renglon(_arranque(cliente, sesion), "respaldo")["tono"] == "grave"

    r = cliente.put("/manual/arranque/respaldo/confirmacion",
                    headers=sesion("dirgeneral"))
    assert r.status_code == 200, r.text
    x = _renglon(r.json(), "respaldo")
    assert x["tono"] == "ok" and x["confirmado"] is True
    assert x["como"].startswith("Confirmado a mano por ")
    with SessionLocal() as db:
        assert db.query(m.RegistroAdmin).filter_by(
            objeto="arranque", accion="arranque confirmado").count() == 1
    # Y se lee en la bitacora de administracion, con su nombre.
    filas = cliente.get("/bitacora-admin?que=catalogos",
                        headers=sesion("dirgeneral")).json()["filas"]
    assert any(f["donde"] == "El arranque"
               and f["que"] == "Confirmó a mano: El respaldo y sus alertas"
               for f in filas), filas[:3]

    # Si el respaldo falla, se quita y vuelve a faltar.
    r = cliente.delete("/manual/arranque/respaldo/confirmacion",
                       headers=sesion("dirgeneral"))
    assert r.status_code == 200, r.text
    assert _renglon(r.json(), "respaldo")["tono"] == "grave"

    # Lo que se revisa solo no se confirma a mano.
    r = cliente.put("/manual/arranque/reloj/confirmacion",
                    headers=sesion("dirgeneral"))
    assert r.status_code == 400
    r = cliente.put("/manual/arranque/respaldo/confirmacion",
                    headers=sesion("consultor"))
    assert r.status_code == 403


# ---------------------------------------------------------------- el dinero

def test_el_dinero_de_ejemplo_falta_y_el_cambio_lo_pone_listo(cliente, sesion):
    a = _arranque(cliente, sesion)
    for clave in ("tabulador", "bono", "tipo_cambio"):
        assert _renglon(a, clave)["tono"] == "grave", clave

    do = sesion("diroperaciones")
    fila = cliente.get("/catalogos/tabulador-viaticos", headers=do).json()[0]
    # El bono: cambiar lo que vale un criterio ahora queda en la bitacora.
    with SessionLocal() as db:
        c = (db.query(m.CriterioEstrella)
             .filter_by(codigo=m.CodigoCriterio.CAPACITACION).first())
        criterio = {"id": c.id, "umbral": str(c.umbral_pct),
                    "minutos": c.tolerancia_minutos,
                    "veces": c.tolerancia_ocasiones, "reparte": c.reparte,
                    "monto": c.monto_mensual}
    try:
        cuerpo = {k: v for k, v in fila.items() if k not in ("id", "activo")}
        cuerpo["monto"] = str(float(fila["monto"]) + 25)
        r = cliente.patch(f"/catalogos/tabulador-viaticos/{fila['id']}",
                          json=cuerpo, headers=do)
        assert r.status_code == 200, r.text

        r = cliente.put(f"/criterios/{criterio['id']}", headers=do, json={
            "monto_mensual": "999", "umbral_pct": criterio["umbral"],
            "tolerancia_minutos": criterio["minutos"],
            "tolerancia_ocasiones": criterio["veces"],
            "reparte": criterio["reparte"], "activo": True})
        assert r.status_code == 200, r.text

        a = _arranque(cliente, sesion)
        for clave in ("tabulador", "bono"):
            x = _renglon(a, clave)
            assert x["tono"] == "ok", (clave, x)
            assert x["como"].startswith("Cambiado el ") and " por " in x["como"], x
        with SessionLocal() as db:
            assert db.query(m.RegistroAdmin).filter_by(
                objeto="criterio_estrella").count() == 1
        filas = cliente.get("/bitacora-admin?que=catalogos",
                            headers=sesion("dirgeneral")).json()["filas"]
        bono = next(f for f in filas if f["objeto"] == "criterio_estrella")
        assert bono["donde"] == "Criterios del bono"
        assert "999.00 MXN" in bono["que"], bono["que"]
    finally:
        # El tabulador y los criterios del bono son catalogo: no se vacian
        # entre pruebas, y el que se deja cambiado lo encuentra la
        # siguiente --los alimentos del dia salian en 375 y no en 350--.
        with SessionLocal() as db:
            db.get(m.TabuladorViatico, fila["id"]).monto = fila["monto"]
            db.get(m.CriterioEstrella, criterio["id"]).monto_mensual = criterio["monto"]
            db.commit()


# ---------------------------------------------------------------- la operacion

def test_las_fallas_por_revisar_dicen_cuantas(cliente, sesion):
    assert _renglon(_arranque(cliente, sesion), "fallas")["tono"] == "ok"
    r = cliente.post("/manual/fallas", headers=sesion("consultor"), json={
        "que_paso": "Le di guardar y no paso nada."})
    assert r.status_code == 201, r.text
    x = _renglon(_arranque(cliente, sesion), "fallas")
    assert x["tono"] == "alerta" and x["como"] == "Por revisar: 1."

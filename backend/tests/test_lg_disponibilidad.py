"""Logistica, bloque 2: quien puede salir a un viaje (seccion 151).

Una sola regla para la unidad y otra para el operador, que usan Flota LG,
Jornada LG y, en el bloque 4, la asignacion. Aqui cada bloqueo y cada
alerta con su ejemplo, sin base: las reglas son puras.

Decision de Salvador, 3 oct: un documento o la licencia sin capturar solo
avisan; vencidos, frenan.
"""
from datetime import date, timedelta

import pytest

from app import lg_disponibilidad as d
from app import lg_flota

HOY = date(2026, 10, 5)                  # un lunes
UN_ANO = HOY + timedelta(days=365)


def _unidad(**cambios) -> dict:
    """Una unidad lista para salir: activa, con tipo, libre, con su
    expediente vigente un ano y sin servicio cerca."""
    base = {"activo": True, "clase": "unidad", "tipo_id": 1, "estado": "disponible",
            "estado_hasta": None, "estado_motivo": None,
            "documentos": {t: (UN_ANO, True) for t in lg_flota.DOCUMENTOS},
            "proximos": [{"nombre": "Cambio de aceite", "faltan_km": 8000}],
            "viajes": []}
    return {**base, **cambios}


def _claves(resultado) -> list[tuple]:
    return [(x["nivel"], x["clave"]) for x in resultado["motivos"]]


def test_una_unidad_en_regla_sale():
    r = d.evaluar_unidad(_unidad(), HOY, HOY + timedelta(days=2), 900, HOY)
    assert r == {"estado": "libre", "motivos": []}


@pytest.mark.parametrize("cambio,clave", [
    ({"activo": False}, "baja"),
    ({"clase": "remolque", "tipo_id": None}, "remolque"),
    ({"tipo_id": None}, "sin_tipo"),
    ({"estado": "fuera_de_servicio", "estado_motivo": "motor desvielado"},
     "fuera_de_servicio"),
    ({"estado": "en_taller", "estado_motivo": "frenos"}, "en_taller"),
    ({"estado": "en_viaje"}, "en_viaje"),
    ({"viajes": [{"folio": "LG-0042", "desde": HOY + timedelta(days=1),
                  "hasta": HOY + timedelta(days=3)}]}, "ocupada"),
    ({"proximos": [{"nombre": "Cambio de aceite", "faltan_km": -150}]},
     "servicio_vencido"),
])
def test_lo_que_frena_a_la_unidad(cambio, clave):
    r = d.evaluar_unidad(_unidad(**cambio), HOY, HOY + timedelta(days=2), 500, HOY)
    assert r["estado"] == "bloqueo"
    assert ("bloqueo", clave) in _claves(r)


def test_un_documento_vencido_frena_y_uno_sin_capturar_avisa():
    docs = {t: (UN_ANO, True) for t in lg_flota.DOCUMENTOS}
    docs["poliza_seguro"] = (HOY - timedelta(days=1), True)
    r = d.evaluar_unidad(_unidad(documentos=docs), HOY, HOY, None, HOY)
    assert r["estado"] == "bloqueo"
    assert r["motivos"] == [{"nivel": "bloqueo", "clave": "documento_vencido",
                             "documento": "poliza_seguro",
                             "vence": (HOY - timedelta(days=1)).isoformat()}]
    docs["poliza_seguro"] = (None, False)
    r = d.evaluar_unidad(_unidad(documentos=docs), HOY, HOY, None, HOY)
    assert r["estado"] == "alerta"
    assert _claves(r) == [("alerta", "documento_falta")]
    # Sin vencimiento capturado (la tarjeta de circulacion), vigente.
    docs["poliza_seguro"] = (None, True)
    assert d.evaluar_unidad(_unidad(documentos=docs), HOY, HOY, None, HOY)["estado"] == "libre"


def test_el_documento_que_vence_a_media_viaje_avisa():
    docs = {t: (UN_ANO, True) for t in lg_flota.DOCUMENTOS}
    docs["verificacion"] = (HOY + timedelta(days=2), True)
    r = d.evaluar_unidad(_unidad(documentos=docs), HOY, HOY + timedelta(days=4), None, HOY)
    assert r["estado"] == "alerta"
    assert r["motivos"][0]["clave"] == "documento_vence_en_viaje"
    # El mismo viaje, saliendo despues de que vence: frena.
    r = d.evaluar_unidad(_unidad(documentos=docs), HOY + timedelta(days=3),
                         HOY + timedelta(days=4), None, HOY)
    assert _claves(r) == [("bloqueo", "documento_vencido")]


def test_el_servicio_que_cae_en_los_km_del_viaje_avisa():
    u = _unidad(proximos=[{"nombre": "Frenos", "faltan_km": 1200}])
    assert d.evaluar_unidad(u, HOY, HOY, 900, HOY)["estado"] == "libre"
    r = d.evaluar_unidad(u, HOY, HOY, 1484, HOY)
    assert r["motivos"] == [{"nivel": "alerta", "clave": "servicio_en_viaje",
                             "servicio": "Frenos", "km": 1200}]
    # Sin km del viaje, no se puede saber: no avisa.
    assert d.evaluar_unidad(u, HOY, HOY, None, HOY)["estado"] == "libre"
    # Sin ultimo registrado, tampoco: lo pide la ficha, no el viaje.
    u = _unidad(proximos=[{"nombre": "Frenos", "faltan_km": None}])
    assert d.evaluar_unidad(u, HOY, HOY, 5000, HOY)["estado"] == "libre"


def test_la_que_regresa_del_taller_antes_de_salir_avisa():
    """Se espera de vuelta antes de la salida: alerta. Si ya paso su fecha
    y sigue en el taller, sigue frenada."""
    u = _unidad(estado="en_taller", estado_hasta=HOY + timedelta(days=1),
                estado_motivo="balatas")
    r = d.evaluar_unidad(u, HOY + timedelta(days=2), HOY + timedelta(days=3), None, HOY)
    assert _claves(r) == [("alerta", "en_taller_regresa")]
    # Para hoy no: hoy sigue en el taller.
    assert _claves(d.evaluar_unidad(u, HOY, HOY, None, HOY)) == [("bloqueo", "en_taller")]
    vencida = _unidad(estado="en_taller", estado_hasta=HOY - timedelta(days=1))
    r = d.evaluar_unidad(vencida, HOY + timedelta(days=2), HOY + timedelta(days=2), None, HOY)
    assert _claves(r) == [("bloqueo", "en_taller")]
    viaje = _unidad(estado="en_viaje", estado_hasta=HOY + timedelta(days=1))
    r = d.evaluar_unidad(viaje, HOY + timedelta(days=3), HOY + timedelta(days=3), None, HOY)
    assert _claves(r) == [("alerta", "en_viaje_regresa")]


def test_primero_lo_que_frena():
    docs = {t: (UN_ANO, True) for t in lg_flota.DOCUMENTOS}
    docs["gps"] = (None, False)
    u = _unidad(documentos=docs, estado="fuera_de_servicio", estado_motivo="choque")
    r = d.evaluar_unidad(u, HOY, HOY, None, HOY)
    assert _claves(r) == [("bloqueo", "fuera_de_servicio"), ("alerta", "documento_falta")]


# ====================================================== el operador

def _operador(**cambios) -> dict:
    base = {"activo": True, "licencia": (UN_ANO, True), "en_viaje": [],
            "jornadas": {HOY: "valida"}, "viajes": []}
    return {**base, **cambios}


def test_un_operador_en_regla_sale():
    assert d.evaluar_operador(_operador(), HOY, HOY + timedelta(days=2), HOY) == {
        "estado": "libre", "motivos": []}


@pytest.mark.parametrize("cambio,clave", [
    ({"activo": False}, "baja"),
    ({"en_viaje": [(HOY - timedelta(days=1), HOY + timedelta(days=1))]}, "en_viaje"),
    ({"viajes": [{"folio": "LG-0042", "desde": HOY, "hasta": HOY}]}, "ocupado"),
    ({"licencia": (HOY - timedelta(days=1), True)}, "licencia_vencida"),
    ({"jornadas": {}}, "sin_jornada"),
    ({"jornadas": {HOY: "por_validar"}}, "jornada_por_validar"),
    ({"jornadas": {HOY: "rechazada"}}, "jornada_rechazada"),
])
def test_lo_que_frena_al_operador(cambio, clave):
    r = d.evaluar_operador(_operador(**cambio), HOY, HOY, HOY)
    assert r["estado"] == "bloqueo"
    assert ("bloqueo", clave) in _claves(r)


def test_la_licencia_sin_capturar_o_por_vencer_avisa():
    r = d.evaluar_operador(_operador(licencia=(None, False)), HOY, HOY, HOY)
    assert _claves(r) == [("alerta", "licencia_falta")]
    r = d.evaluar_operador(_operador(licencia=(HOY + timedelta(days=12), True)),
                           HOY, HOY, HOY)
    assert r["motivos"] == [{"nivel": "alerta", "clave": "licencia_por_vencer",
                             "vence": (HOY + timedelta(days=12)).isoformat(), "dias": 12}]
    r = d.evaluar_operador(_operador(licencia=(HOY + timedelta(days=2), True)),
                           HOY, HOY + timedelta(days=4), HOY)
    assert _claves(r) == [("alerta", "licencia_vence_en_viaje")]


def test_la_marca_de_jornada_solo_se_pide_para_hoy():
    """La de manana todavia no existe: un viaje de manana no la pide."""
    r = d.evaluar_operador(_operador(jornadas={}), HOY + timedelta(days=1),
                           HOY + timedelta(days=2), HOY)
    assert r["estado"] == "libre"


def test_el_viaje_a_mano_que_ya_paso_no_frena():
    o = _operador(en_viaje=[(HOY - timedelta(days=5), HOY - timedelta(days=1))])
    assert d.evaluar_operador(o, HOY, HOY, HOY)["estado"] == "libre"
    # Uno que regresa antes de la salida del viaje nuevo tampoco.
    o = _operador(en_viaje=[(HOY, HOY + timedelta(days=1))])
    assert d.evaluar_operador(o, HOY + timedelta(days=3), HOY + timedelta(days=4),
                              HOY)["estado"] == "libre"

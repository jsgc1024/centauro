# -*- coding: utf-8 -*-
"""Lo que Odoo manda de la flota.

Odoo es la fuente de verdad de los empleados y de las unidades: aquí no
se capturan, se reciben. Y de una unidad lo primero que hace falta saber
es **qué es** —una Suburban no es una Sprinter— porque eso es lo que
pregunta quien la va a recibir en un estacionamiento, y es lo que el
task sheet le enseña al ejecutivo.

`marca_modelo` se pedía en el documento que le mandamos a Odoo y **no
estaba en la lista que el endpoint copia**: llegaba y se tiraba. Lo
encontró la prueba 360, por el renglón vacío en tres pantallas.
"""


def _flota(cliente, headers, filas):
    return cliente.post("/odoo/flota", json=filas, headers=headers)


def test_la_marca_y_el_modelo_llegan_de_odoo(cliente, sesion, datos):
    h = sesion("admin")
    unidad = datos["suburban"]

    r = _flota(cliente, h, [{"placa": unidad["placa"],
                             "marca_modelo": "Chevrolet Suburban LT",
                             "color": "Negro", "modelo_anio": 2024}])
    assert r.status_code == 200, r.text

    actualizada = cliente.get(f"/catalogos/vehiculos/{unidad['id']}",
                              headers=h).json()
    assert actualizada["marca_modelo"] == "Chevrolet Suburban LT"
    assert actualizada["color"] == "Negro"
    assert actualizada["modelo_anio"] == 2024


def test_lo_que_odoo_no_manda_no_se_borra(cliente, sesion, datos):
    """Odoo manda lo que tiene. Un campo que no viene no es un campo
    vacío: es un campo del que no dijo nada, y borrarlo sería perder lo
    que ya se sabía."""
    h = sesion("admin")
    unidad = datos["suburban"]
    _flota(cliente, h, [{"placa": unidad["placa"],
                         "marca_modelo": "Chevrolet Tahoe",
                         "color": "Gris"}])

    _flota(cliente, h, [{"placa": unidad["placa"], "color": "Blanco"}])

    actualizada = cliente.get(f"/catalogos/vehiculos/{unidad['id']}",
                              headers=h).json()
    assert actualizada["color"] == "Blanco"
    assert actualizada["marca_modelo"] == "Chevrolet Tahoe"

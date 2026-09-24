# -*- coding: utf-8 -*-
"""El cargador de la hoja que devuelve RH (cargar_hoja_rh.py).

Solo el calculo del plan, contra un Odoo de mentiras: no sale a la red,
no escribe nada y no necesita openpyxl (las filas van ya leidas).
"""
import cargar_hoja_rh as hoja


class OdooFalso:
    def __init__(self, *empleados):
        self.empleados = list(empleados)
        self.contexto = {}

    def leer(self, modelo, dominio, campos, **contexto):
        if modelo == "hr.work.location":
            return [{"id": i, "name": p, "company_id": [1, "Centauro"]}
                    for i, p in enumerate(hoja.PLAZAS, start=1)]
        assert modelo == "hr.employee"
        if dominio:      # la revision de referencias: quien ya tiene una
            return [e for e in self.empleados if e["registration_number"]]
        return self.empleados


def empleado(n):
    return {"id": n, "name": f"Agente {n}", "job_id": False,
            "job_title": "Personal de Seguridad", "company_id": [1, "Centauro"],
            "work_location_id": False, "mobile_phone": False,
            "work_email": False, "private_email": f"agente{n}@correo.lat",
            "registration_number": False}


def fila(n, plaza, nombre=None):
    return {"id": n, "nombre": nombre or f"Agente {n}",
            "work_location_id": plaza, "mobile_phone": None,
            "work_email": None, "private_email": None,
            "registration_number": None, "notas": None}


GDL, MTY = hoja.PLAZAS.index("Guadalajara") + 1, hoja.PLAZAS.index("Monterrey") + 1


def test_una_fila_movida_no_le_quita_su_numero_a_la_fila_buena():
    # Paso con la hoja del 24 de septiembre: un bloque de filas quedo con
    # el No. Odoo de otras personas. La fila movida se salta y la buena,
    # que viene despues con el mismo numero, se toma.
    ops, resumen = hoja.calcular(OdooFalso(empleado(1), empleado(2)), [
        fila(1, "Guadalajara", nombre="Agente 2"),
        fila(1, "Monterrey"),
        fila(2, "Guadalajara")])
    assert {op["id"]: op["valores"] for op in ops} == {
        1: {"work_location_id": MTY}, 2: {"work_location_id": GDL}}
    assert "      1  el nombre de la fila no es el de Odoo" in resumen
    assert not any("dos veces" in renglon for renglon in resumen)


def test_la_misma_persona_dos_veces_solo_cuenta_la_primera():
    ops, resumen = hoja.calcular(OdooFalso(empleado(1)), [
        fila(1, "Monterrey"),
        fila(1, "Guadalajara")])
    assert [op["valores"] for op in ops] == [{"work_location_id": MTY}]
    assert "      1  la persona viene dos veces" in resumen

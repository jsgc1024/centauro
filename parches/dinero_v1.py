"""Paso 5a: las puertas del dinero preguntan por actividad.

La regla de esta mudanza: **los roles de cada actividad son identicos a
los de hoy**. Cambia como se pregunta, no la respuesta. Por eso las 491
pruebas en verde son la prueba de que nada se movio.

Donde se parte un alias en dos --el consultor que asigna dinero y el que
revisa lo gastado-- las dos actividades nacen con los mismos roles, asi
que tampoco cambia nada hoy. Lo que cambia es que manana se pueden dar
por separado, que es de lo que sirve una categoria.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/permisos.py"
s = R.read_text()

VIEJO = '''    "servicios.ver": {
        "descripcion": "Ver los servicios y su avance",
        "roles": {R.CONSULTOR, R.CENTRAL, R.DIRECTOR_OPERACIONES},
    },
}'''
NUEVO = '''    "servicios.ver": {
        "descripcion": "Ver los servicios y su avance",
        "roles": {R.CONSULTOR, R.CENTRAL, R.DIRECTOR_OPERACIONES},
    },

    # ------------------------------------------------------- el dinero
    #
    # Aqui viven las actividades que de verdad se van a repartir en
    # categorias: la diferencia entre el que consulta y el que gasta.
    #
    # Los aliases de los routers se partieron donde el verbo era otro:
    # asignar dinero no es lo mismo que revisar lo que se gasto, y
    # calcular una nomina no es lo mismo que marcarla pagada. Las dos
    # mitades nacen con los mismos roles, asi que hoy no cambia nada;
    # manana se pueden dar por separado.

    "viaticos.ver": {
        "descripcion": "Ver los viaticos de un servicio y quien trae dinero",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES, R.FINANZAS, R.CENTRAL},
    },
    "viaticos.asignar": {
        "descripcion": "Decidir cuanto se le deposita a cada quien y pedirlo "
                       "a finanzas",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "viaticos.cerrar": {
        "descripcion": "Validar o rechazar comprobantes y cerrar el viatico "
                       "de una persona",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "viaticos.transferir": {
        "descripcion": "Confirmar que el dinero salio, y corregir o anular un "
                       "deposito",
        "roles": {R.FINANZAS},
    },
    "viaticos.comprobar": {
        "descripcion": "Subir desde la app el comprobante de lo que se gasto",
        "roles": {R.PERSONAL_SEGURIDAD},
    },
    "viaticos.evidencia": {
        "descripcion": "Ver el comprobante del deposito. El agente solo ve el "
                       "suyo: eso se revisa aparte",
        "roles": {R.FINANZAS, R.DIRECTOR_OPERACIONES, R.DIRECTOR_GENERAL,
                  R.CONSULTOR, R.PERSONAL_SEGURIDAD},
    },

    "cierre.ver": {
        "descripcion": "Ver cotizaciones, el comparativo y la revision previa",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES, R.FINANZAS, R.CENTRAL},
    },
    "cierre.cotizar": {
        "descripcion": "Generar la cotizacion y registrar que el cliente la "
                       "autorizo",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "cierre.cerrar": {
        "descripcion": "Cerrar el servicio, justificar desviaciones y mandarlo "
                       "a facturar",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "cierre.facturar": {
        "descripcion": "Facturar el servicio o regresarlo a operacion",
        "roles": {R.FINANZAS},
    },
    "cierre.rentabilidad": {
        "descripcion": "Ver la utilidad y el margen de un servicio",
        "roles": {R.CONSULTOR, R.FINANZAS, R.DIRECTOR_OPERACIONES,
                  R.DIRECTOR_GENERAL},
    },

    "nomina.ver": {
        "descripcion": "Ver los cortes de nomina y lo que entrara al proximo",
        "roles": {R.FINANZAS, R.CONSULTOR, R.CENTRAL, R.DIRECTOR_OPERACIONES},
    },
    "nomina.tabulador": {
        "descripcion": "Cambiar lo que se paga por dia, por rol y modalidad",
        "roles": {R.FINANZAS, R.DIRECTOR_OPERACIONES},
    },
    "nomina.calcular": {
        "descripcion": "Armar el corte de la semana, descartarlo y registrar "
                       "ajustes",
        "roles": {R.FINANZAS, R.DIRECTOR_OPERACIONES},
    },
    "nomina.pagar": {
        "descripcion": "Marcar el corte como pagado. Es el momento en que sale "
                       "el dinero",
        "roles": {R.FINANZAS, R.DIRECTOR_OPERACIONES},
    },

    "bonos.ver": {
        "descripcion": "Ver incidencias, evaluaciones y el corte del consultor",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES, R.FINANZAS, R.CENTRAL},
    },
    "bonos.incidencia": {
        "descripcion": "Clasificar una incidencia y calcular las estrellas del "
                       "mes",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "bonos.visto_bueno": {
        "descripcion": "Autorizar o descartar una incidencia que quita bono",
        "roles": {R.DIRECTOR_OPERACIONES},
    },
    "bonos.autorizar": {
        "descripcion": "Autorizar el pago del bono del mes",
        "roles": {R.DIRECTOR_OPERACIONES, R.FINANZAS},
    },
    "comisiones.generar": {
        "descripcion": "Generar la comision del consultor de un servicio",
        "roles": {R.FINANZAS, R.DIRECTOR_OPERACIONES},
    },
    "comisiones.ajustar": {
        "descripcion": "Restar del corte siguiente una factura que no se cobro",
        "roles": {R.FINANZAS},
    },
    "comisiones.resolver": {
        "descripcion": "Decidir una comision retenida",
        "roles": {R.DIRECTOR_GENERAL},
    },
}'''
assert s.count(VIEJO) == 1, "no encontre el final de ACTIVIDADES"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("permisos.py: veinte actividades del dinero")

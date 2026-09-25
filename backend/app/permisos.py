"""Actividades del sistema y que rol puede hacer cada una.

La pregunta que se le hace al sistema no es "que rol tiene esta persona"
sino "puede hacer esta actividad". Hoy la respuesta sale de su rol, como
siempre; manana saldra de un panel donde se le dan actividades a cada
colaborador segun lo que realmente hace. Cuando llegue ese panel, lo
unico que cambia es esta tabla: los endpoints ya preguntan por actividad.

Se va llenando pantalla por pantalla. Lo que todavia no esta aqui sigue
funcionando con auth.requiere(...) y sus roles, sin cambio alguno.
"""
from app import models as m

R = m.Rol

# actividad -> roles que la traen de fabrica.
# La descripcion es la que vera el panel de permisos: se escribe pensando
# en quien la va a leer, no en el endpoint.
# Actividades que no pueden vivir en la misma mano.
#
# Autorizar el bono del mes y depositarlo son el unico control que tiene
# ese dinero. La regla estaba escrita solo en el reparto de roles, y eso
# alcanzaba mientras el reparto de accesos lo hiciera un tercero. Desde
# que RRHH reparte los accesos --y RRHH es quien autoriza-- la regla
# tiene que vivir en el codigo: sin esto, la pantalla de accesos le
# permite a quien la abre darse a si mismo lo que le falta.
INCOMPATIBLES: list[tuple[str, str]] = [
    ("bonos.autorizar", "bonos.pagar"),
    # La comision del consultor, igual (seccion 66): quien le da el visto
    # bueno al corte del mes no es quien la transfiere.
    ("comisiones.visto_bueno", "comisiones.pagar"),
]


def choca_con(actividad: str) -> set[str]:
    """Con que no puede convivir esta actividad."""
    contra = set()
    for una, otra in INCOMPATIBLES:
        if actividad == una:
            contra.add(otra)
        elif actividad == otra:
            contra.add(una)
    return contra


ACTIVIDADES: dict[str, dict] = {
    "servicios.alta": {
        "descripcion": "Dar de alta un servicio y dejarlo programado",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "mapas.buscar": {
        "descripcion": "Buscar un punto de encuentro en Google Maps",
        "roles": {R.CONSULTOR, R.CENTRAL, R.DIRECTOR_OPERACIONES},
    },
    "ciudades.alta": {
        "descripcion": "Agregar una ciudad donde se dan servicios",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "solicitantes.ver": {
        "descripcion": "Ver quien puede solicitar servicios de un cliente",
        "roles": {R.CONSULTOR, R.CENTRAL, R.DIRECTOR_OPERACIONES},
    },
    "solicitantes.alta": {
        "descripcion": "Dar de alta a quien solicita servicios",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "solicitantes.editar": {
        "descripcion": "Corregir o dar de baja a quien solicita servicios",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "servicios.ver": {
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
        "roles": {R.CONSULTOR, R.FINANZAS, R.DIRECTOR_OPERACIONES},
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
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES, R.FINANZAS, R.CENTRAL,
                  R.RECURSOS_HUMANOS},
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
        # Finanzas no esta aqui a proposito: quien autoriza el bono no es
        # quien lo deposita. Con las dos actividades en la misma mano, el
        # unico control sobre el bono seria la buena fe. Y esa regla no
        # se queda en la costumbre: vive en INCOMPATIBLES, abajo.
        "roles": {R.RECURSOS_HUMANOS},
    },
    "bonos.pagar": {
        "descripcion": "Registrar el deposito del bono del mes, con su "
                       "referencia y su comprobante",
        "roles": {R.FINANZAS},
    },
    "bonos.configurar": {
        "descripcion": "Fijar cuanto vale cada criterio del bono y que tan "
                       "bien hay que cumplirlo, por pais",
        "roles": {R.DIRECTOR_OPERACIONES, R.DIRECTOR_GENERAL},
    },
    "comisiones.generar": {
        "descripcion": "Generar la comision del consultor de un servicio",
        "roles": {R.FINANZAS, R.DIRECTOR_OPERACIONES},
    },
    "comisiones.ajustar": {
        "descripcion": "Registrar una diferencia en la comision de un "
                       "consultor: una factura que no se cobro o una "
                       "correccion a mano",
        "roles": {R.FINANZAS},
    },
    # El corte mensual de comisiones, en Nominas (seccion 66).
    "comisiones.ver": {
        "descripcion": "Ver el corte de comisiones de los consultores. El "
                       "consultor ve solo el suyo",
        "roles": {R.FINANZAS, R.DIRECTOR_OPERACIONES, R.CONSULTOR},
    },
    "comisiones.visto_bueno": {
        "descripcion": "Dar el visto bueno al corte de comisiones del mes: "
                       "deja fijo lo que se le paga a cada consultor",
        "roles": {R.DIRECTOR_OPERACIONES},
    },
    "comisiones.pagar": {
        "descripcion": "Registrar la transferencia de la comision de cada "
                       "consultor, con su referencia",
        "roles": {R.FINANZAS},
    },
    "comisiones.resolver": {
        "descripcion": "Decidir una comision retenida",
        "roles": {R.DIRECTOR_GENERAL},
    },

    # ------------------------------------------------- la operacion
    #
    # Lo que quedaba preguntando por rol. La mudanza se hizo con una
    # regla: **solo se juntaron puertas que pedian exactamente los
    # mismos roles**. Juntar dos con roles distintos obligaria a que la
    # casilla trajera la union de ambos, y el dia que se aplicara,
    # alguien ganaria acceso que hoy no tiene sin que nadie lo decida.
    #
    # Con esa regla, las cuarenta y tantas puertas cayeron en cinco
    # conjuntos de roles. Por eso esta mudanza no le cambia nada a nadie:
    # cada endpoint sigue pidiendo lo mismo, ahora con nombre.
    #
    # Fuera se quedaron tres a proposito:
    #   la app de campo   el candado de ahi no es un permiso repartible
    #                     sino "es su propia jornada". Como casilla seria
    #                     una que nadie debe marcar nunca, y el dia que
    #                     alguien la marcara le abriria la app a oficina.
    #   leer catalogos    es "todo el que no es de campo". Una casilla
    #                     que nunca se apaga es ruido en la pantalla.
    #   el panel mismo    si repartir permisos se pudiera repartir, quien
    #                     lo tuviera se daria todo lo demas.

    # Hay dos alertas distintas y no se pueden juntar: las de aqui
    # --`Alerta`-- las levanta el sistema solo (un servicio callado, unas
    # horas extra que se vienen) y las mira quien vigila el dia; la de
    # `contingencia` --`AlertaIncidencia`-- la levanta el que esta en la
    # calle, y tomarla es hacerse cargo. Piden roles distintos hoy, asi
    # que juntarlas le daria a alguien algo que no tiene.
    "operacion.ver": {
        "descripcion": "El tablero de la central: el pulso, los proximos, "
                       "los dias sin cerrar y las alertas del sistema",
        "roles": {R.CENTRAL, R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "operacion.atender": {
        "descripcion": "Marcar atendida una alerta que levanto el sistema, "
                       "diciendo como se resolvio",
        "roles": {R.CENTRAL, R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "operacion.planear": {
        "descripcion": "Fijar el punto de encuentro y el vuelo de una jornada",
        "roles": {R.CENTRAL, R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "operacion.corregir": {
        "descripcion": "Ajustar un hito, cerrar a mano una jornada o reabrirla",
        "roles": {R.CENTRAL, R.DIRECTOR_OPERACIONES},
    },
    "contingencia.ver": {
        "descripcion": "Las alertas que levanta el campo y los relevos de un "
                       "servicio",
        "roles": {R.CONSULTOR, R.CENTRAL, R.FINANZAS, R.DIRECTOR_OPERACIONES},
    },
    "contingencia.atender": {
        "descripcion": "Tomar y cerrar una alerta que levanto el campo",
        "roles": {R.CENTRAL, R.DIRECTOR_OPERACIONES},
    },
    # El GPS de las unidades (seccion 60): la flota con su GPS y lo que
    # hay que arreglar. No ensena donde esta ninguna unidad.
    "unidades.ver": {
        "descripcion": "Ver la flota con su GPS: que unidad reporta, cual "
                       "no liga y que trae cada una hoy",
        "roles": {R.CONSULTOR, R.CENTRAL, R.DIRECTOR_OPERACIONES,
                  R.DIRECTOR_GENERAL},
    },
    "relevos.mover": {
        "descripcion": "Relevar personal o unidad, registrar el regreso y "
                       "deshacer un relevo",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },

    # ------------------------------------------------- el task sheet
    #
    # Armar y publicar se partieron porque publicar es lo unico de aqui
    # que sale de la empresa: la hoja publicada es la que ve el cliente.

    "tasksheet.ver": {
        "descripcion": "La hoja publicada, sus versiones y el hospedaje",
        "roles": {R.CONSULTOR, R.CENTRAL, R.FINANZAS, R.DIRECTOR_OPERACIONES},
    },
    "tasksheet.armar": {
        "descripcion": "La agenda del dia, las paradas, el hotel y la senal "
                       "de encuentro",
        "roles": {R.CENTRAL, R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "tasksheet.publicar": {
        "descripcion": "Publicar la hoja que ve el cliente",
        "roles": {R.CENTRAL, R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },

    # ------------------------------------------------- la asignacion
    #
    # El auto subarrendado va solo: es la unica puerta por la que entra
    # un costo de renta a un servicio.

    "asignaciones.ver": {
        "descripcion": "Quien y que trae el equipo, las recomendaciones y la "
                       "auditoria del servicio",
        "roles": {R.CENTRAL, R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "asignaciones.confirmar_a_mano": {
        "descripcion": "Registrar que alguien confirmo por telefono, cuando "
                       "no trae la app. Queda sellado con quien lo registro",
        "roles": {R.CENTRAL, R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "asignaciones.mover": {
        "descripcion": "Asignar y quitar personal y unidades, y decir en que "
                       "unidad va cada quien",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "unidades.subarrendar": {
        "descripcion": "Dar de alta un auto rentado para un equipo",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },

    # ------------------------------------------------- los implantados
    #
    # Las dos ultimas son el "consultor que no decide cuanto dinero se
    # deposita", en la cartera donde mas dinero se mueve.

    "implantado.ver": {
        "descripcion": "La cartera de implantados, el calendario, el mes y "
                       "el acuerdo",
        "roles": {R.CONSULTOR, R.CENTRAL, R.FINANZAS, R.DIRECTOR_OPERACIONES},
    },
    "implantado.armar": {
        "descripcion": "Dar de alta, abrir meses, cubrir dias, cambiar gente "
                       "o unidad, taller y plantilla",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "implantado.tabulador": {
        "descripcion": "Que se paga de viaticos en ese acuerdo",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "implantado.viaticos": {
        "descripcion": "Fijar los depositos del mes, pedirlos a finanzas y "
                       "cancelarlos",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },

    # ------------------------------------- encuestas y profesionalismo
    #
    # Clasificar va aparte de enviar: clasificar una mala calificacion es
    # lo que decide si castiga el profesionalismo de alguien.

    "encuestas.ver": {
        "descripcion": "Las encuestas del servicio y los resumenes por persona",
        "roles": {R.CONSULTOR, R.CENTRAL, R.FINANZAS, R.DIRECTOR_OPERACIONES},
    },
    "encuestas.enviar": {
        "descripcion": "Mandar las encuestas y recuperar el enlace",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "encuestas.clasificar": {
        "descripcion": "Revisar una mala calificacion y decidir si castiga",
        "roles": {R.CONSULTOR, R.DIRECTOR_OPERACIONES},
    },
    "profesionalismo.ver": {
        "descripcion": "El tablero del personal y la ficha de una persona",
        "roles": {R.CONSULTOR, R.CENTRAL, R.DIRECTOR_OPERACIONES},
    },
    "profesionalismo.pesos": {
        "descripcion": "Cuanto pesa cada dimension de la calificacion",
        "roles": {R.ADMIN, R.DIRECTOR_OPERACIONES},
    },
    "panorama.ver": {
        "descripcion": "Todo lo que esta pasando ahora, y las marcas que no "
                       "cuadran",
        "roles": {R.CONSULTOR, R.CENTRAL, R.FINANZAS, R.DIRECTOR_OPERACIONES,
                  R.DIRECTOR_GENERAL},
    },
}


def roles_de(actividad: str) -> set:
    """Los roles que traen esa actividad. Una actividad desconocida no la
    puede nadie: mas vale un 403 visible que una puerta abierta."""
    entrada = ACTIVIDADES.get(actividad)
    return set(entrada["roles"]) if entrada else set()


def catalogo() -> list[dict]:
    """Para el panel de permisos y para la documentacion de la API."""
    return [{"actividad": nombre,
             "descripcion": datos["descripcion"],
             "roles": sorted(r.value for r in datos["roles"])}
            for nombre, datos in sorted(ACTIVIDADES.items())]


def actividades_de_rol(rol) -> set[str]:
    """Lo que trae un rol de fabrica. Es el reverso de `roles_de`, y hace
    falta para saber que puede ya alguien antes de darle algo mas."""
    return {nombre for nombre, datos in ACTIVIDADES.items()
            if rol in datos["roles"]}

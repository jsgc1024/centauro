"""Los puestos de la propuesta del 26 de septiembre (seccion 73).

Salieron de los puestos que Centauro ya tiene en Odoo: monitorista,
facturista, consultor JR, jefe de finanzas, recursos humanos... Cada uno
dice con que rol entra quien lo trae, que pantallas le salen en el menu y
que puede hacer en ellas.

Se arman partiendo de lo que trae su rol de fabrica y quitando o poniendo
lo que ese trabajo no hace o si hace. Asi un puesto nuevo no se queda sin
una actividad que alguien agrego despues al rol --salvo la que se le
quito a proposito--.

Dos quedan fuera a proposito, y entran con su rol:
  * Direccion general, que puede todo: un puesto con todo juntaria las
    actividades que no pueden vivir en la misma mano.
  * Administracion, la llave maestra, que pasa cualquier candado: un
    puesto no le quitaria nada. Desde la seccion 83 se guarda para una
    emergencia tecnica; quien administra el sistema a diario trae su
    puesto.

Estos puestos se crean una sola vez, con el boton de la pantalla de
Accesos o con `crear_puestos` de aqui abajo. Despues se ajustan en la
misma pantalla: lo que se cambie alla no lo vuelve a pisar nadie.
"""
from app import models as m
from app import permisos

R = m.Rol


def _de(rol) -> set[str]:
    return set(permisos.actividades_de_rol(rol))


# Lo que un consultor JR no hace: decidir el dinero y dar el visto bueno.
# Lo prepara todo; eso lo da su consultor titular o direccion de
# operaciones (decision del 26 sep). El tabulador del acuerdo de un
# implantado tambien es dinero: fija cuanto viatico se paga por dia.
NO_JR = {"viaticos.asignar", "viaticos.cerrar", "implantado.viaticos",
         "implantado.tabulador", "cierre.cerrar", "bonos.incidencia",
         "encuestas.clasificar"}

# El monitorista atiende la alerta; corregir un hito es del supervisor.
NO_MONITORISTA = {"operacion.corregir"}

# El jefe de finanzas marca pagado lo que arma nomina, y el tabulador lo
# fija direccion de operaciones.
NO_JEFE_FINANZAS = {"nomina.calcular", "nomina.tabulador"}

PUESTOS: list[dict] = [
    {
        "nombre": "Dirección de operaciones",
        "area": "Dirección",
        "rol": R.DIRECTOR_OPERACIONES,
        "orden": 10,
        "descripcion": "Toda la operación y sus vistos buenos; no mueve dinero.",
        # Sin Codigo: lo que protege ese camino es que quien dicta el
        # codigo reconozca la voz de quien llama (seccion 57).
        "pantallas": ["panorama", "servicios", "implantados", "equipo",
                      "unidades", "bonos", "encuestas", "central",
                      "finanzas", "facturacion", "nomina"],
        "actividades": _de(R.DIRECTOR_OPERACIONES),
        "puestos_odoo": "Director de Operaciones, Director Operativo",
    },
    {
        "nombre": "Consultor de seguridad",
        "area": "Operaciones EP",
        "rol": R.CONSULTOR,
        "orden": 20,
        "descripcion": "Sus servicios, de punta a punta.",
        "pantallas": ["panorama", "servicios", "implantados", "equipo",
                      "unidades", "bonos", "encuestas", "central", "codigo",
                      "nomina"],
        "actividades": _de(R.CONSULTOR),
        "puestos_odoo": "Consultor de Seguridad, Consultor",
    },
    {
        "nombre": "Consultor JR",
        "area": "Operaciones EP",
        "rol": R.CONSULTOR,
        "orden": 21,
        "descripcion": "Prepara el servicio; el dinero y el visto bueno los "
                       "da su consultor titular.",
        "pantallas": ["panorama", "servicios", "implantados", "equipo",
                      "unidades", "bonos", "encuestas", "central", "codigo",
                      "nomina"],
        "actividades": _de(R.CONSULTOR) - NO_JR,
        "puestos_odoo": "Consultor JR, Consultor Jr, Consultor Junior",
    },
    {
        "nombre": "Supervisor de central",
        "area": "Operaciones CI",
        "rol": R.CENTRAL,
        "orden": 30,
        "descripcion": "Monitoreo, código y correcciones con su motivo.",
        "pantallas": ["panorama", "servicios", "implantados", "equipo",
                      "unidades", "bonos", "central", "codigo"],
        "actividades": _de(R.CENTRAL),
        "puestos_odoo": ("Supervisor Analisis, Supervisor Análisis, "
                         "Especialista Monitoreo, Supervisor de Central, "
                         "Jefe de Central"),
    },
    {
        "nombre": "Monitorista",
        "area": "Operaciones CI",
        "rol": R.CENTRAL,
        "orden": 31,
        "descripcion": "Monitoreo y código; no corrige hitos.",
        "pantallas": ["panorama", "servicios", "implantados", "unidades",
                      "central", "codigo"],
        "actividades": _de(R.CENTRAL) - NO_MONITORISTA,
        "puestos_odoo": "Monitorista, Asistente CI, Analista de Monitoreo",
    },
    {
        "nombre": "Jefe de finanzas",
        "area": "Finanzas",
        "rol": R.FINANZAS,
        "orden": 40,
        "descripcion": "Aprueba, factura y paga: nómina, bonos y comisiones.",
        "pantallas": ["panorama", "bonos", "finanzas", "facturacion",
                      "nomina"],
        "actividades": _de(R.FINANZAS) - NO_JEFE_FINANZAS,
        "puestos_odoo": "Jefe de Finanzas, Gerente de Finanzas, "
                        "Director de Finanzas",
    },
    {
        "nombre": "Facturación y cobranza",
        "area": "Finanzas",
        "rol": R.FINANZAS,
        "orden": 41,
        "descripcion": "Aprueba, regresa y factura lo que tiene visto bueno.",
        "pantallas": ["panorama", "facturacion"],
        "actividades": {"panorama.ver", "cierre.ver", "cierre.facturar",
                        "cierre.historial", "viaticos.ver",
                        "viaticos.evidencia"},
        "puestos_odoo": "Facturista, Facturación, Facturacion, Cobranza",
    },
    {
        "nombre": "Tesorería y gastos",
        "area": "Finanzas",
        "rol": R.FINANZAS,
        "orden": 42,
        "descripcion": "Deposita los viáticos y las compras, y cierra las "
                       "devoluciones.",
        "pantallas": ["panorama", "finanzas"],
        "actividades": {"panorama.ver", "viaticos.ver", "viaticos.transferir",
                        "viaticos.evidencia", "contingencia.ver"},
        "puestos_odoo": "Analista de Finanzas, Auxiliar de gastos, "
                        "Tesorería, Tesoreria",
    },
    {
        "nombre": "Nómina",
        "area": "Finanzas",
        "rol": R.FINANZAS,
        "orden": 43,
        "descripcion": "Arma el corte del lunes y las comisiones; no las "
                       "marca pagadas.",
        "pantallas": ["bonos", "nomina"],
        "actividades": {"nomina.ver", "nomina.calcular", "comisiones.generar",
                        "comisiones.ajustar", "comisiones.ver", "bonos.ver"},
        "puestos_odoo": "Nómina, Nomina",
    },
    {
        "nombre": "Recursos Humanos",
        "area": "Recursos Humanos",
        "rol": R.RECURSOS_HUMANOS,
        "orden": 50,
        "descripcion": "Da los accesos y autoriza el bono del mes.",
        "pantallas": ["equipo", "bonos", "accesos"],
        "actividades": {"accesos.dar", "bonos.ver", "bonos.autorizar",
                        "profesionalismo.ver"},
        "puestos_odoo": "Recursos Humanos, Coordinadora de RH, "
                        "Coordinador de RH, Generalista, Analista de RH, "
                        "Analista RH",
    },
    {
        "nombre": "Capacitación",
        "area": "Recursos Humanos",
        "rol": R.RECURSOS_HUMANOS,
        "orden": 51,
        "descripcion": "Consulta al personal, sus certificados y su "
                       "desempeño.",
        "pantallas": ["equipo", "bonos"],
        "actividades": {"profesionalismo.ver", "bonos.ver"},
        "puestos_odoo": "Capacitación, Capacitacion",
    },
    # Seccion 85. Decision de Salvador, 27 sep: la administracion del
    # sistema va junto con calidad, y es el puesto de Aridiai Morales.
    # Administra --accesos junto con recursos humanos, las lecturas de
    # Odoo y los catalogos-- y mide la calidad del servicio; consulta la
    # operacion y no la opera, no mueve dinero y no clasifica nada. Reparte
    # accesos, asi que solo lo arma y lo da direccion general (seccion 83),
    # y no se le sugiere a nadie desde Odoo: se da a mano.
    {
        "nombre": "Administración del sistema y calidad",
        "area": "Sistema y calidad",
        "rol": R.SISTEMA_CALIDAD,
        "orden": 85,
        "descripcion": "Administra el sistema —accesos, Odoo y catálogos— "
                       "y mide la calidad del servicio. No mueve dinero ni "
                       "opera.",
        "pantallas": ["panorama", "servicios", "implantados", "equipo",
                      "unidades", "bonos", "encuestas", "accesos", "odoo"],
        "actividades": _de(R.SISTEMA_CALIDAD),
        "puestos_odoo": None,
    },
]


# Los dos que entran con su rol y sin puesto. No se crean: se ensenan en
# la lista de puestos para que este completa, con cuantos entran asi.
#
# Desde la seccion 83 ya no se le sugieren a nadie de Odoo: los da, a
# mano, solo direccion general. Antes la llave maestra se le sugeria a
# quien en Odoo era desarrollador, y recursos humanos la daba con un
# clic.
POR_ROL: list[dict] = [
    {
        "nombre": "Dirección general",
        "area": "Dirección",
        "rol": R.DIRECTOR_GENERAL,
        "orden": 5,
        "descripcion": "Todo. Entra con su rol, sin puesto.",
        "puestos_odoo": None,
    },
    {
        "nombre": "Administración (llave maestra)",
        "area": "Sistema",
        "rol": R.ADMIN,
        "orden": 90,
        "descripcion": "Pasa todos los candados. Solo para una emergencia "
                       "técnica: nadie entra así a diario.",
        "puestos_odoo": None,
    },
]


def por_rol(db) -> list[dict]:
    """Los de POR_ROL, con cuantas personas entran asi hoy: con ese rol y
    sin puesto."""
    salida = []
    for p in POR_ROL:
        gente = (db.query(m.Usuario)
                 .filter(m.Usuario.rol == p["rol"],
                         m.Usuario.categoria_id.is_(None))
                 .count())
        salida.append({**p, "rol": p["rol"].value, "personas": gente})
    return salida


def de_direccion(nombres) -> list[str]:
    """De esos, los que reparten accesos: esos los crea solo direccion
    general (seccion 83)."""
    from app import accesos

    return [p["nombre"] for p in PUESTOS
            if p["nombre"] in set(nombres) and accesos.REPARTE in p["actividades"]]


def faltan(db) -> list[str]:
    """Los de la propuesta que todavia no existen, por nombre."""
    hay = {n for (n,) in db.query(m.CategoriaAcceso.nombre).all()}
    return [p["nombre"] for p in PUESTOS if p["nombre"] not in hay]


def crear_puestos(db, actor) -> dict:
    """Crea los que falten; los que ya estan no se tocan, aunque alguien
    los haya cambiado --para eso se cambiaron--.

    El que reparte accesos lo crea solo direccion general (seccion 83):
    si quien aprieta el boton no lo es, se crean los demas y ese se dice
    en `de_direccion`, en vez de que el boton falle entero."""
    from app import accesos

    creados, de_direccion = [], []
    por_crear = set(faltan(db))
    for p in PUESTOS:
        if p["nombre"] not in por_crear:
            continue
        if accesos.REPARTE in p["actividades"] and not accesos.es_direccion(actor):
            de_direccion.append(p["nombre"])
            continue
        accesos.crear_categoria(
            db, actor, p["nombre"], sorted(p["actividades"]),
            descripcion=p["descripcion"], rol=p["rol"], area=p["area"],
            pantallas=p["pantallas"], puestos_odoo=p["puestos_odoo"],
            orden=p["orden"])
        creados.append(p["nombre"])
    return {"creados": creados, "de_direccion": de_direccion,
            "ya_estaban": [p["nombre"] for p in PUESTOS
                           if p["nombre"] not in creados
                           and p["nombre"] not in de_direccion]}

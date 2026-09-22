"""Por donde pasa un servicio antes de salir a la calle.

    borrador -> planeado -> asignado -> en_curso -> terminado -> cerrado

El minimo para dejarlo *planeado* es corto a proposito: cliente, quien lo
solicita, el dia con su hora de inicio y el punto donde arranca el
servicio (la direccion, los datos del vuelo, o los dos).

De planeado pasa a *asignado* solo cuando todas sus jornadas ya tienen
personal y unidad. Asi, de un vistazo, se distingue lo que esta programado
pero todavia sin equipo de lo que ya esta listo para salir.

Todo lo demas que el sistema exige mas adelante (la geocerca para los
candados de la app, el task sheet completo) se sigue exigiendo donde toca.
"""
from app import models as m

# Estatus anteriores a la programacion.
ANTES_DE_PROGRAMAR = {
    m.EstatusServicio.BORRADOR,
    m.EstatusServicio.COTIZADO,
    m.EstatusServicio.AUTORIZADO,
}

# Estatus que esta funcion puede mover. Un servicio en curso, terminado o
# cancelado no se toca: ya paso de largo.
PROMOVIBLES = ANTES_DE_PROGRAMAR | {m.EstatusServicio.PLANEADO}


def _jornadas_vivas(servicio: m.Servicio) -> list:
    return [j for eq in servicio.equipos for j in eq.jornadas
            if j.estatus != m.EstatusJornada.CANCELADA]


def _tiene_punto_de_inicio(jornada: m.Jornada) -> bool:
    """La direccion escrita o los datos del vuelo. Cualquiera de las dos
    dice donde empieza el servicio; el vuelo ademas amarra la hora."""
    if jornada.origen_direccion:
        return True
    return bool(jornada.vuelo_numero or jornada.vuelo_aerolinea
                or jornada.vuelo_hora)


def faltantes(servicio: m.Servicio) -> list[str]:
    """Lo que le falta al servicio para quedar planeado, en palabras que el
    consultor pueda leer sin traducir."""
    pendientes = []

    if not servicio.cliente_id:
        pendientes.append("El cliente")
    if not (servicio.solicitante_nombre or "").strip():
        pendientes.append("El nombre de quien solicita el servicio")
    if not (servicio.solicitante_apellidos or "").strip():
        pendientes.append("Los apellidos de quien solicita el servicio")

    # El servicio es para alguien: sin saber a quien se protege no esta
    # planeado. Su correo y su telefono si pueden llegar despues, porque
    # hay clientes que no los dan. Cada equipo cuida a alguien. Con un solo equipo es lo de siempre:
    # se captura arriba y el equipo lo hereda. Con dos o mas, cada uno
    # dice a quien lleva, porque cada uno publica su propia hoja.
    for equipo in servicio.equipos:
        quien = "del servicio" if len(servicio.equipos) == 1 \
            else f"del equipo {equipo.alias}"
        nombre = (equipo.ejecutivo_nombre if equipo.tiene_ejecutivo_propio
                  else servicio.ejecutivo_nombre)
        apellidos = (equipo.ejecutivo_apellidos if equipo.tiene_ejecutivo_propio
                     else servicio.ejecutivo_apellidos)
        if not (nombre or "").strip():
            pendientes.append(f"El nombre del ejecutivo principal {quien}")
        if not (apellidos or "").strip():
            pendientes.append(f"Los apellidos del ejecutivo principal {quien}")
    if not servicio.equipos and not (servicio.ejecutivo_nombre or "").strip():
        pendientes.append("El nombre del ejecutivo principal del servicio")

    jornadas = _jornadas_vivas(servicio)
    if not jornadas:
        pendientes.append("Al menos un dia de servicio con su hora de inicio")
    else:
        primera = min(jornadas, key=lambda j: j.inicio_programado)
        if not _tiene_punto_de_inicio(primera):
            pendientes.append("El punto de inicio: la direccion o los datos del vuelo")

    return pendientes


def faltantes_de_recursos(servicio: m.Servicio) -> list[str]:
    """Los dias que todavia no tienen equipo o unidad. Un dia a la vez:
    'el 07 oct falta la unidad' se entiende; 'faltan recursos' no."""
    pendientes = []
    for jornada in sorted(_jornadas_vivas(servicio), key=lambda j: j.fecha):
        sin = []
        if not jornada.personal:
            sin.append("personal")
        if not jornada.vehiculos:
            sin.append("unidad")
        if sin:
            pendientes.append(f"{jornada.fecha.isoformat()}: falta {' y '.join(sin)}")
    return pendientes


def evaluar(servicio: m.Servicio) -> list[str]:
    """Mueve el servicio hasta donde sus datos alcancen.

    No baja de estatus a nadie: un servicio que ya quedo asignado y al que
    despues le quitan un recurso no regresa solo, porque en la calle ya se
    esta moviendo y el reemplazo es un paso con su propio control. Lo que
    falte se ve en la pantalla.
    """
    if servicio.estatus not in PROMOVIBLES:
        return faltantes(servicio)

    pendientes = faltantes(servicio)
    if pendientes:
        return pendientes

    if servicio.estatus in ANTES_DE_PROGRAMAR:
        servicio.estatus = m.EstatusServicio.PLANEADO

    if (servicio.estatus == m.EstatusServicio.PLANEADO
            and _jornadas_vivas(servicio)
            and not faltantes_de_recursos(servicio)):
        servicio.estatus = m.EstatusServicio.ASIGNADO

    return []


def confirmar_si_todos(jornada: m.Jornada) -> bool:
    """El dia pasa a *confirmada* cuando ya confirmo toda su gente.

    `confirmada` existia en el catalogo de la jornada y no lo escribia
    nadie: cada asignacion guardaba su `confirmado` y el dia se quedaba
    en `planeada` hasta que alguien llegaba al punto. La regla es la
    misma que la de `evaluar` con el servicio: sube cuando ya no falta
    nada, y no baja. Si despues entra un relevo sin confirmar, su renglon
    lo dice; el dia no regresa.

    Cuenta la gente viva del dia --la relevada ya no va--. Un dia sin
    nadie no se confirma solo. Y solo sube desde `planeada`: uno que el
    reloj ya puso proximo a iniciar va mas adelante, no atras.

    Lo llaman los cuatro lugares donde alguien confirma: la app, la
    posicion del "voy en camino", lo dicho por telefono y la central.
    """
    if jornada.estatus != m.EstatusJornada.PLANEADA:
        return False
    vivos = [a for a in jornada.personal if a.persona_id and not a.relevado_en]
    if not vivos or not all(a.confirmado for a in vivos):
        return False
    jornada.estatus = m.EstatusJornada.CONFIRMADA
    return True


def estado(servicio: m.Servicio) -> dict:
    pendientes = faltantes(servicio)
    sin_recursos = faltantes_de_recursos(servicio)
    return {
        "servicio_id": servicio.id,
        "folio": servicio.folio,
        "estatus": servicio.estatus.value,
        "planeado": servicio.estatus not in ANTES_DE_PROGRAMAR,
        "listo": not pendientes,
        "faltantes": pendientes,
        "recursos_completos": not sin_recursos and bool(_jornadas_vivas(servicio)),
        "faltantes_de_recursos": sin_recursos,
    }

"""Chico 3: la unidad tambien regresa.

`regresar()` solo sabia de personas. La unidad que sale del taller no lo
necesitaba porque su `hasta` viene del registro de taller, pero un
cambio de unidad hecho a mano sin fin no tenia con que cerrarse.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/contingencia.py"
s = R.read_text()

# --- 1. quien sale y quien entra, sea persona o unidad ---------------
ANCLA = "def _dinero_trabado(db: Session, equipo_id: int, desde: date, hasta: date,"
AYUDAS = '''def _quienes(r: m.ReemplazoRecurso) -> tuple[int | None, int | None]:
    """El que sale y el que entra, sea persona o unidad."""
    if r.tipo == m.TipoRecurso.PERSONAL:
        return r.sale_persona_id, r.entra_persona_id
    return r.sale_vehiculo_id, r.entra_vehiculo_id


def _asignacion_de(r: m.ReemplazoRecurso):
    """La tabla de asignaciones que le toca y su columna de recurso."""
    if r.tipo == m.TipoRecurso.PERSONAL:
        return m.AsignacionPersonal, m.AsignacionPersonal.persona_id
    return m.AsignacionVehiculo, m.AsignacionVehiculo.vehiculo_id


def _como_se_llama(db: Session, r: m.ReemplazoRecurso,
                   recurso_id: int | None) -> str | None:
    if not recurso_id:
        return None
    if r.tipo == m.TipoRecurso.PERSONAL:
        persona = db.get(m.Persona, recurso_id)
        return persona.nombre if persona else None
    unidad = db.get(m.Vehiculo, recurso_id)
    return unidad.placa if unidad else None


def _se_partio(db: Session, r: m.ReemplazoRecurso, jornada: m.Jornada) -> bool:
    """Si el dia del regreso quedo repartido entre los dos."""
    sale, entra = _quienes(r)
    if r.tipo == m.TipoRecurso.PERSONAL:
        return (db.query(m.AsignacionPersonal.id)
                .filter(m.AsignacionPersonal.jornada_id == jornada.id,
                        m.AsignacionPersonal.persona_id == entra,
                        m.AsignacionPersonal.relevado_por_id == sale,
                        m.AsignacionPersonal.relevado_en.isnot(None))
                .first()) is not None
    return (db.query(m.AsignacionVehiculo.id)
            .filter(m.AsignacionVehiculo.jornada_id == jornada.id,
                    m.AsignacionVehiculo.vehiculo_id == entra,
                    m.AsignacionVehiculo.relevado_por_vehiculo_id == sale,
                    m.AsignacionVehiculo.relevado_en.isnot(None))
            .first()) is not None


def _relevar_al_reves(db: Session, r: m.ReemplazoRecurso, desde: m.Jornada,
                      hasta: m.Jornada | None, sale: int, entra: int,
                      hecho_por_id: int | None,
                      relevado_en: datetime | None) -> dict:
    """El mismo relevo de siempre, con los nombres al reves."""
    motor = (reemplazar_personal if r.tipo == m.TipoRecurso.PERSONAL
             else reemplazar_vehiculo)
    llaves = ({"sale_persona_id": sale, "entra_persona_id": entra}
              if r.tipo == m.TipoRecurso.PERSONAL
              else {"sale_vehiculo_id": sale, "entra_vehiculo_id": entra})
    return motor(db, desde_jornada_id=desde.id, motivo=r.motivo,
                 hecho_por_id=hecho_por_id, motivo_tipo=r.motivo_tipo,
                 hasta_jornada_id=hasta.id if hasta else None,
                 relevado_en=relevado_en, **llaves)


def _dinero_trabado(db: Session, equipo_id: int, desde: date, hasta: date,'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, AYUDAS)

# --- 2. regresar(): deja pasar la unidad ----------------------------
VIEJO = '''    if r.tipo != m.TipoRecurso.PERSONAL:
        raise HTTPException(409, "Por ahora solo regresa el personal")
'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, "")

VIEJO = '''    hecho = reemplazar_personal(
        db, desde_jornada_id=vuelve.id,
        sale_persona_id=r.entra_persona_id,
        entra_persona_id=r.sale_persona_id,
        motivo=r.motivo, hecho_por_id=hecho_por_id,
        motivo_tipo=r.motivo_tipo, hasta_jornada_id=r.hasta_jornada_id,
        relevado_en=relevado_en)
    return _firmar_el_cierre(db, r, arranco, vuelve, hecho, hecho_por_id)'''
NUEVO = '''    titular, cubre = _quienes(r)
    hecho = _relevar_al_reves(db, r, vuelve, fin, cubre, titular,
                              hecho_por_id, relevado_en)
    return _firmar_el_cierre(db, r, arranco, vuelve, hecho, hecho_por_id)'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# --- 3. _mover_el_regreso: los dos recursos -------------------------
VIEJO = '''    # Si el dia del regreso se partio, ese dia ya esta repartido entre los
    # dos y tiene su hora. Moverlo seria rehacer una nomina.
    partido = (db.query(m.AsignacionPersonal.id)
               .filter(m.AsignacionPersonal.jornada_id == fin.id,
                       m.AsignacionPersonal.persona_id == r.entra_persona_id,
                       m.AsignacionPersonal.relevado_por_id == r.sale_persona_id,
                       m.AsignacionPersonal.relevado_en.isnot(None))
               .first())
    if partido:'''
NUEVO = '''    # Si el dia del regreso se partio, ese dia ya esta repartido entre los
    # dos y tiene su hora. Moverlo seria rehacer una nomina.
    if _se_partio(db, r, fin):'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    gente = [r.sale_persona_id, r.entra_persona_id]
    if vuelve.fecha > vuelve_hoy.fecha:'''
NUEVO = '''    titular, cubre = _quienes(r)
    if vuelve.fecha > vuelve_hoy.fecha:'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''        _no_pasarse_del_tope(arranco, hasta)
        trabados = _dinero_trabado(db, arranco.equipo_id, vuelve_hoy.fecha,
                                   hasta.fecha, gente)
        _no_con_dinero(trabados)
        hecho = reemplazar_personal(
            db, desde_jornada_id=vuelve_hoy.id,
            sale_persona_id=r.sale_persona_id,
            entra_persona_id=r.entra_persona_id,
            motivo=r.motivo, hecho_por_id=hecho_por_id,
            motivo_tipo=r.motivo_tipo, hasta_jornada_id=hasta.id,
            relevado_en=relevado_en)'''
NUEVO = '''        _no_pasarse_del_tope(arranco, hasta)
        _no_con_dinero(_dinero_trabado(db, r, arranco.equipo_id,
                                       vuelve_hoy.fecha, hasta.fecha))
        hecho = _relevar_al_reves(db, r, vuelve_hoy, hasta, titular, cubre,
                                  hecho_por_id, relevado_en)'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    # Se adelanta: el titular se lleva unos dias mas.
    trabados = _dinero_trabado(db, arranco.equipo_id, vuelve.fecha,
                               fin.fecha, gente)
    _no_con_dinero(trabados)
    hecho = reemplazar_personal(
        db, desde_jornada_id=vuelve.id,
        sale_persona_id=r.entra_persona_id,
        entra_persona_id=r.sale_persona_id,
        motivo=r.motivo, hecho_por_id=hecho_por_id,
        motivo_tipo=r.motivo_tipo, hasta_jornada_id=fin.id,
        relevado_en=relevado_en)'''
NUEVO = '''    # Se adelanta: el titular se lleva unos dias mas.
    _no_con_dinero(_dinero_trabado(db, r, arranco.equipo_id, vuelve.fecha,
                                   fin.fecha))
    hecho = _relevar_al_reves(db, r, vuelve, fin, cubre, titular,
                              hecho_por_id, relevado_en)'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# --- 4. el candado del dinero es de personas ------------------------
VIEJO = '''def _dinero_trabado(db: Session, equipo_id: int, desde: date, hasta: date,
                    personas: list[int]) -> list[m.AsignacionViatico]:
    """Los viaticos de ese tramo que ya no se pueden desandar.

    El mismo candado que usa `deshacer`: en cuanto alguien pidio el
    dinero o lo transfirio, el movimiento dejo de vivir solo en una
    tabla. Hay una solicitud, una transferencia y un plazo corriendo.
    """
    tocados'''
NUEVO = '''def _dinero_trabado(db: Session, r: m.ReemplazoRecurso, equipo_id: int,
                    desde: date, hasta: date) -> list[m.AsignacionViatico]:
    """Los viaticos de ese tramo que ya no se pueden desandar.

    El mismo candado que usa `deshacer`: en cuanto alguien pidio el
    dinero o lo transfirio, el movimiento dejo de vivir solo en una
    tabla. Hay una solicitud, una transferencia y un plazo corriendo.

    La unidad no mueve viaticos: el combustible y las casetas siguen
    siendo del conductor, que es el mismo.
    """
    if r.tipo != m.TipoRecurso.PERSONAL:
        return []
    personas = [r.sale_persona_id, r.entra_persona_id]
    tocados'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# --- 5. el cierre cuenta lo que toque -------------------------------
VIEJO = '''    cubiertos = (db.query(m.AsignacionPersonal.id)
                 .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
                 .filter(m.Jornada.equipo_id == arranco.equipo_id,
                         m.Jornada.fecha >= arranco.fecha,
                         m.Jornada.fecha <= ultimo.fecha,
                         m.AsignacionPersonal.persona_id == r.entra_persona_id)
                 .count())'''
NUEVO = '''    tabla, columna = _asignacion_de(r)
    _, cubre = _quienes(r)
    cubiertos = (db.query(tabla.id)
                 .join(m.Jornada, tabla.jornada_id == m.Jornada.id)
                 .filter(m.Jornada.equipo_id == arranco.equipo_id,
                         m.Jornada.fecha >= arranco.fecha,
                         m.Jornada.fecha <= ultimo.fecha,
                         columna == cubre)
                 .count())'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    titular = db.get(m.Persona, r.sale_persona_id)
    cubrio = db.get(m.Persona, r.entra_persona_id)
    return {
        "cerrado": r.id,
        "servicio_id": r.servicio_id,
        "regresa": titular.nombre if titular else None,
        "sale": cubrio.nombre if cubrio else None,'''
NUEVO = '''    sale_id, _ = _quienes(r)
    return {
        "cerrado": r.id,
        "servicio_id": r.servicio_id,
        "tipo": r.tipo.value,
        "regresa": _como_se_llama(db, r, sale_id),
        "sale": _como_se_llama(db, r, cubre),'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

R.write_text(s)
print("contingencia.py: la unidad tambien regresa")

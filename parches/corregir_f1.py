"""Entrega 4: mover un regreso ya capturado.

Juan dijo que volvia el 25, el consultor lo capturo, y el 24 avisa que
mejor el 28. El movimiento no se duplica: se recorre otra vez y se
vuelve a firmar. El candado es el del dinero, el mismo que ya usa
`deshacer`.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/contingencia.py"
s = R.read_text()

# ---- 1. el cuerpo de regresar se parte en dos ------------------------
VIEJO = '''    if r.regreso_en:
        raise HTTPException(409, {
            "mensaje": "Ese cambio ya se cerro con un regreso.",
            "regreso_en": r.regreso_en.isoformat()})

    arranco = db.get(m.Jornada, r.desde_jornada_id)'''
NUEVO = '''    arranco = db.get(m.Jornada, r.desde_jornada_id)'''
assert s.count(VIEJO) == 1, "no encontre el candado del regreso"
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    vuelve = (db.query(m.Jornada)
              .filter(m.Jornada.equipo_id == arranco.equipo_id,
                      m.Jornada.fecha >= desde,
                      m.Jornada.estatus.notin_([m.EstatusJornada.CANCELADA,
                                                m.EstatusJornada.TERMINADA]))
              .order_by(m.Jornada.fecha).first())
    if not vuelve:
        raise HTTPException(409, "No hay dias abiertos de ese dia en adelante")

    fin = db.get(m.Jornada, r.hasta_jornada_id) if r.hasta_jornada_id else None
    if fin and vuelve.fecha > fin.fecha:
        raise HTTPException(409, {
            "mensaje": ("Ese cambio ya termino por su cuenta: no hay nada "
                        "que cerrar."),
            "termino": fin.fecha.isoformat()})

    hecho = reemplazar_personal(
        db, desde_jornada_id=vuelve.id,
        sale_persona_id=r.entra_persona_id,
        entra_persona_id=r.sale_persona_id,
        motivo=r.motivo, hecho_por_id=hecho_por_id,
        motivo_tipo=r.motivo_tipo, hasta_jornada_id=r.hasta_jornada_id,
        relevado_en=relevado_en)

    partidas = hecho["jornadas_partidas"]
    nuevo = db.get(m.ReemplazoRecurso, hecho["reemplazo_id"])
    if nuevo:
        db.delete(nuevo)

    # Hasta que dia se queda el que cubrio. Si el dia del regreso se
    # partio, ese dia todavia lo trabajo el: cuenta como suyo.
    if vuelve.fecha.isoformat() in partidas:
        ultimo = vuelve
    else:
        ultimo = (db.query(m.Jornada)
                  .filter(m.Jornada.equipo_id == arranco.equipo_id,
                          m.Jornada.fecha >= arranco.fecha,
                          m.Jornada.fecha < vuelve.fecha,
                          m.Jornada.estatus != m.EstatusJornada.CANCELADA)
                  .order_by(m.Jornada.fecha.desc()).first()) or arranco

    # Los dias se recuentan mirando las asignaciones, no restando: un
    # dia partido sigue siendo suyo y una jornada cancelada en medio no
    # lo era.
    cubiertos = (db.query(m.AsignacionPersonal.id)
                 .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
                 .filter(m.Jornada.equipo_id == arranco.equipo_id,
                         m.Jornada.fecha >= arranco.fecha,
                         m.Jornada.fecha <= ultimo.fecha,
                         m.AsignacionPersonal.persona_id == r.entra_persona_id)
                 .count())

    r.hasta_jornada_id = ultimo.id
    r.jornadas_afectadas = cubiertos
    r.regreso_en = reloj.ahora_de_la_jornada(db, vuelve)
    r.regreso_por_id = hecho_por_id
    db.flush()

    titular = db.get(m.Persona, r.sale_persona_id)
    cubrio = db.get(m.Persona, r.entra_persona_id)
    return {
        "cerrado": r.id,
        "servicio_id": r.servicio_id,
        "regresa": titular.nombre if titular else None,
        "sale": cubrio.nombre if cubrio else None,
        "desde": arranco.fecha.isoformat(),
        "hasta": ultimo.fecha.isoformat(),
        "dias_cubiertos": cubiertos,
        "jornadas_devueltas": hecho["jornadas_afectadas"],
        # Si el que cubria alcanzo a trabajar la manana del dia del
        # regreso, ese dia lo cobran los dos.
        "jornadas_partidas": partidas,
        "jornadas_con_choque": hecho["jornadas_con_choque"],
        # La hora que el sistema propone para partir ese dia: la ultima
        # marca del que cubria. El consultor la confirma o la corrige.
        "hora_propuesta": hecho.get("hora_propuesta"),
        "viaticos": hecho["viaticos"],
    }'''

NUEVO = '''    vuelve = _primer_dia_abierto(db, arranco.equipo_id, desde)
    if not vuelve:
        raise HTTPException(409, "No hay dias abiertos de ese dia en adelante")

    if r.regreso_en:
        return _mover_el_regreso(db, r, arranco, vuelve, hecho_por_id,
                                 relevado_en)

    fin = db.get(m.Jornada, r.hasta_jornada_id) if r.hasta_jornada_id else None
    if fin and vuelve.fecha > fin.fecha:
        raise HTTPException(409, {
            "mensaje": ("Ese cambio ya termino por su cuenta: no hay nada "
                        "que cerrar."),
            "termino": fin.fecha.isoformat()})

    hecho = reemplazar_personal(
        db, desde_jornada_id=vuelve.id,
        sale_persona_id=r.entra_persona_id,
        entra_persona_id=r.sale_persona_id,
        motivo=r.motivo, hecho_por_id=hecho_por_id,
        motivo_tipo=r.motivo_tipo, hasta_jornada_id=r.hasta_jornada_id,
        relevado_en=relevado_en)
    return _firmar_el_cierre(db, r, arranco, vuelve, hecho, hecho_por_id)


def _primer_dia_abierto(db: Session, equipo_id: int,
                        desde: date) -> m.Jornada | None:
    """El primer dia que todavia se puede mover, de esa fecha en adelante.

    El consultor dice "vuelve el sabado" y el sabado no hay jornada: su
    primer dia es el lunes. Traducirlo aqui evita que el calendario de la
    pantalla tenga que saber que dias opera cada servicio.
    """
    return (db.query(m.Jornada)
            .filter(m.Jornada.equipo_id == equipo_id,
                    m.Jornada.fecha >= desde,
                    m.Jornada.estatus.notin_([m.EstatusJornada.CANCELADA,
                                              m.EstatusJornada.TERMINADA]))
            .order_by(m.Jornada.fecha).first())


def _firmar_el_cierre(db: Session, r: m.ReemplazoRecurso, arranco: m.Jornada,
                      vuelve: m.Jornada, hecho: dict,
                      hecho_por_id: int | None) -> dict:
    """Recorre el `hasta` del movimiento y lo firma.

    El relevo que acaba de correr abrio su propio movimiento; ese se
    borra aqui, porque el hecho es el cierre del primero y no otro
    cambio.
    """
    partidas = hecho["jornadas_partidas"]
    nuevo = db.get(m.ReemplazoRecurso, hecho["reemplazo_id"])
    if nuevo:
        db.delete(nuevo)

    # Hasta que dia se queda el que cubrio. Si el dia del regreso se
    # partio, ese dia todavia lo trabajo el: cuenta como suyo.
    if vuelve.fecha.isoformat() in partidas:
        ultimo = vuelve
    else:
        ultimo = (db.query(m.Jornada)
                  .filter(m.Jornada.equipo_id == arranco.equipo_id,
                          m.Jornada.fecha >= arranco.fecha,
                          m.Jornada.fecha < vuelve.fecha,
                          m.Jornada.estatus != m.EstatusJornada.CANCELADA)
                  .order_by(m.Jornada.fecha.desc()).first()) or arranco

    # Los dias se recuentan mirando las asignaciones, no restando: un
    # dia partido sigue siendo suyo y una jornada cancelada en medio no
    # lo era.
    cubiertos = (db.query(m.AsignacionPersonal.id)
                 .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
                 .filter(m.Jornada.equipo_id == arranco.equipo_id,
                         m.Jornada.fecha >= arranco.fecha,
                         m.Jornada.fecha <= ultimo.fecha,
                         m.AsignacionPersonal.persona_id == r.entra_persona_id)
                 .count())

    r.hasta_jornada_id = ultimo.id
    r.jornadas_afectadas = cubiertos
    r.regreso_en = reloj.ahora_de_la_jornada(db, vuelve)
    r.regreso_por_id = hecho_por_id
    db.flush()

    titular = db.get(m.Persona, r.sale_persona_id)
    cubrio = db.get(m.Persona, r.entra_persona_id)
    return {
        "cerrado": r.id,
        "servicio_id": r.servicio_id,
        "regresa": titular.nombre if titular else None,
        "sale": cubrio.nombre if cubrio else None,
        "desde": arranco.fecha.isoformat(),
        "hasta": ultimo.fecha.isoformat(),
        "dias_cubiertos": cubiertos,
        "jornadas_devueltas": hecho["jornadas_afectadas"],
        # Si el que cubria alcanzo a trabajar la manana del dia del
        # regreso, ese dia lo cobran los dos.
        "jornadas_partidas": partidas,
        "jornadas_con_choque": hecho["jornadas_con_choque"],
        # La hora que el sistema propone para partir ese dia: la ultima
        # marca del que cubria. El consultor la confirma o la corrige.
        "hora_propuesta": hecho.get("hora_propuesta"),
        "viaticos": hecho["viaticos"],
    }'''
assert s.count(VIEJO) == 1, "no encontre el cuerpo de regresar"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("contingencia.py: regresar() partido en piezas reusables")

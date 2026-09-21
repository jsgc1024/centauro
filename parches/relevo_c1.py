"""Paso C: el regreso cierra el movimiento, no abre otro."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- modelo ----------------------------------------------------------
R = RAIZ / "backend/app/models.py"
s = R.read_text()
VIEJO = """    jornadas_afectadas: Mapped[int] = mapped_column(Integer, default=0)
    hecho_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
"""
NUEVO = """    jornadas_afectadas: Mapped[int] = mapped_column(Integer, default=0)
    hecho_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    # Cuando el titular volvio. El regreso no abre otro movimiento: recorre
    # el `hasta` de este y lo firma, para que el mes lea "Luis cubrio a
    # Marta del 10 al 24" y no dos cambios cruzados que nadie sabe cual
    # cierra a cual.
    regreso_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    regreso_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("persona.id"), nullable=True)
"""
assert s.count(VIEJO) == 1, "no encontre el final de ReemplazoRecurso"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("models.py: regreso_en y regreso_por_id")

# --- motor -----------------------------------------------------------
R = RAIZ / "backend/app/contingencia.py"
s = R.read_text()
assert s.count("from datetime import datetime\n") == 1
s = s.replace("from datetime import datetime\n", "from datetime import date, datetime\n")

MOTOR = '''

# ==================================================================
# El regreso: el titular vuelve
# ==================================================================

def regresar(db: Session, reemplazo_id: int, desde: date,
             hecho_por_id: int | None = None,
             relevado_en: datetime | None = None) -> dict:
    """El titular vuelve. Cierra el movimiento, no abre otro.

    Marta se enferma el 10 y Luis la cubre. Marta se recupera, avisa al
    consultor y regresa el 25; Luis trabaja hasta el 24 por orden del
    consultor. Eso es un solo hecho —"Luis cubrio a Marta del 10 al
    24"— y asi tiene que leerse en el historial y en el corte del mes.
    Si el regreso abriera su propio movimiento, el mismo mes mostraria
    dos cambios cruzados y nadie sabria cual cierra a cual.

    El regreso no pide motivo: el motivo es el del movimiento que cierra.
    Lo que si queda es quien lo ordeno y cuando.

    Por dentro es el mismo relevo de siempre, con los nombres al reves,
    asi que si Luis alcanzo a trabajar la manana del 25 ese dia se parte
    y los dos cobran su parte. El movimiento que ese relevo abre se borra
    aqui mismo: el hecho es el cierre del primero.
    """
    r = db.get(m.ReemplazoRecurso, reemplazo_id)
    if not r:
        raise HTTPException(404, f"No existe el cambio {reemplazo_id}")
    if r.tipo != m.TipoRecurso.PERSONAL:
        raise HTTPException(409, "Por ahora solo regresa el personal")
    if r.regreso_en:
        raise HTTPException(409, {
            "mensaje": "Ese cambio ya se cerro con un regreso.",
            "regreso_en": r.regreso_en.isoformat()})

    arranco = db.get(m.Jornada, r.desde_jornada_id)
    if not arranco:
        raise HTTPException(404, "El cambio apunta a un dia que ya no existe")
    if desde <= arranco.fecha:
        raise HTTPException(409, {
            "mensaje": ("El regreso tiene que caer despues del dia en que "
                        "arranco el cambio. Si fue un error, se deshace."),
            "arranco": arranco.fecha.isoformat()})

    vuelve = (db.query(m.Jornada)
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
        "dias_devueltos": hecho["jornadas_afectadas"],
        # Si el que cubria alcanzo a trabajar la manana del dia del
        # regreso, ese dia lo cobran los dos.
        "dias_partidos": partidas,
        "dias_con_choque": hecho["jornadas_con_choque"],
        "viaticos": hecho["viaticos"],
    }
'''

MARCA = '''

# ==================================================================
# Antes de guardar: decir en voz alta lo que va a pasar
# =================================================================='''
assert s.count(MARCA) == 1
s = s.replace(MARCA, MOTOR + MARCA)
R.write_text(s)
print("contingencia.py: regresar()")

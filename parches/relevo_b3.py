"""Paso B3: las dos pantallas que leen relevos leen las dos tablas.

Hay dos tablas guardando el mismo hecho: `reemplazo`, la vieja del
implantado, y `reemplazo_recurso`, la del motor de relevo. Los cambios
nuevos caen en la segunda. Si las pantallas siguieran leyendo solo la
primera, el historial viejo se veria y el nuevo no.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- resumen del mes -------------------------------------------------
R = RAIZ / "backend/app/implantado.py"
s = R.read_text()

VIEJO = """    reemplazos = (db.query(m.Reemplazo)
                  .join(m.Jornada, m.Reemplazo.jornada_id == m.Jornada.id)
                  .filter(m.Jornada.equipo_id == equipo.id).all() if equipo else [])
"""
NUEVO = """    reemplazos = _cambios_de_personal(db, vivas)
"""
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJA_SALIDA = """        "reemplazos": [{
            "fecha": r.jornada.fecha.isoformat(), "sale": r.sale.nombre,
            "entra": r.entra.nombre, "motivo": r.motivo.value, "nota": r.nota,
        } for r in reemplazos],
        "total_reemplazos": len(reemplazos),"""
NUEVA_SALIDA = """        "reemplazos": reemplazos,
        "total_reemplazos": len(reemplazos),"""
assert s.count(VIEJA_SALIDA) == 1
s = s.replace(VIEJA_SALIDA, NUEVA_SALIDA)

AYUDA = '''def _cambios_de_personal(db: Session, jornadas: list) -> list[dict]:
    """Quien cubrio a quien en el mes, de las dos tablas.

    La vieja guarda un dia suelto y la nueva un tramo, asi que las dos se
    dicen igual: desde, hasta y cuantos dias. Un cambio de un dia tiene
    desde igual a hasta.

    Los dias partidos van aparte porque son los que explican por que el
    mismo dia aparece dos veces en la nomina: ese dia lo trabajaron dos
    personas y las dos cobran su parte.
    """
    if not jornadas:
        return []
    ids = [j.id for j in jornadas]
    fecha_de = {j.id: j.fecha for j in jornadas}
    salida = []

    for r in (db.query(m.Reemplazo)
              .filter(m.Reemplazo.jornada_id.in_(ids)).all()):
        dia = fecha_de[r.jornada_id].isoformat()
        salida.append({"desde": dia, "hasta": dia, "fecha": dia, "dias": 1,
                       "sale": r.sale.nombre, "entra": r.entra.nombre,
                       "motivo": r.motivo.value, "nota": r.nota,
                       "dias_partidos": []})

    for r in (db.query(m.ReemplazoRecurso)
              .filter(m.ReemplazoRecurso.desde_jornada_id.in_(ids),
                      m.ReemplazoRecurso.tipo == m.TipoRecurso.PERSONAL).all()):
        sale = db.get(m.Persona, r.sale_persona_id) if r.sale_persona_id else None
        entra = db.get(m.Persona, r.entra_persona_id) if r.entra_persona_id else None
        desde = fecha_de.get(r.desde_jornada_id)
        hasta = fecha_de.get(r.hasta_jornada_id) if r.hasta_jornada_id else None
        # Los dias que se partieron: la asignacion del que salio sigue
        # ahi, con la hora en que lo relevaron.
        partidos = [fecha_de[a.jornada_id].isoformat() for a in
                    db.query(m.AsignacionPersonal)
                    .filter(m.AsignacionPersonal.jornada_id.in_(ids),
                            m.AsignacionPersonal.persona_id == r.sale_persona_id,
                            m.AsignacionPersonal.relevado_por_id == r.entra_persona_id,
                            m.AsignacionPersonal.relevado_en.isnot(None)).all()]
        salida.append({
            "desde": desde.isoformat() if desde else None,
            "hasta": (hasta or desde).isoformat() if desde else None,
            "fecha": desde.isoformat() if desde else None,
            "dias": r.jornadas_afectadas,
            "sale": sale.nombre if sale else None,
            "entra": entra.nombre if entra else None,
            "motivo": r.motivo_tipo.value if r.motivo_tipo else None,
            "nota": r.motivo,
            "dias_partidos": sorted(partidos)})

    return sorted(salida, key=lambda c: c["desde"] or "")


def cierre_del_mes(db: Session, contrato_id: int) -> dict:'''
assert s.count("def cierre_del_mes(db: Session, contrato_id: int) -> dict:") == 1
s = s.replace("def cierre_del_mes(db: Session, contrato_id: int) -> dict:", AYUDA)
R.write_text(s)
print("implantado.py: el resumen lee las dos tablas")

# --- panorama --------------------------------------------------------
R = RAIZ / "backend/app/panorama.py"
s = R.read_text()
VIEJO = """    relevos = 0
    if ids:
        relevos = (db.query(m.Reemplazo)
                   .filter(m.Reemplazo.jornada_id.in_(ids)).count())
"""
NUEVO = """    # Dos tablas guardan el mismo hecho: la vieja del implantado y la del
    # motor de relevo, donde caen todos los cambios nuevos.
    relevos = 0
    if ids:
        relevos = ((db.query(m.Reemplazo)
                    .filter(m.Reemplazo.jornada_id.in_(ids)).count())
                   + (db.query(m.ReemplazoRecurso)
                      .filter(m.ReemplazoRecurso.desde_jornada_id.in_(ids))
                      .count()))
"""
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("panorama.py: los relevos del dia cuentan las dos tablas")

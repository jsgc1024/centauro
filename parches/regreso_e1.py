"""Paso 1: el historial dice lo que la tarjeta necesita decir.

Le faltaban dos cosas: si el movimiento sigue corriendo, y que dias se
partieron. La segunda es la prueba de que quien trabajo media jornada va
a cobrar media jornada, y hoy solo se ve abriendo la nomina --o sea la
semana siguiente, o sea cuando ya hubo reclamo--.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/routers/contingencia.py"
s = R.read_text()

# El import del reloj: el "hoy" que decide si un cambio sigue en curso
# es el del pais del servicio, no el del navegador ni el del servidor.
VIEJO = "from app import auditoria, auth, contingencia as motor\n"
NUEVO = "from app import auditoria, auth, contingencia as motor\nfrom app import reloj\n"
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

AYUDA = '''def _partidos(db: Session, r: m.ReemplazoRecurso, desde: m.Jornada,
              hasta: m.Jornada | None) -> list[dict]:
    """Los dias que el cambio partio en dos, con su hora.

    La asignacion de quien salio sigue ahi, marcada con la hora en que lo
    relevaron. Ese renglon es lo que explica por que el mismo dia aparece
    dos veces en la nomina, y el consultor tiene que poder verlo sin
    abrirla.
    """
    if r.tipo != m.TipoRecurso.PERSONAL or not r.sale_persona_id:
        return []
    consulta = (db.query(m.Jornada.fecha, m.AsignacionPersonal.relevado_en)
                .join(m.AsignacionPersonal,
                      m.AsignacionPersonal.jornada_id == m.Jornada.id)
                .filter(m.Jornada.equipo_id == desde.equipo_id,
                        m.Jornada.fecha >= desde.fecha,
                        m.AsignacionPersonal.persona_id == r.sale_persona_id,
                        m.AsignacionPersonal.relevado_por_id == r.entra_persona_id,
                        m.AsignacionPersonal.relevado_en.isnot(None)))
    if hasta is not None:
        consulta = consulta.filter(m.Jornada.fecha <= hasta.fecha)
    return [{"fecha": f.isoformat(), "hora": h.strftime("%H:%M")}
            for f, h in consulta.order_by(m.Jornada.fecha).all()]


def _nombre(db: Session, persona_id: int | None) -> str | None:'''
assert s.count("def _nombre(db: Session, persona_id: int | None) -> str | None:") == 1
s = s.replace("def _nombre(db: Session, persona_id: int | None) -> str | None:", AYUDA)

# El cuerpo del historial.
VIEJO = '''    filas = (db.query(m.ReemplazoRecurso)
             .filter_by(servicio_id=servicio_id)
             .order_by(m.ReemplazoRecurso.creado_en).all())
    salida = []'''
NUEVO = '''    filas = (db.query(m.ReemplazoRecurso)
             .filter_by(servicio_id=servicio_id)
             .order_by(m.ReemplazoRecurso.creado_en).all())
    # El "hoy" que decide si un cambio sigue corriendo es el del pais del
    # servicio. El del navegador no sirve: un consultor en Mexico mirando
    # un servicio de Sao Paulo veria terminado lo que alli sigue vivo.
    servicio = db.get(m.Servicio, servicio_id)
    hoy = reloj.Relojes(db).hoy(servicio.pais_id if servicio else None)
    implantado = bool(servicio and servicio.tipo == m.TipoServicio.IMPLANTADO)
    salida = []'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''            "regreso_por": _nombre(db, r.regreso_por_id),
        })'''
NUEVO = '''            "regreso_por": _nombre(db, r.regreso_por_id),
            # Sigue corriendo: nadie lo cerro y todavia no llega a su
            # ultimo dia. Es lo que decide si se ofrece el regreso.
            "en_curso": (r.regreso_en is None
                         and (hasta is None or hasta.fecha >= hoy)),
            # Los dias que se partieron, con la hora del relevo.
            "jornadas_partidas": _partidos(db, r, desde, hasta) if desde else [],
            # El implantado siempre termina en una fecha, aunque el
            # consultor no la haya escrito. Despues de esa fecha hay que
            # volver a pedirlo.
            "se_vuelve_a_pedir": implantado and hasta is not None,
        })'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

R.write_text(s)
print("routers/contingencia.py: el historial trae estado y dias partidos")

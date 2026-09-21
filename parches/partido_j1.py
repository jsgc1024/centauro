"""El dia partido se busca en los dos sentidos.

Un movimiento puede partir dos dias: el que lo abre --se fue Juan a
media manana y entro Luis-- y el que lo cierra --Luis trabajo la manana
en que Juan volvio--. En el primero el relevado es el titular; en el
segundo es el que cubria. Buscando en un solo sentido, el dia partido
del regreso no aparecia en ninguna pantalla.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

R = RAIZ / "backend/app/routers/contingencia.py"
s = R.read_text()

VIEJO = '''def _partidos(db: Session, r: m.ReemplazoRecurso, desde: m.Jornada,
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
            for f, h in consulta.order_by(m.Jornada.fecha).all()]'''

NUEVO = '''def _partidos(db: Session, r: m.ReemplazoRecurso, desde: m.Jornada,
              hasta: m.Jornada | None) -> list[dict]:
    """Los dias que el movimiento partio en dos, con su hora y su dueno.

    La asignacion de quien fue relevado sigue ahi, marcada con la hora en
    que lo relevaron. Ese renglon es lo que explica por que el mismo dia
    aparece dos veces en la nomina, y el consultor tiene que poder verlo
    sin abrirla.

    Se busca en los dos sentidos porque un movimiento puede partir dos
    dias: el que lo abre --se fue el titular a media manana y entro el
    que cubre-- y el que lo cierra --el que cubria trabajo la manana en
    que el titular volvio--. En el primero el relevado es el titular; en
    el segundo, el que cubria. Buscando en un solo sentido, el dia
    partido del regreso no aparecia en ninguna pantalla.

    `quien` es el que cobra hasta esa hora: el relevado de ese dia.
    """
    if r.tipo != m.TipoRecurso.PERSONAL or not r.sale_persona_id:
        return []

    def buscar(relevado: int, releva: int) -> list:
        consulta = (db.query(m.Jornada.fecha, m.AsignacionPersonal.relevado_en)
                    .join(m.AsignacionPersonal,
                          m.AsignacionPersonal.jornada_id == m.Jornada.id)
                    .filter(m.Jornada.equipo_id == desde.equipo_id,
                            m.Jornada.fecha >= desde.fecha,
                            m.AsignacionPersonal.persona_id == relevado,
                            m.AsignacionPersonal.relevado_por_id == releva,
                            m.AsignacionPersonal.relevado_en.isnot(None)))
        if hasta is not None:
            consulta = consulta.filter(m.Jornada.fecha <= hasta.fecha)
        return consulta.all()

    titular, cubre = r.sale_persona_id, r.entra_persona_id
    filas = ([(f, h, titular) for f, h in buscar(titular, cubre)]
             + [(f, h, cubre) for f, h in buscar(cubre, titular)])
    return [{"fecha": f.isoformat(), "hora": h.strftime("%H:%M"),
             "quien": _nombre(db, quien)}
            for f, h, quien in sorted(filas, key=lambda x: x[0])]'''

assert s.count(VIEJO) == 1, "no encontre _partidos"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("routers/contingencia.py: el dia partido se busca en los dos sentidos")

# --- la tarjeta nombra al que cobra, no siempre al titular -----------
R = RAIZ / "backend/app/web/servicio.js"
s = R.read_text()
VIEJO = '''      t("srv_r_partido").replace("{f}", fecha(d.fecha))
        .replace("{p}", r.sale || "?").replace("{h}", d.hora)));'''
NUEVO = '''      t("srv_r_partido").replace("{f}", fecha(d.fecha))
        .replace("{p}", d.quien || r.sale || "?").replace("{h}", d.hora)));'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("servicio.js: el renglon nombra a quien cobra ese dia")

# --- el banco: el dia partido del regreso tambien --------------------
R = RAIZ / "backend/app/web/banco.html"
s = R.read_text()
VIEJO = '''  partidos: [{ fecha: dia(0), hora: "11:05" }],'''
NUEVO = '''  partidos: [{ fecha: dia(0), hora: "11:05", quien: "Juan Ramirez" }],'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
# Y el cerrado enseña el dia partido del regreso: al reves.
VIEJO = '''  en_curso: false, se_vuelve_a_pedir: false, partidos: [],
  regreso_en: `${dia(-11)}T17:30:00`, regreso_por: "Ana Solis",'''
NUEVO = '''  en_curso: false, se_vuelve_a_pedir: false,
  /* El dia partido del regreso: aqui el que cobra hasta esa hora es el
     que estaba cubriendo, no el titular. */
  partidos: [{ fecha: dia(-10), hora: "09:40", quien: "Beatriz Roman" }],
  regreso_en: `${dia(-11)}T17:30:00`, regreso_por: "Ana Solis",'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("banco.html: los dos sentidos a la vista")

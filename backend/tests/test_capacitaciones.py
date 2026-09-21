"""El padrón de certificados, y lo que cuelga de él.

De aquí sale ahora si alguien está al corriente —el criterio del bono y
la dimensión de la calificación— en vez de una casilla que alguien
marcaba a mano. Y de aquí salen los avisos de certificado por vencer:
`vigencia_hasta` existía desde hacía meses y nada la miraba.
"""
from datetime import date, timedelta


def _cursos(cliente, sesion, filas):
    return cliente.post("/odoo/capacitaciones", json=filas,
                        headers=sesion("admin"))


def _curso(correo, nombre, vence=None, **extra):
    fila = {"correo": correo, "nombre": nombre, **extra}
    if vence is not None:
        fila["vigencia_hasta"] = vence.isoformat()
    return fila


CORREO = "juan.ramirez@centauro.lat"


# ------------------------------------------------------------- lo que entra

def test_odoo_manda_los_cursos(cliente, sesion, datos):
    r = _cursos(cliente, sesion, [
        _curso(CORREO, "Manejo defensivo", date.today() + timedelta(days=400),
               institucion="ANSI Capacitacion",
               obtenida_en=date.today().isoformat())])
    assert r.status_code == 200, r.text
    assert r.json()["creadas"] == 1


def test_revalidar_no_crea_otro_renglon(cliente, sesion, datos):
    """La llave es la persona más el nombre del curso. Cuando alguien
    revalida su manejo defensivo se le mueve la vigencia al mismo
    renglón: así el padrón dice cuántos cursos tiene, no cuántas veces
    los ha tomado."""
    from app import models as m
    from app.db import SessionLocal

    nueva = date.today() + timedelta(days=700)
    _cursos(cliente, sesion, [
        _curso(CORREO, "Manejo defensivo", date.today() + timedelta(days=10))])
    r = _cursos(cliente, sesion, [_curso(CORREO, "Manejo defensivo", nueva)])
    assert r.json()["creadas"] == 0
    assert r.json()["actualizadas"] == 1

    db = SessionLocal()
    try:
        persona = db.query(m.Persona).filter_by(correo=CORREO).first()
        cursos = db.query(m.Capacitacion).filter_by(
            persona_id=persona.id, nombre="Manejo defensivo").all()
        assert len(cursos) == 1
        assert cursos[0].vigencia_hasta == nueva
    finally:
        db.close()


def test_un_envio_parcial_no_da_de_baja_nada(cliente, sesion, datos):
    """Lo que no viene no borra lo que hay: un envío parcial no es una
    baja. Para retirar un curso hay que mandarlo con activo: false."""
    from app import capacitaciones
    from app.db import SessionLocal

    _cursos(cliente, sesion, [
        _curso(CORREO, "Primeros auxilios", date.today() + timedelta(days=90)),
        _curso(CORREO, "Manejo defensivo", date.today() + timedelta(days=90))])
    _cursos(cliente, sesion, [
        _curso(CORREO, "Primeros auxilios", date.today() + timedelta(days=120))])

    db = SessionLocal()
    try:
        from app import models as m
        persona = db.query(m.Persona).filter_by(correo=CORREO).first()
        assert capacitaciones.por_vencer(db, persona.id)["cursos"] == 2

        _cursos(cliente, sesion,
                [{"correo": CORREO, "nombre": "Manejo defensivo",
                  "activo": False}])
        db.expire_all()
        assert capacitaciones.por_vencer(db, persona.id)["cursos"] == 1
    finally:
        db.close()


# --------------------------------------------------------- el semáforo

def _persona(db, correo=CORREO):
    from app import models as m
    return db.query(m.Persona).filter_by(correo=correo).first().id


def test_sin_padron_el_criterio_no_aplica(cliente, sesion, datos):
    """Padrón vacío no es reprobado: nadie pierde dinero porque a un
    padrón le falte una captura, ni porque Odoo no haya conectado."""
    from app import capacitaciones
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        r = capacitaciones.por_vencer(db, _persona(db))
        assert r["aplica"] is False
        assert r["estado"] == "sin_registro"
    finally:
        db.close()


def test_el_semaforo_distingue_vencido_de_por_vencer(cliente, sesion, datos):
    from app import capacitaciones
    from app.db import SessionLocal

    _cursos(cliente, sesion, [
        _curso(CORREO, "Manejo defensivo", date.today() + timedelta(days=20))])
    db = SessionLocal()
    try:
        r = capacitaciones.por_vencer(db, _persona(db))
        assert r["estado"] == "por_vencer"
        assert r["dias"] == 20
    finally:
        db.close()

    _cursos(cliente, sesion, [
        _curso(CORREO, "Primeros auxilios", date.today() - timedelta(days=3))])
    db = SessionLocal()
    try:
        r = capacitaciones.por_vencer(db, _persona(db))
        assert r["estado"] == "vencido", "un vencido manda sobre un por vencer"
        assert r["curso"] == "Primeros auxilios"
    finally:
        db.close()


def test_un_curso_sin_vigencia_es_permanente(cliente, sesion, datos):
    from app import capacitaciones
    from app.db import SessionLocal

    _cursos(cliente, sesion, [_curso(CORREO, "Induccion Centauro")])
    db = SessionLocal()
    try:
        assert capacitaciones.por_vencer(db, _persona(db))["estado"] \
            == "al_corriente"
    finally:
        db.close()


# ------------------------------------------------------------ el aviso

def test_avisa_a_los_treinta_dias_y_el_dia_que_vence(cliente, sesion, datos):
    from app import capacitaciones
    from app.db import SessionLocal

    hoy = date.today()
    _cursos(cliente, sesion, [_curso(CORREO, "Manejo defensivo",
                                     hoy + timedelta(days=30))])
    db = SessionLocal()
    try:
        r = capacitaciones.revisar_vencimientos(db, hoy)
        assert r["avisados"] == 1
        # Y no se repite el mismo dia: la tarea corre diario.
        assert capacitaciones.revisar_vencimientos(db, hoy)["avisados"] == 0
        # A los veintinueve no toca: son dos avisos, no una cuenta atras.
        assert capacitaciones.revisar_vencimientos(
            db, hoy + timedelta(days=1))["avisados"] == 0
        # El dia que vence, el ultimo.
        assert capacitaciones.revisar_vencimientos(
            db, hoy + timedelta(days=30))["avisados"] == 1
    finally:
        db.close()


def test_el_aviso_le_llega_a_quien_gestiona_a_la_gente(cliente, sesion, datos):
    """Un certificado no es de un consultor: una persona no tiene
    consultor fijo, va con el que le toque cada día."""
    from app import capacitaciones, models as m
    from app.db import SessionLocal

    hoy = date.today()
    _cursos(cliente, sesion, [_curso(CORREO, "Primeros auxilios", hoy)])
    db = SessionLocal()
    try:
        capacitaciones.revisar_vencimientos(db, hoy)
        aviso = (db.query(m.Notificacion)
                 .filter_by(destinatario=m.Destinatario.COLABORADOR)
                 .order_by(m.Notificacion.id.desc()).first())
        assert aviso is not None
        assert aviso.correo == "rrhh@centauro.lat"
        assert "Primeros auxilios" in aviso.asunto
        assert "Juan Ramirez" in aviso.datos
    finally:
        db.close()


# ----------------------------------------------------- y lo que cuelga

def test_el_bono_lee_el_padron_y_no_una_casilla(cliente, sesion, datos):
    """El criterio decía «dato de Odoo» cuando Odoo no lo mandaba, y
    dependía de que alguien marcara una casilla cada mes."""
    from app import bonos
    from app.db import SessionLocal

    hoy = date.today()
    db = SessionLocal()
    try:
        persona = _persona(db)
        sin = bonos.medir_capacitacion(db, persona, hoy.year, hoy.month)
        assert sin["aplica"] is False
    finally:
        db.close()

    _cursos(cliente, sesion, [_curso(CORREO, "Manejo defensivo",
                                     hoy + timedelta(days=400))])
    db = SessionLocal()
    try:
        con = bonos.medir_capacitacion(db, _persona(db), hoy.year, hoy.month)
        assert con.get("aplica", True) is True
        assert con["valor"] == 100
    finally:
        db.close()

    # Uno vencido antes del cierre del mes lo reprueba.
    _cursos(cliente, sesion, [_curso(CORREO, "Primeros auxilios",
                                     date(hoy.year, hoy.month, 1)
                                     - timedelta(days=1))])
    db = SessionLocal()
    try:
        mal = bonos.medir_capacitacion(db, _persona(db), hoy.year, hoy.month)
        assert mal["valor"] == 0
        assert "Primeros auxilios" in mal["detalle"]
    finally:
        db.close()

"""Entrega 4b: mover un regreso ya capturado."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- el tope se muda junto a su candado -------------------------------
R = RAIZ / "backend/app/implantado.py"
s = R.read_text()
VIEJO = '''def ultimo_dia_del_mes(fecha: date) -> date:
    """El tope de un cambio sin fecha de fin."""
    return fecha.replace(day=calendar.monthrange(fecha.year, fecha.month)[1])


'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, "")
VIEJO = "    tope = hasta or ultimo_dia_del_mes(desde)"
NUEVO = "    tope = hasta or contingencia.ultimo_dia_del_mes(desde)"
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("implantado.py: el tope se pide donde vive la regla")

# --- contingencia -----------------------------------------------------
R = RAIZ / "backend/app/contingencia.py"
s = R.read_text()
VIEJO = "from datetime import date, datetime\n"
NUEVO = "import calendar\nfrom datetime import date, datetime, timedelta\n"
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# El tope, junto al candado que lo exige.
ANCLA = "def _tramo_con_fin(desde: m.Jornada, hasta: m.Jornada | None) -> None:"
TOPE = '''def ultimo_dia_del_mes(fecha: date) -> date:
    """El tope de un cambio de implantado sin fecha de fin.

    Vive aqui, al lado del candado que lo exige, y no en el implantado:
    escrito en dos lugares es como el umbral de silencio, que acabo
    diciendo 60 en una pantalla y 120 en la otra.
    """
    return fecha.replace(day=calendar.monthrange(fecha.year, fecha.month)[1])


def _tramo_con_fin(desde: m.Jornada, hasta: m.Jornada | None) -> None:'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, TOPE)

# La correccion del regreso.
ANCLA = '''def _firmar_el_cierre(db: Session, r: m.ReemplazoRecurso, arranco: m.Jornada,'''
MOVER = '''def _dinero_trabado(db: Session, equipo_id: int, desde: date, hasta: date,
                    personas: list[int]) -> list[m.AsignacionViatico]:
    """Los viaticos de ese tramo que ya no se pueden desandar.

    El mismo candado que usa `deshacer`: en cuanto alguien pidio el
    dinero o lo transfirio, el movimiento dejo de vivir solo en una
    tabla. Hay una solicitud, una transferencia y un plazo corriendo.
    """
    tocados = (db.query(m.AsignacionViatico)
               .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
               .filter(m.Jornada.equipo_id == equipo_id,
                       m.Jornada.fecha >= desde, m.Jornada.fecha <= hasta,
                       m.AsignacionViatico.persona_id.in_(personas))
               .all())
    return [v for v in tocados
            if v.estatus not in SIN_TOCAR or v.comprobantes
            or float(v.monto_comprobado or 0) > 0]


def _mover_el_regreso(db: Session, r: m.ReemplazoRecurso, arranco: m.Jornada,
                      vuelve: m.Jornada, hecho_por_id: int | None,
                      relevado_en: datetime | None) -> dict:
    """El titular dijo otra fecha despues de que ya se capturo el regreso.

    Juan dijo el 25, el consultor lo capturo, y el 24 avisa que mejor el
    28. El movimiento no se duplica: se recorre otra vez y se vuelve a
    firmar, para que el mes siga leyendo un solo hecho.

    Por dentro es el mismo relevo, en el sentido que toque: si se atrasa,
    el que cubria recupera los dias que ya habian vuelto al titular; si
    se adelanta, el titular se lleva unos dias mas.

    Dos cosas lo bloquean, y las dos son la misma: que el dinero ya se
    haya movido. Un viatico pedido, transferido o comprobado no se
    desanda a mano --eso seria peor que el error-- y lo que corresponde
    es un cambio nuevo, con su rastro.
    """
    fin = db.get(m.Jornada, r.hasta_jornada_id) if r.hasta_jornada_id else None
    if not fin:
        raise HTTPException(409, "Ese cambio no tiene ultimo dia que mover")

    # Si el dia del regreso se partio, ese dia ya esta repartido entre los
    # dos y tiene su hora. Moverlo seria rehacer una nomina.
    partido = (db.query(m.AsignacionPersonal.id)
               .filter(m.AsignacionPersonal.jornada_id == fin.id,
                       m.AsignacionPersonal.persona_id == r.entra_persona_id,
                       m.AsignacionPersonal.relevado_por_id == r.sale_persona_id,
                       m.AsignacionPersonal.relevado_en.isnot(None))
               .first())
    if partido:
        raise HTTPException(409, {
            "mensaje": ("El dia del regreso se partio: ese dia ya esta "
                        "repartido entre los dos, con su hora. Para "
                        "cambiarlo hay que hacer un cambio nuevo."),
            "dia": fin.fecha.isoformat(),
        })

    vuelve_hoy = _primer_dia_abierto(db, arranco.equipo_id,
                                     fin.fecha + timedelta(days=1))
    if not vuelve_hoy:
        raise HTTPException(409, "Ya no quedan dias abiertos despues de ese cambio")
    if vuelve.fecha == vuelve_hoy.fecha:
        raise HTTPException(409, {
            "mensaje": "El titular ya regresa ese dia.",
            "regresa": vuelve_hoy.fecha.isoformat()})

    gente = [r.sale_persona_id, r.entra_persona_id]
    if vuelve.fecha > vuelve_hoy.fecha:
        # Se atrasa: el que cubria recupera los dias que ya eran del titular.
        hasta = (db.query(m.Jornada)
                 .filter(m.Jornada.equipo_id == arranco.equipo_id,
                         m.Jornada.fecha >= vuelve_hoy.fecha,
                         m.Jornada.fecha < vuelve.fecha,
                         m.Jornada.estatus.notin_([m.EstatusJornada.CANCELADA,
                                                   m.EstatusJornada.TERMINADA]))
                 .order_by(m.Jornada.fecha.desc()).first())
        if not hasta:
            raise HTTPException(409, "No hay dias abiertos que recuperar")
        _no_pasarse_del_tope(arranco, hasta)
        trabados = _dinero_trabado(db, arranco.equipo_id, vuelve_hoy.fecha,
                                   hasta.fecha, gente)
        _no_con_dinero(trabados)
        hecho = reemplazar_personal(
            db, desde_jornada_id=vuelve_hoy.id,
            sale_persona_id=r.sale_persona_id,
            entra_persona_id=r.entra_persona_id,
            motivo=r.motivo, hecho_por_id=hecho_por_id,
            motivo_tipo=r.motivo_tipo, hasta_jornada_id=hasta.id,
            relevado_en=relevado_en)
        cerrado = _firmar_el_cierre(db, r, arranco, vuelve, hecho, hecho_por_id)
        # Esos dias no volvieron al titular: se los llevo el que cubre.
        cerrado["jornadas_recuperadas"] = cerrado.pop("jornadas_devueltas")
        cerrado["jornadas_devueltas"] = []
        return cerrado

    # Se adelanta: el titular se lleva unos dias mas.
    trabados = _dinero_trabado(db, arranco.equipo_id, vuelve.fecha,
                               fin.fecha, gente)
    _no_con_dinero(trabados)
    hecho = reemplazar_personal(
        db, desde_jornada_id=vuelve.id,
        sale_persona_id=r.entra_persona_id,
        entra_persona_id=r.sale_persona_id,
        motivo=r.motivo, hecho_por_id=hecho_por_id,
        motivo_tipo=r.motivo_tipo, hasta_jornada_id=fin.id,
        relevado_en=relevado_en)
    cerrado = _firmar_el_cierre(db, r, arranco, vuelve, hecho, hecho_por_id)
    cerrado["jornadas_recuperadas"] = []
    return cerrado


def _no_con_dinero(trabados: list[m.AsignacionViatico]) -> None:
    if trabados:
        raise HTTPException(409, {
            "mensaje": ("El dinero de esos dias ya se movio, asi que el "
                        "regreso no se puede correr. Si hay que cambiarlo, "
                        "se hace un cambio nuevo, con su rastro."),
            "viaticos": [v.id for v in trabados],
        })


def _no_pasarse_del_tope(arranco: m.Jornada, hasta: m.Jornada) -> None:
    """Atrasar un regreso no puede saltarse el tope del mes.

    Es el mismo candado de siempre visto por el otro lado: si el regreso
    se corre al 2 de octubre, el que cubre se quedaria con dias de
    octubre que nadie pidio.
    """
    servicio = arranco.equipo.servicio if arranco.equipo else None
    if servicio and servicio.tipo == m.TipoServicio.IMPLANTADO:
        tope = ultimo_dia_del_mes(arranco.fecha)
        if hasta.fecha > tope:
            raise HTTPException(409, {
                "mensaje": ("Ese regreso se pasa del mes. El cambio termina "
                            "el ultimo dia del mes; para seguir despues hay "
                            "que pedirlo otra vez."),
                "tope": tope.isoformat(),
            })


def _firmar_el_cierre(db: Session, r: m.ReemplazoRecurso, arranco: m.Jornada,'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, MOVER)

# La primera vez tampoco devuelve dias recuperados: la forma es una sola.
VIEJO = '''        "jornadas_devueltas": hecho["jornadas_afectadas"],'''
NUEVO = '''        "jornadas_devueltas": hecho["jornadas_afectadas"],
        # Los que el que cubria recupera cuando el regreso se atrasa. La
        # primera vez siempre va vacia; la forma es una sola.
        "jornadas_recuperadas": [],'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

R.write_text(s)
print("contingencia.py: _mover_el_regreso con su candado")

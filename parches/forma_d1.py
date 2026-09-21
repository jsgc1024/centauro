"""Entrega 1: una sola forma de respuesta y una vista previa.

La pantalla que pinta el cambio es la misma para eventual y para
implantado. Si cada puerta devolviera los mismos datos con otro nombre,
habria dos recuadros que dicen lo mismo y se separan con el tiempo.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- 1. cambiar_recurso: los nombres del motor y sin commit ----------
R = RAIZ / "backend/app/implantado.py"
s = R.read_text()

VIEJO = '''    db.commit()

    fechas = hecho["jornadas_afectadas"]
    return {
        "resultado": "cambiado", "tipo": tipo.value,
        "reemplazo_id": hecho["reemplazo_id"],
        "dias_cambiados": len(fechas),
        "desde": fechas[0] if fechas else dias[0].fecha.isoformat(),
        "hasta": fechas[-1] if fechas else dias[-1].fecha.isoformat(),
        # Si el consultor no puso fin, el tope lo puso el sistema. La
        # pantalla lo dice en voz alta: "hasta el 30; para octubre hay
        # que volver a pedirlo".
        "tope_automatico": hasta is None,
        "sale": sale_nombre, "entra": entra_nombre,
        "motivo": motivo_tipo.value,
        # Los dias que se partieron: la prueba de que quien trabajo media
        # jornada va a cobrar media jornada.
        "dias_partidos": hecho["jornadas_partidas"],
        "dias_con_choque": hecho["jornadas_con_choque"],
        "relevado_en": hecho["relevado_en"],
        "hora_propuesta": hecho.get("hora_propuesta"),
        "viaticos": hecho["viaticos"],
        "revision_pendiente": hecho.get("revision_pendiente"),
        "aviso": _aviso_del_dinero(hecho["viaticos"], sale_nombre,
                                   entra_nombre),
    }'''

NUEVO = '''    # No se cierra aqui: el router es quien guarda, igual que en
    # contingencia. Asi la vista previa puede correr el cambio de verdad
    # y deshacerlo, en vez de tener una segunda cuenta que calcule "lo
    # que pasaria" y acabe separandose de la primera.
    db.flush()

    fechas = hecho["jornadas_afectadas"]
    return {
        "resultado": "cambiado", "tipo": tipo.value,
        "reemplazo_id": hecho["reemplazo_id"],
        "dias_cambiados": len(fechas),
        "desde": fechas[0] if fechas else dias[0].fecha.isoformat(),
        "hasta": fechas[-1] if fechas else dias[-1].fecha.isoformat(),
        # Si el consultor no puso fin, el tope lo puso el sistema. La
        # pantalla lo dice en voz alta: "hasta el 30; para octubre hay
        # que volver a pedirlo".
        "tope_automatico": hasta is None,
        "sale": sale_nombre, "entra": entra_nombre,
        "motivo": motivo_tipo.value,
        # Con los nombres del motor y no con unos propios: la pantalla
        # que pinta esto es la misma para eventual y para implantado.
        "jornadas_afectadas": fechas,
        # Los dias que se partieron: la prueba de que quien trabajo media
        # jornada va a cobrar media jornada.
        "jornadas_partidas": hecho["jornadas_partidas"],
        "jornadas_con_choque": hecho["jornadas_con_choque"],
        "relevado_en": hecho["relevado_en"],
        "hora_propuesta": hecho.get("hora_propuesta"),
        "viaticos": hecho["viaticos"],
        "revision_pendiente": hecho.get("revision_pendiente"),
        "aviso": _aviso_del_dinero(hecho["viaticos"], sale_nombre,
                                   entra_nombre),
    }'''
assert s.count(VIEJO) == 1, "no encontre la salida de cambiar_recurso"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("implantado.py: una sola forma, sin commit")

# --- 2. el router: guarda el, y su vista previa ----------------------
R = RAIZ / "backend/app/routers/implantados.py"
s = R.read_text()

VIEJO = '''    partidos = resultado.get("dias_partidos") or []'''
NUEVO = '''    partidos = resultado.get("jornadas_partidas") or []'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

ANCLA = '''@router.get("/{servicio_id}/hospitales",'''
PREVIA = '''@router.post("/{servicio_id}/cambios/vista-previa",
             summary="Que pasaria con este cambio, sin guardarlo")
def cambiar_previa(servicio_id: int, datos: CambioRecursoIn,
                   db: Session = Depends(get_db),
                   _: m.Usuario = Depends(CONSULTOR)):
    """Se ejecuta el cambio de verdad y se deshace.

    No hay una segunda implementacion que calcule "lo que pasaria": esa
    siempre acaba separandose de la primera, y entonces el recuadro que
    el consultor lee deja de ser lo que el sistema hace.

    Lo delicado no es el nombre de quien va: es que quien sale se queda
    con dinero que tiene que comprobar, que el dia puede partirse, y que
    un cambio sin fin llega hasta donde el sistema decida. Todo eso se
    dice antes de guardar.
    """
    servicio = _servicio_implantado(db, servicio_id)
    try:
        return motor.cambiar_recurso(
            db, servicio.id, datos.tipo, datos.desde, datos.hasta,
            datos.entra_id, datos.motivo, None,
            datos.sale_id, datos.nota, datos.relevado_en)
    finally:
        db.rollback()


@router.get("/{servicio_id}/hospitales",'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, PREVIA)
R.write_text(s)
print("routers/implantados.py: vista previa del cambio")

# --- 3. el guion de humo -------------------------------------------
R = RAIZ / "probar_implantado.py"
s = R.read_text()
VIEJO = '''if rem.get("dias_partidos"):
    print(f"   dia partido: {', '.join(rem['dias_partidos'])} "'''
NUEVO = '''if rem.get("jornadas_partidas"):
    print(f"   dia partido: {', '.join(rem['jornadas_partidas'])} "'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("probar_implantado.py: al dia")

"""Regla de Salvador (18 sep): el que debe viaticos no se da de baja.

Quitar a alguien de un servicio ya lo revisaba --`quitar_personal`
rechaza con 409 si esa persona ya recibio dinero-- pero la baja del
sistema no revisaba nada. Se podia cerrar la puerta de alguien que trae
diez mil pesos sin comprobar, y ese dinero se queda sin dueno con el
cierre trabado.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

R = RAIZ / "backend/app/accesos.py"
s = R.read_text()

VIEJO = '''# Estas jornadas ya no se pueden quedar sin nadie: una cancelada no va y
# una terminada ya se trabajo.
CERRADAS = (m.EstatusJornada.CANCELADA, m.EstatusJornada.TERMINADA)
'''
NUEVO = '''# Estas jornadas ya no se pueden quedar sin nadie: una cancelada no va y
# una terminada ya se trabajo.
CERRADAS = (m.EstatusJornada.CANCELADA, m.EstatusJornada.TERMINADA)

# El ciclo del viatico que todavia corre. Mientras uno de estos viva, esa
# persona no se va: trae dinero de la empresa o esta a punto de traerlo,
# y sin su comprobacion el servicio no cierra.
#
# Fuera quedan dos a proposito:
#   ASIGNADO   el consultor lo planeo y nunca se movio un peso. Quitarla
#              del servicio lo borra con ella, sin rastro que cuadrar.
#   CERRADO    su ciclo ya termino. Si bloqueara, nadie que haya recibido
#              un viatico en su vida podria darse de baja nunca.
CICLO_ABIERTO = (m.EstatusViatico.SOLICITADO, m.EstatusViatico.TRANSFERIDO,
                 m.EstatusViatico.EN_COMPROBACION)
'''
assert s.count(VIEJO) == 1, "no encontre CERRADAS"
s = s.replace(VIEJO, NUEVO)

ANCLA = '''def jornadas_por_cubrir(db: Session, persona_id: int) -> list[dict]:'''
NUEVO_FN = '''def viaticos_sin_cerrar(db: Session, persona_id: int) -> list[dict]:
    """El dinero que esa persona todavia no cierra.

    Es lo que le impide irse. No es burocracia: un viatico transferido y
    sin comprobar es dinero de la empresa que se queda sin dueno, y el
    servicio no cierra hasta que alguien lo comprueba. El que se va tiene
    que terminar su ciclo primero.
    """
    filas = (db.query(m.AsignacionViatico)
             .filter(m.AsignacionViatico.persona_id == persona_id,
                     m.AsignacionViatico.estatus.in_(CICLO_ABIERTO))
             .all())
    salida = []
    for v in filas:
        jornada = db.get(m.Jornada, v.jornada_id)
        servicio = (jornada.equipo.servicio
                    if jornada and jornada.equipo else None)
        salida.append({
            "viatico_id": v.id,
            "fecha": jornada.fecha.isoformat() if jornada else None,
            "folio": servicio.folio if servicio else None,
            "estatus": v.estatus.value,
            "monto": float(v.monto_total or 0),
            "comprobado": float(v.monto_comprobado or 0),
            "limite": (v.limite_comprobacion.isoformat()
                       if v.limite_comprobacion else None),
        })
    return sorted(salida, key=lambda f: f["fecha"] or "")


def jornadas_por_cubrir(db: Session, persona_id: int) -> list[dict]:'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO_FN)

# El candado, dentro de desactivar.
VIEJO = '''    if not usuario.activo:
        raise HTTPException(409, "Ese acceso ya estaba desactivado")

    usuario.activo = False'''
NUEVO = '''    if not usuario.activo:
        raise HTTPException(409, "Ese acceso ya estaba desactivado")

    # El que trae dinero de la empresa no se va hasta comprobarlo. Es la
    # misma regla que ya impedia sacarla de un servicio; faltaba de este
    # lado, donde se cierra la puerta de verdad.
    debiendo = viaticos_sin_cerrar(db, usuario.persona_id)
    if debiendo:
        pendiente = sum(f["monto"] - f["comprobado"] for f in debiendo)
        raise HTTPException(409, {
            "mensaje": (f"No se le puede cerrar el acceso: tiene "
                        f"{len(debiendo)} viatico(s) sin cerrar, por "
                        f"{pendiente:,.2f}."),
            "que_hacer": "Tiene que terminar su ciclo: comprobar lo que "
                         "recibio. Si ya no va a volver, finanzas puede "
                         "cerrarlo con el ajuste que corresponda.",
            "viaticos": debiendo,
        })

    usuario.activo = False'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# Y la ficha del que si se puede ir lo dice.
VIEJO = '''    # No se desasigna nada: solo se dice lo que queda colgando.
    pendientes = jornadas_por_cubrir(db, usuario.persona_id)'''
NUEVO = '''    # Estaba asignada pero sin dinero de por medio: no afecta a la
    # operacion. Se va, y el consultor asigna a alguien mas. No se
    # desasigna nada aqui: solo se dice lo que queda colgando.
    pendientes = jornadas_por_cubrir(db, usuario.persona_id)'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

R.write_text(s)
print("accesos.py: el que debe viaticos no se da de baja")

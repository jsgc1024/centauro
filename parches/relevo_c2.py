"""Paso C2: la puerta del regreso."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- esquema ---------------------------------------------------------
R = RAIZ / "backend/app/schemas.py"
s = R.read_text()
ANCLA = "class ReemplazoVehiculoIn(Base):"
NUEVO = '''class RegresoIn(Base):
    """El titular vuelve. No pide motivo: el motivo es el del cambio que
    cierra."""
    # El primer dia que vuelve a ser suyo.
    desde: date
    # Si el que cubria alcanzo a trabajar la manana de ese dia, la hora
    # en que lo relevaron. Vacia: el sistema propone su ultima marca.
    relevado_en: datetime | None = None


class ReemplazoVehiculoIn(Base):'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("schemas.py: RegresoIn")

# --- router ----------------------------------------------------------
R = RAIZ / "backend/app/routers/contingencia.py"
s = R.read_text()
ANCLA = '''@router.post("/reemplazos/personal/vista-previa",'''
NUEVO = '''@router.post("/reemplazos/{reemplazo_id}/regreso",
             summary="El titular vuelve: cierra el cambio")
def regreso(reemplazo_id: int, datos: s.RegresoIn,
            db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(CONSULTOR)):
    """Marta se recupera y regresa el 25; Luis trabaja hasta el 24.

    No abre otro movimiento: recorre el `hasta` del que ya existe, para
    que el mes lea "Luis cubrio a Marta del 10 al 24" y no dos cambios
    cruzados que nadie sabe cual cierra a cual.
    """
    resultado = motor.regresar(db, reemplazo_id, datos.desde,
                               hecho_por_id=usuario.persona_id,
                               relevado_en=datos.relevado_en)
    servicio = db.get(m.Servicio, resultado["servicio_id"])
    partidos = resultado["dias_partidos"]
    auditoria.registrar(
        db, usuario, servicio, "regreso del titular",
        f"regresa {resultado['regresa']}; {resultado['sale']} cubrio del "
        f"{resultado['desde']} al {resultado['hasta']}"
        + (f"; dia partido: {', '.join(partidos)}" if partidos else ""))
    db.commit()
    return resultado


@router.post("/reemplazos/personal/vista-previa",'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("routers/contingencia.py: /reemplazos/{id}/regreso")

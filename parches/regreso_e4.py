"""Paso 3a: la vista previa del regreso, y una sola forma de nombrar.

`jornadas_partidas` es siempre una lista de fechas, en las tres puertas.
Lo del historial lleva ademas la hora, asi que se llama distinto
--`partidos`-- porque tener dos formas con el mismo nombre es como se
rompe una pantalla sin que nadie lo note.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- 1. regresar(): los nombres del motor ----------------------------
R = RAIZ / "backend/app/contingencia.py"
s = R.read_text()
VIEJO = '''        # Si el que cubria alcanzo a trabajar la manana del dia del
        # regreso, ese dia lo cobran los dos.
        "dias_partidos": partidas,
        "dias_con_choque": hecho["jornadas_con_choque"],
        "viaticos": hecho["viaticos"],
    }'''
NUEVO = '''        # Si el que cubria alcanzo a trabajar la manana del dia del
        # regreso, ese dia lo cobran los dos.
        "jornadas_partidas": partidas,
        "jornadas_con_choque": hecho["jornadas_con_choque"],
        # La hora que el sistema propone para partir ese dia: la ultima
        # marca del que cubria. El consultor la confirma o la corrige.
        "hora_propuesta": hecho.get("hora_propuesta"),
        "viaticos": hecho["viaticos"],
    }'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("contingencia.py: regresar() con los nombres del motor")

# --- 2. el router: auditoria, previa y el nombre del historial -------
R = RAIZ / "backend/app/routers/contingencia.py"
s = R.read_text()

VIEJO = '''    servicio = db.get(m.Servicio, resultado["servicio_id"])
    partidos = resultado["dias_partidos"]'''
NUEVO = '''    servicio = db.get(m.Servicio, resultado["servicio_id"])
    partidos = resultado["jornadas_partidas"]'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''            # Los dias que se partieron, con la hora del relevo.
            "jornadas_partidas": _partidos(db, r, desde, hasta) if desde else [],'''
NUEVO = '''            # Los dias que se partieron, con la hora del relevo. Se
            # llama distinto que el `jornadas_partidas` de las puertas de
            # cambio porque lleva la hora: dos formas con el mismo nombre
            # es como se rompe una pantalla sin que nadie lo note.
            "partidos": _partidos(db, r, desde, hasta) if desde else [],'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

ANCLA = '''@router.post("/reemplazos/personal/vista-previa",'''
PREVIA = '''@router.post("/reemplazos/{reemplazo_id}/regreso/vista-previa",
             summary="Que pasaria con este regreso, sin guardarlo")
def regreso_previa(reemplazo_id: int, datos: s.RegresoIn,
                   db: Session = Depends(get_db),
                   _: m.Usuario = Depends(CONSULTOR)):
    """Hasta que dia se queda el que cubria, si ese dia se parte y a que
    hora, y que pasa con el dinero de los dos.

    Se ejecuta el regreso de verdad y se deshace, por la misma razon que
    el cambio: una segunda cuenta que calcule "lo que pasaria" acaba
    separandose de la primera.
    """
    try:
        return motor.regresar(db, reemplazo_id, datos.desde,
                              hecho_por_id=None,
                              relevado_en=datos.relevado_en)
    finally:
        db.rollback()


@router.post("/reemplazos/personal/vista-previa",'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, PREVIA)
R.write_text(s)
print("routers/contingencia.py: vista previa del regreso")

# --- 3. las pruebas que nombraban dias_partidos ----------------------
R = RAIZ / "backend/tests/test_relevo.py"
s = R.read_text()
n = s.count('["dias_partidos"]')
assert n == 3, f"esperaba 3 usos, hay {n}"
s = s.replace('["dias_partidos"]', '["jornadas_partidas"]')
s = s.replace('    partidos = resultado["dias_partidos"]',
              '    partidos = resultado["jornadas_partidas"]')
R.write_text(s)
print(f"test_relevo.py: {n} usos al dia")

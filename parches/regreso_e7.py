"""jornadas_devueltas: una lista de fechas se llama como las demas."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

R = RAIZ / "backend/app/contingencia.py"
s = R.read_text()
VIEJO = '''        "dias_cubiertos": cubiertos,
        "dias_devueltos": hecho["jornadas_afectadas"],'''
NUEVO = '''        "dias_cubiertos": cubiertos,
        "jornadas_devueltas": hecho["jornadas_afectadas"],'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("contingencia.py: jornadas_devueltas")

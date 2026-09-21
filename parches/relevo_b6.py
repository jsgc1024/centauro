"""El filtro de marzo se comia abril: "2029-04-02" >= "2029-03-15" es
cierto si se comparan como texto. Se acota por los dos lados."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/tests/test_relevo.py"
s = R.read_text()

VIEJO = '''    # Y marzo si: del 15 en adelante es de Luis.
    marzo = [j for j in detalle["equipos"][0]["jornadas"]
             if j["fecha"] >= "2029-03-15"]'''
NUEVO = '''    # Y marzo si: del 15 al 31 es de Luis. Acotado por los dos lados,
    # porque como texto "2029-04-02" tambien es mayor que "2029-03-15".
    marzo = [j for j in detalle["equipos"][0]["jornadas"]
             if "2029-03-15" <= j["fecha"] <= "2029-03-31"]'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("test_relevo.py: el filtro de marzo ya no se come abril")

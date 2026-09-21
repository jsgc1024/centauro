"""Un solo nombre para "lista de dias partidos"."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

for rel, esperados in (("backend/app/implantado.py", 2),
                       ("backend/tests/test_relevo.py", 2)):
    R = RAIZ / rel
    s = R.read_text()
    n = s.count("dias_partidos")
    assert n == esperados, f"{rel}: esperaba {esperados}, hay {n}"
    s = s.replace("dias_partidos", "jornadas_partidas")
    R.write_text(s)
    print(f"{rel}: {n} al dia")

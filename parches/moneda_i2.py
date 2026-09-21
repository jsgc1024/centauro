import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

VIEJO = """  Hoy no muerde porque no hay tarifarios en dólares cargados. **El día
  que se cargue uno, muerde en silencio.** Por eso lo único que
  conviene adelantar es el candado: que no se autorice una cotización en
  moneda distinta a la local sin tipo de cambio. Son pocas líneas y no
  depende de ninguna decisión pendiente.
"""
NUEVO = """  Hoy no muerde porque no hay tarifarios en dólares cargados. **El día
  que se cargue uno, muerde en silencio.**

  Se propuso adelantar un candado —no autorizar una cotización en moneda
  distinta a la local sin tipo de cambio, pocas líneas, sin depender de
  ninguna decisión pendiente— y **Salvador decidió que también espere**.
  Va todo junto al final. No adelantarlo por iniciativa propia.

  El aviso práctico mientras tanto: **mientras no exista el candado, no
  cargar tarifarios en otra moneda.** Es lo único que dispara el
  problema.
"""
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("BITACORA.md: la decision queda escrita como es")

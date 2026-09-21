import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

VIEJO = """- Las pruebas **nunca** corren contra la base de desarrollo."""
NUEVO = """- Las pruebas **nunca** corren contra la base de desarrollo.
- **Se dice cuántas pruebas deberían pasar, antes de correrlas.** No es
  ceremonia: el 18 de septiembre una corrida salió en verde con 464
  cuando había 466 escritas. Las dos que faltaban eran justo las dos
  últimas — Docker en Mac sincroniza los archivos con retraso y el
  contenedor todavía no las veía. Una corrida verde que no probó lo que
  acabas de escribir es peor que una roja. Si el número no cuadra, se
  vuelve a correr antes de creerle."""
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("BITACORA.md: la practica del conteo")

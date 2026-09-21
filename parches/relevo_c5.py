import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

ANCLA = """**Dos tablas para el mismo hecho.**"""
NUEVO = """**El regreso cierra el movimiento, no abre otro.**

Juan trabaja hasta el 10 y se enferma; Luis lo releva y entra el 11. A
los días Juan se recupera, avisa al consultor, y el consultor coordina
que regrese el 25: **Luis trabaja hasta el 24 por orden del consultor**.

Eso es un solo hecho —"Luis cubrió a Juan del 11 al 24"— y así se lee en
el historial y en el corte del mes. Si el regreso abriera su propio
movimiento, el mismo mes mostraría dos cambios cruzados —Luis por Juan,
Juan por Luis— y nadie sabría cuál cierra a cuál.

Por dentro es el mismo relevo de siempre con los nombres al revés, así
que si Luis alcanzó a trabajar la mañana del 25 ese día se parte y lo
cobran los dos —y ese día sigue contando como suyo—. El movimiento que
ese relevo abre se borra: el hecho es el cierre del primero. Lo que
queda firmado es `regreso_en` y `regreso_por_id`: quién lo ordenó y
cuándo.

El regreso **no pide motivo**: el motivo es el del cambio que cierra.

Por ahora regresa el personal. La unidad que sale del taller ya trae su
`hasta` del registro de taller, así que no lo necesita todavía.

**Dos tablas para el mismo hecho.**"""

assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("BITACORA.md: el regreso")

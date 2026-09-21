"""El banco enseña también la corrección, y la bitácora la cuenta."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- banco -----------------------------------------------------------
R = RAIZ / "backend/app/web/banco.html"
s = R.read_text()
ANCLA = '''  "/servicios/equipos/1/recomendaciones": {'''
NUEVA = '''  /* Y la de un regreso que se atrasa: el que cubria recupera dias que
     ya habian vuelto al titular. */
  "/contingencia/reemplazos/3/regreso/vista-previa": {
    cerrado: 3, servicio_id: 1, regresa: "Ana Torres", sale: "Beatriz Roman",
    desde: dia(-14), hasta: dia(-8), dias_cubiertos: 7,
    jornadas_devueltas: [],
    jornadas_recuperadas: [dia(-10), dia(-9), dia(-8)],
    jornadas_partidas: [],
    jornadas_con_choque: [],
    hora_propuesta: null,
    viaticos: { a_comprobar: [], cancelados: [],
                propuestos: [{ persona_id: 8, monto: 2100 }] },
  },
  "/servicios/equipos/1/recomendaciones": {'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVA)
R.write_text(s)
print("banco.html: la previa de una correccion")

# --- bitacora --------------------------------------------------------
R = RAIZ / "BITACORA.md"
s = R.read_text()
ANCLA = "El regreso **no pide motivo**: el motivo es el del cambio que cierra."
NUEVO = """El regreso **no pide motivo**: el motivo es el del cambio que cierra.

**Y se puede mover.** Juan dijo el 25, el consultor lo capturó, y el 24
avisa que mejor el 28. Capturar el regreso otra vez recorre el mismo
movimiento y lo vuelve a firmar: el mes sigue leyendo un solo hecho. Por
dentro es el mismo relevo en el sentido que toque — si se atrasa, el que
cubría recupera los días que ya habían vuelto al titular; si se
adelanta, el titular se lleva unos días más.

Dos cosas lo bloquean, y las dos son la misma:

| | |
|---|---|
| **El dinero ya se movió** | Un viático pedido, transferido o comprobado no se desanda a mano. Es el mismo candado que usa `deshacer` |
| **El día del regreso se partió** | Ese día ya está repartido entre los dos, con su hora. Moverlo sería rehacer una nómina |

En los dos casos lo que corresponde es un cambio nuevo, con su rastro, y
eso es lo que dice el 409.

Un detalle que costó encontrarlo: **el tope del mes se mudó a
`contingencia`**, junto al candado que lo exige. Escrito en dos lugares
es como el umbral de silencio, que acabó diciendo 60 en una pantalla y
120 en la otra."""
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("BITACORA.md: la correccion del regreso")

import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

VIEJO = """- **El calendario de cambios del implantado.** El formulario de cambio
  y el bloque de movimientos viven en la pantalla del servicio
  (`#/servicio/{id}`), que sirve igual para eventual y para implantado.
  La pantalla propia del implantado (`#/implantado/{id}`) tiene el
  contrato, la plantilla, los viáticos y el taller, pero no enlaza a la
  otra: el consultor tiene que llegar por la cartera. Falta el puente, y
  probablemente enseñar los movimientos del mes junto al calendario.
- **El regreso de la unidad.** `regresar()` cierra el movimiento de una
  persona. La unidad que sale del taller no lo necesita todavía porque
  su `hasta` viene del registro de taller, pero si algún día se manda un
  cambio de unidad sin fin, no hay con qué cerrarlo.
- **La hora del regreso no se guarda al lado.** El movimiento guarda
  `hora_propuesta` del relevo que lo abrió. Si el día del regreso se
  parte, esa hora vive en la asignación —que es de donde la lee la
  nómina— pero no queda la propuesta contra la cual compararla. Se nota
  solo si alguien quiere auditar una corrección de hora del regreso.
"""
NUEVO = """- **La revisión de la unidad que vuelve no se enseña.** Cuando una
  camioneta cambia de manos, el motor ya dice qué revisiones faltan
  —`revision_pendiente`: entregar la que sale, recibir la que entra— y
  **ninguna pantalla lo pinta**, ni en el cambio ni en el regreso. Si
  nadie registra cómo se recibió la unidad, un daño reclamado después no
  se le puede atribuir a nadie, que es exactamente lo que la revisión
  con fotos vino a resolver.
"""
assert s.count(VIEJO) == 1, "no encontre los tres pendientes"
s = s.replace(VIEJO, NUEVO)

ANCLA = """En los dos casos lo que corresponde es un cambio nuevo, con su rastro, y
eso es lo que dice el 409."""
EXTRA = """En los dos casos lo que corresponde es un cambio nuevo, con su rastro, y
eso es lo que dice el 409.

**La unidad también regresa.** El motor es el mismo con los nombres al
revés; lo único que no aplica es el candado del dinero, porque la unidad
no mueve viáticos: el combustible y las casetas siguen siendo del
conductor, que es el mismo.

**Las dos horas quedan guardadas.** `hora_propuesta` es la del relevo
que abrió el movimiento y `hora_propuesta_regreso` la del día que lo
cerró. Las dos pueden partir un día y las dos las puede corregir el
consultor; guardar la propuesta al lado es lo único que deja ver que la
corrigió."""
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, EXTRA)
R.write_text(s)
print("BITACORA.md: al dia")

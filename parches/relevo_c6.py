import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

VIEJO = """- **El relevo del implantado.** Su reemplazo vive aparte
  (`implantado.py`, tabla `Reemplazo`) y sigue mutando la asignacion:
  quien sale a media jornada cobra cero, igual que pasaba en eventual.
  Ahi pasa mas seguido, porque es operacion diaria con plantilla fija.
  El arreglo de fondo es el mismo —relevar en vez de mutar— pero cuidado
  con el alcance: el implantado reutiliza el mismo equipo mes tras mes,
  asi que necesita un tope duro (el mes en curso) antes de tocarlo.
"""

NUEVO = """- **El formulario de cambios del implantado.** El motor está hecho
  (sección 11 bis) y la pantalla del servicio ya tiene el bloque que
  lista los cambios, pero **no hay formulario**: hoy un cambio de
  personal o de unidad en un implantado solo se puede hacer por la API.
  Falta también decir en pantalla lo que la respuesta ya trae: qué días
  se partieron, hasta cuándo llega el tope y el botón de regreso del
  titular.
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

assert s.count(VIEJO) == 1, "no encontre el pendiente del relevo"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("BITACORA.md: pendientes al dia")

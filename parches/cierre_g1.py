import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

VIEJO = """- **El formulario de cambios del implantado.** El motor está hecho
  (sección 11 bis) y la pantalla del servicio ya tiene el bloque que
  lista los cambios, pero **no hay formulario**: hoy un cambio de
  personal o de unidad en un implantado solo se puede hacer por la API.
  Falta también decir en pantalla lo que la respuesta ya trae: qué días
  se partieron, hasta cuándo llega el tope y el botón de regreso del
  titular.
"""
NUEVO = """- **El calendario de cambios del implantado.** El formulario de cambio
  y el bloque de movimientos viven en la pantalla del servicio
  (`#/servicio/{id}`), que sirve igual para eventual y para implantado.
  La pantalla propia del implantado (`#/implantado/{id}`) tiene el
  contrato, la plantilla, los viáticos y el taller, pero no enlaza a la
  otra: el consultor tiene que llegar por la cartera. Falta el puente, y
  probablemente enseñar los movimientos del mes junto al calendario.
"""
assert s.count(VIEJO) == 1, "no encontre el pendiente del formulario"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("BITACORA.md: pendientes al dia")

import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

VIEJO = """- **No se le puede cortar el acceso a nadie, ni cambiarle el rol.**
  `Usuario.activo` se **lee** en tres lugares —y el candado funciona: en
  cuanto está en falso, la sesión abierta muere en la siguiente
  petición— pero **no se escribe en ninguna parte del sistema**. Y
  `Usuario.rol` solo se escribe en `seed.py`. Hoy, cortarle el acceso a
  alguien o cambiarle el puesto es un UPDATE a mano en Postgres. En una
  empresa de protección, un exempleado con sesión válida que ve dónde
  está cada ejecutivo es *la* falla. Ver `PROPUESTA_ACCESOS.md`.
"""
NUEVO = """- **El panel de accesos, para verlo y tocarlo.** El motor ya está (ver
  sección 15): desactivar, reactivar, cambiar rol, las dos
  recuperaciones y el código de campo, todo con sus candados y su
  bitácora. Lo que falta es la pantalla de administración —quién tiene
  acceso, con qué categoría, cuándo entró por última vez, quién nunca
  entró— y después las categorías configurables. Hoy todo eso se hace
  por API.
- **Las 59 puertas que preguntan por rol.** Son tres de cada cuatro del
  sistema. Un panel de permisos solo puede configurar las 19 que
  preguntan por actividad, así que mudarlas, pantalla por pantalla, es
  lo que hace que el panel de verdad controle el sistema y no una
  esquina.
- **El correo que no cuelga de un servicio.** `Notificacion.servicio_id`
  es obligatorio, así que no hay forma de mandar un correo de
  recuperación. Es el mismo patrón que tenía la bitácora, y ya van tres
  veces. Mientras tanto el enlace lo entrega administración a mano.
"""
assert s.count(VIEJO) == 1, "no encontre el pendiente de accesos"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("BITACORA.md: pendientes al dia")

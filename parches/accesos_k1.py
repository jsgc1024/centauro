import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

ANCLA = "- Restringir la llave de Google por IP del servidor."
NUEVO = """- **No se le puede cortar el acceso a nadie, ni cambiarle el rol.**
  `Usuario.activo` se **lee** en tres lugares —y el candado funciona: en
  cuanto está en falso, la sesión abierta muere en la siguiente
  petición— pero **no se escribe en ninguna parte del sistema**. Y
  `Usuario.rol` solo se escribe en `seed.py`. Hoy, cortarle el acceso a
  alguien o cambiarle el puesto es un UPDATE a mano en Postgres. En una
  empresa de protección, un exempleado con sesión válida que ve dónde
  está cada ejecutivo es *la* falla. Ver `PROPUESTA_ACCESOS.md`.
- **La baja en Odoo no cierra el acceso.** `odoo.sincronizar_personal`
  actualiza solo nombre, teléfono y foto; `activo` no está en la lista y
  `_sincronizar` nunca da de baja a nadie. Recursos humanos da de baja a
  alguien en Odoo —que es la fuente de verdad de empleados— y en Centauro
  su cuenta sigue viva.
- **No hay bitácora de catálogos.** `crud.py` —por donde se editan
  tarifarios, tarifas de recurso, de vehículo, de freelance y las
  comisiones del personal— no menciona la auditoría ni una vez. Y no cabe
  en la que existe: `RegistroAccion.servicio_id` es obligatorio, así que
  esa bitácora está amarrada a un servicio y un cambio de tarifario no
  tiene servicio al cual colgarse. **Cualquiera con rol de administración
  cambia el precio al cliente o la comisión del personal y no queda nada
  escrito.** Necesita tabla nueva.
- Restringir la llave de Google por IP del servidor."""
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("BITACORA.md: los tres huecos de acceso, escritos")

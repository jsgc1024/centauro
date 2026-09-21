"""El panel de accesos, en el banco de pruebas.

Con los cuatro casos que importan: la cuenta viva, la que nunca se
estreno, la que lleva meses dormida y --la fea-- la de alguien dado de
baja como empleado con el acceso todavia abierto.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/web/banco.html"
s = R.read_text()

VIEJO = '''  <a href="?p=panorama&i=es&d=roto">Panorama · mal día</a>'''
NUEVO = '''  <a href="?p=panorama&i=es&d=roto">Panorama · mal día</a>
  <a href="?p=accesos&i=es">Accesos</a>'''
assert s.count(VIEJO) == 1, "no encontre la barra de enlaces"
s = s.replace(VIEJO, NUEVO)

VIEJO = '''  } else if (PANTALLA === "servicio") {'''
NUEVO = '''  } else if (PANTALLA === "accesos") {
    const { pantallaAccesos } = await import("/consola/accesos.js");
    await pantallaAccesos(main);
  } else if (PANTALLA === "servicio") {'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

ANCLA = '''  "/servicios/equipos/1/recomendaciones": {'''
DATOS = '''  /* Los cuatro casos del panel de accesos. El ultimo es el que duele:
     dado de baja como empleado y con la puerta abierta. */
  "/auth/usuarios": [
    { usuario_id: 1, persona_id: 3, nombre: "Ana Solis",
      correo: "ana.solis@centauro.lat", rol: "consultor", activo: true,
      estrenado: true, ultimo_acceso: new Date(Date.now() - 12 * 60000).toISOString(),
      persona_de_baja: false },
    { usuario_id: 2, persona_id: 2, nombre: "Luis Mendoza",
      correo: "luismendoza88@gmail.com", rol: "personal_seguridad",
      activo: true, estrenado: false, ultimo_acceso: null,
      persona_de_baja: false },
    { usuario_id: 3, persona_id: 7, nombre: "Carlos Vega",
      correo: "carlos.vega@centauro.lat", rol: "central", activo: true,
      estrenado: true,
      ultimo_acceso: new Date(Date.now() - 130 * 86400000).toISOString(),
      persona_de_baja: false },
    { usuario_id: 4, persona_id: 11, nombre: "Hector Palacios",
      correo: "hector.palacios@centauro.lat", rol: "finanzas", activo: true,
      estrenado: true,
      ultimo_acceso: new Date(Date.now() - 40 * 86400000).toISOString(),
      persona_de_baja: true },
    { usuario_id: 5, persona_id: 12, nombre: "Raul Ortiz",
      correo: "raul.ortiz@freelance.mx", rol: "personal_seguridad",
      activo: false, estrenado: true,
      ultimo_acceso: new Date(Date.now() - 200 * 86400000).toISOString(),
      persona_de_baja: false },
  ],
  "/auth/usuarios/1/historial": [
    { accion: "rol cambiado", antes: "central", despues: "consultor",
      detalle: "Cambio de area", quien: "Admin Sistema",
      rol_de_quien: "admin",
      cuando: new Date(Date.now() - 90 * 86400000).toISOString() },
    { accion: "acceso creado", antes: null, despues: "central",
      detalle: "ana.solis@centauro.lat", quien: "Admin Sistema",
      rol_de_quien: "admin",
      cuando: new Date(Date.now() - 400 * 86400000).toISOString() },
  ],
  "/servicios/equipos/1/recomendaciones": {'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, DATOS)

# La sesion del banco tiene que poder abrir el panel.
VIEJO = '''sesion.usuario = { rol: "finanzas", nombre: "Laura Mendez", persona_id: 9 };'''
NUEVO = '''/* El panel de accesos es de administracion, asi que el banco entra con
   ese rol cuando se pide esa pantalla. Las demas siguen con finanzas. */
sesion.usuario = PANTALLA === "accesos"
  ? { rol: "admin", nombre: "Admin Sistema", persona_id: 1 }
  : { rol: "finanzas", nombre: "Laura Mendez", persona_id: 9 };'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

R.write_text(s)
print("banco.html: el panel de accesos, con sus cuatro casos")

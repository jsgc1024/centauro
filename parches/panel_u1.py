"""Paso 4: el panel entra al menu, al ruteo y al estilo."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- import que no se usa -------------------------------------------
R = RAIZ / "backend/app/web/accesos.js"
s = R.read_text()
VIEJO = 'import { aviso, entrada, etiqueta, h, lista, mensaje } from "./util.js";'
NUEVO = 'import { aviso, entrada, h, lista, mensaje } from "./util.js";'
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("accesos.js: sin el import de mas")

# --- ruteo y menu ----------------------------------------------------
R = RAIZ / "backend/app/web/app.js"
s = R.read_text()

VIEJO = 'import { pantallaCodigo } from "./codigo.js";'
NUEVO = ('import { pantallaAccesos } from "./accesos.js";\n'
         'import { pantallaCodigo } from "./codigo.js";')
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = "const CODIGO = [\"consultor\", \"central\", \"director_general\", \"admin\"];"
NUEVO = ("const CODIGO = [\"consultor\", \"central\", \"director_general\", \"admin\"];\n"
         "/* Quien reparte permisos. Direccion general quedo como super\n"
         "   administrador por decision de la direccion (ver PROPUESTA_ACCESOS.md):\n"
         "   quien puede abrir esta pantalla puede darle a alguien un permiso que\n"
         "   cuesta dinero. */\n"
         "const ADMINISTRA = [\"admin\", \"director_general\"];")
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''  [/^#\\/codigo$/, pantallaCodigo, CODIGO],
];'''
NUEVO = '''  [/^#\\/codigo$/, pantallaCodigo, CODIGO],
  [/^#\\/accesos$/, pantallaAccesos, ADMINISTRA],
];'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''  if (CODIGO.includes(rol)) nav.append(enlace("/codigo", t("nav_codigo")));'''
NUEVO = '''  if (CODIGO.includes(rol)) nav.append(enlace("/codigo", t("nav_codigo")));
  if (ADMINISTRA.includes(rol)) nav.append(enlace("/accesos", t("nav_accesos")));'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("app.js: ruta y menu del panel")

# --- estilo ----------------------------------------------------------
R = RAIZ / "backend/app/web/estilo.css"
s = R.read_text()
s += '''

/* ------------------------------------------------------ panel de accesos */

.renglon-acceso {
  display: flex; gap: 14px; align-items: center; flex-wrap: wrap;
  border-top: 1px solid var(--linea); padding: 12px 0;
}
.renglon-acceso > :first-child { flex: 1 1 220px; min-width: 0; }
.renglon-acceso > :nth-child(2) { flex: 0 0 150px; }
.renglon-acceso > :nth-child(3) { flex: 0 0 110px; }
.quien-acceso { min-width: 0; }
.quien-acceso .chico { overflow-wrap: anywhere; }

/* El acceso cerrado se ve apagado, no escondido: sigue siendo una
   cuenta que existe y a la que alguien le puede volver a abrir. */
.cerrado .renglon-acceso { opacity: .55; }

@media (max-width: 700px) {
  /* En telefono cada dato baja a su renglon: el puesto y el ultimo
     acceso apretados en 110px no se leen. */
  .renglon-acceso > :nth-child(2),
  .renglon-acceso > :nth-child(3) { flex: 1 1 auto; }
}
'''
R.write_text(s)
print("estilo.css: el panel")

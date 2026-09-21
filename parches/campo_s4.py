"""Paso 3d: la pantalla entra al menu y al ruteo, y su estilo."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

R = RAIZ / "backend/app/web/app.js"
s = R.read_text()

VIEJO = 'import { pantallaServicio } from "./servicio.js";'
NUEVO = ('import { pantallaCodigo } from "./codigo.js";\n'
         'import { pantallaServicio } from "./servicio.js";')
assert s.count(VIEJO) == 1, "no encontre el import de servicio"
s = s.replace(VIEJO, NUEVO)

VIEJO = 'const DINERO = ["finanzas", "director_operaciones", "director_general", "admin"];'
NUEVO = ('const DINERO = ["finanzas", "director_operaciones", "director_general", "admin"];\n'
         '/* Quien le dicta el codigo al personal de campo. La central porque\n'
         '   esta despierta a las 5:40, que es cuando de verdad pasa; el\n'
         '   consultor porque conoce a su gente por la voz, que es lo unico que\n'
         '   protege este camino. Direccion de operaciones no entra. */\n'
         'const CODIGO = ["consultor", "central", "director_general", "admin"];')
assert s.count(VIEJO) == 1, "no encontre DINERO"
s = s.replace(VIEJO, NUEVO)

VIEJO = '''  [/^#\\/nomina$/, pantallaNomina, DINERO],
];'''
NUEVO = '''  [/^#\\/nomina$/, pantallaNomina, DINERO],
  [/^#\\/codigo$/, pantallaCodigo, CODIGO],
];'''
assert s.count(VIEJO) == 1, "no encontre la tabla de rutas"
s = s.replace(VIEJO, NUEVO)

VIEJO = '''  if (CONSULTA.includes(rol)) nav.append(enlace("/equipo", t("nav_personal")));'''
NUEVO = '''  if (CONSULTA.includes(rol)) nav.append(enlace("/equipo", t("nav_personal")));
  /* A un toque, porque la llamada llega a las 5:40 y casi siempre al
     telefono. Escondida dentro de un servicio serian cuatro toques con
     una mano. */
  if (CODIGO.includes(rol)) nav.append(enlace("/codigo", t("nav_codigo")));'''
assert s.count(VIEJO) == 1, "no encontre el enlace de equipo"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("app.js: ruta y menu del codigo")

R = RAIZ / "backend/app/web/estilo.css"
s = R.read_text()
s += '''

/* ------------------------------------------- codigo de acceso de campo
   Pensada para telefono: la llamada de las 5:40 le llega al consultor en
   su casa. Los digitos grandes son para dictarlos sin equivocarse. */

.lista-codigo { margin-top: 12px; }

.persona-codigo {
  display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
  border-top: 1px solid var(--linea); padding: 12px 0;
}
.persona-codigo:first-child { border-top: 0; }
.persona-codigo .foto {
  width: 44px; height: 44px; border-radius: 50%; object-fit: cover;
  background: var(--linea); flex: 0 0 auto;
}
.datos-codigo { flex: 1 1 180px; min-width: 0; }
.persona-codigo button { flex: 0 0 auto; }

.codigo-grande { text-align: center; margin-top: 14px; }
.codigo-grande .digitos {
  font-size: 54px; font-weight: 700; letter-spacing: 6px;
  font-variant-numeric: tabular-nums; color: var(--centauro);
  margin: 6px 0 2px;
}

@media (max-width: 480px) {
  /* El boton baja a su propio renglon y ocupa el ancho: con una mano y
     medio dormido, un boton chico al lado de la foto se falla. */
  .persona-codigo button { flex: 1 1 100%; }
  .codigo-grande .digitos { font-size: 46px; letter-spacing: 4px; }
}
'''
R.write_text(s)
print("estilo.css: la tarjeta del codigo, pensada angosta")

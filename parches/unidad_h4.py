"""Chico 3b: la pantalla sabe regresar una unidad."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- el cierre devuelve lo que falta para la unidad ------------------
R = RAIZ / "backend/app/contingencia.py"
s = R.read_text()
VIEJO = '''        "hora_propuesta": hecho.get("hora_propuesta"),
        "viaticos": hecho["viaticos"],
    }'''
NUEVO = '''        "hora_propuesta": hecho.get("hora_propuesta"),
        "viaticos": hecho["viaticos"],
        # La unidad que vuelve cambia de manos otra vez: si nadie la
        # recibe, un golpe en ella se queda sin dueno.
        "revision_pendiente": hecho.get("revision_pendiente"),
    }'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("contingencia.py: la revision pendiente viaja en la respuesta")

# --- textos ----------------------------------------------------------
R = RAIZ / "backend/app/web/idioma.js"
s = R.read_text()
NUEVOS = {
'    srv_r_regresar: "Regresar a {p}",\n':
'    srv_r_regresar: "Regresar a {p}",\n    srv_r_regresar_u: "Regresar la unidad {p}",\n',
'    srv_r_regresar: "Bring {p} back",\n':
'    srv_r_regresar: "Bring {p} back",\n    srv_r_regresar_u: "Bring unit {p} back",\n',
'    srv_r_regresar: "Trazer {p} de volta",\n':
'    srv_r_regresar: "Trazer {p} de volta",\n    srv_r_regresar_u: "Trazer a unidade {p} de volta",\n',
'    srv_r_cuando: "¿Qué día regresa {p}?",\n':
'    srv_r_cuando: "¿Qué día regresa {p}?",\n    srv_r_cuando_u: "¿Qué día vuelve la unidad {p}?",\n',
'    srv_r_cuando: "What day does {p} come back?",\n':
'    srv_r_cuando: "What day does {p} come back?",\n    srv_r_cuando_u: "What day does unit {p} come back?",\n',
'    srv_r_cuando: "Que dia {p} volta?",\n':
'    srv_r_cuando: "Que dia {p} volta?",\n    srv_r_cuando_u: "Que dia a unidade {p} volta?",\n',
}
for viejo, nuevo in NUEVOS.items():
    assert s.count(viejo) == 1, viejo[:40]
    s = s.replace(viejo, nuevo)
R.write_text(s)
print("idioma.js: dos claves de unidad")

# --- pantalla --------------------------------------------------------
R = RAIZ / "backend/app/web/servicio.js"
s = R.read_text()

VIEJO = '''  if (r.tipo === "personal" && (r.en_curso || r.regreso_en)) {'''
NUEVO = '''  if (r.en_curso || r.regreso_en) {'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''          r.regreso_en
            ? t("srv_r_corregir")
            : t("srv_r_regresar").replace("{p}", r.sale || "?"))),'''
NUEVO = '''          r.regreso_en
            ? t("srv_r_corregir")
            : (r.tipo === "vehiculo"
               ? t("srv_r_regresar_u") : t("srv_r_regresar")
              ).replace("{p}", r.sale || "?"))),'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    h("h4", { style: "margin:0 0 2px" },
      t("srv_r_cuando").replace("{p}", r.sale || "?")),'''
NUEVO = '''    h("h4", { style: "margin:0 0 2px" },
      (r.tipo === "vehiculo" ? t("srv_r_cuando_u") : t("srv_r_cuando"))
        .replace("{p}", r.sale || "?")),'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# La unidad no mueve viaticos: el combustible y las casetas siguen
# siendo del conductor, que es el mismo.
VIEJO = '''    bloqueDinero(p.viaticos || {}, p.regresa || "?"),'''
NUEVO = '''    p.tipo === "vehiculo" ? "" : bloqueDinero(p.viaticos || {}, p.regresa || "?"),'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

R.write_text(s)
print("servicio.js: el regreso de la unidad")

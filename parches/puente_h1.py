"""Chico 1: el puente entre las dos pantallas del implantado.

El contrato, la plantilla, los viaticos y el taller viven en
`#/implantado/{id}`. El calendario, el equipo por dia y los cambios de
recurso viven en `#/servicio/{id}`. Las dos funcionan y no se hablan: el
consultor tiene que salirse a la cartera para pasar de una a la otra.
"""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- textos ----------------------------------------------------------
R = RAIZ / "backend/app/web/idioma.js"
s = R.read_text()
NUEVOS = {
'    imp_volver: "Volver a la cartera",\n':
'''    imp_volver: "Volver a la cartera",
    imp_ver_operacion: "Calendario y equipo",
''',
'    imp_volver: "Back to the list",\n':
'''    imp_volver: "Back to the list",
    imp_ver_operacion: "Calendar and team",
''',
'    imp_volver: "Voltar à carteira",\n':
'''    imp_volver: "Voltar à carteira",
    imp_ver_operacion: "Calendário e equipe",
''',
'    srv_eliminar: "Eliminar",\n':
'''    srv_eliminar: "Eliminar",
    srv_ver_contrato: "Contrato del mes",
''',
'    srv_eliminar: "Delete",\n':
'''    srv_eliminar: "Delete",
    srv_ver_contrato: "Monthly contract",
''',
'    srv_eliminar: "Excluir",\n':
'''    srv_eliminar: "Excluir",
    srv_ver_contrato: "Contrato do mês",
''',
}
for viejo, nuevo in NUEVOS.items():
    assert s.count(viejo) == 1, viejo[:40]
    s = s.replace(viejo, nuevo)
R.write_text(s)
print("idioma.js: las dos claves del puente")

# --- del contrato a la operacion -------------------------------------
R = RAIZ / "backend/app/web/implantado.js"
s = R.read_text()
VIEJO = '''    h("div", { clase: "acciones", style: "margin:0 0 16px" },
      h("button", { clase: "claro chico", type: "button",
        onclick: () => (location.hash = "#/implantados") },
        t("imp_volver"))));'''
NUEVO = '''    h("div", { clase: "acciones", style: "margin:0 0 16px" },
      h("button", { clase: "claro chico", type: "button",
        onclick: () => (location.hash = "#/implantados") },
        t("imp_volver")),
      /* El otro lado del mismo servicio: el calendario, quien va cada
         dia y los cambios de recurso. Sin esto hay que salirse a la
         cartera para pasar de una pantalla a la otra. */
      h("button", { clase: "claro chico", type: "button",
        onclick: () => (location.hash = `#/servicio/${servicioId}`) },
        t("imp_ver_operacion"))));'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("implantado.js: al calendario")

# --- de la operacion al contrato -------------------------------------
R = RAIZ / "backend/app/web/servicio.js"
s = R.read_text()
VIEJO = '''        h("div", { clase: "acciones bajo-sello" },
          ANTES_DE_ARRANCAR.includes(servicio.estatus)'''
NUEVO = '''        h("div", { clase: "acciones bajo-sello" },
          /* El otro lado del mismo servicio: el contrato del mes, la
             plantilla, los viaticos y el taller. Solo en implantado,
             porque un eventual no tiene contrato mensual. */
          servicio.tipo === "implantado"
            ? h("button", { clase: "claro chico", type: "button",
                onclick: () => (location.hash = `#/implantado/${servicio.id}`) },
                t("srv_ver_contrato"))
            : "",
          ANTES_DE_ARRANCAR.includes(servicio.estatus)'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("servicio.js: al contrato")

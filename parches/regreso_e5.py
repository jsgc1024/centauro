"""Paso 3b: los textos del formulario de regreso."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/web/idioma.js"
s = R.read_text()

NUEVOS = {
'    srv_r_regresar: "Regresar a {p}",\n':
'''    srv_r_regresar: "Regresar a {p}",
    srv_r_cuando: "¿Qué día regresa {p}?",
    srv_r_form_pie: "El que está cubriendo trabaja hasta el día anterior. No se pide motivo: es el del cambio que se cierra.",
    srv_r_ver: "Ver qué pasa",
    srv_r_vuelve_el: "{p} regresa el {f}",
    srv_r_trabaja_hasta: "{p} trabaja hasta el {f}",
    srv_r_devueltos: "{n} día(s) vuelven a {p}",
    srv_r_confirmar: "Confirmar el regreso",
    srv_r_hecho: "Regreso capturado",
''',
'    srv_r_regresar: "Bring {p} back",\n':
'''    srv_r_regresar: "Bring {p} back",
    srv_r_cuando: "What day does {p} come back?",
    srv_r_form_pie: "Whoever is covering works until the day before. No reason is asked: it is the one from the change being closed.",
    srv_r_ver: "See what happens",
    srv_r_vuelve_el: "{p} comes back on {f}",
    srv_r_trabaja_hasta: "{p} works until {f}",
    srv_r_devueltos: "{n} day(s) go back to {p}",
    srv_r_confirmar: "Confirm the return",
    srv_r_hecho: "Return recorded",
''',
'    srv_r_regresar: "Trazer {p} de volta",\n':
'''    srv_r_regresar: "Trazer {p} de volta",
    srv_r_cuando: "Que dia {p} volta?",
    srv_r_form_pie: "Quem está cobrindo trabalha até o dia anterior. Não se pede motivo: é o da troca que se fecha.",
    srv_r_ver: "Ver o que acontece",
    srv_r_vuelve_el: "{p} volta em {f}",
    srv_r_trabaja_hasta: "{p} trabalha até {f}",
    srv_r_devueltos: "{n} dia(s) voltam para {p}",
    srv_r_confirmar: "Confirmar o retorno",
    srv_r_hecho: "Retorno registrado",
''',
}
for viejo, nuevo in NUEVOS.items():
    assert s.count(viejo) == 1, viejo[:40]
    s = s.replace(viejo, nuevo)
R.write_text(s)
print("idioma.js: nueve claves del formulario de regreso")

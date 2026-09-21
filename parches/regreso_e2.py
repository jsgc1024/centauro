"""Paso 2a: los textos de la tarjeta."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/web/idioma.js"
s = R.read_text()

NUEVOS = {
'    srv_formalizo: "Formalizó: {p}",\n':
'''    srv_formalizo: "Formalizó: {p}",
    srv_r_en_curso: "En curso",
    srv_r_cerrado: "Cerrado",
    srv_r_terminado: "Terminado",
    srv_r_cerro: "Regreso capturado por {p} el {f}",
    srv_r_partido: "{f}: día partido — {p} cobra hasta las {h}",
    srv_r_repedir: "Después del {f} hay que volver a pedirlo.",
    srv_r_regresar: "Regresar a {p}",
''',
'    srv_formalizo: "Recorded by: {p}",\n':
'''    srv_formalizo: "Recorded by: {p}",
    srv_r_en_curso: "Running",
    srv_r_cerrado: "Closed",
    srv_r_terminado: "Ended",
    srv_r_cerro: "Return recorded by {p} on {f}",
    srv_r_partido: "{f}: split day — {p} is paid up to {h}",
    srv_r_repedir: "After {f} it has to be requested again.",
    srv_r_regresar: "Bring {p} back",
''',
'    srv_formalizo: "Formalizou: {p}",\n':
'''    srv_formalizo: "Formalizou: {p}",
    srv_r_en_curso: "Em curso",
    srv_r_cerrado: "Fechado",
    srv_r_terminado: "Terminado",
    srv_r_cerro: "Retorno registrado por {p} em {f}",
    srv_r_partido: "{f}: dia partido — {p} recebe até as {h}",
    srv_r_repedir: "Depois de {f} é preciso pedir de novo.",
    srv_r_regresar: "Trazer {p} de volta",
''',
}
for viejo, nuevo in NUEVOS.items():
    assert s.count(viejo) == 1, viejo[:40]
    s = s.replace(viejo, nuevo)
R.write_text(s)
print("idioma.js: siete claves de la tarjeta, en es, en y pt")

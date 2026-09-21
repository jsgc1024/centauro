"""Entrega 1b: los textos nuevos del tope."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/web/idioma.js"
s = R.read_text()

NUEVOS = {
'    srv_alcance_pie: "Una contingencia no tiene fin: nadie sabe cuándo vuelve el que salió. Unas vacaciones sí.",\n':
'''    srv_alcance_pie: "Una contingencia no tiene fin: nadie sabe cuándo vuelve el que salió. Unas vacaciones sí.",
    srv_hasta_fin_mes: " Hasta el fin del mes",
    srv_alcance_imp_pie: "El implantado reutiliza el mismo equipo mes tras mes, así que un cambio sin fin se llevaría también el mes que sigue. Por eso se detiene el último día del mes en curso.",
    srv_tope: "Se detiene el {f}. Para el mes siguiente hay que volver a pedirlo.",
''',
'    srv_alcance_pie: "A contingency has no end date: nobody knows when the person who left comes back. A vacation does.",\n':
'''    srv_alcance_pie: "A contingency has no end date: nobody knows when the person who left comes back. A vacation does.",
    srv_hasta_fin_mes: " Until the end of the month",
    srv_alcance_imp_pie: "An embedded service reuses the same team month after month, so an open-ended change would sweep the next month too. That is why it stops on the last day of the current month.",
    srv_tope: "It stops on {f}. For the next month it has to be requested again.",
''',
'    srv_alcance_pie: "Uma contingência não tem fim: ninguém sabe quando volta quem saiu. Umas férias sim.",\n':
'''    srv_alcance_pie: "Uma contingência não tem fim: ninguém sabe quando volta quem saiu. Umas férias sim.",
    srv_hasta_fin_mes: " Até o fim do mês",
    srv_alcance_imp_pie: "O implantado reutiliza a mesma equipe mês após mês, então uma troca sem fim levaria também o mês seguinte. Por isso ela para no último dia do mês em curso.",
    srv_tope: "Para em {f}. Para o mês seguinte é preciso pedir de novo.",
''',
}

for viejo, nuevo in NUEVOS.items():
    assert s.count(viejo) == 1, viejo[:50]
    s = s.replace(viejo, nuevo)

R.write_text(s)
print("idioma.js: tres claves en es, en y pt")

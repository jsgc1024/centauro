"""Paso 3c: los textos de la pantalla del codigo."""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/web/idioma.js"
s = R.read_text()

BLOQUES = {
'    nav_personal:': '''    nav_codigo: "Código",
    cod_titulo: "Código de acceso",
    cod_pie: "Para el de campo que no puede entrar a la app. Le dictas el código por teléfono y él pone su contraseña ahí mismo.",
    cod_buscar: "Escribe su nombre",
    cod_dos_letras: "Escribe al menos dos letras.",
    cod_nadie: "Nadie con ese nombre entre tu gente.",
    cod_generar: "Generar código",
    cod_confirma: "Antes de dictarlo, confirma que es él.",
    cod_hoy: "Hoy en {s}",
    cod_sin_hoy: "Hoy no trae servicio",
    cod_sin_estrenar: "Nunca ha entrado",
    cod_ya_tiene: "Ya tiene un código vigente. Si generas otro, el anterior deja de servir.",
    cod_vence: "Vence en {m}",
    cod_vencido: "Ya venció. Genera otro.",
    cod_dictalo: "{p} lo escribe en la app y pone su contraseña.",
    cod_una_vez: "No se vuelve a mostrar. Si se pierde, genera otro.",
    cod_cerrar: "Cerrar",
    nav_personal:''',
'    nav_personal: "Team"': '''    nav_codigo: "Code",
    cod_titulo: "Access code",
    cod_pie: "For field staff who cannot get into the app. You read them the code over the phone and they set their password there.",
    cod_buscar: "Type their name",
    cod_dos_letras: "Type at least two letters.",
    cod_nadie: "Nobody by that name among your people.",
    cod_generar: "Generate code",
    cod_confirma: "Before reading it out, confirm it is them.",
    cod_hoy: "Today on {s}",
    cod_sin_hoy: "No service today",
    cod_sin_estrenar: "Never signed in",
    cod_ya_tiene: "They already have a live code. A new one voids the previous.",
    cod_vence: "Expires in {m}",
    cod_vencido: "It expired. Generate another.",
    cod_dictalo: "{p} types it in the app and sets their password.",
    cod_una_vez: "It is not shown again. If lost, generate another.",
    cod_cerrar: "Close",
    nav_personal: "Team"''',
'    nav_personal: "Equipe"': '''    nav_codigo: "Código",
    cod_titulo: "Código de acesso",
    cod_pie: "Para quem está em campo e não consegue entrar no app. Você dita o código por telefone e ele define a senha ali mesmo.",
    cod_buscar: "Escreva o nome",
    cod_dos_letras: "Escreva pelo menos duas letras.",
    cod_nadie: "Ninguém com esse nome entre a sua gente.",
    cod_generar: "Gerar código",
    cod_confirma: "Antes de ditar, confirme que é ele.",
    cod_hoy: "Hoje em {s}",
    cod_sin_hoy: "Hoje não tem serviço",
    cod_sin_estrenar: "Nunca entrou",
    cod_ya_tiene: "Já tem um código válido. Se gerar outro, o anterior deixa de servir.",
    cod_vence: "Vence em {m}",
    cod_vencido: "Já venceu. Gere outro.",
    cod_dictalo: "{p} escreve no app e define a senha.",
    cod_una_vez: "Não se mostra de novo. Se perder, gere outro.",
    cod_cerrar: "Fechar",
    nav_personal: "Equipe"''',
}

# El primero es el de espanol: se ancla en la primera aparicion.
primero = BLOQUES.pop('    nav_personal:')
i = s.index('    nav_personal:')
s = s[:i] + primero + s[i + len('    nav_personal:'):]

for viejo, nuevo in BLOQUES.items():
    assert s.count(viejo) == 1, viejo[:40]
    s = s.replace(viejo, nuevo)

R.write_text(s)
print("idioma.js: diecisiete claves de la pantalla del codigo")

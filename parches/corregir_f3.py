"""Entrega 4c: la pantalla sabe corregir un regreso."""
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# --- textos ----------------------------------------------------------
R = RAIZ / "backend/app/web/idioma.js"
s = R.read_text()
NUEVOS = {
'    srv_r_hecho: "Regreso capturado",\n':
'''    srv_r_hecho: "Regreso capturado",
    srv_r_corregir: "Corregir el regreso",
    srv_r_recuperados: "{p} recupera {n} día(s)",
    srv_r_corregir_pie: "Si el dinero de esos días ya se movió, no se puede correr: hay que hacer un cambio nuevo.",
''',
'    srv_r_hecho: "Return recorded",\n':
'''    srv_r_hecho: "Return recorded",
    srv_r_corregir: "Change the return date",
    srv_r_recuperados: "{p} takes back {n} day(s)",
    srv_r_corregir_pie: "If the money for those days already moved, it cannot be shifted: a new change is needed.",
''',
'    srv_r_hecho: "Retorno registrado",\n':
'''    srv_r_hecho: "Retorno registrado",
    srv_r_corregir: "Corrigir o retorno",
    srv_r_recuperados: "{p} recupera {n} dia(s)",
    srv_r_corregir_pie: "Se o dinheiro desses dias já se moveu, não dá para mudar: é preciso uma troca nova.",
''',
}
for viejo, nuevo in NUEVOS.items():
    assert s.count(viejo) == 1, viejo[:40]
    s = s.replace(viejo, nuevo)
R.write_text(s)
print("idioma.js: tres claves de la correccion")

# --- pantalla --------------------------------------------------------
R = RAIZ / "backend/app/web/servicio.js"
s = R.read_text()

VIEJO = '''function abrirRegreso(zona, r) {
  const minimo = diaSiguiente(r.desde);
  const hoy = new Date().toISOString().slice(0, 10);
  let valor = hoy < minimo ? minimo : hoy;
  if (r.hasta && valor > r.hasta) valor = r.hasta;

  const dia = h("input", { type: "date", value: valor, min: minimo });
  if (r.hasta) dia.max = r.hasta;

  const previa = h("div", { style: "margin-top:12px" });
  const ver = h("button", { clase: "chico", type: "button",
    onclick: (e) => verPreviaRegreso(e, previa, r, dia.value) },
    t("srv_r_ver"));

  zona.replaceChildren(h("div", { clase: "tarjeta lisa" },
    h("h4", { style: "margin:0 0 2px" },
      t("srv_r_cuando").replace("{p}", r.sale || "?")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      t("srv_r_form_pie")),
    h("div", { clase: "acciones" }, dia, ver),
    previa));
}'''
NUEVO = '''function abrirRegreso(zona, r) {
  /* Corregir es capturar otra vez: el movimiento se recorre y se vuelve
     a firmar. Lo unico distinto es el techo del calendario --un regreso
     que se atrasa va mas alla del ultimo dia de hoy-- y lo que hay que
     advertir, que es el candado del dinero. */
  const corrige = Boolean(r.regreso_en);
  const minimo = diaSiguiente(r.desde);
  const hoy = new Date().toISOString().slice(0, 10);
  let valor = hoy < minimo ? minimo : hoy;
  if (!corrige && r.hasta && valor > r.hasta) valor = r.hasta;

  const dia = h("input", { type: "date", value: valor, min: minimo });
  if (!corrige && r.hasta) dia.max = r.hasta;

  const previa = h("div", { style: "margin-top:12px" });
  const ver = h("button", { clase: "chico", type: "button",
    onclick: (e) => verPreviaRegreso(e, previa, r, dia.value) },
    t("srv_r_ver"));

  zona.replaceChildren(h("div", { clase: "tarjeta lisa" },
    h("h4", { style: "margin:0 0 2px" },
      t("srv_r_cuando").replace("{p}", r.sale || "?")),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      corrige ? t("srv_r_corregir_pie") : t("srv_r_form_pie")),
    h("div", { clase: "acciones" }, dia, ver),
    previa));
}'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# El recuadro dice quien se lleva los dias, segun el sentido.
VIEJO = '''  const devueltos = (p.jornadas_devueltas || []).length;'''
NUEVO = '''  const devueltos = (p.jornadas_devueltas || []).length;
  const recuperados = (p.jornadas_recuperadas || []).length;'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

VIEJO = '''    h("div", { clase: "chico gris", style: "margin-top:4px" },
      t("srv_r_devueltos").replace("{n}", devueltos)
        .replace("{p}", p.regresa || "?")),'''
NUEVO = '''    h("div", { clase: "chico gris", style: "margin-top:4px" },
      recuperados
        ? t("srv_r_recuperados").replace("{n}", recuperados)
            .replace("{p}", p.sale || "?")
        : t("srv_r_devueltos").replace("{n}", devueltos)
            .replace("{p}", p.regresa || "?")),'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# El boton tambien aparece en un movimiento ya cerrado.
VIEJO = '''  if (r.en_curso && r.tipo === "personal") {
    const zona = h("div", { style: "margin-top:10px" });
    tarjeta.append(
      h("div", { clase: "acciones", style: "margin-top:8px" },
        h("button", { clase: "claro chico", type: "button",
          onclick: () => abrirRegreso(zona, r) },
          t("srv_r_regresar").replace("{p}", r.sale || "?"))),
      zona);
  }'''
NUEVO = '''  if (r.tipo === "personal" && (r.en_curso || r.regreso_en)) {
    const zona = h("div", { style: "margin-top:10px" });
    tarjeta.append(
      h("div", { clase: "acciones", style: "margin-top:8px" },
        h("button", { clase: "claro chico", type: "button",
          onclick: () => abrirRegreso(zona, r) },
          r.regreso_en
            ? t("srv_r_corregir")
            : t("srv_r_regresar").replace("{p}", r.sale || "?"))),
      zona);
  }'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

R.write_text(s)
print("servicio.js: corregir el regreso")

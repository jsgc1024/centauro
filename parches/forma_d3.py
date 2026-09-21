"""Entrega 1c: el formulario apunta a la puerta que corresponde.

El implantado y el eventual hacen el mismo cambio, pero por puertas
distintas: la del implantado es la que pone el tope del mes. Antes la
pantalla mandaba todo a la de eventual, asi que la opcion que viene
marcada por omision --"de aqui en adelante"-- devolvia un 409 en un
implantado.
"""
import pathlib

R = pathlib.Path(__file__).resolve().parent.parent / "backend/app/web/servicio.js"
s = R.read_text()

# --- 1. la puerta ----------------------------------------------------
ANCLA = "async function abrirCambio(zona, servicio, equipo, cat, persona, datos) {"
PUERTA = '''/* Las dos puertas hacen el mismo cambio y por dentro es el mismo motor.
   La del implantado ademas pone el tope: un cambio sin fecha de fin
   llega al ultimo dia del mes en curso. Esa regla vive en el servidor y
   no aqui: el navegador solo pregunta por cual puerta entra. */
function puertaDe(servicio) {
  return servicio.tipo === "implantado"
    ? { previa: `/implantados/${servicio.id}/cambios/vista-previa`,
        guardar: `/implantados/${servicio.id}/cambios`,
        entra: "entra_id", implantado: true }
    : { previa: "/contingencia/reemplazos/personal/vista-previa",
        guardar: "/contingencia/reemplazos/personal",
        entra: "entra_persona_id", implantado: false };
}

async function abrirCambio(zona, servicio, equipo, cat, persona, datos) {'''
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, PUERTA)

# --- 2. el cuerpo del cambio, segun la puerta ------------------------
VIEJO = '''  const armar = () => ({
    desde_jornada_id: Number(desde.value),
    hasta_jornada_id: conFin.checked ? Number(hasta.value) : null,
    sale_persona_id: persona.persona_id,
    motivo: nota.value.trim() || MOTIVOS.find(x => x.valor === motivo.value).texto,
    motivo_tipo: motivo.value,
  });
'''
NUEVO = '''  /* La puerta del implantado habla de fechas y la de eventual de
     jornadas. Es la misma eleccion del consultor dicha de dos maneras. */
  const fechaDe = new Map(dias.map(j => [String(j.id), j.fecha]));

  const armar = () => (puerta.implantado
    ? { tipo: "personal",
        desde: fechaDe.get(desde.value),
        hasta: conFin.checked ? fechaDe.get(hasta.value) : null,
        sale_id: persona.persona_id,
        motivo: motivo.value,
        nota: nota.value.trim() || null }
    : { desde_jornada_id: Number(desde.value),
        hasta_jornada_id: conFin.checked ? Number(hasta.value) : null,
        sale_persona_id: persona.persona_id,
        motivo: nota.value.trim()
                || MOTIVOS.find(x => x.valor === motivo.value).texto,
        motivo_tipo: motivo.value });
'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# `puerta` tiene que existir antes de armar(). Se declara arriba del todo.
VIEJO = '''async function abrirCambio(zona, servicio, equipo, cat, persona, datos) {
  const dias = diasPendientes(equipo);'''
NUEVO = '''async function abrirCambio(zona, servicio, equipo, cat, persona, datos) {
  const puerta = puertaDe(servicio);
  const dias = diasPendientes(equipo);'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# --- 3. la etiqueta del alcance dice la verdad -----------------------
VIEJO = '''        h("label", { clase: "chico" }, adelante, t("srv_adelante")),
        h("label", { clase: "chico", style: "margin-left:12px" },
          conFin, t("srv_hasta_el_dia")), hasta,
        h("div", { clase: "gris chico", style: "margin-top:4px" },
          t("srv_alcance_pie"))))),'''
NUEVO = '''        h("label", { clase: "chico" }, adelante,
          t(puerta.implantado ? "srv_hasta_fin_mes" : "srv_adelante")),
        h("label", { clase: "chico", style: "margin-left:12px" },
          conFin, t("srv_hasta_el_dia")), hasta,
        h("div", { clase: "gris chico", style: "margin-top:4px" },
          t(puerta.implantado ? "srv_alcance_imp_pie"
                              : "srv_alcance_pie"))))),'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

# --- 4. la puerta viaja hasta el boton de confirmar ------------------
CAMBIOS = [
    ('      tablaCandidatos(r.personal, persona, armar, previa));',
     '      tablaCandidatos(r.personal, persona, armar, previa, puerta));'),
    ('function tablaCandidatos(bloque, sale, armar, previa) {',
     'function tablaCandidatos(bloque, sale, armar, previa, puerta) {'),
    ('      h("td", {}, botonElegir(est, (e) => verPrevia(e, previa, armar(), p)))));',
     '      h("td", {}, botonElegir(est,\n'
     '        (e) => verPrevia(e, previa, armar(), p, puerta)))));'),
    ('async function verPrevia(e, zona, cambio, entra) {',
     'async function verPrevia(e, zona, cambio, entra, puerta) {'),
    ('  const cuerpo = { ...cambio, entra_persona_id: entra.persona_id };',
     '  const cuerpo = { ...cambio, [puerta.entra]: entra.persona_id };'),
    ('''    const r = await api.post("/contingencia/reemplazos/personal/vista-previa",
                             cuerpo);
    zona.replaceChildren(recuadroPrevia(r, cuerpo, entra));''',
     '''    const r = await api.post(puerta.previa, cuerpo);
    zona.replaceChildren(recuadroPrevia(r, cuerpo, entra, puerta));'''),
    ('function recuadroPrevia(r, cuerpo, entra) {',
     'function recuadroPrevia(r, cuerpo, entra, puerta) {'),
    ('''        await api.post("/contingencia/reemplazos/personal",
                       corregida ? { ...cuerpo, relevado_en: corregida }
                                 : cuerpo);''',
     '''        await api.post(puerta.guardar,
                       corregida ? { ...cuerpo, relevado_en: corregida }
                                 : cuerpo);'''),
]
for viejo, nuevo in CAMBIOS:
    assert s.count(viejo) == 1, viejo[:60]
    s = s.replace(viejo, nuevo)

# --- 5. el tope se dice en voz alta ---------------------------------
VIEJO = '''    h("div", { clase: "chico" },
      t("srv_entra"), h("b", {}, entra.nombre), t("srv_mismo_rol")),'''
NUEVO = '''    h("div", { clase: "chico" },
      t("srv_entra"), h("b", {}, entra.nombre), t("srv_mismo_rol")),
    /* El consultor pidio "hasta el fin del mes" y el sistema decidio
       cual es ese dia. Decirlo aqui evita que en octubre nadie se
       acuerde de que el cambio ya termino. */
    r.tope_automatico
      ? h("div", { clase: "chico gris", style: "margin-top:4px" },
          t("srv_tope").replace("{f}", fecha(r.hasta)))
      : "",'''
assert s.count(VIEJO) == 1
s = s.replace(VIEJO, NUEVO)

R.write_text(s)
print("servicio.js: el formulario entra por la puerta que corresponde")

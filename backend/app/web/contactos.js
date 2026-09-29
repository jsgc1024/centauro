/* Corregir los contactos del servicio (seccion 95).

   Pieza 2 de «Para poder operar» (decision 3 de Salvador, 28 sep). El
   correo y el telefono de quien solicita y del principal se capturan en
   el alta, y ya no se podian corregir: un correo mal escrito mandaba a
   otro lado los avisos del dia, el task sheet y la encuesta, y la unica
   salida era borrar el servicio y darlo de alta otra vez. Los corrige
   quien hace el alta --el consultor del servicio, o quien lo cubre, que
   queda anotado como cobertura--, mientras el servicio no este cerrado
   ni cancelado.

   Lo que cambia se marca y lleva lo de antes debajo: quien guarda ve
   exactamente que va a cambiar. Y solo se manda lo que cambio: un
   principal que nunca se capturo no detiene la correccion del correo de
   quien solicita. */
import { api } from "./api.js";
import { aviso, conAyuda, h, mensaje } from "./util.js";
import { IDIOMAS, t } from "./idioma.js";

/* La misma forma que pide el servidor. El revisa ademas los dominios
   mal escritos --gamil.com, hotmial.com-- y lo dice al guardar. */
const FORMA_DE_CORREO = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/* Lo que se dice al guardar sobrevive a la recarga: la pantalla se pinta
   de nuevo entera, para que el encabezado, los equipos y la cotizacion
   traigan los datos nuevos, y el aviso sale una sola vez. */
const LLAVE = "centauro_contactos_corregidos";

const CAMPOS = ["nombre", "apellidos", "correo", "telefono"];

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (s, [k, v]) => s.split(`{${k}}`).join(v ?? ""), texto);
}

/* Como lo guarda el servidor: sin espacios de mas, y el correo sin
   ninguno. Asi lo que se marca como cambiado es lo que de verdad cambia. */
function limpiar(llave, valor) {
  const texto = String(valor ?? "");
  return llave === "correo" ? texto.replace(/\s+/g, "")
                            : texto.split(/\s+/).filter(Boolean).join(" ");
}

const nombreDe = (c) => [c.nombre, c.apellidos].filter(Boolean).join(" ");

function nombreDelIdioma(codigo) {
  const i = IDIOMAS.find(x => x.codigo === codigo);
  return i ? i.nombre : codigo;
}

/* ------------------------------------------------------------ el boton */

/* El mismo boton abre la forma debajo de los contactos y la cierra. */
export function botonContactos(servicio, cliente, zona) {
  return h("button", { clase: "claro chico", type: "button",
    onclick: () => abrir(servicio, cliente, zona) }, t("con_corregir"));
}

/* Lo que se dijo al guardar, una sola vez, debajo de los contactos. */
export function avisoDeContactos(servicio) {
  let guardado = null;
  try {
    guardado = JSON.parse(sessionStorage.getItem(LLAVE) || "null");
    sessionStorage.removeItem(LLAVE);
  } catch { return ""; }
  if (!guardado || guardado.servicio !== servicio.id) return "";
  return h("div", { style: "margin-top:12px" },
    aviso(guardado.lineas.map(l => h("div", {}, l)), "ok"));
}

async function abrir(servicio, cliente, zona) {
  if (zona.firstChild) {
    zona.replaceChildren();
    return;
  }
  let d;
  try {
    d = await api.get(`/servicios/${servicio.id}/contactos`);
  } catch (err) {
    mensaje(err.message, "grave");
    return;
  }
  if (!d.se_puede) {
    mensaje(t("con_cerrado"), "alerta");
    return;
  }
  zona.replaceChildren(forma(servicio, cliente, zona, d));
  zona.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* ------------------------------------------------------------ un campo */

/* Un campo que recuerda lo que traia: si cambia, se marca y dice lo de
   antes debajo. Si se regresa a lo de antes, se desmarca solo. */
function campoQueRecuerda(llave, rotulo, original, alCambiar, atributos = {}) {
  const antes = limpiar(llave, original);
  const control = h("input", atributos);
  control.value = original || "";
  const nota = h("div", { clase: "chico gris ctc-antes", hidden: "hidden" });
  const caja = h("div", { clase: "campo" }, h("label", {}, rotulo), control, nota);
  caja.control = control;
  caja.valor = () => limpiar(llave, control.value);
  caja.cambio = () => caja.valor() !== antes;
  caja.repintar = () => {
    const cambio = caja.cambio();
    control.classList.toggle("ctc-cambio", cambio);
    nota.hidden = !cambio;
    nota.textContent = antes ? reemplazar(t("con_antes"), { v: antes })
                             : t("con_antes_vacio");
  };
  caja.poner = (valor) => {
    control.value = valor || "";
    caja.repintar();
  };
  control.addEventListener("input", () => { caja.repintar(); alCambiar(); });
  return caja;
}

/* En que idioma le llegan sus correos, su encuesta y su task sheet. */
function idiomaQueRecuerda(original, alCambiar) {
  const control = h("select", {},
    ...IDIOMAS.map(i => h("option", { value: i.codigo },
                          `${i.bandera} ${i.nombre}`)));
  control.value = original;
  const nota = h("div", { clase: "chico gris ctc-antes", hidden: "hidden" },
    reemplazar(t("con_antes"), { v: nombreDelIdioma(original) }));
  const caja = h("div", { clase: "campo" },
    h("label", {}, t("con_idioma")), control, nota);
  caja.control = control;
  caja.valor = () => control.value;
  caja.cambio = () => control.value !== original;
  caja.repintar = () => {
    control.classList.toggle("ctc-cambio", caja.cambio());
    nota.hidden = !caja.cambio();
  };
  control.addEventListener("change", () => { caja.repintar(); alCambiar(); });
  return caja;
}

/* Una persona: nombre, apellidos, correo y telefono, y su idioma si lo
   lleva --el principal de un equipo lee en el del principal del
   servicio--. */
function persona(datos, alCambiar, conIdioma) {
  const p = {
    nombre: campoQueRecuerda("nombre", t("nombre"), datos.nombre, alCambiar),
    apellidos: campoQueRecuerda("apellidos", t("apellido"), datos.apellidos,
                                alCambiar),
    correo: campoQueRecuerda("correo", t("correo_campo"), datos.correo,
                             alCambiar, { type: "email" }),
    telefono: campoQueRecuerda("telefono", t("telefono"), datos.telefono,
                               alCambiar, { inputmode: "tel" }),
    idioma: conIdioma ? idiomaQueRecuerda(datos.idioma, alCambiar) : null,
  };
  const todos = [p.nombre, p.apellidos, p.correo, p.telefono, p.idioma]
    .filter(Boolean);
  p.cambio = () => todos.some(c => c.cambio());
  p.datos = () => ({
    nombre: p.nombre.valor(),
    apellidos: p.apellidos.valor() || null,
    correo: p.correo.valor() || null,
    telefono: p.telefono.valor() || null,
    ...(p.idioma ? { idioma: p.idioma.valor() } : {}),
  });
  return p;
}

/* Lo que no se puede mandar se dice aqui, en el idioma de quien lo
   escribe, y el cursor se va al campo. El servidor lo revisa igual. */
function queFalta(p, quien) {
  if (!p.nombre.valor()) {
    return [p.nombre.control, reemplazar(t("con_falta_nombre"), { q: quien })];
  }
  const correo = p.correo.valor();
  if (correo && !FORMA_DE_CORREO.test(correo)) {
    return [p.correo.control, reemplazar(t("con_correo_mal"), { q: quien })];
  }
  return null;
}

/* ------------------------------------------------------------ la forma */

function forma(servicio, cliente, zona, d) {
  const guardar = h("button", { type: "button", disabled: "disabled",
    onclick: () => mandar() }, t("con_guardar"));
  const nadaTodavia = h("span", { clase: "chico gris" }, t("con_sin_cambios"));
  let secciones = [];

  function alCambiar() {
    const hay = secciones.some(p => p.cambio());
    guardar.disabled = !hay;
    nadaTodavia.hidden = hay;
  }

  const principal = persona(d.ejecutivo, alCambiar, true);
  const solicita = columnaSolicita(d, cliente, alCambiar);
  const equipos = d.equipos.map(e => ({
    id: e.equipo_id, alias: e.alias, p: persona(e, alCambiar, false) }));
  secciones = [principal, solicita.p, ...equipos.map(e => e.p)];

  async function mandar() {
    const cuerpo = {};
    const porRevisar = [];
    if (principal.cambio()) {
      porRevisar.push([principal, t("con_q_principal")]);
      cuerpo.ejecutivo = principal.datos();
    }
    if (solicita.p.cambio()) {
      porRevisar.push([solicita.p, t("con_q_solicita")]);
      cuerpo.solicitante = { ...solicita.p.datos(),
                             solicitante_id: solicita.p.elegido(),
                             corregir_en_lista: solicita.p.enLista() };
    }
    const cambiados = equipos.filter(e => e.p.cambio());
    for (const e of cambiados) {
      porRevisar.push([e.p, reemplazar(t("con_q_equipo"), { a: e.alias })]);
    }
    if (cambiados.length) {
      cuerpo.equipos = cambiados.map(e => ({ equipo_id: e.id, ...e.p.datos() }));
    }
    for (const [p, quien] of porRevisar) {
      const falta = queFalta(p, quien);
      if (falta) {
        falta[0].focus();
        mensaje(falta[1], "alerta");
        return;
      }
    }
    if (!porRevisar.length) {
      mensaje(t("con_sin_cambios"), "alerta");
      return;
    }

    guardar.disabled = true;
    guardar.textContent = t("con_guardando");
    try {
      const r = await api.patch(`/servicios/${servicio.id}/contactos`, cuerpo);
      if (!r.cambios.length) {
        mensaje(t("con_nada_cambio"), "alerta");
        zona.replaceChildren();
        return;
      }
      const lineas = [t("con_listo")];
      if (r.avisos) lineas.push(reemplazar(t("con_listo_avisos"), { n: r.avisos }));
      if (r.encuestas) lineas.push(t("con_listo_encuesta"));
      /* La encuesta que no habia nacido por falta de correo, con el
         servicio ya terminado, sale con la correccion (seccion 101). */
      if ((r.encuestas_nuevas || []).length) lineas.push(t("con_listo_encuesta_nueva"));
      if (r.lista_corregida) lineas.push(t("con_listo_lista"));
      if ((r.otros_servicios || []).length) {
        lineas.push(reemplazar(t("con_listo_otros"),
                               { f: r.otros_servicios.join(", ") }));
      }
      if (r.task_sheet_liberado) lineas.push(t("con_listo_ts"));
      try {
        sessionStorage.setItem(LLAVE, JSON.stringify({ servicio: servicio.id,
                                                       lineas }));
      } catch { /* sin el aviso; lo guardado ya esta guardado */ }
      location.reload();
    } catch (err) {
      guardar.textContent = t("con_guardar");
      alCambiar();
      mensaje(err.message, "grave");
    }
  }

  return h("div", { clase: "tarjeta lisa", style: "margin:16px 0 0" },
    conAyuda("h3", t("con_corregir"), "ay_con", { style: "margin:0" }),
    h("p", { clase: "chico gris", style: "margin:4px 0 14px" }, t("con_sub")),
    /* En el orden del encabezado: cada columna queda debajo de lo que
       corrige. */
    h("div", { clase: "rejilla dos" },
      h("div", {}, h("h4", {}, t("srv_ejecutivo")), ...cuerpoDe(principal)),
      solicita.nodo),
    ...equipos.map(e => h("div", {},
      h("h4", { clase: "grupo" }, reemplazar(t("con_equipo"), { a: e.alias })),
      h("p", { clase: "chico gris", style: "margin:-2px 0 10px" },
        t("con_equipo_nota")),
      h("div", { clase: "rejilla cuatro" },
        e.p.nombre, e.p.apellidos, e.p.correo, e.p.telefono))),
    aviso(d.task_sheet_liberado ? `${t("con_aviso")} ${t("con_aviso_ts")}`
                                : t("con_aviso"), ""),
    h("div", { clase: "acciones", style: "margin-top:12px" },
      guardar,
      /* No «Cancelar»: arriba, junto al estatus, «Cancelar» cancela el
         servicio. */
      h("button", { clase: "claro", type: "button",
        onclick: () => zona.replaceChildren() }, t("con_cerrar")),
      nadaTodavia),
    h("p", { clase: "chico gris", style: "margin:8px 0 0" }, t("con_bitacora")));
}

/* Nombre y apellidos en un renglon, el correo solo, y el telefono con el
   idioma de sus correos. */
function cuerpoDe(p) {
  return [
    h("div", { clase: "rejilla dos", style: "gap:10px" }, p.nombre, p.apellidos),
    p.correo,
    h("div", { clase: "rejilla dos", style: "gap:10px" }, p.telefono, p.idioma || ""),
  ];
}

/* Quien solicita: ademas de corregirlo, se puede cambiar por otro de la
   lista del cliente, y corregirlo tambien en esa lista para que el
   siguiente servicio ya lo tome bien. */
function columnaSolicita(d, cliente, alCambiar) {
  const s = d.solicitante;
  const p = persona(s, alCambiar, true);
  const estaEnLista = d.lista.some(c => c.id === s.solicitante_id);
  const original = estaEnLista ? String(s.solicitante_id) : "";

  const lista = h("select", {},
    estaEnLista ? "" : h("option", { value: "" }, t("con_no_en_lista")),
    ...d.lista.map(c => h("option", { value: c.id },
      c.correo ? `${nombreDe(c)} · ${c.correo}` : nombreDe(c))));
  lista.value = original;
  const notaLista = h("div", { clase: "chico gris ctc-antes", hidden: "hidden" },
    reemplazar(t("con_antes"), { v: nombreDe(s) || "—" }));

  /* Al escoger a otro se traen sus datos; se pueden corregir encima. Al
     regresar al de antes, vuelve lo que traia el servicio. */
  lista.addEventListener("change", () => {
    const otro = d.lista.find(c => String(c.id) === lista.value);
    const fuente = lista.value === original || !otro ? s : otro;
    for (const llave of CAMPOS) p[llave].poner(fuente[llave]);
    const cambio = lista.value !== original;
    lista.classList.toggle("ctc-cambio", cambio);
    notaLista.hidden = !cambio;
    repintarCasilla();
    alCambiar();
  });

  const cambioDeLosCampos = p.cambio;
  p.cambio = () => cambioDeLosCampos() || lista.value !== original;
  p.elegido = () => (lista.value ? Number(lista.value) : null);

  /* Solo quien puede corregir la lista del cliente lo ve. Sin nadie de
     la lista escogido, lo agrega. */
  const casilla = h("input", { type: "checkbox", checked: "checked" });
  const rotulo = h("span", {});
  function repintarCasilla() {
    rotulo.textContent = t(lista.value ? "con_en_lista" : "con_a_la_lista");
  }
  repintarCasilla();
  p.enLista = () => !!d.puede_corregir_lista && casilla.checked;

  const nodo = h("div", {},
    h("h4", {}, t("srv_solicita")),
    d.lista.length
      ? h("div", { clase: "campo" },
          h("label", {}, reemplazar(t("con_de_la_lista"),
                                    { c: cliente ? cliente.nombre : "" })),
          lista, notaLista)
      : "",
    ...cuerpoDe(p),
    d.puede_corregir_lista
      ? h("div", {},
          h("label", { clase: "casilla" }, casilla, rotulo),
          h("div", { clase: "chico gris" }, t("con_en_lista_nota")))
      : "");
  return { p, nodo };
}

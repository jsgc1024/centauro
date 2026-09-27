/* Calidad: el mes en cifras (seccion 89).

   Como salio el servicio en el mes: lo que dijo el cliente, lo que paso
   en la calle, como se cerro, la gente y los datos. Cada cifra lleva a
   su detalle, y el detalle a su pantalla: el servicio, la ficha de la
   persona, Clientes, Odoo o Catalogos.

   Las frases vienen armadas del servidor, en el idioma de la consola,
   igual que en la bitacora: el reporte en Excel dice lo mismo que la
   pantalla, y dos copias de la misma frase se separan. Aqui se pinta.

   El mes en curso va al dia de hoy; los anteriores, cada uno contra el
   mes de antes. La abren sistema y calidad, direccion de operaciones y
   direccion general. Mide, no juzga: lo que se clasifica se clasifica
   en su pantalla. */
import { api, sesion } from "./api.js";
import { bajar } from "./bitacora_admin.js";
import { aviso, conAyuda, h, lista, mensaje } from "./util.js";
import { idioma, t } from "./idioma.js";
import { menuDe } from "./menu.js";

/* El pais y el mes se quedan al volver a la pantalla. */
let paisVisto = null;
let mesVisto = null;

const TONO = { ok: "cal-mejor", alerta: "cal-peor", ambar: "ambar",
               rojo: "rojo", gris: "gris" };

function puedeAbrir(clave) {
  return menuDe(sesion.usuario).some(x => x.clave === clave);
}

function consulta(extra = {}) {
  const q = new URLSearchParams({ idioma: idioma() });
  if (paisVisto) q.set("pais_id", paisVisto);
  if (mesVisto) q.set("mes", mesVisto);
  for (const [k, v] of Object.entries(extra)) q.set(k, v);
  return q.toString();
}

export async function pantallaCalidad(main) {
  const zona = h("div", { clase: "calidad" });
  main.append(h("h1", {}, t("cal_titulo")),
              h("p", { clase: "sub" }, t("cal_sub")), zona);
  await cargar(zona);
}

async function cargar(zona) {
  zona.replaceChildren(h("p", { clase: "gris" }, t("cal_cargando")));
  let r;
  try {
    r = await api.get(`/calidad?${consulta()}`);
  } catch (err) {
    zona.replaceChildren(aviso(err.message, "grave"));
    return;
  }
  paisVisto = r.pais.id;
  mesVisto = r.mes;
  pintar(zona, r);
}

/* ------------------------------------------------------------ la barra */

function barra(zona, r) {
  const pais = lista("pais", r.opciones.paises.map(
    p => ({ valor: String(p.id), texto: p.nombre })), { style: "width:auto" });
  pais.value = String(r.pais.id);
  pais.addEventListener("change", () => {
    paisVisto = Number(pais.value);
    mesVisto = null;
    cargar(zona);
  });
  const mes = lista("mes", r.opciones.meses, { style: "width:auto" });
  mes.value = r.mes;
  mes.addEventListener("change", () => { mesVisto = mes.value; cargar(zona); });

  const excel = h("button", { clase: "claro", type: "button",
    onclick: async () => {
      const antes = excel.textContent;
      excel.disabled = true;
      excel.textContent = t("cal_preparando");
      try {
        await bajar(`/calidad/excel?${consulta()}`);
      } catch (err) {
        mensaje(err.message, "grave");
      } finally {
        excel.disabled = false;
        excel.textContent = antes;
      }
    } }, t("cal_bajar"));
  return h("div", { clase: "acciones cal-barra" }, pais, mes, excel);
}

/* --------------------------------------------------- las cinco de arriba */

function cifraArriba(x) {
  const valor = h("div", { clase: `cifra ${x.tono === "rojo" ? "rojo" : ""}`.trim() },
                  x.valor);
  const liga = x.ir && puedeAbrir(x.ir)
    ? h("a", { href: `#/${x.ir}`, clase: "cal-liga" }, valor) : valor;
  const comparacion = x.comparacion
    ? h("div", { clase: `chico ${TONO[x.comparacion.tono] || ""}`.trim() },
        x.comparacion.t)
    : null;
  return h("div", {}, liga, h("div", { clase: "chico gris" }, x.texto), comparacion);
}

/* --------------------------------------------------------- los bloques */

/* La celda del detalle: el servicio lleva a su pantalla y la persona a
   su ficha, si quien mira las abre. */
function celda(c) {
  if (c.servicio) {
    const clave = c.implantado ? "implantados" : "servicios";
    const ruta = c.implantado ? `#/implantado/${c.servicio}` : `#/servicio/${c.servicio}`;
    return puedeAbrir(clave) ? h("a", { href: ruta }, c.t) : c.t;
  }
  if (c.persona && puedeAbrir("equipo")) {
    return h("a", { href: `#/equipo/${c.persona}` }, c.t);
  }
  return c.t;
}

function detalle(ver) {
  return h("table", { clase: "lista cal-tabla" },
    h("thead", {}, h("tr", {}, ...ver.columnas.map(c => h("th", {}, c)))),
    h("tbody", {}, ...ver.filas.map(fila =>
      h("tr", {}, ...fila.map(c => h("td", { clase: "chico" }, celda(c)))))));
}

function nota(partes) {
  const nodos = [];
  (partes || []).forEach((p, i) => {
    if (i) nodos.push(" · ");
    nodos.push(p.tono ? h("span", { clase: TONO[p.tono] || "" }, p.t) : p.t);
  });
  return nodos;
}

function renglones(bloque) {
  const cuerpo = h("tbody");
  for (const x of bloque.renglones) {
    const abajo = x.ver
      ? h("tr", { clase: "cal-detalle", hidden: "hidden" },
          h("td", { colspan: "3" }, detalle(x.ver)))
      : null;
    const boton = x.ver
      ? h("button", { clase: "chico claro cal-ver", type: "button",
          onclick: () => {
            abajo.hidden = !abajo.hidden;
            boton.textContent = t(abajo.hidden ? "cal_ver" : "cal_ocultar");
          } }, t("cal_ver"))
      : null;
    cuerpo.append(...[
      h("tr", {},
        h("td", {}, x.texto),
        h("td", { clase: "num cal-valor" },
          h("b", { clase: x.tono === "rojo" ? "rojo" : "" }, x.valor)),
        h("td", { clase: "chico" }, ...nota(x.nota), boton)),
      abajo,
    ].filter(Boolean));
  }
  return h("table", { clase: "cal-renglones" }, cuerpo);
}

function irA(clave, texto) {
  if (!puedeAbrir(clave)) return null;
  return h("button", { clase: "chico claro cal-ir", type: "button",
                       onclick: () => { location.hash = `#/${clave}`; } }, texto);
}

/* Cada bloque con su "?": la clave va escrita aqui, pegada al bloque que
   explica, para que revisar.py la encuentre. */
function titulo(bloque) {
  switch (bloque.clave) {
    case "cliente": return conAyuda("h3", bloque.titulo, "ay_cal_cliente");
    case "calle": return conAyuda("h3", bloque.titulo, "ay_cal_calle");
    case "cierre": return conAyuda("h3", bloque.titulo, "ay_cal_cierre");
    case "gente": return conAyuda("h3", bloque.titulo, "ay_cal_gente");
    default: return h("h3", {}, bloque.titulo);
  }
}

function tarjeta(bloque) {
  const ir = bloque.clave === "cliente" ? irA("encuestas", t("cal_ir_clientes")) : null;
  return h("div", { clase: "tarjeta" }, titulo(bloque), renglones(bloque), ir);
}

/* ------------------------------------------------------------ los datos */

function cosas(lado) {
  if (!lado.cosas.length) return h("p", { clase: "chico gris" }, t("cal_nada_aqui"));
  return h("ul", { clase: "chico cal-cosas" }, ...lado.cosas.map(c => {
    const nombres = (c.cuales || []).length
      ? h("div", { clase: "gris cal-cuales", hidden: "hidden" }, c.cuales.join(", "))
      : null;
    const ver = nombres
      ? h("a", { href: "#", clase: "cal-ver-nombres", onclick: (e) => {
          e.preventDefault();
          nombres.hidden = !nombres.hidden;
          ver.textContent = t(nombres.hidden ? "cal_cuales" : "cal_ocultar");
        } }, t("cal_cuales"))
      : null;
    return h("li", {}, c.t, ver ? " · " : null, ver, nombres);
  }));
}

function losDatos(d) {
  return h("div", { clase: "tarjeta" },
    conAyuda("h3", d.titulo, "ay_cal_datos"),
    h("p", { clase: "gris chico", style: "margin:4px 0 0" }, t("cal_datos_sub")),
    h("div", { clase: "cal-datos" },
      h("div", {}, h("h4", {}, d.odoo.titulo), cosas(d.odoo),
        irA("odoo", t("cal_ir_odoo"))),
      h("div", {}, h("h4", {}, d.catalogos.titulo), cosas(d.catalogos),
        irA("catalogos", t("cal_ir_catalogos")))));
}

/* ---------------------------------------------------------------- todo */

function pintar(zona, r) {
  zona.replaceChildren(
    barra(zona, r),
    conAyuda("h3", t("cal_principales"), "ay_cal_arriba", { clase: "cal-sobre" }),
    h("div", { clase: "corte" }, ...r.arriba.map(cifraArriba)),
    h("div", { clase: "rejilla dos" }, ...r.bloques.map(tarjeta)),
    losDatos(r.datos));
}

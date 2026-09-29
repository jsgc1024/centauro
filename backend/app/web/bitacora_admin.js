/* La bitacora de administracion (seccion 86).

   Cada cambio de administracion deja su renglon desde el panel de
   accesos: quien le abrio o le cerro la puerta a quien, quien le cambio
   el puesto, quien movio un festivo, un hospital o un monto del
   tabulador, quien puso el tipo de cambio. Se escribia bien y se leia a
   pedazos --el historial de un acceso, el de un renglon--; para saber
   que cambio en el mes no habia donde mirar.

   Aqui se lee junta: que, quien y que mes, y en Excel. Cada renglon
   viene contado del servidor en el idioma de la consola, con nombres y
   no con numeros --"ciudad Queretaro -> Monterrey"--, y el Excel dice lo
   mismo, con lo escrito tal cual a su lado para quien audita.

   Las lecturas de Odoo de cada hora van aparte: dejan un renglon aunque
   no cambie nada, y taparian lo que hizo una persona. */
import { api, ErrorApi, sesion } from "./api.js";
import { conAyuda, fecha, h, hora, lista, mensaje } from "./util.js";
import { idioma, t } from "./idioma.js";

const QUE = [["", "bta_que_todo"], ["accesos", "bta_que_accesos"],
             ["puestos", "bta_que_puestos"], ["catalogos", "bta_que_catalogos"],
             ["tipo_cambio", "bta_que_tipo_cambio"], ["odoo", "bta_que_odoo"]];
const MESES = ["bon_mes_1", "bon_mes_2", "bon_mes_3", "bon_mes_4",
               "bon_mes_5", "bon_mes_6", "bon_mes_7", "bon_mes_8",
               "bon_mes_9", "bon_mes_10", "bon_mes_11", "bon_mes_12"];

function esteMes() {
  const hoy = new Date();
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`;
}

function nombreDelMes(clave) {
  const [anio, mes] = clave.split("-");
  return `${t(MESES[Number(mes) - 1])} ${anio}`;
}

function consulta(filtros, extra = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...filtros, ...extra })) {
    if (v !== null && v !== undefined && v !== "") q.set(k, v);
  }
  return q.toString();
}

/* El Excel se baja con la sesion puesta y con el nombre que pone el
   servidor, como el del historial de lo facturado. Lo usa tambien el
   reporte de Calidad (seccion 89). */
export async function bajar(ruta) {
  const cab = sesion.token ? { Authorization: `Bearer ${sesion.token}` } : {};
  const r = await fetch(ruta, { headers: cab });
  if (!r.ok) {
    const d = await r.json().catch(() => null);
    throw new ErrorApi(r.status, d && d.detail);
  }
  const dicho = r.headers.get("content-disposition") || "";
  const nombre = (dicho.match(/filename="([^"]+)"/) || [])[1] || "bitacora.xlsx";
  const url = URL.createObjectURL(await r.blob());
  const enlace = h("a", { href: url, download: nombre });
  document.body.append(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export async function pestanaBitacora(zona) {
  const filtros = { que: "", quien: "", mes: esteMes(), pagina: 1 };
  const tabla = h("div");
  let datos = null;

  // Solo se pinta la respuesta del ultimo filtro pedido (seccion 101).
  let peticion = 0;

  async function cargar() {
    tabla.replaceChildren(h("div", { clase: "gris chico" }, "…"));
    const mia = ++peticion;
    let r;
    try {
      r = await api.get(`/bitacora-admin?${consulta(filtros, { idioma: idioma() })}`);
    } catch (err) {
      if (mia !== peticion) return;
      tabla.replaceChildren(h("div", { clase: "aviso grave" }, err.message));
      return;
    }
    if (mia !== peticion) return;
    datos = r;
    pintarTabla();
  }

  function selector(nombre, opciones, valor, alCambiar) {
    const sel = lista(nombre, opciones, { style: "width:auto" });
    sel.value = valor;
    sel.addEventListener("change", () => alCambiar(sel.value));
    return sel;
  }

  function barra(opciones) {
    const meses = [...new Set([esteMes(), ...opciones.meses])].sort().reverse();
    const excel = h("button", { clase: "claro", type: "button",
      onclick: async () => {
        const antes = excel.textContent;
        excel.disabled = true;
        excel.textContent = t("bta_preparando");
        const lo = { que: filtros.que, quien: filtros.quien, mes: filtros.mes };
        const q = consulta(lo, { idioma: idioma() });
        try {
          await bajar(`/bitacora-admin/excel?${q}`);
        } catch (err) {
          mensaje(err.message, "grave");
        } finally {
          excel.disabled = false;
          excel.textContent = antes;
        }
      } }, t("bta_excel"));
    const cambiar = (clave) => (v) => { filtros[clave] = v; filtros.pagina = 1; cargar(); };
    return h("div", { clase: "acciones", style: "margin:0 0 12px" },
      selector("que", QUE.map(([v, k]) => ({ valor: v, texto: t(k) })), filtros.que,
               cambiar("que")),
      selector("quien", [{ valor: "", texto: t("bta_quien_todos") },
        ...opciones.quienes.map(q => ({ valor: String(q.usuario_id), texto: q.nombre }))],
        filtros.quien, cambiar("quien")),
      selector("mes", [...meses.map(m => ({ valor: m, texto: nombreDelMes(m) })),
        { valor: "", texto: t("bta_mes_todos") }], filtros.mes, cambiar("mes")),
      excel);
  }

  function pintarTabla() {
    const paginas = Math.max(1, Math.ceil(datos.total / datos.por_pagina));
    const filas = datos.filas.map(x => h("tr", {},
      h("td", { clase: "chico num", style: "white-space:nowrap" },
        fecha(x.cuando), h("div", { clase: "gris" }, hora(x.cuando))),
      h("td", { clase: "chico" }, h("b", {}, x.quien || "—"),
        x.rol_texto ? h("div", { clase: "gris" }, x.rol_texto) : null),
      h("td", { clase: "chico" }, x.donde),
      h("td", { clase: "chico" }, x.que)));
    tabla.replaceChildren(...[
      barra(datos.opciones),
      h("table", { clase: "lista" },
        h("thead", {}, h("tr", {},
          h("th", { style: "width:14%" }, t("bta_cuando")),
          h("th", { style: "width:18%" }, t("bta_quien")),
          h("th", { style: "width:16%" }, t("bta_donde")),
          h("th", {}, t("bta_que_cambio")))),
        h("tbody", {}, ...(filas.length ? filas
          : [h("tr", {}, h("td", { colspan: "4", clase: "gris chico" }, t("bta_vacio")))]))),
      datos.total > datos.por_pagina ? h("div", { clase: "acciones", style: "margin-top:10px" },
        h("button", { type: "button", clase: "claro chico", disabled: filtros.pagina <= 1,
                      onclick: () => { filtros.pagina -= 1; cargar(); } }, t("bta_anterior")),
        h("span", { clase: "chico gris" }, t("bta_pagina")
          .replace("{p}", filtros.pagina).replace("{n}", paginas).replace("{total}", datos.total)),
        h("button", { type: "button", clase: "claro chico", disabled: filtros.pagina >= paginas,
                      onclick: () => { filtros.pagina += 1; cargar(); } }, t("bta_siguiente")))
        : h("p", { clase: "chico gris", style: "margin-top:8px" },
            t("bta_cuantos").replace("{total}", datos.total)),
    ].filter(Boolean));
  }

  zona.replaceChildren(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("bta_titulo"), "ay_bta"),
    h("p", { clase: "gris chico ctl-pie" }, t("bta_pie")),
    tabla));
  await cargar();
}

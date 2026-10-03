/* Los catalogos de Logistica, AI/LG (seccion 150).

   Lo que el margen, el anticipo y la nomina de cada viaje de Logistica
   van a usar, capturado una vez y con su fecha. Ocho catalogos en dos
   grupos (decision de Salvador, 3 oct): los que deciden dinero los fija
   la gerencia de Logistica; los tipos de unidad y los patios los lleva
   sistema y calidad. Quien no los lleva los ve con su candado.

   Cada valor rige desde su fecha y uno nuevo no borra el anterior. Lo que
   ya rige no se edita: se corrige capturando el bueno desde la misma
   fecha, con su porque, y el malo se queda tachado. Lo programado si se
   corrige o se quita. Las reglas viven en el servidor
   (`lg_catalogos.py`); aqui solo se deja de pintar el boton que
   contestaria que no, y se avisa antes de guardar lo que va a pasar.

   Los numeros que salen calculados --el costo por dia, el ejemplo del
   tabulador, la comision de prueba-- los calcula el servidor: el
   navegador redondea distinto y un centavo de diferencia entre la
   pantalla y la nomina es una llamada. */
import { api } from "./api.js";
import { campo, conAyuda, dinero, entrada, etiqueta, fecha, h, hora, lista,
         mensaje } from "./util.js";
import { idioma, t } from "./idioma.js";

const CANDADO = '<svg width="11" height="13" viewBox="0 0 11 13" aria-hidden="true">'
  + '<rect x="0.5" y="5.5" width="10" height="7" rx="1.5" fill="currentColor"/>'
  + '<path d="M2.8 5.5V3.8a2.7 2.7 0 0 1 5.4 0v1.7" fill="none" '
  + 'stroke="currentColor" stroke-width="1.4"/></svg>';

const DE_DINERO = ["tabulador", "diesel", "alimentos", "operador", "costos", "bono"];
const DE_SISTEMA = ["tipos", "patios"];
const CATALOGOS = [...DE_DINERO, ...DE_SISTEMA];
const TITULO = {
  tabulador: "lgc_tabulador", diesel: "lgc_diesel", alimentos: "lgc_alimentos",
  operador: "lgc_operador", costos: "lgc_costos", bono: "lgc_bono",
  tipos: "lgc_tipos", patios: "lgc_patios",
};
/* Como se llama cada valor en una tabla, y en corto en la lista de la
   izquierda cuando falta. */
const QUE = {
  tabulador: "lgc_q_tabulador", diesel: "lgc_q_diesel", holgura: "lgc_q_holgura",
  tolerancia: "lgc_q_tolerancia", alimentos: "lgc_q_alimentos",
  margen: "lgc_q_margen", operador: "lgc_q_operador", bono: "lgc_q_bono",
  garantia: "lgc_q_garantia",
};
const CORTO = {
  diesel: "lgc_n_diesel", holgura: "lgc_n_holgura", tolerancia: "lgc_n_tolerancia",
  alimentos: "lgc_n_alimentos", margen: "lgc_n_margen",
};
const ESTADO = {
  vigente: ["lgc_e_vigente", "ok"], programado: ["lgc_e_programado", "info"],
  anterior: ["lgc_e_anterior", ""], reemplazado: ["lgc_e_reemplazado", ""],
  quitado: ["lgc_e_quitado", ""],
};
const VIVOS = ["vigente", "anterior", "programado"];

/* El catalogo que se esta mirando se queda al guardar y al volver. */
let elegido = "tabulador";

/* ------------------------------------------------------------ formatos */

const MXN2 = new Intl.NumberFormat("es-MX", {
  style: "currency", currency: "MXN", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MXN4 = new Intl.NumberFormat("es-MX", {
  style: "currency", currency: "MXN", minimumFractionDigits: 2, maximumFractionDigits: 4 });
const NUMERO = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 2 });
const nada = (v) => v === null || v === undefined || v === "";
const pesos = (v) => (nada(v) ? "—" : dinero(v, "MXN"));
const pesos2 = (v) => (nada(v) ? "—" : MXN2.format(Number(v)));
const porKm = (v) => (nada(v) ? "—" : MXN4.format(Number(v)));
const pct = (v) => (nada(v) ? "—" : `${NUMERO.format(Number(v))}%`);
const kms = (v) => (nada(v) ? "—" : NUMERO.format(Number(v)));

function poner(nodo, ...hijos) {
  nodo.replaceChildren(...hijos.flat().filter(Boolean));
}

function boton(texto, alPicar, clase = "claro chico") {
  return h("button", { type: "button", clase, onclick: alPicar }, texto);
}

function tabla(cabezas, filas, vacio = "lgc_vacio") {
  return h("table", { clase: "lista ctl-tabla" },
    h("thead", {}, h("tr", {}, ...cabezas.map(c => h("th", {}, c)))),
    h("tbody", {}, ...(filas.length ? filas
      : [h("tr", {}, h("td", { colspan: String(cabezas.length), clase: "gris chico" }, t(vacio)))])));
}

const activos = (d) => d.tipos.filter(x => x.activo);
const nombreTipo = (d, id) => (d.tipos.find(x => x.id === Number(id)) || {}).nombre || "—";
const puede = (d, cat) => (DE_DINERO.includes(cat) ? d.puede.dinero : d.puede.editar);
const tachado = (v) => v.estado === "reemplazado" || v.estado === "quitado";

function estadoDe(v) {
  const [clave, tono] = ESTADO[v.estado] || ESTADO.anterior;
  return etiqueta(t(clave), tono);
}

/* El programado que sigue, para decir «el lunes cambia a...». */
function proximo(d, clave, tipoId = null) {
  return (d.valores[clave] || [])
    .filter(v => v.estado === "programado" && (v.tipo_unidad_id || null) === tipoId)
    .sort((a, b) => a.vigente_desde.localeCompare(b.vigente_desde))[0] || null;
}

/* ------------------------------------------------------------ como se lee cada valor */

function tramosTexto(datos) {
  return (datos.tramos || []).map(x => (Number(x.desde_anios) > 0
    ? t("lgc_tramo_corto").replace("{pct}", pct(x.pct)).replace("{n}", x.desde_anios)
    : pct(x.pct))).join(" · ");
}

function valorTexto(d, v) {
  const datos = v.datos || {};
  const calculo = v.calculo || {};
  if (v.clave === "diesel") return t("lgc_res_litro").replace("{v}", pesos2(v.valor));
  if (["holgura", "tolerancia", "margen"].includes(v.clave)) return pct(v.valor);
  if (v.clave === "alimentos") return t("lgc_res_dia").replace("{v}", pesos(v.valor));
  if (v.clave === "operador") {
    return t("lgc_v_operador").replace("{mes}", pesos(datos.costo_mensual))
      .replace("{dias}", datos.dias_laborables).replace("{dia}", pesos2(calculo.costo_dia));
  }
  if (v.clave === "unidad") {
    return `${t("lgc_km_l").replace("{n}", kms(datos.rendimiento))} · `
      + t("lgc_res_dia").replace("{v}", pesos2(calculo.costo_dia));
  }
  if (v.clave === "bono") {
    return `${tramosTexto(datos)} · `
      + t("lgc_v_dias").replace("{n}", datos.dias_requeridos);
  }
  if (v.clave === "garantia") {
    return t("lgc_v_garantia").replace("{tipo}", nombreTipo(d, datos.tipo_unidad_id))
      .replace("{monto}", pesos(datos.monto_semanal))
      .replace("{exige}", t(datos.exige_dias_completos ? "lgc_si" : "lgc_no"))
      .replace("{sobre}", t(datos.bono_sobre_garantia ? "lgc_si" : "lgc_no"));
  }
  if (v.clave === "tabulador") {
    return Object.entries(datos.tipos || {}).map(([id, x]) =>
      `${nombreTipo(d, id)} ${pesos(x.base)} + ${porKm(x.por_km)}`).join(" · ");
  }
  return v.valor || "—";
}

function queDe(d, v) {
  return v.clave === "unidad" ? nombreTipo(d, v.tipo_unidad_id) : t(QUE[v.clave]);
}

/* ============================================================ la pantalla */

export async function pantallaLgCatalogos(main) {
  const pestanas = h("div", { clase: "pestanas", style: "margin:0 0 14px" });
  const zona = h("div");
  let vista = "catalogos";

  function pintarPestanas() {
    poner(pestanas, [["catalogos", "lgc_pestana_catalogos"], ["bitacora", "lgc_pestana_bitacora"]]
      .map(([clave, texto]) => h("button", {
        type: "button", clase: clave === vista ? "pestana activa" : "pestana",
        onclick: () => { vista = clave; pintarPestanas(); pintarVista(); },
      }, t(texto))));
  }

  async function pintarVista() {
    poner(zona, h("div", { clase: "gris chico" }, "…"));
    try {
      if (vista === "bitacora") await pestanaBitacora(zona);
      else await pestanaCatalogos(zona);
    } catch (err) {
      poner(zona, h("div", { clase: "aviso grave" }, err.message));
    }
  }

  main.append(h("h1", {}, t("lgc_titulo")), h("p", { clase: "sub" }, t("lgc_sub")),
              pestanas, zona);
  pintarPestanas();
  await pintarVista();
}

/* ================================================ la lista de la izquierda */

function resumenDe(d, cat) {
  const v = d.vigentes;
  const vacio = t("lgc_res_vacio");
  if (cat === "tabulador") {
    if (!v.tabulador) return vacio;
    const con = activos(d).filter(x => (v.tabulador.datos.tipos || {})[String(x.id)]);
    const muestra = con.length > 2 ? [con[0], con[con.length - 1]] : con;
    return muestra.map((x) => {
      const m = v.tabulador.datos.tipos[String(x.id)];
      return `${x.nombre} ${pesos(m.base)} + ${porKm(m.por_km)}`;
    }).join(" · ") || vacio;
  }
  if (cat === "diesel") {
    return [v.diesel ? t("lgc_res_litro").replace("{v}", pesos2(v.diesel.valor)) : null,
            v.holgura ? t("lgc_res_holgura").replace("{v}", pct(v.holgura.valor)) : null,
            v.tolerancia ? t("lgc_res_tolerancia").replace("{v}", pct(v.tolerancia.valor)) : null]
      .filter(Boolean).join(" · ") || vacio;
  }
  if (cat === "alimentos") {
    return [v.alimentos ? t("lgc_res_dia").replace("{v}", pesos(v.alimentos.valor)) : null,
            v.margen ? t("lgc_res_margen").replace("{v}", pct(v.margen.valor)) : null]
      .filter(Boolean).join(" · ") || vacio;
  }
  if (cat === "operador") {
    return v.operador ? t("lgc_res_dia").replace("{v}", pesos2(v.operador.calculo.costo_dia)) : vacio;
  }
  if (cat === "costos") {
    const tipo = activos(d).find(x => v.unidad[String(x.id)]);
    if (!tipo) return vacio;
    const u = v.unidad[String(tipo.id)];
    return `${tipo.nombre} ${t("lgc_km_l").replace("{n}", kms(u.datos.rendimiento))} · `
      + t("lgc_res_dia").replace("{v}", pesos(u.calculo.costo_dia));
  }
  if (cat === "bono") {
    return [v.bono ? tramosTexto(v.bono.datos) : null,
            v.garantia ? `${nombreTipo(d, v.garantia.datos.tipo_unidad_id)} ${pesos(v.garantia.datos.monto_semanal)}` : null]
      .filter(Boolean).join(" · ") || vacio;
  }
  if (cat === "tipos") return activos(d).map(x => x.nombre).join(" · ") || vacio;
  const vivos = d.patios.filter(x => x.activo);
  return vivos.map(x => x.nombre).join(" · ") || vacio;
}

function faltaDe(d, cat) {
  const f = d.faltas[cat] || [];
  if (!f.length) return null;
  if (cat === "tabulador") {
    return f.includes("tabulador") ? t("lgc_falta")
      : t("lgc_falta_de").replace("{que}", f.join(", "));
  }
  if (cat === "diesel" || cat === "alimentos") {
    return t("lgc_falta_de").replace("{que}", f.map(c => t(CORTO[c])).join(", "));
  }
  if (cat === "operador" || cat === "bono") return t("lgc_lo_da_rh");
  if (cat === "costos") {
    return f.length === 1 ? t("lgc_falta_tipo").replace("{tipo}", f[0])
      : t("lgc_faltan_tipos").replace("{n}", f.length);
  }
  if (cat === "patios" && !f.includes("patios")) {
    return t("lgc_sin_ubicacion_n").replace("{n}", f.length);
  }
  return t("lgc_falta");
}

async function pestanaCatalogos(zona) {
  let d = await api.get("/lg/catalogos");
  const izquierda = h("div", { clase: "tarjeta lisa ctl-lista" });
  const derecha = h("div");

  const recargar = async () => { d = await api.get("/lg/catalogos"); pintar(); };

  function renglon(cat) {
    const falta = faltaDe(d, cat);
    const escoger = () => { elegido = cat; pintar(); };
    return h("div", {
      clase: cat === elegido ? "ctl-item sel" : "ctl-item",
      role: "button", tabindex: "0", onclick: escoger,
      onkeydown: (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); escoger(); }
      },
    },
      h("div", {},
        h("b", {}, puede(d, cat) ? null : h("span", { clase: "ctl-candado", html: CANDADO }),
          t(TITULO[cat])),
        h("div", { clase: "chico gris" }, resumenDe(d, cat))),
      falta ? h("div", {}, etiqueta(falta, "alerta")) : null);
  }

  function pintar() {
    poner(izquierda,
      h("h4", { clase: "ctl-grupo" }, t("lgc_grupo_dinero")),
      h("p", { clase: "chico gris ctl-nota" }, t("lgc_grupo_dinero_pie")),
      DE_DINERO.map(renglon),
      h("h4", { clase: "ctl-grupo otro" }, t("lgc_grupo_sistema")),
      DE_SISTEMA.map(renglon));
    poner(derecha);
    PINTA[elegido](derecha, d, recargar);
  }

  poner(zona, h("div", { clase: "ctl-marco" }, izquierda, derecha));
  pintar();
}

/* ============================================================ piezas */

function quienLoLleva(d, cat) {
  if (puede(d, cat)) return null;
  return h("p", { clase: "aviso ctl-quien" },
    t(DE_DINERO.includes(cat) ? "lgc_lo_fija_dinero" : "lgc_lo_lleva_sistema"));
}

/* Lo ultimo que le paso a este catalogo, de la bitacora. */
function historial(cat) {
  const caja = h("div", { clase: "ctl-historial" }, h("div", { clase: "gris chico" }, "…"));
  api.get(`/lg/catalogos/bitacora?catalogo=${cat}&idioma=${idioma()}`).then((r) => {
    if (!r.filas.length) {
      poner(caja, h("p", { clase: "chico gris" }, t("lgc_hist_nadie")));
      return;
    }
    const pocas = r.filas.slice(0, 8);
    poner(caja,
      pocas.map(x => h("div", { clase: "ctl-hist-renglon chico" },
        h("span", { clase: "gris num" }, `${fecha(x.cuando)} ${hora(x.cuando)}`),
        h("b", {}, x.quien || "—"),
        h("span", {}, x.que))),
      r.total > pocas.length
        ? h("p", { clase: "chico gris" }, t("lgc_hist_mas").replace("{n}", r.total - pocas.length))
        : null);
  }).catch((err) => poner(caja, h("p", { clase: "chico gris" }, err.message)));
  return h("div", {}, h("h4", { clase: "grupo" }, t("lgc_hist")), caja);
}

/* Quitar lo programado: pregunta antes, y queda en la bitacora. */
function quitarValor(d, v, recargar) {
  return boton(t("lgc_quitar"), async (e) => {
    const que = `${queDe(d, v)} · ${fecha(v.vigente_desde)}`;
    if (!confirm(t("lgc_quitar_seguro").replace("{que}", que))) return;
    e.target.disabled = true;
    try {
      await api.borrar(`/lg/catalogos/valores/${v.id}`);
      mensaje(t("lgc_quitado"));
      await recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  });
}

/* Los valores de unas claves, con su estado: lo vigente, lo programado,
   lo de antes y lo tachado, con quien lo capturo y por que. */
function tablaValores(d, claves, recargar, abrirEdicion, conQue = true) {
  const filas = claves.flatMap(c => d.valores[c] || []);
  return tabla([...(conQue ? [t("lgc_col_que")] : []), t("lgc_col_rige"), t("lgc_col_valor"),
                t("lgc_col_capturo"), ""],
    filas.map(v => h("tr", { clase: tachado(v) ? "apagado" : "" },
      conQue ? h("td", {}, queDe(d, v)) : null,
      h("td", { clase: "num", style: "white-space:nowrap" }, fecha(v.vigente_desde), " ", estadoDe(v)),
      h("td", { clase: "num" }, tachado(v) ? h("s", {}, valorTexto(d, v)) : valorTexto(d, v)),
      h("td", {}, v.capturado_por || "—",
        v.motivo ? h("div", { clase: "chico gris" }, `«${v.motivo}»`) : null),
      h("td", { style: "text-align:right;white-space:nowrap" },
        v.estado === "programado" && d.puede.dinero
          ? boton(t("lgc_editar"), () => abrirEdicion(v)) : null,
        v.estado === "programado" && d.puede.dinero ? quitarValor(d, v, recargar) : null))));
}

/* «Rige desde el ... · lo capturo ...», con su etiqueta. */
function rige(v) {
  if (!v) return null;
  return h("p", { clase: "chico", style: "margin:0 0 10px" },
    t("lgc_rige_desde").replace("{fecha}", fecha(v.vigente_desde)), " ", estadoDe(v),
    v.capturado_por ? ` · ${t("lgc_lo_capturo").replace("{quien}", v.capturado_por)}` : null);
}

/* ============================================================ la forma de un valor */

/* Lo que va a pasar al guardar con esa fecha, dicho antes de guardar.
   El servidor revisa lo mismo; esto es para que nadie se entere por un
   error. */
function queVaAPasar(d, clave, tipoId, fechaIso, propioId) {
  if (!fechaIso) return null;
  const mismo = (d.valores[clave] || []).find(v => v.id !== propioId
    && (v.tipo_unidad_id || null) === (tipoId || null)
    && VIVOS.includes(v.estado) && v.vigente_desde === fechaIso);
  if (mismo && mismo.estado !== "programado") {
    return { texto: t("lgc_f_reemplaza"), tono: "alerta", motivo: true };
  }
  if (fechaIso < d.hoy) return { texto: t("lgc_f_pasada"), tono: "alerta", motivo: true };
  if (fechaIso > d.hoy) {
    return { texto: t(mismo ? "lgc_f_reemplaza_prog" : "lgc_f_programa"), tono: "", motivo: false };
  }
  return null;
}

function control(nombre, valor, atributos = {}) {
  const c = entrada(nombre, { type: "number", step: "any", autocomplete: "off", ...atributos });
  c.value = nada(valor) ? "" : String(valor);
  return c;
}

/* La forma de un valor nuevo o de lo programado. `fila` es lo programado
   que se corrige; sin ella, es un valor nuevo de `clave`. */
function formaValor(d, clave, recargar, alCerrar, { fila = null, tipoId = null } = {}) {
  const ahora = clave === "unidad" ? d.vigentes.unidad[String(tipoId)] : d.vigentes[clave];
  const base = fila || ahora || null;
  const datos = (base && base.datos) || {};
  const campos = [];
  const sacar = [];       // cada uno devuelve [clave, valor] o lanza
  const pedir = (texto, c) => {
    if (c.value.trim() === "") {
      c.focus();
      throw new Error(t("lgc_f_falta").replace("{campo}", texto));
    }
    return Number(c.value);
  };

  if (["diesel", "holgura", "tolerancia", "margen", "alimentos"].includes(clave)) {
    const etiquetas = { diesel: "lgc_f_precio", holgura: "lgc_f_pct", tolerancia: "lgc_f_pct",
                        margen: "lgc_f_pct", alimentos: "lgc_f_monto_dia" };
    const c = control("valor", base && base.valor);
    campos.push(campo(t(etiquetas[clave]), c, { obligatorio: true }));
    sacar.push(() => ["valor", pedir(t(etiquetas[clave]), c)]);
  } else if (clave === "operador") {
    const mes = control("costo_mensual", datos.costo_mensual);
    const dias = control("dias_laborables", datos.dias_laborables, { step: "1" });
    campos.push(campo(t("lgc_f_costo_mensual"), mes, { obligatorio: true }),
                campo(t("lgc_f_dias"), dias, { obligatorio: true }));
    sacar.push(() => ["datos", { costo_mensual: pedir(t("lgc_f_costo_mensual"), mes),
                                 dias_laborables: pedir(t("lgc_f_dias"), dias) }]);
  } else if (clave === "unidad") {
    const PARTES = [["rendimiento", "lgc_f_rendimiento"], ["compra", "lgc_f_compra"],
                    ["anios", "lgc_f_anios"], ["seguro", "lgc_f_seguro"],
                    ["mantenimiento", "lgc_f_mantenimiento"], ["llantas", "lgc_f_llantas"],
                    ["gps", "lgc_f_gps"]];
    const cajas = PARTES.map(([k, texto]) => [k, texto, control(k, datos[k])]);
    campos.push(...cajas.map(([, texto, c]) => campo(t(texto), c, { obligatorio: true })));
    sacar.push(() => ["datos", Object.fromEntries(cajas.map(([k, texto, c]) => [k, pedir(t(texto), c)]))]);
  } else if (clave === "tabulador") {
    const kmBase = control("km_base", nada(datos.km_base) ? 100 : datos.km_base, { step: "1" });
    const cabeza = h("th", {}, t("lgc_col_primeros").replace("{km}", kms(kmBase.value)));
    kmBase.addEventListener("input", () => {
      cabeza.textContent = t("lgc_col_primeros").replace("{km}", kms(kmBase.value || 0));
    });
    const renglones = activos(d).map((x) => {
      const m = (datos.tipos || {})[String(x.id)] || {};
      return [x, control(`base_${x.id}`, m.base), control(`por_km_${x.id}`, m.por_km)];
    });
    campos.push(campo(t("lgc_f_km_base"), kmBase, { obligatorio: true }));
    campos.push(h("table", { clase: "lista ctl-tabla", style: "grid-column:1/-1" },
      h("thead", {}, h("tr", {}, h("th", {}, t("lgc_col_tipo")), cabeza, h("th", {}, t("lgc_col_por_km")))),
      h("tbody", {}, ...renglones.map(([x, b, p]) => h("tr", {}, h("td", {}, h("b", {}, x.nombre)),
        h("td", {}, b), h("td", {}, p))))));
    sacar.push(() => ["datos", {
      km_base: pedir(t("lgc_f_km_base"), kmBase),
      tipos: Object.fromEntries(renglones.map(([x, b, p]) => [String(x.id), {
        base: pedir(`${x.nombre} · ${t("lgc_f_base")}`, b),
        por_km: pedir(`${x.nombre} · ${t("lgc_col_por_km")}`, p) }])) }]);
  } else if (clave === "bono") {
    const filas = h("tbody");
    const tramos = [];
    const agregar = (desde, porcentaje) => {
      const a = control("desde_anios", desde, { step: "1" });
      const p = control("pct", porcentaje);
      const tr = h("tr", {}, h("td", {}, a), h("td", {}, p),
        h("td", {}, boton(t("lgc_f_quitar_tramo"), () => {
          tramos.splice(tramos.findIndex(x => x.tr === tr), 1);
          tr.remove();
        })));
      tramos.push({ a, p, tr });
      filas.append(tr);
    };
    for (const x of (datos.tramos || [{ desde_anios: 0, pct: "" }])) agregar(x.desde_anios, x.pct);
    const dias = control("dias_requeridos", nada(datos.dias_requeridos) ? 5 : datos.dias_requeridos,
                         { step: "1" });
    campos.push(h("div", { style: "grid-column:1/-1" },
      h("table", { clase: "lista ctl-tabla" },
        h("thead", {}, h("tr", {}, h("th", {}, t("lgc_f_desde_anios")), h("th", {}, t("lgc_f_pct_bono")),
          h("th", {}))), filas),
      h("div", { clase: "acciones", style: "margin:6px 0" },
        boton(t("lgc_f_agregar_tramo"), () => agregar("", "")))));
    campos.push(campo(t("lgc_f_dias_bono"), dias, { obligatorio: true }));
    sacar.push(() => ["datos", {
      tramos: tramos.map(x => ({ desde_anios: pedir(t("lgc_f_desde_anios"), x.a),
                                 pct: pedir(t("lgc_f_pct_bono"), x.p) })),
      dias_requeridos: pedir(t("lgc_f_dias_bono"), dias) }]);
  } else if (clave === "garantia") {
    const tipos = activos(d);
    const tipo = lista("tipo_unidad_id", tipos.map(x => ({ valor: String(x.id), texto: x.nombre })));
    tipo.value = String(datos.tipo_unidad_id || (tipos[tipos.length - 1] || {}).id || "");
    const monto = control("monto_semanal", datos.monto_semanal);
    const siNo = (nombre, v) => {
      const s = lista(nombre, [{ valor: "", texto: "—" }, { valor: "si", texto: t("lgc_si") },
                               { valor: "no", texto: t("lgc_no") }]);
      s.value = v === true ? "si" : v === false ? "no" : "";
      return s;
    };
    const exige = siNo("exige", datos.exige_dias_completos);
    const sobre = siNo("sobre", datos.bono_sobre_garantia);
    campos.push(campo(t("lgc_f_tipo"), tipo, { obligatorio: true }),
                campo(t("lgc_f_monto_semanal"), monto, { obligatorio: true }),
                campo(t("lgc_f_exige"), exige, { obligatorio: true }),
                campo(t("lgc_f_sobre"), sobre, { obligatorio: true }));
    const regla = (s, texto) => {
      if (!s.value) { s.focus(); throw new Error(t("lgc_f_falta").replace("{campo}", texto)); }
      return s.value === "si";
    };
    sacar.push(() => ["datos", { tipo_unidad_id: Number(tipo.value),
                                 monto_semanal: pedir(t("lgc_f_monto_semanal"), monto),
                                 exige_dias_completos: regla(exige, t("lgc_f_exige")),
                                 bono_sobre_garantia: regla(sobre, t("lgc_f_sobre")) }]);
  }

  /* La fecha y el porque, con lo que va a pasar dicho antes de guardar. */
  const desde = entrada("vigente_desde", { type: "date" });
  desde.value = fila ? fila.vigente_desde : d.hoy;
  const motivo = entrada("motivo", { autocomplete: "off", maxlength: "200", "data-crudo": "" });
  motivo.value = "";
  const cajaMotivo = campo(t("lgc_f_motivo"), motivo);
  cajaMotivo.style.gridColumn = "1 / -1";
  const avisoFecha = h("div");
  const propio = fila ? fila.id : null;
  const tipoDeFila = fila ? fila.tipo_unidad_id : tipoId;
  function revisarFecha() {
    const x = queVaAPasar(d, clave, tipoDeFila, desde.value, propio);
    poner(avisoFecha, x ? h("div", { clase: `aviso ${x.tono}`.trim(), style: "margin:4px 0 10px" }, x.texto) : null);
    poner(cajaMotivo.querySelector("label"), t("lgc_f_motivo"),
      x && x.motivo ? h("span", { clase: "obligatorio" }, " *") : null);
  }
  desde.addEventListener("change", revisarFecha);
  desde.addEventListener("input", revisarFecha);

  const guardar = boton(t("lgc_guardar"), async () => {
    let cuerpo;
    try {
      if (!desde.value) throw new Error(t("lgc_f_falta").replace("{campo}", t("lgc_f_rige")));
      cuerpo = { vigente_desde: desde.value, motivo: motivo.value.trim() || null };
      for (const f of sacar) {
        const [k, v] = f();
        cuerpo[k] = v;
      }
    } catch (err) {
      mensaje(err.message, "alerta");
      return;
    }
    guardar.disabled = true;
    try {
      if (fila) {
        await api.put(`/lg/catalogos/valores/${fila.id}`, cuerpo);
      } else {
        await api.post("/lg/catalogos/valores", { clave, tipo_unidad_id: tipoId, ...cuerpo });
      }
      mensaje(t("lgc_guardado"));
      await recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      guardar.disabled = false;
    }
  }, "chico");

  const titulo = clave === "unidad" ? `${t("lgc_q_unidad")} · ${nombreTipo(d, tipoDeFila)}`
    : t(QUE[clave]);
  const nodo = h("div", { clase: "ctl-forma" },
    h("h4", {}, fila ? t("lgc_f_corrige").replace("{que}", titulo) : titulo),
    h("div", { clase: "ctl-campos" }, ...campos),
    h("div", { clase: "ctl-campos" }, campo(t("lgc_f_rige"), desde, { obligatorio: true }), cajaMotivo),
    h("div", { clase: "chico gris", style: "margin:-4px 0 6px" }, t("lgc_f_motivo_ayuda")),
    avisoFecha,
    h("div", { clase: "acciones" }, guardar, boton(t("lgc_cancelar"), () => alCerrar())));
  revisarFecha();
  return nodo;
}

/* El hueco donde se abre una forma, y como se abre: una a la vez. */
function hueco(d, recargar) {
  const caja = h("div");
  caja.abrir = (clave, opciones = {}) => {
    const nodo = formaValor(d, clave, recargar, () => poner(caja), opciones);
    poner(caja, nodo);
    const primero = nodo.querySelector("input, select");
    if (primero) primero.focus();
  };
  caja.editar = (v) => caja.abrir(v.clave, { fila: v, tipoId: v.tipo_unidad_id });
  return caja;
}

/* Una tarjeta chica con lo que rige de un valor y lo que viene. */
function mini(d, clave, cifra, nota, forma, falta = null) {
  const v = d.vigentes[clave];
  const sig = proximo(d, clave);
  return h("div", { clase: "tarjeta lisa", style: "margin:0" },
    h("h4", {}, t(QUE[clave])),
    h("div", { clase: "cifra" }, v ? cifra(v) : "—"),
    h("div", { clase: "chico gris" },
      v ? t("lgc_desde").replace("{fecha}", fecha(v.vigente_desde)) : null, v ? " " : null,
      v ? estadoDe(v) : etiqueta(falta || t("lgc_falta"), "alerta")),
    sig ? h("div", { clase: "chico", style: "margin-top:6px" },
      t("lgc_cambia_el").replace("{fecha}", fecha(sig.vigente_desde)).replace("{valor}", valorTexto(d, sig)),
      " ", estadoDe(sig)) : null,
    nota ? h("div", { clase: "chico gris", style: "margin-top:6px" }, nota) : null,
    d.puede.dinero ? h("div", { clase: "acciones", style: "margin-top:8px" },
      boton(t("lgc_nuevo_valor"), () => forma.abrir(clave))) : null);
}

/* ============================================================ el tabulador */

function tabulador(caja, d, recargar) {
  const v = d.vigentes.tabulador;
  const forma = hueco(d, recargar);
  const montos = (v && v.datos.tipos) || {};
  const ejemplos = (v && v.calculo && v.calculo.ejemplos) || {};
  const kmBase = v ? v.datos.km_base : 100;
  const ejemploKm = (v && v.calculo && v.calculo.km) || 1450;

  const filas = activos(d).map((x) => {
    const m = montos[String(x.id)];
    return h("tr", {},
      h("td", {}, h("b", {}, x.nombre)),
      h("td", { clase: "num" }, m ? pesos2(m.base) : etiqueta(t("lgc_falta"), "alerta")),
      h("td", { clase: "num" }, m ? porKm(m.por_km) : "—"),
      h("td", { clase: "num gris" }, m ? pesos2(ejemplos[String(x.id)]) : "—"));
  });

  poner(caja, h("div", { clase: "tarjeta" },
    conAyuda("h3", t("lgc_tabulador"), "ay_lgc_tabulador"),
    h("p", { clase: "gris chico ctl-pie" }, t("lgc_tabulador_pie")),
    quienLoLleva(d, "tabulador"),
    v ? rige(v) : h("p", { clase: "aviso alerta" }, t("lgc_tabulador_falta")),
    tabla([t("lgc_col_tipo"), t("lgc_col_primeros").replace("{km}", kms(kmBase)),
           t("lgc_col_por_km"), t("lgc_col_ejemplo").replace("{km}", kms(ejemploKm))], filas),
    d.puede.dinero ? h("div", { clase: "acciones", style: "margin-top:10px" },
      boton(t("lgc_nuevo_tabulador"), () => forma.abrir("tabulador"))) : null,
    forma,
    probar(d),
    (d.valores.tabulador || []).length > 1
      ? h("div", {}, h("h4", { clase: "grupo" }, t("lgc_versiones")),
          tablaValores(d, ["tabulador"], recargar, forma.editar, false))
      : null,
    historial("tabulador")));
}

/* La comision de cualquier viaje, con el tabulador de su fecha. */
function probar(d) {
  const tipos = activos(d);
  const tipo = lista("tipo_prueba", tipos.map(x => ({ valor: String(x.id), texto: x.nombre })));
  const kmC = entrada("km_prueba", { type: "number", step: "any", min: "0", autocomplete: "off" });
  const dia = entrada("fecha_prueba", { type: "date" });
  dia.value = d.hoy;
  const salida = h("div");
  const calcular = boton(t("lgc_probar"), async () => {
    if (kmC.value.trim() === "") {
      mensaje(t("lgc_f_falta").replace("{campo}", t("lgc_f_km")), "alerta");
      kmC.focus();
      return;
    }
    calcular.disabled = true;
    try {
      const r = await api.get(`/lg/catalogos/comision?tipo_unidad_id=${tipo.value}`
        + `&km=${encodeURIComponent(kmC.value)}&fecha=${dia.value || d.hoy}`);
      const largo = Number(r.km_extra) > 0;
      const como = (largo ? t("lgc_probar_como") : t("lgc_probar_corto"))
        .replace("{base}", pesos2(r.base)).replace("{km}", kms(r.km_base))
        .replace("{extra_km}", kms(r.km_extra)).replace("{por_km}", porKm(r.por_km))
        .replace("{extra}", pesos2(r.extra))
        .replace("{desde}", fecha(r.vigente_desde));
      poner(salida, h("div", { clase: "aviso ok", style: "margin:6px 0 0" },
        h("b", {}, t("lgc_probar_res").replace("{total}", pesos2(r.comision))), " — ", como));
    } catch (err) {
      poner(salida, h("div", { clase: "aviso grave", style: "margin:6px 0 0" }, err.message));
    } finally {
      calcular.disabled = false;
    }
  }, "chico");
  kmC.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); calcular.click(); }
  });
  if (!tipos.length) return null;
  return h("div", { clase: "ctl-forma" },
    h("h4", {}, t("lgc_probar_titulo")),
    h("div", { clase: "ctl-campos" },
      campo(t("lgc_f_tipo"), tipo), campo(t("lgc_f_km"), kmC), campo(t("lgc_f_fecha"), dia)),
    h("div", { clase: "acciones" }, calcular),
    salida);
}

/* ============================================================ diesel y anticipo */

function diesel(caja, d, recargar) {
  const forma = hueco(d, recargar);
  poner(caja, h("div", { clase: "tarjeta" },
    conAyuda("h3", t("lgc_diesel"), "ay_lgc_diesel"),
    h("p", { clase: "gris chico ctl-pie" }, t("lgc_diesel_pie")),
    quienLoLleva(d, "diesel"),
    h("div", { clase: "rejilla tres", style: "margin-bottom:14px" },
      mini(d, "diesel", v => h("span", {}, pesos2(v.valor), " ",
        h("span", { clase: "chico gris", style: "font-weight:400" }, t("lgc_por_litro"))), null, forma),
      mini(d, "holgura", v => pct(v.valor), t("lgc_holgura_nota"), forma),
      mini(d, "tolerancia", v => pct(v.valor), t("lgc_tolerancia_nota"), forma)),
    forma,
    h("h4", { clase: "grupo" }, t("lgc_valores")),
    tablaValores(d, ["diesel", "holgura", "tolerancia"], recargar, forma.editar),
    historial("diesel")));
}

/* ============================================================ alimentos y margen */

function alimentos(caja, d, recargar) {
  const forma = hueco(d, recargar);
  poner(caja, h("div", { clase: "tarjeta" },
    conAyuda("h3", t("lgc_alimentos"), "ay_lgc_alimentos"),
    h("p", { clase: "gris chico ctl-pie" }, t("lgc_alimentos_pie")),
    quienLoLleva(d, "alimentos"),
    h("div", { clase: "rejilla dos", style: "margin-bottom:14px" },
      mini(d, "alimentos", v => pesos(v.valor), t("lgc_alimentos_nota"), forma),
      mini(d, "margen", v => pct(v.valor), t("lgc_margen_nota"), forma)),
    forma,
    h("h4", { clase: "grupo" }, t("lgc_valores")),
    tablaValores(d, ["alimentos", "margen"], recargar, forma.editar),
    historial("alimentos")));
}

/* ============================================================ el operador */

function operador(caja, d, recargar) {
  const forma = hueco(d, recargar);
  const v = d.vigentes.operador;
  const sig = proximo(d, "operador");
  const cifra = (titulo, valor, pie, fondo = false) => h("div", {
    clase: "tarjeta lisa", style: fondo ? "margin:0;background:#f4f6fb" : "margin:0" },
    h("h4", {}, titulo), h("div", { clase: "cifra" }, valor), h("div", { clase: "chico gris" }, pie));
  const desde = v ? h("span", {}, t("lgc_desde").replace("{fecha}", fecha(v.vigente_desde)), " ", estadoDe(v))
    : etiqueta(t("lgc_lo_da_rh"), "alerta");
  poner(caja, h("div", { clase: "tarjeta" },
    conAyuda("h3", t("lgc_operador"), "ay_lgc_operador"),
    h("p", { clase: "gris chico ctl-pie" }, t("lgc_operador_pie")),
    quienLoLleva(d, "operador"),
    h("div", { clase: "rejilla tres" },
      cifra(t("lgc_f_costo_mensual"), v ? pesos(v.datos.costo_mensual) : "—", desde),
      cifra(t("lgc_f_dias"), v ? String(v.datos.dias_laborables) : "—", v ? desde.cloneNode(true) : "—"),
      cifra(t("lgc_costo_dia"), v ? pesos2(v.calculo.costo_dia) : "—",
        v ? t("lgc_costo_dia_como").replace("{mes}", pesos(v.datos.costo_mensual))
          .replace("{dias}", v.datos.dias_laborables) : t("lgc_lo_calcula"), true)),
    sig ? h("p", { clase: "chico", style: "margin:10px 0 0" },
      t("lgc_cambia_el").replace("{fecha}", fecha(sig.vigente_desde)).replace("{valor}", valorTexto(d, sig)),
      " ", estadoDe(sig)) : null,
    h("div", { clase: "aviso alerta", style: "margin-top:12px" }, t("lgc_operador_aviso")),
    d.puede.dinero ? h("div", { clase: "acciones", style: "margin-top:10px" },
      boton(t("lgc_nuevo_valor"), () => forma.abrir("operador"))) : null,
    forma,
    h("h4", { clase: "grupo" }, t("lgc_valores")),
    tablaValores(d, ["operador"], recargar, forma.editar, false),
    historial("operador")));
}

/* ============================================================ costo por tipo */

let tipoVisto = null;

function costos(caja, d, recargar) {
  const forma = hueco(d, recargar);
  const tipos = activos(d);
  const vig = (x) => d.vigentes.unidad[String(x.id)] || null;
  if (!tipos.some(x => x.id === tipoVisto)) {
    tipoVisto = (tipos.find(vig) || tipos[0] || {}).id || null;
  }
  const detalle = h("div");

  function pintarDetalle() {
    const x = tipos.find(y => y.id === tipoVisto);
    if (!x) { poner(detalle); return; }
    const v = vig(x);
    const c = v ? v.calculo : null;
    const dd = v ? v.datos : null;
    const renglon = (texto, como, monto, estimado = false) => h("tr", {},
      h("td", {}, texto), h("td", { clase: "chico gris" }, como,
        estimado ? ` · ${t("lgc_c_estimado")}` : null),
      h("td", { clase: "num" }, monto));
    const anual = (monto) => t("lgc_c_al_anio").replace("{monto}", pesos(monto));
    poner(detalle, h("div", { clase: "ctl-forma" },
      h("h4", {}, t("lgc_como_sale").replace("{tipo}", x.nombre)),
      v ? tabla([t("lgc_col_componente"), t("lgc_col_como"), t("lgc_col_costo_dia")], [
        renglon(t("lgc_c_depreciacion"), t("lgc_c_depreciacion_como")
          .replace("{compra}", pesos(dd.compra)).replace("{anios}", kms(dd.anios)), pesos2(c.depreciacion)),
        renglon(t("lgc_c_seguro"), anual(dd.seguro), pesos2(c.seguro)),
        renglon(t("lgc_c_mantenimiento"), anual(dd.mantenimiento), pesos2(c.mantenimiento), true),
        renglon(t("lgc_c_llantas"), anual(dd.llantas), pesos2(c.llantas), true),
        renglon(t("lgc_c_gps"), anual(dd.gps), pesos2(c.gps)),
        h("tr", {}, h("td", {}, h("b", {}, t("lgc_costo_dia"))), h("td", {}),
          h("td", { clase: "num" }, h("b", {}, pesos2(c.costo_dia)))),
      ]) : h("p", { clase: "chico gris" }, t("lgc_costos_sin")),
      v ? h("p", { clase: "chico gris", style: "margin:8px 0 0" }, t("lgc_costos_nota")) : null,
      (d.valores.unidad || []).some(y => y.tipo_unidad_id === x.id)
        ? h("div", {}, h("h4", { clase: "grupo" }, t("lgc_valores")),
            tablaValores({ ...d, valores: { unidad: d.valores.unidad.filter(y => y.tipo_unidad_id === x.id) } },
                         ["unidad"], recargar, forma.editar, false))
        : null));
  }

  const filas = tipos.map((x) => {
    const v = vig(x);
    return h("tr", {
      style: x.id === tipoVisto ? "background:#f4f6fb;cursor:pointer" : "cursor:pointer",
      onclick: (e) => {
        if (e.target.tagName === "BUTTON") return;
        tipoVisto = x.id;
        poner(caja);
        costos(caja, d, recargar);
      },
    },
      h("td", {}, h("b", {}, x.nombre)),
      h("td", { clase: "num" }, v ? t("lgc_km_l").replace("{n}", kms(v.datos.rendimiento)) : "—"),
      h("td", { clase: "num" }, v ? h("b", {}, pesos2(v.calculo.costo_dia)) : "—"),
      h("td", { clase: "num", style: "white-space:nowrap" },
        v ? h("span", {}, fecha(v.vigente_desde), " ", estadoDe(v)) : etiqueta(t("lgc_lo_da_flota"), "alerta")),
      h("td", { style: "text-align:right;white-space:nowrap" }, d.puede.dinero
        ? boton(t(v ? "lgc_nuevo_valor_corto" : "lgc_capturar"),
                () => forma.abrir("unidad", { tipoId: x.id })) : null));
  });

  poner(caja, h("div", { clase: "tarjeta" },
    conAyuda("h3", t("lgc_costos_titulo"), "ay_lgc_costos"),
    h("p", { clase: "gris chico ctl-pie" }, t("lgc_costos_pie")),
    quienLoLleva(d, "costos"),
    tabla([t("lgc_col_tipo"), t("lgc_col_rendimiento"), t("lgc_col_costo_dia"), t("lgc_col_rige"), ""], filas),
    forma,
    detalle,
    historial("costos")));
  pintarDetalle();
}

/* ============================================================ bono y garantia */

function bono(caja, d, recargar) {
  const forma = hueco(d, recargar);
  const b = d.vigentes.bono;
  const g = d.vigentes.garantia;
  const tramos = b ? [...b.datos.tramos].sort((x, y) => Number(x.desde_anios) - Number(y.desde_anios)) : [];
  const rango = (i) => {
    const desde = Number(tramos[i].desde_anios);
    const sig = tramos[i + 1] ? Number(tramos[i + 1].desde_anios) - 1 : null;
    if (sig === null) return desde === 0 ? t("lgc_tramo_todos") : t("lgc_tramo_desde").replace("{n}", desde);
    if (desde === 0) return t("lgc_tramo_hasta").replace("{n}", sig);
    return t("lgc_tramo_entre").replace("{a}", desde).replace("{b}", sig);
  };
  const pie = (v, faltaTxt) => h("div", { clase: "chico gris", style: "margin-top:6px" },
    v ? t("lgc_desde").replace("{fecha}", fecha(v.vigente_desde)) : null, v ? " " : null,
    v ? estadoDe(v) : etiqueta(faltaTxt, "alerta"));
  const sigB = proximo(d, "bono");
  const sigG = proximo(d, "garantia");
  const viene = (sig) => (sig ? h("div", { clase: "chico", style: "margin-top:6px" },
    t("lgc_cambia_el").replace("{fecha}", fecha(sig.vigente_desde)).replace("{valor}", valorTexto(d, sig)),
    " ", estadoDe(sig)) : null);

  poner(caja, h("div", { clase: "tarjeta" },
    conAyuda("h3", t("lgc_bono_titulo"), "ay_lgc_bono"),
    h("p", { clase: "gris chico ctl-pie" }, t("lgc_bono_pie")),
    quienLoLleva(d, "bono"),
    h("div", { clase: "rejilla dos" },
      h("div", { clase: "tarjeta lisa", style: "margin:0" },
        h("h4", {}, t("lgc_q_bono")),
        b ? tabla([t("lgc_col_antiguedad"), t("lgc_col_sobre")],
                  tramos.map((x, i) => h("tr", {}, h("td", {}, rango(i)), h("td", { clase: "num" }, pct(x.pct)))))
          : h("div", { clase: "cifra" }, "—"),
        b ? h("div", { clase: "chico", style: "margin-top:8px" },
          t("lgc_bono_dias").replace("{n}", b.datos.dias_requeridos)) : null,
        pie(b, t("lgc_lo_da_rh")),
        viene(sigB),
        d.puede.dinero ? h("div", { clase: "acciones", style: "margin-top:8px" },
          boton(t("lgc_nuevo_valor"), () => forma.abrir("bono"))) : null),
      h("div", { clase: "tarjeta lisa", style: "margin:0" },
        h("h4", {}, g ? t("lgc_garantia_de").replace("{tipo}", nombreTipo(d, g.datos.tipo_unidad_id))
                      : t("lgc_q_garantia")),
        h("div", { clase: "cifra" }, g ? pesos(g.datos.monto_semanal) : "—"),
        h("div", { clase: "chico gris" }, t("lgc_garantia_nota")),
        g ? tabla([t("lgc_col_regla"), ""], [
          h("tr", {}, h("td", {}, t("lgc_f_exige")),
            h("td", {}, t(g.datos.exige_dias_completos ? "lgc_si" : "lgc_no"))),
          h("tr", {}, h("td", {}, t("lgc_f_sobre")),
            h("td", {}, t(g.datos.bono_sobre_garantia ? "lgc_si" : "lgc_no")))]) : null,
        pie(g, t("lgc_lo_da_rh")),
        viene(sigG),
        d.puede.dinero ? h("div", { clase: "acciones", style: "margin-top:8px" },
          boton(t("lgc_nuevo_valor"), () => forma.abrir("garantia"))) : null)),
    h("div", { clase: "aviso", style: "margin-top:12px" }, t("lgc_bono_aviso")),
    forma,
    h("h4", { clase: "grupo" }, t("lgc_valores")),
    tablaValores(d, ["bono", "garantia"], recargar, forma.editar),
    historial("bono")));
}

/* ============================================================ tipos de unidad */

function prenderBoton(ruta, activo, nombre, recargar) {
  return boton(t(activo ? "lgc_quitar" : "lgc_reactivar"), async (e) => {
    if (activo && !confirm(t("lgc_quitar_tipo_seguro").replace("{que}", nombre))) return;
    e.target.disabled = true;
    try {
      if (activo) await api.borrar(ruta);
      else await api.post(`${ruta}/reactivar`);
      mensaje(t(activo ? "lgc_quitado" : "lgc_reactivado"));
      await recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  });
}

/* Una forma chica de catalogo: los campos y sus dos botones. */
function formaSimple(campos, alGuardar, alCancelar) {
  const controles = {};
  const cajas = campos.map((c) => {
    const control_ = entrada(c.k, { type: c.numero ? "number" : "text", step: c.numero ? "any" : null,
                                     autocomplete: "off", "data-crudo": c.crudo ? "" : null });
    control_.value = nada(c.valor) ? "" : String(c.valor);
    controles[c.k] = control_;
    return campo(c.texto, control_, { obligatorio: !!c.requerido });
  });
  const guardar = boton(t("lgc_guardar"), async () => {
    const valores = {};
    for (const c of campos) {
      const v = controles[c.k].value.trim();
      if (c.requerido && v === "") {
        mensaje(t("lgc_f_falta").replace("{campo}", c.texto), "alerta");
        controles[c.k].focus();
        return;
      }
      valores[c.k] = v === "" ? null : (c.numero ? Number(v) : v);
    }
    guardar.disabled = true;
    try {
      await alGuardar(valores);
    } catch (err) {
      mensaje(err.message, "grave");
      guardar.disabled = false;
    }
  }, "chico");
  const nodo = h("div", { clase: "ctl-forma" },
    h("div", { clase: "ctl-campos" }, ...cajas),
    h("div", { clase: "acciones" }, guardar, boton(t("lgc_cancelar"), () => alCancelar())));
  nodo.controles = controles;
  return nodo;
}

function tipos(caja, d, recargar) {
  const forma = h("div");
  const abrir = (x) => {
    poner(forma, formaSimple([
      { k: "nombre", texto: t("lgc_f_nombre"), valor: x && x.nombre, requerido: true, crudo: true },
      { k: "capacidad_ton", texto: t("lgc_f_capacidad"), valor: x && x.capacidad_ton, numero: true },
      { k: "nombre_tango", texto: t("lgc_f_tango"), valor: x && x.nombre_tango, crudo: true },
      { k: "orden", texto: t("lgc_f_orden"), valor: x && x.orden, numero: true },
    ], async (v) => {
      if (x) await api.patch(`/lg/catalogos/tipos/${x.id}`, v);
      else await api.post("/lg/catalogos/tipos", v);
      mensaje(t("lgc_guardado"));
      await recargar();
    }, () => poner(forma)));
  };
  const filas = d.tipos.map(x => h("tr", { clase: x.activo ? "" : "apagado" },
    h("td", {}, h("b", {}, x.nombre)),
    h("td", { clase: "num" }, nada(x.capacidad_ton) ? "—" : t("lgc_ton").replace("{n}", kms(x.capacidad_ton))),
    h("td", { clase: "gris" }, x.nombre_tango || "—"),
    h("td", { style: "text-align:right;white-space:nowrap" },
      d.puede.editar && x.activo ? boton(t("lgc_editar"), () => abrir(x)) : null,
      d.puede.editar ? prenderBoton(`/lg/catalogos/tipos/${x.id}`, x.activo, x.nombre, recargar) : null)));
  poner(caja, h("div", { clase: "tarjeta" },
    conAyuda("h3", t("lgc_tipos"), "ay_lgc_tipos"),
    h("p", { clase: "gris chico ctl-pie" }, t("lgc_tipos_pie")),
    quienLoLleva(d, "tipos"),
    tabla([t("lgc_col_tipo_corto"), t("lgc_col_capacidad"), t("lgc_col_tango"), ""], filas),
    d.puede.editar ? h("div", { clase: "acciones", style: "margin-top:10px" },
      boton(t("lgc_agregar_tipo"), () => abrir(null))) : null,
    forma,
    historial("tipos")));
}

/* ============================================================ patios */

/* Buscar el patio en Google y traerse su direccion y su punto. Se busca
   al picar, no mientras se escribe: cada busqueda se cobra. El nombre no
   se pisa: el patio se llama como le dice Centauro. */
function buscadorGoogle(d, forma) {
  const texto = entrada("buscar_google", { placeholder: t("lgc_google_ayuda"),
                                            autocomplete: "off", "data-crudo": "" });
  const hallados = h("div");
  const buscar = boton(t("lgc_google_buscar"), async () => {
    if (texto.value.trim().length < 3) return;
    buscar.disabled = true;
    try {
      const r = await api.get(`/mapas/lugares?texto=${encodeURIComponent(texto.value.trim())}`
        + `&pais_id=${d.pais_id || ""}`);
      poner(hallados, r.lugares.length ? r.lugares.map(l => h("div", { clase: "ctl-hallado" },
        h("div", {}, h("b", {}, l.nombre || "—"), h("div", { clase: "chico gris" }, l.direccion || "")),
        boton(t("lgc_google_usar"), () => {
          const c = forma.controles;
          if (!c.nombre.value.trim() && l.nombre) c.nombre.value = l.nombre;
          if (l.direccion) c.direccion.value = l.direccion;
          c.lat.value = l.lat;
          c.lon.value = l.lon;
          poner(hallados);
        }))) : h("p", { clase: "chico gris" }, t("lgc_google_nada")));
    } catch (err) {
      mensaje(err.message, "grave");
    } finally {
      buscar.disabled = false;
    }
  });
  texto.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); buscar.click(); }
  });
  return h("div", { clase: "ctl-google" },
    h("div", { clase: "acciones" }, h("div", { style: "flex:1 1 260px" }, texto), buscar),
    hallados);
}

function patios(caja, d, recargar) {
  const forma = h("div");
  const abrir = (x) => {
    const nodo = formaSimple([
      { k: "nombre", texto: t("lgc_f_nombre"), valor: x && x.nombre, requerido: true, crudo: true },
      { k: "direccion", texto: t("lgc_f_direccion"), valor: x && x.direccion, crudo: true },
      { k: "lat", texto: t("lgc_f_lat"), valor: x && x.lat, numero: true },
      { k: "lon", texto: t("lgc_f_lon"), valor: x && x.lon, numero: true },
      { k: "geocerca_metros", texto: t("lgc_f_geocerca"), valor: x ? x.geocerca_metros : 300,
        numero: true, requerido: true },
    ], async (v) => {
      if ((v.lat === null) !== (v.lon === null)) throw new Error(t("lgc_punto_completo"));
      if (x) await api.patch(`/lg/catalogos/patios/${x.id}`, v);
      else await api.post("/lg/catalogos/patios", v);
      mensaje(t("lgc_guardado"));
      await recargar();
    }, () => poner(forma));
    poner(forma, d.puede.buscar ? buscadorGoogle(d, nodo) : null, nodo);
    nodo.controles.nombre.focus();
  };
  const filas = d.patios.map(x => h("tr", { clase: x.activo ? "" : "apagado" },
    h("td", {}, h("b", {}, x.nombre), x.direccion ? h("div", { clase: "chico gris" }, x.direccion) : null),
    h("td", {}, nada(x.lat) ? etiqueta(t("lgc_sin_ubicacion"), "alerta")
      : h("span", { clase: "chico gris num" }, `${Number(x.lat).toFixed(4)}, ${Number(x.lon).toFixed(4)}`)),
    h("td", { clase: "num" }, t("lgc_m").replace("{n}", kms(x.geocerca_metros))),
    h("td", { style: "text-align:right;white-space:nowrap" },
      d.puede.editar && x.activo ? boton(t("lgc_editar"), () => abrir(x)) : null,
      d.puede.editar ? prenderBoton(`/lg/catalogos/patios/${x.id}`, x.activo, x.nombre, recargar) : null)));
  poner(caja, h("div", { clase: "tarjeta" },
    conAyuda("h3", t("lgc_patios"), "ay_lgc_patios"),
    h("p", { clase: "gris chico ctl-pie" }, t("lgc_patios_pie")),
    quienLoLleva(d, "patios"),
    tabla([t("lgc_col_patio"), t("lgc_col_ubicacion"), t("lgc_col_geocerca"), ""], filas),
    d.puede.editar ? h("div", { clase: "acciones", style: "margin-top:10px" },
      boton(t("lgc_agregar_patio"), () => abrir(null))) : null,
    forma,
    historial("patios")));
}

const PINTA = { tabulador, diesel, alimentos, operador, costos, bono, tipos, patios };

/* ============================================================ la bitacora */

/* Todo lo que le ha pasado a los catalogos de Logistica, lo mas nuevo
   arriba: quien, cuando, en cual y que cambio. La de toda la
   administracion vive en Catalogos -> Bitacora, para quien la lee. */
async function pestanaBitacora(zona) {
  let catalogo = "";
  let pagina = 1;
  let filas = [];
  let total = 0;
  const cuerpo = h("div");
  const sel = lista("catalogo", [{ valor: "", texto: t("lgc_bit_todos") },
    ...CATALOGOS.map(c => ({ valor: c, texto: t(TITULO[c]) }))], { style: "width:auto" });

  async function cargar(mas = false) {
    const r = await api.get(`/lg/catalogos/bitacora?catalogo=${catalogo}&pagina=${pagina}`
      + `&idioma=${idioma()}`);
    filas = mas ? [...filas, ...r.filas] : r.filas;
    total = r.total;
    pintar();
  }

  function pintar() {
    poner(cuerpo,
      tabla([t("lgc_col_cuando"), t("lgc_col_quien"), t("lgc_col_donde"), t("lgc_col_que_cambio")],
        filas.map(x => h("tr", {},
          h("td", { clase: "num", style: "white-space:nowrap" }, `${fecha(x.cuando)} ${hora(x.cuando)}`),
          h("td", {}, x.quien || "—"),
          h("td", { clase: "chico" }, x.donde),
          h("td", {}, x.que))), "lgc_bit_vacia"),
      filas.length < total
        ? h("div", { clase: "acciones", style: "margin-top:10px" },
            boton(t("lgc_ver_mas"), async () => { pagina += 1; await cargar(true); }))
        : null);
  }

  sel.addEventListener("change", async () => {
    catalogo = sel.value;
    pagina = 1;
    await cargar();
  });
  poner(zona, h("div", { clase: "tarjeta" },
    h("div", { clase: "acciones", style: "margin:0 0 12px" }, sel),
    cuerpo));
  await cargar();
}

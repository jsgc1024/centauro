/* Catalogos (seccion 86).

   Lo que el sistema usa para calcular y para armar la hoja del servicio.
   Hasta hoy casi todo esto solo se movia desde /docs, con la llave
   maestra: los festivos, los hospitales, el combustible, el tabulador.

   Dos grupos, como se decidio el 27 de septiembre con la propuesta del
   puesto de administracion del sistema y calidad:

     - Los que no deciden dinero --festivos, hospitales, hoteles,
       ciudades, combustible, unidades por categoria, perfiles y paises--
       los lleva sistema y calidad.
     - Los que si --el tabulador de viaticos, las horas de cada
       modalidad y los pesos del profesionalismo-- los fija direccion de
       operaciones. Sistema y calidad los ve con su candado. Los costos
       de cada freelance viven en su ficha (seccion 111).

   Y lo que ya tiene su pantalla se dice donde vive, con su enlace: los
   tarifarios, lo que se paga por dia, los criterios del bono, el tipo de
   cambio.

   Cada cambio queda en la bitacora --quien, cuando, antes y despues-- y
   abajo de cada catalogo se ve lo ultimo que le paso. La bitacora entera
   es la otra pestana, para quien trae `bitacora.ver`.

   Quien puede escribir en cada uno lo decide el servidor; aqui solo se
   deja de pintar el boton que le contestaria que no. */
import { api, sesion } from "./api.js";
import { campo, conAyuda, dinero, entrada, etiqueta, fecha, h, hora,
         hoyLocal, lista, mensaje, reducirImagen } from "./util.js";
import { idioma, t } from "./idioma.js";
import { menuDe, tiene } from "./menu.js";
import { pestanaBitacora } from "./bitacora_admin.js";

const CANDADO = '<svg width="11" height="13" viewBox="0 0 11 13" aria-hidden="true">'
  + '<rect x="0.5" y="5.5" width="10" height="7" rx="1.5" fill="currentColor"/>'
  + '<path d="M2.8 5.5V3.8a2.7 2.7 0 0 1 5.4 0v1.7" fill="none" '
  + 'stroke="currentColor" stroke-width="1.4"/></svg>';

/* Quien escribe en cada uno: la misma actividad que pide el servidor. */
const ESCRIBE = {
  "dias-festivos": "catalogos.editar", hospitales: "catalogos.editar",
  hoteles: "catalogos.editar", plazas: "ciudades.alta",
  "parametros-combustible": "catalogos.editar",
  "categorias-vehiculo": "catalogos.editar", paises: "catalogos.editar",
  "tabulador-viaticos": "catalogos.dinero", modalidades: "catalogos.dinero",
  "requisitos-freelance": "catalogos.editar",
  profesionalismo: "profesionalismo.pesos",
};
/* Los costos de cada freelance salieron de aqui (seccion 111): viven en
   su ficha, en Personal de seguridad. Entro la lista de lo que Recursos
   Humanos pide para activarlo, que lleva sistema y calidad. */
const DE_SISTEMA = ["dias-festivos", "hospitales", "hoteles", "plazas",
                    "parametros-combustible", "categorias-vehiculo", "paises",
                    "requisitos-freelance"];
const DE_DINERO = ["tabulador-viaticos", "modalidades", "profesionalismo"];
const TITULO = {
  "dias-festivos": "ctl_festivos", hospitales: "ctl_hospitales",
  hoteles: "ctl_hoteles", plazas: "ctl_ciudades",
  "parametros-combustible": "ctl_combustible",
  "categorias-vehiculo": "ctl_categorias", paises: "ctl_paises",
  "tabulador-viaticos": "ctl_tabulador", modalidades: "ctl_modalidades",
  "requisitos-freelance": "ctl_requisitos", profesionalismo: "ctl_pesos",
};
/* Lo que ya tiene su pantalla: se dice donde vive. */
const CON_PANTALLA = [
  { texto: "ctl_ln_tarifarios", clave: "odoo", donde: "nav_odoo" },
  { texto: "ctl_ln_comisiones", clave: "nomina", donde: "nav_nomina" },
  { texto: "ctl_ln_bono", clave: "bonos", donde: "nav_bonos" },
  { texto: "ctl_ln_tipo_cambio", clave: "facturacion", donde: "nav_facturacion" },
];

const CONCEPTOS = [["alimentos", "cie_con_alimentos"], ["hospedaje", "cie_con_hospedaje"],
                   ["combustible", "cie_con_combustible"], ["casetas", "cie_con_casetas"],
                   ["traslado_personal", "cie_con_traslado"], ["otros", "cie_con_otros"]];
const ESCENARIOS = [["full_day_local", "ctl_esc_local"], ["full_day_foraneo", "ctl_esc_foraneo"],
                    ["medio_dia", "mod_medio_dia"], ["transfer", "mod_transfer"]];
/* El implantado es siempre dia completo (seccion 109, caso de Salvador):
   su tabla solo lleva el local y el foraneo. Medio dia y transfer no le
   aplican y pedirlos confundia --parecia que faltaba capturarlos--. */
const ESCENARIOS_DE = (tipo) => (tipo === "implantado"
  ? ESCENARIOS.filter(([e]) => e.startsWith("full_day")) : ESCENARIOS);
/* La del implantado (seccion 105): su jornada, aparte del full day del
   eventual. Es donde se cambian sus horas de descanso. */
const MODALIDADES = [["full_day", "mod_full_day"], ["medio_dia", "mod_medio_dia"],
                     ["transfer", "mod_transfer"], ["implantado", "cat_mod_implantado"]];
const NIVELES = () => [
  { valor: "", texto: "—" },
  { valor: "tercer_nivel", texto: t("imp_hosp_tercero") },
  { valor: "segundo_nivel", texto: t("imp_hosp_segundo") },
  { valor: "primer_nivel", texto: t("imp_hosp_primero") },
];
const DIMENSIONES = [["estrellas", "ctl_dim_estrellas"], ["satisfaccion", "ctl_dim_satisfaccion"],
                     ["incidencias", "ctl_dim_incidencias"], ["capacitacion", "ctl_dim_capacitacion"],
                     ["experiencia", "ctl_dim_experiencia"], ["manejo", "ctl_dim_manejo"]];
const MONEDAS = ["MXN", "BRL", "USD", "VES"];
const IDIOMAS_APP = [["es", "ctl_idioma_es"], ["en", "ctl_idioma_en"], ["pt", "ctl_idioma_pt"]];

const puede = (clave) => tiene(sesion.usuario, ESCRIBE[clave]);

/* El pais que se esta mirando se queda al cambiar de catalogo: quien
   revisa Brasil revisa sus festivos, su combustible y su tabulador de
   corrido. Arranca en el de quien mira; si no tiene, en Mexico. */
let paisVisto = null;
function paisInicial(d) {
  const valido = (id) => d.paises.some(p => p.id === id);
  if (valido(paisVisto)) return paisVisto;
  const suyo = (sesion.usuario || {}).pais_id;
  if (valido(suyo)) return suyo;
  return (d.paises.find(p => p.codigo === "MX") || d.paises[0] || {}).id;
}
const ANIO = () => new Date().getFullYear();
const HOY = () => hoyLocal();

/* ============================================================ la pantalla */

export async function pantallaCatalogos(main) {
  const conBitacora = tiene(sesion.usuario, "bitacora.ver");
  const pestanas = h("div", { clase: "pestanas", style: "margin:0 0 14px" });
  const zona = h("div");
  let vista = "catalogos";

  function pintarPestanas() {
    pestanas.replaceChildren(...[["catalogos", "ctl_pestana_catalogos"],
                                 ["bitacora", "ctl_pestana_bitacora"]]
      .map(([clave, texto]) => h("button", {
        type: "button", clase: clave === vista ? "pestana activa" : "pestana",
        onclick: () => { vista = clave; pintarPestanas(); pintarVista(); },
      }, t(texto))));
  }

  async function pintarVista() {
    zona.replaceChildren(...[h("div", { clase: "gris chico" }, "…")].filter(Boolean));
    try {
      if (vista === "bitacora") await pestanaBitacora(zona);
      else await pestanaCatalogos(zona);
    } catch (err) {
      zona.replaceChildren(...[h("div", { clase: "aviso grave" }, err.message)].filter(Boolean));
    }
  }

  main.append(...[
    h("h1", {}, t("ctl_titulo")),
    h("p", { clase: "sub" }, t("ctl_pie")),
    conBitacora ? pestanas : null,
    zona,
  ].filter(Boolean));
  if (conBitacora) pintarPestanas();
  await pintarVista();
}

/* ============================================================ los datos */

/* Todo de una vez: son catalogos chicos, y con todo a la mano la lista
   de la izquierda dice que le falta a cada uno sin abrirlo. */
async function traer() {
  const [paises, plazas, perfiles, categorias, festivos, combustible,
         hospitales, hoteles, modalidades, tabulador, requisitos_,
         colores] = await Promise.all([
    api.get("/catalogos/paises"),
    api.get("/catalogos/plazas?todas=true"),
    api.get("/catalogos/perfiles"),
    api.get("/catalogos/categorias-vehiculo"),
    api.get("/catalogos/dias-festivos?incluir_inactivos=true"),
    api.get("/catalogos/parametros-combustible?incluir_inactivos=true"),
    api.get("/catalogos/hospitales?incluir_inactivos=true"),
    api.get("/catalogos/hoteles?todos=true"),
    api.get("/catalogos/modalidades"),
    api.get("/catalogos/tabulador-viaticos"),
    api.get("/catalogos/requisitos-freelance?incluir_inactivos=true"),
    api.get("/catalogos/categorias-vehiculo/colores").catch(() => ({})),
  ]);
  const pesos = {};
  await Promise.all(paises.map(async (p) => {
    pesos[p.id] = await api.get(`/profesionalismo/pesos?pais_id=${p.id}`)
      .catch(() => null);
  }));
  /* Lo quitado viene en las listas (seccion 101) y se aparta: las cuentas
     y los selectores siguen con lo vivo, y cada tabla lo pinta en gris
     con «Reactivar». Antes lo quitado no tenia vuelta: la lista no lo
     traia y volver a darlo de alta chocaba con «ya existe». */
  const apagados = {};
  const vivos = (clave, lista) => {
    apagados[clave] = lista.filter(x => x.activo === false);
    return lista.filter(x => x.activo !== false);
  };
  return { paises, plazas: vivos("plazas", plazas), perfiles, categorias,
           festivos: vivos("festivos", festivos),
           combustible: vivos("combustible", combustible),
           hospitales: vivos("hospitales", hospitales),
           hoteles: vivos("hoteles", hoteles), modalidades, tabulador,
           requisitos: requisitos_, colores, pesos, apagados };
}

const apagadosDe = (d, clave, filtro) => (d.apagados[clave] || []).filter(filtro);

const paisDe = (d, id) => d.paises.find(p => p.id === Number(id));
const nombrePais = (d, id) => (paisDe(d, id) || {}).nombre || "—";
const monedaDe = (d, id) => (paisDe(d, id) || {}).moneda_local || "MXN";
const nombreCiudad = (d, id) => {
  const c = d.plazas.find(p => p.id === Number(id));
  return c ? c.nombre : "—";
};
const opcionesCiudad = (d, paisId, vacia) => [
  ...(vacia ? [{ valor: "", texto: vacia }] : []),
  ...d.plazas.filter(p => p.pais_id === Number(paisId))
    .map(p => ({ valor: String(p.id), texto: p.nombre }))];
const numero = (v) => (v === null || v === undefined ? "—" : String(Number(v)));
const siNo = (v) => t(v ? "ctl_si" : "ctl_no");

function vigenteDe(d, paisId) {
  const hoy = HOY();
  return d.combustible
    .filter(c => c.pais_id === paisId && c.vigencia_desde <= hoy)
    .sort((a, b) => b.vigencia_desde.localeCompare(a.vigencia_desde))[0] || null;
}

/* ================================================ la lista de la izquierda */

/* Lo que dice cada catalogo en su renglon, y lo que le falta. */
const RESUMEN = {
  "dias-festivos": (d) => d.paises.map(p => `${p.nombre} ${
    d.festivos.filter(f => f.pais_id === p.id && f.fecha.startsWith(String(ANIO()))).length}`)
    .join(" · "),
  hospitales: (d) => t("ctl_res_hospitales")
    .replace("{n}", d.hospitales.length)
    .replace("{c}", new Set(d.hospitales.map(x => x.plaza_id).filter(Boolean)).size),
  hoteles: (d) => t("ctl_res_hoteles").replace("{n}", d.hoteles.length)
    .replace("{s}", d.hoteles.filter(x => x.lat === null || x.lat === undefined).length),
  plazas: (d) => t("ctl_res_ciudades").replace("{n}", d.plazas.length)
    .replace("{p}", d.plazas.filter(x => x.tiene_recurso_local).length),
  "parametros-combustible": (d) => d.paises.map((p) => {
    const v = vigenteDe(d, p.id);
    return v ? `${p.nombre} ${dinero(v.precio_litro, p.moneda_local)}` : null;
  }).filter(Boolean).join(" · ") || t("ctl_res_vacio"),
  "categorias-vehiculo": (d) => t("ctl_res_categorias").replace("{n}", d.categorias.length),
  paises: (d) => t("ctl_res_paises").replace("{p}", d.paises.length)
    .replace("{f}", d.perfiles.length),
  "tabulador-viaticos": () => t("ctl_res_tabulador"),
  modalidades: (d) => {
    const primero = d.paises[0];
    if (!primero) return t("ctl_res_vacio");
    return MODALIDADES.map(([codigo, texto]) => {
      const x = d.modalidades.find(mo => mo.pais_id === primero.id && mo.codigo === codigo);
      return x ? `${t(texto)} ${numero(x.horas)} h` : null;
    }).filter(Boolean).join(" · ");
  },
  "requisitos-freelance": (d) => {
    const vivos = d.requisitos.filter(x => x.activo !== false);
    return t("ctl_res_requisitos")
      .replace("{n}", vivos.length)
      .replace("{p}", new Set(vivos.map(x => x.pais_id)).size);
  },
  profesionalismo: () => t("ctl_res_pesos"),
};

const FALTA = {
  "dias-festivos": (d) => {
    const sin = d.paises.find(p => !d.festivos.some(
      f => f.pais_id === p.id && f.fecha.startsWith(String(ANIO()))));
    return sin ? t("ctl_falta").replace("{que}", sin.nombre) : null;
  },
  hospitales: (d) => {
    const sin = d.plazas.filter(c => c.tiene_recurso_local
      && !d.hospitales.some(x => x.plaza_id === c.id));
    return sin.length ? t("ctl_ninguno_en").replace("{ciudad}", sin[0].nombre) : null;
  },
  hoteles: (d) => {
    const n = d.hoteles.filter(x => x.lat === null || x.lat === undefined).length;
    return n ? t("ctl_sin_ubicacion_n").replace("{n}", n) : null;
  },
  "parametros-combustible": (d) => {
    const sin = d.paises.find(p => !vigenteDe(d, p.id));
    return sin ? t("ctl_falta").replace("{que}", sin.nombre) : null;
  },
  "categorias-vehiculo": (d) => {
    const n = d.categorias.filter(c => !(c.fotos || []).length).length;
    return n ? t("ctl_sin_foto_n").replace("{n}", n) : null;
  },
  "tabulador-viaticos": (d) => {
    const sin = d.paises.find(p => !d.tabulador.some(x => x.pais_id === p.id));
    return sin ? t("ctl_falta").replace("{que}", sin.nombre) : null;
  },
  modalidades: (d) => {
    const sin = d.paises.find(p => MODALIDADES.some(([codigo]) =>
      !d.modalidades.some(x => x.pais_id === p.id && x.codigo === codigo)));
    return sin ? t("ctl_falta").replace("{que}", sin.nombre) : null;
  },
  /* Sin lista, el freelance de ese pais no se puede asignar. */
  "requisitos-freelance": (d) => {
    const sin = d.paises.find(p => !d.requisitos.some(
      x => x.pais_id === p.id && x.activo !== false));
    return sin ? t("ctl_falta").replace("{que}", sin.nombre) : null;
  },
  profesionalismo: (d) => (Object.values(d.pesos).some(p => p && !p.configurado)
    ? t("ctl_de_ejemplo") : null),
};

const PINTA = {
  "dias-festivos": festivos, hospitales, hoteles, plazas: ciudades,
  "parametros-combustible": combustible, "categorias-vehiculo": categorias,
  paises, "tabulador-viaticos": tabulador, modalidades,
  "requisitos-freelance": requisitos, profesionalismo: pesos,
};

async function pestanaCatalogos(zona) {
  let d = await traer();
  let elegido = "dias-festivos";
  const izquierda = h("div", { clase: "tarjeta lisa ctl-lista" });
  const derecha = h("div");

  const recargar = async () => { d = await traer(); pintar(); };

  function renglon(clave) {
    const falta = FALTA[clave] ? FALTA[clave](d) : null;
    const cerrado = !puede(clave);
    return h("div", {
      clase: clave === elegido ? "ctl-item sel" : "ctl-item",
      role: "button", tabindex: "0",
      onclick: () => { elegido = clave; pintar(); },
      onkeydown: (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); elegido = clave; pintar(); }
      },
    },
      h("div", {},
        h("b", {}, cerrado ? h("span", { clase: "ctl-candado", html: CANDADO }) : null,
          t(TITULO[clave])),
        h("div", { clase: "chico gris" }, RESUMEN[clave](d))),
      falta ? h("div", {}, etiqueta(falta, "alerta")) : null);
  }

  function pintar() {
    const suyas = new Set(menuDe(sesion.usuario).map(x => x.clave));
    izquierda.replaceChildren(
      h("h4", { clase: "ctl-grupo" }, t("ctl_grupo_sistema")),
      ...DE_SISTEMA.map(renglon),
      h("h4", { clase: "ctl-grupo otro" }, t("ctl_grupo_dinero")),
      h("p", { clase: "chico gris ctl-nota" }, t("ctl_grupo_dinero_pie")),
      ...DE_DINERO.map(renglon),
      h("h4", { clase: "ctl-grupo otro" }, t("ctl_grupo_pantalla")),
      ...CON_PANTALLA.map(x => h("div", { clase: "ctl-enlace" },
        h("span", {}, t(x.texto)),
        suyas.has(x.clave)
          ? h("a", { href: `#/${x.clave}` }, t("ctl_ir_a").replace("{donde}", t(x.donde)))
          : h("span", { clase: "gris" }, t(x.donde)))));
    derecha.replaceChildren();
    PINTA[elegido](derecha, d, recargar);
  }

  zona.replaceChildren(...[h("div", { clase: "ctl-marco" }, izquierda, derecha)].filter(Boolean));
  pintar();
}

/* ============================================================ piezas */

/* El pie de cada catalogo: quien lo lleva, si no es quien mira. */
function quienLoLleva(clave) {
  if (puede(clave)) return null;
  return h("p", { clase: "aviso ctl-quien" },
    t(DE_DINERO.includes(clave) ? "ctl_lo_fija_dinero" : "ctl_lo_lleva_sistema"));
}

function tabla(cabezas, filas, vacio = "ctl_vacio") {
  return h("table", { clase: "lista ctl-tabla" },
    h("thead", {}, h("tr", {}, ...cabezas.map(c => h("th", {}, c)))),
    h("tbody", {}, ...(filas.length ? filas
      : [h("tr", {}, h("td", { colspan: String(cabezas.length), clase: "gris chico" }, t(vacio)))])));
}

function boton(texto, alPicar, clase = "claro chico") {
  return h("button", { type: "button", clase, onclick: alPicar }, texto);
}

/* Quitar pregunta antes: lo quitado sale de las listas donde se escoge. */
function quitar(ruta, nombre, recargar) {
  return boton(t("ctl_quitar"), async (e) => {
    if (!confirm(t("ctl_quitar_seguro").replace("{que}", nombre))) return;
    e.target.disabled = true;
    try {
      await api.borrar(ruta);
      mensaje(t("ctl_quitado").replace("{que}", nombre));
      await recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  });
}

/* Lo quitado vuelve con un clic; lo que ya lo usaba nunca se fue. */
function reactivar(ruta, nombre, recargar) {
  return boton(t("ctl_reactivar"), async (e) => {
    e.target.disabled = true;
    try {
      await api.post(`${ruta}/reactivar`);
      mensaje(t("ctl_reactivado").replace("{que}", nombre));
      await recargar();
    } catch (err) {
      mensaje(err.message, "grave");
      e.target.disabled = false;
    }
  });
}

/* El boton que le toca al renglon: quitar al vivo, reactivar al quitado. */
function quitarOReactivar(x, ruta, nombre, recargar) {
  return x.activo === false ? reactivar(ruta, nombre, recargar)
    : quitar(ruta, nombre, recargar);
}
const filaDe = (x) => ({ clase: x.activo === false ? "apagado" : "" });

/* Un formulario chico: los campos que se le digan y sus dos botones.
   `campos`: [{k, texto, tipo, opciones, valor, requerido, entero, crudo}].
   Si guardar truena, el mensaje sale y el formulario se queda como
   estaba: lo escrito no se pierde. */
function formulario(campos, alGuardar, alCancelar, textoGuardar = t("ctl_guardar")) {
  const controles = {};
  const cajas = campos.map((c) => {
    let control;
    const valor = c.valor === null || c.valor === undefined ? "" : String(c.valor);
    if (c.tipo === "lista") {
      control = lista(c.k, c.opciones);
      control.value = valor;
    } else if (c.tipo === "si_no") {
      control = h("input", { type: "checkbox", name: c.k, clase: "ctl-casilla" });
      control.checked = !!c.valor;
    } else {
      control = entrada(c.k, {
        type: c.tipo === "numero" ? "number" : c.tipo === "fecha" ? "date" : "text",
        step: c.tipo === "numero" ? "any" : null,
        "data-crudo": c.crudo ? "" : null,
        autocomplete: "off",
      });
      control.value = valor;
    }
    controles[c.k] = control;
    // El asterisco sale del mismo `requerido` que ya frenaba el guardado
    // (seccion 106): lo obligatorio se ve antes de intentar.
    const caja = campo(c.texto, control, { obligatorio: !!c.requerido });
    /* Una frase de ayuda debajo del control, cuando el nombre solo no
       alcanza (seccion 105: el intervalo de descanso). */
    if (c.ayuda) caja.append(h("div", { clase: "gris chico" }, c.ayuda));
    return caja;
  });

  const guardar = boton(textoGuardar, async () => {
    const valores = {};
    for (const c of campos) {
      const control = controles[c.k];
      let v;
      if (c.tipo === "si_no") v = control.checked;
      else if (c.tipo === "numero") v = control.value === "" ? null : Number(control.value);
      else if (c.tipo === "lista" && c.entero) v = control.value === "" ? null : Number(control.value);
      else v = control.value.trim() === "" ? null : control.value.trim();
      if (c.requerido && (v === null || v === "" || Number.isNaN(v))) {
        mensaje(t("ctl_falta_campo").replace("{campo}", c.texto), "alerta");
        control.focus();
        return;
      }
      valores[c.k] = v;
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
    h("div", { clase: "acciones" }, guardar,
      boton(t("ctl_cancelar"), () => alCancelar())));
  nodo.controles = controles;
  return nodo;
}

/* Lo de un registro que el servidor pide completo: el PATCH valida con
   el mismo esquema que el alta. Se manda todo, con lo cambiado encima. */
function completo(fila, campos, cambios) {
  const salida = {};
  for (const k of campos) salida[k] = fila[k] === undefined ? null : fila[k];
  return { ...salida, ...cambios };
}

/* Lo ultimo que le paso a este catalogo, de la bitacora. */
function historial(clave) {
  const caja = h("div", { clase: "ctl-historial" }, h("div", { clase: "gris chico" }, "…"));
  api.get(`/bitacora-admin/catalogo/${clave}?idioma=${idioma()}`).then((r) => {
    if (!r.filas.length) {
      return caja.replaceChildren(h("p", { clase: "chico gris" }, t("ctl_hist_nadie")));
    }
    caja.replaceChildren(
      ...r.filas.map(x => h("div", { clase: "ctl-hist-renglon chico" },
        h("span", { clase: "gris num" }, `${fecha(x.cuando)} ${hora(x.cuando)}`),
        h("b", {}, x.quien || "—"),
        h("span", {}, x.que))),
      ...(r.total > r.filas.length
        ? [h("p", { clase: "chico gris" }, t("ctl_hist_mas").replace("{n}", r.total - r.filas.length))]
        : []));
  }).catch((err) => caja.replaceChildren(h("p", { clase: "chico gris" }, err.message)));
  return h("div", {}, h("h4", { clase: "grupo" }, t("ctl_historial")), caja);
}

/* El pais que se esta mirando: botones, como en la maqueta. */
function botonesDePais(d, actual, alCambiar) {
  return h("div", { clase: "acciones ctl-paises" },
    ...d.paises.map(p => h("button", {
      type: "button", clase: p.id === actual ? "pestana activa" : "pestana",
      onclick: () => { paisVisto = p.id; alCambiar(p.id); },
    }, p.nombre)));
}

/* ============================================================ festivos */

function festivos(caja, d, recargar) {
  const clave = "dias-festivos";
  let paisId = paisInicial(d);
  let anio = ANIO();
  const zona = h("div");
  const forma = h("div");

  function pintar() {
    const anios = [...new Set([anio, ANIO() - 1, ANIO(), ANIO() + 1,
      ...d.festivos.map(f => Number(f.fecha.slice(0, 4)))])].sort();
    const selAnio = lista("anio", anios.map(a => ({ valor: String(a), texto: String(a) })),
                          { style: "width:auto" });
    selAnio.value = String(anio);
    selAnio.addEventListener("change", () => { anio = Number(selAnio.value); pintar(); });

    const esDelAnio = (f) => f.pais_id === paisId && f.fecha.startsWith(String(anio));
    const del = [...d.festivos.filter(esDelAnio),
                 ...apagadosDe(d, "festivos", esDelAnio)]
      .sort((a, b) => a.fecha.localeCompare(b.fecha));
    const factor = (f) => (Number(f.factor_comision) === 2 ? t("ctl_al_doble")
      : t("ctl_por_factor").replace("{n}", numero(f.factor_comision)));
    zona.replaceChildren(...[
      h("div", { clase: "acciones", style: "margin:0 0 10px" },
        botonesDePais(d, paisId, (id) => { paisId = id; pintar(); }), selAnio),
      tabla([t("ctl_fecha"), t("ctl_nombre"), t("ctl_comision_dia"), ""],
        del.map(f => h("tr", filaDe(f),
          h("td", { clase: "num" }, fecha(f.fecha)), h("td", {}, f.nombre),
          h("td", { clase: "chico" }, factor(f)),
          h("td", { style: "text-align:right" },
            puede(clave) ? quitarOReactivar(f, `/catalogos/dias-festivos/${f.id}`, f.nombre, recargar) : null)))),
      puede(clave) ? h("div", { clase: "acciones", style: "margin-top:10px" },
        boton(t("ctl_agregar_festivo"), () => abrirAlta())) : null].filter(Boolean));
  }

  function abrirAlta() {
    forma.replaceChildren(formulario([
      { k: "fecha", texto: t("ctl_fecha"), tipo: "fecha", requerido: true },
      { k: "nombre", texto: t("ctl_nombre"), requerido: true },
      { k: "factor_comision", texto: t("ctl_factor"), tipo: "numero", valor: 2, requerido: true },
    ], async (v) => {
      await api.post("/catalogos/dias-festivos", { pais_id: paisId, ...v });
      mensaje(t("ctl_agregado").replace("{que}", v.nombre));
      await recargar();
    }, () => forma.replaceChildren(), t("ctl_agregar")));
  }

  caja.append(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctl_festivos"), "ay_ctl_festivos"),
    h("p", { clase: "gris chico ctl-pie" }, t("ctl_festivos_pie")),
    ...[quienLoLleva(clave)].filter(Boolean), zona, forma, historial(clave)));
  pintar();
}

/* ============================================= hospitales y hoteles */

/* Los dos son lugares: nombre, ciudad, direccion y su punto. El hospital
   lleva ademas su nivel --de ahi sale la regla del quirofano en la hoja
   del servicio-- y su punto es obligatorio: sin el no se sabe cual es
   el mas cercano. */
function lugares(cuerpo, d, recargar, tipo) {
  const clave = tipo;
  const esHospital = tipo === "hospitales";
  const todos = esHospital ? d.hospitales : d.hoteles;
  let paisId = paisInicial(d);
  let ciudadId = "";
  const zona = h("div");
  const forma = h("div");
  const CAMPOS = esHospital
    ? ["pais_id", "nombre", "lat", "lon", "plaza_id", "direccion", "telefono", "nivel_atencion"]
    : ["pais_id", "nombre", "plaza_id", "direccion", "telefono", "lat", "lon"];

  function pintar() {
    const selCiudad = lista("ciudad", opcionesCiudad(d, paisId, t("ctl_todas_ciudades")));
    selCiudad.value = ciudadId;
    selCiudad.addEventListener("change", () => { ciudadId = selCiudad.value; pintar(); });
    const aqui = (x) => x.pais_id === paisId && (!ciudadId || x.plaza_id === Number(ciudadId));
    const filas = [...todos.filter(aqui), ...apagadosDe(d, tipo, aqui)]
      .sort((a, b) => (nombreCiudad(d, a.plaza_id) + a.nombre)
        .localeCompare(nombreCiudad(d, b.plaza_id) + b.nombre));
    const cabezas = [t("ctl_nombre"), t("ctl_ciudad"),
      ...(esHospital ? [t("imp_hosp_nivel")] : []), t("ctl_telefono"), t("ctl_ubicacion"), ""];
    zona.replaceChildren(...[
      h("div", { clase: "acciones", style: "margin:0 0 10px" },
        botonesDePais(d, paisId, (id) => { paisId = id; ciudadId = ""; pintar(); }),
        h("div", { style: "min-width:200px" }, selCiudad)),
      tabla(cabezas, filas.map(x => h("tr", filaDe(x),
        h("td", {}, h("b", {}, x.nombre),
          x.direccion ? h("div", { clase: "chico gris" }, x.direccion) : null),
        h("td", {}, nombreCiudad(d, x.plaza_id)),
        esHospital ? h("td", { clase: "chico" }, nivelTexto(x.nivel_atencion)) : null,
        h("td", { clase: "chico" }, x.telefono || "—"),
        h("td", {}, x.lat === null || x.lat === undefined
          ? etiqueta(t("ctl_sin_ubicacion"), "alerta")
          : h("span", { clase: "chico gris num" }, `${Number(x.lat).toFixed(4)}, ${Number(x.lon).toFixed(4)}`)),
        h("td", { style: "text-align:right;white-space:nowrap" },
          puede(clave) && x.activo !== false ? boton(t("ctl_editar"), () => abrir(x)) : null,
          puede(clave) ? quitarOReactivar(x, `/catalogos/${tipo}/${x.id}`, x.nombre, recargar) : null)))),
      puede(clave) ? h("div", { clase: "acciones", style: "margin-top:10px" },
        boton(t(esHospital ? "ctl_agregar_hospital" : "ctl_agregar_hotel"), () => abrir(null))) : null].filter(Boolean));
  }

  function abrir(x) {
    const campos = [
      { k: "nombre", texto: t("ctl_nombre"), valor: x && x.nombre, requerido: true, crudo: true },
      { k: "plaza_id", texto: t("ctl_ciudad"), tipo: "lista", entero: true,
        opciones: opcionesCiudad(d, x ? x.pais_id : paisId, "—"),
        valor: x ? x.plaza_id : (ciudadId || "") },
      ...(esHospital ? [{ k: "nivel_atencion", texto: t("imp_hosp_nivel"), tipo: "lista",
                          opciones: NIVELES(), valor: x && x.nivel_atencion }] : []),
      { k: "direccion", texto: t("ctl_direccion"), valor: x && x.direccion, crudo: true },
      { k: "telefono", texto: t("ctl_telefono"), valor: x && x.telefono, crudo: true },
      { k: "lat", texto: t("ctl_latitud"), tipo: "numero", valor: x && x.lat, requerido: esHospital },
      { k: "lon", texto: t("ctl_longitud"), tipo: "numero", valor: x && x.lon, requerido: esHospital },
    ];
    const nodo = formulario(campos, async (v) => {
      if ((v.lat === null) !== (v.lon === null)) {
        throw new Error(t("ctl_punto_completo"));
      }
      if (x) {
        await api.patch(`/catalogos/${tipo}/${x.id}`, completo(x, CAMPOS, v));
        mensaje(t("ctl_guardado").replace("{que}", v.nombre));
      } else {
        await api.post(`/catalogos/${tipo}`, { pais_id: paisId, ...v });
        mensaje(t("ctl_agregado").replace("{que}", v.nombre));
      }
      await recargar();
    }, () => forma.replaceChildren());
    forma.replaceChildren(...[
      tiene(sesion.usuario, "mapas.buscar") ? buscadorGoogle(x ? x.pais_id : paisId, nodo) : null,
      nodo,
    ].filter(Boolean));
    nodo.controles.nombre.focus();
  }

  cuerpo.append(h("div", { clase: "tarjeta" },
    esHospital ? conAyuda("h3", t("ctl_hospitales"), "ay_ctl_hospitales")
               : conAyuda("h3", t("ctl_hoteles"), "ay_ctl_hoteles"),
    h("p", { clase: "gris chico ctl-pie" }, t(esHospital ? "ctl_hospitales_pie" : "ctl_hoteles_pie")),
    ...[quienLoLleva(clave)].filter(Boolean), zona, forma, historial(clave)));
  pintar();
}

function nivelTexto(nivel) {
  const x = NIVELES().find(n => n.valor === nivel);
  return x && nivel ? x.texto : "—";
}

/* Buscar el lugar en Google y traerse su nombre, su direccion y su
   punto. Se busca al picar, no mientras se escribe: cada busqueda se
   cobra. */
function buscadorGoogle(paisId, forma) {
  const texto = entrada("buscar_google", { placeholder: t("ctl_google_ayuda"),
                                            autocomplete: "off", "data-crudo": "" });
  const hallados = h("div");
  const buscar = boton(t("ctl_google_buscar"), async () => {
    if (texto.value.trim().length < 3) return;
    buscar.disabled = true;
    try {
      const r = await api.get(`/mapas/lugares?texto=${encodeURIComponent(texto.value.trim())}&pais_id=${paisId}`);
      hallados.replaceChildren(...(r.lugares.length ? r.lugares.map(l => h("div", { clase: "ctl-hallado" },
        h("div", {}, h("b", {}, l.nombre || "—"), h("div", { clase: "chico gris" }, l.direccion || "")),
        boton(t("ctl_google_usar"), () => {
          const c = forma.controles;
          if (l.nombre) c.nombre.value = l.nombre;
          if (l.direccion) c.direccion.value = l.direccion;
          c.lat.value = l.lat;
          c.lon.value = l.lon;
          hallados.replaceChildren();
        }))) : [h("p", { clase: "chico gris" }, t("ctl_google_nada"))]));
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

function hospitales(caja, d, recargar) { lugares(caja, d, recargar, "hospitales"); }
function hoteles(caja, d, recargar) { lugares(caja, d, recargar, "hoteles"); }

/* ============================================================ ciudades */

function ciudades(caja, d, recargar) {
  const clave = "plazas";
  let paisId = paisInicial(d);
  const zona = h("div");
  const forma = h("div");

  function pintar() {
    const delPais = (x) => x.pais_id === paisId;
    const filas = [...d.plazas.filter(delPais), ...apagadosDe(d, "plazas", delPais)]
      .sort((a, b) => a.nombre.localeCompare(b.nombre));
    zona.replaceChildren(...[
      h("div", { clase: "acciones", style: "margin:0 0 10px" },
        botonesDePais(d, paisId, (id) => { paisId = id; pintar(); })),
      tabla([t("ctl_ciudad"), t("ctl_personal_propio"), ""], filas.map(x => h("tr", filaDe(x),
        h("td", {}, h("b", {}, x.nombre), x.fija ? " " : null,
          x.fija ? etiqueta(t("ctl_fija"), "ok") : null),
        h("td", {}, siNo(x.tiene_recurso_local)),
        h("td", { style: "text-align:right;white-space:nowrap" },
          puede(clave) && x.activo !== false ? boton(t("ctl_editar"), () => abrir(x)) : null,
          puede(clave) && !x.fija ? quitarOReactivar(x, `/catalogos/plazas/${x.id}`, x.nombre, recargar) : null)))),
      puede(clave) ? h("div", { clase: "acciones", style: "margin-top:10px" },
        boton(t("ctl_agregar_ciudad"), () => abrir(null))) : null].filter(Boolean));
  }

  function abrir(x) {
    forma.replaceChildren(formulario([
      { k: "nombre", texto: t("ctl_ciudad"), valor: x && x.nombre, requerido: true },
      { k: "tiene_recurso_local", texto: t("ctl_personal_propio"), tipo: "si_no",
        valor: x ? x.tiene_recurso_local : false },
    ], async (v) => {
      if (x) {
        await api.patch(`/catalogos/plazas/${x.id}`,
          completo(x, ["pais_id", "nombre", "tiene_recurso_local"], v));
        mensaje(t("ctl_guardado").replace("{que}", v.nombre));
      } else {
        await api.post("/catalogos/plazas", { pais_id: paisId, ...v });
        mensaje(t("ctl_agregado").replace("{que}", v.nombre));
      }
      await recargar();
    }, () => forma.replaceChildren()));
  }

  caja.append(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctl_ciudades"), "ay_ctl_ciudades"),
    h("p", { clase: "gris chico ctl-pie" }, t("ctl_ciudades_pie")),
    ...[quienLoLleva(clave)].filter(Boolean), zona, forma, historial(clave)));
  pintar();
}

/* ============================================================ combustible */

function combustible(caja, d, recargar) {
  const clave = "parametros-combustible";
  let paisId = paisInicial(d);
  const zona = h("div");
  const forma = h("div");
  const CAMPOS = ["pais_id", "precio_litro", "holgura_pct", "vigencia_desde"];

  function pintar() {
    const moneda = monedaDe(d, paisId);
    const vigente = vigenteDe(d, paisId);
    const delPais = (x) => x.pais_id === paisId;
    const filas = [...d.combustible.filter(delPais), ...apagadosDe(d, "combustible", delPais)]
      .sort((a, b) => b.vigencia_desde.localeCompare(a.vigencia_desde));
    zona.replaceChildren(...[
      h("div", { clase: "acciones", style: "margin:0 0 10px" },
        botonesDePais(d, paisId, (id) => { paisId = id; pintar(); })),
      tabla([t("ctl_vigente_desde"), t("ctl_precio_litro"), t("ctl_holgura"), ""],
        filas.map(x => h("tr", filaDe(x),
          h("td", { clase: "num" }, fecha(x.vigencia_desde), " ",
            vigente && vigente.id === x.id ? etiqueta(t("ctl_vigente"), "ok") : null),
          h("td", { clase: "num" }, dinero(x.precio_litro, moneda)),
          h("td", { clase: "num" }, `${numero(x.holgura_pct)} %`),
          h("td", { style: "text-align:right;white-space:nowrap" },
            puede(clave) && x.activo !== false ? boton(t("ctl_editar"), () => abrir(x)) : null,
            puede(clave) ? quitarOReactivar(x, `/catalogos/parametros-combustible/${x.id}`,
                                            fecha(x.vigencia_desde), recargar) : null)))),
      puede(clave) ? h("div", { clase: "acciones", style: "margin-top:10px" },
        boton(t("ctl_agregar_precio"), () => abrir(null))) : null].filter(Boolean));
  }

  function abrir(x) {
    forma.replaceChildren(formulario([
      { k: "vigencia_desde", texto: t("ctl_vigente_desde"), tipo: "fecha",
        valor: x ? x.vigencia_desde : HOY(), requerido: true },
      { k: "precio_litro", texto: t("ctl_precio_litro"), tipo: "numero",
        valor: x && x.precio_litro, requerido: true },
      { k: "holgura_pct", texto: t("ctl_holgura"), tipo: "numero",
        valor: x ? x.holgura_pct : 20, requerido: true },
    ], async (v) => {
      if (x) await api.patch(`/catalogos/parametros-combustible/${x.id}`, completo(x, CAMPOS, v));
      else await api.post("/catalogos/parametros-combustible", { pais_id: paisId, ...v });
      mensaje(t("ctl_guardado").replace("{que}", t("ctl_combustible")));
      await recargar();
    }, () => forma.replaceChildren()));
  }

  caja.append(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctl_combustible"), "ay_ctl_combustible"),
    h("p", { clase: "gris chico ctl-pie" }, t("ctl_combustible_pie")),
    ...[quienLoLleva(clave)].filter(Boolean), zona, forma, historial(clave)));
  pintar();
}

/* ============================================= unidades por categoria */

function categorias(caja, d, recargar) {
  const clave = "categorias-vehiculo";
  const zona = h("div");
  const forma = h("div");
  const CAMPOS = ["codigo", "nombre", "blindado", "rendimiento_km_litro"];

  function pintar() {
    const filas = [...d.categorias].sort((a, b) => a.nombre.localeCompare(b.nombre));
    zona.replaceChildren(...[
      tabla([t("ctl_categoria"), t("ctl_blindada"), t("ctl_rendimiento"), t("ctl_fotos"), ""],
        filas.map(x => h("tr", {},
          h("td", {}, h("b", {}, x.nombre), h("div", { clase: "chico gris" }, x.codigo)),
          h("td", {}, siNo(x.blindado)),
          h("td", { clase: "num" }, `${numero(x.rendimiento_km_litro)} km/l`),
          h("td", {}, (x.fotos || []).length
            ? h("span", { clase: "chico" }, t("ctl_fotos_n").replace("{n}", x.fotos.length))
            : etiqueta(t("ctl_sin_foto"), "alerta")),
          h("td", { style: "text-align:right;white-space:nowrap" },
            boton(t("ctl_ver_fotos"), () => abrirFotos(x)),
            puede(clave) ? boton(t("ctl_editar"), () => abrir(x)) : null)))),
      puede(clave) ? h("div", { clase: "acciones", style: "margin-top:10px" },
        boton(t("ctl_agregar_categoria"), () => abrir(null))) : null].filter(Boolean));
  }

  function abrir(x) {
    forma.replaceChildren(formulario([
      ...(x ? [] : [{ k: "codigo", texto: t("ctl_codigo"), requerido: true, crudo: true }]),
      { k: "nombre", texto: t("ctl_nombre"), valor: x && x.nombre, requerido: true, crudo: true },
      { k: "blindado", texto: t("ctl_blindada"), tipo: "si_no", valor: x ? x.blindado : false },
      { k: "rendimiento_km_litro", texto: t("ctl_rendimiento"), tipo: "numero",
        valor: x && x.rendimiento_km_litro, requerido: true },
    ], async (v) => {
      if (x) await api.patch(`/catalogos/categorias-vehiculo/${x.id}`, completo(x, CAMPOS, v));
      else await api.post("/catalogos/categorias-vehiculo", v);
      mensaje(t("ctl_guardado").replace("{que}", v.nombre));
      await recargar();
    }, () => forma.replaceChildren()));
  }

  /* La unidad no lleva su foto real: lleva la de su categoria en su color
     (decision de Salvador, 23 sep). La base es la que se ensena cuando su
     color todavia no tiene la suya. */
  function abrirFotos(x) {
    const colores = ["", ...new Set([...(d.colores[String(x.id)] || []),
                                     ...(x.fotos || []).filter(Boolean)])];
    forma.replaceChildren(h("div", { clase: "ctl-forma" },
      h("h4", {}, t("ctl_fotos_de").replace("{que}", x.nombre)),
      h("div", { clase: "ctl-fotos" }, ...colores.map(color => fotoDeColor(x, color))),
      h("div", { clase: "acciones", style: "margin-top:10px" },
        boton(t("ctl_cerrar"), () => forma.replaceChildren()))));
  }

  function fotoDeColor(x, color) {
    const tiene_ = (x.fotos || []).includes(color);
    const marco = h("div", { clase: "ctl-foto-marco" }, h("span", { clase: "chico gris" }, "…"));
    if (tiene_) {
      api.get(`/catalogos/categorias-vehiculo/${x.id}/foto?color=${encodeURIComponent(color)}`)
        .then(r => marco.replaceChildren(h("img", { src: r.foto, alt: x.nombre })))
        .catch(() => marco.replaceChildren(h("span", { clase: "chico gris" }, "—")));
    } else {
      marco.replaceChildren(h("span", { clase: "chico gris" }, t("ctl_sin_foto")));
    }
    const archivo = h("input", { type: "file", accept: "image/*", hidden: "hidden" });
    archivo.addEventListener("change", async () => {
      if (!archivo.files.length) return;
      try {
        const reducida = await reducirImagen(archivo.files[0]);
        await api.formulario(
          `/catalogos/categorias-vehiculo/${x.id}/foto?color=${encodeURIComponent(color)}`,
          { archivo: reducida }, "PUT");
        mensaje(t("ctl_foto_puesta"));
        await recargar();
      } catch (err) {
        mensaje(err.message, "grave");
      }
    });
    return h("div", { clase: "ctl-foto" },
      marco,
      h("div", { clase: "chico" }, h("b", {}, color || t("ctl_foto_base"))),
      puede(clave) ? h("div", { clase: "acciones" },
        boton(t(tiene_ ? "ctl_foto_cambiar" : "ctl_foto_subir"), () => archivo.click()),
        tiene_ ? boton(t("ctl_quitar"), async () => {
          if (!confirm(t("ctl_quitar_seguro").replace("{que}", color || t("ctl_foto_base")))) return;
          try {
            await api.borrar(`/catalogos/categorias-vehiculo/${x.id}/foto?color=${encodeURIComponent(color)}`);
            await recargar();
          } catch (err) {
            mensaje(err.message, "grave");
          }
        }) : null, archivo) : null);
  }

  caja.append(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctl_categorias"), "ay_ctl_categorias"),
    h("p", { clase: "gris chico ctl-pie" }, t("ctl_categorias_pie")),
    ...[quienLoLleva(clave)].filter(Boolean), zona, forma, historial(clave)));
  pintar();
}

/* ============================================ perfiles y paises */

function paises(caja, d, recargar) {
  const clave = "paises";
  const zona = h("div");
  const forma = h("div");
  const CAMPOS = ["codigo", "nombre", "moneda_local", "lada", "anticipacion_aeropuerto_min",
                  "anticipacion_min", "zona_horaria", "idioma"];

  function pintar() {
    zona.replaceChildren(...[
      tabla([t("ctl_pais"), t("ctl_moneda"), t("ctl_lada"), t("ctl_anticipacion"),
             t("ctl_zona"), t("ctl_idioma_app"), ""],
        d.paises.map(x => h("tr", {},
          h("td", {}, h("b", {}, x.nombre), h("div", { clase: "chico gris" }, x.codigo)),
          h("td", {}, x.moneda_local),
          h("td", { clase: "num" }, x.lada || "—"),
          h("td", { clase: "chico" }, t("ctl_anticipacion_valor")
            .replace("{a}", x.anticipacion_aeropuerto_min).replace("{o}", x.anticipacion_min)),
          h("td", { clase: "chico" }, x.zona_horaria),
          h("td", {}, t((IDIOMAS_APP.find(i => i[0] === x.idioma) || [null, "ctl_idioma_es"])[1])),
          h("td", { style: "text-align:right" },
            puede(clave) ? boton(t("ctl_editar"), () => abrirPais(x)) : null)))),
      puede(clave) ? h("div", { clase: "acciones", style: "margin:10px 0 0" },
        boton(t("ctl_agregar_pais"), () => abrirPais(null))) : null,
      h("h4", { clase: "grupo" }, t("ctl_perfiles")),
      tabla([t("ctl_codigo"), t("ctl_nombre"), ""], d.perfiles.map(x => h("tr", {},
        h("td", { clase: "chico gris" }, x.codigo), h("td", {}, x.nombre),
        h("td", { style: "text-align:right" },
          puede(clave) ? boton(t("ctl_editar"), () => abrirPerfil(x)) : null))))].filter(Boolean));
  }

  function abrirPais(x) {
    forma.replaceChildren(formulario([
      ...(x ? [] : [
        { k: "codigo", texto: t("ctl_codigo_pais"), requerido: true, crudo: true },
        { k: "moneda_local", texto: t("ctl_moneda"), tipo: "lista", requerido: true,
          opciones: MONEDAS.map(mo => ({ valor: mo, texto: mo })), valor: "MXN" }]),
      { k: "nombre", texto: t("ctl_nombre"), valor: x && x.nombre, requerido: true },
      { k: "lada", texto: t("ctl_lada"), valor: x && x.lada, crudo: true },
      { k: "anticipacion_aeropuerto_min", texto: t("ctl_anticipacion_aeropuerto"), tipo: "numero",
        valor: x ? x.anticipacion_aeropuerto_min : 45, requerido: true },
      { k: "anticipacion_min", texto: t("ctl_anticipacion_otro"), tipo: "numero",
        valor: x ? x.anticipacion_min : 30, requerido: true },
      { k: "zona_horaria", texto: t("ctl_zona"), valor: x ? x.zona_horaria : "America/Mexico_City",
        requerido: true, crudo: true },
      { k: "idioma", texto: t("ctl_idioma_app"), tipo: "lista", requerido: true,
        opciones: IDIOMAS_APP.map(([v, k]) => ({ valor: v, texto: t(k) })), valor: x ? x.idioma : "es" },
    ], async (v) => {
      v.lada = v.lada || "";
      if (x) await api.patch(`/catalogos/paises/${x.id}`, completo(x, CAMPOS, v));
      else await api.post("/catalogos/paises", v);
      mensaje(t("ctl_guardado").replace("{que}", v.nombre));
      await recargar();
    }, () => forma.replaceChildren()));
  }

  function abrirPerfil(x) {
    forma.replaceChildren(formulario([
      { k: "nombre", texto: t("ctl_nombre"), valor: x.nombre, requerido: true },
    ], async (v) => {
      await api.patch(`/catalogos/perfiles/${x.id}`, completo(x, ["codigo", "nombre"], v));
      mensaje(t("ctl_guardado").replace("{que}", v.nombre));
      await recargar();
    }, () => forma.replaceChildren()));
  }

  caja.append(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctl_paises"), "ay_ctl_paises"),
    h("p", { clase: "gris chico ctl-pie" }, t("ctl_paises_pie")),
    ...[quienLoLleva(clave)].filter(Boolean), zona, forma, historial(clave)));
  pintar();
}

/* ============================================ tabulador de viaticos */

function tabulador(caja, d, recargar) {
  const clave = "tabulador-viaticos";
  let paisId = paisInicial(d);
  let tipo = "eventual";
  const zona = h("div");
  const forma = h("div");
  const CAMPOS = ["pais_id", "tipo_servicio", "concepto", "escenario", "monto", "monto_abierto"];

  function pintar() {
    const moneda = monedaDe(d, paisId);
    const selTipo = lista("tipo", [{ valor: "eventual", texto: t("ctl_eventual") },
                                   { valor: "implantado", texto: t("ctl_implantado") }]);
    selTipo.value = tipo;
    selTipo.addEventListener("change", () => { tipo = selTipo.value; pintar(); });
    const celda = (concepto, escenario) => {
      const x = d.tabulador.find(r => r.pais_id === paisId && r.tipo_servicio === tipo
        && r.concepto === concepto && r.escenario === escenario);
      const texto = x ? [dinero(x.monto, moneda),
        x.monto_abierto ? h("div", { clase: "chico gris" }, t("imp_tab_abierto")) : null] : ["—"];
      return h("td", {
        clase: puede(clave) ? "num ctl-celda" : "num",
        title: puede(clave) ? t("ctl_tab_cambiar") : null,
        onclick: puede(clave) ? () => abrir(concepto, escenario, x) : null,
      }, ...texto);
    };
    const escenarios = ESCENARIOS_DE(tipo);
    zona.replaceChildren(...[
      h("div", { clase: "acciones", style: "margin:0 0 10px" },
        botonesDePais(d, paisId, (id) => { paisId = id; pintar(); }),
        h("div", { style: "min-width:160px" }, selTipo)),
      tabla([t("ctl_concepto"), ...escenarios.map(([, k]) => t(k))],
        CONCEPTOS.map(([concepto, k]) => h("tr", {},
          h("td", {}, h("b", {}, t(k))),
          ...escenarios.map(([escenario]) => celda(concepto, escenario))))),
      tipo === "implantado"
        ? h("p", { clase: "chico gris", style: "margin:8px 0 0" }, t("ctl_tab_implantado_pie"))
        : null].filter(Boolean));
    /* Al cambiar de tabla se cierra lo que estaba abierto: un monto de
       medio dia del eventual no se guarda en la del implantado. */
    forma.replaceChildren();
  }

  function abrir(concepto, escenario, x) {
    const titulo = `${t((CONCEPTOS.find(c => c[0] === concepto) || [])[1])} · ${
      t((ESCENARIOS.find(e => e[0] === escenario) || [])[1])}`;
    forma.replaceChildren(
      h("h4", { style: "margin-top:12px" }, titulo),
      formulario([
        { k: "monto", texto: t("ctl_monto"), tipo: "numero", valor: x ? x.monto : "", requerido: true },
        { k: "monto_abierto", texto: t("imp_tab_abierto"), tipo: "si_no", valor: x ? x.monto_abierto : false },
      ], async (v) => {
        if (x) {
          await api.patch(`/catalogos/tabulador-viaticos/${x.id}`, completo(x, CAMPOS, v));
        } else {
          await api.post("/catalogos/tabulador-viaticos", {
            pais_id: paisId, tipo_servicio: tipo, concepto, escenario, ...v });
        }
        mensaje(t("ctl_guardado").replace("{que}", titulo));
        await recargar();
      }, () => forma.replaceChildren()));
  }

  caja.append(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctl_tabulador"), "ay_ctl_tabulador"),
    h("p", { clase: "gris chico ctl-pie" }, t("ctl_tabulador_pie")),
    ...[quienLoLleva(clave)].filter(Boolean), zona, forma, historial(clave)));
  pintar();
}

/* ============================================ horas de cada modalidad */

function modalidades(caja, d, recargar) {
  const clave = "modalidades";
  let paisId = paisInicial(d);
  const zona = h("div");
  const forma = h("div");
  const CAMPOS = ["pais_id", "codigo", "horas", "horas_descanso", "intervalo_descanso",
                  "aplica_horas_extra", "bloquea_dia_completo", "km_estimados"];

  function pintar() {
    const filas = MODALIDADES.map(([codigo, k]) => [codigo, k,
      d.modalidades.find(x => x.pais_id === paisId && x.codigo === codigo)]);
    zona.replaceChildren(...[
      h("div", { clase: "acciones", style: "margin:0 0 10px" },
        botonesDePais(d, paisId, (id) => { paisId = id; pintar(); })),
      tabla([t("ctl_modalidad"), t("ctl_horas"), t("ctl_descanso"),
             h("span", { title: t("cat_intervalo_descanso_ayuda") }, t("cat_intervalo_descanso")),
             t("ctl_horas_extra"), t("ctl_bloquea"), t("ctl_km"), ""],
        filas.map(([codigo, k, x]) => h("tr", {},
          h("td", {}, h("b", {}, t(k))),
          ...(x ? [
            h("td", { clase: "num" }, `${numero(x.horas)} h`),
            h("td", { clase: "num" }, `${numero(x.horas_descanso)} h`),
            h("td", { clase: "num" }, `${numero(x.intervalo_descanso)} h`),
            h("td", {}, siNo(x.aplica_horas_extra)),
            h("td", {}, siNo(x.bloquea_dia_completo)),
            h("td", { clase: "num" }, numero(x.km_estimados)),
          ] : [h("td", { colspan: "6" }, etiqueta(t("ctl_no_existe"), "alerta"))]),
          h("td", { style: "text-align:right" },
            puede(clave) ? boton(t(x ? "ctl_editar" : "ctl_agregar"), () => abrir(codigo, x)) : null))))].filter(Boolean));
  }

  function abrir(codigo, x) {
    forma.replaceChildren(formulario([
      { k: "horas", texto: t("ctl_horas"), tipo: "numero", valor: x && x.horas, requerido: true },
      { k: "horas_descanso", texto: t("ctl_descanso"), tipo: "numero",
        valor: x ? x.horas_descanso : 0, requerido: true },
      /* De cuantas horas es cada bloque de descanso (seccion 105). */
      { k: "intervalo_descanso", texto: t("cat_intervalo_descanso"), tipo: "numero",
        valor: x ? x.intervalo_descanso : 1, requerido: true,
        ayuda: t("cat_intervalo_descanso_ayuda") },
      { k: "aplica_horas_extra", texto: t("ctl_horas_extra"), tipo: "si_no",
        valor: x ? x.aplica_horas_extra : false },
      { k: "bloquea_dia_completo", texto: t("ctl_bloquea"), tipo: "si_no",
        valor: x ? x.bloquea_dia_completo : false },
      { k: "km_estimados", texto: t("ctl_km"), tipo: "numero", valor: x && x.km_estimados },
    ], async (v) => {
      if (x) await api.patch(`/catalogos/modalidades/${x.id}`, completo(x, CAMPOS, v));
      else await api.post("/catalogos/modalidades", { pais_id: paisId, codigo, ...v });
      mensaje(t("ctl_guardado").replace("{que}", t((MODALIDADES.find(mo => mo[0] === codigo) || [])[1])));
      await recargar();
    }, () => forma.replaceChildren()));
  }

  caja.append(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctl_modalidades"), "ay_ctl_modalidades"),
    h("p", { clase: "gris chico ctl-pie" }, t("ctl_modalidades_pie")),
    ...[quienLoLleva(clave)].filter(Boolean), zona, forma, historial(clave)));
  pintar();
}

/* ========================================= requisitos del freelance */

/* Lo que Recursos Humanos pide para activar a un freelance, por pais
   (seccion 111, decision 12): lo lleva sistema y calidad, a pedido de
   Recursos Humanos. Mexico nace con su tabla; Brasil se llena cuando se
   opere alla. Los costos de cada freelance ya no viven aqui: estan en su
   ficha, en Personal de seguridad → Freelance. */
const CAPTURAS = ["archivo", "numero", "archivo_numero", "banco", "riesgo",
                  "entrevista", "contactos", "prueba"];
const VIGENCIAS = ["ninguna", "meses", "documento", "servicio"];

function vigenciaTexto(x) {
  if (x.vigencia === "meses") {
    return x.vigencia_meses === 12 ? t("ctl_req_un_anio")
      : t("ctl_req_meses").replace("{n}", x.vigencia_meses);
  }
  return x.vigencia === "ninguna" ? "—" : t(`ctl_req_vig_${x.vigencia}`);
}

/* La clave del requisito sale de su nombre: es para el sistema, y nadie
   tendria por que escribirla. */
function claveDe(nombre) {
  return (nombre || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40)
    || "requisito";
}

function requisitos(caja, d, recargar) {
  const clave = "requisitos-freelance";
  let paisId = paisInicial(d);
  const zona = h("div");
  const forma = h("div");
  const CAMPOS = ["pais_id", "clave", "nombre", "detalle", "programado", "emergencia",
                  "captura", "vigencia", "vigencia_meses", "antiguedad_meses", "orden"];

  function pintar() {
    const suyos = d.requisitos.filter(x => x.pais_id === paisId)
      .sort((a, b) => a.orden - b.orden || a.id - b.id);
    const cuenta = (tipo) => suyos.filter(x => x.activo !== false && x[tipo]).length;
    zona.replaceChildren(...[
      botonesDePais(d, paisId, (id) => { paisId = id; pintar(); }),
      suyos.length
        ? h("p", { clase: "chico gris" }, t("ctl_req_cuenta")
            .replace("{p}", cuenta("programado")).replace("{e}", cuenta("emergencia")))
        : null,
      tabla([t("ctl_req_requisito"), t("fre_tipo_programado"), t("fre_tipo_emergencia"),
             t("ctl_req_vigencia"), t("ctl_req_captura"), ""],
        suyos.map(x => h("tr", filaDe(x),
          h("td", {}, h("b", {}, x.nombre),
            x.detalle ? h("div", { clase: "chico gris" }, x.detalle) : null),
          h("td", {}, x.programado ? t("ctl_si") : "—"),
          h("td", {}, x.emergencia ? t("ctl_si") : "—"),
          h("td", { clase: "chico" }, vigenciaTexto(x)),
          h("td", { clase: "chico gris" }, t(`fre_cap_${x.captura}`)),
          h("td", { style: "text-align:right;white-space:nowrap" },
            puede(clave) && x.activo !== false ? boton(t("ctl_editar"), () => abrir(x)) : null,
            puede(clave) ? quitarOReactivar(x, `/catalogos/requisitos-freelance/${x.id}`,
                                            x.nombre, recargar) : null))),
        "ctl_req_vacio"),
      h("p", { clase: "chico gris", style: "margin-top:10px" }, t("ctl_req_plazo")),
      puede(clave) ? h("div", { clase: "acciones" },
        boton(t("ctl_req_agregar"), () => abrir(null))) : null].filter(Boolean));
  }

  function abrir(x) {
    forma.replaceChildren(formulario([
      { k: "nombre", texto: t("ctl_req_requisito"), valor: x && x.nombre, requerido: true },
      { k: "detalle", texto: t("ctl_req_detalle"), valor: x && x.detalle },
      { k: "programado", texto: t("fre_tipo_programado"), tipo: "si_no",
        valor: x ? x.programado : true },
      { k: "emergencia", texto: t("fre_tipo_emergencia"), tipo: "si_no",
        valor: x ? x.emergencia : false },
      { k: "captura", texto: t("ctl_req_captura"), tipo: "lista", requerido: true,
        opciones: CAPTURAS.map(c => ({ valor: c, texto: t(`fre_cap_${c}`) })),
        valor: x ? x.captura : "archivo" },
      { k: "vigencia", texto: t("ctl_req_vigencia"), tipo: "lista", requerido: true,
        opciones: VIGENCIAS.map(v => ({ valor: v, texto: t(`ctl_req_tipo_vig_${v}`) })),
        valor: x ? x.vigencia : "ninguna" },
      { k: "vigencia_meses", texto: t("ctl_req_vigencia_meses"), tipo: "numero",
        valor: x && x.vigencia_meses, ayuda: t("ctl_req_vigencia_meses_pie") },
      { k: "antiguedad_meses", texto: t("ctl_req_antiguedad"), tipo: "numero",
        valor: x && x.antiguedad_meses, ayuda: t("ctl_req_antiguedad_pie") },
      { k: "orden", texto: t("ctl_req_orden"), tipo: "numero",
        valor: x ? x.orden : (d.requisitos.filter(r => r.pais_id === paisId)
          .reduce((m, r) => Math.max(m, r.orden), 0) + 10) },
    ], async (v) => {
      const cuerpo = { ...v, pais_id: paisId, orden: v.orden || 0,
                       clave: x ? x.clave : claveDe(v.nombre) };
      if (x) await api.patch(`/catalogos/requisitos-freelance/${x.id}`, completo(x, CAMPOS, cuerpo));
      else await api.post("/catalogos/requisitos-freelance", cuerpo);
      mensaje(t("ctl_guardado").replace("{que}", v.nombre));
      await recargar();
    }, () => forma.replaceChildren()));
  }

  caja.append(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctl_requisitos"), "ay_ctl_requisitos"),
    h("p", { clase: "gris chico ctl-pie" }, t("ctl_requisitos_pie")),
    ...[quienLoLleva(clave)].filter(Boolean), zona, forma, historial(clave)));
  pintar();
}

/* ============================================ pesos del profesionalismo */

function pesos(caja, d, recargar) {
  const clave = "profesionalismo";
  let paisId = paisInicial(d);
  const zona = h("div");

  function pintar() {
    const p = d.pesos[paisId];
    if (!p) {
      zona.replaceChildren(...[
        botonesDePais(d, paisId, (id) => { paisId = id; pintar(); }),
        h("p", { clase: "chico gris" }, t("ctl_pesos_no_se_leen"))].filter(Boolean));
      return;
    }
    const editable = puede(clave);
    const entradas = {};
    const suma = h("b", { clase: "num" });
    const contar = () => {
      const total = DIMENSIONES.reduce((s, [k]) => s + (Number(entradas[k].value) || 0), 0);
      suma.textContent = `${numero(total)} %`;
      suma.className = Math.abs(total - 100) < 0.01 ? "num" : "num ctl-suma-mal";
    };
    const renglonDe = (k, texto, valor) => {
      const control = entrada(k, { type: "number", step: "any", value: String(valor) });
      control.disabled = !editable;
      entradas[k] = control;
      return campo(texto, control);
    };
    const castigos = p.castigo_por_incidencia || {};
    const pesosNodo = h("div", { clase: "ctl-campos" },
      ...DIMENSIONES.map(([k, texto]) => renglonDe(k, t(texto), numero(p.pesos[k]))));
    pesosNodo.addEventListener("input", contar);
    const parametros = h("div", { clase: "ctl-campos" },
      renglonDe("meses_ventana", t("ctl_meses_ventana"), p.ventana_meses),
      renglonDe("horas_referencia", t("ctl_horas_referencia"), p.horas_referencia),
      renglonDe("castigo_error_menor", t("ctl_castigo_menor"), numero(castigos.error_menor)),
      renglonDe("castigo_leve", t("ctl_castigo_leve"), numero(castigos.leve)),
      renglonDe("castigo_grave", t("ctl_castigo_grave"), numero(castigos.grave)),
      renglonDe("puntos_por_evento_manejo", t("ctl_puntos_manejo"), numero(p.puntos_por_evento_manejo)));

    const guardar = boton(t("ctl_guardar"), async () => {
      const valores = {};
      for (const [k] of DIMENSIONES) valores[k] = Number(entradas[k].value) || 0;
      const total = Object.values(valores).reduce((a, b) => a + b, 0);
      if (Math.abs(total - 100) > 0.01) return mensaje(t("ctl_pesos_suma"), "alerta");
      guardar.disabled = true;
      try {
        await api.put("/profesionalismo/pesos", {
          pais_id: paisId, pesos: valores,
          meses_ventana: Number(entradas.meses_ventana.value) || null,
          horas_referencia: Number(entradas.horas_referencia.value) || null,
          castigo_error_menor: Number(entradas.castigo_error_menor.value),
          castigo_leve: Number(entradas.castigo_leve.value),
          castigo_grave: Number(entradas.castigo_grave.value),
          puntos_por_evento_manejo: Number(entradas.puntos_por_evento_manejo.value),
        });
        mensaje(t("ctl_guardado").replace("{que}", t("ctl_pesos")));
        await recargar();
      } catch (err) {
        mensaje(err.message, "grave");
        guardar.disabled = false;
      }
    }, "chico");

    zona.replaceChildren(...[
      h("div", { clase: "acciones", style: "margin:0 0 10px" },
        botonesDePais(d, paisId, (id) => { paisId = id; pintar(); }),
        p.configurado ? null : etiqueta(t("ctl_de_ejemplo"), "alerta")),
      h("h4", {}, t("ctl_pesos_dimensiones")),
      pesosNodo,
      h("p", { clase: "chico" }, t("ctl_pesos_suman"), " ", suma),
      h("h4", { clase: "grupo" }, t("ctl_pesos_parametros")),
      parametros,
      editable ? h("div", { clase: "acciones" }, guardar) : null,
    ].filter(Boolean));
    contar();
  }

  caja.append(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctl_pesos"), "ay_ctl_pesos"),
    h("p", { clase: "gris chico ctl-pie" }, t("ctl_pesos_pie")),
    ...[quienLoLleva(clave)].filter(Boolean), zona, historial(clave)));
  pintar();
}

/* Los tarifarios que vienen de Odoo (seccion 77).

   Los precios viven en Odoo: una lista general por pais y, cuando el
   cliente negocio la suya, la del cliente. Centauro las lee cada hora
   --en la pantalla de Odoo, la tarjeta "Los tarifarios"-- y aqui se ven.

   Dos cosas viven en este archivo:

     * La tabla de productos, en Facturacion: que es en Centauro cada
       producto que Odoo vende. Centauro lo sugiere por el nombre y
       finanzas lo confirma una vez. Sin ella no se sabe que precio de la
       lista es el del conductor y cual el de la Suburban; con ella saldra
       tambien la factura del paso 4.
     * El tarifario de un cliente, como quedo de su lista de Odoo. Lo ve
       finanzas en su pestana y quien cotiza dentro del servicio. Aqui no
       se edita: se corrige en Odoo.
     * El tipo de cambio (seccion 82): cuantos pesos vale un dolar y,
       desde la seccion 123, cuantos reales. Lo pone finanzas a mano y
       aplica para todo hasta que alguien lo cambie. */
import { api } from "./api.js";
import { clientesDelPais, paisDeArranque, paisesDeClientes, pestanasDeClientes,
         recordarPais } from "./catalogos.js";
import { aviso, conAyuda, dinero, etiqueta, fecha, h, hora, listaBuscable,
         mensaje, plegable, tasa } from "./util.js";
import { t } from "./idioma.js";

const MODALIDADES = ["full_day", "medio_dia", "transfer"];
/* Lo que en Odoo se cobra por «Mes» (seccion 123): el paquete de Amazon
   Brasil. Su columna sale solo si la lista trae algo por mes. */
const MES = "mes";
const DEL_PRODUCTO = [...MODALIDADES, MES];
const NOMBRE_MODALIDAD = { full_day: "mod_full_day", medio_dia: "mod_medio_dia",
                           transfer: "mod_transfer", mes: "mod_mes" };
/* De donde salio un precio que la lista no pacto. */
const ORIGEN = { general: "tar_o_general", otra: "tar_o_otra",
                 precio_venta: "tar_o_precio_venta" };
/* Las clases que se cobran por modalidad; las demas no llevan. */
const CON_MODALIDAD = ["rol", "unidad", "paquete"];
/* Las que ponen un precio en el tarifario. */
const CON_PRECIO = ["rol", "unidad", "paquete", "hora_extra"];

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (s, [k, v]) => s.split(`{${k}}`).join(v ?? ""), texto);
}

function cuando(iso) {
  return iso ? `${fecha(iso)} ${hora(iso)}` : "—";
}

/* ------------------------------------------------------------ el tarifario */

/* Una tabla por lo que se cobra --el personal, las unidades, los
   paquetes-- con una columna por modalidad. Lo que la lista pacto va en
   negro; lo que toma de otra lista o del "Precio de venta", en gris y
   dicho. Donde no hay precio lo dice: eso no se puede cotizar. */
function tabla(titulo, filas, moneda) {
  const columnas = filas.some(f => f.precios[MES]) ? DEL_PRODUCTO : MODALIDADES;
  const ancho = `${Math.floor(66 / columnas.length)}%`;
  return h("div", {},
    h("h4", { style: "margin:14px 0 6px" }, titulo),
    h("table", { clase: "lista", style: "table-layout:fixed" },
      h("colgroup", {}, h("col", { style: "width:34%" }),
        ...columnas.map(() => h("col", { style: `width:${ancho}` }))),
      h("thead", {}, h("tr", {}, h("th"),
        ...columnas.map(mo => h("th", { clase: "der" }, t(NOMBRE_MODALIDAD[mo]))))),
      h("tbody", {}, ...filas.map(f => h("tr", {},
        h("td", { style: "font-weight:600" }, f.nombre),
        ...columnas.map(mo => celda(f.precios[mo], moneda)))))));
}

function celda(p, moneda) {
  if (!p) return h("td", { clase: "der gris chico" }, t("tar_sin_precio"));
  const pactado = !p.origen || p.origen === "propio";
  return h("td", { clase: "der num" },
    h("span", pactado ? { style: "font-weight:650" } : { clase: "gris" },
      dinero(p.precio, moneda)),
    pactado ? "" : h("span", { clase: "chico gris" },
                     ` ${t(ORIGEN[p.origen] || "tar_o_otra")}`));
}

function porModalidad(filas) {
  const salida = {};
  for (const f of filas) salida[f.modalidad] = f;
  return salida;
}

/* La hora extra: en Odoo cada rol trae la suya (seccion 113); si todos
   cuestan lo mismo, se dice un solo precio. */
function horaExtra(tar, perfiles) {
  const moneda = tar.moneda;
  const tiene = (x) => x.precio_hora_extra !== null && x.precio_hora_extra !== undefined;
  const conExtra = tar.personal.filter(tiene);
  /* El rol que solo va en paquete trae la suya en el paquete (seccion
     123): la lista de Amazon Brasil no trae al conductor suelto. */
  for (const x of tar.paquetes || []) {
    if (tiene(x) && !tar.personal.some(y => y.perfil_id === x.perfil_id)
        && !conExtra.some(y => y.perfil_id === x.perfil_id)) conExtra.push(x);
  }
  const distintos = [...new Set(conExtra.map(x => Number(x.precio_hora_extra)))];
  if (!distintos.length) return t("tar_extra_sin");
  if (distintos.length === 1) {
    return reemplazar(t("tar_extra"), { m: dinero(distintos[0], moneda) });
  }
  return reemplazar(t("tar_extra"), { m: perfiles.map(p => {
    const x = conExtra.find(y => y.perfil_id === p.id);
    return x ? `${p.nombre} ${dinero(x.precio_hora_extra, moneda)}` : null;
  }).filter(Boolean).join(" · ") });
}

/* Si los paquetes de la lista traen los viaticos del dia (seccion 79;
   los de HASBRO si). Odoo no lo dice: lo marca finanzas aqui, y quien
   cotiza solo lo lee. */
function viaticosDelPaquete(tar, editable) {
  if (!editable) {
    return tar.paquetes_con_viaticos
      ? h("p", { clase: "gris chico", style: "margin:6px 0 0" }, t("tar_con_viaticos"))
      : null;
  }
  const casilla = h("input", { type: "checkbox", style: "width:auto;margin:0" });
  casilla.checked = !!tar.paquetes_con_viaticos;
  casilla.addEventListener("change", async () => {
    casilla.disabled = true;
    try {
      const r = await api.patch(`/tarifarios/${tar.id}/viaticos`,
                                { incluidos: casilla.checked });
      tar.paquetes_con_viaticos = r.paquetes_con_viaticos;
      mensaje(t(r.paquetes_con_viaticos ? "tar_viaticos_si" : "tar_viaticos_no"));
    } catch (err) {
      casilla.checked = !casilla.checked;
      mensaje(err.message, "grave");
    }
    casilla.disabled = false;
  });
  return h("label", { style: "display:flex;gap:8px;align-items:center;margin:8px 0 0;"
                             + "font-weight:400;font-size:13px" },
    casilla, t("tar_con_viaticos_casilla"));
}

function tablas(tar, perfiles, categorias, editable = false) {
  const moneda = tar.moneda;
  const personal = perfiles.map(p => ({ nombre: p.nombre,
    precios: porModalidad(tar.personal.filter(x => x.perfil_id === p.id)) }));
  const unidades = categorias.map(c => ({ nombre: c.nombre,
    precios: porModalidad(tar.unidades.filter(x => x.categoria_id === c.id)) }));
  const paquetes = [];
  for (const x of tar.paquetes) {
    const llave = `${x.perfil_id}:${x.categoria_id}`;
    let fila = paquetes.find(f => f.llave === llave);
    if (!fila) {
      fila = { llave, nombre: `${x.perfil} + ${x.categoria}`, precios: {} };
      paquetes.push(fila);
    }
    fila.precios[x.modalidad] = x;
  }
  return h("div", {},
    tabla(t("tar_personal"), personal, moneda),
    h("p", { clase: "gris chico", style: "margin:6px 0 0" }, horaExtra(tar, perfiles)),
    tabla(t("tar_unidades"), unidades, moneda),
    paquetes.length ? tabla(t("tar_paquetes"), paquetes, moneda) : "",
    paquetes.length ? viaticosDelPaquete(tar, editable) : "");
}

/* De que lista es y de donde sale lo que no trae. */
function cabeza(tar, nombre) {
  const sellos = [];
  if (tar.de_odoo) {
    sellos.push(etiqueta(`${t(tar.general ? "tar_general_de_pais" : "tar_lista_de_odoo")}: `
                         + `${tar.nombre} · ${tar.moneda}`, "ok"));
    if (tar.resto_de) sellos.push(etiqueta(`${t("tar_lo_demas")}: ${tar.resto_de}`, "negro"));
  } else {
    sellos.push(etiqueta(`${t("tar_de_centauro")}: ${tar.nombre} · ${tar.moneda}`, "info"));
  }
  return h("div", { style: "display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:0 0 6px" },
    nombre ? h("span", { style: "font-size:15px;font-weight:650" }, nombre) : "",
    ...sellos);
}

/* Una lista en dolares: el tipo de cambio con que salen los precios que
   toma de una lista en pesos --los grises-- (seccion 82). */
function lineaDelCambio(tar, d) {
  const tc = d.tipo_cambio;
  if (!tc || tar.moneda !== tc.moneda) return null;
  if (!tc.vigente) {
    return aviso(reemplazar(t("tar_tc_sin"), { l: tc.moneda_local }), "alerta");
  }
  return h("div", { clase: "aviso", style: "margin:8px 0 0" },
    reemplazar(t("tar_tc_linea"), { m: tc.moneda, t: tasa(tc.vigente.tasa),
                                    l: tc.moneda_local }));
}

function nota(tar, d) {
  if (!tar.de_odoo) {
    return t(d.cliente.de_odoo && d.desde_odoo ? "tar_nota_retenido" : "tar_nota_centauro");
  }
  const propios = [...tar.personal, ...tar.unidades, ...tar.paquetes]
    .filter(x => x.origen === "propio").length;
  return reemplazar(t(propios === 1 ? "tar_nota_odoo_uno" : "tar_nota_odoo"),
                    { n: propios, l: tar.nombre, c: cuando(tar.leido_en) });
}

/* Lo que devuelve /tarifarios/cliente/{id}, pintado. `conNombre`: dentro
   del servicio el cliente ya esta en el encabezado. */
export function vistaTarifario(d, conNombre = true) {
  const nombre = conNombre ? d.cliente.nombre : null;
  if (!d.tarifario) {
    return h("div", {},
      nombre ? h("div", { style: "font-size:15px;font-weight:650;margin:0 0 8px" }, nombre) : "",
      aviso(t(d.cliente.de_odoo && d.desde_odoo ? "tar_sin_tarifario_odoo"
                                                 : "tar_sin_tarifario"), "alerta"));
  }
  const partes = [
    cabeza(d.tarifario, nombre),
    h("p", { clase: "gris chico", style: "margin:0" }, nota(d.tarifario, d)),
    lineaDelCambio(d.tarifario, d) || "",
    tablas(d.tarifario, d.perfiles, d.categorias, d.puede_editar),
    h("p", { clase: "gris chico", style: "margin:12px 0 0" }, t("tar_leyenda")),
  ];
  /* La de los implantados, aparte y plegada: se usa en el acuerdo del
     implantado, no al cotizar un eventual. */
  if (d.implantados) {
    partes.push(h("div", { style: "margin-top:14px" }, plegable(
      reemplazar(t("tar_implantados"), { l: d.implantados.nombre }),
      h("div", { style: "margin-top:8px" }, cabeza(d.implantados, null),
        lineaDelCambio(d.implantados, d) || "",
        tablas(d.implantados, d.perfiles, d.categorias, d.puede_editar)),
      () => `${d.implantados.nombre} · ${d.implantados.moneda}`, {}, false)));
  }
  return h("div", {}, ...partes);
}

/* Dentro del servicio: quien cotiza ve con que precios se le cobra a este
   cliente. Nace plegado, con la lista en el renglon del titulo. */
export async function bloqueTarifario(clienteId) {
  let d;
  try {
    d = await api.get(`/tarifarios/cliente/${clienteId}`);
  } catch {
    return h("div");
  }
  const resumen = () => (d.tarifario
    ? `${d.tarifario.nombre} · ${d.tarifario.moneda}` : t("tar_sin_tarifario_corto"));
  return h("div", { clase: "tarjeta" },
    plegable(t("tar_del_cliente"), h("div", { style: "margin-top:8px" },
      vistaTarifario(d, false)), resumen, {}, false));
}

/* ------------------------------------------------------------ la pestana */

/* La pestana de Facturacion: el tipo de cambio, la tabla de productos y
   el tarifario de cualquier cliente. */
export function pestanaTarifarios() {
  const cambio = h("div");
  const productos = h("div", {}, h("p", { clase: "gris" }, t("tar_cargando")));
  const cliente = h("div");
  tarjetaTipoDeCambio(cambio);
  tarjetaProductos(productos);
  tarjetaCliente(cliente);
  return h("div", {}, cambio, productos, cliente);
}

/* ------------------------------------------------------------ el tipo de cambio */

/* Cuantos pesos vale un dolar (seccion 82) y, para Brasil, cuantos
   reales (seccion 123). Decision de Salvador, 26 de septiembre: lo pone
   finanzas a mano y el que se pone aplica para todo hasta que alguien lo
   cambie. Lo que ya quedo fijo --una cotizacion o una propuesta
   autorizada, un visto bueno, un mes abierto-- se queda con el suyo. */
async function tarjetaTipoDeCambio(caja) {
  let d;
  try {
    d = await api.get("/tarifarios/tipo-de-cambio");
  } catch (err) {
    return caja.replaceChildren(aviso(err.message, "grave"));
  }
  const pintar = (todo) => {
    const pares = (todo.pares && todo.pares.length) ? todo.pares : [todo];
    const nodos = [conAyuda("h3", t("tar_tc_titulo"), "ay_tar_tipo_cambio")];
    for (const x of pares) {
      if (pares.length > 1) {
        nodos.push(h("div", { style: "font-weight:650;margin:10px 0 6px" },
          t(`tar_tc_par_${x.moneda_local}`)));
      }
      nodos.push(...unPar(x, todo.puede_editar, pintar));
    }
    nodos.push(h("p", { clase: "gris chico", style: "margin:10px 0 0" }, t("tar_tc_pie")));
    caja.replaceChildren(h("div", { clase: "tarjeta" }, ...nodos));
  };
  pintar(d);
}

/* Un tipo de cambio: el dolar a peso o el dolar a real. */
function unPar(x, editable, pintar) {
  const v = x.vigente;
  const brl = x.moneda_local === "BRL";
  const nodos = [];
  if (editable) {
    const campo = h("input", { type: "number", min: "0.0001", step: "0.0001",
                               clase: "num", style: "width:130px",
                               value: v ? tasa(v.tasa) : "" });
    const guardar = h("button", { type: "button" }, t("tar_tc_guardar"));
    guardar.addEventListener("click", async () => {
      const nueva = Number(campo.value);
      if (!(nueva > 0)) return mensaje(t(brl ? "tar_tc_falta_BRL" : "tar_tc_falta"), "alerta");
      /* Un salto grande casi siempre es un dedo que se resbalo: se
         pregunta antes, porque desde ese momento aplica para todo. */
      const antes = v ? Number(v.tasa) : null;
      if (antes && Math.abs(nueva - antes) / antes > 0.1 && !confirm(
          reemplazar(t("tar_tc_salto"), { a: tasa(v.tasa),
                                          b: tasa(campo.value) }))) return;
      guardar.disabled = true;
      try {
        pintar(await api.put("/tarifarios/tipo-de-cambio",
                             { tasa: campo.value, moneda_local: x.moneda_local }));
        mensaje(t("tar_tc_guardado"));
      } catch (err) {
        mensaje(err.message, "grave");
        guardar.disabled = false;
      }
    });
    nodos.push(h("div", { clase: "acciones",
                          style: "align-items:center;margin:0 0 8px" },
      h("span", { style: "font-weight:650" }, `1 ${x.moneda} =`), campo,
      h("span", { style: "font-weight:650" }, x.moneda_local), guardar));
  } else if (v) {
    nodos.push(h("p", { style: "font-size:15px;font-weight:650;margin:0 0 6px" },
      `1 ${x.moneda} = ${tasa(v.tasa)} ${x.moneda_local}`));
  }
  if (v) {
    nodos.push(h("p", { clase: "gris chico", style: "margin:0 0 6px" },
      reemplazar(t(v.por ? "tar_tc_puesto" : "tar_tc_puesto_sin"),
                 { q: v.por || "", c: cuando(v.puesto_en) })));
  } else {
    nodos.push(aviso(t(brl ? "tar_tc_sin_ninguno_BRL" : "tar_tc_sin_ninguno"), "alerta"));
  }
  if ((x.anteriores || []).length) {
    nodos.push(h("p", { clase: "gris chico", style: "margin:0 0 6px" },
      reemplazar(t("tar_tc_antes"), { l: x.anteriores.map(a =>
        reemplazar(t(a.por ? "tar_tc_anterior" : "tar_tc_anterior_sin"),
                   { t: tasa(a.tasa), f: fecha(a.puesto_en), q: a.por || "" }))
        .join(" · ") })));
  }
  return nodos;
}

/* El tarifario de cualquier cliente y, arriba, las generales de cada
   pais (seccion 124): «Brasil · General USD» no siempre tiene cliente, y
   sin abrirla no habia donde marcar si sus paquetes traen los viaticos.
   Con una pestana por pais (seccion 125), como en la cotizacion: cada
   una trae sus generales y sus clientes. */
async function tarjetaCliente(caja) {
  let clientes, listas, paises;
  try {
    [clientes, listas, paises] = await Promise.all([
      api.get("/catalogos/clientes"), api.get("/tarifarios").catch(() => []),
      api.get("/catalogos/paises").catch(() => [])]);
  } catch (err) {
    return caja.replaceChildren(aviso(err.message, "grave"));
  }
  const cat = { clientes, paises };
  const varios = paisesDeClientes(cat).length > 1;
  let paisId = paisDeArranque(cat);
  const delPais = (x) => !varios || x.pais_id == null || String(x.pais_id) === String(paisId);
  const pestanas = h("div");
  const busca = h("div", { style: "max-width:460px" });
  const vista = h("div", { style: "margin-top:14px" });

  function pintar() {
    const nodo = pestanasDeClientes(cat, paisId, (id) => {
      paisId = id;
      recordarPais(id);
      vista.replaceChildren();
      pintar();
    });
    if (nodo) nodo.style.margin = "0 0 10px";
    pestanas.replaceChildren(nodo || "");
    const activos = (varios ? clientesDelPais(cat, paisId) : clientes.filter(c => c.activo))
      .sort((a, b) => a.nombre.localeCompare(b.nombre));
    const escoger = h("select", { style: "max-width:460px" },
      h("option", { value: "" }, t("tar_escoge_cliente")),
      ...listas.filter(x => x.general && delPais(x)).map(x => h("option",
        { value: `lista:${x.id}` },
        reemplazar(t("tar_opcion_general"), { l: x.nombre, m: x.moneda }))),
      ...activos.map(c => h("option", { value: String(c.id) }, c.nombre)));
    escoger.addEventListener("change", async () => {
      if (!escoger.value) return vista.replaceChildren();
      vista.replaceChildren(h("p", { clase: "gris" }, t("tar_cargando")));
      const lista = escoger.value.startsWith("lista:");
      try {
        vista.replaceChildren(vistaTarifario(await api.get(lista
          ? `/tarifarios/lista/${escoger.value.slice("lista:".length)}`
          : `/tarifarios/cliente/${escoger.value}`), !lista));
      } catch (err) {
        vista.replaceChildren(aviso(err.message, "grave"));
      }
    });
    busca.replaceChildren(listaBuscable(escoger, t("buscar_cliente")));
  }
  pintar();
  caja.replaceChildren(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("tar_titulo_cliente"), "ay_tar_cliente"),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" }, t("tar_cliente_pie")),
    pestanas, busca, vista));
}

/* ------------------------------------------------------------ los productos */

const SELLOS = {
  confirmado: ["tar_e_confirmado", "ok"],
  no_ep: ["tar_e_confirmado", "negro"],
  sugerido: ["tar_e_sugerido", "alerta"],
  falta: ["tar_e_falta", "grave"],
};
/* Lo que falta decidir, arriba: es la lista de trabajo de finanzas. */
const ORDEN = { falta: 0, sugerido: 1, confirmado: 2, no_ep: 3 };

function estadoDe(p) {
  if (!p.clase) return "falta";
  if (!p.confirmado) return "sugerido";
  return p.clase === "no_ep" ? "no_ep" : "confirmado";
}

/* Cada opcion del selector es la clase con su rol y su unidad:
   "rol:1:", "unidad::5", "paquete:1:5", "no_ep::". Vacio: falta decir. */
function valorDe(p) {
  return p.clase ? `${p.clase}:${p.perfil_id ?? ""}:${p.categoria_id ?? ""}` : "";
}

/* Lo que pone precio un producto confirmado: dos que dicen lo mismo --el
   gemelo en ingles-- chocan si la lista no pacta ninguno, y manda el que
   finanzas escoja. Solo dentro de su pais (seccion 123): el conductor de
   Brasil no choca con el de Mexico, cada lista lee los de su pais. */
function conceptoDe(p) {
  if (!p.confirmado || !CON_PRECIO.includes(p.clase)) return null;
  return [p.pais ?? "", p.clase, p.perfil_id ?? "", p.categoria_id ?? "",
          p.clase === "hora_extra" ? "" : (p.modalidad ?? "")].join(":");
}

function opciones(d) {
  const grupo = (titulo, lista) => h("optgroup", { label: titulo }, ...lista);
  return [
    h("option", { value: "" }, t("tar_falta_decir")),
    grupo(t("tar_g_rol"), d.perfiles.map(p =>
      h("option", { value: `rol:${p.id}:` }, `${t("tar_rol")} · ${p.nombre}`))),
    grupo(t("tar_g_unidad"), d.categorias.map(c =>
      h("option", { value: `unidad::${c.id}` }, `${t("tar_unidad")} · ${c.nombre}`))),
    grupo(t("tar_g_paquete"), d.perfiles.flatMap(p => d.categorias.map(c =>
      h("option", { value: `paquete:${p.id}:${c.id}` },
        `${t("tar_paquete")} · ${p.nombre} + ${c.nombre}`)))),
    /* La hora extra de cada rol (seccion 113): en Odoo cada rol trae la
       suya. Sin rol, la de todos. */
    grupo(t("tar_g_hora_extra"), [
      h("option", { value: "hora_extra::" }, t("tar_hora_extra_todos")),
      ...d.perfiles.map(p => h("option", { value: `hora_extra:${p.id}:` },
                               `${t("tar_hora_extra")} · ${p.nombre}`))]),
    grupo(t("tar_g_otro"), [
      h("option", { value: "viaticos::" }, t("tar_viaticos")),
      h("option", { value: "no_ep::" }, t("tar_no_ep"))]),
  ];
}

function filaDeProducto(p, d, repintar, gemelos) {
  const editable = d.puede_editar;
  const que = h("select", { style: "width:auto;min-width:250px;max-width:360px",
                            disabled: editable ? false : "disabled" }, ...opciones(d));
  que.value = valorDe(p);
  /* Lo que se dijo por la API y no esta entre las opciones --un rol que
     ya no existe-- se muestra tal cual, para no perderlo. */
  if (que.value !== valorDe(p)) {
    que.append(h("option", { value: valorDe(p) }, p.clase));
    que.value = valorDe(p);
  }
  const modalidad = h("select", { style: "width:auto" },
    h("option", { value: "" }, "—"),
    ...DEL_PRODUCTO.map(mo => h("option", { value: mo }, t(NOMBRE_MODALIDAD[mo]))));
  modalidad.value = p.modalidad || "";
  const ajustar = () => {
    const lleva = CON_MODALIDAD.includes(que.value.split(":")[0]);
    modalidad.disabled = !editable || !lleva;
    if (!lleva) modalidad.value = "";
    else if (!modalidad.value) modalidad.value = "full_day";
  };
  ajustar();

  /* Guardar lo deja confirmado: ninguna lectura lo vuelve a sugerir. */
  const guardar = async () => {
    const [clase, perfil, categoria] = que.value.split(":");
    try {
      await api.patch(`/tarifarios/productos/${p.id}`, {
        clase: clase || null,
        perfil_id: perfil ? Number(perfil) : null,
        categoria_id: categoria ? Number(categoria) : null,
        modalidad: modalidad.value || null });
      mensaje(t(clase ? "tar_guardado" : "tar_quitado"));
    } catch (err) {
      mensaje(err.message, "grave");
    }
    await repintar();
  };
  que.addEventListener("change", () => { ajustar(); guardar(); });
  modalidad.addEventListener("change", guardar);

  const estado = estadoDe(p);
  const [clave, tono] = SELLOS[estado];
  const confirmar = editable && estado === "sugerido"
    ? h("button", { type: "button", clase: "chico claro", onclick: guardar },
        t("tar_confirmar"))
    : "";
  /* Entre los que dicen lo mismo, el que manda. */
  const mandar = async () => {
    try {
      await api.post(`/tarifarios/productos/${p.id}/preferido`, { preferido: true });
      mensaje(t("tar_mandado"));
    } catch (err) {
      mensaje(err.message, "grave");
    }
    await repintar();
  };
  const manda = !gemelos ? ""
    : p.preferido ? etiqueta(t("tar_manda"), "info")
    : editable ? h("button", { type: "button", clase: "chico claro", onclick: mandar },
                   t("tar_que_mande"))
    : "";
  /* Para la factura del eventual (seccion 116): el de los gastos, y el
     que en Odoo tiene varias variantes, que no se sabe con cual cobrar. */
  const variantes = p.variantes > 1 && (p.de_gastos || CON_PRECIO.includes(p.clase))
    ? h("div", { clase: "chico", style: "color:var(--alerta);margin-top:2px" },
        reemplazar(t("tar_variantes"), { n: p.variantes }))
    : "";
  return h("tr", p.vendible ? {} : { style: "opacity:.65" },
    h("td", {}, h("div", { style: "font-weight:600" }, p.nombre),
      p.vendible ? "" : h("div", { clase: "chico gris" }, t("tar_ya_no_se_vende")),
      p.de_gastos ? h("div", { clase: "chico gris", style: "margin-top:2px" },
                      t("tar_de_gastos_pie")) : "",
      variantes),
    h("td", { clase: "gris" }, p.unidad || "—"),
    h("td", {}, que,
      gemelos ? h("div", { clase: "chico gris", style: "margin-top:4px" },
                  reemplazar(t("tar_gemelos"), { n: gemelos.length - 1 })) : ""),
    h("td", {}, modalidad),
    h("td", {}, h("div", { style: "display:flex;gap:8px;align-items:center;white-space:nowrap" },
      etiqueta(t(clave), tono), confirmar, manda,
      p.de_gastos ? etiqueta(t("tar_de_gastos"), "info") : "")));
}

/* La pestana de pais de la tabla de productos (seccion 123): se queda
   al repintar, despues de decir que es un producto. */
let paisDeProductos = null;

/* «Mexico (34)» «Brasil (3)»: cada pais con los de su categoria. Lo que
   no es de ninguna --el de los gastos, si no esta en ellas-- se ve en el
   primero. */
function pestanasDePais(d, filas, alCambiar) {
  const paises = d.paises || [];
  if (paises.length < 2) return { visibles: filas, pais: paises[0] || null, nodo: "" };
  const delPais = (p) => p.pais || paises[0].codigo;
  if (!paises.some(x => x.codigo === paisDeProductos)) paisDeProductos = paises[0].codigo;
  const nodo = h("div", { clase: "pestanas", style: "margin:0 0 10px" },
    ...paises.map(x => h("button", {
      type: "button", clase: x.codigo === paisDeProductos ? "pestana chico activa" : "pestana chico",
      onclick: () => { paisDeProductos = x.codigo; alCambiar(); },
    }, `${x.pais} (${filas.filter(p => delPais(p) === x.codigo).length})`)));
  return { visibles: filas.filter(p => delPais(p) === paisDeProductos),
           pais: paises.find(x => x.codigo === paisDeProductos), nodo };
}

/* De donde salen los de ese pais: su categoria de Odoo y, si no es el
   espanol de Mexico, el idioma de sus nombres. */
function deDondeSalen(d, pais) {
  if (pais) {
    const idioma = pais.idioma && pais.idioma !== "es_MX"
      ? " " + reemplazar(t("tar_productos_idioma"), { i: t(`tar_idioma_${pais.idioma}`) }) : "";
    return " " + reemplazar(t("tar_productos_categoria"), { c: pais.categoria }) + idioma;
  }
  return d.categoria ? " " + reemplazar(t("tar_productos_categoria"), { c: d.categoria }) : "";
}

async function tarjetaProductos(caja) {
  let d;
  try {
    d = await api.get("/tarifarios/productos");
  } catch (err) {
    return caja.replaceChildren(aviso(err.message, "grave"));
  }
  const repintar = () => tarjetaProductos(caja);
  /* Dentro de cada estado, por lo que es: asi los que dicen lo mismo
     --el gemelo en ingles-- quedan juntos y se ve cual manda. */
  const CLASES = ["rol", "unidad", "paquete", "hora_extra", "viaticos", "no_ep"];
  const cifra = (n) => String(n ?? 0).padStart(6, "0");
  const loQueEs = (p) => [
    cifra(p.clase ? CLASES.indexOf(p.clase) : 9), cifra(p.perfil_id),
    cifra(p.categoria_id), cifra(DEL_PRODUCTO.indexOf(p.modalidad) + 1)].join(":");
  const filas = [...d.productos].sort((a, b) =>
    (a.vendible === b.vendible ? 0 : a.vendible ? -1 : 1)
    || ORDEN[estadoDe(a)] - ORDEN[estadoDe(b)]
    || loQueEs(a).localeCompare(loQueEs(b))
    || a.nombre.localeCompare(b.nombre));
  const iguales = {};
  for (const p of filas) {
    const c = conceptoDe(p);
    if (c) (iguales[c] = iguales[c] || []).push(p);
  }
  const gemelosDe = (p) => {
    const lista = iguales[conceptoDe(p)];
    return lista && lista.length > 1 ? lista : null;
  };
  /* Cada pais con los suyos (seccion 123): Mexico y Brasil, cada uno de
     su categoria de Odoo. La cuenta y «Confirmar los sugeridos» son de la
     pestana que se ve (seccion 124): el de Brasil no confirma los de
     Mexico. */
  const pestanas = pestanasDePais(d, filas, repintar);
  const cuenta = { t: pestanas.visibles.length, c: 0, s: 0, f: 0 };
  for (const p of pestanas.visibles) {
    const e = estadoDe(p);
    if (e === "falta") cuenta.f += 1;
    else if (e === "sugerido") cuenta.s += 1;
    else cuenta.c += 1;
  }

  const leer = h("button", { type: "button", clase: "claro",
                             disabled: d.conectado ? false : "disabled" },
    t("tar_leer_odoo"));
  leer.addEventListener("click", async () => {
    leer.disabled = true;
    try {
      const r = await api.post("/tarifarios/productos/leer", {}, { segundos: 120 });
      mensaje(reemplazar(t("tar_leidos"), { n: r.leidos, v: r.nuevos }));
      await repintar();
    } catch (err) {
      mensaje(err.message, "grave");
      leer.disabled = false;
    }
  });
  const confirmar = h("button", { type: "button" },
    reemplazar(t("tar_confirmar_sugeridos"), { n: cuenta.s }));
  confirmar.addEventListener("click", async () => {
    confirmar.disabled = true;
    try {
      const r = await api.post("/tarifarios/productos/confirmar", {
        ids: pestanas.visibles.filter(p => estadoDe(p) === "sugerido").map(p => p.id) });
      mensaje(reemplazar(t("tar_confirmados"), { n: r.confirmados }));
      await repintar();
    } catch (err) {
      mensaje(err.message, "grave");
      confirmar.disabled = false;
    }
  });

  const pie = [reemplazar(t("tar_cuenta"), cuenta)];
  if (d.leidos_en) pie.push(reemplazar(t("tar_leidos_en"), { c: cuando(d.leidos_en) }));
  const acciones = h("div", { clase: "acciones", style: "margin:0 0 12px;align-items:center" },
    d.puede_editar && cuenta.s ? confirmar : "",
    d.puede_editar ? leer : "",
    h("span", { clase: "gris chico" }, pie.join(" · ")));

  const cuerpo = pestanas.visibles.length
    ? h("table", { clase: "lista" },
        h("thead", {}, h("tr", {},
          h("th", {}, t("tar_col_producto")), h("th", {}, t("tar_col_unidad")),
          h("th", {}, t("tar_col_que")), h("th", {}, t("tar_col_modalidad")), h("th"))),
        h("tbody", {}, ...pestanas.visibles.map(p => filaDeProducto(p, d, repintar,
                                                                     gemelosDe(p)))))
    : h("div", { clase: "vacio" }, t(!d.conectado ? "tar_sin_conexion"
                                     : filas.length ? "tar_sin_productos_pais"
                                     : "tar_sin_productos"));

  caja.replaceChildren(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("tar_titulo_productos"), "ay_tar_productos"),
    h("p", { clase: "gris", style: "margin:0 0 10px" }, t("tar_productos_pie"),
      /* De donde salen (seccion 112): solo la categoria de PE en Odoo; la
         de cada pais desde la seccion 123. */
      deDondeSalen(d, pestanas.pais)),
    acciones, pestanas.nodo, cuerpo));
}

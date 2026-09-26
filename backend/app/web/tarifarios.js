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
       se edita: se corrige en Odoo. */
import { api } from "./api.js";
import { aviso, conAyuda, dinero, etiqueta, fecha, h, hora, listaBuscable,
         mensaje, plegable } from "./util.js";
import { t } from "./idioma.js";

const MODALIDADES = ["full_day", "medio_dia", "transfer"];
const NOMBRE_MODALIDAD = { full_day: "mod_full_day", medio_dia: "mod_medio_dia",
                           transfer: "mod_transfer" };
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
  return h("div", {},
    h("h4", { style: "margin:14px 0 6px" }, titulo),
    h("table", { clase: "lista", style: "table-layout:fixed" },
      h("colgroup", {}, h("col", { style: "width:34%" }),
        ...MODALIDADES.map(() => h("col", { style: "width:22%" }))),
      h("thead", {}, h("tr", {}, h("th"),
        ...MODALIDADES.map(mo => h("th", { clase: "der" }, t(NOMBRE_MODALIDAD[mo]))))),
      h("tbody", {}, ...filas.map(f => h("tr", {},
        h("td", { style: "font-weight:600" }, f.nombre),
        ...MODALIDADES.map(mo => celda(f.precios[mo], moneda)))))));
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

/* La hora extra: en Odoo es un producto para todos, asi que casi siempre
   es un solo precio. Si cada rol trae el suyo, se dice cada uno. */
function horaExtra(tar, perfiles) {
  const moneda = tar.moneda;
  const conExtra = tar.personal.filter(x => x.precio_hora_extra !== null
                                            && x.precio_hora_extra !== undefined);
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

function tablas(tar, perfiles, categorias) {
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
    paquetes.length ? tabla(t("tar_paquetes"), paquetes, moneda) : "");
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

function nota(tar, d) {
  if (!tar.de_odoo) {
    return t(d.cliente.de_odoo && d.desde_odoo ? "tar_nota_retenido" : "tar_nota_centauro");
  }
  const propios = [...tar.personal, ...tar.unidades, ...tar.paquetes]
    .filter(x => x.origen === "propio").length;
  return reemplazar(t("tar_nota_odoo"),
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
    tablas(d.tarifario, d.perfiles, d.categorias),
    h("p", { clase: "gris chico", style: "margin:12px 0 0" }, t("tar_leyenda")),
  ];
  /* La de los implantados, aparte y plegada: se usa en el acuerdo del
     implantado, no al cotizar un eventual. */
  if (d.implantados) {
    partes.push(h("div", { style: "margin-top:14px" }, plegable(
      reemplazar(t("tar_implantados"), { l: d.implantados.nombre }),
      h("div", { style: "margin-top:8px" }, cabeza(d.implantados, null),
        tablas(d.implantados, d.perfiles, d.categorias)),
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

/* La pestana de Facturacion: la tabla de productos y el tarifario de
   cualquier cliente. */
export function pestanaTarifarios() {
  const productos = h("div", {}, h("p", { clase: "gris" }, t("tar_cargando")));
  const cliente = h("div");
  tarjetaProductos(productos);
  tarjetaCliente(cliente);
  return h("div", {}, productos, cliente);
}

async function tarjetaCliente(caja) {
  let clientes;
  try {
    clientes = await api.get("/catalogos/clientes");
  } catch (err) {
    return caja.replaceChildren(aviso(err.message, "grave"));
  }
  const activos = clientes.filter(c => c.activo)
    .sort((a, b) => a.nombre.localeCompare(b.nombre));
  const vista = h("div", { style: "margin-top:14px" });
  const escoger = h("select", { style: "max-width:460px" },
    h("option", { value: "" }, t("tar_escoge_cliente")),
    ...activos.map(c => h("option", { value: String(c.id) }, c.nombre)));
  escoger.addEventListener("change", async () => {
    if (!escoger.value) return vista.replaceChildren();
    vista.replaceChildren(h("p", { clase: "gris" }, t("tar_cargando")));
    try {
      vista.replaceChildren(vistaTarifario(
        await api.get(`/tarifarios/cliente/${escoger.value}`)));
    } catch (err) {
      vista.replaceChildren(aviso(err.message, "grave"));
    }
  });
  caja.replaceChildren(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("tar_titulo_cliente"), "ay_tar_cliente"),
    h("p", { clase: "gris chico", style: "margin:0 0 10px" }, t("tar_cliente_pie")),
    h("div", { style: "max-width:460px" }, listaBuscable(escoger, t("buscar_cliente"))),
    vista));
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
   finanzas escoja. */
function conceptoDe(p) {
  if (!p.confirmado || !CON_PRECIO.includes(p.clase)) return null;
  return [p.clase, p.perfil_id ?? "", p.categoria_id ?? "",
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
    grupo(t("tar_g_otro"), [
      h("option", { value: "hora_extra::" }, t("tar_hora_extra")),
      h("option", { value: "viaticos::" }, t("tar_viaticos")),
      h("option", { value: "no_ep::" }, t("tar_no_ep"))]),
  ];
}

function filaDeProducto(p, d, repintar, gemelos) {
  const editable = d.puede_editar;
  const que = h("select", { style: "width:auto;min-width:250px;max-width:360px",
                            disabled: editable ? false : "disabled" }, ...opciones(d));
  que.value = valorDe(p);
  /* Lo que se dijo por la API y no esta entre las opciones --la hora
     extra de un solo rol-- se muestra tal cual, para no perderlo. */
  if (que.value !== valorDe(p)) {
    que.append(h("option", { value: valorDe(p) }, p.clase));
    que.value = valorDe(p);
  }
  const modalidad = h("select", { style: "width:auto" },
    h("option", { value: "" }, "—"),
    ...MODALIDADES.map(mo => h("option", { value: mo }, t(NOMBRE_MODALIDAD[mo]))));
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
  return h("tr", p.vendible ? {} : { style: "opacity:.65" },
    h("td", {}, h("div", { style: "font-weight:600" }, p.nombre),
      p.vendible ? "" : h("div", { clase: "chico gris" }, t("tar_ya_no_se_vende"))),
    h("td", { clase: "gris" }, p.unidad || "—"),
    h("td", {}, que,
      gemelos ? h("div", { clase: "chico gris", style: "margin-top:4px" },
                  reemplazar(t("tar_gemelos"), { n: gemelos.length - 1 })) : ""),
    h("td", {}, modalidad),
    h("td", {}, h("div", { style: "display:flex;gap:8px;align-items:center;white-space:nowrap" },
      etiqueta(t(clave), tono), confirmar, manda)));
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
    cifra(p.categoria_id), cifra(MODALIDADES.indexOf(p.modalidad) + 1)].join(":");
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
  const cuenta = { t: filas.length, c: 0, s: 0, f: 0 };
  for (const p of filas) {
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
      const r = await api.post("/tarifarios/productos/confirmar", {});
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

  const cuerpo = filas.length
    ? h("table", { clase: "lista" },
        h("thead", {}, h("tr", {},
          h("th", {}, t("tar_col_producto")), h("th", {}, t("tar_col_unidad")),
          h("th", {}, t("tar_col_que")), h("th", {}, t("tar_col_modalidad")), h("th"))),
        h("tbody", {}, ...filas.map(p => filaDeProducto(p, d, repintar, gemelosDe(p)))))
    : h("div", { clase: "vacio" }, t(d.conectado ? "tar_sin_productos" : "tar_sin_conexion"));

  caja.replaceChildren(h("div", { clase: "tarjeta" },
    conAyuda("h3", t("tar_titulo_productos"), "ay_tar_productos"),
    h("p", { clase: "gris", style: "margin:0 0 10px" }, t("tar_productos_pie")),
    acciones, cuerpo));
}

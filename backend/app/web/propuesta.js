/* La propuesta del implantado (seccion 115).

   Salvador, 30 de septiembre: «empezamos implantado. Te mando el ejemplo
   de una propuesta. Esta no se llama cotizacion, se llama propuesta». Se
   arma en Cotizaciones, junto a la del eventual, con sus decisiones del 1
   de octubre:

     1. Folio EP/PRO-0001, con su version.
     2. Los precios salen de la lista de implantados del cliente; el que
        no tiene --la empresa nueva-- o el precio que se pacta distinto lo
        escribe el consultor con su motivo, y direccion de operaciones lo
        autoriza antes de que se pueda mandar.
     3. Tres modalidades: lunes a viernes (22 dias al mes mas los
        adicionales), lunes a sabado (26 mas los adicionales) o el mes
        completo (30 a costo fijo); en las tres, mas viaticos o con los
        viaticos incluidos.
     4. El mensual antes de IVA, el IVA y el mensual con IVA.
     5. Cuando el cliente la autoriza, nace el implantado con ella
        adentro.

   Los precios se piden al servidor mientras se arma, sin guardar nada,
   como en la cotizacion. Connect no manda correos: el consultor baja el
   PDF y lo manda desde su correo. */
import { api, sesion } from "./api.js";
import { catalogos, clientesDelPais, listaDeConsultores, paisDeArranque, pestanasDeClientes,
         recordarPais } from "./catalogos.js";
import { aviso, campo, conAyuda, dinero, entrada, etiqueta, h, hoyLocal, lista,
         listaBuscable, mensaje } from "./util.js";
import { t } from "./idioma.js";
import { tiene } from "./menu.js";
import { bajar } from "./bitacora_admin.js";
import { abrirPdf, diaDe, estatusDe, fechaCorta, finDeAnio, IDIOMA_PDF, irA, NUEVA,
         OTRA, reemplazar } from "./cotizaciones.js";

const ESPERA_PRECIOS = 400;
const ESPECIAL = "propuestas.precio_especial";
/* Las tres modalidades (decision 3), con los dias que cubre el mensual. */
const MODALIDADES = [["lunes_viernes", "pro_mod_lv", "pro_mod_lv_pie"],
                     ["lunes_sabado", "pro_mod_ls", "pro_mod_ls_pie"],
                     ["todos", "pro_mod_todos", "pro_mod_todos_pie"]];
const MODALIDAD_CORTA = { lunes_viernes: "pro_mod_lv_corta", lunes_sabado: "pro_mod_ls_corta",
                          todos: "pro_mod_todos_corta" };
/* Lo que el PDF toma de Catalogos y todavia no esta escrito. */
const FALTA_TEXTO = {
  razon_social: "ctz_ft_razon_social", rfc: "ctz_ft_rfc", tasa_iva: "ctz_ft_tasa_iva",
  pro_incluye: "pro_ft_incluye", pro_incluye_unidad: "pro_ft_incluye_unidad",
  pro_incluidos: "pro_ft_incluidos", pro_no_incluye: "pro_ft_no_incluye",
  pro_viaticos: "pro_ft_viaticos", pro_cliente: "pro_ft_cliente",
  pro_centauro: "pro_ft_centauro", pro_aceptacion: "pro_ft_aceptacion",
};

const numero = (v) => (v === null || v === undefined || v === "" ? null : Number(v));

/* Lo que el consultor escribe como precio, en el formato de la moneda de
   la propuesta (seccion 129, hallazgo r2-05): en reales el punto es de
   miles y la coma es decimal --«17.500,00»--; en pesos y dolares, al
   reves. Con los dos separadores, el ultimo es el decimal, venga la
   moneda que venga. Antes «17.500,00» se leia como «17.500.00», no era
   numero y se mandaba vacio: la fila quedaba «de la lista» sin que el
   consultor lo notara. */
export function montoEscrito(texto, moneda) {
  const s = String(texto ?? "").trim().replace(/[^\d.,-]/g, "");
  if (!s) return null;
  const coma = s.lastIndexOf(","), punto = s.lastIndexOf(".");
  let limpio;
  if (coma >= 0 && punto >= 0) {
    limpio = coma > punto ? s.replace(/\./g, "").replace(",", ".")
                          : s.replace(/,/g, "");
  } else if (moneda === "BRL") {
    limpio = coma >= 0 ? s.replace(",", ".") : s.replace(/\./g, "");
  } else {
    limpio = s.replace(/,/g, "");
  }
  const n = Number(limpio);
  return Number.isFinite(n) ? n : null;
}

/* El precio sugerido, sin separador de miles y con el decimal de la
   moneda, para que se pueda copiar tal cual en el campo. */
function sinMiles(valor, moneda) {
  return new Intl.NumberFormat(moneda === "BRL" ? "pt-BR" : "en-US", {
    useGrouping: false, minimumFractionDigits: 0, maximumFractionDigits: 2,
  }).format(Number(valor));
}
/* Un rotulo que va a media frase: «Más viáticos» → «más viáticos». */
const aMedia = (texto) => texto.charAt(0).toLocaleLowerCase() + texto.slice(1);

/* ============================================================ la entrada */

export async function pantallaPropuesta(main, cual) {
  const cat = await catalogos();
  if (cual === "nueva") return armar(main, cat, null);
  const d = await api.get(`/cotizaciones/propuesta/${cual}`);
  if (d.se_edita) return armar(main, cat, d);
  return detalle(main, cat, d);
}

/* Lo que cada renglon escoge: un rol, una unidad o un paquete de la
   lista, en una sola lista desplegable. */
function claveDe(p) {
  if (p.tipo === "paquete") return `paquete:${p.perfil_id}:${p.categoria_id}`;
  return p.tipo === "recurso" ? `recurso:${p.perfil_id}` : `vehiculo:${p.categoria_id}`;
}

function deClave(valor) {
  const [tipo, a, b] = (valor || "").split(":");
  if (tipo === "paquete") return { tipo, perfil_id: Number(a), categoria_id: Number(b) };
  if (tipo === "recurso") return { tipo, perfil_id: Number(a), categoria_id: null };
  if (tipo === "vehiculo") return { tipo, perfil_id: null, categoria_id: Number(a) };
  return null;
}

/* ============================================================ armarla */

async function armar(main, cat, d) {
  const e = {
    id: d ? d.id : null, folio: d ? d.folio : null, version: d ? d.version : 1,
    cliente_id: d ? (d.cliente_id ? String(d.cliente_id) : NUEVA) : "",
    prospecto: d ? (d.prospecto || "") : "",
    pais_id: d ? d.pais_id : null,
    solicitante_id: d ? (d.solicitante_id ? String(d.solicitante_id) : OTRA) : "",
    nombre: d ? (d.solicitante_nombre || "") : "",
    apellidos: d ? (d.solicitante_apellidos || "") : "",
    correo: d ? (d.solicitante_correo || "") : "",
    telefono: d ? (d.solicitante_telefono || "") : "",
    consultor_id: d && d.consultor_id ? String(d.consultor_id) : "",
    plaza_id: d && d.plaza_id ? String(d.plaza_id) : "",
    tipo_servicio: d ? (d.tipo_servicio || "") : t("pro_tipo_omision"),
    valida_hasta: d && d.valida_hasta ? d.valida_hasta : finDeAnio(),
    idioma: d ? (d.idioma || "es") : "",
    con_iva: d ? d.con_iva : true,
    inicio: d ? (d.inicio || "") : "",
    dias_servicio: d ? (d.dias_servicio || "lunes_viernes") : "lunes_viernes",
    viaticos: d ? d.viaticos : "aparte",
    horas_jornada: d && d.horas_jornada !== null ? String(d.horas_jornada) : "",
    hora_presentacion: d ? (d.hora_presentacion || "") : "",
    precio_hora_extra: d && d.precio_hora_extra !== null ? String(d.precio_hora_extra) : "",
    introduccion: d ? (d.introduccion || "") : "",
    alcance: d ? (d.alcance || "") : "",
    motivo: d ? (d.motivo || "") : "",
    especial_motivo: d && d.especial ? (d.especial.motivo || "") : "",
    posiciones: d ? d.posiciones.map(p => ({
      clave: claveDe(p), cantidad: p.cantidad,
      precio_mes: p.especial ? String(p.precio_mes) : "",
      descripcion: p.descripcion || "" })) : [],
  };
  let guardado = d;         // lo ultimo que dijo el servidor de lo guardado
  let info = null;          // la lista de implantados del cliente
  let ultimo = null;        // la ultima vista previa buena
  let enviados = [];        // que renglon de la pantalla es cada precio
  let turno = 0;
  let espera = null;
  const puedeEspecial = tiene(sesion.usuario, ESPECIAL);

  const caja = h("div");
  main.append(
    h("h1", {}, t("pro_titulo")),
    h("p", { clase: "sub" }, !e.folio ? t("pro_sub_nueva")
      : d && d.consultor ? reemplazar(t("ctz_sub_borrador_de"), { f: e.folio, v: e.version, c: d.consultor })
        : reemplazar(t("ctz_sub_borrador"), { f: e.folio, v: e.version })),
    caja);

  /* ---------------------------------------------------- 1: para quien */
  const paisDe = (id) => cat.paises.find(p => String(p.id) === String(id));
  const clienteDe = (id) => cat.clientes.find(c => String(c.id) === String(id));

  /* El cliente, por pais (seccion 125), como en la cotizacion: una
     pestana por pais arriba de «Cliente»; la empresa que todavia no esta
     en Odoo es del pais de la pestana. La que ya existe abre en el suyo. */
  if (!e.pais_id) e.pais_id = paisDeArranque(cat);
  const pestanas = h("div");
  const cajaCliente = h("div");
  function pintarCliente() {
    pestanas.replaceChildren(pestanasDeClientes(cat, e.pais_id, cambiarPais) || "");
    const sel = lista("cliente_id", [
      { valor: "", texto: t("ctz_escoge_cliente") },
      { valor: NUEVA, texto: t("ctz_empresa_no_odoo") },
      ...clientesDelPais(cat, e.pais_id).map(c => ({ valor: c.id, texto: c.nombre }))],
    { onchange: async () => {
      if (sel.value === e.cliente_id) return;
      e.cliente_id = sel.value;
      e.solicitante_id = "";
      await alCambiarCliente();
    } });
    sel.value = e.cliente_id;
    cajaCliente.replaceChildren(listaBuscable(sel, t("buscar_cliente")));
  }
  async function cambiarPais(paisId) {
    e.pais_id = Number(paisId);
    recordarPais(paisId);
    const c = e.cliente_id && e.cliente_id !== NUEVA ? clienteDe(e.cliente_id) : null;
    if (c && String(c.pais_id) !== String(paisId)) {
      e.cliente_id = "";
      e.solicitante_id = "";
    }
    pintarCliente();
    await alCambiarCliente();
  }
  pintarCliente();
  const prospecto = entrada("prospecto", { value: e.prospecto, maxlength: "160",
    "data-crudo": "", placeholder: t("ctz_empresa_nombre"),
    oninput: () => {
      e.prospecto = prospecto.value;
      if (info) lineaLista.replaceChildren(...pintarLista(true));
      recalcular();
    } });
  const cajaProspecto = h("div", { clase: "rejilla dos" },
    campo(t("ctz_empresa"), prospecto, { obligatorio: true }));
  const lineaLista = h("p", { clase: "chico gris", style: "margin:2px 0 10px" });

  const selQuien = h("select", { onchange: () => {
    e.solicitante_id = selQuien.value; pintarQuien(); recalcular();
  } });
  const campoQuien = campo(t("ctz_quien_solicita"), selQuien, { obligatorio: true });
  const quienOtra = h("div", { clase: "rejilla cuatro", style: "margin-top:4px" });
  const nombre = entrada("nombre", { value: e.nombre, maxlength: "160",
    oninput: () => { e.nombre = nombre.value; revisar(); recalcular(); } });
  const apellidos = entrada("apellidos", { value: e.apellidos, maxlength: "160",
    oninput: () => { e.apellidos = apellidos.value; recalcular(); } });
  const correo = entrada("correo", { type: "email", value: e.correo, maxlength: "160",
    oninput: () => { e.correo = correo.value; } });
  const telefono = entrada("telefono", { type: "tel", value: e.telefono, maxlength: "40",
    oninput: () => { e.telefono = telefono.value; } });
  quienOtra.append(campo(t("ctz_nombre"), nombre, { obligatorio: true }),
                   campo(t("ctz_apellidos"), apellidos), campo(t("ctz_correo"), correo),
                   campo(t("ctz_telefono"), telefono));

  const consultor = listaDeConsultores(cat);
  if (e.consultor_id) consultor.value = e.consultor_id;
  e.consultor_id = consultor.value;
  consultor.addEventListener("change", () => {
    e.consultor_id = consultor.value; revisar(); recalcular();
  });

  const selPlaza = h("select", { onchange: () => {
    e.plaza_id = selPlaza.value; revisar(); recalcular();
  } });
  const tipo = entrada("tipo", { value: e.tipo_servicio, maxlength: "120", "data-crudo": "",
    oninput: () => { e.tipo_servicio = tipo.value; recalcular(); } });
  const valida = entrada("valida", { type: "date", value: e.valida_hasta, min: hoyLocal(),
    onchange: () => { e.valida_hasta = valida.value; revisar(); } });
  const selIdioma = lista("idioma", ["es", "en", "pt"].map(i => ({ valor: i, texto: t(IDIOMA_PDF[i]) })),
    { onchange: () => { e.idioma = selIdioma.value; recalcular(); } });
  const inicio = entrada("inicio", { type: "date", value: e.inicio,
    onchange: () => { e.inicio = inicio.value; recalcular(); } });
  const sinIva = h("input", { type: "checkbox",
    onchange: () => { e.con_iva = !sinIva.checked; recalcular(); } });
  sinIva.checked = !e.con_iva;

  const plazasDelPais = () => cat.plazas.filter(p => String(p.pais_id) === String(e.pais_id)
                                                     && p.activo !== false);
  function pintarPlazas() {
    const deAqui = plazasDelPais();
    if (e.plaza_id && !deAqui.some(p => String(p.id) === String(e.plaza_id))) e.plaza_id = "";
    selPlaza.replaceChildren(h("option", { value: "" }, t("ctz_escoge_ciudad")),
      ...deAqui.map(p => h("option", { value: String(p.id) }, p.nombre)));
    selPlaza.value = e.plaza_id;
  }

  function pintarQuien() {
    const nueva = e.cliente_id === NUEVA;
    const contactos = (info && info.solicitantes) || [];
    selQuien.replaceChildren(
      h("option", { value: "" }, t("ctz_escoge_quien")),
      ...contactos.map(s => h("option", { value: String(s.id) },
        s.correo ? `${s.completo || s.nombre} · ${s.correo}` : (s.completo || s.nombre))),
      h("option", { value: OTRA }, t("ctz_otra_persona")));
    if (nueva) e.solicitante_id = OTRA;
    selQuien.value = e.solicitante_id || "";
    campoQuien.hidden = nueva || !e.cliente_id;
    quienOtra.hidden = e.solicitante_id !== OTRA;
    revisar();
  }

  async function alCambiarCliente() {
    const nueva = e.cliente_id === NUEVA;
    cajaProspecto.hidden = !nueva;
    if (!nueva && e.cliente_id) {
      const c = clienteDe(e.cliente_id);
      e.pais_id = c ? c.pais_id : e.pais_id;
    }
    if (nueva && !e.pais_id) {
      e.pais_id = (cat.paises.find(p => p.codigo === "MX") || cat.paises[0] || {}).id;
    }
    if (!e.idioma || !d) {
      const p = paisDe(e.pais_id);
      e.idioma = (p && p.idioma) || "es";
    }
    selIdioma.value = e.idioma;
    pintarPlazas();
    info = null;
    lineaLista.replaceChildren();
    if (e.cliente_id && e.pais_id) {
      try {
        const qs = nueva ? `pais_id=${e.pais_id}` : `cliente_id=${e.cliente_id}`;
        info = await api.get(`/cotizaciones/propuesta/lista-de-precios?${qs}`);
        lineaLista.append(...pintarLista(nueva));
      } catch (err) {
        lineaLista.append(aviso(err.message, "grave"));
      }
    }
    if (info && !e.posiciones.length) {
      e.posiciones.push({ clave: "", cantidad: 1, precio_mes: "", descripcion: "" });
    }
    pintarQuien();
    pintarPosiciones();
    pintarModalidad();
    recalcular();
  }

  /* «Precios de la lista de implantados Volvo Implantado 2026 (MXN).» O
     por que se escriben: la empresa nueva, o el cliente sin lista. Si el
     nombre ya trae la moneda, «Amazon Implantados (USD)», no se repite. */
  function pintarLista(nueva) {
    if (info.lista) {
      const [antes, despues] = t("pro_precios_de").split("{l}");
      const yaLaDice = (info.lista.nombre || "").includes(`(${info.lista.moneda})`);
      return [antes, h("b", {}, info.lista.nombre),
              reemplazar(yaLaDice ? (despues || "").replace(" ({m})", "") : (despues || ""),
                         { m: info.lista.moneda })];
    }
    return [reemplazar(t(nueva ? "pro_sin_lista_nueva" : "pro_sin_lista_cliente"), {
      e: nueva ? (e.prospecto || t("ctz_empresa")) : ((clienteDe(e.cliente_id) || {}).nombre || "") })];
  }

  const paraQuien = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctz_para_quien"), "ay_pro_para_quien", { style: "margin:0" }),
    pestanas,
    h("div", { clase: "rejilla tres", style: "margin-top:12px" },
      campo(t("ctz_cliente"), cajaCliente, { obligatorio: true }),
      campoQuien,
      campo(t("ctz_quien_firma"), consultor, { obligatorio: true })),
    cajaProspecto, quienOtra, lineaLista,
    h("div", { clase: "rejilla tres" },
      campo(t("pro_ciudad"), selPlaza, { obligatorio: true }),
      campo(t("ctz_tipo_servicio"), tipo),
      campo(t("ctz_valida_hasta"), valida, { obligatorio: true })),
    h("div", { clase: "rejilla tres" },
      campo(t("ctz_idioma_pdf"), selIdioma),
      h("div", {}, campo(t("pro_inicio"), inicio),
        h("div", { clase: "chico gris", style: "margin-top:-6px" }, t("pro_inicio_pie"))),
      h("div", { clase: "campo" }, h("label", {}, " "),
        h("label", { clase: "opcion", style: "margin-top:6px" }, sinIva, t("pro_sin_iva")))));

  /* ---------------------------------------------------- 2: lo que lleva */
  const cuerpoTabla = h("tbody");
  const avisoEspecial = h("div");
  const sugerencias = h("div");
  const base = () => (info && info.bases ? info.bases[e.dias_servicio] : 22);
  const columnaMes = h("th", { clase: "der" });

  /* Con mas viaticos, el paquete de una lista que trae los gastos no va
     (la regla de la cotizacion del eventual, seccion 115). */
  const paquetesQueVan = () => (info && info.lista && info.lista.paquetes_con_viaticos
                                && e.viaticos !== "incluidos" ? [] : (info ? info.paquetes : []));

  function opciones() {
    if (!info) return [];
    const grupo = (titulo, cosas) => (cosas.length
      ? [h("optgroup", { label: titulo }, ...cosas.map(([valor, texto]) =>
        h("option", { value: valor }, texto)))] : []);
    return [
      h("option", { value: "" }, t("pro_escoge")),
      ...grupo(t("pro_grupo_roles"), info.roles.map(r => [`recurso:${r.id}`, r.producto || r.nombre])),
      ...grupo(t("pro_grupo_unidades"), info.unidades.map(u => [`vehiculo:${u.id}`, u.producto || u.nombre])),
      ...grupo(t("pro_grupo_paquetes"), paquetesQueVan().map(p => [
        `paquete:${p.perfil_id}:${p.categoria_id}`, p.producto || p.nombre])),
    ];
  }

  /* Las celdas que cambian con cada vista previa, sin repintar la fila:
     repintar mientras alguien teclea un precio le quita el cursor. */
  const celdas = [];

  function filaDePosicion(p, i) {
    const cantidad = h("input", { type: "number", min: "0", max: "20", step: "1",
      value: String(p.cantidad), style: "width:64px;margin:0",
      oninput: () => { p.cantidad = Number(cantidad.value || 0); recalcular(); } });
    const escoger = h("select", { style: "width:100%;margin:0",
      onchange: () => { p.clave = escoger.value; recalcular(); revisar(); } }, ...opciones());
    escoger.value = p.clave;
    if (info && p.clave && escoger.value !== p.clave) {
      /* El paquete que ya no va con mas viaticos --la lista lo trae con
         los gastos dentro--: se escoge otra cosa. */
      escoger.value = "";
      p.clave = "";
    }
    const descripcion = entrada("descripcion", { value: p.descripcion, maxlength: "200",
      "data-crudo": "", clase: "pro-descripcion",
      oninput: () => { p.descripcion = descripcion.value; recalcular(); } });
    /* Vacio, el PDF dice el nombre de lo escogido: eso es el ejemplo. */
    const ejemplo = () => {
      const o = escoger.value ? escoger.selectedOptions[0] : null;
      descripcion.placeholder = o ? reemplazar(t("pro_como_lo_lee_de"), { p: o.textContent })
        : t("pro_como_lo_lee");
    };
    escoger.addEventListener("change", ejemplo);
    ejemplo();
    const mes = h("input", { type: "text", inputmode: "decimal", value: p.precio_mes,
      clase: "pro-mes", oninput: () => { p.precio_mes = mes.value; recalcular(); } });
    const dia = h("td", { clase: "der num" }, "—");
    const marca = h("td");
    celdas[i] = { dia, marca, mes };
    return h("tr", {},
      h("td", { style: "width:80px" }, cantidad),
      h("td", {}, escoger, descripcion),
      dia,
      h("td", { clase: "der" }, mes),
      marca,
      h("td", {}, h("button", { clase: "claro chico", type: "button", title: t("cot_quitar"),
        "aria-label": t("cot_quitar"),
        onclick: () => { e.posiciones.splice(i, 1); pintarPosiciones(); recalcular(); } }, "×")));
  }

  function pintarPosiciones() {
    celdas.length = 0;
    columnaMes.textContent = reemplazar(t("pro_col_al_mes"), { n: base() });
    cuerpoTabla.replaceChildren(...e.posiciones.map(filaDePosicion));
    pintarPreciosDeFilas();
  }

  function pintarPreciosDeFilas() {
    const moneda = ultimo ? ultimo.moneda : (info ? info.moneda : "MXN");
    e.posiciones.forEach((p, i) => {
      const c = celdas[i];
      if (!c) return;
      const k = enviados.indexOf(i);
      const x = ultimo && k >= 0 ? ultimo.posiciones[k] : null;
      c.mes.placeholder = x && x.lista_precio_mes !== null
        ? sinMiles(x.lista_precio_mes, moneda) : t("pro_escribe_precio");
      c.dia.replaceChildren(x && x.precio_dia !== null ? dinero(x.precio_dia, moneda) : "—");
      /* El mensual que la lista trae por mes, tal cual (seccion 123). */
      c.marca.replaceChildren(!x ? "" : x.especial ? etiqueta(t("pro_especial"), "alerta")
        : x.precio_mes !== null ? h("span", { clase: "chico gris" },
                                    t(x.lista_por_mes ? "pro_de_la_lista_mes" : "pro_de_la_lista"))
        : "");
    });
  }

  const tarjetaLleva = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("pro_lleva"), "ay_pro_lleva", { style: "margin:0" }),
    h("p", { clase: "chico gris", style: "margin:8px 0 0" }, t("pro_lleva_pie")),
    h("table", { clase: "lista", style: "margin-top:10px" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("cot_col_cant")), h("th", {}, t("pro_col_que")),
        h("th", { clase: "der" }, t("pro_col_por_dia")), columnaMes,
        h("th", {}, ""), h("th", {}, ""))),
      cuerpoTabla),
    h("div", { clase: "acciones", style: "margin:10px 0 0" },
      h("button", { clase: "claro chico", type: "button", onclick: () => {
        e.posiciones.push({ clave: "", cantidad: 1, precio_mes: "", descripcion: "" });
        pintarPosiciones();
      } }, t("pro_otro_renglon"))),
    sugerencias, avisoEspecial);

  /* ---------------------------------------------------- 3: modalidad y horario */
  const modalidad = h("div", { clase: "bloque-radio" });
  const viaticos = h("div", { clase: "bloque-radio" });
  function pintarModalidad() {
    const radio = (grupo, valor, actual, texto, pie, alCambiar) => {
      const control = h("input", { type: "radio", name: `pro_${grupo}`, value: valor,
        style: "margin-top:3px", onchange: () => alCambiar(valor) });
      control.checked = actual === valor;
      return h("label", { clase: "opcion", style: "margin:0 0 6px;align-items:flex-start" },
        control, h("span", {}, texto,
          pie ? h("span", { clase: "chico gris", style: "font-weight:400" }, ` · ${pie}`) : null));
    };
    modalidad.replaceChildren(...MODALIDADES.map(([valor, texto, pie]) => radio(
      "modalidad", valor, e.dias_servicio, t(texto), t(pie),
      (v) => { e.dias_servicio = v; pintarPosiciones(); recalcular(); })));
    viaticos.replaceChildren(
      radio("viaticos", "aparte", e.viaticos, t("pro_viaticos_aparte"), t("pro_viaticos_aparte_pie"),
        (v) => { e.viaticos = v; pintarPosiciones(); recalcular(); }),
      radio("viaticos", "incluidos", e.viaticos, t("pro_viaticos_incluidos"),
        t("pro_viaticos_incluidos_pie"),
        (v) => { e.viaticos = v; pintarPosiciones(); recalcular(); }));
  }
  const horas = h("input", { type: "number", min: "1", max: "24", step: "0.5",
    value: e.horas_jornada, clase: "num",
    oninput: () => { e.horas_jornada = horas.value; recalcular(); } });
  const horasPie = h("div", { clase: "chico gris", style: "margin-top:4px" });
  const hora = entrada("hora", { type: "time", value: e.hora_presentacion,
    onchange: () => { e.hora_presentacion = hora.value; } });
  const diaAdicional = h("div", { clase: "pro-cifra-chica" }, "—");
  const diaAdicionalPie = h("div", { clase: "chico gris", style: "margin-top:4px" });
  const horaExtra = h("input", { type: "text", inputmode: "decimal", value: e.precio_hora_extra,
    clase: "num", oninput: () => { e.precio_hora_extra = horaExtra.value; recalcular(); } });
  const horaExtraPie = h("div", { clase: "chico gris", style: "margin-top:4px" });

  const tarjetaModalidad = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("pro_modalidad_titulo"), "ay_pro_modalidad", { style: "margin:0" }),
    h("div", { clase: "rejilla dos", style: "margin-top:12px" },
      h("div", { clase: "campo" }, h("label", {}, t("pro_modalidad")), modalidad),
      h("div", { clase: "campo" }, h("label", {}, t("pro_viaticos")), viaticos)),
    h("div", { clase: "rejilla cuatro" },
      h("div", { clase: "campo" }, h("label", {}, t("pro_jornada")), horas, horasPie),
      h("div", { clase: "campo" }, h("label", {}, t("pro_hora")), hora,
        h("div", { clase: "chico gris", style: "margin-top:4px" }, t("pro_hora_pie"))),
      h("div", { clase: "campo" }, h("label", {}, t("pro_dia_adicional")), diaAdicional,
        diaAdicionalPie),
      h("div", { clase: "campo" }, h("label", {}, t("pro_hora_extra")), horaExtra,
        horaExtraPie)),
    h("p", { clase: "chico gris", style: "margin:0" }, t("pro_modalidad_pie")));

  /* ---------------------------------------------------- 4: lo que lee */
  const intro = h("textarea", { rows: "3", maxlength: "2000",
    oninput: () => { e.introduccion = intro.value; pintarTextos(); } });
  intro.value = e.introduccion;
  const cambiarIntro = h("button", { clase: "enlace chico", type: "button",
    onclick: () => {
      intro.value = (ultimo && ultimo.introduccion_auto) || "";
      e.introduccion = intro.value;
      pintarTextos();
      intro.focus();
    } }, t("ctz_intro_cambiar"));
  const volverIntro = h("button", { clase: "enlace chico", type: "button",
    onclick: () => { intro.value = ""; e.introduccion = ""; pintarTextos(); } },
  t("ctz_intro_volver"));
  /* El alcance sale de Catalogos, el de cada rol que lleva; se puede
     cambiar para esta propuesta. Vaciarlo lo regresa al de Catalogos. */
  const alcance = h("textarea", { rows: "5", maxlength: "6000",
    oninput: () => { e.alcance = alcance.value; pintarTextos(); } });
  alcance.value = e.alcance;
  const cambiarAlcance = h("button", { clase: "enlace chico", type: "button",
    onclick: () => {
      alcance.value = (ultimo && ultimo.alcance_auto) || "";
      e.alcance = alcance.value;
      pintarTextos();
      alcance.focus();
    } }, t("pro_alcance_cambiar"));
  const volverAlcance = h("button", { clase: "enlace chico", type: "button",
    onclick: () => { alcance.value = ""; e.alcance = ""; pintarTextos(); } },
  t("pro_alcance_volver"));
  function pintarTextos() {
    const propia = Boolean(e.introduccion.trim());
    intro.placeholder = (ultimo && ultimo.introduccion_auto) || t("pro_intro_espera");
    cambiarIntro.hidden = propia || !(ultimo && ultimo.introduccion_auto);
    volverIntro.hidden = !propia;
    const suyo = Boolean(e.alcance.trim());
    alcance.placeholder = (ultimo && ultimo.alcance_auto) || t("pro_alcance_espera");
    cambiarAlcance.hidden = suyo || !(ultimo && ultimo.alcance_auto);
    volverAlcance.hidden = !suyo;
  }
  const motivo = h("textarea", { rows: "2", maxlength: "300", placeholder: t("pro_motivo_ayuda"),
    oninput: () => { e.motivo = motivo.value; revisar(); } });
  motivo.value = e.motivo;
  const faltaCatalogo = h("div");
  const tarjetaTexto = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctz_lo_que_lee"), "ay_pro_texto", { style: "margin:0" }),
    h("div", { clase: "campo", style: "margin-top:12px" },
      h("label", {}, t("ctz_introduccion"), " ",
        h("span", { clase: "chico gris", style: "font-weight:500" }, t("ctz_intro_pie"))),
      intro, h("div", {}, cambiarIntro, volverIntro)),
    h("div", { clase: "campo" },
      h("label", {}, t("pro_alcance"), " ",
        h("span", { clase: "chico gris", style: "font-weight:500" }, t("pro_alcance_pie"))),
      alcance, h("div", {}, cambiarAlcance, volverAlcance)),
    e.version > 1 ? campo(t("ctz_motivo"), motivo, { obligatorio: true }) : null,
    h("p", { clase: "chico gris", style: "margin:4px 0 0" }, t("pro_condiciones_salen")),
    faltaCatalogo);

  /* ---------------------------------------------------- el precio especial */
  const motivoEspecial = h("textarea", { rows: "2", maxlength: "400",
    placeholder: t("pro_especial_motivo_ayuda"),
    oninput: () => { e.especial_motivo = motivoEspecial.value; revisar(); } });
  motivoEspecial.value = e.especial_motivo;
  const estadoEspecial = h("div");
  const decision = h("div");
  const tarjetaEspecial = h("div", { clase: "tarjeta pro-especial", hidden: "hidden" },
    conAyuda("h3", t("pro_especial_titulo"), "ay_pro_especial", { style: "margin:0" }),
    h("p", { clase: "chico gris", style: "margin:8px 0 10px" }, t("pro_especial_pie")),
    campo(t("pro_especial_motivo"), motivoEspecial, { obligatorio: true }),
    estadoEspecial, decision);

  /* Si lo que se ve tiene su visto bueno: el de lo guardado, y que los
     precios de la pantalla sean esos mismos. */
  const especialVigente = () => Boolean(
    guardado && guardado.especial && guardado.especial.vigente && ultimo
    && guardado.huella === ultimo.huella);

  function pintarEspecial() {
    const hace = Boolean(ultimo && ultimo.especial);
    tarjetaEspecial.hidden = !hace;
    avisoEspecial.replaceChildren(hace ? h("div", { clase: "aviso alerta", style: "margin:12px 0 0" },
      h("b", {}, t("pro_especial"), ":"), " ", t("pro_especial_aviso")) : "");
    estadoEspecial.replaceChildren();
    decision.replaceChildren();
    if (!hace) return;
    const x = guardado && guardado.especial ? guardado.especial : {};
    const cambiaron = guardado && ultimo && guardado.huella !== ultimo.huella;
    if (x.estatus === "autorizado" && !cambiaron) {
      estadoEspecial.append(aviso(reemplazar(t("pro_especial_autorizado"), {
        q: x.por || "—", f: fechaCorta(diaDe(x.en), false),
        n: x.nota ? ` «${x.nota}»` : "" }), "ok"));
    } else if (x.estatus === "pedido") {
      estadoEspecial.append(aviso(reemplazar(t("pro_especial_pedido"), {
        q: x.pedido_por || "—", f: fechaCorta(diaDe(x.pedido_en), false) }), "info"));
    } else if (x.estatus === "rechazado") {
      estadoEspecial.append(aviso(reemplazar(t("pro_especial_rechazado"), {
        q: x.por || "—", n: x.nota || "—" }), "grave"));
    } else if (x.estatus === "autorizado" && cambiaron) {
      estadoEspecial.append(aviso(t("pro_especial_cambio"), "alerta"));
    }
    /* Direccion de operaciones decide aqui mismo, con lo guardado. */
    if (puedeEspecial && x.estatus === "pedido" && !cambiaron && guardado) {
      const nota = entrada("nota", { maxlength: "400", "data-crudo": "",
                                     placeholder: t("pro_especial_nota") });
      const decidir = async (autoriza) => {
        if (!autoriza && !nota.value.trim()) { mensaje(t("pro_especial_falta_nota"), "alerta"); return; }
        try {
          guardado = await api.post(`/cotizaciones/propuesta/${e.id}/especial/decidir`, {
            autoriza, nota: nota.value.trim() || null, huella: guardado.huella });
          mensaje(t(autoriza ? "pro_especial_lo_autorizaste" : "pro_especial_no_lo_autorizaste"),
                  autoriza ? "ok" : "alerta");
          pintarEspecial(); revisar();
        } catch (err) { mensaje(err.message, "grave"); }
      };
      decision.append(h("div", { style: "margin-top:10px" }, nota),
        h("div", { clase: "acciones", style: "margin:8px 0 0" },
          h("button", { type: "button", onclick: () => decidir(true) }, t("dir_autorizar")),
          h("button", { type: "button", clase: "claro", onclick: () => decidir(false) },
            t("pro_no_autorizar"))));
    }
  }

  /* ---------------------------------------------------- el pie */
  const rotuloTotal = h("div", { clase: "chico gris" });
  const total = h("div", { clase: "cifra" }, "—");
  const pieTotal = h("div", { clase: "chico gris" });
  const avisoPrecios = h("div");
  const queFalta = h("div", { clase: "chico", style: "margin-top:6px;color:var(--alerta);text-align:right" });
  const notaFirma = h("div", { clase: "chico gris", style: "margin-top:4px;text-align:right" });
  const botonVer = h("button", { type: "button", clase: "claro", onclick: () => ver() },
    t("ctz_ver_pdf"));
  const botonGuardar = h("button", { type: "button", clase: "claro", onclick: () => guardar() },
    t("ctz_guardar"));
  const botonPedir = h("button", { type: "button", onclick: () => pedir() });
  const botonMandar = h("button", { type: "button", onclick: () => mandar() }, t("ctz_mandar"));
  /* «Descartar este borrador» (seccion 131, decision 1), como en la
     cotizacion: solo sobre un borrador ya guardado. */
  const botonDescartar = !e.id ? null : h("button", { type: "button", clase: "claro",
    onclick: () => descartar() }, t("ctz_descartar"));
  const pie = h("div", { clase: "tarjeta" }, avisoPrecios,
    h("div", { clase: "cot-pie", style: "margin:0;border:0;padding:0" },
      h("div", {}, rotuloTotal, total, pieTotal),
      h("div", {}, h("div", { clase: "acciones", style: "margin:0;justify-content:flex-end" },
        botonVer, botonGuardar, botonPedir, botonMandar, botonDescartar), queFalta, notaFirma)));

  async function descartar() {
    const pregunta = e.version > 1
      ? reemplazar(t("pro_seguro_descartar_v"), { v: e.version, a: e.version - 1 })
      : reemplazar(t("pro_seguro_descartar_1"), { f: e.folio });
    if (!confirm(pregunta)) return;
    botonDescartar.disabled = true;
    try {
      const r = await api.post(`/cotizaciones/propuesta/${e.id}/descartar`);
      mensaje(r.vuelve ? reemplazar(t("ctz_descartada_vuelve"), { v: r.vuelve.version })
                       : reemplazar(t("pro_descartada_eliminada"), { f: e.folio }), "ok");
      irA(r.vuelve ? `#/propuesta/${r.vuelve.id}` : "#/cotizaciones");
    } catch (err) {
      mensaje(err.message, "grave");
      botonDescartar.disabled = false;
    }
  }

  caja.append(paraQuien, tarjetaLleva, tarjetaModalidad, tarjetaTexto, tarjetaEspecial, pie);

  /* ---------------------------------------------------- lo que se manda */
  function cuerpo() {
    const nueva = e.cliente_id === NUEVA;
    const otra = nueva || e.solicitante_id === OTRA;
    const moneda = ultimo ? ultimo.moneda : (info ? info.moneda : "MXN");
    enviados = [];
    const posiciones = [];
    e.posiciones.forEach((p, i) => {
      const elegido = deClave(p.clave);
      if (!elegido || !(Number(p.cantidad) > 0)) return;
      enviados.push(i);
      posiciones.push({ ...elegido, cantidad: Number(p.cantidad),
                        precio_mes: montoEscrito(p.precio_mes, moneda),
                        descripcion: p.descripcion.trim() || null });
    });
    return {
      cliente_id: nueva || !e.cliente_id ? null : Number(e.cliente_id),
      prospecto: nueva ? e.prospecto : null,
      pais_id: e.pais_id ? Number(e.pais_id) : null,
      solicitante_id: !otra && e.solicitante_id ? Number(e.solicitante_id) : null,
      solicitante_nombre: otra ? e.nombre : null,
      solicitante_apellidos: otra ? e.apellidos : null,
      solicitante_correo: otra ? e.correo : null,
      solicitante_telefono: otra ? e.telefono : null,
      consultor_id: e.consultor_id ? Number(e.consultor_id) : null,
      plaza_id: e.plaza_id ? Number(e.plaza_id) : null,
      tipo_servicio: e.tipo_servicio || null,
      introduccion: e.introduccion.trim() || null,
      valida_hasta: e.valida_hasta || null,
      idioma: e.idioma || null,
      con_iva: e.con_iva,
      inicio: e.inicio || null,
      dias_servicio: e.dias_servicio,
      viaticos: e.viaticos,
      horas_jornada: numero(e.horas_jornada),
      hora_presentacion: e.hora_presentacion || null,
      alcance: e.alcance.trim() || null,
      precio_hora_extra: montoEscrito(e.precio_hora_extra, moneda),
      especial_motivo: e.especial_motivo.trim() || null,
      motivo: e.version > 1 ? (e.motivo || null) : null,
      posiciones,
    };
  }

  function faltante() {
    const nueva = e.cliente_id === NUEVA;
    if (!e.cliente_id) return t("ctz_falta_cliente");
    if (nueva && !e.prospecto.trim()) return t("ctz_falta_empresa");
    if (!nueva && !e.solicitante_id) return t("ctz_falta_quien");
    if ((nueva || e.solicitante_id === OTRA) && !e.nombre.trim()) return t("ctz_falta_quien");
    if (!e.consultor_id) return t("ctz_falta_firma");
    if (!e.plaza_id) return t("pro_falta_ciudad");
    if (!e.valida_hasta) return t("ctz_falta_valida");
    if (!ultimo || !ultimo.posiciones.length) return t("pro_falta_lleva");
    if (!ultimo.personas) return t("pro_falta_persona");
    if (ultimo.faltan_precios.length) {
      return reemplazar(t("pro_falta_precio"), { q: ultimo.faltan_precios.join(", ") });
    }
    if (e.version > 1 && !e.motivo.trim()) return t("ctz_falta_motivo");
    if (ultimo.especial && !e.especial_motivo.trim()) return t("pro_falta_motivo_especial");
    /* Lo de Catalogos sin lo que no se manda (seccion 130, decision 15). */
    const delPais = ultimo.faltan_textos || [];
    if (e.con_iva !== false && delPais.includes("tasa_iva")) return t("pro_falta_tasa_pais");
    if (delPais.includes("pro_aceptacion")) {
      return reemplazar(t("pro_falta_aceptacion_pais"), { i: t(IDIOMA_PDF[e.idioma] || "ctz_idioma_es") });
    }
    return null;
  }

  function revisar() {
    const falta = faltante();
    const sinCliente = !e.cliente_id || (e.cliente_id === NUEVA && !e.prospecto.trim());
    /* Con precio especial sin su visto bueno, el boton que manda es el
       que lo pide; con el, el de mandarla. */
    const pide = Boolean(ultimo && ultimo.especial && !especialVigente());
    const pendiente = pide && guardado && guardado.especial
      && guardado.especial.estatus === "pedido" && guardado.huella === (ultimo || {}).huella;
    botonPedir.hidden = !pide;
    botonMandar.hidden = pide;
    botonPedir.textContent = t(puedeEspecial ? "pro_autorizar_y_guardar" : "pro_pedir_visto_bueno");
    botonPedir.disabled = Boolean(falta) || pendiente;
    botonMandar.disabled = Boolean(falta);
    queFalta.textContent = falta || (pendiente ? t("pro_esperando_visto_bueno")
      : pide ? t("pro_falta_visto_bueno") : "");
    botonGuardar.disabled = sinCliente;
    botonVer.disabled = sinCliente;
  }

  function recalcular() {
    clearTimeout(espera);
    espera = setTimeout(pedirPrecios, ESPERA_PRECIOS);
  }

  async function pedirPrecios() {
    const mio = ++turno;
    if (!info) { ultimo = null; pintarTodo(); return; }
    try {
      const r = await api.post("/cotizaciones/propuesta/precios", cuerpo());
      if (mio !== turno) return;
      ultimo = r;
      avisoPrecios.replaceChildren();
    } catch (err) {
      if (mio !== turno) return;
      ultimo = null;
      avisoPrecios.replaceChildren(aviso(err.message, "grave"));
    }
    pintarTodo();
  }

  function pintarTodo() {
    pintarPreciosDeFilas();
    pintarSugerencias();
    pintarModalidadCifras();
    pintarTextos();
    pintarEspecial();
    pintarTotal();
    revisar();
  }

  function pintarSugerencias() {
    /* El paquete que la lista cobra al mes dice su mensual (seccion 123). */
    sugerencias.replaceChildren(...((ultimo && ultimo.sugerencias) || []).map(s =>
      h("div", { clase: "aviso info", style: "margin:10px 0 0" },
        s.precio_mes !== null && s.precio_mes !== undefined
          ? reemplazar(t("pro_sugerencia_mes"), { p: s.nombre,
              m: dinero(s.precio_mes, ultimo.moneda) })
          : reemplazar(t("pro_sugerencia"), { p: s.nombre,
              d: dinero(s.precio_dia, ultimo.moneda) }))));
  }

  function pintarModalidadCifras() {
    const moneda = ultimo ? ultimo.moneda : (info ? info.moneda : "MXN");
    const delPais = ultimo ? ultimo.horas_del_pais : (info ? info.horas_del_pais : null);
    horas.placeholder = delPais !== null && delPais !== undefined ? String(delPais) : "";
    horasPie.textContent = delPais !== null && delPais !== undefined
      ? reemplazar(t("pro_jornada_pie"), { h: delPais }) : "";
    if (e.dias_servicio === "todos") {
      diaAdicional.textContent = "—";
      diaAdicionalPie.textContent = t("pro_sin_adicional");
    } else {
      diaAdicional.textContent = ultimo && ultimo.dia_adicional !== null
        ? dinero(ultimo.dia_adicional, moneda) : "—";
      /* Con un mensual que la lista trae por mes, el dia es ese mensual
         entre los dias de la modalidad (seccion 123). */
      const porMes = ultimo && (ultimo.posiciones || []).some(x => x.lista_por_mes && !x.especial
        && (x.tipo === "recurso" || x.tipo === "paquete"));
      diaAdicionalPie.textContent = porMes
        ? reemplazar(t("pro_dia_adicional_pie_mes"), { n: ultimo.base })
        : t("pro_dia_adicional_pie");
    }
    horaExtra.placeholder = ultimo && ultimo.hora_extra_lista !== null
      ? String(ultimo.hora_extra_lista) : "0.00";
    horaExtraPie.replaceChildren(t("pro_hora_extra_pie"),
      ...(ultimo && ultimo.hora_extra_especial ? [" ", etiqueta(t("pro_especial"), "alerta")] : []));
  }

  function pintarTotal() {
    rotuloTotal.textContent = reemplazar(t(e.con_iva ? "pro_total_v_iva" : "pro_total_v_sin"),
                                         { v: e.version });
    faltaCatalogo.replaceChildren();
    notaFirma.textContent = "";
    if (!ultimo || !ultimo.posiciones.length) {
      total.textContent = "—";
      pieTotal.textContent = "";
      return;
    }
    const moneda = ultimo.moneda;
    total.textContent = dinero(ultimo.total, moneda);
    const partes = [
      !e.con_iva ? t("ctz_sin_iva_corto")
        : ultimo.tasa_iva === null ? t("ctz_sin_tasa")
          : reemplazar(t("ctz_mas_iva"), { s: dinero(ultimo.subtotal, moneda),
                                           i: dinero(ultimo.iva, moneda) }),
      ultimo.personas ? reemplazar(t(ultimo.personas === 1 ? "pro_una_persona" : "pro_n_personas"),
                                   { n: ultimo.personas }) : null,
      ultimo.unidades ? reemplazar(t(ultimo.unidades === 1 ? "pro_una_unidad" : "pro_n_unidades"),
                                   { n: ultimo.unidades }) : null,
      t(MODALIDAD_CORTA[e.dias_servicio]),
      e.horas_jornada ? reemplazar(t("pro_n_horas"), { n: e.horas_jornada }) : null,
      t(e.viaticos === "incluidos" ? "pro_viaticos_incluidos" : "pro_viaticos_aparte"),
    ];
    pieTotal.textContent = partes.filter(Boolean).join(" · ");
    const faltan = ultimo.faltan_textos || [];
    if (faltan.length) {
      faltaCatalogo.append(aviso(reemplazar(t("pro_falta_catalogo"), {
        i: t(IDIOMA_PDF[e.idioma] || "ctz_idioma_es"),
        l: [...new Set(faltan.map(k => t(FALTA_TEXTO[k] || "pro_ft_incluye")))].join(", "),
      }), "alerta"));
    }
    if (e.consultor_id && !ultimo.firma) notaFirma.textContent = t("ctz_sin_firma");
  }

  /* ---------------------------------------------------- guardar, pedir y mandar */
  async function guardarYa() {
    const r = e.id ? await api.put(`/cotizaciones/propuesta/${e.id}`, cuerpo())
      : await api.post("/cotizaciones/propuesta", cuerpo());
    if (!e.id) {
      e.id = r.id; e.folio = r.folio;
      history.replaceState(null, "", `#/propuesta/${r.id}`);
    }
    guardado = r;
    if (r.aviso_precios) {
      avisoPrecios.replaceChildren(aviso(reemplazar(t("pro_guardada_sin_precio"),
        { q: r.aviso_precios }), "alerta"));
    }
    return r;
  }

  async function guardar() {
    botonGuardar.disabled = true;
    try {
      const r = await guardarYa();
      mensaje(reemplazar(t("ctz_guardada"), { f: r.folio, v: r.version }), "ok");
    } catch (err) { mensaje(err.message, "grave"); }
    pintarEspecial();
    revisar();
  }

  async function ver() {
    botonVer.disabled = true;
    await abrirPdf(() => `/cotizaciones/propuesta/${e.id}/pdf`, guardarYa);
    revisar();
  }

  /* Pedir el visto bueno guarda primero: direccion autoriza lo guardado.
     Quien lo puede autorizar lo deja autorizado de una vez. */
  async function pedir() {
    if (faltante()) return;
    botonPedir.disabled = true;
    try {
      await guardarYa();
      guardado = await api.post(`/cotizaciones/propuesta/${e.id}/especial`);
      mensaje(t(guardado.especial.estatus === "autorizado" ? "pro_especial_quedo_autorizado"
        : "pro_especial_quedo_pedido"), "ok");
    } catch (err) { mensaje(err.message, "grave"); }
    pintarEspecial();
    revisar();
  }

  async function mandar() {
    if (faltante()) return;
    if (!confirm(t("pro_seguro_mandar"))) return;
    botonMandar.disabled = true;
    botonMandar.textContent = t("ctz_mandando");
    try {
      await guardarYa();
      await api.post(`/cotizaciones/propuesta/${e.id}/enviar`);
    } catch (err) {
      botonMandar.textContent = t("ctz_mandar");
      mensaje(err.message, "grave");
      revisar();
      return;
    }
    try {
      await bajar(`/cotizaciones/propuesta/${e.id}/pdf?bajar=true`);
      mensaje(t("pro_mandada"), "ok");
    } catch (err) {
      mensaje(reemplazar(t("ctz_mandada_sin_pdf"), { m: err.message }), "alerta");
    }
    irA(`#/propuesta/${e.id}`);
  }

  cajaProspecto.hidden = e.cliente_id !== NUEVA;
  pintarPlazas();
  pintarQuien();
  pintarModalidad();
  pintarTotal();
  await alCambiarCliente();
}

/* ============================================================ el detalle */

function lineaDeEstado(d) {
  if (d.estatus === "autorizada") {
    return reemplazar(t("ctz_linea_autorizada"), {
      q: d.autorizada_por || "—", f: fechaCorta(d.autorizada_el, false) });
  }
  if (d.estatus === "rechazada") {
    return reemplazar(t("ctz_linea_rechazada"), { m: d.rechazo_motivo || "—" });
  }
  if (d.estatus === "vencida") {
    return reemplazar(t("ctz_linea_vencida"), { f: fechaCorta(d.valida_hasta, false) });
  }
  if (d.estatus === "sustituida") return t("ctz_linea_sustituida");
  if (d.enviada_en) {
    return reemplazar(t("ctz_linea_enviada"), {
      f: fechaCorta(diaDe(d.enviada_en), false), q: d.enviada_por || "—",
      s: d.solicitante || "—" });
  }
  return t("ctz_linea_borrador");
}

async function detalle(main, cat, d) {
  const tarjeta = h("div", { clase: "tarjeta" });
  main.append(
    h("h1", {}, reemplazar(t("pro_titulo_folio"), { f: d.folio, c: d.cliente })),
    h("p", { clase: "sub" }, reemplazar(t("ctz_version_n"), { v: d.version }), " · ",
      lineaDeEstado(d)),
    tarjeta, tablaDeLoQueLleva(d), tablaDeVersiones(d));
  pintarTarjeta(tarjeta, cat, d);
}

/* El mensual con IVA, desde cuando, la modalidad y la vigencia; y el
   precio especial, si lo lleva, con quien lo autorizo. */
function cifrasDe(d) {
  const moneda = d.moneda;
  return h("div", { clase: "rejilla cuatro", style: "margin-top:12px" },
    h("div", {}, h("div", { clase: "chico gris" }, t(d.iva ? "pro_mensual_con_iva" : "pro_mensual")),
      h("div", { clase: "cifra", style: "font-size:19px" }, dinero(d.total, moneda)),
      h("div", { clase: "chico gris" }, d.iva
        ? reemplazar(t("pro_antes_iva"), { s: dinero(d.subtotal, moneda) })
        : t("ctz_sin_iva_corto"))),
    h("div", {}, h("div", { clase: "chico gris" }, t("pro_desde_titulo")),
      h("b", {}, d.inicio ? fechaCorta(d.inicio) : "—"),
      h("div", { clase: "chico gris" }, d.plaza || "—")),
    h("div", {}, h("div", { clase: "chico gris" }, t("pro_modalidad")),
      h("b", {}, t(MODALIDAD_CORTA[d.dias_servicio] || "pro_mod_lv_corta")),
      h("div", { clase: "chico gris" }, reemplazar(t("pro_jornada_de"), {
        n: d.horas_jornada ?? d.horas_del_pais ?? "—" }))),
    h("div", {}, h("div", { clase: "chico gris" }, t("ctz_col_valida")),
      h("b", {}, fechaCorta(d.valida_hasta)),
      h("div", { clase: "chico gris" },
        t(d.viaticos === "incluidos" ? "pro_viaticos_incluidos" : "pro_viaticos_aparte"))));
}

function lineaEspecial(d) {
  const x = d.especial || {};
  if (!x.necesita || x.estatus !== "autorizado") return null;
  return h("p", { clase: "chico gris", style: "margin:10px 0 0" },
    etiqueta(t("pro_especial"), "alerta"), " ",
    reemplazar(t("pro_especial_lo_autorizo"), {
      q: x.por || "—", f: fechaCorta(diaDe(x.en), false),
      m: x.motivo ? ` «${x.motivo}»` : "" }));
}

function pintarTarjeta(tarjeta, cat, d) {
  const formulario = h("div");
  const descargar = async () => {
    try { await bajar(`/cotizaciones/propuesta/${d.id}/pdf?bajar=true`); }
    catch (err) { mensaje(err.message, "grave"); }
  };
  const acciones = h("div", { clase: "acciones", style: "margin:16px 0 0" },
    ...[
      d.se_autoriza ? h("button", { type: "button",
        onclick: () => formularioAutorizar(tarjeta, cat, d) }, t("ctz_la_autorizo")) : null,
      d.sale_otra ? h("button", { type: "button", clase: "claro", onclick: async (ev) => {
        ev.target.disabled = true;
        try {
          const nueva = await api.post(`/cotizaciones/propuesta/${d.id}/version`);
          location.hash = `#/propuesta/${nueva.id}`;
        } catch (err) { mensaje(err.message, "grave"); ev.target.disabled = false; }
      } }, reemplazar(t("ctz_hacer_version"), { v: d.version + 1 })) : null,
      d.pdf ? h("button", { type: "button", clase: "claro", onclick: descargar },
        t("ctz_bajar_pdf")) : null,
      !d.pdf && d.estatus === "borrador" ? h("button", { type: "button", clase: "claro",
        onclick: () => abrirPdf(() => `/cotizaciones/propuesta/${d.id}/pdf`) },
      t("ctz_ver_pdf")) : null,
      d.comprobante ? h("button", { type: "button", clase: "claro",
        onclick: () => abrirPdf(() => `/cotizaciones/propuesta/${d.id}/comprobante`) },
      t("ctz_ver_comprobante")) : null,
      d.se_autoriza ? h("button", { type: "button", clase: "claro",
        onclick: () => formularioRechazo(formulario, d) }, t("ctz_la_rechazo")) : null,
    ].filter(Boolean));

  /* Su implantado se elimino (seccion 131, decision 2): se vuelve a crear
     con los terminos de la propuesta, o se elimina la propuesta, como la
     cotizacion desde la 126. Antes se quedaba atorada. */
  const recrear = async (ev) => {
    if (!confirm(t("pro_seguro_recrear"))) return;
    ev.target.disabled = true;
    try {
      const r = await api.post(`/cotizaciones/propuesta/${d.id}/servicio`);
      mensaje(reemplazar(t("pro_implantado_creado"), { f: r.folio }), "ok");
      if (r.sin_consultor) mensaje(t("ctz_nacio_sin_consultor"), "alerta");
      irA(`#/implantado/${r.servicio_id}`);
    } catch (err) { mensaje(err.message, "grave"); ev.target.disabled = false; }
  };
  const implantado = d.servicio
    ? h("p", { style: "margin:14px 0 0" }, t("pro_nacio_implantado"), " ",
      h("a", { href: `#/implantado/${d.servicio.id}`, clase: "enlace" }, d.servicio.folio))
    : d.servicio_folio
      ? h("div", { style: "margin:14px 0 0" },
        h("p", { clase: "gris", style: "margin:0" },
          reemplazar(t("ctz_servicio_borrado"), { f: d.servicio_folio })),
        d.se_recrea ? h("p", { clase: "chico", style: "margin:6px 0 0" },
          t("pro_borrado_que_hacer")) : null,
        d.se_recrea ? avisoInicioPasado(d) : null,
        d.se_recrea ? h("div", { clase: "acciones", style: "margin:8px 0 0" },
          h("button", { type: "button", onclick: recrear }, t("pro_recrear_implantado")),
          h("button", { type: "button", clase: "claro",
            onclick: () => formularioEliminar(formulario, d) }, t("pro_eliminar_propuesta")))
          : null)
      : null;
  const vigente = !d.es_ultima
    ? h("p", { clase: "chico gris", style: "margin:12px 0 0" }, t("pro_hay_otra"), " ",
      ...d.versiones.filter(v => v.version === Math.max(...d.versiones.map(x => x.version)))
        .map(v => h("a", { href: `#/propuesta/${v.id}`, clase: "enlace" }, `V${v.version}`)))
    : null;

  tarjeta.replaceChildren(...[
    conAyuda("h3", [t("pro_la_propuesta"), " ", estatusDe(d.estatus)], "ay_pro_estado",
      { style: "margin:0" }),
    cifrasDe(d), lineaEspecial(d), implantado, vigente, acciones, formulario].filter(Boolean));
}

/* Lo que se le cobra al cliente cada mes, y aparte cuando aplique. */
function aparteDe(d) {
  const moneda = d.moneda;
  return [
    d.dia_adicional !== null && d.dias_servicio !== "todos"
      ? reemplazar(t("pro_aparte_dia"), { p: dinero(d.dia_adicional, moneda) }) : null,
    d.hora_extra ? reemplazar(t("pro_aparte_hora"), { p: dinero(d.hora_extra, moneda) }) : null,
    d.viaticos === "aparte" ? t("pro_aparte_viaticos") : null,
  ].filter(Boolean);
}

function tablaDeLoQueLleva(d) {
  const moneda = d.moneda;
  const aparte = aparteDe(d);
  return h("div", { clase: "tarjeta", style: "margin-top:16px" },
    h("h3", { style: "margin:0 0 10px" }, t("pro_lleva_al_mes")),
    h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("cot_col_cant")), h("th", {}, t("pro_col_que")),
        h("th", { clase: "der" }, t("pro_col_mes")),
        h("th", { clase: "der" }, t("cot_col_importe")))),
      h("tbody", {}, ...d.posiciones.map(p => h("tr", {},
        h("td", {}, String(p.cantidad)),
        h("td", {}, p.descripcion || p.producto || p.nombre,
          p.especial ? [" ", etiqueta(t("pro_especial"), "alerta")] : ""),
        h("td", { clase: "der num" }, p.precio_mes === null ? "—" : dinero(p.precio_mes, moneda)),
        h("td", { clase: "der num" }, p.importe === null ? "—" : dinero(p.importe, moneda)))))),
    aparte.length ? h("p", { clase: "chico gris", style: "margin:8px 0 0" },
      `${t("pro_aparte")} ${aparte.join(" · ")}.`) : null);
}

function tablaDeVersiones(d) {
  return h("div", { clase: "tarjeta", style: "margin-top:16px" },
    conAyuda("h3", t("ctz_versiones"), "ay_pro_versiones", { style: "margin:0 0 10px" }),
    h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("ctz_col_version")), h("th", {}, t("ctz_col_estatus")),
        h("th", {}, t("ctz_col_cambio")), h("th", { clase: "der" }, t("pro_col_mensual_iva")),
        h("th", {}, ""))),
      h("tbody", {}, ...d.versiones.slice().sort((a, b) => b.version - a.version).map(v => h("tr", {},
        h("td", {}, v.id === d.id ? h("b", {}, `V${v.version}`)
          : h("a", { href: `#/propuesta/${v.id}`, clase: "enlace" }, `V${v.version}`)),
        h("td", {}, estatusDe(v.estatus)),
        h("td", {}, v.motivo || (v.version === 1 ? t("ctz_primera") : "—")),
        h("td", { clase: "der num" }, dinero(v.total, d.moneda)),
        h("td", {}, v.pdf ? h("button", { clase: "enlace chico", type: "button",
          onclick: async () => {
            try { await bajar(`/cotizaciones/propuesta/${v.id}/pdf?bajar=true`); }
            catch (err) { mensaje(err.message, "grave"); }
          } }, t("ctz_pdf")) : ""))))));
}

/* ------------------------------------------------------------ autorizarla */

/* Como en la cotizacion: la tarjeta se vuelve la forma y Cancelar la
   regresa. Al guardar nace el implantado con la propuesta adentro. */
async function formularioAutorizar(tarjeta, cat, d) {
  const prospecto = !d.cliente_id;
  let contactos = [];
  if (!prospecto) {
    try {
      const info = await api.get(`/cotizaciones/propuesta/lista-de-precios?cliente_id=${d.cliente_id}`);
      contactos = info.solicitantes || [];
    } catch { contactos = []; }
  }
  const opciones = [];
  if (d.solicitante) {
    opciones.push({ valor: d.solicitante,
                    texto: reemplazar(t("ctz_quien_solicita_op"), { n: d.solicitante }) });
  }
  for (const c of contactos) {
    if (c.completo && !opciones.some(o => o.valor === c.completo)) {
      opciones.push({ valor: c.completo, texto: c.completo });
    }
  }
  const otra = entrada("otra", { maxlength: "160", placeholder: t("cot_nombre_otra") });
  const quien = lista("quien", [...opciones, { valor: OTRA, texto: t("cot_otra_persona") }],
    { onchange: () => { otra.hidden = quien.value !== OTRA; } });
  otra.hidden = opciones.length > 0;
  if (!opciones.length) quien.value = OTRA;
  const dia = entrada("dia", { type: "date", value: d.hoy, max: d.hoy });

  const archivo = h("input", { type: "file", accept: "application/pdf,image/png,image/jpeg",
                               hidden: "hidden" });
  const nombreArchivo = h("span", { clase: "chico gris" }, t("ctz_comprobante_tipos"));
  archivo.addEventListener("change", () => {
    nombreArchivo.textContent = archivo.files[0] ? archivo.files[0].name : t("ctz_comprobante_tipos");
  });
  const adjuntar = h("div", { clase: "ctz-adjunto" },
    h("button", { type: "button", clase: "claro", onclick: () => archivo.click() },
      t("ctz_adjuntar")), nombreArchivo, archivo);

  const selCliente = lista("cliente_id", [{ valor: "", texto: t("ctz_escoge_cliente_odoo") },
    ...cat.clientes.filter(c => String(c.pais_id) === String(d.pais_id)
                                && c.odoo_id && c.activo !== false)
      .map(c => ({ valor: c.id, texto: c.nombre }))]);

  const boton = h("button", { type: "button" }, t("pro_autorizar_y_crear"));
  const cancelar = h("button", { type: "button", clase: "claro",
    onclick: () => pintarTarjeta(tarjeta, cat, d) }, t("cot_cancelar"));
  boton.addEventListener("click", async () => {
    const nombre = quien.value === OTRA ? otra.value.trim() : quien.value;
    if (prospecto && !selCliente.value) { mensaje(t("ctz_falta_cliente_odoo"), "alerta"); return; }
    if (!nombre) { mensaje(t("cot_falta_quien"), "alerta"); return; }
    if (!dia.value) { mensaje(t("cot_falta_dia"), "alerta"); return; }
    boton.disabled = true;
    cancelar.disabled = true;
    try {
      const r = await api.formulario(`/cotizaciones/propuesta/${d.id}/autorizar`, {
        autorizada_por: nombre, autorizada_el: dia.value,
        cliente_id: prospecto ? selCliente.value : null,
        comprobante: archivo.files[0] || null });
      mensaje(reemplazar(t("pro_implantado_creado"), { f: r.folio }), "ok");
      location.hash = `#/implantado/${r.servicio_id}`;
    } catch (err) {
      mensaje(err.message, "grave");
      boton.disabled = false;
      cancelar.disabled = false;
    }
  });

  const lleva = d.posiciones.map(p => `${p.cantidad} ${p.descripcion || p.producto || p.nombre}`)
    .join(" y ");
  tarjeta.replaceChildren(...[
    conAyuda("h3", t("ctz_la_autorizo"), "ay_pro_autorizar", { style: "margin:0" }),
    prospecto ? h("div", { style: "margin-top:12px" },
      aviso(reemplazar(t("pro_cliente_en_odoo_pie"), { e: d.prospecto }), "alerta"),
      h("div", { clase: "rejilla dos", style: "margin-top:10px" },
        campo(t("ctz_cliente_en_odoo"), listaBuscable(selCliente, t("buscar_cliente")),
              { obligatorio: true }))) : null,
    h("div", { clase: "rejilla tres", style: "margin-top:12px" },
      h("div", {}, campo(t("ctz_quien_autorizo"), quien, { obligatorio: true }), otra),
      campo(t("cot_el_dia"), dia, { obligatorio: true }),
      campo(t("ctz_comprobante"), adjuntar)),
    h("div", { clase: "aviso ok", style: "margin:6px 0 14px" },
      h("b", {}, t("pro_al_autorizar_titulo")), " ",
      reemplazar(t("pro_al_autorizar"), {
        c: d.cliente, p: d.plaza || "—", s: d.solicitante || "—", l: lleva,
        m: t(MODALIDAD_CORTA[d.dias_servicio] || "pro_mod_lv_corta"),
        h: d.horas_jornada ?? d.horas_del_pais ?? "—",
        f: d.inicio ? fechaCorta(d.inicio, false) : "—",
        x: dinero(d.subtotal, d.moneda),
        v: aMedia(t(d.viaticos === "incluidos" ? "pro_viaticos_incluidos"
                                                : "pro_viaticos_aparte")) })),
    avisoInicioPasado(d),
    h("div", { clase: "acciones", style: "margin:0" }, boton, cancelar)].filter(Boolean));
}

/* El inicio del trato que ya paso (seccion 131, decision 11): el
   implantado que se autoriza o se vuelve a crear tarde nace con su primer
   mes atrasado. Se dice en amarillo y se deja seguir. */
function avisoInicioPasado(d) {
  if (!d.dias_pasados) return null;
  return h("div", { style: "margin:6px 0 10px" },
    aviso(reemplazar(t(d.dias_pasados === 1 ? "pro_dia_pasado" : "pro_dias_pasados"),
                     { n: d.dias_pasados, f: fechaCorta(d.inicio, false) }), "alerta"));
}

/* Eliminar la propuesta cuyo implantado se elimino (seccion 131), con su
   porque, como la cotizacion desde la 126. */
function formularioEliminar(caja, d) {
  caja.replaceChildren();
  const motivo = h("textarea", { rows: "2", maxlength: "300",
                                 placeholder: t("ctz_eliminar_ayuda") });
  const boton = h("button", { type: "button", clase: "peligro" }, t("ctz_eliminarla"));
  boton.addEventListener("click", async () => {
    if (!motivo.value.trim()) { mensaje(t("ctz_falta_motivo_eliminar"), "alerta"); return; }
    if (!confirm(t("pro_seguro_eliminar"))) return;
    boton.disabled = true;
    try {
      await api.post(`/cotizaciones/propuesta/${d.id}/eliminar`, { motivo: motivo.value });
      mensaje(t("pro_eliminada"), "ok");
      irA("#/cotizaciones");
    } catch (err) { mensaje(err.message, "grave"); boton.disabled = false; }
  });
  caja.append(h("div", { clase: "ctz-forma" },
    h("h4", { style: "margin:0 0 8px" }, t("pro_eliminar_propuesta")),
    h("p", { clase: "chico gris", style: "margin:0 0 8px" }, t("ctz_eliminar_pie")),
    campo(t("ctz_motivo_eliminar"), motivo, { obligatorio: true }),
    h("div", { clase: "acciones", style: "margin:8px 0 0" }, boton,
      h("button", { type: "button", clase: "claro", onclick: () => caja.replaceChildren() },
        t("cot_cancelar")))));
}

function formularioRechazo(caja, d) {
  caja.replaceChildren();
  const motivo = h("textarea", { rows: "2", maxlength: "300", placeholder: t("ctz_rechazo_ayuda") });
  const boton = h("button", { type: "button" }, t("ctz_rechazar"));
  boton.addEventListener("click", async () => {
    if (!motivo.value.trim()) { mensaje(t("ctz_falta_motivo_rechazo"), "alerta"); return; }
    boton.disabled = true;
    try {
      await api.post(`/cotizaciones/propuesta/${d.id}/rechazar`, { motivo: motivo.value });
      irA(`#/propuesta/${d.id}`);
    } catch (err) { mensaje(err.message, "grave"); boton.disabled = false; }
  });
  caja.append(h("div", { clase: "ctz-forma" },
    h("h4", { style: "margin:0 0 8px" }, t("ctz_la_rechazo")),
    campo(t("ctz_motivo_rechazo"), motivo, { obligatorio: true }),
    h("div", { clase: "acciones", style: "margin:8px 0 0" }, boton,
      h("button", { type: "button", clase: "claro", onclick: () => caja.replaceChildren() },
        t("cot_cancelar")))));
}

/* ============================================================ en el implantado */

/* El bloque «La propuesta autorizada» de la pantalla del implantado: lo
   que se le vendio al cliente, con su PDF. */
export function bloquePropuesta(p) {
  if (!p) return null;
  const moneda = p.moneda;
  const lleva = p.posiciones.map(x => `${x.cantidad} ${x.nombre} ${dinero(x.precio_mes, moneda)}`);
  const aparte = [
    p.dia_adicional !== null && p.dias_servicio !== "todos"
      ? reemplazar(t("pro_imp_dia_adicional"), { p: dinero(p.dia_adicional, moneda) }) : null,
    p.hora_extra ? reemplazar(t("pro_imp_hora_extra"), { p: dinero(p.hora_extra, moneda) }) : null,
    p.horas_jornada ? reemplazar(t("pro_jornada_de"), { n: p.horas_jornada }) : null,
    p.inicio ? reemplazar(t("pro_desde"), { f: fechaCorta(p.inicio) }) : null,
  ].filter(Boolean);
  return h("div", { clase: "tarjeta" },
    conAyuda("h4", [t("pro_imp_titulo"), " ",
      etiqueta(reemplazar(t("pro_imp_autorizada_v"), { v: p.version }), "ok")],
    "ay_pro_imp", { style: "margin:0" }),
    h("div", { clase: "rejilla cuatro", style: "margin-top:12px" },
      h("div", {}, h("div", { clase: "chico gris" }, t("pro_mensual")),
        h("div", { clase: "cifra", style: "font-size:19px" }, dinero(p.subtotal, moneda)),
        h("div", { clase: "chico gris" }, reemplazar(t("pro_imp_antes_iva"), {
          m: t(MODALIDAD_CORTA[p.dias_servicio] || "pro_mod_lv_corta") }))),
      h("div", {}, h("div", { clase: "chico gris" }, t("pro_imp_la_autorizo")),
        h("b", {}, p.autorizada_por || "—"),
        h("div", { clase: "chico gris" }, p.autorizada_el ? fechaCorta(p.autorizada_el) : "—")),
      h("div", {}, h("div", { clase: "chico gris" }, t("ctz_col_folio")),
        h("a", { href: `#/propuesta/${p.id}`, clase: "enlace" }, h("b", {}, p.nombre)),
        p.pdf ? h("div", {}, h("button", { clase: "enlace chico", type: "button",
          onclick: async () => {
            try { await bajar(`/cotizaciones/propuesta/${p.id}/pdf?bajar=true`); }
            catch (err) { mensaje(err.message, "grave"); }
          } }, t("pro_imp_pdf"))) : null),
      h("div", {}, h("div", { clase: "chico gris" }, t("pro_viaticos")),
        h("b", {}, t(p.viaticos === "incluidos" ? "pro_viaticos_incluidos" : "pro_viaticos_aparte")))),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, [...lleva, ...aparte].join(" · ")),
    h("p", { clase: "chico gris", style: "margin:6px 0 0" }, reemplazar(t("pro_imp_pie"), {
      n: p.base })));
}

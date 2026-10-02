/* Cotizaciones (seccion 114).

   Salvador, 30 de septiembre: la cotizacion se arma en Connect, en una
   pantalla nueva que pregunta si es una propuesta para implantado o una
   cotizacion para eventual. Se saca su PDF, el consultor la manda al
   cliente y, cuando el cliente la autoriza, pasa a servicio eventual: el
   servicio se crea solo. La propuesta del implantado llego en la seccion
   115 (`propuesta.js`): la lista de esta pantalla trae las dos.

   Con sus decisiones del 1 de octubre: folio nuevo (EP/COT-0001) con su
   version; se puede cotizar a una empresa que todavia no esta en Odoo,
   con la lista general de su pais, y para autorizarla ya tiene que
   estar; la autorizacion la registra el consultor --quien y que dia, con
   el correo adjunto--; el PDF lleva el IVA; cada consultor sube su firma.

   Los precios no se teclean: salen de la lista del cliente, igual que en
   la cotizacion del servicio (seccion 94), y el paquete conductor +
   unidad sale solo si la lista lo pacta. Se piden al servidor mientras
   se arma, sin guardar nada. Lo que se manda ya no cambia: si el cliente
   pide algo distinto, se hace la version siguiente.

   Connect no manda correos: el consultor baja el PDF y lo manda desde
   su correo, como hoy. Por eso el boton dice lo que hace --descargar el
   PDF y marcarla enviada-- y no «enviar». */
import { api } from "./api.js";
import { catalogos, listaDeConsultores } from "./catalogos.js";
import { aviso, campo, conAyuda, dinero, entrada, etiqueta, fechaLocal, h,
         hoyLocal, lista, listaBuscable, mensaje } from "./util.js";
import { t } from "./idioma.js";
import { bajar } from "./bitacora_admin.js";

const OTRA = "__otra";
const NUEVA = "__nueva";
const ESPERA_PRECIOS = 400;
/* Como los nombra el servidor (alias_de_equipo): los renglones con
   precio dicen de que equipo son por su alias. */
const ALIAS = ["Alfa", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta",
               "Iota", "Kappa", "Lambda", "My", "Ny", "Xi", "Omicron", "Pi", "Rho",
               "Sigma", "Tau", "Ypsilon", "Fi", "Ji", "Psi", "Omega"];
const MODALIDAD = { full_day: "mod_full_day", medio_dia: "mod_medio_dia",
                    transfer: "mod_transfer" };
const ESTATUS = {
  borrador: ["ctz_est_borrador", "info"], enviada: ["ctz_est_enviada", "azul"],
  autorizada: ["ctz_est_autorizada", "ok"], rechazada: ["ctz_est_rechazada", "grave"],
  vencida: ["ctz_est_vencida", "alerta"], sustituida: ["ctz_est_sustituida", ""],
};
const VISTAS = [["abiertas", "ctz_vista_abiertas"], ["autorizadas", "ctz_vista_autorizadas"],
                ["cerradas", "ctz_vista_cerradas"], ["todas", "ctz_vista_todas"]];
const GASTOS_CORTO = { dentro: "cot_g_corto_dentro", fijo: "cot_g_corto_fijo",
                       comprobar: "cot_g_corto_comprobar" };
const GASTOS_LARGO = { dentro: "ctz_gl_dentro", fijo: "ctz_gl_fijo",
                       comprobar: "ctz_gl_comprobar" };
/* Lo que el PDF toma de Catalogos y todavia no esta escrito. */
const FALTA_TEXTO = {
  razon_social: "ctz_ft_razon_social", rfc: "ctz_ft_rfc", tasa_iva: "ctz_ft_tasa_iva",
  pago: "ctz_ft_pago", aceptacion: "ctz_ft_aceptacion", cancelacion: "ctz_ft_cancelacion",
  cierre: "ctz_ft_cierre", incluye_dentro: "ctz_ft_incluye",
  incluye_fijo: "ctz_ft_incluye", incluye_comprobar: "ctz_ft_incluye",
};
const IDIOMA_PDF = { es: "ctz_idioma_es", en: "ctz_idioma_en", pt: "ctz_idioma_pt" };
const MONEDA_TEXTO = { MXN: "ctz_moneda_mxn", USD: "ctz_moneda_usd", BRL: "ctz_moneda_brl" };

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (s, [k, v]) => s.split(`{${k}}`).join(v ?? ""), texto);
}

function estatusDe(codigo) {
  const [clave, tono] = ESTATUS[codigo] || ESTATUS.borrador;
  return etiqueta(t(clave), tono);
}

/* «31 dic 2026», como en el PDF y en la maqueta. */
function fechaCorta(iso, conAnio = true) {
  if (!iso) return "—";
  const f = new Date(`${iso.slice(0, 10)}T00:00:00`);
  const mes = t("f_meses").split(",")[f.getMonth()];
  return conAnio ? `${f.getDate()} ${mes} ${f.getFullYear()}` : `${f.getDate()} ${mes}`;
}

/* «27 al 29 sep», «30 sep al 2 oct»; con el anio al final si se pide. */
function rangoCorto(desde, hasta, conAnio = false) {
  if (!desde) return "—";
  const meses = t("f_meses").split(",");
  const a = new Date(`${desde}T00:00:00`);
  const b = new Date(`${hasta || desde}T00:00:00`);
  const anio = conAnio ? ` ${b.getFullYear()}` : "";
  if (a.getTime() === b.getTime()) return `${a.getDate()} ${meses[a.getMonth()]}${anio}`;
  const mismoMes = a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear();
  return reemplazar(t("ctz_rango"), {
    a: mismoMes ? String(a.getDate()) : `${a.getDate()} ${meses[a.getMonth()]}`,
    b: `${b.getDate()} ${meses[b.getMonth()]}`,
  }) + anio;
}

/* El dia de un instante del servidor, como lo vive quien mira. La hora
   de envio viene en UTC: mandada a las 8 de la noche en Mexico, su
   fecha a secas ya es la de manana. */
const diaDe = (instante) => (instante ? fechaLocal(new Date(instante)) : null);

const diasEntre = (desde, hasta) =>
  Math.round((new Date(`${hasta}T00:00:00`) - new Date(`${desde}T00:00:00`)) / 86400000);

/* Dias del calendario, no dias de equipo: «3 dias · 3 equipos» es del 27
   al 29 con tres equipos, como lo lee el cliente. */
function cuantos(lineas) {
  const trabajo = lineas.filter(l => l.tipo !== "viaticos");
  const dias = new Set(trabajo.map(l => l.fecha)).size;
  const equipos = new Set(trabajo.map(l => l.equipo)).size;
  return [
    dias === 1 ? t("cot_un_dia") : reemplazar(t("cot_n_dias"), { n: dias }),
    equipos === 1 ? t("cot_un_equipo") : reemplazar(t("cot_n_equipos"), { n: equipos }),
  ].join(" · ");
}

/* Volver a pintar la misma direccion: asignarla de nuevo no avisa. */
function irA(destino) {
  if (location.hash === destino) window.dispatchEvent(new HashChangeEvent("hashchange"));
  else location.hash = destino;
}

/* El PDF se abre en una pestana nueva con la sesion puesta. La pestana
   se abre al picar, antes de esperar al servidor: abierta despues, el
   navegador la toma por ventana emergente y la bloquea. La ruta puede
   depender de lo que se haga antes --el folio de un borrador que se
   guarda por primera vez--. */
async function abrirPdf(ruta, antes = null) {
  const pestana = window.open("", "_blank");
  try {
    if (antes) await antes();
    const url = await api.imagen(typeof ruta === "function" ? ruta() : ruta);
    if (pestana) pestana.location.href = url;
    else window.open(url, "_blank");
  } catch (err) {
    if (pestana) pestana.close();
    mensaje(err.message, "grave");
  }
}

/* Lo que usa la propuesta del implantado (seccion 115), que vive en su
   archivo y se arma con las mismas piezas. */
export { reemplazar, estatusDe, fechaCorta, irA, abrirPdf, diaDe, finDeAnio,
         notaDeEstatus, panelFirma, OTRA, NUEVA, IDIOMA_PDF };

/* ============================================================ la lista */

/* Que se ve: las dos, o solo unas (seccion 115). */
const QUE = [["todas", "ctz_que_todas"], ["cotizaciones", "ctz_que_cotizaciones"],
             ["propuestas", "ctz_que_propuestas"]];

export async function pantallaCotizaciones(main) {
  let vista = "todas";
  let q = "";
  let que = "todas";
  let espera = null;
  const zona = h("div");
  const pestanas = h("div", { clase: "pestanas", style: "margin:0 0 12px" });
  const firma = h("div");
  const buscar = entrada("q", {
    type: "search", placeholder: t("ctz_buscar_ayuda"),
    oninput: () => { q = buscar.value; clearTimeout(espera); espera = setTimeout(cargar, 300); },
  });
  const acciones = h("div", { clase: "acciones", style: "margin-bottom:16px" });
  const selQue = lista("que", QUE.map(([valor, texto]) => ({ valor, texto: t(texto) })),
    { onchange: () => { que = selQue.value; cargar(); } });

  main.append(
    h("h1", {}, t("ctz_titulo")),
    h("p", { clase: "sub" }, t("ctz_sub")),
    acciones, firma,
    h("div", { clase: "tarjeta lisa", style: "margin-bottom:16px" },
      pestanas,
      h("div", { clase: "rejilla tres", style: "grid-template-columns:2fr 1fr" },
        campo(t("ctz_buscar"), buscar), campo(t("ctz_que"), selQue))),
    zona);

  async function cargar() {
    const d = await api.get(`/cotizaciones/lista?vista=${vista}&que=${que}`
                            + `&q=${encodeURIComponent(q)}`);
    acciones.replaceChildren(...[
      d.puede_armar ? h("button", { type: "button",
        onclick: () => { location.hash = "#/cotizacion/eventual"; } }, t("ctz_nueva")) : null,
      d.puede_armar ? h("button", { type: "button",
        onclick: () => { location.hash = "#/propuesta/nueva"; } }, t("pro_nueva")) : null,
      d.puede_armar ? h("button", { type: "button", clase: "claro",
        onclick: () => panelFirma(firma) }, t("ctz_tu_firma")) : null,
    ].filter(Boolean));
    pestanas.replaceChildren(...VISTAS.map(([clave, texto]) => h("button", {
      type: "button", clase: clave === vista ? "pestana activa" : "pestana",
      onclick: () => { vista = clave; cargar(); },
    }, reemplazar(t(texto), { n: d.cuentas[clave] }))));
    zona.replaceChildren(tablaDeLista(d.filas, q));
  }

  await cargar();
}

function notaDeEstatus(f) {
  if (f.estatus === "enviada" && f.valida_hasta) {
    const quedan = diasEntre(hoyLocal(), f.valida_hasta);
    if (quedan >= 0 && quedan <= 5) {
      return h("div", { clase: "chico", style: "margin-top:4px;color:var(--alerta);font-weight:650" },
        quedan === 0 ? t("ctz_vence_hoy")
          : quedan === 1 ? t("ctz_vence_manana") : reemplazar(t("ctz_vence_en"), { n: quedan }));
    }
  }
  if (f.estatus === "enviada" && f.enviada_en) {
    const hace = diasEntre(diaDe(f.enviada_en), hoyLocal());
    return h("div", { clase: "chico gris", style: "margin-top:4px" },
      hace <= 0 ? t("ctz_enviada_hoy")
        : hace === 1 ? t("ctz_enviada_ayer") : reemplazar(t("ctz_enviada_hace"), { n: hace }));
  }
  if (f.estatus === "autorizada") {
    return h("div", { clase: "chico gris", style: "margin-top:4px" },
      `${fechaCorta(f.autorizada_el, false)} · ${f.autorizada_por || "—"}`);
  }
  if (f.estatus === "rechazada" && f.rechazo_motivo) {
    return h("div", { clase: "chico gris", style: "margin-top:4px" }, `«${f.rechazo_motivo}»`);
  }
  return null;
}

function servicioDe(f) {
  if (f.servicio) {
    /* La propuesta hizo nacer un implantado: se abre en su pantalla. */
    const ruta = f.clase === "propuesta" ? `#/implantado/${f.servicio.id}`
      : `#/servicio/${f.servicio.id}`;
    return h("a", { href: ruta, style: "white-space:nowrap",
                    onclick: (e) => e.stopPropagation() }, h("b", {}, f.servicio.folio));
  }
  if (f.servicio_folio) {
    return h("span", { clase: "chico gris" },
      reemplazar(t("ctz_servicio_borrado"), { f: f.servicio_folio }));
  }
  return "—";
}

function tablaDeLista(filas, q) {
  if (!filas.length) return h("p", { clase: "gris" }, t(q ? "ctz_no_hay_asi" : "ctz_ninguna"));
  const esPropuesta = (f) => f.clase === "propuesta";
  /* La propuesta dice desde cuando: su mensual no tiene fecha de fin. */
  const cuando = (f) => (esPropuesta(f)
    ? (f.desde ? reemplazar(t("pro_desde"), { f: fechaCorta(f.desde, false) }) : "—")
    : rangoCorto(f.desde, f.hasta));
  return h("table", { clase: "lista" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("ctz_col_folio")), h("th", {}, t("ctz_col_que_es")),
      h("th", {}, t("ctz_col_cliente")),
      h("th", {}, t("ctz_col_solicita")), h("th", {}, t("ctz_col_cuando")),
      h("th", { clase: "der" }, t("ctz_col_total")), h("th", {}, t("ctz_col_valida")),
      h("th", {}, t("ctz_col_estatus")), h("th", {}, t("ctz_col_servicio")))),
    h("tbody", {}, ...filas.map(f => h("tr", {
      clase: "clic", onclick: () => {
        location.hash = esPropuesta(f) ? `#/propuesta/${f.id}` : `#/cotizacion/${f.id}`;
      } },
      h("td", { style: "white-space:nowrap" }, h("b", {}, f.folio), " ",
        h("span", { clase: "gris chico" }, `V${f.version}`)),
      h("td", {}, esPropuesta(f) ? etiqueta(t("ctz_es_propuesta"), "info")
        : etiqueta(t("ctz_es_cotizacion"))),
      h("td", {}, f.cliente, f.es_prospecto
        ? h("div", { style: "margin-top:4px" }, etiqueta(t("ctz_empresa_nueva"), "alerta")) : null),
      h("td", {}, f.solicitante || "—"),
      h("td", { style: "white-space:nowrap" }, cuando(f)),
      h("td", { clase: "der num" }, dinero(f.total, f.moneda),
        esPropuesta(f) ? h("div", { clase: "chico gris" }, t("pro_al_mes")) : null),
      h("td", { style: "white-space:nowrap" }, fechaCorta(f.valida_hasta)),
      h("td", {}, estatusDe(f.estatus), notaDeEstatus(f)),
      h("td", {}, servicioDe(f))))));
}

/* ------------------------------------------------------------ la firma */

/* La firma de quien esta mirando, y solo la suya: no hay forma de subir
   la de otro (decision 5). Sale en las cotizaciones que el firma. */
async function panelFirma(caja) {
  if (caja.firstChild) { caja.replaceChildren(); return; }
  const d = await api.get("/cotizaciones/firma");
  const repintar = async () => { caja.replaceChildren(); await panelFirma(caja); };
  const archivo = h("input", { type: "file", accept: "image/png,image/jpeg", hidden: "hidden",
    onchange: async () => {
      if (!archivo.files[0]) return;
      try {
        await api.formulario("/cotizaciones/firma", { archivo: archivo.files[0] }, "PUT");
        mensaje(t("ctz_firma_lista"), "ok");
        await repintar();
      } catch (err) { mensaje(err.message, "grave"); }
    } });
  const quitar = h("button", { type: "button", clase: "claro chico",
    onclick: async () => {
      try {
        await api.borrar("/cotizaciones/firma");
        await repintar();
      } catch (err) { mensaje(err.message, "grave"); }
    } }, t("ctz_firma_quitar"));
  const tarjeta = h("div", { clase: "tarjeta", style: "margin-bottom:16px" },
    conAyuda("h3", t("ctz_firma_titulo"), "ay_ctz_firma", { style: "margin:0" }),
    h("p", { clase: "chico gris", style: "margin:8px 0 10px" }, t("ctz_firma_pie")),
    d.tiene ? h("img", { src: d.imagen, alt: t("ctz_firma_titulo"), clase: "ctz-firma" })
      : h("p", { clase: "gris" }, t("ctz_firma_no_hay")),
    h("div", { clase: "acciones", style: "margin:10px 0 0" },
      h("button", { type: "button", clase: "chico", onclick: () => archivo.click() },
        t(d.tiene ? "ctz_firma_cambiar" : "ctz_firma_subir")),
      d.tiene ? quitar : null, archivo));
  caja.append(tarjeta);
}

/* ============================================================ nueva */

export async function nuevaCotizacion(main) {
  const opcion = (titulo, texto, boton, activa, extra = null) => h("div", {
    clase: activa ? "tarjeta ctz-tipo" : "tarjeta ctz-tipo ctz-apagada" },
    h("h3", { style: "margin:0 0 6px" }, titulo, extra ? [" ", extra] : ""),
    h("p", { clase: "gris", style: "margin:0 0 14px" }, texto),
    boton);
  main.append(
    h("h1", {}, t("ctz_nueva")),
    h("p", { clase: "sub" }, t("ctz_que_cotizas")),
    h("div", { clase: "ctz-tipos" },
      opcion(t("ctz_tipo_eventual"), t("ctz_tipo_eventual_pie"),
        h("button", { type: "button", onclick: () => { location.hash = "#/cotizacion/eventual"; } },
          t("ctz_armar")), true),
      opcion(t("ctz_tipo_implantado"), t("ctz_tipo_implantado_pie"),
        h("button", { type: "button", onclick: () => { location.hash = "#/propuesta/nueva"; } },
          t("pro_armar")), true)),
    h("p", { style: "margin-top:16px" },
      h("a", { href: "#/cotizaciones", clase: "enlace" }, t("ctz_volver"))));
}

/* ============================================================ una cotizacion */

export async function pantallaCotizacion(main, cual) {
  const cat = await catalogos();
  if (cual === "eventual") return armar(main, cat, null);
  const d = await api.get(`/cotizaciones/eventual/${cual}`);
  if (d.se_edita) return armar(main, cat, d);
  return detalle(main, cat, d);
}

/* ------------------------------------------------------------ lo que lleva */

function ordenar(lleva) {
  return lleva.sort((a, b) => (a.tipo === b.tipo ? a.id - b.id
                                                 : a.tipo === "recurso" ? -1 : 1));
}

function clave(lleva) {
  return ordenar(lleva.filter(i => i.id && Number(i.cantidad) > 0).map(i => ({ ...i })))
    .map(i => `${i.tipo}:${i.id}:${Number(i.cantidad)}`).join("|");
}

/* Al volver a abrir un borrador: lo que mas se repite entre los dias es
   lo que lleva el equipo, y los dias distintos quedan como su cambio. */
function baseYCambios(dias) {
  let base = [];
  let mejor = -1;
  for (const d of dias) {
    const veces = dias.filter(x => clave(x.lleva) === clave(d.lleva)).length;
    if (veces > mejor && d.lleva.length) { mejor = veces; base = d.lleva; }
  }
  return {
    base: base.map(i => ({ ...i })),
    dias: dias.map(d => ({
      fecha: d.fecha, modalidad_id: d.modalidad_id, hora: (d.hora || "").slice(0, 5),
      es_foraneo: d.es_foraneo, destino: d.destino || "",
      cambio: d.lleva.length && clave(d.lleva) !== clave(base)
        ? d.lleva.map(i => ({ ...i })) : null,
    })),
  };
}

function siguienteDia(iso) {
  const f = new Date(`${iso}T00:00:00`);
  f.setDate(f.getDate() + 1);
  return `${f.getFullYear()}-${String(f.getMonth() + 1).padStart(2, "0")}-`
    + `${String(f.getDate()).padStart(2, "0")}`;
}

/* Valida hasta el 31 de diciembre, salvo que se diga otra cosa. */
const finDeAnio = () => `${new Date().getFullYear()}-12-31`;

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
    tipo_servicio: d ? (d.tipo_servicio || "") : t("ctz_tipo_omision"),
    valida_hasta: d && d.valida_hasta ? d.valida_hasta : finDeAnio(),
    idioma: d ? (d.idioma || "es") : "",
    moneda: d ? (d.moneda || "") : "",
    con_iva: d ? d.con_iva : true,
    gastos: d ? d.gastos : "",
    gastos_escogidos: Boolean(d),
    monto: d && d.monto_gastos ? String(d.monto_gastos) : "",
    introduccion: d ? (d.introduccion || "") : "",
    motivo: d ? (d.motivo || "") : "",
    equipos: d ? d.equipos.map(q => ({ plaza_id: q.plaza_id ? String(q.plaza_id) : "",
                                       ...baseYCambios(q.dias) })) : [],
  };
  let info = null;          // la lista de precios del cliente
  let ultimo = null;        // la ultima vista previa buena
  let turno = 0;
  let espera = null;

  const caja = h("div");
  main.append(
    h("h1", {}, t("ctz_eventual_titulo")),
    h("p", { clase: "sub" }, !e.folio ? t("ctz_eventual_sub_nueva")
      : d && d.consultor ? reemplazar(t("ctz_sub_borrador_de"), { f: e.folio, v: e.version, c: d.consultor })
        : reemplazar(t("ctz_sub_borrador"), { f: e.folio, v: e.version })),
    caja);

  /* ---------------------------------------------------- 1: para quien */
  const paisDe = (id) => cat.paises.find(p => String(p.id) === String(id));
  const clienteDe = (id) => cat.clientes.find(c => String(c.id) === String(id));

  /* La empresa que todavia no esta en Odoo va primero: abierta la lista,
     se ve sin buscarla. */
  const selCliente = lista("cliente_id", [
    { valor: "", texto: t("ctz_escoge_cliente") },
    { valor: NUEVA, texto: t("ctz_empresa_no_odoo") },
    ...cat.clientes.filter(c => c.activo !== false).map(c => ({ valor: c.id, texto: c.nombre }))],
  { onchange: async () => {
    if (selCliente.value === e.cliente_id) return;
    e.cliente_id = selCliente.value;
    e.solicitante_id = "";
    e.moneda = "";
    await alCambiarCliente();
  } });
  selCliente.value = e.cliente_id;
  const buscable = listaBuscable(selCliente, t("buscar_cliente"));
  /* El nombre de una empresa se queda como se escribe: «S.A. de C.V.»
     no se vuelve «S.a. De C.v.» al salir de la caja. */
  const prospecto = entrada("prospecto", { value: e.prospecto, maxlength: "160",
    "data-crudo": "", placeholder: t("ctz_empresa_nombre"),
    oninput: () => { e.prospecto = prospecto.value; recalcular(); } });
  const selPais = lista("pais_id", cat.paises.map(p => ({ valor: p.id, texto: p.nombre })),
    { onchange: async () => { e.pais_id = Number(selPais.value); e.moneda = ""; await alCambiarCliente(); } });
  const cajaProspecto = h("div", { clase: "rejilla dos" },
    campo(t("ctz_empresa"), prospecto, { obligatorio: true }),
    campo(t("ctz_pais"), selPais, { obligatorio: true }));
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

  /* «Transportacion ejecutiva» se queda asi: la introduccion lo lee en
     minusculas y una mayuscula de mas se nota. */
  const tipo = entrada("tipo", { value: e.tipo_servicio, maxlength: "120", "data-crudo": "",
    oninput: () => { e.tipo_servicio = tipo.value; recalcular(); } });
  const valida = entrada("valida", { type: "date", value: e.valida_hasta, min: hoyLocal(),
    onchange: () => { e.valida_hasta = valida.value; revisar(); } });
  const selIdioma = lista("idioma", ["es", "en", "pt"].map(i => ({ valor: i, texto: t(IDIOMA_PDF[i]) })),
    { onchange: () => { e.idioma = selIdioma.value; recalcular(); } });
  /* La moneda (seccion 120): se escoge si el pais tiene general en dos
     monedas y la empresa es nueva o el cliente esta en la general. Si no,
     se ve la de su lista, sin cambiarse. Cambiarla trae la otra lista y
     vuelve a poner los precios. */
  const selMoneda = h("select", { name: "moneda", onchange: async () => {
    e.moneda = selMoneda.value; await alCambiarCliente(true);
  } });
  const notaMoneda = h("div", { clase: "chico gris", style: "margin-top:4px" });
  function pintarMoneda() {
    const opciones = info ? (info.monedas.length ? info.monedas : [info.tarifario.moneda]) : [];
    selMoneda.replaceChildren(...opciones.map(x =>
      h("option", { value: x }, t(MONEDA_TEXTO[x] || x) || x)));
    selMoneda.value = e.moneda;
    selMoneda.disabled = !info || info.monedas.length < 2;
    notaMoneda.textContent = !info ? ""
      : info.monedas.length > 1 ? "" : t(info.pactada ? "ctz_moneda_pactada" : "ctz_moneda_unica");
  }
  const sinIva = h("input", { type: "checkbox",
    onchange: () => { e.con_iva = !sinIva.checked; recalcular(); } });
  sinIva.checked = !e.con_iva;

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

  async function alCambiarCliente(soloMoneda = false) {
    const nueva = e.cliente_id === NUEVA;
    cajaProspecto.hidden = !nueva;
    if (!nueva && e.cliente_id) {
      const c = clienteDe(e.cliente_id);
      e.pais_id = c ? c.pais_id : e.pais_id;
    }
    if (nueva && !e.pais_id) {
      e.pais_id = (cat.paises.find(p => p.codigo === "MX") || cat.paises[0] || {}).id;
    }
    selPais.value = e.pais_id ? String(e.pais_id) : "";
    /* El PDF sale en la lengua del pais del cliente; se puede cambiar.
       Cambiar la moneda no la toca. */
    if (!soloMoneda && (!e.idioma || !d)) {
      const p = paisDe(e.pais_id);
      e.idioma = (p && p.idioma) || "es";
    }
    selIdioma.value = e.idioma;
    /* Otro pais trae sus propias ciudades y modalidades. El equipo cuya
       ciudad no es de este pais toma la primera de aqui, y cada dia se
       queda con su modalidad, buscada por su codigo. */
    const deAqui = plazasDelPais();
    for (const q of e.equipos) {
      if (q.plaza_id && !deAqui.some(p => String(p.id) === String(q.plaza_id))) {
        q.plaza_id = deAqui[0] ? String(deAqui[0].id) : "";
      }
    }
    const antes = info ? info.modalidades : [];
    info = null;
    lineaLista.replaceChildren();
    if (e.cliente_id && e.pais_id) {
      try {
        const qs = (nueva ? `pais_id=${e.pais_id}` : `cliente_id=${e.cliente_id}`)
          + (e.moneda ? `&moneda=${e.moneda}` : "");
        info = await api.get(`/cotizaciones/eventual/lista-de-precios?${qs}`);
        e.moneda = info.tarifario.moneda;
        const codigoDe = Object.fromEntries(antes.map(x => [x.id, x.codigo]));
        const idDe = Object.fromEntries(info.modalidades.map(x => [x.codigo, x.id]));
        const porOmision = (info.modalidades.find(x => x.codigo === "full_day")
                            || info.modalidades[0] || {}).id;
        for (const q of e.equipos) {
          for (const x of q.dias) {
            if (idDe[codigoDe[x.modalidad_id]]) x.modalidad_id = idDe[codigoDe[x.modalidad_id]];
            else if (!info.modalidades.some(mo => mo.id === x.modalidad_id)) x.modalidad_id = porOmision;
          }
        }
        lineaLista.append(...pintarLista(info.tarifario, nueva, info.escogida));
        /* Si la lista trae sus paquetes Todo incluido, los gastos van
           dentro del precio; si no, por comprobar. Lo que el consultor
           ya escogio no se toca. */
        if (!e.gastos_escogidos) {
          e.gastos = info.tarifario.paquetes_con_viaticos ? "dentro" : "comprobar";
        }
      } catch (err) {
        lineaLista.append(aviso(err.message, "grave"));
      }
    }
    if (!e.gastos) e.gastos = "comprobar";
    pintarMoneda();
    pintarQuien();
    pintarEquipos();
    pintarGastos();
    recalcular();
  }

  /* «Precios de PE · General Mexico (MXN), la lista del cliente en Odoo.»
     Si el nombre ya trae la moneda, «Amazon Implantados (USD)», no se repite. */
  function pintarLista(tarifario, nueva, escogida) {
    const [antes, despues] = t(nueva ? "ctz_precios_general"
      : escogida ? "ctz_precios_escogida" : "ctz_precios_de").split("{l}");
    const yaLaDice = (tarifario.nombre || "").includes(`(${tarifario.moneda})`);
    return [antes, h("b", {}, tarifario.nombre),
            reemplazar(yaLaDice ? (despues || "").replace(" ({m})", "") : (despues || ""),
                       { m: tarifario.moneda }),
            tarifario.paquetes_con_viaticos ? ` ${t("ctz_todo_incluido")}` : ""];
  }

  const paraQuien = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctz_para_quien"), "ay_ctz_para_quien", { style: "margin:0" }),
    h("div", { clase: "rejilla tres", style: "margin-top:12px" },
      campo(t("ctz_cliente"), buscable, { obligatorio: true }),
      campoQuien,
      campo(t("ctz_quien_firma"), consultor, { obligatorio: true })),
    cajaProspecto, quienOtra, lineaLista,
    h("div", { clase: "rejilla cuatro" },
      campo(t("ctz_tipo_servicio"), tipo),
      campo(t("ctz_valida_hasta"), valida, { obligatorio: true }),
      campo(t("ctz_idioma_pdf"), selIdioma),
      h("div", {}, campo(t("ctz_moneda"), selMoneda), notaMoneda)),
    h("label", { clase: "opcion", style: "margin:0" }, sinIva, t("ctz_sin_iva")));

  /* ---------------------------------------------------- 2: equipos y dias */
  const equipos = h("div");

  const opcionesDe = (tipoItem) => (tipoItem === "recurso"
    ? (info ? info.roles : []) : (info ? info.unidades : []));

  function pieza(item, alCambiar, alQuitar) {
    const numero = h("input", { type: "number", min: "0", max: "20", step: "1",
      value: String(item.cantidad),
      oninput: () => { item.cantidad = Number(numero.value || 0); alCambiar(); } });
    const escoger = h("select", {
      onchange: () => { item.id = escoger.value ? Number(escoger.value) : null; alCambiar(); } },
      h("option", { value: "" }, t(item.tipo === "recurso" ? "cot_escoge_rol" : "cot_escoge_unidad")),
      ...opcionesDe(item.tipo).map(o => h("option", { value: String(o.id) }, o.nombre)));
    escoger.value = item.id ? String(item.id) : "";
    return h("span", { clase: "cot-lleva" }, numero, escoger,
      h("button", { clase: "claro chico", type: "button", title: t("cot_quitar"),
        "aria-label": t("cot_quitar"), onclick: alQuitar }, "×"));
  }

  function filaLleva(lleva, alCambiar) {
    const fila = h("div", { clase: "cot-fila-lleva" });
    const repintar = () => {
      fila.replaceChildren(
        ...lleva.map((item, i) => pieza(item, alCambiar,
          () => { lleva.splice(i, 1); repintar(); alCambiar(); })),
        h("button", { clase: "claro chico", type: "button",
          onclick: () => { lleva.push({ tipo: "recurso", id: null, cantidad: 1 }); repintar(); } },
        t("cot_otro_rol")),
        h("button", { clase: "claro chico", type: "button",
          onclick: () => { lleva.push({ tipo: "vehiculo", id: null, cantidad: 1 }); repintar(); } },
        t("cot_otra_unidad")));
    };
    repintar();
    return fila;
  }

  const modalidades = () => (info ? info.modalidades : []);
  const plazasDelPais = () => cat.plazas.filter(p => String(p.pais_id) === String(e.pais_id)
                                                     && p.activo !== false);

  function nuevoEquipo() {
    const modalidad = (modalidades().find(x => x.codigo === "full_day") || modalidades()[0] || {}).id;
    const primera = plazasDelPais()[0];
    const anterior = e.equipos[e.equipos.length - 1];
    return { plaza_id: anterior ? anterior.plaza_id : (primera ? String(primera.id) : ""),
             base: [{ tipo: "recurso", id: null, cantidad: 1 }, { tipo: "vehiculo", id: null, cantidad: 1 }],
             dias: [{ fecha: anterior && anterior.dias[0] ? anterior.dias[0].fecha : hoyLocal(1),
                      modalidad_id: modalidad, hora: "", es_foraneo: false, destino: "", cambio: null }] };
  }

  /* Lo que cobra un dia, de la ultima vista previa: el producto de la
     lista y lo que suma. Se escribe en sus dos celdas sin volver a pintar
     el renglon: repintar mientras alguien teclea una cantidad le quita
     el cursor. */
  const celdas = new Map();     // dia -> [lo que se cobra, precio]

  function pintarPrecio(alias, dia) {
    const [que, precio] = celdas.get(dia) || [];
    if (!que) return;
    const moneda = ultimo ? ultimo.moneda : (info ? info.tarifario.moneda : "MXN");
    const suyas = ultimo ? ultimo.lineas.filter(l => l.equipo === alias && l.fecha === dia.fecha
                                                     && l.tipo !== "viaticos") : [];
    const paquete = suyas.some(l => l.tipo === "paquete");
    que.replaceChildren(...(suyas.length ? [
      suyas.map(l => (l.producto || l.descripcion)
        + (l.cantidad > 1 ? ` ×${l.cantidad}` : "")).join(" · "),
      ...(paquete ? [" ", etiqueta(t("cot_paquete"), "azul")] : []),
    ] : [h("span", { clase: "gris" }, "—")]));
    precio.replaceChildren(suyas.length
      ? h("b", {}, dinero(suyas.reduce((s, l) => s + Number(l.importe), 0), moneda)) : "—");
  }

  function pintarPrecios() {
    e.equipos.forEach((q, n) => q.dias.forEach(dia => pintarPrecio(ALIAS[n] || String(n + 1), dia)));
  }

  function filaDeDia(q, dia, i, alias, cuerpo) {
    const selMod = lista("modalidad", modalidades().map(x => ({
      valor: x.id, texto: t(MODALIDAD[x.codigo] || "cot_col_modalidad") })),
    { onchange: () => { dia.modalidad_id = Number(selMod.value); recalcular(); } });
    selMod.value = String(dia.modalidad_id || "");
    const destino = entrada("destino", { value: dia.destino, maxlength: "120",
      placeholder: t("ctz_destino"), clase: "ctz-destino",
      oninput: () => { dia.destino = destino.value; recalcular(); } });
    destino.hidden = !dia.es_foraneo;
    const foraneo = h("input", { type: "checkbox", title: t("ctz_col_foraneo"),
      onchange: () => {
        dia.es_foraneo = foraneo.checked; destino.hidden = !foraneo.checked; recalcular();
      } });
    foraneo.checked = dia.es_foraneo;
    const que = h("td");
    const precio = h("td", { clase: "der num", style: "white-space:nowrap" });
    celdas.set(dia, [que, precio]);
    const fila = h("tr", {},
      h("td", {}, entrada("fecha", { type: "date", value: dia.fecha, clase: "ctz-fecha",
        onchange: (ev) => { dia.fecha = ev.target.value; recalcular(); } }),
      h("div", {}, h("button", { clase: "enlace chico", type: "button",
        onclick: () => {
          dia.cambio = dia.cambio ? null : q.base.map(x => ({ ...x }));
          pintarEquipos(); recalcular();
        } }, t(dia.cambio ? "ctz_igual_que_todos" : "cot_cambiar_dia")))),
      h("td", {}, selMod),
      h("td", {}, entrada("hora", { type: "time", value: dia.hora, clase: "ctz-hora",
        onchange: (ev) => { dia.hora = ev.target.value; } })),
      h("td", {}, h("div", { clase: "ctz-foraneo" }, foraneo), destino),
      que, precio,
      h("td", {}, q.dias.length > 1 ? h("button", { clase: "claro chico", type: "button",
        title: t("ctz_quitar_dia"), "aria-label": t("ctz_quitar_dia"),
        onclick: () => { q.dias.splice(i, 1); pintarEquipos(); recalcular(); } }, "×") : ""));
    cuerpo.append(fila);
    if (dia.cambio) {
      cuerpo.append(h("tr", { clase: "cot-dia-otro" }, h("td", { colspan: "7" },
        h("div", { clase: "chico gris", style: "margin:0 0 6px" },
          reemplazar(t("ctz_dia_distinto"), { d: fechaCorta(dia.fecha, false) })),
        filaLleva(dia.cambio, recalcular))));
    }
    pintarPrecio(alias, dia);
  }

  function pintarEquipos() {
    if (!e.equipos.length && info) e.equipos.push(nuevoEquipo());
    celdas.clear();
    const bloques = e.equipos.map((q, n) => {
      const alias = ALIAS[n] || String(n + 1);
      const selPlaza = lista("plaza", [{ valor: "", texto: t("ctz_escoge_ciudad") },
        ...plazasDelPais().map(p => ({ valor: p.id, texto: p.nombre }))],
      { onchange: () => { q.plaza_id = selPlaza.value; revisar(); recalcular(); } });
      selPlaza.value = q.plaza_id;
      const cuerpo = h("tbody");
      q.dias.forEach((dia, i) => filaDeDia(q, dia, i, alias, cuerpo));
      const varios = h("div", { hidden: "hidden", clase: "ctz-varios" });
      const desde = entrada("desde", { type: "date" });
      const hasta = entrada("hasta", { type: "date" });
      varios.append(campo(t("ctz_del"), desde), campo(t("ctz_al"), hasta),
        h("button", { type: "button", clase: "chico", onclick: () => {
          if (!desde.value || !hasta.value || hasta.value < desde.value) {
            mensaje(t("ctz_rango_mal"), "alerta"); return;
          }
          if (diasEntre(desde.value, hasta.value) > 60) {
            mensaje(t("ctz_rango_largo"), "alerta"); return;
          }
          const ultimoDia = q.dias[q.dias.length - 1];
          for (let f = desde.value; f <= hasta.value; f = siguienteDia(f)) {
            if (q.dias.some(x => x.fecha === f)) continue;
            q.dias.push({ fecha: f, modalidad_id: ultimoDia ? ultimoDia.modalidad_id : null,
                          hora: ultimoDia ? ultimoDia.hora : "", es_foraneo: false,
                          destino: "", cambio: null });
          }
          q.dias.sort((a, b) => a.fecha.localeCompare(b.fecha));
          pintarEquipos(); recalcular();
        } }, t("ctz_agregar_dias")));
      return h("div", { clase: "ctz-equipo" },
        h("div", { clase: "ctz-cabeza" },
          h("h4", { style: "margin:0" }, reemplazar(t("ctz_equipo_lleva"), { e: alias })),
          h("div", { clase: "ctz-ciudad" },
            h("label", {}, t("ctz_ciudad"), h("span", { clase: "obligatorio" }, " *")), selPlaza),
          e.equipos.length > 1 ? h("button", { clase: "claro chico", type: "button",
            onclick: () => { e.equipos.splice(n, 1); pintarEquipos(); recalcular(); } },
          t("ctz_quitar_equipo")) : null),
        filaLleva(q.base, recalcular),
        h("table", { clase: "lista ctz-dias" },
          h("thead", {}, h("tr", {},
            h("th", {}, t("cot_col_dia")), h("th", {}, t("cot_col_modalidad")),
            h("th", {}, t("ctz_col_hora")), h("th", {}, t("ctz_col_foraneo")),
            h("th", {}, t("ctz_col_que")), h("th", { clase: "der" }, t("cot_col_precio")),
            h("th", {}, ""))),
          cuerpo),
        h("div", { clase: "acciones", style: "margin:8px 0 0" },
          h("button", { clase: "claro chico", type: "button", onclick: () => {
            const ultimoDia = q.dias[q.dias.length - 1];
            q.dias.push({ fecha: ultimoDia ? siguienteDia(ultimoDia.fecha) : hoyLocal(1),
                          modalidad_id: ultimoDia ? ultimoDia.modalidad_id : null,
                          hora: ultimoDia ? ultimoDia.hora : "", es_foraneo: false,
                          destino: "", cambio: null });
            pintarEquipos(); recalcular();
          } }, t("ctz_mas_dia")),
          h("button", { clase: "claro chico", type: "button",
            onclick: () => { varios.hidden = !varios.hidden; } }, t("ctz_varios_dias"))),
        varios);
    });
    const otro = h("div", { clase: "acciones", style: "margin:16px 0 0" },
      e.equipos.length < ALIAS.length && info ? h("button", { clase: "claro", type: "button",
        onclick: () => { e.equipos.push(nuevoEquipo()); pintarEquipos(); recalcular(); } },
      t("ctz_otro_equipo")) : null);
    equipos.replaceChildren(...bloques, otro);
  }

  const tarjetaEquipos = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctz_equipos_dias"), "ay_ctz_equipos", { style: "margin:0" }),
    h("p", { clase: "chico gris", style: "margin:8px 0 0" }, t("ctz_equipos_pie")),
    equipos);

  /* ---------------------------------------------------- 3: los gastos */
  const monto = h("input", { type: "text", inputmode: "decimal", placeholder: "0.00",
    value: e.monto, clase: "cot-monto",
    oninput: () => { e.monto = monto.value; revisar(); recalcular(); } });
  /* Escribir el monto es escoger el monto fijo. Se marca su opcion sin
     repintar: repintar moveria la caja y le quitaria el cursor. */
  const radios = {};
  monto.addEventListener("focus", () => {
    if (e.gastos !== "fijo") {
      e.gastos = "fijo"; e.gastos_escogidos = true;
      if (radios.fijo) radios.fijo.checked = true;
      revisar(); recalcular();
    }
  });
  const gastos = h("div", { clase: "bloque-radio", style: "margin:12px 0 0" });
  function pintarGastos() {
    const opcion = (valor, texto, extra = null) => {
      const radio = h("input", { type: "radio", name: "ctz_gastos", value: valor,
        onchange: () => { e.gastos = valor; e.gastos_escogidos = true; revisar(); recalcular(); } });
      radio.checked = e.gastos === valor;
      radios[valor] = radio;
      return h("label", { clase: "opcion", style: "margin:0 0 6px" }, radio, texto, extra);
    };
    const nota = info && info.tarifario.paquetes_con_viaticos
      ? h("span", { clase: "chico gris" }, ` · ${t("ctz_g_lista_todo")}`) : null;
    gastos.replaceChildren(
      opcion("dentro", t("ctz_g_dentro"), nota),
      opcion("fijo", t("ctz_g_fijo"), monto),
      opcion("comprobar", t("ctz_g_comprobar")));
  }
  const tarjetaGastos = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctz_gastos"), "ay_ctz_gastos", { style: "margin:0" }), gastos);

  /* ---------------------------------------------------- 4: lo que lee */
  /* La introduccion la escribe Connect con los datos y se acomoda sola
     si cambian las fechas o las ciudades. Si el consultor la cambia, se
     queda como la escribio; vaciarla la regresa a la de Connect. */
  const intro = h("textarea", { rows: "3", maxlength: "2000",
    oninput: () => { e.introduccion = intro.value; pintarIntro(); } });
  intro.value = e.introduccion;
  const cambiarIntro = h("button", { clase: "enlace chico", type: "button",
    onclick: () => {
      intro.value = (ultimo && ultimo.introduccion_auto) || "";
      e.introduccion = intro.value;
      pintarIntro();
      intro.focus();
    } }, t("ctz_intro_cambiar"));
  const volverIntro = h("button", { clase: "enlace chico", type: "button",
    onclick: () => { intro.value = ""; e.introduccion = ""; pintarIntro(); } },
  t("ctz_intro_volver"));
  function pintarIntro() {
    const propia = Boolean(e.introduccion.trim());
    intro.placeholder = (ultimo && ultimo.introduccion_auto) || t("ctz_intro_espera");
    cambiarIntro.hidden = propia || !(ultimo && ultimo.introduccion_auto);
    volverIntro.hidden = !propia;
  }
  const motivo = h("textarea", { rows: "2", maxlength: "300", placeholder: t("ctz_motivo_ayuda"),
    oninput: () => { e.motivo = motivo.value; revisar(); } });
  motivo.value = e.motivo;
  const lineaHoraExtra = h("p", { clase: "chico gris", style: "margin:6px 0 0" });
  const faltaCatalogo = h("div");
  const tarjetaTexto = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("ctz_lo_que_lee"), "ay_ctz_texto", { style: "margin:0" }),
    h("div", { clase: "campo", style: "margin-top:12px" },
      h("label", {}, t("ctz_introduccion"), " ",
        h("span", { clase: "chico gris", style: "font-weight:500" }, t("ctz_intro_pie"))),
      intro, h("div", {}, cambiarIntro, volverIntro)),
    e.version > 1 ? campo(t("ctz_motivo"), motivo, { obligatorio: true }) : null,
    h("p", { clase: "chico gris", style: "margin:4px 0 0" }, t("ctz_condiciones_salen")),
    lineaHoraExtra, faltaCatalogo);

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
  const botonMandar = h("button", { type: "button", onclick: () => mandar() },
    t("ctz_mandar"));
  const pie = h("div", { clase: "tarjeta" }, avisoPrecios,
    h("div", { clase: "cot-pie", style: "margin:0;border:0;padding:0" },
      h("div", {}, rotuloTotal, total, pieTotal),
      h("div", {}, h("div", { clase: "acciones", style: "margin:0;justify-content:flex-end" },
        botonVer, botonGuardar, botonMandar), queFalta, notaFirma)));

  caja.append(paraQuien, tarjetaEquipos, tarjetaGastos, tarjetaTexto, pie);

  /* ---------------------------------------------------- lo que se manda */
  const conPrecio = (lleva) => lleva.filter(i => i.id && Number(i.cantidad) > 0)
    .map(i => ({ tipo: i.tipo, id: Number(i.id), cantidad: Number(i.cantidad) }));

  function cuerpo() {
    const nueva = e.cliente_id === NUEVA;
    const otra = nueva || e.solicitante_id === OTRA;
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
      tipo_servicio: e.tipo_servicio || null,
      introduccion: e.introduccion.trim() || null,
      valida_hasta: e.valida_hasta || null,
      idioma: e.idioma || null,
      moneda: e.moneda || null,
      con_iva: e.con_iva,
      gastos: e.gastos === "fijo" && !(Number(e.monto) > 0) ? "dentro" : (e.gastos || "comprobar"),
      monto_gastos: e.gastos === "fijo" && Number(e.monto) > 0 ? Number(e.monto) : null,
      motivo: e.version > 1 ? (e.motivo || null) : null,
      equipos: e.equipos.map(q => ({
        plaza_id: q.plaza_id ? Number(q.plaza_id) : null,
        lleva: conPrecio(q.base),
        dias: q.dias.filter(x => x.fecha && x.modalidad_id).map(x => ({
          fecha: x.fecha, modalidad_id: Number(x.modalidad_id), hora: x.hora || null,
          es_foraneo: x.es_foraneo, destino: x.es_foraneo ? (x.destino || null) : null,
          lleva: x.cambio ? conPrecio(x.cambio) : null })),
      })),
    };
  }

  function faltante() {
    const nueva = e.cliente_id === NUEVA;
    if (!e.cliente_id) return t("ctz_falta_cliente");
    if (nueva && !e.prospecto.trim()) return t("ctz_falta_empresa");
    if (!nueva && !e.solicitante_id) return t("ctz_falta_quien");
    if ((nueva || e.solicitante_id === OTRA) && !e.nombre.trim()) return t("ctz_falta_quien");
    if (!e.consultor_id) return t("ctz_falta_firma");
    if (!e.valida_hasta) return t("ctz_falta_valida");
    if (e.equipos.some(q => !q.plaza_id)) return t("ctz_falta_ciudad");
    if (e.gastos === "fijo" && !(Number(e.monto) > 0)) return t("cot_falta_monto");
    if (e.version > 1 && !e.motivo.trim()) return t("ctz_falta_motivo");
    if (!ultimo || !ultimo.lineas.some(l => l.tipo !== "viaticos")) return t("ctz_falta_lleva");
    return null;
  }

  function revisar() {
    const falta = faltante();
    queFalta.textContent = falta || "";
    const sinCliente = !e.cliente_id || (e.cliente_id === NUEVA && !e.prospecto.trim());
    botonMandar.disabled = Boolean(falta);
    botonGuardar.disabled = sinCliente;
    botonVer.disabled = sinCliente;
  }

  function recalcular() {
    clearTimeout(espera);
    espera = setTimeout(pedirPrecios, ESPERA_PRECIOS);
  }

  async function pedirPrecios() {
    const mio = ++turno;
    if (!info) { ultimo = null; pintarTotal(); revisar(); return; }
    try {
      const r = await api.post("/cotizaciones/eventual/precios", cuerpo());
      if (mio !== turno) return;
      ultimo = r;
      avisoPrecios.replaceChildren();
    } catch (err) {
      if (mio !== turno) return;
      ultimo = null;
      avisoPrecios.replaceChildren(aviso(err.message, "grave"));
    }
    pintarPrecios();
    pintarTotal();
    revisar();
  }

  function pintarTotal() {
    pintarIntro();
    rotuloTotal.textContent = reemplazar(t(e.con_iva ? "ctz_total_v_iva" : "ctz_total_v_sin"),
                                         { v: e.version });
    lineaHoraExtra.replaceChildren();
    faltaCatalogo.replaceChildren();
    notaFirma.textContent = "";
    if (!ultimo) {
      total.textContent = "—";
      pieTotal.textContent = "";
      return;
    }
    const moneda = ultimo.moneda;
    const conTrabajo = ultimo.lineas.some(l => l.tipo !== "viaticos");
    total.textContent = conTrabajo ? dinero(ultimo.total, moneda) : "—";
    pieTotal.textContent = [
      !e.con_iva ? t("ctz_sin_iva_corto")
        : ultimo.tasa_iva === null ? t("ctz_sin_tasa")
          : conTrabajo ? reemplazar(t("ctz_mas_iva"), { s: dinero(ultimo.subtotal, moneda),
                                                        i: dinero(ultimo.iva, moneda) }) : null,
      conTrabajo ? cuantos(ultimo.lineas) : null,
      t(GASTOS_CORTO[e.gastos] || "cot_g_corto_comprobar"),
    ].filter(Boolean).join(" · ");
    if (ultimo.hora_extra.length) {
      lineaHoraExtra.textContent = reemplazar(t("ctz_hora_extra_es"), {
        h: ultimo.hora_extra.map(x => `${x.rol} ${dinero(x.precio, moneda)}`).join(", ") });
    }
    const faltan = (ultimo.faltan_textos || []).filter(k =>
      !k.startsWith("incluye_") || k === `incluye_${e.gastos}`);
    if (faltan.length) {
      faltaCatalogo.append(aviso(reemplazar(t("ctz_falta_catalogo"), {
        i: t(IDIOMA_PDF[e.idioma] || "ctz_idioma_es"),
        l: [...new Set(faltan.map(k => t(FALTA_TEXTO[k] || "ctz_ft_incluye")))].join(", "),
      }), "alerta"));
    }
    if (e.consultor_id && !ultimo.firma) notaFirma.textContent = t("ctz_sin_firma");
  }

  /* ---------------------------------------------------- guardar y mandar */
  async function guardarYa() {
    const r = e.id ? await api.put(`/cotizaciones/eventual/${e.id}`, cuerpo())
      : await api.post("/cotizaciones/eventual", cuerpo());
    if (!e.id) {
      e.id = r.id; e.folio = r.folio;
      history.replaceState(null, "", `#/cotizacion/${r.id}`);
    }
    if (r.aviso_precios) {
      const texto = typeof r.aviso_precios === "string" ? r.aviso_precios
        : r.aviso_precios.mensaje;
      avisoPrecios.replaceChildren(aviso(texto, "alerta"));
    }
    return r;
  }

  async function guardar() {
    botonGuardar.disabled = true;
    try {
      const r = await guardarYa();
      mensaje(reemplazar(t("ctz_guardada"), { f: r.folio, v: r.version }), "ok");
    } catch (err) { mensaje(err.message, "grave"); }
    revisar();
  }

  /* Como va el PDF: se guarda el borrador y se abre. */
  async function ver() {
    botonVer.disabled = true;
    await abrirPdf(() => `/cotizaciones/eventual/${e.id}/pdf`, guardarYa);
    revisar();
  }

  async function mandar() {
    if (faltante()) return;
    if (!confirm(t("ctz_seguro_mandar"))) return;
    botonMandar.disabled = true;
    botonMandar.textContent = t("ctz_mandando");
    try {
      await guardarYa();
      await api.post(`/cotizaciones/eventual/${e.id}/enviar`);
    } catch (err) {
      botonMandar.textContent = t("ctz_mandar");
      mensaje(err.message, "grave");
      revisar();
      return;
    }
    try {
      await bajar(`/cotizaciones/eventual/${e.id}/pdf?bajar=true`);
      mensaje(t("ctz_mandada"), "ok");
    } catch (err) {
      mensaje(reemplazar(t("ctz_mandada_sin_pdf"), { m: err.message }), "alerta");
    }
    irA(`#/cotizacion/${e.id}`);
  }

  cajaProspecto.hidden = e.cliente_id !== NUEVA;
  selPais.value = e.pais_id ? String(e.pais_id) : "";
  pintarQuien();
  pintarGastos();
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
    h("h1", {}, reemplazar(t("ctz_titulo_folio"), { f: d.folio, c: d.cliente })),
    h("p", { clase: "sub" }, reemplazar(t("ctz_version_n"), { v: d.version }), " · ",
      lineaDeEstado(d)),
    tarjeta,
    tablaDeRenglones(d),
    tablaDeVersiones(d));
  pintarTarjeta(tarjeta, cat, d);
}

function pintarTarjeta(tarjeta, cat, d) {
  const moneda = d.moneda;
  const formulario = h("div");
  const cifras = h("div", { clase: "rejilla cuatro", style: "margin-top:12px" },
    h("div", {}, h("div", { clase: "chico gris" }, t(d.iva ? "ctz_total_con_iva" : "ctz_total")),
      h("div", { clase: "cifra", style: "font-size:19px" }, dinero(d.total, moneda)),
      d.iva ? null : h("div", { clase: "chico gris" }, t("ctz_sin_iva_corto"))),
    h("div", {}, h("div", { clase: "chico gris" }, t("ctz_col_fechas")),
      h("b", {}, rangoCorto(d.desde, d.hasta, true)),
      h("div", { clase: "chico gris" }, cuantos(d.lineas))),
    h("div", {}, h("div", { clase: "chico gris" }, t("ctz_gastos_corto")),
      h("b", {}, d.gastos === "fijo"
        ? reemplazar(t("ctz_gl_fijo"), { m: dinero(d.monto_gastos, moneda) })
        : t(GASTOS_LARGO[d.gastos] || "ctz_gl_comprobar"))),
    h("div", {}, h("div", { clase: "chico gris" }, t("ctz_col_valida")),
      h("b", {}, fechaCorta(d.valida_hasta))));

  const descargar = async () => {
    try { await bajar(`/cotizaciones/eventual/${d.id}/pdf?bajar=true`); }
    catch (err) { mensaje(err.message, "grave"); }
  };
  const acciones = h("div", { clase: "acciones", style: "margin:16px 0 0" },
    ...[
      d.se_autoriza ? h("button", { type: "button",
        onclick: () => formularioAutorizar(tarjeta, cat, d) }, t("ctz_la_autorizo")) : null,
      d.sale_otra ? h("button", { type: "button", clase: "claro", onclick: async (ev) => {
        ev.target.disabled = true;
        try {
          const nueva = await api.post(`/cotizaciones/eventual/${d.id}/version`);
          location.hash = `#/cotizacion/${nueva.id}`;
        } catch (err) { mensaje(err.message, "grave"); ev.target.disabled = false; }
      } }, reemplazar(t("ctz_hacer_version"), { v: d.version + 1 })) : null,
      d.pdf ? h("button", { type: "button", clase: "claro", onclick: descargar },
        t("ctz_bajar_pdf")) : null,
      !d.pdf && d.estatus === "borrador" ? h("button", { type: "button", clase: "claro",
        onclick: () => abrirPdf(() => `/cotizaciones/eventual/${d.id}/pdf`) },
      t("ctz_ver_pdf")) : null,
      d.comprobante ? h("button", { type: "button", clase: "claro",
        onclick: () => abrirPdf(() => `/cotizaciones/eventual/${d.id}/comprobante`) },
      t("ctz_ver_comprobante")) : null,
      d.se_autoriza ? h("button", { type: "button", clase: "claro",
        onclick: () => formularioRechazo(formulario, d) }, t("ctz_la_rechazo")) : null,
    ].filter(Boolean));

  const servicio = d.servicio
    ? h("p", { style: "margin:14px 0 0" }, t("ctz_nacio_servicio"), " ",
      h("a", { href: `#/servicio/${d.servicio.id}`, clase: "enlace" }, d.servicio.folio))
    : d.servicio_folio
      ? h("p", { clase: "gris", style: "margin:14px 0 0" },
        reemplazar(t("ctz_servicio_borrado"), { f: d.servicio_folio }))
      : null;
  const vigente = !d.es_ultima
    ? h("p", { clase: "chico gris", style: "margin:12px 0 0" }, t("ctz_hay_otra"), " ",
      ...d.versiones.filter(v => v.version === Math.max(...d.versiones.map(x => x.version)))
        .map(v => h("a", { href: `#/cotizacion/${v.id}`, clase: "enlace" }, `V${v.version}`)))
    : null;

  tarjeta.replaceChildren(...[
    conAyuda("h3", [t("ctz_la_cotizacion"), " ", estatusDe(d.estatus)], "ay_ctz_estado",
      { style: "margin:0" }),
    cifras, servicio, vigente, acciones, formulario].filter(Boolean));
}

function tablaDeRenglones(d) {
  const moneda = d.moneda;
  const trabajo = d.lineas.filter(l => l.tipo !== "viaticos");
  if (!trabajo.length) return h("div");
  return h("div", { clase: "tarjeta", style: "margin-top:16px" },
    h("h3", { style: "margin:0 0 10px" }, t("ctz_lo_que_lleva")),
    h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("cot_col_dia")), h("th", {}, t("ctz_col_equipo")),
        h("th", {}, t("cot_col_modalidad")), h("th", {}, t("ctz_col_que")),
        h("th", { clase: "der" }, t("cot_col_cant")), h("th", { clase: "der" }, t("cot_col_precio")),
        h("th", { clase: "der" }, t("cot_col_importe")))),
      h("tbody", {}, ...trabajo.map(l => h("tr", {},
        h("td", { style: "white-space:nowrap" }, fechaCorta(l.fecha, false)), h("td", {}, l.equipo),
        h("td", {}, t(MODALIDAD[l.modalidad] || "cot_col_modalidad")),
        h("td", {}, l.producto || l.descripcion,
          l.tipo === "paquete" ? [" ", etiqueta(t("cot_paquete"), "azul")] : ""),
        h("td", { clase: "der num" }, String(l.cantidad)),
        h("td", { clase: "der num" }, dinero(l.precio, moneda)),
        h("td", { clase: "der num" }, dinero(l.importe, moneda)))))),
    d.hora_extra.length ? h("p", { clase: "chico gris", style: "margin:8px 0 0" },
      reemplazar(t("ctz_hora_extra_es"), {
        h: d.hora_extra.map(x => `${x.rol} ${dinero(x.precio, moneda)}`).join(", ") })) : null);
}

function tablaDeVersiones(d) {
  return h("div", { clase: "tarjeta", style: "margin-top:16px" },
    conAyuda("h3", t("ctz_versiones"), "ay_ctz_versiones", { style: "margin:0 0 10px" }),
    h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("ctz_col_version")), h("th", {}, t("ctz_col_estatus")),
        h("th", {}, t("ctz_col_cambio")), h("th", { clase: "der" }, t("ctz_col_total")),
        h("th", {}, ""))),
      h("tbody", {}, ...d.versiones.slice().sort((a, b) => b.version - a.version).map(v => h("tr", {},
        h("td", {}, v.id === d.id ? h("b", {}, `V${v.version}`)
          : h("a", { href: `#/cotizacion/${v.id}`, clase: "enlace" }, `V${v.version}`)),
        h("td", {}, estatusDe(v.estatus)),
        h("td", {}, v.motivo || (v.version === 1 ? t("ctz_primera") : "—")),
        h("td", { clase: "der num" }, dinero(v.total, d.moneda)),
        h("td", {}, v.pdf ? h("button", { clase: "enlace chico", type: "button",
          onclick: async () => {
            try { await bajar(`/cotizaciones/eventual/${v.id}/pdf?bajar=true`); }
            catch (err) { mensaje(err.message, "grave"); }
          } }, t("ctz_pdf")) : ""))))));
}

/* ------------------------------------------------------------ autorizarla */

/* Como en la maqueta: la tarjeta de la cotizacion se vuelve la forma, y
   Cancelar la regresa. Al guardar nace el servicio con el mismo alta que
   Nuevo servicio y esta misma cotizacion adentro, ya autorizada. */
async function formularioAutorizar(tarjeta, cat, d) {
  const prospecto = !d.cliente_id;
  let contactos = [];
  if (!prospecto) {
    try {
      const info = await api.get(`/cotizaciones/eventual/lista-de-precios?cliente_id=${d.cliente_id}`);
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

  const boton = h("button", { type: "button" }, t("ctz_autorizar_y_crear"));
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
      const r = await api.formulario(`/cotizaciones/eventual/${d.id}/autorizar`, {
        autorizada_por: nombre, autorizada_el: dia.value,
        cliente_id: prospecto ? selCliente.value : null,
        comprobante: archivo.files[0] || null });
      mensaje(reemplazar(t("ctz_servicio_creado"), { f: r.folio }), "ok");
      location.hash = `#/servicio/${r.servicio_id}`;
    } catch (err) {
      mensaje(err.message, "grave");
      boton.disabled = false;
      cancelar.disabled = false;
    }
  });

  const equipos = [...new Set(d.lineas.filter(l => l.tipo !== "viaticos").map(l => l.equipo))];
  /* En otra moneda que la del pais (seccion 120): el tipo de cambio que
     queda fijo al autorizar, o que falta, antes de picar el boton. */
  const otraMoneda = d.moneda_local && d.moneda !== d.moneda_local;
  const tc = d.tipo_cambio_hoy;
  const notaCambio = !otraMoneda ? null
    : tc ? h("div", { clase: "aviso", style: "margin:6px 0 8px" },
      reemplazar(t("ctz_autorizar_tc"), { m: d.moneda, l: d.moneda_local, t: tc.corta,
        p: tc.por || "finanzas", f: fechaCorta(tc.fecha) }))
      : h("div", { style: "margin:6px 0 8px" },
        aviso(reemplazar(t("ctz_autorizar_sin_tc"), { m: d.moneda }), "alerta"));
  tarjeta.replaceChildren(...[
    conAyuda("h3", t("ctz_la_autorizo"), "ay_ctz_autorizar", { style: "margin:0" }),
    prospecto ? h("div", { style: "margin-top:12px" },
      aviso(reemplazar(t("ctz_cliente_en_odoo_pie"), { e: d.prospecto }), "alerta"),
      h("div", { clase: "rejilla dos", style: "margin-top:10px" },
        campo(t("ctz_cliente_en_odoo"), listaBuscable(selCliente, t("buscar_cliente")),
              { obligatorio: true }))) : null,
    h("div", { clase: "rejilla tres", style: "margin-top:12px" },
      h("div", {}, campo(t("ctz_quien_autorizo"), quien, { obligatorio: true }), otra),
      campo(t("cot_el_dia"), dia, { obligatorio: true }),
      campo(t("ctz_comprobante"), adjuntar)),
    h("div", { clase: "aviso ok", style: "margin:6px 0 14px" },
      h("b", {}, t("ctz_al_autorizar_titulo")), " ",
      reemplazar(t("ctz_al_autorizar"), {
        c: d.cliente, s: d.solicitante || "—",
        e: equipos.length === 1 ? t("cot_un_equipo")
          : reemplazar(t("cot_n_equipos"), { n: equipos.length }),
        a: equipos.join(", "), f: rangoCorto(d.desde, d.hasta) })),
    notaCambio,
    h("div", { clase: "acciones", style: "margin:0" }, boton, cancelar)].filter(Boolean));
}

function formularioRechazo(caja, d) {
  caja.replaceChildren();
  const motivo = h("textarea", { rows: "2", maxlength: "300", placeholder: t("ctz_rechazo_ayuda") });
  const boton = h("button", { type: "button" }, t("ctz_rechazar"));
  boton.addEventListener("click", async () => {
    if (!motivo.value.trim()) { mensaje(t("ctz_falta_motivo_rechazo"), "alerta"); return; }
    boton.disabled = true;
    try {
      await api.post(`/cotizaciones/eventual/${d.id}/rechazar`, { motivo: motivo.value });
      irA(`#/cotizacion/${d.id}`);
    } catch (err) { mensaje(err.message, "grave"); boton.disabled = false; }
  });
  caja.append(h("div", { clase: "ctz-forma" },
    h("h4", { style: "margin:0 0 8px" }, t("ctz_la_rechazo")),
    campo(t("ctz_motivo_rechazo"), motivo, { obligatorio: true }),
    h("div", { clase: "acciones", style: "margin:8px 0 0" }, boton,
      h("button", { type: "button", clase: "claro", onclick: () => caja.replaceChildren() },
        t("cot_cancelar")))));
}

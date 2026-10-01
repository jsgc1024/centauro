/* La cotizacion autorizada, en el servicio (seccion 94).

   Pieza 1 de «Para poder operar» (decisiones de Salvador, 28 sep).
   Mientras Odoo no manda la cotizacion, el consultor --o quien lo cubre,
   que queda anotado como cobertura-- la registra aqui: que lleva cada
   dia, como se cobran los gastos y quien la autorizo del lado del
   cliente, que dia y, si se hizo en Odoo, con que folio.

   Los precios no se teclean: salen del tarifario del cliente, igual que
   al cerrar, y el paquete conductor + unidad sale solo si la lista lo
   pacta. Lo unico que se escribe es el monto fijo de gastos, porque es
   lo que se pacto con el cliente.

   Se guarda ya autorizada. Si el cliente cambia algo antes del visto
   bueno, se recotiza: la version nueva nace autorizada, con su motivo, y
   la de antes queda sustituida; el servicio nunca se queda sin
   cotizacion vigente. Despues del visto bueno, un cambio lo regresa
   finanzas y ahi se recotiza. */
import { api, sesion } from "./api.js";
import { aviso, conAyuda, dinero, etiqueta, fecha, h, mensaje } from "./util.js";
import { t } from "./idioma.js";
import { tiene } from "./menu.js";
import { bajar } from "./bitacora_admin.js";

const MODALIDAD = { full_day: "mod_full_day", medio_dia: "mod_medio_dia",
                    transfer: "mod_transfer" };
const OTRA_PERSONA = "__otra";
const ESPERA_PRECIOS = 350;

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (s, [k, v]) => s.split(`{${k}}`).join(v ?? ""), texto);
}

/* ------------------------------------------------------------ el bloque */

export async function bloqueCotizacion(servicio) {
  let d;
  try {
    d = await api.get(`/cotizaciones/servicio/${servicio.id}/bloque`);
  } catch {
    /* Quien no ve el cierre no ve la cotizacion: no hay nada que pintar. */
    return h("div");
  }
  if (!d.se_cotiza) return h("div");
  const caja = h("div", { clase: "tarjeta", id: "cotizacion" });
  pintar(caja, d);
  return caja;
}

function pintar(caja, d) {
  caja.replaceChildren();
  if (d.vigente) {
    caja.append(...vistaAutorizada(caja, d));
  } else {
    caja.append(...vistaFalta(caja, d));
  }
}

/* El titulo con su estado al lado, y el "?" al final del renglon. */
function cabeza(estado, tono) {
  return conAyuda("h3", [t("cot_titulo"), " ", etiqueta(estado, tono)], "ay_cot",
                  { style: "margin:0" });
}

const puedeArmar = (d) => d.puede_cotizar && d.se_puede;

/* ------------------------------------------------------------ sin cotizacion */

function vistaFalta(caja, d) {
  const partes = [
    cabeza(t("cot_falta"), "grave"),
    aviso(t("cot_falta_aviso"), "alerta"),
    h("p", { clase: "chico gris", style: "margin:10px 0 12px" }, t("cot_precios_de")),
  ];
  if (!d.tarifario) {
    partes.push(aviso(t("cot_sin_tarifario"), "grave"));
  } else if (!d.dias.length) {
    partes.push(aviso(t("cot_sin_dias"), "alerta"));
  } else if (puedeArmar(d)) {
    partes.push(h("div", { clase: "acciones" },
      h("button", { type: "button",
        onclick: () => armar(caja, d) }, t("cot_armar"))));
  } else if (!d.puede_cotizar) {
    partes.push(h("p", { clase: "chico gris" }, t("cot_la_arma")));
  }
  return partes;
}

/* ------------------------------------------------------------ ya autorizada */

function textoDeGastos(c, moneda) {
  if (c.gastos === "fijo") {
    return reemplazar(t("cot_gl_fijo"), { m: dinero(c.gastos_fijos, moneda) });
  }
  return t(c.gastos === "dentro" ? "cot_gl_dentro" : "cot_gl_comprobar");
}

function cuantosDias(n) {
  return n === 1 ? t("cot_un_dia") : reemplazar(t("cot_n_dias"), { n });
}

function cuantosEquipos(n) {
  return n === 1 ? t("cot_un_equipo") : reemplazar(t("cot_n_equipos"), { n });
}

/* Lo que lleva, dicho en una linea: "Conductor de seguridad + SUV
   Blindada, en paquete". Sale de los renglones, sin repetirlos. */
function queLleva(lineas) {
  const vistos = [];
  for (const l of lineas) {
    if (l.tipo === "viaticos") continue;
    const texto = l.tipo === "paquete"
      ? reemplazar(t("cot_en_paquete"), { p: l.descripcion })
      : l.descripcion;
    if (!vistos.includes(texto)) vistos.push(texto);
  }
  return vistos.join(" · ");
}

function vistaAutorizada(caja, d) {
  const c = d.vigente;
  const moneda = c.moneda;
  const renglones = h("div", { hidden: "hidden", style: "margin-top:12px" },
    tablaDeRenglones(c.lineas, d, moneda));
  const ver = h("button", { clase: "claro chico", type: "button",
    onclick: () => {
      renglones.hidden = !renglones.hidden;
      ver.textContent = t(renglones.hidden ? "cot_ver_renglones" : "cot_ocultar_renglones");
    } }, t("cot_ver_renglones"));

  const registro = c.registrada_por
    ? reemplazar(t("cot_registro"), { p: c.registrada_por, f: fecha(c.registrada_el) })
    : reemplazar(t("cot_registro_sin"), { f: fecha(c.registrada_el) });

  const partes = [
    cabeza(reemplazar(t("cot_autorizada_v"), { v: c.version }), "ok"),
    h("div", { clase: "rejilla cuatro", style: "margin-top:12px" },
      h("div", {}, h("div", { clase: "chico gris" }, t("cot_total")),
        h("div", { clase: "cifra", style: "font-size:19px" }, dinero(c.total, moneda)),
        /* El PDF de Cotizaciones dice el total con IVA (seccion 114); aqui
           va el de antes de IVA, que es contra el que compara el cierre. */
        h("div", { clase: "chico gris" }, t("cot_antes_iva"))),
      h("div", {}, h("div", { clase: "chico gris" }, t("cot_la_autorizo")),
        h("b", {}, c.autorizada_por || "—"),
        h("div", { clase: "chico gris" }, c.autorizada_el ? fecha(c.autorizada_el) : "—")),
      folioDe(c),
      h("div", {}, h("div", { clase: "chico gris" }, t("cot_los_gastos")),
        h("b", {}, textoDeGastos(c, moneda)))),
    h("p", { clase: "chico gris", style: "margin:12px 0 0" },
      `${cuantosDias(c.dias)} · ${queLleva(c.lineas)}. ${registro}`),
  ];
  if (c.motivo) {
    partes.push(h("p", { clase: "chico gris", style: "margin:4px 0 0" },
      reemplazar(t("cot_version_motivo"), { v: c.version, m: c.motivo })));
  }
  /* En otra moneda se quedo con el tipo de cambio de ese dia (seccion 82). */
  if (c.tipo_cambio && d.moneda_local && moneda !== d.moneda_local) {
    partes.push(h("p", { clase: "chico gris", style: "margin:4px 0 0" },
      reemplazar(t("cie_cot_otra_moneda"), {
        m: moneda, l: d.moneda_local, t: c.tipo_cambio.tasa,
        f: fecha(c.registrada_el) })));
  }
  const acciones = h("div", { clase: "acciones", style: "margin-top:12px" }, ver);
  if (puedeArmar(d)) {
    acciones.append(h("button", { clase: "claro chico", type: "button",
      onclick: () => armar(caja, d) }, t("cot_recotizar")));
  }
  partes.push(acciones);
  if (d.con_visto_bueno) {
    partes.push(h("p", { clase: "chico gris", style: "margin:8px 0 0" },
      t("cot_tras_visto_bueno")));
  }
  partes.push(renglones);
  return partes;
}

/* La que nacio en Cotizaciones (seccion 114) dice su folio --con enlace a
   la cotizacion-- y deja bajar el PDF que se le mando al cliente. La que
   se registro aqui sigue diciendo su folio de Odoo, si lo trae. */
function folioDe(c) {
  if (!c.folio) {
    return h("div", {}, h("div", { clase: "chico gris" }, t("cot_folio_odoo")),
      h("b", {}, c.folio_odoo || "—"));
  }
  const ve = tiene(sesion.usuario, "cotizaciones.ver");
  const nombre = `${c.folio} V${c.version}`;
  return h("div", {}, h("div", { clase: "chico gris" }, t("cot_folio_connect")),
    ve ? h("a", { href: `#/cotizacion/${c.id}`, clase: "enlace" }, nombre) : h("b", {}, nombre),
    ve && c.tiene_pdf ? h("div", {}, h("button", { clase: "enlace chico", type: "button",
      onclick: async () => {
        try { await bajar(`/cotizaciones/eventual/${c.id}/pdf?bajar=true`); }
        catch (err) { mensaje(err.message, "grave"); }
      } }, t("cot_pdf_enviado"))) : null);
}

/* ------------------------------------------------------------ los renglones */

function nombreModalidad(codigo, horas) {
  const nombre = MODALIDAD[codigo] ? t(MODALIDAD[codigo]) : (codigo || "—");
  return horas ? reemplazar(t("cot_modalidad_horas"), { m: nombre, h: horas }) : nombre;
}

/* Una tabla por equipo, con los dias en su orden. Cada dia dice su
   modalidad una sola vez; lo que va en paquete lo dice su etiqueta. Los
   gastos a monto fijo no son de ningun dia: van al pie. */
function tablaDeRenglones(lineas, d, moneda, alPintarDia = null) {
  const equipos = [...new Set(d.dias.map(x => x.equipo))];
  const caja = h("div");
  for (const equipo of equipos) {
    const dias = d.dias.filter(x => x.equipo === equipo);
    const cuerpo = h("tbody");
    dias.forEach((dia, i) => {
      const suyas = lineas.filter(l => l.equipo === equipo && l.fecha === dia.fecha
                                       && l.tipo !== "viaticos");
      const etiquetaDia = h("td", {},
        h("b", {}, reemplazar(t("cot_dia_n"), { n: i + 1 })), " · ", fecha(dia.fecha));
      const modalidad = h("td", {}, nombreModalidad(dia.modalidad, dia.horas));
      if (!suyas.length) {
        cuerpo.append(h("tr", {}, etiquetaDia, modalidad,
          h("td", { clase: "gris", colspan: "4" }, t("cot_no_se_cotiza"))));
      }
      suyas.forEach((l, j) => {
        cuerpo.append(h("tr", {},
          j === 0 ? etiquetaDia : h("td"),
          j === 0 ? modalidad : h("td"),
          h("td", {}, l.descripcion,
            l.tipo === "paquete" ? [" ", etiqueta(t("cot_paquete"), "azul")] : ""),
          h("td", { clase: "der num" }, String(l.cantidad)),
          h("td", { clase: "der num" }, dinero(l.precio, moneda)),
          h("td", { clase: "der num" }, dinero(l.importe, moneda))));
      });
      if (alPintarDia) alPintarDia(cuerpo, equipo, dia, etiquetaDia);
    });
    caja.append(
      equipos.length > 1 ? h("h4", { style: "margin:10px 0 6px" },
        reemplazar(t("cot_equipo"), { e: equipo })) : "",
      h("table", { clase: "lista" },
        h("thead", {}, h("tr", {},
          h("th", {}, t("cot_col_dia")), h("th", {}, t("cot_col_modalidad")),
          h("th", {}, t("cot_col_que")), h("th", { clase: "der" }, t("cot_col_cant")),
          h("th", { clase: "der" }, t("cot_col_precio")),
          h("th", { clase: "der" }, t("cot_col_importe")))),
        cuerpo));
  }
  const gastos = lineas.filter(l => l.tipo === "viaticos");
  if (gastos.length) {
    const total = gastos.reduce((s, l) => s + Number(l.importe), 0);
    caja.append(h("p", { clase: "chico gris", style: "margin:6px 0 0" },
      reemplazar(t("cot_incluye_gastos"), { m: dinero(total, moneda) })));
  }
  return caja;
}

/* ------------------------------------------------------------ armarla */

/* Lo que lleva un dia: [{tipo, id, cantidad}]. Sale de los renglones
   (el paquete lleva el rol y la unidad) o de lo asignado. */
function deRenglones(lineas) {
  const cuenta = {};
  const sumar = (tipo, id, n) => {
    if (!id) return;
    const k = `${tipo}:${id}`;
    cuenta[k] = cuenta[k] || { tipo, id, cantidad: 0 };
    cuenta[k].cantidad += n;
  };
  for (const l of lineas) {
    if (l.tipo === "paquete") {
      sumar("recurso", l.perfil_id, l.cantidad);
      sumar("vehiculo", l.categoria_id, l.cantidad);
    } else if (l.tipo === "recurso") {
      sumar("recurso", l.perfil_id, l.cantidad);
    } else if (l.tipo === "vehiculo") {
      sumar("vehiculo", l.categoria_id, l.cantidad);
    }
  }
  return ordenar(Object.values(cuenta));
}

function deAsignado(dia) {
  const salida = [];
  for (const [id, n] of Object.entries((dia || {}).roles || {})) {
    salida.push({ tipo: "recurso", id: Number(id), cantidad: n });
  }
  for (const [id, n] of Object.entries((dia || {}).unidades || {})) {
    salida.push({ tipo: "vehiculo", id: Number(id), cantidad: n });
  }
  return ordenar(salida);
}

function ordenar(lleva) {
  return lleva.sort((a, b) => (a.tipo === b.tipo ? a.id - b.id
                                                 : a.tipo === "recurso" ? -1 : 1));
}

function igual(a, b) {
  const clave = (x) => ordenar(x.filter(i => i.id && i.cantidad > 0)
    .map(i => ({ ...i }))).map(i => `${i.tipo}:${i.id}:${i.cantidad}`).join("|");
  return clave(a) === clave(b);
}

/* Lo que mas se repite entre los dias de un equipo es su base; los dias
   distintos quedan como cambio de ese dia. Un dia sin nada --todavia sin
   gente asignada, o agregado despues de la cotizacion-- toma la base. */
function baseYCambios(porDia) {
  const fechas = Object.keys(porDia);
  let base = [];
  let mejor = -1;
  for (const f of fechas) {
    if (!porDia[f].length) continue;
    const veces = fechas.filter(g => igual(porDia[g], porDia[f])).length;
    if (veces > mejor) { mejor = veces; base = porDia[f]; }
  }
  const cambios = {};
  for (const f of fechas) {
    if (porDia[f].length && !igual(porDia[f], base)) {
      cambios[f] = porDia[f].map(i => ({ ...i }));
    }
  }
  return { base: base.map(i => ({ ...i })), cambios };
}

function estadoInicial(d) {
  const equipos = {};
  const porEquipo = {};
  for (const dia of d.dias) {
    (porEquipo[dia.equipo] = porEquipo[dia.equipo] || []).push(dia.fecha);
  }
  const hayAsignado = Object.values(d.asignado || {}).some(e =>
    Object.values(e).some(x => Object.keys(x.roles).length
                               || Object.keys(x.unidades).length));
  for (const [equipo, fechas] of Object.entries(porEquipo)) {
    const porDia = {};
    for (const f of fechas) {
      if (d.vigente) {
        porDia[f] = deRenglones(d.vigente.lineas.filter(
          l => l.equipo === equipo && l.fecha === f));
      } else if (hayAsignado) {
        porDia[f] = deAsignado(((d.asignado || {})[equipo] || {})[f]);
      } else {
        porDia[f] = [];
      }
    }
    const { base, cambios } = baseYCambios(porDia);
    equipos[equipo] = {
      base: base.length ? base : [{ tipo: "recurso", id: null, cantidad: 1 }],
      cambios,
    };
  }
  const c = d.vigente;
  const primero = d.quienes.length ? d.quienes[0].nombre : "";
  const quien = c ? c.autorizada_por : primero;
  const conocida = d.quienes.some(q => q.nombre === quien);
  return {
    equipos,
    gastos: c ? c.gastos : "comprobar",
    monto: c && c.gastos === "fijo" ? String(Number(c.gastos_fijos)) : "",
    quien: quien && conocida ? quien : (quien ? OTRA_PERSONA : (primero || OTRA_PERSONA)),
    otra: quien && !conocida ? quien : "",
    el: d.hoy,
    folio: c ? (c.folio_odoo || "") : "",
    motivo: "",
  };
}

/* Los renglones que se mandan: por equipo y por dia, lo del dia si va
   distinto y si no la base del equipo. */
function renglonesDe(estado, d) {
  const salida = [];
  for (const dia of d.dias) {
    const e = estado.equipos[dia.equipo];
    const lleva = e.cambios[dia.fecha] || e.base;
    for (const i of lleva) {
      if (!i.id || !(Number(i.cantidad) > 0)) continue;
      salida.push({
        fecha: dia.fecha, equipo_clave: dia.equipo, tipo: i.tipo,
        cantidad: Number(i.cantidad),
        ...(i.tipo === "recurso" ? { perfil_id: i.id } : { categoria_id: i.id }),
      });
    }
  }
  return salida;
}

/* Un rol o una unidad con su cuantos, en una sola pieza. */
function pieza(item, opciones, alCambiar, alQuitar) {
  const numero = h("input", { type: "number", min: "0", step: "1",
    value: String(item.cantidad),
    oninput: () => { item.cantidad = Number(numero.value || 0); alCambiar(); } });
  const escoger = h("select", {
    onchange: () => { item.id = escoger.value ? Number(escoger.value) : null; alCambiar(); } },
    h("option", { value: "" }, t(item.tipo === "recurso" ? "cot_escoge_rol" : "cot_escoge_unidad")),
    ...opciones.map(o => h("option", { value: String(o.id) }, o.nombre)));
  escoger.value = item.id ? String(item.id) : "";
  return h("span", { clase: "cot-lleva" }, numero, escoger,
    h("button", { clase: "claro chico", type: "button", title: t("cot_quitar"),
      "aria-label": t("cot_quitar"), onclick: alQuitar }, "×"));
}

/* La fila de lo que lleva: sus piezas y los botones para agregar. */
function filaDeLoQueLleva(lista, d, alCambiar, extra = []) {
  const fila = h("div", { clase: "cot-fila-lleva" });
  const repintar = () => {
    fila.replaceChildren(
      ...lista.map((item, i) => pieza(item,
        item.tipo === "recurso" ? d.roles : d.unidades, alCambiar,
        () => { lista.splice(i, 1); repintar(); alCambiar(); })),
      h("button", { clase: "claro chico", type: "button",
        onclick: () => { lista.push({ tipo: "recurso", id: null, cantidad: 1 });
                         repintar(); } }, t("cot_otro_rol")),
      h("button", { clase: "claro chico", type: "button",
        onclick: () => { lista.push({ tipo: "vehiculo", id: null, cantidad: 1 });
                         repintar(); } }, t("cot_otra_unidad")),
      ...extra);
  };
  repintar();
  return fila;
}

function armar(caja, d) {
  const estado = estadoInicial(d);
  const version = d.siguiente_version;
  const moneda = d.tarifario.moneda;
  const recotiza = Boolean(d.vigente);
  let ultimo = null;          // la ultima vista previa buena
  let turno = 0;              // para no pintar una respuesta vieja
  let espera = null;

  const tablas = h("div");
  const avisoPrecios = h("div");
  const total = h("div", { clase: "cifra" }, "—");
  const pieTotal = h("div", { clase: "chico gris" }, "");
  const guardar = h("button", { type: "button", disabled: "disabled",
    onclick: () => mandar() }, t("cot_guardar"));
  const cancelar = h("button", { clase: "claro", type: "button",
    onclick: () => pintar(caja, d) }, t("cot_cancelar"));

  /* ---- 1: lo que lleva cada dia */
  const equipos = h("div");
  const pintarEquipos = () => {
    equipos.replaceChildren();
    for (const [equipo, e] of Object.entries(estado.equipos)) {
      const tomar = h("button", { clase: "claro chico", type: "button",
        onclick: () => {
          const porDia = {};
          for (const dia of d.dias.filter(x => x.equipo === equipo)) {
            porDia[dia.fecha] = deAsignado(((d.asignado || {})[equipo] || {})[dia.fecha]);
          }
          if (!Object.values(porDia).some(x => x.length)) {
            mensaje(t("cot_nada_asignado"), "alerta");
            return;
          }
          const r = baseYCambios(porDia);
          e.base.splice(0, e.base.length, ...(r.base.length ? r.base
            : [{ tipo: "recurso", id: null, cantidad: 1 }]));
          e.cambios = r.cambios;
          pintarEquipos();
          recalcular();
        } }, t("cot_tomar_asignado"));
      equipos.append(
        h("h4", { style: "margin:14px 0 8px" },
          `${t("cot_paso_lleva")} · ${reemplazar(t("cot_equipo"), { e: equipo })}`),
        filaDeLoQueLleva(e.base, d, recalcular, [tomar]),
        h("div", { "data-equipo": equipo }));
    }
    pintarTablas();
  };

  /* La tabla de cada equipo con los precios de la vista previa, y en
     cada dia el boton para que ese dia vaya distinto. */
  const pintarTablas = () => {
    const lineas = ultimo ? ultimo.lineas : [];
    for (const [equipo, e] of Object.entries(estado.equipos)) {
      const lugar = equipos.querySelector(`[data-equipo="${CSS.escape(equipo)}"]`);
      if (!lugar) continue;
      const soloEste = { ...d, dias: d.dias.filter(x => x.equipo === equipo) };
      lugar.replaceChildren(tablaDeRenglones(lineas, soloEste, moneda,
        (cuerpo, eq, dia, celda) => {
          const distinto = e.cambios[dia.fecha];
          celda.append(h("div", {},
            h("button", { clase: "enlace chico", type: "button",
              onclick: () => {
                if (distinto) delete e.cambios[dia.fecha];
                else e.cambios[dia.fecha] = e.base.map(i => ({ ...i }));
                pintarTablas();
                recalcular();
              } }, t(distinto ? "cot_igual_que_todos" : "cot_cambiar_dia"))));
          if (distinto) {
            cuerpo.append(h("tr", { clase: "cot-dia-otro" },
              h("td", { colspan: "6" },
                h("div", { clase: "chico gris", style: "margin:0 0 6px" },
                  reemplazar(t("cot_dia_distinto"), { d: fecha(dia.fecha) })),
                filaDeLoQueLleva(distinto, d, recalcular))));
          }
        }));
    }
  };

  /* ---- 2: los gastos */
  const monto = h("input", { type: "text", inputmode: "decimal",
    placeholder: "0.00", value: estado.monto, clase: "cot-monto",
    oninput: () => { estado.monto = monto.value; recalcular(); } });
  const opcionGastos = (valor, texto, extra = null) => {
    const radio = h("input", { type: "radio", name: "cot_gastos", value: valor,
      onchange: () => { estado.gastos = valor; recalcular(); } });
    radio.checked = estado.gastos === valor;
    return h("label", { clase: "opcion", style: "margin:0 0 6px" }, radio, texto, extra);
  };
  const gastos = h("div", { clase: "bloque-radio", style: "margin:0 0 16px" },
    opcionGastos("dentro", t("cot_g_dentro")),
    opcionGastos("fijo", t("cot_g_fijo"), monto),
    opcionGastos("comprobar", t("cot_g_comprobar")));

  /* ---- 3: la autorizacion */
  const otra = h("input", { type: "text", maxlength: "160",
    placeholder: t("cot_nombre_otra"), value: estado.otra,
    oninput: () => { estado.otra = otra.value; revisarListo(); } });
  const quien = h("select", {
    onchange: () => {
      estado.quien = quien.value;
      otra.hidden = quien.value !== OTRA_PERSONA;
      revisarListo();
    } },
    ...d.quienes.map(q => h("option", { value: q.nombre },
      q.solicita ? reemplazar(t("cot_quien_solicita"), { n: q.nombre }) : q.nombre)),
    h("option", { value: OTRA_PERSONA }, t("cot_otra_persona")));
  quien.value = estado.quien;
  otra.hidden = estado.quien !== OTRA_PERSONA;
  const dia = h("input", { type: "date", value: estado.el, max: d.hoy,
    oninput: () => { estado.el = dia.value; revisarListo(); } });
  const folio = h("input", { type: "text", maxlength: "40", value: estado.folio,
    oninput: () => { estado.folio = folio.value; } });
  const motivo = h("textarea", { rows: "2", maxlength: "400",
    placeholder: t("cot_motivo_ayuda"),
    oninput: () => { estado.motivo = motivo.value; revisarListo(); } });

  const autorizacion = h("div", {},
    h("div", { clase: "rejilla tres" },
      h("div", {}, h("label", {}, t("cot_quien"), h("span", { clase: "obligatorio", title: t("obligatorio") }, " *")), quien, otra),
      h("div", {}, h("label", {}, t("cot_el_dia"), h("span", { clase: "obligatorio", title: t("obligatorio") }, " *")), dia),
      h("div", {}, h("label", {}, t("cot_folio")), folio)),
    recotiza ? h("div", { style: "margin-top:12px" },
      h("label", {}, t("cot_motivo")), motivo) : "");

  /* ---- lo que falta para guardar */
  const nombreDeQuien = () => (estado.quien === OTRA_PERSONA
    ? estado.otra.trim() : estado.quien);
  const faltante = () => {
    if (!ultimo) return null;
    if (estado.gastos === "fijo" && !(Number(estado.monto) > 0)) return t("cot_falta_monto");
    if (!nombreDeQuien()) return t("cot_falta_quien");
    if (!estado.el) return t("cot_falta_dia");
    if (recotiza && !estado.motivo.trim()) return t("cot_falta_motivo");
    return null;
  };
  const queFalta = h("div", { clase: "chico gris", style: "margin-top:6px" });
  const revisarListo = () => {
    const falta = faltante();
    queFalta.textContent = falta || "";
    if (ultimo && !falta) guardar.removeAttribute("disabled");
    else guardar.setAttribute("disabled", "disabled");
  };

  /* ---- los precios: se piden al servidor, que arma igual que al
     guardar --con los paquetes que la lista pacta-- sin guardar nada. */
  function recalcular() {
    clearTimeout(espera);
    espera = setTimeout(pedirPrecios, ESPERA_PRECIOS);
  }

  async function pedirPrecios() {
    const lineas = renglonesDe(estado, d);
    const mio = ++turno;
    avisoPrecios.replaceChildren();
    if (!lineas.length) {
      ultimo = null;
      avisoPrecios.append(aviso(t("cot_falta_algo"), "alerta"));
      pintarTablas();
      pintarTotal();
      revisarListo();
      return;
    }
    /* Sin el monto todavia no hay renglon de gastos: lo demas se calcula
       como si fueran dentro del precio, y abajo dice que falta el monto. */
    avisoPrecios.append(h("p", { clase: "chico gris" }, t("cot_calculando")));
    try {
      const r = await api.post("/cotizaciones/vista-previa", {
        servicio_id: d.servicio_id, lineas,
        gastos: estado.gastos === "fijo" && !(Number(estado.monto) > 0)
          ? "dentro" : estado.gastos,
        monto_gastos: estado.gastos === "fijo" && Number(estado.monto) > 0
          ? Number(estado.monto) : null,
      });
      if (mio !== turno) return;
      ultimo = r;
      avisoPrecios.replaceChildren();
    } catch (err) {
      if (mio !== turno) return;
      ultimo = null;
      avisoPrecios.replaceChildren(aviso(err.message, "grave"));
    }
    pintarTablas();
    pintarTotal();
    revisarListo();
  }

  const pintarTotal = () => {
    if (!ultimo) {
      total.textContent = "—";
      pieTotal.textContent = "";
      return;
    }
    total.textContent = dinero(ultimo.total, moneda);
    const g = { dentro: "cot_g_corto_dentro", fijo: "cot_g_corto_fijo",
                comprobar: "cot_g_corto_comprobar" }[estado.gastos];
    pieTotal.textContent = [cuantosDias(ultimo.dias), cuantosEquipos(ultimo.equipos),
                            t(g)].join(" · ");
  };

  async function mandar() {
    const falta = faltante();
    if (falta) { mensaje(falta, "alerta"); return; }
    guardar.setAttribute("disabled", "disabled");
    guardar.textContent = t("cot_guardando");
    try {
      const r = await api.post("/cotizaciones/autorizada", {
        servicio_id: d.servicio_id, lineas: renglonesDe(estado, d),
        gastos: estado.gastos,
        monto_gastos: estado.gastos === "fijo" ? Number(estado.monto) : null,
        autorizada_por: nombreDeQuien(), autorizada_el: estado.el,
        folio_odoo: estado.folio.trim() || null,
        motivo: recotiza ? estado.motivo.trim() : null,
      });
      mensaje(reemplazar(t("cot_guardada"), { v: r.version }), "ok");
      /* El estatus del servicio y el visto bueno dependen de ella. */
      setTimeout(() => location.reload(), 900);
    } catch (err) {
      guardar.textContent = t("cot_guardar");
      revisarListo();
      mensaje(errorAlGuardar(err), "grave");
    }
  }

  caja.replaceChildren(
    cabeza(reemplazar(t("cot_armando"), { v: version }), "alerta"),
    h("p", { clase: "chico gris", style: "margin:8px 0 6px" },
      reemplazar(t("cot_de_la_lista"), { l: d.tarifario.nombre, m: moneda })),
    equipos,
    avisoPrecios,
    h("p", { clase: "chico gris", style: "margin:6px 0 16px" }, t("cot_nota_dias")),
    h("h4", { style: "margin:0 0 8px" }, t("cot_paso_gastos")),
    gastos,
    h("h4", { style: "margin:0 0 8px" }, t("cot_paso_autoriza")),
    autorizacion,
    h("div", { clase: "cot-pie" },
      h("div", {},
        h("div", { clase: "chico gris" }, reemplazar(t("cot_total_v"), { v: version })),
        total, pieTotal),
      h("div", {},
        h("div", { clase: "acciones", style: "margin:0" }, guardar, cancelar),
        queFalta)));
  pintarEquipos();
  recalcular();
  caja.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* El tipo de cambio que falta se dice en el idioma de la pantalla; lo
   demas, como lo manda el servidor. */
function errorAlGuardar(err) {
  const d = err && err.detalle;
  if (d && typeof d === "object" && d.motivo) {
    const clave = d.motivo === "no_se_convierte" ? "cie_sin_tc_no_se_convierte"
                                                 : "cie_sin_tc_mensaje";
    const accion = d.motivo === "no_se_convierte" ? "cie_sin_tc_accion_nada"
                                                  : "cie_sin_tc_accion";
    return `${reemplazar(t(clave), { m: d.moneda, l: d.local })} ${t(accion)}`;
  }
  return err.message;
}

/* La tarjeta de visto bueno y facturacion, para el eventual y para el
   mes del implantado. Seccion 59, sesion 3 del cierre en dos relojes.

   Dice siempre en que fase va --comprobacion, visto bueno, facturacion,
   cerrado-- y el reloj de esa fase, diciendo de quien es: el del
   personal mientras comprueba, el del consultor sin visto bueno, y 24
   horas desde que finanzas lo regreso. Antes solo se veia un reloj, sin
   decir de quien, y "Facturado" aparecia antes de que finanzas lo
   revisara.

   Aqui tambien se revisa el dinero del personal: cada persona con lo
   depositado y lo comprobado, cada ticket con su foto para validarlo o
   rechazarlo, y los botones para cerrar su dinero --o cerrarlo con
   descuento cuando ya vencio su plazo--. Sin esto el visto bueno no se
   podia dar: pedia los viaticos cerrados y no habia donde cerrarlos.

   La cuenta regresiva sale del limite y del momento que manda el
   servidor, los dos en hora del pais del servicio: el reloj de esta
   maquina solo mide cuanto ha pasado desde que llego la respuesta. */
import { api, sesion } from "./api.js";
import { aviso, conAyuda, dinero, entrada, etiqueta, h, hora,
         mensaje } from "./util.js";
import { IDIOMAS, t } from "./idioma.js";

/* ------------------------------------------------------------ fechas */

function dia(iso) {
  if (!iso) return "—";
  const f = new Date(iso);
  const dias = t("f_dias").split(",");
  return `${dias[f.getDay()]} ${f.getDate()}`;
}

function diaHora(iso) {
  return iso ? `${dia(iso)} · ${hora(iso)}` : "—";
}

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (x, [k, v]) => x.replaceAll(`{${k}}`, v ?? ""), texto);
}

/* ------------------------------------------------------------ el reloj

   Cada segundo, contra el momento del servidor. Vencido se dice en
   rojo; en la ultima hora, ambar. */
export function reloj(hasta, momento, pie, mediano = false) {
  const nodo = h("div", { clase: "reloj-cierre" + (mediano ? " mediano" : "") });
  if (!hasta) {
    nodo.append(h("span", { clase: "gris" }, t("srv_sin_plazo")));
    return nodo;
  }
  const fin = new Date(hasta).getTime();
  const base = new Date(momento).getTime();
  const arranque = Date.now();
  const clase = "reloj-cierre" + (mediano ? " mediano" : "");
  const latir = () => {
    if (!nodo.isConnected && Date.now() - arranque > 2000) return;
    const faltan = Math.floor((fin - (base + (Date.now() - arranque))) / 1000);
    if (faltan <= 0) {
      nodo.className = clase + " vencido";
      nodo.replaceChildren(h("span", {}, t("cie_vencido")),
        h("span", { clase: "pie-reloj" }, " " + pie));
      return;
    }
    const hh = String(Math.floor(faltan / 3600)).padStart(2, "0");
    const mm = String(Math.floor((faltan % 3600) / 60)).padStart(2, "0");
    const ss = String(faltan % 60).padStart(2, "0");
    nodo.className = clase + (faltan < 3600 ? " apurado" : "");
    nodo.replaceChildren(h("span", { clase: "num" }, `${hh}:${mm}:${ss}`),
      h("span", { clase: "pie-reloj" }, " " + pie));
    setTimeout(latir, 1000);
  };
  latir();
  return nodo;
}

/* Cuanto queda, en palabras cortas: "faltan 5 h", "fuera de plazo".
   Para la cartera, que no necesita un reloj corriendo por renglon. */
export function queda(minutos) {
  if (minutos === null || minutos === undefined) return "";
  if (minutos < 0) return t("cie_fuera_de_plazo");
  if (minutos < 60) return reemplazar(t("cie_n_min"), { n: minutos });
  return reemplazar(t("cie_n_h"), { n: Math.floor(minutos / 60) });
}

/* ------------------------------------------------------------ las fases */

const ORDEN = { comprobacion: 0, sin_visto_bueno: 1, devuelto: 1,
                en_facturacion: 2, aprobado: 3, facturado: 3 };

function paso(clase, marca, nombre, cuando) {
  return h("li", { clase },
    h("span", { clase: "punto" }, marca),
    h("b", {}, nombre),
    h("span", { clase: "cuando", html: cuando || "" }));
}

function esc(texto) {
  return String(texto ?? "").replace(/[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

function fases(c, tuyo) {
  const actual = c.fase ? ORDEN[c.fase] : -1;
  const estado = (i) => (i < actual || (i === 3 && actual === 3))
    ? "hecha" : (i === actual ? "actual" : "");
  const marca = (i) => (estado(i) === "hecha" ? "✓" : String(i + 1));
  const finComprobacion = c.visto_bueno_desde || c.comprobacion_hasta;

  const uno = actual === 0
    ? reemplazar(t("cie_paso_personal_hasta"), { f: esc(diaHora(c.comprobacion_hasta)) })
    : actual > 0
      ? `${esc(diaHora(c.abierto_en))} →<br>${esc(diaHora(finComprobacion))}`
      : "";

  let dos = tuyo ? t("cie_paso_tus_24") : t("cie_paso_sus_24");
  let claseDos = estado(1);
  if (c.fase === "sin_visto_bueno") {
    dos = reemplazar(tuyo ? t("cie_paso_tuyo_hasta") : t("cie_paso_consultor_hasta"),
                     { f: esc(diaHora(c.limite)) });
  } else if (c.fase === "devuelto") {
    claseDos = "regresada";
    dos = t("cie_paso_regresado");
  } else if (actual > 1) {
    dos = `${esc(diaHora(c.visto_bueno_en))}<br>`
        + (c.dentro_de_plazo === false ? t("cie_fuera_de_plazo")
                                       : t("cie_en_plazo"));
  }

  const tres = actual === 2 ? t("cie_paso_finanzas_revisa")
    : actual > 2 ? esc(c.factura || t("cie_sin_factura"))
    : t("cie_paso_finanzas");
  const cuatro = actual === 3 ? esc(diaHora(c.aprobado_en)) : "";

  return h("ol", { clase: "fases" },
    paso(estado(0), marca(0), t("cie_fase_comprobacion"), uno),
    paso(claseDos, claseDos === "regresada" ? "2" : marca(1),
         t("cie_fase_visto_bueno"), dos),
    paso(estado(2), marca(2), t("cie_fase_facturacion"), tres),
    paso(estado(3), marca(3), t("cie_fase_cerrado"), cuatro));
}

/* ------------------------------------------------------------ lo cotizado contra lo ejecutado */

/* Los gastos van en su propio renglon, con su trato (seccion 59): a
   precio alzado se factura el monto fijo de la propuesta, se gaste mas
   o menos; con gastos netos, lo comprobado, y el cliente recibe el
   desglose. */
function renglonGastos(g, moneda) {
  if (!g || !g.modo) return null;
  const cotizado = Number(g.cotizado || 0);
  const nombre = g.modo === "netos" ? t("cie_gastos_netos")
    : cotizado ? t("cie_gastos_alzado") : t("cie_gastos_incluidos");
  return h("tr", {},
    h("td", {}, nombre),
    h("td", { clase: "der num" + (cotizado ? "" : " gris") },
      cotizado ? dinero(cotizado, moneda) : "—"),
    h("td", { clase: "der num" },
      reemplazar(t("cie_comprobados"), { m: dinero(g.comprobado, moneda) })),
    h("td", { clase: "der num" + (Number(g.a_facturar) ? "" : " gris") },
      Number(g.a_facturar) || g.modo === "netos"
        ? dinero(g.a_facturar, moneda) : "—"));
}

function notaGastos(g, moneda) {
  if (!g || !g.modo) return null;
  if (g.modo === "netos") return t("cie_nota_netos");
  const cotizado = Number(g.cotizado || 0);
  if (!cotizado) return t("cie_nota_incluidos");
  const dif = cotizado - Number(g.comprobado || 0);
  if (dif >= 0) {
    return reemplazar(t("cie_nota_alzado_margen"), { m: dinero(dif, moneda) });
  }
  return reemplazar(t("cie_nota_alzado_absorbe"), { m: dinero(-dif, moneda) });
}

function comparativoEventual(cmp, moneda) {
  const servicio = h("tr", {},
    h("td", {}, reemplazar(t("cie_servicio_dias"), {
      d: cmp.ejecutado.dias, e: cmp.ejecutado.equipos })),
    h("td", { clase: "der num" }, dinero(cmp.cotizacion.servicio, moneda)),
    h("td", { clase: "der num" }, dinero(cmp.a_facturar.servicio, moneda)),
    h("td", { clase: "der num" }, dinero(cmp.a_facturar.servicio, moneda)));
  const diferencia = Number(cmp.diferencia || 0);
  return {
    encabezados: [t("cie_col_cotizado"), t("cie_col_ejecutado"),
                  t("cie_col_a_facturar")],
    renglones: [servicio, renglonGastos(cmp.gastos, moneda)],
    total: cmp.a_facturar.total,
    notas: [diferencia ? reemplazar(t("cie_nota_diferencia"), {
              m: (diferencia > 0 ? "+" : "−") + dinero(Math.abs(diferencia), moneda) })
            : null,
            notaGastos(cmp.gastos, moneda)],
  };
}

function comparativoMes(cmp, moneda) {
  const r = [];
  const tr = (a, b, c, d) => h("tr", {}, h("td", {}, a),
    h("td", { clase: "der num" }, b), h("td", { clase: "der num" }, c),
    h("td", { clase: "der num" }, d));
  if (cmp.esquema === "mes_completo") {
    r.push(tr(t("cie_mes_completo"), dinero(cmp.contratado.importe, moneda),
              dinero(cmp.trabajado.importe, moneda),
              dinero(cmp.trabajado.importe, moneda)));
  } else {
    const d = cmp.trabajado.desglose || {};
    r.push(tr(t("cie_dias_base"), cmp.contratado.dias_base,
              cmp.trabajado.dias_base, dinero(d.dias_base || 0, moneda)));
    if (cmp.trabajado.dias_adicionales) {
      r.push(tr(t("cie_dias_adicionales"), "—",
                `${cmp.trabajado.dias_adicionales} · `
                + (cmp.trabajado.fechas_adicionales || []).map(dia).join(", "),
                dinero(d.dias_adicionales || 0, moneda)));
    }
    if (Number(d.vehiculo_mes || 0)) {
      r.push(tr(t("cie_vehiculo"), t("cie_un_mes"), t("cie_un_mes"),
                dinero(d.vehiculo_mes, moneda)));
    }
  }
  r.push(renglonGastos(cmp.gastos, moneda));
  return {
    encabezados: [t("cie_col_contratado"), t("cie_col_trabajado"),
                  t("cie_col_importe")],
    renglones: r, total: cmp.a_facturar.total,
    notas: [notaGastos(cmp.gastos, moneda)],
  };
}

function tablaComparativo(cmp, esMes, moneda, desglose) {
  if (!cmp) return null;
  const d = esMes ? comparativoMes(cmp, moneda) : comparativoEventual(cmp, moneda);
  const cuerpo = h("tbody", {}, ...d.renglones.filter(Boolean),
    h("tr", { clase: "total" },
      h("td", {}, h("b", {}, t("cie_a_facturar"))), h("td"), h("td"),
      h("td", { clase: "der num" }, h("b", {}, dinero(d.total, moneda)))));
  return h("div", {},
    h("h4", { clase: "seccion" },
      esMes ? t("cie_contratado_contra") : t("cie_cotizado_contra")),
    h("table", { clase: "tabla-cierre" },
      h("thead", {}, h("tr", {}, h("th"),
        ...d.encabezados.map(x => h("th", { clase: "der" }, x)))),
      cuerpo),
    ...d.notas.filter(Boolean).map(n =>
      h("p", { clase: "gris chico", style: "margin:4px 0 0" }, n)),
    cmp.gastos && cmp.gastos.modo === "netos" && desglose
      ? botonDesglose(desglose) : null);
}

/* El desglose se abre con la sesion puesta, igual que el task sheet: en
   una pestana nueva perderia el token. Sale en el idioma del cliente;
   el selector sirve para el dia que el cliente lo pide en otro. */
function botonDesglose(ruta) {
  const lengua = h("select", { clase: "chico", style: "width:auto" },
    h("option", { value: "" }, t("cie_idioma_cliente")),
    ...IDIOMAS.map(i => h("option", { value: i.codigo }, i.nombre)));
  const abrir = async () => {
    const w = window.open("", "_blank");
    if (!w) return mensaje(t("srv_bloqueo_ventana"), "alerta");
    w.document.write('<p style="font:14px system-ui;padding:20px">'
                     + t("srv_preparando") + "</p>");
    try {
      const html = await api.get(
        ruta + (lengua.value ? `?idioma=${lengua.value}` : ""), { crudo: true });
      w.document.open(); w.document.write(html); w.document.close();
    } catch (err) { w.close(); mensaje(err.message, "grave"); }
  };
  return h("div", { clase: "acciones", style: "margin-top:8px" },
    h("button", { clase: "claro chico", type: "button", onclick: abrir },
      t("cie_ver_desglose")), lengua);
}

/* ------------------------------------------------------------ antes de mandarlo */

/* Los asuntos del revisor llegan como el servidor los nombra --en clave,
   "dias_de_mas", o en su espanol sin acentos-- y aqui se dicen en el
   idioma de la pantalla. */
const ASUNTOS = {
  dias_de_mas: "cie_desv_dias_de_mas",
  dias_de_menos: "cie_desv_dias_de_menos",
  recurso_no_cotizado: "cie_desv_recurso_no_cotizado",
  horas_extra: "cie_desv_horas_extra",
  cobro_menor: "cie_desv_cobro_menor",
  viatico_sin_comprobar: "cie_desv_viatico_sin_comprobar",
  viatico_no_cerrado: "cie_desv_viatico_no_cerrado",
  viatico_excedido: "cie_desv_viatico_excedido",
  "Sin cotizacion autorizada": "cie_asu_sin_cotizacion",
  "Horas extra": "cie_desv_horas_extra",
  "Desviacion respaldada": "cie_asu_respaldada",
  "Jornada sin termino": "cie_asu_jornada",
  "Marca fuera de horario sin revisar": "cie_asu_marca",
  "Alertas sin atender": "cie_asu_alertas",
  "Viaticos sin cerrar": "cie_desv_viatico_no_cerrado",
};

/* Lo que ya dice el reloj de la tarjeta no se repite abajo. */
const DEL_RELOJ = ["Comprobacion en curso", "Plazo vencido", "Plazo por vencer",
                   "Regreso vencido", "Regreso por vencer"];

function asunto(texto) {
  return ASUNTOS[texto] ? t(ASUNTOS[texto]) : texto;
}

/* El dinero sin cerrar de una persona se dice con los numeros de su
   ficha --los mismos de "Viaticos del personal"-- y no con el texto del
   servidor. Sin ficha, se queda lo que mando el revisor. */
function dineroSinCerrar(o, personas) {
  const p = o.persona_id && personas.find(x => x.persona_id === o.persona_id);
  if (!p) return o;
  const m = p.moneda;
  const falta = Number(p.falta);
  const partes = [];
  if (falta > 0) {
    partes.push(reemplazar(t("cie_obs_le_faltan"), { m: dinero(falta, m) }));
  } else if (falta < 0) {
    partes.push(reemplazar(t("cie_obs_de_mas"), { m: dinero(-falta, m) }));
  }
  if (Number(p.por_depositar) > 0) {
    partes.push(reemplazar(t("cie_obs_por_depositar"),
                           { m: dinero(p.por_depositar, m) }));
  }
  if (Number(p.devolucion_en_revision) > 0) {
    partes.push(reemplazar(t("cie_obs_devolucion"),
                           { m: dinero(p.devolucion_en_revision, m) }));
  }
  const n = Number(p.sin_revisar);
  if (n) {
    partes.push(n === 1 ? t("cie_obs_sin_revisar_uno")
                        : reemplazar(t("cie_obs_sin_revisar"), { n }));
  }
  if (!partes.length) partes.push(t("cie_obs_ya_cuadra"));
  return {
    mensaje: `${p.nombre || "—"}: ${partes.join("; ")}`,
    accion: t("cie_obs_cierralo")
      + (p.vencido && falta > 0 ? " " + t("cie_obs_con_descuento") : ""),
  };
}

function antesDeMandarlo(revision, fallo, viaticos) {
  const zona = h("div", {}, h("h4", { clase: "seccion" }, t("cie_antes")));
  if (fallo) return zona.append(aviso(fallo, "alerta")), zona;
  const personas = (viaticos && viaticos.personas) || [];
  const obs = (revision && revision.observaciones) || [];
  const corregir = obs.filter(o => o.nivel === "corregir");
  const revisar = obs.filter(o => o.nivel !== "corregir"
                                  && !DEL_RELOJ.includes(o.asunto));
  if (!corregir.length) {
    zona.append(h("p", { clase: "verde chico", style: "margin:4px 0" },
      t("srv_sin_observaciones")));
  } else {
    zona.append(
      aviso(reemplazar(t("srv_antes_de_enviar"), { n: corregir.length }), "alerta"),
      h("ul", { style: "margin:6px 0;padding-left:18px" },
        ...corregir.map(o => {
          const dicho = dineroSinCerrar(o, personas);
          return h("li", { style: "margin-bottom:6px" },
            h("b", {}, asunto(o.asunto)), ": ",
            h("span", { clase: "chico" }, dicho.mensaje || ""),
            dicho.accion ? h("div", { clase: "chico gris" }, dicho.accion) : "");
        })));
  }
  if (revisar.length) {
    zona.append(h("div", { clase: "chico gris", style: "margin:4px 0 0" },
      h("b", {}, t("cie_para_revisar")), " ",
      ...revisar.map((o, i) => h("span", {},
        i ? " · " : "", `${asunto(o.asunto)}: ${o.mensaje || ""}`))));
  }
  return zona;
}

/* ------------------------------------------------------------ el dinero del personal */

function chipDePersona(p) {
  const m = p.moneda;
  if (p.estatus === "cerrado") return etiqueta(t("cie_chip_cerrado"), "ok");
  if (p.estatus === "con_descuento") {
    return etiqueta(t("cie_chip_con_descuento"), "cafe");
  }
  if (Number(p.por_depositar) > 0) {
    return etiqueta(reemplazar(t("cie_chip_por_depositar"),
                               { m: dinero(p.por_depositar, m) }), "info");
  }
  const falta = Number(p.falta);
  if (falta > 0) {
    return etiqueta(reemplazar(t("cie_chip_le_faltan"), { m: dinero(falta, m) }),
                    p.vencido ? "grave" : "alerta");
  }
  if (falta < 0) {
    return etiqueta(reemplazar(t("cie_chip_de_mas"), { m: dinero(-falta, m) }),
                    "info");
  }
  return etiqueta(t("cie_chip_cuadra"), "ok");
}

const TIPO_TICKET = { factura: "cie_ticket_factura", nota: "cie_ticket_nota" };
const CONCEPTO = {
  alimentos: "cie_con_alimentos", hospedaje: "cie_con_hospedaje",
  combustible: "cie_con_combustible", casetas: "cie_con_casetas",
  traslado_personal: "cie_con_traslado", otros: "cie_con_otros",
};

function nombreConcepto(c) {
  if (c.concepto === "otros" && c.descripcion) return c.descripcion;
  return CONCEPTO[c.concepto] ? t(CONCEPTO[c.concepto]) : c.concepto;
}

async function verFoto(c) {
  try {
    const url = await api.imagen(
      `/viaticos/${c.viatico_id}/comprobantes/${c.id}/imagen`);
    const w = window.open("", "_blank");
    if (!w) return mensaje(t("srv_bloqueo_ventana"), "alerta");
    w.document.write(`<img src="${url}" style="max-width:100%">`);
  } catch (err) { mensaje(err.message, "grave"); }
}

/* La miniatura se baja con la sesion puesta, como toda imagen del
   servidor. Si no carga, se queda el cuadro rayado: el boton sigue
   abriendo la foto. */
function miniatura(c) {
  const boton = h("button", { clase: "miniatura", type: "button",
    title: t("cie_ver_foto"), onclick: () => verFoto(c) });
  if (c.tiene_imagen) {
    api.imagen(`/viaticos/${c.viatico_id}/comprobantes/${c.id}/imagen`)
      .then(url => {
        boton.style.backgroundImage = `url("${url}")`;
        boton.style.backgroundSize = "cover";
      }).catch(() => {});
  } else {
    boton.disabled = true;
    boton.title = t("cie_sin_foto");
  }
  return boton;
}

function renglonComprobante(c, p, recargar) {
  const m = p.moneda;
  let estado;
  if (c.rechazado) {
    estado = h("div", { clase: "estado chico rojo" },
      reemplazar(t("cie_rechazado_por"), { m: c.motivo_rechazo || "" }));
  } else if (c.validado) {
    estado = h("div", { clase: "estado verde chico", style: "font-weight:650" },
      "✓ " + t("cie_validado"));
  } else if (p.estatus !== "abierto") {
    estado = h("div", { clase: "estado gris chico" }, t("cie_sin_revisar"));
  } else {
    estado = h("div", { clase: "estado" });
    const validar = h("button", { clase: "chico", type: "button",
      onclick: async (e) => {
        e.target.disabled = true;
        try {
          await api.post(`/viaticos/${c.viatico_id}/validar-comprobante/${c.id}`, {});
          await recargar();
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, t("cie_validar"));
    const rechazar = h("button", { clase: "claro chico", type: "button",
      onclick: () => {
        const motivo = entrada("motivo", { placeholder: t("cie_motivo_rechazo"),
                                           style: "max-width:220px" });
        const mandar = h("button", { clase: "chico", type: "button",
          onclick: async (e) => {
            if (motivo.value.trim().length < 3) {
              return mensaje(t("cie_falta_motivo"), "alerta");
            }
            e.target.disabled = true;
            try {
              await api.post(
                `/viaticos/${c.viatico_id}/rechazar-comprobante/${c.id}`,
                { motivo: motivo.value.trim() });
              mensaje(t("cie_rechazado_aviso"));
              await recargar();
            } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
          } }, t("cie_rechazar"));
        estado.replaceChildren(h("div", { clase: "acciones",
          style: "justify-content:flex-end" }, motivo, mandar));
        motivo.focus();
      } }, t("cie_rechazar"));
    estado.append(validar, " ", rechazar);
  }
  return h("div", { clase: "comprobante" },
    h("div", {}, miniatura(c), "  ", nombreConcepto(c), " ",
      h("span", { clase: "gris chico" },
        `· ${t(TIPO_TICKET[c.tipo] || "cie_ticket_nota")} · ${dia(c.fecha)}`)),
    h("div", { clase: "importe num" + (c.rechazado ? " tachado" : "") },
      dinero(c.monto, m)),
    estado);
}

/* Cerrar con descuento: por omision todo lo que falta; la empresa puede
   absorber una parte, pero tiene que decir por que. */
function formularioDescuento(p, recargar) {
  const m = p.moneda;
  const falta = Number(p.falta);
  const descuento = entrada("descuento", { type: "number", step: "1", min: "0",
    value: String(falta), clase: "num" });
  const absorbe = entrada("absorbe", { type: "number", value: "0",
    clase: "num", readonly: "readonly" });
  const motivo = entrada("motivo", { placeholder: t("cie_motivo_descuento_ej") });
  const porQueAbsorbe = entrada("motivo_absorcion",
    { placeholder: t("cie_motivo_absorcion_ej") });
  const cajaAbsorbe = h("div", { clase: "campo", hidden: true },
    h("label", {}, t("cie_por_que_absorbe")), porQueAbsorbe);
  descuento.addEventListener("input", () => {
    const d = Math.max(0, Math.min(falta, Number(descuento.value) || 0));
    absorbe.value = String(falta - d);
    cajaAbsorbe.hidden = !(falta - d > 0);
  });
  const boton = h("button", { clase: "chico", type: "button",
    onclick: async (e) => {
      if (motivo.value.trim().length < 5) {
        return mensaje(t("cie_falta_motivo"), "alerta");
      }
      e.target.disabled = true;
      try {
        const r = await api.post(
          `/viaticos/${p.viatico_id}/bolson/cerrar-con-descuento`, {
            motivo: motivo.value.trim(),
            monto_descuento: Number(descuento.value),
            motivo_absorcion: porQueAbsorbe.value.trim() || null,
          });
        mensaje(reemplazar(t("cie_descontado_aviso"), {
          m: dinero(r.descontado_al_personal, m) }));
        await recargar();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, t("cie_cerrar_con_descuento"));
  return h("div", { clase: "tarjeta lisa", style: "margin:0;padding:12px 14px" },
    h("div", { clase: "rejilla tres" },
      h("div", { clase: "campo" }, h("label", {}, t("cie_se_le_descuenta")), descuento),
      h("div", { clase: "campo" }, h("label", {}, t("cie_absorbe_empresa")), absorbe),
      h("div", { clase: "campo" }, h("label", {}, t("cie_por_que")), motivo)),
    cajaAbsorbe,
    h("p", { clase: "gris chico", style: "margin:0 0 8px" }, t("cie_descuento_pie")),
    h("div", { clase: "acciones" }, boton));
}

/* Por que todavia no se cierra, en el idioma de la pantalla: el
   servidor manda la clave y los numeros salen de la ficha. */
function queFrena(p) {
  const frena = p.frena_cierre || {};
  const m = p.moneda;
  switch (frena.codigo) {
    case "por_depositar":
      return reemplazar(t("cie_frena_por_depositar"),
                        { m: dinero(p.por_depositar, m) });
    case "devolucion":
      return reemplazar(t("cie_frena_devolucion"),
                        { m: dinero(p.devolucion_en_revision, m) });
    case "sin_revisar":
      return Number(p.sin_revisar) === 1
        ? t("cie_frena_sin_revisar_uno")
        : reemplazar(t("cie_frena_sin_revisar"), { n: p.sin_revisar });
    case "falta":
      return reemplazar(t("cie_frena_falta"), { m: dinero(p.falta, m) });
    case "de_mas":
      return reemplazar(t("cie_frena_de_mas"), { m: dinero(-Number(p.falta), m) });
    default:
      return [frena.mensaje, frena.que_hacer].filter(Boolean).join(". ")
        .replace(/\.\./g, ".").replace(/([^.])$/, "$1.");
  }
}

function pieDePersona(p, recargar) {
  if (p.estatus === "con_descuento") {
    return h("p", { clase: "chico gris", style: "margin:10px 0 0" },
      reemplazar(t("cie_se_desconto"), {
        d: dinero(p.descontado, p.moneda), a: dinero(p.absorbido, p.moneda),
        m: p.motivo_cierre || "" }));
  }
  if (p.estatus !== "abierto") return null;

  const plazo = (p.limite
    ? reemplazar(p.vencido ? t("cie_su_plazo_vencio") : t("cie_su_plazo_vence"),
                 { f: diaHora(p.limite) })
    : t("cie_su_plazo_no_arranca")) + ".";
  if (p.puede_cerrar) {
    const cerrar = h("button", { clase: "chico", type: "button",
      onclick: async (e) => {
        e.target.disabled = true;
        try {
          await api.post(`/viaticos/${p.viatico_id}/bolson/cerrar`, {});
          mensaje(t("cie_cerrado_aviso"));
          await recargar();
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, t("cie_cerrar_sus_viaticos"));
    return h("div", { clase: "acciones", style: "margin-top:10px" }, cerrar,
      h("span", { clase: "chico gris" }, t("cie_cuadra_pie")));
  }
  if (p.puede_descontar) {
    return h("div", {},
      h("p", { clase: "chico gris", style: "margin:10px 0 8px" },
        plazo + " " + t("cie_se_puede_descontar")),
      formularioDescuento(p, recargar));
  }
  return h("p", { clase: "chico gris", style: "margin:10px 0 0" },
    `${queFrena(p)} ${plazo}`);
}

function tarjetaPersona(p, recargar) {
  const m = p.moneda;
  const numeros = [
    reemplazar(t("cie_depositado_m"), { m: dinero(p.depositado, m) }),
    reemplazar(t("cie_comprobado_m"), { m: dinero(p.comprobado, m) }),
    Number(p.devuelto) ? reemplazar(t("cie_devuelto_m"), { m: dinero(p.devuelto, m) }) : null,
  ].filter(Boolean).join(" · ");
  const lista = p.comprobantes.length
    ? h("div", { clase: "comprobantes" },
        ...p.comprobantes.map(c => renglonComprobante(c, p, recargar)))
    : h("p", { clase: "chico gris", style: "margin:8px 0 0" }, t("cie_sin_tickets"));
  return h("div", { clase: "persona-viatico" },
    h("div", { clase: "cabeza" },
      h("div", {}, h("b", {}, p.nombre || "—"),
        p.puesto ? h("span", { clase: "chico gris" }, ` · ${p.puesto}`) : null),
      h("div", { clase: "chico num" }, numeros),
      chipDePersona(p)),
    lista,
    pieDePersona(p, recargar));
}

function resumenDelDinero(personas) {
  if (!personas.length) return null;
  return h("table", { clase: "tabla-cierre" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("cie_col_persona")),
      h("th", { clase: "der" }, t("cie_col_depositado")),
      h("th", { clase: "der" }, t("cie_col_comprobado")),
      h("th", { clase: "der" }, t("cie_col_falta")))),
    h("tbody", {}, ...personas.map(p => h("tr", {},
      h("td", {}, p.nombre || "—"),
      h("td", { clase: "der num" }, dinero(p.depositado, p.moneda)),
      h("td", { clase: "der num" }, dinero(p.comprobado, p.moneda)),
      p.estatus === "abierto"
        ? h("td", { clase: "der num", style: Number(p.falta) > 0
              ? "color:var(--alerta);font-weight:650" : "" },
            dinero(p.falta, p.moneda))
        : h("td", { clase: "der verde", style: "font-weight:650" },
            t("cie_chip_cerrado"))))));
}

function seccionDinero(viaticos, recargar) {
  if (!viaticos) return null;
  const personas = viaticos.personas || [];
  return h("div", {},
    h("h4", { clase: "seccion" }, t("cie_viaticos_personal")),
    personas.length
      ? h("div", {}, ...personas.map(p => tarjetaPersona(p, recargar)))
      : h("p", { clase: "chico gris" }, t("cie_sin_viaticos")));
}

/* ------------------------------------------------------------ la tarjeta */

/* `op`:
     titulo, ayuda     el encabezado con su "?"
     rutas             {estado, revision, viaticos, desglose}
     esMes             el cierre del mes del implantado
     lugar             donde se da el servicio: "hora de Ciudad de Mexico"
     moneda
     consultorId       para decir "tu" o "del consultor"
     alCambiar         para repintar lo de alrededor (el estatus) */
export function tarjetaCierre(op) {
  const caja = h("div", { clase: "tarjeta" });
  const pintar = async () => {
    let c;
    try {
      c = await api.get(op.rutas.estado);
    } catch (err) {
      caja.replaceChildren(conAyuda("h3", op.titulo, op.ayuda),
                           aviso(err.message, "alerta"));
      return;
    }
    const nodos = (await cuerpo(c, op, pintar)).filter(Boolean);
    caja.replaceChildren(conAyuda("h3", op.titulo, op.ayuda), ...nodos);
  };
  caja.append(conAyuda("h3", op.titulo, op.ayuda),
              h("p", { clase: "gris chico" }, t("imp_cargando")));
  pintar();
  return caja;
}

async function cuerpo(c, op, recargar) {
  const tuyo = !!(sesion.usuario && c.consultor
                  && sesion.usuario.persona_id === c.consultor.id);
  const m = op.moneda;
  const nodos = [];

  if (!c.existe) {
    nodos.push(fases(c, tuyo), h("p", { clase: "gris chico" },
      op.esMes ? t("cie_mes_sin_cierre") : t("cie_sin_cierre")));
    return nodos;
  }
  nodos.push(fases(c, tuyo));
  if (c.motivo === "cancelacion") {
    nodos.push(aviso(t("cie_es_cancelacion"), "alerta"));
  }

  const conRevision = ["sin_visto_bueno", "devuelto"].includes(c.fase);
  const conDinero = conRevision || c.fase === "comprobacion";
  const [revision, viaticos] = await Promise.all([
    conRevision ? api.get(op.rutas.revision).then(x => ({ x }),
                                                  e => ({ fallo: e.message }))
                : null,
    conDinero ? api.get(op.rutas.viaticos).catch(() => null) : null,
  ]);

  if (c.fase === "comprobacion") {
    nodos.push(
      reloj(c.reloj && c.reloj.hasta, c.momento, t("cie_reloj_personal"), true),
      h("p", { clase: "gris chico", style: "margin:6px 0 12px" },
        reemplazar(t("cie_comprobacion_pie"), { f: diaHora(c.abierto_en) })));
    const personas = viaticos ? viaticos.personas : [];
    /* Abierto o cerrado se recuerda al repintar: validar un ticket no
       tiene por que plegar lo que se esta revisando. */
    const detalle = h("div", { hidden: !op.verDinero },
                      seccionDinero(viaticos, recargar));
    nodos.push(resumenDelDinero(personas) || h("p", { clase: "chico gris" },
      t("cie_sin_viaticos")));
    if (personas.length) {
      const texto = () => (op.verDinero ? t("cie_ocultar_comprobantes")
                                        : t("cie_revisar_comprobantes"));
      nodos.push(h("div", { clase: "acciones", style: "margin-top:10px" },
        h("button", { clase: "claro chico", type: "button", onclick: (e) => {
          op.verDinero = !op.verDinero;
          detalle.hidden = !op.verDinero;
          e.target.textContent = texto();
        } }, texto())), detalle);
    }
    return nodos;
  }

  if (conRevision) {
    if (c.fase === "devuelto") {
      nodos.push(aviso(reemplazar(t("cie_regresado_por"), {
        f: diaHora(c.devuelto_en), m: c.devuelto_motivo || "" }), "alerta"),
        reloj(c.reloj && c.reloj.hasta, c.momento, t("cie_reloj_regreso"), true),
        h("p", { clase: "gris chico", style: "margin:6px 0 0" },
          reemplazar(c.dentro_de_plazo === false ? t("cie_regreso_fuera_pie")
                                                 : t("cie_regreso_pie"),
                     { f: diaHora(c.visto_bueno_en) })));
    } else {
      nodos.push(
        reloj(c.reloj && c.reloj.hasta, c.momento, t("cie_reloj_consultor")),
        h("p", { clase: "gris chico", style: "margin:4px 0 0" },
          reemplazar(t("cie_vence_pie"), { f: diaHora(c.limite),
                                           l: op.lugar || "" })));
    }
    const rev = revision && revision.x;
    nodos.push(
      tablaComparativo(rev && rev.comparativo, op.esMes, m, op.rutas.desglose),
      antesDeMandarlo(rev, revision && revision.fallo, viaticos),
      seccionDinero(viaticos, recargar));

    const zona = h("div", { style: "margin-top:10px" });
    const boton = h("button", { type: "button", onclick: async (e) => {
      if (!confirm(t("srv_confirmar_visto"))) return;
      e.target.disabled = true;
      try {
        const envio = await api.post(`/cierre/${c.cierre_id}/enviar-finanzas`, {});
        mensaje(t("srv_enviado_finanzas"));
        if (envio.factura && envio.factura.resultado !== "facturado") {
          mensaje(t("cie_factura_pendiente"), "alerta");
        }
        await recargar();
        if (op.alCambiar) op.alCambiar();
      } catch (err) {
        mensaje(err.message, "grave");
        const detalle = err.detalle;
        if (detalle && detalle.observaciones && detalle.observaciones.length) {
          zona.replaceChildren(antesDeMandarlo(
            { observaciones: detalle.observaciones }, "", viaticos));
        }
        e.target.disabled = false;
      }
    } }, t("cie_dar_visto_bueno"));
    nodos.push(h("div", { clase: "acciones", style: "margin-top:16px" }, boton), zona);
    return nodos;
  }

  /* Con el visto bueno dado: ya no hay reloj, hay constancias. */
  const plazo = c.dentro_de_plazo === false;
  const vb = reemplazar(plazo ? t("cie_diste_vb_fuera") : t("cie_diste_vb"), {
    f: diaHora(c.visto_bueno_en),
    q: c.consultor ? c.consultor.nombre : "" });
  const comision = c.comision;
  const lineaComision = !comision ? null
    : comision.estatus === "se_pierde" || comision.estatus === "perdida"
      ? t("cie_comision_se_pierde")
      : reemplazar(comision.generada
          ? (tuyo ? t("cie_tu_comision_generada") : t("cie_comision_generada"))
          : (tuyo ? t("cie_tu_comision") : t("cie_comision_de")),
          { m: dinero(comision.monto, comision.moneda || m),
            p: comision.porcentaje ?? "",
            q: c.consultor ? c.consultor.nombre : "" });
  const factura = c.factura
    ? reemplazar(t("cie_factura_odoo"), { f: c.factura,
                                          m: dinero(c.total, m) })
    : reemplazar(t("cie_factura_no_sale"), { m: dinero(c.total, m) });

  if (c.fase === "en_facturacion") {
    nodos.push(
      h("p", { clase: plazo ? "rojo" : "verde",
               style: "margin:0 0 6px;font-weight:650" }, vb),
      h("p", { style: "margin:0 0 6px" }, factura),
      c.factura_error && !c.factura
        ? h("p", { clase: "chico gris", style: "margin:0 0 6px" }, c.factura_error)
        : null,
      lineaComision ? h("p", { clase: "gris chico", style: "margin:0" },
                        lineaComision) : null);
    return nodos;
  }

  nodos.push(
    h("p", { style: "margin:0 0 6px" },
      reemplazar(t("cie_cerrado_por_finanzas"), { f: diaHora(c.aprobado_en) })),
    h("p", { clase: "gris chico", style: "margin:0" },
      [factura, lineaComision].filter(Boolean).join(" · ")));
  return nodos;
}

/* Facturacion: la pantalla de finanzas para cerrar lo que ya tiene el
   visto bueno del consultor (seccion 59).

   Los endpoints existian --aprobar, regresar, reintentar la factura-- y
   la pantalla no: finanzas no tenia donde aprobar un cierre. Aqui va lo
   que espera su aprobacion, cada servicio con su visto bueno (en plazo
   o no), lo que se factura y su factura. Un implantado va por mes. Al
   abrir un renglon: el comparativo, lo que hay que revisar y los
   botones.

   Aprobar no espera a la factura: el servicio se cierra y la factura se
   reintenta desde "Por facturar". Nunca sale dos veces: la que ya tiene
   folio de Odoo no se vuelve a mandar.

   Mientras la factura no se conecta con Odoo (seccion 96, decision 5 de
   Salvador del 28 sep), finanzas la hace alla y aqui la anota: «Ya se
   facturo en Odoo», con su folio y su fecha. La anotada a mano se corrige
   aqui; la que llega de Odoo, en Odoo.

   La cuarta pestana es el historial (seccion 69): todo lo cerrado desde
   el primer servicio, con filtros, en Excel, y con lo que pasa con las
   fotos de sus comprobantes. Vive en historial.js.

   La quinta, los tarifarios (seccion 77): que es cada producto de Odoo
   --lo confirma finanzas-- y el tarifario de cada cliente, como quedo de
   su lista de Odoo. Vive en tarifarios.js.

   Con la llave de la factura (seccion 117) lo que sale con el visto
   bueno es la prefactura en borrador: «Por facturar» se parte en «En
   Odoo» --lo que espera al facturista-- y «No se pudo mandar», con su
   porque. Los eventuales y los meses de los implantados van juntos;
   «Ver» los separa. Finanzas sigue aprobando aqui. */
import { api, sesion } from "./api.js";
import { botonOdoo, tablaDeRenglones } from "./cierre.js";
import { pestanaHistorial } from "./historial.js";
import { pestanaTarifarios } from "./tarifarios.js";
import { aviso, conAyuda, dinero, etiqueta, h, hora, mensaje,
         montos, tasa } from "./util.js";
import { t } from "./idioma.js";
import { CONSULTA, abre, tiene } from "./menu.js";

/* Quien puede abrir la pantalla del servicio: quien la tiene en su
   menu. Finanzas no: la suya es esta. */
function abreElServicio(f) {
  return f.contrato_id ? abre(sesion.usuario, "implantados", CONSULTA)
                       : abre(sesion.usuario, "servicios", CONSULTA);
}

/* Aprobar, regresar y volver a mandar la factura son de quien factura
   (seccion 73): direccion de operaciones mira esta pantalla sin tocar,
   y ya no ve botones que le contestan que no. */
function puedeFacturar() {
  return tiene(sesion.usuario, "cierre.facturar");
}

function dia(iso) {
  if (!iso) return "—";
  const f = new Date(iso);
  const dias = t("f_dias").split(",");
  return `${dias[f.getDay()]} ${f.getDate()} · ${hora(iso)}`;
}

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (x, [k, v]) => x.replaceAll(`{${k}}`, v ?? ""), texto);
}

const QUE_PASO = {
  sin_conexion: "fac_paso_sin_conexion",
  rechazada: "fac_paso_rechazada",
  sin_respuesta: "fac_paso_sin_respuesta",
  falta_dato: "fac_paso_falta_dato",
  /* Los de la prefactura (seccion 117). */
  sin_llave: "fac_paso_sin_llave",
  anterior_viva: "fac_paso_anterior_viva",
  no_cuadra: "fac_paso_no_cuadra",
  de_antes: "fac_paso_de_antes",
  cancelada_en_odoo: "fac_paso_cancelada_en_odoo",
};

const MESES = ["bon_mes_1", "bon_mes_2", "bon_mes_3", "bon_mes_4",
               "bon_mes_5", "bon_mes_6", "bon_mes_7", "bon_mes_8",
               "bon_mes_9", "bon_mes_10", "bon_mes_11", "bon_mes_12"];

function servicio(f) {
  return h("div", {},
    h("b", {}, f.folio),
    f.periodo ? h("span", {}, " ", etiqueta(
      `${t(MESES[f.mes - 1]).slice(0, 3)} ${f.anio}`, "info")) : "",
    h("div", { clase: "chico gris" }, f.cliente || ""));
}

/* Hace cuanto, para la prefactura: «hace 2 h», «ayer 18:20». */
function haceCuanto(iso) {
  if (!iso) return "";
  const minutos = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  /* Un reloj adelantado no dice «hace»: dice el dia. */
  if (minutos < 0) return dia(iso);
  if (minutos < 60) return reemplazar(t("fac_hace_min"), { n: Math.max(minutos, 1) });
  if (minutos < 12 * 60) return reemplazar(t("fac_hace_h"), { n: Math.floor(minutos / 60) });
  return dia(iso);
}

/* La prefactura de un renglon: «Prefactura en Odoo» y su borrador. */
function prefacturaDe(f) {
  return h("div", {}, etiqueta(t("fac_prefactura_en_odoo"), "azul"),
    h("div", { clase: "chico gris", style: "margin-top:4px" },
      reemplazar(t("fac_borrador_hace"), { n: f.prefactura.id,
                                           h: haceCuanto(f.prefactura.en) })));
}

function vistoBueno(f) {
  const fuera = f.dentro_de_plazo === false;
  return h("div", {}, dia(f.visto_bueno_en),
    h("div", { clase: "chico gris" }, `${f.consultor || "—"} · `,
      h("span", { style: `color:var(${fuera ? "--grave" : "--ok"});font-weight:650` },
        fuera ? t("cie_fuera_de_plazo") : t("cie_en_plazo"))));
}

function aFacturar(f, moneda) {
  moneda = f.moneda || moneda;
  const g = f.gastos || {};
  const monto = Number(g.monto || 0);
  /* Sin tipo de cambio los gastos en pesos no tienen cifra en dolares
     (seccion 82): se dice, no se inventa. */
  const pie = g.monto === null && g.modo ? t("fac_gastos_sin_tc")
    : g.modo === "netos"
      ? reemplazar(t("fac_con_gastos_netos"), { m: dinero(monto, moneda) })
      : monto ? reemplazar(t("fac_con_gastos_alzado"), { m: dinero(monto, moneda) })
              : t("fac_gastos_incluidos");
  return h("td", { clase: "num der" }, h("b", {}, dinero(f.total, moneda)),
    g.modo ? h("div", { clase: "chico gris" }, pie) : "");
}

function factura(f) {
  if (f.factura) return h("td", {}, folioDe(f));
  if (f.prefactura) return h("td", {}, prefacturaDe(f));
  return h("td", {}, etiqueta(t("fac_sin_factura"), "alerta"),
    f.que_paso ? h("div", { clase: "chico gris", style: "margin-top:4px" },
                   t(QUE_PASO[f.que_paso] || "fac_paso_falta_dato")) : "");
}

export async function pantallaFacturacion(main) {
  const moneda = "MXN";
  const sub = h("p", { clase: "sub" }, t("fac_sub"));
  main.append(conAyuda("h1", t("fac_titulo"), "ay_fac_titulo"), sub);
  const zona = h("div");
  main.append(zona);
  let pestana = "aprobar";
  /* Todos, solo los eventuales o solo los meses de los implantados. */
  let ver = "todos";

  const pintar = async () => {
    let b;
    try {
      b = await api.get("/cierre/facturacion");
    } catch (err) {
      zona.replaceChildren(aviso(err.message, "grave"));
      return;
    }
    const r = b.resumen;
    /* Con la llave de la factura (seccion 117): En Odoo y No se pudo
       mandar en lugar de Por facturar. */
    const llave = !!b.llave;
    sub.textContent = t(llave ? "fac_sub_llave" : "fac_sub");
    if (llave && pestana === "facturar") pestana = "en_odoo";
    if (!llave && ["en_odoo", "no_se_pudo"].includes(pestana)) pestana = "facturar";

    const tarjeta = (titulo, cifra, pie, color = "") => h("div", {},
      h("div", { clase: "chico gris" }, titulo),
      h("div", { clase: "cifra", style: color ? `color:var(${color})` : "" }, cifra),
      h("div", { clase: "chico gris num" }, pie));
    const porAprobarCifra = tarjeta(t("fac_por_aprobar"), r.por_aprobar.cuantos,
      /* Uno por moneda (seccion 82): los dolares no se suman a los
         pesos. */
      r.por_aprobar.montos ? montos(r.por_aprobar.montos, moneda)
                           : dinero(r.por_aprobar.monto, moneda));
    const cerradosCifra = tarjeta(
      reemplazar(t("fac_cerrados_en"), { m: t(MESES[r.cerrados.mes - 1]) }),
      r.cerrados.cuantos,
      r.cerrados.montos ? montos(r.cerrados.montos, moneda)
                        : dinero(r.cerrados.monto, moneda));
    const corte = h("div", { clase: "corte" }, porAprobarCifra,
      ...(llave
        ? [tarjeta(t("fac_en_odoo_por_timbrar"), r.en_odoo.cuantos,
                   r.en_odoo.cuantos ? montos(r.en_odoo.montos, moneda)
                                     : t("fac_nada_en_odoo_corto")),
           tarjeta(t("fac_no_se_pudo"), r.no_se_pudo.cuantos,
                   r.no_se_pudo.de_antes
                     ? reemplazar(t("fac_n_de_antes"), { n: r.no_se_pudo.de_antes })
                     : t("fac_se_reintenta"),
                   r.no_se_pudo.cuantos ? "--grave" : "")]
        : [tarjeta(t("fac_por_facturar"), r.por_facturar.cuantos,
                   b.odoo_configurado ? t("fac_odoo_no_acepto") : t("fac_sin_odoo"),
                   r.por_facturar.cuantos ? "--alerta" : "")]),
      cerradosCifra);

    const boton = (clave, texto) => h("button", {
      clase: `pestana ${pestana === clave ? "activa" : ""}`.trim(), type: "button",
      onclick: () => { pestana = clave; pintar(); } }, texto);
    const pestanas = h("div", { clase: "pestanas", style: "margin:0 0 12px" },
      boton("aprobar", reemplazar(t("fac_tab_aprobar"), { n: b.por_aprobar.length })),
      ...(llave
        ? [boton("en_odoo", reemplazar(t("fac_tab_en_odoo"), { n: b.en_odoo.length })),
           boton("no_se_pudo", reemplazar(t("fac_tab_no_se_pudo"),
                                          { n: b.no_se_pudo.length }))]
        : [boton("facturar", reemplazar(t("fac_tab_facturar"),
                                        { n: b.por_facturar.length }))]),
      boton("cerrados", t("fac_tab_cerrados")),
      tiene(sesion.usuario, "cierre.historial")
        ? boton("historial", t("fac_tab_historial")) : "",
      tiene(sesion.usuario, "cierre.ver")
        ? boton("tarifarios", t("fac_tab_tarifarios")) : "");

    const listas = { aprobar: b.por_aprobar, en_odoo: b.en_odoo,
                     no_se_pudo: b.no_se_pudo, facturar: b.por_facturar,
                     cerrados: b.cerrados };
    const lista = listas[pestana];
    const filtrar = (filas) => (ver === "todos" ? filas
      : filas.filter(f => (ver === "implantados") === !!f.contrato_id));
    const filas = lista ? filtrar(lista) : null;

    const cuerpo = pestana === "aprobar" ? porAprobar(filas, moneda, pintar)
      : pestana === "en_odoo" ? enOdoo(filas, moneda, pintar)
      : pestana === "no_se_pudo" ? noSePudo(filas, moneda, pintar)
      : pestana === "facturar" ? porFacturar(filas, moneda, pintar,
                                             b.odoo_configurado)
      : pestana === "historial" ? pestanaHistorial()
      : pestana === "tarifarios" ? pestanaTarifarios()
      : cerrados(filas, moneda, pintar);
    zona.replaceChildren(corte, pestanas,
      lista ? filtroVer(lista, ver, (v) => { ver = v; pintar(); }) : "",
      cuerpo);
  };
  await pintar();
}

/* «Ver»: todos, los eventuales o los implantados, con cuantos hay de
   cada uno en la pestana que esta abierta. */
function filtroVer(lista, ver, cambiar) {
  const implantados = lista.filter(f => f.contrato_id).length;
  const cuantos = { todos: lista.length, eventuales: lista.length - implantados,
                    implantados };
  const boton = (clave, texto) => h("button", {
    clase: ver === clave ? "pestana chico activa" : "pestana chico", type: "button",
    onclick: () => cambiar(clave) }, reemplazar(texto, { n: cuantos[clave] }));
  return h("div", { clase: "pestanas", style: "margin:0 0 12px;align-items:center" },
    h("span", { clase: "chico gris", style: "margin-right:4px" }, t("fac_ver")),
    boton("todos", t("fac_ver_todos")),
    boton("eventuales", t("fac_ver_eventuales")),
    boton("implantados", t("fac_ver_implantados")));
}

/* ------------------------------------------------------------ por aprobar */

function porAprobar(filas, moneda, repintar) {
  if (!filas.length) {
    return h("div", { clase: "tarjeta" }, h("div", { clase: "vacio" },
      t("fac_nada_por_aprobar")));
  }
  const cuerpo = h("tbody");
  for (const f of filas) {
    const extra = h("tr", { clase: "fila-extra", hidden: true },
      h("td", { colspan: "5", style: "padding:4px 14px 16px" }));
    const abrir = h("button", { clase: "claro chico", type: "button",
      onclick: async () => {
        extra.hidden = !extra.hidden;
        abrir.textContent = extra.hidden ? t("fac_revisar") : t("fac_cerrar_detalle");
        if (!extra.hidden) {
          extra.firstChild.replaceChildren(await detalle(f, moneda, repintar));
        }
      } }, t("fac_revisar"));
    cuerpo.append(
      h("tr", {}, h("td", {}, servicio(f)), h("td", {}, vistoBueno(f)),
        aFacturar(f, moneda), factura(f),
        h("td", { clase: "der" }, abrir)),
      extra);
  }
  return h("table", { clase: "lista" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("fac_col_servicio")), h("th", {}, t("fac_col_visto_bueno")),
      h("th", { clase: "der" }, t("cie_col_a_facturar")),
      h("th", {}, t("fac_col_factura")), h("th"))),
    cuerpo);
}

async function detalle(f, moneda, repintar) {
  moneda = f.moneda || moneda;
  const ruta = f.contrato_id
    ? `/implantados/contratos/${f.contrato_id}/cierre/revision`
    : `/cierre/servicio/${f.servicio_id}/revision`;
  let rev = null;
  try { rev = await api.get(ruta); } catch (err) { rev = { fallo: err.message }; }

  const nodos = [];
  if (rev.fallo) nodos.push(aviso(rev.fallo, "alerta"));
  const cmp = rev.comparativo;
  if (cmp) nodos.push(tablaDetalle(cmp, !!f.contrato_id, moneda));
  /* Lo que sale en la factura, renglon por renglon, con el paquete a la
     vista (seccion 79). El mes del implantado va con su contrato. */
  const renglones = cmp && !f.contrato_id ? tablaDeRenglones(cmp, moneda) : null;
  if (renglones) nodos.push(renglones);
  const revisar = (rev.observaciones || []).filter(o => o.nivel !== "corregir"
    && o.asunto !== "Plazo vencido" && o.asunto !== "Plazo por vencer");
  if (revisar.length) {
    nodos.push(h("p", { clase: "chico gris", style: "margin:6px 0 10px" },
      h("b", {}, t("cie_para_revisar")), " ",
      revisar.map(o => `${o.asunto}: ${o.mensaje || ""}`).join(" · ")));
  }
  if (f.devuelto_en) {
    nodos.push(h("p", { clase: "chico gris", style: "margin:0 0 10px" },
      reemplazar(t("fac_ya_regresado"), { f: dia(f.devuelto_en) })));
  }
  if (f.factura_anulada) {
    nodos.push(h("p", { clase: "chico gris", style: "margin:0 0 10px" },
      reemplazar(t("fac_sustituye_a"), { f: f.factura_anulada })));
  }

  const regreso = h("div");
  const acciones = h("div", { clase: "acciones" },
    !puedeFacturar() ? "" : h("button", { clase: "chico", type: "button", onclick: async (e) => {
      if (!confirm(t("fac_confirmar_aprobar"))) return;
      e.target.disabled = true;
      try {
        await api.post(`/cierre/${f.cierre_id}/aprobar`, {});
        mensaje(t("fac_aprobado"));
        await repintar();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, t("fac_aprobar")),
    !puedeFacturar() ? "" : h("button", { clase: "chico claro", type: "button",
      onclick: () => regreso.replaceChildren(formularioRegreso(f, repintar)) },
      t("fac_regresar")),
    f.factura_a_mano && puedeFacturar()
      ? h("button", { clase: "chico claro", type: "button",
          onclick: () => regreso.replaceChildren(formaFactura(
            f, repintar, () => regreso.replaceChildren())) },
          t("fac_corregir_factura"))
      : "",
    abreElServicio(f)
      ? h("button", { clase: "chico claro", type: "button", onclick: () => {
          location.hash = f.contrato_id ? `#/implantado/${f.servicio_id}`
                                        : `#/servicio/${f.servicio_id}`;
        } }, t("fac_abrir_servicio"))
      : "");
  nodos.push(acciones, regreso);
  return h("div", {}, ...nodos);
}

function tablaDetalle(cmp, esMes, moneda) {
  moneda = cmp.moneda || moneda;
  const g = cmp.gastos || {};
  const renglon = (a, b, c) => h("tr", {}, h("td", {}, a),
    h("td", { clase: "der num" }, b), h("td", {}, c));
  const filas = esMes
    ? [renglon(t("fac_contratado"), dinero(cmp.contratado.importe, moneda), ""),
       renglon(t("fac_trabajado"), dinero(cmp.a_facturar.servicio, moneda),
               (cmp.notas || []).join(" · "))]
    : [renglon(t("fac_cotizado"), dinero(cmp.cotizacion.servicio, moneda),
               reemplazar(t("cie_servicio_dias"),
                          { d: cmp.ejecutado.dias, e: cmp.ejecutado.equipos })),
       renglon(t("fac_ejecutado"), dinero(cmp.a_facturar.servicio, moneda),
               [Number(cmp.diferencia) ? reemplazar(t("fac_diferencia"), {
                  m: dinero(cmp.diferencia, moneda) }) : "",
                /* Cuanto del ejecutado son horas extra (seccion 65). */
                Number(cmp.ejecutado.horas_extra || 0)
                  ? reemplazar(t("fac_incluye_extra"),
                               { n: cmp.ejecutado.horas_extra }) : ""]
                 .filter(Boolean).join(" · "))];
  if (g.modo) {
    /* Netos en otra moneda (seccion 82): de cuanto en pesos sale y a que
       tipo de cambio. */
    const cambio = g.modo === "netos" && g.tipo_cambio
      ? reemplazar(t("fac_gastos_cambio"), {
          c: dinero(Number(g.comprobado) - Number(g.en_paquete || 0),
                    g.moneda_local), t: tasa(g.tipo_cambio.tasa) })
      : "";
    filas.push(renglon(t("fac_gastos"), dinero(g.a_facturar, moneda),
      g.sin_tipo_de_cambio ? t("fac_gastos_sin_tc")
        : [g.modo === "netos" ? t("fac_gastos_netos_pie")
            : Number(g.cotizado) ? t("fac_gastos_alzado_pie")
            : t("fac_gastos_incluidos"), cambio].filter(Boolean).join(" · ")));
  }
  return h("table", { clase: "tabla-cierre", style: "background:#fff" },
    h("tbody", {}, ...filas));
}

/* Regresar pide el motivo: es lo que el consultor lee en su tarjeta. */
function formularioRegreso(f, repintar) {
  const motivo = h("textarea", { rows: "2", style: "margin-bottom:10px",
                                 placeholder: t("fac_motivo_ej") });
  const mandar = h("button", { clase: "chico", type: "button",
    onclick: async (e) => {
      if (motivo.value.trim().length < 10) {
        return mensaje(t("fac_falta_motivo"), "alerta");
      }
      e.target.disabled = true;
      try {
        const r = await api.post(`/cierre/${f.cierre_id}/devolver`,
                                 { motivo: motivo.value.trim() });
        mensaje(r.factura_anulada
          ? reemplazar(t("fac_regresado_anulada"), { f: r.factura_anulada })
          : r.prefactura_anulada
            ? reemplazar(t("fac_regresado_prefactura"), { n: r.prefactura_anulada })
            : t("fac_regresado"));
        await repintar();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, t("fac_regresar"));
  return h("div", { clase: "tarjeta lisa", style: "margin:10px 0 0" },
    h("label", {}, t("fac_por_que_regresa")), motivo,
    h("div", { clase: "acciones" }, mandar,
      h("button", { clase: "chico claro", type: "button",
        onclick: (e) => e.target.closest(".tarjeta").remove() }, t("cancelar"))),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("fac_regresar_pie")));
}

/* ------------------------------------------------------------ en Odoo (seccion 117) */

/* Las prefacturas que Connect mando y que el facturista todavia no
   timbra. Mientras Connect no las lee de vuelta, la timbrada se anota
   aqui con «Ya se facturó en Odoo», con su folio y su fecha. */
function enOdoo(filas, moneda, repintar) {
  if (!filas.length) {
    return h("div", { clase: "tarjeta" }, h("div", { clase: "vacio" },
      t("fac_nada_en_odoo")));
  }
  const cuerpo = h("tbody");
  for (const f of filas) {
    const extra = h("tr", { clase: "fila-extra", hidden: true },
      h("td", { colspan: "4", style: "padding:2px 14px 16px" }));
    const cerrar = () => {
      extra.hidden = true;
      extra.firstChild.replaceChildren();
    };
    const anotar = !puedeFacturar() ? "" : h("button", { clase: "chico", type: "button",
      onclick: () => {
        if (!extra.hidden) return cerrar();
        extra.firstChild.replaceChildren(formaFactura(f, repintar, cerrar));
        extra.hidden = false;
        extra.querySelector("input").focus();
      } }, t("fac_ya_en_odoo"));
    /* «Volver a revisar en Odoo» (seccion 127): Connect no lee de vuelta
       todavia, asi que el borrador que el facturista cancelo o borro
       seguia aqui para siempre. Con esto se relee su estado: cancelado o
       borrado, se suelta y la vuelta de cada hora manda otro; timbrado,
       se dice para anotarlo; en borrador, nada cambia. */
    const revisar = !puedeFacturar() ? "" : h("button", { clase: "chico claro", type: "button",
      onclick: async (e) => {
        e.target.disabled = true;
        try {
          const r = await api.post(`/cierre/${f.cierre_id}/revisar-en-odoo`, {});
          if (r.resultado === "sigue") {
            mensaje(reemplazar(t(r.estado === "timbrada" ? "fac_rev_timbrada"
                                                        : "fac_rev_sigue"),
                               { n: r.prefactura, f: r.nombre || "" }),
                    r.estado === "timbrada" ? "alerta" : "ok");
          } else if (r.resultado === "cancelada" || r.resultado === "borrada") {
            mensaje(reemplazar(t(`fac_rev_${r.resultado}`), { n: r.prefactura }), "ok");
            await repintar();
          } else {
            mensaje(t("fac_rev_no_contesto"), "alerta");
          }
        } catch (err) { mensaje(err.message, "grave"); }
        e.target.disabled = false;
      } }, t("fac_revisar_en_odoo"));
    cuerpo.append(
      h("tr", {},
        h("td", {}, servicio(f),
          h("div", { clase: "chico gris" }, vistoBuenoCorto(f))),
        h("td", { clase: "der num" },
          h("b", {}, dinero(f.prefactura.total ?? f.total, f.moneda || moneda)),
          h("div", { clase: "chico gris" },
            reemplazar(t("fac_antes_de_iva"), { m: f.moneda || moneda }))),
        h("td", {}, prefacturaDe(f)),
        h("td", { clase: "der", style: "width:1%;white-space:nowrap" },
          h("div", { clase: "acciones",
                     style: "flex-direction:column;align-items:stretch" },
            f.prefactura.url ? botonOdoo(f.prefactura.url) : "", revisar, anotar))),
      extra);
  }
  return h("div", {},
    h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("fac_col_servicio")),
        h("th", { clase: "der" }, t("cie_col_a_facturar")),
        h("th", {}, t("fac_col_en_odoo")), h("th"))),
      cuerpo),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("fac_en_odoo_pie")));
}

/* «Ana Solis · visto bueno a tiempo». */
function vistoBuenoCorto(f) {
  const fuera = f.dentro_de_plazo === false;
  return h("span", {}, `${f.consultor || "—"} · `,
    h("span", { style: `color:var(${fuera ? "--grave" : "--ok"})` },
      t(fuera ? "fac_vb_fuera" : "fac_vb_a_tiempo")));
}

/* ------------------------------------------------------------ no se pudo mandar (seccion 117) */

/* Lo que tiene el visto bueno y no llego a Odoo, con su porque. La
   tarea de cada hora lo vuelve a intentar, sin duplicar; lo que tuvo su
   visto bueno antes de la llave no sale solo: lo manda finanzas. */
function noSePudo(filas, moneda, repintar) {
  if (!filas.length) {
    return h("div", { clase: "tarjeta" }, h("div", { clase: "vacio" },
      t("fac_nada_no_se_pudo")));
  }
  const cuerpo = h("tbody");
  for (const f of filas) {
    const extra = h("tr", { clase: "fila-extra", hidden: true },
      h("td", { colspan: "4", style: "padding:2px 14px 16px" }));
    const cerrar = () => {
      extra.hidden = true;
      extra.firstChild.replaceChildren();
    };
    const anotar = h("button", { clase: "chico", type: "button",
      onclick: () => {
        if (!extra.hidden) return cerrar();
        extra.firstChild.replaceChildren(formaFactura(f, repintar, cerrar));
        extra.hidden = false;
        extra.querySelector("input").focus();
      } }, t("fac_ya_en_odoo"));
    const mandar = h("button", { clase: "chico claro", type: "button",
      onclick: async (e) => {
        if (f.de_antes && !confirm(t("fac_confirmar_mandar_de_antes"))) return;
        e.target.disabled = true;
        try {
          const r = await api.post(`/cierre/${f.cierre_id}/facturar`, {});
          if (r.resultado === "en odoo" || r.resultado === "ya estaba en odoo") {
            mensaje(reemplazar(t("fac_prefactura_salio"), { n: r.prefactura }), "ok");
          } else {
            mensaje(t("fac_sigue_sin_salir"), "alerta");
          }
          await repintar();
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, t(f.de_antes ? "fac_mandar_a_odoo" : "fac_mandar_otra_vez"));
    const titulo = t(QUE_PASO[f.que_paso] || "fac_paso_falta_dato");
    const debajo = f.de_antes ? t("fac_de_antes_pie")
      : f.que_paso === "anterior_viva"
        ? reemplazar(t("fac_anterior_viva_pie"), { n: f.prefactura_anulada || "" })
        : [f.que_paso === "sin_llave" ? t("fac_sin_llave_pie") : f.error,
           reemplazar(t("fac_intentos_hora"), {
             n: f.intentos, f: f.ultimo_intento ? dia(f.ultimo_intento) : "—" })]
            .filter(Boolean).join(" · ");
    cuerpo.append(
      h("tr", {},
        h("td", { style: "min-width:190px" }, servicio(f)),
        h("td", { clase: "der num", style: "white-space:nowrap" },
          h("b", {}, dinero(f.total, f.moneda || moneda))),
        h("td", {},
          h("span", { style: `color:var(${f.de_antes ? "--centauro" : "--alerta"});font-weight:650` },
            titulo),
          h("div", { clase: "chico gris" }, debajo),
          f.que_paso === "anterior_viva" && f.prefactura_url_anulada
            ? h("div", { style: "margin-top:6px" }, botonOdoo(f.prefactura_url_anulada))
            : ""),
        h("td", { clase: "der", style: "width:1%;white-space:nowrap" },
          !puedeFacturar() ? ""
            : h("div", { clase: "acciones",
                         style: "flex-direction:column;align-items:stretch" },
                mandar, anotar))),
      extra);
  }
  return h("div", {},
    h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("fac_col_servicio")),
        h("th", { clase: "der", style: "white-space:nowrap" }, t("cie_col_a_facturar")),
        h("th", {}, t("fac_col_que_paso")), h("th"))),
      cuerpo),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("fac_no_se_pudo_pie")));
}

/* ------------------------------------------------------------ por facturar */

function porFacturar(filas, moneda, repintar, conectado) {
  if (!filas.length) {
    return h("div", { clase: "tarjeta" }, h("div", { clase: "vacio" },
      t("fac_nada_por_facturar")));
  }
  const cuerpo = h("tbody");
  for (const f of filas) {
    /* La forma de la factura se abre debajo de su renglon. */
    const extra = h("tr", { clase: "fila-extra", hidden: true },
      h("td", { colspan: "4", style: "padding:2px 14px 16px" }));
    const cerrar = () => {
      extra.hidden = true;
      extra.firstChild.replaceChildren();
    };
    const anotar = h("button", { clase: "chico", type: "button",
      onclick: () => {
        if (!extra.hidden) return cerrar();
        extra.firstChild.replaceChildren(formaFactura(f, repintar, cerrar));
        extra.hidden = false;
        extra.querySelector("input").focus();
      } }, t("fac_ya_en_odoo"));
    /* Volver a mandarla solo sirve con Odoo conectado: sin conexion el
       intento siempre dice lo mismo. */
    const otraVez = !conectado ? "" : h("button", { clase: "chico claro", type: "button",
      onclick: async (e) => {
        e.target.disabled = true;
        try {
          const r = await api.post(`/cierre/${f.cierre_id}/facturar`, {});
          mensaje(r.resultado === "facturado"
            ? reemplazar(t("fac_facturado"), { f: r.factura || "" })
            : t("fac_sigue_sin_factura"),
            r.resultado === "facturado" ? "ok" : "alerta");
          await repintar();
        } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
      } }, t("fac_mandar_otra_vez"));
    /* Sin conexion, el error siempre dice lo mismo: basta con los
       intentos. */
    const intentos = [
      f.que_paso === "sin_conexion" ? "" : f.error,
      reemplazar(t("fac_intentos"), { n: f.intentos,
                                      f: f.ultimo_intento ? dia(f.ultimo_intento) : "—" }),
    ].filter(Boolean).join(" · ");
    cuerpo.append(
      h("tr", {},
        h("td", {}, servicio(f)),
        h("td", { clase: "der num" }, h("b", {}, dinero(f.total, f.moneda || moneda))),
        h("td", {},
          h("span", { style: "color:var(--alerta);font-weight:650" },
            t(QUE_PASO[f.que_paso] || "fac_paso_falta_dato")),
          h("div", { clase: "chico gris" }, intentos)),
        h("td", { clase: "der" }, !puedeFacturar() ? ""
          : h("div", { clase: "acciones", style: "justify-content:flex-end" },
              anotar, otraVez))),
      extra);
  }
  return h("div", {},
    h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("fac_col_servicio")),
        h("th", { clase: "der" }, t("cie_col_a_facturar")),
        h("th", {}, t("fac_col_que_paso")), h("th"))),
      cuerpo),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" },
      t(conectado ? "fac_por_facturar_pie" : "fac_por_facturar_pie_sin_odoo")));
}

/* La factura que finanzas hizo en Odoo (seccion 96): su folio y su
   fecha. La misma forma corrige la que se anoto a mano, con lo de antes
   a la vista. */
function formaFactura(f, repintar, cerrar) {
  const corrige = !!f.factura;
  const hoy = hoyAqui();
  /* El folio se queda como lo da Odoo: sin `data-crudo`, la consola lo
     ponia en formato de nombre al salir de la caja --«Inv/2026/01842»--. */
  const folio = h("input", { maxlength: "60", "data-crudo": "" });
  folio.value = f.factura || "";
  const fecha = h("input", { type: "date", max: hoy });
  fecha.value = f.facturado_en ? f.facturado_en.slice(0, 10) : hoy;
  const guardar = h("button", { clase: "chico", type: "button",
    onclick: async () => {
      const escrito = folio.value.trim();
      if (!escrito) {
        folio.focus();
        return mensaje(t("fac_falta_folio"), "alerta");
      }
      if (!fecha.value) {
        fecha.focus();
        return mensaje(t("fac_falta_fecha"), "alerta");
      }
      if (fecha.value > hoy) {
        fecha.focus();
        return mensaje(t("fac_fecha_futura"), "alerta");
      }
      guardar.disabled = true;
      try {
        const r = await api.put(`/cierre/${f.cierre_id}/factura-de-odoo`,
                                { folio: escrito, fecha: fecha.value });
        mensaje(reemplazar(t(r.corregida ? "fac_corregida" : "fac_anotada"),
                           { f: r.factura }));
        await repintar();
      } catch (err) {
        guardar.disabled = false;
        mensaje(err.message, "grave");
      }
    } }, t("fac_anotar"));
  return h("div", { clase: "tarjeta lisa", style: "margin:6px 0 0" },
    h("h4", {}, t(corrige ? "fac_corregir_la_de_odoo" : "fac_la_de_odoo")),
    h("div", { clase: "rejilla tres", style: "align-items:end" },
      h("div", {}, h("label", {}, t("fac_folio_factura")), folio),
      h("div", {}, h("label", {}, t("fac_fecha_factura")), fecha),
      h("div", { clase: "acciones" }, guardar,
        h("button", { clase: "chico claro", type: "button", onclick: cerrar },
          t("cancelar")))),
    corrige
      ? h("p", { clase: "chico gris", style: "margin:8px 0 0" },
          reemplazar(t("fac_antes_folio"),
                     { f: f.factura, d: f.facturado_en ? fechaCorta(f.facturado_en) : "—" }))
      : "",
    h("p", { clase: "chico gris", style: "margin:8px 0 0" },
      t(corrige ? "fac_corregir_pie" : "fac_anotar_pie")));
}

/* El folio, y si se anoto a mano, quien lo anoto. */
function folioDe(f) {
  return h("div", {}, f.factura,
    f.factura_a_mano
      ? h("div", { clase: "chico gris" },
          f.factura_anotada_por
            ? reemplazar(t("fac_a_mano_por"), { p: f.factura_anotada_por })
            : t("fac_a_mano"))
      : "");
}

/* Hoy, en la computadora de quien anota: la fecha de la factura no
   puede ser de mañana. El servidor lo revisa con el dia del pais. */
function hoyAqui() {
  const d = new Date();
  const dos = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}`;
}

function fechaCorta(iso) {
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

/* ------------------------------------------------------------ cerrados */

function cerrados(filas, moneda, repintar) {
  if (!filas.length) {
    return h("div", { clase: "tarjeta" }, h("div", { clase: "vacio" },
      t("fac_nada_cerrado")));
  }
  const comision = (c) => {
    if (!c) return "—";
    if (c.estatus === "perdida") return t("fac_comision_perdida");
    if (c.estatus === "retenida") return t("fac_comision_retenida");
    return dinero(c.monto, c.moneda || moneda);
  };
  const cuerpo = h("tbody");
  for (const f of filas) {
    const extra = h("tr", { clase: "fila-extra", hidden: true },
      h("td", { colspan: "5", style: "padding:2px 14px 16px" }));
    const cerrar = () => {
      extra.hidden = true;
      extra.firstChild.replaceChildren();
    };
    /* La que se anoto a mano se corrige aqui; la de Odoo, en Odoo. */
    const corregir = f.factura_a_mano && puedeFacturar()
      ? h("button", { clase: "chico claro", type: "button",
          style: "margin-top:4px",
          onclick: () => {
            if (!extra.hidden) return cerrar();
            extra.firstChild.replaceChildren(formaFactura(f, repintar, cerrar));
            extra.hidden = false;
          } }, t("fac_corregir"))
      : "";
    cuerpo.append(
      h("tr", {},
        h("td", {}, servicio(f)),
        h("td", {}, dia(f.aprobado_en)),
        h("td", { clase: "der num" }, dinero(f.total, f.moneda || moneda)),
        h("td", {}, f.factura ? folioDe(f) : etiqueta(t("fac_sin_factura"), "alerta"),
          corregir),
        h("td", { clase: "der num" }, comision(f.comision))),
      extra);
  }
  return h("table", { clase: "lista" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("fac_col_servicio")), h("th", {}, t("fac_col_cerrado")),
      h("th", { clase: "der" }, t("fac_col_total")),
      h("th", {}, t("fac_col_factura")),
      h("th", { clase: "der" }, t("fac_col_comision")))),
    cuerpo);
}

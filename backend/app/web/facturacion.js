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

   La cuarta pestana es el historial (seccion 69): todo lo cerrado desde
   el primer servicio, con filtros, en Excel, y con lo que pasa con las
   fotos de sus comprobantes. Vive en historial.js. */
import { api, sesion } from "./api.js";
import { pestanaHistorial } from "./historial.js";
import { aviso, conAyuda, dinero, etiqueta, h, hora, mensaje } from "./util.js";
import { t } from "./idioma.js";

/* Quien puede abrir la pantalla del servicio. Finanzas no: la suya es
   esta. */
const ABREN_SERVICIO = ["consultor", "director_operaciones",
                        "director_general", "admin"];

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
  const pie = g.modo === "netos"
    ? reemplazar(t("fac_con_gastos_netos"), { m: dinero(monto, moneda) })
    : monto ? reemplazar(t("fac_con_gastos_alzado"), { m: dinero(monto, moneda) })
            : t("fac_gastos_incluidos");
  return h("td", { clase: "num der" }, h("b", {}, dinero(f.total, moneda)),
    g.modo ? h("div", { clase: "chico gris" }, pie) : "");
}

function factura(f) {
  if (f.factura) return h("td", {}, f.factura);
  return h("td", {}, etiqueta(t("fac_sin_factura"), "alerta"),
    f.que_paso ? h("div", { clase: "chico gris", style: "margin-top:4px" },
                   t(QUE_PASO[f.que_paso] || "fac_paso_falta_dato")) : "");
}

export async function pantallaFacturacion(main) {
  const moneda = "MXN";
  main.append(
    conAyuda("h1", t("fac_titulo"), "ay_fac_titulo"),
    h("p", { clase: "sub" }, t("fac_sub")));
  const zona = h("div");
  main.append(zona);
  let pestana = "aprobar";

  const pintar = async () => {
    let b;
    try {
      b = await api.get("/cierre/facturacion");
    } catch (err) {
      zona.replaceChildren(aviso(err.message, "grave"));
      return;
    }
    const r = b.resumen;
    const corte = h("div", { clase: "corte" },
      h("div", {}, h("div", { clase: "chico gris" }, t("fac_por_aprobar")),
        h("div", { clase: "cifra" }, r.por_aprobar.cuantos),
        h("div", { clase: "chico gris num" }, dinero(r.por_aprobar.monto, moneda))),
      h("div", {}, h("div", { clase: "chico gris" }, t("fac_por_facturar")),
        h("div", { clase: "cifra", style: r.por_facturar.cuantos
                     ? "color:var(--alerta)" : "" }, r.por_facturar.cuantos),
        h("div", { clase: "chico gris" },
          b.odoo_configurado ? t("fac_odoo_no_acepto") : t("fac_sin_odoo"))),
      h("div", {}, h("div", { clase: "chico gris" },
          reemplazar(t("fac_cerrados_en"), { m: t(MESES[r.cerrados.mes - 1]) })),
        h("div", { clase: "cifra" }, r.cerrados.cuantos),
        h("div", { clase: "chico gris num" }, dinero(r.cerrados.monto, moneda))));

    const boton = (clave, texto) => h("button", {
      clase: `pestana ${pestana === clave ? "activa" : ""}`.trim(), type: "button",
      onclick: () => { pestana = clave; pintar(); } }, texto);
    const pestanas = h("div", { clase: "pestanas", style: "margin:0 0 12px" },
      boton("aprobar", reemplazar(t("fac_tab_aprobar"), { n: b.por_aprobar.length })),
      boton("facturar", reemplazar(t("fac_tab_facturar"), { n: b.por_facturar.length })),
      boton("cerrados", t("fac_tab_cerrados")),
      boton("historial", t("fac_tab_historial")));

    const cuerpo = pestana === "aprobar" ? porAprobar(b.por_aprobar, moneda, pintar)
      : pestana === "facturar" ? porFacturar(b.por_facturar, moneda, pintar)
      : pestana === "historial" ? pestanaHistorial()
      : cerrados(b.cerrados, moneda);
    zona.replaceChildren(corte, pestanas, cuerpo);
  };
  await pintar();
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
    h("button", { clase: "chico", type: "button", onclick: async (e) => {
      if (!confirm(t("fac_confirmar_aprobar"))) return;
      e.target.disabled = true;
      try {
        await api.post(`/cierre/${f.cierre_id}/aprobar`, {});
        mensaje(t("fac_aprobado"));
        await repintar();
      } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
    } }, t("fac_aprobar")),
    h("button", { clase: "chico claro", type: "button",
      onclick: () => regreso.replaceChildren(formularioRegreso(f, repintar)) },
      t("fac_regresar")),
    sesion.usuario && ABREN_SERVICIO.includes(sesion.usuario.rol)
      ? h("button", { clase: "chico claro", type: "button", onclick: () => {
          location.hash = f.contrato_id ? `#/implantado/${f.servicio_id}`
                                        : `#/servicio/${f.servicio_id}`;
        } }, t("fac_abrir_servicio"))
      : "");
  nodos.push(acciones, regreso);
  return h("div", {}, ...nodos);
}

function tablaDetalle(cmp, esMes, moneda) {
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
    filas.push(renglon(t("fac_gastos"), dinero(g.a_facturar, moneda),
      g.modo === "netos" ? t("fac_gastos_netos_pie")
        : Number(g.cotizado) ? t("fac_gastos_alzado_pie")
        : t("fac_gastos_incluidos")));
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

/* ------------------------------------------------------------ por facturar */

function porFacturar(filas, moneda, repintar) {
  if (!filas.length) {
    return h("div", { clase: "tarjeta" }, h("div", { clase: "vacio" },
      t("fac_nada_por_facturar")));
  }
  const cuerpo = h("tbody", {}, ...filas.map(f => h("tr", {},
    h("td", {}, servicio(f)),
    h("td", { clase: "der num" }, h("b", {}, dinero(f.total, f.moneda || moneda))),
    h("td", {},
      h("span", { style: "color:var(--alerta);font-weight:650" },
        t(QUE_PASO[f.que_paso] || "fac_paso_falta_dato")),
      h("div", { clase: "chico gris" }, [
        f.que_paso === "sin_conexion" ? null : f.error,
        reemplazar(t("fac_intentos"), { n: f.intentos,
                                        f: f.ultimo_intento ? dia(f.ultimo_intento) : "—" }),
      ].filter(Boolean).join(" · "))),
    h("td", { clase: "der" }, h("button", { clase: "chico", type: "button",
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
      } }, t("fac_mandar_otra_vez"))))));
  return h("div", {},
    h("table", { clase: "lista" },
      h("thead", {}, h("tr", {},
        h("th", {}, t("fac_col_servicio")),
        h("th", { clase: "der" }, t("cie_col_a_facturar")),
        h("th", {}, t("fac_col_que_paso")), h("th"))),
      cuerpo),
    h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("fac_por_facturar_pie")));
}

/* ------------------------------------------------------------ cerrados */

function cerrados(filas, moneda) {
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
  return h("table", { clase: "lista" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("fac_col_servicio")), h("th", {}, t("fac_col_cerrado")),
      h("th", { clase: "der" }, t("fac_col_total")),
      h("th", {}, t("fac_col_factura")),
      h("th", { clase: "der" }, t("fac_col_comision")))),
    h("tbody", {}, ...filas.map(f => h("tr", {},
      h("td", {}, servicio(f)),
      h("td", {}, dia(f.aprobado_en)),
      h("td", { clase: "der num" }, dinero(f.total, f.moneda || moneda)),
      h("td", {}, f.factura || etiqueta(t("fac_sin_factura"), "alerta")),
      h("td", { clase: "der num" }, comision(f.comision))))));
}

/* Concentrado de la operacion viva.

   Orden deliberado: primero lo que puede lastimar a alguien, luego lo
   que puede costar dinero, al final lo que solo hay que atender. */
import { api } from "./api.js";
import { aviso, dinero, etiqueta, fecha, h, hora } from "./util.js";
import { t } from "./idioma.js";

const REFRESCO_SEGUNDOS = 60;
let temporizador = null;

export async function pantallaPanorama(main) {
  main.append(
    h("h1", {}, t("pan_titulo")),
    h("p", { clase: "sub" },
      t("pan_sub").replace("{s}", REFRESCO_SEGUNDOS)));
  const zona = h("div");
  main.append(zona);

  const refrescar = async () => {
    if (!document.body.contains(zona)) { clearInterval(temporizador); return; }
    try { zona.replaceChildren(...pintar(await api.get("/panorama"))); }
    catch (e) { zona.replaceChildren(aviso(e.message, "grave")); }
  };
  await refrescar();
  clearInterval(temporizador);
  temporizador = setInterval(refrescar, REFRESCO_SEGUNDOS * 1000);
}

export function detenerPanorama() { clearInterval(temporizador); temporizador = null; }

function tarjetaNumero(titulo, valor, nota, tono = "") {
  return h("div", { clase: "tarjeta" },
    h("h4", {}, titulo),
    h("div", { style: "font-size:30px;font-weight:700;line-height:1.1" }, String(valor)),
    nota ? h("div", { clase: "chico gris", style: "margin-top:4px" }, nota) : "",
    tono ? h("div", { style: "margin-top:8px" }, etiqueta(t("pan_requiere_atencion"), tono)) : "");
}

function pintar(p) {
  const bloques = [];

  /* ---------------------------------------------- lo urgente primero */
  if (p.alertas.abiertas) {
    bloques.push(h("div", { clase: "destacado" },
      h("h4", {}, t("pan_alertas_sin_tomar")),
      h("div", { clase: "valor" },
        `${p.alertas.abiertas} `
        + `${p.alertas.abiertas === 1 ? t("pan_alerta") : t("pan_alertas")} `
        + t("pan_esperando_central")),
      h("div", { clase: "nota" }, t("pan_cada_una"))));
  }

  bloques.push(h("div", { clase: "rejilla tres" },
    tarjetaNumero(t("pan_en_curso"), p.en_curso.cuantos,
      t("pan_en_curso_nota")),
    tarjetaNumero(t("pan_por_iniciar"), p.por_iniciar.cuantos,
      p.por_iniciar.no_listos.length
        ? `${p.por_iniciar.no_listos.length} ${t("pan_sin_estar_listos")}`
        : t("pan_todos_listos"),
      p.por_iniciar.no_listos.length ? "grave" : ""),
    tarjetaNumero(t("pan_alertas_atencion"), p.alertas.en_atencion,
      t("pan_ya_tomadas"))));

  /* ---------------------------------------------- por iniciar */
  if (p.por_iniciar.no_listos.length) {
    const cuerpo = h("tbody");
    for (const j of p.por_iniciar.no_listos) {
      cuerpo.append(h("tr", {},
        h("td", {}, h("b", {}, j.servicio)),
        h("td", { clase: "num" }, `${hora(j.inicia)}`,
          h("div", { clase: "gris chico" },
            t("en_minutos").replace("{n}", j.en_minutos))),
        h("td", {}, j.faltas.map(f => h("span", { style: "margin-right:6px" },
          etiqueta(f, "grave"))))));
    }
    bloques.push(h("div", { clase: "tarjeta" },
      h("h3", {}, t("pan_arrancan_pronto")),
      h("table", {}, h("thead", {}, h("tr", {},
        h("th", {}, t("col_servicio")), h("th", {}, t("col_inicia")),
        h("th", {}, t("col_falta")))),
        cuerpo)));
  }

  /* ---------------------------------------------- en curso */
  if (p.en_curso.servicios.length) {
    const cuerpo = h("tbody");
    for (const s of p.en_curso.servicios) {
      const mudo = s.minutos_sin_reportar !== null && s.minutos_sin_reportar > 120;
      const porExtra = s.minutos_para_horas_extra !== null
                    && s.minutos_para_horas_extra <= 30
                    && s.minutos_para_horas_extra > -600;
      cuerpo.append(h("tr", {},
        h("td", {}, h("b", {}, s.servicio),
          h("div", { clase: "gris chico" }, `${s.cliente} · ${t("col_equipo")} ${s.equipo}`)),
        h("td", {}, s.personal.join(", ") || "—",
          h("div", { clase: "chico" },
            s.placas.map(pl => h("span", { clase: "placas" }, pl)))),
        h("td", { clase: "num" }, `${hora(s.inicio)} — ${hora(s.fin_programado)}`),
        h("td", {},
          s.ultimo_reporte
            ? h("div", {}, s.ultimo_reporte.replace(/_/g, " "),
                h("div", { clase: "chico " + (mudo ? "" : "gris"),
                           style: mudo ? "color:#c0392b;font-weight:600" : "" },
                  t("hace_minutos").replace("{n}", s.minutos_sin_reportar)))
            : etiqueta(t("pan_sin_reportar"), "grave"),
          porExtra ? h("div", { style: "margin-top:4px" },
            etiqueta(t("pan_por_horas_extra"), "alerta")) : "")));
    }
    bloques.push(h("div", { clase: "tarjeta" },
      h("h3", {}, t("pan_en_la_calle")),
      h("table", {}, h("thead", {}, h("tr", {},
        h("th", {}, t("col_servicio")), h("th", {}, t("col_equipo")),
        h("th", {}, t("col_horario")), h("th", {}, t("col_ultimo_reporte")))),
        cuerpo)));
  }

  /* ---------------------------------------------- dinero */
  const d = p.dinero;
  const dineroBloque = h("div", { clase: "tarjeta" },
    h("h3", {}, t("pan_dinero")),
    h("div", { clase: "rejilla tres" },
      h("div", {}, h("h4", {}, t("pan_viaticos_transferir")),
        h("div", { style: "font-size:20px;font-weight:650" },
          dinero(d.viaticos_por_transferir.monto)),
        h("div", { clase: "chico gris" },
          `${d.viaticos_por_transferir.cuantos} ${t("pan_asignaciones")}`)),
      h("div", {}, h("h4", {}, t("pan_en_comprobacion")),
        h("div", { style: "font-size:20px;font-weight:650" },
          d.viaticos_en_comprobacion),
        h("div", { clase: "chico gris" },
          `${d.viaticos_con_plazo_vencido.length} ${t("pan_plazo_vencido")}`)),
      h("div", {}, h("h4", {}, t("pan_nomina_semana")),
        h("div", { style: "font-size:20px;font-weight:650" },
          dinero(d.nomina_de_la_semana.total)),
        h("div", { clase: "chico gris" },
          `${t("pan_corte")} ${fecha(d.nomina_de_la_semana.fecha_corte)} · ` +
          `${d.nomina_de_la_semana.estatus}`))));

  if (d.viaticos_con_plazo_vencido.length) {
    dineroBloque.append(h("div", { style: "margin-top:14px" },
      h("h4", {}, t("pan_comprobacion_vencida")),
      h("ul", { clase: "chico", style: "margin:0;padding-left:18px" },
        ...d.viaticos_con_plazo_vencido.map(v =>
          h("li", {}, `${v.persona} · ${dinero(v.monto)} · `
                      + `${t("pan_vencio")} ${fecha(v.vencio)}`)))));
  }
  if (d.ajustes_pendientes.cuantos) {
    dineroBloque.append(h("div", { clase: "chico gris", style: "margin-top:10px" },
      `${d.ajustes_pendientes.cuantos} ${t("pan_ajustes")} ` +
      `(${t("pan_neto")} ${dinero(d.ajustes_pendientes.neto)})`));
  }
  bloques.push(dineroBloque);

  /* ---------------------------------------------- camino al cobro */
  const c = p.cierres;
  const cierres = h("div", { clase: "tarjeta" },
    h("h3", {}, t("pan_camino_cobro")),
    h("div", { clase: "rejilla tres" },
      h("div", {}, h("h4", {}, t("pan_cierres_abiertos")),
        h("div", { style: "font-size:20px;font-weight:650" }, c.abiertos)),
      h("div", {}, h("h4", {}, t("pan_esperando_finanzas")),
        h("div", { style: "font-size:20px;font-weight:650" }, c.esperando_finanzas)),
      h("div", {}, h("h4", {}, t("pan_devueltos")),
        h("div", { style: "font-size:20px;font-weight:650" },
          c.devueltos_a_operacion.length))));

  if (c.con_plazo_vencido.length) {
    cierres.append(h("div", { style: "margin-top:14px" },
      h("h4", {}, t("pan_con_plazo_vencido")),
      h("ul", { clase: "chico", style: "margin:0;padding-left:18px" },
        ...c.con_plazo_vencido.map(x =>
          h("li", {}, `${x.servicio} — ${x.nota}`)))));
  }
  if (c.devueltos_a_operacion.length) {
    cierres.append(h("div", { style: "margin-top:14px" },
      h("h4", {}, t("pan_regresados")),
      h("ul", { clase: "chico", style: "margin:0;padding-left:18px" },
        ...c.devueltos_a_operacion.map(x =>
          h("li", {}, `${x.servicio}: ${x.motivo || t("pan_sin_motivo")}`)))));
  }
  bloques.push(cierres);

  /* ---------------------------------------------- por atender */
  const a = p.pendientes_de_atencion;
  if (a.encuestas_por_clasificar.length || a.incidencias_sin_visto_bueno.length) {
    bloques.push(h("div", { clase: "tarjeta" },
      h("h3", {}, t("pan_esperando_decision")),
      a.encuestas_por_clasificar.length
        ? h("div", {},
            h("h4", {}, t("pan_malas_calificaciones")),
            h("div", { clase: "chico gris" },
              a.encuestas_por_clasificar
                .map(e => `${t("pan_servicio")} ${e.servicio_id} `
                          + `(${e.calificacion} ${t("pan_de_5")})`)
                .join(" · ")))
        : "",
      a.incidencias_sin_visto_bueno.length
        ? h("div", { style: "margin-top:12px" },
            h("h4", {}, t("pan_incidencias_sin_vb")),
            h("div", { clase: "chico gris" },
              a.incidencias_sin_visto_bueno
                .map(i => `${i.persona} (${i.gravedad})`).join(" · ")))
        : ""));
  }

  return bloques;
}

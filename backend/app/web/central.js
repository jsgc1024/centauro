/* La central de inteligencia.

   Esta pantalla queda abierta todo el dia en un monitor, asi que el
   orden importa mas que el contenido. Y el orden sale de una idea: una
   central que solo mira lo que esta pasando llega tarde siempre —si el
   equipo no llego al punto, ya no llego—. El unico momento en que se
   puede cambiar el resultado de un servicio es la vispera.

   Por eso el eje no es "ahora", es el tiempo:

     1. lo roto     lo que ya no se arregla solo
     2. manana      el meet and greet, que es el corazon
     3. el pulso    los que estan en curso y cuanto llevan callados
     4. la semana   para ver venir el lunes de seis servicios
*/
import { api } from "./api.js";
import { aviso, entrada, estatus, etiqueta, h, hora, mensaje } from "./util.js";
import { t } from "./idioma.js";

const REFRESCO_SEGUNDOS = 45;
let temporizador = null;

export async function tableroCentral(main) {
  main.append(
    h("h1", {}, t("central_titulo")),
    h("p", { clase: "sub" },
      t("cen_sub").replace("{s}", REFRESCO_SEGUNDOS)));

  const zona = h("div");
  main.append(zona);

  const refrescar = async () => {
    if (!document.body.contains(zona)) {
      clearInterval(temporizador);
      return;
    }
    await pintar(zona);
  };

  await refrescar();
  clearInterval(temporizador);
  temporizador = setInterval(refrescar, REFRESCO_SEGUNDOS * 1000);
}

async function pintar(zona) {
  let d;
  try {
    d = await api.get("/central/tablero");
  } catch (e) {
    return zona.replaceChildren(aviso(e.message, "grave"));
  }
  /* Los dias sin cerrar van al final a proposito: no son urgentes
     —ya pasaron— pero tampoco pueden quedarse invisibles, porque cada
     uno es alguien esperando su pago. */
  const sinCerrar = await bandaSinCerrar(zona);
  zona.replaceChildren(
    bandaRoto(d.roto, zona),
    bandaManana(d),
    bandaPulso(d.pulso),
    bandaSemana(d.semana),
    ...(sinCerrar ? [sinCerrar] : []));
}

/* ------------------------------------------------- 1 · lo roto

   Si no hay nada, esta banda no existe. Una franja que siempre dice
   "todo bien" deja de leerse a la semana. */

function bandaRoto(roto, zona) {
  if (!roto.hay) return h("div", {});

  const caja = h("div", { clase: "tarjeta" },
    h("h3", {}, t("cen_roto")));

  for (const a of roto.panico) {
    caja.append(fichaPanico(a, zona));
  }
  for (const f of roto.callados) {
    caja.append(renglonRoto(t("cen_callado"), "grave",
      `${f.folio} · ${f.cliente || ""}`,
      f.minutos_callado === null
        ? t("cen_nunca_reporto")
        : t("cen_callado_min").replace("{n}", f.minutos_callado),
      f));
  }
  for (const f of roto.manana_vencido) {
    caja.append(renglonRoto(t("cen_vencido"), "grave",
      `${f.folio} · ${hora(f.equipo_llega)}`,
      `${cuantasFaltan(f.faltan)}${f.consultor ? " · " + f.consultor : ""}`,
      f));
  }
  for (const f of roto.por_entrar_en_extra) {
    caja.append(renglonRoto(t("cen_extra"), "alerta",
      `${f.folio} · ${f.cliente || ""}`,
      `${f.minutos_para_horas_extra} min`, f));
  }
  return caja;
}

function renglonRoto(titulo, tono, principal, detalle, ficha) {
  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 10px" },
    h("div", { style: "display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center" },
      h("div", {},
        etiqueta(titulo, tono), " ",
        h("b", {}, principal),
        h("div", { clase: "gris chico" }, detalle)),
      ficha && ficha.servicio_id
        ? h("a", { clase: "chico", href: rutaDelServicio(ficha) },
            t("cen_ver_servicio"))
        : null));
}

function fichaPanico(a, zona) {
  const canal = { boton_app: t("canal_boton_app"),
                  boton_vehiculo: t("canal_boton_vehiculo"),
                  llamada: t("canal_llamada") }[a.canal] || a.canal;
  const urgente = a.estatus === "abierta";
  const acciones = h("div", { clase: "acciones", style: "margin-top:10px" });

  if (urgente) {
    acciones.append(
      h("button", { clase: "chico", onclick: (e) => tomar(e, false) },
        t("central_tomar")),
      h("button", { clase: "chico claro", onclick: (e) => tomar(e, true) },
        t("central_tomar_equipo")));
  } else {
    const nota = entrada("resolucion",
                         { placeholder: t("central_resolucion_ph") });
    acciones.append(
      h("div", { style: "flex:1;min-width:240px" }, nota),
      h("button", { clase: "chico", onclick: (e) => cerrar(e, nota) },
        t("central_cerrar")));
  }

  async function tomar(e, conEquipo) {
    e.target.disabled = true;
    try {
      await api.post(`/contingencia/alertas/${a.id}/tomar`,
                     { equipo_respuesta_enviado: conEquipo });
      mensaje(conEquipo ? t("central_alerta_tomada_equipo")
                        : t("central_alerta_tomada"));
      await pintar(zona);
    } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
  }

  async function cerrar(e, nota) {
    if (!nota.value.trim()) {
      return mensaje(t("central_falta_resolucion"), "alerta");
    }
    e.target.disabled = true;
    try {
      await api.post(`/contingencia/alertas/${a.id}/cerrar`,
                     { resolucion: nota.value });
      mensaje(t("central_alerta_cerrada"));
      await pintar(zona);
    } catch (err) { mensaje(err.message, "grave"); e.target.disabled = false; }
  }

  return h("div", { clase: "tarjeta lisa", style: "margin:0 0 12px" },
    h("div", { style: "display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap" },
      h("div", {},
        etiqueta(t("cen_panico"), "grave"), " ",
        h("b", {}, canal),
        h("div", { clase: "gris chico" },
          `${t("central_reportada")} ${hora(a.reportada_en)}`)),
      etiqueta(estatus(a.estatus), urgente ? "grave" : "alerta")),
    a.descripcion ? h("p", { style: "margin:8px 0 0" }, a.descripcion) : null,
    /* La central estabiliza y el consultor formaliza. Verlo aqui ahorra
       la llamada de "oye, ¿ya lo cambiaste?". */
    a.cambio
      ? h("div", { clase: "chico", style: "margin-top:6px" },
          etiqueta(t("central_cambio"), "ok"), " ", a.cambio)
      : null,
    a.lat
      ? h("div", { clase: "chico" },
          h("a", { target: "_blank",
                   href: `https://www.google.com/maps?q=${a.lat},${a.lon}` },
            t("central_ver_mapa")))
      : null,
    acciones);
}

/* --------------------------------------------- 2 · manana

   El corazon de la pantalla. Una tarjeta por servicio, ordenadas por la
   hora a la que el equipo tiene que estar parado en el punto —que es la
   unica hora que de verdad se puede perder— y debajo, lo que tiene que
   ser cierto para que ese encuentro ocurra. */

/* A donde lleva "abrir el servicio". Eventual e implantado son dos
   pantallas distintas, y el tablero mezcla los dos. */
function rutaDelServicio(f) {
  return f.tipo === "implantado"
    ? `#/implantado/${f.servicio_id}`
    : `#/servicio/${f.servicio_id}`;
}

function cuantasFaltan(n) {
  return n === 1 ? t("cen_falta_uno") : t("cen_faltan").replace("{n}", n);
}

function bandaManana(d) {
  const m = d.manana;
  const caja = h("div", { clase: "tarjeta" },
    h("div", { style: "display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline" },
      h("h3", { style: "margin:0" }, t("cen_manana")),
      h("div", { clase: "chico" },
        m.cuantos
          ? h("span", {},
              h("span", { clase: "verde" }, `${m.listos} ${t("cen_listos")}`),
              m.incompletos
                ? h("span", { clase: "ambar" },
                    ` · ${m.incompletos} ${t("cen_incompletos")}`)
                : null)
          : null)),
    h("p", { clase: "gris chico", style: "margin:4px 0 10px" },
      t("cen_manana_sub")),
    /* El corte de la vispera: antes es trabajo, despues es un problema
       de esta noche. Decirlo cambia como se lee toda la banda. */
    h("div", { clase: d.paso_el_corte ? "aviso alerta" : "aviso",
               style: "margin:0 0 12px" },
      h("b", {}, `${t("cen_corte")} ${d.corte_de_la_vispera}`), " · ",
      d.paso_el_corte ? t("cen_paso_el_corte") : t("cen_antes_del_corte")));

  if (!m.cuantos) {
    caja.append(h("div", { clase: "vacio" }, t("cen_manana_nada")));
    return caja;
  }
  for (const f of m.servicios) caja.append(tarjetaDelDia(f));
  return caja;
}

function tarjetaDelDia(f) {
  const faltan = f.revision.filter(p => !p.listo);

  return h("div", {
    clase: "tarjeta lisa",
    style: "margin:0 0 12px;border-left:3px solid "
           + (f.listo ? "var(--ok)" : "var(--grave)"),
  },
    h("div", { style: "display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap" },
      h("div", {},
        /* La hora grande es a la que el equipo llega, no a la que
           arranca el servicio: es la que se puede perder. */
        h("div", { style: "font-size:22px;font-weight:650;line-height:1.1" },
          hora(f.equipo_llega)),
        h("div", { clase: "gris chico" },
          `${t("cen_equipo_llega")} · ${t("cen_servicio_inicia")} `
          + `${hora(f.servicio_inicia)}`
          + (f.contra_vuelo ? ` · ${t("cen_contra_vuelo")}` : ""))),
      h("div", { style: "flex:1;min-width:220px" },
        h("b", {}, f.folio),
        h("div", {}, f.cliente || ""),
        h("div", { clase: "gris chico" },
          [f.ejecutivo, f.ciudad, f.consultor].filter(Boolean).join(" · ")),
        f.punto ? h("div", { clase: "chico" }, f.punto) : null),
      h("div", { style: "text-align:right" },
        f.listo
          ? etiqueta(t("cen_todo_listo"), "ok")
          : etiqueta(cuantasFaltan(f.faltan), "grave"),
        h("div", { style: "margin-top:6px" },
          h("a", { clase: "chico", href: rutaDelServicio(f) },
            t("cen_ver_servicio"))))),

    f.personal.length
      ? h("div", { clase: "minimo", style: "margin-top:10px" },
          ...f.personal.map(p => h("div", { clase: "punto" },
            h("span", { clase: `marca ${p.confirmado ? "si" : ""}` },
              p.confirmado ? "✓" : "?"),
            h("span", {}, p.nombre,
              p.rol ? h("span", { clase: "gris chico" }, ` · ${p.rol}`) : null))),
          f.unidades.length
            ? h("div", { clase: "punto" },
                h("span", { clase: "placas" }, f.unidades.join(" · ")))
            : null)
      : null,

    /* Lo que falta, con lo que hay que hacer. Un renglon que dice
       "pendiente" obliga a abrir otra pantalla para saber de que se
       trata; a las seis de la tarde eso es el problema. */
    faltan.length
      ? h("ul", { clase: "minimo", style: "margin:10px 0 0;padding-left:18px;display:block" },
          ...faltan.map(p => h("li", { style: "margin-bottom:4px" },
            h("b", {}, t(`cen_p_${p.clave}`)), ": ",
            h("span", { clase: "chico" }, p.que_hacer || ""))))
      : null);
}

/* ------------------------------------------------ 3 · el pulso */

const HITOS = {
  llegada_origen: "cen_hito_llegada_origen",
  contacto_ejecutivo: "cen_hito_contacto_ejecutivo",
  llegada_destino: "cen_hito_llegada_destino",
  salida_ruta: "cen_hito_salida_ruta",
  standby: "cen_hito_standby",
  fin_servicio: "cen_hito_fin_servicio",
};

const TONO_SILENCIO = { verde: "ok", ambar: "alerta", rojo: "grave",
                        sin_reporte: "grave" };

function bandaPulso(p) {
  const caja = h("div", { clase: "tarjeta" },
    h("h3", {}, `${t("cen_pulso")}${p.cuantos ? ` · ${p.cuantos}` : ""}`),
    h("p", { clase: "gris chico", style: "margin:-6px 0 12px" },
      t("cen_pulso_sub")));

  if (!p.cuantos) {
    caja.append(h("div", { clase: "vacio" }, t("cen_pulso_nada")));
    return caja;
  }

  if (p.eventuales.length) caja.append(tablaPulso(p.eventuales));
  if (p.implantados.length) {
    caja.append(
      h("h4", { clase: "grupo" }, t("cen_implantados")),
      tablaPulso(p.implantados));
  }
  return caja;
}

function tablaPulso(filas) {
  const cuerpo = h("tbody");
  for (const f of filas) {
    cuerpo.append(h("tr", {},
      h("td", {}, h("b", {}, f.folio),
        h("div", { clase: "gris chico" },
          [f.cliente, f.personal.join(", ")].filter(Boolean).join(" · ")),
        f.unidades.length
          ? h("div", { clase: "placas chico" }, f.unidades.join(" · "))
          : null),
      h("td", {},
        etiqueta(
          f.minutos_callado === null
            ? t("cen_nunca_reporto")
            : t("cen_callado_min").replace("{n}", f.minutos_callado),
          TONO_SILENCIO[f.silencio] || ""),
        f.ultimo_hito
          ? h("div", { clase: "gris chico" },
              `${t("cen_ultimo")}: ${t(HITOS[f.ultimo_hito] || "")} `
              + `${hora(f.ultimo_en)}`)
          : null),
      h("td", { clase: "chico" },
        f.por_entrar_en_extra
          ? etiqueta(`${t("cen_extra")} · ${f.minutos_para_horas_extra} min`,
                     "alerta")
          : null,
        f.alertas_abiertas
          ? h("div", {}, etiqueta(`${f.alertas_abiertas}`, "grave"))
          : null),
      h("td", {},
        h("a", { clase: "chico", href: rutaDelServicio(f) },
          t("cen_ver_servicio")))));
  }
  return h("table", {}, cuerpo);
}

/* ---------------------------------------------- 4 · la semana */

const DIAS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"];

function bandaSemana(tira) {
  const celdas = tira.map(d => h("div", {
    clase: "tarjeta lisa",
    style: "flex:1;min-width:92px;text-align:center;margin:0",
  },
    h("div", { clase: "gris chico" },
      `${DIAS[d.dia_semana]} ${d.fecha.slice(8)}`),
    d.servicios
      ? h("div", {},
          h("div", { style: "font-size:20px;font-weight:650" }, d.servicios),
          h("div", { clase: d.incompletos ? "ambar chico" : "verde chico" },
            t("cen_dia_completos").replace("{c}", d.completos)
              .replace("{t}", d.servicios)))
      : h("div", { clase: "gris chico", style: "padding:6px 0" },
          t("cen_sin_servicios"))));

  return h("div", { clase: "tarjeta" },
    h("h3", {}, t("cen_semana")),
    h("p", { clase: "gris chico", style: "margin:-6px 0 12px" },
      t("cen_semana_sub")),
    h("div", { style: "display:flex;gap:8px;flex-wrap:wrap" }, ...celdas));
}

export function detener() {
  clearInterval(temporizador);
  temporizador = null;
}


/* ------------------------------------------- 5 · dias sin cerrar

   Un dia que se trabajo y que nadie marco se queda abierto, y mientras
   lo este no entra a nomina: alguien que trabajo no cobra por una marca
   que falto. Esta banda es la lista de trabajo para que eso no pase, del
   mas viejo al mas nuevo —el mas viejo es el que mas cerca esta de
   convertirse en un reclamo.

   Si no hay nada, la banda no existe. */

async function bandaSinCerrar(zona) {
  let d;
  try { d = await api.get("/operacion/dias-sin-cerrar"); }
  catch { return null; }
  if (!d.cuantos) return null;

  const caja = h("div", { clase: "tarjeta" },
    h("div", { clase: "encabeza-revision" },
      h("h3", {}, t("sc_titulo")),
      h("span", { clase: "etiqueta alerta" },
        t("sc_cuantos").replace("{n}", d.cuantos))),
    h("p", { clase: "sub" }, t("sc_sub")));

  for (const f of d.dias) caja.append(renglonSinCerrar(f, zona));
  return caja;
}

function renglonSinCerrar(f, zona) {
  const dias = Math.floor(f.horas_abierto / 24);
  const antiguedad = dias >= 1
    ? t("sc_dias").replace("{n}", dias)
    : t("sc_horas").replace("{n}", f.horas_abierto);

  const cuerpo = h("div", { clase: "linea-sin-cerrar" },
    h("div", {},
      h("a", { href: rutaDelServicio(f) }, h("b", {}, f.folio)),
      h("div", { clase: "chico gris" },
        `${f.fecha} · ${f.equipo} · ${f.personal.length ? f.personal
          .map(p => p.nombre).join(", ") : t("sc_sin_gente")}`)),
    h("div", { clase: "chico" },
      /* Un dia con contacto y sin fin es una marca que falto. Uno sin
         ninguna marca es un dia del que no se sabe nada, y no es lo
         mismo: el segundo hay que preguntarlo antes de firmarlo. */
      f.arranco
        ? h("span", { clase: "etiqueta alerta" }, t("sc_arranco"))
        : h("span", { clase: "etiqueta grave" }, t("sc_sin_marcas"))),
    h("div", { clase: "chico gris num" }, antiguedad));

  const zonaForm = h("div", {});
  const boton = h("button", { clase: "claro chico", onclick: () => {
    if (zonaForm.firstChild) {
      zonaForm.replaceChildren();
      boton.textContent = t("sc_cerrar");
      return;
    }
    zonaForm.append(formCerrar(f, zona));
    boton.textContent = t("sc_cancelar");
  } }, t("sc_cerrar"));

  return h("div", { clase: "renglon-sin-cerrar" },
    h("div", { clase: "encabeza-revision" }, cuerpo, boton), zonaForm);
}

function formCerrar(f, zona) {
  /* Las horas vienen llenas con las programadas: es lo que casi siempre
     paso, y pedir que alguien las teclee de cero es pedir que invente
     un numero o que se equivoque de dia. */
  const inicio = h("input", { type: "datetime-local",
    value: (f.inicio_real || f.inicio_programado).slice(0, 16) });
  const fin = h("input", { type: "datetime-local",
    value: f.fin_programado.slice(0, 16) });
  const motivo = h("textarea", { rows: 2,
    placeholder: t("sc_motivo_ejemplo") });

  const guardar = h("button", {}, t("sc_firmar"));
  const salida = h("div", {});

  guardar.addEventListener("click", async () => {
    if (motivo.value.trim().length < 10) {
      return salida.replaceChildren(aviso(t("sc_falta_motivo"), "alerta"));
    }
    guardar.disabled = true;
    try {
      const r = await api.post(
        `/operacion/jornadas/${f.jornada_id}/cerrar-a-mano`, {
          justificacion: motivo.value.trim(),
          inicio_real: inicio.value,
          fin_real: fin.value,
        });
      salida.replaceChildren(aviso(
        t("sc_cerrado").replace("{h}", r.horas)
          .replace("{n}", r.personas), "ok"));
      setTimeout(() => pintar(zona), 1200);
    } catch (e) {
      guardar.disabled = false;
      salida.replaceChildren(aviso(e.message, "grave"));
    }
  });

  return h("div", { clase: "marco-cierre" },
    h("p", { clase: "chico gris" }, t("sc_advertencia")),
    h("div", { clase: "rejilla-revision" },
      h("div", { clase: "campo" }, h("label", {}, t("sc_inicio")), inicio),
      h("div", { clase: "campo" }, h("label", {}, t("sc_fin")), fin)),
    h("div", { clase: "campo" }, h("label", {}, t("sc_motivo")), motivo),
    guardar, salida);
}

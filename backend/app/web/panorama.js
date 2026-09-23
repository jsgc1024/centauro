/* La fotografia de la operacion, para quien decide.

   Escrita al reves que las demas pantallas: arriba una sola frase que
   dice si estamos bien, y lo demas solo aparece cuando hay algo que ver.
   Un dia tranquilo esta pantalla esta casi vacia, y de eso se trata: si
   estuviera siempre llena, en tres semanas nadie la abre.

   Ninguna regla se decide aqui. Cuanto silencio es mucho lo dice el
   motor —el mismo numero que usa la central— y esta pantalla solo lo
   pinta. */
import { api } from "./api.js";
import { aviso, conAyuda, dinero, etiqueta, fecha, h, hora } from "./util.js";
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

function pintar(p) {
  const bloques = [estado(p), enLaCalle(p)];
  for (const tira of p.dia) bloques.push(diaDelPais(tira));
  bloques.push(dineroBloque(p.dinero), calidad(p.calidad));
  return bloques.filter(Boolean);
}

/* ------------------------------------------------ el renglon de arriba */

const TONO = { normal: "ok", atender: "alerta", grave: "grave" };

function estado(p) {
  const e = p.estado;
  const caja = h("div", { clase: "tarjeta estado " + e.nivel });

  caja.append(h("div", { clase: "estado_fila" },
    h("h3", { style: "margin:0" },
      h("span", { clase: "luz " + e.nivel }), " ", tituloDelEstado(e)),
    h("span", { clase: "gris chico" }, fecha(p.momento) + " · " + hora(p.momento))));

  caja.append(h("div", { clase: "estado_conteo" }, ...conteo(p.en_la_calle)));

  if (!e.atender.length) {
    caja.append(h("div", { clase: "chico gris" }, t("pan_todos_reportando")));
    return caja;
  }
  for (const cosa of e.atender) caja.append(renglonAtender(cosa));
  if (e.mas) {
    caja.append(h("div", { clase: "chico gris", style: "margin-top:8px" },
      t("pan_y_mas").replace("{n}", e.mas)));
  }
  return caja;
}

function tituloDelEstado(e) {
  if (!e.atender.length) return t("pan_normal");
  const n = e.atender.length + e.mas;
  return n === 1 ? t("pan_una_cosa") : t("pan_n_cosas").replace("{n}", n);
}

/* La gente primero: el negocio es cuidar personas, no mover folios. */
function conteo(c) {
  const partes = [
    h("b", {}, t("pan_personas").replace("{n}", c.personas)),
    " · ",
    t("pan_ejecutivos").replace("{n}", c.ejecutivos),
    " · ",
    t("pan_servicios_n").replace("{n}", c.servicios),
  ];
  if (c.eventual && c.implantado) {
    partes.push(h("div", { clase: "chico gris" },
      t("pan_desglose").replace("{e}", c.eventual)
                       .replace("{i}", c.implantado)));
  }
  return partes;
}

function renglonAtender(c) {
  const linea = h("div", { clase: "renglon_atender " + c.nivel });
  linea.append(h("div", {}, h("b", {}, textoAtender(c))));
  const pie = detalleAtender(c);
  if (pie) linea.append(h("div", { clase: "chico gris" }, pie));
  if (c.servicio_id) {
    linea.append(h("a", { clase: "boton chico",
                          href: `#/servicios/${c.servicio_id}` }, t("pan_abrir")));
  }
  return linea;
}

function textoAtender(c) {
  /* El canal va abajo, en el pie: "Alerta de panico · Boton de panico
     (app)" decia panico dos veces en el mismo renglon. */
  if (c.tipo === "panico") return t("pan_panico_ahora");
  if (c.tipo === "silencio") {
    /* Las dos claves escritas enteras, no armadas al vuelo: asi
       revisar.py puede comprobar que existen en los tres idiomas. */
    const texto = c.minutos_callado === null
      ? t("pan_nunca_reporto_srv")
      : t("pan_callado_srv").replace("{n}", c.minutos_callado);
    return texto.replace("{s}", c.servicio).replace("{e}", c.equipo);
  }
  return t("pan_sin_listo").replace("{s}", c.servicio)
                           .replace("{n}", c.en_minutos)
                           .replace("{f}", c.faltas.map(f => t(FALTAS[f])).join(", "));
}

function detalleAtender(c) {
  if (c.tipo === "panico") {
    const canal = t(CANALES[c.canal] || c.canal);
    return c.reportada_en
      ? `${canal} · ${t("pan_reportada_a_las").replace("{t}", hora(c.reportada_en))}`
      : canal;
  }
  if (c.tipo === "silencio" && c.ultima_marca) {
    return t("pan_ultima_marca").replace("{h}", t(HITOS[c.ultimo_hito] || ""))
                                .replace("{t}", hora(c.ultima_marca));
  }
  return "";
}

const CANALES = {
  boton_app: "canal_boton_app",
  boton_vehiculo: "canal_boton_vehiculo",
  llamada: "canal_llamada",
};

const FALTAS = {
  personal: "pan_f_personal",
  confirmar: "pan_f_confirmar",
  unidad: "pan_f_unidad",
  meet_and_greet: "pan_f_meet_and_greet",
};

/* El estatus viene en clave y aqui se traduce. Antes salia el valor
   crudo del servidor y en la consola en ingles decia "sin calcular". */
const ESTATUS_NOMINA = {
  sin_calcular: "pan_n_sin_calcular",
  calculada: "pan_n_calculada",
  pagada: "pan_n_pagada",
};

const HITOS = {
  llegada_origen: "cen_hito_llegada_origen",
  contacto_ejecutivo: "cen_hito_contacto_ejecutivo",
  llegada_destino: "cen_hito_llegada_destino",
  salida_ruta: "cen_hito_salida_ruta",
  standby: "cen_hito_standby",
  fin_servicio: "cen_hito_fin_servicio",
};

/* ------------------------------------------------ la gente, por pais */

function enLaCalle(p) {
  if (!p.paises.length) return null;
  const cuerpo = h("tbody");
  for (const f of p.paises) {
    cuerpo.append(h("tr", {},
      h("td", {}, h("b", {}, f.pais || "—"),
        f.plazas.length
          ? h("div", { clase: "gris chico solo_ancho" },
              f.plazas.map(x => `${x.plaza} ${x.personas}`).join(" · "))
          : ""),
      h("td", { clase: "num" }, hora(f.hora_local)),
      h("td", { clase: "num" }, f.personas),
      h("td", { clase: "num solo_ancho" }, f.servicios),
      h("td", {}, f.callados
        ? etiqueta(t("pan_callados_n").replace("{n}", f.callados), "grave")
        : etiqueta(t("pan_todos_ok"), "ok"))));
  }
  return h("div", { clase: "tarjeta paises" },
    conAyuda("h3", t("pan_por_pais"), "ay_pan_paises"),
    h("table", {}, h("thead", {}, h("tr", {},
      h("th", {}, t("pais")), h("th", {}, t("hora")),
      h("th", {}, t("pan_col_personas")),
      h("th", { clase: "solo_ancho" }, t("col_servicio")),
      h("th", {}, ""))), cuerpo));
}

/* ------------------------------------------------ la tira del dia

   Un eje por pais y no uno solo para todos: las 14:00 de la tira son las
   14:00 de donde esta parado ese equipo. Un eje unico con Mexico y
   Brasil encima no querria decir nada. */

/* Los minutos se cuentan desde la medianoche de HOY, no desde la del
   reloj de cada marca: asi una jornada de noche que empieza a las 21:00
   y termina a las 05:00 sale como una barra que cruza el final del eje,
   y no como un muñon al reves. En proteccion ejecutiva la jornada
   nocturna es rutina, no excepcion. */
function medianoche(tira) {
  const f = new Date(tira.ahora);
  f.setHours(0, 0, 0, 0);
  return f;
}

function minutosDesde(base, iso) {
  return Math.round((new Date(iso) - base) / 60000);
}

function diaDelPais(tira) {
  const base = medianoche(tira);
  const min = (iso) => minutosDesde(base, iso);
  const finales = tira.barras.map(b => b.fin_programado || b.inicio);
  const desde = Math.floor(
    Math.min(...tira.barras.map(b => min(b.inicio))) / 60) * 60;
  const hasta = Math.ceil(Math.max(...finales.map(min)) / 60) * 60;
  const largo = Math.max(hasta - desde, 60);
  const sitio = (min) => ((Math.min(Math.max(min, desde), hasta) - desde) / largo) * 100;

  const filas = h("div", { clase: "tira" });
  for (const b of tira.barras) {
    const ini = min(b.inicio);
    const fin = min(b.fin_programado || b.inicio);
    const barra = h("div", {
      clase: "tramo " + b.estatus + (b.silencio ? " s_" + b.silencio : ""),
      style: `left:${sitio(ini)}%;width:${Math.max(sitio(fin) - sitio(ini), 1)}%`,
      title: `${b.servicio} · ${hora(b.inicio)}—${hora(b.fin_programado || b.inicio)}`,
    });
    const carril = h("div", { clase: "carril" }, barra);
    if (b.ultima_marca) {
      carril.append(h("div", { clase: "muesca",
                               style: `left:${sitio(min(b.ultima_marca))}%`,
                               title: hora(b.ultima_marca) }));
    }
    filas.append(
      h("div", { clase: "renglon_tira" },
        h("div", { clase: "chico etiqueta_tira" },
          h("b", {}, b.servicio), " ", h("span", { clase: "gris" }, b.equipo)),
        carril));
  }

  /* La linea del ahora va sobre una capa con la misma forma que los
     renglones —hueco de la etiqueta + pista—, porque su porcentaje es
     del ancho de la pista, no del de la tira. Puesta directamente sobre
     la tira quedaba corrida el ancho de la etiqueta. */
  const ahoraMin = min(tira.ahora);
  if (ahoraMin >= desde && ahoraMin <= hasta) {
    filas.append(h("div", { clase: "capa_ahora" },
      h("div", { clase: "etiqueta_tira" }),
      h("div", { clase: "pista" },
        h("div", { clase: "ahora", style: `left:${sitio(ahoraMin)}%` }))));
  }

  const marcas = h("div", { clase: "horas chico gris" });
  for (let corte = desde; corte <= hasta; corte += 120) {
    /* El eje puede pasar de la medianoche: 26:00 se rotula 02. */
    const reloj = ((Math.floor(corte / 60) % 24) + 24) % 24;
    marcas.append(h("span", { style: `left:${sitio(corte)}%` },
      String(reloj).padStart(2, "0")));
  }

  return h("div", { clase: "tarjeta" },
    conAyuda("h3", `${t("pan_hoy")} · ${tira.pais} ${hora(tira.ahora)}`,
             "ay_pan_hoy"),
    filas, marcas);
}

/* ------------------------------------------------ el dinero */

function cifra(titulo, valor, pie, tono = "") {
  return h("tr", {},
    h("td", {}, titulo),
    h("td", { clase: "num" }, h("b", {}, valor)),
    h("td", { clase: "chico " + (tono || "gris") }, pie));
}

function dineroBloque(d) {
  const cuerpo = h("tbody");
  cuerpo.append(cifra(t("pan_por_depositar_c"),
    dinero(d.por_depositar.monto),
    Number(d.por_depositar.cuantos) === 1 ? t("pan_solicitud_uno")
      : t("pan_solicitudes").replace("{n}", d.por_depositar.cuantos)));

  const a = d.afuera_sin_comprobar;
  cuerpo.append(cifra(t("fin_afuera"), dinero(a.monto),
    (Number(a.personas) === 1 ? t("pan_persona_uno")
      : t("pan_personas_n").replace("{n}", a.personas))
    + (Number(a.vencido) ? ` · ${dinero(a.vencido)} ${t("pan_vencido_suelto")}` : ""),
    Number(a.vencido) ? "rojo" : ""));

  const n = d.nomina_de_la_semana;
  cuerpo.append(cifra(t("pan_nomina_semana"), dinero(n.total),
    `${t("pan_corte")} ${fecha(n.fecha_corte)} · `
    + t(ESTATUS_NOMINA[n.estatus] || "pan_n_sin_calcular")));

  const c = d.cierres;
  const caja = h("div", { clase: "tarjeta" },
    conAyuda("h3", t("pan_dinero"), "ay_pan_dinero"),
    h("table", {}, cuerpo),
    caminoAlCobro(d));

  if (c.devueltos.length) {
    caja.append(h("div", { style: "margin-top:12px" },
      conAyuda("h4", t("pan_regresados"), "ay_pan_regresados"),
      h("ul", { clase: "chico", style: "margin:0;padding-left:18px" },
        ...c.devueltos.map(x =>
          h("li", {}, `${x.servicio}: ${x.motivo || t("pan_sin_motivo")}`)))));
  }
  return caja;
}

/* El camino al cobro (seccion 59): cuantos servicios --y meses de
   implantado-- hay en cada fase del cierre, y lo que vence primero. Lo
   que antes decia "cierres abiertos" contaba los que el personal
   todavia comprobaba y los juzgaba con el reloj del consultor. */
const MESES_PAN = ["bon_mes_1", "bon_mes_2", "bon_mes_3", "bon_mes_4",
                   "bon_mes_5", "bon_mes_6", "bon_mes_7", "bon_mes_8",
                   "bon_mes_9", "bon_mes_10", "bon_mes_11", "bon_mes_12"];

function caminoAlCobro(d) {
  const c = d.camino;
  if (!c) return null;
  const celda = (titulo, cifra_, pie, tono = "") => h("div", {},
    h("div", { clase: "chico gris" }, titulo),
    h("div", { clase: "cifra", style: tono }, cifra_),
    pie);
  const fuera = c.sin_visto_bueno.fuera_de_plazo;
  const grid = h("div", { clase: "camino" },
    celda(t("pan_camino_comprobacion"), c.comprobacion.cuantos,
          h("div", { clase: "chico gris" }, t("pan_camino_el_personal"))),
    celda(t("est_sin_visto_bueno"), c.sin_visto_bueno.cuantos,
          fuera ? h("div", { clase: "chico rojo" },
                    t("pan_camino_fuera").replace("{n}", fuera))
                : h("div", { clase: "chico gris" }, t("pan_camino_del_consultor"))),
    celda(t("est_en_facturacion"), c.en_facturacion.cuantos,
          h("div", { clase: "chico gris num" }, dinero(c.en_facturacion.monto))),
    celda(t("pan_camino_por_facturar"), c.por_facturar.cuantos,
          h("div", { clase: "chico gris" }, t("pan_camino_sin_factura")),
          c.por_facturar.cuantos ? "color:var(--alerta)" : ""));

  const lista = (d.vence_primero || []).map(x => {
    const mes = x.mes ? ` · ${t(MESES_PAN[x.mes - 1]).toLowerCase()}` : "";
    const tiempo = x.minutos < 0
      ? h("span", { clase: "rojo" }, t("pan_fuera_desde").replace(
          "{q}", cuanto(-x.minutos)))
      : h("span", { style: x.minutos < 12 * 60
                      ? "color:var(--alerta);font-weight:650" : "" },
          t("pan_vence_en").replace("{q}", cuanto(x.minutos)));
    return h("li", {}, `${x.folio}${mes} · ${x.consultor || "—"}`
      + (x.regresado ? ` · ${t("pan_regresado")}` : "") + " · ", tiempo);
  });
  return h("div", {},
    conAyuda("h4", t("pan_camino"), "ay_pan_camino",
             { style: "margin:16px 0 4px" }),
    grid,
    lista.length ? h("div", {},
      h("h4", { style: "margin:16px 0 4px" }, t("pan_vence_primero")),
      h("ul", { clase: "chico", style: "margin:0;padding-left:18px" }, ...lista))
      : "");
}

function cuanto(minutos) {
  if (minutos < 60) return t("cie_n_min").replace("{n}", minutos);
  return t("cie_n_h").replace("{n}", Math.floor(minutos / 60));
}

/* ------------------------------------------------ la calidad del reporte

   La unica parte de la pantalla que no habla de la operacion sino de si
   lo que nos reportan es cierto. */

function calidad(c) {
  const hay = c.intentos_fuera_de_geocerca || c.marcas_por_validar
           || c.unidades_sin_revision_de_entrada || c.relevos_hoy;
  if (!hay) return null;

  const cuerpo = h("tbody");
  const renglon = (titulo, valor, abre) => {
    if (!valor) return;
    cuerpo.append(h("tr", {},
      h("td", {}, titulo),
      h("td", { clase: "num" }, h("b", {}, valor)),
      h("td", {}, abre
        ? h("button", { clase: "chico claro ver_marcas", type: "button",
                        onclick: (e) => verMarcas(e) }, t("pan_ver_marcas"))
        : "")));
  };
  renglon(t("pan_intentos_geocerca"), c.intentos_fuera_de_geocerca, true);
  renglon(t("pan_por_validar"), c.marcas_por_validar, true);
  renglon(t("pan_sin_entrada_n"), c.unidades_sin_revision_de_entrada, false);
  renglon(t("pan_relevos_hoy"), c.relevos_hoy, false);

  return h("div", { clase: "tarjeta" },
    conAyuda("h3", t("pan_calidad"), "ay_pan_calidad"),
    h("p", { clase: "sub" }, t("pan_calidad_sub")),
    h("table", {}, cuerpo));
}

/* El boton abre y cierra. Antes solo abria: la lista se quedaba
   pegada abajo de la tarjeta y volver a picarle la recargaba igual, asi
   que la unica manera de quitarla de la pantalla era recargar la
   pagina. Con dieciseis marcas eso es media pantalla que ya no se
   puede tapar. */

function cerrarMarcas(caja) {
  const abierta = caja.querySelector(".detalle_marcas");
  if (abierta) abierta.remove();
  for (const b of caja.querySelectorAll("button.ver_marcas")) {
    b.textContent = t("pan_ver_marcas");
    b.dataset.abierto = "";
  }
}

async function verMarcas(e) {
  const boton = e.target;
  const caja = boton.closest(".tarjeta");
  const estaba = boton.dataset.abierto === "1";
  cerrarMarcas(caja);
  if (estaba) return;
  boton.disabled = true;
  try {
    const d = await api.get("/panorama/marcas");
    caja.append(listaMarcas(d));
    boton.textContent = t("pan_ocultar_marcas");
    boton.dataset.abierto = "1";
  } catch (err) {
    caja.append(h("div", { clase: "detalle_marcas" }, aviso(err.message, "grave")));
  }
  boton.disabled = false;
}

function listaMarcas(d) {
  const caja = h("div", { clase: "detalle_marcas", style: "margin-top:14px" });

  /* La marca se rechaza y el hito no se guarda; lo que queda es la
     alerta, y ahi va el nombre de quien lo intento. */
  if (d.intentos_fuera_de_geocerca.length) {
    const cuerpo = h("tbody");
    for (const f of d.intentos_fuera_de_geocerca) {
      cuerpo.append(h("tr", {},
        h("td", {}, h("b", {}, f.servicio),
          h("div", { clase: "gris chico" }, `${t("col_equipo")} ${f.equipo}`)),
        h("td", {}, f.persona || "—"),
        h("td", { clase: "num" }, f.creada_en ? hora(f.creada_en) : "—"),
        h("td", { clase: "chico" }, f.mensaje)));
    }
    caja.append(h("h4", {}, t("pan_intentos_geocerca")),
      h("table", {}, h("thead", {}, h("tr", {},
        h("th", {}, t("col_servicio")), h("th", {}, t("srv_persona")),
        h("th", {}, t("hora")), h("th", {}, t("pan_detalle")))), cuerpo));
  }

  if (d.por_validar.length) {
    const cuerpo = h("tbody");
    for (const f of d.por_validar) {
      cuerpo.append(h("tr", {},
        h("td", {}, h("b", {}, f.servicio),
          h("div", { clase: "gris chico" }, `${t("col_equipo")} ${f.equipo}`)),
        h("td", {}, f.persona || "—"),
        h("td", {}, t(HITOS[f.tipo] || "")),
        h("td", { clase: "num" }, f.marcado_en ? hora(f.marcado_en) : "—")));
    }
    caja.append(h("h4", {}, t("pan_por_validar")),
      h("table", {}, h("thead", {}, h("tr", {},
        h("th", {}, t("col_servicio")), h("th", {}, t("srv_persona")),
        h("th", {}, t("pan_marca")), h("th", {}, t("hora")))), cuerpo));
  }
  return caja;
}

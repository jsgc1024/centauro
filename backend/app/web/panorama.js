/* La fotografia de la operacion, para quien decide.

   Escrita al reves que las demas pantallas: arriba una sola frase que
   dice si estamos bien, y lo demas solo aparece cuando hay algo que ver.
   Un dia tranquilo esta pantalla esta casi vacia, y de eso se trata: si
   estuviera siempre llena, en tres semanas nadie la abre.

   Ninguna regla se decide aqui. Cuanto silencio es mucho lo dice el
   motor —el mismo numero que usa la central— y esta pantalla solo lo
   pinta. */
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
      h("span", { clase: "punto " + e.nivel }), " ", titulo(e)),
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

function titulo(e) {
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
  const linea = h("div", { clase: "atender " + c.nivel });
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
    h("h3", {}, t("pan_por_pais")),
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
      clase: "barra " + b.estatus + (b.silencio ? " s_" + b.silencio : ""),
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
    h("h3", {}, `${t("pan_hoy")} · ${tira.pais} ${hora(tira.ahora)}`),
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
    t("pan_solicitudes").replace("{n}", d.por_depositar.cuantos)));

  const a = d.afuera_sin_comprobar;
  cuerpo.append(cifra(t("fin_afuera"), dinero(a.monto),
    t("pan_personas_n").replace("{n}", a.personas)
    + (Number(a.vencido) ? ` · ${dinero(a.vencido)} ${t("pan_vencido_suelto")}` : ""),
    Number(a.vencido) ? "rojo" : ""));

  const n = d.nomina_de_la_semana;
  cuerpo.append(cifra(t("pan_nomina_semana"), dinero(n.total),
    `${t("pan_corte")} ${fecha(n.fecha_corte)} · `
    + t(ESTATUS_NOMINA[n.estatus] || "pan_n_sin_calcular")));

  const c = d.cierres;
  cuerpo.append(cifra(t("pan_cierres_c"), c.abiertos,
    c.vencidos ? t("pan_vencidos_n").replace("{n}", c.vencidos)
               : t("pan_sin_vencidos"),
    c.vencidos ? "rojo" : ""));

  const caja = h("div", { clase: "tarjeta" },
    h("h3", {}, t("pan_dinero")), h("table", {}, cuerpo));

  if (c.devueltos.length) {
    caja.append(h("div", { style: "margin-top:12px" },
      h("h4", {}, t("pan_regresados")),
      h("ul", { clase: "chico", style: "margin:0;padding-left:18px" },
        ...c.devueltos.map(x =>
          h("li", {}, `${x.servicio}: ${x.motivo || t("pan_sin_motivo")}`)))));
  }
  return caja;
}

/* ------------------------------------------------ la calidad del reporte

   La unica parte de la pantalla que no habla de la operacion sino de si
   lo que nos reportan es cierto. */

function calidad(c) {
  const hay = c.fuera_de_geocerca || c.marcas_por_validar
           || c.unidades_sin_revision_de_entrada || c.relevos_hoy;
  if (!hay) return null;

  const cuerpo = h("tbody");
  const renglon = (titulo, valor, abre) => {
    if (!valor) return;
    cuerpo.append(h("tr", {},
      h("td", {}, titulo),
      h("td", { clase: "num" }, h("b", {}, valor)),
      h("td", {}, abre
        ? h("button", { clase: "chico claro", type: "button",
                        onclick: (e) => verMarcas(e) }, t("pan_ver_marcas"))
        : "")));
  };
  renglon(t("pan_fuera_geocerca"), c.fuera_de_geocerca, true);
  renglon(t("pan_por_validar"), c.marcas_por_validar, true);
  renglon(t("pan_sin_entrada_n"), c.unidades_sin_revision_de_entrada, false);
  renglon(t("pan_relevos_hoy"), c.relevos_hoy, false);

  return h("div", { clase: "tarjeta" },
    h("h3", {}, t("pan_calidad")),
    h("p", { clase: "sub" }, t("pan_calidad_sub")),
    h("table", {}, cuerpo));
}

async function verMarcas(e) {
  const boton = e.target;
  boton.disabled = true;
  const caja = boton.closest(".tarjeta");
  const vieja = caja.querySelector(".detalle_marcas");
  if (vieja) vieja.remove();
  try {
    const d = await api.get("/panorama/marcas");
    caja.append(listaMarcas(d));
  } catch (err) {
    caja.append(h("div", { clase: "detalle_marcas" }, aviso(err.message, "grave")));
  }
  boton.disabled = false;
}

function listaMarcas(d) {
  const caja = h("div", { clase: "detalle_marcas", style: "margin-top:14px" });
  const grupo = (titulo, filas, conDistancia) => {
    if (!filas.length) return;
    const cuerpo = h("tbody");
    for (const f of filas) {
      cuerpo.append(h("tr", {},
        h("td", {}, h("b", {}, f.servicio),
          h("div", { clase: "gris chico" }, `${t("col_equipo")} ${f.equipo}`)),
        h("td", {}, f.persona || "—"),
        h("td", {}, t(HITOS[f.tipo] || "")),
        h("td", { clase: "num" }, f.marcado_en ? hora(f.marcado_en) : "—"),
        h("td", { clase: "num" }, conDistancia && f.distancia_m !== null
          ? t("pan_a_metros").replace("{n}", Math.round(f.distancia_m))
              .replace("{g}", f.geocerca_m)
          : "")));
    }
    caja.append(h("h4", {}, titulo),
      h("table", {}, h("thead", {}, h("tr", {},
        h("th", {}, t("col_servicio")), h("th", {}, t("srv_persona")),
        h("th", {}, t("pan_marca")), h("th", {}, t("hora")),
        h("th", {}, ""))), cuerpo));
  };
  grupo(t("pan_fuera_geocerca"), d.fuera_de_geocerca, true);
  grupo(t("pan_por_validar"), d.por_validar, false);
  return caja;
}

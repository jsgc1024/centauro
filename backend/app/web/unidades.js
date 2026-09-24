/* Unidades: la flota con su GPS (seccion 60).

   Cada unidad de Odoo con su GPS de Pegasus, ligadas por la placa, y lo
   que hay que arreglar antes de que haga falta: el GPS que no reporta,
   la placa que no coincide. Lo que no liga dice donde se corrige --en
   Odoo o en Pegasus-- y al corregirlo se liga solo: nada se captura dos
   veces.

   Lo que esta pantalla NO dice es donde esta una unidad. Eso se usa
   durante el servicio, en Monitoreo; aqui solo si su GPS reporta, que
   trae hoy y su odometro.

   Sin "?": cada renglon dice que le falta y donde se corrige, y la
   cabeza dice que se lee y de donde. */
import { api, sesion } from "./api.js";
import { aviso, buscador, campo, coincide, etiqueta, fecha, h, hora,
         lista } from "./util.js";
import { t } from "./idioma.js";

let paisActual = null;
let soloRevisar = false;
let busqueda = "";
let ultimo = null;

function reemplazar(texto, valores) {
  return Object.entries(valores).reduce(
    (s, [k, v]) => s.split(`{${k}}`).join(v ?? ""), texto);
}

export async function pantallaUnidades(main) {
  const paises = await api.get("/catalogos/paises");
  const suyo = paises.find(p => p.id === (sesion.usuario || {}).pais_id);
  paisActual = paisActual || (suyo || paises[0] || {}).id;

  const selector = lista("pais", paises.map(
    p => ({ valor: p.id, texto: p.nombre })));
  selector.value = paisActual;
  const casilla = h("input", { type: "checkbox", id: "solo_revisar" });
  casilla.checked = soloRevisar;
  const zona = h("div");

  const caja = buscador(t("uni_buscar_ayuda"), (texto) => {
    busqueda = texto;
    dibujar(zona);
  });
  caja.value = busqueda;

  selector.addEventListener("change", () => {
    paisActual = Number(selector.value);
    pintar(zona);
  });
  casilla.addEventListener("change", () => {
    soloRevisar = casilla.checked;
    dibujar(zona);
  });

  main.append(
    h("h1", {}, t("uni_titulo")),
    h("p", { clase: "sub" }, t("uni_sub")),
    h("div", { clase: "tarjeta lisa" },
      h("div", { clase: "rejilla tres" },
        campo(t("pais"), selector),
        campo(t("bus_buscar"), caja),
        h("div", { clase: "campo" },
          h("label", { for: "solo_revisar" }, " "),
          h("label", { clase: "casilla", for: "solo_revisar" },
            casilla, " ", t("uni_solo_revisar"))))),
    zona);

  await pintar(zona);
}

async function pintar(zona) {
  zona.replaceChildren(h("p", { clase: "gris" }, t("per_cargando")));
  try {
    ultimo = await api.get(`/gps/unidades?pais_id=${paisActual}`);
  } catch (err) {
    ultimo = null;
    return zona.replaceChildren(aviso(err.message, "grave"));
  }
  dibujar(zona);
}

/* Cuanto hace, en la unidad que se lee de un vistazo. */
function hace(minutos) {
  if (minutos === null || minutos === undefined) return "—";
  if (minutos < 60) return reemplazar(t("uni_hace_min"), { n: minutos });
  if (minutos < 48 * 60) {
    return reemplazar(t("uni_hace_h"), { n: Math.floor(minutos / 60) });
  }
  return reemplazar(t("uni_hace_d"), { n: Math.floor(minutos / 1440) });
}

function conexion(d) {
  const g = d.grupo || {};
  if (!d.conectado) return aviso(t("uni_sin_conexion"), "alerta");
  if (g.error) {
    return aviso(reemplazar(t("uni_error"), { e: g.error }), "grave");
  }
  if (g.hace_min !== null && g.hace_min !== undefined) {
    return h("p", { clase: "gris chico", style: "margin:0 0 10px" },
      reemplazar(t("uni_leido"), { hace: hace(g.hace_min) }));
  }
  return aviso(t("uni_sin_lectura"), "alerta");
}

function cifras(d) {
  const c = d.cifras;
  const celda = (titulo, numero, pie, color) => h("div", {},
    h("div", { clase: "chico gris" }, titulo),
    h("div", { clase: "cifra", style: color ? `color:${color}` : "" },
      String(numero)),
    h("div", { clase: "chico gris" }, pie));
  const sinLigar = c.sin_ligar_pegasus + c.sin_gps;
  return h("div", { clase: "camino", style: "background:#fff;margin:0 0 14px" },
    celda(t("uni_en_pegasus"), c.en_pegasus,
          reemplazar(t("uni_grupo"), { g: (d.grupo || {}).nombre || "—" })),
    celda(t("uni_ligadas"), c.ligadas, t("uni_ligadas_pie")),
    celda(t("uni_sin_ligar"), sinLigar,
          reemplazar(t("uni_sin_ligar_pie"),
                     { p: c.sin_ligar_pegasus, c: c.sin_gps }),
          sinLigar ? "var(--alerta)" : ""),
    celda(t("uni_sin_senal"), c.sin_senal, t("uni_sin_senal_pie"),
          c.sin_senal ? "var(--grave)" : ""));
}

function sinPlaca(d) {
  const n = d.sin_placa.length;
  if (!n) return null;
  return h("div", { clase: "aviso alerta", style: "margin:0 0 14px" },
    reemplazar(t(n === 1 ? "uni_aviso_sin_placa_uno" : "uni_aviso_sin_placa"),
               { n, ids: d.sin_placa.join(", ") }));
}

/* Por que una unidad de Pegasus no liga: que es, por que, y donde se
   corrige. Los mapas van escritos enteros a proposito: una clave armada
   al vuelo no se encuentra buscandola. */
const NO_LIGA = {
  sin_placa: ["uni_sin_placa", "uni_sin_placa_det", "uni_sin_placa_pie"],
  repetida: ["uni_repetida", "uni_repetida_det", "uni_repetida_pie"],
  no_esta: ["uni_no_esta", "uni_no_esta_det", "uni_no_esta_pie"],
};

const TALLER = {
  mantenimiento_correctivo: "imp_taller_correctivo",
  mantenimiento_preventivo: "imp_taller_preventivo",
};

function celdaUnidad(f) {
  if (f.tipo === "pegasus") {
    /* Que es y por que no liga. Lo que se hace al respecto va en la
       columna del GPS, junto a su etiqueta. */
    return h("td", {},
      f.placa
        ? h("span", { clase: "placas" }, f.placa)
        : h("span", {}, h("span", { clase: "chico gris" }, t("uni_pegasus")),
            " ", h("span", { clase: "placas" }, String(f.pegasus_id))),
      h("div", { clase: "chico", style: "margin-top:4px" },
        h("b", {}, t((NO_LIGA[f.motivo] || NO_LIGA.no_esta)[0]))),
      h("div", { clase: "chico gris" },
        t((NO_LIGA[f.motivo] || NO_LIGA.no_esta)[1])),
      f.marca_modelo
        ? h("div", { clase: "chico gris" },
            [f.marca_modelo, f.color, f.anio].filter(Boolean).join(" · "))
        : null);
  }
  return h("td", {},
    h("span", { clase: "placas" }, f.placa),
    h("div", { clase: "chico", style: "margin-top:4px" },
      h("b", {}, [f.categoria, f.plaza].filter(Boolean).join(" · "))),
    h("div", { clase: "chico gris" },
      [f.marca_modelo, f.color, f.anio].filter(Boolean).join(" · ") || "—"));
}

function celdaGps(f) {
  const lineas = [];
  if (f.gps === "reporta") {
    lineas.push(etiqueta(t("uni_reporta"), "ok"),
                h("div", { clase: "chico gris" }, hace(f.hace_min)));
  } else if (f.gps === "sin_senal") {
    lineas.push(etiqueta(t("uni_chip_sin_senal"), "grave"),
                h("div", { clase: "chico gris" },
                  f.reporte_en
                    ? reemplazar(t("uni_desde"),
                                 { f: fecha(f.reporte_en), h: hora(f.reporte_en) })
                    : t("uni_nunca")));
  } else if (f.gps === "sin_gps") {
    lineas.push(etiqueta(t("uni_chip_sin_gps"), "alerta"),
                h("div", { clase: "chico gris" }, t("uni_sin_gps_pie")));
  } else {
    lineas.push(etiqueta(t("uni_chip_sin_ligar"), "alerta"),
                h("div", { clase: "chico gris" },
                  t((NO_LIGA[f.motivo] || NO_LIGA.no_esta)[2])));
  }
  if (f.sin_encendido) {
    lineas.push(h("div", { clase: "chico", style: "color:#7a5c07" },
      t("uni_sin_encendido")));
  }
  return h("td", {}, ...lineas);
}

function celdaHoy(f) {
  if (!f.hoy) return h("td", { clase: "chico gris" }, "—");
  const lineas = [];
  if (f.hoy.estado === "servicio") {
    lineas.push(etiqueta(t("uni_en_servicio"), "azul"),
                h("div", { clase: "chico" },
                  [f.hoy.folio, f.hoy.persona].filter(Boolean).join(" · ")));
  } else if (f.hoy.estado === "taller") {
    lineas.push(etiqueta(t("uni_en_taller"), "cafe"),
                h("div", { clase: "chico gris" },
                  reemplazar(t("uni_taller_pie"), {
                    tipo: t(TALLER[f.hoy.tipo] || "uni_taller_otro"),
                    f: fecha(f.hoy.desde) })
                  + (f.hoy.de_odoo ? ` · ${t("uni_de_odoo")}` : "")));
  } else {
    lineas.push(h("span", { clase: "chico gris" }, t("uni_libre")));
  }
  /* La que no reporta y ya tiene servicio lo dice en rojo, con el dia
     que queda para arreglarla. */
  if (f.gps === "sin_senal") {
    if (f.hoy.estado === "servicio") {
      lineas.push(h("div", { clase: "chico rojo" },
        reemplazar(t("uni_hoy_sin_senal"), { folio: f.hoy.folio })));
    } else if (f.manana) {
      lineas.push(h("div", { clase: "chico rojo" },
        reemplazar(t("uni_manana"), { folio: f.manana.folio })));
    }
  }
  return h("td", {}, ...lineas);
}

function celdaOdometro(f) {
  if (!f.odometro_km) return h("td", { clase: "gris" }, "—");
  return h("td", { clase: "num", style: "white-space:nowrap" },
    `${Math.round(f.odometro_km).toLocaleString()} km`,
    f.gps === "sin_senal" && f.reporte_en
      ? h("div", { clase: "chico gris" },
          reemplazar(t("uni_al"), { f: fecha(f.reporte_en) }))
      : null);
}

function porRevisar(f) {
  return f.gps !== "reporta" || f.sin_encendido;
}

function dibujar(zona) {
  if (!ultimo) return;
  let filas = ultimo.unidades;
  if (soloRevisar) filas = filas.filter(porRevisar);
  const q = busqueda.trim();
  if (q) {
    filas = filas.filter(f => coincide(q, f.placa, f.categoria, f.plaza,
                                       f.marca_modelo, String(f.pegasus_id || "")));
  }
  const cuerpo = h("tbody", {}, ...filas.map(f => h("tr", {},
    celdaUnidad(f), celdaGps(f), celdaHoy(f), celdaOdometro(f))));
  zona.replaceChildren(
    conexion(ultimo),
    sinPlaca(ultimo) || h("div"),
    cifras(ultimo),
    filas.length
      ? h("div", { clase: "tarjeta lisa", style: "padding:0" },
          h("table", {},
            h("thead", {}, h("tr", {},
              h("th", {}, t("uni_col_unidad")), h("th", {}, t("uni_col_gps")),
              h("th", {}, t("uni_col_hoy")), h("th", {}, t("uni_col_odometro")))),
            cuerpo))
      : aviso(q ? t("bus_nada").replace("{q}", q)
                : (soloRevisar && ultimo.unidades.length ? t("uni_todo_bien")
                                                         : t("uni_vacio")),
              soloRevisar && !q && ultimo.unidades.length ? "ok" : ""));
}

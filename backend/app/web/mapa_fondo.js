/* El fondo del mapa de riesgo: el Nivel Centauro pintado por estado o por
   municipio (seccion 135). Lo usan la consola y la app del cliente.

   Los colores son los del tablero de Power BI de la Central (Salvador,
   2 oct: "los colores de riesgo como estan los del power bi"): verde,
   ambar y rojo corridos segun el numero, no cinco cajas de color. Un 61 y
   un 79 son los dos "medio alto", pero el 79 ya se ve casi rojo, como en
   su tablero.

   Dos formas de pintar. Con la llave de Google, el fondo va como una capa
   encima del mapa de verdad --se acerca, se ven las carreteras--. Sin
   llave, un dibujo propio con los mismos contornos: la pantalla sirve
   igual, solo no se acerca.

   Los contornos son del Marco Geoestadistico del INEGI, simplificados una
   vez con preparar_mapas.py y guardados en /consola/geo/. */
import { t } from "./idioma.js";

const PARADAS = [[20, [76, 172, 11]], [50, [245, 170, 18]], [80, [185, 11, 11]]];
const SIN_DATO = "#d9dce6";
const NS = "http://www.w3.org/2000/svg";
const geos = {};

export const RANGOS = ["bajo", "medio_bajo", "medio", "medio_alto", "alto"];

export function colorDe(v) {
  if (v === null || v === undefined) return SIN_DATO;
  let c = PARADAS[0][1];
  if (v >= PARADAS[PARADAS.length - 1][0]) c = PARADAS[PARADAS.length - 1][1];
  else if (v > PARADAS[0][0]) {
    for (let i = 0; i < PARADAS.length - 1; i++) {
      const [a, ca] = PARADAS[i];
      const [b, cb] = PARADAS[i + 1];
      if (v >= a && v <= b) {
        const k = (v - a) / (b - a);
        c = ca.map((x, j) => Math.round(x + (cb[j] - x) * k));
        break;
      }
    }
  }
  return `#${c.map((x) => x.toString(16).padStart(2, "0")).join("")}`;
}

/* Blanco o casi negro, el que se lea encima de ese color. */
export function textoSobre(v) {
  const c = colorDe(v);
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#1a1d21" : "#ffffff";
}

export function rangoDe(v, cortes) {
  const i = cortes.findIndex((c) => v < c);
  return RANGOS[i === -1 ? RANGOS.length - 1 : i];
}

export function nombreRango(clave) {
  return t(`rsg_f_rango_${clave}`);
}

/* La pastilla del rango, del color del numero. */
export function chip(v, cortes, clase = "fondo-chip") {
  const nodo = document.createElement("span");
  nodo.className = clase;
  nodo.textContent = nombreRango(rangoDe(v, cortes));
  nodo.style.background = colorDe(v);
  nodo.style.color = textoSobre(v);
  return nodo;
}

/* Los cinco rangos con sus numeros: 0-19 Bajo, 20-41 Medio bajo... */
export function leyenda(cortes, conNumeros = true) {
  const caja = document.createElement("div");
  caja.className = "fondo-leyenda";
  const bordes = [0, ...cortes, 101];
  RANGOS.forEach((clave, i) => {
    const de = bordes[i];
    const a = bordes[i + 1] - 1;
    const punto = document.createElement("i");
    punto.style.background = colorDe((de + Math.min(a, 100)) / 2);
    const linea = document.createElement("span");
    linea.append(punto, conNumeros ? `${de}–${Math.min(a, 100)} ` : "", nombreRango(clave));
    caja.append(linea);
  });
  return caja;
}

/* Los contornos, una vez por sesion: estados.json o mun_09.json. */
export async function contornos(nombre) {
  if (!geos[nombre]) {
    geos[nombre] = fetch(`/consola/geo/${nombre}.json`).then((r) => {
      if (!r.ok) throw new Error(`geo ${nombre}`);
      return r.json();
    }).catch((e) => { delete geos[nombre]; throw e; });
  }
  return geos[nombre];
}

function anillos(geometria) {
  if (geometria.type === "Polygon") return geometria.coordinates;
  if (geometria.type === "MultiPolygon") return geometria.coordinates.flat();
  return [];
}

function s(etiqueta, atributos = {}) {
  const nodo = document.createElementNS(NS, etiqueta);
  for (const [k, v] of Object.entries(atributos)) nodo.setAttribute(k, v);
  return nodo;
}

/* El dibujo propio. `valorDe(feature)` da {valor, nombre} o null;
   `marcado` es la clave del lugar elegido; `eventos` son los vigentes
   ({lat, lon, color}); `alElegir(clave)` al picar un lugar. */
export function dibujo(features, valorDe, opciones = {}) {
  const { marcado = null, eventos = [], alElegir = null, ancho = 760 } = opciones;
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const f of features) {
    for (const anillo of anillos(f.geometry)) {
      for (const [x, y] of anillo) {
        if (x < x0) x0 = x; if (x > x1) x1 = x;
        if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
    }
  }
  const k = Math.cos(((y0 + y1) / 2) * Math.PI / 180);
  const margen = 10;
  const alto = Math.max(280, Math.min(560,
    ((y1 - y0) / ((x1 - x0) * k)) * (ancho - 2 * margen) + 2 * margen));
  const escala = Math.min((ancho - 2 * margen) / ((x1 - x0) * k),
                          (alto - 2 * margen) / (y1 - y0));
  const dx = (ancho - (x1 - x0) * k * escala) / 2;
  const dy = (alto - (y1 - y0) * escala) / 2;
  const P = (x, y) => [dx + (x - x0) * k * escala, dy + (y1 - y) * escala];

  const svg = s("svg", { viewBox: `0 0 ${ancho} ${Math.round(alto)}`,
                         class: "fondo-dibujo", role: "img" });
  let encima = null;
  for (const f of features) {
    const clave = f.properties.c;
    const dato = valorDe(f);
    const d = anillos(f.geometry).map((anillo) => "M" + anillo.map(([x, y]) => {
      const [a, b] = P(x, y);
      return `${a.toFixed(1)},${b.toFixed(1)}`;
    }).join("L") + "Z").join("");
    const camino = s("path", {
      d, fill: colorDe(dato ? dato.valor : null), "fill-rule": "evenodd",
      class: String(clave) === String(marcado) ? "fondo-lugar fondo-marcado" : "fondo-lugar",
    });
    const titulo = s("title");
    titulo.textContent = dato ? `${dato.nombre} · ${dato.valor}` : "";
    camino.append(titulo);
    if (alElegir) camino.addEventListener("click", () => alElegir(clave));
    if (String(clave) === String(marcado)) encima = camino;
    else svg.append(camino);
  }
  // El elegido al final, para que su borde no quede tapado.
  if (encima) svg.append(encima);
  for (const e of eventos) {
    if (e.lat === null || e.lat === undefined) continue;
    if (e.lon < x0 || e.lon > x1 || e.lat < y0 || e.lat > y1) continue;
    const [cx, cy] = P(e.lon, e.lat);
    svg.append(s("circle", { cx, cy, r: 8, class: "fondo-evento" }),
               s("circle", { cx, cy, r: 4, fill: e.color }));
  }
  return svg;
}

/* La capa encima de Google. Devuelve con que quitarla. */
export function capaGoogle(mapa, features, valorDe, opciones = {}) {
  const { marcado = null, alElegir = null, ajustar = true } = opciones;
  const capa = new google.maps.Data({ map: mapa });
  capa.addGeoJson({ type: "FeatureCollection", features });
  capa.setStyle((f) => {
    const clave = f.getProperty("c");
    const dato = valorDe({ properties: { c: clave } });
    const elegido = String(clave) === String(marcado);
    return { fillColor: colorDe(dato ? dato.valor : null), fillOpacity: 0.6,
             strokeColor: elegido ? "#1B1546" : "#ffffff",
             strokeWeight: elegido ? 3 : 0.8, zIndex: elegido ? 2 : 1 };
  });
  if (alElegir) capa.addListener("click", (ev) => alElegir(ev.feature.getProperty("c")));
  if (ajustar) {
    const limites = new google.maps.LatLngBounds();
    capa.forEach((f) => f.getGeometry().forEachLatLng((p) => limites.extend(p)));
    if (!limites.isEmpty()) mapa.fitBounds(limites, 8);
  }
  return () => capa.setMap(null);
}

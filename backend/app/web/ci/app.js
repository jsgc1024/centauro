/* La app del cliente de la Central de Inteligencia (seccion 136).

   Misma cara que la app de campo --su hoja de estilo, su encabezado, su
   barra de abajo (Salvador, 2 oct: "el diseño debe estar igual al que
   usamos en Connect")-- y otra casa: su propia sesion, que no abre nada
   de Centauro, y solo lo que le toca al cliente.

   Cuatro cosas, en el orden de los bocetos aprobados el 2 de octubre:
   entrar (y poner la contrasena con el enlace del correo), el mapa de
   sus estados, sus avisos con el «Enterado», y lo suyo. */

import { firma } from "/consola/firma.js";
import { idioma, nombreIdioma, ponerIdioma as fijarIdioma, t as traducir }
  from "/consola/idioma.js";
import { capaGoogle, colorDe, contornos, dibujo, leyenda as leyendaFondo, nombreRango,
         rangoDe, textoSobre } from "/consola/mapa_fondo.js";

const LLAVE = "centauro_ci_token";
const COLOR = { 1: "#5f7187", 2: "#c99a06", 3: "#e07000", 4: "#c62828" };
const raiz = document.getElementById("app");

let yo = null;
let logo = null;
let refresco = null;

/* ------------------------------------------------------------ utilidades */

function guardado(llave) {
  try { return localStorage.getItem(llave); } catch { return null; }
}
function guardar(llave, valor) {
  try { valor ? localStorage.setItem(llave, valor) : localStorage.removeItem(llave); }
  catch { /* sin almacenamiento: la sesion dura lo que la pestana */ }
}

/* Los textos viven en idioma.js con los de toda la casa, con la marca
   ci_ (la regla de revisar.py: un solo diccionario, tres idiomas). Aqui
   solo se rellenan los {huecos}. */
function t(clave, huecos = {}) {
  let texto = traducir(clave);
  for (const [k, v] of Object.entries(huecos)) texto = texto.split(`{${k}}`).join(v);
  return texto;
}

function ponerIdioma(nuevo) {
  if (!["es", "pt", "en"].includes(nuevo)) return;
  fijarIdioma(nuevo);
  document.documentElement.lang = nuevo;
}

function h(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [k, v] of Object.entries(atributos || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "clase") nodo.className = v;
    else if (k.startsWith("on")) nodo.addEventListener(k.slice(2), v);
    else nodo.setAttribute(k, v);
  }
  for (const hijo of hijos.flat(Infinity)) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return nodo;
}

class ErrorApi extends Error {
  constructor(codigo, detalle) {
    const d = detalle || {};
    super(typeof d === "string" ? d : (d.mensaje || d.detail || `Error ${codigo}`));
    this.codigo = codigo;
    this.detalle = d;
  }
}

async function api(metodo, ruta, cuerpo) {
  const cabeceras = { "Content-Type": "application/json" };
  const token = guardado(LLAVE);
  if (token) cabeceras.Authorization = `Bearer ${token}`;
  let r;
  try {
    r = await fetch(`/ci-api${ruta}`, {
      method: metodo, headers: cabeceras,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    });
  } catch {
    throw new ErrorApi(0, t("ci_sin_red"));
  }
  if (r.status === 204) return null;
  const datos = await r.json().catch(() => null);
  if (r.status === 401 && token) {
    /* La sesion vencio o la cerraron: a entrar de nuevo. */
    guardar(LLAVE, null);
    yo = null;
    location.hash = "#/entrar";
  }
  if (!r.ok) throw new ErrorApi(r.status, datos && (datos.detail ?? datos));
  return datos;
}

function aviso(texto, tipo = "grave") {
  return h("div", { clase: `aviso ${tipo}` }, texto);
}

function nivel(n) {
  return h("span", { clase: "nivel", style: `background:${COLOR[n]}` },
           `${n} · ${t(`ci_nivel_${n}`)}`);
}

/* Las horas llegan con la zona del pais del evento ("...T23:00:00-06:00"):
   se dicen a la hora de ese lugar, que es la que importa para un bloqueo
   en Reynosa, y "hoy" o "manana" se cuentan en ese mismo reloj. */
function relojDe(iso) {
  const m = /([+-])(\d\d):(\d\d)$/.exec(iso || "");
  const minutos = m ? (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3])) : 0;
  const hoy = new Date(Date.now() + minutos * 60000).toISOString().slice(0, 10);
  return { dia: iso.slice(0, 10), hora: iso.slice(11, 16), hoy };
}

const MESES = {
  es: ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
  pt: ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"],
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
};

function cuando(iso) {
  if (!iso) return "—";
  const { dia, hora, hoy } = relojDe(iso);
  const desfase = Math.round((Date.parse(dia) - Date.parse(hoy)) / 86400000);
  if (desfase === 0) return `${t("ci_hoy")} ${hora}`;
  if (desfase === 1) return `${t("ci_manana")} ${hora}`;
  if (desfase === -1) return `${t("ci_ayer")} ${hora}`;
  const mes = (MESES[idioma()] || MESES.es)[Number(dia.slice(5, 7)) - 1];
  return `${Number(dia.slice(8, 10))} ${mes} ${hora}`;
}

function hace(iso) {
  const minutos = Math.round((Date.now() - Date.parse(iso)) / 60000);
  if (minutos < 1) return t("ci_ahora_mismo");
  if (minutos < 60) return t("ci_hace_min", { n: minutos });
  if (minutos < 24 * 60) return t("ci_hace_h", { n: Math.round(minutos / 60) });
  return cuando(iso);
}

function dondeDe(e) {
  return e.municipio ? [e.municipio, e.region].join(", ") : e.region;
}

function lugarDe(e) {
  return t("ci_lugar_evento", { tipo: e.tipo, donde: dondeDe(e) });
}

function vigencia(e) {
  return e.vigente ? t("ci_afecta_hasta", { cuando: cuando(e.vigente_hasta) })
                   : t("ci_ya_termino", { cuando: cuando(e.vigente_hasta) });
}

async function cargarLogo() {
  if (logo) return;
  try {
    const r = await fetch("/sistema/logo").then((x) => x.json());
    logo = r && r.logo ? r.logo : null;
  } catch { logo = null; }
}

function imagenLogo(clase) {
  return h("img", { clase, src: logo || "/app/icono-192.png", alt: "Centauro" });
}

function encabezado() {
  return h("div", { clase: "encabezado" }, imagenLogo("logo ancho"),
           h("span", { clase: "marca sello-ci" }, "AI/CI"));
}

function barra(activa) {
  const pendientes = yo ? yo.por_confirmar : 0;
  const pestana = (ruta, icono, texto, extra) =>
    h("a", { href: `#/${ruta}`, clase: activa === ruta ? "activo" : "" },
      h("span", { clase: "icono" }, icono), texto, extra || null);
  return h("div", { clase: "barra" },
    pestana("mapa", "◎", t("ci_nav_mapa")),
    pestana("avisos", "▲", t("ci_nav_avisos"),
            pendientes ? h("span", { clase: "contador" }, pendientes) : null),
    pestana("yo", "☺", t("ci_nav_yo")));
}

function portada() {
  return h("div", { clase: "portada" }, imagenLogo("logo-entrada"),
    h("div", { clase: "app-nombre" }, t("ci_app_nombre")),
    h("div", { clase: "app-sello" }, firma(t("ci_sello"), t("ci_lema"))));
}

function pintar(...nodos) {
  raiz.replaceChildren(...nodos.flat(Infinity).filter(Boolean));
  window.scrollTo(0, 0);
}

function boton(texto, accion, clase = null) {
  const b = h("button", { clase });
  b.textContent = texto;
  b.addEventListener("click", async () => {
    b.disabled = true;
    try { await accion(b); } finally { b.disabled = false; }
  });
  return b;
}

function campo(etiqueta, entrada) {
  return h("div", { clase: "campo" }, h("label", {}, etiqueta), entrada);
}

/* ------------------------------------------------------------ entrar */

function pantallaEntrar() {
  const correo = h("input", { type: "email", inputmode: "email",
                              autocapitalize: "none", autocomplete: "username" });
  const clave = h("input", { type: "password", autocomplete: "current-password" });
  const salida = h("div");
  const entrar = boton(t("ci_entrar"), async () => {
    salida.replaceChildren();
    try {
      const r = await api("POST", "/entrar",
                          { correo: correo.value, contrasena: clave.value });
      guardar(LLAVE, r.token);
      if (r.idioma) ponerIdioma(r.idioma);
      location.hash = "#/mapa";
    } catch (e) {
      salida.replaceChildren(aviso(e.codigo === 401 ? t("ci_mal_entrada") : e.message));
    }
  });
  clave.addEventListener("keydown", (ev) => { if (ev.key === "Enter") entrar.click(); });
  pintar(h("div", { clase: "entrada" },
    h("div", { clase: "caja" }, portada(), salida,
      campo(t("ci_correo"), correo), campo(t("ci_contrasena"), clave), entrar,
      h("button", { clase: "claro", style: "margin-top:10px",
                    onclick: () => { location.hash = "#/recuperar"; } }, t("ci_olvide"))),
    h("p", { clase: "pie-entrada" }, t("ci_pie_entrada"))));
}

function pantallaRecuperar() {
  const correo = h("input", { type: "email", inputmode: "email",
                              autocapitalize: "none", autocomplete: "username" });
  const salida = h("div");
  pintar(h("div", { clase: "entrada" },
    h("div", { clase: "caja" }, portada(),
      h("h2", { style: "margin-top:0" }, t("ci_rec_titulo")),
      h("p", { clase: "gris chico" }, t("ci_rec_texto")),
      salida, campo(t("ci_correo"), correo),
      boton(t("ci_rec_mandar"), async () => {
        try {
          await api("POST", "/recuperar", { correo: correo.value });
          salida.replaceChildren(aviso(t("ci_rec_listo"), "ok"));
        } catch (e) { salida.replaceChildren(aviso(e.message)); }
      }),
      h("button", { clase: "claro", style: "margin-top:10px",
                    onclick: () => { location.hash = "#/entrar"; } }, t("ci_volver"))),
    h("p", { clase: "pie-entrada" }, t("ci_pie_entrada"))));
}

async function pantallaEnlace(token) {
  pintar(h("div", { clase: "entrada" }, h("div", { clase: "caja" }, portada(),
    h("p", { clase: "gris chico" }, t("ci_cargando")))));
  let estado;
  try { estado = await api("POST", "/enlace", { token }); }
  catch (e) { estado = { estado: "error", mensaje: e.message }; }
  if (estado.idioma) ponerIdioma(estado.idioma);

  if (estado.estado !== "vivo") {
    pintar(h("div", { clase: "entrada" },
      h("div", { clase: "caja" }, portada(),
        h("h2", { style: "margin-top:0" }, t("ci_enlace_muerto")),
        h("p", { clase: "gris chico" },
          estado.mensaje || t(`ci_enlace_${estado.estado}`)),
        h("button", { onclick: () => { location.hash = "#/entrar"; } },
          t("ci_ir_a_entrar")))));
    return;
  }

  const invitacion = estado.tipo === "invitacion";
  const nueva = h("input", { type: "password", autocomplete: "new-password" });
  const otra = h("input", { type: "password", autocomplete: "new-password" });
  const salida = h("div");
  const negritas = (texto, valores) => {
    /* El nombre del cliente y el correo, en negritas, como en el boceto. */
    const partes = [];
    let resto = texto;
    for (const [clave, valor] of Object.entries(valores)) {
      const [antes, despues] = resto.split(`{${clave}}`);
      if (despues === undefined) continue;
      partes.push(antes, h("b", {}, valor));
      resto = despues;
    }
    partes.push(resto);
    return partes;
  };
  pintar(h("div", { clase: "entrada" },
    h("div", { clase: "caja" }, portada(),
      h("h2", { style: "margin-top:0" },
        invitacion ? t("ci_bienvenido", { nombre: estado.nombre }) : t("ci_nueva_titulo")),
      h("p", { clase: "gris chico" },
        invitacion
          ? negritas(t("ci_bienvenida_texto"), { cliente: estado.cliente, correo: estado.correo })
          : negritas(t("ci_nueva_texto"), { correo: estado.correo })),
      salida,
      campo(t("ci_contrasena_nueva"), nueva), campo(t("ci_otra_vez"), otra),
      h("p", { clase: "gris chico" }, t("ci_regla")),
      boton(t("ci_guardar_entrar"), async () => {
        salida.replaceChildren();
        if (nueva.value !== otra.value) {
          salida.replaceChildren(aviso(t("ci_no_coinciden")));
          return;
        }
        try {
          const r = await api("POST", "/enlace/usar",
                              { token, contrasena: nueva.value });
          guardar(LLAVE, r.token);
          /* El token no se queda en la barra ni en el historial. */
          history.replaceState(null, "", "/ci/#/mapa");
          yo = null;     // si habia otra sesion en esta pestana, ya no es
          arrancar();
        } catch (e) { salida.replaceChildren(aviso(e.message)); }
      })),
    h("p", { clase: "pie-entrada" },
      invitacion ? t("ci_enlace_pie") : t("ci_enlace_pie_rec"))));
}

/* ------------------------------------------------------------ el mapa */

let googleListo = null;

function cargarGoogle(llave) {
  if (window.google && window.google.maps) return Promise.resolve();
  if (googleListo) return googleListo;
  googleListo = new Promise((resolver, rechazar) => {
    window.__ciMapaListo = () => resolver();
    const s = document.createElement("script");
    s.src = "https://maps.googleapis.com/maps/api/js?key="
      + encodeURIComponent(llave) + "&v=weekly&language=" + idioma()
      + "&callback=__ciMapaListo";
    s.async = true;
    s.referrerPolicy = "strict-origin-when-cross-origin";
    s.onerror = () => { googleListo = null; rechazar(new Error("maps")); };
    document.head.append(s);
  });
  return googleListo;
}

/* El mapa de Google con un circulo por evento, del color de su nivel, y
   el punto de quien mira si el telefono ya dio permiso de ubicacion. Sin
   llave no se pinta nada: el cliente no tiene por que leer un aviso de
   configuracion; la lista de abajo dice lo mismo. */
function lienzoMapa(eventos, llave, alto = 300) {
  if (!llave) return null;
  const lienzo = h("div", { clase: "mapa", style: `height:${alto}px` });
  cargarGoogle(llave).then(() => {
    const mapa = new google.maps.Map(lienzo, {
      center: { lat: 23.6, lng: -102.5 }, zoom: 5,
      disableDefaultUI: true, zoomControl: true, gestureHandling: "greedy",
    });
    const limites = new google.maps.LatLngBounds();
    let puntos = 0;
    for (const e of eventos) {
      if (e.lat === null || e.lat === undefined) continue;
      const centro = { lat: e.lat, lng: e.lon };
      const c = new google.maps.Circle({
        map: mapa, center: centro, radius: e.radio_m || 1000,
        strokeColor: COLOR[e.nivel], strokeWeight: 2, strokeOpacity: 0.9,
        fillColor: COLOR[e.nivel], fillOpacity: 0.22,
      });
      c.addListener("click", () => { location.hash = `#/evento/${e.id}`; });
      limites.union(c.getBounds());
      puntos += 1;
    }
    if (puntos === 1) { mapa.fitBounds(limites); }
    else if (puntos > 1) mapa.fitBounds(limites, 24);
    if (navigator.permissions && navigator.geolocation) {
      navigator.permissions.query({ name: "geolocation" }).then((p) => {
        if (p.state === "denied") return;
        navigator.geolocation.getCurrentPosition((pos) => {
          new google.maps.Marker({
            map: mapa,
            position: { lat: pos.coords.latitude, lng: pos.coords.longitude },
            icon: { path: google.maps.SymbolPath.CIRCLE, scale: 7,
                    fillColor: "#1B1546", fillOpacity: 1,
                    strokeColor: "#fff", strokeWeight: 3 },
          });
        }, () => {}, { maximumAge: 300000, timeout: 8000 });
      }).catch(() => {});
    }
  }).catch(() => { lienzo.remove(); });
  return lienzo;
}

function leyenda() {
  return h("div", { clase: "leyenda" }, ...[1, 2, 3, 4].map((n) =>
    h("span", {}, h("i", { style: `background:${COLOR[n]}` }), `${n} ${t(`ci_nivel_${n}`)}`)));
}

function tarjetaEvento(e, desde, pie = null) {
  return h("a", { clase: "caja evento", href: `#/evento/${e.id}` },
    nivel(e.nivel), " ", h("span", { clase: "chico gris" }, `· ${hace(desde || e.ocurrio_en)}`),
    h("h3", {}, e.titulo),
    h("div", { clase: "chico gris" }, lugarDe(e)),
    h("div", { clase: "chico", style: "margin-top:6px" }, vigencia(e)),
    pie);
}

function listaDeZonas(zonas) {
  if (zonas.length <= 1) return zonas.join("");
  const y = { es: " y ", pt: " e ", en: " and " }[idioma()] || " y ";
  return `${zonas.slice(0, -1).join(", ")}${y}${zonas[zonas.length - 1]}`;
}

/* Dos vistas del mismo mapa (seccion 138): lo que pasa hoy y el riesgo
   de fondo del mes. Se queda la que eligio la ultima vez. */
const LLAVE_VISTA = "centauro_ci_vista";

function selectorDeVista(actual) {
  const opcion = (cual, texto) => h("button", {
    clase: actual === cual ? null : "claro",
    onclick: () => { guardar(LLAVE_VISTA, cual); route(); } }, texto);
  return h("div", { clase: "seg" },
    opcion("eventos", t("ci_f_eventos")), opcion("fondo", t("ci_f_fondo")));
}

async function pantallaMapa(mia = vuelta) {
  const vista = guardado(LLAVE_VISTA) === "fondo" ? "fondo" : "eventos";
  const datos = await api("GET", "/mapa");
  const fondo = vista === "fondo" ? await api("GET", "/fondo") : null;
  if (mia !== vuelta) return;
  const eventos = datos.eventos;
  pintar(encabezado(),
    h("h1", {}, t("ci_hola", { nombre: yo.nombre.split(" ")[0] })),
    h("p", { clase: "gris chico", style: "margin:2px 0 10px" },
      yo.zonas.length ? t("ci_lo_que_pasa", { zonas: listaDeZonas(yo.zonas) })
                      : t("ci_sin_zonas")),
    selectorDeVista(vista),
    vista === "fondo" ? vistaFondo(fondo, eventos, datos.llave_mapa) : [
      lienzoMapa(eventos, datos.llave_mapa),
      datos.llave_mapa ? leyenda() : null,
      h("h2", {}, t("ci_vigente_ahora", { n: eventos.length })),
      eventos.length ? eventos.map((e) => tarjetaEvento(e))
                     : h("div", { clase: "vacio" }, t("ci_nada_vigente"))],
    cajaPanico(),
    barra("mapa"));
}

/* ------------------------------------------------- el riesgo de fondo */

function mesDe(iso, menos = 0) {
  const [a, m] = iso.split("-").map(Number);
  const total = a * 12 + (m - 1) - menos;
  return { mes: t("rsg_f_meses").split(",")[total % 12], anio: Math.floor(total / 12) };
}

/* «66 · Medio alto», del color del numero. */
function chipFondo(v, cortes) {
  return h("span", { clase: "nivel",
                     style: `background:${colorDe(v)};color:${textoSobre(v)}` },
    `${v} · ${nombreRango(rangoDe(v, cortes))}`);
}

const FLECHA = { 1: ["sube", "▲"], "-1": ["baja", "▼"], 0: ["igual", "="] };

function flecha(diferencia) {
  if (diferencia === null || diferencia === undefined) return null;
  const [clase, signo] = FLECHA[Math.sign(diferencia)];
  return h("span", { clase: `flecha ${clase}` }, `${signo} ${Math.abs(diferencia)}`);
}

function vistaFondo(fondo, eventos, llave) {
  if (!fondo || !fondo.mes) return h("div", { clase: "vacio" }, t("ci_f_sin_mes"));
  const mes = fondo.mes;
  const porClave = new Map(fondo.estados.map((l) => [String(l.clave_region), l]));
  const valorDe = (f) => {
    const l = porClave.get(String(f.properties.c));
    return l ? { valor: l.valor, nombre: l.region } : null;
  };
  const alElegir = (clave) => {
    const l = porClave.get(String(clave));
    if (l && l.mio) location.hash = `#/fondo/${l.region_id}`;
  };
  const puntos = eventos.map((e) => ({ lat: e.lat, lon: e.lon, color: COLOR[e.nivel] }));
  const lienzo = h("div", { clase: "mapa fondo" });
  contornos("estados").then((geo) => {
    if (llave) {
      return cargarGoogle(llave).then(() => {
        const mapa = new google.maps.Map(lienzo, {
          center: { lat: 23.6, lng: -102.5 }, zoom: 4,
          disableDefaultUI: true, zoomControl: true, gestureHandling: "greedy" });
        for (const p of puntos) {
          if (p.lat === null || p.lat === undefined) continue;
          new google.maps.Marker({ map: mapa, position: { lat: p.lat, lng: p.lon }, clickable: false,
            icon: { path: google.maps.SymbolPath.CIRCLE, scale: 6, fillColor: p.color,
                    fillOpacity: 1, strokeColor: "#fff", strokeWeight: 2 } });
        }
        capaGoogle(mapa, geo.features, valorDe, { alElegir });
      });
    }
    lienzo.classList.add("dibujo");
    lienzo.replaceChildren(dibujo(geo.features, valorDe, { eventos: puntos, alElegir }));
    return null;
  }).catch(() => { lienzo.remove(); });

  const mios = fondo.estados.filter((l) => l.mio);
  return [
    lienzo,
    leyendaFondo(mes.cortes, false),
    h("h2", {}, t("ci_f_tus_estados", { mes: mesDe(mes.periodo).mes })),
    mios.length
      ? mios.map((l) => h("a", { clase: "caja evento fila estado-fondo", href: `#/fondo/${l.region_id}` },
          h("b", { clase: "nombre" }, l.region), chipFondo(l.valor, mes.cortes), flecha(l.vs_ano)))
      : h("div", { clase: "vacio" }, t("ci_sin_zonas")),
    h("p", { clase: "chico gris" }, t("ci_f_que_es")),
  ];
}

async function pantallaFondoEstado(regionId, mia = vuelta) {
  let d;
  try { d = await api("GET", `/fondo/estados/${regionId}`); }
  catch (err) {
    if (mia !== vuelta) return;
    pintar(encabezado(), h("a", { clase: "atras", href: "#/mapa" }, t("ci_f_atras")),
           h("div", { clase: "vacio" }, err.codigo === 404 ? t("ci_no_encontrado") : err.message),
           barra("mapa"));
    return;
  }
  if (mia !== vuelta) return;
  const { mes, estado: e } = d;
  const este = mesDe(mes.periodo);
  const haceUnAno = mesDe(mes.periodo, 12);
  const antes = mesDe(mes.periodo, 1);
  const contra = [
    e.vs_ano === null ? null : [flecha(e.vs_ano), " ",
      t("ci_f_contra_ano", { mes: haceUnAno.mes, anio: haceUnAno.anio })],
    e.vs_mes === null ? null : [flecha(e.vs_mes), " ", t("ci_f_contra_mes", { mes: antes.mes })],
  ].filter(Boolean);
  const faltan = new Set(mes.faltan);
  const componentes = ["violencia_letal", "delitos_violencia", "delincuencia_organizada",
                       "miedo", "no_denuncia", "cifra_negra"].map((c) => {
    const p = e.componentes[c];
    const sinDato = p === null || p === undefined || faltan.has(c);
    return h("div", { clase: "componente" },
      h("div", { clase: "fila separa chico" }, h("span", {}, t(`ci_f_comp_${c}`)),
        sinDato ? h("span", { clase: "gris" }, t("rsg_f_sin_dato_min")) : h("b", {}, String(Math.round(p)))),
      h("div", { clase: "riel" }, sinDato ? null
        : h("div", { clase: "lleno", style: `width:${Math.max(1, Math.round(p))}%` })));
  });
  const verEventos = h("a", { href: "#/mapa", onclick: () => guardar(LLAVE_VISTA, "eventos") },
                       t("ci_f_verlo"));
  pintar(encabezado(),
    h("a", { clase: "atras", href: "#/mapa" }, t("ci_f_atras")),
    h("div", { clase: "caja principal" },
      h("div", { clase: "chico gris" }, t("ci_f_nivel_de", { mes: este.mes, anio: este.anio })),
      h("h1", { clase: "titulo-estado" }, e.region),
      h("div", { clase: "fila" }, h("span", { clase: "grande" }, String(e.valor)), chipFondo(e.valor, mes.cortes)),
      contra.length ? h("div", { clase: "chico contra" },
        contra.flatMap((x, i) => (i ? [" · ", ...x] : x))) : null,
      h("h2", {}, t("ci_f_compone")), componentes,
      d.municipios.length ? [h("h2", {}, t("ci_f_mas_altos")),
        d.municipios.map((l) => h("div", { clase: "fila separa municipio-fondo" },
          h("span", {}, l.municipio), chipFondo(l.valor, mes.cortes)))] : null),
    h("p", { clase: "chico gris" },
      t("ci_f_vigentes", { edo: e.region, n: d.vigentes }), " ", d.vigentes ? verEventos : null),
    barra("mapa"));
}

/* ------------------------------------------------------------ los avisos */

async function enterado(alertaId) {
  await api("POST", `/avisos/${alertaId}/enterado`);
  yo = await api("GET", "/yo");
}

function avisoPorConfirmar(a) {
  const e = a.evento;
  const salida = h("div");
  return h("div", { clase: "caja pide" },
    nivel(e.nivel), " ", h("span", { clase: "chico gris" }, `· ${hace(a.creada_en)}`),
    h("a", { href: `#/evento/${e.id}`, clase: "evento" }, h("h3", {}, e.titulo)),
    h("div", { clase: "chico gris" }, lugarDe(e)),
    e.texto ? h("p", { clase: "chico", style: "margin:8px 0 12px" }, e.texto) : null,
    salida,
    boton(t("ci_enterado"), async () => {
      try { await enterado(a.id); route(); }
      catch (err) { salida.replaceChildren(aviso(err.message)); }
    }),
    a.nivel === 4 ? h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
                      t("ci_si_no_confirmas")) : null);
}

function avisoAnterior(a) {
  const pie = a.acuse_en
    ? h("div", { clase: "chico verde", style: "margin-top:6px" },
        t("ci_confirmado_en", { cuando: cuando(a.acuse_en) }))
    : a.en_resumen
      ? h("div", { clase: "chico verde", style: "margin-top:6px" }, t("ci_en_resumen"))
      : null;
  return tarjetaEvento(a.evento, a.creada_en, pie);
}

async function pantallaAvisos(mia = vuelta) {
  const datos = await api("GET", "/avisos");
  if (mia !== vuelta) return;
  const pendientes = datos.por_confirmar;
  pintar(encabezado(),
    h("h1", {}, t("ci_avisos")),
    h("p", { clase: "gris chico", style: "margin:2px 0 14px" }, t("ci_avisos_pie")),
    pendientes.length ? [
      h("h2", { style: "color:var(--grave)" }, t("ci_por_confirmar", { n: pendientes.length })),
      pendientes.map(avisoPorConfirmar)] : null,
    datos.anteriores.length ? [h("h2", {}, t("ci_anteriores")),
                               datos.anteriores.map(avisoAnterior)] : null,
    !pendientes.length && !datos.anteriores.length
      ? h("div", { clase: "vacio" }, t("ci_sin_avisos")) : null,
    cajaPanico(),
    barra("avisos"));
}

async function pantallaEvento(id, mia = vuelta) {
  let e;
  try { e = await api("GET", `/eventos/${id}`); }
  catch (err) {
    pintar(encabezado(), h("a", { clase: "atras", href: "#/avisos" }, t("ci_atras_avisos")),
           h("div", { clase: "vacio" }, err.codigo === 404 ? t("ci_no_encontrado") : err.message),
           barra("avisos"));
    return;
  }
  const llave = (await api("GET", "/mapa")).llave_mapa;
  if (mia !== vuelta) return;
  const salida = h("div");
  const dato = (clave, valor) => h("div", { clase: "dato" },
    h("div", { clase: "clave" }, clave), valor || "—");
  const verificado = e.verificacion !== "sin_confirmar";
  pintar(encabezado(),
    h("a", { clase: "atras", href: "#/avisos",
             onclick: (ev) => { if (history.length > 1) { ev.preventDefault(); history.back(); } } },
      t("ci_atras_avisos")),
    h("div", { clase: "caja principal" },
      nivel(e.nivel), " ",
      h("span", { clase: `marca ${verificado ? "ok" : ""}` }, t(`ci_verif_${e.verificacion}`)),
      h("h1", { style: "margin:10px 0 4px" }, e.titulo),
      h("div", { clase: "chico gris" }, `${e.folio} · ${lugarDe(e)}`),
      e.texto ? h("p", { style: "margin:12px 0" }, e.texto) : null,
      h("div", { clase: "rejilla" },
        dato(t("ci_cuando_paso"), cuando(e.ocurrio_en)),
        dato(t("ci_afecta"), e.vigente ? cuando(e.vigente_hasta)
                                    : t("ci_ya_termino", { cuando: cuando(e.vigente_hasta) })),
        dato(t("ci_donde"), e.lugar || dondeDe(e)),
        dato(t("ci_tendencia"), e.tendencia ? t(`ci_tend_${e.tendencia}`) : null)),
      salida,
      e.alerta_por_confirmar ? boton(t("ci_enterado"), async () => {
        try { await enterado(e.alerta_por_confirmar); route(); }
        catch (err) { salida.replaceChildren(aviso(err.message)); }
      }) : null),
    e.lat !== null && e.lat !== undefined ? lienzoMapa([e], llave, 220) : null,
    h("p", { clase: "chico gris" }, t("ci_verif_explica")),
    barra("avisos"));
}

/* ------------------------------------------------------------ yo */

function soportaAvisos() {
  return "serviceWorker" in navigator && "PushManager" in window
    && "Notification" in window;
}

function base64aBytes(base64) {
  const relleno = "=".repeat((4 - base64.length % 4) % 4);
  const limpio = (base64 + relleno).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from([...atob(limpio)].map((c) => c.charCodeAt(0)));
}

async function miSuscripcion() {
  if (!soportaAvisos()) return null;
  try {
    const reg = await navigator.serviceWorker.ready;
    return await reg.pushManager.getSubscription();
  } catch { return null; }
}

async function cajaAvisos() {
  const salida = h("div");
  const caja = h("div", { clase: "caja principal" },
    h("h2", { style: "margin-top:0" }, t("ci_avisos_telefono")),
    h("p", { clase: "chico gris" }, t("ci_avisos_telefono_pie")), salida);
  if (!soportaAvisos()) {
    caja.append(aviso(t("ci_sin_soporte"), "alerta"), h("p", { clase: "chico gris" }, t("ci_iphone")));
    return caja;
  }
  const sus = await miSuscripcion();
  const consulta = sus ? "?endpoint=" + encodeURIComponent(sus.endpoint) : "";
  const estado = await api("GET", "/push" + consulta);
  if (!estado.activo) {
    caja.append(aviso(t("ci_sin_configurar"), "alerta"));
    return caja;
  }
  if (sus && estado.este_telefono && Notification.permission === "granted") {
    caja.append(h("div", {}, h("span", { clase: "marca ok" }, t("ci_activados"))),
      boton(t("ci_probar"), async () => {
        try {
          await api("POST", "/push/probar");
          salida.replaceChildren(aviso(t("ci_prueba_mandada"), "ok"));
        } catch (e) { salida.replaceChildren(aviso(e.message)); }
      }, "claro chico"));
    caja.lastChild.style.marginTop = "12px";
  } else {
    caja.append(boton(t("ci_activar"), async () => {
      const permiso = await Notification.requestPermission();
      if (permiso !== "granted") {
        salida.replaceChildren(aviso(t("ci_sin_permiso"), "alerta"));
        return;
      }
      try {
        const reg = await navigator.serviceWorker.ready;
        const nueva = await reg.pushManager.subscribe({
          userVisibleOnly: true, applicationServerKey: base64aBytes(estado.llave) });
        const j = nueva.toJSON();
        await api("POST", "/push", { endpoint: j.endpoint, p256dh: j.keys.p256dh,
                                     auth: j.keys.auth, agente: navigator.userAgent });
        route();
      } catch (e) { salida.replaceChildren(aviso(e.message)); }
    }));
  }
  caja.append(h("p", { clase: "chico gris", style: "margin-top:12px" }, t("ci_iphone")));
  return caja;
}

async function pantallaYo(mia = vuelta) {
  yo = await api("GET", "/yo");
  if (mia !== vuelta) return;
  const lengua = h("select", {},
    ...["es", "pt", "en"].map((v) => {
      const o = h("option", { value: v }, nombreIdioma(v));
      if (v === yo.idioma) o.selected = true;
      return o;
    }));
  lengua.addEventListener("change", async () => {
    yo = await api("PATCH", "/yo", { idioma: lengua.value });
    ponerIdioma(yo.idioma);
    route();
  });
  pintar(encabezado(),
    h("h1", {}, `${yo.nombre} ${yo.apellidos}`.trim()),
    h("p", { clase: "gris chico", style: "margin:2px 0 14px" },
      `${t(`ci_perfil_${yo.perfil}`)} · ${yo.cliente}`),
    await cajaAvisos(),
    h("div", { clase: "caja" },
      h("h2", { style: "margin-top:0" }, t("ci_lo_que_sigues")),
      h("p", { clase: "chico" }, yo.zonas.length ? yo.zonas.join(" · ") : "—"),
      h("p", { clase: "chico gris" }, t("ci_pedir_cambio"))),
    h("div", { clase: "caja" },
      campo(t("ci_idioma"), lengua),
      h("button", { clase: "claro", onclick: () => { location.hash = "#/contrasena"; } },
        t("ci_cambiar_contrasena")),
      h("button", { clase: "claro", style: "margin-top:10px", onclick: salir }, t("ci_salir"))),
    barra("yo"));
}

async function salir() {
  const sus = await miSuscripcion();
  if (sus) {
    /* Quien sale ya no recibe los avisos de esta cuenta en este telefono. */
    try { await api("DELETE", `/push?endpoint=${encodeURIComponent(sus.endpoint)}`); } catch { /* */ }
  }
  guardar(LLAVE, null);
  yo = null;
  location.hash = "#/entrar";
}

function pantallaContrasena() {
  const actual = h("input", { type: "password", autocomplete: "current-password" });
  const nueva = h("input", { type: "password", autocomplete: "new-password" });
  const otra = h("input", { type: "password", autocomplete: "new-password" });
  const salida = h("div");
  pintar(encabezado(),
    h("a", { clase: "atras", href: "#/yo" }, `‹ ${t("ci_nav_yo")}`),
    h("div", { clase: "caja principal" },
      h("h2", { style: "margin-top:0" }, t("ci_cambiar_contrasena")), salida,
      campo(t("ci_contrasena_actual"), actual), campo(t("ci_contrasena_nueva"), nueva),
      campo(t("ci_otra_vez"), otra), h("p", { clase: "gris chico" }, t("ci_regla")),
      boton(t("ci_guardar"), async () => {
        if (nueva.value !== otra.value) {
          salida.replaceChildren(aviso(t("ci_no_coinciden")));
          return;
        }
        try {
          const r = await api("POST", "/contrasena",
                              { actual: actual.value, nueva: nueva.value });
          guardar(LLAVE, r.token);
          salida.replaceChildren(aviso(t("ci_contrasena_lista"), "ok"));
          actual.value = nueva.value = otra.value = "";
        } catch (e) { salida.replaceChildren(aviso(e.message)); }
      })),
    barra("yo"));
}

/* ------------------------------------------------- el panico (seccion 145)

   Se mantiene presionado tres segundos: en la bolsa o con la mano
   temblando, un toque no basta para levantarlo por error, y tres
   segundos si se pueden sostener. No pide confirmar. La alerta sale con
   la ubicacion si llega pronto y, si no, sin ella; despues el telefono
   la sigue mandando cada quince segundos mientras siga abierta.
   Si no hay red, se llama a Respuesta a emergencias. */

const SOSTENER_MS = 3000;
let seguimiento = null;

function telefonoEmergencias() {
  return (yo && (yo.telefono_emergencias || yo.telefono_central)) || "";
}

function leerUbicacion(tiempo = 8000) {
  return new Promise((resolver) => {
    if (!navigator.geolocation) return resolver(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolver({ lat: p.coords.latitude, lon: p.coords.longitude,
                        precision: p.coords.accuracy }),
      () => resolver(null),
      { enableHighAccuracy: true, timeout: tiempo, maximumAge: 10000 });
  });
}

/* Mientras la alerta siga abierta, donde va. Se detiene sola cuando la
   cierran (o cuando la app deja de estar abierta: el navegador no deja
   que una pagina mande la ubicacion con el telefono bloqueado). */
function seguirUbicacion(cada = 15) {
  if (seguimiento) return;
  const mandar = async () => {
    const donde = await leerUbicacion(10000);
    if (!donde) return;
    try {
      const r = await api("POST", "/emergencia/ubicacion", donde);
      if (!r.abierta) { clearInterval(seguimiento); seguimiento = null; }
    } catch (e) {
      /* Sin sesion se detiene; sin red, la siguiente vuelta lo intenta. */
      if (e.codigo === 401) { clearInterval(seguimiento); seguimiento = null; }
    }
  };
  seguimiento = setInterval(mandar, cada * 1000);
}

function cajaPanico() {
  const tel = telefonoEmergencias();
  const avance = h("span", { clase: "avance-panico" });
  const b = h("button", { clase: "panico panico-sostener", type: "button" },
              t("ci_em_sostener"), avance);
  let reloj = null;
  const soltar = () => {
    clearTimeout(reloj);
    reloj = null;
    b.classList.remove("sosteniendo");
  };
  const empezar = (ev) => {
    ev.preventDefault();
    if (reloj) return;
    b.classList.add("sosteniendo");
    reloj = setTimeout(async () => {
      reloj = null;
      b.classList.remove("sosteniendo");
      if (navigator.vibrate) navigator.vibrate(250);
      await levantar();
    }, SOSTENER_MS);
  };
  b.addEventListener("pointerdown", empezar);
  for (const fin of ["pointerup", "pointerleave", "pointercancel"]) {
    b.addEventListener(fin, soltar);
  }
  b.addEventListener("contextmenu", (ev) => ev.preventDefault());
  return h("div", { clase: "caja urgente" }, b,
    h("div", { clase: "chico gris", style: "margin-top:8px;text-align:center" },
      t("ci_em_sostener_pie")),
    tel ? h("a", { href: `tel:${tel.replace(/\s/g, "")}`, style: "text-decoration:none" },
            h("button", { clase: "claro", style: "margin-top:10px" },
              t("ci_em_llamar", { tel }))) : null);
}

/* La ubicacion se pide al terminar de presionar, no al empezar: la
   primera vez el telefono pregunta si la permite, y esa pregunta, a
   media presion, cancelaba el toque (iOS). Si en dos segundos no llega,
   la alerta sale sin ella y la ubicacion la sigue en cuanto la haya. */
async function levantar() {
  const pedida = leerUbicacion(15000);
  const donde = await Promise.race([
    pedida, new Promise((r) => setTimeout(() => r(null), 2000))]);
  try {
    const r = await api("POST", "/emergencia", donde || {});
    seguirUbicacion(r.cada_segundos);
    if (!donde) {
      pedida.then((tarde) => tarde && api("POST", "/emergencia/ubicacion", tarde).catch(() => {}));
    }
    if (location.hash === "#/emergencia") route();
    else location.hash = "#/emergencia";
  } catch (e) {
    const tel = telefonoEmergencias();
    alert(t("ci_em_fallo", { error: e.message, tel }));
    if (tel) location.href = `tel:${tel.replace(/\s/g, "")}`;
  }
}

/* Lo que esta pintado de la alerta: cada diez segundos se cambian sus
   textos y se mueve el punto, sin rehacer la pantalla ni pedirle a
   Google un mapa nuevo. */
let emPintada = null;

function mapaDeMiAlerta(a) {
  if (!a.llave_mapa || a.lat === null || a.lat === undefined) return null;
  const lienzo = h("div", { clase: "mapa", style: "height:220px" });
  cargarGoogle(a.llave_mapa).then(() => {
    const punto = { lat: a.lat, lng: a.lon };
    const mapa = new google.maps.Map(lienzo, {
      center: punto, zoom: 15, disableDefaultUI: true, zoomControl: true,
      gestureHandling: "greedy" });
    if (emPintada) emPintada.marca = new google.maps.Marker({
      map: mapa, position: punto,
      icon: { path: google.maps.SymbolPath.CIRCLE, scale: 8,
              fillColor: COLOR[4], fillOpacity: 1,
              strokeColor: "#fff", strokeWeight: 3 } });
  }).catch(() => { lienzo.remove(); });
  return lienzo;
}

function textoAtiende(a) {
  if (a.atiende) return t("ci_em_atiende", { quien: a.atiende });
  return a.atendida ? t("ci_em_atendida") : t("ci_em_por_atender");
}

function textoUltima(a) {
  return a.ubicacion_en
    ? t("ci_em_ultima", { hace: hace(a.ubicacion_en),
                          precision: a.precision_m === null ? "—" : a.precision_m })
    : t("ci_em_sin_ubicacion");
}

async function actualizarEmergencia(mia) {
  const a = await api("GET", "/emergencia");
  if (mia !== vuelta) return;
  const p = emPintada;
  if (!p || !a.abierta || a.id !== p.id || a.dijo_error !== p.dijo_error
      || (p.sinMapa && a.lat !== null)) {
    await pantallaEmergencia(mia, a);
    return;
  }
  p.atiende.textContent = textoAtiende(a);
  p.ultima.textContent = textoUltima(a);
  if (p.marca && a.lat !== null) p.marca.setPosition({ lat: a.lat, lng: a.lon });
}

async function pantallaEmergencia(mia = vuelta, datos = null) {
  const a = datos || await api("GET", "/emergencia");
  if (mia !== vuelta) return;
  const tel = a.telefono || telefonoEmergencias();
  const llamar = tel
    ? h("a", { href: `tel:${tel.replace(/\s/g, "")}`, style: "text-decoration:none" },
        h("button", {}, t("ci_em_llamar_respuesta")))
    : null;
  if (!a.abierta) {
    emPintada = null;
    clearInterval(seguimiento);
    seguimiento = null;
    pintar(encabezado(),
      h("div", { clase: "caja" }, h("h2", { style: "margin-top:0" }, t("ci_em_cerrada")),
        h("p", { clase: "gris" }, t("ci_em_cerrada_pie"))),
      cajaPanico(), barra("mapa"));
    return;
  }
  seguirUbicacion(a.cada_segundos);
  const error = a.dijo_error
    ? h("div", { clase: "chico gris", style: "margin:8px 0 18px;text-align:center" },
        t("ci_em_error_dicho"))
    : [boton(t("ci_em_fue_error"), async () => {
        if (!confirm(t("ci_em_fue_error_confirmar"))) return;
        await api("POST", "/emergencia/error");
        route();
      }, "claro"),
       h("div", { clase: "chico gris", style: "margin:8px 0 18px;text-align:center" },
         t("ci_em_fue_error_pie"))];
  const atiende = h("div", { style: "margin-top:2px;font-weight:700" }, textoAtiende(a));
  const ultima = h("div", { clase: "chico gris", style: "margin-top:4px" }, textoUltima(a));
  emPintada = { id: a.id, dijo_error: a.dijo_error, atiende, ultima, marca: null,
                sinMapa: a.lat === null };
  pintar(encabezado(),
    h("div", { clase: "caja alerta-enviada" },
      h("div", { clase: "alerta-enviada-titulo" }, t("ci_em_enviada")),
      h("div", { style: "margin-top:6px" }, t("ci_em_recibida", { hora: horaCorta(a.recibida_en) })),
      atiende),
    mapaDeMiAlerta(a),
    h("div", { clase: "caja" },
      h("div", { clase: "dato" }, h("span", { clase: "clave" }, t("ci_em_tu_ubicacion"))),
      h("div", { style: "margin-top:4px" }, t("ci_em_se_comparte", { s: a.cada_segundos })),
      ultima),
    llamar, error, barra("mapa"));
}

function horaCorta(iso) {
  const f = new Date(iso);
  return `${String(f.getHours()).padStart(2, "0")}:${String(f.getMinutes()).padStart(2, "0")}`;
}

/* ------------------------------------------------------------ las rutas */

/* Cada vuelta de route() lleva su numero: si mientras esperaba al
   servidor ya empezo otra (se pico otra pestana), esta no pinta ni deja
   su reloj andando. */
let vuelta = 0;
let alArrancar = true;

async function route() {
  clearInterval(refresco);
  const mia = ++vuelta;
  const ruta = location.hash.replace(/^#\/?/, "");
  const [pantalla, arg] = ruta.split("/");
  document.documentElement.lang = idioma();

  if (pantalla === "enlace" && arg) return pantallaEnlace(arg);
  if (pantalla === "recuperar") return pantallaRecuperar();
  if (!guardado(LLAVE) || pantalla === "entrar") {
    if (guardado(LLAVE) && pantalla === "entrar") { location.hash = "#/mapa"; return; }
    return pantallaEntrar();
  }
  try {
    if (!yo) {
      yo = await api("GET", "/yo");
      ponerIdioma(yo.idioma);
    }
    if (mia !== vuelta) return;
    /* Con una alerta abierta, la app abre en ella: quien la levanto no
       tiene que buscarla (seccion 145). Solo al abrir la app: despues
       puede ir a su mapa sin que lo regrese. */
    if (alArrancar) {
      alArrancar = false;
      const abierta = await api("GET", "/emergencia").catch(() => null);
      if (mia !== vuelta) return;
      if (abierta && abierta.abierta && pantalla !== "emergencia") {
        location.hash = "#/emergencia";
        return;
      }
    }
    if (pantalla === "emergencia") {
      await pantallaEmergencia(mia);
      if (mia !== vuelta) return;
      /* Mientras siga abierta, quien la atiende y la ultima ubicacion se
         ven sin recargar. */
      clearInterval(refresco);
      refresco = setInterval(() => {
        if (document.visibilityState === "visible") actualizarEmergencia(mia).catch(() => {});
      }, 10000);
      return;
    }
    if (pantalla === "avisos") await pantallaAvisos(mia);
    else if (pantalla === "evento" && arg) await pantallaEvento(Number(arg), mia);
    else if (pantalla === "fondo" && arg) await pantallaFondoEstado(Number(arg), mia);
    else if (pantalla === "yo") await pantallaYo(mia);
    else if (pantalla === "contrasena") pantallaContrasena();
    else await pantallaMapa(mia);
    if (mia !== vuelta) return;
    /* Lo que la Central publica se ve sin recargar: cada minuto, en las
       dos pantallas que lo ensenan. */
    if (["", "mapa", "avisos"].includes(pantalla || "")) {
      const fuente = pantalla === "avisos" ? "/avisos" : "/mapa";
      const pintado = await huella(fuente);
      if (mia !== vuelta) return;
      clearInterval(refresco);
      refresco = setInterval(async () => {
        if (document.visibilityState !== "visible") return;
        let ahora;
        try { ahora = await huella(fuente); } catch { return; }
        /* Solo se vuelve a pintar si algo cambio: repintar cada minuto
           movia el mapa y subia la pantalla de quien estaba leyendo. */
        if (ahora === pintado) return;
        const y = window.scrollY;
        yo = await api("GET", "/yo").catch(() => yo);
        await route();
        window.scrollTo(0, y);
      }, 60000);
    }
  } catch (e) {
    if (e.codigo === 401) return;
    pintar(encabezado(), aviso(e.message), barra(pantalla || "mapa"));
  }
}

async function huella(fuente) {
  const [datos, mio] = await Promise.all([api("GET", fuente), api("GET", "/yo")]);
  return JSON.stringify([datos, mio.por_confirmar]);
}

async function arrancar() {
  await cargarLogo();
  route();
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/ci/sw.js").catch(() => {});
}
window.addEventListener("hashchange", route);
arrancar();

/* LG Connect, la app de los operadores de Logistica (seccion 151).

   Decision de Salvador, 3 de octubre: los operadores no usan la app de
   Proteccion Ejecutiva. Tienen la suya, en su propia direccion
   (applg.mycentauro.lat), con su propia sesion: un operador no ve nada de
   EP ni un agente de EP ve nada de Logistica. La cara es la de Connect
   --la hoja de estilo de la app de campo, su encabezado y su barra de
   abajo-- y por debajo usa las mismas piezas: la contrasena con su limite
   de intentos, la huella o la cara, la geocerca.

   Entra con su correo personal y su contrasena; la primera vez, o si la
   olvida, con los cuatro digitos que le dicta su gerente por telefono.
   En este bloque solo marca su inicio de jornada dentro del patio; los
   viajes, los hitos, las evidencias, los gastos y el panico llegan en el
   bloque 6. */

import { firma } from "/consola/firma.js";
import { IDIOMAS, idioma, ponerIdioma as fijarIdioma, t as traducir } from "/consola/idioma.js";

const LLAVE = "centauro_lg_token";
const RECUERDO = "centauro_lg_huella";
const NO_AHORA = "centauro_lg_huella_no_ahora";
const raiz = document.getElementById("app");

let logo = null;
let yo = null;
/* La ultima ubicacion del telefono: {lat, lon, precision} o {error}. */
let ubicacion = null;

/* ------------------------------------------------------------ utilidades */

function guardado(llave) {
  try { return localStorage.getItem(llave); } catch { return null; }
}
function guardar(llave, valor) {
  try { valor ? localStorage.setItem(llave, valor) : localStorage.removeItem(llave); }
  catch { /* sin almacenamiento: la sesion dura lo que la pestana */ }
}
function leerJson(llave) {
  try { return JSON.parse(guardado(llave) || "null"); } catch { return null; }
}

/* Los textos viven en idioma.js con los de toda la casa, con la marca
   lga_ (un solo diccionario, tres idiomas). Aqui solo se rellenan los
   {huecos}. */
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
    super(typeof d === "string" ? d
      : d.que_hacer ? `${d.mensaje || ""} ${d.que_hacer}`.trim()
        : (d.mensaje || d.detail || `Error ${codigo}`));
    this.codigo = codigo;
    this.detalle = d;
  }
}

async function api(metodo, ruta, cuerpo, conSesion = true) {
  const cabeceras = { "Content-Type": "application/json" };
  const token = conSesion ? guardado(LLAVE) : null;
  if (token) cabeceras.Authorization = `Bearer ${token}`;
  let r;
  try {
    r = await fetch(`/lgapp-api${ruta}`, {
      method: metodo, headers: cabeceras,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    });
  } catch {
    throw new ErrorApi(0, t("lga_sin_red"));
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

async function cargarLogo() {
  if (logo) return;
  logo = guardado("centauro_lg_logo");
  try {
    const r = await fetch("/sistema/logo").then((x) => x.json());
    if (r && r.logo) {
      logo = r.logo;
      guardar("centauro_lg_logo", r.logo);
    }
  } catch { /* sin senal se queda con el guardado, o con el icono */ }
}

function imagenLogo(clase) {
  return h("img", { clase, src: logo || "/app/icono-192.png", alt: "Centauro" });
}

function encabezado() {
  return h("div", { clase: "encabezado" }, imagenLogo("logo ancho"),
           h("span", { clase: "marca sello-lg" }, "AI/LG"));
}

function barra(activa) {
  const pestana = (ruta, icono, texto) =>
    h("a", { href: `#/${ruta}`, clase: activa === ruta ? "activo" : "" },
      h("span", { clase: "icono" }, icono), texto);
  return h("div", { clase: "barra" },
    pestana("hoy", "◉", t("lga_nav_hoy")),
    pestana("yo", "☺", t("lga_nav_yo")));
}

function portada() {
  return h("div", { clase: "portada" }, imagenLogo("logo-entrada"),
    h("div", { clase: "app-nombre" }, t("lga_app_nombre")),
    h("div", { clase: "app-sello" }, firma(t("app_sello"), t("lema"))));
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

function puerta(...hijos) {
  return h("div", { clase: "entrada" },
    h("div", { clase: "caja" }, portada(), ...hijos),
    h("p", { clase: "pie-entrada" }, t("lga_pie_entrada")),
    h("p", { clase: "lga-url" }, location.host));
}

/* ------------------------------------------------------------ la huella

   Lo mismo que hace la app de EP (`/consola/huella.js`), contra la API de
   LG Connect: aquella habla con la sesion de la consola y esta no. La
   huella nunca sale del telefono: el telefono firma un reto del servidor
   despues de pedir la huella, la cara o su PIN. */

function hayWebAuthn() {
  return !!(window.isSecureContext && window.PublicKeyCredential && navigator.credentials);
}

async function hayLector() {
  if (!hayWebAuthn()) return false;
  try { return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable(); }
  catch { return false; }
}

function recordado() {
  const r = leerJson(RECUERDO);
  return r && r.correo ? r : null;
}
function recordar(correo, nombre, credencial) {
  guardar(RECUERDO, JSON.stringify({ correo, nombre, credencial }));
}
function olvidar() { guardar(RECUERDO, null); }

function primerNombre(nombre) {
  return (nombre || "").trim().split(/\s+/)[0] || "";
}

function aBytes(texto) {
  const b = atob(texto.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((texto.length + 3) % 4));
  return Uint8Array.from(b, c => c.charCodeAt(0));
}
function aTexto(buffer) {
  let s = "";
  for (const b of new Uint8Array(buffer)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function opcionesDe(json) {
  const o = JSON.parse(json);
  o.challenge = aBytes(o.challenge);
  if (o.user) o.user.id = aBytes(o.user.id);
  for (const lista of [o.excludeCredentials, o.allowCredentials]) {
    for (const c of lista || []) c.id = aBytes(c.id);
  }
  return o;
}
function credencialJSON(c) {
  const r = c.response;
  const respuesta = { clientDataJSON: aTexto(r.clientDataJSON) };
  if (r.attestationObject) {
    respuesta.attestationObject = aTexto(r.attestationObject);
    if (r.getTransports) respuesta.transports = r.getTransports();
  } else {
    respuesta.authenticatorData = aTexto(r.authenticatorData);
    respuesta.signature = aTexto(r.signature);
    respuesta.userHandle = r.userHandle ? aTexto(r.userHandle) : null;
  }
  return { id: c.id, rawId: aTexto(c.rawId), type: c.type, response: respuesta };
}
function motivoDe(err) {
  if (err && err.name === "NotAllowedError") return new Error(t("hue_cancelada"));
  if (err && err.name === "InvalidStateError") return new Error(t("hue_ya_activada"));
  if (err && err.name === "NotSupportedError") return new Error(t("hue_no_hay"));
  return err;
}

function nombreDelEquipo() {
  const ua = navigator.userAgent || "";
  const nav = /SamsungBrowser/.test(ua) ? "Samsung Internet" : /Chrome\//.test(ua) ? "Chrome"
    : /Safari\//.test(ua) ? "Safari" : /Firefox\//.test(ua) ? "Firefox" : "";
  const so = /Android/.test(ua) ? "Android" : /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : "";
  return [nav, so].filter(Boolean).join(" · ") || t("hue_este");
}

async function entrarConHuella(correo = null) {
  const aqui = recordado();
  const suya = !correo && aqui && aqui.credencial ? aqui.credencial : null;
  const r = await api("POST", "/llaves/entrada/opciones",
                      { correo: suya ? null : (correo || (aqui || {}).correo || null) }, false);
  const opciones = opcionesDe(r.opciones);
  if (suya) opciones.allowCredentials = [{ type: "public-key", id: aBytes(suya) }];
  let c;
  try { c = await navigator.credentials.get({ publicKey: opciones }); }
  catch (err) { throw motivoDe(err); }
  let d;
  try {
    d = await api("POST", "/llaves/entrada", { credencial: credencialJSON(c), estado: r.estado }, false);
  } catch (err) {
    /* La de este telefono ya no existe alla: se olvida aqui y se entra
       con la contrasena, que la vuelve a ofrecer. */
    if (err.detalle && err.detalle.codigo === "huella_desconocida") olvidar();
    throw err;
  }
  guardar(LLAVE, d.access_token);
  recordar(d.correo, d.nombre, c.id);
  if (d.idioma) ponerIdioma(d.idioma);
  return d;
}

async function activarHuella(contrasena, correo, nombre) {
  const r = await api("POST", "/llaves/alta/opciones", { contrasena });
  let c;
  try { c = await navigator.credentials.create({ publicKey: opcionesDe(r.opciones) }); }
  catch (err) { throw motivoDe(err); }
  const hecha = await api("POST", "/llaves/alta", {
    credencial: credencialJSON(c), estado: r.estado, nombre: nombreDelEquipo() });
  recordar(correo, nombre, hecha.credencial_id);
  return hecha;
}

/* Se ofrece una vez, al entrar con la contrasena en un telefono con
   lector; quien dijo «ahora no» no vuelve a ver la pregunta en un mes. */
async function convieneOfrecer(correo) {
  if (!(await hayLector())) return false;
  const r = recordado();
  if (r && r.correo === correo) return false;
  const dijo = (leerJson(NO_AHORA) || {})[correo];
  return !(dijo && Date.now() - dijo < 30 * 86400000);
}

function pantallaOfrecer(correo, nombre, contrasena) {
  const salida = h("div");
  pintar(puerta(
    h("h2", { clase: "lga-centro", style: "margin:6px 0 8px" }, t("hue_ofrecer_titulo")),
    h("p", { clase: "gris chico lga-centro", style: "line-height:1.5;margin:0 0 14px" }, t("hue_ofrecer_texto")),
    salida,
    boton(t("hue_ofrecer_si"), async () => {
      salida.replaceChildren();
      try {
        await activarHuella(contrasena, correo, nombre);
        location.hash = "#/hoy";
        route();
      } catch (e) { salida.replaceChildren(aviso(e.message)); }
    }),
    h("button", { clase: "claro", style: "margin-top:10px", onclick: () => {
      const todos = leerJson(NO_AHORA) || {};
      todos[correo] = Date.now();
      guardar(NO_AHORA, JSON.stringify(todos));
      location.hash = "#/hoy";
      route();
    } }, t("hue_ofrecer_no")),
    h("p", { clase: "chico gris lga-centro", style: "margin:14px 0 0" }, t("hue_ofrecer_pie"))));
}

async function despuesDeEntrar(correo, nombre, contrasena) {
  if (await convieneOfrecer(correo)) return pantallaOfrecer(correo, nombre, contrasena);
  location.hash = "#/hoy";
  route();
}

/* ------------------------------------------------------------ entrar */

async function pantallaEntrar(conContrasena = false) {
  const lector = await hayLector();
  const conocido = recordado();
  const salida = h("div");

  if (lector && conocido && !conContrasena) {
    pintar(puerta(
      h("p", { clase: "lga-centro", style: "margin:18px 0;font-size:17px" },
        t("hue_hola", { nombre: "" }), h("b", {}, primerNombre(conocido.nombre))),
      salida,
      boton(t("hue_boton"), async () => {
        salida.replaceChildren();
        try { await entrarConHuella(); location.hash = "#/hoy"; route(); }
        catch (e) { salida.replaceChildren(aviso(e.message)); }
      }),
      h("button", { clase: "claro", style: "margin-top:10px",
                    onclick: () => pantallaEntrar(true) }, t("hue_usar_contrasena")),
      h("p", { clase: "gris chico lga-centro", style: "margin:14px 0 0" },
        h("a", { href: "#", onclick: (e) => { e.preventDefault(); olvidar(); pantallaEntrar(true); } },
          t("hue_no_soy", { nombre: primerNombre(conocido.nombre) })))));
    return;
  }

  const correo = h("input", { type: "email", inputmode: "email", autocapitalize: "none",
                              autocomplete: "username" });
  const clave = h("input", { type: "password", autocomplete: "current-password" });
  const entrar = boton(t("lga_entrar"), async () => {
    salida.replaceChildren();
    try {
      const r = await api("POST", "/entrar", { correo: correo.value, contrasena: clave.value }, false);
      guardar(LLAVE, r.access_token);
      if (r.idioma) ponerIdioma(r.idioma);
      await despuesDeEntrar(r.correo, r.nombre, clave.value);
    } catch (e) {
      salida.replaceChildren(aviso(e.codigo === 401 ? t("lga_mal_entrada") : e.message));
    }
  });
  clave.addEventListener("keydown", (ev) => { if (ev.key === "Enter") entrar.click(); });
  pintar(puerta(salida,
    campo(t("lga_correo"), correo), campo(t("lga_contrasena"), clave), entrar,
    lector ? boton(t("hue_boton"), async () => {
      salida.replaceChildren();
      try { await entrarConHuella(correo.value.trim() || null); location.hash = "#/hoy"; route(); }
      catch (e) { salida.replaceChildren(aviso(e.message)); }
    }, "claro") : null,
    h("button", { clase: "claro", style: "margin-top:10px",
                  onclick: () => { location.hash = "#/codigo"; } }, t("lga_primera_vez"))));
  /* Los dos botones claros, separados como en la app de campo. */
  for (const b of raiz.querySelectorAll("button.claro")) b.style.marginTop = "10px";
}

/* El operador llamo a Karla --o a quien lleva la flota-- y le dictaron
   cuatro digitos por telefono. Aqui los escribe y pone su contrasena. */
function pantallaCodigo() {
  const correo = h("input", { type: "email", inputmode: "email", autocapitalize: "none",
                              autocomplete: "username" });
  const codigo = h("input", { type: "text", inputmode: "numeric", maxlength: "4",
                              autocomplete: "one-time-code", placeholder: "0000" });
  const clave = h("input", { type: "password", autocomplete: "new-password" });
  const salida = h("div");
  pintar(puerta(
    h("p", { clase: "gris" }, t("lga_pide_codigo")),
    salida,
    campo(t("lga_correo"), correo), campo(t("lga_codigo"), codigo),
    campo(t("lga_contrasena_nueva"), clave),
    boton(t("lga_guardar_entrar"), async () => {
      salida.replaceChildren();
      try {
        const r = await api("POST", "/codigo", { correo: correo.value, codigo: codigo.value.trim(),
                                                 nueva: clave.value }, false);
        guardar(LLAVE, r.access_token);
        if (r.idioma) ponerIdioma(r.idioma);
        await despuesDeEntrar(r.correo, r.nombre, clave.value);
      } catch (e) { salida.replaceChildren(aviso(e.message)); }
    }),
    h("button", { clase: "claro", style: "margin-top:10px",
                  onclick: () => { location.hash = "#/entrar"; } }, t("lga_regresar"))));
}

/* ------------------------------------------------------------ donde esta */

function metros(a, b) {
  const rad = (x) => x * Math.PI / 180;
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const s = Math.sin(dLat / 2) ** 2
    + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  /* Entero hacia abajo, como el servidor: el telefono y la consola dicen
     los mismos metros. */
  return Math.floor(6371000 * 2 * Math.asin(Math.sqrt(s)));
}

function distanciaTexto(m) {
  return m < 1000 ? t("lga_m", { n: m }) : t("lga_km", { n: (m / 1000).toFixed(1) });
}

/* El patio mas cercano y que tan lejos esta, para decirlo antes de
   marcar. Quien decide si la marca vale es el servidor. */
function cercano(patios, punto) {
  let mejor = null;
  for (const p of patios || []) {
    const d = metros(punto, p);
    if (!mejor || d < mejor.metros) mejor = { patio: p, metros: d };
  }
  return mejor;
}

function buscarUbicacion() {
  return new Promise((listo) => {
    if (!navigator.geolocation) { listo({ error: "sin_gps" }); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => listo({ lat: p.coords.latitude, lon: p.coords.longitude,
                     precision: Math.round(p.coords.accuracy || 0) }),
      (e) => listo({ error: e.code === 1 ? "sin_permiso" : "sin_senal" }),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 20000 });
  });
}

function bandaGeo(lugar) {
  if (!ubicacion) {
    return h("div", { clase: "lga-geo" }, h("span", { clase: "lga-punto" }), t("lga_buscando"));
  }
  if (ubicacion.error) {
    return h("div", { clase: "lga-geo fuera" }, h("span", { clase: "lga-punto" }),
      t(ubicacion.error === "sin_permiso" ? "lga_sin_permiso" : "lga_sin_ubicacion"));
  }
  if (!lugar) {
    return h("div", { clase: "lga-geo" }, h("span", { clase: "lga-punto" }), t("lga_sin_patio"));
  }
  if (lugar.metros <= lugar.patio.radio) {
    return h("div", { clase: "lga-geo dentro" }, h("span", { clase: "lga-punto" }),
      t("lga_en_patio", { p: lugar.patio.nombre, d: distanciaTexto(lugar.metros) }));
  }
  return h("div", { clase: "lga-geo fuera" }, h("span", { clase: "lga-punto" }),
    t("lga_lejos", { d: distanciaTexto(lugar.metros), p: lugar.patio.nombre }));
}

/* ------------------------------------------------------------ mi dia */

const SIGNO = { marca: ["si", "✓"], viaje: ["viaje", "✓"], por_validar: ["espera", "?"],
                rechazada: ["no", "✗"], falta: ["no", "✗"], pendiente: ["", "·"], libre: ["", "—"] };

function semana(dias, hoy) {
  const iniciales = t("f_dias").split(",");
  return h("div", { clase: "lga-semana" }, dias.slice(0, 5).map((d) => {
    const [clase, signo] = SIGNO[d.codigo] || ["", "·"];
    const inicial = iniciales[new Date(d.fecha + "T00:00:00").getDay()].charAt(0);
    return h("div", { clase: [clase, d.fecha === hoy ? "hoy" : ""].filter(Boolean).join(" ") },
      inicial, h("b", {}, signo));
  }));
}

function fechaDeHoy(iso) {
  const f = new Date(iso + "T00:00:00");
  return f.toLocaleDateString(idioma() === "en" ? "en-US" : idioma() === "pt" ? "pt-BR" : "es-MX",
                              { weekday: "long", day: "numeric", month: "long" });
}

function horaDe(iso) {
  const f = new Date(iso);
  return `${String(f.getHours()).padStart(2, "0")}:${String(f.getMinutes()).padStart(2, "0")}`;
}

async function marcar(nota = null) {
  ubicacion = await buscarUbicacion();
  if (ubicacion.error) { pantallaHoy(); return; }
  try {
    yo = await api("POST", "/jornada", { lat: ubicacion.lat, lon: ubicacion.lon,
                                         precision: ubicacion.precision, nota });
    pantallaHoy();
  } catch (e) {
    if (e.detalle && e.detalle.codigo === "fuera_del_patio") {
      pantallaHoy(e.message);
      return;
    }
    pantallaHoy(null, e.message);
  }
}

function tarjetaJornada(lugar, fueraDice, error) {
  const s = yo.semana;
  const cuenta = t("lga_de_cinco", { n: s.activos });
  const m = yo.marca;
  if (m && m.estado === "valida") {
    return h("div", { clase: "caja lga-jornada hecha" },
      h("div", { clase: "clave gris chico" }, t("lga_jornada")),
      h("div", { clase: "lga-palomota" }, "✓"),
      h("div", { clase: "lga-kv" }, h("span", {}, t("lga_inicio")),
        h("span", { style: "color:#1e7a4d" }, `${horaDe(m.marcada_en)} ✓`),
        h("span", {}, t("lga_activos")), h("span", {}, cuenta)),
      semana(s.dias, yo.hoy),
      h("p", { clase: "chico lga-centro", style: "margin:10px 0 0" },
        t("lga_ya_libre"), " ", s.bono === "si" ? t("lga_bono_completo") : ""));
  }
  if (m && m.estado === "por_validar") {
    return h("div", { clase: "caja lga-jornada espera" },
      h("div", { clase: "clave gris chico" }, t("lga_jornada")),
      h("div", { clase: "lga-kv" }, h("span", {}, t("lga_inicio")),
        h("span", { style: "color:#b8860b" }, horaDe(m.marcada_en)),
        h("span", {}, t("lga_activos")), h("span", {}, cuenta)),
      h("p", { clase: "chico", style: "margin:10px 0 0" }, t("lga_espera_central")),
      semana(s.dias, yo.hoy));
  }
  if (m && m.estado === "rechazada") {
    return h("div", { clase: "caja lga-jornada no" },
      h("div", { clase: "clave gris chico" }, t("lga_jornada")),
      h("p", { clase: "chico", style: "margin:8px 0" }, t("lga_rechazada")),
      m.justificacion ? h("p", { clase: "chico gris", style: "margin:0" }, `«${m.justificacion}»`) : null,
      semana(s.dias, yo.hoy));
  }
  if (yo.en_viaje) {
    return h("div", { clase: "caja lga-jornada hecha" },
      h("div", { clase: "clave gris chico" }, t("lga_jornada")),
      h("p", { clase: "chico", style: "margin:8px 0 0" }, t("lga_en_viaje")),
      h("div", { clase: "lga-kv" }, h("span", {}, t("lga_activos")), h("span", {}, cuenta)),
      semana(s.dias, yo.hoy));
  }

  const afuera = fueraDice || (lugar && lugar.metros > lugar.patio.radio && !ubicacion.error);
  if (afuera) {
    const donde = h("input", { type: "text", maxlength: "200" });
    return h("div", { clase: "caja lga-jornada espera" },
      h("div", { clase: "clave gris chico" }, t("lga_jornada")),
      h("div", { clase: "marco" },
        error ? aviso(error) : null,
        h("div", { clase: "chico", style: "line-height:1.45" },
          fueraDice || t("lga_fuera_explica", { r: lugar ? lugar.patio.radio : 300 })),
        campo(t("lga_donde_estas"), donde),
        boton(t("lga_marcar_validar"), async () => {
          if (donde.value.trim().length < 3) { donde.focus(); return; }
          await marcar(donde.value.trim());
        }),
        h("button", { clase: "claro", style: "margin-top:10px", onclick: async () => {
          ubicacion = null; pantallaHoy(); ubicacion = await buscarUbicacion(); pantallaHoy();
        } }, t("lga_volver_a_buscar")),
        h("div", { clase: "chico gris lga-centro", style: "margin-top:8px" }, t("lga_mientras_central"))));
  }
  return h("div", { clase: "caja lga-jornada" },
    h("div", { clase: "clave gris chico" }, t("lga_jornada")),
    h("div", { clase: "lga-kv" }, h("span", {}, t("lga_inicio")), h("span", {}, t("lga_todavia_no")),
      h("span", {}, t("lga_activos")), h("span", {}, cuenta)),
    h("div", { clase: "marco" },
      error ? aviso(error) : null,
      boton(t("lga_marcar"), () => marcar()),
      h("div", { clase: "chico gris lga-centro", style: "margin-top:8px" }, t("lga_cuenta_para")),
      semana(s.dias, yo.hoy)));
}

/* Ya marcada, lo que importa es donde se marco, como lo guardo el
   servidor: al volver a abrir la app ya no se busca la ubicacion. */
function bandaMarca(m) {
  if (!m.patio) return h("div", { clase: "lga-geo" }, h("span", { clase: "lga-punto" }), t("lga_sin_patio"));
  if (m.dentro) {
    return h("div", { clase: "lga-geo dentro" }, h("span", { clase: "lga-punto" }),
      t("lga_marcaste_en", { p: m.patio, d: distanciaTexto(m.distancia_m) }));
  }
  return h("div", { clase: "lga-geo fuera" }, h("span", { clase: "lga-punto" }),
    t("lga_marcaste_lejos", { d: distanciaTexto(m.distancia_m), p: m.patio }));
}

function pantallaHoy(fueraDice = null, error = null) {
  const lugar = ubicacion && !ubicacion.error ? cercano(yo.patios, ubicacion) : null;
  const patio = yo.marca ? yo.marca.patio : lugar ? lugar.patio.nombre : null;
  /* En viaje no se marca: no hay ubicacion que buscar. */
  const banda = yo.marca ? bandaMarca(yo.marca) : yo.en_viaje ? null : bandaGeo(lugar);
  pintar(encabezado(),
    h("h1", {}, t("lga_hola", { n: primerNombre(yo.nombre) })),
    h("p", { clase: "gris chico", style: "margin:2px 0 12px" },
      [fechaDeHoy(yo.hoy), patio].filter(Boolean).join(" · ")),
    banda,
    tarjetaJornada(lugar, fueraDice, error),
    barra("hoy"));
}

/* ------------------------------------------------------------ yo */

async function pantallaYo() {
  const llaves = await api("GET", "/llaves").catch(() => []);
  const lector = await hayLector();
  const salida = h("div");
  const idiomaSel = h("select", {},
    ...IDIOMAS.map(({ codigo, nombre }) => {
      const o = h("option", { value: codigo }, nombre);
      if (codigo === idioma()) o.selected = true;
      return o;
    }));
  idiomaSel.addEventListener("change", async () => {
    try { await api("POST", "/idioma", { idioma: idiomaSel.value }); } catch { /* se queda aqui */ }
    ponerIdioma(idiomaSel.value);
    pantallaYo();
  });

  const actual = h("input", { type: "password", autocomplete: "current-password" });
  const nueva = h("input", { type: "password", autocomplete: "new-password" });
  const paraHuella = h("input", { type: "password", autocomplete: "current-password" });

  pintar(encabezado(),
    h("h1", {}, yo.nombre),
    h("p", { clase: "gris chico", style: "margin:2px 0 12px" }, yo.correo || ""),
    salida,
    h("div", { clase: "caja" }, campo(t("lga_idioma"), idiomaSel)),
    h("div", { clase: "caja" },
      h("div", { clase: "clave gris chico" }, t("hue_titulo")),
      llaves.length ? llaves.map(k => h("div", { clase: "lga-kv" }, h("span", {}, k.nombre),
        h("span", {}, h("a", { href: "#", onclick: async (e) => {
          e.preventDefault();
          if (!confirm(t("hue_quitar_pregunta", { nombre: k.nombre }))) return;
          try {
            await api("DELETE", `/llaves/${k.id}`);
            const r = recordado();
            if (r && r.credencial === k.credencial_id) olvidar();
            pantallaYo();
          } catch (err) { salida.replaceChildren(aviso(err.message)); }
        } }, t("hue_quitar")))))
        : h("p", { clase: "chico gris" }, t("hue_ninguna")),
      lector ? h("div", { clase: "marco" },
        campo(t("hue_pide_contrasena"), paraHuella),
        boton(t("hue_activar_aqui"), async () => {
          salida.replaceChildren();
          try {
            await activarHuella(paraHuella.value, yo.correo, yo.nombre);
            salida.replaceChildren(aviso(t("hue_activada"), "ok"));
            pantallaYo();
          } catch (err) { salida.replaceChildren(aviso(err.message)); }
        }, "claro")) : null,
      h("p", { clase: "chico gris", style: "margin:10px 0 0" }, t("lga_huella_pie"))),
    h("div", { clase: "caja" },
      h("div", { clase: "clave gris chico" }, t("lga_cambiar_contrasena")),
      campo(t("lga_contrasena_actual"), actual), campo(t("lga_contrasena_nueva"), nueva),
      boton(t("lga_guardar"), async () => {
        salida.replaceChildren();
        try {
          const r = await api("POST", "/contrasena", { actual: actual.value, nueva: nueva.value });
          guardar(LLAVE, r.access_token);
          olvidar();
          salida.replaceChildren(aviso(t("lga_contrasena_lista"), "ok"));
          window.scrollTo(0, 0);
        } catch (err) { salida.replaceChildren(aviso(err.message)); window.scrollTo(0, 0); }
      }, "claro")),
    h("button", { clase: "claro", style: "margin-top:4px", onclick: () => {
      guardar(LLAVE, null); yo = null; location.hash = "#/entrar"; route();
    } }, t("lga_salir")),
    barra("yo"));
}

/* ------------------------------------------------------------ el reparto */

async function route() {
  const pantalla = location.hash.replace("#/", "");
  if (pantalla === "codigo") return pantallaCodigo();
  if (!guardado(LLAVE)) return pantallaEntrar();
  try {
    yo = await api("GET", "/yo");
    if (yo.idioma && yo.idioma !== idioma()) ponerIdioma(yo.idioma);
    if (pantalla === "yo") return pantallaYo();
    pantallaHoy();
    /* La ubicacion se busca al abrir: asi el operador sabe antes de
       picar si esta dentro del patio. */
    if (!yo.marca && !yo.en_viaje) {
      ubicacion = await buscarUbicacion();
      if (location.hash.replace("#/", "") !== "yo") pantallaHoy();
    }
  } catch (e) {
    if (e.codigo === 401) return pantallaEntrar();
    pintar(encabezado(), aviso(e.message), barra(pantalla || "hoy"));
  }
}

async function arrancar() {
  await cargarLogo();
  route();
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/lgapp/sw.js").catch(() => {});
}
window.addEventListener("hashchange", route);
arrancar();

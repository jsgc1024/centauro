/* Entrar con huella o cara (30 sep). Lo comparten la consola y la app de
   campo: la llave vale en las dos (mycentauro.lat y appep.mycentauro.lat).

   Aqui vive lo que habla con el telefono (WebAuthn) y con el servidor;
   los textos, en idioma.js con el prefijo hue_. Lo que se pinta lo
   decide cada app: la consola y la app de campo no se ven igual.

   La huella nunca sale del telefono. El telefono firma un reto del
   servidor despues de pedir la huella, la cara o el PIN del equipo, y el
   servidor comprueba la firma. */
import { ErrorApi, api, sesion } from "/consola/api.js";
import { idioma, t } from "/consola/idioma.js";

/* Los textos viven en idioma.js, con el prefijo hue_. */
export function th(clave, valores = {}) {
  let texto = t(`hue_${clave}`);
  for (const [k, v] of Object.entries(valores)) texto = texto.replace(`{${k}}`, v);
  return texto;
}

/* ------------------------------------------------ lo que se recuerda

   En el navegador, sin nada secreto: quien entro con huella la ultima
   vez --para saludarlo y ofrecerle el boton grande-- y a quien ya se le
   ofrecio y dijo "ahora no". La llave de verdad la guarda el telefono. */
const RECUERDO = "centauro_huella";
const NO_AHORA = "centauro_huella_no_ahora";
const DIAS_SIN_PREGUNTAR = 30;

function leer(llave) {
  try { return JSON.parse(localStorage.getItem(llave) || "null"); } catch { return null; }
}
function escribir(llave, valor) {
  try {
    if (valor === null) localStorage.removeItem(llave);
    else localStorage.setItem(llave, JSON.stringify(valor));
  } catch { /* sin almacenamiento: solo no se recuerda */ }
}

export function recordado() {
  const r = leer(RECUERDO);
  return r && r.correo ? r : null;
}
export function recordar(correo, nombre, credencial) {
  if (correo) escribir(RECUERDO, { correo, nombre: nombre || correo, credencial });
}
export function olvidar() { escribir(RECUERDO, null); }

function primerNombre(nombre) {
  return (nombre || "").trim().split(/\s+/)[0] || nombre || "";
}
export function saludo() {
  const r = recordado();
  return r ? th("hola", { nombre: primerNombre(r.nombre) }) : "";
}
export function noSoy() {
  const r = recordado();
  return r ? th("no_soy", { nombre: primerNombre(r.nombre) }) : "";
}

/* ------------------------------------------------ que puede este equipo */

export function disponible() {
  return !!(window.isSecureContext && window.PublicKeyCredential
            && navigator.credentials);
}

/* Si tiene lector: huella, cara o el PIN del equipo. Sin el, no se
   ofrece nada --un boton que abre la ventana de la llave USB confunde--. */
export async function hayLector() {
  if (!disponible()) return false;
  try {
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch { return false; }
}

/* Se ofrece al entrar con contrasena, una vez: si ya entra con huella en
   este equipo, o dijo "ahora no" hace menos de un mes, no se pregunta.
   Se llama ya con la sesion puesta. */
export async function convieneOfrecer(correo) {
  if (!(await hayLector())) return false;
  const r = recordado();
  if (r && r.correo === correo) {
    /* Este equipo entraba con huella. Si alla ya no esta --la quito
       desde otro equipo o cambio su contrasena, que las quita todas--,
       se olvida aqui y se vuelve a ofrecer (seccion 110). */
    try {
      if ((await mias()).some(esDeAqui)) return false;
    } catch { return false; }
    olvidar();
  }
  const dijo = (leer(NO_AHORA) || {})[correo];
  return !(dijo && Date.now() - dijo < DIAS_SIN_PREGUNTAR * 86400000);
}
export function ahoraNo(correo) {
  const todos = leer(NO_AHORA) || {};
  todos[correo] = Date.now();
  escribir(NO_AHORA, todos);
}

/* Como se va a llamar en su lista: "Chrome en Android". */
export function nombreDelEquipo() {
  const ua = navigator.userAgent || "";
  const nav = /Edg\//.test(ua) ? "Edge" : /SamsungBrowser/.test(ua) ? "Samsung Internet"
    : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome"
    : /Safari\//.test(ua) ? "Safari" : "";
  const so = /Android/.test(ua) ? "Android" : /iPhone/.test(ua) ? "iPhone"
    : /iPad/.test(ua) ? "iPad" : /Macintosh/.test(ua) ? "Mac"
    : /Windows/.test(ua) ? "Windows" : "";
  return [nav, so].filter(Boolean).join(idioma() === "en" ? " on " : " en ") || th("este");
}

/* ------------------------------------------------ WebAuthn en base64url */

function aBytes(texto) {
  const b = atob(texto.replace(/-/g, "+").replace(/_/g, "/")
                 + "===".slice((texto.length + 3) % 4));
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

/* Lo que el navegador contesta cuando la persona cancela o no hay huella,
   dicho en humano. */
function motivoDe(err) {
  if (err && err.name === "NotAllowedError") return new Error(th("cancelada"));
  if (err && err.name === "InvalidStateError") return new Error(th("ya_activada"));
  if (err && err.name === "NotSupportedError") return new Error(th("no_hay"));
  return err;
}

async function publico(ruta, cuerpo) {
  /* Sin la sesion: entrar es antes de tenerla, y un 401 aqui es "la
     huella no sirvio", no "tu sesion vencio" (api.post llevaria a la
     entrada). */
  const r = await fetch(ruta, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
  const d = await r.json().catch(() => null);
  if (!r.ok) throw new ErrorApi(r.status, d && d.detail);
  return d;
}

/* ------------------------------------------------ lo que se hace */

/* Entrar. Deja la sesion puesta, igual que entrar con contrasena. */
export async function entrar(correo = null) {
  /* Si este equipo ya entra con huella, la llave se escoge aqui: es la
     suya, y el telefono la encuentra aunque sea de las que no se ofrecen
     solas. Con el correo, el servidor contesta lo mismo tenga o no huella
     (seccion 110), y si alla ya no estaba el telefono no encontraba nada y
     decia "se cancelo"; asi firma, y el servidor dice claro que ya no
     esta. El correo va solo cuando se escribio en la caja. */
  const aqui = recordado();
  const suya = !correo && aqui && aqui.credencial ? aqui.credencial : null;
  const r = await publico("/auth/llaves/entrada/opciones",
                          { correo: suya ? null : (correo || (aqui || {}).correo || null) });
  const opciones = opcionesDe(r.opciones);
  if (suya) opciones.allowCredentials = [{ type: "public-key", id: aBytes(suya) }];
  let c;
  try {
    c = await navigator.credentials.get({ publicKey: opciones });
  } catch (err) { throw motivoDe(err); }
  let d;
  try {
    d = await publico("/auth/llaves/entrada",
                      { credencial: credencialJSON(c), estado: r.estado });
  } catch (err) {
    /* La de este equipo ya no existe alla: se olvida aqui, y la entrada
       vuelve a pedir la contrasena, que la ofrece otra vez (seccion 110). */
    if (err && err.detalle && err.detalle.codigo === "huella_desconocida") olvidar();
    throw err;
  }
  sesion.token = d.access_token;
  recordar(d.correo, d.nombre, c.id);
  return d;
}

/* Activar en este equipo. Pide la contrasena: la manda la pantalla que
   acaba de entrar con ella, o se escribe en "Entrar con huella". */
export async function activar(contrasena, correo, nombre) {
  const r = await api.post("/auth/llaves/alta/opciones", { contrasena });
  let c;
  try {
    c = await navigator.credentials.create({ publicKey: opcionesDe(r.opciones) });
  } catch (err) { throw motivoDe(err); }
  const hecha = await api.post("/auth/llaves/alta", {
    credencial: credencialJSON(c), estado: r.estado, nombre: nombreDelEquipo() });
  recordar(correo, nombre, hecha.credencial_id);
  return hecha;
}

export async function mias() {
  return api.get("/auth/llaves");
}

export async function quitar(llave) {
  await api.borrar(`/auth/llaves/${llave.id}`);
  const r = recordado();
  if (r && r.credencial === llave.credencial_id) olvidar();
}

/* Si esa llave es la de este equipo. */
export function esDeAqui(llave) {
  const r = recordado();
  return !!(r && r.credencial && r.credencial === llave.credencial_id);
}

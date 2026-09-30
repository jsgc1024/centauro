/* Entrar con huella o cara (30 sep). Lo comparten la consola y la app de
   campo: la llave vale en las dos (mycentauro.lat y appep.mycentauro.lat).

   Aqui vive lo que habla con el telefono (WebAuthn) y con el servidor, y
   los textos --en su propio diccionario, para no tocar idioma.js cada
   vez--. Lo que se pinta lo decide cada app: la consola y la app de
   campo no se ven igual.

   La huella nunca sale del telefono. El telefono firma un reto del
   servidor despues de pedir la huella, la cara o el PIN del equipo, y el
   servidor comprueba la firma. */
import { ErrorApi, api, sesion } from "/consola/api.js";
import { idioma } from "/consola/idioma.js";

const TEXTOS = {
  es: {
    boton: "Entrar con huella o cara",
    boton_corto: "Entrar con huella",
    o: "o",
    hola: "Hola, {nombre}",
    usar_contrasena: "Usar mi contraseña",
    no_soy: "No soy {nombre}",
    ofrecer_titulo: "¿Entrar con huella o cara la próxima vez?",
    ofrecer_texto: "En este equipo ya no tendrás que escribir tu contraseña: te pedirá tu huella, tu cara o el PIN del equipo.",
    ofrecer_si: "Sí, activar",
    ofrecer_no: "Ahora no",
    ofrecer_pie: "Tu huella no sale del equipo: Centauro nunca la ve. Se quita cuando quieras.",
    activada: "Listo: la próxima vez entras con tu huella o tu cara.",
    cancelada: "Se canceló. Vuelve a intentar o entra con tu contraseña.",
    ya_activada: "Este equipo ya tiene la huella activada.",
    no_hay: "Este equipo o navegador no permite entrar con huella.",
    titulo: "Entrar con huella o cara",
    pie: "Al entrar, el equipo te pide tu huella, tu cara o su PIN en vez de tu contraseña. Actívala solo en equipos que son tuyos.",
    este: "Este equipo",
    activar_aqui: "Activar en este equipo",
    pide_contrasena: "Para activarla, escribe tu contraseña.",
    contrasena: "Contraseña",
    ninguna: "Todavía no la tienes activada en ningún equipo.",
    usada: "Última vez: {cuando}",
    nunca: "Todavía no se usa",
    quitar: "Quitar",
    quitar_pregunta: "¿Quitar la huella de «{nombre}»? En ese equipo tendrás que entrar con tu contraseña.",
    quitada: "Se quitó. En ese equipo se entra con la contraseña.",
    activado_aqui: "Activado en este equipo",
  },
  en: {
    boton: "Sign in with fingerprint or face",
    boton_corto: "Sign in with fingerprint",
    o: "or",
    hola: "Hi, {nombre}",
    usar_contrasena: "Use my password",
    no_soy: "I am not {nombre}",
    ofrecer_titulo: "Sign in with your fingerprint or face next time?",
    ofrecer_texto: "On this device you won't have to type your password: it will ask for your fingerprint, your face or the device PIN.",
    ofrecer_si: "Yes, turn it on",
    ofrecer_no: "Not now",
    ofrecer_pie: "Your fingerprint never leaves the device: Centauro never sees it. You can remove it at any time.",
    activada: "Done: next time you sign in with your fingerprint or face.",
    cancelada: "It was cancelled. Try again or sign in with your password.",
    ya_activada: "This device already has fingerprint sign-in.",
    no_hay: "This device or browser does not support fingerprint sign-in.",
    titulo: "Sign in with fingerprint or face",
    pie: "When you sign in, the device asks for your fingerprint, face or PIN instead of your password. Turn it on only on devices that are yours.",
    este: "This device",
    activar_aqui: "Turn on for this device",
    pide_contrasena: "To turn it on, type your password.",
    contrasena: "Password",
    ninguna: "You have not turned it on for any device yet.",
    usada: "Last used: {cuando}",
    nunca: "Not used yet",
    quitar: "Remove",
    quitar_pregunta: "Remove fingerprint sign-in from “{nombre}”? On that device you will sign in with your password.",
    quitada: "Removed. On that device you sign in with your password.",
    activado_aqui: "On for this device",
  },
  pt: {
    boton: "Entrar com digital ou rosto",
    boton_corto: "Entrar com digital",
    o: "ou",
    hola: "Olá, {nombre}",
    usar_contrasena: "Usar minha senha",
    no_soy: "Não sou {nombre}",
    ofrecer_titulo: "Entrar com digital ou rosto da próxima vez?",
    ofrecer_texto: "Neste aparelho você não precisará digitar a senha: ele pedirá sua digital, seu rosto ou o PIN do aparelho.",
    ofrecer_si: "Sim, ativar",
    ofrecer_no: "Agora não",
    ofrecer_pie: "Sua digital não sai do aparelho: a Centauro nunca a vê. Pode ser removida quando quiser.",
    activada: "Pronto: da próxima vez você entra com sua digital ou seu rosto.",
    cancelada: "Foi cancelado. Tente de novo ou entre com sua senha.",
    ya_activada: "Este aparelho já tem a digital ativada.",
    no_hay: "Este aparelho ou navegador não permite entrar com digital.",
    titulo: "Entrar com digital ou rosto",
    pie: "Ao entrar, o aparelho pede sua digital, seu rosto ou o PIN em vez da senha. Ative só em aparelhos que são seus.",
    este: "Este aparelho",
    activar_aqui: "Ativar neste aparelho",
    pide_contrasena: "Para ativar, digite sua senha.",
    contrasena: "Senha",
    ninguna: "Ainda não está ativada em nenhum aparelho.",
    usada: "Última vez: {cuando}",
    nunca: "Ainda não usada",
    quitar: "Remover",
    quitar_pregunta: "Remover a digital de “{nombre}”? Nesse aparelho você entrará com a senha.",
    quitada: "Removida. Nesse aparelho se entra com a senha.",
    activado_aqui: "Ativado neste aparelho",
  },
};

export function th(clave, valores = {}) {
  const dic = TEXTOS[idioma()] || TEXTOS.es;
  let texto = dic[clave] || TEXTOS.es[clave] || clave;
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
   este equipo, o dijo "ahora no" hace menos de un mes, no se pregunta. */
export async function convieneOfrecer(correo) {
  if (!(await hayLector())) return false;
  const r = recordado();
  if (r && r.correo === correo) return false;
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
  const r = await publico("/auth/llaves/entrada/opciones",
                          { correo: correo || (recordado() || {}).correo || null });
  let c;
  try {
    c = await navigator.credentials.get({ publicKey: opcionesDe(r.opciones) });
  } catch (err) { throw motivoDe(err); }
  const d = await publico("/auth/llaves/entrada",
                          { credencial: credencialJSON(c), estado: r.estado });
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

/* La app del cliente de la Central de Inteligencia (seccion 133).

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

function llamarCentral() {
  if (!yo || !yo.telefono_central) return null;
  return h("div", { clase: "caja urgente" },
    h("a", { href: `tel:${yo.telefono_central.replace(/\s/g, "")}`,
             style: "text-decoration:none" },
      h("button", { clase: "claro" }, t("ci_llamar_central", { tel: yo.telefono_central }))),
    h("div", { clase: "chico gris", style: "margin-top:10px;text-align:center" },
      t("ci_atiende")));
}

function listaDeZonas(zonas) {
  if (zonas.length <= 1) return zonas.join("");
  const y = { es: " y ", pt: " e ", en: " and " }[idioma()] || " y ";
  return `${zonas.slice(0, -1).join(", ")}${y}${zonas[zonas.length - 1]}`;
}

async function pantallaMapa(mia = vuelta) {
  const datos = await api("GET", "/mapa");
  if (mia !== vuelta) return;
  const eventos = datos.eventos;
  pintar(encabezado(),
    h("h1", {}, t("ci_hola", { nombre: yo.nombre.split(" ")[0] })),
    h("p", { clase: "gris chico", style: "margin:2px 0 14px" },
      yo.zonas.length ? t("ci_lo_que_pasa", { zonas: listaDeZonas(yo.zonas) })
                      : t("ci_sin_zonas")),
    lienzoMapa(eventos, datos.llave_mapa),
    datos.llave_mapa ? leyenda() : null,
    h("h2", {}, t("ci_vigente_ahora", { n: eventos.length })),
    eventos.length ? eventos.map((e) => tarjetaEvento(e))
                   : h("div", { clase: "vacio" }, t("ci_nada_vigente")),
    llamarCentral(),
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

/* ------------------------------------------------------------ las rutas */

/* Cada vuelta de route() lleva su numero: si mientras esperaba al
   servidor ya empezo otra (se pico otra pestana), esta no pinta ni deja
   su reloj andando. */
let vuelta = 0;

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
    if (pantalla === "avisos") await pantallaAvisos(mia);
    else if (pantalla === "evento" && arg) await pantallaEvento(Number(arg), mia);
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

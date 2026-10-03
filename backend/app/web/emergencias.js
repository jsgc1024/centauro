/* Respuesta a emergencias (seccion 145).

   El panel de la guardia 24/7. A la izquierda lo activo --primero lo que
   nadie ha tomado, lo mas viejo arriba--; a la derecha la ficha de la
   alerta abierta: donde esta quien pidio ayuda (en vivo, con su
   recorrido), quien es, que riesgo hay cerca, a quien mas llamar, que
   unidades hay cerca, y lo que el area va haciendo, que queda en su
   bitacora.

   Llegan los tres panicos: el del cliente de la Central (desde su app),
   el de la app de campo y el del boton de la camioneta. Tomarla aqui es
   tomarla tambien en la central.

   Mientras haya una sin tomar, el panel suena. El navegador no deja
   sonar sin que alguien toque la pagina una vez: por eso el boton
   «Activar el sonido», que se va en cuanto sirve. */
import { api, sesion } from "./api.js";
import { aviso, h, hora, mensaje } from "./util.js";
import { t } from "./idioma.js";
import { tiene } from "./menu.js";
import { cargarGoogle } from "./riesgo.js";

const REFRESCO_SEGUNDOS = 10;
const COLOR = { abierta: "#c62828", en_atencion: "#e07000" };
const NIVEL = { 1: "#5f7187", 2: "#c99a06", 3: "#e07000", 4: "#c62828" };

let temporizador = null;
let sonando = null;
let audio = null;
let estado = null;

const puede = (actividad) => tiene(sesion.usuario, actividad);

export function detenerEmergencias() {
  clearInterval(temporizador);
  clearInterval(sonando);
  temporizador = null;
  sonando = null;
}

/* Hay algo escrito a medias: esta vuelta no se repinta la ficha. */
function hayCaptura(zona) {
  const foco = document.activeElement;
  return !!(foco && zona.contains(foco)
            && ["INPUT", "TEXTAREA", "SELECT"].includes(foco.tagName));
}

function hace(segundos) {
  if (segundos < 60) return t("em_hace_s").replace("{n}", segundos);
  if (segundos < 3600) return t("em_hace_min").replace("{n}", Math.floor(segundos / 60));
  return t("em_hace_h").replace("{n}", Math.floor(segundos / 3600));
}

/* La direccion aproximada sale de Google (su geocodificador), una vez
   por cada lugar distinto: se pide cuando quien pidio ayuda se movio. */
function claveDe(a) {
  return `${a.id}:${a.lat.toFixed(3)},${a.lon.toFixed(3)}`;
}

function direccionDe(a, zona) {
  if (!window.google || !google.maps || !google.maps.Geocoder) return;
  const clave = claveDe(a);
  if (estado.direccion && estado.direccion.clave === clave) return;
  estado.direccion = { clave, texto: "—" };
  new google.maps.Geocoder().geocode({ location: { lat: a.lat, lng: a.lon } }, (r, st) => {
    if (st !== "OK" || !r || !r.length) return;
    estado.direccion = { clave, texto: r[0].formatted_address };
    const celda = zona.querySelector(".em-donde");
    if (celda) celda.textContent = r[0].formatted_address;
  });
}

function dura(segundos) {
  if (segundos < 60) return t("em_dura_s").replace("{n}", segundos);
  return t("em_dura_min").replace("{n}", Math.round(segundos / 60));
}

function desde(iso) {
  return iso ? Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000)) : null;
}

/* La llamada que captura la central no es un panico, aunque se atienda
   igual. */
function tipoDe(c) {
  return c === "llamada" ? t("em_llamada") : t("em_panico");
}

function canal(c) {
  return t(`em_canal_${c}`) || c;
}

export async function pantallaEmergencias(main) {
  detenerEmergencias();
  estado = { abierto: null, mapa: null, mapaDe: null, lienzo: null, marca: null,
             linea: null, circulo: null, llave: undefined, direccion: null };
  const izquierda = h("div", { clase: "rsg-cola em-cola" });
  const ficha = h("div");
  main.append(
    h("h1", {}, t("em_titulo")),
    h("p", { clase: "sub" }, t("em_sub")),
    h("div", { clase: "rsg-mesa" }, izquierda, ficha));

  const refrescar = async () => {
    if (!document.body.contains(izquierda)) { detenerEmergencias(); return; }
    let datos;
    try {
      datos = await api.get("/emergencias");
    } catch (e) {
      izquierda.replaceChildren(aviso(e.message, "grave"));
      return;
    }
    pintarCola(izquierda, datos, ficha);
    sonar(datos.sin_tomar > 0);
    const ids = datos.activas.map((a) => a.id);
    /* La que se cerro (aqui o en la central) deja su lugar a la que
       sigue: con un panico nuevo sonando, la ficha no se queda en una
       cerrada. */
    if (!ids.includes(estado.abierto) && !hayCaptura(ficha)) {
      estado.abierto = ids.length ? ids[0] : null;
      if (!estado.abierto) {
        ficha.replaceChildren(h("div", { clase: "tarjeta" }, h("p", { clase: "gris" }, t("em_nada"))));
      }
    }
    if (estado.abierto && !hayCaptura(ficha)) await pintarFicha(ficha, estado.abierto, izquierda);
  };
  estado.refrescar = refrescar;
  /* El primer toque en la pagina ya deja sonar: el que llegue primero en
     el turno no entra en silencio. */
  document.addEventListener("pointerdown", activarSonido, { once: true });
  await refrescar();
  temporizador = setInterval(refrescar, REFRESCO_SEGUNDOS * 1000);
}

/* ------------------------------------------------------------ el sonido */

function sonar(hay) {
  if (!hay) {
    clearInterval(sonando);
    sonando = null;
    return;
  }
  if (sonando || !audio) return;
  const pitido = () => {
    if (!audio || audio.state !== "running") return;
    for (const [inicio, tono] of [[0, 880], [0.25, 660]]) {
      const osc = audio.createOscillator();
      const vol = audio.createGain();
      osc.frequency.value = tono;
      vol.gain.setValueAtTime(0.0001, audio.currentTime + inicio);
      vol.gain.exponentialRampToValueAtTime(0.4, audio.currentTime + inicio + 0.02);
      vol.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + inicio + 0.22);
      osc.connect(vol).connect(audio.destination);
      osc.start(audio.currentTime + inicio);
      osc.stop(audio.currentTime + inicio + 0.24);
    }
  };
  pitido();
  sonando = setInterval(pitido, 2000);
}

function activarSonido() {
  try {
    const Contexto = window.AudioContext || window.webkitAudioContext;
    if (!audio && Contexto) audio = new Contexto();
    if (audio && audio.state === "suspended") audio.resume();
  } catch (e) { audio = null; }
}

/* ------------------------------------------------------------ la cola */

function pintarCola(zona, datos, ficha) {
  const bloques = [];
  const sinSonido = !audio || audio.state !== "running";
  const botonSonido = sinSonido
    ? h("button", { type: "button", clase: "claro chico", onclick: () => {
        activarSonido();
        sonar(false);
        sonar(datos.sin_tomar > 0);
        estado.refrescar();
      } }, t("em_activar_sonido"))
    : null;
  if (datos.sin_tomar > 0) {
    bloques.push(h("div", { clase: "aviso grave" },
      h("b", {}, t(datos.sin_tomar === 1 ? "em_sin_tomar_1" : "em_sin_tomar_n")
        .replace("{n}", datos.sin_tomar)), " ", t("em_suena"),
      botonSonido ? h("div", { style: "margin-top:8px" }, botonSonido) : null));
  } else if (botonSonido) {
    /* Sin nada sonando tambien: que el primero del turno no llegue en
       silencio. */
    bloques.push(h("div", { clase: "aviso alerta" }, t("em_sin_sonido"), " ", botonSonido));
  }
  bloques.push(h("h3", { clase: datos.sin_tomar ? "rsg-grave" : "" },
    t("em_activas").replace("{n}", datos.activas.length)));
  if (!datos.activas.length) bloques.push(h("p", { clase: "chico gris" }, t("em_nada")));
  for (const a of datos.activas) {
    const sinTomar = a.estatus === "abierta";
    bloques.push(h("button", {
      type: "button", clase: "rsg-renglon" + (a.id === estado.abierto ? " em-elegida" : ""),
      style: "border-left:5px solid " + (COLOR[a.estatus] || "#5f7187"),
      onclick: async () => { estado.abierto = a.id; pintarCola(zona, datos, ficha); await pintarFicha(ficha, a.id, zona); },
    },
      h("div", {}, h("span", { clase: sinTomar ? "etiqueta grave" : "etiqueta" },
        sinTomar ? t("em_sin_tomar") : t("em_la_atiende").replace("{quien}", a.atiende || "—")),
        a.dijo_error ? h("span", { clase: "etiqueta alerta", style: "margin-left:6px" }, t("em_dijo_error_corto")) : null),
      h("strong", {}, `${tipoDe(a.canal)} · ${a.quien}`),
      h("div", { clase: "chico gris" },
        [canal(a.canal), a.de, hace(desde(a.reportada_en))].filter(Boolean).join(" · "))));
  }
  const dia = datos.dia;
  bloques.push(h("h3", {}, t("em_hoy")),
    h("div", { clase: "chico gris" }, t("em_hoy_cuenta")
      .replace("{total}", dia.total).replace("{cerradas}", dia.cerradas)
      .replace("{tomar}", dia.para_tomar_s === null ? "—" : dura(dia.para_tomar_s))));
  zona.replaceChildren(...bloques);
}

/* ------------------------------------------------------------ la ficha */

async function pintarFicha(zona, id, cola) {
  let a;
  try {
    a = await api.get(`/emergencias/${id}`);
  } catch (e) {
    zona.replaceChildren(aviso(e.message, "grave"));
    return;
  }
  if (estado.abierto !== id) return;
  const atender = puede("emergencias.atender");
  const sinTomar = a.estatus === "abierta";
  const cerrada = a.estatus === "cerrada";
  const salida = h("div");

  const hacer = async (ruta, cuerpo = {}) => {
    /* Un doble clic no escribe dos renglones en la bitacora. */
    for (const b of zona.querySelectorAll("button")) b.disabled = true;
    try {
      await api.post(`/emergencias/${id}/${ruta}`, cuerpo);
      mensaje(t("em_listo"));
      await estado.refrescar();
      await pintarFicha(zona, id, cola);
    } catch (e) {
      for (const b of zona.querySelectorAll("button")) b.disabled = false;
      salida.replaceChildren(aviso(e.message, "grave"));
    }
  };

  const cabeza = h("div", { clase: "rsg-cabeza" },
    h("strong", {}, a.folio), " ",
    h("span", { clase: "etiqueta grave" }, tipoDe(a.canal)), " ",
    h("span", { clase: "etiqueta" }, canal(a.canal)), " ",
    h("span", { clase: sinTomar ? "etiqueta grave" : "etiqueta" },
      sinTomar ? `${t("em_sin_tomar")} · ${hace(desde(a.reportada_en))}`
               : cerrada ? t("em_cerrada") : t("em_la_atiende").replace("{quien}", a.atiende || "—")));

  const arriba = h("div", { clase: "acciones", style: "margin:10px 0 12px" },
    sinTomar && atender
      ? h("button", { type: "button", clase: "peligro", onclick: () => hacer("tomar") }, t("em_tomar"))
      : null,
    a.telefono_de_quien
      ? h("a", { href: `tel:${a.telefono_de_quien.replace(/\s/g, "")}`, style: "text-decoration:none" },
          h("button", { type: "button", clase: "claro" },
            t("em_llamar").replace("{tel}", a.telefono_de_quien)))
      : null);

  const mapa = h("div", { clase: "em-mapa" });
  const ubic = a.lat === null
    ? h("p", { clase: "chico gris" }, t("em_sin_ubicacion"))
    : h("p", { clase: "chico gris", style: "margin:4px 0 10px" },
        t("em_ubicacion").replace("{hace}", hace(desde(a.ubicacion_en) || 0))
          .replace("{precision}", a.precision_m === null ? "—" : a.precision_m),
        " · ",
        h("a", { href: `https://www.google.com/maps?q=${a.lat},${a.lon}`, target: "_blank",
                 rel: "noopener" }, `${a.lat.toFixed(5)}, ${a.lon.toFixed(5)}`));

  const fila = (clave, valor) => h("tr", {},
    h("td", { clase: "gris", style: "width:170px" }, t(clave)), h("td", {}, valor));
  const riesgo = a.riesgo_cerca.length
    ? h("div", {}, ...a.riesgo_cerca.map((e) => h("div", {},
        h("span", { clase: "rsg-nivel", style: `background:${NIVEL[e.nivel]}` }, String(e.nivel)), " ",
        `${e.titulo} · ${t("em_a_km").replace("{km}", e.km)} (${e.folio})`)))
    : t("em_nada_cerca");
  const contactos = a.contactos.length
    ? h("div", {}, ...a.contactos.map((c) => h("div", {},
        `${c.nombre} (${t(`em_contacto_${c.que}`)})`,
        c.telefono ? [" · ", h("a", { href: `tel:${c.telefono.replace(/\s/g, "")}` }, c.telefono)] : "")))
    : t("em_sin_contacto");
  const unidades = a.unidades_cerca.length
    ? a.unidades_cerca.map((u) => t("em_unidad").replace("{placa}", u.placa)
        .replace("{km}", u.km).replace("{min}", u.hace_min)).join(" · ")
    : t("em_sin_unidades");
  const tabla = h("table", { clase: "fondo-tabla" }, h("tbody", {},
    fila("em_quien", [a.quien, a.telefono_de_quien ? ` · ${a.telefono_de_quien}` : ""].join("")),
    fila("em_de", a.de || "—"),
    a.lat === null ? null : fila("em_donde", h("span", { clase: "em-donde" },
      estado.direccion && estado.direccion.clave === claveDe(a) ? estado.direccion.texto : "—")),
    fila("em_riesgo_cerca", riesgo),
    fila("em_contactos", contactos),
    fila("em_unidades", unidades)));

  const avisos = [];
  if (a.dijo_error) avisos.push(aviso(t("em_dijo_error"), "alerta"));
  if (a.descripcion) avisos.push(aviso(a.descripcion));
  if (cerrada && a.resolucion) avisos.push(aviso(t("em_resolucion").replace("{r}", a.resolucion), "ok"));

  const acciones = [];
  if (atender && !cerrada && !sinTomar) {
    const nota = h("textarea", { rows: "2", placeholder: t("em_nota_ph"), "data-crudo": "" });
    acciones.push(
      h("div", { clase: "acciones", style: "margin-top:12px" },
        a.equipo_enviado
          ? h("span", { clase: "etiqueta ok" }, t("em_equipo_salio"))
          : h("button", { type: "button", clase: "claro", onclick: () => hacer("equipo", { nota: nota.value }) }, t("em_equipo")),
        a.autoridades
          ? h("span", { clase: "etiqueta ok" }, t("em_autoridades_ya"))
          : h("button", { type: "button", clase: "claro", onclick: () => hacer("autoridades", { nota: nota.value }) }, t("em_autoridades"))),
      h("div", { clase: "campo", style: "margin-top:10px" }, nota),
      h("div", { clase: "acciones" },
        h("button", { type: "button", clase: "claro", onclick: () => hacer("nota", { nota: nota.value }) }, t("em_guardar_nota")),
        h("button", { type: "button", onclick: () => hacer("cerrar", { resolucion: nota.value }) }, t("em_cerrar"))),
      h("p", { clase: "chico gris" }, t("em_cerrar_pie")));
  }

  const bitacora = h("ul", { clase: "chico" },
    ...a.bitacora.map((b) => h("li", {},
      h("b", {}, hora(b.en)), ` · ${b.quien} · ${t(`em_accion_${b.accion}`) || b.accion}`,
      b.detalle ? ` — ${b.detalle}` : "")));

  zona.replaceChildren(h("div", { clase: "tarjeta em-ficha", style: "border-top:4px solid " + (COLOR[a.estatus] || "#5f7187") },
    cabeza, arriba, ...avisos, mapa, ubic, tabla, ...acciones, salida,
    h("h3", { style: "margin-top:14px" }, t("em_bitacora")), bitacora));
  await pintarMapa(mapa, a);
  if (a.lat !== null) direccionDe(a, zona);
}

/* El mapa se arma una vez por alerta y se mueve a la ficha nueva en
   cada vuelta: rehacerlo cada diez segundos lo haria parpadear y le
   pediria a Google un mapa nuevo cada vez. Se mueven el punto, el
   circulo de la precision y el recorrido. */
async function pintarMapa(caja, a) {
  if (a.lat === null) { caja.remove(); return; }
  if (estado.llave === undefined) {
    try { estado.llave = (await api.get("/emergencias/mapa-llave")).llave; }
    catch (e) { estado.llave = null; }
  }
  if (!estado.llave) { caja.replaceChildren(aviso(t("em_sin_llave"), "alerta")); return; }
  try { await cargarGoogle(estado.llave); }
  catch (e) { caja.replaceChildren(aviso(t("em_mapa_no_cargo"), "alerta")); return; }
  const punto = { lat: a.lat, lng: a.lon };
  const recorrido = a.puntos.map((p) => ({ lat: p.lat, lng: p.lon }));
  if (estado.mapa && estado.mapaDe === a.id) {
    caja.replaceChildren(estado.lienzo);
    estado.marca.setPosition(punto);
    estado.linea.setPath(recorrido);
    estado.circulo.setCenter(punto);
    estado.circulo.setRadius(a.precision_m || 0);
    return;
  }
  const lienzo = h("div", { clase: "rsg-lienzo em-lienzo" });
  caja.replaceChildren(lienzo);
  const mapa = new google.maps.Map(lienzo, {
    center: punto, zoom: 14, mapTypeControl: false, streetViewControl: false,
    fullscreenControl: true, clickableIcons: false });
  Object.assign(estado, {
    mapa, mapaDe: a.id, lienzo,
    linea: new google.maps.Polyline({ map: mapa, path: recorrido,
      strokeColor: "#2e86de", strokeOpacity: 0.9, strokeWeight: 4 }),
    marca: new google.maps.Marker({ map: mapa, position: punto, title: a.quien }),
    circulo: new google.maps.Circle({ map: mapa, center: punto, radius: a.precision_m || 0,
      strokeColor: COLOR.abierta, strokeWeight: 1, fillColor: COLOR.abierta, fillOpacity: 0.12 }),
  });
}

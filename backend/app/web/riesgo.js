/* El mapa de riesgo de la Central de Inteligencia (seccion 135).

   Una pantalla, dos mesas. La del analista: a la izquierda lo que espera
   una mano --la llamada del nivel 4 sin acuse, lo que espera al jefe de
   turno, lo propuesto--, al centro el mapa con lo vigente, y la ficha del
   evento que se esta trabajando. La de los clientes de la Central: quien
   tiene el servicio, que estados sigue y quien de su gente entra a su
   app.

   El orden de la izquierda es el de la urgencia, no el de llegada: la
   llamada que se debe va antes que el evento por publicar, porque detras
   de ella hay alguien que no ha visto un nivel 4.

   El mapa es Google Maps interactivo, con su propia llave limitada a las
   direcciones del sistema. Sin llave la pantalla sigue sirviendo: el
   punto se escribe a mano y lo vigente se lee en la lista. */
import { api, sesion } from "./api.js";
import { aviso, campo, entrada, fecha, fechaLocal, h, hora, lista, mensaje } from "./util.js";
import { t } from "./idioma.js";
import { tiene } from "./menu.js";
import { mesaDeFondo } from "./fondo.js";
import { mesaDelLector } from "./lector.js";

const REFRESCO_SEGUNDOS = 60;
const COLOR = { 1: "#5f7187", 2: "#c99a06", 3: "#e07000", 4: "#c62828" };
const CENTRO = { MX: { lat: 23.6, lng: -102.5, zoom: 5 },
                 BR: { lat: -14.2, lng: -51.9, zoom: 4 } };

let temporizador = null;
let googleListo = null;           // la promesa de la carga del script
let mapa = null;
let capas = [];                   // circulos de lo vigente
let marca = null;                 // el punto del evento abierto
let circuloAbierto = null;
let ctx = null;                   // pais, catalogos, ultimo tablero

const puede = (actividad) => tiene(sesion.usuario, actividad);

/* Hay algo escrito a medias: esta vuelta no se repinta (como la
   central, seccion 101). */
function hayCaptura(zona) {
  const foco = document.activeElement;
  if (foco && zona.contains(foco)
      && ["INPUT", "TEXTAREA", "SELECT"].includes(foco.tagName)) return true;
  return !!zona.querySelector("[data-editando]");
}

export async function pantallaRiesgo(main) {
  clearInterval(temporizador);
  mapa = null; capas = []; marca = null; circuloAbierto = null;

  let paises = [];
  try {
    paises = await api.get("/catalogos/paises");
  } catch (e) {
    main.append(aviso(e.message, "grave"));
    return;
  }
  const conRegiones = paises.filter((p) => p.codigo === "MX" || p.codigo === "BR");
  ctx = { pais: conRegiones.find((p) => p.codigo === "MX") || conRegiones[0],
          paises: conRegiones, cat: null, tablero: null, abierto: null };

  const selPais = lista("pais", conRegiones.map((p) => ({ valor: p.id, texto: p.nombre })));
  selPais.value = ctx.pais.id;

  const pestanaMapa = h("button", { type: "button", clase: "pestana activa" }, t("rsg_tab_mapa"));
  const pestanaLector = h("button", { type: "button", clase: "pestana" }, t("rsg_tab_lector"));
  const pestanaFondo = h("button", { type: "button", clase: "pestana" }, t("rsg_tab_fondo"));
  const pestanaClientes = h("button", { type: "button", clase: "pestana" }, t("rsg_tab_clientes"));
  const cuerpo = h("div");

  main.append(
    h("h1", {}, t("rsg_titulo")),
    h("p", { clase: "sub" }, t("rsg_sub")),
    h("div", { clase: "rsg-barra" }, campo(t("rsg_pais"), selPais),
      h("div", { clase: "pestanas" }, pestanaMapa, pestanaLector, pestanaFondo, pestanaClientes)),
    cuerpo);

  /* La cuenta de lo que espera en el lector va en su pestana: se ve
     desde cualquier otra. */
  const contarLector = (n) => {
    pestanaLector.textContent = n ? `${t("rsg_tab_lector")} · ${n}` : t("rsg_tab_lector");
  };
  const mostrar = async (cual, abrir = null) => {
    pestanaMapa.classList.toggle("activa", cual === "mapa");
    pestanaLector.classList.toggle("activa", cual === "lector");
    pestanaFondo.classList.toggle("activa", cual === "fondo");
    pestanaClientes.classList.toggle("activa", cual === "clientes");
    clearInterval(temporizador);
    cuerpo.replaceChildren();
    if (cual === "mapa") {
      await mesaDelAnalista(cuerpo);
      if (abrir) await abrirEvento(abrir);
    } else if (cual === "lector") {
      await mesaDelLector(cuerpo, {
        pais: ctx.pais, contar: contarLector, catalogos,
        puedePublicar: puede("riesgo.publicar"), puedeFuentes: puede("riesgo.catalogo"),
        abrirEnMapa: (id) => mostrar("mapa", id),
        cadaMinuto: (fn, ms) => { clearInterval(temporizador); temporizador = setInterval(fn, ms); },
      });
    } else if (cual === "fondo") await mesaDeFondo(cuerpo, { pais: ctx.pais, cargarGoogle });
    else await mesaDeClientes(cuerpo);
  };
  const activa = () => (pestanaMapa.classList.contains("activa") ? "mapa"
    : pestanaLector.classList.contains("activa") ? "lector"
    : pestanaFondo.classList.contains("activa") ? "fondo" : "clientes");
  pestanaLector.onclick = () => mostrar("lector");
  pestanaMapa.onclick = () => mostrar("mapa");
  pestanaFondo.onclick = () => mostrar("fondo");
  pestanaClientes.onclick = () => mostrar("clientes");
  selPais.onchange = async () => {
    ctx.pais = conRegiones.find((p) => String(p.id) === selPais.value);
    ctx.cat = null;
    mapa = null;
    await mostrar(activa());
  };
  await mostrar("mapa");
  if (ctx.pais.codigo === "MX") {
    api.get("/riesgo/lector").then((d) => contarLector(d.cuenta.revisar)).catch(() => {});
  }
}

async function catalogos() {
  if (!ctx.cat) ctx.cat = await api.get(`/riesgo/catalogos?pais_id=${ctx.pais.id}`);
  return ctx.cat;
}

/* ================================================== la mesa del analista */

async function mesaDelAnalista(cuerpo) {
  const izquierda = h("div", { clase: "rsg-cola" });
  const caja = h("div", { clase: "rsg-mapa" });
  const ficha = h("div", { clase: "rsg-ficha" });
  cuerpo.append(h("div", { clase: "rsg-mesa" }, izquierda,
                  h("div", { clase: "rsg-centro" }, caja, ficha)));
  try {
    await catalogos();
  } catch (e) {
    cuerpo.replaceChildren(aviso(e.message, "grave"));
    return;
  }
  await prepararMapa(caja, ficha);

  const refrescar = async () => {
    if (!document.body.contains(izquierda)) {
      clearInterval(temporizador);
      return;
    }
    if (hayCaptura(izquierda) || hayCaptura(ficha)) return;
    await pintarCola(izquierda, ficha);
  };
  await refrescar();
  temporizador = setInterval(refrescar, REFRESCO_SEGUNDOS * 1000);
}

async function prepararMapa(caja, ficha) {
  let llave = null;
  try {
    llave = (await api.get("/riesgo/mapa-llave")).llave;
  } catch (e) { /* sin llave: la pantalla sigue sin mapa */ }
  if (!llave) {
    caja.replaceChildren(aviso(t("rsg_sin_llave"), "alerta"));
    return;
  }
  try {
    await cargarGoogle(llave);
  } catch (e) {
    caja.replaceChildren(aviso(t("rsg_mapa_no_cargo"), "alerta"));
    return;
  }
  const centro = CENTRO[ctx.pais.codigo] || CENTRO.MX;
  const lienzo = h("div", { clase: "rsg-lienzo" });
  caja.replaceChildren(lienzo, leyenda());
  mapa = new google.maps.Map(lienzo, {
    center: { lat: centro.lat, lng: centro.lng }, zoom: centro.zoom,
    mapTypeControl: false, streetViewControl: false, fullscreenControl: true,
    clickableIcons: false,
  });
  /* Con una ficha abierta y editable, un clic en el mapa pone el punto. */
  mapa.addListener("click", (ev) => {
    if (!ctx.abierto || !ctx.abierto.editable) return;
    ctx.abierto.ponerPunto(ev.latLng.lat(), ev.latLng.lng());
  });
}

/* La comparte el panel de Respuesta a emergencias (seccion 145): una
   sola carga del script de Google por consola. */
export function cargarGoogle(llave) {
  if (window.google && window.google.maps) return Promise.resolve();
  if (googleListo) return googleListo;
  googleListo = new Promise((resolver, rechazar) => {
    window.__rsgMapaListo = () => resolver();
    const idioma = (document.documentElement.lang || "es").slice(0, 2);
    const s = document.createElement("script");
    s.src = "https://maps.googleapis.com/maps/api/js?key="
      + encodeURIComponent(llave) + "&v=weekly&language=" + idioma
      + "&callback=__rsgMapaListo";
    s.async = true;
    /* El dominio, no la ruta: con eso Google reconoce la llave aunque la
       pagina diga otra politica (seccion 135). */
    s.referrerPolicy = "strict-origin-when-cross-origin";
    s.onerror = () => { googleListo = null; rechazar(new Error("maps")); };
    document.head.append(s);
  });
  return googleListo;
}

function leyenda() {
  return h("div", { clase: "rsg-leyenda" },
    ...[1, 2, 3, 4].map((n) => h("span", {},
      h("i", { style: `background:${COLOR[n]}` }), `${n} ${t(`rsg_nivel_${n}`)}`)));
}

function pintarEnMapa(publicados) {
  if (!mapa) return;
  for (const c of capas) c.setMap(null);
  capas = [];
  for (const e of publicados) {
    if (e.lat === null || e.lat === undefined) continue;
    const c = new google.maps.Circle({
      map: mapa, center: { lat: e.lat, lng: e.lon }, radius: e.radio_m || 1000,
      strokeColor: COLOR[e.nivel], strokeWeight: 2, strokeOpacity: 0.9,
      fillColor: COLOR[e.nivel], fillOpacity: 0.22,
    });
    c.addListener("click", () => abrirEvento(e.id));
    capas.push(c);
  }
}

function etiquetaNivel(n) {
  return h("span", { clase: "rsg-nivel", style: `background:${COLOR[n]}` },
           `${n} · ${t(`rsg_nivel_${n}`)}`);
}

async function pintarCola(zona, ficha) {
  let tablero, llamar = [];
  try {
    [tablero, llamar] = await Promise.all([
      api.get(`/riesgo/mapa?pais_id=${ctx.pais.id}`),
      api.get("/riesgo/por-llamar"),
    ]);
  } catch (e) {
    zona.replaceChildren(aviso(e.message, "grave"));
    return;
  }
  ctx.tablero = tablero;
  pintarEnMapa(tablero.publicados);

  const bloques = [];
  if (puede("riesgo.publicar")) {
    bloques.push(h("button", { type: "button", clase: "rsg-nuevo",
      onclick: () => abrirEvento(null) }, t("rsg_nuevo")));
  }

  if (llamar.length) {
    bloques.push(h("h3", { clase: "rsg-grave" }, t("rsg_por_llamar"), ` · ${llamar.length}`),
      ...llamar.map((a) => renglonLlamada(a, zona, ficha)));
  }
  const esperan = tablero.cola.filter((e) => e.estado === "por_confirmar" || e.nivel_pendiente);
  const propuestos = tablero.cola.filter((e) => e.estado === "propuesto");
  if (esperan.length) {
    bloques.push(h("h3", {}, t("rsg_esperan_jefe"), ` · ${esperan.length}`),
      ...esperan.map(renglonEvento));
  }
  bloques.push(h("h3", {}, t("rsg_propuestos"), ` · ${propuestos.length}`),
    propuestos.length ? h("div", {}, ...propuestos.map(renglonEvento))
                      : h("p", { clase: "chico gris" }, t("rsg_nada_propuesto")));
  bloques.push(h("h3", {}, t("rsg_vigentes"), ` · ${tablero.publicados.length}`),
    tablero.publicados.length ? h("div", {}, ...tablero.publicados.map(renglonEvento))
                              : h("p", { clase: "chico gris" }, t("rsg_nada_vigente")));
  zona.replaceChildren(...bloques);
}

/* Lo que publico Connect solo (seccion 143): por que regla, a que hora,
   y que el analista lo puede corregir o cerrar. */
function avisoDeConnect(e) {
  const regla = ["oficial", "confirmado", "informativo", "alto", "critico"].includes(e.auto_regla)
    ? e.auto_regla : "informativo";
  const porQue = t(`rsg_auto_${regla}`).replace("{dato}", e.auto_dato || "").replace("{nivel}", e.nivel);
  const hora = (e.publicado_en || "").slice(11, 16);
  return h("div", { clase: "aviso rsg-auto-aviso" },
    h("b", {}, t("rsg_auto_aviso").replace("{hora}", hora)), " ", porQue, ". ",
    t("rsg_auto_aviso_sub"));
}

function renglonEvento(e) {
  const donde = e.municipio ? `${e.municipio}, ${e.region}` : e.region;
  return h("button", { type: "button", clase: "rsg-renglon", onclick: () => abrirEvento(e.id) },
    h("div", {}, etiquetaNivel(e.nivel),
      e.nivel_pendiente ? h("span", { clase: "etiqueta alerta" }, t("rsg_pide_4")) : null,
      e.auto_regla ? h("span", { clase: "etiqueta info rsg-auto" }, t("rsg_auto_etiqueta")) : null),
    h("strong", {}, e.titulo),
    h("div", { clase: "chico gris" }, `${e.folio} · ${e.tipo} · ${donde}`));
}

function renglonLlamada(a, zona, ficha) {
  const nota = entrada("nota", { "data-crudo": "", placeholder: t("rsg_nota_llamada") });
  const salida = h("div");
  return h("div", { clase: "rsg-renglon rsg-llamar" },
    h("div", {}, etiquetaNivel(a.nivel), " ", h("strong", {}, a.persona)),
    h("div", { clase: "chico" }, `${a.cliente} · ${a.telefono || a.correo}`),
    h("div", { clase: "chico gris" }, `${a.folio} · ${a.titulo}`),
    puede("riesgo.publicar") ? h("div", { clase: "rsg-linea" }, nota,
      h("button", { type: "button", onclick: async () => {
        try {
          await api.post(`/riesgo/avisos/${a.id}/llamada`, { nota: nota.value });
          await pintarCola(zona, ficha);
        } catch (e) { salida.replaceChildren(mensaje(e.message, "grave")); }
      } }, t("rsg_registrar_llamada"))) : null,
    salida);
}

/* ------------------------------------------------------------ la ficha */

const EDITABLES = ["region_id", "municipio", "tipo_id", "nivel", "titulo",
                   "texto_cliente", "lat", "lon", "radio_m", "lugar",
                   "ocurrio_en", "vigente_hasta", "tendencia"];

/* "2026-10-02T21:00:00-06:00" -> "2026-10-02T21:00": la hora del pais tal
   cual, sin que el navegador la mueva a la suya. */
const local = (iso) => (iso ? iso.slice(0, 16) : "");

function ahoraLocal(masHoras = 0) {
  const zona = ctx.pais.zona_horaria || "America/Mexico_City";
  const d = new Date(Date.now() + masHoras * 3600 * 1000);
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: zona, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(d).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour === "24" ? "00" : p.hour}:${p.minute}`;
}

async function abrirEvento(id) {
  const ficha = document.querySelector(".rsg-ficha");
  if (!ficha) return;
  let e = null;
  if (id) {
    try {
      e = await api.get(`/riesgo/eventos/${id}`);
    } catch (err) {
      ficha.replaceChildren(aviso(err.message, "grave"));
      return;
    }
  }
  pintarFicha(ficha, e);
}

function pintarFicha(ficha, e) {
  const cat = ctx.cat;
  const nuevo = !e;
  const terminado = e && ["cerrado", "descartado"].includes(e.estado);
  const editable = puede("riesgo.publicar") && !terminado;
  const original = e ? Object.fromEntries(EDITABLES.map((k) => [k,
    ["ocurrio_en", "vigente_hasta"].includes(k) ? local(e[k]) : e[k]])) : {};

  const tipo = lista("tipo_id", cat.tipos.filter((x) => x.activo || (e && x.id === e.tipo_id))
    .map((x) => ({ valor: x.id, texto: x.nombre })));
  const definicion = h("p", { clase: "chico gris rsg-definicion" });
  const region = lista("region_id", [{ valor: "", texto: t("rsg_elige_estado") },
    ...cat.regiones.map((r) => ({ valor: r.id, texto: r.nombre }))]);
  const municipio = entrada("municipio", { maxlength: 120 });
  const titulo = entrada("titulo", { maxlength: 160, "data-crudo": "" });
  const texto = h("textarea", { name: "texto_cliente", rows: 3, maxlength: 2000,
                                placeholder: t("rsg_ph_texto") });
  const lugar = entrada("lugar", { maxlength: 300, "data-crudo": "" });
  const lat = entrada("lat", { inputmode: "decimal" });
  const lon = entrada("lon", { inputmode: "decimal" });
  const radio = entrada("radio_m", { type: "number", min: 50, max: 200000, step: 50 });
  const ocurrio = entrada("ocurrio_en", { type: "datetime-local" });
  const vigente = entrada("vigente_hasta", { type: "datetime-local" });
  const tendencia = lista("tendencia", [{ valor: "", texto: "—" },
    ...cat.tendencias.map((x) => ({ valor: x, texto: t(`rsg_tend_${x}`) }))]);
  let nivel = e ? e.nivel : 2;
  const niveles = h("div", { clase: "rsg-niveles" });
  const pintarNiveles = () => niveles.replaceChildren(...[1, 2, 3, 4].map((n) =>
    h("button", { type: "button", clase: n === nivel ? "rsg-n activo" : "rsg-n",
      style: n === nivel ? `background:${COLOR[n]};border-color:${COLOR[n]}` : `border-color:${COLOR[n]}`,
      disabled: !editable, onclick: () => { nivel = n; pintarNiveles(); } },
      `${n} ${t(`rsg_nivel_${n}`)}`)));
  pintarNiveles();

  if (e) {
    tipo.value = e.tipo_id; region.value = e.region_id; municipio.value = e.municipio || "";
    titulo.value = e.titulo; texto.value = e.texto_cliente || ""; lugar.value = e.lugar || "";
    lat.value = e.lat ?? ""; lon.value = e.lon ?? ""; radio.value = e.radio_m ?? "";
    ocurrio.value = local(e.ocurrio_en); vigente.value = local(e.vigente_hasta);
    tendencia.value = e.tendencia || "";
  } else {
    ocurrio.value = ahoraLocal(); vigente.value = ahoraLocal(6);
  }
  const mostrarDefinicion = () => {
    const x = cat.tipos.find((y) => String(y.id) === String(tipo.value));
    definicion.textContent = x ? x.definicion : "";
    if (nuevo && x && !radio.value) radio.value = x.radio_m;
  };
  tipo.onchange = () => { radio.value = ""; mostrarDefinicion(); dibujarPunto(); };
  mostrarDefinicion();

  for (const c of [tipo, region, municipio, titulo, texto, lugar, lat, lon, radio,
                   ocurrio, vigente, tendencia]) {
    c.disabled = !editable;
    c.addEventListener("input", () => ficha.setAttribute("data-editando", "1"));
  }

  const masHoras = (n) => h("button", { type: "button", clase: "claro chico", disabled: !editable,
    onclick: () => { vigente.value = sumarHoras(ocurrio.value || ahoraLocal(), n);
                     ficha.setAttribute("data-editando", "1"); } }, `+${n} h`);

  /* El punto en el mapa: un clic lo pone, arrastrarlo lo mueve. */
  function dibujarPunto() {
    if (!mapa) return;
    const la = parseFloat(lat.value), lo = parseFloat(lon.value);
    if (Number.isNaN(la) || Number.isNaN(lo)) {
      if (marca) marca.setMap(null);
      if (circuloAbierto) circuloAbierto.setMap(null);
      marca = null; circuloAbierto = null;
      return;
    }
    const pos = { lat: la, lng: lo };
    if (!marca) {
      marca = new google.maps.Marker({ map: mapa, position: pos, draggable: editable });
      marca.addListener("dragend", (ev) => ponerPunto(ev.latLng.lat(), ev.latLng.lng()));
    } else marca.setPosition(pos);
    const r = parseInt(radio.value, 10) || 1000;
    if (!circuloAbierto) {
      circuloAbierto = new google.maps.Circle({ map: mapa, center: pos, radius: r,
        strokeColor: COLOR[nivel], strokeWeight: 2, fillOpacity: 0.08, fillColor: COLOR[nivel],
        clickable: false });
    } else { circuloAbierto.setCenter(pos); circuloAbierto.setRadius(r); }
  }
  function ponerPunto(la, lo) {
    lat.value = la.toFixed(6); lon.value = lo.toFixed(6);
    ficha.setAttribute("data-editando", "1");
    dibujarPunto();
  }
  for (const c of [lat, lon, radio]) c.addEventListener("change", dibujarPunto);
  if (marca) { marca.setMap(null); marca = null; }
  if (circuloAbierto) { circuloAbierto.setMap(null); circuloAbierto = null; }
  dibujarPunto();
  if (mapa && e && e.lat !== null && e.lat !== undefined) {
    mapa.panTo({ lat: e.lat, lng: e.lon });
    if (mapa.getZoom() < 9) mapa.setZoom(10);
  }
  ctx.abierto = { editable, ponerPunto };

  const salida = h("div");
  const leer = () => {
    const v = {
      region_id: region.value ? Number(region.value) : null,
      municipio: municipio.value.trim() || null,
      tipo_id: Number(tipo.value), nivel,
      titulo: titulo.value.trim(), texto_cliente: texto.value.trim(),
      lat: lat.value === "" ? null : Number(lat.value),
      lon: lon.value === "" ? null : Number(lon.value),
      radio_m: radio.value === "" ? null : Number(radio.value),
      lugar: lugar.value.trim() || null,
      ocurrio_en: ocurrio.value, vigente_hasta: vigente.value,
      tendencia: tendencia.value || null,
    };
    if (nuevo) return { ...v, pais_id: ctx.pais.id };
    /* Solo lo que cambio: mandar el nivel de siempre cancelaria un 4 que
       espera al jefe. */
    const cambios = {};
    for (const k of EDITABLES) {
      const antes = original[k] ?? null, ahora = v[k] ?? null;
      if (String(antes ?? "") !== String(ahora ?? "")) cambios[k] = v[k];
    }
    return cambios;
  };

  const ejecutar = async (accion) => {
    salida.replaceChildren();
    try {
      const r = await accion();
      ficha.removeAttribute("data-editando");
      pintarFicha(ficha, r);
      await pintarCola(document.querySelector(".rsg-cola"), ficha);
    } catch (err) {
      salida.replaceChildren(mensaje(err.message, "grave"));
    }
  };
  const guardar = () => ejecutar(async () => {
    if (nuevo) return api.post("/riesgo/eventos", leer());
    const cambios = leer();
    if (!Object.keys(cambios).length) return api.get(`/riesgo/eventos/${e.id}`);
    return api.patch(`/riesgo/eventos/${e.id}`, cambios);
  });
  const accion = (ruta, cuerpo) => ejecutar(() => api.post(`/riesgo/eventos/${e.id}/${ruta}`, cuerpo));

  /* Las acciones que piden motivo abren su renglon en vez de un dialogo. */
  const conMotivo = (texto, ruta, tono = "") => {
    const motivo = entrada("motivo", { maxlength: 400, "data-crudo": "", placeholder: t("rsg_ph_motivo") });
    const fila = h("div", { clase: "rsg-linea" }, motivo,
      h("button", { type: "button", clase: tono, onclick: () => accion(ruta, { motivo: motivo.value }) },
        t("rsg_confirmar")));
    return h("button", { type: "button", clase: `claro ${tono}`.trim(), onclick: (ev) => {
      ev.target.replaceWith(fila);
      ficha.setAttribute("data-editando", "1");
      motivo.focus();
    } }, texto);
  };

  const botones = [];
  if (editable) {
    botones.push(h("button", { type: "button", onclick: guardar },
      nuevo ? t("rsg_guardar_propuesto") : t("rsg_guardar")));
  }
  if (e && editable && e.estado === "propuesto") {
    botones.push(h("button", { type: "button", clase: "primario", onclick: async () => {
      const cambios = leer();
      await ejecutar(async () => {
        if (Object.keys(cambios).length) await api.patch(`/riesgo/eventos/${e.id}`, cambios);
        return api.post(`/riesgo/eventos/${e.id}/publicar`);
      });
    } }, e.nivel === 4 || nivel === 4 ? t("rsg_pedir_4") : t("rsg_publicar")));
  }
  const esperaJefe = e && (e.estado === "por_confirmar" || e.nivel_pendiente);
  if (esperaJefe && puede("riesgo.confirmar")) {
    botones.push(h("button", { type: "button", clase: "grave", onclick: () => accion("confirmar") },
      t("rsg_confirmar_4")), conMotivo(t("rsg_devolver"), "devolver"));
  }
  if (e && editable && e.estado === "publicado") {
    botones.push(conMotivo(t("rsg_cerrar"), "cerrar"));
  }
  if (e && editable && ["propuesto", "por_confirmar"].includes(e.estado)) {
    botones.push(conMotivo(t("rsg_descartar"), "descartar", "grave"));
  }
  botones.push(h("button", { type: "button", clase: "claro", onclick: () => {
    ficha.removeAttribute("data-editando");
    ctx.abierto = null;
    if (marca) { marca.setMap(null); marca = null; }
    if (circuloAbierto) { circuloAbierto.setMap(null); circuloAbierto = null; }
    ficha.replaceChildren();
  } }, t("rsg_cerrar_ficha")));

  const cabeza = e
    ? h("div", { clase: "rsg-cabeza" }, h("strong", {}, e.folio), " ",
        h("span", { clase: "etiqueta" }, t(`rsg_estado_${e.estado}`)), " ",
        h("span", { clase: "etiqueta" }, t(`rsg_verif_${e.verificacion}`)),
        e.nivel_pendiente ? h("span", { clase: "etiqueta alerta" }, t("rsg_pide_4")) : null,
        e.auto_regla ? h("span", { clase: "etiqueta info" }, t("rsg_auto_etiqueta")) : null)
    : h("div", { clase: "rsg-cabeza" }, h("strong", {}, t("rsg_nuevo")));

  const tarjeta = h("div", { clase: "tarjeta" },
    cabeza,
    e && e.auto_regla ? avisoDeConnect(e) : null,
    e && e.motivo ? aviso(e.motivo) : null,
    h("div", { clase: "rejilla" },
      campo(t("rsg_tipo"), tipo, { obligatorio: true }),
      campo(t("rsg_estado_region"), region, { obligatorio: true }),
      campo(t("rsg_municipio"), municipio)),
    definicion,
    campo(t("rsg_nivel"), niveles, { obligatorio: true }),
    campo(t("rsg_titulo_evento"), titulo, { obligatorio: true }),
    campo(t("rsg_texto_cliente"), texto, { obligatorio: true }),
    h("div", { clase: "rejilla" },
      campo(t("rsg_ocurrio"), ocurrio, { obligatorio: true }),
      campo(t("rsg_vigente"), h("div", {}, vigente,
        h("div", { clase: "rsg-linea" }, masHoras(2), masHoras(6), masHoras(24))), { obligatorio: true }),
      campo(t("rsg_tendencia"), tendencia)),
    h("p", { clase: "chico gris" }, mapa ? t("rsg_ayuda_punto") : t("rsg_ayuda_punto_sin_mapa")),
    h("div", { clase: "rejilla" },
      campo(t("rsg_lat"), lat), campo(t("rsg_lon"), lon),
      campo(t("rsg_radio"), radio), campo(t("rsg_lugar"), lugar)),
    h("div", { clase: "acciones" }, ...botones),
    salida,
    e ? fuentes(e, editable, ficha) : null,
    e ? h("div", { clase: "rsg-avisos" }) : null,
    e ? bitacora(e) : null);
  ficha.replaceChildren(tarjeta);
  if (e) pintarAvisos(ficha.querySelector(".rsg-avisos"), e);
}

function sumarHoras(valor, horas) {
  const [d, hhmm] = valor.split("T");
  const [y, mo, da] = d.split("-").map(Number);
  const [hh, mi] = hhmm.split(":").map(Number);
  const x = new Date(Date.UTC(y, mo - 1, da, hh, mi) + horas * 3600 * 1000);
  return x.toISOString().slice(0, 16);
}

function fuentes(e, editable, ficha) {
  const descripcion = entrada("descripcion", { maxlength: 300, "data-crudo": "", placeholder: t("rsg_ph_fuente") });
  const url = entrada("url", { maxlength: 600, "data-crudo": "", placeholder: "https://…" });
  const oficial = h("input", { type: "checkbox", name: "oficial" });
  const salida = h("div");
  const quitar = (f) => h("button", { type: "button", clase: "claro chico", title: t("rsg_quitar"),
    "aria-label": t("rsg_quitar"), onclick: async () => {
      try {
        pintarFicha(ficha, await api.borrar(`/riesgo/eventos/${e.id}/fuentes/${f.id}`));
      } catch (err) { salida.replaceChildren(mensaje(err.message, "grave")); }
    } }, "×");
  return h("div", { clase: "tarjeta" },
    h("h3", {}, t("rsg_fuentes"), " · ", h("span", { clase: "chico gris" }, t("rsg_fuentes_pie"))),
    e.fuentes.length ? h("ul", {}, ...e.fuentes.map((f) => h("li", {},
      f.url ? h("a", { href: f.url, target: "_blank", rel: "noopener noreferrer" }, f.descripcion)
            : f.descripcion,
      f.oficial ? h("span", { clase: "etiqueta ok" }, t("rsg_oficial")) : null,
      editable ? quitar(f) : null)))
      : h("p", { clase: "chico gris" }, t("rsg_sin_fuentes")),
    editable ? h("div", { clase: "rsg-linea" }, descripcion, url,
      h("label", { clase: "casilla" }, oficial, t("rsg_oficial")),
      h("button", { type: "button", onclick: async () => {
        try {
          pintarFicha(ficha, await api.post(`/riesgo/eventos/${e.id}/fuentes`, {
            descripcion: descripcion.value, url: url.value || null, oficial: oficial.checked }));
        } catch (err) { salida.replaceChildren(mensaje(err.message, "grave")); }
      } }, t("rsg_agregar"))) : null,
    salida);
}

async function pintarAvisos(zona, e) {
  let filas = [];
  try {
    filas = await api.get(`/riesgo/eventos/${e.id}/avisos`);
  } catch (err) {
    zona.replaceChildren(aviso(err.message, "grave"));
    return;
  }
  zona.replaceChildren(h("div", { clase: "tarjeta" },
    h("h3", {}, t("rsg_avisos"), ` · ${filas.length}`),
    filas.length ? h("table", { clase: "tabla" },
      h("thead", {}, h("tr", {}, h("th", {}, t("rsg_persona")), h("th", {}, t("rsg_cliente")),
        h("th", {}, t("rsg_nivel")), h("th", {}, t("rsg_por_donde")), h("th", {}, t("rsg_acuse")))),
      h("tbody", {}, ...filas.map((a) => h("tr", {},
        h("td", {}, a.persona), h("td", {}, a.cliente), h("td", {}, etiquetaNivel(a.nivel)),
        h("td", {}, [a.telefonos ? t("rsg_por_telefono") : null,
                     a.correo_enviado ? t("rsg_por_correo") : null].filter(Boolean).join(" · ") || "—"),
        h("td", {}, a.acuse_en ? h("span", { clase: "etiqueta ok" }, t("rsg_visto"))
          : a.requiere_acuse ? h("span", { clase: "etiqueta alerta" }, t("rsg_sin_acuse")) : "—")))))
      : h("p", { clase: "chico gris" }, e.estado === "publicado" ? t("rsg_sin_avisos") : t("rsg_avisos_al_publicar"))));
}

function bitacora(e) {
  return h("div", { clase: "tarjeta" }, h("h3", {}, t("rsg_bitacora")),
    h("ul", { clase: "chico" }, ...e.bitacora.slice().reverse().map((b) => h("li", {},
      h("strong", {}, b.en.slice(0, 16).replace("T", " ")), " · ", b.quien, " · ",
      t(`rsg_acc_${b.accion}`), b.detalle ? ` — ${b.detalle}` : ""))));
}

/* ================================================ los clientes de la Central */

async function mesaDeClientes(cuerpo) {
  let filas, todos;
  try {
    await catalogos();
    [filas, todos] = await Promise.all([api.get("/riesgo/clientes"),
                                        api.get("/catalogos/clientes")]);
  } catch (e) {
    cuerpo.replaceChildren(aviso(e.message, "grave"));
    return;
  }
  const delPais = filas.filter((c) => c.pais_id === ctx.pais.id);
  const maneja = puede("riesgo.clientes");
  const salida = h("div");

  const bloques = [h("p", { clase: "sub" }, t("rsg_clientes_sub"))];
  if (maneja) {
    const yaEstan = new Set(filas.map((c) => c.cliente_id));
    const disponibles = todos.filter((c) => c.pais_id === ctx.pais.id && !yaEstan.has(c.id));
    const sel = lista("cliente_id", [{ valor: "", texto: t("rsg_elige_cliente") },
      ...disponibles.map((c) => ({ valor: c.id, texto: c.nombre }))]);
    bloques.push(h("div", { clase: "rsg-linea" }, sel,
      h("button", { type: "button", onclick: async () => {
        if (!sel.value) return;
        try {
          await api.post("/riesgo/clientes", { cliente_id: Number(sel.value) });
          await mesaDeClientes(cuerpo.replaceChildren() || cuerpo);
        } catch (e) { salida.replaceChildren(mensaje(e.message, "grave")); }
      } }, t("rsg_dar_servicio"))), salida);
  }
  if (!delPais.length) bloques.push(h("p", { clase: "chico gris" }, t("rsg_sin_clientes")));
  for (const c of delPais) bloques.push(fichaCliente(c, maneja, cuerpo));
  cuerpo.replaceChildren(...bloques);
}

function fichaCliente(c, maneja, cuerpo) {
  const salida = h("div");
  const recargar = () => mesaDeClientes(cuerpo);
  const marcadas = new Set(c.zonas.map((z) => z.region_id));
  const casillas = h("div", { clase: "rsg-zonas" }, ...ctx.cat.regiones.map((r) => {
    const caja = h("input", { type: "checkbox", value: r.id, disabled: !maneja });
    caja.checked = marcadas.has(r.id);
    return h("label", { clase: "casilla" }, caja, r.nombre);
  }));
  const guardarZonas = h("button", { type: "button", onclick: async () => {
    const ids = [...casillas.querySelectorAll("input:checked")].map((x) => Number(x.value));
    try {
      await api.put(`/riesgo/clientes/${c.id}/zonas`, { region_ids: ids });
      await recargar();
    } catch (e) { salida.replaceChildren(mensaje(e.message, "grave")); }
  } }, t("rsg_guardar_zonas"));

  const nombre = entrada("nombre", { maxlength: 80, placeholder: t("rsg_nombre") });
  const apellidos = entrada("apellidos", { maxlength: 120, placeholder: t("rsg_apellidos") });
  const correo = entrada("correo", { type: "email", maxlength: 160, placeholder: t("rsg_correo") });
  const tel = entrada("telefono", { maxlength: 40, placeholder: "+52 …" });
  const idioma = lista("idioma", ["es", "pt", "en"].map((x) => ({ valor: x, texto: t(`rsg_idioma_${x}`) })));
  const contacto = entrada("contacto_emergencia", { maxlength: 120, placeholder: t("rsg_contacto_nombre"),
                                                   value: c.contacto_emergencia || "" });
  const telContacto = entrada("telefono_emergencia", { maxlength: 40, placeholder: "+52 …",
                                                       value: c.telefono_emergencia || "" });

  const persona = (g) => h("tr", {},
    h("td", {}, `${g.nombre} ${g.apellidos}`), h("td", {}, g.correo), h("td", {}, g.telefono || "—"),
    h("td", {}, g.activo ? (g.con_contrasena ? h("span", { clase: "etiqueta ok" }, t("rsg_entra"))
                                             : h("span", { clase: "etiqueta alerta" }, t("rsg_sin_contrasena")))
                         : h("span", { clase: "etiqueta" }, t("rsg_cerrado_acceso")),
      /* Seccion 136: su invitacion, mientras no ponga su contrasena. */
      g.activo && !g.con_contrasena
        ? h("div", { clase: "chico gris" }, g.invitacion_vence
          ? t("rsg_invitacion_vence").replace("{cuando}",
              [fecha(fechaLocal(new Date(g.invitacion_vence))), hora(g.invitacion_vence)].join(" "))
          : t("rsg_invitacion_vencida"))
        : null),
    h("td", {}, maneja && g.activo ? h("button", { type: "button", clase: "claro chico", onclick: async () => {
      try {
        await api.post(`/riesgo/clientes/${c.id}/gente/${g.id}/invitacion`, {});
        await recargar();
      } catch (e) { salida.replaceChildren(mensaje(e.message, "grave")); }
    } }, t("rsg_reenviar_invitacion")) : null),
    h("td", {}, maneja ? h("button", { type: "button", clase: "claro chico", onclick: async () => {
      try {
        await api.patch(`/riesgo/clientes/${c.id}/gente/${g.id}`, { activo: !g.activo });
        await recargar();
      } catch (e) { salida.replaceChildren(mensaje(e.message, "grave")); }
    } }, g.activo ? t("rsg_cerrar_acceso") : t("rsg_abrir_acceso")) : null));

  return h("div", { clase: "tarjeta rsg-cliente" },
    h("div", { clase: "rsg-cabeza" }, h("strong", {}, c.cliente), " ",
      c.activo ? h("span", { clase: "etiqueta ok" }, t("rsg_con_servicio"))
               : h("span", { clase: "etiqueta" }, t("rsg_sin_servicio")),
      maneja ? h("button", { type: "button", clase: "claro chico", onclick: async () => {
        try {
          await api.patch(`/riesgo/clientes/${c.id}`, { activo: !c.activo });
          await recargar();
        } catch (e) { salida.replaceChildren(mensaje(e.message, "grave")); }
      } }, c.activo ? t("rsg_apagar_servicio") : t("rsg_encender_servicio")) : null),
    h("h3", {}, t("rsg_zonas"), ` · ${c.zonas.length}`),
    h("p", { clase: "chico gris" }, t("rsg_zonas_pie")),
    casillas, maneja ? h("div", { clase: "acciones" }, guardarZonas) : null,
    h("h3", {}, t("rsg_gente"), ` · ${c.gente.length}`),
    c.gente.length ? h("table", { clase: "tabla" }, h("tbody", {}, ...c.gente.map(persona)))
                   : h("p", { clase: "chico gris" }, t("rsg_sin_gente")),
    /* A quien llama Respuesta a emergencias del lado del cliente cuando
       alguien suyo aprieta el panico (seccion 145). */
    h("h3", {}, t("rsg_contacto_emergencia")),
    h("p", { clase: "chico gris" }, t("rsg_contacto_emergencia_pie")),
    maneja ? h("div", { clase: "rsg-linea" }, contacto, telContacto,
      h("button", { type: "button", clase: "claro", onclick: async () => {
        try {
          await api.put(`/riesgo/clientes/${c.id}/emergencia`, {
            contacto: contacto.value, telefono: telContacto.value });
          await recargar();
        } catch (e) { salida.replaceChildren(mensaje(e.message, "grave")); }
      } }, t("rsg_guardar_contacto")))
      : h("p", {}, [c.contacto_emergencia, c.telefono_emergencia].filter(Boolean).join(" · ")
          || t("rsg_sin_contacto_emergencia")),
    maneja ? h("div", { clase: "rsg-linea" }, nombre, apellidos, correo, tel, idioma,
      h("button", { type: "button", onclick: async () => {
        try {
          await api.post(`/riesgo/clientes/${c.id}/gente`, {
            nombre: nombre.value, apellidos: apellidos.value, correo: correo.value,
            telefono: tel.value || null, idioma: idioma.value, perfil: "gerente" });
          await recargar();
        } catch (e) { salida.replaceChildren(mensaje(e.message, "grave")); }
      } }, t("rsg_dar_alta_gerente"))) : null,
    salida);
}

export function detenerRiesgo() {
  clearInterval(temporizador);
}

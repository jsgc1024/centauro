/* El punto de encuentro, buscado en Google.

   De sus coordenadas salen la geocerca que el conductor tiene que pisar
   para marcar su llegada y los tres hospitales mas cercanos del task
   sheet. Escribirlas a mano es la forma mas facil de equivocarse, asi
   que aqui se buscan y se toman de ahi.

   Vive aparte porque el mismo punto se captura en dos pantallas —al dar
   de alta el servicio y al armar cada dia— y tienen que comportarse
   igual: la misma busqueda, el mismo mapa y el mismo cobro. */
import { api } from "./api.js";
import { aviso, h, mensaje, vaciar } from "./util.js";

export function buscadorDeLugar({
  paisId = () => "", alCambiar = () => {}, alDetectarAeropuerto = () => {},
  valores = {}, filas = "2",
} = {}) {
  /* El recuadro crece con lo que trae dentro. Google devuelve el
     nombre y la direccion completos —"Hyatt Regency Mexico City -
     Campos Eliseos 204, Polanco..."— y en dos renglones fijos hay que
     scrollear para leer lo que uno acaba de elegir, que es justo el
     momento en que se quiere verificar que es el hotel correcto. */
  const direccion = h("textarea", {
    rows: filas,
    placeholder: "Hotel, terminal o direccion. Ej: Las Alcobas Polanco",
    oninput: () => { crecer(); sugerir(); alCambiar(); } });
  direccion.value = valores.direccion || "";

  function crecer() {
    direccion.style.height = "auto";
    direccion.style.height = `${direccion.scrollHeight + 2}px`;
  }
  // Al pintarse todavia no esta en el documento y scrollHeight da cero.
  setTimeout(crecer, 0);

  const lat = h("input", { name: "origen_lat", placeholder: "19.4361",
                           value: valores.lat || "",
                           oninput: () => repintarMapa() });
  const lon = h("input", { name: "origen_lon", placeholder: "-99.0719",
                           value: valores.lon || "",
                           oninput: () => repintarMapa() });
  /* El radio de la geocerca, alrededor del mismo pin del punto de
     encuentro. Un kilometro por defecto: un aeropuerto no cabe en menos. */
  /* Dos kilometros en aeropuerto, uno en cualquier otro lado: un
     aeropuerto no cabe en un kilometro y la app le negaria la llegada a
     alguien que esta donde debe. Es una propuesta: en cuanto se escribe
     un radio a mano, deja de moverse solo. */
  const GEOCERCA_AEROPUERTO = 2000;
  const GEOCERCA_NORMAL = 500;

  const metros = h("input", { name: "geocerca_metros", type: "number",
                              min: "50", step: "50",
                              value: valores.metros || GEOCERCA_NORMAL,
                              oninput: () => {
                                metros.dataset.suyo = "1";
                                repintarMapa();
                              } });

  function proponerRadio(aeropuerto) {
    if (metros.dataset.suyo) return;
    metros.value = aeropuerto ? GEOCERCA_AEROPUERTO : GEOCERCA_NORMAL;
    repintarMapa();
  }

  const mapaImagen = h("img", { clase: "mapa-vista", alt: "" });
  const mapaEnlace = h("a", { target: "_blank", rel: "noopener" },
                       "Abrir en Google Maps");
  const mapaPie = h("div", { clase: "mapa-pie" }, mapaEnlace);
  const mapaVacio = h("div", { clase: "mapa-vacio" },
    "Busca la direccion para fijar el punto y su geocerca.");
  const cajaMapa = h("div", { clase: "mapa-caja" }, mapaVacio);
  const resultados = h("div", { clase: "resultados" });

  // La imagen anterior se suelta al pedir otra: si no, se van juntando
  // en la memoria del navegador conforme se mueve el pin.
  let direccionImagen = null;

  async function repintarMapa() {
    const conPin = lat.value.trim() && lon.value.trim();
    vaciar(cajaMapa);
    if (!conPin) { cajaMapa.append(mapaVacio); alCambiar(); return; }

    const radio = Number(metros.value) || GEOCERCA_NORMAL;
    mapaEnlace.href = "https://www.google.com/maps/search/?api=1&query="
      + encodeURIComponent(`${lat.value.trim()},${lon.value.trim()}`);
    cajaMapa.append(mapaImagen, mapaPie);
    alCambiar();

    try {
      const nueva = await api.imagen(
        `/mapas/imagen?lat=${lat.value.trim()}`
        + `&lon=${lon.value.trim()}&metros=${radio}`);
      if (direccionImagen) URL.revokeObjectURL(direccionImagen);
      direccionImagen = nueva;
      mapaImagen.src = nueva;
    } catch (err) {
      vaciar(cajaMapa);
      cajaMapa.append(h("div", { clase: "mapa-vacio" }, err.message));
    }
  }

  /* Google cobra por sesion de busqueda: todas las teclas de un mismo
     lugar mas el detalle del que se elija cuentan como una. Por eso el
     identificador se mantiene mientras se escribe y se renueva al
     elegir, que es cuando esa busqueda termino. */
  let esAeropuerto = !!valores.aeropuerto;
  // El ultimo lugar elegido, tal como lo devolvio Google: de ahi salen
  // su nombre, su direccion y su telefono sin volver a preguntarle.
  let ultimo_ = null;
  /* Lo que Google dijo del lugar, aparte de lo que decida el consultor.
     Arranca con lo que ya estaba guardado del dia, para que la pantalla
     pueda avisar antes de mandar algo que el servidor va a trabar. */
  let googleAeropuerto_ = valores.googleAeropuerto ?? null;
  let sesion = nuevaSesion();
  let espera = null;
  let ultimo = "";
  let apagado = false;

  function nuevaSesion() {
    return (crypto.randomUUID && crypto.randomUUID())
      || String(Date.now()) + Math.random().toString(16).slice(2);
  }

  function sugerir() {
    if (apagado) return;
    clearTimeout(espera);
    const texto = direccion.value.trim();
    if (texto.length < 3) { vaciar(resultados); return; }
    // Se espera a que deje de teclear: no se pide una sugerencia por letra.
    espera = setTimeout(() => pedir(texto), 350);
  }

  async function pedir(texto) {
    if (texto === ultimo) return;
    ultimo = texto;
    try {
      const r = await api.get("/mapas/sugerencias?texto="
        + encodeURIComponent(texto)
        + `&pais_id=${paisId()}&sesion=${sesion}`);
      // Si siguio escribiendo, esta respuesta ya no sirve.
      if (direccion.value.trim() !== texto) return;
      pintar(r.lugares);
    } catch (err) {
      vaciar(resultados);
      if (err.codigo === 503) {
        /* Sin llave de Google la pantalla sigue sirviendo: se escribe la
           direccion y el pin se pone a mano. No tiene caso repetir el
           intento —ni el aviso rojo— en cada tecla. */
        apagado = true;
        resultados.append(h("div", { clase: "gris chico" },
          "La busqueda en Google no esta configurada. Escribe la direccion "
          + "y fija el pin a mano en el apartado de abajo."));
      } else {
        resultados.append(aviso(err.message, "grave"));
      }
    }
  }

  function pintar(lugares) {
    vaciar(resultados);
    for (const lugar of lugares) {
      resultados.append(h("button", {
        clase: "resultado", type: "button", onclick: () => tomar(lugar) },
        h("b", {}, lugar.nombre),
        lugar.direccion
          ? h("span", { clase: "gris chico" }, lugar.direccion) : null));
    }
  }

  /* Al elegir una sugerencia se piden sus coordenadas y se guarda la
     direccion como la escribe Google: se puede seguir corrigiendo el
     texto, el punto ya quedo. */
  async function tomar(sugerencia) {
    vaciar(resultados);
    resultados.append(h("div", { clase: "gris chico" }, "Buscando el punto…"));
    try {
      const lugar = await api.get(
        `/mapas/lugar/${sugerencia.id}?sesion=${sesion}`);
      direccion.value = lugar.nombre && lugar.direccion
        ? `${lugar.nombre} - ${lugar.direccion}`
        : (lugar.direccion || lugar.nombre);
      crecer();
      lat.value = lugar.lat;
      lon.value = lugar.lon;
      // Google dice si el lugar elegido es un aeropuerto; de ahi sale
      // el radio, sin que nadie tenga que acordarse de la regla.
      esAeropuerto = !!lugar.aeropuerto;
      googleAeropuerto_ = !!lugar.aeropuerto;
      ultimo_ = lugar;
      if (lugar.aeropuerto) alDetectarAeropuerto();
      proponerRadio(lugar.aeropuerto);
      repintarMapa();
    } catch (err) {
      mensaje(err.message, "grave");
    }
    vaciar(resultados);
    // Esa busqueda termino: la siguiente es otra sesion.
    sesion = nuevaSesion();
    ultimo = "";
    alCambiar();
  }

  repintarMapa();

  return {
    direccion, resultados, cajaMapa, lat, lon, metros, repintarMapa,
    proponerRadio,
    conPin: () => !!(lat.value.trim() && lon.value.trim()),
    ultimo: () => ultimo_,
    /* true, false o null cuando la direccion se escribio a mano y no
       hay veredicto de Google que contradecir. */
    segunGoogle: () => googleAeropuerto_,
    valor: () => ({
      direccion: direccion.value.trim(),
      lat: lat.value.trim() || null,
      lon: lon.value.trim() || null,
      metros: Number(metros.value) || GEOCERCA_NORMAL,
      aeropuerto: esAeropuerto,
      googleAeropuerto: googleAeropuerto_,
    }),
    /* La casilla del consultor tambien manda: hay aeropuertos chicos que
       Google no marca como tales. */
    decirAeropuerto: (si) => { esAeropuerto = !!si; proponerRadio(si); },
  };
}

/* Ayudas de pintado. Nada de librerias: el objetivo es que esto se
   entienda y se pueda cambiar sin saber de frameworks. */

import { t } from "./idioma.js";

export function h(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [k, v] of Object.entries(atributos || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "clase") nodo.className = v;
    else if (k === "html") nodo.innerHTML = v;
    else if (k.startsWith("on")) nodo.addEventListener(k.slice(2), v);
    else nodo.setAttribute(k, v);
  }
  for (const hijo of hijos.flat()) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return nodo;
}

/* Una seccion que se pliega, y que al plegarse DICE lo que guarda.

   El alta de un servicio es larga: cliente, quien solicita, idiomas,
   vestimenta, y luego un equipo por cada uno. Para cuando se llega a los
   dias, lo de arriba ya esta resuelto y solo estorba --hay que bajar
   media pantalla para volver a ver lo que importa ahora--.

   Lo que hace que esto sirva y no sea solo esconder es el RESUMEN. Una
   seccion plegada que no dice nada obliga a abrirla para recordar que se
   puso, y entonces plegarla no ahorro nada: se cambio bajar la pantalla
   por abrir y cerrar. Con "Cliente Demo AAA · Mexico · Salvador Garcia"
   en el mismo renglon del titulo, no hace falta abrirla.

   El resumen se calcula al plegar, no al construir: los campos se llenan
   despues, asi que uno fijo diria siempre lo mismo que al abrir la
   pantalla, o sea nada.

   No se pliega sola al completarse, a proposito. Alguien que todavia
   esta escribiendo y ve desaparecer lo que escribe no confia en la
   pantalla nunca mas. Se pliega cuando la persona lo decide. */
export function plegable(titulo, contenido, resumen = null,
                         atributos = {}, abierto = true) {
  const cuerpo = h("div", {}, contenido);
  const linea = h("span", { clase: "resumen-plegable" });
  const flecha = h("span", { clase: "flecha-plegable" }, abierto ? "▾" : "▸");

  const pintar = (plegado) => {
    cuerpo.hidden = plegado;
    flecha.textContent = plegado ? "▸" : "▾";
    cabeza.setAttribute("aria-expanded", plegado ? "false" : "true");
    linea.textContent = plegado && resumen ? (resumen() || "") : "";
  };

  const alternar = () => pintar(!cuerpo.hidden);

  const cabeza = h("div", {
    clase: "cabeza-plegable", role: "button", tabindex: "0",
    "aria-expanded": "true",
    onclick: alternar,
    onkeydown: (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); alternar(); }
    },
  }, flecha, h("h4", { ...atributos, style: "margin:0" }, titulo), linea);

  /* Un bloque que nace cerrado tiene que nacer CON su resumen. Sin
     esto, el que arranca plegado se ve como un titulo solo --sin decir
     si guarda algo o esta vacio-- y hay que abrirlo para averiguarlo,
     que es justo lo que el resumen existe para evitar. */
  if (!abierto) pintar(true);

  return h("div", { clase: "plegable" }, cabeza, cuerpo);
}

/* Comparar nombres como los escribe alguien con prisa.
  
   Quien busca a Gerardo Muñoz teclea "munoz", y quien busca a Ivan
   escribe "ivan" aunque en su ficha diga "Ivan". Un filtro que exige la
   tilde y la ene no encuentra a nadie y se abandona al segundo intento.
   Se quitan los diacriticos y se baja todo a minusculas de los dos
   lados. */
export function sinTildes(texto) {
  return (texto || "").normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

/* ------------------------------------------------------------ buscar

   Tres listas --personal, servicios, implantados-- crecen hasta que dar
   con un renglon a ojo deja de ser posible. El buscador es el mismo en
   las tres y vive aqui para que se porte igual en todas: filtra sobre
   lo que ya se trajo --pedir la lista otra vez por cada letra es lo que
   hace que un buscador se sienta trabado-- y no le importan los
   acentos, porque Munoz y Muñoz son la misma persona para quien escribe
   de prisa. */

export function coincide(q, ...datos) {
  const buscado = sinTildes(q);
  if (!buscado) return true;
  return datos.some(dato => sinTildes(dato).includes(buscado));
}

export function buscador(ayuda, alEscribir) {
  const caja = h("input", { type: "search", placeholder: ayuda });
  caja.addEventListener("input", () => alEscribir(caja.value));
  return caja;
}


/* Lo que se lee en un desplegable, no su id: el resumen es para una
   persona. */
export function textoDe(select) {
  if (!select || select.selectedIndex < 0) return "";
  const opcion = select.options[select.selectedIndex];
  return opcion ? opcion.text.trim() : "";
}

export function campo(etiqueta, control) {
  return h("div", { clase: "campo" }, h("label", {}, etiqueta), control);
}

export function entrada(nombre, atributos = {}) {
  return h("input", { name: nombre, ...atributos });
}

export function lista(nombre, opciones, atributos = {}) {
  const sel = h("select", { name: nombre, ...atributos });
  for (const o of opciones) {
    sel.append(h("option", { value: o.valor }, o.texto));
  }
  return sel;
}

/* Un telefono se captura en dos: la clave del pais por un lado y el
   numero por otro. Asi la clave nunca se queda fuera y el numero se
   escribe de corrido, como lo dicta quien lo da. */
export function telefono(nombre, clavePais = "+52") {
  const pais = h("input", { name: `${nombre}_pais`, value: clavePais,
                            clase: "tel-pais", inputmode: "tel" });
  const numero = h("input", { name: `${nombre}_numero`,
                              placeholder: "55 1234 5678", inputmode: "tel" });
  const caja = h("div", { clase: "telefono" }, pais, numero);

  caja.controles = [pais, numero];

  caja.valor = () => {
    const clave = pais.value.trim();
    const resto = numero.value.trim();
    if (!resto) return null;              // solo la clave no es un telefono
    if (!clave) return resto;
    return `${clave.startsWith("+") ? clave : "+" + clave} ${resto}`;
  };

  /* Al traer un contacto ya guardado se vuelve a partir: "+52 55 1234
     5678" cae en sus dos casillas. */
  caja.poner = (completo) => {
    const partes = String(completo || "").trim().split(/\s+/).filter(Boolean);
    pais.value = partes.length && partes[0].startsWith("+") ? partes.shift()
                                                            : clavePais;
    numero.value = partes.join(" ");
  };

  caja.limpiar = () => { pais.value = clavePais; numero.value = ""; };

  caja.bloquear = (si) => {
    for (const c of caja.controles) {
      c.readOnly = si;
      c.classList.toggle("fijo", si);
    }
  };

  caja.clavePais = (clave) => {
    // Solo se cambia si el consultor no la ha tocado.
    if (!pais.value || pais.value === clavePais) pais.value = clave;
    clavePais = clave;
  };

  return caja;
}

export function etiqueta(texto, tono = "") {
  return h("span", { clase: `etiqueta ${tono}`.trim() }, texto);
}

/* Los estatus llegan del servidor en su clave: "en_comprobacion",
   "pagada". Antes se pintaban tal cual, asi que la consola en ingles
   decia "calculada" y la portuguesa "cancelado". El mapa va escrito
   entero a proposito: una clave armada al vuelo no se puede revisar. */
const ESTATUS = {
  borrador: "est_borrador",
  solicitado: "est_solicitado",
  // Reservado: la cotizacion vive en Odoo y el servicio llega ya
  // autorizado. Se traduce por si un dato viejo lo trae.
  cotizado: "est_cotizado",
  autorizado: "est_autorizado",
  planeado: "est_planeado",
  asignado: "est_asignado",
  arribado: "est_arribado",
  en_curso: "est_en_curso",
  terminado: "est_terminado",
  sin_visto_bueno: "est_sin_visto_bueno",
  en_facturacion: "est_en_facturacion",
  cerrado: "est_cerrado",
  cancelado: "est_cancelado",
  abierta: "est_abierta",
  en_atencion: "est_en_atencion",
  cerrada: "est_cerrada",
  calculada: "est_calculada",
  pagada: "est_pagada",
  transferido: "est_transferido",
  en_comprobacion: "est_en_comprobacion",
  devuelto: "est_devuelto",
  // Los del dia. `arribado` y `en_curso` son los mismos de arriba.
  planeada: "est_planeada",
  confirmada: "est_confirmada",
  proxima_a_iniciar: "est_proxima_a_iniciar",
  terminada: "est_terminada",
  cancelada: "est_cancelada",
};

export function estatus(codigo) {
  if (!codigo) return "—";
  const clave = ESTATUS[codigo];
  return clave ? t(clave) : String(codigo).replace(/_/g, " ");
}

export function aviso(texto, tono = "") {
  return h("div", { clase: `aviso ${tono}`.trim() }, texto);
}

/* ------------------------------------------------ la ayuda en pantalla

   Un encabezado de bloque con su "?" al lado. Tres frases, y las tres
   son la misma pregunta hecha de tres maneras:

     para      para que sirve este bloque
     cuando    cuando te enteras si falla
     numero    de donde sale el numero (cuando hay numero)

   Las dos primeras se exigen; la tercera solo tiene sentido donde hay
   una cifra que alguien va a querer cuadrar.

   El "?" existe para no escribir un manual. Un tutorial que vive aparte
   de la pantalla se despega el dia que la pantalla cambia, y nadie se
   entera hasta que alguien sigue un paso que ya no existe y pierde la
   confianza en todo lo demas. Este proyecto ya aprendio esa leccion tres
   veces: el umbral de silencio con 60 en una pantalla y 120 en la otra,
   el tope del mes escrito lejos de su candado, la lista de angulos de
   foto que se quedo en cuatro cuando el servidor paso a cinco.

   Por eso la clave se escribe AQUI, pegada al bloque que explica. Quien
   cambie el bloque tiene el texto delante, y `revisar.py` se queja si la
   clave no existe en los tres idiomas.

   El panel FLOTA, y no siempre fue asi. Abierto dentro del bloque
   empujaba todo hacia abajo y quedaba pegado al pie que ese mismo bloque
   ya trae: dos explicaciones seguidas y luego los botones, todo
   amontonado justo cuando uno abrio el "?" porque no entendia algo. Una
   ayuda que desacomoda la pantalla que esta explicando se lee peor que
   no tenerla.

   Asi que se abre encima, como cualquier menu: nada se mueve de su
   lugar, se lee, y se cierra picando afuera o con Escape. Una sola a la
   vez, porque dos paneles abiertos son dos explicaciones compitiendo. */
export function conAyuda(nivel, texto, clave, atributos = {}) {
  const panel = h("div", {
    clase: "panel-ayuda", hidden: "hidden",
    // Picar dentro no lo cierra: se puede seleccionar el texto.
    onclick: (e) => e.stopPropagation(),
  },
    parrafoAyuda(t("ayuda_para"), `${clave}_para`),
    parrafoAyuda(t("ayuda_cuando"), `${clave}_cuando`),
    parrafoAyuda(t("ayuda_numero"), `${clave}_numero`, true));

  const boton = h("button", {
    clase: "boton-ayuda", type: "button",
    title: t("ayuda_abrir"),
    "aria-label": t("ayuda_abrir"),
    "aria-expanded": "false",
    onclick: (e) => {
      e.stopPropagation();
      const abrir = panel.hidden;
      cerrarAyudas();
      panel.hidden = !abrir;
      boton.setAttribute("aria-expanded", abrir ? "true" : "false");
    },
  }, "?");

  return h("div", { clase: "con-ayuda" },
    h("div", { clase: "fila-ayuda" }, h(nivel, atributos, texto), boton),
    panel);
}

/* Se cierran como cualquier menu. Va una sola vez por modulo y no una
   por cada "?": hay cuarenta en la consola y se repintan enteros en cada
   vuelta, asi que un oyente por bloque son cuarenta oyentes nuevos cada
   vez que alguien cambia de pantalla. */
function cerrarAyudas() {
  for (const p of document.querySelectorAll(".panel-ayuda:not([hidden])")) {
    p.hidden = true;
  }
  for (const b of document.querySelectorAll('.boton-ayuda[aria-expanded="true"]')) {
    b.setAttribute("aria-expanded", "false");
  }
}

document.addEventListener("click", cerrarAyudas);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") cerrarAyudas();
});

/* La tercera frase no siempre aplica, y un renglon vacio con su titulito
   es peor que no ponerlo: ensena que los "?" traen relleno. */
function parrafoAyuda(rotulo, clave, opcional = false) {
  const texto = t(clave);
  if (opcional && (!texto || texto === clave)) return null;
  return h("p", { clase: "chico", style: "margin:6px 0 0" },
    h("b", {}, rotulo), " ", texto);
}

/* Mismo formato de fecha del task sheet: sin ambiguedad entre
   dia/mes y mes/dia, que con clientes extranjeros importa. El nombre
   del dia y el del mes salen del idioma de la consola: en portugues un
   viernes es "Sex", no "Vie". */
export function fecha(iso) {
  if (!iso) return "—";
  const f = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  const dias = t("f_dias").split(",");
  const meses = t("f_meses").split(",");
  return `${dias[f.getDay()]} ${String(f.getDate()).padStart(2, "0")} ` +
         `${meses[f.getMonth()]} ${f.getFullYear()}`;
}

export function hora(iso) {
  if (!iso) return "—";
  const f = new Date(iso);
  return `${String(f.getHours()).padStart(2, "0")}:${String(f.getMinutes()).padStart(2, "0")}`;
}

/* Cada moneda se escribe como se escribe en su pais. Con el formato de
   Mexico fijo, R$ 1.234,56 salia "R$ 1,234.56": los separadores al
   reves, que en un monto es justo lo que se lee mal. El formato es de
   la moneda, no de quien mira: un monto en reales se ve igual en la
   consola en ingles, que es como sale del banco brasileno. */
const COMO_SE_ESCRIBE = {
  MXN: "es-MX",
  BRL: "pt-BR",
  // El dolar NO va en en-US: ahi sale "$1,234.56", identico a como sale
  // un peso. En una empresa que cobra en las dos monedas, ese signo
  // suelto es un malentendido de 17 a 1. Con es-MX sale "USD 1,234.56".
  USD: "es-MX",
  VES: "es-VE",
};

export function dinero(valor, moneda = "MXN") {
  if (valor === null || valor === undefined) return "—";
  const numero = Number(valor);
  /* Sin centavos cuando no los hay. Los viaticos se depositan en enteros
     y una columna de "$550.00" al lado de "$1,200.00" se lee mas lenta
     que "$550" y "$1,200". Lo que si trae centavos —la factura de un
     boleto— los conserva. */
  const cerrado = Number.isInteger(numero);
  return new Intl.NumberFormat(COMO_SE_ESCRIBE[moneda] || "es-MX", {
    style: "currency", currency: moneda,
    minimumFractionDigits: cerrado ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(numero);
}

export function vaciar(nodo) {
  while (nodo.firstChild) nodo.removeChild(nodo.firstChild);
  return nodo;
}

/* Una sola forma de contar lo que pasa, para no llenar la pantalla de
   alertas del navegador. */
export function mensaje(texto, tono = "ok") {
  const barra = document.getElementById("mensajes");
  const nodo = aviso(texto, tono);
  barra.prepend(nodo);
  setTimeout(() => nodo.remove(), tono === "grave" ? 9000 : 5000);
}

export function datosDeFormulario(formulario) {
  const datos = {};
  for (const [k, v] of new FormData(formulario).entries()) {
    if (v !== "") datos[k] = v;
  }
  return datos;
}

/* Regla del sistema: lo que se captura se guarda parejo, con inicial
   mayuscula y el resto en minuscula, sin importar como venga escrito.
   Las palabras de enlace se quedan abajo porque un apellido se lee
   "Maria de la Cruz", no "Maria De La Cruz". */
const MENUDAS = new Set(["de", "del", "la", "las", "los", "y", "e", "el",
                         "al", "da", "do", "dos", "van", "von", "di", "der",
                         // Los lugares de la agenda tambien las llevan:
                         // "Comida en San Angel", "Bank of America".
                         "en", "a", "con", "por", "para", "of", "the"]);

export function titulo(texto) {
  let primera = true;
  return String(texto || "").trim().toLowerCase()
    .split(/(\s+|-|\/)/)
    .map((parte) => {
      if (!parte.trim()) return parte;
      const enlace = !primera && MENUDAS.has(parte);
      primera = false;
      return enlace ? parte : parte.charAt(0).toUpperCase() + parte.slice(1);
    })
    .join("");
}

/* Se aplica al salir del campo, no mientras se escribe: corregir letra
   por letra le mueve el cursor a quien captura. El correo, la clave y
   los campos marcados crudos se quedan como se escribieron; el numero
   de vuelo va todo en mayuscula porque asi lo imprime la aerolinea. */
const SIN_TOCAR = new Set(["email", "password", "date", "time",
                           "datetime-local", "number", "tel", "hidden",
                           "checkbox", "radio", "file"]);

export function vigilarCapturas(raiz = document) {
  raiz.addEventListener("focusout", (e) => {
    const el = e.target;
    if (!el || el.tagName !== "INPUT") return;
    if (SIN_TOCAR.has(el.type) || el.dataset.crudo !== undefined) return;
    const valor = el.value.trim();
    if (!valor) return;
    const nuevo = el.dataset.mayusculas !== undefined
      ? valor.toUpperCase() : titulo(valor);
    if (nuevo !== el.value) {
      el.value = nuevo;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }, true);
}

/* Una imagen lista para subir, sin que el navegador la mande entera.

   Una captura de pantalla de una Mac o de un iPhone sale en varios
   megas, y el servidor no acepta mas de tres. Se reduce aqui antes de
   salir: lo que no se sube, no se espera.

   La app de campo tiene su propia copia de esto en campo/foto.js, a
   proposito: ese archivo vive en el cache del trabajador de fondo, con
   su lista fija, y hacerlo depender de este romperia la app sin senal.
   Dos copias chicas cuestan menos que eso. */
const LADO_MAXIMO = 1600;
const CALIDAD = 0.75;

export function reducirImagen(archivo, lado = LADO_MAXIMO, calidad = CALIDAD) {
  return new Promise((listo, falla) => {
    const lector = new FileReader();
    lector.onerror = () => falla(new Error("No se pudo leer el archivo"));
    lector.onload = () => {
      const img = new Image();
      img.onerror = () => falla(new Error("Esa imagen no se puede abrir"));
      img.onload = () => {
        const escala = Math.min(1, lado / Math.max(img.width, img.height));
        const lienzo = document.createElement("canvas");
        lienzo.width = Math.round(img.width * escala);
        lienzo.height = Math.round(img.height * escala);
        lienzo.getContext("2d").drawImage(img, 0, 0, lienzo.width,
                                          lienzo.height);
        lienzo.toBlob(
          (b) => b ? listo(new File([b], "comprobante.jpg",
                                    { type: "image/jpeg" }))
                   : falla(new Error("No se pudo preparar la imagen")),
          "image/jpeg", calidad);
      };
      img.src = lector.result;
    };
    lector.readAsDataURL(archivo);
  });
}

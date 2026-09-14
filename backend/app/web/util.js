/* Ayudas de pintado. Nada de librerias: el objetivo es que esto se
   entienda y se pueda cambiar sin saber de frameworks. */

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

export function aviso(texto, tono = "") {
  return h("div", { clase: `aviso ${tono}`.trim() }, texto);
}

const MESES = ["ene", "feb", "mar", "abr", "may", "jun",
               "jul", "ago", "sep", "oct", "nov", "dic"];
const DIAS = ["Dom", "Lun", "Mar", "Mie", "Jue", "Vie", "Sab"];

/* Mismo formato de fecha del task sheet: sin ambiguedad entre
   dia/mes y mes/dia, que con clientes extranjeros importa. */
export function fecha(iso) {
  if (!iso) return "—";
  const f = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  return `${DIAS[f.getDay()]} ${String(f.getDate()).padStart(2, "0")} ` +
         `${MESES[f.getMonth()]} ${f.getFullYear()}`;
}

export function hora(iso) {
  if (!iso) return "—";
  const f = new Date(iso);
  return `${String(f.getHours()).padStart(2, "0")}:${String(f.getMinutes()).padStart(2, "0")}`;
}

export function dinero(valor, moneda = "MXN") {
  if (valor === null || valor === undefined) return "—";
  const numero = Number(valor);
  /* Sin centavos cuando no los hay. Los viaticos se depositan en enteros
     y una columna de "$550.00" al lado de "$1,200.00" se lee mas lenta
     que "$550" y "$1,200". Lo que si trae centavos —la factura de un
     boleto— los conserva. */
  const cerrado = Number.isInteger(numero);
  return new Intl.NumberFormat("es-MX", {
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

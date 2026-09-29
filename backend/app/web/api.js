/* Cliente de la API. Todo lo que habla con el servidor pasa por aqui,
   para que el manejo de errores y de la sesion viva en un solo lugar. */

const LLAVE = "centauro_token";

export const sesion = {
  get token() { return localStorage.getItem(LLAVE); },
  set token(v) { v ? localStorage.setItem(LLAVE, v) : localStorage.removeItem(LLAVE); },
  usuario: null,
};

export class ErrorApi extends Error {
  constructor(codigo, detalle) {
    super(ErrorApi.mensajeDe(detalle, codigo) || `Error ${codigo}`);
    this.codigo = codigo;
    this.detalle = detalle;
  }

  /* Quien traduce. Este archivo no importa idioma.js a proposito: es el
     unico que tiene que seguir funcionando aunque idioma.js sea justo lo
     que no cargo. La consola y la app de campo le prestan su `t()` al
     arrancar (seccion 101); sin el, los codigos salen en espanol. */
  static traducir = null;

  static texto(clave, huecos = {}) {
    const base = ErrorApi.traducir ? ErrorApi.traducir(clave) : null;
    let texto = base && base !== clave ? base : (ErrorApi.DE_FABRICA[clave] || clave);
    for (const [k, v] of Object.entries(huecos)) texto = texto.split(`{${k}}`).join(v);
    return texto;
  }

  /* El backend contesta errores de tres formas: texto, {mensaje, ...} o
     la lista de validacion de FastAPI. Aqui se normalizan. */
  static mensajeDe(d, codigo = null) {
    /* Se fue la senal o se acabo el tiempo: la pantalla decia "sin_red"
       y "tardo" tal cual, que no es ningun idioma (seccion 101). */
    if (codigo === 0) return ErrorApi.texto(d === "tardo" ? "api_tardo" : "cc_sin_red");
    if (!d) return null;
    if (typeof d === "string") return d;
    /* Un dato mal capturado (422): el servidor dice que campo y que le
       falta, y aqui se dice en el idioma de quien mira. Si el servidor
       no trae la lista (un 422 de antes), se usa su mensaje. */
    if (Array.isArray(d.errores) && d.errores.length) {
      return d.errores.map(e => ErrorApi.dato(e)).join("\n");
    }
    /* El backend escribe dos cosas distintas: que paso y que hacer. La
       segunda es la unica que sirve para salir del problema —"Registra
       primero la recepcion"— y se estaba tirando. Van juntas. */
    if (d.mensaje) return d.que_hacer ? `${d.mensaje}\n\n${d.que_hacer}`
                                      : d.mensaje;
    /* La lista de FastAPI, por si un 422 llega sin pasar por el
       manejador del servidor: cuando menos, con el nombre del campo. */
    if (Array.isArray(d)) {
      return d.map(x => {
        const campo = ErrorApi.campoDe(x.loc);
        return campo ? `${campo}: ${x.msg}` : (x.msg || JSON.stringify(x));
      }).join(". ");
    }
    return null;
  }

  static campoDe(loc) {
    return (Array.isArray(loc) ? loc : [])
      .filter(x => !["body", "query", "path"].includes(x))
      .map(String).join(".");
  }

  /* Un renglon de la lista del servidor: {campo, tipo, limite}. */
  static dato(e) {
    const clave = ErrorApi.TIPOS[e.tipo] || "val_otro";
    return ErrorApi.texto(clave, { campo: e.campo || "?",
                                   limite: e.limite === undefined || e.limite === null
                                     ? "" : String(e.limite),
                                   detalle: e.detalle || "" });
  }
}

/* Que clave de idioma le toca a cada tipo de error de captura. */
ErrorApi.TIPOS = {
  falta: "val_falta", numero: "val_numero", entero: "val_entero",
  largo: "val_largo", corto: "val_corto", minimo: "val_minimo",
  mas_de: "val_mas_de", maximo: "val_maximo", menos_de: "val_menos_de",
  fecha: "val_fecha", hora: "val_hora",
  opcion: "val_opcion", texto: "val_texto", lista: "val_lista",
  cuerpo: "val_cuerpo", regla: "val_regla",
};

/* Lo que se dice cuando no hay quien traduzca (idioma.js no cargo). Sin
   acentos a proposito: es el unico texto de la consola que no pasa por
   idioma.js, y la revision estatica lo sabe por eso. */
ErrorApi.DE_FABRICA = {
  cc_sin_red: "No hay conexion. Revisa tu internet e intentalo otra vez.",
  api_tardo: "El servidor tardo demasiado en contestar. Intentalo otra vez.",
  api_sesion_vencio: "La sesion vencio. Vuelve a entrar.",
  val_falta: "Falta el dato «{campo}».",
  val_numero: "«{campo}» tiene que ser un numero.",
  val_entero: "«{campo}» tiene que ser un numero entero.",
  val_largo: "«{campo}» es demasiado largo: caben {limite} letras.",
  val_corto: "«{campo}» es demasiado corto: minimo {limite} letras.",
  val_minimo: "«{campo}» tiene que ser de {limite} o mas.",
  val_mas_de: "«{campo}» tiene que ser mas de {limite}.",
  val_maximo: "«{campo}» no puede pasar de {limite}.",
  val_menos_de: "«{campo}» tiene que ser menos de {limite}.",
  val_fecha: "«{campo}» no es una fecha valida.",
  val_hora: "«{campo}» no es una hora valida.",
  val_opcion: "«{campo}» no es una opcion valida.",
  val_texto: "«{campo}» tiene que ser un texto.",
  val_lista: "«{campo}» tiene que ser una lista.",
  val_cuerpo: "Lo que se mando no se pudo leer.",
  val_regla: "«{campo}»: {detalle}",
  val_otro: "«{campo}»: {detalle}",
};

/* Cuanto se espera antes de darlo por perdido. Sin esto, media barra
   de senal deja la app en "Un momento..." para siempre: el telefono no
   corta solo. Lo que lleva fotos aguanta mas, porque subirlas con mala
   senal tarda de verdad. */
const SEGUNDOS = 25;
const SEGUNDOS_PESADO = 120;
const PESADO = 200000;

/* La caja negra (seccion 92).

   Lo ultimo que se le pidio al servidor y lo ultimo que se le enseno a
   quien usa el sistema, para cuando reporta una falla: con eso se
   encuentra la falla en el codigo sin preguntarle que boton pico. Vive
   solo en la memoria de esta pestana y no guarda la sesion: la ruta sin
   lo que va despues del ?, lo que contesto y cuando. Los errores se
   guardan aparte de lo demas para que las consultas de cada minuto no
   los saquen. */
const ERRORES = [];
const RECIENTES = [];
const MENSAJES = [];

function empujar(lista, cosa, cuantas) {
  lista.push(cosa);
  if (lista.length > cuantas) lista.shift();
}

function anotarLlamada(metodo, ruta, codigo, mensaje = "") {
  /* El reporte no se anota a si mismo: ni el envio ni la version que la
     forma pide al abrirse. */
  if (/^\/manual\/(fallas|version)/.test(String(ruta))) return;
  const llamada = { cuando: new Date().toISOString(), metodo,
                    ruta: String(ruta).split("?")[0], codigo,
                    mensaje: String(mensaje || "").slice(0, 300) };
  const lista = codigo === 0 || codigo >= 400 ? ERRORES : RECIENTES;
  /* La misma llamada con la misma respuesta, otra vez seguida --la app
     pide su dia al abrir y al repintar--, cuenta una vez con su hora
     nueva: seis renglones iguales no dicen nada. */
  const ultima = lista[lista.length - 1];
  if (ultima && ultima.metodo === metodo && ultima.ruta === llamada.ruta
      && ultima.codigo === codigo && ultima.mensaje === llamada.mensaje) {
    ultima.cuando = llamada.cuando;
    return;
  }
  empujar(lista, llamada, 6);
}

/* El mismo mensaje dos veces seguidas es uno solo, con su hora nueva: la
   app repinta cada minuto, y un aviso en rojo que se queda en pantalla
   llenaria la caja con seis copias de lo mismo. */
export function anotarMensaje(texto, tono = "") {
  if (!texto) return;
  const cuando = new Date().toISOString();
  const recorte = String(texto).slice(0, 300);
  const ultimo = MENSAJES[MENSAJES.length - 1];
  if (ultimo && ultimo.texto === recorte) {
    ultimo.cuando = cuando;
    return;
  }
  empujar(MENSAJES, { cuando, texto: recorte, tono }, 6);
}

/* Lo que va en el reporte: los mensajes y las llamadas, de la mas nueva
   a la mas vieja. */
export function cajaNegra() {
  const porHora = (a, b) => (a.cuando < b.cuando ? 1 : -1);
  return { mensajes: [...MENSAJES].sort(porHora),
           llamadas: [...ERRORES, ...RECIENTES].sort(porHora).slice(0, 10) };
}

/* La sesion vencio a media pantalla: se guarda donde estaba para volver
   ahi despues de entrar otra vez (seccion 101). Antes, quien estaba en
   el servicio 123 caia en la pantalla de inicio de su rol. */
const VOLVER = "centauro_volver";

function sesionVencida() {
  sesion.token = null;
  try {
    const donde = location.hash;
    if (donde && donde !== "#/entrar") sessionStorage.setItem(VOLVER, donde);
  } catch { /* sin sessionStorage se vuelve al inicio */ }
  location.hash = "#/entrar";
  return new ErrorApi(401, ErrorApi.texto("api_sesion_vencio"));
}

/* A donde volver despues de entrar, una sola vez. */
export function destinoPendiente() {
  try {
    const donde = sessionStorage.getItem(VOLVER);
    sessionStorage.removeItem(VOLVER);
    return donde && donde !== "#/entrar" ? donde : null;
  } catch { return null; }
}

/* El texto de una respuesta con error, ya como `detail` si era JSON. */
function detalleDe(texto, codigo, ruta) {
  try {
    const datos = JSON.parse(texto);
    if (datos && datos.detail !== undefined) return datos.detail;
  } catch { /* no era JSON */ }
  const recorte = String(texto || "").trim().slice(0, 400);
  return recorte ? "Error " + codigo + " · " + ruta + " · " + recorte : null;
}

async function pedir(metodo, ruta, cuerpo, opciones = {}) {
  try {
    const datos = await pedirAlServidor(metodo, ruta, cuerpo, opciones);
    anotarLlamada(metodo, ruta, 200);
    return datos;
  } catch (err) {
    anotarLlamada(metodo, ruta, err && typeof err.codigo === "number" ? err.codigo : 0,
                  err && err.message);
    throw err;
  }
}

async function pedirAlServidor(metodo, ruta, cuerpo, opciones = {}) {
  const cab = {};
  if (sesion.token) cab["Authorization"] = `Bearer ${sesion.token}`;
  if (cuerpo !== undefined) cab["Content-Type"] = "application/json";

  const texto_cuerpo = cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined;
  const limite = opciones.segundos
    || (texto_cuerpo && texto_cuerpo.length > PESADO ? SEGUNDOS_PESADO : SEGUNDOS);
  const control = new AbortController();
  const reloj = setTimeout(() => control.abort(), limite * 1000);

  let r;
  try {
    r = await fetch(ruta, {
      method: metodo,
      headers: cab,
      body: texto_cuerpo,
      signal: control.signal,
    });
  } catch (err) {
    /* Se fue la senal o se acabo el tiempo. Se marca con codigo 0 para
       que quien llama lo distinga de una respuesta del servidor: la
       cola reintenta esto, y la pantalla lo dice en el idioma de quien
       mira en vez de soltar el "Failed to fetch" del navegador. */
    throw new ErrorApi(0, err && err.name === "AbortError" ? "tardo" : "sin_red");
  } finally {
    clearTimeout(reloj);
  }

  if (r.status === 401) throw sesionVencida();
  if (opciones.crudo) {
    /* Un error con `crudo` (la hoja, el desglose) llegaba con el JSON
       tal cual: {"detail":{"mensaje":...}}. Se lee como los demas. */
    if (!r.ok) throw new ErrorApi(r.status, detalleDe(await r.text(), r.status, ruta));
    return r.text();
  }
  const texto = await r.text();
  let datos = null;
  try {
    datos = texto ? JSON.parse(texto) : null;
  } catch {
    /* El servidor contesto algo que no es JSON: casi siempre un error
       interno con su rastreo. Se muestra tal cual en vez de reventar
       aqui y tapar el error de verdad. */
    const recorte = texto.trim().slice(0, 400);
    throw new ErrorApi(r.status,
      /* Sin `t()` a proposito: es el unico mensaje que tiene que salir
         aunque `idioma.js` sea justo lo que no cargo. Un traductor que
         depende de lo que se rompio no traduce nada. Y no hay que
         traducir: "Error" se lee igual en los tres idiomas y lo demas
         son datos. */
      "Error " + r.status + " · " + ruta + " · " + recorte);
  }
  if (!r.ok) throw new ErrorApi(r.status, datos && datos.detail);
  return datos;
}

export const api = {
  get: (ruta, o) => pedir("GET", ruta, undefined, o),
  post: (ruta, cuerpo, o) => pedir("POST", ruta, cuerpo ?? {}, o),
  put: (ruta, cuerpo) => pedir("PUT", ruta, cuerpo ?? {}),
  patch: (ruta, cuerpo) => pedir("PATCH", ruta, cuerpo ?? {}),
  /* Un DELETE puede llevar cuerpo: el motivo por el que se borra algo. */
  borrar: (ruta, cuerpo) => pedir("DELETE", ruta, cuerpo),

  /* Una imagen del servidor tambien va con sesion. Puesta en el src a
     secas, el navegador la pide por su cuenta y sin token: el servidor
     la rechaza y queda el icono de imagen rota. Se baja aqui y se
     entrega como direccion local para el src. */
  async imagen(ruta) {
    const cab = {};
    if (sesion.token) cab["Authorization"] = `Bearer ${sesion.token}`;
    const r = await fetch(ruta, { headers: cab });
    if (r.status === 401) throw sesionVencida();
    if (!r.ok) throw new ErrorApi(r.status, detalleDe(await r.text(), r.status, ruta));
    return URL.createObjectURL(await r.blob());
  },

  /* Un archivo no viaja como JSON. El navegador arma el multipart solo,
     por eso aqui no se toca el Content-Type: si se pone a mano, se queda
     sin la frontera y el servidor no encuentra el archivo. */
  async subir(ruta, archivo, campo = "archivo") {
    const cab = {};
    if (sesion.token) cab["Authorization"] = `Bearer ${sesion.token}`;
    const cuerpo = new FormData();
    cuerpo.append(campo, archivo);
    const r = await fetch(ruta, { method: "POST", headers: cab, body: cuerpo });
    if (r.status === 401) throw sesionVencida();
    const datos = await r.json().catch(() => null);
    if (!r.ok) throw new ErrorApi(r.status, datos && datos.detail);
    return datos;
  },

  /* Un formulario con archivo y campos juntos. `subir` manda un solo
     archivo y nada mas; el deposito necesita mandar tambien la
     referencia y a quien se le paga, en la misma peticion: si el
     archivo viajara aparte, un corte de red a medio camino dejaria un
     deposito registrado sin su comprobante. */
  async formulario(ruta, campos, metodo = "POST") {
    const cab = {};
    if (sesion.token) cab["Authorization"] = `Bearer ${sesion.token}`;
    const cuerpo = new FormData();
    for (const [k, v] of Object.entries(campos)) {
      if (v !== null && v !== undefined) cuerpo.append(k, v);
    }
    const r = await fetch(ruta, { method: metodo, headers: cab, body: cuerpo });
    if (r.status === 401) throw sesionVencida();
    const datos = await r.json().catch(() => null);
    if (!r.ok) throw new ErrorApi(r.status, datos && datos.detail);
    return datos;
  },

  async entrar(correo, contrasena) {
    const cuerpo = new URLSearchParams({ username: correo, password: contrasena });
    const r = await fetch("/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: cuerpo,
    });
    if (!r.ok) {
      const d = await r.json().catch(() => null);
      throw new ErrorApi(r.status, (d && d.detail) || "Correo o contrasena incorrectos");
    }
    const datos = await r.json();
    sesion.token = datos.access_token;
    return datos;
  },

  async quienSoy() {
    sesion.usuario = await pedir("GET", "/auth/yo");
    return sesion.usuario;
  },

  salir() { sesion.token = null; sesion.usuario = null; },
};

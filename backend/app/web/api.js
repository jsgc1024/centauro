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
    super(ErrorApi.mensajeDe(detalle) || `Error ${codigo}`);
    this.codigo = codigo;
    this.detalle = detalle;
  }
  /* El backend contesta errores de tres formas: texto, {mensaje, ...} o
     la lista de validacion de FastAPI. Aqui se normalizan. */
  static mensajeDe(d) {
    if (!d) return null;
    if (typeof d === "string") return d;
    /* El backend escribe dos cosas distintas: que paso y que hacer. La
       segunda es la unica que sirve para salir del problema —"Registra
       primero la recepcion"— y se estaba tirando. Van juntas. */
    if (d.mensaje) return d.que_hacer ? `${d.mensaje}\n\n${d.que_hacer}`
                                      : d.mensaje;
    if (Array.isArray(d)) return d.map(x => x.msg || JSON.stringify(x)).join(". ");
    return null;
  }
}

async function pedir(metodo, ruta, cuerpo, opciones = {}) {
  const cab = {};
  if (sesion.token) cab["Authorization"] = `Bearer ${sesion.token}`;
  if (cuerpo !== undefined) cab["Content-Type"] = "application/json";

  const r = await fetch(ruta, {
    method: metodo,
    headers: cab,
    body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined,
  });

  if (r.status === 401) {
    sesion.token = null;
    location.hash = "#/entrar";
    throw new ErrorApi(401, "La sesion vencio. Vuelve a entrar.");
  }
  if (opciones.crudo) {
    if (!r.ok) throw new ErrorApi(r.status, await r.text());
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
      `El servidor contesto ${r.status} en ${ruta}. ${recorte}`);
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
    if (!r.ok) throw new ErrorApi(r.status, await r.text());
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
    if (r.status === 401) {
      sesion.token = null;
      location.hash = "#/entrar";
      throw new ErrorApi(401, "La sesion vencio. Vuelve a entrar.");
    }
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
    if (r.status === 401) {
      sesion.token = null;
      location.hash = "#/entrar";
      throw new ErrorApi(401, "La sesion vencio. Vuelve a entrar.");
    }
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

/* Consola de Centauro: entrada, navegacion y reparto por rol. */
import { ErrorApi, api, destinoPendiente, sesion } from "./api.js";
import { cartera, nuevoServicio } from "./consultor.js";
import { detener, tableroCentral } from "./central.js";
import { bandejaFinanzas } from "./finanzas.js";
import { pantallaFacturacion } from "./facturacion.js";
import { pantallaNomina } from "./nomina.js";
import { pantallaBonos } from "./bonos.js";
import { pantallaEncuestas } from "./encuestas.js";
import { pantallaPersonal } from "./personal.js";
import { pantallaFreelance } from "./freelance.js";
import { pantallaUnidades } from "./unidades.js";
import { carteraImplantados, nuevoImplantado,
         pantallaImplantado } from "./implantado.js";
import { detenerPanorama, pantallaPanorama } from "./panorama.js";
import { pantallaAccesos } from "./accesos.js";
import { pantallaOdoo } from "./odoo.js";
import { pantallaCatalogos } from "./catalogos_pantalla.js";
import { pantallaCalidad } from "./calidad.js";
import { pantallaManual } from "./manual.js";
import { pantallaDireccion } from "./direccion.js";
import { botonReportar } from "./falla.js";
// Entrar con huella o cara (30 sep): aparte, para no tocar lo demas.
import * as huella from "./huella.js";
import * as huellaConsola from "./huella_consola.js";
import { pantallaCodigo } from "./codigo.js";
import { pantallaEnlace, pantallaOlvide } from "./contrasena.js";
import { nombreDelRol } from "./categorias.js";
import { pantallaServicio } from "./servicio.js";
import { nuevaCotizacion, pantallaCotizacion,
         pantallaCotizaciones } from "./cotizaciones.js";
import { pantallaPropuesta } from "./propuesta.js";
import { aviso, campo, entrada, h, lista, mensaje, reponerMensajes, vaciar,
         vigilarCapturas } from "./util.js";
import { IDIOMAS, idioma, idiomaGuardado, ponerIdioma, t } from "./idioma.js";
import { abrirRecorrido } from "./recorrido.js";
import { firma } from "./firma.js";
import { ADMINISTRA, CALIDAD, CATALOGOS, CODIGO, CONSULTA, DESEMPENO,
         DINERO, DIRECCION, LEE_ODOO, MANUAL, MONITOREO, NOMINAS, PANORAMA,
         VOZ_CLIENTE, abre, destinoDe, menuDe } from "./menu.js";

/* La regla de captura vale para toda la consola, no para una
   pantalla: se engancha una sola vez al documento. */
vigilarCapturas();

/* Los errores de red y de captura salen en el idioma de quien mira:
   api.js no importa idioma.js (tiene que vivir aunque este no cargue),
   asi que se le presta el traductor aqui (seccion 101). */
ErrorApi.traducir = t;

/* Un solo oyente para cerrar los menus con un clic afuera (seccion
   101). Antes cada repintado de la barra enganchaba uno por grupo y
   otro por la pastilla, y ninguno se quitaba: tras una jornada eran
   cientos, cada uno reteniendo un menu viejo. */
document.addEventListener("click", (e) => {
  for (const caja of document.querySelectorAll("details.grupo_menu[open]")) {
    if (!caja.contains(e.target)) caja.open = false;
  }
  const menu = document.querySelector(".menu-yo");
  if (menu && !menu.hidden && !menu.contains(e.target)) menu.hidden = true;
});



let logo = null;

async function traerLogo() {
  if (logo !== null) return logo;
  try {
    const r = await api.get("/sistema/logo");
    logo = r.logo || "";
  } catch { logo = ""; }
  return logo;
}

/* Toda esta consola es de Proteccion Ejecutiva. Va dicho en el encabezado
   porque vienen mas lineas de operacion y no se deben confundir: el mismo
   prefijo que llevan los folios, AI/EP.

   Junto a la clave va el nombre de la consola, Connect, en el dorado de
   la puerta de entrada: la misma firma adentro y afuera. Decia
   "Proteccion Ejecutiva", que la clave AI/EP ya dice (Salvador, 26 sep).
   Es un nombre: no se traduce. */
const LINEA = "AI/EP";

function sello(conNombre = true) {
  return h("div", { clase: "linea" },
    h("span", { clase: "clave" }, LINEA),
    conNombre
      ? h("span", { clase: "nombre" }, firma(t("consola_sello"), t("lema")))
      : null);
}

function marca(alto = 40) {
  return logo
    ? h("img", { src: logo, alt: "Centauro", style: `height:${alto}px` })
    : h("span", { style: `font-weight:700;letter-spacing:3px;color:#1B1546;
                          font-size:${Math.round(alto / 3)}px` }, "CENTAURO");
}

/* La portada de las pantallas de antes de entrar: la marca de la
   empresa y, pegado a ella, el nombre de la consola: Connect. Es la
   puerta del personal administrativo y de los consultores, en
   mycentauro.lat; la app del personal de seguridad es otra puerta, en
   appep.mycentauro.lat, y se llama Proteccion Ejecutiva Connect App
   (secciones 70 y 71). Salvador la quiso limpia: sin repetir Centauro
   debajo del logo que ya lo dice. El nombre no se traduce --es un
   nombre--; la linea de abajo de la tarjeta, si. */
function portada() {
  return h("div", { clase: "portada" },
    marca(54),
    h("div", { clase: "app-sello" }, firma(t("consola_sello"), t("lema"))));
}

/* La tarjeta va sobre el fondo navy de la puerta, con su pie afuera. */
function puerta(tarjeta) {
  return h("div", { clase: "entrada" },
    h("div", { clase: "hoja-entrada" },
      tarjeta,
      h("p", { clase: "pie-entrada" }, t("entrada_pie"))));
}

/* ------------------------------------------------------------ entrada */

/* El correo con que se llega de las pantallas de antes de entrar: quien
   acaba de crear su contrasena no tiene por que volver a escribirlo, y
   quien pide el enlace ya lo habia escrito en la entrada. */
let correoSugerido = "";

async function pantallaEntrada(conContrasena = false) {
  await traerLogo();
  /* Antes de vaciar, no despues: de vaciar a pintar no puede haber un
     await. Al salir, la entrada se pinta dos veces seguidas (el boton y
     el cambio de direccion); con la espera en medio las dos vaciaban
     primero y luego pintaban las dos, y salia la entrada doble (seccion
     110). */
  const lector = await huella.hayLector();
  const cuerpo = document.getElementById("app");
  vaciar(cuerpo);

  /* Lo que sigue a entrar, con contrasena o con huella: la misma sesion
     y el mismo camino. */
  const alEntrar = async () => {
    await api.quienSoy();
    idiomaDelUsuario();
    /* Si la sesion vencio a media pantalla, se vuelve a esa pantalla
       (seccion 101); si no, al inicio de su rol. */
    location.hash = destinoPendiente() || destinoDe(sesion.usuario);
    pintar();
  };

  /* Quien ya entra con huella en este equipo (30 sep): "Hola, Salvador"
     y un boton. La contrasena queda a un clic. */
  if (lector && huella.recordado() && !conContrasena && !notaEntrada) {
    cuerpo.append(puerta(huellaConsola.saludo({
      portada: portada(), alEntrar,
      usarContrasena: () => pantallaEntrada(true),
      cambiarPersona: () => pantallaEntrada(true) })));
    return;
  }

  const correo = entrada("correo", { type: "email", required: "true",
                                     autocomplete: "username",
                                     value: correoSugerido || null });
  correoSugerido = "";

  const f = h("form", { onsubmit: async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(f).entries());
    const boton = f.querySelector("button");
    boton.disabled = true;
    try {
      const quien = (d.correo || "").trim().toLowerCase();
      const dentro = await api.entrar(quien, d.contrasena);
      /* Una sola vez: si este equipo tiene huella o cara, se ofrece
         entrar asi la proxima (30 sep). */
      if (await huella.convieneOfrecer(quien)) {
        await huellaConsola.ofrecer({ cuerpo, puerta, correo: quien,
                                      nombre: dentro.nombre,
                                      contrasena: d.contrasena });
      }
      await alEntrar();
    } catch (err) {
      f.querySelector(".error").replaceChildren(aviso(err.message, "grave"));
      boton.disabled = false;
    }
  }});

  const nota = notaEntrada ? aviso(notaEntrada, "ok") : null;
  notaEntrada = "";
  const error = h("div", { clase: "error" });
  /* `append` no es `h`: un null se pintaba como la palabra "null"
     encima del correo. Se filtra. */
  f.append(...[
    portada(),
    nota,
    campo(t("correo"), correo),
    campo(t("contrasena"), entrada("contrasena", { type: "password", required: "true",
                                                  autocomplete: "current-password" })),
    error,
    h("button", { type: "submit" }, t("entrar")),
    /* Con huella o cara, si el equipo tiene con que (30 sep). */
    lector ? huellaConsola.separador() : null,
    lector ? huellaConsola.botonEntrar({ alEntrar, correo, error, claro: true }) : null,
    /* Quien trabaja en la consola la recupera solo, por correo. El de
       campo lo lee en la pantalla siguiente: lo suyo va con su
       consultor o con la central. */
    h("div", { clase: "centro" },
      h("button", { type: "button", clase: "enlace", onclick: () => {
        correoSugerido = correo.value.trim();
        location.hash = "#/olvide";
      } }, t("cc_olvide")))].filter(Boolean));

  cuerpo.append(puerta(f));
}

/* La consola arranca en el idioma de quien entra --el de su plaza, que
   viene con su identidad-- si en este navegador nadie ha escogido uno
   (seccion 101). La bandera sigue mandando: lo que se escoge se queda. */
function idiomaDelUsuario() {
  const suyo = sesion.usuario && sesion.usuario.idioma;
  if (suyo && !idiomaGuardado() && suyo !== idioma()) ponerIdioma(suyo);
}

/* Lo que se abre sin haber entrado: el enlace del correo para crear la
   contrasena, y el "olvide mi contrasena". Se mira antes que la sesion:
   quien llega aqui no tiene una, o trae la de otra persona en esa misma
   computadora. */
const ANTES_DE_ENTRAR = [
  [/^#\/crear-contrasena\/([\w-]+)$/, pantallaEnlace],
  [/^#\/olvide$/, pantallaOlvide],
];

/* Lo que esas pantallas necesitan del armazon: la marca de arriba y el
   camino de vuelta a la entrada, con el correo ya escrito. */
function deAfuera() {
  const op = {
    cabecera: () => [portada()],
    puerta,
    correo: correoSugerido,
    irAEntrada: (correo = "", cerrarSesion = false) => {
      correoSugerido = correo;
      if (cerrarSesion) api.salir();
      location.hash = "#/entrar";
    },
  };
  correoSugerido = "";
  return op;
}

/* ------------------------------------------------------------ armazon */

function aqui(x) {
  const rutas = [x.ruta, ...(x.tambien || [])];
  return rutas.some(r => location.hash.startsWith(`#${r}`));
}

/* Una pantalla recien llegada lo dice en el menu unos dias, hasta la
   fecha que trae en `nueva` (menu.js). */
function esNueva(x) {
  return !!x.nueva && new Date() <= new Date(`${x.nueva}T23:59:59`);
}

function armazon() {
  const rol = sesion.usuario.rol;
  const nav = h("nav");
  const enlace = (x) => h("a", {
    href: `#${x.ruta}`,
    clase: aqui(x) ? "activo" : "",
  }, t(x.texto), esNueva(x) ? h("span", { clase: "etiqueta alerta nav-nueva" },
                                t("nav_nueva")) : null);

  /* El menu se arma respetando el orden de MENU: las entradas que
     comparten `grupo` se juntan en un solo boton que se abre. Se usa
     <details> y no un menu propio porque el navegador ya sabe abrirlo,
     cerrarlo con Escape y llegar a el con el teclado. */
  const grupos = new Map();
  for (const x of menuDe(sesion.usuario)) {
    if (!x.grupo) { nav.append(enlace(x)); continue; }
    if (!grupos.has(x.grupo)) {
      const caja = h("details", { clase: "grupo_menu" });
      caja.panel = h("div", { clase: "panel_menu" });
      grupos.set(x.grupo, caja);
      nav.append(caja);
    }
    grupos.get(x.grupo).panel.append(enlace(x));
  }
  for (const [clave, caja] of grupos) {
    /* Un grupo de uno no es un grupo. Los roles no ven lo mismo --hay
       quien alcanza la central y no el codigo-- y para esa persona el
       boton escondería una sola pantalla detrás de un nombre que no
       es el suyo. Se dibuja el enlace tal cual, en el lugar del
       grupo. */
    if (caja.panel.children.length === 1) {
      caja.replaceWith(caja.panel.children[0]);
      continue;
    }
    const dentro = [...caja.panel.children]
      .some(a => a.classList.contains("activo"));
    const boton = h("summary", { clase: dentro ? "activo" : "" }, t(clave));
    caja.append(boton, caja.panel);

    /* El panel se coloca al abrirlo, no antes: la barra se desplaza de
       lado en el celular y la posicion del boton cambia con ella. */
    caja.addEventListener("toggle", () => {
      if (!caja.open) return;
      const r = boton.getBoundingClientRect();
      caja.panel.style.top = `${r.bottom + 6}px`;
      caja.panel.style.left = `${Math.max(8, r.left)}px`;
    });
    /* Escoger algo cierra el grupo: dejarlo abierto tapa la pantalla
       que se acaba de pedir. Y un clic afuera tambien, porque un panel
       que solo se cierra con su propio boton se queda abierto. */
    caja.addEventListener("click", (e) => {
      if (e.target.tagName === "A") caja.open = false;
    });
  }

  /* El menu va en su propio renglon, debajo del logo: apretado entre la
     marca y los datos del usuario se perdia, y es lo que mas se usa de
     toda la pantalla. */
  return h("header", { clase: "barra" },
    h("div", { clase: "cinta" },
      h("div", { clase: "identidad" }, marca(40), sello()),
      quienSoy(rol)),
    nav);
}


/* Quien eres, en un solo control.

   Arriba competian siete cosas: la marca, el sello, el rol, el nombre,
   el correo, la bandera y Salir. Y abajo el menu, que es lo unico que
   se usa todo el dia. Darle aire a eso lo deja igual de amontonado y
   mas alto: lo que sobraba no era espacio, era informacion.

   El rol, el correo y el idioma no cambian nunca y nadie necesita leer
   su propio correo en cada pantalla. Se miran cuando hacen falta, que
   es casi nunca. Lo que si sirve de un vistazo es el nombre: dice con
   que cuenta estas trabajando, y en una consola donde el consultor ve
   lo suyo y el director lo de todos, eso importa.

   El idioma sigue a un toque: quien atiende a un cliente brasileño lo
   cambia una vez y se queda puesto la sesion entera. */
function quienSoy(rol) {
  const menu = h("div", { clase: "menu-yo", hidden: true },
    /* Su puesto si lo tiene --"Monitorista" dice mas que "central"--;
       si no, su rol, en el idioma de la consola (seccion 101: salia
       "director_operaciones" tal cual). */
    h("span", { clase: "rol" },
      sesion.usuario.puesto || nombreDelRol(rol)),
    h("div", { clase: "nombre" }, sesion.usuario.nombre),
    h("span", { clase: "correo" }, sesion.usuario.correo),
    h("hr"),
    /* Volver a verlo cuando uno quiera. Vive aqui, con lo que no cambia
       nunca: es donde alguien lo va a buscar sin que nadie se lo diga. */
    h("button", { clase: "otra-vez", type: "button", onclick: () => {
      menu.hidden = true;
      abrirRecorrido(menuDe(sesion.usuario));
    } }, t("rec_ver")),
    /* Cambiar la propia contrasena (seccion 101): la ruta existia y no
       tenia boton; habia que salir y usar "olvide mi contrasena". */
    h("button", { clase: "otra-vez", type: "button", onclick: () => {
      menu.hidden = true;
      location.hash = "#/mi-contrasena";
    } }, t("cc_cambiar")),
    /* Entrar con huella o cara (30 sep): en que equipos, y quitarla. */
    h("button", { clase: "otra-vez", type: "button", onclick: () => {
      menu.hidden = true;
      location.hash = "#/mi-huella";
    } }, huella.th("titulo")),
    h("div", { clase: "idiomas" }, ...IDIOMAS.map(i =>
      h("button", {
        clase: `bandera ${i.codigo === idioma() ? "activa" : ""}`.trim(),
        type: "button", title: i.nombre,
        onclick: () => {
          ponerIdioma(i.codigo);
          mensaje(t("idioma_puesto"));
          pintar();        // la consola entera se vuelve a pintar
        } }, i.bandera))),
    h("button", { clase: "salir", type: "button", onclick: () => {
      api.salir(); detener(); detenerPanorama();
      location.hash = "#/entrar"; pintar();
    } }, t("salir")));

  const pastilla = h("button", { clase: "pastilla", type: "button",
    title: sesion.usuario.correo,
    onclick: (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; } },
    h("span", { clase: "iniciales" }, iniciales(sesion.usuario.nombre)),
    h("span", { clase: "nom" }, nombreCorto(sesion.usuario.nombre)),
    h("span", { clase: "flecha" }, "▾"));

  // Se cierra al picar en cualquier otro lado: lo hace el oyente
  // global de arriba, uno para toda la consola.

  /* Reportar una falla (seccion 92) va aqui, a la vista en todas las
     pantallas y no dentro de la pastilla: se usa justo cuando algo salio
     mal, y en ese momento nadie va a buscar en un menu. */
  return h("div", { clase: "yo" }, botonReportar(), pastilla, menu);
}

/* Nombre y apellido, no el nombre completo: "Salvador Garcia Carrasco"
   en la pastilla la hace crecer hasta comerse el menu, y para reconocer
   de quien es la sesion sobra con dos palabras. */
function nombreCorto(nombre) {
  return (nombre || "").split(/\s+/).filter(Boolean).slice(0, 2).join(" ");
}

function iniciales(nombre) {
  const partes = (nombre || "").split(/\s+/).filter(Boolean);
  if (!partes.length) return "?";
  const primera = partes[0][0];
  return (partes.length > 1 ? primera + partes[1][0] : primera).toUpperCase();
}

/* ------------------------------------------------------------ personal */

/* La pantalla pedia `paises[0]` y llamaba `mx` a lo que saliera: el
   catalogo viene ordenado por nombre, asi que el primero es Brasil o
   Colombia, no Mexico. La tabla salia del pais equivocado y, si ahi no
   hay nadie, salia vacia sin decir por que.

   Ahora el pais se elige, arranca en el de quien esta viendo, y cuando
   no hay nadie lo dice con todas sus letras. */
/* ------------------------------------------------------- contrasena */

/* Cambiar la propia contrasena, desde adentro (seccion 101). Cualquiera
   con sesion puede; por eso no pasa por el menu ni por `abre`. Al
   guardarla, el servidor cierra todas las sesiones --tambien esta--, asi
   que se vuelve a la entrada con el correo ya puesto. */
let notaEntrada = "";

async function pantallaContrasena(main) {
  const actual = entrada("actual", { type: "password", required: "true",
                                      autocomplete: "current-password" });
  const nueva = entrada("nueva", { type: "password", required: "true",
                                    autocomplete: "new-password", minlength: "8" });
  const repite = entrada("repite", { type: "password", required: "true",
                                      autocomplete: "new-password" });
  const error = h("div");
  const f = h("form", { onsubmit: async (e) => {
    e.preventDefault();
    if (nueva.value !== repite.value) {
      error.replaceChildren(aviso(t("cc_no_coinciden"), "grave"));
      return;
    }
    const boton = f.querySelector("button[type=submit]");
    boton.disabled = true;
    try {
      await api.post("/auth/mi-contrasena", { actual: actual.value, nueva: nueva.value });
      correoSugerido = sesion.usuario.correo;
      notaEntrada = t("cc_cambiada_vuelve");
      api.salir(); detener(); detenerPanorama();
      location.hash = "#/entrar"; pintar();
    } catch (err) {
      error.replaceChildren(aviso(err.message, "grave"));
      boton.disabled = false;
    }
  } },
    h("h2", {}, t("cc_cambiar")),
    h("p", { clase: "sub" }, t("cc_nueva_sub")),
    campo(t("cc_actual"), actual),
    campo(t("cc_nueva"), nueva),
    campo(t("cc_repite"), repite),
    h("p", { clase: "gris chico" }, t("cc_reglas")),
    error,
    h("div", { clase: "acciones" },
      h("button", { type: "submit" }, t("cc_guardar")),
      h("button", { type: "button", clase: "claro chico", onclick: () => history.back() },
        t("cancelar"))));
  main.append(h("div", { clase: "tarjeta", style: "max-width:520px;margin:20px auto" }, f));
}

/* ------------------------------------------------------------ ruteo */

/* Cada ruta dice de que pantalla del menu es: quien no la tiene en su
   menu no la abre escribiendo la direccion a mano. El servidor sigue
   cuidando cada peticion; esto evita la pantalla a medio pintar. */
const RUTAS = [
  [/^#\/panorama$/, pantallaPanorama, "panorama", PANORAMA],
  [/^#\/cotizaciones$/, pantallaCotizaciones, "cotizaciones", CONSULTA],
  [/^#\/cotizacion\/nueva$/, nuevaCotizacion, "cotizaciones", CONSULTA],
  [/^#\/cotizacion\/(\d+|eventual)$/, pantallaCotizacion, "cotizaciones", CONSULTA],
  /* La propuesta del implantado (seccion 115), en la misma pantalla. */
  [/^#\/propuesta\/(\d+|nueva)$/, pantallaPropuesta, "cotizaciones", CONSULTA],
  [/^#\/servicios$/, cartera, "servicios", CONSULTA],
  [/^#\/servicio\/nuevo$/, nuevoServicio, "servicios", CONSULTA],
  [/^#\/servicio\/(\d+)$/, pantallaServicio, "servicios", CONSULTA],
  [/^#\/implantados$/, carteraImplantados, "implantados", CONSULTA],
  [/^#\/implantado\/nuevo$/, nuevoImplantado, "implantados", CONSULTA],
  [/^#\/implantado\/(\d+)$/, pantallaImplantado, "implantados", CONSULTA],
  [/^#\/central$/, tableroCentral, "central", MONITOREO],
  [/^#\/equipo$/, pantallaPersonal, "equipo", CONSULTA],
  /* La ficha de una persona, abierta directo: desde Calidad (seccion 89),
     el certificado vencido lleva a quien lo trae. */
  [/^#\/equipo\/(\d+)$/, pantallaPersonal, "equipo", CONSULTA],
  /* El freelance (seccion 111): su alta y su ficha, dentro de Personal. */
  [/^#\/freelance\/(\d+|nuevo)$/, pantallaFreelance, "equipo", CONSULTA],
  [/^#\/unidades$/, pantallaUnidades, "unidades", MONITOREO],
  [/^#\/finanzas$/, bandejaFinanzas, "finanzas", DINERO],
  [/^#\/facturacion$/, pantallaFacturacion, "facturacion", DINERO],
  /* Nominas, y la pestana de comisiones de un pais y un mes abierta
     directo desde el panel de direccion (seccion 131):
     #/nomina/comisiones/<pais>/<anio>-<mes>. */
  [/^#\/nomina\/?(comisiones\/\d+\/\d{4}-\d{1,2})?$/, pantallaNomina, "nomina", NOMINAS],
  [/^#\/bonos$/, pantallaBonos, "bonos", DESEMPENO],
  [/^#\/encuestas$/, pantallaEncuestas, "encuestas", VOZ_CLIENTE],
  [/^#\/calidad$/, pantallaCalidad, "calidad", CALIDAD],
  /* La ventana del director de operaciones (seccion 105). */
  [/^#\/direccion$/, pantallaDireccion, "direccion", DIRECCION],
  [/^#\/codigo$/, pantallaCodigo, "codigo", CODIGO],
  [/^#\/accesos$/, pantallaAccesos, "accesos", ADMINISTRA],
  [/^#\/odoo$/, pantallaOdoo, "odoo", LEE_ODOO],
  [/^#\/catalogos$/, pantallaCatalogos, "catalogos", CATALOGOS],
  /* El manual y sus paginas: #/manual, #/manual/atorado,
     #/manual/leer/<capitulo>, y asi. La pantalla reparte el resto. */
  [/^#\/manual\b\/?(.*)$/, pantallaManual, "manual", MANUAL],
];

async function pintar() {
  const cuerpo = document.getElementById("app");

  for (const [patron, vista] of ANTES_DE_ENTRAR) {
    const coincide = location.hash.match(patron);
    if (!coincide) continue;
    await traerLogo();
    return vista(cuerpo, deAfuera(), coincide[1]);
  }

  if (!sesion.token) return pantallaEntrada();
  if (!sesion.usuario) {
    try { await api.quienSoy(); } catch { return pantallaEntrada(); }
    idiomaDelUsuario();
  }
  await traerLogo();

  if (!location.hash || location.hash === "#/entrar") {
    location.hash = destinoDe(sesion.usuario);
    return;
  }

  vaciar(cuerpo);
  const main = h("main");
  const mensajes = h("div", { id: "mensajes",
    style: "max-width:1180px;margin:10px auto 0;padding:0 20px" });
  cuerpo.append(armazon(), mensajes, main);
  /* El aviso de la accion que trajo hasta aqui sigue a la vista. */
  reponerMensajes(mensajes);

  /* La primera vez, el recorrido. Una sola vez por persona y no por
     navegador: quien ya lo vio no lo vuelve a ver porque cambio de
     computadora. Se marca al abrirlo, asi que se cierra con un clic y
     no vuelve a salir. */
  if (sesion.usuario.recorrido_pendiente) {
    sesion.usuario.recorrido_pendiente = false;
    abrirRecorrido(menuDe(sesion.usuario));
  }

  if (location.hash === "#/mi-huella") {
    try { await huellaConsola.pantalla(main, sesion.usuario); }
    catch (err) { main.append(aviso(err.message, "grave")); }
    return;
  }

  if (location.hash === "#/mi-contrasena") {
    try { await pantallaContrasena(main); } catch (err) { main.append(aviso(err.message, "grave")); }
    return;
  }

  for (const [patron, vista, clave, roles] of RUTAS) {
    const coincide = location.hash.match(patron);
    if (!coincide) continue;
    if (!abre(sesion.usuario, clave, roles)) {
      main.append(aviso(t("sin_acceso"), "grave"));
      return;
    }
    try {
      await vista(main, coincide[1]);
    } catch (err) {
      main.append(aviso(err.message, "grave"));
    }
    return;
  }
  main.append(aviso(t("no_existe"), "alerta"));
}

window.addEventListener("hashchange", () => {
  detener(); detenerPanorama(); pintar();
});
pintar();

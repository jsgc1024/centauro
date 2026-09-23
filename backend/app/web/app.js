/* Consola de Centauro: entrada, navegacion y reparto por rol. */
import { api, sesion } from "./api.js";
import { cartera, nuevoServicio } from "./consultor.js";
import { detener, tableroCentral } from "./central.js";
import { bandejaFinanzas } from "./finanzas.js";
import { pantallaNomina } from "./nomina.js";
import { pantallaBonos } from "./bonos.js";
import { pantallaEncuestas } from "./encuestas.js";
import { pantallaPersonal } from "./personal.js";
import { carteraImplantados, nuevoImplantado,
         pantallaImplantado } from "./implantado.js";
import { detenerPanorama, pantallaPanorama } from "./panorama.js";
import { pantallaAccesos } from "./accesos.js";
import { pantallaCodigo } from "./codigo.js";
import { pantallaServicio } from "./servicio.js";
import { aviso, campo, entrada, h, lista, mensaje, vaciar,
         vigilarCapturas } from "./util.js";
import { IDIOMAS, idioma, ponerIdioma, t } from "./idioma.js";
import { abrirRecorrido } from "./recorrido.js";

/* La regla de captura vale para toda la consola, no para una
   pantalla: se engancha una sola vez al documento. */
vigilarCapturas();

const CONSULTA = ["consultor", "director_operaciones", "director_general", "admin"];
/* El consultor tambien entra: la central de inteligencia le dice que le
   falta a SUS servicios de manana, y es el que lo tiene que resolver
   antes del corte. Dejarlo fuera era mandarle el recado por telefono. */
const MONITOREO = ["central", "consultor", "director_operaciones",
                   "director_general", "admin"];
/* La bandeja de finanzas la abre finanzas; direccion la mira sin tocar. */
const DINERO = ["finanzas", "director_operaciones", "director_general", "admin"];
/* Quien le dicta el codigo al personal de campo. La central porque
   esta despierta a las 5:40, que es cuando de verdad pasa; el
   consultor porque conoce a su gente por la voz, que es lo unico que
   protege este camino. Direccion de operaciones no entra. */
const CODIGO = ["consultor", "central", "director_general", "admin"];
/* Quien reparte permisos. Direccion general quedo como super
   administrador por decision de la direccion (ver PROPUESTA_ACCESOS.md):
   quien puede abrir esta pantalla puede darle a alguien un permiso que
   cuesta dinero. */
const ADMINISTRA = ["admin", "director_general", "recursos_humanos"];
/* El desempeno lo mira casi todo el mundo y lo toca casi nadie: la
   central y el consultor ven el mes de su gente, operaciones firma,
   finanzas deposita. Quien autoriza y quien paga se separan en el
   servidor, no aqui. */
const DESEMPENO = ["consultor", "central", "finanzas", "recursos_humanos",
                   "director_operaciones", "director_general", "admin"];
/* Lo que dijo el cliente. Lo abre quien puede hacer algo con eso: el
   consultor revisa lo suyo, operaciones lo de todos, la central porque
   es quien contesta el telefono cuando el cliente vuelve a llamar. */
const VOZ_CLIENTE = ["consultor", "central", "finanzas",
                     "director_operaciones", "director_general", "admin"];

/* El menu de arriba, en una sola lista.

   De aqui sale la barra Y sale el recorrido de la primera vez. Son la
   misma cosa dicha dos veces, y dos listas se separan: el dia que se
   agregue una pantalla, el recorrido la trae sola o `revisar.py` se
   queja de que le falta el texto. Un tutorial que vive aparte se
   despega el dia que la pantalla cambia, y nadie se entera hasta que
   alguien sigue un paso que ya no existe.

   `quienes` en nulo quiere decir que la ve todo el mundo. */
const MENU = [
  /* Las tres de operacion van juntas bajo un solo boton.
     Sueltas eran tres de once entradas, y once no caben en la barra
     sin apretarla. Y el grupo lleva la linea en el nombre --EP, por
     Proteccion Ejecutiva-- porque vienen mas lineas de operacion: el
     dia que llegue la siguiente, este menu ya sabe como crecer. */
  { ruta: "/panorama", texto: "nav_operacion", grupo: "nav_operaciones_ep",
    cuenta: "rec_operacion", quienes: null },
  /* Eventual e implantado son dos operaciones distintas y se capturan
     distinto; cada una tiene su boton para no tener que escoger el tipo
     dentro de una pantalla que sirve para las dos. */
  { ruta: "/servicios", texto: "nav_eventuales", grupo: "nav_operaciones_ep",
    /* Estando dentro de un servicio, el boton del grupo sigue
       encendido: `#/servicio/12` no empieza con `#/servicios`. */
    tambien: ["/servicio/"],
    cuenta: "rec_eventuales", quienes: CONSULTA },
  { ruta: "/implantados", texto: "nav_implantados", grupo: "nav_operaciones_ep",
    tambien: ["/implantado/"],
    cuenta: "rec_implantados", quienes: CONSULTA },
  /* Central de Inteligencia: el tablero de lo que esta corriendo y el
     codigo que se le dicta al personal de campo. Los dos son la misma
     mesa a las 5:40 de la manana. */
  { ruta: "/central", texto: "nav_central", grupo: "nav_operaciones_ci",
    cuenta: "rec_central", quienes: MONITOREO },
  /* Gestion Administrativa: lo que se paga y quien puede que cosa.
     Dos bolsas distintas y dos pantallas: los gastos del servicio
     —viaticos y compras— y la nomina del personal de seguridad. */
  { ruta: "/finanzas", texto: "nav_finanzas", grupo: "nav_administrativa",
    cuenta: "rec_finanzas", quienes: DINERO },
  { ruta: "/nomina", texto: "nav_nomina", grupo: "nav_administrativa",
    cuenta: "rec_nomina", quienes: DINERO },
  /* El personal va en Operaciones EP: a quien se manda es una decision
     de operacion, y se toma mirando la misma cartera. */
  { ruta: "/equipo", texto: "nav_personal", grupo: "nav_operaciones_ep",
    cuenta: "rec_personal", quienes: CONSULTA },
  /* El desempeno del personal y su bono del mes vencido, que se
     calcula el dia 3 y se deposita el 5. Va en Operaciones EP
     --decision de Salvador, 23 sep--, junto a Personal: lo que mide
     es como trabajo la gente en la calle, y lo consulta quien decide
     a quien se manda. Estaba junto a la nomina porque el bono es
     dinero. */
  { ruta: "/bonos", texto: "nav_bonos", grupo: "nav_operaciones_ep",
    cuenta: "rec_bonos", quienes: DESEMPENO },
  /* La voz del cliente. Una calificacion baja abre revision y hasta
     hoy nadie podia verla: el motor llevaba meses escrito sin pantalla.

     Va en Operaciones EP --decision de Salvador-- y no suelta en la
     barra: lo que el cliente califica es el servicio, y quien lee una
     calificacion baja acaba abriendo la cartera en el mismo minuto. */
  { ruta: "/encuestas", texto: "nav_encuestas", grupo: "nav_operaciones_ep",
    cuenta: "rec_encuestas", quienes: VOZ_CLIENTE },
  /* A un toque, porque la llamada llega a las 5:40 y casi siempre al
     telefono. Escondida dentro de un servicio serian cuatro toques con
     una mano. */
  { ruta: "/codigo", texto: "nav_codigo", grupo: "nav_operaciones_ci",
    cuenta: "rec_codigo", quienes: CODIGO },
  { ruta: "/accesos", texto: "nav_accesos", grupo: "nav_administrativa",
    cuenta: "rec_accesos", quienes: ADMINISTRA },
];

export function menuDe(rol) {
  return MENU.filter(x => !x.quienes || x.quienes.includes(rol));
}

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
   prefijo que llevan los folios, AI/EP. */
const LINEA = "AI/EP";
// El nombre de la linea se dice en el idioma de la consola; la clave no.

function sello(conNombre = true) {
  return h("div", { clase: "linea" },
    h("span", { clase: "clave" }, LINEA),
    conNombre ? h("span", { clase: "nombre" }, t("linea")) : null);
}

function marca(alto = 40) {
  return logo
    ? h("img", { src: logo, alt: "Centauro", style: `height:${alto}px` })
    : h("span", { style: `font-weight:700;letter-spacing:3px;color:#1B1546;
                          font-size:${Math.round(alto / 3)}px` }, "CENTAURO");
}

/* ------------------------------------------------------------ entrada */

async function pantallaEntrada() {
  await traerLogo();
  const cuerpo = document.getElementById("app");
  vaciar(cuerpo);

  const f = h("form", { onsubmit: async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(f).entries());
    const boton = f.querySelector("button");
    boton.disabled = true;
    try {
      await api.entrar(d.correo, d.contrasena);
      await api.quienSoy();
      location.hash = destinoDe(sesion.usuario.rol);
      pintar();
    } catch (err) {
      f.querySelector(".error").replaceChildren(aviso(err.message, "grave"));
      boton.disabled = false;
    }
  }});

  f.append(
    marca(62),
    sello(),
    campo(t("correo"), entrada("correo", { type: "email", required: "true",
                                          autocomplete: "username" })),
    campo(t("contrasena"), entrada("contrasena", { type: "password", required: "true",
                                                  autocomplete: "current-password" })),
    h("div", { clase: "error" }),
    h("button", { type: "submit" }, t("entrar")));

  cuerpo.append(h("div", { clase: "entrada" }, f));
}

function destinoDe(rol) {
  if (rol === "central") return "#/central";
  if (rol === "consultor") return "#/servicios";
  if (rol === "finanzas") return "#/finanzas";
  /* RRHH abre en el bono: es lo que hace todos los dias 3 y 5 del mes,
     y la pantalla de accesos se usa cuando entra o sale alguien. */
  if (rol === "recursos_humanos") return "#/bonos";
  return "#/panorama";
}

/* ------------------------------------------------------------ armazon */

function aqui(x) {
  const rutas = [x.ruta, ...(x.tambien || [])];
  return rutas.some(r => location.hash.startsWith(`#${r}`));
}

function armazon() {
  const rol = sesion.usuario.rol;
  const nav = h("nav");
  const enlace = (x) => h("a", {
    href: `#${x.ruta}`,
    clase: aqui(x) ? "activo" : "",
  }, t(x.texto));

  /* El menu se arma respetando el orden de MENU: las entradas que
     comparten `grupo` se juntan en un solo boton que se abre. Se usa
     <details> y no un menu propio porque el navegador ya sabe abrirlo,
     cerrarlo con Escape y llegar a el con el teclado. */
  const grupos = new Map();
  for (const x of menuDe(rol)) {
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
    document.addEventListener("click", (e) => {
      if (caja.open && !caja.contains(e.target)) caja.open = false;
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
    h("span", { clase: "rol" }, rol.replace("_", " ")),
    h("div", { clase: "nombre" }, sesion.usuario.nombre),
    h("span", { clase: "correo" }, sesion.usuario.correo),
    h("hr"),
    /* Volver a verlo cuando uno quiera. Vive aqui, con lo que no cambia
       nunca: es donde alguien lo va a buscar sin que nadie se lo diga. */
    h("button", { clase: "otra-vez", type: "button", onclick: () => {
      menu.hidden = true;
      abrirRecorrido(menuDe(rol));
    } }, t("rec_ver")),
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

  // Se cierra al picar en cualquier otro lado, como cualquier menu.
  document.addEventListener("click", () => { menu.hidden = true; });

  return h("div", { clase: "yo" }, pastilla, menu);
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
/* ------------------------------------------------------------ ruteo */

const TODOS = ["consultor", "central", "finanzas", "recursos_humanos",
               "director_operaciones", "director_general", "admin"];

const RUTAS = [
  [/^#\/panorama$/, pantallaPanorama, TODOS],
  [/^#\/servicios$/, cartera, CONSULTA],
  [/^#\/servicio\/nuevo$/, nuevoServicio, CONSULTA],
  [/^#\/servicio\/(\d+)$/, pantallaServicio, CONSULTA],
  [/^#\/implantados$/, carteraImplantados, CONSULTA],
  [/^#\/implantado\/nuevo$/, nuevoImplantado, CONSULTA],
  [/^#\/implantado\/(\d+)$/, pantallaImplantado, CONSULTA],
  [/^#\/central$/, tableroCentral, MONITOREO],
  [/^#\/equipo$/, pantallaPersonal, CONSULTA],
  [/^#\/finanzas$/, bandejaFinanzas, DINERO],
  [/^#\/nomina$/, pantallaNomina, DINERO],
  [/^#\/bonos$/, pantallaBonos, DESEMPENO],
  [/^#\/encuestas$/, pantallaEncuestas, VOZ_CLIENTE],
  [/^#\/codigo$/, pantallaCodigo, CODIGO],
  [/^#\/accesos$/, pantallaAccesos, ADMINISTRA],
];

async function pintar() {
  const cuerpo = document.getElementById("app");

  if (!sesion.token) return pantallaEntrada();
  if (!sesion.usuario) {
    try { await api.quienSoy(); } catch { return pantallaEntrada(); }
  }
  await traerLogo();

  if (!location.hash || location.hash === "#/entrar") {
    location.hash = destinoDe(sesion.usuario.rol);
    return;
  }

  vaciar(cuerpo);
  const main = h("main");
  cuerpo.append(armazon(), h("div", { id: "mensajes",
    style: "max-width:1180px;margin:10px auto 0;padding:0 20px" }), main);

  /* La primera vez, el recorrido. Una sola vez por persona y no por
     navegador: quien ya lo vio no lo vuelve a ver porque cambio de
     computadora. Se marca al abrirlo, asi que se cierra con un clic y
     no vuelve a salir. */
  if (sesion.usuario.recorrido_pendiente) {
    sesion.usuario.recorrido_pendiente = false;
    abrirRecorrido(menuDe(sesion.usuario.rol));
  }

  for (const [patron, vista, roles] of RUTAS) {
    const coincide = location.hash.match(patron);
    if (!coincide) continue;
    if (!roles.includes(sesion.usuario.rol)) {
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

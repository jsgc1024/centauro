/* Consola de Centauro: entrada, navegacion y reparto por rol. */
import { api, sesion } from "./api.js";
import { cartera, nuevoServicio } from "./consultor.js";
import { detener, tableroCentral } from "./central.js";
import { bandejaFinanzas } from "./finanzas.js";
import { pantallaNomina } from "./nomina.js";
import { carteraImplantados, nuevoImplantado,
         pantallaImplantado } from "./implantado.js";
import { detenerPanorama, pantallaPanorama } from "./panorama.js";
import { pantallaServicio } from "./servicio.js";
import { aviso, campo, entrada, h, mensaje, vaciar, vigilarCapturas } from "./util.js";
import { IDIOMAS, idioma, ponerIdioma, t } from "./idioma.js";

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
  return "#/panorama";
}

/* ------------------------------------------------------------ armazon */

function armazon() {
  const rol = sesion.usuario.rol;
  const nav = h("nav");
  const enlace = (ruta, texto) => h("a", {
    href: `#${ruta}`,
    clase: location.hash.startsWith(`#${ruta}`) ? "activo" : "",
  }, texto);

  nav.append(enlace("/panorama", t("nav_operacion")));
  /* Eventual e implantado son dos operaciones distintas y se capturan
     distinto; cada una tiene su boton para no tener que escoger el tipo
     dentro de una pantalla que sirve para las dos. */
  if (CONSULTA.includes(rol)) {
    nav.append(enlace("/servicios", t("nav_eventuales")));
    nav.append(enlace("/implantados", t("nav_implantados")));
  }
  if (MONITOREO.includes(rol)) nav.append(enlace("/central", t("nav_central")));
  /* Dos bolsas distintas y dos pantallas: los gastos del servicio
     —viaticos y compras— y la nomina del personal de seguridad. */
  if (DINERO.includes(rol)) {
    nav.append(enlace("/finanzas", t("nav_finanzas")));
    nav.append(enlace("/nomina", t("nav_nomina")));
  }
  if (CONSULTA.includes(rol)) nav.append(enlace("/equipo", t("nav_personal")));

  /* El menu va en su propio renglon, debajo del logo: apretado entre la
     marca y los datos del usuario se perdia, y es lo que mas se usa de
     toda la pantalla. */
  return h("header", { clase: "barra" },
    h("div", { clase: "cinta" },
      h("div", { clase: "identidad" }, marca(40), sello()),
      h("div", { clase: "quien sello" },
        h("span", { clase: "rol" }, rol.replace("_", " ")),
        h("span", { clase: "nombre" }, sesion.usuario.nombre),
        h("span", { clase: "correo" }, sesion.usuario.correo)),
      banderas(),
      h("button", { clase: "claro chico", onclick: () => {
        api.salir(); detener(); detenerPanorama();
        location.hash = "#/entrar"; pintar();
      } }, t("salir"))),
    nav);
}

/* El idioma de la consola. Se elige por bandera porque es lo que se
   reconoce de un vistazo, y se queda puesto toda la sesion: quien
   atiende a un cliente brasileño trabaja el dia entero en portugues.

   El TS es aparte: sale en el idioma que prefiera el ejecutivo, y para
   eso estan sus tres botones. */
function banderas() {
  /* Se ve una sola bandera —la que esta puesta— y al picarla se abren
     las otras dos. Tres banderas siempre a la vista parecen tres botones
     que hacen algo distinto; una sola dice en que idioma esta la consola
     y se quita de en medio. */
  const caja = h("div", { clase: "banderas" });
  const actual = IDIOMAS.find(i => i.codigo === idioma()) || IDIOMAS[0];

  const otras = h("div", { clase: "otras-banderas", hidden: true },
    ...IDIOMAS.filter(i => i.codigo !== actual.codigo).map(i =>
      h("button", { clase: "bandera", type: "button", title: i.nombre,
        onclick: () => {
          ponerIdioma(i.codigo);
          mensaje(t("idioma_puesto"));
          pintar();        // la consola entera se vuelve a pintar
        } }, i.bandera, h("span", { clase: "nombre-idioma" }, i.nombre))));

  const puesta = h("button", { clase: "bandera activa", type: "button",
    title: actual.nombre,
    onclick: (e) => { e.stopPropagation(); otras.hidden = !otras.hidden; } },
    actual.bandera);

  // Se cierra al picar en cualquier otro lado, como cualquier menu.
  document.addEventListener("click", () => { otras.hidden = true; });

  caja.append(puesta, otras);
  return caja;
}

/* ------------------------------------------------------------ personal */

async function pantallaPersonal(main) {
  const paises = await api.get("/catalogos/paises");
  const mx = paises[0];
  const filas = await api.get(`/profesionalismo?pais_id=${mx.id}`);

  main.append(h("h1", {}, t("personal_titulo")),
              h("p", { clase: "sub" }, t("personal_sub")));

  const cuerpo = h("tbody");
  for (const p of filas) {
    cuerpo.append(h("tr", {},
      h("td", {}, h("b", {}, p.persona),
        h("div", { clase: "gris chico" }, p.plaza)),
      h("td", { clase: "num", style: "font-size:18px;font-weight:650" },
        p.calificacion),
      h("td", { clase: "chico gris" }, `confianza ${p.confianza}`),
      h("td", { clase: "num" }, `${p.horas_en_centauro} h`)));
  }
  main.append(h("table", { clase: "lista" },
    h("thead", {}, h("tr", {},
      h("th", {}, t("col_persona")), h("th", {}, t("col_calificacion")),
      h("th", {}, t("col_confianza")), h("th", {}, t("col_experiencia")))),
    cuerpo));
}

/* ------------------------------------------------------------ ruteo */

const TODOS = ["consultor", "central", "finanzas",
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

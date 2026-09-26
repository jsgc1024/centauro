/* Consola de Centauro: entrada, navegacion y reparto por rol. */
import { api, sesion } from "./api.js";
import { cartera, nuevoServicio } from "./consultor.js";
import { detener, tableroCentral } from "./central.js";
import { bandejaFinanzas } from "./finanzas.js";
import { pantallaFacturacion } from "./facturacion.js";
import { pantallaNomina } from "./nomina.js";
import { pantallaBonos } from "./bonos.js";
import { pantallaEncuestas } from "./encuestas.js";
import { pantallaPersonal } from "./personal.js";
import { pantallaUnidades } from "./unidades.js";
import { carteraImplantados, nuevoImplantado,
         pantallaImplantado } from "./implantado.js";
import { detenerPanorama, pantallaPanorama } from "./panorama.js";
import { pantallaAccesos } from "./accesos.js";
import { pantallaOdoo } from "./odoo.js";
import { pantallaCodigo } from "./codigo.js";
import { pantallaEnlace, pantallaOlvide } from "./contrasena.js";
import { pantallaServicio } from "./servicio.js";
import { aviso, campo, entrada, h, lista, mensaje, vaciar,
         vigilarCapturas } from "./util.js";
import { IDIOMAS, idioma, ponerIdioma, t } from "./idioma.js";
import { abrirRecorrido } from "./recorrido.js";
import { firma } from "./firma.js";
import { ADMINISTRA, CODIGO, CONSULTA, DESEMPENO, DINERO, LEE_ODOO,
         MONITOREO, NOMINAS, PANORAMA, VOZ_CLIENTE, abre, destinoDe,
         menuDe } from "./menu.js";

/* La regla de captura vale para toda la consola, no para una
   pantalla: se engancha una sola vez al documento. */
vigilarCapturas();



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

async function pantallaEntrada() {
  await traerLogo();
  const cuerpo = document.getElementById("app");
  vaciar(cuerpo);

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
      await api.entrar(d.correo, d.contrasena);
      await api.quienSoy();
      location.hash = destinoDe(sesion.usuario);
      pintar();
    } catch (err) {
      f.querySelector(".error").replaceChildren(aviso(err.message, "grave"));
      boton.disabled = false;
    }
  }});

  f.append(
    portada(),
    campo(t("correo"), correo),
    campo(t("contrasena"), entrada("contrasena", { type: "password", required: "true",
                                                  autocomplete: "current-password" })),
    h("div", { clase: "error" }),
    h("button", { type: "submit" }, t("entrar")),
    /* Quien trabaja en la consola la recupera solo, por correo. El de
       campo lo lee en la pantalla siguiente: lo suyo va con su
       consultor o con la central. */
    h("div", { clase: "centro" },
      h("button", { type: "button", clase: "enlace", onclick: () => {
        correoSugerido = correo.value.trim();
        location.hash = "#/olvide";
      } }, t("cc_olvide"))));

  cuerpo.append(puerta(f));
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
    /* Su puesto si lo tiene --"Monitorista" dice mas que "central"--;
       si no, su rol, como siempre. */
    h("span", { clase: "rol" },
      sesion.usuario.puesto || rol.replaceAll("_", " ")),
    h("div", { clase: "nombre" }, sesion.usuario.nombre),
    h("span", { clase: "correo" }, sesion.usuario.correo),
    h("hr"),
    /* Volver a verlo cuando uno quiera. Vive aqui, con lo que no cambia
       nunca: es donde alguien lo va a buscar sin que nadie se lo diga. */
    h("button", { clase: "otra-vez", type: "button", onclick: () => {
      menu.hidden = true;
      abrirRecorrido(menuDe(sesion.usuario));
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

/* Cada ruta dice de que pantalla del menu es: quien no la tiene en su
   menu no la abre escribiendo la direccion a mano. El servidor sigue
   cuidando cada peticion; esto evita la pantalla a medio pintar. */
const RUTAS = [
  [/^#\/panorama$/, pantallaPanorama, "panorama", PANORAMA],
  [/^#\/servicios$/, cartera, "servicios", CONSULTA],
  [/^#\/servicio\/nuevo$/, nuevoServicio, "servicios", CONSULTA],
  [/^#\/servicio\/(\d+)$/, pantallaServicio, "servicios", CONSULTA],
  [/^#\/implantados$/, carteraImplantados, "implantados", CONSULTA],
  [/^#\/implantado\/nuevo$/, nuevoImplantado, "implantados", CONSULTA],
  [/^#\/implantado\/(\d+)$/, pantallaImplantado, "implantados", CONSULTA],
  [/^#\/central$/, tableroCentral, "central", MONITOREO],
  [/^#\/equipo$/, pantallaPersonal, "equipo", CONSULTA],
  [/^#\/unidades$/, pantallaUnidades, "unidades", MONITOREO],
  [/^#\/finanzas$/, bandejaFinanzas, "finanzas", DINERO],
  [/^#\/facturacion$/, pantallaFacturacion, "facturacion", DINERO],
  [/^#\/nomina$/, pantallaNomina, "nomina", NOMINAS],
  [/^#\/bonos$/, pantallaBonos, "bonos", DESEMPENO],
  [/^#\/encuestas$/, pantallaEncuestas, "encuestas", VOZ_CLIENTE],
  [/^#\/codigo$/, pantallaCodigo, "codigo", CODIGO],
  [/^#\/accesos$/, pantallaAccesos, "accesos", ADMINISTRA],
  [/^#\/odoo$/, pantallaOdoo, "odoo", LEE_ODOO],
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
  }
  await traerLogo();

  if (!location.hash || location.hash === "#/entrar") {
    location.hash = destinoDe(sesion.usuario);
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
    abrirRecorrido(menuDe(sesion.usuario));
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
